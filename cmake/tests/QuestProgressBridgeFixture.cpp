// Test world producers; TestQuestProgressBridge.py inserts the actual bridge logic.
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cctype>
#include <cstdint>
#include <cstring>
#include <deque>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

using uint8 = std::uint8_t;
using uint16 = std::uint16_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
using int32 = std::int32_t;
using int64 = std::int64_t;
using ChatMsg = int;
constexpr ChatMsg CHAT_MSG_WHISPER = 7;
constexpr uint32 PLAYERBOT_SECURITY_ALLOW_ALL = 0;
constexpr char kFieldSeparator = '~';
constexpr char const* kAddonEnvelope = "MBOT\t";
constexpr std::size_t kMaxBridgeWireLength = 255;
constexpr std::size_t kMaxTokenLength = 64;
constexpr std::size_t kMaxBotNameLength = 64;

@NATIVE_QUEST@

struct ObjectGuid
{
    uint64 _guid = 0;
    auto operator<=>(ObjectGuid const&) const = default;
    explicit operator bool() const { return _guid != 0; }
    uint32 GetCounter() const { return static_cast<uint32>(_guid); }
    bool HasEntry() const { return false; }
    bool IsPet() const { return false; }
    uint32 GetEntry() const { return 0; }
    char const* GetTypeName() const { return "Player"; }
    std::string ToString() const;
};

class Player;
struct Group
{
    std::set<ObjectGuid> members;
    bool IsMember(ObjectGuid guid) const { return members.contains(guid); }
};
struct WorldSession
{
    bool loggingOut = false;
    bool socketClosed = false;
    bool PlayerLogout() const { return loggingOut; }
    bool IsSocketClosed() const { return socketClosed; }
};
struct ReputationMgr
{
    std::map<uint32, int32> reputations;
    int32 GetReputation(uint32 faction) const
    {
        auto const found = reputations.find(faction);
        return found == reputations.end() ? 0 : found->second;
    }
};
struct Quest
{
    uint32 RequiredItemId[QUEST_ITEM_OBJECTIVES_COUNT]{};
    uint32 RequiredItemCount[QUEST_ITEM_OBJECTIVES_COUNT]{};
    int32 RequiredNpcOrGo[QUEST_OBJECTIVES_COUNT]{};
    uint32 RequiredNpcOrGoCount[QUEST_OBJECTIVES_COUNT]{};
    uint32 RequiredPlayerKills = 0;
    uint32 SpecialFlags = 0;
    uint32 RequiredFactionId1 = 0;
    int32 RequiredFactionValue1 = 0;
    uint32 RequiredFactionId2 = 0;
    int32 RequiredFactionValue2 = 0;
    int32 RewardMoney = 0;
    bool HasSpecialFlag(uint32 flags) const { return (SpecialFlags & flags) != 0; }
    uint32 GetPlayersSlain() const { return RequiredPlayerKills; }
    int32 GetRewOrReqMoney(uint8 = 0) const { return RewardMoney; }
    uint32 GetRepObjectiveFaction() const { return RequiredFactionId1; }
    int32 GetRepObjectiveValue() const { return RequiredFactionValue1; }
    uint32 GetRepObjectiveFaction2() const { return RequiredFactionId2; }
    int32 GetRepObjectiveValue2() const { return RequiredFactionValue2; }
};
struct ObjectMgr
{
    std::map<uint32, Quest> quests;
    Quest const* GetQuestTemplate(uint32 id) const
    {
        auto const found = quests.find(id);
        return found == quests.end() ? nullptr : &found->second;
    }
} objectMgr;
auto* sObjectMgr = &objectMgr;

struct Security
{
    bool allowed = true;
    bool CheckLevelFor(uint32, bool, Player*) const { return allowed; }
};
struct PlayerbotAI
{
    Security security;
    Player* master = nullptr;
    Security* GetSecurity() { return &security; }
    Player* GetMaster() const { return master; }
};
class Player
{
public:
    ObjectGuid guid;
    std::string name;
    Group* group = nullptr;
    WorldSession session;
    bool online = true;
    bool connected = true;
    bool teleporting = false;
    PlayerbotAI* ai = nullptr;
    std::array<uint32, MAX_QUEST_LOG_SIZE> questSlots{};
    std::map<uint32, QuestStatusData> quests;
    uint32 questLogReads = 0;
    uint32 money = 0;
    ReputationMgr reputation;
    ObjectGuid GetGUID() const { return guid; }
    std::string const& GetName() const { return name; }
    Group* GetGroup() const { return group; }
    WorldSession* GetSession() { return &session; }
    bool IsInWorld() const { return online; }
    bool IsBeingTeleported() const { return teleporting; }
    uint32 GetQuestSlotQuestId(uint16 slot) const { return questSlots.at(slot); }
    auto& getQuestStatusMap() { ++questLogReads; return quests; }
    uint32 GetMoney() const { return money; }
    ReputationMgr& GetReputationMgr() { return reputation; }
};
std::map<ObjectGuid, Player*> worldPlayers;
namespace ObjectAccessor
{
Player* FindPlayer(ObjectGuid guid)
{
    auto const found = worldPlayers.find(guid);
    return found == worldPlayers.end() || !found->second->connected || !found->second->online ? nullptr : found->second;
}
Player* FindConnectedPlayer(ObjectGuid guid)
{
    auto const found = worldPlayers.find(guid);
    return found == worldPlayers.end() || !found->second->connected ? nullptr : found->second;
}
}
struct PlayerbotsMgr
{
    PlayerbotAI* GetPlayerbotAI(Player* player) const { return player ? player->ai : nullptr; }
} sPlayerbotsMgr;
std::vector<Player*> visibleBots;
std::vector<Player*> GetBridgeVisibleBots(Player*)
{
    return visibleBots;
}
#define GET_PLAYERBOT_AI(player) sPlayerbotsMgr.GetPlayerbotAI(player)

struct SentPacket
{
    ObjectGuid recipient;
    ChatMsg distribution;
    std::string opcode;
    std::string payload;
};
std::vector<SentPacket> sentPackets;
bool SendStateAddonPacket(Player* requester, ChatMsg distribution, std::string const& opcode,
    std::string const& payload)
{
    assert(requester && requester->GetSession());
    assert(std::strlen(kAddonEnvelope) + opcode.size() + (payload.empty() ? 0 : payload.size() + 1)
        <= kMaxBridgeWireLength);
    sentPackets.push_back({requester->GetGUID(), distribution, opcode, payload});
    return true;
}
void SendAddonPacket(Player* requester, ChatMsg distribution, std::string const& opcode,
    std::string const& payload = "")
{
    SendStateAddonPacket(requester, distribution, opcode, payload);
}
bool SendProtocolError(Player* requester, ChatMsg distribution, std::string const& opcode,
    std::string const& type, std::string const& token, std::string const& reason)
{
    SendAddonPacket(requester, distribution, "ERR", opcode + "~" + type + "~" + token + "~" + reason);
    return true;
}

@PRODUCTION@

bool HasPacket(ObjectGuid recipient, std::string const& opcode, std::string const& payload)
{
    return std::any_of(sentPackets.begin(), sentPackets.end(), [&](SentPacket const& packet)
    {
        return packet.recipient == recipient && packet.opcode == opcode && packet.payload == payload;
    });
}

void ExpectError(std::string const& reason)
{
    assert(sentPackets.size() == 1);
    assert(sentPackets.front().opcode == "ERR");
    assert(sentPackets.front().payload.ends_with("~" + reason));
    sentPackets.clear();
}

void AllowNextRequest(Player& owner, Player& bot)
{
    questProgressRequesters.at(owner.GetGUID()).lastRequests.erase(bot.GetGUID());
    sentPackets.clear();
}

void ExpectEmptySnapshot(Player& owner, Player& bot, std::string const& token)
{
    assert(sentPackets.size() == 2);
    assert(HasPacket(owner.guid, "QUEST_PROGRESS_BEGIN", bot.name + "~" + token + "~" + bot.guid.ToString()));
    assert(HasPacket(owner.guid, "QUEST_PROGRESS_END", bot.name + "~" + token));
    assert(questProgressRequesters.at(owner.guid).watches.empty());
    sentPackets.clear();
}

int main()
{
    Group group, otherGroup;
    Player owner, tank, mage, human, outsider;
    owner.guid = {1}; owner.name = "Owner"; owner.group = &group;
    tank.guid = {2}; tank.name = "Tankbot"; tank.group = &group;
    mage.guid = {3}; mage.name = "Magebot"; mage.group = &group;
    human.guid = {4}; human.name = "Human"; human.group = &group;
    outsider.guid = {5}; outsider.name = "Outsider"; outsider.group = &otherGroup;
    PlayerbotAI tankAI, mageAI, outsideAI;
    tank.ai = &tankAI; mage.ai = &mageAI; outsider.ai = &outsideAI;
    // Headless bots have no socket. Only the human viewer needs an open one.
    tank.session.socketClosed = mage.session.socketClosed = outsider.session.socketClosed = true;
    for (Player* player : {&owner, &tank, &mage, &human, &outsider})
        worldPlayers[player->guid] = player;
    // The native visible-bot list can contain the owner's ungrouped altbots.
    visibleBots = {&tank, &mage, &outsider};
    auto& quest = objectMgr.quests[100];
    quest.RequiredNpcOrGo[0] = 1001; quest.RequiredNpcOrGoCount[0] = 10;
    quest.RequiredNpcOrGo[1] = -2002; quest.RequiredNpcOrGoCount[1] = 4;
    quest.RequiredNpcOrGo[2] = 3003; quest.RequiredNpcOrGoCount[2] = 5;
    quest.RequiredItemId[0] = 4004; quest.RequiredItemCount[0] = 8;
    quest.RequiredPlayerKills = 6;
    quest.SpecialFlags = QUEST_SPECIAL_FLAGS_EXPLORATION_OR_EVENT;
    quest.RewardMoney = -5000;
    quest.RequiredFactionId1 = 72; quest.RequiredFactionValue1 = 3000;
    tank.questSlots[0] = 100;
    auto& progress = tank.quests[100];
    progress.Status = QUEST_STATUS_INCOMPLETE;
    progress.CreatureOrGOCount[0] = 8;
    progress.CreatureOrGOCount[1] = 2;
    progress.CreatureOrGOCount[2] = 3;
    progress.ItemCount[0] = 6;
    progress.PlayerCount = 4;
    tank.money = 4321;
    tank.reputation.reputations[72] = -100;
    auto snapshot = BuildQuestProgressSnapshot(&tank);
    assert(snapshot.size() == 1 && snapshot[0].id == 100 && snapshot[0].status == 'I');
    assert(snapshot[0].objectives.size() == 8);
    std::vector<QuestProgressObjectiveData> const expected = {
        {'m', 1, 1001, 8, 10, false}, {'o', 2, 2002, 2, 4, false},
        {'m', 3, 3003, 3, 5, false}, {'i', 4, 4004, 6, 8, false},
        {'p', 5, 0, 4, 6, false}, {'e', 6, 0, 0, 1, false},
        {'g', 7, 0, 4321, 5000, false}, {'r', 8, 72, -100, 3000, false},
    };
    assert(snapshot[0].objectives == expected);
    // Missing templates, orphaned status rows and rewarded quests are not active log entries.
    tank.quests[101].Status = QUEST_STATUS_INCOMPLETE;
    tank.questSlots[1] = 102;
    tank.quests[102].Status = QUEST_STATUS_INCOMPLETE;
    tank.questSlots[2] = 103;
    objectMgr.quests[103] = Quest{};
    tank.quests[103].Status = QUEST_STATUS_REWARDED;
    assert(BuildQuestProgressSnapshot(&tank) == snapshot);
    progress.Status = QUEST_STATUS_COMPLETE;
    assert(BuildQuestProgressSnapshot(&tank)[0].status == 'C');
    progress.Status = QUEST_STATUS_FAILED;
    assert(BuildQuestProgressSnapshot(&tank)[0].status == 'F');
    progress.Status = QUEST_STATUS_INCOMPLETE;

    auto packets = BuildQuestProgressPackets("T~a%nk", "qpb1", tank.guid, snapshot);
    assert(packets.front() == std::make_pair(std::string("QUEST_PROGRESS_BEGIN"),
        std::string("T%7Ea%25nk~qpb1~GUID Full: 0x0000000000000002 Type: Player Low: 2")));
    assert(packets[1] == std::make_pair(std::string("QUEST_PROGRESS_QUEST"), std::string("T%7Ea%25nk~qpb1~100~I")));
    assert(packets[2] == std::make_pair(std::string("QUEST_PROGRESS_OBJECTIVE"), std::string("T%7Ea%25nk~qpb1~100~m~1~1001~8~10~0")));
    assert(packets.back() == std::make_pair(std::string("QUEST_PROGRESS_END"), std::string("T%7Ea%25nk~qpb1")));
    assert(packets.size() == 11);
    assert(BuildQuestProgressPackets("Palad\xC3\xADn", "qpb2", tank.guid, snapshot).size() == 11);
    assert(BuildQuestProgressPackets(std::string(64, '~'), std::string(64, 'x'), tank.guid, snapshot).empty());
    assert(!SendQuestProgressSnapshot(&owner, CHAT_MSG_WHISPER, std::string(64, '~'), std::string(64, 'x'), tank.guid, snapshot));
    ExpectError("PACKET_TOO_LARGE");
    // Even when BEGIN fits, a later oversized objective must prevent all data packets.
    std::string const budgetName(48, '~'), budgetToken(16, 'x');
    assert(IsAddonPacketWithinBudget("QUEST_PROGRESS_BEGIN",
        UrlEncodeField(budgetName) + "~" + budgetToken + "~" + tank.guid.ToString()));
    QuestProgressSnapshot const oversized = {{std::numeric_limits<uint32>::max(), 'I',
        {{'r', std::numeric_limits<uint32>::max(), std::numeric_limits<uint32>::max(),
          std::numeric_limits<int64>::max(), std::numeric_limits<int64>::max(), true}}}};
    assert(!SendQuestProgressSnapshot(&owner, CHAT_MSG_WHISPER, budgetName, budgetToken, tank.guid, oversized));
    ExpectError("PACKET_TOO_LARGE");

    // Widening before negation handles an unusual signed GO template safely.
    quest.RequiredNpcOrGo[1] = std::numeric_limits<int32>::min();
    assert(BuildQuestProgressSnapshot(&tank)[0].objectives[1].id == 2147483648u);
    quest.RequiredNpcOrGo[1] = -2002;

    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Tankbot", "qpb1", "WATCH"}));
    assert(sentPackets.size() == 11 && questProgressRequesters.at(owner.guid).watches.size() == 1);
    assert(std::all_of(sentPackets.begin(), sentPackets.end(), [](SentPacket const& packet)
        { return packet.distribution == CHAT_MSG_WHISPER; }));
    sentPackets.clear();
    progress.CreatureOrGOCount[0] = 9;
    UpdateQuestProgress(999);
    assert(sentPackets.empty());
    UpdateQuestProgress(1);
    assert(HasPacket(owner.guid, "QUEST_PROGRESS_OBJECTIVE", "Tankbot~qpb1~100~m~1~1001~9~10~0"));
    sentPackets.clear();
    progress.Explored = true;
    UpdateQuestProgress(1000);
    assert(HasPacket(owner.guid, "QUEST_PROGRESS_OBJECTIVE", "Tankbot~qpb1~100~m~1~1001~9~10~0"));
    assert(HasPacket(owner.guid, "QUEST_PROGRESS_OBJECTIVE", "Tankbot~qpb1~100~e~6~0~1~1~1"));
    sentPackets.clear();
    UpdateQuestProgress(1000);
    assert(sentPackets.empty());

    mage.questSlots[0] = 100;
    mage.quests[100] = progress;
    mage.quests[100].CreatureOrGOCount[0] = 4;
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Magebot", "qpb2", "WATCH"}));
    assert(HasPacket(owner.guid, "QUEST_PROGRESS_OBJECTIVE", "Magebot~qpb2~100~m~1~1001~4~10~0"));
    sentPackets.clear();
    progress.CreatureOrGOCount[0] = 10;
    progress.Status = QUEST_STATUS_COMPLETE;
    mage.quests[100].CreatureOrGOCount[0] = 5;
    UpdateQuestProgress(1000);
    assert(HasPacket(owner.guid, "QUEST_PROGRESS_QUEST", "Tankbot~qpb1~100~C"));
    assert(HasPacket(owner.guid, "QUEST_PROGRESS_OBJECTIVE", "Tankbot~qpb1~100~m~1~1001~10~10~1"));
    assert(HasPacket(owner.guid, "QUEST_PROGRESS_OBJECTIVE", "Magebot~qpb2~100~m~1~1001~5~10~0"));
    sentPackets.clear();
    // Turn-in or abandon removes the log slot; the status map can retain its row.
    tank.questSlots[0] = 0;
    UpdateQuestProgress(1000);
    assert(sentPackets.size() == 2 && sentPackets[0].opcode == "QUEST_PROGRESS_BEGIN"
        && sentPackets[1].opcode == "QUEST_PROGRESS_END");
    sentPackets.clear();
    tank.questSlots[0] = 100;
    UpdateQuestProgress(1000);
    assert(HasPacket(owner.guid, "QUEST_PROGRESS_QUEST", "Tankbot~qpb1~100~C"));

    // New reload tokens replace a subscription; stale UNWATCH cannot remove it.
    AllowNextRequest(owner, tank);
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Tankbot", "reloaded", "WATCH"}));
    assert(questProgressRequesters.at(owner.guid).watches.at(tank.guid).token == "reloaded");
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Tankbot", "qpb1", "UNWATCH"}));
    assert(questProgressRequesters.at(owner.guid).watches.contains(tank.guid));
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Tankbot", "reloaded", "UNWATCH"}));
    assert(!questProgressRequesters.at(owner.guid).watches.contains(tank.guid));
    AllowNextRequest(owner, tank);
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Tankbot", "new", "WATCH"}));
    sentPackets.clear();
    mage.online = false;
    UpdateQuestProgress(1000);
    assert(sentPackets.size() == 2 && !questProgressRequesters.at(owner.guid).watches.contains(mage.guid));
    mage.online = true;

    // A second real viewer gets its own token and independent authoritative log.
    sentPackets.clear();
    assert(DispatchQuestProgress(&human, {"QUEST_PROGRESS", "Tankbot", "human1", "WATCH"}));
    sentPackets.clear();
    progress.Status = QUEST_STATUS_FAILED;
    uint32 const readsBefore = tank.questLogReads;
    UpdateQuestProgress(1000);
    assert(tank.questLogReads == readsBefore + 1);
    assert(HasPacket(owner.guid, "QUEST_PROGRESS_QUEST", "Tankbot~new~100~F"));
    assert(HasPacket(human.guid, "QUEST_PROGRESS_QUEST", "Tankbot~human1~100~F"));
    sentPackets.clear();
    human.connected = false;
    UpdateQuestProgress(1000);
    assert(!questProgressRequesters.contains(human.guid));
    human.connected = true;

    tank.group = &otherGroup;
    UpdateQuestProgress(1000);
    ExpectEmptySnapshot(owner, tank, "new");
    tank.group = &group;
    AllowNextRequest(owner, tank);
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Tankbot", "access", "WATCH"}));
    sentPackets.clear();
    tankAI.security.allowed = false;
    UpdateQuestProgress(1000);
    ExpectEmptySnapshot(owner, tank, "access");
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Tankbot", "denied", "WATCH"}));
    ExpectError("BOT_UNAVAILABLE");
    tankAI.security.allowed = true;
    AllowNextRequest(owner, tank);
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Tankbot", "offline", "WATCH"}));
    sentPackets.clear();
    tank.online = false;
    UpdateQuestProgress(1000);
    ExpectEmptySnapshot(owner, tank, "offline");
    tank.online = true;

    AllowNextRequest(owner, tank);
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Tankbot", "visibility", "WATCH"}));
    sentPackets.clear();
    visibleBots = {&mage, &outsider};
    UpdateQuestProgress(1000);
    ExpectEmptySnapshot(owner, tank, "visibility");
    visibleBots.push_back(&tank);

    // Group and real-client checks are independent of bridge visibility.
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Outsider", "outside", "WATCH"}));
    ExpectError("BOT_UNAVAILABLE");
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Human", "human", "WATCH"}));
    ExpectError("BOT_UNAVAILABLE");
    assert(!CanObserveQuestProgress(&owner, &human));
    tankAI.master = &tank;
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Tankbot", "self", "WATCH"}));
    ExpectError("BOT_UNAVAILABLE");
    tankAI.master = nullptr;
    assert(!CanObserveQuestProgress(&owner, &owner));

    for (auto const& [fields, reason] : std::vector<std::pair<std::vector<std::string>, std::string>>{
        {{"QUEST_PROGRESS"}, "BAD_FIELD_COUNT"},
        {{"QUEST_PROGRESS", "Tankbot", "x", "WATCH", "extra"}, "BAD_FIELD_COUNT"},
        {{"QUEST_PROGRESS", "", "x"}, "BAD_BOT_NAME"},
        {{"QUEST_PROGRESS", " Tankbot", "x"}, "BAD_BOT_NAME"},
        {{"QUEST_PROGRESS", "Tankbot\n", "x"}, "BAD_BOT_NAME"},
        {{"QUEST_PROGRESS", std::string(65, 'x'), "x"}, "BAD_BOT_NAME"},
        {{"QUEST_PROGRESS", "Tankbot", ""}, "BAD_TOKEN"},
        {{"QUEST_PROGRESS", "Tankbot", std::string(65, 'x')}, "BAD_TOKEN"},
        {{"QUEST_PROGRESS", "Tankbot", "bad%00"}, "BAD_TOKEN"},
        {{"QUEST_PROGRESS", "Tankbot", "x", "RUN"}, "BAD_MODE"},
    })
    {
        assert(DispatchQuestProgress(&owner, fields));
        ExpectError(reason);
    }

    AllowNextRequest(owner, tank);
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Tankbot", "lease", "WATCH"}));
    sentPackets.clear();
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Tankbot", "too-fast", "WATCH"}));
    ExpectError("RATE_LIMIT");
    questProgressRequesters.at(owner.guid).watches.at(tank.guid).expires = QuestProgressClock::now() - std::chrono::seconds(1);
    UpdateQuestProgress(1000);
    ExpectEmptySnapshot(owner, tank, "lease");
    AllowNextRequest(owner, tank);
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Tankbot", "logout", "WATCH"}));
    sentPackets.clear();
    tank.online = false;
    UpdateQuestProgress(1000);
    ExpectEmptySnapshot(owner, tank, "logout");
    tank.online = true;
    AllowNextRequest(owner, tank);
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Tankbot", "gone", "WATCH"}));
    sentPackets.clear();
    owner.online = false;
    UpdateQuestProgress(1000);
    assert(questProgressRequesters.at(owner.guid).watches.contains(tank.guid) && sentPackets.empty());
    owner.online = true;
    owner.session.socketClosed = true;
    UpdateQuestProgress(1000);
    assert(!questProgressRequesters.contains(owner.guid) && sentPackets.empty());
    owner.session.socketClosed = false;

    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Tankbot", "expired", "WATCH"}));
    sentPackets.clear();
    owner.online = false;
    questProgressRequesters.at(owner.guid).lastSeen = QuestProgressClock::now() - std::chrono::seconds(181);
    UpdateQuestProgress(1000);
    assert(!questProgressRequesters.contains(owner.guid) && sentPackets.size() == 2);
    sentPackets.clear();
    owner.online = true;
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Tankbot", "bound", "WATCH"}));
    sentPackets.clear();
    auto& state = questProgressRequesters.at(owner.guid);
    state.requests = 80;
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Magebot", "limit", "WATCH"}));
    ExpectError("RATE_LIMIT");
    state.requests = 0;
    for (uint32 index = 0; index < 39; ++index)
        state.watches[{1000 + index}] = QuestProgressWatch{};
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Magebot", "limit", "WATCH"}));
    ExpectError("WATCH_LIMIT");
    questProgressRequesters.clear();
    for (uint32 index = 0; index < 512; ++index)
        questProgressRequesters[{1000 + index}] = QuestProgressRequesterState{};
    assert(DispatchQuestProgress(&owner, {"QUEST_PROGRESS", "Tankbot", "limit", "WATCH"}));
    ExpectError("RATE_LIMIT");
    assert(questProgressRequesters.size() == 512);
    std::cout << "Quest progress: native counters, exact wire, multi-bot updates, auth, reload, cleanup, leases and rate bounds passed\n";
}
