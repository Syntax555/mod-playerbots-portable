#!/usr/bin/env python3
"""Exercise the production coordinator and real-path gates with native API doubles."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from PreparedSources import prepared_core

STUBS = r'''
#pragma once
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <map>
#include <memory>
#include <limits>
#include <set>
#include <shared_mutex>
#include <string>
#include <type_traits>
#include <vector>
using uint8=uint8_t;using uint32=uint32_t;using int32=int32_t;
constexpr uint32 MINUTE=60,HOUR=3600,IN_MILLISECONDS=1000,CMSG_AREATRIGGER=1,FORCED_MOVEMENT_NONE=0,MOTION_SLOT_ACTIVE=1,ESCORT_MOTION_TYPE=2,FOLLOW_MOTION_TYPE=3;
enum TeamId:uint8{TEAM_ALLIANCE=0,TEAM_HORDE=1,TEAM_NEUTRAL=2};
struct ObjectGuid{uint32 id=0;bool operator<(ObjectGuid r)const{return id<r.id;}bool operator==(ObjectGuid r)const{return id==r.id;}bool operator!=(ObjectGuid r)const{return id!=r.id;}std::string ToString()const{return std::to_string(id);}bool IsEmpty()const{return id==0;}uint32 GetCounter()const{return id;}static const ObjectGuid Empty;};const ObjectGuid ObjectGuid::Empty{};
struct Vec{float x=0,y=0,z=0;Vec()=default;Vec(float a,float b,float c):x(a),y(b),z(c){}Vec operator-(Vec b)const{return {x-b.x,y-b.y,z-b.z};}float squaredMagnitude()const{return x*x+y*y+z*z;}float magnitude()const{return std::sqrt(squaredMagnitude());}float GetPositionX()const{return x;}float GetPositionY()const{return y;}float GetPositionZ()const{return z;}};
using Position=Vec;
namespace G3D{using Vector3=Vec;}
namespace Movement{using PointsArray=std::vector<Vec>;}
enum PathType{PATHFIND_BLANK=0,PATHFIND_NORMAL=1,PATHFIND_SHORTCUT=2,PATHFIND_INCOMPLETE=4,PATHFIND_NOPATH=8,PATHFIND_NOT_USING_PATH=16,PATHFIND_SHORT=32,PATHFIND_FARFROMPOLY_START=64,PATHFIND_FARFROMPOLY_END=128,PATHFIND_FARFROMPOLY=192};
class Player;class PlayerbotAI;class Group;
struct AreaTriggerTeleport{uint32 target_mapId;float target_X=0,target_Y=0,target_Z=0,target_Orientation=0;};
struct AreaTrigger{uint32 entry=0,map=0;float x=0,y=0,z=0,radius=2;};
float fakeWaterX=std::numeric_limits<float>::infinity();
struct Map{enum EnterState{CAN_ENTER=0,CANNOT_ENTER_UNSPECIFIED_REASON=1};uint32 id=0,instance=0;bool heroic=false;bool IsRaid()const{return false;}bool IsHeroic()const{return heroic;}uint32 GetId()const{return id;}bool IsInWater(uint32,float x,float,float,float)const{return x>=fakeWaterX;}};
std::map<std::pair<uint32,uint32>,Map> maps;
struct WorldPacket{uint32 id=0;std::string name;WorldPacket(uint32=0){}WorldPacket& operator<<(uint32 n){id=n;return *this;}WorldPacket& operator<<(std::string n){name=n;return *this;}};
struct Session{Player* owner;bool headless=true;uint32 account=1;bool loading=false;bool IsHeadless()const{return headless;}uint32 GetAccountId()const{return account;}bool PlayerLoading()const{return loading;}void HandleGroupInviteOpcode(WorldPacket&);void HandleAreaTriggerOpcode(WorldPacket&);};
struct MotionMaster{Player* owner;Movement::PointsArray last;int splines=0;bool following=false;uint32 GetMotionSlotType(int){return following?FOLLOW_MOTION_TYPE:last.empty()?0:ESCORT_MOTION_TYPE;}void Clear(){last.clear();following=false;}void MoveSplinePath(Movement::PointsArray* p,uint32);};
struct GroupReference{Player* source;GroupReference* link=nullptr;Player* GetSource(){return source;}GroupReference* next(){return link;}};
class Group{public:ObjectGuid guid;Player* leader=nullptr;std::vector<Player*> players;std::vector<GroupReference> refs;struct MemberSlot{ObjectGuid guid;};std::vector<MemberSlot> slots;std::vector<MemberSlot> additionalSlots;bool raid=false;std::vector<MemberSlot> const& GetMemberSlots();bool isRaidGroup(){return raid;}ObjectGuid GetGUID(){return guid;}ObjectGuid GetLeaderGUID();uint32 GetMembersCount(){return players.size()+additionalSlots.size();}GroupReference* GetFirstMember(){refs.clear();for(Player* p:players)refs.push_back({p,nullptr});for(size_t i=0;i+1<refs.size();++i)refs[i].link=&refs[i+1];return refs.empty()?nullptr:&refs[0];}void RemoveMember(ObjectGuid);};
struct Event{std::string source,param;Player* owner=nullptr;Event(std::string s,std::string p="",Player* o=nullptr):source(s),param(p),owner(o){}std::string GetSource(){return source;}Player* getOwner(){return owner;}};
struct Run{bool enabled=false;};
struct ValueString{std::string str;std::string& Get(){return str;}};
struct Context{ValueString stall;template<class T>ValueString* GetValue(char const*){return &stall;}};
constexpr int BOT_STATE_NON_COMBAT=0;
class PlayerbotAI{public:Player* bot;Player* master=nullptr;bool humanMaster=false,accept=true,start=true;Run run;Context context;std::set<std::string> strategies{"new rpg","grind","follow","bg"};int started=0,reconciled=0,disabled=0;explicit PlayerbotAI(Player* p):bot(p){}bool HasGameClientMaster(){return humanMaster;}Player* GetMaster(){return master;}void SetMaster(Player* p){master=p;}bool HasStrategy(char const* n,int){return strategies.count(n);}void ChangeStrategy(std::string s,int){if(s[0]=='+')strategies.insert(s.substr(1));else strategies.erase(s.substr(1));}bool CanMove();bool DoSpecificAction(std::string,Event,bool);Context* GetAiObjectContext(){return &context;}static bool IsTank(Player*,bool);static bool IsHeal(Player*,bool);};
class Player{public:ObjectGuid guid;std::string name;uint8 level=25,tier=0,role=2;TeamId team=TEAM_ALLIANCE;bool world=true,alive=true,gm=false,combat=false,bg=false,queue=false,transfer=false,flying=false,cast=false,moving=false,doorRefused=false,pendingDoor=false,temporaryForm=false,rooted=false,vehicle=false,transport=false;uint8 rdf=0;int rewards=0,doorCalls=0;uint32 money=151,xp=90,items=7;bool dazed=true,progressionGate=false,cannotEnter=false,swimming=false;int immunityGrants=0,dazeRemoved=0,flagUpdates=0,entryChecks=0,gateChecks=0;Session session;MotionMaster motion;PlayerbotAI ai;Map* map=nullptr;Vec position;Group* group=nullptr;Group* invite=nullptr;explicit Player(uint32 id):guid{id},name("bot"+std::to_string(id)),session{this},motion{this,{},0},ai(this){}bool IsInWorld(){return world;}bool IsAlive(){return alive;}bool IsGameMaster(){return gm;}TeamId GetTeamId(){return team;}uint8 GetLevel(){return level;}bool InBattleground(){return bg;}bool InBattlegroundQueue(){return queue;}Session* GetSession(){return &session;}bool IsBeingTeleported(){return transfer;}bool IsInFlight(){return flying;}bool GetVehicle(){return vehicle;}bool GetTransport(){return transport;}bool IsInCombat(){return combat;}bool IsNonMeleeSpellCast(bool){return cast;}bool isMoving(){return moving;}float GetPositionX()const{return position.x;}float GetPositionY()const{return position.y;}float GetPositionZ()const{return position.z;}Map* GetMap(){return map;}uint32 GetMapId(){return map->id;}uint32 GetInstanceId(){return map->instance;}ObjectGuid GetGUID(){return guid;}Group* GetGroup(){return group;}Group* GetGroupInvite(){return invite;}std::string GetName(){return name;}float GetExactDist(float x,float y,float z){return (position-Vec{x,y,z}).magnitude();}float GetExactDist(Player* p){return (position-p->position).magnitude();}bool IsInAreaTriggerRadius(AreaTrigger const* a){return a->map==GetMapId()&&GetExactDist(a->x,a->y,a->z)<=a->radius;}Position GetFirstCollisionPosition(float dist,float angle){return {position.x+dist*std::cos(angle),position.y+dist*std::sin(angle),position.z};}MotionMaster* GetMotionMaster(){return &motion;}void UninviteFromGroup();void StopMoving(){moving=false;}void StopMovingOnCurrentPos(){moving=false;}void ApplySpellImmune(uint32,uint32,uint32,bool apply){if(apply)++immunityGrants;}void RemoveAurasDueToSpell(uint32){dazed=false;++dazeRemoved;}void AddItem(uint32,uint32){++rewards;}void SetRewardedQuest(uint32){++rewards;}void TeleportTo(uint32,float,float,float,float){++rewards;}void ResurrectPlayer(float){++rewards;}uint32 GetPhaseMask(){return 1;}float GetCollisionHeight(){return 2.0f;}bool SetSwim(bool on){if(on==swimming)return false;swimming=on;return true;}void SendMovementFlagUpdate(){++flagUpdates;}};
#define GET_PLAYERBOT_AI(p) (&(p)->ai)
ObjectGuid Group::GetLeaderGUID(){return leader->guid;}
std::vector<Group::MemberSlot> const& Group::GetMemberSlots(){slots.clear();for(auto* p:players)slots.push_back({p->GetGUID()});slots.insert(slots.end(),additionalSlots.begin(),additionalSlots.end());return slots;}
void Player::UninviteFromGroup(){invite=nullptr;}
void Group::RemoveMember(ObjectGuid guid){for(Player* p:players)if(p->guid==guid)p->group=nullptr;std::erase_if(players,[guid](Player* p){return p->guid==guid;});if(players.size()<2){for(Player* p:players)p->group=nullptr;players.clear();}else if(leader->guid==guid)leader=players.front();}
void MotionMaster::MoveSplinePath(Movement::PointsArray* p,uint32){last=*p;++splines;owner->moving=true;}
std::map<ObjectGuid,Player*> online;
template<class T>struct HashMapHolder{static std::shared_mutex* GetLock(){static std::shared_mutex mutex;return &mutex;}};
namespace ObjectAccessor{Player* FindConnectedPlayer(ObjectGuid g){auto it=online.find(g);return it==online.end()?nullptr:it->second;}auto const& GetPlayers(){return online;}}
std::vector<std::unique_ptr<Group>> groups;
struct GroupMgr{Group* GetGroupByGUID(uint32 guid){for(auto& g:groups)if(g&&g->guid.id==guid)return g.get();return nullptr;}};GroupMgr groupMgr;GroupMgr* sGroupMgr=&groupMgr;
void Session::HandleGroupInviteOpcode(WorldPacket& packet){Player* candidate=nullptr;for(auto const& [g,p]:online)if(p->name==packet.name)candidate=p;if(!candidate||candidate->group||candidate->invite)return;Group* grp=owner->group?owner->group:owner->invite;if(!grp){groups.push_back(std::make_unique<Group>());grp=groups.back().get();grp->guid={uint32(100+groups.size())};grp->leader=owner;owner->invite=grp;}candidate->invite=grp;}
bool PlayerbotAI::CanMove(){return !bot->rooted;}
bool PlayerbotAI::IsTank(Player* p,bool bySpec){return p->role==0&&(!bySpec||!p->temporaryForm);}bool PlayerbotAI::IsHeal(Player* p,bool){return p->role==1;}
bool PlayerbotAI::DoSpecificAction(std::string name,Event,bool){if(name=="accept invitation"){if(!accept||!bot->invite)return false;Group* g=bot->invite;if(g->players.empty()){g->players.push_back(g->leader);g->leader->group=g;g->leader->invite=nullptr;}g->players.push_back(bot);bot->group=g;bot->invite=nullptr;master=g->leader;strategies={"follow","new rpg","grind","bg"};return true;}if(name=="dc on"){++started;if(!start)return false;run.enabled=true;return true;}return false;}
struct ObjectMgr{std::map<uint32,AreaTrigger> triggers;AreaTrigger const* GetAreaTrigger(uint32 id){auto it=triggers.find(id);return it==triggers.end()?nullptr:&it->second;}std::map<uint32,AreaTriggerTeleport> targets;AreaTriggerTeleport const* GetAreaTriggerTeleport(uint32 id){auto it=targets.find(id);return it==targets.end()?nullptr:&it->second;}std::map<uint32,AreaTriggerTeleport> const& GetAllAreaTriggerTeleports(){return targets;}};
ObjectMgr objectMgr;ObjectMgr* sObjectMgr=&objectMgr;
bool IsContinentMap(uint32 map);
void Session::HandleAreaTriggerOpcode(WorldPacket& packet){auto* at=sObjectMgr->GetAreaTrigger(packet.id);assert(at&&owner->IsInAreaTriggerRadius(at));++owner->doorCalls;if(owner->doorRefused)return;uint32 origin=owner->GetMapId(),target=sObjectMgr->GetAreaTriggerTeleport(packet.id)->target_mapId;uint32 instance=IsContinentMap(target)?0:(owner->group?owner->group->guid.id:owner->guid.id);auto& destination=maps[{target,instance}];destination={target,instance,false};owner->map=&destination;AreaTrigger const* exit=nullptr;for(auto const& [id,tp]:sObjectMgr->GetAllAreaTriggerTeleports())if(tp.target_mapId==origin&&sObjectMgr->GetAreaTrigger(id)->map==target)exit=sObjectMgr->GetAreaTrigger(id);owner->position={exit->x+20,exit->y,exit->z};if(owner->pendingDoor){owner->transfer=true;owner->world=false;}owner->moving=false;}
uint32 fakeNow=0;uint32 getMSTime(){return fakeNow;}uint32 getMSTimeDiff(uint32 a,uint32 b){return b-a;}
struct PlayerbotAIConfig{bool naturalProgression=true;float sightDistance=45.0f;std::set<uint32> random{1};bool IsInRandomAccountList(uint32 id){return random.count(id);}};PlayerbotAIConfig sPlayerbotAIConfig;
struct IndividualProgression{bool enabled=true,strict=true;bool IsStrictDefaultProgression(){return enabled&&strict;}uint8 GetPlayerProgressionFromQuests(Player* p){return p->tier;}bool CanEnterMap(Player* p,uint32,float,float,float){++p->gateChecks;return !p->progressionGate;}};IndividualProgression ip;IndividualProgression* sIndividualProgression=&ip;
// NATIVE_PROGRESSION_ENUM
struct Config{std::map<std::string,uint32> settings{{"DungeonClear.AutonomousParties.Enable",1},{"DungeonClear.AutonomousParties.MaxConcurrent",2}};std::map<std::string,std::string> strings;template<class T>T GetOption(char const* name,T def){if constexpr(std::is_same_v<T,std::string>){auto it=strings.find(name);return it==strings.end()?def:it->second;}else{auto it=settings.find(name);return it==settings.end()?def:static_cast<T>(it->second);}}};Config config;Config* sConfigMgr=&config;
namespace lfg{constexpr uint8 LFG_STATE_NONE=0;constexpr uint32 LFG_TYPE_DUNGEON=1,LFG_FLAG_SEASONAL=4;struct LFGDungeonData{float x=0,y=0,z=0;};}struct LFGMgr{std::map<uint32,lfg::LFGDungeonData> starts;uint8 GetState(ObjectGuid guid){return ObjectAccessor::FindConnectedPlayer(guid)->rdf;}lfg::LFGDungeonData const* GetLFGDungeon(uint32 id){auto it=starts.find(id);return it==starts.end()?nullptr:&it->second;}};
// World data doubles: Dungeon Finder rows, maps, capital zones and the zone of a position.
template<class T>struct Store{std::map<uint32,T> rows;T const* LookupEntry(uint32 id){auto it=rows.find(id);return it==rows.end()?nullptr:&it->second;}};
struct LFGDungeonEntry{uint32 ID,MinLevel,MaxLevel,TargetLevel,TargetLevelMin,TargetLevelMax,MapID,Difficulty,Flags,TypeID,ExpansionLevel;};Store<LFGDungeonEntry> sLFGDungeonStore;
struct MapEntry{uint32 id;bool instance,continent;bool IsNonRaidDungeon()const{return instance;}bool IsContinent()const{return continent;}};Store<MapEntry> sMapStore;
bool IsContinentMap(uint32 map){auto* row=sMapStore.LookupEntry(map);return row&&row->IsContinent();}
struct AreaTableEntry{uint32 ID,flags,team;};Store<AreaTableEntry> sAreaTableStore;constexpr uint32 AREA_FLAG_CAPITAL=0x100,AREATEAM_ALLY=2,AREATEAM_HORDE=4,PHASEMASK_NORMAL=1,DUNGEON_DIFFICULTY_NORMAL=0;
struct MapMgr{std::map<std::pair<uint32,int>,uint32> zones;uint32 GetZoneId(uint32,uint32 map,float x,float,float){auto it=zones.find({map,int(x)/100});return it==zones.end()?0:it->second;}Map::EnterState PlayerCannotEnter(uint32,Player* p,bool login){assert(!login);++p->entryChecks;return p->cannotEnter?Map::CANNOT_ENTER_UNSPECIFIED_REASON:Map::CAN_ENTER;}};MapMgr mapMgr;MapMgr* sMapMgr=&mapMgr;
// Teleport hooks act on their player, e.g. Dungeon Clear ends a spectate; recruitment never fires them.
struct ScriptMgr{bool OnPlayerBeforeTeleport(Player*,uint32,float,float,float,float,uint32,void*){assert(!"recruitment fired a teleport hook");return false;}};ScriptMgr scriptMgr;ScriptMgr* sScriptMgr=&scriptMgr;
namespace DcEarnedEvents{std::set<uint32> unaudited;bool MapAudited(uint32 map,std::string& reason){if(!unaudited.count(map))return true;reason="fixture objective requires a shortcut";return false;}}LFGMgr lfgManager;LFGMgr* sLFGMgr=&lfgManager;
uint32 fakePathType=PATHFIND_NORMAL;bool fakePathBuild=true,fakeRaycastBlocked=false,fakeDiagonalWall=false;float fakeWallX=std::numeric_limits<float>::infinity(),fakeMissingTileX=std::numeric_limits<float>::infinity();
class PathGenerator{
 Player* owner;Movement::PointsArray points;Vec actualEnd;bool raycast=false,blocked=false,missingTile=false;
 public:explicit PathGenerator(Player* p):owner(p){}void SetUseRaycast(bool on){raycast=on;}
 bool CalculatePath(float x,float y,float z,bool force){return CalculatePath(owner->position.x,owner->position.y,owner->position.z,x,y,z,force);}
 bool CalculatePath(float ax,float ay,float az,float bx,float by,float bz,bool force){assert(!force);actualEnd={bx,by,bz};points={{ax,ay,az},actualEnd};missingTile=!raycast&&bx>=fakeMissingTileX;blocked=raycast&&(fakeRaycastBlocked||(ax<fakeWallX&&bx>=fakeWallX)||(fakeDiagonalWall&&std::abs(ax-bx)>0.05f&&std::abs(ay-by)>0.05f));if(blocked)points.back()={ax+(bx-ax)/2,ay+(by-ay)/2,az+(bz-az)/2};return fakePathBuild;}
 PathType GetPathType()const{return PathType(blocked?uint32(PATHFIND_INCOMPLETE):missingTile?uint32(PATHFIND_NORMAL|PATHFIND_NOT_USING_PATH):fakePathType);}Movement::PointsArray const& GetPath()const{return points;}
 // Native early raycast wall return leaves this requested endpoint unchanged.
 Vec const& GetActualEndPosition()const{return actualEnd;}
};
constexpr uint32 IMMUNITY_MECHANIC=1,MECHANIC_DAZE=2;
class DcLeaderSignal{public:static void SetLeaderDazeImmunity(Player*,bool);};
struct LootRollAction{int usefulCalls=0,executeCalls=0;bool isUseful(){++usefulCalls;return true;}bool Execute(Event){++executeCalls;return true;}};
struct DungeonClearBetterLootRollAction:LootRollAction{Player* bot;bool isUseful();};
namespace DcPlayerbotCompat{bool IsSelfBot(Player* p){return !p->GetSession()->IsHeadless();}}
int nativeFollowCalls=0,guardedFollowCalls=0;bool DcMoveTo(uint32,float,float,float,bool,bool,bool normal,bool exact){assert(normal&&!exact);++guardedFollowCalls;return true;}bool Follow(Player*,float,float){++nativeFollowCalls;return true;}
namespace DcSettings{bool betterLoot=true;bool GetBool(Player*,char const*){return betterLoot;}}

namespace DcModule{bool IsEnabled(){return true;}}
namespace DcRun{Run& Of(PlayerbotAI* ai){return ai->run;}}
namespace DcKey{constexpr char const* StallReason="stall";}
namespace DcActionShared{void DisableDungeonClear(PlayerbotAI* ai,char const*){ai->run.enabled=false;++ai->disabled;}}
namespace DcStrategyGate{void Reconcile(Player* p){++p->ai.reconciled;}}
namespace DcRunWing{std::string FenceWing(Player*){return {};}}
namespace DcNavPenaltyRegistry{bool HasVolumes(uint32,std::string const&){return false;}bool IsInsideRegion(uint32,float,float,float,std::string const&){return false;}}
size_t LosCleanPrefixCount(Player*,std::vector<Vec> const& points){return points.size();}
#define LOG_DEBUG(...) ((void)0)
#define LOG_INFO(...) ((void)0)
'''

HARNESS = r'''
#include "Ai/Dungeon/DungeonClear/Util/ChunkedPathfinder.h"
// Keep the producer contract native, but control its upstream fallback outputs:
// reachable also covers missing-mmap chords and hand-tuned anchors.
ChunkedPathfinder::Result fakeChunkedResult;
bool fakeChunkedCustom=false;
uint32 fakeChunkedCalls=0,fakePlannerMap=0,fakePlannerBoss=999,fakePlannerBudget=0;
ChunkedPathfinder::Result ChunkedPathfinder::Build(Player* p,uint32 map,uint32 boss,float x,float y,float z,uint32 depth){
 ++fakeChunkedCalls;fakePlannerMap=map;fakePlannerBoss=boss;fakePlannerBudget=depth;
 if(fakeChunkedCustom)return fakeChunkedResult;
 Result result;result.reachable=true;result.complete=true;Vec const target{x,y,z};float const distance=(target-p->position).magnitude();
 if(distance<=8.0f)return result;
 PathSegment segment;segment.ex=x;segment.ey=y;segment.ez=z;
 uint32 const count=uint32(std::ceil(distance/5.0f));
 for(uint32 i=1;i<=count;++i){float const f=float(i)/count;segment.polyline.push_back({p->position.x+(x-p->position.x)*f,p->position.y+(y-p->position.y)*f,p->position.z+(z-p->position.z)*f});}
 result.segments.push_back(segment);return result;
}
#include "DcEarnedProgression.cpp"
#include "EarnedDungeonParties.cpp"
#include "NativeProductionMethods.h"
#include <iostream>
std::vector<std::unique_ptr<Player>> actors;
// One coordinator tick's corridor budget, then a direct walk of member 0.
std::array<WalkState,5> walks;
bool walkOnce(Player* p,uint32 trigger){buildBudget=buildsPerTick;return Walk(p,trigger,walks,0)==Travel::Moving;}
void reset(){parties.clear();retryAfter.clear();refusals.clear();walks={};fakeWaterX=std::numeric_limits<float>::infinity();online.clear();groups.clear();actors.clear();maps.clear();fakeNow=0;accumulator=0;recruitAccumulator=0;fakePathType=PATHFIND_NORMAL;fakePathBuild=true;fakeRaycastBlocked=false;fakeDiagonalWall=false;fakeWallX=fakeMissingTileX=std::numeric_limits<float>::infinity();fakeChunkedCustom=false;fakeChunkedResult={};fakeChunkedCalls=0;sPlayerbotAIConfig.sightDistance=45.0f;ip.enabled=true;ip.strict=true;sPlayerbotAIConfig.naturalProgression=true;config.settings["DungeonClear.AutonomousParties.Enable"]=1;config.settings["DungeonClear.AutonomousParties.MaxConcurrent"]=2;config.settings.erase("DungeonClear.AutonomousParties.LevelSpread");config.strings["DungeonClear.AutonomousParties.Dungeons"]="4,12";objectMgr.triggers={{101,{101,0,0,0,0,2}},{503,{503,34,10,0,0,2}},{2230,{2230,1,0,0,0,2}},{2226,{2226,389,10,0,0,2}}};objectMgr.targets={{101,{34,10,0,0}},{503,{0}},{2230,{389,10,0,0}},{2226,{1}}};
 // Dungeon Finder rows: Ragefire Chasm 15-21 (target 15-16), Stockade 20-30 (target 22-25).
 sLFGDungeonStore.rows={{4,{4,15,21,16,15,16,389,0,3,1,0}},{12,{12,20,30,24,22,25,34,0,3,1,0}}};lfgManager.starts={{4,{10,0,0}},{12,{10,0,0}}};
 sMapStore.rows={{0,{0,false,true}},{1,{1,false,true}},{34,{34,true,false}},{389,{389,true,false}}};
 sAreaTableStore.rows={{1519,{1519,0x100,AREATEAM_ALLY}},{1637,{1637,0x100,AREATEAM_HORDE}},{40,{40,0,AREATEAM_ALLY}},{17,{17,0,AREATEAM_HORDE}}};mapMgr.zones={{{0,0},1519},{{1,0},1637}};
 DcEarnedEvents::unaudited.clear();EarnedDungeonParties::LoadConfig();}
Route const* route(uint32 dungeon){for(auto const& r:routes)if(r.dungeon==dungeon)return &r;return nullptr;}
Player* add(uint32 id,uint8 role,TeamId team=TEAM_ALLIANCE,uint8 level=25){actors.push_back(std::make_unique<Player>(id));auto* p=actors.back().get();p->role=role;p->team=team;p->level=level;auto& map=maps[{team==TEAM_ALLIANCE?0u:1u,0}];map={team==TEAM_ALLIANCE?0u:1u,0,false};p->map=&map;p->position={100+float(id%5),0,0};online[p->guid]=p;return p;}
void five(uint32 first=1,TeamId team=TEAM_ALLIANCE,uint8 level=25){add(first,0,team,level);add(first+1,1,team,level);for(uint32 i=2;i<5;++i)add(first+i,2,team,level);}
void tick(int count=1){for(int i=0;i<count;++i){fakeNow+=1000;EarnedDungeonParties::Update(1000);}}
void walkToPortal(bool entering){for(auto& p:actors){if(p->transfer)continue;if(entering&&(p->GetMapId()==34||p->GetMapId()==389))continue;if(!entering&&(p->GetMapId()==0||p->GetMapId()==1))continue;uint32 id=entering?(p->team==TEAM_ALLIANCE?101:2230):(p->team==TEAM_ALLIANCE?503:2226);auto* at=objectMgr.GetAreaTrigger(id);p->position={at->x,at->y,at->z};p->moving=false;}}
void unchanged(){for(auto const& p:actors)assert(p->rewards==0&&p->money==151&&p->xp==90&&p->items==7&&p->immunityGrants==0&&p->dazeRemoved==0);}
// Explicit world-data scenarios: the outdoor map never defines a dungeon's era.
void expansionRoute(uint32 dungeon,uint32 instance,uint32 outside,uint8 expansion,uint8 recommended,uint8 targetMax,uint8 entryMax=83){
 sLFGDungeonStore.rows[dungeon]={dungeon,recommended,entryMax,targetMax,recommended,targetMax,instance,0,3,1,expansion};
 sMapStore.rows[outside]={outside,false,true};sMapStore.rows[instance]={instance,true,false};
 objectMgr.triggers[7000]={7000,outside,500,0,0,2};objectMgr.triggers[7001]={7001,instance,10,0,0,2};
 objectMgr.targets[7000]={instance,10,0,0};objectMgr.targets[7001]={outside};lfgManager.starts[dungeon]={10,0,0};
 config.strings["DungeonClear.AutonomousParties.Dungeons"]=std::to_string(dungeon);EarnedDungeonParties::LoadConfig();
}
void expansionBots(uint32 outside,uint8 tier,uint8 level){
 five(1,TEAM_ALLIANCE,level);auto& map=maps[{outside,0}];map={outside,0,false};
 for(auto& p:actors){p->map=&map;p->tier=tier;p->position={600+float(p->guid.id%5),0,0};}
}
void expansionPortal(uint32 trigger){auto* at=objectMgr.GetAreaTrigger(trigger);assert(at);for(auto& p:actors){assert(p->GetMapId()==at->map);p->position={at->x,at->y,at->z};p->moving=false;}}
int main(){
 reset();five();tick(30);assert(parties.size()==1);for(auto& p:actors)assert(p->group&&p->ai.started==0);
 tick();for(auto& p:actors)assert(p->motion.splines==1&&p->doorCalls==0);walkToPortal(true);
 actors[4]->pendingDoor=true;tick();assert(parties.size()==1&&actors[0]->ai.started==0);tick();assert(parties.size()==1&&actors[0]->ai.started==0);
 actors[4]->transfer=false;actors[4]->world=true;actors[4]->pendingDoor=false;tick();assert(actors[0]->ai.started==1&&actors[0]->ai.run.enabled);for(auto& p:actors)assert(p->doorCalls==1&&p->ai.reconciled==1);unchanged();
 actors[0]->ai.run.enabled=false;tick();tick();walkToPortal(false);tick();tick();assert(parties.empty());for(auto& p:actors)assert(!p->group&&!p->ai.master&&p->doorCalls==2&&p->ai.HasStrategy("new rpg",0));unchanged();
 // Only eligible nearby earned random bots form a 1/1/3 party.
 for(int bad=0;bad<22;++bad){reset();five();Player* p=actors[4].get();switch(bad){case 0:p->session.headless=false;break;case 1:p->ai.humanMaster=true;break;case 2:p->ai.master=actors[3].get();break;case 3:p->tier=8;break;case 4:p->alive=false;break;case 5:p->gm=true;break;case 6:p->level=21;break;case 7:p->level=29;break;case 8:p->position.x=200;break;case 9:p->combat=true;break;case 10:p->session.account=900;break;case 11:p->rdf=2;break;case 12:p->team=TEAM_HORDE;break;case 13:p->role=1;break;case 14:p->world=false;break;case 15:p->vehicle=true;break;case 16:p->transport=true;break;case 17:p->transfer=true;break;case 18:p->flying=true;break;case 19:p->queue=true;break;case 20:p->session.loading=true;break;case 21:p->bg=true;break;}tick(30);assert(parties.empty());unchanged();}
 // Normal invitation security remains authoritative, and failed setup does not force add members.
 reset();five();actors[2]->ai.accept=false;tick(30);assert(parties.empty());for(auto& p:actors)assert(!p->group&&!p->invite);unchanged();
 // No navigation data/straight shortcut/snap across missing mesh can transport a party.
 for(uint32 path:{uint32(PATHFIND_NOPATH),uint32(PATHFIND_NORMAL|PATHFIND_NOT_USING_PATH),uint32(PATHFIND_SHORTCUT),uint32(PATHFIND_FARFROMPOLY),uint32(PATHFIND_BLANK)}){reset();five();tick(30);fakePathType=path;tick();assert(parties.empty());for(auto& p:actors)assert(p->motion.splines==0&&p->doorCalls==0);unchanged();}
 reset();five();tick(30);fakePathBuild=false;tick();assert(parties.empty());unchanged();
 // Disconnect/wipe stops the run without reviving or changing loot/quests.
 reset();five();tick(30);actors[3]->alive=false;tick();assert(parties.empty());for(auto& p:actors)assert(!p->group);unchanged();
 reset();five();tick(30);online.erase(actors[3]->guid);tick();assert(parties.empty());unchanged();
 // A player claiming a member keeps their party: the coordinator must not disband it.
 reset();five();tick(30);Group* owned=actors[0]->group;actors[0]->ai.strategies.insert("rpg");actors[4]->session.headless=false;actors[4]->ai.humanMaster=true;tick();assert(parties.empty()&&actors[4]->group==owned&&actors[0]->ai.HasStrategy("rpg",0));unchanged();
 // Wrong instance copies, refused portals and unsupported IP profiles stay bounded.
 reset();five();tick(30);walkToPortal(true);tick();actors[4]->map=&maps[{34,999}];maps[{34,999}]={34,999,false};tick();assert(parties.empty());unchanged();
 // A refused portal stops the attempt at once and keeps that bot out of the
 // dungeon until its level or earned progression changes.
 reset();five();tick(30);actors[0]->doorRefused=true;walkToPortal(true);tick();assert(parties.empty()&&actors[0]->doorCalls==1);for(auto& p:actors)assert(!p->group);
 tick(15*60+30);assert(parties.empty());actors[0]->doorRefused=false;actors[0]->level=26;tick(30);assert(parties.size()==1);unchanged();
 // The portal's own checks are asked before recruiting, without a teleport: an
 // Individual Progression map gate or a core entry refusal keeps the bot out.
 for(int gate=0;gate<2;++gate){reset();five();(gate?actors[3]->cannotEnter:actors[3]->progressionGate)=true;tick(30);assert(parties.empty()&&actors[3]->gateChecks==1&&actors[3]->entryChecks==(gate?1:0));for(auto& p:actors)assert(!p->group&&!p->invite);unchanged();}
 reset();five();tick(30);assert(parties.size()==1);for(auto& p:actors)assert(p->gateChecks>=1&&p->entryChecks>=1);unchanged();
 reset();five();ip.strict=false;tick(31);assert(parties.empty());
 reset();five();ip.enabled=false;tick(31);assert(parties.empty());
 reset();five();sPlayerbotAIConfig.naturalProgression=false;tick(31);assert(parties.empty());
 // Both factions use audited native entrances; max concurrent bounds the active workload.
 reset();five();five(6,TEAM_HORDE,17);five(11,TEAM_ALLIANCE,25);tick(90);assert(parties.size()==2);unchanged();
 // Internal start is never authorized for client-like fabricated events outside dispatch.
 assert(!EarnedDungeonParties::AuthorizeInternalStart(actors[0].get(),Event("earned dungeon party","",actors[0].get())));
 // Native spline guards reject missing mesh/fabricated endpoint segments.
 fakePathType=PATHFIND_NORMAL;auto* walker=actors[0].get();Movement::PointsArray points{walker->position,Vec{walker->position.x+5,0,0}};assert(DcEarnedPlay::RealSpline(walker,points));fakePathType=PATHFIND_NORMAL|PATHFIND_NOT_USING_PATH;assert(!DcEarnedPlay::RealSpline(walker,points));
 // A reachable detour cannot authorize a raw spline through a wall. Native
 // GetActualEndPosition stays at the request on the early blocked raycast return.
 fakePathType=PATHFIND_NORMAL;fakeRaycastBlocked=true;assert(!DcEarnedPlay::RealSpline(walker,points));
 fakeRaycastBlocked=false;points.front().x+=1;assert(!DcEarnedPlay::RealSpline(walker,points));
 // Invitations reset navigation; cleanup restores each pre-recruit baseline.
 reset();five();actors[2]->ai.strategies={"travel","rpg"};tick(30);tick();for(auto& p:actors)p->moving=false;fakePathBuild=false;tick();assert(parties.empty());assert(actors[2]->ai.strategies==std::set<std::string>({"travel","rpg"}));for(auto& p:actors)assert(p->motion.last.empty());unchanged();
 // An invitation refusal must leave untouched candidates' original movement.
 reset();five();actors[1]->ai.accept=false;actors[4]->moving=true;tick(30);assert(parties.empty()&&actors[4]->moving);for(auto& p:actors)assert(!p->invite&&!p->group);unchanged();
 // A newly claimed tank keeps its run and movement; cleanup cannot disable it.
 reset();five();tick(30);walkToPortal(true);tick();tick();auto* tank=actors[0].get();tank->ai.humanMaster=true;int stopped=tank->ai.disabled;tick();assert(parties.empty()&&tank->ai.run.enabled&&tank->ai.disabled==stopped);unchanged();
 // A third-party offline group slot also invalidates ownership preflight.
 reset();five();tick(30);actors[0]->group->additionalSlots.push_back({{999}});actors[4]->alive=false;tick();assert(parties.empty());for(auto& p:actors)assert(p->group);unchanged();
 // Wipes inside preserve native groups rather than start homebind teleports.
 reset();five();tick(30);walkToPortal(true);tick();tick();actors[4]->alive=false;tick();assert(parties.empty());for(auto& p:actors)assert(p->group&&p->doorCalls==1);assert(!actors[0]->ai.run.enabled);unchanged();
 // Ordinary earned XP and temporary druid forms do not abort a valid run.
 reset();five();tick(30);walkToPortal(true);tick();tick();actors[4]->level=29;actors[0]->temporaryForm=true;tick();assert(parties.size()==1&&actors[0]->ai.run.enabled);unchanged();
 // An earned era change during travel is evaluated before the portal or start.
 reset();five();tick(30);actors[4]->tier=8;walkToPortal(true);tick();assert(parties.empty());for(auto& p:actors)assert(p->doorCalls==0);unchanged();
 // Native crowd control pauses foot movement until normal control returns.
 reset();five();tick(30);for(auto& p:actors)p->rooted=true;tick();for(auto& p:actors)assert(p->motion.splines==0);for(auto& p:actors)p->rooted=false;tick();for(auto& p:actors)assert(p->motion.splines==1);unchanged();
 // Nearby recruitment stays below the native invitation summon threshold.
 reset();five();actors[4]->position.x=actors[0]->position.x+50;tick(30);assert(parties.empty());unchanged();
 // Reloading autonomy stops owned travel; global concurrency is bounded.
 reset();five();tick(30);config.settings["DungeonClear.AutonomousParties.Enable"]=0;EarnedDungeonParties::LoadConfig();tick();assert(parties.empty());for(auto& p:actors)assert(!p->group);unchanged();
 reset();config.settings["DungeonClear.AutonomousParties.MaxConcurrent"]=0;EarnedDungeonParties::LoadConfig();assert(maxConcurrent==1);config.settings["DungeonClear.AutonomousParties.MaxConcurrent"]=99;EarnedDungeonParties::LoadConfig();assert(maxConcurrent==8);
 // Custom/missing portal targets cannot start a journey to another instance.
 reset();five();objectMgr.targets[101].target_mapId=529;tick(30);assert(parties.empty());
 reset();five();objectMgr.targets.erase(503);tick(30);assert(parties.empty());
 // Incomplete/short paths are safe for generated walking, but unsafe for a raw spline.
 reset();five();walker=actors[0].get();points={walker->position,Vec{walker->position.x+5,0,0}};
 for(uint32 type:{uint32(PATHFIND_INCOMPLETE),uint32(PATHFIND_NORMAL|PATHFIND_SHORT)}){fakePathType=type;assert(!DcEarnedPlay::RealSpline(walker,points));}
 // Ordinary follower fallback issues guarded points rather than a persistent
 // independently replanning raw MoveFollow generator under natural progression.
 nativeFollowCalls=guardedFollowCalls=0;walker->motion.following=true;assert(NativeFollowFallback(walker,walker,3.0f,0.5f));assert(nativeFollowCalls==0&&guardedFollowCalls==1&&!walker->motion.following);
 sPlayerbotAIConfig.naturalProgression=false;assert(NativeFollowFallback(walker,walker,3.0f,0.5f));assert(nativeFollowCalls==1&&guardedFollowCalls==1);sPlayerbotAIConfig.naturalProgression=true;
 // Native DC daze and custom loot hooks must retain ordinary player penalties.
 fakePathType=PATHFIND_NORMAL;DcLeaderSignal::SetLeaderDazeImmunity(walker,true);assert(walker->dazed&&walker->immunityGrants==0&&walker->dazeRemoved==0);
 DungeonClearBetterLootRollAction loot;loot.bot=walker;walker->session.headless=false;assert(loot.isUseful()&&loot.usefulCalls==1);
 sPlayerbotAIConfig.naturalProgression=false;assert(!loot.isUseful());walker->session.headless=true;DcLeaderSignal::SetLeaderDazeImmunity(walker,true);assert(walker->immunityGrants==1&&walker->dazeRemoved==1);

 // Routes come from the world data: portals, Dungeon Finder target bands widened by the
 // spread within entry levels and level 60, and the capital faction of the entrance.
 reset();tick();assert(routes.size()==2);
 {auto* rfc=route(4);auto* sw=route(12);assert(rfc&&rfc->map==389&&rfc->continent==1&&rfc->entrance==2230&&rfc->exit==2226&&rfc->team==TEAM_HORDE&&rfc->minLevel==15&&rfc->maxLevel==19);
  assert(sw&&sw->map==34&&sw->continent==0&&sw->entrance==101&&sw->exit==503&&sw->team==TEAM_ALLIANCE&&sw->minLevel==22&&sw->maxLevel==28);
  assert(EarnedDungeonParties::RouteEnabled(389)&&EarnedDungeonParties::RouteEnabled(34)&&!EarnedDungeonParties::RouteEnabled(36));}
 for(uint8 level:{22,28}){reset();five(1,TEAM_ALLIANCE,level);tick(30);assert(parties.size()==1);unchanged();}
 for(uint8 level:{21,29}){reset();five(1,TEAM_ALLIANCE,level);tick(30);assert(parties.empty());unchanged();}
 reset();config.settings["DungeonClear.AutonomousParties.LevelSpread"]=0;EarnedDungeonParties::LoadConfig();tick();assert(route(4)->maxLevel==16&&route(12)->maxLevel==25);
 reset();config.settings["DungeonClear.AutonomousParties.LevelSpread"]=99;EarnedDungeonParties::LoadConfig();tick();assert(route(4)->maxLevel==21&&route(12)->maxLevel==30);
 // A level-60 dungeon never admits a band above the Vanilla cap.
 reset();sLFGDungeonStore.rows[40]={40,55,65,60,0,0,329,0,3,1,0};sMapStore.rows[329]={329,true,false};objectMgr.triggers[2216]={2216,0,1000,0,0,2};objectMgr.triggers[2221]={2221,329,10,0,0,2};objectMgr.targets[2216]={329,10,0,0};objectMgr.targets[2221]={0};config.strings["DungeonClear.AutonomousParties.Dungeons"]="40";EarnedDungeonParties::LoadConfig();tick();assert(route(40)&&route(40)->minLevel==60&&route(40)->maxLevel==60&&route(40)->team==TEAM_NEUTRAL);
 // Unknown, unsupported expansion, heroic, raid or seasonal rows, duplicates and unaudited maps stay disabled.
 reset();sLFGDungeonStore.rows[77]={77,58,68,62,61,63,543,0,3,1,3};sLFGDungeonStore.rows[78]={78,15,21,16,15,16,389,0,7,1,0};sLFGDungeonStore.rows[79]={79,60,83,60,60,63,409,0,0,2,0};
 config.strings["DungeonClear.AutonomousParties.Dungeons"]=" 4, 999,77,78,79,4,x,12";EarnedDungeonParties::LoadConfig();DcEarnedEvents::unaudited.insert(34);tick();assert(routes.size()==1&&route(4)&&!route(12)&&!EarnedDungeonParties::RouteEnabled(34));
 five();five(6,TEAM_HORDE,17);tick(30);assert(parties.size()==1&&parties[0].route.map==389);unchanged();
 // A dungeon outside the capitals admits either faction, but never a mixed party.
 auto neutral=[]{sLFGDungeonStore.rows[16]={16,22,32,26,24,27,47,0,3,1,0};sMapStore.rows[47]={47,true,false};objectMgr.triggers[244]={244,1,500,0,0,2};objectMgr.triggers[242]={242,47,10,0,0,2};objectMgr.targets[244]={47,10,0,0};objectMgr.targets[242]={1};mapMgr.zones[{1,5}]=17;lfgManager.starts[16]={10,0,0};config.strings["DungeonClear.AutonomousParties.Dungeons"]="16";EarnedDungeonParties::LoadConfig();};
 auto onBarrens=[](uint32 first,TeamId team){for(uint32 id=first;id<first+5;++id){auto* p=online[ObjectGuid{id}];auto& map=maps[{1,0}];map={1,0,false};p->map=&map;p->team=team;p->position={500+float(id%5),0,0};}};
 reset();neutral();five(1,TEAM_ALLIANCE,25);onBarrens(1,TEAM_ALLIANCE);tick(30);assert(route(16)->team==TEAM_NEUTRAL&&parties.size()==1);unchanged();
 reset();neutral();five(1,TEAM_HORDE,25);onBarrens(1,TEAM_HORDE);tick(30);assert(parties.size()==1);unchanged();
 reset();neutral();five(1,TEAM_ALLIANCE,25);onBarrens(1,TEAM_ALLIANCE);actors[1]->team=TEAM_HORDE;tick(30);assert(parties.empty());unchanged();
 // Wings sharing a map use the portal arriving nearest their own start and its nearest exit.
 reset();sLFGDungeonStore.rows[18]={18,27,37,31,29,32,189,0,3,1,0};sLFGDungeonStore.rows[165]={165,30,40,34,32,35,189,0,3,1,0};sMapStore.rows[189]={189,true,false};
 lfgManager.starts[18]={100,0,0};lfgManager.starts[165]={900,0,0};objectMgr.triggers[45]={45,0,600,0,0,2};objectMgr.triggers[614]={614,0,610,0,0,2};objectMgr.targets[45]={189,105,0,0};objectMgr.targets[614]={189,905,0,0};
 objectMgr.triggers[602]={602,189,100,0,0,2};objectMgr.triggers[608]={608,189,900,0,0,2};objectMgr.targets[602]={0};objectMgr.targets[608]={0};mapMgr.zones[{0,6}]=40;
 config.strings["DungeonClear.AutonomousParties.Dungeons"]="18,165";EarnedDungeonParties::LoadConfig();tick();assert(route(18)->entrance==45&&route(18)->exit==602&&route(165)->entrance==614&&route(165)->exit==608&&route(18)->team==TEAM_NEUTRAL);
 // Recruitment rotates through the enabled routes rather than always serving the first.
 reset();config.settings["DungeonClear.AutonomousParties.MaxConcurrent"]=1;EarnedDungeonParties::LoadConfig();five(1,TEAM_ALLIANCE,25);five(6,TEAM_HORDE,17);tick(30);assert(parties.size()==1);uint32 firstMap=parties[0].route.map;parties[0].members={};parties.clear();for(auto& p:actors){p->group=nullptr;p->invite=nullptr;}retryAfter.clear();tick(30);assert(parties.size()==1&&parties[0].route.map!=firstMap);
 // A clear stalled on an objective nobody performs ends after five minutes; progress resets it.
 reset();five();tick(30);walkToPortal(true);tick();tick();assert(actors[0]->ai.run.enabled);actors[0]->ai.context.stall.str="I can't progress the event at Fixture on my own.";tick(200);actors[0]->ai.context.stall.str.clear();tick();actors[0]->ai.context.stall.str="Way blocked";tick(300);assert(parties.size()==1);tick(2);assert(parties.empty()&&!actors[0]->ai.run.enabled);for(auto& p:actors)assert(p->group);unchanged();
 // Compile the production progression bridge with the pinned native stage enum.
 // Neither account ownership nor level influences these rewarded-marker boundaries.
 reset();auto* eraBot=add(1,2);
 for(auto [tier,expansion]:std::vector<std::pair<uint8,uint8>>{{0,0},{7,0},{8,1},{11,1},{12,1},{13,2},{18,2},{19,3},{255,3}}){eraBot->tier=tier;assert(DcEarnedProgression::Expansion(eraBot)==expansion);}
 // A complete native portal journey works on Outland, Northrend, and Kalimdor
 // for expansion dungeons. Exit maps 530/571 are continents, never instance copies.
 struct EraCase{uint32 dungeon,instance,outside;uint8 expansion,tier,level;};
 std::vector<EraCase> const eraCases{{136,543,530,1,8,62},{202,574,571,2,13,72},{170,560,1,1,12,66},{209,595,1,2,18,78}};
 for(EraCase const& c:eraCases){
  reset();expansionRoute(c.dungeon,c.instance,c.outside,c.expansion,c.level,c.level);expansionBots(c.outside,c.tier,c.level);tick(30);
  assert(routes.size()==1&&route(c.dungeon)->expansion==c.expansion&&route(c.dungeon)->continent==c.outside&&parties.size()==1);
  tick();for(auto& p:actors)assert(p->motion.splines==1&&p->doorCalls==0);expansionPortal(7000);tick();tick();
  assert(parties.size()==1&&actors[0]->ai.run.enabled&&actors[0]->ai.started==1);
  for(auto& p:actors)assert(p->GetMapId()==c.instance&&p->GetInstanceId()==actors[0]->group->guid.id&&p->doorCalls==1);
  actors[0]->ai.run.enabled=false;tick();tick();expansionPortal(7001);tick();tick();assert(parties.empty());
  for(auto& p:actors){assert(p->GetMapId()==c.outside&&p->GetInstanceId()==0&&p->doorCalls==2&&!p->group&&!p->ai.master&&p->ai.HasStrategy("new rpg",0));}unchanged();
 }
 // Every member must independently match the dungeon era. A higher-era tank,
 // earlier-era companion, legacy high level or invalid marker cannot unlock it.
 for(EraCase const& c:eraCases){
  for(uint8 badTier:{uint8(0),uint8(7),uint8(8),uint8(12),uint8(13),uint8(18),uint8(19),uint8(255)}){
   uint8 const expected=badTier>18?3:badTier>=13?2:badTier>=8?1:0;if(expected==c.expansion)continue;
   for(size_t member:{size_t(0),size_t(4)}){reset();expansionRoute(c.dungeon,c.instance,c.outside,c.expansion,c.level,c.level);expansionBots(c.outside,c.tier,c.level);actors[member]->tier=badTier;tick(30);assert(parties.empty());for(auto& p:actors)assert(!p->group&&p->doorCalls==0);unchanged();}
  }
 }
 // Discovery and active runs use the earned era cap. Normal XP within that
 // cap remains valid after exceeding the original recruitment band.
 for(uint8 expansion:{uint8(0),uint8(1),uint8(2)}){
  uint8 const cap=expansion==0?60:expansion==1?70:80;uint8 const tier=expansion==0?7:expansion==1?12:18;
  reset();expansionRoute(900,900,expansion==0?0:expansion==1?530:571,expansion,cap,83);tick();assert(route(900)&&route(900)->minLevel==cap&&route(900)->maxLevel==cap);
  expansionBots(route(900)->continent,tier,cap);tick(30);assert(parties.size()==1);actors[4]->level=cap+1;tick();assert(parties.empty());unchanged();
  reset();expansionRoute(900,900,0,expansion,cap+1,83);tick();assert(routes.empty());
  reset();expansionRoute(900,900,0,expansion,cap-5,cap-5);expansionBots(0,tier,cap-5);tick(30);assert(parties.size()==1);expansionPortal(7000);tick();tick();actors[4]->level=cap;tick();assert(parties.size()==1&&actors[0]->ai.run.enabled);unchanged();
 }
 // Higher expansions never enable autonomous heroic, seasonal or raid routes.
 for(int bad=0;bad<4;++bad){reset();expansionRoute(136,543,530,1,62,63);switch(bad){case 0:sLFGDungeonStore.rows[136].Difficulty=1;break;case 1:sLFGDungeonStore.rows[136].Flags|=lfg::LFG_FLAG_SEASONAL;break;case 2:sLFGDungeonStore.rows[136].TypeID=2;break;case 3:sLFGDungeonStore.rows[136].ExpansionLevel=3;break;}tick();assert(routes.empty());}
 // Progress within the same expansion is allowed; earning a different era or
 // an invalid marker stops travel before any portal and stops an active clear.
 for(EraCase const& c:eraCases){
  for(bool running:{false,true}){
   reset();expansionRoute(c.dungeon,c.instance,c.outside,c.expansion,c.level,c.level);expansionBots(c.outside,c.tier,c.level);tick(30);
   if(running){expansionPortal(7000);tick();tick();assert(actors[0]->ai.run.enabled);}
   actors[4]->tier=c.expansion==1?12:18;tick();assert(parties.size()==1);
   actors[4]->tier=c.expansion==1?13:19;if(!running)expansionPortal(7000);tick();assert(parties.empty()&&!actors[0]->ai.run.enabled);
   for(auto& p:actors){assert(p->doorCalls==(running?1:0));}unchanged();
  }
 }

 // A long native planner corridor crosses several turns/segments. Prefixes must
 // preserve point order and lengths rather than draw chords to segment endpoints.
 auto polyline=[](std::vector<Vec> const& points,bool complete=true){ChunkedPathfinder::Result result;result.reachable=true;result.complete=complete;for(size_t start=0;start<points.size();start+=3){PathSegment segment;size_t const end=std::min(start+3,points.size());segment.polyline.assign(points.begin()+start,points.begin()+end);segment.ex=points[end-1].x;segment.ey=points[end-1].y;segment.ez=points[end-1].z;result.segments.push_back(segment);}return result;};
 auto motionDone=[](Player* p){assert(!p->motion.last.empty());p->position=p->motion.last.back();p->moving=false;};
 reset();walker=add(1,0);walker->position={0,0,0};objectMgr.triggers[101].x=320;fakeChunkedCustom=true;
 std::vector<Vec> corridor{{40,0,0},{40,40,0},{80,40,0},{80,0,0},{120,0,0},{120,40,0},{160,40,0},{160,0,0},{200,0,0},{200,40,0},{240,40,0},{240,0,0},{280,0,0},{280,40,0},{320,40,0},{320,0,0}};
 fakeChunkedResult=polyline(corridor);fakeDiagonalWall=true;
 size_t visited=0;
 while(walker->doorCalls==0){Vec const start=walker->position;uint32 const planned=fakeChunkedCalls;
  assert(walkOnce(walker,101));if(walker->doorCalls)break;
  assert(fakePlannerMap==0&&fakePlannerBoss==0&&fakePlannerBudget==4&&walker->motion.last.size()<=32);
  assert((walker->motion.last.front()-start).magnitude()<0.001f);
  float length=0;for(size_t i=1;i<walker->motion.last.size();++i){length+=(walker->motion.last[i]-walker->motion.last[i-1]).magnitude();assert((walker->motion.last[i]-corridor.at(visited++)).magnitude()<0.001f);}assert(length<=80.0f);
  assert(fakeChunkedCalls==(planned?planned:1));int const launched=walker->motion.splines;
  assert(walkOnce(walker,101)&&fakeChunkedCalls==1&&walker->motion.splines==launched);motionDone(walker);
 }
 assert(visited==corridor.size()&&fakeChunkedCalls==1&&walker->doorCalls==1&&!walks[0].corridor);unchanged();
 // A producer's partial route can make real progress without complete=true.
 // At its end the module rebuilds from the new position instead of looping it.
 reset();walker=add(1,0);walker->position={0,0,0};objectMgr.triggers[101].x=200;fakeChunkedCustom=true;fakeChunkedResult=polyline({{30,0,0},{60,0,0}},false);
 assert(walkOnce(walker,101)&&fakeChunkedCalls==1&&walker->motion.last.back().x==60);motionDone(walker);fakeChunkedResult=polyline({{90,0,0},{120,0,0}},false);
 assert(walkOnce(walker,101)&&fakeChunkedCalls==2&&walker->motion.last.front().x==60&&walker->motion.last.back().x==120);unchanged();
 // The first raycast is from the current physical position. A reachable result
 // from a no-mmap/direct or blocked fallback never authorizes raw movement.
 for(uint32 type:{uint32(PATHFIND_SHORTCUT),uint32(PATHFIND_NOPATH),uint32(PATHFIND_NORMAL|PATHFIND_NOT_USING_PATH),uint32(PATHFIND_NORMAL|PATHFIND_SHORT),uint32(PATHFIND_FARFROMPOLY),uint32(PATHFIND_INCOMPLETE)}){
  reset();walker=add(1,0);walker->position={0,0,0};objectMgr.triggers[101].x=200;fakeChunkedCustom=true;fakeChunkedResult=polyline({{40,0,0},{80,0,0}});fakePathType=type;
  assert(!walkOnce(walker,101)&&walker->motion.splines==0&&walker->doorCalls==0);unchanged();
 }
 reset();walker=add(1,0);walker->position={0,0,0};objectMgr.triggers[101].x=200;fakeChunkedCustom=true;fakeChunkedResult=polyline({{40,0,0},{80,0,0}});fakeRaycastBlocked=true;assert(!walkOnce(walker,101)&&walker->motion.splines==0);
 // Cache reuse revalidates changed geometry and never consumes unwalked turns.
 // A blocked cached window is planned once more from the current position.
 reset();walker=add(1,0);walker->position={0,0,0};objectMgr.triggers[101].x=320;fakeChunkedCustom=true;fakeChunkedResult=polyline(corridor);assert(walkOnce(walker,101));motionDone(walker);fakeWallX=80;fakeChunkedCustom=false;
 assert(!walkOnce(walker,101)&&fakeChunkedCalls==2&&walker->motion.splines==1&&walker->doorCalls==0);unchanged();
 // A displaced bot rejoins the nearest corridor point instead of planning
 // again; the leg back to it is raycast like every other one.
 reset();walker=add(1,0);walker->position={0,0,0};objectMgr.triggers[101].x=320;fakeChunkedCustom=true;fakeChunkedResult=polyline(corridor);assert(walkOnce(walker,101));motionDone(walker);
 walker->position={45,45,0};assert(walkOnce(walker,101)&&fakeChunkedCalls==1);assert(walker->motion.last[0].x==45&&walker->motion.last[1].x==40&&walker->motion.last[1].y==40&&walker->motion.last[2].x==80);unchanged();
 // Far displacement, another instance or map, or a different portal need a fresh build.
 for(int changed=0;changed<4;++changed){reset();walker=add(1,0);walker->position={0,0,0};objectMgr.triggers[101].x=320;fakeChunkedCustom=true;fakeChunkedResult=polyline(corridor);assert(walkOnce(walker,101));motionDone(walker);uint32 trigger=101;
  if(changed==0)walker->position={40,200,0};
  if(changed==1){auto& other=maps[{0,99}];other={0,99,false};walker->map=&other;}
  if(changed==2){auto& other=maps[{1,0}];other={1,0,false};walker->map=&other;objectMgr.triggers[101].map=1;}
  if(changed==3){objectMgr.triggers[102]={102,0,360,0,0,2};trigger=102;}
  Vec const pos=walker->position;fakeChunkedResult=polyline({{pos.x+20,pos.y,0},{pos.x+40,pos.y,0}});assert(walkOnce(walker,trigger)&&fakeChunkedCalls==2&&walker->motion.last.front().x==pos.x&&walker->motion.last.back().x==pos.x+40);unchanged();
 }
 // Party members share a planned corridor; a spent budget waits for a later tick.
 reset();walker=add(1,0);walker->position={0,0,0};objectMgr.triggers[101].x=320;fakeChunkedCustom=true;fakeChunkedResult=polyline(corridor);assert(walkOnce(walker,101)&&fakeChunkedCalls==1);
 {Player* mate=add(2,1);mate->position={35,3,0};buildBudget=0;assert(Walk(mate,101,walks,1)==Travel::Moving&&fakeChunkedCalls==1&&mate->motion.splines==1&&walks[1].corridor==walks[0].corridor);
  Player* far=add(3,2);far->position={0,300,0};buildBudget=0;assert(Walk(far,101,walks,2)==Travel::Moving&&fakeChunkedCalls==1&&far->motion.splines==0&&!walks[2].corridor);}
 unchanged();
 // Water on a window uses the bot's own swim speed; land windows clear it again.
 reset();walker=add(1,0);walker->position={0,0,0};objectMgr.triggers[101].x=320;fakeChunkedCustom=true;fakeChunkedResult=polyline(corridor);fakeWaterX=60;
 assert(walkOnce(walker,101)&&!walker->swimming&&walker->flagUpdates==0);motionDone(walker);assert(walkOnce(walker,101)&&walker->swimming&&walker->flagUpdates==1);
 fakeWaterX=std::numeric_limits<float>::infinity();motionDone(walker);assert(walkOnce(walker,101)&&!walker->swimming&&walker->flagUpdates==2);unchanged();
 // The planner's eight-yard arrival tolerance cannot bypass a smaller native
 // portal radius. Finish on a verified core path, then submit the normal opcode.
 reset();walker=add(1,0);walker->position={6,0,0};assert(walkOnce(walker,101)&&walker->motion.splines==1&&walker->doorCalls==0);motionDone(walker);assert(walker->position.x==0);assert(walkOnce(walker,101)&&walker->doorCalls==1);unchanged();
 // No-op, off-mesh, anchor, jump and door plans cannot advance. Oversized or
 // nonfinite routes fail before the movement API, including an unsafe tail.
 for(int bad=0;bad<12;++bad){reset();walker=add(1,0);walker->position={0,0,0};objectMgr.triggers[101].x=320;fakeChunkedCustom=true;fakeChunkedResult=polyline(corridor);
  switch(bad){case 0:fakeChunkedResult.reachable=false;break;case 1:fakeChunkedResult.startFarFromPoly=true;break;case 2:fakeChunkedResult.segments[1].anchored=true;break;case 3:fakeChunkedResult.segments[1].jumpDown=true;break;case 4:fakeChunkedResult.segments[1].jumpGap=true;break;case 5:fakeChunkedResult.segments[1].doorGoEntry=123;break;case 6:fakeChunkedResult.segments.clear();fakeChunkedResult.complete=false;break;case 7:fakeChunkedResult=polyline({{0,0,0},{0,0,0}});break;case 8:fakeChunkedResult.segments.back().polyline.back().x=std::numeric_limits<float>::quiet_NaN();break;case 9:fakeChunkedResult.segments.back().polyline.back().z=std::numeric_limits<float>::infinity();break;case 10:fakeChunkedResult.segments[0].polyline.assign(4097,Vec{10,0,0});break;case 11:fakeChunkedResult=polyline({{100,0,0}});break;}
  assert(!walkOnce(walker,101)&&walker->motion.splines==0&&walker->doorCalls==0);unchanged();
 }
 // The point limit independently bounds dense native corridors; distant tails
 // wait for the next window and are independently checked when reached.
 reset();walker=add(1,0);walker->position={0,0,0};objectMgr.triggers[101].x=200;std::vector<Vec> dense;for(int x=1;x<=100;++x)dense.push_back({float(x),0,0});fakeChunkedCustom=true;fakeChunkedResult=polyline(dense);fakeWallX=90;
 assert(walkOnce(walker,101)&&walker->motion.last.size()==32&&walker->motion.last.back().x==31);motionDone(walker);assert(walkOnce(walker,101)&&walker->motion.last.back().x==62);motionDone(walker);fakeChunkedCustom=false;assert(!walkOnce(walker,101)&&fakeChunkedCalls==2&&walker->motion.splines==2);unchanged();
 // Moving, fighting, casting or crowd-controlled bots never invoke the planner.
 for(int pause=0;pause<4;++pause){reset();walker=add(1,0);walker->position={10,0,0};switch(pause){case 0:walker->moving=true;break;case 1:walker->combat=true;break;case 2:walker->cast=true;break;case 3:walker->rooted=true;break;}assert(walkOnce(walker,101)&&fakeChunkedCalls==0&&walker->motion.splines==0&&walker->doorCalls==0);unchanged();}
 // The coordinator plans one shared real corridor per party for long entrances
 // and exits in each earned era, while portals and whole-party start remain native.
 for(uint8 expansion:{uint8(0),uint8(1),uint8(2)}){
  reset();uint32 const outside=expansion==0?0:expansion==1?530:571,inside=expansion==0?34:expansion==1?543:574;uint8 const tier=expansion==0?7:expansion==1?12:18,level=expansion==0?25:expansion==1?65:75;
  objectMgr.triggers.clear();objectMgr.targets.clear();expansionRoute(900,inside,outside,expansion,level,level);expansionBots(outside,tier,level);objectMgr.triggers[7000].x=0;tick(30);assert(parties.size()==1);
  for(int step=0;step<12&&!actors[0]->ai.run.enabled;++step){tick();for(auto& p:actors)if(p->GetMapId()==outside&&p->moving)motionDone(p.get());}
  assert(parties.size()==1&&actors[0]->ai.run.enabled&&fakeChunkedCalls==1);for(auto& p:actors)assert(p->doorCalls==1&&p->GetMapId()==inside&&p->motion.splines>4);
  uint32 const entranceCalls=fakeChunkedCalls;actors[0]->ai.run.enabled=false;objectMgr.triggers[7001].x=710;
  for(int step=0;step<14&&!parties.empty();++step){tick();for(auto& p:actors)if(p->GetMapId()==inside&&p->moving)motionDone(p.get());}
  assert(parties.empty()&&fakeChunkedCalls==entranceCalls+1);for(auto& p:actors)assert(p->doorCalls==2&&p->GetMapId()==outside&&!p->group);unchanged();
 }


 // Compile the actual upstream TryProbe gate: an unloaded far tile must refuse
 // its direct shortcut so existing nearer real stride probes can be attempted.
 reset();walker=add(1,0);walker->position={0,0,0};std::vector<Vec> probe;uint32 probeType=0;fakeMissingTileX=180;
 assert(!TryProbe(walker,0,0,0,0,300,0,0,probe,probeType)&&probe.empty()&&(probeType&PATHFIND_NOT_USING_PATH));
 assert(TryProbe(walker,0,0,0,0,90,0,0,probe,probeType)&&probe.size()==1&&probe.back().x==90);
 fakeMissingTileX=std::numeric_limits<float>::infinity();
 for(uint32 type:{uint32(PATHFIND_NORMAL),uint32(PATHFIND_INCOMPLETE)}){fakePathType=type;assert(TryProbe(walker,0,0,0,0,90,0,0,probe,probeType)&&!probe.empty());}
 for(uint32 type:{uint32(PATHFIND_NORMAL|PATHFIND_NOT_USING_PATH),uint32(PATHFIND_NORMAL|PATHFIND_FARFROMPOLY_START),uint32(PATHFIND_NORMAL|PATHFIND_FARFROMPOLY_END),uint32(PATHFIND_SHORT),uint32(PATHFIND_SHORTCUT),uint32(PATHFIND_NOPATH),uint32(PATHFIND_BLANK)}){fakePathType=type;assert(!TryProbe(walker,0,0,0,0,90,0,0,probe,probeType)&&probe.empty());}
 sPlayerbotAIConfig.naturalProgression=false;fakePathType=PATHFIND_NORMAL|PATHFIND_NOT_USING_PATH;assert(TryProbe(walker,0,0,0,0,90,0,0,probe,probeType)&&probe.size()==1&&probe.back().x==90);unchanged();

 reset();std::cout<<"Earned dungeon production coordinator: shared, rejoined and budgeted curved/partial long routes, swim speed, portal refusal memory, native entry pre-checks, bounded raw splines, geometry revalidation, native portal finish, recruitment, native era boundaries, three expansion caps, real-path gates, routes on 0/1/530/571, capital factions, wings, level bands, portal pending ACK, complete parties, native exits, ownership, wipes, era transitions, stalls, timeouts and concurrency passed\n";
}
'''


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth, cursor = 1, opening + 1
    while depth:
        depth += (source[cursor] == '{') - (source[cursor] == '}')
        cursor += 1
    return source[start:cursor]


def native_contracts(core, source):
    # Keep the test doubles honest about the core's real call boundary and
    # path early-return behavior. Executable tests below cover module behavior.
    world=(core/'src/server/game/World/World.cpp').read_text()
    assert world.index('sMapMgr->Update(diff)') < world.index('sScriptMgr->OnWorldUpdate(diff)')
    map_mgr=(core/'src/server/game/Maps/MapMgr.cpp').read_text()
    assert 'm_updater.wait()' in function(map_mgr, 'void MapMgr::Update(')
    accept=(core/'modules/mod-playerbots/src/Ai/Base/Actions/AcceptInvitationAction.cpp').read_text()
    body=function(accept, 'bool AcceptInvitationAction::Execute(')
    assert 'CheckLevelFor(PLAYERBOT_SECURITY_INVITE' in body and 'HandleGroupAcceptOpcode' in body
    assert 'botAI->ResetStrategies()' in body
    summon=(core/'modules/mod-playerbots/src/Ai/Base/Actions/UseMeetingStoneAction.cpp').read_text()
    assert re.search(r'if \(sPlayerbotAIConfig.naturalProgression\)\s*return false;',function(summon,'bool SummonAction::Teleport('))
    path=(core/'src/server/game/Movement/MovementGenerators/PathGenerator.cpp').read_text()
    assert '_useRaycast' in path and 'PATHFIND_INCOMPLETE' in path
    coordinator=(source/'EarnedDungeonParties.cpp').read_text()
    assert 'std::shared_lock<std::shared_mutex>' in coordinator and 'GetMemberSlots()' in coordinator
    # Individual Progression stays out of the coordinator's translation unit
    # (its GENERAL rank collides with playerbots' chat channel enumerator).
    assert '#include "IndividualProgression.h"' not in coordinator
    bridge=(source/'DcEarnedProgression.cpp').read_text()
    assert 'GetPlayerProgressionFromQuests(player)' in bridge and 'IsStrictDefaultProgression()' in bridge
    assert all(name in bridge for name in ('PROGRESSION_PRE_TBC', 'PROGRESSION_TBC_TIER_5', 'PROGRESSION_WOTLK_TIER_5'))
    continent = function((core/'src/server/shared/DataStores/DBCStructure.h').read_text(), '[[nodiscard]] bool IsContinent() const')
    assert all(name in continent for name in ('MAP_EASTERN_KINGDOMS', 'MAP_KALIMDOR', 'MAP_OUTLAND', 'MAP_NORTHREND'))
    # Production shortcut gates remain enforced even if an existing config
    # enables a provisioning/recovery option in the portable earned profile.
    gated={
      'Util/DcDungeonAccess.cpp': ('std::string GrantEntry(', '!bot || DcEarnedPlay::Active()'),
      'Ai/Dungeon/DungeonClear/Util/DungeonEventExecutor.cpp': ('StepResult DungeonEventExecutor::RunStep(', 'if (DcEarnedPlay::Active() && !DcEarnedEvents::StepAllowed(step))\n        return StepResult::Failed;'),
      'Ai/Dungeon/DungeonClear/Overrides/ObjectiveHookRegistry.cpp': ('ObjectiveArriveResult ObjectiveHookRegistry::Run(', 'if (DcEarnedPlay::Active())\n        return ObjectiveArriveResult::Blocked;'),
      'Ai/Dungeon/DungeonClear/Util/DcRezRecovery.cpp': ('bool RegroupAtEntrance(', 'if (DcEarnedPlay::Active())'),
      'Ai/Dungeon/DungeonClear/Action/DcAdvanceAction.cpp': ('bool TryFarFromPolyRecovery(', 'if (DcEarnedPlay::Active())'),
      'Ai/Dungeon/DungeonClear/Util/DcSocialQuarantine.cpp': ('void Update(', 'if (DcEarnedPlay::Active())'),
      'Ai/Dungeon/DungeonClear/Action/BetterLootRollAction.cpp': ('bool DungeonClearBetterLootRollAction::Execute(', 'DcEarnedPlay::Active() ||'),
      'Ai/Dungeon/DungeonClear/Action/DcPullActions.cpp': ('bool DungeonClearPullManeuverAction::Execute(', 'if (!DcEarnedPlay::Active())\n        bot->RemoveAurasDueToSpell(1604);'),
    }
    for path,(signature,gate) in gated.items():
        assert gate in function((source/path).read_text(),signature), path
    # Earned events click through the client opcodes with the bot's own key and
    # never receive a granted quest item; shortcut drivers are not reached.
    run_step=function((source/'Ai/Dungeon/DungeonClear/Util/DungeonEventExecutor.cpp').read_text(),'StepResult DungeonEventExecutor::RunStep(')
    earned_use=run_step[run_step.index('            if (DcEarnedPlay::Active())\n            {'):run_step.index('// A GO script that gates on a carried key item')]
    assert 'DcEarnedEvents::CanOpen(bot, go)' in earned_use and 'HandleGameObjectUseOpcode(packet)' in earned_use and 'AddItem' not in earned_use
    assert 'if (!item && DcEarnedPlay::Active())\n                return StepResult::Failed;' in run_step
    engage=(source/'Ai/Dungeon/DungeonClear/Action/DcEngageActions.cpp').read_text()
    for kind in ('EscortCreature','DropInHole','UseItemOnGO','UseItemAt'):
        assert f'step.kind == EventStepKind::{kind} && !DcEarnedPlay::Active()' in engage, kind
    chunked=(source/'Ai/Dungeon/DungeonClear/Util/ChunkedPathfinder.cpp').read_text()
    strided=(source/'Ai/Dungeon/DungeonClear/Util/StridedPathfinder.cpp').read_text()
    assert 'return StridedPathfinder::Build(' in chunked and 'LongRangePathfinder::Build(bot, tx, ty, tz)' in strided
    assert 'if (bossEntry)' in strided and 'PATHFIND_NOT_USING_PATH' in strided
    assert 'ChunkedPathfinder::Build(player, player->GetMapId(), 0,' in function(coordinator, 'bool BuildCorridor(')
    # The recruitment pre-check asks the same native gates the portal applies:
    # the area-trigger handler's entry check, then TeleportTo's module hook,
    # where Individual Progression refuses dungeons above a bot's earned stage.
    trigger=function((core/'src/server/game/Handlers/MiscHandler.cpp').read_text(),'void WorldSession::HandleAreaTriggerOpcode(')
    assert trigger.index('sMapMgr->PlayerCannotEnter(at->target_mapId, player, false)') < trigger.index('player->TeleportTo(at->target_mapId')
    teleport=function((core/'src/server/game/Entities/Player/Player.cpp').read_text(),'bool Player::TeleportTo(')
    assert 'sScriptMgr->OnPlayerBeforeTeleport(this, mapid, x, y, z, orientation, options, target)' in teleport
    # The probe reuses the hook's gates without firing teleport hooks, which act
    # on the candidate; TestProgressionMapGates checks that both decide alike.
    ip=(core/'modules/mod-individual-progression/src/IndividualProgressionPlayer.cpp').read_text()
    assert 'return CanEnterMap(player, mapid, x, y, z, player ? player->GetSession() : nullptr);' in function(ip,'bool OnPlayerBeforeTeleport(')
    assert 'IndividualPlayerProgression::CanEnterMap(player, mapId, x, y, z, nullptr)' in function(ip,'bool IndividualProgression::CanEnterMap(')
    gates=function(ip,'static bool CanEnterMap(')
    assert all(name in gates for name in ('MAP_THE_FORGE_OF_SOULS','MAP_MAGISTERS_TERRACE','MAP_TRIAL_OF_THE_CHAMPION'))
    spectate=function((source/'DungeonClearModule.cpp').read_text(),'    bool OnPlayerBeforeTeleport(')
    assert 'DcSpectator::Stop(player);' in spectate
    assert 'sScriptMgr' not in (source/'EarnedDungeonParties.cpp').read_text()
    print('Native dungeon contracts: joined map workers, invitation security/reset, summon refusal, group ownership, event shortcut and production shortcut gates verified')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path)
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[2]
    core=prepared_core(repo)
    source=args.source or core/'modules/mod-dungeon-clear/src'
    native_contracts(core,source)
    if not (source/'EarnedDungeonParties.cpp').exists():
        raise SystemExit('PrepareModules.cmake must prepare the earned DungeonClear patch first')
    compiler=shutil.which('c++') or shutil.which('g++') or shutil.which('clang++')
    if not compiler:
        raise SystemExit('A C++20 compiler is required')
    with tempfile.TemporaryDirectory(prefix='earned-dungeons-') as temp:
        work=Path(temp)
        ip_header=(core/'modules/mod-individual-progression/src/IndividualProgression.h').read_text()
        progression_enum=re.search(r'enum ProgressionState : uint8[^{}]*\{.*?^\};', ip_header, re.M|re.S)
        if not progression_enum:
            raise SystemExit('Native Individual Progression stages were not recognised')
        (work/'NativeStubs.h').write_text(STUBS.replace('// NATIVE_PROGRESSION_ENUM', progression_enum.group(0)))
        headers=('Define.h','Common.h','Map.h','ScriptMgr.h','G3D/Vector3.h','Ai/Dungeon/DungeonClear/Data/WaypointHint.h','MapMgr.h','PlayerbotAIConfig.h','PathGenerator.h','Player.h','DcModuleEnable.h','DcStrategyGate.h','Ai/Dungeon/DungeonClear/Action/DcActionShared.h','Ai/Dungeon/DungeonClear/Util/DcRun.h','Ai/Dungeon/DungeonClear/DcValueKeys.h','Config.h','DBCStores.h','Event.h','Group.h','GroupMgr.h','IndividualProgression.h','Log.h','LFGMgr.h','MotionMaster.h','ObjectAccessor.h','ObjectMgr.h','Playerbots.h','PlayerbotAI.h','Timer.h','WorldPacket.h','WorldSession.h')
        for name in headers:
            path=work/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('#include "NativeStubs.h"\n')
        path=work/'Ai/Dungeon/DungeonClear/Util/ChunkedPathfinder.h';shutil.copyfile(source/'Ai/Dungeon/DungeonClear/Util/ChunkedPathfinder.h',path)
        for name in ('EarnedDungeonParties.cpp','EarnedDungeonParties.h','DcEarnedPlay.h','DcEarnedEvents.h','DcEarnedProgression.h','DcEarnedProgression.cpp'):
            shutil.copyfile(source/name,work/name)
        methods=function((source/'Ai/Dungeon/DungeonClear/Util/DcLeaderSignal.cpp').read_text(),'void DcLeaderSignal::SetLeaderDazeImmunity(')+'\n'+function((source/'Ai/Dungeon/DungeonClear/Action/BetterLootRollAction.cpp').read_text(),'bool DungeonClearBetterLootRollAction::isUseful(')
        follow=function((source/'Ai/Dungeon/DungeonClear/Action/DcFollowerActions.cpp').read_text(),'bool DungeonClearFollowTankAction::Execute(')
        follow=follow[follow.rindex('    if (DcEarnedPlay::Active())'):]
        methods+='\nbool NativeFollowFallback(Player* bot,Player* tank,float followDist,float angle)\n{\n'+follow
        strided=(source/'Ai/Dungeon/DungeonClear/Util/StridedPathfinder.cpp').read_text()
        methods+='\n'+function(strided,'bool PathTypeIsBogusChunk(')+'\n'+function(strided,'bool TryProbe(')
        (work/'NativeProductionMethods.h').write_text(methods)
        (work/'fixture.cpp').write_text(HARNESS)
        exe=work/('fixture.exe' if os.name=='nt' else 'fixture')
        flags=['-std=c++20','-O1','-Wall','-Wextra','-Wno-unused-parameter','-I',str(work)]
        if os.name!='nt':
            flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie']
        subprocess.run([compiler,*flags,str(work/'fixture.cpp'),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
        originals={name:(work/name).read_text() for name in ('DcEarnedPlay.h','EarnedDungeonParties.cpp','DcEarnedProgression.cpp','NativeProductionMethods.h')}
        mutations=[
            ('unloaded tile probe accepts shortcut','NativeProductionMethods.h','if (DcEarnedPlay::Active() && !DcEarnedPlay::UsesRealPath(gen))','if (false)'),
            ('raw planner fallback spline','EarnedDungeonParties.cpp','if (DcEarnedPlay::RealSpline(player, points))','if (true)'),
            ('flatten segment endpoints into chords','EarnedDungeonParties.cpp','corridor.insert(corridor.end(), segment.polyline.begin(), segment.polyline.end());','corridor.push_back(G3D::Vector3(segment.ex, segment.ey, segment.ez));'),
            ('partial route requires whole completion','EarnedDungeonParties.cpp','if (!route.reachable || route.startFarFromPoly)','if (!route.complete || !route.reachable || route.startFarFromPoly)'),
            ('off-mesh route accepted','EarnedDungeonParties.cpp','!route.reachable || route.startFarFromPoly','!route.reachable'),
            ('anchor shortcut accepted','EarnedDungeonParties.cpp','segment.anchored || segment.jumpDown','segment.jumpDown'),
            ('jump-down shortcut accepted','EarnedDungeonParties.cpp','segment.anchored || segment.jumpDown || segment.jumpGap','segment.anchored || segment.jumpGap'),
            ('jump-gap shortcut accepted','EarnedDungeonParties.cpp','segment.jumpDown || segment.jumpGap || segment.doorGoEntry','segment.jumpDown || segment.doorGoEntry'),
            ('door shortcut accepted','EarnedDungeonParties.cpp','segment.jumpGap || segment.doorGoEntry','segment.jumpGap'),
            ('lost physical cursor check','EarnedDungeonParties.cpp','(state.expected - origin).magnitude() <= 0.05f','true'),
            ('cached wrong map','EarnedDungeonParties.cpp','corridor && map == player->GetMapId() &&','corridor &&'),
            ('cached wrong instance','EarnedDungeonParties.cpp','instance == player->GetInstanceId() && trigger','trigger'),
            ('cached wrong portal','EarnedDungeonParties.cpp','&& trigger == portal;',';'),
            ('party corridor not shared','EarnedDungeonParties.cpp','walks[(self + offset) % walks.size()]','walks[self]'),
            ('unbounded corridor builds','EarnedDungeonParties.cpp','if (!buildBudget)','if (false)'),
            ('water crossed at run speed','EarnedDungeonParties.cpp','DcEarnedPlay::MatchSwimming(player, points);',''),
            ('portal refusal ignored','EarnedDungeonParties.cpp','return player->IsBeingTeleported() || player->GetMapId() != at->map;','return true;'),
            ('refused bot recruited again','EarnedDungeonParties.cpp','Refused(player, route) || !CanEnter','!CanEnter'),
            ('native entry pre-check skipped','EarnedDungeonParties.cpp',' || !CanEnter(player, *entranceTarget)',''),
            ('progression map gate skipped','EarnedDungeonParties.cpp','return DcEarnedProgression::CanEnterMap(','return true || DcEarnedProgression::CanEnterMap('),
            ('progression map gate not asked','DcEarnedProgression.cpp','return sIndividualProgression->CanEnterMap(player, mapId, x, y, z);','return true;'),
            ('teleport hook probe','EarnedDungeonParties.cpp','return DcEarnedProgression::CanEnterMap(player, target.target_mapId, target.target_X, target.target_Y,\n                                                target.target_Z) &&','return sScriptMgr->OnPlayerBeforeTeleport(player, target.target_mapId, target.target_X, target.target_Y, target.target_Z, target.target_Orientation, 0, nullptr) &&'),
            ('core entry check skipped','EarnedDungeonParties.cpp','sMapMgr->PlayerCannotEnter(target.target_mapId, player, false) == Map::CAN_ENTER','true'),
            ('unbounded spline distance','EarnedDungeonParties.cpp','if (distance + leg > 80.0f)','if (false)'),
            ('unbounded spline points','EarnedDungeonParties.cpp','points.size() < 32','points.size() < 4096'),
            ('missing last-yard portal approach','EarnedDungeonParties.cpp','if (corridor.empty() && route.complete &&','if (false && route.complete &&'),

            ('missing navmesh guard','DcEarnedPlay.h','auto const type = path.GetPathType();','return true;\n        auto const type = path.GetPathType();'),
            ('raw wall-crossing spline','DcEarnedPlay.h','leg.SetUseRaycast(true);','leg.SetUseRaycast(false);'),
            ('member era bypass','EarnedDungeonParties.cpp','DcEarnedProgression::Expansion(player) != route.expansion','false'),
            ('partial-party start','EarnedDungeonParties.cpp','if (allInside)','if (true)'),
            ('lost group ownership','EarnedDungeonParties.cpp','if (group && !ownedGroup)','if (false)'),
            ('premature navigation takeover','EarnedDungeonParties.cpp','members[i] = member;\n            ++roles[Role(member)];','members[i] = member;\n            HoldNavigation(member);\n            ++roles[Role(member)];'),
            ('mixed-faction party','EarnedDungeonParties.cpp','candidate->GetMap() != tank->GetMap() || candidate->GetTeamId() != tank->GetTeamId() ||','candidate->GetMap() != tank->GetMap() ||'),
            ('capital faction ignored','EarnedDungeonParties.cpp','if (zone && (zone->flags & AREA_FLAG_CAPITAL))','if (false)'),
            ('unaudited dungeon route','EarnedDungeonParties.cpp','if (!DcEarnedEvents::MapAudited(dungeon->MapID, reason))','if (false)'),
            ('band above the expansion cap','EarnedDungeonParties.cpp','target + levelSpread, ExpansionLevelCap(route.expansion)}','target + levelSpread, 255u}'),
            ('invalid progression marker','DcEarnedProgression.cpp','stage > PROGRESSION_WOTLK_TIER_5','false'),
            ('TBC boundary lifted early','DcEarnedProgression.cpp','stage >= PROGRESSION_PRE_TBC','stage >= PROGRESSION_NAXX40'),
            ('Wrath boundary lifted early','DcEarnedProgression.cpp','stage >= PROGRESSION_TBC_TIER_5','stage >= PROGRESSION_TBC_TIER_4'),
            ('TBC cap uses Wrath level','EarnedDungeonParties.cpp','expansion == 1 ? 70','expansion == 1 ? 80'),
            ('endless stalled run','EarnedDungeonParties.cpp','else if (getMSTimeDiff(party.stalledSince, getMSTime()) > stallTimeout)','else if (false)'),
            ('uncontrolled persistent follower path','NativeProductionMethods.h','if (DcEarnedPlay::Active())','if (false)'),
            ('free daze immunity','NativeProductionMethods.h','if (apply && !DcEarnedPlay::Active())','if (apply)'),
        ]
        for label,name,old,new in mutations:
            for original_name,text in originals.items():
                (work/original_name).write_text(text)
            mutated=originals[name].replace(old,new)
            if mutated==originals[name]:
                raise SystemExit(f'{label} mutation was not applied')
            (work/name).write_text(mutated)
            subprocess.run([compiler,'-std=c++20','-O1','-I',str(work),str(work/'fixture.cpp'),'-o',str(exe)],check=True)
            result=subprocess.run([str(exe)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            if result.returncode==0:
                raise SystemExit(f'Production fixture did not reject {label}')
            print(f'Earned dungeon production mutation rejected: {label}')

if __name__=='__main__':
    main()
