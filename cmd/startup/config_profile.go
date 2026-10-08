package main

import (
	"embed"
	"errors"
	"fmt"
	"io/fs"
	"strings"
)

// Missing configs receive these embedded profiles automatically. Existing
// configs follow changed defaults only while their managed values are unchanged.
//
//go:embed profiles/*.conf
var configProfiles embed.FS

type configAssignment struct {
	key   string
	value string
}

func parseConfigAssignments(profile string) ([]configAssignment, error) {
	var assignments []configAssignment
	seen := make(map[string]bool)
	for i, line := range strings.Split(profile, "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		// AzerothCore module templates share the worldserver section. The
		// distributed source template supplies it; profiles only merge settings.
		if line == "[worldserver]" {
			continue
		}
		key, value, ok := strings.Cut(line, "=")
		key = strings.TrimSpace(key)
		value = strings.TrimSpace(value)
		if !ok || key == "" || value == "" || seen[key] {
			return nil, fmt.Errorf("invalid or duplicate profile setting on line %d", i+1)
		}
		seen[key] = true
		assignments = append(assignments, configAssignment{key, value})
	}
	return assignments, nil
}

func mergeConfigProfile(content, profile string) (string, error) {
	assignments, err := parseConfigAssignments(profile)
	if err != nil {
		return "", err
	}
	values := make(map[string]string, len(assignments))
	for _, assignment := range assignments {
		values[assignment.key] = assignment.value
	}

	newline := "\n"
	if strings.Contains(content, "\r\n") {
		newline = "\r\n"
	}
	lines := strings.Split(strings.ReplaceAll(content, "\r\n", "\n"), "\n")
	seen := make(map[string]bool, len(assignments))
	for i, line := range lines {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "#") {
			continue
		}
		key, _, ok := strings.Cut(trimmed, "=")
		key = strings.TrimSpace(key)
		if value, exists := values[key]; ok && exists {
			lines[i] = key + " = " + value
			seen[key] = true
		}
	}
	result := strings.Join(lines, newline)
	var missing []string
	for _, assignment := range assignments {
		if !seen[assignment.key] {
			missing = append(missing, assignment.key+" = "+assignment.value)
		}
	}
	if len(missing) > 0 {
		if !strings.HasSuffix(result, newline) {
			result += newline
		}
		result += newline + "# Portable server recommended settings." + newline
		result += strings.Join(missing, newline) + newline
	}
	return result, nil
}

func applyConfigProfile(filename, content string) (string, error) {
	filename = strings.TrimSuffix(filename, ".dist")
	profile, err := configProfiles.ReadFile("profiles/" + filename)
	if err != nil {
		if !fs.ValidPath(filename) || !strings.HasSuffix(filename, ".conf") {
			return "", fmt.Errorf("invalid config filename %q", filename)
		}
		if errors.Is(err, fs.ErrNotExist) {
			return content, nil
		}
		return "", fmt.Errorf("read config profile for %s: %w", filename, err)
	}
	result, err := mergeConfigProfile(content, string(profile))
	if err != nil {
		return "", fmt.Errorf("apply config profile for %s: %w", filename, err)
	}
	return result, nil
}
