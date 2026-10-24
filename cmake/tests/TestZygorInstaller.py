"""Offline installation, integrity and preservation checks for the Zygor Individual Progression installer."""
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
INSTALLER = ROOT / "client-addon/zygor-installer/Install-Zygor.ps1"
POWERSHELL = os.environ.get("POWERSHELL_EXECUTABLE") or shutil.which("powershell.exe") or shutil.which("pwsh")
NAME = "ZygorGuidesViewerRM"
REVISION = "b" * 40
ROOT_PREFIX = f"ZygorGuidesRemaster-3.3.5a_WOTLK-{REVISION}/"
ORIGINAL = b'local tier = "upstream"\nreturn tier\n'
PATCHED = b'local tier = "earned"\nreturn tier\n'
CREATED = b"-- Individual Progression\nreturn true\n"


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
        self.script = self.package / "Install-Zygor.ps1"
        shutil.copyfile(INSTALLER, self.script)
        self.addons = root / "WoW/Interface/AddOns"
        self.target = self.addons / NAME
        self.target.mkdir(parents=True)
        (self.target / "old.lua").write_bytes(b"existing user addon\n")
        self.saved = root / "WoW/WTF/Account/example/SavedVariables/ZygorGuidesViewerRM.lua"
        self.saved.parent.mkdir(parents=True)
        self.saved.write_bytes(b"existing account settings\n")
        self.archive = root / "upstream.zip"
        # The client loads TOC paths without regard to case, as the real addon's TOC relies on.
        self.files = {f"{NAME}.toc": b"## Interface: 30300\nLibs\\LibStub\\LibStub.lua\nMain.lua\nIndividualProgression.lua\n",
                      "libs/LibStub/LibStub.lua": b"return true\n", "Main.lua": ORIGINAL,
                      "Skin/notice.txt": b"Preserve upstream notice\n"}
        self.repository_files = {"README.md": b"repository readme\n", "tools/test_main.lua": b"assert(true)\n"}
        self.patch_data = {"schemaVersion": 1, "files": [
            {"path": "IndividualProgression.lua", "created": True, "afterSha256": digest(CREATED),
             "hunks": [{"start": 0, "deleteCount": 1, "lines": ["-- Individual Progression", "return true", ""]}]},
            {"path": "Main.lua", "beforeSha256": digest(ORIGINAL), "afterSha256": digest(PATCHED),
             "hunks": [{"start": 0, "deleteCount": 1, "lines": ['local tier = "earned"']}]},
        ]}
        self.manifest = {
            "schemaVersion": 1, "name": NAME,
            "repository": "https://github.com/ErebusAres/ZygorGuidesRemaster-3.3.5a_WOTLK.git",
            "revision": REVISION, "interface": 30300,
            "sourceArchive": {"url": f"https://github.com/ErebusAres/ZygorGuidesRemaster-3.3.5a_WOTLK/archive/{REVISION}.zip",
                              "root": ROOT_PREFIX + NAME},
            "patches": {"patches/zygor-individual-progression.patch": digest(b"fixture source patch\n")},
            "patchDataSha256": "", "upstreamFilesSha256": "",
        }
        self.write_archive()
        self.write_metadata()

    def write_archive(self, extra=None, skip=()):
        with zipfile.ZipFile(self.archive, "w") as archive:
            for relative, content in self.repository_files.items():
                archive.writestr(ROOT_PREFIX + relative, content)
            for relative, content in self.files.items():
                if relative not in skip:
                    archive.writestr(f"{ROOT_PREFIX}{NAME}/{relative}", content)
            for relative, content in (extra or {}).items():
                archive.writestr(relative, content)

    def write_metadata(self, upstream=None):
        content = write_json(self.package / "PATCH_DATA.json", self.patch_data)
        self.manifest["patchDataSha256"] = digest(content)
        files = upstream if upstream is not None else {path: digest(value) for path, value in self.files.items()}
        listing = write_json(self.package / "UPSTREAM_FILES.json", {"schemaVersion": 1, "root": NAME, "files": files})
        self.manifest["upstreamFilesSha256"] = digest(listing)
        write_json(self.package / "SOURCE_MANIFEST.json", self.manifest)

    def install(self):
        return subprocess.run([POWERSHELL, "-NoProfile", "-File", str(self.script),
                               "-AddOnsPath", str(self.addons), "-SourceArchive", str(self.archive)],
                              text=True, capture_output=True, check=False, timeout=60)

    def remove_gate(self, value):
        source = self.script.read_text()
        if source.count(value) != 1:
            raise AssertionError(f"Expected exactly one production integrity gate: {value}")
        self.script.write_text(source.replace(value, "# integrity gate removed by mutation fixture"))


@unittest.skipUnless(POWERSHELL, "PowerShell is required for offline Zygor installation checks")
class ZygorInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="zygor-installation-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = InstallationFixture(self.root)

    def rejected_without_changes(self):
        result = self.fixture.install()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.fixture.target / "old.lua").read_bytes(), b"existing user addon\n")
        self.assertEqual(self.fixture.saved.read_bytes(), b"existing account settings\n")
        self.assertEqual(sorted(path.name for path in self.fixture.addons.iterdir()), [NAME])
        return result

    def mutation_accepted(self, gate):
        self.fixture.remove_gate(gate)
        result = self.fixture.install()
        self.assertEqual(result.returncode, 0, "Integrity mutation was not exercised: " + result.stderr)

    def test_installs_patched_addon_and_preserves_old_folder_and_saved_variables(self):
        result = self.fixture.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        target = self.fixture.target
        self.assertEqual((target / "Main.lua").read_bytes(), PATCHED)
        self.assertEqual((target / "IndividualProgression.lua").read_bytes(), CREATED)
        self.assertEqual((target / "Skin/notice.txt").read_bytes(), b"Preserve upstream notice\n")
        self.assertEqual((target / "SOURCE_REVISION.txt").read_text(), REVISION + "\n")
        self.assertEqual(json.loads((target / "SOURCE_MANIFEST.json").read_text()), self.fixture.manifest)
        self.assertFalse((target / "README.md").exists() or (target / "tools").exists() or (target / "old.lua").exists())
        backups = list(self.fixture.addons.glob(NAME + ".backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "old.lua").read_bytes(), b"existing user addon\n")
        self.assertEqual(self.fixture.saved.read_bytes(), b"existing account settings\n")
        self.assertFalse(list(self.fixture.addons.glob(".Zygor-install-*")))

    def test_installs_into_an_empty_addon_folder_and_warns_about_standalone_copies(self):
        shutil.rmtree(self.fixture.target)
        (self.fixture.addons / "ZygorTalentAdvisor").mkdir()
        result = self.fixture.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.fixture.target / "Main.lua").read_bytes(), PATCHED)
        self.assertIn("ZygorTalentAdvisor", result.stdout + result.stderr)
        self.assertEqual(sorted(path.name for path in self.fixture.addons.iterdir()), [NAME, "ZygorTalentAdvisor"])

    def test_replacement_failure_restores_the_previous_addon(self):
        operation = '    try { [System.IO.Directory]::Move($payload, $target) }'
        source = self.fixture.script.read_text()
        self.assertEqual(source.count(operation), 1)
        self.fixture.script.write_text(source.replace(operation, "    try { throw 'fixture replacement failure' }"))
        self.assertIn("fixture replacement failure", self.rejected_without_changes().stderr)

    def test_changed_upstream_file_is_detected(self):
        self.fixture.files["Skin/notice.txt"] = b"unexpected source change\n"
        self.fixture.write_archive()
        self.assertIn("Upstream Zygor file Skin/notice.txt failed", self.rejected_without_changes().stderr)
        self.mutation_accepted('            Assert-Hash $Expected[$relative] ([System.IO.File]::ReadAllBytes($target)) "Upstream Zygor file $relative"')

    def test_extra_and_missing_upstream_files_are_detected(self):
        self.fixture.write_archive({f"{ROOT_PREFIX}{NAME}/Injected.lua": b"injected"})
        self.assertIn("Unexpected file in the Zygor archive: Injected.lua", self.rejected_without_changes().stderr)
        self.fixture.write_archive(skip=("Skin/notice.txt",))
        self.assertIn("missing files", self.rejected_without_changes().stderr)
        self.mutation_accepted("    if ($found.Count -ne $Expected.Count) { throw 'The Zygor archive is missing files of the pinned version.' }")

    def test_metadata_hash_failures_are_detected(self):
        with (self.fixture.package / "PATCH_DATA.json").open("ab") as output:
            output.write(b"\n")
        self.assertIn("patch data failed", self.rejected_without_changes().stderr)
        self.fixture.write_metadata()
        with (self.fixture.package / "UPSTREAM_FILES.json").open("ab") as output:
            output.write(b"\n")
        self.assertIn("upstream file list failed", self.rejected_without_changes().stderr)
        self.mutation_accepted("    Assert-Hash $manifest.upstreamFilesSha256 $filesBytes 'Zygor upstream file list'")

    def test_original_and_patched_file_hash_failures_are_detected(self):
        self.fixture.files["Main.lua"] = ORIGINAL.replace(b"upstream", b"other source")
        self.fixture.write_archive()
        self.fixture.write_metadata()
        self.assertIn("Original Zygor file Main.lua failed", self.rejected_without_changes().stderr)
        self.fixture.files["Main.lua"] = ORIGINAL
        self.fixture.write_archive()
        self.fixture.patch_data["files"][1]["afterSha256"] = "0" * 64
        self.fixture.write_metadata()
        self.assertIn("Patched Zygor file Main.lua failed", self.rejected_without_changes().stderr)
        self.mutation_accepted('        Assert-Hash $file.afterSha256 $patched "Patched Zygor file $relative"')

    def test_new_files_cannot_replace_upstream_files(self):
        self.fixture.patch_data["files"][0]["path"] = "Skin/notice.txt"
        self.fixture.write_metadata()
        self.assertIn("A new Zygor file already exists", self.rejected_without_changes().stderr)

    def test_rejects_archive_traversal_case_collisions_foreign_roots_and_links(self):
        cases = (
            {f"{ROOT_PREFIX}../escape.lua": b"escape"},
            {f"{ROOT_PREFIX}{NAME}/MAIN.lua": b"case collision"},
            {"other-project/Main.lua": b"wrong root"},
        )
        for extra in cases:
            with self.subTest(path=next(iter(extra))):
                self.fixture.write_archive(extra)
                self.rejected_without_changes()
                self.assertFalse((self.fixture.addons / "escape.lua").exists())
        self.fixture.write_archive()
        with zipfile.ZipFile(self.fixture.archive, "a") as archive:
            entry = zipfile.ZipInfo(f"{ROOT_PREFIX}{NAME}/linked.lua")
            entry.create_system = 3
            entry.external_attr = 0o120777 << 16
            archive.writestr(entry, "Main.lua")
        self.assertIn("Linked file", self.rejected_without_changes().stderr)

    def test_rejects_wrong_toc_missing_assets_and_out_of_range_patch_data(self):
        toc = f"{NAME}.toc"
        for content, message in ((b"## Interface: 11500\nMain.lua\n", "interface version"),
                                 (b"## Interface: 30300\nMissing.lua\n", "Missing Zygor TOC asset")):
            with self.subTest(message=message):
                self.fixture.files[toc] = content
                self.fixture.write_archive()
                self.fixture.write_metadata()
                self.assertIn(message, self.rejected_without_changes().stderr)
        self.fixture.files[toc] = b"## Interface: 30300\nMain.lua\n"
        self.fixture.write_archive()
        self.fixture.patch_data["files"][1]["hunks"][0]["start"] = 9999
        self.fixture.write_metadata()
        self.assertIn("out-of-range", self.rejected_without_changes().stderr)

    def test_toc_paths_match_without_regard_to_case(self):
        source = self.fixture.script.read_text()
        folded = "$files = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)"
        self.assertEqual(source.count(folded), 1)
        self.fixture.script.write_text(source.replace(folded, folded.replace("OrdinalIgnoreCase", "Ordinal")))
        self.assertIn("Missing Zygor TOC asset: Libs/LibStub/LibStub.lua", self.rejected_without_changes().stderr)


if __name__ == "__main__":
    unittest.main()
