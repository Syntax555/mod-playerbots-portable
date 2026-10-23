"""Offline installation, integrity and preservation checks for the Questie installer."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "client-addon/questie-installer/Install-Questie.ps1"
POWERSHELL = os.environ.get("POWERSHELL_EXECUTABLE") or shutil.which("powershell.exe") or shutil.which("pwsh")
REVISION = "a" * 40
ORIGINAL = b'local progress = "upstream"\nreturn progress\n'
PATCHED = b'local progress = "playerbots"\nreturn progress\n'


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value) -> bytes:
    content = (json.dumps(value, indent=2) + "\n").encode()
    path.write_bytes(content)
    return content


class InstallationFixture:
    def __init__(self, root: Path):
        self.root = root
        self.package = root / "installer"
        self.package.mkdir()
        self.script = self.package / "Install-Questie.ps1"
        shutil.copyfile(INSTALLER, self.script)
        self.addons = root / "WoW/Interface/AddOns"
        self.target = self.addons / "Questie-335"
        self.target.mkdir(parents=True)
        (self.target / "old.lua").write_bytes(b"existing user addon\n")
        self.saved = root / "WoW/WTF/Account/example/SavedVariables/Questie.lua"
        self.saved.parent.mkdir(parents=True)
        self.saved.write_bytes(b"existing account settings\n")
        self.archive = root / "upstream.zip"
        self.files = {"Questie-335.toc": b"## Interface: 30300\nMain.lua\n",
                      "Main.lua": ORIGINAL, "Icons/LICENSE.md": b"Preserve upstream notice\n"}
        self.patch_data = {"schemaVersion": 1, "files": [{
            "path": "Main.lua", "beforeSha256": digest(ORIGINAL), "afterSha256": digest(PATCHED),
            "hunks": [{"start": 0, "deleteCount": 1, "lines": ['local progress = "playerbots"']}],
        }]}
        self.manifest = {
            "schemaVersion": 1, "name": "Questie-335", "repository": "https://github.com/Aldori15/Questie.git",
            "revision": REVISION, "interface": 30300,
            "sourceArchive": {"url": f"https://github.com/Aldori15/Questie/archive/{REVISION}.zip", "sha256": ""},
            "patches": {"patches/questie-playerbots-progress.patch": digest(b"fixture source patch\n")},
            "patchDataSha256": "",
        }
        self.write_archive()
        self.write_metadata()

    def write_archive(self, extra=None, *, update_hash=True):
        with zipfile.ZipFile(self.archive, "w") as archive:
            for relative, content in self.files.items():
                archive.writestr(f"Questie-{REVISION}/{relative}", content)
            for relative, content in (extra or {}).items():
                archive.writestr(relative, content)
        if update_hash:
            self.manifest["sourceArchive"]["sha256"] = digest(self.archive.read_bytes())

    def write_metadata(self):
        content = write_json(self.package / "PATCH_DATA.json", self.patch_data)
        self.manifest["patchDataSha256"] = digest(content)
        write_json(self.package / "SOURCE_MANIFEST.json", self.manifest)

    def install(self):
        return subprocess.run([POWERSHELL, "-NoProfile", "-File", str(self.script),
                               "-AddOnsPath", str(self.addons), "-SourceArchive", str(self.archive)],
                              text=True, capture_output=True, check=False, timeout=30)

    def remove_gate(self, value):
        source = self.script.read_text()
        if source.count(value) != 1:
            raise AssertionError(f"Expected exactly one production integrity gate: {value}")
        self.script.write_text(source.replace(value, "# integrity gate removed by mutation fixture"))


@unittest.skipUnless(POWERSHELL, "PowerShell is required for offline Questie installation checks")
class QuestieInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="questie-installation-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = InstallationFixture(self.root)

    def rejected_without_changes(self):
        result = self.fixture.install()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.fixture.target / "old.lua").read_bytes(), b"existing user addon\n")
        self.assertEqual(self.fixture.saved.read_bytes(), b"existing account settings\n")
        self.assertEqual(sorted(path.name for path in self.fixture.addons.iterdir()), ["Questie-335"])
        return result

    def test_installs_patched_addon_and_preserves_old_folder_and_saved_variables(self):
        result = self.fixture.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.fixture.target / "Main.lua").read_bytes(), PATCHED)
        self.assertEqual((self.fixture.target / "Icons/LICENSE.md").read_bytes(), b"Preserve upstream notice\n")
        self.assertEqual((self.fixture.target / "SOURCE_REVISION.txt").read_text(), REVISION + "\n")
        self.assertEqual(json.loads((self.fixture.target / "SOURCE_MANIFEST.json").read_text()), self.fixture.manifest)
        backups = list(self.fixture.addons.glob("Questie-335.backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "old.lua").read_bytes(), b"existing user addon\n")
        self.assertEqual(self.fixture.saved.read_bytes(), b"existing account settings\n")
        self.assertFalse(list(self.fixture.addons.glob(".Questie-install-*")))

    def test_archive_hash_failure_preserves_the_installed_addon(self):
        self.fixture.files["Icons/LICENSE.md"] = b"unexpected source change\n"
        self.fixture.write_archive(update_hash=False)
        self.assertIn("source archive failed", self.rejected_without_changes().stderr)
        self.fixture.remove_gate("    Assert-Hash $manifest.sourceArchive.sha256 ([System.IO.File]::ReadAllBytes($archivePath)) 'Questie source archive'")
        result = self.fixture.install()
        self.assertEqual(result.returncode, 0, "Archive integrity mutation was not exercised: " + result.stderr)

    def test_replacement_failure_restores_the_previous_addon(self):
        operation = '    try { [System.IO.Directory]::Move($payload, $target) }'
        source = self.fixture.script.read_text()
        self.assertEqual(source.count(operation), 1)
        self.fixture.script.write_text(source.replace(operation, "    try { throw 'fixture replacement failure' }"))
        self.assertIn("fixture replacement failure", self.rejected_without_changes().stderr)

    def test_installs_into_an_empty_addon_folder_without_a_backup(self):
        shutil.rmtree(self.fixture.target)
        result = self.fixture.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.fixture.target / "Main.lua").read_bytes(), PATCHED)
        self.assertEqual(sorted(path.name for path in self.fixture.addons.iterdir()), ["Questie-335"])

    def test_reconstructs_multiple_insertions_deletions_and_utf8_lines(self):
        original = b"first\nremove\nlast\n"
        patched = "prefix\nfirst\nGrüße\ntail\n".encode()
        self.fixture.files["Main.lua"] = original
        file = self.fixture.patch_data["files"][0]
        file.update(beforeSha256=digest(original), afterSha256=digest(patched), hunks=[
            {"start": 0, "deleteCount": 0, "lines": ["prefix"]},
            {"start": 1, "deleteCount": 1, "lines": []},
            {"start": 2, "deleteCount": 1, "lines": ["Grüße", "tail"]},
        ])
        self.fixture.write_archive()
        self.fixture.write_metadata()
        result = self.fixture.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.fixture.target / "Main.lua").read_bytes(), patched)

    def test_patch_data_hash_failure_is_detected(self):
        with (self.fixture.package / "PATCH_DATA.json").open("ab") as output:
            output.write(b"\n")
        self.assertIn("patch data failed", self.rejected_without_changes().stderr)
        self.fixture.remove_gate("    Assert-Hash $manifest.patchDataSha256 $patchBytes 'Questie patch data'")
        result = self.fixture.install()
        self.assertEqual(result.returncode, 0, "Patch integrity mutation was not exercised: " + result.stderr)

    def test_original_file_hash_failure_is_detected(self):
        self.fixture.files["Main.lua"] = ORIGINAL.replace(b"upstream", b"other source")
        self.fixture.write_archive()
        self.fixture.write_metadata()
        self.assertIn("Original Questie file Main.lua failed", self.rejected_without_changes().stderr)
        self.fixture.remove_gate('        Assert-Hash $file.beforeSha256 $original "Original Questie file $relative"')
        result = self.fixture.install()
        self.assertEqual(result.returncode, 0, "Original file integrity mutation was not exercised: " + result.stderr)

    def test_patched_file_hash_failure_is_detected(self):
        self.fixture.patch_data["files"][0]["afterSha256"] = "0" * 64
        self.fixture.write_metadata()
        self.assertIn("Patched Questie file Main.lua failed", self.rejected_without_changes().stderr)
        self.fixture.remove_gate('        Assert-Hash $file.afterSha256 $patched "Patched Questie file $relative"')
        result = self.fixture.install()
        self.assertEqual(result.returncode, 0, "Patched file integrity mutation was not exercised: " + result.stderr)

    def test_rejects_archive_traversal_case_collisions_foreign_roots_and_links(self):
        cases = (
            {f"Questie-{REVISION}/../escape.lua": b"escape"},
            {f"Questie-{REVISION}/MAIN.lua": b"case collision"},
            {"other-project/Main.lua": b"wrong root"},
        )
        for extra in cases:
            with self.subTest(path=next(iter(extra))):
                self.fixture.write_archive(extra)
                self.fixture.write_metadata()
                self.rejected_without_changes()
                self.assertFalse((self.fixture.addons / "escape.lua").exists())
        self.fixture.write_archive()
        with zipfile.ZipFile(self.fixture.archive, "a") as archive:
            entry = zipfile.ZipInfo(f"Questie-{REVISION}/linked.lua")
            entry.create_system = 3
            entry.external_attr = 0o120777 << 16
            archive.writestr(entry, "Main.lua")
        self.fixture.manifest["sourceArchive"]["sha256"] = digest(self.fixture.archive.read_bytes())
        self.fixture.write_metadata()
        self.assertIn("Linked file", self.rejected_without_changes().stderr)

    def test_rejects_wrong_toc_missing_assets_and_out_of_range_patch_data(self):
        self.fixture.files["Questie-335.toc"] = b"## Interface: 11500\nMain.lua\n"
        self.fixture.write_archive()
        self.fixture.write_metadata()
        self.assertIn("interface version", self.rejected_without_changes().stderr)
        self.fixture.files["Questie-335.toc"] = b"## Interface: 30300\nMissing.lua\n"
        self.fixture.write_archive()
        self.fixture.write_metadata()
        self.assertIn("Missing Questie TOC asset", self.rejected_without_changes().stderr)
        self.fixture.files["Questie-335.toc"] = b"## Interface: 30300\nMain.lua\n"
        self.fixture.write_archive()
        self.fixture.patch_data["files"][0]["hunks"][0]["start"] = 9999
        self.fixture.write_metadata()
        self.assertIn("out-of-range", self.rejected_without_changes().stderr)


if __name__ == "__main__":
    unittest.main()
