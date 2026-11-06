"""Check AV mining access and Windsor's own summon phase with native handlers."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import struct
import subprocess
import tempfile
import urllib.request

from FixtureSupport import (
    SANITIZER_FLAGS,
    TIMEOUT,
    cxx,
    function,
    prepared_core,
    reject_mutants,
    run_fixture,
    source_argument,
    sql_rows,
    wdbc,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help='Individual Progression module directory')
core = prepared_core()
module = parser.parse_args().source or core / 'modules/mod-individual-progression'
repository = Path(__file__).resolve().parents[2]
sql = (module / 'data/sql/world/base/av_gameobjects.sql').read_text()
update = re.search(r'UPDATE `gameobject_template_addon` SET `faction`[^;]+;', sql)[0]
entries = {175404, 176643, 176645}
native = (core / 'data/sql/base/db_world/gameobject_template_addon.sql').read_text()
columns = re.findall(r'^  `([^`]+)`', native.split('CREATE TABLE `gameobject_template_addon` (')[1].split(') ENGINE')[0],
                     re.MULTILINE)
other = int(re.search(r'^\((\d+),', native, re.MULTILINE)[1])
assert other not in entries
rows = sql_rows(core, 'gameobject_template_addon', entries | {other})
with sqlite3.connect(':memory:') as db:
    db.execute('CREATE TABLE gameobject_template_addon (' + ','.join('`' + column + '` NUMERIC' for column in columns) + ')')
    db.executemany('INSERT INTO gameobject_template_addon VALUES (' + ','.join('?' for _ in columns) + ')',
                   [tuple(row[column] for column in columns) for row in rows])
    before = db.execute('SELECT * FROM gameobject_template_addon ORDER BY entry').fetchall()
    db.executescript(update)
    after = db.execute('SELECT * FROM gameobject_template_addon ORDER BY entry').fetchall()
    db.executescript(update)
    assert db.execute('SELECT * FROM gameobject_template_addon ORDER BY entry').fetchall() == after
    for original, changed in zip(before, after, strict=True):
        expected = list(original)
        if original[0] in entries:
            assert original[columns.index('faction')] == 94
            expected[columns.index('faction')] = 0
        assert changed == tuple(expected)
    factions = [db.execute('SELECT faction FROM gameobject_template_addon WHERE entry=?', (entry,)).fetchone()[0]
                for entry in sorted(entries)]

# These immutable client records supply the real faction and mining lock data.
locale = json.loads((repository / 'versions.lock.json').read_text())['clientPatch']['localizations']['deDE']
base = locale['url'].removesuffix('.git').replace('github.com/', 'raw.githubusercontent.com/')
base += '/' + locale['revision'] + '/' + locale['sourcePath']
records = {}
for filename, fields, digest in (
    ('FactionTemplate.dbc', 14, '0e5aae3ec23aea267afcff265386c78719c17ada1cc443d010372fb0e3e63f8a'),
    ('Lock.dbc', 33, 'c49bd7ed970583a3660d5d16d6917e91e46aafc9e9ed7926281f4889d45904d0'),
):
    cache = repository / '.module-cache/fixtures' / filename
    if not cache.exists():
        with urllib.request.urlopen(base + '/' + filename, timeout=TIMEOUT) as response:
            data = response.read()
        assert hashlib.sha256(data).hexdigest() == digest
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
    data = cache.read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest
    values, _ = wdbc(data, fields)
    records[filename] = {struct.unpack_from('<I', row)[0]: struct.unpack('<' + str(fields) + 'I', row) for row in values}
assert 0 not in records['FactionTemplate.dbc']
templates = {int(row['entry']): row for row in sql_rows(core, 'gameobject_template', entries)}
locks = []
for entry in sorted(entries):
    assert int(templates[entry]['type']) == 3
    lock = records['Lock.dbc'][int(templates[entry]['Data0'])]
    assert lock[1:9] == (2, 0, 0, 0, 0, 0, 0, 0) and lock[9] == 3
    locks.append(lock)

source = (module / 'src/vanillaScripts/quest_the_masquerade.cpp').read_text()
rowe = function(source, 'struct npc_squire_roweAI')
windsor = function(source, 'struct npc_reginald_windsorAI')
movement = function(rowe, 'void MovementInform(').replace(' override', '')
visible = function(windsor, 'bool CanBeSeen(').replace(' override', '')
accept = function(source[source.index('class npc_reginald_windsor :'):], 'bool OnQuestAccept(').replace(' override', '')
object_header = (core / 'src/server/game/Entities/Object/Object.h').read_text()
object_source = (core / 'src/server/game/Entities/Object/Object.cpp').read_text()
assert 'm_useCombinedPhases(true)' in object_source
summon = function(object_source, 'TempSummon* Map::SummonCreature(')
assert 'phase = summoner->GetPhaseMask();' in summon
phase_sql = (module / 'data/sql/world/base/zz_ipp_aware_npcs.sql').read_text()
phase = re.search(r'SET @IPPPHASE_II\s*:=\s*(\d+);', phase_sql)[1]
assert 'SET `phaseMask` = @IPPPHASE_II  WHERE `id` = 1749;' in phase_sql
dbc = (core / 'src/server/shared/DataStores/DBCStructure.h').read_text()
shared = (core / 'src/server/shared/SharedDefines.h').read_text()
assert re.search(r'#define MAX_FACTION_RELATIONS\s+4\b', dbc)
assert re.search(r'#define MAX_LOCK_CASE\s+8\b', dbc)
quests = (core / 'src/server/game/Quests/QuestDef.h').read_text()
assert re.search(r'QUEST_STATUS_COMPLETE\s*=\s*1\b', quests)
assert re.search(r'QUEST_STATUS_INCOMPLETE\s*=\s*3\b', quests)
faction = dbc[dbc.index('struct FactionTemplateEntry'):dbc.index('    // helpers', dbc.index('struct FactionTemplateEntry'))]
faction += function(dbc, '[[nodiscard]] bool IsFriendlyTo(FactionTemplateEntry const& entry) const') + '\n};'
player = (core / 'src/server/game/Entities/Player/Player.cpp').read_text()
spell = (core / 'src/server/game/Spells/Spell.cpp').read_text()
check = function(spell, 'SpellCastResult Spell::CheckCast(')
assert check.index('!unitCaster->ToPlayer()->CanUseBattlegroundObject(m_targets.GetGOTarget())') < check.index('CanOpenLock(i, lockId, skillId, reqSkillValue, skillValue)')
assert 'sLockStore.LookupEntry(lockId)' in function(spell, 'SpellCastResult Spell::CanOpenLock(')

fixture = r'''
#include <array>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <map>
#include <utility>
#include <vector>
using uint32 = std::uint32_t; using int32 = std::int32_t; using ObjectGuid = std::uint64_t;
using namespace std::chrono_literals;
constexpr int MAX_FACTION_RELATIONS = 4, MAX_LOCK_CASE = 8;
constexpr uint32 GAMEOBJECT_FACTION = 1, SPELL_RECENTLY_DROPPED_FLAG = 2;
constexpr uint32 POINT_MOTION_TYPE = 3, EMOTE_ONESHOT_KNEEL = 4, UNIT_NPC_FLAGS = 5;
constexpr uint32 UNIT_NPC_FLAG_GOSSIP = 1, UNIT_NPC_FLAG_QUESTGIVER = 2;
constexpr uint32 TEMPSUMMON_MANUAL_DESPAWN = 8, QUEST_STATUS_COMPLETE = 1, QUEST_STATUS_INCOMPLETE = 3;
constexpr uint32 LOCK_KEY_ITEM = 1, LOCK_KEY_SKILL = 2, LOCK_KEY_SPELL = 3, TARGET_GAMEOBJECT_ITEM_TARGET = 26;
enum SpellCastResult { SPELL_CAST_OK, SPELL_FAILED_BAD_TARGETS, SPELL_FAILED_LOW_CASTLEVEL };
@PHASES@
@QUEST_ENUM@
@SKILLS@
@LOCK_TYPES@
@SKILL_BY_LOCK@
@FACTION@
@LOCK_ENTRY@;
template<class Record> struct Store
{
    std::map<uint32, Record> rows;
    Record const* LookupEntry(uint32 id) const
    { auto found = rows.find(id); return found == rows.end() ? nullptr : &found->second; }
};
Store<FactionTemplateEntry> sFactionTemplateStore;
Store<LockEntry> sLockStore;
struct WorldObject
{
    uint32 m_phaseMask = PHASEMASK_NORMAL;
    bool m_useCombinedPhases = true;
    uint32 GetPhaseMask() const { return m_phaseMask; }
    @SAME_PHASE@
};
struct Player;
struct Unit : WorldObject
{
    Unit* ToUnit() { return this; }
    bool IsPlayer() const { return true; }
    Player* ToPlayer();
};
struct GameObject
{
    uint32 faction;
    uint32 GetUInt32Value(uint32 key) const { assert(key == GAMEOBJECT_FACTION); return faction; }
};
struct Player : Unit
{
    uint32 faction = 1, skill = 0;
    bool alive = true, immune = false, flag = false;
    std::map<uint32, uint32> quests;
    bool isTotalImmune() const { return immune; }
    bool HasAura(uint32 id) const { assert(id == SPELL_RECENTLY_DROPPED_FLAG); return flag; }
    bool IsAlive() const { return alive; }
    FactionTemplateEntry const* GetFactionTemplateEntry() const { return sFactionTemplateStore.LookupEntry(faction); }
    bool CanUseBattlegroundObject(GameObject*) const;
    uint32 GetSkillValue(SkillType type) const { assert(type == SKILL_MINING); return skill; }
    uint32 GetQuestStatus(uint32 id) const { auto found = quests.find(id); return found == quests.end() ? 0 : found->second; }
    ObjectGuid GetGUID() const { return 77; }
};
Player* Unit::ToPlayer() { return static_cast<Player*>(this); }
@BG_USE@
struct Item { uint32 GetEntry() const { return 0; } };
struct Target { uint32 GetTarget() const { return TARGET_GAMEOBJECT_ITEM_TARGET; } };
struct Effect
{
    int32 MiscValue = LOCKTYPE_MINING;
    Target TargetA, TargetB;
    int32 CalcValue() const { return 0; }
};
struct SpellInfo
{
    uint32 Id = 2576;
    Effect Effects[1];
    bool IsAbilityOfSkillType(SkillType) const { return false; }
};
struct Spell
{
    Unit* m_caster;
    SpellInfo* m_spellInfo;
    Item* m_CastItem = nullptr;
    SpellCastResult CanOpenLock(uint32, uint32, SkillType&, int32&, int32&);
};
@OPEN_LOCK@
struct CreatureAI
{
    ObjectGuid guid = 0;
    int32 action = -1;
    void SetGUID(ObjectGuid value, int32 type) { guid = value; action = type; }
    void Talk(uint32) {}
};
struct MotionMaster { void Clear() {} };
struct Position { float GetOrientation() const { return 0; } };
struct Creature : Unit
{
    Creature* summoned = nullptr;
    CreatureAI ai;
    MotionMaster motion;
    uint32 spawn = 0, summons = 0, phaseUpdates = 0;
    bool active = false, walk = false;
    Creature* SummonCreature(uint32 entry, float, float, float, float)
    {
        assert(entry == NPC_REGINALD_WINDSOR);
        ++summons;
        if (summoned) summoned->m_phaseMask = GetPhaseMask();
        return summoned;
    }
    void SetPhaseMask(uint32 phase, bool update) { m_phaseMask = phase; phaseUpdates += update; }
    void setActive(bool value) { active = value; }
    CreatureAI* AI() { return &ai; }
    void HandleEmoteCommand(uint32) {}
    void RemoveFlag(uint32, uint32) {}
    MotionMaster* GetMotionMaster() { return &motion; }
    Position GetHomePosition() const { return {}; }
    void SetFacingTo(float) {}
    uint32 GetSpawnId() const { return spawn; }
    void SetWalk(bool value) { walk = value; }
    Creature* FindNearestCreature(uint32, float) { return nullptr; }
};
struct EventMap
{
    template<class Duration> void ScheduleEvent(uint32, Duration) {}
};
struct RoweAI
{
    Creature* me;
    EventMap _events{};
    ObjectGuid _playerGUID = 77;
    @MOVEMENT@
};
struct WindsorAI
{
    Creature* me;
    @VISIBLE@
};
struct Quest { uint32 id; uint32 GetQuestId() const { return id; } };
@ACCEPT@
int main()
{
    @FACTION_ROWS@
    @LOCK_ROWS@
    std::array<uint32, 3> mineFactions{@MINE_FACTIONS@};
    std::array<uint32, 3> mineLocks{@MINE_LOCKS@};
    for (uint32 team : {1u, 2u})
    {
        Player player;
        player.faction = team;
        SpellInfo info;
        Spell mining{&player, &info};
        for (uint32 index = 0; index < mineFactions.size(); ++index)
        {
            GameObject node{mineFactions[index]};
            assert(player.CanUseBattlegroundObject(&node));
            auto* lock = sLockStore.LookupEntry(mineLocks[index]);
            SkillType skill = SKILL_NONE;
            int32 required = 0, actual = 0;
            player.skill = lock->Skill[0] - 1;
            assert(mining.CanOpenLock(0, mineLocks[index], skill, required, actual) == SPELL_FAILED_LOW_CASTLEVEL);
            player.skill = lock->Skill[0];
            assert(mining.CanOpenLock(0, mineLocks[index], skill, required, actual) == SPELL_CAST_OK);
            assert(skill == SKILL_MINING && required == int32(player.skill));
            player.alive = false; assert(!player.CanUseBattlegroundObject(&node)); player.alive = true;
            player.immune = true; assert(!player.CanUseBattlegroundObject(&node)); player.immune = false;
            player.flag = true; assert(!player.CanUseBattlegroundObject(&node)); player.flag = false;
        }
        GameObject hostile{94};
        assert(!player.CanUseBattlegroundObject(&hostile));
    }
    Creature rowe, reginald, katrana;
    katrana.m_phaseMask = @KATRANA_PHASE@;
    rowe.summoned = &reginald;
    RoweAI escort{&rowe};
    escort.MovementInform(0, 2); assert(rowe.summons == 0);
    escort.MovementInform(POINT_MOTION_TYPE, 1); assert(rowe.summons == 0);
    escort.MovementInform(POINT_MOTION_TYPE, 2);
    assert(reginald.GetPhaseMask() == (PHASEMASK_NORMAL | @KATRANA_PHASE@));
    assert(reginald.InSamePhase(katrana.GetPhaseMask()) && reginald.InSamePhase(PHASEMASK_NORMAL));
    assert(!reginald.InSamePhase(262144));
    assert(reginald.phaseUpdates == 1 && reginald.active && reginald.ai.guid == 77);
    assert(reginald.ai.action == ACTION_START_ESCORT && rowe.GetPhaseMask() == PHASEMASK_NORMAL);
    assert(katrana.GetPhaseMask() == @KATRANA_PHASE@);
    rowe.summoned = nullptr;
    escort.MovementInform(POINT_MOTION_TYPE, 2);
    Player player;
    player.quests[QUEST_THE_GREAT_MASQUERADE] = QUEST_STATUS_INCOMPLETE;
    auto quests = player.quests;
    auto playerPhase = player.GetPhaseMask();
    WindsorAI visibility{&reginald};
    assert(visibility.CanBeSeen(&player));
    reginald.spawn = 86900;
    assert(!visibility.CanBeSeen(&player));
    player.quests.clear(); assert(visibility.CanBeSeen(&player));
    player.quests[QUEST_STORMWIND_RENDEZVOUZ] = QUEST_STATUS_COMPLETE;
    assert(!visibility.CanBeSeen(&player));
    player.quests = quests;
    Quest wrong{1}, masquerade{QUEST_THE_GREAT_MASQUERADE};
    reginald.ai.guid = 0;
    OnQuestAccept(&player, &reginald, &wrong); assert(reginald.ai.guid == 0);
    OnQuestAccept(&player, &reginald, &masquerade);
    assert(reginald.ai.guid == player.GetGUID() && reginald.ai.action == ACTION_START_MASQUERADE);
    assert(player.GetPhaseMask() == playerPhase && player.quests == quests);
}
'''
replacements = {
    'PHASES': function(object_header, 'enum PhaseMasks') + ';',
    'QUEST_ENUM': function(source, 'enum TheGreatMasquerade') + ';',
    'SKILLS': function(shared, 'enum SkillType') + ';',
    'LOCK_TYPES': function(shared, 'enum LockType') + ';',
    'SKILL_BY_LOCK': function(shared, 'inline SkillType SkillByLockType('),
    'FACTION': faction,
    'LOCK_ENTRY': function(dbc, 'struct LockEntry'),
    'SAME_PHASE': function(object_header, '[[nodiscard]] bool InSamePhase(uint32 phasemask) const'),
    'BG_USE': function(player, 'bool Player::CanUseBattlegroundObject('),
    'OPEN_LOCK': function(spell, 'SpellCastResult Spell::CanOpenLock('),
    'MOVEMENT': movement, 'VISIBLE': visible, 'ACCEPT': accept, 'KATRANA_PHASE': phase,
    'MINE_FACTIONS': ', '.join(map(str, factions)), 'MINE_LOCKS': ', '.join(str(row[0]) for row in locks),
}
replacements['FACTION_ROWS'] = '\n'.join(
    'sFactionTemplateStore.rows[' + str(key) + '] = {' + ','.join(map(str, row[:6])) + ',{' +
    ','.join(map(str, row[6:10])) + '},{' + ','.join(map(str, row[10:14])) + '}};'
    for key in (1, 2, 94) for row in [records['FactionTemplate.dbc'][key]])
replacements['LOCK_ROWS'] = '\n'.join(
    'sLockStore.rows[' + str(row[0]) + '] = {' + str(row[0]) + ',{' + ','.join(map(str, row[1:9])) + '},{' +
    ','.join(map(str, row[9:17])) + '},{' + ','.join(map(str, row[17:25])) + '}};' for row in locks)
for key, value in replacements.items():
    fixture = fixture.replace('@' + key + '@', value)


def build(directory, executable):
    return [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', *SANITIZER_FLAGS,
            str(directory / 'fixture.cpp'), '-o', str(executable)]


with tempfile.TemporaryDirectory(prefix='ip-world-fixes-') as temporary:
    work = Path(temporary)
    (work / 'fixture.cpp').write_text(fixture)
    executable = work / 'fixture'
    subprocess.run(build(work, executable), check=True)
    result = run_fixture([str(executable)])
    assert result.returncode == 0, result.stdout + result.stderr
    reject_mutants(work, (
        ('mining faction 94 restored', 'fixture.cpp', 'mineFactions{0, 0, 0}', 'mineFactions{94, 94, 94}'),
        ('mining skill bypass', 'fixture.cpp', 'if (skillValue < reqSkillValue)', 'if (false)'),
        ('Windsor phase update removed', 'fixture.cpp', 'reginald->SetPhaseMask(PHASEMASK_MASQUERADE, true);', ''),
        ('patrol quest visibility bypass', 'fixture.cpp', 'if (me->GetSpawnId() == 86900)', 'if (false)'),
    ), build, 'IP world fixes')
print('IP world fixes: scoped neutral mining, native skill checks and Windsor summon/quest phases verified')
