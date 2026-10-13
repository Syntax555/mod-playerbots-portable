"""Build and verify the era client MPQ using only manifest-pinned inputs.

The IP client archive is the base. Both DBC generators come from the locked,
earned-patched era module. No upstream bootstrap or latest-clone script runs.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import zipfile


SHA = re.compile(r"[a-f0-9]{40}\Z")
GITHUB_URL = re.compile(r"https://github.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git\Z")
VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
SOURCE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,127}\Z")
INTERNAL_SPELL = r"DBFilesClient\Spell.dbc"
INTERNAL_SKILL = r"DBFilesClient\SkillLineAbility.dbc"
FIXED_TIME = (2000, 1, 1, 0, 0, 0)
SPELL_LOCALIZED_FIELDS = {"name": 136, "rank": 153, "description": 170, "aura description": 187}
SPELL_LOCALE_COUNT = 16

_locale_spec = importlib.util.spec_from_file_location("client_locales", Path(__file__).with_name("ClientLocales.py"))
CLIENT_LOCALES = importlib.util.module_from_spec(_locale_spec)
_locale_spec.loader.exec_module(CLIENT_LOCALES)
_runtime_spec = importlib.util.spec_from_file_location("addon_runtime", Path(__file__).with_name("AddonRuntime.py"))
ADDON_RUNTIME = importlib.util.module_from_spec(_runtime_spec)
_runtime_spec.loader.exec_module(ADDON_RUNTIME)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError(f"Invalid relative path: {value!r}")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts) or value.startswith("/"):
        raise ValueError(f"Invalid relative path: {value!r}")
    return value


def run(command, *, cwd=None, quiet=False):
    result = subprocess.run(command, cwd=cwd, check=True, capture_output=True)
    if not quiet and result.stdout:
        print(result.stdout.decode(errors="replace").strip())
    return result.stdout


def locked_module(lock, name):
    matches = [item for item in lock["modules"] if item["name"] == name]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one locked module: {name}")
    item = matches[0]
    if not SHA.fullmatch(item["revision"]) or not GITHUB_URL.fullmatch(item["url"]):
        raise ValueError(f"Invalid module source: {name}")
    return item


def historical_class_data(lock):
    """Validate the optional historical-data provenance and notice paths."""
    if "historicalClassData" not in lock:
        return None
    spec = lock["historicalClassData"]
    if not isinstance(spec, dict) or not isinstance(spec.get("sources"), list) or not spec["sources"]:
        raise ValueError("Historical class data must have locked sources")
    names = set()
    for source in spec["sources"]:
        if (not isinstance(source, dict) or not isinstance(source.get("name"), str)
                or not SOURCE_NAME.fullmatch(source["name"]) or source["name"] in names
                or not isinstance(source.get("url"), str) or not GITHUB_URL.fullmatch(source["url"])
                or not isinstance(source.get("revision"), str) or not SHA.fullmatch(source["revision"])):
            raise ValueError("Invalid historical class data source")
        names.add(source["name"])
    additional = spec.get("licenses", [])
    if not isinstance(additional, list):
        raise ValueError("Historical class data licenses must be a list")
    paths = [spec.get("notice"), spec.get("license"), *additional]
    for path in paths:
        relative_path(path)
        if not path.startswith("licenses/"):
            raise ValueError("Historical class data notices must be under licenses/")
    if len({path.casefold() for path in paths}) != len(paths):
        raise ValueError("Duplicate historical class data notice or license")
    return spec


def historical_class_files(repository: Path, lock):
    spec = historical_class_data(lock)
    if spec is None:
        return {}
    files = {}
    for path in (spec["notice"], spec["license"], *spec.get("licenses", [])):
        content = (repository / path).read_bytes()
        if not content:
            raise ValueError(f"Empty historical class data notice or license: {path}")
        files[path] = content
    return files


def export_module(repository: Path, module, destination: Path, git: str):
    """Re-export a pinned commit and ordered patches, independently of prepared files."""
    cache = repository / module.get("source", f".module-cache/{module['name']}")
    run([git, "-C", str(cache), "cat-file", "-e", f"{module['revision']}^{{commit}}"], quiet=True)
    archive = destination.parent / f"{module['name']}.tar"
    run([git, "-C", str(cache), "archive", "--format=tar", f"--output={archive}", module["revision"]], quiet=True)
    destination.mkdir(parents=True)
    with tarfile.open(archive) as source:
        # A module export must not contain links, special files or escaping paths.
        for member in source.getmembers():
            relative_path(member.name.rstrip("/"))
            if not (member.isdir() or member.isfile()):
                raise ValueError(f"Unsupported source archive entry: {member.name}")
        if not hasattr(tarfile, "data_filter"):
            raise ValueError("Python 3.12 or newer is required for safe archive extraction")
        source.extractall(destination, filter="data")
    archive.unlink()
    patches = {}
    for index, path in enumerate(module.get("patches", [])):
        path = relative_path(path)
        content = (repository / path).read_bytes()
        patches[path] = sha(content)
        patch = destination.parent / f"{module['name']}-{index}.patch"
        patch.write_bytes(content.replace(b"\r\n", b"\n"))
        env = os.environ.copy()
        env["GIT_CEILING_DIRECTORIES"] = str(destination.parent)
        subprocess.run([git, "-C", str(destination), "apply", "--check", str(patch)], env=env, check=True)
        subprocess.run([git, "-C", str(destination), "apply", str(patch)], env=env, check=True)
        patch.unlink()
    return {"url": module["url"], "revision": module["revision"], "patches": patches}


def read_mpq(tool: Path, archive: Path, internal: str, output: Path) -> bytes:
    run([str(tool), str(archive), internal, str(output)], quiet=True)
    return output.read_bytes()


def dbc_records(raw: bytes, field_count: int):
    if len(raw) < 20:
        raise ValueError("Truncated DBC header")
    magic, count, fields, size, strings_size = struct.unpack_from("<4s4I", raw)
    if magic != b"WDBC" or fields != field_count or size != fields * 4 or len(raw) != 20 + count * size + strings_size:
        raise ValueError("Invalid DBC layout or length")
    records = {}
    for index in range(count):
        record = raw[20 + index * size:20 + (index + 1) * size]
        key = struct.unpack_from("<I", record)[0]
        if key in records:
            raise ValueError(f"Duplicate DBC record ID: {key}")
        records[key] = record
    return records, raw[20 + count * size:]


def native_spell_contract(contract):
    """Limit native client restorations to explicitly authored mana-cost fields."""
    if (not isinstance(contract, dict)
            or set(contract) != {"source", "sourceSha256", "fields", "spellIds"}
            or contract["source"] != "pinned-wrath-english"
            or not isinstance(contract["sourceSha256"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", contract["sourceSha256"])
            or contract["fields"] != ["ManaCost", "ManaCostPct"]):
        raise ValueError("Invalid native spell restoration contract")
    ids = contract["spellIds"]
    if (not isinstance(ids, list) or not ids
            or any(type(value) is not int or not 0 < value <= 0xffffffff for value in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("Invalid native spell restoration IDs")
    return contract


def restore_native_spell_fields(base: bytes, donor: bytes, contract, columns, types):
    """Copy only contracted unsigned costs; preserve row order and every other byte."""
    native_spell_contract(contract)
    if sha(donor) != contract["sourceSha256"]:
        raise ValueError("Native spell donor hash differs from restoration contract")
    if (len(columns) != 234 or len(types) != 234 or len(set(columns)) != 234
            or columns[0] != "ID"):
        raise ValueError("Invalid native spell restoration column layout")
    fields = {}
    for name in contract["fields"]:
        if name not in columns or types[columns.index(name)] != "unsigned":
            raise ValueError(f"Native spell restoration field must be unsigned: {name}")
        fields[name] = columns.index(name)
    base_records, _ = dbc_records(base, 234)
    native_records, _ = dbc_records(donor, 234)
    missing = set(contract["spellIds"]) - (base_records.keys() & native_records.keys())
    if missing:
        raise ValueError(f"Missing native spell restoration records: {sorted(missing)}")
    offsets = {key: 20 + index * 234 * 4 for index, key in enumerate(base_records)}
    restored, changes = bytearray(base), []
    for key in contract["spellIds"]:
        for name, column in fields.items():
            before = struct.unpack_from("<I", base_records[key], column * 4)[0]
            after = struct.unpack_from("<I", native_records[key], column * 4)[0]
            if before != after:
                struct.pack_into("<I", restored, offsets[key] + column * 4, after)
                changes.append({"spellId": key, "field": name, "before": before, "after": after})
    return bytes(restored), {"contract": contract, "changes": changes}


def verify_native_spell_restoration_report(report, patch):
    path = patch.get("nativeSpellRestorations")
    if path is None:
        if report is not None:
            raise ValueError("Native spell restorations are not locked")
        return
    relative_path(path)
    if (not isinstance(report, dict) or set(report) != {"contractFile", "contract", "changes"}
            or report["contractFile"] != path):
        raise ValueError("Native spell restoration report differs from lock")
    contract = native_spell_contract(report["contract"])
    source = patch.get("localizations", {}).get("deDE", {}).get("englishSpellSha256")
    if contract["sourceSha256"] != source:
        raise ValueError("Native spell restoration source differs from lock")
    if not isinstance(report["changes"], list):
        raise ValueError("Invalid native spell restoration changes")
    seen = set()
    for change in report["changes"]:
        if (not isinstance(change, dict) or set(change) != {"spellId", "field", "before", "after"}
                or type(change["spellId"]) is not int or change["spellId"] not in contract["spellIds"]
                or change["field"] not in contract["fields"]
                or any(type(change[key]) is not int or not 0 <= change[key] <= 0xffffffff
                       for key in ("before", "after")) or change["before"] == change["after"]):
            raise ValueError("Invalid native spell restoration change")
        key = (change["spellId"], change["field"])
        if key in seen:
            raise ValueError("Duplicate native spell restoration change")
        seen.add(key)


def verify_merged_spell(base: bytes, merged: bytes, stamp: str, custom_ids, expected_rows=None):
    base_records, base_strings = dbc_records(base, 234)
    records, strings = dbc_records(merged, 234)
    if not strings.startswith(base_strings):
        raise ValueError("Merged client spell strings changed the IP base")
    for key, value in base_records.items():
        if key not in custom_ids and records.get(key) != value:
            raise ValueError(f"Merged client changed IP spell record {key}")
    if not set(custom_ids).issubset(records):
        raise ValueError("Merged client is missing visible era spell rows")
    def text(record, field):
        offset = struct.unpack_from("<I", record, field * 4)[0]
        if offset >= len(strings):
            raise ValueError("Merged client spell has an invalid localized string offset")
        end = strings.find(b"\0", offset)
        if end == -1:
            raise ValueError("Merged client spell has an unterminated localized string")
        try:
            return strings[offset:end].decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("Merged client spell has invalid localized UTF-8 text") from None

    # WoW reads the selected client's locale slot, including deDE (slot 3).
    # A marker present only in enUS produces MISSING on localized clients.
    record = records[932999]
    for locale in range(SPELL_LOCALE_COUNT):
        if text(record, SPELL_LOCALIZED_FIELDS["name"] + locale) != f"EraTalents Gen {stamp}":
            raise ValueError(f"Merged client generation sentinel differs from server SQL for locale slot {locale}")
    # German helpers use authored translations; other locale slots fall back to
    # English. Check custom rows only; preserve every original IP record.
    for key in custom_ids:
        record = records[key]
        for label, field in SPELL_LOCALIZED_FIELDS.items():
            english = text(record, field)
            if label == "name" and not english:
                raise ValueError(f"Merged client visible era spell has an empty name: {key}")
            if expected_rows is not None and key in expected_rows and english != (expected_rows[key][field] or ""):
                raise ValueError(f"Merged client authored spell {label} differs from dataset: spell {key}")
            for locale in range(1, SPELL_LOCALE_COUNT):
                expected = english
                if locale == 3 and expected_rows is not None and key in expected_rows:
                    expected = expected_rows[key][field + locale] or ""
                if text(record, field + locale) != expected:
                    raise ValueError(
                        f"Merged client localized spell {label} differs from authored text: spell {key}, locale slot {locale}")


def verify_merged_skill(base: bytes, merged: bytes, custom_spells):
    base_records, base_strings = dbc_records(base, 14)
    records, strings = dbc_records(merged, 14)
    if strings != base_strings:
        raise ValueError("Merged client skill strings changed the IP base")
    for key, record in base_records.items():
        spell = struct.unpack_from("<I", record, 2 * 4)[0]
        if spell not in custom_spells and records.get(key) != record:
            raise ValueError(f"Merged client changed IP skill record {key}")
    spells = {struct.unpack_from("<I", record, 2 * 4)[0] for record in records.values()}
    if not set(custom_spells).issubset(spells):
        raise ValueError("Merged client is missing era spellbook skill mappings")


def addon_files(source: Path, module: Path):
    result = {}
    for relative in ADDON_RUNTIME.runtime_paths(source, "EraTalents.toc"):
        result[f"Interface/AddOns/EraTalents/{relative}"] = (source / relative).read_bytes()
    # The module README documents the server build; README.txt covers installation.
    result["Interface/AddOns/EraTalents/LICENSE"] = (module / "LICENSE").read_bytes()
    return result


def write_zip(path: Path, files):
    temporary = path.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(files.items()):
            relative_path(name)
            entry = zipfile.ZipInfo(name, FIXED_TIME)
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    temporary.replace(path)


def verify_zip(path: Path, lock):
    """Structural, source-identity, TOC and every-byte checks for a client ZIP."""
    with zipfile.ZipFile(path) as archive:
        files = {}
        folded = set()
        for entry in archive.infolist():
            name = relative_path(entry.filename)
            if name.casefold() in folded or entry.is_dir() or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"Duplicate, directory or symbolic link in client ZIP: {name}")
            if name.startswith(".") or any(part.startswith(".") for part in PurePosixPath(name).parts):
                raise ValueError(f"Hidden asset in client ZIP: {name}")
            if not (name.startswith(("Interface/AddOns/EraTalents/", "licenses/"))
                    or name in ("Data/patch-V.mpq", "README.txt", "SOURCE_MANIFEST.json")):
                raise ValueError(f"Unexpected client ZIP asset: {name}")
            folded.add(name.casefold())
            files[name] = archive.read(entry)
    required = ("Data/patch-V.mpq", "README.txt", "SOURCE_MANIFEST.json", "licenses/mod-era-talents.txt",
                "licenses/mod-individual-progression.txt", "licenses/StormLib.txt",
                "Interface/AddOns/EraTalents/EraTalents.toc", "Interface/AddOns/EraTalents/LICENSE",
                "Interface/AddOns/EraTalents/SOURCE_REVISION.txt")
    for name in required:
        if not files.get(name):
            raise ValueError(f"Missing client ZIP asset: {name}")
    manifest = json.loads(files["SOURCE_MANIFEST.json"])
    if manifest.get("schemaVersion") != 1 or manifest.get("clientInterface") != 30300:
        raise ValueError("Invalid historical client source manifest")
    historical = historical_class_data(lock)
    if historical is not None:
        if manifest.get("historicalClassData") != historical:
            raise ValueError("Historical class data provenance differs from lock")
        for name in (historical["notice"], historical["license"], *historical.get("licenses", [])):
            if not files.get(name):
                raise ValueError(f"Missing historical class data notice or license: {name}")
    elif "historicalClassData" in manifest:
        raise ValueError("Historical class data provenance is not locked")
    patch = lock["clientPatch"]
    verify_native_spell_restoration_report(manifest.get("nativeSpellRestorations"), patch)
    for key, module_key in (("eraModule", "eraModule"), ("baseModule", "baseModule")):
        expected = locked_module(lock, patch[module_key])
        actual = manifest[key]
        if actual.get("revision") != expected["revision"] or actual.get("url") != expected["url"]:
            raise ValueError(f"Client source identity differs from lock: {key}")
        if set(actual.get("patches", {})) != set(expected.get("patches", [])):
            raise ValueError(f"Client source patches differ from lock: {key}")
    if manifest.get("stormLib") != patch["stormLib"] or manifest.get("baseArchive") != patch["baseArchive"]:
        raise ValueError("Client build dependencies differ from lock")
    if patch.get("localizations"):
        if manifest.get("localizations") != patch["localizations"]:
            raise ValueError("Client localization source differs from lock")
        if not files.get("licenses/client-locales.txt"):
            raise ValueError("Missing client localization source notice")
    if not re.fullmatch(r"[a-f0-9]{8}", manifest.get("generation", "")):
        raise ValueError("Invalid client generation")
    era = locked_module(lock, patch["eraModule"])
    if files["Interface/AddOns/EraTalents/SOURCE_REVISION.txt"].decode().strip() != era["revision"]:
        raise ValueError("Addon source revision differs from lock")
    expected_files = manifest.get("files", {})
    if set(expected_files) != set(files) - {"SOURCE_MANIFEST.json"}:
        raise ValueError("Client ZIP assets differ from manifest")
    for name, content in files.items():
        if name != "SOURCE_MANIFEST.json" and expected_files[name] != sha(content):
            raise ValueError(f"Client ZIP asset hash differs from manifest: {name}")
    toc = files["Interface/AddOns/EraTalents/EraTalents.toc"].decode("utf-8")
    if re.findall(r"(?m)^##\s*Interface\s*:\s*(\d+)\s*$", toc) != ["30300"]:
        raise ValueError("EraTalents must declare WotLK Interface 30300 once")
    for line in toc.splitlines():
        asset = line.strip().replace("\\", "/")
        if asset and not asset.startswith("#"):
            relative_path(asset)
            if not files.get(f"Interface/AddOns/EraTalents/{asset}"):
                raise ValueError(f"Missing EraTalents TOC asset: {asset}")
    with tempfile.TemporaryDirectory(prefix="era-client-runtime-verify-") as temporary:
        addon = Path(temporary)
        prefix = "Interface/AddOns/EraTalents/"
        assets = {name[len(prefix):]: content for name, content in files.items() if name.startswith(prefix)}
        for name, content in assets.items():
            path = addon / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        if set(ADDON_RUNTIME.runtime_paths(addon, "EraTalents.toc")) != set(assets):
            raise ValueError("Development-only addon asset in client ZIP")
    return files, manifest


def build(args):
    repository = args.repository.resolve()
    lock = json.loads((repository / "versions.lock.json").read_text())
    if lock.get("schemaVersion") != 1 or not VERSION.fullmatch(args.version):
        raise ValueError("Invalid manifest schema or package version")
    spec = lock["clientPatch"]
    if not VERSION.fullmatch(spec["name"]):
        raise ValueError("Invalid historical client archive name")
    storm = spec["stormLib"]
    if not SHA.fullmatch(storm["revision"]) or not GITHUB_URL.fullmatch(storm["url"]):
        raise ValueError("StormLib must have a locked GitHub URL and full commit SHA")
    era_entry = locked_module(lock, spec["eraModule"])
    ip_entry = locked_module(lock, spec["baseModule"])
    historical_files = historical_class_files(repository, lock)
    cache = repository / ".module-cache"
    cache.mkdir(exist_ok=True)
    storm_source = cache / "client-tools-stormlib"
    if not (storm_source / ".git").exists():
        run([args.git, "init", "--quiet", str(storm_source)], quiet=True)
    available = subprocess.run([args.git, "-C", str(storm_source), "cat-file", "-e", f"{storm['revision']}^{{commit}}"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0
    if not available:
        run([args.git, "-C", str(storm_source), "fetch", "--depth=1", storm["url"], storm["revision"]], quiet=True)
    with tempfile.TemporaryDirectory(prefix="era-client-", dir=cache) as temp:
        stage = Path(temp)
        storm_export = stage / "StormLib"
        export_module(repository, {**storm, "name": "StormLib", "source": ".module-cache/client-tools-stormlib"}, storm_export, args.git)
        era, ip = stage / "mod-era-talents", stage / "mod-individual-progression"
        era_identity = export_module(repository, era_entry, era, args.git)
        ip_identity = export_module(repository, ip_entry, ip, args.git)
        base_archive = ip / relative_path(spec["baseArchive"])
        base_dir = stage / "base"
        base_dir.mkdir()
        # Extract one locked patch file, never the separately shipped server DBC.
        run([args.sevenzip, "x", "-y", f"-o{base_dir}", str(base_archive), "patch-V.mpq"], quiet=True)
        base = base_dir / "patch-V.mpq"
        if not base.is_file():
            raise ValueError("Locked IP archive does not contain patch-V.mpq")
        tool_build = stage / "tools-build"
        run([args.cmake, "-S", str(repository / "cmake/era-client-tools"), "-B", str(tool_build),
             f"-DSTORM_SOURCE_DIR={storm_export}", f"-DERA_SOURCE_DIR={era}", "-DCMAKE_BUILD_TYPE=Release"], quiet=True)
        run([args.cmake, "--build", str(tool_build), "--parallel", "4"], quiet=True)
        mpqread, mpqpack = tool_build / "mpqread", tool_build / "mpqpack"
        sys.path.insert(0, str(era / "tools"))
        generator = importlib.import_module("gen_era_talents")
        spell_builder = importlib.import_module("build_client_dbc")
        skill_builder = importlib.import_module("build_client_skilllineability")
        datasets = []
        for line in (era / "era-data/datasets.txt").read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                parts = line.split()
                if len(parts) != 3:
                    raise ValueError("Malformed era dataset manifest")
                datasets.append(str(era / "era-data" / relative_path(parts[0])))
        generation = generator.generation_stamp(datasets)
        sql = (era / "data/sql/world/base/2026_08_14_11_era_talent_meta.sql").read_text()
        if re.findall(r"VALUES\s*\('generation',\s*'([a-f0-9]{8})'\)", sql) != [generation]:
            raise ValueError("Era module server SQL and client generation differ; regenerate all artifacts")
        spell_raw = read_mpq(mpqread, base, INTERNAL_SPELL, stage / "base-spell.dbc")
        skill_raw = read_mpq(mpqread, base, INTERNAL_SKILL, stage / "base-skill.dbc")
        localized_tables, localization_reports = {}, {}
        localization_identity = None
        restoration_report = None
        if spec.get("localizations"):
            donors, overrides, localization_identity = CLIENT_LOCALES.load_german_inputs(repository, spec["localizations"])
        if spec.get("nativeSpellRestorations"):
            contract_path = era / relative_path(spec["nativeSpellRestorations"])
            if str(contract_path) not in datasets:
                raise ValueError("Native spell restoration contract must be a generated era dataset")
            contract = generator._load(str(contract_path)).get("clientNativeSpellRestoration")
            if localization_identity is None or "Spell.enUS.dbc" not in donors:
                raise ValueError("Native spell restoration requires the locked English spell donor")
            spell_raw, restoration_report = restore_native_spell_fields(
                spell_raw, donors["Spell.enUS.dbc"], contract, generator.COLS, generator.COLTYPES)
            restoration_report["contractFile"] = spec["nativeSpellRestorations"]
            verify_native_spell_restoration_report(restoration_report, spec)
            (stage / "base-spell.dbc").write_bytes(spell_raw)
        if spec.get("localizations"):
            for filename in CLIENT_LOCALES.DBC_LAYOUTS:
                internal = "DBFilesClient\\" + filename
                original = spell_raw if filename == "Spell.dbc" else read_mpq(mpqread, base, internal, stage / "locale-base.dbc")
                if filename == "Spell.dbc" and "Spell.enUS.dbc" in donors:
                    CLIENT_LOCALES.verify_source_semantics(original, donors["Spell.enUS.dbc"], filename, overrides[filename])
                localized, report = CLIENT_LOCALES.merge_german_text(original, donors[filename], filename, overrides[filename])
                if report["fallbackFields"]:
                    raise ValueError(f"Missing authored German translations: {filename} {report['fallbackFields']}")
                localized_tables[internal] = localized
                localization_reports[filename] = report
                if filename == "Spell.dbc":
                    spell_raw = localized
                    (stage / "base-spell.dbc").write_bytes(localized)
        spell_builder.build(datasets, stage / "base-spell.dbc", stage / "Spell.dbc", generation)
        skill_builder.build(datasets, stage / "base-skill.dbc", stage / "SkillLineAbility.dbc")
        merged_spell = (stage / "Spell.dbc").read_bytes()
        merged_skill = (stage / "SkillLineAbility.dbc").read_bytes()
        custom = spell_builder._client_rows(datasets, generator.read_dbc_templates(stage / "base-spell.dbc"))
        if restoration_report is not None and set(restoration_report["contract"]["spellIds"]) & set(custom):
            raise ValueError("Native spell restoration IDs overlap authored era helpers")
        verify_merged_spell(spell_raw, merged_spell, generation, set(custom) | {generator.SENTINEL_SPELL_ID}, custom)
        custom_skills = {row[2] for row in skill_builder._rows(datasets)}
        verify_merged_skill(skill_raw, merged_skill, custom_skills)
        output_mpq = stage / "patch-V.mpq"
        shutil.copyfile(base, output_mpq)
        merged_tables = {INTERNAL_SPELL: stage / "Spell.dbc", INTERNAL_SKILL: stage / "SkillLineAbility.dbc"}
        for internal, content in localized_tables.items():
            if internal != INTERNAL_SPELL:
                source = stage / (internal.split("\\")[-1])
                source.write_bytes(content)
                merged_tables[internal] = source
        for internal, source in merged_tables.items():
            os.utime(source, (946684800, 946684800))
            run([str(mpqpack), str(output_mpq), internal, str(source)], quiet=True)
            if read_mpq(mpqread, output_mpq, internal, stage / "verify.dbc") != source.read_bytes():
                raise ValueError(f"MPQ did not retain generated DBC: {internal}")
        # Preserve all entries other than the explicitly verified merged DBCs.
        entries = read_mpq(mpqread, base, "(listfile)", stage / "listfile").decode().splitlines()
        preserved = {}
        for internal in entries:
            if internal in merged_tables or internal.startswith("("):
                continue
            before = read_mpq(mpqread, base, internal, stage / "base-entry")
            after = read_mpq(mpqread, output_mpq, internal, stage / "merged-entry")
            if before != after:
                raise ValueError(f"Merged MPQ changed IP client patch entry: {internal}")
            preserved[internal] = sha(before)
        files = addon_files(era / "client-addon/EraTalents", era)
        files["Interface/AddOns/EraTalents/SOURCE_REVISION.txt"] = (era_entry["revision"] + "\n").encode()
        files["Data/patch-V.mpq"] = output_mpq.read_bytes()
        for name, source in (("mod-era-talents", era), ("mod-individual-progression", ip), ("StormLib", storm_export)):
            candidates = [source / "LICENSE", source / "LICENSE.md", source / "LICENSE.txt"]
            license_file = next((path for path in candidates if path.is_file()), None)
            if license_file is None:
                raise ValueError(f"Client build dependency has no license: {name}")
            files[f"licenses/{name}.txt"] = license_file.read_bytes()
        if localization_identity is not None:
            files["licenses/client-locales.txt"] = (
                "German World of Warcraft 3.3.5a client text source (build 12340).\n"
                f"Source: {localization_identity['url']}\nRevision: {localization_identity['revision']}\n"
                "Only German text fields are imported; IP gameplay fields remain intact.\n"
                "World of Warcraft client data retains its original terms. Neither the launcher MIT\n"
                "license nor the TrinityCore code license is applied to these extracted game data.\n"
                "Source checksums and authored restored-entry overrides are recorded in SOURCE_MANIFEST.json.\n"
            ).encode()
        files.update(historical_files)
        files["README.txt"] = ("EraTalents client files for World of Warcraft 3.3.5a (build 12340).\n\n"
            "Close WoW completely. Replace Interface/AddOns/EraTalents/ and Data/patch-V.mpq with this\n"
            "matching package, then restart WoW. Both are required; /reload cannot load an MPQ.\n"
            "The server updates through normal startup.exe launches. Install client files manually;\n"
            "the client and server generations must match. Later-loading DBC patches can override this patch.\n"
            f"Generation: {generation}\n"
            "In game: /run print(GetSpellInfo(932999)) should show EraTalents Gen and this generation.\n"
            "Bots need server files only. This ZIP contains an addon and the merged IP client patch.\n").encode()
        manifest = {"schemaVersion": 1, "clientInterface": 30300, "packageVersion": args.version,
                    "generation": generation, "eraModule": era_identity, "baseModule": ip_identity,
                    "stormLib": storm, "baseArchive": spec["baseArchive"], "baseArchiveSha256": sha(base_archive.read_bytes()),
                    "baseMpqSha256": sha(base.read_bytes()), "preservedIpEntries": preserved,
                    "mergedDbcSha256": {internal: sha(source.read_bytes()) for internal, source in merged_tables.items()},
                    "files": {name: sha(content) for name, content in files.items()}}
        if localization_identity is not None:
            manifest["localizations"] = {"deDE": localization_identity}
            manifest["localizedDbcReports"] = localization_reports
        if "historicalClassData" in lock:
            manifest["historicalClassData"] = lock["historicalClassData"]
        if restoration_report is not None:
            manifest["nativeSpellRestorations"] = restoration_report
        files["SOURCE_MANIFEST.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        args.output.mkdir(parents=True, exist_ok=True)
        output = args.output / f"{spec['name']}-{args.version}.zip"
        write_zip(output, files)
        verified_files, verified_manifest = verify_zip(output, lock)
        if verified_files != files or verified_manifest != manifest:
            raise ValueError("Packaged client files differ from verified build inputs")
        print(f"Verified historical client ZIP: {output} ({len(files)} files, generation {generation})")
        print(f"SHA-256: {sha(output.read_bytes())}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--git", default="git")
    parser.add_argument("--sevenzip", default="7z")
    args = parser.parse_args()
    try:
        build(args)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print(f"Historical client packaging failed: {error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr.decode(errors="replace"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
