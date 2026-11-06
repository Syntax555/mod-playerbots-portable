"""Exercise natural quest grinding of gray mobs without relaxing target checks."""

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
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help='Playerbots src directory')
args = parser.parse_args()
core = prepared_core()
module = args.source or core / 'modules/mod-playerbots/src'
source = (module / 'Ai/Base/Value/GrindTargetValue.cpp').read_text()
production = {
    'find': function(source, 'Unit* GrindTargetValue::FindTargetForGrinding('),
    'needed': function(source, 'bool GrindTargetValue::needForQuest('),
}

# The loot adapter uses the core's own lookup and the same quest-item producer:
# native loot templates ask whether this player still needs their item.
loot = (core / 'src/server/game/Loot/LootMgr.cpp').read_text()
production['loot'] = function(loot, 'bool LootStore::HaveQuestLootForPlayer(')
native_drop = function(loot, 'bool LootTemplate::HasQuestDropForPlayer(')
assert 'player->HasQuestForItem(item->itemid)' in native_drop
native_items = function((core / 'src/server/game/Entities/Player/PlayerQuest.cpp').read_text(),
                        'bool Player::HasQuestForItem(')
assert 'QUEST_STATUS_INCOMPLETE' in native_items
assert 'itemid == qinfo->RequiredItemId[j] && q_status.ItemCount[j] < qinfo->RequiredItemCount[j]' in native_items

prelude = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <map>
#include <string>
#include <unordered_map>
#include <vector>
using uint32=uint32_t; using int32=int32_t;
constexpr int REP_NEUTRAL=4, UNIT_NPC_FLAG_NONE=0, CREATURE_ELITE_NORMAL=0, QUEST_OBJECTIVES_COUNT=4;
constexpr float INTERACTION_DISTANCE=5.0f;
constexpr int RPG_IDLE=0, RPG_WANDER_RANDOM=1, RPG_DO_QUEST=2;
namespace BotState { constexpr int BOT_STATE_NON_COMBAT=0; }
enum QuestStatus { QUEST_STATUS_NONE, QUEST_STATUS_INCOMPLETE, QUEST_STATUS_COMPLETE, QUEST_STATUS_REWARDED };
struct ObjectGuid { uint32 id=0; bool player=false; bool IsPlayer() const { return player; } };
using GuidVector=std::vector<ObjectGuid>;
struct Player; struct Creature; struct PlayerbotAI;
struct CreatureTemplate { uint32 lootid=0,rank=0; };
struct Unit {
    virtual ~Unit()=default;
    uint32 entry=100,level=10,flags=0; float x=10,z=0;
    bool alive=true,inWorld=true,removing=false,xp=false,hostile=true,los=true;
    ObjectGuid guid{1};
    virtual Creature* ToCreature() { return nullptr; }
    bool IsAlive() const { return alive; }
    bool IsInWorld() const { return inWorld; }
    bool IsDuringRemoveFromWorld() const { return removing; }
    uint32 GetEntry() const { return entry; }
    uint32 GetLevel() const { return level; }
    uint32 GetNpcFlags() const { return flags; }
    float GetPositionZ() const { return z; }
    ObjectGuid GetGUID() const { return guid; }
};
struct Creature:Unit {
    CreatureTemplate data; float aggro=5;
    Creature* ToCreature() override { return this; }
    CreatureTemplate const* GetCreatureTemplate() const { return &data; }
    float GetAggroRange(Player*) const { return aggro; }
};
struct Quest {
    uint32 id=1473,level=10;
    std::array<int32,4> RequiredNpcOrGo{};
    std::array<uint32,4> RequiredNpcOrGoCount{},RequiredItemId{},RequiredItemCount{};
    uint32 GetQuestId() const { return id; }
    uint32 GetQuestLevel() const { return level; }
};
struct QuestStatusData {
    QuestStatus status=QUEST_STATUS_INCOMPLETE;
    std::array<uint32,4> CreatureOrGOCount{},ItemCount{};
};
using QuestStatusMap=std::map<uint32,QuestStatusData>;
struct Group {
    struct Slot { ObjectGuid guid; };
    using MemberSlotList=std::vector<Slot>; using member_citerator=MemberSlotList::const_iterator;
    MemberSlotList members;
    MemberSlotList const& GetMemberSlots() const { return members; }
};
struct Player:Unit {
    PlayerbotAI* ai=nullptr; Group* group=nullptr;
    QuestStatusMap quests;
    bool bg=false,teleport=false;
    Player() { level=30; }
    Group* GetGroup() const { return group; }
    uint32 GetMapId() const { return 0; }
    bool IsBeingTeleported() const { return teleport; }
    int GetReactionTo(Unit* u) const { return u->hostile?1:REP_NEUTRAL; }
    bool IsHostileTo(Unit* u) const { return u->hostile; }
    bool isHonorOrXPTarget(Unit* u) const { return u->xp; }
    bool InBattleground() const { return bg; }
    bool IsWithinLOSInMap(Unit* u) const { return u->los; }
    float GetDistance(Unit* u) const { return std::abs(x-u->x); }
    QuestStatusMap& getQuestStatusMap() { return quests; }
    QuestStatus GetQuestStatus(uint32 id) const {
        auto it=quests.find(id); return it==quests.end()?QUEST_STATUS_NONE:it->second.status;
    }
    bool HasQuestForItem(uint32) const;
};
struct ObjectMgr {
    std::map<uint32,Quest> quests; std::map<uint32,CreatureTemplate> creatures;
    Quest const* GetQuestTemplate(uint32 id) const {
        auto it=quests.find(id); return it==quests.end()?nullptr:&it->second;
    }
    CreatureTemplate const* GetCreatureTemplate(uint32 id) const {
        auto it=creatures.find(id); return it==creatures.end()?nullptr:&it->second;
    }
} objectMgr;
auto* sObjectMgr=&objectMgr;
bool Player::HasQuestForItem(uint32 item) const {
    for(auto const& [id,status]:quests) if(status.status==QUEST_STATUS_INCOMPLETE) {
        auto const* quest=objectMgr.GetQuestTemplate(id); if(!quest) continue;
        for(uint32 i=0;i<4;++i) if(quest->RequiredItemId[i]==item) {
            if(status.ItemCount[i]<quest->RequiredItemCount[i]) return true;
        }
    }
    return false;
}
struct LootTemplate;
using LootTemplateMap=std::map<uint32,LootTemplate const*>;
struct LootTemplate {
    uint32 item=0;
    bool HasQuestDropForPlayer(LootTemplateMap const&,Player const* p) const { return p->HasQuestForItem(item); }
};
struct LootStore {
    LootTemplateMap m_LootTemplates;
    bool HaveQuestLootForPlayer(uint32,Player const*) const;
} LootTemplates_Creature;
template<class T> struct Value {
    T value{}; T Get() const { return value; } operator T() const { return value; }
};
struct Context {
    Value<GuidVector> attackers,targets;
    template<class T> Value<T>* GetValue(std::string const& name) { return name=="attackers"?&attackers:&targets; }
};
struct NewRpgInfo { int status=RPG_DO_QUEST; int GetStatus() const { return status; } };
struct PlayerbotAI {
    Player* bot; Player* master=nullptr; Context context; NewRpgInfo rpgInfo;
    bool elite=false,follow=false;
    std::map<uint32,Unit*> units;
    Unit* GetUnit(ObjectGuid g) const { auto it=units.find(g.id); return it==units.end()?nullptr:it->second; }
    bool HasStrategy(std::string const& name,int) const { return name=="follow"&&follow; }
    void TellMaster(std::string const&) {}
};
#define GET_PLAYERBOT_AI(p) ((p)->ai)
#define AI_VALUE(type,name) botAI->elite
struct Config { bool naturalProgression=true; float LootDistance=100.0f; } sPlayerbotAIConfig;
struct ServerFacade {
    static ServerFacade& instance() { static ServerFacade value; return value; }
    float GetDistance2d(Player* p,Unit* u) const { return p->GetDistance(u); }
};
struct Chat { std::string FormatWorldobject(Unit*) { return "target"; } } chatValue;
namespace ObjectAccessor { Player* FindPlayer(ObjectGuid) { return nullptr; } }
struct GrindTargetValue {
    PlayerbotAI* botAI; Player* bot; Context* context; Chat* chat=&chatValue;
    explicit GrindTargetValue(PlayerbotAI* ai):botAI(ai),bot(ai->bot),context(&ai->context){}
    Player* GetMaster() const { return botAI->master; }
    uint32 GetTargetingPlayerCount(Unit*) const { return 0; }
    Unit* FindTargetForGrinding(uint32);
    bool needForQuest(Unit*);
};
@@LOOT@@
@@NEEDED@@
@@FIND@@
'''

tests = r'''
struct Scenario {
    Player bot; PlayerbotAI ai{&bot}; GrindTargetValue value{&ai}; Creature target;
    Quest quest;
    Scenario() {
        objectMgr={}; LootTemplates_Creature={}; sPlayerbotAIConfig={};
        bot.ai=&ai; ai.units[1]=&target; ai.context.targets.value={{1}};
        quest.RequiredNpcOrGo[0]=100; quest.RequiredNpcOrGoCount[0]=1;
    }
    void KillQuest() { objectMgr.quests[quest.id]=quest; bot.quests[quest.id]={}; }
    void ItemQuest() {
        quest.RequiredNpcOrGo={}; quest.RequiredNpcOrGoCount={};
        quest.RequiredItemId[0]=6930; quest.RequiredItemCount[0]=3;
        target.data.lootid=99; objectMgr.creatures[target.entry]=target.data; KillQuest();
    }
    Unit* Find() { return value.FindTargetForGrinding(0); }
};
int main() {
    { Scenario s; assert(!s.Find()); }
    { Scenario s; s.target.xp=true; assert(s.Find()==&s.target); }
    { Scenario s; sPlayerbotAIConfig.naturalProgression=false; s.target.xp=true; assert(s.Find()==&s.target); }
    { Scenario s; s.KillQuest(); assert(s.Find()==&s.target); }
    { Scenario s; s.KillQuest(); sPlayerbotAIConfig.naturalProgression=false; assert(!s.Find()); }
    { Scenario s; s.KillQuest(); s.bot.quests[1473].status=QUEST_STATUS_COMPLETE; assert(!s.Find()); }
    { Scenario s; s.KillQuest(); s.bot.quests[1473].status=QUEST_STATUS_REWARDED; assert(!s.Find()); }
    { Scenario s; s.KillQuest(); s.bot.quests[1473].CreatureOrGOCount[0]=1; assert(!s.Find()); }
    { Scenario s; s.KillQuest(); s.target.entry=101; assert(!s.Find()); }
    { Scenario s; s.quest.level=36; s.KillQuest(); assert(!s.Find()); }
    { Scenario s; s.KillQuest(); objectMgr.quests.clear(); assert(!s.Find()); }
    { Scenario s; s.KillQuest(); s.target.los=false; assert(!s.Find()); }
    { Scenario s; s.KillQuest(); s.target.z=6; assert(!s.Find()); }
    { Scenario s; s.KillQuest(); s.target.inWorld=false; assert(!s.Find()); }
    { Scenario s; s.KillQuest(); s.target.removing=true; assert(!s.Find()); }
    { Scenario s; s.KillQuest(); s.target.hostile=false; s.target.flags=1; s.target.data.lootid=99; assert(!s.Find()); }
    { Scenario s; s.KillQuest(); s.target.level=35; assert(!s.Find()); }
    { Scenario s; s.KillQuest(); s.target.data.rank=1; assert(!s.Find()); s.ai.elite=true; assert(s.Find()==&s.target); }
    { Scenario s; s.target.alive=false; s.ai.context.targets.value.clear(); s.ai.context.attackers.value={{1}};
      assert(!s.Find()); s.target.alive=true; assert(s.Find()==&s.target); }
    { Scenario s; s.ItemQuest(); LootTemplate loot{6930}; LootTemplates_Creature.m_LootTemplates[99]=&loot;
      assert(s.Find()==&s.target); s.bot.quests[1473].ItemCount[0]=3; assert(!s.Find()); s.bot.quests[1473].ItemCount[0]=2;
      assert(s.Find()==&s.target); s.bot.quests[1473].status=QUEST_STATUS_COMPLETE; assert(!s.Find()); }
    { Scenario s; s.ItemQuest(); LootTemplate loot{9999}; LootTemplates_Creature.m_LootTemplates[99]=&loot;
      assert(!s.Find()); }
    { Scenario s; s.ItemQuest(); assert(!s.Find()); }
    std::cout<<"Quest grind targets: gray kill/item objectives, normal-mode exclusion and native target gates passed\n";
}
'''

mutations = (
    ('gray quest targets allowed', 'find',
     ' && (!sPlayerbotAIConfig.naturalProgression || !needForQuest(unit))', ''),
    ('natural mode required', 'find', '!sPlayerbotAIConfig.naturalProgression || ', ''),
    ('actual quest target required', 'find', '!needForQuest(unit)', 'false'),
    ('incomplete kill objective required', 'needed', 'status == QUEST_STATUS_INCOMPLETE',
     'status == QUEST_STATUS_INCOMPLETE || status == QUEST_STATUS_COMPLETE'),
    ('remaining kill credit required', 'needed', 'available < required', 'available <= required'),
    ('matching creature required', 'needed', 'target->GetEntry() == uint32(entry)', 'true'),
    ('line of sight required', 'find', '!bot->IsWithinLOSInMap(unit)', 'false'),
    ('reachable elevation retained', 'find',
     'abs(bot->GetPositionZ() - unit->GetPositionZ()) > INTERACTION_DISTANCE', 'false'),
)


def build(directory, parts, name):
    text = prelude
    for key, value in parts.items():
        text = text.replace('@@' + key.upper() + '@@', value)
    path = directory / (name + '.cpp')
    path.write_text(text + tests)
    binary = directory / name
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-missing-field-initializers',
                    *SANITIZER_FLAGS, str(path), '-o', str(binary)], check=True)
    return run_fixture([str(binary)])


with tempfile.TemporaryDirectory(prefix='portable-quest-grind-') as temporary:
    directory = Path(temporary)
    result = build(directory, production, 'quest-grind')
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit('Quest grind target fixture failed')

    reject_part_mutants(production, mutations, lambda parts, tag: build(directory, parts, tag),
                        'Quest grind')
