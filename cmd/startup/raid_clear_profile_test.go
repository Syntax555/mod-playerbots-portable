package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRaidClearProfileKeepsSpellLearningEarned(t *testing.T) {
	const key = "RaidClear.Bots.TeachTranquilizingShot"
	fresh, err := applyConfigProfile("mod_raid_clear.conf.dist", "[worldserver]\n"+key+" = 1\n")
	if err != nil {
		t.Fatal(err)
	}
	if value, ok := configValue(fresh, key); !ok || value != "0" {
		t.Fatalf("fresh raid profile grants spells: %q", fresh)
	}
	for _, existing := range []string{"", key + " = 0\n", key + " = 1\n"} {
		t.Run(strings.TrimSpace(existing), func(t *testing.T) {
			root := t.TempDir()
			path := writeFixture(t, filepath.Join(root, "configs/modules/mod_raid_clear.conf"), "[worldserver]\n"+existing+"Custom = 7\n")
			if _, err := migrateConfigProfiles(root); err != nil {
				t.Fatal(err)
			}
			current, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			want := "0"
			if strings.Contains(existing, " = 1") {
				want = "1"
			}
			if value, ok := configValue(string(current), key); !ok || value != want || !strings.Contains(string(current), "Custom = 7\n") {
				t.Fatalf("raid config migration lost defaults or user values: %q", current)
			}
			if changes, err := migrateConfigProfiles(root); err != nil || len(changes) != 0 {
				t.Fatalf("raid config migration is not idempotent: %v, %v", changes, err)
			}
		})
	}
}
