package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

func dirExists(path string) bool {
	if path == "" {
		return false
	}
	info, err := os.Stat(path)
	return err == nil && info.IsDir()
}

func directoryHasEntries(path string) bool {
	directory, err := os.Open(path)
	if err != nil {
		return false
	}
	defer directory.Close()
	entries, err := directory.Readdirnames(1)
	return err == nil && len(entries) > 0
}

func fileExists(path string) bool {
	if path == "" {
		return false
	}
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}

func findExecutable(dir, name string) string {
	exts := []string{".exe", ".bat", ".cmd", ""}

	if dir != "" {
		absolute, err := filepath.Abs(dir)
		if err != nil {
			return ""
		}
		for _, ext := range exts {
			fullPath := filepath.Join(absolute, name+ext)
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
	if baseDataDir != workDataDir && directoryHasEntries(baseDataDir) {
		dataDirForConf = filepath.ToSlash(baseDataDir)
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
			if strings.EqualFold(filepath.Dir(relPath), "modules") && retiredModuleConfig(info.Name()) {
				return nil
			}
			targetConfPath := filepath.Join(configDstDir, relTargetName)

			if !fileExists(targetConfPath) {
				data, err := os.ReadFile(path)
				if err != nil {
					return fmt.Errorf("failed to read %s: %w", path, err)
				}

				content := string(data)
				var settings []string
				for _, setting := range []struct{ key, baseline, value string }{
					{"DataDir", `"."`, dataDirForConf},
					{"LogsDir", `""`, "logs"},
					{"SourceDirectory", `""`, srcDirForConf},
					{"MySQLExecutable", `""`, mysqlExeForConf},
					{"BindIP", `"0.0.0.0"`, "127.0.0.1"},
				} {
					if value, exists := configValue(content, setting.key); exists && value == setting.baseline {
						settings = append(settings, setting.key+` = "`+setting.value+`"`)
					}
				}
				content, err = mergeConfigProfile(content, strings.Join(settings, "\n"))
				if err != nil {
					return err
				}

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
