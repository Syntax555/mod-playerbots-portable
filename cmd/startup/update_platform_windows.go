//go:build windows

package main

import (
	"errors"
	"fmt"
	"os"
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

func transientUpdateFileError(err error) bool {
	const errorSharingViolation, errorLockViolation = syscall.Errno(32), syscall.Errno(33)
	var errno syscall.Errno
	return errors.As(err, &errno) && (errno == syscall.ERROR_ACCESS_DENIED || errno == errorSharingViolation || errno == errorLockViolation)
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

// portableUpdateProcessPath reports whether executable lies inside root.
// Windows reports image paths in long form with links resolved, while root
// keeps the spelling it was started with, for example 8.3 short names or a
// junction. Folders that differ in spelling are compared by file identity.
func portableUpdateProcessPath(root, executable string) bool {
	rel, err := filepath.Rel(strings.ToLower(root), strings.ToLower(executable))
	if err == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return true
	}
	rootInfo, err := os.Stat(root)
	if err != nil {
		return false
	}
	for folder := filepath.Dir(executable); ; folder = filepath.Dir(folder) {
		if info, err := os.Stat(folder); err == nil && os.SameFile(info, rootInfo) {
			return true
		}
		if filepath.Dir(folder) == folder {
			return false
		}
	}
}
