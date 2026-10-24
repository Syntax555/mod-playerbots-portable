"""Exercise historical class acquisition through production quest and trainer gates.

Replay the delivered SQL against the pinned world dumps, compile actual core and
Individual Progression decisions, and generate client/server spell records. World,
session and storage adapters are isolated; this does not start a realm or certify
every historical quest. --base-dbc additionally verifies a supplied native DBC.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import struct
import subprocess
import sys
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    TIMEOUT,
    cxx,
    function,
    make_wdbc,
    pinned_source,
    prepared_core,
    source_argument,
    wdbc,
)
import yaml


def values(source):
    """Read a dump tuple, including MySQL-escaped quest text, without evaluating it."""
    result, cursor = [], 0
    while cursor < len(source):
        if source[cursor] == "'":
            cursor += 1
            value = ''
            while cursor < len(source):
                character = source[cursor]
                cursor += 1
                if character == '\\':
                    character = source[cursor]
                    cursor += 1
                    value += {'n': '\n', 'r': '\r', 't': '\t', '0': '\0'}.get(character, character)
                elif character == "'":
                    if cursor < len(source) and source[cursor] == "'":
                        value += "'"
                        cursor += 1
                    else:
                        break
                else:
                    value += character
        else:
            end = source.find(',', cursor)
            if end < 0:
                end = len(source)
            token = source[cursor:end].strip()
            value = None if token == 'NULL' else (float(token) if '.' in token else int(token))
            cursor = end
        result.append(value)
        if cursor < len(source):
            assert source[cursor] == ',', source[cursor:cursor + 20]
            cursor += 1
    return result


def dump(db, directory, table):
    source = (directory / (table + '.sql')).read_text(encoding='utf-8')
    columns = re.findall(r'^  `([^`]+)`', source, re.MULTILINE)
    assert columns, table
    primary = re.search(r'PRIMARY KEY \(([^\n]+)\)', source)
    constraint = ',PRIMARY KEY (' + primary.group(1) + ')' if primary else ''
    constraint += ''.join(',UNIQUE (' + key + ')' for key in re.findall(r'UNIQUE KEY `[^`]+` \(([^\n]+)\)', source))
    db.execute('CREATE TABLE "' + table + '" (' + ','.join('"' + c + '"' for c in columns) + constraint + ')')
    rows = []
    for match in re.finditer(r'^\((.+)\)[,;]$', source, re.MULTILINE):
        row = values(match.group(1))
        assert len(row) == len(columns), (table, len(row), len(columns))
        rows.append(row)
    assert rows, table
    db.executemany('INSERT INTO "' + table + '" VALUES (' + ','.join('?' for _ in columns) + ')', rows)
    return {row[0]: dict(zip(columns, row)) for row in rows}


def snapshot(db, tables):
    return {table: db.execute('SELECT * FROM "' + table + '" ORDER BY 1,2').fetchall() for table in tables}


def assert_historical_rank_chains(db):
    singletons = db.execute('SELECT first_spell_id FROM spell_ranks WHERE first_spell_id>=948081 '
                            'GROUP BY first_spell_id HAVING COUNT(*)=1').fetchall()
    assert not singletons, ('single-rank historical spells must not enter spell_ranks', singletons)


def compile_run(temporary, name, source, expected=True):
    cpp, executable = temporary / (name + '.cpp'), temporary / name
    cpp.write_text(source)
    command = [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror']
    if os.name != 'nt':
        command += [*SANITIZER_FLAGS, '-fno-pie', '-no-pie']
    subprocess.run(command + [str(cpp), '-o', str(executable)], check=True)
    result = subprocess.run([str(executable)], text=True, capture_output=True, check=False, timeout=TIMEOUT)
    if expected:
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout.strip())
    else:
        assert result.returncode != 0, name + ' did not detect the reverted gate'


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, 'core')
parser.add_argument('--ip', type=Path)
parser.add_argument('--era', type=Path)
parser.add_argument('--base-dbc', type=Path)
parser.add_argument('--era-client', type=Path)
parser.add_argument('--mpq-reader', type=Path)
args = parser.parse_args()
repository = Path(__file__).resolve().parents[2]
core = args.core or prepared_core(repository)
ip = args.ip or core / 'modules/mod-individual-progression'
era = args.era or core / 'modules/mod-era-talents'
world = core / 'data/sql/base/db_world'
fallback = prepared_core(repository)


def core_file(relative):
    path = core / relative
    return path if path.exists() else fallback / relative


quest_source = core_file('src/server/game/Entities/Player/PlayerQuest.cpp').read_text()
historical = (ip / 'src/HistoricalClassQuests.cpp').read_text()
progress_source = (ip / 'src/IndividualProgression.cpp').read_text()
progress_enum = function((ip / 'src/IndividualProgression.h').read_text(), 'enum ProgressionState') + ';'
trainer_source = core_file('src/server/game/Entities/Creature/Trainer.cpp').read_text()
rank_loader = function(core_file('src/server/game/Spells/SpellMgr.cpp').read_text(), 'void SpellMgr::LoadSpellRanks()')
assert 'if (rankChain.size() < 2)' in rank_loader, 'native minimum rank-chain length changed'
condition_source = core_file('src/server/game/Conditions/ConditionMgr.cpp').read_text()
condition_header = core_file('src/server/game/Conditions/ConditionMgr.h').read_text()
sql = (ip / 'data/sql/world/updates/2026_10_11_00_historical_class_quests.sql').read_text().replace('INSERT IGNORE', 'INSERT OR IGNORE')
condition_sql = (ip / 'data/sql/world/updates/2026_10_15_00_historical_class_quest_conditions.sql').read_text().replace('INSERT IGNORE', 'INSERT OR IGNORE')
training = (era / 'data/sql/world/base/2026_10_11_00_historical_priest_training.sql').read_text().replace('INSERT IGNORE', 'INSERT OR IGNORE')
rank_cleanup = (era / 'data/sql/world/updates/2026_10_24_00_historical_priest_singletons.sql').read_text()

db = sqlite3.connect(':memory:')
tables = ('quest_template', 'quest_template_addon', 'disables', 'creature_queststarter',
          'creature_questender', 'trainer_spell', 'spell_ranks', 'spell_script_names', 'spell_bonus_data', 'conditions')
rows = {table: dump(db, world if world.exists() else fallback / 'data/sql/base/db_world', table)
        for table in tables}
# The native rewarded-quest condition requires a real nonrepeatable template.
markers = (ip / 'data/sql/world/base/player_progression.sql').read_text()
marker_insert = re.search(r'INSERT INTO `quest_template`.*?;', markers, re.DOTALL).group()
db.executescript(marker_insert)
marker_addon = re.search(r'INSERT INTO `quest_template_addon`.*?;', markers, re.DOTALL).group()
db.executescript(marker_addon)
for marker in range(66001, 66019):
    row = db.execute('SELECT * FROM quest_template WHERE ID=?', (marker,)).fetchone()
    assert row is not None
    special = db.execute('SELECT SpecialFlags FROM quest_template_addon WHERE ID=?', (marker,)).fetchone()
    assert special is not None and not special[0] & 1, 'marker unexpectedly repeatable'
# Existing custom OR alternatives must both keep the progression gate.
custom_conditions = [(19, 0, 5634, 0, group, 16, 0, race, 0, 0, 0, 0, 0, '', 'Custom historical race')
                     for group, race in ((7, 1), (9, 4))]
custom_conditions.append((19, 0, 5634, 0, 11, 8, 0, 66013, 0, 0, 0, 0, 0, '', 'Custom positive marker'))
db.executemany('INSERT INTO conditions VALUES (' + ','.join('?' for _ in range(15)) + ')', custom_conditions)
# Replay an upgrade from the previously shipped unnecessary rank-one entries.
single_rank_spells = (948089, 949316, 949377, 949378)
db.executemany('INSERT INTO spell_ranks (first_spell_id,spell_id,rank) VALUES (?,?,1)',
               ((spell, spell) for spell in single_rank_spells))
before = snapshot(db, tables)
db.executescript(sql)
db.executescript(condition_sql)
db.executescript(training)
db.executescript(rank_cleanup)
after = snapshot(db, tables)
db.executescript(sql)
db.executescript(condition_sql)
db.executescript(training)
db.executescript(rank_cleanup)
assert snapshot(db, tables) == after, 'migrations are not idempotent'
assert before['quest_template_addon'] == after['quest_template_addon'], 'native class/race/chain gates changed'
assert_historical_rank_chains(db)
rank_schema = db.execute("SELECT sql FROM sqlite_master WHERE name='spell_ranks'").fetchone()[0]


def cleaned_ranks(source, records):
    with sqlite3.connect(':memory:') as upgrade:
        upgrade.execute(rank_schema)
        upgrade.executemany('INSERT INTO spell_ranks VALUES (?,?,?)', records)
        upgrade.executescript(source)
        result = set(upgrade.execute('SELECT * FROM spell_ranks'))
        upgrade.executescript(source)
        assert set(upgrade.execute('SELECT * FROM spell_ranks')) == result, 'rank cleanup is not idempotent'
        return result


preserved_ranks = set(after['spell_ranks']) | {(1000000, 1000000, 1)}
singletons = {(spell, spell, 1) for spell in single_rank_spells}
assert cleaned_ranks(rank_cleanup, preserved_ranks | singletons) == preserved_ranks
for spell in single_rank_spells:
    removed = rank_cleanup.replace(str(spell), '0', 1)
    assert removed != rank_cleanup
    assert cleaned_ranks(removed, preserved_ranks | singletons) != preserved_ranks, ('missing singleton cleanup', spell)
for description, custom, old, new in (
    ('multiple ranks', singletons | {(spell, 1000001 + i, 2) for i, spell in enumerate(single_rank_spells)},
     'HAVING COUNT(*) = 1', 'HAVING COUNT(*) >= 1'),
    ('custom spell', {(spell, 1000001 + i, 1) for i, spell in enumerate(single_rank_spells)},
     '  AND `spell_id` = `first_spell_id`\n', ''),
    ('custom rank', {(spell, spell, 2) for spell in single_rank_spells}, '  AND `rank` = 1\n', ''),
    ('unrelated singleton', set(), 'WHERE `first_spell_id` IN (948089, 949316, 949377, 949378)', 'WHERE 1'),
):
    records = preserved_ranks | custom
    assert cleaned_ranks(rank_cleanup, records) == records, ('custom ranks changed', description)
    removed = rank_cleanup.replace(old, new)
    assert removed != rank_cleanup
    assert cleaned_ranks(removed, records) != records, ('rank cleanup scope mutation undetected', description)
print('Historical rank SQL: scoped upgrade cleanup, custom chains, idempotence and eight mutations passed')

# Independently recorded historical roots. Class/race, objectives and exclusive
# groups continue to come from the native quest dump, rather than this test.
families = (
    ((5634, 5635, 5636, 5637, 5638, 5639), 5, 10, 948081, 949300, 948090),
    ((5641, 5645, 5647), 4, 20, 948089, 0, 948091),
    ((5627, 5628, 5629, 5630, 5631, 5632, 5633), 8, 10, 949100, 949308, 949290),
    ((5672, 5673, 5674, 5675), 8, 20, 949107, 949316, 949291),
    ((5658, 5660, 5661, 5662, 5663), 16, 10, 949112, 949317, 949292),
    ((5652, 5654, 5655, 5656, 5657), 128, 10, 949124, 949331, 949293),
    ((5642, 5643, 5680), 128, 20, 949130, 949338, 949294),
    ((5676, 5677), 1, 20, 949142, 949352, 949295),
    ((5644, 5646, 5679), 16, 20, 949152, 949364, 949296),
)
quest_ids = tuple(q for family in families for q in family[0])
for family in families:
    for quest in family[0]:
        assert rows['quest_template_addon'][quest]['AllowableClasses'] == 16, quest
        assert rows['quest_template'][quest]['MinLevel'] == family[2], quest
        native_races = 1028 if quest in families[1][0] else family[1]
        assert rows['quest_template'][quest]['AllowableRaces'] == native_races, quest
assert any(row[0:2] == (1, 5634) for row in before['disables']), 'baseline no longer demonstrates the reported missing prayer quest'
quest_columns = list(rows['quest_template'][5634])
assert set(before['conditions']) <= set(after['conditions']), 'custom/native conditions changed'
for quest in quest_ids:
    gates = db.execute('SELECT ElseGroup,ConditionValue1,NegativeCondition FROM conditions WHERE SourceTypeOrReferenceId=19 AND SourceEntry=? AND ConditionTypeOrReference=8 AND NegativeCondition=1', (quest,)).fetchall()
    first = 66008 if quest in families[1][0] else 66013
    groups = (7, 9, 11) if quest == 5634 else (0,)
    assert set(gates) == {(group, marker, 1) for group in groups for marker in range(first, 66019)}, quest
# The native primary key omits NegativeCondition. Dropping the discriminator
# must fail the same gate check when a custom positive marker occupies it.
with sqlite3.connect(':memory:') as collision:
    collision.execute(db.execute("SELECT sql FROM sqlite_master WHERE name='conditions'").fetchone()[0])
    collision.execute('CREATE TABLE quest_template (ID INTEGER PRIMARY KEY, RewardSpell INTEGER)')
    collision.execute('INSERT INTO quest_template VALUES (5634,948090)')
    collision.executemany('INSERT INTO conditions VALUES (' + ','.join('?' for _ in range(15)) + ')', custom_conditions)
    mutated_sql = condition_sql.replace('marker.`ID`, 1, 0, 1', 'marker.`ID`, 0, 0, 1')
    assert mutated_sql != condition_sql
    collision.executescript(mutated_sql)
    gates = collision.execute('SELECT ElseGroup,ConditionValue1,NegativeCondition FROM conditions WHERE SourceTypeOrReferenceId=19 AND SourceEntry=5634 AND ConditionTypeOrReference=8 AND NegativeCondition=1').fetchall()
    assert set(gates) != {(group, marker, 1) for group in (7, 9, 11) for marker in range(66013, 66019)}
print('Historical SQL mutation rejected: colliding positive marker swallowed the availability gate')
for original, current in zip(before['quest_template'], after['quest_template']):
    assert original[0] == current[0]
    if original[0] not in quest_ids:
        assert original == current, ('unrelated quest changed', original[0])
for table in ('disables', 'creature_queststarter', 'creature_questender'):
    old_set, new_set = set(before[table]), set(after[table])
    changed = old_set ^ new_set
    assert all(row[1] in quest_ids for row in changed), ('unrelated quest relation/disable changed', table)
for table, spell_column in (('trainer_spell', 1), ('spell_ranks', 0), ('spell_bonus_data', 0), ('spell_script_names', 0)):
    assert [r for r in before[table] if r[spell_column] < 900000] == \
           [r for r in after[table] if r[spell_column] < 900000], ('native Wrath rows changed', table)
for quest_id in quest_ids:
    original = rows['quest_template'][quest_id]
    actual_columns = list(original)
    current = dict(zip(actual_columns, db.execute('SELECT * FROM quest_template WHERE ID=?', (quest_id,)).fetchone()))
    for column in actual_columns:
        if column not in ('RewardSpell', 'RewardDisplaySpell'):
            assert current[column] == original[column], (quest_id, column)
    assert not db.execute('SELECT 1 FROM disables WHERE sourceType=1 AND entry=? AND comment=\'Deprecated quest\'',
                         (quest_id,)).fetchone()
    assert db.execute('SELECT 1 FROM creature_queststarter WHERE quest=?', (quest_id,)).fetchone()
    assert db.execute('SELECT 1 FROM creature_questender WHERE quest=?', (quest_id,)).fetchone()
for quest, npc in ((5634, 4092), (5635, 1226), (5636, 3600), (5637, 377), (5638, 11397), (5639, 11406)):
    assert db.execute('SELECT 1 FROM creature_queststarter WHERE id=? AND quest=?', (npc, quest)).fetchone()
    assert db.execute('SELECT 1 FROM creature_questender WHERE id=376 AND quest=?', (quest,)).fetchone()

# A customized reward must not activate the stock historical quest automatically.
db.execute('UPDATE quest_template SET RewardSpell=123456,RewardDisplaySpell=123456 WHERE ID=5634')
db.execute("INSERT INTO disables (sourceType,entry,flags,params_0,params_1,comment) VALUES(1,5634,0,'','','Deprecated quest')")
db.executescript(sql)
assert db.execute('SELECT RewardSpell,RewardDisplaySpell FROM quest_template WHERE ID=5634').fetchone() == (123456, 123456)
assert db.execute('SELECT 1 FROM disables WHERE sourceType=1 AND entry=5634').fetchone()
db.execute('DELETE FROM disables WHERE sourceType=1 AND entry=5634')
db.execute('UPDATE quest_template SET RewardSpell=948090,RewardDisplaySpell=948081 WHERE ID=5634')
print('Historical SQL: native quest/condition data, every custom OR branch, later-marker gaps, idempotence and customized rewards passed')

FIXTURE = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <functional>
#include <list>
#include <map>
#include <set>
#include <string>
#include <utility>
#include <vector>
using uint8=std::uint8_t; using uint16=std::uint16_t; using uint32=std::uint32_t; using int32=std::int32_t;
constexpr uint8 CLASS_PRIEST=5,RACE_HUMAN=1,RACE_DWARF=3,RACE_NIGHTELF=4,RACE_UNDEAD_PLAYER=5,RACE_TROLL=8,RACE_BLOODELF=10,RACE_DRAENEI=11;
constexpr uint32 MAX_MONEY_AMOUNT=2147483647, SPELL_EFFECT_LEARN_SPELL=36, SPELL_EFFECT_CREATE_ITEM=24, SPELL_EFFECT_DUMMY=3, SPELL_EFFECT_ENERGIZE=30, EFFECT_0=0, SPELLFAMILY_PRIEST=6;
using SpellEffIndex=uint32;
enum SpellCastResult{SPELL_CAST_OK,SPELL_FAILED_NOTHING_TO_DISPEL};
enum { DISABLE_TYPE_QUEST, INVALIDREASON_DONT_HAVE_REQ, INVALIDREASON_QUEST_FAILED_LOW_LEVEL,
 INVALIDREASON_QUEST_FAILED_WRONG_RACE, QUEST_STATUS_NONE, QUEST_STATUS_INCOMPLETE, QUEST_STATUS_COMPLETE, QUEST_STATUS_REWARDED,
 QUEST_SPECIAL_FLAGS_DELIVER, QUEST_ITEM_OBJECTIVES_COUNT=4, EQUIP_ERR_ITEM_NOT_FOUND=7, CONFIG_QUEST_HIGH_LEVEL_HIDE_DIFF=8 };
PROGRESSION_ENUM
CONDITION_ENUMS
struct Quest {
 using PrevQuests=std::vector<int32>;
 uint32 id=0,minLevel=1,maxLevel=0,races=0,classes=0,rewardSpell=0,rewardDisplay=0;
 int32 exclusiveGroup=0; PrevQuests prevQuests;
 std::array<uint32,4> RequiredItemCount{},RequiredItemId{};
 bool IsSeasonal() const {return false;} bool IsRepeatable() const {return false;}
 bool IsDFQuest() const {return false;} bool IsAutoComplete() const {return false;}
 uint32 GetQuestMethod() const {return 2;} bool HasSpecialFlag(int) const {return false;}
 int32 GetRewOrReqMoney() const {return 0;}
 int32 GetExclusiveGroup() const {return exclusiveGroup;}
 uint32 GetQuestId() const {return id;} uint32 GetMinLevel() const {return minLevel;}
 uint32 GetMaxLevel() const {return maxLevel;} uint32 GetAllowableRaces() const {return races;}
 uint32 GetRequiredClasses() const {return classes;} uint32 GetRewSpellCast() const {return rewardSpell;}
 uint32 GetRewSpell() const {return rewardDisplay;}
};
struct ObjectMgr {
 using Groups=std::multimap<int32,uint32>; using ExclusiveQuestGroupsBounds=std::pair<Groups::const_iterator,Groups::const_iterator>;
 Groups mExclusiveQuestGroups; std::map<uint32,Quest> quests;
 Quest const* GetQuestTemplate(uint32 id) const {auto i=quests.find(id);return i==quests.end()?nullptr:&i->second;}
} objects; auto* sObjectMgr=&objects;
struct DisableMgr {std::set<uint32> disabled; bool IsDisabledFor(int,uint32 id,void const*)const{return disabled.contains(id);}} disables;
auto* sDisableMgr=&disables;
struct World { uint32 getIntConfig(int) const {return 0;} } world; auto* sWorld=&world;
struct Object {virtual ~Object()=default;Object* ToUnit(){return this;}struct Player* GetCharmerOrOwnerPlayerOrPlayerItself();bool IsUnit()const{return false;} uint32 GetGUID()const{return 0;}virtual uint32 getRaceMask()const{return 0;}};
struct Creature: Object { void SendPlaySpellVisual(uint32){} void SendPlaySpellImpact(uint32,uint32){}
 void CastSpell(struct Player*,uint32,bool){} };
struct SpellEffectInfo {uint32 Effect=0,TriggerSpell=0;bool IsEffect(uint32 id)const{return Effect==id;}};
struct SpellInfo {uint32 Id=0;std::vector<SpellEffectInfo> effects;uint32 SpellFamilyName=SPELLFAMILY_PRIEST;
 bool HasEffect(uint32 id)const{return std::any_of(effects.begin(),effects.end(),[id](auto const& e){return e.IsEffect(id);});}
 bool IsSelfCast()const{return true;} bool IsPrimaryProfessionFirstRank()const{return false;}
 auto const& GetEffects()const{return effects;}};
struct Spell {SpellInfo const* info=nullptr;bool cancelled=false;SpellInfo const* GetSpellInfo()const{return info;}void cancel(){cancelled=true;}};
struct Aura{SpellInfo const* info;bool passive=false,removed=false;bool IsPassive()const{return passive;}bool IsRemoved()const{return removed;}SpellInfo const* GetSpellInfo()const{return info;}};
struct AuraApplication{Aura* aura;bool positive=true;uint32 removeMode=0;uint32 GetRemoveMode()const{return removeMode;}bool IsPositive()const{return positive;}Aura const* GetBase()const{return aura;}};
struct SpellMgr {
 std::map<uint32,SpellInfo> spells;std::map<uint32,uint32> previous;
 SpellInfo const* GetSpellInfo(uint32 id)const{auto i=spells.find(id);return i==spells.end()?nullptr:&i->second;}
 SpellInfo const* AssertSpellInfo(uint32 id)const{auto p=GetSpellInfo(id);assert(p);return p;}
 uint32 GetPrevSpellInChain(uint32 id)const{auto i=previous.find(id);return i==previous.end()?0:i->second;}
 std::vector<std::pair<uint32,uint32>> GetSpellsRequiredForSpellBounds(uint32)const{return {};}
} spellMgr; auto* sSpellMgr=&spellMgr;
struct Player;
namespace Trainer {
enum class SpellState {Available,Unavailable,Known};enum class Type {Class,Pet,Mount,Tradeskill};enum class FailReason {Unavailable,NotEnoughSkill,NotEnoughMoney};
struct Spell {uint32 SpellId=0,MoneyCost=0,ReqSkillLine=0,ReqSkillRank=0;std::array<int32,3> ReqAbility{};uint32 ReqLevel=0;bool IsCastable()const;};
class Trainer {public:uint32 _trainerId=11,_requirement=5;Type _type=Type::Class;std::vector<Spell> _spells;uint32 failures=0,successes=0;
uint32 GetTrainerRequirement()const{return _requirement;}Type GetTrainerType()const{return _type;}
Spell const* GetSpell(uint32)const;SpellState GetDefaultSpellState(struct ::Player const*,Spell const*)const;
SpellState GetSpellState(struct ::Player const*,Spell const*)const;bool CanTeachSpell(struct ::Player const*,Spell const*)const;
bool IsTrainerValidForPlayer(struct ::Player const*)const;uint32 GetSpellCost(struct ::Player const*,Creature const*,Spell const*)const;
void TeachSpell(Creature*,struct ::Player*,uint32);void SendTeachFailure(Creature*,struct ::Player*,uint32,FailReason){++failures;}
void SendTeachSucceeded(Creature*,struct ::Player*,uint32){++successes;}};
}
namespace WorldPackets::NPC {struct TrainerListSpell {int32 SpellID=0;};struct TrainerList {std::vector<TrainerListSpell> Spells;};}
struct Player: Object {
 uint8 race=3,playerClass=5,state=0;uint32 level=10,money=10000;bool inWorld=true;
 uint32 sideEffects=0,moneyChanges=0;float discount=1.0f;std::set<uint32> known,rewarded;
 std::map<uint32,int> active;mutable std::vector<int> errors;
 std::map<uint32,AuraApplication*> applied;uint32 removedAuras=0;
 auto const& GetAppliedAuras()const{return applied;}void RemoveAura(AuraApplication* aura){for(auto i=applied.begin();i!=applied.end();){if(i->second==aura){i=applied.erase(i);++removedAuras;}else ++i;}}
 uint32 GetLevel()const{return level;}uint8 getRace()const{return race;}uint8 getClass()const{return playerClass;}
 uint32 getRaceMask()const{return 1u<<(race-1);}uint32 getClassMask()const{return 1u<<(playerClass-1);}
 bool IsInWorld()const{return inWorld;}bool GetQuestRewardStatus(uint32 id)const;
 bool IsQuestRewarded(uint32 id)const{return rewarded.contains(id)||(state&&id==66000u+state);}int GetQuestStatus(uint32 id)const{if(id==66000u+state&&state)return QUEST_STATUS_REWARDED;auto i=active.find(id);return i==active.end()?QUEST_STATUS_NONE:i->second;}
 void SendCanTakeQuestResponse(int e)const{errors.push_back(e);}void SendEquipError(int,void*,void*,uint32){}
 uint32 GetItemCount(uint32)const{return 0;}bool HasEnoughMoney(uint32 cost)const{return money>=cost;}
 void ModifyMoney(int32 delta){assert(std::int64_t(money)+delta>=0);money=uint32(std::int64_t(money)+delta);++moneyChanges;}
 bool HasSpell(uint32 id)const{return known.contains(id);}void learnSpell(uint32,bool=false,bool=false);Player* ToPlayer(){return this;}
 void CastSpell(Player*,uint32,bool);bool IsSpellFitByClassAndRace(uint32)const{return playerClass==5;}
 uint32 GetBaseSkillValue(uint32)const{return 0;}uint32 GetFreePrimaryProfessionPoints()const{return 2;}
 float GetReputationPriceDiscount(Creature const*)const{return discount;}
 struct Map {Creature* GetCreature(uint32)const{return nullptr;}} map;Map* GetMap(){return &map;}
 void RemoveActiveQuest(uint32 id,bool){active.erase(id);}void SetRewardedQuest(uint32 id){rewarded.insert(id);}
 bool CanSeeStartQuest(Quest const*);bool CanTakeQuest(Quest const*,bool);bool CanRewardQuest(Quest const*,bool);
 void RewardQuest(Quest const*,uint32,Object*,bool,bool);
 bool SatisfyQuestPreviousQuest(Quest const*,bool)const;bool SatisfyQuestExclusiveGroup(Quest const*,bool)const;
 bool SatisfyQuestClass(Quest const*,bool)const;bool SatisfyQuestRace(Quest const*,bool)const;bool SatisfyQuestLevel(Quest const*,bool)const;
 bool SatisfyQuestStatus(Quest const* q,bool)const{return GetQuestStatus(q->id)==QUEST_STATUS_NONE&&!rewarded.contains(q->id);}
#define GUARD(name) bool name(Quest const*,bool)const{return true;}
 GUARD(SatisfyQuestSkill) GUARD(SatisfyQuestReputation) GUARD(SatisfyQuestTimed) GUARD(SatisfyQuestNextChain)
 GUARD(SatisfyQuestPrevChain) GUARD(SatisfyQuestBreadcrumb) GUARD(SatisfyQuestDay) GUARD(SatisfyQuestWeek)
 GUARD(SatisfyQuestMonth) GUARD(SatisfyQuestSeasonal)
 bool SatisfyQuestConditions(Quest const*,bool);
#undef GUARD
};
Player* Object::GetCharmerOrOwnerPlayerOrPlayerItself(){return dynamic_cast<Player*>(this);}
using WorldObject=Object;using Unit=Object;
struct IndividualProgression {int progressionLimit=0;bool enabled=true,strictEarnedProgression=true,disableDefaultProgression=false;std::map<uint32,uint32> customProgressionMap;
 bool IsStrictDefaultProgression()const;uint8 GetPlayerProgressionFromQuests(Player*)const;} progression;
auto* sIndividualProgression=&progression;
PRODUCTION_HOOK_ENUM
struct PlayerScript {std::set<uint16> hooks;PlayerScript(char const*,std::vector<uint16> enabled):hooks(enabled.begin(),enabled.end()){}
 virtual ~PlayerScript()=default;
 virtual bool OnPlayerCanLearnSpell(Player*,uint32){return true;}virtual void OnPlayerLogin(Player*){}
 virtual void OnPlayerGetTrainerSpellState(Player const*,uint32,uint32,Trainer::SpellState&){}
 virtual void OnPlayerBeforeReceiveSpellListFromTrainer(Player*,Creature*,WorldPackets::NPC::TrainerList&){}
 virtual void OnPlayerSpellCast(Player*,Spell*,bool){}
};
std::vector<PlayerScript*> registered;
struct ScriptMgr {
 bool OnPlayerCanLearnSpell(Player* p,uint32 id){for(auto* s:registered)if(s->hooks.contains(PLAYERHOOK_CAN_LEARN_SPELL)&&!s->OnPlayerCanLearnSpell(p,id))return false;return true;}
 void OnPlayerGetTrainerSpellState(Player const* p,uint32 trainer,uint32 spell,Trainer::SpellState& state){for(auto* s:registered)s->OnPlayerGetTrainerSpellState(p,trainer,spell,state);}
 void OnPlayerGetTrainerSpellCost(Player const*,Creature const*,uint32,uint32&){}
 void OnPlayerAfterTrainSpell(Player*,Creature*,uint32){}
} scripts;auto* sScriptMgr=&scripts;
struct Condition;
struct ConditionSourceInfo {std::array<Object*,1> mConditionTargets;Condition* mLastFailedCondition=nullptr;
 explicit ConditionSourceInfo(Object* p):mConditionTargets{{p}}{}};
struct Condition {uint32 ConditionType=8,ConditionValue1=0,NegativeCondition=1,ElseGroup=0,ReferenceId=0;
 bool isLoaded()const{return true;}bool Meets(ConditionSourceInfo&);};
using ConditionList=std::list<Condition*>;
using ConditionTypeContainer=std::map<uint32,ConditionList>;
using ConditionContainer=std::map<ConditionSourceType,ConditionTypeContainer>;
using ConditionReferenceContainer=std::map<uint32,ConditionList>;
struct ConditionMgr {ConditionContainer ConditionStore;ConditionReferenceContainer ConditionReferenceStore;
 ConditionList GetConditionsForNotGroupedEntry(ConditionSourceType,uint32);
 bool IsObjectMeetToConditions(WorldObject*,ConditionList const&);
 bool IsObjectMeetToConditions(ConditionSourceInfo&,ConditionList const&);
 bool IsObjectMeetToConditionList(ConditionSourceInfo&,ConditionList const&);
} conditions;auto* sConditionMgr=&conditions;
#define LOG_DEBUG(...) ((void)0)
#define ASSERT(value) assert(value)
struct SpellScript {
 Player* caster=nullptr;SpellInfo const* info=nullptr;
 bool preventDefault=false;void PreventHitDefaultEffect(uint32){preventDefault=true;}
 struct EffectHooks {SpellScript* owner;std::function<void(SpellEffIndex)> handler;uint32 index=999,effect=999;
 template<class T>void operator+=(std::tuple<void(T::*)(SpellEffIndex),uint32,uint32> entry){
  auto fn=std::get<0>(entry);index=std::get<1>(entry);effect=std::get<2>(entry);
  handler=[this,fn](SpellEffIndex index){(static_cast<T*>(owner)->*fn)(index);};}}
 OnEffectHitTarget{this,{},999,999};
 struct CheckHooks{SpellScript* owner;std::function<SpellCastResult()> handler;
 template<class T>void operator+=(SpellCastResult(T::*fn)()){handler=[this,fn](){return(static_cast<T*>(owner)->*fn)();};}}
 OnCheckCast{this,{}};
 virtual ~SpellScript()=default;virtual void Register()=0;
 Player* GetCaster(){return caster;}SpellInfo const* GetSpellInfo(){return info;}
};
#define PrepareSpellScript(name) public:
#define SpellEffectFn(method,index,effect) std::tuple{&method,uint32(index),uint32(effect)}
#define SpellCheckCastFn(method) &method
#define RegisterSpellScript(name) ((void)0)
PRODUCTION_PROGRESS
PRODUCTION_HISTORICAL
PRODUCTION_CONDITIONS
PRODUCTION_QUESTS
PRODUCTION_TRAINER
PRODUCTION_LEARN_GATE
void Player::CastSpell(Player*,uint32 id,bool){
 if(!sScriptMgr->OnPlayerCanLearnSpell(this,id))return;
 for(auto const& effect:sSpellMgr->AssertSpellInfo(id)->effects){
  if(effect.IsEffect(SPELL_EFFECT_LEARN_SPELL))learnSpell(effect.TriggerSpell);
  if(effect.IsEffect(SPELL_EFFECT_DUMMY)){spell_historical_priest_training script;script.caster=this;script.info=sSpellMgr->AssertSpellInfo(id);
   script.Register();assert(script.OnEffectHitTarget.index==EFFECT_0&&script.OnEffectHitTarget.effect==SPELL_EFFECT_DUMMY);
   script.OnEffectHitTarget.handler(EFFECT_0);}
 }
}
int main(){
 historical_class_quests hook;registered.push_back(&hook);
 QUEST_ROWS
 CONDITION_ROWS
 SPELL_ROWS
 Trainer::Trainer trainer;TRAINER_ROWS
 Object giver;Creature npc;
 uint32 cases=0;
 struct Contract{uint32 quest,races,minLevel,vanillaRoot,tbcRoot;};
 std::vector<Contract> contracts={FAMILY_CONTRACTS};
 for(auto const& contract:contracts) {
  uint32 id=contract.quest;
  Quest const* quest=objects.GetQuestTemplate(id);assert(quest);
  for(uint8 tier=0;tier<=18;++tier)for(uint8 race:{1,2,3,4,5,6,7,8,10,11})for(uint8 cls:{1,5,8}) {
   Player p;p.state=tier;p.race=race;p.playerClass=cls;p.level=contract.minLevel;
   uint32 root=tier<8?contract.vanillaRoot:(tier<13?contract.tbcRoot:0);
   bool expected=cls==5&&(contract.races&(1u<<(race-1)))&&root;
   bool nativeEligible=cls==5&&(quest->GetAllowableRaces()&(1u<<(race-1)));
   assert(p.CanSeeStartQuest(quest)==nativeEligible);assert(p.CanTakeQuest(quest,false)==expected);
   assert(!p.CanRewardQuest(quest,false));p.active[id]=QUEST_STATUS_COMPLETE;
   assert(p.CanRewardQuest(quest,false));
   p.RewardQuest(quest,0,&giver,false,false);
   assert(p.sideEffects==1&&p.rewarded.contains(id));
   assert(p.HasSpell(root)==expected);++cases;
  }
 }
 Player p;p.level=60;
 Quest const* prayer=objects.GetQuestTemplate(5634);
 assert(p.CanTakeQuest(prayer,false));p.active[5635]=QUEST_STATUS_INCOMPLETE;
 assert(!p.CanTakeQuest(prayer,false));p.active.clear();p.rewarded.insert(5635);
 assert(!p.CanTakeQuest(prayer,false));p.rewarded.clear();
 p.level=9;assert(!p.CanTakeQuest(prayer,false));p.level=10;
 p.active[5634]=QUEST_STATUS_COMPLETE;p.state=13;
 assert(!p.CanTakeQuest(prayer,false));assert(p.CanRewardQuest(prayer,false));
 p.RewardQuest(prayer,0,&giver,false,false);
 assert(p.sideEffects==1&&!p.active.contains(5634)&&p.rewarded.contains(5634)&&p.known.empty());
 Player capped;capped.state=13;capped.level=60;
 progression.progressionLimit=7;
 assert(!capped.CanTakeQuest(prayer,false));
 capped.rewarded.insert(5634);
 assert(HistoricalClassQuests::CanUseSpell(&capped,948081));
 assert(!HistoricalClassQuests::CanUseSpell(&capped,949300));
 progression.progressionLimit=12;
 assert(!HistoricalClassQuests::CanUseSpell(&capped,948081));
 assert(HistoricalClassQuests::CanUseSpell(&capped,949300));
 progression.progressionLimit=0;
 assert(!HistoricalClassQuests::CanUseSpell(&capped,949300));
 p.rewarded.clear();p.active[5634]=QUEST_STATUS_COMPLETE;
 p.state=0;assert(!HistoricalClassQuests::CanUseSpell(&p,948081));p.learnSpell(948081);assert(p.known.empty());
 p.RewardQuest(prayer,0,&giver,false,false);assert(p.HasSpell(948081));assert(!p.HasSpell(948082));
 p.known.clear();hook.OnPlayerLogin(&p);assert(p.HasSpell(948081)&&!p.HasSpell(948082));
 p.level=18;p.money=99;trainer.TeachSpell(&npc,&p,948082);assert(!p.HasSpell(948082)&&p.money==99);
 p.money=100;trainer.TeachSpell(&npc,&p,948082);assert(p.HasSpell(948082)&&p.money==0);
 for(uint32 id=948083;id<=948087;++id){auto row=trainer.GetSpell(id);assert(row);p.level=row->ReqLevel;p.money=row->MoneyCost;trainer.TeachSpell(&npc,&p,id);assert(p.HasSpell(id)&&p.money==0);}
 Player unpaid;unpaid.level=60;unpaid.money=10000;unpaid.known.insert(948081);
 trainer.TeachSpell(&npc,&unpaid,948082);assert(unpaid.money==10000&&!unpaid.HasSpell(948082));
 p.state=13;auto balance=p.money;p.money=10000;trainer.TeachSpell(&npc,&p,948082);assert(p.money==10000);
 (void)balance;assert(!HistoricalClassQuests::CanUseSpell(&p,948081));assert(HistoricalClassQuests::CanUseSpell(&p,19236));
 WorldPackets::NPC::TrainerList list;list.Spells={{948082},{19236},{6346},{2060}};
 p.state=0;hook.OnPlayerBeforeReceiveSpellListFromTrainer(&p,&npc,list);assert(list.Spells.size()==2);
 Spell denied{spellMgr.AssertSpellInfo(19236)};hook.OnPlayerSpellCast(&p,&denied,false);assert(denied.cancelled);
 uint32 purchases=0;
 for(auto const& contract:contracts)if(contract.quest==objects.GetQuestTemplate(contract.quest)->id){
  for(uint8 tier:{0,8}){
   uint32 root=tier==0?contract.vanillaRoot:contract.tbcRoot;if(!root)continue;
   Player buyer;buyer.state=tier;buyer.level=70;buyer.race=1;
   while(!(contract.races&(1u<<(buyer.race-1))))++buyer.race;
   buyer.active[contract.quest]=QUEST_STATUS_COMPLETE;
   buyer.RewardQuest(objects.GetQuestTemplate(contract.quest),0,&giver,false,false);
   assert(buyer.HasSpell(root));
   for(auto const& row:trainer._spells){
    uint32 first=row.SpellId;while(auto previous=spellMgr.GetPrevSpellInChain(first))first=previous;
    if(first!=root||row.SpellId==root)continue;
    auto wallet=buyer.money;buyer.level=row.ReqLevel-1;trainer.TeachSpell(&npc,&buyer,row.SpellId);
    assert(!buyer.HasSpell(row.SpellId)&&buyer.money==wallet);buyer.level=row.ReqLevel;
    buyer.money=row.MoneyCost-1;trainer.TeachSpell(&npc,&buyer,row.SpellId);
    assert(!buyer.HasSpell(row.SpellId)&&buyer.money==row.MoneyCost-1);
    buyer.money=row.MoneyCost;trainer.TeachSpell(&npc,&buyer,row.SpellId);
    assert(buyer.HasSpell(row.SpellId)&&buyer.money==0);++purchases;
   }
   buyer.known.clear();hook.OnPlayerLogin(&buyer);assert(buyer.known==std::set<uint32>{root});
   buyer.state=13;auto known=buyer.known;hook.OnPlayerLogin(&buyer);assert(buyer.known==known);
   assert(!HistoricalClassQuests::CanUseSpell(&buyer,root));
  }
 }
 Player leader;leader.state=13;leader.rewarded.insert(5634);leader.known.insert(948081);
 Player follower;follower.level=60;hook.OnPlayerLogin(&follower);assert(follower.known.empty());
 assert(follower.CanTakeQuest(prayer,false));assert(!HistoricalClassQuests::CanUseSpell(&follower,948081));
 follower.inWorld=false;assert(!HistoricalClassQuests::CanUseSpell(&follower,948081));
 assert(!HistoricalClassQuests::CanUseSpell(nullptr,948081));
 struct Paid{uint32 root,races,level;};std::array<Paid,4> paid={{{949317,512,10},{949371,1028,20},{949377,1024,10},{949378,512,20}}};
 uint32 paidCases=0;
 for(auto const& entry:paid)for(uint8 tier=0;tier<=18;++tier)for(uint8 race:{1,2,3,4,5,6,7,8,10,11})for(uint8 cls:{1,5,8}){
  Player buyer;buyer.race=race;buyer.playerClass=cls;buyer.state=tier;buyer.level=entry.level;
  hook.OnPlayerLogin(&buyer);assert(buyer.known.empty());
  bool expected=cls==5&&tier>=8&&tier<13&&(entry.races&(1u<<(race-1)));
  assert(HistoricalClassQuests::CanUseSpell(&buyer,entry.root)==expected);
  auto lesson=trainer.GetSpell(entry.root);assert(lesson&&lesson->MoneyCost>0&&lesson->ReqAbility[0]==0);
  buyer.money=lesson->MoneyCost;trainer.TeachSpell(&npc,&buyer,entry.root);
  assert(buyer.HasSpell(entry.root)==expected&&buyer.money==(expected?0:lesson->MoneyCost));
  if(race==10){assert(!HistoricalClassQuests::CanUseSpell(&buyer,949292));assert(!buyer.CanTakeQuest(objects.GetQuestTemplate(5658),false));}
  ++paidCases;
 }
 Player consumer;consumer.race=10;consumer.state=8;consumer.level=20;
 spell_historical_consume_magic consume;consume.caster=&consumer;consume.Register();
 assert(consume.OnCheckCast.handler()==SPELL_FAILED_NOTHING_TO_DISPEL);
 SpellInfo priestInfo{17,{},SPELLFAMILY_PRIEST},otherInfo{1459,{},3};
 Aura priest{&priestInfo,false},passive{&priestInfo,true},other{&otherInfo,false};
 AuraApplication negative{&priest,false},passiveApplication{&passive,true},otherApplication{&other,true},beneficial{&priest,true};
 consumer.applied={{1,&negative},{2,&passiveApplication},{3,&otherApplication}};
 assert(consume.OnCheckCast.handler()==SPELL_FAILED_NOTHING_TO_DISPEL);
 consumer.applied.emplace(4,&beneficial);assert(consume.OnCheckCast.handler()==SPELL_CAST_OK);
 consume.OnEffectHitTarget.handler(EFFECT_0);assert(consumer.removedAuras==1&&consumer.applied.size()==3&&!consume.preventDefault);
 consumer.applied.emplace(4,&beneficial);assert(consume.OnCheckCast.handler()==SPELL_CAST_OK);
 consumer.applied.erase(4);consume.OnEffectHitTarget.handler(EFFECT_0);assert(consume.preventDefault&&consumer.removedAuras==1);
 consumer.applied.emplace(4,&beneficial);beneficial.removeMode=1;
 assert(consume.OnCheckCast.handler()==SPELL_FAILED_NOTHING_TO_DISPEL);consume.preventDefault=false;
 consume.OnEffectHitTarget.handler(EFFECT_0);assert(consume.preventDefault&&consumer.removedAuras==1);
 beneficial.removeMode=0;priest.removed=true;
 assert(consume.OnCheckCast.handler()==SPELL_FAILED_NOTHING_TO_DISPEL);consume.preventDefault=false;
 consume.OnEffectHitTarget.handler(EFFECT_0);assert(consume.preventDefault&&consumer.removedAuras==1);
 for(int mode=0;mode<4;++mode){progression.enabled=mode!=0;progression.strictEarnedProgression=mode!=1;
 progression.disableDefaultProgression=mode==2;progression.customProgressionMap.clear();if(mode==3)progression.customProgressionMap[0]=1;
 assert(p.CanSeeStartQuest(prayer));assert(!HistoricalClassQuests::CanUseSpell(&p,948081));assert(HistoricalClassQuests::CanUseSpell(&p,19236));}
 std::cout<<"Native historical acquisition: "<<cases<<" era/race/class/reward cases, "<<paidCases<<" TBC paid-racial cases, "<<purchases<<" real paid-rank purchases, native condition routing, exclusive choices, personal markers and reward-spell gates passed\n";
}
'''

quest_functions = '\n'.join(function(quest_source, signature) for signature in (
    'bool Player::CanSeeStartQuest(', 'bool Player::CanTakeQuest(', 'bool Player::CanRewardQuest(Quest const* quest, bool msg)',
    'bool Player::SatisfyQuestPreviousQuest(', 'bool Player::SatisfyQuestExclusiveGroup(',
    'bool Player::SatisfyQuestClass(', 'bool Player::SatisfyQuestRace(', 'bool Player::SatisfyQuestLevel(',
    'bool Player::SatisfyQuestConditions(', 'bool Player::GetQuestRewardStatus('))
assert 'if (!CanTakeQuest(quest, false))' in function(quest_source, 'void Player::PrepareQuestMenu(')
dialog = function(quest_source, 'QuestGiverStatus Player::GetQuestDialogStatus(')
assert dialog.count('GetConditionsForNotGroupedEntry(CONDITION_SOURCE_TYPE_QUEST_AVAILABLE,') == 2
assert dialog.count('if (!sConditionMgr->IsObjectMeetToConditions(this, conditions))') == 2
# Keep the native mark-credit-before-reward-cast block.
# The unrelated inventory/XP/mail middle is an observable storage adapter.
reward = function(quest_source, 'void Player::RewardQuest(')
entry = reward[:reward.index('    //this THING')]
assert 'OnPlayerCanUseQuest' not in entry, 'obsolete core quest hook remains'
tail = reward[reward.index('    RemoveActiveQuest('):reward.index('    if (quest->GetZoneOrSort()')]
quest_functions += '\n' + entry + '    ++sideEffects;\n    uint32 quest_id = quest->GetQuestId();\n    (void)reward; (void)announce; (void)isLFGReward;\n' + tail.replace('    if (announce)\n        SendQuestReward(quest, XP);\n', '') + '\n}\n'
trainer_functions = '\n'.join(function(trainer_source, signature) for signature in (
    'bool Spell::IsCastable()', 'uint32 Trainer::GetSpellCost(', 'void Trainer::TeachSpell(',
    'Spell const* Trainer::GetSpell(', 'bool Trainer::CanTeachSpell(', 'SpellState Trainer::GetSpellState(',
    'SpellState Trainer::GetDefaultSpellState(', 'bool Trainer::IsTrainerValidForPlayer('))

initializers = [f'objects.quests.emplace({marker},Quest{{{marker},60,0,0,0,0,0,0,{{}}}});' for marker in range(66001, 66019)]
for quest_id in quest_ids:
    quest = rows['quest_template'][quest_id]
    addon = rows['quest_template_addon'][quest_id]
    reward_spell, display = db.execute('SELECT RewardSpell,RewardDisplaySpell FROM quest_template WHERE ID=?', (quest_id,)).fetchone()
    previous = str(addon['PrevQuestID']) if addon['PrevQuestID'] else ''
    scalars = [quest_id, quest['MinLevel'], addon['MaxLevel'], quest['AllowableRaces'], addon['AllowableClasses'], reward_spell, display, addon['ExclusiveGroup']]
    initializers.append('objects.quests.emplace(' + str(quest_id) + ',Quest{' + ','.join(map(str, scalars)) + ',{' + previous + '}});')
    if addon['ExclusiveGroup']:
        initializers.append(f'objects.mExclusiveQuestGroups.emplace({addon["ExclusiveGroup"]},{quest_id});')
spell_initializers = []
for era_name in ('vanilla', 'tbc'):
    data = yaml.safe_load((era / f'era-data/{era_name}/priest.yaml').read_text())
    for helper in data.get('helpers', []):
        effects = ','.join('{' + str(e.get('effect', 0)) + ',' + str(e.get('trigger', 0)) + '}' for e in helper.get('effects', []))
        spell_initializers.append(f'spellMgr.spells.emplace({helper["id"]},SpellInfo{{{helper["id"]},{{{effects}}}}});')
for spell in (19236, 6346, 2060):
    spell_initializers.append(f'spellMgr.spells.emplace({spell},SpellInfo{{{spell},{{}}}});')
trainer_initializers = []
for row in db.execute('SELECT * FROM trainer_spell WHERE TrainerId=11 AND SpellId>=948081 ORDER BY SpellId'):
    trainer_initializers.append('trainer._spells.push_back(Trainer::Spell{' + ','.join(map(str, row[1:5])) + ',{' + ','.join(map(str, row[5:8])) + '},' + str(row[8]) + '});')
for row in db.execute('SELECT spell_id,rank FROM spell_ranks WHERE first_spell_id>=948081 ORDER BY first_spell_id,rank'):
    if row[1] > 1:
        spell_initializers.append(f'spellMgr.previous.emplace({row[0]},{row[0]-1});')
fixture = FIXTURE.replace('PROGRESSION_ENUM', progress_enum).replace('PRODUCTION_PROGRESS', '\n'.join(function(progress_source, signature) for signature in ('bool IndividualProgression::IsStrictDefaultProgression()', 'uint8 IndividualProgression::GetPlayerProgressionFromQuests(', 'uint8 IndividualProgression_GetEarnedEra(')))
fixture = fixture.replace('PRODUCTION_HISTORICAL', re.sub(r'^#include[^\n]*\n', '', historical, flags=re.MULTILINE))
# Compile the native marker/race decisions, negation and OR-group evaluator.
# Other Condition::Meets cases concern unrelated object/spell/world adapters.
meets = function(condition_source, 'bool Condition::Meets(')
rewarded_case = meets[meets.index('    case CONDITION_QUESTREWARDED:'):meets.index('    case CONDITION_QUESTTAKEN:')]
assert 'ConditionValue2' not in rewarded_case, 'rewarded-quest discriminator now changes evaluation'
validation = function(condition_source, 'bool ConditionMgr::isConditionTypeValid(')
quest_validation = validation[validation.index('    case CONDITION_QUESTREWARDED:'):validation.index('    case CONDITION_QUESTSTATE:')]
assert 'if (cond->ConditionValue2 > 1)' in quest_validation, 'rewarded-quest discriminator no longer accepted'
race_case = meets[meets.index('    case CONDITION_RACE:'):meets.index('    case CONDITION_GENDER:')]
condition_functions = 'bool Condition::Meets(ConditionSourceInfo& sourceInfo) {\nWorldObject* object=sourceInfo.mConditionTargets[0];if(!object)return false;bool condMeets=false;switch(ConditionType){\n' + rewarded_case + race_case + 'default:break; }\n' + meets[meets.index('    if (NegativeCondition)'):]
condition_functions += '\n'.join(function(condition_source, signature) for signature in (
    'ConditionList ConditionMgr::GetConditionsForNotGroupedEntry(',
    'bool ConditionMgr::IsObjectMeetToConditionList(',
    'bool ConditionMgr::IsObjectMeetToConditions(WorldObject* object,',
    'bool ConditionMgr::IsObjectMeetToConditions(ConditionSourceInfo&'))
fixture = fixture.replace('CONDITION_ENUMS', function(condition_header, 'enum ConditionTypes') + ';\n' + function(condition_header, 'enum ConditionSourceType') + ';')
fixture = fixture.replace('PRODUCTION_CONDITIONS', condition_functions)
condition_initializers = []
for index, row in enumerate(db.execute('SELECT SourceEntry,ElseGroup,ConditionTypeOrReference,ConditionValue1,NegativeCondition FROM conditions WHERE SourceTypeOrReferenceId=19 AND SourceEntry IN (' + ','.join(map(str, quest_ids)) + ')')):
    quest, group, kind, value, negative = row
    assert kind in (8, 16), row
    condition_initializers.append(f'Condition condition{index}{{{kind},{value},{negative},{group},0}};conditions.ConditionStore[CONDITION_SOURCE_TYPE_QUEST_AVAILABLE][{quest}].push_back(&condition{index});')
fixture = fixture.replace('CONDITION_ROWS', '\n'.join(condition_initializers))
fixture = fixture.replace('PRODUCTION_HOOK_ENUM', function(core_file('src/server/game/Scripting/ScriptDefines/PlayerScript.h').read_text(), 'enum PlayerHook') + ';')
fixture = fixture.replace('PRODUCTION_QUESTS', quest_functions).replace('PRODUCTION_TRAINER', 'namespace Trainer {\n' + trainer_functions + '\n}')
fixture = fixture.replace('QUEST_ROWS', '\n'.join(initializers)).replace('SPELL_ROWS', '\n'.join(spell_initializers)).replace('TRAINER_ROWS', '\n'.join(trainer_initializers))
fixture = fixture.replace('FAMILY_CONTRACTS', ','.join('{' + ','.join(map(str, (quest, *family[1:5]))) + '}' for family in families for quest in family[0]))
learn = function(core_file('src/server/game/Entities/Player/Player.cpp').read_text(), 'void Player::learnSpell(uint32 spellId,')
fixture = fixture.replace('PRODUCTION_LEARN_GATE', learn[:learn.index('    // Xinef:')] + '    (void)temporary; (void)learnFromSkill;\n    known.insert(spellId);\n}\n')

with tempfile.TemporaryDirectory(prefix='historical-class-quests-') as directory:
    temporary = Path(directory)
    compile_run(temporary, 'native', fixture)
    removed = fixture.replace('           && SatisfyQuestConditions(quest, msg)', '')
    assert removed != fixture
    compile_run(temporary, 'missing-native-condition-route', removed, expected=False)
    removed = fixture.replace('condMeets = player->GetQuestRewardStatus(ConditionValue1);', 'condMeets = player && false;')
    assert removed != fixture
    compile_run(temporary, 'missing-personal-marker-gate', removed, expected=False)
    removed = fixture.replace('condMeets = unit->getRaceMask() & ConditionValue1;', 'condMeets = unit != nullptr;')
    assert removed != fixture
    compile_run(temporary, 'missing-vanilla-fear-ward-race-gate', removed, expected=False)
print('Native availability route, personal-marker and historical-race mutations were rejected')


def load_python(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(era / 'tools'))
generator = load_python('historical_generator', era / 'tools/gen_era_talents.py')
client = load_python('historical_client', era / 'tools/build_client_dbc.py')
indices = {name: index for index, name in enumerate(generator.COLS)}
types = generator.COLTYPES
lock = json.loads((repository / 'versions.lock.json').read_text())
restoration = yaml.safe_load((era / 'era-data/vanilla/priest.yaml').read_text())['clientNativeSpellRestoration']
assert restoration['source'] == 'pinned-wrath-english'
assert restoration['sourceSha256'] == lock['clientPatch']['localizations']['deDE']['englishSpellSha256']
assert restoration['fields'] == ['ManaCost', 'ManaCostPct']
assert set(restoration['spellIds']) == {19236, 19238, 19240, 19241, 19242, 19243,
                                       2944, 19276, 19277, 19278, 19279, 19280}
assert len(restoration['spellIds']) == 12
datasets, helpers, dataset_paths, template_ids = [], {}, [], set()
for era_name in ('vanilla', 'tbc'):
    path = era / f'era-data/{era_name}/priest.yaml'
    data = yaml.safe_load(path.read_text())
    dataset_paths.append(str(path))
    template_ids.update(h['template'] for h in data.get('helpers', []) if 'template' in h)
    baseline = pinned_source('mod-era-talents', 'era-data/' + era_name + '/priest.yaml')
    old_ids = {h['id'] for h in yaml.safe_load(baseline).get('helpers', [])}
    new_helpers = [h for h in data.get('helpers', []) if h['id'] not in old_ids]
    datasets.append({**data, 'helpers': new_helpers, 'tabs': [], 'scriptBindings': []})
    helpers.update({h['id']: h for h in new_helpers})
assert set(range(948081, 948088)) | {948089, 948090, 948091} <= set(helpers)


def decoded_dbc(data):
    rows, strings = wdbc(data, 234)
    records = {}
    for raw in rows:
        typed = []
        for index, field_type in enumerate(types):
            value = struct.unpack_from('<f' if field_type == 'float' else '<i' if field_type == 'signed' else '<I', raw, index * 4)[0]
            if field_type == 'string':
                end = strings.index(b'\0', value)
                value = strings[value:end].decode('utf-8')
            typed.append(value)
        records[typed[0]] = (typed, raw)
    return records


def verify_historical_contracts(records):
    # Classic DB ec4f596146... rank magnitudes and growth windows, independent
    # of the YAML/generator being tested. BasePoints are client zero-based.
    amounts = (133, 262, 446, 587, 833, 1100, 1323)
    dice = (37, 63, 97, 121, 161, 205, 239)
    growth = (2.4, 3.4, 4.5, 5.3, 6.4, 7.4, 8.2)
    for rank in range(7):
        row = records[948081 + rank][0]
        exact = {'Category': 671, 'RecoveryTime': 0, 'CategoryRecoveryTime': 600000,
                 'ManaCost': 0, 'ManaCostPct': 0, 'SpellLevel': 10 + rank * 8,
                 'BaseLevel': 10 + rank * 8, 'MaxLevel': 16 + rank * 8,
                 'Effect_1': 10, 'ImplicitTargetA_1': 1,
                 'EffectBasePoints_1': amounts[rank], 'EffectDieSides_1': dice[rank]}
        for field, value in exact.items():
            assert row[indices[field]] == value, (948081 + rank, field, row[indices[field]], value)
        assert abs(row[indices['EffectRealPointsPerLevel_1']] - growth[rank]) < 1e-5
        # The 3.3.5 client reads locale slot 3. The SQL column labels include
        # an enGB alias and are not the client locale-index contract.
        assert row[indices['Name_Lang_enUS'] + 3] == 'Verzweifeltes Gebet', (948081 + rank, row[indices['Name_Lang_enUS'] + 3])
        assert row[indices['NameSubtext_Lang_enUS'] + 3] == f'Rang {rank + 1}'
        assert row[indices['Description_Lang_enUS'] + 3]
    ward = records[948089][0]
    for field, value in {'RecoveryTime': 30000, 'DurationIndex': 6, 'ManaCost': 100,
                         'ManaCostPct': 0, 'ProcCharges': 1, 'Effect_1': 6,
                         'EffectAura_1': 77, 'EffectMiscValue_1': 5, 'ImplicitTargetA_1': 21}.items():
        assert ward[indices[field]] == value, (948089, field)
    assert ward[indices['Name_Lang_enUS'] + 3] == 'Furchtzauberschutz'
    assert ward[indices['Description_Lang_enUS'] + 3] and ward[indices['AuraDescription_Lang_enUS'] + 3]
    contracts = {
        949100: {'ManaCost': 50, 'DurationIndex': 32, 'SchoolMask': 64, 'EffectAura_1': 3, 'EffectAuraPeriod_1': 1000, 'EffectBasePoints_1': 13},
        949107: {'ManaCost': 60, 'DurationIndex': 8, 'CategoryRecoveryTime': 300000, 'EffectAura_1': 113, 'EffectAura_2': 49},
        949112: {'ManaCost': 25, 'ProcTypeMask': 40, 'ProcCharges': 1, 'EffectAura_1': 42, 'EffectTriggerSpell_1': 949118},
        949124: {'ManaCost': 35, 'DurationIndex': 4, 'EffectAura_1': 13, 'EffectAura_2': 118, 'EffectBasePoints_2': -21},
        949130: {'ManaCost': 50, 'ProcTypeMask': 139944, 'ProcCharges': 3, 'EffectTriggerSpell_1': 949136},
        949142: {'ManaCost': 140, 'CategoryRecoveryTime': 180000, 'ProcTypeMask': 131072, 'EffectTriggerSpell_1': 949147},
        949147: {'ManaCost': 0, 'Effect_1': 62, 'EffectBasePoints_1': 17, 'EffectMultipleValue_1': 1},
        949152: {'ManaCost': 215, 'CategoryRecoveryTime': 180000, 'DurationIndex': 106, 'EffectAura_1': 53, 'EffectAuraPeriod_1': 3000, 'EffectMultipleValue_1': 1},
    }
    for spell_id, fields in contracts.items():
        for field, value in fields.items():
            assert records[spell_id][0][indices[field]] == value, (spell_id, field)


MECHANIC_FIXTURE = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <vector>
using uint8=std::uint8_t;using uint32=std::uint32_t;using int8=std::int8_t;using int32=std::int32_t;
using SpellEffIndex=uint32;using Powers=int32;
constexpr int32 MAX_POWERS=7,POWER_MANA=0,SPELL_EFFECT_HANDLE_HIT_TARGET=1,SPELLMOD_VALUE_MULTIPLIER=27,
 SPELL_AURA_MOD_FEAR=7,BASE_ATTACK=0,MELEE_HIT_NORMAL=0,DOT=0,CR_CRIT_TAKEN_SPELL=0,
 SPELL_EFFECT_PERSISTENT_AREA_AURA=27,SPELL_MISS_NONE=0,DYNOBJ_AURA_TYPE=1,CLASS_PALADIN=2;
constexpr uint32 PROC_FLAG_DONE_PERIODIC=1,PROC_FLAG_TAKEN_PERIODIC=2,PROC_EX_INTERNAL_DOT=4,
 PROC_EX_CRITICAL_HIT=8,PROC_EX_NORMAL_HIT=16,PROC_EX_ABSORB=32,PROC_FLAG_TAKEN_DAMAGE=64;
struct Player;struct Spell;struct WorldObject {Player* GetSpellModOwner()const{return nullptr;}};
struct SpellInfo;
struct SpellEffectInfo {float ValueMultiplier=1;int32 MiscValue=0;uint32 Effect=6;SpellInfo const* _spellInfo=nullptr;
 float CalcValueMultiplier(WorldObject*,Spell* =nullptr)const;};
struct SpellInfo {uint32 Id=0;std::array<SpellEffectInfo,3> Effects;uint32 GetSchoolMask()const{return 32;}};
struct CleanDamage {uint32 mitigated_damage=0;CleanDamage(uint32,uint32,int32,int32){}};
struct DamageInfo {uint32 damage=0,absorb=0,resist=0;DamageInfo(struct Unit*,struct Unit*,uint32 d,SpellInfo const*,uint32,int32,uint32):damage(d){}
 uint32 GetDamage()const{return damage;}uint32 GetAbsorb()const{return absorb;}uint32 GetResist()const{return resist;}
 void ModifyDamage(uint32 reduction){damage-=std::min(reduction,damage);}};
struct HealInfo {struct Unit* recipient;uint32 amount;HealInfo(struct Unit*,struct Unit* r,uint32 a,SpellInfo const*,uint32):recipient(r),amount(a){}};
struct Unit:WorldObject {bool alive=true,immune=false;uint32 health=100,maxHealth=100,absorb=0;int32 mana=100,resilience=0;
 bool IsAlive()const{return alive&&health>0;}bool HasActivePowerType(Powers p)const{return p==POWER_MANA;}
 int32 ModifyPower(Powers,int32 amount){auto before=mana;mana=std::max(0,mana+amount);return mana-before;}
 uint32 GetMaxPower(Powers)const{return 100;}int32 GetSpellCritDamageReduction(int32)const{return resilience;}
 void RemoveAurasByType(int32){}bool IsImmunedToDamage(Unit*,SpellInfo const*)const{return immune;}
 int32 SpellHitResult(Unit*,SpellInfo const*,bool)const{return SPELL_MISS_NONE;}
 struct AI {void OnCalculatePeriodicTickReceived(uint32&,Unit*){}};AI* GetAI()const{return nullptr;}
 uint32 SpellDamageBonusDone(Unit*,SpellInfo const*,uint32 d,int32,uint32,float,uint32)const{return d;}
 uint32 SpellDamageBonusTaken(Unit*,SpellInfo const*,uint32 d,int32,uint32)const{return d;}
 static uint32 SpellCriticalDamageBonus(Unit*,SpellInfo const*,uint32 d,Unit*){return d;}
 static bool IsDamageReducedByArmor(uint32,SpellInfo const*,uint32){return false;}
 static uint32 CalcArmorReducedDamage(Unit*,Unit*,uint32 d,SpellInfo const*,uint32){return d;}
 static void ApplyResilience(Unit*,void*,int32*,bool,int32){}
 static void CalcAbsorbResist(DamageInfo& d,bool,uint32){(void)d;}
 uint32 GetHealth()const{return health;}uint32 GetGUID()const{return 0;}
 void SendSpellNonMeleeDamageLog(Unit*,SpellInfo const*,uint32,uint32,uint32,uint32,bool,int32,bool){}
 static int32 DealDamage(Unit*,Unit* target,uint32 d,CleanDamage*,int32,uint32,SpellInfo const*,bool){auto actual=std::min(d,target->health);target->health-=actual;return int32(actual);}
 static void ProcSkillsAndAuras(Unit*,Unit*,uint32,uint32,uint32,uint32,int32,SpellInfo const*,void*,uint32,void*,DamageInfo*){}
 uint32 SpellHealingBonusDone(Unit*,SpellInfo const*,uint32 h,int32,uint32,float,uint32)const{return h;}
 uint32 SpellHealingBonusTaken(Unit*,SpellInfo const*,uint32 h,int32,uint32)const{return h;}
 uint32 HealBySpell(HealInfo const& h){auto actual=std::min(h.amount,maxHealth-health);health+=actual;return actual;}
 bool IsClass(int32)const{return false;}struct Threat {void ForwardThreatForAssistingMe(Unit*,float,SpellInfo const*){}} threat;
 Threat& GetThreatMgr(){return threat;}
};
struct Player:Unit {void ApplySpellMod(uint32,int32,float&,Spell*){}};
struct ScriptMgr {void ModifyPeriodicDamageAurasTick(Unit*,Unit*,uint32&,SpellInfo const*){}} scripts;auto* sScriptMgr=&scripts;
bool roll_chance_f(float){return false;}template<class T>int32 CalculatePct(T value,int32 p){return int32(value*p/100);}
#define LOG_DEBUG(...) ((void)0)
struct Spell {Unit* unitTarget=nullptr;Unit* caster=nullptr;WorldObject* m_originalCaster=nullptr;SpellInfo const* m_spellInfo=nullptr;
 int32 effectHandleMode=SPELL_EFFECT_HANDLE_HIT_TARGET,damage=0,m_damage=0;uint32 logged=0;
 Unit* GetUnitCasterForEffectHandlers()const{return caster;}
 void ExecuteLogEffectTakeTargetPower(uint32,Unit*,Powers,int32 amount,float){logged=uint32(amount);}
 void EffectPowerBurn(SpellEffIndex);};
struct AuraEffect {SpellInfo const* m_spellInfo;uint32 m_effIndex=0;int32 amount=0;
 SpellInfo const* GetSpellInfo()const{return m_spellInfo;}uint32 GetEffIndex()const{return m_effIndex;}
 int32 GetAmount()const{return amount;}float GetCritChance()const{return 0;}bool CanApplyResilience()const{return false;}
 uint32 GetCasterLevel()const{return 60;}uint32 GetCasterGUID()const{return 0;}uint32 GetId()const{return m_spellInfo->Id;}
 void SendTickImmune(Unit*,Unit*)const{}
 struct Base {int32 GetType()const{return 0;}uint32 GetStackAmount()const{return 1;}} base;
 Base const* GetBase()const{return &base;}void HandlePeriodicHealthLeechAuraTick(Unit*,Unit*)const;};
NATIVE_MULTIPLIER
NATIVE_BURN
NATIVE_LEECH
int main(){
 struct Row{uint32 id;bool burn;int32 amount;float multiplier;};std::vector<Row> rows={MECHANIC_ROWS};
 for(auto const& row:rows){
  SpellInfo info;info.Id=row.id;info.Effects[0].ValueMultiplier=row.multiplier;info.Effects[0]._spellInfo=&info;
  Unit caster,target;caster.health=1000;caster.maxHealth=20000;target.health=20000;target.maxHealth=20000;target.mana=20000;
  if(row.burn){Spell spell;spell.unitTarget=&target;spell.caster=&caster;spell.m_originalCaster=&caster;spell.m_spellInfo=&info;spell.damage=row.amount;
   spell.EffectPowerBurn(0);assert(target.mana==20000-row.amount&&spell.m_damage==row.amount&&spell.logged==uint32(row.amount));
   target.mana=3;spell.m_damage=0;spell.EffectPowerBurn(0);assert(target.mana==0&&spell.m_damage==3);
   target.mana=100;target.alive=false;spell.m_damage=0;spell.EffectPowerBurn(0);assert(target.mana==100&&spell.m_damage==0);
  }else{AuraEffect effect{&info,0,row.amount,{}};effect.HandlePeriodicHealthLeechAuraTick(&target,&caster);
   assert(target.health==20000-uint32(row.amount)&&caster.health==1000+uint32(row.amount));
   target.health=3;caster.health=1000;effect.HandlePeriodicHealthLeechAuraTick(&target,&caster);assert(target.health==0&&caster.health==1003);
   target.health=100;target.immune=true;caster.health=50;effect.HandlePeriodicHealthLeechAuraTick(&target,&caster);assert(target.health==100&&caster.health==50);
  }
 }
 std::cout<<"Native Feedback power-burn and Devouring Plague health-leech: "<<rows.size()<<" generated historical ranks, bounded resources, immunity and dead target passed\n";
}
'''


with tempfile.TemporaryDirectory(prefix='historical-class-spells-') as directory:
    temporary = Path(directory)
    base = args.base_dbc
    if base:
        donor = lock['clientPatch']['localizations']['deDE']
        assert hashlib.sha256(base.read_bytes()).hexdigest() == donor['englishSpellSha256']
    else:
        # Deliberately nonzero template metadata proves the builder overrides
        # old mechanics while preserving every unrelated native record byte.
        pool = client.StringPool(b'\0')
        records = []
        for spell_id in sorted(template_ids | {19236, 6346, 48173}):
            row = generator._row_values({'ID': spell_id, 'Name_Lang_enUS': 'Native Wrath spell',
                                        'Name_Lang_deDE': 'Originaler Wrath-Zauber',
                                        'RecoveryTime': 98765, 'ManaCost': 543, 'DurationIndex': 99})
            records.append(client._encode_record(row, pool))
        strings = b'\0' + pool.appended()
        base = temporary / 'base.dbc'
        base.write_bytes(make_wdbc(records, strings))
    output = temporary / 'Spell.dbc'
    client.build(dataset_paths, base, output)
    emitted = decoded_dbc(output.read_bytes())
    native = decoded_dbc(base.read_bytes())
    for spell_id, (_, record) in native.items():
        assert emitted[spell_id][1] == record, ('native record changed', spell_id)
    verify_historical_contracts(emitted)
    spell_db = sqlite3.connect(':memory:')
    spell_db.execute('CREATE TABLE spell_dbc (' + ','.join('"' + c + '"' for c in generator.COLS) + ')')
    for table in ('spell_proc', 'spell_script_names'):
        dump(spell_db, world if world.exists() else fallback / 'data/sql/base/db_world', table)
    for data in datasets:
        spell_db.executescript(generator.emit_custom_sql(data, base))
    for spell_id in helpers:
        server = spell_db.execute('SELECT * FROM spell_dbc WHERE ID=?', (spell_id,)).fetchone()
        assert server is not None, spell_id
        for index, field_type in enumerate(types):
            if field_type == 'string' or generator.COLS[index] in ('SpellIconID', 'Name_Lang_Mask',
                    'NameSubtext_Lang_Mask', 'Description_Lang_Mask', 'AuraDescription_Lang_Mask'):
                continue
            actual = emitted[spell_id][0][index]
            if field_type == 'float':
                assert abs(actual - server[index]) <= max(1e-5, abs(actual) * 1e-6), (spell_id, generator.COLS[index])
            else:
                assert actual == server[index], (spell_id, generator.COLS[index], actual, server[index])
    print('Historical spell generation: independent Classic rank/cooldown/mana/ward contracts, DE text, server/client numeric parity and unchanged native Wrath records passed')
    mechanics = []
    for spell_id in helpers:
        row = emitted[spell_id][0]
        if row[indices['Effect_1']] == 62 or row[indices['EffectAura_1']] == 53:
            mechanics.append('{' + ','.join((str(spell_id), 'true' if row[indices['Effect_1']] == 62 else 'false',
                                           str(row[indices['EffectBasePoints_1']] + row[indices['EffectDieSides_1']]),
                                           str(row[indices['EffectMultipleValue_1']]) + 'f')) + '}')
    mechanic = MECHANIC_FIXTURE.replace('MECHANIC_ROWS', ','.join(mechanics))
    mechanic = mechanic.replace('NATIVE_MULTIPLIER', function(core_file('src/server/game/Spells/SpellInfo.cpp').read_text(), 'float SpellEffectInfo::CalcValueMultiplier('))
    mechanic = mechanic.replace('NATIVE_BURN', function(core_file('src/server/game/Spells/SpellEffects.cpp').read_text(), 'void Spell::EffectPowerBurn('))
    mechanic = mechanic.replace('NATIVE_LEECH', function(core_file('src/server/game/Spells/Auras/SpellAuraEffects.cpp').read_text(), 'void AuraEffect::HandlePeriodicHealthLeechAuraTick('))
    compile_run(temporary, 'spell-mechanics', mechanic)
    compile_run(temporary, 'zero-feedback-leech-multiplier', mechanic.replace('float multiplier = ValueMultiplier;', 'float multiplier = 0.0f;'), expected=False)

    if args.era_client:
        assert args.base_dbc, '--era-client also requires the pinned --base-dbc'
        package = load_python('historical_package', repository / 'cmake/PackageEraClient.py')
        files, manifest = package.verify_zip(args.era_client, lock)
        reader = args.mpq_reader
        if reader is None:
            storm = temporary / 'StormLib'
            package.export_module(repository, {**lock['clientPatch']['stormLib'], 'name': 'StormLib',
                                                'source': '.module-cache/client-tools-stormlib'}, storm, 'git')
            build = temporary / 'build'
            subprocess.run(['cmake', '-S', str(repository / 'cmake/era-client-tools'), '-B', str(build),
                            '-DSTORM_SOURCE_DIR=' + str(storm), '-DERA_SOURCE_DIR=' + str(era),
                            '-DCMAKE_BUILD_TYPE=Release'], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(['cmake', '--build', str(build), '--target', 'mpqread', '--parallel', '4'],
                           check=True, stdout=subprocess.DEVNULL)
            reader = build / 'mpqread'
        archive = temporary / 'patch-V.mpq'
        archive.write_bytes(files['Data/patch-V.mpq'])
        actual = package.read_mpq(reader.resolve(), archive, 'DBFilesClient\\Spell.dbc', temporary / 'delivered.dbc')
        assert hashlib.sha256(actual).hexdigest() == manifest['mergedDbcSha256']['DBFilesClient\\Spell.dbc']
        delivered = decoded_dbc(actual)
        verify_historical_contracts(delivered)
        for spell_id in helpers:
            for index, field_type in enumerate(types):
                if field_type != 'string':
                    assert delivered[spell_id][0][index] == emitted[spell_id][0][index], (spell_id, generator.COLS[index])
        for spell_id in (19236, 19238, 19240, 19241, 19242, 19243, 25437, 48172, 48173, 6346,
                         2944, 19276, 19277, 19278, 19279, 19280, 25467, 48299, 48300):
            for index, field_type in enumerate(types):
                if field_type != 'string':
                    assert delivered[spell_id][0][index] == native[spell_id][0][index], ('native Wrath mechanics changed', spell_id, generator.COLS[index])
        print('Delivered EraTalents MPQ: historical server/client mechanics and DE text verified; native Wrath prayer/fear-ward/plague mechanics unchanged')
    elif args.mpq_reader:
        parser.error('--mpq-reader requires --era-client')
