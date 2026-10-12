package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestManagedProfileThreeWayMerge(t *testing.T) {
	original := "# my settings\r\nManaged = 10\r\nCustom = 99\r\nLoginDatabaseInfo = \"db;3310;user;secret;auth\"\r\n"
	result, err := mergeManagedProfile(original, "Managed = 10\nCustom = 20\n", "Managed = 30\nCustom = 40\nNew = 50\n")
	if err != nil {
		t.Fatal(err)
	}
	for _, retained := range []string{"# my settings\r\n", "Managed = 30\r\n", "Custom = 99\r\n", "New = 50\r\n", "LoginDatabaseInfo = \"db;3310;user;secret;auth\"\r\n"} {
		if !strings.Contains(result, retained) {
			t.Fatalf("lost setting %q in %q", retained, result)
		}
	}
	if strings.Contains(strings.ReplaceAll(result, "\r\n", ""), "\n") {
		t.Fatal("migration did not preserve CRLF")
	}
	second, err := mergeManagedProfile(result, "Managed = 30\nCustom = 40\nNew = 50\n", "Managed = 30\nCustom = 40\nNew = 50\n")
	if err != nil || second != result {
		t.Fatalf("migration is not idempotent: %v", err)
	}
}

func TestManagedProfileWithoutBaselinePreservesExistingKeys(t *testing.T) {
	result, err := mergeManagedProfile("Existing = 5\n", "", "Existing = 9\nAdded = 3\n")
	if err != nil || !strings.Contains(result, "Existing = 5\n") || !strings.Contains(result, "Added = 3\n") {
		t.Fatalf("untracked user setting overwritten: %q, %v", result, err)
	}
}

func TestManagedProfileUsesFirstDuplicateLikeServer(t *testing.T) {
	// AzerothCore applies the first assignment and ignores later duplicates.
	managed, err := mergeManagedProfile("Managed = 10\nManaged = 99\n", "Managed = 10\n", "Managed = 30\n")
	if err != nil || managed != "Managed = 30\nManaged = 30\n" {
		t.Fatalf("effective managed value was not updated: %q, %v", managed, err)
	}
	custom, err := mergeManagedProfile("Managed = 99\nManaged = 10\n", "Managed = 10\n", "Managed = 30\n")
	if err != nil || custom != "Managed = 99\nManaged = 10\n" {
		t.Fatalf("effective custom value was overwritten: %q, %v", custom, err)
	}
}

func TestManagedProfileRejectsInvalidBaselines(t *testing.T) {
	for _, previous := range []string{"Value = 1\nValue = 2\n", "not a setting"} {
		if _, err := mergeManagedProfile("Value = 1\n", previous, "Value = 3\n"); err == nil {
			t.Fatalf("accepted invalid baseline %q", previous)
		}
	}
}

func profileFixture(t *testing.T, root, relative, content string) string {
	t.Helper()
	path := filepath.Join(root, filepath.FromSlash(relative))
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestAutomaticProfilesIgnoreEditedLegacyDefaultsAndKeepCustomData(t *testing.T) {
	root := t.TempDir()
	phase, _ := parseRealmPhase("individual")
	profiles, err := currentManagedProfiles(phase)
	if err != nil {
		t.Fatal(err)
	}
	profileFixture(t, root, "configs/realm-phase.txt", "individual\n")
	previous := strings.Replace(profiles["playerbots.conf"], "AiPlayerbot.RandomBotJoinBG = 1", "AiPlayerbot.RandomBotJoinBG = 0", 1)
	if previous == profiles["playerbots.conf"] {
		t.Fatal("fixture no longer represents a changed default")
	}
	profileFixture(t, root, "defaults/playerbots.conf", previous)
	previous = strings.Replace(previous, "AiPlayerbot.RandomBotEmote = 0", "AiPlayerbot.RandomBotEmote = 1", 1)
	previous = strings.ReplaceAll(previous, "\r\n", "\n")
	previous = strings.Replace(previous, "AiPlayerbot.Enabled = 1\n", "", 1)
	original := "# custom comment\n" + previous + "\nPlayerbotsDatabaseInfo = \"db;3310;alice;secret;bots\"\nCustom.Bot = 42\n"
	original = strings.ReplaceAll(strings.ReplaceAll(original, "\r\n", "\n"), "\n", "\r\n")
	bots := profileFixture(t, root, "configs/modules/playerbots.conf", original)
	world := profileFixture(t, root, "configs/worldserver.conf", profiles["worldserver.conf"])
	characters := profileFixture(t, root, "mysql/data/characters.ibd", "existing characters")
	auth := profileFixture(t, root, "configs/authserver.conf", "LoginDatabaseInfo = \"db;3310;alice;secret;auth\"\n")
	backups, err := migrateConfigProfiles(root)
	if err != nil {
		t.Fatal(err)
	}
	if len(backups) != 1 {
		t.Fatalf("expected one changed config backup, got %v", backups)
	}
	backedUp, err := os.ReadFile(backups[0])
	if err != nil || string(backedUp) != original {
		t.Fatalf("original configuration not backed up exactly: %v", err)
	}
	updated, err := os.ReadFile(bots)
	if err != nil {
		t.Fatal(err)
	}
	for _, expected := range []string{"AiPlayerbot.RandomBotJoinBG = 0\r\n", "AiPlayerbot.RandomBotEmote = 1\r\n", "AiPlayerbot.Enabled = 1\r\n", "PlayerbotsDatabaseInfo = \"db;3310;alice;secret;bots\"\r\n", "Custom.Bot = 42\r\n"} {
		if !strings.Contains(string(updated), expected) {
			t.Fatalf("missing managed or custom setting %q", expected)
		}
	}
	for path, expected := range map[string]string{world: profiles["worldserver.conf"], characters: "existing characters", auth: "LoginDatabaseInfo = \"db;3310;alice;secret;auth\"\n"} {
		content, err := os.ReadFile(path)
		if err != nil || string(content) != expected {
			t.Fatalf("unmanaged content changed at %s: %v", path, err)
		}
	}
	state, _, err := readManagedProfileState(root)
	if err != nil || len(state.Profiles) != 2 {
		t.Fatalf("managed defaults were not recorded: %+v, %v", state, err)
	}
	if strings.Contains(state.Profiles["playerbots.conf"], "secret") {
		t.Fatal("user credentials persisted in defaults baseline")
	}
	second, err := migrateConfigProfiles(root)
	if err != nil || len(second) != 0 {
		t.Fatalf("second startup changed unchanged configurations: %v, %v", second, err)
	}
}

func TestAutomaticProfilesUseSavedDefaultsAndPreserveRealmPhase(t *testing.T) {
	root := t.TempDir()
	phase, _ := parseRealmPhase("tbc")
	profiles, _ := currentManagedProfiles(phase)
	old := strings.Replace(profiles["playerbots.conf"], "AiPlayerbot.RandomBotJoinBG = 1", "AiPlayerbot.RandomBotJoinBG = 0", 1)
	profileFixture(t, root, "configs/realm-phase.txt", "tbc\n")
	bots := profileFixture(t, root, "configs/modules/playerbots.conf", old)
	state, err := json.Marshal(managedProfileState{Schema: 1, Profiles: map[string]string{"playerbots.conf": old}})
	if err != nil {
		t.Fatal(err)
	}
	profileFixture(t, root, "configs/"+automaticProfileState, string(state))
	backups, err := migrateConfigProfiles(root)
	if err != nil {
		t.Fatal(err)
	}
	current, _ := os.ReadFile(bots)
	if !strings.Contains(string(current), "AiPlayerbot.RandomBotJoinBG = 1") || !strings.Contains(string(current), "AiPlayerbot.RandomBotMaxLevel = 70") {
		t.Fatalf("managed default or TBC phase lost: %s", current)
	}
	// Only user-facing configs receive backups; the baseline changed as well.
	if len(backups) != 1 || !strings.HasPrefix(backups[0], bots+".backup.") {
		t.Fatalf("backups = %v; want only the playerbots.conf backup", backups)
	}
	if matches, err := filepath.Glob(filepath.Join(root, "configs", automaticProfileState+".backup.*")); err != nil || len(matches) != 0 {
		t.Fatalf("baseline backups were written: %v, %v", matches, err)
	}
	if saved, _, err := readManagedProfileState(root); err != nil || saved.Profiles["playerbots.conf"] == old {
		t.Fatalf("baseline was not updated: %v", err)
	}
}

func TestAutomaticProfilesPlayerPresenceKeepsCustomSettings(t *testing.T) {
	for _, test := range []struct {
		name          string
		previousValue string
		wantValue     string
	}{
		{name: "managed always-online default", previousValue: "0", wantValue: "1"},
		{name: "custom always-online setting", previousValue: "1", wantValue: "0"},
		{name: "untracked existing setting", wantValue: "0"},
	} {
		t.Run(test.name, func(t *testing.T) {
			root := t.TempDir()
			phase, _ := parseRealmPhase("individual")
			profiles, err := currentManagedProfiles(phase)
			if err != nil {
				t.Fatal(err)
			}
			// Windows checkouts embed CRLF profiles; the fixture uses LF on every platform.
			current := strings.ReplaceAll(profiles["playerbots.conf"], "\r\n", "\n")
			if value, ok := configValue(current, "AiPlayerbot.DisabledWithoutRealPlayer"); !ok || value != "1" {
				t.Fatal("player-presence default is missing from the effective profile")
			}
			original := strings.Replace(current, "AiPlayerbot.DisabledWithoutRealPlayer = 1", "AiPlayerbot.DisabledWithoutRealPlayer = 0", 1)
			original = strings.Replace(original, "AiPlayerbot.MaxRandomBots = 2500", "AiPlayerbot.MaxRandomBots = 25", 1)
			original += "\nPlayerbotsDatabaseInfo = \"db;3310;alice;secret;bots\"\nCustom.Bot = 42\n"
			bots := profileFixture(t, root, "configs/modules/playerbots.conf", original)
			characters := profileFixture(t, root, "mysql/data/characters.ibd", "existing characters")
			if test.previousValue != "" {
				previous := strings.Replace(current, "AiPlayerbot.DisabledWithoutRealPlayer = 1", "AiPlayerbot.DisabledWithoutRealPlayer = "+test.previousValue, 1)
				state, err := json.Marshal(managedProfileState{Schema: 1, Profiles: map[string]string{"playerbots.conf": previous}})
				if err != nil {
					t.Fatal(err)
				}
				profileFixture(t, root, "configs/"+automaticProfileState, string(state))
			}
			backups, err := migrateConfigProfiles(root)
			if err != nil {
				t.Fatal(err)
			}
			updated, err := os.ReadFile(bots)
			if err != nil {
				t.Fatal(err)
			}
			if value, _ := configValue(string(updated), "AiPlayerbot.DisabledWithoutRealPlayer"); value != test.wantValue {
				t.Fatalf("presence setting = %q, want %q", value, test.wantValue)
			}
			for _, retained := range []string{"AiPlayerbot.MaxRandomBots = 25\n", "PlayerbotsDatabaseInfo = \"db;3310;alice;secret;bots\"\n", "Custom.Bot = 42\n"} {
				if !strings.Contains(string(updated), retained) {
					t.Fatalf("lost custom setting %q", retained)
				}
			}
			if test.wantValue == "1" {
				foundBackup := false
				for _, backup := range backups {
					if strings.HasPrefix(backup, bots+".backup.") {
						content, err := os.ReadFile(backup)
						if err != nil || string(content) != original {
							t.Fatalf("previous config was not backed up exactly: %v", err)
						}
						foundBackup = true
					}
				}
				if !foundBackup {
					t.Fatal("managed presence change did not create a backup")
				}
			} else if string(updated) != original {
				t.Fatal("custom presence configuration was modified")
			}
			if content, err := os.ReadFile(characters); err != nil || string(content) != "existing characters" {
				t.Fatalf("character data changed: %v", err)
			}
			second, err := migrateConfigProfiles(root)
			if err != nil || len(second) != 0 {
				t.Fatalf("second startup changed the configuration: %v, %v", second, err)
			}
		})
	}
}

func TestAutomaticDungeonRoutesPreserveCustomSelection(t *testing.T) {
	const key = "DungeonClear.AutonomousParties.Dungeons"
	const previousRoutes = `"4,1,6,8,10,12,16,14,18,165,163,164,20,22,24,272,26,273,28,30,276,34,32,36,2,38,40,274"`
	for _, ending := range []string{"\n", "\r\n"} {
		endingName := "LF"
		if ending == "\r\n" {
			endingName = "CRLF"
		}
		for _, test := range []struct {
			name      string
			selection string
			tracked   bool
			managed   bool
		}{
			{name: "managed Vanilla default", selection: previousRoutes, tracked: true, managed: true},
			{name: "custom dungeon selection", selection: `"4,12"`, tracked: true},
			{name: "existing untracked selection", selection: `"4,12"`},
		} {
			t.Run(test.name+"/"+endingName, func(t *testing.T) {
				root := t.TempDir()
				phase, _ := parseRealmPhase("individual")
				profiles, err := currentManagedProfiles(phase)
				if err != nil {
					t.Fatal(err)
				}
				current := strings.ReplaceAll(profiles["mod_dungeon_clear.conf"], "\r\n", "\n")
				newRoutes, ok := configValue(current, key)
				if !ok || newRoutes == previousRoutes {
					t.Fatal("expanded dungeon routes are missing from the managed profile")
				}
				previous := strings.Replace(current, key+" = "+newRoutes, key+" = "+previousRoutes, 1)
				original := strings.Replace(previous, key+" = "+previousRoutes, key+" = "+test.selection, 1)
				original = strings.Replace(original, "DungeonClear.AutonomousParties.Enable = 1", "DungeonClear.AutonomousParties.Enable = 0", 1)
				original = strings.Replace(original, "DungeonClear.AutonomousParties.MaxConcurrent = 2", "DungeonClear.AutonomousParties.MaxConcurrent = 1", 1)
				original += "\nCustom.Dungeon = 42\n"
				original = strings.ReplaceAll(original, "\n", ending)
				path := profileFixture(t, root, "configs/modules/mod_dungeon_clear.conf", original)
				characters := profileFixture(t, root, "mysql/data/characters.ibd", "existing characters")
				if test.tracked {
					state, err := json.Marshal(managedProfileState{Schema: 1, Profiles: map[string]string{"mod_dungeon_clear.conf": previous}})
					if err != nil {
						t.Fatal(err)
					}
					profileFixture(t, root, "configs/"+automaticProfileState, string(state))
				}
				backups, err := migrateConfigProfiles(root)
				if err != nil {
					t.Fatal(err)
				}
				var configBackups []string
				for _, backup := range backups {
					if strings.HasPrefix(backup, path+".backup.") {
						configBackups = append(configBackups, backup)
					}
				}
				updated, err := os.ReadFile(path)
				if err != nil {
					t.Fatal(err)
				}
				want := test.selection
				if test.managed {
					want = newRoutes
					if len(configBackups) != 1 {
						t.Fatalf("expected one config backup, got %v", configBackups)
					}
					backup, err := os.ReadFile(configBackups[0])
					if err != nil || string(backup) != original {
						t.Fatalf("original configuration was not preserved exactly: %v", err)
					}
				} else if len(configBackups) != 0 || string(updated) != original {
					t.Fatal("custom or untracked dungeon selection was modified")
				}
				if value, _ := configValue(string(updated), key); value != want {
					t.Fatalf("dungeon selection = %q, want %q", value, want)
				}
				for _, retained := range []string{"DungeonClear.AutonomousParties.Enable = 0", "DungeonClear.AutonomousParties.MaxConcurrent = 1", "Custom.Dungeon = 42"} {
					if !strings.Contains(string(updated), retained+ending) {
						t.Fatalf("lost custom setting %q", retained)
					}
				}
				if ending == "\r\n" && strings.Contains(strings.ReplaceAll(string(updated), "\r\n", ""), "\n") {
					t.Fatal("migration changed Windows line endings")
				}
				if content, err := os.ReadFile(characters); err != nil || string(content) != "existing characters" {
					t.Fatalf("character data changed: %v", err)
				}
				if second, err := migrateConfigProfiles(root); err != nil || len(second) != 0 {
					t.Fatalf("second startup changed unchanged configuration: %v, %v", second, err)
				}
			})
		}
	}
}

func TestAutomaticProfilesInvalidStateAbortsBeforeWriting(t *testing.T) {
	for _, content := range []string{`{"schema":2,"profiles":{}}`, `{"schema":1,"profiles":{"../escape.conf":"Value = 1"}}`, "{} trailing"} {
		t.Run(content, func(t *testing.T) {
			root := t.TempDir()
			original := "Custom = 42\n"
			path := profileFixture(t, root, "configs/worldserver.conf", original)
			profileFixture(t, root, "configs/"+automaticProfileState, content)
			if _, err := migrateConfigProfiles(root); err == nil {
				t.Fatal("invalid state accepted")
			}
			after, _ := os.ReadFile(path)
			if string(after) != original {
				t.Fatal("configuration changed before baseline was validated")
			}
		})
	}
}

func TestAutomaticProfilesRefuseSymlinkTargets(t *testing.T) {
	root := t.TempDir()
	target := profileFixture(t, t.TempDir(), "outside.conf", "Existing = 5\n")
	directory := filepath.Join(root, "configs")
	if err := os.MkdirAll(directory, 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(target, filepath.Join(directory, "worldserver.conf")); err != nil {
		t.Skipf("symlinks unavailable: %v", err)
	}
	if _, err := migrateConfigProfiles(root); err == nil {
		t.Fatal("migration followed a symlink")
	}
	after, _ := os.ReadFile(target)
	if string(after) != "Existing = 5\n" {
		t.Fatal("external configuration overwritten")
	}
}
