"""Tests for historical creature stat selection; no network access required."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generate_era_creature_stats as generator


HISTORICAL = """CREATE TABLE `creature_template` (
  `Entry` mediumint unsigned NOT NULL,
  `Name` char(100),
  `Expansion` tinyint NOT NULL,
  PRIMARY KEY (`Entry`)
) ENGINE=MyISAM;
INSERT INTO `creature_template` VALUES (1,'Classic Boss',0),(2,'TBC Boss',1),(3,'Wrong NPC',0),
(4,'Vol\\'jin',0),(5,'Native',0),(6,'TBC with Classic stats',0),(7,'Unmanaged',0);
"""
CORE = """CREATE TABLE `creature_template` (
  `entry` int unsigned NOT NULL,
  `name` char(100),
  `exp` smallint NOT NULL,
  PRIMARY KEY (`entry`)
) ENGINE=InnoDB;
INSERT INTO `creature_template` VALUES (1,'Classic Boss',2),(2,'TBC Boss',2),(3,'Different NPC',2),
(4,'Vol''jin',2),(5,'Native',0),(6,'TBC with Classic stats',1),(7,'Unmanaged',2),(8,'Only in Wrath',2);
"""


def rows(*entries):
    return {int(row['Entry']): row for row in generator.table_rows(HISTORICAL, 'creature_template')
            if int(row['Entry']) in entries}


def table(table_name, columns, records):
    return f'CREATE TABLE `{table_name}` (\n' + ',\n'.join(f'  `{column}` TEXT' for column in columns) + (
        f'\n) ENGINE=InnoDB;\nINSERT INTO `{table_name}` VALUES ' + ','.join(records) + ';\n')


OUTDOOR_CORE = table('creature_template', ('entry', 'name', *generator.STATS, 'flags_extra', 'ScriptName'),
                     ("(17468,'Prophet Velen',83,83,400,2,2,0,'')", "(16802,'Lor\\'themar Theron',83,83,400,2,2,0,'')"))
OUTDOOR_HISTORICAL = {
    17468: {'Entry': '17468', 'Name': "'Prophet Velen'", 'MinLevel': '73', 'MaxLevel': '73',
            'HealthMultiplier': '400', 'UnitClass': '2', 'Expansion': '1'},
    16802: {'Entry': '16802', 'Name': "'Lor''themar Theron'", 'MinLevel': '73', 'MaxLevel': '73',
            'HealthMultiplier': '250', 'UnitClass': '1', 'Expansion': '1'},
}


class SelectionTests(unittest.TestCase):
    def test_replacement_raid_difficulty_templates_keep_native_stat_curves(self):
        core = table('creature_template', ('entry', 'name', 'exp', 'difficulty_entry_1',
                                          'difficulty_entry_2', 'difficulty_entry_3'),
                     ("(1,'Classic Boss',2,100,0,0)", "(2,'TBC Boss',2,200,0,0)"))
        actual = generator.repairs(rows(1), rows(2), core, {1, 2}, {'Classic Boss'})
        self.assertEqual([(2, 1, 2, 'TBC Boss')], actual)

    def test_raid_replacement_names_come_from_explicit_name_columns(self):
        with tempfile.TemporaryDirectory() as temporary:
            ip = Path(temporary)
            base = ip / 'data/sql/world/base'
            base.mkdir(parents=True)
            (base / generator.REPLACEMENTS[0]).write_text(
                "INSERT INTO `creature_template` (`entry`, `name`, `ScriptName`) VALUES\n"
                "(@ENTRY + 1, 'Boss, One', 'boss_one'), -- comment\n"
                "(@ENTRY+2, 'Boss -- Two', 'boss_two');\n")
            (base / generator.REPLACEMENTS[1]).write_text(
                'INSERT INTO `creature_template` (`name`, `entry`, `ScriptName`) VALUES\n'
                '("Onyxia",301000,"boss_onyxia_40");\n')
            self.assertEqual({'Boss, One', 'Boss -- Two', 'Onyxia'}, generator.replacement_names(ip))

    def test_earliest_identity_selects_its_expansion_stat_table(self):
        self.assertEqual([(1, 0, 2, 'Classic Boss'), (2, 1, 2, 'TBC Boss'), (4, 0, 2, "Vol'jin"),
                          (6, 0, 1, 'TBC with Classic stats')],
                         generator.repairs(rows(1, 3, 4, 5, 7), rows(1, 2, 3, 4, 5, 6, 7), CORE, {1, 2, 3, 4, 5, 6, 8}))

    def test_unmanaged_and_unmatched_entries_keep_their_native_values(self):
        self.assertEqual([], generator.repairs(rows(1, 3, 4, 5, 7), rows(2, 6), CORE, {3, 5, 8}))

    def test_reused_classic_id_does_not_fall_back_to_a_later_identity(self):
        classic, tbc = rows(3), rows(3)
        tbc[3]['Name'] = "'Different NPC'"
        self.assertEqual([], generator.repairs(classic, tbc, CORE, {3}))

    def test_unsupported_historical_expansion_is_refused(self):
        tbc = rows(2)
        tbc[2]['Expansion'] = '2'
        with self.assertRaises(ValueError):
            generator.repairs({}, tbc, CORE, {2})

    def test_sql_strings_and_comments_preserve_quoted_content(self):
        self.assertEqual("Vol'jin", generator.sql_string("'Vol\\'jin'"))
        self.assertEqual("Vol'jin", generator.sql_string("'Vol''jin'"))
        self.assertEqual('a\n;--b', generator.sql_string("'a\\n;--b'"))
        self.assertEqual("'a--b/*c*/' \n", generator.without_comments("'a--b/*c*/' -- removed\n/* removed */"))
        with self.assertRaises(ValueError):
            generator.sql_string('NULL')

    def test_managed_entries_come_only_from_era_creature_updates(self):
        with tempfile.TemporaryDirectory() as temporary:
            ip = Path(temporary)
            base = ip / 'data/sql/world/base'
            base.mkdir(parents=True)
            (base / generator.BASES[0]).write_text('UPDATE `creature_template` SET `minlevel`=63 WHERE `entry` = 1;\n')
            path = base / generator.BASES[1]
            path.write_text('/* UPDATE `creature_template` SET `exp`=0 WHERE `entry`=99; */\n'
                            'UPDATE `creature_template` SET `speed_run`=1 WHERE `entry` IN (2, 3);\n')
            self.assertEqual({1, 2, 3}, generator.managed_entries(ip))
            path.write_text('UPDATE `creature_template` SET `exp`=0 WHERE `entry` > 3;\n')
            with self.assertRaises(ValueError):
                generator.managed_entries(ip)


class OutdoorTests(unittest.TestCase):
    def test_stock_capital_bosses_regain_historical_levels_health_class_and_expansion(self):
        actual = generator.outdoor_repairs({}, OUTDOOR_HISTORICAL, OUTDOOR_CORE, {16802, 17468}, set(), set())
        self.assertEqual({(16802, 'minlevel', '73', '83'), (16802, 'maxlevel', '73', '83'),
                          (16802, 'HealthModifier', '250', '400'), (16802, 'unit_class', '1', '2'),
                          (16802, 'exp', '1', '2'), (17468, 'minlevel', '73', '83'),
                          (17468, 'maxlevel', '73', '83'), (17468, 'exp', '1', '2')},
                         {row[:4] for row in actual})

    def test_outdoor_repairs_exclude_module_overrides_managed_and_unspawned_entries(self):
        for outdoor, managed, overridden in ((set(), set(), set()), ({16802, 17468}, {16802, 17468}, set()),
                                              ({16802, 17468}, set(), {16802, 17468})):
            with self.subTest(outdoor=outdoor, managed=managed, overridden=overridden):
                self.assertEqual([], generator.outdoor_repairs({}, OUTDOOR_HISTORICAL, OUTDOOR_CORE,
                                                              outdoor, managed, overridden))

    def test_both_level_bounds_must_show_a_later_expansion_leak(self):
        for core in (OUTDOOR_CORE.replace('83,83', '73,83'), OUTDOOR_CORE.replace('83,83', '83,73'),
                     OUTDOOR_CORE.replace('83,83', '72,72')):
            with self.subTest(core=core):
                self.assertEqual([], generator.outdoor_repairs({}, OUTDOOR_HISTORICAL, core,
                                                              {16802, 17468}, set(), set()))
        historical = {entry: {**row, 'MinLevel': '60', 'MaxLevel': '60'}
                      for entry, row in OUTDOOR_HISTORICAL.items()}
        # An era-appropriate level adjustment within TBC is not evidence of leaked Wrath stats.
        core = OUTDOOR_CORE.replace('83,83', '70,70').replace(",2,2,0,'')", ",2,1,0,'')")
        self.assertEqual([], generator.outdoor_repairs({}, historical, core, {16802, 17468}, set(), set()))

    def test_reused_names_and_unsupported_historical_stats_are_excluded(self):
        for fields in ({'Name': "'Someone Else'"}, {'UnitClass': '0'}, {'Expansion': '2'}):
            historical = {entry: {**row, **fields} for entry, row in OUTDOOR_HISTORICAL.items()}
            with self.subTest(fields=fields):
                self.assertEqual([], generator.outdoor_repairs({}, historical, OUTDOOR_CORE,
                                                              {16802, 17468}, set(), set()))

    def test_invisible_and_named_script_helpers_keep_native_stats(self):
        invisible = OUTDOOR_CORE.replace(",2,2,0,'')", ",2,2,128,'')")
        self.assertEqual([], generator.outdoor_repairs({}, OUTDOOR_HISTORICAL, invisible,
                                                      {16802, 17468}, set(), set()))
        historical = {entry: {**row, 'Name': "'Invisible Trigger'"}
                      for entry, row in OUTDOOR_HISTORICAL.items()}
        core = OUTDOOR_CORE.replace("'Prophet Velen'", "'Invisible Trigger'").replace(
            "'Lor\\'themar Theron'", "'Invisible Trigger'")
        self.assertEqual([], generator.outdoor_repairs({}, historical, core, {16802, 17468}, set(), set()))

    def test_only_entries_with_exclusively_outdoor_native_spawns_are_selected(self):
        spawns = table('creature', ('id1', 'id2', 'id3', 'map'),
                       ('(1,2,0,0)', '(1,0,3,530)', '(4,0,0,1)', '(2,0,0,533)', '(5,0,0,249)', '(6,0,0,571)'))
        self.assertEqual({1, 3, 4}, generator.outdoor_entries(spawns))

    def test_module_stat_overrides_include_variable_selectors_and_skip_the_generated_migration(self):
        with tempfile.TemporaryDirectory() as temporary:
            ip = Path(temporary)
            base = ip / 'data/sql/world/base'
            base.mkdir(parents=True)
            (base / 'encounters.sql').write_text(
                'SET @ENTRY = 100;\nUPDATE `creature_template` SET `minlevel`=63 WHERE `entry` = @ENTRY + 2;\n'
                'UPDATE `creature_template` SET `HealthModifier`=25 WHERE `entry` IN (3,4);\n'
                'UPDATE `creature_template` SET `name`=\'Unrelated\' WHERE `entry`=5;\n')
            (base / generator.MIGRATION).write_text('UPDATE `creature_template` SET `exp`=0 WHERE `entry`=99;\n')
            self.assertEqual({3, 4, 102}, generator.overridden_entries(ip))
            (base / 'unsupported.sql').write_text('UPDATE `creature_template` SET `minlevel`=63 WHERE `entry`>4;\n')
            with self.assertRaises(ValueError):
                generator.overridden_entries(ip)


class HistoricalCheckoutTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.checkout = self.root / 'classic-db'
        (self.checkout / 'Full_DB').mkdir(parents=True)
        (self.checkout / 'Updates').mkdir()
        with gzip.open(self.checkout / generator.CLASSIC_DUMP, 'wt', encoding='utf-8') as handle:
            handle.write(HISTORICAL)
        git = ['git', '-C', str(self.checkout), '-c', 'user.name=test', '-c', 'user.email=test@localhost']
        subprocess.run([*git, 'init', '-q'], check=True)
        subprocess.run([*git, 'add', '-A'], check=True)
        subprocess.run([*git, 'commit', '-qm', 'historical fixture'], check=True)
        self.revision = generator.checkout_revision(self.checkout)
        self.repository = self.root / 'repository'
        self.repository.mkdir()
        self.lock(self.revision)

    def lock(self, revision):
        (self.repository / 'versions.lock.json').write_text(json.dumps({'historicalClassData': {'sources': [
            {'name': generator.CLASSIC_SOURCE, 'revision': revision}]}}))

    def read(self):
        return generator.historical_rows(self.checkout, generator.CLASSIC_SOURCE, generator.CLASSIC_DUMP, self.repository)

    def test_matching_pinned_checkout_loads_the_dump(self):
        self.assertEqual(rows(1, 2, 3, 4, 5, 6, 7), self.read())
        self.lock('a' * 40)
        with self.assertRaises(SystemExit):
            self.read()

    def test_updates_replay_historical_stats_and_ignore_unrelated_fields(self):
        (self.checkout / 'Updates/0001.sql').write_text(
            "UPDATE `creature_template` SET `Name`='New; Name -- here', `Rank`=3 WHERE `Entry`='1';\n"
            "UPDATE creature_template SET Expansion='1', HealthMultiplier=3 WHERE (Entry = '6');\n"
            'UPDATE creature_template SET Rank=3 WHERE Entry IN (1,2);\n'
            'UPDATE creature_template SET UnitClass=2 WHERE Entry IN (1,2);\n'
            "UPDATE other_table SET Name='Ignored' WHERE Entry=1;\n")
        actual = self.read()
        self.assertEqual("'New; Name -- here'", actual[1]['Name'])
        self.assertEqual('1', actual[6]['Expansion'])
        self.assertEqual('3', actual[6]['HealthMultiplier'])
        self.assertEqual('2', actual[1]['UnitClass'])
        self.assertEqual({**rows(2)[2], 'UnitClass': '2'}, actual[2])

    def test_unsupported_relevant_updates_are_refused(self):
        path = self.checkout / 'Updates/0001.sql'
        for statement in ("UPDATE creature_template SET Name='New' WHERE Entry > 2;",
                          'UPDATE creature_template SET Expansion=Expansion+1 WHERE Entry=2;',
                          'UPDATE creature_template SET Expansion=1+1 WHERE Entry=2;',
                          "UPDATE creature_template SET Name='New', Expansion=1+1 WHERE Entry=2;",
                          "UPDATE creature_template SET Name='New' WHERE Entry=2",
                          'DELETE FROM creature_template WHERE Entry=1;',
                          "INSERT INTO creature_template VALUES (9,'New',0);",
                          "REPLACE INTO creature_template VALUES (9,'New',0);"):
            path.write_text(statement)
            with self.subTest(statement=statement), self.assertRaises(SystemExit):
                self.read()


if __name__ == '__main__':
    unittest.main()
