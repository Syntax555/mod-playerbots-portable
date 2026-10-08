#!/usr/bin/env python3
"""Publish verified build artifacts as the repository's rolling Latest release.

The build must still match main's runtime sources. Documentation-only commits
may follow the built commit. Uploads are staged in a draft before the existing
release or version tags are changed. This script uses only the Python standard
library and the Actions job's GH_TOKEN.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import string
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen
import uuid
import zipfile


ZIP_CONTENTS = {
    "mod-playerbots-portable-latest.zip": (
        "startup.exe", "authserver.exe", "worldserver.exe", "versions.lock.json", "portable-release.json",
    ),
    "EraTalents-client-latest.zip": (
        "Data/patch-V.mpq", "Interface/AddOns/EraTalents/EraTalents.toc",
    ),
    "MultiBot-Chatless-latest.zip": ("MultiBot/MultiBot.toc",),
}
CHECKSUM_NAME = "SHA256SUMS.txt"
UPDATE_MANIFEST_NAME = "UPDATE_MANIFEST.json"
SERVER_PACKAGE_NAME = "mod-playerbots-portable-latest.zip"
# Keep these paths aligned with release.yml's documentation-only exclusions.
DOCUMENTATION_FILES = {"README.md", "AGENTS.md", "CONTRIBUTING.md", ".github/RELEASE_TEMPLATE.md"}
COMPARE_FILE_LIMIT = 300
# Limit cleanup to numbered version tags. Branches and other tag names are kept.
VERSION_TAG = re.compile(
    r"^v\d+\.\d+(?:\.\d+"
    r"(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?"
    r"(?:\+[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?)?$"
)


class PublishError(RuntimeError):
    """An actionable publication failure without authentication details."""


class APIError(PublishError):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(f"GitHub API returned HTTP {status}: {message}")


@dataclass(frozen=True)
class Asset:
    path: Path
    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class PublishResult:
    skipped: bool = False
    url: str = ""
    removed_releases: int = 0
    removed_tags: int = 0


class GitHubClient:
    """Small REST client with operations that can be mocked independently."""

    def __init__(self, repository: str, token: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise PublishError("GITHUB_REPOSITORY must be an owner/repository name")
        if not token:
            raise PublishError("GH_TOKEN is required")
        self.repository = repository
        self._token = token
        self._base = f"https://api.github.com/repos/{repository}"

    def _request(self, method: str, path: str, payload: Any = None) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = self._headers()
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self._base + path, data=data, headers=headers, method=method)
        return self._open(request, timeout=60)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mod-playerbots-portable-latest-publisher",
        }

    @staticmethod
    def _open(request: Request, timeout: int) -> Any:
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read()
        except HTTPError as error:
            # Do not include headers or request representations in diagnostics.
            try:
                message = json.loads(error.read()).get("message", "request failed")
            except (ValueError, AttributeError):
                message = "request failed"
            raise APIError(error.code, str(message)) from None
        except (URLError, TimeoutError, OSError):
            raise PublishError("GitHub request failed; check the job's network access") from None
        if not body:
            return None
        try:
            return json.loads(body)
        except ValueError:
            raise PublishError("GitHub returned an invalid JSON response") from None

    def _pages(self, path: str) -> list[dict[str, Any]]:
        results = []
        for page in range(1, 1001):
            entries = self._request("GET", f"{path}?per_page=100&page={page}")
            if not isinstance(entries, list):
                raise PublishError("GitHub returned an invalid paginated response")
            results.extend(entries)
            if len(entries) < 100:
                return results
        raise PublishError("GitHub pagination exceeded the expected repository size")

    def main_sha(self) -> str:
        return self._request("GET", "/git/ref/heads/main")["object"]["sha"]

    def compare_commits(self, base: str, head: str) -> dict[str, Any]:
        # Files are returned only on the first page, capped at 300 entries.
        return self._request("GET", f"/compare/{base}...{head}")

    def release_by_tag(self, tag: str) -> dict[str, Any] | None:
        try:
            return self._request("GET", f"/releases/tags/{quote(tag, safe='')}")
        except APIError as error:
            if error.status == 404:
                return None
            raise

    def create_draft(self, tag: str, sha: str, notes: str) -> dict[str, Any]:
        return self._request("POST", "/releases", {
            "tag_name": tag, "target_commitish": sha, "name": "Latest",
            "body": notes, "draft": True, "prerelease": False,
        })

    def upload_asset(self, release: dict[str, Any], asset: Asset) -> dict[str, Any]:
        upload_url = release["upload_url"].split("{", 1)[0]
        parsed = urlparse(upload_url)
        if parsed.scheme != "https" or parsed.netloc != "uploads.github.com":
            raise PublishError("GitHub supplied an unexpected asset upload URL")
        headers = self._headers()
        headers.update({"Content-Type": "application/octet-stream", "Content-Length": str(asset.size)})
        # Streaming avoids keeping the complete server archive in memory.
        with asset.path.open("rb") as stream:
            request = Request(upload_url + "?" + urlencode({"name": asset.name}),
                              data=stream, headers=headers, method="POST")
            return self._open(request, timeout=600)

    def get_release(self, release_id: int) -> dict[str, Any]:
        return self._request("GET", f"/releases/{release_id}")

    def delete_release(self, release_id: int) -> None:
        self._request("DELETE", f"/releases/{release_id}")

    def tag_sha(self, tag: str) -> str | None:
        try:
            return self._request("GET", f"/git/ref/tags/{quote(tag, safe='')}")["object"]["sha"]
        except APIError as error:
            if error.status == 404:
                return None
            raise

    def set_tag(self, tag: str, sha: str) -> None:
        if self.tag_sha(tag) is None:
            self._request("POST", "/git/refs", {"ref": f"refs/tags/{tag}", "sha": sha})
        else:
            self._request("PATCH", f"/git/refs/tags/{quote(tag, safe='')}", {"sha": sha, "force": True})

    def delete_tag(self, tag: str) -> None:
        # GitHub does not create the temporary ref when creating a draft.
        # DELETE for that absent ref returns 422 rather than the usual 404.
        if self.tag_sha(tag) is None:
            return
        try:
            self._request("DELETE", f"/git/refs/tags/{quote(tag, safe='')}")
        except APIError as error:
            if error.status == 404:
                return
            # A ref can disappear between the existence check and deletion.
            # Confirm absence before accepting 422; other validation failures
            # (for example, a protected ref) must still fail publication.
            if error.status == 422 and self.tag_sha(tag) is None:
                return
            raise

    def promote_release(self, release_id: int, sha: str, notes: str) -> dict[str, Any]:
        return self._request("PATCH", f"/releases/{release_id}", {
            "tag_name": "latest", "target_commitish": sha, "name": "Latest",
            "body": notes, "draft": False, "prerelease": False, "make_latest": "true",
        })

    def list_releases(self) -> list[dict[str, Any]]:
        return self._pages("/releases")

    def list_tags(self) -> list[dict[str, Any]]:
        return self._pages("/tags")


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def zip_inventory(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    """Accept the two supported ZIP writers without changing path semantics."""
    entries = {}
    seen = set()
    for entry in archive.infolist():
        name = entry.filename.removeprefix("./")
        if ((not name and entry.filename != "./") or name.startswith("/")
                or re.search(r'[\\:<>"|?*\x00-\x1f]|(^|/)\.{1,2}(/|$)|//|[. ](/|$)', name)
                or re.search(r'(^|/)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|/|$)', name, re.I)):
            raise PublishError(f"Unsafe path in portable ZIP: {entry.filename}")
        normalized = name.rstrip("/").casefold()
        if normalized in seen:
            raise PublishError(f"Duplicate path in portable ZIP: {entry.filename}")
        seen.add(normalized)
        if ((entry.external_attr >> 16) & 0xF000 == 0xA000
                or entry.external_attr & 0x400 or entry.flag_bits & 1):
            raise PublishError(f"Linked or encrypted file in portable ZIP: {entry.filename}")
        if entry.is_dir() or not name:
            if entry.file_size:
                raise PublishError(f"Nonempty directory in portable ZIP: {entry.filename}")
            continue
        if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise PublishError(f"Unsupported ZIP compression: {entry.filename}")
        entries[name] = entry
    folded_files = {name.casefold() for name in entries}
    for name in entries:
        parts = name.split("/")
        if any("/".join(parts[:count]).casefold() in folded_files for count in range(1, len(parts))):
            raise PublishError(f"File/directory collision in portable ZIP: {name}")
    return entries


def update_manifest(package: Asset, expected_revision: str | None) -> dict[str, Any]:
    """Inventory final compressed artifacts; never manage mutable user state."""
    with zipfile.ZipFile(package.path) as archive:
        entries = zip_inventory(archive)
        try:
            identity = json.loads(archive.read(entries["portable-release.json"]))
        except (KeyError, ValueError, TypeError):
            raise PublishError("The server package has an invalid portable release identity") from None
        if (not isinstance(identity, dict) or identity.get("schema") != 1
                or not re.fullmatch(r"[0-9a-f]{40}", str(identity.get("revision", "")))
                or identity.get("package") != SERVER_PACKAGE_NAME or identity.get("version") != "latest"
                or expected_revision is not None and identity["revision"] != expected_revision):
            raise PublishError("The server package has an invalid or mismatched portable release identity")
        files = []
        for name, entry in sorted(entries.items()):
            if (re.search(r"^(data|logs|mysql/data|mysql-files)(/|$)|[.]conf$|(^|/)(my[.]cnf|my[.]ini)$|(^|/)[.]portable-|^configs/realm-phase[.]txt$", name, re.I)
                    or re.search(r"^(addons|defaults)(/|$)|^CONTRIBUTING[.]md$|^docs/building[.]md$|(^|/)[.]git(/|$)", name, re.I)
                    or re.search(r"^(dbimport|map_extractor|vmap4_extractor|vmap4_assembler|mmaps_generator)[.]exe$|^mmaps-config[.]yaml$|^(configs/)?dbimport[.]conf[.]dist$", name, re.I)
                    or name == UPDATE_MANIFEST_NAME):
                raise PublishError(f"Unmanaged user or redundant development file in portable ZIP: {name}")
            hasher = hashlib.sha256()
            size = 0
            with archive.open(entry) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    size += len(chunk)
                    hasher.update(chunk)
            if size != entry.file_size:
                raise PublishError(f"Incomplete file in portable ZIP: {name}")
            files.append({"path": name, "size": size, "sha256": hasher.hexdigest()})
        return {"schema": 1, "revision": identity["revision"], "package": package.name,
                "sha256": package.sha256, "size": package.size, "files": files}


def prepare_assets(directory: Path, expected_revision: str | None = None) -> list[Asset]:
    """Validate the required packages before creating checksums or API writes."""
    if not directory.is_dir():
        raise PublishError("The artifacts directory does not exist")
    assets = []
    for name, required in ZIP_CONTENTS.items():
        candidates = sorted(path for path in directory.rglob(name) if path.is_file())
        if len(candidates) != 1:
            raise PublishError(f"Expected exactly one artifact named {name}; found {len(candidates)}")
        path = candidates[0]
        size = path.stat().st_size
        if not size:
            raise PublishError(f"Artifact is empty: {name}")
        try:
            with zipfile.ZipFile(path) as archive:
                entries = zip_inventory(archive)
                for entry_name in required:
                    try:
                        entry = entries[entry_name]
                    except KeyError:
                        raise PublishError(f"{name} is missing {entry_name}") from None
                    if entry.is_dir() or entry.file_size == 0 or entry.flag_bits & 1:
                        raise PublishError(f"{name} has an invalid required file: {entry_name}")
        except (zipfile.BadZipFile, OSError):
            raise PublishError(f"Artifact is not a readable ZIP: {name}") from None
        assets.append(Asset(path, name, size, digest(path)))
    try:
        manifest = update_manifest(next(asset for asset in assets if asset.name == SERVER_PACKAGE_NAME), expected_revision)
    except (zipfile.BadZipFile, OSError):
        raise PublishError("The server package failed file integrity verification") from None
    manifest_path = directory / UPDATE_MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    assets.append(Asset(manifest_path, UPDATE_MANIFEST_NAME, manifest_path.stat().st_size, digest(manifest_path)))
    checksum_path = directory / CHECKSUM_NAME
    checksum_path.write_text(
        "".join(f"{asset.sha256}  {asset.name}\n" for asset in sorted(assets, key=lambda item: item.name)),
        encoding="utf-8",
    )
    assets.append(Asset(checksum_path, CHECKSUM_NAME, checksum_path.stat().st_size, digest(checksum_path)))
    return assets


def render_notes(path: Path, repository: str, sha: str) -> str:
    template = path.read_text(encoding="utf-8")
    repository_url = f"https://github.com/{repository}"
    fields = {
        "repository_url": repository_url, "source_url": f"{repository_url}/blob/{sha}",
        "commit_url": f"{repository_url}/commit/{sha}", "revision": sha[:12],
    }
    try:
        for _, field, spec, conversion in string.Formatter().parse(template):
            if field is not None and (field not in fields or spec or conversion):
                raise PublishError(f"Unsupported release template field: {field}")
        notes = template.format(**fields).strip()
    except ValueError:
        raise PublishError("The release template has invalid format syntax") from None
    if not notes:
        raise PublishError("The release notes must not be empty")
    return notes


def verify_assets(release: dict[str, Any], assets: list[Asset]) -> None:
    uploaded = release.get("assets", [])
    expected = {asset.name: asset for asset in assets}
    if len(uploaded) != len(expected) or {entry.get("name") for entry in uploaded} != set(expected):
        raise PublishError("The staged release does not contain exactly the expected assets")
    for entry in uploaded:
        asset = expected[entry["name"]]
        if entry.get("size") != asset.size or entry.get("state", "uploaded") != "uploaded":
            raise PublishError(f"Uploaded asset is incomplete: {asset.name}")
        api_digest = entry.get("digest")
        if api_digest and api_digest.lower() != f"sha256:{asset.sha256}":
            raise PublishError(f"Uploaded asset checksum does not match: {asset.name}")


def documentation_path(name: Any) -> bool:
    if (not isinstance(name, str) or "\\" in name or "\x00" in name
            or any(part in {"", ".", ".."} for part in name.split("/"))):
        return False
    return name in DOCUMENTATION_FILES or name.startswith("docs/")


def build_is_current(client: GitHubClient, sha: str) -> bool:
    current = client.main_sha()
    if not isinstance(current, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", current):
        return False
    current = current.lower()
    if current == sha:
        return True
    comparison = client.compare_commits(sha, current)
    if not isinstance(comparison, dict) or comparison.get("status") != "ahead":
        return False
    for field in ("base_commit", "merge_base_commit"):
        commit = comparison.get(field)
        if not isinstance(commit, dict) or commit.get("sha") != sha:
            return False
    ahead, behind, total = (comparison.get(field) for field in ("ahead_by", "behind_by", "total_commits"))
    if (any(type(count) is not int for count in (ahead, behind, total))
            or ahead <= 0 or behind != 0 or total != ahead):
        return False
    files = comparison.get("files")
    # At the API cap, a documentation-only prefix could hide runtime changes.
    if not isinstance(files, list) or len(files) >= COMPARE_FILE_LIMIT:
        return False
    for entry in files:
        if not isinstance(entry, dict):
            return False
        status = entry.get("status")
        if (not isinstance(status, str) or status not in {
                "added", "removed", "modified", "renamed", "copied", "changed", "unchanged",
        } or not documentation_path(entry.get("filename"))):
            return False
        if status in {"renamed", "copied"} and "previous_filename" not in entry:
            return False
        if "previous_filename" in entry and not documentation_path(entry["previous_filename"]):
            return False
    return True


def publish(client: GitHubClient, sha: str, directory: Path, notes_path: Path, run_id: str) -> PublishResult:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise PublishError("--sha must be a full 40-character commit SHA")
    if not re.fullmatch(r"[0-9]+", run_id):
        raise PublishError("--run-id must be a numeric Actions run ID")
    sha = sha.lower()
    assets = prepare_assets(directory, sha)
    notes = render_notes(notes_path, client.repository, sha)
    if not build_is_current(client, sha):
        return PublishResult(skipped=True)

    stage_tag = f"build-{run_id}-{uuid.uuid4().hex[:12]}"
    draft = client.create_draft(stage_tag, sha, notes)
    draft_id = draft["id"]
    try:
        for asset in assets:
            client.upload_asset(draft, asset)
        verified_draft = client.get_release(draft_id)
        if not verified_draft.get("draft") or verified_draft.get("tag_name") != stage_tag:
            raise PublishError("GitHub did not preserve the staged draft release")
        verify_assets(verified_draft, assets)
        if not build_is_current(client, sha):
            client.delete_release(draft_id)
            client.delete_tag(stage_tag)
            return PublishResult(skipped=True)
    except Exception:
        # This cleanup touches only this run's unpublished staging objects.
        try:
            client.delete_release(draft_id)
            client.delete_tag(stage_tag)
        except PublishError:
            pass
        raise

    previous = client.release_by_tag("latest")
    # Final freshness check immediately before the release replacement.
    if not build_is_current(client, sha):
        client.delete_release(draft_id)
        client.delete_tag(stage_tag)
        return PublishResult(skipped=True)
    if previous is not None:
        client.delete_release(previous["id"])
    client.set_tag("latest", sha)
    client.promote_release(draft_id, sha, notes)
    published = client.get_release(draft_id)
    if (published.get("draft") is not False or published.get("prerelease") is not False
            or published.get("tag_name") != "latest" or published.get("name") != "Latest"):
        raise PublishError("GitHub did not publish the expected Latest release")
    verify_assets(published, assets)
    if client.tag_sha("latest") != sha:
        raise PublishError("The latest tag does not point to the built commit")
    url = published.get("html_url")
    if not url:
        raise PublishError("The published release does not have a public URL")

    # Numbered history is removed only after the replacement is publicly verified.
    removed_releases = 0
    for release in client.list_releases():
        if VERSION_TAG.fullmatch(release.get("tag_name", "")):
            client.delete_release(release["id"])
            removed_releases += 1
    removed_tags = 0
    for tag in client.list_tags():
        if VERSION_TAG.fullmatch(tag.get("name", "")):
            client.delete_tag(tag["name"])
            removed_tags += 1
    client.delete_tag(stage_tag)
    return PublishResult(url=url, removed_releases=removed_releases, removed_tags=removed_tags)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--notes", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    try:
        client = GitHubClient(os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GH_TOKEN", ""))
        result = publish(client, args.sha, args.artifacts, args.notes, args.run_id)
    except (PublishError, OSError) as error:
        print(f"Publication failed: {error}", file=sys.stderr)
        return 1
    if result.skipped:
        print("Skipped a superseded build; the current release is unchanged.")
    else:
        print(f"Published Latest: {result.url}")
        print(f"Verified 3 ZIPs and {CHECKSUM_NAME}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
