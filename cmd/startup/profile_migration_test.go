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
