package main

import (
	"archive/zip"
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const defaultClientDataURL = "https://github.com/wowgaming/client-data/releases/download/v20.0/Data.zip"

func isClientDataPresent(dataDir string) bool {
	requiredDirs := []string{"dbc", "maps", "vmaps", "mmaps"}
	for _, req := range requiredDirs {
		directory, err := os.Open(filepath.Join(dataDir, req))
		if err != nil {
			return false
		}
		entries, err := directory.Readdirnames(1)
		directory.Close()
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
	if isClientDataPresent(baseDataDir) {
		fmt.Printf("Client data verified at %s.\n", baseDataDir)
		return nil
	}
	if isClientDataPresent(workDataDir) {
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
