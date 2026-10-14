#!/usr/bin/env python3
"""Exercise the earned Dungeon Clear event audit with native lock and registry doubles."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from FixtureSupport import function, prepared_core


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
struct EventStep{{EventStepKind kind{{EventStepKind::Wait}};uint32 goEntry=0,itemId=0,hookId=0;int32 instanceDataId=-1;uint32 instanceDataMin=0;}};
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
 roster[5]={{"Ring of Law",7,0}};assert(!audited(5));
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
    parser.add_argument('--source', type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    core = prepared_core(repo)
    source = args.source or core/'modules/mod-dungeon-clear/src'
    if not (source/'DcEarnedEvents.cpp').exists():
        raise SystemExit('PrepareModules.cmake must prepare the earned DungeonClear patch first')
    native_contracts(core, source)
    compiler = shutil.which('c++') or shutil.which('g++') or shutil.which('clang++')
    if not compiler:
        raise SystemExit('A C++20 compiler is required')
    registry = (source/'Ai/Dungeon/DungeonClear/Data/DungeonEventRegistry.h').read_text()
    kinds = re.findall(r'^\s{4}([A-Z][A-Za-z]+),', block(registry, 'enum class EventStepKind : uint8'), re.M)
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
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-no-pie']
        subprocess.run([compiler, *flags, str(work/'fixture.cpp'), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
        original = (work/'DcEarnedEvents.cpp').read_text()
        mutations = [
            ('off-mesh jump step', 'case EventStepKind::MoveTo:\n                return step.hookId == 0;', 'case EventStepKind::Jump:\n            case EventStepKind::MoveTo:\n                return step.hookId == 0;'),
            ('custom hook on a walk', 'return step.hookId == 0;', 'return true;'),
            ('locked object clicked open', "return go->HasGameObjectFlag(GO_FLAG_LOCKED) ? opening == Opening::Key : opening != Opening::Closed;", 'return opening != Opening::Closed;'),
            ('lockpick counted as click', 'SkillByLockType(LockType(lock->Index[i])) == SKILL_NONE', 'true'),
            ('quest-conditional interaction', '(go->HasGameObjectFlag(GO_FLAG_INTERACT_COND) && !go->ActivateToQuest(bot))', 'false'),
            ('granted quest item accepted', '|| step.kind == EventStepKind::UseItem || step.itemId', ''),
            ('legacy objective hook', 'else if (info.onArriveHook)', 'else if (false)'),
            ('roster event objectives ignored', 'BossRosterRegistry::Apply(\n                 mapId, normal, BossSpawnIndex::Get(mapId, DUNGEON_DIFFICULTY_NORMAL))', 'BossSpawnIndex::Get(mapId, DUNGEON_DIFFICULTY_NORMAL)'),
            ('optional anchored controller skipped', 'if (essential(*ev) && DcGateMatches(ev->gate, normal)', 'if (ev->required && DcGateMatches(ev->gate, normal)'),
            ('conditional events skipped', 'if (essential(*ev) && !StepsAudited(*ev, reason))', 'if (false)'),
            ('optional pull controller skipped', 'return ev.required || ev.ownsThePull || ev.stepsOwnMovement;', 'return ev.required || ev.stepsOwnMovement;'),
            ('optional movement controller skipped', 'return ev.required || ev.ownsThePull || ev.stepsOwnMovement;', 'return ev.required || ev.ownsThePull;'),
        ]
        for label, old, new in mutations:
            mutated = original.replace(old, new)
            if mutated == original:
                raise SystemExit(f'{label} mutation was not applied')
            (work/'DcEarnedEvents.cpp').write_text(mutated)
            subprocess.run([compiler, '-std=c++20', '-O1', '-I', str(work), str(work/'fixture.cpp'), '-o', str(exe)], check=True)
            result = subprocess.run([str(exe)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode == 0:
                raise SystemExit(f'Earned event audit did not reject {label}')
            print(f'Earned event audit mutation rejected: {label}')


if __name__ == '__main__':
    main()
