"""Verify installer release contents against pinned original sources and patches."""
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
SPEC = importlib.util.spec_from_file_location("questie_packaging", ROOT / "cmake/PackageQuestieInstaller.py")
packaging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packaging)
POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh")


def git(repository: Path, *arguments: str) -> bytes:
    return subprocess.run(["git", "-C", str(repository), *arguments], check=True,
                          capture_output=True).stdout


class QuestieInstallerPackagingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="questie-packaging-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cache = self.root / ".module-cache/client-addon-Questie-335"
        self.cache.mkdir(parents=True)
        git(self.cache, "init", "--quiet")
        git(self.cache, "config", "user.name", "Fixture")
        git(self.cache, "config", "user.email", "test@example.invalid")
        git(self.cache, "config", "core.autocrlf", "false")
        self.files = {"Questie-335.toc": b"## Interface: 30300\nMain.lua\n",
                      "Main.lua": b'local progress = "upstream"\nreturn progress\n',
                      "Icons/unknown.tga": b"upstream icon; do not redistribute\n"}
        for relative, content in self.files.items():
            path = self.cache / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        git(self.cache, "add", ".")
        git(self.cache, "commit", "--quiet", "-m", "Pinned fixture")
        revision = git(self.cache, "rev-parse", "HEAD").decode().strip()
        (self.cache / "Main.lua").write_bytes(self.files["Main.lua"].replace(b"upstream", b"playerbots"))
        self.expected = (self.cache / "Main.lua").read_bytes()
        patch = self.root / "patches/questie-playerbots-progress.patch"
        patch.parent.mkdir()
        patch.write_bytes(git(self.cache, "diff", "--", "Main.lua"))
        git(self.cache, "checkout", "--", "Main.lua")
        self.addon = {"name": "Questie-335", "url": "https://github.com/Aldori15/Questie.git",
                      "revision": revision, "interface": 30300, "toc": "Questie-335.toc",
                      "patches": [patch.relative_to(self.root).as_posix()]}
        self.archive = self.root / "original.zip"
        self.output = self.root / "output/Questie-335-latest.zip"
        self.write_archive()
        self.installer = self.root / "client-addon/questie-installer"
        shutil.copytree(ROOT / "client-addon/questie-installer", self.installer)
        shutil.copyfile(ROOT / "LICENSE", self.root / "LICENSE")

    def write_archive(self, extra=None):
        with zipfile.ZipFile(self.archive, "w") as archive:
            for relative, value in self.files.items():
                archive.writestr(f"Questie-{self.addon['revision']}/{relative}", value)
            for relative, value in (extra or {}).items():
                archive.writestr(relative, value)
        self.addon["archiveSha256"] = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        (self.root / "versions.lock.json").write_text(
            json.dumps({"schemaVersion": 1, "sourceAddons": [self.addon]}), encoding="utf-8")

    def test_package_contains_installer_and_verified_changes_without_upstream_addon(self):
        packaging.package(self.root, self.output, self.archive)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(set(archive.namelist()), packaging.PACKAGE_FILES)
            manifest = json.loads(archive.read("SOURCE_MANIFEST.json"))
            changes = archive.read("PATCH_DATA.json")
            self.assertEqual(manifest["patchDataSha256"], hashlib.sha256(changes).hexdigest())
            self.assertEqual(manifest["sourceArchive"]["sha256"], self.addon["archiveSha256"])
            self.assertEqual(manifest["revision"], self.addon["revision"])
            files = json.loads(changes)["files"]
            self.assertEqual([file["path"] for file in files], ["Main.lua"])
            self.assertEqual(files[0]["beforeSha256"], hashlib.sha256(self.files["Main.lua"]).hexdigest())
            self.assertEqual(files[0]["afterSha256"], hashlib.sha256(self.expected).hexdigest())
            self.assertNotIn(b"upstream icon; do not redistribute", b"".join(archive.read(name) for name in archive.namelist()))
        first = self.output.read_bytes()
        packaging.package(self.root, self.output, self.archive)
        self.assertEqual(self.output.read_bytes(), first)

    def test_patch_data_preserves_bytes_despite_git_line_ending_settings(self):
        def verify(module):
            file = module.patch_data(self.root, self.addon, self.archive)["files"][0]
            self.assertEqual(file["afterSha256"], hashlib.sha256(self.expected).hexdigest())
            lines = self.files["Main.lua"].decode("utf-8").split("\n")
            for hunk in reversed(file["hunks"]):
                lines[hunk["start"]:hunk["start"] + hunk["deleteCount"]] = hunk["lines"]
            self.assertEqual("\n".join(lines).encode("utf-8"), self.expected)

        environment = {"GIT_CONFIG_COUNT": "2",
                       "GIT_CONFIG_KEY_0": "core.autocrlf", "GIT_CONFIG_VALUE_0": "true",
                       "GIT_CONFIG_KEY_1": "core.eol", "GIT_CONFIG_VALUE_1": "crlf"}
        with mock.patch.dict(os.environ, environment):
            verify(packaging)
            source = Path(SPEC.origin).read_text(encoding="utf-8")
            setting = '"-c", "core.autocrlf=false", '
            self.assertEqual(source.count(setting), 1)
            mutated_path = self.root / "PackageQuestieInstaller.py"
            mutated_path.write_text(source.replace(setting, ""), encoding="utf-8")
            mutated_spec = importlib.util.spec_from_file_location("questie_packaging_mutated", mutated_path)
            mutated = importlib.util.module_from_spec(mutated_spec)
            mutated_spec.loader.exec_module(mutated)
            with self.assertRaises(AssertionError):
                verify(mutated)

    @unittest.skipUnless(POWERSHELL, "PowerShell is required to exercise the packaged installer")
    def test_generated_package_installs_the_changes_without_external_patch_files(self):
        packaging.package(self.root, self.output, self.archive)
        extracted = self.root / "downloaded-installer"
        with zipfile.ZipFile(self.output) as archive:
            archive.extractall(extracted)
        addons = self.root / "WoW/Interface/AddOns"
        addons.mkdir(parents=True)
        result = subprocess.run([POWERSHELL, "-NoProfile", "-File", str(extracted / "Install-Questie.ps1"),
                                 "-AddOnsPath", str(addons), "-SourceArchive", str(self.archive)],
                                capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((addons / "Questie-335/Main.lua").read_bytes(), self.expected)
        self.assertEqual((addons / "Questie-335/Icons/unknown.tga").read_bytes(), self.files["Icons/unknown.tga"])

    def test_corrupt_archive_preserves_existing_verified_package(self):
        self.output.parent.mkdir()
        self.output.write_bytes(b"previous verified package")
        with self.archive.open("ab") as archive:
            archive.write(b"changed upstream archive")
        with self.assertRaisesRegex(ValueError, "pinned SHA-256"):
            packaging.package(self.root, self.output, self.archive)
        self.assertEqual(self.output.read_bytes(), b"previous verified package")

    def test_changed_original_cannot_be_relabelled_as_the_pinned_git_commit(self):
        self.files["Main.lua"] += b"-- changed outside patch context\n"
        self.write_archive()
        with self.assertRaisesRegex(ValueError, "differs from the pinned Git source"):
            packaging.package(self.root, self.output, self.archive)
        self.assertFalse(self.output.exists())

    def test_rejects_inapplicable_patch_and_unsafe_archive_before_writing_package(self):
        patch = self.root / self.addon["patches"][0]
        original = patch.read_bytes()
        patch.write_bytes(original.replace(b'"upstream"', b'"different source"'))
        with self.assertRaisesRegex(ValueError, "Cannot reconstruct"):
            packaging.package(self.root, self.output, self.archive)
        self.assertFalse(self.output.exists())
        patch.write_bytes(original)
        self.write_archive({f"Questie-{self.addon['revision']}/../escaped.lua": b"escape"})
        with self.assertRaisesRegex(ValueError, "Unsafe Questie source archive path"):
            packaging.package(self.root, self.output, self.archive)
        self.assertFalse(self.output.exists())
        self.assertFalse((self.root / "escaped.lua").exists())


if __name__ == "__main__":
    unittest.main()
