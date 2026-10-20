package main

import (
	"encoding/json"
	"path/filepath"
	"strings"
	"testing"
)

func TestLfgProfilesKeepFinderOptionalAndPreserveExistingSettings(t *testing.T) {
	for _, ending := range []string{"\n", "\r\n"} {
		for _, test := range []struct {
			name     string
			existing bool
			tracked  bool
		}{
			{name: "fresh"},
			{name: "active without baseline", existing: true},
			{name: "active with baseline", existing: true, tracked: true},
		} {
			endingName := "LF"
			if ending == "\r\n" {
				endingName = "CRLF"
			}
			t.Run(test.name+"/"+endingName, func(t *testing.T) {
				root := t.TempDir()
				templates := map[string]string{
					"worldserver.conf":                   "DungeonFinder.OptionsMask = 1\n",
					"modules/playerbots.conf":            "Playerbots.RandomBotJoinLfg = 1\n",
					"modules/individualProgression.conf": "IndividualProgression.DisableRDF = 1\n",
					"modules/mod_lfg_progression.conf":   "LfgProgression.Enable = 0\nLfgProgression.BotLock = 0\n",
				}
				for relative, content := range templates {
					writeFixture(t, filepath.Join(root, "configs", relative+".dist"), strings.ReplaceAll("[worldserver]\n"+content, "\n", ending))
				}
				expected := map[string]map[string]string{
					"worldserver.conf":                   {"DungeonFinder.OptionsMask": "0"},
					"modules/playerbots.conf":            {"Playerbots.RandomBotJoinLfg": "0"},
					"modules/individualProgression.conf": {"IndividualProgression.DisableRDF": "0"},
					"modules/mod_lfg_progression.conf": {
						"LfgProgression.Enable": "1", "LfgProgression.BotLock": "1", "LfgProgression.BotTier": "0",
						"LfgProgression.ClassicMaxLevel": "60", "LfgProgression.TbcMaxLevel": "70",
					},
				}
				originals := make(map[string]string)
				if test.existing {
					writeFixture(t, filepath.Join(root, "configs", realmPhaseFile), "individual\n")
					phase, _ := parseRealmPhase("individual")
					profiles, err := currentManagedProfiles(phase)
					if err != nil {
						t.Fatal(err)
					}
					expected["worldserver.conf"]["DungeonFinder.OptionsMask"] = "4"
					expected["modules/playerbots.conf"]["Playerbots.RandomBotJoinLfg"] = "1"
					expected["modules/mod_lfg_progression.conf"]["LfgProgression.ClassicMaxLevel"] = "59"
					expected["modules/mod_lfg_progression.conf"]["LfgProgression.TbcMaxLevel"] = "69"
					for relative, values := range expected {
						content := strings.ReplaceAll(profiles[filepath.Base(relative)], "\r\n", "\n")
						for key, value := range values {
							previous, _ := configValue(content, key)
							content = strings.ReplaceAll(content, key+" = "+previous, key+" = "+value)
						}
						originals[relative] = strings.ReplaceAll(content+"\nCustom.Value = 42\n", "\n", ending)
						writeFixture(t, filepath.Join(root, "configs", relative), originals[relative])
					}
					if test.tracked {
						state, err := json.Marshal(managedProfileState{Schema: 1, Profiles: profiles})
						if err != nil {
							t.Fatal(err)
						}
						writeFixture(t, filepath.Join(root, "configs", automaticProfileState), string(state))
					}
				}
				if err := ensureConfigFiles(root, root, "", defaultTestOptions()); err != nil {
					t.Fatal(err)
				}
				if backups, err := migrateConfigProfiles(root); err != nil || len(backups) != 0 {
					t.Fatalf("unexpected config migration: %v, %v", backups, err)
				}
				assertConfigValues(t, root, expected)
				for relative := range expected {
					content := readFixture(t, filepath.Join(root, "configs", relative))
					if test.existing && content != originals[relative] {
						t.Fatalf("personal configuration changed: %s", relative)
					}
					if ending == "\r\n" && strings.Contains(strings.ReplaceAll(content, "\r\n", ""), "\n") {
						t.Fatalf("Windows line endings changed: %s", relative)
					}
					originals[relative] = content
				}
				if backups, err := migrateConfigProfiles(root); err != nil || len(backups) != 0 {
					t.Fatalf("second migration is not idempotent: %v, %v", backups, err)
				}
				for relative, original := range originals {
					if readFixture(t, filepath.Join(root, "configs", relative)) != original {
						t.Fatalf("second migration changed %s", relative)
					}
				}
			})
		}
	}
}
