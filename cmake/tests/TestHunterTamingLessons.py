"""Exercise native hunter lesson acquisition, rods, travel and ordinary turn-ins.

The lesson table is checked against named native quest/item/condition/spawn fields.
Production selection and actions run with native-shaped adapters; mutations must fail.
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
    prepared_core,
    reject_part_mutants,
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
hunter = module / 'Ai/Class/Hunter'
source = (hunter / 'HunterTamingLessons.cpp').read_text()
header = (hunter / 'HunterTamingLessons.h').read_text()
actions = (hunter / 'HunterActions.cpp').read_text()
items = (module / 'Ai/Base/Actions/UseItemAction.cpp').read_text()
lessons = [tuple(map(int, row)) for row in re.findall(
    r'\{(\d+), (\d+), (\d+), (\d+)\}', source)]
assert len(lessons) == 24 and len({row[0] for row in lessons}) == 24
quests = {int(row['ID']): row for row in sql_rows(core, 'quest_template', {r[0] for r in lessons})}
addon = {int(row['ID']): row for row in sql_rows(core, 'quest_template_addon', set(quests))}
item_rows = {int(row['entry']): row for row in sql_rows(core, 'item_template', {r[1] for r in lessons if r[1]})}
conditions = sql_rows(core, 'conditions', {17})
templates = sql_rows(core, 'creature_template', {r[3] for r in lessons if r[3]})
assert len(templates) == 18
for quest, item, spell, creature in lessons:
    q = quests[quest]
    assert int(addon[quest]['AllowableClasses']) == 4
    assert int(q['StartItem']) == item
    assert int(q['RewardNextQuest']) in set(quests) | {0}
    assert int(q['RewardChoiceItemID1']) == 0
    if item:
        assert int(item_rows[item]['spellid_1']) == spell
        assert int(item_rows[item]['spelltrigger_1']) == 0
        assert any(int(row['SourceEntry']) == spell and int(row['ConditionTypeOrReference']) == 31
                   and int(row['ConditionTarget']) == 1 and int(row['ConditionValue1']) == 3
                   and int(row['ConditionValue2']) == creature and int(row['NegativeCondition']) == 0
                   for row in conditions)
        assert int(q['RewardSpell']) in (0, 1579)
    else:
        assert int(q['RewardSpell']) == 5300 and int(q['Flags']) & 8
assert sum(int(q['RewardSpell']) == 1579 for q in quests.values()) == 6
assert sum(int(q['RewardSpell']) == 5300 for q in quests.values()) == 6
for quest, races in ((6061, 32), (6062, 130), (6063, 8), (6064, 4), (9484, 512), (9591, 1024)):
    assert int(quests[quest]['MinLevel']) == 10 and int(quests[quest]['AllowableRaces']) == races
for quest, item, _, _ in lessons:
    if item:
        assert int(addon[quest]['ProvidedItemCount']) == 1
    previous = int(addon[quest]['PrevQuestID'])
    if previous:
        assert abs(previous) in set(quests)

context_source = (hunter / 'HunterAiObjectContext.cpp').read_text()
for factory in ('HunterTriggerFactoryInternal', 'HunterAiObjectContextInternal', 'HunterValueFactoryInternal'):
    assert f'creators["hunter taming lesson"] = &{factory}::hunter_taming_lesson;' in context_source
assert 'valueContexts.Add(new HunterValueFactoryInternal());' in context_source
assert 'CalculatedValue(botAI, "hunter taming lesson", 5)' in header
assert 'Trigger(botAI, "hunter taming lesson", 5)' in header
strategy = (hunter / 'Strategy/GenericHunterNonCombatStrategy.cpp').read_text()
assert 'NextAction("hunter taming lesson", ACTION_NORMAL + 2)' in strategy

# Exact spawns exist, and the native helper returns real rows on the origin map.
spawn_text = (core / 'data/sql/base/db_world/creature.sql').read_text()
spawn_columns = re.findall(r'^  `([^`]+)`', spawn_text, re.MULTILINE)
assert spawn_columns[1] == 'id1'
spawn_entries = {int(line.split(',', 2)[1]) for line in spawn_text.splitlines() if line.startswith('(')}
assert {r[3] for r in lessons if r[3]} <= spawn_entries
travel = (module / 'Mgr/Travel/TravelMgr.cpp').read_text()
assert 'creatureData.mapid == point.GetMapId()' in function(travel, 'void FindPointCreatureData::operator()(')
assert 'worker(itr.second)' in function(travel, 'std::vector<CreatureData const*> WorldPosition::getCreaturesNear(')
cast_source = function(items, 'bool UseItemAction::UseItem(Item* item, ObjectGuid goGuid, Item* itemTarget, Unit* unitTarget)')
assert 'packet << targetFlag << unitTarget->GetGUID().WriteAsPacked();' in cast_source
assert 'bot->GetSession()->HandleUseItemOpcode(packet);' in cast_source
precheck = function(cast_source, '    for (uint8 i = 0; i < spellSlotLimit; ++i)')
quest_handler = (core / 'src/server/game/Handlers/QuestHandler.cpp').read_text()
assert 'CanTakeQuest' in function(quest_handler, 'void WorldSession::HandleQuestgiverAcceptQuestOpcode(')
assert 'CanRewardQuest' in function(quest_handler, 'void WorldSession::HandleQuestgiverChooseRewardOpcode(')
player_quest = (core / 'src/server/game/Entities/Player/PlayerQuest.cpp').read_text()
native_take = function(player_quest, 'bool Player::CanTakeQuest(')
for check in ('SatisfyQuestRace', 'SatisfyQuestClass', 'SatisfyQuestLevel',
              'SatisfyQuestPreviousQuest', 'SatisfyQuestConditions'):
    assert check in native_take
assert 'IsObjectMeetToConditions(this, conditions)' in function(player_quest, 'bool Player::SatisfyQuestConditions(')
item_handler = function((core / 'src/server/game/Handlers/SpellHandler.cpp').read_text(),
                        'void WorldSession::HandleUseItemOpcode(')
for check in ('pUser->CanUseItem(pItem)', 'pItem->GetGUID() != itemGUID', 'pUser->CastItemUseSpell(pItem, targets,'):
    assert check in item_handler
auras = (core / 'src/server/game/Spells/Auras/SpellAuraEffects.cpp').read_text()
assert 'aurApp->GetRemoveMode() != AURA_REMOVE_BY_CANCEL' in auras
assert 'caster->CastSpell(target, finalSpelId, true, nullptr, this);' in auras

production = {
    'table': function(source, 'namespace\n'),
    'gate': function(actions, 'bool TameBeastAction::CanAcquirePet('),
    'value': function(source, 'HunterTamingLesson const* HunterTamingLessonValue::Calculate()'),
    'trigger': function(source, 'bool HunterTamingLessonTrigger::IsActive()'),
    'useful': function(source, 'bool HunterTamingLessonAction::isUseful()'),
    'move': function(source, 'bool HunterTamingLessonAction::MoveToLessonLocation('),
    'giver': function(source, 'bool HunterTamingLessonAction::InteractWithLessonGiver('),
    'execute': function(source, 'bool HunterTamingLessonAction::Execute('),
    'wrapper': function(items, 'bool UseItemAction::UseItemOnUnit('),
    'precheck': precheck,
    'classes': '\n'.join(function(header, name) + ';' for name in (
        'struct HunterTamingLesson', 'class HunterTamingLessonValue',
        'class HunterTamingLessonTrigger', 'class HunterTamingLessonAction')),
}
rpg = (module / 'Ai/World/Rpg/Action/NewRpgBaseAction.cpp').read_text()
production['accept'] = function(rpg, 'bool NewRpgBaseAction::AcceptQuest(')
production['turnin'] = function(rpg, 'bool NewRpgBaseAction::TurnInQuest(')
far_move = function(rpg, 'bool NewRpgBaseAction::MoveFarTo(')
assert re.search(r'if \(sPlayerbotAIConfig.naturalProgression\)\s+return false;', far_move)
assert 'path.GetActualEndPosition()' in far_move
assert 'endDistToDest + 5.0f < disToDest' in far_move
for forbidden in ('bot->AddQuest(', 'bot->RewardQuest(', 'CompleteQuest(', 'AreaExploredOrEventHappens(',
                  'learnSpell(', 'CreateTamedPetFrom', 'RemovePet(', 'RemoveCharmAuras', 'TeleportTo('):
    assert forbidden not in source, forbidden

prelude = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <vector>
using uint8=uint8_t; using uint32=uint32_t; using int32=int32_t;
constexpr int CLASS_HUNTER=3, UNIT_STATE_LOST_CONTROL=1, CURRENT_CHANNELED_SPELL=1;
constexpr int QUEST_STATUS_NONE=0, QUEST_STATUS_INCOMPLETE=1, QUEST_STATUS_COMPLETE=2, QUEST_STATUS_REWARDED=3;
constexpr int CMSG_QUESTGIVER_CHOOSE_REWARD=1, CMSG_QUESTGIVER_ACCEPT_QUEST=2;
constexpr float INTERACTION_DISTANCE=5.0f;
uint32 now=100000;
uint32 getMSTime() { return now; }
uint32 GetMSTimeDiffToNow(uint32 before) { return now-before; }
struct ObjectGuid { uint32 value=0; explicit operator bool() const { return value!=0; } static ObjectGuid Empty; };
ObjectGuid ObjectGuid::Empty;
using GuidVector=std::vector<ObjectGuid>;
struct Event {};
struct Player; struct Unit; struct Creature; struct HunterTamingLesson;
struct Spell {};
struct WorldPacket {
    int opcode; std::vector<uint32> values;
    explicit WorldPacket(int opcode):opcode(opcode){}
    WorldPacket& operator<<(uint32 n) { values.push_back(n); return *this; }
    WorldPacket& operator<<(ObjectGuid guid) { values.push_back(guid.value); return *this; }
    void rpos(uint32) {}
};
struct Session {
    Player* player=nullptr; bool headless=true, accept=true, reward=true; int accepts=0,rewards=0;
    bool IsHeadless() const { return headless; }
    void HandleQuestgiverAcceptQuestOpcode(WorldPacket&);
    void HandleQuestgiverChooseRewardOpcode(WorldPacket&);
};
struct Map { bool dungeon=false; bool IsDungeon() const { return dungeon; } };
struct PetStable { bool CurrentPet=false; std::vector<bool> UnslottedPets; std::array<bool,4> StabledPets{}; };
struct ItemTemplate { struct Slot { int32 SpellId=0; } Spells[5]; };
struct Item { ItemTemplate proto; ItemTemplate const* GetTemplate() const { return &proto; } };
struct Quest {
    uint32 id=0,next=0,source=0; bool training=false;
    uint32 GetQuestId() const { return id; }
    uint32 GetRewChoiceItemsCount() const { return 0; }
};
struct Unit { virtual ~Unit()=default; virtual Creature* ToCreature() { return nullptr; } };
struct Creature:Unit {
    uint32 entry=0, guid=1; float x=10.0f;
    bool inWorld=true,removing=false,alive=true,sameMap=true,samePhase=true,visible=true,los=true,
         pet=false,summon=false,combat=false,loot=false,attackable=true,canInteract=true;
    ObjectGuid owner,charmer; std::set<uint32> starts,finishes;
    Creature* ToCreature() override { return this; }
    uint32 GetEntry() const { return entry; }
    ObjectGuid GetGUID() const { return {guid}; }
    bool IsInWorld() const { return inWorld; }
    bool IsDuringRemoveFromWorld() const { return removing; }
    bool IsAlive() const { return alive; }
    bool IsPet() const { return pet; } bool IsSummon() const { return summon; }
    ObjectGuid GetOwnerGUID() const { return owner; } ObjectGuid GetCharmerGUID() const { return charmer; }
    bool IsInCombat() const { return combat; } bool hasLootRecipient() const { return loot; }
    bool hasQuest(uint32 q) const { return starts.contains(q); }
    bool hasInvolvedQuest(uint32 q) const { return finishes.contains(q); }
    float GetPositionX() const { return x; } float GetPositionY() const { return 0; } float GetPositionZ() const { return 0; }
};
struct WorldPosition;
struct Player:Unit {
    uint32 cls=CLASS_HUNTER,temporaryPet=0,mapId=0,phase=1; bool random=true,hasSession=true,group=false,
      alive=true,inWorld=true,teleport=false,battleground=false,arena=false,combat=false,mounted=false,
      flight=false,flying=false,transport=false,vehicle=false,lostControl=false,casting=false,pet=false,
      canAdd=true,canReward=true;
    Map map; Session session; ObjectGuid petGuid,charmGuid; std::unique_ptr<PetStable> stable;
    std::set<uint32> known,available; std::map<uint32,int> quests; std::map<uint32,Item> inventory;
    Spell channel; int stops=0;
    Player() { session.player=this; }
    uint32 getClass() const { return cls; } Session* GetSession() { return hasSession?&session:nullptr; }
    bool GetGroup() const { return group; } bool IsAlive() const { return alive; }
    bool IsInWorld() const { return inWorld; } bool IsBeingTeleported() const { return teleport; }
    Map* GetMap() { return &map; } bool InBattleground() const { return battleground; } bool InArena() const { return arena; }
    bool IsInCombat() const { return combat; } bool IsMounted() const { return mounted; }
    bool IsInFlight() const { return flight; } bool IsFlying() const { return flying; }
    bool GetTransport() const { return transport; } bool GetVehicle() const { return vehicle; }
    bool HasUnitState(int) const { return lostControl; } bool IsNonMeleeSpellCast(bool) const { return casting; }
    bool HasSpell(uint32 n) const { return known.contains(n); } bool GetPet() const { return pet; }
    ObjectGuid GetPetGUID() const { return petGuid; } ObjectGuid GetCharmGUID() const { return charmGuid; }
    uint32 GetTemporaryUnsummonedPetNumber() const { return temporaryPet; }
    PetStable const* GetPetStable() const { return stable.get(); }
    int GetQuestStatus(uint32 q) const { return quests.contains(q)?quests.at(q):QUEST_STATUS_NONE; }
    bool GetQuestRewardStatus(uint32 q) const { return GetQuestStatus(q)==QUEST_STATUS_REWARDED; }
    Item* GetItemByEntry(uint32 i) { return inventory.contains(i)?&inventory.at(i):nullptr; }
    bool CanTakeQuest(Quest const* q,bool) const { return available.contains(q->id)&&GetQuestStatus(q->id)==QUEST_STATUS_NONE; }
    bool CanAddQuest(Quest const*,bool) const { return canAdd; }
    bool CanRewardQuest(Quest const*,bool) const { return canReward; }
    bool IsInMap(Creature* c) const { return c->sameMap; } bool InSamePhase(Creature* c) const { return c->samePhase; }
    bool CanSeeOrDetect(Creature* c) const { return c->visible; } bool IsWithinLOSInMap(Creature* c) const { return c->los; }
    bool IsValidAttackTarget(Creature* c) const { return c->attackable; }
    bool CanInteractWithQuestGiver(Creature* c) const { return c->canInteract; }
    float GetDistance(Creature* c) const { return std::abs(c->x); }
    float GetDistance(WorldPosition const&) const;
    bool IsWithinDistInMap(Creature* c,float range) const { return GetDistance(c)<=range; }
    void StopMoving() { ++stops; } Spell* GetCurrentSpell(int) { return &channel; }
    void PlayDistanceSound(uint32) {}
    uint32 GetMapId() const { return mapId; } uint32 GetPhaseMask() const { return phase; }
};
using QuestRelations=std::multimap<uint32,uint32>;
struct ObjectMgr {
    std::map<uint32,Quest> quests; QuestRelations starts,finishes;
    Quest const* GetQuestTemplate(uint32 q) const { return quests.contains(q)?&quests.at(q):nullptr; }
    QuestRelations const* GetCreatureQuestRelationMap() const { return &starts; }
    QuestRelations const* GetCreatureQuestInvolvedRelationMap() const { return &finishes; }
} objectMgr;
auto* sObjectMgr=&objectMgr;
void Session::HandleQuestgiverAcceptQuestOpcode(WorldPacket& p) {
    assert(p.opcode==CMSG_QUESTGIVER_ACCEPT_QUEST&&p.values.size()==3); ++accepts;
    if (!accept) return;
    uint32 q=p.values[1]; auto const* quest=objectMgr.GetQuestTemplate(q); assert(quest&&player->CanTakeQuest(quest,false));
    player->quests[q]=quest->training?QUEST_STATUS_COMPLETE:QUEST_STATUS_INCOMPLETE;
}
void Session::HandleQuestgiverChooseRewardOpcode(WorldPacket& p) {
    assert(p.opcode==CMSG_QUESTGIVER_CHOOSE_REWARD&&p.values.size()==3); ++rewards;
    if (!reward) return;
    uint32 q=p.values[1]; assert(player->GetQuestStatus(q)==QUEST_STATUS_COMPLETE); player->quests[q]=QUEST_STATUS_REWARDED;
}
struct Config { bool naturalProgression=true; float SightDistance=100.0f; std::set<uint32> IgnoredQuests; } sPlayerbotAIConfig;
struct RandomMgr { bool IsRandomBot(Player* p) const { return p->random; } } sRandomPlayerbotMgr;
struct SpellInfo { bool questTame=true; bool IsQuestTame() const { return questTame; } float GetMaxRange(bool,Player*) const { return 30.0f; } };
struct SpellMgr { bool exists=true; SpellInfo info; SpellInfo const* GetSpellInfo(uint32) const { return exists?&info:nullptr; } } spellMgr;
auto* sSpellMgr=&spellMgr;
struct Context { GuidVector nearby; HunterTamingLesson const* lesson=nullptr; };
template<class T> T GetValue(Context* c) { if constexpr(std::is_same_v<T,GuidVector>) return c->nearby; else return c->lesson; }
#define AI_VALUE(type,name) GetValue<type>(context)
struct GameObject {};
struct PlayerbotAI {
    Player* bot; Context context; bool master=false,castResult=true,moveResult=true;
    int casts=0,waits=0,moves=0; Unit* castTarget=nullptr; Unit* expectedTarget=nullptr;
    std::map<uint32,Unit*> units;
    Player* GetBot() const { return bot; } bool GetMaster() const { return master; }
    Unit* GetUnit(ObjectGuid g) const { return units.contains(g.value)?units.at(g.value):nullptr; }
    bool CanCastSpell(uint32,Unit* target,bool,Item*,Item*) { castTarget=target; return target==expectedTarget; }
    bool CanCastSpell(uint32,GameObject*,bool,Item*) { return false; }
    void WaitForSpellCast(Spell*) { ++waits; }
};
struct CreatureData { uint32 id=0,mapid=0,phaseMask=1; float posX=200,posY=0,posZ=0; };
std::vector<CreatureData> spawns; int spawnScans=0;
struct WorldPosition {
    uint32 map=0; float x=0,y=0,z=0;
    explicit WorldPosition(Player* p):map(p->GetMapId()){}
    WorldPosition(uint32 m,float a,float b,float c):map(m),x(a),y(b),z(c){}
    uint32 GetMapId() const { return map; } float GetPositionX() const { return x; }
    float GetPositionY() const { return y; } float GetPositionZ() const { return z; }
    float sqDistance(WorldPosition const& p) const { return (x-p.x)*(x-p.x)+(y-p.y)*(y-p.y)+(z-p.z)*(z-p.z); }
    std::vector<CreatureData const*> getCreaturesNear(float,uint32 entry) {
        ++spawnScans; std::vector<CreatureData const*> rows;
        for(auto const& s:spawns) if(s.mapid==map&&s.id==entry) rows.push_back(&s);
        return rows;
    }
};
float Player::GetDistance(WorldPosition const& p) const { return std::sqrt(p.sqDistance(WorldPosition(mapId,0,0,0))); }
enum PathType { PATHFIND_NORMAL=1,PATHFIND_NOPATH=2,PATHFIND_INCOMPLETE=4 };
bool pathResult=true; PathType pathType=PATHFIND_NORMAL;
struct PathGenerator {
    explicit PathGenerator(Player*){} bool CalculatePath(float,float,float,bool force) { assert(!force); return pathResult; }
    PathType GetPathType() const { return pathType; }
};
struct MovementAction {
    PlayerbotAI* botAI; Player* bot; Context* context;
    MovementAction(PlayerbotAI* ai,std::string):botAI(ai),bot(ai->bot),context(&ai->context){}
    virtual ~MovementAction()=default; virtual bool isUseful(){return true;} virtual bool Execute(Event){return false;}
    bool MoveTo(Creature*,float) { ++botAI->moves; return botAI->moveResult; }
    bool MoveTo(uint32,float,float,float,bool,bool,bool normal) { assert(normal); ++botAI->moves; return botAI->moveResult; }
};
struct NewRpgBaseAction:MovementAction {
    using MovementAction::MovementAction;
    bool MoveFarTo(WorldPosition) { if (!pathResult) return false; ++botAI->moves; return botAI->moveResult; }
    bool AcceptQuest(Quest const*,ObjectGuid);
    bool TurnInQuest(Quest const*,ObjectGuid);
    uint32 BestRewardIndex(Quest const*) { return 0; }
};
struct Trigger {
    PlayerbotAI* botAI; Context* context;
    Trigger(PlayerbotAI* ai,std::string,int):botAI(ai),context(&ai->context){}
    virtual ~Trigger()=default; virtual bool IsActive(){return false;}
};
template<class T> struct CalculatedValue {
    PlayerbotAI* botAI;
    CalculatedValue(PlayerbotAI* ai,std::string,int):botAI(ai){}
    virtual ~CalculatedValue()=default; virtual T Calculate()=0;
};
struct TameBeastAction { static bool CanAcquirePet(PlayerbotAI*); };
struct UseItemAction {
    PlayerbotAI* botAI;
    explicit UseItemAction(PlayerbotAI* ai):botAI(ai){}
    bool UseItemOnUnit(Item*,Unit*);
    bool UseItem(Item* item,ObjectGuid,Item* itemTarget,Unit* unitTarget) {
        (void)unitTarget;
        Player* bot=botAI->GetBot(); uint32 spellId=0;
        auto const* itemProto=item->GetTemplate(); uint8 const spellSlotLimit=5;
        GameObject* goTarget=nullptr;
        @@PRECHECK@@
        ++botAI->casts;
        return botAI->castResult;
    }
};
@@CLASSES@@
@@ACCEPT@@
@@TURNIN@@
@@GATE@@
@@TABLE@@
@@WRAPPER@@
@@VALUE@@
@@TRIGGER@@
@@USEFUL@@
@@MOVE@@
@@GIVER@@
@@EXECUTE@@
'''

tests = r'''
struct Scenario {
    Player bot; PlayerbotAI ai{&bot}; HunterTamingLessonValue value{&ai}; HunterTamingLessonAction action{&ai};
    Creature beast,giver;
    Scenario(HunterTamingLesson const& lesson) {
        sPlayerbotAIConfig={}; objectMgr={}; spellMgr={}; pathResult=true; pathType=PATHFIND_NORMAL;
        spawns.clear(); spawnScans=0;
        for(auto const& l:kTamingLessons) objectMgr.quests.emplace(l.Quest,Quest{l.Quest,0,l.Item,l.Item==0});
        bot.quests[lesson.Quest]=QUEST_STATUS_INCOMPLETE;
        if(lesson.Item) bot.inventory[lesson.Item].proto.Spells[0].SpellId=int32(lesson.Spell);
        beast.entry=lesson.Creature; ai.units[1]=&beast; ai.expectedTarget=&beast; ai.context.nearby={{1}};
        giver.guid=2; giver.x=2; giver.starts.insert(lesson.Quest); giver.finishes.insert(lesson.Quest); ai.units[2]=&giver;
        ai.context.lesson=value.Calculate();
    }
};
int main() {
    for(auto const& lesson:kTamingLessons) {
        Scenario s(lesson);
        assert(s.value.Calculate()==&lesson);
        if(!lesson.Item) continue;
        assert(s.action.Execute({})&&s.ai.casts==1&&s.ai.waits==1&&s.ai.castTarget==&s.beast);
        assert(s.bot.GetQuestStatus(lesson.Quest)==QUEST_STATUS_INCOMPLETE); // only the native completed channel supplies credit
        s.bot.quests[lesson.Quest]=QUEST_STATUS_COMPLETE; s.ai.context.nearby={{2}};
        assert(s.action.Execute({})&&s.bot.GetQuestRewardStatus(lesson.Quest)&&s.bot.session.rewards==1);
        s.bot.quests.erase(lesson.Quest); s.bot.available.insert(lesson.Quest);
        assert(s.action.Execute({})&&s.bot.GetQuestStatus(lesson.Quest)==QUEST_STATUS_INCOMPLETE&&s.bot.session.accepts==1);
    }
    auto const& lesson=kTamingLessons[0];
    { Scenario s(lesson); s.bot.inventory.clear(); assert(!s.action.Execute({})&&s.ai.casts==0); }
    { Scenario s(lesson); s.bot.session.headless=false; assert(!s.action.Execute({})&&s.ai.casts==0); }
    { Scenario s(lesson); s.ai.master=true; assert(!s.action.Execute({})); }
    { Scenario s(lesson); s.bot.stable=std::make_unique<PetStable>(); s.bot.stable->StabledPets[0]=true;
      assert(!s.action.Execute({})&&s.ai.casts==0); }
    { Scenario s(lesson); s.bot.charmGuid={2}; assert(!s.action.Execute({})&&s.ai.casts==0); }
    { Scenario s(lesson); s.bot.known={1515}; assert(s.value.Calculate()); s.bot.known={1515,6991,982}; assert(!s.value.Calculate()); }
    { Scenario s(lesson); sPlayerbotAIConfig.IgnoredQuests.insert(lesson.Quest); assert(!s.action.Execute({})); }
    { Scenario s(lesson); s.beast.entry=9999; assert(!s.action.Execute({})&&s.ai.casts==0); }
    { Scenario s(lesson); s.beast.visible=false; assert(!s.action.Execute({})&&s.ai.casts==0); }
    { Scenario s(lesson); s.beast.owner={3}; assert(!s.action.Execute({})&&s.ai.casts==0); }
    { Scenario s(lesson); s.beast.samePhase=false; assert(!s.action.Execute({})&&s.ai.casts==0); }
    { Scenario s(lesson); s.beast.x=50; assert(s.action.Execute({})&&s.ai.moves==1&&s.ai.casts==0); }
    { Scenario s(lesson); s.beast.x=50; pathType=PATHFIND_INCOMPLETE; assert(!s.action.Execute({})&&s.ai.moves==0); }
    { Scenario s(lesson); s.ai.castResult=false; assert(!s.action.Execute({})&&s.ai.waits==0); }
    { Scenario s(lesson); s.bot.quests[lesson.Quest]=QUEST_STATUS_COMPLETE; s.ai.context.nearby={{2}};
      s.giver.canInteract=false; assert(!s.action.Execute({})&&s.bot.session.rewards==0); }
    { Scenario s(lesson); s.bot.quests[lesson.Quest]=QUEST_STATUS_COMPLETE; s.ai.context.nearby={{2}};
      s.bot.canReward=false; assert(!s.action.Execute({})&&s.bot.session.rewards==0); }
    { Scenario s(lesson); s.bot.quests.erase(lesson.Quest); s.ai.context.nearby={{2}};
      assert(!s.action.Execute({})&&s.bot.session.accepts==0); }
    { Scenario s(lesson); s.bot.quests.erase(lesson.Quest); s.bot.available.insert(lesson.Quest); s.bot.canAdd=false;
      assert(!s.action.Execute({})&&s.bot.session.accepts==0); }
    { Scenario s(lesson); s.bot.quests[lesson.Quest]=QUEST_STATUS_COMPLETE; s.ai.context.nearby={{2}}; s.bot.session.reward=false;
      assert(!s.action.Execute({})&&s.bot.GetQuestStatus(lesson.Quest)==QUEST_STATUS_COMPLETE); }
    { Scenario s(lesson); s.ai.context.nearby.clear(); spawns={{lesson.Creature,1,1,200,0,0},{lesson.Creature,0,2,200,0,0}};
      assert(!s.action.Execute({})&&s.ai.moves==0); }
    { Scenario s(lesson); s.ai.context.nearby.clear(); spawns={{lesson.Creature,0,1,200,0,0}};
      assert(s.action.Execute({})&&s.ai.moves==1); assert(s.action.Execute({})&&spawnScans==1); }
    { Scenario s(lesson); s.ai.context.nearby.clear(); spawns={{lesson.Creature,0,1,200,0,0}}; pathResult=false;
      assert(!s.action.Execute({})&&s.ai.moves==0); }
    for(auto const& lesson:kTamingLessons) if(!lesson.Item) {
        Scenario s(lesson); s.bot.known={1515}; s.bot.quests.erase(lesson.Quest); s.bot.available.insert(lesson.Quest);
        s.ai.context.nearby={{2}}; assert(s.action.Execute({})&&s.bot.GetQuestStatus(lesson.Quest)==QUEST_STATUS_COMPLETE);
        assert(s.action.Execute({})&&s.bot.GetQuestRewardStatus(lesson.Quest));
    }
    std::cout<<"Hunter taming lessons: all native chains, source rods, own access, protected pets, checked routes and ordinary quest packets passed\n";
}
'''

mutations = (
    ('actual item target validated', 'precheck', 'unitTarget ? unitTarget : bot', 'bot'),
    ('owned source rod required', 'execute', '!rod ||', ''),
    ('current ownership revalidated', 'table', 'if (!CanTakeTamingLesson(botAI))', 'if (!CanTakeTamingLesson(botAI) && false)'),
    ('correct lesson creature', 'execute', 'creature->GetEntry() != lesson->Creature ||', ''),
    ('hidden target rejected', 'execute', '!bot->CanSeeOrDetect(creature) ||', ''),
    ('claimed target rejected', 'execute', 'creature->GetOwnerGUID() ||', ''),
    ('phase target rejected', 'execute', '!bot->InSamePhase(creature) ||', ''),
    ('complete live-target path', 'execute', 'path.GetPathType() != PATHFIND_NORMAL', 'false'),
    ('native spawn route required', 'move', 'return MoveFarTo(destination);', '++botAI->moves; return true;'),
    ('channel wait retained', 'execute', 'botAI->WaitForSpellCast(bot->GetCurrentSpell(CURRENT_CHANNELED_SPELL));', ''),
    ('native reward result', 'giver', 'return bot->GetQuestRewardStatus(lesson.Quest);', 'return true;'),
)


def build(directory, parts, name):
    text = prelude
    for key, value in parts.items():
        text = text.replace('@@' + key.upper() + '@@', value)
    path = directory / (name + '.cpp')
    path.write_text(text + tests)
    binary = directory / name
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-missing-field-initializers',
                    *SANITIZER_FLAGS, str(path), '-o', str(binary)], check=True)
    return run_fixture([str(binary)])


with tempfile.TemporaryDirectory(prefix='portable-hunter-lessons-') as temporary:
    directory = Path(temporary)
    result = build(directory, production, 'lessons')
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit('Hunter lesson fixture failed')

    reject_part_mutants(production, mutations, lambda parts, tag: build(directory, parts, tag),
                        'Hunter lesson')
