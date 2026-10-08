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

func TestAutomaticProfilesImportLegacyDefaultsAndKeepCustomData(t *testing.T) {
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
	for _, expected := range []string{"AiPlayerbot.RandomBotJoinBG = 1\r\n", "AiPlayerbot.RandomBotEmote = 1\r\n", "PlayerbotsDatabaseInfo = \"db;3310;alice;secret;bots\"\r\n", "Custom.Bot = 42\r\n"} {
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
	if _, err := migrateConfigProfiles(root); err != nil {
		t.Fatal(err)
	}
	current, _ := os.ReadFile(bots)
	if !strings.Contains(string(current), "AiPlayerbot.RandomBotJoinBG = 1") || !strings.Contains(string(current), "AiPlayerbot.RandomBotMaxLevel = 70") {
		t.Fatalf("managed default or TBC phase lost: %s", current)
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
