//go:build !windows

package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"syscall"
	"time"
)

func configureConsoleProcess(cmd *exec.Cmd) {}

func enableConsoleInterrupt() error { return nil }

func interruptConsoleProcess(process *os.Process) error {
	if process == nil {
		return os.ErrProcessDone
	}
	return process.Signal(os.Interrupt)
}

func isProcessAlive(pid int) (bool, uint32) {
	if pid <= 0 {
		return false, 0
	}
	p, err := os.FindProcess(pid)
	if err != nil {
		return false, 0
	}
	defer p.Release()
	return p.Signal(syscall.Signal(0)) == nil, 0
}

// processExecutable returns the program file of a running process. It returns
// os.ErrProcessDone when pid names no process that this user can observe.
func processExecutable(pid int) (string, error) {
	if alive, _ := isProcessAlive(pid); !alive {
		return "", os.ErrProcessDone
	}
	return os.Readlink(filepath.Join("/proc", strconv.Itoa(pid), "exe"))
}

func watchProcessExit(pid int) func(timeout time.Duration) bool {
	return func(timeout time.Duration) bool { return pollProcessExit(pid, timeout) }
}

func getTotalRAMBytes() uint64 {
	return 0
}

func isPackagedApp() bool {
	return false
}
