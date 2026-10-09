//go:build windows

package main

import (
	"os"
	"syscall"
	"unsafe"
)

func portableUpdateConsole(file *os.File) bool {
	var mode uint32
	result, _, _ := syscall.NewLazyDLL("kernel32.dll").NewProc("GetConsoleMode").Call(file.Fd(), uintptr(unsafe.Pointer(&mode)))
	return result != 0
}
