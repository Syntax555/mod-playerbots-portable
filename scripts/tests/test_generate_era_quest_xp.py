"""Tests for the era quest experience generator; no network access required."""

from __future__ import annotations

import gzip
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generate_era_quest_xp as generator


DUMP = """CREATE TABLE `quest_template` (
  `entry` mediumint unsigned NOT NULL DEFAULT '0',
  `QuestLevel` smallint NOT NULL DEFAULT '0',
  `Title` text,
  `RewMoneyMaxLevel` int unsigned NOT NULL DEFAULT '0',
  PRIMARY KEY (`entry`)
) ENGINE=MyISAM;
INSERT INTO `quest_template` VALUES (9492,70,'Turning (the) Tide, part 2',75900),(26,-1,'A Lesson to Learn',2820),\
(4,0,'Unused',600);
INSERT INTO `quest_template` VALUES (2,30,'Sharptalon\\'s Claw',1500),(3,60,'It''s done; (really)',4950),\
(7,61,NULL,600),(8,62,'',600),(9,63,'',37500),(10,64,'',600),(11,65,'',600),(12,45,'',0),(13,40,'',1500);
"""
CLASSIC = """CREATE TABLE `quest_template` (
  `entry` mediumint unsigned NOT NULL DEFAULT '0',
  `QuestLevel` smallint NOT NULL DEFAULT '0',
  PRIMARY KEY (`entry`)
) ENGINE=MyISAM;
INSERT INTO `quest_template` VALUES (2,30),(3,62),(4,0),(9,55),(13,40);
"""
CORE = """CREATE TABLE `quest_template` (
  `ID` int unsigned NOT NULL DEFAULT '0',
  `LogTitle` text,
  PRIMARY KEY (`ID`)
) ENGINE=InnoDB;
INSERT INTO `quest_template` VALUES (2,'a'),(3,'b'),(4,'c'),(7,'d'),(8,'e'),(9,'f'),(10,'g'),(11,'h'),(12,'i'),\
(26,'j'),(9492,'k');
"""
IP = """INSERT INTO `custom_quest_xp` (`entry`, `xpValue`) VALUES
(2, 2450),
(3, 6600),
(4, 0),
(13, 1500);
"""


class FullValueTests(unittest.TestCase):
    def test_each_quest_level_uses_its_mangos_divisor(self):
        cases = {(1, 240): 400, (30, 1500): 2500, (60, 4950): 8250, (61, 600): 500, (62, 600): 250,
                 (63, 37500): 10417, (64, 600): 125, (65, 600): 100, (70, 75900): 12650}
        for (level, money), expected in cases.items():
            with self.subTest(level=level, money=money):
                self.assertEqual(expected, generator.full_xp(level, money))

    def test_division_and_ceiling_use_single_precision(self):
        # 36000 / 3.6f is 10000.00026 in double precision but exactly 10000 in single precision.
        self.assertEqual(10001, math.ceil(36000 / generator.float32(3.6)))
        self.assertEqual(10000, generator.full_xp(63, 36000))
        self.assertEqual(2, generator.full_xp(60, 1))

    def test_quests_without_level_or_money_pay_nothing(self):
        for level, money in ((0, 600), (-1, 600), (60, 0)):
            with self.subTest(level=level, money=money):
                self.assertEqual(0, generator.full_xp(level, money))


class RowTests(unittest.TestCase):
    def test_tbc_rows_keep_their_quest_level_and_are_filtered_by_core_quests(self):
        self.assertEqual([(2, 2500, 30), (3, 8250, 60), (7, 500, 61), (8, 250, 62), (9, 10417, 63), (10, 125, 64),
                          (11, 100, 65), (12, 0, 45), (9492, 12650, 70)], generator.tbc_values(DUMP, CORE))

    def test_vanilla_levels_cover_individual_progression_values_in_the_core(self):
        # 9 has no Individual Progression value, 4 no positive level and 13 no core quest.
        self.assertEqual([(2, 30), (3, 62)], generator.vanilla_levels(CLASSIC, CORE, generator.ip_values(IP)))

    def test_individual_progression_values_are_read_from_its_table(self):
        self.assertEqual({2: 2450, 3: 6600, 4: 0, 13: 1500}, generator.ip_values(IP))

    def test_unterminated_or_misaligned_statements_are_refused(self):
        with self.assertRaises(ValueError):
            list(generator.table_rows(DUMP.replace("(13,40,'',1500);", "(13,40,'',1500)"), 'quest_template'))
        with self.assertRaises(ValueError):
            list(generator.table_rows(DUMP.replace("(13,40,'',1500)", "(13,40,1500)"), 'quest_template'))

    def test_rendered_tables_are_recreated_from_scratch(self):
        text = generator.render([(2, 2500, 30), (5, 400, 20)], [(2, 30), (3, 62)], 'e' * 40, 'a' * 40, 'b' * 40)
        self.assertIn('DROP TABLE IF EXISTS `custom_quest_xp_tbc`;\nCREATE TABLE `custom_quest_xp_tbc`', text)
        self.assertIn('DROP TABLE IF EXISTS `custom_quest_xp_level`;\nCREATE TABLE `custom_quest_xp_level`', text)
        self.assertIn('classic-db ' + 'e' * 40, text)
        self.assertIn('tbc-db ' + 'a' * 40, text)
        self.assertIn('mangos-tbc ' + 'b' * 40, text)
        self.assertIn('VALUES\n(2, 2500, 30),\n(5, 400, 20);\n', text)
        self.assertTrue(text.endswith('VALUES\n(2, 30),\n(3, 62);\n'))


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.classic, self.classic_revision = self.checkout('classic-db', generator.CLASSIC_DUMP, CLASSIC)
        self.tbc, self.revision = self.checkout('tbc-db', generator.DUMP, DUMP)
        self.core = self.root / 'core'
        for path, text in ((generator.CORE_QUESTS, CORE), (generator.IP_QUESTS, IP)):
            (self.core / path).parent.mkdir(parents=True)
            (self.core / path).write_text(text)

    def checkout(self, name, dump, text):
        checkout = self.root / name
        (checkout / 'Full_DB').mkdir(parents=True)
        (checkout / 'Updates').mkdir()
        with gzip.open(checkout / dump, 'wt', encoding='utf-8') as handle:
            handle.write(text)
        (checkout / 'Updates/0001_npc.sql').write_text('UPDATE `creature_template` SET `Rank` = 1;\n')
        (checkout / 'Updates/0002_quest.sql').write_text('UPDATE `quest_template` SET `Method` = 2 WHERE `entry` = 2;\n')
        git = ['git', '-C', str(checkout), '-c', 'user.name=test', '-c', 'user.email=test@localhost']
        subprocess.run([*git, 'init', '-q'], check=True)
        subprocess.run([*git, 'add', '-A'], check=True)
        subprocess.run([*git, 'commit', '-qm', 'dump'], check=True)
        return checkout, generator.checkout_revision(checkout)

    def lock(self, classic_revision, revision):
        repository = self.root / f'repository-{classic_revision[:8]}-{revision[:8]}'
        repository.mkdir(exist_ok=True)
        sources = [{'name': generator.CLASSIC_SOURCE, 'revision': classic_revision},
                   {'name': generator.SOURCE, 'revision': revision},
                   {'name': generator.CORE_SOURCE, 'revision': 'c' * 40}]
        (repository / 'versions.lock.json').write_text(json.dumps({'historicalClassData': {'sources': sources}}))
        return repository

    def generate(self, classic_revision=None, revision=None):
        repository = self.lock(classic_revision or self.classic_revision, revision or self.revision)
        return generator.generate(self.classic, self.tbc, self.core, repository)

    def test_pinned_checkouts_generate_the_tables(self):
        expected = generator.render(generator.tbc_values(DUMP, CORE),
                                    generator.vanilla_levels(CLASSIC, CORE, generator.ip_values(IP)),
                                    self.classic_revision, self.revision, 'c' * 40)
        self.assertEqual(expected, self.generate())

    def test_other_revisions_are_refused(self):
        for revisions in (('d' * 40, None), (None, 'd' * 40)):
            with self.subTest(revisions=revisions), self.assertRaises(SystemExit):
                self.generate(*revisions)

    def test_unapplied_updates_of_the_columns_used_are_refused(self):
        for checkout, update in ((self.classic, 'UPDATE `quest_template` SET `QuestLevel` = 1;\n'),
                                 (self.tbc, 'UPDATE quest_template SET RewMoneyMaxLevel = 1 WHERE entry = 2;\n'),
                                 (self.tbc, 'INSERT INTO `quest_template` VALUES (14,40);\n'),
                                 (self.classic, 'DELETE FROM quest_template WHERE entry = 2;\n')):
            path = checkout / 'Updates/0003_quest.sql'
            path.write_text(update)
            with self.subTest(checkout=checkout.name, update=update), self.assertRaises(SystemExit):
                self.generate()
            path.unlink()
        self.assertTrue(self.generate())


if __name__ == '__main__':
    unittest.main()
