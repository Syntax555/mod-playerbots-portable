package main

import (
	"errors"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

const realmPhaseFile = "realm-phase.txt"

type realmPhase struct {
	name  string
	level int
	limit int
	maps  string
}

func parseRealmPhase(name string) (realmPhase, error) {
	switch strings.ToLower(strings.TrimSpace(name)) {
	case "vanilla":
		return realmPhase{"vanilla", 60, 7, "0,1"}, nil
	case "tbc":
		return realmPhase{"tbc", 70, 12, "0,1,530"}, nil
	case "wotlk", "wrath":
		return realmPhase{"wotlk", 80, 0, "0,1,530,571"}, nil
	default:
		return realmPhase{}, fmt.Errorf("unknown expansion %q; choose vanilla, tbc or wotlk", name)
	}
}

// Templates contain sections and unrelated settings, so read just this key.
func configValue(content, key string) (string, bool) {
	var value string
	var found bool
	for _, line := range strings.Split(content, "\n") {
		name, candidate, ok := strings.Cut(strings.TrimSpace(line), "=")
		if ok && strings.TrimSpace(name) == key {
			value, found = strings.TrimSpace(candidate), true
		}
	}
	return value, found
}

func loadRealmPhase(workDir string) (realmPhase, error) {
	return detectRealmPhase(workDir, false)
}

func detectRealmPhase(workDir string, allowConflictingCaps bool) (realmPhase, error) {
	path := filepath.Join(workDir, "configs", realmPhaseFile)
	content, err := os.ReadFile(path)
	if err == nil {
		phase, err := parseRealmPhase(string(content))
		if err != nil {
			return realmPhase{}, fmt.Errorf("invalid %s: %w", path, err)
		}
		return phase, nil
	}
	if !errors.Is(err, os.ErrNotExist) {
		return realmPhase{}, err
	}

	// Recognize older realms upgraded manually. Refuse conflicting caps rather
	// than silently applying Vanilla defaults to an established later realm.
	var inferred realmPhase
	for _, setting := range []struct{ file, key string }{
		{"worldserver.conf", "MaxPlayerLevel"},
		{"modules/playerbots.conf", "AiPlayerbot.RandomBotMaxLevel"},
		{"modules/individualProgression.conf", "IndividualProgression.ProgressionLimit"},
	} {
		path := filepath.Join(workDir, "configs", filepath.FromSlash(setting.file))
		content, err := os.ReadFile(path)
		if errors.Is(err, os.ErrNotExist) {
			continue
		}
		if err != nil {
			return realmPhase{}, err
		}
		value, exists := configValue(string(content), setting.key)
		if !exists {
			continue
		}
		number, err := strconv.Atoi(value)
		if err != nil {
			return realmPhase{}, fmt.Errorf("invalid %s in %s", setting.key, path)
		}
		name := ""
		if setting.key == "IndividualProgression.ProgressionLimit" {
			switch {
			case number >= 1 && number <= 7:
				name = "vanilla"
			case number >= 8 && number <= 12:
				name = "tbc"
			case number == 0 || (number >= 13 && number <= 18):
				name = "wotlk"
			}
		} else {
			switch {
			case number >= 1 && number <= 60:
				name = "vanilla"
			case number >= 61 && number <= 70:
				name = "tbc"
			case number >= 71 && number <= 80:
				name = "wotlk"
			}
		}
		if name == "" {
			return realmPhase{}, fmt.Errorf("unsupported expansion setting %s = %s in %s", setting.key, value, path)
		}
		phase, _ := parseRealmPhase(name)
		if inferred.name != "" && inferred != phase {
			if !allowConflictingCaps {
				return realmPhase{}, errors.New("expansion caps disagree; run --set-expansion with the latest expansion already enabled before applying profiles")
			}
			if inferred.level > phase.level {
				continue
			}
		}
		inferred = phase
	}
	if inferred.name == "" {
		inferred, _ = parseRealmPhase("vanilla")
	}
	return inferred, nil
}

func (phase realmPhase) profile(filename string) string {
	switch strings.TrimSuffix(filename, ".dist") {
	case "worldserver.conf":
		raceMask, classMask, dualSpec := 1536, 32, 80
		if phase.level >= 70 {
			raceMask = 0
		}
		if phase.level == 80 {
			classMask, dualSpec = 0, 40
		}
		return fmt.Sprintf("Expansion = 2\nMaxPlayerLevel = %d\nCharacterCreating.Disabled.RaceMask = %d\nCharacterCreating.Disabled.ClassMask = %d\nMinDualSpecLevel = %d\n", phase.level, raceMask, classMask, dualSpec)
	case "individualProgression.conf":
		return fmt.Sprintf("IndividualProgression.Enable = 1\nIndividualProgression.ProgressionLimit = %d\nIndividualProgression.BotAccountsMaxLevel = %d\nIndividualProgression.StartingProgression = 0\nIndividualProgression.BotAccountsRegex = \"\"\nIndividualProgression.ExcludedAccountsRegex = \"\"\n", phase.limit, phase.level)
	case "playerbots.conf":
		return fmt.Sprintf("AiPlayerbot.RandomBotMaxLevel = %d\nAiPlayerbot.botActiveAloneSmartScaleWhenMaxLevel = %d\nAiPlayerbot.RandomBotMaps = %s\nAiPlayerbot.NaturalProgression = 1\n", phase.level, phase.level, phase.maps)
	}
	return ""
}

func applyConfigProfileForPhase(filename, content string, phase realmPhase) (string, error) {
	content, err := applyConfigProfile(filename, content)
	if err != nil {
		return "", err
	}
	if profile := phase.profile(filename); profile != "" {
		return mergeConfigProfile(content, profile)
	}
	return content, nil
}

func ensureRealmStopped(workDir string) error {
	for _, server := range []struct {
		file, key string
		port      int
	}{{"worldserver.conf", "WorldServerPort", 8085}, {"authserver.conf", "RealmServerPort", 3724}} {
		content, err := os.ReadFile(filepath.Join(workDir, "configs", server.file))
		if err != nil && !errors.Is(err, os.ErrNotExist) {
			return err
		}
		port := server.port
		if value, exists := configValue(string(content), server.key); exists {
			port, err = strconv.Atoi(value)
			if err != nil || port < 1 || port > 65535 {
				return fmt.Errorf("invalid %s in %s", server.key, server.file)
			}
		}
		hosts := []string{"127.0.0.1", "::1"}
		if value, exists := configValue(string(content), "BindIP"); exists {
			host := strings.Trim(value, "\"")
			if host != "" && host != "0.0.0.0" && host != "::" {
				hosts = append(hosts, host)
			}
		}
		for _, host := range hosts {
			conn, err := net.DialTimeout("tcp", net.JoinHostPort(host, strconv.Itoa(port)), 200*time.Millisecond)
			if err == nil {
				conn.Close()
				return fmt.Errorf("%s is listening on port %d; stop startup.exe and the realm servers before changing expansion settings", server.file, port)
			}
		}
	}
	return nil
}

func setRealmPhase(workDir string, phase realmPhase) ([]string, error) {
	if err := ensureRealmStopped(workDir); err != nil {
		return nil, err
	}
	current, err := detectRealmPhase(workDir, true)
	if err != nil {
		return nil, err
	}
	if phase.level < current.level {
		return nil, fmt.Errorf("cannot lower the realm from %s to %s; reverting requires a matching database and config backup", current.name, phase.name)
	}
	timestamp := time.Now().UTC().Format("20060102T150405.000000000Z")
	var updates []profileUpdate
	for _, relative := range []string{"worldserver.conf", "modules/individualProgression.conf", "modules/playerbots.conf", realmPhaseFile} {
		path := filepath.Join(workDir, "configs", filepath.FromSlash(relative))
		original, err := os.ReadFile(path)
		create := errors.Is(err, os.ErrNotExist) && relative == realmPhaseFile
		if err != nil && !create {
			return nil, fmt.Errorf("read %s: %w; initialize the realm configs with startup.exe before choosing an expansion", path, err)
		}
		mode := os.FileMode(0644)
		if !create {
			info, err := os.Stat(path)
			if err != nil {
				return nil, err
			}
			mode = info.Mode().Perm()
		}
		updated := phase.name + "\n"
		if relative != realmPhaseFile {
			updated, err = mergeConfigProfile(string(original), phase.profile(filepath.Base(relative)))
			if err != nil {
				return nil, err
			}
		}
		if !create && updated == string(original) {
			continue
		}
		updates = append(updates, profileUpdate{path: path, original: original, updated: []byte(updated), mode: mode, backup: path + ".backup." + timestamp, create: create})
	}
	return applyProfileUpdates(updates)
}
