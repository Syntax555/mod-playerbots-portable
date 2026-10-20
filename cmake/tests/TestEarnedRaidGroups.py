"""Exercise the real raid recruitment transaction with native-shaped adapters."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    cxx,
    function,
    prepared_core,
    reject_mutants,
    run_fixture,
    source_argument,
)
from TestEarnedRaidComposition import native_contracts as composition_contracts


STUBS = r'''
#pragma once
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <vector>
using uint8=uint8_t;using uint32=uint32_t;
struct ObjectGuid {uint32 id=0;bool operator==(ObjectGuid r)const{return id==r.id;}bool operator!=(ObjectGuid r)const{return id!=r.id;}bool operator<(ObjectGuid r)const{return id<r.id;}static const ObjectGuid Empty;};const ObjectGuid ObjectGuid::Empty{};
enum TeamId:uint8 {TEAM_ALLIANCE,TEAM_HORDE,TEAM_NEUTRAL};
enum Difficulty:uint8 {RAID_DIFFICULTY_10MAN_NORMAL,RAID_DIFFICULTY_25MAN_NORMAL,RAID_DIFFICULTY_10MAN_HEROIC};
constexpr uint8 POWER_MANA=0,POWER_RAGE=1,CLASS_MAGE=8,CLASS_HUNTER=3,BOT_STATE_NON_COMBAT=0;
struct Player;struct Group;
struct Map {enum EnterState {CAN_ENTER,CANNOT_ENTER_NOT_IN_RAID,CANNOT_ENTER_UNSPECIFIED_REASON};uint32 id=0;};
struct AreaTrigger {uint32 entry,map;float x=0,y=0,z=0;};
struct AreaTriggerTeleport {uint32 target_mapId;float target_X=0,target_Y=0,target_Z=0;};
struct MapEntry {uint32 MapID=0;bool continent=false,raid=false;bool IsContinent()const{return continent;}bool IsRaid()const{return raid;}};
struct MapDifficulty {uint32 maxPlayers=0;};
constexpr uint32 SPELL_EFFECT_APPLY_AREA_AURA_PARTY=35,SPELL_EFFECT_APPLY_AREA_AURA_RAID=65,TARGET_UNIT_CASTER_AREA_PARTY=20,SPELL_EFFECT_SUMMON=28;
struct Target {uint32 GetTarget()const{return 0;}};
struct SpellEffectInfo {uint32 Effect=0;Target TargetA,TargetB;int32_t MiscValue=0;};
struct SpellInfo {std::array<SpellEffectInfo,3> Effects;};
struct CreatureTemplate {std::array<uint32,8> spells{};};
struct SpellMgr {SpellInfo const* GetSpellInfo(uint32){return nullptr;}} spellMgr;SpellMgr* sSpellMgr=&spellMgr;
template<class T>struct Store {std::map<uint32,T> rows;T const* LookupEntry(uint32 id){auto found=rows.find(id);return found==rows.end()?nullptr:&found->second;}};Store<MapEntry> sMapStore;
std::map<std::pair<uint32,Difficulty>,MapDifficulty> difficulties;
MapDifficulty const* GetMapDifficultyData(uint32 map,Difficulty difficulty){auto found=difficulties.find({map,difficulty});return found==difficulties.end()?nullptr:&found->second;}
struct WorldPacket {std::string name;WorldPacket& operator<<(std::string value){name=value;return *this;}WorldPacket& operator<<(uint32){return *this;}};
struct Session {Player* owner;bool headless=true,loading=false;uint32 account=1;bool IsHeadless()const{return headless;}bool PlayerLoading()const{return loading;}uint32 GetAccountId()const{return account;}void HandleGroupInviteOpcode(WorldPacket&);void HandleGroupRaidConvertOpcode(WorldPacket&);};
struct Event {std::string source;explicit Event(char const* s):source(s){}};
struct Spell {std::string name;bool active=true,removed=false,inSpec=true,passive=false;};
struct Value {uint32 value=0;uint32 Get(){return value;}};
struct Context {Player* player;Value value;template<class T>Value* GetValue(char const*,char const*);};
struct PlayerbotAI {
 Player* player;Player* master=nullptr;Context context;bool human=false,accept=true;int roleAfter=-1;
 uint32 navChanges=0;std::set<std::string> strategies{"new rpg","grind","travel"};
 explicit PlayerbotAI(Player* p):player(p),context{p,{}}{}
 Player* GetMaster(){return master;}void SetMaster(Player* p){master=p;}bool HasGameClientMaster(){return human;}
 bool HasStrategy(char const* name,int){return strategies.count(name);}void ChangeStrategy(std::string name,int){++navChanges;if(name[0]=='+')strategies.insert(name.substr(1));else strategies.erase(name.substr(1));}
 bool DoSpecificAction(char const*,Event,bool);Context* GetAiObjectContext(){return &context;}
 static bool IsTank(Player*,bool=false);static bool IsHeal(Player*,bool=false);static bool IsRanged(Player*,bool=false);
};
struct Player {
 ObjectGuid guid;uint8 level=60,era=0,role=3,klass=CLASS_MAGE,power=POWER_MANA;TeamId team=TEAM_ALLIANCE;
 bool world=true,alive=true,gm=false,bg=false,queue=false,transfer=false,flying=false,vehicle=false,transport=false,combat=false,access=true,progression=true,entry=true;
 uint32 bind=0;bool permanentBind=false;
 uint8 lfg=0;uint32 phase=1;float x=100,y=0,z=0;Map* map=nullptr;Difficulty difficulty=RAID_DIFFICULTY_10MAN_NORMAL;
 uint32 satisfyCalls=0,progressionCalls=0,entryCalls=0,invited=0,money=100,xp=200,items=4;bool denyAfterAccept=false;
 Session session;std::unique_ptr<PlayerbotAI> ai;Group* group=nullptr;Group* invitation=nullptr;std::map<uint32,Spell> spells;
 explicit Player(uint32 id):guid{id},session{this},ai(std::make_unique<PlayerbotAI>(this)){}
 ObjectGuid GetGUID()const{return guid;}std::string GetName()const{return "bot"+std::to_string(guid.id);}
 Session* GetSession(){return &session;}Group* GetGroup(){return group;}Group* GetGroupInvite(){return invitation;}
 Map* GetMap(){return map;}uint32 GetMapId(){return map->id;}TeamId GetTeamId()const{return team;}uint32 GetPhaseMask()const{return phase;}
 bool IsInWorld(){return world;}bool IsAlive(){return alive;}bool IsGameMaster(){return gm;}uint8 GetLevel(){return level;}
 bool InBattleground(){return bg;}bool InBattlegroundQueue(){return queue;}bool IsBeingTeleported(){return transfer;}bool IsInFlight(){return flying;}bool GetVehicle(){return vehicle;}bool GetTransport(){return transport;}bool IsInCombat(){return combat;}
 Difficulty GetRaidDifficulty(){return difficulty;}Difficulty GetDifficulty(bool raid){assert(raid);return difficulty;}
 float GetExactDist(float a,float b,float c){return std::sqrt((x-a)*(x-a)+(y-b)*(y-b)+(z-c)*(z-c));}float GetExactDist(Player* p){return GetExactDist(p->x,p->y,p->z);}
 bool leaderOnly=false;uint32 accessCheckTakeover=0;
 bool Satisfy(void const*,uint32,bool);
 uint8 getClass(){return klass;}uint8 getPowerType(){return power;}bool HasActiveSpell(uint32 id){auto found=spells.find(id);return found!=spells.end()&&found->second.active&&!found->second.removed&&found->second.inSpec;}
 void UninviteFromGroup();
};
#define GET_PLAYERBOT_AI(player) ((player)->ai.get())
bool PlayerbotAI::IsTank(Player* p,bool){return p->role==0;}bool PlayerbotAI::IsHeal(Player* p,bool){return p->role==1;}bool PlayerbotAI::IsRanged(Player* p,bool){return p->role==3;}
template<class T>Value* Context::GetValue(char const* type,char const* name){assert(std::string(type)=="spell id");value.value=0;for(auto const& [id,spell]:player->spells)if(spell.name==name&&spell.active&&!spell.removed&&spell.inSpec&&!spell.passive)value.value=id;return &value;}
uint32 bindCopyCount=0,raidMinLevel=10;
struct Group {
 struct MemberSlot {ObjectGuid guid;uint8 group=0;};ObjectGuid guid;Player* leader;bool raid=false;std::vector<Player*> players;std::vector<MemberSlot> slots;uint32 conversions=0;
 ObjectGuid GetGUID(){return guid;}ObjectGuid GetLeaderGUID(){return leader->guid;}bool isRaidGroup(){return raid;}size_t GetMembersCount(){return players.size();}
 auto const& GetMemberSlots(){return slots;}uint8 GetMemberGroup(ObjectGuid id){for(auto const& slot:slots)if(slot.guid==id)return slot.group;return 255;}
 void ConvertToRaid(){++conversions;raid=true;}void ChangeMembersGroup(ObjectGuid id,uint8 subgroup){assert(raid&&subgroup<8);for(auto& slot:slots)if(slot.guid==id){slot.group=subgroup;return;}}
 bool CheckLevelForRaid(){for(Player* player:players)if(player->GetLevel()<raidMinLevel)return true;return false;}
 bool AddMember(Player* player){std::array<uint8,8> occupied{};for(auto const& slot:slots)++occupied[slot.group];uint8 subgroup=0;while(subgroup<8&&occupied[subgroup]>=5)++subgroup;if(subgroup==8||(!raid&&subgroup>0))return false;players.push_back(player);slots.push_back({player->guid,subgroup});player->group=this;player->invitation=nullptr;player->difficulty=leader->difficulty;return true;}
 void ChangeLeader(Player* p){Player* old=leader;leader=p;++bindCopyCount;if(!leader->bind)leader->bind=old->bind;}
 void RemoveMember(ObjectGuid id){for(Player* p:players)if(p->guid==id)p->group=nullptr;std::erase_if(players,[&](Player* p){return p->guid==id;});std::erase_if(slots,[&](MemberSlot const& slot){return slot.guid==id;});if(players.size()<2){for(Player* p:players)p->group=nullptr;players.clear();slots.clear();}else if(leader->guid==id)ChangeLeader(players.front());}
};
std::vector<std::unique_ptr<Group>> groups;std::vector<std::unique_ptr<Player>> actors;std::vector<Player*> online;
uint32 inviteCount=0,acceptedCount=0;std::map<uint32,Map> maps;bool moduleEnabled=true,strictProgression=true;
Player* takeoverAfterAccept=nullptr;
Player* denyAccessAfterAccept=nullptr;
Player* changeLeaderAfterAccept=nullptr;uint32 changeLeaderAtAccept=0;
bool Player::Satisfy(void const*,uint32,bool){++satisfyCalls;if(accessCheckTakeover==satisfyCalls)ai->human=true;return leaderOnly&&group?group->leader->access:access;}
void Player::UninviteFromGroup(){Group* pending=invitation;invitation=nullptr;if(pending&&pending->players.empty()){bool other=false;for(Player* p:online)if(p!=pending->leader&&p->invitation==pending)other=true;if(!other&&pending->leader->invitation==pending)pending->leader->invitation=nullptr;}}
void Session::HandleGroupInviteOpcode(WorldPacket& packet){++inviteCount;if(owner->group&&owner->group->leader!=owner)return;Player* target=nullptr;for(Player* p:online)if(p->GetName()==packet.name)target=p;if(!target||target->group||target->invitation)return;++target->invited;Group* group=owner->group?owner->group:owner->invitation;if(!group){groups.push_back(std::make_unique<Group>(Group{{uint32(groups.size()+100)},owner,false,{},{},0}));group=groups.back().get();owner->invitation=group;}target->invitation=group;}
void Session::HandleGroupRaidConvertOpcode(WorldPacket&){Group* group=owner->group;if(!group||owner->InBattleground()||group->CheckLevelForRaid()||group->leader!=owner||group->GetMembersCount()<2)return;group->ConvertToRaid();}
bool PlayerbotAI::DoSpecificAction(char const* action,Event,bool){assert(std::string(action)=="accept invitation");if(!accept||!player->invitation)return false;Group* group=player->invitation;if(group->players.empty()){group->AddMember(group->leader);group->leader->invitation=nullptr;}if(!group->AddMember(player))return false;++acceptedCount;master=group->leader;strategies={"follow","new rpg","grind"};if(roleAfter>=0)player->role=uint8(roleAfter);if(player->denyAfterAccept)player->access=false;if(takeoverAfterAccept){takeoverAfterAccept->ai->human=true;takeoverAfterAccept=nullptr;}if(denyAccessAfterAccept){denyAccessAfterAccept->access=false;denyAccessAfterAccept=nullptr;}if(changeLeaderAfterAccept&&acceptedCount==changeLeaderAtAccept){group->ChangeLeader(changeLeaderAfterAccept);changeLeaderAfterAccept=nullptr;}return true;}
struct Config {bool naturalProgression=true;float SightDistance=45;bool IsInRandomAccountList(uint32 account){return account==1;}} sPlayerbotAIConfig;
namespace lfg {constexpr uint8 LFG_STATE_NONE=0;}
struct Lfg {uint8 GetState(ObjectGuid id){for(Player* p:online)if(p->guid==id)return p->lfg;return 0;}} lfgManager;Lfg* sLFGMgr=&lfgManager;
namespace DcModule {bool IsEnabled(){return moduleEnabled;}}
namespace DcEarnedPlay {bool Active(){return sPlayerbotAIConfig.naturalProgression;}}
namespace DcEarnedProgression {
 bool StrictDefault(){return strictProgression;}uint8 Expansion(Player* p){return p->era;}
 bool CanEnterMap(Player* p,uint32,float,float,float){++p->progressionCalls;return p->progression;}
}
struct ObjectMgr {
 std::map<uint32,AreaTrigger> triggers;std::map<uint32,AreaTriggerTeleport> targets;
 AreaTrigger const* GetAreaTrigger(uint32 id){auto found=triggers.find(id);return found==triggers.end()?nullptr:&found->second;}
 AreaTriggerTeleport const* GetAreaTriggerTeleport(uint32 id){auto found=targets.find(id);return found==targets.end()?nullptr:&found->second;}
 void const* GetAccessRequirement(uint32,Difficulty){return this;}
 CreatureTemplate const* GetCreatureTemplate(uint32){return nullptr;}
} objectMgr;ObjectMgr* sObjectMgr=&objectMgr;
struct MapMgr {Map::EnterState PlayerCannotEnter(uint32 map,Player* p,bool login){assert(!login);++p->entryCalls;auto* row=sMapStore.LookupEntry(map);if(row&&row->IsRaid()&&(!p->group||!p->group->isRaidGroup()))return Map::CANNOT_ENTER_NOT_IN_RAID;return p->entry&&p->Satisfy(sObjectMgr->GetAccessRequirement(map,p->GetDifficulty(true)),map,true)?Map::CAN_ENTER:Map::CANNOT_ENTER_UNSPECIFIED_REASON;}} mapMgr;MapMgr* sMapMgr=&mapMgr;
struct InstanceSaveMgr {uint32 PlayerGetDestinationInstanceId(Player* p,uint32,Difficulty){if(p->permanentBind)return p->bind;if(p->group)return p->group->leader->bind;return p->bind;}} instanceSaveMgr;InstanceSaveMgr* sInstanceSaveMgr=&instanceSaveMgr;
'''


HARNESS = r'''
#include "SharedRecruitment.inc"
#include "EarnedRaidComposition.cpp"
#include "EarnedRaidGroups.cpp"
using namespace EarnedRaidComposition;
void reset(){groups.clear();actors.clear();online.clear();maps={{0,{0}},{1,{1}},{409,{409}}};inviteCount=acceptedCount=bindCopyCount=changeLeaderAtAccept=0;raidMinLevel=10;takeoverAfterAccept=denyAccessAfterAccept=changeLeaderAfterAccept=nullptr;moduleEnabled=strictProgression=sPlayerbotAIConfig.naturalProgression=true;sPlayerbotAIConfig.SightDistance=45;sMapStore.rows={{0,{0,true,false}},{1,{1,true,false}}};difficulties.clear();objectMgr.triggers={{101,{101,0,0,0,0}}};objectMgr.targets.clear();}
Difficulty difficultyFor(uint32 map,uint8 size,uint8 era){return era==0&&(map==249||map==533)?RAID_DIFFICULTY_10MAN_HEROIC:era==2&&size==25?RAID_DIFFICULTY_25MAN_NORMAL:RAID_DIFFICULTY_10MAN_NORMAL;}
void roster(uint32 map=532,uint8 size=10,uint8 era=1){reset();auto const quota=Quota(map,size,era);assert(quota);sMapStore.rows[map]={map,false,true};objectMgr.targets[101]={map,10,20,30};difficulties[{map,difficultyFor(map,size,era)}]={size};for(uint8 i=0;i<size;++i){actors.push_back(std::make_unique<Player>(i+1));Player* p=actors.back().get();p->era=era;p->level=era==0?60:era==1?70:80;p->role=i<quota->tanks?0:i<quota->tanks+quota->healers?1:i<quota->tanks+quota->healers+quota->melee?2:3;p->power=p->role==0||p->role==2?POWER_RAGE:POWER_MANA;p->difficulty=difficultyFor(map,size,era);p->map=&maps[0];p->x=100+float(i%4);online.push_back(p);}}
Group* recruit(uint32 size=10,uint8 era=1){return EarnedRaidGroups::Recruit(101,uint8(size),era,online);}
void noInvites(){assert(!recruit());assert(inviteCount==0);for(Player* p:online)assert(!p->group&&!p->invitation&&p->invited==0);}
void rolledBack(){assert(bindCopyCount==0);for(Player* p:online){assert(!p->group&&!p->invitation&&!p->ai->master);assert(p->money==100&&p->xp==200&&p->items==4);assert(p->ai->strategies==std::set<std::string>({"new rpg","grind","travel"}));}}
void success(uint32 map,uint8 size,uint8 era){roster(map,size,era);Group* group=recruit(size,era);assert(group&&group->isRaidGroup()&&group->GetMembersCount()==size&&group->conversions==1);assert(inviteCount==uint32(size-1)&&acceptedCount==uint32(size-1));std::array<uint8,8> occupancy{};for(auto const& slot:group->GetMemberSlots()){assert(slot.group<size/5);++occupancy[slot.group];}for(uint8 i=0;i<size/5;++i)assert(occupancy[i]==5);for(Player* p:online){assert(p->group==group&&p->GetMapId()==0&&p->entryCalls==1&&p->satisfyCalls>=2&&p->progressionCalls>=2);assert(p->difficulty==difficultyFor(map,size,era)&&p->money==100&&p->xp==200&&p->items==4);}}
int main(){
 success(532,10,1);success(309,20,0);success(565,25,1);success(533,25,2);success(409,40,0);success(249,40,0);success(533,40,0);
 roster();online.front()->role=3;noInvites();roster();online[2]->role=3;noInvites();
 // Each candidate's own earned era and access is authoritative, including
 // restrictions that the grouped core might otherwise check on its leader.
 for(int i=0;i<10;++i){roster();online[i]->era=0;noInvites();roster();online[i]->access=false;online[i]->leaderOnly=true;noInvites();roster();online[i]->progression=false;noInvites();}
 roster();online[2]->level=69;noInvites();roster();online[2]->level=71;noInvites();
 roster();online[2]->difficulty=RAID_DIFFICULTY_25MAN_NORMAL;noInvites();
 roster(249,40,0);for(Player* p:online)p->difficulty=RAID_DIFFICULTY_10MAN_NORMAL;assert(!recruit(40,0)&&inviteCount==0);
 roster();difficulties.clear();noInvites();roster();difficulties.begin()->second.maxPlayers=25;noInvites();
 // Human clients, SelfBots and controlled random-account altbots are never
 // candidates. The same native ownership checks serve dungeon recruitment.
 roster();online[2]->session.headless=false;noInvites();roster();online[2]->ai->human=true;noInvites();
 roster();online[2]->session.account=42;noInvites();roster();online[2]->ai->master=online[0];noInvites();
 roster();online[2]->alive=false;noInvites();roster();online[2]->world=false;noInvites();roster();online[2]->gm=true;noInvites();
 roster();online[2]->bg=true;noInvites();roster();online[2]->queue=true;noInvites();roster();online[2]->lfg=1;noInvites();
 roster();online[2]->transfer=true;noInvites();roster();online[2]->flying=true;noInvites();roster();online[2]->vehicle=true;noInvites();roster();online[2]->transport=true;noInvites();roster();online[2]->session.loading=true;noInvites();
 roster();online[2]->combat=true;noInvites();roster();online[2]->map=&maps[1];noInvites();
 roster();online[2]->team=TEAM_HORDE;noInvites();roster();online[2]->phase=2;noInvites();roster();online[2]->x=1000;noInvites();
 roster();sPlayerbotAIConfig.SightDistance=1;noInvites();roster();for(Player* p:online)p->x=1200;noInvites();
 roster();online[2]->group=reinterpret_cast<Group*>(1);assert(!recruit()&&inviteCount==0);online[2]->group=nullptr;
 roster();online[2]->invitation=reinterpret_cast<Group*>(1);assert(!recruit()&&inviteCount==0);online[2]->invitation=nullptr;
 roster();objectMgr.triggers.clear();noInvites();roster();objectMgr.targets.clear();noInvites();
 roster();sMapStore.rows[0].continent=false;noInvites();roster();sMapStore.rows[532].raid=false;noInvites();
 roster();moduleEnabled=false;noInvites();roster();sPlayerbotAIConfig.naturalProgression=false;noInvites();roster();strictProgression=false;noInvites();
 // A native refusal is rolled back, including the pending leader invitation
 // when the first acceptance never establishes a group.
 roster();online[1]->ai->accept=false;assert(!recruit()&&inviteCount==1);rolledBack();
 for(Player* p:online)assert(p->ai->navChanges==0);
 roster();raidMinLevel=71;assert(!recruit()&&inviteCount==1&&groups.front()->conversions==0);rolledBack();
 roster();online[5]->ai->accept=false;assert(!recruit()&&inviteCount>1);rolledBack();
 roster();online[9]->entry=false;assert(!recruit()&&inviteCount==9);rolledBack();
 roster();online[0]->bind=41;online[9]->entry=false;assert(!recruit()&&inviteCount==9);rolledBack();for(size_t i=1;i<online.size();++i)assert(online[i]->bind==0);
 roster();online[9]->denyAfterAccept=true;assert(!recruit()&&inviteCount==9);rolledBack();
 roster();online[2]->ai->roleAfter=3;assert(!recruit()&&inviteCount>1);rolledBack();
 roster();online[9]->bind=42;online[9]->permanentBind=true;assert(!recruit()&&inviteCount==9);rolledBack();
 roster();online[0]->bind=41;online[0]->permanentBind=true;online[9]->bind=42;online[9]->permanentBind=true;assert(!recruit()&&inviteCount==9);rolledBack();
 roster();online[0]->bind=41;online[9]->bind=42;assert(recruit());
 // Ordinary acceptance hooks may transfer another character to a player.
 // Recheck immediately before each invitation and in the shared mutation point.
 roster();takeoverAfterAccept=online[2];assert(!recruit()&&inviteCount==1&&online[2]->invited==0);online[2]->ai->human=false;rolledBack();
 roster();denyAccessAfterAccept=online[2];assert(!recruit()&&inviteCount==1&&online[2]->invited==0);rolledBack();
 roster();online[2]->accessCheckTakeover=2;assert(!recruit()&&online[2]->invited==0);online[2]->ai->human=false;rolledBack();
 // A player takes over an already accepted member. Its established native
 // group and strategy state belong to the player and must remain untouched.
 roster();takeoverAfterAccept=online[1];assert(!recruit()&&inviteCount==1);assert(online[0]->group&&online[1]->group==online[0]->group&&online[1]->ai->human&&online[1]->ai->navChanges==0);
 roster();online[0]->bind=41;changeLeaderAfterAccept=online[1];changeLeaderAtAccept=2;assert(!recruit()&&inviteCount==2);assert(online[0]->group&&online[0]->group->GetMembersCount()==3&&online[0]->group->leader==online[1]&&bindCopyCount==1);for(size_t i=0;i<3;++i)assert(online[i]->ai->navChanges==0);
 // The native group setter itself does not check capacity. The caller must
 // refuse a sixth member in a target subgroup before invoking it.
 roster();auto plan=Plan(532,10,1,online);assert(!plan.empty());auto group=std::make_unique<Group>(Group{{100},online.front(),true,{},{},0});for(size_t i=0;i<6;++i)assert(group->AddMember(online[i]));assert(!Assign(group.get(),{online[5],0},10));assert(!Assign(group.get(),{online[5],2},10));
}
'''


def native_contracts(core):
    composition_contracts(core)
    group = (core / 'src/server/game/Groups/Group.cpp').read_text()
    member = function(group, 'bool Group::AddMember(Player* player,')
    assert 'm_subGroupsCounts[subGroup] < MAXGROUPSIZE' in member and 'player->SetRaidDifficulty(GetRaidDifficulty())' in member
    change = function(group, 'void Group::ChangeMembersGroup(ObjectGuid guid, uint8 group)')
    assert 'if (!isRaidGroup())' in change and 'slot->group = group;' in change
    assert 'HasFreeSlotSubGroup' not in change, 'The caller capacity contract changed'
    remove = function(group, 'bool Group::RemoveMember(ObjectGuid guid,')
    assert 'GetMembersCount() >' in remove and 'Disband();' in remove and 'ChangeLeader(' in remove
    assert 'sInstanceSaveMgr->CopyBinds(m_leaderGuid, newLeaderGuid, newLeader);' in function(group, 'void Group::ChangeLeader(')
    enter = function((core / 'src/server/game/Maps/MapMgr.cpp').read_text(), 'Map::EnterState MapMgr::PlayerCannotEnter(')
    assert enter.index('return Map::CANNOT_ENTER_NOT_IN_RAID;') < enter.index('player->Satisfy(')
    assert 'player->GetDifficulty(entry->IsRaid())' in enter and 'sInstanceSaveMgr->PlayerGetDestinationInstanceId' in enter
    invitation = (core / 'modules/mod-playerbots/src/Ai/Base/Actions/AcceptInvitationAction.cpp').read_text()
    for contract in ('HandleGroupAcceptOpcode(p)', 'botAI->SetMaster(inviter)', 'botAI->ResetStrategies()',
                     'bot->GetDistance(inviter) > sPlayerbotAIConfig.SightDistance'):
        assert contract in invitation
    handlers = (core / 'src/server/game/Handlers/GroupHandler.cpp').read_text()
    accept = function(handlers, 'void WorldSession::HandleGroupAcceptOpcode(')
    assert 'group->IsFull()' in accept and 'group->AddMember(GetPlayer())' in accept
    invite = function(handlers, 'void WorldSession::HandleGroupInviteOpcode(')
    assert '!group->IsLeader(invitingPlayer->GetGUID()) && !group->IsAssistant(invitingPlayer->GetGUID())' in invite
    assert 'group->AddLeaderInvite(invitingPlayer)' in invite and 'group->AddInvite(invitedPlayer)' in invite
    convert = function(handlers, 'void WorldSession::HandleGroupRaidConvertOpcode(')
    assert convert.index('group->CheckLevelForRaid()') < convert.index('group->ConvertToRaid()')
    assert 'group->IsLeader(GetPlayer()->GetGUID())' in convert and 'group->GetMembersCount() < 2' in convert
    level = function(group, 'bool Group::CheckLevelForRaid()')
    assert 'player->GetLevel() < sConfigMgr->GetOption<int32>("Group.Raid.LevelRestriction", 10)' in level
    player = (core / 'src/server/game/Entities/Player/PlayerStorage.cpp').read_text()
    satisfy = function(player, 'bool Player::Satisfy(')
    for contract in ('GetLevel()', 'HasItemCount(', 'GetQuestRewardStatus(', 'checkLeaderOnly'):
        assert contract in satisfy
    assert 'report' in satisfy
    ip = core / 'modules/mod-individual-progression/data/sql/world/base'
    for name, map_id in (('dungeon_onyxia.sql', 249), ('naxx40.sql', 533)):
        text = (ip / name).read_text()
        assert re.search(rf'\([0-9]+,\s*{map_id},\s*2,.*?40', text), f'{name}: native forty-member difficulty override changed'
    save = function((core / 'src/server/game/Instances/InstanceSaveMgr.cpp').read_text(),
                    'uint32 InstanceSaveMgr::PlayerGetDestinationInstanceId(')
    assert save.index('if (ipb && ipb->perm)') < save.index('if (Group* g = player->GetGroup())')
    assert 'g->GetLeaderGUID()' in save and 'return 0;' in save


def shared_production(source):
    coordinator = (source / 'EarnedDungeonParties.cpp').read_text()
    navigation = re.search(r'constexpr std::array<char const\*, 9> navigation\{\{.*?\}\};', coordinator, re.DOTALL)
    assert navigation
    definitions = '\n'.join(function(coordinator, signature) for signature in (
        'struct Route', 'constexpr uint8 ExpansionLevelCap(',
        'bool Eligible(Player* player, Route const& route', 'bool Owned(Player* player, Player* leader)',
        'void SaveNavigation(Player* member,', 'bool CanEnter(Player* player, AreaTriggerTeleport const& target)',
    ))
    # function() omits a struct definition's trailing semicolon.
    route = function(coordinator, 'struct Route')
    definitions = definitions.replace(route, route + ';', 1)
    return ('#include "DcEarnedRecruitment.h"\nnamespace {\n' + navigation.group(0) + '\n' + definitions +
            '\n}\n' + function(coordinator, 'namespace DcEarnedRecruitment'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source_argument(parser)
    args = parser.parse_args()
    core = prepared_core()
    source = args.source or core / 'modules/mod-dungeon-clear/src'
    native_contracts(core)
    with tempfile.TemporaryDirectory(prefix='earned-raid-groups-') as directory:
        work = Path(directory)
        (work / 'NativeStubs.h').write_text(STUBS)
        for name in ('Define.h', 'AiObjectContext.h', 'Player.h', 'PlayerbotAI.h', 'Playerbots.h',
                     'DcEarnedPlay.h', 'DcEarnedProgression.h', 'DcModuleEnable.h', 'DBCStores.h', 'Group.h',
                     'ObjectMgr.h', 'InstanceSaveMgr.h', 'CreatureData.h', 'SpellMgr.h', 'WorldPacket.h', 'WorldSession.h'):
            (work / name).write_text('#include "NativeStubs.h"\n')
        for name in ('EarnedRaidGroups.h', 'EarnedRaidGroups.cpp', 'EarnedRaidComposition.h',
                     'EarnedRaidComposition.cpp', 'DcEarnedRecruitment.h'):
            shutil.copyfile(source / name, work / name)
        (work / 'SharedRecruitment.inc').write_text(shared_production(source))
        (work / 'fixture.cpp').write_text(HARNESS)
        flags = ['-std=c++20', '-O1', '-Wall', '-Wextra', '-Wno-unused-parameter', '-I', str(work)]
        if os.name != 'nt':
            flags += [*SANITIZER_FLAGS, '-no-pie']
        binary = work / 'fixture'
        subprocess.run([cxx(), *flags, str(work / 'fixture.cpp'), '-o', str(binary)], check=True)
        result = run_fixture([str(binary)])
        if result.returncode:
            raise SystemExit(result.stdout + result.stderr)
        mutations = (
            ('own earned era ignored', 'SharedRecruitment.inc',
             'DcEarnedProgression::Expansion(player) != route.expansion', 'false'),
            ('human client recruited', 'SharedRecruitment.inc', '!player->GetSession()->IsHeadless()', 'false'),
            ('controlled client master recruited', 'SharedRecruitment.inc', 'ai->HasGameClientMaster() ||', 'false ||'),
            ('controlled altbot recruited', 'SharedRecruitment.inc',
             '(ai->GetMaster() && ai->GetMaster() != leader)', 'false'),
            ('nonrandom account recruited', 'SharedRecruitment.inc',
             '!sPlayerbotAIConfig.IsInRandomAccountList(player->GetSession()->GetAccountId())', 'false'),
            ('minimum level relaxed', 'SharedRecruitment.inc', 'player->GetLevel() < route.minLevel', 'false'),
            ('era level cap relaxed', 'SharedRecruitment.inc',
             'player->GetLevel() > (leader ? ExpansionLevelCap(route.expansion) : route.maxLevel)', 'false'),
            ('personal progression ignored', 'EarnedRaidGroups.cpp',
             'DcEarnedProgression::CanEnterMap(player, target->target_mapId, target->target_X, target->target_Y,\n                                                target->target_Z)', 'true'),
            ('personal attunement ignored before grouping', 'EarnedRaidGroups.cpp',
             'player->Satisfy(sObjectMgr->GetAccessRequirement(target->target_mapId, difficulty),\n                                target->target_mapId, false)', 'true'),
            ('full native entry skipped after grouping', 'EarnedRaidGroups.cpp',
             '!DcEarnedRecruitment::CanEnter(member.player, *target)', 'false'),
            ('selected native difficulty ignored', 'EarnedRaidGroups.cpp',
             'player->GetRaidDifficulty() == difficulty &&', 'true &&'),
            ('native capacity ignored', 'EarnedRaidGroups.cpp', 'mapDifficulty->maxPlayers != size', 'false'),
            ('different faction recruited', 'EarnedRaidGroups.cpp',
             'player->GetTeamId() == tank->GetTeamId() &&', 'true &&'),
            ('different phase recruited', 'EarnedRaidGroups.cpp',
             '(player->GetPhaseMask() & tank->GetPhaseMask())', 'true'),
            ('distant bot recruited', 'EarnedRaidGroups.cpp',
             'player->GetExactDist(tank) <= std::min(60.0f, sPlayerbotAIConfig.SightDistance)', 'true'),
            ('distant raid staging allowed', 'EarnedRaidGroups.cpp',
             'tank->GetExactDist(entrance->x, entrance->y, entrance->z) > 1000.0f', 'false'),
            ('inside staging allowed', 'EarnedRaidGroups.cpp', '!sourceMap->IsContinent()', 'false'),
            ('wrong map type admitted', 'EarnedRaidGroups.cpp', '!raid->IsRaid()', 'false'),
            ('module disabled gate removed', 'EarnedRaidGroups.cpp', '!DcModule::IsEnabled() ||', 'false ||'),
            ('natural progression gate removed', 'EarnedRaidGroups.cpp', '!DcEarnedPlay::Active() ||', 'false ||'),
            ('strict progression gate removed', 'EarnedRaidGroups.cpp', '!DcEarnedProgression::StrictDefault()', 'false'),
            ('failed invitation left pending', 'EarnedRaidGroups.cpp', 'player->UninviteFromGroup();', '(void)player;'),
            ('failed group left established', 'EarnedRaidGroups.cpp', 'current->RemoveMember(player->GetGUID());', '(void)current;'),
            ('original navigation not restored', 'EarnedRaidGroups.cpp',
             'DcEarnedRecruitment::RestoreNavigation(player, member->navigation);', '(void)member;'),
            ('sixth subgroup member allowed', 'EarnedRaidGroups.cpp', '}) >= 5)', '}) >= 6)'),
            ('subgroup range ignored', 'EarnedRaidGroups.cpp', 'if (member.subgroup >= size / 5)', 'if (false)'),
            ('ownership lost at invitation mutation point', 'SharedRecruitment.inc',
             '!::Owned(leader, nullptr) || !::Owned(member, nullptr)', 'false'),
            ('personal access not rechecked before next invitation', 'EarnedRaidGroups.cpp',
             '!available(player) ||', 'false ||'),
            ('different permanent lockouts accepted', 'EarnedRaidGroups.cpp',
             'sInstanceSaveMgr->PlayerGetDestinationInstanceId(member.player, target->target_mapId, difficulty) != destination', 'false'),
            ('TBC twenty-five uses Wrath difficulty', 'EarnedRaidGroups.cpp',
             'expansion == 2 && size == 25 ?', 'size == 25 ?'),
            ('rollback copies leader lockouts to another bot', 'EarnedRaidGroups.cpp',
             'for (auto member = saved.rbegin(); member != saved.rend(); ++member)',
             'for (auto member = saved.begin(); member != saved.end(); ++member)'),
            ('changed raid leader still treated as owned', 'EarnedRaidGroups.cpp',
             '(group->GetGUID() != groupId || group->GetLeaderGUID() != leader->GetGUID())',
             '(group->GetGUID() != groupId)'),
            ('native raid conversion requirement bypassed', 'EarnedRaidGroups.cpp',
             'leader->GetSession()->HandleGroupRaidConvertOpcode(convert);', 'group->ConvertToRaid();'),
        )
        # The transaction deliberately checks accepted roles both during each
        # join and at final validation. Remove the complete redundant gate to
        # demonstrate that an acceptance reset cannot weaken the quota.
        production = (work / 'EarnedRaidGroups.cpp').read_text()
        without_roles = production.replace('Role(plan[j].player) != saved[j].role', 'false').replace(
            'Role(member.player) != saved[members.size()].role', 'false').replace(
            'auto const currentPlan = EarnedRaidComposition::Plan(target->target_mapId, size, expansion, members);',
            'auto const currentPlan = plan;')
        assert production != without_roles
        mutations += (('accepted role changes ignored', 'EarnedRaidGroups.cpp', production, without_roles),)
        reject_mutants(work, mutations,
                       lambda tree, output: [cxx(), '-std=c++20', '-O1', '-I', str(tree),
                                             str(tree / 'fixture.cpp'), '-o', str(output)],
                       'Earned raid grouping')
    print('Native raid invitations, individual earned access, subgroup capacity and rollback verified')


if __name__ == '__main__':
    main()
