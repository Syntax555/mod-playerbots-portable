package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"sync/atomic"
	"testing"
	"time"
)

func TestMySQLProcessIdentityRejectsReusedAncestors(t *testing.T) {
	const root, monitor, listener = uint32(100), uint32(200), uint32(300)
	cases := []struct {
		name       string
		identities map[uint32]mysqlProcessIdentity
		owned      bool
	}{
		{"direct listener", map[uint32]mysqlProcessIdentity{root: {created: 10, sameExecutable: true}}, true},
		{"same executable child", map[uint32]mysqlProcessIdentity{
			root: {created: 10, sameExecutable: true}, listener: {parent: root, created: 20, sameExecutable: true}}, true},
		{"same executable grandchild", map[uint32]mysqlProcessIdentity{
			root: {created: 10, sameExecutable: true}, monitor: {parent: root, created: 20, sameExecutable: true},
			listener: {parent: monitor, created: 30, sameExecutable: true}}, true},
		{"reused root PID", map[uint32]mysqlProcessIdentity{
			root: {created: 40, sameExecutable: true}, listener: {parent: root, created: 20, sameExecutable: true}}, false},
		{"reused intermediate PID", map[uint32]mysqlProcessIdentity{
			root: {created: 10, sameExecutable: true}, monitor: {parent: root, created: 40, sameExecutable: true},
			listener: {parent: monitor, created: 30, sameExecutable: true}}, false},
		{"foreign intermediate executable", map[uint32]mysqlProcessIdentity{
			root: {created: 10, sameExecutable: true}, monitor: {parent: root, created: 20},
			listener: {parent: monitor, created: 30, sameExecutable: true}}, false},
		{"different listening executable", map[uint32]mysqlProcessIdentity{
			root: {created: 10, sameExecutable: true}, listener: {parent: root, created: 20}}, false},
		{"missing exited parent", map[uint32]mysqlProcessIdentity{
			root: {created: 10, sameExecutable: true}, listener: {parent: monitor, created: 30, sameExecutable: true}}, false},
		{"parent cycle", map[uint32]mysqlProcessIdentity{
			root: {created: 10, sameExecutable: true}, monitor: {parent: listener, created: 20, sameExecutable: true},
			listener: {parent: monitor, created: 20, sameExecutable: true}}, false},
		{"missing creation time", map[uint32]mysqlProcessIdentity{
			root: {sameExecutable: true}, listener: {parent: root, created: 20, sameExecutable: true}}, false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			pid := listener
			if c.name == "direct listener" {
				pid = root
			}
			currentParents := make(map[uint32]uint32)
			for candidate, identity := range c.identities {
				currentParents[candidate] = identity.parent
			}
			if got := validMySQLProcessChain(root, pid, c.identities, currentParents); got != c.owned {
				t.Fatalf("ownership=%v, want %v", got, c.owned)
			}
		})
	}
	identities := map[uint32]mysqlProcessIdentity{root: {created: 1, sameExecutable: true}}
	for pid := uint32(101); pid < 101+maxMySQLParentDepth; pid++ {
		identities[pid] = mysqlProcessIdentity{parent: pid - 1, created: uint64(pid), sameExecutable: true}
	}
	currentParents := make(map[uint32]uint32)
	for pid, identity := range identities {
		currentParents[pid] = identity.parent
	}
	if validMySQLProcessChain(root, 100+maxMySQLParentDepth, identities, currentParents) {
		t.Fatal("unbounded ancestry chain was accepted")
	}
}

func TestMySQLProcessIdentityRejectsSnapshotReuseBeforeHandleOpen(t *testing.T) {
	const root, monitor, listener, foreign = uint32(100), uint32(200), uint32(300), uint32(400)
	identities := map[uint32]mysqlProcessIdentity{
		root:     {created: 10, sameExecutable: true},
		monitor:  {parent: root, created: 20, sameExecutable: true},
		listener: {parent: monitor, created: 30, sameExecutable: true},
	}
	// All images and timestamps remain plausible after a PID is reused by a
	// later same-path executable. Its actual current parent exposes the reuse.
	for _, currentParents := range []map[uint32]uint32{
		{monitor: root, listener: foreign},    // stale leaf PID
		{monitor: foreign, listener: monitor}, // stale intermediate PID
		{monitor: root},                       // exited leaf absent from the fresh snapshot
		{listener: monitor},                   // exited intermediate absent from the fresh snapshot
	} {
		if validMySQLProcessChain(root, listener, identities, currentParents) {
			t.Fatalf("stale snapshot ancestry was accepted: %v", currentParents)
		}
	}
}

func TestMySQLSupervisorFinalizesExitedProcessBeforeRestart(t *testing.T) {
	var starts, finishes atomic.Int32
	completed := make(chan error, 2)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	ps := newProcessSupervisor("MySQL lifecycle fixture", func() (*exec.Cmd, error) {
		previousStarts := starts.Load()
		if finishes.Load() != previousStarts {
			return nil, fmt.Errorf("restart began before prior process cleanup: starts=%d finishes=%d", previousStarts, finishes.Load())
		}
		cmd := exec.Command(os.Args[0], "-test.run=^TestHelperProcess$")
		cmd.Env = append(os.Environ(), "GO_WANT_HELPER_PROCESS=1")
		if err := cmd.Start(); err != nil {
			completed <- err
			cancel()
			return nil, err
		}
		starts.Add(1)
		return cmd, nil
	}, time.Millisecond)
	ps.finishProcess = func(cmd *exec.Cmd) error {
		if cmd.ProcessState == nil {
			completed <- fmt.Errorf("process finalizer ran before Wait")
			cancel()
			return nil
		}
		if finishes.Add(1) == 2 {
			cancel()
		}
		return nil
	}
	go ps.Run(ctx, nil, nil)
	select {
	case <-ps.doneChan:
	case <-time.After(6 * time.Second):
		cancel()
		t.Fatal("supervisor did not finish its restart/finalization cycle")
	}
	select {
	case err := <-completed:
		t.Fatal(err)
	default:
	}
	if starts.Load() != 2 || finishes.Load() != 2 {
		t.Fatalf("not every exited process was finalized: starts=%d finishes=%d", starts.Load(), finishes.Load())
	}
}
