"""Exercise native Shaman totem chains, owned Sapta and water rituals.

The shared class-quest fixture covers ownership, NPC/object interactions and
travel. This fixture executes the Shaman selector and special steps against
native quest, item, spell-focus and scripted-event contracts.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    cxx,
    function,
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
shaman = module / 'Ai/Class/Shaman'
source = (shaman / 'ShamanTotemQuests.cpp').read_text()
header = (shaman / 'ShamanTotemQuests.h').read_text()

families = {
    5175: {1516, 1517, 1518, 1519, 1520, 1521, 1462, 1463},
    5176: {1522, 1523, 1524, 1525, 1526, 1527, 2983, 2984, 1464},
    5177: {63, 96, 100, 220, 972, 1103, 1528, 1529, 1530, 1534, 1535, 1536, 2985, 2986},
    5178: {1531, 1532},
}
expected_quests = {quest: totem for totem, quests in families.items() for quest in quests}
assert len(expected_quests) == 33
quests = {int(row['ID']): row for row in sql_rows(core, 'quest_template', set(expected_quests))}
addons = {int(row['ID']): row for row in sql_rows(core, 'quest_template_addon', set(expected_quests))}
for quest, row in quests.items():
    assert int(addons[quest]['AllowableClasses']) == 64, quest
    previous = abs(int(addons[quest]['PrevQuestID']))
    if previous:
        assert previous in expected_quests, (quest, previous)
        assert expected_quests[quest] == expected_quests[previous]
    next_quest = int(row['RewardNextQuest']) or int(addons[quest]['NextQuestID'])
    if next_quest:
        assert next_quest in expected_quests, (quest, next_quest)
        assert expected_quests[quest] == expected_quests[next_quest]

for quest, totem in ((1518, 5175), (1521, 5175), (1527, 5176), (96, 5177), (1531, 5178), (1532, 5178)):
    assert int(quests[quest]['RewardItem1']) == totem
    assert int(quests[quest]['RewardAmount1']) == 1
assert {int(quests[quest]['RewardSpell']) for quest in (1531, 1532)} == {8385}

# The first Earth journey completes on acceptance; visibility remains a separate
# owned-item step before speaking to the spirit.
for quest in (1517, 1520):
    assert not any(int(quests[quest][field + str(index)])
                   for field, count in (('RequiredNpcOrGo', 4), ('RequiredItemId', 6))
                   for index in range(1, count + 1))
    assert int(quests[quest]['StartItem']) == 6635
ip_sql = core / 'modules/mod-individual-progression/data/sql/world/base'
for zone, quest in (('zone_durotar', 1517), ('zone_mulgore', 1520)):
    restoration = re.sub(r'--[^\n]*', '', (ip_sql / (zone + '.sql')).read_text())
    groups = re.findall(r'UPDATE `quest_template_addon` SET `SpecialFlags`\s*=\s*0 WHERE `ID` IN \(([^;]+)\)', restoration)
    assert any(quest in map(int, group.split(',')) for group in groups)

sapta_items = {6635: 8202, 6636: 8898, 6637: 8899}
water_items = {7766: (9586, 7769, 224), 7768: (9583, 7771, 226), 7767: (9584, 7770, 223)}
items = {int(row['entry']): row for row in sql_rows(core, 'item_template', set(sapta_items) | set(water_items))}
for item, spell in {**sapta_items, **{item: row[0] for item, row in water_items.items()}}.items():
    assert int(items[item]['spellid_1']) == spell
    assert int(items[item]['spelltrigger_1']) == 0
    assert int(items[item]['spellcharges_1']) == -1
for quest, item in ((1535, 7766), (1536, 7768), (1534, 7767)):
    assert int(quests[quest]['StartItem']) == item
    assert int(quests[quest]['RequiredItemId1']) == water_items[item][1]
for quest, sapta in ((972, 6637), (1462, 6635), (1463, 6635), (1464, 6636)):
    assert int(addons[quest]['SpecialFlags']) & 1
    assert int(quests[quest]['QuestType']) == 0
    assert int(quests[quest]['RewardItem1']) == sapta
    assert int(quests[quest]['RewardAmount1']) == 1
assert not int(addons[1103]['SpecialFlags']) & 1
assert int(quests[1103]['StartItem']) == 0
assert int(quests[1103]['RequiredItemId1']) == 6637
assert int(quests[1103]['RequiredItemCount1']) == 1

# These fields are read from the native Spell.dbc into SpellInfo; the adapter
# exercises the runtime value, including a non-historical focus ID.
dbc = (core / 'src/server/shared/DataStores/DBCStructure.h').read_text()
assert re.search(r'uint32\s+RequiresSpellFocus;\s*// 18', dbc)
spell_info = (core / 'src/server/game/Spells/SpellInfo.cpp').read_text()
assert 'RequiresSpellFocus = spellEntry->RequiresSpellFocus;' in spell_info
focuses = sql_rows(core, 'gameobject_template', {63674, 100035, 107045, 107046, 107047})
assert {(int(row['entry']), int(row['type']), int(row['Data0']), int(row['Data1'])) for row in focuses} == {
    (63674, 8, 63, 50), (100035, 8, 63, 10), (107045, 8, 226, 5), (107046, 8, 224, 25),
    (107047, 8, 223, 5)}
assert {int(row['Data3']) for row in focuses if int(row['entry']) in (107045, 107046, 107047)} == {1}
go_source = (core / 'src/server/game/Entities/GameObject/GameObject.cpp').read_text()
assert 'spellFocus.serverOnly == 1' in function(go_source, 'bool GameObject::IsNeverVisible()')

events = {(int(row['entryorguid']), int(row['source_type']), int(row['id'])): row
          for row in sql_rows(core, 'smart_scripts', {7007, 700700, 113791, 11379100})}
for key, fields in {
    (113791, 1, 0): {'event_type': 20, 'event_param1': 63, 'action_type': 80, 'action_param1': 11379100},
    (11379100, 9, 1): {'event_param1': 15000, 'event_param2': 15000, 'action_type': 70},
    (11379100, 9, 2): {'action_type': 12, 'action_param1': 5895, 'action_param2': 3,
                       'action_param3': 180000, 'target_type': 8},
    (7007, 0, 0): {'event_type': 20, 'event_param1': 1103, 'action_type': 80, 'action_param1': 700700},
    (700700, 9, 1): {'event_param1': 15000, 'event_param2': 15000, 'action_type': 12,
                     'action_param1': 5895, 'action_param2': 3, 'action_param3': 180000},
}.items():
    assert all(int(events[key][field]) == expected for field, expected in fields.items()), key

table = function(source, 'namespace\n')
totem_names = {'EarthTotem': 5175, 'FireTotem': 5176, 'WaterTotem': 5177, 'AirTotem': 5178}
chains = {int(quest): totem_names[totem] for quest, totem in re.findall(
    r'\{(\d+),\s*(EarthTotem|FireTotem|WaterTotem|AirTotem)\}', table)}
assert chains == expected_quests
assert 'CalculatedValue<uint32>(botAI, "shaman totem quest", 5)' in header
assert 'Trigger(botAI, "shaman totem quest")' in header
for forbidden in ('bot->AddQuest(', 'bot->RewardQuest(', 'CompleteQuest(', 'AreaExploredOrEventHappens(',
                  'learnSpell(', 'SummonCreature(', 'AddItem(', 'TeleportTo('):
    assert forbidden not in source, forbidden

item_source = (module / 'Ai/Base/Actions/UseItemAction.cpp').read_text()
item_cast = function(item_source, 'bool UseItemAction::UseItem(Item* item, ObjectGuid goGuid, Item* itemTarget, Unit* unitTarget)')
native_focus = function((core / 'src/server/game/Grids/Notifiers/GridNotifiers.h').read_text(),
                       'class GameObjectFocusCheck') + ';'
assert 'bot->GetSession()->HandleUseItemOpcode(packet);' in item_cast
native_cast = function((module / 'Bot/PlayerbotAI.cpp').read_text(), 'bool PlayerbotAI::CanCastSpell(uint32 spellid, Unit*')
assert 'spell->m_CastItem = castItem;' in native_cast
assert 'SpellCastResult result = spell->CheckCast(true);' in native_cast
native_spell = (core / 'src/server/game/Spells/Spell.cpp').read_text()
assert 'castResult = CheckSpellFocus();' in function(native_spell, 'SpellCastResult Spell::CheckCast(')
assert 'GameObjectFocusCheck go_check(m_caster, m_spellInfo->RequiresSpellFocus);' in function(
    native_spell, 'SpellCastResult Spell::CheckSpellFocus()')
nearest_objects = function((module / 'Ai/Base/Value/NearestGameObjects.cpp').read_text(),
                           'GuidVector NearestGameObjects::Calculate()')
nearest_check = function((module / 'Ai/Base/Value/NearestGameObjects.h').read_text(),
                         'class AnyGameObjectInObjectRangeCheck')
assert 'result.push_back(go->GetGUID());' in nearest_objects
assert 'u->isSpawned() && u->GetGOInfo()' in nearest_check
assert 'CanSeeOrDetect' not in nearest_objects + nearest_check
native_worldobject = (core / 'src/server/game/Entities/Object/Object.cpp').read_text()
assert 'IsInMap(obj) && InSamePhase(obj) && _IsWithinDist(' in function(
    native_worldobject, 'bool WorldObject::IsWithinDistInMap(')
native_distance = function(native_worldobject, 'bool WorldObject::_IsWithinDist(')
assert 'maxdist += GetObjectSize();' in native_distance
assert 'maxdist += obj->GetObjectSize();' in native_distance
native_take = function((core / 'src/server/game/Entities/Player/PlayerQuest.cpp').read_text(), 'bool Player::CanTakeQuest(')
assert 'SatisfyQuestConditions(quest, msg)' in native_take
native_remove = function((core / 'src/server/game/Handlers/QuestHandler.cpp').read_text(),
                         'void WorldSession::HandleQuestLogRemoveQuest(')
assert 'packet.Slot < MAX_QUEST_LOG_SIZE' in native_remove
assert '_player->AbandonQuest(questId);' in native_remove
native_objects = function((module / 'Mgr/Travel/TravelMgr.cpp').read_text(),
                          'void FindPointGameObjectData::operator()(')
assert '(!point || gameobjectData.mapid == point.GetMapId())' in native_objects

scheduler_header = (core / 'src/common/Utilities/TaskScheduler.h').read_text()
scheduler_source = (core / 'src/common/Utilities/TaskScheduler.cpp').read_text()
assert 'typedef std::chrono::steady_clock clock_t;' in scheduler_header
assert '_now = clock_t::now();' in function(scheduler_source, 'TaskScheduler& TaskScheduler::Update(success_t const&')
assert 'return ScheduleAt(_now, time, task);' in scheduler_header
# Replace only the wall-clock provider. Native scheduling, dispatch and cancellation
# still execute, while tests can advance time without sleeping for a ritual.
scheduler = re.sub(r'^#include "[^"\n]+"\n', '', scheduler_header + scheduler_source, flags=re.MULTILINE)
scheduler = scheduler.replace('typedef std::chrono::steady_clock clock_t;', 'typedef TestClock clock_t;')

production = {
    'table': table,
    'classes': '\n'.join(function(header, name) + ';' for name in (
        'struct ShamanTotemQuest', 'class ShamanTotemQuestValue',
        'class ShamanTotemQuestTrigger', 'class ShamanTotemQuestAction')),
    'current': function(source, 'ShamanTotemQuest const* CurrentShamanTotemQuest('),
    'value': function(source, 'uint32 ShamanTotemQuestValue::Calculate()'),
    'trigger': function(source, 'bool ShamanTotemQuestTrigger::IsActive()'),
    'useful': function(source, 'bool ShamanTotemQuestAction::isUseful()'),
    'execute': function(source, 'bool ShamanTotemQuestAction::Execute('),
    'focused': function(source, 'bool ShamanTotemQuestAction::UseFocusedQuestItem('),
    'reset': function(source, 'void ShamanTotemQuestAction::ResetWaterWait('),
    'water': function(source, 'bool ShamanTotemQuestAction::WaitForWaterSpirit('),
    'restart': function(source, 'bool ShamanTotemQuestAction::RestartWaterQuest('),
    'wrapper': function(item_source, 'bool UseItemAction::UseItemOnUnit('),
    'precheck': function(item_cast, '    for (uint8 i = 0; i < spellSlotLimit; ++i)'),
    'focuscheck': native_focus,
    'scheduler': scheduler,
}

native_quests = []
for quest, row in quests.items():
    fields = [str(quest), row['StartItem'], str(expected_quests[quest]),
              'true' if int(addons[quest]['SpecialFlags']) & 1 else 'false']
    for field, count in (('RequiredNpcOrGo', 4), ('RequiredNpcOrGoCount', 4),
                         ('RequiredItemId', 6), ('RequiredItemCount', 6)):
        fields.append('{' + ','.join(row[field + str(index + 1)] for index in range(count)) + '}')
    fields.append('{' + ','.join(row['RewardItem' + str(index)] for index in range(1, 5)) + '}')
    native_quests.append('Quest{' + ','.join(fields) + '}')
production['nativequests'] = ('for(Quest const& q : {' + ',\n'.join(native_quests)
                             + '}) objectMgr.quests.emplace(q.id,q);')
production['items'] = '\n'.join(
    f'objectMgr.items[{item}].Spells[0].SpellId={row["spellid_1"]};' for item, row in items.items())
relations = {}
for name in ('creature_queststarter', 'creature_questender', 'gameobject_queststarter', 'gameobject_questender'):
    raw = (core / f'data/sql/base/db_world/{name}.sql').read_text()
    assert re.findall(r'^  `([^`]+)`', raw, re.MULTILINE) == ['id', 'quest']
    relations[name] = {(int(entry), int(quest)) for entry, quest in re.findall(r'^\((\d+),(\d+)\)[,;]$', raw, re.MULTILINE)
                       if int(quest) in expected_quests}
assert (61934, 1526) in relations['gameobject_questender']
assert (61934, 1527) in relations['gameobject_queststarter']
assert (113791, 63) in relations['gameobject_questender']
assert (113791, 100) in relations['gameobject_queststarter']
for quest, entry in ((972, 5901), (1462, 5888), (1463, 5887), (1464, 5900), (1103, 7007)):
    assert (entry, quest) in relations['creature_queststarter']
    assert (entry, quest) in relations['creature_questender']
production['relations'] = '\n'.join(
    'std::multimap<uint32,uint32> ' + name + '={' + ','.join(
        '{' + str(entry) + ',' + str(quest) + '}' for entry, quest in sorted(rows)) + '};'
    for name, rows in relations.items())

prelude = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <optional>
#include <queue>
#include <set>
#include <string>
#include <type_traits>
#include <unordered_map>
#include <variant>
#include <vector>
using uint8=uint8_t; using uint16=uint16_t; using uint32=uint32_t; using int32=int32_t;
using Milliseconds=std::chrono::milliseconds;
constexpr uint32 CLASS_SHAMAN=7, CLASS_WARLOCK=9, IN_MILLISECONDS=1000, MINUTE=60;
constexpr uint32 QUEST_OBJECTIVES_COUNT=4, QUEST_ITEM_OBJECTIVES_COUNT=6, MAX_QUEST_LOG_SIZE=25;
constexpr uint32 CURRENT_CHANNELED_SPELL=1,CURRENT_GENERIC_SPELL=2,GAMEOBJECT_TYPE_SPELL_FOCUS=8;
constexpr uint32 CMSG_QUESTLOG_REMOVE_QUEST=1;
constexpr float INTERACTION_DISTANCE=5.0f;
enum QuestStatus { QUEST_STATUS_NONE,QUEST_STATUS_INCOMPLETE,QUEST_STATUS_COMPLETE,QUEST_STATUS_REWARDED };
uint32 now=100000;
uint32 getMSTime(){return now;}
uint32 GetMSTimeDiffToNow(uint32 value){return now-value;}
uint32 urand(uint32 low,uint32){return low;}
#define ASSERT(value) assert(value)
struct TestClock {
    using duration=std::chrono::milliseconds;
    using rep=duration::rep; using period=duration::period;
    using time_point=std::chrono::time_point<TestClock>;
    static constexpr bool is_steady=true;
    static time_point now(){return time_point(duration(::now));}
};
@@SCHEDULER@@
struct ObjectGuid { uint32 value=0; explicit operator bool()const{return value!=0;}
    bool operator==(ObjectGuid const&)const=default; static ObjectGuid Empty; };
ObjectGuid ObjectGuid::Empty;
using GuidVector=std::vector<ObjectGuid>;
struct Event{}; struct Player; struct Creature; struct GameObject; struct WorldPosition;
struct Spell{};
struct ItemTemplate { struct Slot{int32 SpellId=0;} Spells[5]; };
struct Item { uint32 entry=0,count=1; ItemTemplate proto; ItemTemplate const* GetTemplate()const{return &proto;} };
struct Quest {
    uint32 id=0,source=0,totem=0; bool repeatable=false;
    std::array<int32,4> RequiredNpcOrGo{};
    std::array<uint32,4> RequiredNpcOrGoCount{};
    std::array<uint32,6> RequiredItemId{},RequiredItemCount{};
    std::array<uint32,4> RewardItem{};
    uint32 GetQuestId()const{return id;} uint32 GetSrcItemId()const{return source;}
    bool IsRepeatable()const{return repeatable;}
};
struct WorldObject {
    uint32 entry=1,guid=1,mapId=1,phaseMask=1; float x=2,y=0,z=0,size=.5f;
    bool inWorld=true,spawned=true,visible=true,los=true,alive=true;
    virtual ~WorldObject()=default;
    uint32 GetEntry()const{return entry;} ObjectGuid GetGUID()const{return {guid};}
    uint32 GetMapId()const{return mapId;} bool IsInWorld()const{return inWorld;}
    bool IsAlive()const{return alive;}
    bool IsWithinDistInMap(WorldObject const* other,float distance)const {
        float maximum=distance+size+other->size,dx=x-other->x,dy=y-other->y,dz=z-other->z;
        return mapId==other->mapId&&(phaseMask&other->phaseMask)&&dx*dx+dy*dy+dz*dz<maximum*maximum;
    }
    float GetExactDist(WorldPosition const&)const;
};
struct Unit:WorldObject { virtual Creature* ToCreature(){return nullptr;} };
struct Creature:Unit {
    bool removing=false; std::set<uint32> starts,ends; uint32 requiresAura=0;
    Creature* ToCreature()override{return this;}
    bool IsDuringRemoveFromWorld()const{return removing;}
    bool hasQuest(uint32 id)const{return starts.contains(id);}
    bool hasInvolvedQuest(uint32 id)const{return ends.contains(id);}
};
struct GameObjectTemplate { uint32 type=8; struct{uint32 focusId=63;float dist=50;uint32 serverOnly=0;}spellFocus; };
struct GameObject:WorldObject {
    GameObjectTemplate info; std::set<uint32> starts,ends;
    bool isSpawned()const{return spawned;}
    uint32 GetGoType()const{return info.type;}
    GameObjectTemplate const* GetGOInfo()const{return &info;}
};
@@FOCUSCHECK@@
struct GameObjectData { uint32 id=0,mapid=1,phaseMask=1; float posX=2,posY=0,posZ=0; };
std::vector<GameObjectData> spawns; uint32 spawnScans=0;
struct WorldPosition {
    uint32 map=0; float x=0,y=0,z=0;
    WorldPosition()=default;
    WorldPosition(uint32 map,float x,float y=0,float z=0):map(map),x(x),y(y),z(z){}
    explicit WorldPosition(WorldObject const* o):map(o->mapId),x(o->x),y(o->y),z(o->z){}
    bool operator==(WorldPosition const&)const=default;
    explicit operator bool()const{return *this!=WorldPosition();}
    uint32 GetMapId()const{return map;}
    float GetPositionX()const{return x;} float GetPositionY()const{return y;} float GetPositionZ()const{return z;}
    float GetExactDist(WorldPosition const& other)const {
        return std::sqrt((x-other.x)*(x-other.x)+(y-other.y)*(y-other.y)+(z-other.z)*(z-other.z));
    }
    std::vector<GameObjectData const*> getGameObjectsNear(float,uint32 entry)const {
        ++spawnScans;std::vector<GameObjectData const*> result;
        for(auto const& s:spawns)if(s.id==entry&&(!bool(*this)||map==s.mapid))result.push_back(&s);
        return result;
    }
};
float WorldObject::GetExactDist(WorldPosition const& p)const{return WorldPosition(this).GetExactDist(p);}
struct WorldPacket {
    uint32 opcode;std::vector<uint32> data;
    explicit WorldPacket(uint32 opcode):opcode(opcode){}
    WorldPacket& operator<<(uint8 value){data.push_back(value);return *this;}
};
namespace WorldPackets::Quest {
struct QuestLogRemoveQuest {
    WorldPacket packet;uint8 Slot=0;
    explicit QuestLogRemoveQuest(WorldPacket&& packet):packet(std::move(packet)){}
    void Read(){assert(packet.opcode==CMSG_QUESTLOG_REMOVE_QUEST&&packet.data.size()==1);Slot=packet.data[0];}
};
}
struct Session {
    Player* player=nullptr;bool allowRemove=true;uint32 removes=0;
    void HandleQuestLogRemoveQuest(WorldPackets::Quest::QuestLogRemoveQuest&);
};
struct Player:Unit {
    uint32 cls=CLASS_SHAMAN;Session session;
    std::map<uint32,QuestStatus> quests;std::map<uint32,Item> inventory;
    std::map<uint32,uint32> bank;std::set<uint32> available,auras;
    std::array<uint32,MAX_QUEST_LOG_SIZE> slots{};
    bool ownAccess=true,canAdd=true,canReward=true;int stops=0;
    // These select the session's post-use spell result, not a pre-existing cast.
    bool resultIsChannel=false,resultInstant=false,castActive=false;
    Spell genericSpell,channelSpell;
    Player(){entry=0;guid=100;x=0;size=1.5;session.player=this;}
    uint32 getClass()const{return cls;}
    QuestStatus GetQuestStatus(uint32 id)const{return quests.contains(id)?quests.at(id):QUEST_STATUS_NONE;}
    bool GetQuestRewardStatus(uint32 id)const{return GetQuestStatus(id)==QUEST_STATUS_REWARDED;}
    bool HasItemCount(uint32 item,uint32 count=1,bool includeBank=false)const {
        uint32 value=inventory.contains(item)?inventory.at(item).count:0;
        if(includeBank&&bank.contains(item))value+=bank.at(item);
        return value>=count;
    }
    Item* GetItemByEntry(uint32 id){return inventory.contains(id)?&inventory.at(id):nullptr;}
    bool HasAura(uint32 id)const{return auras.contains(id);}
    bool CanTakeQuest(Quest const* q,bool)const{return ownAccess&&available.contains(q->id)&&GetQuestStatus(q->id)==QUEST_STATUS_NONE;}
    bool CanAddQuest(Quest const*,bool)const{return canAdd;}
    bool CanRewardQuest(Quest const* q,bool)const{return canReward&&GetQuestStatus(q->id)==QUEST_STATUS_COMPLETE;}
    uint32 GetQuestSlotQuestId(uint16 slot)const{return slots.at(slot);}
    Session* GetSession(){return &session;}
    uint32 GetPhaseMask()const{return phaseMask;}
    bool IsInMap(WorldObject const* o)const{return mapId==o->mapId;}
    bool InSamePhase(WorldObject const* o)const{return phaseMask&o->phaseMask;}
    bool CanSeeOrDetect(WorldObject const* o)const{
        auto const* creature=dynamic_cast<Creature const*>(o);
        auto const* object=dynamic_cast<GameObject const*>(o);
        return o->visible&&(!object||!object->info.spellFocus.serverOnly)&&
            (!creature||!creature->requiresAura||HasAura(creature->requiresAura));
    }
    void StopMoving(){++stops;}
    Spell* GetCurrentSpell(uint32 id){
        return !castActive||resultInstant?nullptr:id==CURRENT_CHANNELED_SPELL?(resultIsChannel?&channelSpell:nullptr):&genericSpell;
    }
};
void Session::HandleQuestLogRemoveQuest(WorldPackets::Quest::QuestLogRemoveQuest& q){
    ++removes;if(!allowRemove||q.Slot>=MAX_QUEST_LOG_SIZE)return;
    player->quests.erase(player->slots[q.Slot]);player->slots[q.Slot]=0;
}
struct ObjectMgr {
    std::map<uint32,Quest> quests;std::map<uint32,ItemTemplate> items;std::map<uint32,GameObjectTemplate> objects;
    Quest const* GetQuestTemplate(uint32 id)const{return quests.contains(id)?&quests.at(id):nullptr;}
    ItemTemplate const* GetItemTemplate(uint32 id)const{return items.contains(id)?&items.at(id):nullptr;}
    auto const* GetGameObjectTemplates()const{return &objects;}
} objectMgr;
auto* sObjectMgr=&objectMgr;
struct SpellInfo {uint32 RequiresSpellFocus=63;};
struct SpellMgr {
    std::map<uint32,SpellInfo> spells;
    SpellInfo const* GetSpellInfo(uint32 id)const{return spells.contains(id)?&spells.at(id):nullptr;}
}spellMgr;
auto* sSpellMgr=&spellMgr;
enum class QuestRelationFlag:uint32 {questGiver=16,questTaker=32};
using questEntryGuidps=std::unordered_map<int32,std::vector<WorldPosition>>;
using questRelationGuidps=std::unordered_map<uint32,questEntryGuidps>;
std::map<uint32,questRelationGuidps> questLocations;
questRelationGuidps const* ClassQuestLocations(uint32 id){return questLocations.contains(id)?&questLocations.at(id):nullptr;}
struct NewRpgInfo {
    struct DoQuest {uint32 questId;Quest const* quest;};struct TravelRoute{};
    std::variant<std::monostate,DoQuest,TravelRoute> data;
    void ChangeToDoQuest(uint32 id,Quest const* q){data=DoQuest{id,q};}
};
struct Context {GuidVector npcs,objects;uint32 quest=0;};
template<class T>T GetValue(Context* c,std::string const& name){
    if constexpr(std::is_same_v<T,GuidVector>)return name=="nearest npcs"?c->npcs:c->objects;
    else return c->quest;
}
#define AI_VALUE(type,name) GetValue<type>(context,name)
struct PlayerbotAI {
    Player* bot;Context context;NewRpgInfo rpgInfo;bool canRun=true,castResult=true,moveResult=true;
    bool acceptResult=true,rewardResult=true,routes=true;uint32 casts=0,castChecks=0,waits=0,moves=0,accepts=0,rewards=0,objectives=0;
    WorldPosition movedTo;uint32 interacted=0;Item* castItem=nullptr;Unit* castTarget=nullptr;Spell* waitedFor=nullptr;
    std::map<uint32,Unit*> units;std::map<uint32,GameObject*> objects;
    Player* GetBot()const{return bot;}
    Unit* GetUnit(ObjectGuid guid)const{return units.contains(guid.value)?units.at(guid.value):nullptr;}
    GameObject* GetGameObject(ObjectGuid guid)const{return objects.contains(guid.value)?objects.at(guid.value):nullptr;}
    bool CanCastSpell(uint32 id,Unit* target,bool,Item*,Item* item){
        ++castChecks;castTarget=target;castItem=item;
        auto const* info=spellMgr.GetSpellInfo(id);
        if(!info||target!=bot||!item||bot->GetItemByEntry(item->entry)!=item)return false;
        GameObjectFocusCheck check(bot,info->RequiresSpellFocus);
        return std::any_of(objects.begin(),objects.end(),[&](auto const& pair){return check(pair.second);});
    }
    bool CanCastSpell(uint32,GameObject*,bool,Item*){return false;}
    void WaitForSpellCast(Spell* spell){assert(spell);++waits;waitedFor=spell;}
};
struct Config {std::set<uint32> IgnoredQuests;}sPlayerbotAIConfig;
bool CanRunClassQuest(PlayerbotAI* ai,uint8 cls){return ai->canRun&&ai->bot&&ai->bot->cls==cls;}
struct ClassQuestRouteCosts {
    PlayerbotAI* ai;explicit ClassQuestRouteCosts(PlayerbotAI* ai):ai(ai){}
    float Cost(WorldPosition const& p)const {
        return p.map==ai->bot->mapId?ai->bot->GetExactDist(p):ai->routes?1000+ai->bot->GetExactDist(p):std::numeric_limits<float>::infinity();
    }
};
WorldPosition NearestClassQuestLocation(uint32 id,uint32 role,ClassQuestRouteCosts const& costs){
    WorldPosition nearest;float distance=std::numeric_limits<float>::infinity();
    if(auto const* all=ClassQuestLocations(id))for(auto const& [flags,entries]:*all)if(flags&role)
      for(auto const& [entry,points]:entries)for(auto const& point:points)if(costs.Cost(point)<distance){nearest=point;distance=costs.Cost(point);}
    return nearest;
}
struct ClassQuestAction {
    PlayerbotAI* botAI;Player* bot;Context* context;
    ClassQuestAction(PlayerbotAI* ai,std::string):botAI(ai),bot(ai->bot),context(&ai->context){}
    virtual ~ClassQuestAction()=default;virtual bool isUseful(){return true;}virtual bool Execute(Event){return false;}
    bool MoveToQuestPosition(WorldPosition const& p){++botAI->moves;botAI->movedTo=p;return botAI->moveResult;}
    bool MoveToQuestLocation(Quest const* q,bool reward){
        ClassQuestRouteCosts cost(botAI);auto const p=NearestClassQuestLocation(q->id,reward?32:16,cost);
        return p!=WorldPosition()&&(p.map!=bot->mapId||bot->GetExactDist(p)>INTERACTION_DISTANCE)&&MoveToQuestPosition(p);
    }
    bool InteractWithQuestGiver(Quest const* q,bool reward);
    bool DoObjectives(Quest const*){++botAI->objectives;return false;}
};
struct Trigger {
    PlayerbotAI* botAI;Context* context;uint32 interval;
    Trigger(PlayerbotAI* ai,std::string,uint32 interval=1):botAI(ai),context(&ai->context),interval(interval){}
    virtual ~Trigger()=default;virtual bool IsActive(){return false;}
};
template<class T>struct CalculatedValue {
    PlayerbotAI* botAI;CalculatedValue(PlayerbotAI* ai,std::string,uint32):botAI(ai){}
    virtual ~CalculatedValue()=default;virtual T Calculate()=0;
};
struct UseItemAction {
    PlayerbotAI* botAI;explicit UseItemAction(PlayerbotAI* ai):botAI(ai){}
    bool UseItemOnUnit(Item*,Unit*);
    bool UseItem(Item* item,ObjectGuid,Item* itemTarget,Unit* unitTarget){
        Player* bot=botAI->GetBot();uint32 spellId=0;auto const* itemProto=item->GetTemplate();
        uint8 const spellSlotLimit=5;GameObject* goTarget=nullptr;
        @@PRECHECK@@
        if(!botAI->castResult)return false;
        ++botAI->casts;bot->castActive=true;
        if(item->entry==6635||item->entry==6636||item->entry==6637)bot->auras.insert(spellId);
        return true;
    }
};
@@CLASSES@@
@@TABLE@@
@@CURRENT@@
@@VALUE@@
@@TRIGGER@@
@@USEFUL@@
@@WRAPPER@@
@@FOCUSED@@
@@RESET@@
@@WATER@@
@@RESTART@@
@@EXECUTE@@
'''

tests = r'''
@@RELATIONS@@
bool ClassQuestAction::InteractWithQuestGiver(Quest const* q,bool reward){
    auto apply=[&](WorldObject* o,bool related){
        if(!o||!related||!o->IsInWorld()||!bot->IsInMap(o)||!bot->InSamePhase(o)||!bot->CanSeeOrDetect(o))return false;
        if(bot->GetExactDist(WorldPosition(o))>INTERACTION_DISTANCE)return MoveToQuestPosition(WorldPosition(o));
        botAI->interacted=q->id;
        if(reward){
            ++botAI->rewards;
            if(!botAI->rewardResult||!bot->CanRewardQuest(q,false))return false;
            for(auto item:q->RewardItem)if(item){auto& got=bot->inventory[item];got.entry=item;got.count=1;got.proto=objectMgr.items[item];}
            if(q->repeatable)bot->quests.erase(q->id);else bot->quests[q->id]=QUEST_STATUS_REWARDED;
            for(auto& slot:bot->slots)if(slot==q->id)slot=0;
            return true;
        }
        ++botAI->accepts;
        if(!botAI->acceptResult||!bot->CanTakeQuest(q,false)||!bot->CanAddQuest(q,false))return false;
        bot->quests[q->id]=QUEST_STATUS_INCOMPLETE;
        if(q->source){auto& got=bot->inventory[q->source];got.entry=q->source;got.count=1;got.proto=objectMgr.items[q->source];}
        bool complete=true;
        for(uint32 i=0;i<4;++i)if(q->RequiredNpcOrGoCount[i])complete=false;
        for(uint32 i=0;i<6;++i)if(q->RequiredItemCount[i]&&!bot->HasItemCount(q->RequiredItemId[i],q->RequiredItemCount[i]))complete=false;
        if(complete)bot->quests[q->id]=QUEST_STATUS_COMPLETE;
        for(auto& slot:bot->slots)if(!slot){slot=q->id;break;}
        return true;
    };
    for(auto guid:context->npcs){auto* u=botAI->GetUnit(guid);auto* c=u?u->ToCreature():nullptr;
      if(c&&apply(c,reward?c->ends.contains(q->id):c->starts.contains(q->id)))return true;}
    for(auto guid:context->objects){auto* g=botAI->GetGameObject(guid);
      if(g&&g->spawned&&apply(g,reward?g->ends.contains(q->id):g->starts.contains(q->id)))return true;}
    return false;
}
struct Scenario {
    Player bot;PlayerbotAI ai{&bot};ShamanTotemQuestValue value{&ai};ShamanTotemQuestTrigger trigger{&ai};
    ShamanTotemQuestAction action{&ai};GameObject focus;std::vector<std::unique_ptr<Creature>> creatures;
    std::vector<std::unique_ptr<GameObject>> objects;uint32 id;
    explicit Scenario(uint32 id=1517):id(id){
        now=100000;objectMgr={};spellMgr={};questLocations.clear();spawns.clear();spawnScans=0;sPlayerbotAIConfig={};
        @@NATIVEQUESTS@@
        @@ITEMS@@
        for(auto const& [item,proto]:objectMgr.items)spellMgr.spells[proto.Spells[0].SpellId]={63};
        spellMgr.spells[9586]={224};spellMgr.spells[9583]={226};spellMgr.spells[9584]={223};
        for(uint32 item:{5175u,5176u,5177u,5178u})if(item!=objectMgr.quests.at(id).totem)bot.bank[item]=1;
        if(id==63||id==96||id==100||id==972||id==1103||id==1536)bot.mapId=0;
        bot.quests[id]=QUEST_STATUS_INCOMPLETE;bot.slots[0]=id;bot.available.insert(id);
        auto const& q=objectMgr.quests.at(id);if(q.source)Give(q.source);
        // Purified Manifestation has native relations but no static spawn.
        for(auto const& [entry,quest]:creature_queststarter)if(quest==id&&entry!=5895)AddNpc(entry,id,false);
        for(auto const& [entry,quest]:creature_questender)if(quest==id&&entry!=5895)AddNpc(entry,id,true);
        for(auto const& [entry,quest]:gameobject_queststarter)if(quest==id)AddGo(entry,id,false);
        for(auto const& [entry,quest]:gameobject_questender)if(quest==id)AddGo(entry,id,true);
        questLocations[63][32][-113791]={{0,2}};
        ai.context.quest=value.Calculate();
    }
    void Give(uint32 item){auto& got=bot.inventory[item];got.entry=item;got.count=1;got.proto=objectMgr.items[item];}
    Creature* AddNpc(uint32 entry,uint32 quest,bool reward){
        auto c=std::make_unique<Creature>();c->entry=entry;c->guid=uint32(ai.units.size()+10);c->mapId=bot.mapId;
        if(entry==5891)c->requiresAura=8202;
        if(reward)c->ends.insert(quest);else c->starts.insert(quest);
        auto* result=c.get();ai.units[c->guid]=result;ai.context.npcs.push_back(c->GetGUID());
        questLocations[quest][reward?32:16][int32(entry)]={{bot.mapId,2}};
        creatures.push_back(std::move(c));return result;
    }
    GameObject* AddGo(uint32 entry,uint32 quest,bool reward){
        auto g=std::make_unique<GameObject>();g->entry=entry;g->guid=uint32(ai.objects.size()+100);g->mapId=bot.mapId;g->info.type=2;
        if(reward)g->ends.insert(quest);else g->starts.insert(quest);
        auto* result=g.get();ai.objects[g->guid]=result;ai.context.objects.push_back(g->GetGUID());
        questLocations[quest][reward?32:16][int32(entry)*-1]={{bot.mapId,2}};
        objects.push_back(std::move(g));return result;
    }
    void Focus(uint32 item,uint32 creature=0){
        Give(item);auto const spell=objectMgr.items.at(item).Spells[0].SpellId;
        focus.entry=item==7766?107046:item==7768?107045:item==7767?107047:63674;
        focus.guid=500;focus.mapId=bot.mapId;focus.info.spellFocus.focusId=spellMgr.spells.at(spell).RequiresSpellFocus;
        focus.info.spellFocus.serverOnly=item==7766||item==7768||item==7767;
        focus.info.spellFocus.dist=10;objectMgr.objects[focus.entry]=focus.info;
        ai.objects[500]=&focus;ai.context.objects.push_back({500});spawns.push_back({focus.entry,bot.mapId,1,2,0,0});
        if(creature)questLocations[id][1][int32(creature)]={{bot.mapId,2}};
    }
    void Offered(){bot.quests.erase(id);bot.slots[0]=0;bot.available.insert(id);ai.context.quest=value.Calculate();}
    void SpiritAt(uint32 entry,float x){
        for(auto& [flags,entries]:questLocations[id])for(auto& [key,points]:entries)
          if(key==int32(entry))points={{bot.mapId,x}};
    }
    uint32 Current(){auto* row=CurrentShamanTotemQuest(&ai);return row?row->Quest:0;}
};
int main(){
    for(auto const& row:ShamanTotemQuests)if(!RecoveryQuest(row.Quest)){
        Scenario s(row.Quest);assert(s.Current()==row.Quest);
        s.bot.bank[row.Totem]=1;assert(!s.Current());s.bot.bank.erase(row.Totem);
        sPlayerbotAIConfig.IgnoredQuests.insert(row.Quest);assert(!s.Current());
    }
    {Scenario s;assert(s.trigger.interval==1&&s.trigger.IsActive()&&s.action.isUseful());
      s.ai.context.quest=0;assert(!s.trigger.IsActive()&&!s.action.isUseful());}
    {Scenario s;s.bot.cls=CLASS_WARLOCK;assert(!s.Current()&&!s.action.Execute({})&&!s.trigger.IsActive()&&!s.action.isUseful());}
    {Scenario s;s.ai.canRun=false;assert(!s.Current()&&!s.action.Execute({})&&!s.trigger.IsActive()&&!s.action.isUseful());}
    {Scenario s;s.Offered();s.bot.ownAccess=false;assert(!s.Current());}
    {Scenario s;s.Offered();s.bot.canAdd=false;assert(!s.Current());}
    for(auto [quest,terminal]:{std::array<uint32,2>{1517,1518},{1520,1521},{1526,1527},{63,96},{1531,1531},{1532,1532}}){
      Scenario s(quest);s.bot.quests[terminal]=QUEST_STATUS_REWARDED;
      assert(TotemEarned(&s.bot,objectMgr.quests.at(quest).totem)&&!s.Current());}
    {Scenario s(1516);s.Offered();s.bot.available.insert(1519);s.AddNpc(5888,1519,false);
      questLocations[1516][16].begin()->second={{1,40}};assert(s.Current()==1519);}
    {Scenario s(1519);s.bot.available.insert(1516);s.AddNpc(5888,1516,false);assert(s.Current()==1519);}
    {Scenario s;s.Offered();s.bot.available.erase(1517);s.bot.available.insert(1463);s.AddNpc(5887,1463,false);
      assert(!s.Current());}
    for(auto [quest,item,creature]:{std::array<uint32,3>{1517,6635,5891},{1520,6635,5891},{1526,6636,5893},{63,6637,5894}}){
        Scenario s(quest);s.Focus(item,creature);
        if(quest==1517||quest==1520)s.bot.quests[quest]=QUEST_STATUS_COMPLETE;
        assert(s.action.Execute({})&&s.ai.casts==1&&s.ai.castTarget==&s.bot&&s.ai.castItem==s.bot.GetItemByEntry(item));
        assert(s.bot.HasAura(objectMgr.items[item].Spells[0].SpellId));
        assert(s.ai.waits==1&&s.ai.waitedFor==&s.bot.genericSpell);
        bool const again=s.action.Execute({});assert(s.ai.casts==1);
        if(quest==1517||quest==1520)assert(again&&s.ai.rewards==1);
        else assert(!again&&s.ai.objectives==1);
    }
    {Scenario s;s.Focus(6635,5891);s.bot.resultIsChannel=true;assert(s.action.Execute({})&&s.ai.waitedFor==&s.bot.channelSpell);}
    {Scenario s;s.Focus(6635,5891);s.bot.resultInstant=true;assert(s.action.Execute({})&&s.ai.waits==0);}
    {Scenario s;s.Focus(6635,5891);s.ai.castResult=false;assert(!s.action.Execute({})&&s.ai.waits==0);}
    {Scenario s;s.Focus(6635,5891);s.bot.inventory.erase(6635);assert(!s.action.Execute({})&&s.ai.casts==0);}
    {Scenario s;s.Focus(6635,5891);spellMgr.spells.clear();assert(!s.action.Execute({})&&s.ai.casts==0);}
    {Scenario s;s.Focus(6635,5891);spellMgr.spells[8202].RequiresSpellFocus=0;
      s.focus.info.spellFocus.focusId=0;objectMgr.objects[s.focus.entry]=s.focus.info;
      assert(!s.action.Execute({})&&s.ai.casts==0);}
    {Scenario s;s.Focus(6635,5891);s.bot.auras.insert(8202);s.bot.quests[1517]=QUEST_STATUS_COMPLETE;
      assert(s.action.Execute({})&&s.ai.rewards==1&&s.ai.casts==0);}
    for(uint32 quest:{1518u,1521u}){Scenario s(quest);s.Offered();s.Focus(6635,5891);
      assert(s.action.Execute({})&&s.ai.casts==1&&s.ai.accepts==0);assert(s.action.Execute({})&&s.ai.accepts==1);}
    {Scenario s(1526);s.Focus(6636,5893);s.Give(6655);assert(!s.action.Execute({})&&s.ai.casts==0&&s.ai.objectives==1);}
    {Scenario s(63);s.Focus(6637,5894);s.Give(7812);assert(!s.action.Execute({})&&s.ai.casts==0&&s.ai.objectives==1);}
    for(auto [quest,item]:{std::array<uint32,2>{1535,7766},{1536,7768},{1534,7767}}){
        Scenario s(quest);s.Focus(item);assert(s.action.Execute({})&&s.ai.casts==1&&s.ai.castTarget==&s.bot);
        assert(s.bot.GetQuestStatus(quest)==QUEST_STATUS_INCOMPLETE);
    }
    {Scenario s(1536);s.Focus(7768);spellMgr.spells[9583].RequiresSpellFocus=777;
      s.focus.info.spellFocus.focusId=777;objectMgr.objects[s.focus.entry]=s.focus.info;
      assert(s.action.Execute({})&&s.ai.casts==1);}
    {Scenario s;s.Focus(6635,5891);s.focus.spawned=false;assert(!s.action.Execute({})&&s.ai.castChecks==0);}
    // Native implicit spell foci can be invisible, including all three server-only water foci.
    {Scenario s;s.Focus(6635,5891);s.focus.visible=false;assert(s.action.Execute({})&&s.ai.casts==1);}
    {Scenario s;s.Focus(6635,5891);s.focus.phaseMask=2;assert(!s.action.Execute({})&&s.ai.castChecks==0);}
    {Scenario s;s.Focus(6635,5891);s.focus.info.type=3;assert(!s.action.Execute({})&&s.ai.castChecks==0);}
    {Scenario s;s.Focus(6635,5891);s.focus.info.spellFocus.focusId=999;assert(!s.action.Execute({})&&s.ai.castChecks==0);}
    {Scenario s;s.Focus(6635,5891);s.focus.x=50;assert(!s.action.Execute({})&&s.ai.casts==0);}
    {Scenario s;s.Focus(6635,5891);s.focus.x=20;spawns[0].posX=20;s.SpiritAt(5891,20);
      assert(s.action.Execute({})&&s.ai.moves==1&&s.ai.casts==0);}
    {Scenario s;s.Focus(6635,5891);s.bot.x=10;assert(s.action.Execute({})&&s.ai.casts==1&&s.ai.moves==0);}
    {Scenario s;s.Focus(6635,5891);objectMgr.objects[1]=s.focus.info;
      objectMgr.objects[1].spellFocus.focusId=999;spawns.push_back({1,1,1,1,0,0});
      assert(s.action.Execute({})&&s.ai.casts==1);}
    {Scenario s;s.Focus(6635,5891);spawns[0].phaseMask=2;spawns[0].posX=40;s.SpiritAt(5891,40);
      assert(!s.action.Execute({})&&s.ai.casts==0&&s.ai.moves==0);}
    {Scenario s;s.Focus(6635,5891);s.SpiritAt(5891,200);
      spawns.push_back({100035,1,1,200,0,0});objectMgr.objects[100035]=s.focus.info;
      assert(s.action.Execute({})&&s.ai.moves==1&&s.ai.movedTo.x==200&&s.ai.casts==0);}
    {Scenario s(1536);s.bot.mapId=1;s.Focus(7768);spawns[0].mapid=0;s.focus.mapId=0;
      assert(s.action.Execute({})&&s.ai.moves==1&&s.ai.movedTo.map==0&&s.ai.casts==0);}
    {Scenario s;s.Focus(6635,5891);s.ai.context.objects.clear();spawns[0].mapid=0;
      assert(!s.action.Execute({})&&s.ai.moves==0);}
    {Scenario s(1536);s.Focus(7768);s.ai.routes=false;spawns[0].mapid=1;s.focus.mapId=1;
      assert(!s.action.Execute({})&&s.ai.moves==0);}
    {Scenario s(1536);s.Focus(7768);s.ai.castResult=false;assert(!s.action.Execute({}));uint32 scans=spawnScans;
      assert(!s.action.Execute({})&&spawnScans==scans);now+=60000;
      assert(!s.action.Execute({})&&spawnScans>scans);}
    {Scenario s(1536);s.Focus(7768);s.ai.castResult=false;assert(!s.action.Execute({}));uint32 scans=spawnScans;
      s.bot.mapId=1;assert(s.action.Execute({})&&spawnScans>scans&&s.ai.movedTo.map==0);}
    {Scenario s(1536);s.Focus(7768);s.ai.castResult=false;assert(!s.action.Execute({}));
      spellMgr.spells[9583].RequiresSpellFocus=777;s.focus.info.spellFocus.focusId=777;
      objectMgr.objects[s.focus.entry]=s.focus.info;uint32 scans=spawnScans;s.ai.castResult=true;
      assert(s.action.Execute({})&&spawnScans>scans&&s.ai.casts==1);}
    {Scenario s;s.bot.inventory.erase(6635);s.bot.available.insert(1463);auto* npc=s.AddNpc(5887,1463,false);npc->ends.insert(1463);
      assert(s.Current()==1463&&s.action.Execute({})&&s.bot.GetQuestStatus(1463)==QUEST_STATUS_COMPLETE);
      assert(s.action.Execute({})&&s.bot.HasItemCount(6635)&&!s.bot.GetQuestRewardStatus(1463));assert(s.Current()==1517);}
    {Scenario s;s.bot.inventory.erase(6635);s.bot.available.insert(1463);sPlayerbotAIConfig.IgnoredQuests.insert(1463);
      assert(s.Current()==1517&&!s.action.Execute({}));}
    for(auto [quest,recovery,item]:{std::array<uint32,3>{1517,1463,6635},{1520,1462,6635},{1526,1464,6636},{63,972,6637}}){
      Scenario s(quest);s.bot.inventory.erase(item);s.bot.available.insert(recovery);assert(s.Current()==recovery);
      s.Give(item);assert(s.Current()==quest);s.bot.inventory.erase(item);
      s.bot.auras.insert(objectMgr.items.at(item).Spells[0].SpellId);assert(s.Current()==quest);}
    {Scenario s(1103);s.bot.quests[1103]=QUEST_STATUS_INCOMPLETE;s.bot.available.insert(972);
      assert(s.Current()==972);s.Give(6637);assert(s.Current()==1103&&RequiredSapta(&s.bot,1103)==0);}
    {Scenario s(100);s.bot.quests[100]=QUEST_STATUS_COMPLETE;
      assert(s.action.Execute({})&&s.bot.session.removes==0&&s.ai.casts==0);
      now+=44999;assert(s.action.Execute({})&&s.bot.session.removes==0);
      now+=1;assert(s.action.Execute({})&&s.bot.session.removes==1&&s.bot.GetQuestStatus(100)==QUEST_STATUS_NONE);
      assert(s.action.Execute({})&&s.ai.accepts==1&&s.bot.GetQuestStatus(100)==QUEST_STATUS_COMPLETE);
      now+=1;assert(s.action.Execute({})&&s.bot.session.removes==1);}
    {Scenario s(100);s.bot.quests[100]=QUEST_STATUS_COMPLETE;
      assert(s.action.Execute({}));now+=45001;s.bot.session.allowRemove=false;assert(!s.action.Execute({})&&s.bot.session.removes==1);}
    for(bool source:{false,true}){Scenario s(100);s.bot.quests[100]=QUEST_STATUS_COMPLETE;
      assert(s.action.Execute({}));now+=45001;
      if(source)objectMgr.quests[100].source=6637;else objectMgr.quests[100].RequiredItemId[0]=6637;
      assert(!s.action.Execute({})&&s.bot.session.removes==0);}
    {Scenario s(100);s.bot.quests[100]=QUEST_STATUS_COMPLETE;s.bot.slots[0]=1526;s.bot.slots[24]=100;
      assert(s.action.Execute({}));now+=45000;assert(s.action.Execute({})&&s.bot.slots[0]==1526&&s.bot.slots[24]==0);}
    {Scenario s(100);s.bot.quests[100]=QUEST_STATUS_COMPLETE;assert(s.action.Execute({}));
      auto* pure=s.AddNpc(5895,100,true);pure->starts.insert(96);now+=15000;
      assert(s.action.Execute({})&&s.bot.GetQuestRewardStatus(100)&&s.bot.session.removes==0);
      now+=60000;assert(!s.action.Execute({})&&s.bot.session.removes==0);}
    {Scenario s(100);s.bot.quests[100]=QUEST_STATUS_COMPLETE;s.bot.x=100;
      assert(s.action.Execute({})&&s.ai.moves==1);now+=60000;assert(s.action.Execute({})&&s.bot.session.removes==0);}
    {Scenario s(96);s.Offered();auto* pure=s.AddNpc(5895,96,false);
      assert(pure->requiresAura==0&&s.action.Execute({})&&s.ai.accepts==1&&s.ai.casts==0);}
    {Scenario s(96);s.Offered();assert(s.Current()==96&&s.action.Execute({}));
      s.bot.available.insert(1103);s.AddNpc(7007,1103,false);now+=45000;
      assert(s.action.Execute({})&&s.ai.interacted==1103&&s.bot.GetQuestStatus(1103)==QUEST_STATUS_INCOMPLETE);
      assert(s.Current()==1103);}
    {Scenario s(96);s.Offered();assert(s.action.Execute({}));
      s.bot.available.insert(1103);s.AddNpc(7007,1103,false);sPlayerbotAIConfig.IgnoredQuests.insert(1103);now+=45000;
      assert(!s.action.Execute({})&&s.ai.accepts==0);}
    {Scenario s(96);s.Offered();assert(s.action.Execute({}));s.bot.available.insert(1103);
      auto* tiev=s.AddNpc(7007,1103,false);tiev->ends.insert(1103);now+=45000;
      assert(s.action.Execute({})&&s.ai.interacted==1103);
      // ItemAddedQuestCheck marks the native deliver quest complete after
      // the earned Sapta recovery. Rewarding it must reset the earlier wait.
      s.Give(6637);s.bot.quests[1103]=QUEST_STATUS_COMPLETE;
      assert(s.action.Execute({})&&s.bot.GetQuestRewardStatus(1103)&&s.ai.casts==0);
      assert(s.action.Execute({}));now+=15000;
      auto* pure=s.AddNpc(5895,96,false);assert(pure->requiresAura==0&&s.action.Execute({}));
      assert(s.bot.GetQuestStatus(96)==QUEST_STATUS_COMPLETE&&s.ai.casts==0);}
    {Scenario s(100);s.bot.quests[100]=QUEST_STATUS_COMPLETE;assert(s.action.Execute({}));
      auto* pure=s.AddNpc(5895,100,true);now+=15000;assert(s.action.Execute({}));pure->visible=false;
      s.bot.available.insert(96);s.bot.available.insert(1103);s.AddNpc(7007,1103,false);now+=1000;
      assert(s.action.Execute({})&&s.ai.accepts==0);now+=29000;
      assert(s.action.Execute({})&&s.ai.accepts==0);now+=16000;
      assert(s.action.Execute({})&&s.ai.interacted==1103&&s.ai.accepts==1);}
    std::cout<<"Shaman totems: native33quests, ownedSapta, runtimefocuses, waterskins and nativeWater wait/recovery passed\n";
}
'''

mutations = [
    ('totem trigger checks every engine tick', 'classes', 'Trigger(botAI, "shaman totem quest")',
     'Trigger(botAI, "shaman totem quest", 5)'),
    ('live Shaman selection delegates ownership gate', 'current', 'if (!CanRunClassQuest(botAI, CLASS_SHAMAN))', 'if (false)'),
    ('cached trigger still checks ownership', 'trigger', 'CanRunClassQuest(botAI, CLASS_SHAMAN) &&', ''),
    ('cached action still checks ownership', 'useful', 'CanRunClassQuest(botAI, CLASS_SHAMAN) &&', ''),
    ('bank-owned totem skips its chain', 'table', 'bot->HasItemCount(totem, 1, true)', 'bot->HasItemCount(totem, 1, false)'),
    ('ignored native quest is skipped', 'table', 'sPlayerbotAIConfig.IgnoredQuests.count(questId)', 'false'),
    ('own native access required for a new quest', 'table', '!bot->CanTakeQuest(quest, false)', 'false'),
    ('own quest log capacity required for a new quest', 'table', '!bot->CanAddQuest(quest, false)', 'false'),
    ('active chain takes precedence over a nearer offer', 'current', 'if (ActiveShamanQuest(bot, data.Quest))', 'if (false)'),
    ('nearest eligible giver selected', 'current', 'costs->Cost(pos) < nearest', 'costs->Cost(pos) < nearest && !selected'),
    ('recovery quests are not ordinary chain entries', 'current', 'RecoveryQuest(data.Quest) ||', ''),
    ('complete first Earth quest still needs Sapta', 'table',
     '(questId == 1517 || questId == 1520) && ActiveShamanQuest(bot, questId)',
     '(questId == 1517 || questId == 1520) && status == QUEST_STATUS_INCOMPLETE'),
    ('Earth spirit must be visible before accepting final quest', 'table',
     '(questId == 1518 || questId == 1521) && status == QUEST_STATUS_NONE', 'false'),
    ('collected Ember stops drinking Fire Sapta', 'table', '&& !bot->HasItemCount(GlowingEmber)', ''),
    ('collected Bracers stop drinking Water Sapta', 'table', '&& !bot->HasItemCount(WaterBracers)', ''),
    ('active Sapta aura avoids repeat drinking', 'execute', 'if (sapta && !SaptaSight(bot, sapta))', 'if (sapta)'),
    ('existing sight avoids unnecessary Sapta recovery', 'current', '&& !SaptaSight(bot, sapta)', ''),
    ('owned Sapta avoids unnecessary recovery', 'current', '&& !bot->HasItemCount(sapta)', ''),
    ('Orc and Tauren native recovery givers distinguished', 'current',
     '(selected->Quest == 1517 || selected->Quest == 1518) ? 1463 : 1462',
     '(selected->Quest == 1517 || selected->Quest == 1518) ? 1462 : 1463'),
    ('Water recovery restores the required owned Sapta first', 'current', 'if (!bot->HasItemCount(WaterSapta))', 'if (false)'),
    ('owned ritual item required', 'focused', 'if (!item)', 'if (false)'),
    ('runtime spell focus must be nonzero', 'focused', '!spell || !spell->RequiresSpellFocus', '!spell'),
    ('runtime focus ID selects native templates', 'focused',
     'entry.second.spellFocus.focusId == spell->RequiresSpellFocus', 'true'),
    ('native static focus phase required', 'focused', 'if (!(spawn->phaseMask & bot->GetPhaseMask()))', 'if (false)'),
    ('Sapta shrine must belong to the requested spirit', 'focused',
     'pos.GetExactDist(spirit) > entry.second.spellFocus.dist + INTERACTION_DISTANCE', 'false'),
    ('Sapta shrine must share the spirit map', 'focused', 'pos.GetMapId() != spirit.GetMapId() ||', ''),
    ('native focus scan includes the destination continent', 'focused', 'WorldPosition origin;', 'WorldPosition origin(bot);'),
    ('focus map change invalidates cached search', 'focused', '_focusMap != bot->GetMapId() ||', ''),
    ('runtime focus change invalidates cached search', 'focused', '_focusSpell != spell->RequiresSpellFocus ||', ''),
    ('native focus search expires after a minute', 'focused',
     'GetMSTimeDiffToNow(_focusChecked) >= MINUTE * IN_MILLISECONDS', 'false'),
    ('implicit native foci may be invisible', 'focused', '!focus->IsInWorld() ||',
     '!focus->IsInWorld() || !bot->CanSeeOrDetect(focus) ||'),
    ('live focus must be spawned before item use', 'focused', '!focus->isSpawned() ||', ''),
    ('live focus phase checked before item use', 'focused', '!bot->InSamePhase(focus) ||', ''),
    ('live focus type checked before item use', 'focused', 'focus->GetGoType() != GAMEOBJECT_TYPE_SPELL_FOCUS ||', ''),
    ('live focus ID checked before item use', 'focused',
     'focus->GetGOInfo()->spellFocus.focusId != spell->RequiresSpellFocus ||', ''),
    ('live focus must be the selected static shrine', 'focused',
     'focus->GetExactDist(_focusPosition) > INTERACTION_DISTANCE', 'false'),
    ('native focus range used for movement', 'focused',
     'focus->IsWithinDistInMap(bot, focus->GetGOInfo()->spellFocus.dist)', 'focus->IsWithinDistInMap(bot, 5.0f)'),
    ('ritual targets the item owner', 'focused', 'UseItemOnUnit(item, bot)', 'UseItemOnUnit(item, nullptr)'),
    ('owned item retained in native cast validation', 'precheck', 'false, itemTarget, item)', 'false, itemTarget, nullptr)'),
    ('generic item cast is waited', 'focused', 'cast = bot->GetCurrentSpell(CURRENT_GENERIC_SPELL);', 'cast = nullptr;'),
    ('native scheduler is updated before each action', 'execute', '_waterScheduler.Update();', ''),
    ('native delayed spirit gets its full waiting period', 'water', 'std::chrono::seconds(45)', 'std::chrono::seconds(15)'),
    ('ritual wait starts only at the brazier', 'water',
     'if (_waterBrazier.GetMapId() != bot->GetMapId() || bot->GetExactDist(_waterBrazier) > INTERACTION_DISTANCE)', 'if (false)'),
    ('Water quest with a source item cannot be abandoned', 'restart', 'quest->GetSrcItemId())', 'false)'),
    ('Water quest with required items cannot be abandoned', 'restart', 'if (item)', 'if (false && item)'),
    ('normal quest removal result is rechecked', 'restart',
     'if (bot->GetQuestStatus(WaterSpiritQuest) != QUEST_STATUS_NONE)', 'if (false)'),
    ('only the selected Water log slot is removed', 'restart', 'packet << uint8(slot);', 'packet << uint8(0);'),
    ('successful Water interaction cancels native pending timer', 'reset', '_waterScheduler.CancelAll();', ''),
    ('successful Water interaction resets waiting state', 'reset', '_waterWaiting = false;', ''),
    ('restarted Water ritual gets a fresh wait', 'reset', '_waterRecoveryReady = false;', ''),
    ('rewarded Tiev recovery resets the previous ritual wait', 'execute',
     'data->Quest == WaterSpiritRecovery && reward && bot->GetQuestRewardStatus(WaterSpiritRecovery)', 'false'),
]
for quest in (1518, 1521, 1527, 1531, 1532):
    mutations.append((f'rewarded terminal quest {quest} skips its chain', 'table',
                      f'bot->GetQuestRewardStatus({quest})', 'false'))
mutations.append(('rewarded Water terminal quest skips its chain', 'table',
                  'bot->GetQuestRewardStatus(ReturnWaterQuest)', 'false'))
for quest in (1535, 1536, 1534):
    mutations.append((f'waterskin step {quest} uses its native source item', 'execute',
                      f'data->Quest == {quest}', 'false'))
for label, key, old, _ in mutations:
    assert old in production[key], label


def build(directory, parts, name):
    text = prelude + tests
    for key, value in parts.items():
        text = text.replace('@@' + key.upper() + '@@', value)
    path = directory / (name + '.cpp')
    path.write_text(text)
    binary = directory / name
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-missing-field-initializers',
                    *SANITIZER_FLAGS, str(path), '-o', str(binary)], check=True)
    return run_fixture([str(binary)])


with tempfile.TemporaryDirectory(prefix='portable-shaman-totems-') as temporary:
    directory = Path(temporary)
    result = build(directory, production, 'totems')
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit('Shaman totem quest fixture failed')

    def rejected(numbered):
        index, (label, key, old, new) = numbered
        assert old in production[key], label
        mutant = {**production, key: production[key].replace(old, new)}
        return build(directory, mutant, f'mutant-{index}').returncode != 0

    # TaskScheduler makes these translation units comparatively large. Keep the
    # same bounded two-worker load on developer machines and hosted CI.
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = pool.map(rejected, enumerate(mutations))
        for (label, *_), rejected_mutant in zip(mutations, results):
            if not rejected_mutant:
                raise SystemExit('Shaman totem quest mutation survived: ' + label)
            print('Shaman totem quest mutation rejected: ' + label, flush=True)
