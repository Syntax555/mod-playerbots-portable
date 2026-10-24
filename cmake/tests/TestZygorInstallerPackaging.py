"""Verify the Zygor installer release contents against the pinned Git tree, the patch and the prepared addon."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("zygor_packaging", ROOT / "cmake/PackageZygorInstaller.py")
packaging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packaging)
POWERSHELL = os.environ.get("POWERSHELL_EXECUTABLE") or shutil.which("powershell.exe") or shutil.which("pwsh")
NAME = "ZygorGuidesViewerRM"
UPSTREAM_ONLY = b"upstream guide text; do not redistribute"


def git(repository: Path, *arguments: str) -> bytes:
    return subprocess.run(["git", "-C", str(repository), *arguments], check=True, capture_output=True).stdout


class ZygorInstallerPackagingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="zygor-packaging-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cache = self.root / f".module-cache/client-addon-{NAME}"
        self.cache.mkdir(parents=True)
        git(self.cache, "init", "--quiet")
        git(self.cache, "config", "user.name", "Fixture")
        git(self.cache, "config", "user.email", "test@example.invalid")
        git(self.cache, "config", "core.autocrlf", "false")
        self.files = {f"{NAME}/{NAME}.toc": b"## Interface: 30300\nfiles.xml\n",
                      f"{NAME}/files.xml": b'<Ui>\n\t<Script file="Main.lua"/>\n</Ui>\n',
                      f"{NAME}/Main.lua": b'local tier = "upstream"\nreturn tier\n',
                      f"{NAME}/Guides/Leveling.lua": UPSTREAM_ONLY + b"\n",
                      "tools/test_main.lua": b"assert(true)\n", "LICENSE": b"Upstream license\n"}
        for relative, content in self.files.items():
            path = self.cache / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        git(self.cache, "add", ".")
        git(self.cache, "commit", "--quiet", "-m", "Pinned fixture")
        self.revision = git(self.cache, "rev-parse", "HEAD").decode().strip()
        (self.cache / NAME / "Main.lua").write_bytes(b'local tier = "earned"\nreturn tier\n')
        (self.cache / NAME / "files.xml").write_bytes(
            b'<Ui>\n\t<Script file="Main.lua"/>\n\t<Script file="IndividualProgression.lua"/>\n</Ui>\n')
        (self.cache / NAME / "IndividualProgression.lua").write_bytes(b"return true\n")
        git(self.cache, "add", "-A")
        patch = self.root / "patches/zygor-individual-progression.patch"
        patch.parent.mkdir()
        patch.write_bytes(git(self.cache, "diff", "--cached"))
        self.expected = {path.relative_to(self.cache / NAME).as_posix(): path.read_bytes()
                         for path in (self.cache / NAME).rglob("*") if path.is_file()}
        git(self.cache, "reset", "--quiet", "--hard")
        self.addon = {"name": NAME, "url": packaging.REPOSITORY, "revision": self.revision, "path": NAME,
                      "interface": 30300, "toc": f"{NAME}.toc", "patches": [patch.relative_to(self.root).as_posix()]}
        (self.root / "versions.lock.json").write_text(
            json.dumps({"schemaVersion": 1, "sourceAddons": [self.addon]}), encoding="utf-8")
        self.prepared = self.root / f".module-cache/prepared-source-addons/{NAME}"
        for relative, value in self.expected.items():
            (self.prepared / relative).parent.mkdir(parents=True, exist_ok=True)
            (self.prepared / relative).write_bytes(value)
        (self.prepared / "SOURCE_REVISION.txt").write_text(self.revision + "\n")
        (self.prepared / ".portable-source").write_text("stamp\n")
        self.archive = self.root / "original.zip"
        self.output = self.root / "output/Zygor-IP-latest.zip"
        self.write_archive()
        installer = self.root / "client-addon/zygor-installer"
        shutil.copytree(ROOT / "client-addon/zygor-installer", installer)
        shutil.copyfile(ROOT / "LICENSE", self.root / "LICENSE")

    def write_archive(self, changes=None, extra=None):
        prefix = packaging.ARCHIVE_ROOT + self.revision + "/"
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr(prefix, b"")
            for relative, value in self.files.items():
                value = (changes or {}).get(relative, value)
                if value is not None:
                    archive.writestr(prefix + relative, value)
            for relative, value in (extra or {}).items():
                archive.writestr(relative, value)

    def test_package_contains_installer_and_verified_changes_without_upstream_addon(self):
        packaging.package(self.root, self.output, self.archive)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(set(archive.namelist()), packaging.PACKAGE_FILES)
            manifest = json.loads(archive.read("SOURCE_MANIFEST.json"))
            changes = archive.read("PATCH_DATA.json")
            listing = archive.read("UPSTREAM_FILES.json")
            self.assertEqual(manifest["patchDataSha256"], hashlib.sha256(changes).hexdigest())
            self.assertEqual(manifest["upstreamFilesSha256"], hashlib.sha256(listing).hexdigest())
            self.assertEqual(manifest["sourceArchive"]["url"], f"{packaging.ARCHIVE_BASE}{self.revision}.zip")
            upstream = json.loads(listing)["files"]
            self.assertEqual(set(upstream), {f"{NAME}.toc", "files.xml", "Main.lua", "Guides/Leveling.lua"})
            self.assertEqual(upstream["Main.lua"], hashlib.sha256(self.files[f"{NAME}/Main.lua"]).hexdigest())
            files = {file["path"]: file for file in json.loads(changes)["files"]}
            self.assertEqual(set(files), {"files.xml", "Main.lua", "IndividualProgression.lua"})
            self.assertTrue(files["IndividualProgression.lua"]["created"])
            self.assertNotIn("beforeSha256", files["IndividualProgression.lua"])
            self.assertNotIn(UPSTREAM_ONLY, b"".join(archive.read(name) for name in archive.namelist()))
        first = self.output.read_bytes()
        packaging.package(self.root, self.output, self.archive)
        self.assertEqual(self.output.read_bytes(), first)

    @unittest.skipUnless(POWERSHELL, "PowerShell is required to exercise the packaged installer")
    def test_generated_package_installs_the_prepared_addon(self):
        packaging.package(self.root, self.output, self.archive)
        extracted = self.root / "downloaded-installer"
        with zipfile.ZipFile(self.output) as archive:
            archive.extractall(extracted)
        addons = self.root / "WoW/Interface/AddOns"
        addons.mkdir(parents=True)
        result = subprocess.run([POWERSHELL, "-NoProfile", "-File", str(extracted / "Install-Zygor.ps1"),
                                 "-AddOnsPath", str(addons), "-SourceArchive", str(self.archive)],
                                capture_output=True, text=True, timeout=60, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        installed = {path.relative_to(addons / NAME).as_posix(): path.read_bytes()
                     for path in (addons / NAME).rglob("*") if path.is_file()}
        self.assertEqual(installed.pop("SOURCE_REVISION.txt"), (self.revision + "\n").encode())
        self.assertEqual(json.loads(installed.pop("SOURCE_MANIFEST.json"))["revision"], self.revision)
        self.assertEqual(installed, self.expected)

    def test_pinned_tree_ignores_git_line_ending_settings(self):
        def verify(module):
            files = module.pinned_files(self.root, self.addon)
            self.assertEqual(files["Main.lua"], self.files[f"{NAME}/Main.lua"])

        environment = {"GIT_CONFIG_COUNT": "2",
                       "GIT_CONFIG_KEY_0": "core.autocrlf", "GIT_CONFIG_VALUE_0": "true",
                       "GIT_CONFIG_KEY_1": "core.eol", "GIT_CONFIG_VALUE_1": "crlf"}
        with mock.patch.dict(os.environ, environment):
            verify(packaging)
            source = Path(SPEC.origin).read_text(encoding="utf-8")
            setting = '"-c", "core.autocrlf=false", '
            self.assertEqual(source.count(setting), 1)
            mutated_path = self.root / "PackageZygorInstaller.py"
            mutated_path.write_text(source.replace(setting, ""), encoding="utf-8")
            mutated_spec = importlib.util.spec_from_file_location("zygor_packaging_mutated", mutated_path)
            mutated = importlib.util.module_from_spec(mutated_spec)
            mutated_spec.loader.exec_module(mutated)
            with self.assertRaises(AssertionError):
                verify(mutated)

    def test_archive_must_match_the_pinned_tree_and_failures_keep_the_previous_package(self):
        self.output.parent.mkdir()
        self.output.write_bytes(b"previous verified package")
        cases = (
            ({f"{NAME}/Main.lua": b"changed upstream\n"}, None, "differs from the pinned Git tree"),
            ({f"{NAME}/Guides/Leveling.lua": None}, None, "lists different files"),
            (None, {packaging.ARCHIVE_ROOT + self.revision + f"/{NAME}/Injected.lua": b"x"}, "lists different files"),
            (None, {packaging.ARCHIVE_ROOT + self.revision + "/../escape.lua": b"x"}, "Unsafe Zygor source archive path"),
            (None, {"other-project/Main.lua": b"x"}, "Unsafe Zygor source archive path"),
            (None, {packaging.ARCHIVE_ROOT + self.revision + f"/{NAME}/MAIN.lua": b"x"}, "Duplicate Zygor source archive path"),
        )
        for changes, extra, message in cases:
            with self.subTest(message=message, changes=changes, extra=extra):
                self.write_archive(changes, extra)
                with self.assertRaisesRegex(ValueError, message):
                    packaging.package(self.root, self.output, self.archive)
                self.assertEqual(self.output.read_bytes(), b"previous verified package")
        self.assertFalse((self.root / "escape.lua").exists())

    def test_result_must_equal_the_prepared_addon(self):
        (self.prepared / "Main.lua").write_bytes(b"stale preparation\n")
        with self.assertRaisesRegex(ValueError, "differs from the prepared Zygor addon: Main.lua"):
            packaging.package(self.root, self.output, self.archive)
        (self.prepared / "Main.lua").write_bytes(self.expected["Main.lua"])
        (self.prepared / "Extra.lua").write_bytes(b"local file\n")
        with self.assertRaisesRegex(ValueError, "list different files"):
            packaging.package(self.root, self.output, self.archive)
        shutil.rmtree(self.prepared)
        with self.assertRaisesRegex(ValueError, "Prepared Zygor addon is missing"):
            packaging.package(self.root, self.output, self.archive)
        self.assertFalse(self.output.exists())

    def test_rejects_invalid_lock_entries_and_inapplicable_patches(self):
        lock = self.root / "versions.lock.json"
        for key, value in (("path", "Other"), ("url", "https://github.com/example/Zygor.git"),
                           ("interface", 11200), ("revision", "main"), ("patches", [])):
            with self.subTest(key=key):
                entry = dict(self.addon, **{key: value})
                lock.write_text(json.dumps({"schemaVersion": 1, "sourceAddons": [entry]}), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Invalid pinned Zygor installer source"):
                    packaging.package(self.root, self.output, self.archive)
        lock.write_text(json.dumps({"schemaVersion": 1, "sourceAddons": [self.addon]}), encoding="utf-8")
        patch = self.root / self.addon["patches"][0]
        patch.write_bytes(patch.read_bytes().replace(b'"upstream"', b'"different source"'))
        with self.assertRaisesRegex(ValueError, "Cannot apply or read the pinned Zygor source"):
            packaging.package(self.root, self.output, self.archive)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
