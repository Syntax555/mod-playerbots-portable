package main

import (
	"context"
	"fmt"
	"io"
	"os"
	"strings"
	"sync"
	"time"
)

func startPortableUpdateProgress(ctx context.Context) *portableUpdateProgress {
	console := portableUpdateConsole(os.Stdout)
	interval := 5 * time.Second
	if console {
		interval = 250 * time.Millisecond
	}
	return newPortableUpdateProgress(ctx, os.Stdout, console, interval)
}

// Update percentages describe checked files or expanded changed-file bytes.
// HTTP metadata and ZIP-index requests have no known denominator and show activity
// instead. A completed byte count never implies that SHA256 verification passed.
type portableUpdateProgress struct {
	mu          sync.Mutex
	output      io.Writer
	console     bool
	stop        chan struct{}
	stopped     chan struct{}
	closed      bool
	label       string
	unit        string
	total       int64
	done        int64
	filesTotal  int64
	filesDone   int64
	complete    bool
	started     time.Time
	ticks       int
	lineVisible bool
}

func newPortableUpdateProgress(ctx context.Context, output io.Writer, console bool, interval time.Duration) *portableUpdateProgress {
	progress := &portableUpdateProgress{
		output: output, console: console, stop: make(chan struct{}), stopped: make(chan struct{}),
	}
	go func() {
		defer close(progress.stopped)
		ticker := time.NewTicker(interval)
		defer ticker.Stop()
		for {
			select {
			case <-ticker.C:
				progress.mu.Lock()
				if !progress.closed && progress.label != "" && !progress.complete {
					progress.ticks++
					progress.renderLocked()
				}
				progress.mu.Unlock()
			case <-ctx.Done():
				return
			case <-progress.stop:
				return
			}
		}
	}()
	return progress
}

func optionalUpdateProgress(progress []*portableUpdateProgress) *portableUpdateProgress {
	if len(progress) == 0 {
		return nil
	}
	return progress[0]
}

func (p *portableUpdateProgress) begin(label, unit string, total, files int64) {
	if p == nil {
		return
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.closed {
		return
	}
	p.finishLineLocked()
	p.label, p.unit, p.total, p.filesTotal = label, unit, total, files
	p.done, p.filesDone, p.ticks = 0, 0, 0
	p.complete, p.started = false, time.Now()
	if p.console {
		fmt.Fprintf(p.output, "Update: %s\n", label)
	}
	p.renderLocked()
}

func (p *portableUpdateProgress) add(amount int64) {
	if p == nil {
		return
	}
	p.mu.Lock()
	p.done += amount
	p.mu.Unlock()
}

func (p *portableUpdateProgress) verifiedFile() {
	if p == nil {
		return
	}
	p.mu.Lock()
	p.filesDone++
	p.mu.Unlock()
}

func (p *portableUpdateProgress) finish() {
	if p == nil {
		return
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.closed || p.label == "" {
		return
	}
	// Only the caller can declare success after validation or durable commit.
	// Keep an inconsistent or oversize transfer visibly incomplete.
	p.complete = (p.unit == "" || p.done == p.total) && p.filesDone == p.filesTotal
	p.renderLocked()
	p.finishLineLocked()
}

func (p *portableUpdateProgress) close() {
	if p == nil {
		return
	}
	p.mu.Lock()
	if p.closed {
		p.mu.Unlock()
		return
	}
	p.closed = true
	if p.label != "" && !p.complete {
		p.renderLocked()
	}
	p.mu.Unlock()
	close(p.stop)
	<-p.stopped
	p.mu.Lock()
	p.finishLineLocked()
	p.mu.Unlock()
}

func (p *portableUpdateProgress) renderLocked() {
	seconds := int(time.Since(p.started) / time.Second)
	var detail string
	if p.unit == "" {
		if p.complete {
			detail = fmt.Sprintf("Done (%ds)", seconds)
		} else {
			detail = fmt.Sprintf("%c Working... (%ds)", "|/-\\"[p.ticks%4], seconds)
		}
	} else {
		percent := int64(0)
		if p.total > 0 {
			percent = p.done * 100 / p.total
		}
		if p.complete {
			percent = 100
		} else if percent >= 100 {
			percent = 99
		}
		if percent < 0 {
			percent = 0
		}
		filled := int(percent / 5)
		detail = fmt.Sprintf("[%s%s] %3d%% ", strings.Repeat("#", filled), strings.Repeat("-", 20-filled), percent)
		if p.unit == "bytes" {
			detail += fmt.Sprintf("%.1f/%.1f MiB unpacked; %d/%d files", float64(p.done)/(1<<20), float64(p.total)/(1<<20), p.filesDone, p.filesTotal)
		} else {
			detail += fmt.Sprintf("%d/%d files", p.done, p.total)
		}
		detail += fmt.Sprintf(" (%ds)", seconds)
	}
	if p.console {
		// Avoid ANSI requirements and line wrapping in the usual 80-column
		// Windows console; overwrite remnants when the status becomes shorter.
		fmt.Fprintf(p.output, "\r%-78.78s", "  "+detail)
		p.lineVisible = true
	} else {
		fmt.Fprintf(p.output, "Update: %s: %s\n", p.label, detail)
	}
}

func (p *portableUpdateProgress) finishLineLocked() {
	if p.lineVisible {
		fmt.Fprintln(p.output)
		p.lineVisible = false
	}
}

// Count bytes only after they have actually reached the staged file and hash.
type updateProgressWriter struct {
	output   io.Writer
	progress *portableUpdateProgress
}

func (w updateProgressWriter) Write(content []byte) (int, error) {
	n, err := w.output.Write(content)
	w.progress.add(int64(n))
	return n, err
}
