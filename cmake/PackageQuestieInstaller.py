"""Package a verified Questie patch installer without redistributing the addon."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.request import urlopen
import zipfile


ROOT = Path(__file__).resolve().parents[1]
NAME = "Questie-335"
PACKAGE_FILES = {"Install-Questie.cmd", "Install-Questie.ps1", "README.md", "LICENSE",
                 "SOURCE_MANIFEST.json", "PATCH_DATA.json"}


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def locked_addon(repository: Path) -> dict:
    lock = json.loads((repository / "versions.lock.json").read_text(encoding="utf-8"))
    matches = [entry for entry in lock.get("sourceAddons", []) if entry.get("name") == NAME]
    if lock.get("schemaVersion") != 1 or len(matches) != 1:
        raise ValueError("Expected one locked Questie source addon")
    addon = matches[0]
    if (addon.get("url") != "https://github.com/Aldori15/Questie.git"
            or not re.fullmatch(r"[a-f0-9]{40}", addon.get("revision", ""))
            or not re.fullmatch(r"[a-f0-9]{64}", addon.get("archiveSha256", ""))
            or addon.get("interface") != 30300 or addon.get("toc") != NAME + ".toc"
            or not addon.get("patches")):
        raise ValueError("Invalid pinned Questie installer source")
    for patch in addon["patches"]:
        if not re.fullmatch(r"patches/[A-Za-z0-9_.-]+[.]patch", patch):
            raise ValueError("Invalid Questie source patch path")
        path = repository / patch
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing Questie source patch: {patch}")
    return addon


def source_url(addon: dict) -> str:
    return f"https://github.com/Aldori15/Questie/archive/{addon['revision']}.zip"


def source_archive(repository: Path, addon: dict, provided: Path | None) -> Path:
    archive = provided or repository / ".module-cache" / f"Questie-{addon['revision']}.zip"
    if not archive.exists():
        if provided:
            raise ValueError("Provided Questie source archive does not exist")
        archive.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(source_url(addon), timeout=60) as response:
            payload = response.read()
        if sha256(payload) != addon["archiveSha256"]:
            raise ValueError("Downloaded Questie archive does not match its pinned SHA-256")
        archive.write_bytes(payload)
    if sha256(archive.read_bytes()) != addon["archiveSha256"]:
        raise ValueError("Questie source archive does not match its pinned SHA-256")
    return archive


def extract_source(archive: Path, destination: Path, revision: str) -> None:
    prefix = f"Questie-{revision}/"
    seen = set()
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            path = entry.filename
            if (not path.startswith(prefix) or "\\" in path or ":" in path
                    or any(part in (".", "..", "") for part in path.rstrip("/").split("/"))
                    or (entry.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError(f"Unsafe Questie source archive path: {path}")
            relative = path[len(prefix):].rstrip("/")
            if not relative:
                continue
            if relative.casefold() in seen:
                raise ValueError(f"Duplicate Questie source archive path: {path}")
            seen.add(relative.casefold())
            target = destination / relative
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read(entry))


def git(directory: Path, *arguments: str, ceiling: Path | None = None) -> bytes:
    environment = os.environ.copy()
    if ceiling is not None:
        environment["GIT_CEILING_DIRECTORIES"] = str(ceiling)
    # Reconstruct archive bytes without inheriting the host's checkout conversion.
    result = subprocess.run(["git", "-c", "core.autocrlf=false", "-C", str(directory), *arguments], capture_output=True,
                            env=environment, check=False)
    if result.returncode:
        raise ValueError("Cannot reconstruct pinned Questie changes: "
                         + result.stderr.decode(errors="replace").strip())
    return result.stdout


def patch_data(repository: Path, addon: dict, archive: Path) -> dict:
    cache = repository / ".module-cache" / ("client-addon-" + NAME)
    git(cache, "cat-file", "-e", addon["revision"] + "^{commit}")
    with tempfile.TemporaryDirectory(prefix="questie-installer-build-") as temporary:
        stage = Path(temporary)
        source = stage / "source"
        source.mkdir()
        extract_source(archive, source, addon["revision"])
        originals = {path.relative_to(source).as_posix(): path.read_bytes()
                     for path in source.rglob("*") if path.is_file()}
        for relative in addon["patches"]:
            normalized = stage / "source.patch"
            normalized.write_bytes((repository / relative).read_bytes().replace(b"\r\n", b"\n"))
            if not git(source, "apply", "--numstat", str(normalized), ceiling=stage).strip():
                raise ValueError("Questie source patch has no changes")
            git(source, "apply", "--check", str(normalized), ceiling=stage)
            git(source, "apply", str(normalized), ceiling=stage)
            git(source, "apply", "--reverse", "--check", str(normalized), ceiling=stage)
        updated = {path.relative_to(source).as_posix(): path.read_bytes()
                   for path in source.rglob("*") if path.is_file()}
        if originals.keys() != updated.keys():
            raise ValueError("Questie installer supports changes to existing files only")
        files = []
        for path, before in sorted(originals.items()):
            after = updated[path]
            if before == after:
                continue
            if before != git(cache, "show", f"{addon['revision']}:{path}"):
                raise ValueError(f"Questie archive differs from the pinned Git source: {path}")
            old_lines, new_lines = before.decode("utf-8").split("\n"), after.decode("utf-8").split("\n")
            hunks = [{"start": start, "deleteCount": end - start, "lines": new_lines[new_start:new_end]}
                     for tag, start, end, new_start, new_end in
                     difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_opcodes()
                     if tag != "equal"]
            files.append({"path": path, "beforeSha256": sha256(before), "afterSha256": sha256(after),
                          "hunks": hunks})
        if not files:
            raise ValueError("Questie installer has no source changes")
        return {"schemaVersion": 1, "files": files}


def package(repository: Path, output: Path, provided_archive: Path | None = None) -> None:
    addon = locked_addon(repository)
    archive = source_archive(repository, addon, provided_archive)
    payload = json_bytes(patch_data(repository, addon, archive))
    manifest = {"schemaVersion": 1, "name": NAME, "repository": addon["url"],
                "revision": addon["revision"], "interface": addon["interface"],
                "sourceArchive": {"url": source_url(addon), "sha256": addon["archiveSha256"]},
                "patches": {path: sha256((repository / path).read_bytes()) for path in addon["patches"]},
                "patchDataSha256": sha256(payload)}
    installer = repository / "client-addon/questie-installer"
    contents = {name: (installer / name).read_bytes()
                for name in ("Install-Questie.cmd", "Install-Questie.ps1", "README.md")}
    contents.update({"LICENSE": (repository / "LICENSE").read_bytes(),
                     "SOURCE_MANIFEST.json": json_bytes(manifest), "PATCH_DATA.json": payload})
    if any(not value for value in contents.values()):
        raise ValueError("Empty Questie installer asset")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="questie-installer-package-", dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED) as result:
            for name, value in sorted(contents.items()):
                entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                result.writestr(entry, value)
        with zipfile.ZipFile(staged) as result:
            if set(result.namelist()) != PACKAGE_FILES or any(result.read(name) != contents[name] for name in contents):
                raise ValueError("Questie installer ZIP differs from verified inputs")
        os.replace(staged, output)
    print(f"Packaged Questie installer: {output} ({len(payload)} patch bytes; upstream addon not included)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-archive", type=Path, help="already downloaded pinned upstream ZIP")
    args = parser.parse_args()
    try:
        package(args.repository.resolve(), args.output.resolve(), args.source_archive)
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Questie installer packaging failed: {error}\n")


if __name__ == "__main__":
    main()
