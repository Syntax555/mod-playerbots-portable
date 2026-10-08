//go:build !windows

package main

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

func syncUpdateDirectory(directory string) error {
	file, err := os.Open(directory)
	if err != nil {
		return err
	}
	defer file.Close()
	return file.Sync()
}

func ensurePortableUpdateStopped(root string, excludedPID int) error {
	entries, err := os.ReadDir("/proc")
	if err != nil {
		return errors.New("cannot inspect running processes before update")
	}
	for _, entry := range entries {
		pid, err := strconv.Atoi(entry.Name())
		if err != nil || pid == excludedPID {
			continue
		}
		executable, err := os.Readlink(filepath.Join("/proc", entry.Name(), "exe"))
		if err != nil {
			continue
		}
		if portableUpdateProcessPath(root, executable) {
			return fmt.Errorf("%s is running; stop the realm and MySQL before updating", filepath.Base(executable))
		}
	}
	return ensureRealmStopped(root)
}

func portableUpdateProcessPath(root, executable string) bool {
	name := strings.ToLower(filepath.Base(executable))
	if name != "worldserver" && name != "worldserver.exe" && name != "authserver" && name != "authserver.exe" && name != "mysqld" && name != "mysqld.exe" && name != "startup" && name != "startup.exe" {
		return false
	}
	rel, err := filepath.Rel(root, executable)
	return err == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator))
}
