package main

import (
	"context"
	"errors"
	"fmt"
	"net"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func runMySQLAdminTestProbe() bool {
	mode := os.Getenv("PORTABLE_MYSQLADMIN_TEST_PROBE")
	if mode == "" {
		return false
	}
	if err := os.WriteFile(os.Getenv("PORTABLE_MYSQLADMIN_TEST_RECORD"), []byte(strings.Join(os.Args[1:], "\n")), 0600); err != nil {
		os.Exit(96)
	}
	if mode == "hang" {
		time.Sleep(30 * time.Second)
	}
	os.Exit(0)
	return true
}

func TestShutdownSignalChild(t *testing.T) {
	mode := os.Getenv("PORTABLE_SHUTDOWN_CHILD_MODE")
	if mode == "" {
		return
	}
	signals := make(chan os.Signal, 4)
	signal.Notify(signals, os.Interrupt)
	if mode == "ctrl-c" {
		if err := enableConsoleInterrupt(); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(91)
		}
	}
	ready := "ready"
	if mode == "listen" {
		listener, err := net.Listen("tcp4", "127.0.0.1:0")
		if err != nil {
			os.Exit(97)
		}
		defer listener.Close()
		ready = strconv.Itoa(listener.Addr().(*net.TCPAddr).Port)
	}
	if err := os.WriteFile(os.Getenv("PORTABLE_SHUTDOWN_READY"), []byte(ready), 0600); err != nil {
		os.Exit(92)
	}
	timeout := time.NewTimer(30 * time.Second)
	for {
		select {
		case <-signals:
			if err := os.WriteFile(os.Getenv("PORTABLE_SHUTDOWN_SIGNAL"), []byte("interrupted"), 0600); err != nil {
				os.Exit(93)
			}
			if mode == "ignore" {
				continue
			}
			if gate := os.Getenv("PORTABLE_SHUTDOWN_EXIT_GATE"); gate != "" {
				deadline := time.Now().Add(20 * time.Second)
				for !fileExists(gate) {
					if time.Now().After(deadline) {
						os.Exit(94)
					}
					time.Sleep(10 * time.Millisecond)
				}
			}
			os.Exit(0)
		case <-timeout.C:
			os.Exit(95)
		}
	}
}

func startShutdownChild(t *testing.T, mode, gate string) (*exec.Cmd, string, string) {
	t.Helper()
	dir := t.TempDir()
	ready, stopped := filepath.Join(dir, "ready"), filepath.Join(dir, "signal")
	cmd := exec.Command(os.Args[0], "-test.run=^TestShutdownSignalChild$")
	cmd.Env = append(os.Environ(), "PORTABLE_SHUTDOWN_CHILD_MODE="+mode,
		"PORTABLE_SHUTDOWN_READY="+ready, "PORTABLE_SHUTDOWN_SIGNAL="+stopped,
		"PORTABLE_SHUTDOWN_EXIT_GATE="+gate)
	configureConsoleProcess(cmd)
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = cmd.Process.Kill() })
	return cmd, ready, stopped
}

func waitForShutdownFile(t *testing.T, path string) {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for !fileExists(path) {
		if time.Now().After(deadline) {
			t.Fatalf("child did not create %s", filepath.Base(path))
		}
		time.Sleep(10 * time.Millisecond)
	}
}

func superviseShutdownChild(t *testing.T, name string, cmd *exec.Cmd) *ProcessSupervisor {
	t.Helper()
	ps := newProcessSupervisor(name, func() (*exec.Cmd, error) {
		return nil, errors.New("stopped child must not restart")
	}, time.Millisecond)
	go ps.Run(context.Background(), cmd, nil)
	t.Cleanup(func() {
		ps.Kill()
		select {
		case <-ps.doneChan:
		case <-time.After(5 * time.Second):
			t.Errorf("supervisor %s did not finish cleanup", name)
		}
	})
	return ps
}

func TestSupervisorRequestsOwnedGracefulStop(t *testing.T) {
	if runProcessTestInPrivateConsole(t) {
		return
	}
	foreign, foreignReady, foreignSignal := startShutdownChild(t, "exit", "")
	defer foreign.Wait()
	defer foreign.Process.Kill()
	owned, ownedReady, ownedSignal := startShutdownChild(t, "exit", "")
	ps := superviseShutdownChild(t, "owned game service", owned)
	waitForShutdownFile(t, foreignReady)
	waitForShutdownFile(t, ownedReady)
	ps.StopAndWait(4 * time.Second)
	if !fileExists(ownedSignal) || owned.ProcessState == nil || !owned.ProcessState.Success() {
		t.Fatalf("owned child did not exit through its signal handler: state=%v", owned.ProcessState)
	}
	if fileExists(foreignSignal) {
		t.Fatal("shutdown signalled an unrelated child")
	}
	if alive, _ := isProcessAlive(foreign.Process.Pid); !alive {
		t.Fatal("shutdown terminated an unrelated child")
	}
}

func TestSupervisorGracefulTimeoutKillsOwnedChild(t *testing.T) {
	if runProcessTestInPrivateConsole(t) {
		return
	}
	cmd, ready, stopped := startShutdownChild(t, "ignore", "")
	ps := superviseShutdownChild(t, "unresponsive owned service", cmd)
	waitForShutdownFile(t, ready)
	start := time.Now()
	ps.StopAndWait(500 * time.Millisecond)
	if elapsed := time.Since(start); elapsed > 4*time.Second {
		t.Fatalf("fallback shutdown took %v", elapsed)
	}
	if !fileExists(stopped) {
		t.Fatal("hard kill happened without an initial graceful shutdown request")
	}
	if cmd.ProcessState == nil || cmd.ProcessState.Success() {
		t.Fatalf("unresponsive child was not killed: state=%v", cmd.ProcessState)
	}
}

func TestSupervisorStopDuringCommandPublication(t *testing.T) {
	if runProcessTestInPrivateConsole(t) {
		return
	}
	cmd, ready, stopped := startShutdownChild(t, "exit", "")
	waitForShutdownFile(t, ready)
	publishing, release := make(chan struct{}), make(chan struct{})
	var starts atomic.Int32
	ps := newProcessSupervisor("starting service", func() (*exec.Cmd, error) {
		starts.Add(1)
		close(publishing)
		<-release
		return cmd, nil
	}, time.Millisecond)
	go ps.Run(context.Background(), nil, nil)
	<-publishing
	ps.requestGracefulStop()
	close(release)
	ps.StopAndWait(4 * time.Second)
	if !fileExists(stopped) || cmd.ProcessState == nil || !cmd.ProcessState.Success() {
		t.Fatalf("child published during shutdown did not stop gracefully: state=%v", cmd.ProcessState)
	}
	if starts.Load() != 1 {
		t.Fatalf("service restarted during shutdown: starts=%d", starts.Load())
	}
}

func TestSupervisorKillBeforeCommandPublication(t *testing.T) {
	if runProcessTestInPrivateConsole(t) {
		return
	}
	cmd, ready, _ := startShutdownChild(t, "ignore", "")
	waitForShutdownFile(t, ready)
	ps := newProcessSupervisor("late owned child", nil, time.Millisecond)
	ps.Kill()
	go ps.Run(context.Background(), cmd, nil)
	select {
	case <-ps.doneChan:
	case <-time.After(4 * time.Second):
		t.Fatal("pre-publication kill request did not stop the owned child")
	}
	if cmd.ProcessState == nil || cmd.ProcessState.Success() {
		t.Fatalf("pre-publication kill request was lost: state=%v", cmd.ProcessState)
	}
}

func TestRealmShutdownKeepsDatabaseAvailableForGameSaves(t *testing.T) {
	if runProcessTestInPrivateConsole(t) {
		return
	}
	gate := filepath.Join(t.TempDir(), "finish-world-save")
	authCmd, authReady, authSignal := startShutdownChild(t, "exit", "")
	worldCmd, worldReady, worldSignal := startShutdownChild(t, "exit", gate)
	dbCmd, dbReady, dbSignal := startShutdownChild(t, "exit", "")
	auth := superviseShutdownChild(t, "authserver", authCmd)
	world := superviseShutdownChild(t, "worldserver", worldCmd)
	database := superviseShutdownChild(t, "database", dbCmd)
	for _, ready := range []string{authReady, worldReady, dbReady} {
		waitForShutdownFile(t, ready)
	}
	var databaseAvailable atomic.Bool
	done := make(chan struct{})
	go func() {
		defer close(done)
		shutdownRealmProcesses(auth, world, database, func() {}, func() error {
			if authCmd.ProcessState == nil || !authCmd.ProcessState.Success() || worldCmd.ProcessState == nil || !worldCmd.ProcessState.Success() {
				return errors.New("database shutdown requested before game services exited")
			}
			alive, _ := isProcessAlive(dbCmd.Process.Pid)
			databaseAvailable.Store(alive)
			return interruptConsoleProcess(dbCmd.Process)
		})
	}()
	waitForShutdownFile(t, authSignal)
	waitForShutdownFile(t, worldSignal)
	if fileExists(dbSignal) {
		t.Error("database received a stop request before the game save finished")
	}
	if alive, _ := isProcessAlive(dbCmd.Process.Pid); !alive {
		t.Error("database exited while world save was still pending")
	}
	if err := os.WriteFile(gate, []byte("saved"), 0600); err != nil {
		t.Fatal(err)
	}
	select {
	case <-done:
	case <-time.After(8 * time.Second):
		t.Fatal("realm shutdown did not finish")
	}
	if !databaseAvailable.Load() || !fileExists(dbSignal) || dbCmd.ProcessState == nil || !dbCmd.ProcessState.Success() {
		t.Fatalf("database was not stopped gracefully after game services: available=%v state=%v", databaseAvailable.Load(), dbCmd.ProcessState)
	}
}

func TestMySQLShutdownDoesNotAddressForeignServiceAfterChildExit(t *testing.T) {
	if runProcessTestInPrivateConsole(t) {
		return
	}
	foreign, ready, stopped := startShutdownChild(t, "exit", "")
	defer foreign.Wait()
	defer foreign.Process.Kill()
	waitForShutdownFile(t, ready)
	child := exec.Command(os.Args[0], "-test.run=^TestHelperProcess$")
	child.Env = append(os.Environ(), "GO_WANT_HELPER_PROCESS=1")
	if err := child.Run(); err != nil {
		t.Fatal(err)
	}
	adminRecord := filepath.Join(t.TempDir(), "admin-command")
	t.Setenv("PORTABLE_MYSQLADMIN_TEST_PROBE", "record")
	t.Setenv("PORTABLE_MYSQLADMIN_TEST_RECORD", adminRecord)
	if err := shutdownMySQLAndWait(&mysqlBinaries{mysqladmin: os.Args[0]}, 3306, child); err != nil {
		t.Fatal(err)
	}
	if fileExists(adminRecord) {
		t.Fatal("mysqladmin was invoked without a live owned MySQL child")
	}
	if fileExists(stopped) {
		t.Fatal("unrelated service received a shutdown signal")
	}
	if alive, _ := isProcessAlive(foreign.Process.Pid); !alive {
		t.Fatal("unrelated service was stopped")
	}
}

func TestMySQLShutdownCommandHonorsDeadline(t *testing.T) {
	record := filepath.Join(t.TempDir(), "admin-command")
	t.Setenv("PORTABLE_MYSQLADMIN_TEST_PROBE", "hang")
	t.Setenv("PORTABLE_MYSQLADMIN_TEST_RECORD", record)
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	start := time.Now()
	err := runMySQLShutdown(ctx, &mysqlBinaries{mysqladmin: os.Args[0]}, 3307)
	if err == nil || !errors.Is(ctx.Err(), context.DeadlineExceeded) {
		t.Fatalf("hanging administrative command did not time out: %v", err)
	}
	if elapsed := time.Since(start); elapsed > 4*time.Second {
		t.Fatalf("administrative command exceeded bounded cleanup: %v", elapsed)
	}
	content, readErr := os.ReadFile(record)
	if readErr != nil || !strings.Contains(string(content), "--connect-timeout=5\n") || !strings.Contains(string(content), "-P\n3307\n") {
		t.Fatalf("actual administrative command did not run with bounded connection and selected port: content=%q err=%v", content, readErr)
	}
}

func TestMySQLShutdownRequiresOwnedTCPListener(t *testing.T) {
	if runProcessTestInPrivateConsole(t) {
		return
	}
	foreign, foreignReady, foreignSignal := startShutdownChild(t, "listen", "")
	defer foreign.Wait()
	defer foreign.Process.Kill()
	owned, ownedReady, _ := startShutdownChild(t, "listen", "")
	ps := superviseShutdownChild(t, "owned MySQL listener", owned)
	waitForShutdownFile(t, foreignReady)
	waitForShutdownFile(t, ownedReady)
	readPort := func(path string) int {
		content, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		port, err := strconv.Atoi(string(content))
		if err != nil {
			t.Fatal(err)
		}
		return port
	}
	foreignPort, ownedPort := readPort(foreignReady), readPort(ownedReady)
	adminRecord := filepath.Join(t.TempDir(), "admin-command")
	t.Setenv("PORTABLE_MYSQLADMIN_TEST_PROBE", "record")
	t.Setenv("PORTABLE_MYSQLADMIN_TEST_RECORD", adminRecord)
	binaries := &mysqlBinaries{mysqladmin: os.Args[0]}
	if err := waitForMySQLReady(context.Background(), owned, binaries, foreignPort, 750*time.Millisecond); err == nil {
		t.Fatal("MySQL readiness accepted another process's listening port")
	}
	if fileExists(adminRecord) {
		t.Fatal("MySQL readiness sent a ping to a foreign listener")
	}
	if err := shutdownMySQL(binaries, foreignPort, owned.Process); err == nil {
		t.Fatal("administrative shutdown accepted a foreign listener while our child was alive")
	}
	if fileExists(adminRecord) || fileExists(foreignSignal) {
		t.Fatal("shutdown attempted to address the foreign service")
	}
	if err := waitForMySQLReady(context.Background(), owned, binaries, ownedPort, 4*time.Second); err != nil {
		t.Fatalf("owned MySQL listener failed readiness: %v", err)
	}
	if err := shutdownMySQL(binaries, ownedPort, owned.Process); err != nil {
		t.Fatalf("owned listener did not permit administrative command: %v", err)
	}
	content, err := os.ReadFile(adminRecord)
	if err != nil || !strings.Contains(string(content), "-P\n"+strconv.Itoa(ownedPort)+"\n") {
		t.Fatalf("admin command did not address owned port: %q (%v)", content, err)
	}
	if alive, _ := isProcessAlive(foreign.Process.Pid); !alive {
		t.Fatal("foreign listening service was terminated")
	}
	ps.StopAndWait(4 * time.Second)
}
