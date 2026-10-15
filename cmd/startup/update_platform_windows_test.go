//go:build windows

package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func updateTestLockBackup(t *testing.T, root string) *os.File {
	t.Helper()
	filename := filepath.Join(root, portableUpdateDirectory, "backup", "locked")
	updateTestWrite(t, root, portableUpdateDirectory+"/backup/locked", []byte("locked backup"))
	reader, err := os.Open(filename)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { reader.Close() })
	if err := os.Remove(filename); err == nil {
		t.Skip("this Windows version removes files that are open for reading")
	} else if !transientUpdateFileError(err) {
		t.Fatalf("open backup produced an unexpected deletion error: %v", err)
	}
	return reader
}

func TestPortableUpdateCommittedCleanupAllowsLockedBackup(t *testing.T) {
	root := t.TempDir()
	updateTestWrite(t, root, "startup.exe", []byte("original launcher"))
	files := updateTestFiles()
	archive, manifest := updateTestArchive(t, files, "")
	server, _, _ := updateTestRangeServer(t, archive)
	plan, err := stagePortableUpdate(context.Background(), root, manifest, nil, server.Client(), server.URL, nil)
	if err != nil {
		t.Fatal(err)
	}
	reader := updateTestLockBackup(t, root)
	if err := applyPortableUpdate(root, plan, nil); err != nil {
		t.Fatalf("locked backup prevented a committed update from finishing: %v", err)
	}
	for name, content := range files {
		if got, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(name))); err != nil || !bytes.Equal(got, content) {
			t.Fatalf("committed update installed wrong %s: %v", name, err)
		}
	}
	installed, err := readInstalledUpdateManifest(root)
	if err != nil || installed.SHA256 != manifest.SHA256 {
		t.Fatalf("committed update did not record its inventory: %v", err)
	}
	if err := recoverPortableUpdate(root); err != nil {
		t.Fatalf("locked backup prevented recovery of a committed update: %v", err)
	}
	if pending, err := readPortableUpdatePlan(root); err != nil || pending.Phase != "committed" {
		t.Fatalf("cleanup failure did not retain the committed journal: plan=%v err=%v", pending, err)
	}
	if err := reader.Close(); err != nil {
		t.Fatal(err)
	}
	if err := recoverPortableUpdate(root); err != nil {
		t.Fatalf("released backup prevented cleanup retry: %v", err)
	}
	for _, name := range []string{"stage", "backup", "journal.json", "owner.json"} {
		if _, err := os.Stat(filepath.Join(root, portableUpdateDirectory, name)); !errors.Is(err, os.ErrNotExist) {
			t.Fatalf("cleanup retry kept %s: %v", name, err)
		}
	}
}

func TestPortableUpdateIntactCleanupAllowsLockedBackup(t *testing.T) {
	for _, phase := range []string{"staged", "rolled-back"} {
		t.Run(phase, func(t *testing.T) {
			root := t.TempDir()
			original := []byte("original launcher")
			updateTestWrite(t, root, "startup.exe", original)
			archive, manifest := updateTestArchive(t, updateTestFiles(), "")
			server, _, _ := updateTestRangeServer(t, archive)
			plan, err := stagePortableUpdate(context.Background(), root, manifest, nil, server.Client(), server.URL, nil)
			if err != nil {
				t.Fatal(err)
			}
			plan.Phase = phase
			if err := writePortableUpdatePlan(root, plan); err != nil {
				t.Fatal(err)
			}
			reader := updateTestLockBackup(t, root)
			if !discardIntactUpdate(root) {
				t.Fatal("locked backup prevented the intact installed release from restarting")
			}
			if got, err := os.ReadFile(filepath.Join(root, "startup.exe")); err != nil || !bytes.Equal(got, original) {
				t.Fatalf("cleanup changed the intact launcher: %v", err)
			}
			if pending, err := readPortableUpdatePlan(root); err != nil || pending.Phase != phase {
				t.Fatalf("cleanup failure did not retain the journal: plan=%v err=%v", pending, err)
			}
			if err := reader.Close(); err != nil {
				t.Fatal(err)
			}
			if err := recoverPortableUpdate(root); err != nil {
				t.Fatalf("released backup prevented cleanup retry: %v", err)
			}
			if _, err := os.Stat(filepath.Join(root, portableUpdateDirectory, "journal.json")); !errors.Is(err, os.ErrNotExist) {
				t.Fatalf("cleanup retry kept the journal: %v", err)
			}
		})
	}
}

func TestPortableUpdateJournalWriteWaitsForConcurrentReader(t *testing.T) {
	root := t.TempDir()
	if err := os.MkdirAll(filepath.Join(root, portableUpdateDirectory), 0700); err != nil {
		t.Fatal(err)
	}
	plan := &portableUpdatePlan{Schema: 1, Phase: "staged", ParentPID: os.Getpid(), Token: strings.Repeat("a", 64)}
	if err := writePortableUpdatePlan(root, plan); err != nil {
		t.Fatal(err)
	}
	journal := filepath.Join(root, portableUpdateDirectory, "journal.json")
	// Installed launchers poll the journal with os.Open, which does not share
	// delete access, while the helper replaces it with its acknowledgement.
	reader, err := os.Open(journal)
	if err != nil {
		t.Fatal(err)
	}
	released := make(chan struct{})
	go func() {
		time.Sleep(300 * time.Millisecond)
		reader.Close()
		close(released)
	}()
	t.Cleanup(func() { <-released })
	updateTestWrite(t, root, "probe.json", []byte("{}"))
	err = os.Rename(filepath.Join(root, "probe.json"), journal)
	if err == nil {
		t.Skip("this Windows version replaces files that are open for reading")
	}
	if !transientUpdateFileError(err) {
		t.Fatalf("open journal produced an unexpected replacement error: %v", err)
	}
	plan.HelperPID = os.Getpid()
	if err := writePortableUpdatePlan(root, plan); err != nil {
		t.Fatalf("helper acknowledgement failed while a launcher read the journal: %v", err)
	}
	var written portableUpdatePlan
	content, err := os.ReadFile(journal)
	if err != nil || json.Unmarshal(content, &written) != nil || written.HelperPID != os.Getpid() {
		t.Fatalf("acknowledgement was not written: %v %s", err, content)
	}
}
