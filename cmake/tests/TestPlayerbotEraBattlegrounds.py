"""Exercise production bot queue eligibility and era-isolated filler counts without a realm."""

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

from FixtureSupport import TIMEOUT, cxx, function, prepared_core


parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, help='prepared Playerbots module directory')
args = parser.parse_args()
repo = Path(__file__).resolve().parents[2]
module = args.source if args.source else prepared_core(repo) / 'modules/mod-playerbots'
pb = module / 'src/Bot'

script = (module / 'src/Script/Playerbots.cpp').read_text()
native_hooks = '\n'.join(function(script, signature).replace(' override', '') for signature in (
    '    bool CanQueueWithBots(', '    bool OnPlayerCanJoinInBattlegroundQueue(',
    '    bool OnPlayerCanJoinInArenaQueue('))
assert 'PLAYERHOOK_CAN_JOIN_IN_BATTLEGROUND_QUEUE' in script
assert 'PLAYERHOOK_CAN_JOIN_IN_ARENA_QUEUE' in script
manager_source = (pb / 'RandomPlayerbotMgr.cpp').read_text()
queue_recorder = function(manager_source, 'static void RecordEarnedBattlegroundQueue(')
check_queue = function(manager_source, 'void RandomPlayerbotMgr::CheckBgQueue()')
assert 'GetBattlegroundBracketByLevel' not in check_queue
for participant in ('player', 'bot'):
    assert check_queue.count(f'getQueueBracket({participant}, bg, queueType, queueTypeId, mapId)') == 1
bracket_start = check_queue.index('    auto getQueueBracket = [&](')
queue_bracket = check_queue[bracket_start:check_queue.index('\n    };\n', bracket_start) + len('\n    };\n')]

shared = r'''
#ifndef TEST_SHARED_DEFINES_H
#define TEST_SHARED_DEFINES_H
#include <cstdint>
using uint8 = uint8_t; using uint32 = uint32_t;
enum TeamId { TEAM_ALLIANCE, TEAM_HORDE, TEAM_NEUTRAL };
enum BattlegroundQueueTypeId {
    BATTLEGROUND_QUEUE_NONE, BATTLEGROUND_QUEUE_AV, BATTLEGROUND_QUEUE_WS,
    BATTLEGROUND_QUEUE_AB, BATTLEGROUND_QUEUE_EY, BATTLEGROUND_QUEUE_SA,
    BATTLEGROUND_QUEUE_IC, BATTLEGROUND_QUEUE_RB, BATTLEGROUND_QUEUE_2v2,
    BATTLEGROUND_QUEUE_3v3, BATTLEGROUND_QUEUE_5v5, MAX_BATTLEGROUND_QUEUE_TYPES
};
constexpr unsigned MAX_BATTLEGROUND_BRACKETS = 16;
struct Group;
struct Battleground;
struct Session { bool headless = false; bool IsHeadless() { return headless; } };
struct Player {
    unsigned stage = 0, level = 1;
    bool isBot = false, selfBot = false, inBattleground = false;
    uint8 queueSlot = 0;
    Session session;
    Session* GetSession() { return &session; }
    Group* group = nullptr;
    unsigned guid = 0;
    TeamId team = TEAM_ALLIANCE;
    Battleground* battleground = nullptr;
    unsigned GetGUID() { return guid; }
    TeamId GetTeamId() { return team; }
    Battleground* GetBattleground(bool create = false);
    unsigned GetLevel() { return level; }
    bool InBattleground() { return inBattleground; }
    uint8 GetCurrentBattlegroundQueueSlot() { return queueSlot; }
    Group* GetGroup() { return group; }
};
using BattlegroundTypeId = uint32;
using BattlegroundBracketId = uint32;
struct ObjectGuid {};
enum GroupJoinBattlegroundResult { ERR_BATTLEGROUND_JOIN_FAILED = -12, TEST_QUEUE_OK = 1 };
constexpr unsigned ARENA_TYPE_NONE = 0;
struct GroupReference {
    Player* player = nullptr;
    GroupReference* following = nullptr;
    Player* GetSource() { return player; }
    GroupReference* next() { return following; }
};
struct Group {
    GroupReference* first = nullptr;
    GroupReference* GetFirstMember() { return first; }
};
#endif
'''
bgmgr = r'''
#ifndef TEST_BATTLEGROUND_MGR_H
#define TEST_BATTLEGROUND_MGR_H
#include "SharedDefines.h"
#include <map>
#include <array>
constexpr unsigned STATUS_WAIT_JOIN = 2, STATUS_IN_PROGRESS = 3, STATUS_WAIT_LEAVE = 4;
struct Battleground {
    uint32 queue = 0, instance = 0, status = STATUS_IN_PROGRESS, bracket = 0;
    bool mapCreated = true;
    uint32 GetBracketId() { return bracket; }
    uint32 GetBgTypeID() { return queue; }
    uint32 GetArenaType() { return 0; }
    uint32 GetStatus() { return status; }
    uint32 GetInstanceID() { return instance; }
};
inline Battleground* Player::GetBattleground(bool create)
{
    return battleground && (create || battleground->mapCreated) ? battleground : nullptr;
}
struct GroupQueueInfo { uint32 IsInvitedToBGInstanceGUID = 0; uint8 BracketId = 0; };
struct PvPDifficultyEntry {
    uint32 mapId, bracketId, minLevel, maxLevel;
    BattlegroundBracketId GetBracketId() const { return bracketId; }
};
inline std::array<PvPDifficultyEntry, 4> pvpBrackets{{{489, 0, 10, 19}, {489, 1, 20, 29}, {489, 2, 30, 39}, {489, 3, 40, 49}}};
inline PvPDifficultyEntry const* GetBattlegroundBracketById(uint32 mapId, BattlegroundBracketId id) {
    for (auto const& entry : pvpBrackets)
        if (entry.mapId == mapId && entry.bracketId == id) return &entry;
    return nullptr;
}
inline PvPDifficultyEntry const* GetBattlegroundBracketByLevel(uint32 mapId, uint32 level) {
    for (auto const& entry : pvpBrackets)
        if (entry.mapId == mapId && level >= entry.minLevel && level <= entry.maxLevel) return &entry;
    return nullptr;
}
struct BattlegroundQueue {
    std::map<uint32, GroupQueueInfo> groups;
    bool GetPlayerGroupInfoData(uint32 guid, GroupQueueInfo* output) {
        auto found = groups.find(guid);
        if (found == groups.end()) return false;
        *output = found->second;
        return true;
    }
};
struct BattlegroundMgr {
    std::array<BattlegroundQueue, MAX_BATTLEGROUND_QUEUE_TYPES> queues;
    std::map<uint32, Battleground*> instances;
    static uint32 BGTemplateId(BattlegroundQueueTypeId queue) { return queue; }
    static BattlegroundQueueTypeId BGQueueTypeId(uint32 type, unsigned) { return BattlegroundQueueTypeId(type); }
    BattlegroundQueue& GetBattlegroundQueue(BattlegroundQueueTypeId queue) { return queues[queue]; }
    Battleground* GetBattleground(uint32 instance, uint32 type) {
        auto found = instances.find(instance);
        return found != instances.end() && found->second->queue == type ? found->second : nullptr;
    }
};
inline BattlegroundMgr testBattlegroundMgr;
inline BattlegroundMgr* sBattlegroundMgr = &testBattlegroundMgr;
#endif
'''
fixture = r'''
#include "BattlegroundQueuePolicy.h"
#include "EarnedBattlegroundQueueState.h"
#include "BattlegroundMgr.h"
#include <cassert>
#include <iostream>
#include <thread>
#include <barrier>

struct Config { bool earnedEraBattlegrounds = true, vanillaBattlegroundsOnly = false; } sPlayerbotAIConfig;
#define GET_PLAYERBOT_AI(player) ((player)->isBot)
bool IsSelfBot(Player* player) { return player && player->isBot && player->selfBot; }
struct QueueHooks {
''' + native_hooks + r'''
} queueHooks;
static unsigned eligibilityCalls = 0;
bool IndividualProgression_CanJoinBattleground(Player* player, uint32 type)
{
    ++eligibilityCalls;
    if (type == BATTLEGROUND_QUEUE_EY) return player->stage >= 8 && player->level >= 61;
    if (type == BATTLEGROUND_QUEUE_IC) return player->stage >= 13 && player->level >= 71;
    if (type == BATTLEGROUND_QUEUE_AV) return player->level >= 51;
    if (type == BATTLEGROUND_QUEUE_AB) return player->level >= 20;
    return type == BATTLEGROUND_QUEUE_WS && player->level >= 10;
}
uint8 IndividualProgression_BattlegroundEra(Player* player)
{
    return player->stage < 8 ? 0 : (player->stage < 13 ? 1 : 2);
}
''' + queue_recorder + r'''
PvPDifficultyEntry const* QueueBracket(Player* participant, Battleground* bg, uint8 slot,
                                       BattlegroundQueueTypeId queueTypeId, uint32 mapId)
{
''' + queue_bracket + r'''
    return getQueueBracket(participant, bg, slot, queueTypeId, mapId);
}
int main()
{
    Player player;
    for (unsigned stage = 0; stage <= 18; ++stage)
    {
        player.stage = stage;
        for (unsigned level = 1; level <= 80; ++level)
        {
            player.level = level;
            for (int q = 0; q < MAX_BATTLEGROUND_QUEUE_TYPES; ++q)
            {
                auto queue = BattlegroundQueueTypeId(q);
                bool supported = q == BATTLEGROUND_QUEUE_AV || q == BATTLEGROUND_QUEUE_WS ||
                                 q == BATTLEGROUND_QUEUE_AB || q == BATTLEGROUND_QUEUE_EY ||
                                 q == BATTLEGROUND_QUEUE_IC;
                bool legacyVanilla = q == BATTLEGROUND_QUEUE_AV || q == BATTLEGROUND_QUEUE_WS ||
                                     q == BATTLEGROUND_QUEUE_AB;
                bool earned = supported && IndividualProgression_CanJoinBattleground(&player, queue);
                eligibilityCalls = 0;
                assert(IsPlayerbotBattlegroundQueueAllowed(&player, false, true, queue) == earned);
                assert(eligibilityCalls == unsigned(supported));
                assert(IsPlayerbotBattlegroundQueueAllowed(&player, true, true, queue) == (earned && legacyVanilla));
                eligibilityCalls = 0;
                assert(IsPlayerbotBattlegroundQueueAllowed(&player, false, false, queue));
                assert(IsPlayerbotBattlegroundQueueAllowed(&player, true, false, queue) == legacyVanilla);
                assert(!eligibilityCalls);
            }
        }
        assert(GetPlayerbotBattlegroundEra(&player) == (stage < 8 ? 0 : stage < 13 ? 1 : 2));
    }
    assert(GetPlayerbotBattlegroundEra(nullptr) == 255);
    assert(!IsPlayerbotBattlegroundQueueAllowed(nullptr, false, true, BATTLEGROUND_QUEUE_WS));

    Player human, bot;
    human.stage = bot.stage = 18;
    human.level = bot.level = 80;
    bot.isBot = true;
    GroupReference botRef{&bot, nullptr}, humanRef{&human, &botRef};
    Group party{&humanRef};
    human.group = bot.group = &party;
    GroupJoinBattlegroundResult result = TEST_QUEUE_OK;
    assert(queueHooks.OnPlayerCanJoinInBattlegroundQueue(&human, {}, BATTLEGROUND_QUEUE_WS, 1, result));
    for (auto unsupported : {BATTLEGROUND_QUEUE_SA, BATTLEGROUND_QUEUE_RB})
    {
        result = TEST_QUEUE_OK;
        assert(!queueHooks.OnPlayerCanJoinInBattlegroundQueue(&human, {}, unsupported, 1, result));
        assert(result == ERR_BATTLEGROUND_JOIN_FAILED);
        assert(queueHooks.OnPlayerCanJoinInBattlegroundQueue(&human, {}, unsupported, 0, result));
    }
    assert(!queueHooks.OnPlayerCanJoinInArenaQueue(&human, {}, 0, 0, 1, 0, result));
    assert(!queueHooks.OnPlayerCanJoinInArenaQueue(&bot, {}, 0, 0, 0, 0, result));
    assert(queueHooks.OnPlayerCanJoinInArenaQueue(&human, {}, 0, 0, 0, 0, result));
    bot.isBot = false;
    assert(queueHooks.OnPlayerCanJoinInArenaQueue(&human, {}, 0, 0, 1, 0, result));
    assert(queueHooks.OnPlayerCanJoinInBattlegroundQueue(&human, {}, BATTLEGROUND_QUEUE_SA, 1, result));
    bot.isBot = true;
    bot.stage = 7;
    bot.level = 69;
    assert(!queueHooks.OnPlayerCanJoinInBattlegroundQueue(&human, {}, BATTLEGROUND_QUEUE_EY, 1, result));
    bot.stage = 8;
    assert(queueHooks.OnPlayerCanJoinInBattlegroundQueue(&human, {}, BATTLEGROUND_QUEUE_EY, 1, result));
    sPlayerbotAIConfig.earnedEraBattlegrounds = false;
    assert(queueHooks.OnPlayerCanJoinInBattlegroundQueue(&human, {}, BATTLEGROUND_QUEUE_SA, 1, result));
    assert(queueHooks.OnPlayerCanJoinInArenaQueue(&human, {}, 0, 0, 1, 0, result));
    sPlayerbotAIConfig.earnedEraBattlegrounds = true;

    // A human with SelfBot keeps human queue rights; real bots in that group still follow the bot policy.
    Player selfBot;
    selfBot.stage = 18;
    selfBot.level = 80;
    selfBot.isBot = selfBot.selfBot = true;
    for (auto queue : {BATTLEGROUND_QUEUE_SA, BATTLEGROUND_QUEUE_RB})
    {
        result = TEST_QUEUE_OK;
        assert(queueHooks.OnPlayerCanJoinInBattlegroundQueue(&selfBot, {}, queue, 0, result));
        assert(result == TEST_QUEUE_OK);
    }
    assert(queueHooks.OnPlayerCanJoinInArenaQueue(&selfBot, {}, 0, 0, 0, 0, result));
    GroupReference selfBotMemberRef{&bot, nullptr}, selfBotRef{&selfBot, &selfBotMemberRef};
    Group selfBotParty{&selfBotRef};
    selfBot.group = &selfBotParty;
    assert(!queueHooks.OnPlayerCanJoinInArenaQueue(&selfBot, {}, 0, 0, 1, 0, result));
    assert(!queueHooks.OnPlayerCanJoinInBattlegroundQueue(&selfBot, {}, BATTLEGROUND_QUEUE_SA, 1, result));
    selfBotMemberRef.player = &human;
    assert(queueHooks.OnPlayerCanJoinInArenaQueue(&selfBot, {}, 0, 0, 1, 0, result));
    assert(queueHooks.OnPlayerCanJoinInArenaQueue(&human, {}, 0, 0, 0, 0, result));
    selfBotMemberRef.player = &selfBot;
    selfBotRef.player = &human;
    human.group = &selfBotParty;
    assert(queueHooks.OnPlayerCanJoinInBattlegroundQueue(&human, {}, BATTLEGROUND_QUEUE_SA, 1, result));
    human.group = &party;

    EarnedBattlegroundQueueState state;
    constexpr uint32 q = BATTLEGROUND_QUEUE_WS, bracket = 5, size = 10;
    state.Record(q, bracket, 0, TEAM_ALLIANCE, false, true, 0);
    assert(state.NeedsPlayer(q, bracket, 0, TEAM_ALLIANCE, size));
    assert(state.NeedsPlayer(q, bracket, 0, TEAM_HORDE, size));
    assert(!state.NeedsPlayer(q, bracket, 1, TEAM_ALLIANCE, size));
    assert(!state.NeedsPlayer(q, bracket, 2, TEAM_ALLIANCE, size));
    assert(!state.NeedsPlayer(q, bracket + 1, 0, TEAM_ALLIANCE, size));
    assert(!state.NeedsPlayer(BATTLEGROUND_QUEUE_AB, bracket, 0, TEAM_ALLIANCE, size));
    state.Record(q, bracket, 1, TEAM_HORDE, false, true, 0);
    assert(!state.TryReserve(q, bracket, 0, TEAM_ALLIANCE, 10, size));
    assert(state.NeedsPlayer(q, bracket, 0, TEAM_ALLIANCE, size));
    assert(state.TryReserve(q, bracket, 0, TEAM_ALLIANCE, 9, size));
    assert(!state.NeedsPlayer(q, bracket, 0, TEAM_ALLIANCE, size));
    assert(state.NeedsPlayer(q, bracket, 1, TEAM_ALLIANCE, size));
    assert(state.NeedsPlayer(q, bracket, 0, TEAM_HORDE, size));
    assert(state.TryReserve(q, bracket, 0, TEAM_HORDE, 10, size));
    assert(!state.NeedsPlayer(q, bracket, 0, TEAM_HORDE, size));

    EarnedBattlegroundQueueState instances;
    instances.Record(q, bracket, 2, TEAM_ALLIANCE, false, false, 123);
    instances.Record(q, bracket, 2, TEAM_HORDE, false, false, 123);
    assert(instances.TryReserve(q, bracket, 2, TEAM_ALLIANCE, 9, size));
    assert(!instances.NeedsPlayer(q, bracket, 2, TEAM_ALLIANCE, size));
    instances.Record(q, bracket, 2, TEAM_ALLIANCE, false, false, 124);
    assert(instances.NeedsPlayer(q, bracket, 2, TEAM_ALLIANCE, size));
    assert(instances.TryReserve(q, bracket, 2, TEAM_ALLIANCE, 9, size));
    assert(!instances.NeedsPlayer(q, bracket, 2, TEAM_ALLIANCE, size));

    EarnedBattlegroundQueueState botsOnly;
    botsOnly.Record(q, bracket, 2, TEAM_ALLIANCE, true, true, 0);
    assert(!botsOnly.NeedsPlayer(q, bracket, 2, TEAM_HORDE, size));
    for (uint32 invalid : {uint32(MAX_BATTLEGROUND_QUEUE_TYPES), uint32(999999)})
    {
        state.Record(invalid, bracket, 0, TEAM_ALLIANCE, false, true, 0);
        assert(!state.TryReserve(invalid, bracket, 0, TEAM_ALLIANCE, 3, size));
        assert(!state.NeedsPlayer(invalid, bracket, 0, TEAM_ALLIANCE, size));
    }
    for (uint8 era : {uint8(3), uint8(255)})
    {
        state.Record(q, bracket, era, TEAM_ALLIANCE, false, true, 0);
        assert(!state.NeedsPlayer(q, bracket, era, TEAM_ALLIANCE, size));
    }
    state.Record(q, MAX_BATTLEGROUND_BRACKETS, 0, TEAM_ALLIANCE, false, true, 0);
    assert(!state.NeedsPlayer(q, MAX_BATTLEGROUND_BRACKETS, 0, TEAM_ALLIANCE, size));
    state.Record(q, bracket, 0, TEAM_NEUTRAL, false, true, 0);
    assert(!state.NeedsPlayer(q, bracket, 0, TEAM_NEUTRAL, size));

    EarnedBattlegroundQueueState concurrent;
    concurrent.Record(q, bracket, 2, TEAM_ALLIANCE, false, true, 0);
    std::array<std::thread, 8> workers;
    for (auto& thread : workers)
        thread = std::thread([&] {
            for (unsigned i = 0; i != 2000; ++i)
            {
                assert(concurrent.TryReserve(q, bracket, 2, TEAM_HORDE, 1, 16000));
                concurrent.NeedsPlayer(q, bracket, 2, TEAM_HORDE, 16000);
            }
        });
    for (auto& thread : workers) thread.join();
    assert(!concurrent.NeedsPlayer(q, bracket, 2, TEAM_HORDE, 16000));
    assert(concurrent.NeedsPlayer(q, bracket, 2, TEAM_HORDE, 16001));
    assert(!concurrent.TryReserve(q, bracket, 2, TEAM_HORDE, 1, 16000));
    assert(!concurrent.TryReserve(q, bracket, 2, TEAM_HORDE, 0, 16000));

    // One player occupies WS while also waiting for AB. That WS instance must not
    // create a second AB match capacity when another human is waiting for AB.
    EarnedBattlegroundQueueState heldQueues;
    Battleground wsMatch{BATTLEGROUND_QUEUE_WS, 42, STATUS_IN_PROGRESS};
    Player wsAndAb, waitingAb;
    wsAndAb.guid = 1;
    wsAndAb.battleground = &wsMatch;
    waitingAb.guid = 2;
    testBattlegroundMgr.queues[BATTLEGROUND_QUEUE_AB].groups.emplace(1, GroupQueueInfo{});
    testBattlegroundMgr.queues[BATTLEGROUND_QUEUE_AB].groups.emplace(2, GroupQueueInfo{});
    RecordEarnedBattlegroundQueue(heldQueues, &wsAndAb, BATTLEGROUND_QUEUE_WS, bracket);
    RecordEarnedBattlegroundQueue(heldQueues, &wsAndAb, BATTLEGROUND_QUEUE_AB, bracket);
    RecordEarnedBattlegroundQueue(heldQueues, &waitingAb, BATTLEGROUND_QUEUE_AB, bracket);
    assert(heldQueues.TryReserve(BATTLEGROUND_QUEUE_WS, bracket, 0, TEAM_HORDE, 10, 10));
    assert(!heldQueues.TryReserve(BATTLEGROUND_QUEUE_WS, bracket, 0, TEAM_HORDE, 1, 10));
    assert(!heldQueues.TryReserve(BATTLEGROUND_QUEUE_AB, bracket, 0, TEAM_HORDE, 16, 15));
    assert(heldQueues.TryReserve(BATTLEGROUND_QUEUE_AB, bracket, 0, TEAM_HORDE, 15, 15));
    assert(!heldQueues.NeedsPlayer(BATTLEGROUND_QUEUE_AB, bracket, 0, TEAM_HORDE, 15));

    EarnedBattlegroundQueueState invitedQueues;
    Battleground abMatch{BATTLEGROUND_QUEUE_AB, 43, STATUS_WAIT_JOIN};
    testBattlegroundMgr.instances.emplace(43, &abMatch);
    testBattlegroundMgr.queues[BATTLEGROUND_QUEUE_AB].groups[1].IsInvitedToBGInstanceGUID = 43;
    RecordEarnedBattlegroundQueue(invitedQueues, &wsAndAb, BATTLEGROUND_QUEUE_AB, bracket);
    assert(invitedQueues.TryReserve(BATTLEGROUND_QUEUE_AB, bracket, 0, TEAM_HORDE, 15, 15));
    assert(!invitedQueues.TryReserve(BATTLEGROUND_QUEUE_AB, bracket, 0, TEAM_HORDE, 1, 15));
    EarnedBattlegroundQueueState endedQueues;
    abMatch.status = STATUS_WAIT_LEAVE;
    RecordEarnedBattlegroundQueue(endedQueues, &wsAndAb, BATTLEGROUND_QUEUE_AB, bracket);
    assert(!endedQueues.NeedsPlayer(BATTLEGROUND_QUEUE_AB, bracket, 0, TEAM_HORDE, 15));
    EarnedBattlegroundQueueState missingQueues;
    testBattlegroundMgr.instances.erase(43);
    RecordEarnedBattlegroundQueue(missingQueues, &wsAndAb, BATTLEGROUND_QUEUE_AB, bracket);
    assert(!missingQueues.NeedsPlayer(BATTLEGROUND_QUEUE_AB, bracket, 0, TEAM_HORDE, 15));
    wsAndAb.battleground = nullptr;
    RecordEarnedBattlegroundQueue(missingQueues, &wsAndAb, BATTLEGROUND_QUEUE_WS, bracket);
    assert(!missingQueues.NeedsPlayer(BATTLEGROUND_QUEUE_WS, bracket, 0, TEAM_HORDE, 10));

    // Account bots live in the non-random player list; headless sessions must
    // occupy queue slots without being mistaken for a real human opening a match.
    EarnedBattlegroundQueueState accountOnly;
    Player accountBot;
    accountBot.guid = 3;
    accountBot.isBot = true;
    accountBot.session.headless = true;
    testBattlegroundMgr.queues[BATTLEGROUND_QUEUE_AB].groups.emplace(3, GroupQueueInfo{});
    RecordEarnedBattlegroundQueue(accountOnly, &accountBot, BATTLEGROUND_QUEUE_AB, bracket);
    assert(!accountOnly.NeedsPlayer(BATTLEGROUND_QUEUE_AB, bracket, 0, TEAM_HORDE, 15));
    assert(!accountOnly.TryReserve(BATTLEGROUND_QUEUE_AB, bracket, 0, TEAM_HORDE, 1, 15));
    RecordEarnedBattlegroundQueue(accountOnly, &waitingAb, BATTLEGROUND_QUEUE_AB, bracket);
    assert(accountOnly.TryReserve(BATTLEGROUND_QUEUE_AB, bracket, 0, TEAM_ALLIANCE, 13, 15));
    assert(!accountOnly.TryReserve(BATTLEGROUND_QUEUE_AB, bracket, 0, TEAM_ALLIANCE, 1, 15));

    // Census brackets come from the queue or instance, not from a level gained while waiting.
    Player leveled;
    leveled.guid = 20;
    leveled.level = 30;
    testBattlegroundMgr.queues[BATTLEGROUND_QUEUE_WS].groups[20].BracketId = 1;
    assert(GetBattlegroundBracketByLevel(489, leveled.level)->GetBracketId() == 2);
    assert(QueueBracket(&leveled, nullptr, 0, BATTLEGROUND_QUEUE_WS, 489)->GetBracketId() == 1);
    Battleground leveledMatch{BATTLEGROUND_QUEUE_WS, 50, STATUS_IN_PROGRESS};
    leveled.inBattleground = true;
    assert(QueueBracket(&leveled, &leveledMatch, 0, BATTLEGROUND_QUEUE_WS, 489)->GetBracketId() == 0);
    assert(!QueueBracket(&leveled, nullptr, 0, BATTLEGROUND_QUEUE_WS, 489));
    leveled.queueSlot = 1;
    assert(QueueBracket(&leveled, &leveledMatch, 0, BATTLEGROUND_QUEUE_WS, 489)->GetBracketId() == 1);
    testBattlegroundMgr.queues[BATTLEGROUND_QUEUE_WS].groups.erase(20);
    assert(!QueueBracket(&leveled, &leveledMatch, 0, BATTLEGROUND_QUEUE_WS, 489));

    // A match whose map is still being created keeps counting the participants who entered it.
    EarnedBattlegroundQueueState starting;
    Battleground pending{BATTLEGROUND_QUEUE_AB, 60, STATUS_WAIT_JOIN};
    pending.mapCreated = false;
    Player entered;
    entered.guid = 21;
    entered.battleground = &pending;
    RecordEarnedBattlegroundQueue(starting, &entered, BATTLEGROUND_QUEUE_AB, bracket);
    assert(starting.NeedsPlayer(BATTLEGROUND_QUEUE_AB, bracket, 0, TEAM_HORDE, 15));

    EarnedBattlegroundQueueState contested;
    contested.Record(q, bracket, 0, TEAM_ALLIANCE, false, true, 0);
    std::atomic<unsigned> claimed = 0;
    std::barrier ready(8);
    for (auto& thread : workers)
        thread = std::thread([&] {
            assert(contested.NeedsPlayer(q, bracket, 0, TEAM_HORDE, 1));
            ready.arrive_and_wait();
            if (contested.TryReserve(q, bracket, 0, TEAM_HORDE, 1, 1)) ++claimed;
        });
    for (auto& thread : workers) thread.join();
    assert(claimed == 1);
    assert(!contested.NeedsPlayer(q, bracket, 0, TEAM_HORDE, 1));
    assert(!contested.TryReserve(q, bracket, 0, TEAM_HORDE, 1, 1));
    std::cout << "Earned bot queue matrices and era-isolated concurrent filler counts passed.\n";
}
'''
missing = r'''
#include "BattlegroundQueuePolicy.h"
#include <cassert>
int main() {
    Player player;
    assert(!IsPlayerbotBattlegroundQueueAllowed(&player, false, true, BATTLEGROUND_QUEUE_WS));
    assert(IsPlayerbotBattlegroundQueueAllowed(&player, false, false, BATTLEGROUND_QUEUE_WS));
    assert(GetPlayerbotBattlegroundEra(&player) == 255);
}
'''
with tempfile.TemporaryDirectory(prefix='portable-bot-era-bg-') as temporary:
    tmp = Path(temporary)
    for file in ('BattlegroundQueuePolicy.h', 'BattlegroundQueuePolicy.cpp', 'EarnedBattlegroundQueueState.h'):
        shutil.copyfile(pb / file, tmp / file)
    (tmp / 'SharedDefines.h').write_text(shared)
    (tmp / 'BattlegroundMgr.h').write_text(bgmgr)
    (tmp / 'IndividualProgressionBattlegrounds.h').write_text(
        '#include "SharedDefines.h"\n'
        'bool IndividualProgression_CanJoinBattleground(Player*, uint32);\n'
        'uint8 IndividualProgression_BattlegroundEra(Player*);\n')
    (tmp / 'fixture.cpp').write_text(fixture)
    executable = tmp / 'fixture'
    command = [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-pedantic', '-pthread',
               '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie',
               '-I', str(tmp), str(tmp / 'fixture.cpp'), str(tmp / 'BattlegroundQueuePolicy.cpp'), '-o', str(executable)]
    subprocess.run(command, check=True)
    subprocess.run([str(executable)], check=True, timeout=TIMEOUT)
    mutations = [
        ('SelfBot humans use the bot queue policy', '!GET_PLAYERBOT_AI(member) || IsSelfBot(member) ||',
         '!GET_PLAYERBOT_AI(member) ||'),
        ('group members skip the bot queue policy', 'if (!allowed(ref->GetSource()))', 'if (false)'),
        ('queued bracket follows current level', 'GetBattlegroundBracketById(mapId, BattlegroundBracketId(groupInfo.BracketId))',
         'GetBattlegroundBracketByLevel(mapId, participant->GetLevel())'),
        ('instance bracket used for another queue slot', 'participant->GetCurrentBattlegroundQueueSlot() == slot',
         'participant->GetCurrentBattlegroundQueueSlot() <= slot + 1u'),
        ('starting match ignored', 'Battleground* active = player->GetBattleground(true);',
         'Battleground* active = player->GetBattleground();'),
    ]
    for label, old, new in mutations:
        mutated = fixture.replace(old, new)
        if mutated == fixture:
            raise SystemExit(f'{label} mutation was not applied')
        (tmp / 'fixture.cpp').write_text(mutated)
        subprocess.run(command, check=True)
        if subprocess.run([str(executable)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=TIMEOUT).returncode == 0:
            raise SystemExit(f'Bot queue fixture did not reject: {label}')
        print(f'Bot queue mutation rejected: {label}')
    (tmp / 'IndividualProgressionBattlegrounds.h').unlink()
    (tmp / 'fixture.cpp').write_text(missing)
    subprocess.run(command, check=True)
    subprocess.run([str(executable)], check=True, timeout=TIMEOUT)
print('Missing progression module fails closed; legacy queue policy remains unchanged.')
