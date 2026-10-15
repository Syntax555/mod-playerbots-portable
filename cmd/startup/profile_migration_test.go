package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestPlayerbotsKeyMigrationKeepsReaderSemantics(t *testing.T) {
	for name, ending := range map[string]string{"LF": "\n", "CRLF": "\r\n"} {
		t.Run(name, func(t *testing.T) {
			original := strings.Join([]string{
				"# AiPlayerbot.Custom = comment",
				"[AiPlayerbot.Custom = section]",
				"  AiPlayerbot.Custom\t= \"AiPlayerbot.literal=retain\"  ",
				"AiPlayerbot.Custom = ignored duplicate",
				"AiPlayerbot.Mixed = legacy before",
				" Playerbots.Mixed = \"explicit\" ",
				"AiPlayerbot.Mixed = legacy after",
				"Playerbots.Mixed = ignored explicit duplicate",
				"AiPlayerbot.Empty =",
				"Other = \"AiPlayerbot.literal\"",
				"",
			}, ending)
			want := strings.Join([]string{
				"# AiPlayerbot.Custom = comment",
				"[AiPlayerbot.Custom = section]",
				"  Playerbots.Custom\t= \"AiPlayerbot.literal=retain\"  ",
				"Playerbots.Custom = ignored duplicate",
				"# Playerbots.Mixed = legacy before",
				" Playerbots.Mixed = \"explicit\" ",
				"# Playerbots.Mixed = legacy after",
				"Playerbots.Mixed = ignored explicit duplicate",
				"Playerbots.Empty =",
				"Other = \"AiPlayerbot.literal\"",
				"",
			}, ending)
			updated := migratePlayerbotsKeys(original)
			if updated != want {
				t.Fatalf("key migration changed values or formatting:\n%q\nwant:\n%q", updated, want)
			}
			for key, value := range map[string]string{
				"Playerbots.Custom": `"AiPlayerbot.literal=retain"`,
				"Playerbots.Mixed":  `"explicit"`,
				"Playerbots.Empty":  "",
			} {
				if actual, exists := configValue(updated, key); !exists || actual != value {
					t.Errorf("%s = %q, %v; want %q", key, actual, exists, value)
				}
			}
			if again := migratePlayerbotsKeys(updated); again != updated {
				t.Fatal("renaming keys is not idempotent")
			}
		})
	}
}

func TestPlayerbotsMigrationPreservesCustomValuesAndManagedBaseline(t *testing.T) {
	for _, tracked := range []bool{false, true} {
		name := "untracked"
		if tracked {
			name = "managed"
		}
		t.Run(name, func(t *testing.T) {
			root := t.TempDir()
			phase, _ := parseRealmPhase("tbc")
			profiles, err := currentManagedProfiles(phase)
			if err != nil {
				t.Fatal(err)
			}
			previous := strings.ReplaceAll(profiles["playerbots.conf"], "Playerbots.", "AiPlayerbot.")
			previous = strings.Replace(previous, "AiPlayerbot.RandomBotJoinBG = 1", "AiPlayerbot.RandomBotJoinBG = 0", 1)
			original := strings.Replace(previous, "AiPlayerbot.MaxRandomBots = 2500", "AiPlayerbot.MaxRandomBots = 25", 1)
			original += "\nAiPlayerbot.CustomUnmanaged = \"keep=me\"\nPlayerbotsDatabaseInfo = \"db;3310;alice;secret;bots\"\n"
			original = strings.ReplaceAll(strings.ReplaceAll(original, "\r\n", "\n"), "\n", "\r\n")
			path := writeFixture(t, filepath.Join(root, "configs/modules/playerbots.conf"), original)
			if tracked {
				state, err := json.Marshal(managedProfileState{Schema: 1, Profiles: map[string]string{"playerbots.conf": previous}})
				if err != nil {
					t.Fatal(err)
				}
				writeFixture(t, filepath.Join(root, "configs/"+automaticProfileState), string(state))
			}
			// No realm-phase file or other cap exists: infer TBC from the old key.
			backups, err := migrateConfigProfiles(root)
			if err != nil || len(backups) != 1 || readFixture(t, backups[0]) != original {
				t.Fatalf("migration did not back up the original config: %v, %v", backups, err)
			}
			updated := readFixture(t, path)
			joinBG := "0"
			if tracked {
				joinBG = "1"
			}
			for key, want := range map[string]string{
				"Playerbots.RandomBotMaxLevel": "70",
				"Playerbots.MaxRandomBots":     "25",
				"Playerbots.RandomBotJoinBG":   joinBG,
				"Playerbots.CustomUnmanaged":   `"keep=me"`,
				"PlayerbotsDatabaseInfo":       `"db;3310;alice;secret;bots"`,
			} {
				if value, exists := configValue(updated, key); !exists || value != want {
					t.Errorf("%s = %q, %v; want %q", key, value, exists, want)
				}
			}
			for key := range configAssignments(updated) {
				if strings.HasPrefix(key, "AiPlayerbot.") {
					t.Errorf("legacy key remains active: %s", key)
				}
			}
			if strings.Contains(strings.ReplaceAll(updated, "\r\n", ""), "\n") {
				t.Fatal("migration did not preserve CRLF")
			}
			state, _, err := readManagedProfileState(root)
			if err != nil || state.Profiles["playerbots.conf"] != profiles["playerbots.conf"] {
				t.Fatalf("renamed managed baseline was not saved: %v", err)
			}
			if second, err := migrateConfigProfiles(root); err != nil || len(second) != 0 || readFixture(t, path) != updated {
				t.Fatalf("migration is not idempotent: %v, %v", second, err)
			}
		})
	}
}

func TestPlayerbotsMigrationRollsBackConfigAndBaseline(t *testing.T) {
	root := t.TempDir()
	original := "AiPlayerbot.Custom = 25\r\n"
	originalState := `{"schema":1,"profiles":{"playerbots.conf":"AiPlayerbot.Custom = 25\r\n"}}`
	updatedState := `{"schema":1,"profiles":{"playerbots.conf":"Playerbots.Custom = 25\r\n"}}`
	config := writeFixture(t, filepath.Join(root, "playerbots.conf"), original)
	state := writeFixture(t, filepath.Join(root, automaticProfileState), originalState)
	blocked := filepath.Join(root, "blocked.conf")
	if err := os.Mkdir(blocked, 0755); err != nil {
		t.Fatal(err)
	}
	updates := []profileUpdate{
		{path: config, original: []byte(original), updated: []byte(migratePlayerbotsKeys(original)), mode: 0644, backup: config + ".backup.test"},
		{path: state, original: []byte(originalState), updated: []byte(updatedState), mode: 0600},
		{path: blocked, updated: []byte("blocked"), mode: 0644},
	}
	backups, err := applyProfileUpdates(updates)
	if err == nil || len(backups) != 1 || readFixture(t, backups[0]) != original {
		t.Fatalf("unexpected rollback result: %v, %v", backups, err)
	}
	if readFixture(t, config) != original || readFixture(t, state) != originalState {
		t.Fatal("failed migration left a renamed config or baseline")
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
