package main

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

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

type mysqlBinaries struct {
	mysqld     string
	mysql      string
	mysqladmin string
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

func mysqlBufferPoolSettings(totalRAMBytes uint64) (sizeStr string, instances int, totalRAMGB int) {
	if totalRAMBytes == 0 {
		return "1G", 1, 0
	}

	ramGB := int((totalRAMBytes + (512 * 1024 * 1024)) / (1024 * 1024 * 1024))
	// Leave memory available for worldserver, bots and the OS on the same host.
	poolMB := min(max(totalRAMBytes/4/(1024*1024), 512), 8192)
	poolMB -= poolMB % 256

	instances = max(int(poolMB/2048), 1)
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
