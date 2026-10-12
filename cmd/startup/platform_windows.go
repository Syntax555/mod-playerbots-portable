//go:build windows

package main

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"syscall"
	"time"
	"unsafe"
)

// The syscall package covers process handles and Toolhelp snapshots. These
// procedures are the remaining kernel32 calls; resolve them once.
var (
	kernel32                       = syscall.NewLazyDLL("kernel32.dll")
	procSetConsoleCtrlHandler      = kernel32.NewProc("SetConsoleCtrlHandler")
	procGenerateConsoleCtrlEvent   = kernel32.NewProc("GenerateConsoleCtrlEvent")
	procGetConsoleProcessList      = kernel32.NewProc("GetConsoleProcessList")
	procGlobalMemoryStatusEx       = kernel32.NewProc("GlobalMemoryStatusEx")
	procGetCurrentPackageFullName  = kernel32.NewProc("GetCurrentPackageFullName")
	procQueryFullProcessImageNameW = kernel32.NewProc("QueryFullProcessImageNameW")
)

const (
	processQueryLimitedInformation = 0x1000
	stillActive                    = 259
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
	ret, _, err := procSetConsoleCtrlHandler.Call(0, 0)
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
	ret, _, err := procGenerateConsoleCtrlEvent.Call(syscall.CTRL_BREAK_EVENT, uintptr(process.Pid))
	if ret == 0 {
		return fmt.Errorf("GenerateConsoleCtrlEvent: %w", err)
	}
	return nil
}

func isProcessAlive(pid int) (bool, uint32) {
	if pid <= 0 {
		return false, 0
	}
	handle, err := syscall.OpenProcess(syscall.SYNCHRONIZE|processQueryLimitedInformation, false, uint32(pid))
	if err != nil {
		return false, 0
	}
	defer syscall.CloseHandle(handle)
	if status, err := syscall.WaitForSingleObject(handle, 0); err == nil && status == syscall.WAIT_TIMEOUT {
		return true, stillActive
	}
	var exitCode uint32
	if err := syscall.GetExitCodeProcess(handle, &exitCode); err != nil {
		return false, 0
	}
	return false, exitCode
}

// processExecutable returns the program file of a running process. It returns
// os.ErrProcessDone when pid names no process that this user can observe.
func processExecutable(pid int) (string, error) {
	if pid <= 0 {
		return "", os.ErrProcessDone
	}
	handle, err := syscall.OpenProcess(syscall.SYNCHRONIZE|processQueryLimitedInformation, false, uint32(pid))
	if err != nil {
		return "", os.ErrProcessDone
	}
	defer syscall.CloseHandle(handle)
	if status, err := syscall.WaitForSingleObject(handle, 0); err == nil && status != syscall.WAIT_TIMEOUT {
		return "", os.ErrProcessDone
	}
	return processImagePath(handle)
}

// watchProcessExit opens pid at once. The returned wait then observes that
// process even if Windows assigns its number to another process after it exits.
func watchProcessExit(pid int) func(timeout time.Duration) bool {
	handle, err := syscall.OpenProcess(syscall.SYNCHRONIZE, false, uint32(pid))
	if err != nil {
		return func(timeout time.Duration) bool { return pollProcessExit(pid, timeout) }
	}
	return func(timeout time.Duration) bool {
		defer syscall.CloseHandle(handle)
		status, err := syscall.WaitForSingleObject(handle, uint32(timeout.Milliseconds()))
		return err == nil && status == syscall.WAIT_OBJECT_0
	}
}

func processImagePath(handle syscall.Handle) (string, error) {
	var image [32768]uint16
	length := uint32(len(image))
	ok, _, err := procQueryFullProcessImageNameW.Call(uintptr(handle), 0,
		uintptr(unsafe.Pointer(&image[0])), uintptr(unsafe.Pointer(&length)))
	if ok == 0 || length == 0 || length > uint32(len(image)) {
		return "", fmt.Errorf("QueryFullProcessImageNameW: %w", err)
	}
	return syscall.UTF16ToString(image[:length]), nil
}

// forEachProcess walks one Toolhelp snapshot. Enumeration failures are
// returned rather than treated as the end of the process list.
func forEachProcess(visit func(*syscall.ProcessEntry32) error) error {
	snapshot, err := syscall.CreateToolhelp32Snapshot(syscall.TH32CS_SNAPPROCESS, 0)
	if err != nil {
		return fmt.Errorf("CreateToolhelp32Snapshot: %w", err)
	}
	defer syscall.CloseHandle(snapshot)
	entry := syscall.ProcessEntry32{Size: uint32(unsafe.Sizeof(syscall.ProcessEntry32{}))}
	if err := syscall.Process32First(snapshot, &entry); err != nil {
		return fmt.Errorf("Process32First: %w", err)
	}
	for {
		if err := visit(&entry); err != nil {
			return err
		}
		if err := syscall.Process32Next(snapshot, &entry); err != nil {
			if errors.Is(err, syscall.ERROR_NO_MORE_FILES) {
				return nil
			}
			return fmt.Errorf("Process32Next: %w", err)
		}
	}
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
	var mem memoryStatusEx
	mem.cbSize = uint32(unsafe.Sizeof(mem))
	ret, _, _ := procGlobalMemoryStatusEx.Call(uintptr(unsafe.Pointer(&mem)))
	if ret == 0 {
		return 0
	}
	return mem.ullTotalPhys
}

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
