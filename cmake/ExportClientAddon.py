"""Reconstruct a client addon from its locked commit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile


def run_git(git: str, repository: Path, *arguments: str) -> bytes:
    result = subprocess.run([git, "-c", "core.autocrlf=false", "-C", str(repository), *arguments],
                            capture_output=True, check=False)
    if result.returncode:
        raise ValueError(f"Cannot reconstruct locked addon source: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def locked_addon(repository: Path, name: str) -> dict:
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
    return addon


def write_metadata(repository: Path, name: str, destination: Path) -> None:
    addon = locked_addon(repository, name)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "SOURCE_REVISION.txt").write_bytes((addon["revision"] + "\n").encode("ascii"))


def export_addon(repository: Path, name: str, destination: Path, git: str = "git") -> None:
    addon = locked_addon(repository, name)
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
