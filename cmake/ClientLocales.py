"""Merge pinned client translations without replacing progression mechanics."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import tempfile
from urllib.request import Request, urlopen

DBC_LAYOUTS = {
    "Achievement.dbc": {"fields": 62, "localized": {"name": 4, "description": 21, "reward": 43}},
    "SkillLine.dbc": {"fields": 56, "localized": {"name": 3, "description": 20, "alternate verb": 38}},
    "Spell.dbc": {"fields": 234, "localized": {"name": 136, "rank": 153, "description": 170, "aura description": 187}},
    "SpellItemEnchantment.dbc": {"fields": 38, "localized": {"name": 14}},
}
GERMAN_SLOT = 3


def _records(raw: bytes, filename: str):
    fields = DBC_LAYOUTS[filename]["fields"]
    if len(raw) < 20:
        raise ValueError(f"Truncated DBC: {filename}")
    magic, count, actual_fields, size, strings_size = struct.unpack_from("<4s4I", raw)
    if (magic != b"WDBC" or actual_fields != fields or size != fields * 4
            or len(raw) != 20 + count * size + strings_size):
        raise ValueError(f"Invalid DBC layout or length: {filename}")
    records = {}
    for index in range(count):
        row = raw[20 + index * size:20 + (index + 1) * size]
        key = struct.unpack_from("<I", row)[0]
        if key in records:
            raise ValueError(f"Duplicate DBC record ID: {filename} {key}")
        records[key] = row
    strings = raw[20 + count * size:]
    if not strings or strings[0] != 0 or strings[-1] != 0:
        raise ValueError(f"Invalid DBC string block: {filename}")
    return records, strings


def _text(row: bytes, field: int, strings: bytes) -> str:
    offset = struct.unpack_from("<I", row, field * 4)[0]
    if offset >= len(strings) or (offset and strings[offset - 1] != 0):
        raise ValueError("Invalid localized string offset")
    end = strings.find(b"\0", offset)
    if end < 0:
        raise ValueError("Unterminated localized string")
    try:
        return strings[offset:end].decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Invalid localized UTF-8 text") from None


def _desired(base_row, base_strings, donor_row, donor_strings, start, label, override):
    current = _text(base_row, start + GERMAN_SLOT, base_strings)
    english = _text(base_row, start, base_strings)
    if label in override:
        translated = override[label]
        if not isinstance(translated, str) or "\0" in translated or (english and not translated):
            raise ValueError(f"Invalid German override: {label}")
        return translated, "override"
    if current or not english:
        return current, "preserved"
    translated = _text(donor_row, start + GERMAN_SLOT, donor_strings) if donor_row else ""
    if translated:
        return translated, "source"
    # Restored IP rows require authored text. Keep a visible English fallback
    # for a newly added row until its corresponding translation is supplied.
    if label == "rank" and re.fullmatch(r"Rank \d+", english):
        return english.replace("Rank ", "Rang ", 1), "rank"
    return english, "fallback"


def _overrides(overrides, records, filename, excluded):
    labels = set(DBC_LAYOUTS[filename]["localized"])
    result = {}
    for key, fields in overrides.items():
        if not isinstance(key, str) or not key.isdecimal() or str(int(key)) != key:
            raise ValueError(f"Invalid German override ID: {filename} {key}")
        key = int(key)
        if key not in records or key in excluded:
            raise ValueError(f"German override targets an absent or excluded row: {filename} {key}")
        if not isinstance(fields, dict) or not set(fields).issubset(labels):
            raise ValueError(f"Unknown German override field: {filename} {key}")
        result[key] = fields
    return result


def merge_german_text(base: bytes, donor: bytes, filename: str, overrides: dict,
                      excluded_ids: set[int] | None = None):
    records, strings = _records(base, filename)
    donor_records, donor_strings = _records(donor, filename)
    excluded = excluded_ids or set()
    overrides = _overrides(overrides, records, filename, excluded)
    output_strings = bytearray(strings)
    offsets = {}
    offset = 0
    for value in strings.split(b"\0")[:-1]:
        offsets.setdefault(value, offset)
        offset += len(value) + 1
    rows = []
    for key, original in records.items():
        row = bytearray(original)
        if key not in excluded:
            for label, start in DBC_LAYOUTS[filename]["localized"].items():
                text, _ = _desired(original, strings, donor_records.get(key), donor_strings,
                                   start, label, overrides.get(key, {}))
                if text == _text(original, start + GERMAN_SLOT, strings):
                    continue
                encoded = text.encode("utf-8")
                if encoded not in offsets:
                    offsets[encoded] = len(output_strings)
                    output_strings.extend(encoded + b"\0")
                struct.pack_into("<I", row, (start + GERMAN_SLOT) * 4, offsets[encoded])
        rows.append(bytes(row))
    fields = DBC_LAYOUTS[filename]["fields"]
    merged = struct.pack("<4s4I", b"WDBC", len(rows), fields, fields * 4, len(output_strings))
    merged += b"".join(rows) + bytes(output_strings)
    report = verify_german_merge(base, merged, donor, filename,
                                 {str(k): v for k, v in overrides.items()}, excluded)
    return merged, report


def verify_german_merge(base: bytes, merged: bytes, donor: bytes, filename: str,
                        overrides: dict, excluded_ids: set[int] | None = None):
    records, strings = _records(base, filename)
    merged_records, merged_strings = _records(merged, filename)
    donor_records, donor_strings = _records(donor, filename)
    if list(records) != list(merged_records):
        raise ValueError(f"German merge changed IP record IDs or order: {filename}")
    if not merged_strings.startswith(strings):
        raise ValueError(f"German merge changed the original string block: {filename}")
    excluded = excluded_ids or set()
    overrides = _overrides(overrides, records, filename, excluded)
    report = {"records": len(records), "changedFields": 0, "sourceFields": 0,
              "overrideFields": 0, "fallbackFields": []}
    for key, original in records.items():
        row = merged_records[key]
        if key in excluded:
            if row != original:
                raise ValueError(f"German merge changed an excluded row: {filename} {key}")
            continue
        original_other, merged_other = bytearray(original), bytearray(row)
        for label, start in DBC_LAYOUTS[filename]["localized"].items():
            expected, source = _desired(original, strings, donor_records.get(key), donor_strings,
                                        start, label, overrides.get(key, {}))
            actual = _text(row, start + GERMAN_SLOT, merged_strings)
            if actual != expected:
                raise ValueError(f"German translation differs from source: {filename} {key} {label}")
            # Preserve masks, mechanics and every other language byte for byte.
            field = (start + GERMAN_SLOT) * 4
            original_other[field:field + 4] = b"\0" * 4
            merged_other[field:field + 4] = b"\0" * 4
            if actual != _text(original, start + GERMAN_SLOT, strings):
                report["changedFields"] += 1
            if source == "source":
                report["sourceFields"] += 1
            elif source == "override":
                report["overrideFields"] += 1
            elif source == "fallback":
                report["fallbackFields"].append({"id": key, "field": label})
        if original_other != merged_other:
            raise ValueError(f"German merge changed mechanics, masks or another locale: {filename} {key}")
    return report


def verify_source_semantics(base: bytes, english_source: bytes, filename: str, overrides: dict):
    """Require authored text when IP's English tooltip differs from stock Wrath."""
    records, strings = _records(base, filename)
    stock, stock_strings = _records(english_source, filename)
    overrides = _overrides(overrides, records, filename, set())
    missing = []
    for key, row in records.items():
        for label, start in DBC_LAYOUTS[filename]["localized"].items():
            english = " ".join(_text(row, start, strings).split())
            original = " ".join(_text(stock[key], start, stock_strings).split()) if key in stock else ""
            if english and english != original and label not in overrides.get(key, {}):
                missing.append({"id": key, "field": label})
    if missing:
        raise ValueError(f"Historical client text needs authored German overrides: {filename} {len(missing)} fields, {missing[:8]}")


def _pinned_dbc(path: Path, filename: str, url: str, expected: str):
    if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ValueError(f"Invalid client text source checksum: {filename}")
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
                temporary = Path(output.name)
                with urlopen(Request(url, headers={"User-Agent": "Playerbots-client-locales"}), timeout=120) as response:
                    shutil.copyfileobj(response, output)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected:
                raise ValueError(f"Client text source checksum mismatch: {filename}")
            temporary.replace(path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    raw = path.read_bytes()
    _records(raw, filename)
    return raw


def load_german_inputs(repository: Path, configuration: dict):
    """Fetch pinned translations and tooltip comparison; never clone the full data set."""
    source = configuration["deDE"]
    match = re.fullmatch(r"https://github.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\.git", source["url"])
    if (not match or not re.fullmatch(r"[a-f0-9]{40}", source["revision"])
            or source["clientBuild"] != 12340 or source["sourcePath"] != "dbc/deDE"
            or set(source["files"]) != set(DBC_LAYOUTS)):
        raise ValueError("Invalid pinned German client text source")
    cache = repository / ".module-cache/client-locales" / source["revision"] / "deDE"
    cache.mkdir(parents=True, exist_ok=True)
    donors = {}
    url_root = f"https://raw.githubusercontent.com/{match[1]}/{source['revision']}/dbc"
    for filename, expected in source["files"].items():
        donors[filename] = _pinned_dbc(cache / filename, filename, f"{url_root}/deDE/{filename}", expected)
    if source.get("englishSpellSha256"):
        donors["Spell.enUS.dbc"] = _pinned_dbc(cache / "Spell.enUS.dbc", "Spell.dbc",
                                             f"{url_root}/Spell.dbc", source["englishSpellSha256"])
    override_path = source["overrides"]
    parts = override_path.split("/")
    if any(p in ("", ".", "..") for p in parts) or "\\" in override_path or ":" in override_path:
        raise ValueError("Invalid German override path")
    raw_overrides = (repository / override_path).read_bytes()
    override_digest = hashlib.sha256(raw_overrides).hexdigest()
    if override_digest != source["overridesSha256"]:
        raise ValueError("German override checksum differs from the dependency manifest")
    overrides = json.loads(raw_overrides)
    if set(overrides) != set(DBC_LAYOUTS):
        raise ValueError("German overrides must cover the four localized client tables")
    identity = dict(source)
    identity["overridesSha256"] = override_digest
    return donors, overrides, identity
