package main

import (
	"archive/zip"
	"bytes"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func updateTestDigest(content []byte) string {
	hash := sha256.Sum256(content)
	return hex.EncodeToString(hash[:])
}

func updateTestArchive(t *testing.T, files map[string][]byte, prefix string) ([]byte, portableUpdateManifest) {
	t.Helper()
	var buffer bytes.Buffer
	writer := zip.NewWriter(&buffer)
	manifest := portableUpdateManifest{Schema: 1, Revision: strings.Repeat("b", 40), Package: portableUpdatePackage}
	names := make([]string, 0, len(files))
	for name := range files {
		names = append(names, name)
	}
	sort.Strings(names)
	for _, name := range names {
		content := files[name]
		header := &zip.FileHeader{Name: prefix + name, Method: zip.Store}
		header.SetMode(0644)
		entry, err := writer.CreateHeader(header)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := entry.Write(content); err != nil {
			t.Fatal(err)
		}
		manifest.Files = append(manifest.Files, portableUpdateFile{Path: name, Size: int64(len(content)), SHA256: updateTestDigest(content)})
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	archive := buffer.Bytes()
	manifest.Size = int64(len(archive))
	manifest.SHA256 = updateTestDigest(archive)
	return archive, manifest
}

func updateTestFiles() map[string][]byte {
	identity, _ := json.Marshal(portableReleaseIdentity{Schema: 1, Revision: strings.Repeat("b", 40), Package: portableUpdatePackage, Version: "latest"})
	return map[string][]byte{
		"startup.exe":                   []byte("verified new launcher"),
		"portable-release.json":         identity,
		"configs/worldserver.conf.dist": []byte("new distributed configuration"),
		"src/data/sql/updates/new.sql":  []byte("SELECT 1;\n"),
		"licenses/empty.txt":            {},
	}
}

func updateTestWrite(t *testing.T, root, name string, content []byte) {
	t.Helper()
	filename := filepath.Join(root, filepath.FromSlash(name))
	if err := os.MkdirAll(filepath.Dir(filename), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filename, content, 0644); err != nil {
		t.Fatal(err)
	}
}

func updateTestRangeServer(t *testing.T, archive []byte) (*httptest.Server, *atomic.Int64, *atomic.Int64) {
	t.Helper()
	return updateTestFaultyRangeServer(t, archive, nil)
}

// fault may answer a numbered request itself, for example with an error
// status or a dropped connection, and then returns true.
func updateTestFaultyRangeServer(t *testing.T, archive []byte, fault func(request int64, w http.ResponseWriter, req *http.Request) bool) (*httptest.Server, *atomic.Int64, *atomic.Int64) {
	t.Helper()
	bytesServed, requests := new(atomic.Int64), new(atomic.Int64)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		if request := requests.Add(1); fault != nil && fault(request, w, req) {
			return
		}
		var start, end int64
		if _, err := fmt.Sscanf(req.Header.Get("Range"), "bytes=%d-%d", &start, &end); err != nil || start < 0 || end < start || end >= int64(len(archive)) {
			http.Error(w, "range required", http.StatusRequestedRangeNotSatisfiable)
			return
		}
		w.Header().Set("Content-Range", fmt.Sprintf("bytes %d-%d/%d", start, end, len(archive)))
		w.Header().Set("Content-Length", strconv.FormatInt(end-start+1, 10))
		w.Header().Set("ETag", `"immutable-test-asset"`)
		w.WriteHeader(http.StatusPartialContent)
		written, _ := w.Write(archive[start : end+1])
		bytesServed.Add(int64(written))
	}))
	t.Cleanup(server.Close)
	return server, bytesServed, requests
}

func TestPortableUpdateDownloadsOnlyChangedFilesAndPreservesUsers(t *testing.T) {
	root := t.TempDir()
	files := updateTestFiles()
	large := make([]byte, 6<<20)
	if _, err := rand.Read(large); err != nil {
		t.Fatal(err)
	}
	files["mysql/lib/unchanged.dll"] = large
	updateTestWrite(t, root, "mysql/lib/unchanged.dll", large)
	updateTestWrite(t, root, "startup.exe", []byte("old launcher"))
	oldIdentity, _ := json.Marshal(portableReleaseIdentity{Schema: 1, Revision: strings.Repeat("a", 40), Package: portableUpdatePackage})
	updateTestWrite(t, root, "portable-release.json", oldIdentity)
	userFiles := map[string][]byte{
		"configs/worldserver.conf":        []byte("custom user config"),
		"mysql/data/characters.ibd":       []byte("characters"),
		"mysql/my.ini":                    []byte("custom database config"),
		"data/dbc/Spell.dbc":              []byte("client data"),
		"logs/world.log":                  []byte("server log"),
		"custom-addon/file.lua":           []byte("user addon"),
		"configs/.portable-profiles.json": []byte("profile baseline"),
		"configs/realm-phase.txt":         []byte("tbc\n"),
	}
	for name, content := range userFiles {
		updateTestWrite(t, root, name, content)
	}
	archive, manifest := updateTestArchive(t, files, "./")
	server, served, _ := updateTestRangeServer(t, archive)
	output := new(updateProgressTestOutput)
	progress := newPortableUpdateProgress(context.Background(), output, false, 5*time.Second)
	t.Cleanup(progress.close)
	plan, err := stagePortableUpdate(context.Background(), root, manifest, []string{"--skip-sql"}, server.Client(), server.URL, progress)
	if err != nil {
		t.Fatal(err)
	}
	if served.Load() >= int64(len(archive))/3 {
		t.Fatalf("downloaded %d bytes for %d-byte ZIP with unchanged large file", served.Load(), len(archive))
	}
	for _, operation := range plan.Operations {
		if operation.File.Path == "mysql/lib/unchanged.dll" {
			t.Fatal("unchanged runtime file was staged")
		}
	}
	if err := applyPortableUpdate(root, plan, progress); err != nil {
		t.Fatal(err)
	}
	progress.close()
	log := output.String()
	for _, phase := range []string{"Comparing installed files", "Downloading, extracting and verifying changed files", "Verifying staged update files", "Installing verified files"} {
		if !strings.Contains(log, "Update: "+phase+": [####################] 100%") {
			t.Fatalf("verified update phase %q never completed:\n%s", phase, log)
		}
	}
	if strings.ContainsAny(log, "\r\x1b") || !strings.Contains(log, "MiB unpacked") {
		t.Fatalf("redirected update output is not readable or correctly labelled:\n%s", log)
	}
	for name, content := range files {
		got, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(name)))
		if err != nil || !bytes.Equal(content, got) {
			t.Fatalf("updated %s: %v", name, err)
		}
	}
	for name, content := range userFiles {
		got, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(name)))
		if err != nil || !bytes.Equal(content, got) {
			t.Fatalf("user file changed %s: %v", name, err)
		}
	}
	installed, err := readInstalledUpdateManifest(root)
	if err != nil || installed.Revision != manifest.Revision {
		t.Fatalf("installed inventory not committed: %v", err)
	}
	if _, err := os.Stat(filepath.Join(root, portableUpdateDirectory, "journal.json")); !errors.Is(err, os.ErrNotExist) {
		t.Fatal("completed transaction journal remains")
	}
}

func TestPortableUpdateCancellationAfterVerifiedStaging(t *testing.T) {
	for _, mode := range []string{"interrupt", "deadline"} {
		t.Run(mode, func(t *testing.T) {
			root := t.TempDir()
			oldIdentity, err := json.Marshal(portableReleaseIdentity{Schema: 1, Revision: strings.Repeat("a", 40), Package: portableUpdatePackage, Version: "latest"})
			if err != nil {
				t.Fatal(err)
			}
			installed := map[string][]byte{
				"startup.exe":               []byte("working installed launcher"),
				"portable-release.json":     oldIdentity,
				"configs/worldserver.conf":  []byte("custom settings"),
				"mysql/data/characters.ibd": []byte("saved characters"),
				"data/dbc/Spell.dbc":        []byte("client data"),
			}
			_, previous := updateTestArchive(t, map[string][]byte{
				"startup.exe": installed["startup.exe"], "portable-release.json": oldIdentity,
			}, "")
			previous.Revision = strings.Repeat("a", 40)
			installed[portableUpdateDirectory+"/installed.json"], err = json.Marshal(previous)
			if err != nil {
				t.Fatal(err)
			}
			for path, content := range installed {
				updateTestWrite(t, root, path, content)
			}
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			archive, manifest := updateTestArchive(t, updateTestFiles(), "")
			server, _, _ := updateTestRangeServer(t, archive)
			plan, err := stagePortableUpdate(ctx, root, manifest, nil, server.Client(), server.URL, nil)
			if err != nil {
				t.Fatal(err)
			}
			journal, err := readPortableUpdatePlan(root)
			if err != nil || journal.Phase != "staged" || plan.Phase != "staged" || ctx.Err() != nil {
				t.Fatalf("update did not finish verified staging before cancellation: plan=%v err=%v", journal, err)
			}
			want := error(context.Canceled)
			if mode == "interrupt" {
				cancel()
			} else {
				var cancelDeadline context.CancelFunc
				ctx, cancelDeadline = context.WithDeadline(ctx, time.Now().Add(-time.Second))
				defer cancelDeadline()
				want = context.DeadlineExceeded
			}
			if err := handoffPortableUpdate(ctx, root, plan); !errors.Is(err, want) {
				t.Fatalf("cancelled staged update was handed to its helper: %v", err)
			}
			for path, original := range installed {
				actual, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(path)))
				if err != nil || !bytes.Equal(actual, original) {
					t.Fatalf("cancellation changed installed/user file %s: %v", path, err)
				}
			}
			for _, child := range []string{"journal.json", "stage", "backup", "owner.json", "helper.exe"} {
				if _, err := os.Stat(filepath.Join(root, portableUpdateDirectory, child)); !errors.Is(err, os.ErrNotExist) {
					t.Fatalf("cancelled completed staging left %s: %v", child, err)
				}
			}
		})
	}
}

func TestPortableUpdateFailedDigestNeverChangesInstalledFiles(t *testing.T) {
	root := t.TempDir()
	old := []byte("old working launcher")
	updateTestWrite(t, root, "startup.exe", old)
	archive, manifest := updateTestArchive(t, updateTestFiles(), "")
	for i := range manifest.Files {
		if manifest.Files[i].Path == "startup.exe" {
			manifest.Files[i].SHA256 = strings.Repeat("0", 64)
		}
	}
	server, _, _ := updateTestRangeServer(t, archive)
	output := new(updateProgressTestOutput)
	progress := newPortableUpdateProgress(context.Background(), output, false, 5*time.Second)
	t.Cleanup(progress.close)
	if _, err := stagePortableUpdate(context.Background(), root, manifest, nil, server.Client(), server.URL, progress); err == nil || !strings.Contains(err.Error(), "verification") {
		t.Fatalf("corrupt download accepted: %v", err)
	}
	progress.close()
	log := output.String()
	transfer := log[strings.Index(log, "Update: Downloading, extracting and verifying changed files"):]
	if strings.Contains(transfer, "100%") || !strings.Contains(transfer, "99%") {
		t.Fatalf("a failed SHA256 verification was shown as complete:\n%s", transfer)
	}
	got, _ := os.ReadFile(filepath.Join(root, "startup.exe"))
	if !bytes.Equal(got, old) {
		t.Fatal("installed launcher changed before verification")
	}
	for _, name := range []string{"journal.json", "stage", "backup", "owner.json"} {
		if _, err := os.Stat(filepath.Join(root, portableUpdateDirectory, name)); !errors.Is(err, os.ErrNotExist) {
			t.Fatalf("failed staging left %s", name)
		}
	}
}

func TestPortableUpdateRejectsFullDownloadAndMalformedRanges(t *testing.T) {
	for _, mode := range []string{"no-range", "wrong-total", "short", "changed-etag", "changed-url"} {
		t.Run(mode, func(t *testing.T) {
			var calls atomic.Int64
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				call := calls.Add(1)
				if mode == "no-range" {
					w.Header().Set("Content-Length", "100000000")
					w.WriteHeader(http.StatusOK)
					return
				}
				var start, end int
				fmt.Sscanf(r.Header.Get("Range"), "bytes=%d-%d", &start, &end)
				total := 20
				if mode == "wrong-total" {
					total++
				}
				w.Header().Set("Content-Range", fmt.Sprintf("bytes %d-%d/%d", start, end, total))
				w.Header().Set("ETag", `"first"`)
				if mode == "changed-etag" && call > 1 {
					w.Header().Set("ETag", `"different"`)
				}
				w.WriteHeader(http.StatusPartialContent)
				if mode != "short" {
					w.Write(bytes.Repeat([]byte{'x'}, end-start+1))
				}
			}))
			defer server.Close()
			reader, err := newUpdateRangeReader(context.Background(), server.Client(), server.URL, 20)
			if mode == "changed-etag" || mode == "changed-url" {
				if err != nil {
					t.Fatal(err)
				}
				if mode == "changed-url" {
					reader.assetURL += "/redirect"
					// An ETag is independent of the rolling URL; final URL must
					// nevertheless remain bound to the resolved asset.
					reader.client.CheckRedirect = func(req *http.Request, via []*http.Request) error { return nil }
					// Direct reader URL mutation is not an external redirect; test
					// the response comparison using a transport below instead.
					reader.client.Transport = updateURLRewriteTransport{base: http.DefaultTransport, original: reader.assetURL}
				}
				_, err = reader.ReadAt(make([]byte, 3), 2)
			}
			if err == nil {
				t.Fatal("invalid ranged response accepted")
			}
		})
	}
}

type updateURLRewriteTransport struct {
	base     http.RoundTripper
	original string
}

func (r updateURLRewriteTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	response, err := r.base.RoundTrip(req)
	if response != nil {
		copyRequest := req.Clone(req.Context())
		copyURL := *req.URL
		copyURL.Path += "/changed"
		copyRequest.URL = &copyURL
		response.Request = copyRequest
	}
	return response, err
}

func TestPortableUpdateManifestRejectsUnsafeFiles(t *testing.T) {
	_, base := updateTestArchive(t, updateTestFiles(), "")
	for _, name := range []string{"../outside", "/outside", "C:/outside", "configs/worldserver.conf", "mysql/my.ini", "my.cnf", "configs/my.ini", "mysql/data/db.ibd", "data/maps/file", "logs/file", "configs/.portable-profiles.json", "configs/realm-phase.txt", ".portable-update/helper.exe", "dir\\file", "dir./file", "NUL.txt", "folder/file ", "file:stream", "file?.dll", "file*.dll", "file\".dll", "file<.dll", "file>.dll", "file|.dll", "file\n.dll"} {
		t.Run(name, func(t *testing.T) {
			m := base
			m.Files = append(append([]portableUpdateFile{}, base.Files...), portableUpdateFile{Path: name, Size: 0, SHA256: updateTestDigest(nil)})
			if err := validateUpdateManifest(m); err == nil {
				t.Fatal("unsafe path accepted")
			}
		})
	}
	for _, mutation := range []func(*portableUpdateManifest){
		func(m *portableUpdateManifest) { m.Revision = "latest" },
		func(m *portableUpdateManifest) { m.Size = maxUpdatePackageBytes + 1 },
		func(m *portableUpdateManifest) { m.Files = append(m.Files, m.Files[0]) },
		func(m *portableUpdateManifest) {
			f := m.Files[0]
			f.Path = strings.ToUpper(f.Path)
			m.Files = append(m.Files, f)
		},
		func(m *portableUpdateManifest) {
			m.Files = append(m.Files, portableUpdateFile{Path: "configs", SHA256: updateTestDigest(nil)})
		},
	} {
		m := base
		m.Files = append([]portableUpdateFile{}, base.Files...)
		mutation(&m)
		if err := validateUpdateManifest(m); err == nil {
			t.Fatal("invalid manifest accepted")
		}
	}
}

func TestPortableUpdateRejectsLinksAndWrongArchiveInventory(t *testing.T) {
	if runtime.GOOS != "windows" {
		root, outside := t.TempDir(), t.TempDir()
		if err := os.Symlink(outside, filepath.Join(root, "configs")); err != nil {
			t.Fatal(err)
		}
		if _, err := safeUpdateTarget(root, "configs/worldserver.conf.dist"); err == nil {
			t.Fatal("directory symlink accepted")
		}
	}
	files := updateTestFiles()
	archive, manifest := updateTestArchive(t, files, "")
	files["extra-user-file"] = []byte("unlisted")
	extra, _ := updateTestArchive(t, files, "")
	manifest.Size = int64(len(extra))
	if _, err := indexedUpdateZip(bytes.NewReader(extra), manifest); err == nil {
		t.Fatal("extra ZIP file accepted")
	}
	manifest.Size = int64(len(archive))
	manifest.Files[0].Size++
	if _, err := indexedUpdateZip(bytes.NewReader(archive), manifest); err == nil {
		t.Fatal("wrong ZIP size accepted")
	}
	var buffer bytes.Buffer
	writer := zip.NewWriter(&buffer)
	for name, content := range updateTestFiles() {
		header := &zip.FileHeader{Name: name}
		if name == "startup.exe" {
			header.SetMode(os.ModeSymlink | 0777)
		} else {
			header.SetMode(0644)
		}
		entry, _ := writer.CreateHeader(header)
		entry.Write(content)
	}
	writer.Close()
	_, manifest = updateTestArchive(t, updateTestFiles(), "")
	manifest.Size = int64(buffer.Len())
	if _, err := indexedUpdateZip(bytes.NewReader(buffer.Bytes()), manifest); err == nil {
		t.Fatal("ZIP symlink accepted")
	}
}

func TestPortableUpdateInterruptedCommitRestoresCompletePreviousVersion(t *testing.T) {
	for _, crash := range []string{"original-moved", "new-installed", "marked-applied", "new-file-installed"} {
		t.Run(crash, func(t *testing.T) {
			root := t.TempDir()
			old := []byte("old working launcher")
			if crash != "new-file-installed" {
				updateTestWrite(t, root, "startup.exe", old)
			}
			archive, manifest := updateTestArchive(t, updateTestFiles(), "")
			server, _, _ := updateTestRangeServer(t, archive)
			plan, err := stagePortableUpdate(context.Background(), root, manifest, nil, server.Client(), server.URL, nil)
			if err != nil {
				t.Fatal(err)
			}
			plan.ParentPID = 2147483647
			plan.Phase = "applying"
			for i := range plan.Operations {
				op := &plan.Operations[i]
				if op.File.Path != "startup.exe" {
					continue
				}
				op.State = "applying"
				if op.HadOriginal {
					if err := os.Rename(filepath.Join(root, op.File.Path), filepath.Join(root, portableUpdateDirectory, op.Backup)); err != nil {
						t.Fatal(err)
					}
				}
				if crash != "original-moved" {
					if err := os.Rename(filepath.Join(root, portableUpdateDirectory, op.Stage), filepath.Join(root, op.File.Path)); err != nil {
						t.Fatal(err)
					}
				}
				if crash == "marked-applied" {
					op.State = "applied"
				}
			}
			if err := writePortableUpdatePlan(root, plan); err != nil {
				t.Fatal(err)
			}
			if err := recoverPortableUpdate(root); err != nil {
				t.Fatal(err)
			}
			got, err := os.ReadFile(filepath.Join(root, "startup.exe"))
			if crash == "new-file-installed" {
				if !errors.Is(err, os.ErrNotExist) {
					t.Fatal("new file was not removed")
				}
			} else if err != nil || !bytes.Equal(got, old) {
				t.Fatalf("previous launcher not restored: %v", err)
			}
			if err := recoverPortableUpdate(root); err != nil {
				t.Fatalf("repeat recovery is not safe: %v", err)
			}
		})
	}
}

// Recovery runs from the installed startup.exe. After a crash late in an
// update, that is the new launcher, which Windows cannot delete while it runs.
func TestPortableUpdateRecoveryRestoresTheRunningLauncher(t *testing.T) {
	root := t.TempDir()
	old := []byte("old working launcher")
	updateTestWrite(t, root, "startup.exe", old)
	launcher, err := os.ReadFile(os.Args[0])
	if err != nil {
		t.Fatal(err)
	}
	files := updateTestFiles()
	files["startup.exe"] = launcher
	archive, manifest := updateTestArchive(t, files, "")
	server, _, _ := updateTestRangeServer(t, archive)
	plan, err := stagePortableUpdate(context.Background(), root, manifest, nil, server.Client(), server.URL, nil)
	if err != nil {
		t.Fatal(err)
	}
	plan.Phase, plan.ParentPID = "applying", 2147483647
	for i := range plan.Operations {
		op := &plan.Operations[i]
		if op.File.Path != "startup.exe" {
			continue
		}
		op.State = "applying"
		if err := os.Rename(filepath.Join(root, op.File.Path), filepath.Join(root, portableUpdateDirectory, op.Backup)); err != nil {
			t.Fatal(err)
		}
		if err := os.Rename(filepath.Join(root, portableUpdateDirectory, op.Stage), filepath.Join(root, op.File.Path)); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.Chmod(filepath.Join(root, "startup.exe"), 0755); err != nil {
		t.Fatal(err)
	}
	if err := writePortableUpdatePlan(root, plan); err != nil {
		t.Fatal(err)
	}
	recovery := exec.Command(filepath.Join(root, "startup.exe"), "-test.run=^TestPortableUpdateRecoveryChild$")
	recovery.Env = append(os.Environ(), "PORTABLE_UPDATE_RECOVERY_ROOT="+root)
	if output, err := recovery.CombinedOutput(); err != nil {
		t.Fatalf("installed new launcher could not restore the previous version: %v\n%s", err, output)
	}
	if got, err := os.ReadFile(filepath.Join(root, "startup.exe")); err != nil || !bytes.Equal(got, old) {
		t.Fatalf("previous launcher not restored: %v", err)
	}
	if _, err := os.Stat(filepath.Join(root, portableUpdateDirectory, "journal.json")); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("recovered update kept its journal: %v", err)
	}
	cached := filepath.Join(root, filepath.FromSlash(portableUpdateCacheDirectory), updateTestDigest(launcher))
	if digest, err := hashUpdateFile(cached, int64(len(launcher))); err != nil || digest != updateTestDigest(launcher) {
		t.Fatalf("rolled-back verified launcher was not kept for the next attempt: %v", err)
	}
}

func TestPortableUpdateRecoveryChild(t *testing.T) {
	if root := os.Getenv("PORTABLE_UPDATE_RECOVERY_ROOT"); root != "" {
		if err := recoverPortableUpdate(root); err != nil {
			t.Fatal(err)
		}
	}
}

func TestPortableUpdateFailureAfterInstalledFilesRestoresPreviousVersion(t *testing.T) {
	root := t.TempDir()
	oldIdentity, err := json.Marshal(portableReleaseIdentity{Schema: 1, Revision: strings.Repeat("a", 40), Package: portableUpdatePackage, Version: "latest"})
	if err != nil {
		t.Fatal(err)
	}
	installed := map[string][]byte{
		"startup.exe":                   []byte("old working launcher"),
		"portable-release.json":         oldIdentity,
		"configs/worldserver.conf.dist": []byte("old distributed configuration"),
		"configs/worldserver.conf":      []byte("custom settings"),
		"mysql/data/characters.ibd":     []byte("saved characters"),
	}
	for name, content := range installed {
		updateTestWrite(t, root, name, content)
	}
	archive, manifest := updateTestArchive(t, updateTestFiles(), "")
	server, _, _ := updateTestRangeServer(t, archive)
	plan, err := stagePortableUpdate(context.Background(), root, manifest, nil, server.Client(), server.URL, nil)
	if err != nil {
		t.Fatal(err)
	}
	// Operations follow manifest order. A directory that appears where the new
	// SQL file belongs fails it after earlier files were already replaced.
	updateTestWrite(t, root, "src/data/sql/updates/new.sql/user.txt", []byte("user file"))
	if err := applyPortableUpdate(root, plan, nil); err == nil || !strings.Contains(err.Error(), "restored to the previous version") {
		t.Fatalf("partial installation was not reported as restored: %v", err)
	}
	for name, content := range installed {
		if got, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(name))); err != nil || !bytes.Equal(got, content) {
			t.Fatalf("rollback did not restore %s: %v", name, err)
		}
	}
	if _, err := os.Stat(filepath.Join(root, "licenses", "empty.txt")); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("new file from the failed update remains: %v", err)
	}
	journal, err := readPortableUpdatePlan(root)
	if err != nil || journal.Phase != "rolled-back" {
		t.Fatalf("rollback was not recorded: %v", err)
	}
	restored := 0
	for _, op := range journal.Operations {
		if op.State == "rolled-back" {
			restored++
		}
	}
	if restored < 2 {
		t.Fatalf("failure did not occur after earlier files were installed: %d restored", restored)
	}
	if err := recoverPortableUpdate(root); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(root, portableUpdateDirectory, "journal.json")); !errors.Is(err, os.ErrNotExist) {
		t.Fatal("recovery kept the rolled-back journal")
	}
	if content, err := os.ReadFile(filepath.Join(root, "src/data/sql/updates/new.sql/user.txt")); err != nil || string(content) != "user file" {
		t.Fatal("recovery changed an unrelated user file")
	}
}

func TestPortableUpdateRemovesOnlyRecordedUnmodifiedObsoleteFiles(t *testing.T) {
	root := t.TempDir()
	previousFiles := updateTestFiles()
	previousFiles["obsolete.dll"] = []byte("old known runtime")
	previousFiles["user-edited.dll"] = []byte("original runtime")
	_, previous := updateTestArchive(t, previousFiles, "")
	if err := os.MkdirAll(filepath.Join(root, portableUpdateDirectory), 0700); err != nil {
		t.Fatal(err)
	}
	if err := writeUpdateJSON(filepath.Join(root, portableUpdateDirectory, "installed.json"), previous); err != nil {
		t.Fatal(err)
	}
	updateTestWrite(t, root, "obsolete.dll", previousFiles["obsolete.dll"])
	updateTestWrite(t, root, "user-edited.dll", []byte("user modified this"))
	updateTestWrite(t, root, "unknown.dll", []byte("unknown user file"))
	archive, manifest := updateTestArchive(t, updateTestFiles(), "")
	server, _, _ := updateTestRangeServer(t, archive)
	plan, err := stagePortableUpdate(context.Background(), root, manifest, nil, server.Client(), server.URL, nil)
	if err != nil {
		t.Fatal(err)
	}
	// Apply verifies a removal against its original digest, so the journal
	// must record the obsolete package file itself as that original.
	for i, op := range plan.Operations {
		if !op.Remove {
			continue
		}
		tampered := *plan
		tampered.Operations = append([]portableUpdateOperation{}, plan.Operations...)
		tampered.Operations[i].OriginalSHA256 = updateTestDigest([]byte("user modified this"))
		if err := writePortableUpdatePlan(root, &tampered); err != nil {
			t.Fatal(err)
		}
		if _, err := readPortableUpdatePlan(root); err == nil {
			t.Fatal("removal of a file other than the recorded package file accepted")
		}
	}
	if err := writePortableUpdatePlan(root, plan); err != nil {
		t.Fatal(err)
	}
	if err := applyPortableUpdate(root, plan, nil); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(root, "obsolete.dll")); !errors.Is(err, os.ErrNotExist) {
		t.Fatal("known obsolete file remains")
	}
	for _, name := range []string{"unknown.dll", "user-edited.dll"} {
		if _, err := os.Stat(filepath.Join(root, name)); err != nil {
			t.Fatalf("user file %s removed: %v", name, err)
		}
	}
}

func TestPortableUpdateOfflineAndCancelledRequestsLeaveInstalledVersion(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		<-r.Context().Done()
	}))
	defer server.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer cancel()
	if _, err := fetchUpdateManifest(ctx, server.Client(), server.URL, time.Second); err == nil {
		t.Fatal("cancelled request accepted")
	}
	server.Close()
	if _, err := fetchUpdateManifest(context.Background(), &http.Client{Timeout: time.Second}, server.URL, time.Second); err == nil {
		t.Fatal("offline request accepted")
	}
}

func TestPortableUpdateTrustedURLsAndHelperDispatch(t *testing.T) {
	for _, text := range []string{"https://github.com/a/b", "https://release-assets.githubusercontent.com/asset", "https://objects.githubusercontent.com/asset"} {
		u, _ := url.Parse(text)
		if !trustedUpdateURL(u) {
			t.Fatalf("trusted URL rejected: %s", text)
		}
	}
	for _, text := range []string{"http://github.com/a", "https://github.com.evil.example/a", "https://user@github.com/a", "https://github.com:444/a", "https://evil.example/a"} {
		u, _ := url.Parse(text)
		if trustedUpdateURL(u) {
			t.Fatalf("untrusted URL accepted: %s", text)
		}
	}
	if handled, err := runPortableUpdateHelper([]string{"--skip-sql"}); handled || err != nil {
		t.Fatal("normal flags dispatched as updater")
	}
	if handled, err := runPortableUpdateHelper([]string{portableUpdateHelperFlag}); !handled || err == nil {
		t.Fatal("malformed helper invocation accepted")
	}
	if _, err := parseUpdateParentPID("0"); err == nil {
		t.Fatal("invalid parent accepted")
	}
	if portableUpdateProcessPath("/portable", "/other/worldserver.exe") {
		t.Fatal("other installation process is treated as ours")
	}
}

// updateTestStartIdleProcess runs a copy of the test binary from executable,
// so a test can record a live process whose program has that location.
func updateTestStartIdleProcess(t *testing.T, executable string) *exec.Cmd {
	t.Helper()
	if executable != os.Args[0] {
		content, err := os.ReadFile(os.Args[0])
		if err != nil {
			t.Fatal(err)
		}
		if err := os.MkdirAll(filepath.Dir(executable), 0755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(executable, content, 0755); err != nil {
			t.Fatal(err)
		}
	}
	cmd := exec.Command(executable, "-test.run=^TestPortableUpdateOwnerChild$")
	cmd.Env = append(os.Environ(), "PORTABLE_UPDATE_OWNER_CHILD=1")
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { cmd.Process.Kill(); cmd.Wait() })
	return cmd
}

func TestPortableUpdateActiveOwnerPreventsConcurrentCleanup(t *testing.T) {
	root := t.TempDir()
	updateTestWrite(t, root, portableUpdateDirectory+"/stage/pending", []byte("pending verified download"))
	cmd := updateTestStartIdleProcess(t, filepath.Join(root, "startup.exe"))
	if err := writeUpdateJSON(filepath.Join(root, portableUpdateDirectory, "owner.json"), portableUpdateOwner{PID: cmd.Process.Pid}); err != nil {
		t.Fatal(err)
	}
	if err := recoverPortableUpdate(root); err == nil {
		t.Fatal("active owner's staging was accepted for cleanup")
	}
	if _, err := os.Stat(filepath.Join(root, portableUpdateDirectory, "stage", "pending")); err != nil {
		t.Fatal("active owner's staging was removed")
	}
}

func TestPortableUpdateOwnerChild(t *testing.T) {
	if os.Getenv("PORTABLE_UPDATE_OWNER_CHILD") == "1" {
		time.Sleep(20 * time.Second)
	}
}

// Ensure the HTTP reader obeys the ReaderAt contract at EOF and does not turn
// an empty reader request into an invalid negative range.
func TestPortableUpdateRangeReaderBounds(t *testing.T) {
	server, _, _ := updateTestRangeServer(t, []byte("abcdef"))
	reader, err := newUpdateRangeReader(context.Background(), server.Client(), server.URL, 6)
	if err != nil {
		t.Fatal(err)
	}
	buffer := make([]byte, 4)
	if n, err := reader.ReadAt(buffer, 4); n != 2 || !errors.Is(err, io.EOF) || string(buffer[:n]) != "ef" {
		t.Fatalf("incorrect EOF result: n=%d,err=%v", n, err)
	}
	if n, err := reader.ReadAt(nil, 1); n != 0 || err != nil {
		t.Fatalf("empty read: n=%d,err=%v", n, err)
	}
}

// updateTestBuildLauncher builds the current launcher, which runs the update
// helper when the installed test launcher hands an update to it.
func updateTestBuildLauncher(t *testing.T) []byte {
	t.Helper()
	if testing.Short() {
		t.Skip("builds an actual launcher for helper integration")
	}
	newLauncher := filepath.Join(t.TempDir(), "new-startup.exe")
	build := exec.Command("go", "build", "-o", newLauncher, ".")
	if output, err := build.CombinedOutput(); err != nil {
		t.Fatalf("build launcher: %v\n%s", err, output)
	}
	launcherBytes, err := os.ReadFile(newLauncher)
	if err != nil {
		t.Fatal(err)
	}
	return launcherBytes
}

// updateTestInstallTestLauncher installs this test binary as the old launcher.
// It runs TestPortableUpdateHelperParentChild as the parent of the handoff.
func updateTestInstallTestLauncher(t *testing.T, root string) []byte {
	t.Helper()
	oldLauncher, err := os.ReadFile(os.Args[0])
	if err != nil {
		t.Fatal(err)
	}
	updateTestWrite(t, root, "startup.exe", oldLauncher)
	if err := os.Chmod(filepath.Join(root, "startup.exe"), 0755); err != nil {
		t.Fatal(err)
	}
	return oldLauncher
}

// updateTestHandOffFromParent runs the installed test launcher as the parent
// that hands the staged update to its helper, and returns the log that the
// parent, the helper and the restarted launcher share.
func updateTestHandOffFromParent(t *testing.T, root string) string {
	t.Helper()
	logPath := filepath.Join(root, "helper-test.log")
	logfile, err := os.Create(logPath)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { logfile.Close() })
	parent := exec.Command(filepath.Join(root, "startup.exe"), "-test.run=^TestPortableUpdateHelperParentChild$")
	parent.Env = append(os.Environ(), "PORTABLE_UPDATE_PARENT_CHILD=1", "PORTABLE_UPDATE_TEST_ROOT="+root)
	parent.Stdout, parent.Stderr = logfile, logfile
	if err := parent.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		parent.Process.Kill()
		if pending, err := readPortableUpdatePlan(root); err == nil && pending.HelperPID > 0 {
			if process, err := os.FindProcess(pending.HelperPID); err == nil {
				process.Kill()
			}
		}
	})
	if err := parent.Wait(); err != nil {
		content, _ := os.ReadFile(logPath)
		t.Fatalf("helper parent failed: %v\n%s", err, content)
	}
	return logPath
}

func TestPortableUpdateSelfReplacementWaitsForParentAndRestarts(t *testing.T) {
	launcherBytes := updateTestBuildLauncher(t)
	root := t.TempDir()
	updateTestInstallTestLauncher(t, root)
	files := updateTestFiles()
	files["startup.exe"] = launcherBytes
	archive, manifest := updateTestArchive(t, files, "")
	server, _, _ := updateTestRangeServer(t, archive)
	plan, err := stagePortableUpdate(context.Background(), root, manifest, []string{"--help"}, server.Client(), server.URL, nil)
	if err != nil {
		t.Fatal(err)
	}
	updateTestHandOffFromParent(t, root)
	deadline := time.Now().Add(15 * time.Second)
	restartEvidence := []byte("no-update")
	if runtime.GOOS != "windows" {
		restartEvidence = []byte("only supported on Windows")
	}
	for time.Now().Before(deadline) {
		digest, hashErr := hashUpdateFile(filepath.Join(root, "startup.exe"), int64(len(launcherBytes)))
		content, _ := os.ReadFile(filepath.Join(root, "helper-test.log"))
		if hashErr == nil && digest == updateTestDigest(launcherBytes) && bytes.Contains(content, []byte("Restarting the launcher")) && bytes.Contains(content, restartEvidence) {
			for _, phase := range []string{"Verifying staged update files", "Installing verified files"} {
				if !bytes.Contains(content, []byte("Update: "+phase+": [####################] 100%")) {
					t.Fatalf("actual updater helper omitted completed %s progress:\n%s", phase, content)
				}
			}
			if bytes.ContainsAny(content, "\r\x1b") {
				t.Fatalf("updater helper used console controls in redirected output:\n%s", content)
			}
			if _, err := os.Stat(filepath.Join(root, "parent-was-running")); err != nil {
				t.Fatal("parent handshake marker missing")
			}
			if identity, err := readPortableIdentity(root); err != nil || identity.Revision != plan.Manifest.Revision {
				t.Fatalf("wrong release identity after replacement: %v", err)
			}
			return
		}
		time.Sleep(50 * time.Millisecond)
	}
	content, _ := os.ReadFile(filepath.Join(root, "helper-test.log"))
	t.Fatalf("helper did not replace and restart launcher:\n%s", content)
}

func TestPortableUpdateHelperParentChild(t *testing.T) {
	if os.Getenv("PORTABLE_UPDATE_PARENT_CHILD") != "1" {
		return
	}
	root := os.Getenv("PORTABLE_UPDATE_TEST_ROOT")
	plan, err := readPortableUpdatePlan(root)
	if err != nil {
		t.Fatal(err)
	}
	plan.ParentPID = os.Getpid()
	if err := writePortableUpdatePlan(root, plan); err != nil {
		t.Fatal(err)
	}
	before, err := os.ReadFile(filepath.Join(root, "startup.exe"))
	if err != nil {
		t.Fatal(err)
	}
	if err := handoffPortableUpdate(context.Background(), root, plan); err != nil {
		t.Fatal(err)
	}
	time.Sleep(150 * time.Millisecond)
	after, err := os.ReadFile(filepath.Join(root, "startup.exe"))
	if err != nil || !bytes.Equal(before, after) {
		t.Fatal("updater replaced a launcher whose parent is still running")
	}
	updateTestWrite(t, root, "parent-was-running", []byte("helper acknowledged; old launcher still intact"))
}

func TestPortableUpdateFailedHelperRestartsInstalledRelease(t *testing.T) {
	launcherBytes := updateTestBuildLauncher(t)
	root := t.TempDir()
	oldLauncher := updateTestInstallTestLauncher(t, root)
	files := updateTestFiles()
	files["startup.exe"] = launcherBytes
	archive, manifest := updateTestArchive(t, files, "")
	server, _, _ := updateTestRangeServer(t, archive)
	if _, err := stagePortableUpdate(context.Background(), root, manifest, nil, server.Client(), server.URL, nil); err != nil {
		t.Fatal(err)
	}
	// A folder where a new SQL file belongs fails the helper after it
	// installed earlier files, so it has to roll them back.
	updateTestWrite(t, root, "src/data/sql/updates/new.sql/user.txt", []byte("user file"))
	logPath := updateTestHandOffFromParent(t, root)
	// The restarted launcher is this test binary, whose own flag parser
	// reports the added --no-update flag.
	deadline := time.Now().Add(15 * time.Second)
	var content []byte
	for time.Now().Before(deadline) {
		content, _ = os.ReadFile(logPath)
		if bytes.Contains(content, []byte("flag provided but not defined: -no-update")) {
			break
		}
		time.Sleep(50 * time.Millisecond)
	}
	for _, evidence := range []string{"Error completing update: update was restored to the previous version", "Starting the installed release without the update check.", "flag provided but not defined: -no-update"} {
		if !bytes.Contains(content, []byte(evidence)) {
			t.Fatalf("failed update did not restart the installed release (%q missing):\n%s", evidence, content)
		}
	}
	if got, err := os.ReadFile(filepath.Join(root, "startup.exe")); err != nil || !bytes.Equal(got, oldLauncher) {
		t.Fatalf("installed launcher was not restored: %v", err)
	}
	if _, err := os.Stat(filepath.Join(root, portableUpdateDirectory, "journal.json")); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("restarted release would find the failed update journal: %v", err)
	}
	cached := filepath.Join(root, filepath.FromSlash(portableUpdateCacheDirectory), updateTestDigest(launcherBytes))
	if digest, err := hashUpdateFile(cached, int64(len(launcherBytes))); err != nil || digest != updateTestDigest(launcherBytes) {
		t.Fatalf("verified download of the uninstalled launcher was not kept: %v", err)
	}
	// Windows keeps the running helper's file; let it exit before cleanup.
	helper := filepath.Join(root, portableUpdateDirectory, "helper.exe")
	for deadline := time.Now().Add(10 * time.Second); time.Now().Before(deadline); time.Sleep(50 * time.Millisecond) {
		if err := os.Remove(helper); err == nil || errors.Is(err, os.ErrNotExist) {
			break
		}
	}
}

func TestPortableUpdateFailedHelperKeepsUnrestoredInstallation(t *testing.T) {
	if got := withoutUpdateCheck([]string{"--skip-sql"}); strings.Join(got, " ") != "--no-update --skip-sql" {
		t.Fatalf("restart arguments: %q", got)
	}
	for _, args := range [][]string{{"--no-update"}, {"-no-update", "--skip-sql"}} {
		if got := withoutUpdateCheck(args); strings.Join(got, " ") != strings.Join(args, " ") {
			t.Fatalf("--no-update was added twice: %q", got)
		}
	}
	root := t.TempDir()
	updateTestWrite(t, root, "startup.exe", []byte("original launcher"))
	archive, manifest := updateTestArchive(t, updateTestFiles(), "")
	server, _, _ := updateTestRangeServer(t, archive)
	plan, err := stagePortableUpdate(context.Background(), root, manifest, nil, server.Client(), server.URL, nil)
	if err != nil {
		t.Fatal(err)
	}
	// A rollback that failed leaves the journal applying; the helper must
	// not start servers on mixed files or discard what recovery needs.
	plan.Phase = "applying"
	if err := writePortableUpdatePlan(root, plan); err != nil {
		t.Fatal(err)
	}
	if discardIntactUpdate(root) {
		t.Fatal("partially installed update was treated as intact")
	}
	if _, err := os.Stat(filepath.Join(root, portableUpdateDirectory, "journal.json")); err != nil {
		t.Fatalf("recovery journal was removed: %v", err)
	}
	plan.Phase = "staged"
	if err := writePortableUpdatePlan(root, plan); err != nil {
		t.Fatal(err)
	}
	if !discardIntactUpdate(root) {
		t.Fatal("update that never changed installed files was not cleared")
	}
	if content, err := os.ReadFile(filepath.Join(root, "startup.exe")); err != nil || string(content) != "original launcher" {
		t.Fatalf("installed launcher changed: %v", err)
	}
}

func TestPortableUpdateRecoveryStopsWhenOriginalAndBackupAreMissing(t *testing.T) {
	root := t.TempDir()
	updateTestWrite(t, root, "startup.exe", []byte("original"))
	archive, manifest := updateTestArchive(t, updateTestFiles(), "")
	server, _, _ := updateTestRangeServer(t, archive)
	plan, err := stagePortableUpdate(context.Background(), root, manifest, nil, server.Client(), server.URL, nil)
	if err != nil {
		t.Fatal(err)
	}
	plan.ParentPID = 2147483647
	plan.Phase = "applying"
	for i := range plan.Operations {
		if plan.Operations[i].File.Path == "startup.exe" {
			plan.Operations[i].State = "applying"
		}
	}
	if err := os.Remove(filepath.Join(root, "startup.exe")); err != nil {
		t.Fatal(err)
	}
	if err := writePortableUpdatePlan(root, plan); err != nil {
		t.Fatal(err)
	}
	if err := recoverPortableUpdate(root); err == nil || !strings.Contains(err.Error(), "both missing") {
		t.Fatalf("incomplete installation allowed to start: %v", err)
	}
	if _, err := os.Stat(filepath.Join(root, portableUpdateDirectory, "journal.json")); err != nil {
		t.Fatal("failed recovery discarded diagnostic journal")
	}
}

func TestPortableUpdateMissingBackupDoesNotAcceptInstalledNewFile(t *testing.T) {
	root := t.TempDir()
	updateTestWrite(t, root, "startup.exe", []byte("original working launcher"))
	files := updateTestFiles()
	archive, manifest := updateTestArchive(t, files, "")
	server, _, _ := updateTestRangeServer(t, archive)
	plan, err := stagePortableUpdate(context.Background(), root, manifest, nil, server.Client(), server.URL, nil)
	if err != nil {
		t.Fatal(err)
	}
	plan.ParentPID = 2147483647
	plan.Phase = "applying"
	for i := range plan.Operations {
		if plan.Operations[i].File.Path == "startup.exe" {
			plan.Operations[i].State = "applied"
		}
	}
	updateTestWrite(t, root, "startup.exe", files["startup.exe"])
	if err := writePortableUpdatePlan(root, plan); err != nil {
		t.Fatal(err)
	}
	if err := recoverPortableUpdate(root); err == nil || !strings.Contains(err.Error(), "not the original") {
		t.Fatalf("mixed installation accepted without a rollback backup: %v", err)
	}
}

func TestPortableUpdateCommittedJournalWithActiveHelperRefusesCleanup(t *testing.T) {
	root := t.TempDir()
	archive, manifest := updateTestArchive(t, updateTestFiles(), "")
	server, _, _ := updateTestRangeServer(t, archive)
	plan, err := stagePortableUpdate(context.Background(), root, manifest, nil, server.Client(), server.URL, nil)
	if err != nil {
		t.Fatal(err)
	}
	cmd := updateTestStartIdleProcess(t, filepath.Join(root, portableUpdateDirectory, "helper.exe"))
	plan.ParentPID = 2147483647
	plan.HelperPID = cmd.Process.Pid
	plan.Phase = "committed"
	if err := writePortableUpdatePlan(root, plan); err != nil {
		t.Fatal(err)
	}
	if err := recoverPortableUpdate(root); err == nil || !strings.Contains(err.Error(), "another launcher") {
		t.Fatalf("live helper's commit finalized concurrently: %v", err)
	}
	if _, err := os.Stat(filepath.Join(root, portableUpdateDirectory, "journal.json")); err != nil {
		t.Fatal("live helper's committed journal was removed")
	}
}

func TestPortableUpdateModifiedRuntimeDuringStagingIsPreserved(t *testing.T) {
	root := t.TempDir()
	updateTestWrite(t, root, "startup.exe", []byte("original working launcher"))
	archive, manifest := updateTestArchive(t, updateTestFiles(), "")
	server, _, _ := updateTestRangeServer(t, archive)
	plan, err := stagePortableUpdate(context.Background(), root, manifest, nil, server.Client(), server.URL, nil)
	if err != nil {
		t.Fatal(err)
	}
	changed := []byte("user edited original runtime while update was downloading")
	updateTestWrite(t, root, "startup.exe", changed)
	if err := applyPortableUpdate(root, plan, nil); err == nil || !strings.Contains(err.Error(), "changed during") {
		t.Fatalf("changed runtime overwritten: %v", err)
	}
	if content, _ := os.ReadFile(filepath.Join(root, "startup.exe")); !bytes.Equal(content, changed) {
		t.Fatal("runtime change during staging was lost")
	}
}

func TestPortableUpdateFreshBaselineEnablesFutureObsoleteSQLCleanup(t *testing.T) {
	root := t.TempDir()
	previousFiles := updateTestFiles()
	previousFiles["src/data/sql/updates/retired.sql"] = []byte("retired stock migration")
	previousFiles["src/data/sql/updates/modified.sql"] = []byte("original stock migration")
	_, previous := updateTestArchive(t, previousFiles, "")
	for name, content := range previousFiles {
		updateTestWrite(t, root, name, content)
	}
	if err := rememberPortableUpdateBaseline(root, previous); err != nil {
		t.Fatal(err)
	}
	baseline, err := readInstalledUpdateManifest(root)
	if err != nil || len(baseline.Files) != len(previous.Files) {
		t.Fatalf("fresh installed inventory missing: %v", err)
	}
	updateTestWrite(t, root, "src/data/sql/updates/modified.sql", []byte("custom SQL change"))
	nextRevision := strings.Repeat("c", 40)
	files := updateTestFiles()
	identity, _ := json.Marshal(portableReleaseIdentity{Schema: 1, Revision: nextRevision, Package: portableUpdatePackage, Version: "latest"})
	files["portable-release.json"] = identity
	archive, next := updateTestArchive(t, files, "")
	next.Revision = nextRevision
	// A manual overlay must retain the older owned inventory for its first
	// subsequent automatic update rather than forgetting removed SQL paths.
	if err := rememberPortableUpdateBaseline(root, next); err != nil {
		t.Fatal(err)
	}
	if kept, err := readInstalledUpdateManifest(root); err != nil || kept.Revision != previous.Revision {
		t.Fatal("manual-overlay check discarded previous owned paths")
	}
	server, _, _ := updateTestRangeServer(t, archive)
	plan, err := stagePortableUpdate(context.Background(), root, next, nil, server.Client(), server.URL, nil)
	if err != nil {
		t.Fatal(err)
	}
	if err := applyPortableUpdate(root, plan, nil); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(root, "src/data/sql/updates/retired.sql")); !errors.Is(err, os.ErrNotExist) {
		t.Fatal("obsolete stock SQL was not removed")
	}
	if content, err := os.ReadFile(filepath.Join(root, "src/data/sql/updates/modified.sql")); err != nil || string(content) != "custom SQL change" {
		t.Fatal("modified user SQL was removed")
	}
}

func TestPortableUpdateFileRetryOnlyWaitsForTransientErrors(t *testing.T) {
	transient := errors.New("file is briefly in use")
	isTransient := func(err error) bool { return errors.Is(err, transient) }
	calls := 0
	err := retryTransientUpdateError(func() error {
		calls++
		if calls < 3 {
			return transient
		}
		return nil
	}, isTransient, time.Second)
	if err != nil || calls != 3 {
		t.Fatalf("transient failure was not retried: calls=%d err=%v", calls, err)
	}
	calls = 0
	permanent := errors.New("access permanently refused")
	if err := retryTransientUpdateError(func() error { calls++; return permanent }, isTransient, time.Second); !errors.Is(err, permanent) || calls != 1 {
		t.Fatalf("permanent failure was retried: calls=%d err=%v", calls, err)
	}
	started := time.Now()
	if err := retryTransientUpdateError(func() error { return transient }, isTransient, 100*time.Millisecond); !errors.Is(err, transient) {
		t.Fatalf("exhausted retry hid its error: %v", err)
	}
	if elapsed := time.Since(started); elapsed > time.Second {
		t.Fatalf("retry exceeded its budget: %v", elapsed)
	}
}

func TestPortableUpdateManifestResponseDeadlineAllowsSlowTransfer(t *testing.T) {
	_, manifest := updateTestArchive(t, updateTestFiles(), "")
	content, err := json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/silent" {
			select {
			case <-r.Context().Done():
			case <-time.After(5 * time.Second):
			}
			return
		}
		w.WriteHeader(http.StatusOK)
		w.Write(content[:len(content)/2])
		w.(http.Flusher).Flush()
		time.Sleep(300 * time.Millisecond)
		w.Write(content[len(content)/2:])
	}))
	defer server.Close()
	// The response deadline covers only the wait for a reply. A slow link may
	// use the rest of the check time to transfer a large manifest.
	got, err := fetchUpdateManifest(context.Background(), server.Client(), server.URL+"/slow", 100*time.Millisecond)
	if err != nil || got.Revision != manifest.Revision {
		t.Fatalf("slow manifest transfer was cut off by the response deadline: %v", err)
	}
	started := time.Now()
	if _, err := fetchUpdateManifest(context.Background(), server.Client(), server.URL+"/silent", 100*time.Millisecond); err == nil || !strings.Contains(err.Error(), "no response") {
		t.Fatalf("silent release host was not reported: %v", err)
	}
	if elapsed := time.Since(started); elapsed > 2*time.Second {
		t.Fatalf("silent release host delayed startup for %v", elapsed)
	}
}

func TestPortableUpdateRetriesInterruptedRangeRequests(t *testing.T) {
	root := t.TempDir()
	files := updateTestFiles()
	large := make([]byte, 2<<20)
	if _, err := rand.Read(large); err != nil {
		t.Fatal(err)
	}
	files["bin/large.dll"] = large
	archive, manifest := updateTestArchive(t, files, "")
	var injected atomic.Int64
	server, _, _ := updateTestFaultyRangeServer(t, archive, func(request int64, w http.ResponseWriter, req *http.Request) bool {
		switch request {
		case 2:
			injected.Add(1)
			w.WriteHeader(http.StatusServiceUnavailable)
			return true
		case 5:
			// Drop the connection halfway through a range body.
			var start, end int64
			fmt.Sscanf(req.Header.Get("Range"), "bytes=%d-%d", &start, &end)
			w.Header().Set("Content-Range", fmt.Sprintf("bytes %d-%d/%d", start, end, len(archive)))
			w.Header().Set("Content-Length", strconv.FormatInt(end-start+1, 10))
			w.Header().Set("ETag", `"immutable-test-asset"`)
			w.WriteHeader(http.StatusPartialContent)
			w.Write(archive[start : start+(end-start+1)/2])
			w.(http.Flusher).Flush()
			injected.Add(1)
			panic(http.ErrAbortHandler)
		case 7:
			// Drop the connection before any response.
			injected.Add(1)
			panic(http.ErrAbortHandler)
		}
		return false
	})
	plan, err := stagePortableUpdate(context.Background(), root, manifest, nil, server.Client(), server.URL, nil)
	if err != nil {
		t.Fatalf("transient release host failures aborted the update: %v", err)
	}
	if injected.Load() != 3 {
		t.Fatalf("only %d of 3 faults were exercised", injected.Load())
	}
	if err := applyPortableUpdate(root, plan, nil); err != nil {
		t.Fatal(err)
	}
	for name, content := range files {
		if got, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(name))); err != nil || !bytes.Equal(got, content) {
			t.Fatalf("retried download installed wrong %s: %v", name, err)
		}
	}
}

func TestPortableUpdateRangeRetriesStopForPermanentErrors(t *testing.T) {
	archive := bytes.Repeat([]byte("x"), 1000)
	failing := func(status int) func(int64, http.ResponseWriter, *http.Request) bool {
		return func(request int64, w http.ResponseWriter, req *http.Request) bool {
			if request == 1 {
				return false
			}
			w.WriteHeader(status)
			return true
		}
	}
	server, _, requests := updateTestFaultyRangeServer(t, archive, failing(http.StatusNotFound))
	reader, err := newUpdateRangeReader(context.Background(), server.Client(), server.URL, int64(len(archive)))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := reader.ReadAt(make([]byte, 10), 500); err == nil || requests.Load() != 2 {
		t.Fatalf("permanent HTTP error was retried: requests=%d err=%v", requests.Load(), err)
	}
	server, _, requests = updateTestFaultyRangeServer(t, archive, failing(http.StatusServiceUnavailable))
	reader, err = newUpdateRangeReader(context.Background(), server.Client(), server.URL, int64(len(archive)))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := reader.ReadAt(make([]byte, 10), 500); err == nil || requests.Load() != 1+updateRangeAttempts {
		t.Fatalf("persistent outage was not limited to %d attempts: requests=%d err=%v", updateRangeAttempts, requests.Load(), err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	server, _, _ = updateTestFaultyRangeServer(t, archive, func(request int64, w http.ResponseWriter, req *http.Request) bool {
		if request == 1 {
			return false
		}
		cancel()
		w.WriteHeader(http.StatusServiceUnavailable)
		return true
	})
	reader, err = newUpdateRangeReader(ctx, server.Client(), server.URL, int64(len(archive)))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := reader.ReadAt(make([]byte, 10), 500); !errors.Is(err, context.Canceled) {
		t.Fatalf("cancelled update kept retrying: %v", err)
	}
	redirect := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests.Add(1)
		http.Redirect(w, r, "/asset", http.StatusFound)
	}))
	defer redirect.Close()
	requests.Store(0)
	client := redirect.Client()
	client.CheckRedirect = portableUpdateHTTPClient().CheckRedirect
	if _, err := newUpdateRangeReader(context.Background(), client, redirect.URL, int64(len(archive))); !errors.Is(err, errUntrustedUpdateRedirect) || requests.Load() != 1 {
		t.Fatalf("untrusted redirect was retried: requests=%d err=%v", requests.Load(), err)
	}
}

// GitHub redirects the rolling release URL to an asset link that is signed for
// a few minutes. A download that outlasts it resolves the release URL again.
func TestPortableUpdateRenewsExpiredAssetLinks(t *testing.T) {
	files := updateTestFiles()
	large := make([]byte, 2<<20)
	if _, err := rand.Read(large); err != nil {
		t.Fatal(err)
	}
	files["bin/large.dll"] = large
	archive, manifest := updateTestArchive(t, files, "")
	release := "/download/latest/" + portableUpdatePackage
	for _, mode := range []string{"same-asset", "replaced-asset"} {
		t.Run(mode, func(t *testing.T) {
			var links, linkRequests atomic.Int64
			server, _, _ := updateTestFaultyRangeServer(t, archive, func(_ int64, w http.ResponseWriter, req *http.Request) bool {
				if req.URL.Path == release {
					linkRequests.Store(0)
					http.Redirect(w, req, fmt.Sprintf("/asset/%d", links.Add(1)), http.StatusFound)
					return true
				}
				// Each signed link serves three ranges and then expires.
				if req.URL.Path != fmt.Sprintf("/asset/%d", links.Load()) || linkRequests.Add(1) > 3 {
					http.Error(w, "Request has expired", http.StatusForbidden)
					return true
				}
				if mode == "replaced-asset" && links.Load() > 1 {
					var start, end int64
					fmt.Sscanf(req.Header.Get("Range"), "bytes=%d-%d", &start, &end)
					w.Header().Set("Content-Range", fmt.Sprintf("bytes %d-%d/%d", start, end, len(archive)))
					w.Header().Set("ETag", `"newer-release-asset"`)
					w.WriteHeader(http.StatusPartialContent)
					w.Write(archive[start : end+1])
					return true
				}
				return false
			})
			root := t.TempDir()
			plan, err := stagePortableUpdate(context.Background(), root, manifest, nil, server.Client(), server.URL+release, nil)
			if mode == "replaced-asset" {
				if err == nil || !strings.Contains(err.Error(), "release asset changed during update") {
					t.Fatalf("renewed link to another asset was accepted: %v", err)
				}
				return
			}
			if err != nil {
				t.Fatalf("expired asset link aborted the update: %v", err)
			}
			if links.Load() < 2 {
				t.Fatal("test download did not outlast its first asset link")
			}
			if err := applyPortableUpdate(root, plan, nil); err != nil {
				t.Fatal(err)
			}
			for name, content := range files {
				if got, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(name))); err != nil || !bytes.Equal(got, content) {
					t.Fatalf("update with renewed links installed wrong %s: %v", name, err)
				}
			}
		})
	}
}

func TestPortableUpdateSequentialRangesGrow(t *testing.T) {
	archive := make([]byte, 8<<20)
	if _, err := rand.Read(archive); err != nil {
		t.Fatal(err)
	}
	server, served, requests := updateTestRangeServer(t, archive)
	reader, err := newUpdateRangeReader(context.Background(), server.Client(), server.URL, int64(len(archive)))
	if err != nil {
		t.Fatal(err)
	}
	var content bytes.Buffer
	if _, err := io.Copy(&content, io.NewSectionReader(reader, 0, 4<<20)); err != nil || !bytes.Equal(content.Bytes(), archive[:4<<20]) {
		t.Fatalf("sequential read failed: %v", err)
	}
	if requests.Load() > 6 {
		t.Fatalf("sequential 4 MiB read used %d range requests", requests.Load())
	}
	// A jump to another part of the archive starts again with the smallest range.
	before := served.Load()
	if _, err := reader.ReadAt(make([]byte, 100), 100); err != nil {
		t.Fatal(err)
	}
	if fetched := served.Load() - before; fetched != minUpdateRangeBytes {
		t.Fatalf("random access fetched %d bytes", fetched)
	}
}

func TestPortableUpdateResumesWithVerifiedDownloads(t *testing.T) {
	root := t.TempDir()
	files := updateTestFiles()
	first, second := make([]byte, 1<<20), make([]byte, 1<<20)
	for _, content := range [][]byte{first, second} {
		if _, err := rand.Read(content); err != nil {
			t.Fatal(err)
		}
	}
	files["bin/a.dll"], files["bin/b.dll"] = first, second
	archive, manifest := updateTestArchive(t, files, "")
	server, served, _ := updateTestRangeServer(t, archive)
	// The first attempt fails after bin/a.dll was downloaded and verified.
	broken := manifest
	broken.Files = append([]portableUpdateFile{}, manifest.Files...)
	for i := range broken.Files {
		if broken.Files[i].Path == "bin/b.dll" {
			broken.Files[i].SHA256 = strings.Repeat("0", 64)
		}
	}
	if _, err := stagePortableUpdate(context.Background(), root, broken, nil, server.Client(), server.URL, nil); err == nil {
		t.Fatal("corrupt download accepted")
	}
	cache := filepath.Join(root, filepath.FromSlash(portableUpdateCacheDirectory))
	if digest, err := hashUpdateFile(filepath.Join(cache, updateTestDigest(first)), int64(len(first))); err != nil || digest != updateTestDigest(first) {
		t.Fatalf("verified download was not kept for the next attempt: %v", err)
	}
	served.Store(0)
	plan, err := stagePortableUpdate(context.Background(), root, manifest, nil, server.Client(), server.URL, nil)
	if err != nil {
		t.Fatal(err)
	}
	if served.Load() > int64(len(archive)-len(first)/2) {
		t.Fatalf("second attempt downloaded %d bytes again for a %d-byte ZIP", served.Load(), len(archive))
	}
	if _, err := os.Stat(cache); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("completed staging kept its download cache: %v", err)
	}
	if err := applyPortableUpdate(root, plan, nil); err != nil {
		t.Fatal(err)
	}
	for name, content := range files {
		if got, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(name))); err != nil || !bytes.Equal(got, content) {
			t.Fatalf("resumed update installed wrong %s: %v", name, err)
		}
	}
}

func TestPortableUpdateCacheKeepsOnlyNeededVerifiedFiles(t *testing.T) {
	cache := t.TempDir()
	needed, stale := []byte("needed release file"), []byte("file of an older release")
	updateTestWrite(t, cache, updateTestDigest(needed), needed)
	updateTestWrite(t, cache, updateTestDigest(stale), stale)
	pruneUpdateCache(cache, []portableUpdateOperation{
		{File: portableUpdateFile{Path: "needed.dll", Size: int64(len(needed)), SHA256: updateTestDigest(needed)}},
		{File: portableUpdateFile{Path: "stale.dll", Size: int64(len(stale)), SHA256: updateTestDigest(stale)}, Remove: true},
	})
	if _, err := os.Stat(filepath.Join(cache, updateTestDigest(stale))); !errors.Is(err, os.ErrNotExist) {
		t.Fatal("cache kept a file the update does not install")
	}
	stage := filepath.Join(t.TempDir(), "000000")
	file := portableUpdateFile{Path: "needed.dll", Size: int64(len(needed)), SHA256: updateTestDigest(needed)}
	updateTestWrite(t, cache, file.SHA256, []byte("damaged release file"))
	if reuseCachedUpdateFile(filepath.Join(cache, file.SHA256), stage, file) {
		t.Fatal("damaged cached file was reused")
	}
	if _, err := os.Stat(filepath.Join(cache, file.SHA256)); !errors.Is(err, os.ErrNotExist) {
		t.Fatal("damaged cached file was kept")
	}
	updateTestWrite(t, cache, file.SHA256, needed)
	if !reuseCachedUpdateFile(filepath.Join(cache, file.SHA256), stage, file) {
		t.Fatal("verified cached file was not reused")
	}
	if got, err := os.ReadFile(stage); err != nil || !bytes.Equal(got, needed) {
		t.Fatalf("reused file was not staged: %v", err)
	}
}

func TestPortableUpdateRecoveryIgnoresReusedProcessIDs(t *testing.T) {
	// A program from another folder stands in for an unrelated process that
	// received a process ID recorded before a crash or reboot.
	unrelated := updateTestStartIdleProcess(t, os.Args[0]).Process.Pid
	t.Run("owner", func(t *testing.T) {
		root := t.TempDir()
		updateTestWrite(t, root, portableUpdateDirectory+"/stage/pending", []byte("abandoned download"))
		if err := writeUpdateJSON(filepath.Join(root, portableUpdateDirectory, "owner.json"), portableUpdateOwner{PID: unrelated}); err != nil {
			t.Fatal(err)
		}
		if err := recoverPortableUpdate(root); err != nil {
			t.Fatalf("unrelated process blocked startup: %v", err)
		}
		for _, name := range []string{"stage", "owner.json"} {
			if _, err := os.Stat(filepath.Join(root, portableUpdateDirectory, name)); !errors.Is(err, os.ErrNotExist) {
				t.Fatalf("abandoned %s was kept: %v", name, err)
			}
		}
	})
	for _, role := range []string{"parent", "helper"} {
		t.Run(role, func(t *testing.T) {
			root := t.TempDir()
			old := []byte("old working launcher")
			updateTestWrite(t, root, "startup.exe", old)
			archive, manifest := updateTestArchive(t, updateTestFiles(), "")
			server, _, _ := updateTestRangeServer(t, archive)
			plan, err := stagePortableUpdate(context.Background(), root, manifest, nil, server.Client(), server.URL, nil)
			if err != nil {
				t.Fatal(err)
			}
			plan.Phase, plan.ParentPID = "applying", 2147483647
			if role == "parent" {
				plan.ParentPID = unrelated
			} else {
				plan.HelperPID = unrelated
			}
			for i := range plan.Operations {
				op := &plan.Operations[i]
				if op.File.Path == "startup.exe" {
					op.State = "applying"
					if err := os.Rename(filepath.Join(root, op.File.Path), filepath.Join(root, portableUpdateDirectory, op.Backup)); err != nil {
						t.Fatal(err)
					}
					if err := os.Rename(filepath.Join(root, portableUpdateDirectory, op.Stage), filepath.Join(root, op.File.Path)); err != nil {
						t.Fatal(err)
					}
				}
			}
			if err := writePortableUpdatePlan(root, plan); err != nil {
				t.Fatal(err)
			}
			if err := recoverPortableUpdate(root); err != nil {
				t.Fatalf("unrelated process blocked recovery: %v", err)
			}
			if got, err := os.ReadFile(filepath.Join(root, "startup.exe")); err != nil || !bytes.Equal(got, old) {
				t.Fatalf("interrupted update was not rolled back: %v", err)
			}
		})
	}
}

func TestPortableUpdateHelperWaitsForRecordedLauncherExit(t *testing.T) {
	launcher := updateTestStartIdleProcess(t, os.Args[0])
	exited := watchProcessExit(launcher.Process.Pid)
	if watchProcessExit(launcher.Process.Pid)(200 * time.Millisecond) {
		t.Fatal("running launcher was reported as exited")
	}
	stopped := make(chan struct{})
	go func() {
		defer close(stopped)
		time.Sleep(100 * time.Millisecond)
		launcher.Process.Kill()
		launcher.Wait()
	}()
	defer func() { <-stopped }()
	if !exited(10 * time.Second) {
		t.Fatal("launcher exit was not observed")
	}
}

func TestPortableUpdateRefusesRunningInstallationServers(t *testing.T) {
	root := t.TempDir()
	// The same server program from another folder belongs to another realm.
	updateTestStartIdleProcess(t, filepath.Join(t.TempDir(), "worldserver.exe"))
	if err := ensurePortableUpdateStopped(root, os.Getpid()); err != nil {
		t.Fatalf("a server of another installation blocked the update: %v", err)
	}
	updateTestStartIdleProcess(t, filepath.Join(root, "bin", "worldserver.exe"))
	if err := ensurePortableUpdateStopped(root, os.Getpid()); err == nil || !strings.Contains(err.Error(), "worldserver.exe is running") {
		t.Fatalf("running installation server was not detected: %v", err)
	}
}

func TestPortableUpdateCheckRecordsCurrentReleaseAndStagesNewOne(t *testing.T) {
	files := updateTestFiles()
	archive, manifest := updateTestArchive(t, files, "")
	manifestJSON, err := json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}
	// The package must be read next to the manifest.
	server, _, _ := updateTestFaultyRangeServer(t, archive, func(_ int64, w http.ResponseWriter, req *http.Request) bool {
		switch req.URL.Path {
		case "/UPDATE_MANIFEST.json":
			w.Write(manifestJSON)
		case "/" + portableUpdatePackage:
			return false
		default:
			http.NotFound(w, req)
		}
		return true
	})
	manifestURL := server.URL + "/UPDATE_MANIFEST.json"
	t.Run("current", func(t *testing.T) {
		root := t.TempDir()
		for name, content := range files {
			updateTestWrite(t, root, name, content)
		}
		if updating, err := checkPortableUpdateFrom(context.Background(), root, nil, server.Client(), manifestURL); updating || err != nil {
			t.Fatalf("current release was not accepted: updating=%v err=%v", updating, err)
		}
		if installed, err := readInstalledUpdateManifest(root); err != nil || installed.Revision != manifest.Revision {
			t.Fatalf("verified inventory of the current release was not recorded: %v", err)
		}
	})
	t.Run("outdated", func(t *testing.T) {
		root := t.TempDir()
		oldIdentity, err := json.Marshal(portableReleaseIdentity{Schema: 1, Revision: strings.Repeat("a", 40), Package: portableUpdatePackage, Version: "latest"})
		if err != nil {
			t.Fatal(err)
		}
		installed := map[string][]byte{
			"startup.exe":              []byte("old launcher"),
			"portable-release.json":    oldIdentity,
			"configs/worldserver.conf": []byte("custom settings"),
		}
		for name, content := range installed {
			updateTestWrite(t, root, name, content)
		}
		// The test release's launcher is not a program, so the verified
		// update is staged completely and then fails to start its helper.
		updating, err := checkPortableUpdateFrom(context.Background(), root, []string{"--skip-sql"}, server.Client(), manifestURL)
		if updating || err == nil || !strings.Contains(err.Error(), "start verified update helper") {
			t.Fatalf("update did not reach the helper launch: updating=%v err=%v", updating, err)
		}
		for name, content := range installed {
			if got, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(name))); err != nil || !bytes.Equal(got, content) {
				t.Fatalf("failed handoff changed %s: %v", name, err)
			}
		}
		for _, name := range []string{"journal.json", "owner.json", "stage", "backup", "helper.exe"} {
			if _, err := os.Stat(filepath.Join(root, portableUpdateDirectory, name)); !errors.Is(err, os.ErrNotExist) {
				t.Fatalf("failed handoff left %s: %v", name, err)
			}
		}
		launcher := files["startup.exe"]
		if digest, err := hashUpdateFile(filepath.Join(root, filepath.FromSlash(portableUpdateCacheDirectory), updateTestDigest(launcher)), int64(len(launcher))); err != nil || digest != updateTestDigest(launcher) {
			t.Fatalf("verified downloads were not kept for the next attempt: %v", err)
		}
	})
	t.Run("offline", func(t *testing.T) {
		root := t.TempDir()
		updateTestWrite(t, root, "portable-release.json", files["portable-release.json"])
		offline := httptest.NewServer(http.NotFoundHandler())
		offline.Close()
		if updating, err := checkPortableUpdateFrom(context.Background(), root, nil, offline.Client(), offline.URL+"/UPDATE_MANIFEST.json"); updating || err == nil {
			t.Fatalf("unreachable release host was accepted: updating=%v err=%v", updating, err)
		}
		if _, err := os.Stat(filepath.Join(root, portableUpdateDirectory)); !errors.Is(err, os.ErrNotExist) {
			t.Fatalf("offline check created update state: %v", err)
		}
	})
}
