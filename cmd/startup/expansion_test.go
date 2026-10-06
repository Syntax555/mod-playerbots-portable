package main

import (
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func newPhaseRealm(t *testing.T) string {
	t.Helper()
	directory := t.TempDir()
	for _, name := range []string{"worldserver.conf", "individualProgression.conf", "playerbots.conf"} {
		content, err := applyConfigProfile(name, "[worldserver]\r\nCustom.Value = \"retain=me\"\r\nCharacterDatabaseInfo = \"host;3307;user;password;custom_characters\"\r\n")
		if err != nil {
			t.Fatal(err)
		}
		path := filepath.Join(directory, "configs", "modules", name)
		if name == "worldserver.conf" {
			path = filepath.Join(directory, "configs", name)
		}
		writePhaseTestFile(t, path, content)
	}
	writePhaseTestFile(t, filepath.Join(directory, "mysql", "data", "progress.ibd"), "earned characters and progression")
	writePhaseTestFile(t, filepath.Join(directory, "configs", "authserver.conf"), "Custom.Auth = preserve\n")
	return directory
}

func writePhaseTestFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}
}

func readPhaseTestFile(t *testing.T, path string) string {
	t.Helper()
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return string(content)
}

func TestExpansionTransitionsPreserveCharactersAndSurviveProfileUpdates(t *testing.T) {
	directory := newPhaseRealm(t)
	for _, target := range []struct {
		name, level, limit, maps, raceMask, classMask string
	}{
		{"tbc", "70", "12", "0,1,530", "0", "32"},
		{"wotlk", "80", "0", "0,1,530,571", "0", "0"},
	} {
		phase, _ := parseRealmPhase(target.name)
		originals := make(map[string]string)
		for _, relative := range []string{"worldserver.conf", "modules/playerbots.conf", "modules/individualProgression.conf"} {
			path := filepath.Join(directory, "configs", filepath.FromSlash(relative))
			originals[path] = readPhaseTestFile(t, path)
		}
		backups, err := setRealmPhase(directory, phase)
		if err != nil {
			t.Fatal(err)
		}
		for path, original := range originals {
			found := false
			for _, backup := range backups {
				if strings.HasPrefix(backup, path+".backup.") {
					found = true
					if readPhaseTestFile(t, backup) != original {
						t.Fatalf("backup did not preserve %s", path)
					}
				}
			}
			if !found {
				t.Fatalf("missing backup for %s", path)
			}
		}
		// A future profile migration must retain the chosen expansion.
		if _, err := applyRecommendedProfiles(directory); err != nil {
			t.Fatal(err)
		}
		for relative, expected := range map[string]map[string]string{
			"worldserver.conf":                   {"Expansion": "2", "MaxPlayerLevel": target.level, "CharacterCreating.Disabled.RaceMask": target.raceMask, "CharacterCreating.Disabled.ClassMask": target.classMask, "Rate.XP.Kill": "1", "StartPlayerLevel": "1"},
			"modules/individualProgression.conf": {"IndividualProgression.Enable": "1", "IndividualProgression.ProgressionLimit": target.limit, "IndividualProgression.BotAccountsMaxLevel": target.level, "IndividualProgression.StartingProgression": "0", "IndividualProgression.BotAccountsRegex": "\"\""},
			"modules/playerbots.conf":            {"AiPlayerbot.RandomBotMaxLevel": target.level, "AiPlayerbot.RandomBotMaps": target.maps, "AiPlayerbot.NaturalProgression": "1", "AiPlayerbot.DisableRandomLevels": "1", "AiPlayerbot.DisableDeathKnightLogin": "1", "AiPlayerbot.BotCheats": "\"\""},
		} {
			content := readPhaseTestFile(t, filepath.Join(directory, "configs", filepath.FromSlash(relative)))
			for key, want := range expected {
				if actual, exists := configValue(content, key); !exists || actual != want {
					t.Errorf("%s: %s = %q; want %q", target.name, key, actual, want)
				}
			}
			for _, retained := range []string{"Custom.Value = \"retain=me\"\r\n", "CharacterDatabaseInfo = \"host;3307;user;password;custom_characters\"\r\n"} {
				if !strings.Contains(content, retained) {
					t.Fatalf("lost custom setting or CRLF: %s", relative)
				}
			}
		}
		if readPhaseTestFile(t, filepath.Join(directory, "mysql", "data", "progress.ibd")) != "earned characters and progression" ||
			readPhaseTestFile(t, filepath.Join(directory, "configs", "authserver.conf")) != "Custom.Auth = preserve\n" {
			t.Fatal("changed characters or auth config")
		}
		if backups, err := setRealmPhase(directory, phase); err != nil || len(backups) != 0 {
			t.Fatalf("repeating phase selection is not idempotent: %v, %v", backups, err)
		}
	}
}

func TestExpansionRejectsDowngradesAndMissingConfigWithoutChanges(t *testing.T) {
	for _, failure := range []string{"downgrade", "missing"} {
		t.Run(failure, func(t *testing.T) {
			directory := newPhaseRealm(t)
			target, _ := parseRealmPhase("tbc")
			if failure == "downgrade" {
				writePhaseTestFile(t, filepath.Join(directory, "configs", realmPhaseFile), "wotlk\n")
			} else {
				os.Remove(filepath.Join(directory, "configs", "modules", "playerbots.conf"))
			}
			world := filepath.Join(directory, "configs", "worldserver.conf")
			before := readPhaseTestFile(t, world)
			if backups, err := setRealmPhase(directory, target); err == nil || len(backups) != 0 {
				t.Fatalf("accepted %s or wrote backups: %v %v", failure, backups, err)
			}
			if readPhaseTestFile(t, world) != before {
				t.Fatal("changed config after rejected switch")
			}
		})
	}
}

func TestExpansionRejectsListeningRealm(t *testing.T) {
	directory := newPhaseRealm(t)
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	world := filepath.Join(directory, "configs", "worldserver.conf")
	before := readPhaseTestFile(t, world) + fmt.Sprintf("WorldServerPort = %d\r\n", listener.Addr().(*net.TCPAddr).Port)
	writePhaseTestFile(t, world, before)
	target, _ := parseRealmPhase("tbc")
	if _, err := setRealmPhase(directory, target); err == nil || !strings.Contains(err.Error(), "stop startup.exe") {
		t.Fatalf("did not reject a listening realm: %v", err)
	}
	if readPhaseTestFile(t, world) != before {
		t.Fatal("changed running realm config")
	}
}

func TestLegacyExpansionInferenceAndInvalidState(t *testing.T) {
	directory := newPhaseRealm(t)
	for _, name := range []string{"tbc", "wotlk"} {
		phase, _ := parseRealmPhase(name)
		for _, relative := range []string{"worldserver.conf", "modules/individualProgression.conf", "modules/playerbots.conf"} {
			path := filepath.Join(directory, "configs", filepath.FromSlash(relative))
			content, _ := mergeConfigProfile(readPhaseTestFile(t, path), phase.profile(filepath.Base(relative)))
			writePhaseTestFile(t, path, content)
		}
		if actual, err := loadRealmPhase(directory); err != nil || actual.name != name {
			t.Fatalf("legacy %s inferred as %+v (%v)", name, actual, err)
		}
		if _, err := applyRecommendedProfiles(directory); err != nil {
			t.Fatal(err)
		}
		if actual, _ := loadRealmPhase(directory); actual.name != name {
			t.Fatal("profile update reverted legacy expansion")
		}
	}
	world := filepath.Join(directory, "configs", "worldserver.conf")
	content, _ := mergeConfigProfile(readPhaseTestFile(t, world), "MaxPlayerLevel = 60")
	writePhaseTestFile(t, world, content)
	if _, err := applyRecommendedProfiles(directory); err == nil {
		t.Fatal("accepted conflicting legacy caps")
	}
	wrath, _ := parseRealmPhase("wotlk")
	if _, err := setRealmPhase(directory, wrath); err != nil {
		t.Fatalf("could not repair partial legacy upgrade: %v", err)
	}
	if actual, _ := configValue(readPhaseTestFile(t, world), "MaxPlayerLevel"); actual != "80" {
		t.Fatal("partial upgrade was not aligned to Wrath")
	}
	writePhaseTestFile(t, filepath.Join(directory, "configs", realmPhaseFile), "not-an-expansion\n")
	if _, err := loadRealmPhase(directory); err == nil {
		t.Fatal("ignored malformed saved phase")
	}
}

func TestMissingConfigUsesSavedPhase(t *testing.T) {
	directory := t.TempDir()
	writePhaseTestFile(t, filepath.Join(directory, "configs", realmPhaseFile), "tbc\n")
	base := t.TempDir()
	for _, relative := range []string{"worldserver.conf.dist", "modules/playerbots.conf.dist", "modules/individualProgression.conf.dist"} {
		writePhaseTestFile(t, filepath.Join(base, "configs", filepath.FromSlash(relative)), "[worldserver]\nExpansion = 2\n")
	}
	if err := ensureConfigFiles(base, directory, "mysql/bin/mysql.exe"); err != nil {
		t.Fatal(err)
	}
	world := readPhaseTestFile(t, filepath.Join(directory, "configs", "worldserver.conf"))
	if actual, _ := configValue(world, "MaxPlayerLevel"); actual != "70" {
		t.Fatalf("missing config recreated Vanilla cap: %s", actual)
	}
}

func TestExpansionCLIValidation(t *testing.T) {
	for _, name := range []string{"vanilla", "TBC", "wotlk", "wrath"} {
		if _, err := parseArgs([]string{"--set-expansion", name}); err != nil {
			t.Fatal(err)
		}
	}
	if options, err := parseArgs([]string{"--show-expansion"}); err != nil || !options.showExpansion {
		t.Fatalf("show expansion parse: %v %v", options, err)
	}
	for _, arguments := range [][]string{{"--set-expansion", ""}, {"--set-expansion", "tcb"}, {"--set-expansion", "tbc", "extra"}, {"--set-expansion", "tbc", "--apply-profiles"}, {"--set-expansion", "tbc", "--show-expansion"}, {"--show-expansion", "--init-only"}} {
		if _, err := parseArgs(arguments); err == nil {
			t.Fatalf("accepted invalid expansion command: %v", arguments)
		}
	}
}

func TestNewPhaseFileRollsBackOnFailedTransaction(t *testing.T) {
	directory := t.TempDir()
	marker := filepath.Join(directory, realmPhaseFile)
	blocked := filepath.Join(directory, "blocked.conf")
	os.Mkdir(blocked, 0755)
	updates := []profileUpdate{
		{path: marker, updated: []byte("tbc\n"), mode: 0644, create: true},
		{path: blocked, original: []byte("old"), updated: []byte("new"), backup: filepath.Join(directory, "blocked.backup"), mode: 0644},
	}
	if _, err := applyProfileUpdates(updates); err == nil {
		t.Fatal("accepted failed transaction")
	}
	if _, err := os.Stat(marker); !os.IsNotExist(err) {
		t.Fatal("phase file survived rollback")
	}
}
