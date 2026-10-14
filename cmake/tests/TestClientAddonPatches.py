"""Offline regressions for pinned, patched client addon release artifacts."""
from __future__ import annotations

import hashlib
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
CMAKE = os.environ.get("CMAKE_EXECUTABLE") or shutil.which("cmake")
GIT = shutil.which("git")
POWERSHELL = shutil.which("pwsh")
ADDON_URL = "https://github.com/example/MultiBot.git"
MODULE_URL = "https://github.com/example/mod-fixture.git"
MAIN = b'local money = "upstream"\nreturn money\n'


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def run(command, *, cwd=None):
    # Every source commit is already available locally. Make accidental network
    # access fail rather than fetching fixtures or depending on remote service.
    environment = os.environ.copy()
    environment["GIT_ALLOW_PROTOCOL"] = "file"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(command, cwd=cwd, env=environment, capture_output=True,
                          text=True, timeout=90, check=False)


def git(repository: Path, *arguments) -> str:
    result = run([GIT, "-C", str(repository), *arguments])
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout.strip()


def commit(repository: Path, files: dict[str, bytes]) -> str:
    repository.mkdir(parents=True)
    git(repository, "init", "--quiet")
    git(repository, "config", "user.name", "TestFixture")
    git(repository, "config", "user.email", "test@example.invalid")
    git(repository, "config", "core.autocrlf", "false")
    for relative, value in files.items():
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    git(repository, "add", ".")
    git(repository, "commit", "--quiet", "-m", "Pinned fixture")
    return git(repository, "rev-parse", "HEAD")


def text_patch(relative: str, before: str, after: str) -> bytes:
    return (f"diff --git a/{relative} b/{relative}\n"
            f"--- a/{relative}\n+++ b/{relative}\n@@ -1,2 +1,2 @@\n"
            f'-local money = "{before}"\n+local money = "{after}"\n'
            " return money\n").encode()


class AddonFixture:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir()
        cmake = self.root / "cmake"
        cmake.mkdir()
        for path in (ROOT / "cmake").iterdir():
            if path.is_file() and path.suffix in (".cmake", ".py", ".ps1"):
                shutil.copyfile(path, cmake / path.name)
        self.core = self.root / "core"
        core_revision = commit(self.core, {"README.md": b"Fixture core\n",
                                           "modules/CMakeLists.txt": b"# Fixture module directory\n"})
        self.addon_files = {
            "MultiBot.toc": b"## Interface: 30300\nUI/Main.lua\nUI/Frame.xml\n",
            "UI/Main.lua": MAIN,
            "UI/Frame.xml": b'<Ui><Script file="XMLLoaded.lua"/></Ui>\n',
            "UI/XMLLoaded.lua": b"return true\n",
            "textures/icon.tga": b"\x00texture\xff",
            "resources/font.custom": b"\x00dynamic font\xff",
            "LICENSE": b"Fixture upstream license\n",
            "README.md": b"Fixture addon installation guide\n",
            "docs/development.md": b"Developer documentation\n",
            "tests/test_money.lua": b"assert(true)\n",
            "test_old_money.lua": b"assert(true)\n",
            ".github/workflows/check.yml": b"name: development\n",
            ".gitignore": b"generated/\n",
            "AGENTS.md": b"Fixture developer instructions\n",
        }
        module_files = {"src/module.cpp": b"int module_fixture = 1;\n",
                        "conf/module.conf.dist": b"Fixture.Enabled = 1\n",
                        "LICENSE": b"Fixture upstream license\n",
                        "README.md": b"Fixture module and addon guide\n"}
        self.module = self.root / ".module-cache/mod-fixture"
        module_revision = commit(self.module, module_files)
        module = {"name": "mod-fixture", "url": MODULE_URL,
                  "revision": module_revision, "patches": []}
        self.cached = self.root / ".module-cache/client-addon-MultiBot"
        addon_revision = commit(self.cached, self.addon_files)
        addon = {"name": "MultiBot", "url": ADDON_URL,
                 "revision": addon_revision, "archiveName": "MultiBot-Chatless",
                 "interface": 30300, "toc": "MultiBot.toc", "license": "LICENSE",
                 "patches": []}
        self.lock = {"schemaVersion": 1,
                     "core": {"name": "core", "url": "https://github.com/example/core.git",
                              "revision": core_revision, "source": "core", "patches": []},
                     "modules": [module], "clientAddons": [addon]}
        self.write_lock()

    @property
    def addon(self):
        return self.lock["clientAddons"][0]

    @property
    def prepared(self):
        return self.root / ".module-cache/prepared-addons/MultiBot"

    @property
    def archive(self):
        return self.root / "output/MultiBot-Chatless-fixture.zip"

    def write_lock(self):
        (self.root / "versions.lock.json").write_text(json.dumps(self.lock), encoding="utf-8")

    def patch(self, name: str, value: bytes):
        relative = f"patches/{name}.patch"
        path = self.root / relative
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(value)
        self.addon["patches"].append(relative)
        self.write_lock()
        return relative

    def export(self, destination: Path):
        return run([sys.executable, str(self.root / "cmake/ExportClientAddon.py"),
                    "--repository", str(self.root), "--addon", "MultiBot",
                    "--destination", str(destination)])

    def prepare(self):
        return run([CMAKE, "-P", str(self.root / "cmake/PrepareModules.cmake")])

    def package(self):
        return run([CMAKE, "-DPACKAGE_VERSION=fixture", "-P",
                    str(self.root / "cmake/PackageClientAddons.cmake")])

    def verify(self, archive=None):
        return run([POWERSHELL, "-NoProfile", "-File",
                    str(self.root / "cmake/VerifyClientAddonZip.ps1"),
                    "-ZipPath", str(archive or self.archive), "-AddonName", "MultiBot",
                    "-RepositoryRoot", str(self.root), "-Python", sys.executable])

    def manifest(self):
        patches = self.addon.get("patches", [])
        return {"schemaVersion": 1, "name": "MultiBot", "repository": self.addon["url"],
                "revision": self.addon["revision"], "interface": 30300,
                "patches": {path: digest((self.root / path).read_bytes()) for path in patches}}


@unittest.skipUnless(GIT and CMAKE, "Git and CMake are required for offline addon fixtures")
class ClientAddonPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="client-addon-patches-")
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self):
        return AddonFixture(self.directory / "repository")

    def successful(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def rejected(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_export_patches_committed_source_and_preserves_upstream_checkout(self):
        fixture = self.fixture()
        fixture.patch("money", text_patch("UI/Main.lua", "upstream", "gold silver copper"))
        # A local modification must neither leak into the artifact nor be lost.
        (fixture.cached / "UI/Main.lua").write_bytes(b"local editing in progress\n")
        status = git(fixture.cached, "status", "--porcelain")
        destination = self.directory / "export"
        self.successful(fixture.export(destination))
        self.assertEqual((destination / "UI/Main.lua").read_bytes(),
                         MAIN.replace(b"upstream", b"gold silver copper"))
        self.assertEqual(git(fixture.cached, "rev-parse", "HEAD"), fixture.addon["revision"])
        self.assertEqual(git(fixture.cached, "show", "HEAD:UI/Main.lua"), MAIN.decode().strip())
        self.assertEqual(git(fixture.cached, "status", "--porcelain"), status)
        self.assertEqual((fixture.cached / "UI/Main.lua").read_bytes(), b"local editing in progress\n")
        self.assertFalse((destination / ".git").exists())
        self.assertFalse((destination / ".github").exists())
        self.assertEqual(json.loads((destination / "SOURCE_MANIFEST.json").read_text()), fixture.manifest())

    def test_multiple_patches_follow_lock_order(self):
        fixture = self.fixture()
        fixture.patch("first", text_patch("UI/Main.lua", "upstream", "intermediate"))
        fixture.patch("second", text_patch("UI/Main.lua", "intermediate", "complete"))
        destination = self.directory / "ordered"
        self.successful(fixture.export(destination))
        self.assertEqual((destination / "UI/Main.lua").read_bytes(), MAIN.replace(b"upstream", b"complete"))
        fixture.addon["patches"].reverse()
        fixture.write_lock()
        self.rejected(fixture.export(self.directory / "reversed"))
        self.assertEqual(git(fixture.cached, "show", "HEAD:UI/Main.lua"), MAIN.decode().strip())

    def test_crlf_patch_applies_but_provenance_hashes_original_bytes(self):
        fixture = self.fixture()
        lf_patch = text_patch("UI/Main.lua", "upstream", "localized")
        patch = fixture.patch("crlf", lf_patch.replace(b"\n", b"\r\n"))
        self.successful(fixture.prepare())
        self.assertEqual((fixture.prepared / "UI/Main.lua").read_bytes(),
                         MAIN.replace(b"upstream", b"localized"))
        manifest = json.loads((fixture.prepared / "SOURCE_MANIFEST.json").read_text())
        self.assertEqual(manifest, fixture.manifest())
        self.assertNotEqual(manifest["patches"][patch], digest(lf_patch))
        stamp = (fixture.prepared / ".portable-source").read_text()
        self.assertIn(f"{patch}: {manifest['patches'][patch]}\n", stamp)
        self.successful(fixture.package())

    def test_missing_and_unsafe_patch_paths_are_rejected(self):
        fixture = self.fixture()
        safe = fixture.patch("money", text_patch("UI/Main.lua", "upstream", "release"))
        (fixture.root / "outside.patch").write_bytes((fixture.root / safe).read_bytes())
        for index, unsafe in enumerate(("patches/missing.patch", "../outside.patch", "outside.patch",
                                        "patches/../outside.patch", "patches/nested/money.patch",
                                        "/tmp/outside.patch", "patches\\money.patch")):
            with self.subTest(path=unsafe):
                fixture.addon["patches"] = [unsafe]
                fixture.write_lock()
                self.rejected(fixture.export(self.directory / f"unsafe-{index}"))
                self.rejected(fixture.prepare())

    def test_nonapplicable_patch_fails_without_mutating_pinned_repository(self):
        fixture = self.fixture()
        fixture.patch("wrong-source", text_patch("UI/Main.lua", "different upstream", "release"))
        self.rejected(fixture.export(self.directory / "failed"))
        self.rejected(fixture.prepare())
        self.assertEqual(git(fixture.cached, "status", "--porcelain"), "")
        self.assertEqual(git(fixture.cached, "show", "HEAD:UI/Main.lua"), MAIN.decode().strip())

    def test_changed_patch_hash_invalidates_prepared_stamp_and_reprepares(self):
        fixture = self.fixture()
        patch = fixture.patch("money", text_patch("UI/Main.lua", "upstream", "release"))
        self.successful(fixture.prepare())
        original_manifest = json.loads((fixture.prepared / "SOURCE_MANIFEST.json").read_text())
        (fixture.root / patch).write_bytes((fixture.root / patch).read_bytes().replace(b"\n", b"\r\n"))
        self.rejected(fixture.package())
        self.successful(fixture.prepare())
        changed_manifest = json.loads((fixture.prepared / "SOURCE_MANIFEST.json").read_text())
        self.assertNotEqual(changed_manifest["patches"][patch], original_manifest["patches"][patch])
        self.assertEqual(changed_manifest, fixture.manifest())
        self.successful(fixture.package())

    @unittest.skipUnless(POWERSHELL, "PowerShell is required for independent ZIP verification")
    def test_verifier_rejects_zip_matching_tampered_prepared_cache(self):
        fixture = self.fixture()
        fixture.patch("money", text_patch("UI/Main.lua", "upstream", "release"))
        self.successful(fixture.prepare())
        self.successful(fixture.package())
        self.successful(fixture.verify())
        corruption = b"unlocked code in both mutable copies\n"
        (fixture.prepared / "UI/Main.lua").write_bytes(corruption)
        with zipfile.ZipFile(fixture.archive) as archive:
            files = {item.filename: archive.read(item) for item in archive.infolist() if not item.is_dir()}
        files["MultiBot/UI/Main.lua"] = corruption
        matching_zip = self.directory / "tampered.zip"
        with zipfile.ZipFile(matching_zip, "w") as archive:
            for name, value in files.items():
                archive.writestr(name, value)
        self.rejected(fixture.verify(matching_zip))
        self.rejected(fixture.package())

    @unittest.skipUnless(POWERSHELL, "PowerShell is required for independent ZIP verification")
    def test_runtime_archive_has_exact_provenance_and_keeps_dynamic_resources(self):
        fixture = self.fixture()
        fixture.patch("money", text_patch("UI/Main.lua", "upstream", "release"))
        self.successful(fixture.prepare())
        self.successful(fixture.package())
        self.successful(fixture.verify())
        with zipfile.ZipFile(fixture.archive) as archive:
            files = {item.filename: archive.read(item) for item in archive.infolist() if not item.is_dir()}
        self.assertEqual(json.loads(files["MultiBot/SOURCE_MANIFEST.json"]), fixture.manifest())
        self.assertEqual(files["MultiBot/SOURCE_REVISION.txt"], (fixture.addon["revision"] + "\n").encode())
        self.assertEqual(files["MultiBot/UI/Main.lua"], MAIN.replace(b"upstream", b"release"))
        self.assertEqual(files["MultiBot/resources/font.custom"], fixture.addon_files["resources/font.custom"])
        self.assertEqual(files["MultiBot/UI/XMLLoaded.lua"], fixture.addon_files["UI/XMLLoaded.lua"])
        for development in ("docs/development.md", "tests/test_money.lua", "test_old_money.lua",
                            ".portable-source", "AGENTS.md", ".gitignore", ".github/workflows/check.yml"):
            self.assertNotIn(f"MultiBot/{development}", files)
        # A metadata file naming an arbitrary source hash must not authenticate
        # an artifact whose code still happens to match a prepared directory.
        manifest = json.loads(files["MultiBot/SOURCE_MANIFEST.json"])
        manifest["patches"][fixture.addon["patches"][0]] = "0" * 64
        files["MultiBot/SOURCE_MANIFEST.json"] = json.dumps(manifest).encode()
        (fixture.prepared / "SOURCE_MANIFEST.json").write_bytes(files["MultiBot/SOURCE_MANIFEST.json"])
        tampered = self.directory / "false-provenance.zip"
        with zipfile.ZipFile(tampered, "w") as archive:
            for name, value in files.items():
                archive.writestr(name, value)
        self.rejected(fixture.verify(tampered))

    def test_unpatched_addon_retains_existing_pinned_source_format(self):
        fixture = self.fixture()
        del fixture.addon["patches"]
        fixture.write_lock()
        destination = self.directory / "pristine"
        self.successful(fixture.export(destination))
        expected = {relative: value for relative, value in fixture.addon_files.items()
                    if not relative.startswith(".github/")
                    and relative not in (".gitignore", ".coderabbit.yaml", "AGENTS.md")}
        expected["SOURCE_REVISION.txt"] = (fixture.addon["revision"] + "\n").encode()
        exported = {path.relative_to(destination).as_posix(): path.read_bytes()
                    for path in destination.rglob("*") if path.is_file()}
        self.assertEqual(exported, expected)
        self.assertFalse((destination / "SOURCE_MANIFEST.json").exists())
        self.successful(fixture.prepare())
        self.successful(fixture.package())
        with zipfile.ZipFile(fixture.archive) as archive:
            self.assertNotIn("MultiBot/SOURCE_MANIFEST.json", archive.namelist())
            self.assertEqual(archive.read("MultiBot/UI/Main.lua"), MAIN)
        if POWERSHELL:
            self.successful(fixture.verify())
        # Exporting over existing user files is forbidden, even with no patches.
        preserved = self.directory / "already-present"
        preserved.mkdir()
        (preserved / "user-file").write_bytes(b"retain me")
        self.rejected(fixture.export(preserved))
        self.assertEqual((preserved / "user-file").read_bytes(), b"retain me")

    def test_preparation_removes_generated_copies_dropped_from_lock(self):
        fixture = self.fixture()
        extra = {"name": "mod-extra", "url": "https://github.com/example/mod-extra.git",
                 "revision": commit(fixture.root / ".module-cache/mod-extra",
                                    {"src/extra.cpp": b"int extra = 1;\n", "conf/extra.conf.dist": b"Extra = 1\n"}),
                 "patches": []}
        fixture.lock["modules"].append(extra)
        fixture.write_lock()
        self.successful(fixture.prepare())
        modules = fixture.root / ".module-cache/prepared-core/modules"
        self.assertTrue((modules / "mod-extra/.portable-source").is_file())
        # Unmarked directories are local work and are never removed.
        (modules / "mod-local").mkdir()
        (modules / "mod-local/keep.cpp").write_bytes(b"local edit\n")
        fixture.lock["modules"].remove(extra)
        fixture.lock["clientAddons"] = []
        fixture.write_lock()
        self.successful(fixture.prepare())
        self.assertFalse((modules / "mod-extra").exists())
        self.assertTrue((modules / "mod-fixture/.portable-source").is_file())
        self.assertEqual((modules / "mod-local/keep.cpp").read_bytes(), b"local edit\n")
        self.assertFalse(fixture.prepared.exists())


if __name__ == "__main__":
    unittest.main()
