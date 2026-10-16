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
  `QuestFlags` int unsigned NOT NULL DEFAULT '0',
  PRIMARY KEY (`entry`)
) ENGINE=MyISAM;
INSERT INTO `quest_template` VALUES (9492,70,'Turning (the) Tide, part 2',75900,0),(26,-1,'A Lesson to Learn',2820,0),\
(4,0,'Unused',600,0);
INSERT INTO `quest_template` VALUES (2,30,'Sharptalon\\'s Claw',1500,8),(3,60,'It''s done; (really)',4950,0),\
(7,61,NULL,600,0),(8,62,'',600,0),(9,63,'',37500,0),(10,64,'',600,0),(11,65,'',600,0),(12,45,'',0,8),(13,40,'',1500,0),\
(14,60,'',0,264),(15,60,'',0,512),(16,60,'',600,256),(17,55,'',4950,8),(18,30,'',1440,0),(19,30,'',1446,0),(20,40,'',4950,0);
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
  `QuestLevel` smallint NOT NULL DEFAULT '1',
  `RewardXPDifficulty` int unsigned NOT NULL DEFAULT '0',
  `LogTitle` text,
  PRIMARY KEY (`ID`)
) ENGINE=InnoDB;
INSERT INTO `quest_template` VALUES (2,30,5,'a'),(3,60,5,'b'),(4,0,5,'c'),(7,61,5,'d'),(8,62,5,'e'),(9,63,5,'f'),\
(10,64,5,'g'),(11,65,5,'h'),(12,45,5,'i'),(14,60,5,'l'),(15,60,5,'m'),(16,60,5,'n'),(17,55,1,'o'),(18,30,0,'p'),\
(19,30,0,'q'),(20,-1,5,'r'),(26,-1,5,'j'),(9492,70,8,'k');
"""
IP = """INSERT INTO `custom_quest_xp` (`entry`, `xpValue`) VALUES
(2, 2450),
(3, 6600),
(4, 0),
(13, 1500),
(17, 560),
(18, 600),
(19, 600);
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


class NativeValueTests(unittest.TestCase):
    def test_native_full_value_rounds_like_the_core(self):
        cases = {(1, 1): 10, (2, 2): 45, (4, 5): 360, (12, 3): 460, (30, 5): 2450, (31, 5): 2550, (60, 5): 9550,
                 (60, 7): 14300, (70, 8): 25300}
        for (level, difficulty), expected in cases.items():
            with self.subTest(level=level, difficulty=difficulty):
                self.assertEqual(expected, generator.native_full_xp(level, difficulty))

    def test_no_native_value_without_a_table_entry(self):
        for level, difficulty in ((0, 5), (101, 5), (60, 0), (60, 9)):
            with self.subTest(level=level, difficulty=difficulty):
                self.assertEqual(0, generator.native_full_xp(level, difficulty))


class RowTests(unittest.TestCase):
    def test_tbc_rows_keep_their_quest_level_and_are_filtered_by_core_quests(self):
        self.assertEqual([(2, 2500, 30), (3, 8250, 60), (7, 500, 61), (8, 250, 62), (9, 10417, 63), (10, 125, 64),
                          (11, 100, 65), (12, 0, 45), (16, 1000, 60), (18, 2400, 30), (20, 8250, 40),
                          (9492, 12650, 70)], generator.tbc_values(DUMP, CORE, generator.ip_values(IP)))

    def test_values_the_pinned_db_cannot_support_are_left_out(self):
        values = {entry for entry, _, _ in generator.tbc_values(DUMP, CORE, generator.ip_values(IP))}
        # 14 and 15 withhold their maximum-level money; 17 and 19 exceed four times the larger reference.
        self.assertFalse({14, 15, 17, 19} & values)

    def test_vanilla_levels_cover_individual_progression_values_in_the_core(self):
        # 9 has no Individual Progression value, 4 no positive level and 13 no core quest.
        self.assertEqual([(2, 30), (3, 62)], generator.vanilla_levels(CLASSIC, CORE, generator.ip_values(IP)))

    def test_individual_progression_values_are_read_from_its_table(self):
        self.assertEqual({2: 2450, 3: 6600, 4: 0, 13: 1500, 17: 560, 18: 600, 19: 600}, generator.ip_values(IP))

    def test_unterminated_or_misaligned_statements_are_refused(self):
        with self.assertRaises(ValueError):
            list(generator.table_rows(DUMP.replace("(20,40,'',4950,0);", "(20,40,'',4950,0)"), 'quest_template'))
        with self.assertRaises(ValueError):
            list(generator.table_rows(DUMP.replace("(13,40,'',1500,0)", "(13,40,1500,0)"), 'quest_template'))

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
        expected = generator.render(generator.tbc_values(DUMP, CORE, generator.ip_values(IP)),
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
                                 (self.tbc, 'UPDATE `quest_template` SET `QuestFlags` = 256 WHERE `entry` = 3;\n'),
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
