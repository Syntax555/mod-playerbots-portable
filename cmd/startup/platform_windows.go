//go:build windows

package main

import (
	"os/exec"
	"syscall"
	"unsafe"
)

func configureConsoleProcess(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{
		CreationFlags: syscall.CREATE_NEW_PROCESS_GROUP,
	}
}

func isProcessAlive(pid int) (bool, uint32) {
	if pid <= 0 {
		return false, 0
	}

	kernel32 := syscall.NewLazyDLL("kernel32.dll")
	openProcess := kernel32.NewProc("OpenProcess")
	getExitCodeProcess := kernel32.NewProc("GetExitCodeProcess")
	waitForSingleObject := kernel32.NewProc("WaitForSingleObject")
	closeHandle := kernel32.NewProc("CloseHandle")

	const SYNCHRONIZE = 0x00100000
	const PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
	const WAIT_TIMEOUT = 258 // 0x102
	const STILL_ACTIVE = 259

	hProcess, _, _ := openProcess.Call(SYNCHRONIZE|PROCESS_QUERY_LIMITED_INFORMATION, 0, uintptr(pid))
	if hProcess == 0 {
		return false, 0
	}
	defer closeHandle.Call(hProcess)

	waitRet, _, _ := waitForSingleObject.Call(hProcess, 0)
	if waitRet == WAIT_TIMEOUT {
		return true, STILL_ACTIVE
	}

	var exitCode uint32
	ret, _, _ := getExitCodeProcess.Call(hProcess, uintptr(unsafe.Pointer(&exitCode)))
	if ret == 0 {
		return false, 0
	}
	return false, exitCode
}

type memoryStatusEx struct {
	cbSize                  uint32
	dwMemoryLoad            uint32
	ullTotalPhys            uint64
	ullAvailPhys            uint64
	ullTotalPageFile        uint64
	ullAvailPageFile        uint64
	ullTotalVirtual         uint64
	ullAvailVirtual         uint64
	ullAvailExtendedVirtual uint64
}

func getTotalRAMBytes() uint64 {
	kernel32 := syscall.NewLazyDLL("kernel32.dll")
	globalMemoryStatusEx := kernel32.NewProc("GlobalMemoryStatusEx")
	var mem memoryStatusEx
	mem.cbSize = uint32(unsafe.Sizeof(mem))
	ret, _, _ := globalMemoryStatusEx.Call(uintptr(unsafe.Pointer(&mem)))
	if ret == 0 {
		return 0
	}
	return mem.ullTotalPhys
}

var (
	kernel32                      = syscall.NewLazyDLL("kernel32.dll")
	procGetCurrentPackageFullName = kernel32.NewProc("GetCurrentPackageFullName")
)

const appModelErrorNoPackage = 15700

// isPackagedApp returns true if the process is running inside an MSIX/AppX package.
func isPackagedApp() bool {
	if err := procGetCurrentPackageFullName.Find(); err != nil {
		return false
	}
	var length uint32
	r1, _, _ := procGetCurrentPackageFullName.Call(
		uintptr(unsafe.Pointer(&length)),
		uintptr(0),
	)
	return r1 != uintptr(appModelErrorNoPackage)
}
