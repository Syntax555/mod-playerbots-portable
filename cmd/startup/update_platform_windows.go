//go:build windows

package main

import (
	"fmt"
	"path/filepath"
	"strings"
	"syscall"
)

func syncUpdateDirectory(directory string) error {
	// Files and the journal are flushed with File.Sync. Windows does not offer
	// portable directory fsync through os.File; the write-ahead journal handles
	// interrupted rename sequences when the launcher starts again.
	return nil
}

func ensurePortableUpdateStopped(root string, excludedPID int) error {
	var running error
	err := forEachProcess(func(entry *syscall.ProcessEntry32) error {
		name := strings.ToLower(syscall.UTF16ToString(entry.ExeFile[:]))
		if int(entry.ProcessID) == excludedPID || (name != "authserver.exe" && name != "worldserver.exe" && name != "mysqld.exe" && name != "startup.exe") {
			return nil
		}
		handle, err := syscall.OpenProcess(processQueryLimitedInformation, false, entry.ProcessID)
		if err != nil {
			running = fmt.Errorf("cannot verify that %s is outside this installation; stop it before updating", name)
			return running
		}
		image, err := processImagePath(handle)
		syscall.CloseHandle(handle)
		if err != nil || portableUpdateProcessPath(root, image) {
			running = fmt.Errorf("%s is running; stop the realm and MySQL before updating", name)
			return running
		}
		return nil
	})
	if running != nil {
		return running
	}
	if err != nil {
		// Fail closed: an incomplete process list cannot show that the realm stopped.
		return fmt.Errorf("cannot inspect running processes before update: %w", err)
	}
	return ensureRealmStopped(root)
}

func portableUpdateProcessPath(root, executable string) bool {
	rel, err := filepath.Rel(strings.ToLower(root), strings.ToLower(executable))
	return err == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator))
}
