package main

import (
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
		if err := os.Remove(temporary); err != nil {
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
	if err := os.Rename(temporary, filename); err != nil {
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
	defer file.Close()
	content, err := io.ReadAll(io.LimitReader(file, (32<<20)+1))
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
		if op.State != "" && op.State != "applying" && op.State != "applied" && op.State != "rolled-back" {
			return nil, errors.New("invalid update operation state")
		}
		if !op.Remove && files[op.File.Path] != op.File || op.Remove && !op.HadOriginal {
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
	for _, relative := range []string{"stage", "backup"} {
		filename, err := safeUpdateChild(root, portableUpdateDirectory+"/"+relative)
		if err != nil {
			return err
		}
		// RemoveAll never follows links inside an unused staging tree.
		if err := os.RemoveAll(filename); err != nil {
			return err
		}
	}
	for _, relative := range []string{"journal.json", "journal.json.tmp", "owner.json", "helper.exe"} {
		filename, err := safeUpdateChild(root, portableUpdateDirectory+"/"+relative)
		if err != nil {
			return err
		}
		if err := os.Remove(filename); err != nil && !errors.Is(err, os.ErrNotExist) {
			if relative != "helper.exe" {
				return err
			}
			// Windows retains the executing helper until it exits. The next
			// normal launcher startup removes this verified temporary copy.
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
			if alive, _ := isProcessAlive(owner.PID); alive && owner.PID != os.Getpid() {
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
		if pid != os.Getpid() {
			if alive, _ := isProcessAlive(pid); alive {
				return errors.New("another launcher is updating this installation; wait for it to finish")
			}
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

func validateStagedUpdate(root string, plan *portableUpdatePlan) error {
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
	}
	return nil
}

func applyPortableUpdate(root string, plan *portableUpdatePlan) error {
	if err := ensurePortableUpdateStopped(root, os.Getpid()); err != nil {
		return err
	}
	if err := validateStagedUpdate(root, plan); err != nil {
		return err
	}
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
		if op.Remove {
			digest, err := hashUpdateFile(target, op.File.Size)
			if err != nil || digest != op.File.SHA256 {
				return rollbackUpdateAfterError(root, plan, errors.New("obsolete package file was modified during update"))
			}
		}
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
			if err := os.Rename(target, backup); err != nil {
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
			if err := os.Rename(stage, target); err != nil {
				return rollbackUpdateAfterError(root, plan, err)
			}
		}
		if err := syncUpdateDirectory(filepath.Dir(target)); err != nil {
			return rollbackUpdateAfterError(root, plan, err)
		}
		op.State = "applied"
		if err := writePortableUpdatePlan(root, plan); err != nil {
			return rollbackUpdateAfterError(root, plan, err)
		}
	}
	plan.Phase = "committed"
	if err := writePortableUpdatePlan(root, plan); err != nil {
		return rollbackUpdateAfterError(root, plan, err)
	}
	return finishPortableUpdate(root, plan)
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
		if info, err := os.Lstat(backup); err == nil {
			if !info.Mode().IsRegular() {
				return errors.New("unsafe rollback backup")
			}
			if digest, err := hashUpdateFile(backup, op.OriginalSize); err != nil || digest != op.OriginalSHA256 {
				return fmt.Errorf("rollback backup failed original-file verification: %s", op.File.Path)
			}
			if err := os.Remove(target); err != nil && !errors.Is(err, os.ErrNotExist) {
				return err
			}
			if err := os.Rename(backup, target); err != nil {
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
				if err := os.Remove(target); err != nil {
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
	plan.HelperPID = os.Getpid()
	if err := writePortableUpdatePlan(root, plan); err != nil {
		return true, err
	}
	deadline := time.Now().Add(2 * time.Minute)
	for {
		alive, _ := isProcessAlive(parentPID)
		if !alive {
			break
		}
		if time.Now().After(deadline) {
			return true, errors.New("launcher is still running; update was not applied")
		}
		time.Sleep(100 * time.Millisecond)
	}
	if err := applyPortableUpdate(root, plan); err != nil {
		return true, err
	}
	fmt.Println("Update complete. Restarting the launcher.")
	cmd := exec.Command(filepath.Join(root, "startup.exe"), plan.Args...)
	cmd.Dir = root
	cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, os.Stdout, os.Stderr
	configureConsoleProcess(cmd)
	if err := cmd.Start(); err != nil {
		return true, fmt.Errorf("update completed; start startup.exe again: %w", err)
	}
	return true, cmd.Process.Release()
}
