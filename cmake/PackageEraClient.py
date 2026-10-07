#!/usr/bin/env python3
"""Build and verify the era client MPQ using only manifest-pinned inputs.

The IP client archive is the base. Both DBC generators come from the locked,
earned-patched era module. No upstream bootstrap or latest-clone script runs.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
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
INTERNAL_SPELL = r"DBFilesClient\Spell.dbc"
INTERNAL_SKILL = r"DBFilesClient\SkillLineAbility.dbc"
FIXED_TIME = (2000, 1, 1, 0, 0, 0)
SPELL_LOCALIZED_FIELDS = {"name": 136, "rank": 153, "description": 170, "aura description": 187}
SPELL_LOCALE_COUNT = 16


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
    result = subprocess.run(command, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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


def verify_merged_spell(base: bytes, merged: bytes, stamp: str, custom_ids):
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
    # Authored helper text is the fallback for each locale. Check custom rows
    # only: the original IP records and their translations remain untouched.
    for key in custom_ids:
        record = records[key]
        for label, field in SPELL_LOCALIZED_FIELDS.items():
            english = text(record, field)
            if label == "name" and not english:
                raise ValueError(f"Merged client visible era spell has an empty name: {key}")
            for locale in range(1, SPELL_LOCALE_COUNT):
                if text(record, field + locale) != english:
                    raise ValueError(
                        f"Merged client localized spell {label} differs from enUS: spell {key}, locale slot {locale}")


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
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symbolic link in addon: {path}")
        if path.is_file():
            relative = relative_path(path.relative_to(source).as_posix())
            result[f"Interface/AddOns/EraTalents/{relative}"] = path.read_bytes()
    for name in ("LICENSE", "README.md"):
        result[f"Interface/AddOns/EraTalents/{name}"] = (module / name).read_bytes()
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
            if not (name.startswith("Interface/AddOns/EraTalents/") or name.startswith("licenses/")
                    or name in ("Data/patch-V.mpq", "README.txt", "SOURCE_MANIFEST.json")):
                raise ValueError(f"Unexpected client ZIP asset: {name}")
            folded.add(name.casefold())
            files[name] = archive.read(entry)
    required = ("Data/patch-V.mpq", "README.txt", "SOURCE_MANIFEST.json", "licenses/mod-era-talents.txt",
                "licenses/mod-individual-progression.txt", "licenses/StormLib.txt",
                "Interface/AddOns/EraTalents/EraTalents.toc", "Interface/AddOns/EraTalents/LICENSE",
                "Interface/AddOns/EraTalents/README.md", "Interface/AddOns/EraTalents/SOURCE_REVISION.txt")
    for name in required:
        if not files.get(name):
            raise ValueError(f"Missing client ZIP asset: {name}")
    manifest = json.loads(files["SOURCE_MANIFEST.json"])
    if manifest.get("schemaVersion") != 1 or manifest.get("clientInterface") != 30300:
        raise ValueError("Invalid historical client source manifest")
    patch = lock["clientPatch"]
    for key, module_key in (("eraModule", "eraModule"), ("baseModule", "baseModule")):
        expected = locked_module(lock, patch[module_key])
        actual = manifest[key]
        if actual.get("revision") != expected["revision"] or actual.get("url") != expected["url"]:
            raise ValueError(f"Client source identity differs from lock: {key}")
        if set(actual.get("patches", {})) != set(expected.get("patches", [])):
            raise ValueError(f"Client source patches differ from lock: {key}")
    if manifest.get("stormLib") != patch["stormLib"] or manifest.get("baseArchive") != patch["baseArchive"]:
        raise ValueError("Client build dependencies differ from lock")
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
    cache = repository / ".module-cache"
    cache.mkdir(exist_ok=True)
    storm_source = cache / "client-tools-stormlib"
    if not (storm_source / ".git").exists():
        run([args.git, "init", "--quiet", str(storm_source)], quiet=True)
    available = subprocess.run([args.git, "-C", str(storm_source), "cat-file", "-e", f"{storm['revision']}^{{commit}}"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
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
        spell_builder.build(datasets, stage / "base-spell.dbc", stage / "Spell.dbc", generation)
        skill_builder.build(datasets, stage / "base-skill.dbc", stage / "SkillLineAbility.dbc")
        merged_spell = (stage / "Spell.dbc").read_bytes()
        merged_skill = (stage / "SkillLineAbility.dbc").read_bytes()
        custom = spell_builder._client_rows(datasets, generator.read_dbc_templates(stage / "base-spell.dbc"))
        verify_merged_spell(spell_raw, merged_spell, generation, set(custom) | {generator.SENTINEL_SPELL_ID})
        custom_skills = {row[2] for row in skill_builder._rows(datasets)}
        verify_merged_skill(skill_raw, merged_skill, custom_skills)
        output_mpq = stage / "patch-V.mpq"
        shutil.copyfile(base, output_mpq)
        for internal, source in ((INTERNAL_SPELL, stage / "Spell.dbc"), (INTERNAL_SKILL, stage / "SkillLineAbility.dbc")):
            os.utime(source, (946684800, 946684800))
            run([str(mpqpack), str(output_mpq), internal, str(source)], quiet=True)
            if read_mpq(mpqread, output_mpq, internal, stage / "verify.dbc") != source.read_bytes():
                raise ValueError(f"MPQ did not retain generated DBC: {internal}")
        # Preserve all original client patch entries other than the two merged DBCs.
        entries = read_mpq(mpqread, base, "(listfile)", stage / "listfile").decode().splitlines()
        preserved = {}
        for internal in entries:
            if internal in (INTERNAL_SPELL, INTERNAL_SKILL) or internal.startswith("("):
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
        files["README.txt"] = ("EraTalents client files for World of Warcraft 3.3.5a (build 12340).\n\n"
            "Close WoW completely. Copy Interface/AddOns/EraTalents to the matching client folder.\n"
            "Copy Data/patch-V.mpq into the client Data folder, replacing the previous IP patch-V.\n"
            "Keep the installed addon folder named EraTalents. Restart WoW; /reload does not load MPQs.\n"
            "Use the client package from the same server build. Later-loading DBC patches can override it.\n"
            f"Generation: {generation}\n"
            "In game: /run print(GetSpellInfo(932999)) should show EraTalents Gen and this generation.\n"
            "Bots need server files only. This ZIP contains an addon and the merged IP client patch.\n").encode()
        manifest = {"schemaVersion": 1, "clientInterface": 30300, "packageVersion": args.version,
                    "generation": generation, "eraModule": era_identity, "baseModule": ip_identity,
                    "stormLib": storm, "baseArchive": spec["baseArchive"], "baseArchiveSha256": sha(base_archive.read_bytes()),
                    "baseMpqSha256": sha(base.read_bytes()), "preservedIpEntries": preserved,
                    "mergedDbcSha256": {INTERNAL_SPELL: sha(merged_spell), INTERNAL_SKILL: sha(merged_skill)},
                    "files": {name: sha(content) for name, content in files.items()}}
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
