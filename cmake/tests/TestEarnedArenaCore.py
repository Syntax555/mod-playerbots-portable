"""Exercise native rated arena selection and weighted map filtering without a realm."""

import argparse
from pathlib import Path
import subprocess
import tempfile

from PreparedSources import prepared_core

repo = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, default=prepared_core(repo), help='Prepared core source tree')
core = parser.parse_args().source


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


queue = (core / 'src/server/game/Battlegrounds/BattlegroundQueue.cpp').read_text()
mgr = (core / 'src/server/game/Battlegrounds/BattlegroundMgr.cpp').read_text()
hooks = (core / 'src/server/game/Scripting/ScriptDefines/AllBattlegroundScript.cpp').read_text()
interfaces = (core / 'src/server/game/Scripting/ScriptDefines/AllBattlegroundScript.h').read_text()
macros = (core / 'src/server/game/Scripting/ScriptMgrMacros.h')
# A minimal scratch tree can point to the pinned core's unchanged hook-dispatch macro.
if not macros.exists():
    macros = repo / 'azerothcore-wotlk/src/server/game/Scripting/ScriptMgrMacros.h'
macro_text = macros.read_text()
macro_start = macro_text.index('#define CALL_ENABLED_BOOLEAN_HOOKS(')
macro = macro_text[macro_start:macro_text.index('\n\n', macro_start)]
selector = function(queue, 'bool BattlegroundQueue::SelectRatedArenaTeams(')
random_map = function(mgr, 'BattlegroundTypeId BattlegroundMgr::GetRandomBG(')
dispatch = '\n'.join(function(hooks, signature) for signature in [
    'bool ScriptMgr::CanMatchArenaTeams(', 'bool ScriptMgr::CanSelectArenaMap('])
defaults = '\n'.join(function(interfaces, signature) for signature in [
    '    [[nodiscard]] virtual bool CanMatchArenaTeams(',
    '    [[nodiscard]] virtual bool CanSelectArenaMap('])

fixture = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <list>
#include <map>
#include <memory>
#include <random>
#include <vector>
using uint8=uint8_t; using uint16=uint16_t; using uint32=uint32_t; using int32=int32_t;
using BattlegroundBracketId=int;
enum BattlegroundTypeId : uint8 {
    BATTLEGROUND_TYPE_NONE=0, BATTLEGROUND_AV=1, BATTLEGROUND_NA=4, BATTLEGROUND_BE=5,
    BATTLEGROUND_AA=6, BATTLEGROUND_RL=8, BATTLEGROUND_DS=10, BATTLEGROUND_RV=11
};
constexpr uint8 PVP_TEAMS_COUNT=2, TEAM_ALLIANCE=0, TEAM_HORDE=1;
constexpr uint8 BG_QUEUE_PREMADE_ALLIANCE=0, BG_QUEUE_PREMADE_HORDE=1, BG_QUEUE_NORMAL_ALLIANCE=2;
struct GroupQueueInfo {
    uint32 IsInvitedToBGInstanceGUID=0, ArenaMatchmakerRating=1000, JoinTime=1000;
    uint32 ArenaTeamId=0, PreviousOpponentsTeamId=0;
    uint8 era=2;
};
class BattlegroundQueue {
public:
    using GroupsQueueType=std::list<GroupQueueInfo*>;
    GroupsQueueType m_QueuedGroups[1][4];
    bool SelectRatedArenaTeams(BattlegroundBracketId, uint32, uint32, int32, int32,
        GroupsQueueType::iterator (&)[PVP_TEAMS_COUNT]);
};
class AllBattlegroundScript {
public:
    virtual ~AllBattlegroundScript()=default;
''' + defaults + r'''
};
enum { ALLBATTLEGROUNDHOOK_CAN_MATCH_ARENA_TEAMS, ALLBATTLEGROUNDHOOK_CAN_SELECT_ARENA_MAP };
template<typename T> struct ScriptRegistry {
    static inline std::array<std::vector<T*>, 2> EnabledHooks;
};
''' + macro + r'''
struct ScriptMgr {
    bool CanMatchArenaTeams(BattlegroundQueue*, GroupQueueInfo*, GroupQueueInfo*, BattlegroundBracketId);
    bool CanSelectArenaMap(BattlegroundTypeId, BattlegroundQueue*, BattlegroundBracketId,
        GroupQueueInfo*, GroupQueueInfo*);
} scriptMgr;
#define sScriptMgr (&scriptMgr)
''' + dispatch + '\n' + selector + r'''
struct EraFilter : AllBattlegroundScript {
    bool enabled=true;
    uint8 poolEra=2;
    bool CanMatchArenaTeams(BattlegroundQueue*, GroupQueueInfo* first, GroupQueueInfo* second,
        BattlegroundBracketId) override {
        return !enabled || (first->era>=1 && first->era==second->era);
    }
    bool CanSelectArenaMap(BattlegroundTypeId map, BattlegroundQueue*, BattlegroundBracketId,
        GroupQueueInfo* first, GroupQueueInfo* second) override {
        if (!enabled) return true;
        uint8 era=first ? first->era : poolEra;
        if (second && second->era!=era) return false;
        if (era<1) return false;
        return era>=2 || map==BATTLEGROUND_NA || map==BATTLEGROUND_BE || map==BATTLEGROUND_RL;
    }
} eraFilter;
struct BattlemasterListEntry { std::array<int32, 6> mapid={-1,-1,-1,-1,-1,-1}; };
struct BattlegroundTemplate {
    BattlegroundTypeId Id=BATTLEGROUND_TYPE_NONE;
    uint32 MinLevel=0; double Weight=0;
    BattlemasterListEntry const* BattlemasterEntry=nullptr;
};
// Capture the inputs to the unchanged weighted-selection boundary. A supplied
// percentile chooses deterministically from the actual eligible weights.
std::vector<BattlegroundTypeId> lastIds;
std::vector<double> lastWeights;
double percentile=0;
uint32 randomCalls=0;
namespace Acore::Containers {
    auto SelectRandomWeightedContainerElement(std::vector<BattlegroundTypeId> const& ids,
        std::vector<double> weights) {
        assert(!ids.empty()); assert(ids.size()==weights.size());
        lastIds=ids; lastWeights=weights; ++randomCalls;
        double total=0; for (double w:weights) total+=w;
        if (total==0) return ids.begin();
        double target=total*percentile;
        auto it=ids.begin();
        for (double w:weights) { if (target<w) return it; target-=w; ++it; }
        return std::prev(ids.end());
    }
}
struct BattlegroundMgr {
    std::map<BattlegroundTypeId, BattlegroundTemplate> types;
    std::map<int32, BattlegroundTemplate> maps;
    BattlegroundTemplate const* GetBattlegroundTemplateByTypeId(BattlegroundTypeId id) {
        auto it=types.find(id); return it==types.end() ? nullptr : &it->second;
    }
    BattlegroundTemplate const* GetBattlegroundTemplateByMapId(int32 id) {
        auto it=maps.find(id); return it==maps.end() ? nullptr : &it->second;
    }
    static bool IsArenaType(BattlegroundTypeId id) {
        return id==BATTLEGROUND_AA || id==BATTLEGROUND_NA || id==BATTLEGROUND_BE ||
            id==BATTLEGROUND_RL || id==BATTLEGROUND_DS || id==BATTLEGROUND_RV;
    }
    BattlegroundTypeId GetRandomBG(BattlegroundTypeId, uint32, BattlegroundQueue*,
        BattlegroundBracketId, GroupQueueInfo*, GroupQueueInfo*);
};
''' + random_map + r'''

// Frozen pre-patch native selector: differential checks prove feature-off
// matching keeps native queue order, MMR limits, invitation and timer rules.
bool NativeSelect(BattlegroundQueue& queue, uint32 minRating, uint32 maxRating,
    int32 discardTime, int32 discardOpponentsTime, BattlegroundQueue::GroupsQueueType::iterator (&teams)[2]) {
    uint8 found=0, team=0;
    for (uint8 i=0; i<2; ++i) {
        auto it=queue.m_QueuedGroups[0][i].begin();
        for (;it!=queue.m_QueuedGroups[0][i].end();++it) {
            auto* group=*it;
            if (!group->IsInvitedToBGInstanceGUID &&
                ((group->ArenaMatchmakerRating>=minRating && group->ArenaMatchmakerRating<=maxRating)
                 || int32(group->JoinTime)<discardTime)) {
                teams[found++]=it;team=i;break;
            }
        }
    }
    if (!found) return false;
    if (found==1) {
        for (auto it=teams[0];it!=queue.m_QueuedGroups[0][team].end();++it) {
            auto* group=*it;
            if (!group->IsInvitedToBGInstanceGUID &&
                ((group->ArenaMatchmakerRating>=minRating && group->ArenaMatchmakerRating<=maxRating)
                 || int32(group->JoinTime)<discardTime) &&
                ((*teams[0])->ArenaTeamId!=group->PreviousOpponentsTeamId || int32(group->JoinTime)<discardOpponentsTime)
                && (*teams[0])->ArenaTeamId!=group->ArenaTeamId) {
                teams[found++]=it;break;
            }
        }
    }
    return found==2;
}
void Register(AllBattlegroundScript* filter) {
    for (auto& hooks:ScriptRegistry<AllBattlegroundScript>::EnabledHooks) {
        hooks.clear(); if (filter) hooks.push_back(filter);
    }
}
void VerifyPair(BattlegroundQueue& queue, GroupQueueInfo* first, GroupQueueInfo* second,
    uint32 minRating=900, uint32 maxRating=1100, int32 discardTime=0, int32 opponents=0) {
    BattlegroundQueue::GroupsQueueType::iterator selected[2];
    bool found=queue.SelectRatedArenaTeams(0,minRating,maxRating,discardTime,opponents,selected);
    assert(found==(first && second));
    if (found) { assert(*selected[0]==first);assert(*selected[1]==second); }
}
int main() {
    AllBattlegroundScript defaults;
    Register(nullptr);
    assert(scriptMgr.CanMatchArenaTeams(nullptr,nullptr,nullptr,0));
    assert(scriptMgr.CanSelectArenaMap(BATTLEGROUND_DS,nullptr,0,nullptr,nullptr));
    Register(&defaults);
    assert(scriptMgr.CanMatchArenaTeams(nullptr,nullptr,nullptr,0));
    assert(scriptMgr.CanSelectArenaMap(BATTLEGROUND_DS,nullptr,0,nullptr,nullptr));
    Register(&eraFilter);
    GroupQueueInfo tbc{0,1000,1000,1,0,1}, wrathA{0,1000,1000,2,0,2}, wrathH{0,1000,1000,3,0,2};
    BattlegroundQueue queue;
    // An unmatched first TBC team cannot block the following Wrath pair.
    queue.m_QueuedGroups[0][0]={&tbc,&wrathA};queue.m_QueuedGroups[0][1]={&wrathH};
    VerifyPair(queue,&wrathA,&wrathH);
    GroupQueueInfo tbcH{0,1000,1000,4,0,1};
    queue.m_QueuedGroups[0][1]={&wrathH,&tbcH};
    VerifyPair(queue,&tbc,&tbcH);
    queue.m_QueuedGroups[0][0]={&tbc};queue.m_QueuedGroups[0][1]={&wrathH};
    VerifyPair(queue,nullptr,nullptr);
    // Same-faction selection also advances past stranded anchors.
    queue.m_QueuedGroups[0][0]={&tbc,&wrathA,&wrathH};queue.m_QueuedGroups[0][1].clear();
    VerifyPair(queue,&wrathA,&wrathH);
    wrathH.PreviousOpponentsTeamId=wrathA.ArenaTeamId;
    VerifyPair(queue,nullptr,nullptr);
    VerifyPair(queue,&wrathA,&wrathH,900,1100,0,1001);
    wrathH.PreviousOpponentsTeamId=0;
    wrathH.ArenaMatchmakerRating=1400;
    VerifyPair(queue,nullptr,nullptr);
    VerifyPair(queue,&wrathA,&wrathH,900,1100,1001);
    wrathH.IsInvitedToBGInstanceGUID=777;
    VerifyPair(queue,nullptr,nullptr,900,1100,1001);
    wrathH.IsInvitedToBGInstanceGUID=0;wrathH.ArenaMatchmakerRating=1000;
    queue.m_QueuedGroups[0][0].clear();queue.m_QueuedGroups[0][1]={&tbc,&wrathA,&wrathH};
    VerifyPair(queue,&wrathA,&wrathH);

    // Differential feature-off regression over varied native queue states.
    std::mt19937 rng(74017);
    eraFilter.enabled=false;
    for (int pass=0; pass<3; ++pass) {
        Register(pass==0 ? nullptr : pass==1 ? &defaults : &eraFilter);
        for (int trial=0;trial<3000;++trial) {
            BattlegroundQueue q;
            std::vector<std::unique_ptr<GroupQueueInfo>> storage;
            for (int faction=0;faction<2;++faction) {
                int size=rng()%9;
                for (int i=0;i<size;++i) {
                    auto g=std::make_unique<GroupQueueInfo>();
                    g->IsInvitedToBGInstanceGUID=rng()%4==0 ? 5 : 0;
                    g->ArenaMatchmakerRating=rng()%1600;
                    g->JoinTime=rng()%3000;
                    g->ArenaTeamId=rng()%8;
                    g->PreviousOpponentsTeamId=rng()%8;
                    g->era=rng()%3;
                    q.m_QueuedGroups[0][faction].push_back(g.get());storage.push_back(std::move(g));
                }
            }
            uint32 min=rng()%600,max=min+800;int32 time=int32(rng()%3500)-500;
            int32 previous=int32(rng()%3500)-500;
            BattlegroundQueue::GroupsQueueType::iterator native[2],actual[2];
            bool n=NativeSelect(q,min,max,time,previous,native);
            bool a=q.SelectRatedArenaTeams(0,min,max,time,previous,actual);
            assert(n==a);
            if (a) { assert(*native[0]==*actual[0]); assert(*native[1]==*actual[1]); }
        }
    }
    eraFilter.enabled=true;Register(&eraFilter);
    BattlegroundMgr manager;
    BattlemasterListEntry allMaps{{559,562,572,617,618,-1}};
    manager.types[BATTLEGROUND_AA]={BATTLEGROUND_AA,10,0,&allMaps};
    std::array<BattlegroundTypeId,5> ids={BATTLEGROUND_NA,BATTLEGROUND_BE,BATTLEGROUND_RL,
        BATTLEGROUND_DS,BATTLEGROUND_RV};
    for (int i=0;i<5;++i) manager.maps[allMaps.mapid[i]]={ids[i],10,double(i+1),nullptr};
    for (auto* first:std::array<GroupQueueInfo*,2>{nullptr,&tbc}) {
        eraFilter.poolEra=1;
        for (int roll=0;roll<100;++roll) {
            percentile=double(roll)/100;
            auto result=manager.GetRandomBG(BATTLEGROUND_AA,70,&queue,0,first,first ? &tbcH : nullptr);
            assert(result==BATTLEGROUND_NA || result==BATTLEGROUND_BE || result==BATTLEGROUND_RL);
            assert((lastIds==std::vector<BattlegroundTypeId>{BATTLEGROUND_NA,BATTLEGROUND_BE,BATTLEGROUND_RL}));
            assert((lastWeights==std::vector<double>{1,2,3}));
        }
    }
    for (auto* first:std::array<GroupQueueInfo*,2>{nullptr,&wrathA}) {
        eraFilter.poolEra=2;percentile=.99;
        assert(manager.GetRandomBG(BATTLEGROUND_AA,80,&queue,0,first,first ? &wrathH : nullptr)==BATTLEGROUND_RV);
        assert(lastIds.size()==5);assert((lastWeights==std::vector<double>{1,2,3,4,5}));
    }
    uint32 before=randomCalls;
    eraFilter.poolEra=0;
    assert(manager.GetRandomBG(BATTLEGROUND_AA,60,&queue,0,nullptr,nullptr)==BATTLEGROUND_TYPE_NONE);
    assert(manager.GetRandomBG(BATTLEGROUND_AA,70,&queue,0,&tbc,&wrathA)==BATTLEGROUND_TYPE_NONE);
    assert(manager.GetRandomBG(BATTLEGROUND_AA,1,&queue,0,&tbc,&tbcH)==BATTLEGROUND_TYPE_NONE);
    assert(randomCalls==before); // No call or dereference with an empty container.
    manager.maps[559].MinLevel=80;eraFilter.poolEra=1;percentile=0;
    assert(manager.GetRandomBG(BATTLEGROUND_AA,70,&queue,0,nullptr,nullptr)==BATTLEGROUND_BE);
    assert((lastWeights==std::vector<double>{2,3}));
    manager.maps[562].Weight=0;manager.maps[572].Weight=0;
    assert(manager.GetRandomBG(BATTLEGROUND_AA,70,&queue,0,nullptr,nullptr)==BATTLEGROUND_BE);
    Register(nullptr);percentile=.99;
    assert(manager.GetRandomBG(BATTLEGROUND_AA,80,nullptr,0,nullptr,nullptr)==BATTLEGROUND_RV);
    assert(manager.GetRandomBG(BATTLEGROUND_BE,80,nullptr,0,nullptr,nullptr)==BATTLEGROUND_TYPE_NONE);
    // A non-arena requested template bypasses the arena-only filter.
    manager.types[BATTLEGROUND_AV]={BATTLEGROUND_AV,10,0,&allMaps};Register(&eraFilter);eraFilter.poolEra=0;
    assert(manager.GetRandomBG(BATTLEGROUND_AV,80,nullptr,0,nullptr,nullptr)==BATTLEGROUND_RV);
    std::cout << "Arena core: 9000 native comparisons, earned-era pair search, weighted map filters passed\n";
}
'''

with tempfile.TemporaryDirectory(prefix='portable-earned-arena-') as temporary:
    source = Path(temporary) / 'arena.cpp'
    executable = Path(temporary) / 'arena'
    source.write_text(fixture)
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-no-pie',
                    str(source), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
