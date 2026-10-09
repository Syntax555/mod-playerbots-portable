package main

import (
	"context"
	"fmt"
	"os"
	"sync"
	"time"
)

func shutdownRealmProcesses(auth, world, database *ProcessSupervisor, cancel context.CancelFunc, shutdownDatabase func() error) {
	fmt.Println("\nShutting down authserver and worldserver first...")
	auth.MarkStopped()
	world.MarkStopped()
	var gameServers sync.WaitGroup
	for _, supervisor := range []*ProcessSupervisor{auth, world} {
		gameServers.Add(1)
		go func(ps *ProcessSupervisor) {
			defer gameServers.Done()
			ps.StopAndWait(60 * time.Second)
		}(supervisor)
	}
	gameServers.Wait()
	fmt.Println("Authserver and worldserver stopped.")

	// Keep MySQL available until both game servers finish saving their state.
	fmt.Println("Shutting down MySQL server...")
	database.MarkStopped()
	cancel()
	if database.IsRunning() {
		if err := shutdownDatabase(); err != nil {
			fmt.Fprintf(os.Stderr, "Warning: %v\n", err)
		}
	}
	select {
	case <-database.doneChan:
		fmt.Println("MySQL server stopped.")
	case <-time.After(30 * time.Second):
		fmt.Println("MySQL did not stop within 30s, terminating process...")
		database.Kill()
		<-database.doneChan
	}
	fmt.Println("All servers stopped.")
}
