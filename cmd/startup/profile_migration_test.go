package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestApplyProfileUpdatesRollback(t *testing.T) {
	directory := t.TempDir()
	first := filepath.Join(directory, "first.conf")
	second := filepath.Join(directory, "second.conf")
	if err := os.WriteFile(first, []byte("original"), 0644); err != nil {
		t.Fatal(err)
	}
	// A concurrent filesystem change can make replacement impossible after
	// preflight. The earlier successful config update must then be restored.
	if err := os.Mkdir(second, 0755); err != nil {
		t.Fatal(err)
	}
	updates := []profileUpdate{
		{path: first, original: []byte("original"), updated: []byte("recommended"), mode: 0644, backup: first + ".backup.test"},
		{path: second, original: []byte("second original"), updated: []byte("recommended"), mode: 0644, backup: second + ".backup.test"},
	}
	backups, err := applyProfileUpdates(updates)
	if err == nil {
		t.Fatal("replacement of a directory unexpectedly succeeded")
	}
	if len(backups) != 2 {
		t.Errorf("expected both backups before writing, got %v", backups)
	}
	actual, err := os.ReadFile(first)
	if err != nil || string(actual) != "original" {
		t.Errorf("earlier config was not rolled back: %q, %v", actual, err)
	}
	temporary, err := filepath.Glob(filepath.Join(directory, ".profile-update-*"))
	if err != nil || len(temporary) != 0 {
		t.Errorf("temporary files remain after failure: %v, %v", temporary, err)
	}
}

func TestApplyProfileUpdatesRestoresStateWithoutBackup(t *testing.T) {
	directory := t.TempDir()
	state := filepath.Join(directory, ".portable-profiles.json")
	blocked := filepath.Join(directory, "blocked.conf")
	if err := os.WriteFile(state, []byte("previous baseline"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(blocked, 0755); err != nil {
		t.Fatal(err)
	}
	updates := []profileUpdate{
		{path: state, original: []byte("previous baseline"), updated: []byte("next baseline"), mode: 0600},
		{path: blocked, original: []byte("old"), updated: []byte("new"), mode: 0644, backup: blocked + ".backup.test"},
	}
	backups, err := applyProfileUpdates(updates)
	if err == nil || len(backups) != 1 || backups[0] != blocked+".backup.test" {
		t.Fatalf("unexpected transaction result: %v, %v", backups, err)
	}
	if actual, err := os.ReadFile(state); err != nil || string(actual) != "previous baseline" {
		t.Errorf("launcher state was not restored from memory: %q, %v", actual, err)
	}
	if matches, err := filepath.Glob(state + ".backup.*"); err != nil || len(matches) != 0 {
		t.Errorf("launcher state was backed up: %v, %v", matches, err)
	}
}

func TestApplyProfileUpdatesBackupCollisionChangesNoConfig(t *testing.T) {
	directory := t.TempDir()
	first := writeFixture(t, filepath.Join(directory, "first.conf"), "first original")
	second := writeFixture(t, filepath.Join(directory, "second.conf"), "second original")
	collision := writeFixture(t, second+".backup.test", "earlier backup")
	updates := []profileUpdate{
		{path: first, original: []byte("first original"), updated: []byte("first updated"), mode: 0644, backup: first + ".backup.test"},
		{path: second, original: []byte("second original"), updated: []byte("second updated"), mode: 0644, backup: second + ".backup.test"},
	}
	backups, err := applyProfileUpdates(updates)
	if err == nil {
		t.Fatal("overwrote an existing backup")
	}
	if len(backups) != 1 || backups[0] != first+".backup.test" || readFixture(t, backups[0]) != "first original" {
		t.Errorf("backups written before the collision = %v", backups)
	}
	if readFixture(t, first) != "first original" || readFixture(t, second) != "second original" || readFixture(t, collision) != "earlier backup" {
		t.Error("a config or earlier backup changed after a backup collision")
	}
}

func TestApplyRuntimePortsPreservesCredentialsAndNewlines(t *testing.T) {
	content := "# LoginDatabaseInfo = \"comment\"\r\nLoginDatabaseInfo = \"dbhost;3306;alice;password;auth_db\"\r\nRealmServerPort = 3724\r\nCustom = 7\r\n"
	updated, err := applyRuntimePorts("authserver.conf.dist", content, startupOptions{port: 3307, authPort: 3725})
	if err != nil {
		t.Fatal(err)
	}
	expected := "# LoginDatabaseInfo = \"comment\"\r\nLoginDatabaseInfo = \"dbhost;3307;alice;password;auth_db\"\r\nRealmServerPort = 3725\r\nCustom = 7\r\n"
	if updated != expected {
		t.Errorf("unexpected config: %q", updated)
	}
}

func TestApplyRuntimePortsRejectsMalformedConnections(t *testing.T) {
	for _, connection := range []string{"not-quoted", "\"host;3306;user\""} {
		if _, err := applyRuntimePorts("worldserver.conf.dist", "WorldDatabaseInfo = "+connection, startupOptions{port: 3307}); err == nil {
			t.Errorf("accepted malformed connection %q", connection)
		}
	}
}
