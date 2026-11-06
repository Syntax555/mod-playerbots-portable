"""Package an addon fork's folders as its rolling Latest release ZIP.

Each --addon names a folder of the fork's checkout, its TOC and the folder name
inside WoW's Interface/AddOns. Only committed files are packaged, selected by the
server's own runtime rules in cmake/AddonRuntime.py: files the TOC or its XML
loads are always kept, other files stay unless they are known development
material. Every folder gets SOURCE_REVISION.txt with the packaged commit. With
--luac, every packaged Lua file must pass that compiler's syntax check.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile


_spec = importlib.util.spec_from_file_location(
    "addon_runtime", Path(__file__).resolve().parents[1] / "cmake/AddonRuntime.py")
ADDON_RUNTIME = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ADDON_RUNTIME)
safe_relative = ADDON_RUNTIME.safe_relative
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def tracked_files(checkout: Path, folder: str) -> dict[str, Path]:
    """Committed files below folder; untracked build output never reaches the ZIP."""
    listed = subprocess.run(["git", "-C", str(checkout), "ls-files", "-z", "--", folder],
                            check=True, capture_output=True).stdout.decode("utf-8").split("\0")
    base = PurePosixPath(folder) if folder != "." else PurePosixPath()
    files, folded = {}, set()
    for name in filter(None, listed):
        path = checkout / name
        if path.is_symlink():
            raise ValueError(f"Symbolic link in addon: {name}")
        relative = safe_relative(PurePosixPath(name).relative_to(base).as_posix())
        if relative.casefold() in folded:
            raise ValueError(f"Case-colliding addon asset: {relative}")
        folded.add(relative.casefold())
        files[relative] = path
    return files


def runtime_paths(files: dict[str, Path], toc: str) -> list[str]:
    toc = safe_relative(toc)
    if toc in files:
        interfaces = re.findall(r"(?m)^##[ \t]*Interface[ \t]*:[ \t]*(\d+)[ \t]*\r?$",
                                files[toc].read_text(encoding="utf-8-sig"))
        if interfaces != ["30300"]:
            raise ValueError(f"{toc} must declare the WoW 3.3.5a interface 30300 exactly once")
    return ADDON_RUNTIME.select_runtime(files, toc)


def check_lua(entries: dict[str, bytes], luac: str) -> None:
    for name, content in sorted(entries.items()):
        if not name.lower().endswith(".lua"):
            continue
        # WoW accepts a UTF-8 BOM that stock Lua 5.1 rejects; strip it in memory only.
        result = subprocess.run([luac, "-p", "-"], input=content.removeprefix(b"\xef\xbb\xbf"),
                                capture_output=True, check=False)
        if result.returncode:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise ValueError(f"{name}: {detail or 'Lua syntax check failed'}")


def package(checkout: Path, addons: list[tuple[str, str, str]], extras: list[tuple[str, str]], output: Path,
            luac: str | None = None) -> None:
    revision = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()
    entries: dict[str, bytes] = {}
    for folder, toc, name in addons:
        files = tracked_files(checkout, folder)
        for relative in runtime_paths(files, toc):
            entries[f"{name}/{relative}"] = files[relative].read_bytes()
        entries[f"{name}/SOURCE_REVISION.txt"] = (revision + "\n").encode("ascii")
    for source, target in extras:
        entries[safe_relative(target)] = (checkout / safe_relative(source)).read_bytes()
    if luac:
        check_lua(entries, luac)
    temporary = output.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(entries.items()):
            entry = zipfile.ZipInfo(name, FIXED_TIME)
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, content)
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip() is not None or sorted(archive.namelist()) != sorted(entries):
            raise ValueError("The packaged ZIP differs from its inputs")
    temporary.replace(output)
    print(f"Packaged {output.name}: {len(entries)} files from {revision}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=Path("."))
    parser.add_argument("--addon", action="append", required=True, metavar="FOLDER:TOC:NAME",
                        help="addon folder in the checkout, its TOC and the installed folder name")
    parser.add_argument("--extra", action="append", default=[], metavar="SOURCE:TARGET",
                        help="additional committed file and its path in the ZIP, such as a license")
    parser.add_argument("--luac", help="Lua compiler that checks the syntax of every packaged Lua file")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    addons = [tuple(value.split(":", 2)) for value in args.addon]
    extras = [tuple(value.split(":", 1)) for value in args.extra]
    if any(len(value) != 3 for value in addons) or any(len(value) != 2 for value in extras):
        parser.error("--addon takes FOLDER:TOC:NAME and --extra takes SOURCE:TARGET")
    package(args.checkout.resolve(), addons, extras, args.output.resolve(), args.luac)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Packaging failed: {error}") from None
