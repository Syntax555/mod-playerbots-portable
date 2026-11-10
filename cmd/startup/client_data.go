package main

import (
	"archive/zip"
	"context"
	"crypto/sha256"
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

// clientDataRelease is the wowgaming/client-data release whose map, vmap and
// mmap formats the pinned core reads; its installer names the same release.
const clientDataRelease = "v20.0"

const defaultClientDataURL = "https://github.com/wowgaming/client-data/releases/download/" + clientDataRelease + "/Data.zip"

// Every launcher before the release marker installed v20.0. Keep this value
// when clientDataRelease changes, so those installations are replaced.
const unmarkedClientDataRelease = "v20.0"

// clientDataReleaseFile is the marker AzerothCore's installer keeps in data/.
const clientDataReleaseFile = "data-version"

// installedClientDataRelease returns the release recorded in dataDir, or ""
// when the marker cannot be read.
func installedClientDataRelease(dataDir string) string {
	content, err := os.ReadFile(filepath.Join(dataDir, clientDataReleaseFile))
	if errors.Is(err, os.ErrNotExist) {
		return unmarkedClientDataRelease
	}
	for line := range strings.Lines(string(content)) {
		if release, ok := strings.CutPrefix(strings.TrimSpace(line), "INSTALLED_VERSION="); ok {
			return release
		}
	}
	return ""
}

func isClientDataPresent(dataDir string) bool {
	requiredDirs := []string{"dbc", "maps", "vmaps", "mmaps"}
	for _, req := range requiredDirs {
		if !directoryHasEntries(filepath.Join(dataDir, req)) {
			return false
		}
	}
	return true
}

// downloadFileWithProgress keeps an interrupted download in destPath.download
// and continues it on the next call. The caller verifies the completed file.
func downloadFileWithProgress(ctx context.Context, url string, destPath string) error {
	tmpPath := destPath + ".download"
	var offset int64
	if info, err := os.Stat(tmpPath); err == nil && info.Mode().IsRegular() {
		offset = info.Size()
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return fmt.Errorf("failed to create download request: %w", err)
	}
	req.Header.Set("User-Agent", "AzerothCore-Playerbots-Launcher/1.0")
	if offset > 0 {
		req.Header.Set("Range", fmt.Sprintf("bytes=%d-", offset))
	}

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

	// A download stopped after its last byte has nothing left to request.
	if offset > 0 && resp.StatusCode == http.StatusRequestedRangeNotSatisfiable {
		resp.Body.Close()
		if err := os.Remove(tmpPath); err != nil {
			return fmt.Errorf("failed to restart download %s: %w", tmpPath, err)
		}
		return downloadFileWithProgress(ctx, url, destPath)
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("server returned HTTP %s", resp.Status)
	}
	flags := os.O_CREATE | os.O_WRONLY | os.O_TRUNC
	total := resp.ContentLength
	if resp.StatusCode == http.StatusPartialContent {
		if !strings.HasPrefix(resp.Header.Get("Content-Range"), fmt.Sprintf("bytes %d-", offset)) {
			return fmt.Errorf("server resumed the download at an unexpected position: %q", resp.Header.Get("Content-Range"))
		}
		flags = os.O_WRONLY | os.O_APPEND
		if total >= 0 {
			total += offset
		}
		fmt.Printf("Resuming the download after %.1f MB.\n", float64(offset)/(1024*1024))
	} else {
		offset = 0
	}

	if err := os.MkdirAll(filepath.Dir(tmpPath), 0755); err != nil {
		return fmt.Errorf("failed to create download directory: %w", err)
	}
	out, err := os.OpenFile(tmpPath, flags, 0644)
	if err != nil {
		return fmt.Errorf("failed to create temporary file %s: %w", tmpPath, err)
	}

	progress := newDownloadProgress(total)
	progress.done, progress.resumed = offset, offset
	// The request context also cancels reading the response body.
	_, err = io.Copy(io.MultiWriter(out, progress), resp.Body)
	progress.finish()
	closeErr := out.Close()
	if err != nil {
		return fmt.Errorf("failed to download to %s; the next start continues it: %w", tmpPath, err)
	}
	if closeErr != nil {
		return fmt.Errorf("failed to close downloaded file: %w", closeErr)
	}

	if err := os.Rename(tmpPath, destPath); err != nil {
		return fmt.Errorf("failed to finalize downloaded file: %w", err)
	}
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
	resumed  int64 // bytes from an earlier attempt, excluded from the speed
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
		speed = float64(p.done-p.resumed) / mb / elapsed
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

	// A populated baseDir/data is the one new configurations use; the launcher
	// replaces only workDir/data, so an outdated baseDir copy stops the start.
	// The worldserver rejects maps, vmaps and mmaps of another release.
	outdated := ""
	for _, dataDir := range []string{baseDataDir, workDataDir} {
		if !isClientDataPresent(dataDir) {
			continue
		}
		release := installedClientDataRelease(dataDir)
		if release == clientDataRelease {
			fmt.Printf("Client data %s verified at %s.\n", release, dataDir)
			return nil
		}
		outdated = fmt.Sprintf("Client data at %s is release %q; this server needs %s.", dataDir, release, clientDataRelease)
		if dataDir != workDataDir {
			return fmt.Errorf("%s Replace it with that release, or remove it to download the release into %s", outdated, workDataDir)
		}
	}

	fmt.Println("\n=== Client Data Verification ===")
	if outdated != "" {
		fmt.Println(outdated)
	} else {
		fmt.Printf("Required client data (dbc, maps, vmaps, mmaps) not found in %s.\n", workDataDir)
	}
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
	// The archive outlives the stage until its data is active: a later start
	// continues an interrupted download or extracts again without one. Its name
	// follows the URL, so a different archive is never appended to it.
	urlDigest := sha256.Sum256([]byte(dataURL))
	zipPath := filepath.Join(workDir, fmt.Sprintf(".client-data-%x.zip", urlDigest[:6]))
	if fileExists(zipPath) {
		fmt.Printf("Extracting client data downloaded earlier from %s...\n", dataURL)
	} else {
		fmt.Printf("Downloading client data from %s...\n", dataURL)
		if err := downloadFileWithProgress(ctx, dataURL, zipPath); err != nil {
			return fmt.Errorf("failed to download client data: %w", err)
		}
	}
	if err := extractZip(ctx, zipPath, stageDataDir); err != nil {
		if ctx.Err() == nil {
			_ = os.Remove(zipPath)
		}
		return fmt.Errorf("failed to extract client data: %w", err)
	}

	if !isClientDataPresent(stageDataDir) {
		_ = os.Remove(zipPath)
		return errors.New("client data archive is missing populated required folders (dbc, maps, vmaps, mmaps)")
	}
	if release := installedClientDataRelease(stageDataDir); fileExists(filepath.Join(stageDataDir, clientDataReleaseFile)) && release != clientDataRelease {
		_ = os.Remove(zipPath)
		return fmt.Errorf("client data archive declares release %q; this server needs %s", release, clientDataRelease)
	}
	// --data-url names a mirror of the required release. The marker becomes
	// active with the data in one rename.
	marker := []byte("INSTALLED_VERSION=" + clientDataRelease + "\n")
	if err := os.WriteFile(filepath.Join(stageDataDir, clientDataReleaseFile), marker, 0644); err != nil {
		return fmt.Errorf("failed to record the client data release: %w", err)
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	if err := activateClientData(stageDataDir, workDataDir); err != nil {
		return err
	}
	if err := os.Remove(zipPath); err != nil {
		fmt.Fprintf(os.Stderr, "Warning: could not remove the downloaded archive %s: %v\n", zipPath, err)
	}
	return nil
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
			fmt.Printf("Previous client data preserved at %s.\n", backupPath)
		}
	}
	return nil
}
