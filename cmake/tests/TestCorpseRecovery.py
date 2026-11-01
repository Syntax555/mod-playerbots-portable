"""Run native release, corpse travel and reclaim decisions without a realm.

Production Playerbots methods and the core packet handlers execute against
recording movement, time, navmesh and geometry. No resurrection or travel decision is
implemented by the fixture. Minimal-AI priorities use the native strategy data.
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
    run_fixture,
    source_argument,
    sql_rows,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help='prepared Playerbots src directory')
source_argument(parser, 'core', help='prepared core source directory')
args = parser.parse_args()
core = args.core or prepared_core(Path(__file__).resolve().parents[2])
source = args.source or core / 'modules/mod-playerbots/src'
corpse_source = (source / 'Ai/Base/Actions/ReviveFromCorpseAction.cpp').read_text()
release_source = (source / 'Ai/Base/Actions/ReleaseSpiritAction.cpp').read_text()
strategy_source = (source / 'Ai/Base/Strategy/DeadStrategy.cpp').read_text()
core_source = (core / 'src/server/game/Handlers/MiscHandler.cpp').read_text()
corpse_header = (core / 'src/server/game/Entities/Corpse/Corpse.h').read_text()
engine_source = (source / 'Bot/Engine/Engine.cpp').read_text()
player_source = (core / 'src/server/game/Entities/Player/Player.cpp').read_text()
object_header = (core / 'src/server/game/Globals/ObjectMgr.h').read_text()
map_header = (core / 'src/server/game/Maps/Map.h').read_text()
dbc_header = (core / 'src/server/shared/DataStores/DBCStructure.h').read_text()
dbc_enums = (core / 'src/server/shared/DataStores/DBCEnums.h').read_text()

# Both native minimal-AI filters must agree with the strategy boundary exercised below.
assert 'if (minimal && (relevance < 100))' in function(engine_source, 'bool Engine::DoNextAction(')
assert 'if (minimal && node->getFirstRelevance() < 100)' in function(engine_source, 'void Engine::ProcessTriggers(')
can_move = function((source / 'Bot/PlayerbotAI.cpp').read_text(), 'bool PlayerbotAI::CanMove()')
assert '(bot->isDead() && !bot->HasPlayerFlag(PLAYER_FLAGS_GHOST))' in can_move
movement_source = (source / 'Ai/Base/Actions/MovementActions.cpp').read_text()
move = movement_source.split('bool MovementAction::MoveTo(uint32', 1)[1].split('\n    return false;', 1)[0]
assert move.index('if (!IsMovingAllowed())') < move.index('DoMovePoint(')
# An exact waypoint goes to the spline as given; the height search would accept the core's straight lines.
exact = move.split('else if (exact_waypoint || disableMoveSplinePath || !generatePath)', 1)[1].split('\n    else\n', 1)[0]
assert 'DoMovePoint(bot, x, y, z, generatePath, backwards);' in exact and 'SearchForBestPath' not in exact
assert 'int typeOk = PATHFIND_NORMAL | PATHFIND_INCOMPLETE;' in function(
    movement_source, 'const Movement::PointsArray MovementAction::SearchForBestPath(')
# The navmesh double answers a player as the core does: an end without a polygon and a route past the
# point limit come back as straight lines, which the spline then follows.
path_header = (core / 'src/server/game/Movement/MovementGenerators/PathGenerator.h').read_text()
path_source = (core / 'src/server/game/Movement/MovementGenerators/PathGenerator.cpp').read_text()
poly_path = function(path_source, 'void PathGenerator::BuildPolyPath(')
assert re.search(r'bool path = creature \? creature->CanFly\(\) : true;.*?if \(path \|\| \(waterPath && canSwim\)\)\s*\{'
                 r'\s*_type = PathType\(PATHFIND_NORMAL \| PATHFIND_NOT_USING_PATH\);', poly_path, re.DOTALL)
assert re.search(r'_type = PathType\(PATHFIND_INCOMPLETE\);\s*AddFarFromPolyFlags\(startFarFromPoly, endFarFromPoly\);',
                 poly_path)
point_path = function(path_source, 'void PathGenerator::BuildPointPath(')
assert re.search(r'else if \(pointCount >= _pointPathLimit\)\s*\{\s*BuildShortcut\(\);\s*'
                 r'_type = PathType\(_type \| PATHFIND_SHORT\);', point_path)
assert 'SetActualEndPosition(_pathPoints[pointCount - 1]);' in point_path
assert 'if (result && !(path.GetPathType() & PATHFIND_NOPATH))' in function(
    (core / 'src/server/game/Movement/Spline/MoveSplineInit.cpp').read_text(),
    'void MoveSplineInit::MoveTo(Vector3 const& dest,')
point_limit = re.search(r'#ifdef MOD_PLAYERBOTS.*?#define MAX_POINT_PATH_LENGTH\s+(\d+)\s.*?#else', path_header, re.DOTALL)
path_step = re.search(r'^#define SMOOTH_PATH_STEP_SIZE\s+([0-9.]+f)$', path_header, re.MULTILINE)
assert 'return GetMap()->GetCorpseByPlayer(GetGUID());' in function(player_source, 'Corpse* Player::GetCorpse() const')
assert '_corpsesByPlayer.find(ownerGuid)' in function(
    (core / 'src/server/game/Maps/Map.h').read_text(), 'Corpse* GetCorpseByPlayer(')
assert 'return IsRealPlayer(master) || IsSelfBot(master);' in function(
    (source / 'Bot/PlayerbotAI.cpp').read_text(), 'bool PlayerbotAI::HasGameClientMaster()')
assert '_corpseLocation.GetMapId() != MAPID_INVALID' in function(
    (core / 'src/server/game/Entities/Player/Player.h').read_text(), 'bool HasCorpse() const')
assert 'return _corpseLocation;' in function(
    (core / 'src/server/game/Entities/Player/Player.h').read_text(), 'WorldLocation GetCorpseLocation() const')
reach = function((source / 'Ai/Base/Actions/AreaTriggerAction.cpp').read_text(), 'bool ReachAreaTriggerAction::Execute(')
assert 'if (IsSelfBot(bot))' in reach and '/*generatePath*/ true' in reach and '/*forceDestination*/ false' in reach
assert 'Get().lastAreaTrigger = triggerId;' in reach
within = function((source / 'Ai/Base/Trigger/WithinAreaTrigger.cpp').read_text(), 'bool WithinAreaTrigger::IsActive()')
assert 'return IsPointInAreaTriggerZone(at, bot->GetMapId()' in within
assert 'if (!movement.lastAreaTrigger)' in within
area = function((source / 'Ai/Base/Actions/AreaTriggerAction.cpp').read_text(), 'bool AreaTriggerAction::Execute(')
assert 'movement.lastAreaTrigger = 0;' in area and 'bot->GetSession()->HandleAreaTriggerOpcode(p);' in area
core_entry = function(core_source, 'void WorldSession::HandleAreaTriggerOpcode(')
assert 'if (!player->IsInAreaTriggerRadius(atEntry, isTavernAreatrigger ? 5.f : 0.f))' in core_entry
assert 'sMapMgr->PlayerCannotEnter(at->target_mapId, player, false)' in core_entry
assert 'player->GetCorpseLocation().GetMapId() == at->target_mapId' in core_entry
assert 'corpseInstance ? corpseInstance->Parent : 0' in function(
    (core / 'src/server/game/Maps/MapMgr.cpp').read_text(), 'Map::EnterState MapMgr::PlayerCannotEnter(')

production = {
    'entrance': function(corpse_source, 'bool HasRemoteInstanceCorpse(') + '\n' +
                function(corpse_source, 'AreaTrigger const* FindCorpseEntrance('),
    'walk': function(corpse_source, 'bool FindGhostWalk('),
    'find': function(corpse_source, 'bool FindCorpseAction::Execute('),
    'useful': function(corpse_source, 'bool FindCorpseAction::isUseful()'),
    'reclaim': function(corpse_source, 'bool ReviveFromCorpseAction::Execute('),
    'release': '\n'.join(function(release_source, signature) for signature in (
        'bool ReleaseSpiritAction::Execute(', 'void ReleaseSpiritAction::IncrementDeathCount()',
        'bool AutoReleaseSpiritAction::Execute(', 'bool AutoReleaseSpiritAction::isUseful()',
        'bool AutoReleaseSpiritAction::ShouldAutoRelease()')),
    'core': '\n'.join(function(core_source, signature) for signature in (
        'void WorldSession::HandleRepopRequestOpcode(', 'void WorldSession::HandleReclaimCorpseOpcode(')),
    'priority': function(strategy_source, 'void DeadStrategy::InitTriggers(') + '\n' +
                function(strategy_source, 'DeadStrategy::DeadStrategy('),
}
classes = '\n'.join((
    function((source / 'Bot/Engine/Action/Action.h').read_text(), 'class NextAction') + ';',
    'class Trigger { public: std::vector<NextAction> getHandlers() { return {}; } };',
    function((source / 'Bot/Engine/Trigger/Trigger.h').read_text(), 'class TriggerNode') + ';',
    ('class Strategy { public: explicit Strategy(PlayerbotAI*) {} virtual ~Strategy() = default; '
     'virtual void InitTriggers(std::vector<TriggerNode*>&) {} virtual std::string const getName() { return ""; } };'),
    function((source / 'Ai/Base/Strategy/PassThroughStrategy.h').read_text(), 'class PassThroughStrategy') + ';',
    function((source / 'Ai/Base/Strategy/PassThroughStrategy.cpp').read_text(), 'void PassThroughStrategy::InitTriggers('),
    function((source / 'Ai/Base/Strategy/DeadStrategy.h').read_text(), 'class DeadStrategy') + ';',
))

prelude = r'''
#include <algorithm>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <map>
#include <limits>
#include <string>
#include <type_traits>
#include <unordered_map>
#include <vector>
using uint8=std::uint8_t; using uint32=std::uint32_t; using uint64=std::uint64_t; using int64=std::int64_t; using int32=std::int32_t;
constexpr int MINUTE=60, MOVE_RUN=0, ALL_ACTIVITY=0, PET_SAVE_NOT_IN_SLOT=0;
constexpr uint32 PLAYER_FLAGS_GHOST=1, SPELL_WAITING_FOR_RESURRECT=2;
constexpr uint32 AURA_INTERRUPT_FLAG_TELEPORTED=1, AURA_INTERRUPT_FLAG_CHANGE_MAP=2;
constexpr int CMSG_REPOP_REQUEST=1, CMSG_RECLAIM_CORPSE=2, CMSG_AREATRIGGER=3;
constexpr uint32 MAPID_INVALID=std::numeric_limits<uint32>::max();
static int64 fixtureNow=100000;
#define time(...) fixtureNow
#define LOG_DEBUG(...) ((void)0)
namespace GameTime { std::chrono::seconds GetGameTime() { return std::chrono::seconds(fixtureNow); } }
enum class DeathState { Alive, JustDied, Corpse };
struct ObjectGuid { uint64 value=1; void Clear() { value=0; } };
static unsigned reclaimPackets=0;
struct WorldPacket {
    int opcode=0; ObjectGuid guid; uint32 triggerId=0; bool emptyPacket=true;
    explicit WorldPacket(int op=0):opcode(op),emptyPacket(op==0) { if(op==CMSG_RECLAIM_CORPSE) ++reclaimPackets; }
    bool empty() const { return emptyPacket; } int GetOpcode() const { return opcode; }
    WorldPacket& operator<<(ObjectGuid value) { guid=value; return *this; }
    WorldPacket& operator<<(uint8) { return *this; }
    WorldPacket& operator<<(uint32 value) { triggerId=value;return *this; }
    WorldPacket& operator>>(ObjectGuid& value) { value=guid; return *this; }
    template<class T> void read_skip() {}
};
struct Event { WorldPacket packet;std::string label;Event()=default;
    Event(char const* name,WorldPacket const& p):packet(p),label(name) {} WorldPacket& getPacket() { return packet; } };
struct Player;
struct AreaTrigger;
struct WorldLocation {
    uint32 map=MAPID_INVALID;float x=0,y=0,z=0;
    uint32 GetMapId() const { return map; } float GetPositionX() const { return x; }
    float GetPositionY() const { return y; } float GetPositionZ() const { return z; }
    float GetExactDistSq(float px,float py,float pz) const { return (x-px)*(x-px)+(y-py)*(y-py)+(z-pz)*(z-pz); }
};
struct Corpse {
    float x=200,y=0,z=0; uint32 map=1; int64 ghostTime=fixtureNow-60; int type=1;
    int64 GetGhostTime() const { return ghostTime; } int GetType() const { return type; }
    bool IsInMap(Player*) const; bool IsWithinDist(Player*,float,bool) const;
};
struct Motion { unsigned clears=0; void Clear() { ++clears; } };
struct Map { bool dungeon=false,raid=false; bool IsDungeon() const { return dungeon; } bool IsRaid() const { return raid; } };
struct Group {};
struct WorldSession { Player* _player; Player* GetPlayer() { return _player; }
    void HandleRepopRequestOpcode(WorldPacket&); void HandleReclaimCorpseOpcode(WorldPacket&); };
struct Player {
    float x=0,y=0,z=0; uint32 mapId=1; bool alive=false,ghost=true,bg=false,arena=false,moving=false;
    bool aiControlled=true,selfBot=false,path=true,preventResurrection=false,grouped=false,fleeUseful=false;
    unsigned resurrections=0,bones=0,teleports=0,freeRepairs=0,graveyardReleases=0,moves=0;
    float targetX=0,targetY=0,targetZ=0; uint32 targetMap=0; bool exactMove=false; Corpse* corpse=nullptr; Corpse* releaseCorpse=nullptr;
    float meshEdge=1e9f,reachEdge=1e9f; bool startOffMesh=false;
    WorldSession* session=nullptr; Motion motion; Map map; Group group;
    WorldLocation corpseLocation;
    bool IsAlive() const { return alive; } bool isDead() const { return !alive; }
    bool InBattleground() const { return bg; } bool InArena() const { return arena; }
    bool HasPlayerFlag(uint32) const { return ghost; } bool HasAura(uint32) const { return false; }
    bool HasPreventResurectionAura() const { return preventResurrection; }
    DeathState getDeathState() const { return alive?DeathState::Alive:DeathState::Corpse; }
    void KillPlayer() {} void RemovePet(void*,int,bool) {}
    void BuildPlayerRepop() { ghost=true; corpse=releaseCorpse; corpse->ghostTime=fixtureNow;
        corpseLocation={corpse->map,corpse->x,corpse->y,corpse->z}; }
    void RepopAtGraveyard() { ++graveyardReleases; x=0; }
    Corpse* GetCorpse() { return corpse && corpse->map==mapId?corpse:nullptr; } uint32 GetMapId() const { return mapId; }
    bool HasCorpse() const { return corpseLocation.map!=MAPID_INVALID; }
    WorldLocation GetCorpseLocation() const { return corpseLocation; }
    float GetExactDistSq(float px,float py,float pz) const { return (x-px)*(x-px)+(y-py)*(y-py)+(z-pz)*(z-pz); }
    float GetPositionX() const { return x; } float GetPositionY() const { return y; } float GetPositionZ() const { return z; }
    float GetAngle(struct WorldPosition const*) const;
    bool IsInAreaTriggerRadius(AreaTrigger const*) const;
    Group* GetGroup() { return grouped?&group:nullptr; } Map* GetMap() { return &map; }
    ObjectGuid GetGUID() const { return {}; } WorldSession* GetSession() { return session; }
    Motion* GetMotionMaster() { return &motion; } void StopMoving() { moving=false; }
    bool isMoving() const { return moving; } float GetSpeed(int) const { return 7; }
    uint32 GetCorpseReclaimDelay(bool) const { return 30; }
    void ResurrectPlayer(float) { ++resurrections; alive=true; ghost=false; }
    void SpawnCorpseBones() { ++bones; corpse=nullptr;corpseLocation.map=MAPID_INVALID; }
    void DurabilityRepairAll(bool,float,bool) { ++freeRepairs; }
    void RemoveAurasWithInterruptFlags(uint32) {}
    bool TeleportTo(uint32 id,float px,float py,float pz,float) { ++teleports; mapId=id; x=px; y=py; z=pz; return true; }
};
bool Corpse::IsInMap(Player* p) const { return map==p->mapId; }
bool Corpse::IsWithinDist(Player* p,float distance,bool threeD) const {
    return std::sqrt((x-p->x)*(x-p->x)+(y-p->y)*(y-p->y)+(threeD?(z-p->z)*(z-p->z):0))<=distance;
}
using GuidVector=std::vector<ObjectGuid>;
struct LastMovement { uint32 lastAreaTrigger=0; };
template<class T> struct Value { T value{}; T Get() const { return value; } void Set(T next) { value=next; } };
template<> struct Value<LastMovement&> { LastMovement value;LastMovement& Get() { return value; } };
struct Context { Value<uint32> deaths; Value<float> leaderDistance; Value<GuidVector> targets;Value<LastMovement&> lastTrigger;
    template<class T> Value<T>* GetValue(char const*,char const* =nullptr) {
        if constexpr(std::is_same_v<T,uint32>) return &deaths;
        else if constexpr(std::is_same_v<T,float>) return &leaderDistance;
        else if constexpr(std::is_same_v<T,LastMovement&>) return &lastTrigger;
        else return &targets;
    }
};
struct Config { bool naturalProgression=true; float FarDistance=50,SpellDistance=30,ReactDistance=50,SightDistance=40; } sPlayerbotAIConfig;
struct ServerFacade {
    static ServerFacade& instance() { static ServerFacade s; return s; }
    bool IsDistanceLessThan(float a,float b) { return a<b; } bool IsDistanceGreaterThan(float a,float b) { return a>b; }
    float GetDistance2d(Player* p,Corpse* c) { return std::hypot(p->x-c->x,p->y-c->y); }
};
struct WorldPosition { uint32 map=1; float x=0,y=0,z=0;
    explicit WorldPosition(Player* p) { if(p) { map=p->mapId;x=p->x;y=p->y;z=p->z; } }
    explicit WorldPosition(Corpse* p):map(p->map),x(p->x),y(p->y),z(p->z) {}
    WorldPosition(uint32 m,float px,float py,float pz,float=0):map(m),x(px),y(py),z(pz) {}
    float distance(WorldPosition p) const { return std::sqrt((x-p.x)*(x-p.x)+(y-p.y)*(y-p.y)+(z-p.z)*(z-p.z)); }
    float fDist(WorldPosition p) const { return distance(p); }
    uint32 GetMapId() const { return map; } float GetPositionX() const { return x; }
    float GetPositionY() const { return y; } float GetPositionZ() const { return z; }
    unsigned getUnitsAggro(GuidVector const&,Player*) const { return 0; }
    bool GetReachableRandomPointOnGround(Player*,float,uint32) { return false; }
};
float Player::GetAngle(WorldPosition const* p) const { return std::atan2(p->y-y,p->x-x); }
uint32 urand(uint32 lower,uint32) { return lower; }
struct FleeManager { Player* bot; FleeManager(Player* p,float,double,uint32,WorldPosition):bot(p) {}
    bool isUseful() const { return bot->fleeUseful; } bool CalculateDestination(float*,float*,float*) { return false; } };
struct PlayerbotAI {
    Player* bot; Player* leader=nullptr; Player* master=nullptr; Context context;
    bool active=false,healerResult=false,follow=true,reachResult=true; unsigned healerCalls=0,reachCalls=0; int64 bgReleaseAttemptTime=0;
    uint32 reachedTrigger=0;
    explicit PlayerbotAI(Player* p):bot(p) {}
    Player* GetGroupLeader() { return leader; } Player* GetMaster() { return master; }
    bool HasGameClientMaster() { return master&&(!master->aiControlled||master->selfBot); }
    bool AllowActivity(int) { return active; }
    bool DoSpecificAction(char const* name,Event event=Event(),bool checkUseful=false) {
        if(std::string(name)=="reach area trigger") { assert(checkUseful&&event.label=="find corpse");
            assert(event.packet.opcode==CMSG_AREATRIGGER);++reachCalls;reachedTrigger=event.packet.triggerId;return reachResult; }
        assert(std::string(name)=="spirit healer");++healerCalls;return healerResult;
    }
    bool HasStrategy(char const*,int) { return follow; } void ChangeStrategy(char const*,int) { follow=true; }
    void TellMasterNoFacing(std::string const&) {} void SetNextCheckDelay(uint32) {}
};
#define GET_PLAYERBOT_AI(player) ((player)&&(player)->aiControlled?reinterpret_cast<void*>(1):nullptr)
bool IsSelfBot(Player* p) { return p&&p->selfBot; }
#define AI_VALUE(type,name) context->GetValue<type>(name)->Get()
#define AI_VALUE2(type,name,qualifier) context->GetValue<type>(name,qualifier)->Get()
constexpr int BOT_STATE_NON_COMBAT=0;
struct RandomManager { unsigned revives=0; void Revive(Player* p) { ++revives;p->alive=true; } } sRandomPlayerbotMgr;
struct PlayerbotTextMgr { static PlayerbotTextMgr& instance() { static PlayerbotTextMgr p; return p; }
    std::string GetBotTextOrDefault(char const*,char const* fallback,std::map<std::string,std::string> const&) { return fallback; } };
struct Action { PlayerbotAI* botAI; Player* bot; Context* context;
    Action(PlayerbotAI* ai,char const*):botAI(ai),bot(ai->bot),context(&ai->context) {} };
struct MovementAction:Action { using Action::Action;
    bool MoveTo(uint32 map,float x,float y,float z,bool,bool,bool=false,bool exact=false) {
        ++bot->moves;bot->targetMap=map;bot->targetX=x;bot->targetY=y;bot->targetZ=z;bot->exactMove=exact;
        if(!bot->path||!bot->ghost||map!=bot->mapId) return false;
        bot->moving=true;return true;
    }
};
struct FindCorpseAction:MovementAction { explicit FindCorpseAction(PlayerbotAI* ai):MovementAction(ai,"find corpse") {}
    bool Execute(Event);bool isUseful(); };
struct ReviveFromCorpseAction:MovementAction { explicit ReviveFromCorpseAction(PlayerbotAI* ai):MovementAction(ai,"revive from corpse") {}
    bool Execute(Event); };
struct ReleaseSpiritAction:Action { explicit ReleaseSpiritAction(PlayerbotAI* ai):Action(ai,"release") {}
    bool Execute(Event);void IncrementDeathCount() const;void LogRelease(std::string const&) const {} };
struct AutoReleaseSpiritAction:ReleaseSpiritAction { using ReleaseSpiritAction::ReleaseSpiritAction;
    ObjectGuid _bgSpiritGuideGuid,_bgSpiritGuideRejectedGuid;int64 _bgSpiritGuideSearchTime=0;
    bool Execute(Event);bool isUseful();bool ShouldAutoRelease() const;
    bool ShouldDelayBattlegroundRelease() const { assert(false);return false; }
    bool HandleBattlegroundSpiritHealer() { assert(false);return false; }
};
'''

portal_types = '\n'.join(function(text, declaration) + ';' for text, declaration in (
    (object_header, 'struct AreaTriggerTeleport'), (object_header, 'struct AreaTrigger\n'),
    (map_header, 'struct InstanceTemplate\n'), (dbc_enums, 'enum MapTypes'), (dbc_enums, 'enum MapFlags')))
portal_types += '\nconstexpr uint32 MAP_EASTERN_KINGDOMS=0,MAP_KALIMDOR=1,MAP_OUTLAND=530,MAP_NORTHREND=571;\n'
portal_types += function(dbc_header, 'struct MapEntry\n') + ';\n'
portal_types += r'''
struct MapStore {
    std::map<uint32,MapEntry> entries;
    MapEntry const* LookupEntry(uint32 id) const { auto i=entries.find(id);return i==entries.end()?nullptr:&i->second; }
    uint32 GetNumRows() const { return entries.empty()?0:entries.rbegin()->first+1; }
} sMapStore;
struct ObjectManager {
    std::map<uint32,AreaTrigger> areas;std::unordered_map<uint32,AreaTriggerTeleport> teleports;
    std::map<uint32,InstanceTemplate> instances;mutable unsigned scans=0;
    AreaTrigger const* GetAreaTrigger(uint32 id) const { auto i=areas.find(id);return i==areas.end()?nullptr:&i->second; }
    AreaTriggerTeleport const* GetAreaTriggerTeleport(uint32 id) const { auto i=teleports.find(id);return i==teleports.end()?nullptr:&i->second; }
    auto const& GetAllAreaTriggerTeleports() const { ++scans;return teleports; }
    InstanceTemplate const* GetInstanceTemplate(uint32 id) const { auto i=instances.find(id);return i==instances.end()?nullptr:&i->second; }
} objects;
ObjectManager* sObjectMgr=&objects;
bool Player::IsInAreaTriggerRadius(AreaTrigger const* at) const {
    return mapId==at->map&&GetExactDistSq(at->x,at->y,at->z)<=at->radius*at->radius;
}
'''
scarlet_ids = {45, 610, 612, 614}
scarlet_areas = {int(row['entry']): row for row in sql_rows(core, 'areatrigger', scarlet_ids)}
scarlet_targets = sql_rows(core, 'areatrigger_teleport', scarlet_ids)
scarlet_data = []
for target in scarlet_targets:
    trigger_id = int(target['ID'])
    at = scarlet_areas[trigger_id]
    geometry = [at[key] if index < 2 else str(float(at[key])) + 'f'
                for index, key in enumerate(('entry', 'map', 'x', 'y', 'z', 'radius', 'length', 'width', 'height', 'orientation'))]
    destination = [target[key] if index == 0 else str(float(target[key])) + 'f'
                   for index, key in enumerate(('target_map', 'target_position_x', 'target_position_y',
                                               'target_position_z', 'target_orientation'))]
    scarlet_data.append('{{' + ','.join(geometry) + '},{' + ','.join(destination) + '}}')
portal_types += '\nstd::vector<std::pair<AreaTrigger,AreaTriggerTeleport>> scarletPortals={' + ','.join(scarlet_data) + '};\n'

tests = r'''
struct Scenario {
    Corpse corpse;Player bot;PlayerbotAI ai;FindCorpseAction find;ReviveFromCorpseAction reclaim;AutoReleaseSpiritAction release;WorldSession session;
    Scenario():ai(&bot),find(&ai),reclaim(&ai),release(&ai),session{&bot} {
        bot.corpse=&corpse;bot.releaseCorpse=&corpse;bot.session=&session;reclaimPackets=0;sRandomPlayerbotMgr.revives=0;
        bot.corpseLocation={corpse.map,corpse.x,corpse.y,corpse.z};sMapStore={};objects={};pathQueries=0;
    }
    void Safe() { assert(!bot.teleports&&!bot.freeRepairs&&!sRandomPlayerbotMgr.revives); }
};
void TravelAndReclaim() {
    sPlayerbotAIConfig.naturalProgression=true;
    for(uint32 deaths:{0,4,5,6,20,100}) for(int64 age:{0,59,599,600,601,3600}) {
        Scenario s;s.ai.context.deaths.value=deaths;s.corpse.ghostTime=fixtureNow-age;
        assert(s.find.isUseful()&&s.find.Execute(Event()));
        assert(s.bot.moves==1&&s.bot.targetX==s.corpse.x&&s.bot.targetMap==s.corpse.map&&!s.ai.healerCalls);
        assert(!s.bot.resurrections&&!reclaimPackets&&s.ai.context.deaths.value==deaths);s.Safe();
    }
    for(uint32 deaths:{0,4,5,20,100}) for(int64 age:{31,600,3600}) {
        Scenario s;s.ai.context.deaths.value=deaths;s.corpse.ghostTime=fixtureNow-age;s.bot.x=180;
        assert(!s.find.Execute(Event()));assert(s.reclaim.Execute(Event()));
        assert(s.bot.alive&&s.bot.resurrections==1&&s.bot.bones==1&&reclaimPackets==1&&!s.ai.healerCalls);s.Safe();
    }
    { Scenario s;s.bot.moving=true;s.ai.context.deaths.value=100;s.corpse.ghostTime=fixtureNow-3600;
      assert(s.find.Execute(Event())&&!s.bot.moves&&!s.ai.healerCalls&&!pathQueries);s.Safe(); }
    { Scenario s;s.bot.path=false;s.ai.context.deaths.value=100;s.corpse.ghostTime=fixtureNow-3600;
      assert(!s.find.Execute(Event())&&s.bot.moves==1&&s.ai.healerCalls==1&&!s.bot.resurrections);s.Safe(); }
    { Scenario s;s.bot.corpse=nullptr;assert(!s.find.isUseful()&&!s.find.Execute(Event())&&!s.reclaim.Execute(Event()));s.Safe(); }
    { Scenario s;s.bot.mapId=2;assert(!s.bot.GetCorpse()&&!s.find.isUseful()&&!s.find.Execute(Event()));s.Safe(); }
    { Scenario s;s.bot.alive=true;s.bot.corpse=nullptr;assert(!s.find.isUseful()&&!s.find.Execute(Event())&&!s.reclaim.Execute(Event()));s.Safe(); }
    { Scenario s;s.bot.bg=true;assert(!s.find.isUseful()&&!s.find.Execute(Event())&&!s.reclaim.Execute(Event()));s.Safe(); }
    { Scenario s;Player leader;leader.aiControlled=false;leader.corpse=&s.corpse;s.ai.leader=&leader;s.ai.context.leaderDistance.value=5;s.bot.x=180;
      assert(!s.reclaim.Execute(Event())&&!reclaimPackets);leader.alive=true;
      assert(s.reclaim.Execute(Event())&&s.bot.alive);s.Safe(); }
}
bool Walk(Scenario& s) {
    unsigned moves=s.bot.moves;float x=s.bot.x,y=s.bot.y;
    if(!s.find.Execute(Event())) return false;
    assert(s.bot.moves==moves+1&&s.bot.exactMove&&s.bot.targetMap==s.corpse.map);
    assert(s.bot.targetX<=std::min(s.bot.meshEdge,s.bot.reachEdge)&&std::hypot(s.bot.targetX-x,s.bot.targetY-y)<=POINT_PATH_REACH);
    s.bot.x=s.bot.targetX;s.bot.y=s.bot.targetY;s.bot.z=s.bot.targetZ;s.bot.moving=false;return true;
}
void GhostWalks() {
    sPlayerbotAIConfig.naturalProgression=true;
    // A route longer than a path holds is walked in legs to the body, never along the core's straight line.
    { Scenario s;s.corpse.x=POINT_PATH_REACH*2.5f;
      assert(Walk(s)&&s.bot.x==GHOST_WALK_LEG&&pathQueries==2);
      unsigned legs=1;while(Walk(s)) ++legs;
      assert(legs>2&&s.bot.x==s.corpse.x);
      assert(!s.ai.healerCalls&&s.reclaim.Execute(Event())&&s.bot.alive);s.Safe(); }
    // A body off the navmesh is approached only to the mesh edge; then the spirit healer remains.
    { Scenario s;s.bot.meshEdge=100;assert(Walk(s)&&s.bot.x==GHOST_WALK_LEG);
      assert(!Walk(s)&&s.bot.moves==1&&s.ai.healerCalls==1&&!s.bot.resurrections);s.Safe(); }
    { Scenario s;s.bot.meshEdge=210;s.corpse.x=230;
      assert(Walk(s)&&Walk(s)&&Walk(s)&&s.bot.x==210&&!Walk(s)&&s.bot.moves==3&&!s.ai.healerCalls);
      assert(s.reclaim.Execute(Event())&&s.bot.alive);s.Safe(); }
    // A ghost standing off the mesh starts no walk.
    { Scenario s;s.bot.startOffMesh=true;
      assert(!s.find.Execute(Event())&&!s.bot.moves&&s.ai.healerCalls==1&&pathQueries==6);s.Safe(); }
    // A floor not connected to the body's is walked to its closest reachable point.
    { Scenario s;s.bot.reachEdge=180;assert(Walk(s)&&s.bot.x==180&&pathQueries==1);
      assert(!s.find.Execute(Event())&&s.reclaim.Execute(Event())&&s.bot.alive&&!s.ai.healerCalls);s.Safe(); }
    { Scenario s;s.bot.reachEdge=100;assert(Walk(s)&&s.bot.x==100);
      assert(!Walk(s)&&s.ai.healerCalls==1&&!s.bot.resurrections);s.Safe(); }
}
void NativeReclaimGuards() {
    for(int refusal=0;refusal<8;++refusal) {
        Scenario s;s.bot.x=200;
        switch(refusal) {
            case 0:s.bot.alive=true;break;case 1:s.bot.arena=true;break;case 2:s.bot.ghost=false;break;
            case 3:s.bot.corpse=nullptr;break;case 4:s.corpse.ghostTime=fixtureNow;break;
            case 5:s.bot.mapId=2;break;case 6:s.bot.x=300;break;case 7:s.bot.z=100;break;
        }
        s.reclaim.Execute(Event());assert(!s.bot.resurrections&&!s.bot.bones);s.Safe();
    }
}
void ReleaseAndGroupWait() {
    { Scenario s;s.bot.x=200;s.bot.ghost=false;s.bot.corpse=nullptr;s.ai.context.deaths.value=4;
      assert(s.release.isUseful()&&s.release.Execute(Event()));
      assert(s.bot.ghost&&s.bot.corpse==&s.corpse&&s.bot.graveyardReleases==1&&s.ai.context.deaths.value==5);
      assert(!s.release.isUseful()&&s.find.Execute(Event())&&s.bot.moves==1);s.Safe();
      s.bot.x=s.corpse.x;s.bot.moving=false;s.corpse.ghostTime=fixtureNow-31;
      assert(s.reclaim.Execute(Event())&&s.bot.alive);s.Safe(); }
    { Scenario s;Player leader;leader.aiControlled=false;s.ai.leader=&leader;s.ai.master=&leader;
      s.bot.grouped=true;s.bot.ghost=false;s.bot.corpse=nullptr;s.bot.map.dungeon=true;s.ai.context.leaderDistance.value=5;
      assert(!s.release.isUseful());s.bot.map.dungeon=false;assert(!s.release.isUseful());
      s.ai.context.leaderDistance.value=100;assert(s.release.isUseful());
      s.bot.map.dungeon=true;leader.aiControlled=true;assert(s.release.isUseful());
      leader.aiControlled=false;ReleaseSpiritAction explicitRelease(&s.ai);Event ownerRelease;
      ownerRelease.packet=WorldPacket(CMSG_REPOP_REQUEST);
      assert(explicitRelease.Execute(ownerRelease)&&s.bot.ghost&&s.bot.graveyardReleases==1);s.Safe(); }
    { Scenario s;s.bot.arena=true;assert(!s.release.isUseful()); }
    { Scenario s;s.bot.alive=true;assert(!s.release.isUseful()); }
    { Scenario s;s.bot.ghost=false;s.bot.corpse=nullptr;s.bot.preventResurrection=true;
      assert(s.release.isUseful()&&s.release.Execute(Event()));assert(!s.bot.ghost&&!s.bot.graveyardReleases);s.Safe(); }
}
void LegacyBehavior() {
    sPlayerbotAIConfig.naturalProgression=false;
    { Scenario s;s.ai.context.deaths.value=5;assert(s.find.Execute(Event()));assert(sRandomPlayerbotMgr.revives==1&&!s.bot.moves); }
    { Scenario s;s.ai.active=true;s.corpse.ghostTime=fixtureNow-600;assert(!s.find.Execute(Event()));assert(!s.bot.moves&&s.ai.healerCalls==1); }
    { Scenario s;s.bot.x=180;s.ai.context.deaths.value=5;assert(!s.reclaim.Execute(Event()));assert(s.ai.healerCalls==1&&!reclaimPackets); }
    for(bool selfBot:{false,true}) {
        Scenario s;Player owner;owner.aiControlled=selfBot;owner.selfBot=selfBot;s.ai.master=&owner;
        s.bot.x=180;s.ai.context.deaths.value=20;assert(s.reclaim.Execute(Event())&&s.bot.alive&&!s.ai.healerCalls);s.Safe();
    }
}
void MinimalPriorities() {
    Player bot;PlayerbotAI ai(&bot);DeadStrategy strategy(&ai);
    for(bool natural:{false,true,true,false,true}) {
        sPlayerbotAIConfig.naturalProgression=natural;std::vector<TriggerNode*> nodes;strategy.InitTriggers(nodes);
        std::map<std::string,float> priorities;
        for(auto* node:nodes) { for(auto action:node->getHandlers()) priorities[action.getName()]=action.getRelevance();delete node; }
        assert(priorities.at("find corpse")==float(natural?101:100));
        assert(priorities.at("revive from corpse")==float(natural?100:99));
        assert(priorities.at("find corpse")>priorities.at("revive from corpse"));
        assert(priorities.at("self resurrect")>priorities.at("accept resurrect"));
        if(natural) assert(priorities.at("revive from corpse")>=100);
    }
}
void MapData(uint32 id,uint32 type=MAP_INSTANCE) { MapEntry entry{};entry.MapID=id;entry.map_type=type;sMapStore.entries[id]=entry; }
void Portal(uint32 id,uint32 from,float sourceX,uint32 to,float targetX) {
    objects.areas[id]={id,from,sourceX,0,0,3,0,0,0,0};objects.teleports[id]={to,targetX,0,0,0};
}
void Remote(Scenario& s,uint32 bodyMap=100) {
    sPlayerbotAIConfig.naturalProgression=true;s.bot.mapId=1;s.corpse.map=bodyMap;
    s.corpse.x=500;s.bot.corpseLocation={bodyMap,500,0,0};MapData(bodyMap);
    assert(!s.bot.GetCorpse()&&s.bot.HasCorpse());
}
void InstanceCorpseRoutes() {
    { Scenario s;Remote(s);Portal(10,1,100,100,500);
      assert(s.find.isUseful()&&s.find.Execute(Event()));
      assert(s.bot.moves==1&&s.bot.targetMap==1&&s.bot.targetX==100&&!s.ai.reachCalls&&!s.ai.healerCalls);
      assert(!s.bot.resurrections&&!reclaimPackets);s.Safe();
      s.bot.moving=false;s.bot.x=100;assert(s.find.Execute(Event()));
      assert(s.ai.reachCalls==1&&s.ai.reachedTrigger==10&&s.bot.moves==1&&!s.bot.resurrections);s.Safe();
      s.ai.context.lastTrigger.value.lastAreaTrigger=10;assert(!s.find.Execute(Event()));
      assert(s.ai.reachCalls==1&&s.ai.context.lastTrigger.value.lastAreaTrigger==10); }
    { Scenario s;Remote(s);Portal(10,1,100,100,500);s.ai.context.lastTrigger.value.lastAreaTrigger=10;
      assert(s.find.Execute(Event())&&s.bot.moves==1&&s.bot.targetX==100&&!s.ai.reachCalls);s.Safe(); }
    { Scenario s;Remote(s);s.bot.moving=true;
      assert(s.find.Execute(Event())&&!objects.scans&&!s.bot.moves&&!s.ai.reachCalls);s.Safe(); }
    { Scenario s;Remote(s);Portal(10,1,100,100,500);s.bot.path=false;
      assert(!s.find.Execute(Event())&&s.bot.moves==1&&!s.ai.reachCalls&&!s.ai.healerCalls);s.Safe(); }
    { Scenario s;Remote(s);Portal(10,1,10,100,0);Portal(20,1,100,100,490);
      s.ai.context.lastTrigger.value.lastAreaTrigger=10;
      assert(FindCorpseEntrance(&s.bot)->entry==20);assert(s.find.Execute(Event())&&s.bot.targetX==100);
      assert(s.ai.context.lastTrigger.value.lastAreaTrigger==0);s.Safe(); }
    { Scenario s;Remote(s);Portal(20,1,10,100,490);Portal(10,1,100,100,510);
      assert(FindCorpseEntrance(&s.bot)->entry==10); }
    { Scenario s;Remote(s,200);MapData(100);objects.instances[200]={100,0,false};
      Portal(10,1,30,100,9000);Portal(20,1,70,100,0);Portal(30,100,50,200,500);
      assert(FindCorpseEntrance(&s.bot)->entry==10);assert(s.find.Execute(Event())&&s.bot.targetX==30);s.Safe();
      s.bot.mapId=100;s.bot.x=0;s.bot.moving=false;s.ai.context.lastTrigger.value.lastAreaTrigger=10;
      assert(FindCorpseEntrance(&s.bot)->entry==30);assert(s.find.Execute(Event())&&s.bot.targetMap==100&&s.bot.targetX==50);s.Safe(); }
    for(int missing=0;missing<4;++missing) {
        Scenario s;Remote(s);
        if(missing==1) Portal(10,2,100,100,500);
        if(missing==2) Portal(10,1,100,300,500);
        if(missing==3) objects.teleports[10]={100,500,0,0,0};
        assert(s.find.isUseful()&&!s.find.Execute(Event())&&!s.bot.moves&&!s.ai.reachCalls&&!s.ai.healerCalls);s.Safe();
    }
    for(int refusal=0;refusal<10;++refusal) {
        Scenario s;Remote(s);Portal(10,1,100,100,500);
        switch(refusal) {
            case 0:s.bot.ghost=false;break;case 1:s.bot.alive=true;break;case 2:s.bot.selfBot=true;break;
            case 3:s.bot.bg=true;break;case 4:s.bot.arena=true;break;
            case 5:s.bot.corpseLocation.map=MAPID_INVALID;break;case 6:sMapStore.entries.clear();break;
            case 7:sMapStore.entries[100].map_type=MAP_COMMON;break;
            case 8:sPlayerbotAIConfig.naturalProgression=false;break;case 9:sMapStore.entries[100].map_type=MAP_BATTLEGROUND;break;
        }
        assert(!HasRemoteInstanceCorpse(&s.bot)&&!s.find.isUseful()&&!s.find.Execute(Event()));
        assert(!s.bot.moves&&!s.ai.reachCalls&&!s.ai.healerCalls);s.Safe();
    }
    { Scenario s;Remote(s);Player owner;owner.aiControlled=false;owner.ghost=true;
      s.ai.master=&owner;s.ai.leader=&owner;s.bot.grouped=true;Portal(10,1,100,100,500);
      assert(s.ai.HasGameClientMaster()&&s.find.Execute(Event())&&s.bot.moves==1);s.Safe(); }
    { Scenario s;Remote(s,200);MapData(100);objects.instances[200]={100,0,false};objects.instances[100]={200,0,false};
      assert(!FindCorpseEntrance(&s.bot));s.Safe(); }
    { Scenario s;Remote(s,189);s.bot.mapId=0;
      for(auto const& [at,target]:scarletPortals) { objects.areas[at.entry]=at;objects.teleports[at.entry]=target; }
      for(auto const& [at,target]:scarletPortals) {
          s.bot.corpseLocation={189,target.target_X,target.target_Y,target.target_Z};
          assert(FindCorpseEntrance(&s.bot)->entry==at.entry);
          uint32 stale=at.entry==45?610:45;AreaTrigger const& wrong=objects.areas.at(stale);
          s.bot.x=wrong.x;s.bot.y=wrong.y;s.bot.z=wrong.z;s.bot.path=false;s.bot.moving=false;
          s.ai.context.lastTrigger.value.lastAreaTrigger=stale;
          assert(s.bot.IsInAreaTriggerRadius(&wrong)&&!s.find.Execute(Event()));
          assert(s.ai.context.lastTrigger.value.lastAreaTrigger==0&&s.bot.targetX==at.x&&!s.ai.reachCalls);
      }
      s.Safe(); }
}
int main() { TravelAndReclaim();GhostWalks();NativeReclaimGuards();ReleaseAndGroupWait();LegacyBehavior();MinimalPriorities();InstanceCorpseRoutes();
    std::cout<<"Corpse recovery: native release, repeated/old deaths, real reclaim guards, group waits and minimal AI passed\n"; }
'''

native_definitions = re.search(r'^#define CORPSE_RECLAIM_RADIUS [0-9]+$', corpse_header, re.MULTILINE).group(0)
native_definitions += '\n' + function(corpse_header, 'enum CorpseType') + ';'
native_definitions += '\n' + function(path_header, 'enum PathType') + ';\n'
native_definitions += re.search(r'^constexpr float GHOST_WALK_LEG = [0-9.]+f;$', corpse_source, re.MULTILINE).group(0)
native_definitions += f'''
constexpr float POINT_PATH_REACH={point_limit.group(1)}*{path_step.group(1)};
static_assert(GHOST_WALK_LEG*2<POINT_PATH_REACH);
''' + r'''
namespace G3D { struct Vector3 { float x=0,y=0,z=0; Vector3()=default; Vector3(float a,float b,float c):x(a),y(b),z(c) {} }; }
static unsigned pathQueries=0;
// The navmesh ends at meshEdge; beyond reachEdge the floor is not connected to the ghost's.
struct PathGenerator {
    Player const* source; PathType type=PATHFIND_BLANK; G3D::Vector3 end;
    explicit PathGenerator(Player const* p):source(p) {}
    bool CalculatePath(float x,float y,float z,bool=false) {
        ++pathQueries;end={x,y,z};
        if(x>source->meshEdge) { type=PathType(PATHFIND_NORMAL|PATHFIND_NOT_USING_PATH);return true; }
        bool partial=x>source->reachEdge;
        type=partial||source->startOffMesh?PATHFIND_INCOMPLETE:PATHFIND_NORMAL;
        if(source->startOffMesh) type=PathType(type|PATHFIND_FARFROMPOLY_START);
        if(std::hypot(x-source->x,y-source->y)>POINT_PATH_REACH) type=PathType(type|PATHFIND_SHORT);
        else if(partial) end.x=source->reachEdge;
        return true;
    }
    PathType GetPathType() const { return type; }
    G3D::Vector3 const& GetActualEndPosition() const { return end; }
};
'''
real_player = function((source / 'Bot/PlayerbotAI.cpp').read_text(), 'bool IsRealPlayer(Player* player)')


def build(directory, name, parts):
    cpp = directory / (name + '.cpp')
    cpp.write_text(prelude + native_definitions + portal_types + real_player + classes + '\n'.join(parts.values()) + tests)
    executable = directory / name
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-g', '-O1',
                    *SANITIZER_FLAGS, str(cpp), '-o', str(executable)], check=True)
    return run_fixture([str(executable)], name)


mutations = (
    ('ghost straight-line corpse run', 'find',
     ('FindGhostWalk(bot, moveToPos, walkEnd) &&\n                        '
      'MoveTo(moveToPos.GetMapId(), walkEnd.x, walkEnd.y, walkEnd.z, false, false, false, true)'),
     ('MoveTo(moveToPos.GetMapId(), moveToPos.GetPositionX(), moveToPos.GetPositionY(), '
      'moveToPos.GetPositionZ(), false, false)')),
    ('route past the path point limit', 'walk', ' | PATHFIND_SHORT |', ' |'),
    ('body off the navmesh', 'walk', 'PATHFIND_NOT_USING_PATH | ', ''),
    ('ghost off the navmesh', 'walk', ' | PATHFIND_FARFROMPOLY_START', ''),
    ('ghost walk without progress', 'walk',
     'destination.distance(WorldPosition(destination.GetMapId(), end.x, end.y, end.z)) + 1.0f < remaining',
     'remaining >= 0.0f'),
    ('height search re-path', 'find', 'walkEnd.z, false, false, false, true)', 'walkEnd.z, false, false)'),
    ('old death and time travel limits', 'find',
     'sPlayerbotAIConfig.naturalProgression || (deadTime < 10 * MINUTE && dCount < 5)',
     'deadTime < 10 * MINUTE && dCount < 5'),
    ('old corpse reclaim death limit', 'reclaim',
     '!sPlayerbotAIConfig.naturalProgression && !botAI->HasGameClientMaster()', '!botAI->HasGameClientMaster()'),
    ('minimal corpse reclaim starvation', 'priority',
     '(sPlayerbotAIConfig.naturalProgression ? 1.0f : 0.0f)', '0.0f'),
    ('free repeated-death resurrection', 'find',
     '!sPlayerbotAIConfig.naturalProgression && !botAI->HasGameClientMaster()', '!botAI->HasGameClientMaster()'),
    ('inactive corpse teleport', 'find',
     '!sPlayerbotAIConfig.naturalProgression && !botAI->AllowActivity(ALL_ACTIVITY)', '!botAI->AllowActivity(ALL_ACTIVITY)'),
    ('core reclaim bypass', 'reclaim', 'bot->GetSession()->HandleReclaimCorpseOpcode(packet);',
     'bot->ResurrectPlayer(0.5f); bot->SpawnCorpseBones();'),
    ('native corpse cooldown', 'core',
     'corpse->GetGhostTime() + _player->GetCorpseReclaimDelay(corpse->GetType() == CORPSE_RESURRECTABLE_PVP)',
     'corpse->GetGhostTime()'),
    ('remote corpse trigger eligibility', 'useful',
     'bot->GetCorpse() || HasRemoteInstanceCorpse(bot)', 'bot->GetCorpse()'),
    ('SelfBot manual ghost movement', 'entrance', 'IsSelfBot(bot) || ', ''),
    ('portal physical arrival', 'find', 'if (!bot->IsInAreaTriggerRadius(entrance))', 'if (false)'),
    ('portal source coordinates', 'find', 'MoveTo(entrance->map, entrance->x, entrance->y, entrance->z, false, false)',
     'MoveTo(bot->GetCorpseLocation().GetMapId(), entrance->x, entrance->y, entrance->z, false, false)'),
    ('corpse wing selection', 'entrance', 'mapId == corpse.GetMapId()', 'false'),
    ('nested instance parent traversal', 'entrance', 'mapId = instance->Parent;', 'break;'),
    ('stale wrong-wing portal state', 'find', 'movement.lastAreaTrigger = 0;', '(void)movement;'),
)
with tempfile.TemporaryDirectory(prefix='portable-corpse-recovery-') as temporary:
    directory = Path(temporary)
    baseline = build(directory, 'fixture', production)
    assert baseline.returncode == 0, baseline.stdout + baseline.stderr
    print(baseline.stdout, end='')
    for index, (label, part, old, new) in enumerate(mutations):
        assert production[part].count(old) == 1, label
        changed = dict(production, **{part: production[part].replace(old, new)})
        rejected = build(directory, 'mutant-' + str(index), changed)
        assert rejected.returncode != 0, 'Unsafe corpse recovery survived: ' + label
        print('Corpse recovery mutation rejected:', label)
