//go:build !windows

package main

import "os"

func portableUpdateConsole(file *os.File) bool {
	info, err := file.Stat()
	return err == nil && info.Mode()&os.ModeCharDevice != 0
}
