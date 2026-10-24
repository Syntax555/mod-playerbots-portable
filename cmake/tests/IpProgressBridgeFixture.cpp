// Native-shaped world and Individual Progression state; TestIpProgressBridge.py
// inserts the actual bridge endpoint, its progression unit and the module's
// own progression functions.
#include <algorithm>
#include <cassert>
#include <chrono>
#include <cctype>
#include <cstdint>
#include <cstring>
#include <functional>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

using uint8 = std::uint8_t;
using uint16 = std::uint16_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
using int32 = std::int32_t;
using ChatMsg = int;
constexpr ChatMsg CHAT_MSG_WHISPER = 7;
constexpr char kFieldSeparator = '~';
constexpr char const* kAddonEnvelope = "MBOT\t";
constexpr std::size_t kMaxBridgeWireLength = 255;
constexpr std::size_t kMaxTokenLength = 64;
constexpr uint32 PHASEMASK_NORMAL = 0x00000001;
enum Difficulty : uint8 { DUNGEON_DIFFICULTY_NORMAL = 0, DUNGEON_DIFFICULTY_HEROIC = 1 };
constexpr uint8 MAX_DIFFICULTY = 4;
enum DisableType { DISABLE_TYPE_QUEST = 1, DISABLE_TYPE_MAP = 2 };
enum ConditionSourceType { CONDITION_SOURCE_TYPE_QUEST_AVAILABLE = 19 };
enum ConditionTypes { CONDITION_QUESTREWARDED = 8, CONDITION_RACE = 16 };
enum WorldIntConfigs { CONFIG_MAX_PLAYER_LEVEL };

@NATIVE@

struct ObjectGuid
{
    uint64 _guid = 0;
    auto operator<=>(ObjectGuid const&) const = default;
};

class Player;
struct Quest
{
    uint32 id = 0;
    uint32 minLevel = 1;
    uint32 maxLevel = 0;
    uint32 breadcrumbFor = 0;
    bool repeatable = false;
    uint32 GetQuestId() const { return id; }
    uint32 GetMinLevel() const { return minLevel; }
    uint32 GetMaxLevel() const { return maxLevel; }
    uint32 GetBreadcrumbForQuestId() const { return breadcrumbFor; }
};
struct WorldSession
{
    uint32 account = 1;
    bool socketClosed = false;
    uint32 GetAccountId() const { return account; }
    bool IsSocketClosed() const { return socketClosed; }
};
struct DungeonProgressionRequirements
{
    uint32 map;
    uint8 difficulty;
};
struct PlayerSetting
{
    uint32 value = 0;
    bool HasFlag(uint32 flag) const { return (value & flag) != 0; }
};

// A native acceptance check that the double reports as failing.
std::set<std::pair<uint32, std::string>> failingChecks;
uint32 settingWrites = 0;

class Player
{
public:
    ObjectGuid guid{1};
    WorldSession session;
    bool online = true;
    bool connected = true;
    bool gm = false;
    uint32 level = 60;
    std::map<uint32, QuestStatus> statuses;
    std::set<uint32> rewarded;
    bool logFull = false;
    std::set<std::pair<uint32, uint8>> missingAccess;
    std::vector<std::tuple<uint32, uint8, bool>> satisfyCalls;

    ObjectGuid GetGUID() const { return guid; }
    WorldSession* GetSession() { return &session; }
    bool IsInWorld() const { return online; }
    bool IsGameMaster() const { return gm; }
    uint32 GetLevel() const { return level; }
    QuestStatus GetQuestStatus(uint32 id) const
    {
        auto const found = statuses.find(id);
        if (found != statuses.end())
            return found->second;
        return rewarded.contains(id) ? QUEST_STATUS_REWARDED : QUEST_STATUS_NONE;
    }
    bool IsQuestRewarded(uint32 id) const { return rewarded.contains(id); }
    bool Check(Quest const* quest, char const* name, bool msg) const
    {
        assert(!msg);
        return !failingChecks.contains({quest->GetQuestId(), name});
    }
    bool SatisfyQuestClass(Quest const* quest, bool msg) const { return Check(quest, "class", msg); }
    bool SatisfyQuestRace(Quest const* quest, bool msg) const { return Check(quest, "race", msg); }
    bool SatisfyQuestLevel(Quest const* quest, bool msg) const
    {
        assert(!msg);
        return level >= quest->GetMinLevel() && (!quest->GetMaxLevel() || level <= quest->GetMaxLevel());
    }
    bool SatisfyQuestSkill(Quest const* quest, bool msg) const { return Check(quest, "skill", msg); }
    bool SatisfyQuestReputation(Quest const* quest, bool msg) const { return Check(quest, "reputation", msg); }
    bool SatisfyQuestPreviousQuest(Quest const* quest, bool msg) const { return Check(quest, "previous", msg); }
    bool SatisfyQuestTimed(Quest const* quest, bool msg) const { return Check(quest, "timed", msg); }
    bool SatisfyQuestExclusiveGroup(Quest const* quest, bool msg) const { return Check(quest, "exclusive", msg); }
    bool SatisfyQuestNextChain(Quest const* quest, bool msg) const { return Check(quest, "next", msg); }
    bool SatisfyQuestPrevChain(Quest const* quest, bool msg) const { return Check(quest, "prevchain", msg); }
    bool SatisfyQuestBreadcrumb(Quest const* quest, bool msg) const
    {
        assert(!msg);
        uint32 const target = quest->GetBreadcrumbForQuestId();
        return !(target && (GetQuestStatus(target) != QUEST_STATUS_NONE || IsQuestRewarded(target))) &&
            !failingChecks.contains({quest->GetQuestId(), "breadcrumb"});
    }
    bool SatisfyQuestDay(Quest const* quest, bool msg) const { return Check(quest, "day", msg); }
    bool SatisfyQuestWeek(Quest const* quest, bool msg) const { return Check(quest, "week", msg); }
    bool SatisfyQuestMonth(Quest const* quest, bool msg) const { return Check(quest, "month", msg); }
    bool SatisfyQuestSeasonal(Quest const* quest, bool msg) const { return Check(quest, "seasonal", msg); }
    bool SatisfyQuestConditions(Quest const* quest, bool msg);
    bool SatisfyQuestLog(bool msg)
    {
        assert(!msg);
        return !logFull;
    }
    bool Satisfy(DungeonProgressionRequirements const* ar, uint32 map, bool report)
    {
        assert(ar && ar->map == map);
        satisfyCalls.emplace_back(map, ar->difficulty, report);
        assert(!report);
        return !missingAccess.contains({map, ar->difficulty});
    }
    PlayerSetting GetPlayerSetting(std::string const&, uint32)
    {
        // The native getter stores a missing entry, a write no reader may cause.
        ++settingWrites;
        return {};
    }
};
std::map<ObjectGuid, Player*> worldPlayers;
namespace ObjectAccessor
{
Player* FindConnectedPlayer(ObjectGuid guid)
{
    auto const found = worldPlayers.find(guid);
    return found == worldPlayers.end() || !found->second->connected ? nullptr : found->second;
}
}

struct ConditionSourceInfo
{
    Player* player;
    explicit ConditionSourceInfo(Player* target) : player(target) { }
};
struct Condition
{
    uint32 ConditionType = CONDITION_QUESTREWARDED;
    uint32 ConditionValue1 = 0;
    bool NegativeCondition = false;
    bool Meets(ConditionSourceInfo& source)
    {
        bool met = ConditionType == CONDITION_QUESTREWARDED ? source.player->IsQuestRewarded(ConditionValue1) :
            !failingChecks.contains({ConditionValue1, "condition"});
        return NegativeCondition ? !met : met;
    }
};
struct ConditionMgr
{
    std::map<uint32, std::vector<Condition>> quests;
    std::vector<Condition*> GetConditionsForNotGroupedEntry(ConditionSourceType type, uint32 entry)
    {
        assert(type == CONDITION_SOURCE_TYPE_QUEST_AVAILABLE);
        std::vector<Condition*> result;
        for (Condition& condition : quests[entry])
            result.push_back(&condition);
        return result;
    }
} conditionMgr;
auto* sConditionMgr = &conditionMgr;
bool Player::SatisfyQuestConditions(Quest const* quest, bool msg)
{
    assert(!msg);
    ConditionSourceInfo source(this);
    for (Condition* condition : conditionMgr.GetConditionsForNotGroupedEntry(CONDITION_SOURCE_TYPE_QUEST_AVAILABLE, quest->GetQuestId()))
        if (!condition->Meets(source))
            return false;
    return true;
}

struct DisableMgr
{
    std::set<std::pair<uint32, uint32>> quests;
    std::set<std::pair<uint32, uint8>> maps;
    uint8 playerDifficulty = 0;
    bool IsDisabledFor(DisableType type, uint32 entry, Player const* unit, uint8 flags = 0) const
    {
        if (type == DISABLE_TYPE_QUEST)
            return quests.contains({entry, 0});
        return maps.contains({entry, unit ? playerDifficulty : flags});
    }
} disableMgr;
auto* sDisableMgr = &disableMgr;

struct MapEntry
{
    bool dungeon = false;
    bool IsDungeon() const { return dungeon; }
};
struct MapStore
{
    std::map<uint32, MapEntry> maps;
    uint32 GetNumRows() const { return maps.empty() ? 0 : maps.rbegin()->first + 1; }
    MapEntry const* LookupEntry(uint32 id) const
    {
        auto const found = maps.find(id);
        return found == maps.end() ? nullptr : &found->second;
    }
} sMapStore;
struct MapDifficulty { };
std::set<std::pair<uint32, uint8>> mapDifficulties;
MapDifficulty const* GetMapDifficultyData(uint32 map, Difficulty difficulty)
{
    static MapDifficulty const data;
    return mapDifficulties.contains({map, difficulty}) ? &data : nullptr;
}

struct CreatureTemplate { uint32 ScriptID = 0; };
struct GameObjectTemplate { uint32 ScriptId = 0; };
struct CreatureData { uint32 id = 0, id2 = 0, id3 = 0; uint32 phaseMask = 1; uint32 ScriptId = 0; };
struct GameObjectData { uint32 id = 0; uint32 phaseMask = 1; uint32 ScriptId = 0; };
struct InstanceTemplate { };
struct AreaTriggerTeleport { uint32 target_mapId; float target_X, target_Y, target_Z, target_Orientation; };
using QuestRelations = std::multimap<uint32, uint32>;
struct ObjectMgr
{
    std::map<uint32, Quest> quests;
    QuestRelations creatureStarters, objectStarters;
    std::map<uint32, CreatureData> creatures;
    std::map<uint32, GameObjectData> objects;
    std::map<uint32, CreatureTemplate> creatureTemplates;
    std::map<uint32, GameObjectTemplate> objectTemplates;
    std::vector<std::string> scripts{""};
    std::map<uint32, InstanceTemplate> instances;
    std::map<uint32, AreaTriggerTeleport> entrances;
    std::map<std::pair<uint32, uint8>, DungeonProgressionRequirements> requirements;
    uint32 indexBuilds = 0;

    Quest const* GetQuestTemplate(uint32 id) const
    {
        auto const found = quests.find(id);
        return found == quests.end() ? nullptr : &found->second;
    }
    QuestRelations* GetCreatureQuestRelationMap() { ++indexBuilds; return &creatureStarters; }
    QuestRelations* GetGOQuestRelationMap() { return &objectStarters; }
    std::map<uint32, CreatureData> const& GetAllCreatureData() const { return creatures; }
    std::map<uint32, GameObjectData> const& GetAllGOData() const { return objects; }
    CreatureTemplate const* GetCreatureTemplate(uint32 entry) const
    {
        auto const found = creatureTemplates.find(entry);
        return found == creatureTemplates.end() ? nullptr : &found->second;
    }
    GameObjectTemplate const* GetGameObjectTemplate(uint32 entry) const
    {
        auto const found = objectTemplates.find(entry);
        return found == objectTemplates.end() ? nullptr : &found->second;
    }
    uint32 Script(std::string const& name)
    {
        scripts.push_back(name);
        return uint32(scripts.size() - 1);
    }
    std::string const& GetScriptName(uint32 id) const { return scripts.at(id < scripts.size() ? id : 0); }
    InstanceTemplate const* GetInstanceTemplate(uint32 map) const
    {
        auto const found = instances.find(map);
        return found == instances.end() ? nullptr : &found->second;
    }
    AreaTriggerTeleport const* GetMapEntranceTrigger(uint32 map) const
    {
        auto const found = entrances.find(map);
        return found == entrances.end() ? nullptr : &found->second;
    }
    DungeonProgressionRequirements const* GetAccessRequirement(uint32 map, Difficulty difficulty)
    {
        return &requirements.try_emplace({map, difficulty}, DungeonProgressionRequirements{map, difficulty}).first->second;
    }
} objectMgr;
auto* sObjectMgr = &objectMgr;

struct World
{
    uint32 maxLevel = 80;
    uint32 getIntConfig(WorldIntConfigs) const { return maxLevel; }
} world;
auto* sWorld = &world;

#ifdef MBB_WITH_INDIVIDUAL_PROGRESSION
// The module's own fields and functions; the definitions below are its source.
class IndividualProgression
{
public:
    bool enabled = true;
    bool strictEarnedProgression = true;
    bool disableDefaultProgression = false;
    bool earlyDungeonSet2 = false;
    int progressionLimit = 0;
    int RequiredZulGurubProgression = 3;
    int RequiredZulAmanProgression = 12;
    std::map<uint32, uint8> customProgressionMap;
    std::set<uint32> botAccounts, excludedAccounts;
    std::set<uint32> refusedMaps;
    std::vector<std::tuple<uint32, float, float, float>> mapChecks;

    bool IsStrictDefaultProgression() const;
    bool HasStrictEarnedMilestone(Player* player, uint8 stage) const;
    uint8 GetPlayerProgressionFromQuests(Player* player) const;
    bool hasPassedProgression(Player* player, ProgressionState state) const;
    static bool isBeforeProgression(Player* player, ProgressionState state);
    bool isExcludedAccount(Player* player);
    bool isExcludedAccount(uint32 accountId) { return !(enabled && strictEarnedProgression) && excludedAccounts.contains(accountId); }
    bool isBotAccount(Player* player);
    bool isBotAccount(uint32 accountId) { return !(enabled && strictEarnedProgression) && botAccounts.contains(accountId); }
    bool CanEnterMap(Player* player, uint32 mapId, float x, float y, float z)
    {
        assert(player);
        mapChecks.emplace_back(mapId, x, y, z);
        return !refusedMaps.contains(mapId);
    }
} individualProgression;
#define sIndividualProgression (&individualProgression)

@INDIVIDUAL_PROGRESSION@
#endif

struct SentPacket
{
    ObjectGuid recipient;
    ChatMsg distribution;
    std::string opcode;
    std::string payload;
};
std::vector<SentPacket> sentPackets;
void SendAddonPacket(Player* player, ChatMsg distribution, std::string const& opcode, std::string const& payload = "")
{
    assert(player && player->GetSession());
    assert(std::strlen(kAddonEnvelope) + opcode.size() + (payload.empty() ? 0 : payload.size() + 1)
        <= kMaxBridgeWireLength);
    sentPackets.push_back({player->GetGUID(), distribution, opcode, payload});
}
bool SendProtocolError(Player* player, ChatMsg distribution, std::string const& opcode,
    std::string const& type, std::string const& token, std::string const& reason)
{
    SendAddonPacket(player, distribution, "ERR", opcode + "~" + type + "~" + token + "~" + reason);
    return true;
}

@PRODUCTION@

void ExpectError(std::string const& reason)
{
    assert(sentPackets.size() == 1);
    assert(sentPackets.front().opcode == "ERR" && sentPackets.front().distribution == CHAT_MSG_WHISPER);
    assert(sentPackets.front().payload.ends_with("~" + reason));
    sentPackets.clear();
}

// The concatenated items of one framed reply, after checking its counts.
std::string Items(std::string const& opcode, std::string const& token)
{
    assert(sentPackets.size() >= 2);
    assert(sentPackets.front().opcode == opcode + "_BEGIN" && sentPackets.back().opcode == opcode + "_END");
    std::string items;
    std::size_t count = 0;
    for (SentPacket const& packet : sentPackets)
    {
        assert(packet.distribution == CHAT_MSG_WHISPER && packet.recipient == ObjectGuid{1});
        assert(packet.payload.starts_with(token + "~"));
        if (packet.opcode != opcode)
            continue;
        std::string const chunk = packet.payload.substr(token.size() + 1);
        count += std::count(chunk.begin(), chunk.end(), ',') + 1;
        items += (items.empty() ? "" : ",") + chunk;
    }
    assert(sentPackets.front().payload == token + "~" + std::to_string(count));
    assert(sentPackets.back().payload == token + "~" + std::to_string(count));
    sentPackets.clear();
    return items;
}

std::string State(Player& player)
{
    assert(Dispatch(&player, {"IP_STATE", "zip1"}));
    assert(sentPackets.size() == 1 && sentPackets[0].opcode == "IP_STATE");
    assert(sentPackets[0].distribution == CHAT_MSG_WHISPER);
    std::string const state = sentPackets[0].payload;
    sentPackets.clear();
    return state;
}

void Reward(Player& player, uint8 tier)
{
    for (uint32 marker = 66001; marker <= 66018; ++marker)
        player.rewarded.erase(marker);
    // The default chain never writes reserved marker 66011.
    for (uint32 stage = 1; stage <= tier; ++stage)
        if (stage != 11)
            player.rewarded.insert(66000 + stage);
}

void AllowRequests(Player& player)
{
    ipProgressRequesters.at(player.GetGUID()).requests = 0;
}

int main()
{
    Player player;
    worldPlayers[player.guid] = &player;

    // Field validation happens before any state is read or rate state is created.
    assert(Dispatch(&player, {"IP_STATE"}));
    ExpectError("BAD_FIELD_COUNT");
    assert(Dispatch(&player, {"IP_STATE", "bad token"}));
    ExpectError("BAD_TOKEN");
    assert(Dispatch(&player, {"IP_STATE", "zip1", "FOREVER"}));
    ExpectError("BAD_MODE");
    assert(Dispatch(&player, {"IP_QUESTS", "zip1"}));
    ExpectError("BAD_FIELD_COUNT");
    assert(Dispatch(&player, {"IP_ACCESS", "zip1", "533"}));
    ExpectError("BAD_FIELD_COUNT");
    assert(ipProgressRequesters.empty());

#ifndef MBB_WITH_INDIVIDUAL_PROGRESSION
    // Without the module the realm reports no progression and no progression gates.
    assert(State(player) == "zip1~1~0~0~0~0~0~255~0~0~N~0~80");
    objectMgr.quests[200] = Quest{200};
    objectMgr.creatureStarters.insert({16841, 200});
    AllowRequests(player);
    assert(Dispatch(&player, {"IP_QUESTS", "zip2", "200"}));
    assert(Items("IP_QUESTS", "zip2") == "200:A");
    sMapStore.maps[532].dungeon = true;
    objectMgr.instances[532];
    mapDifficulties.insert({532, 0});
    assert(Dispatch(&player, {"IP_ACCESS", "zip3"}));
    assert(Items("IP_ACCESS", "zip3") == "532:A---");
    std::cout << "IP progress bridge without Individual Progression passed\n";
    return 0;
#else
    // A fresh strict character: stored and effective tier 0, Ragnaros next.
    assert(State(player) == "zip1~1~1~1~0~0~0~0~1~0~N~0~80");
    // Boss milestones are never read: their getter would store a setting.
    assert(settingWrites == 0);

    Reward(player, 7);
    AllowRequests(player);
    assert(State(player) == "zip1~1~1~1~7~7~0~0~8~0~N~0~80");
    // A rewarded Into the Breach is reported as the satisfied pending transition.
    player.rewarded.insert(INTO_THE_BREACH);
    assert(State(player) == "zip1~1~1~1~7~7~0~0~8~1~N~0~80");
    player.rewarded.erase(INTO_THE_BREACH);
    // Tier 4 needs a rewarded gong quest, either IP's own or the native one.
    Reward(player, 3);
    AllowRequests(player);
    assert(State(player).ends_with("~3~3~0~0~4~0~N~0~80"));
    player.rewarded.insert(SIMPLY_BANG_A_GONG);
    assert(State(player).ends_with("~3~3~0~0~4~1~N~0~80"));
    player.rewarded.erase(SIMPLY_BANG_A_GONG);
    Reward(player, 10);
    // Reserved stage 11 is skipped: Kael'thas leads to Illidan.
    assert(State(player).ends_with("~10~10~0~1~12~0~N~0~80"));
    Reward(player, 13);
    AllowRequests(player);
    assert(State(player).ends_with("~13~13~0~2~14~0~N~0~80"));
    Reward(player, 18);
    assert(State(player).ends_with("~18~18~0~2~0~0~N~0~80"));
    assert(settingWrites == 0);

    // A realm ceiling keeps the stored marker but clamps the usable tier and era.
    individualProgression.progressionLimit = 7;
    world.maxLevel = 60;
    Reward(player, 13);
    AllowRequests(player);
    assert(State(player) == "zip1~1~1~1~13~7~7~0~14~0~N~0~60");
    individualProgression.progressionLimit = 12;
    world.maxLevel = 70;
    assert(State(player) == "zip1~1~1~1~13~12~12~1~14~0~N~0~70");
    individualProgression.progressionLimit = 0;
    world.maxLevel = 80;

    // Custom chains have no default era; filters apply only outside strict mode.
    individualProgression.customProgressionMap[1234] = 3;
    individualProgression.strictEarnedProgression = false;
    individualProgression.botAccounts.insert(1);
    AllowRequests(player);
    assert(State(player) == "zip1~1~1~0~13~13~0~255~0~0~B~0~80");
    individualProgression.botAccounts.clear();
    individualProgression.excludedAccounts.insert(1);
    assert(State(player).ends_with("~X~0~80"));
    individualProgression.excludedAccounts.clear();
    individualProgression.customProgressionMap.clear();
    individualProgression.strictEarnedProgression = true;
    player.gm = true;
    assert(State(player).ends_with("~N~1~80"));
    player.gm = false;
    individualProgression.enabled = false;
    AllowRequests(player);
    assert(State(player) == "zip1~1~0~0~0~0~0~255~0~0~N~0~80");
    individualProgression.enabled = true;

    // A watch pushes only changed states, once per second, under its own token.
    Reward(player, 7);
    AllowRequests(player);
    assert(Dispatch(&player, {"IP_STATE", "zipw", "WATCH"}));
    assert(sentPackets.size() == 1 && sentPackets[0].payload == "zipw~1~1~1~7~7~0~0~8~0~N~0~80");
    sentPackets.clear();
    UpdateIpProgress(1000);
    assert(sentPackets.empty());
    Reward(player, 8);
    UpdateIpProgress(999);
    assert(sentPackets.empty());
    UpdateIpProgress(1);
    assert(sentPackets.size() == 1 && sentPackets[0].opcode == "IP_STATE");
    assert(sentPackets[0].payload == "zipw~1~1~1~8~8~0~1~9~0~N~0~80");
    assert(sentPackets[0].distribution == CHAT_MSG_WHISPER);
    sentPackets.clear();
    UpdateIpProgress(1000);
    assert(sentPackets.empty());
    // Another token cannot cancel the watch; the owning token can.
    assert(Dispatch(&player, {"IP_STATE", "other", "UNWATCH"}));
    Reward(player, 9);
    UpdateIpProgress(1000);
    assert(sentPackets.size() == 1);
    sentPackets.clear();
    assert(Dispatch(&player, {"IP_STATE", "zipw", "UNWATCH"}));
    assert(sentPackets.empty());
    Reward(player, 10);
    UpdateIpProgress(1000);
    assert(sentPackets.empty());
    // Leases expire after 180 seconds unless renewed.
    assert(Dispatch(&player, {"IP_STATE", "zipw", "WATCH"}));
    sentPackets.clear();
    ipProgressRequesters.at(player.guid).watchExpires = QuestProgressClock::now() - std::chrono::seconds(1);
    Reward(player, 12);
    UpdateIpProgress(1000);
    assert(sentPackets.empty() && ipProgressRequesters.at(player.guid).watchToken.empty());
    // Requester state ends after idling or when the session closes.
    ipProgressRequesters.at(player.guid).lastSeen = QuestProgressClock::now() - std::chrono::seconds(181);
    UpdateIpProgress(1000);
    assert(ipProgressRequesters.empty());
    assert(Dispatch(&player, {"IP_STATE", "zipw", "WATCH"}));
    sentPackets.clear();
    player.session.socketClosed = true;
    UpdateIpProgress(1000);
    assert(ipProgressRequesters.empty());
    player.session.socketClosed = false;

    // Requests are bounded per character and in the number of tracked characters.
    for (int request = 0; request < 20; ++request)
        assert(Dispatch(&player, {"IP_STATE", "zip1"}));
    sentPackets.clear();
    assert(Dispatch(&player, {"IP_STATE", "zip1"}));
    ExpectError("RATE_LIMIT");
    ipProgressRequesters.at(player.guid).windowStart = QuestProgressClock::now() - std::chrono::seconds(2);
    assert(Dispatch(&player, {"IP_STATE", "zip1"}));
    sentPackets.clear();
    for (uint64 other = 100; ipProgressRequesters.size() < 512; ++other)
        ipProgressRequesters[ObjectGuid{other}];
    Player stranger;
    stranger.guid = {99};
    worldPlayers[stranger.guid] = &stranger;
    assert(Dispatch(&stranger, {"IP_STATE", "zip1"}));
    assert(sentPackets.size() == 1 && sentPackets[0].recipient == stranger.guid && sentPackets[0].payload.ends_with("~RATE_LIMIT"));
    sentPackets.clear();
    for (auto it = ipProgressRequesters.begin(); it != ipProgressRequesters.end();)
        it = it->first == player.guid ? std::next(it) : ipProgressRequesters.erase(it);

    // World data, including quest givers, is loaded before the first request indexes it.
    uint32 const tbc = objectMgr.Script("npc_ipp_tbc");
    uint32 const preTbc = objectMgr.Script("npc_ipp_pre_tbc");
    uint32 const vendor = objectMgr.Script("npc_vendor_custom");
    uint32 const portal = objectMgr.Script("gobject_ipp_tbc");
    objectMgr.creatureTemplates[16841].ScriptID = tbc;           // Watch Commander Netherwane
    objectMgr.creatureStarters.insert({16841, 326});
    objectMgr.creatures[1] = CreatureData{16841};
    objectMgr.creatureTemplates[500].ScriptID = 0;
    objectMgr.creatureStarters.insert({500, 327});
    objectMgr.creatures[2] = CreatureData{500, 0, 0, 1, tbc};    // spawn-only script
    objectMgr.creatureStarters.insert({501, 328});              // never spawned, e.g. summoned
    objectMgr.creatureStarters.insert({501, 333});              // ... beside a hidden giver
    objectMgr.creatureStarters.insert({16841, 333});
    objectMgr.quests[333] = Quest{333};
    objectMgr.creatureTemplates[501].ScriptID = tbc;
    objectMgr.creatureTemplates[502].ScriptID = tbc;
    objectMgr.creatureStarters.insert({502, 329});
    objectMgr.creatures[3] = CreatureData{502, 0, 0, 0x10000};  // area-phased spawn
    objectMgr.creatureTemplates[503].ScriptID = preTbc;
    objectMgr.creatureTemplates[504].ScriptID = vendor;
    objectMgr.creatureStarters.insert({503, 330});
    objectMgr.creatureStarters.insert({504, 330});
    objectMgr.creatures[4] = CreatureData{503};
    objectMgr.creatures[5] = CreatureData{504};
    objectMgr.objectTemplates[600].ScriptId = portal;
    objectMgr.objectStarters.insert({600, 331});
    objectMgr.objects[6] = GameObjectData{600};
    objectMgr.quests[331] = Quest{331};
    objectMgr.creatureTemplates[505].ScriptID = tbc;
    objectMgr.creatures[7] = CreatureData{506, 505};            // secondary entries keep the template script
    objectMgr.creatureTemplates[506].ScriptID = vendor;
    objectMgr.creatures[7].ScriptId = vendor;
    objectMgr.creatureStarters.insert({505, 332});
    objectMgr.quests[332] = Quest{332};
    objectMgr.creatureStarters.insert({503, 300});

    // Quest availability uses the native checks without messages.
    Reward(player, 7);
    player.level = 58;
    for (uint32 id = 300; id <= 330; ++id)
        objectMgr.quests[id] = Quest{id};
    AllowRequests(player);
    assert(Dispatch(&player, {"IP_QUESTS", "zipq", "300,999999"}));
    assert(Items("IP_QUESTS", "zipq") == "300:A,999999:U");
    player.statuses[301] = QUEST_STATUS_INCOMPLETE;
    player.statuses[302] = QUEST_STATUS_COMPLETE;
    player.statuses[303] = QUEST_STATUS_FAILED;
    player.rewarded.insert(304);
    objectMgr.quests[305].minLevel = 60;
    objectMgr.quests[306].maxLevel = 50;
    failingChecks = {{307, "class"}, {308, "race"}, {309, "skill"}, {310, "reputation"}, {311, "previous"},
        {312, "timed"}, {313, "exclusive"}, {314, "next"}, {315, "prevchain"}, {316, "day"}, {317, "seasonal"}};
    disableMgr.quests.insert({318, 0});
    assert(Dispatch(&player, {"IP_QUESTS", "zipq", "301,302,303,304,305,306,307,308,309,310,311,312,313,314,315,316,317,318"}));
    assert(Items("IP_QUESTS", "zipq") ==
        "301:I,302:C,303:F,304:R,305:L8,306:L10,307:L2,308:L4,309:L20,310:L40,311:L80,312:L100,"
        "313:L200,314:L400,315:L800,316:L4000,317:L4000,318:L1");
    // A breadcrumb whose target is taken never returns; an active one only waits for turn-in.
    objectMgr.quests[319].breadcrumbFor = 320;
    player.statuses[320] = QUEST_STATUS_INCOMPLETE;
    failingChecks.insert({321, "breadcrumb"});
    // Progression marker conditions name the tier they need or the tier that retired them.
    conditionMgr.quests[322] = {Condition{CONDITION_QUESTREWARDED, 66008, false}};
    conditionMgr.quests[323] = {Condition{CONDITION_QUESTREWARDED, 66007, true}};
    conditionMgr.quests[324] = {Condition{CONDITION_RACE, 324, false}};
    failingChecks.insert({324, "condition"});
    conditionMgr.quests[325] = {Condition{CONDITION_QUESTREWARDED, 66005, false}};
    // A met marker row names nothing; the failing row decides.
    objectMgr.quests[340] = Quest{340};
    objectMgr.quests[341] = Quest{341};
    conditionMgr.quests[340] = {Condition{CONDITION_QUESTREWARDED, 66005, false}, Condition{CONDITION_QUESTREWARDED, 66008, false}};
    conditionMgr.quests[341] = {Condition{CONDITION_QUESTREWARDED, 66005, false}, Condition{CONDITION_RACE, 341, false}};
    failingChecks.insert({341, "condition"});
    assert(Dispatch(&player, {"IP_QUESTS", "zipq", "319,321,322,323,324,325,340,341"}));
    assert(Items("IP_QUESTS", "zipq") == "319:L1000,321:L2000,322:L18000:+8,323:L18000:-7,324:L8000,325:A,340:L18000:+8,341:L8000");
    conditionMgr.quests.erase(340);
    conditionMgr.quests.erase(341);
    player.logFull = true;
    assert(Dispatch(&player, {"IP_QUESTS", "zipq", "300"}));
    assert(Items("IP_QUESTS", "zipq") == "300:L40000");
    player.logFull = false;

    player.level = 60;
    // Givers hidden by an Individual Progression script make their quest unavailable.
    assert(Dispatch(&player, {"IP_QUESTS", "zipg", "326,327,328,329,330,331,332,333"}));
    assert(Items("IP_QUESTS", "zipg") == "326:L20000,327:L20000,328:A,329:A,330:A,331:L20000,332:L20000,333:A");
    assert(objectMgr.indexBuilds == 1);
    Reward(player, 8);
    assert(Dispatch(&player, {"IP_QUESTS", "zipg", "326,330,331"}));
    assert(Items("IP_QUESTS", "zipg") == "326:A,330:A,331:A");
    // Vanilla-only givers leave once TBC is earned, while a visible alternative remains.
    assert(Dispatch(&player, {"IP_QUESTS", "zipg", "300"}));
    assert(Items("IP_QUESTS", "zipg") == "300:L20000");
    // A lowered realm ceiling hides TBC givers again while the marker stays saved.
    individualProgression.progressionLimit = 7;
    assert(Dispatch(&player, {"IP_QUESTS", "zipg", "326"}));
    assert(Items("IP_QUESTS", "zipg") == "326:L20000");
    individualProgression.progressionLimit = 0;
    Reward(player, 7);
    player.gm = true;
    AllowRequests(player);
    assert(Dispatch(&player, {"IP_QUESTS", "zipg", "326"}));
    assert(Items("IP_QUESTS", "zipg") == "326:A");
    player.gm = false;
    assert(objectMgr.indexBuilds == 1);

    // Quest lists are bounded and validated as a whole.
    std::string many;
    for (int id = 0; id < 33; ++id)
        many += (many.empty() ? "" : ",") + std::to_string(300 + id % 10);
    AllowRequests(player);
    assert(Dispatch(&player, {"IP_QUESTS", "zipq", many}));
    ExpectError("BAD_QUEST");
    for (std::string const& list : {std::string(""), std::string("300,abc"), std::string(",300"), std::string("0"),
             std::string("10000000"), std::string("300, 301")})
    {
        assert(Dispatch(&player, {"IP_QUESTS", "zipq", list}));
        ExpectError("BAD_QUEST");
    }
    // A full list of 32 answers splits into several packets inside the wire budget.
    many = many.substr(0, many.rfind(','));
    assert(Dispatch(&player, {"IP_QUESTS", std::string(64, 'q'), many}));
    assert(sentPackets.size() > 3);
    std::string const full = Items("IP_QUESTS", std::string(64, 'q'));
    assert(std::count(full.begin(), full.end(), ',') == 31);
    // An item that cannot fit one packet rejects the whole reply instead of truncating it.
    assert(BuildIpListPackets("IP_QUESTS", "zipq", {"1:A", std::string(250, '1')}).empty());

    // Instance access: IP's map gate and the native requirements, without refusal side effects.
    sMapStore.maps[0].dungeon = false;                           // continent
    sMapStore.maps[30].dungeon = true;                           // battleground-like, no instance template
    for (uint32 map : {33u, 249u, 469u, 532u, 548u})
    {
        sMapStore.maps[map].dungeon = true;
        objectMgr.instances[map];
        mapDifficulties.insert({map, 0});
    }
    mapDifficulties.insert({33, 1});
    mapDifficulties.insert({532, 1});
    objectMgr.entrances[469] = {469, -7666.0f, -1101.0f, 399.0f, 0.0f};
    individualProgression.refusedMaps = {469};
    player.missingAccess = {{249, 0}, {532, 1}};
    disableMgr.maps.insert({548, 0});
    AllowRequests(player);
    assert(Dispatch(&player, {"IP_ACCESS", "zipa"}));
    assert(Items("IP_ACCESS", "zipa") == "33:AA--,249:R---,469:G---,532:AR--,548:D---");
    assert(std::find(individualProgression.mapChecks.begin(), individualProgression.mapChecks.end(),
        std::make_tuple(469u, -7666.0f, -1101.0f, 399.0f)) != individualProgression.mapChecks.end());
    assert(std::all_of(player.satisfyCalls.begin(), player.satisfyCalls.end(),
        [](auto const& call) { return !std::get<2>(call) && std::get<0>(call) != 469 && std::get<0>(call) != 548; }));
    // Satisfy would send a refusal for a map disabled at the player's own difficulty.
    disableMgr.maps.insert({33, 1});
    disableMgr.playerDifficulty = 1;
    player.satisfyCalls.clear();
    assert(Dispatch(&player, {"IP_ACCESS", "zipa"}));
    assert(Items("IP_ACCESS", "zipa").starts_with("33:DD--,"));
    assert(std::none_of(player.satisfyCalls.begin(), player.satisfyCalls.end(),
        [](auto const& call) { return std::get<0>(call) == 33; }));
    // Answers never change progression, quests or settings.
    assert(settingWrites == 0 && player.rewarded.contains(66007) && !player.rewarded.contains(66008));
    std::cout << "IP progress bridge state, quests, givers, access, watches and limits passed\n";
    return 0;
#endif
}
