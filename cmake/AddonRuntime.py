"""Export installable addon assets while retaining unknown dynamic resources."""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import xml.etree.ElementTree as ET


DEVELOPMENT_METADATA = {".git", ".github", ".vscode", ".idea"}
DEVELOPMENT_DIRECTORIES = {"docs", "tests"}
DEVELOPMENT_FILES = {".portable-source", ".editorconfig", ".gitignore", ".gitattributes", ".luacheckrc",
                     ".coderabbit.yaml", "stylua.toml", "build-addon.sh", "agents.md", "contributing.md",
                     "code_of_conduct.md", "todo.md", "changelog.md"}


def development_path(relative: str) -> bool:
    path = PurePosixPath(relative)
    return (any(part.casefold() in DEVELOPMENT_METADATA for part in path.parts)
            or path.parts[0].casefold() in DEVELOPMENT_DIRECTORIES
            or path.name.casefold() in DEVELOPMENT_FILES
            or re.fullmatch(r"test_.*\.lua", path.name, re.IGNORECASE) is not None)


def safe_relative(value: str) -> str:
    value = value.replace("\\", "/")
    if (not value or value.startswith("/") or ":" in value
            or any(part in ("", ".", "..") for part in value.split("/"))):
        raise ValueError(f"Unsafe addon asset path: {value!r}")
    return value


def runtime_paths(source: Path, toc: str) -> list[str]:
    """Protect TOC and recursive XML loads, then exclude known development paths.

    Unlisted Lua, textures, fonts and any unknown resource type remain included:
    addons can load these dynamically and file extensions cannot establish usage.
    """
    toc = safe_relative(toc)
    if source.is_symlink() or not source.is_dir():
        raise ValueError("Addon source must be a real directory")
    files = {}
    folded = set()
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symbolic link in addon: {path}")
        if path.is_file():
            relative = safe_relative(path.relative_to(source).as_posix())
            if relative.casefold() in folded:
                raise ValueError(f"Case-colliding addon asset: {relative}")
            folded.add(relative.casefold())
            files[relative] = path
    if toc not in files:
        raise ValueError(f"Missing addon TOC: {toc}")
    protected = {toc}
    pending = []
    for line in files[toc].read_text(encoding="utf-8-sig").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        relative = safe_relative(value)
        if relative not in files:
            raise ValueError(f"Missing addon TOC asset: {relative}")
        protected.add(relative)
        if relative.lower().endswith(".xml"):
            pending.append(relative)
    visited = set()
    while pending:
        relative = pending.pop()
        if relative in visited:
            continue
        visited.add(relative)
        try:
            document = ET.fromstring(files[relative].read_bytes())
        except ET.ParseError as error:
            raise ValueError(f"Invalid addon XML: {relative}: {error}") from None
        for node in document.iter():
            if node.tag.rsplit("}", 1)[-1] not in ("Script", "Include") or "file" not in node.attrib:
                continue
            value = node.attrib["file"].replace("\\", "/")
            if value.startswith("/") or ":" in value:
                raise ValueError(f"Unsafe addon XML include: {relative}: {value}")
            if value.startswith("Interface/"):
                prefix = f"Interface/AddOns/{PurePosixPath(toc).stem}/"
                if not value.startswith(prefix):
                    continue  # Shared Blizzard/other-addon includes are not local assets.
                candidate = value[len(prefix):]
            else:
                parts = list(PurePosixPath(relative).parent.parts)
                for part in value.split("/"):
                    if part == "..":
                        if not parts:
                            raise ValueError(f"Escaping addon XML include: {relative}: {value}")
                        parts.pop()
                    elif part not in ("", "."):
                        parts.append(part)
                candidate = "/".join(parts)
            candidate = safe_relative(candidate)
            if candidate not in files:
                raise ValueError(f"Missing addon XML asset: {relative}: {candidate}")
            protected.add(candidate)
            if candidate.lower().endswith(".xml"):
                pending.append(candidate)
    return [relative for relative in files if relative in protected or not development_path(relative)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--toc", required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    paths = runtime_paths(args.source, args.toc)
    if args.destination is not None:
        if args.destination.exists() or args.destination.resolve().is_relative_to(args.source.resolve()):
            raise ValueError("Runtime export destination must be new and outside its source")
        args.destination.mkdir(parents=True)
        for relative in paths:
            target = args.destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.source / relative, target)
    if args.list:
        print(json.dumps(paths))
    else:
        print(f"Exported {len(paths)} addon runtime assets")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(f"Addon runtime export failed: {error}")
