//go:build windows

package main

import (
	"os"
	"path/filepath"
	"syscall"
	"testing"
)

func TestAutoBalanceRemovalRollsBackWhenTemplateIsLocked(t *testing.T) {
	root := t.TempDir()
	config := writeFixture(t, filepath.Join(root, "configs/modules/AutoBalance.conf"), "custom settings\r\n")
	template := writeFixture(t, config+".dist", "template\r\n")
	baseline := `{"schema":1,"profiles":{"AutoBalance.conf":"AutoBalance.Enable.Global = 1\n"}}`
	state := writeFixture(t, filepath.Join(root, "configs/"+automaticProfileState), baseline)
	path, err := syscall.UTF16PtrFromString(template)
	if err != nil {
		t.Fatal(err)
	}
	handle, err := syscall.CreateFile(path, syscall.GENERIC_READ, syscall.FILE_SHARE_READ|syscall.FILE_SHARE_WRITE,
		nil, syscall.OPEN_EXISTING, syscall.FILE_ATTRIBUTE_NORMAL, 0)
	if err != nil {
		t.Fatal(err)
	}
	locked := true
	t.Cleanup(func() {
		if locked {
			syscall.CloseHandle(handle)
		}
	})
	backups, err := migrateConfigProfiles(root)
	if err == nil || len(backups) != 2 {
		t.Fatalf("locked template did not stop removal after saving backups: %v, %v", backups, err)
	}
	for path, want := range map[string]string{config: "custom settings\r\n", template: "template\r\n", state: baseline} {
		if readFixture(t, path) != want {
			t.Fatalf("failed removal changed %s", path)
		}
	}
	if err := syscall.CloseHandle(handle); err != nil {
		t.Fatal(err)
	}
	locked = false
	if _, err := migrateConfigProfiles(root); err != nil {
		t.Fatalf("released template prevented removal retry: %v", err)
	}
	for _, path := range []string{config, template} {
		if _, err := os.Stat(path); !os.IsNotExist(err) {
			t.Fatalf("retired configuration remains after retry: %s, %v", path, err)
		}
	}
}

func TestRaidClearMigrationRollsBackWhenPlayerbotsConfigIsLocked(t *testing.T) {
	root := t.TempDir()
	legacy := writeFixture(t, filepath.Join(root, "configs/modules/mod_raid_clear.conf"), "RaidClear.Enable = 0\r\n")
	template := writeFixture(t, legacy+".dist", "RaidClear.Enable = 1\r\n")
	original := "[worldserver]\r\nCustom = 7\r\n"
	config := writeFixture(t, filepath.Join(root, "configs/modules/playerbots.conf"), original)
	baseline := `{"schema":1,"profiles":{"mod_raid_clear.conf":"RaidClear.Bots.TeachTranquilizingShot = 0\n"}}`
	state := writeFixture(t, filepath.Join(root, "configs/"+automaticProfileState), baseline)
	path, err := syscall.UTF16PtrFromString(config)
	if err != nil {
		t.Fatal(err)
	}
	handle, err := syscall.CreateFile(path, syscall.GENERIC_READ, syscall.FILE_SHARE_READ|syscall.FILE_SHARE_WRITE,
		nil, syscall.OPEN_EXISTING, syscall.FILE_ATTRIBUTE_NORMAL, 0)
	if err != nil {
		t.Fatal(err)
	}
	locked := true
	t.Cleanup(func() {
		if locked {
			syscall.CloseHandle(handle)
		}
	})
	if backups, err := migrateConfigProfiles(root); err == nil || len(backups) != 2 {
		t.Fatalf("locked playerbots config did not stop migration after backups: %v, %v", backups, err)
	}
	for path, want := range map[string]string{legacy: "RaidClear.Enable = 0\r\n", template: "RaidClear.Enable = 1\r\n", config: original, state: baseline} {
		if readFixture(t, path) != want {
			t.Fatalf("failed migration changed %s", path)
		}
	}
	if err := syscall.CloseHandle(handle); err != nil {
		t.Fatal(err)
	}
	locked = false
	if _, err := migrateConfigProfiles(root); err != nil {
		t.Fatalf("released config prevented migration retry: %v", err)
	}
	if value, _ := configValue(readFixture(t, config), "RaidClear.Enable"); value != "0" {
		t.Fatalf("retry lost the legacy raid switch: %q", value)
	}
}
