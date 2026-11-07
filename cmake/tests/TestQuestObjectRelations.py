"""Exercise native quest-role producers, spawn maps and active-role consumers."""

import argparse
from pathlib import Path
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    cxx,
    function,
    prepared_core,
    reject_part_mutants,
    run_fixture,
    source_argument,
    sql_rows,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help='Playerbots src directory')
args = parser.parse_args()
core = prepared_core()
module = args.source or core / 'modules/mod-playerbots/src'
source = (module / 'Ai/Base/Value/QuestValues.cpp').read_text()
header = (module / 'Ai/Base/Value/QuestValues.h').read_text()
loot = (module / 'Ai/Base/Value/LootValues.cpp').read_text()
travel = (module / 'Mgr/Travel/TravelMgr.cpp').read_text()

# Native quests have four creature or object slots and six item slots; the
# shared relation map gives each item slot its own bit below the quest roles.
quest_def = (core / 'src/server/game/Quests/QuestDef.h').read_text()
assert '#define QUEST_OBJECTIVES_COUNT 4' in quest_def and '#define QUEST_ITEM_OBJECTIVES_COUNT 6' in quest_def
assert 'uint32 RequiredItemId[QUEST_ITEM_OBJECTIVES_COUNT];' in quest_def
assert 'int32  RequiredNpcOrGo[QUEST_OBJECTIVES_COUNT];' in quest_def
assert 'uint16 ItemCount[QUEST_ITEM_OBJECTIVES_COUNT];' in quest_def
assert 'static_assert(uint32(QuestRelationFlag::questGiver) == 1u << QUEST_ITEM_OBJECTIVES_COUNT);' in source

# Native ObjectMgr's involved maps are loaded from ender tables, not starters.
object_mgr = (core / 'src/server/game/Globals/ObjectMgr.cpp').read_text()
for kind, prefix in (('Gameobject', '_go'), ('Creature', '_creature')):
    assert f'LoadQuestRelationsHelper({prefix}QuestRelations,' in function(
        object_mgr, f'void ObjectMgr::Load{kind}QuestStarters()')
    assert f'LoadQuestRelationsHelper({prefix}QuestInvolvedRelations,' in function(
        object_mgr, f'void ObjectMgr::Load{kind}QuestEnders()')
enders = sql_rows(core, 'gameobject_questender', {61934, 113791})
starters = sql_rows(core, 'gameobject_queststarter', {61934, 113791})
assert {(int(row['id']), int(row['quest'])) for row in enders} == {(61934, 1526), (113791, 63)}
assert {(int(row['id']), int(row['quest'])) for row in starters} == {(61934, 1527), (113791, 100)}
drop_source = function(loot, 'DropMap* DropMapValue::Calculate()')
assert 'dropMap->insert(std::make_pair(lItem->itemid, sEntry))' in drop_source
assert 'dropMap->insert(std::make_pair(lItem->itemid, -sEntry))' in drop_source

production = {
    'types': header[header.index('enum class QuestRelationFlag'):header.index('// Returns the quest relation')],
    'relations': function(source, 'entryQuestRelationMap EntryQuestRelationMapValue::Calculate()'),
    'getentries': function(source, 'void FindQuestObjectData::GetObjectiveEntries()'),
    'spawnentries': function(source, 'static std::array<uint32, 3> SpawnEntries('),
    'creature': function(source, 'void FindQuestObjectData::operator()(CreatureData const& creData)'),
    'gameobject': function(source, 'void FindQuestObjectData::operator()(GameObjectData const& goData)'),
    'guidmap': function(source, 'questGuidpMap QuestGuidpMapValue::Calculate()'),
    'takers': function(source, 'std::vector<GuidPosition> ActiveQuestTakersValue::Calculate()'),
    'objectives': function(source, 'std::vector<GuidPosition> ActiveQuestObjectivesValue::Calculate()'),
    'dropentries': function(loot, 'std::vector<int32> ItemDropListValue::Calculate()'),
    'creatureposition': function(travel, 'GuidPosition::GuidPosition(CreatureData const& creData)'),
    'goposition': function(travel, 'GuidPosition::GuidPosition(GameObjectData const& goData)'),
    'accessible': function(travel, 'bool GuidPosition::IsCreatureOrGOAccessible()'),
    'travelquests': function(travel, 'for (auto& q : questMap)'),
    'nativego': '\n'.join(
        f'objectMgr.go{kind}.emplace({row["id"]},{row["quest"]});'
        for kind, rows in (('Starts', starters), ('Ends', enders)) for row in rows),
}

prelude = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <map>
#include <string>
#include <type_traits>
#include <unordered_map>
#include <vector>
using uint32=uint32_t; using int32=int32_t;
constexpr uint32 QUEST_OBJECTIVES_COUNT=4,QUEST_ITEM_OBJECTIVES_COUNT=6;
constexpr uint32 SECOND=1,MINUTE=SECOND*60,IN_MILLISECONDS=1000;
constexpr int REP_FRIENDLY=4;
enum QuestStatus { QUEST_STATUS_NONE, QUEST_STATUS_INCOMPLETE, QUEST_STATUS_COMPLETE, QUEST_STATUS_REWARDED };
enum class HighGuid { Unit, GameObject };
struct CreatureData { uint32 id=0,id2=0,id3=0,spawnId=0,mapid=0; float posX=0,posY=0,posZ=0,orientation=0; };
struct GameObjectData { uint32 id=0,spawnId=0,mapid=0; float posX=0,posY=0,posZ=0,orientation=0; };
struct Creature { bool inWorld=true,alive=true; bool IsInWorld() const { return inWorld; } bool IsAlive() const { return alive; } };
struct GameObject { bool inWorld=true; bool IsInWorld() const { return inWorld; } };
struct Map { bool loaded=true; bool IsGridLoaded(float,float) const { return loaded; } };
std::map<uint32,Map> maps;
std::map<uint32,Creature> creatures;
std::map<uint32,GameObject> objects;
struct ObjectGuid {
    HighGuid kind; uint32 entry,spawn;
    ObjectGuid(HighGuid kind,uint32 entry,uint32 spawn):kind(kind),entry(entry),spawn(spawn){}
    bool IsCreature() const { return kind==HighGuid::Unit; }
    bool IsGameObject() const { return kind==HighGuid::GameObject; }
};
struct WorldPosition {
    uint32 map; float x,y,z,o;
    WorldPosition(uint32 map,float x,float y,float z,float o):map(map),x(x),y(y),z(z),o(o){}
    Map* getMap() { auto it=maps.find(map); return it==maps.end()?nullptr:&it->second; }
    float GetPositionX() const { return x; } float GetPositionY() const { return y; }
};
struct GuidPosition:ObjectGuid,WorldPosition {
    bool loadedFromDB=false;
    explicit GuidPosition(CreatureData const&);
    explicit GuidPosition(GameObjectData const&);
    Creature* GetCreature() { auto it=creatures.find(spawn); return it==creatures.end()?nullptr:&it->second; }
    GameObject* GetGameObject() { auto it=objects.find(spawn); return it==objects.end()?nullptr:&it->second; }
    bool IsCreatureOrGOAccessible();
};
@@CREATUREPOSITION@@
@@GOPOSITION@@
@@ACCESSIBLE@@
@@TYPES@@
struct Quest {
    uint32 id=0; bool autoComplete=false;
    std::array<int32,4> RequiredNpcOrGo{};
    std::array<uint32,QUEST_OBJECTIVES_COUNT> RequiredNpcOrGoCount{};
    std::array<uint32,QUEST_ITEM_OBJECTIVES_COUNT> RequiredItemId{},RequiredItemCount{};
    bool IsAutoComplete() const { return autoComplete; }
};
struct QuestStatusData {
    QuestStatus Status=QUEST_STATUS_NONE;
    std::array<uint32,QUEST_ITEM_OBJECTIVES_COUNT> ItemCount{};
    std::array<uint32,QUEST_OBJECTIVES_COUNT> CreatureOrGOCount{};
};
using QuestStatusMap=std::map<uint32,QuestStatusData>;
struct CreatureTemplate { uint32 faction=35; };
struct FactionTemplate {};
struct FactionTemplateStore {
    FactionTemplate entry;
    FactionTemplate const* LookupEntry(uint32) const { return &entry; }
} sFactionTemplateStore;
struct ObjectMgr {
    using QuestMap=std::unordered_map<uint32,Quest*>;
    QuestMap quests;
    std::multimap<uint32,uint32> npcStarts,npcEnds,goStarts,goEnds;
    std::unordered_map<uint32,CreatureData> creatureSpawns;
    std::unordered_map<uint32,GameObjectData> objectSpawns;
    CreatureTemplate creatureTemplate;
    auto const* GetCreatureQuestRelationMap() const { return &npcStarts; }
    auto const* GetCreatureQuestInvolvedRelationMap() const { return &npcEnds; }
    auto const* GetGOQuestRelationMap() const { return &goStarts; }
    auto const* GetGOQuestInvolvedRelationMap() const { return &goEnds; }
    QuestMap const& GetQuestTemplates() const { return quests; }
    auto const& GetAllCreatureData() const { return creatureSpawns; }
    auto const& GetAllGOData() const { return objectSpawns; }
    Quest const* GetQuestTemplate(uint32 id) const { auto it=quests.find(id); return it==quests.end()?nullptr:it->second; }
    CreatureTemplate const* GetCreatureTemplate(uint32) const { return &creatureTemplate; }
} objectMgr;
auto* sObjectMgr=&objectMgr;
struct Player {
    QuestStatusMap quests; int reaction=REP_FRIENDLY; bool canTake=true;
    FactionTemplate faction;
    QuestStatusMap& getQuestStatusMap() { return quests; }
    bool GetQuestRewardStatus(uint32 id) const { return quests.at(id).Status==QUEST_STATUS_REWARDED; }
    bool CanTakeQuest(Quest const*,bool) const { return canTake; }
    FactionTemplate const* GetFactionTemplateEntry() const { return &faction; }
    int GetFactionReactionTo(FactionTemplate const*,FactionTemplate const*) const { return reaction; }
};
entryQuestRelationMap globalEntries;
questGuidpMap globalPositions;
using DropMap=std::multimap<uint32,int32>;
DropMap globalDrops;
template<class T> T GlobalValue(std::string const&) {
    if constexpr(std::is_same_v<T,entryQuestRelationMap>) return globalEntries;
    else if constexpr(std::is_same_v<T,questGuidpMap>) return globalPositions;
    else return &globalDrops;
}
#define GAI_VALUE(type,name) GlobalValue<type>(name)
struct ItemDropListValue {
    std::string qualifier;
    explicit ItemDropListValue(std::string value):qualifier(value){}
    std::string getQualifier() const { return qualifier; }
    std::vector<int32> Calculate();
};
using std::stoi;
@@DROPENTRIES@@
#define GAI_VALUE2(type,name,qualifier) ItemDropListValue(std::to_string(qualifier)).Calculate()
struct EntryQuestRelationMapValue { entryQuestRelationMap Calculate(); };
class FindQuestObjectData {
public:
    FindQuestObjectData() { GetObjectiveEntries(); }
    void GetObjectiveEntries();
    void operator()(CreatureData const&);
    void operator()(GameObjectData const&);
    questGuidpMap GetResult() const { return data; }
private:
    entryQuestRelationMap relationMap;
    questGuidpMap data;
};
struct QuestGuidpMapValue { questGuidpMap Calculate(); };
struct ActiveQuestTakersValue { Player* bot; std::vector<GuidPosition> Calculate(); };
struct ActiveQuestObjectivesValue { Player* bot; std::vector<GuidPosition> Calculate(); };
@@RELATIONS@@
@@GETENTRIES@@
@@SPAWNENTRIES@@
@@CREATURE@@
@@GAMEOBJECT@@
@@GUIDMAP@@
@@TAKERS@@
@@OBJECTIVES@@
struct { float TooCloseDistance=5.0f,SightDistance=75.0f; } sPlayerbotAIConfig;
struct QuestTravelDestination {
    uint32 questId; int32 entry; uint32 points=0;
    QuestTravelDestination(uint32 questId,int32 entry):questId(questId),entry(entry){}
    virtual ~QuestTravelDestination()=default;
    void addPoint(WorldPosition*) { ++points; }
    void setExpireDelay(uint32) {}
    void setMaxVisitors(uint32,uint32) {}
};
struct QuestRelationTravelDestination:QuestTravelDestination {
    uint32 relation;
    QuestRelationTravelDestination(uint32 quest,int32 entry,uint32 relation,float,float)
        :QuestTravelDestination(quest,entry),relation(relation){}
};
struct QuestObjectiveTravelDestination:QuestTravelDestination {
    uint32 objective;
    QuestObjectiveTravelDestination(uint32 quest,int32 entry,uint32 objective,float,float)
        :QuestTravelDestination(quest,entry),objective(objective){}
};
struct QuestContainer { std::vector<QuestTravelDestination*> questGivers,questTakers,questObjectives; };
// The quest part of TravelMgr::LoadQuestTravelTable.
struct TravelQuests {
    std::map<uint32,QuestContainer*> quests;
    std::vector<QuestTravelDestination*> questGivers;
    void Load(questGuidpMap questMap) {
@@TRAVELQUESTS@@
    }
    ~TravelQuests() {
        for (auto& [quest,container]:quests) {
            for (auto* list:{&container->questGivers,&container->questTakers,&container->questObjectives})
                for (auto* destination:*list) delete destination;
            delete container;
        }
    }
};
'''

tests = r'''
uint32 Count(std::vector<GuidPosition> const& positions,HighGuid kind,uint32 spawn) {
    return std::count_if(positions.begin(),positions.end(),[&](auto const& p){return p.kind==kind&&p.spawn==spawn;});
}
void Rebuild() {
    globalEntries=EntryQuestRelationMapValue().Calculate();
    globalPositions=QuestGuidpMapValue().Calculate();
}
int main() {
    constexpr uint32 GIVER=uint32(QuestRelationFlag::questGiver),TAKER=uint32(QuestRelationFlag::questTaker);
    constexpr uint32 FIFTH=uint32(QuestRelationFlag::objective5),SIXTH=uint32(QuestRelationFlag::objective6);
    // Item slots 5 and 6 continue the objective bits; the quest roles follow them.
    assert(FIFTH==1u<<4&&SIXTH==1u<<5&&GIVER==1u<<QUEST_ITEM_OBJECTIVES_COUNT&&TAKER==GIVER<<1);
    maps[0]={}; maps[1]={};
    Quest fire{1526},nextFire{1527},water{63},nextWater{100};
    Quest combined{90001},kill{90002},items{90003},late{90004};
    for(auto* q:{&fire,&nextFire,&water,&nextWater,&combined,&kill,&items,&late}) objectMgr.quests.emplace(q->id,q);
    @@NATIVEGO@@
    objectMgr.objectSpawns[101]={61934,101,0,10,20,30,1};
    objectMgr.objectSpawns[102]={113791,102,0,40,50,60,2};
    objectMgr.objectSpawns[103]={2000,103,1,70,80,90,3};
    objectMgr.creatureSpawns[201]={1000,1001,0,201,1,11,22,33,4};
    for(uint32 spawn:{101u,102u,103u}) objects[spawn]={};
    creatures[201]={};
    objectMgr.npcStarts.emplace(1000,combined.id); objectMgr.npcEnds.emplace(1000,combined.id);
    objectMgr.goStarts.emplace(2000,combined.id); objectMgr.goEnds.emplace(2000,combined.id);
    combined.RequiredNpcOrGo[0]=1000; combined.RequiredNpcOrGoCount[0]=1;
    combined.RequiredNpcOrGo[1]=-2000; combined.RequiredNpcOrGoCount[1]=1;
    kill.RequiredNpcOrGo[0]=1001; kill.RequiredNpcOrGoCount[0]=1;
    items.RequiredItemId[0]=5000; items.RequiredItemCount[0]=2;
    items.RequiredItemId[1]=5001; items.RequiredItemCount[1]=1;
    globalDrops.emplace(5000,1000); globalDrops.emplace(5000,-2000); globalDrops.emplace(5001,1000);
    // Only item slots 5 and 6 of this quest have sources; their givers and takers stay apart.
    objectMgr.npcStarts.emplace(1000,late.id);
    late.RequiredItemId[4]=5002; late.RequiredItemCount[4]=1; late.RequiredItemId[5]=5003; late.RequiredItemCount[5]=3;
    globalDrops.emplace(5002,1001); globalDrops.emplace(5003,-2000);
    Rebuild();
    assert(globalEntries[-61934][1526]==TAKER&&globalEntries[-61934][1527]==GIVER);
    assert(globalEntries[-113791][63]==TAKER&&globalEntries[-113791][100]==GIVER);
    assert(!globalEntries.contains(61934)&&!globalEntries.contains(113791));
    assert(globalEntries[1000][combined.id]==(GIVER|TAKER|1));
    assert(globalEntries[-2000][combined.id]==(GIVER|TAKER|2));
    assert(globalEntries[1000][items.id]==(1|2)&&globalEntries[-2000][items.id]==1);
    assert(globalEntries[1000][late.id]==GIVER&&globalEntries[1001][late.id]==FIFTH&&globalEntries[-2000][late.id]==SIXTH);
    assert(globalPositions.at(late.id).at(SIXTH).at(-2000).front().spawn==103);
    auto const& firePos=globalPositions.at(1526).at(TAKER).at(-61934).front();
    assert(firePos.kind==HighGuid::GameObject&&firePos.entry==61934&&firePos.spawn==101);
    assert(firePos.loadedFromDB&&firePos.map==0&&firePos.x==10&&firePos.z==30);
    auto const& alternate=globalPositions.at(kill.id).at(1).at(1001).front();
    assert(alternate.kind==HighGuid::Unit&&alternate.entry==1000&&alternate.spawn==201&&alternate.map==1);
    Player player;
    ActiveQuestTakersValue takers{&player}; ActiveQuestObjectivesValue objectives{&player};
    player.quests[1526].Status=QUEST_STATUS_COMPLETE; player.quests[63].Status=QUEST_STATUS_COMPLETE;
    player.quests[combined.id].Status=QUEST_STATUS_COMPLETE; player.quests[late.id].Status=QUEST_STATUS_COMPLETE;
    auto targets=takers.Calculate();
    assert(targets.size()==4&&Count(targets,HighGuid::GameObject,101)==1&&Count(targets,HighGuid::GameObject,102)==1);
    assert(Count(targets,HighGuid::GameObject,103)==1&&Count(targets,HighGuid::Unit,201)==1);
    player.quests[1526].Status=QUEST_STATUS_REWARDED; player.quests[63].Status=QUEST_STATUS_INCOMPLETE;
    targets=takers.Calculate(); assert(targets.size()==2);
    player.reaction=REP_FRIENDLY-1; targets=takers.Calculate();
    assert(targets.size()==1&&Count(targets,HighGuid::GameObject,103)==1);
    objects[103].inWorld=false; assert(takers.Calculate().empty()); objects[103].inWorld=true;
    player.reaction=REP_FRIENDLY; player.quests.clear(); player.quests[combined.id].Status=QUEST_STATUS_INCOMPLETE;
    auto goals=objectives.Calculate(); assert(goals.size()==2&&Count(goals,HighGuid::Unit,201)==1&&Count(goals,HighGuid::GameObject,103)==1);
    player.quests[combined.id].CreatureOrGOCount[0]=1; goals=objectives.Calculate();
    assert(goals.size()==1&&Count(goals,HighGuid::GameObject,103)==1);
    player.quests[combined.id].CreatureOrGOCount[1]=1; assert(objectives.Calculate().empty());
    player.quests.clear(); player.quests[items.id].Status=QUEST_STATUS_INCOMPLETE;
    goals=objectives.Calculate(); assert(goals.size()==3&&Count(goals,HighGuid::Unit,201)==2&&Count(goals,HighGuid::GameObject,103)==1);
    player.quests[items.id].ItemCount[0]=2; goals=objectives.Calculate();
    assert(goals.size()==1&&Count(goals,HighGuid::Unit,201)==1);
    player.quests[items.id].ItemCount[1]=1; assert(objectives.Calculate().empty());
    player.quests[items.id].ItemCount={}; creatures[201].alive=false; goals=objectives.Calculate();
    assert(goals.size()==1&&Count(goals,HighGuid::GameObject,103)==1);
    maps[1].loaded=false; assert(objectives.Calculate().empty()); maps[1].loaded=true;
    player.quests[items.id].Status=QUEST_STATUS_COMPLETE; assert(objectives.Calculate().empty());

    // Travel destinations: a giver alone is no objective, and the four creature and
    // object slots exclude item slots 5 and 6.
    GuidPosition const at(objectMgr.creatureSpawns.at(201));
    questGuidpMap travelMap;
    travelMap[late.id][GIVER][1000]={at,at};
    travelMap[late.id][TAKER][1002]={at};
    travelMap[late.id][GIVER|1][1001]={at};
    travelMap[late.id][4][-2000]={at};
    travelMap[late.id][FIFTH][1003]={at};
    travelMap[late.id][SIXTH][1004]={at};
    {
        TravelQuests travel; travel.Load(travelMap);
        assert(travel.quests.size()==1&&travel.questGivers.size()==2);
        QuestContainer const& container=*travel.quests.at(late.id);
        assert(container.questGivers.size()==2&&container.questTakers.size()==1&&container.questObjectives.size()==2);
        auto const relation=[](QuestTravelDestination* d){return static_cast<QuestRelationTravelDestination*>(d);};
        auto const objective=[](QuestTravelDestination* d){return static_cast<QuestObjectiveTravelDestination*>(d);};
        assert(relation(container.questTakers[0])->entry==1002&&relation(container.questTakers[0])->relation==1);
        for (auto* giver:container.questGivers)
            assert((giver->entry==1000&&giver->points==2)||(giver->entry==1001&&giver->points==1));
        for (auto* goal:container.questObjectives)
            assert((goal->entry==1001&&objective(goal)->objective==0)||(goal->entry==-2000&&objective(goal)->objective==2));
    }
    std::cout<<"Quest object relations: native Shaman GO endings, combined roles, objectives, item slots 5 and 6, "
               "spawn aliases, travel destinations and active consumers passed\n";
}
'''

mutations = (
    ('GO ender role', 'relations',
     ('for (auto relation : *sObjectMgr->GetGOQuestInvolvedRelationMap())\n'
      '        rMap[-(int32)relation.first][relation.second] |= (int)QuestRelationFlag::questTaker;'),
     ('for (auto relation : *sObjectMgr->GetGOQuestInvolvedRelationMap())\n'
      '        rMap[-(int32)relation.first][relation.second] |= (int)QuestRelationFlag::questGiver;')),
    ('GO role entry sign', 'relations', 'rMap[-(int32)relation.first]', 'rMap[(int32)relation.first]'),
    ('combined taker roles', 'takers', 'relation.first & (uint32)QuestRelationFlag::questTaker',
     'relation.first == (uint32)QuestRelationFlag::questTaker'),
    ('combined objective roles', 'objectives', 'relation.first & (1u << objective)',
     'relation.first == (1u << objective)'),
    ('GO spawn entry sign', 'gameobject', 'goData.id * -1', 'goData.id'),
    ('alternate creature spawn entry', 'creature', 'data[questId][flag][entry]', 'data[questId][flag][creData.id]'),
    ('remaining kill credit', 'objectives', 'hasCount >= reqCount', 'hasCount > reqCount'),
    ('completed objective exclusion', 'objectives', 'statusData.Status != QUEST_STATUS_INCOMPLETE', 'false'),
    ('accessible quest giver', 'takers', '!guidp.IsCreatureOrGOAccessible()', 'false'),
    ('accessible quest target', 'objectives', '!guidp.IsCreatureOrGOAccessible()', 'false'),
    ('item objective slots 5 and 6', 'relations', 'objective < QUEST_ITEM_OBJECTIVES_COUNT;',
     'objective < QUEST_OBJECTIVES_COUNT;'),
    ('item objectives sharing the quest role bits', 'types', 'questGiver = 64,\n    questTaker = 128,',
     'questGiver = 16,\n    questTaker = 32,'),
    ('quest giver as travel objective', 'travelquests', '(uint32)QuestRelationFlag::objective4))',
     '(uint32)QuestRelationFlag::objective4 | (uint32)QuestRelationFlag::questGiver))'),
    ('item objective 5 as travel objective', 'travelquests', '(uint32)QuestRelationFlag::objective4))',
     '(uint32)QuestRelationFlag::objective4 | (uint32)QuestRelationFlag::objective5))'),
)


def build(directory, parts, name):
    text = prelude + tests
    for key, value in parts.items():
        text = text.replace('@@' + key.upper() + '@@', value)
    path = directory / (name + '.cpp')
    path.write_text(text)
    binary = directory / name
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror',
                    '-Wno-missing-field-initializers', *SANITIZER_FLAGS, str(path), '-o', str(binary)], check=True)
    return run_fixture([str(binary)])


with tempfile.TemporaryDirectory(prefix='portable-quest-objects-') as temporary:
    directory = Path(temporary)
    result = build(directory, production, 'quest-objects')
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit('Quest object relation fixture failed')

    reject_part_mutants(production, mutations, lambda parts, tag: build(directory, parts, tag),
                        'Quest object relation')
