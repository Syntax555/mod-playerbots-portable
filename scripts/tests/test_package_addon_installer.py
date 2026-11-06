"""Offline installation, integrity and packaging checks for the shared addon installer.

Run with: python3 -m unittest discover -s scripts/tests -p 'test_*.py'
Set POWERSHELL_EXECUTABLE to test a particular PowerShell.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
PACKAGER = ROOT / "scripts/package_addon_installer.py"
_spec = importlib.util.spec_from_file_location("package_addon_installer", PACKAGER)
PACKAGE = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(PACKAGE)
NAME, SHORT, TITLE = "Example-Addon", "Example", "Example Addon"
SCRIPTS = PACKAGE.installer_scripts(NAME, SHORT, TITLE, [])
INSTALLER = Path(f"Install-{SHORT}.ps1")
POWERSHELL = os.environ.get("POWERSHELL_EXECUTABLE") or shutil.which("powershell.exe") or shutil.which("pwsh")
REVISION = "a" * 40
REPOSITORY = "https://github.com/Example/Addon-Fork"
MAIN = b'local progress = "fork"\nreturn progress\n'


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value) -> bytes:
    content = (json.dumps(value, indent=2) + "\n").encode()
    path.write_bytes(content)
    return content


def git(directory: Path, *arguments: str) -> str:
    return subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "user.name=Fixture", "-c", "user.email=f@example.invalid",
                           "-C", str(directory), *arguments], check=True, capture_output=True, text=True).stdout


class InstallationFixture:
    def __init__(self, root: Path, path: str = ""):
        self.root = root
        self.path = path
        self.package = root / "installer"
        self.package.mkdir()
        self.script = self.package / INSTALLER.name
        self.script.write_bytes(SCRIPTS[INSTALLER.name])
        self.addons = root / "WoW/Interface/AddOns"
        self.target = self.addons / NAME
        self.target.mkdir(parents=True)
        (self.target / "old.lua").write_bytes(b"existing user addon\n")
        self.saved = root / f"WoW/WTF/Account/example/SavedVariables/{NAME}.lua"
        self.saved.parent.mkdir(parents=True)
        self.saved.write_bytes(b"existing account settings\n")
        self.archive = root / "source.zip"
        self.archive_root = f"Addon-Fork-{REVISION}/"
        self.files = {f"{NAME}.toc": b"## Interface: 30300\nMain.lua\n", "Main.lua": MAIN,
                      "Icons/LICENSE.md": b"Preserve upstream notice\n"}
        # Repository content outside the installed addon.
        self.outside = {".github/workflows/latest.yml": b"name: Latest\n", ".github/installer/README.md": b"tooling\n"}
        if path:
            self.outside["tools/build.py"] = b"print('tooling')\n"
        self.listed = None
        self.manifest = {
            "schemaVersion": 2, "name": NAME, "repository": REPOSITORY, "revision": REVISION, "interface": 30300,
            "sourceArchive": {"url": f"{REPOSITORY}/archive/{REVISION}.zip", "root": self.archive_root, "path": path},
            "addonFilesSha256": "",
        }
        self.write_archive()
        self.write_metadata()

    def write_archive(self, extra=None):
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr(self.archive_root, b"")
            for relative, content in self.files.items():
                archive.writestr(self.archive_root + self.path + relative, content)
            for relative, content in self.outside.items():
                archive.writestr(self.archive_root + relative, content)
            for relative, content in (extra or {}).items():
                archive.writestr(relative, content)

    def write_metadata(self, files=None):
        listed = {"schemaVersion": 1, "root": NAME,
                  "files": {relative: digest(value) for relative, value in (files or self.files).items()}}
        content = write_json(self.package / "ADDON_FILES.json", listed)
        self.manifest["addonFilesSha256"] = digest(content)
        write_json(self.package / "SOURCE_MANIFEST.json", self.manifest)

    def install(self):
        return subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.script),
                               "-AddOnsPath", str(self.addons), "-SourceArchive", str(self.archive)],
                              text=True, capture_output=True, check=False, timeout=60)

    def remove_gate(self, value):
        source = self.script.read_text(encoding="utf-8")
        if source.count(value) != 1:
            raise AssertionError(f"Expected exactly one production integrity gate: {value}")
        self.script.write_text(source.replace(value, "# integrity gate removed by mutation fixture"), encoding="utf-8")


@unittest.skipUnless(POWERSHELL, "PowerShell is required for offline installation checks")
class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="addon-installation-")
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

    def assert_installed(self, fixture):
        installed = {path.relative_to(fixture.target).as_posix(): path.read_bytes()
                     for path in fixture.target.rglob("*") if path.is_file()}
        self.assertEqual(installed.pop("SOURCE_REVISION.txt"), (REVISION + "\n").encode())
        self.assertEqual(json.loads(installed.pop("SOURCE_MANIFEST.json")), fixture.manifest)
        self.assertEqual(installed, fixture.files, "exactly the listed addon files, without repository tooling")

    def test_installs_the_fork_and_preserves_old_folder_and_saved_variables(self):
        result = self.fixture.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_installed(self.fixture)
        backups = list(self.fixture.addons.glob(f"{NAME}.backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "old.lua").read_bytes(), b"existing user addon\n")
        self.assertEqual(self.fixture.saved.read_bytes(), b"existing account settings\n")
        self.assertFalse(list(self.fixture.addons.glob(f".{NAME}-install-*")))

    def test_installs_an_addon_folder_inside_the_repository(self):
        root = self.root / "nested"
        root.mkdir()
        fixture = InstallationFixture(root, f"{NAME}/")
        result = fixture.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_installed(fixture)

    def test_installs_into_an_empty_addon_folder_without_a_backup(self):
        shutil.rmtree(self.fixture.target)
        result = self.fixture.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.fixture.target / "Main.lua").read_bytes(), MAIN)
        self.assertEqual(sorted(path.name for path in self.fixture.addons.iterdir()), [NAME])

    def test_changed_file_fails_its_hash_check(self):
        self.fixture.files["Main.lua"] = MAIN.replace(b"fork", b"tampered")
        self.fixture.write_archive()
        self.assertIn("file Main.lua failed", self.rejected_without_changes().stderr)
        self.fixture.remove_gate('            Assert-Hash $Expected[$relative] ([System.IO.File]::ReadAllBytes($target)) "$title file $relative"')
        result = self.fixture.install()
        self.assertEqual(result.returncode, 0, "File integrity mutation was not exercised: " + result.stderr)

    def test_changed_file_list_fails_its_hash_check(self):
        with (self.fixture.package / "ADDON_FILES.json").open("ab") as output:
            output.write(b"\n")
        self.assertIn("file list failed", self.rejected_without_changes().stderr)
        self.fixture.remove_gate('    Assert-Hash $manifest.addonFilesSha256 $filesBytes "$title file list"')
        result = self.fixture.install()
        self.assertEqual(result.returncode, 0, "File list integrity mutation was not exercised: " + result.stderr)

    def test_listed_file_missing_from_the_archive_is_rejected(self):
        self.fixture.write_metadata(dict(self.fixture.files, **{"Extra.lua": b"listed but absent\n"}))
        self.assertIn("missing files", self.rejected_without_changes().stderr)
        self.fixture.remove_gate('    if ($found.Count -ne $Expected.Count) { throw "The $title archive is missing files of the packaged version." }')
        result = self.fixture.install()
        self.assertEqual(result.returncode, 0, "Completeness mutation was not exercised: " + result.stderr)

    def test_unlisted_file_in_the_addon_folder_is_rejected(self):
        self.fixture.write_archive({self.fixture.archive_root + "Injected.lua": b"not in the Git tree\n"})
        self.assertIn("Unexpected file", self.rejected_without_changes().stderr)

    def test_manifest_must_name_this_addon_and_a_matching_github_archive(self):
        cases = (("repository", "https://example.com/Example/Addon-Fork"),
                 ("name", "Other"),
                 ("sourceArchive", dict(self.fixture.manifest["sourceArchive"],
                                        url=f"https://github.com/Other/Addon-Fork/archive/{REVISION}.zip")),
                 ("sourceArchive", dict(self.fixture.manifest["sourceArchive"], root="Addon-Fork-other/")),
                 ("sourceArchive", dict(self.fixture.manifest["sourceArchive"], path="../")))
        original = json.loads(json.dumps(self.fixture.manifest))
        for key, value in cases:
            with self.subTest(key=key, value=value):
                self.fixture.manifest = dict(original, **{key: value})
                write_json(self.fixture.package / "SOURCE_MANIFEST.json", self.fixture.manifest)
                self.assertIn("invalid", self.rejected_without_changes().stderr)

    def test_replacement_failure_restores_the_previous_addon(self):
        operation = '    try { [System.IO.Directory]::Move($payload, $target) }'
        source = self.fixture.script.read_text(encoding="utf-8")
        self.assertEqual(source.count(operation), 1)
        self.fixture.script.write_text(source.replace(operation, "    try { throw 'fixture replacement failure' }"),
                                       encoding="utf-8")
        self.assertIn("fixture replacement failure", self.rejected_without_changes().stderr)

    def test_rejects_archive_traversal_case_collisions_foreign_roots_and_links(self):
        cases = (
            {self.fixture.archive_root + "../escape.lua": b"escape"},
            {self.fixture.archive_root + "MAIN.lua": b"case collision"},
            {"other-project/Main.lua": b"wrong root"},
        )
        for extra in cases:
            with self.subTest(path=next(iter(extra))):
                self.fixture.write_archive(extra)
                self.rejected_without_changes()
                self.assertFalse((self.fixture.addons / "escape.lua").exists())
        self.fixture.write_archive()
        with zipfile.ZipFile(self.fixture.archive, "a") as archive:
            entry = zipfile.ZipInfo(self.fixture.archive_root + "linked.lua")
            entry.create_system = 3
            entry.external_attr = 0o120777 << 16
            archive.writestr(entry, "Main.lua")
        self.assertIn("Linked file", self.rejected_without_changes().stderr)

    def test_rejects_wrong_toc_and_missing_toc_assets(self):
        self.fixture.files[f"{NAME}.toc"] = b"## Interface: 11500\nMain.lua\n"
        self.fixture.write_archive()
        self.fixture.write_metadata()
        self.assertIn("interface version", self.rejected_without_changes().stderr)
        self.fixture.files[f"{NAME}.toc"] = b"## Interface: 30300\nMissing.lua\n"
        self.fixture.write_archive()
        self.fixture.write_metadata()
        self.assertIn("TOC asset", self.rejected_without_changes().stderr)


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="addon-installer-package-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.checkout = self.root / "Addon-Fork"
        installer = self.checkout / ".github/installer"
        installer.mkdir(parents=True)
        (installer / "README.md").write_bytes(b"# Example Addon installer\n")
        self.files = {f"{NAME}.toc": b"## Interface: 30300\nMain.lua\nLibs\\Lib.lua\n", "Main.lua": MAIN,
                      "Libs/Lib.lua": "-- Grüße\r\nreturn true\n".encode()}
        for relative, value in self.files.items():
            (self.checkout / relative).parent.mkdir(parents=True, exist_ok=True)
            (self.checkout / relative).write_bytes(value)
        (self.checkout / ".github/workflows").mkdir()
        (self.checkout / ".github/workflows/latest.yml").write_bytes(b"name: Latest\n")
        git(self.checkout, "init", "-q")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-qm", "fixture")
        self.archive = self.root / "source.zip"
        self.archive_head()
        self.output = self.root / "installer.zip"

    def archive_head(self):
        """GitHub's archive of the current commit."""
        self.revision = git(self.checkout, "rev-parse", "HEAD").strip()
        self.archive.unlink(missing_ok=True)
        git(self.checkout, "archive", "--format=zip", f"--prefix=Addon-Fork-{self.revision}/", "-o", str(self.archive), "HEAD")

    def package(self):
        return subprocess.run([sys.executable, str(PACKAGER), "--checkout", str(self.checkout), "--name", NAME,
                               "--short", SHORT, "--title", TITLE, "--repository", REPOSITORY,
                               "--source-archive", str(self.archive), "--output", str(self.output)],
                              capture_output=True, text=True, check=False)

    def test_packages_hashes_of_the_tree_and_no_addon_files(self):
        result = self.package()
        self.assertEqual(result.returncode, 0, result.stderr)
        with zipfile.ZipFile(self.output) as package:
            names = sorted(package.namelist())
            manifest = json.loads(package.read("SOURCE_MANIFEST.json"))
            listed = package.read("ADDON_FILES.json")
        self.assertEqual(names, sorted(["ADDON_FILES.json", "LICENSE", "README.md", "SOURCE_MANIFEST.json",
                                        INSTALLER.name, INSTALLER.with_suffix(".cmd").name]))
        self.assertEqual(json.loads(listed)["files"], {relative: digest(value) for relative, value in self.files.items()})
        self.assertEqual(manifest, {
            "schemaVersion": 2, "name": NAME, "repository": REPOSITORY, "revision": self.revision, "interface": 30300,
            "sourceArchive": {"url": f"{REPOSITORY}/archive/{self.revision}.zip", "root": f"Addon-Fork-{self.revision}/",
                              "path": ""},
            "addonFilesSha256": digest(listed)})
        if not POWERSHELL:
            return
        extracted = self.root / "extracted"
        with zipfile.ZipFile(self.output) as package:
            package.extractall(extracted)
        addons = self.root / "AddOns"
        addons.mkdir()
        install = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                  str(extracted / INSTALLER.name), "-AddOnsPath", str(addons),
                                  "-SourceArchive", str(self.archive)], capture_output=True, text=True, timeout=60,
                                 check=False)
        self.assertEqual(install.returncode, 0, install.stdout + install.stderr)
        installed = {path.relative_to(addons / NAME).as_posix(): path.read_bytes()
                     for path in (addons / NAME).rglob("*") if path.is_file()}
        self.assertEqual(installed.pop("SOURCE_REVISION.txt"), (self.revision + "\n").encode())
        installed.pop("SOURCE_MANIFEST.json")
        self.assertEqual(installed, self.files)
        verify = [sys.executable, str(PACKAGER), "--verify-installed", str(addons / NAME),
                  "--installer-package", str(extracted)]
        result = subprocess.run(verify, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        (addons / NAME / "Main.lua").write_bytes(b"changed after installation\n")
        result = subprocess.run(verify, capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0, "a changed installed file must fail verification")

    @unittest.skipUnless(shutil.which("luac5.1"), "luac5.1 is required for the Lua syntax check")
    def test_checks_the_syntax_of_loaded_lua_only(self):
        (self.checkout / "Libs/Lib.lua").write_bytes(b"\xef\xbb\xbfreturn true\n")
        (self.checkout / "Unloaded.lua").write_bytes(b"this is not Lua\n")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-qm", "bom and unloaded file")
        self.archive_head()
        command = [sys.executable, str(PACKAGER), "--checkout", str(self.checkout), "--name", NAME,
                   "--short", SHORT, "--title", TITLE, "--repository", REPOSITORY,
                   "--source-archive", str(self.archive), "--luac", "luac5.1", "--output", str(self.output)]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, "a BOM and unloaded files pass the Lua check: " + result.stderr)
        (self.checkout / "Main.lua").write_bytes(b"local progress =\n")
        git(self.checkout, "commit", "-qam", "broken loaded file")
        self.archive_head()
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Main.lua", result.stderr)

    def test_refuses_an_archive_that_differs_from_the_tree(self):
        with zipfile.ZipFile(self.archive, "a") as archive:
            archive.writestr(f"Addon-Fork-{self.revision}/Injected.lua", b"not committed\n")
        result = self.package()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("different addon files", result.stderr)
        self.assertFalse(self.output.exists())

    def test_refuses_a_toc_for_another_client(self):
        (self.checkout / f"{NAME}.toc").write_bytes(b"## Interface: 11500\nMain.lua\n")
        git(self.checkout, "commit", "-qam", "classic toc")
        result = self.package()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("30300", result.stderr)


class InstallerTemplateTests(unittest.TestCase):
    def test_renders_the_addon_into_both_scripts(self):
        scripts = PACKAGE.installer_scripts("Guides-RM", "Guides", "Guide Viewer", ["Guides", "GuideTalents"])
        self.assertEqual(sorted(scripts), ["Install-Guides.cmd", "Install-Guides.ps1"])
        script = scripts["Install-Guides.ps1"].decode("ascii")
        self.assertIn("$addonName = 'Guides-RM'\n$title = 'Guide Viewer'\n", script)
        self.assertIn("$containedAddons = @('Guides', 'GuideTalents')\n", script)
        self.assertNotIn("@@", script)
        batch = scripts["Install-Guides.cmd"]
        self.assertIn(b'-File "%~dp0Install-Guides.ps1" %*\r\n', batch)
        self.assertIn(b"echo Guide Viewer was not installed.", batch)
        self.assertNotIn(b"\n", batch.replace(b"\r\n", b""), "batch files keep CRLF line endings")
        self.assertIn("$containedAddons = @()\n", SCRIPTS[INSTALLER.name].decode("ascii"))

    def test_refuses_values_that_escape_their_script_strings(self):
        for name, short, title, contained in (("Bad'Name", SHORT, TITLE, []), (NAME, "Ex-ample", TITLE, []),
                                              (NAME, SHORT, "Title' ; Remove-Item", []), (NAME, SHORT, "100% & more", []),
                                              (NAME, SHORT, TITLE, ["Other'Addon"])):
            with self.assertRaises(ValueError):
                PACKAGE.installer_scripts(name, short, title, contained)


if __name__ == "__main__":
    unittest.main()
