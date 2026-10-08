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
POWERSHELL = shutil.which("pwsh")
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

    def test_locked_localization_identity_and_source_notice_required(self):
        source = {"deDE": {"revision": "c" * 40, "files": {"Spell.dbc": "d" * 64},
                            "overridesSha256": "e" * 64}}
        self.lock["clientPatch"]["localizations"] = source
        self.manifest["localizations"] = copy.deepcopy(source)
        self.files["licenses/client-locales.txt"] = b"Client data source and original terms"
        self.manifest["files"]["licenses/client-locales.txt"] = PACKAGE.sha(self.files["licenses/client-locales.txt"])
        self.files["SOURCE_MANIFEST.json"] = json.dumps(self.manifest).encode()
        self.verify()
        for field in ("revision", "files", "overridesSha256"):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.manifest)
                changed["localizations"]["deDE"][field] = "different"
                self.files["SOURCE_MANIFEST.json"] = json.dumps(changed).encode()
                with self.assertRaisesRegex(ValueError, "localization source differs"):
                    self.verify()
        self.files["SOURCE_MANIFEST.json"] = json.dumps(self.manifest).encode()
        del self.files["licenses/client-locales.txt"]
        with self.assertRaisesRegex(ValueError, "localization source notice"):
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

    def test_development_asset_rejected_even_with_matching_manifest_hash(self):
        self.files["Interface/AddOns/EraTalents/test_tooltip.lua"] = b"assert(true)"
        del self.files["SOURCE_MANIFEST.json"]
        add_manifest(self.files, self.lock)
        with self.assertRaisesRegex(ValueError, "Development-only addon asset"):
            self.verify()

    def test_unknown_dynamic_binary_resource_is_retained_and_hash_checked(self):
        name = "Interface/AddOns/EraTalents/resources/font.custom"
        self.files[name] = b"\0runtime font\xff"
        del self.files["SOURCE_MANIFEST.json"]
        add_manifest(self.files, self.lock)
        self.assertEqual(self.verify()[0][name], self.files[name])
        self.files[name] += b"changed"
        with self.assertRaisesRegex(ValueError, "hash differs"):
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


def record(spell, name_offset=0, localized_fields=None):
    row = bytearray(234 * 4)
    struct.pack_into("<I", row, 0, spell)
    for locale in range(PACKAGE.SPELL_LOCALE_COUNT):
        struct.pack_into("<I", row, (136 + locale) * 4, name_offset)
    for field, offsets in (localized_fields or {}).items():
        for locale, offset in enumerate(offsets):
            struct.pack_into("<I", row, (field + locale) * 4, offset)
    return bytes(row)


class ClientDbcTests(unittest.TestCase):
    def test_german_helpers_match_authored_translations_and_keep_fallback_locales(self):
        offsets, strings = {}, b"\0"
        values = ("EraTalents Gen 1234abcd", "Arcane Power", "Arkane Macht",
                  "Rank 1", "Rang 1", "Damage increased by 30%.", "Schaden um 30% erhöht.")
        for value in values:
            offsets[value] = len(strings)
            strings += value.encode("utf-8") + b"\0"
        fields, expected = {}, [0] * 234
        for field, english, german in ((136, "Arcane Power", "Arkane Macht"),
                                       (153, "Rank 1", "Rang 1"),
                                       (170, "Damage increased by 30%.", "Schaden um 30% erhöht."),
                                       (187, "Damage increased by 30%.", "Schaden um 30% erhöht.")):
            fields[field] = [offsets[english]] * 16
            fields[field][3] = offsets[german]
            for locale in range(16):
                expected[field + locale] = german if locale == 3 else english
        base = dbc([record(10)], strings)
        helper = record(932760, localized_fields=fields)
        sentinel = record(932999, offsets[values[0]])
        merged = dbc([record(10), helper, sentinel], strings)
        PACKAGE.verify_merged_spell(base, merged, "1234abcd", {932760, 932999}, {932760: expected})
        for label, field in PACKAGE.SPELL_LOCALIZED_FIELDS.items():
            with self.subTest(label=label):
                broken = bytearray(helper)
                # A lost German translation must fail even with a correct marker.
                struct.pack_into("<I", broken, (field + 3) * 4, fields[field][0])
                changed = dbc([record(10), bytes(broken), sentinel], strings)
                with self.assertRaisesRegex(ValueError, "localized spell.*locale slot 3"):
                    PACKAGE.verify_merged_spell(base, changed, "1234abcd", {932760, 932999}, {932760: expected})

    def test_preserves_ip_records_and_reads_generation(self):
        base = dbc([record(10)])
        merged = dbc([record(10), record(932999, 1)], b"\0EraTalents Gen 1234abcd\0")
        PACKAGE.verify_merged_spell(base, merged, "1234abcd", {932999})
        with self.assertRaisesRegex(ValueError, "generation sentinel"):
            PACKAGE.verify_merged_spell(base, merged, "ffffffff", {932999})

    def test_english_only_generation_marker_is_rejected(self):
        base = dbc([record(10)])
        sentinel = record(932999, localized_fields={136: [1] + [0] * 15})
        merged = dbc([record(10), sentinel], b"\0EraTalents Gen 1234abcd\0")
        with self.assertRaisesRegex(ValueError, "generation sentinel.*locale slot 1"):
            PACKAGE.verify_merged_spell(base, merged, "1234abcd", {932999})

    def test_missing_or_wrong_german_generation_marker_is_rejected(self):
        base = dbc([record(10)])
        strings = b"\0EraTalents Gen 1234abcd\0"
        wrong_offset = len(strings)
        strings += b"EraTalents Gen ffffffff\0"
        for german_offset in (0, wrong_offset):
            with self.subTest(german_offset=german_offset):
                offsets = [1] * 16
                offsets[3] = german_offset
                sentinel = record(932999, localized_fields={136: offsets})
                merged = dbc([record(10), sentinel], strings)
                with self.assertRaisesRegex(ValueError, "generation sentinel.*locale slot 3"):
                    PACKAGE.verify_merged_spell(base, merged, "1234abcd", {932999})

    def test_custom_spell_text_has_fallbacks_without_changing_ip_translations(self):
        strings = b"\0"
        offsets = {}
        for value in ("IP English", "IP German", "EraTalents Gen 1234abcd", "Era spell", "Rank 1", "Era description", "Era aura"):
            offsets[value] = len(strings)
            strings += value.encode() + b"\0"
        original_names = [offsets["IP English"]] * 16
        original_names[3] = offsets["IP German"]
        original = record(10, localized_fields={136: original_names})
        base = dbc([original], strings)
        fields = {field: [offsets[value]] * 16 for field, value in zip(
            PACKAGE.SPELL_LOCALIZED_FIELDS.values(), ("Era spell", "Rank 1", "Era description", "Era aura"))}
        helper = record(920010, localized_fields=fields)
        sentinel = record(932999, offsets["EraTalents Gen 1234abcd"])
        merged = dbc([original, helper, sentinel], strings)
        PACKAGE.verify_merged_spell(base, merged, "1234abcd", {920010, 932999})
        self.assertEqual(PACKAGE.dbc_records(base, 234)[0][10], PACKAGE.dbc_records(merged, 234)[0][10])
        for label, field in PACKAGE.SPELL_LOCALIZED_FIELDS.items():
            with self.subTest(label=label):
                mutated = bytearray(helper)
                struct.pack_into("<I", mutated, (field + 3) * 4, 0)
                changed = dbc([original, bytes(mutated), sentinel], strings)
                with self.assertRaisesRegex(ValueError, "localized spell.*locale slot 3"):
                    PACKAGE.verify_merged_spell(base, changed, "1234abcd", {920010, 932999})

    def test_invalid_locale_string_offset_is_rejected(self):
        base = dbc([record(10)])
        sentinel = bytearray(record(932999, 1))
        struct.pack_into("<I", sentinel, (136 + 3) * 4, 9999)
        merged = dbc([record(10), bytes(sentinel)], b"\0EraTalents Gen 1234abcd\0")
        with self.assertRaisesRegex(ValueError, "invalid localized string offset"):
            PACKAGE.verify_merged_spell(base, merged, "1234abcd", {932999})

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
            (addon / "test_tooltip.lua").write_text("assert(true)\n")
            (addon / "build-addon.sh").write_text("#!/bin/sh\nexit 0\n")
            (addon / "Fonts").mkdir()
            (addon / "Fonts/dynamic.resource").write_bytes(b"\0font\xff")
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
                if path.is_dir():
                    shutil.copytree(path, prepared / path.name)
                else:
                    shutil.copyfile(path, prepared / path.name)
            for name in ("LICENSE", "README.md"):
                shutil.copyfile(source / name, prepared / name)
            (prepared / "SOURCE_REVISION.txt").write_text(revision + "\n")
            prepare_hash = hashlib.sha256((root / "cmake/PrepareModules.cmake").read_bytes()).hexdigest()
            header = f"prepare: {prepare_hash}\n{URL}\n{revision}\n"
            stamp = header + "interface: 30300\nmodule: mod-era-talents\npath: client-addon/EraTalents\n" + header
            stamp += f"patches/earned.patch: {hashlib.sha256(patch).hexdigest()}\n"
            stamp += f"export: {hashlib.sha256((ROOT / 'cmake/ExportClientAddon.py').read_bytes()).hexdigest()}\n"
            (prepared / ".portable-source").write_text(stamp)
            command = [CMAKE, f"-DPORTABLE_SOURCE_DIR={root}", "-DPACKAGE_VERSION=fixture", "-P", str(ROOT / "cmake/PackageClientAddons.cmake")]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with zipfile.ZipFile(root / "output/EraTalents-fixture.zip") as archive:
                self.assertEqual(archive.read("EraTalents/Main.lua"), b"return 'earned'\n")
                self.assertEqual(archive.read("EraTalents/Fonts/dynamic.resource"), b"\0font\xff")
                self.assertNotIn("EraTalents/test_tooltip.lua", archive.namelist())
                self.assertNotIn("EraTalents/build-addon.sh", archive.namelist())
            self.assertTrue((prepared / "test_tooltip.lua").is_file())
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


class AddonRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="addon-runtime-regression-")
        self.root = Path(self.temporary.name)
        self.source = self.root / "Demo"
        self.source.mkdir()
        self.write("Demo.toc", b"## Interface: 30300\nMain.lua\nUI/Frame.xml\n")
        self.write("Main.lua", b"return true\n")
        self.write("UI/Frame.xml", b'<Ui><Include file="parts/Nested.xml"/></Ui>')
        self.write("UI/parts/Nested.xml", b'<Ui><Script file="../../test_compat.lua"/></Ui>')
        self.write("test_compat.lua", b"return 'loaded runtime compatibility'\n")
        self.write("Textures/test_icon.tga", b"\0\xfftexture\r\n")
        self.write("Fonts/font.custom", b"\0font\xff")
        self.write("Dynamic/not_in_toc.lua", b"return 'dynamic'\n")
        self.write("LICENSE", b"MIT\n")
        self.write("README.md", b"Install the Demo folder.\n")
        self.write("SOURCE_REVISION.txt", (REVISION + "\n").encode())
        self.development = ("test_unloaded.lua", "build-addon.sh", ".editorconfig", ".gitignore", ".gitattributes",
                            ".luacheckrc", "stylua.toml", "CONTRIBUTING.md", ".github/workflows/test.yml",
                            "docs/DEBUG_RUNBOOK.md", "tests/fixture.lua", ".portable-source")
        for path in self.development:
            self.write(path, b"development only\n")

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, name, value):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)

    def test_runtime_export_keeps_xml_loads_and_dynamic_binary_assets(self):
        paths = PACKAGE.ADDON_RUNTIME.runtime_paths(self.source, "Demo.toc")
        self.assertFalse(set(paths) & set(self.development))
        for name in ("test_compat.lua", "Textures/test_icon.tga", "Fonts/font.custom", "Dynamic/not_in_toc.lua",
                     "UI/parts/Nested.xml", "LICENSE", "README.md", "SOURCE_REVISION.txt"):
            self.assertIn(name, paths)

    def test_export_preserves_prepared_source_and_every_runtime_byte(self):
        before = {path.relative_to(self.source).as_posix(): path.read_bytes()
                  for path in self.source.rglob("*") if path.is_file()}
        destination = self.root / "runtime/Demo"
        subprocess.run([os.sys.executable, str(ROOT / "cmake/AddonRuntime.py"), "--source", str(self.source),
                        "--toc", "Demo.toc", "--destination", str(destination)], check=True, capture_output=True)
        self.assertEqual(before, {path.relative_to(self.source).as_posix(): path.read_bytes()
                                  for path in self.source.rglob("*") if path.is_file()})
        for path in destination.rglob("*"):
            if path.is_file():
                self.assertEqual(path.read_bytes(), before[path.relative_to(destination).as_posix()])

    def test_missing_or_escaping_xml_script_cannot_be_silently_excluded(self):
        for include in ("missing.lua", "../../../outside.lua"):
            with self.subTest(include=include):
                self.write("UI/parts/Nested.xml", f'<Ui><Script file="{include}"/></Ui>'.encode())
                with self.assertRaises(ValueError):
                    PACKAGE.ADDON_RUNTIME.runtime_paths(self.source, "Demo.toc")

    @unittest.skipUnless(POWERSHELL, "PowerShell needed for standalone runtime verification")
    def test_standalone_verifier_checks_runtime_bytes_and_refuses_development_asset(self):
        repository = self.root / "repository"
        cached = repository / ".module-cache/client-addon-Demo"
        shutil.copytree(self.source, cached)
        (cached / "SOURCE_REVISION.txt").unlink()
        (cached / ".portable-source").unlink()
        subprocess.run(["git", "init", "-q", str(cached)], check=True)
        subprocess.run(["git", "-C", str(cached), "add", "."], check=True)
        subprocess.run(["git", "-C", str(cached), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "commit", "-qm", "Pinned runtime fixture"], check=True)
        revision = subprocess.check_output(["git", "-C", str(cached), "rev-parse", "HEAD"], text=True).strip()
        self.write("SOURCE_REVISION.txt", (revision + "\n").encode())
        prepared = repository / ".module-cache/prepared-addons/Demo"
        shutil.copytree(self.source, prepared)
        (repository / "versions.lock.json").write_text(json.dumps({"schemaVersion": 1, "clientAddons": [
            {"name": "Demo", "url": URL, "revision": revision, "toc": "Demo.toc", "license": "LICENSE", "interface": 30300}]}))
        path = self.root / "Demo.zip"

        def archive(extra=None):
            with zipfile.ZipFile(path, "w") as output:
                for relative in PACKAGE.ADDON_RUNTIME.runtime_paths(self.source, "Demo.toc"):
                    output.writestr("Demo/" + relative, (self.source / relative).read_bytes())
                for relative, content in (extra or {}).items():
                    output.writestr("Demo/" + relative, content)

        command = [POWERSHELL, "-NoLogo", "-NoProfile", "-File", str(ROOT / "cmake/VerifyClientAddonZip.ps1"),
                   "-ZipPath", str(path), "-AddonName", "Demo", "-RepositoryRoot", str(repository),
                   "-Python", os.sys.executable]
        archive()
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        archive({"test_unloaded.lua": b"development only\n"})
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unexpected asset", result.stderr)
        archive()
        (prepared / "Textures/test_icon.tga").write_bytes(b"corrupted texture")
        # Mutating the prepared cache does not change the independently locked
        # expected bytes. A ZIP containing the same mutation still fails.
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.write("Textures/test_icon.tga", b"corrupted texture")
        archive()
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("differs from locked source", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
