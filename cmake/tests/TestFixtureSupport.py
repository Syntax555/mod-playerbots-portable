"""Regression checks for shared fixture source options, WDBC data and SQL rows."""

import argparse
from pathlib import Path
import struct
import tempfile
import unittest

from FixtureSupport import make_wdbc, source_argument, sql_rows, sql_values, wdbc


class FixtureSupportTests(unittest.TestCase):
    # One two-field record (ID 7, string offset 1), followed by an UTF-8 string block.
    data = bytes.fromhex('57444243 01000000 02000000 08000000 04000000 07000000 01000000 00c3a400')
    row = bytes.fromhex('07000000 01000000')
    strings = b'\0\xc3\xa4\0'

    def test_reads_and_writes_known_wdbc_bytes(self):
        self.assertEqual(([self.row], self.strings), wdbc(self.data, 2))
        self.assertEqual(([self.row], self.strings), wdbc(self.data))
        self.assertEqual(self.data, make_wdbc([self.row], self.strings, 2))

    def test_rejects_invalid_wdbc_layouts(self):
        malformed = [b'WDBC', b'XXXX' + self.data[4:], self.data[:-1], self.data + b'\0']
        for offset, value in ((4, 2), (8, 3), (8, 0), (12, 4), (16, 5)):
            changed = bytearray(self.data)
            struct.pack_into('<I', changed, offset, value)
            malformed.append(bytes(changed))
        for data in malformed:
            with self.subTest(data=data), self.assertRaises(AssertionError):
                wdbc(data)
        with self.assertRaises(AssertionError):
            wdbc(self.data, 3)

    def test_empty_wdbc(self):
        data = bytes.fromhex('57444243 00000000 02000000 08000000 01000000 00')
        self.assertEqual(([], b'\0'), wdbc(data, 2))
        self.assertEqual(data, make_wdbc([], fields=2))

    def test_source_options_keep_path_defaults_and_overrides(self):
        parser = argparse.ArgumentParser()
        source_argument(parser, default=Path('prepared'))
        source_argument(parser, 'core')
        source_argument(parser, 'module', help='custom module directory')
        defaults = parser.parse_args([])
        self.assertEqual(Path('prepared'), defaults.source)
        self.assertIsNone(defaults.core)
        self.assertIsNone(defaults.module)
        args = parser.parse_args(['--source', 'custom', '--core', 'core', '--module', 'module'])
        self.assertEqual((Path('custom'), Path('core'), Path('module')), (args.source, args.core, args.module))
        self.assertIn('custom module directory', parser.format_help())


    def test_sql_rows_use_named_columns_and_quoted_values(self):
        self.assertEqual(['1', "it's, quoted", 'a\\b', ''], sql_values("1,'it\\'s, quoted','a\\\\b',''"))
        with tempfile.TemporaryDirectory() as directory:
            core = Path(directory)
            table = core / 'data/sql/base/db_world/fixture.sql'
            table.parent.mkdir(parents=True)
            table.write_text('CREATE TABLE `fixture` (\n  `entry` int,\n  `name` text\n) ENGINE=InnoDB;\n'
                             "INSERT INTO `fixture` VALUES\n(-7,'minus, seven'),\n(8,'eight');\n"
                             "INSERT INTO `fixture` VALUES\n(8,'acht');", encoding='utf-8')
            self.assertEqual([{'entry': '-7', 'name': 'minus, seven'}], sql_rows(core, 'fixture', {-7}))
            self.assertEqual([{'entry': '8', 'name': 'eight'}, {'entry': '8', 'name': 'acht'}],
                             sql_rows(core, 'fixture', {8}))
            with self.assertRaises(AssertionError):
                sql_rows(core, 'fixture', {9})
            with table.open('a', encoding='utf-8') as output:
                output.write("\n(9,'wrong','column count');\n")
            with self.assertRaises(ValueError):
                sql_rows(core, 'fixture', {9})


if __name__ == '__main__':
    unittest.main()
