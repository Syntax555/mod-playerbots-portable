package main

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

func BenchmarkIsClientDataPresent(b *testing.B) {
	dataDir := b.TempDir()
	for _, folder := range []string{"dbc", "maps", "vmaps", "mmaps"} {
		directory := filepath.Join(dataDir, folder)
		if err := os.Mkdir(directory, 0755); err != nil {
			b.Fatal(err)
		}
		for i := 0; i < 4096; i++ {
			if err := os.WriteFile(filepath.Join(directory, fmt.Sprintf("%05d.dat", i)), nil, 0644); err != nil {
				b.Fatal(err)
			}
		}
	}
	b.ResetTimer()
	for b.Loop() {
		if !isClientDataPresent(dataDir) {
			b.Fatal("client data was not found")
		}
	}
}
