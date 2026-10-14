"""Compile the actual LFG hooks and exercise earned-era/native-lock behavior."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

from FixtureSupport import TIMEOUT, cxx, prepared_core, run_fixture


STUBS = r'''
#pragma once
#include <algorithm>
#include <cstdint>
#include <initializer_list>
#include <map>
#include <set>
#include <string>
#include <vector>
using uint8=uint8_t; using uint32=uint32_t;
struct ObjectGuid {
 uint32 value=0; bool IsEmpty()const{return !value;}
 bool operator<(ObjectGuid r)const{return value<r.value;}
 bool operator==(ObjectGuid r)const{return value==r.value;}
 bool operator!=(ObjectGuid r)const{return value!=r.value;}
};
class Player; class Group;
namespace lfg {
 constexpr uint8 LFG_TYPE_RANDOM=6;
 constexpr uint32 LFG_LOCKSTATUS_QUEST_NOT_COMPLETED=1022;
 struct LFGDungeonData {uint32 id=0; uint32 map=0;uint8 difficulty=0;uint8 expansion=0;uint8 type=1;bool seasonal=false;};
 struct Lfg5Guids {std::vector<ObjectGuid> guids;std::string toString()const{return "proposal";}};
}
struct WorldSession {bool headless=false;uint32 account=0;bool IsHeadless()const{return headless;}uint32 GetAccountId()const{return account;}};
struct GroupReference {
 Player* source=nullptr;GroupReference* following=nullptr;
 Player* GetSource(){return source;}GroupReference* next(){return following;}
};
class Group {
public: ObjectGuid guid{100};std::vector<GroupReference> refs;
 ObjectGuid GetGUID()const{return guid;}
 GroupReference* GetFirstMember(){return refs.empty()?nullptr:&refs[0];}
 void Set(std::initializer_list<Player*> members);
};
class Player {
public:
 ObjectGuid guid;uint8 level=60,tier=0;Group* group=nullptr;WorldSession session;
 bool gm=false;uint8 cls=1;bool dkRewarded=false;int syntheticRewards=0,refreshes=0;
 explicit Player(uint32 id=1):guid{id}{}
 Group* GetGroup(){return group;}uint8 GetLevel(){return level;}ObjectGuid GetGUID(){return guid;}
 WorldSession* GetSession(){return &session;}std::string GetName(){return "character";}
 bool IsClass(uint8 id){return cls==id;}bool IsGameMaster(){return gm;}
 bool IsQuestRewarded(uint32){return dkRewarded;}uint8 GetTeamId(bool){return 0;}
 void SetRewardedQuest(uint32){++syntheticRewards;dkRewarded=true;}
};
void Group::Set(std::initializer_list<Player*> members){refs.clear();for(Player* p:members){p->group=this;refs.push_back({p,nullptr});}for(size_t i=0;i+1<refs.size();++i)refs[i].following=&refs[i+1];}
struct ConfigMgr {std::map<std::string,uint32> opts;template<class T>T GetOption(char const* name,T fallback){auto it=opts.find(name);return it==opts.end()?fallback:static_cast<T>(it->second);}};
ConfigMgr config;ConfigMgr* sConfigMgr=&config;
struct IndividualProgression {
 bool enabled=true,strict=true;uint8 progressionLimit=0;
 bool IsStrictDefaultProgression()const{return enabled&&strict;}
 bool hasPassedProgression(Player* p,uint8 state)const{return p&&p->tier>=state&&(!progressionLimit||state<=progressionLimit);}
};
IndividualProgression ip;IndividualProgression* sIndividualProgression=&ip;
constexpr uint8 PROGRESSION_PRE_TBC=8,PROGRESSION_TBC_TIER_5=13;
struct PlayerbotAIConfig {std::set<uint32> accounts;bool IsInRandomAccountList(uint32 id){return accounts.count(id)!=0;}};
PlayerbotAIConfig sPlayerbotAIConfig;
struct LFGMgr {
 std::map<uint32,lfg::LFGDungeonData> data;
 lfg::LFGDungeonData const* GetLFGDungeon(uint32 id){auto it=data.find(id);return it==data.end()?nullptr:&it->second;}
 void InitializeLockedDungeons(Player* p,Group const* =nullptr){++p->refreshes;}
};
LFGMgr lfgMgr;LFGMgr* sLFGMgr=&lfgMgr;
constexpr uint8 CLASS_DEATH_KNIGHT=6,TEAM_ALLIANCE=0;
constexpr int GLOBALHOOK_ON_INITIALIZE_LOCKED_DUNGEONS=1,GLOBALHOOK_ON_AFTER_INITIALIZE_LOCKED_DUNGEONS=2,GLOBALHOOK_CAN_CREATE_LFG_PROPOSAL=3;
constexpr int PLAYERHOOK_ON_QUEUE_RANDOM_DUNGEON=1,PLAYERHOOK_CAN_JOIN_LFG=2,PLAYERHOOK_ON_LEVEL_CHANGED=3,PLAYERHOOK_ON_LOGOUT=4,GROUPHOOK_ON_DISBAND=1;
struct WorldScript {explicit WorldScript(char const*){}virtual ~WorldScript()=default;virtual void OnAfterConfigLoad(bool){};};
struct GlobalScript {GlobalScript(char const*,std::initializer_list<int>){}virtual ~GlobalScript()=default;virtual void OnInitializeLockedDungeons(Player*,uint8&,uint32&,lfg::LFGDungeonData const*){}virtual void OnAfterInitializeLockedDungeons(Player*){}virtual bool CanCreateLfgProposal(lfg::Lfg5Guids const&){return true;}};
struct PlayerScript {PlayerScript(char const*,std::initializer_list<int>){}virtual ~PlayerScript()=default;virtual void OnPlayerQueueRandomDungeon(Player*,uint32&){}virtual bool OnPlayerCanJoinLfg(Player*,uint8,std::set<uint32>&,std::string const&){return true;}virtual void OnPlayerLevelChanged(Player*,uint8){}virtual void OnPlayerLogout(Player*){}};
struct GroupScript {GroupScript(char const*,std::initializer_list<int>){}virtual ~GroupScript()=default;virtual void OnDisband(Group*){}};
#define LOG_INFO(...) ((void)0)
#define LOG_ERROR(...) ((void)0)
#define LOG_DEBUG(...) ((void)0)
'''

HARNESS = r'''
#include "LfgProgression.cpp"
#include <cassert>
#include <iostream>
int main(){
 LfgProgressionWorld world;LfgProgressionGlobal locks;LfgProgressionPlayer queue;
 world.OnAfterConfigLoad(false);
 unsigned checked=0;
 Player p(1);p.session.headless=true;p.session.account=11;sPlayerbotAIConfig.accounts.insert(11);
 for(uint8 tier=0;tier<18;++tier)for(uint8 level:{10,60,70,80})for(uint8 exp:{0,1,2}){
  p.tier=tier;p.level=level;lfg::LFGDungeonData d{1,389,0,exp,1,false};
  uint32 lock=0;uint8 actualLevel=level;locks.OnInitializeLockedDungeons(&p,actualLevel,lock,&d);
  uint8 earned=tier>=13?2:tier>=8?1:0;
  assert((lock!=0)==(exp>earned));assert(actualLevel==level);locks.OnAfterInitializeLockedDungeons(&p);++checked;
  for(uint32 reason:{1u,2u,1022u,1041u}){
   lock=reason;locks.OnInitializeLockedDungeons(&p,actualLevel,lock,&d);assert(lock==reason);assert(p.syntheticRewards==0);locks.OnAfterInitializeLockedDungeons(&p);++checked;
  }
 }
 // DK starting quests remain required for bots, and original lock reason is never cleared.
 p.cls=CLASS_DEATH_KNIGHT;p.dkRewarded=false;uint32 lock=lfg::LFG_LOCKSTATUS_QUEST_NOT_COMPLETED;uint8 level=60;
 lfg::LFGDungeonData classic{3,389,0,0,1,false};locks.OnInitializeLockedDungeons(&p,level,lock,&classic);
 assert(lock==lfg::LFG_LOCKSTATUS_QUEST_NOT_COMPLETED&&!p.dkRewarded&&p.syntheticRewards==0);p.cls=1;
 // Inviting a random bot does not copy the group's earned expansion.
 Player human(2),bot(3);human.tier=13;human.level=80;bot.tier=0;bot.level=60;
 bot.session.headless=true;bot.session.account=11;Group party;party.Set({&human,&bot});
 uint32 random=LfgProgression::RDF_WOTLK;queue.OnPlayerQueueRandomDungeon(&human,random);assert(random==LfgProgression::RDF_CLASSIC);
 random=LfgProgression::RDF_WOTLK_HEROIC;queue.OnPlayerQueueRandomDungeon(&bot,random);assert(random==LfgProgression::RDF_CLASSIC);
 bot.tier=8;random=LfgProgression::RDF_WOTLK_HEROIC;queue.OnPlayerQueueRandomDungeon(&human,random);assert(random==LfgProgression::RDF_TBC_HEROIC);
 bot.tier=13;random=LfgProgression::RDF_WOTLK;queue.OnPlayerQueueRandomDungeon(&human,random);assert(random==LfgProgression::RDF_WOTLK);
 // Each join rebuilds every member's native lock map, including unchanged-level progression.
 std::set<uint32> selected{259};queue.OnPlayerCanJoinLfg(&human,1,selected,"");assert(human.refreshes==1&&bot.refreshes==1);
 bot.tier=0;queue.OnPlayerCanJoinLfg(&human,1,selected,"");assert(human.refreshes==2&&bot.refreshes==2);
 // Realm progression ceilings and unsupported/custom chains fail closed.
 ip.progressionLimit=7;p.tier=17;p.level=80;p.group=nullptr;random=261;queue.OnPlayerQueueRandomDungeon(&p,random);assert(random==258);
 ip.progressionLimit=12;random=261;queue.OnPlayerQueueRandomDungeon(&p,random);assert(random==259);
 ip.progressionLimit=0;ip.strict=false;random=261;queue.OnPlayerQueueRandomDungeon(&p,random);assert(random==258);
 ip.strict=true;ip.enabled=false;random=261;queue.OnPlayerQueueRandomDungeon(&p,random);assert(random==261);ip.enabled=true;
 // Random category entries stay usable for the remap; specific later-era entries remain locked.
 p.tier=0;p.level=60;lfg::LFGDungeonData randomEntry{259,0,0,1,lfg::LFG_TYPE_RANDOM,false};lock=0;
 locks.OnInitializeLockedDungeons(&p,level,lock,&randomEntry);assert(lock==0);locks.OnAfterInitializeLockedDungeons(&p);
 config.opts["LfgProgression.Enable"]=0;world.OnAfterConfigLoad(true);random=261;queue.OnPlayerQueueRandomDungeon(&p,random);assert(random==261);
 int before=p.refreshes;queue.OnPlayerCanJoinLfg(&p,1,selected,"");assert(p.refreshes==before);
 std::cout<<"LFG production hooks: "<<checked<<" era/native-lock cases; mixed groups, queue refresh, DK gates, disabled/custom chains passed\n";
}
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path)
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[2]
    source=args.source or prepared_core(repo)/'modules/mod-lfg-progression/src'
    if not source.is_dir():
        raise SystemExit('PrepareModules.cmake must prepare mod-lfg-progression first')
    compiler=cxx()
    with tempfile.TemporaryDirectory(prefix='lfg-earned-') as temp:
        work=Path(temp)
        (work/'NativeStubs.h').write_text(STUBS)
        for name in ('Config.h','Group.h','LFG.h','LFGMgr.h','Log.h','ObjectMgr.h','Player.h','ScriptMgr.h','WorldSession.h','IndividualProgression.h','PlayerbotAIConfig.h'):
            (work/name).write_text('#include "NativeStubs.h"\n')
        (work/'fixture.cpp').write_text(HARNESS)
        exe=work/('fixture.exe' if os.name=='nt' else 'fixture')
        subprocess.run([compiler,'-std=c++20','-O1','-Wall','-Wextra','-Wno-unused-variable','-I',str(work),'-I',str(source),str(work/'fixture.cpp'),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True,timeout=TIMEOUT)
        # The original high-level shortcut must fail this same production fixture.
        original=(source/'LfgProgression.cpp').read_text()
        mutation=original.replace('return LfgProgression::PlayerExpansion(g_settings, level, IpTier(player));','return LfgProgression::ExpansionForLevel(g_settings, level);')
        if mutation==original:
            raise SystemExit('High-level shortcut mutation was not applied')
        (work/'LfgProgression.cpp').write_text(mutation)
        subprocess.run([compiler,'-std=c++20','-O1','-I',str(work),'-I',str(source),str(work/'fixture.cpp'),'-o',str(exe)],check=True)
        if run_fixture([str(exe)],'Legacy level shortcut mutant').returncode==0:
            raise SystemExit('Production fixture did not reject the legacy level shortcut')
        print('LFG production mutation: level-based era bypass rejected')

if __name__=='__main__':
    main()
