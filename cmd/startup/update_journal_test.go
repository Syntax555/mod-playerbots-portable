package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func updateTestStageJournal(t *testing.T) (string, *portableUpdatePlan, map[string][]byte) {
	t.Helper()
	root := t.TempDir()
	identity, err := json.Marshal(portableReleaseIdentity{Schema: 1, Revision: strings.Repeat("a", 40), Package: portableUpdatePackage, Version: "latest"})
	if err != nil {
		t.Fatal(err)
	}
	originals := map[string][]byte{
		"startup.exe":                   []byte("old working launcher"),
		"portable-release.json":         identity,
		"configs/worldserver.conf.dist": []byte("old distributed configuration"),
		"obsolete.dll":                  []byte("old package file"),
	}
	_, previous := updateTestArchive(t, originals, "")
	previous.Revision = strings.Repeat("a", 40)
	installed, err := json.Marshal(previous)
	if err != nil {
		t.Fatal(err)
	}
	originals[portableUpdateDirectory+"/installed.json"] = installed
	originals["configs/worldserver.conf"] = []byte("custom configuration")
	originals["mysql/data/characters.ibd"] = []byte("saved characters")
	for name, content := range originals {
		updateTestWrite(t, root, name, content)
	}
	archive, manifest := updateTestArchive(t, updateTestFiles(), "")
	server, _, _ := updateTestRangeServer(t, archive)
	plan, err := stagePortableUpdate(context.Background(), root, manifest, []string{"--skip-sql"}, server.Client(), server.URL, nil)
	if err != nil {
		t.Fatal(err)
	}
	plan.ParentPID = 2147483647
	return root, plan, originals
}

func TestPortableUpdateBeginWritesCompatibleRecoverySnapshot(t *testing.T) {
	root, plan, _ := updateTestStageJournal(t)
	if err := beginPortableUpdate(root, plan); err != nil {
		t.Fatal(err)
	}
	journal, err := readPortableUpdatePlan(root)
	if err != nil {
		t.Fatal(err)
	}
	if journal.Schema != 1 || journal.Phase != "applying" || plan.Phase != "applying" {
		t.Fatalf("incompatible recovery snapshot: schema=%d phase=%q in-memory phase=%q", journal.Schema, journal.Phase, plan.Phase)
	}
	if len(journal.Operations) != len(plan.Operations) {
		t.Fatal("recovery snapshot omitted operations")
	}
	for i, op := range journal.Operations {
		if op.State != "applying" {
			t.Fatalf("recovery snapshot left operation %s unprotected", op.File.Path)
		}
		if plan.Operations[i].State != "" {
			t.Fatalf("snapshot marked untouched in-memory operation %s as started", op.File.Path)
		}
		op.State = ""
		if op != plan.Operations[i] {
			t.Fatalf("recovery snapshot changed operation %s", op.File.Path)
		}
	}
}

func TestPortableUpdateRecoverySnapshotRestoresEveryInterruptedPrefix(t *testing.T) {
	// Each prefix contains complete earlier operations and one operation at the
	// chosen rename boundary. The journal always retains its initial snapshot.
	_, template, _ := updateTestStageJournal(t)
	for prefix := 0; prefix <= len(template.Operations); prefix++ {
		for _, boundary := range []string{"before-backup", "after-backup", "after-install"} {
			if prefix == len(template.Operations) && boundary != "before-backup" {
				continue
			}
			t.Run(fmt.Sprintf("%02d-%s", prefix, boundary), func(t *testing.T) {
				root, plan, originals := updateTestStageJournal(t)
				if err := beginPortableUpdate(root, plan); err != nil {
					t.Fatal(err)
				}
				for i := 0; i < len(plan.Operations) && i <= prefix; i++ {
					if i == prefix && boundary == "before-backup" {
						break
					}
					op := &plan.Operations[i]
					op.State = "applying"
					target := filepath.Join(root, filepath.FromSlash(op.File.Path))
					if err := os.MkdirAll(filepath.Dir(target), 0755); err != nil {
						t.Fatal(err)
					}
					if op.HadOriginal {
						backup := filepath.Join(root, portableUpdateDirectory, op.Backup)
						if err := backupUpdateFile(target, backup, *op); err != nil {
							t.Fatal(err)
						}
					}
					if i == prefix && boundary == "after-backup" {
						break
					}
					if !op.Remove {
						stage := filepath.Join(root, portableUpdateDirectory, op.Stage)
						if err := renameUpdateFile(stage, target); err != nil {
							t.Fatal(err)
						}
					}
				}
				journal, err := readPortableUpdatePlan(root)
				if err != nil {
					t.Fatal(err)
				}
				for _, op := range journal.Operations {
					if op.State != "applying" {
						t.Fatalf("interrupted update lost its initial recovery snapshot: %s", op.File.Path)
					}
				}
				if err := recoverPortableUpdate(root); err != nil {
					t.Fatal(err)
				}
				for name, original := range originals {
					got, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(name)))
					if err != nil || !bytes.Equal(got, original) {
						t.Fatalf("recovery did not preserve original %s: %v", name, err)
					}
				}
				for _, op := range plan.Operations {
					if op.HadOriginal {
						continue
					}
					if _, err := os.Stat(filepath.Join(root, filepath.FromSlash(op.File.Path))); !errors.Is(err, os.ErrNotExist) {
						t.Fatalf("recovery left a new package file %s: %v", op.File.Path, err)
					}
				}
				if err := recoverPortableUpdate(root); err != nil {
					t.Fatalf("repeat recovery is unsafe: %v", err)
				}
			})
		}
	}
}

func TestPortableUpdateRecoverySnapshotPreservesForeignDestination(t *testing.T) {
	root, plan, originals := updateTestStageJournal(t)
	if err := beginPortableUpdate(root, plan); err != nil {
		t.Fatal(err)
	}
	foreign := "src/data/sql/updates/new.sql/user.txt"
	updateTestWrite(t, root, foreign, []byte("user file"))
	if err := recoverPortableUpdate(root); err == nil {
		t.Fatal("recovery accepted a foreign destination as an installed update file")
	}
	if got, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(foreign))); err != nil || string(got) != "user file" {
		t.Fatalf("recovery changed the foreign destination: %v", err)
	}
	for name, original := range originals {
		if got, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(name))); err != nil || !bytes.Equal(got, original) {
			t.Fatalf("refused recovery changed original %s: %v", name, err)
		}
	}
	journal, err := readPortableUpdatePlan(root)
	if err != nil || journal.Phase != "applying" {
		t.Fatalf("refused recovery discarded its recovery journal: %v", err)
	}
}
