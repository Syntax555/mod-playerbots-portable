//go:build windows

package main

import (
	"context"
	"os"
	"os/exec"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"
	"unsafe"
)

func attachedConsoleProcesses(t *testing.T) []uint32 {
	t.Helper()
	var ids [8]uint32
	count, _, err := kernel32.NewProc("GetConsoleProcessList").Call(uintptr(unsafe.Pointer(&ids[0])), uintptr(len(ids)))
	if count == 0 || count > uintptr(len(ids)) {
		t.Fatalf("private test console has invalid process count %d: %v", count, err)
	}
	return ids[:count]
}

func runProcessTestInPrivateConsole(t *testing.T) bool {
	t.Helper()
	if token := os.Getenv("PORTABLE_PRIVATE_TEST_CONSOLE"); token != "" {
		// A test child cannot silently reuse the runner's console. The wrapper
		// records its own PID and the new console must contain only this child.
		parent, err := strconv.Atoi(token)
		ids := attachedConsoleProcesses(t)
		if err != nil || parent == os.Getpid() || len(ids) != 1 || ids[0] != uint32(os.Getpid()) {
			t.Fatalf("test was not started in an isolated console: pids=%v", ids)
		}
		return false
	}
	ctx, cancel := context.WithTimeout(context.Background(), 45*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, os.Args[0], "-test.run=^"+t.Name()+"$")
	cmd.Env = append(os.Environ(), "PORTABLE_PRIVATE_TEST_CONSOLE="+strconv.Itoa(os.Getpid()))
	const createNewConsole = 0x00000010
	cmd.SysProcAttr = &syscall.SysProcAttr{
		CreationFlags: createNewConsole,
		HideWindow:    true,
	}
	output, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("private console process test failed: %v\n%s", err, output)
	}
	if !strings.Contains(string(output), "PASS") {
		t.Fatalf("private console process test did not complete: %s", output)
	}
	return true
}

func TestConsoleInterruptReenabledAfterGroupRestart(t *testing.T) {
	if runProcessTestInPrivateConsole(t) {
		return
	}
	// Absorb the synthetic event in this private harness. The worker is
	// started exactly as the update helper starts a replacement launcher.
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, os.Interrupt)
	defer signal.Stop(signals)
	cmd, ready, received := startShutdownChild(t, "ctrl-c", "")
	waitForShutdownFile(t, ready)
	ids := attachedConsoleProcesses(t)
	if len(ids) != 2 {
		t.Fatalf("refusing CTRL_C_EVENT outside a two-process private console: %v", ids)
	}
	for _, pid := range ids {
		if pid != uint32(os.Getpid()) && pid != uint32(cmd.Process.Pid) {
			t.Fatalf("refusing CTRL_C_EVENT in a console with an unrelated process: %v", ids)
		}
	}
	ret, _, err := kernel32.NewProc("GenerateConsoleCtrlEvent").Call(syscall.CTRL_C_EVENT, 0)
	if ret == 0 {
		t.Fatalf("private CTRL_C_EVENT failed: %v", err)
	}
	waitForShutdownFile(t, received)
	if err := cmd.Wait(); err != nil {
		t.Fatalf("restarted launcher did not handle Ctrl+C gracefully: %v", err)
	}
}
