package main

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const relocationSQLProbe = "PORTABLE_RELOCATION_SQL_PROBE"

// The subprocess is launched through the production startServerProcess. It
// checks the generated config and SQL exports from the child's actual cwd,
// without starting a database or modifying character data.
func TestMain(m *testing.M) {
	if runMySQLAdminTestProbe() {
		return
	}
	if server := os.Getenv(relocationSQLProbe); server != "" {
		if err := probeRelocatedSQL(server); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(20)
		}
		os.Exit(0)
	}
	os.Exit(m.Run())
}

func probeRelocatedSQL(server string) error {
	if server != "authserver" && server != "worldserver" {
		return fmt.Errorf("unexpected SQL probe server %q", server)
	}
	content, err := os.ReadFile(filepath.Join("configs", server+".conf"))
	if err != nil {
		return err
	}
	value, exists := configValue(string(content), "SourceDirectory")
	if !exists || len(value) < 2 || value[0] != '"' || value[len(value)-1] != '"' {
		return fmt.Errorf("SQL source is not configured")
	}
	source, err := filepath.Abs(filepath.FromSlash(value[1 : len(value)-1]))
	if err != nil {
		return err
	}
	if source != filepath.Join(os.Getenv("PORTABLE_RELOCATION_ROOT"), "src") {
		return fmt.Errorf("SQL source resolved outside the relocated installation: %s", source)
	}
	databases := []string{"db_auth"}
	if server == "worldserver" {
		databases = append(databases, "db_world", "db_characters")
	}
	for _, database := range databases {
		for _, kind := range []string{"base", "updates"} {
			content, err := os.ReadFile(filepath.Join(source, "data", "sql", kind, database, "fixture.sql"))
			if err != nil || string(content) != "-- relocation SQL fixture\n" {
				return fmt.Errorf("cannot load %s %s SQL from configured source: %v", database, kind, err)
			}
		}
	}
	return nil
}

func relocationSQLFixture(t *testing.T, root string) {
	t.Helper()
	for _, database := range []string{"db_auth", "db_world", "db_characters"} {
		for _, kind := range []string{"base", "updates"} {
			writeFixture(t, filepath.Join(root, "src/data/sql/"+kind+"/"+database+"/fixture.sql"), "-- relocation SQL fixture\n")
		}
	}
}

func relocationConfigFixtures(t *testing.T, root string) {
	t.Helper()
	relocationSQLFixture(t, root)
	for _, server := range []string{"authserver", "worldserver"} {
		writeFixture(t, filepath.Join(root, "configs/"+server+".conf.dist"), "# Custom template\r\nSourceDirectory = \"\"\r\n"+
			"MySQLExecutable = \"\"\r\nDataDir = \".\"\r\nLogsDir = \"\"\r\nBindIP = \"0.0.0.0\"\r\n"+
			"LoginDatabaseInfo = \"db;3306;alice;fixture-password;acore_auth\"\r\nCustom.Option = 42\r\n")
	}
	writeFixture(t, filepath.Join(root, "mysql/data/characters.ibd"), "existing character fixture")
	writeFixture(t, filepath.Join(root, "data/maps/0004331.map"), "existing map fixture")
	if err := ensureConfigFiles(root, root, filepath.Join(root, "mysql", "bin", "mysql.exe"), defaultTestOptions()); err != nil {
		t.Fatal(err)
	}
}

func runRelocatedSQLProbes(t *testing.T, root string) {
	t.Helper()
	t.Setenv("PORTABLE_RELOCATION_ROOT", root)
	executable, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	for _, server := range []string{"authserver", "worldserver"} {
		t.Setenv(relocationSQLProbe, server)
		cmd, err := startServerProcess(server, executable, root, nil)
		if err != nil {
			t.Fatal(err)
		}
		if err := cmd.Wait(); err != nil {
			t.Fatalf("%s could not load relocated SQL: %v", server, err)
		}
	}
}

func TestNewServerConfigsRemainPortableAfterMoving(t *testing.T) {
	container := t.TempDir()
	root := filepath.Join(container, "Downloads", "portable server")
	relocationConfigFixtures(t, root)
	for _, server := range []string{"authserver", "worldserver"} {
		content := readFixture(t, filepath.Join(root, "configs", server+".conf"))
		if value, _ := configValue(content, "SourceDirectory"); value != `"src"` {
			t.Fatalf("new %s config contains a location-dependent SQL path: %s", server, value)
		}
	}
	relocated := filepath.Join(container, "relocated server")
	if err := os.Rename(root, relocated); err != nil {
		t.Fatal(err)
	}
	t.Chdir(t.TempDir())
	if backups, err := relocatePortableSourcePaths(relocated, relocated); err != nil || len(backups) != 0 {
		t.Fatalf("new relative paths required migration: %v, %v", backups, err)
	}
	runRelocatedSQLProbes(t, relocated)
}

func TestRelocatedLegacySQLPathsKeepSettingsAndCharacterData(t *testing.T) {
	container := t.TempDir()
	root := filepath.Join(container, "Downloads", "portable server")
	relocationConfigFixtures(t, root)
	originals := make(map[string]string)
	for _, server := range []string{"authserver", "worldserver"} {
		name := "configs/" + server + ".conf"
		content := readFixture(t, filepath.Join(root, filepath.FromSlash(name)))
		legacy, err := mergeConfigProfile(content, `SourceDirectory = "`+filepath.ToSlash(filepath.Join(root, "src"))+`"`)
		if err != nil {
			t.Fatal(err)
		}
		writeFixture(t, filepath.Join(root, name), legacy)
		originals[name] = legacy
	}
	// A still-existing custom source is not reclassified as a moved default.
	if backups, err := relocatePortableSourcePaths(root, root); err != nil || len(backups) != 0 {
		t.Fatalf("valid absolute SQL sources were changed: %v, %v", backups, err)
	}
	originals["mysql/my.cnf"] = readFixture(t, filepath.Join(root, "mysql", "my.cnf"))
	originals["mysql/data/characters.ibd"] = "existing character fixture"
	originals["data/maps/0004331.map"] = "existing map fixture"
	relocated := filepath.Join(container, "relocated server")
	if err := os.Rename(root, relocated); err != nil {
		t.Fatal(err)
	}
	t.Chdir(t.TempDir())
	backups, err := relocatePortableSourcePaths(relocated, relocated)
	if err != nil || len(backups) != 2 {
		t.Fatalf("legacy relocation did not back up both configs: %v, %v", backups, err)
	}
	for name, original := range originals {
		expected := original
		if strings.HasSuffix(name, ".conf") {
			expected, err = mergeConfigProfile(original, `SourceDirectory = "src"`)
			if err != nil {
				t.Fatal(err)
			}
			matches, err := filepath.Glob(filepath.Join(relocated, filepath.FromSlash(name)) + ".backup.*")
			if err != nil || len(matches) != 1 || readFixture(t, matches[0]) != original {
				t.Fatalf("%s original was not backed up exactly: %v, %v", name, matches, err)
			}
		}
		if actual := readFixture(t, filepath.Join(relocated, filepath.FromSlash(name))); actual != expected {
			t.Fatalf("unrelated settings or saved data changed at %s", name)
		}
	}
	runRelocatedSQLProbes(t, relocated)
	// Once repaired, a second move needs no additional path rewrite or backup.
	second := filepath.Join(container, "second move")
	if err := os.Rename(relocated, second); err != nil {
		t.Fatal(err)
	}
	if backups, err := relocatePortableSourcePaths(second, second); err != nil || len(backups) != 0 {
		t.Fatalf("repaired paths were not idempotent: %v, %v", backups, err)
	}
	runRelocatedSQLProbes(t, second)
}

func TestPrepareConfigurationUpdatesMovedLegacyRealmInOnePass(t *testing.T) {
	container := t.TempDir()
	root := filepath.Join(container, "Downloads", "portable server")
	relocationConfigFixtures(t, root)
	world := filepath.Join(root, "configs", "worldserver.conf")
	legacyWorld, err := mergeConfigProfile(readFixture(t, world), `SourceDirectory = "`+filepath.ToSlash(filepath.Join(root, "src"))+`"`)
	if err != nil {
		t.Fatal(err)
	}
	writeFixture(t, world, legacyWorld)
	// A module config from a release before its managed defaults existed.
	writeFixture(t, filepath.Join(root, "configs", "modules", "mod_era_events.conf"), "Custom.Module = 7\n")
	relocated := filepath.Join(container, "relocated server")
	if err := os.Rename(root, relocated); err != nil {
		t.Fatal(err)
	}
	t.Chdir(t.TempDir())

	opts := defaultTestOptions()
	if _, err := prepareConfiguration(relocated, relocated, filepath.Join(relocated, "mysql", "bin", "mysql.exe"), &opts); err != nil {
		t.Fatal(err)
	}
	world = filepath.Join(relocated, "configs", "worldserver.conf")
	if value, _ := configValue(readFixture(t, world), "SourceDirectory"); value != `"src"` {
		t.Errorf("moved SQL path was not repaired: %s", value)
	}
	if matches, err := filepath.Glob(world + ".backup.*"); err != nil || len(matches) != 1 || readFixture(t, matches[0]) != legacyWorld {
		t.Errorf("legacy worldserver.conf was not backed up: %v, %v", matches, err)
	}
	phase, err := loadRealmPhase(relocated)
	if err != nil {
		t.Fatal(err)
	}
	profiles, err := currentManagedProfiles(phase)
	if err != nil {
		t.Fatal(err)
	}
	expected, err := mergeManagedProfile("Custom.Module = 7\n", "", profiles["mod_era_events.conf"])
	if err != nil {
		t.Fatal(err)
	}
	module := filepath.Join(relocated, "configs", "modules", "mod_era_events.conf")
	if actual := readFixture(t, module); actual != expected || !strings.Contains(actual, "Custom.Module = 7\n") {
		t.Errorf("managed module defaults were not migrated: %q", actual)
	}
	if matches, err := filepath.Glob(module + ".backup.*"); err != nil || len(matches) != 1 || readFixture(t, matches[0]) != "Custom.Module = 7\n" {
		t.Errorf("module config was not backed up: %v, %v", matches, err)
	}
	if readFixture(t, filepath.Join(relocated, "mysql", "data", "characters.ibd")) != "existing character fixture" {
		t.Error("character data changed")
	}
	opts = defaultTestOptions()
	if _, err := prepareConfiguration(relocated, relocated, filepath.Join(relocated, "mysql", "bin", "mysql.exe"), &opts); err != nil {
		t.Fatal(err)
	}
	top, _ := filepath.Glob(filepath.Join(relocated, "configs", "*.backup.*"))
	modules, _ := filepath.Glob(filepath.Join(relocated, "configs", "modules", "*.backup.*"))
	if len(top) != 1 || len(modules) != 1 {
		t.Errorf("second start wrote more backups: %v %v", top, modules)
	}
}

func TestSQLPathRecoveryPreservesCustomAndAmbiguousValues(t *testing.T) {
	root := t.TempDir()
	relocationSQLFixture(t, root)
	custom := filepath.Join(t.TempDir(), "src")
	if err := os.Mkdir(custom, 0755); err != nil {
		t.Fatal(err)
	}
	missing := filepath.ToSlash(filepath.Join(t.TempDir(), "missing", "src"))
	for _, value := range []string{
		`"` + filepath.ToSlash(custom) + `"`, `"custom/path"`, `"src"`, `""`,
		`"` + strings.TrimSuffix(missing, "src") + `custom-sql"`,
		`"` + missing + `/"`, `"` + strings.ReplaceAll(missing, "/", "\\") + `"`,
		`"` + strings.TrimSuffix(missing, "src") + `unused/../src"`,
		`"` + missing + `" # custom comment`, missing,
	} {
		t.Run(value, func(t *testing.T) {
			original := "# user config\nSourceDirectory = " + value + "\nCustom = 42\n"
			path := writeFixture(t, filepath.Join(root, "configs/authserver.conf"), original)
			if backups, err := relocatePortableSourcePaths(root, root); err != nil || len(backups) != 0 {
				t.Fatalf("custom source migrated: %v, %v", backups, err)
			}
			if actual := readFixture(t, path); actual != original {
				t.Fatal("custom source configuration changed")
			}
		})
	}
	original := `SourceDirectory = "` + missing + `"` + "\nSourceDirectory = \"custom/path\"\n"
	path := writeFixture(t, filepath.Join(root, "configs/authserver.conf"), original)
	if backups, err := relocatePortableSourcePaths(root, root); err != nil || len(backups) != 0 || readFixture(t, path) != original {
		t.Fatalf("ambiguous duplicate source changed: %v, %v", backups, err)
	}
}

func TestSQLPathRecoveryRequiresCompleteBundledSQL(t *testing.T) {
	root := t.TempDir()
	relocationSQLFixture(t, root)
	if err := os.RemoveAll(filepath.Join(root, "src", "data", "sql", "updates", "db_characters")); err != nil {
		t.Fatal(err)
	}
	original := `SourceDirectory = "` + filepath.ToSlash(filepath.Join(t.TempDir(), "src")) + `"` + "\n"
	path := writeFixture(t, filepath.Join(root, "configs/authserver.conf"), original)
	if backups, err := relocatePortableSourcePaths(root, root); err != nil || len(backups) != 0 || readFixture(t, path) != original {
		t.Fatalf("incomplete bundled SQL was selected: %v, %v", backups, err)
	}
}

func TestSQLPathRecoveryValidatesAllTargetsBeforeWriting(t *testing.T) {
	root := t.TempDir()
	relocationSQLFixture(t, root)
	original := `SourceDirectory = "` + filepath.ToSlash(filepath.Join(t.TempDir(), "src")) + `"` + "\n"
	auth := writeFixture(t, filepath.Join(root, "configs/authserver.conf"), original)
	external := writeFixture(t, filepath.Join(t.TempDir(), "worldserver.conf"), original)
	if err := os.Symlink(external, filepath.Join(root, "configs", "worldserver.conf")); err != nil {
		t.Skipf("symlinks unavailable: %v", err)
	}
	if _, err := relocatePortableSourcePaths(root, root); err == nil {
		t.Fatal("SQL recovery followed a configuration symlink")
	}
	for _, path := range []string{auth, external} {
		actual, err := os.ReadFile(path)
		if err != nil || !bytes.Equal(actual, []byte(original)) {
			t.Fatalf("configuration changed before all targets were validated: %s, %v", path, err)
		}
	}
	if backups, err := filepath.Glob(auth + ".backup.*"); err != nil || len(backups) != 0 {
		t.Fatalf("invalid target triggered a partial migration: %v, %v", backups, err)
	}
}

func TestPortableSQLSourceWithSeparateWorkDirectory(t *testing.T) {
	base := t.TempDir()
	work := t.TempDir()
	relocationSQLFixture(t, base)
	source := portableSourceDirectory(base, work)
	if filepath.IsAbs(filepath.FromSlash(source)) {
		t.Fatalf("same-volume separate work directory received an absolute source: %s", source)
	}
	if filepath.Clean(filepath.Join(work, filepath.FromSlash(source))) != filepath.Join(base, "src") {
		t.Fatalf("SQL source does not resolve from server work directory: %s", source)
	}
	if actual := portableSourceDirectory(t.TempDir(), work); actual != "src" {
		t.Fatalf("missing bundled source changed fallback: %s", actual)
	}
}
