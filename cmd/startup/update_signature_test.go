package main

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

// Test releases are signed with a key the launcher trusts only in this package's tests.
var updateTestSigningKey ed25519.PrivateKey

func init() {
	public, private, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		panic(err)
	}
	updateTestSigningKey = private
	updateSigningKeys = []ed25519.PublicKey{public}
}

func updateTestSignature(key ed25519.PrivateKey, content []byte) []byte {
	return []byte(base64.StdEncoding.EncodeToString(ed25519.Sign(key, content)) + "\n")
}

func TestPortableUpdateEmbeddedSigningKeysAreEd25519(t *testing.T) {
	content, err := os.ReadFile("update-signing-key.pem")
	if err != nil {
		t.Fatal(err)
	}
	if keys := parseUpdateSigningKeys(content); len(keys) == 0 {
		t.Fatal("the release has no trusted update signing key")
	}
	for _, invalid := range []string{"", "not a key", "-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n"} {
		func() {
			defer func() {
				if recover() == nil {
					t.Fatalf("invalid embedded key accepted: %q", invalid)
				}
			}()
			parseUpdateSigningKeys([]byte(invalid))
		}()
	}
}

func TestPortableUpdateRequiresTrustedManifestSignature(t *testing.T) {
	_, manifest := updateTestArchive(t, updateTestFiles(), "")
	content, err := json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}
	_, foreign, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	tampered := append([]byte{}, content...)
	tampered[len(tampered)-2] = ' '
	cases := map[string]struct {
		manifest, signature []byte
		missing             bool
		failure             string
	}{
		"signed":         {manifest: content, signature: updateTestSignature(updateTestSigningKey, content)},
		"unsigned":       {manifest: content, missing: true, failure: "update manifest signature returned HTTP 404"},
		"foreign key":    {manifest: content, signature: updateTestSignature(foreign, content), failure: "trusted release key"},
		"tampered":       {manifest: tampered, signature: updateTestSignature(updateTestSigningKey, content), failure: "trusted release key"},
		"malformed":      {manifest: content, signature: []byte("not base64!"), failure: "malformed"},
		"short":          {manifest: content, signature: []byte(base64.StdEncoding.EncodeToString([]byte("short"))), failure: "malformed"},
		"oversized":      {manifest: content, signature: []byte(strings.Repeat("A", maxUpdateSignatureBytes+1)), failure: "too large"},
		"other manifest": {manifest: content, signature: updateTestSignature(updateTestSigningKey, []byte("{}")), failure: "trusted release key"},
	}
	for name, test := range cases {
		t.Run(name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				switch {
				case r.URL.Path == "/UPDATE_MANIFEST.json":
					w.Write(test.manifest)
				case r.URL.Path == "/UPDATE_MANIFEST.json.sig" && !test.missing:
					w.Write(test.signature)
				default:
					http.NotFound(w, r)
				}
			}))
			defer server.Close()
			got, err := fetchUpdateManifest(context.Background(), server.Client(), server.URL+"/UPDATE_MANIFEST.json", time.Second)
			if test.failure == "" {
				if err != nil || got.Revision != manifest.Revision {
					t.Fatalf("signed manifest was refused: %v", err)
				}
				return
			}
			if err == nil || !strings.Contains(err.Error(), test.failure) {
				t.Fatalf("expected %q, got %v", test.failure, err)
			}
			if got.Revision != "" {
				t.Fatal("an unverified manifest was decoded")
			}
		})
	}
}
