#!/usr/bin/env python3
"""Client artifact regressions: locked patched addons, ZIP integrity and DBC preservation."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("era_client_package", ROOT / "cmake/PackageEraClient.py")
PACKAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGE)
CMAKE = os.environ.get("CMAKE_EXECUTABLE") or shutil.which("cmake")
REVISION = "a" * 40
URL = "https://github.com/example/module.git"


def source_lock():
    return {"schemaVersion": 1, "modules": [
        {"name": "mod-era-talents", "url": URL, "revision": REVISION, "patches": []},
        {"name": "mod-individual-progression", "url": URL, "revision": REVISION}],
        "clientPatch": {"name": "EraTalents-client", "eraModule": "mod-era-talents",
                        "baseModule": "mod-individual-progression", "baseArchive": "optional/patch-V.7z",
                        "stormLib": {"url": URL, "revision": REVISION}}}


def source_files():
    return {"Data/patch-V.mpq": b"MPQ\x1a\x00fixture",
            "README.txt": b"Install instructions",
            "licenses/mod-era-talents.txt": b"MIT", "licenses/mod-individual-progression.txt": b"AGPL",
            "licenses/StormLib.txt": b"MIT", "Interface/AddOns/EraTalents/EraTalents.toc": b"## Interface: 30300\nMain.lua\n",
            "Interface/AddOns/EraTalents/Main.lua": b"return true",
            "Interface/AddOns/EraTalents/LICENSE": b"MIT", "Interface/AddOns/EraTalents/README.md": b"Addon README",
            "Interface/AddOns/EraTalents/SOURCE_REVISION.txt": (REVISION + "\n").encode()}


def add_manifest(files, lock):
    identity = {"url": URL, "revision": REVISION, "patches": {}}
    manifest = {"schemaVersion": 1, "clientInterface": 30300, "generation": "1234abcd", "eraModule": identity,
                "baseModule": identity, "stormLib": lock["clientPatch"]["stormLib"], "baseArchive": "optional/patch-V.7z",
                "files": {name: PACKAGE.sha(value) for name, value in files.items()}}
    files["SOURCE_MANIFEST.json"] = json.dumps(manifest).encode()
    return manifest


class ClientZipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="era-client-regression-")
        self.path = Path(self.temp.name) / "client.zip"
        self.lock = source_lock()
        self.files = source_files()
        self.manifest = add_manifest(self.files, self.lock)

    def tearDown(self):
        self.temp.cleanup()

    def verify(self):
        PACKAGE.write_zip(self.path, self.files)
        return PACKAGE.verify_zip(self.path, self.lock)

    def test_complete_zip_and_deterministic_archive(self):
        self.assertEqual(self.verify()[0], self.files)
        first = self.path.read_bytes()
        PACKAGE.write_zip(self.path, dict(reversed(list(self.files.items()))))
        self.assertEqual(self.path.read_bytes(), first)

    def test_modified_texture_or_mpq_rejected(self):
        for name in ("Data/patch-V.mpq", "Interface/AddOns/EraTalents/Main.lua"):
            with self.subTest(name=name):
                before = self.files[name]
                self.files[name] = b"changed"
                with self.assertRaisesRegex(ValueError, "hash differs"):
                    self.verify()
                self.files[name] = before

    def test_missing_license_rejected(self):
        del self.files["licenses/StormLib.txt"]
        with self.assertRaisesRegex(ValueError, "Missing client ZIP asset"):
            self.verify()

    def test_stale_module_or_tool_revision_rejected(self):
        for module in ("eraModule", "baseModule", "stormLib"):
            with self.subTest(module=module):
                changed = copy.deepcopy(self.manifest)
                changed[module]["revision"] = "b" * 40
                self.files["SOURCE_MANIFEST.json"] = json.dumps(changed).encode()
                with self.assertRaises(ValueError):
                    self.verify()

    def test_missing_toc_asset_rejected_even_with_updated_hashes(self):
        del self.files["Interface/AddOns/EraTalents/Main.lua"]
        del self.files["SOURCE_MANIFEST.json"]
        add_manifest(self.files, self.lock)
        with self.assertRaisesRegex(ValueError, "Missing EraTalents TOC asset"):
            self.verify()

    def test_foreign_asset_rejected(self):
        self.files["worldserver.exe"] = b"unexpected"
        with self.assertRaisesRegex(ValueError, "Unexpected client ZIP asset"):
            self.verify()

    def test_traversal_case_collision_and_symlink_rejected(self):
        for name in ("../outside", "Data/../outside", r"Data\patch-V.mpq", "/Data/patch-V.mpq", "data/PATCH-V.mpq"):
            with self.subTest(name=name):
                with zipfile.ZipFile(self.path, "w") as archive:
                    for path, content in self.files.items():
                        archive.writestr(path, content)
                    archive.writestr(name, b"invalid")
                with self.assertRaises(ValueError):
                    PACKAGE.verify_zip(self.path, self.lock)
        with zipfile.ZipFile(self.path, "w") as archive:
            entry = zipfile.ZipInfo("Interface/AddOns/EraTalents/link")
            entry.create_system = 3
            entry.external_attr = 0o120777 << 16
            archive.writestr(entry, "outside")
        with self.assertRaisesRegex(ValueError, "symbolic link"):
            PACKAGE.verify_zip(self.path, self.lock)


def dbc(rows, strings=b"\0", fields=234):
    return struct.pack("<4s4I", b"WDBC", len(rows), fields, fields * 4, len(strings)) + b"".join(rows) + strings


def record(spell, name_offset=0):
    row = bytearray(234 * 4)
    struct.pack_into("<I", row, 0, spell)
    struct.pack_into("<I", row, 136 * 4, name_offset)
    return bytes(row)


class ClientDbcTests(unittest.TestCase):
    def test_preserves_ip_records_and_reads_generation(self):
        base = dbc([record(10)])
        merged = dbc([record(10), record(932999, 1)], b"\0EraTalents Gen 1234abcd\0")
        PACKAGE.verify_merged_spell(base, merged, "1234abcd", {932999})
        with self.assertRaisesRegex(ValueError, "generation sentinel"):
            PACKAGE.verify_merged_spell(base, merged, "ffffffff", {932999})

    def test_corrupted_base_record_rejected(self):
        base = dbc([record(10)])
        mutated = bytearray(record(10))
        mutated[4] = 1
        merged = dbc([bytes(mutated), record(932999, 1)], b"\0EraTalents Gen 1234abcd\0")
        with self.assertRaisesRegex(ValueError, "changed IP spell record"):
            PACKAGE.verify_merged_spell(base, merged, "1234abcd", {932999})

    def test_truncation_and_duplicate_record_ids_rejected(self):
        for raw in (b"WDBC", dbc([record(10)])[:-1], dbc([record(10), record(10)])):
            with self.assertRaises(ValueError):
                PACKAGE.dbc_records(raw, 234)

    def test_preserves_ip_skill_mappings_and_requires_era_rows(self):
        original = struct.pack("<14I", 1, 2, 10, *([0] * 11))
        era = struct.pack("<14I", 900010, 2, 920010, *([0] * 11))
        base = dbc([original], fields=14)
        merged = dbc([original, era], fields=14)
        PACKAGE.verify_merged_skill(base, merged, {920010})
        with self.assertRaisesRegex(ValueError, "missing era spellbook"):
            PACKAGE.verify_merged_skill(base, base, {920010})
        corrupted = bytearray(original)
        corrupted[4] = 3
        with self.assertRaisesRegex(ValueError, "changed IP skill record"):
            PACKAGE.verify_merged_skill(base, dbc([bytes(corrupted), era], fields=14), {920010})


@unittest.skipUnless(CMAKE and shutil.which("git"), "CMake and Git needed for addon source export checks")
class ModuleAddonTests(unittest.TestCase):
    def test_addon_exports_earned_patch_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory(prefix="module-addon-regression-") as temp:
            root = Path(temp)
            source = root / ".module-cache/mod-era-talents"
            source.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            addon = source / "client-addon/EraTalents"
            addon.mkdir(parents=True)
            (addon / "EraTalents.toc").write_text("## Interface: 30300\nMain.lua\n")
            (addon / "Main.lua").write_text("return 'baseline'\n")
            (source / "LICENSE").write_text("MIT\n")
            (source / "README.md").write_text("Module README\n")
            subprocess.run(["git", "-C", str(source), "add", "."], check=True)
            subprocess.run(["git", "-C", str(source), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                            "commit", "-qm", "Pinned fixture"], check=True)
            revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
            (addon / "Main.lua").write_text("return 'earned'\n")
            patch = subprocess.check_output(["git", "-C", str(source), "diff"])
            (root / "patches").mkdir()
            (root / "patches/earned.patch").write_bytes(patch)
            (root / "cmake").mkdir()
            (root / "cmake/PrepareModules.cmake").write_text("# Fixture preparation identity\n")
            lock = {"schemaVersion": 1, "core": {"source": "core"},
                    "modules": [{"name": "mod-era-talents", "url": URL, "revision": revision, "patches": ["patches/earned.patch"]}],
                    "clientAddons": [{"name": "EraTalents", "url": URL, "revision": revision, "toc": "EraTalents.toc",
                                      "license": "LICENSE", "interface": 30300, "sourceModule": "mod-era-talents",
                                      "sourcePath": "client-addon/EraTalents"}]}
            (root / "versions.lock.json").write_text(json.dumps(lock))
            prepared = root / ".module-cache/prepared-addons/EraTalents"
            prepared.mkdir(parents=True)
            for path in addon.iterdir():
                shutil.copyfile(path, prepared / path.name)
            for name in ("LICENSE", "README.md"):
                shutil.copyfile(source / name, prepared / name)
            (prepared / "SOURCE_REVISION.txt").write_text(revision + "\n")
            prepare_hash = hashlib.sha256((root / "cmake/PrepareModules.cmake").read_bytes()).hexdigest()
            header = f"prepare: {prepare_hash}\n{URL}\n{revision}\n"
            stamp = header + "interface: 30300\nmodule: mod-era-talents\npath: client-addon/EraTalents\n" + header
            stamp += f"patches/earned.patch: {hashlib.sha256(patch).hexdigest()}\n"
            (prepared / ".portable-source").write_text(stamp)
            command = [CMAKE, f"-DPORTABLE_SOURCE_DIR={root}", "-DPACKAGE_VERSION=fixture", "-P", str(ROOT / "cmake/PackageClientAddons.cmake")]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with zipfile.ZipFile(root / "output/EraTalents-fixture.zip") as archive:
                self.assertEqual(archive.read("EraTalents/Main.lua"), b"return 'earned'\n")
            (prepared / "Main.lua").write_text("return 'tampered'\n")
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("corrupt asset", result.stderr)

    def test_old_source_without_client_patch_is_supported(self):
        with tempfile.TemporaryDirectory(prefix="old-client-regression-") as temp:
            root = Path(temp)
            (root / "versions.lock.json").write_text('{"schemaVersion": 1}')
            result = subprocess.run([CMAKE, f"-DPORTABLE_SOURCE_DIR={root}", "-P", str(ROOT / "cmake/PackageEraClient.cmake")],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("no historical client patch", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
