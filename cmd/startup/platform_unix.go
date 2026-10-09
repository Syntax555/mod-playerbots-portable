//go:build !windows

package main

import (
	"os"
	"os/exec"
	"syscall"
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

func getTotalRAMBytes() uint64 {
	return 0
}

func isPackagedApp() bool {
	return false
}
