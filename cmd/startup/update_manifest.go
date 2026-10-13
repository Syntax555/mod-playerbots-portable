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

// Offline and filtered networks fail at the response deadline; a slow link
// may then use the remaining check time to transfer the manifest itself.
const updateManifestResponseTimeout = 8 * time.Second

// Sequential ZIP reads double the requested range while each request finishes
// within a second. Random access and slow links keep the smallest range.
const minUpdateRangeBytes = 256 << 10
const maxUpdateRangeBytes = 8 << 20
const updateRangeAttempts = 3
const updateRangeRetryDelay = 500 * time.Millisecond

var errUntrustedUpdateRedirect = errors.New("update redirect is not a trusted HTTPS GitHub asset")

var updateRevisionPattern = regexp.MustCompile(`^[0-9a-f]{40}$`)
var updateDigestPattern = regexp.MustCompile(`^[0-9a-f]{64}$`)

type portableUpdateFile struct {
	Path   string `json:"path"`
	Size   int64  `json:"size"`
	SHA256 string `json:"sha256"`
}

type portableUpdateManifest struct {
	Schema   int                  `json:"schema"`
	Revision string               `json:"revision"`
	Package  string               `json:"package"`
	SHA256   string               `json:"sha256"`
	Size     int64                `json:"size"`
	Files    []portableUpdateFile `json:"files"`
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
		seen[key] = true
		total += f.Size
		if total > 8<<30 {
			return errors.New("update exceeds installed-size limit")
		}
	}
	// A file path may not also be a directory of another file, in either order.
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
				return errUntrustedUpdateRedirect
			}
			return nil
		},
	}
}

func fetchUpdateManifest(ctx context.Context, client *http.Client, manifestURL string, responseTimeout time.Duration) (portableUpdateManifest, error) {
	var manifest portableUpdateManifest
	responseCtx, cancel := context.WithCancel(ctx)
	defer cancel()
	timer := time.AfterFunc(responseTimeout, cancel)
	req, err := http.NewRequestWithContext(responseCtx, http.MethodGet, manifestURL, nil)
	if err != nil {
		return manifest, err
	}
	resp, err := client.Do(req)
	if !timer.Stop() {
		// The response deadline cancelled the request, possibly just after
		// its headers arrived; its body can no longer be read.
		if err == nil {
			resp.Body.Close()
		}
		return manifest, fmt.Errorf("update manifest: no response within %v", responseTimeout)
	}
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
// byte request resolves GitHub's rolling URL to one immutable asset URL. When
// that signed link expires, the rolling URL is resolved again (resolve) and the
// ETag must show that the new link names the same asset.
type updateRangeReader struct {
	ctx         context.Context
	client      *http.Client
	releaseURL  string
	assetURL    string
	resolve     bool
	size        int64
	etag        string
	mu          sync.Mutex
	cacheOff    int64
	cacheData   []byte
	lastRequest time.Duration
}

// updateRangeRetryable marks a failure that a repeated identical request can
// fix: a dropped connection, a timeout or temporary server-side throttling.
type updateRangeRetryable struct{ error }

func (e updateRangeRetryable) Unwrap() error { return e.error }

func newUpdateRangeReader(ctx context.Context, client *http.Client, assetURL string, size int64) (*updateRangeReader, error) {
	r := &updateRangeReader{ctx: ctx, client: client, releaseURL: assetURL, assetURL: assetURL, size: size, cacheOff: -1}
	content, err := r.request(0, 1)
	if err != nil {
		return nil, err
	}
	r.cacheOff = 0
	r.cacheData = content
	return r, nil
}

// Each retry keeps the asset's ETag precondition, so a retried range still
// comes from the same immutable release asset.
func (r *updateRangeReader) request(offset, length int64) ([]byte, error) {
	started := time.Now()
	defer func() { r.lastRequest = time.Since(started) }()
	for attempt := 1; ; attempt++ {
		content, err := r.requestOnce(offset, length)
		var retryable updateRangeRetryable
		if err == nil || attempt == updateRangeAttempts || !errors.As(err, &retryable) {
			return content, err
		}
		select {
		case <-r.ctx.Done():
			return nil, errors.Join(r.ctx.Err(), err)
		case <-time.After(time.Duration(attempt) * updateRangeRetryDelay):
		}
	}
}

func (r *updateRangeReader) requestOnce(offset, length int64) ([]byte, error) {
	requestURL := r.assetURL
	if r.resolve {
		requestURL = r.releaseURL
	}
	req, err := http.NewRequestWithContext(r.ctx, http.MethodGet, requestURL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Range", fmt.Sprintf("bytes=%d-%d", offset, offset+length-1))
	req.Header.Set("Accept-Encoding", "identity")
	if r.etag != "" && !r.resolve {
		req.Header.Set("If-Match", r.etag)
	}
	resp, err := r.client.Do(req)
	if err != nil {
		if r.ctx.Err() != nil || errors.Is(err, errUntrustedUpdateRedirect) {
			return nil, err
		}
		return nil, updateRangeRetryable{err}
	}
	defer resp.Body.Close()
	switch resp.StatusCode {
	case http.StatusRequestTimeout, http.StatusTooManyRequests, http.StatusInternalServerError, http.StatusBadGateway, http.StatusServiceUnavailable, http.StatusGatewayTimeout:
		return nil, updateRangeRetryable{fmt.Errorf("release host returned HTTP %d", resp.StatusCode)}
	case http.StatusUnauthorized, http.StatusForbidden:
		// GitHub signs each resolved asset link for a few minutes, which a
		// slow download outlasts.
		if !r.resolve && r.assetURL != r.releaseURL {
			r.resolve = true
			return nil, updateRangeRetryable{fmt.Errorf("release download link expired (HTTP %d)", resp.StatusCode)}
		}
	}
	wantRange := fmt.Sprintf("bytes %d-%d/%d", offset, offset+length-1, r.size)
	if resp.StatusCode != http.StatusPartialContent || resp.Header.Get("Content-Range") != wantRange || resp.Header.Get("Content-Encoding") != "" || (resp.ContentLength >= 0 && resp.ContentLength != length) {
		return nil, errors.New("release host did not provide the requested ZIP range; keeping the installed version")
	}
	finalURL := resp.Request.URL.String()
	etag := resp.Header.Get("ETag")
	if r.cacheOff >= 0 {
		sameAsset := finalURL == r.assetURL && (r.etag == "" || etag == r.etag)
		if r.resolve && r.etag != "" {
			// A renewed link differs from the expired one.
			sameAsset = etag == r.etag
		}
		if !sameAsset {
			return nil, errors.New("release asset changed during update")
		}
	}
	content, err := io.ReadAll(io.LimitReader(resp.Body, length+1))
	if err != nil || int64(len(content)) != length {
		if err == nil {
			err = io.ErrUnexpectedEOF
		}
		if r.ctx.Err() != nil {
			return nil, err
		}
		return nil, updateRangeRetryable{err}
	}
	r.assetURL, r.etag, r.resolve = finalURL, etag, false
	return content, nil
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
			length := int64(minUpdateRangeBytes)
			if pos == r.cacheOff+int64(len(r.cacheData)) && r.lastRequest < time.Second {
				length = min(max(2*int64(len(r.cacheData)), minUpdateRangeBytes), maxUpdateRangeBytes)
			}
			if length > r.size-pos {
				length = r.size - pos
			}
			data, err := r.request(pos, length)
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
