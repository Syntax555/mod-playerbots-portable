//go:build !windows

package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// The portable launcher supports Windows. Linux uses actual socket ownership
// for subprocess tests rather than substituting a guessed PID or open port.
func ownsMySQLListener(port int, process *os.Process) (bool, error) {
	if process == nil || process.Pid <= 0 || port <= 0 || port > 65535 {
		return false, nil
	}
	fdDir := fmt.Sprintf("/proc/%d/fd", process.Pid)
	entries, err := os.ReadDir(fdDir)
	if err != nil {
		return false, err
	}
	inodes := make(map[string]bool)
	for _, entry := range entries {
		target, err := os.Readlink(filepath.Join(fdDir, entry.Name()))
		if err == nil && strings.HasPrefix(target, "socket:[") && strings.HasSuffix(target, "]") {
			inodes[strings.TrimSuffix(strings.TrimPrefix(target, "socket:["), "]")] = true
		}
	}
	content, err := os.ReadFile("/proc/net/tcp")
	if err != nil {
		return false, err
	}
	address := fmt.Sprintf("0100007F:%04X", port)
	for _, line := range strings.Split(string(content), "\n") {
		fields := strings.Fields(line)
		if len(fields) >= 10 && fields[1] == address && fields[3] == "0A" && inodes[fields[9]] {
			return true, nil
		}
	}
	return false, nil
}
