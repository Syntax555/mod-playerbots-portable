#!/usr/bin/env python3
"""Regression coverage for missing German texts in the IP client DBC tables."""
import importlib.util
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("client_locales", ROOT / "cmake/ClientLocales.py")
LOCALES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOCALES)
GERMAN = 3
LOCALE_COUNT = 16
FILES = ("Spell.dbc", "Achievement.dbc", "SkillLine.dbc", "SpellItemEnchantment.dbc")


def fixture(filename, records, numeric_bias=0):
    """Build independent DBC records with visibly different gameplay data."""
    layout = LOCALES.DBC_LAYOUTS[filename]
    fields = layout["fields"]
    strings = bytearray(b"\0")
    rows = []
    for key, localized in records:
        values = [numeric_bias + key * 1000 + field for field in range(fields)]
        values[0] = key
        for label, start in layout["localized"].items():
            for locale in range(LOCALE_COUNT):
                value = localized.get(label, {}).get(locale, "")
                if value:
                    values[start + locale] = len(strings)
                    strings.extend(value.encode("utf-8") + b"\0")
                else:
                    values[start + locale] = 0
        rows.append(struct.pack(f"<{fields}I", *values))
    return (struct.pack("<4s4I", b"WDBC", len(rows), fields, fields * 4, len(strings))
            + b"".join(rows) + bytes(strings))


def decoded(raw):
    _, count, fields, row_size, _ = struct.unpack_from("<4s4I", raw)
    rows = [list(struct.unpack_from(f"<{fields}I", raw, 20 + index * row_size))
            for index in range(count)]
    return rows, raw[20 + count * row_size:]


def value(raw, key, field):
    rows, strings = decoded(raw)
    row = next(row for row in rows if row[0] == key)
    offset = row[field]
    end = strings.index(b"\0", offset)
    return strings[offset:end].decode("utf-8")


def edit_field(raw, key, field, new_value):
    result = bytearray(raw)
    rows, _ = decoded(raw)
    index = next(index for index, row in enumerate(rows) if row[0] == key)
    struct.pack_into("<I", result, 20 + (index * len(rows[0]) + field) * 4, new_value)
    return bytes(result)


def localized_texts(filename, german=False, foreign_prefix="Original"):
    return {
        label: {locale: (f"Deutscher {label}: Stärke erhöht" if locale == GERMAN and german
                         else "" if locale == GERMAN
                         else f"{foreign_prefix} {label} locale {locale}")
                for locale in range(LOCALE_COUNT)}
        for label in LOCALES.DBC_LAYOUTS[filename]["localized"]
    }


class GermanClientLocaleTests(unittest.TestCase):
    def merge(self, filename, base, donor, overrides=None, excluded=None):
        merged, report = LOCALES.merge_german_text(
            base, donor, filename, overrides or {}, excluded)
        self.assertIsInstance(report, dict)
        self.assertIsInstance(LOCALES.verify_german_merge(
            base, merged, donor, filename, overrides or {}, excluded), dict)
        return merged

    def test_normal_german_names_and_descriptions_are_restored_in_all_tables(self):
        for filename in FILES:
            with self.subTest(filename=filename):
                base = fixture(filename, [(42, localized_texts(filename))])
                donor = fixture(filename, [(42, localized_texts(filename, german=True))], 500000)
                merged = self.merge(filename, base, donor)
                for label, start in LOCALES.DBC_LAYOUTS[filename]["localized"].items():
                    self.assertEqual(value(merged, 42, start + GERMAN),
                                     f"Deutscher {label}: Stärke erhöht")

    def test_donor_gameplay_data_and_other_languages_cannot_replace_ip_values(self):
        for filename in FILES:
            with self.subTest(filename=filename):
                base = fixture(filename, [(99, localized_texts(filename)),
                                          (7, localized_texts(filename))])
                donor = fixture(filename, [(7, localized_texts(filename, True, "Donor")),
                                           (99, localized_texts(filename, True, "Donor")),
                                           (500, localized_texts(filename, True))], 800000)
                merged = self.merge(filename, base, donor)
                before_rows, before_strings = decoded(base)
                after_rows, after_strings = decoded(merged)
                german_fields = {start + GERMAN for start in
                                 LOCALES.DBC_LAYOUTS[filename]["localized"].values()}
                self.assertEqual([row[0] for row in after_rows], [99, 7])
                self.assertEqual(after_strings[:len(before_strings)], before_strings)
                for before, after in zip(before_rows, after_rows):
                    for field in range(len(before)):
                        if field not in german_fields:
                            self.assertEqual(after[field], before[field], (filename, field))

    def test_existing_german_translation_is_preserved(self):
        filename = "Spell.dbc"
        base = fixture(filename, [(42, localized_texts(filename, True, "Original"))])
        donor_texts = localized_texts(filename, True, "Donor")
        donor_texts["name"][GERMAN] = "Falscher Name aus Spender"
        donor = fixture(filename, [(42, donor_texts)], 500000)
        self.assertEqual(self.merge(filename, base, donor), base)

    def test_explicit_historical_enchantment_overrides_donor_and_existing_german(self):
        filename = "SpellItemEnchantment.dbc"
        base = fixture(filename, [(42, {"name": {0: "+15 Agility", GERMAN: "+20 Beweglichkeit"}})])
        donor = fixture(filename, [(42, {"name": {0: "+20 Agility", GERMAN: "+20 Beweglichkeit"}})])
        overrides = {"42": {"name": "+15 Beweglichkeit"}}
        merged = self.merge(filename, base, donor, overrides)
        start = LOCALES.DBC_LAYOUTS[filename]["localized"]["name"]
        self.assertEqual(value(merged, 42, start + GERMAN), "+15 Beweglichkeit")
        self.assertEqual(value(merged, 42, start), "+15 Agility")

    def test_suppressed_ip_text_is_not_reintroduced_from_donor(self):
        filename = "Achievement.dbc"
        base = fixture(filename, [(42, {})])
        donor = fixture(filename, [(42, localized_texts(filename, True))])
        self.assertEqual(self.merge(filename, base, donor), base)

    def test_unknown_historical_id_uses_visible_fallback_and_german_rank(self):
        filename = "Spell.dbc"
        base_texts = localized_texts(filename)
        base_texts["rank"][0] = "Rank 4"
        base = fixture(filename, [(9876, base_texts)])
        donor = fixture(filename, [(42, localized_texts(filename, True))])
        merged = self.merge(filename, base, donor)
        for label, start in LOCALES.DBC_LAYOUTS[filename]["localized"].items():
            expected = "Rang 4" if label == "rank" else base_texts[label][0]
            self.assertEqual(value(merged, 9876, start + GERMAN), expected)

    def test_empty_donor_german_uses_base_english_not_donor_english(self):
        filename = "Spell.dbc"
        base = fixture(filename, [(42, {"name": {0: "IP restored spell"}})])
        donor = fixture(filename, [(42, {"name": {0: "Unrelated donor name"}})])
        merged = self.merge(filename, base, donor)
        start = LOCALES.DBC_LAYOUTS[filename]["localized"]["name"]
        self.assertEqual(value(merged, 42, start + GERMAN), "IP restored spell")

    def test_custom_era_rows_are_excluded(self):
        filename = "Spell.dbc"
        base = fixture(filename, [(900001, localized_texts(filename)),
                                  (42, localized_texts(filename))])
        donor = fixture(filename, [(900001, localized_texts(filename, True)),
                                   (42, localized_texts(filename, True))])
        merged = self.merge(filename, base, donor, excluded={900001})
        before, _ = decoded(base)
        after, _ = decoded(merged)
        self.assertEqual(after[0], before[0])
        self.assertNotEqual(after[1], before[1])

    def test_override_targeting_excluded_custom_era_row_is_rejected(self):
        filename = "Spell.dbc"
        base = fixture(filename, [(900001, localized_texts(filename))])
        donor = fixture(filename, [(900001, localized_texts(filename, True))])
        overrides = {"900001": {"name": "Darf nicht verwendet werden"}}
        with self.assertRaises(ValueError):
            LOCALES.merge_german_text(base, donor, filename, overrides, {900001})

    def test_second_merge_is_byte_identical(self):
        filename = "Spell.dbc"
        base = fixture(filename, [(42, localized_texts(filename)),
                                  (9876, {"name": {0: "Legacy spell"}, "rank": {0: "Rank 2"}})])
        donor = fixture(filename, [(42, localized_texts(filename, True))])
        overrides = {"9876": {"name": "Historischer Zauber"}}
        merged = self.merge(filename, base, donor, overrides)
        self.assertEqual(self.merge(filename, merged, donor, overrides), merged)

    def test_invalid_dbc_schema_and_length_are_rejected(self):
        filename = "Spell.dbc"
        base = fixture(filename, [(42, localized_texts(filename))])
        donor = fixture(filename, [(42, localized_texts(filename, True))])
        bad_fields = bytearray(donor)
        struct.pack_into("<I", bad_fields, 8, 1)
        for malformed in (b"WDBC", donor[:-1], bytes(bad_fields), b"XXXX" + donor[4:]):
            with self.subTest(header=malformed[:20]):
                with self.assertRaises(ValueError):
                    LOCALES.merge_german_text(base, malformed, filename, {})

    def test_invalid_localized_string_offsets_and_utf8_are_rejected(self):
        filename = "Spell.dbc"
        base = fixture(filename, [(42, localized_texts(filename))])
        donor = fixture(filename, [(42, localized_texts(filename, True))])
        start = LOCALES.DBC_LAYOUTS[filename]["localized"]["name"] + GERMAN
        rows, strings = decoded(donor)
        german_offset = rows[0][start]
        invalid_utf8 = bytearray(donor)
        string_block = len(donor) - len(strings)
        invalid_utf8[string_block + german_offset] = 0xFF
        malformed = (
            edit_field(donor, 42, start, len(strings)),
            edit_field(donor, 42, start, german_offset + 1),
            bytes(invalid_utf8),
            donor[:-1] + b"x",
        )
        for candidate in malformed:
            with self.subTest(offset=decoded(candidate)[0][0][start]):
                with self.assertRaises(ValueError):
                    LOCALES.merge_german_text(base, candidate, filename, {})

    def test_duplicate_donor_ids_are_rejected(self):
        filename = "Achievement.dbc"
        base = fixture(filename, [(42, localized_texts(filename))])
        donor = fixture(filename, [(42, localized_texts(filename, True)),
                                   (42, localized_texts(filename, True))])
        with self.assertRaises(ValueError):
            LOCALES.merge_german_text(base, donor, filename, {})

    def test_verifier_rejects_erased_german_and_modified_gameplay(self):
        filename = "Spell.dbc"
        base = fixture(filename, [(42, localized_texts(filename))])
        donor = fixture(filename, [(42, localized_texts(filename, True))])
        merged = self.merge(filename, base, donor)
        name = LOCALES.DBC_LAYOUTS[filename]["localized"]["name"]
        for field, changed in ((name + GERMAN, 0), (1, 123456)):
            with self.subTest(field=field):
                candidate = edit_field(merged, 42, field, changed)
                with self.assertRaises(ValueError):
                    LOCALES.verify_german_merge(base, candidate, donor, filename, {})

    def test_verifier_rejects_changed_or_erased_other_locale_text(self):
        filename = "Achievement.dbc"
        base = fixture(filename, [(42, localized_texts(filename))])
        donor = fixture(filename, [(42, localized_texts(filename, True))])
        merged = self.merge(filename, base, donor)
        name = LOCALES.DBC_LAYOUTS[filename]["localized"]["name"]
        rows, strings = decoded(merged)
        for candidate in (edit_field(merged, 42, name + 2, 0),
                          edit_field(merged, 42, name + 2, rows[0][name + GERMAN])):
            with self.assertRaises(ValueError):
                LOCALES.verify_german_merge(base, candidate, donor, filename, {})
        changed_string = bytearray(merged)
        string_block = len(merged) - len(strings)
        changed_string[string_block + rows[0][name + 2]] = ord("X")
        with self.assertRaises(ValueError):
            LOCALES.verify_german_merge(base, bytes(changed_string), donor, filename, {})

    def test_verifier_rejects_reordered_records_and_changed_locale_masks(self):
        filename = "Spell.dbc"
        base = fixture(filename, [(99, localized_texts(filename)),
                                  (7, localized_texts(filename))])
        donor = fixture(filename, [(99, localized_texts(filename, True)),
                                   (7, localized_texts(filename, True))])
        merged = self.merge(filename, base, donor)
        row_size = LOCALES.DBC_LAYOUTS[filename]["fields"] * 4
        reordered = (merged[:20] + merged[20 + row_size:20 + 2 * row_size]
                     + merged[20:20 + row_size] + merged[20 + 2 * row_size:])
        name = LOCALES.DBC_LAYOUTS[filename]["localized"]["name"]
        changed_mask = edit_field(merged, 99, name + LOCALE_COUNT, 0)
        for candidate in (reordered, changed_mask):
            with self.assertRaises(ValueError):
                LOCALES.verify_german_merge(base, candidate, donor, filename, {})


class SourceTextSemanticsTests(unittest.TestCase):
    def test_earth_shock_interrupt_requires_override_instead_of_stock_slow_description(self):
        filename = "Spell.dbc"
        common = {"name": {0: "Earth Shock"}, "rank": {0: "Rank 1"}}
        ip = fixture(filename, [(8042, {**common, "description": {
            0: "Deals $s1 Nature damage and interrupts spellcasting for 2 sec."}})])
        stock = fixture(filename, [(8042, {**common, "description": {
            0: "Deals $s1 Nature damage and reduces melee attack speed for 8 sec."}})])
        with self.assertRaises(ValueError):
            LOCALES.verify_source_semantics(ip, stock, filename, {})
        self.assertIsNone(LOCALES.verify_source_semantics(ip, stock, filename, {
            "8042": {"description": "Verursacht $s1 Naturschaden und unterbricht Zauber für 2 Sek."}}))

    def test_restored_missing_spell_requires_every_nonempty_field_to_be_authored(self):
        filename = "Spell.dbc"
        ip = fixture(filename, [(9876, {"name": {0: "Restored historical spell"},
                                        "rank": {0: "Rank 2"},
                                        "description": {0: "Grants $s1 spell damage."},
                                        "aura description": {0: "Spell damage increased by $s1."}})])
        stock = fixture(filename, [(42, localized_texts(filename))])
        for overrides in ({}, {"9876": {"name": "Historischer Zauber"}}):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    LOCALES.verify_source_semantics(ip, stock, filename, overrides)
        self.assertIsNone(LOCALES.verify_source_semantics(ip, stock, filename, {
            "9876": {"name": "Historischer Zauber", "rank": "Rang 2",
                     "description": "Gewährt $s1 Zauberschaden.",
                     "aura description": "Zauberschaden um $s1 erhöht."}}))

    def test_whitespace_and_numeric_only_differences_do_not_require_overrides(self):
        filename = "Spell.dbc"
        ip = fixture(filename, [(42, {"name": {0: "Earth Shock"},
                                      "description": {0: "Deals $s1 damage.\n\n Interrupts casting."}})])
        stock = fixture(filename, [(42, {"name": {0: "Earth  Shock"},
                                         "description": {0: " Deals $s1 damage.  Interrupts casting. "}})], 800000)
        self.assertIsNone(LOCALES.verify_source_semantics(ip, stock, filename, {}))

    def test_empty_ip_fields_are_intentionally_suppressed(self):
        filename = "Spell.dbc"
        ip = fixture(filename, [(42, {}), (9876, {})])
        stock = fixture(filename, [(42, localized_texts(filename))])
        self.assertIsNone(LOCALES.verify_source_semantics(ip, stock, filename, {}))


class PinnedGermanSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="client-locales-source-")
        self.repository = Path(self.temporary.name)
        self.donors = {filename: fixture(filename, [(42, localized_texts(filename, True))])
                       for filename in FILES}
        self.override_path = self.repository / "locales/deDE.json"
        self.override_path.parent.mkdir()
        self.override_path.write_text(json.dumps({filename: {} for filename in FILES}))
        self.source = {
            "url": "https://github.com/example/client-data.git",
            "revision": "a" * 40,
            "sourcePath": "dbc/deDE",
            "clientBuild": 12340,
            "files": {filename: hashlib.sha256(raw).hexdigest()
                      for filename, raw in self.donors.items()},
            "overrides": "locales/deDE.json",
            "overridesSha256": hashlib.sha256(self.override_path.read_bytes()).hexdigest(),
        }
        self.configuration = {"deDE": self.source}
        self.cache = (self.repository / ".module-cache/client-locales"
                      / self.source["revision"] / "deDE")

    def tearDown(self):
        self.temporary.cleanup()

    def response(self, request, **kwargs):
        self.assertEqual(kwargs, {"timeout": 120})
        prefix = ("https://raw.githubusercontent.com/example/client-data/"
                  + "a" * 40 + "/dbc/deDE/")
        self.assertTrue(request.full_url.startswith(prefix))
        filename = request.full_url[len(prefix):]
        self.assertIn(filename, self.donors)
        return io.BytesIO(self.donors[filename])

    def load(self):
        return LOCALES.load_german_inputs(self.repository, self.configuration)

    def test_fetches_only_four_raw_commit_pinned_tables_and_reuses_verified_cache(self):
        with mock.patch.object(LOCALES, "urlopen", side_effect=self.response) as download:
            donors, overrides, identity = self.load()
            self.assertEqual(download.call_count, 4)
            self.assertEqual(donors, self.donors)
            self.assertEqual(overrides, {filename: {} for filename in FILES})
            self.assertEqual(identity, self.source)
            self.assertEqual({call.args[0].full_url.rsplit("/", 1)[-1]
                              for call in download.call_args_list}, set(FILES))
        with mock.patch.object(LOCALES, "urlopen") as download:
            self.assertEqual(self.load()[0], self.donors)
            download.assert_not_called()

    def test_corrupt_cached_table_is_replaced_by_a_verified_download(self):
        with mock.patch.object(LOCALES, "urlopen", side_effect=self.response):
            self.load()
        (self.cache / "Spell.dbc").write_bytes(b"corrupt cached client data")
        with mock.patch.object(LOCALES, "urlopen", side_effect=self.response) as download:
            self.assertEqual(self.load()[0], self.donors)
            download.assert_called_once()
            self.assertTrue(download.call_args.args[0].full_url.endswith("/Spell.dbc"))
        self.assertEqual((self.cache / "Spell.dbc").read_bytes(), self.donors["Spell.dbc"])
        self.assertEqual({path.name for path in self.cache.iterdir()}, set(FILES))

    def test_download_checksum_failure_is_rejected_without_installing_artifact(self):
        with mock.patch.object(LOCALES, "urlopen", return_value=io.BytesIO(b"untrusted data")):
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                self.load()
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_changed_authored_override_file_is_rejected_even_when_json_is_valid(self):
        with mock.patch.object(LOCALES, "urlopen", side_effect=self.response):
            self.load()
        self.override_path.write_bytes(self.override_path.read_bytes() + b"\n")
        with mock.patch.object(LOCALES, "urlopen") as download:
            with self.assertRaisesRegex(ValueError, "override checksum"):
                self.load()
            download.assert_not_called()

    def test_unpinned_revision_wrong_build_path_and_extra_files_are_rejected(self):
        changes = (("revision", "main"), ("clientBuild", 12341),
                   ("sourcePath", "dbc/enUS"),
                   ("files", {**self.source["files"], "../foreign.dbc": "0" * 64}))
        for key, bad_value in changes:
            with self.subTest(key=key):
                configuration = {"deDE": {**self.source, key: bad_value}}
                with mock.patch.object(LOCALES, "urlopen") as download:
                    with self.assertRaises(ValueError):
                        LOCALES.load_german_inputs(self.repository, configuration)
                    download.assert_not_called()

    def test_optional_english_spell_uses_fifth_pinned_url_and_verified_cache(self):
        english = fixture("Spell.dbc", [(42, {"name": {0: "Earth Shock"}})])
        self.source["englishSpellSha256"] = hashlib.sha256(english).hexdigest()
        english_url = ("https://raw.githubusercontent.com/example/client-data/"
                       + "a" * 40 + "/dbc/Spell.dbc")

        def response(request, **kwargs):
            if request.full_url == english_url:
                self.assertEqual(kwargs, {"timeout": 120})
                return io.BytesIO(english)
            return self.response(request, **kwargs)

        with mock.patch.object(LOCALES, "urlopen", side_effect=response) as download:
            donors, _, identity = self.load()
            self.assertEqual(download.call_count, 5)
            self.assertEqual(donors, {**self.donors, "Spell.enUS.dbc": english})
            self.assertEqual(identity, self.source)
            self.assertEqual(sum(call.args[0].full_url == english_url
                                 for call in download.call_args_list), 1)
        with mock.patch.object(LOCALES, "urlopen") as download:
            self.assertEqual(self.load()[0]["Spell.enUS.dbc"], english)
            download.assert_not_called()

    def test_optional_english_spell_checksum_and_schema_are_validated(self):
        with mock.patch.object(LOCALES, "urlopen", side_effect=self.response):
            self.load()
        valid_spell = fixture("Spell.dbc", [(42, {"name": {0: "Earth Shock"}})])
        self.source["englishSpellSha256"] = hashlib.sha256(valid_spell).hexdigest()
        with mock.patch.object(LOCALES, "urlopen", return_value=io.BytesIO(b"corrupt download")):
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                self.load()
        self.assertFalse((self.cache / "Spell.enUS.dbc").exists())
        wrong_schema = self.donors["Achievement.dbc"]
        self.source["englishSpellSha256"] = hashlib.sha256(wrong_schema).hexdigest()
        with mock.patch.object(LOCALES, "urlopen", return_value=io.BytesIO(wrong_schema)):
            with self.assertRaisesRegex(ValueError, "DBC layout"):
                self.load()


if __name__ == "__main__":
    unittest.main()
