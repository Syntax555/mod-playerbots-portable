"""Exercise the earned Dungeon Clear event audit with native lock and registry doubles."""
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


def block(source, signature, closing='};'):
    start = source.index(signature)
    return source[start:source.index(closing, start) + len(closing)]


def stubs(core, dc):
    shared = (core/'src/server/shared/SharedDefines.h').read_text()
    registry = (dc/'Ai/Dungeon/DungeonClear/Data/DungeonEventRegistry.h').read_text()
    flags = {name: re.search(name + r'\s*=\s*(0x[0-9A-Fa-f]+)', shared).group(1)
             for name in ('GO_FLAG_LOCKED', 'GO_FLAG_INTERACT_COND', 'GO_FLAG_NOT_SELECTABLE')}
    event_flags = ''.join(re.search(r'bool\s+' + name + r'\{(?:true|false)\};', registry).group(0)
                          for name in ('required', 'ownsThePull', 'stepsOwnMovement'))
    tables = (dc/'Ai/Dungeon/DungeonClear/Data/Events/DungeonEventTables.h').read_text()
    trial = tables[tables.index('namespace DcTrialOfTheChampion'):]
    trial_progress = '\n'.join('constexpr uint32 TRIAL_' + name + '=' +
                               re.search(name + r'\s*=\s*(\d+)', trial).group(1) + ';'
                               for name in ('DATA_INSTANCE_PROGRESS', 'PROGRESS_CHAMPIONS_DEAD',
                                            'PROGRESS_ARGENT_CHALLENGE_DIED', 'PROGRESS_FINISHED'))
    for name, default in (('creatureEntry', 0), ('escortDoneEntry', 0), ('gossipOption', -1),
                          ('escortDoneBit', -1), ('instanceDataId', -1)):
        assert re.search(rf'\b{name}\{{{default}\}};', registry)
    # Real lock and step vocabularies: a new upstream step kind is refused until audited.
    return '''#pragma once
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <vector>
using uint8=uint8_t;using uint32=uint32_t;using int32=int32_t;
#define MAX_LOCK_CASE 8
''' + block(shared, 'enum LockKeyType') + block(shared, 'enum LockType') + block(shared, 'enum SkillType') + \
        function(shared, 'inline SkillType SkillByLockType(LockType locktype)') + '\n' + \
        block(registry, 'enum class EventStepKind : uint8') + f'''
constexpr uint32 GO_FLAG_LOCKED={flags['GO_FLAG_LOCKED']},GO_FLAG_INTERACT_COND={flags['GO_FLAG_INTERACT_COND']},GO_FLAG_NOT_SELECTABLE={flags['GO_FLAG_NOT_SELECTABLE']};
constexpr uint8 DUNGEON_DIFFICULTY_NORMAL=0;
{trial_progress}
struct EventStep{{EventStepKind kind{{EventStepKind::Wait}};uint32 goEntry=0,itemId=0,hookId=0,spellId=0,creatureEntry=0,escortDoneEntry=0;int32 instanceDataId=-1,gossipOption=-1,escortDoneBit=-1;uint32 instanceDataMin=0;}};
enum class DcDifficultyGate:uint8{{Any,NormalOnly,HeroicOnly}};
struct DcDiffKey{{bool isRaid=false;uint8 difficulty=0;bool IsHeroic()const{{return difficulty>0;}}}};
inline bool DcGateMatches(DcDifficultyGate gate,DcDiffKey key){{return gate==DcDifficultyGate::Any||(gate==DcDifficultyGate::NormalOnly)!=key.IsHeroic();}}
struct DungeonEvent{{uint32 mapId=0,id=0;std::string name;DcDifficultyGate gate{{DcDifficultyGate::Any}};std::vector<EventStep> steps;{event_flags}}};
struct DungeonBossInfo{{std::string name;uint32 onArriveHook=0,eventId=0;}};
// Production splits objectives: the spawn index only lists encounter bosses,
// while the roster corrections add every event objective and its event id.
std::map<uint32,std::vector<DungeonBossInfo>> spawned,roster;std::map<std::pair<uint32,uint32>,DungeonEvent> events;std::map<uint32,std::vector<DungeonEvent>> conditional;
struct BossSpawnIndex{{static std::vector<DungeonBossInfo> const& Get(uint32 map,uint8){{for(auto const& boss:spawned[map])if(boss.eventId||boss.onArriveHook)throw 0;return spawned[map];}}}};
struct BossRosterRegistry{{static std::vector<DungeonBossInfo> Apply(uint32 map,DcDiffKey,std::vector<DungeonBossInfo> base){{base.insert(base.end(),roster[map].begin(),roster[map].end());return base;}}}};
struct DungeonEventRegistry{{static DungeonEvent const* Find(uint32 map,uint32 id){{auto it=events.find({{map,id}});return it==events.end()?nullptr:&it->second;}}
 static std::vector<DungeonEvent const*> Conditional(uint32 map,DcDiffKey key){{std::vector<DungeonEvent const*> out;for(auto& ev:conditional[map])if(DcGateMatches(ev.gate,key))out.push_back(&ev);return out;}}}};
struct LockEntry{{uint32 ID;uint32 Type[MAX_LOCK_CASE];uint32 Index[MAX_LOCK_CASE];uint32 Skill[MAX_LOCK_CASE];}};
struct LockStore{{std::map<uint32,LockEntry> rows;LockEntry const* LookupEntry(uint32 id){{auto it=rows.find(id);return it==rows.end()?nullptr:&it->second;}}}};LockStore sLockStore;
struct GameObjectTemplate{{uint32 lock=0;uint32 GetLockId()const{{return lock;}}}};
struct ObjectMgr{{std::map<uint32,GameObjectTemplate> templates;GameObjectTemplate const* GetGameObjectTemplate(uint32 id){{auto it=templates.find(id);return it==templates.end()?nullptr:&it->second;}}}};ObjectMgr objectMgr;ObjectMgr* sObjectMgr=&objectMgr;
class Player{{public:std::set<uint32> items;bool HasItemCount(uint32 item,uint32,bool=false)const{{return items.count(item);}}}};
class GameObject{{public:GameObjectTemplate info;uint32 flags=0;bool quest=true;bool HasGameObjectFlag(uint32 flag)const{{return flags&flag;}}bool ActivateToQuest(Player*)const{{return quest;}}GameObjectTemplate const* GetGOInfo()const{{return &info;}}}};
'''


HARNESS = r'''
#include "DcEarnedEvents.cpp"
#include <cassert>
#include <iostream>
EventStep step(EventStepKind kind,uint32 go=0,uint32 item=0,uint32 hook=0){EventStep s;s.kind=kind;s.goEntry=go;s.itemId=item;s.hookId=hook;return s;}
EventStep progress_gate(int32 data,uint32 minimum){EventStep s=step(EventStepKind::MoveTo);s.instanceDataId=data;s.instanceDataMin=minimum;return s;}
LockEntry lock(uint32 id,std::vector<std::pair<uint32,uint32>> cases){LockEntry l{id,{},{},{}};for(size_t i=0;i<cases.size();++i){l.Type[i]=cases[i].first;l.Index[i]=cases[i].second;}return l;}
DungeonEvent event(std::string name,std::vector<EventStep> steps,bool required=true,DcDifficultyGate gate=DcDifficultyGate::Any){DungeonEvent ev;ev.name=name;ev.steps=steps;ev.required=required;ev.gate=gate;return ev;}
bool audited(uint32 map){std::string reason;bool ok=DcEarnedEvents::MapAudited(map,reason);assert(ok==reason.empty());return ok;}
int main(){
 // Ordinary player actions only: real walks, clicks, talks, waits and fights.
 std::set<EventStepKind> allowed{EventStepKind::MoveTo,EventStepKind::UseGameObject,EventStepKind::Gossip,EventStepKind::WaitForSpawn,EventStepKind::WaitForGameObjectState,EventStepKind::KillCreature,EventStepKind::ClearRadius,EventStepKind::Wait,EventStepKind::UseItem};
 for(EventStepKind kind:ALL_KINDS)assert(DcEarnedEvents::StepAllowed(step(kind))==allowed.count(kind));
 assert(!DcEarnedEvents::StepAllowed(step(EventStepKind::MoveTo,0,0,7)));
 assert(DcEarnedEvents::StepAllowed(step(EventStepKind::Custom,0,0,1)));
 assert(DcEarnedEvents::StepAllowed(step(EventStepKind::Custom,0,0,5)));
 for(uint32 hook:{0u,2u,40u,63u,64u,65u})assert(!DcEarnedEvents::StepAllowed(step(EventStepKind::Custom,0,0,hook)));
 // Locks: a click opens no lock or a profession-free open lock; keys open item locks.
 sLockStore.rows={{1,lock(1,{{LOCK_KEY_SKILL,LOCKTYPE_OPEN}})},{2,lock(2,{{LOCK_KEY_ITEM,5000}})},{3,lock(3,{{LOCK_KEY_SKILL,LOCKTYPE_PICKLOCK}})},{4,lock(4,{{LOCK_KEY_SPELL,1234}})},{5,lock(5,{{LOCK_KEY_ITEM,5000},{LOCK_KEY_SKILL,LOCKTYPE_PICKLOCK}})}};
 Player bot;GameObject go;
 assert(DcEarnedEvents::CanOpen(&bot,&go));go.info.lock=1;assert(DcEarnedEvents::CanOpen(&bot,&go));
 go.flags=GO_FLAG_LOCKED;assert(!DcEarnedEvents::CanOpen(&bot,&go));
 for(uint32 id:{2u,3u,4u,5u,99u}){go.flags=0;go.info.lock=id;assert(!DcEarnedEvents::CanOpen(&bot,&go));}
 bot.items.insert(5000);for(uint32 id:{2u,5u}){go.info.lock=id;assert(DcEarnedEvents::CanOpen(&bot,&go));go.flags=GO_FLAG_LOCKED;assert(DcEarnedEvents::CanOpen(&bot,&go));go.flags=0;}
 go.info.lock=0;go.flags=GO_FLAG_NOT_SELECTABLE;assert(!DcEarnedEvents::CanOpen(&bot,&go));
 go.flags=GO_FLAG_INTERACT_COND;go.quest=false;assert(!DcEarnedEvents::CanOpen(&bot,&go));go.quest=true;assert(DcEarnedEvents::CanOpen(&bot,&go));
 assert(!DcEarnedEvents::CanOpen(nullptr,&go)&&!DcEarnedEvents::CanOpen(&bot,nullptr));
 // Map audit: every required normal objective must consist of ordinary keyless steps.
 objectMgr.templates={{10,{0}},{11,{1}},{12,{2}}};
 assert(audited(1));
 // Blackfathom's disconnected navigation remains unaudited even when custom
 // world data omits its optional movement objectives from the roster.
 assert(!audited(48));
 conditional[48]={event("Pool exit",{step(EventStepKind::Custom,0,0,63)},false)};
 assert(!audited(48));

 // Encounter bosses alone carry no event; the roster-added objective decides.
 spawned[9]={{"Mennu the Betrayer",0,0}};assert(audited(9));
 roster[9]={{"Drop down past Mennu",0,1}};events[{9,1}]=event("Drop down past Mennu",{step(EventStepKind::MoveTo),step(EventStepKind::TeleportParty)});assert(!audited(9));
 events[{9,1}].required=false;assert(audited(9));
 // An optional anchored controller that owns the pull or the movement is essential too.
 events[{9,1}].ownsThePull=true;assert(!audited(9));
 events[{9,1}].ownsThePull=false;events[{9,1}].stepsOwnMovement=true;assert(!audited(9));
 roster[2]={{"Gong",0,1}};events[{2,1}]=event("Ring the Gong",{step(EventStepKind::MoveTo),step(EventStepKind::UseGameObject,10),step(EventStepKind::UseGameObject,11),step(EventStepKind::Gossip),step(EventStepKind::ClearRadius)});assert(audited(2));
 roster[3]={{"Cannon",0,1}};events[{3,1}]=event("Cannon",{step(EventStepKind::MoveTo),step(EventStepKind::Custom)});assert(!audited(3));
 events[{3,1}].required=false;assert(audited(3));
 events[{3,1}]=event("Cannon",{step(EventStepKind::Custom)},true,DcDifficultyGate::HeroicOnly);assert(audited(3));
 roster[4]={{"Keyed door",0,1}};events[{4,1}]=event("Door",{step(EventStepKind::UseGameObject,12)});assert(!audited(4));
 events[{4,1}]=event("Door",{step(EventStepKind::UseGameObject,99)});assert(!audited(4));
 events[{4,1}]=event("Urn",{step(EventStepKind::UseGameObject,10,4242)});assert(!audited(4));
 events[{4,1}]=event("Egg",{step(EventStepKind::UseItem,0,4242)});assert(!audited(4));
 for(EventStepKind kind:{EventStepKind::Jump,EventStepKind::DropInHole,EventStepKind::TeleportParty,EventStepKind::EscortCreature,EventStepKind::CastSpell,EventStepKind::UseItemOnGO,EventStepKind::UseItemAt}){events[{4,1}]=event("Shortcut",{step(kind)});assert(!audited(4));}
 // Only the exact native WC escort is admitted, on its own map and event.
 EventStep naralex=step(EventStepKind::EscortCreature);naralex.creatureEntry=3678;naralex.gossipOption=0;naralex.escortDoneEntry=3654;naralex.escortDoneBit=7;
 assert(DcEarnedEvents::StepAllowed(naralex));
 for(int field=0;field<7;++field){auto bad=naralex;if(field==0)bad.creatureEntry++;if(field==1)bad.gossipOption++;if(field==2)bad.escortDoneEntry++;if(field==3)bad.escortDoneBit++;if(field==4)bad.hookId++;if(field==5)bad.instanceDataId=0;if(field==6)bad.kind=EventStepKind::Jump;assert(!DcEarnedEvents::StepAllowed(bad));}
 roster[43]={{"Naralex",0,2}};events[{43,2}]=event("Naralex",{naralex});events[{43,2}].mapId=43;events[{43,2}].id=2;assert(audited(43));
 events[{43,2}].mapId=1;assert(!audited(43));events[{43,2}].mapId=43;
 events[{43,2}].id=1;assert(!audited(43));events[{43,2}].id=2;
 // Only the earned cannon's exact item-target spell has an acquisition driver.
 EventStep cannon=step(EventStepKind::UseItemOnGO,16398,5397);cannon.spellId=6250;
 assert(DcEarnedEvents::StepAllowed(cannon));
 for(int field=0;field<4;++field){auto bad=cannon;if(field==0)bad.goEntry++;if(field==1)bad.itemId++;if(field==2)bad.spellId++;if(field==3)bad.hookId++;assert(!DcEarnedEvents::StepAllowed(bad));}
 objectMgr.templates[17155]={1};objectMgr.templates[16398]={83};
 roster[36]={{"Defias Cannon",0,1}};events[{36,1}]=event("Defias Cannon",{step(EventStepKind::MoveTo),cannon,step(EventStepKind::WaitForGameObjectState,16397)});
 assert(audited(36));
 objectMgr.templates.erase(17155);assert(!audited(36));objectMgr.templates[17155]={2};assert(!audited(36));
 objectMgr.templates[17155]={1};objectMgr.templates.erase(16398);assert(!audited(36));
 objectMgr.templates[16398]={0};assert(!audited(36));objectMgr.templates[16398]={83};assert(audited(36));
 events[{36,1}].steps[1].spellId=1;assert(!audited(36));events[{36,1}].steps[1]=cannon;
 roster[5]={{"Ring of Law",7,0}};assert(!audited(5));
 roster[230]={{"Ring of Law",0,1}};events[{230,1}]=event("Ring of Law",{step(EventStepKind::Custom,0,0,1)});
 events[{230,1}].mapId=230;events[{230,1}].id=1;assert(audited(230));
 events[{230,1}].mapId=229;assert(!audited(230));events[{230,1}].mapId=230;
 events[{230,1}].id=2;assert(!audited(230));events[{230,1}].id=1;
 events[{230,1}].steps[0].hookId=5;assert(!audited(230));events[{230,1}].steps[0].hookId=1;
 // Zum'rah admits only his spatial controller, not arbitrary hooks or locks.
 conditional[209]={event("Wake Witch Doctor Zum'rah",{step(EventStepKind::Custom,0,0,5)})};
 auto& wake=conditional[209][0];wake.mapId=209;wake.id=3;assert(audited(209));
 wake.mapId=208;assert(!audited(209));wake.mapId=209;
 wake.id=2;assert(!audited(209));wake.id=3;
 wake.steps[0].hookId=1;assert(!audited(209));wake.steps[0].hookId=5;
 objectMgr.templates[141073]={420};objectMgr.templates[141832]={99};
 roster[209]={{"Temple Summit",0,1}};events[{209,1}]=event("Troll Cage",{step(EventStepKind::UseGameObject,141073)});
 assert(!audited(209));events[{209,1}].steps[0].goEntry=141832;assert(!audited(209));
 roster[209].clear();assert(audited(209));
 roster[6]={{"Missing",0,9}};assert(!audited(6));
 conditional[7]={event("Room aggro",{step(EventStepKind::KillCreature)}),event("Drop",{step(EventStepKind::Jump)},false)};assert(audited(7));
 conditional[7].push_back(event("Wake",{step(EventStepKind::Custom)}));assert(!audited(7));
 // Trial of the Champion: required objectives only wait for instance progress.
 // Its optional controller performs the gossip/joust transitions those waits
 // depend on. An unsupported controller must reject automatic recruitment.
 roster[650]={{"The Grand Champions",0,1},{"The Argent Challenge",0,2},{"The Black Knight",0,3}};
 events[{650,1}]=event("The Grand Champions",{step(EventStepKind::MoveTo),progress_gate(TRIAL_DATA_INSTANCE_PROGRESS,TRIAL_PROGRESS_CHAMPIONS_DEAD)});
 events[{650,2}]=event("The Argent Challenge",{step(EventStepKind::MoveTo),progress_gate(TRIAL_DATA_INSTANCE_PROGRESS,TRIAL_PROGRESS_ARGENT_CHALLENGE_DIED)});
 events[{650,3}]=event("The Black Knight",{step(EventStepKind::MoveTo),progress_gate(TRIAL_DATA_INSTANCE_PROGRESS,TRIAL_PROGRESS_FINISHED)});
 conditional[650]={event("The Champion's Arena",{step(EventStepKind::Custom)},false)};
 assert(audited(650)); // an optional noncontroller may still be skipped
 auto& controller=conditional[650].front();
 controller.ownsThePull=true;assert(!audited(650));
 controller.ownsThePull=false;controller.stepsOwnMovement=true;assert(!audited(650));
 controller.ownsThePull=true;assert(!audited(650));
 std::string reason;assert(!DcEarnedEvents::MapAudited(650,reason));assert(reason.find("The Champion's Arena")!=std::string::npos);
 controller.steps={step(EventStepKind::Gossip),step(EventStepKind::MoveTo)};assert(audited(650));
 controller.steps={step(EventStepKind::Custom)};controller.gate=DcDifficultyGate::HeroicOnly;assert(audited(650));
 // Drak'Tharon's optional Novos movement controller needs the same audit even
 // though it does not own the pull. Optional unrelated hooks remain skippable.
 conditional[600]={event("Novos: hold the camp",{step(EventStepKind::Custom)},false)};
 conditional[600].front().stepsOwnMovement=true;assert(!audited(600));
 conditional[601]={event("Hadronox: web the doors",{step(EventStepKind::Custom)},false)};assert(audited(601));
 std::cout<<"Earned dungeon events: ordinary steps, native locks and keys, required/optional/heroic objectives, hooks and essential optional encounter controllers audited\n";
}
'''


def native_contracts(core, dc):
    # The native use opcode never checks a lock: the client casts the opening
    # spell instead. The earned audit therefore evaluates the lock itself.
    handler = function((core/'src/server/game/Handlers/SpellHandler.cpp').read_text(),
                       'void WorldSession::HandleGameObjectUseOpcode(')
    assert 'obj->Use(GetPlayer())' in handler and 'Lock' not in handler
    can_open = function((core/'src/server/game/Spells/Spell.cpp').read_text(), 'SpellCastResult Spell::CanOpenLock(')
    assert 'SkillByLockType' in can_open and 'LOCK_KEY_ITEM' in can_open
    executor = (dc/'Ai/Dungeon/DungeonClear/Util/DungeonEventExecutor.cpp').read_text()
    assert 'if (DcEarnedPlay::Active() && !DcEarnedEvents::StepAllowed(step))\n        return StepResult::Failed;' in executor
    # A refused step fails: optional events skip, required ones stall for players.
    advance = function(executor, 'EventDriveOutcome DungeonEventExecutor::Advance(')
    assert 'return ev.required ? EventDriveOutcome::Stalled : EventDriveOutcome::Skipped;' in advance
    hop = function(executor, 'void HopTo(Player* bot, float x, float y, float z)')
    assert hop.index('DcEarnedPlay::ReachableLeg(bot, x, y, z)') < hop.index('MovePoint(')
    # Event objectives reach a running clear only through the roster corrections;
    # the spawn index never assigns them. The audit must read the same roster.
    spawn_index = (dc/'Ai/Dungeon/DungeonClear/Data/BossSpawnIndex.cpp').read_text()
    assert 'eventId' not in spawn_index and 'onArriveHook' not in spawn_index
    bosses_value = (dc/'Ai/Dungeon/DungeonClear/Value/DungeonBossesValue.cpp').read_text()
    assert re.search(r'BossRosterRegistry::Apply\(mapId,\s*DcDifficulty::Of\(map\),\s*BossSpawnIndex::Get\(', bosses_value)
    audit = function((dc/'DcEarnedEvents.cpp').read_text(), 'bool MapAudited(')
    assert re.search(r'BossRosterRegistry::Apply\(\s*mapId,\s*normal,\s*BossSpawnIndex::Get\(', audit)
    trial = (dc/'Ai/Dungeon/DungeonClear/Data/Events/TrialOfTheChampionEvents.cpp').read_text()
    trial_events = function(trial, 'void RegisterTrialOfTheChampionEvents(')
    assert trial_events.count('.MoveToHoldUntilInstanceData(') == 3
    controller = trial_events[trial_events.index('"The Champion\'s Arena"'):]
    assert all(flag in controller for flag in ('.Optional()', '.OwnsThePull()', '.StepsOwnMovement()', '.Custom('))
    print('Native event contracts: lock-free use opcode, core lock rules, roster-sourced objectives, refused-step outcomes and real-path hops verified')


def main():
    parser = argparse.ArgumentParser()
    source_argument(parser)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    core = prepared_core(repo)
    source = args.source or core/'modules/mod-dungeon-clear/src'
    if not (source/'DcEarnedEvents.cpp').exists():
        raise SystemExit('PrepareModules.cmake must prepare the earned DungeonClear sources first')
    native_contracts(core, source)
    compiler = cxx()
    registry = (source/'Ai/Dungeon/DungeonClear/Data/DungeonEventRegistry.h').read_text()
    kinds = re.findall(r'^\s{4}([A-Z][A-Za-z]+),', block(registry, 'enum class EventStepKind : uint8'), re.MULTILINE)
    if len(kinds) < 17:
        raise SystemExit('Dungeon Clear event step vocabulary was not recognised')
    with tempfile.TemporaryDirectory(prefix='earned-events-') as temp:
        work = Path(temp)
        (work/'NativeStubs.h').write_text(stubs(core, source) +
            'constexpr EventStepKind ALL_KINDS[]{' + ','.join('EventStepKind::' + k for k in kinds) + '};\n')
        for name in ('Define.h', 'DBCStores.h', 'GameObject.h', 'ObjectMgr.h', 'Player.h', 'SharedDefines.h',
                     'Ai/Dungeon/DungeonClear/Data/BossSpawnIndex.h', 'Ai/Dungeon/DungeonClear/Data/DungeonEventRegistry.h',
                     'Ai/Dungeon/DungeonClear/Util/DcDifficulty.h', 'Ai/Dungeon/DungeonClear/Overrides/BossRosterRegistry.h'):
            path = work/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('#include "NativeStubs.h"\n')
        for name in ('DcEarnedEvents.cpp', 'DcEarnedEvents.h'):
            shutil.copyfile(source/name, work/name)
        (work/'fixture.cpp').write_text(HARNESS)
        exe = work/('fixture.exe' if os.name == 'nt' else 'fixture')
        flags = ['-std=c++20', '-O1', '-Wall', '-Wextra', '-Wno-unused-parameter', '-I', str(work)]
        if os.name != 'nt':
            flags += [*SANITIZER_FLAGS, '-no-pie']
        subprocess.run([compiler, *flags, str(work/'fixture.cpp'), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=TIMEOUT)
        mutations = [
            ('Blackfathom movement audit bypass', 'if (mapId == 48)', 'if (false)'),
            ('off-mesh jump step', 'case EventStepKind::MoveTo:\n                return step.hookId == 0;', 'case EventStepKind::Jump:\n            case EventStepKind::MoveTo:\n                return step.hookId == 0;'),
            ('custom hook on a walk', 'return step.hookId == 0;', 'return true;'),
            ('arbitrary custom shortcut', 'return step.hookId == 1 || step.hookId == 5;', 'return true;'),
            ('earned Ring hook denied', 'return step.hookId == 1 || step.hookId == 5;', 'return step.hookId == 5;'),
            ('earned Zumrah hook denied', 'return step.hookId == 1 || step.hookId == 5;', 'return step.hookId == 1;'),
            ('Ring controller on another map', 'ev.mapId == 230 && ', ''),
            ('Ring controller on another event', 'ev.id == 1 && ', ''),
            ('Zumrah hook on Ring event', 'ev.id == 1 && step.hookId == 1', 'ev.id == 1'),
            ('Zumrah controller on another map', 'ev.mapId == 209 && ', ''),
            ('Zumrah controller on another event', 'ev.id == 3 && ', ''),
            ('Ring hook on Zumrah event', 'ev.id == 3 && step.hookId == 5', 'ev.id == 3'),
            ('locked object clicked open', "return go->HasGameObjectFlag(GO_FLAG_LOCKED) ? opening == Opening::Key : opening != Opening::Closed;", 'return opening != Opening::Closed;'),
            ('lockpick counted as click', 'lock->Index[i] == LOCKTYPE_OPEN', 'true'),
            ('quest-conditional interaction', '(go->HasGameObjectFlag(GO_FLAG_INTERACT_COND) && !go->ActivateToQuest(bot))', 'false'),
            ('granted quest item accepted', '(!cannon && (step.kind == EventStepKind::UseItem || step.itemId))', 'false'),
            ('escort on another map', 'ev.mapId != 43 || ', ''),
            ('escort on another event', ' || ev.id != 2', ''),
            ('wrong escort creature', 'step.creatureEntry == 3678 &&', ''),
            ('wrong escort gossip', 'step.gossipOption == 0 &&', ''),
            ('wrong escort final boss', 'step.escortDoneEntry == 3654 &&', ''),
            ('wrong escort kill credit', 'step.escortDoneBit == 7 &&', ''),
            ('escort hook bypass', 'step.hookId == 0 && step.instanceDataId < 0', 'step.instanceDataId < 0'),
            ('escort data bypass', '&& step.instanceDataId < 0', ''),
            ('arbitrary item target accepted', 'step.goEntry == 16398 &&', ''),
            ('unearned cannon item accepted', 'step.itemId == 5397 &&', ''),
            ('arbitrary cannon spell accepted', 'step.spellId == 6250 &&', ''),
            ('cannon custom hook accepted', '&& step.hookId == 0', ''),
            ('locked powder source accepted', 'LockOpening(chest->GetLockId(), nullptr) != Opening::Click', 'false'),
            ('wrong cannon lock accepted', 'target->GetLockId() != 83', 'false'),
            ('legacy objective hook', 'else if (info.onArriveHook)', 'else if (false)'),
            ('roster event objectives ignored', 'BossRosterRegistry::Apply(\n                 mapId, normal, BossSpawnIndex::Get(mapId, DUNGEON_DIFFICULTY_NORMAL))', 'BossSpawnIndex::Get(mapId, DUNGEON_DIFFICULTY_NORMAL)'),
            ('optional anchored controller skipped', 'if (essential(*ev) && DcGateMatches(ev->gate, normal)', 'if (ev->required && DcGateMatches(ev->gate, normal)'),
            ('conditional events skipped', 'if (essential(*ev) && !StepsAudited(*ev, reason))', 'if (false)'),
            ('optional pull controller skipped', 'return ev.required || ev.ownsThePull || ev.stepsOwnMovement;', 'return ev.required || ev.stepsOwnMovement;'),
            ('optional movement controller skipped', 'return ev.required || ev.ownsThePull || ev.stepsOwnMovement;', 'return ev.required || ev.ownsThePull;'),
        ]
        reject_mutants(work, [(label, 'DcEarnedEvents.cpp', old, new) for label, old, new in mutations],
                       lambda directory, executable: [compiler, '-std=c++20', '-O1', '-I', str(directory),
                                                      str(directory/'fixture.cpp'), '-o', str(executable)],
                       'Earned event audit')


if __name__ == '__main__':
    main()
