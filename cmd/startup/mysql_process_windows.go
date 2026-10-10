//go:build windows

package main

import (
	"encoding/binary"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"unsafe"
)

// mysqlProcessEntry mirrors Windows PROCESSENTRY32W.
type mysqlProcessEntry struct {
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

func ownsMySQLListener(port int, process *os.Process) (bool, error) {
	if process == nil || process.Pid <= 0 || port <= 0 || port > 65535 {
		return false, nil
	}
	getExtendedTCPTable := syscall.NewLazyDLL("iphlpapi.dll").NewProc("GetExtendedTcpTable")
	const (
		afInet                   = 2
		tcpTableOwnerPIDListener = 3
		errorInsufficientBuffer  = 122
	)
	var size uint32
	status, _, _ := getExtendedTCPTable.Call(0, uintptr(unsafe.Pointer(&size)), 0, afInet, tcpTableOwnerPIDListener, 0)
	if status != errorInsufficientBuffer {
		return false, fmt.Errorf("GetExtendedTcpTable size: %w", syscall.Errno(status))
	}
	for attempts := 0; attempts < 3; attempts++ {
		if size < 4 || size > 16<<20 {
			return false, fmt.Errorf("invalid TCP table size %d", size)
		}
		buffer := make([]byte, size)
		status, _, _ = getExtendedTCPTable.Call(uintptr(unsafe.Pointer(&buffer[0])), uintptr(unsafe.Pointer(&size)), 0, afInet, tcpTableOwnerPIDListener, 0)
		if status == errorInsufficientBuffer {
			continue
		}
		if status != 0 {
			return false, fmt.Errorf("GetExtendedTcpTable: %w", syscall.Errno(status))
		}
		count := binary.LittleEndian.Uint32(buffer[:4])
		const rowSize = 24
		if uint64(count)*rowSize+4 > uint64(len(buffer)) {
			return false, fmt.Errorf("invalid TCP listener count %d", count)
		}
		for i := uint32(0); i < count; i++ {
			row := buffer[4+int(i)*rowSize : 4+int(i+1)*rowSize]
			if binary.LittleEndian.Uint32(row[:4]) != 2 ||
				binary.LittleEndian.Uint32(row[4:8]) != 0x0100007f ||
				binary.BigEndian.Uint16(row[8:10]) != uint16(port) {
				continue
			}

			listenerPID := binary.LittleEndian.Uint32(row[20:24])
			if listenerPID == uint32(process.Pid) {
				return true, nil
			}
			// Windows MySQL can spawn another mysqld.exe process to own the
			// listener. Only accept it if it descends from the launcher-owned
			// process AND runs the very same executable.
			return isOwnedMySQLDescendant(uint32(process.Pid), listenerPID)
		}
		return false, nil
	}
	return false, fmt.Errorf("TCP table changed repeatedly during ownership check")
}

func isOwnedMySQLDescendant(launchedPID, listenerPID uint32) (bool, error) {
	dll := syscall.NewLazyDLL("kernel32.dll")
	createSnapshot := dll.NewProc("CreateToolhelp32Snapshot")
	first := dll.NewProc("Process32FirstW")
	next := dll.NewProc("Process32NextW")
	closeHandle := dll.NewProc("CloseHandle")
	const snapshotProcesses = 0x00000002

	snapshot, _, err := createSnapshot.Call(snapshotProcesses, 0)
	if snapshot == ^uintptr(0) {
		return false, fmt.Errorf("CreateToolhelp32Snapshot: %w", err)
	}
	defer closeHandle.Call(snapshot)

	parents := make(map[uint32]uint32)
	entry := mysqlProcessEntry{Size: uint32(unsafe.Sizeof(mysqlProcessEntry{}))}
	ok, _, err := first.Call(snapshot, uintptr(unsafe.Pointer(&entry)))
	if ok == 0 {
		return false, fmt.Errorf("Process32FirstW: %w", err)
	}
	for ok != 0 {
		parents[entry.ProcessID] = entry.ParentProcessID
		ok, _, _ = next.Call(snapshot, uintptr(unsafe.Pointer(&entry)))
	}

	// Follow a bounded parent chain: never accept unrelated processes or
	// a stale PID that is no longer present in the snapshot.
	seen := make(map[uint32]bool)
	descendant := false
	for pid := listenerPID; pid != 0 && !seen[pid]; {
		if pid == launchedPID {
			descendant = true
			break
		}
		seen[pid] = true
		parent, exists := parents[pid]
		if !exists || parent == pid {
			break
		}
		pid = parent
	}
	if !descendant {
		return false, nil
	}

	launchedImage, err := mysqlProcessImage(launchedPID)
	if err != nil {
		return false, fmt.Errorf("verify launched MySQL executable: %w", err)
	}
	listenerImage, err := mysqlProcessImage(listenerPID)
	if err != nil {
		return false, fmt.Errorf("verify listening MySQL executable: %w", err)
	}
	return strings.EqualFold(filepath.Clean(launchedImage), filepath.Clean(listenerImage)), nil
}

func mysqlProcessImage(pid uint32) (string, error) {
	dll := syscall.NewLazyDLL("kernel32.dll")
	openProcess := dll.NewProc("OpenProcess")
	queryImage := dll.NewProc("QueryFullProcessImageNameW")
	closeHandle := dll.NewProc("CloseHandle")
	const processQueryLimitedInformation = 0x1000

	handle, _, err := openProcess.Call(processQueryLimitedInformation, 0, uintptr(pid))
	if handle == 0 {
		return "", fmt.Errorf("OpenProcess(%d): %w", pid, err)
	}
	defer closeHandle.Call(handle)

	var image [32768]uint16
	length := uint32(len(image))
	ok, _, err := queryImage.Call(handle, 0, uintptr(unsafe.Pointer(&image[0])), uintptr(unsafe.Pointer(&length)))
	if ok == 0 || length == 0 {
		return "", fmt.Errorf("QueryFullProcessImageNameW(%d): %w", pid, err)
	}
	return syscall.UTF16ToString(image[:length]), nil
}
