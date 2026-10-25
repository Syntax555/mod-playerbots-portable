package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRaidClearProfileKeepsSpellLearningEarned(t *testing.T) {
	const key = "RaidClear.Bots.TeachTranquilizingShot"
	fresh, err := applyConfigProfile("playerbots.conf.dist", "[worldserver]\n"+key+" = 1\n")
	if err != nil {
		t.Fatal(err)
	}
	if value, ok := configValue(fresh, key); !ok || value != "0" {
		t.Fatalf("fresh raid profile grants spells: %q", fresh)
	}
	if _, err := configProfiles.ReadFile("profiles/mod_raid_clear.conf"); !os.IsNotExist(err) {
		t.Fatalf("standalone raid profile remains embedded: %v", err)
	}
}

func TestRaidClearMigrationPreservesSettingsAndDestinationChoices(t *testing.T) {
	const teaching = "RaidClear.Bots.TeachTranquilizingShot"
	for _, ending := range []string{"\n", "\r\n"} {
		for _, tracked := range []bool{false, true} {
			t.Run(ending+"/"+map[bool]string{false: "untracked", true: "tracked"}[tracked], func(t *testing.T) {
				root := t.TempDir()
				legacy := strings.ReplaceAll("[worldserver]\n# original comments\n"+teaching+" = 1\n"+teaching+" = 0\nRaidClear.Enable = 0\nRaidClear.Tanks.Separation = 17\nRaidClear.BlackwingLair.Firemaw.TankSpot = \t\nCustom.Legacy = 7\n", "\n", ending)
				oldPath := writeFixture(t, filepath.Join(root, "configs/modules/mod_raid_clear.conf"), legacy)
				template := writeFixture(t, oldPath+".dist", "[worldserver]\nRaidClear.Enable = 1\n")
				original := strings.ReplaceAll("[worldserver]\nRaidClear.Enable = 1\nRaidClear.Enable = 0\nCustom.Playerbots = 9\n", "\n", ending)
				path := writeFixture(t, filepath.Join(root, "configs/modules/playerbots.conf"), original)
				if tracked {
					state, err := json.Marshal(managedProfileState{Schema: 1, Profiles: map[string]string{
						"mod_raid_clear.conf": "[worldserver]\n" + teaching + " = 0\n",
						"playerbots.conf":     "Playerbots.Enabled = 1\n",
					}})
					if err != nil {
						t.Fatal(err)
					}
					writeFixture(t, filepath.Join(root, "configs/"+automaticProfileState), string(state))
				}
				backups, err := migrateConfigProfiles(root)
				if err != nil {
					t.Fatal(err)
				}
				updated := readFixture(t, path)
				for key, want := range map[string]string{teaching: "1", "RaidClear.Enable": "1", "RaidClear.Tanks.Separation": "17", "RaidClear.BlackwingLair.Firemaw.TankSpot": `""`, "Custom.Playerbots": "9"} {
					if value, ok := configValue(updated, key); !ok || value != want {
						t.Errorf("%s = %q, %v; want %q", key, value, ok, want)
					}
				}
				if !strings.HasPrefix(updated, original) || strings.Contains(updated, "Custom.Legacy") ||
					strings.Count(updated, teaching+" = ") != 1 {
					t.Fatalf("migration changed explicit settings or copied unrelated/duplicate keys: %q", updated)
				}
				if ending == "\r\n" && strings.Contains(strings.ReplaceAll(updated, ending, ""), "\n") {
					t.Fatal("migration changed Windows line endings")
				}
				if readFixture(t, oldPath) != legacy {
					t.Fatal("original raid configuration changed")
				}
				if len(backups) != 2 {
					t.Fatalf("expected playerbots and obsolete template backups, got %v", backups)
				}
				for source, want := range map[string]string{path: original, template: "[worldserver]\nRaidClear.Enable = 1\n"} {
					matches, err := filepath.Glob(source + ".backup.*")
					if err != nil || len(matches) != 1 || readFixture(t, matches[0]) != want {
						t.Fatalf("original settings not backed up exactly: %v, %v", matches, err)
					}
				}
				if _, err := os.Stat(template); !os.IsNotExist(err) {
					t.Fatalf("obsolete template remains: %v", err)
				}
				state, _, err := readManagedProfileState(root)
				if err != nil {
					t.Fatal(err)
				}
				if _, exists := state.Profiles["mod_raid_clear.conf"]; exists {
					t.Fatal("standalone raid profile remains managed")
				}
				if changes, err := migrateConfigProfiles(root); err != nil || len(changes) != 0 || readFixture(t, path) != updated {
					t.Fatalf("raid config migration is not idempotent: %v, %v", changes, err)
				}
			})
		}
	}
}

func TestRaidClearMigrationSeedsNewPlayerbotsWithoutLosingLegacySettings(t *testing.T) {
	const key = "RaidClear.Bots.TeachTranquilizingShot"
	for _, separate := range []bool{false, true} {
		t.Run(map[bool]string{false: "portable", true: "separate work directory"}[separate], func(t *testing.T) {
			base := t.TempDir()
			root := base
			if separate {
				root = t.TempDir()
			}
			legacy := "[worldserver]\r\nRaidClear.Enable = 0\r\n" + key + " = 1\r\nRaidClear.BlackwingLair.Firemaw.TankSpot = \t\r\n"
			writeFixture(t, filepath.Join(base, "configs/modules/mod_raid_clear.conf"), legacy)
			writeFixture(t, filepath.Join(base, "configs/modules/mod_raid_clear.conf.dist"), "[worldserver]\nRaidClear.Enable = 1\n")
			writeFixture(t, filepath.Join(base, "configs/modules/playerbots.conf.dist"), "[worldserver]\r\nRaidClear.Enable = 1\r\n"+key+" = 1\r\nRaidClear.BlackwingLair.Firemaw.TankSpot = \"1 2 3\"\r\n")
			if err := ensureConfigFiles(base, root, "", defaultTestOptions()); err != nil {
				t.Fatal(err)
			}
			if _, err := migrateConfigProfiles(root); err != nil {
				t.Fatal(err)
			}
			path := filepath.Join(root, "configs/modules/playerbots.conf")
			updated := readFixture(t, path)
			for key, want := range map[string]string{key: "1", "RaidClear.Enable": "0", "RaidClear.BlackwingLair.Firemaw.TankSpot": `""`, "Playerbots.NaturalProgression": "1"} {
				if value, ok := configValue(updated, key); !ok || value != want {
					t.Fatalf("seeded %s = %q, %v; want %q", key, value, ok, want)
				}
			}
			if readFixture(t, filepath.Join(root, "configs/modules/mod_raid_clear.conf")) != legacy {
				t.Fatal("original raid configuration changed")
			}
			if err := ensureConfigFiles(base, root, "", defaultTestOptions()); err != nil {
				t.Fatal(err)
			}
			if changes, err := migrateConfigProfiles(root); err != nil || len(changes) != 0 || readFixture(t, path) != updated {
				t.Fatalf("second startup changed migrated settings: %v, %v", changes, err)
			}
		})
	}
}

func TestRaidClearOldTemplateDoesNotCreateConfig(t *testing.T) {
	root := t.TempDir()
	writeFixture(t, filepath.Join(root, "configs/modules/mod_raid_clear.conf.dist"), "[worldserver]\nRaidClear.Enable = 1\n")
	writeFixture(t, filepath.Join(root, "configs/modules/playerbots.conf.dist"), "[worldserver]\nRaidClear.Enable = 1\n")
	if err := ensureConfigFiles(root, root, "", defaultTestOptions()); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(root, "configs/modules/mod_raid_clear.conf")); !os.IsNotExist(err) {
		t.Fatalf("obsolete raid config was seeded: %v", err)
	}
	if value, _ := configValue(readFixture(t, filepath.Join(root, "configs/modules/playerbots.conf")), "RaidClear.Bots.TeachTranquilizingShot"); value != "0" {
		t.Fatalf("missing earned spell-learning default: %q", value)
	}
}

func TestRaidClearMigrationRefusesLinkedLegacyConfigBeforeWriting(t *testing.T) {
	root := t.TempDir()
	original := "[worldserver]\nCustom = 7\n"
	path := writeFixture(t, filepath.Join(root, "configs/modules/playerbots.conf"), original)
	external := writeFixture(t, filepath.Join(t.TempDir(), "raid.conf"), "RaidClear.Enable = 0\n")
	if err := os.Symlink(external, filepath.Join(root, "configs/modules/mod_raid_clear.conf")); err != nil {
		t.Skipf("symlinks unavailable: %v", err)
	}
	if _, err := migrateConfigProfiles(root); err == nil || !strings.Contains(err.Error(), "symbolic link") {
		t.Fatalf("linked legacy config accepted: %v", err)
	}
	if readFixture(t, path) != original || readFixture(t, external) != "RaidClear.Enable = 0\n" {
		t.Fatal("refused migration changed user settings")
	}
}
