package main

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

type updateProgressTestOutput struct {
	mu     sync.Mutex
	buffer bytes.Buffer
	events chan string
}

func (w *updateProgressTestOutput) Write(content []byte) (int, error) {
	w.mu.Lock()
	n, err := w.buffer.Write(content)
	w.mu.Unlock()
	if w.events != nil {
		select {
		case w.events <- string(content):
		default:
		}
	}
	return n, err
}

func (w *updateProgressTestOutput) String() string {
	w.mu.Lock()
	defer w.mu.Unlock()
	return w.buffer.String()
}

func TestPortableUpdateProgressRemainsActiveDuringStalledRangeAndCancellation(t *testing.T) {
	root := t.TempDir()
	oldLauncher := []byte("working installed launcher")
	updateTestWrite(t, root, "startup.exe", oldLauncher)
	files := updateTestFiles()
	files["startup.exe"] = bytes.Repeat([]byte("new launcher payload"), 100000)
	archive, manifest := updateTestArchive(t, files, "")
	stalled := make(chan struct{})
	var stalledOnce sync.Once
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		var start, end int64
		if _, err := fmt.Sscanf(request.Header.Get("Range"), "bytes=%d-%d", &start, &end); err != nil || start < 0 || end < start || end >= int64(len(archive)) {
			http.Error(w, "invalid range", http.StatusRequestedRangeNotSatisfiable)
			return
		}
		// Initial identity/index requests finish normally. A changed-file body
		// then really stalls inside the production HTTP range reader.
		if end-start > 1 && start < int64(len(archive))-65557 {
			stalledOnce.Do(func() { close(stalled) })
			<-request.Context().Done()
			return
		}
		w.Header().Set("Content-Range", fmt.Sprintf("bytes %d-%d/%d", start, end, len(archive)))
		w.Header().Set("ETag", `"stalled-range-test"`)
		w.WriteHeader(http.StatusPartialContent)
		_, _ = w.Write(archive[start : end+1])
	}))
	defer server.Close()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	output := &updateProgressTestOutput{events: make(chan string, 64)}
	progress := newPortableUpdateProgress(ctx, output, false, 10*time.Millisecond)
	t.Cleanup(progress.close)
	result := make(chan error, 1)
	go func() {
		_, err := stagePortableUpdate(ctx, root, manifest, nil, server.Client(), server.URL, progress)
		result <- err
	}()
	deadline := time.NewTimer(3 * time.Second)
	defer deadline.Stop()
	select {
	case <-stalled:
	case <-deadline.C:
		t.Fatal("changed-file request did not reach the intended stall")
	}
	heartbeats := 0
	for heartbeats < 2 {
		select {
		case message := <-output.events:
			if strings.HasPrefix(message, "Update: Downloading, extracting and verifying changed files:") {
				heartbeats++
			}
		case <-deadline.C:
			t.Fatal("stalled download stopped displaying update activity")
		}
	}
	cancel()
	select {
	case err := <-result:
		if !errors.Is(err, context.Canceled) {
			t.Fatalf("cancelled range returned %v", err)
		}
	case <-deadline.C:
		t.Fatal("cancelled HTTP range did not stop staging")
	}
	progress.close()
	log := output.String()
	transfer := log[strings.Index(log, "Update: Downloading, extracting and verifying changed files"):]
	if strings.Contains(transfer, "100%") || strings.ContainsAny(log, "\r\x1b") {
		t.Fatalf("stalled cancelled transfer claimed completion or used console controls:\n%s", transfer)
	}
	got, err := os.ReadFile(filepath.Join(root, "startup.exe"))
	if err != nil || !bytes.Equal(got, oldLauncher) {
		t.Fatalf("cancellation changed the installed launcher: %v", err)
	}
	for _, child := range []string{"journal.json", "stage", "backup", "owner.json"} {
		if _, err := os.Stat(filepath.Join(root, portableUpdateDirectory, child)); !errors.Is(err, os.ErrNotExist) {
			t.Fatalf("cancelled staging left %s: %v", child, err)
		}
	}
}

func TestPortableUpdateProgressConsoleAndZeroByteFiles(t *testing.T) {
	for _, console := range []bool{false, true} {
		t.Run(fmt.Sprintf("console-%t", console), func(t *testing.T) {
			output := new(updateProgressTestOutput)
			progress := newPortableUpdateProgress(context.Background(), output, console, time.Hour)
			t.Cleanup(progress.close)
			progress.begin("Verifying empty files", "bytes", 0, 1)
			progress.finish()
			if strings.Contains(output.String(), "100%") {
				t.Fatal("empty file was complete before its verification")
			}
			progress.verifiedFile()
			progress.finish()
			progress.close()
			log := output.String()
			if !strings.Contains(log, "100%") || strings.Contains(log, "\x1b") {
				t.Fatalf("missing zero-byte completion or unnecessary ANSI sequences:\n%s", log)
			}
			if console {
				for _, line := range strings.Split(log, "\r")[1:] {
					if len(strings.SplitN(line, "\n", 2)[0]) > 78 {
						t.Fatal("console progress wraps an 80-column window")
					}
				}
			} else if strings.Contains(log, "\r") {
				t.Fatal("redirected progress contains carriage returns")
			}
		})
	}
}

func TestPortableUpdateProgressZeroChangedFilesCompletesVerifiedInventory(t *testing.T) {
	root := t.TempDir()
	files := updateTestFiles()
	for name, content := range files {
		updateTestWrite(t, root, name, content)
	}
	archive, manifest := updateTestArchive(t, files, "")
	server, _, _ := updateTestRangeServer(t, archive)
	output := new(updateProgressTestOutput)
	progress := newPortableUpdateProgress(context.Background(), output, false, time.Hour)
	t.Cleanup(progress.close)
	plan, err := stagePortableUpdate(context.Background(), root, manifest, nil, server.Client(), server.URL, progress)
	if err != nil || len(plan.Operations) != 0 {
		t.Fatalf("identical installation produced operations: %v", err)
	}
	if err := applyPortableUpdate(root, plan, progress); err != nil {
		t.Fatal(err)
	}
	progress.close()
	installed, err := readInstalledUpdateManifest(root)
	if err != nil || installed.Revision != manifest.Revision {
		t.Fatalf("zero-change update did not record verified inventory: %v", err)
	}
	for _, phase := range []string{"Downloading, extracting and verifying changed files", "Verifying staged update files", "Installing verified files"} {
		if !strings.Contains(output.String(), "Update: "+phase+": [####################] 100%") {
			t.Fatalf("zero-change update did not complete %s:\n%s", phase, output.String())
		}
	}
}

func TestPortableUpdateProgressVerifiedFilesDoNotCompleteWrongReleaseIdentity(t *testing.T) {
	root := t.TempDir()
	old := []byte("installed launcher")
	updateTestWrite(t, root, "startup.exe", old)
	files := updateTestFiles()
	files["portable-release.json"] = bytes.ReplaceAll(files["portable-release.json"], []byte(strings.Repeat("b", 40)), []byte(strings.Repeat("a", 40)))
	// Every ZIP file and SHA256 is valid; only the final release identity differs.
	archive, manifest := updateTestArchive(t, files, "")
	server, _, _ := updateTestRangeServer(t, archive)
	output := new(updateProgressTestOutput)
	progress := newPortableUpdateProgress(context.Background(), output, false, time.Hour)
	t.Cleanup(progress.close)
	if _, err := stagePortableUpdate(context.Background(), root, manifest, nil, server.Client(), server.URL, progress); err == nil || !strings.Contains(err.Error(), "release identity") {
		t.Fatalf("incorrect release identity accepted: %v", err)
	}
	progress.close()
	log := output.String()
	transfer := log[strings.Index(log, "Update: Downloading, extracting and verifying changed files"):]
	if strings.Contains(transfer, "100%") || !strings.Contains(transfer, "99%") {
		t.Fatalf("incorrect release identity was displayed as complete:\n%s", transfer)
	}
	got, err := os.ReadFile(filepath.Join(root, "startup.exe"))
	if err != nil || !bytes.Equal(got, old) {
		t.Fatalf("incorrect release identity changed the installed launcher: %v", err)
	}
}

func TestPortableUpdateProgressShortWriteCountsOnlyWrittenBytes(t *testing.T) {
	output := new(updateProgressTestOutput)
	progress := newPortableUpdateProgress(context.Background(), output, false, time.Hour)
	t.Cleanup(progress.close)
	progress.begin("Staging file", "bytes", 100, 1)
	var staged bytes.Buffer
	writer := updateProgressWriter{output: updateProgressShortWriter{output: &staged}, progress: progress}
	if n, err := writer.Write(make([]byte, 100)); n != 1 || !errors.Is(err, io.ErrShortWrite) {
		t.Fatalf("short staged write reported %d, %v", n, err)
	}
	progress.close()
	if staged.Len() != 1 || !strings.Contains(output.String(), "  1%") || strings.Contains(output.String(), "100%") {
		t.Fatalf("progress counted unwritten bytes:\n%s", output.String())
	}
}

type updateProgressShortWriter struct{ output io.Writer }

func (w updateProgressShortWriter) Write(content []byte) (int, error) {
	n, _ := w.output.Write(content[:1])
	return n, io.ErrShortWrite
}
