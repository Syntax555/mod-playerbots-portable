package main

import (
	"context"
	"fmt"
	"path/filepath"
	"strings"
	"testing"
)

func TestEnsureConfigFilesUsesCompleteClientData(t *testing.T) {
	for _, test := range []struct {
		name, baseFile string
		complete       bool
	}{
		{name: "absent"},
		{name: "partial", baseFile: "dbc/test.dat"},
		{name: "marker only", baseFile: clientDataReleaseFile},
		{name: "complete", complete: true},
	} {
		t.Run(test.name, func(t *testing.T) {
			base, work := t.TempDir(), t.TempDir()
			writeFixture(t, filepath.Join(base, "configs/worldserver.conf.dist"), "DataDir = \".\"\n")
			for _, required := range []string{"dbc", "maps", "vmaps", "mmaps"} {
				writeFixture(t, filepath.Join(work, "data", required, "test.dat"), "data")
				if test.complete {
					writeFixture(t, filepath.Join(base, "data", required, "test.dat"), "data")
				}
			}
			if test.baseFile != "" {
				writeFixture(t, filepath.Join(base, "data", test.baseFile), "INSTALLED_VERSION="+clientDataRelease+"\n")
			}
			if err := ensureConfigFiles(base, work, "", defaultTestOptions()); err != nil {
				t.Fatal(err)
			}
			if err := ensureClientData(context.Background(), work, base, "", false); err != nil {
				t.Fatal(err)
			}
			content := readFixture(t, filepath.Join(work, "configs/worldserver.conf"))
			value, _ := configValue(content, "DataDir")
			path := filepath.FromSlash(strings.Trim(value, `"`))
			if !filepath.IsAbs(path) {
				path = filepath.Join(work, path)
			}
			expected := filepath.Join(work, "data")
			if test.complete {
				expected = filepath.Join(base, "data")
			}
			if path != expected || !isClientDataPresent(path) {
				t.Fatalf("worldserver data path = %q; want complete data at %q", path, expected)
			}
		})
	}
}

func TestEnsureConfigFilesSeedsActiveDefaults(t *testing.T) {
	for name, ending := range map[string]string{"LF": "\n", "CRLF": "\r\n"} {
		t.Run(name, func(t *testing.T) {
			root := t.TempDir()
			original := strings.Join([]string{
				"[authserver]",
				"# DataDir = \".\"",
				"# LogsDir = \"\"",
				"# SourceDirectory = \"\"",
				"# MySQLExecutable = \"\"",
				"# BindIP = \"0.0.0.0\"",
				"DataDir\t=\t\".\"",
				"LogsDir=\"\"",
				"SourceDirectory = \"\"",
				"MySQLExecutable=\"\"",
				"BindIP = \"0.0.0.0\"",
				"",
			}, ending)
			writeFixture(t, filepath.Join(root, "configs/authserver.conf.dist"), original)
			mysql := filepath.Join(root, "mysql/bin/mysql.exe")
			if err := ensureConfigFiles(root, root, mysql, defaultTestOptions()); err != nil {
				t.Fatal(err)
			}
			assertConfigValues(t, root, map[string]map[string]string{"authserver.conf": {
				"DataDir":         `"data"`,
				"LogsDir":         `"logs"`,
				"SourceDirectory": `"src"`,
				"MySQLExecutable": `"mysql/bin/mysql.exe"`,
				"BindIP":          `"127.0.0.1"`,
			}})
			updated := readFixture(t, filepath.Join(root, "configs/authserver.conf"))
			for line := range strings.SplitSeq(original, ending) {
				if strings.HasPrefix(line, "#") && !strings.Contains(updated, line+ending) {
					t.Errorf("comment changed: %s", line)
				}
			}
			if ending == "\r\n" && strings.Contains(strings.ReplaceAll(updated, ending, ""), "\n") {
				t.Fatal("config seeding changed Windows line endings")
			}
		})
	}
}

func BenchmarkMergeManagedProfile(b *testing.B) {
	var template, profile strings.Builder
	for i := 0; i < 2000; i++ {
		fmt.Fprintf(&template, "Template.%d = 0\n", i)
	}
	for i := 0; i < 200; i++ {
		fmt.Fprintf(&profile, "Managed.%d = 1\n", i)
	}
	content := template.String() + profile.String()
	baseline := profile.String()
	b.ResetTimer()
	for b.Loop() {
		if _, err := mergeManagedProfile(content, baseline, baseline); err != nil {
			b.Fatal(err)
		}
	}
}

func TestEnsureConfigFilesPreservesCustomTemplateSettings(t *testing.T) {
	root := t.TempDir()
	content := "DataDir = \"custom-data\"\nDataDir = \".\"\nLogsDir = \"custom-logs\"\n" +
		"SourceDirectory = \"custom-src\"\nMySQLExecutable = \"custom-mysql\"\nBindIP = \"192.168.1.10\"\n"
	writeFixture(t, filepath.Join(root, "configs/authserver.conf.dist"), content)
	if err := ensureConfigFiles(root, root, filepath.Join(root, "mysql/bin/mysql.exe"), defaultTestOptions()); err != nil {
		t.Fatal(err)
	}
	updated := readFixture(t, filepath.Join(root, "configs/authserver.conf"))
	if !strings.HasPrefix(updated, content) {
		t.Fatalf("custom template settings changed: %q", updated)
	}
}

func TestApplyRuntimePortsUsesFirstDatabaseAssignment(t *testing.T) {
	for _, ignored := range []string{`"ignored;3306;bob;other;wrong"`, "not-a-connection"} {
		t.Run(ignored, func(t *testing.T) {
			content := "LoginDatabaseInfo = \"localhost;3306;alice;password;auth\"\nLoginDatabaseInfo = " + ignored + "\n"
			updated, err := applyRuntimePorts("authserver.conf.dist", content, startupOptions{port: 3307, authPort: 3725})
			if err != nil {
				t.Fatal(err)
			}
			if value, _ := configValue(updated, "LoginDatabaseInfo"); value != `"localhost;3307;alice;password;auth"` {
				t.Fatalf("effective database connection = %q", value)
			}
		})
	}
}
