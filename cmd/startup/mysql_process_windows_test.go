//go:build windows

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

type mysqlTreeProbeRecord struct {
	PID int
}

// This is a real Windows process tree and TCP socket, matching MySQL's monitor
// plus listening mysqld child. The helper never connects to an installed DB.
func TestMySQLProcessTreeProbe(t *testing.T) {
	depthText := os.Getenv("PORTABLE_MYSQL_TREE_DEPTH")
	if depthText == "" {
		return
	}
	depth, err := strconv.Atoi(depthText)
	if err != nil || depth < 0 || depth > 3 {
		os.Exit(80)
	}
	interrupts := make(chan os.Signal, 4)
	signal.Notify(interrupts, os.Interrupt)
	go func() {
		for range interrupts {
		}
	}()
	if depth == 0 {
		listener, err := net.Listen("tcp4", "127.0.0.1:0")
		if err != nil {
			os.Exit(84)
		}
		defer listener.Close()
		port := listener.Addr().(*net.TCPAddr).Port
		if err := writeProbeFile(os.Getenv("PORTABLE_MYSQL_TREE_PORT"), []byte(strconv.Itoa(port))); err != nil {
			os.Exit(85)
		}
		time.Sleep(30 * time.Second)
		os.Exit(86)
	}
	if gate := os.Getenv("PORTABLE_MYSQL_TREE_START"); gate != "" {
		if err := os.WriteFile(gate+".ready", []byte("ready"), 0600); err != nil {
			os.Exit(87)
		}
		deadline := time.Now().Add(20 * time.Second)
		for !fileExists(gate) {
			if time.Now().After(deadline) {
				os.Exit(88)
			}
			time.Sleep(10 * time.Millisecond)
		}
	}
	executable := os.Args[0]
	if alternative := os.Getenv("PORTABLE_MYSQL_TREE_LEAF_EXE"); depth == 1 && alternative != "" {
		executable = alternative
	}
	cmd := exec.Command(executable, "-test.run=^TestMySQLProcessTreeProbe$")
	cmd.Env = append(os.Environ(), "PORTABLE_MYSQL_TREE_DEPTH="+strconv.Itoa(depth-1))
	if err := cmd.Start(); err != nil {
		os.Exit(82)
	}
	content, _ := json.Marshal(mysqlTreeProbeRecord{PID: cmd.Process.Pid})
	path := filepath.Join(os.Getenv("PORTABLE_MYSQL_TREE_DIR"), fmt.Sprintf("child-of-%d.json", os.Getpid()))
	if err := writeProbeFile(path, content); err != nil {
		_ = cmd.Process.Kill()
		os.Exit(83)
	}
	_ = cmd.Wait()
	os.Exit(0)
}

func startMySQLProcessTree(t *testing.T, depth int, alternative string) (*exec.Cmd, int, []*os.Process) {
	t.Helper()
	dir := t.TempDir()
	portFile := filepath.Join(dir, "port")
	cmd := exec.Command(os.Args[0], "-test.run=^TestMySQLProcessTreeProbe$")
	cmd.Env = append(os.Environ(), "PORTABLE_MYSQL_TREE_DEPTH="+strconv.Itoa(depth),
		"PORTABLE_MYSQL_TREE_DIR="+dir, "PORTABLE_MYSQL_TREE_PORT="+portFile,
		"PORTABLE_MYSQL_TREE_LEAF_EXE="+alternative)
	configureConsoleProcess(cmd)
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	if err := trackMySQLProcess(cmd); err != nil {
		_ = cmd.Process.Kill()
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = finishMySQLProcess(cmd); _ = cmd.Process.Kill() })
	var children []*os.Process
	pid := cmd.Process.Pid
	for i := 0; i < depth; i++ {
		path := filepath.Join(dir, fmt.Sprintf("child-of-%d.json", pid))
		waitForShutdownFile(t, path)
		content, err := os.ReadFile(path)
		var record mysqlTreeProbeRecord
		if err != nil || json.Unmarshal(content, &record) != nil || record.PID <= 0 {
			t.Fatalf("invalid child record: %q (%v)", content, err)
		}
		child, err := os.FindProcess(record.PID)
		if err != nil {
			t.Fatal(err)
		}
		children = append(children, child)
		t.Cleanup(func() { _ = child.Kill(); _ = child.Release() })
		pid = record.PID
	}
	waitForShutdownFile(t, portFile)
	content, err := os.ReadFile(portFile)
	port, parseErr := strconv.Atoi(string(content))
	if err != nil || parseErr != nil || port <= 0 {
		t.Fatalf("invalid listening port: %q (%v, %v)", content, err, parseErr)
	}
	return cmd, port, children
}

func waitForMySQLTreeStopped(t *testing.T, children []*os.Process) {
	t.Helper()
	deadline := time.Now().Add(3 * time.Second)
	for _, child := range children {
		for {
			if alive, _ := isProcessAlive(child.Pid); !alive {
				break
			}
			if time.Now().After(deadline) {
				t.Fatalf("owned listening descendant %d survived cleanup", child.Pid)
			}
			time.Sleep(10 * time.Millisecond)
		}
	}
}

func TestMySQLReadinessAndShutdownAcceptOwnedDescendants(t *testing.T) {
	if runProcessTestInPrivateConsole(t) {
		return
	}
	for _, depth := range []int{1, 2} {
		t.Run(fmt.Sprintf("depth-%d", depth), func(t *testing.T) {
			cmd, port, children := startMySQLProcessTree(t, depth, "")
			defer cmd.Wait()
			defer killMySQLProcessTree(cmd.Process)
			pid, err := mysqlListenerPID(port)
			if err != nil || pid != uint32(children[len(children)-1].Pid) || pid == uint32(cmd.Process.Pid) {
				t.Fatalf("fixture did not create a child-owned listener: %d (%v)", pid, err)
			}
			adminRecord := filepath.Join(t.TempDir(), "admin-command")
			t.Setenv("PORTABLE_MYSQLADMIN_TEST_PROBE", "record")
			t.Setenv("PORTABLE_MYSQLADMIN_TEST_RECORD", adminRecord)
			binaries := &mysqlBinaries{mysqladmin: os.Args[0]}
			if err := waitForMySQLReady(context.Background(), cmd, binaries, port, 4*time.Second); err != nil {
				t.Fatalf("owned descendant failed actual readiness path: %v", err)
			}
			if err := shutdownMySQL(binaries, port, cmd.Process); err != nil {
				t.Fatalf("owned descendant rejected administrative shutdown: %v", err)
			}
			content, err := os.ReadFile(adminRecord)
			if err != nil || !strings.Contains(string(content), "-P\n"+strconv.Itoa(port)+"\n") || !strings.HasSuffix(string(content), "shutdown") {
				t.Fatalf("shutdown did not address the verified descendant port: %q (%v)", content, err)
			}
		})
	}
}

func TestMySQLOwnershipRejectsDifferentExecutableDescendant(t *testing.T) {
	if runProcessTestInPrivateConsole(t) {
		return
	}
	alternative := filepath.Join(t.TempDir(), "different-server.exe")
	content, err := os.ReadFile(os.Args[0])
	if err != nil || os.WriteFile(alternative, content, 0700) != nil {
		t.Fatal("could not prepare a distinct executable path")
	}
	cmd, port, children := startMySQLProcessTree(t, 1, alternative)
	defer cmd.Wait()
	defer cmd.Process.Kill()
	adminRecord := filepath.Join(t.TempDir(), "admin-command")
	t.Setenv("PORTABLE_MYSQLADMIN_TEST_PROBE", "record")
	t.Setenv("PORTABLE_MYSQLADMIN_TEST_RECORD", adminRecord)
	binaries := &mysqlBinaries{mysqladmin: os.Args[0]}
	if err := waitForMySQLReady(context.Background(), cmd, binaries, port, 750*time.Millisecond); err == nil {
		t.Fatal("different executable descendant was accepted for readiness")
	}
	if err := shutdownMySQL(binaries, port, cmd.Process); err == nil || fileExists(adminRecord) {
		t.Fatal("administrative command was sent to a different executable")
	}
	if err := killMySQLProcessTree(cmd.Process); err != nil {
		t.Fatal(err)
	}
	if alive, _ := isProcessAlive(children[0].Pid); !alive {
		t.Fatal("tree cleanup terminated an unverified different executable")
	}
}

func TestMySQLFallbackCleanupStopsOwnedTreeAndPreservesForeignListener(t *testing.T) {
	if runProcessTestInPrivateConsole(t) {
		return
	}
	foreign, ready, foreignSignal := startShutdownChild(t, "listen", "")
	defer foreign.Wait()
	defer foreign.Process.Kill()
	waitForShutdownFile(t, ready)
	cmd, port, children := startMySQLProcessTree(t, 2, "")
	adminRecord := filepath.Join(t.TempDir(), "admin-command")
	t.Setenv("PORTABLE_MYSQLADMIN_TEST_PROBE", "record")
	t.Setenv("PORTABLE_MYSQLADMIN_TEST_RECORD", adminRecord)
	// The administrative fixture records shutdown without exiting the tree,
	// forcing production's bounded startup-failure cleanup to run its fallback.
	if err := shutdownMySQLAndWait(&mysqlBinaries{mysqladmin: os.Args[0]}, port, cmd); err != nil {
		t.Fatal(err)
	}
	waitForMySQLTreeStopped(t, children)
	if cmd.ProcessState == nil {
		t.Fatal("failed-start cleanup did not wait for its own monitor")
	}
	if alive, _ := isProcessAlive(foreign.Process.Pid); !alive || fileExists(foreignSignal) {
		t.Fatal("MySQL tree cleanup stopped or signalled an unrelated listener")
	}
}

func TestMySQLSupervisorKillStopsOwnedDescendants(t *testing.T) {
	if runProcessTestInPrivateConsole(t) {
		return
	}
	for _, beforePublication := range []bool{false, true} {
		t.Run(fmt.Sprintf("before-publication-%v", beforePublication), func(t *testing.T) {
			cmd, _, children := startMySQLProcessTree(t, 2, "")
			ps := newProcessSupervisor("mysqld", nil, time.Millisecond)
			ps.killProcess = killMySQLProcessTree
			ps.finishProcess = finishMySQLProcess
			if beforePublication {
				ps.Kill()
			}
			go ps.Run(context.Background(), cmd, nil)
			ps.StopAndWait(300 * time.Millisecond)
			waitForMySQLTreeStopped(t, children)
			if cmd.ProcessState == nil {
				t.Fatal("supervisor did not wait for its owned monitor")
			}
			if trackedMySQLProcess(cmd.Process) != nil {
				t.Fatal("supervisor did not release its completed tree tracker")
			}
		})
	}
}

func TestMySQLOwnershipRejectsListenerAfterMonitorExit(t *testing.T) {
	if runProcessTestInPrivateConsole(t) {
		return
	}
	cmd, port, children := startMySQLProcessTree(t, 1, "")
	retained, err := os.FindProcess(cmd.Process.Pid)
	if err != nil {
		t.Fatal(err)
	}
	defer retained.Release()
	if err := cmd.Process.Kill(); err != nil {
		t.Fatal(err)
	}
	_ = cmd.Wait()
	if alive, _ := isProcessAlive(children[0].Pid); !alive {
		t.Fatal("fixture did not leave a child after its monitor exited")
	}
	if owned, err := ownsMySQLListener(port, retained); owned {
		t.Fatalf("dead monitor was accepted as a live ownership anchor: %v (%v)", owned, err)
	}
	if err := finishMySQLProcess(cmd); err != nil {
		t.Fatalf("could not clean up children of the already waited monitor: %v", err)
	}
	waitForMySQLTreeStopped(t, children)
	if trackedMySQLProcess(cmd.Process) != nil {
		t.Fatal("completed monitor retained its tracker")
	}
}

func TestMySQLFreshSnapshotRejectsStaleForeignProcessLinks(t *testing.T) {
	if runProcessTestInPrivateConsole(t) {
		return
	}
	ownedCmd, _, _ := startMySQLProcessTree(t, 1, "")
	defer ownedCmd.Wait()
	defer killMySQLProcessTree(ownedCmd.Process)
	// Start this second, so its genuine creation times are later than the
	// owned monitor and pass the chronological check despite forged old links.
	foreignCmd, _, foreignChildren := startMySQLProcessTree(t, 1, "")
	defer foreignCmd.Wait()
	defer killMySQLProcessTree(foreignCmd.Process)
	root, err := openMySQLProcess(uint32(ownedCmd.Process.Pid), false)
	if err != nil {
		t.Fatal(err)
	}
	defer root.close()
	for _, depth := range []int{1, 2} {
		parents, err := mysqlProcessParents()
		if err != nil {
			t.Fatal(err)
		}
		foreignPID := uint32(foreignCmd.Process.Pid)
		if depth == 2 {
			foreignPID = uint32(foreignChildren[0].Pid)
			parents[foreignPID] = uint32(foreignCmd.Process.Pid)
		}
		parents[uint32(foreignCmd.Process.Pid)] = root.pid
		for _, terminate := range []bool{false, true} {
			candidate, err := ownedMySQLDescendant(root, foreignPID, parents, terminate)
			if candidate != nil {
				candidate.close()
				t.Fatalf("stale depth-%d snapshot bound foreign PID %d to owned root", depth, foreignPID)
			}
			if err != nil {
				t.Fatalf("fresh snapshot lookup failed instead of checking real ancestry: %v", err)
			}
		}
	}
	if alive, _ := isProcessAlive(foreignCmd.Process.Pid); !alive {
		t.Fatal("ownership lookup affected the unrelated monitor")
	}
	if alive, _ := isProcessAlive(foreignChildren[0].Pid); !alive {
		t.Fatal("ownership lookup affected the unrelated listening child")
	}
}

func TestMySQLCleanupFindsChildrenStartedAfterInitialSnapshot(t *testing.T) {
	if runProcessTestInPrivateConsole(t) {
		return
	}
	foreign, _, _ := startMySQLProcessTree(t, 0, "")
	defer foreign.Wait()
	defer finishMySQLProcess(foreign)
	for _, depth := range []int{1, 2} {
		t.Run(fmt.Sprintf("late-depth-%d", depth), func(t *testing.T) {
			dir := t.TempDir()
			gate := filepath.Join(dir, "start-child")
			portFile := filepath.Join(dir, "port")
			cmd := exec.Command(os.Args[0], "-test.run=^TestMySQLProcessTreeProbe$")
			cmd.Env = append(os.Environ(), "PORTABLE_MYSQL_TREE_DEPTH="+strconv.Itoa(depth),
				"PORTABLE_MYSQL_TREE_DIR="+dir, "PORTABLE_MYSQL_TREE_PORT="+portFile,
				"PORTABLE_MYSQL_TREE_START="+gate)
			configureConsoleProcess(cmd)
			if err := cmd.Start(); err != nil {
				t.Fatal(err)
			}
			defer cmd.Wait()
			defer cmd.Process.Kill()
			if err := trackMySQLProcess(cmd); err != nil {
				t.Fatal(err)
			}
			defer finishMySQLProcess(cmd)
			waitForShutdownFile(t, gate+".ready")
			initialParents, err := mysqlProcessParents()
			if err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(gate, []byte("start"), 0600); err != nil {
				t.Fatal(err)
			}
			var children []*os.Process
			pid := cmd.Process.Pid
			for i := 0; i < depth; i++ {
				path := filepath.Join(dir, fmt.Sprintf("child-of-%d.json", pid))
				waitForShutdownFile(t, path)
				content, err := os.ReadFile(path)
				var record mysqlTreeProbeRecord
				if err != nil || json.Unmarshal(content, &record) != nil || record.PID <= 0 {
					t.Fatalf("invalid late child record: %q (%v)", content, err)
				}
				child, err := os.FindProcess(record.PID)
				if err != nil {
					t.Fatal(err)
				}
				children = append(children, child)
				t.Cleanup(func() { _ = child.Kill(); _ = child.Release() })
				pid = record.PID
				if _, present := initialParents[uint32(pid)]; present {
					t.Fatal("late fixture child existed in the initial snapshot")
				}
			}
			waitForShutdownFile(t, portFile)
			tracker := trackedMySQLProcess(cmd.Process)
			tracker.mu.Lock()
			// Use the actual snapshot from before the real child was created.
			// The production cleanup body must find it after stopping the root.
			err = tracker.stopOwnedTreeFromSnapshotLocked(initialParents, nil)
			tracker.mu.Unlock()
			if err != nil {
				t.Fatal(err)
			}
			waitForMySQLTreeStopped(t, children)
			if alive, _ := isProcessAlive(foreign.Process.Pid); !alive {
				t.Fatal("late-child cleanup stopped a same-executable foreign listener")
			}
		})
	}
}

func TestMySQLCleanupRetainsKnownExitedAncestors(t *testing.T) {
	if runProcessTestInPrivateConsole(t) {
		return
	}
	cmd, port, children := startMySQLProcessTree(t, 2, "")
	if owned, err := ownsMySQLListener(port, cmd.Process); err != nil || !owned {
		t.Fatalf("could not retain the live native ancestor chain: %v, %v", owned, err)
	}
	if err := children[0].Kill(); err != nil {
		t.Fatal(err)
	}
	_ = cmd.Wait()
	if alive, _ := isProcessAlive(children[1].Pid); !alive {
		t.Fatal("fixture did not leave a child after its intermediate ancestor exited")
	}
	if err := finishMySQLProcess(cmd); err != nil {
		t.Fatal(err)
	}
	waitForMySQLTreeStopped(t, children)
}

func TestMySQLDeadMonitorCleanupRejectsStaleForeignSnapshot(t *testing.T) {
	if runProcessTestInPrivateConsole(t) {
		return
	}
	cmd, _, children := startMySQLProcessTree(t, 1, "")
	if err := cmd.Process.Kill(); err != nil {
		t.Fatal(err)
	}
	_ = cmd.Wait()
	foreign, _, foreignChildren := startMySQLProcessTree(t, 1, "")
	defer foreign.Wait()
	defer finishMySQLProcess(foreign)
	parents, err := mysqlProcessParents()
	if err != nil {
		t.Fatal(err)
	}
	parents[uint32(foreign.Process.Pid)] = uint32(cmd.Process.Pid)
	tracker := trackedMySQLProcess(cmd.Process)
	tracker.mu.Lock()
	err = tracker.stopOwnedTreeFromSnapshotLocked(parents, nil)
	tracker.mu.Unlock()
	if err != nil {
		t.Fatal(err)
	}
	waitForMySQLTreeStopped(t, children)
	for _, process := range append([]*os.Process{foreign.Process}, foreignChildren...) {
		if alive, _ := isProcessAlive(process.Pid); !alive {
			t.Fatalf("dead-root cleanup adopted foreign PID %d from stale links", process.Pid)
		}
	}
	if err := finishMySQLProcess(cmd); err != nil {
		t.Fatal(err)
	}
}
