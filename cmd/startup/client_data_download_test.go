package main

import (
	"bytes"
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestClientDataDownloadKeepsShortRangeForNextResume(t *testing.T) {
	content := []byte("0123456789")
	requests := make(chan string, 2)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests <- r.Header.Get("Range")
		if r.Header.Get("Range") == "bytes=3-" {
			w.Header().Set("Content-Range", "bytes 3-5/10")
			w.WriteHeader(http.StatusPartialContent)
			_, _ = w.Write(content[3:6])
			return
		}
		http.ServeContent(w, r, "Data.zip", time.Time{}, bytes.NewReader(content))
	}))
	defer server.Close()
	destination := filepath.Join(t.TempDir(), "Data.zip")
	writeFixture(t, destination+".download", "012")
	if err := downloadFileWithProgress(context.Background(), server.URL, destination); err == nil || !strings.Contains(err.Error(), "incomplete") {
		t.Fatalf("short byte range was finalized as a complete download: %v", err)
	}
	if fileExists(destination) || readFixture(t, destination+".download") != "012345" {
		t.Fatal("short byte range was not retained as resumable progress")
	}
	if err := downloadFileWithProgress(context.Background(), server.URL, destination); err != nil {
		t.Fatal(err)
	}
	if readFixture(t, destination) != string(content) || fileExists(destination+".download") {
		t.Fatal("the next request did not complete the retained byte range")
	}
	if first, second := <-requests, <-requests; first != "bytes=3-" || second != "bytes=6-" {
		t.Fatalf("resume requests = %q, %q", first, second)
	}
}

func TestClientDataDownloadRejectsInvalidRangeBeforeAppending(t *testing.T) {
	for _, test := range []struct {
		name, header, body string
	}{
		{name: "missing", body: "3456789"},
		{name: "wrong start", header: "bytes 4-9/10", body: "456789"},
		{name: "reversed", header: "bytes 3-2/10", body: "3456789"},
		{name: "outside total", header: "bytes 3-10/10", body: "34567890"},
		{name: "unknown total", header: "bytes 3-9/*", body: "3456789"},
		{name: "trailing data", header: "bytes 3-9/10 invalid", body: "3456789"},
		{name: "body length mismatch", header: "bytes 3-9/10", body: "34"},
	} {
		t.Run(test.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Range", test.header)
				w.Header().Set("Content-Length", fmt.Sprint(len(test.body)))
				w.WriteHeader(http.StatusPartialContent)
				_, _ = w.Write([]byte(test.body))
			}))
			defer server.Close()
			destination := filepath.Join(t.TempDir(), "Data.zip")
			writeFixture(t, destination+".download", "012")
			if err := downloadFileWithProgress(context.Background(), server.URL, destination); err == nil {
				t.Fatal("invalid byte range was accepted")
			}
			if fileExists(destination) || readFixture(t, destination+".download") != "012" {
				t.Fatal("invalid byte range changed the retained download")
			}
		})
	}
}

func TestClientDataDownloadChecksChunkedRangeLength(t *testing.T) {
	for _, test := range []struct {
		name, header, body, retained string
	}{
		{name: "short", header: "bytes 3-9/10", body: "345", retained: "012345"},
		{name: "long", header: "bytes 3-5/10", body: "3456", retained: "012"},
	} {
		t.Run(test.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Range", test.header)
				w.WriteHeader(http.StatusPartialContent)
				w.(http.Flusher).Flush()
				_, _ = w.Write([]byte(test.body))
			}))
			defer server.Close()
			destination := filepath.Join(t.TempDir(), "Data.zip")
			writeFixture(t, destination+".download", "012")
			if err := downloadFileWithProgress(context.Background(), server.URL, destination); err == nil {
				t.Fatal("chunked response with a wrong byte count was finalized")
			}
			if fileExists(destination) || readFixture(t, destination+".download") != test.retained {
				t.Fatal("chunked response left incorrect resumable progress")
			}
		})
	}
}
