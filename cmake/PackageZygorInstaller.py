"""Package a verified Zygor Individual Progression installer without redistributing the addon.

GitHub does not promise byte-identical source archives over time, so the
installer checks every extracted file of the addon folder against SHA-256
hashes of the pinned Git tree instead of one archive hash. Packaging proves
that the upstream archive matches that tree and that the installer's patch
data reproduces the prepared, tested addon.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
from urllib.request import urlopen
import zipfile


ROOT = Path(__file__).resolve().parents[1]
NAME = "ZygorGuidesViewerRM"
REPOSITORY = "https://github.com/ErebusAres/ZygorGuidesRemaster-3.3.5a_WOTLK.git"
ARCHIVE_BASE = "https://github.com/ErebusAres/ZygorGuidesRemaster-3.3.5a_WOTLK/archive/"
ARCHIVE_ROOT = "ZygorGuidesRemaster-3.3.5a_WOTLK-"
PACKAGE_FILES = {"Install-Zygor.cmd", "Install-Zygor.ps1", "README.md", "LICENSE",
                 "SOURCE_MANIFEST.json", "PATCH_DATA.json", "UPSTREAM_FILES.json"}
# Files preparation adds to the prepared addon.
PREPARED_STAMPS = {"SOURCE_REVISION.txt", ".portable-source"}
MAX_ENTRIES = 100000
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def locked_addon(repository: Path) -> dict:
    lock = json.loads((repository / "versions.lock.json").read_text(encoding="utf-8"))
    matches = [entry for entry in lock.get("sourceAddons", []) if entry.get("name") == NAME]
    if lock.get("schemaVersion") != 1 or len(matches) != 1:
        raise ValueError("Expected one locked Zygor source addon")
    addon = matches[0]
    if (addon.get("url") != REPOSITORY or not re.fullmatch(r"[a-f0-9]{40}", addon.get("revision", ""))
            or addon.get("path") != NAME or addon.get("interface") != 30300 or addon.get("toc") != NAME + ".toc"
            or not addon.get("patches")):
        raise ValueError("Invalid pinned Zygor installer source")
    for patch in addon["patches"]:
        if not re.fullmatch(r"patches/[A-Za-z0-9_.-]+[.]patch", patch):
            raise ValueError("Invalid Zygor source patch path")
        path = repository / patch
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing Zygor source patch: {patch}")
    return addon


def source_url(addon: dict) -> str:
    return f"{ARCHIVE_BASE}{addon['revision']}.zip"


def git(directory: Path, *arguments: str, ceiling: Path | None = None) -> bytes:
    environment = os.environ.copy()
    if ceiling is not None:
        environment["GIT_CEILING_DIRECTORIES"] = str(ceiling)
    # Reconstruct archive bytes without inheriting the host's checkout conversion.
    result = subprocess.run(["git", "-c", "core.autocrlf=false", "-C", str(directory), *arguments], capture_output=True,
                            env=environment, check=False)
    if result.returncode:
        raise ValueError("Cannot apply or read the pinned Zygor source: " + result.stderr.decode(errors="replace").strip())
    return result.stdout


def pinned_files(repository: Path, addon: dict) -> dict[str, bytes]:
    """The addon folder as an archive of the pinned commit contains it."""
    cache = repository / ".module-cache" / ("client-addon-" + NAME)
    git(cache, "cat-file", "-e", addon["revision"] + "^{commit}")
    payload = git(cache, "archive", "--format=tar", addon["revision"], NAME)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        for member in archive.getmembers():
            if member.isfile():
                files[member.name[len(NAME) + 1:]] = archive.extractfile(member).read()
            elif not member.isdir() and member.name != "pax_global_header":
                raise ValueError(f"Unsupported entry in the pinned Zygor source: {member.name}")
    if NAME + ".toc" not in files:
        raise ValueError("The pinned Zygor source has no addon TOC")
    return files


def source_archive(repository: Path, addon: dict, provided: Path | None) -> Path:
    archive = provided or repository / ".module-cache" / f"Zygor-{addon['revision']}.zip"
    if not archive.exists():
        if provided:
            raise ValueError("Provided Zygor source archive does not exist")
        archive.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(source_url(addon), timeout=120) as response:
            payload = response.read()
        staged = archive.with_suffix(".partial")
        staged.write_bytes(payload)
        os.replace(staged, archive)
    return archive


def extract_addon(archive: Path, revision: str) -> dict[str, bytes]:
    """The addon folder of the upstream archive, with the installer's path rules."""
    root = ARCHIVE_ROOT + revision + "/"
    prefix = root + NAME + "/"
    seen, files, total = set(), {}, 0
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        if len(entries) > MAX_ENTRIES:
            raise ValueError("The Zygor archive has too many entries")
        for entry in entries:
            path = entry.filename
            if (not path.startswith(root) or "\\" in path or ":" in path or "\0" in path or "//" in path
                    or any(part in (".", "..") for part in path.rstrip("/").split("/"))
                    or (entry.external_attr >> 16) & 0o170000 == 0o120000 or entry.external_attr & 0x400):
                raise ValueError(f"Unsafe Zygor source archive path: {path}")
            if path.rstrip("/").casefold() in seen:
                raise ValueError(f"Duplicate Zygor source archive path: {path}")
            seen.add(path.rstrip("/").casefold())
            if not path.startswith(prefix) or entry.is_dir():
                continue
            total += entry.file_size
            if entry.file_size > MAX_FILE or total > MAX_TOTAL:
                raise ValueError("The Zygor archive exceeds the installation size limit")
            files[path[len(prefix):]] = source.read(entry)
    return files


def lines(value: bytes) -> list[str]:
    return value.decode("utf-8").split("\n")


def hunks(before: bytes, after: bytes) -> list[dict]:
    old, new = lines(before), lines(after)
    return [{"start": start, "deleteCount": end - start, "lines": new[new_start:new_end]}
            for tag, start, end, new_start, new_end in
            difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes() if tag != "equal"]


def apply_hunks(before: bytes, changes: list[dict]) -> bytes:
    """The installer's patch application."""
    result = lines(before)
    for hunk in sorted(changes, key=lambda item: item["start"], reverse=True):
        result[hunk["start"]:hunk["start"] + hunk["deleteCount"]] = hunk["lines"]
    return "\n".join(result).encode("utf-8")


def patched_addon(repository: Path, addon: dict, original: dict[str, bytes]) -> dict[str, bytes]:
    with tempfile.TemporaryDirectory(prefix="zygor-installer-build-") as temporary:
        stage = Path(temporary)
        source = stage / "source"
        for relative, value in original.items():
            target = source / NAME / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
        for relative in addon["patches"]:
            normalized = stage / "source.patch"
            normalized.write_bytes((repository / relative).read_bytes().replace(b"\r\n", b"\n"))
            if not git(source, "apply", "--numstat", str(normalized), ceiling=stage).strip():
                raise ValueError("Zygor source patch has no changes")
            git(source, "apply", "--check", str(normalized), ceiling=stage)
            git(source, "apply", str(normalized), ceiling=stage)
            git(source, "apply", "--reverse", "--check", str(normalized), ceiling=stage)
        return {path.relative_to(source / NAME).as_posix(): path.read_bytes()
                for path in (source / NAME).rglob("*") if path.is_file()}


def patch_data(original: dict[str, bytes], updated: dict[str, bytes]) -> dict:
    if not set(original) <= set(updated):
        raise ValueError("Zygor installer does not support removing upstream files")
    files = []
    for path in sorted(updated):
        before, after = original.get(path), updated[path]
        if before == after:
            continue
        entry = {"path": path, "afterSha256": sha256(after), "hunks": hunks(before or b"", after)}
        if before is None:
            entry["created"] = True
        else:
            entry["beforeSha256"] = sha256(before)
        if apply_hunks(before or b"", entry["hunks"]) != after:
            raise ValueError(f"Zygor patch data does not reproduce {path}")
        files.append(entry)
    if not files:
        raise ValueError("Zygor installer has no source changes")
    return {"schemaVersion": 1, "files": files}


def check_prepared(prepared: Path, updated: dict[str, bytes]) -> None:
    """The installed result must equal the prepared addon the fixtures test."""
    if not (prepared / (NAME + ".toc")).is_file():
        raise ValueError(f"Prepared Zygor addon is missing: {prepared}. Run cmake -P cmake/PrepareModules.cmake first.")
    files = {path.relative_to(prepared).as_posix(): path.read_bytes() for path in prepared.rglob("*")
             if path.is_file() and path.relative_to(prepared).as_posix() not in PREPARED_STAMPS}
    if files.keys() != updated.keys():
        raise ValueError("Installer result and prepared Zygor addon list different files")
    for path, value in files.items():
        if value != updated[path]:
            raise ValueError(f"Installer result differs from the prepared Zygor addon: {path}")


def package(repository: Path, output: Path, provided_archive: Path | None = None,
            prepared: Path | None = None) -> None:
    addon = locked_addon(repository)
    pinned = pinned_files(repository, addon)
    archive = source_archive(repository, addon, provided_archive)
    downloaded = extract_addon(archive, addon["revision"])
    if downloaded.keys() != pinned.keys():
        raise ValueError("The Zygor source archive lists different files than the pinned Git tree")
    for path, value in pinned.items():
        if downloaded[path] != value:
            raise ValueError(f"The Zygor source archive differs from the pinned Git tree: {path}")
    updated = patched_addon(repository, addon, pinned)
    check_prepared(prepared or repository / ".module-cache/prepared-source-addons" / NAME, updated)
    payload = json_bytes(patch_data(pinned, updated))
    upstream = json_bytes({"schemaVersion": 1, "root": NAME,
                           "files": {path: sha256(value) for path, value in sorted(pinned.items())}})
    manifest = {"schemaVersion": 1, "name": NAME, "repository": addon["url"],
                "revision": addon["revision"], "interface": addon["interface"],
                "sourceArchive": {"url": source_url(addon), "root": ARCHIVE_ROOT + addon["revision"] + "/" + NAME},
                "patches": {path: sha256((repository / path).read_bytes()) for path in addon["patches"]},
                "patchDataSha256": sha256(payload), "upstreamFilesSha256": sha256(upstream)}
    installer = repository / "client-addon/zygor-installer"
    contents = {name: (installer / name).read_bytes() for name in ("Install-Zygor.cmd", "Install-Zygor.ps1", "README.md")}
    contents.update({"LICENSE": (repository / "LICENSE").read_bytes(), "SOURCE_MANIFEST.json": json_bytes(manifest),
                     "PATCH_DATA.json": payload, "UPSTREAM_FILES.json": upstream})
    if any(not value for value in contents.values()):
        raise ValueError("Empty Zygor installer asset")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="zygor-installer-package-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED) as result:
            for name, value in sorted(contents.items()):
                entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                result.writestr(entry, value)
        with zipfile.ZipFile(staged) as result:
            if set(result.namelist()) != PACKAGE_FILES or any(result.read(name) != contents[name] for name in contents):
                raise ValueError("Zygor installer ZIP differs from verified inputs")
        os.replace(staged, output)
    print(f"Packaged Zygor installer: {output} ({len(pinned)} verified upstream files, "
          f"{len(payload)} patch bytes; upstream addon not included)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-archive", type=Path, help="already downloaded pinned upstream ZIP")
    parser.add_argument("--prepared", type=Path, help="prepared ZygorGuidesViewerRM directory")
    args = parser.parse_args()
    try:
        package(args.repository.resolve(), args.output.resolve(), args.source_archive, args.prepared)
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile, tarfile.TarError) as error:
        parser.exit(1, f"Zygor installer packaging failed: {error}\n")


if __name__ == "__main__":
    main()
