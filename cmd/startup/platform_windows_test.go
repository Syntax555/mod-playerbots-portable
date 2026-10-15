//go:build windows

package main

import (
	"context"
	"errors"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"
	"unsafe"
)

func denyProcessQueries(t *testing.T, pid int) syscall.Handle {
	t.Helper()
	const writeDAC = 0x40000
	handle, err := syscall.OpenProcess(writeDAC|syscall.PROCESS_TERMINATE|syscall.SYNCHRONIZE, false, uint32(pid))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_ = syscall.TerminateProcess(handle, 0)
		_ = syscall.CloseHandle(handle)
	})
	// Keep the existing handle usable while new query and wait handles are denied.
	security, err := syscall.UTF16PtrFromString("D:(D;;0x101000;;;WD)(A;;GA;;;WD)")
	if err != nil {
		t.Fatal(err)
	}
	advapi := syscall.NewLazyDLL("advapi32.dll")
	var descriptor uintptr
	ok, _, err := advapi.NewProc("ConvertStringSecurityDescriptorToSecurityDescriptorW").Call(
		uintptr(unsafe.Pointer(security)), 1, uintptr(unsafe.Pointer(&descriptor)), 0)
	if ok == 0 {
		t.Fatalf("create process DACL: %v", err)
	}
	defer kernel32.NewProc("LocalFree").Call(descriptor)
	const daclSecurityInformation = 4
	ok, _, err = advapi.NewProc("SetKernelObjectSecurity").Call(uintptr(handle), daclSecurityInformation, descriptor)
	if ok == 0 {
		t.Fatalf("set process DACL: %v", err)
	}
	for _, access := range []uint32{syscall.SYNCHRONIZE | processQueryLimitedInformation, syscall.SYNCHRONIZE} {
		probe, err := syscall.OpenProcess(access, false, uint32(pid))
		if err == nil {
			_ = syscall.CloseHandle(probe)
		}
		if !errors.Is(err, syscall.ERROR_ACCESS_DENIED) {
			t.Fatalf("process DACL did not deny OpenProcess(%#x): %v", access, err)
		}
	}
	return handle
}

func TestProcessSnapshotAfterAccessDenied(t *testing.T) {
	for _, name := range []string{"STARTUP.EXE", "helper.exe", "renamed.exe", "foreign.exe"} {
		t.Run(name, func(t *testing.T) {
			root := t.TempDir()
			folder := root
			if name == "foreign.exe" {
				folder = t.TempDir()
			}
			child := updateTestStartIdleProcess(t, filepath.Join(folder, name))
			pid := child.Process.Pid
			handle := denyProcessQueries(t, pid)
			if alive, code := isProcessAlive(pid); !alive || code != stillActive {
				t.Fatalf("inaccessible process treated as exited: alive=%v code=%d", alive, code)
			}
			if image, err := processExecutable(pid); err != nil || !strings.EqualFold(image, name) {
				t.Fatalf("process snapshot did not supply its image name: image=%q err=%v", image, err)
			}
			if watchProcessExit(pid)(100 * time.Millisecond) {
				t.Fatal("inaccessible running process reported as exited")
			}
			if active := updateProcessActive(root, pid); active != (name != "foreign.exe") {
				t.Fatalf("inaccessible image %q has unexpected updater status: %v", name, active)
			}
			if err := syscall.TerminateProcess(handle, 0); err != nil {
				t.Fatal(err)
			}
			if err := child.Wait(); err != nil {
				t.Fatal(err)
			}
			// The retained handle can keep an exited process in the snapshot.
			if alive, _ := isProcessAlive(pid); alive {
				t.Fatal("snapshot kept an exited process alive")
			}
			if image, err := processExecutable(pid); !errors.Is(err, os.ErrProcessDone) {
				t.Fatalf("exited process still has an image: image=%q err=%v", image, err)
			}
			if !watchProcessExit(pid)(100*time.Millisecond) || updateProcessActive(root, pid) {
				t.Fatal("exited process still blocks update recovery")
			}
		})
	}
}

func attachedConsoleProcesses(t *testing.T) []uint32 {
	t.Helper()
	var ids [8]uint32
	count, _, err := procGetConsoleProcessList.Call(uintptr(unsafe.Pointer(&ids[0])), uintptr(len(ids)))
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
	ret, _, err := procGenerateConsoleCtrlEvent.Call(syscall.CTRL_C_EVENT, 0)
	if ret == 0 {
		t.Fatalf("private CTRL_C_EVENT failed: %v", err)
	}
	waitForShutdownFile(t, received)
	if err := cmd.Wait(); err != nil {
		t.Fatalf("restarted launcher did not handle Ctrl+C gracefully: %v", err)
	}
}
