"""Exercise production Pull Lab and movement/recovery natural gates."""
import argparse
import os
from pathlib import Path
import re
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


STUBS = r'''
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
using uint32=std::uint32_t;
using Tail=std::string;
std::vector<std::string> calls;
bool enabled=true,natural=true,online=true;
uint32 expectedDiff=1000;
struct Player{};Player issuer;
struct Session{Player* GetPlayer(){return &issuer;}} session;
struct ChatHandler{
 bool console=true;
 std::vector<std::string> messages;
 Session* GetSession(){return console?nullptr:&session;}
 void SendSysMessage(std::string const& message){messages.push_back(message);}
};
namespace DcModule{bool IsEnabled(){return enabled;}}
struct PlayerbotAIConfig{bool& naturalProgression=natural;} sPlayerbotAIConfig;
namespace DcEarnedPlay{NATIVE_ACTIVE}
namespace DcProvisionBudget{void Reset(){calls.push_back("budget");}}
namespace EarnedDungeonParties{void Update(uint32 diff){assert(diff==expectedDiff);calls.push_back("earned");}}
namespace DcFollowerLifecycle{
 void ReapOrphanedFollows(){calls.push_back("orphaned");}
 void ReapStrandedPassives(){calls.push_back("passives");}
}
namespace DcStatusPublisher{void TickStatusPushes(uint32 diff){assert(diff==expectedDiff);calls.push_back("status");}}
namespace DcLyceum{void Tick(uint32 diff,bool){assert(diff==expectedDiff);calls.push_back("lyceum");}}
namespace DcCombatPurge{void Tick(uint32 diff){assert(diff==expectedDiff);calls.push_back("purge");}}
namespace DcStrategyGate{void ReconcileAllBots(){calls.push_back("strategies");}}
namespace DcTestDriver{
 void Tick(){calls.push_back("driver");}
 bool EnsureOnline(std::string* why){calls.push_back("login");*why="driver pending";return online;}
 Player* Get(){return &issuer;}
}
struct DcPathWorker{
 static DcPathWorker& Instance(){static DcPathWorker worker;return worker;}
 void Sweep(uint32 ttl){assert(ttl==DC_ASYNC_PATH_RESULT_TTL_MS);calls.push_back("paths");}
};
#define TICK_MANAGER(name,label) struct name{static name& Instance(){static name manager;return manager;}void Tick(uint32 diff){assert(diff==expectedDiff);calls.push_back(label);}};
TICK_MANAGER(DcDungeonQueueFillManager,"dungeon queue")
TICK_MANAGER(DcBgQueueFillManager,"battleground queue")
TICK_MANAGER(DcTestPlanManager,"plan")
TICK_MANAGER(DcTestRunManager,"runs")
struct DcLabManager{
 std::vector<std::string> ids;uint32 seed=0,repeat=0;std::string sweep;
 static DcLabManager& Instance(){static DcLabManager manager;return manager;}
 void Tick(uint32 diff){assert(diff==expectedDiff);calls.push_back("lab");}
 std::vector<std::string> ListIds(std::string const& glob)const{
  calls.push_back("list");assert(glob=="tank-*");return {"tank-one","tank-two"};
 }
 std::string Enqueue(Player* player,std::vector<std::string> const& scenarios,uint32 seedValue,
                     uint32 repeats,std::string const& sweepValue,std::string* msg){
  assert(player==&issuer);calls.push_back("enqueue");ids=scenarios;seed=seedValue;repeat=repeats;sweep=sweepValue;
  *msg="queued";return "batch-id";
 }
 std::string StatusText(){calls.push_back("lab status");return "status";}
 void Stop(std::string* msg){calls.push_back("lab stop");*msg="stopped";}
};
struct WorldScript{virtual void OnUpdate(uint32)=0;virtual ~WorldScript()=default;};
struct FixtureWorld:WorldScript{
 NATIVE_UPDATE
 uint32 _gateSweepAccumMs=0;
};
NATIVE_COMMANDS
'''

HARNESS = r'''
int main(){
 FixtureWorld world;
 // Natural ticks retain real party work and cleanup but never provision labs.
 world.OnUpdate(1000);
 assert((calls==std::vector<std::string>{"budget","dungeon queue","battleground queue","lyceum","earned","orphaned","passives","paths","status"}));
 calls.clear();expectedDiff=2000;world.OnUpdate(2000);
 assert((calls==std::vector<std::string>{"budget","dungeon queue","battleground queue","lyceum","earned","orphaned","passives","paths","status","strategies"}));
 // Existing unrestricted test-driver, plan, run and lab ordering stays intact.
 natural=false;calls.clear();expectedDiff=1000;world.OnUpdate(1000);
 assert((calls==std::vector<std::string>{"budget","dungeon queue","battleground queue","lyceum","earned","orphaned","passives","paths","status","purge","driver","plan","runs","lab"}));
 enabled=false;calls.clear();world.OnUpdate(1000);
 assert((calls==std::vector<std::string>{"budget","dungeon queue","battleground queue","lyceum","earned"}));
 enabled=true;natural=true;
 // Both command entry points refuse before a console driver's login or listing.
 for(bool console:{false,true})for(bool batch:{false,true}){
  ChatHandler handler;handler.console=console;calls.clear();
  assert(batch?HandleLabBatch(&handler,"tank-* seed=7 repeat=3 sweep=events"):HandleLabRun(&handler,"tank-one seed=7 repeat=3 sweep=events"));
  assert(calls.empty()&&handler.messages.size()==1&&handler.messages[0].find("natural progression")!=std::string::npos);
 }
 // Status and cancellation remain usable while natural progression is active.
 ChatHandler handler;calls.clear();assert(HandleLabStatus(&handler)&&HandleLabStop(&handler));
 assert((calls==std::vector<std::string>{"lab status","lab stop"}));
 assert((handler.messages==std::vector<std::string>{"status","stopped"}));
 natural=false;
 for(bool console:{false,true})for(bool batch:{false,true}){
  ChatHandler command;command.console=console;calls.clear();
  assert(batch?HandleLabBatch(&command,"tank-* seed=7 repeat=3 sweep=events"):HandleLabRun(&command,"tank-one seed=7 repeat=3 sweep=events"));
  std::vector<std::string> expected;if(console)expected.push_back("login");if(batch)expected.push_back("list");expected.push_back("enqueue");assert(calls==expected);
  auto const& lab=DcLabManager::Instance();
  assert((lab.ids==(batch?std::vector<std::string>{"tank-one","tank-two"}:std::vector<std::string>{"tank-one"})));
  assert(lab.seed==7&&lab.repeat==3&&lab.sweep=="events"&&command.messages.back()=="queued");
 }
 // Existing disabled-module and pending-driver paths keep their early returns.
 enabled=false;calls.clear();handler.messages.clear();assert(HandleLabRun(&handler,"tank-one"));assert(calls.empty()&&handler.messages.size()==1);
 enabled=true;online=false;calls.clear();handler.messages.clear();assert(HandleLabBatch(&handler,"tank-*"));
 assert((calls==std::vector<std::string>{"login"})&&handler.messages.back()=="driver pending");
 // Invalid arguments never start a driver or enqueue a scenario.
 online=true;calls.clear();handler.messages.clear();assert(HandleLabRun(&handler,""));assert(HandleLabBatch(&handler,"tank-* extra"));assert(calls.empty()&&handler.messages.size()==2);
 std::cout<<"Dungeon Pull Lab: natural tick/run/batch gates and ordinary command paths passed\n";
}
'''


SHORTCUT_STUBS = r'''
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <map>
#include <optional>
#include <string>
#include <type_traits>
#include <vector>
using uint8=uint8_t;using uint32=uint32_t;using uint64=uint64_t;
#define LOG_INFO(...) ((void)0)
#define LOG_DEBUG(...) ((void)0)
#define LOG_WARN(...) ((void)0)
bool natural=true;uint32 nowMs=100000;
struct PlayerbotAIConfig{bool& naturalProgression=natural;} sPlayerbotAIConfig;
namespace DcEarnedPlay{NATIVE_ACTIVE}
uint32 getMSTime(){return nowMs;}
struct Item{};class Player;class PlayerbotAI;class Group;
struct SpellCastTargets{Player* target=nullptr;void SetUnitTarget(Player* p){target=p;}};
struct Guid{uint64 id=0;uint64 GetRawValue()const{return id;}};
struct MotionMaster{int clears=0;void Clear(){++clears;}};
struct Player{Group* group=nullptr;uint64 id=0;bool alive=true,underwater=true,combat=false,vehicle=false,owned=false,cooldown=false;int teleports=0,grants=0,drinks=0;Item item;PlayerbotAI* ai=nullptr;MotionMaster motion;
 Group* GetGroup(){return group;}bool IsInWorld(){return true;}float GetExactDist(float x,float y,float z){return std::sqrt(x*x+y*y+z*z);}
 bool IsAlive(){return alive;}bool IsUnderWater(){return underwater;}bool IsInCombat(){return combat;}bool GetVehicle(){return vehicle;}Guid GetGUID(){return {id};}
 uint32 GetInstanceId(){return 1;}uint32 GetMapId(){return 48;}float GetPositionX(){return 0;}float GetPositionY(){return 0;}float GetPositionZ(){return 0;}float GetOrientation(){return 0;}
 std::string GetName(){return "fixture";}MotionMaster* GetMotionMaster(){return &motion;}
 void NearTeleportTo(float,float,float,float,bool=false,bool=false,bool=false){++teleports;}void RemoveUnitMovementFlag(uint32){}
 Item* GetItemByEntry(uint32 id){assert(id==5996);return owned?&item:nullptr;}void AddItem(uint32 id,uint32 count){assert(id==5996&&count==1);owned=true;++grants;}
 bool HasSpellCooldown(uint32 id){assert(id==7178);return cooldown;}void CastItemUseSpell(Item* i,SpellCastTargets const& target,uint32,uint32){assert(i==&item&&target.target==this);++drinks;}
};
struct GroupReference{Player* player;GroupReference* link=nullptr;Player* GetSource(){return player;}GroupReference* next(){return link;}};
class Group{public:GroupReference* first=nullptr;GroupReference* GetFirstMember(){return first;}};
#define GET_PLAYERBOT_AI(p) ((p)->ai)
constexpr uint32 MOVEMENTFLAG_FALLING=1,MOVEMENTFLAG_FALLING_FAR=2,MOVEMENTFLAG_SWIMMING=4;
// The native event/chain producer fields are asserted before these API doubles compile.
enum class EventStepKind:uint8{MoveTo,RawPath,Jump,Wait};
struct EventStep{EventStepKind kind=EventStepKind::Wait;bool swim=false;};
struct Fall{bool enabled=true;uint32 maxFalls=2;float finalX=1,finalY=2,finalZ=3,retryX=4,retryY=5,retryZ=6;bool Contains(float,float,float)const{return true;}};
struct DungeonEvent{uint32 id=1,mapId=48;std::string name="chain";std::vector<EventStep> steps{{EventStepKind::RawPath}};Fall fall;};
struct DungeonBossInfo{};
struct DcChainState{uint32 eventId=0,mapId=0,instanceId=0,stepIndex=0,startedMs=0,falls=0;DungeonEvent const* ev=nullptr;bool done=false;void Reset(){*this={};}void BeginStep(uint32){}};
struct DcApproachState{uint32 longPathTargetEntry=1,longPathExpiresMs=1,pendingPathJob=1,pendingPathSinceMs=1;};
struct DungeonFollowerState{};
namespace ChunkedPathfinder{struct Result{};}
namespace DcKey{constexpr char const* ChainState="chain",*ApproachState="approach",*LongPath="long",*FollowerState="follower",*CurrentHop="hop",*NextDungeonBoss="next";}
template<class T>struct Value{std::remove_reference_t<T> data{};auto& Get(){return data;}void Reset(){data={};}void Set(std::remove_reference_t<T> v){data=v;}};
struct AiObjectContext{Value<DcChainState&> chain;template<class T>Value<T>* GetValue(char const*){if constexpr(std::is_same_v<T,DcChainState&>)return &chain;else{static Value<T> v;return &v;}}};
struct PlayerbotAI{};
struct DcRunState{bool enabled=true,paused=false;uint32 chainFalls=0;std::map<uint64,uint32> underwaterSinceMs;void SetTestExtra(char const*,std::string,bool){}} run;
DcRunState* LeaderRun(Player*){return &run;}
namespace DcRun{DcRunState& Of(PlayerbotAI*){return run;}}
Player* leader=nullptr;DungeonEvent const* live=nullptr;std::vector<Player*> members;
namespace DcLeaderSignal{bool IsDungeonClearLeader(Player* p){return p==leader;}Player* FindLeaderTank(Player*){return leader;}DungeonEvent const* GetLeaderPartyWideChain(Player*){return live;}}
std::vector<Player*> PartyOnMap(Player*){return members;}
namespace DcFormGate{void DropBlockingForm(Player*,Item*){}}
#include "DcBreathSource.h"
namespace DcBreathProvision{void WatchdogTick(Player*);}
#include "ChainRelease.h"
namespace DcPartyWideChain{
 constexpr uint32 DC_CHAIN_SPACING_MS=8000;
 enum class StepOutcome:uint8{Running,Done,Fell,Stalled};
 bool FallArmed(DungeonEvent const&,uint32){return true;}
 bool IsOnSwimLeg(Player*){return false;}
 StepOutcome DriveStep(Player*,PlayerbotAI*,AiObjectContext*,DungeonEvent const&,EventStep const&,DcChainState&);
 bool DriveFollower(Player*,PlayerbotAI*,AiObjectContext*);
 bool HandleAsFall(Player*,DungeonEvent const&,DcChainState&,uint32){return false;}
}
std::vector<Player*> FollowerBots(Player* tank){std::vector<Player*> out;for(Player* p:members)if(p!=tank)out.push_back(p);return out;}
DcChainRelease::Ahead LeaderAhead(Player*,DungeonEvent const&){return {true,true,1,1};}
DcChainRelease::Ahead FollowerAhead(Player*,DungeonEvent const&){return {true,true,1,1};}
bool IsMovementStepKind(EventStepKind kind){return kind!=EventStepKind::Wait;}
namespace DcMovement{enum class Stop{Hold};void StopBot(Player*,Stop){}}
int movementCalls=0;
DcPartyWideChain::StepOutcome DriveMoveTo(Player*,EventStep const&){++movementCalls;return DcPartyWideChain::StepOutcome::Running;}
DcPartyWideChain::StepOutcome DriveRawPath(Player*,PlayerbotAI*,DungeonEvent const&,EventStep const&,DcChainState&,uint32){++movementCalls;return DcPartyWideChain::StepOutcome::Running;}
DcPartyWideChain::StepOutcome DriveJump(Player*,DungeonEvent const&,EventStep const&,DcChainState&,uint32){++movementCalls;return DcPartyWideChain::StepOutcome::Running;}
void DropCombatLeftBehind(Player*){++movementCalls;}
struct DungeonEventExecutor{static void RelocateParty(Player*,AiObjectContext*,float,float,float);};
enum class ObjectiveArriveResult{Done,Blocked};
using Hook=ObjectiveArriveResult(*)(Player*,AiObjectContext*,DungeonBossInfo const&);
int hookCalls=0;ObjectiveArriveResult hook(Player*,AiObjectContext*,DungeonBossInfo const&){++hookCalls;return ObjectiveArriveResult::Done;}
std::map<uint32,Hook> const& Hooks(){static std::map<uint32,Hook> hooks{{1,hook},{5,hook},{63,hook},{64,hook},{65,hook}};return hooks;}
struct ObjectiveHookRegistry{static ObjectiveArriveResult Run(uint32,Player*,AiObjectContext*,DungeonBossInfo const&);};
#include "Fall.cpp"
#include "Drive.cpp"
#include "Follower.cpp"
#include "Elixir.cpp"
#include "Watchdog.cpp"
#include "Stragglers.cpp"
#include "Relocate.cpp"
#include "Hook.cpp"
#include "DcStratTrapAlley.h"
namespace DcModule{bool IsEnabled(){return true;}}
struct Creature{uint32 entry=10441;float x=3610,y=-3345,z=123;bool alive=true,summoned=true;int despawns=0;
 uint32 GetMapId(){return 329;}uint32 GetEntry(){return entry;}bool IsSummon(){return summoned;}bool IsAlive(){return alive;}
 float GetPositionX()const{return x;}float GetPositionY()const{return y;}float GetPositionZ()const{return z;}Creature const& GetHomePosition(){return *this;}void DespawnOrUnsummon(){++despawns;}
};
struct AllCreatureScript{explicit AllCreatureScript(char const*){}virtual ~AllCreatureScript()=default;virtual void OnAllCreatureUpdate(Creature*,uint32)=0;};
#include "Critter.cpp"
'''

SHORTCUT_HARNESS = r'''
int main(){
 Player tank,follower;tank.id=1;follower.id=2;PlayerbotAI ai;tank.ai=follower.ai=&ai;leader=&tank;members={&tank,&follower};DungeonEvent ev;AiObjectContext context;DcChainState state;live=&ev;
 // New party-wide raw splines, jumps and fall ladders never drive earned bots.
 assert(!HandleFall(&follower,ev,state,0,nowMs,true));assert(state.falls==0&&follower.teleports==0);
 for(auto kind:{EventStepKind::MoveTo,EventStepKind::RawPath,EventStepKind::Jump}){EventStep step{kind};assert(DcPartyWideChain::DriveStep(&follower,&ai,&context,ev,step,state)==DcPartyWideChain::StepOutcome::Stalled);}
 assert(!DcPartyWideChain::DriveFollower(&follower,&ai,&context));assert(context.chain.Get().ev==nullptr&&movementCalls==0);
 // Missing consumables stay missing; an owned elixir uses the native item cast.
 assert(!DrinkElixir(&follower)&&follower.grants==0&&follower.drinks==0);
 follower.owned=true;assert(DrinkElixir(&follower)&&follower.grants==0&&follower.drinks==1);
 follower.cooldown=true;assert(!DrinkElixir(&follower)&&follower.drinks==1);follower.cooldown=false;
 // An expired underwater clock cannot rescue an earned bot by teleporting.
 run.underwaterSinceMs[2]=1;DcBreathProvision::WatchdogTick(&tank);assert(follower.teleports==0&&run.underwaterSinceMs.at(2)==1);
 GroupReference followerRef{&follower},tankRef{&tank,&followerRef};Group group;group.first=&tankRef;tank.group=&group;
 PullStrandedFollowersAcross(&tank,100,0,0);assert(follower.teleports==0);
 DungeonEventExecutor::RelocateParty(&tank,&context,1,2,3);assert(tank.teleports==0&&movementCalls==0);
 DungeonBossInfo info;for(uint32 id:{63u,64u,65u})assert(ObjectiveHookRegistry::Run(id,&tank,&context,info)==ObjectiveArriveResult::Blocked);
 assert(hookCalls==0);for(uint32 id:{1u,5u})assert(ObjectiveHookRegistry::Run(id,&tank,&context,info)==ObjectiveArriveResult::Done);assert(hookCalls==2);
 Creature critter;DungeonClearStratFallenCritterScript critterScript;critterScript.OnAllCreatureUpdate(&critter,1000);assert(critter.despawns==0);
 // The same complete methods retain ordinary upstream behavior when disabled.
 natural=false;assert(HandleFall(&follower,ev,state,0,nowMs,true)&&follower.teleports==1&&state.falls==1);
 ev.fall.enabled=false;assert(DcPartyWideChain::DriveStep(&follower,&ai,&context,ev,ev.steps[0],state)==DcPartyWideChain::StepOutcome::Running&&movementCalls==1);
 assert(DcPartyWideChain::DriveFollower(&follower,&ai,&context)&&context.chain.Get().ev==&ev);
 follower.owned=false;assert(DrinkElixir(&follower)&&follower.grants==1&&follower.drinks==2);
 DcBreathProvision::WatchdogTick(&tank);assert(follower.teleports==2);
 DungeonEventExecutor::RelocateParty(&tank,&context,1,2,3);assert(tank.teleports==1);
 for(uint32 id:{63u,64u,65u})assert(ObjectiveHookRegistry::Run(id,&tank,&context,info)==ObjectiveArriveResult::Done);
 assert(hookCalls==5);
 critterScript.OnAllCreatureUpdate(&critter,1000);assert(critter.despawns==1);
 PullStrandedFollowersAcross(&tank,100,0,0);assert(follower.teleports==3);
 std::cout<<"Dungeon shortcut gates: party chains, fall rescue, owned elixirs, breath rescue, relocation and recovery hooks passed\n";
}
'''


def shortcut_guards(core,source):
    chain=(source/'Ai/Dungeon/DungeonClear/Util/DcPartyWideChain.cpp').read_text()
    breath=(source/'Ai/Dungeon/DungeonClear/Util/DcBreathProvision.cpp').read_text()
    executor=(source/'Ai/Dungeon/DungeonClear/Util/DungeonEventExecutor.cpp').read_text()
    hooks=(source/'Ai/Dungeon/DungeonClear/Overrides/ObjectiveHookRegistry.cpp').read_text()
    # The item producer searches this player's inventory and bags and returns
    # nullptr when absent; movement doubles only record dispatch past each gate.
    storage=(core/'src/server/game/Entities/Player/PlayerStorage.cpp').read_text()
    item=function(storage,'Item* Player::GetItemByEntry(')
    assert 'pItem->GetEntry() == entry' in item and 'GetBagByPos(i)' in item and 'return nullptr;' in item
    # These new registered hooks really own the ids refused by the dispatch test.
    for header,number in (('Data/Events/DungeonEventTables.h',63),('Util/DcStratTrapAlley.h',64),('Util/DcKaraLibraryPit.h',65)):
        text=(source/'Ai/Dungeon/DungeonClear'/header).read_text()
        assert re.search(r'HOOK_(?:POOL_EXIT|PIT_RESCUE)\s*=\s*'+str(number)+r'\s*;',text)

    assert 'GetValue<DcChainState&>(DcKey::ChainState)->Get()' in chain
    assert 'p->GetItemByEntry(DcBreathSource::ITEM_ELIXIR_OF_WATER_BREATHING)' in breath
    assert 'run.underwaterSinceMs.emplace(key, now)' in breath
    methods={
        'Fall.cpp':function(chain,'bool HandleFall('),
        'Drive.cpp':function(chain,'DcPartyWideChain::StepOutcome DcPartyWideChain::DriveStep('),
        'Follower.cpp':function(chain,'bool DcPartyWideChain::DriveFollower('),
        'Elixir.cpp':function(breath,'bool DrinkElixir('),
        'Watchdog.cpp':function(breath,'void DcBreathProvision::WatchdogTick('),
        'Stragglers.cpp':function(executor,'void PullStrandedFollowersAcross('),
        'Relocate.cpp':function(executor,'void DungeonEventExecutor::RelocateParty('),
        'Hook.cpp':function(hooks,'ObjectiveArriveResult ObjectiveHookRegistry::Run('),
    }
    module=(source/'DungeonClearModule.cpp').read_text()
    critter=function(module,'class DungeonClearStratFallenCritterScript')+';'
    methods['Critter.cpp']=critter
    header=(source/'Ai/Dungeon/DungeonClear/Util/DcPartyWideChain.h').read_text()
    release='namespace DcChainRelease {\n'+function(header,'struct Ahead')+';\n'+function(header,'inline uint32 ReleaseAfterStep(')+'\n'+function(header,'inline bool MayStart(')+'\n}'
    compiler=cxx()
    with tempfile.TemporaryDirectory(prefix='dungeon-shortcuts-') as temp:
        work=Path(temp)
        for name,method in methods.items():
            (work/name).write_text(method)
        (work/'ChainRelease.h').write_text(release)
        for name in ('DcBreathSource.h','DcStratTrapAlley.h'):
            (work/name).write_text((source/'Ai/Dungeon/DungeonClear/Util'/name).read_text())
        active=function((source/'DcEarnedPlay.h').read_text(),'inline bool Active(')
        (work/'fixture.cpp').write_text(SHORTCUT_STUBS.replace('NATIVE_ACTIVE',active)+SHORTCUT_HARNESS)
        flags=['-std=c++20','-O1','-Wall','-Wextra','-Wno-unused-parameter','-I',str(work)]
        if os.name!='nt':
            flags+=[*SANITIZER_FLAGS,'-no-pie']
        def build(directory,exe):
            return [compiler,*flags,str(directory/'fixture.cpp'),'-o',str(exe)]
        exe=work/('fixture.exe' if os.name=='nt' else 'fixture')
        subprocess.run(build(work,exe),check=True)
        subprocess.run([str(exe)],check=True,timeout=TIMEOUT)
        mutations=[(label,file,'if (DcEarnedPlay::Active())','if (false)') for label,file in (
            ('chain fall teleport','Fall.cpp'),('chain movement','Drive.cpp'),('follower chain adoption','Follower.cpp'),
            ('free breathing elixir','Elixir.cpp'),('underwater teleport rescue','Watchdog.cpp'),('party relocation','Relocate.cpp'),('stranded follower teleport','Stragglers.cpp'),
            ('native trap critter removed','Critter.cpp'))]
        mutations.append(('new recovery hooks','Hook.cpp','DcEarnedPlay::Active() && hookId != 1 && hookId != 5','false'))
        reject_mutants(work,mutations,build,'Dungeon shortcut gates')


def main():
    parser=argparse.ArgumentParser()
    source_argument(parser)
    args=parser.parse_args()
    core=prepared_core()
    source=args.source or core/'modules/mod-dungeon-clear/src'
    shortcut_guards(core,source)
    module=(source/'DungeonClearModule.cpp').read_text()
    commands=(source/'DungeonClearCommand.cpp').read_text()
    lab=(source/'Lab/DcLabManager.cpp').read_text()
    # Native contracts: these are the command bindings and provisioning producer
    # the fixture observes, including console login before queuing lab runs.
    for command,handler in (('run','HandleLabRun'),('batch','HandleLabBatch')):
        assert re.search(r'\{\s*"'+command+r'",\s*'+handler+r',\s*SEC_GAMEMASTER,\s*Console::Yes\s*\}',commands)
    assert 'DcTestDriver::EnsureOnline(&whyPending)' in function(commands,'static Player* ResolveTestIssuer(')
    assert 'Launch(key, gm);' in function(lab,'void DcLabManager::Tick(')
    assert '_queues[run.partyKey].push_back(std::move(run));' in function(lab,'std::string DcLabManager::Enqueue(')
    config=(core/'modules/mod-playerbots/src/PlayerbotAIConfig.h').read_text()
    assert re.search(r'bool\s+naturalProgression\s*=\s*false\s*;',config)
    constants='\n'.join(re.search(r'constexpr uint32 '+name+r'\s*=\s*[^;]+;',module).group(0)
                        for name in ('DC_ASYNC_PATH_RESULT_TTL_MS','DC_STRATEGY_GATE_SWEEP_MS'))
    methods='\n'.join(function(commands,signature) for signature in (
        'bool DcDisabledNotice(', 'static Player* ResolveTestIssuer(', 'static bool LabEnqueue(',
        'static bool HandleLabRun(', 'static bool HandleLabBatch(',
        'static bool HandleLabStatus(', 'static bool HandleLabStop('))
    code=STUBS.replace('NATIVE_ACTIVE',function((source/'DcEarnedPlay.h').read_text(),'inline bool Active('))
    code=code.replace('NATIVE_UPDATE',function(module,'void OnUpdate(uint32 diff) override'))
    code=code.replace('NATIVE_COMMANDS',methods)
    compiler=cxx()
    with tempfile.TemporaryDirectory(prefix='dungeon-lab-gates-') as temp:
        work=Path(temp)
        (work/'fixture.cpp').write_text('#include <cstdint>\nusing uint32=std::uint32_t;\n'+constants+'\n'+code+HARNESS)
        flags=['-std=c++20','-O1','-Wall','-Wextra','-Wno-unused-parameter']
        if os.name!='nt':
            flags+=[*SANITIZER_FLAGS,'-no-pie']
        def build(directory,exe):
            return [compiler,*flags,str(directory/'fixture.cpp'),'-o',str(exe)]
        exe=work/('fixture.exe' if os.name=='nt' else 'fixture')
        subprocess.run(build(work,exe),check=True)
        subprocess.run([str(exe)],check=True,timeout=TIMEOUT)
        mutations=[
            ('provisioning tick gate removed','fixture.cpp','if (!DcEarnedPlay::Active())\n        {\n            DcTestDriver::Tick();','if (true)\n        {\n            DcTestDriver::Tick();'),
            ('lab tick outside natural gate','fixture.cpp','            DcLabManager::Instance().Tick(diff);\n        }','        }\n        DcLabManager::Instance().Tick(diff);'),
            ('ordinary lab tick omitted','fixture.cpp','            DcLabManager::Instance().Tick(diff);',''),
            ('lab command gate removed','fixture.cpp','if (DcEarnedPlay::Active())','if (false)'),
            ('lab refusal does not return','fixture.cpp','handler->SendSysMessage("Provisioned lab runs are unavailable in natural progression.");\n            return true;','handler->SendSysMessage("Provisioned lab runs are unavailable in natural progression.");'),
        ]
        reject_mutants(work,mutations,build,'Dungeon Pull Lab')


if __name__=='__main__':
    main()
