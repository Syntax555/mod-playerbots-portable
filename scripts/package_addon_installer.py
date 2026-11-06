"""Package an addon fork's installer for its rolling Latest release.

The installer ZIP holds no addon files. On the player's PC it downloads
GitHub's source archive of the packaged commit and checks every file of the
addon folder against SHA-256 hashes of that commit's Git tree, because GitHub
does not promise byte-identical archives over time. Packaging proves that the
archive matches the tree before the installer is published. With --luac, every
Lua file the TOC or its XML loads must pass that compiler's syntax check.
--verify-installed checks a folder the installer wrote against the package.
The installer scripts come from this repository's addon-installer templates;
the fork supplies only the README that describes its addon.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import time
from urllib.error import URLError
from urllib.request import urlopen
import zipfile


TEMPLATES = Path(__file__).resolve().with_name("addon-installer")
ADDON_NAME = r"[A-Za-z0-9_.-]+"
MAX_ENTRIES = 100000
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def git(checkout: Path, *arguments: str) -> bytes:
    # Reconstruct archive bytes without inheriting the runner's checkout conversion;
    # text=auto without an eol follows core.eol.
    return subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf", "-C", str(checkout), *arguments],
                          check=True, capture_output=True).stdout


def installed(relative: str) -> bool:
    """Repository tooling, this installer included, is not part of the addon."""
    return bool(relative) and relative.split("/")[0] != ".github"


def safe_relative(value: str) -> str:
    if (not value or "\\" in value or ":" in value or "\0" in value or value.startswith("/") or "//" in value
            or any(part in (".", "..") for part in value.rstrip("/").split("/"))):
        raise ValueError(f"Unsafe path: {value!r}")
    return value


def tree_files(checkout: Path, revision: str, path: str) -> dict[str, bytes]:
    """The addon folder as GitHub's archive of the commit contains it."""
    payload = git(checkout, "archive", "--format=tar", revision, *([path.rstrip("/")] if path else []))
    files, folded = {}, set()
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        for member in archive.getmembers():
            if member.name == "pax_global_header" or member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f"Unsupported entry in the addon tree: {member.name}")
            relative = safe_relative(member.name[len(path):])
            if not installed(relative):
                continue
            if relative.casefold() in folded:
                raise ValueError(f"Case-colliding addon file: {relative}")
            folded.add(relative.casefold())
            files[relative] = archive.extractfile(member).read()
    return files


def download(url: str, destination: Path) -> None:
    for attempt in range(5):
        try:
            with urlopen(url, timeout=300) as response:
                payload = response.read(MAX_TOTAL + 1)
            if len(payload) > MAX_TOTAL:
                raise ValueError("The source archive exceeds the installation size limit")
            staged = destination.with_suffix(".partial")
            staged.write_bytes(payload)
            os.replace(staged, destination)
            return
        except URLError as error:
            # GitHub may build the archive of a fresh commit with a short delay.
            if attempt == 4:
                raise ValueError(f"Cannot download {url}: {error}") from None
            time.sleep(15 * (attempt + 1))


def archive_files(archive: Path, revision: str, path: str) -> tuple[str, dict[str, bytes]]:
    """The addon folder of the source archive, under the installer's path rules."""
    seen, files, total, root = set(), {}, 0, None
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        if len(entries) > MAX_ENTRIES:
            raise ValueError("The source archive has too many entries")
        for entry in entries:
            name = safe_relative(entry.filename)
            if root is None:
                root = name.split("/")[0] + "/"
                if not re.fullmatch(r"[A-Za-z0-9_.-]+-" + revision + "/", root):
                    raise ValueError(f"Unexpected root in the source archive: {name}")
            if not name.startswith(root):
                raise ValueError(f"Unexpected root in the source archive: {name}")
            if name.rstrip("/").casefold() in seen:
                raise ValueError(f"Duplicate path in the source archive: {name}")
            seen.add(name.rstrip("/").casefold())
            if (entry.external_attr >> 16) & 0o170000 == 0o120000 or entry.external_attr & 0x400:
                raise ValueError(f"Linked file in the source archive: {name}")
            if not name.startswith(root + path) or entry.is_dir():
                continue
            relative = name[len(root + path):]
            if not installed(relative):
                continue
            total += entry.file_size
            if entry.file_size > MAX_FILE or total > MAX_TOTAL:
                raise ValueError("The source archive exceeds the installation size limit")
            files[relative] = source.read(entry)
    if root is None:
        raise ValueError("The source archive is empty")
    return root, files


def check_toc(files: dict[str, bytes], name: str) -> None:
    toc = files.get(name + ".toc")
    if toc is None:
        raise ValueError(f"The addon folder has no {name}.toc")
    text = toc.decode("utf-8-sig")
    if re.findall(r"(?m)^##[ \t]*Interface[ \t]*:[ \t]*(\d+)[ \t]*\r?$", text) != ["30300"]:
        raise ValueError(f"{name}.toc must declare the WoW 3.3.5a interface 30300 exactly once")
    folded = {relative.casefold() for relative in files}
    for line in text.splitlines():
        value = line.strip().replace("\\", "/")
        if value and not value.startswith("#") and safe_relative(value).casefold() not in folded:
            raise ValueError(f"Missing TOC asset: {value}")


def loaded_lua(files: dict[str, bytes], name: str) -> list[str]:
    """Lua files the client loads through the TOC and the XML it includes."""
    actual = {relative.casefold(): relative for relative in files}
    pending, loaded, visited, missing = [], [], set(), []
    for line in files[name + ".toc"].decode("utf-8-sig").splitlines():
        value = line.strip().replace("\\", "/")
        if value and not value.startswith("#"):
            pending.append(actual[value.casefold()])
    while pending:
        relative = pending.pop(0)
        if relative in visited:
            continue
        visited.add(relative)
        if relative.lower().endswith(".lua"):
            loaded.append(relative)
        elif relative.lower().endswith(".xml"):
            # The client ignores commented-out includes.
            text = re.sub(r"<!--.*?-->", "", files[relative].decode("utf-8-sig"), flags=re.DOTALL)
            base = PurePosixPath(relative).parent
            for reference in re.findall(r"""<(?:Script|Include)\b[^>]*\bfile\s*=\s*["']([^"']+)["']""", text):
                parts = list(base.parts)
                for part in reference.replace("\\", "/").split("/"):
                    if part == "..":
                        if not parts:
                            raise ValueError(f"Escaping XML include in {relative}: {reference}")
                        parts.pop()
                    elif part not in ("", "."):
                        parts.append(part)
                target = "/".join(parts)
                if target.casefold() not in actual:
                    # The client skips a missing include and loads the rest; addons use
                    # this for optional files such as user-added guides.
                    missing.append(target)
                    continue
                pending.append(actual[target.casefold()])
    if missing:
        print(f"Note: {len(missing)} XML includes name optional files that are not in the addon, such as {missing[0]}")
    return loaded


def check_lua(files: dict[str, bytes], name: str, luac: str) -> None:
    for relative in loaded_lua(files, name):
        # WoW accepts a UTF-8 BOM that stock Lua 5.1 rejects; strip it in memory only.
        result = subprocess.run([luac, "-p", "-"], input=files[relative].removeprefix(b"\xef\xbb\xbf"),
                                capture_output=True, check=False)
        if result.returncode:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise ValueError(f"{relative}: {detail or 'Lua syntax check failed'}")


def verify_installed(folder: Path, package_folder: Path) -> None:
    """The installed addon must hold exactly the packaged files and stamps."""
    manifest = (package_folder / "SOURCE_MANIFEST.json").read_bytes()
    listed = json.loads((package_folder / "ADDON_FILES.json").read_bytes())["files"]
    revision = json.loads(manifest)["revision"]
    found = {path.relative_to(folder).as_posix(): path.read_bytes() for path in folder.rglob("*") if path.is_file()}
    if found.pop("SOURCE_MANIFEST.json", None) != manifest or found.pop("SOURCE_REVISION.txt", None) != (revision + "\n").encode():
        raise ValueError("The installed addon lacks its source stamps")
    if {relative: sha256(value) for relative, value in found.items()} != listed:
        raise ValueError("The installed addon differs from the packaged file list")
    print(f"Verified {len(found)} installed files of {revision}")


def installer_scripts(name: str, short: str, title: str, contained: list[str]) -> dict[str, bytes]:
    """Install-<short>.ps1 and Install-<short>.cmd rendered from the shared templates."""
    # The values are written into PowerShell string literals and a batch echo.
    for value, pattern in ((name, ADDON_NAME), (short, r"[A-Za-z0-9]+"), (title, r"[A-Za-z0-9][A-Za-z0-9 ._-]*"),
                           *((addon, ADDON_NAME) for addon in contained)):
        if not re.fullmatch(pattern, value):
            raise ValueError(f"Unsupported installer value: {value!r}")
    values = {"@@NAME@@": name, "@@SHORT@@": short, "@@TITLE@@": title,
              "@@CONTAINED@@": ", ".join(f"'{addon}'" for addon in contained)}
    files = {}
    for template, target in (("Install-Addon.ps1", f"Install-{short}.ps1"), ("Install-Addon.cmd", f"Install-{short}.cmd")):
        text = (TEMPLATES / template).read_bytes().decode("ascii")
        for placeholder, value in values.items():
            text = text.replace(placeholder, value)
        if "@@" in text:
            raise ValueError(f"{template} has an unknown placeholder")
        files[target] = text.encode("ascii")
    return files


def installer_files(checkout: Path, readme: str, name: str, short: str, title: str,
                    contained: list[str]) -> dict[str, bytes]:
    """The rendered installer scripts, the shared LICENSE and the fork's README."""
    readme = safe_relative(readme)
    if git(checkout, "ls-files", "-z", "--", readme).decode("utf-8").split("\0")[0] != readme:
        raise ValueError(f"{readme} must be a committed file of the addon fork")
    files = installer_scripts(name, short, title, contained)
    files["LICENSE"] = (TEMPLATES / "LICENSE").read_bytes()
    files["README.md"] = (checkout / readme).read_bytes()
    return files


def package(checkout: Path, name: str, path: str, installer: dict, repository: str, output: Path,
            provided: Path | None, saved: Path | None, luac: str | None = None) -> None:
    if not re.fullmatch(r"https://github[.]com/[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError(f"Not a GitHub repository URL: {repository}")
    path = "" if path in ("", ".") else safe_relative(path.strip("/")) + "/"
    revision = git(checkout, "rev-parse", "HEAD").decode().strip()
    pinned = tree_files(checkout, revision, path)
    check_toc(pinned, name)
    if luac:
        check_lua(pinned, name, luac)
    url = f"{repository}/archive/{revision}.zip"
    archive = provided or saved or output.with_name("source-archive.zip")
    if provided is None:
        download(url, archive)
    root, downloaded = archive_files(archive, revision, path)
    if downloaded.keys() != pinned.keys():
        raise ValueError("The source archive lists different addon files than the Git tree: "
                         + ", ".join(sorted(downloaded.keys() ^ pinned.keys())[:10]))
    for relative, value in pinned.items():
        if downloaded[relative] != value:
            raise ValueError(f"The source archive differs from the Git tree: {relative}")
    if provided is None and saved is None:
        archive.unlink()
    listed = json_bytes({"schemaVersion": 1, "root": name,
                         "files": {relative: sha256(value) for relative, value in sorted(pinned.items())}})
    manifest = {"schemaVersion": 2, "name": name, "repository": repository, "revision": revision,
                "interface": 30300, "sourceArchive": {"url": url, "root": root, "path": path},
                "addonFilesSha256": sha256(listed)}
    contents = installer_files(checkout, name=name, **installer)
    contents.update({"SOURCE_MANIFEST.json": json_bytes(manifest), "ADDON_FILES.json": listed})
    temporary = output.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as result:
        for entry_name, value in sorted(contents.items()):
            entry = zipfile.ZipInfo(entry_name, FIXED_TIME)
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            result.writestr(entry, value)
    with zipfile.ZipFile(temporary) as result:
        if result.testzip() is not None or any(result.read(entry) != contents[entry] for entry in contents) \
                or sorted(result.namelist()) != sorted(contents):
            raise ValueError("The installer ZIP differs from its verified inputs")
    temporary.replace(output)
    print(f"Packaged {output.name}: installer for {name} at {revision} "
          f"({len(pinned)} verified files; the addon itself is not included)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=Path("."))
    parser.add_argument("--name", help="installed folder in Interface/AddOns and its TOC name")
    parser.add_argument("--path", default=".", help="addon folder in the repository")
    parser.add_argument("--short", help="installer file name: Install-SHORT.ps1 and Install-SHORT.cmd")
    parser.add_argument("--title", help="addon name the installer shows to players")
    parser.add_argument("--contains", action="append", default=[], metavar="ADDON",
                        help="separate addon this one already contains; the installer refuses to load both")
    parser.add_argument("--readme", default=".github/installer/README.md", help="the fork's installer README")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_SERVER_URL", "https://github.com") + "/"
                        + os.environ.get("GITHUB_REPOSITORY", ""), help="GitHub URL the installer downloads from")
    parser.add_argument("--source-archive", type=Path, help="already downloaded source archive of HEAD")
    parser.add_argument("--save-archive", type=Path, help="keep the downloaded source archive here")
    parser.add_argument("--luac", help="Lua compiler that checks the syntax of every loaded Lua file")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-installed", type=Path, metavar="FOLDER", help="installed addon folder to verify")
    parser.add_argument("--installer-package", type=Path, metavar="FOLDER", help="extracted installer ZIP")
    args = parser.parse_args()
    if args.verify_installed:
        if not args.installer_package:
            parser.error("--verify-installed needs --installer-package")
        verify_installed(args.verify_installed, args.installer_package)
        return
    if not args.name or not args.output or not args.short or not args.title:
        parser.error("packaging needs --name, --short, --title and --output")
    installer = {"readme": args.readme, "short": args.short, "title": args.title, "contained": args.contains}
    package(args.checkout.resolve(), args.name, args.path, installer, args.repository.rstrip("/"),
            args.output.resolve(), args.source_archive, args.save_archive, args.luac)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile, tarfile.TarError) as error:
        raise SystemExit(f"Installer packaging failed: {error}") from None
