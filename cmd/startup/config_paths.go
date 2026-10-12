package main

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// Server processes run in workDir, so a relative SQL path keeps a portable
// installation usable when its containing directory is renamed or moved.
func portableSourceDirectory(baseDir, workDir string) string {
	source := filepath.Join(baseDir, "src")
	if !dirExists(source) {
		return "src"
	}
	if relative, err := filepath.Rel(workDir, source); err == nil {
		return filepath.ToSlash(relative)
	}
	// A separate work directory may be on another Windows drive.
	return filepath.ToSlash(source)
}

func hasBundledSQL(baseDir string) bool {
	for _, database := range []string{"db_auth", "db_world", "db_characters"} {
		for _, kind := range []string{"base", "updates"} {
			if !dirExists(filepath.Join(baseDir, "src", "data", "sql", kind, database)) {
				return false
			}
		}
	}
	return true
}

// Previous launchers wrote a clean, quoted absolute path ending in /src.
// Restrict automatic recovery to that representation, leaving manually chosen
// paths and ambiguous configurations alone.
func legacySourceDirectory(content string) (string, bool) {
	var value string
	count := 0
	for name, candidate := range configAssignments(content) {
		if name == "SourceDirectory" {
			value = candidate
			count++
		}
	}
	if count != 1 || len(value) < 3 || value[0] != '"' || value[len(value)-1] != '"' {
		return "", false
	}
	source := value[1 : len(value)-1]
	if !filepath.IsAbs(source) || strings.ContainsAny(source, "\\\"\x00") ||
		!strings.HasSuffix(source, "/src") || filepath.ToSlash(filepath.Clean(source)) != source {
		return "", false
	}
	return source, true
}

// Repair a missing SQL path left by moving an older portable installation.
// Existing paths remain administrator-owned, including valid external sources.
// Backups and rollback use the same transaction as managed config migration.
func relocatePortableSourcePaths(baseDir, workDir string) ([]string, error) {
	if !hasBundledSQL(baseDir) {
		return nil, nil
	}
	timestamp := backupTimestamp()
	var updates []profileUpdate
	for _, name := range []string{"authserver.conf", "worldserver.conf"} {
		path := filepath.Join(workDir, "configs", name)
		original, mode, exists, err := readConfigForUpdate(workDir, path)
		if err != nil {
			return nil, err
		}
		if !exists {
			continue
		}
		source, legacy := legacySourceDirectory(string(original))
		if !legacy {
			continue
		}
		if _, err := os.Stat(filepath.FromSlash(source)); !errors.Is(err, os.ErrNotExist) {
			continue
		}
		updated, err := mergeConfigProfile(string(original), fmt.Sprintf("SourceDirectory = %q", portableSourceDirectory(baseDir, workDir)))
		if err != nil {
			return nil, err
		}
		updates = append(updates, profileUpdate{path: path, original: original, updated: []byte(updated),
			mode: mode, backup: path + ".backup." + timestamp})
	}
	return applyProfileUpdates(updates)
}
