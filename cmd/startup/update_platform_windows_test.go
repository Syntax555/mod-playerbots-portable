//go:build windows

package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

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
