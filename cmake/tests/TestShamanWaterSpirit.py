"""Check native Call of Water acceptance, retry timing and shared spirit deduplication."""

import argparse
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    cxx,
    function,
    in_parallel,
    prepared_core,
    run_fixture,
    source_argument,
    sql_rows,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help='Individual Progression module directory')
args = parser.parse_args()
core = prepared_core()
module = args.source or core / 'modules/mod-individual-progression'
base = module / 'data/sql/world/base/zz_shaman_water_spirit.sql'
update = module / 'data/sql/world/updates/2026_11_02_00_shaman_water_spirit.sql'
sql = base.read_text()
assert sql == update.read_text()
assert set(re.findall(r'(?:INTO|FROM)\s+' + chr(96) + r'([^' + chr(96) + r']+)', sql)) == {
    'smart_scripts', 'conditions'}
scripts = sql_rows(core, 'smart_scripts', {7007, 700700, 113791, 11379100})
assert {(int(row['entryorguid']), int(row['source_type']), int(row['id'])) for row in scripts} == {
    (7007, 0, 0), (700700, 9, 0), (700700, 9, 1), (700700, 9, 2),
    (113791, 1, 0), (11379100, 9, 0), (11379100, 9, 1), (11379100, 9, 2)}
quests = {int(row['ID']): row for row in sql_rows(core, 'quest_template', {63, 100, 1103})}
addon = {int(row['ID']): row for row in sql_rows(core, 'quest_template_addon', {100, 1103})}
assert int(addon[1103]['SpecialFlags']) == 0 and int(addon[1103]['PrevQuestID']) == -100
assert int(quests[100]['StartItem']) == 0
for index in range(1, 5):
    assert int(quests[100]['RequiredNpcOrGo' + str(index)]) == 0
for index in range(1, 7):
    assert int(quests[100]['RequiredItemId' + str(index)]) == 0

# Apply the actual paired SQL twice to native-shaped tables, retaining unrelated events.
db = sqlite3.connect(':memory:')
for table, rows in (('smart_scripts', scripts), ('conditions', [])):
    schema = (core / f'data/sql/base/db_world/{table}.sql').read_text().split(
        'CREATE TABLE ' + chr(96) + table + chr(96) + ' (', 1)[1].split(') ENGINE', 1)[0]
    fields = re.findall(r'^\s*' + chr(96) + r'([^' + chr(96) + r']+)' + chr(96) + r' (.+),?$', schema, re.MULTILINE)
    definitions = []
    for name, declaration in fields:
        text_type = bool(re.search(r'char|text', declaration))
        default = re.search(r"DEFAULT '([^']*)'", declaration)
        value = default[1] if default else '' if text_type else '0'
        definitions.append('"' + name + '" ' + ('TEXT' if text_type else 'INTEGER')
                           + " DEFAULT '" + value.replace("'", "''") + "'")
    db.execute(f'CREATE TABLE {table} (' + ','.join(definitions) + ')')
    for row in rows:
        db.execute(f'INSERT INTO {table} VALUES (' + ','.join('?' for _ in row) + ')', tuple(row.values()))
db.execute("INSERT INTO smart_scripts (entryorguid,source_type,id,comment) VALUES (7007,0,99,'unrelated event')")
original = db.execute('SELECT * FROM smart_scripts WHERE id=0 OR id=99 ORDER BY entryorguid,source_type,id').fetchall()
db.executescript(sql)
first = (db.execute('SELECT * FROM smart_scripts ORDER BY entryorguid,source_type,id').fetchall(),
         db.execute('SELECT * FROM conditions ORDER BY SourceEntry,SourceGroup').fetchall())
db.executescript(sql)
assert first == (db.execute('SELECT * FROM smart_scripts ORDER BY entryorguid,source_type,id').fetchall(),
                 db.execute('SELECT * FROM conditions ORDER BY SourceEntry,SourceGroup').fetchall())
assert original == db.execute(
    'SELECT * FROM smart_scripts WHERE id=0 OR id=99 ORDER BY entryorguid,source_type,id').fetchall()


def records(table):
    cursor = db.execute('SELECT * FROM ' + table)
    return [dict(zip((column[0] for column in cursor.description), row)) for row in cursor]


events = records('smart_scripts')
guards = records('conditions')
assert len(guards) == 2

smart = (core / 'src/server/game/AI/SmartScripts/SmartScript.cpp').read_text()
smart_ai = (core / 'src/server/game/AI/SmartScripts/SmartAI.cpp').read_text()
smart_header = (core / 'src/server/game/AI/SmartScripts/SmartScriptMgr.h').read_text()
conditions = (core / 'src/server/game/Conditions/ConditionMgr.cpp').read_text()
player_quest = (core / 'src/server/game/Entities/Player/PlayerQuest.cpp').read_text()
quest_handler = (core / 'src/server/game/Handlers/QuestHandler.cpp').read_text()
accept = function(quest_handler, 'void WorldSession::HandleQuestgiverAcceptQuestOpcode(')
assert 'CanTakeQuest(quest, true)' in accept and 'AddQuestAndCheckCompletion(quest, object)' in accept
assert 'questGiver->ToGameObject()->AI()->QuestAccept(this, quest)' in player_quest
assert 'questGiver->ToCreature()->AI()->sQuestAccept(this, quest)' in player_quest
assert 'SMART_SCRIPT_TYPE_MASK_CREATURE + SMART_SCRIPT_TYPE_MASK_GAMEOBJECT' in smart_header.split(
    '{SMART_EVENT_ACCEPTED_QUEST,', 1)[1].split('}', 1)[0]
assert 'GetQuestStatus(qInfo->GetQuestId()) != QUEST_STATUS_NONE' in function(
    player_quest, 'bool Player::SatisfyQuestStatus(')
assert 'GetClosestCreatureWithEntry(object, ConditionValue1, static_cast<float>(ConditionValue2), !ConditionValue3)' in conditions
assert 'maxdist += GetObjectSize()' in function(
    (core / 'src/server/game/Entities/Object/Object.cpp').read_text(), 'bool WorldObject::_IsWithinDist(')

process = function(smart, 'void SmartScript::ProcessEvent(')
process_prefix = process[:process.index('    switch (e.GetEventType())')]
quest_case = function(process, '        case SMART_EVENT_ACCEPTED_QUEST:')
# The selected native branches are the ones supplied by these SQL rows.
process = (process_prefix + '    switch (e.GetEventType())\n    {\n'
           'case SMART_EVENT_LINK: ProcessAction(e,unit,var0,var1,bvar,spell,gob); break;\n'
           + quest_case + '\ncase SMART_EVENT_UPDATE: ProcessTimedAction(e,0,0); break;\n'
           'case SMART_EVENT_UPDATE_IC: case SMART_EVENT_UPDATE_OOC: ProcessTimedAction(e,0,0); break;\n'
           'default: break;\n    }\n}')
meet = function(conditions, 'bool Condition::Meets(')
meet_prefix = meet[:meet.index('    switch (ConditionType)')]
near_case = function(meet, '    case CONDITION_NEAR_CREATURE:')
meet_tail = meet[meet.index('    if (NegativeCondition)'):]
meet = meet_prefix + '    switch (ConditionType)\n    {\n' + near_case + '\n default: break;\n    }\n' + meet_tail

native_position = function(smart, '        case SMART_ACTION_SUMMON_CREATURE:')
native_position = native_position[native_position.index('            if (e.GetTargetType() != SMART_TARGET_POSITION)'):]
assert 'e.action.summonCreature.duration' in native_position
native_call = function(smart, '        case SMART_ACTION_CALL_TIMED_ACTIONLIST:')
native_loop = function(smart, 'void SmartScript::OnUpdate(')
native_loop = native_loop[native_loop.index('    bool needCleanup = true;'):native_loop.index('    if (!mRemIDs.empty())')]

parts = {
    'condition': meet,
    'conditionlookup': function(conditions, 'ConditionList ConditionMgr::GetConditionsForSmartEvent('),
    'conditionlist': function(conditions, 'bool ConditionMgr::IsObjectMeetToConditionList('),
    'conditions': function(conditions, 'bool ConditionMgr::IsObjectMeetToConditions(ConditionSourceInfo&'),
    'dispatch': function(smart, 'void SmartScript::ProcessEventsFor('),
    'event': process,
    'timed': function(smart, 'void SmartScript::ProcessTimedAction('),
    'setlist': function(smart, 'void SmartScript::SetScript9('),
    'init': function(smart, 'void SmartScript::InitTimer('),
    'recalc': function(smart, 'void SmartScript::RecalcTimer('),
    'update': function(smart, 'void SmartScript::UpdateTimer('),
    'loop': native_loop,
    'call': native_call,
    'summon': native_position,
    'npcaccept': function(smart_ai, 'void SmartAI::sQuestAccept('),
    'goaccept': function(smart_ai, 'bool SmartGameObjectAI::QuestAccept('),
    'npcreward': function(smart_ai, 'void SmartAI::sQuestReward('),
    'goreward': function(smart_ai, 'bool SmartGameObjectAI::QuestReward('),
    'queststatus': function(player_quest, 'bool Player::SatisfyQuestStatus('),
}
used = set(re.findall(r'\b(?:SMART_[A-Z_0-9]+|SMARTCAST_[A-Z_0-9]+)\b', ''.join(parts.values())))
used.discard('SMART_EVENT')
used.add('SMART_ACTION_SUMMON_CREATURE')
values = dict(re.findall(r'\b(SMART_[A-Z_0-9]+|SMARTCAST_[A-Z_0-9]+)\s*=\s*(0x[0-9a-fA-F]+|\d+)', smart_header))
parts['constants'] = '\n'.join(f'constexpr int {name}={values[name]};' for name in sorted(used))

prelude = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <map>
#include <memory>
#include <tuple>
#include <utility>
#include <vector>
using uint32=uint32_t; using int32=int32_t;
@@CONSTANTS@@
using SMART_EVENT=int;
using TempSummonType=int;
constexpr int MAX_CONDITION_TARGETS=3,CONDITION_NEAR_CREATURE=29;
constexpr int INVALIDREASON_QUEST_ALREADY_ON=1;
enum QuestStatus { QUEST_STATUS_NONE,QUEST_STATUS_COMPLETE,QUEST_STATUS_REWARDED };
#define ASSERT(x) assert(x)
#define LOG_ERROR(...) do {} while(0)
#define LOG_DEBUG(...) do {} while(0)
#define CAST_AI(type,ptr) static_cast<type*>(ptr)
uint32 urand(uint32 a,uint32 b) { assert(a==b); return a; }
struct SmartScript; struct SmartAI; struct SmartGameObjectAI;
struct Unit; struct Creature; struct Player; struct GameObject;
struct SpellInfo {};
struct AIBase { virtual ~AIBase()=default; virtual void AttackStart(Unit*){} };
struct WorldObject {
    uint32 entry=0,map=0,phase=1; float x=0,y=0,z=0; bool alive=true;
    virtual ~WorldObject()=default;
    virtual Creature* ToCreature(){return nullptr;}
    virtual GameObject* ToGameObject(){return nullptr;}
    virtual Unit* ToUnit(){return nullptr;}
    Creature* SummonCreature(uint32,float,float,float,float,int,uint32);
};
struct Unit:WorldObject { Unit* ToUnit() override {return this;} };
struct Creature:Unit {
    AIBase* ai=nullptr; Creature* ToCreature() override {return this;} AIBase* AI(){return ai;}
    Unit* GetVictim(){return nullptr;} bool IsEngaged(){return false;}
    bool IsActionPreventedByCasting(){return false;}
};
struct GameObject:WorldObject {
    AIBase* ai=nullptr; GameObject* ToGameObject() override {return this;} AIBase* AI(){return ai;}
};
struct Quest { uint32 id=100; uint32 GetQuestId() const {return id;} };
struct Player:Unit {
    QuestStatus state=QUEST_STATUS_NONE; bool eligible=true; int rewards=0;
    QuestStatus GetQuestStatus(uint32) const {return state;}
    void SendCanTakeQuestResponse(int) const {}
    bool SatisfyQuestStatus(Quest const*,bool) const;
};
@@QUESTSTATUS@@
bool IsCharmedCreature(Creature*) {return false;}
struct Spirit { Creature creature; uint32 remaining=0; };
std::vector<Spirit> spirits;
int created=0;
Creature* WorldObject::SummonCreature(uint32 id,float sx,float sy,float sz,float,int kind,uint32 duration) {
    assert(id==5895&&kind==3&&duration==180000);
    spirits.push_back({}); auto& spirit=spirits.back();
    spirit.creature.entry=id;spirit.creature.map=map;spirit.creature.phase=phase;
    spirit.creature.x=sx;spirit.creature.y=sy;spirit.creature.z=sz;spirit.remaining=duration;
    ++created;return &spirit.creature;
}
Creature* GetClosestCreatureWithEntry(WorldObject* origin,uint32 id,float range,bool alive) {
    for(auto& spirit:spirits) {
        auto& c=spirit.creature;
        float dx=c.x-origin->x,dy=c.y-origin->y,dz=c.z-origin->z;
        if(c.entry==id&&c.map==origin->map&&c.phase==origin->phase&&c.alive==alive
           &&dx*dx+dy*dy+dz*dz<=range*range)return &c;
    }
    return nullptr;
}
struct Condition;
struct ConditionSourceInfo {
    std::array<WorldObject*,3> mConditionTargets;
    Condition* mLastFailedCondition=nullptr;
    ConditionSourceInfo(WorldObject* a,WorldObject* b,WorldObject* c):mConditionTargets{a,b,c}{}
};
struct Condition {
    int32 SourceEntry=0; uint32 SourceType=22,SourceGroup=0,SourceId=9,ElseGroup=0,ReferenceId=0;
    int ConditionType=29; uint32 ConditionTarget=1,ConditionValue1=5895,ConditionValue2=100,ConditionValue3=0;
    bool NegativeCondition=true;
    bool isLoaded() const {return true;}
    bool Meets(ConditionSourceInfo&);
};
using ConditionList=std::vector<Condition*>;
using ConditionTypeContainer=std::map<uint32,ConditionList>;
using SmartEventConditionContainer=std::map<std::pair<int32,uint32>,ConditionTypeContainer>;
using ConditionReferenceContainer=std::map<uint32,ConditionList>;
struct ConditionMgr {
    SmartEventConditionContainer SmartEventConditionStore;
    ConditionReferenceContainer ConditionReferenceStore;
    std::vector<std::unique_ptr<Condition>> owned;
    ConditionList GetConditionsForSmartEvent(int32,uint32,uint32);
    bool IsObjectMeetToConditionList(ConditionSourceInfo&,ConditionList const&);
    bool IsObjectMeetToConditions(ConditionSourceInfo&,ConditionList const&);
} conditionMgr;
auto* sConditionMgr=&conditionMgr;
@@CONDITION@@
@@CONDITIONLOOKUP@@
@@CONDITIONLIST@@
@@CONDITIONS@@
struct SmartScriptHolder {
    static constexpr int DEFAULT_PRIORITY=0;
    int32 entryOrGuid=0; uint32 source_type=0,event_id=0; int priority=0;
    uint32 timer=0; bool active=true,runOnce=false,enableTimed=false;
    struct {
        int type=0; uint32 event_phase_mask=0,event_flags=0;
        struct {uint32 quest=0,cooldownMin=0,cooldownMax=0;} quest;
        struct {uint32 min=0,max=0,repeatMin=0,repeatMax=0;} minMaxRepeat;
        struct {uint32 firstTimer=0;} nearPlayer;
        struct {uint32 repeat=0;} distance;
        struct {uint32 timer=0;} nearUnit;
    } event;
    struct {
        int type=0;
        struct {uint32 id=0,timerType=0,allowOverride=0;} timedActionList;
        struct {uint32 creature=0,type=0,duration=0,flags=0,attackInvoker=0,attackScriptOwner=0;} summonCreature;
        struct {uint32 castFlags=0,flags=0;} cast,castCustom;
    } action;
    struct {int type=0;float x=0,y=0,z=0,o=0;} target;
    int GetEventType() const{return event.type;} int GetActionType()const{return action.type;}
    int GetTargetType()const{return target.type;} int GetScriptType()const{return source_type;}
};
using SmartAIEventList=std::vector<SmartScriptHolder>;
using SmartScriptFrame=std::tuple<SmartScriptHolder&,Unit*,uint32,uint32,bool,SpellInfo const*,GameObject*>;
struct SmartScriptMgr {
    std::map<std::pair<uint32,uint32>,SmartAIEventList> rows;
    SmartAIEventList GetScript(uint32 id,uint32 type) {return rows[{id,type}];}
} scriptMgr;
auto* sSmartScriptMgr=&scriptMgr;
struct SmartScript {
    WorldObject* base; Creature* me; Unit* invoker=nullptr;
    SmartAIEventList mEvents,mTimedActionList;
    std::vector<SmartScriptFrame> executionStack;
    bool isProcessingTimedActionList=false,mEventSortingRequired=false;
    explicit SmartScript(WorldObject* object,uint32 source):base(object),me(object->ToCreature()),
      mEvents(scriptMgr.GetScript(object->entry,source)){}
    WorldObject* GetBaseObject(){return base;} Unit* GetLastInvoker(){return invoker;}
    bool IsSmart(Creature*){return true;} bool IsSmart(GameObject*){return true;}
    bool IsInPhase(uint32){return true;}
    void RaisePriority(SmartScriptHolder&){}
    void ProcessEventsFor(SMART_EVENT,Unit* = nullptr,uint32=0,uint32=0,bool=false,SpellInfo const* = nullptr,GameObject* = nullptr);
    void ProcessEvent(SmartScriptHolder&,Unit* = nullptr,uint32=0,uint32=0,bool=false,SpellInfo const* = nullptr,GameObject* = nullptr);
    void ProcessAction(SmartScriptHolder&,Unit* = nullptr,uint32=0,uint32=0,bool=false,SpellInfo const* = nullptr,GameObject* = nullptr);
    void ProcessTimedAction(SmartScriptHolder&,uint32 const&,uint32 const&,Unit* = nullptr,uint32=0,uint32=0,bool=false,SpellInfo const* = nullptr,GameObject* = nullptr);
    void SetScript9(SmartScriptHolder&,uint32);
    void InitTimer(SmartScriptHolder&);
    void RecalcTimer(SmartScriptHolder&,uint32,uint32);
    void UpdateTimer(SmartScriptHolder&,uint32);
    void Tick(uint32 diff) {
        for(auto& e:mEvents)UpdateTimer(e,diff);
        @@LOOP@@
    }
};
struct SmartAI:AIBase {
    SmartScript* script; explicit SmartAI(SmartScript* p):script(p){}
    SmartScript* GetScript(){return script;}
    void sQuestAccept(Player*,Quest const*);void sQuestReward(Player*,Quest const*,uint32);
    void SetScript9(SmartScriptHolder& e,uint32 id,Unit*){script->SetScript9(e,id);}
    void AttackStart(Unit*) override {}
};
struct SmartGameObjectAI:AIBase {
    SmartScript* script;GameObject* me;SmartGameObjectAI(SmartScript* p,GameObject* g):script(p),me(g){}
    SmartScript* GetScript(){return script;}
    bool QuestAccept(Player*,Quest const*);bool QuestReward(Player*,Quest const*,uint32);
    void SetScript9(SmartScriptHolder& e,uint32 id,Unit*){script->SetScript9(e,id);}
};
@@NPCACCEPT@@
@@GOACCEPT@@
@@NPCREWARD@@
@@GOREWARD@@
@@DISPATCH@@
@@EVENT@@
@@TIMED@@
@@SETLIST@@
@@INIT@@
@@RECALC@@
@@UPDATE@@
void SmartScript::ProcessAction(SmartScriptHolder& e,Unit* unit,uint32,uint32,bool,SpellInfo const*,GameObject*) {
    e.runOnce=true;if(unit)invoker=unit;
    std::vector<WorldObject*> targets{base};
    WorldObject* summoner=GetBaseObject();
    switch(e.GetActionType()) {
        @@CALL@@
        case SMART_ACTION_SUMMON_CREATURE: {
            @@SUMMON@@
        default:break;
    }
}
void LoadData() {
    scriptMgr.rows.clear();conditionMgr.SmartEventConditionStore.clear();conditionMgr.owned.clear();
    spirits.clear();created=0;
    @@DATA@@
}
struct Scenario {
    GameObject brazier;Creature tiev;Player first,second;
    std::unique_ptr<SmartScript> goScript,npcScript;
    std::unique_ptr<SmartGameObjectAI> goAI;std::unique_ptr<SmartAI> npcAI;
    Scenario() {
        LoadData();brazier.entry=113791;brazier.x=419.041f;brazier.y=1843.15f;brazier.z=11.989f;
        tiev.entry=7007;tiev.x=430.385f;tiev.y=1881.86f;tiev.z=15.4168f;
        goScript=std::make_unique<SmartScript>(&brazier,1);npcScript=std::make_unique<SmartScript>(&tiev,0);
        goAI=std::make_unique<SmartGameObjectAI>(goScript.get(),&brazier);brazier.ai=goAI.get();
        npcAI=std::make_unique<SmartAI>(npcScript.get());tiev.ai=npcAI.get();
    }
    bool Accept(Player& player,bool npc=false) {
        Quest quest;
        if(!player.eligible||!player.SatisfyQuestStatus(&quest,false))return false;
        player.state=QUEST_STATUS_COMPLETE;
        if(npc)npcAI->sQuestAccept(&player,&quest);else goAI->QuestAccept(&player,&quest);
        return true;
    }
    bool Abandon(Player& player) {
        if(player.state==QUEST_STATUS_NONE||player.state==QUEST_STATUS_REWARDED)return false;
        player.state=QUEST_STATUS_NONE;return true;
    }
    void Tick(uint32 diff,bool npcFirst=false) {
        for(auto& spirit:spirits)if(spirit.creature.alive) {
            if(spirit.remaining<=diff){spirit.remaining=0;spirit.creature.alive=false;}
            else spirit.remaining-=diff;
        }
        if(npcFirst){npcScript->Tick(diff);goScript->Tick(diff);}
        else{goScript->Tick(diff);npcScript->Tick(diff);}
    }
};
int main() {
    {Scenario s;s.Tick(20000);assert(created==0&&s.first.state==QUEST_STATUS_NONE);}
    for(bool npc:{false,true}) {
        Scenario s;assert(s.Accept(s.first,npc));assert(created==0&&s.first.rewards==0);
        s.Tick(1);s.Tick(14000);assert(created==0);s.Tick(2000);assert(created==1);
    }
    for(bool order:{false,true}) {
        Scenario s;Quest previous{63};s.goAI->QuestReward(&s.first,&previous,0);
        assert(s.Accept(s.first,true));s.Tick(1,order);s.Tick(16000,order);
        assert(created==1);
        s.Tick(1000,order);s.Tick(200000,order);assert(created==1);
        for(int retry=0;retry<3;++retry) {
            assert(s.Abandon(s.first)&&s.Accept(s.first));s.Tick(1);s.Tick(16000);
            assert(created==retry+2&&s.first.rewards==0);
            s.Tick(200000);s.Tick(1000);
        }
    }
    {Scenario s;assert(s.Accept(s.first));s.Tick(1);s.Tick(1100);
     auto const timer=s.goScript->mTimedActionList.at(1).timer;
     assert(s.Accept(s.second));assert(s.goScript->mTimedActionList.at(1).timer==timer);
     s.Tick(16000);assert(created==1);}
    {Scenario s;s.first.eligible=false;assert(!s.Accept(s.first));s.Tick(20000);assert(created==0);}
    {Scenario s;s.first.state=QUEST_STATUS_REWARDED;assert(!s.Accept(s.first)&&!s.Abandon(s.first));
     s.Tick(20000);assert(created==0);}
    {Scenario s;Quest wrong{101};s.goAI->QuestAccept(&s.first,&wrong);s.npcAI->sQuestAccept(&s.first,&wrong);
     s.Tick(20000);assert(created==0);}
    {Scenario s;Quest recovery{1103};s.npcAI->sQuestReward(&s.first,&recovery,0);
     s.Tick(1);s.Tick(16000);assert(created==1);}
    std::cout<<"Shaman water spirit: native accepted quests, ordinary retries, timed summon and shared deduplication passed\n";
}
'''


def data_source(rows, condition_rows):
    text = []
    for row in rows:
        if int(row['id']) == 99:
            continue
        text.append('{SmartScriptHolder e;')
        for field, expression in (
                ('entryorguid', 'entryOrGuid'), ('source_type', 'source_type'), ('id', 'event_id'),
                ('event_type', 'event.type'), ('event_phase_mask', 'event.event_phase_mask'),
                ('event_flags', 'event.event_flags'), ('action_type', 'action.type'),
                ('action_param1', 'action.timedActionList.id'), ('action_param2', 'action.timedActionList.timerType'),
                ('action_param3', 'action.timedActionList.allowOverride'), ('target_type', 'target.type'),
                ('event_param1', 'event.quest.quest'), ('event_param2', 'event.quest.cooldownMin'),
                ('event_param3', 'event.quest.cooldownMax'), ('event_param1', 'event.minMaxRepeat.min'),
                ('event_param2', 'event.minMaxRepeat.max'), ('action_param1', 'action.summonCreature.creature'),
                ('action_param2', 'action.summonCreature.type'), ('action_param3', 'action.summonCreature.duration'),
                ('action_param4', 'action.summonCreature.attackInvoker'),
                ('action_param5', 'action.summonCreature.attackScriptOwner'),
                ('target_x', 'target.x'), ('target_y', 'target.y'), ('target_z', 'target.z'), ('target_o', 'target.o')):
            value = str(row[field])
            if field.startswith('target_') and field != 'target_type':
                value += 'f' if '.' in value else '.0f'
            text.append(f'e.{expression}={value};')
        text.append('scriptMgr.rows[{uint32(e.entryOrGuid),e.source_type}].push_back(e);}')
    for row in condition_rows:
        text.append('{auto c=std::make_unique<Condition>();')
        for column, field in (
                ('SourceEntry', 'SourceEntry'), ('SourceTypeOrReferenceId', 'SourceType'),
                ('SourceId', 'SourceId'), ('SourceGroup', 'SourceGroup'), ('ElseGroup', 'ElseGroup'),
                ('ConditionTypeOrReference', 'ConditionType'), ('ConditionTarget', 'ConditionTarget'),
                ('ConditionValue1', 'ConditionValue1'), ('ConditionValue2', 'ConditionValue2'),
                ('ConditionValue3', 'ConditionValue3'), ('NegativeCondition', 'NegativeCondition')):
            text.append(f'c->{field}={row[column]};')
        text.append('conditionMgr.SmartEventConditionStore[{c->SourceEntry,c->SourceId}][c->SourceGroup].push_back(c.get());'
                    'conditionMgr.owned.push_back(std::move(c));}')
    return '\n'.join(text)


def build(directory, rows, condition_rows, name):
    content = prelude
    for key, value in {**parts, 'data': data_source(rows, condition_rows)}.items():
        content = content.replace('@@' + key.upper() + '@@', value)
    path = directory / (name + '.cpp')
    path.write_text(content)
    binary = directory / name
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-missing-field-initializers',
                    *SANITIZER_FLAGS, str(path), '-o', str(binary)], check=True)
    return run_fixture([str(binary)])


mutations = (
    ('brazier acceptance restored', 'event', 113791, 'event_param1', 101),
    ('Tiev acceptance restored', 'event', 7007, 'event_param1', 101),
    ('brazier spawn deduplicated', 'remove', 11379100, '', 0),
    ('Tiev spawn deduplicated', 'remove', 700700, '', 0),
    ('base object used on timer ticks', 'condition', 11379100, 'ConditionTarget', 0),
    ('Tiev radius reaches the spirit', 'condition', 700700, 'ConditionValue2', 50),
    ('living spirit checked', 'condition', 700700, 'ConditionValue3', 1),
    ('absent spirit required', 'condition', 11379100, 'NegativeCondition', 0),
    ('timed-list source checked', 'condition', 11379100, 'SourceId', 1),
    ('event id plus one checked', 'condition', 700700, 'SourceGroup', 1),
    ('ordinary acceptance can restart', 'event', 113791, 'event_flags', 1),
)

with tempfile.TemporaryDirectory(prefix='portable-shaman-water-') as temporary:
    directory = Path(temporary)
    result = build(directory, events, guards, 'water')
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit('Shaman water spirit fixture failed')

    def rejected(numbered):
        number, (_label, kind, entry, field, value) = numbered
        rows, condition_rows = [dict(row) for row in events], [dict(row) for row in guards]
        if kind == 'event':
            for row in rows:
                if int(row['entryorguid']) == entry and int(row['id']) == 1:
                    row[field] = value
        elif kind == 'remove':
            condition_rows = [row for row in condition_rows if int(row['SourceEntry']) != entry]
        else:
            for row in condition_rows:
                if int(row['SourceEntry']) == entry:
                    row[field] = value
        return build(directory, rows, condition_rows, f'mutant-{number}').returncode != 0

    for (label, *_), killed in zip(mutations, in_parallel(rejected, enumerate(mutations))):
        if not killed:
            raise SystemExit('Shaman water mutation survived: ' + label)
        print('Shaman water mutation rejected: ' + label)
