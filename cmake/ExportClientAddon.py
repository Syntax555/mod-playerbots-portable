"""Reconstruct a client addon from its locked commit and ordered source patches."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile


def run_git(git: str, repository: Path, *arguments: str, ceiling: Path | None = None) -> bytes:
    environment = os.environ.copy()
    if ceiling is not None:
        environment["GIT_CEILING_DIRECTORIES"] = str(ceiling)
    result = subprocess.run([git, "-c", "core.autocrlf=false", "-C", str(repository), *arguments], env=environment,
                            capture_output=True, check=False)
    if result.returncode:
        raise ValueError(f"Cannot reconstruct locked addon source: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def addon_inputs(repository: Path, name: str) -> tuple[dict, list[tuple[str, Path]]]:
    lock = json.loads((repository / "versions.lock.json").read_text(encoding="utf-8"))
    matches = [entry for entry in lock["clientAddons"] if entry["name"] == name]
    if lock.get("schemaVersion") != 1 or len(matches) != 1:
        raise ValueError("Expected one locked client addon")
    addon = matches[0]
    if (not re.fullmatch(r"[A-Za-z0-9_-]+", name)
            or not re.fullmatch(r"[a-f0-9]{40}", addon.get("revision", ""))
            or not re.fullmatch(r"https://github.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+[.]git", addon.get("url", ""))
            or addon.get("interface") != 30300 or addon.get("toc") != name + ".toc"
            or not re.fullmatch(r"[A-Za-z0-9_.-]+", addon.get("license", ""))):
        raise ValueError("Invalid locked client addon identity")
    patches = []
    values = addon.get("patches", [])
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ValueError("Client addon patches must be an ordered list")
    for value in values:
        if not re.fullmatch(r"patches/[A-Za-z0-9_.-]+[.]patch", value):
            raise ValueError(f"Invalid client addon patch: {value}")
        path = repository / value
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(repository.resolve()):
            raise ValueError(f"Missing or unsafe client addon patch: {value}")
        patches.append((value, path))
    return addon, patches


def write_metadata(repository: Path, name: str, destination: Path) -> None:
    addon, patches = addon_inputs(repository, name)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "SOURCE_REVISION.txt").write_bytes((addon["revision"] + "\n").encode("ascii"))
    if not patches:
        return
    manifest = {"schemaVersion": 1, "name": name, "repository": addon["url"],
                "revision": addon["revision"], "interface": addon["interface"],
                "patches": {path: hashlib.sha256(file.read_bytes()).hexdigest() for path, file in patches}}
    (destination / "SOURCE_MANIFEST.json").write_bytes(
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def export_addon(repository: Path, name: str, destination: Path, git: str = "git") -> None:
    addon, patches = addon_inputs(repository, name)
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError("Addon reconstruction destination must be empty")
    cache = repository / ".module-cache" / ("client-addon-" + name)
    run_git(git, cache, "cat-file", "-e", addon["revision"] + "^{commit}")
    with tempfile.TemporaryDirectory(prefix="locked-client-addon-") as temporary:
        stage = Path(temporary)
        raw = stage / "source"
        raw.mkdir()
        archive_path = stage / "source.tar"
        run_git(git, cache, "archive", "--format=tar", "--output=" + str(archive_path), addon["revision"])
        with tarfile.open(archive_path) as archive:
            if any(not entry.isfile() and not entry.isdir() for entry in archive.getmembers()):
                raise ValueError("Linked or special file in locked addon source")
            if not hasattr(tarfile, "data_filter"):
                raise ValueError("Python 3.12 or newer is required for safe archive extraction")
            archive.extractall(raw, filter="data")

        for path, file in patches:
            normalized = stage / "source.patch"
            normalized.write_bytes(file.read_bytes().replace(b"\r\n", b"\n"))
            if not run_git(git, raw, "apply", "--numstat", str(normalized), ceiling=stage).strip():
                raise ValueError(f"Patch has no applicable files: {path}")
            run_git(git, raw, "apply", "--check", str(normalized), ceiling=stage)
            run_git(git, raw, "apply", str(normalized), ceiling=stage)
            run_git(git, raw, "apply", "--reverse", "--check", str(normalized), ceiling=stage)
        shutil.rmtree(raw / ".github", ignore_errors=True)
        for filename in (".gitignore", ".coderabbit.yaml", "AGENTS.md"):
            (raw / filename).unlink(missing_ok=True)
        write_metadata(repository, name, raw)
        shutil.copytree(raw, destination, dirs_exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--addon", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--manifest-only", action="store_true")
    parser.add_argument("--git", default="git")
    args = parser.parse_args()
    try:
        if args.manifest_only:
            write_metadata(args.repository, args.addon, args.destination)
        else:
            export_addon(args.repository, args.addon, args.destination, args.git)
    except (ValueError, OSError, KeyError, tarfile.TarError) as error:
        parser.exit(1, f"Cannot reconstruct client addon: {error}\n")


if __name__ == "__main__":
    main()
