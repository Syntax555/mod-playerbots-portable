"""Exercise the real altar driver, authored steps and native ritual implementation."""
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


def audit_uldaman(core, source, compiler):
    repository = Path(__file__).resolve().parents[2]
    locale = json.loads((repository / 'versions.lock.json').read_text())['clientPatch']['localizations']['deDE']
    url = locale['url'].removesuffix('.git').replace('github.com/', 'raw.githubusercontent.com/')
    url += f'/{locale["revision"]}/{locale["sourcePath"]}/Lock.dbc'
    cache = repository / '.module-cache/fixtures/Lock.dbc'
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            data = response.read()
        assert hashlib.sha256(data).hexdigest() == 'c49bd7ed970583a3660d5d16d6917e91e46aafc9e9ed7926281f4889d45904d0'
        cache.write_bytes(data)
    data = cache.read_bytes()
    assert hashlib.sha256(data).hexdigest() == 'c49bd7ed970583a3660d5d16d6917e91e46aafc9e9ed7926281f4889d45904d0'
    rows, _ = wdbc(data, 33)
    dbc_structure = (core / 'src/server/shared/DataStores/DBCStructure.h').read_text()
    assert '#define MAX_LOCK_CASE 8' in dbc_structure
    native_lock = function(dbc_structure, 'struct LockEntry')
    assert re.search(r'uint32\s+Type\[MAX_LOCK_CASE\];', native_lock)
    assert re.search(r'uint32\s+Index\[MAX_LOCK_CASE\];', native_lock)
    lock = next(struct.unpack('<33I', row) for row in rows if struct.unpack_from('<I', row)[0] == 359)
    assert lock[1:9] == (1, 0, 0, 0, 0, 0, 0, 0) and lock[9:17] == (7733, 0, 0, 0, 0, 0, 0, 0)
    keystone = sql_rows(core, 'gameobject_template', {124371})[0]
    assert int(keystone['type']) == 0 and int(keystone['Data1']) == lock[0]
    go_data = (core / 'src/server/game/Entities/GameObject/GameObjectData.h').read_text()
    assert re.search(r'case GAMEOBJECT_TYPE_DOOR:\s*return door.lockId;', function(go_data, 'uint32 GetLockId() const'))
    events = (source / 'Ai/Dungeon/DungeonClear/Data/Events/UldamanEvents.cpp').read_text()
    assert '.UseGO(ULD_KEYSTONE,' in events and re.search(r'ULD_KEYSTONE\s*=\s*124371;', events)
    harness = r'''
#include "DcEarnedEvents.cpp"
#include <cassert>
#include <iostream>
int main(){
    LockEntry staff{359,{1},{7733},{}};sLockStore.rows[359]=staff;
    objectMgr.templates={{124371,{359}},{130511,{0}},{133234,{0}}};
    auto altar=[](uint32 entry){EventStep step;step.kind=EventStepKind::UseGameObject;step.goEntry=entry;return step;};
    DungeonEvent keepers;keepers.name="Keepers";keepers.steps={altar(130511)};
    DungeonEvent archaedas;archaedas.name="Archaedas";archaedas.steps={altar(133234)};
    events[{70,2}]=keepers;events[{70,3}]=archaedas;roster[70]={{"Keepers",0,2},{"Archaedas",0,3}};
    std::string reason;assert(DcEarnedEvents::MapAudited(70,reason)&&reason.empty());
    DungeonEvent ironaya;ironaya.name="Ironaya";ironaya.steps={altar(124371)};conditional[70]={ironaya};
    assert(!DcEarnedEvents::MapAudited(70,reason));assert(reason.find("Ironaya")!=std::string::npos);
    assert(reason.find("key or locked object")!=std::string::npos);
    Player player;GameObject keystone;keystone.info.lock=359;
    assert(!DcEarnedEvents::CanOpen(&player,&keystone));player.items.insert(7733);
    assert(DcEarnedEvents::CanOpen(&player,&keystone));
    std::cout<<"Uldaman audit: regular altars pass, native Staff of Prehistoria lock 359 still refuses autonomous recruitment\n";
}
'''
    with tempfile.TemporaryDirectory(prefix='uldaman-audit-') as temp:
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
        (work / 'fixture.cpp').write_text(harness)
        exe = work / ('fixture.exe' if os.name == 'nt' else 'fixture')
        subprocess.run([compiler, '-std=c++20', '-O1', '-I', str(work), str(work / 'fixture.cpp'), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=TIMEOUT)
        mutations = [('staff lock ignored', 'DcEarnedEvents.cpp', 'LockOpening(go->GetLockId(), nullptr) != Opening::Click', 'false')]
        reject_mutants(work, mutations, lambda directory, executable: [compiler, '-std=c++20', '-O1', '-I', str(directory),
                       str(directory / 'fixture.cpp'), '-o', str(executable)], 'Uldaman audit')


def native_sources(core, source):
    objects = {int(row['entry']): row for row in sql_rows(core, 'gameobject_template', {130511, 133234})}
    for entry, spell in ((130511, 11568), (133234, 10340)):
        row = objects[entry]
        assert int(row['type']) == 18
        assert [int(row[f'Data{i}']) for i in range(7)] == [1, spell, 11206, 1, 0, 1, 1]
    uldaman = core / 'src/server/scripts/EasternKingdoms/Uldaman'
    header = (uldaman / 'uldaman.h').read_text()
    for name, value in (('DATA_STONE_KEEPERS', 1), ('DATA_ARCHAEDAS', 2),
                        ('NPC_STONE_KEEPER', 4857), ('NPC_ARCHAEDAS', 2748)):
        assert re.search(rf'\b{name}\s*=\s*{value}\b', header)
    scripts = (uldaman / 'instance_uldaman.cpp').read_text()
    keeper = function(scripts.split('class spell_uldaman_sub_boss_agro_keepers', 1)[1], 'void HandleSendEvent(')
    archaedas = function(scripts.split('class spell_uldaman_boss_agro_archaedas', 1)[1], 'void HandleSendEvent(')
    names = sql_rows(core, 'spell_script_names', {11568, 10340})
    assert {(int(row['spell_id']), row['ScriptName']) for row in names} == {
        (11568, 'spell_uldaman_sub_boss_agro_keepers'), (10340, 'spell_uldaman_boss_agro_archaedas')}
    smart = sql_rows(core, 'smart_scripts', {-28368, -27794, -27555, -27554})
    for spawn in (-28368, -27794, -27555, -27554):
        rows = [row for row in smart if int(row['entryorguid']) == spawn]
        assert any(int(row['event_type']) == 25 and int(row['action_type']) == 11 and
                   int(row['action_param1']) == 10255 for row in rows)
        assert any(int(row['event_type']) == 38 and int(row['event_param1']) == 1 and
                   int(row['event_param2']) == 1 and int(row['action_type']) == 28 and
                   int(row['action_param1']) == 10255 for row in rows)
        assert any(int(row['action_type']) == 34 and int(row['action_param1']) == 1 and
                   int(row['action_param2']) == 3 for row in rows)
    boss = sql_rows(core, 'smart_scripts', {2748})
    assert any(int(row['event_type']) == 6 and int(row['action_type']) == 34 and
               int(row['action_param1']) == 2 and int(row['action_param2']) == 3 for row in boss)
    assert any(int(row['event_type']) == 21 and int(row['action_type']) == 34 and
               int(row['action_param1']) == 2 and int(row['action_param2']) == 0 for row in boss)
    assert any(int(row['event_type']) == 61 and int(row['action_type']) == 67 and
               int(row['action_param1']) == 1 and int(row['action_param2']) == 4000 and
               int(row['action_param3']) == 4000 for row in boss)
    assert any(int(row['event_type']) == 59 and int(row['event_param1']) == 1 and
               int(row['action_type']) == 28 and int(row['action_param1']) == 10255 for row in boss)

    go = (core / 'src/server/game/Entities/GameObject/GameObject.cpp').read_text()
    use = go.split('case GAMEOBJECT_TYPE_SUMMONING_RITUAL:              //18', 1)[1]
    use = function(use, '{')
    update = go.split('case GAMEOBJECT_TYPE_SUMMONING_RITUAL:', 1)[1]
    update = function(update, '{')
    # The extracted cases have no outer switch: only strip their outer braces.
    native = ['void GameObject::RitualUse(Unit* user) ' + use,
              'void GameObject::RitualUpdate() ' + update,
              function(go, 'void GameObject::CheckRitualList()'),
              function(go, 'void GameObject::ClearRitualList()'),
              'struct KeeperScript { Player* caster; Player* GetCaster(){return caster;} ' + keeper + ' };',
              'struct ArchaedasScript { Player* caster; Player* GetCaster(){return caster;} ' + archaedas + ' };']
    assert 'm_cooldownTime = GameTime::GetGameTimeMS().count() + 5 * IN_MILLISECONDS;' in use
    assert 'm_cooldownTime' in update and 'CheckRitualList();' in update
    bounds = function(go, 'bool GameObject::IsWithinDistInMap(Player const* player) const')
    assert 'IsInMap(player) && InSamePhase(player) && IsAtInteractDistance(player)' in bounds
    handler = function((core / 'src/server/game/Handlers/SpellHandler.cpp').read_text(),
                       'void WorldSession::HandleGameObjectUseOpcode(')
    assert '!obj->isSpawned()' in handler
    assert '!obj->IsWithinDistInMap(GetPlayer(), obj->GetInteractionDistance())' in handler
    assert 'obj->Use(GetPlayer());' in handler
    action = (core / 'modules/mod-playerbots/src/Ai/Base/Actions/UseItemAction.cpp').read_text()
    assert 'return UseGameObject(*gos.begin());' in function(action, 'bool UseItemAction::Execute(')
    assert 'HandleGameObjectUseOpcode(use)' in function(action, 'bool UseItemAction::UseGameObject(')
    assert 'HandleGameobjectReportUse(report)' in function(action, 'bool UseItemAction::UseGameObject(')
    lock = function((source / 'DcEarnedEvents.cpp').read_text(), 'bool CanOpen(')
    assert 'GO_FLAG_NOT_SELECTABLE' in lock and 'GO_FLAG_INTERACT_COND' in lock
    assert 'GetLockId()' in lock
    opening = function((source / 'DcEarnedEvents.cpp').read_text(), 'Opening LockOpening(')
    assert 'HasItemCount(' in opening and 'LOCK_KEY_ITEM' in opening
    helper = (source / 'DcUldamanAltars.cpp').read_text()
    for shortcut in ('CastSpell(', 'SetData(', '->Use(', 'AI()->', 'AddItem(', 'StoreNewItem(', 'SetGoState('):
        assert shortcut not in helper, shortcut
    chat = (core / 'modules/mod-playerbots/src/Bot/Cmd/ChatHelper.cpp').read_text()
    native += [function(chat, 'std::string const ChatHelper::FormatGameobject('),
               function(chat, 'GuidVector ChatHelper::parseGameobjects(')]
    return '\n'.join(native)


STUBS = r'''#pragma once
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <list>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>
using uint8=uint8_t;using uint32=uint32_t;using uint64=uint64_t;using int32=int32_t;
using ObjectGuid=uint32;using GuidSet=std::set<ObjectGuid>;using GuidVector=std::vector<ObjectGuid>;
enum TeamId{TEAM_ALLIANCE,TEAM_HORDE,TEAM_NEUTRAL};
enum class DcDifficultyGate:uint8{Any,NormalOnly,HeroicOnly};
struct DcDiffKey{bool IsHeroic()const{return false;}};
enum class StepResult:uint8{Running,Done,Blocked,Failed};
constexpr uint32 NOT_STARTED=0,IN_PROGRESS=1,DONE=3,GO_READY=1,GO_NOT_READY=0,GO_JUST_DEACTIVATED=3;
constexpr uint32 GAMEOBJECT_TYPE_SUMMONING_RITUAL=18,FORCED_MOVEMENT_NONE=0,CURRENT_CHANNELED_SPELL=1;
constexpr uint32 DATA_ARCHAEDAS=2,NPC_ARCHAEDAS=2748,NPC_STONE_KEEPER=4857,IN_MILLISECONDS=1000;
constexpr uint32 TRIGGERED_IGNORE_EFFECTS=1,TRIGGERED_IGNORE_SPELL_AND_CATEGORY_CD=2;
constexpr uint32 TRIGGERED_IGNORE_POWER_AND_REAGENT_COST=4,TRIGGERED_CAST_DIRECTLY=8,SPELL_CAST_OK=0;
using TriggerCastFlags=uint32;using SpellCastResult=uint32;using SpellEffIndex=uint32;
class Player;class GameObject;
struct DungeonEvent;struct DungeonEventProgress;enum class EventDriveOutcome:uint8;
struct SpellInfo{uint32 Id=11206;};
struct Spell{SpellInfo info;SpellInfo* m_spellInfo=&info;bool active=false;uint32 finishes=0;
    void SendChannelUpdate(uint32 value){assert(value==0);}void finish(bool=true){active=false;++finishes;}};
struct Unit{virtual ~Unit()=default;Spell channel;virtual bool IsPlayer()const{return false;}
    virtual Player* ToPlayer(){return nullptr;}Spell* GetCurrentSpell(uint32){return channel.active?&channel:nullptr;}
    virtual SpellCastResult CastSpell(Unit*,uint32,uint32);};
struct InstanceScript{uint32 data[3]={0,0,0};uint32 writes=0;uint32 GetData(uint32 key)const{return data[key];}
    void SetData(uint32 key,uint32 value){data[key]=value;++writes;}};
struct Creature{uint32 entry;bool alive=true,stoned=true,inMap=true,phase=true;float distance=2;uint32 wakes=0;
    bool IsAlive()const{return alive;}bool IsInMap(Player*)const{return inMap;}bool InSamePhase(Player*)const{return phase;}
    bool HasAura(uint32 spell)const{assert(spell==10255);return stoned;}Creature* AI(){return this;}
    void SetData(uint32 key,uint32 value){assert(key==1&&value==1);if(entry==4857)stoned=false;++wakes;}};
struct GameObjectTemplate{struct{uint32 reqParticipants=1,spellId=11568,animSpell=11206,castersGrouped=1;
    uint32 casterTargetSpell=0,casterTargetSpellTargets=1,ritualPersistent=1;}summoningRitual;};
namespace GameTime{inline uint32 now=0;struct Time{uint32 value;uint32 count()const{return value;}};
inline Time GetGameTimeMS(){return {now};}}
namespace Acore::Containers{template<class T>auto SelectRandomContainerElement(T const& values){return *values.begin();}}
namespace ObjectAccessor{Player* GetPlayer(GameObject const&,ObjectGuid);}
struct GameObject
{
    uint32 entry,guid,loot=GO_READY,type=18,state=1;bool spawned=true,inMap=true,phase=true,within=true,los=true;
    bool canOpen=true,selectable=true,eligible=true,locked=false;float distance=2,x=0,y=0,z=0;
    GameObjectTemplate info;ObjectGuid m_ritualOwnerGUID=0;GuidSet m_unique_users;uint32 m_cooldownTime=0;
    GameObject(uint32 value,uint32 id):entry(value),guid(id){info.summoningRitual.spellId=entry==130511?11568:10340;}
    struct RawGuid{uint32 value;uint32 GetRawValue()const{return value;}};
    bool isSpawned()const{return spawned;}uint32 GetEntry()const{return entry;}RawGuid GetGUID()const{return {guid};}
    std::string GetNameForLocaleIdx(uint32)const{return "Altar";}
    uint32 GetGoType()const{return type;}uint32 getLootState()const{return loot;}void SetLootState(uint32 value){loot=value;}
    uint32 GetGoState()const{return state;}GameObjectTemplate const* GetGOInfo()const{return &info;}
    Unit* GetOwner()const{return nullptr;}ObjectGuid GetOwnerGUID()const{return 0;}uint32 GetSpellId()const{return 11206;}
    uint32 GetUniqueUseCount()const{return m_unique_users.size();}void AddUniqueUse(Player*);
    bool IsWithinDistInMap(Player*)const{return inMap&&phase&&within&&distance<=5.0f;}
    float GetPositionX()const{return x;}float GetPositionY()const{return y;}float GetPositionZ()const{return z;}
    void CheckRitualList();void ClearRitualList();void RitualUse(Unit* user);void RitualUpdate();
};
struct PlayerbotAI{Player* bot;bool movable=true;bool CanMove()const{return movable;}};
struct MotionMaster{Player* bot;uint32 calls=0;bool generated=false;
    void MovePoint(uint32,float,float,float,uint32,float,float,bool generate,bool);};
class Player:public Unit
{
public:
    uint32 guid=1,mapId=70,loot=0,stops=0,uses=0,events=0,raid=1;bool ai=true,hasInstance=true,alive=true;
    bool combat=false,flight=false,casting=false,moving=false,reachable=true,useAllowed=true;
    Player* m_mover=this;PlayerbotAI botAI{this};MotionMaster motion{this};InstanceScript instance;
    GameObject keeperAltar{130511,101},archAltar{133234,102};Creature keeper{4857},otherKeeper{4857},arch{2748};
    std::map<uint32,GameObject*> objects{{130511,&keeperAltar},{133234,&archAltar}};
    std::vector<Creature*> creatures{&keeper,&otherKeeper,&arch};
    uint32 GetMapId()const{return mapId;}bool IsAlive()const{return alive;}bool IsInCombat()const{return combat;}
    bool IsInFlight()const{return flight;}bool IsNonMeleeSpellCast(bool)const{return casting||channel.active;}
    uint32 GetLootGUID()const{return loot;}InstanceScript* GetInstanceScript(){return hasInstance?&instance:nullptr;}
    GameObject* FindNearestGameObject(uint32 value,float range){auto found=objects.find(value);
        return found==objects.end()||found->second->distance>range?nullptr:found->second;}
    void GetCreatureListWithEntryInGrid(std::list<Creature*>& out,uint32 entry,float range){
        for(auto* creature:creatures)if(creature->entry==entry&&creature->distance<=range)out.push_back(creature);}
    Creature* FindNearestCreature(uint32 entry,float range,bool live){Creature* result=nullptr;
        for(auto* creature:creatures){if(creature->entry==entry&&(!live||creature->alive)&&creature->distance<=range&&
           creature->inMap&&creature->phase&&(!result||creature->distance<result->distance))result=creature;}return result;}
    float GetExactDist(GameObject* go)const{return go->distance;}bool isMoving()const{return moving;}
    void StopMoving(){++stops;moving=false;}MotionMaster* GetMotionMaster(){return &motion;}
    bool IsPlayer()const override{return true;}Player* ToPlayer()override{return this;}
    uint32 GetGUID()const{return guid;}bool IsInSameRaidWith(Player* other)const{return raid&&raid==other->raid;}
};
inline std::map<uint32,Player*> players;
Player* ObjectAccessor::GetPlayer(GameObject const&,ObjectGuid guid){auto found=players.find(guid);return found==players.end()?nullptr:found->second;}
void GameObject::AddUniqueUse(Player* bot){m_unique_users.insert(bot->guid);}
void MotionMaster::MovePoint(uint32,float,float,float,uint32,float,float,bool generate,bool){assert(bot->reachable);++calls;generated=generate;bot->moving=true;}
#define GET_PLAYERBOT_AI(bot) ((bot)->ai?&(bot)->botAI:nullptr)
struct Config{std::set<uint32> DisallowedGameObjects;} sPlayerbotAIConfig;
namespace DcEarnedEvents{inline bool CanOpen(Player*,GameObject* go){return go->canOpen&&go->selectable&&go->eligible&&!go->locked;}}
namespace DcEarnedPlay{inline bool ReachableLeg(Player* bot,float,float,float){return bot->reachable;}}
struct DungeonEventExecutor{static bool HasGameObjectLos(Player*,GameObject* go){return go->los;}
    static EventDriveOutcome Advance(DungeonEvent const&,DungeonEventProgress&,StepResult,uint32,uint32);};
struct Event{std::string name,param;Event(std::string value,std::string text):name(value),param(text){}};
struct World{uint32 GetDefaultDbcLocale()const{return 0;}}world;inline World* sWorld=&world;
struct ChatHelper{static std::string const FormatGameobject(GameObject* go);static GuidVector parseGameobjects(std::string const text);};
struct UseItemAction{PlayerbotAI* ai;explicit UseItemAction(PlayerbotAI* value):ai(value){}
    bool Execute(Event event){assert(event.name=="use");Player* bot=ai->bot;++bot->uses;
        auto guids=ChatHelper::parseGameobjects(event.param);assert(guids.size()==1);GameObject* go=nullptr;
        for(auto const& [entry,object]:bot->objects)if(object->guid==guids.front())go=object;
        assert(go&&!bot->moving&&event.param==ChatHelper::FormatGameobject(go));
        if(!bot->useAllowed)return false;
        if(!go->spawned||!go->IsWithinDistInMap(bot)||!go->canOpen||go->locked)return false;
        players[bot->guid]=bot;go->RitualUse(bot);return true;}};
'''


HARNESS = r'''
#include "DcUldamanAltars.cpp"
#include "NativeRitual.cpp"
#include "AuthoredAltars.cpp"
#include <iostream>
SpellCastResult Unit::CastSpell(Unit*,uint32 spell,uint32)
{
    Player* player=ToPlayer();assert(player);
    if(spell==11206){channel.active=true;channel.info.Id=spell;return SPELL_CAST_OK;}
    ++player->events;
    if(spell==11568)KeeperScript{player}.HandleSendEvent(0);
    else{assert(spell==10340);ArchaedasScript{player}.HandleSendEvent(0);}
    return SPELL_CAST_OK;
}
using DcUldamanAltars::Run;
void running(Player& bot,uint32 entry){assert(Run(&bot,entry)==StepResult::Running);}
void quiet(Player& bot,uint32 entry){running(bot,entry);assert(!bot.uses&&!bot.motion.calls&&!bot.events&&!bot.instance.writes);}
GameObject& altar(Player& bot,uint32 entry){return entry==130511?bot.keeperAltar:bot.archAltar;}
void GateTests(uint32 entry)
{
    for(uint32 gate=0;gate<6;++gate){Player bot;switch(gate){case 0:bot.alive=false;break;case 1:bot.combat=true;break;
        case 2:bot.flight=true;break;case 3:bot.m_mover=nullptr;break;case 4:bot.casting=true;break;case 5:bot.loot=999;break;}quiet(bot,entry);}
    for(uint32 gate=0;gate<16;++gate){Player bot;auto& go=altar(bot,entry);bool blocked=false;
        switch(gate){case 0:bot.objects.erase(entry);break;case 1:go.spawned=false;break;case 2:go.distance=101;break;
        case 3:go.canOpen=false;blocked=true;break;case 4:go.locked=true;blocked=true;break;
        case 5:go.selectable=false;blocked=true;break;case 6:go.eligible=false;blocked=true;break;
        case 7:sPlayerbotAIConfig.DisallowedGameObjects.insert(entry);blocked=true;break;
        case 8:go.type=10;blocked=true;break;case 9:go.loot=GO_NOT_READY;break;case 10:go.loot=GO_JUST_DEACTIVATED;break;
        case 11:go.distance=20;bot.reachable=false;break;case 12:go.distance=20;bot.botAI.movable=false;break;
        case 13:bot.creatures.clear();break;case 14:for(auto* c:bot.creatures)c->alive=false;break;
        case 15:for(auto* c:bot.creatures)c->distance=101;break;}
        assert(Run(&bot,entry)==(blocked?StepResult::Blocked:StepResult::Running));
        assert(!bot.uses&&!bot.events&&!bot.motion.calls&&!bot.instance.writes);sPlayerbotAIConfig.DisallowedGameObjects.clear();}
    for(uint32 gate=0;gate<5;++gate){Player bot;auto& go=altar(bot,entry);
        switch(gate){case 0:go.distance=5.01f;break;case 1:go.within=false;break;case 2:go.inMap=false;break;
            case 3:go.phase=false;break;case 4:go.los=false;break;}
        running(bot,entry);assert(bot.motion.calls==1&&bot.motion.generated&&!bot.uses);
        running(bot,entry);assert(bot.motion.calls==1&&!bot.uses);}
    for(float distance:{4.9f,5.0f}){Player bot;altar(bot,entry).distance=distance;running(bot,entry);
        assert(bot.uses==1&&bot.channel.active&&!bot.motion.calls&&!bot.events);}
    Player stopping;stopping.moving=true;running(stopping,entry);assert(stopping.stops==1&&!stopping.uses);
    running(stopping,entry);assert(stopping.uses==1&&stopping.channel.active&&!stopping.events);
    for(uint32 gate=0;gate<2;++gate){Player bot;for(auto* c:bot.creatures){if(gate==0)c->inMap=false;else c->phase=false;}quiet(bot,entry);}
}
void NativeRitualTests(uint32 entry)
{
    GameTime::now=0;Player bot;players={{1,&bot}};auto& go=altar(bot,entry);go.distance=4.9f;
    bot.useAllowed=false;running(bot,entry);assert(bot.uses==1&&!bot.channel.active&&!bot.events);
    bot.useAllowed=true;running(bot,entry);assert(bot.uses==2&&bot.channel.active&&go.loot==GO_NOT_READY);
    assert(go.m_unique_users.size()==1&&!bot.events&&!bot.instance.writes);
    for(uint32 tick=0;tick<3;++tick)running(bot,entry);
    assert(bot.uses==2);GameTime::now=4999;go.RitualUpdate();assert(!bot.events&&bot.channel.active);
    // A native interrupted channel is removed at the normal five-second update.
    bot.channel.active=false;GameTime::now=5000;go.RitualUpdate();
    assert(go.loot==GO_READY&&go.m_unique_users.empty()&&!bot.events);running(bot,entry);
    assert(bot.uses==3&&bot.channel.active);GameTime::now=9999;go.RitualUpdate();assert(!bot.events);
    GameTime::now=10000;go.RitualUpdate();assert(bot.events==1&&!bot.channel.active&&bot.channel.finishes==1);
    assert(go.loot==GO_READY&&go.m_unique_users.empty());running(bot,entry);assert(bot.uses==3);
    if(entry==130511){assert(!bot.keeper.stoned&&bot.otherKeeper.stoned&&bot.instance.GetData(1)==NOT_STARTED);
        // A living awake keeper anywhere in the scan owns the native death chain.
        bot.keeper.stoned=true;bot.otherKeeper.stoned=false;bot.otherKeeper.distance=90;running(bot,entry);assert(bot.uses==3);
        bot.otherKeeper.alive=false;running(bot,entry);assert(bot.uses==4); // Interrupted fight/reset permits a fresh ritual.
    }else{assert(bot.arch.stoned&&bot.arch.wakes==1&&bot.instance.GetData(2)==IN_PROGRESS);
        running(bot,entry);assert(bot.uses==3); // Native four-second awaken is still pending: instance state wins.
        bot.instance.data[2]=NOT_STARTED;running(bot,entry);assert(bot.uses==4);}
    uint32 uses=bot.uses;bot.instance.data[entry==130511?1:2]=DONE;bot.alive=false;bot.creatures.clear();
    assert(Run(&bot,entry)==StepResult::Done&&bot.uses==uses);
    // The native ritual owner remains authoritative after a retry, including
    // its ordinary same-raid requirement; the driver never adds participants.
    Player owner,outsider;owner.guid=8;owner.raid=8;outsider.guid=9;outsider.raid=9;
    players={{8,&owner},{9,&outsider}};GameObject grouped(entry,300);grouped.m_ritualOwnerGUID=owner.guid;
    outsider.objects[entry]=&grouped;running(outsider,entry);assert(outsider.uses==1&&!outsider.channel.active&&grouped.m_unique_users.empty());
    outsider.raid=8;running(outsider,entry);assert(outsider.uses==2&&outsider.channel.active&&grouped.m_unique_users.size()==1);
    players.clear();
}
void AuthoredTests()
{
    std::vector<DungeonEvent> events;RegisterAltarEvents(events);assert(events.size()==2);
    for(auto const& event:events){assert(event.mapId==70&&event.required&&!event.persistent&&event.stepsOwnMovement);
        assert(event.activation==EventActivation::Anchored);uint32 uses=0;
        for(auto const& step:event.steps){assert(step.kind!=EventStepKind::CastSpell&&step.kind!=EventStepKind::KillCreature);
            if(step.kind==EventStepKind::UseGameObject){++uses;Player bot;uint32 entry=event.id==2?130511:133234;
                uint32 budget=event.id==2?120000:180000;
                assert(step.goEntry==entry&&step.timeoutMs==budget);altar(bot,entry).state=0;
                assert(RunAuthoredStep(&bot,step)==StepResult::Running&&bot.uses==1);
                // Real Advance must retain the fight beyond the ordinary 30s
                // default, while preserving the authored finite failure budget.
                DungeonEvent one=event;one.steps={step};DungeonEventProgress progress;
                assert(DungeonEventExecutor::Advance(one,progress,StepResult::Running,30001,30000)==EventDriveOutcome::Running);
                assert(DungeonEventExecutor::Advance(one,progress,StepResult::Running,budget-1,30000)==EventDriveOutcome::Running);
                DungeonEventProgress expired=progress;
                assert(DungeonEventExecutor::Advance(one,expired,StepResult::Running,budget,30000)==EventDriveOutcome::Stalled);
                bot.instance.data[event.id==2?1:2]=DONE;assert(RunAuthoredStep(&bot,step)==StepResult::Done);
                assert(DungeonEventExecutor::Advance(one,progress,RunAuthoredStep(&bot,step),budget-1,30000)==EventDriveOutcome::Completed);}}
        assert(uses==1);}
    EventStep unrelated;unrelated.kind=EventStepKind::UseGameObject;unrelated.goEntry=1;Player bot;
    assert(RunAuthoredStep(&bot,unrelated)==StepResult::Failed);unrelated.goEntry=130511;bot.mapId=1;
    assert(RunAuthoredStep(&bot,unrelated)==StepResult::Failed);
    Player links;GameObject decoy(130511,999);links.objects[1]=&decoy;
    links.keeperAltar.guid=76543;running(links,130511);
    assert(links.channel.active&&links.keeperAltar.m_unique_users.size()==1&&decoy.m_unique_users.empty());
}
int main()
{
    assert(Run(nullptr,130511)==StepResult::Failed);Player invalid;invalid.mapId=1;assert(Run(&invalid,130511)==StepResult::Failed);
    invalid.mapId=70;invalid.ai=false;assert(Run(&invalid,130511)==StepResult::Failed);invalid.ai=true;
    assert(Run(&invalid,1)==StepResult::Failed);invalid.hasInstance=false;assert(Run(&invalid,130511)==StepResult::Blocked);
    for(uint32 entry:{130511,133234}){GateTests(entry);NativeRitualTests(entry);}AuthoredTests();
    std::cout<<"Uldaman altars: ordinary use, native five-second grouped ritual, interruption/retry, earned access and instance completion verified\n";
}
'''


def authored_sources(source):
    registry = source / 'Ai/Dungeon/DungeonClear/Data/DungeonEventRegistry.h'
    builder = registry.with_suffix('.cpp').read_text()
    authored = ['#include "DungeonEventRegistry.h"', '#include <utility>']
    for signature in ('EventBuilder::EventBuilder(', 'EventStep& EventBuilder::Add(',
                      'EventBuilder& EventBuilder::Anchored(', 'EventBuilder& EventBuilder::Persistent(',
                      'EventBuilder& EventBuilder::StepsOwnMovement(', 'EventBuilder& EventBuilder::MoveTo(',
                      'EventBuilder& EventBuilder::ClearRadius(', 'EventBuilder& EventBuilder::Timeout(',
                      'EventBuilder& EventBuilder::UseGO(', 'EventBuilder& EventBuilder::WaitForGOState('):
        authored.append(function(builder, signature))
    events = (source / 'Ai/Dungeon/DungeonClear/Data/Events/UldamanEvents.cpp').read_text()
    authored += re.findall(r'constexpr\s+(?:float|uint32)\s+ULD_\w+\s*=\s*[^;]+;', events)
    authored.append('void RegisterAltarEvents(std::vector<DungeonEvent>& out) {')
    for event in (2, 3):
        start = events.index(f'out.push_back(EventBuilder(70, {event},')
        end = events.index('.Build());', start) + len('.Build());')
        authored.append(events[start:end])
    authored.append('}')
    executor = (source / 'Ai/Dungeon/DungeonClear/Util/DungeonEventExecutor.cpp').read_text()
    executor_header = (source / 'Ai/Dungeon/DungeonClear/Util/DungeonEventExecutor.h').read_text()
    authored += [function(executor_header, 'enum class EventDriveOutcome') + ';',
                 function(executor_header, 'struct DungeonEventProgress') + ';',
                 re.search(r'constexpr uint32 DC_EVENT_NO_PROGRESS_FACTOR\s*=\s*\d+;', executor).group(),
                 function(executor, 'EventDriveOutcome DungeonEventExecutor::Advance(')]
    case = executor.split('case EventStepKind::UseGameObject:', 1)[1]
    assert case.index('return DcUldamanAltars::Run(bot, step.goEntry);') < case.index('go->GetGoState()')
    dispatch = case[case.index('if (bot->GetMapId()'):case.index('return DcUldamanAltars::Run(bot, step.goEntry);') +
                    len('return DcUldamanAltars::Run(bot, step.goEntry);')]
    authored.append('StepResult RunAuthoredStep(Player* bot,EventStep const& step){' + dispatch + '\nreturn StepResult::Failed;}')
    return registry, '\n'.join(authored)


def main():
    parser = argparse.ArgumentParser()
    source_argument(parser)
    args = parser.parse_args()
    core = prepared_core()
    source = args.source or core / 'modules/mod-dungeon-clear/src'
    native = native_sources(core, source)
    registry, authored = authored_sources(source)
    compiler = cxx()
    audit_uldaman(core, source, compiler)
    with tempfile.TemporaryDirectory(prefix='uldaman-altars-') as temp:
        work = Path(temp)
        (work / 'NativeStubs.h').write_text(STUBS)
        for name in ('Define.h', 'DcEarnedEvents.h', 'DcEarnedPlay.h', 'ChatHelper.h', 'Creature.h', 'Event.h',
                     'GameObject.h', 'InstanceScript.h', 'MotionMaster.h', 'Player.h', 'Playerbots.h',
                     'UseItemAction.h', 'Common.h', 'SharedDefines.h', 'Ai/Dungeon/DungeonClear/Data/DcDifficultyGate.h',
                     'Ai/Dungeon/DungeonClear/Util/DungeonEventExecutor.h'):
            path = work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('#include "NativeStubs.h"\n')
        for name in ('DcUldamanAltars.cpp', 'DcUldamanAltars.h'):
            shutil.copyfile(source / name, work / name)
        shutil.copyfile(registry, work / 'DungeonEventRegistry.h')
        (work / 'NativeRitual.cpp').write_text(native)
        (work / 'AuthoredAltars.cpp').write_text(authored)
        (work / 'fixture.cpp').write_text(HARNESS)
        exe = work / ('fixture.exe' if os.name == 'nt' else 'fixture')
        flags = ['-std=c++20', '-O1', '-Wall', '-Wextra', '-Wno-missing-field-initializers', '-I', str(work)]
        if os.name != 'nt':
            flags += [*SANITIZER_FLAGS, '-no-pie']
        subprocess.run([compiler, *flags, str(work / 'fixture.cpp'), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=TIMEOUT)
        gates = [
            ('wrong map', 'bot->GetMapId() != 70', 'false'), ('missing AI', '!GET_PLAYERBOT_AI(bot)', 'false'),
            ('wrong altar', '(altarEntry != 130511 && altarEntry != 133234)', 'false'),
            ('missing instance', 'if (!instance)', 'if (false)'),
            ('dead interaction', '!bot->IsAlive()', 'false'), ('combat interaction', 'bot->IsInCombat()', 'false'),
            ('flight interaction', 'bot->IsInFlight()', 'false'), ('remote mover', 'bot->m_mover != bot', 'false'),
            ('casting interruption', 'bot->IsNonMeleeSpellCast(false)', 'false'), ('loot interruption', 'bot->GetLootGUID()', 'false'),
            ('unspawned altar', '!altar->isSpawned()', 'false'), ('wrong object type', 'altar->GetGoType() != GAMEOBJECT_TYPE_SUMMONING_RITUAL', 'false'),
            ('server disallow', 'sPlayerbotAIConfig.DisallowedGameObjects.contains(altarEntry)', 'false'),
            ('native access', '!DcEarnedEvents::CanOpen(bot, altar)', 'false'),
            ('ritual readiness', 'altar->getLootState() != GO_READY', 'false'),
            ('native interaction range', '!altar->IsWithinDistInMap(bot)', 'false'),
            ('line of sight', '!DungeonEventExecutor::HasGameObjectLos(bot, altar)', 'false'),
            ('crowd controlled movement', 'GET_PLAYERBOT_AI(bot)->CanMove()', 'true'),
            ('mesh route', 'DcEarnedPlay::ReachableLeg(bot, altar->GetPositionX(), altar->GetPositionY(), altar->GetPositionZ())', 'true'),
            ('path generation', '/*generatePath*/ true, false', '/*generatePath*/ false, false'),
            ('restarted movement', '!bot->isMoving() &&', ''), ('moving interaction', 'if (bot->isMoving())', 'if (false)'),
            ('missing creatures', 'if (!present)', 'if (false)'), ('dead creatures', '!creature->IsAlive() || ', ''),
            ('wrong creature map', '!creature->IsInMap(bot) || ', ''), ('wrong creature phase', ' || !creature->InSamePhase(bot)', ''),
            ('awake event restarted', '!creature->HasAura(10255)', 'false'),
            ('running Archaedas restarted', '!keepers && state == IN_PROGRESS', 'false'),
            ('completion awarded before DONE', 'state == DONE', 'state != DONE'),
            ('regular use skipped', 'UseItemAction(GET_PLAYERBOT_AI(bot)).Execute(Event("use", ChatHelper::FormatGameobject(altar)));', '(void)0;'),
        ]
        mutations = [(label, 'DcUldamanAltars.cpp', old, new) for label, old, new in gates]
        mutations += [
            ('movement ownership', 'AuthoredAltars.cpp', '.StepsOwnMovement()', ''),
            ('sticky objective after wipe', 'AuthoredAltars.cpp', '.StepsOwnMovement()', '.Persistent().StepsOwnMovement()'),
            ('keeper fight default timeout', 'AuthoredAltars.cpp', '.Timeout(ULD_KEEPER_TIMEOUT)', ''),
            ('Archaedas fight default timeout', 'AuthoredAltars.cpp', '.Timeout(180000)', ''),
            ('ordinary use dispatch', 'AuthoredAltars.cpp', 'return DcUldamanAltars::Run(bot, step.goEntry);', 'return StepResult::Done;'),
            ('native ritual timer', 'NativeRitual.cpp', '+ 5 * IN_MILLISECONDS', '+ 0 * IN_MILLISECONDS'),
            ('native channel cleanup', 'NativeRitual.cpp', 'CheckRitualList();', '(void)0;'),
            ('native grouped requirement', 'NativeRitual.cpp', 'info->summoningRitual.castersGrouped && !player->IsInSameRaidWith(ritualOwner)', 'false'),
            ('object entry used as GUID', 'NativeRitual.cpp', 'go->GetGUID().GetRawValue()', 'go->GetEntry()'),
        ]
        reject_mutants(work, mutations, lambda directory, executable: [compiler, '-std=c++20', '-O1', '-I', str(directory),
                       str(directory / 'fixture.cpp'), '-o', str(executable)], 'Uldaman altars')


if __name__ == '__main__':
    main()
