package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

const automaticProfileState = ".portable-profiles.json"

type managedProfileState struct {
	Schema   int               `json:"schema"`
	Profiles map[string]string `json:"profiles"`
}

// A saved default is a baseline, never a copy of the user's live configuration.
// Only values still matching that baseline follow a new recommended default.
func mergeManagedProfile(content, previous, current string) (string, error) {
	oldSettings, err := parseConfigAssignments(previous)
	if err != nil {
		return "", fmt.Errorf("invalid previous profile: %w", err)
	}
	newSettings, err := parseConfigAssignments(current)
	if err != nil {
		return "", fmt.Errorf("invalid current profile: %w", err)
	}
	old := make(map[string]string, len(oldSettings))
	for _, setting := range oldSettings {
		old[setting.key] = setting.value
	}
	var updates []string
	for _, setting := range newSettings {
		value, exists := configValue(content, setting.key)
		baseline, managed := old[setting.key]
		if !exists || (managed && value == baseline) {
			updates = append(updates, setting.key+" = "+setting.value)
		}
	}
	if len(updates) == 0 {
		return content, nil
	}
	return mergeConfigProfile(content, strings.Join(updates, "\n"))
}

func currentManagedProfiles(phase realmPhase) (map[string]string, error) {
	entries, err := configProfiles.ReadDir("profiles")
	if err != nil {
		return nil, err
	}
	profiles := make(map[string]string, len(entries))
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		content, err := configProfiles.ReadFile("profiles/" + entry.Name())
		if err != nil {
			return nil, err
		}
		effective := string(content)
		if overrides := phase.profile(entry.Name()); overrides != "" {
			effective, err = mergeConfigProfile(effective, overrides)
			if err != nil {
				return nil, err
			}
		}
		profiles[entry.Name()] = effective
	}
	return profiles, nil
}

func requireRegularConfigPath(root, path string) error {
	rootInfo, err := os.Lstat(root)
	if err != nil || !rootInfo.IsDir() || rootInfo.Mode()&os.ModeSymlink != 0 {
		return errors.New("installation root is not a real directory")
	}
	relative, err := filepath.Rel(root, path)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return errors.New("configuration path is outside the installation")
	}
	current := root
	for _, part := range strings.Split(relative, string(filepath.Separator)) {
		current = filepath.Join(current, part)
		info, err := os.Lstat(current)
		if errors.Is(err, os.ErrNotExist) {
			continue
		}
		if err != nil {
			return err
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return fmt.Errorf("configuration path contains a symbolic link: %s", current)
		}
		if current == path && !info.Mode().IsRegular() {
			return fmt.Errorf("configuration is not a regular file: %s", current)
		}
	}
	return nil
}

func readManagedProfileState(root string) (managedProfileState, []byte, error) {
	path := filepath.Join(root, "configs", automaticProfileState)
	if err := requireRegularConfigPath(root, path); err != nil {
		return managedProfileState{}, nil, err
	}
	file, err := os.Open(path)
	if errors.Is(err, os.ErrNotExist) {
		return managedProfileState{Schema: 1, Profiles: map[string]string{}}, nil, nil
	}
	if err != nil {
		return managedProfileState{}, nil, err
	}
	defer file.Close()
	raw, err := io.ReadAll(io.LimitReader(file, 1024*1024+1))
	if err != nil {
		return managedProfileState{}, nil, err
	}
	if len(raw) > 1024*1024 {
		return managedProfileState{}, nil, errors.New("profile baseline exceeds the supported size")
	}
	var state managedProfileState
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&state); err != nil {
		return state, nil, fmt.Errorf("read profile baseline: %w", err)
	}
	if decoder.Decode(new(any)) != io.EOF || state.Schema != 1 || state.Profiles == nil {
		return state, nil, errors.New("unsupported or invalid profile baseline")
	}
	for name, profile := range state.Profiles {
		if filepath.Base(name) != name || strings.ContainsAny(name, "/\\") || !strings.HasSuffix(name, ".conf") {
			return state, nil, errors.New("invalid filename in profile baseline")
		}
		if _, err := parseConfigAssignments(profile); err != nil {
			return state, nil, fmt.Errorf("invalid profile baseline for %s: %w", name, err)
		}
	}
	return state, raw, nil
}

func migrateConfigProfiles(root string) ([]string, error) {
	phase, err := loadRealmPhase(root)
	if err != nil {
		return nil, err
	}
	current, err := currentManagedProfiles(phase)
	if err != nil {
		return nil, err
	}
	previous, originalState, err := readManagedProfileState(root)
	if err != nil {
		return nil, err
	}
	// Exported profiles from older bundles may have been edited. Without our
	// saved baseline, preserve every existing value and only add missing keys.
	names := make([]string, 0, len(current))
	for name := range current {
		names = append(names, name)
	}
	sort.Strings(names)
	timestamp := time.Now().UTC().Format("20060102T150405.000000000Z")
	var updates []profileUpdate
	next := managedProfileState{Schema: 1, Profiles: make(map[string]string)}
	for _, name := range names {
		path := filepath.Join(root, "configs", "modules", name)
		if name == "worldserver.conf" {
			path = filepath.Join(root, "configs", name)
		}
		if err := requireRegularConfigPath(root, path); err != nil {
			return nil, err
		}
		original, err := os.ReadFile(path)
		if errors.Is(err, os.ErrNotExist) {
			continue
		}
		if err != nil {
			return nil, err
		}
		info, err := os.Stat(path)
		if err != nil {
			return nil, err
		}
		updated, err := mergeManagedProfile(string(original), previous.Profiles[name], current[name])
		if err != nil {
			return nil, fmt.Errorf("migrate %s: %w", name, err)
		}
		next.Profiles[name] = current[name]
		if updated != string(original) {
			updates = append(updates, profileUpdate{path: path, original: original, updated: []byte(updated),
				mode: info.Mode().Perm(), backup: path + ".backup." + timestamp})
		}
	}
	if len(next.Profiles) == 0 {
		return nil, nil
	}
	nextState, err := json.MarshalIndent(next, "", "  ")
	if err != nil {
		return nil, err
	}
	nextState = append(nextState, '\n')
	if !bytes.Equal(nextState, originalState) {
		path := filepath.Join(root, "configs", automaticProfileState)
		updates = append(updates, profileUpdate{path: path, original: originalState, updated: nextState,
			mode: 0600, backup: path + ".backup." + timestamp, create: originalState == nil})
	}
	return applyProfileUpdates(updates)
}
