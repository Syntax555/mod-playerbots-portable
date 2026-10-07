#!/usr/bin/env python3
"""Publish verified build artifacts as the repository's rolling Latest release.

The build must still be the current main commit. Uploads are staged in a draft
before the existing release or version tags are changed. This script uses only
the Python standard library and the Actions job's GH_TOKEN.
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
        "startup.exe", "authserver.exe", "worldserver.exe", "versions.lock.json",
    ),
    "EraTalents-client-latest.zip": (
        "Data/patch-V.mpq", "Interface/AddOns/EraTalents/EraTalents.toc",
    ),
    "MultiBot-Chatless-latest.zip": ("MultiBot/MultiBot.toc",),
}
CHECKSUM_NAME = "SHA256SUMS.txt"
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
        try:
            self._request("DELETE", f"/git/refs/tags/{quote(tag, safe='')}")
        except APIError as error:
            if error.status != 404:
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


def prepare_assets(directory: Path) -> list[Asset]:
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
                for entry_name in required:
                    try:
                        entry = archive.getinfo(entry_name)
                    except KeyError:
                        raise PublishError(f"{name} is missing {entry_name}") from None
                    if entry.is_dir() or entry.file_size == 0 or entry.flag_bits & 1:
                        raise PublishError(f"{name} has an invalid required file: {entry_name}")
        except (zipfile.BadZipFile, OSError):
            raise PublishError(f"Artifact is not a readable ZIP: {name}") from None
        assets.append(Asset(path, name, size, digest(path)))
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


def publish(client: GitHubClient, sha: str, directory: Path, notes_path: Path, run_id: str) -> PublishResult:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise PublishError("--sha must be a full 40-character commit SHA")
    if not re.fullmatch(r"[0-9]+", run_id):
        raise PublishError("--run-id must be a numeric Actions run ID")
    sha = sha.lower()
    assets = prepare_assets(directory)
    notes = render_notes(notes_path, client.repository, sha)
    if client.main_sha().lower() != sha:
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
        if client.main_sha().lower() != sha:
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
    if client.main_sha().lower() != sha:
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
