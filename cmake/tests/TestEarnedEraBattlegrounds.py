"""Check production earned-era queue gates and matchmaking under ASan/UBSan."""

import argparse
from pathlib import Path
import re
import subprocess
import tempfile
from PreparedSources import prepared_core

repo = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path,
                    default=prepared_core(repo) / 'modules/mod-individual-progression')
args = parser.parse_args()
module = args.source
production = (module / 'src/EarnedEraBattlegrounds.cpp').read_text()
production = re.sub(r'^#include ".*"\n', '', production, flags=re.MULTILINE)
bridge = (module / 'src/IndividualProgressionBattlegrounds.h').read_text()
bridge = re.sub(r'^#include ".*"\n', '', bridge, flags=re.MULTILINE)
# Exercise the native same-faction side/list moves with the production filter.
native_queue = (prepared_core(repo) / 'src/server/game/Battlegrounds/BattlegroundQueue.cpp').read_text()
start = native_queue.index('bool BattlegroundQueue::CheckSkirmishForSameFaction(')
opening = native_queue.index('{', start)
depth = 1
end = opening + 1
while depth:
    depth += (native_queue[end] == '{') - (native_queue[end] == '}')
    end += 1
native_skirmish = native_queue[start:end]


prelude = r'''
#include <cassert>
#include <cstdint>
#include <iostream>
#include <list>
#include <map>
#include <set>
#include <string>
#include <vector>
using uint8=std::uint8_t; using uint16=std::uint16_t; using uint32=std::uint32_t;
using ObjectGuid=uint32; using BattlegroundBracketId=uint8; using TeamId=uint8;
using BattlegroundQueueTypeId=uint8;
constexpr uint8 PROGRESSION_PRE_TBC=8, PROGRESSION_TBC_TIER_5=13;
constexpr uint32 MAX_BATTLEGROUND_TYPE_ID=33;
constexpr uint8 STATUS_WAIT_JOIN=1;
constexpr uint8 TEAM_ALLIANCE=0, TEAM_HORDE=1, PVP_TEAMS_COUNT=2;
constexpr uint8 BG_QUEUE_PREMADE_ALLIANCE=0, BG_QUEUE_PREMADE_HORDE=1,
    BG_QUEUE_NORMAL_ALLIANCE=2, BG_QUEUE_NORMAL_HORDE=3;
constexpr uint8 PLAYERHOOK_CAN_JOIN_IN_BATTLEGROUND_QUEUE=0,
    PLAYERHOOK_CAN_JOIN_IN_ARENA_QUEUE=1, PLAYERHOOK_CAN_BATTLEFIELD_PORT=2,
    GROUPHOOK_CAN_GROUP_JOIN_BATTLEGROUND_QUEUE=0;
constexpr uint8 ALLBATTLEGROUNDHOOK_ON_QUEUE_UPDATE=0, ALLBATTLEGROUNDHOOK_IS_CHECK_NORMAL_MATCH=1,
    ALLBATTLEGROUNDHOOK_CAN_ADD_GROUP_TO_MATCHING_POOL=2, ALLBATTLEGROUNDHOOK_ON_BATTLEGROUND_CREATE=3,
    ALLBATTLEGROUNDHOOK_ON_BATTLEGROUND_DESTROY=4,
    ALLBATTLEGROUNDHOOK_CAN_MATCH_ARENA_TEAMS=5, ALLBATTLEGROUNDHOOK_CAN_SELECT_ARENA_MAP=6;
constexpr uint8 CONFIG_BATTLEGROUND_PREMADE_GROUP_WAIT_FOR_MATCH=0,
    CONFIG_BATTLEGROUND_INVITATION_TYPE=1, BG_QUEUE_INVITATION_TYPE_NO_BALANCE=0;
enum BattlegroundTypeId : uint8 { BATTLEGROUND_TYPE_NONE=0, BATTLEGROUND_AV=1,
    BATTLEGROUND_WS=2, BATTLEGROUND_AB=3, BATTLEGROUND_NA=4, BATTLEGROUND_BE=5,
    BATTLEGROUND_AA=6, BATTLEGROUND_EY=7, BATTLEGROUND_RL=8, BATTLEGROUND_SA=9,
    BATTLEGROUND_DS=10, BATTLEGROUND_RV=11, BATTLEGROUND_IC=30, BATTLEGROUND_RB=32 };
enum GroupJoinBattlegroundResult { ERR_BATTLEGROUND_JOIN_FAILED=-1 };
struct Group;
struct GroupReference;
struct Player {
    uint32 id=0; uint8 stage=0, level=80; bool online=true; Group* group=nullptr;
    bool IsInWorld() const { return online; }
    uint32 GetLevel() const { return level; }
    ObjectGuid GetGUID() const { return id; }
    Group* GetGroup() const { return group; }
    bool GetBGAccessByLevel(BattlegroundTypeId type) const;
};
struct GroupReference {
    Player* player=nullptr; GroupReference* following=nullptr;
    Player* GetSource() const { return player; }
    GroupReference* next() const { return following; }
};
struct Group {
    std::list<GroupReference> refs;
    GroupReference* GetFirstMember() { return refs.empty()?nullptr:&refs.front(); }
    GroupReference const* GetFirstMember() const { return refs.empty()?nullptr:&refs.front(); }
    void Set(std::initializer_list<Player*> players) {
        refs.clear(); GroupReference* previous=nullptr;
        for (Player* player : players) {
            refs.push_back({player,nullptr});
            if (previous) previous->following=&refs.back();
            previous=&refs.back(); if (player) player->group=this;
        }
    }
};
struct Battleground {
    BattlegroundTypeId type=BATTLEGROUND_WS; uint32 id=0, minLevel=10, maxLevel=80;
    uint8 arenaType=0; bool arena=false;
    uint32 maxScore=0, nearVictory=0, reinforcements=999, startTime=0, configurationCalls=0;
    uint8 configuredEra=255;
    uint8 status=STATUS_WAIT_JOIN; std::map<ObjectGuid,Player*> players;
    uint8 GetStatus() const { return status; }
    uint32 GetStartTime() const { return startTime; }
    auto const& GetPlayers() const { return players; }
    BattlegroundTypeId GetBgTypeID(bool =false) const { return type; }
    Battleground* ToBattlegroundAB() { return this; }
    Battleground* ToBattlegroundAV() { return this; }
    Battleground* ToBattlegroundEY() { return this; }
    Battleground* ToBattlegroundWS() { return this; }
    void ConfigureScoreLimit(uint32 max) { maxScore=max; ++configurationCalls; }
    void ConfigureEraRules(uint8 era) { configuredEra=era; ++configurationCalls; }
    void ConfigureScoreLimit(uint32 max,uint32 near) { maxScore=max; nearVictory=near; ++configurationCalls; }
    void ConfigureReinforcements(uint32 count) { reinforcements=count; ++configurationCalls; }
    uint32 GetInstanceID() const { return id; }
    uint8 GetArenaType() const { return arenaType; }
    bool isArena() const { return arena; }
    uint32 GetMinLevel() const { return minLevel; }
    uint32 GetMaxLevel() const { return maxLevel; }
};
struct GroupQueueInfo {
    std::set<ObjectGuid> Players; uint8 teamId=0, RealTeamID=0, GroupType=2;
    BattlegroundTypeId BgTypeId=BATTLEGROUND_WS;
    uint32 JoinTime=0, IsInvitedToBGInstanceGUID=0;
};
struct BattlegroundQueue {
    using GroupsQueueType=std::list<GroupQueueInfo*>;
    struct SelectionPool {
        GroupsQueueType SelectedGroups; uint32 PlayerCount=0;
        void Init() { SelectedGroups.clear(); PlayerCount=0; }
        uint32 GetPlayerCount() const { return PlayerCount; }
        bool AddGroup(GroupQueueInfo* group, uint32 desired) {
            if (!group->IsInvitedToBGInstanceGUID && desired>=PlayerCount+group->Players.size()) {
                SelectedGroups.push_back(group); PlayerCount+=group->Players.size(); return true;
            }
            return PlayerCount<desired;
        }
    };
    bool CheckSkirmishForSameFaction(BattlegroundBracketId,uint32);
    SelectionPool m_SelectionPools[2];
    GroupsQueueType m_QueuedGroups[4][10];
    std::map<ObjectGuid,GroupQueueInfo*> m_QueuedPlayers;
    bool GetPlayerGroupInfoData(ObjectGuid guid,GroupQueueInfo* info) {
        auto found=m_QueuedPlayers.find(guid); if (found==m_QueuedPlayers.end()) return false;
        *info=*found->second; return true;
    }
};
struct BattlegroundMgr {
    bool testing=false;
    std::map<uint8,Battleground> templates;
    std::map<uint8,BattlegroundQueue*> queues;
    std::map<uint32,Battleground*> instances;
    static BattlegroundQueueTypeId BGQueueTypeId(BattlegroundTypeId type,uint8 arena) {
        return arena?static_cast<uint8>(BATTLEGROUND_AA):static_cast<uint8>(type);
    }
    BattlegroundQueue& GetBattlegroundQueue(uint8 type) { assert(queues.count(type)); return *queues.at(type); }
    Battleground* GetBattlegroundTemplate(uint8 type) { return templates.count(type)?&templates.at(type):nullptr; }
    Battleground* GetBattleground(uint32 id,BattlegroundTypeId) {
        auto found=instances.find(id); return found==instances.end()?nullptr:found->second;
    }
    bool isTesting() const { return testing; }
} manager;
BattlegroundMgr* sBattlegroundMgr=&manager;
bool Player::GetBGAccessByLevel(BattlegroundTypeId type) const {
    Battleground* bg=sBattlegroundMgr->GetBattlegroundTemplate(type);
    if (!bg) return false;
    uint32 actualLevel=GetLevel(); if (actualLevel>80) actualLevel=80;
    return actualLevel>=bg->GetMinLevel() && actualLevel<=bg->GetMaxLevel();
}
namespace ObjectAccessor {
    std::map<uint32,Player*> players;
    Player* FindConnectedPlayer(ObjectGuid guid) {
        auto found=players.find(guid); return found==players.end()?nullptr:found->second;
    }
}
struct IndividualProgression {
    bool enabled=true, strict=true, disableDefault=false; std::map<int,int> custom;
    bool IsStrictDefaultProgression() const { return enabled&&strict&&!disableDefault&&custom.empty(); }
    uint8 GetPlayerProgressionFromQuests(Player* player) const { return player->stage; }
} individual;
IndividualProgression* sIndividualProgression=&individual;
struct World { uint32 wait=1800000, balance=1;
    uint32 getIntConfig(uint8 config) const { return config==0?wait:balance; }
} world;
World* sWorld=&world;
namespace GameTime { uint32 now=0; struct Clock { uint32 count() const { return now; } };
    Clock GetGameTimeMS() { return {}; }
}
struct PlayerScript {
    PlayerScript(char const*,std::vector<uint16>) {}
    virtual bool OnPlayerCanJoinInBattlegroundQueue(Player*,ObjectGuid,BattlegroundTypeId,uint8,GroupJoinBattlegroundResult&) { return true; }
    virtual bool OnPlayerCanJoinInArenaQueue(Player*,ObjectGuid,uint8,BattlegroundTypeId,uint8,uint8,GroupJoinBattlegroundResult&) { return true; }
    virtual bool OnPlayerCanBattleFieldPort(Player*,uint8,BattlegroundTypeId,uint8) { return true; }
};
struct GroupScript {
    GroupScript(char const*,std::vector<uint16>) {}
    virtual bool CanGroupJoinBattlegroundQueue(Group const*,Player*,Battleground const*,uint32,bool,uint32) { return true; }
};
struct AllBattlegroundScript {
    AllBattlegroundScript(char const*,std::vector<uint16>) {}
    virtual void OnQueueUpdate(BattlegroundQueue*,uint32,BattlegroundTypeId,BattlegroundBracketId,uint8,bool,uint32) {}
    virtual bool CanAddGroupToMatchingPool(BattlegroundQueue*,GroupQueueInfo*,uint32,Battleground*,BattlegroundBracketId) { return true; }
    virtual bool IsCheckNormalMatch(BattlegroundQueue*,Battleground*,BattlegroundBracketId,uint32,uint32) { return false; }
    virtual bool CanMatchArenaTeams(BattlegroundQueue*,GroupQueueInfo*,GroupQueueInfo*,BattlegroundBracketId) { return true; }
    virtual bool CanSelectArenaMap(BattlegroundTypeId,BattlegroundQueue*,BattlegroundBracketId,GroupQueueInfo*,GroupQueueInfo*) { return true; }
    virtual void OnBattlegroundCreate(Battleground*) {}
    virtual void OnBattlegroundDestroy(Battleground*) {}
};
struct ScriptMgr {
    AllBattlegroundScript* hook=nullptr;
    bool CanAddGroupToMatchingPool(BattlegroundQueue* queue,GroupQueueInfo* group,uint32 count,Battleground* bg,BattlegroundBracketId bracket) {
        return hook->CanAddGroupToMatchingPool(queue,group,count,bg,bracket);
    }
} scripts;
ScriptMgr* sScriptMgr=&scripts;
'''

checks = r'''
int main() {
    for (uint8 type : {1,2,3,4,5,6,7,8,9,10,11,30,32}) {
        Battleground bg; bg.type=BattlegroundTypeId(type);
        bg.minLevel=(type==7?61:(type==9||type==30?71:(type==32?80:10)));
        manager.templates.emplace(type,bg);
    }
    IndividualProgressionEarnedBattlegroundPlayer playerHook;
    IndividualProgressionEarnedBattlegroundGroup groupHook;
    IndividualProgressionEarnedBattlegroundQueue queueHook;
    scripts.hook=&queueHook;
    Player player;
    for (uint8 stage=0;stage<=18;++stage) {
        player.stage=stage;
        uint8 era=stage>=13?2:stage>=8?1:0;
        player.level=era==0?60:era==1?70:80;
        assert(IndividualProgression_GetEarnedEra(&player)==era);
        assert(IndividualProgression_BattlegroundEra(&player)==era);
        for (uint8 type : {1,2,3,4,5,6,7,8,9,10,11,30,32}) {
            uint8 required=(type<=3?0:(type==4||type==5||type==6||type==7||type==8?1:2));
            assert(IndividualProgression_CanJoinBattleground(&player,type)==(era>=required && player.level>=manager.templates.at(type).minLevel));
        }
    }
    player.stage=18; player.level=9;
    assert(!IndividualProgression_CanJoinBattleground(&player,BATTLEGROUND_WS));
    player.level=60; assert(!IndividualProgression_CanJoinBattleground(&player,BATTLEGROUND_EY));
    player.level=70; assert(!IndividualProgression_CanJoinBattleground(&player,BATTLEGROUND_SA));
    assert(!IndividualProgression_CanJoinBattleground(nullptr,2));
    assert(!IndividualProgression_CanJoinBattleground(&player,256));
    assert(!IndividualProgression_CanJoinBattleground(&player,31));
    player.stage=0; player.level=61;
    assert(!IndividualProgression_CanJoinBattleground(&player,BATTLEGROUND_WS));
    player.stage=8; player.level=71;
    assert(!IndividualProgression_CanJoinBattleground(&player,BATTLEGROUND_WS));
    player.online=false; assert(!IndividualProgression_CanJoinBattleground(&player,2)); player.online=true;
    individual.strict=false; player.level=80; player.stage=0;
    assert(IndividualProgression_CanJoinBattleground(&player,9));
    assert(IndividualProgression_GetEarnedEra(&player)==255);
    individual.strict=true; individual.disableDefault=true;
    assert(IndividualProgression_CanJoinBattleground(&player,9)); individual.disableDefault=false;
    individual.custom[1]=1; assert(IndividualProgression_CanJoinBattleground(&player,9)); individual.custom.clear();

    Player leader{1,13,80}, member{2,8,80};
    Group party; party.Set({&leader,&member});
    GroupJoinBattlegroundResult error=GroupJoinBattlegroundResult(2);
    assert(!playerHook.OnPlayerCanJoinInBattlegroundQueue(&leader,0,BATTLEGROUND_WS,1,error));
    assert(error==ERR_BATTLEGROUND_JOIN_FAILED);
    member.stage=13;
    assert(playerHook.OnPlayerCanJoinInBattlegroundQueue(&leader,0,BATTLEGROUND_SA,1,error));
    member.stage=7;
    assert(!playerHook.OnPlayerCanJoinInBattlegroundQueue(&leader,0,BATTLEGROUND_EY,1,error));
    assert(!groupHook.CanGroupJoinBattlegroundQueue(&party,&member,&manager.templates.at(2),1,false,0));
    party.Set({&leader,nullptr});
    assert(!playerHook.OnPlayerCanJoinInBattlegroundQueue(&leader,0,BATTLEGROUND_WS,1,error));
    assert(!playerHook.OnPlayerCanJoinInArenaQueue(&member,0,0,BATTLEGROUND_AA,0,0,error));
    member.stage=8; member.level=70;
    assert(playerHook.OnPlayerCanJoinInArenaQueue(&member,0,0,BATTLEGROUND_AA,0,0,error));
    assert(playerHook.OnPlayerCanBattleFieldPort(&member,0,BATTLEGROUND_SA,0));
    assert(!playerHook.OnPlayerCanBattleFieldPort(&member,0,BATTLEGROUND_SA,1));

    std::vector<Player> players; players.reserve(12);
    std::vector<GroupQueueInfo> groups; groups.reserve(12);
    BattlegroundQueue queue;
    manager.queues[2]=&queue;
    auto add=[&](uint8 stage,uint8 team,uint8 groupType=255) {
        uint32 id=10+players.size(); players.push_back({id,stage,60});
        ObjectAccessor::players[id]=&players.back();
        GroupQueueInfo group; group.Players.insert(id); group.BgTypeId=BATTLEGROUND_WS;
        group.teamId=group.RealTeamID=team;
        group.GroupType=groupType==255?2+team:groupType;
        groups.push_back(group);
        queue.m_QueuedGroups[0][groups.back().GroupType].push_back(&groups.back());
        queue.m_QueuedPlayers[id]=&groups.back();
        return &groups.back();
    };
    GroupQueueInfo* vanillaA=add(7,0);
    GroupQueueInfo* tbcA=add(8,0);
    GroupQueueInfo* tbcH=add(8,1);
    Battleground bg=manager.templates.at(2);
    assert(queueHook.IsCheckNormalMatch(&queue,&bg,0,1,10));
    assert(queue.m_SelectionPools[0].GetPlayerCount()==1&&queue.m_SelectionPools[1].GetPlayerCount()==1);
    assert(queue.m_SelectionPools[0].SelectedGroups.front()==tbcA);
    assert(queue.m_SelectionPools[1].SelectedGroups.front()==tbcH);
    assert(!queueHook.CanAddGroupToMatchingPool(&queue,vanillaA,1,&bg,0));
    GroupQueueInfo* vanillaH=add(7,1);
    add(13,0); add(13,1);
    std::set<uint8> served;
    for (int round=0;round<3;++round) {
        assert(queueHook.IsCheckNormalMatch(&queue,&bg,0,1,10));
        uint8 era=SelectedEra(&queue); assert(era<3); served.insert(era);
        for (auto const& pool:queue.m_SelectionPools)
            for (auto* group:pool.SelectedGroups) assert(QueuedGroupEra(group)==era);
    }
    assert(served.size()==3);  // No permanently waiting era when all are ready.
    for (auto& pool:queue.m_SelectionPools) pool.Init();
    vanillaA->IsInvitedToBGInstanceGUID=777; vanillaH->IsInvitedToBGInstanceGUID=777;
    bg.id=777; manager.instances[777]=&bg; queueHook.OnBattlegroundCreate(&bg);
    assert(playerHook.OnPlayerCanBattleFieldPort(&players.front(),0,BATTLEGROUND_WS,1));
    players.front().stage=8;
    assert(!playerHook.OnPlayerCanBattleFieldPort(&players.front(),0,BATTLEGROUND_WS,1));
    assert(playerHook.OnPlayerCanBattleFieldPort(&players.front(),0,BATTLEGROUND_WS,0));
    players.front().stage=7;
    assert(IndividualProgression_BattlegroundMatchEra(&bg)==0);
    bg.status=2; bg.startTime=900; bg.players[players.front().id]=&players.front();
    assert(IndividualProgression_BattlegroundMatchEra(&bg)==0);
    queue.m_QueuedPlayers.erase(*vanillaA->Players.begin());
    queue.m_QueuedPlayers.erase(*vanillaH->Players.begin());
    players.front().stage=13;  // Era remains fixed even if invitees progress/leave.
    assert(IndividualProgression_BattlegroundMatchEra(&bg)==0);
    assert(!queueHook.CanAddGroupToMatchingPool(&queue,tbcA,0,&bg,0));
    Player replacement{99,7,60}; ObjectAccessor::players[99]=&replacement;
    GroupQueueInfo refill; refill.Players.insert(99); refill.BgTypeId=BATTLEGROUND_WS;
    assert(queueHook.CanAddGroupToMatchingPool(&queue,&refill,0,&bg,0));
    assert(bg.configurationCalls==1 && bg.configuredEra==0); // Refilling keeps the match's original rules.
    queueHook.OnBattlegroundDestroy(&bg);
    assert(IndividualProgression_BattlegroundMatchEra(&bg)==255);
    assert(queueHook.CanAddGroupToMatchingPool(&queue,&refill,0,&bg,0)==false);
    bg.id=0; bg.status=STATUS_WAIT_JOIN; bg.startTime=0; bg.players.clear();

    GroupQueueInfo* premadeA=add(7,0,0);
    GroupQueueInfo* premadeH=add(8,1,1);
    queueHook.OnQueueUpdate(&queue,0,BATTLEGROUND_WS,0,0,false,0);
    for (auto& pool:queue.m_SelectionPools) pool.Init();
    assert(queueHook.CanAddGroupToMatchingPool(&queue,premadeA,0,nullptr,0));
    assert(!queueHook.CanAddGroupToMatchingPool(&queue,premadeH,0,nullptr,0));
    GameTime::now=world.wait;
    queueHook.OnQueueUpdate(&queue,0,BATTLEGROUND_WS,0,0,false,0);
    assert(queue.m_QueuedGroups[0][0].empty()&&queue.m_QueuedGroups[0][1].empty());
    assert(premadeA->GroupType==2&&premadeH->GroupType==3);
    assert(premadeA->teamId==0&&premadeH->teamId==1);
    assert(premadeA->Players.size()==1&&premadeH->Players.size()==1);
    for (auto& pool:queue.m_SelectionPools) pool.Init();
    queue.m_SelectionPools[0].AddGroup(tbcA,10); queue.m_SelectionPools[1].AddGroup(tbcH,10);
    assert(queueHook.CanMatchArenaTeams(&queue,tbcA,tbcH,0));
    assert(!queueHook.CanMatchArenaTeams(&queue,tbcA,premadeA,0));
    assert(!queueHook.CanMatchArenaTeams(&queue,tbcA,tbcA,0));
    assert(queueHook.CanSelectArenaMap(BATTLEGROUND_NA,&queue,0,nullptr,nullptr));
    assert(queueHook.CanSelectArenaMap(BATTLEGROUND_BE,&queue,0,tbcA,tbcH));
    assert(queueHook.CanSelectArenaMap(BATTLEGROUND_RL,&queue,0,tbcA,tbcH));
    assert(!queueHook.CanSelectArenaMap(BATTLEGROUND_DS,&queue,0,tbcA,tbcH));
    assert(!queueHook.CanSelectArenaMap(BATTLEGROUND_RV,&queue,0,tbcA,tbcH));
    tbcA->IsInvitedToBGInstanceGUID=800; tbcH->IsInvitedToBGInstanceGUID=800;
    manager.queues[3]=&queue; manager.queues[1]=&queue;
    Battleground ab=manager.templates.at(3); ab.id=800;
    queueHook.OnBattlegroundCreate(&ab);
    assert(ab.maxScore==2000 && ab.nearVictory==1800);
    Battleground av=manager.templates.at(1); av.id=801;
    tbcA->IsInvitedToBGInstanceGUID=801; tbcH->IsInvitedToBGInstanceGUID=801;
    queueHook.OnBattlegroundCreate(&av); assert(av.reinforcements==600);
    uint32 const avConfigurationCalls=av.configurationCalls;
    av.reinforcements=577; // A running match has already spent reinforcements.
    GroupQueueInfo tbcRefill=*tbcA; tbcRefill.IsInvitedToBGInstanceGUID=0;
    assert(queueHook.CanAddGroupToMatchingPool(&queue,&tbcRefill,0,&av,0));
    assert(av.configurationCalls==avConfigurationCalls && av.reinforcements==577);
    for (auto* group:{tbcA,tbcH})
        ObjectAccessor::players.at(*group->Players.begin())->stage=13;
    assert(queueHook.CanSelectArenaMap(BATTLEGROUND_DS,&queue,0,tbcA,tbcH));
    assert(queueHook.CanSelectArenaMap(BATTLEGROUND_RV,&queue,0,tbcA,tbcH));
    tbcA->IsInvitedToBGInstanceGUID=802; tbcH->IsInvitedToBGInstanceGUID=802;
    ab.id=802; queueHook.OnBattlegroundCreate(&ab); assert(ab.maxScore==1600&&ab.nearVictory==1400);
    for (auto* group:{tbcA,tbcH}) {
        ObjectAccessor::players.at(*group->Players.begin())->stage=7;
        group->IsInvitedToBGInstanceGUID=803;
    }
    av.id=803; queueHook.OnBattlegroundCreate(&av); assert(av.reinforcements==0);
    av.id=804; av.status=2;
    for (auto* group:{tbcA,tbcH}) group->IsInvitedToBGInstanceGUID=804;
    assert(IndividualProgression_BattlegroundMatchEra(&av)==255);
    av.status=STATUS_WAIT_JOIN; av.players[99]=&replacement;
    assert(IndividualProgression_BattlegroundMatchEra(&av)==255);
    manager.queues[7]=&queue;
    Battleground eye=manager.templates.at(7);
    for (auto* group:{tbcA,tbcH}) {
        group->BgTypeId=BATTLEGROUND_EY; group->IsInvitedToBGInstanceGUID=900;
        Player* participant=ObjectAccessor::players.at(*group->Players.begin());
        participant->stage=8; participant->level=70;
    }
    eye.id=900; queueHook.OnBattlegroundCreate(&eye); assert(eye.maxScore==2000);
    for (auto* group:{tbcA,tbcH}) {
        group->IsInvitedToBGInstanceGUID=901;
        ObjectAccessor::players.at(*group->Players.begin())->stage=13;
    }
    eye.id=901; queueHook.OnBattlegroundCreate(&eye); assert(eye.maxScore==1600);
    Battleground warsong=manager.templates.at(2);
    for (uint8 era=0;era<3;++era) {
        for (auto* group:{tbcA,tbcH}) {
            group->BgTypeId=BATTLEGROUND_WS; group->IsInvitedToBGInstanceGUID=902+era;
            Player* participant=ObjectAccessor::players.at(*group->Players.begin());
            participant->stage=era==0?7:era==1?8:13; participant->level=60;
        }
        warsong.id=902+era; queueHook.OnBattlegroundCreate(&warsong);
        assert(warsong.configuredEra==era);
    }
    BattlegroundQueue arenaQueue;
    std::vector<Player> arenaPlayers; arenaPlayers.reserve(16);
    std::vector<GroupQueueInfo> arenaGroups; arenaGroups.reserve(8);
    auto addArena=[&](uint8 stage,uint8 team) {
        GroupQueueInfo group; group.BgTypeId=BATTLEGROUND_AA;
        group.teamId=group.RealTeamID=team; group.GroupType=2+team;
        for (int memberIndex=0;memberIndex<2;++memberIndex) {
            uint32 id=900+arenaPlayers.size(); arenaPlayers.push_back({id,stage,70});
            ObjectAccessor::players[id]=&arenaPlayers.back(); group.Players.insert(id);
        }
        arenaGroups.push_back(group); auto* result=&arenaGroups.back();
        arenaQueue.m_QueuedGroups[0][result->GroupType].push_back(result);
        for (auto guid:result->Players) arenaQueue.m_QueuedPlayers[guid]=result;
        return result;
    };
    GroupQueueInfo* firstTbc=addArena(8,0);
    addArena(13,0); addArena(13,1);
    Battleground arena=manager.templates.at(6); arena.arena=true;
    assert(queueHook.IsCheckNormalMatch(&arenaQueue,&arena,0,2,2));
    assert(SelectedEra(&arenaQueue)==2); // Stranded first TBC team cannot block a ready Wrath pair.
    assert(arenaQueue.m_SelectionPools[0].GetPlayerCount()==2);
    assert(arenaQueue.m_SelectionPools[1].GetPlayerCount()==2);
    GroupQueueInfo* secondTbc=addArena(8,0);
    auto originalMembers=secondTbc->Players;
    assert(queueHook.IsCheckNormalMatch(&arenaQueue,&arena,0,2,2));
    assert(SelectedEra(&arenaQueue)==1);
    assert(arenaQueue.m_SelectionPools[0].SelectedGroups.front()==firstTbc);
    assert(arenaQueue.m_SelectionPools[1].GetPlayerCount()==0);
    assert(arenaQueue.CheckSkirmishForSameFaction(0,2));
    assert(arenaQueue.m_SelectionPools[1].SelectedGroups.front()==secondTbc);
    assert(secondTbc->teamId==1&&secondTbc->RealTeamID==0&&secondTbc->GroupType==3);
    assert(secondTbc->Players==originalMembers);
    assert(arenaQueue.m_QueuedGroups[0][3].front()==secondTbc);
    individual.strict=false;
    assert(!queueHook.IsCheckNormalMatch(&queue,&bg,0,1,10));
    assert(queueHook.CanAddGroupToMatchingPool(&queue,premadeH,0,&bg,0));
    Battleground native=manager.templates.at(7); native.id=900;
    queueHook.OnBattlegroundCreate(&native);
    assert(native.configurationCalls==0); // Unrestricted policy leaves the native rules alone.
    std::cout<<"Earned era battleground gates, group isolation, fair matching and immutable refill era passed.\n";
}
'''

with tempfile.TemporaryDirectory(prefix='earned-era-bg-') as scratch:
    folder = Path(scratch)
    source = folder / 'fixture.cpp'
    source.write_text(prelude + bridge + production + native_skirmish + checks)
    binary = folder / 'fixture'
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-pthread',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-g',
                    str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
