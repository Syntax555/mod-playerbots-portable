"""Check that natural bots fly only flight routes they have discovered.

The production follower TaxiAction, NewRpg flight selection and flight start
run with the core's real interaction guard, taxi mask and node-learning code.
The shared route rule is compared with the core express-taxi opcode handler.
Mutation checks confirm that each guard is required. No realm is started.
"""

from pathlib import Path
import os
import subprocess
import tempfile

from FixtureSupport import function, prepared_core


repository = Path(__file__).resolve().parents[2]
core = prepared_core(repository)
module = core / 'modules/mod-playerbots/src'
ai = (module / 'Bot/PlayerbotAI.cpp').read_text()
taxi_action = (module / 'Ai/Base/Actions/TaxiAction.cpp').read_text()
travel = (module / 'Mgr/Travel/TravelMgr.cpp').read_text()
rpg = (module / 'Ai/World/Rpg/Action/NewRpgAction.cpp').read_text()
player = (core / 'src/server/game/Entities/Player/Player.cpp').read_text()
handler = (core / 'src/server/game/Handlers/TaxiHandler.cpp').read_text()
taxi_header = (core / 'src/server/game/Entities/Player/PlayerTaxi.h').read_text()

production = {
    'route': function(ai, 'bool CanUseTaxiNodes(Player* player, std::vector<uint32> const& nodes)'),
    'taxi': function(taxi_action, 'bool TaxiAction::Execute(Event event)'),
    'zones': function(travel, 'std::vector<uint32> TravelMgr::GetFlightNodesInZone('),
    'select': function(travel, 'std::vector<std::vector<uint32>> TravelMgr::GetOptimalFlightDestinations(Player* bot)'),
    'flight': function(rpg, 'bool NewRpgTravelFlightAction::Execute(Event /*event*/)'),
}
native = '\n'.join([
    function(player, 'Creature* Player::GetNPCIfCanInteractWith'),
    function(handler, 'bool WorldSession::SendLearnNewTaxiNode'),
    function(handler, 'void WorldSession::HandleActivateTaxiExpressOpcode'),
])

fixture = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <type_traits>
#include <unordered_set>
#include <utility>
#include <variant>
#include <vector>

using uint8 = std::uint8_t; using uint16 = std::uint16_t; using uint32 = std::uint32_t; using uint64 = std::uint64_t;
#define LOG_DEBUG(...) ((void)0)
static constexpr std::size_t TaxiMaskSize = 14;
typedef std::array<uint32, TaxiMaskSize> TaxiMask;
constexpr uint32 UNIT_NPC_FLAG_FLIGHTMASTER = 0x2000;
constexpr uint32 CREATURE_TYPE_FLAG_VISIBLE_TO_GHOSTS = 1, CREATURE_TYPE_FLAG_INTERACT_WHILE_DEAD = 2;
constexpr int REP_UNFRIENDLY = 2;
constexpr float INTERACTION_DISTANCE = 5.5f;
constexpr uint32 AREA_FLAG_CAPITAL = 0x200;
constexpr uint16 CMSG_TAXICLEARALLNODES = 1, CMSG_TAXICLEARNODE = 2, SMSG_NEW_TAXI_PATH = 3, SMSG_TAXINODE_STATUS = 4;
enum NPCFlags : uint32 {};
enum TeamId { TEAM_ALLIANCE = 0, TEAM_HORDE = 1, TEAM_NEUTRAL = 2 };
enum ActivateTaxiReply { ERR_TAXIOK = 0, ERR_TAXITOOFARAWAY = 4, ERR_TAXINOTVISITED = 6 };

struct ObjectGuid
{
    uint64 raw = 0;
    bool operator!() const { return !raw; }
    explicit operator bool() const { return raw != 0; }
    bool operator==(ObjectGuid const& other) const { return raw == other.raw; }
    bool operator<(ObjectGuid const& other) const { return raw < other.raw; }
};
using GuidVector = std::vector<ObjectGuid>;

struct WorldPacket
{
    uint16 opcode = 0;
    std::vector<uint64> data;
    std::size_t read = 0;
    WorldPacket() = default;
    explicit WorldPacket(uint16 opcode, std::size_t = 0) : opcode(opcode) {}
    bool empty() const { return data.empty(); }
    uint16 GetOpcode() const { return opcode; }
    WorldPacket& operator<<(ObjectGuid guid) { data.push_back(guid.raw); return *this; }
    WorldPacket& operator<<(uint32 value) { data.push_back(value); return *this; }
    WorldPacket& operator<<(uint8 value) { data.push_back(value); return *this; }
    WorldPacket& operator>>(ObjectGuid& guid) { guid.raw = data.at(read++); return *this; }
    WorldPacket& operator>>(uint32& value) { value = uint32(data.at(read++)); return *this; }
    void rfinish() { read = data.size(); }
};

struct Event
{
    std::string param;
    WorldPacket packet;
    Event() = default;
    Event(std::string param) : param(std::move(param)) {}
    std::string getParam() { return param; }
    WorldPacket& getPacket() { return packet; }
};

struct WorldPosition { uint32 mapId = 0; float x = 0.0f; };
struct CreatureTemplate { uint32 type_flags = 0; };
class Player;
class Creature
{
public:
    ObjectGuid guid;
    uint32 entry = 3838;
    uint32 mapId = 0;
    float x = 0.0f;
    bool alive = true;
    uint32 flags = UNIT_NPC_FLAG_FLIGHTMASTER;
    int reaction = 4;
    ObjectGuid charmer;
    uint32 node = 10;
    CreatureTemplate creatureTemplate;
    bool IsAlive() const { return alive; }
    uint32 GetNpcFlags() const { return flags; }
    bool HasNpcFlag(NPCFlags required) const { return (flags & required) == required; }
    int GetReactionTo(Player const*) const { return reaction; }
    ObjectGuid GetCharmerGUID() const { return charmer; }
    CreatureTemplate const* GetCreatureTemplate() const { return &creatureTemplate; }
    bool IsWithinDistInMap(Player const* player, float distance) const;
    ObjectGuid GetGUID() const { return guid; }
    uint32 GetEntry() const { return entry; }
    float GetPositionX() const { return x; }
    float GetPositionY() const { return 0.0f; }
    float GetPositionZ() const { return 0.0f; }
    uint32 GetMapId() const { return mapId; }
};

class PlayerTaxi
{
public:
    TaxiMask m_taximask{};
    TAXI_IS_KNOWN
    TAXI_SET_KNOWN
};

class WorldSession
{
public:
    Player* player = nullptr;
    std::vector<uint16> sent;
    std::vector<ActivateTaxiReply> replies;
    Player* GetPlayer() { return player; }
    void SendPacket(WorldPacket const* packet) { sent.push_back(packet->GetOpcode()); }
    void SendActivateTaxiReply(ActivateTaxiReply reply) { replies.push_back(reply); }
    bool SendLearnNewTaxiNode(Creature* unit);
    void HandleActivateTaxiExpressOpcode(WorldPacket& recvData);
};

class Player
{
public:
    ObjectGuid guid{200};
    uint32 mapId = 0;
    float x = 1.0f;
    bool alive = true;
    bool inWorld = true;
    bool inFlight = false;
    bool taxiCheater = false;
    bool mounted = false;
    TeamId team = TEAM_ALLIANCE;
    uint32 level = 20;
    uint32 zoneId = 40;
    PlayerTaxi m_taxi;
    WorldSession session;
    std::vector<std::vector<uint32>> flights;
    std::vector<Creature*> flightMasters;
    Player() { session.player = this; }
    bool IsAlive() const { return alive; }
    bool IsInWorld() const { return inWorld; }
    bool IsInFlight() const { return inFlight; }
    bool isTaxiCheater() const { return taxiCheater; }
    bool IsMounted() const { return mounted; }
    void Dismount() { mounted = false; }
    TeamId GetTeamId(bool = false) const { return team; }
    uint32 GetLevel() const { return level; }
    uint32 GetZoneId() const { return zoneId; }
    WorldSession* GetSession() { return &session; }
    float GetDistance(Creature const* creature) const { return std::abs(x - creature->x); }
    float GetDistance(WorldPosition const& position) const { return std::abs(x - position.x); }
    Creature* FindNearestCreature(uint32 entry, float range);
    Creature* GetNPCIfCanInteractWith(ObjectGuid const& guid, uint32 npcflagmask);
    bool ActivateTaxiPathTo(std::vector<uint32> const& nodes, Creature* npc, uint32)
    {
        flights.push_back(nodes);
        flightMasters.push_back(npc);
        return true;
    }
};

inline bool Creature::IsWithinDistInMap(Player const* player, float distance) const
{
    return player->mapId == mapId && std::abs(player->x - x) <= distance;
}

namespace ObjectAccessor
{
    inline std::map<std::pair<uint32, ObjectGuid>, Creature*> creatures;
    inline Creature* GetCreatureOrPetOrVehicle(Player const& player, ObjectGuid guid)
    {
        auto found = creatures.find({player.mapId, guid});
        return found == creatures.end() ? nullptr : found->second;
    }
    inline Creature* GetCreature(Player const& player, ObjectGuid guid) { return GetCreatureOrPetOrVehicle(player, guid); }
}

inline Creature* Player::FindNearestCreature(uint32 entry, float range)
{
    for (auto const& [key, creature] : ObjectAccessor::creatures)
        if (key.first == mapId && creature->entry == entry && std::abs(creature->x - x) <= range)
            return creature;
    return nullptr;
}

struct ObjectManager
{
    uint32 GetNearestTaxiNode(Creature const& creature, uint32) { return creature.node; }
    uint32 GetNearestTaxiNode(float x, float, float, uint32 mapId, uint32)
    {
        for (auto const& [key, creature] : ObjectAccessor::creatures)
            if (creature->mapId == mapId && creature->x == x)
                return creature->node;
        return 0;
    }
};
inline ObjectManager objectManager;
#define sObjectMgr (&objectManager)
struct ScriptManager
{
    std::vector<uint32> learned;
    void OnPlayerLearnTaxiNode(Player*, uint32 node) { learned.push_back(node); }
};
inline ScriptManager scriptManager;
#define sScriptMgr (&scriptManager)

struct TaxiPathEntry { uint32 from; uint32 to; };
struct TaxiNodesEntry { uint32 map_id; char const* name[16]; };
struct AreaTableEntry { uint32 flags; };
template <class Entry>
struct Store
{
    std::map<uint32, Entry> rows;
    uint32 GetNumRows() const { return rows.empty() ? 0 : rows.rbegin()->first + 1; }
    Entry const* LookupEntry(uint32 id) const
    {
        auto found = rows.find(id);
        return found == rows.end() ? nullptr : &found->second;
    }
};
inline Store<TaxiPathEntry> sTaxiPathStore;
inline Store<TaxiNodesEntry> sTaxiNodesStore;
inline Store<AreaTableEntry> sAreaTableStore;

struct PlayerbotAIConfig
{
    bool naturalProgression = true;
    float farDistance = 20.0f;
    uint32 botTaxiDelayMin = 350, botTaxiGapMs = 200, botTaxiGapJitterMs = 100, botTaxiDelayMax = 5000;
    float probTeleToBankers = 0.0f;
};
inline PlayerbotAIConfig sPlayerbotAIConfig;
inline uint32 randomState = 1;
inline uint32 urand(uint32 min, uint32 max)
{
    randomState = randomState * 1103515245u + 12345u;
    return min + (randomState >> 8) % (max - min + 1);
}

struct PlayerbotTextMgr
{
    static PlayerbotTextMgr& instance() { static PlayerbotTextMgr manager; return manager; }
    std::string GetBotTextOrDefault(std::string const&, std::string const& text, std::map<std::string, std::string>)
    {
        return text;
    }
};

struct NewRpgInfo
{
    struct TravelFlight
    {
        uint32 flightMasterEntry{0};
        WorldPosition flightMasterPos{};
        std::vector<uint32> path;
        bool inFlight{false};
    };
    std::variant<std::monostate, TravelFlight> data;
    void ChangeToIdle() { data = std::monostate{}; }
};

class PlayerbotAI
{
public:
    Player* bot;
    bool clientMaster = true;
    std::vector<std::string> errors;
    std::vector<std::string> said;
    std::vector<std::function<void()>> timed;
    NewRpgInfo rpgInfo;
    explicit PlayerbotAI(Player* bot) : bot(bot) {}
    void RemoveShapeshift() {}
    void TellMaster(std::string const& text) { said.push_back(text); }
    void TellMasterNoFacing(std::string const& text) { said.push_back(text); }
    void TellError(std::string const& text) { errors.push_back(text); }
    bool HasGameClientMaster() { return clientMaster; }
    uint32 GetGroupSlotIndex(Player*) { return 1; }
    void AddTimedEvent(std::function<void()> callback, uint32) { timed.push_back(std::move(callback)); }
    void SetNextCheckDelay(uint32) {}
};

struct LastMovement
{
    std::vector<uint32> taxiNodes;
    int cleared = 0;
    void Set(std::nullptr_t) { ++cleared; }
};
template <class T>
struct ValueStub
{
    std::remove_reference_t<T>* target;
    T Get() { return *target; }
    operator T() { return *target; }
};
struct Context
{
    LastMovement movement;
    GuidVector npcs;
    ValueStub<LastMovement&> movementValue{&movement};
    ValueStub<GuidVector> npcValue{&npcs};
    template <class T>
    ValueStub<T>* GetValue(std::string const& name)
    {
        if constexpr (std::is_same_v<T, LastMovement&>)
        {
            assert(name == "last taxi");
            return &movementValue;
        }
        else
        {
            assert(name == "nearest npcs");
            return &npcValue;
        }
    }
};

bool CanUseTaxiNodes(Player* player, std::vector<uint32> const& nodes);

class TaxiAction
{
public:
    PlayerbotAI* botAI;
    Player* bot;
    Context* context;
    TaxiAction(PlayerbotAI* ai, Context* context) : botAI(ai), bot(ai->bot), context(context) {}
    bool Execute(Event event);
};

struct Capital { uint32 zoneId; TeamId team; };
static const std::vector<Capital> capitals = {{1519, TEAM_ALLIANCE}};
struct TravelNodeMap
{
    std::map<std::pair<uint32, uint32>, std::vector<uint32>> paths;
    std::vector<uint32> FindTaxiPath(uint32 from, uint32 to)
    {
        auto found = paths.find({from, to});
        return found == paths.end() ? std::vector<uint32>{} : found->second;
    }
};
inline TravelNodeMap sTravelNodeMap;
class TravelMgr
{
public:
    struct FlightMasterInfo
    {
        WorldPosition pos;
        uint32 zoneId;
        uint32 taxiNodeId;
        uint32 templateEntry;
        uint32 dbGuid;
    };
    struct LevelBracket { uint32 low; uint32 high; };
    std::map<uint32, FlightMasterInfo> allianceFlightMasterCache;
    std::map<uint32, FlightMasterInfo> hordeFlightMasterCache;
    std::map<uint32, LevelBracket> zone2LevelBracket;
    FlightMasterInfo const* nearest = nullptr;
    FlightMasterInfo const* GetNearestFlightMasterInfo(Player*) { return nearest; }
    std::vector<uint32> GetFlightNodesInZone(uint32 zoneId, TeamId team, uint32 excludeNode = 0) const;
    std::vector<std::vector<uint32>> GetOptimalFlightDestinations(Player* bot);
};

class NewRpgTravelFlightAction
{
public:
    PlayerbotAI* botAI;
    Player* bot;
    int moves = 0;
    explicit NewRpgTravelFlightAction(PlayerbotAI* ai) : botAI(ai), bot(ai->bot) {}
    bool Execute(Event event);
    bool MoveFarTo(WorldPosition) { return ++moves; }
    bool MoveFarTo(Creature*) { return ++moves; }
    void ContinueCrossMapTaxi() {}
};
'''

fixture = fixture.replace('TAXI_IS_KNOWN', function(taxi_header, '[[nodiscard]] bool IsTaximaskNodeKnown'))
fixture = fixture.replace('TAXI_SET_KNOWN', function(taxi_header, 'bool SetTaximaskNode'))

tests = r'''
#include "Fixture.h"

struct World
{
    Creature flightMaster;
    Player bot;
    PlayerbotAI ai{&bot};
    Context context;
    TaxiAction action{&ai, &context};
    World(bool natural = true)
    {
        sPlayerbotAIConfig.naturalProgression = natural;
        scriptManager.learned.clear();
        flightMaster.guid.raw = 0xF1300000000E0010ULL;
        ObjectAccessor::creatures.clear();
        ObjectAccessor::creatures[{0, flightMaster.guid}] = &flightMaster;
        context.npcs = {flightMaster.guid};
        sTaxiPathStore.rows = {{1, {10, 11}}, {2, {10, 12}}, {3, {10, 13}}, {4, {13, 14}}, {5, {11, 10}}};
        sTaxiNodesStore.rows.clear();
        for (uint32 node : {10u, 11u, 12u, 13u, 14u})
            sTaxiNodesStore.rows[node] = TaxiNodesEntry{0, {node == 11 ? "Known" : node == 12 ? "Unknown" : "Other"}};
        bot.m_taxi.SetTaximaskNode(11);
    }
    bool Follow(std::vector<uint32> nodes)
    {
        context.movement.taxiNodes = std::move(nodes);
        return action.Execute(Event{});
    }
    void Fire()
    {
        for (auto& callback : ai.timed)
            callback();
        ai.timed.clear();
    }
    bool Said(std::string const& text) const
    {
        for (auto const& line : ai.said)
            if (line.find(text) != std::string::npos)
                return true;
        return false;
    }
};

bool CoreAccepts(Player& player, Creature& npc, std::vector<uint32> const& nodes)
{
    WorldPacket packet;
    packet << npc.guid << uint32(nodes.size());
    for (uint32 node : nodes)
        packet << node;
    std::size_t before = player.flights.size();
    player.session.HandleActivateTaxiExpressOpcode(packet);
    return player.flights.size() == before + 1 && player.flights.back() == nodes;
}

int main()
{
    // Followers fly a discovered route from an interactable flight master and learn only that origin.
    {
        World w;
        assert(w.Follow({10, 11}) && w.ai.errors.empty() && w.ai.timed.size() == 1);
        assert(w.bot.m_taxi.IsTaximaskNodeKnown(10) && scriptManager.learned == std::vector<uint32>{10});
        assert(w.bot.flights.empty());
        w.Fire();
        assert((w.bot.flights == std::vector<std::vector<uint32>>{{10, 11}} && w.bot.flightMasters[0] == &w.flightMaster));
    }
    // Undiscovered destinations or express stops leave the follower behind with an explanation.
    for (std::vector<uint32> route : {std::vector<uint32>{10, 12}, std::vector<uint32>{10, 13, 14}})
    {
        World w;
        w.bot.m_taxi.SetTaximaskNode(14);
        assert(!w.Follow(route) && w.ai.timed.empty() && w.context.movement.taxiNodes.empty());
        assert(w.ai.errors == std::vector<std::string>{"I have not discovered that flight path"});
        assert(w.context.movement.cleared == 1);
        w.Fire();
        assert(w.bot.flights.empty());
    }
    // Outside normal interaction range the follower neither learns the origin nor flies.
    {
        World w;
        w.bot.x = 15.0f;
        assert(!w.Follow({10, 11}) && w.ai.timed.empty() && w.bot.flights.empty());
        assert(!w.bot.m_taxi.IsTaximaskNodeKnown(10) && scriptManager.learned.empty() && w.bot.session.sent.empty());
        assert(w.ai.errors == std::vector<std::string>{"Cannot find any flightmaster to talk"});
    }
    // Hostile, dead and charmed flight masters fail the native interaction guard.
    for (int condition = 0; condition < 3; ++condition)
    {
        World w;
        if (condition == 0) w.flightMaster.reaction = REP_UNFRIENDLY;
        if (condition == 1) w.flightMaster.charmer.raw = 7;
        if (condition == 2) w.bot.alive = false;
        assert(!w.Follow({10, 11}) && w.bot.flights.empty() && scriptManager.learned.empty());
    }
    // The delayed take-off rechecks interaction and the route it is about to fly.
    for (int condition = 0; condition < 3; ++condition)
    {
        World w;
        assert(w.Follow({10, 11}));
        if (condition == 0) w.bot.x = 10.0f;
        if (condition == 1) w.bot.alive = false;
        if (condition == 2) w.context.movement.taxiNodes = {10, 12};
        w.Fire();
        assert(w.bot.flights.empty());
    }
    // Taxi cheaters keep the core exemption.
    {
        World w;
        w.bot.taxiCheater = true;
        assert(w.Follow({10, 12}));
        w.Fire();
        assert((w.bot.flights == std::vector<std::vector<uint32>>{{10, 12}}));
    }
    // Without natural progression the upstream follower behavior is unchanged.
    {
        World w(false);
        w.bot.x = 15.0f;
        assert(w.Follow({10, 13, 14}) && w.bot.m_taxi.IsTaximaskNodeKnown(10));
        w.Fire();
        assert((w.bot.flights == std::vector<std::vector<uint32>>{{10, 13, 14}}));
    }
    // Commanded flights list and select only discovered destinations, with bounded indexes.
    {
        World w;
        w.ai.clientMaster = false;
        Event list{"?"};
        assert(w.action.Execute(list));
        assert(w.Said("=== Taxi ===") && w.Said("1: Known") && !w.Said("Unknown") && !w.Said("Other"));
        assert(w.ai.said.size() == 2);
        assert((w.action.Execute(Event{"1"}) && w.bot.flights == std::vector<std::vector<uint32>>{{10, 11}}));
        for (char const* index : {"2", "3", "99"})
            assert(!w.action.Execute(Event{index}));
        assert(w.bot.flights.size() == 1);
    }
    {
        World w(false);
        w.ai.clientMaster = false;
        assert(w.action.Execute(Event{"?"}) && w.Said("1: Known") && w.Said("2: Unknown") && w.Said("3: Other"));
        assert((w.action.Execute(Event{"2"}) && w.bot.flights == std::vector<std::vector<uint32>>{{10, 12}}));
        assert(!w.action.Execute(Event{"4"}));
    }
    // Remembered routes for bot-led groups follow the same rule.
    {
        World w;
        w.ai.clientMaster = false;
        assert(!w.Follow({10, 12}) && w.bot.flights.empty() && w.context.movement.taxiNodes.empty());
        assert(w.ai.errors == std::vector<std::string>{"I can't fly with you"});
        assert((w.Follow({10, 11}) && w.bot.flights == std::vector<std::vector<uint32>>{{10, 11}}));
    }

    // The shared rule matches the native express-taxi handler for every valid node list.
    sPlayerbotAIConfig.naturalProgression = true;
    {
        Player player;
        Creature npc;
        npc.guid.raw = 0xF1300000000E0099ULL;
        ObjectAccessor::creatures.clear();
        ObjectAccessor::creatures[{0, npc.guid}] = &npc;
        uint32 accepted = 0, rejected = 0;
        for (int sample = 0; sample < 20000; ++sample)
        {
            player.m_taxi.m_taximask = {};
            player.taxiCheater = urand(0, 9) == 0;
            for (int known = urand(0, 40); known > 0; --known)
                player.m_taxi.SetTaximaskNode(urand(0, 1) ? urand(1, 40) : urand(1, TaxiMaskSize * 32));
            std::vector<uint32> nodes;
            for (int count = urand(1, 5); count > 0; --count)
                nodes.push_back(urand(0, 3) ? urand(1, 40) : urand(1, TaxiMaskSize * 32));
            bool const rule = CanUseTaxiNodes(&player, nodes);
            assert(rule == CoreAccepts(player, npc, nodes));
            ++(rule ? accepted : rejected);
        }
        assert(accepted > 1000 && rejected > 1000);
        player.m_taxi.m_taximask.fill(~0u);
        for (uint32 invalid : {0u, uint32(TaxiMaskSize * 32 + 1), 100000u, ~0u})
            assert(!CanUseTaxiNodes(&player, {invalid}));
        sPlayerbotAIConfig.naturalProgression = false;
        player.m_taxi.m_taximask = {};
        assert(CanUseTaxiNodes(&player, {12, 13}));
        sPlayerbotAIConfig.naturalProgression = true;
    }

    // Autonomous route selection: the origin is learned on arrival; later nodes must be discovered.
    {
        TravelMgr travel;
        TravelMgr::FlightMasterInfo origin{{0, 0.0f}, 40, 10, 3838, 1};
        travel.nearest = &origin;
        travel.allianceFlightMasterCache = {
            {1, origin}, {2, {{0, 900.0f}, 41, 11, 3839, 2}}, {3, {{0, 950.0f}, 41, 12, 3840, 3}},
            {4, {{0, 990.0f}, 42, 14, 3841, 4}}};
        travel.zone2LevelBracket = {{40, {15, 25}}, {41, {15, 25}}, {42, {15, 25}}};
        sTravelNodeMap.paths = {{{10, 11}, {10, 11}}, {{10, 12}, {10, 12}}, {{10, 14}, {10, 13, 14}}};
        sTaxiNodesStore.rows = {{10, {}}, {11, {}}, {12, {}}, {13, {}}, {14, {}}};
        sAreaTableStore.rows = {{40, {0}}};
        auto destinations = [&](Player& bot)
        {
            std::set<std::vector<uint32>> seen;
            for (int sample = 0; sample < 300; ++sample)
            {
                auto result = travel.GetOptimalFlightDestinations(&bot);
                assert(result.size() <= 1);
                seen.insert(result.empty() ? std::vector<uint32>{} : result[0]);
            }
            return seen;
        };
        Player bot;
        assert((destinations(bot) == std::set<std::vector<uint32>>{{}}));
        bot.m_taxi.SetTaximaskNode(11);
        assert((destinations(bot) == std::set<std::vector<uint32>>{{10, 11}}));
        bot.m_taxi.SetTaximaskNode(14);
        assert((destinations(bot) == std::set<std::vector<uint32>>{{10, 11}}));
        bot.m_taxi.SetTaximaskNode(13);
        assert((destinations(bot) == std::set<std::vector<uint32>>{{10, 11}, {10, 13, 14}}));
        assert(!bot.m_taxi.IsTaximaskNodeKnown(10));
        sPlayerbotAIConfig.naturalProgression = false;
        Player stock;
        assert((destinations(stock) == std::set<std::vector<uint32>>{{10, 11}, {10, 12}, {10, 13, 14}}));
        sPlayerbotAIConfig.naturalProgression = true;
    }

    // Autonomous take-off learns the origin like a player, then refuses undiscovered stops.
    for (bool natural : {true, false})
        for (bool knowsStop : {false, true})
        {
            World w(natural);
            w.bot.m_taxi.SetTaximaskNode(14);
            if (knowsStop)
                w.bot.m_taxi.SetTaximaskNode(13);
            NewRpgTravelFlightAction flight(&w.ai);
            w.ai.rpgInfo.data = NewRpgInfo::TravelFlight{w.flightMaster.entry, {0, 0.0f}, {10, 13, 14}, false};
            assert(flight.Execute(Event{}));
            assert(w.bot.m_taxi.IsTaximaskNodeKnown(10) && scriptManager.learned == std::vector<uint32>{10});
            bool const flies = knowsStop || !natural;
            assert(w.bot.flights.size() == (flies ? 1u : 0u));
            assert(std::holds_alternative<NewRpgInfo::TravelFlight>(w.ai.rpgInfo.data) == flies);
        }
    {
        World w;
        NewRpgTravelFlightAction flight(&w.ai);
        w.ai.rpgInfo.data = NewRpgInfo::TravelFlight{w.flightMaster.entry, {0, 0.0f}, {10, 11}, false};
        assert((flight.Execute(Event{}) && w.bot.flights == std::vector<std::vector<uint32>>{{10, 11}}));
    }
    std::cout << "Natural taxi routes: follower, commanded and autonomous flights use discovered nodes and native interaction\n";
}
'''


COMPILE = ['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-g', '-O1', '-D_GLIBCXX_ASSERTIONS',
           '-fsanitize=address,undefined', '-fno-omit-frame-pointer']


def build(directory, sources, name):
    (directory / 'production.cpp').write_text(
        '#include "Fixture.h"\n' + native + '\n' + '\n'.join(sources.values()) + '\n')
    executable = directory / name
    subprocess.run(COMPILE + ['-I', str(directory), str(directory / 'production.cpp'), str(directory / 'tests.o'),
                              '-o', str(executable)], check=True)
    return subprocess.run([str(executable)], timeout=60, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1:abort_on_error=1',
                               'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'})


mutations = [
    ('undiscovered nodes accepted', 'route', 'if (!sPlayerbotAIConfig.naturalProgression || player->isTaxiCheater())',
     'if (true)'),
    ('invalid node ids read the taxi mask', 'route', '!node || node > TaxiMaskSize * 32 || ', ''),
    ('follower learns and flies from 15 yards', 'taxi',
     'sPlayerbotAIConfig.naturalProgression ? !bot->GetNPCIfCanInteractWith', 'false ? !bot->GetNPCIfCanInteractWith'),
    ('commanded list offers undiscovered routes', 'taxi',
     'field < TaxiMaskSize && CanUseTaxiNodes(bot, {entry->from, entry->to})', 'field < TaxiMaskSize'),
    ('follower route accepted without explanation', 'taxi', 'if (!CanUseTaxiNodes(bot, movement.taxiNodes))\n',
     'if (false)\n'),
    ('delayed take-off skips interaction', 'taxi',
     '? bot->GetNPCIfCanInteractWith(npcGuid, UNIT_NPC_FLAG_FLIGHTMASTER)', '? ObjectAccessor::GetCreature(*bot, npcGuid)'),
    ('delayed take-off skips route', 'taxi',
     '!movement.taxiNodes.empty() && CanUseTaxiNodes(bot, movement.taxiNodes))', '!movement.taxiNodes.empty())'),
    ('selected index unchecked', 'taxi', 'if (selected > nodes.size())', 'if (false)'),
    ('remembered route accepted', 'taxi', '(!CanUseTaxiNodes(bot, movement.taxiNodes) || ', '('),
    ('autonomous selection uses undiscovered stops', 'select',
     'CanUseTaxiNodes(bot, std::vector<uint32>(path.begin() + 1, path.end()))', 'true'),
    ('autonomous selection requires an unvisited origin', 'select',
     'std::vector<uint32>(path.begin() + 1, path.end())', 'path'),
    ('autonomous take-off skips route', 'flight', '!CanUseTaxiNodes(bot, nodes) || ', ''),
]

with tempfile.TemporaryDirectory(prefix='portable-natural-taxi-') as temporary:
    temporary = Path(temporary)
    (temporary / 'Fixture.h').write_text('#pragma once\n' + fixture)
    (temporary / 'tests.cpp').write_text(tests)
    subprocess.run(COMPILE + ['-c', '-I', str(temporary), str(temporary / 'tests.cpp'), '-o', str(temporary / 'tests.o')],
                   check=True)
    result = build(temporary, production, 'natural-taxi')
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit(f'Natural taxi fixture failed (exit {result.returncode})')
    for label, key, old, new in mutations:
        mutated = dict(production)
        mutated[key] = production[key].replace(old, new)
        if mutated[key] == production[key]:
            raise SystemExit(f'{label} mutation was not applied')
        if not build(temporary, mutated, 'mutant').returncode:
            raise SystemExit(f'Natural taxi fixture did not reject: {label}')
        print(f'Natural taxi mutation rejected: {label}')
