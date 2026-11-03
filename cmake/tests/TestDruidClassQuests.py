"""Exercise earned Druid form and cure quests against native content contracts.

The shared class-quest fixture covers native eligibility, interactions and
travel. This fixture executes the Druid selector and its owned-item, dialogue,
gathering and cure steps with the native producers those steps depend on.
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
    sql_values,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help='Playerbots src directory')
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
core = prepared_core(root)
module = args.source or core / 'modules/mod-playerbots/src'
druid = module / 'Ai/Class/Druid'

families = {
    5487: {*range(5921, 5933), 6001, 6002},
    1066: {26, 27, 28, 29, 30, 31, 272, 5061},
    8946: set(range(6121, 6131)),
}
expected_quests = {quest: spell for spell, quests in families.items() for quest in quests}
assert len(expected_quests) == 32
quests = {int(row['ID']): row for row in sql_rows(core, 'quest_template', set(expected_quests))}
addons = {int(row['ID']): row for row in sql_rows(core, 'quest_template_addon', set(expected_quests))}
for quest, row in quests.items():
    assert int(addons[quest]['AllowableClasses']) == 1024, quest
    previous = abs(int(addons[quest]['PrevQuestID']))
    if previous:
        assert previous in expected_quests and expected_quests[previous] == expected_quests[quest], quest
    next_quest = int(row['RewardNextQuest']) or int(addons[quest]['NextQuestID'])
    if next_quest:
        assert next_quest in expected_quests and expected_quests[next_quest] == expected_quests[quest], quest
for final, reward in ((6001, 19179), (6002, 19179), (31, 1446), (5061, 1446), (6125, 8947), (6130, 8947)):
    assert int(quests[final]['RewardSpell']) == reward

item_spells = {15208: 18974, 15710: 19138, 15877: 19719, 15883: 19720,
               15826: 19512, 15844: 19564, 15842: 19565}
items = {int(row['entry']): row for row in sql_rows(core, 'item_template', set(item_spells) | {15882, 15885, 2449, 15851, 15852})}
for item, spell in item_spells.items():
    assert int(items[item]['spellid_1']) == spell
    assert int(items[item]['spelltrigger_1']) == 0
assert int(items[15826]['spellcharges_1']) == -10
for quest, item in ((6001, 15208), (6002, 15710), (6122, 15844), (6127, 15842), (6124, 15826), (6129, 15826)):
    assert int(quests[quest]['StartItem']) == item and int(addons[quest]['ProvidedItemCount']) == 1
for quest, target in ((6124, 12299), (6129, 12297)):
    assert int(quests[quest]['RequiredNpcOrGo1']) == target
    assert int(quests[quest]['RequiredNpcOrGoCount1']) == 10
for quest in (6123, 6128):
    assert (2449, 5) in {(int(quests[quest]['RequiredItemId' + str(index)]),
                          int(quests[quest]['RequiredItemCount' + str(index)])) for index in range(1, 7)}

focus_templates = {int(row['entry']): row for row in sql_rows(
    core, 'gameobject_template', {177525, 15885, 19463, 19464})}
assert {(entry, int(row['type']), int(row['Data0']), int(row['Data1']))
        for entry, row in focus_templates.items()} == {
    (177525, 8, 943, 10), (15885, 8, 1043, 30), (19463, 8, 1003, 13), (19464, 8, 1004, 13)}
native_gossip = function((core / 'src/server/game/Handlers/MiscHandler.cpp').read_text(),
                         'void WorldSession::HandleGossipSelectOptionOpcode(')
for contract in ('GetItem(gossipListId)', 'GetSenderGUID() != guid',
                 'unit->AI()->sGossipSelect(_player, menuId, gossipListId)',
                 '_player->OnGossipSelect(unit, gossipListId, menuId)'):
    assert contract in native_gossip
assert native_gossip.index('unit->AI()->sGossipSelect(_player, menuId, gossipListId)') < native_gossip.rindex(
    '_player->OnGossipSelect(unit, gossipListId, menuId)')
menu_rows = sql_rows(core, 'gossip_menu_option', {3862, 3881, 3882, 3883, 3884})
assert {(int(row['MenuID']), int(row['OptionID']), int(row['ActionMenuID'])) for row in menu_rows} == {
    (3882, 0, 3881), (3881, 0, 3883), (3883, 0, 3884), (3884, 0, 3885), (3862, 0, 3863), (3862, 1, 3863)}
assert all(int(row['OptionType']) == 1 and int(row['BoxMoney']) == 0 and int(row['BoxCoded']) == 0 for row in menu_rows)
native_spirits = {int(row['entry']): row for row in sql_rows(core, 'creature_template', {11956, 12144})}
assert int(native_spirits[11956]['gossip_menu_id']) == 3882 and int(native_spirits[12144]['gossip_menu_id']) == 3862
smart_rows = {(int(row['entryorguid']), int(row['id'])): row
              for row in sql_rows(core, 'smart_scripts', {11956, 12144})}
for key, fields in {
    (11956, 0): {'event_type': 62, 'event_param1': 3884, 'event_param2': 0, 'link': 1, 'action_type': 15, 'action_param1': 5929},
    (11956, 1): {'event_type': 61, 'action_type': 15, 'action_param1': 5930},
    (12144, 0): {'event_type': 62, 'event_param1': 3862, 'event_param2': 0, 'link': 1},
    (12144, 1): {'link': 2}, (12144, 2): {'action_type': 15, 'action_param1': 6001},
    (12144, 3): {'event_type': 62, 'event_param1': 3862, 'event_param2': 1, 'link': 4},
    (12144, 4): {'link': 5}, (12144, 5): {'action_type': 15, 'action_param1': 6002},
}.items():
    assert all(int(smart_rows[key][field]) == value for field, value in fields.items()), key
prepare_menu = function((core / 'src/server/game/Entities/Player/PlayerGossip.cpp').read_text(),
                        'void Player::PrepareGossipMenu(')
assert 'AddMenuItem(itr->second.OptionID,' in prepare_menu
assert 'AddGossipMenuItemData(itr->second.OptionID, itr->second.ActionMenuID' in prepare_menu
native_buy = function((core / 'src/server/game/Entities/Player/Player.cpp').read_text(),
                      'bool Player::BuyItemFromVendorSlot(')
for contract in ('GetCurrentVendor()', 'GetVendorItems()', 'GetVendorItemCurrentCount(crItem)',
                 'HasEnoughMoney(price)', 'BuyPrice', '_StoreOrEquipNewItem(', 'return crItem->maxcount != 0;'):
    assert contract in native_buy
native_list = function((core / 'src/server/game/Handlers/ItemHandler.cpp').read_text(),
                       'void WorldSession::SendListInventory(')
assert 'SetCurrentVendor(vendorEntry);' in native_list and 'GetNPCIfCanInteractWith' in native_list
for quest in (6001, 6002):
    assert not any(int(quests[quest][field + str(index)])
                   for field, count in (('RequiredNpcOrGo', 4), ('RequiredItemId', 6), ('ItemDrop', 4))
                   for index in range(1, count + 1))
native_remove = function((core / 'src/server/game/Handlers/QuestHandler.cpp').read_text(),
                         'void WorldSession::HandleQuestLogRemoveQuest(')
assert '_player->AbandonQuest(questId);' in native_remove
item_source = (module / 'Ai/Base/Actions/UseItemAction.cpp').read_text()
item_use = function(item_source, 'bool UseItemAction::UseItem(Item* item, ObjectGuid goGuid, Item* itemTarget, Unit* unitTarget)')
assert 'CanCastSpell(spellId, unitTarget ? unitTarget : bot, false, itemTarget, item)' in item_use
assert 'packet << targetFlag << unitTarget->GetGUID().WriteAsPacked();' in item_use
assert 'bot->GetSession()->HandleUseItemOpcode(packet);' in item_use
salve_source = (core / 'src/server/scripts/Spells/spell_quest.cpp').read_text()
salve_class = function(salve_source, 'class spell_q6124_6129_apply_salve')
salve_handler = function(salve_class, '    void HandleDummy(')
for contract in ('GetCastItem()', 'GetHitCreature()', 'creatureTarget->UpdateEntry(newEntry)',
                 'creatureTarget->DespawnOrUnsummon(DESPAWN_TIME)', 'caster->KilledMonsterCredit(newEntry)'):
    assert contract in salve_handler
native_focus = function((core / 'src/server/game/Grids/Notifiers/GridNotifiers.h').read_text(),
                        'class GameObjectFocusCheck') + ';'
spell_info = (core / 'src/server/game/Spells/SpellInfo.cpp').read_text()
for contract in ('RequiresSpellFocus = spellEntry->RequiresSpellFocus;', 'Reagent = spellEntry->Reagent;',
                 'ReagentCount = spellEntry->ReagentCount;',
                 'CastTimeEntry = spellEntry->CastingTimeIndex ? sSpellCastTimesStore.LookupEntry(spellEntry->CastingTimeIndex)'):
    assert contract in function(spell_info, 'SpellInfo::SpellInfo(')
for contract in ('Effect = spellEntry->Effect[effIndex];', 'MiscValue = spellEntry->EffectMiscValue[effIndex];',
                 'ItemType = spellEntry->EffectItemType[effIndex];'):
    assert contract in function(spell_info, 'SpellEffectInfo::SpellEffectInfo(')
spell_effects = (core / 'src/server/game/Spells/SpellEffects.cpp').read_text()
assert 'DoCreateItem(effIndex, m_spellInfo->Effects[effIndex].ItemType);' in function(
    spell_effects, 'void Spell::EffectCreateItem(')
quest_effect = function(spell_effects, 'void Spell::EffectQuestComplete(')
assert 'questId = m_spellInfo->Effects[effIndex].MiscValue;' in quest_effect
assert 'player->AreaExploredOrEventHappens(questId);' in quest_effect
assert 'ScriptsStart(sEventScripts, m_spellInfo->Effects[effIndex].MiscValue, m_caster, target);' in function(
    spell_effects, 'void Spell::EffectSendEvent(')
native_reagents = function((core / 'src/server/game/Spells/Spell.cpp').read_text(), 'void Spell::TakeReagents(')
for contract in ('m_spellInfo->Reagent[x]', 'm_spellInfo->ReagentCount[x]',
                 'p_caster->DestroyItemCount(itemid, itemcount, true);'):
    assert contract in native_reagents
native_creature_lookup = function((module / 'Mgr/Travel/TravelMgr.cpp').read_text(),
                                  'void FindPointCreatureData::operator()(')
assert '!entry || creatureData.id == entry' in native_creature_lookup
assert 'creatureData.id2' not in native_creature_lookup and 'creatureData.id3' not in native_creature_lookup
native_take = function((core / 'src/server/game/Entities/Player/PlayerQuest.cpp').read_text(),
                       'bool Player::CanTakeQuest(')
for contract in ('SatisfyQuestRace', 'SatisfyQuestClass', 'SatisfyQuestLevel',
                 'SatisfyQuestPreviousQuest', 'SatisfyQuestConditions'):
    assert contract in native_take

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
#include <set>
#include <sstream>
#include <string>
#include <tuple>
#include <utility>
#include <variant>
#include <vector>
using uint8=uint8_t;using uint16=uint16_t;using uint32=uint32_t;using uint64=uint64_t;using int32=int32_t;
using Milliseconds=std::chrono::milliseconds;
constexpr uint32 CLASS_DRUID=11,CLASS_WARLOCK=9,IN_MILLISECONDS=1000,MINUTE=60;
constexpr uint32 QUEST_OBJECTIVES_COUNT=4,QUEST_ITEM_OBJECTIVES_COUNT=6;
constexpr uint32 CURRENT_GENERIC_SPELL=1,CURRENT_CHANNELED_SPELL=2,GAMEOBJECT_TYPE_SPELL_FOCUS=8;
constexpr uint32 CMSG_GOSSIP_HELLO=1,CMSG_GOSSIP_SELECT_OPTION=2,CMSG_QUESTLOG_REMOVE_QUEST=3;
constexpr uint32 UNIT_NPC_FLAG_GOSSIP=1,UNIT_NPC_FLAG_VENDOR=128,GOSSIP_OPTION_GOSSIP=1,MAX_QUEST_LOG_SIZE=25;
constexpr uint32 GAMEOBJECT_TYPE_QUESTGIVER=2,SPELL_AURA_MOD_SHAPESHIFT=36,SCRIPT_COMMAND_TEMP_SUMMON_CREATURE=10;
constexpr uint8 TEAM_ALLIANCE=0,TEAM_HORDE=1,INVENTORY_SLOT_BAG_0=255,NULL_BAG=0,NULL_SLOT=255;
constexpr uint32 UNIT_FLAG_NOT_ATTACKABLE_1=128,SPELL_EFFECT_SEND_EVENT=61;
constexpr float INTERACTION_DISTANCE=5.0f;
constexpr Milliseconds DESPAWN_TIME=Milliseconds(30000);
enum QuestStatus {QUEST_STATUS_NONE,QUEST_STATUS_INCOMPLETE,QUEST_STATUS_COMPLETE,QUEST_STATUS_REWARDED,QUEST_STATUS_FAILED};
uint32 now=100000;
uint32 getMSTime(){return now;}uint32 GetMSTimeDiffToNow(uint32 before){return now-before;}
struct ObjectGuid {
    using LowType=uint32;
    uint32 value=0;explicit operator bool()const{return value!=0;}bool operator==(ObjectGuid const&)const=default;
    bool IsCreatureOrVehicle()const{return value!=0;}static ObjectGuid Empty;
};
ObjectGuid ObjectGuid::Empty;
using GuidVector=std::vector<ObjectGuid>;
struct Player;struct Creature;struct GameObject;struct WorldPosition;struct PlayerbotAI;
struct Event {std::string source;ObjectGuid object;Event()=default;
    Event(std::string source,ObjectGuid object):source(std::move(source)),object(object){}
    ObjectGuid getObject()const{return object;}};
struct WorldPacket {
    uint32 opcode=0;std::vector<uint32> data;std::size_t read=0;
    explicit WorldPacket(uint32 opcode=0):opcode(opcode){}
    WorldPacket& operator<<(ObjectGuid guid){data.push_back(guid.value);return *this;}
    WorldPacket& operator<<(uint32 value){data.push_back(value);return *this;}
    WorldPacket& operator>>(ObjectGuid& guid){guid.value=data.at(read++);return *this;}
    WorldPacket& operator>>(uint32& value){value=data.at(read++);return *this;}
    void rfinish(){read=data.size();}
};
struct Spell {int32 castTime=0;int32 GetCastTime()const{return castTime;}};
struct ItemTemplate {struct Slot{int32 SpellId=0,SpellCharges=0;}Spells[5];uint32 ItemId=0,BuyCount=1,BuyPrice=0;
    int32 MaxCount=0,Stackable=1;uint32 GetMaxStackSize()const{return uint32(std::max(1,Stackable));}};
struct Item {uint32 entry=0,count=1;int32 charges=0;ItemTemplate proto;
    ItemTemplate const* GetTemplate()const{return &proto;}
    uint32 GetEntry()const{return entry;}uint32 GetCount()const{return count;}
    uint8 GetBagSlot()const{return INVENTORY_SLOT_BAG_0;}uint8 GetSlot()const{return 23;}
    ObjectGuid GetGUID()const{return {entry};}};
struct Quest {
    uint32 id=0,source=0,goal=0,races=0,level=1,previous=0,flags=0;
    std::array<int32,4> RequiredNpcOrGo{};std::array<uint32,4> RequiredNpcOrGoCount{},ItemDrop{},ItemDropQuantity{};
    std::array<uint32,6> RequiredItemId{},RequiredItemCount{};
    uint32 GetQuestId()const{return id;}uint32 GetSrcItemId()const{return source;}
};
struct WorldObject {
    uint32 entry=1,guid=1,mapId=1,phaseMask=1;float x=0,y=0,z=0,size=.5f;
    bool inWorld=true,visible=true,los=true,alive=true;
    virtual ~WorldObject()=default;
    uint32 GetEntry()const{return entry;}ObjectGuid GetGUID()const{return {guid};}
    uint32 GetMapId()const{return mapId;}bool IsInWorld()const{return inWorld;}bool IsAlive()const{return alive;}
    bool IsWithinDistInMap(WorldObject const* other,float distance)const {
        float dx=x-other->x,dy=y-other->y,dz=z-other->z,range=distance+size+other->size;
        return mapId==other->mapId&&(phaseMask&other->phaseMask)&&dx*dx+dy*dy+dz*dz<range*range;}
    float GetExactDist(WorldPosition const&)const;
};
struct Unit:WorldObject {virtual Creature* ToCreature(){return nullptr;}};
struct MotionMaster {bool cleared=false,fleeing=false;
    void Clear(){cleared=true;}void MoveFleeing(Player*){fleeing=true;}};
struct VendorItem {uint32 item=0,maxcount=0,ExtendedCost=0;};
struct VendorItemData {std::vector<VendorItem> offers;uint32 GetItemCount()const{return offers.size();}
    VendorItem const* GetItem(uint32 slot)const{return slot<offers.size()?&offers[slot]:nullptr;}};
struct Creature:Unit {
    bool removing=false;uint32 spawnId=1,npcFlags=UNIT_NPC_FLAG_GOSSIP,despawn=0;
    uint32 unitFlags=0,stock=99;bool hostile=false;MotionMaster motion;std::set<uint32> starts,ends;
    VendorItemData inventory;
    Creature* ToCreature()override{return this;}bool IsDuringRemoveFromWorld()const{return removing;}
    uint32 GetSpawnId()const{return spawnId;}bool HasNpcFlag(uint32 flag)const{return npcFlags&flag;}
    bool IsHostileTo(Player*)const{return hostile;}VendorItemData const* GetVendorItems()const{return &inventory;}
    uint32 GetVendorItemCurrentCount(VendorItem const* offer)const{return offer->maxcount?stock:0;}
    void UpdateEntry(uint32 value){entry=value;}MotionMaster* GetMotionMaster(){return &motion;}
    void SetUnitFlag(uint32 flag){unitFlags|=flag;}
    void DespawnOrUnsummon(Milliseconds delay){despawn=uint32(delay.count());}
};
struct GameObjectTemplate {uint32 type=GAMEOBJECT_TYPE_SPELL_FOCUS;
    struct{uint32 focusId=0;float dist=13;uint32 serverOnly=0;}spellFocus;};
struct GameObject:WorldObject {
    GameObjectTemplate info;bool spawned=true,lootPossible=true;uint32 spawnId=1;
    bool isSpawned()const{return spawned;}uint32 GetGoType()const{return info.type;}
    GameObjectTemplate const* GetGOInfo()const{return &info;}
    uint32 GetSpawnId()const{return spawnId;}
    bool IsAtInteractDistance(Player const*)const;
};
@@FOCUSCHECK@@
struct GameObjectData {uint32 id=0,mapid=1,phaseMask=1;float posX=0,posY=0,posZ=0;uint32 spawnId=0;};
struct CreatureData {uint32 id=0,id2=0,id3=0,mapid=1,phaseMask=1,spawnId=0;float posX=0,posY=0,posZ=0;};
std::vector<GameObjectData> objectSpawns;std::vector<CreatureData> creatureSpawns;uint32 spawnScans=0;
struct WorldPosition {
    uint32 map=0;float x=0,y=0,z=0;
    WorldPosition()=default;WorldPosition(uint32 map,float x,float y=0,float z=0):map(map),x(x),y(y),z(z){}
    explicit WorldPosition(WorldObject const* o):map(o->mapId),x(o->x),y(o->y),z(o->z){}
    bool operator==(WorldPosition const&)const=default;explicit operator bool()const{return *this!=WorldPosition();}
    uint32 GetMapId()const{return map;}float GetPositionX()const{return x;}float GetPositionY()const{return y;}
    float GetPositionZ()const{return z;}
    float GetExactDist(WorldPosition const& other)const {
        float dx=x-other.x,dy=y-other.y,dz=z-other.z;return std::sqrt(dx*dx+dy*dy+dz*dz);}
    std::vector<GameObjectData const*> getGameObjectsNear(float,uint32 entry)const {
        ++spawnScans;std::vector<GameObjectData const*> found;
        for(auto const& spawn:objectSpawns)if(spawn.id==entry&&(!*this||spawn.mapid==map))found.push_back(&spawn);
        return found;}
    std::vector<CreatureData const*> getCreaturesNear(float,uint32 entry)const {
        ++spawnScans;std::vector<CreatureData const*> found;
        for(auto const& spawn:creatureSpawns) {
            if((!entry||spawn.id==entry)&&(!*this||spawn.mapid==map))found.push_back(&spawn);
        }
        return found;}
};
float WorldObject::GetExactDist(WorldPosition const& pos)const{return WorldPosition(this).GetExactDist(pos);}
using questRelationGuidps=std::map<uint32,std::map<int32,std::vector<WorldPosition>>>;
std::map<uint32,questRelationGuidps> questLocations;
enum class QuestRelationFlag {questGiver=16,questTaker=32};
struct GossipMenuItem {uint32 OptionType=1,BoxMoney=0;bool IsCoded=false;};
struct GossipMenuItemData {uint32 GossipActionMenuId=0;};
using GossipMenuItemContainer=std::map<uint32,GossipMenuItem>;
struct GossipMenu {
    uint32 id=0;ObjectGuid sender;GossipMenuItemContainer entries;std::map<uint32,GossipMenuItemData> details;
    uint32 GetMenuId()const{return id;}ObjectGuid GetSenderGUID()const{return sender;}
    GossipMenuItem const* GetItem(uint32 key)const {auto i=entries.find(key);return i==entries.end()?nullptr:&i->second;}
    GossipMenuItemData const* GetItemData(uint32 key)const{auto i=details.find(key);return i==details.end()?nullptr:&i->second;}
    GossipMenuItemContainer const& GetMenuItems()const{return entries;}bool Empty()const{return entries.empty();}
};
struct PlayerMenu {GossipMenu gossip;GossipMenu& GetGossipMenu(){return gossip;}};
namespace WorldPackets::Quest {
struct QuestLogRemoveQuest {
    WorldPacket packet;uint8 Slot=0;explicit QuestLogRemoveQuest(WorldPacket&& p):packet(std::move(p)){}
    void Read(){Slot=uint8(packet.data.at(0));}
};
}
struct Session {
    Player* player=nullptr;uint32 hellos=0,selections=0;bool allowHello=true,allowSelect=true;
    std::vector<std::tuple<uint32,uint32,uint32>> selected;bool allowRemove=true;uint32 removes=0;
    uint32 vendorContext=0,lists=0,alternateVendor=0;
    void HandleGossipHelloOpcode(WorldPacket&);void HandleGossipSelectOptionOpcode(WorldPacket&);
    void HandleQuestLogRemoveQuest(WorldPackets::Quest::QuestLogRemoveQuest&);
    void SendListInventory(ObjectGuid);uint32 GetCurrentVendor()const{return vendorContext;}
};
struct Player:Unit {
    uint8 cls=CLASS_DRUID,team=TEAM_ALLIANCE;uint32 race=8,level=60,money=100000;
    bool addAllowed=true,takeAllowed=true,storeAllowed=true,interactAllowed=true,form=false;uint32 stops=0,unshifts=0,buys=0;
    std::map<uint32,QuestStatus> quests;std::set<uint32> learned,available;
    std::map<uint32,Item> inventory;std::map<uint32,uint32> bank;
    std::array<uint32,MAX_QUEST_LOG_SIZE> slots{};ObjectGuid lootGuid;
    std::map<uint32,std::array<uint32,4>> credits;
    Session session{this};PlayerMenu talk;PlayerMenu* PlayerTalkClass=&talk;PlayerbotAI* ai=nullptr;
    Spell generic{3000},channel{3000};bool casting=false,channelled=false;
    uint32 pendingSpell=0,pendingItem=0,pendingTarget=0,castDue=0;
    Player* ToPlayer(){return this;}bool IsPlayer()const{return true;}
    uint8 getClass()const{return cls;}uint8 GetTeamId()const{return team;}uint32 GetLevel()const{return level;}
    uint32 GetPhaseMask()const{return phaseMask;}Session* GetSession(){return &session;}
    bool HasSpell(uint32 id)const{return learned.contains(id);}
    QuestStatus GetQuestStatus(uint32 id)const{auto i=quests.find(id);return i==quests.end()?QUEST_STATUS_NONE:i->second;}
    bool GetQuestRewardStatus(uint32 id)const{return GetQuestStatus(id)==QUEST_STATUS_REWARDED;}
    bool CanTakeQuest(Quest const* q,bool)const {
        return takeAllowed&&GetQuestStatus(q->id)==QUEST_STATUS_NONE&&available.contains(q->id)&&
            (!q->races||(q->races&race))&&level>=q->level;}
    bool CanAddQuest(Quest const*,bool)const{return addAllowed;}
    uint32 GetItemCount(uint32 entry,bool includeBank=false)const{auto i=inventory.find(entry);
        return (i==inventory.end()?0:i->second.count)+(includeBank&&bank.contains(entry)?bank.at(entry):0);}
    bool HasItemCount(uint32 entry,uint32 count=1,bool bank=false)const{return GetItemCount(entry,bank)>=count;}
    Item* GetItemByEntry(uint32 entry){auto i=inventory.find(entry);return i==inventory.end()?nullptr:&i->second;}
    bool IsInMap(WorldObject const* o)const{return mapId==o->mapId;}
    bool InSamePhase(WorldObject const* o)const{return phaseMask&o->phaseMask;}
    bool CanSeeOrDetect(WorldObject const* o)const{return o->visible&&IsInMap(o)&&InSamePhase(o);}
    bool IsWithinLOSInMap(WorldObject const* o)const{return o->los;}
    bool IsWithinLOS(float,float,float)const{return pointLos;}bool pointLos=true;
    float GetPositionZ()const{return z;}
    float GetDistance(WorldPosition const& pos)const{return GetExactDist(pos);}
    float GetDistance(WorldObject const* object)const{return GetExactDist(WorldPosition(object));}
    void StopMoving(){++stops;}
    void RemoveAurasByType(uint32){form=false;++unshifts;}
    Creature* GetNPCIfCanInteractWith(ObjectGuid,uint32);
    uint32 GetQuestSlotQuestId(uint16 slot)const{return slots.at(slot);}
    bool HasQuestForItem(uint32)const;ObjectGuid GetLootGUID()const{return lootGuid;}
    uint32 GetMoney()const{return money;}bool HasEnoughMoney(uint32 price)const{return money>=price;}
    float GetReputationPriceDiscount(Creature*)const{return discount;}float discount=1.0f;
    void const* GetFactionTemplateEntry()const{return this;}
    int GetFactionReactionTo(void const*,struct FactionTemplateEntry const*)const;
    bool BuyItemFromVendorSlot(ObjectGuid,uint32,uint32,uint32,uint8,uint8);
    Spell* GetCurrentSpell(uint32 type){return casting&&((type==CURRENT_CHANNELED_SPELL)==channelled)?
        (channelled?&channel:&generic):nullptr;}
    void KilledMonsterCredit(uint32);void FinishCast();
};
bool GameObject::IsAtInteractDistance(Player const* player)const{return IsWithinDistInMap(player,INTERACTION_DISTANCE);}
struct FactionTemplateEntry {uint32 id=0;};constexpr int REP_NEUTRAL=3;
struct FactionStore {std::map<uint32,FactionTemplateEntry> entries;
    FactionTemplateEntry const* LookupEntry(uint32 id)const{auto i=entries.find(id);return i==entries.end()?nullptr:&i->second;}
}sFactionTemplateStore;
struct CreatureTemplate {uint32 faction=0,minlevel=0;};
struct ObjectMgr {
    std::map<uint32,Quest> quests;std::map<uint32,ItemTemplate> items;
    std::map<uint32,GameObjectTemplate> objects;std::map<uint32,CreatureTemplate> creatures;
    std::map<uint32,VendorItemData> vendors;
    Quest const* GetQuestTemplate(uint32 id)const{auto i=quests.find(id);return i==quests.end()?nullptr:&i->second;}
    ItemTemplate const* GetItemTemplate(uint32 id)const{auto i=items.find(id);return i==items.end()?nullptr:&i->second;}
    auto const* GetGameObjectTemplates()const{return &objects;}
    CreatureTemplate const* GetCreatureTemplate(uint32 id)const{auto i=creatures.find(id);return i==creatures.end()?nullptr:&i->second;}
    VendorItemData const* GetNpcVendorItemList(uint32 id)const{auto i=vendors.find(id);return i==vendors.end()?nullptr:&i->second;}
}objectMgr;ObjectMgr* sObjectMgr=&objectMgr;
struct SpellInfo {uint32 RequiresSpellFocus=0;struct Slot{uint32 Effect=0,MiscValue=0;}Effects[3];};
struct SpellMgr {std::map<uint32,SpellInfo> spells;
    SpellInfo const* GetSpellInfo(uint32 id)const{auto i=spells.find(id);return i==spells.end()?nullptr:&i->second;}
}spellMgr;SpellMgr* sSpellMgr=&spellMgr;
struct ScriptInfo {uint32 command=0;struct {uint32 CreatureEntry=0;float PosX=0,PosY=0,PosZ=0;}TempSummonCreature;};
std::map<uint32,std::multimap<uint32,ScriptInfo>> sEventScripts;
std::vector<std::pair<uint32,WorldPosition>> nativeSummons;
struct NewRpgInfo {
    struct DoQuest{uint32 questId=0;};std::variant<std::monostate,DoQuest> data;
    void ChangeToDoQuest(uint32 id,Quest const*){data=DoQuest{id};}
};
struct LootObjectStack {bool pending=false;std::vector<ObjectGuid> queued;
    bool IsLootPending()const{return pending;}bool Add(ObjectGuid guid){
        if(std::find(queued.begin(),queued.end(),guid)!=queued.end())return false;
        queued.push_back(guid);return true;}};
struct Context;
template<class T>struct ContextValue {Context* context=nullptr;std::string name;T Get();};
struct Context {uint32 quest=0;GuidVector npcs,corpses,objects;LootObjectStack loot;
    template<class T>ContextValue<T>* GetValue(char const* name){static ContextValue<T> result;result={this,name};return &result;}};
template<class T>T GetValue(Context*,char const*);
template<> uint32 GetValue<uint32>(Context* context,char const*){return context->quest;}
template<> GuidVector GetValue<GuidVector>(Context* context,char const* name){
    return std::string(name)=="nearest npcs"?context->npcs:std::string(name)=="nearest corpses"?context->corpses:context->objects;}
template<> LootObjectStack* GetValue<LootObjectStack*>(Context* context,char const*){return &context->loot;}
template<class T>T ContextValue<T>::Get(){return ::GetValue<T>(context,name.c_str());}
#define AI_VALUE(type,name) GetValue<type>(context,name)
std::map<uint32,std::vector<int32>> itemDrops;
#define GAI_VALUE2(type,name,item) itemDrops[item]
struct PlayerbotAI {
    Player* bot;Context context;NewRpgInfo rpgInfo;bool canRun=true,routes=true,moveResult=true,castResult=true;
    bool rewardResult=true,acceptResult=true;uint32 moves=0,casts=0,castChecks=0,waits=0,objectives=0;
    uint32 accepts=0,rewards=0;WorldPosition movedTo;Item* castItem=nullptr;Unit* castTarget=nullptr;Spell* waitedFor=nullptr;
    std::map<uint32,Unit*> units;std::map<uint32,GameObject*> objects;
    Player* GetBot()const{return bot;}Unit* GetUnit(ObjectGuid guid)const{auto i=units.find(guid.value);return i==units.end()?nullptr:i->second;}
    GameObject* GetGameObject(ObjectGuid guid)const{auto i=objects.find(guid.value);return i==objects.end()?nullptr:i->second;}
    Context* GetAiObjectContext(){return &context;}
    bool CanCastSpell(uint32,Unit*,bool,Item*,Item*);
    void WaitForSpellCast(Spell* spell){assert(spell);++waits;waitedFor=spell;}
};
struct Config {std::set<uint32> IgnoredQuests,DisallowedGameObjects;float SightDistance=60;
    uint32 MaximumQuestGrindLevelDifference=4;}sPlayerbotAIConfig;
bool CanRunClassQuest(PlayerbotAI* ai,uint8 cls){return ai&&ai->canRun&&ai->bot&&ai->bot->cls==cls&&!ai->bot->casting;}
struct ClassQuestRouteCosts {
    PlayerbotAI* ai;explicit ClassQuestRouteCosts(PlayerbotAI* ai):ai(ai){}
    float Cost(WorldPosition const& pos)const{return ai->routes||pos.map==ai->bot->mapId?
        ai->bot->GetExactDist(pos):std::numeric_limits<float>::infinity();}
};
questRelationGuidps const* ClassQuestLocations(uint32 quest){auto i=questLocations.find(quest);return i==questLocations.end()?nullptr:&i->second;}
WorldPosition NearestClassQuestLocation(uint32 quest,uint32 relation,ClassQuestRouteCosts const& costs){
    WorldPosition best;float nearest=std::numeric_limits<float>::max();
    if(auto const* locations=ClassQuestLocations(quest))for(auto const& [flags,entries]:*locations)if(flags&relation)
        for(auto const& [entry,positions]:entries)for(auto const& pos:positions)if(costs.Cost(pos)<nearest){best=pos;nearest=costs.Cost(pos);}
    return best;}
template<class T>struct CalculatedValue {PlayerbotAI* botAI;Context* context;
    CalculatedValue(PlayerbotAI* ai,char const*,int):botAI(ai),context(&ai->context){}virtual T Calculate()=0;};
struct Trigger {PlayerbotAI* botAI;Context* context;
    Trigger(PlayerbotAI* ai,char const*):botAI(ai),context(&ai->context){}virtual bool IsActive()=0;};
struct ClassQuestAction {
    PlayerbotAI* botAI;Player* bot;Context* context;
    ClassQuestAction(PlayerbotAI* ai,char const*):botAI(ai),bot(ai->bot),context(&ai->context){}
    virtual bool isUseful(){return true;}virtual bool Execute(Event){return false;}
    bool MoveToQuestPosition(WorldPosition const& pos){++botAI->moves;botAI->movedTo=pos;return botAI->moveResult;}
    bool MoveToQuestLocation(Quest const* quest,bool reward){ClassQuestRouteCosts costs(botAI);
        auto pos=NearestClassQuestLocation(quest->id,reward?32:16,costs);return pos!=WorldPosition()&&MoveToQuestPosition(pos);}
    bool InteractWithQuestGiver(Quest const*,bool);
    bool DoObjectives(Quest const* quest){++botAI->objectives;botAI->rpgInfo.ChangeToDoQuest(quest->id,quest);return false;}
};
struct UseItemAction {
    PlayerbotAI* botAI;Player* bot;explicit UseItemAction(PlayerbotAI* ai):botAI(ai),bot(ai->bot){}
    bool UseItemOnUnit(Item*,Unit*);bool UseItem(Item*,ObjectGuid,Item*,Unit*);
};
struct LootObject {
    Player* bot;ObjectGuid guid;LootObject(Player* bot,ObjectGuid guid):bot(bot),guid(guid){}
    bool IsEmpty()const{return !guid;}bool IsLootPossible(Player*)const;
};
struct AddLootAction {PlayerbotAI* botAI;Player* bot;Context* context;
    explicit AddLootAction(PlayerbotAI* ai):botAI(ai),bot(ai->bot),context(&ai->context){}bool Execute(Event);};
@@ADDLOOT@@
@@CLASSES@@
@@TABLE@@
@@CURRENT@@
@@VALUE@@
@@TRIGGER@@
@@USEFUL@@
@@WRAPPER@@
@@TALK@@
@@FOCUSPOSITION@@
@@FOCUSED@@
@@GATHER@@
@@CURE@@
@@EARTHROOT@@
@@BODY@@
@@RESTART@@
@@EXECUTE@@
'''

source = (druid / 'DruidClassQuests.cpp').read_text()
header = (druid / 'DruidClassQuests.h').read_text()
production = {
    'table': function(source, 'namespace\n'),
    'classes': '\n'.join(function(header, name) + ';' for name in (
        'struct DruidClassQuest', 'class DruidClassQuestValue',
        'class DruidClassQuestTrigger', 'class DruidClassQuestAction')),
    'current': function(source, 'DruidClassQuest const* CurrentDruidClassQuest('),
    'value': function(source, 'uint32 DruidClassQuestValue::Calculate()'),
    'trigger': function(source, 'bool DruidClassQuestTrigger::IsActive()'),
    'useful': function(source, 'bool DruidClassQuestAction::isUseful()'),
    'execute': function(source, 'bool DruidClassQuestAction::Execute('),
    'talk': function(source, 'bool DruidClassQuestAction::TalkToSpirit('),
    'focusposition': function(source, 'WorldPosition DruidClassQuestAction::FocusPosition('),
    'focused': function(source, 'bool DruidClassQuestAction::UseFocusedItem('),
    'gather': function(source, 'bool DruidClassQuestAction::GatherQuestItem('),
    'cure': function(source, 'bool DruidClassQuestAction::CureSick('),
    'earthroot': function(source, 'bool DruidClassQuestAction::AcquireEarthroot('),
    'body': function(source, 'bool DruidClassQuestAction::BodyAndHeart('),
    'restart': function(source, 'bool DruidClassQuestAction::RestartLunaclawQuest('),
    'wrapper': function(item_source, 'bool UseItemAction::UseItemOnUnit('),
    'focuscheck': native_focus,
    'addloot': function((module / 'Ai/Base/Actions/AddLootAction.cpp').read_text(), 'bool AddLootAction::Execute('),
}
for forbidden in ('bot->AddQuest(', 'bot->RewardQuest(', 'bot->CompleteQuest(', 'bot->AreaExploredOrEventHappens(',
                  'learnSpell(', 'SummonCreature(', 'AddItem(', 'TeleportTo(', 'SetMoney('):
    assert forbidden not in source, forbidden
assert 'CalculatedValue<uint32>(botAI, "druid class quest", 5)' in header
assert 'Trigger(botAI, "druid class quest")' in header
context_source = (druid / 'DruidAiObjectContext.cpp').read_text()
for factory in ('DruidTriggerFactoryInternal', 'DruidAiObjectContextInternal', 'DruidValueContextInternal'):
    assert f'creators["druid class quest"] = &{factory}::class_quest;' in context_source
assert 'valueContexts.Add(new DruidValueContextInternal());' in context_source
assert 'NextAction("druid class quest", ACTION_NORMAL + 2)' in (
    druid / 'Strategy/GenericDruidNonCombatStrategy.cpp').read_text()
goal_names = {'BearForm': 5487, 'AquaticForm': 1066, 'CurePoison': 8946}
assert {int(quest): goal_names[goal] for quest, goal in re.findall(
    r'\{(\d+),\s*(BearForm|AquaticForm|CurePoison)\}', production['table'])} == expected_quests
native_initializers = []
for quest, row in quests.items():
    fields = [str(quest), row['StartItem'], str(expected_quests[quest]), row['AllowableRaces'], row['MinLevel'],
              str(abs(int(addons[quest]['PrevQuestID']))), addons[quest]['SpecialFlags']]
    for field, count in (('RequiredNpcOrGo', 4), ('RequiredNpcOrGoCount', 4), ('ItemDrop', 4), ('ItemDropQuantity', 4),
                         ('RequiredItemId', 6), ('RequiredItemCount', 6)):
        fields.append('{' + ','.join(row[field + str(index + 1)] for index in range(count)) + '}')
    native_initializers.append('Quest{' + ','.join(fields) + '}')
native_init = 'for(Quest const& q : {' + ',\n'.join(native_initializers) + '}) objectMgr.quests.emplace(q.id,q);'
item_init = '\n'.join(f'objectMgr.items[{item}].ItemId={item};'
                      f'objectMgr.items[{item}].Spells[0].SpellId={row["spellid_1"]};'
                      f'objectMgr.items[{item}].Spells[0].SpellCharges={row["spellcharges_1"]};'
                      f'objectMgr.items[{item}].BuyCount={row["BuyCount"]};'
                      f'objectMgr.items[{item}].BuyPrice={row["BuyPrice"]};'
                      f'objectMgr.items[{item}].MaxCount={row["maxcount"]};'
                      f'objectMgr.items[{item}].Stackable={row["stackable"]};'
                      for item, row in items.items())
# Adapter spell fields and effects reflect audited native 3.3.5 Spell.dbc rows;
# the contracts above keep their runtime SpellInfo and effect pipeline explicit.
spell_focuses = {18974: 943, 19138: 943, 19719: 1043, 19720: 1043, 19564: 1003, 19565: 1004, 19512: 0}
spell_init = '\n'.join(f'spellMgr.spells[{spell}].RequiresSpellFocus={focus};'
                       for spell, focus in spell_focuses.items())
event_rows = sql_rows(core, 'event_scripts', {5991, 6028})
assert {int(row['datalong']) for row in event_rows} == {12138}
ambush_rows = sql_rows(core, 'event_scripts', {6138, 5246})
assert {(int(row['id']), int(row['datalong'])) for row in ambush_rows} == {(6138, 2179), (6138, 12321), (5246, 12319)}
assert all(int(row['command']) == 10 and int(row['delay']) == 0 and int(row['datalong2']) == 3000000
           for row in ambush_rows)
event_init = '\n'.join('sEventScripts[' + row['id'] + '].emplace(' + row['delay'] + ',ScriptInfo{' + row['command']
                       + ',{' + row['datalong'] + ',' + str(float(row['x'])) + 'f,' + str(float(row['y'])) + 'f,'
                       + str(float(row['z'])) + 'f}});'
                       for row in event_rows)


def spawn_rows(table, wanted):
    columns = []
    found = []
    wanted_text = {str(entry) for entry in wanted}
    with (core / f'data/sql/base/db_world/{table}.sql').open() as stream:
        for line in stream:
            if line.startswith('  `'):
                columns.append(line.split('`')[1])
            if not line.startswith('('):
                continue
            entries = line.split(',', 4)[1:4] if table == 'creature' else line.split(',', 2)[1:2]
            if not any(value in wanted_text for value in entries):
                continue
            row = dict(zip(columns, sql_values(line.rstrip('\n,;')[1:-1]), strict=True))
            found.append(row)
    return found


native_objects = spawn_rows('gameobject', {177525, 15885, 19463, 19464, 177785, 177792, 177794, 177844, 177790, 177750})
assert {int(row['id']) for row in native_objects} == {177525, 15885, 19463, 19464, 177785, 177792, 177794, 177844, 177790, 177750}
object_init = '\n'.join('objectSpawns.push_back(GameObjectData{' + ','.join([
    row['id'], row['map'], row['phaseMask'], str(float(row['position_x'])) + 'f',
    str(float(row['position_y'])) + 'f', str(float(row['position_z'])) + 'f', row['guid']]) + '});'
    for row in native_objects)
native_creatures = spawn_rows('creature', {11956, 12296, 12298, 3234, 3236})
creature_init = '\n'.join('creatureSpawns.push_back(CreatureData{' + ','.join([
    row['id1'], row['id2'], row['id3'], row['map'], row['phaseMask'], row['guid'],
    str(float(row['position_x'])) + 'f', str(float(row['position_y'])) + 'f', str(float(row['position_z'])) + 'f']) + '});'
    for row in native_creatures)
source_monsters = sql_rows(core, 'creature_template', {3234, 3236})
creature_init += '\n' + '\n'.join('objectMgr.creatures[' + row['entry'] + ']={' + row['faction'] + ','
                                  + row['minlevel'] + '};' for row in source_monsters)
focus_init = '\n'.join(f'objectMgr.objects[{entry}].type=8;'
                       f'objectMgr.objects[{entry}].spellFocus={{{row["Data0"]},{row["Data1"]},{row["Data3"]}}};'
                       for entry, row in focus_templates.items())
loot_templates = sql_rows(core, 'gameobject_template', {177785, 177792, 177794, 177844, 177790, 177750})
assert {int(row['type']) for row in loot_templates} == {3}
native_go_loot = sql_rows(core, 'gameobject_loot_template', {int(row['Data1']) for row in loot_templates})
expected_sources = {177785: 15877, 177792: 15883, 177794: 15883, 177844: 15882, 177790: 15882, 177750: 15851}
for row in loot_templates:
    assert any(int(loot['Entry']) == int(row['Data1']) and int(loot['Item']) == expected_sources[int(row['entry'])]
               for loot in native_go_loot)
native_horn_loot = sql_rows(core, 'creature_loot_template', {int(row['lootid']) for row in source_monsters})
for row in source_monsters:
    assert any(int(loot['Entry']) == int(row['lootid']) and int(loot['Item']) == 15852 for loot in native_horn_loot)
drop_source = (module / 'Ai/Base/Value/LootValues.cpp').read_text()
drop_lookup = function(drop_source, 'LootTemplateAccess const* DropMapValue::GetLootTemplate(')
assert 'LootTemplates_Creature.GetLootFor(info->lootid)' in drop_lookup
assert 'LootTemplates_Gameobject.GetLootFor(info->GetLootId())' in drop_lookup
drop_map = function(drop_source, 'DropMap* DropMapValue::Calculate()')
assert 'dropMap->insert(std::make_pair(lItem->itemid, sEntry))' in drop_map
assert 'dropMap->insert(std::make_pair(lItem->itemid, -sEntry))' in drop_map
assert 'dropMap->equal_range(itemId)' in function(drop_source, 'std::vector<int32> ItemDropListValue::Calculate()')
native_store = function((core / 'src/server/game/Entities/Player/Player.cpp').read_text(),
                        'inline bool Player::_StoreOrEquipNewItem(')
assert 'CanStoreNewItem(' in native_store and 'ModifyMoney(-price)' in native_store and 'StoreNewItem(' in native_store
native_wants_item = function((core / 'src/server/game/Entities/Player/PlayerQuest.cpp').read_text(),
                             'bool Player::HasQuestForItem(')
assert 'qinfo->ItemDrop[j] == itemid' in native_wants_item and 'GetItemCount(itemid, true)' in native_wants_item
focus_init += '\n' + '\n'.join(f'objectMgr.objects[{row["entry"]}].type=3;' for row in loot_templates)
relations = []
for table, reward in (('creature_queststarter', False), ('creature_questender', True)):
    raw = (core / f'data/sql/base/db_world/{table}.sql').read_text()
    assert re.findall(r'^  `([^`]+)`', raw, re.MULTILINE) == ['id', 'quest']
    for entry, quest in re.findall(r'^\((\d+),(\d+)\)[,;]$', raw, re.MULTILINE):
        if int(quest) in expected_quests:
            relations.append((int(entry), int(quest), reward))
relation_init = '\n'.join(f'if(id=={quest}) AddNpc({entry}, {str(reward).lower()});'
                          for entry, quest, reward in relations)

callbacks = r'''
void Recount(Player& bot);
bool Player::HasQuestForItem(uint32 item)const {
    for(auto const& [id,status]:quests)if(status==QUEST_STATUS_INCOMPLETE) {
        auto const& quest=objectMgr.quests.at(id);
        for(uint32 i=0;i<6;++i)if(quest.RequiredItemId[i]==item&&GetItemCount(item)<quest.RequiredItemCount[i])return true;
        for(uint32 i=0;i<4;++i)if(quest.ItemDrop[i]==item){
            auto const* proto=objectMgr.GetItemTemplate(item);uint32 owned=GetItemCount(item,true);
            if(proto&&((proto->MaxCount&&int32(owned)<proto->MaxCount)||
               (quest.ItemDropQuantity[i]?owned<quest.ItemDropQuantity[i]:owned<proto->GetMaxStackSize())))return true;
        }
    }
    return false;
}
Creature* Player::GetNPCIfCanInteractWith(ObjectGuid guid,uint32 flags){
    auto* unit=ai?ai->GetUnit(guid):nullptr;auto* npc=unit?unit->ToCreature():nullptr;
    return interactAllowed&&npc&&npc->alive&&npc->inWorld&&!npc->removing&&IsInMap(npc)&&InSamePhase(npc)&&
        CanSeeOrDetect(npc)&&npc->IsWithinDistInMap(this,INTERACTION_DISTANCE)&&IsWithinLOSInMap(npc)&&
        (!flags||npc->HasNpcFlag(flags))?npc:nullptr;
}
int Player::GetFactionReactionTo(void const*,FactionTemplateEntry const* faction)const{return faction->id==999?1:REP_NEUTRAL;}
void Session::SendListInventory(ObjectGuid guid){++lists;
    if(player->GetNPCIfCanInteractWith(guid,UNIT_NPC_FLAG_VENDOR))vendorContext=alternateVendor;}
bool Player::BuyItemFromVendorSlot(ObjectGuid guid,uint32 slot,uint32 item,uint32,uint8,uint8){
    ++buys;auto* vendor=GetNPCIfCanInteractWith(guid,UNIT_NPC_FLAG_VENDOR);if(!vendor||vendor->hostile)return false;
    auto const* offers=session.vendorContext?objectMgr.GetNpcVendorItemList(session.vendorContext):vendor->GetVendorItems();
    auto const* offer=offers?offers->GetItem(slot):nullptr;auto const* proto=objectMgr.GetItemTemplate(item);
    if(!offer||offer->item!=item||offer->ExtendedCost||!proto||!storeAllowed)return false;
    uint32 price=uint32(std::floor(proto->BuyPrice*discount));
    if(!HasEnoughMoney(price)||(offer->maxcount&&vendor->stock<proto->BuyCount))return false;
    money-=price;if(offer->maxcount)vendor->stock-=proto->BuyCount;
    auto [position,inserted]=inventory.try_emplace(item);auto& owned=position->second;if(inserted)owned.count=0;
    owned.entry=item;owned.proto=*proto;owned.count+=proto->BuyCount;Recount(*this);
    return offer->maxcount!=0;
}
void Player::KilledMonsterCredit(uint32 entry){
    for(auto& [id,status]:quests)if(status==QUEST_STATUS_INCOMPLETE) {
        auto const& q=objectMgr.quests.at(id);auto& counts=credits[id];bool matched=false;
        for(uint32 i=0;i<4;++i)if(q.RequiredNpcOrGo[i]==int32(entry)&&counts[i]<q.RequiredNpcOrGoCount[i]){++counts[i];matched=true;}
        bool complete=matched;
        for(uint32 i=0;i<4;++i)if(counts[i]<q.RequiredNpcOrGoCount[i])complete=false;
        for(uint32 i=0;i<6;++i)if(GetItemCount(q.RequiredItemId[i])<q.RequiredItemCount[i])complete=false;
        if(complete)status=QUEST_STATUS_COMPLETE;
    }
}
enum {NPC_SICKLY_GAZELLE=12296,NPC_CURED_GAZELLE=12297,NPC_SICKLY_DEER=12298,NPC_CURED_DEER=12299};
using SpellEffIndex=int;
struct ApplySalve {
    Player* caster;Item* item;Creature* target;
    Player* GetCaster(){return caster;}Item* GetCastItem(){return item;}Creature* GetHitCreature(){return target;}
    @@SALVEHANDLER@@
};
void Recount(Player& bot) {
    for(auto& [id,status]:bot.quests)if(status==QUEST_STATUS_INCOMPLETE) {
        auto const& q=objectMgr.quests.at(id);bool complete=true,needed=false;
        for(uint32 i=0;i<6;++i)if(q.RequiredItemCount[i]){needed=true;if(bot.GetItemCount(q.RequiredItemId[i])<q.RequiredItemCount[i])complete=false;}
        if(needed&&complete)status=QUEST_STATUS_COMPLETE;
    }
}
void Player::FinishCast(){
    if(!casting||now<castDue)return;
    casting=false;Item* item=GetItemByEntry(pendingItem);
    if(!item)return;
    if(pendingSpell==19512){
        Unit* unit=ai->GetUnit({pendingTarget});Creature* creature=unit?unit->ToCreature():nullptr;
        ApplySalve{this,item,creature}.HandleDummy(0);
    }else if(pendingSpell==19564||pendingSpell==19565||pendingSpell==19720){
        uint32 output=pendingSpell==19564?15845:pendingSpell==19565?15843:15885;
        if(pendingSpell==19720){if(!HasItemCount(15882))return;inventory.erase(15882);}
        Item owned;owned.entry=output;owned.proto=objectMgr.items[output];inventory[output]=owned;
    }else if(pendingSpell==19719){
        for(uint32 id:{28u,29u})if(GetQuestStatus(id)==QUEST_STATUS_INCOMPLETE)quests[id]=QUEST_STATUS_COMPLETE;
    }else if(pendingSpell==18974||pendingSpell==19138){
        uint32 event=pendingSpell==18974?5991:6028;
        for(auto const& [delay,info]:sEventScripts.at(event))nativeSummons.emplace_back(info.TempSummonCreature.CreatureEntry,
            WorldPosition(mapId,info.TempSummonCreature.PosX,info.TempSummonCreature.PosY,info.TempSummonCreature.PosZ));
    }
    if(item->charges<0){++item->charges;if(!item->charges)inventory.erase(pendingItem);}
    Recount(*this);
}
bool PlayerbotAI::CanCastSpell(uint32 spell,Unit* target,bool,Item*,Item* item){
    ++castChecks;castItem=item;castTarget=target;
    if(!item||bot->GetItemByEntry(item->entry)!=item||!target||!target->alive||!target->inWorld||
       !bot->IsInMap(target)||!bot->InSamePhase(target)||!bot->CanSeeOrDetect(target)||!bot->IsWithinLOSInMap(target))return false;
    auto const* info=spellMgr.GetSpellInfo(spell);if(!info)return false;
    if(spell==19512)return (target->entry==12296||target->entry==12298)&&target->IsWithinDistInMap(bot,INTERACTION_DISTANCE);
    if(target!=bot)return false;
    if(spell==19720&&!bot->HasItemCount(15882))return false;
    GameObjectFocusCheck check(bot,info->RequiresSpellFocus);
    return std::any_of(objects.begin(),objects.end(),[&](auto const& pair){return check(pair.second);});
}
bool UseItemAction::UseItem(Item* item,ObjectGuid,Item*,Unit* target){
    uint32 spell=item?uint32(item->proto.Spells[0].SpellId):0;
    if(!botAI->castResult||!botAI->CanCastSpell(spell,target,false,nullptr,item))return false;
    ++botAI->casts;bot->pendingSpell=spell;bot->pendingItem=item->entry;bot->pendingTarget=target->guid;
    bot->casting=true;bot->channelled=false;bot->generic.castTime=spell==19512?1300:3000;
    bot->castDue=now+uint32(bot->generic.castTime);bot->FinishCast();return true;
}
bool LootObject::IsLootPossible(Player*)const {
    auto* object=bot->ai->GetGameObject(guid);return object&&object->lootPossible&&object->spawned&&object->inWorld&&
        bot->IsInMap(object)&&bot->InSamePhase(object)&&bot->CanSeeOrDetect(object);
}
void SetMenu(Player& player,ObjectGuid sender,uint32 id){
    auto& menu=player.talk.gossip;menu.id=id;menu.sender=sender;menu.entries.clear();menu.details.clear();
    if(id==3862){uint32 option=player.team==TEAM_HORDE?1:0;menu.entries[option]={};menu.details[option]={3863};}
    else {uint32 next=id==3882?3881:id==3881?3883:id==3883?3884:id==3884?3885:0;
        if(next){menu.entries[0]={};menu.details[0]={next};}}
}
void Session::HandleGossipHelloOpcode(WorldPacket& packet){
    ++hellos;ObjectGuid guid;packet>>guid;
    auto* npc=player->GetNPCIfCanInteractWith(guid,UNIT_NPC_FLAG_GOSSIP);
    if(allowHello&&npc)SetMenu(*player,guid,npc->entry==11956?3882:npc->entry==12144?3862:0);
}
void Session::HandleGossipSelectOptionOpcode(WorldPacket& packet){
    ObjectGuid guid;uint32 id,option;packet>>guid>>id>>option;
    auto& menu=player->talk.gossip;
    auto* npc=player->GetNPCIfCanInteractWith(guid,UNIT_NPC_FLAG_GOSSIP);
    if(!allowSelect||!menu.GetItem(option)||menu.sender!=guid||!npc)return;
    ++selections;selected.emplace_back(guid.value,id,option);
    // Native SmartAI receives menuId before Player::OnGossipSelect validates it.
    if(npc->entry==11956&&id==3884&&option==0){
        for(uint32 quest:{5929u,5930u})if(player->GetQuestStatus(quest)==QUEST_STATUS_INCOMPLETE)player->quests[quest]=QUEST_STATUS_COMPLETE;
    }else if(npc->entry==12144&&id==3862){uint32 quest=option==0?6001:6002;
        if(player->GetQuestStatus(quest)==QUEST_STATUS_INCOMPLETE)player->quests[quest]=QUEST_STATUS_COMPLETE;}
    if(id!=menu.id)return;
    auto const* details=menu.GetItemData(option);uint32 next=details?details->GossipActionMenuId:0;
    SetMenu(*player,guid,next);
}
void Session::HandleQuestLogRemoveQuest(WorldPackets::Quest::QuestLogRemoveQuest& request){
    ++removes;if(!allowRemove||request.Slot>=MAX_QUEST_LOG_SIZE)return;
    uint32 id=player->slots[request.Slot];player->quests.erase(id);player->slots[request.Slot]=0;
}
bool ClassQuestAction::InteractWithQuestGiver(Quest const* quest,bool reward){
    for(auto guid:context->npcs){auto* unit=botAI->GetUnit(guid);auto* npc=unit?unit->ToCreature():nullptr;
        if(!npc||!(reward?npc->ends:npc->starts).contains(quest->id)||!npc->inWorld||!bot->IsInMap(npc)||
            !bot->InSamePhase(npc)||!bot->CanSeeOrDetect(npc))continue;
        if(!npc->IsWithinDistInMap(bot,INTERACTION_DISTANCE))return MoveToQuestPosition(WorldPosition(npc));
        if(reward){++botAI->rewards;if(!botAI->rewardResult)return false;bot->quests[quest->id]=QUEST_STATUS_REWARDED;
            if(quest->id==6001||quest->id==6002||quest->id==31||quest->id==5061||quest->id==6125||quest->id==6130)
                bot->learned.insert(quest->goal);
        }else{++botAI->accepts;if(!botAI->acceptResult||!bot->CanTakeQuest(quest,false)||!bot->CanAddQuest(quest,false))return false;
            bot->quests[quest->id]=QUEST_STATUS_INCOMPLETE;
            if(quest->source){Item owned;owned.entry=quest->source;owned.proto=objectMgr.items[quest->source];
                owned.charges=owned.proto.Spells[0].SpellCharges;bot->inventory[owned.entry]=owned;}
        }
        return true;
    }
    return false;
}
'''

tests = r'''
struct Scenario {
    Player bot;PlayerbotAI ai{&bot};DruidClassQuestAction action{&ai};DruidClassQuestValue value{&ai};
    DruidClassQuestTrigger trigger{&ai};uint32 id;
    std::vector<std::unique_ptr<Creature>> creatures;std::vector<std::unique_ptr<GameObject>> objects;
    explicit Scenario(uint32 id=5929):id(id){
        now=100000;objectMgr={};spellMgr={};sPlayerbotAIConfig={};sFactionTemplateStore={};questLocations.clear();
        objectSpawns.clear();creatureSpawns.clear();itemDrops.clear();sEventScripts.clear();nativeSummons.clear();spawnScans=0;
        bot.ai=&ai;bot.guid=1;
        @@NATIVEINIT@@
        @@ITEMINIT@@
        @@SPELLINIT@@
        @@EVENTINIT@@
        @@FOCUSINIT@@
        @@OBJECTINIT@@
        @@CREATUREINIT@@
        spellMgr.spells[18974].Effects[0]={SPELL_EFFECT_SEND_EVENT,5991};
        spellMgr.spells[19138].Effects[0]={SPELL_EFFECT_SEND_EVENT,6028};
        itemDrops={{15877,{-177785}},{15883,{-177792,-177794}},{15882,{-177844,-177790}},
                   {15851,{-177750}},{15852,{3234,3236}}};
        auto const& q=objectMgr.quests.at(id);bot.level=q.level;
        if(q.races&&!(q.races&8)){bot.team=TEAM_HORDE;bot.race=32;}
        for(uint32 goal:{5487u,1066u,8946u})if(goal!=q.goal)bot.learned.insert(goal);
        bot.quests[id]=QUEST_STATUS_INCOMPLETE;bot.slots[0]=id;bot.available.insert(id);if(q.source)Give(q.source);
        @@RELATIONINIT@@
        ai.context.quest=value.Calculate();
    }
    void Give(uint32 entry,uint32 count=1){Item owned;owned.entry=entry;owned.count=count;owned.proto=objectMgr.items[entry];
        owned.charges=owned.proto.Spells[0].SpellCharges;bot.inventory[entry]=owned;}
    Creature* AddNpc(uint32 entry,bool reward=false){
        auto owned=std::make_unique<Creature>();auto* npc=owned.get();npc->entry=entry;npc->guid=uint32(ai.units.size()+10);
        npc->mapId=bot.mapId;npc->x=bot.x+2;npc->y=bot.y;npc->z=bot.z;npc->spawnId=npc->guid;npc->npcFlags=3;
        if(reward)npc->ends.insert(id);else npc->starts.insert(id);
        ai.units[npc->guid]=npc;ai.context.npcs.push_back(npc->GetGUID());
        questLocations[id][reward?32:16][int32(entry)].push_back(WorldPosition(npc));
        creatures.push_back(std::move(owned));return npc;
    }
    GameObject* AddObject(GameObjectData const& data){
        auto owned=std::make_unique<GameObject>();auto* go=owned.get();go->entry=data.id;go->spawnId=data.spawnId;
        go->guid=uint32(ai.objects.size()+500);go->mapId=data.mapid;go->phaseMask=data.phaseMask;
        go->x=data.posX;go->y=data.posY;go->z=data.posZ;go->info=objectMgr.objects[data.id];
        ai.objects[go->guid]=go;ai.context.objects.push_back(go->GetGUID());objects.push_back(std::move(owned));return go;
    }
    void Place(WorldPosition const& pos){bot.mapId=pos.map;bot.x=pos.x;bot.y=pos.y;bot.z=pos.z;}
    GameObject* Focus(uint32 item){
        Give(item);uint32 spell=uint32(objectMgr.items.at(item).Spells[0].SpellId);uint32 focus=spellMgr.spells.at(spell).RequiresSpellFocus;
        for(auto const& data:objectSpawns){auto t=objectMgr.objects.find(data.id);
            if(t==objectMgr.objects.end()||t->second.spellFocus.focusId!=focus)continue;
            if(spell==18974||spell==19138){auto const& event=sEventScripts.at(spell==18974?5991:6028).begin()->second;
                WorldPosition target(data.mapid,event.TempSummonCreature.PosX,event.TempSummonCreature.PosY,event.TempSummonCreature.PosZ);
                if(WorldPosition(data.mapid,data.posX,data.posY,data.posZ).GetExactDist(target)>100)continue;}
            Place(WorldPosition(data.mapid,data.posX,data.posY,data.posZ));return AddObject(data);
        }
        assert(false);return nullptr;
    }
    void Advance(uint32 elapsed){now+=elapsed;bot.FinishCast();ai.context.quest=value.Calculate();}
    GameObject* Source(uint32 entry){
        for(auto const& data:objectSpawns)if(data.id==entry){Place(WorldPosition(data.mapid,data.posX,data.posY,data.posZ));return AddObject(data);}
        assert(false);return nullptr;
    }
    Creature* Vendor(uint32 entry=844,uint32 stock=3,uint32 spawn=9000,float distance=2){
        auto* npc=AddNpc(entry);npc->npcFlags=UNIT_NPC_FLAG_VENDOR;npc->spawnId=spawn;npc->stock=stock;npc->x=bot.x+distance;
        npc->inventory.offers={{2449,3,0}};objectMgr.vendors[entry]=npc->inventory;
        objectMgr.creatures[entry]={35};sFactionTemplateStore.entries[35]={35};
        creatureSpawns.push_back({entry,0,0,npc->mapId,npc->phaseMask,spawn,npc->x,npc->y,npc->z});return npc;
    }
    void Offered(){bot.quests.erase(id);bot.inventory.clear();ai.context.quest=value.Calculate();}
};
int main(){
    for(uint32 id: {@@QUESTIDS@@}){
        Scenario s(id);assert(CurrentDruidClassQuest(&s.ai)&&CurrentDruidClassQuest(&s.ai)->Quest==id);
        assert(s.trigger.IsActive()&&s.action.isUseful());
    }
    for(uint32 id: {@@QUESTIDS@@}){
        Scenario s(id);s.Offered();assert(s.action.Execute({})&&s.bot.GetQuestStatus(id)!=QUEST_STATUS_NONE);
        s.bot.quests[id]=QUEST_STATUS_COMPLETE;assert(s.action.Execute({})&&s.bot.GetQuestRewardStatus(id));
    }
    {Scenario s;s.ai.canRun=false;assert(!CurrentDruidClassQuest(&s.ai)&&!s.trigger.IsActive()&&!s.action.isUseful()&&!s.action.Execute({}));}
    {Scenario s;s.bot.cls=CLASS_WARLOCK;assert(!CurrentDruidClassQuest(&s.ai));}
    {Scenario s;sPlayerbotAIConfig.IgnoredQuests.insert(s.id);assert(!CurrentDruidClassQuest(&s.ai));}
    {Scenario s;s.Offered();s.bot.takeAllowed=false;assert(!CurrentDruidClassQuest(&s.ai));}
    {Scenario s;s.Offered();s.bot.addAllowed=false;assert(!CurrentDruidClassQuest(&s.ai));}
    {Scenario s;s.bot.quests[s.id]=QUEST_STATUS_FAILED;assert(!CurrentDruidClassQuest(&s.ai));}
    {Scenario s;objectMgr.quests.erase(s.id);assert(!CurrentDruidClassQuest(&s.ai));}
    for(uint32 goal:{5487u,1066u,8946u}){
        Scenario s(goal==5487?5929:goal==1066?28:6124);s.bot.learned.insert(goal);
        assert(!CurrentDruidClassQuest(&s.ai)&&!s.action.Execute({}));
    }
    for(auto [id,final]:std::vector<std::pair<uint32,uint32>>{{5929,6001},{5930,6002},{28,31},{29,5061},{6124,6125},{6129,6130}}){
        Scenario s(id);s.bot.quests[final]=QUEST_STATUS_REWARDED;assert(!CurrentDruidClassQuest(&s.ai));
    }
    {Scenario s(5923);s.Offered();s.bot.available.clear();std::vector<uint32> offers;
        for(auto const& [id,q]:objectMgr.quests)if(q.goal==5487&&!q.previous&&(!q.races||(q.races&s.bot.race))){
            s.bot.available.insert(id);questLocations[id][16][10]={{1,100+float(offers.size())}};offers.push_back(id);}
        assert(offers.size()>1);auto near=offers.back();questLocations[near][16][10]={{1,1}};
        assert(CurrentDruidClassQuest(&s.ai)->Quest==near);s.bot.quests[offers.front()]=QUEST_STATUS_INCOMPLETE;
        assert(CurrentDruidClassQuest(&s.ai)->Quest==offers.front());
    }
    for(uint32 quest:{5929u,5930u}){
        Scenario s(quest);auto* spirit=s.AddNpc(11956);(void)spirit;
        for(uint32 step=0;step<5;++step)assert(s.action.Execute({}));
        assert(s.bot.GetQuestStatus(quest)==QUEST_STATUS_COMPLETE&&s.bot.session.hellos==1&&s.bot.session.selections==4);
        std::vector<uint32> menus;for(auto const& [guid,menu,option]:s.bot.session.selected){(void)guid;assert(option==0);menus.push_back(menu);}
        assert((menus==std::vector<uint32>{3882,3881,3883,3884}));
    }
    for(uint32 quest:{6001u,6002u}){
        Scenario s(quest);s.bot.inventory.clear();s.AddNpc(12144);
        assert(s.action.Execute({})&&s.action.Execute({}));
        assert(s.bot.GetQuestStatus(quest)==QUEST_STATUS_COMPLETE);
        assert(std::get<2>(s.bot.session.selected.back())==(quest==6001?0:1));
    }
    {Scenario s;auto* spirit=s.AddNpc(11956);SetMenu(s.bot,spirit->GetGUID(),3882);s.bot.talk.gossip.sender={999};
        assert(s.action.Execute({})&&s.bot.session.hellos==1&&s.bot.session.selections==0);}
    {Scenario s;auto* spirit=s.AddNpc(11956);SetMenu(s.bot,spirit->GetGUID(),9000);
        assert(s.action.Execute({})&&s.bot.session.hellos==1);}
    for(uint32 bad=0;bad<5;++bad){Scenario s;auto* spirit=s.AddNpc(11956);SetMenu(s.bot,spirit->GetGUID(),3882);
        if(bad==0)s.bot.talk.gossip.entries[0].IsCoded=true;
        if(bad==1)s.bot.talk.gossip.entries[0].BoxMoney=1;
        if(bad==2)s.bot.talk.gossip.entries[0].OptionType=2;
        if(bad==3)s.bot.talk.gossip.details[0].GossipActionMenuId=3884;
        if(bad==4)s.bot.talk.gossip.details.erase(0);
        assert(!s.action.Execute({})&&s.bot.session.selections==0&&s.bot.GetQuestStatus(s.id)==QUEST_STATUS_INCOMPLETE);}
    {Scenario s;auto* spirit=s.AddNpc(11956);spirit->x=40;assert(s.action.Execute({})&&s.ai.moves==1&&s.bot.session.hellos==0);}
    {Scenario s;s.AddNpc(11956);s.bot.interactAllowed=false;assert(!s.action.Execute({})&&s.bot.session.hellos==0);}
    for(auto [quest,item]:std::vector<std::pair<uint32,uint32>>{{28,15877},{29,15877},{6122,15844},{6127,15842}}){
        Scenario s(quest);s.Focus(item);assert(s.action.Execute({})&&s.ai.casts==1&&s.ai.castTarget==&s.bot);
        s.Advance(3000);assert(s.bot.GetQuestStatus(quest)==QUEST_STATUS_COMPLETE);
    }
    for(uint32 quest:{6001u,6002u}){
        Scenario s(quest);auto* focus=s.Focus(objectMgr.quests.at(quest).source);assert(s.action.Execute({})&&s.ai.casts==1&&s.ai.waits==1);
        assert(!s.action.Execute({}));s.Advance(3000);assert(!s.bot.HasItemCount(objectMgr.quests.at(quest).source));
        assert(nativeSummons.size()==1&&nativeSummons[0].first==12138);
        assert(WorldPosition(focus).GetExactDist(nativeSummons[0].second)<100);
    }
    {Scenario s(6001);auto* correct=s.Focus(15208);WorldPosition wanted(correct);s.ai.context.objects.clear();
        auto const& info=sEventScripts.at(6028).begin()->second;
        for(auto const& data:objectSpawns)if(data.id==177525&&WorldPosition(data.mapid,data.posX,data.posY,data.posZ).GetExactDist(
            {data.mapid,info.TempSummonCreature.PosX,info.TempSummonCreature.PosY,info.TempSummonCreature.PosZ})<100){
                s.Place({data.mapid,data.posX,data.posY,data.posZ});s.AddObject(data);break;}
        assert(s.action.Execute({})&&s.ai.moves==1&&s.ai.movedTo==wanted&&s.ai.casts==0);}
    {Scenario s(6001);s.Focus(15208);sEventScripts.clear();assert(!s.action.Execute({})&&s.ai.casts==0&&s.ai.moves==0);}
    {Scenario s(6001);s.Focus(15208);s.bot.inventory.clear();s.bot.bank[15208]=1;
        assert(!s.action.Execute({})&&s.bot.session.removes==0&&s.ai.moves==0);}
    {Scenario s(6001);s.Focus(15208);s.bot.inventory.clear();auto const& info=sEventScripts.at(5991).begin()->second;
        s.Place({1,info.TempSummonCreature.PosX,info.TempSummonCreature.PosY,info.TempSummonCreature.PosZ});
        assert(s.action.Execute({})&&s.bot.session.removes==0);s.Advance(44999);assert(s.action.Execute({})&&s.bot.session.removes==0);
        s.Advance(1);assert(s.action.Execute({})&&s.bot.session.removes==1&&s.bot.GetQuestStatus(s.id)==QUEST_STATUS_NONE);}
    {Scenario s(6001);s.Focus(15208);s.bot.inventory.clear();auto const& info=sEventScripts.at(5991).begin()->second;
        s.Place({1,info.TempSummonCreature.PosX,info.TempSummonCreature.PosY,info.TempSummonCreature.PosZ});
        assert(s.action.Execute({}));s.Advance(45000);s.bot.session.allowRemove=false;
        assert(!s.action.Execute({})&&s.bot.GetQuestStatus(s.id)==QUEST_STATUS_INCOMPLETE);}
    for(uint32 kind=0;kind<3;++kind){Scenario s(6001);s.Focus(15208);s.bot.inventory.clear();
        auto const& info=sEventScripts.at(5991).begin()->second;s.Place({1,info.TempSummonCreature.PosX,info.TempSummonCreature.PosY,info.TempSummonCreature.PosZ});
        s.action.Execute({});s.Advance(45000);auto& quest=objectMgr.quests.at(s.id);
        if(kind==0)quest.RequiredNpcOrGo[0]=1;
        if(kind==1)quest.ItemDrop[0]=1;
        if(kind==2)quest.RequiredItemId[0]=1;
        assert(!s.action.Execute({})&&s.bot.session.removes==0);}
    {Scenario s(6001);s.bot.inventory.clear();auto* luna=s.AddNpc(12138);luna->x=40;
        assert(s.action.Execute({})&&s.ai.moves==1&&s.ai.casts==0);}
    {Scenario s(6001);s.bot.inventory.clear();s.AddNpc(12138);assert(!s.action.Execute({})&&s.ai.casts==0&&s.bot.session.removes==0);}
    for(uint32 quest:{30u,272u}){Scenario s(quest);s.Give(15882);s.Focus(15883);
        assert(s.action.Execute({}));s.Advance(3000);assert(s.bot.HasItemCount(15885)&&!s.bot.HasItemCount(15882)&&!s.bot.HasItemCount(15883));
        assert(s.bot.GetQuestStatus(quest)==QUEST_STATUS_COMPLETE);}
    {Scenario s(6122);s.Focus(15844);s.bot.inventory.erase(15844);assert(!s.action.Execute({})&&s.ai.casts==0&&s.ai.moves==0);}
    {Scenario s(6122);s.Focus(15844);s.bot.inventory.erase(15844);s.bot.x+=100;
        assert(!s.action.Execute({})&&s.ai.moves==0);}
    {Scenario s(6122);auto* focus=s.Focus(15844);focus->spawned=false;s.bot.form=true;
        assert(!s.action.Execute({})&&s.ai.casts==0&&s.ai.castChecks==0&&s.ai.moves==0&&s.bot.form&&s.bot.unshifts==0&&s.bot.stops==0);}
    {Scenario s(6122);auto* focus=s.Focus(15844);focus->phaseMask=2;s.bot.form=true;
        assert(!s.action.Execute({})&&s.ai.casts==0&&s.ai.castChecks==0&&s.ai.moves==0&&s.bot.form&&s.bot.unshifts==0&&s.bot.stops==0);}
    {Scenario s(6122);auto* focus=s.Focus(15844);focus->visible=false;assert(s.action.Execute({})&&s.ai.casts==1);}
    {Scenario s(6122);s.Focus(15844);s.ai.castResult=false;assert(!s.action.Execute({})&&s.ai.waits==0);}
    {Scenario s(6122);s.Focus(15844);spellMgr.spells.clear();assert(!s.action.Execute({})&&s.ai.moves==0&&s.ai.casts==0);}
    {Scenario s(6122);auto* focus=s.Focus(15844);focus->entry=999;assert(!s.action.Execute({})&&s.ai.casts==0);}
    {Scenario s(6122);s.Focus(15844);s.bot.x+=100;assert(s.action.Execute({})&&s.ai.moves==1&&s.ai.casts==0);}
    {Scenario s(6122);auto* focus=s.Focus(15844);focus->info.type=3;s.bot.form=true;
        assert(!s.action.Execute({})&&s.bot.form&&s.ai.casts==0&&s.ai.castChecks==0&&s.ai.moves==0&&s.bot.unshifts==0&&s.bot.stops==0);}
    {Scenario s(6122);auto* focus=s.Focus(15844);focus->x+=6;s.bot.form=true;
        assert(!s.action.Execute({})&&s.bot.form&&s.ai.casts==0&&s.ai.castChecks==0&&s.ai.moves==0&&s.bot.unshifts==0&&s.bot.stops==0);}
    {Scenario s(6122);s.Focus(15844);s.ai.castResult=false;s.action.Execute({});
        spellMgr.spells[19564].RequiresSpellFocus=1004;s.Focus(15844);s.ai.castResult=true;
        assert(s.action.Execute({})&&s.ai.casts==1&&s.ai.moves==0);}
    {Scenario s(6122);s.ai.context.objects.clear();s.bot.mapId=0;s.ai.routes=false;
        assert(!s.action.Execute({})&&s.ai.moves==0);s.bot.mapId=1;assert(s.action.Execute({})&&s.ai.moves==1);}
    {Scenario s(6122);s.ai.context.objects.clear();s.bot.mapId=0;s.ai.routes=false;
        assert(!s.action.Execute({}));s.ai.routes=true;s.Advance(59999);assert(!s.action.Execute({}));
        s.Advance(1);assert(s.action.Execute({})&&s.ai.moves==1);}
    for(uint32 quest:{6124u,6129u}){
        Scenario s(quest);for(uint32 i=0;i<10;++i)s.AddNpc(quest==6124?12298:12296);
        for(uint32 i=0;i<10;++i){assert(s.action.Execute({}));assert(s.bot.GetQuestStatus(quest)==QUEST_STATUS_INCOMPLETE);
            s.Advance(1300);}
        assert(s.bot.GetQuestStatus(quest)==QUEST_STATUS_COMPLETE&&!s.bot.HasItemCount(15826));
        assert(s.ai.waits==10);
        for(auto const& creature:s.creatures)if(creature->entry==12299||creature->entry==12297){
            assert(creature->motion.fleeing&&creature->despawn==30000&&creature->unitFlags);}
    }
    {Scenario s(6124);s.bot.inventory.erase(15826);s.AddNpc(12298);assert(!s.action.Execute({})&&s.ai.casts==0);}
    {Scenario s(6124);s.bot.inventory.erase(15826);auto* sick=s.AddNpc(12298);sick->x=40;
        assert(!s.action.Execute({})&&s.ai.moves==0);}
    {Scenario s(6124);auto* wrong=s.AddNpc(12296);auto* right=s.AddNpc(12298);right->x=3;
        assert(s.action.Execute({})&&s.ai.castTarget==right&&s.ai.castTarget!=wrong);}
    {Scenario s(6124);auto* sick=s.AddNpc(12298);sick->x=40;assert(s.action.Execute({})&&s.ai.moves==1&&s.ai.casts==0);}
    {Scenario s(6124);s.AddNpc(12299);s.ai.context.npcs.erase(s.ai.context.npcs.begin(),s.ai.context.npcs.end());
        assert(s.action.Execute({})&&s.ai.moves==1&&s.ai.casts==0);}
    {Scenario s(6124);s.ai.context.npcs.clear();auto const first=*std::find_if(creatureSpawns.begin(),creatureSpawns.end(),
        [](auto const& spawn){return spawn.id==12298;});s.Place({first.mapid,first.posX,first.posY,first.posZ});
        assert(!s.action.Execute({}));assert(s.action.Execute({})&&s.ai.moves==1&&
            s.ai.movedTo!=WorldPosition(first.mapid,first.posX,first.posY,first.posZ));}
    {Scenario s(6124);s.ai.context.npcs.clear();for(auto& spawn:creatureSpawns)if(spawn.id==12298)spawn.phaseMask=2;
        assert(!s.action.Execute({})&&s.ai.moves==0);}
    {Scenario s(28);auto* chest=s.Source(177785);assert(!s.action.Execute({})&&s.ai.context.loot.queued.size()==1);
        assert(s.bot.GetItemCount(15877)==0&&!s.ai.context.loot.pending);
        s.ai.context.loot.pending=true;assert(s.action.Execute({})&&s.ai.context.loot.queued.size()==1);
        (void)chest;}
    {Scenario s(28);auto* chest=s.Source(177785);chest->lootPossible=false;assert(!s.action.Execute({})&&s.ai.context.loot.queued.empty());}
    {Scenario s(28);s.Source(177785);sPlayerbotAIConfig.DisallowedGameObjects.insert(177785);
        assert(!s.action.Execute({})&&s.ai.context.loot.queued.empty());}
    {Scenario s(28);s.Source(177785);s.bot.x+=100;sPlayerbotAIConfig.DisallowedGameObjects.insert(177785);
        assert(!s.action.Execute({})&&s.ai.moves==0);}
    {Scenario s(28);s.Source(177785);s.bot.lootGuid={999};assert(s.action.Execute({})&&s.ai.context.loot.queued.empty());}
    {Scenario s(30);s.bot.bank[15882]=1;s.Source(177844);assert(!s.action.Execute({})&&s.ai.context.loot.queued.empty());}
    {Scenario s(6123);s.Give(2449,5);s.Source(177750);s.Vendor();
        assert(!s.action.Execute({})&&s.ai.context.loot.queued.size()==1&&s.ai.objectives==0&&s.bot.buys==0&&s.bot.GetItemCount(2449)==5);}
    {Scenario s(6128);s.Give(2449,5);for(auto const& spawn:creatureSpawns)if(spawn.id==3234){
        s.Place({spawn.mapid,spawn.posX,spawn.posY,spawn.posZ});break;}
        assert(!s.action.Execute({})&&std::get_if<NewRpgInfo::DoQuest>(&s.ai.rpgInfo.data)->questId==6128&&s.ai.objectives==0);}
    {Scenario s(6128);s.Give(2449,5);creatureSpawns.erase(std::remove_if(creatureSpawns.begin(),creatureSpawns.end(),
        [](auto const& spawn){return spawn.id==3234;}),creatureSpawns.end());
        assert(!s.action.Execute({})&&s.ai.moves==0&&!std::get_if<NewRpgInfo::DoQuest>(&s.ai.rpgInfo.data));}
    {Scenario s(6128);s.Give(2449,5);s.bot.level=15;
        creatureSpawns.erase(std::remove_if(creatureSpawns.begin(),creatureSpawns.end(),[](auto const& spawn){return spawn.id==3234;}),creatureSpawns.end());
        for(auto const& spawn:creatureSpawns)if(spawn.id==3236){s.Place({spawn.mapid,spawn.posX,spawn.posY,spawn.posZ});break;}
        assert(!s.action.Execute({})&&std::get_if<NewRpgInfo::DoQuest>(&s.ai.rpgInfo.data));}
    {Scenario s(6128);s.Give(2449,5);for(auto const& spawn:creatureSpawns)if(spawn.id==3236){
        s.Place({spawn.mapid,spawn.posX,spawn.posY,spawn.posZ});break;}
        assert(s.action.Execute({})&&s.ai.moves==1);
        assert(std::any_of(creatureSpawns.begin(),creatureSpawns.end(),[&](auto const& spawn){return spawn.id==3234&&
            s.ai.movedTo==WorldPosition(spawn.mapid,spawn.posX,spawn.posY,spawn.posZ);}));}
    {Scenario s(6123);s.Give(15851,12);auto* first=s.Vendor(844,3,9000,2);auto* second=s.Vendor(1302,3,9001,3);
        uint32 before=s.bot.money,price=objectMgr.items.at(2449).BuyPrice;
        for(uint32 i=0;i<6;++i)s.action.Execute({});
        assert(s.bot.GetItemCount(2449)==5&&s.bot.buys==5&&s.bot.money==before-price*5&&first->stock==0&&second->stock==1);}
    {Scenario s(6123);s.Give(15851,12);auto* vendor=s.Vendor();vendor->inventory.offers[0].maxcount=0;vendor->stock=0;
        objectMgr.vendors[844]=vendor->inventory;assert(s.action.Execute({})&&s.bot.GetItemCount(2449)==1&&s.bot.buys==1);}
    {Scenario s(6123);s.Give(15851,12);s.Vendor();s.bot.money=0;
        assert(!s.action.Execute({})&&s.bot.buys==0&&s.bot.GetItemCount(2449)==0);}
    {Scenario s(6123);s.Give(15851,12);s.Vendor();s.bot.money=objectMgr.items.at(2449).BuyPrice-1;
        assert(!s.action.Execute({})&&s.bot.buys==0&&s.bot.GetItemCount(2449)==0);}
    {Scenario s(6123);s.Give(15851,12);s.Vendor(844,0);
        assert(!s.action.Execute({})&&s.bot.buys==0);}
    {Scenario s(6123);s.Give(15851,12);s.Vendor();s.bot.interactAllowed=false;
        assert(!s.action.Execute({})&&s.bot.session.lists==0&&s.bot.buys==0);}
    {Scenario s(6123);s.Give(15851,12);auto* vendor=s.Vendor();vendor->inventory.offers[0].ExtendedCost=1;
        objectMgr.vendors[844]=vendor->inventory;assert(!s.action.Execute({})&&s.bot.buys==0);}
    {Scenario s(6123);s.Give(15851,12);s.Vendor();s.bot.session.alternateVendor=9009;objectMgr.vendors[9009].offers={{1,3,0}};
        assert(!s.action.Execute({})&&s.bot.buys==0);}
    {Scenario s(6123);s.Give(15851,12);s.Vendor();s.bot.storeAllowed=false;
        assert(!s.action.Execute({})&&s.bot.buys==1&&s.bot.GetItemCount(2449)==0);s.bot.storeAllowed=true;
        assert(!s.action.Execute({})&&s.bot.buys==1);s.Advance(10*MINUTE*IN_MILLISECONDS);
        assert(s.action.Execute({})&&s.bot.GetItemCount(2449)==1);}
    {Scenario s(6123);s.Give(15851,12);auto* vendor=s.Vendor();vendor->inventory.offers.insert(vendor->inventory.offers.begin(),{1,0,0});
        objectMgr.vendors[844]=vendor->inventory;s.bot.session.alternateVendor=9009;objectMgr.vendors[9009].offers={{2449,3,0}};
        assert(s.action.Execute({})&&s.bot.GetItemCount(2449)==1&&s.bot.session.lists==1);}
    std::cout<<"Druid class quests: native32, actual spirit dialogue, owned focuses and native salve credit passed\n";
}
'''

replacements = {
    'nativeinit': native_init, 'iteminit': item_init, 'spellinit': spell_init,
    'eventinit': event_init, 'focusinit': focus_init, 'objectinit': object_init,
    'creatureinit': creature_init, 'relationinit': relation_init,
    'questids': ','.join(str(quest) + 'u' for quest in expected_quests),
    'salvehandler': salve_handler,
}


def build(directory, parts, name):
    text = prelude + callbacks + tests
    for key, value in {**parts, **replacements}.items():
        text = text.replace('@@' + key.upper() + '@@', value)
    assert '@@' not in text
    path = directory / (name + '.cpp')
    path.write_text(text)
    binary = directory / name
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-missing-field-initializers',
                    *SANITIZER_FLAGS, str(path), '-o', str(binary)], check=True)
    return run_fixture([str(binary)])


mutations = [
    ('live selector checks random-bot ownership', 'current', 'if (!CanRunClassQuest(botAI, CLASS_DRUID))', 'if (false)'),
    ('selector requests the actual Druid class', 'current', 'CanRunClassQuest(botAI, CLASS_DRUID)', 'CanRunClassQuest(botAI, CLASS_WARLOCK)'),
    ('cached trigger rechecks ownership', 'trigger', 'CanRunClassQuest(botAI, CLASS_DRUID) &&', ''),
    ('cached action rechecks ownership', 'useful', 'CanRunClassQuest(botAI, CLASS_DRUID) &&', ''),
    ('execution rechecks the live selected quest', 'execute', 'if (!data)', 'if (false)'),
    ('known class spell stops its completed family', 'table', 'if (bot->HasSpell(spell))', 'if (false)'),
    ('ignored quests remain ignored while active', 'current', 'sPlayerbotAIConfig.IgnoredQuests.count(data.Quest) ||', ''),
    ('missing native templates are rejected', 'current', 'if (!quest)', 'if (false)'),
    ('native quest eligibility is required', 'current', '!bot->CanTakeQuest(quest, false) ||', ''),
    ('native quest-log space is required', 'current', '|| !bot->CanAddQuest(quest, false)', ''),
    ('active earned quests precede nearby alternatives', 'current', 'return &data;', 'continue;'),
    ('nearest available native giver selected', 'current', 'distance < nearest', 'distance < nearest && !selected'),
    ('nearby targets must match the requested creature', 'table', 'creature->GetEntry() != entry ||', 'entry == 0 ||'),
    ('gossip opens the selected spirit menu', 'talk', 'menu.GetSenderGUID() != spirit->GetGUID() ||', ''),
    ('unrecognized menus require a fresh hello', 'talk', '|| !allowed)', '|| (!allowed && current == 0))'),
    ('gossip refuses coded options', 'talk', 'option.second.IsCoded ||', ''),
    ('gossip refuses paid options', 'talk', 'option.second.BoxMoney ||', ''),
    ('gossip requires the native dialogue option type', 'talk', 'option.second.OptionType != GOSSIP_OPTION_GOSSIP ||', ''),
    ('gossip requires current option details', 'talk', '!details ||', ''),
    ('gossip follows the actual native next menu', 'talk', 'details->GossipActionMenuId != next', '(details->GossipActionMenuId != next && false)'),
    ('gossip packets carry the real current menu', 'talk', '<< menu.GetMenuId() << option.first', '<< uint32(3884) << option.first'),
    ('gossip packets preserve Horde list id one', 'talk', '<< option.first;', '<< uint32(0);'),
    ('spirit interaction observes native range', 'talk', '!spirit->IsWithinDistInMap(bot, INTERACTION_DISTANCE)', 'false'),
    ('spirit uses the native interaction permission', 'talk', '!bot->GetNPCIfCanInteractWith(spirit->GetGUID(), UNIT_NPC_FLAG_GOSSIP)', 'false'),
    ('owned focus item is required before travelling', 'focused', 'if (!item)', 'if (false)'),
    ('native spell must resolve before focus lookup', 'focusposition', '!spell ||', ''),
    ('runtime focus changes invalidate cached destinations', 'focusposition', '_focusId == spell->RequiresSpellFocus', '_focusId != 0'),
    ('map changes invalidate cached focus failures', 'focusposition', '_focusMap == bot->GetMapId() &&', ''),
    ('cached focus failures expire', 'focusposition', 'GetMSTimeDiffToNow(_focusChecked) < MINUTE * IN_MILLISECONDS', 'true'),
    ('ritual dust requires its native summon event', 'focusposition', 'if (!summon)', 'if (false)'),
    ('shared Moonkin focus is anchored to the correct faction event', 'focusposition', 'pos.GetExactDist(target) > 100.0f', 'false'),
    ('Darkshore focus permits its actual sixty-yard event offset', 'focusposition', 'pos.GetExactDist(target) > 100.0f', 'pos.GetExactDist(target) > 10.0f'),
    ('focused casting rejects a missing destination', 'focused', 'if (pos == WorldPosition())', 'if (false)'),
    ('focused casting uses the selected native entry', 'focused', 'focus->GetEntry() != _focusEntry ||', ''),
    ('focused casting observes spawned state', 'focused', '!focus->isSpawned() ||', ''),
    ('focused casting observes phase', 'focused', '!bot->InSamePhase(focus) ||', ''),
    ('focused casting observes object type before unshifting', 'focused', 'focus->GetGoType() != GAMEOBJECT_TYPE_SPELL_FOCUS ||', ''),
    ('focused casting verifies the chosen spawn position', 'focused', 'focus->GetExactDist(pos) > INTERACTION_DISTANCE', 'false'),
    ('focused casting walks into native focus range', 'focused', '!focus->IsWithinDistInMap(bot, focus->GetGOInfo()->spellFocus.dist)', 'false'),
    ('focused item targets its owner', 'focused', 'UseItemOnUnit(item, bot)', 'UseItemOnUnit(item, nullptr)'),
    ('focused item must actually pass native casting', 'focused', 'if (!UseItemAction(botAI).UseItemOnUnit(item, bot))',
     'if (!UseItemAction(botAI).UseItemOnUnit(item, bot) && false)'),
    ('source loot must still be needed by the native quest', 'gather', 'if (!bot->HasQuestForItem(itemId))', 'if (false)'),
    ('active loot response is not interrupted', 'gather', 'AI_VALUE(LootObjectStack*, "available loot")->IsLootPending() ||', ''),
    ('current loot guid prevents opening a second source', 'gather', '|| bot->GetLootGUID()', ''),
    ('disallowed objects are not selected as destinations', 'gather', '!sPlayerbotAIConfig.DisallowedGameObjects.contains(uint32(-entry))', 'true'),
    ('creature loot sources respect the native grind level limit', 'gather', '> MaximumQuestGrindLevelDifference', '> MaximumQuestGrindLevelDifference + 100'),
    ('creature source establishes ordinary quest grinding', 'gather', 'if (!state || state->questId != quest->GetQuestId())', 'if (state && state->questId == quest->GetQuestId())'),
    ('ordinary gathering yields after queueing loot', 'gather', 'return false;  // Ordinary loot, movement and opening actions must be allowed to run.',
     'return true;  // Ordinary loot, movement and opening actions must be allowed to run.'),
    ('salve maps the correct racial sick species', 'cure', '? 12298 : 12296', '? 12296 : 12298'),
    ('salve requires an owned charged item', 'cure', 'if (!salve)', 'if (false)'),
    ('salve approaches its actual creature target', 'cure', '!sick->IsWithinDistInMap(bot, INTERACTION_DISTANCE)', 'false'),
    ('salve waits for its native cast', 'cure', 'GetCurrentSpell(CURRENT_GENERIC_SPELL)', 'GetCurrentSpell(CURRENT_CHANNELED_SPELL)'),
    ('sick spawn selection preserves native phase', 'cure', '!(spawn->phaseMask & bot->GetPhaseMask()) ||', 'false ||'),
    ('empty sick spawns are temporarily skipped', 'cure', 'GetMSTimeDiffToNow(blocked->second) < MINUTE * IN_MILLISECONDS', 'false'),
    ('nearby Lunaclaw yields to ordinary combat', 'body', 'MoveToQuestPosition(WorldPosition(lunaclaw)) : false', 'MoveToQuestPosition(WorldPosition(lunaclaw)) : true'),
    ('banked dust cannot be replaced through abandonment', 'body', 'if (bot->HasItemCount(itemId, 1, true))', 'if (false)'),
    ('missing dust waits for the native event', 'body', 'GetMSTimeDiffToNow(_bearMissingSince) < 45 * IN_MILLISECONDS', 'false'),
    ('abandonment verifies native handler success', 'restart', 'if (bot->GetQuestStatus(id) != QUEST_STATUS_NONE)', 'if (false)'),
    ('abandonment preserves native creature objectives', 'restart', 'quest->RequiredNpcOrGo[index] ||', ''),
    ('abandonment preserves native source-drop objectives', 'restart', '|| quest->ItemDrop[index]', ''),
    ('abandonment preserves native required items', 'restart', 'if (item)', 'if (item && false)'),
    ('Earthroot purchases stop when the recipe already owns enough', 'earthroot', 'bot->GetItemCount(itemId, false) >= required ||', ''),
    ('Earthroot vendor selection uses the actual current offer', 'earthroot', '&& !offer->ExtendedCost', ''),
    ('failed vendor sources enter a bounded cooldown', 'earthroot', 'GetMSTimeDiffToNow(blocked->second) < 10 * MINUTE * IN_MILLISECONDS', 'false'),
    ('failed vendors invalidate the cached destination', 'earthroot', '_rootChecked = 0;', ''),
    ('vendor access uses the native interaction permission', 'earthroot', '!bot->GetNPCIfCanInteractWith(guid, UNIT_NPC_FLAG_VENDOR)', 'false'),
    ('vendor slot is resolved after opening the native context', 'earthroot',
     'vendorContext ? sObjectMgr->GetNpcVendorItemList(vendorContext) : vendor->GetVendorItems()',
     '(static_cast<void>(vendorContext), vendor->GetVendorItems())'),
    ('limited vendor stock is checked before purchase', 'earthroot', 'vendor->GetVendorItemCurrentCount(offer) < proto->BuyCount', 'false'),
    ('own funds are checked before purchase', 'earthroot', '!bot->HasEnoughMoney(price)', '(!bot->HasEnoughMoney(price) && false)'),
    ('unlimited-stock purchases use owned item growth rather than the false native return', 'earthroot',
     'bot->GetItemCount(itemId, false) > before', '(bot->GetItemCount(itemId, false) > before && false)'),
]
for final in (6001, 6002, 31, 5061, 6125, 6130):
    old = f'bot->GetQuestRewardStatus({final})'
    mutations.append((f'earned final quest {final} stops its family', 'table', old, 'false'))
for label, key, old, _ in mutations:
    assert old in production[key], label


with tempfile.TemporaryDirectory(prefix='portable-druid-quests-') as temporary:
    directory = Path(temporary)
    result = build(directory, production, 'druid')
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit('Druid class quest fixture failed')

    def rejected(numbered):
        index, (label, key, old, new) = numbered
        assert old in production[key], label
        mutant = {**production, key: production[key].replace(old, new)}
        return build(directory, mutant, f'mutant-{index}').returncode != 0

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = pool.map(rejected, enumerate(mutations))
        survivors = []
        for (label, *_), rejected_mutant in zip(mutations, results):
            if not rejected_mutant:
                survivors.append(label)
                print('Druid class quest mutation survived: ' + label, flush=True)
            else:
                print('Druid class quest mutation rejected: ' + label, flush=True)
        if survivors:
            raise SystemExit('Druid class quest mutations survived: ' + '; '.join(survivors))
