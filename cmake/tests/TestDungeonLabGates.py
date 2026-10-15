"""Exercise the production Pull Lab command and world-tick natural gates."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

from FixtureSupport import TIMEOUT, cxx, function, prepared_core, reject_mutants


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
 assert((calls==std::vector<std::string>{"budget","dungeon queue","battleground queue","earned","orphaned","passives","paths","status"}));
 calls.clear();expectedDiff=2000;world.OnUpdate(2000);
 assert((calls==std::vector<std::string>{"budget","dungeon queue","battleground queue","earned","orphaned","passives","paths","status","strategies"}));
 // Existing unrestricted test-driver, plan, run and lab ordering stays intact.
 natural=false;calls.clear();expectedDiff=1000;world.OnUpdate(1000);
 assert((calls==std::vector<std::string>{"budget","dungeon queue","battleground queue","earned","orphaned","passives","paths","status","purge","driver","plan","runs","lab"}));
 enabled=false;calls.clear();world.OnUpdate(1000);
 assert((calls==std::vector<std::string>{"budget","dungeon queue","battleground queue","earned"}));
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


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path)
    args=parser.parse_args()
    core=prepared_core()
    source=args.source or core/'modules/mod-dungeon-clear/src'
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
            flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie']
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
