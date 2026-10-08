//go:build windows

package main

import (
	"errors"
	"fmt"
	"path/filepath"
	"strings"
	"syscall"
	"unsafe"
)

func syncUpdateDirectory(directory string) error {
	// Files and the journal are flushed with File.Sync. Windows does not offer
	// portable directory fsync through os.File; the write-ahead journal handles
	// interrupted rename sequences when the launcher starts again.
	return nil
}

type updateProcessEntry struct {
	Size            uint32
	Usage           uint32
	ProcessID       uint32
	DefaultHeapID   uintptr
	ModuleID        uint32
	Threads         uint32
	ParentProcessID uint32
	BasePriority    int32
	Flags           uint32
	Executable      [260]uint16
}

func ensurePortableUpdateStopped(root string, excludedPID int) error {
	dll := syscall.NewLazyDLL("kernel32.dll")
	createSnapshot := dll.NewProc("CreateToolhelp32Snapshot")
	first := dll.NewProc("Process32FirstW")
	next := dll.NewProc("Process32NextW")
	openProcess := dll.NewProc("OpenProcess")
	queryImage := dll.NewProc("QueryFullProcessImageNameW")
	closeHandle := dll.NewProc("CloseHandle")
	const snapshotProcesses = 0x00000002
	const queryLimited = 0x1000
	snapshot, _, _ := createSnapshot.Call(snapshotProcesses, 0)
	if snapshot == ^uintptr(0) {
		return errors.New("cannot inspect running processes before update")
	}
	defer closeHandle.Call(snapshot)
	entry := updateProcessEntry{Size: uint32(unsafe.Sizeof(updateProcessEntry{}))}
	result, _, _ := first.Call(snapshot, uintptr(unsafe.Pointer(&entry)))
	for result != 0 {
		name := strings.ToLower(syscall.UTF16ToString(entry.Executable[:]))
		if int(entry.ProcessID) != excludedPID && (name == "authserver.exe" || name == "worldserver.exe" || name == "mysqld.exe" || name == "startup.exe") {
			handle, _, _ := openProcess.Call(queryLimited, 0, uintptr(entry.ProcessID))
			if handle == 0 {
				return fmt.Errorf("cannot verify that %s is outside this installation; stop it before updating", name)
			}
			var image [32768]uint16
			length := uint32(len(image))
			ok, _, _ := queryImage.Call(handle, 0, uintptr(unsafe.Pointer(&image[0])), uintptr(unsafe.Pointer(&length)))
			closeHandle.Call(handle)
			if ok == 0 || portableUpdateProcessPath(root, syscall.UTF16ToString(image[:length])) {
				return fmt.Errorf("%s is running; stop the realm and MySQL before updating", name)
			}
		}
		result, _, _ = next.Call(snapshot, uintptr(unsafe.Pointer(&entry)))
	}
	return ensureRealmStopped(root)
}

func portableUpdateProcessPath(root, executable string) bool {
	rel, err := filepath.Rel(strings.ToLower(root), strings.ToLower(executable))
	return err == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator))
}
