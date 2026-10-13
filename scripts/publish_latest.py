"""Publish verified build artifacts as the repository's rolling Latest release.

The build must belong to main's history and must not be older than the
current Latest. Uploads are staged in a draft, and the replacement is
published and verified under its staging tag before the previous release is
removed. This script uses only the Python standard library and the Actions
job's GH_TOKEN.

GitHub refuses the Actions token any ref change, and any release change that
names a target commit, when that commit's workflow files differ from main's.
Every ref this script creates or moves therefore points at the build commit,
which is checked against main first. Releases are retagged by name only, and
the previous release, which may predate main's workflow files, is never
changed: it is deleted once its replacement is public and verified.
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
import time
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
# Seconds to wait before repeating an idempotent request after a transient failure.
RETRY_DELAYS = (2, 5)
# Temporary tags created by publish(): the staged replacement, and the previous
# release as moved aside by earlier versions of this script.
STAGING_TAG = re.compile(r"build-[0-9]+-[0-9a-f]{12}")
BACKUP_TAG = re.compile(r"latest-previous-[0-9]+-[0-9a-f]{12}")


class PublishError(RuntimeError):
    """An actionable publication failure without authentication details."""


class APIError(PublishError):
    def __init__(self, status: int, message: str, step: str = ""):
        self.status = status
        self.message = message
        prefix = f"{step}: " if step else ""
        super().__init__(f"{prefix}GitHub API returned HTTP {status}: {message}")


@dataclass(frozen=True)
class Asset:
    path: Path
    name: str
    size: int
    sha256: str


def step(description: str, call: Any, *args: Any) -> Any:
    """Run one API step and name it in any failure."""
    try:
        return call(*args)
    except APIError as error:
        raise APIError(error.status, error.message, description) from None
    except PublishError as error:
        raise PublishError(f"{description}: {error}") from None


@dataclass(frozen=True)
class PublishResult:
    skipped: bool = False
    url: str = ""
    assets: int = 0
    removed_staging: int = 0
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
        self.retry_delays = RETRY_DELAYS

    def _request(self, method: str, path: str, payload: Any = None) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = self._headers()
        if data is not None:
            headers["Content-Type"] = "application/json"
        # Reads and PATCH updates are idempotent, so transient failures repeat.
        attempts = len(self.retry_delays) + 1 if method in {"GET", "PATCH"} else 1
        for attempt in range(attempts):
            request = Request(self._base + path, data=data, headers=headers, method=method)
            try:
                return self._open(request, timeout=60)
            except PublishError as error:
                if attempt + 1 == attempts or isinstance(error, APIError) and error.status < 500:
                    raise
            time.sleep(self.retry_delays[attempt])

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

    def workflow_files(self, commit: str) -> dict[str, str]:
        """Return the blob or tree id of each entry in the commit's .github/workflows."""
        try:
            entries = self._request("GET", f"/contents/.github/workflows?ref={commit}")
        except APIError as error:
            if error.status == 404:
                return {}
            raise
        if not isinstance(entries, list):
            raise PublishError("GitHub returned an invalid workflow directory listing")
        return {str(entry.get("path")): str(entry.get("sha")) for entry in entries}

    def tag_sha(self, tag: str) -> str | None:
        try:
            return self._request("GET", f"/git/ref/tags/{quote(tag, safe='')}")["object"]["sha"]
        except APIError as error:
            if error.status == 404:
                return None
            raise

    def create_tag(self, tag: str, sha: str) -> None:
        self._request("POST", "/git/refs", {"ref": f"refs/tags/{tag}", "sha": sha})

    def set_tag(self, tag: str, sha: str) -> None:
        if self.tag_sha(tag) is None:
            self.create_tag(tag, sha)
        else:
            self._request("PATCH", f"/git/refs/tags/{quote(tag, safe='')}", {"sha": sha, "force": True})

    def temporary_tags(self) -> list[str]:
        """Return the tags with the publisher's temporary prefixes."""
        names = []
        for prefix in ("build-", "latest-previous-"):
            refs = self._request("GET", f"/git/matching-refs/tags/{prefix}")
            if not isinstance(refs, list):
                raise PublishError("GitHub returned an invalid tag listing")
            names.extend(str(ref.get("ref", "")).removeprefix("refs/tags/") for ref in refs)
        return names

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

    # Release updates name only existing tags and never send target_commitish,
    # which GitHub checks against main's workflow files even when unchanged.
    def promote_release(self, release_id: int, tag: str, notes: str) -> dict[str, Any]:
        return self._request("PATCH", f"/releases/{release_id}", {
            "tag_name": tag, "name": "Latest", "body": notes,
            "draft": False, "prerelease": False, "make_latest": "true",
        })

    def retag_release(self, release_id: int, tag: str) -> None:
        self._request("PATCH", f"/releases/{release_id}", {"tag_name": tag})

    def list_releases(self) -> list[dict[str, Any]]:
        return self._pages("/releases")


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
                or re.search(r'(^|/)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|/|$)', name, re.IGNORECASE)):
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
            if (re.search(r"^(data|logs|mysql/data|mysql-files)(/|$)|[.]conf$|(^|/)(my[.]cnf|my[.]ini)$|(^|/)[.]portable-|^configs/realm-phase[.]txt$", name, re.IGNORECASE)
                    or re.search(r"^(addons|defaults)(/|$)|^CONTRIBUTING[.]md$|^docs/building[.]md$|(^|/)[.]git(/|$)|^src/data/sql/old/", name, re.IGNORECASE)
                    or re.search(r"^(dbimport|map_extractor|vmap4_extractor|vmap4_assembler|mmaps_generator)[.]exe$|^mmaps-config[.]yaml$|^(configs/)?dbimport[.]conf[.]dist$", name, re.IGNORECASE)
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


def commit_sha(value: Any) -> str | None:
    if isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{40}", value):
        return value.lower()
    return None


def contains(client: GitHubClient, base: str, head: str) -> bool:
    """Return whether head is base or one of its descendants."""
    if base == head:
        return True
    comparison = client.compare_commits(base, head)
    if not isinstance(comparison, dict) or comparison.get("status") != "ahead":
        return False
    merge_base = comparison.get("merge_base_commit")
    behind = comparison.get("behind_by")
    return (isinstance(merge_base, dict) and commit_sha(merge_base.get("sha")) == base
            and type(behind) is int and behind == 0)


def workflows_match_main(client: GitHubClient, sha: str, main: str) -> bool:
    """Whether GitHub lets the Actions token point refs at the build commit."""
    return sha == main or client.workflow_files(sha) == client.workflow_files(main)


def build_is_publishable(client: GitHubClient, sha: str) -> bool:
    """Accept a build from main's history unless it is older than Latest.

    Main builds queue, so newer commits may follow a finished build; it still
    replaces an older Latest. A build that finishes after a newer one was
    published is skipped. If history was rewritten and the Latest commit is no
    longer on main, any build from main replaces it. A build whose workflow
    files differ from main's cannot be tagged and waits for the newer build.
    """
    main = commit_sha(client.main_sha())
    if main is None or not contains(client, sha, main):
        return False
    latest = commit_sha(client.tag_sha("latest"))
    if latest is not None and not contains(client, latest, sha) and contains(client, latest, main):
        return False
    return workflows_match_main(client, sha, main)


def is_interrupted_publication(release: dict[str, Any]) -> bool:
    """Match only the temporary releases that publish() creates under exact tag names."""
    tag = release.get("tag_name")
    if not isinstance(tag, str) or release.get("name") != "Latest":
        return False
    return STAGING_TAG.fullmatch(tag) is not None or BACKUP_TAG.fullmatch(tag) is not None


def superseded(client: GitHubClient, sha: str) -> bool:
    """After a refused write: whether main moved on, so the newer build publishes instead."""
    try:
        return not build_is_publishable(client, sha)
    except PublishError:
        return False


def remove_release(client: GitHubClient, release: dict[str, Any]) -> None:
    step(f"deleting release {release['tag_name']}", client.delete_release, release["id"])
    step(f"deleting tag {release['tag_name']}", client.delete_tag, release["tag_name"])


def remove_failed_run_leftovers(client: GitHubClient) -> tuple[int, int]:
    """Delete drafts and unused temporary tags of failed or cancelled runs.

    Drafts never serve downloads. Published releases under temporary tags are
    kept until a replacement is verified, since one may be the only Latest.
    """
    releases = step("listing releases", client.list_releases)
    drafts = [release for release in releases if release.get("draft") is True and is_interrupted_publication(release)]
    for release in drafts:
        remove_release(client, release)
    used = {release.get("tag_name") for release in releases if release not in drafts}
    orphans = [tag for tag in step("listing temporary tags", client.temporary_tags)
               if (STAGING_TAG.fullmatch(tag) or BACKUP_TAG.fullmatch(tag)) and tag not in used]
    for tag in orphans:
        step(f"deleting tag {tag}", client.delete_tag, tag)
    return len(drafts), len(orphans)


def discard_replacement(client: GitHubClient, release_id: int, stage_tag: str) -> None:
    """Remove this run's unverified replacement; the next run removes what remains."""
    for description, call, value in (("deleting the staged release", client.delete_release, release_id),
                                     (f"deleting tag {stage_tag}", client.delete_tag, stage_tag)):
        try:
            step(description, call, value)
        except PublishError as error:
            print(f"Warning: could not remove this run's staged release: {error}", file=sys.stderr)


def publish(client: GitHubClient, sha: str, directory: Path, notes_path: Path, run_id: str) -> PublishResult:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise PublishError("--sha must be a full 40-character commit SHA")
    if not re.fullmatch(r"[0-9]+", run_id):
        raise PublishError("--run-id must be a numeric Actions run ID")
    sha = sha.lower()
    assets = prepare_assets(directory, sha)
    notes = render_notes(notes_path, client.repository, sha)
    if not build_is_publishable(client, sha):
        return PublishResult(skipped=True)
    # Publications run one at a time, so earlier drafts and unused temporary
    # tags belong to failed or cancelled runs.
    removed_staging, removed_tags = remove_failed_run_leftovers(client)

    stage_tag = f"build-{run_id}-{uuid.uuid4().hex[:12]}"
    try:
        draft = step("creating the staging draft", client.create_draft, stage_tag, sha, notes)
    except PublishError:
        if superseded(client, sha):
            return PublishResult(skipped=True, removed_staging=removed_staging, removed_tags=removed_tags)
        raise
    draft_id = draft["id"]
    try:
        for asset in assets:
            step(f"uploading {asset.name}", client.upload_asset, draft, asset)
        verified_draft = step("reading the staging draft", client.get_release, draft_id)
        if not verified_draft.get("draft") or verified_draft.get("tag_name") != stage_tag:
            raise PublishError("GitHub did not preserve the staged draft release")
        verify_assets(verified_draft, assets)
        if not build_is_publishable(client, sha):
            discard_replacement(client, draft_id, stage_tag)
            return PublishResult(skipped=True, removed_staging=removed_staging, removed_tags=removed_tags)
        previous = step("reading the Latest release", client.release_by_tag, "latest")
        # Final check immediately before the release replacement.
        if not build_is_publishable(client, sha):
            discard_replacement(client, draft_id, stage_tag)
            return PublishResult(skipped=True, removed_staging=removed_staging, removed_tags=removed_tags)
    except Exception:
        # This cleanup touches only this run's unpublished staging objects.
        discard_replacement(client, draft_id, stage_tag)
        raise

    # The replacement is published and verified under its staging tag while the
    # previous release still serves tag latest.
    try:
        step(f"creating tag {stage_tag}", client.create_tag, stage_tag, sha)
        step("publishing the new release", client.promote_release, draft_id, stage_tag, notes)
        staged = step("reading the new release", client.get_release, draft_id)
        if (staged.get("draft") is not False or staged.get("prerelease") is not False
                or staged.get("tag_name") != stage_tag or staged.get("name") != "Latest"):
            raise PublishError("GitHub did not publish the expected Latest release")
        verify_assets(staged, assets)
        # Main may have gained workflow changes since the last check; GitHub
        # would then refuse the remaining steps.
        if not build_is_publishable(client, sha):
            discard_replacement(client, draft_id, stage_tag)
            return PublishResult(skipped=True, removed_staging=removed_staging, removed_tags=removed_tags)
        step(f"moving tag latest to {sha}", client.set_tag, "latest", sha)
    except Exception:
        discard_replacement(client, draft_id, stage_tag)
        if superseded(client, sha):
            return PublishResult(skipped=True, removed_staging=removed_staging, removed_tags=removed_tags)
        raise
    # Tag names are unique, so the previous release goes before the verified
    # replacement takes tag latest. Until then the replacement already serves
    # releases/latest/download, and a run that stops here is completed by the next one.
    if previous is not None:
        try:
            step("deleting the previous release", client.delete_release, previous["id"])
        except PublishError:
            # The deletion may have completed although its response was lost.
            current = step("reading the Latest release", client.release_by_tag, "latest")
            if current is not None and current.get("id") == previous["id"]:
                raise
    try:
        step("moving the new release to tag latest", client.retag_release, draft_id, "latest")
    except PublishError:
        print("Tag latest has no release until this job is re-run or the next build publishes; "
              "releases/latest/download serves the verified replacement meanwhile.", file=sys.stderr)
        raise
    published = step("reading the new release", client.get_release, draft_id)
    if published.get("draft") is not False or published.get("tag_name") != "latest":
        raise PublishError("GitHub did not move the new release to tag latest")
    verify_assets(published, assets)
    if step("reading tag latest", client.tag_sha, "latest") != sha:
        raise PublishError("The latest tag does not point to the built commit")
    url = published.get("html_url")
    if not url:
        raise PublishError("The published release does not have a public URL")
    # Latest is published and verified; leftovers that cannot be removed now
    # are removed by the next run, so they only produce warnings.
    try:
        step(f"deleting tag {stage_tag}", client.delete_tag, stage_tag)
        # Interrupted runs can leave published releases under temporary tags.
        for release in step("listing releases", client.list_releases):
            if release.get("id") != draft_id and is_interrupted_publication(release):
                remove_release(client, release)
                removed_staging += 1
    except PublishError as error:
        print(f"Warning: cleanup after publication stopped: {error}", file=sys.stderr)
    return PublishResult(url=url, assets=len(assets), removed_staging=removed_staging, removed_tags=removed_tags)


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
        if isinstance(error, APIError) and error.status == 403 and "not accessible by integration" in error.message:
            print("GitHub refuses the Actions token ref and release changes at commits whose workflow files "
                  "differ from main's; check which commit the failed step targets.", file=sys.stderr)
        return 1
    if result.skipped:
        print("Skipped a superseded build; the current release is unchanged.")
    else:
        print(f"Published Latest: {result.url}")
        print(f"Verified {result.assets} release assets.")
    if result.removed_staging:
        print(f"Removed {result.removed_staging} releases left by interrupted publications.")
    if result.removed_tags:
        print(f"Removed {result.removed_tags} unused temporary tags.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
