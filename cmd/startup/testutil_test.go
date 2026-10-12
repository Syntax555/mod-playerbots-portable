package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

// TestHelperProcess is the short-lived child that helperProcessCmd starts.
func TestHelperProcess(t *testing.T) {
	if os.Getenv("GO_WANT_HELPER_PROCESS") != "1" {
		return
	}
	os.Exit(0)
}

// helperProcessCmd returns an unstarted command that exits successfully.
func helperProcessCmd() *exec.Cmd {
	cmd := exec.Command(os.Args[0], "-test.run=^TestHelperProcess$")
	cmd.Env = append(os.Environ(), "GO_WANT_HELPER_PROCESS=1")
	return cmd
}

// writeFixture writes content to path, creating missing parent directories.
func writeFixture(t *testing.T, path, content string) string {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}
	return path
}

func readFixture(t *testing.T, path string) string {
	t.Helper()
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return string(content)
}

// assertConfigValues checks effective settings in root/configs. Files are
// keyed by their slash-separated path relative to that directory.
func assertConfigValues(t *testing.T, root string, expected map[string]map[string]string) {
	t.Helper()
	for relative, values := range expected {
		content := readFixture(t, filepath.Join(root, "configs", filepath.FromSlash(relative)))
		for key, want := range values {
			if actual, exists := configValue(content, key); !exists || actual != want {
				t.Errorf("%s: %s = %q; want %q", relative, key, actual, want)
			}
		}
	}
}
