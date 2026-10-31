"""Tests for the era world-content generator; no database server required."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generate_era_world_content as generator


HEADER = 'enum ProgressionState : uint8\n{\n    PROGRESSION_START = 0,\n    PROGRESSION_PRE_TBC = 8,\n    PROGRESSION_TBC_TIER_4 = 12,\n    PROGRESSION_TBC_TIER_5 = 13,\n};\n'
SOURCE = '''
class npc_ipp_tbc : public CreatureScript
{
public:
    npc_ipp_tbc() : CreatureScript("npc_ipp_tbc") { }

    struct npc_ipp_tbcAI: ScriptedAI
    {
        bool CanBeSeen(Player const* player) override
        {
            if (player->IsGameMaster() || !sIndividualProgression->enabled)
                return true;

            Player* target = ObjectAccessor::FindConnectedPlayer(player->GetGUID());
            if (sIndividualProgression->hasPassedProgression(target, PROGRESSION_PRE_TBC))
                return true;
            else
                return false;
        }
    };
};

class npc_ipp_za : public CreatureScript
{
public:
    npc_ipp_za() : CreatureScript("npc_ipp_za") { }

    struct npc_ipp_zaAI: ScriptedAI
    {
        bool CanBeSeen(Player const* player) override
        {
            Player* target = ObjectAccessor::FindConnectedPlayer(player->GetGUID());

            uint32 PLAYER_PROGRESSION = sIndividualProgression->GetPlayerProgressionFromQuests(target);
            ProgressionState REQUIRED_ZA_PROGRESSION = static_cast<ProgressionState>(sIndividualProgression->RequiredZulAmanProgression);

            if (PLAYER_PROGRESSION >= REQUIRED_ZA_PROGRESSION)
                return true;
            else
                return false;
        }
    };
};

class gobject_ipp_closed : public GameObjectScript
{
public:
    gobject_ipp_closed() : GameObjectScript("gobject_ipp_closed") { }

    struct gobject_ipp_closedAI: GameObjectAI
    {
        bool CanBeSeen(Player const* player) override
        {
            Player* target = ObjectAccessor::FindConnectedPlayer(player->GetGUID());
            if (target->GetQuestStatus(66106) == QUEST_STATUS_REWARDED)
                return false;
            else
                return true;
        }
    };
};

class boss_plain : public CreatureScript
{
public:
    boss_plain() : CreatureScript("boss_plain") { }
};
'''


def stages(mask):
    return [stage for stage in generator.STAGES if mask >> stage & 1]


class AwarenessRules(unittest.TestCase):
    def test_stage_rules_follow_the_module_sources_and_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            ip = Path(directory)
            (ip / 'src/sub').mkdir(parents=True)
            (ip / 'conf').mkdir()
            (ip / 'src/IndividualProgression.h').write_text(HEADER)
            (ip / 'src/sub/Awareness.cpp').write_text(SOURCE)
            (ip / 'conf/individualProgression.conf.dist').write_text(
                'IndividualProgression.RequiredZulGurubProgression = 3\n'
                'IndividualProgression.RequiredZulAmanProgression = 12\n'
                'IndividualProgression.AllowEarlyDungeonSet2 = 0\n')
            rules = generator.awareness_rules(ip)
        self.assertEqual(stages(rules['npc_ipp_tbc']), list(range(8, 19)))
        self.assertEqual(stages(rules['npc_ipp_za']), list(range(12, 19)))
        # Quest-status and plain scripts are the module's own decisions, not stage rules.
        self.assertIsNone(rules['gobject_ipp_closed'])
        self.assertIsNone(rules['boss_plain'])


class Render(unittest.TestCase):
    def replay(self, sql):
        db = sqlite3.connect(':memory:')
        db.executescript('''
            CREATE TABLE creature (guid INTEGER PRIMARY KEY, id INTEGER);
            CREATE TABLE gameobject (guid INTEGER PRIMARY KEY, id INTEGER);
            CREATE TABLE quest_template (ID INTEGER PRIMARY KEY);
            CREATE TABLE npc_vendor (entry INTEGER, item INTEGER);
            CREATE TABLE conditions (SourceTypeOrReferenceId INTEGER, SourceGroup INTEGER, SourceEntry INTEGER,
                SourceId INTEGER, ElseGroup INTEGER, ConditionTypeOrReference INTEGER, ConditionTarget INTEGER,
                ConditionValue1 INTEGER, ConditionValue2 INTEGER, ConditionValue3 INTEGER, NegativeCondition INTEGER,
                ErrorType INTEGER, ErrorTextId INTEGER, ScriptName TEXT, Comment TEXT,
                PRIMARY KEY (SourceTypeOrReferenceId, SourceGroup, SourceEntry, SourceId, ElseGroup,
                    ConditionTypeOrReference, ConditionTarget, ConditionValue1, ConditionValue2, ConditionValue3));
            INSERT INTO creature VALUES (10, 30713), (11, 30713), (12, 4949);
            INSERT INTO gameobject VALUES (20, 187290);
            INSERT INTO quest_template VALUES (11123), (7848);
            INSERT INTO npc_vendor VALUES (66, 39354), (66, 159), (4775, 20975);
            INSERT INTO conditions VALUES (19, 0, 11123, 0, 3, 16, 0, 1, 0, 0, 0, 0, 0, '', 'custom race'),
                (19, 0, 11123, 0, 5, 16, 0, 2, 0, 0, 0, 0, 0, '', 'custom race'),
                (30, 0, 30713, 11, 0, 8, 0, 66013, 0, 0, 0, 0, 0, '', 'Era content: Wrath creature');
        ''')
        script = sql.replace('INSERT IGNORE', 'INSERT OR IGNORE')
        db.executescript(script)
        first = sorted(db.execute('SELECT * FROM conditions'))
        db.executescript(script)
        self.assertEqual(sorted(db.execute('SELECT * FROM conditions')), first)
        return db

    def test_gates_name_spawns_alternatives_and_vendor_pairs(self):
        sql = generator.render([(30, 0, 30713, 10, 66013), (30, 1, 187290, 20, 66008),
                                (19, 0, 11123, 0, 66008), (23, 66, 39354, 0, 66013), (23, 4775, 20975, 0, 66008)])
        db = self.replay(sql)
        rows = set(db.execute("SELECT SourceTypeOrReferenceId, SourceGroup, SourceEntry, SourceId, ElseGroup, "
                              "ConditionValue1 FROM conditions WHERE Comment LIKE 'Era content: %'"))
        self.assertEqual(rows, {(30, 0, 30713, 10, 0, 66013), (30, 1, 187290, 20, 0, 66008),
                                (19, 0, 11123, 0, 3, 66008), (19, 0, 11123, 0, 5, 66008),
                                (23, 66, 39354, 0, 0, 66013), (23, 4775, 20975, 0, 0, 66008)})
        # A stale spawn gate from an earlier run is removed; custom rows stay.
        self.assertEqual(db.execute("SELECT COUNT(*) FROM conditions WHERE Comment = 'custom race'").fetchone()[0], 2)
        self.assertIsNone(db.execute('SELECT 1 FROM conditions WHERE SourceId = 11').fetchone())
        self.assertIsNone(db.execute('SELECT 1 FROM conditions WHERE SourceGroup = 66 AND SourceEntry = 159').fetchone())


if __name__ == '__main__':
    unittest.main()
