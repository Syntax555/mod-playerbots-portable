//go:build windows

package main

import (
	"fmt"
	"os"
	"os/exec"
	"syscall"
	"unsafe"
)

func configureConsoleProcess(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{
		CreationFlags: syscall.CREATE_NEW_PROCESS_GROUP,
	}
}

func enableConsoleInterrupt() error {
	// CREATE_NEW_PROCESS_GROUP disables Ctrl+C, including for a launcher
	// restarted by the update helper. Registering a Go signal handler does
	// not clear that inherited flag. Only the normal launcher enables it;
	// the atomic update helper remains protected from interruption.
	setConsoleCtrlHandler := kernel32.NewProc("SetConsoleCtrlHandler")
	ret, _, err := setConsoleCtrlHandler.Call(0, 0)
	if ret == 0 {
		return fmt.Errorf("SetConsoleCtrlHandler: %w", err)
	}
	return nil
}

func interruptConsoleProcess(process *os.Process) error {
	if process == nil || process.Pid <= 0 {
		return os.ErrProcessDone
	}
	// CTRL_BREAK reaches only this owned process group; CTRL_C cannot be
	// directed at one group. AzerothCore handles SIGBREAK as a normal stop.
	generateConsoleCtrlEvent := kernel32.NewProc("GenerateConsoleCtrlEvent")
	ret, _, err := generateConsoleCtrlEvent.Call(syscall.CTRL_BREAK_EVENT, uintptr(process.Pid))
	if ret == 0 {
		return fmt.Errorf("GenerateConsoleCtrlEvent: %w", err)
	}
	return nil
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
