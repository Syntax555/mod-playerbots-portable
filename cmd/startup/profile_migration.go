package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// Port overrides are applied only while creating a missing configuration.
// Existing credentials, hosts and databases in its template are preserved.
func applyRuntimePorts(filename, content string, opts startupOptions) (string, error) {
	var settings []string
	for _, line := range strings.Split(content, "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "#") {
			continue
		}
		key, value, found := strings.Cut(line, "=")
		if !found {
			continue
		}
		key, value = strings.TrimSpace(key), strings.TrimSpace(value)
		switch key {
		case "LoginDatabaseInfo", "WorldDatabaseInfo", "CharacterDatabaseInfo", "PlayerbotsDatabaseInfo":
			if len(value) < 2 || value[0] != '"' || value[len(value)-1] != '"' {
				return "", fmt.Errorf("invalid quoted database connection in %s: %s", filename, key)
			}
			parts := strings.Split(value[1:len(value)-1], ";")
			if len(parts) < 5 {
				return "", fmt.Errorf("invalid database connection in %s: %s", filename, key)
			}
			parts[1] = strconv.Itoa(opts.port)
			settings = append(settings, key+" = \""+strings.Join(parts, ";")+"\"")
		}
	}
	if strings.TrimSuffix(filename, ".dist") == "authserver.conf" {
		settings = append(settings, "RealmServerPort = "+strconv.Itoa(opts.authPort))
	}
	if len(settings) == 0 {
		return content, nil
	}
	return mergeConfigProfile(content, strings.Join(settings, "\n"))
}

type profileUpdate struct {
	path     string
	original []byte
	updated  []byte
	mode     os.FileMode
	backup   string
	create   bool
}

func applyProfileUpdates(updates []profileUpdate) ([]string, error) {
	var backups []string
	for _, update := range updates {
		if update.create {
			continue
		}
		if err := writeConfigBackup(update.backup, update.original, update.mode); err != nil {
			return backups, err
		}
		backups = append(backups, update.backup)
	}
	for i, update := range updates {
		if err := writeConfigAtomically(update.path, update.updated, update.mode); err != nil {
			var rollbackErrors []string
			for _, previous := range updates[:i] {
				if previous.create {
					if restoreErr := os.Remove(previous.path); restoreErr != nil {
						rollbackErrors = append(rollbackErrors, previous.path+": "+restoreErr.Error())
					}
					continue
				}
				if restoreErr := writeConfigAtomically(previous.path, previous.original, previous.mode); restoreErr != nil {
					rollbackErrors = append(rollbackErrors, previous.path+": "+restoreErr.Error())
				}
			}
			if len(rollbackErrors) > 0 {
				return backups, fmt.Errorf("%w; rollback failed: %s; original settings remain in config backups", err, strings.Join(rollbackErrors, "; "))
			}
			return backups, err
		}
	}
	return backups, nil
}

func writeConfigBackup(path string, content []byte, mode os.FileMode) error {
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, mode)
	if err != nil {
		return fmt.Errorf("create config backup %s: %w", path, err)
	}
	if _, err := file.Write(content); err != nil {
		file.Close()
		os.Remove(path)
		return fmt.Errorf("write config backup %s: %w", path, err)
	}
	if err := file.Sync(); err != nil {
		file.Close()
		os.Remove(path)
		return fmt.Errorf("flush config backup %s: %w", path, err)
	}
	if err := file.Close(); err != nil {
		os.Remove(path)
		return fmt.Errorf("close config backup %s: %w", path, err)
	}
	return nil
}

func writeConfigAtomically(path string, content []byte, mode os.FileMode) error {
	file, err := os.CreateTemp(filepath.Dir(path), ".profile-update-")
	if err != nil {
		return fmt.Errorf("create temporary config for %s: %w", path, err)
	}
	temporary := file.Name()
	defer os.Remove(temporary)
	if err := file.Chmod(mode); err != nil {
		file.Close()
		return fmt.Errorf("set config permissions for %s: %w", path, err)
	}
	if _, err := file.Write(content); err != nil {
		file.Close()
		return fmt.Errorf("write temporary config for %s: %w", path, err)
	}
	if err := file.Sync(); err != nil {
		file.Close()
		return fmt.Errorf("flush temporary config for %s: %w", path, err)
	}
	if err := file.Close(); err != nil {
		return fmt.Errorf("close temporary config for %s: %w", path, err)
	}
	if err := os.Rename(temporary, path); err != nil {
		return fmt.Errorf("replace config %s: %w", path, err)
	}
	return nil
}
