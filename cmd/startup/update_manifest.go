package main

import (
	"archive/zip"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"path"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"
)

const portableUpdateManifestURL = "https://github.com/Syntax555/mod-playerbots-portable/releases/download/latest/UPDATE_MANIFEST.json"
const portableUpdatePackage = "mod-playerbots-portable-latest.zip"
const maxUpdateManifestBytes = 8 << 20
const maxUpdateFileBytes = 1 << 30
const maxUpdatePackageBytes = 4 << 30

var updateRevisionPattern = regexp.MustCompile(`^[0-9a-f]{40}$`)
var updateDigestPattern = regexp.MustCompile(`^[0-9a-f]{64}$`)

type portableUpdateFile struct {
	Path   string `json:"path"`
	Size   int64  `json:"size"`
	SHA256 string `json:"sha256"`
}

type portableUpdateManifest struct {
	Schema     int                  `json:"schema"`
	Revision   string               `json:"revision"`
	Package    string               `json:"package"`
	SHA256     string               `json:"sha256"`
	Size       int64                `json:"size"`
	Generation string               `json:"generation,omitempty"`
	Files      []portableUpdateFile `json:"files"`
}

type portableReleaseIdentity struct {
	Schema   int    `json:"schema"`
	Revision string `json:"revision"`
	Package  string `json:"package"`
	Version  string `json:"version"`
}

func protectedUpdatePath(name string) bool {
	lower := strings.ToLower(name)
	base := path.Base(lower)
	if strings.HasSuffix(lower, ".conf") || base == "my.ini" || base == "my.cnf" {
		return true
	}
	for _, prefix := range []string{"mysql/data", "data", "logs", ".portable-update", "configs/.portable-profiles.json", "configs/realm-phase.txt"} {
		if lower == prefix || strings.HasPrefix(lower, prefix+"/") {
			return true
		}
	}
	return strings.Contains(lower, ".backup.") || strings.HasSuffix(lower, ".pid")
}

func validateUpdatePath(name string) error {
	if name == "" || len(name) > 1024 || strings.ContainsAny(name, "\\:<>\"|?*") || path.Clean(name) != name || strings.HasPrefix(name, "/") {
		return fmt.Errorf("invalid update path %q", name)
	}
	for _, character := range name {
		if character < 32 {
			return fmt.Errorf("control character in update path %q", name)
		}
	}
	for _, part := range strings.Split(name, "/") {
		if part == "" || part == "." || part == ".." || strings.HasSuffix(part, ".") || strings.HasSuffix(part, " ") {
			return fmt.Errorf("invalid update path %q", name)
		}
		base := strings.ToUpper(strings.SplitN(part, ".", 2)[0])
		if base == "CON" || base == "PRN" || base == "AUX" || base == "NUL" || (len(base) == 4 && (strings.HasPrefix(base, "COM") || strings.HasPrefix(base, "LPT")) && base[3] >= '0' && base[3] <= '9') {
			return fmt.Errorf("reserved Windows name in update path %q", name)
		}
	}
	if protectedUpdatePath(name) {
		return fmt.Errorf("update attempts to replace user data: %s", name)
	}
	return nil
}

func validateUpdateManifest(m portableUpdateManifest) error {
	if m.Schema != 1 || !updateRevisionPattern.MatchString(m.Revision) || m.Package != portableUpdatePackage || !updateDigestPattern.MatchString(m.SHA256) || m.Size <= 0 || m.Size > maxUpdatePackageBytes {
		return errors.New("unsupported or invalid update manifest")
	}
	if len(m.Files) == 0 || len(m.Files) > 100000 {
		return errors.New("invalid update file count")
	}
	seen := make(map[string]bool, len(m.Files))
	var total int64
	for _, f := range m.Files {
		if err := validateUpdatePath(f.Path); err != nil {
			return err
		}
		key := strings.ToLower(f.Path)
		if seen[key] || f.Size < 0 || f.Size > maxUpdateFileBytes || !updateDigestPattern.MatchString(f.SHA256) {
			return fmt.Errorf("invalid or duplicate update file: %s", f.Path)
		}
		for ancestor := path.Dir(key); ancestor != "."; ancestor = path.Dir(ancestor) {
			if seen[ancestor] {
				return fmt.Errorf("update file conflicts with directory: %s", f.Path)
			}
		}
		seen[key] = true
		total += f.Size
		if total > 8<<30 {
			return errors.New("update exceeds installed-size limit")
		}
	}
	for name := range seen {
		for ancestor := path.Dir(name); ancestor != "."; ancestor = path.Dir(ancestor) {
			if seen[ancestor] {
				return fmt.Errorf("update file conflicts with directory: %s", name)
			}
		}
	}
	if !seen["startup.exe"] || !seen["portable-release.json"] {
		return errors.New("update is missing launcher or release identity")
	}
	return nil
}

func trustedUpdateURL(u *url.URL) bool {
	if u == nil || u.Scheme != "https" || u.User != nil || (u.Port() != "" && u.Port() != "443") {
		return false
	}
	switch strings.ToLower(u.Hostname()) {
	case "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com", "github-releases.githubusercontent.com":
		return true
	}
	return false
}

func portableUpdateHTTPClient() *http.Client {
	return &http.Client{
		Timeout: 45 * time.Second,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			if len(via) >= 5 || !trustedUpdateURL(req.URL) {
				return errors.New("update redirect is not a trusted HTTPS GitHub asset")
			}
			return nil
		},
	}
}

func fetchUpdateManifest(ctx context.Context, client *http.Client, manifestURL string) (portableUpdateManifest, error) {
	var manifest portableUpdateManifest
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, manifestURL, nil)
	if err != nil {
		return manifest, err
	}
	resp, err := client.Do(req)
	if err != nil {
		return manifest, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return manifest, fmt.Errorf("update manifest returned HTTP %d", resp.StatusCode)
	}
	content, err := io.ReadAll(io.LimitReader(resp.Body, maxUpdateManifestBytes+1))
	if err != nil {
		return manifest, err
	}
	if len(content) > maxUpdateManifestBytes {
		return manifest, errors.New("update manifest is too large")
	}
	if err := json.Unmarshal(content, &manifest); err != nil {
		return manifest, fmt.Errorf("decode update manifest: %w", err)
	}
	return manifest, validateUpdateManifest(manifest)
}

// updateRangeReader never falls back to downloading the entire archive. The first
// byte request resolves GitHub's rolling URL to one immutable asset URL.
type updateRangeReader struct {
	ctx       context.Context
	client    *http.Client
	assetURL  string
	size      int64
	etag      string
	mu        sync.Mutex
	cacheOff  int64
	cacheData []byte
}

func newUpdateRangeReader(ctx context.Context, client *http.Client, assetURL string, size int64) (*updateRangeReader, error) {
	r := &updateRangeReader{ctx: ctx, client: client, assetURL: assetURL, size: size, cacheOff: -1}
	content, finalURL, etag, err := r.request(0, 1)
	if err != nil {
		return nil, err
	}
	r.assetURL = finalURL
	r.etag = etag
	r.cacheOff = 0
	r.cacheData = content
	return r, nil
}

func (r *updateRangeReader) request(offset, length int64) ([]byte, string, string, error) {
	req, err := http.NewRequestWithContext(r.ctx, http.MethodGet, r.assetURL, nil)
	if err != nil {
		return nil, "", "", err
	}
	req.Header.Set("Range", fmt.Sprintf("bytes=%d-%d", offset, offset+length-1))
	req.Header.Set("Accept-Encoding", "identity")
	if r.etag != "" {
		req.Header.Set("If-Match", r.etag)
	}
	resp, err := r.client.Do(req)
	if err != nil {
		return nil, "", "", err
	}
	defer resp.Body.Close()
	wantRange := fmt.Sprintf("bytes %d-%d/%d", offset, offset+length-1, r.size)
	if resp.StatusCode != http.StatusPartialContent || resp.Header.Get("Content-Range") != wantRange || resp.Header.Get("Content-Encoding") != "" || (resp.ContentLength >= 0 && resp.ContentLength != length) {
		return nil, "", "", errors.New("release host did not provide the requested ZIP range; keeping the installed version")
	}
	finalURL := resp.Request.URL.String()
	etag := resp.Header.Get("ETag")
	if r.cacheOff >= 0 && (finalURL != r.assetURL || (r.etag != "" && etag != r.etag)) {
		return nil, "", "", errors.New("release asset changed during update")
	}
	content, err := io.ReadAll(io.LimitReader(resp.Body, length+1))
	if err != nil || int64(len(content)) != length {
		if err == nil {
			err = io.ErrUnexpectedEOF
		}
		return nil, "", "", err
	}
	return content, finalURL, etag, nil
}

func (r *updateRangeReader) ReadAt(p []byte, off int64) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if len(p) == 0 {
		return 0, nil
	}
	if off < 0 || off >= r.size {
		return 0, io.EOF
	}
	want := len(p)
	if int64(want) > r.size-off {
		want = int(r.size - off)
	}
	n := 0
	for n < want {
		pos := off + int64(n)
		if pos < r.cacheOff || pos >= r.cacheOff+int64(len(r.cacheData)) {
			length := int64(256 << 10)
			if length > r.size-pos {
				length = r.size - pos
			}
			data, _, _, err := r.request(pos, length)
			if err != nil {
				return n, err
			}
			r.cacheOff, r.cacheData = pos, data
		}
		n += copy(p[n:want], r.cacheData[pos-r.cacheOff:])
	}
	if n != len(p) {
		return n, io.EOF
	}
	return n, nil
}

func indexedUpdateZip(reader io.ReaderAt, manifest portableUpdateManifest) (map[string]*zip.File, error) {
	zr, err := zip.NewReader(reader, manifest.Size)
	if err != nil {
		return nil, fmt.Errorf("read release ZIP directory: %w", err)
	}
	index := make(map[string]*zip.File, len(zr.File))
	for _, file := range zr.File {
		if file.FileInfo().IsDir() {
			continue
		}
		name := strings.TrimPrefix(file.Name, "./")
		if err := validateUpdatePath(name); err != nil {
			return nil, err
		}
		if !file.Mode().IsRegular() || file.Flags&1 != 0 {
			return nil, fmt.Errorf("unsupported ZIP entry: %s", file.Name)
		}
		if _, exists := index[strings.ToLower(name)]; exists {
			return nil, fmt.Errorf("duplicate ZIP entry: %s", file.Name)
		}
		index[strings.ToLower(name)] = file
	}
	if len(index) != len(manifest.Files) {
		return nil, errors.New("ZIP file list does not match the update manifest")
	}
	for _, file := range manifest.Files {
		z, exists := index[strings.ToLower(file.Path)]
		if !exists || strings.TrimPrefix(z.Name, "./") != file.Path || z.UncompressedSize64 != uint64(file.Size) || z.CompressedSize64 > uint64(manifest.Size) {
			return nil, fmt.Errorf("ZIP metadata differs from update manifest: %s", file.Path)
		}
	}
	return index, nil
}

func parseUpdateParentPID(text string) (int, error) {
	pid, err := strconv.Atoi(text)
	if err != nil || pid <= 0 {
		return 0, errors.New("invalid updater parent process")
	}
	return pid, nil
}
