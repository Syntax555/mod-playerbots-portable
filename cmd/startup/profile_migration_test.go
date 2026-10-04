package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestApplyRecommendedProfilesPreservesUnmanagedSettingsAndData(t *testing.T) {
	workDir := t.TempDir()
	entries, err := configProfiles.ReadDir("profiles")
	if err != nil {
		t.Fatal(err)
	}
	originals := make(map[string]string)
	for _, entry := range entries {
		directory := filepath.Join(workDir, "configs", "modules")
		if entry.Name() == "worldserver.conf" {
			directory = filepath.Join(workDir, "configs")
		}
		if err := os.MkdirAll(directory, 0755); err != nil {
			t.Fatal(err)
		}
		path := filepath.Join(directory, entry.Name())
		content := "# My own comments\r\nCustom.Value = \"retain=me\"\r\nLoginDatabaseInfo = \"192.168.0.10;3307;custom;secret;custom_auth\"\r\n"
		if entry.Name() == "playerbots.conf" {
			content += "AiPlayerbot.DisabledWithoutRealPlayer = 0\r\n"
		}
		if entry.Name() == "worldserver.conf" {
			content += "Expansion = 0\r\n"
		}
		originals[path] = content
		if err := os.WriteFile(path, []byte(content), 0644); err != nil {
			t.Fatal(err)
		}
	}
	authPath := filepath.Join(workDir, "configs", "authserver.conf")
	authContent := "RealmServerPort = 3725\nCustom.Auth = 42\n"
	if err := os.WriteFile(authPath, []byte(authContent), 0644); err != nil {
		t.Fatal(err)
	}
	dataPath := filepath.Join(workDir, "mysql", "data", "character-progress.ibd")
	if err := os.MkdirAll(filepath.Dir(dataPath), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(dataPath, []byte("existing characters"), 0644); err != nil {
		t.Fatal(err)
	}
	backups, err := applyRecommendedProfiles(workDir)
	if err != nil {
		t.Fatal(err)
	}
	if len(backups) != len(originals) {
		t.Fatalf("created %d backups for %d changed configs", len(backups), len(originals))
	}
	for _, backup := range backups {
		path := strings.Split(backup, ".backup.")[0]
		previous, err := os.ReadFile(backup)
		if err != nil {
			t.Fatal(err)
		}
		if string(previous) != originals[path] {
			t.Errorf("backup does not preserve original %s", path)
		}
		updated, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		for _, retained := range []string{"# My own comments\r\n", "Custom.Value = \"retain=me\"\r\n", "LoginDatabaseInfo = \"192.168.0.10;3307;custom;secret;custom_auth\"\r\n"} {
			if !strings.Contains(string(updated), retained) {
				t.Errorf("lost unmanaged setting %q in %s", retained, path)
			}
		}
		if strings.Contains(strings.ReplaceAll(string(updated), "\r\n", ""), "\n") {
			t.Errorf("changed CRLF line endings in %s", path)
		}
	}
	updatedBots, err := os.ReadFile(filepath.Join(workDir, "configs", "modules", "playerbots.conf"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(updatedBots), "AiPlayerbot.DisabledWithoutRealPlayer = 1\r\n") {
		t.Error("recommended player-presence setting was not applied")
	}
	for path, expected := range map[string]string{authPath: authContent, dataPath: "existing characters"} {
		actual, err := os.ReadFile(path)
		if err != nil || string(actual) != expected {
			t.Errorf("unmanaged file changed: %s (%v)", path, err)
		}
	}
	backups, err = applyRecommendedProfiles(workDir)
	if err != nil || len(backups) != 0 {
		t.Errorf("idempotent reapply created backups or failed: %v, %v", backups, err)
	}
}

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
