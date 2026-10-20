"""Exercise Zum'rah's ordinary spatial activation and native SmartTrigger dispatch."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    TIMEOUT,
    cxx,
    function,
    prepared_core,
    reject_mutants,
    source_argument,
)
from TestDefiasCannon import sql_rows


def native_sources(core, source):
    trigger = sql_rows(core, 'areatrigger', {962})[0]
    assert [float(trigger[key]) for key in ('map', 'x', 'y', 'z', 'radius')] == [209, 1909.27, 1015.11, 11.5155, 10]
    assert all(float(trigger[key]) == 0 for key in ('length', 'width', 'height', 'orientation'))
    assert sql_rows(core, 'areatrigger_scripts', {962})[0]['ScriptName'] == 'SmartTrigger'
    for table in ('areatrigger_teleport', 'areatrigger_involvedrelation'):
        assert not re.search(r'^\(962,', (core / f'data/sql/base/db_world/{table}.sql').read_text(), re.MULTILINE)
    creature = sql_rows(core, 'creature', {81524})[0]
    assert {key: int(creature[key]) for key in ('id1', 'map')} == {'id1': 7271, 'map': 209}
    template = sql_rows(core, 'creature_template', {7271})[0]
    assert int(template['faction']) == 35 and template['AIName'] == 'SmartAI'
    # These separate access objectives remain outside the activation driver.
    objects = {int(row['entry']): row for row in sql_rows(core, 'gameobject_template', {141073, 141832})}
    assert int(objects[141073]['type']) == 0 and int(objects[141073]['Data1']) == 420
    assert int(objects[141832]['type']) == 10 and int(objects[141832]['Data0']) == 99
    rows = sql_rows(core, 'smart_scripts', {962, 7271})
    wake = [row for row in rows if row['entryorguid'] == '962' and row['source_type'] == '2']
    assert len(wake) == 1
    assert {key: int(wake[0][key]) for key in ('event_type', 'action_type', 'action_param1',
                                             'target_type', 'target_param1', 'target_param2')} == {
        'event_type': 46, 'action_type': 2, 'action_param1': 37,
        'target_type': 10, 'target_param1': 81524, 'target_param2': 7271}
    reset = [row for row in rows if row['entryorguid'] == '7271' and row['source_type'] == '0'
             and row['event_type'] == '25' and row['action_type'] == '2']
    assert len(reset) == 1 and int(reset[0]['action_param1']) == 0 and int(reset[0]['target_type']) == 1
    conditions = (core / 'data/sql/base/db_world/conditions.sql').read_text()
    assert not re.search(r',(?:962|81524),', conditions)

    player = (core / 'src/server/game/Entities/Player/Player.cpp').read_text()
    native = function(player, 'bool Player::IsInAreaTriggerRadius(') + '\n'
    position = (core / 'src/server/game/Entities/Object/Position.cpp').read_text()
    native += function(position, 'bool Position::IsWithinBox(') + '\n'
    world_object = (core / 'src/server/game/Entities/Object/Object.cpp').read_text()
    native += function(world_object, 'float WorldObject::GetDistance(float x, float y, float z)') + '\n'
    nearest = function(world_object, 'Creature* WorldObject::FindNearestCreature(')
    assert 'NearestCreatureEntryWithLiveStateInObjectRangeCheck' in nearest and 'Cell::VisitObjects(this, searcher, range)' in nearest
    notifiers = (core / 'src/server/game/Grids/Notifiers/GridNotifiers.h').read_text()
    nearest_check = function(notifiers, 'class NearestCreatureEntryWithLiveStateInObjectRangeCheck')
    assert all(test in nearest_check for test in ('u->GetEntry() == i_entry', 'u->IsAlive() == i_alive',
                                                'i_obj.IsWithinDist(u, i_range)', 'i_obj.InSamePhase(u)'))
    assert 'IsInWorld() && obj->IsInWorld() && (FindMap() == obj->FindMap())' in function(world_object, 'bool WorldObject::IsInMap(')
    handler = function((core / 'src/server/game/Handlers/MiscHandler.cpp').read_text(),
                       'void WorldSession::HandleAreaTriggerOpcode(')
    assert handler.index('player->IsInFlight()') < handler.index('sObjectMgr->GetAreaTrigger(triggerId)')
    assert handler.index('player->IsInAreaTriggerRadius(') < handler.index('sScriptMgr->OnAreaTrigger(player, atEntry)')
    assert '(!player->IsGameMaster() || player->isDebugAreaTriggers)' in handler
    smart_ai = (core / 'src/server/game/AI/SmartScripts/SmartAI.cpp').read_text()
    on_trigger = function(smart_ai.split('class SmartTrigger', 1)[1], 'bool OnTrigger(').replace(' override', '')
    native += 'struct NativeSmartTrigger {' + on_trigger + '};\n'
    smart = (core / 'src/server/game/AI/SmartScripts/SmartScript.cpp').read_text()
    dispatch = function(smart, 'void SmartScript::ProcessEventsFor(')
    assert 'GetConditionsForSmartEvent' in dispatch
    assert dispatch.index('sConditionMgr->IsObjectMeetToConditions(info, conds)') < dispatch.index('ProcessEvent(')
    target = smart.split('case SMART_TARGET_CREATURE_GUID:', 1)[1].split('case SMART_TARGET_GAMEOBJECT_GUID:', 1)[0]
    assert 'FindCreatureNear(scriptTrigger ? scriptTrigger : GetBaseObject(), e.target.unitGUID.dbGuid)' in target
    assert '(!e.target.unitGUID.entry || target->GetEntry() == e.target.unitGUID.entry)' in target
    smart_header = (core / 'src/server/game/AI/SmartScripts/SmartScript.h').read_text()
    finder = function(smart_header, 'Creature* FindCreatureNear(')
    assert 'searchObject->GetMap()->GetCreatureBySpawnIdStore().equal_range(guid)' in finder
    faction = 'case SMART_ACTION_SET_FACTION:' + smart.split('case SMART_ACTION_SET_FACTION:', 1)[1].split('case SMART_ACTION_MORPH_TO_ENTRY_OR_MODEL:', 1)[0]
    native += 'void NativeFactionAction(SmartEvent const& e,std::vector<WorldObject*> targets){switch(SMART_ACTION_SET_FACTION){' + faction + '}}\n'
    for name, value in (('SMART_EVENT_AREATRIGGER_ONTRIGGER', 46), ('SMART_EVENT_RESET', 25),
                        ('SMART_ACTION_SET_FACTION', 2), ('SMART_TARGET_CREATURE_GUID', 10)):
        assert re.search(rf'\b{name}\s*=\s*{value}\b', (core / 'src/server/game/AI/SmartScripts/SmartScriptMgr.h').read_text())
    hook = (source / 'Ai/Dungeon/DungeonClear/Overrides/ObjectiveHookRegistry.cpp').read_text()
    wake_hook = function(hook, 'ObjectiveArriveResult WakeZumrah(')
    for shortcut in ('SetFaction(', 'SetData(', 'SetBossState(', 'SummonCreature(', 'OnAreaTrigger(',
                     'ProcessEventsFor(', 'TeleportTo(', 'AddItem(', 'CastSpell('):
        assert shortcut not in wake_hook, shortcut
    print('Native Zumrah contracts: spatial SmartTrigger, same-instance spawn targeting, faction reset and ordinary entry dispatch verified')
    return native, finder


STUBS = r'''#pragma once
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <functional>
#include <map>
#include <string>
#include <unordered_map>
#include <vector>
using uint8=uint8_t;using uint32=uint32_t;using int32=int32_t;
namespace ObjectGuid{using LowType=uint32;}
constexpr uint32 CMSG_AREATRIGGER=1,FORCED_MOVEMENT_NONE=0;
constexpr uint32 SMART_EVENT_AREATRIGGER_ONTRIGGER=46,SMART_ACTION_SET_FACTION=2;
enum class ObjectiveArriveResult{Done,Running,Blocked};
enum TeamId{TEAM_ALLIANCE,TEAM_HORDE,TEAM_NEUTRAL};
enum class DcDifficultyGate:uint8{Any,NormalOnly,HeroicOnly};
struct DcDiffKey{};
struct AreaTrigger{uint32 entry=962,map=209;float x=1909.27f,y=1015.11f,z=11.5155f,radius=10,length=0,width=0,height=0,orientation=0;};
struct Position
{
    float x=1909.27f,y=1015.11f,z=11.5155f,orientation=0;
    Position()=default;Position(float px,float py,float pz,float o):x(px),y(py),z(pz),orientation(o){}
    float GetPositionX()const{return x;}float GetPositionY()const{return y;}float GetPositionZ()const{return z;}
    float GetOrientation()const{return orientation;}bool IsWithinBox(Position const&,float,float,float)const;
};
class Creature;class Player;
struct Map
{
    using CreatureBySpawnIdContainer=std::multimap<uint32,Creature*>;
    CreatureBySpawnIdContainer creatures;
    CreatureBySpawnIdContainer const& GetCreatureBySpawnIdStore()const{return creatures;}
};
struct WorldObject:Position
{
    virtual ~WorldObject()=default;
    Map* map=nullptr;uint32 mapId=209,phase=1;bool world=true;
    float GetObjectSize()const{return 0.3889999986f;}
    float GetExactDist(float px,float py,float pz)const{return std::sqrt((px-x)*(px-x)+(py-y)*(py-y)+(pz-z)*(pz-z));}
    float GetDistance(float,float,float)const;
    bool IsInWorld()const{return world;}uint32 GetMapId()const{return mapId;}Map* GetMap()const{return map;}
    bool IsInMap(WorldObject const* other)const{return world&&other->world&&map==other->map;}
    bool InSamePhase(WorldObject const* other)const{return phase&other->phase;}
    Creature* ToCreature();
};
struct Creature:WorldObject
{
    uint32 entry=7271,faction=35,spawnId=81524,writes=0;bool alive=true;
    uint32 GetEntry()const{return entry;}uint32 GetFaction()const{return faction;}
    uint32 GetSpawnId()const{return spawnId;}bool IsAlive()const{return alive;}
    void SetFaction(uint32 value){faction=value;++writes;}
    bool IsHostileTo(Player const*)const{return faction==37;}
};
Creature* WorldObject::ToCreature(){return dynamic_cast<Creature*>(this);}
inline bool IsCreature(WorldObject* target){return target->ToCreature();}
struct CreatureTemplate{uint32 faction=35;};
struct ObjectMgr
{
    AreaTrigger trigger;CreatureTemplate info;bool present=true,binding=true,accepted=true;
    uint32 initializations=0,events=0;
    AreaTrigger const* GetAreaTrigger(uint32 id){assert(id==962);return present?&trigger:nullptr;}
    CreatureTemplate const* GetCreatureTemplate(uint32 entry){assert(entry==7271);return &info;}
}objectMgr;
ObjectMgr* sObjectMgr=&objectMgr;
struct SmartEvent{struct{struct{uint32 factionID;}faction;}action;};
void NativeFactionAction(SmartEvent const&,std::vector<WorldObject*>);
struct SmartScript
{
    AreaTrigger const* area=nullptr;
    void OnInitialize(WorldObject* object,AreaTrigger const* trigger){assert(!object);area=trigger;++objectMgr.initializations;}
    void ProcessEventsFor(uint32 event,Player* player,uint32 entry);
    NATIVE_FIND_CREATURE
};
#define LOG_DEBUG(...) ((void)0)
#define LOG_WARN(...) ((void)0)
struct AiObjectContext{bool enabled=true,paused=false;};
namespace DcRun{inline AiObjectContext& Of(AiObjectContext* context){return *context;}}
struct PlayerbotAI
{
    bool movable=true;bool CanMove()const{return movable;}
};
struct MotionMaster
{
    Player* bot;uint32 calls=0;bool generated=false;
    void MovePoint(uint32,float,float,float,uint32,float,float,bool,bool);
};
struct WorldPacket
{
    uint32 opcode,id=0;explicit WorldPacket(uint32 op):opcode(op){}
    WorldPacket& operator<<(uint32 value){id=value;return *this;}
};
struct WorldSession{Player* bot;uint32 packets=0;void HandleAreaTriggerOpcode(WorldPacket&);};
class Player:public WorldObject
{
public:
    bool alive=true,combat=false,flight=false,transfer=false,casting=false,moving=false,reachable=true;
    bool ai=true,hasSession=true,gm=false,isDebugAreaTriggers=false,selfBot=false;uint32 loot=0,stops=0;
    mutable uint32 nearestCalls=0;
    Player* m_mover=this;PlayerbotAI botAI;WorldSession session{this};MotionMaster motion{this};
    bool IsAlive()const{return alive;}bool IsInCombat()const{return combat;}bool IsInFlight()const{return flight;}
    bool IsBeingTeleported()const{return transfer;}bool IsNonMeleeSpellCast(bool)const{return casting;}
    uint32 GetLootGUID()const{return loot;}bool isMoving()const{return moving;}bool IsGameMaster()const{return gm;}
    bool IsInAreaTriggerRadius(AreaTrigger const*,float delta=0)const;
    bool IsValidAttackTarget(Creature* creature)const{return creature&&creature->alive&&creature->faction==37;}
    MotionMaster* GetMotionMaster(){return &motion;}WorldSession* GetSession(){return hasSession?&session:nullptr;}
    Creature* FindNearestCreature(uint32 entry,float range,bool alive=true)const
    {
        ++nearestCalls;
        Creature* closest=nullptr;
        for(auto const& [guid,creature]:map->creatures)
            if(creature->IsInWorld()&&creature->GetEntry()==entry&&creature->IsAlive()==alive&&
               creature->map==map&&creature->InSamePhase(this))
            {
                float distance=GetDistance(creature->x,creature->y,creature->z)-creature->GetObjectSize();
                if(distance<=range){range=distance;closest=creature;}
            }
        return closest;
    }
};
#define GET_PLAYERBOT_AI(bot) ((bot)->ai?&(bot)->botAI:nullptr)
inline bool IsSelfBot(Player* bot){return bot->selfBot;}
void MotionMaster::MovePoint(uint32,float x,float y,float z,uint32,float,float,bool generate,bool)
{
    assert(bot->reachable);assert(x==objectMgr.trigger.x&&y==objectMgr.trigger.y&&z==objectMgr.trigger.z);
    ++calls;generated=generate;bot->moving=true;
}
namespace DcEarnedPlay{inline bool active=true;inline bool Active(){return active;}inline bool ReachableLeg(Player* bot,float,float,float){return bot->reachable;}}
namespace DcMovement
{
    enum class Stop{Hold};inline bool DcMovementAllowed(PlayerbotAI*){return true;}
    inline void StopBot(Player* bot,Stop){++bot->stops;bot->moving=false;}
}
struct DungeonBossInfo{};
struct ObjectiveHookRegistry
{
    using Hook=std::function<ObjectiveArriveResult(Player*,AiObjectContext*,DungeonBossInfo const&)>;
    using HookTable=std::unordered_map<uint32,Hook>;
    static ObjectiveArriveResult Run(uint32,Player*,AiObjectContext*,DungeonBossInfo const&);
};
inline uint32 getMSTime(){return 0;}
'''


def production_sources(source):
    hook = (source / 'Ai/Dungeon/DungeonClear/Overrides/ObjectiveHookRegistry.cpp').read_text()
    constants = '\n'.join(re.findall(r'^    constexpr (?:uint32|float) ZF_ZUMRAH[^;]+;', hook, re.MULTILINE))
    wake = 'namespace Wake {\n' + constants + '\n' + function(hook, 'ObjectiveArriveResult WakeZumrah(') + '\n}\n'
    wake += '''
uint32 shortcutCalls=0;
ObjectiveHookRegistry::HookTable const& Hooks(){static ObjectiveHookRegistry::HookTable hooks{
    {5,&Wake::WakeZumrah},{2,[](Player*,AiObjectContext*,DungeonBossInfo const&){++shortcutCalls;return ObjectiveArriveResult::Done;}}};return hooks;}
'''
    wake += function(hook, 'ObjectiveArriveResult ObjectiveHookRegistry::Run(')
    registry = source / 'Ai/Dungeon/DungeonClear/Data/DungeonEventRegistry.h'
    builder = registry.with_suffix('.cpp').read_text()
    authored = ['#include "DungeonEventRegistry.h"', '#include <utility>']
    for signature in ('EventBuilder::EventBuilder(', 'EventStep& EventBuilder::Add(', 'EventBuilder& EventBuilder::Conditional(',
                      'EventBuilder& EventBuilder::Repeatable(', 'EventBuilder& EventBuilder::PanelBeforeBoss(',
                      'EventBuilder& EventBuilder::OwnsThePull(', 'EventBuilder& EventBuilder::StepsOwnMovement(',
                      'EventBuilder& EventBuilder::Custom(', 'EventBuilder& EventBuilder::Timeout('):
        authored.append(function(builder, signature))
    events = (source / 'Ai/Dungeon/DungeonClear/Data/Events/ZulFarrakEvents.cpp').read_text()
    constants = '\n'.join(re.findall(r'^    constexpr (?:uint32|float) ZF_(?:ZUMRAH|HOOK_WAKE_ZUMRAH)[^;]+;', events, re.MULTILINE))
    start = events.index('out.push_back(EventBuilder(209, 3,')
    end = events.index('.Build());', start) + len('.Build());')
    predicate = function(events, 'bool ZfZumrahAsleep(Player* bot, AiObjectContext* /*context*/)')
    authored.append('namespace Authored {\n' + constants + '\n' + predicate + '\n'
                    + 'void Register(std::vector<DungeonEvent>& out){' + events[start:end] + '}\n}\n')
    return registry, wake, '\n'.join(authored)


HARNESS = r'''
#include "NativeStubs.h"
#include "NativeZumrah.cpp"
#include "WakeZumrah.cpp"
#include "AuthoredZumrah.cpp"
#include <iostream>
void SmartScript::ProcessEventsFor(uint32 event,Player* player,uint32 entry)
{
    assert(event==SMART_EVENT_AREATRIGGER_ONTRIGGER&&entry==962&&area&&area->entry==962);
    ++objectMgr.events;
    if(!objectMgr.accepted)return; // Native SmartScript conditions are authoritative.
    // The native trigger's data targets spawn 81524 in the invoker's map.
    if(Creature* target=FindCreatureNear(player,81524);target&&target->GetEntry()==7271)
    {
        SmartEvent action;action.action.faction.factionID=37;NativeFactionAction(action,{target});
    }
}
void WorldSession::HandleAreaTriggerOpcode(WorldPacket& packet)
{
    ++packets;assert(packet.opcode==CMSG_AREATRIGGER&&packet.id==962);
    AreaTrigger const* trigger=sObjectMgr->GetAreaTrigger(packet.id);
    // Native handler contract asserted above: flight and the actual trigger
    // volume precede script dispatch; there is no teleport row for this trigger.
    if(bot->IsInFlight()||!bot->IsInAreaTriggerRadius(trigger)||
       (bot->IsGameMaster()&&!bot->isDebugAreaTriggers)||!objectMgr.binding)return;
    NativeSmartTrigger{}.OnTrigger(bot,trigger);
}
struct Scenario
{
    Map instance;Creature boss;Player bot;AiObjectContext context;DungeonBossInfo info;
    Scenario(){objectMgr={};DcEarnedPlay::active=true;shortcutCalls=0;bot.map=&instance;boss.map=&instance;
        instance.creatures.emplace(81524,&boss);}
    ObjectiveArriveResult Run(){return ObjectiveHookRegistry::Run(5,&bot,&context,info);}
    bool Due(){return Authored::ZfZumrahAsleep(&bot,&context);}
    void Quiet(){assert(Run()==ObjectiveArriveResult::Running);assert(!bot.motion.calls&&!bot.session.packets&&!boss.writes);}
    void Outside(){bot.x+=20;}
    void Reset(){SmartEvent action;action.action.faction.factionID=0;NativeFactionAction(action,{&boss});}
};
void AdmissionAndInterruptions()
{
    Scenario null;assert(Wake::WakeZumrah(nullptr,&null.context,null.info)==ObjectiveArriveResult::Blocked);
    for(uint32 gate=0;gate<6;++gate){Scenario s;
        switch(gate){case 0:s.bot.mapId=1;break;case 1:s.bot.world=false;break;case 2:s.bot.ai=false;break;
            case 3:s.bot.hasSession=false;break;case 4:s.bot.selfBot=true;break;case 5:objectMgr.present=false;break;}
        assert(s.Run()==ObjectiveArriveResult::Blocked);assert(!s.bot.motion.calls&&!s.bot.session.packets&&!s.boss.writes);}
    {Scenario s;objectMgr.trigger.map=1;assert(s.Run()==ObjectiveArriveResult::Blocked);assert(!s.bot.session.packets);}
    for(uint32 gate=0;gate<9;++gate){Scenario s;s.Outside();
        switch(gate){case 0:s.bot.alive=false;break;case 1:s.bot.combat=true;break;case 2:s.bot.flight=true;break;
            case 3:s.bot.transfer=true;break;case 4:s.bot.m_mover=nullptr;break;case 5:s.bot.casting=true;break;
            case 6:s.bot.loot=99;break;case 7:s.context.enabled=false;break;case 8:s.context.paused=true;break;}
        s.Quiet();}
    {Scenario s;assert(Wake::WakeZumrah(&s.bot,nullptr,s.info)==ObjectiveArriveResult::Running);assert(!s.bot.session.packets);}
    for(uint32 gate=0;gate<3;++gate){Scenario s;s.Outside();
        if(gate==0)s.bot.reachable=false;
        if(gate==1)s.bot.botAI.movable=false;
        if(gate==2)s.bot.moving=true;
        s.Quiet();}
    // A changed neutral faction must not count as native activation.
    {Scenario s;s.boss.faction=36;assert(s.Run()==ObjectiveArriveResult::Blocked);assert(!s.bot.session.packets);}
    {Scenario s;assert(ObjectiveHookRegistry::Run(2,&s.bot,&s.context,s.info)==ObjectiveArriveResult::Blocked&&shortcutCalls==0);}
}
void PresenceAndGeometry()
{
    for(uint32 gate=0;gate<7;++gate){Scenario s;Map other;
        switch(gate){case 0:s.instance.creatures.clear();break;case 1:s.boss.alive=false;break;
            case 2:s.boss.map=&other;s.instance.creatures.clear();other.creatures.emplace(81524,&s.boss);break;
            case 3:s.boss.phase=2;break;case 4:s.boss.world=false;s.instance.creatures.clear();break;
            case 5:s.boss.spawnId=99;s.instance.creatures.clear();s.instance.creatures.emplace(99,&s.boss);break;
            case 6:s.bot.x+=100;break;}
        assert(!s.Due());s.Quiet();}
    {Scenario s;assert(!Authored::ZfZumrahAsleep(nullptr,&s.context));s.bot.mapId=1;assert(!s.Due()&&!s.bot.nearestCalls);}
    {Scenario s;s.bot.world=false;assert(!s.Due()&&!s.bot.nearestCalls);}
    for(float distance:{9.9f,10.0f,10.2f,10.5f}){Scenario s;s.bot.x+=distance;
        bool inside=s.bot.IsInAreaTriggerRadius(&objectMgr.trigger);assert(inside==(distance<10.4f));
        assert(s.Run()==ObjectiveArriveResult::Running);assert(s.bot.session.packets==(inside?1u:0u));
        assert(s.bot.motion.calls==(inside?0u:1u));}
    {Scenario s;s.bot.z+=20;assert(s.Run()==ObjectiveArriveResult::Running);assert(!s.bot.session.packets&&s.bot.motion.calls==1);}
    {Scenario s;s.Outside();assert(s.Due());assert(s.Run()==ObjectiveArriveResult::Running);
        assert(s.bot.motion.calls==1&&s.bot.motion.generated&&!s.bot.session.packets&&s.boss.faction==35);
        assert(s.Run()==ObjectiveArriveResult::Running);assert(s.bot.motion.calls==1&&!s.bot.session.packets);
        // Movement requests do not prove arrival; the simulated walk changes position.
        s.bot.x=objectMgr.trigger.x;assert(s.Run()==ObjectiveArriveResult::Running);
        assert(s.bot.stops==1&&!s.bot.moving&&s.bot.session.packets==1&&s.boss.faction==37);}
}
void NativeLifecycle()
{
    {Scenario s;assert(s.Due());assert(s.Run()==ObjectiveArriveResult::Running);
        assert(objectMgr.initializations==1&&objectMgr.events==1&&s.boss.faction==37&&s.boss.writes==1);
        assert(!s.Due()&&s.Run()==ObjectiveArriveResult::Done);assert(s.bot.session.packets==1&&s.boss.writes==1);
        s.Reset();assert(s.boss.faction==35&&s.Due());assert(s.Run()==ObjectiveArriveResult::Running);
        assert(s.boss.faction==37&&s.bot.session.packets==2);assert(s.Run()==ObjectiveArriveResult::Done);}
    // A human already entered: the driver leaves the native encounter untouched.
    {Scenario s;NativeSmartTrigger{}.OnTrigger(&s.bot,&objectMgr.trigger);assert(!s.Due());
        assert(s.Run()==ObjectiveArriveResult::Done&&!s.bot.session.packets&&s.boss.writes==1);}
    for(uint32 refusal=0;refusal<3;++refusal){Scenario s;
        if(refusal==0)objectMgr.binding=false;
        if(refusal==1)objectMgr.accepted=false;
        if(refusal==2)s.bot.gm=true;
        assert(s.Run()==ObjectiveArriveResult::Running);assert(s.boss.faction==35&&s.boss.writes==0&&s.Due());
        assert(s.Run()==ObjectiveArriveResult::Running);assert(s.bot.session.packets==2&&s.boss.writes==0);
        objectMgr.binding=true;objectMgr.accepted=true;s.bot.gm=false;
        assert(s.Run()==ObjectiveArriveResult::Running&&s.boss.faction==37);assert(s.Run()==ObjectiveArriveResult::Done);}
    // Same map id, separate instance: SmartScript finds only the invoker's spawn.
    {Scenario s;Map other;Creature elsewhere;elsewhere.map=&other;other.creatures.emplace(81524,&elsewhere);
        assert(s.Run()==ObjectiveArriveResult::Running);assert(s.boss.faction==37&&elsewhere.faction==35&&!elsewhere.writes);}
    {Scenario s;s.bot.alive=false;assert(!NativeSmartTrigger{}.OnTrigger(&s.bot,&objectMgr.trigger));assert(!s.boss.writes);}
    {Scenario s;s.context.enabled=false;s.Quiet();s.context.enabled=true;s.context.paused=true;s.Quiet();
        s.context.paused=false;assert(s.Run()==ObjectiveArriveResult::Running&&s.boss.faction==37);}
}
void AuthoredEvent()
{
    std::vector<DungeonEvent> events;Authored::Register(events);assert(events.size()==1);
    auto const& ev=events[0];assert(ev.mapId==209&&ev.id==3&&ev.required&&ev.repeatable);
    assert(ev.activation==EventActivation::Conditional&&ev.condition&&ev.ownsThePull&&ev.stepsOwnMovement);
    assert(ev.panelGatesBossEntry==7271&&ev.steps.size()==1&&ev.steps[0].kind==EventStepKind::Custom);
    assert(ev.steps[0].hookId==5&&ev.steps[0].timeoutMs==120000);
    Scenario s;assert(ev.condition(&s.bot,&s.context));s.boss.faction=37;assert(!ev.condition(&s.bot,&s.context));
    s.Reset();assert(ev.condition(&s.bot,&s.context));s.boss.alive=false;assert(!ev.condition(&s.bot,&s.context));
}
int main(){AdmissionAndInterruptions();PresenceAndGeometry();NativeLifecycle();AuthoredEvent();
    std::cout<<"Zumrah: ordinary spatial activation, native SmartTrigger and reset, interrupted walks, retries and unchanged access gates verified\n";}
'''


def main():
    parser = argparse.ArgumentParser()
    source_argument(parser)
    args = parser.parse_args()
    core = prepared_core()
    source = args.source or core / 'modules/mod-dungeon-clear/src'
    native, finder = native_sources(core, source)
    registry, wake, authored = production_sources(source)
    compiler = cxx()
    with tempfile.TemporaryDirectory(prefix='zumrah-') as temp:
        work = Path(temp)
        (work / 'NativeStubs.h').write_text(STUBS.replace('NATIVE_FIND_CREATURE', finder))
        shutil.copyfile(registry, work / 'DungeonEventRegistry.h')
        for name in ('Common.h', 'SharedDefines.h', 'Ai/Dungeon/DungeonClear/Data/DcDifficultyGate.h'):
            path = work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('#include "NativeStubs.h"\n')
        (work / 'NativeZumrah.cpp').write_text(native)
        (work / 'WakeZumrah.cpp').write_text(wake)
        (work / 'AuthoredZumrah.cpp').write_text(authored)
        (work / 'fixture.cpp').write_text(HARNESS)
        executable = work / ('fixture.exe' if os.name == 'nt' else 'fixture')
        flags = ['-std=c++20', '-O1', '-Wall', '-Wextra', '-Wno-missing-field-initializers', '-I', str(work)]
        if os.name != 'nt':
            flags += [*SANITIZER_FLAGS, '-no-pie']
        subprocess.run([compiler, *flags, str(work / 'fixture.cpp'), '-o', str(executable)], check=True)
        subprocess.run([str(executable)], check=True, timeout=TIMEOUT)
        gates = [
            ('wrong map', 'bot->GetMapId() != 209', 'false'),
            ('world readiness', '!bot->IsInWorld()', 'false'),
            ('missing AI', '!GET_PLAYERBOT_AI(bot)', 'false'),
            ('missing session', '!bot->GetSession()', 'false'),
            ('SelfBot control', 'IsSelfBot(bot)', 'false'),
            ('missing context', '!context || !DcRun::Of(context).enabled', '!DcRun::Of(context).enabled'),
            ('cancelled clear', '!DcRun::Of(context).enabled || ', ''),
            ('paused clear', ' || DcRun::Of(context).paused', ''),
            ('missing boss credited', 'if (!zumrah || zumrah->GetSpawnId() != ZF_ZUMRAH_SPAWN)\n            return ObjectiveArriveResult::Running;', 'if (!zumrah || zumrah->GetSpawnId() != ZF_ZUMRAH_SPAWN)\n            return ObjectiveArriveResult::Done;'),
            ('wrong spawn', 'zumrah->GetSpawnId() != ZF_ZUMRAH_SPAWN', 'false'),
            ('premature hostile completion', 'zumrah->IsHostileTo(bot)', 'true'),
            ('neutral faction accepted', 'zumrah->GetFaction() != ZF_ZUMRAH_FACTION_FRIENDLY', 'false'),
            ('missing trigger', '!trigger || trigger->map != 209', 'trigger->map != 209'),
            ('wrong trigger map', 'trigger->map != 209', 'false'),
            ('dead approach', '!bot->IsAlive()', 'false'),
            ('combat interruption', 'bot->IsInCombat()', 'false'),
            ('flight interruption', 'bot->IsInFlight()', 'false'),
            ('pending transfer', 'bot->IsBeingTeleported()', 'false'),
            ('remote mover', 'bot->m_mover != bot', 'false'),
            ('cast interruption', 'bot->IsNonMeleeSpellCast(false)', 'false'),
            ('loot interruption', 'bot->GetLootGUID()', 'false'),
            ('native arrival check', '!bot->IsInAreaTriggerRadius(trigger)', 'false'),
            ('real mesh route', 'DcEarnedPlay::ReachableLeg(bot, trigger->x, trigger->y, trigger->z)', 'true'),
            ('crowd controlled movement', 'ai->CanMove()', 'true'),
            ('movement restart', '!bot->isMoving() && ', ''),
            ('generated path', '/*generatePath*/ true, false', '/*generatePath*/ false, false'),
            ('arrival hold', 'DcMovement::StopBot(bot, DcMovement::Stop::Hold);', '(void)0;'),
            ('native opcode', 'bot->GetSession()->HandleAreaTriggerOpcode(packet);', '(void)packet;'),
            ('success before native observation', 'bot->GetSession()->HandleAreaTriggerOpcode(packet);\n        return ObjectiveArriveResult::Running;', 'bot->GetSession()->HandleAreaTriggerOpcode(packet);\n        return ObjectiveArriveResult::Done;'),
            ('earned hook denied', 'hookId != 1 && hookId != 5', 'hookId != 1'),
            ('unrelated shortcut allowed', 'hookId != 1 && hookId != 5', 'false'),
        ]
        mutations = [(label, 'WakeZumrah.cpp', old, new) for label, old, new in gates]
        mutations += [
            ('conditional map', 'AuthoredZumrah.cpp', 'bot->GetMapId() != 209', 'false'),
            ('conditional world readiness', 'AuthoredZumrah.cpp', '!bot->IsInWorld()', 'false'),
            ('conditional spawn', 'AuthoredZumrah.cpp', 'zumrah->GetSpawnId() == ZF_ZUMRAH_SPAWN &&', ''),
            ('conditional native faction', 'AuthoredZumrah.cpp', 'zumrah->GetFaction() == ZF_ZUMRAH_FACTION_FRIENDLY', 'true'),
            ('reset retry', 'AuthoredZumrah.cpp', '.Repeatable()', ''),
            ('pull ownership', 'AuthoredZumrah.cpp', '.OwnsThePull()', ''),
            ('movement ownership', 'AuthoredZumrah.cpp', '.StepsOwnMovement()', ''),
            ('finite approach', 'AuthoredZumrah.cpp', '.Timeout(120000)', ''),
            ('native living trigger', 'NativeZumrah.cpp', '!player->IsAlive()', 'false'),
        ]
        reject_mutants(work, mutations,
                       lambda directory, binary: [compiler, '-std=c++20', '-O1', '-I', str(directory),
                                                   str(directory / 'fixture.cpp'), '-o', str(binary)],
                       'Zumrah activation')


if __name__ == '__main__':
    main()
