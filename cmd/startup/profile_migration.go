package main

import (
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// Explicit new keys take precedence over their legacy aliases. Keep colliding
// values as comments, and leave duplicate order intact for the server's first-
// assignment-wins parser.
func migratePlayerbotsKeys(content string) string {
	const legacy = "AiPlayerbot."
	const current = "Playerbots."
	if !strings.Contains(content, legacy) {
		return content
	}
	explicit := make(map[string]bool)
	for key := range configAssignments(content) {
		if strings.HasPrefix(key, current) {
			explicit[key] = true
		}
	}
	lines := strings.Split(content, "\n")
	for i, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" || trimmed[0] == '#' || trimmed[0] == '[' {
			continue
		}
		key, _, assignment := strings.Cut(trimmed, "=")
		key = strings.TrimSpace(key)
		if !assignment || !strings.HasPrefix(key, legacy) {
			continue
		}
		renamed := current + strings.TrimPrefix(key, legacy)
		lines[i] = strings.Replace(line, key, renamed, 1)
		if explicit[renamed] {
			lines[i] = "# " + lines[i]
		}
	}
	return strings.Join(lines, "\n")
}

// Port overrides are applied only while creating a missing configuration.
// Existing credentials, hosts and databases in its template are preserved.
func applyRuntimePorts(filename, content string, opts startupOptions) (string, error) {
	var settings []string
	seen := make(map[string]bool)
	for key, value := range configAssignments(content) {
		switch key {
		case "LoginDatabaseInfo", "WorldDatabaseInfo", "CharacterDatabaseInfo", "PlayerbotsDatabaseInfo":
			if seen[key] {
				continue
			}
			seen[key] = true
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

// The servers read their ports from the active configs, while the port flags
// only seed new configs. Follow the configs so mysqld, the readiness checks and
// the servers agree.
//
// applyConfiguredMySQLPort runs before missing configs are created, so a
// regenerated config receives the port its realm already uses. An explicit
// --port still selects the MySQL port.
func applyConfiguredMySQLPort(workDir string, opts *startupOptions) {
	port, file, ok := configuredMySQLPort(workDir)
	if !ok || port == opts.port {
		return
	}
	if opts.portSet {
		fmt.Fprintf(os.Stderr, "Warning: --port %d differs from the LoginDatabaseInfo port %d in %s.\n", opts.port, port, file)
		return
	}
	opts.port = port
}

// applyConfiguredAuthPort reads the authserver listener once its config exists
// and returns the addresses on which authserver accepts connections.
func applyConfiguredAuthPort(workDir string, opts *startupOptions) ([]string, error) {
	hosts, port, err := configuredListener(workDir, "authserver.conf", "RealmServerPort", 3724)
	if err != nil {
		return nil, err
	}
	if opts.authPortSet && port != opts.authPort {
		fmt.Fprintf(os.Stderr, "Warning: --auth-port %d applies only to new configs; authserver.conf uses port %d.\n", opts.authPort, port)
	}
	opts.authPort = port
	return hosts, nil
}

// configuredMySQLPort returns the LoginDatabaseInfo port of the first existing
// authserver.conf or worldserver.conf that sets it, when that connection
// addresses this computer, where the launcher runs its MySQL server.
func configuredMySQLPort(workDir string) (int, string, bool) {
	for _, file := range []string{"authserver.conf", "worldserver.conf"} {
		content, err := os.ReadFile(filepath.Join(workDir, "configs", file))
		if err != nil {
			continue
		}
		value, exists := configValue(string(content), "LoginDatabaseInfo")
		if !exists {
			continue
		}
		parts := strings.Split(strings.ReplaceAll(value, `"`, ""), ";")
		if len(parts) < 5 {
			return 0, "", false
		}
		switch strings.ToLower(strings.TrimSpace(parts[0])) {
		case "127.0.0.1", "localhost", "::1":
		default:
			return 0, "", false
		}
		port, err := strconv.Atoi(strings.TrimSpace(parts[1]))
		if err != nil || port < 1 || port > 65535 {
			return 0, "", false
		}
		return port, file, true
	}
	return 0, "", false
}

type profileUpdate struct {
	path     string
	original []byte
	updated  []byte
	mode     os.FileMode
	backup   string // empty for launcher state, which rollback restores from memory
	create   bool
	remove   bool
}

// backupTimestamp names the backups written by one configuration change.
func backupTimestamp() string {
	return time.Now().UTC().Format("20060102T150405.000000000Z")
}

// readConfigForUpdate reads a configuration that a transaction may replace,
// with its permissions. Symbolic links in the path are refused, so an update
// never replaces a link or writes outside the installation.
func readConfigForUpdate(root, path string) (original []byte, mode os.FileMode, exists bool, err error) {
	if err := requireRegularConfigPath(root, path); err != nil {
		return nil, 0, false, err
	}
	file, err := os.Open(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil, 0, false, nil
	}
	if err != nil {
		return nil, 0, false, err
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil {
		return nil, 0, false, err
	}
	original, err = io.ReadAll(file)
	if err != nil {
		return nil, 0, false, err
	}
	return original, info.Mode().Perm(), true, nil
}

func applyProfileUpdates(updates []profileUpdate) ([]string, error) {
	var backups []string
	for _, update := range updates {
		if update.create || update.backup == "" {
			continue
		}
		if err := writeConfigBackup(update.backup, update.original, update.mode); err != nil {
			return backups, err
		}
		backups = append(backups, update.backup)
	}
	for i, update := range updates {
		var err error
		if update.remove {
			err = os.Remove(update.path)
		} else {
			err = writeConfigAtomically(update.path, update.updated, update.mode)
		}
		if err != nil {
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
