"""Exercise ordinary Wailing Caverns routes and the native Naralex escort."""
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
    sql_rows,
    wdbc,
)


def native_contracts(core, source):
    wc = core / 'src/server/scripts/Kalimdor/WailingCaverns'
    header = (wc / 'wailing_caverns.h').read_text()
    for name, value in (('TYPE_LORD_COBRAHN', 0), ('TYPE_LORD_PYTHAS', 1),
                        ('TYPE_LADY_ANACONDRA', 2), ('TYPE_LORD_SERPENTIS', 3),
                        ('TYPE_MUTANUS', 4), ('NPC_DISCIPLE_OF_NARALEX', 3678)):
        assert re.search(rf'\b{name}\s*=\s*{value}\b', header)
    instance = (wc / 'instance_wailing_caverns.cpp').read_text()
    read = function(instance, 'uint32 GetData(uint32 type) const override')
    assert all(name in read for name in ('TYPE_LORD_COBRAHN', 'TYPE_LORD_PYTHAS',
                                        'TYPE_LADY_ANACONDRA', 'TYPE_LORD_SERPENTIS'))
    # Mutanus is stored on death, but the pinned getter does not expose it.
    # A double returning DONE for GetData(4) would hide a permanent real stall.
    assert 'TYPE_MUTANUS' not in read and 'return 0;' in read
    smart = (core / 'src/server/game/AI/SmartScripts/SmartAI.cpp').read_text()
    native_get = function(smart, 'uint32 SmartAI::GetData(uint32 id) const')
    assert 'aiDataSet.find(id)' in native_get and 'return itr->second;' in native_get
    assert 'aiDataSet.clear();' in function(smart, 'void SmartAI::JustRespawned()')
    assert 'aiDataSet[id] = value;' in function(smart, 'void SmartAI::SetData(')
    assert 'GetScript()->SetPathId(entry);' in function(smart, 'bool SmartAI::LoadPath(')
    start = function(smart, 'void SmartAI::StartPath(')
    assert 'LoadPath(path, pathSource)' in start and 'AddEscortState(SMART_ESCORT_ESCORTING);' in start
    smart_header = (core / 'src/server/game/AI/SmartScripts/SmartAI.h').read_text()
    assert 'return (mEscortState & SMART_ESCORT_ESCORTING);' in function(smart_header, 'bool IsEscorted()')
    script_header = (core / 'src/server/game/AI/SmartScripts/SmartScript.h').read_text()
    assert 'return mPathId;' in function(script_header, 'uint32 GetPathId()')
    script = (core / 'src/server/game/AI/SmartScripts/SmartScript.cpp').read_text()
    escort_start = script.split('case SMART_ACTION_ESCORT_START:', 1)[1].split('case SMART_ACTION_ESCORT_PAUSE:', 1)[0]
    assert 'CAST_AI(SmartAI, me->AI())->StartPath(forcedMovement, entry, repeat, unit);' in escort_start
    assert 'while (!executionStack.empty())' in function(script, 'void SmartScript::ProcessEventsFor(')
    assert 'executionStack.emplace_back(SmartScriptFrame{ linkedEvent' in function(script, 'void SmartScript::ProcessAction(')
    smart_types = (core / 'src/server/game/AI/SmartScripts/SmartScriptMgr.h').read_text()
    assert re.search(r'SMART_ACTION_ESCORT_START\s*=\s*53,', smart_types)
    escort_paths = sql_rows(core, 'waypoints', {3678, 3679})
    assert {int(row['pointid']) for row in escort_paths if int(row['entry']) == 3678} == set(range(1, 26))
    assert {int(row['pointid']) for row in escort_paths if int(row['entry']) == 3679} == {1, 2, 3}

    object_source = (core / 'src/server/game/Entities/Object/Object.cpp').read_text()
    assert 'NearestCreatureEntryWithLiveStateInObjectRangeCheck' in function(object_source, 'Creature* WorldObject::FindNearestCreature(')
    notifiers = (core / 'src/server/game/Grids/Notifiers/GridNotifiers.h').read_text()
    nearest = function(notifiers, 'class NearestCreatureEntryWithLiveStateInObjectRangeCheck')
    assert 'u->IsAlive() == i_alive' in nearest and 'i_obj.InSamePhase(u)' in nearest
    path_source = (core / 'src/server/game/Movement/MovementGenerators/PathGenerator.cpp').read_text()
    calculate = function(path_source, 'bool PathGenerator::CalculatePath(float x,')
    assert '!Acore::IsValidMapCoord(destX, destY, destZ)' in calculate
    assert '_type = PathType(PATHFIND_NORMAL | PATHFIND_NOT_USING_PATH);' in calculate
    chat = (source / 'Ai/Dungeon/DungeonClear/Action/DungeonClearChatActions.cpp').read_text()
    halt = function(chat, 'void HaltAllMovement(')
    assert 'mm->Clear();' in halt and 'bot->StopMovingOnCurrentPos();' in halt
    off = function(chat, 'bool DcOffAction::Execute(')
    assert off.index('DisableDungeonClear(') < off.index('HaltAllMovement(bot)')
    pause = function(chat, 'bool DcPauseAction::Execute(')
    assert 'DcRun::Of(context).paused = true;' in pause and 'HaltAllMovement(bot);' in pause
    ring = (source / 'DcRingOfLaw.cpp').read_text()
    assert 'leader->GetMapId() != 230' in function(ring, 'bool IsActive(')
    assert '!IsActive(leader)' in function(ring, 'bool Follow(')

    creature = sql_rows(core, 'creature_template', {3678, 3679})
    assert all(row['AIName'] == 'SmartAI' for row in creature)
    disciple = next(row for row in creature if int(row['entry']) == 3678)
    assert int(disciple['gossip_menu_id']) == 201
    assert int(disciple['faction']) == 35 and int(disciple['npcflag']) & 1
    menu = sql_rows(core, 'gossip_menu_option', {201})
    assert len(menu) == 1 and int(menu[0]['OptionID']) == 0
    conditions = sql_rows(core, 'conditions', {15})
    prerequisites = [row for row in conditions if int(row['SourceGroup']) == 201 and int(row['SourceEntry']) == 0]
    assert len(prerequisites) == 4
    assert {int(row['ConditionValue1']) for row in prerequisites} == {0, 1, 2, 3}
    assert all(int(row['ConditionTypeOrReference']) == 13 and int(row['ConditionValue2']) == 3 and
               int(row['NegativeCondition']) == 0 and int(row['ElseGroup']) == 0 for row in prerequisites)

    rows = sql_rows(core, 'smart_scripts', {3654, 3678, 3679, 367800, 367900})
    scripts = {(int(row['entryorguid']), int(row['id'])): row for row in rows}
    def check(entry, index, **fields):
        row = scripts[entry, index]
        assert all(int(row[key]) == value for key, value in fields.items()), (entry, index, fields)
    check(3678, 1, event_type=62, event_param1=201, event_param2=0, action_type=2, action_param1=250)
    check(3678, 3, action_type=53, action_param2=3678)
    check(3678, 5, event_type=40, event_param1=1, action_type=54, action_param1=8000)
    check(3678, 8, event_type=40, event_param1=5, action_type=54, action_param1=8000)
    check(3678, 13, event_type=40, event_param1=12, action_type=54, action_param1=32500)
    check(3678, 21, event_type=40, event_param1=25, action_type=54, action_param1=1800000)
    check(3678, 22, action_type=80, action_param1=367800)
    # Native ambushes, cleansing and ritual waves must remain with SmartAI.
    check(3678, 10, action_type=12, action_param1=3636)
    check(3678, 11, action_type=12, action_param1=3636)
    check(3678, 16, action_type=11, action_param1=6270)
    check(3678, 17, action_type=107, action_param1=1)
    check(3678, 35, action_type=107, action_param1=2)
    check(3678, 31, action_type=12, action_param1=3654)
    check(3654, 5, event_type=6, action_type=45, action_param1=1, action_param2=1, target_param1=3679)
    check(3654, 6, event_type=6, action_type=34, action_param1=4, action_param2=3)
    check(3679, 0, event_type=38, event_param1=1, event_param2=1, action_type=80, action_param1=367900)
    check(367900, 3, event_param1=7000, event_param2=7000)
    check(367900, 4, event_param1=7000, event_param2=7000)
    check(367900, 5, event_param1=3000, action_type=11, action_param1=8153)
    check(367900, 9, event_param1=6000, event_param2=6000)
    check(367900, 11, action_type=45, action_param1=2, action_param2=2, target_param1=3678)
    check(3678, 24, event_type=38, event_param1=2, event_param2=2)
    check(3678, 25, action_type=53, action_param2=3679)
    credit = sql_rows(core, 'instance_encounters', {592})[0]
    assert int(credit['creditEntry']) == 3654
    repository = Path(__file__).resolve().parents[2]
    locale = json.loads((repository / 'versions.lock.json').read_text())['clientPatch']['localizations']['deDE']
    cache = repository / '.module-cache/fixtures/DungeonEncounter.dbc'
    if not cache.exists():
        url = locale['url'].removesuffix('.git').replace('github.com/', 'raw.githubusercontent.com/')
        url += f'/{locale["revision"]}/{locale["sourcePath"]}/DungeonEncounter.dbc'
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            data = response.read()
        assert hashlib.sha256(data).hexdigest() == '654b29bc4b4a3abaf4610ec2ce64d9ec7197fbefa3eaa8a522b8d29e167508ff'
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(data)
    data = cache.read_bytes()
    assert hashlib.sha256(data).hexdigest() == '654b29bc4b4a3abaf4610ec2ce64d9ec7197fbefa3eaa8a522b8d29e167508ff'
    records, _ = wdbc(data, 23)
    encounter = next(struct.unpack('<23I', row) for row in records if struct.unpack_from('<I', row)[0] == 592)
    assert encounter[1:5] == (43, 0, 7000, 7)
    structure = function((core / 'src/server/shared/DataStores/DBCStructure.h').read_text(), 'struct DungeonEncounterEntry')
    assert re.search(r'uint32\s+mapId;.*uint32\s+difficulty;.*uint32\s+encounterIndex;', structure, re.DOTALL)
    mask = function((core / 'src/server/game/Maps/Map.cpp').read_text(), 'void Map::UpdateEncounterState(')
    assert '1 << encounter->dbcEntry->encounterIndex' in mask
    movement = (source / 'Ai/Dungeon/DungeonClear/Util/DcMovement.cpp').read_text()
    assert 'mm->MoveSplinePath(&pts, FORCED_MOVEMENT_NONE);' in function(movement, 'bool SplinePath(')
    targets = function((source / 'Ai/Dungeon/DungeonClear/Util/DcTargeting.cpp').read_text(), 'Unit* DcTargeting::NearestHostileNearPoint(')
    assert all(token in targets for token in ('!u->IsAlive()', 'AttackersValue::IsPossibleTarget(u, bot)',
        'IsDungeonBossEntry(ctx, u->GetEntry())', 'DcEngageGeometry::IsEngageReachable(bot, u)'))
    gossip = function((source / 'Ai/Dungeon/DungeonClear/Util/DungeonEventExecutor.cpp').read_text(), 'bool DungeonEventExecutor::SelectGossip(')
    assert all(token in gossip for token in ('HandleGossipHelloOpcode(hello)', 'ResolveGossipListId(menu, option, gossipListId)',
        'select << npc->GetGUID() << menuId << opt;', 'HandleGossipSelectOptionOpcode(select)'))
    for name in ('DcWailingCaverns.cpp', 'DcNaralexEscort.cpp'):
        helper = (source / name).read_text()
        assert not any(shortcut in helper for shortcut in ('TeleportTo(', 'NearTeleportTo(', 'SetSpeed(', 'SetVelocity(',
            'Relocate(', 'SetData(', 'SetBossState(', 'SummonCreature(', 'SetFaction(', 'StartPath(', 'ResumePath('))


    patrol = sql_rows(core, 'creature', {38117})[0]
    assert int(patrol['id1']) == 3640 and int(patrol['map']) == 43 and int(patrol['MovementType']) == 2
    addon = sql_rows(core, 'creature_addon', {38117})[0]
    assert int(addon['path_id']) == 381170
    waypoints = sql_rows(core, 'waypoint_data', {381170})
    assert len(waypoints) == 6
    route = [(float(row['position_x']), float(row['position_y']), float(row['position_z'])) for row in waypoints[:4]]
    assert route == [(-206.648, 58.6654, -49.4123), (-187.331, 56.9268, -49.9537),
                     (-169.269, 54.0309, -40.636), (-147.96, 31.9855, -29.7619)]
    assert not any(int(row['move_type']) for row in waypoints)
    print('Native WC contracts: ground patrol ascent, four Fanglord prerequisites, ordinary gossip, escort ambushes, ritual and post-dialogue marker verified')
    return native_get, read, function(header, 'enum DataTypes') + ';', route


STUB_AUDIT_TYPES = r'''
constexpr uint8 DUNGEON_DIFFICULTY_NORMAL=0;
constexpr uint32 MAX_LOCK_CASE=8;
struct LockEntry{uint32 Type[MAX_LOCK_CASE]{},Index[MAX_LOCK_CASE]{};};
struct LockStore{LockEntry const* LookupEntry(uint32)const{return nullptr;}}sLockStore;
struct GameObjectTemplate{uint32 GetLockId()const{return 0;}};
struct ObjectMgr{GameObjectTemplate const* GetGameObjectTemplate(uint32)const{return nullptr;}}objectMgr;
ObjectMgr* sObjectMgr=&objectMgr;
struct GameObject{bool HasGameObjectFlag(uint32)const{return false;}bool ActivateToQuest(Player*)const{return true;}
    GameObjectTemplate const* GetGOInfo()const{static GameObjectTemplate go;return &go;}};
struct BossSpawnIndex{static std::vector<DungeonBossInfo> const& Get(uint32,uint8){static std::vector<DungeonBossInfo> base;return base;}};
struct BossRosterRegistry{
    static constexpr uint32 ObjectiveEntry(uint32 seq) { return 0x4F000000u | seq; }
    static std::vector<DungeonBossInfo> Apply(uint32,DcDiffKey,std::vector<DungeonBossInfo>);
};
inline std::vector<DungeonEvent> authoredEvents;
DungeonEvent const* DungeonEventRegistry::Find(uint32 mapId,uint32 id){
    for(auto const& ev:authoredEvents){if(ev.mapId==mapId&&ev.id==id)return &ev;}
    return nullptr;}
std::vector<DungeonEvent const*> DungeonEventRegistry::Conditional(uint32 mapId,DcDiffKey key){
    std::vector<DungeonEvent const*> out;for(auto const& ev:authoredEvents)
        if(ev.mapId==mapId&&ev.activation==EventActivation::Conditional&&DcGateMatches(ev.gate,key))out.push_back(&ev);
    return out;}
'''


STUBS = r'''#pragma once
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <string>
#include <type_traits>
#include <vector>
#include <unordered_set>
using uint8=uint8_t;using uint32=uint32_t;using int32=int32_t;
enum TeamId{TEAM_ALLIANCE,TEAM_HORDE,TEAM_NEUTRAL};
enum class DcDifficultyGate:uint8{Any,NormalOnly,HeroicOnly};
struct DcDiffKey{bool isRaid=false;uint8 difficulty=0;bool IsHeroic()const{return difficulty>0;}};
NATIVE_DIFFICULTY_MATCH
constexpr uint32 NOT_STARTED=0,IN_PROGRESS=1,FAIL=2,DONE=3,SPECIAL=4;
enum class StepResult:uint8{Running,Done,Blocked,Failed};
#include "DungeonEventRegistry.h"
NATIVE_BOSS_TYPES
NATIVE_ROSTER_PATCH
NATIVE_AUDIT_TYPES
NATIVE_PROGRESS
NATIVE_DRIVE_OUTCOME
namespace Movement{using PointsArray=std::vector<G3D::Vector3>;}
NATIVE_PATH_TYPES
NATIVE_DATA_TYPES
struct InstanceScript
{
    uint32 _encounters[5]{DONE,DONE,DONE,DONE,NOT_STARTED},mask=0;
    NATIVE_INSTANCE_GETDATA
    uint32 GetCompletedEncounterMask()const{return mask;}
};
class Unit;
template<class T>struct Value{using U=std::remove_reference_t<T>;U data{};U& Get(){return data;}void Set(U value){data=value;}};
struct AiObjectContext
{
    bool enabled=true,paused=false,active=true;std::string pauseReason;
    Value<std::string&> reason;Value<DungeonEventProgress&> progress;Value<Unit*> target;
    template<class T>Value<T>* GetValue(char const*){
        if constexpr(std::is_same_v<T,std::string&>)return &reason;else if constexpr(std::is_same_v<T,Unit*>)return &target;else return &progress;}
};
namespace DcRun{inline AiObjectContext& Of(AiObjectContext* ctx){return *ctx;}}
namespace DcKey{constexpr char StallReason[]="dungeon clear stall reason",EventProgress[]="dungeon clear event progress";namespace Stock{constexpr char CurrentTarget[]="current target";}}
class Player;
bool RunFollowerDispatch(Player*,Player*);
struct PlayerbotAI
{
    Player* bot;bool movable=true,allowed=true;AiObjectContext context;
    bool CanMove()const{return movable;}Player* GetBot(){return bot;}
    AiObjectContext* GetAiObjectContext(){return &context;}
};
struct Map{bool water=false;bool IsInWater(uint32,float,float,float,float)const{return water;}};
class Creature;
class Unit
{
public:
    uint32 mapId=43,instanceId=1,phase=1;float x=0,y=0,z=0;
    bool world=true,alive=true,combat=false,los=true,validAttack=true;
    virtual ~Unit()=default;virtual Creature* ToCreature(){return nullptr;}
    uint32 GetMapId()const{return mapId;}uint32 GetInstanceId()const{return instanceId;}
    bool IsInWorld()const{return world;}bool IsAlive()const{return alive;}bool IsInCombat()const{return combat;}
    bool IsInMap(Unit const* other)const{return world&&other->world&&mapId==other->mapId&&instanceId==other->instanceId;}
    bool InSamePhase(Unit const* other)const{return phase&other->phase;}
    float GetPositionX()const{return x;}float GetPositionY()const{return y;}float GetPositionZ()const{return z;}
    float GetExactDist(float px,float py,float pz)const{return G3D::Vector3(px-x,py-y,pz-z).magnitude();}
    float GetExactDist(Unit const* other)const{return GetExactDist(other->x,other->y,other->z);}
    bool IsWithinLOSInMap(Unit const* other)const{return los&&other->los;}
    bool IsValidAttackTarget(Unit const* other)const{return other->validAttack;}
};
struct SmartScript{uint32 path=0;uint32 GetPathId()const{return path;}};
struct CreatureAI{virtual ~CreatureAI()=default;virtual uint32 GetData(uint32)const{return 0;}};
struct SmartAI:CreatureAI
{
    std::map<uint32,uint32> aiDataSet;bool escorted=false;SmartScript script;
    uint32 GetData(uint32)const override;
    bool IsEscorted(){return escorted;}SmartScript* GetScript(){return &script;}
};
class Creature:public Unit
{
public:
    SmartAI smart;CreatureAI otherAI;bool scripted=true,hasAI=true,moving=false,evading=false;uint32 faction=35;
    std::vector<Unit*> attackers;
    Creature* ToCreature()override{return this;}CreatureAI* AI(){return hasAI?(scripted?static_cast<CreatureAI*>(&smart):&otherAI):nullptr;}
    uint32 GetFaction()const{return faction;}bool isMoving()const{return moving;}bool IsInEvadeMode()const{return evading;}
    std::vector<Unit*> const& getAttackers()const{return attackers;}
};
struct Group{struct MemberSlot{uint32 guid;};std::vector<MemberSlot> slots;std::vector<MemberSlot> const& GetMemberSlots()const{return slots;}};
class Player:public Unit
{
public:
    uint32 pathType=PATHFIND_NORMAL,rayType=PATHFIND_NORMAL,stops=0,queries=0,rays=0,launches=0;
    bool ai=true,flight=false,transfer=false,vehicle=false,transport=false;
    bool casting=false,moving=false,loot=false,hasInstance=true,launchAccepted=true;
    int pathSize=3;float startOffset=0,endOffset=0,rayEndOffset=0;
    Creature* disciple=nullptr;Group* group=nullptr;bool session=true,gossipAccepted=true;uint32 gossips=0,melees=0;
    Player* m_mover=this;PlayerbotAI botAI{this};InstanceScript instance;Map map;
    Movement::PointsArray launched;
    bool IsInFlight()const{return flight;}bool IsBeingTeleported()const{return transfer;}
    bool GetVehicle()const{return vehicle;}bool GetTransport()const{return transport;}
    bool IsNonMeleeSpellCast(bool)const{return casting;}bool GetLootGUID()const{return loot;}
    bool isMoving()const{return moving;}uint32 GetPhaseMask()const{return phase;}
    float GetCollisionHeight()const{return 2;}Map const* GetMap()const{return &map;}
    bool SetSwim(bool){return false;}void SendMovementFlagUpdate(){}
    Creature* FindNearestCreature(uint32 entry,float radius,bool living){assert(entry==3678&&radius==250&&living);
        return disciple&&disciple->alive&&IsInMap(disciple)&&InSamePhase(disciple)&&GetExactDist(disciple)<=radius?disciple:nullptr;}
    bool GetSession()const{return session;}Group* GetGroup(){return group;}
    bool HasItemCount(uint32,uint32)const{return false;}
    InstanceScript* GetInstanceScript(){return hasInstance?&instance:nullptr;}
};
#define GET_PLAYERBOT_AI(bot) ((bot)->ai?&(bot)->botAI:nullptr)
struct Config{bool naturalProgression=true;}sPlayerbotAIConfig;
class PathGenerator
{
    Player* bot;bool raycast=false;uint32 type=PATHFIND_BLANK;Movement::PointsArray points;
public:
    explicit PathGenerator(Player* player):bot(player){}
    void SetUseRaycast(bool value){raycast=value;}
    bool CalculatePath(float x,float y,float z,bool force){assert(!force);++bot->queries;
        if(!std::isfinite(x)||!std::isfinite(y)||!std::isfinite(z)||
            !std::isfinite(bot->x)||!std::isfinite(bot->y)||!std::isfinite(bot->z))return false;
        type=bot->pathType;points={{bot->x,bot->y,bot->z+bot->startOffset},{x/2,y/2+3,z/2},{x,y,z+bot->endOffset}};
        if(bot->pathSize<3)points.resize(bot->pathSize);
        return true;}
    bool CalculatePath(float sx,float sy,float sz,float x,float y,float z,bool force){
        assert(raycast&&!force);++bot->rays;
        if(!std::isfinite(sx)||!std::isfinite(sy)||!std::isfinite(sz)||!std::isfinite(x)||!std::isfinite(y)||!std::isfinite(z))return false;
        type=bot->rayType;points={{sx,sy,sz},{x,y,z+bot->rayEndOffset}};return true;}
    uint32 GetPathType()const{return type;}
    Movement::PointsArray const& GetPath()const{return points;}
};
namespace DcMovement
{
    enum class Stop{Hold};
    inline bool DcMovementAllowed(PlayerbotAI* ai){return ai&&ai->allowed&&!ai->context.paused;}
    inline void StopBot(Player* bot,Stop){++bot->stops;bot->moving=false;}
    inline bool SplinePath(PlayerbotAI* ai,Movement::PointsArray& points){++ai->bot->launches;ai->bot->launched=points;
        ai->bot->moving=ai->bot->launchAccepted;return ai->bot->launchAccepted;}
}
struct Creature;
struct DungeonEventExecutor
{
    static bool SelectGossip(Player*,Creature*,int32);
    static EventDriveOutcome Advance(DungeonEvent const&,DungeonEventProgress&,StepResult,uint32,uint32);
    static bool IsPersistentAnchoredEventActive(AiObjectContext* ctx){return ctx->active;}
};
namespace ObjectAccessor{inline std::map<uint32,Player*> players;inline Player* FindConnectedPlayer(uint32 id){auto it=players.find(id);return it==players.end()?nullptr:it->second;}}
namespace DcTargeting{inline Unit* nearby=nullptr;inline Unit* NearestHostileNearPoint(Player*,AiObjectContext*,float,float,float,float,float){return nearby;}}
struct Event{};
struct MeleeAction{PlayerbotAI* ai;explicit MeleeAction(PlayerbotAI* a):ai(a){}bool Execute(Event){assert(ai->context.target.Get());++ai->bot->melees;return true;}};
NATIVE_SMART_GETDATA
bool DungeonEventExecutor::SelectGossip(Player* bot,Creature* disciple,int32 option)
{
    assert(option==0);++bot->gossips;
    if(!bot->gossipAccepted)return false;
    disciple->faction=250;disciple->smart.escorted=true;disciple->smart.script.path=3678;return true;
}
'''


ROUTE_TESTS = r'''
#include "DcWailingCaverns.cpp"
#include <iostream>
using DcWailingCaverns::Walk;
StepResult walk(Player& bot){return Walk(&bot,&bot.botAI.context,10,10,10,2);}
void Routes()
{
    Player bot;
    assert(Walk(nullptr,&bot.botAI.context,10,10,10,2)==StepResult::Failed);
    assert(Walk(&bot,nullptr,10,10,10,2)==StepResult::Failed);
    bot.mapId=1;assert(walk(bot)==StepResult::Failed);bot.mapId=43;
    bot.ai=false;assert(walk(bot)==StepResult::Failed);bot.ai=true;
    for(bool* flag:{&bot.world,&bot.alive,&bot.botAI.movable,&bot.botAI.allowed,&bot.botAI.context.enabled}){
        *flag=false;assert(walk(bot)==StepResult::Running&&!bot.queries&&!bot.launches);*flag=true;}
    for(bool* flag:{&bot.combat,&bot.flight,&bot.transfer,&bot.vehicle,&bot.transport,&bot.casting,&bot.loot,&bot.botAI.context.paused}){
        *flag=true;assert(walk(bot)==StepResult::Running&&!bot.queries&&!bot.launches);*flag=false;}
    AiObjectContext leaderContext;leaderContext.paused=true;
    assert(Walk(&bot,&leaderContext,10,10,10,2)==StepResult::Running&&!bot.queries&&!bot.launches);
    Player other;bot.m_mover=&other;assert(walk(bot)==StepResult::Running&&!bot.queries);bot.m_mover=&bot;
    float const nan=std::numeric_limits<float>::quiet_NaN();
    for(auto target:{G3D::Vector3(nan,10,10),G3D::Vector3(10,nan,10),G3D::Vector3(10,10,nan)})
        assert(Walk(&bot,&bot.botAI.context,target.x,target.y,target.z,2)==StepResult::Failed&&!bot.queries);
    Player invalidStart;invalidStart.x=nan;assert(walk(invalidStart)==StepResult::Failed&&!invalidStart.launches);
    for(float radius:{0.f,-1.f,nan})assert(Walk(&bot,&bot.botAI.context,10,10,10,radius)==StepResult::Failed&&!bot.queries);
    bot.x=10;bot.y=10;bot.z=10;
    assert(walk(bot)==StepResult::Done&&bot.stops==1&&!bot.queries);bot.z=16;
    assert(walk(bot)==StepResult::Running&&bot.queries==1&&bot.launches==1);
    assert(bot.launched.size()==3&&bot.launched.front().z==16&&bot.launched[1].y==8);
    // Issuing a spline is never arrival. A combat/loot interruption resumes
    // from the real current position and revalidates every actual segment.
    assert(bot.x==10&&bot.z==16);uint32 queries=bot.queries;
    assert(walk(bot)==StepResult::Running&&bot.queries==queries);
    bot.moving=false;bot.x=9;bot.y=8;bot.z=6;bot.startOffset=3;
    assert(walk(bot)==StepResult::Running&&bot.launched.front().x==9&&bot.launched.front().z==6&&bot.queries==queries+1);
    bot=Player();bot.botAI.bot=&bot;bot.m_mover=&bot;bot.pathType=PATHFIND_NOPATH;
    assert(walk(bot)==StepResult::Failed&&!bot.launches&&!bot.botAI.context.reason.Get().empty());
    for(uint32 type:{uint32(PATHFIND_BLANK),uint32(PATHFIND_INCOMPLETE),uint32(PATHFIND_SHORT),
        uint32(PATHFIND_NORMAL|PATHFIND_SHORTCUT),uint32(PATHFIND_NORMAL|PATHFIND_NOPATH),
        uint32(PATHFIND_NORMAL|PATHFIND_NOT_USING_PATH),uint32(PATHFIND_NORMAL|PATHFIND_FARFROMPOLY),
        uint32(PATHFIND_NORMAL|PATHFIND_INCOMPLETE),uint32(PATHFIND_NORMAL|PATHFIND_SHORT)}){
        Player invalid;invalid.pathType=type;assert(walk(invalid)==StepResult::Failed&&!invalid.launches);}
    for(int size:{0,1}){Player invalid;invalid.pathSize=size;assert(walk(invalid)==StepResult::Failed&&!invalid.launches);}
    for(float offset:{1.01f,5.6f,-75.f}){Player invalid;invalid.endOffset=offset;assert(walk(invalid)==StepResult::Failed&&!invalid.launches);}
    Player refused;refused.launchAccepted=false;
    assert(walk(refused)==StepResult::Running&&refused.launches==1&&!refused.moving&&refused.x==0&&refused.z==0);
    Player close;close.endOffset=.99f;assert(walk(close)==StepResult::Running&&close.launches==1);
    Player ray;ray.rayType=PATHFIND_NOPATH;assert(walk(ray)==StepResult::Failed&&!ray.launches);
    ray.rayType=PATHFIND_NORMAL;ray.rayEndOffset=.051f;assert(walk(ray)==StepResult::Failed&&!ray.launches);
    ray.rayEndOffset=0;ray.rayType=PATHFIND_NORMAL|PATHFIND_INCOMPLETE;assert(walk(ray)==StepResult::Failed&&!ray.launches);
    ray.rayType=PATHFIND_NORMAL;assert(walk(ray)==StepResult::Running&&ray.launches==1&&ray.rays>=4);
    std::cout<<"WC routes: complete paths, correct floor, raycast segments, live-position revalidation and interruptions verified\n";
}
'''


ESCORT_TESTS = r'''
#include "DcNaralexEscort.cpp"
using DcNaralexEscort::Run;
void ready(Player& bot,Creature& disciple)
{
    bot.disciple=&disciple;bot.botAI.context.progress.Get().eventId=2;
    bot.botAI.context.progress.Get().instanceId=bot.instanceId;
}
void start(Player& bot,Creature& disciple)
{
    ready(bot,disciple);assert(Run(&bot,&bot.botAI.context)==StepResult::Running);
    assert(bot.gossips==1&&disciple.faction==250&&disciple.smart.escorted&&disciple.smart.script.path==3678);
}
void Escorts()
{
    Player bot;Creature disciple;ready(bot,disciple);AiObjectContext& ctx=bot.botAI.context;
    assert(Run(nullptr,&ctx)==StepResult::Failed);bot.mapId=1;assert(Run(&bot,&ctx)==StepResult::Failed);bot.mapId=43;
    bot.world=false;assert(Run(&bot,&ctx)==StepResult::Failed);bot.world=true;
    bot.ai=false;assert(Run(&bot,&ctx)==StepResult::Failed);bot.ai=true;
    assert(Run(&bot,nullptr)==StepResult::Running&&!bot.gossips);
    for(bool* flag:{&ctx.enabled,&ctx.active}){*flag=false;assert(Run(&bot,&ctx)==StepResult::Running&&!bot.gossips&&!bot.queries);*flag=true;}
    ctx.paused=true;assert(Run(&bot,&ctx)==StepResult::Running&&!bot.gossips&&!bot.queries);ctx.paused=false;
    ctx.progress.Get().eventId=3;assert(Run(&bot,&ctx)==StepResult::Running&&!bot.gossips);ctx.progress.Get().eventId=2;
    bot.hasInstance=false;assert(Run(&bot,&ctx)==StepResult::Blocked);bot.hasInstance=true;
    assert(bot.instance.GetData(4)==NOT_STARTED);
    for(uint32 type=0;type<4;++type)for(uint32 state:{NOT_STARTED,IN_PROGRESS,FAIL,SPECIAL}){
        bot.instance._encounters[type]=state;assert(Run(&bot,&ctx)==StepResult::Blocked&&!bot.gossips);bot.instance._encounters[type]=DONE;}
    bot.disciple=nullptr;assert(Run(&bot,&ctx)==StepResult::Blocked);bot.disciple=&disciple;
    for(bool* flag:{&disciple.world,&disciple.alive,&disciple.scripted,&disciple.hasAI}){
        *flag=false;assert(Run(&bot,&ctx)==StepResult::Blocked&&!bot.gossips);*flag=true;}
    disciple.mapId=1;assert(Run(&bot,&ctx)==StepResult::Blocked);disciple.mapId=43;
    disciple.instanceId=2;assert(Run(&bot,&ctx)==StepResult::Blocked);disciple.instanceId=1;
    disciple.phase=2;assert(Run(&bot,&ctx)==StepResult::Blocked);disciple.phase=1;
    bot.alive=false;assert(Run(&bot,&ctx)==StepResult::Running&&!bot.gossips);bot.alive=true;
    for(bool* flag:{&bot.combat,&bot.flight,&bot.transfer,&bot.vehicle,&bot.transport,&bot.casting,&bot.loot}){
        *flag=true;assert(Run(&bot,&ctx)==StepResult::Running&&!bot.gossips&&!bot.queries);*flag=false;}
    Player mover;bot.m_mover=&mover;assert(Run(&bot,&ctx)==StepResult::Running&&!bot.gossips);bot.m_mover=&bot;
    disciple.faction=250;assert(Run(&bot,&ctx)==StepResult::Blocked&&!bot.gossips);disciple.faction=35;
    disciple.moving=true;assert(Run(&bot,&ctx)==StepResult::Blocked&&!bot.gossips);disciple.moving=false;
    bot.session=false;assert(Run(&bot,&ctx)==StepResult::Blocked&&!bot.gossips);bot.session=true;
    bot.los=false;assert(Run(&bot,&ctx)==StepResult::Blocked&&!bot.gossips);bot.los=true;
    // Initial approach uses the same fully checked ground route as WC traversal.
    disciple.x=20;assert(Run(&bot,&ctx)==StepResult::Running&&bot.launches==1&&!bot.gossips);
    bot.moving=false;bot.pathType=PATHFIND_NOPATH;assert(Run(&bot,&ctx)==StepResult::Failed&&!bot.gossips);
    bot.pathType=PATHFIND_NORMAL;disciple.x=0;
    bot.gossipAccepted=false;assert(Run(&bot,&ctx)==StepResult::Blocked&&bot.gossips==1&&!disciple.smart.escorted);
    bot.gossipAccepted=true;assert(Run(&bot,&ctx)==StepResult::Running&&bot.gossips==2);
    assert(disciple.smart.escorted&&disciple.smart.script.path==3678&&disciple.faction==250);
    uint32 const clicks=bot.gossips;
    assert(Run(&bot,&ctx)==StepResult::Running&&bot.gossips==clicks);
    disciple.smart.script.path=999;assert(Run(&bot,&ctx)==StepResult::Blocked);disciple.smart.script.path=3678;
    disciple.faction=35;assert(Run(&bot,&ctx)==StepResult::Blocked);disciple.faction=250;
    // A spawn, a dead boss or a kill bit does not finish the dialogue or ritual.
    bot.instance.mask=1u<<7;assert(Run(&bot,&ctx)==StepResult::Running);
    disciple.smart.aiDataSet[2]=1;assert(Run(&bot,&ctx)==StepResult::Running);
    disciple.smart.aiDataSet[2]=2;assert(Run(&bot,&ctx)==StepResult::Running);
    disciple.smart.script.path=3679;bot.instance.mask=1u<<6;assert(Run(&bot,&ctx)==StepResult::Blocked);
    bot.instance.mask=1u<<7;assert(Run(&bot,&ctx)==StepResult::Done);
    disciple.smart.aiDataSet.clear();assert(Run(&bot,&ctx)==StepResult::Blocked);
    bot.disciple=nullptr;assert(Run(&bot,&ctx)==StepResult::Blocked); // Native despawn without an observed marker is no success.
    // Native respawn clears SmartAI data and path. Restart only through gossip.
    Creature respawn;bot.disciple=&respawn;bot.instance.mask=0;
    assert(Run(&bot,&ctx)==StepResult::Running&&bot.gossips==clicks+1&&respawn.smart.GetData(2)==0);
    std::cout<<"Naralex: earned prerequisites, native gossip receipt, script reset, final dialogue and queued interruptions verified\n";
}
void GroupsAndFollowers()
{
    Player leader,member;Creature disciple;ready(leader,disciple);Group group;group.slots={{1},{2}};
    leader.group=&group;member.disciple=&disciple;ObjectAccessor::players={{1,&leader}};
    auto run=[&]{return Run(&leader,&leader.botAI.context);};
    assert(run()==StepResult::Running&&!leader.gossips);ObjectAccessor::players[2]=&member;
    member.world=false;assert(run()==StepResult::Running&&!leader.gossips);member.world=true;
    member.mapId=1;assert(run()==StepResult::Running&&!leader.gossips);member.mapId=43;
    member.instanceId=2;assert(run()==StepResult::Running&&!leader.gossips);member.instanceId=1;
    member.phase=2;assert(run()==StepResult::Running&&!leader.gossips);member.phase=1;
    member.alive=false;assert(run()==StepResult::Running&&!leader.gossips);member.alive=true;
    for(bool* flag:{&member.combat,&member.flight,&member.transfer,&member.vehicle,&member.transport,&member.casting,&member.loot}){
        *flag=true;assert(run()==StepResult::Running&&!leader.gossips);*flag=false;}
    member.los=false;assert(run()==StepResult::Running&&!leader.gossips);member.los=true;
    member.x=16;assert(run()==StepResult::Running&&!leader.gossips);
    assert(RunFollowerDispatch(&member,&leader)&&member.launches==1&&!leader.gossips&&member.x==16);
    member.moving=false;member.x=8;assert(run()==StepResult::Running&&leader.gossips==1);
    auto const queries=member.queries;disciple.smart.aiDataSet[2]=2;
    assert(DcNaralexEscort::Follow(&member,&leader)&&member.queries==queries);
    disciple.smart.aiDataSet.clear();member.x=20;member.moving=false;member.pathType=PATHFIND_NOPATH;
    uint32 const stops=leader.stops;
    assert(DcNaralexEscort::Follow(&member,&leader)&&leader.botAI.context.paused&&leader.stops==stops+1);
    assert(leader.botAI.context.pauseReason.starts_with("No real navigation-mesh route")&&
        leader.botAI.context.reason.Get()==leader.botAI.context.pauseReason);
    leader.botAI.context.paused=false;member.pathType=PATHFIND_NORMAL;member.disciple=nullptr;
    assert(DcNaralexEscort::Follow(&member,&leader)&&member.queries==queries+1);
    for(bool* flag:{&member.world,&leader.botAI.context.enabled,&leader.botAI.context.active,&leader.ai}){
        *flag=false;assert(!DcNaralexEscort::Follow(&member,&leader));*flag=true;}
    leader.botAI.context.paused=true;assert(!DcNaralexEscort::Follow(&member,&leader));leader.botAI.context.paused=false;
    leader.botAI.context.progress.Get().eventId=3;assert(!DcNaralexEscort::Follow(&member,&leader));leader.botAI.context.progress.Get().eventId=2;
    member.phase=2;assert(!DcNaralexEscort::Follow(&member,&leader));member.phase=1;
    member.mapId=1;assert(!DcNaralexEscort::Follow(&member,&leader));member.mapId=43;
    leader.mapId=1;assert(!DcNaralexEscort::Follow(&member,&leader));leader.mapId=43;
    sPlayerbotAIConfig.naturalProgression=false;assert(DcNaralexEscort::Follow(&member,&leader));sPlayerbotAIConfig.naturalProgression=true;
    assert(!DcNaralexEscort::Follow(nullptr,&leader)&&!DcNaralexEscort::Follow(&member,nullptr));
    ObjectAccessor::players.clear();
}
void Protection()
{
    Player bot;Creature disciple,enemy;start(bot,disciple);AiObjectContext& ctx=bot.botAI.context;
    disciple.attackers={nullptr,&enemy};enemy.x=1;enemy.y=1;
    auto run=[&]{return Run(&bot,&ctx);};
    assert(run()==StepResult::Running&&bot.melees==1&&ctx.target.Get()==&enemy);
    uint32 melees=bot.melees;
    for(bool* flag:{&enemy.world,&enemy.alive,&enemy.validAttack}){*flag=false;assert(run()==StepResult::Running&&bot.melees==melees);*flag=true;}
    enemy.mapId=1;assert(run()==StepResult::Running&&bot.melees==melees);enemy.mapId=43;
    enemy.phase=2;assert(run()==StepResult::Running&&bot.melees==melees);enemy.phase=1;
    enemy.evading=true;assert(run()==StepResult::Running&&bot.melees==melees);enemy.evading=false;
    enemy.los=false;assert(run()==StepResult::Blocked&&bot.melees==melees);enemy.los=true;
    bot.combat=true;assert(run()==StepResult::Running&&bot.melees==melees);bot.combat=false;
    enemy.x=10;assert(run()==StepResult::Running&&bot.launches==1&&bot.melees==melees);
    bot.moving=false;bot.pathType=PATHFIND_NOPATH;assert(run()==StepResult::Failed&&bot.melees==melees);bot.pathType=PATHFIND_NORMAL;
    // The nearby-target producer excludes bosses and impossible targets. The
    // native selector contract is asserted in Python; its result remains subject
    // to the same real route and ordinary melee action as an actual attacker.
    disciple.attackers.clear();enemy.x=1;DcTargeting::nearby=&enemy;
    assert(run()==StepResult::Running&&bot.melees==melees+1);
    DcTargeting::nearby=nullptr;
}
'''


def authored_sources(source):
    registry = source / 'Ai/Dungeon/DungeonClear/Data/DungeonEventRegistry.h'
    builder = registry.with_suffix('.cpp').read_text()
    output = ['#include "DungeonEventRegistry.h"', '#include <utility>']
    for signature in ('EventBuilder::EventBuilder(', 'EventStep& EventBuilder::Add(',
                      'EventBuilder& EventBuilder::Anchored(', 'EventBuilder& EventBuilder::Persistent(',
                      'EventBuilder& EventBuilder::StepsOwnMovement(', 'EventBuilder& EventBuilder::MoveTo(',
                      'EventBuilder& EventBuilder::Timeout(', 'EventBuilder& EventBuilder::EscortCreature(',
                      'DungeonEvent EventBuilder::Build('):
        output.append(function(builder, signature))
    events = (source / 'Ai/Dungeon/DungeonClear/Data/Events/WailingCavernsEvents.cpp').read_text()
    output.append(function(events, 'void RegisterWailingCavernsEvents('))
    roster = (source / 'Ai/Dungeon/DungeonClear/Overrides/BossRosterRegistry.cpp').read_text()
    builders = (source / 'Ai/Dungeon/DungeonClear/Data/Events/DungeonRosterBuilders.h').read_text()
    roster_header = (source / 'Ai/Dungeon/DungeonClear/Overrides/BossRosterRegistry.h').read_text()
    output.append('namespace DcRoster {')
    for signature in ('inline constexpr uint32 OBJ(', 'inline DungeonBossInfo MakeBoss(', 'inline DungeonBossInfo MakeObjective('):
        output.append(function(builders, signature))
    output.append('}')
    output.append(function(events, 'void RegisterWailingCavernsRoster('))
    output.append('std::vector<BossRosterPatch> const& PatchTable(){static std::vector<BossRosterPatch> p;'
                  'if(p.empty())RegisterWailingCavernsRoster(p);return p;}')
    output.append(function(roster, 'std::vector<DungeonBossInfo> ApplyOne('))
    output.append(function(roster, 'std::vector<DungeonBossInfo> BossRosterRegistry::Apply('))
    assert function(roster_header, 'static constexpr uint32 ObjectiveEntry(') in STUB_AUDIT_TYPES
    executor = (source / 'Ai/Dungeon/DungeonClear/Util/DungeonEventExecutor.cpp').read_text()
    output += [re.search(r'constexpr uint32 DC_EVENT_NO_PROGRESS_FACTOR\s*=\s*\d+;', executor).group(),
               function(executor, 'EventDriveOutcome DungeonEventExecutor::Advance(')]
    for name, kind, dispatch in (
        ('RunAuthoredWalk', 'MoveTo', 'return DcWailingCaverns::RunLeg(bot, context, step);'),
        ('RunAuthoredEscort', 'EscortCreature', 'return DcNaralexEscort::Run(bot, context);'),
    ):
        case = executor.split(f'case EventStepKind::{kind}:', 1)[1]
        first = case.index('if (bot->GetMapId()')
        last = case.index(dispatch) + len(dispatch)
        output.append(f'StepResult {name}(Player* bot,AiObjectContext* context,EventStep const& step){{' +
                      case[first:last] + '\nreturn StepResult::Failed;}')
    engage = (source / 'Ai/Dungeon/DungeonClear/Action/DcEngageActions.cpp').read_text()
    legacy = re.search(r'else if \((step\.kind == EventStepKind::EscortCreature.*?)\)\s*\{\s*if \(DriveEscortCreature\(',
                       engage, re.DOTALL).group(1)
    output.append('bool UsesLegacyEscort(EventStep const& step){return ' + legacy + ';}')
    follower = (source / 'Ai/Dungeon/DungeonClear/Action/DcFollowerActions.cpp').read_text()
    dispatch = re.search(r'if \((DcWailingCaverns::FollowRoute\(bot, tank\).*?)\)\s*\{\s*followedTank',
                         follower, re.DOTALL).group(1)
    # The Ring helper cannot own a follower on map 43; its native map guard is
    # asserted above so the dispatcher double cannot mask a missing WC driver.
    output.append('namespace DcRingOfLaw{bool Follow(Player*,Player* tank){assert(tank->GetMapId()==43);return false;}}')
    output.append('bool RunFollowerDispatch(Player* bot,Player* tank){return ' + dispatch + ';}')
    header = (source / 'Ai/Dungeon/DungeonClear/Util/DungeonEventExecutor.h').read_text()
    return registry, '\n'.join(output), header


AUTHORED_TESTS = r'''
#include "DcEarnedEvents.cpp"
#include "AuthoredWC.cpp"
void RouteGroups()
{
    authoredEvents.clear();RegisterWailingCavernsEvents(authoredEvents);
    Player leader,member;Group group;group.slots={{1},{2}};leader.group=&group;
    ObjectAccessor::players={{1,&leader}};
    auto& ctx=leader.botAI.context;ctx.progress.Get().instanceId=1;
    EventStep const& step=authoredEvents[0].steps[0];ctx.progress.Get().eventId=1;
    leader.x=step.x;leader.y=step.y;leader.z=step.z;
    auto run=[&]{return DcWailingCaverns::RunLeg(&leader,&ctx,step);};
    assert(run()==StepResult::Running);
    ObjectAccessor::players[2]=&member;member.x=step.x;member.y=step.y;member.z=step.z;
    assert(run()==StepResult::Done);
    for(bool* flag:{&member.world,&member.alive}){*flag=false;assert(run()==StepResult::Running);*flag=true;}
    for(bool* flag:{&member.combat,&member.flight,&member.transfer,&member.casting,&member.loot,&member.vehicle,&member.transport}){
        *flag=true;assert(run()==StepResult::Running);*flag=false;}
    member.m_mover=&leader;assert(run()==StepResult::Running);member.m_mover=&member;
    member.mapId=1;assert(run()==StepResult::Running);member.mapId=43;
    member.instanceId=2;assert(run()==StepResult::Running);member.instanceId=1;
    member.phase=2;assert(run()==StepResult::Running);member.phase=1;
    member.z=step.z+5.6f;assert(run()==StepResult::Running);member.z=step.z;
    member.x=step.x+3;assert(run()==StepResult::Running);
    assert(RunFollowerDispatch(&member,&leader)&&member.launches==1&&member.x==step.x+3);
    member.moving=false;member.x=step.x;assert(run()==StepResult::Done);
    // Every authored prefix, including the escort's initial gather, uses the
    // same checkpoint driver. Only the actual escort step changes follower mode.
    for(uint32 id:{1u,2u,3u}){
        ctx.progress.Get().eventId=id;ctx.progress.Get().stepIndex=0;member.moving=false;
        assert(DcWailingCaverns::FollowRoute(&member,&leader));}
    ctx.progress.Get().eventId=2;ctx.progress.Get().stepIndex=1;
    assert(!DcWailingCaverns::FollowRoute(&member,&leader));
    Creature disciple;member.disciple=&disciple;member.moving=false;
    uint32 const queries=member.queries;
    assert(RunFollowerDispatch(&member,&leader)&&member.queries==queries+1);
    member.disciple=nullptr;
    ctx.progress.Get().stepIndex=999;assert(!DcWailingCaverns::FollowRoute(&member,&leader));
    ctx.progress.Get().stepIndex=0;ctx.progress.Get().eventId=999;
    assert(!DcWailingCaverns::FollowRoute(&member,&leader));ctx.progress.Get().eventId=1;
    for(bool* flag:{&member.world,&ctx.enabled,&ctx.active,&leader.ai}){
        *flag=false;assert(!DcWailingCaverns::FollowRoute(&member,&leader));*flag=true;}
    ctx.paused=true;assert(!DcWailingCaverns::FollowRoute(&member,&leader));ctx.paused=false;
    member.phase=2;assert(!DcWailingCaverns::FollowRoute(&member,&leader));member.phase=1;
    member.mapId=1;assert(!DcWailingCaverns::FollowRoute(&member,&leader));
    leader.mapId=1;assert(!DcWailingCaverns::FollowRoute(&member,&leader));member.mapId=leader.mapId=43;
    assert(!DcWailingCaverns::FollowRoute(nullptr,&leader)&&!DcWailingCaverns::FollowRoute(&member,nullptr));
    auto saved=authoredEvents;authoredEvents.clear();assert(!DcWailingCaverns::FollowRoute(&member,&leader));authoredEvents=saved;
    member.x=0;member.y=0;member.z=0;member.moving=false;member.pathType=PATHFIND_NOPATH;
    uint32 const stops=leader.stops;
    assert(DcWailingCaverns::FollowRoute(&member,&leader)&&ctx.paused&&leader.stops==stops+1&&!member.moving);
    assert(ctx.pauseReason.starts_with("No real navigation-mesh route")&&ctx.reason.Get()==ctx.pauseReason);
    ObjectAccessor::players.clear();
    std::cout<<"WC party routes: exact checkpoints, all members, escort handoff and unreachable follower abort verified\n";
}

void Authored()
{
    std::vector<DungeonEvent> events;RegisterWailingCavernsEvents(events);assert(events.size()==3);
    authoredEvents=events;
    auto const roster=BossRosterRegistry::Apply(43,DcDiffKey{},{});assert(roster.size()==4);
    assert(roster[0].eventId==1&&roster[0].encounterIndex==5&&roster[0].x==-206.648f&&roster[0].z==-49.4123f);
    assert(roster[1].eventId==3&&roster[1].x==-81.8554f&&roster[1].z==-30.9939f);
    assert(roster[2].eventId==2&&roster[2].x==-134.97f&&roster[2].z==-78.09f);
    assert(roster[3].entry==3654&&roster[3].encounterIndex==7&&roster[3].kind==DungeonAnchorKind::Boss);
    for(auto const& anchor:roster)assert(!anchor.gateEntry&&!anchor.onArriveHook&&!anchor.skipByDesign);
    std::string reason;assert(DcEarnedEvents::MapAudited(43,reason)&&reason.empty());
    std::vector<G3D::Vector3> ramp{{-206.648f,58.6654f,-49.4123f},{-187.331f,56.9268f,-49.9537f},
        {-169.269f,54.0309f,-40.636f},{-147.96f,31.9855f,-29.7619f}};
    for(auto const& event:events){
        assert(event.mapId==43&&event.required&&event.persistent&&event.stepsOwnMovement);
        assert(event.activation==EventActivation::Anchored);
        assert(event.steps.size()==(event.id==2?2:5));
        for(auto const& step:event.steps){
            assert(step.kind==EventStepKind::MoveTo||step.kind==EventStepKind::EscortCreature);
            DungeonEvent one=event;one.steps={step};DungeonEventProgress progress;
            uint32 const budget=step.kind==EventStepKind::MoveTo?120000:900000;
            assert(step.timeoutMs==budget);
            assert(DungeonEventExecutor::Advance(one,progress,StepResult::Running,budget-1,30000)==EventDriveOutcome::Running);
            DungeonEventProgress expired=progress;
            assert(DungeonEventExecutor::Advance(one,expired,StepResult::Running,budget,30000)==EventDriveOutcome::Stalled);
            assert(DungeonEventExecutor::Advance(one,progress,StepResult::Blocked,1,30000)==EventDriveOutcome::Stalled);
            if(step.kind==EventStepKind::MoveTo){
                Player bot;assert(RunAuthoredWalk(&bot,&bot.botAI.context,step)==StepResult::Running&&bot.launches==1);
                assert(step.radius==2);bot.moving=false;bot.x=step.x;bot.y=step.y;bot.z=step.z;
                assert(RunAuthoredWalk(&bot,&bot.botAI.context,step)==StepResult::Done);
            }else{
                assert(DcEarnedEvents::IsNaralexStep(step));Player bot;Creature disciple;ready(bot,disciple);
                for(bool natural:{false,true}){
                    sPlayerbotAIConfig.naturalProgression=natural;
                    assert(!UsesLegacyEscort(step));
                    EventStep other=step;other.creatureEntry=1;
                    assert(UsesLegacyEscort(other)==!natural);
                }
                assert(RunAuthoredEscort(&bot,&bot.botAI.context,step)==StepResult::Running&&bot.gossips==1);
                bot.instance.mask=1u<<7;disciple.smart.aiDataSet[2]=2;disciple.smart.script.path=3679;
                assert(RunAuthoredEscort(&bot,&bot.botAI.context,step)==StepResult::Done);
            }
        }
        if(event.id!=2){
            assert(event.orderIndex==(event.id==1?5:7));
            for(size_t i=0;i<4;++i){auto const& point=ramp[event.id==1?i:3-i];auto const& step=event.steps[i];
                assert(step.x==point.x&&step.y==point.y&&step.z==point.z);}
        }
        auto const& last=event.steps.back();
        if(event.id==1)assert(last.x==-120.163f&&last.y==-24.624f&&last.z==-28.5832f);
        if(event.id==3)assert(last.x==-134.97f&&last.y==125.40f&&last.z==-78.09f);
    }
    std::cout<<"WC authored events: native ramp in both directions, ordinary dispatch and finite required-step failures verified\n";
}
int main(){Routes();Escorts();GroupsAndFollowers();Protection();Authored();RouteGroups();}
'''


def main():
    parser = argparse.ArgumentParser()
    source_argument(parser)
    args = parser.parse_args()
    core = prepared_core()
    source = args.source or core / 'modules/mod-dungeon-clear/src'
    native_get, native_read, native_enum, _route = native_contracts(core, source)
    registry, authored, executor_header = authored_sources(source)
    paths = (core / 'src/server/game/Movement/MovementGenerators/PathGenerator.h').read_text()
    generated = STUBS.replace('NATIVE_SMART_GETDATA', native_get).replace('NATIVE_INSTANCE_GETDATA', native_read.replace(' override', ''))
    generated = generated.replace('NATIVE_DATA_TYPES', native_enum).replace('NATIVE_PATH_TYPES', function(paths, 'enum PathType') + ';')
    generated = generated.replace('NATIVE_PROGRESS', function(executor_header, 'struct DungeonEventProgress') + ';')
    generated = generated.replace('NATIVE_DRIVE_OUTCOME', function(executor_header, 'enum class EventDriveOutcome') + ';')
    boss = (source / 'Ai/Dungeon/DungeonClear/Data/DungeonBossInfo.h').read_text()
    generated = generated.replace('NATIVE_BOSS_TYPES', function(boss, 'enum class DungeonAnchorKind') + ';' +
                                  function(boss, 'struct DcSpawnPoint') + ';' + function(boss, 'struct DungeonBossInfo') + ';' +
                                  function(boss, 'inline uint32 BossOrderKey('))
    roster_header = (source / 'Ai/Dungeon/DungeonClear/Overrides/BossRosterRegistry.h').read_text()
    generated = generated.replace('NATIVE_ROSTER_PATCH', function(roster_header, 'struct BossRosterPatch') + ';')
    gate = (source / 'Ai/Dungeon/DungeonClear/Data/DcDifficultyGate.h').read_text()
    generated = generated.replace('NATIVE_DIFFICULTY_MATCH', function(gate, 'inline bool DcGateMatches('))
    shared = (core / 'src/server/shared/SharedDefines.h').read_text()
    constants = ('LOCK_KEY_ITEM', 'LOCK_KEY_SKILL', 'LOCKTYPE_OPEN', 'GO_FLAG_LOCKED', 'GO_FLAG_INTERACT_COND', 'GO_FLAG_NOT_SELECTABLE')
    values = '\n'.join('constexpr uint32 ' + name + '=' + re.search(name + r'\s*=\s*(0x[0-9A-Fa-f]+|\d+)', shared).group(1) + ';' for name in constants)
    generated = generated.replace('NATIVE_AUDIT_TYPES', values + STUB_AUDIT_TYPES)
    compiler = cxx()
    with tempfile.TemporaryDirectory(prefix='wailing-caverns-') as temp:
        work = Path(temp)
        (work / 'NativeStubs.h').write_text(generated)
        for name in ('Common.h', 'SharedDefines.h', 'Define.h', 'Map.h', 'PlayerbotAIConfig.h', 'PathGenerator.h',
                     'Player.h', 'Playerbots.h', 'AiObjectContext.h', 'Creature.h', 'Event.h', 'Group.h',
                     'InstanceScript.h', 'ObjectAccessor.h', 'SmartAI.h', 'AttackAction.h', 'DBCStores.h', 'GameObject.h', 'ObjectMgr.h',
                     'Ai/Dungeon/DungeonClear/Data/BossSpawnIndex.h', 'Ai/Dungeon/DungeonClear/Data/DungeonEventRegistry.h',
                     'Ai/Dungeon/DungeonClear/Overrides/BossRosterRegistry.h', 'Ai/Dungeon/DungeonClear/Util/DcDifficulty.h',
                     'Ai/Dungeon/DungeonClear/Data/DcDifficultyGate.h', 'Ai/Dungeon/DungeonClear/DcValueKeys.h',
                     'Ai/Dungeon/DungeonClear/Util/DcMovement.h', 'Ai/Dungeon/DungeonClear/Util/DcRun.h',
                     'Ai/Dungeon/DungeonClear/Util/DcTargeting.h', 'Ai/Dungeon/DungeonClear/Util/DungeonEventExecutor.h'):
            path = work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('#include "NativeStubs.h"\n')
        for name in ('DcWailingCaverns.cpp', 'DcWailingCaverns.h', 'DcNaralexEscort.cpp', 'DcNaralexEscort.h', 'DcEarnedPlay.h', 'DcEarnedEvents.cpp', 'DcEarnedEvents.h'):
            shutil.copyfile(source / name, work / name)
        shutil.copyfile(registry, work / 'DungeonEventRegistry.h')
        (work / 'AuthoredWC.cpp').write_text(authored)
        (work / 'fixture.cpp').write_text(ROUTE_TESTS + ESCORT_TESTS + AUTHORED_TESTS)
        exe = work / ('fixture.exe' if os.name == 'nt' else 'fixture')
        g3d_include = str(core / 'deps/g3dlite/include')
        flags = ['-std=c++20', '-O1', '-Wall', '-Wextra', '-Wno-missing-field-initializers',
                 '-I', str(work), '-I', g3d_include]
        if os.name != 'nt':
            flags += [*SANITIZER_FLAGS, '-no-pie']
        subprocess.run([compiler, *flags, str(work / 'fixture.cpp'), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=TIMEOUT)
        mutations = [
            ('wrong map movement', 'DcWailingCaverns.cpp', 'bot->GetMapId() != 43', 'false'),
            ('missing movement AI', 'DcWailingCaverns.cpp', '!GET_PLAYERBOT_AI(bot)', 'false'),
            ('cancelled movement', 'DcWailingCaverns.cpp', '!DcRun::Of(context).enabled', 'false'),
            ('paused movement', 'DcWailingCaverns.cpp', 'DcRun::Of(context).paused)', 'false)'),
            ('dead movement', 'DcWailingCaverns.cpp', '!bot->IsAlive()', 'false'),
            ('world readiness movement', 'DcWailingCaverns.cpp', '!bot->IsInWorld()', 'false'),
            ('combat movement', 'DcWailingCaverns.cpp', 'bot->IsInCombat()', 'false'),
            ('flight movement', 'DcWailingCaverns.cpp', 'bot->IsInFlight()', 'false'),
            ('pending transfer movement', 'DcWailingCaverns.cpp', 'bot->IsBeingTeleported()', 'false'),
            ('remote movement', 'DcWailingCaverns.cpp', 'bot->m_mover != bot', 'false'),
            ('vehicle movement', 'DcWailingCaverns.cpp', 'bot->GetVehicle()', 'false'),
            ('transport movement', 'DcWailingCaverns.cpp', 'bot->GetTransport()', 'false'),
            ('casting movement', 'DcWailingCaverns.cpp', 'bot->IsNonMeleeSpellCast(false)', 'false'),
            ('looting movement', 'DcWailingCaverns.cpp', 'bot->GetLootGUID()', 'false'),
            ('controlled movement', 'DcWailingCaverns.cpp', '!ai->CanMove()', 'false'),
            ('paused issuance', 'DcWailingCaverns.cpp', '!DcMovement::DcMovementAllowed(ai)', 'false'),
            ('native path status', 'DcWailingCaverns.cpp', '!DcEarnedPlay::UsesRealPath(path)', 'false'),
            ('partial path', 'DcWailingCaverns.cpp', '(path.GetPathType() & (PATHFIND_INCOMPLETE | PATHFIND_SHORT))', 'false'),
            ('wrong endpoint floor', 'DcWailingCaverns.cpp', '(path.GetPath().back() - G3D::Vector3(x, y, z)).magnitude() > 1.0f', 'false'),
            ('unsafe actual spline', 'DcWailingCaverns.cpp', '!DcEarnedPlay::RealSpline(bot, points)', 'false'),
            ('stale starting position', 'DcWailingCaverns.cpp', 'points.front() = G3D::Vector3(bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ());', '(void)0;'),
            ('restart in flight spline', 'DcWailingCaverns.cpp', 'if (bot->isMoving())', 'if (false)'),
            ('movement not issued', 'DcWailingCaverns.cpp', 'DcMovement::SplinePath(ai, points);', '(void)0;'),
            ('movement reports arrival', 'DcWailingCaverns.cpp', 'DcMovement::SplinePath(ai, points);\n        return StepResult::Running;', 'DcMovement::SplinePath(ai, points);\n        return StepResult::Done;'),
            ('checkpoint group gate', 'DcWailingCaverns.cpp', 'if (Group* group = bot->GetGroup())', 'if (Group* group = nullptr)'),
            ('checkpoint native map', 'DcWailingCaverns.cpp', '!member->IsInMap(bot)', 'false'),
            ('checkpoint phase', 'DcWailingCaverns.cpp', '!member->InSamePhase(bot)', 'false'),
            ('checkpoint death', 'DcWailingCaverns.cpp', '!member->IsAlive()', 'false'),
            ('checkpoint combat', 'DcWailingCaverns.cpp', 'member->IsInCombat()', 'false'),
            ('checkpoint flight', 'DcWailingCaverns.cpp', 'member->IsInFlight()', 'false'),
            ('checkpoint pending transfer', 'DcWailingCaverns.cpp', 'member->IsBeingTeleported()', 'false'),
            ('checkpoint cast', 'DcWailingCaverns.cpp', 'member->IsNonMeleeSpellCast(false)', 'false'),
            ('checkpoint loot', 'DcWailingCaverns.cpp', 'member->GetLootGUID()', 'false'),
            ('checkpoint vehicle', 'DcWailingCaverns.cpp', 'member->GetVehicle()', 'false'),
            ('checkpoint transport', 'DcWailingCaverns.cpp', 'member->GetTransport()', 'false'),
            ('checkpoint remote mover', 'DcWailingCaverns.cpp', 'member->m_mover != member', 'false'),
            ('checkpoint physical floor', 'DcWailingCaverns.cpp', 'member->GetExactDist(step.x, step.y, step.z) > step.radius', 'false'),
            ('route follower missing event', 'DcWailingCaverns.cpp', '!event || ', ''),
            ('route follower missing step', 'DcWailingCaverns.cpp', 'progress.stepIndex >= event->steps.size()', 'false'),
            ('route follower escort handoff', 'DcWailingCaverns.cpp', 'step.kind != EventStepKind::MoveTo', 'false'),
            ('route follower unsafe failure', 'DcWailingCaverns.cpp', 'DcRun::Of(context).paused = true;', '(void)0;'),
            ('Fanglord gate', 'DcNaralexEscort.cpp', 'instance->GetData(type) != DONE', 'false'),
            ('Fanglord count', 'DcNaralexEscort.cpp', 'type < 4', 'type < 3'),
            ('missing instance', 'DcNaralexEscort.cpp', 'if (!instance)', 'if (false)'),
            ('missing or invalid escort', 'DcNaralexEscort.cpp', 'if (!escortAI)', 'if (false)'),
            ('native escort data', 'DcNaralexEscort.cpp', 'escortAI->GetData(2) == 2 && ', ''),
            ('native encounter credit', 'DcNaralexEscort.cpp', '(instance->GetCompletedEncounterMask() & MutanusBit) &&', 'true &&'),
            ('native departure path', 'DcNaralexEscort.cpp', 'escortAI->GetScript()->GetPathId() == 3679', 'true'),
            ('running script identity', 'DcNaralexEscort.cpp', 'escortAI->GetScript()->GetPathId() != DiscipleEntry', 'false'),
            ('running faction', 'DcNaralexEscort.cpp', 'disciple->GetFaction() != 250', 'false'),
            ('cancelled start', 'DcNaralexEscort.cpp', 'DcRun::Of(context).enabled', 'true'),
            ('paused start', 'DcNaralexEscort.cpp', '!DcRun::Of(context).paused', 'true'),
            ('stale objective', 'DcNaralexEscort.cpp', 'context->GetValue<DungeonEventProgress&>(DcKey::EventProgress)->Get().eventId == 2', 'true'),
            ('inactive persistent event', 'DcNaralexEscort.cpp', 'DungeonEventExecutor::IsPersistentAnchoredEventActive(context)', 'true'),
            ('gossip line of sight', 'DcNaralexEscort.cpp', '!bot->IsWithinLOSInMap(disciple)', 'false'),
            ('gossip skipped', 'DcNaralexEscort.cpp', 'DungeonEventExecutor::SelectGossip(bot, disciple, 0);', '(void)0;'),
            ('missing group guard', 'DcNaralexEscort.cpp', 'if (Group* group = bot->GetGroup())', 'if (Group* group = nullptr)'),
            ('trailing member', 'DcNaralexEscort.cpp', 'member->GetExactDist(disciple) > 15.0f', 'false'),
            ('member native world and map', 'DcNaralexEscort.cpp', '!member->IsInWorld() || !member->IsInMap(bot) ||', ''),
            ('member phase', 'DcNaralexEscort.cpp', '!member->InSamePhase(bot)', 'false'),
            ('member line of sight', 'DcNaralexEscort.cpp', '!member->IsWithinLOSInMap(disciple)', 'false'),
            ('member death', 'DcNaralexEscort.cpp', '!bot->IsAlive()', 'false'),
            ('member flight', 'DcNaralexEscort.cpp', 'bot->IsInFlight()', 'false'),
            ('member pending transfer', 'DcNaralexEscort.cpp', 'bot->IsBeingTeleported()', 'false'),
            ('member vehicle', 'DcNaralexEscort.cpp', 'bot->GetVehicle()', 'false'),
            ('member transport', 'DcNaralexEscort.cpp', 'bot->GetTransport()', 'false'),
            ('member combat', 'DcNaralexEscort.cpp', 'bot->IsInCombat()', 'false'),
            ('member cast', 'DcNaralexEscort.cpp', 'bot->IsNonMeleeSpellCast(false)', 'false'),
            ('member loot', 'DcNaralexEscort.cpp', 'bot->GetLootGUID()', 'false'),
            ('protection line of sight', 'DcNaralexEscort.cpp', '!bot->IsWithinLOSInMap(threat)', 'false'),
            ('normal attack target', 'DcNaralexEscort.cpp', 'Set(threat);', 'Set(nullptr);'),
            ('normal attack skipped', 'DcNaralexEscort.cpp', 'MeleeAction(GET_PLAYERBOT_AI(bot)).Execute(Event());', '(void)0;'),
            ('formation takes escort movement', 'DcNaralexEscort.cpp', 'StepResult const result = Approach(member, context, disciple, 8.0f);', 'StepResult const result = StepResult::Running;'),
            ('unreachable follower ignored', 'DcNaralexEscort.cpp', 'DcRun::Of(context).paused = true;', '(void)0;'),
            ('sticky event removed', 'AuthoredWC.cpp', '.Persistent()', ''),
            ('movement ownership removed', 'AuthoredWC.cpp', '.StepsOwnMovement()', ''),
            ('ground path changed', 'AuthoredWC.cpp', '-206.648f', '-290.65567f'),
            ('route timeout removed', 'AuthoredWC.cpp', '.Timeout(120000)', ''),
            ('escort timeout removed', 'AuthoredWC.cpp', '.Timeout(900000)', ''),
            ('unbounded escort exemption', 'AuthoredWC.cpp', '&&\n                               !DcEarnedEvents::IsNaralexStep(step)', ''),
            ('route dispatch skipped', 'AuthoredWC.cpp', 'return DcWailingCaverns::RunLeg(bot, context, step);', 'return StepResult::Done;'),
            ('escort dispatch skipped', 'AuthoredWC.cpp', 'return DcNaralexEscort::Run(bot, context);', 'return StepResult::Done;'),
            ('legacy escort speed driver admitted', 'AuthoredWC.cpp', '&&\n                     !DcEarnedEvents::IsNaralexStep(step)', ''),
            ('route follower dispatch omitted', 'AuthoredWC.cpp', 'DcWailingCaverns::FollowRoute(bot, tank) ||', ''),
            ('escort follower dispatch omitted', 'AuthoredWC.cpp', 'DcNaralexEscort::Follow(bot, tank) ||', ''),
        ]
        reject_mutants(work, mutations, lambda directory, executable: [compiler, '-std=c++20', '-O1', '-I', str(directory),
                       '-I', g3d_include, str(directory / 'fixture.cpp'), '-o', str(executable)], 'Wailing Caverns')


if __name__ == '__main__':
    main()
