"""Exercise earned warrior, paladin and priest class quest chains for random bots.

The selector and action execute production code against native-shaped adapters.
Named native SQL fields, scripts and handler contracts anchor the data those adapters return.
"""

import argparse
from pathlib import Path
import re
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    cxx,
    function,
    in_parallel,
    prepared_core,
    run_fixture,
    source_argument,
    sql_rows,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help='Playerbots src directory')
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
core = prepared_core(root)
module = args.source or core / 'modules/mod-playerbots/src'
rpg = module / 'Ai/World/Rpg/Action'
source = (rpg / 'ClassQuestChains.cpp').read_text()
header = (rpg / 'ClassQuestChains.h').read_text()
shared = (rpg / 'ClassQuestAction.cpp').read_text()
classes = {'WARRIOR': 1, 'PALADIN': 2, 'PRIEST': 5}

# Native quest rows: each step belongs to its class, and every lesson's reward quest teaches that lesson.
steps = [(classes[cls], 1719 if quest == 'TheAffray' else int(quest), int(spell), int(item), int(target))
         for cls, quest, spell, item, target in re.findall(
             r'\{CLASS_(\w+), (\w+), (\d+), (\d+), (-?\d+)\}', function(source, 'ClassQuestStep const ClassQuestSteps[]'))]
assert len(steps) == 88 and len(steps) == len({row[1] for row in steps})
assert re.search(r'constexpr uint32 TheAffray = 1719;', source)
by_quest = {row[1]: row for row in steps}
lessons = {}
for row in steps:
    lessons.setdefault((row[0], row[2]), []).append(row[1])
order = [(row[0], row[2]) for row in steps]
assert all(order[i] == order[i + 1] or order[i + 1] not in order[:i + 1] for i in range(len(order) - 1)), \
    'steps of one lesson must stay together'
quests = {int(row['ID']): row for row in sql_rows(core, 'quest_template', set(by_quest))}
addon = {int(row['ID']): row for row in sql_rows(core, 'quest_template_addon', set(by_quest))}
assert set(quests) == set(by_quest) == set(addon)
class_masks = {1: 1, 2: 2, 5: 16}
for cls, quest, spell, item, target in steps:
    assert int(addon[quest]['AllowableClasses']) == class_masks[cls], quest
ip_root = core / 'modules/mod-individual-progression/data/sql/world'
historical = (ip_root / 'updates/2026_10_11_00_historical_class_quests.sql').read_text()
restored_rewards = {int(quest): (int(display), int(cast)) for display, cast, quest in re.findall(
    r'UPDATE `quest_template` SET `RewardDisplaySpell` = (\d+), `RewardSpell` = (\d+) WHERE `ID` = (\d+)', historical)}
# Native teaching spells, from the pinned client Spell.dbc: Path of Defense, Path of the Berserker,
# Redemption, Sense Undead and the two warhorse lessons teach the listed stance, spell or mount.
teaches = {8121: 71, 8616: 2458, 7329: 7328, 5503: 5502, 13820: 13819, 34768: 34769}
for (cls, spell), members in lessons.items():
    rewarding = []
    for quest in members:
        cast = int(quests[quest]['RewardSpell'])
        if quest in restored_rewards:
            display, cast = restored_rewards[quest]
            assert cls == 5 and display == spell, quest
            rewarding.append(quest)
        elif cast:
            assert teaches[cast] == spell, (quest, cast)
            rewarding.append(quest)
    assert rewarding, (cls, spell)
assert set(restored_rewards) == {row[1] for row in steps if row[0] == 5}
# Individual Progression teaches each restored family through its dummy reward; Vanilla rank 1 is the displayed spell.
families = re.findall(r'\{\{([\d, ]+)\}, \{\d+, \d+\}, \{\d+, \d+\}, (\d+), \{\{\{(\d+),',
                      (ip_root.parents[2] / 'src/HistoricalClassQuests.cpp').read_text())
taught_by = {}
for members, cast, first in families:
    for quest in map(int, members.split(', ')):
        if quest:
            taught_by[quest] = (int(first), int(cast))
assert taught_by == restored_rewards

# Players and bots receive every step from a native giver or the owned item that starts it.
relations = {}
for table in ('creature_queststarter', 'creature_questender', 'gameobject_queststarter', 'gameobject_questender'):
    raw = (core / f'data/sql/base/db_world/{table}.sql').read_text()
    assert re.findall(r'^  `([^`]+)`', raw, re.MULTILINE) == ['id', 'quest']
    relations[table] = {tuple(map(int, row)) for row in re.findall(r'^\((\d+),(\d+)\)[,;]$', raw, re.MULTILINE)}
mounts = (ip_root / 'base/mounts_and_riding.sql').read_text()
for table in ('creature_queststarter', 'creature_questender'):
    for statement in re.findall(rf'INSERT INTO `{table}` \(`id`, `quest`\) VALUES ([^;]+);', mounts):
        relations[table] |= {tuple(map(int, row)) for row in re.findall(r'\((\d+), (\d+)\)', statement)}
    for giver, quest in re.findall(rf'INSERT INTO `{table}` \(`id`, `quest`\) SELECT (\d+), (\d+)', historical):
        relations[table].add((int(giver), int(quest)))
start_items = {int(row['entry']): int(row['startquest']) for row in sql_rows(core, 'item_template', {6776})}
assert start_items == {6776: 1649}
assert {int(quests[q]['RewardItem1']) for q in (1793, 1794)} == {6776}
for quest in by_quest:
    started = any(q == quest for _, q in relations['creature_queststarter'] | relations['gameobject_queststarter'])
    assert started or quest in start_items.values(), quest
    assert any(q == quest for _, q in relations['creature_questender'] | relations['gameobject_questender']), quest
disables = (core / 'data/sql/base/db_world/disables.sql').read_text()
disabled = {int(entry) for entry in re.findall(r'^\(1,(\d+),', disables, re.MULTILINE)} & set(by_quest)
assert disabled and disabled <= set(restored_rewards)
for quest in disabled:
    assert f"`entry` = {quest} AND `comment` = 'Deprecated quest'" in historical, quest

# Native event and item metadata used by the step interactions.
event_quests = {quest for quest in by_quest if int(addon[quest]['SpecialFlags']) & 2}
assert event_quests == {1640, 1651, 1719, 9678, 9686}
for quest in event_quests:
    # Abandoning a stalled event quest cannot discard collected quest items.
    assert all(quests[quest][f'RequiredItemId{index}'] == '0' for index in range(1, 7)), quest
    assert quests[quest]['StartItem'] == '0', quest
creature_steps = {row[1]: row for row in steps if row[4] > 0}
object_steps = {row[1]: row for row in steps if row[4] < 0}
assert {quest: (item, target) for quest, (_, _, _, item, target) in creature_steps.items()} == {
    1640: (0, 6090), 1651: (0, 6182), 1786: (6866, 6172), 1783: (6866, 6177), 9600: (6866, 17542),
    9684: (24157, 17845), 9685: (24184, 17768)}
assert {quest: (item, target) for quest, (_, _, _, item, target) in object_steps.items()} == {
    1819: (0, -104593), 9582: (23925, -181849), 9678: (0, -181956), 9686: (0, -182052)}
items = {int(row['entry']): row for row in sql_rows(core, 'item_template', {6866, 24157, 24184, 23925})}
conditions = sql_rows(core, 'conditions', {13})
targets = {}
for row in conditions:
    if int(row['ConditionTypeOrReference']) == 31 and int(row['ConditionValue1']) == 3:
        targets.setdefault(int(row['SourceEntry']), set()).add(int(row['ConditionValue2']))
for quest, (_, _, _, item, target) in creature_steps.items():
    if item:
        assert target in targets[int(items[item]['spellid_1'])], quest
        assert int(items[item]['spelltrigger_1']) == 0
assert int(quests[1781]['StartItem']) == 6866 and int(quests[1779]['StartItem']) == 6866
assert int(quests[9600]['StartItem']) == 6866 and int(quests[9685]['StartItem']) == 24184
assert int(quests[9684]['StartItem']) == 24157 and int(quests[9582]['StartItem']) == 23925
for quest in (1786, 1783):
    target = creature_steps[quest][4]
    assert (target, quest) in relations['creature_questender'] and not int(quests[quest]['RequiredNpcOrGo1'])
for quest in (9600, 9685):
    assert int(addon[quest]['SpecialFlags']) & 32 and int(quests[quest]['RequiredNpcOrGo1']) == creature_steps[quest][4]
objects = {int(row['entry']): row for row in sql_rows(core, 'gameobject_template', {104593, 181956, 182052, 181849})}
for entry, quest in ((104593, 1819), (181956, 9678), (182052, 9686)):
    assert int(objects[entry]['type']) == 10 and int(objects[entry]['Data1']) == quest, entry
assert int(objects[181849]['type']) == 0 and objects[181849]['ScriptName'] == 'go_ravager_cage'
object_addons = {int(row['entry']): int(row['flags']) for row in sql_rows(core, 'gameobject_template_addon', set(objects))}
assert all(not flags & 2 for flags in object_addons.values()), 'quest objects must be unlocked'
spawned = set()
with (core / 'data/sql/base/db_world/creature.sql').open(encoding='utf-8') as rows:
    for line in rows:
        if line.startswith('('):
            spawned.add(int(line.split(',', 2)[1]))
assert {row[4] for row in creature_steps.values()} <= spawned
spawned_objects = set()
with (core / 'data/sql/base/db_world/gameobject.sql').open(encoding='utf-8') as rows:
    for line in rows:
        if line.startswith('('):
            spawned_objects.add(int(line.split(',', 2)[1]))
assert {-row[4] for row in object_steps.values()} <= spawned_objects

smart = {}
for row in sql_rows(core, 'smart_scripts', {6090, 6172, 6177, 17542, 17768, 617200, 617700, 1754200, 1776800,
                                            104593, 10459300, 182052, 17807, 17716}):
    smart.setdefault(int(row['entryorguid']), []).append(row)
def has(entry, **fields):
    return any(all(int(row[key]) == value for key, value in fields.items()) for row in smart[entry])
# Bartleby fights the bot that took Beat Bartleby and credits it at 15 percent health.
assert has(6090, event_type=19, event_param1=1640, action_type=2)
assert has(6090, event_type=61, action_type=49) and has(6090, event_type=2, event_param2=15, action_type=15)
# The Symbol of Life and Shimmering Vessel revive their native targets.
for entry, script in ((6172, 617200), (6177, 617700)):
    assert has(entry, event_type=8, event_param1=8593, action_type=80, action_param1=script)
    assert has(script, action_type=81, action_param1=2)
assert has(17542, event_type=8, event_param1=8593) and has(1754200, action_type=33, action_param1=17542)
assert has(17768, event_type=8, event_param1=31225) and has(1776800, action_type=33, action_param1=17768)
assert has(104593, event_type=70, action_type=80, action_param1=10459300)
assert has(10459300, action_type=12, action_param1=6390)
assert has(17807, event_type=19, event_param1=9686, action_type=70, target_param2=182052)
assert has(182052, event_type=70, action_type=12) and has(17716, event_type=6, action_type=15, action_param1=9678)

scripts = core / 'src/server/scripts'
barrens = (scripts / 'Kalimdor/zone_the_barrens.cpp').read_text()
twiggy = function(barrens, 'class npc_twiggy_flathead')
assert 'me->IsWithinDistInMap(who, 10.0f) && who->ToPlayer()->GetQuestStatus(1719) == QUEST_STATUS_INCOMPLETE' in twiggy
assert 'x >= -1684 && x <= -1674 && y >= -4334 && y <= -4324' in twiggy
assert 'pWarrior->FailQuest(1719);' in twiggy
grate = re.search(r'WorldPosition const AffrayGrate\(1, (-?[\d.]+)f, (-?[\d.]+)f, (-?[\d.]+)f\);', source)
gx, gy = float(grate.group(1)), float(grate.group(2))
assert -1684 <= gx - 3 and gx + 3 <= -1674 and -4334 <= gy - 3 and gy + 3 <= -4324
assert re.search(r'constexpr float WaitDistance = 3\.0f;', source)
with (core / 'data/sql/base/db_world/creature.sql').open(encoding='utf-8') as rows:
    twiggy_spawn = [line for line in rows if line.startswith('(') and line.split(',')[1] == '6248']
assert len(twiggy_spawn) == 1
tx, ty = map(float, twiggy_spawn[0].split(',')[10:12])
assert ((tx - gx) ** 2 + (ty - gy) ** 2) ** 0.5 + 3 < 10
westfall = (scripts / 'EasternKingdoms/zone_westfall.cpp').read_text()
assert 'pEscortAI->Start(true, player->GetGUID());' in function(westfall, 'bool OnQuestAccept(')
assert 'creature->AI()->AttackStart(me);' in function(westfall, 'void JustSummoned(Creature* creature)')
ravager = (scripts / 'Kalimdor/zone_azuremyst_isle.cpp').read_text()
cage = function(ravager, 'class go_ravager_cage')
assert 'ravager->AI()->AttackStart(player);' in cage and 'QUEST_STRENGTH_ONE' in cage
assert 'QUEST_STRENGTH_ONE      = 9582' in ravager
brazier = function((scripts / 'World/go_scripts.cpp').read_text(), 'class go_gilded_brazier')
assert 'player->SummonCreature(NPC_STILLBLADE' in brazier and 'QUEST_STATUS_INCOMPLETE' in brazier

game = core / 'src/server/game'
go_source = (game / 'Entities/GameObject/GameObject.cpp').read_text()
use = function(go_source, 'void GameObject::Use(Unit* user)')
goober = use[use.index('case GAMEOBJECT_TYPE_GOOBER:'):]
assert 'if (HasGameObjectFlag(GO_FLAG_IN_USE))' in goober[:400]
assert 'player->GetQuestStatus(info->goober.questId) != QUEST_STATUS_INCOMPLETE' in goober
quest_handler = (game / 'Handlers/QuestHandler.cpp').read_text()
accept = function(quest_handler, 'void WorldSession::HandleQuestgiverAcceptQuestOpcode(')
assert 'TYPEMASK_ITEM' in accept and '!object->hasQuest(questId)' in accept and 'CanTakeQuest(quest, true)' in accept
remove = function(quest_handler, 'void WorldSession::HandleQuestLogRemoveQuest(')
assert 'if (!_player->TakeQuestSourceItem(questId, true))\n                return;' in remove
assert '_player->GetQuestSlotQuestId(packet.Slot)' in remove and '_player->RemoveActiveQuest(questId);' in remove
assert 'bool hasQuest(uint32 quest_id) const override { return GetTemplate()->StartQuest == quest_id; }' in (
    game / 'Entities/Item/Item.h').read_text()
player_quest = (game / 'Entities/Player/PlayerQuest.cpp').read_text()
assert 'TakeQuestSourceItem' not in function(player_quest, 'void Player::RewardQuest(')
started = function(player_quest, 'void Player::AddQuestAndCheckCompletion(')
assert 'DestroyItem(item->GetBagSlot(), item->GetSlot(), true);' in started[started.index('case TYPEID_ITEM:'):]
native_take = function(player_quest, 'bool Player::CanTakeQuest(')
for check in ('SatisfyQuestRace', 'SatisfyQuestClass', 'SatisfyQuestLevel', 'SatisfyQuestExclusiveGroup',
              'SatisfyQuestPreviousQuest', 'SatisfyQuestConditions'):
    assert check in native_take
items_source = (module / 'Ai/Base/Actions/UseItemAction.cpp').read_text()
native_use = function(items_source, 'bool UseItemAction::UseGameObject(')
for check in ('!go->isSpawned()', 'go->ActivateToQuest(bot)', 'GO_FLAG_LOCKED', 'HandleGameObjectUseOpcode(use)'):
    assert check in native_use
assert 'UseItem(item, ObjectGuid::Empty, nullptr, target)' in function(items_source, 'bool UseItemAction::UseItemOnUnit(')
assert 'UseItem(item, go, nullptr)' in function(items_source, 'bool UseItemAction::UseItemOnGameObject(')
attack_source = (module / 'Ai/Base/Actions/AttackAction.cpp').read_text()
attack = function(attack_source, 'bool AttackAction::Attack(')
for check in ('bot->IsFriendlyTo(target)', '!bot->IsWithinLOSInMap(target)', '!bot->IsValidAttackTarget(target)',
              'botAI->ChangeEngine(BOT_STATE_COMBAT);'):
    assert check in attack
assert 'bool Attack(Unit* target, bool with_pet = true);' in (module / 'Ai/Base/Actions/AttackAction.h').read_text()
for forbidden in ('bot->AddQuest(', 'bot->RewardQuest(', 'CompleteQuest(', 'AreaExploredOrEventHappens(',
                  'learnSpell(', 'SummonCreature(', 'AddItem(', 'TeleportTo(', 'KilledMonsterCredit(',
                  'CastSpell(', 'SetFaction(', 'RemoveUnitFlag('):
    assert forbidden not in source, forbidden

contexts = {name: (module / f'Ai/Base/{name}.h').read_text() for name in ('ActionContext', 'TriggerContext', 'ValueContext')}
assert 'creators["class quest chain"] = &ActionContext::class_quest_chain;' in contexts['ActionContext']
assert 'return new ClassQuestChainAction(botAI);' in contexts['ActionContext']
assert 'creators["class quest chain"] = &TriggerContext::class_quest_chain;' in contexts['TriggerContext']
assert 'return new ClassQuestChainTrigger(botAI);' in contexts['TriggerContext']
assert 'creators["class quest chain"] = &ValueContext::class_quest_chain;' in contexts['ValueContext']
assert 'return new ClassQuestChainValue(botAI);' in contexts['ValueContext']
assert 'CalculatedValue<uint32>(botAI, "class quest chain", 5)' in header
for strategy in ('Warrior/Strategy/GenericWarriorNonCombatStrategy.cpp', 'Paladin/Strategy/GenericPaladinNonCombatStrategy.cpp',
                 'Priest/Strategy/PriestNonCombatStrategy.cpp'):
    text = (module / 'Ai/Class' / strategy).read_text()
    assert 'new TriggerNode("class quest chain", {NextAction("class quest chain", ACTION_NORMAL + 2)})' in text, strategy

production = {
    'namespace': function(source, 'namespace\n'),
    'gate': function(shared, 'bool CanRunClassQuest('),
    'needed': function(shared, 'bool ClassQuestObjectiveNeeded('),
    'current': function(source, 'ClassQuestStep const* CurrentClassQuestStep('),
    'value': function(source, 'uint32 ClassQuestChainValue::Calculate()'),
    'trigger': function(source, 'bool ClassQuestChainTrigger::IsActive()'),
    'useful': function(source, 'bool ClassQuestChainAction::isUseful()'),
    'execute': function(source, 'bool ClassQuestChainAction::Execute('),
    'creature': function(source, 'bool ClassQuestChainAction::UseOnCreature('),
    'object': function(source, 'bool ClassQuestChainAction::UseObject('),
    'stay': function(source, 'bool ClassQuestChainAction::StayWith('),
    'wait': function(source, 'bool ClassQuestChainAction::Wait('),
    'restart': function(source, 'bool ClassQuestChainAction::Restart('),
    'abandon': function(source, 'bool ClassQuestChainAction::Abandon('),
    'spawn': function(source, 'WorldPosition ClassQuestChainAction::SpawnPosition('),
    'classes': '\n'.join(function(header, name) + ';' for name in (
        'struct ClassQuestStep', 'class ClassQuestChainValue', 'class ClassQuestChainTrigger',
        'class ClassQuestChainAction')),
}
native_quests = []
for quest, row in quests.items():
    display, cast = restored_rewards.get(quest, (int(row['RewardDisplaySpell']), int(row['RewardSpell'])))
    taught = teaches.get(cast, display if quest in restored_rewards else 0)
    fields = [str(quest), str(display), str(cast), str(taught), row['StartItem'], addon[quest]['SpecialFlags'],
              '{' + ','.join(row[f'RequiredNpcOrGo{index}'] for index in range(1, 5)) + '}',
              '{' + ','.join(row[f'RequiredNpcOrGoCount{index}'] for index in range(1, 5)) + '}',
              '{' + ','.join(row[f'RequiredItemId{index}'] for index in range(1, 7)) + '}',
              '{' + ','.join(row[f'RequiredItemCount{index}'] for index in range(1, 7)) + '}']
    native_quests.append('Quest{' + ','.join(fields) + '}')
production['nativequests'] = 'for(Quest const& native : {' + ',\n'.join(native_quests) + '}) objectMgr.quests.emplace(native.id,native);'

prelude = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>
using uint8=uint8_t; using uint16=uint16_t; using uint32=uint32_t; using int32=int32_t;
constexpr uint8 CLASS_WARRIOR=1, CLASS_PALADIN=2, CLASS_PRIEST=5, CLASS_MAGE=8;
constexpr int UNIT_STATE_LOST_CONTROL=1, CURRENT_CHANNELED_SPELL=1, CURRENT_GENERIC_SPELL=2, CMSG_QUESTLOG_REMOVE_QUEST=3;
constexpr uint32 QUEST_OBJECTIVES_COUNT=4, QUEST_ITEM_OBJECTIVES_COUNT=6, IN_MILLISECONDS=1000, MINUTE=60,
    MAX_QUEST_LOG_SIZE=25, UNIT_NPC_FLAG_QUESTGIVER=2, QUEST_SPECIAL_FLAGS_EXPLORATION_OR_EVENT=2;
constexpr float INTERACTION_DISTANCE=5.0f;
enum QuestStatus { QUEST_STATUS_NONE=0, QUEST_STATUS_COMPLETE=1, QUEST_STATUS_INCOMPLETE=3, QUEST_STATUS_FAILED=5,
                   QUEST_STATUS_REWARDED=6 };
uint32 now=100000;
uint32 getMSTime() { return now; }
uint32 GetMSTimeDiffToNow(uint32 before) { return now-before; }
struct ObjectGuid {
    using LowType=uint32;
    uint32 value=0;
    bool operator==(ObjectGuid const&) const=default;
};
using GuidVector=std::vector<ObjectGuid>;
struct Event {};
struct WorldPacket {
    int opcode; std::vector<uint32> values;
    explicit WorldPacket(int opcode):opcode(opcode){}
    WorldPacket& operator<<(uint8 n) { values.push_back(n); return *this; }
};
namespace WorldPackets::Quest {
struct QuestLogRemoveQuest {
    WorldPacket packet; uint8 Slot=255;
    explicit QuestLogRemoveQuest(WorldPacket&& p):packet(std::move(p)){}
    void Read() { assert(packet.opcode==CMSG_QUESTLOG_REMOVE_QUEST&&packet.values.size()==1); Slot=uint8(packet.values[0]); }
};
}
struct Player; struct Creature; struct GameObject; struct Spell { int kind=0; };
struct Session {
    Player* player=nullptr; bool headless=true,removeFails=false; int removals=0;
    bool IsHeadless() const { return headless; }
    void HandleQuestLogRemoveQuest(WorldPackets::Quest::QuestLogRemoveQuest&);
};
struct Map { bool dungeon=false; bool IsDungeon() const { return dungeon; } };
struct ItemTemplate { uint32 StartQuest=0; };
struct Item {
    uint32 entry=0,guid=0; ItemTemplate proto;
    ItemTemplate const* GetTemplate() const { return &proto; }
    ObjectGuid GetGUID() const { return {guid}; }
};
struct Quest {
    uint32 id=0,display=0; int32 cast=0; uint32 taught=0,source=0,special=0;
    std::array<int32,QUEST_OBJECTIVES_COUNT> RequiredNpcOrGo{};
    std::array<uint32,QUEST_OBJECTIVES_COUNT> RequiredNpcOrGoCount{};
    std::array<uint32,QUEST_ITEM_OBJECTIVES_COUNT> RequiredItemId{},RequiredItemCount{};
    uint32 GetQuestId() const { return id; }
    uint32 GetRewSpell() const { return display; }
    int32 GetRewSpellCast() const { return cast; }
    uint32 GetSrcItemId() const { return source; }
    bool HasSpecialFlag(uint32 flag) const { return (special&flag)!=0; }
};
struct QuestStatusData {
    QuestStatus Status=QUEST_STATUS_NONE;
    std::array<uint32,QUEST_OBJECTIVES_COUNT> CreatureOrGOCount{};
};
struct WorldObject {
    uint32 guid=1,entry=0,mapId=0,spawn=0; float x=2,y=0,z=0,size=0.5f;
    bool inWorld=true,sameMap=true,samePhase=true,visible=true,los=true,alive=true;
    virtual ~WorldObject()=default;
    ObjectGuid GetGUID() const { return {guid}; }
    uint32 GetEntry() const { return entry; }
    uint32 GetSpawnId() const { return spawn; }
    bool IsInWorld() const { return inWorld; }
    bool IsAlive() const { return alive; }
    bool IsWithinDistInMap(WorldObject const* other,float range) const {
        float const dx=x-other->x,dy=y-other->y,maximum=range+size+other->size;
        return sameMap&&samePhase&&dx*dx+dy*dy<maximum*maximum;
    }
};
struct Unit:WorldObject {
    std::set<Unit*> attackers; bool attackable=true;
    virtual Creature* ToCreature() { return nullptr; }
    std::set<Unit*> const& getAttackers() const { return attackers; }
};
struct Creature:Unit {
    bool removing=false,questgiver=true; std::set<uint32> finishes;
    Creature* ToCreature() override { return this; }
    bool IsDuringRemoveFromWorld() const { return removing; }
    bool hasInvolvedQuest(uint32 q) const { return finishes.contains(q); }
    bool HasNpcFlag(uint32 flag) const { assert(flag==UNIT_NPC_FLAG_QUESTGIVER); return questgiver; }
};
struct GameObject:WorldObject {
    bool spawned=true;
    bool isSpawned() const { return spawned; }
};
struct Player:Unit {
    uint32 cls=CLASS_WARRIOR,phase=1; bool random=true,hasSession=true,group=false,teleport=false,battleground=false,
      arena=false,combat=false,mounted=false,flight=false,flying=false,transport=false,vehicle=false,lostControl=false,
      casting=false,canAdd=true,useChannel=false,targetsAttackable=true;
    Map map; Session session; Spell channel{CURRENT_CHANNELED_SPELL},generic{CURRENT_GENERIC_SPELL}; int stops=0;
    std::set<uint32> known,available; std::map<uint32,QuestStatusData> quests; std::map<uint32,Item> inventory;
    std::map<uint32,uint32> bank;
    Player() { session.player=this; guid=100; x=0; size=1.5f; }
    uint32 getClass() const { return cls; } Session* GetSession() { return hasSession?&session:nullptr; }
    bool GetGroup() const { return group; } bool IsBeingTeleported() const { return teleport; }
    Map* GetMap() { return &map; } bool InBattleground() const { return battleground; } bool InArena() const { return arena; }
    bool IsInCombat() const { return combat; } bool IsMounted() const { return mounted; }
    bool IsInFlight() const { return flight; } bool IsFlying() const { return flying; }
    bool GetTransport() const { return transport; } bool GetVehicle() const { return vehicle; }
    bool HasUnitState(int) const { return lostControl; } bool IsNonMeleeSpellCast(bool) const { return casting; }
    bool HasSpell(uint32 n) const { return known.contains(n); }
    QuestStatus GetQuestStatus(uint32 q) const { return quests.contains(q)?quests.at(q).Status:QUEST_STATUS_NONE; }
    bool GetQuestRewardStatus(uint32 q) const { return quests.contains(q)&&quests.at(q).Status==QUEST_STATUS_REWARDED; }
    auto const& getQuestStatusMap() const { return quests; }
    uint32 GetQuestSlotQuestId(uint16 slot) const {
        uint16 index=0;
        for(auto const& [id,data]:quests) if(data.Status!=QUEST_STATUS_REWARDED&&data.Status!=QUEST_STATUS_NONE&&index++==slot) return id;
        return 0;
    }
    Item* GetItemByEntry(uint32 i) { return inventory.contains(i)?&inventory.at(i):nullptr; }
    uint32 GetItemCount(uint32 i) const { return inventory.contains(i)?1:0; }
    bool HasItemCount(uint32 i,uint32 count,bool inBank) const {
        assert(count==1&&inBank); return inventory.contains(i)||bank.contains(i);
    }
    bool CanTakeQuest(Quest const* q,bool) const { return available.contains(q->id)&&GetQuestStatus(q->id)==QUEST_STATUS_NONE&&!GetQuestRewardStatus(q->id); }
    bool CanAddQuest(Quest const*,bool) const { return canAdd; }
    bool IsInMap(WorldObject const* o) const { return o->sameMap; }
    bool InSamePhase(WorldObject const* o) const { return o->samePhase; }
    bool CanSeeOrDetect(WorldObject const* o) const { return o->visible; }
    bool IsWithinLOSInMap(WorldObject const* o) const { return o->los; }
    bool IsValidAttackTarget(Unit const* u) const { return targetsAttackable&&u->attackable&&u!=this; }
    float GetDistance(WorldObject const* o) const { return std::max(0.0f,std::hypot(o->x-x,o->y-y)-size-o->size); }
    void StopMoving() { ++stops; }
    Spell* GetCurrentSpell(int kind) { return kind==CURRENT_GENERIC_SPELL?(casting?&generic:nullptr):useChannel?&channel:nullptr; }
    uint32 GetMapId() const { return mapId; } uint32 GetPhaseMask() const { return phase; }
    float GetExactDist(struct WorldPosition const&) const;
};
struct ObjectMgr {
    std::map<uint32,Quest> quests;
    Quest const* GetQuestTemplate(uint32 q) const { return quests.contains(q)?&quests.at(q):nullptr; }
} objectMgr;
auto* sObjectMgr=&objectMgr;
void Session::HandleQuestLogRemoveQuest(WorldPackets::Quest::QuestLogRemoveQuest& request) {
    ++removals; uint32 const id=player->GetQuestSlotQuestId(request.Slot); assert(id);
    if(removeFails) return;  // Native removal stops when the source item cannot be taken.
    // Native removal takes the quest's own source item and clears the log entry.
    if(uint32 src=objectMgr.quests.at(id).source) player->inventory.erase(src);
    player->quests.erase(id);
}
struct Config { bool naturalProgression=true; std::set<uint32> IgnoredQuests; } sPlayerbotAIConfig;
struct RandomMgr { bool IsRandomBot(Player* p) const { return p->random; } } sRandomPlayerbotMgr;
struct CreatureData { uint32 id=0,mapid=0,phaseMask=1; float posX=0,posY=0,posZ=0; };
struct GameObjectData { uint32 id=0,mapid=0,phaseMask=1; float posX=0,posY=0,posZ=0; };
std::vector<CreatureData> creatureSpawns; std::vector<GameObjectData> objectSpawns; int spawnScans=0;
struct WorldPosition {
    uint32 map=0; float x=0,y=0,z=0;
    WorldPosition()=default;
    explicit WorldPosition(WorldObject* o):map(o->mapId),x(o->x),y(o->y),z(o->z){}
    WorldPosition(uint32 m,float a,float b,float c):map(m),x(a),y(b),z(c){}
    bool operator==(WorldPosition const&) const=default;
    uint32 GetMapId() const { return map; }
    std::vector<CreatureData const*> getCreaturesNear(float radius,uint32 entry) {
        assert(radius==0); ++spawnScans; std::vector<CreatureData const*> rows;
        for(auto const& s:creatureSpawns) if(s.id==entry) rows.push_back(&s);
        return rows;
    }
    std::vector<GameObjectData const*> getGameObjectsNear(float radius,uint32 entry) {
        assert(radius==0); ++spawnScans; std::vector<GameObjectData const*> rows;
        for(auto const& s:objectSpawns) if(s.id==entry) rows.push_back(&s);
        return rows;
    }
};
float Player::GetExactDist(WorldPosition const& p) const { return std::sqrt((p.x-x)*(p.x-x)+(p.y-y)*(p.y-y)+(p.z-z)*(p.z-z)); }
enum class QuestRelationFlag:uint32 { questGiver=16, questTaker=32 };
struct ItemsValue { std::vector<Item*> items; std::vector<Item*> Get() { return items; } };
struct Context {
    GuidVector npcs,objects; uint32 quest=0; ItemsValue startItems;
    template<class T> ItemsValue* GetValue(std::string const& name,std::string const& qualifier) {
        static_assert(std::is_same_v<T,std::vector<Item*>>);
        assert(name=="inventory items"&&qualifier=="start quest"); return &startItems;
    }
};
template<class T> T GetValue(Context* c,std::string const& name) {
    if constexpr(std::is_same_v<T,GuidVector>) {
        if(name=="nearest npcs") return c->npcs;
        assert(name=="nearest game objects no los"); return c->objects;
    }
    else { assert(name=="class quest chain"); return c->quest; }
}
#define AI_VALUE(type,name) GetValue<type>(context,name)
struct PlayerbotAI {
    Player* bot; Context context; bool master=false,useResult=true,attackResult=true,startsCast=false;
    int waits=0,itemUses=0,objectUses=0,attacks=0; Spell* waitedFor=nullptr;
    Unit* usedOn=nullptr; Unit* attacked=nullptr; Item* usedItem=nullptr; ObjectGuid usedObject;
    std::map<uint32,Unit*> units; std::map<uint32,GameObject*> objects;
    Player* GetBot() const { return bot; } bool GetMaster() const { return master; }
    Context* GetAiObjectContext() { return &context; }
    Unit* GetUnit(ObjectGuid g) const { return units.contains(g.value)?units.at(g.value):nullptr; }
    GameObject* GetGameObject(ObjectGuid g) const { return objects.contains(g.value)?objects.at(g.value):nullptr; }
    void WaitForSpellCast(Spell* spell) { assert(spell); ++waits; waitedFor=spell; }
};
// Shared route costs are covered by the continent route fixtures; without travel they stay on the current map.
struct ClassQuestRouteCosts {
    Player* bot;
    explicit ClassQuestRouteCosts(PlayerbotAI* ai):bot(ai->bot){}
    float Cost(WorldPosition const& pos) const {
        return pos.GetMapId()==bot->GetMapId()?bot->GetExactDist(pos):std::numeric_limits<float>::infinity();
    }
};
std::map<uint32,std::vector<WorldPosition>> givers;
WorldPosition NearestClassQuestLocation(uint32 questId,uint32 relation,ClassQuestRouteCosts const& costs) {
    assert(relation==uint32(QuestRelationFlag::questGiver));
    WorldPosition nearest; float distance=std::numeric_limits<float>::max();
    for(auto const& pos:givers[questId]) if(costs.Cost(pos)<distance) { nearest=pos; distance=costs.Cost(pos); }
    return nearest;
}
struct AiNamedObject {
    PlayerbotAI* botAI; Player* bot; Context* context;
    AiNamedObject(PlayerbotAI* ai,std::string):botAI(ai),bot(ai->bot),context(&ai->context){}
    virtual ~AiNamedObject()=default;
};
struct Trigger:AiNamedObject { Trigger(PlayerbotAI* ai,std::string name):AiNamedObject(ai,name){} virtual bool IsActive(){return false;} };
template<class T> struct CalculatedValue {
    PlayerbotAI* botAI; CalculatedValue(PlayerbotAI* ai,std::string,int):botAI(ai){}
    virtual ~CalculatedValue()=default; virtual T Calculate()=0;
};
struct Record { int gives=0,rewards=0,moves=0,objectives=0,accepts=0; ObjectGuid acceptedFrom; WorldPosition target; };
Record calls; bool giverResult=false,rewardResult=false,moveResult=true,objectiveResult=true,acceptRefused=false;
// Native giver interaction, quest-location travel and objectives are exercised by the warlock and druid fixtures.
struct ClassQuestAction:AiNamedObject {
    ClassQuestAction(PlayerbotAI* ai,std::string name):AiNamedObject(ai,name){}
    virtual bool isUseful(){return true;} virtual bool Execute(Event){return false;}
protected:
    bool InteractWithQuestGiver(Quest const*,bool reward) {
        ++(reward?calls.rewards:calls.gives); return reward?rewardResult:giverResult;
    }
    bool MoveToQuestLocation(Quest const*,bool) { ++calls.moves; return moveResult; }
    bool MoveToQuestPosition(WorldPosition const& pos) { ++calls.moves; calls.target=pos; return moveResult; }
    bool DoObjectives(Quest const*) { ++calls.objectives; return objectiveResult; }
    bool AcceptQuest(Quest const* quest,ObjectGuid guid) {
        ++calls.accepts; calls.acceptedFrom=guid;
        for(auto& [entry,item]:bot->inventory)
            if(!acceptRefused&&item.guid==guid.value&&item.proto.StartQuest==quest->id&&bot->CanTakeQuest(quest,true)) {
                // Native acceptance destroys the start item and supplies the quest's own source item.
                bot->quests[quest->id].Status=QUEST_STATUS_INCOMPLETE; bot->inventory.erase(entry);
                if(quest->source) bot->inventory[quest->source].entry=quest->source;
                return true;
            }
        return true;
    }
};
struct AttackAction {
    PlayerbotAI* botAI;
    AttackAction(PlayerbotAI* ai,std::string const):botAI(ai){}
protected:
    bool Attack(Unit* target,bool=true) {
        Player* bot=botAI->bot;
        if(!target||!target->IsInWorld()||!target->IsAlive()||!bot->IsWithinLOSInMap(target)||!bot->IsValidAttackTarget(target))
            return false;
        ++botAI->attacks; botAI->attacked=target; return botAI->attackResult;
    }
};
struct UseItemAction {
    PlayerbotAI* botAI;
    explicit UseItemAction(PlayerbotAI* ai,std::string const="use",bool=false):botAI(ai){}
    bool UseItemOnUnit(Item* item,Unit* target) {
        assert(item&&target&&botAI->bot->GetItemByEntry(item->entry)==item);
        ++botAI->itemUses; botAI->usedItem=item; botAI->usedOn=target; return botAI->useResult;
    }
    bool UseItemOnGameObject(Item* item,ObjectGuid go) {
        assert(item&&botAI->bot->GetItemByEntry(item->entry)==item);
        ++botAI->itemUses; botAI->usedItem=item; botAI->usedObject=go; botAI->bot->casting=botAI->startsCast;
        return botAI->useResult;
    }
protected:
    bool UseGameObject(ObjectGuid guid) {
        GameObject* go=botAI->GetGameObject(guid);
        if(!go||!go->isSpawned()) return false;
        ++botAI->objectUses; botAI->usedObject=guid; botAI->bot->casting=botAI->startsCast; return botAI->useResult;
    }
};
@@CLASSES@@
@@GATE@@
@@NEEDED@@
@@NAMESPACE@@
@@CURRENT@@
@@VALUE@@
@@TRIGGER@@
@@USEFUL@@
@@EXECUTE@@
@@CREATURE@@
@@OBJECT@@
@@STAY@@
@@WAIT@@
@@RESTART@@
@@ABANDON@@
@@SPAWN@@
'''

tests = r'''
ClassQuestStep const* Step(uint32 quest) {
    auto const* row=std::find_if(std::begin(ClassQuestSteps),std::end(ClassQuestSteps),[quest](auto const& s){return s.Quest==quest;});
    assert(row!=std::end(ClassQuestSteps)); return row;
}
struct Scenario {
    Player bot; PlayerbotAI ai{&bot}; ClassQuestChainValue value{&ai}; ClassQuestChainTrigger trigger{&ai};
    ClassQuestChainAction action{&ai}; Creature target; GameObject object; Creature raider;
    ClassQuestStep const* step;
    explicit Scenario(uint32 quest=1786,QuestStatus status=QUEST_STATUS_INCOMPLETE) {
        now=100000; sPlayerbotAIConfig={}; objectMgr={}; givers.clear(); creatureSpawns.clear(); objectSpawns.clear();
        spawnScans=0; calls={}; giverResult=false; rewardResult=false; moveResult=true; objectiveResult=true; acceptRefused=false;
        @@NATIVEQUESTS@@
        step=Step(quest); bot.cls=step->Class;
        if(status!=QUEST_STATUS_NONE) bot.quests[quest].Status=status;
        if(step->Item) bot.inventory[step->Item]={step->Item,50};
        target.guid=2; target.entry=step->Target>0?uint32(step->Target):6172; target.spawn=20;
        target.questgiver=false; target.finishes.insert(quest);
        ai.units[2]=&target; ai.context.npcs={{2}};
        object.guid=3; object.entry=step->Target<0?uint32(-step->Target):104593; ai.objects[3]=&object; ai.context.objects={{3}};
        raider.guid=4; raider.entry=6180; raider.x=3; ai.units[4]=&raider;
        creatureSpawns.push_back({target.entry,0,1,40,0,0}); objectSpawns.push_back({object.entry,0,1,40,0,0});
        ai.context.quest=value.Calculate();
    }
    void Offer(uint32 quest) { bot.quests.erase(quest); bot.available.insert(quest); givers[quest]={{0,30,0,0}}; }
    void Objective(uint32 quest,int32 entry) {
        auto& native=objectMgr.quests.at(quest); native.RequiredNpcOrGo[0]=entry; native.RequiredNpcOrGoCount[0]=1;
    }
};
int main() {
    // The table selects the in-progress step of the first unearned lesson for the bot's own class.
    for(auto const& row:ClassQuestSteps) {
        Scenario s(row.Quest);
        assert(s.value.Calculate()==row.Quest&&s.trigger.IsActive()&&s.action.isUseful());
        s.bot.known.insert(row.Spell); s.ai.context.quest=s.value.Calculate();
        assert(!s.ai.context.quest&&!s.trigger.IsActive()&&!s.action.isUseful()&&!s.action.Execute({}));
    }
    for(auto const& row:ClassQuestSteps) {
        Scenario s(row.Quest,QUEST_STATUS_NONE);
        assert(!s.value.Calculate());
        s.Offer(row.Quest); assert(s.value.Calculate()==row.Quest);
        s.ai.context.quest=s.value.Calculate();
        assert(s.action.Execute({})&&calls.gives==1&&calls.moves==1);
        moveResult=false; assert(!s.action.Execute({}));
        giverResult=true; assert(s.action.Execute({})&&calls.gives==3);
        // Another class never inherits the chain.
        s.bot.cls=row.Class==CLASS_PRIEST?CLASS_WARRIOR:CLASS_PRIEST; assert(s.value.Calculate()!=row.Quest);
        s.bot.cls=CLASS_MAGE; assert(!s.value.Calculate());
    }
    // A rewarded lesson quest ends the lesson even when an era-specific spell record replaced the learned spell.
    for(auto const& row:ClassQuestSteps) if(objectMgr.quests.at(row.Quest).taught) {
        Scenario s(row.Quest,QUEST_STATUS_REWARDED);
        for(auto const& other:ClassQuestSteps) if(other.Class==row.Class&&other.Spell==row.Spell) s.Offer(other.Quest);
        s.bot.quests[row.Quest].Status=QUEST_STATUS_REWARDED; assert(objectMgr.quests.at(row.Quest).taught==row.Spell);
        uint32 const selected=s.value.Calculate();
        assert(!selected||Step(selected)->Spell!=row.Spell);
    }
    // A rewarded step without the lesson reward keeps its chain going.
    { Scenario s(1644,QUEST_STATUS_NONE); s.Offer(1644); s.bot.quests[1643].Status=QUEST_STATUS_REWARDED;
      assert(s.value.Calculate()==1644); s.bot.quests[1644].Status=QUEST_STATUS_REWARDED; assert(!s.value.Calculate()); }
    // The first unearned lesson is completed before a later one.
    { Scenario s(1505,QUEST_STATUS_NONE); s.Offer(1505); s.Offer(1718); givers[1718]={{0,5,0,0}};
      assert(s.value.Calculate()==1505); s.bot.known.insert(71); assert(s.value.Calculate()==1718); }
    { Scenario s(1505,QUEST_STATUS_NONE); s.Offer(1505); s.Offer(1818); givers[1818]={{0,10,0,0}};
      assert(s.value.Calculate()==1818); givers[1818]={{1,1,0,0}}; assert(s.value.Calculate()==1505); }
    { Scenario s(1505,QUEST_STATUS_NONE); s.Offer(1505); s.Offer(1718); s.bot.quests[1498].Status=QUEST_STATUS_INCOMPLETE;
      assert(s.value.Calculate()==1498); }
    { Scenario s(1505,QUEST_STATUS_NONE); s.Offer(1505); sPlayerbotAIConfig.IgnoredQuests.insert(1505); assert(!s.value.Calculate()); }
    { Scenario s(1505,QUEST_STATUS_NONE); s.Offer(1505); s.bot.canAdd=false; assert(!s.value.Calculate()); }
    { Scenario s(1505,QUEST_STATUS_NONE); s.Offer(1505); givers[1505].clear(); assert(!s.value.Calculate()); }
    { Scenario s(1505,QUEST_STATUS_NONE); s.Offer(1505); givers[1505]={{1,0,0,0}}; assert(!s.value.Calculate()); }
    { Scenario s(1786); objectMgr.quests.erase(1786); assert(!s.value.Calculate()); }

    // The owned Tome of Valor starts its quest where the bot stands, through the native item quest giver.
    { Scenario s(1649,QUEST_STATUS_NONE); s.bot.available.insert(1649);
      auto& tome=s.bot.inventory[6776]; tome={6776,77,{1649}}; s.ai.context.startItems.items={&tome};
      s.ai.context.quest=s.value.Calculate(); assert(s.ai.context.quest==1649);
      assert(s.action.Execute({})&&calls.accepts==1&&calls.acceptedFrom==ObjectGuid{77}&&calls.gives==0);
      assert(s.bot.GetQuestStatus(1649)==QUEST_STATUS_INCOMPLETE&&!s.bot.GetItemByEntry(6776)); }
    { Scenario s(1649,QUEST_STATUS_NONE); s.bot.available.insert(1649); acceptRefused=true;
      auto& tome=s.bot.inventory[6776]; tome={6776,77,{1649}}; s.ai.context.startItems.items={&tome};
      assert(!s.action.Execute({})&&calls.accepts==1&&s.bot.GetQuestStatus(1649)==QUEST_STATUS_NONE); }
    { Scenario s(1649,QUEST_STATUS_NONE); auto& tome=s.bot.inventory[6776]; tome={6776,77,{1650}};
      s.ai.context.startItems.items={&tome}; s.bot.available.insert(1649); assert(!s.value.Calculate()); }
    { Scenario s(1649,QUEST_STATUS_NONE); auto& tome=s.bot.inventory[6776]; tome={6776,77,{1649}};
      s.ai.context.startItems.items={&tome}; assert(!s.value.Calculate()); }

    // Failed trials and escorts are abandoned through the native quest log, then offered again.
    for(uint32 quest:{1640u,1651u,1719u,9678u,9686u}) {
        Scenario s(quest,QUEST_STATUS_FAILED); s.ai.context.quest=s.value.Calculate();
        assert(s.ai.context.quest==quest&&s.action.Execute({})&&s.bot.session.removals==1);
        assert(s.bot.GetQuestStatus(quest)==QUEST_STATUS_NONE&&!s.bot.GetQuestRewardStatus(quest));
    }
    { Scenario s(1786,QUEST_STATUS_COMPLETE); rewardResult=true; assert(s.action.Execute({})&&calls.rewards==1&&s.ai.itemUses==0); }

    // Owned quest items are used on their native creature targets.
    for(uint32 quest:{9600u,9684u,9685u}) {
        Scenario s(quest);
        assert(s.action.Execute({})&&s.ai.itemUses==1&&s.ai.usedOn==&s.target&&s.ai.usedItem==s.bot.GetItemByEntry(s.step->Item));
        assert(s.bot.stops==1&&s.ai.waits==0&&calls.objectives==0);
        assert(s.action.Execute({})&&s.ai.itemUses==1&&calls.moves==1&&calls.target==WorldPosition(0,40,0,0));
        now+=60*IN_MILLISECONDS; assert(s.action.Execute({})&&s.ai.itemUses==2);
    }
    { Scenario s(9684); s.bot.useChannel=true; assert(s.action.Execute({})&&s.ai.waitedFor==&s.bot.channel); }
    { Scenario s(9684); s.bot.casting=true; s.ai.context.quest=s.value.Calculate(); assert(!s.ai.context.quest); }
    { Scenario s(9600); s.ai.useResult=false; assert(!s.action.Execute({})&&s.ai.itemUses==1); s.ai.useResult=true;
      assert(s.action.Execute({})&&s.ai.itemUses==2); }
    { Scenario s(9600); s.target.x=20; assert(s.action.Execute({})&&s.ai.itemUses==0&&calls.target==WorldPosition(&s.target)); }
    { Scenario s(9600); s.target.los=false; assert(s.action.Execute({})&&s.ai.itemUses==0&&calls.moves==1); }
    for(auto field:{&WorldObject::inWorld,&WorldObject::sameMap,&WorldObject::samePhase,&WorldObject::visible,&WorldObject::alive}) {
        Scenario s(9600); s.target.*field=false;
        assert(s.action.Execute({})&&s.ai.itemUses==0&&calls.target==WorldPosition(0,40,0,0));
    }
    { Scenario s(9600); s.target.removing=true; assert(s.action.Execute({})&&s.ai.itemUses==0); }
    { Scenario s(9600); s.target.entry=17543; assert(s.action.Execute({})&&s.ai.itemUses==0); }
    { Scenario s(9600); s.ai.context.npcs.clear(); creatureSpawns.clear(); assert(!s.action.Execute({})&&calls.moves==0); }
    { Scenario s(9600); s.ai.context.npcs.clear(); creatureSpawns[0].phaseMask=2; assert(!s.action.Execute({})); }
    { Scenario s(9600); s.ai.context.npcs.clear(); creatureSpawns[0].posX=4;
      assert(!s.action.Execute({})&&calls.moves==0&&spawnScans==1); assert(!s.action.Execute({})&&spawnScans==1);
      now+=60*IN_MILLISECONDS; assert(!s.action.Execute({})&&spawnScans==2); }
    // A consumed source item is replaced only by abandoning and accepting the step again.
    for(uint32 quest:{9600u,9684u,9685u,9582u}) {
        Scenario s(quest); s.bot.inventory.clear();
        assert(s.action.Execute({})&&s.bot.session.removals==1&&s.bot.GetQuestStatus(quest)==QUEST_STATUS_NONE);
    }
    { Scenario s(9600); s.bot.inventory.clear(); s.bot.bank[6866]=1; assert(!s.action.Execute({})&&s.bot.session.removals==0); }
    { Scenario s(1786); s.bot.inventory.clear(); assert(!s.action.Execute({})&&s.bot.session.removals==0); }

    // Henze and Narm Faulk: the owned Symbol of Life revives the dormant quest taker before the native turn-in.
    for(uint32 quest:{1786u,1783u}) {
        Scenario s(quest,QUEST_STATUS_COMPLETE);
        assert(s.action.Execute({})&&calls.rewards==1&&s.ai.itemUses==1&&s.ai.usedOn==&s.target&&calls.moves==0);
        s.target.questgiver=true; rewardResult=true; assert(s.action.Execute({})&&calls.rewards==2&&s.ai.itemUses==1);
    }
    { Scenario s(1786,QUEST_STATUS_COMPLETE); s.target.finishes.clear(); assert(s.action.Execute({})&&s.ai.itemUses==0&&calls.moves==1); }
    { Scenario s(1786,QUEST_STATUS_COMPLETE); s.target.questgiver=true; assert(s.action.Execute({})&&s.ai.itemUses==0&&calls.moves==1); }
    { Scenario s(1786,QUEST_STATUS_COMPLETE); s.bot.inventory.clear(); assert(s.action.Execute({})&&calls.moves==1&&s.bot.session.removals==0); }
    { Scenario s(9600,QUEST_STATUS_COMPLETE); s.target.finishes.clear(); assert(s.action.Execute({})&&s.ai.itemUses==0&&calls.moves==1); }
    { Scenario s(1786); assert(s.action.Execute({})&&s.ai.itemUses==1); }

    // Native quest objects: the mausoleum, ravager cage, gilded brazier and Second Trial harbinger.
    for(uint32 quest:{1819u,9582u,9678u,9686u}) {
        Scenario s(quest);
        assert(s.action.Execute({})&&s.bot.stops==1&&s.ai.usedObject==ObjectGuid{3});
        assert(s.step->Item?(s.ai.itemUses==1&&s.ai.objectUses==0&&s.ai.usedItem==s.bot.GetItemByEntry(s.step->Item))
                           :(s.ai.itemUses==0&&s.ai.objectUses==1));
        s.bot.x=-2;
        assert(s.action.Execute({})&&s.ai.itemUses+s.ai.objectUses==1&&calls.moves==1&&calls.target==WorldPosition(&s.object));
        s.bot.x=2; assert(s.action.Execute({})&&calls.moves==1);
        now+=60*IN_MILLISECONDS; assert(s.action.Execute({})&&s.ai.itemUses+s.ai.objectUses==2);
    }
    for(uint32 quest:{9678u,9582u}) { Scenario s(quest); s.ai.startsCast=true; assert(s.action.Execute({})&&s.ai.waitedFor==&s.bot.generic); }
    { Scenario s(1819); assert(s.action.Execute({})&&s.ai.waits==0); }
    { Scenario s(1819); s.ai.useResult=false; assert(!s.action.Execute({})); s.ai.useResult=true; assert(s.action.Execute({})&&s.ai.objectUses==2); }
    { Scenario s(1819); s.object.x=20; assert(s.action.Execute({})&&s.ai.objectUses==0&&calls.target==WorldPosition(&s.object)); }
    { Scenario s(1819); s.object.los=false; assert(s.action.Execute({})&&s.ai.objectUses==0&&calls.moves==1); }
    for(auto field:{&WorldObject::inWorld,&WorldObject::sameMap,&WorldObject::samePhase,&WorldObject::visible}) {
        Scenario s(1819); s.object.*field=false; assert(s.action.Execute({})&&s.ai.objectUses==0&&calls.target==WorldPosition(0,40,0,0));
    }
    { Scenario s(1819); s.object.spawned=false; assert(s.action.Execute({})&&s.ai.objectUses==0); }
    { Scenario s(1819); s.object.entry=104594; assert(s.action.Execute({})&&s.ai.objectUses==0); }
    { Scenario s(9582); s.bot.inventory.clear(); s.bot.bank[23925]=1; assert(!s.action.Execute({})&&s.ai.itemUses==0); }
    // A released or summoned objective is fought through ordinary combat instead of using the object again.
    for(uint32 quest:{1819u,9582u,9678u}) {
        Scenario s(quest); s.target.entry=uint32(objectMgr.quests.at(quest).RequiredNpcOrGo[0]); s.target.questgiver=true;
        assert(s.action.Execute({})&&s.ai.attacks==1&&s.ai.attacked==&s.target&&s.ai.objectUses+s.ai.itemUses==0);
        s.target.los=false; assert(s.action.Execute({})&&s.ai.attacks==1&&calls.target==WorldPosition(&s.target));
        s.target.los=true; s.target.attackable=false; assert(s.action.Execute({})&&s.ai.objectUses+s.ai.itemUses==1);
    }
    { Scenario s(1819); s.target.entry=6390; s.bot.quests[1819].CreatureOrGOCount[0]=1;
      assert(s.action.Execute({})&&s.ai.attacks==0&&s.ai.objectUses==1); }
    { Scenario s(1819); s.target.entry=6390; s.target.alive=false; assert(s.action.Execute({})&&s.ai.attacks==0&&s.ai.objectUses==1); }
    { Scenario s(1819); s.target.entry=6390; s.target.samePhase=false; assert(s.action.Execute({})&&s.ai.attacks==0); }
    { Scenario s(1819); s.target.entry=6390; s.ai.attackResult=false; assert(!s.action.Execute({})&&s.ai.objectUses==0); }

    // The Affray waits on Twiggy Flathead's grate; a stalled native event is abandoned after five idle minutes.
    { Scenario s(1719);
      assert(s.action.Execute({})&&calls.moves==1&&calls.target==WorldPosition(1,-1681.0f,-4327.0f,2.79f));
      s.bot.mapId=1; s.bot.x=-1681; s.bot.y=-4327; s.bot.z=2.79f;
      for(int i=0;i<30;++i) { assert(s.action.Execute({})&&s.bot.session.removals==0); now+=10*IN_MILLISECONDS; }
      assert(s.action.Execute({})&&s.bot.session.removals==1&&s.bot.GetQuestStatus(1719)==QUEST_STATUS_NONE&&calls.moves==1); }
    { Scenario s(1719); s.bot.mapId=1; s.bot.x=-1681; s.bot.y=-4327; s.bot.z=2.79f;
      for(int i=0;i<40;++i) { assert(s.action.Execute({})&&s.bot.session.removals==0); now+=11*IN_MILLISECONDS; } }
    { Scenario s(1719); s.bot.mapId=1; s.bot.x=-1678.5f; s.bot.y=-4327; s.bot.z=2.79f; assert(s.action.Execute({})&&calls.moves==0);
      s.bot.x=-1677.5f; assert(s.action.Execute({})&&calls.moves==1); }
    { Scenario s(1719,QUEST_STATUS_FAILED); s.bot.session.removeFails=true; assert(!s.action.Execute({})&&s.bot.session.removals==1); }
    { Scenario s(1719); moveResult=false; assert(!s.action.Execute({})); }
    // Escorted and baiting creatures: Bartleby's fight and Daphne Stilwell's raiders.
    { Scenario s(1651); s.target.questgiver=true; s.target.x=6;
      assert(s.action.Execute({})&&calls.moves==1&&calls.target==WorldPosition(&s.target));
      s.target.attackers.insert(&s.raider); assert(s.action.Execute({})&&s.ai.attacks==1&&s.ai.attacked==&s.raider);
      s.raider.attackable=false; assert(s.action.Execute({})&&s.ai.attacks==1&&calls.moves==2); }
    for(auto field:{&WorldObject::alive,&WorldObject::samePhase,&WorldObject::visible,&WorldObject::los}) {
        Scenario s(1651); s.target.attackers.insert(&s.raider); s.raider.*field=false;
        assert(s.action.Execute({})&&s.ai.attacks==0);
    }
    { Scenario s(1651); s.ai.context.npcs.clear(); assert(s.action.Execute({})&&calls.target==WorldPosition(0,40,0,0)); }
    { Scenario s(1640); s.target.x=2.5f; s.bot.x=0;
      for(int i=0;i<30;++i) { assert(s.action.Execute({})&&calls.moves==0); now+=10*IN_MILLISECONDS; }
      assert(s.action.Execute({})&&s.bot.session.removals==1); }
    // Steps without a native interaction use the ordinary objectives; non-event waits never abandon.
    { Scenario s(1787); assert(s.action.Execute({})&&calls.objectives==1); objectiveResult=false; assert(!s.action.Execute({})); }
    { Scenario s(1640); objectMgr.quests.at(1640).special=0; s.target.x=2.5f;
      for(int i=0;i<40;++i) { assert(s.action.Execute({})&&s.bot.session.removals==0); now+=10*IN_MILLISECONDS; } }

    auto rejected=[](auto change) {
        Scenario s; change(s);
        assert(!s.value.Calculate()&&!s.trigger.IsActive()&&!s.action.isUseful());
        assert(!s.action.Execute({})&&s.ai.itemUses==0&&calls.moves==0&&s.bot.session.removals==0);
    };
    rejected([](auto&){sPlayerbotAIConfig.naturalProgression=false;});
    rejected([](auto& s){s.ai.bot=nullptr;});
    rejected([](auto& s){s.bot.hasSession=false;});
    rejected([](auto& s){s.bot.session.headless=false;});
    rejected([](auto& s){s.bot.random=false;});
    rejected([](auto& s){s.ai.master=true;});
    rejected([](auto& s){s.bot.group=true;});
    rejected([](auto& s){s.bot.alive=false;});
    rejected([](auto& s){s.bot.inWorld=false;});
    rejected([](auto& s){s.bot.teleport=true;});
    rejected([](auto& s){s.bot.map.dungeon=true;});
    rejected([](auto& s){s.bot.battleground=true;});
    rejected([](auto& s){s.bot.arena=true;});
    rejected([](auto& s){s.bot.combat=true;});
    rejected([](auto& s){s.bot.mounted=true;});
    rejected([](auto& s){s.bot.flight=true;});
    rejected([](auto& s){s.bot.flying=true;});
    rejected([](auto& s){s.bot.transport=true;});
    rejected([](auto& s){s.bot.vehicle=true;});
    rejected([](auto& s){s.bot.lostControl=true;});
    rejected([](auto& s){s.bot.casting=true;});
}
'''

mutations = [
    ('own class chain required', 'current', 'if (step.Class != bot->getClass())', 'if (false)'),
    ('learned lesson skipped', 'namespace', 'if (bot->HasSpell(spell))', 'if (false)'),
    ('rewarded lesson quest ends chain', 'namespace', 'bot->GetQuestRewardStatus(step.Quest))\n', 'false)\n'),
    ('only lesson rewards end chain', 'namespace', 'quest && (quest->GetRewSpell() || quest->GetRewSpellCast())', 'quest'),
    ('first unearned lesson kept', 'current', 'if (selected)\n                return selected;', ''),
    ('ignored quest skipped', 'current', 'sPlayerbotAIConfig.IgnoredQuests.count(step.Quest)', 'false'),
    ('own native quest access required', 'current', '!bot->CanTakeQuest(quest, false)', 'false'),
    ('own quest log capacity required', 'current', '!bot->CanAddQuest(quest, false)', 'false'),
    ('nearest native giver selected', 'current', 'costs->Cost(pos) < nearest', 'costs->Cost(pos) <= nearest && !selected'),
    ('reachable giver required', 'current', 'pos != WorldPosition() && ', ''),
    ('own start item matched to quest', 'namespace', 'item->GetTemplate()->StartQuest == questId', 'true'),
    ('own start item offered to native handler', 'execute', 'AcceptQuest(quest, item->GetGUID())', 'AcceptQuest(quest, item ? ObjectGuid() : ObjectGuid())'),
    ('item acceptance result rechecked', 'execute',
     'AcceptQuest(quest, item->GetGUID()) && bot->GetQuestStatus(step->Quest) != QUEST_STATUS_NONE',
     'AcceptQuest(quest, item->GetGUID())'),
    ('failed quest abandoned', 'execute', 'if (status == QUEST_STATUS_FAILED)\n        return Abandon(step->Quest);', ''),
    ('quest taker revived only on completion', 'execute', 'step->Item && step->Target > 0 && UseOnCreature(quest, *step)',
     'false'),
    ('the Affray waits on the grate', 'execute', 'return Wait(quest, AffrayGrate);', 'return DoObjectives(quest);'),
    ('owned item required', 'creature', 'if (!item)\n        return !revive && Restart(quest, step.Item);',
     'if (!item)\n        return false;'),
    ('target entry matched', 'creature', 'creature->GetEntry() != uint32(step.Target) ||', ''),
    ('living target required', 'creature', '!creature->IsAlive() ||', ''),
    ('removed target skipped', 'creature', 'creature->IsDuringRemoveFromWorld() ||', ''),
    ('usable target required', 'creature', '|| !Usable(bot, creature))\n            continue;\n        // Henze',
     ')\n            continue;\n        // Henze'),
    ('only dormant taker revived', 'creature', '|| creature->HasNpcFlag(UNIT_NPC_FLAG_QUESTGIVER)', ''),
    ('only own quest taker revived', 'creature', '!creature->hasInvolvedQuest(quest->GetQuestId()) ||', ''),
    ('used target rested', 'creature', 'GetMSTimeDiffToNow(used->second) < MINUTE * IN_MILLISECONDS', 'false'),
    ('used target recorded', 'creature', '_usedTargets[target->GetSpawnId()] = getMSTime();', ''),
    ('target range required', 'creature', '!target->IsWithinDistInMap(bot, INTERACTION_DISTANCE) || ', ''),
    ('target line of sight required', 'creature', ' || !bot->IsWithinLOSInMap(target))', ')'),
    ('item use result checked', 'creature', 'if (!UseItemAction(botAI).UseItemOnUnit(item, target))\n        return false;',
     'UseItemAction(botAI).UseItemOnUnit(item, target);'),
    ('channel waited', 'creature', 'Spell* cast = bot->GetCurrentSpell(CURRENT_CHANNELED_SPELL);',
     'Spell* cast = nullptr;'),
    ('spawn phase required', 'spawn', 'if (!(spawn->phaseMask & bot->GetPhaseMask()))', 'if (false)'),
    ('spawn search cached', 'spawn', 'GetMSTimeDiffToNow(_spawnChecked) < MINUTE * IN_MILLISECONDS', 'false'),
    ('owned key required', 'object', 'if (step.Item && !item)\n        return Restart(quest, step.Item);', ''),
    ('only needed objective fought', 'object', '&&\n                ClassQuestObjectiveNeeded(bot, quest, index))', ')'),
    ('only attackable objective fought', 'object', '|| !bot->IsValidAttackTarget(creature))', ')'),
    ('living objective required', 'object', '!creature->IsAlive() || ', ''),
    ('objective usable required', 'object', '!Usable(bot, creature) || ', ''),
    ('used object not repeated', 'object', '_usedAt && GetMSTimeDiffToNow(_usedAt) < MINUTE * IN_MILLISECONDS', 'false'),
    ('object entry matched', 'object', 'object->GetEntry() != uint32(-step.Target) || ', ''),
    ('spawned object required', 'object', '!object->isSpawned() || ', ''),
    ('object usable required', 'object', ' || !Usable(bot, object))\n            continue;', ')\n            continue;'),
    ('object range required', 'object', '!object->IsWithinDistInMap(bot, INTERACTION_DISTANCE) || ', ''),
    ('object use result checked', 'object',
     'if (!(item ? use.UseItemOnGameObject(item, guid) : use.UseGameObject(guid)))\n            return false;',
     'item ? use.UseItemOnGameObject(item, guid) : use.UseGameObject(guid);'),
    ('object key used on object', 'object', 'item ? use.UseItemOnGameObject(item, guid) : use.UseGameObject(guid)',
     'use.UseGameObject(guid)'),
    ('escort attackers defended', 'stay', 'ClassQuestAttack(botAI, "class quest attack").Attack(attacker))', 'false)'),
    ('escort attacker usable', 'stay', 'Usable(bot, attacker) && ', ''),
    ('wait distance kept', 'wait', 'bot->GetExactDist(pos) > WaitDistance', 'false'),
    ('only event quests abandoned', 'wait', '!quest->HasSpecialFlag(QUEST_SPECIAL_FLAGS_EXPLORATION_OR_EVENT) ||', ''),
    ('stall clock restarted after combat', 'wait', ' || GetMSTimeDiffToNow(_waitLast) > 10 * IN_MILLISECONDS', ''),
    ('stall duration respected', 'wait', 'GetMSTimeDiffToNow(_waitSince) < StalledEventMs', 'false'),
    ('only own source item restored', 'restart', 'quest->GetSrcItemId() != itemId || ', ''),
    ('banked item kept', 'restart', ' || bot->HasItemCount(itemId, 1, true)', ''),
    ('abandon result rechecked', 'abandon', 'return bot->GetQuestStatus(questId) == QUEST_STATUS_NONE;', 'return true;'),
]
for label, predicate in (
        ('earned play mode', 'sPlayerbotAIConfig.naturalProgression'),
        ('headless session', 'bot->GetSession()->IsHeadless()'),
        ('random ownership', 'sRandomPlayerbotMgr.IsRandomBot(bot)'),
        ('no human controller', '!botAI->GetMaster()'),
        ('solo character', '!bot->GetGroup()'),
        ('living character', 'bot->IsAlive()'),
        ('character in world', 'bot->IsInWorld()'),
        ('no teleport in progress', '!bot->IsBeingTeleported()'),
        ('outside instance', '!bot->GetMap()->IsDungeon()'),
        ('outside battleground', '!bot->InBattleground()'),
        ('outside arena', '!bot->InArena()'),
        ('outside combat', '!bot->IsInCombat()'),
        ('unmounted character', '!bot->IsMounted()'),
        ('no flight path', '!bot->IsInFlight()'),
        ('no flying character', '!bot->IsFlying()'),
        ('no moving transport', '!bot->GetTransport()'),
        ('no vehicle', '!bot->GetVehicle()'),
        ('own control', '!bot->HasUnitState(UNIT_STATE_LOST_CONTROL)'),
        ('no overlapping cast', '!bot->IsNonMeleeSpellCast(true)')):
    mutations.append((label, 'gate', predicate, 'true'))
for label, key, old, _ in mutations:
    assert production[key].count(old) == 1, label


def build(directory, parts, name):
    text = prelude + tests
    for key, value in parts.items():
        text = text.replace('@@' + key.upper() + '@@', value)
    assert '@@' not in text
    path = directory / (name + '.cpp')
    path.write_text(text)
    binary = directory / name
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-missing-field-initializers',
                    '-Wno-unused-parameter', *SANITIZER_FLAGS, str(path), '-o', str(binary)], check=True)
    return run_fixture([str(binary)])


with tempfile.TemporaryDirectory(prefix='portable-class-quest-chains-') as temporary:
    directory = Path(temporary)
    result = build(directory, production, 'chains')
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit('Class quest chain fixture failed')

    def rejected(numbered):
        index, (_label, key, old, new) = numbered
        mutant = {**production, key: production[key].replace(old, new)}
        return build(directory, mutant, f'mutant-{index}').returncode != 0

    for (label, *_), rejected_mutant in zip(mutations, in_parallel(rejected, enumerate(mutations))):
        if not rejected_mutant:
            raise SystemExit('Class quest chain mutation survived: ' + label)
        print('Class quest chain mutation rejected: ' + label)
