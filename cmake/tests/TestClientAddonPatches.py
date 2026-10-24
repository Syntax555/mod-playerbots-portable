"""Offline regressions for pinned, patched client addon release artifacts."""
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
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[2]
CMAKE = os.environ.get("CMAKE_EXECUTABLE") or shutil.which("cmake")
GIT = shutil.which("git")
POWERSHELL = shutil.which("pwsh")
ADDON_URL = "https://github.com/example/MultiBot.git"
CORE_URL = "https://github.com/example/azerothcore-wotlk.git"
MODULE_URL = "https://github.com/example/mod-fixture.git"
MAIN = b'local money = "upstream"\nreturn money\n'


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def run(command, *, cwd=None, env=None):
    # Every source commit is already available locally. Make accidental network
    # access fail rather than fetching fixtures or depending on remote service.
    environment = os.environ.copy()
    environment["GIT_ALLOW_PROTOCOL"] = "file"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment.update(env or {})
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
        self.core = self.root / ".module-cache/azerothcore-wotlk"
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
                     "core": {"name": "azerothcore-wotlk", "url": CORE_URL,
                              "revision": core_revision, "patches": []},
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

    def prepare(self, env=None):
        return run([CMAKE, "-P", str(self.root / "cmake/PrepareModules.cmake")], env=env)

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

    def test_patched_exports_ignore_host_line_ending_conversion(self):
        def verify(index, mutation=None):
            fixture = AddonFixture(self.directory / f"repository-{index}")
            (fixture.cached / "Native.lua").write_bytes(b"return true\r\n")
            git(fixture.cached, "add", "Native.lua")
            git(fixture.cached, "commit", "--quiet", "-m", "Preserve native CRLF source")
            fixture.addon["revision"] = git(fixture.cached, "rev-parse", "HEAD")
            fixture.patch("money", text_patch("UI/Main.lua", "upstream", "release"))
            patch = fixture.root / "patches/module.patch"
            patch.write_bytes(b"diff --git a/src/module.cpp b/src/module.cpp\n"
                              b"--- a/src/module.cpp\n+++ b/src/module.cpp\n@@ -1 +1 @@\n"
                              b"-int module_fixture = 1;\n+int module_fixture = 2;\n")
            fixture.lock["modules"][0]["patches"] = ["patches/module.patch"]
            fixture.write_lock()
            if mutation:
                path = fixture.root / "cmake" / mutation
                source = path.read_text(encoding="utf-8")
                setting = ('-c "core.autocrlf=false" ' if path.suffix == ".cmake"
                           else ', "-c", "core.autocrlf=false"')
                path.write_text(source.replace(setting, ""), encoding="utf-8")
            spec = importlib.util.spec_from_file_location(
                f"era_client_endings_{index}", fixture.root / "cmake/PackageEraClient.py")
            package = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(package)
            expected = MAIN.replace(b"upstream", b"release")
            environment = {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "core.autocrlf",
                           "GIT_CONFIG_VALUE_0": "true", "GIT_CONFIG_KEY_1": "core.eol",
                           "GIT_CONFIG_VALUE_1": "crlf"}
            with mock.patch.dict(os.environ, environment):
                exported = self.directory / f"export-{index}"
                self.successful(fixture.export(exported))
                self.assertEqual((exported / "UI/Main.lua").read_bytes(), expected)
                self.assertEqual((exported / "Native.lua").read_bytes(), b"return true\r\n")
                self.successful(fixture.prepare())
                self.assertEqual((fixture.prepared / "UI/Main.lua").read_bytes(), expected)
                prepared = fixture.root / ".module-cache/prepared-core"
                self.assertEqual((prepared / "README.md").read_bytes(), b"Fixture core\n")
                self.assertEqual((prepared / "modules/mod-fixture/src/module.cpp").read_bytes(),
                                 b"int module_fixture = 2;\n")
                self.successful(fixture.package())
                with zipfile.ZipFile(fixture.archive) as archive:
                    self.assertEqual(archive.read("MultiBot/UI/Main.lua"), expected)
                module = self.directory / f"module-{index}"
                package.export_module(fixture.root, fixture.lock["modules"][0], module, GIT)
                self.assertEqual((module / "src/module.cpp").read_bytes(), b"int module_fixture = 2;\n")

        verify(0)
        for index, mutation in enumerate(("ExportClientAddon.py", "PrepareModules.cmake",
                                           "PackageClientAddons.cmake", "PackageEraClient.py"), 1):
            source = (ROOT / "cmake" / mutation).read_text(encoding="utf-8")
            setting = ('-c "core.autocrlf=false" ' if mutation.endswith(".cmake")
                       else ', "-c", "core.autocrlf=false"')
            self.assertIn(setting, source)
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                verify(index, mutation)

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

    def test_preparation_pins_core_and_modules_and_preserves_local_work(self):
        fixture = self.fixture()
        for repository, relative, value in (
            (fixture.core, "README.md", b"Newer core\n"),
            (fixture.module, "src/module.cpp", b"int module_fixture = 2;\n"),
        ):
            (repository / relative).write_bytes(value)
            git(repository, "commit", "--quiet", "-am", "Newer upstream revision")
            (repository / relative).write_bytes(b"unfinished local edit\n")
        legacy = (fixture.root / "azerothcore-wotlk", fixture.root / "mod-playerbots")
        for directory in legacy:
            directory.mkdir()
            (directory / "keep.txt").write_bytes(b"local legacy checkout\n")
        original = {path: (git(path, "rev-parse", "HEAD"), git(path, "status", "--porcelain"))
                    for path in (fixture.core, fixture.module)}
        prepared = fixture.root / ".module-cache/prepared-core"

        def assert_pinned_sources():
            self.assertEqual(git(prepared, "rev-parse", "HEAD"), fixture.lock["core"]["revision"])
            self.assertEqual((prepared / "README.md").read_bytes(), b"Fixture core\n")
            self.assertEqual((prepared / "modules/mod-fixture/src/module.cpp").read_bytes(),
                             b"int module_fixture = 1;\n")

        self.assertFalse((fixture.root / ".gitmodules").exists())
        self.successful(fixture.prepare())
        assert_pinned_sources()
        self.successful(fixture.prepare())
        assert_pinned_sources()
        for path, (head, status) in original.items():
            self.assertEqual(git(path, "rev-parse", "HEAD"), head)
            self.assertEqual(git(path, "status", "--porcelain"), status)
        self.assertEqual((fixture.core / "README.md").read_bytes(), b"unfinished local edit\n")
        self.assertEqual((fixture.module / "src/module.cpp").read_bytes(), b"unfinished local edit\n")
        for directory in legacy:
            self.assertEqual((directory / "keep.txt").read_bytes(), b"local legacy checkout\n")

        script = fixture.root / "cmake/PrepareModules.cmake"
        source = script.read_text(encoding="utf-8")
        mutations = (
            ("core", (
                ('update-ref refs/heads/portable-pinned "${_core_revision}"',
                 'update-ref refs/heads/portable-pinned HEAD'),
                ('checkout --detach --quiet "${_core_revision}"', 'checkout --detach --quiet HEAD'),
            )),
            ("module", (
                ('archive --format=tar "--output=${_archive}" "${_revision}"',
                 'archive --format=tar "--output=${_archive}" HEAD'),
            )),
        )
        for name, replacements in mutations:
            with self.subTest(mutation=name):
                mutated = source
                for before, after in replacements:
                    self.assertEqual(mutated.count(before), 1)
                    mutated = mutated.replace(before, after)
                script.write_text(mutated, encoding="utf-8")
                self.successful(fixture.prepare())
                with self.assertRaises(AssertionError):
                    assert_pinned_sources()

    def test_preparation_fetches_lock_revisions_without_submodules_and_reuses_cache(self):
        fixture = self.fixture()
        core_remote = self.directory / "remote core"
        module_remote = self.directory / "remote module"
        fixture.core.rename(core_remote)
        fixture.module.rename(module_remote)
        # Keep real Git fetches offline while retaining the manifest's GitHub URL contract.
        environment = {"GIT_CONFIG_COUNT": "2",
                       "GIT_CONFIG_KEY_0": f"url.{core_remote.as_uri()}.insteadOf",
                       "GIT_CONFIG_VALUE_0": CORE_URL,
                       "GIT_CONFIG_KEY_1": f"url.{module_remote.as_uri()}.insteadOf",
                       "GIT_CONFIG_VALUE_1": MODULE_URL}
        prepared = fixture.root / ".module-cache/prepared-core"
        self.successful(fixture.prepare(environment))
        self.assertEqual(git(prepared, "rev-parse", "HEAD"), fixture.lock["core"]["revision"])
        self.assertEqual((prepared / "modules/mod-fixture/src/module.cpp").read_bytes(),
                         b"int module_fixture = 1;\n")
        self.assertFalse((fixture.root / "azerothcore-wotlk").exists())
        self.assertFalse((fixture.root / "mod-playerbots").exists())
        # Without URL rewrites, any unnecessary network fetch is rejected.
        self.successful(fixture.prepare())

        for remote, relative, value, entry, output in (
            (module_remote, "src/module.cpp", b"int module_fixture = 2;\n",
             fixture.lock["modules"][0], prepared / "modules/mod-fixture/src/module.cpp"),
            (core_remote, "README.md", b"New pinned core\n", fixture.lock["core"], prepared / "README.md"),
        ):
            with self.subTest(source=entry["name"]):
                (remote / relative).write_bytes(value)
                git(remote, "commit", "--quiet", "-am", "Advance pinned source")
                entry["revision"] = git(remote, "rev-parse", "HEAD")
                fixture.write_lock()
                self.successful(fixture.prepare(environment))
                self.assertEqual(output.read_bytes(), value)
                self.assertEqual(git(prepared, "rev-parse", "HEAD"), fixture.lock["core"]["revision"])
                self.successful(fixture.prepare())
                self.assertEqual(output.read_bytes(), value)

    def source_addon(self, fixture):
        cache = fixture.root / ".module-cache/client-addon-Questie-335"
        revision = commit(cache, {"Questie-335.toc": b"## Interface: 30300\nMain.lua\n",
                                  "Main.lua": MAIN})
        addon = {"name": "Questie-335", "url": "https://github.com/example/Questie.git",
                 "revision": revision, "interface": 30300, "toc": "Questie-335.toc",
                 "patches": []}
        fixture.lock["sourceAddons"] = [addon]
        fixture.write_lock()
        return addon, fixture.root / ".module-cache/prepared-source-addons/Questie-335"

    def test_source_addons_prepare_patches_without_entering_release_packages(self):
        fixture = self.fixture()
        addon, prepared = self.source_addon(fixture)
        patch = fixture.root / "patches/questie.patch"
        patch.parent.mkdir()
        patch.write_bytes(text_patch("Main.lua", "upstream", "first"))
        second = patch.with_name("questie-second.patch")
        second.write_bytes(text_patch("Main.lua", "first", "local"))
        addon["patches"] = ["patches/questie.patch", "patches/questie-second.patch"]
        fixture.write_lock()

        self.successful(fixture.prepare())
        self.assertEqual((prepared / "Main.lua").read_bytes(), MAIN.replace(b"upstream", b"local"))
        self.assertEqual((prepared / "SOURCE_REVISION.txt").read_text(), addon["revision"] + "\n")
        self.assertFalse((prepared / "LICENSE").exists())
        self.assertFalse((fixture.root / ".module-cache/prepared-addons/Questie-335").exists())
        self.successful(fixture.package())
        self.assertEqual(sorted(path.name for path in (fixture.root / "output").glob("*.zip")),
                         ["MultiBot-Chatless-fixture.zip"])
        (prepared / "Main.lua").write_bytes(b"mutable checkout damage\n")
        self.successful(fixture.prepare())
        self.assertEqual((prepared / "Main.lua").read_bytes(), MAIN.replace(b"upstream", b"local"))

        # Omitting the production patch application must break the same expectation.
        script = fixture.root / "cmake/PrepareModules.cmake"
        source = script.read_text()
        gate = 'portable_apply_patches("${_source_stage}" ${_source_patches})'
        self.assertEqual(source.count(gate), 1)
        script.write_text(source.replace(gate, "# omitted patch application"))
        self.successful(fixture.prepare())
        self.assertNotEqual((prepared / "Main.lua").read_bytes(), MAIN.replace(b"upstream", b"local"))
        script.write_text(source)

    def test_source_addons_reject_unsafe_inputs_and_preserve_local_directories(self):
        fixture = self.fixture()
        addon, prepared = self.source_addon(fixture)
        original = dict(addon)
        for key, value in (("name", "../Questie"), ("toc", "../Questie.toc"),
                           ("interface", 12340), ("revision", "HEAD"),
                           ("patches", ["../outside.patch"])):
            with self.subTest(field=key):
                addon.update(original)
                addon[key] = value
                fixture.write_lock()
                self.assertNotEqual(fixture.prepare().returncode, 0)
        addon.update(original)
        fixture.write_lock()
        prepared.mkdir(parents=True)
        (prepared / "keep.txt").write_text("local checkout")
        self.assertNotEqual(fixture.prepare().returncode, 0)
        self.assertEqual((prepared / "keep.txt").read_text(), "local checkout")

    def test_source_addon_in_repository_subdirectory_with_case_insensitive_toc(self):
        # Zygor marks its files text=auto without an eol; Windows exports them with CRLF
        # unless preparation fixes core.eol.
        windows = {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "core.autocrlf", "GIT_CONFIG_VALUE_0": "true",
                   "GIT_CONFIG_KEY_1": "core.eol", "GIT_CONFIG_VALUE_1": "crlf"}
        with mock.patch.dict(os.environ, windows):
            self.source_addon_in_repository_subdirectory()

    def source_addon_in_repository_subdirectory(self):
        fixture = self.fixture()
        cache = fixture.root / ".module-cache/client-addon-Zygor"
        files = {"Zygor/Zygor.toc": b"## Interface: 30300\nLibs\\LibStub\\LibStub.lua\nMain.lua\n",
                 "Zygor/libs/LibStub/LibStub.lua": b"return true\n", "Zygor/Main.lua": MAIN,
                 "tools/test_main.lua": b"assert(true)\n", "LICENSE": b"Fixture upstream license\n",
                 ".gitattributes": b"* text=auto\n"}
        revision = commit(cache, files)
        addon = {"name": "Zygor", "url": "https://github.com/example/Zygor.git", "revision": revision,
                 "path": "Zygor", "interface": 30300, "toc": "Zygor.toc", "patches": ["patches/zygor.patch"]}
        patch = fixture.root / "patches/zygor.patch"
        patch.parent.mkdir()
        patch.write_bytes(text_patch("Zygor/Main.lua", "upstream", "local"))
        fixture.lock["sourceAddons"] = [addon]
        fixture.write_lock()
        prepared = fixture.root / ".module-cache/prepared-source-addons/Zygor"

        self.successful(fixture.prepare())
        self.assertEqual((prepared / "Main.lua").read_bytes(), MAIN.replace(b"upstream", b"local"))
        self.assertEqual((prepared / "SOURCE_REVISION.txt").read_text(), revision + "\n")
        self.assertFalse((prepared / "tools").exists() or (prepared / "LICENSE").exists() or (prepared / "Zygor").exists())

        # The client resolves TOC paths without regard to case; a strict check rejects the real addon.
        script = fixture.root / "cmake/PrepareModules.cmake"
        source = script.read_text()
        folded = 'string(TOLOWER "${_asset}" _asset_key)'
        self.assertEqual(source.count(folded), 1)
        script.write_text(source.replace(folded, 'set(_asset_key "${_asset}")'))
        shutil.rmtree(prepared)
        self.rejected(fixture.prepare())
        subdirectory = 'set(_addon_stage "${_source_stage}/${_path}")'
        self.assertEqual(source.count(subdirectory), 1)
        script.write_text(source.replace(subdirectory, ""))
        self.rejected(fixture.prepare())
        endings = '-c "core.eol=lf" '
        self.assertEqual(source.count(endings), 1)
        script.write_text(source.replace(endings, ""))
        self.rejected(fixture.prepare())
        script.write_text(source)
        self.successful(fixture.prepare())
        self.assertEqual((prepared / "Main.lua").read_bytes(), MAIN.replace(b"upstream", b"local"))

        for path in ("Other", "../Zygor", ""):
            with self.subTest(path=path):
                addon["path"] = path
                fixture.write_lock()
                self.rejected(fixture.prepare())

    def test_addon_tocs_need_the_locked_interface_and_regular_files(self):
        fixture = self.fixture()
        source, _ = self.source_addon(fixture)
        self.successful(fixture.prepare())
        for entry, cache, asset, invalid in (
            (fixture.addon, fixture.cached, "UI/Main.lua", ("UI/Missing.lua", "UI", "./UI/Main.lua", "C:/UI/Main.lua")),
            (source, fixture.root / ".module-cache/client-addon-Questie-335", "Main.lua",
             ("Missing.lua", ".", "./Main.lua", "C:/Main.lua")),
        ):
            valid = entry["revision"]
            if os.name != "nt":
                # A POSIX checkout can hold a name the Windows client cannot load.
                (cache / "a:b.lua").write_bytes(b"return true\n")
                git(cache, "add", "a:b.lua")
                invalid += ("a:b.lua",)
            for toc in ([f"## Interface: 12340\n{asset}\n"] + [f"## Interface: 30300\n{path}\n" for path in invalid]):
                with self.subTest(addon=entry["name"], toc=toc):
                    (cache / entry["toc"]).write_text(toc)
                    git(cache, "commit", "--quiet", "-am", "Invalid TOC")
                    entry["revision"] = git(cache, "rev-parse", "HEAD")
                    fixture.write_lock()
                    self.rejected(fixture.prepare())
            entry["revision"] = valid
            fixture.write_lock()
        self.successful(fixture.prepare())

    def test_patchwork_keeps_lf_sources_on_windows_line_ending_settings(self):
        windows = {"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "core.autocrlf", "GIT_CONFIG_VALUE_0": "true",
                   "GIT_CONFIG_KEY_1": "core.eol", "GIT_CONFIG_VALUE_1": "crlf"}
        script = ROOT / "scripts/patchwork.py"
        source = script.read_text(encoding="utf-8")
        endings = "'-c', 'core.eol=lf', "
        self.assertEqual(source.count(endings), 1)

        def regenerate(name, patchwork):
            fixture = AddonFixture(self.directory / name)
            addon, _ = self.source_addon(fixture)
            cache = fixture.root / ".module-cache/client-addon-Questie-335"
            (cache / ".gitattributes").write_bytes(b"* text=auto\n")
            git(cache, "add", ".gitattributes")
            git(cache, "commit", "--quiet", "-m", "Normalize text")
            addon["revision"] = git(cache, "rev-parse", "HEAD")
            addon["patches"] = ["patches/questie.patch"]
            fixture.write_lock()
            git(fixture.root, "init", "--quiet")
            with mock.patch.dict(os.environ, windows):
                opened = run([sys.executable, str(patchwork), "open", "patches/questie.patch"], cwd=fixture.root)
                self.successful(opened)
                work = Path(opened.stdout.strip().splitlines()[-1])
                self.assertNotIn(b"\r", (work / "Main.lua").read_bytes())
                (work / "Main.lua").write_bytes(MAIN.replace(b"upstream", b"local"))
                (fixture.root / "patches").mkdir()
                self.successful(run([sys.executable, str(patchwork), "save", str(work)], cwd=fixture.root))
            patch = (fixture.root / "patches/questie.patch").read_bytes()
            self.assertNotIn(b"\r", patch)
            self.assertIn(b'+local money = "local"', patch)

        regenerate("lf-repository", script)
        mutated = self.directory / "patchwork-without-eol.py"
        mutated.write_text(source.replace(endings, ""), encoding="utf-8")
        with self.assertRaises(AssertionError):
            regenerate("crlf-repository", mutated)

    def test_patchwork_regenerates_source_addon_patch(self):
        fixture = self.fixture()
        addon, prepared = self.source_addon(fixture)
        addon["patches"] = ["patches/questie.patch"]
        fixture.write_lock()
        git(fixture.root, "init", "--quiet")
        script = ROOT / "scripts/patchwork.py"
        opened = run([sys.executable, str(script), "open", "patches/questie.patch"], cwd=fixture.root)
        self.successful(opened)
        work = Path(opened.stdout.strip().splitlines()[-1])
        (work / "Main.lua").write_bytes(MAIN.replace(b"upstream", b"local"))
        (fixture.root / "patches").mkdir()
        self.successful(run([sys.executable, str(script), "save", str(work)], cwd=fixture.root))
        self.assertIn('+local money = "local"', (fixture.root / "patches/questie.patch").read_text())
        self.successful(fixture.prepare())
        self.assertEqual((prepared / "Main.lua").read_bytes(), MAIN.replace(b"upstream", b"local"))


if __name__ == "__main__":
    unittest.main()
