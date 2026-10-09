//go:build !windows

package main

import "testing"

func runProcessTestInPrivateConsole(t *testing.T) bool { return false }
