package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestEnsureClientDataChecksArchiveRelease(t *testing.T) {
	for _, test := range []struct {
		name, marker  string
		marked, valid bool
	}{
		{name: "unmarked", valid: true},
		{name: "current", marker: "INSTALLED_VERSION=" + clientDataRelease + "\n", marked: true, valid: true},
		{name: "older", marker: "INSTALLED_VERSION=v16\n", marked: true},
		{name: "newer", marker: "INSTALLED_VERSION=v999\n", marked: true},
		{name: "malformed", marker: "unknown\n", marked: true},
		{name: "empty", marked: true},
	} {
		t.Run(test.name, func(t *testing.T) {
			files := map[string]string{
				"Data/dbc/test.dat": "new", "Data/maps/test.dat": "new",
				"Data/vmaps/test.dat": "new", "Data/mmaps/test.dat": "new",
			}
			if test.marked {
				files["Data/"+clientDataReleaseFile] = test.marker
			}
			archivePath := filepath.Join(t.TempDir(), "Data.zip")
			createTestZip(t, archivePath, files)
			archive, err := os.ReadFile(archivePath)
			if err != nil {
				t.Fatal(err)
			}
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				_, _ = w.Write(archive)
			}))
			defer server.Close()
			workDir := t.TempDir()
			dataDir := filepath.Join(workDir, "data")
			previous := filepath.Join(dataDir, "custom.dat")
			writeFixture(t, previous, "keep existing data")
			err = ensureClientData(context.Background(), workDir, workDir, server.URL, false)
			if test.valid {
				if err != nil {
					t.Fatal(err)
				}
				if !isClientDataPresent(dataDir) || installedClientDataRelease(dataDir) != clientDataRelease {
					t.Fatal("compatible archive was not activated with its release marker")
				}
				return
			}
			if err == nil || !strings.Contains(err.Error(), "archive declares release") {
				t.Fatalf("incompatible archive was not rejected: %v", err)
			}
			if readFixture(t, previous) != "keep existing data" || isClientDataPresent(dataDir) {
				t.Error("incompatible archive changed the active data directory")
			}
			cached, err := filepath.Glob(filepath.Join(workDir, ".client-data-*"))
			if err != nil || len(cached) != 0 {
				t.Errorf("incompatible archive or stage was kept: %v, %v", cached, err)
			}
		})
	}
}
