package main

import (
	"archive/zip"
	"bytes"
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

const defaultClientDataURL = "https://github.com/wowgaming/client-data/releases/download/v20.0/Data.zip"

const createMySQLSQL = `
CREATE USER IF NOT EXISTS 'acore'@'localhost' IDENTIFIED BY 'acore' WITH MAX_QUERIES_PER_HOUR 0 MAX_CONNECTIONS_PER_HOUR 0 MAX_UPDATES_PER_HOUR 0;

CREATE DATABASE IF NOT EXISTS ` + "`acore_world`" + ` DEFAULT CHARACTER SET UTF8MB4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS ` + "`acore_characters`" + ` DEFAULT CHARACTER SET UTF8MB4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS ` + "`acore_auth`" + ` DEFAULT CHARACTER SET UTF8MB4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS ` + "`acore_playerbots`" + ` DEFAULT CHARACTER SET UTF8MB4 COLLATE utf8mb4_unicode_ci;

GRANT ALL PRIVILEGES ON ` + "`acore_world`" + ` . * TO 'acore'@'localhost' WITH GRANT OPTION;
GRANT ALL PRIVILEGES ON ` + "`acore_characters`" + ` . * TO 'acore'@'localhost' WITH GRANT OPTION;
GRANT ALL PRIVILEGES ON ` + "`acore_auth`" + ` . * TO 'acore'@'localhost' WITH GRANT OPTION;
GRANT ALL PRIVILEGES ON ` + "`acore_playerbots`" + ` . * TO 'acore'@'localhost' WITH GRANT OPTION;
`

type startupOptions struct {
	mysqlDir         string
	dataDir          string
	mysqlCnf         string
	port             int
	portSet          bool
	authPort         int
	authPortSet      bool
	timeout          int
	initOnly         bool
	skipSQL          bool
	skipDataCheck    bool
	dataURL          string
	downloadDataOnly bool
	noUpdate         bool
	setExpansion     string
	showExpansion    bool
}

type mysqlBinaries struct {
	mysqld     string
	mysql      string
	mysqladmin string
}

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

func dirExists(path string) bool {
	if path == "" {
		return false
	}
	info, err := os.Stat(path)
	return err == nil && info.IsDir()
}

func fileExists(path string) bool {
	if path == "" {
		return false
	}
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}

func findDefaultMySQLDir() string {
	// 1. Check relative to executable directory: <exeDir>/mysql
	if exePath, err := os.Executable(); err == nil {
		exeDir := filepath.Dir(exePath)
		candidate := filepath.Join(exeDir, "mysql")
		if dirExists(candidate) {
			return candidate
		}
	}

	// 2. Check current working directory: ./mysql
	if dirExists("mysql") {
		absPath, err := filepath.Abs("mysql")
		if err == nil {
			return absPath
		}
		return "mysql"
	}

	// 3. Check MYSQL_ROOT environment variable
	if envVal := os.Getenv("MYSQL_ROOT"); envVal != "" && dirExists(envVal) {
		return envVal
	}

	// 4. Check dist/mysql relative to cwd
	if dirExists(filepath.Join("dist", "mysql")) {
		absPath, err := filepath.Abs(filepath.Join("dist", "mysql"))
		if err == nil {
			return absPath
		}
		return filepath.Join("dist", "mysql")
	}

	// 5. Check deps/mysql-* directory
	depsPattern := filepath.Join("deps", "mysql-*")
	if matches, err := filepath.Glob(depsPattern); err == nil {
		for _, m := range matches {
			if dirExists(m) {
				absPath, err := filepath.Abs(m)
				if err == nil {
					return absPath
				}
				return m
			}
		}
	}

	return ""
}

func parseArgs(args []string) (startupOptions, error) {
	var opts startupOptions

	fs := flag.NewFlagSet("startup", flag.ContinueOnError)

	defaultMysql := findDefaultMySQLDir()

	fs.StringVar(&opts.mysqlDir, "mysql-dir", defaultMysql, "Path to MySQL root directory. Default: ./mysql or $env:MYSQL_ROOT")
	fs.StringVar(&opts.dataDir, "data-dir", "", "Path to MySQL data directory. Default: <work-dir>/mysql/data")
	fs.StringVar(&opts.mysqlCnf, "mysql-cnf", "", "Path to MySQL configuration file (my.cnf or my.ini). Default: auto-detected in <work-dir>/mysql")
	fs.IntVar(&opts.port, "port", 3306, "MySQL server port.")
	fs.IntVar(&opts.authPort, "auth-port", 3724, "Authserver realm port.")
	fs.IntVar(&opts.timeout, "timeout", 30, "Timeout in seconds to wait for MySQL to become ready.")
	fs.BoolVar(&opts.initOnly, "init-only", false, "Initialize MySQL data dir, start server, apply SQL script, and exit.")
	fs.BoolVar(&opts.skipSQL, "skip-sql", false, "Skip executing the embedded create_mysql.sql script.")
	fs.BoolVar(&opts.skipDataCheck, "skip-data-check", false, "Skip checking and downloading client data (maps, vmaps, mmaps, dbc).")
	fs.StringVar(&opts.dataURL, "data-url", defaultClientDataURL, "Custom URL to download client data Data.zip from.")
	fs.BoolVar(&opts.downloadDataOnly, "download-data-only", false, "Download and extract client data, then exit.")
	fs.BoolVar(&opts.noUpdate, "no-update", false, "Start without checking GitHub for a server update.")
	fs.StringVar(&opts.setExpansion, "set-expansion", "", "Set progression mode (individual, vanilla, tbc or wotlk) with config backups, then exit. Stop the realm first.")
	fs.BoolVar(&opts.showExpansion, "show-expansion", false, "Show the selected realm expansion and level cap, then exit.")

	fs.Usage = func() {
		fmt.Fprintf(fs.Output(), "Usage of mod-playerbots startup tool:\n\n")
		fmt.Fprintf(fs.Output(), "Start MySQL server in console mode and initialize AzerothCore database.\n\nOptions:\n")
		fs.PrintDefaults()
	}

	if err := fs.Parse(args); err != nil {
		return opts, err
	}
	if fs.NArg() != 0 {
		return opts, fmt.Errorf("unexpected argument %q", fs.Arg(0))
	}
	if opts.port < 1 || opts.port > 65535 || opts.authPort < 1 || opts.authPort > 65535 {
		return opts, errors.New("MySQL and authserver ports must be between 1 and 65535")
	}
	if opts.timeout <= 0 {
		return opts, errors.New("timeout must be greater than zero")
	}
	setExpansionSelected := false
	fs.Visit(func(option *flag.Flag) {
		switch option.Name {
		case "set-expansion":
			setExpansionSelected = true
		case "port":
			opts.portSet = true
		case "auth-port":
			opts.authPortSet = true
		}
	})
	if setExpansionSelected {
		phase, err := parseRealmPhase(opts.setExpansion)
		if err != nil {
			return opts, err
		}
		opts.setExpansion = phase.name
	}
	if (opts.setExpansion != "" || opts.showExpansion) && (opts.initOnly || opts.downloadDataOnly || (opts.setExpansion != "" && opts.showExpansion)) {
		return opts, errors.New("expansion commands cannot be combined with other launcher modes")
	}

	return opts, nil
}

func findExecutable(dir, name string) string {
	exts := []string{".exe", ".bat", ".cmd", ""}

	if dir != "" {
		for _, ext := range exts {
			fullPath := filepath.Join(dir, name+ext)
			if fileExists(fullPath) {
				return fullPath
			}
		}
	}

	for _, ext := range exts {
		if path, err := exec.LookPath(name + ext); err == nil {
			return path
		}
	}

	return ""
}

func findMySQLBinaries(mysqlDir string) (*mysqlBinaries, error) {
	binDir := ""
	if mysqlDir != "" {
		binDir = filepath.Join(mysqlDir, "bin")
		if !dirExists(binDir) {
			binDir = mysqlDir
		}
	}

	mysqld := findExecutable(binDir, "mysqld")
	mysql := findExecutable(binDir, "mysql")
	mysqladmin := findExecutable(binDir, "mysqladmin")

	var missing []string
	if mysqld == "" {
		missing = append(missing, "mysqld")
	}
	if mysql == "" {
		missing = append(missing, "mysql")
	}
	if mysqladmin == "" {
		missing = append(missing, "mysqladmin")
	}

	if len(missing) > 0 {
		return nil, fmt.Errorf("required MySQL binaries not found (%s) in %s or PATH", strings.Join(missing, ", "), binDir)
	}

	return &mysqlBinaries{
		mysqld:     mysqld,
		mysql:      mysql,
		mysqladmin: mysqladmin,
	}, nil
}

func isDataDirInitialized(dataDir string) bool {
	if !dirExists(dataDir) {
		return false
	}

	entries, err := os.ReadDir(dataDir)
	if err != nil || len(entries) == 0 {
		return false
	}

	return true
}

func isClientDataPresent(dataDir string) bool {
	if !dirExists(dataDir) {
		return false
	}

	requiredDirs := []string{"dbc", "maps", "vmaps", "mmaps"}
	for _, req := range requiredDirs {
		subDir := filepath.Join(dataDir, req)
		if !dirExists(subDir) {
			return false
		}
		entries, err := os.ReadDir(subDir)
		if err != nil || len(entries) == 0 {
			return false
		}
	}
	return true
}

func downloadFileWithProgress(ctx context.Context, url string, destPath string) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return fmt.Errorf("failed to create download request: %w", err)
	}
	req.Header.Set("User-Agent", "AzerothCore-Playerbots-Launcher/1.0")

	client := &http.Client{
		Transport: &http.Transport{
			Proxy:                 http.ProxyFromEnvironment,
			DialContext:           (&net.Dialer{Timeout: 30 * time.Second, KeepAlive: 30 * time.Second}).DialContext,
			TLSHandshakeTimeout:   15 * time.Second,
			ResponseHeaderTimeout: 60 * time.Second,
		},
	}
	defer client.CloseIdleConnections()

	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to connect to %s: %w", url, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("server returned HTTP %s", resp.Status)
	}

	tmpPath := destPath + ".download"
	if err := os.MkdirAll(filepath.Dir(tmpPath), 0755); err != nil {
		return fmt.Errorf("failed to create download directory: %w", err)
	}

	out, err := os.OpenFile(tmpPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0644)
	if err != nil {
		return fmt.Errorf("failed to create temporary file %s: %w", tmpPath, err)
	}
	finalized := false
	defer func() {
		if !finalized {
			out.Close()
			_ = os.Remove(tmpPath)
		}
	}()

	progress := newDownloadProgress(resp.ContentLength)
	// The request context also cancels reading the response body.
	_, err = io.Copy(io.MultiWriter(out, progress), resp.Body)
	progress.finish()
	if err != nil {
		return fmt.Errorf("failed to download to %s: %w", tmpPath, err)
	}
	if err := out.Close(); err != nil {
		return fmt.Errorf("failed to close downloaded file: %w", err)
	}

	if err := os.Rename(tmpPath, destPath); err != nil {
		return fmt.Errorf("failed to finalize downloaded file: %w", err)
	}
	finalized = true

	return nil
}

// downloadProgress reports the bytes written to a download. A console shows a
// status line that is redrawn in place; redirected output gets a complete line
// every few seconds instead of carriage-return frames.
type downloadProgress struct {
	console  bool
	interval time.Duration
	total    int64
	done     int64
	started  time.Time
	printed  time.Time
}

func newDownloadProgress(total int64) *downloadProgress {
	now := time.Now()
	progress := &downloadProgress{console: portableUpdateConsole(os.Stdout), interval: 5 * time.Second, total: total, started: now, printed: now}
	if progress.console {
		progress.interval = 200 * time.Millisecond
	}
	return progress
}

func (p *downloadProgress) Write(content []byte) (int, error) {
	p.done += int64(len(content))
	if now := time.Now(); now.Sub(p.printed) >= p.interval {
		p.printed = now
		p.print(now)
	}
	return len(content), nil
}

func (p *downloadProgress) finish() {
	p.print(time.Now())
	if p.console {
		fmt.Println()
	}
}

func (p *downloadProgress) print(now time.Time) {
	const mb = 1024 * 1024
	speed := 0.0
	if elapsed := now.Sub(p.started).Seconds(); elapsed > 0 {
		speed = float64(p.done) / mb / elapsed
	}
	if p.total <= 0 {
		printProgress(p.console, "%6.1f MB downloaded (%5.1f MB/s)", float64(p.done)/mb, speed)
		return
	}
	percent := min(float64(p.done)/float64(p.total)*100, 100)
	const barWidth = 25
	filled := int(percent / 100 * barWidth)
	bar := strings.Repeat("=", filled)
	if filled < barWidth {
		bar += ">" + strings.Repeat(" ", barWidth-filled-1)
	}
	eta := 0
	if speed > 0 {
		eta = int(float64(p.total-p.done) / mb / speed)
	}
	printProgress(p.console, "[%s] %5.1f%% (%6.1f / %6.1f MB) %5.1f MB/s (ETA: %ds)",
		bar, percent, float64(p.done)/mb, float64(p.total)/mb, speed, eta)
}

// printProgress redraws a status line on a console and writes complete lines
// when output is redirected to a file.
func printProgress(console bool, format string, args ...any) {
	if console {
		fmt.Printf("\r  "+format+"  ", args...)
	} else {
		fmt.Printf("  "+format+"\n", args...)
	}
}

type contextReader struct {
	ctx    context.Context
	reader io.Reader
}

func (r contextReader) Read(p []byte) (int, error) {
	if err := r.ctx.Err(); err != nil {
		return 0, err
	}
	return r.reader.Read(p)
}

func extractZip(ctx context.Context, zipPath string, destDir string) error {
	r, err := zip.OpenReader(zipPath)
	if err != nil {
		return fmt.Errorf("failed to open zip archive %s: %w", zipPath, err)
	}
	defer r.Close()

	cleanDestDir, err := filepath.Abs(destDir)
	if err != nil {
		return fmt.Errorf("failed to resolve destination directory %s: %w", destDir, err)
	}
	if err := os.MkdirAll(cleanDestDir, 0755); err != nil {
		return fmt.Errorf("failed to create destination directory %s: %w", cleanDestDir, err)
	}

	// Normalize Windows archive separators on every host and detect the Data root
	// with the same case-insensitive comparison used when removing it.
	entryNames := make([]string, len(r.File))
	hasCommonRoot := len(r.File) > 0
	for i, f := range r.File {
		name := strings.ReplaceAll(f.Name, `\`, "/")
		// IsLocal rejects absolute and escaping paths. Reject colons explicitly
		// so Windows drive paths and alternate streams are also rejected on Unix.
		if !filepath.IsLocal(filepath.FromSlash(name)) || strings.Contains(name, ":") {
			return fmt.Errorf("illegal file path in zip archive: %s", f.Name)
		}
		entryNames[i] = name
		root, _, hasSeparator := strings.Cut(name, "/")
		if !strings.EqualFold(root, "data") || (!hasSeparator && !f.FileInfo().IsDir()) {
			hasCommonRoot = false
		}
	}

	totalFiles := len(r.File)
	console := portableUpdateConsole(os.Stdout)
	fmt.Printf("Extracting %d files into %s...\n", totalFiles, cleanDestDir)

	for i, f := range r.File {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		relName := entryNames[i]
		if hasCommonRoot {
			_, relName, _ = strings.Cut(relName, "/")
		}
		if relName == "" || relName == "." {
			continue
		}

		// Removing Data/ can expose traversal or an absolute path that was
		// contained in the original name, such as Data/../file or Data//file.
		localName := filepath.FromSlash(relName)
		if !filepath.IsLocal(localName) {
			return fmt.Errorf("illegal file path in zip archive: %s", f.Name)
		}
		targetPath := filepath.Join(cleanDestDir, localName)

		if f.FileInfo().IsDir() || strings.HasSuffix(relName, "/") {
			if err := os.MkdirAll(targetPath, 0755); err != nil {
				return err
			}
			continue
		}

		if err := os.MkdirAll(filepath.Dir(targetPath), 0755); err != nil {
			return err
		}

		outFile, err := os.OpenFile(targetPath, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, f.Mode())
		if err != nil {
			return fmt.Errorf("failed to create destination file %s: %w", targetPath, err)
		}

		rc, err := f.Open()
		if err != nil {
			outFile.Close()
			return fmt.Errorf("failed to read zip entry %s: %w", f.Name, err)
		}

		_, err = io.Copy(outFile, contextReader{ctx: ctx, reader: rc})
		readCloseErr := rc.Close()
		writeCloseErr := outFile.Close()
		if err != nil {
			return fmt.Errorf("failed writing to %s: %w", targetPath, err)
		}
		if readCloseErr != nil {
			return fmt.Errorf("failed to close zip entry %s: %w", f.Name, readCloseErr)
		}
		if writeCloseErr != nil {
			return fmt.Errorf("failed to close extracted file %s: %w", targetPath, writeCloseErr)
		}

		if (i+1)%500 == 0 || i+1 == totalFiles {
			printProgress(console, "Extracting client data: %d / %d files (%d%%)", i+1, totalFiles, (i+1)*100/totalFiles)
		}
	}

	if console {
		fmt.Println()
	}
	fmt.Println("Client data extracted successfully.")
	return nil
}

func ensureClientData(ctx context.Context, workDir, baseDir, dataURL string, skipCheck bool) error {
	if skipCheck {
		return nil
	}

	workDataDir := filepath.Join(workDir, "data")
	baseDataDir := filepath.Join(baseDir, "data")

	// 1. Check if client data is already present in baseDir/data or workDir/data
	if dirExists(baseDataDir) && isClientDataPresent(baseDataDir) {
		fmt.Printf("Client data verified at %s.\n", baseDataDir)
		return nil
	}
	if dirExists(workDataDir) && isClientDataPresent(workDataDir) {
		fmt.Printf("Client data verified at %s.\n", workDataDir)
		return nil
	}

	fmt.Println("\n=== Client Data Verification ===")
	fmt.Printf("Required client data (dbc, maps, vmaps, mmaps) not found in %s.\n", workDataDir)
	if dataURL == "" {
		dataURL = defaultClientDataURL
	}

	if err := os.MkdirAll(workDir, 0755); err != nil {
		return fmt.Errorf("failed to create working directory %s: %w", workDir, err)
	}
	stageDir, err := os.MkdirTemp(workDir, ".client-data-stage-")
	if err != nil {
		return fmt.Errorf("failed to create client data staging directory: %w", err)
	}
	defer os.RemoveAll(stageDir)
	stageDataDir := filepath.Join(stageDir, "data")
	zipPath := filepath.Join(stageDir, "Data.zip")
	fmt.Printf("Downloading client data from %s...\n", dataURL)

	if err := downloadFileWithProgress(ctx, dataURL, zipPath); err != nil {
		return fmt.Errorf("failed to download client data: %w", err)
	}
	if err := extractZip(ctx, zipPath, stageDataDir); err != nil {
		return fmt.Errorf("failed to extract client data: %w", err)
	}

	if !isClientDataPresent(stageDataDir) {
		return errors.New("client data archive is missing populated required folders (dbc, maps, vmaps, mmaps)")
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	return activateClientData(stageDataDir, workDataDir)
}

// The previous directory is retained if it contains user data. Only a fully
// extracted and validated directory can become the active client data.
func activateClientData(stageDataDir, workDataDir string) error {
	backupPath := ""
	if entries, err := os.ReadDir(workDataDir); err == nil {
		backupPath = workDataDir + ".backup." + backupTimestamp()
		if err := os.Rename(workDataDir, backupPath); err != nil {
			return fmt.Errorf("failed to preserve previous client data: %w", err)
		}
		if len(entries) == 0 {
			defer os.Remove(backupPath)
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("failed to inspect previous client data: %w", err)
	}
	if err := os.Rename(stageDataDir, workDataDir); err != nil {
		if backupPath != "" {
			if restoreErr := os.Rename(backupPath, workDataDir); restoreErr != nil {
				return fmt.Errorf("activate client data: %w; restore failed: %v; previous files remain at %s", err, restoreErr, backupPath)
			}
		}
		return fmt.Errorf("failed to activate client data: %w", err)
	}
	if backupPath != "" && dirExists(backupPath) {
		if entries, err := os.ReadDir(backupPath); err == nil && len(entries) > 0 {
			fmt.Printf("Previous incomplete client data preserved at %s.\n", backupPath)
		}
	}
	return nil
}

func initializeMySQL(binaries *mysqlBinaries, dataDir string, configFile string) error {
	absDataDir, err := filepath.Abs(dataDir)
	if err != nil {
		return fmt.Errorf("failed to resolve absolute data dir: %w", err)
	}

	if err := os.MkdirAll(absDataDir, 0755); err != nil {
		return fmt.Errorf("failed to create data directory %s: %w", absDataDir, err)
	}

	fmt.Printf("=== [1/4] Initializing MySQL data directory at %s ===\n", absDataDir)

	args := append(defaultsFileArgs(configFile),
		"--initialize-insecure",
		"--datadir="+absDataDir,
		"--console",
	)

	cmd := exec.Command(binaries.mysqld, args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	configureConsoleProcess(cmd)

	if err := cmd.Run(); err != nil {
		return fmt.Errorf("mysqld --initialize-insecure failed: %w", err)
	}

	fmt.Println("MySQL data directory initialized successfully.")
	return nil
}

func startMySQLServer(binaries *mysqlBinaries, dataDir string, port int, configFile string) (*exec.Cmd, error) {
	absDataDir, err := filepath.Abs(dataDir)
	if err != nil {
		return nil, fmt.Errorf("failed to resolve absolute data dir: %w", err)
	}

	args := append(defaultsFileArgs(configFile),
		"--datadir="+absDataDir,
		"--port="+strconv.Itoa(port),
		"--bind-address=127.0.0.1",
		"--mysqlx=0",
		"--console",
	)

	fmt.Printf("=== Starting MySQL server (Port: %d) ===\n", port)
	cmd := exec.Command(binaries.mysqld, args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	configureConsoleProcess(cmd)

	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("failed to start mysqld: %w", err)
	}
	if err := trackMySQLProcess(cmd); err != nil {
		_ = cmd.Process.Kill()
		_ = cmd.Wait()
		return nil, fmt.Errorf("failed to retain mysqld process identity: %w", err)
	}

	return cmd, nil
}

// mysqlRootArgs connects a MySQL client tool as root to the launcher's
// loopback server over TCP, followed by extra options and commands.
func mysqlRootArgs(port int, extra ...string) []string {
	return append([]string{"-u", "root", "-h", "127.0.0.1", "-P", strconv.Itoa(port), "--protocol=tcp"}, extra...)
}

// defaultsFileArgs selects an existing option file. MySQL requires
// --defaults-file to be the first argument.
func defaultsFileArgs(configFile string) []string {
	if configFile == "" || !fileExists(configFile) {
		return nil
	}
	if absolute, err := filepath.Abs(configFile); err == nil {
		configFile = absolute
	}
	return []string{"--defaults-file=" + configFile}
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

func waitForMySQLReady(ctx context.Context, cmd *exec.Cmd, binaries *mysqlBinaries, port int, timeout time.Duration) error {
	fmt.Printf("Waiting for MySQL server to accept connections on port %d...\n", port)
	return waitForReady(ctx, cmd, "MySQL server", timeout, func(ctx context.Context) (bool, error) {
		if !acceptsConnection([]string{"127.0.0.1"}, port, 500*time.Millisecond) {
			return false, nil
		}
		if cmd == nil || cmd.Process == nil {
			return false, errors.New("MySQL readiness requires an owned server process")
		}
		owned, err := ownsMySQLListener(port, cmd.Process)
		if err != nil {
			return false, fmt.Errorf("cannot verify MySQL listener ownership: %w", err)
		}
		if !owned {
			return false, nil
		}
		ping := exec.CommandContext(ctx, binaries.mysqladmin, mysqlRootArgs(port, "--connect-timeout=5", "ping")...)
		if ping.Run() != nil {
			return false, nil
		}
		fmt.Println("MySQL server is online and ready.")
		return true, nil
	})
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

func runEmbeddedSQL(binaries *mysqlBinaries, port int, sqlContent string) error {
	if strings.TrimSpace(sqlContent) == "" {
		return errors.New("embedded SQL content is empty")
	}

	fmt.Println("\n=== [3/4] Applying create_mysql.sql ===")

	cmd := exec.Command(binaries.mysql, mysqlRootArgs(port)...)
	cmd.Stdin = strings.NewReader(sqlContent)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	if err := cmd.Run(); err != nil {
		return fmt.Errorf("failed to execute embedded SQL script: %w", err)
	}

	fmt.Println("AzerothCore databases and user 'acore' ready.")
	return nil
}

// sanitizeRealmlistFlags clears the version-mismatch flag that a worldserver
// interrupted during boot leaves behind. Together with the offline flag set
// by authserver it would hide the realm from the realm list (flag 3). Other
// flags, such as recommended or new, are administrator settings and are kept.
func sanitizeRealmlistFlags(binaries *mysqlBinaries, port int) {
	query := "UPDATE `acore_auth`.`realmlist` SET `flag` = `flag` & ~1 WHERE (`flag` & 1) <> 0;"
	output, err := exec.Command(binaries.mysql, mysqlRootArgs(port, "-e", query)...).CombinedOutput()
	// Before the first authserver start the auth database or table is not
	// created yet (unknown database 1049, missing table 1146).
	if err == nil || bytes.Contains(output, []byte("ERROR 1049")) || bytes.Contains(output, []byte("ERROR 1146")) {
		return
	}
	fmt.Fprintf(os.Stderr, "Warning: could not reset stale realm flags: %v %s\n", err, strings.TrimSpace(string(output)))
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

func shutdownMySQL(binaries *mysqlBinaries, port int, process *os.Process) error {
	owned, err := ownsMySQLListener(port, process)
	if err != nil {
		return fmt.Errorf("cannot verify MySQL listener ownership: %w", err)
	}
	if !owned {
		return errors.New("MySQL port is not owned by the launched process; administrative shutdown skipped")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	return runMySQLShutdown(ctx, binaries, port)
}

func runMySQLShutdown(ctx context.Context, binaries *mysqlBinaries, port int) error {
	shutdownCmd := exec.CommandContext(ctx, binaries.mysqladmin, mysqlRootArgs(port, "--connect-timeout=5", "shutdown")...)
	shutdownCmd.Stdout = os.Stdout
	shutdownCmd.Stderr = os.Stderr
	if err := shutdownCmd.Run(); err != nil {
		return fmt.Errorf("mysqladmin shutdown failed: %w", err)
	}

	return nil
}

func shutdownMySQLAndWait(binaries *mysqlBinaries, port int, cmd *exec.Cmd) (cleanupErr error) {
	if cmd == nil || cmd.Process == nil {
		return nil
	}
	defer func() { cleanupErr = errors.Join(cleanupErr, finishMySQLProcess(cmd)) }()
	if cmd.ProcessState != nil {
		return nil
	}
	// Keep the original process identity alive while cmd.Wait releases its
	// handle, including the race between normal exit and timeout cleanup.
	retained, retainErr := os.FindProcess(cmd.Process.Pid)
	if retained != nil {
		defer retained.Release()
	}
	fmt.Println("Shutting down MySQL server...")

	// A failed launch can leave another MySQL instance listening on this
	// port. Send an administrative command only while our child is alive.
	if alive, _ := isProcessAlive(cmd.Process.Pid); alive {
		if err := shutdownMySQL(binaries, port, cmd.Process); err != nil {
			fmt.Fprintf(os.Stderr, "Warning: %v\n", err)
		}
	}

	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()

	select {
	case <-time.After(10 * time.Second):
		fmt.Println("MySQL did not stop within 10s, terminating process...")
		var killErr error
		if retained != nil {
			killErr = killMySQLProcessTree(retained)
		} else {
			killErr = errors.Join(retainErr, cmd.Process.Kill())
		}
		if killErr != nil && !errors.Is(killErr, os.ErrProcessDone) {
			fmt.Fprintf(os.Stderr, "Warning: MySQL cleanup: %v\n", killErr)
		}
		<-done
	case <-done:
		fmt.Println("MySQL server stopped cleanly.")
	}

	return nil
}

// stopMySQLOrWarn stops a MySQL server the launcher started and reports owned
// processes that could not be cleaned up and may still hold its port or data.
func stopMySQLOrWarn(binaries *mysqlBinaries, port int, cmd *exec.Cmd) {
	if err := shutdownMySQLAndWait(binaries, port, cmd); err != nil && !errors.Is(err, os.ErrProcessDone) {
		fmt.Fprintf(os.Stderr, "Warning: MySQL cleanup: %v\n", err)
	}
}

func findBaseDir() string {
	if exePath, err := os.Executable(); err == nil {
		exeDir := filepath.Dir(exePath)
		if fileExists(filepath.Join(exeDir, "authserver.exe")) {
			return exeDir
		}
	}

	if fileExists("authserver.exe") {
		if abs, err := filepath.Abs("."); err == nil {
			return abs
		}
	}

	if fileExists(filepath.Join("dist", "authserver.exe")) {
		if abs, err := filepath.Abs("dist"); err == nil {
			return abs
		}
	}

	return "."
}

func mysqlBufferPoolSettings(totalRAMBytes uint64) (sizeStr string, instances int, totalRAMGB int) {
	if totalRAMBytes == 0 {
		return "1G", 1, 0
	}

	ramGB := int((totalRAMBytes + (512 * 1024 * 1024)) / (1024 * 1024 * 1024))
	// Leave memory available for worldserver, bots and the OS on the same host.
	poolMB := totalRAMBytes / 4 / (1024 * 1024)
	if poolMB < 512 {
		poolMB = 512
	} else if poolMB > 8192 {
		poolMB = 8192
	}
	poolMB -= poolMB % 256

	instances = int(poolMB / 2048)
	if instances < 1 {
		instances = 1
	}
	if poolMB%1024 == 0 {
		return fmt.Sprintf("%dG", poolMB/1024), instances, ramGB
	}
	return fmt.Sprintf("%dM", poolMB), instances, ramGB
}

func generateDefaultMyCnf(poolSize string, poolInstances int, totalRAMGB int) string {
	ramComment := ""
	if totalRAMGB > 0 {
		ramComment = fmt.Sprintf("# System RAM detected: ~%d GB (Shared-host buffer pool: %s)\n", totalRAMGB, poolSize)
	}

	redoLogCapacity := "1G"
	if totalRAMGB >= 16 {
		redoLogCapacity = "2G"
	} else if totalRAMGB > 0 && totalRAMGB < 8 {
		redoLogCapacity = "512M"
	}

	return fmt.Sprintf(`#
# MySQL 8.0 Configuration for AzerothCore + mod-playerbots
#
# The default MySQL configuration is not adequate for use with Playerbots,
# and will lead to increased disk activity and decreased performance.
#
%s# Reserve about 25%% of RAM for this shared-host buffer pool, between 512M and 8G.
# Worldserver, bots and the operating system need the remaining memory.
#

[mysqld]
# Basic Network and Connection Settings (Loopback only to avoid firewall alerts)
bind-address = 127.0.0.1
mysqlx = 0
port = 3306
max_connections = 500
max_allowed_packet = 64M

# Character Set
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci

#
# * Fine Tuning for Playerbots
#

# INNODB Buffer Pool & I/O
innodb_buffer_pool_size = %s
innodb_buffer_pool_instances = %d
innodb_redo_log_capacity = %s
innodb_log_buffer_size = 64M
innodb_io_capacity = 1000
innodb_io_capacity_max = 3000
innodb_use_fdatasync = ON
innodb_read_io_threads = 4
innodb_write_io_threads = 4

# Performance & SSD Lifespan Optimization:
# Flushes redo log to OS cache every commit and to disk once per second.
innodb_flush_log_at_trx_commit = 2

# Table Cache
table_open_cache = 4000
table_definition_cache = 2000

# Binary Logging:
# Binary logging is disabled for this local standalone database.
skip-log-bin

# Max age of binary logs if binary logging is re-enabled - 5 days to prevent binary log pileups
binlog_expire_logs_seconds = 432000

# Prevent SQL Deadlocks as much as possible
transaction_isolation = "READ-COMMITTED"

[client]
default-character-set = utf8mb4

[mysql]
default-character-set = utf8mb4
`, ramComment, poolSize, poolInstances, redoLogCapacity)
}

// isDirWritable checks whether a directory exists and files can be created in it.
func isDirWritable(dir string) bool {
	if !dirExists(dir) {
		return false
	}
	testFile := filepath.Join(dir, fmt.Sprintf(".write_test_%d", time.Now().UnixNano()))
	if err := os.WriteFile(testFile, []byte("ok"), 0644); err != nil {
		return false
	}
	_ = os.Remove(testFile)
	return true
}

func ensureWorkDirStructure(dir string) {
	_ = os.MkdirAll(dir, 0755)
	_ = os.MkdirAll(filepath.Join(dir, "configs"), 0755)
	_ = os.MkdirAll(filepath.Join(dir, "logs"), 0755)
	_ = os.MkdirAll(filepath.Join(dir, "data"), 0755)
	_ = os.MkdirAll(filepath.Join(dir, "mysql"), 0755)
	_ = os.MkdirAll(filepath.Join(dir, "mysql", "data"), 0755)
}

func getWorkDir(baseDir string) string {
	if envDir := os.Getenv("PLAYERBOTS_WORKDIR"); envDir != "" {
		ensureWorkDirStructure(envDir)
		return envDir
	}

	if !isPackagedApp() && isDirWritable(baseDir) {
		ensureWorkDirStructure(baseDir)
		return baseDir
	}

	localAppData := os.Getenv("LOCALAPPDATA")
	if localAppData == "" {
		if userProfile := os.Getenv("USERPROFILE"); userProfile != "" {
			localAppData = filepath.Join(userProfile, "AppData", "Local")
		} else if home := os.Getenv("HOME"); home != "" {
			localAppData = filepath.Join(home, ".local", "share")
		} else {
			localAppData = "."
		}
	}

	appDir := filepath.Join(localAppData, "Playerbots")
	ensureWorkDirStructure(appDir)
	return appDir
}

func findMySQLConfigFile(customPath, mysqlDir, baseDir, workDir string) string {
	if customPath != "" && fileExists(customPath) {
		return customPath
	}

	var candidates []string

	if workDir != "" {
		candidates = append(candidates,
			filepath.Join(workDir, "mysql", "my.cnf"),
			filepath.Join(workDir, "mysql", "my.ini"),
			filepath.Join(workDir, "configs", "my.cnf"),
			filepath.Join(workDir, "configs", "my.ini"),
			filepath.Join(workDir, "my.cnf"),
			filepath.Join(workDir, "my.ini"),
		)
	}

	if mysqlDir != "" {
		candidates = append(candidates,
			filepath.Join(mysqlDir, "my.cnf"),
			filepath.Join(mysqlDir, "my.ini"),
		)
	}

	candidates = append(candidates,
		filepath.Join(baseDir, "mysql", "my.cnf"),
		filepath.Join(baseDir, "mysql", "my.ini"),
		filepath.Join(baseDir, "configs", "my.cnf"),
		filepath.Join(baseDir, "configs", "my.ini"),
		filepath.Join(baseDir, "my.cnf"),
		filepath.Join(baseDir, "my.ini"),
	)

	for _, cand := range candidates {
		if cand != "" && fileExists(cand) {
			return cand
		}
	}

	return ""
}

func ensureMySQLConfigFile(baseDir, workDir, mysqlDir string) (string, error) {
	if existing := findMySQLConfigFile("", mysqlDir, baseDir, workDir); existing != "" {
		return existing, nil
	}

	targetDir := filepath.Join(workDir, "mysql")
	targetPath := filepath.Join(targetDir, "my.cnf")

	poolSize, instances, ramGB := mysqlBufferPoolSettings(getTotalRAMBytes())
	content := generateDefaultMyCnf(poolSize, instances, ramGB)

	if err := os.MkdirAll(filepath.Dir(targetPath), 0755); err != nil {
		return "", fmt.Errorf("failed to create directory for %s: %w", targetPath, err)
	}

	// An interrupted first start must not leave a truncated config that is
	// never regenerated.
	if err := writeConfigAtomically(targetPath, []byte(content), 0644); err != nil {
		return "", fmt.Errorf("failed to write %s: %w", targetPath, err)
	}

	relTarget, err := filepath.Rel(workDir, targetPath)
	if err != nil {
		relTarget = targetPath
	}
	fmt.Printf("Created default MySQL config: %s (Buffer pool: %s, Instances: %d)\n", filepath.ToSlash(relTarget), poolSize, instances)

	return targetPath, nil
}

// mysqlInstallDir returns the MySQL root searched for an existing option file:
// --mysql-dir, else the parent of the client's bin directory. Config creation
// and server start must search the same directory.
func mysqlInstallDir(mysqlDir, mysqlExePath, workDir string) string {
	if mysqlDir != "" {
		return mysqlDir
	}
	if mysqlExePath != "" {
		return filepath.Dir(filepath.Dir(mysqlExePath))
	}
	return filepath.Join(workDir, "mysql")
}

func ensureConfigFiles(baseDir, workDir string, mysqlExePath string, opts startupOptions) error {
	phase, err := loadRealmPhase(workDir)
	if err != nil {
		return err
	}
	// 1. Ensure MySQL configuration file (my.cnf) exists with fine-tuning settings
	if opts.mysqlCnf != "" {
		if !fileExists(opts.mysqlCnf) {
			return fmt.Errorf("specified MySQL config file does not exist: %s", opts.mysqlCnf)
		}
	} else if _, err := ensureMySQLConfigFile(baseDir, workDir, mysqlInstallDir(opts.mysqlDir, mysqlExePath, workDir)); err != nil {
		return fmt.Errorf("failed to ensure MySQL config file: %w", err)
	}

	// 2. Ensure server configs and logs directory in workDir
	_ = os.MkdirAll(filepath.Join(workDir, "logs"), 0755)
	configSrcDir := filepath.Join(baseDir, "configs")
	if !dirExists(configSrcDir) {
		return nil
	}
	configDstDir := filepath.Join(workDir, "configs")
	_ = os.MkdirAll(configDstDir, 0755)
	marker := filepath.Join(configDstDir, realmPhaseFile)
	if phase.name == "individual" && !fileExists(marker) {
		if err := writeConfigAtomically(marker, []byte(phase.name+"\n"), 0644); err != nil {
			return err
		}
	}

	mysqlExeForConf := "mysql/bin/mysql.exe"
	if mysqlExePath != "" {
		if rel, err := filepath.Rel(workDir, mysqlExePath); err == nil && !strings.HasPrefix(rel, "..") {
			mysqlExeForConf = filepath.ToSlash(rel)
		} else {
			mysqlExeForConf = filepath.ToSlash(mysqlExePath)
		}
	}

	srcDirForConf := portableSourceDirectory(baseDir, workDir)

	dataDirForConf := "data"
	baseDataDir := filepath.Join(baseDir, "data")
	workDataDir := filepath.Join(workDir, "data")
	if dirExists(baseDataDir) && baseDataDir != workDataDir {
		if entries, err := os.ReadDir(baseDataDir); err == nil && len(entries) > 0 {
			dataDirForConf = filepath.ToSlash(baseDataDir)
		}
	}

	return filepath.Walk(configSrcDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() {
			return nil
		}

		if strings.HasSuffix(info.Name(), ".conf.dist") || strings.HasSuffix(info.Name(), ".conf") {
			relPath, err := filepath.Rel(configSrcDir, path)
			if err != nil {
				relPath = info.Name()
			}
			relTargetName := strings.TrimSuffix(relPath, ".dist")
			targetConfPath := filepath.Join(configDstDir, relTargetName)

			if !fileExists(targetConfPath) {
				data, err := os.ReadFile(path)
				if err != nil {
					return fmt.Errorf("failed to read %s: %w", path, err)
				}

				content := string(data)
				content = strings.Replace(content, `DataDir = "."`, fmt.Sprintf(`DataDir = "%s"`, dataDirForConf), 1)
				content = strings.Replace(content, `LogsDir = ""`, `LogsDir = "logs"`, 1)
				content = strings.Replace(content, `SourceDirectory = ""`, fmt.Sprintf(`SourceDirectory = "%s"`, srcDirForConf), 1)
				content = strings.Replace(content, `MySQLExecutable = ""`, fmt.Sprintf(`MySQLExecutable = "%s"`, mysqlExeForConf), 1)
				content = strings.Replace(content, `BindIP = "0.0.0.0"`, `BindIP = "127.0.0.1"`, 1)

				content, err = applyConfigProfileForPhase(info.Name(), content, phase)
				if err != nil {
					return err
				}
				content, err = applyRuntimePorts(info.Name(), content, opts)
				if err != nil {
					return err
				}

				if err := os.MkdirAll(filepath.Dir(targetConfPath), 0755); err != nil {
					return fmt.Errorf("failed to create directory for %s: %w", targetConfPath, err)
				}

				if err := writeConfigAtomically(targetConfPath, []byte(content), 0644); err != nil {
					return fmt.Errorf("failed to write %s: %w", targetConfPath, err)
				}

				relTarget, err := filepath.Rel(workDir, targetConfPath)
				if err != nil {
					relTarget = targetConfPath
				}
				fmt.Printf("Created default config: %s (BindIP: 127.0.0.1)\n", filepath.ToSlash(relTarget))
			}
		}
		return nil
	})
}

func main() {
	if handled, err := runPortableUpdateHelper(os.Args[1:]); handled {
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error completing update: %v\n", err)
			os.Exit(1)
		}
		return
	}
	if runtime.GOOS != "windows" {
		fmt.Fprintf(os.Stderr, "Error: mod-playerbots startup tool is only supported on Windows (detected OS: %s)\n", runtime.GOOS)
		os.Exit(1)
	}

	opts, err := parseArgs(os.Args[1:])
	if err != nil {
		if errors.Is(err, flag.ErrHelp) {
			os.Exit(0)
		}
		fmt.Fprintf(os.Stderr, "Error parsing arguments: %v\n", err)
		os.Exit(1)
	}

	baseDir := findBaseDir()
	workDir := getWorkDir(baseDir)
	if workDir != baseDir {
		fmt.Printf("Running in packaged mode. Working directory: %s\n", workDir)
	} else {
		fmt.Printf("Working directory: %s\n", workDir)
	}
	if baseDir == workDir {
		if err := recoverPortableUpdate(baseDir); err != nil {
			fmt.Fprintf(os.Stderr, "Error recovering interrupted update: %v\n", err)
			os.Exit(1)
		}
	}
	if opts.setExpansion != "" || opts.showExpansion {
		phase, err := loadRealmPhase(workDir)
		if opts.setExpansion != "" {
			phase, _ = parseRealmPhase(opts.setExpansion)
			var backups []string
			backups, err = setRealmPhase(workDir, phase)
			for _, backup := range backups {
				fmt.Printf("Previous settings saved to %s\n", backup)
			}
		}
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error selecting expansion: %v\n", err)
			os.Exit(1)
		}
		fmt.Printf("Realm expansion: %s; level cap: %d; progression limit: %d (0 = unlimited).\n", phase.name, phase.level, phase.limit)
		if opts.setExpansion != "" {
			fmt.Println("Start startup.exe normally to use this phase. Players and bots still earn their progression; existing characters and databases are preserved.")
		}
		return
	}

	// Set up early root context and signal handling so Ctrl+C at any time shuts down child processes
	rootCtx, rootCancel := context.WithCancel(context.Background())
	defer rootCancel()

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
	defer signal.Stop(sigChan)
	if err := enableConsoleInterrupt(); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: could not enable Ctrl+C handling: %v\n", err)
	}

	go func() {
		select {
		case sig := <-sigChan:
			fmt.Printf("\nReceived signal (%v)...\n", sig)
			rootCancel()
		case <-rootCtx.Done():
		}
	}()

	if baseDir == workDir && !opts.downloadDataOnly {
		if !opts.noUpdate {
			if updating, err := checkPortableUpdate(rootCtx, baseDir, os.Args[1:]); err != nil {
				fmt.Fprintf(os.Stderr, "Update check unavailable; starting installed release: %v\n", err)
			} else if updating {
				return
			}
		}
	}
	if rootCtx.Err() != nil {
		fmt.Println("Startup canceled.")
		return
	}

	// Handle -download-data-only mode, which needs no MySQL installation
	if opts.downloadDataOnly {
		if err := ensureClientData(rootCtx, workDir, baseDir, opts.dataURL, false); err != nil {
			fmt.Fprintf(os.Stderr, "Error downloading client data: %v\n", err)
			os.Exit(1)
		}
		fmt.Println("Client data download and extraction complete.")
		os.Exit(0)
	}

	binaries, err := findMySQLBinaries(opts.mysqlDir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}

	authserverExe := findExecutable(baseDir, "authserver")
	worldserverExe := findExecutable(baseDir, "worldserver")

	if !opts.initOnly {
		if authserverExe == "" {
			fmt.Fprintf(os.Stderr, "Error: authserver executable not found in %s or PATH\n", baseDir)
			os.Exit(1)
		}
		if worldserverExe == "" {
			fmt.Fprintf(os.Stderr, "Error: worldserver executable not found in %s or PATH\n", baseDir)
			os.Exit(1)
		}
	}

	// Default dataDir to <workDir>/mysql/data
	if opts.dataDir == "" {
		opts.dataDir = filepath.Join(workDir, "mysql", "data")
	}

	// Ensure config files (e.g. worldserver.conf, authserver.conf, modules/playerbots.conf, mysql/my.cnf) exist in workDir
	if err := ensureConfigFiles(baseDir, workDir, binaries.mysql, opts); err != nil {
		fmt.Fprintf(os.Stderr, "Error: failed to ensure config files: %v\n", err)
		os.Exit(1)
	}
	if err := ensureRealmStopped(workDir); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
	pathBackups, err := relocatePortableSourcePaths(baseDir, workDir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error updating portable SQL paths: %v\n", err)
		os.Exit(1)
	}
	for _, backup := range pathBackups {
		fmt.Printf("SQL path updated; previous settings saved to %s\n", backup)
	}
	backups, err := migrateConfigProfiles(workDir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error updating configuration defaults: %v\n", err)
		os.Exit(1)
	}
	for _, backup := range backups {
		fmt.Printf("Configuration updated; previous settings saved to %s\n", backup)
	}
	authHosts, err := applyConfiguredPorts(workDir, &opts)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error reading server ports: %v\n", err)
		os.Exit(1)
	}

	// Ensure client data files (maps, vmaps, mmaps, dbc) are present
	if !opts.initOnly {
		if err := ensureClientData(rootCtx, workDir, baseDir, opts.dataURL, opts.skipDataCheck); err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
	}

	cnfFile := findMySQLConfigFile(opts.mysqlCnf, mysqlInstallDir(opts.mysqlDir, binaries.mysql, workDir), baseDir, workDir)
	if rootCtx.Err() != nil {
		fmt.Println("Startup canceled.")
		return
	}

	// 1. Initialize data directory if needed
	if !isDataDirInitialized(opts.dataDir) {
		if err := initializeMySQL(binaries, opts.dataDir, cnfFile); err != nil {
			fmt.Fprintf(os.Stderr, "Error initializing MySQL: %v\n", err)
			os.Exit(1)
		}
	} else {
		fmt.Printf("MySQL data directory already initialized at %s\n", opts.dataDir)
	}
	if rootCtx.Err() != nil {
		fmt.Println("Startup canceled.")
		return
	}

	// 2. Start MySQL Server
	fmt.Println("\n=== [2/4] Starting MySQL server ===")
	mysqlCmd, err := startMySQLServer(binaries, opts.dataDir, opts.port, cnfFile)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error starting MySQL: %v\n", err)
		os.Exit(1)
	}

	// 3. Wait for MySQL to become ready
	timeoutDuration := time.Duration(opts.timeout) * time.Second
	if err := waitForMySQLReady(rootCtx, mysqlCmd, binaries, opts.port, timeoutDuration); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		stopMySQLOrWarn(binaries, opts.port, mysqlCmd)
		os.Exit(1)
	}

	// 4. Apply SQL script
	if !opts.skipSQL {
		if err := runEmbeddedSQL(binaries, opts.port, createMySQLSQL); err != nil {
			fmt.Fprintf(os.Stderr, "Error applying SQL: %v\n", err)
			stopMySQLOrWarn(binaries, opts.port, mysqlCmd)
			os.Exit(1)
		}
	}

	// 5. If init-only, shutdown and exit
	if opts.initOnly {
		fmt.Println("\nInit-only mode complete. Shutting down MySQL...")
		stopMySQLOrWarn(binaries, opts.port, mysqlCmd)
		os.Exit(0)
	}

	// 6. Start authserver and worldserver (staggered)
	fmt.Println("\n=== [4/4] Starting authserver and worldserver ===")

	// Reset the realm status left by a worldserver interrupted during boot
	sanitizeRealmlistFlags(binaries, opts.port)

	authCmd, err := startServerProcess("authserver", authserverExe, workDir, nil)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error starting authserver: %v\n", err)
		stopMySQLOrWarn(binaries, opts.port, mysqlCmd)
		os.Exit(1)
	}

	authTimeout := time.Duration(opts.timeout*2) * time.Second
	if authTimeout < 60*time.Second {
		authTimeout = 60 * time.Second
	}

	if err := waitForAuthServerReady(rootCtx, authCmd, authHosts, opts.authPort, authTimeout); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		stopProcess("authserver", authCmd)
		stopMySQLOrWarn(binaries, opts.port, mysqlCmd)
		os.Exit(1)
	}

	worldCmd, err := startServerProcess("worldserver", worldserverExe, workDir, os.Stdin)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error starting worldserver: %v\n", err)
		stopProcess("authserver", authCmd)
		stopMySQLOrWarn(binaries, opts.port, mysqlCmd)
		os.Exit(1)
	}

	// 7. Setup supervisors with auto-restart capability
	supervisorCtx, supervisorCancel := context.WithCancel(context.Background())
	defer supervisorCancel()

	var wg sync.WaitGroup

	mysqlSupervisor := newProcessSupervisor("mysqld", func() (*exec.Cmd, error) {
		cmd, err := startMySQLServer(binaries, opts.dataDir, opts.port, cnfFile)
		if err != nil {
			return nil, err
		}
		// Crash recovery after an unexpected exit can be slow; honor --timeout.
		if err := waitForMySQLReady(supervisorCtx, cmd, binaries, opts.port, timeoutDuration); err != nil {
			stopMySQLOrWarn(binaries, opts.port, cmd)
			return nil, err
		}
		return cmd, nil
	}, 2*time.Second)
	mysqlSupervisor.killProcess = killMySQLProcessTree
	mysqlSupervisor.finishProcess = finishMySQLProcess

	authSupervisor := newProcessSupervisor("authserver", func() (*exec.Cmd, error) {
		sanitizeRealmlistFlags(binaries, opts.port)
		return startServerProcess("authserver", authserverExe, workDir, nil)
	}, 2*time.Second)

	worldSupervisor := newProcessSupervisor("worldserver", func() (*exec.Cmd, error) {
		return startServerProcess("worldserver", worldserverExe, workDir, os.Stdin)
	}, 2*time.Second)

	wg.Add(3)
	go mysqlSupervisor.Run(supervisorCtx, mysqlCmd, &wg)
	go authSupervisor.Run(supervisorCtx, authCmd, &wg)
	go worldSupervisor.Run(supervisorCtx, worldCmd, &wg)

	fmt.Println("\n========================================================")
	fmt.Println(" All servers running. You can type commands into console.")
	fmt.Println(" Worldserver and authserver will auto-restart if exited.")
	fmt.Println(" Press Ctrl+C to shut down all servers.")
	fmt.Println("========================================================")

	<-rootCtx.Done()
	shutdownRealmProcesses(authSupervisor, worldSupervisor, mysqlSupervisor, supervisorCancel, func() error {
		process := mysqlSupervisor.RetainCurrentProcess()
		if process == nil {
			return nil
		}
		defer process.Release()
		return shutdownMySQL(binaries, opts.port, process)
	})
}
