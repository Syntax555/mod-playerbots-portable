package main

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

const portableUpdateDirectory = ".portable-update"
const portableUpdateCacheDirectory = portableUpdateDirectory + "/cache"
const portableUpdateHelperFlag = "--portable-update-helper"

// Bounds how long one launch spends downloading before it starts the installed
// release. Verified files are kept, so the next launch continues from there.
const portableUpdateDownloadTime = 15 * time.Minute

func safeUpdateTarget(root, relative string) (string, error) {
	if err := validateUpdatePath(relative); err != nil {
		return "", err
	}
	return safeUpdateChild(root, relative)
}

// Every component is inspected with Lstat. User junctions/symlinks must not
// redirect package writes outside the portable installation.
func safeUpdateChild(root, relative string) (string, error) {
	if filepath.IsAbs(relative) || filepath.Clean(filepath.FromSlash(relative)) != filepath.FromSlash(relative) || relative == ".." || strings.HasPrefix(relative, "../") || strings.ContainsAny(relative, "\\:\x00") {
		return "", errors.New("invalid updater internal path")
	}
	current := root
	if info, err := os.Lstat(current); err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return "", errors.New("installation root is not a real directory")
	}
	for _, component := range strings.Split(relative, "/") {
		current = filepath.Join(current, component)
		info, err := os.Lstat(current)
		if errors.Is(err, os.ErrNotExist) {
			continue
		}
		if err != nil {
			return "", err
		}
		if info.Mode()&os.ModeSymlink != 0 || info.Mode()&os.ModeType != 0 && !info.IsDir() {
			return "", fmt.Errorf("update path contains a link or special file: %s", current)
		}
	}
	return current, nil
}

func hashUpdateFile(filename string, expectedSize int64) (string, error) {
	info, err := os.Lstat(filename)
	if err != nil {
		return "", err
	}
	if !info.Mode().IsRegular() {
		return "", fmt.Errorf("update destination is not a regular file: %s", filename)
	}
	if info.Size() != expectedSize {
		return "", nil
	}
	file, err := os.Open(filename)
	if err != nil {
		return "", err
	}
	defer file.Close()
	hash := sha256.New()
	written, err := io.Copy(hash, io.LimitReader(file, expectedSize+1))
	if err != nil {
		return "", err
	}
	if written != expectedSize {
		return "", nil
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}

func readPortableIdentity(root string) (portableReleaseIdentity, error) {
	var identity portableReleaseIdentity
	filename, err := safeUpdateTarget(root, "portable-release.json")
	if err != nil {
		return identity, err
	}
	file, err := os.Open(filename)
	if err != nil {
		return identity, err
	}
	defer file.Close()
	content, err := io.ReadAll(io.LimitReader(file, 8193))
	if err != nil || len(content) > 8192 {
		return identity, errors.New("invalid installed release identity")
	}
	if err := json.Unmarshal(content, &identity); err != nil || identity.Schema != 1 || !updateRevisionPattern.MatchString(identity.Revision) || identity.Package != portableUpdatePackage || identity.Version != "latest" {
		return identity, errors.New("invalid installed release identity")
	}
	return identity, nil
}

func checkPortableUpdate(ctx context.Context, root string, args []string) (bool, error) {
	return checkPortableUpdateFrom(ctx, root, args, portableUpdateHTTPClient(), portableUpdateManifestURL)
}

// checkPortableUpdateFrom checks the release whose manifest is at manifestURL;
// its package must be published next to the manifest.
func checkPortableUpdateFrom(ctx context.Context, root string, args []string, client *http.Client, manifestURL string) (bool, error) {
	identity, err := readPortableIdentity(root)
	if err != nil {
		return false, fmt.Errorf("read installed version: %w", err)
	}
	progress := startPortableUpdateProgress(ctx)
	defer progress.close()
	progress.begin("Checking release metadata", "", 0, 0)
	checkCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	manifest, err := fetchUpdateManifest(checkCtx, client, manifestURL, updateManifestResponseTimeout)
	cancel()
	if err != nil {
		return false, err
	}
	progress.finish()
	if manifest.Revision == identity.Revision {
		progress.begin("Recording verified inventory", "", 0, 0)
		if err := rememberPortableUpdateBaseline(root, manifest); err != nil {
			return false, err
		}
		progress.finish()
		progress.close()
		fmt.Println("Installed release is up to date.")
		return false, nil
	}
	if err := ensurePortableUpdateStopped(root, os.Getpid()); err != nil {
		return false, err
	}
	updateCtx, cancelUpdate := context.WithTimeout(ctx, portableUpdateDownloadTime)
	defer cancelUpdate()
	assetURL := strings.TrimSuffix(manifestURL, "UPDATE_MANIFEST.json") + manifest.Package
	plan, err := stagePortableUpdate(updateCtx, root, manifest, args, client, assetURL, progress)
	if err != nil {
		if ctx.Err() == nil && errors.Is(updateCtx.Err(), context.DeadlineExceeded) {
			return false, fmt.Errorf("update download did not finish within %v; the next start continues with the files verified so far: %w", portableUpdateDownloadTime, err)
		}
		return false, err
	}
	progress.begin("Starting verified updater", "", 0, 0)
	if err := handoffPortableUpdate(updateCtx, root, plan); err != nil {
		return false, err
	}
	progress.finish()
	progress.close()
	fmt.Printf("Installing verified update (%d changed files). The launcher will restart automatically.\n", len(plan.Operations))
	return true, nil
}

// Cancellation before the helper handoff keeps the installed release.
// Local identity checks and journal writes can finish after the last HTTP read,
// so a successful staging result does not imply that its context is still live.
func handoffPortableUpdate(ctx context.Context, root string, plan *portableUpdatePlan) error {
	if err := ctx.Err(); err != nil {
		return errors.Join(err, discardStagedUpdate(root))
	}
	if err := launchPortableUpdateHelper(root, plan); err != nil {
		return errors.Join(err, discardStagedUpdate(root))
	}
	return nil
}

// A fresh installation already has the current revision, but it still needs
// the verified inventory so a later update can recognize obsolete stock files.
// Keep an older inventory after a manual overlay; its known paths remain useful
// until the next real update removes only their unchanged original bytes.
func rememberPortableUpdateBaseline(root string, manifest portableUpdateManifest) error {
	if err := validateUpdateManifest(manifest); err != nil {
		return err
	}
	if _, err := readInstalledUpdateManifest(root); err == nil {
		return nil
	} else if !errors.Is(err, os.ErrNotExist) {
		return err
	}
	if err := ensurePortableUpdateStopped(root, os.Getpid()); err != nil {
		return err
	}
	stateDir, err := acquirePortableUpdateOwner(root)
	if err != nil {
		return err
	}
	defer os.Remove(filepath.Join(stateDir, "owner.json"))
	return writeUpdateJSON(filepath.Join(stateDir, "installed.json"), manifest)
}

func acquirePortableUpdateOwner(root string) (string, error) {
	stateDir, err := safeUpdateChild(root, portableUpdateDirectory)
	if err != nil {
		return "", err
	}
	if err := os.MkdirAll(stateDir, 0700); err != nil {
		return "", err
	}
	if _, err := os.Lstat(filepath.Join(stateDir, "journal.json")); err == nil {
		return "", errors.New("another update is pending; restart the launcher before updating")
	} else if !errors.Is(err, os.ErrNotExist) {
		return "", err
	}
	ownerPath, err := safeUpdateChild(root, portableUpdateDirectory+"/owner.json")
	if err != nil {
		return "", err
	}
	owner, err := os.OpenFile(ownerPath, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return "", errors.New("another launcher is preparing an update")
	}
	ownerContent, _ := json.Marshal(portableUpdateOwner{PID: os.Getpid()})
	_, writeErr := owner.Write(ownerContent)
	syncErr, closeErr := owner.Sync(), owner.Close()
	if err := errors.Join(writeErr, syncErr, closeErr); err != nil {
		_ = os.Remove(ownerPath)
		return "", err
	}
	return stateDir, nil
}

func stagePortableUpdate(ctx context.Context, root string, manifest portableUpdateManifest, args []string, client *http.Client, assetURL string, progress *portableUpdateProgress) (plan *portableUpdatePlan, err error) {
	if err := validateUpdateManifest(manifest); err != nil {
		return nil, err
	}
	stateDir, err := acquirePortableUpdateOwner(root)
	if err != nil {
		return nil, err
	}
	defer func() {
		if err != nil {
			_ = discardStagedUpdate(root)
		}
	}()
	for _, folder := range []string{"stage", "backup"} {
		p, err := safeUpdateChild(root, portableUpdateDirectory+"/"+folder)
		if err != nil {
			return nil, err
		}
		if err := os.Mkdir(p, 0700); err != nil {
			return nil, fmt.Errorf("create update staging directory: %w", err)
		}
	}
	tokenBytes := make([]byte, 32)
	if _, err = rand.Read(tokenBytes); err != nil {
		return nil, err
	}
	plan = &portableUpdatePlan{Schema: 1, Phase: "staging", ParentPID: os.Getpid(), Token: hex.EncodeToString(tokenBytes), Args: append([]string{}, args...), Manifest: manifest}
	progress.begin("Comparing installed files", "files", int64(len(manifest.Files)), 0)
	for _, f := range manifest.Files {
		target, pathErr := safeUpdateTarget(root, f.Path)
		if pathErr != nil {
			return nil, pathErr
		}
		digest, hashErr := hashUpdateFile(target, f.Size)
		if hashErr != nil && !errors.Is(hashErr, os.ErrNotExist) {
			return nil, hashErr
		}
		if digest != f.SHA256 {
			info, statErr := os.Lstat(target)
			op := portableUpdateOperation{File: f, HadOriginal: statErr == nil}
			if statErr == nil {
				if info.Size() > maxUpdateFileBytes {
					return nil, fmt.Errorf("original update destination is too large: %s", f.Path)
				}
				op.OriginalSize = info.Size()
				op.OriginalSHA256, err = hashUpdateFile(target, info.Size())
				if err != nil || op.OriginalSHA256 == "" {
					return nil, fmt.Errorf("verify original update destination: %s", f.Path)
				}
			}
			plan.Operations = append(plan.Operations, op)
		}
		progress.add(1)
	}
	progress.finish()
	// Removal is restricted to files recorded by a previous verified update and
	// still byte-identical. First migration deliberately keeps unknown files.
	previous, previousErr := readInstalledUpdateManifest(root)
	if previousErr == nil {
		progress.begin("Checking obsolete package files", "files", int64(len(previous.Files)), 0)
		currentPaths := make(map[string]bool, len(manifest.Files))
		for _, f := range manifest.Files {
			currentPaths[strings.ToLower(f.Path)] = true
		}
		for _, old := range previous.Files {
			if currentPaths[strings.ToLower(old.Path)] || protectedUpdatePath(old.Path) {
				progress.add(1)
				continue
			}
			target, pathErr := safeUpdateTarget(root, old.Path)
			if pathErr != nil {
				return nil, pathErr
			}
			if digest, hashErr := hashUpdateFile(target, old.Size); hashErr == nil && digest == old.SHA256 {
				plan.Operations = append(plan.Operations, portableUpdateOperation{File: old, HadOriginal: true, OriginalSize: old.Size, OriginalSHA256: old.SHA256, Remove: true})
			}
			progress.add(1)
		}
		progress.finish()
	} else if !errors.Is(previousErr, os.ErrNotExist) {
		return nil, previousErr
	}
	for i := range plan.Operations {
		plan.Operations[i].Stage = fmt.Sprintf("stage/%06d", i)
		plan.Operations[i].Backup = fmt.Sprintf("backup/%06d", i)
	}
	cacheDir, err := safeUpdateChild(root, portableUpdateCacheDirectory)
	if err != nil {
		return nil, err
	}
	pruneUpdateCache(cacheDir, plan.Operations)
	progress.begin("Reading update ZIP index", "", 0, 0)
	if err = writePortableUpdatePlan(root, plan); err != nil {
		return nil, err
	}
	reader, err := newUpdateRangeReader(ctx, client, assetURL, manifest.Size)
	if err != nil {
		return nil, err
	}
	index, err := indexedUpdateZip(reader, manifest)
	if err != nil {
		return nil, err
	}
	progress.finish()
	var changedBytes, changedFiles int64
	for _, op := range plan.Operations {
		if !op.Remove {
			changedBytes += op.File.Size
			changedFiles++
		}
	}
	progress.begin("Downloading, extracting and verifying changed files", "bytes", changedBytes, changedFiles)
	for i := range plan.Operations {
		op := &plan.Operations[i]
		if op.Remove {
			continue
		}
		stagePath := filepath.Join(stateDir, filepath.FromSlash(op.Stage))
		if reuseCachedUpdateFile(filepath.Join(cacheDir, op.File.SHA256), stagePath, op.File) {
			progress.add(op.File.Size)
			progress.verifiedFile()
			continue
		}
		entry := index[strings.ToLower(op.File.Path)]
		input, openErr := entry.Open()
		if openErr != nil {
			return nil, openErr
		}
		stage, createErr := os.OpenFile(stagePath, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
		if createErr != nil {
			input.Close()
			return nil, createErr
		}
		hash := sha256.New()
		written, copyErr := io.Copy(updateProgressWriter{output: io.MultiWriter(stage, hash), progress: progress}, io.LimitReader(input, op.File.Size+1))
		inputErr := input.Close()
		syncErr := stage.Sync()
		closeErr := stage.Close()
		if copyErr != nil || inputErr != nil || syncErr != nil || closeErr != nil || written != op.File.Size || hex.EncodeToString(hash.Sum(nil)) != op.File.SHA256 {
			err = errors.Join(copyErr, inputErr, syncErr, closeErr)
			if err == nil {
				err = fmt.Errorf("download verification failed for %s (size or SHA256 mismatch)", op.File.Path)
			} else {
				err = fmt.Errorf("download verification failed for %s: %w", op.File.Path, err)
			}
			return nil, err
		}
		progress.verifiedFile()
	}
	identityPath := filepath.Join(root, "portable-release.json")
	for _, op := range plan.Operations {
		if op.File.Path == "portable-release.json" && !op.Remove {
			identityPath = filepath.Join(stateDir, filepath.FromSlash(op.Stage))
		}
	}
	identityBytes, err := os.ReadFile(identityPath)
	if err != nil {
		return nil, err
	}
	var identity portableReleaseIdentity
	if json.Unmarshal(identityBytes, &identity) != nil || identity.Schema != 1 || identity.Revision != manifest.Revision || identity.Package != manifest.Package || identity.Version != "latest" {
		return nil, errors.New("release identity does not match the verified update")
	}
	plan.Phase = "staged"
	if err = writePortableUpdatePlan(root, plan); err != nil {
		return nil, err
	}
	// Every needed cached file is now staged; the rest are duplicates.
	_ = os.RemoveAll(cacheDir)
	progress.finish()
	return plan, nil
}

// keepStagedUpdateFiles moves complete downloads of an unfinished update into
// the download cache, named by their expected SHA-256, so the next attempt
// fetches only the files that are still missing. The cache is best effort and
// untrusted: staging verifies each cached file again before reusing it.
func keepStagedUpdateFiles(root string, plan *portableUpdatePlan) {
	cacheDir, err := safeUpdateChild(root, portableUpdateCacheDirectory)
	if err != nil {
		return
	}
	created := false
	for _, op := range plan.Operations {
		if op.Remove || op.File.Size == 0 {
			continue
		}
		stage, err := safeUpdateChild(root, portableUpdateDirectory+"/"+op.Stage)
		if err != nil {
			continue
		}
		if info, err := os.Lstat(stage); err != nil || !info.Mode().IsRegular() || info.Size() != op.File.Size {
			continue
		}
		if !created {
			if err := os.Mkdir(cacheDir, 0700); err != nil && !errors.Is(err, os.ErrExist) {
				return
			}
			created = true
		}
		_ = os.Rename(stage, filepath.Join(cacheDir, op.File.SHA256))
	}
}

// pruneUpdateCache keeps only cached files that this update still needs, so
// failed attempts across several releases cannot accumulate downloads.
func pruneUpdateCache(cacheDir string, operations []portableUpdateOperation) {
	entries, err := os.ReadDir(cacheDir)
	if err != nil {
		return
	}
	needed := make(map[string]bool, len(operations))
	for _, op := range operations {
		if !op.Remove {
			needed[op.File.SHA256] = true
		}
	}
	for _, entry := range entries {
		if !needed[entry.Name()] {
			_ = os.Remove(filepath.Join(cacheDir, entry.Name()))
		}
	}
}

func reuseCachedUpdateFile(cached, stage string, file portableUpdateFile) bool {
	digest, err := hashUpdateFile(cached, file.Size)
	if err != nil {
		return false
	}
	if digest != file.SHA256 {
		_ = os.Remove(cached)
		return false
	}
	return os.Rename(cached, stage) == nil
}

func launchPortableUpdateHelper(root string, plan *portableUpdatePlan) error {
	stateDir := filepath.Join(root, portableUpdateDirectory)
	launcher := filepath.Join(root, "startup.exe")
	var launcherFile portableUpdateFile
	for _, f := range plan.Manifest.Files {
		if f.Path == "startup.exe" {
			launcherFile = f
		}
	}
	for _, op := range plan.Operations {
		if op.File.Path == "startup.exe" && !op.Remove {
			launcher = filepath.Join(stateDir, filepath.FromSlash(op.Stage))
		}
	}
	helper := filepath.Join(stateDir, "helper.exe")
	if err := copyVerifiedUpdateFile(launcher, helper, launcherFile, 0700); err != nil {
		return err
	}
	cmd := exec.Command(helper, portableUpdateHelperFlag, root, fmt.Sprint(os.Getpid()), plan.Token)
	cmd.Dir = root
	cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, os.Stdout, os.Stderr
	configureConsoleProcess(cmd)
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("start verified update helper: %w", err)
	}
	// Wait for the helper's journal acknowledgement before allowing the parent
	// to exit. A concurrent launch can then always see a live journal owner.
	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		acknowledged, err := readPortableUpdatePlan(root)
		if err == nil && acknowledged.HelperPID == cmd.Process.Pid && acknowledged.Token == plan.Token {
			return cmd.Process.Release()
		}
		if alive, _ := isProcessAlive(cmd.Process.Pid); !alive {
			_ = cmd.Wait()
			return errors.New("verified updater could not start; keeping the installed version")
		}
		time.Sleep(50 * time.Millisecond)
	}
	_ = cmd.Process.Kill()
	_ = cmd.Wait()
	return errors.New("verified updater did not respond; keeping the installed version")
}

func copyVerifiedUpdateFile(source, destination string, file portableUpdateFile, mode os.FileMode) error {
	input, err := os.Open(source)
	if err != nil {
		return err
	}
	defer input.Close()
	output, err := os.OpenFile(destination, os.O_WRONLY|os.O_CREATE|os.O_EXCL, mode)
	if err != nil {
		return err
	}
	hash := sha256.New()
	written, copyErr := io.Copy(io.MultiWriter(output, hash), io.LimitReader(input, file.Size+1))
	syncErr, closeErr := output.Sync(), output.Close()
	if copyErr != nil || syncErr != nil || closeErr != nil || written != file.Size || hex.EncodeToString(hash.Sum(nil)) != file.SHA256 {
		_ = os.Remove(destination)
		return errors.New("verified launcher copy failed")
	}
	return nil
}
