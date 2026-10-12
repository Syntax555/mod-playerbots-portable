package main

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"sync"
	"time"
)

type ProcessSupervisor struct {
	name          string
	startFunc     func() (*exec.Cmd, error)
	killProcess   func(*os.Process) error
	finishProcess func(*exec.Cmd) error
	restartDelay  time.Duration

	mu              sync.Mutex
	currentCmd      *exec.Cmd
	interruptTarget *os.Process
	stopRequested   bool
	killRequested   bool
	interruptedCmd  *exec.Cmd
	stopped         bool
	doneChan        chan struct{}
}

func newProcessSupervisor(name string, startFunc func() (*exec.Cmd, error), restartDelay time.Duration) *ProcessSupervisor {
	return &ProcessSupervisor{
		name:         name,
		startFunc:    startFunc,
		restartDelay: restartDelay,
		doneChan:     make(chan struct{}),
	}
}

func (ps *ProcessSupervisor) setCurrentCmdLocked(cmd *exec.Cmd) {
	if ps.currentCmd == cmd {
		return
	}
	if ps.interruptTarget != nil {
		_ = ps.interruptTarget.Release()
		ps.interruptTarget = nil
	}
	ps.currentCmd = cmd
	if cmd != nil && cmd.Process != nil {
		// Keep an independent Windows process handle until Wait completes. This
		// prevents a completed child's PID from being reused during dispatch.
		ps.interruptTarget, _ = os.FindProcess(cmd.Process.Pid)
	}
}

func (ps *ProcessSupervisor) IsRunning() bool {
	ps.mu.Lock()
	defer ps.mu.Unlock()
	if ps.currentCmd == nil || ps.interruptTarget == nil {
		return false
	}
	alive, _ := isProcessAlive(ps.interruptTarget.Pid)
	return alive
}

func (ps *ProcessSupervisor) RetainCurrentProcess() *os.Process {
	ps.mu.Lock()
	defer ps.mu.Unlock()
	if ps.interruptTarget == nil {
		return nil
	}
	process, _ := os.FindProcess(ps.interruptTarget.Pid)
	return process
}

func (ps *ProcessSupervisor) MarkStopped() {
	ps.mu.Lock()
	defer ps.mu.Unlock()
	ps.stopped = true
}

func (ps *ProcessSupervisor) Kill() {
	ps.mu.Lock()
	ps.stopped = true
	ps.killRequested = true
	cmd := ps.currentCmd
	killProcess := ps.killProcess
	treeCleanup := killProcess != nil
	var retained *os.Process
	if killProcess != nil && ps.interruptTarget != nil {
		// Retain while the supervisor still holds the original handle. Wait
		// may finish as soon as we release this lock; a PID-only reopen after
		// that would risk binding tree cleanup to a different process.
		retained, _ = os.FindProcess(ps.interruptTarget.Pid)
	}
	ps.mu.Unlock()
	if retained != nil {
		defer retained.Release()
	}

	if cmd != nil && cmd.Process != nil {
		fmt.Printf("Stopping %s (PID: %d)...\n", ps.name, cmd.Process.Pid)
		if killProcess == nil {
			killProcess = (*os.Process).Kill
		}
		target := cmd.Process
		if retained != nil {
			target = retained
		} else if treeCleanup {
			// The original os.Process can still safely kill its own handle, but
			// do not discover descendants without a retained root identity.
			killProcess = (*os.Process).Kill
		}
		if err := killProcess(target); err != nil && !errors.Is(err, os.ErrProcessDone) {
			fmt.Fprintf(os.Stderr, "Could not terminate %s: %v\n", ps.name, err)
		}
	}
}

func (ps *ProcessSupervisor) StopAndWait(gracePeriod time.Duration) {
	ps.requestGracefulStop()

	select {
	case <-ps.doneChan:
		return
	case <-time.After(gracePeriod):
		fmt.Printf("%s did not stop within %v, killing process...\n", ps.name, gracePeriod)
		ps.Kill()
		<-ps.doneChan
	}
}

func (ps *ProcessSupervisor) requestGracefulStop() {
	ps.mu.Lock()
	defer ps.mu.Unlock()
	ps.stopped = true
	ps.stopRequested = true
	cmd := ps.currentCmd
	if cmd == nil || cmd.Process == nil || ps.interruptTarget == nil || ps.interruptedCmd == cmd {
		return
	}
	ps.interruptedCmd = cmd
	fmt.Printf("Requesting graceful shutdown of %s (PID: %d)...\n", ps.name, cmd.Process.Pid)
	if err := interruptConsoleProcess(ps.interruptTarget); err != nil && !errors.Is(err, os.ErrProcessDone) {
		fmt.Fprintf(os.Stderr, "Could not signal %s; waiting for its shutdown grace period: %v\n", ps.name, err)
	}
}

func (ps *ProcessSupervisor) Run(ctx context.Context, initialCmd *exec.Cmd, wg *sync.WaitGroup) {
	if wg != nil {
		defer wg.Done()
	}
	defer close(ps.doneChan)

	cmd := initialCmd
	for {
		if cmd == nil {
			ps.mu.Lock()
			stopped := ps.stopped
			ps.mu.Unlock()
			if stopped || ctx.Err() != nil {
				return
			}

			var err error
			cmd, err = ps.startFunc()
			if err != nil {
				ps.mu.Lock()
				stopped = ps.stopped
				ps.mu.Unlock()
				if stopped || ctx.Err() != nil {
					return
				}

				select {
				case <-ctx.Done():
					return
				default:
					fmt.Fprintf(os.Stderr, "Failed to start %s: %v\n", ps.name, err)
				}

				select {
				case <-ctx.Done():
					return
				case <-time.After(ps.restartDelay):
					continue
				}
			}
		}

		ps.mu.Lock()
		ps.setCurrentCmdLocked(cmd)
		stopRequested := ps.stopRequested
		killRequested := ps.killRequested
		cancelledWithoutStop := ctx.Err() != nil && !ps.stopped
		ps.mu.Unlock()
		if killRequested || cancelledWithoutStop {
			ps.Kill()
		} else if stopRequested {
			ps.requestGracefulStop()
		}

		err := cmd.Wait()
		if ps.finishProcess != nil {
			if cleanupErr := ps.finishProcess(cmd); cleanupErr != nil && !errors.Is(cleanupErr, os.ErrProcessDone) {
				fmt.Fprintf(os.Stderr, "Could not clean up %s: %v\n", ps.name, cleanupErr)
			}
		}

		ps.mu.Lock()
		ps.setCurrentCmdLocked(nil)
		stopped := ps.stopped
		ps.mu.Unlock()

		if stopped || ctx.Err() != nil {
			return
		}

		if err != nil {
			fmt.Printf("\n[%s] Process exited: %v\n", ps.name, err)
		} else {
			fmt.Printf("\n[%s] Process stopped.\n", ps.name)
		}

		fmt.Printf("[%s] Restarting in %v...\n", ps.name, ps.restartDelay)

		select {
		case <-ctx.Done():
			return
		case <-time.After(ps.restartDelay):
		}

		cmd = nil
	}
}

// waitForReady polls probe every 500 ms until it reports readiness or an
// error, the launched process exits, or the timeout expires.
func waitForReady(ctx context.Context, cmd *exec.Cmd, name string, timeout time.Duration, probe func(context.Context) (bool, error)) error {
	waitCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()

	for {
		select {
		case <-waitCtx.Done():
			if errors.Is(waitCtx.Err(), context.Canceled) {
				return fmt.Errorf("interrupted waiting for %s", name)
			}
			return fmt.Errorf("timed out waiting for %s after %v", name, timeout)
		case <-ticker.C:
			if cmd != nil && cmd.Process != nil {
				if alive, exitCode := isProcessAlive(cmd.Process.Pid); !alive {
					return fmt.Errorf("%s process exited prematurely (PID: %d, exit code: %d)", name, cmd.Process.Pid, exitCode)
				}
			}
			if ready, err := probe(waitCtx); ready || err != nil {
				return err
			}
		}
	}
}

func waitForAuthServerReady(ctx context.Context, cmd *exec.Cmd, hosts []string, port int, timeout time.Duration) error {
	fmt.Printf("Waiting for authserver to initialize and listen on port %d...\n", port)
	return waitForReady(ctx, cmd, "authserver", timeout, func(context.Context) (bool, error) {
		if !acceptsConnection(hosts, port, 500*time.Millisecond) {
			return false, nil
		}
		fmt.Println("Authserver is online and ready.")
		return true, nil
	})
}

func startServerProcess(name, exePath, workDir string, stdin *os.File) (*exec.Cmd, error) {
	cmd := exec.Command(exePath)
	if workDir != "" {
		cmd.Dir = workDir
	}
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if stdin != nil {
		cmd.Stdin = stdin
	}
	configureConsoleProcess(cmd)

	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("failed to start %s: %w", name, err)
	}

	fmt.Printf("%s started successfully (PID: %d).\n", name, cmd.Process.Pid)
	return cmd, nil
}

func stopProcess(name string, cmd *exec.Cmd) {
	if cmd == nil || cmd.Process == nil {
		return
	}

	ps := newProcessSupervisor(name, nil, 0)
	go ps.Run(context.Background(), cmd, nil)
	ps.StopAndWait(10 * time.Second)
}
