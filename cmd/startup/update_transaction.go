package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

type portableUpdateOperation struct {
	File           portableUpdateFile `json:"file"`
	Stage          string             `json:"stage"`
	Backup         string             `json:"backup"`
	HadOriginal    bool               `json:"hadOriginal"`
	OriginalSize   int64              `json:"originalSize,omitempty"`
	OriginalSHA256 string             `json:"originalSha256,omitempty"`
	Remove         bool               `json:"remove,omitempty"`
	State          string             `json:"state,omitempty"`
}

type portableUpdatePlan struct {
	Schema     int                       `json:"schema"`
	Phase      string                    `json:"phase"`
	ParentPID  int                       `json:"parentPID"`
	HelperPID  int                       `json:"helperPID,omitempty"`
	Token      string                    `json:"token"`
	Args       []string                  `json:"args"`
	Manifest   portableUpdateManifest    `json:"manifest"`
	Operations []portableUpdateOperation `json:"operations"`
}

type portableUpdateOwner struct {
	PID int `json:"pid"`
}

// Windows refuses to rename or remove a file while another process has it
// open without FILE_SHARE_DELETE. Antivirus scanners, indexers and an older
// launcher polling journal.json do that briefly, so retry those errors for a
// short time. Other errors, and every error on other platforms, return at once.
func retryUpdateFileOperation(operation func() error) error {
	return retryTransientUpdateError(operation, transientUpdateFileError, 2*time.Second)
}

func retryTransientUpdateError(operation func() error, transient func(error) bool, budget time.Duration) error {
	deadline := time.Now().Add(budget)
	for delay := 10 * time.Millisecond; ; delay = min(2*delay, 200*time.Millisecond) {
		err := operation()
		if err == nil || !transient(err) || time.Now().Add(delay).After(deadline) {
			return err
		}
		time.Sleep(delay)
	}
}

func renameUpdateFile(from, to string) error {
	return retryUpdateFileOperation(func() error { return os.Rename(from, to) })
}

func removeUpdateFile(filename string) error {
	return retryUpdateFileOperation(func() error { return os.Remove(filename) })
}

func writeUpdateJSON(filename string, value any) error {
	content, err := json.Marshal(value)
	if err != nil {
		return err
	}
	temporary := filename + ".tmp"
	file, err := os.OpenFile(temporary, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if errors.Is(err, os.ErrExist) {
		if info, statErr := os.Lstat(temporary); statErr != nil || !info.Mode().IsRegular() {
			return errors.New("unsafe updater temporary file")
		}
		if err := removeUpdateFile(temporary); err != nil {
			return err
		}
		file, err = os.OpenFile(temporary, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	}
	if err != nil {
		return err
	}
	_, writeErr := file.Write(content)
	syncErr, closeErr := file.Sync(), file.Close()
	if err := errors.Join(writeErr, syncErr, closeErr); err != nil {
		_ = os.Remove(temporary)
		return err
	}
	if err := renameUpdateFile(temporary, filename); err != nil {
		_ = os.Remove(temporary)
		return err
	}
	return syncUpdateDirectory(filepath.Dir(filename))
}

func writePortableUpdatePlan(root string, plan *portableUpdatePlan) error {
	filename, err := safeUpdateChild(root, portableUpdateDirectory+"/journal.json")
	if err != nil {
		return err
	}
	return writeUpdateJSON(filename, plan)
}

func readLimitedUpdateJSON(filename string, destination any) error {
	info, err := os.Lstat(filename)
	if err != nil {
		return err
	}
	if !info.Mode().IsRegular() || info.Size() > 32<<20 {
		return errors.New("invalid update state file")
	}
	file, err := os.Open(filename)
	if err != nil {
		return err
	}
	// Close before decoding: an open handle blocks the helper's journal rename.
	content, err := io.ReadAll(io.LimitReader(file, (32<<20)+1))
	file.Close()
	if err != nil || len(content) > 32<<20 {
		return errors.New("invalid update state file")
	}
	return json.Unmarshal(content, destination)
}

func readPortableUpdatePlan(root string) (*portableUpdatePlan, error) {
	filename, err := safeUpdateChild(root, portableUpdateDirectory+"/journal.json")
	if err != nil {
		return nil, err
	}
	var plan portableUpdatePlan
	if err := readLimitedUpdateJSON(filename, &plan); err != nil {
		return nil, err
	}
	if plan.Schema != 1 || plan.ParentPID <= 0 || !updateDigestPattern.MatchString(plan.Token) || len(plan.Operations) > 100000 {
		return nil, errors.New("invalid update journal")
	}
	if plan.Phase != "staging" && plan.Phase != "staged" && plan.Phase != "applying" && plan.Phase != "committed" && plan.Phase != "rolled-back" {
		return nil, errors.New("invalid update journal phase")
	}
	if err := validateUpdateManifest(plan.Manifest); err != nil {
		return nil, err
	}
	files := make(map[string]portableUpdateFile, len(plan.Manifest.Files))
	for _, file := range plan.Manifest.Files {
		files[file.Path] = file
	}
	seen := make(map[string]bool, len(plan.Operations))
	for i, op := range plan.Operations {
		if err := validateUpdatePath(op.File.Path); err != nil {
			return nil, err
		}
		if seen[strings.ToLower(op.File.Path)] || op.Stage != fmt.Sprintf("stage/%06d", i) || op.Backup != fmt.Sprintf("backup/%06d", i) || op.File.Size < 0 || !updateDigestPattern.MatchString(op.File.SHA256) {
			return nil, errors.New("invalid update journal operation")
		}
		seen[strings.ToLower(op.File.Path)] = true
		// Earlier helpers also recorded "applied"; rollback treats it like "applying".
		if op.State != "" && op.State != "applying" && op.State != "applied" && op.State != "rolled-back" {
			return nil, errors.New("invalid update operation state")
		}
		if !op.Remove && files[op.File.Path] != op.File || op.Remove && (!op.HadOriginal || op.OriginalSize != op.File.Size || op.OriginalSHA256 != op.File.SHA256) {
			return nil, errors.New("update operation differs from manifest")
		}
		if op.HadOriginal && (op.OriginalSize < 0 || op.OriginalSize > maxUpdateFileBytes || !updateDigestPattern.MatchString(op.OriginalSHA256)) {
			return nil, errors.New("update journal is missing original-file verification")
		}
	}
	return &plan, nil
}

func readInstalledUpdateManifest(root string) (portableUpdateManifest, error) {
	var manifest portableUpdateManifest
	filename, err := safeUpdateChild(root, portableUpdateDirectory+"/installed.json")
	if err != nil {
		return manifest, err
	}
	if err := readLimitedUpdateJSON(filename, &manifest); err != nil {
		return manifest, err
	}
	return manifest, validateUpdateManifest(manifest)
}

func discardStagedUpdate(root string) error {
	if plan, err := readPortableUpdatePlan(root); err == nil && plan.Phase != "committed" {
		keepStagedUpdateFiles(root, plan)
	}
	for _, relative := range []string{"stage", "backup"} {
		filename, err := safeUpdateChild(root, portableUpdateDirectory+"/"+relative)
		if err != nil {
			return err
		}
		// RemoveAll never follows links inside an unused staging tree.
		if err := retryUpdateFileOperation(func() error { return os.RemoveAll(filename) }); err != nil {
			return err
		}
	}
	for _, relative := range []string{"journal.json", "journal.json.tmp", "owner.json", "helper.exe"} {
		filename, err := safeUpdateChild(root, portableUpdateDirectory+"/"+relative)
		if err != nil {
			return err
		}
		if relative == "helper.exe" {
			// Windows retains the executing helper until it exits. The next
			// normal launcher startup removes this verified temporary copy.
			_ = os.Remove(filename)
		} else if err := removeUpdateFile(filename); err != nil && !errors.Is(err, os.ErrNotExist) {
			return err
		}
	}
	return nil
}

func recoverPortableUpdate(root string) error {
	plan, err := readPortableUpdatePlan(root)
	if errors.Is(err, os.ErrNotExist) {
		ownerPath, pathErr := safeUpdateChild(root, portableUpdateDirectory+"/owner.json")
		if pathErr != nil {
			return pathErr
		}
		var owner portableUpdateOwner
		if ownerErr := readLimitedUpdateJSON(ownerPath, &owner); ownerErr == nil {
			if owner.PID != os.Getpid() && updateProcessActive(root, owner.PID) {
				return errors.New("another launcher is preparing an update; wait for it to finish")
			}
		} else if !errors.Is(ownerErr, os.ErrNotExist) {
			return ownerErr
		}
		return discardStagedUpdate(root)
	}
	if err != nil {
		return fmt.Errorf("read pending update: %w", err)
	}
	for _, pid := range []int{plan.ParentPID, plan.HelperPID} {
		if pid != os.Getpid() && updateProcessActive(root, pid) {
			return errors.New("another launcher is updating this installation; wait for it to finish")
		}
	}
	if plan.Phase == "committed" {
		return finishPortableUpdate(root, plan)
	}
	if plan.Phase == "applying" {
		if err := ensurePortableUpdateStopped(root, os.Getpid()); err != nil {
			return err
		}
		if err := rollbackPortableUpdate(root, plan); err != nil {
			return fmt.Errorf("restore interrupted update before starting servers: %w", err)
		}
	}
	return discardStagedUpdate(root)
}

// updateProcessActive reports whether pid runs a program from this
// installation's root or update directory, as the launcher and the update
// helper do. Owner and journal files outlive crashes and reboots, and Windows
// soon reuses process IDs, so an unrelated process that later received a
// recorded ID must not block startup. A process whose program cannot be
// located still counts as active.
func updateProcessActive(root string, pid int) bool {
	executable, err := processExecutable(pid)
	if errors.Is(err, os.ErrProcessDone) {
		return false
	}
	if err != nil {
		return true
	}
	folder, err := os.Stat(filepath.Dir(executable))
	if err != nil {
		return true
	}
	for _, candidate := range []string{root, filepath.Join(root, portableUpdateDirectory)} {
		if info, err := os.Stat(candidate); err == nil && os.SameFile(info, folder) {
			return true
		}
	}
	return false
}

// pollProcessExit reports whether pid exited within timeout.
func pollProcessExit(pid int, timeout time.Duration) bool {
	deadline := time.Now().Add(timeout)
	for {
		if alive, _ := isProcessAlive(pid); !alive {
			return true
		}
		if time.Now().After(deadline) {
			return false
		}
		time.Sleep(100 * time.Millisecond)
	}
}

func validateStagedUpdate(root string, plan *portableUpdatePlan, progress *portableUpdateProgress) error {
	for _, op := range plan.Operations {
		target, err := safeUpdateTarget(root, op.File.Path)
		if err != nil {
			return err
		}
		if op.HadOriginal {
			if digest, err := hashUpdateFile(target, op.OriginalSize); err != nil || digest != op.OriginalSHA256 {
				return fmt.Errorf("installed file changed during update download: %s", op.File.Path)
			}
		}
		if op.Remove {
			progress.add(1)
			continue
		}
		stage, err := safeUpdateChild(root, portableUpdateDirectory+"/"+op.Stage)
		if err != nil {
			return err
		}
		digest, err := hashUpdateFile(stage, op.File.Size)
		if err != nil || digest != op.File.SHA256 {
			return fmt.Errorf("staged update verification failed: %s", op.File.Path)
		}
		progress.add(1)
	}
	return nil
}

func applyPortableUpdate(root string, plan *portableUpdatePlan, progress *portableUpdateProgress) error {
	if err := ensurePortableUpdateStopped(root, os.Getpid()); err != nil {
		return err
	}
	progress.begin("Verifying staged update files", "files", int64(len(plan.Operations)), 0)
	if err := validateStagedUpdate(root, plan, progress); err != nil {
		return err
	}
	progress.finish()
	progress.begin("Installing verified files", "files", int64(len(plan.Operations)), 0)
	plan.Phase = "applying"
	if err := writePortableUpdatePlan(root, plan); err != nil {
		return err
	}
	for i := range plan.Operations {
		op := &plan.Operations[i]
		target, err := safeUpdateTarget(root, op.File.Path)
		if err != nil {
			return rollbackUpdateAfterError(root, plan, err)
		}
		stage, err := safeUpdateChild(root, portableUpdateDirectory+"/"+op.Stage)
		if err != nil {
			return rollbackUpdateAfterError(root, plan, err)
		}
		backup, err := safeUpdateChild(root, portableUpdateDirectory+"/"+op.Backup)
		if err != nil {
			return rollbackUpdateAfterError(root, plan, err)
		}
		if err := os.MkdirAll(filepath.Dir(target), 0755); err != nil {
			return rollbackUpdateAfterError(root, plan, err)
		}
		// A removal's original is the obsolete package file itself.
		if op.HadOriginal {
			digest, err := hashUpdateFile(target, op.OriginalSize)
			if err != nil || digest != op.OriginalSHA256 {
				return rollbackUpdateAfterError(root, plan, errors.New("update destination changed before commit"))
			}
		} else if _, err := os.Lstat(target); !errors.Is(err, os.ErrNotExist) {
			return rollbackUpdateAfterError(root, plan, errors.New("a new update destination appeared during staging"))
		}
		op.State = "applying"
		if err := writePortableUpdatePlan(root, plan); err != nil {
			return rollbackUpdateAfterError(root, plan, err)
		}
		if op.HadOriginal {
			if err := renameUpdateFile(target, backup); err != nil {
				return rollbackUpdateAfterError(root, plan, err)
			}
		}
		if !op.Remove {
			if err := os.Chmod(stage, 0644); err != nil {
				return rollbackUpdateAfterError(root, plan, err)
			}
			if strings.HasSuffix(strings.ToLower(op.File.Path), ".exe") {
				if err := os.Chmod(stage, 0755); err != nil {
					return rollbackUpdateAfterError(root, plan, err)
				}
			}
			if err := renameUpdateFile(stage, target); err != nil {
				return rollbackUpdateAfterError(root, plan, err)
			}
		}
		if err := syncUpdateDirectory(filepath.Dir(target)); err != nil {
			return rollbackUpdateAfterError(root, plan, err)
		}
		// Rollback treats a started operation the same whether or not it
		// finished, so completed files stay "applying". Recording "applied"
		// would rewrite the whole journal, manifest included, twice per file.
		progress.add(1)
	}
	plan.Phase = "committed"
	if err := writePortableUpdatePlan(root, plan); err != nil {
		return rollbackUpdateAfterError(root, plan, err)
	}
	if err := finishPortableUpdate(root, plan); err != nil {
		return err
	}
	progress.finish()
	return nil
}

func rollbackUpdateAfterError(root string, plan *portableUpdatePlan, cause error) error {
	if err := rollbackPortableUpdate(root, plan); err != nil {
		return fmt.Errorf("update failed (%v); rollback failed: %w; do not start the servers", cause, err)
	}
	return fmt.Errorf("update was restored to the previous version: %w", cause)
}

func rollbackPortableUpdate(root string, plan *portableUpdatePlan) error {
	for i := len(plan.Operations) - 1; i >= 0; i-- {
		op := &plan.Operations[i]
		if op.State == "" || op.State == "rolled-back" {
			continue
		}
		target, err := safeUpdateTarget(root, op.File.Path)
		if err != nil {
			return err
		}
		backup, err := safeUpdateChild(root, portableUpdateDirectory+"/"+op.Backup)
		if err != nil {
			return err
		}
		stage, err := safeUpdateChild(root, portableUpdateDirectory+"/"+op.Stage)
		if err != nil {
			return err
		}
		if info, err := os.Lstat(backup); err == nil {
			if !info.Mode().IsRegular() {
				return errors.New("unsafe rollback backup")
			}
			if digest, err := hashUpdateFile(backup, op.OriginalSize); err != nil || digest != op.OriginalSHA256 {
				return fmt.Errorf("rollback backup failed original-file verification: %s", op.File.Path)
			}
			if err := unstageUpdateFile(target, stage); err != nil {
				return err
			}
			if err := renameUpdateFile(backup, target); err != nil {
				return err
			}
		} else if !errors.Is(err, os.ErrNotExist) {
			return err
		} else if !op.HadOriginal {
			// No original existed. Only remove the file that we verified and
			// installed; preserve any externally changed destination.
			if digest, err := hashUpdateFile(target, op.File.Size); err == nil {
				if digest != op.File.SHA256 {
					return errors.New("new update file changed before rollback")
				}
				if err := unstageUpdateFile(target, stage); err != nil {
					return err
				}
			} else if !errors.Is(err, os.ErrNotExist) {
				return err
			}
		} else {
			if digest, err := hashUpdateFile(target, op.OriginalSize); err != nil {
				return errors.New("original and backup are both missing; restore from a backup before starting servers")
			} else if digest != op.OriginalSHA256 {
				return fmt.Errorf("rollback backup is missing and %s is not the original file; restore a backup before starting servers", op.File.Path)
			}
		}
		op.State = "rolled-back"
		if err := writePortableUpdatePlan(root, plan); err != nil {
			return err
		}
	}
	plan.Phase = "rolled-back"
	return writePortableUpdatePlan(root, plan)
}

// unstageUpdateFile moves an installed update file back to its staging name
// instead of deleting it. Recovery runs from the installed startup.exe, which
// may be the new launcher that the interrupted update had already installed;
// Windows cannot delete a running program but can rename it. Discarding the
// update then keeps the file as a download for the next attempt.
func unstageUpdateFile(target, stage string) error {
	info, err := os.Lstat(target)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	if !info.Mode().IsRegular() {
		return fmt.Errorf("rollback destination is not a regular file: %s", target)
	}
	if err := os.MkdirAll(filepath.Dir(stage), 0700); err != nil {
		return err
	}
	return renameUpdateFile(target, stage)
}

func finishPortableUpdate(root string, plan *portableUpdatePlan) error {
	filename, err := safeUpdateChild(root, portableUpdateDirectory+"/installed.json")
	if err != nil {
		return err
	}
	if err := writeUpdateJSON(filename, plan.Manifest); err != nil {
		return err
	}
	return discardStagedUpdate(root)
}

func runPortableUpdateHelper(args []string) (bool, error) {
	if len(args) == 0 || args[0] != portableUpdateHelperFlag {
		return false, nil
	}
	if len(args) != 4 {
		return true, errors.New("invalid internal updater invocation")
	}
	root, err := filepath.Abs(args[1])
	if err != nil {
		return true, err
	}
	parentPID, err := parseUpdateParentPID(args[2])
	if err != nil {
		return true, err
	}
	plan, err := readPortableUpdatePlan(root)
	if err != nil {
		return true, err
	}
	executable, err := os.Executable()
	if err != nil || !strings.EqualFold(filepath.Clean(executable), filepath.Join(root, portableUpdateDirectory, "helper.exe")) || parentPID != plan.ParentPID || args[3] != plan.Token || plan.Phase != "staged" {
		return true, errors.New("untrusted internal updater invocation")
	}
	// The launcher waits for this acknowledgement, so it is still running
	// here; a number reused after it exits cannot delay the update.
	parentExited := watchProcessExit(parentPID)
	plan.HelperPID = os.Getpid()
	if err := writePortableUpdatePlan(root, plan); err != nil {
		return true, err
	}
	if !parentExited(2 * time.Minute) {
		return true, errors.New("launcher is still running; update was not applied")
	}
	progress := startPortableUpdateProgress(context.Background())
	defer progress.close()
	if err := applyPortableUpdate(root, plan, progress); err != nil {
		progress.close()
		// The original launcher has exited. Start the intact installed release
		// so the realm still runs and this console keeps the reason visible.
		if !discardIntactUpdate(root) {
			return true, err
		}
		fmt.Fprintf(os.Stderr, "Error completing update: %v\nStarting the installed release without the update check.\n", err)
		if err := restartPortableLauncher(root, withoutUpdateCheck(plan.Args)); err != nil {
			return true, fmt.Errorf("start startup.exe again: %w", err)
		}
		return true, nil
	}
	progress.close()
	fmt.Println("Update complete. Restarting the launcher.")
	if err := restartPortableLauncher(root, plan.Args); err != nil {
		return true, fmt.Errorf("update completed; start startup.exe again: %w", err)
	}
	return true, nil
}

// discardIntactUpdate clears an update that never changed installed files or
// was completely rolled back, and reports whether the installed release is
// intact. Downloads stay cached for the next attempt. An update that is still
// applying, after a failed rollback, keeps its journal for recovery.
func discardIntactUpdate(root string) bool {
	plan, err := readPortableUpdatePlan(root)
	if err != nil || plan.Phase != "staged" && plan.Phase != "rolled-back" {
		return false
	}
	return discardStagedUpdate(root) == nil
}

// withoutUpdateCheck adds --no-update once, before any "--" terminator, so a
// release that cannot be installed is not downloaded again in a loop.
func withoutUpdateCheck(args []string) []string {
	for _, arg := range args {
		if arg == "--no-update" || arg == "-no-update" {
			return args
		}
	}
	return append([]string{"--no-update"}, args...)
}

func restartPortableLauncher(root string, args []string) error {
	cmd := exec.Command(filepath.Join(root, "startup.exe"), args...)
	cmd.Dir = root
	cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, os.Stdout, os.Stderr
	configureConsoleProcess(cmd)
	if err := cmd.Start(); err != nil {
		return err
	}
	return cmd.Process.Release()
}
