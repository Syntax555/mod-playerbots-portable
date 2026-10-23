package main

import (
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func updateTestInstalledJournal(t *testing.T) (string, *portableUpdatePlan, map[string][]byte) {
	t.Helper()
	root, plan, originals := updateTestStageJournal(t)
	if err := beginPortableUpdate(root, plan); err != nil {
		t.Fatal(err)
	}
	for i := range plan.Operations {
		op := &plan.Operations[i]
		op.State = "applying"
		target := filepath.Join(root, filepath.FromSlash(op.File.Path))
		if err := os.MkdirAll(filepath.Dir(target), 0755); err != nil {
			t.Fatal(err)
		}
		if op.HadOriginal {
			if err := backupUpdateFile(target, filepath.Join(root, portableUpdateDirectory, op.Backup), *op); err != nil {
				t.Fatal(err)
			}
		}
		if !op.Remove {
			if err := renameUpdateFile(filepath.Join(root, portableUpdateDirectory, op.Stage), target); err != nil {
				t.Fatal(err)
			}
		}
	}
	return root, plan, originals
}

func TestPortableUpdateInterruptedRollbackAfterCommitWriteFailure(t *testing.T) {
	for _, durablePhase := range []string{"applying", "committed"} {
		t.Run(durablePhase, func(t *testing.T) {
			testPortableUpdateInterruptedRollbackAfterCommitWriteFailure(t, durablePhase)
		})
	}
}

func testPortableUpdateInterruptedRollbackAfterCommitWriteFailure(t *testing.T, durablePhase string) {
	t.Helper()
	root, plan, originals := updateTestInstalledJournal(t)
	// A failed commit write leaves the in-memory phase ahead of durable state.
	plan.Phase = "committed"
	if durablePhase == "committed" {
		// Rename succeeded, but syncing the commit journal failed.
		if err := writePortableUpdatePlan(root, plan); err != nil {
			t.Fatal(err)
		}
	}
	var backup string
	for _, op := range plan.Operations {
		if op.File.Path == "startup.exe" {
			backup = filepath.Join(root, portableUpdateDirectory, op.Backup)
		}
	}
	if backup == "" {
		t.Fatal("fixture has no launcher backup")
	}
	if err := os.WriteFile(backup, []byte("damaged backup"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := rollbackPortableUpdate(root, plan); err == nil {
		t.Fatal("rollback accepted a damaged backup")
	}
	journal, err := readPortableUpdatePlan(root)
	if err != nil {
		t.Fatal(err)
	}
	if journal.Phase != "applying" {
		t.Fatalf("interrupted rollback was recorded as complete: phase=%q", journal.Phase)
	}
	if got, err := os.ReadFile(filepath.Join(root, "obsolete.dll")); err != nil || !bytes.Equal(got, originals["obsolete.dll"]) {
		t.Fatalf("fixture did not interrupt after the first rollback write: %v", err)
	}
	if err := os.WriteFile(backup, originals["startup.exe"], 0644); err != nil {
		t.Fatal(err)
	}
	if err := recoverPortableUpdate(root); err != nil {
		t.Fatal(err)
	}
	for name, original := range originals {
		if got, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(name))); err != nil || !bytes.Equal(got, original) {
			t.Fatalf("recovery did not restore %s: %v", name, err)
		}
	}
	for _, op := range plan.Operations {
		if !op.HadOriginal {
			if _, err := os.Stat(filepath.Join(root, filepath.FromSlash(op.File.Path))); !errors.Is(err, os.ErrNotExist) {
				t.Fatalf("recovery left a new update file %s: %v", op.File.Path, err)
			}
		}
	}
}

func TestPortableUpdateRollbackPersistsPhaseBeforeChangingFiles(t *testing.T) {
	root, plan, _ := updateTestInstalledJournal(t)
	plan.Phase = "committed"
	if err := writePortableUpdatePlan(root, plan); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(filepath.Join(root, portableUpdateDirectory, "journal.json.tmp"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := rollbackPortableUpdate(root, plan); err == nil {
		t.Fatal("rollback proceeded without being able to record its phase")
	}
	for _, op := range plan.Operations {
		target := filepath.Join(root, filepath.FromSlash(op.File.Path))
		if op.Remove {
			if _, err := os.Stat(target); !errors.Is(err, os.ErrNotExist) {
				t.Fatalf("rollback restored %s before recording its phase: %v", op.File.Path, err)
			}
		} else if digest, err := hashUpdateFile(target, op.File.Size); err != nil || digest != op.File.SHA256 {
			t.Fatalf("rollback changed %s before recording its phase: %v", op.File.Path, err)
		}
	}
}
