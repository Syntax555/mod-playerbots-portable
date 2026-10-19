"""Exercise earned Ring of Law movement, the native spatial trigger and core completion."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
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
    source_argument,
    wdbc,
)
from TestDefiasCannon import sql_rows
from TestEarnedDungeonEvents import stubs as audit_stubs


def native_sources(core, source):
    brd = core / 'src/server/scripts/EasternKingdoms/BlackrockMountain/BlackrockDepths'
    header = (brd / 'blackrock_depths.h').read_text()
    for name, value in (('TYPE_RING_OF_LAW', 1), ('NPC_GRIMSTONE', 10096)):
        assert re.search(rf'\b{name}\s*=\s*{value}\b', header)
    trigger = sql_rows(core, 'areatrigger', {1526})[0]
    assert [float(trigger[key]) for key in ('map', 'x', 'y', 'z', 'radius')] == [230, 596.432, -188.498, -50, 8]
    assert sql_rows(core, 'areatrigger_scripts', {1526})[0]['ScriptName'] == 'at_ring_of_law'
    portals = sql_rows(core, 'areatrigger_teleport', {1466, 1526})
    assert {int(row['ID']) for row in portals} == {1466}
    assert not re.search(r'^\(1526,', (core / 'data/sql/base/db_world/areatrigger_teleport.sql').read_text(), re.MULTILINE)
    scripts = (brd / 'blackrock_depths.cpp').read_text()
    native_trigger = function(scripts.split('class at_ring_of_law', 1)[1], 'bool OnTrigger(').replace(' override', '')
    native = 'struct NativeRingTrigger { ' + native_trigger + ' };\n'
    player = (core / 'src/server/game/Entities/Player/Player.cpp').read_text()
    native += function(player, 'bool Player::IsInAreaTriggerRadius(') + '\n'
    position = (core / 'src/server/game/Entities/Object/Position.cpp').read_text()
    native += function(position, 'bool Position::IsWithinBox(') + '\n'
    world_object = (core / 'src/server/game/Entities/Object/Object.cpp').read_text()
    native += function(world_object, 'float WorldObject::GetDistance(float x, float y, float z)')
    assert 'IsInWorld() && obj->IsInWorld() && (FindMap() == obj->FindMap())' in function(world_object, 'bool WorldObject::IsInMap(')
    object_header = (core / 'src/server/game/Entities/Object/Object.h').read_text()
    assert 'GetPhaseMask() & phasemask : GetPhaseMask() == phasemask' in object_header
    handler = function((core / 'src/server/game/Handlers/MiscHandler.cpp').read_text(),
                       'void WorldSession::HandleAreaTriggerOpcode(')
    assert handler.index('player->IsInAreaTriggerRadius(') < handler.index('sScriptMgr->OnAreaTrigger(player, atEntry)')
    assert 'player->IsInFlight()' in handler and 'sObjectMgr->GetAreaTrigger(triggerId)' in handler
    # The handler double stops at the script boundary. Native scripts, not the
    # driver, own the cooldown, summon chain, combat watchdog and final credit.
    instance = (brd / 'instance_blackrock_depths.cpp').read_text()
    ring_state = function(instance, 'void SetData(uint32 type, uint32 data) override').split('case TYPE_RING_OF_LAW:', 1)[1]
    ring_state = ring_state[:ring_state.index('case TYPE_VAULT:')]
    assert 'encounter[0] = data;' in ring_state
    assert 'instance->SummonCreature(NPC_GRIMSTONE, GrimstonePositon)' in ring_state
    assert 'timeRingFail = GameTime::GetGameTime().count();' in ring_state
    assert 'SetData(TYPE_RING_OF_LAW, NOT_STARTED);' in ring_state
    get_data = function(instance, 'uint32 GetData(uint32 type) const override')
    assert re.search(r'case TYPE_RING_OF_LAW:\s*return encounter\[0\];', get_data)
    assert re.search(r'case DATA_TIME_RING_FAIL:\s*return timeRingFail;', get_data)
    grimstone = scripts.split('struct npc_grimstone', 1)[1]
    deaths = function(grimstone, 'void SummonedCreatureDies(')
    assert 'summons.Despawn(summon);' in deaths and 'if (summons.empty())' in deaths and 'eventTimer = 5000;' in deaths
    reset = function(grimstone, 'bool updateReset(')
    assert 'creature->IsAlive() && creature->GetVictim()' in reset and 'resetTimer = 30000;' in reset
    update = function(grimstone, 'void UpdateEscortAI(')
    assert all(token in update for token in ('updateReset(diff)', 'summons.DespawnAll();',
        'instance->SetData(TYPE_RING_OF_LAW, FAIL);', 'SpawnWave(MobSpawnId); // wave 1',
        'SpawnWave(MobSpawnId); // wave 2', 'SummonBoss();'))
    waypoint = function(grimstone, 'void WaypointReached(')
    assert re.search(r'case 5:.*UpdateEncounterState\(ENCOUNTER_CREDIT_KILL_CREATURE, NPC_GRIMSTONE, me\);\s*instance->SetData\(TYPE_RING_OF_LAW, DONE\);', waypoint, re.DOTALL)
    helper = (source / 'DcRingOfLaw.cpp').read_text()
    for shortcut in ('SetData(', 'SetBossState(', 'SummonCreature(', 'TeleportTo(', 'AddItem(', 'StoreNewItem(', 'SetGoState('):
        assert shortcut not in helper, shortcut
    movement = (source / 'Ai/Dungeon/DungeonClear/Util/DcMovement.cpp').read_text()
    assert 'return !DcRun::Of(ctx).paused;' in function(movement, 'bool DcMovementAllowed(')
    stop = function(movement, 'void StopBot(')
    assert 'FOLLOW_MOTION_TYPE' in stop and 'mm->Clear();' in stop
    follower = function((source / 'Ai/Dungeon/DungeonClear/Action/DcFollowerActions.cpp').read_text(),
                        'bool DungeonClearFollowTankAction::Execute(')
    assert follower.index('lootYieldStart = 0;') < follower.index('DcRingOfLaw::Follow(bot, tank)')
    assert follower.index('DcRingOfLaw::Follow(bot, tank)') < follower.index('float const dist =')
    hook = (source / 'Ai/Dungeon/DungeonClear/Overrides/ObjectiveHookRegistry.cpp').read_text()
    assert 'return DcRingOfLaw::Run(bot);' in function(hook, 'ObjectiveArriveResult EnsureRingStarted(')
    assert 'if (DcEarnedPlay::Active() && hookId != 1)\n        return ObjectiveArriveResult::Blocked;' in function(hook, 'ObjectiveArriveResult ObjectiveHookRegistry::Run(')
    objective = (source / 'Ai/Dungeon/DungeonClear/Action/DcEngageActions.cpp').read_text()
    assert 'DcPullPlanner::MaintainScoutCamp(botAI, context);' in function(objective, 'bool DcObjectiveArriveAction::Execute(')
    pull_mode = (source / 'Ai/Dungeon/DungeonClear/Value/DungeonClearPullModeCurrentValue.cpp').read_text()
    assert 'DungeonEventExecutor::IsPullOwningEventDriving(bot, context)' in pull_mode and 'return false;' in pull_mode
    executor = (source / 'Ai/Dungeon/DungeonClear/Util/DungeonEventExecutor.cpp').read_text()
    custom = executor.split('case EventStepKind::Custom:', 1)[1].split('case EventStepKind::Gossip:', 1)[0]
    assert 'ObjectiveHookRegistry::Run(step.hookId, bot, context, dummy)' in custom
    assert all(f'case ObjectiveArriveResult::{result}:' in custom and f'return StepResult::{result};' in custom
               for result in ('Done', 'Running', 'Blocked'))
    assert 'IsPersistentAnchoredEventActive(context)' in function(executor, 'bool DungeonEventExecutor::IsPullOwningEventDriving(')
    persistent = function(executor, 'bool DungeonEventExecutor::IsPersistentAnchoredEventActive(')
    assert all(token in persistent for token in ('next->kind != DungeonAnchorKind::Objective', '!ev->persistent',
        'prog.instanceId != instanceId', 'ev->steps.front().kind == EventStepKind::Custom && ev->stepsOwnMovement',
        'prog.eventId == ev->id && started && prog.stepIndex < ev->steps.size()'))
    camp = function((source / 'Ai/Dungeon/DungeonClear/Util/DcPullPlanner.cpp').read_text(), 'void DcPullPlanner::MaintainScoutCamp(')
    assert all(token in camp for token in ('DcKey::PullModeCurrent', 'ShouldReleaseStandingPull(',
        'DcCombatFlag::AnyPartyEngagement(bot)', 'DcLeaderSignal::IsPullPhaseHolding(',
        'pull.Transition(DcPullPhase::Idle,', 'pull.PublishCamp(Position(),'))
    print('Native Ring contracts: spatial script dispatch, two waves, random boss, combat watchdog, 120-second retry cooldown and final waypoint credit verified')
    return native, function(header, 'enum DataTypes') + ';'


STUBS = r'''#pragma once
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <ctime>
#include <functional>
#include <map>
#include <string>
#include <unordered_map>
#include <vector>
using uint8=uint8_t;using uint32=uint32_t;using int32=int32_t;
enum class ObjectiveArriveResult{Done,Running,Blocked};
enum class StepResult:uint8{Running,Done,Blocked,Failed};
enum TeamId{TEAM_ALLIANCE,TEAM_HORDE,TEAM_NEUTRAL};
enum class DcDifficultyGate:uint8{Any,NormalOnly,HeroicOnly};
struct DcDiffKey{bool IsHeroic()const{return false;}};
constexpr uint32 NOT_STARTED=0,IN_PROGRESS=1,FAIL=2,DONE=3,SPECIAL=4;
constexpr uint32 CMSG_AREATRIGGER=1,FORCED_MOVEMENT_NONE=0;
NATIVE_DATA_TYPES
struct AreaTrigger{uint32 entry=1526,map=230;float x=596.432f,y=-188.498f,z=-50.0f,radius=8.0f,length=0,width=0,height=0,orientation=0;};
struct Position
{
    float x=596.432f,y=-188.498f,z=-53.9f,orientation=0;
    Position()=default;Position(float px,float py,float pz,float o):x(px),y(py),z(pz),orientation(o){}
    float GetPositionX()const{return x;}float GetPositionY()const{return y;}float GetPositionZ()const{return z;}
    float GetOrientation()const{return orientation;}
    bool IsWithinBox(Position const&,float,float,float)const;
};
struct WorldObject:Position
{
    float GetObjectSize()const{return 0.3889999986f;}
    float GetExactDist(float px,float py,float pz)const{return std::sqrt((px-x)*(px-x)+(py-y)*(py-y)+(pz-z)*(pz-z));}
    float GetDistance(float,float,float)const;
};
struct InstanceScript
{
    uint32 state=NOT_STARTED,failedAt=0,writes=0,grimstones=0;
    uint32 GetData(uint32 key)const{assert(key==TYPE_RING_OF_LAW||key==DATA_TIME_RING_FAIL);return key==TYPE_RING_OF_LAW?state:failedAt;}
    void SetData(uint32 key,uint32 value){assert(key==TYPE_RING_OF_LAW&&value==IN_PROGRESS);state=value;++writes;++grimstones;}
};
namespace GameTime{inline time_t now=1000;struct Time{time_t value;time_t count()const{return value;}};inline Time GetGameTime(){return {now};}}
struct DungeonEventProgress{uint32 eventId=1;};
template<class T>struct Value{DungeonEventProgress data;DungeonEventProgress& Get(){return data;}};
struct AiObjectContext
{
    bool active=true,enabled=true,paused=false;Value<DungeonEventProgress&> progress;
    template<class T>Value<T>* GetValue(char const*){return &progress;}
};
namespace DcRun{inline AiObjectContext& Of(AiObjectContext* context){return *context;}}
namespace DcKey{constexpr char EventProgress[]="dungeon clear event progress";}
class Player;
struct DungeonBossInfo{};
struct ObjectiveHookRegistry
{
    using Hook=std::function<ObjectiveArriveResult(Player*,AiObjectContext*,DungeonBossInfo const&)>;
    using HookTable=std::unordered_map<uint32,Hook>;
    static ObjectiveArriveResult Run(uint32,Player*,AiObjectContext*,DungeonBossInfo const&);
};
inline uint32 getMSTime(){return 0;}
#define LOG_WARN(...) ((void)0)
struct PlayerbotAI
{
    Player* bot;bool movable=true,hasContext=true;AiObjectContext context;
    bool CanMove()const{return movable;}AiObjectContext* GetAiObjectContext(){return hasContext?&context:nullptr;}
};
struct Group{struct MemberSlot{uint32 guid;};std::vector<MemberSlot> slots;std::vector<MemberSlot> const& GetMemberSlots()const{return slots;}};
struct MotionMaster
{
    Player* bot;uint32 calls=0;bool generated=false;
    void MovePoint(uint32,float,float,float,uint32,float,float,bool,bool);
};
struct WorldPacket{uint32 opcode,id=0;explicit WorldPacket(uint32 op):opcode(op){}WorldPacket& operator<<(uint32 value){id=value;return *this;}};
struct WorldSession{Player* bot;uint32 packets=0;bool accepted=true;void HandleAreaTriggerOpcode(WorldPacket&);};
class Player:public WorldObject
{
public:
    uint32 guid=1,mapId=230,instanceId=1,stops=0,phase=1,loot=0;bool ai=true,world=true,alive=true,combat=false;
    bool flight=false,transfer=false,casting=false,moving=false,reachable=true,hasSession=true,hasInstance=true,followGenerator=false;
    Player* m_mover=this;Group* group=nullptr;InstanceScript ownInstance;InstanceScript* instance=&ownInstance;
    PlayerbotAI botAI{this};WorldSession session{this};MotionMaster motion{this};
    uint32 GetMapId()const{return mapId;}bool IsInWorld()const{return world;}bool IsAlive()const{return alive;}
    bool IsInCombat()const{return combat;}bool IsInFlight()const{return flight;}bool IsBeingTeleported()const{return transfer;}
    bool IsNonMeleeSpellCast(bool)const{return casting;}uint32 GetLootGUID()const{return loot;}
    bool IsInMap(Player* other)const{return world&&other->world&&mapId==other->mapId&&instanceId==other->instanceId;}
    bool InSamePhase(Player* other)const{return phase&other->phase;}bool isMoving()const{return moving;}
    bool IsInAreaTriggerRadius(AreaTrigger const*,float delta=0)const;
    InstanceScript* GetInstanceScript(){return hasInstance?instance:nullptr;}WorldSession* GetSession(){return hasSession?&session:nullptr;}
    MotionMaster* GetMotionMaster(){return &motion;}Group* GetGroup(){return group;}
};
void MotionMaster::MovePoint(uint32,float x,float y,float z,uint32,float,float,bool generate,bool)
{assert(bot->reachable);assert(x==596.432f&&y==-188.498f&&z==-53.9f);++calls;generated=generate;bot->moving=true;}
#define GET_PLAYERBOT_AI(bot) ((bot)->ai?&(bot)->botAI:nullptr)
struct ObjectMgr{AreaTrigger trigger;bool present=true;AreaTrigger const* GetAreaTrigger(uint32 id){assert(id==1526);return present?&trigger:nullptr;}}objectMgr;
ObjectMgr* sObjectMgr=&objectMgr;
namespace ObjectAccessor{inline std::map<uint32,Player*> players;inline Player* FindConnectedPlayer(uint32 id){auto i=players.find(id);return i==players.end()?nullptr:i->second;}}
namespace DcEarnedPlay{inline bool active=true;inline bool Active(){return active;}inline bool ReachableLeg(Player* bot,float,float,float){return bot->reachable;}}
namespace DcMovement
{
    enum class Stop{Hold};inline bool DcMovementAllowed(PlayerbotAI* ai){return ai&&ai->hasContext&&!ai->context.paused;}
    inline void StopBot(Player* bot,Stop){++bot->stops;bot->moving=false;bot->followGenerator=false;}
}
struct DungeonEventExecutor{static bool IsPersistentAnchoredEventActive(AiObjectContext* ctx){return ctx->active;}};
'''


HARNESS = r'''
#include "DcRingOfLaw.cpp"
#include "NativeRing.cpp"
#include "AuthoredRing.cpp"
#include "HookDispatch.cpp"
#include <iostream>
void WorldSession::HandleAreaTriggerOpcode(WorldPacket& packet)
{
    ++packets;assert(packet.opcode==CMSG_AREATRIGGER&&packet.id==1526);
    auto* trigger=sObjectMgr->GetAreaTrigger(packet.id);
    if(accepted&&!bot->IsInFlight()&&bot->IsInAreaTriggerRadius(trigger))NativeRingTrigger{}.OnTrigger(bot,trigger);
}
using DcRingOfLaw::Run;using DcRingOfLaw::Follow;using DcRingOfLaw::IsActive;
void reset(){objectMgr={};ObjectAccessor::players.clear();GameTime::now=1000;DcEarnedPlay::active=true;}
void outside(Player& bot){bot.x+=20;}
void running(Player& bot){assert(Run(&bot)==ObjectiveArriveResult::Running);}
void quiet(Player& bot){running(bot);assert(!bot.session.packets&&!bot.motion.calls&&!bot.ownInstance.writes);}
void RunGates()
{
    assert(Run(nullptr)==ObjectiveArriveResult::Blocked);
    for(uint32 gate=0;gate<8;++gate){reset();Player bot;
        switch(gate){case 0:bot.mapId=1;break;case 1:bot.world=false;break;case 2:bot.ai=false;break;
            case 3:bot.hasSession=false;break;case 4:bot.hasInstance=false;break;case 5:objectMgr.present=false;break;
            case 6:objectMgr.trigger.map=1;break;case 7:bot.mapId=0;break;}
        assert(Run(&bot)==ObjectiveArriveResult::Blocked);assert(!bot.session.packets&&!bot.motion.calls);}
    for(uint32 gate=0;gate<9;++gate){reset();Player bot;outside(bot);
        switch(gate){case 0:bot.alive=false;break;case 1:bot.combat=true;break;case 2:bot.flight=true;break;
            case 3:bot.transfer=true;break;case 4:bot.m_mover=nullptr;break;case 5:bot.casting=true;break;
            case 6:bot.loot=99;break;case 7:bot.botAI.context.paused=true;break;case 8:bot.ai=false;break;}
        if(gate==8)assert(Run(&bot)==ObjectiveArriveResult::Blocked);else quiet(bot);
        assert(!bot.motion.calls&&!bot.session.packets);}
    for(uint32 gate=0;gate<3;++gate){reset();Player bot;outside(bot);
        if(gate==0)bot.reachable=false;
        if(gate==1)bot.botAI.movable=false;
        if(gate==2)bot.moving=true;
        quiet(bot);}
    // A queued objective after dc off must not start even a fully gathered party.
    for(uint32 gate=0;gate<3;++gate){reset();Player bot;
        if(gate==0)bot.botAI.hasContext=false;
        if(gate==1)bot.botAI.context.enabled=false;
        if(gate==2)bot.botAI.context.paused=true;
        quiet(bot);bot.ownInstance.state=DONE;quiet(bot);}
    reset();Player walker;outside(walker);running(walker);
    assert(walker.motion.calls==1&&walker.motion.generated&&walker.moving&&!walker.session.packets);
    running(walker);assert(walker.motion.calls==1); // A movement order does not prove arrival.
    walker.x=objectMgr.trigger.x;running(walker);
    assert(walker.stops==1&&!walker.moving&&walker.session.packets==1&&walker.ownInstance.state==IN_PROGRESS);
}
void NativeGeometry()
{
    for(float offset:{7.9f,8.0f,8.38f,8.5f,9.0f}){reset();Player bot;bot.z=objectMgr.trigger.z;bot.x+=offset;
        bool inside=bot.IsInAreaTriggerRadius(&objectMgr.trigger);assert(inside==(offset<=8.38f));
        running(bot);assert(bot.session.packets==(inside?1u:0u));assert(bot.motion.calls==(inside?0u:1u));}
    reset();Player below;below.z=-84;running(below);assert(!below.session.packets&&below.motion.calls==1);
    reset();Player gallery;gallery.z=-35;running(gallery);assert(!gallery.session.packets&&gallery.motion.calls==1);
    // A radius check remains authoritative if the native volume becomes a box.
    reset();objectMgr.trigger.radius=0;objectMgr.trigger.length=8;objectMgr.trigger.width=2;objectMgr.trigger.height=8;
    objectMgr.trigger.orientation=float(M_PI/2);Player box;box.z=-50;box.x+=2;running(box);assert(!box.session.packets);
    box.x=objectMgr.trigger.x;box.y+=3;running(box);assert(box.session.packets==1);
}
void PartyGates()
{
    for(uint32 gate=0;gate<9;++gate){reset();Player leader,member;member.guid=2;Group group;
        group.slots={{1},{2}};leader.group=&group;ObjectAccessor::players={{1,&leader},{2,&member}};
        switch(gate){case 0:ObjectAccessor::players.erase(2);break;case 1:member.world=false;break;
            case 2:member.alive=false;break;case 3:member.mapId=1;break;case 4:member.instanceId=2;break;
            case 5:member.phase=2;break;case 6:member.flight=true;break;case 7:member.transfer=true;break;
            case 8:outside(member);break;}
        running(leader);assert(!leader.session.packets&&!leader.ownInstance.writes&&!member.motion.calls);}
    reset();Player leader,member;member.guid=2;Group group;group.slots={{1},{2}};leader.group=&group;
    ObjectAccessor::players={{1,&leader},{2,&member}};outside(member);running(leader);assert(!leader.session.packets);
    assert(Follow(&member,&leader)&&member.motion.calls==1&&member.motion.generated);
    running(leader);assert(!leader.session.packets); // Follow's path has not arrived yet.
    member.x=objectMgr.trigger.x;member.followGenerator=true;assert(Follow(&member,&leader));
    assert(!member.followGenerator&&!member.moving&&member.stops==1&&!member.session.packets);
    running(leader);assert(leader.session.packets==1&&leader.ownInstance.state==IN_PROGRESS);
    assert(!Follow(&member,&leader)); // Combat and ordinary formation own the running encounter.
}
void FollowGates()
{
    reset();Player leader,member;assert(!Follow(nullptr,&leader)&&!Follow(&member,nullptr)&&!IsActive(nullptr));
    for(uint32 gate=0;gate<16;++gate){reset();Player leader,member;outside(member);
        switch(gate){case 0:leader.mapId=1;break;case 1:member.world=false;break;case 2:member.mapId=1;break;
            case 3:member.instanceId=2;break;case 4:member.phase=2;break;case 5:leader.ai=false;break;
            case 6:leader.botAI.hasContext=false;break;case 7:leader.botAI.context.active=false;break;
            case 8:leader.botAI.context.progress.data.eventId=2;break;case 9:leader.hasInstance=false;break;
            case 10:leader.ownInstance.state=IN_PROGRESS;break;case 11:objectMgr.present=false;break;
            case 12:objectMgr.trigger.map=1;break;case 13:leader.world=false;break;
            case 14:leader.botAI.context.enabled=false;break;case 15:leader.botAI.context.paused=true;break;}
        if(gate==0||(gate>=5&&gate<=8)||gate>=13)assert(!IsActive(&leader));
        assert(!Follow(&member,&leader)&&!member.motion.calls&&!member.session.packets);}
    for(uint32 gate=0;gate<10;++gate){reset();Player leader,member;outside(member);
        switch(gate){case 0:member.ai=false;break;case 1:member.alive=false;break;case 2:member.combat=true;break;
            case 3:member.flight=true;break;case 4:member.transfer=true;break;case 5:member.m_mover=nullptr;break;
            case 6:member.casting=true;break;case 7:member.loot=1;break;case 8:member.botAI.context.paused=true;break;
            case 9:member.botAI.movable=false;break;}
        assert(Follow(&member,&leader)&&!member.motion.calls&&!member.session.packets);}
}
void NativeEventLifecycle()
{
    reset();Player bot;bot.session.accepted=false;running(bot);assert(bot.session.packets==1&&!bot.ownInstance.writes);
    bot.session.accepted=true;running(bot);assert(bot.session.packets==2&&bot.ownInstance.state==IN_PROGRESS);
    for(uint32 tick=0;tick<5;++tick)running(bot);
    assert(bot.session.packets==2&&bot.ownInstance.grimstones==1); // Already started; empty floor is not DONE.
    bot.combat=true;uint32 fightingPackets=bot.session.packets,fightingMoves=bot.motion.calls;running(bot);
    assert(bot.session.packets==fightingPackets&&bot.motion.calls==fightingMoves);
    bot.combat=false;bot.ownInstance.state=NOT_STARTED;bot.ownInstance.failedAt=uint32(GameTime::now);
    for(uint32 tick=0;tick<3;++tick)running(bot);
    assert(bot.session.packets==5&&bot.ownInstance.grimstones==1);
    GameTime::now+=119;running(bot);assert(bot.ownInstance.state==NOT_STARTED);
    ++GameTime::now;running(bot);assert(bot.ownInstance.state==IN_PROGRESS&&bot.ownInstance.grimstones==2);
    for(uint32 state:{FAIL,SPECIAL,5u}){bot.ownInstance.state=state;uint32 packets=bot.session.packets;running(bot);assert(bot.session.packets==packets);}
    bot.ownInstance.state=DONE;bot.alive=false;bot.combat=true;outside(bot);uint32 packets=bot.session.packets;
    assert(Run(&bot)==ObjectiveArriveResult::Done&&bot.session.packets==packets);
    bot.alive=true;bot.combat=false;assert(!Follow(&bot,&bot));
}
void AuthoredTests()
{
    std::vector<DungeonEvent> events;RegisterRingEvent(events);assert(events.size()==1);auto const& event=events.front();
    assert(event.mapId==230&&event.id==1&&event.required&&event.persistent&&event.stepsOwnMovement);
    assert(event.activation==EventActivation::Anchored&&event.orderIndex==3&&event.steps.size()==1);
    auto const& step=event.steps.front();assert(step.kind==EventStepKind::Custom&&step.hookId==1&&step.timeoutMs==600000);
}
void HookTests()
{
    reset();Player bot;DungeonBossInfo info;shortcutCalls=0;
    assert(ObjectiveHookRegistry::Run(0,&bot,nullptr,info)==ObjectiveArriveResult::Done);
    assert(ObjectiveHookRegistry::Run(2,&bot,nullptr,info)==ObjectiveArriveResult::Blocked&&!shortcutCalls);
    assert(ObjectiveHookRegistry::Run(1,&bot,nullptr,info)==ObjectiveArriveResult::Running&&bot.session.packets==1);
    bot.mapId=229;assert(ObjectiveHookRegistry::Run(1,&bot,nullptr,info)==ObjectiveArriveResult::Blocked);
    DcEarnedPlay::active=false;assert(ObjectiveHookRegistry::Run(2,&bot,nullptr,info)==ObjectiveArriveResult::Done&&shortcutCalls==1);
}
int main()
{
    RunGates();NativeGeometry();PartyGates();FollowGates();NativeEventLifecycle();AuthoredTests();HookTests();
    std::cout<<"Ring of Law: native spatial arrival, party muster, real mesh walks, interrupted starts, core cooldown/retry, existing events and exact DONE verified\n";
}
'''


def authored_sources(source):
    registry = source / 'Ai/Dungeon/DungeonClear/Data/DungeonEventRegistry.h'
    builder = registry.with_suffix('.cpp').read_text()
    authored = ['#include "DungeonEventRegistry.h"', '#include <utility>']
    for signature in ('EventBuilder::EventBuilder(', 'EventStep& EventBuilder::Add(', 'EventBuilder& EventBuilder::Anchored(',
                      'EventBuilder& EventBuilder::Persistent(', 'EventBuilder& EventBuilder::StepsOwnMovement(',
                      'EventBuilder& EventBuilder::Custom(', 'EventBuilder& EventBuilder::Timeout('):
        authored.append(function(builder, signature))
    events = (source / 'Ai/Dungeon/DungeonClear/Data/Events/BlackrockDepthsEvents.cpp').read_text()
    authored.append(re.search(r'constexpr uint32 BRD_RING_OF_LAW_HOOK\s*=\s*1;', events).group())
    start = events.index('out.push_back(')
    end = events.index('.Build());', start) + len('.Build());')
    authored.append('void RegisterRingEvent(std::vector<DungeonEvent>& out){' + events[start:end] + '}')
    return registry, '\n'.join(authored)


def audit_ring(core, source, compiler):
    repository = Path(__file__).resolve().parents[2]
    locale = json.loads((repository / 'versions.lock.json').read_text())['clientPatch']['localizations']['deDE']
    cache = repository / '.module-cache/fixtures/Lock.dbc'
    if not cache.exists():
        url = locale['url'].removesuffix('.git').replace('github.com/', 'raw.githubusercontent.com/')
        url += f'/{locale["revision"]}/{locale["sourcePath"]}/Lock.dbc'
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            data = response.read()
        assert hashlib.sha256(data).hexdigest() == 'c49bd7ed970583a3660d5d16d6917e91e46aafc9e9ed7926281f4889d45904d0'
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
    data = cache.read_bytes()
    assert hashlib.sha256(data).hexdigest() == 'c49bd7ed970583a3660d5d16d6917e91e46aafc9e9ed7926281f4889d45904d0'
    rows, _ = wdbc(data, 33)
    lock = next(struct.unpack('<33I', row) for row in rows if struct.unpack_from('<I', row)[0] == 680)
    panel_lock = next(struct.unpack('<33I', row) for row in rows if struct.unpack_from('<I', row)[0] == 43)
    assert lock[1:9] == (1, 2, 2, 2, 2, 0, 0, 0)
    assert lock[9:17] == (11000, 1, 10, 11, 16, 0, 0, 0)
    assert panel_lock[1:9] == (0, 2, 0, 0, 0, 0, 0, 0) and panel_lock[9:17] == (0, 13, 0, 0, 0, 0, 0, 0)
    spell = function((core / 'src/server/game/Spells/Spell.cpp').read_text(), 'SpellCastResult Spell::CanOpenLock(')
    assert spell.index('uint32(m_spellInfo->Effects[effIndex].MiscValue) != lockInfo->Index[j]') < spell.index('SkillByLockType(')
    objects = {int(row['entry']): row for row in sql_rows(core, 'gameobject_template', {161460, 170570})}
    assert all(int(row['type']) == 0 and int(row['Data1']) == 680 for row in objects.values())
    go_data = (core / 'src/server/game/Entities/GameObject/GameObjectData.h').read_text()
    assert re.search(r'case GAMEOBJECT_TYPE_DOOR:\s*return door.lockId;', function(go_data, 'uint32 GetLockId() const'))
    authored = (source / 'Ai/Dungeon/DungeonClear/Data/Events/BlackrockDepthsEvents.cpp').read_text()
    assert re.search(r'BRD_GO_SHADOWFORGE_LOCK\s*=\s*161460;', authored)
    assert '.UseGO(BRD_GO_SHADOWFORGE_LOCK,' in function(authored, 'void RegisterBlackrockDepthsEvents(')
    panel = sql_rows(core, 'gameobject_template', {184126})[0]
    assert int(panel['type']) == 0 and int(panel['Data1']) == 43
    steamvault = (source / 'Ai/Dungeon/DungeonClear/Data/Events/SteamvaultEvents.cpp').read_text()
    assert re.search(r'SV_ACCESS_PANEL_MEK\s*=\s*184126;', steamvault)
    assert '.UseGO(SV_ACCESS_PANEL_MEK,' in function(steamvault, 'void RegisterSteamvaultEvents(')
    harness = r'''
#include "DcEarnedEvents.cpp"
#include <cassert>
#include <iostream>
int main(){
    LOCK_ROW
    objectMgr.templates={{161460,{680}},{170570,{680}},{184126,{43}}};
    EventStep step;step.kind=EventStepKind::Custom;step.hookId=1;
    assert(DcEarnedEvents::StepAllowed(step));
    for(uint32 hook:{0u,2u,5u,40u}){step.hookId=hook;assert(!DcEarnedEvents::StepAllowed(step));}
    step.hookId=1;DungeonEvent ring;ring.mapId=230;ring.id=1;ring.name="Ring of Law";ring.steps={step};
    events[{230,1}]=ring;roster[230]={{"Ring of Law",0,1}};
    std::string reason;assert(DcEarnedEvents::MapAudited(230,reason)&&reason.empty());
    events[{230,1}].mapId=229;assert(!DcEarnedEvents::MapAudited(230,reason));events[{230,1}].mapId=230;
    events[{230,1}].id=2;assert(!DcEarnedEvents::MapAudited(230,reason));events[{230,1}].id=1;
    EventStep use;use.kind=EventStepKind::UseGameObject;use.goEntry=161460;
    DungeonEvent shadow;shadow.name="Shadowforge Lock";shadow.steps={use};events[{230,2}]=shadow;
    roster[230].push_back({"Shadowforge Lock",0,2});
    assert(!DcEarnedEvents::MapAudited(230,reason));assert(reason.find("Shadowforge Lock")!=std::string::npos);
    assert(reason.find("key or locked object")!=std::string::npos);
    Player bot;GameObject door;door.info.lock=680;assert(!DcEarnedEvents::CanOpen(&bot,&door));
    bot.items.insert(11000);assert(DcEarnedEvents::CanOpen(&bot,&door));
    door.flags=GO_FLAG_LOCKED;assert(DcEarnedEvents::CanOpen(&bot,&door));
    bot.items.clear();assert(!DcEarnedEvents::CanOpen(&bot,&door));
    use.goEntry=184126;DungeonEvent panel;panel.name="Main Chambers Door";panel.steps={use};events[{545,1}]=panel;
    roster[545]={{"Main Chambers Door",0,1}};assert(!DcEarnedEvents::MapAudited(545,reason));
    assert(reason.find("Main Chambers Door")!=std::string::npos);door.info.lock=43;door.flags=0;
    assert(!DcEarnedEvents::CanOpen(&bot,&door));
    std::cout<<"BRD audit: Ring driver accepted, native Shadowforge lock 680 still refuses autonomous recruitment\n";
}
'''
    def lock_row(record):
        fields = ','.join('{' + ','.join(str(value) for value in record[start:start + 8]) + '}'
                          for start in (1, 9, 17))
        return f'sLockStore.rows[{record[0]}]=LockEntry{{{record[0]},{fields}}};'
    with tempfile.TemporaryDirectory(prefix='ring-audit-') as temp:
        work = Path(temp)
        (work / 'NativeStubs.h').write_text(audit_stubs(core, source))
        for name in ('Define.h', 'DBCStores.h', 'GameObject.h', 'ObjectMgr.h', 'Player.h', 'SharedDefines.h',
                     'Ai/Dungeon/DungeonClear/Data/BossSpawnIndex.h', 'Ai/Dungeon/DungeonClear/Data/DungeonEventRegistry.h',
                     'Ai/Dungeon/DungeonClear/Util/DcDifficulty.h', 'Ai/Dungeon/DungeonClear/Overrides/BossRosterRegistry.h'):
            path = work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('#include "NativeStubs.h"\n')
        for name in ('DcEarnedEvents.cpp', 'DcEarnedEvents.h'):
            shutil.copyfile(source / name, work / name)
        (work / 'fixture.cpp').write_text(harness.replace('LOCK_ROW', lock_row(lock) + lock_row(panel_lock)))
        build = lambda directory, executable: [compiler, '-std=c++20', '-O1', '-I', str(directory), str(directory / 'fixture.cpp'), '-o', str(executable)]
        exe = work / ('fixture.exe' if os.name == 'nt' else 'fixture')
        subprocess.run(build(work, exe), check=True)
        subprocess.run([str(exe)], check=True, timeout=TIMEOUT)
        mutations = [
            ('arbitrary custom shortcut', 'DcEarnedEvents.cpp', 'return step.hookId == 1;', 'return true;'),
            ('Ring driver denied', 'DcEarnedEvents.cpp', 'return step.hookId == 1;', 'return false;'),
            ('wrong map custom controller', 'DcEarnedEvents.cpp', 'ev.mapId != 230 || ', ''),
            ('wrong event custom controller', 'DcEarnedEvents.cpp', ' || ev.id != 1', ''),
            ('Shadowforge lock bypass', 'DcEarnedEvents.cpp', 'LockOpening(go->GetLockId(), nullptr) != Opening::Click', 'false'),
            ('special lock types counted as clicks', 'DcEarnedEvents.cpp', 'lock->Index[i] == LOCKTYPE_OPEN',
             'SkillByLockType(LockType(lock->Index[i])) == SKILL_NONE'),
        ]
        reject_mutants(work, mutations, build, 'Ring earned audit')


def main():
    parser = argparse.ArgumentParser()
    source_argument(parser)
    args = parser.parse_args()
    core = prepared_core()
    source = args.source or core / 'modules/mod-dungeon-clear/src'
    native, data_types = native_sources(core, source)
    registry, authored = authored_sources(source)
    compiler = cxx()
    audit_ring(core, source, compiler)
    with tempfile.TemporaryDirectory(prefix='ring-of-law-') as temp:
        work = Path(temp)
        (work / 'NativeStubs.h').write_text(STUBS.replace('NATIVE_DATA_TYPES', data_types))
        for name in ('Common.h', 'Define.h', 'DcEarnedPlay.h', 'AiObjectContext.h', 'Group.h', 'InstanceScript.h',
                     'MotionMaster.h', 'ObjectAccessor.h', 'ObjectMgr.h', 'Opcodes.h', 'Player.h', 'Playerbots.h',
                     'SharedDefines.h', 'WorldPacket.h', 'WorldSession.h',
                     'Ai/Dungeon/DungeonClear/Data/DcDifficultyGate.h', 'Ai/Dungeon/DungeonClear/DcValueKeys.h',
                     'Ai/Dungeon/DungeonClear/Overrides/ObjectiveHookRegistry.h',
                     'Ai/Dungeon/DungeonClear/Util/DcMovement.h', 'Ai/Dungeon/DungeonClear/Util/DcRun.h',
                     'Ai/Dungeon/DungeonClear/Util/DungeonEventExecutor.h'):
            path = work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('#include "NativeStubs.h"\n')
        for name in ('DcRingOfLaw.cpp', 'DcRingOfLaw.h'):
            shutil.copyfile(source / name, work / name)
        shutil.copyfile(registry, work / 'DungeonEventRegistry.h')
        (work / 'NativeRing.cpp').write_text(native)
        (work / 'AuthoredRing.cpp').write_text(authored)
        hook = (source / 'Ai/Dungeon/DungeonClear/Overrides/ObjectiveHookRegistry.cpp').read_text()
        dispatch = function(hook, 'ObjectiveArriveResult EnsureRingStarted(')
        dispatch += '''
uint32 shortcutCalls=0;
ObjectiveHookRegistry::HookTable const& Hooks(){static ObjectiveHookRegistry::HookTable hooks{
    {1,&EnsureRingStarted},{2,[](Player*,AiObjectContext*,DungeonBossInfo const&){++shortcutCalls;return ObjectiveArriveResult::Done;}}};return hooks;}
'''
        dispatch += function(hook, 'ObjectiveArriveResult ObjectiveHookRegistry::Run(')
        (work / 'HookDispatch.cpp').write_text(dispatch)
        (work / 'fixture.cpp').write_text(HARNESS)
        exe = work / ('fixture.exe' if os.name == 'nt' else 'fixture')
        flags = ['-std=c++20', '-O1', '-Wall', '-Wextra', '-Wno-missing-field-initializers', '-I', str(work)]
        if os.name != 'nt':
            flags += [*SANITIZER_FLAGS, '-no-pie']
        subprocess.run([compiler, *flags, str(work / 'fixture.cpp'), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=TIMEOUT)
        gates = [
            ('wrong map', 'bot->GetMapId() != 230', 'false'),
            ('world readiness', '!bot->IsInWorld()', 'false'),
            ('missing AI', '!GET_PLAYERBOT_AI(bot)', 'false'),
            ('missing session', '!bot->GetSession()', 'false'),
            ('missing run context', '!context || !DcRun::Of(context).enabled', '!DcRun::Of(context).enabled'),
            ('cancelled leader start', '!DcRun::Of(context).enabled || ', ''),
            ('paused leader start', ' || DcRun::Of(context).paused', ''),
            ('missing instance', '!instance || !trigger || trigger->map != 230', '!trigger || trigger->map != 230'),
            ('missing spatial trigger', '!instance || !trigger || trigger->map != 230', '!instance || trigger->map != 230'),
            ('wrong trigger map', 'trigger->map != 230', 'false'),
            ('dead movement', '!bot->IsAlive()', 'false'),
            ('combat movement', 'bot->IsInCombat()', 'false'),
            ('flight movement', 'bot->IsInFlight()', 'false'),
            ('pending transfer', 'bot->IsBeingTeleported()', 'false'),
            ('remote mover', 'bot->m_mover != bot', 'false'),
            ('cast interruption', 'bot->IsNonMeleeSpellCast(false)', 'false'),
            ('loot interruption', 'bot->GetLootGUID()', 'false'),
            ('paused movement', '!DcMovement::DcMovementAllowed(ai)', 'false'),
            ('native volume', 'bot->IsInAreaTriggerRadius(trigger)', 'true'),
            ('mesh route', 'DcEarnedPlay::ReachableLeg(bot, trigger->x, trigger->y, FloorZ)', 'true'),
            ('crowd controlled movement', 'ai->CanMove()', 'true'),
            ('restarted movement', '!bot->isMoving() && ', ''),
            ('generated path', '/*generatePath*/ true, false', '/*generatePath*/ false, false'),
            ('formation generator retained', 'DcMovement::StopBot(bot, DcMovement::Stop::Hold);', '(void)0;'),
            ('completion before core DONE', 'state == DONE', 'state != DONE'),
            ('FAIL treated as phase progress', 'state != NOT_STARTED && state != IN_PROGRESS', 'false'),
            ('already running event retriggered', ' || state == IN_PROGRESS', ''),
            ('party gate removed', 'if (Group* group = bot->GetGroup())', 'if (Group* group = nullptr)'),
            ('offline member', '!member || ', ''),
            ('member world and native map readiness', '!member->IsInWorld() || !member->IsAlive() ||\n                    !member->IsInMap(bot) || ', '!member->IsAlive() || '),
            ('dead member', '!member->IsAlive() ||', ''),
            ('member map and instance', '!member->IsInMap(bot) || ', ''),
            ('member phase', '!member->InSamePhase(bot) ||', ''),
            ('member flight', 'member->IsInFlight() || ', ''),
            ('member transfer', 'member->IsBeingTeleported() ||', ''),
            ('member spatial arrival', '!member->IsInAreaTriggerRadius(trigger)', 'false'),
            ('native opcode skipped', 'bot->GetSession()->HandleAreaTriggerOpcode(packet);', '(void)packet;'),
            ('follower leader map', 'leader->GetMapId() != 230', 'false'),
            ('follower leader world', '!leader->IsInWorld()', 'false'),
            ('follower instance', '!member->IsInMap(leader)', 'false'),
            ('follower phase', '!member->InSamePhase(leader)', 'false'),
            ('follower event active', 'DungeonEventExecutor::IsPersistentAnchoredEventActive(context)', 'true'),
            ('follower event identity', 'context->GetValue<DungeonEventProgress&>(DcKey::EventProgress)->Get().eventId == 1', 'true'),
            ('disabled leader run', 'DcRun::Of(context).enabled && ', ''),
            ('paused leader run', '!DcRun::Of(context).paused &&', ''),
            ('follower native state', 'instance->GetData(RingState) != NOT_STARTED', 'false'),
            ('follower physical movement', 'Gather(member, trigger);', '(void)member;'),
        ]
        mutations = [(label, 'DcRingOfLaw.cpp', old, new) for label, old, new in gates]
        mutations += [
            ('event persistence', 'AuthoredRing.cpp', '.Persistent()', ''),
            ('event movement ownership', 'AuthoredRing.cpp', '.StepsOwnMovement()', ''),
            ('event core driver', 'AuthoredRing.cpp', '.Custom(BRD_RING_OF_LAW_HOOK)', '.Custom(2)'),
            ('event fight budget', 'AuthoredRing.cpp', '.Timeout(600000)', ''),
            ('native cooldown', 'NativeRing.cpp', '2 * 60', '0 * 60'),
            ('unaudited hook execution', 'HookDispatch.cpp', 'DcEarnedPlay::Active() && hookId != 1', 'false'),
            ('earned Ring hook execution', 'HookDispatch.cpp', 'hookId != 1', 'true'),
            ('Ring delegate skipped', 'HookDispatch.cpp', 'return DcRingOfLaw::Run(bot);', 'return ObjectiveArriveResult::Done;'),
        ]
        reject_mutants(work, mutations, lambda directory, executable: [compiler, '-std=c++20', '-O1', '-I', str(directory),
                       str(directory / 'fixture.cpp'), '-o', str(executable)], 'Ring of Law')


if __name__ == '__main__':
    main()
