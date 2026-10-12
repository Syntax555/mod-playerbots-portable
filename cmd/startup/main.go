package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"sync"
	"syscall"
	"time"
)

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

func parseArgs(args []string) (startupOptions, error) {
	var opts startupOptions

	fs := flag.NewFlagSet("startup", flag.ContinueOnError)

	defaultMysql := findDefaultMySQLDir()

	fs.StringVar(&opts.mysqlDir, "mysql-dir", defaultMysql, "Path to MySQL root directory. Default: ./mysql or $env:MYSQL_ROOT")
	fs.StringVar(&opts.dataDir, "data-dir", "", "Path to MySQL data directory. Default: <work-dir>/mysql/data")
	fs.StringVar(&opts.mysqlCnf, "mysql-cnf", "", "Path to MySQL configuration file (my.cnf or my.ini). Default: auto-detected in <work-dir>/mysql")
	fs.IntVar(&opts.port, "port", 3306, "MySQL server port. Without this flag, the LoginDatabaseInfo port of existing configs is used.")
	fs.IntVar(&opts.authPort, "auth-port", 3724, "Authserver realm port for a newly created authserver.conf.")
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

func main() {
	os.Exit(run(os.Args[1:]))
}

// run starts the realm and returns the process exit code. Returning instead
// of exiting lets deferred cleanup stop processes started before a failure.
func run(args []string) int {
	if handled, err := runPortableUpdateHelper(args); handled {
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error completing update: %v\n", err)
			return 1
		}
		return 0
	}
	if runtime.GOOS != "windows" {
		fmt.Fprintf(os.Stderr, "Error: mod-playerbots startup tool is only supported on Windows (detected OS: %s)\n", runtime.GOOS)
		return 1
	}

	opts, err := parseArgs(args)
	if err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		fmt.Fprintf(os.Stderr, "Error parsing arguments: %v\n", err)
		return 1
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
			return 1
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
			return 1
		}
		fmt.Printf("Realm expansion: %s; level cap: %d; progression limit: %d (0 = unlimited).\n", phase.name, phase.level, phase.limit)
		if opts.setExpansion != "" {
			fmt.Println("Start startup.exe normally to use this phase. Players and bots still earn their progression; existing characters and databases are preserved.")
		}
		return 0
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
			if updating, err := checkPortableUpdate(rootCtx, baseDir, args); err != nil {
				fmt.Fprintf(os.Stderr, "Update check unavailable; starting installed release: %v\n", err)
			} else if updating {
				return 0
			}
		}
	}
	if rootCtx.Err() != nil {
		fmt.Println("Startup canceled.")
		return 0
	}

	// Handle -download-data-only mode, which needs no MySQL installation
	if opts.downloadDataOnly {
		if err := ensureClientData(rootCtx, workDir, baseDir, opts.dataURL, false); err != nil {
			fmt.Fprintf(os.Stderr, "Error downloading client data: %v\n", err)
			return 1
		}
		fmt.Println("Client data download and extraction complete.")
		return 0
	}

	binaries, err := findMySQLBinaries(opts.mysqlDir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		return 1
	}

	authserverExe := findExecutable(baseDir, "authserver")
	worldserverExe := findExecutable(baseDir, "worldserver")

	if !opts.initOnly {
		if authserverExe == "" {
			fmt.Fprintf(os.Stderr, "Error: authserver executable not found in %s or PATH\n", baseDir)
			return 1
		}
		if worldserverExe == "" {
			fmt.Fprintf(os.Stderr, "Error: worldserver executable not found in %s or PATH\n", baseDir)
			return 1
		}
	}

	// Default dataDir to <workDir>/mysql/data
	if opts.dataDir == "" {
		opts.dataDir = filepath.Join(workDir, "mysql", "data")
	}

	authHosts, err := prepareConfiguration(baseDir, workDir, binaries.mysql, &opts)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		return 1
	}

	// Ensure client data files (maps, vmaps, mmaps, dbc) are present
	if !opts.initOnly {
		if err := ensureClientData(rootCtx, workDir, baseDir, opts.dataURL, opts.skipDataCheck); err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			return 1
		}
	}

	cnfFile := findMySQLConfigFile(opts.mysqlCnf, mysqlInstallDir(opts.mysqlDir, binaries.mysql, workDir), baseDir, workDir)
	if rootCtx.Err() != nil {
		fmt.Println("Startup canceled.")
		return 0
	}

	// 1. Initialize data directory if needed
	if !isDataDirInitialized(opts.dataDir) {
		if err := initializeMySQL(binaries, opts.dataDir, cnfFile); err != nil {
			fmt.Fprintf(os.Stderr, "Error initializing MySQL: %v\n", err)
			return 1
		}
	} else {
		fmt.Printf("MySQL data directory already initialized at %s\n", opts.dataDir)
	}
	if rootCtx.Err() != nil {
		fmt.Println("Startup canceled.")
		return 0
	}

	// 2. Start MySQL Server
	fmt.Println("\n=== [2/4] Starting MySQL server ===")
	mysqlCmd, err := startMySQLServer(binaries, opts.dataDir, opts.port, cnfFile)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error starting MySQL: %v\n", err)
		return 1
	}
	// Until the supervisors own the servers, stop what was started on return.
	supervised := false
	defer func() {
		if !supervised {
			stopMySQLOrWarn(binaries, opts.port, mysqlCmd)
		}
	}()

	// 3. Wait for MySQL to become ready
	timeoutDuration := time.Duration(opts.timeout) * time.Second
	if err := waitForMySQLReady(rootCtx, mysqlCmd, binaries, opts.port, timeoutDuration); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		return 1
	}

	// 4. Apply SQL script
	if !opts.skipSQL {
		if err := runEmbeddedSQL(binaries, opts.port, createMySQLSQL); err != nil {
			fmt.Fprintf(os.Stderr, "Error applying SQL: %v\n", err)
			return 1
		}
	}

	// 5. If init-only, shutdown and exit
	if opts.initOnly {
		fmt.Println("\nInit-only mode complete. Shutting down MySQL...")
		return 0
	}

	// 6. Start authserver and worldserver (staggered)
	fmt.Println("\n=== [4/4] Starting authserver and worldserver ===")

	// Reset the realm status left by a worldserver interrupted during boot
	sanitizeRealmlistFlags(binaries, opts.port)

	authCmd, err := startServerProcess("authserver", authserverExe, workDir, nil)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error starting authserver: %v\n", err)
		return 1
	}
	defer func() {
		if !supervised {
			stopProcess("authserver", authCmd)
		}
	}()

	authTimeout := max(time.Duration(opts.timeout*2)*time.Second, 60*time.Second)

	if err := waitForAuthServerReady(rootCtx, authCmd, authHosts, opts.authPort, authTimeout); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		return 1
	}

	worldCmd, err := startServerProcess("worldserver", worldserverExe, workDir, os.Stdin)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error starting worldserver: %v\n", err)
		return 1
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
		// Crash recovery after an unexpected exit can be slow. Wait at least
		// 30 seconds, and longer when --timeout asks for it.
		if err := waitForMySQLReady(supervisorCtx, cmd, binaries, opts.port, max(timeoutDuration, 30*time.Second)); err != nil {
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

	supervised = true
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
	return 0
}

// prepareConfiguration creates missing configs and updates existing ones in
// the order startup requires: the MySQL port of existing configs is adopted so
// new configs match it, configs exist, the realm is stopped, moved SQL paths
// are repaired, managed defaults are migrated and the authserver listener is
// read. Returns the addresses on which authserver accepts connections.
func prepareConfiguration(baseDir, workDir, mysqlExePath string, opts *startupOptions) ([]string, error) {
	applyConfiguredMySQLPort(workDir, opts)
	// Ensure config files (e.g. worldserver.conf, authserver.conf, modules/playerbots.conf, mysql/my.cnf) exist in workDir
	if err := ensureConfigFiles(baseDir, workDir, mysqlExePath, *opts); err != nil {
		return nil, fmt.Errorf("failed to ensure config files: %w", err)
	}
	if err := ensureRealmStopped(workDir); err != nil {
		return nil, err
	}
	pathBackups, err := relocatePortableSourcePaths(baseDir, workDir)
	if err != nil {
		return nil, fmt.Errorf("failed to update portable SQL paths: %w", err)
	}
	for _, backup := range pathBackups {
		fmt.Printf("SQL path updated; previous settings saved to %s\n", backup)
	}
	backups, err := migrateConfigProfiles(workDir)
	if err != nil {
		return nil, fmt.Errorf("failed to update configuration defaults: %w", err)
	}
	for _, backup := range backups {
		fmt.Printf("Configuration updated; previous settings saved to %s\n", backup)
	}
	authHosts, err := applyConfiguredAuthPort(workDir, opts)
	if err != nil {
		return nil, fmt.Errorf("failed to read server ports: %w", err)
	}
	return authHosts, nil
}
