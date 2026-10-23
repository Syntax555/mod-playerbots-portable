package main

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestRelativeMySQLDirectoryWithSeparateWorkDirectory(t *testing.T) {
	root := t.TempDir()
	t.Chdir(root)
	baseDir := filepath.Join(root, "server")
	workDir := filepath.Join(root, "realm")
	writeFixture(t, filepath.Join(baseDir, "configs", "authserver.conf.dist"), "MySQLExecutable = \"\"\n")
	for _, name := range []string{"mysqld", "mysql", "mysqladmin"} {
		writeFixture(t, filepath.Join(root, "mysql-install", "bin", name+".exe"), "executable")
	}
	binaries, err := findMySQLBinaries("mysql-install")
	if err != nil {
		t.Fatal(err)
	}
	if err := ensureConfigFiles(baseDir, workDir, binaries.mysql, defaultTestOptions()); err != nil {
		t.Fatal(err)
	}
	value, exists := configValue(readFixture(t, filepath.Join(workDir, "configs", "authserver.conf")), "MySQLExecutable")
	if !exists {
		t.Fatal("generated config has no MySQL executable")
	}
	configured := filepath.FromSlash(strings.Trim(value, `"`))
	if !filepath.IsAbs(configured) {
		configured = filepath.Join(workDir, configured)
	}
	want := filepath.Join(root, "mysql-install", "bin", "mysql.exe")
	if configured != want {
		t.Fatalf("server resolves MySQL executable to %s; want %s", configured, want)
	}
}
