//go:build windows

package main

import (
	"encoding/binary"
	"fmt"
	"os"
	"syscall"
	"unsafe"
)

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
			if binary.LittleEndian.Uint32(row[:4]) == 2 &&
				binary.LittleEndian.Uint32(row[4:8]) == 0x0100007f &&
				binary.BigEndian.Uint16(row[8:10]) == uint16(port) &&
				binary.LittleEndian.Uint32(row[20:24]) == uint32(process.Pid) {
				return true, nil
			}
		}
		return false, nil
	}
	return false, fmt.Errorf("TCP table changed repeatedly during ownership check")
}
