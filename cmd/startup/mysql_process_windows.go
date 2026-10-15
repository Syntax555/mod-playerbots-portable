//go:build windows

package main

import (
	"encoding/binary"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"
	"unsafe"
)

var procGetExtendedTCPTable = syscall.NewLazyDLL("iphlpapi.dll").NewProc("GetExtendedTcpTable")

type mysqlNativeProcess struct {
	pid     uint32
	handle  syscall.Handle
	created uint64
	image   string
	parent  uint32
}

type mysqlProcessTracker struct {
	mu     sync.Mutex
	root   *mysqlNativeProcess
	owned  map[uint32]*mysqlNativeProcess
	closed bool
}

var mysqlProcessTrackers = struct {
	sync.Mutex
	byPID map[uint32]*mysqlProcessTracker
}{byPID: make(map[uint32]*mysqlProcessTracker)}

// Capture the original process while exec.Cmd still owns its handle. Retaining
// this identity through Wait prevents an exited monitor's PID from being reused
// before its remaining listening children have been cleaned up.
func trackMySQLProcess(cmd *exec.Cmd) error {
	if cmd == nil || cmd.Process == nil || cmd.Process.Pid <= 0 {
		return errors.New("MySQL tracking requires a started process")
	}
	root, err := openMySQLProcess(uint32(cmd.Process.Pid), true)
	if err != nil {
		return err
	}
	mysqlProcessTrackers.Lock()
	defer mysqlProcessTrackers.Unlock()
	if existing := mysqlProcessTrackers.byPID[root.pid]; existing != nil {
		root.close()
		return errors.New("MySQL process identity is already tracked")
	}
	mysqlProcessTrackers.byPID[root.pid] = &mysqlProcessTracker{
		root: root, owned: map[uint32]*mysqlNativeProcess{root.pid: root},
	}
	return nil
}

func trackedMySQLProcess(process *os.Process) *mysqlProcessTracker {
	if process == nil || process.Pid <= 0 {
		return nil
	}
	mysqlProcessTrackers.Lock()
	defer mysqlProcessTrackers.Unlock()
	return mysqlProcessTrackers.byPID[uint32(process.Pid)]
}

func finishMySQLProcess(cmd *exec.Cmd) error {
	if cmd == nil || cmd.Process == nil {
		return nil
	}
	tracker := trackedMySQLProcess(cmd.Process)
	if tracker == nil {
		return nil
	}
	tracker.mu.Lock()
	defer tracker.mu.Unlock()
	if tracker.closed {
		return nil
	}
	err := tracker.stopOwnedTreeLocked()
	tracker.closed = true
	mysqlProcessTrackers.Lock()
	delete(mysqlProcessTrackers.byPID, tracker.root.pid)
	mysqlProcessTrackers.Unlock()
	for _, process := range tracker.owned {
		process.close()
	}
	return err
}

func (p *mysqlNativeProcess) close() { _ = syscall.CloseHandle(p.handle) }

func (p *mysqlNativeProcess) alive() bool {
	status, err := syscall.WaitForSingleObject(p.handle, 0)
	return err == nil && status == syscall.WAIT_TIMEOUT
}

func openMySQLProcess(pid uint32, terminate bool) (*mysqlNativeProcess, error) {
	access := uint32(syscall.SYNCHRONIZE | processQueryLimitedInformation)
	if terminate {
		access |= syscall.PROCESS_TERMINATE
	}
	handle, err := syscall.OpenProcess(access, false, pid)
	if err != nil {
		return nil, fmt.Errorf("OpenProcess(%d): %w", pid, err)
	}
	p := &mysqlNativeProcess{pid: pid, handle: handle}
	var created, exited, kernel, user syscall.Filetime
	if err := syscall.GetProcessTimes(handle, &created, &exited, &kernel, &user); err != nil {
		p.close()
		return nil, fmt.Errorf("GetProcessTimes(%d): %w", pid, err)
	}
	p.created = uint64(created.HighDateTime)<<32 | uint64(created.LowDateTime)
	if p.image, err = processImagePath(handle); err != nil {
		p.close()
		return nil, fmt.Errorf("process %d image: %w", pid, err)
	}
	return p, nil
}

func mysqlProcessParents() (map[uint32]uint32, error) {
	parents := make(map[uint32]uint32)
	err := forEachProcess(func(entry *syscall.ProcessEntry32) error {
		// Toolhelp can retain exited processes while their handles are open.
		if entry.Threads != 0 {
			parents[entry.ProcessID] = entry.ParentProcessID
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	return parents, nil
}

// Hold every new ancestor until a second snapshot verifies its actual links.
// Cleanup can use previously verified, retained ancestors after they exit;
// readiness callers still require the original monitor to be alive.
func openOwnedMySQLChain(root *mysqlNativeProcess, pid uint32, parents map[uint32]uint32, known map[uint32]*mysqlNativeProcess, terminate bool) ([]*mysqlNativeProcess, error) {
	chain := make([]uint32, 0, maxMySQLParentDepth)
	seen := make(map[uint32]bool)
	for candidate := pid; candidate != root.pid; {
		parent, exists := parents[candidate]
		if retained := known[candidate]; retained != nil {
			parent, exists = retained.parent, true
		}
		if !exists || seen[candidate] || candidate == 0 || len(chain) >= maxMySQLParentDepth-1 {
			return nil, nil
		}
		seen[candidate] = true
		chain = append(chain, candidate)
		candidate = parent
	}
	if len(chain) == 0 {
		return nil, nil
	}
	identities := map[uint32]mysqlProcessIdentity{
		root.pid: {created: root.created, sameExecutable: true},
	}
	for candidate, p := range known {
		identities[candidate] = mysqlProcessIdentity{
			parent: p.parent, created: p.created,
			sameExecutable: strings.EqualFold(filepath.Clean(root.image), filepath.Clean(p.image)),
		}
	}
	held := make([]*mysqlNativeProcess, 0, len(chain))
	accepted := false
	defer func() {
		if accepted {
			return
		}
		for _, p := range held {
			p.close()
		}
	}()
	for _, candidate := range chain {
		if known[candidate] != nil {
			continue
		}
		p, err := openMySQLProcess(candidate, terminate)
		if err != nil {
			// A process can exit after the snapshot, making OpenProcess fail
			// with access denied. Keep errors for candidates still running.
			currentParents, snapshotErr := mysqlProcessParents()
			if _, present := currentParents[candidate]; snapshotErr == nil && !present {
				return nil, nil
			}
			return nil, errors.Join(err, snapshotErr)
		}
		held = append(held, p)
		p.parent = parents[candidate]
		if !p.alive() {
			return nil, nil
		}
		identities[candidate] = mysqlProcessIdentity{
			parent: p.parent, created: p.created,
			sameExecutable: strings.EqualFold(filepath.Clean(root.image), filepath.Clean(p.image)),
		}
	}
	// The first snapshot may predate OpenProcess. A dead candidate's PID can
	// be reused by an unrelated same-path executable in that interval. Take
	// a fresh snapshot now that every identity is pinned by its open handle.
	currentParents, err := mysqlProcessParents()
	if err != nil {
		return nil, err
	}
	for candidate, p := range known {
		if _, present := currentParents[candidate]; !present && !p.alive() {
			// An exited, retained process cannot acquire a different parent.
			// Its original ancestry was verified before this handle was kept.
			currentParents[candidate] = p.parent
		}
	}
	if !validMySQLProcessChain(root.pid, pid, identities, currentParents) {
		return nil, nil
	}
	for _, p := range held {
		if !p.alive() {
			return nil, nil
		}
	}
	accepted = true
	return held, nil
}

func ownedMySQLDescendant(root *mysqlNativeProcess, pid uint32, parents map[uint32]uint32, terminate bool) (*mysqlNativeProcess, error) {
	if !root.alive() {
		return nil, nil
	}
	held, err := openOwnedMySQLChain(root, pid, parents, map[uint32]*mysqlNativeProcess{root.pid: root}, terminate)
	if len(held) == 0 {
		return nil, err
	}
	for _, ancestor := range held[1:] {
		ancestor.close()
	}
	if !root.alive() || !held[0].alive() {
		held[0].close()
		return nil, nil
	}
	return held[0], nil
}

func ownsMySQLListener(port int, process *os.Process) (bool, error) {
	if process == nil || process.Pid <= 0 || port <= 0 || port > 65535 {
		return false, nil
	}
	if tracker := trackedMySQLProcess(process); tracker != nil {
		tracker.mu.Lock()
		defer tracker.mu.Unlock()
		if tracker.closed || !tracker.root.alive() {
			return false, nil
		}
		pid, err := mysqlListenerPID(port)
		if err != nil || pid == 0 {
			return false, err
		}
		if known := tracker.owned[pid]; known != nil {
			return known.alive() && tracker.root.alive(), nil
		}
		parents, err := mysqlProcessParents()
		if err != nil {
			return false, err
		}
		held, err := openOwnedMySQLChain(tracker.root, pid, parents, tracker.owned, true)
		for _, candidate := range held {
			tracker.owned[candidate.pid] = candidate
		}
		owned := tracker.owned[pid]
		return owned != nil && owned.alive() && tracker.root.alive(), err
	}
	root, err := openMySQLProcess(uint32(process.Pid), false)
	if err != nil {
		return false, err
	}
	defer root.close()
	if !root.alive() {
		return false, nil
	}
	pid, err := mysqlListenerPID(port)
	if err != nil || pid == 0 {
		return false, err
	}
	if pid == root.pid {
		return root.alive(), nil
	}
	parents, err := mysqlProcessParents()
	if err != nil {
		return false, err
	}
	owned, err := ownedMySQLDescendant(root, pid, parents, false)
	if owned == nil {
		return false, err
	}
	defer owned.close()
	return owned.alive() && root.alive(), nil
}

func mysqlListenerPID(port int) (uint32, error) {
	const (
		afInet                   = 2
		tcpTableOwnerPIDListener = 3
		errorInsufficientBuffer  = 122
	)
	var size uint32
	status, _, _ := procGetExtendedTCPTable.Call(0, uintptr(unsafe.Pointer(&size)), 0, afInet, tcpTableOwnerPIDListener, 0)
	if status != errorInsufficientBuffer {
		return 0, fmt.Errorf("GetExtendedTcpTable size: %w", syscall.Errno(status))
	}
	for attempts := 0; attempts < 3; attempts++ {
		if size < 4 || size > 16<<20 {
			return 0, fmt.Errorf("invalid TCP table size %d", size)
		}
		buffer := make([]byte, size)
		status, _, _ = procGetExtendedTCPTable.Call(uintptr(unsafe.Pointer(&buffer[0])), uintptr(unsafe.Pointer(&size)), 0, afInet, tcpTableOwnerPIDListener, 0)
		if status == errorInsufficientBuffer {
			continue
		}
		if status != 0 {
			return 0, fmt.Errorf("GetExtendedTcpTable: %w", syscall.Errno(status))
		}
		count := binary.LittleEndian.Uint32(buffer[:4])
		const rowSize = 24
		if uint64(count)*rowSize+4 > uint64(len(buffer)) {
			return 0, fmt.Errorf("invalid TCP listener count %d", count)
		}
		for i := uint32(0); i < count; i++ {
			row := buffer[4+int(i)*rowSize : 4+int(i+1)*rowSize]
			if binary.LittleEndian.Uint32(row[:4]) == 2 &&
				binary.LittleEndian.Uint32(row[4:8]) == 0x0100007f &&
				binary.BigEndian.Uint16(row[8:10]) == uint16(port) {
				return binary.LittleEndian.Uint32(row[20:24]), nil
			}
		}
		return 0, nil
	}
	return 0, fmt.Errorf("TCP table changed repeatedly during ownership check")
}

func (tracker *mysqlProcessTracker) collectOwnedChildrenLocked(parents map[uint32]uint32) (int, error) {
	added := 0
	var failures []error
	for pid := range parents {
		if tracker.owned[pid] != nil {
			continue
		}
		held, err := openOwnedMySQLChain(tracker.root, pid, parents, tracker.owned, true)
		if err != nil {
			failures = append(failures, err)
		}
		for _, process := range held {
			tracker.owned[process.pid] = process
			added++
		}
	}
	return added, errors.Join(failures...)
}

// Stop the monitor before its children, then take another fresh snapshot after
// the stopped processes finish. A child started after the first snapshot is
// still bound to the original retained monitor or a verified ancestor. Repeating
// this for newly found children also covers their late descendants. The shared
// deadline bounds all waits, rather than granting every child a new timeout.
func (tracker *mysqlProcessTracker) stopOwnedTreeLocked() error {
	parents, err := mysqlProcessParents()
	return tracker.stopOwnedTreeFromSnapshotLocked(parents, err)
}

func (tracker *mysqlProcessTracker) stopOwnedTreeFromSnapshotLocked(parents map[uint32]uint32, snapshotErr error) error {
	if tracker.closed {
		return os.ErrProcessDone
	}
	var failures []error
	if snapshotErr != nil {
		failures = append(failures, snapshotErr)
	}
	if _, err := tracker.collectOwnedChildrenLocked(parents); err != nil {
		failures = append(failures, err)
	}
	deadline := time.Now().Add(5 * time.Second)
	for round := 0; round < maxMySQLParentDepth; round++ {
		// The root is first so an active monitor cannot respawn its listener.
		ordered := []*mysqlNativeProcess{tracker.root}
		for pid, process := range tracker.owned {
			if pid != tracker.root.pid {
				ordered = append(ordered, process)
			}
		}
		for _, process := range ordered {
			if process.alive() {
				if err := syscall.TerminateProcess(process.handle, 1); err != nil {
					failures = append(failures, fmt.Errorf("terminate owned MySQL process %d: %w", process.pid, err))
				}
			}
		}
		for _, process := range ordered {
			remaining := max(time.Until(deadline), 0)
			status, err := syscall.WaitForSingleObject(process.handle, uint32(remaining.Milliseconds()))
			if err != nil || status != syscall.WAIT_OBJECT_0 {
				failures = append(failures, fmt.Errorf("owned MySQL process %d did not finish cleanup (wait=%d): %v", process.pid, status, err))
			}
		}
		parents, err := mysqlProcessParents()
		if err != nil {
			failures = append(failures, err)
		}
		added, err := tracker.collectOwnedChildrenLocked(parents)
		if err != nil {
			failures = append(failures, err)
		}
		if added == 0 {
			return errors.Join(failures...)
		}
	}
	// Even at the bounded ancestry limit, terminate the last collected handles;
	// exhausting the wait budget must not leave a newly verified child running.
	for _, process := range tracker.owned {
		if process.alive() {
			if err := syscall.TerminateProcess(process.handle, 1); err != nil {
				failures = append(failures, err)
			}
		}
	}
	failures = append(failures, errors.New("MySQL descendant cleanup reached its ancestry limit"))
	return errors.Join(failures...)
}

func killMySQLProcessTree(process *os.Process) error {
	if process == nil || process.Pid <= 0 {
		return os.ErrProcessDone
	}
	tracker := trackedMySQLProcess(process)
	if tracker == nil {
		// Without a start-time identity, only os.Process's original handle is
		// safe to terminate. Never discover a tree by reopening an unheld PID.
		return process.Kill()
	}
	tracker.mu.Lock()
	defer tracker.mu.Unlock()
	return tracker.stopOwnedTreeLocked()
}
