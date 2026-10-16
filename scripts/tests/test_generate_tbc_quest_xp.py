"""Tests for the 2.4.3 quest experience generator; no network access required."""

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
import generate_tbc_quest_xp as generator


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
CORE = """CREATE TABLE `quest_template` (
  `ID` int unsigned NOT NULL DEFAULT '0',
  `LogTitle` text,
  PRIMARY KEY (`ID`)
) ENGINE=InnoDB;
INSERT INTO `quest_template` VALUES (2,'a'),(3,'b'),(4,'c'),(7,'d'),(8,'e'),(9,'f'),(10,'g'),(11,'h'),(12,'i'),\
(26,'j'),(9492,'k');
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
    def test_rows_are_filtered_by_core_quests_and_sorted(self):
        self.assertEqual([(2, 2500), (3, 8250), (7, 500), (8, 250), (9, 10417), (10, 125), (11, 100), (12, 0),
                          (9492, 12650)], generator.quest_values(DUMP, CORE))

    def test_unterminated_or_misaligned_statements_are_refused(self):
        with self.assertRaises(ValueError):
            list(generator.table_rows(DUMP.replace("(13,40,'',1500);", "(13,40,'',1500)"), 'quest_template'))
        with self.assertRaises(ValueError):
            list(generator.table_rows(DUMP.replace("(13,40,'',1500)", "(13,40,1500)"), 'quest_template'))

    def test_rendered_table_is_recreated_from_scratch(self):
        text = generator.render([(2, 2500), (5, 400)], 'a' * 40, 'b' * 40)
        self.assertIn('DROP TABLE IF EXISTS `custom_quest_xp_tbc`;\nCREATE TABLE `custom_quest_xp_tbc`', text)
        self.assertIn('tbc-db ' + 'a' * 40, text)
        self.assertIn('mangos-tbc ' + 'b' * 40, text)
        self.assertTrue(text.endswith('VALUES\n(2, 2500),\n(5, 400);\n'))


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.checkout = self.root / 'tbc-db'
        (self.checkout / 'Full_DB').mkdir(parents=True)
        (self.checkout / 'Updates').mkdir()
        with gzip.open(self.checkout / generator.DUMP, 'wt', encoding='utf-8') as handle:
            handle.write(DUMP)
        (self.checkout / 'Updates/0001_npc.sql').write_text('UPDATE `creature_template` SET `Rank` = 1;\n')
        git = ['git', '-C', str(self.checkout), '-c', 'user.name=test', '-c', 'user.email=test@localhost']
        subprocess.run([*git, 'init', '-q'], check=True)
        subprocess.run([*git, 'add', '-A'], check=True)
        subprocess.run([*git, 'commit', '-qm', 'dump'], check=True)
        self.revision = generator.checkout_revision(self.checkout)
        self.core = self.root / 'core'
        (self.core / generator.CORE_QUESTS).parent.mkdir(parents=True)
        (self.core / generator.CORE_QUESTS).write_text(CORE)

    def lock(self, revision):
        repository = self.root / f'repository-{revision[:8]}'
        repository.mkdir()
        sources = [{'name': generator.SOURCE, 'revision': revision},
                   {'name': generator.CORE_SOURCE, 'revision': 'c' * 40}]
        (repository / 'versions.lock.json').write_text(json.dumps({'historicalClassData': {'sources': sources}}))
        return repository

    def test_pinned_checkout_generates_the_table(self):
        text = generator.generate(self.checkout, self.core, self.lock(self.revision))
        self.assertEqual(generator.render(generator.quest_values(DUMP, CORE), self.revision, 'c' * 40), text)

    def test_other_revisions_are_refused(self):
        with self.assertRaises(SystemExit):
            generator.generate(self.checkout, self.core, self.lock('d' * 40))

    def test_unapplied_quest_updates_are_refused(self):
        (self.checkout / 'Updates/0002_quest.sql').write_text('UPDATE `quest_template` SET `QuestLevel` = 1;\n')
        with self.assertRaises(SystemExit):
            generator.generate(self.checkout, self.core, self.lock(self.revision))


if __name__ == '__main__':
    unittest.main()
