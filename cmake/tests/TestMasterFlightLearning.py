"""Exercise follower flight-point learning against isolated native core fixtures.

The actual action, packet forwarding and strategy execute with the core's real
WorldPacket, ByteBuffer and ObjectGuid types. Native interaction and taxi-node
methods supply their own guards; fixtures provide NPC/world state and recording
sessions. This does not launch a realm or replace the full Windows build.
"""

from pathlib import Path
import argparse
import os
import re
import subprocess
import tempfile

from PreparedSources import prepared_core


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    cursor = opening + 1
    while depth:
        depth += (source[cursor] == '{') - (source[cursor] == '}')
        cursor += 1
    return source[start:cursor]


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, help='prepared Playerbots src directory')
parser.add_argument('--core', type=Path, help='prepared core source directory')
args = parser.parse_args()
repository = Path(__file__).resolve().parents[2]
core = args.core or prepared_core(repository)
module = args.source or core / 'modules/mod-playerbots/src'

ai = (module / 'Bot/PlayerbotAI.cpp').read_text()
ai_header = (module / 'Bot/PlayerbotAI.h').read_text()
manager = (module / 'Bot/PlayerbotMgr.cpp').read_text()
packet = (core / 'src/server/shared/Packets/ByteBuffer.cpp').read_text()
guid = (core / 'src/server/game/Entities/Object/ObjectGuid.cpp').read_text()
player = (core / 'src/server/game/Entities/Player/Player.cpp').read_text()
taxi = (core / 'src/server/game/Handlers/TaxiHandler.cpp').read_text()
taxi_header = (core / 'src/server/game/Entities/Player/PlayerTaxi.h').read_text()
external = (module / 'Bot/Engine/ExternalEventHelper.cpp').read_text()

action_context = (module / 'Ai/Base/WorldPacketActionContext.h').read_text()
trigger_context = (module / 'Ai/Base/WorldPacketTriggerContext.h').read_text()
assert 'creators["learn taxi"] = &WorldPacketActionContext::learn_taxi;' in action_context
assert 'return new LearnTaxiAction(botAI);' in action_context
assert 'creators["learn taxi"] = &WorldPacketTriggerContext::learn_taxi;' in trigger_context
assert 'return new WorldPacketTrigger(botAI, "learn taxi");' in trigger_context

registrations = '\n'.join(re.findall(
    r'^    (?:masterIncomingPacketHandlers\.AddHandler|_masterTaxiPacketHandlers\.emplace)\([^\n]+$',
    ai, re.MULTILINE))
assert registrations.count('_masterTaxiPacketHandlers.emplace') == 2
pending_start = ai.index('    if (_masterTaxiPacketPending.load())')
pending_end = ai.index('\n    masterOutgoingPacketHandlers.Handle(helper);', pending_start)
pending_delivery = ai[pending_start:pending_end]
pending_fields_start = ai_header.index('    std::map<uint16, std::string> _masterTaxiPacketHandlers;')
pending_fields_end = ai_header.index('\n\n', pending_fields_start)
pending_fields = ai_header[pending_fields_start:pending_fields_end]
manager_delivery = function(manager, 'void PlayerbotMgr::HandleMasterIncomingPacket')
manager_delivery = manager_delivery[:manager_delivery.index('    switch (packet.GetOpcode())')] + '}\n'

fixture = r'''
#pragma once
#include <atomic>
#include <cassert>
#include <chrono>
#include <cmath>
#include <future>
#include <iostream>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <set>
#include <sstream>
#include <stack>
#include <string>
#include <thread>
#include <vector>
#include "WorldPacket.h"
#include "ObjectGuid.h"
#include "Event.h"
#define ASSERT(condition, ...) assert(condition)
#define GET_PLAYERBOT_AI(player) ((player) ? (player)->botAI : nullptr)

constexpr uint32 UNIT_NPC_FLAG_FLIGHTMASTER = 1;
constexpr uint32 CREATURE_TYPE_FLAG_VISIBLE_TO_GHOSTS = 1;
constexpr uint32 CREATURE_TYPE_FLAG_INTERACT_WHILE_DEAD = 2;
constexpr int REP_UNFRIENDLY = 2;
constexpr float INTERACTION_DISTANCE = 5.0f;
enum NPCFlags : uint32 { FlightMasterFlag = UNIT_NPC_FLAG_FLIGHTMASTER };

class Player;
class PlayerbotAI;
class Creature;
class ExternalEventHelper;
struct CreatureTemplate { uint32 type_flags = 0; };

class Creature
{
public:
    ObjectGuid guid;
    uint32 mapId = 0;
    float x = 0.0f;
    bool alive = true;
    uint32 flags = UNIT_NPC_FLAG_FLIGHTMASTER;
    int reaction = 4;
    ObjectGuid charmer;
    uint32 node[2] = {17, 25};
    CreatureTemplate creatureTemplate;
    bool IsAlive() const { return alive; }
    bool HasNpcFlag(NPCFlags required) const { return (flags & required) == required; }
    int GetReactionTo(Player*) const { return reaction; }
    ObjectGuid GetCharmerGUID() const { return charmer; }
    CreatureTemplate const* GetCreatureTemplate() const { return &creatureTemplate; }
    bool IsWithinDistInMap(Player* player, float distance) const;
    ObjectGuid GetGUID() const { return guid; }
};

class TaxiMaskFixture
{
public:
    std::array<uint32, 16> m_taximask{};
    TAXI_IS_KNOWN
    TAXI_SET_KNOWN
};

class WorldSession
{
public:
    Player* player = nullptr;
    std::vector<WorldPacket> sent;
    Player* GetPlayer() { return player; }
    void SendPacket(WorldPacket const* packet) { sent.push_back(*packet); }
    bool SendLearnNewTaxiNode(Creature* creature);
};

class Player
{
public:
    ObjectGuid guid;
    uint32 mapId = 0;
    uint32 team = 0;
    uint32 instanceId = 0;
    float x = 0.0f;
    bool alive = true;
    bool inWorld = true;
    bool inFlight = false;
    bool beingTeleported = false;
    uint32 money = 123456;
    PlayerbotAI* botAI = nullptr;
    TaxiMaskFixture m_taxi;
    WorldSession session;
    Player() { session.player = this; }
    bool IsAlive() const { return alive; }
    bool IsInWorld() const { return inWorld; }
    bool IsInFlight() const { return inFlight; }
    bool IsBeingTeleported() const { return beingTeleported; }
    void const* GetMap() const
    {
        return reinterpret_cast<void const*>(std::uintptr_t(1 + mapId + instanceId * 65536));
    }
    uint32 GetTeamId(bool = false) const { return team; }
    ObjectGuid GetGUID() const { return guid; }
    WorldSession* GetSession() { return &session; }
    Creature* GetNPCIfCanInteractWith(ObjectGuid const& guid, uint32 npcflagmask);
};

inline bool Creature::IsWithinDistInMap(Player* player, float distance) const
{
    return player->mapId == mapId && std::abs(player->x - x) <= distance;
}

namespace ObjectAccessor
{
    inline std::map<std::pair<uint32, ObjectGuid>, Creature*> creatures;
    inline Creature* GetCreatureOrPetOrVehicle(Player& player, ObjectGuid guid)
    {
        auto found = creatures.find({player.mapId, guid});
        return found == creatures.end() ? nullptr : found->second;
    }
}
struct ObjectManager
{
    uint32 GetNearestTaxiNode(Creature& creature, uint32 team) { return creature.node[team]; }
};
inline ObjectManager objectManager;
#define sObjectMgr (&objectManager)
struct ScriptManager
{
    std::vector<std::pair<Player*, uint32>> learned;
    void OnPlayerLearnTaxiNode(Player* player, uint32 node) { learned.emplace_back(player, node); }
};
inline ScriptManager scriptManager;
#define sScriptMgr (&scriptManager)
struct PlayerbotAIConfig { bool LearnFlightPathsWithMaster = false; };
inline PlayerbotAIConfig playerbotAIConfig;
#define sPlayerbotAIConfig playerbotAIConfig
bool IsRealPlayer(Player* player);

PACKET_HELPER

class PlayerbotAI
{
public:
    Player* bot;
    Player* master;
    PacketHandlingHelper masterIncomingPacketHandlers;
PENDING_FIELDS
    PlayerbotAI(Player* bot, Player* master) : bot(bot), master(master)
    {
        bot->botAI = this;
        REGISTRATIONS
    }
    Player* GetMaster() { return master; }
    void HandleMasterIncomingPacket(WorldPacket const& packet, Player* packetMaster = nullptr);
    void DeliverTaxiPacket(ExternalEventHelper& helper);
};

class Action
{
public:
    Action(PlayerbotAI* ai, std::string const&) : botAI(ai), bot(ai->bot) {}
    virtual ~Action() = default;
    virtual bool isUseful() { return true; }
    virtual bool Execute(Event) { return true; }
    Player* GetMaster() { return botAI->GetMaster(); }
protected:
    PlayerbotAI* botAI;
    Player* bot;
};

class Trigger
{
public:
    Trigger(PlayerbotAI*, std::string name) : name(std::move(name)) {}
    virtual ~Trigger() = default;
    virtual void ExternalEvent(WorldPacket&, Player* = nullptr) {}
    virtual void ExternalEvent(std::string const&, Player* = nullptr) {}
    virtual Event Check() { return {}; }
    virtual void Reset() {}
    std::string getName() { return name; }
private:
    std::string name;
};
class AiObjectContext
{
public:
    std::unique_ptr<Trigger> learn;
    explicit AiObjectContext(PlayerbotAI* ai);
    Trigger* GetTrigger(std::string const& name) { return name == "learn taxi" ? learn.get() : nullptr; }
};
class ExternalEventHelper
{
public:
    AiObjectContext* aiObjectContext;
    ExternalEventHelper(AiObjectContext* context) : aiObjectContext(context) {}
    void HandlePacket(std::map<uint16, std::string>& handlers, WorldPacket const& packet, Player* owner = nullptr);
};

using PlayerBotMap = std::map<ObjectGuid, Player*>;
class PlayerbotMgr
{
public:
    Player* master;
    PlayerBotMap bots;
    explicit PlayerbotMgr(Player* master) : master(master) {}
    Player* GetMaster() { return master; }
    auto GetPlayerBotsBegin() const { return bots.begin(); }
    auto GetPlayerBotsEnd() const { return bots.end(); }
    void HandleMasterIncomingPacket(WorldPacket const& packet);
};
inline PlayerbotMgr randomManager(nullptr);
#define sRandomPlayerbotMgr randomManager

class NextAction
{
public:
    std::string name;
    NextAction(std::string name, float = 0.0f) : name(std::move(name)) {}
};
class TriggerNode
{
public:
    std::string name;
    std::vector<NextAction> actions;
    TriggerNode(std::string name, std::vector<NextAction> actions) : name(std::move(name)), actions(std::move(actions)) {}
};
class PassThroughStrategy
{
public:
    std::vector<std::string> supported;
    float relevance = 1.0f;
    explicit PassThroughStrategy(PlayerbotAI*) {}
    virtual ~PassThroughStrategy() = default;
    virtual void InitTriggers(std::vector<TriggerNode*>&) {}
    virtual std::string const getName() { return ""; }
};
'''

fixture = fixture.replace('TAXI_IS_KNOWN', function(taxi_header, '[[nodiscard]] bool IsTaximaskNodeKnown'))
fixture = fixture.replace('TAXI_SET_KNOWN', function(taxi_header, 'bool SetTaximaskNode'))
fixture = fixture.replace('PACKET_HELPER', function(ai_header, 'class PacketHandlingHelper') + ';')
fixture = fixture.replace('PENDING_FIELDS', pending_fields)
fixture = fixture.replace('REGISTRATIONS', registrations)

tests = r'''
#include "Fixture.h"
#include "LearnTaxiAction.h"
#include "WorldPacketHandlerStrategy.h"

struct Scenario
{
    Player master;
    Player bot;
    Creature flightMaster;
    Creature otherFlightMaster;
    PlayerbotAI ai;
    PlayerbotMgr manager;
    AiObjectContext context;
    ExternalEventHelper helper;
    LearnTaxiAction action;
    Scenario() : ai(&bot, &master), manager(&master), context(&ai), helper(&context), action(&ai)
    {
        master.guid.Set(0x1122334455667788ULL);
        bot.guid.Set(200);
        flightMaster.guid.Set(0xF130000011003344ULL);
        otherFlightMaster.guid.Set(0xF130000022003355ULL);
        otherFlightMaster.node[0] = 18;
        ObjectAccessor::creatures.clear();
        ObjectAccessor::creatures[{0, flightMaster.guid}] = &flightMaster;
        ObjectAccessor::creatures[{0, otherFlightMaster.guid}] = &otherFlightMaster;
        manager.bots.emplace(bot.guid, &bot);
        randomManager.bots.clear();
        scriptManager.learned.clear();
        sPlayerbotAIConfig.LearnFlightPathsWithMaster = true;
    }
    WorldPacket Click(uint16 opcode = CMSG_GOSSIP_HELLO)
    {
        WorldPacket packet(opcode);
        packet << flightMaster.guid;
        assert(packet.size() == 8);
        return packet;
    }
    bool Deliver()
    {
        ai.DeliverTaxiPacket(helper);
        Event event = context.learn->Check();
        context.learn->Reset();
        return !(!event) && action.isUseful() && action.Execute(event);
    }
    bool ClickAndLearn(uint16 opcode = CMSG_GOSSIP_HELLO)
    {
        auto packet = Click(opcode);
        manager.HandleMasterIncomingPacket(packet);
        assert(packet.size() == 8 && packet.rpos() == 0 && packet.wpos() == 8);
        return Deliver();
    }
    void Unchanged()
    {
        assert(!bot.m_taxi.IsTaximaskNodeKnown(17));
        assert(!bot.m_taxi.IsTaximaskNodeKnown(18));
        assert(scriptManager.learned.empty());
        assert(bot.session.sent.empty());
        assert(bot.money == 123456);
    }
};

int main()
{
    // Real GUID/packet encoding and both native click opcodes, for both factions.
    for (uint16 opcode : {uint16(CMSG_GOSSIP_HELLO), uint16(CMSG_TAXIQUERYAVAILABLENODES)})
        for (uint32 team : {0u, 1u})
        {
            Scenario s;
            s.bot.team = team;
            auto packet = s.Click(opcode);
            assert(packet.contents()[0] == 0x44 && packet.contents()[7] == 0xF1);
            s.manager.HandleMasterIncomingPacket(packet);
            assert(s.ai._masterTaxiPacketPending.load());
            assert(s.ai._pendingMasterTaxiPacket->size() == 16);
            assert(s.ai._pendingMasterTaxiPacket->contents()[8] == 0x88);
            assert(s.ai._pendingMasterTaxiPacket->contents()[15] == 0x11);
            assert(s.Deliver());
            assert(!s.ai._masterTaxiPacketPending.load() && !s.ai._pendingMasterTaxiPacket);
            uint32 node = s.flightMaster.node[team];
            assert(s.bot.m_taxi.IsTaximaskNodeKnown(node));
            assert(!s.bot.m_taxi.IsTaximaskNodeKnown(18));
            assert(scriptManager.learned.size() == 1 && scriptManager.learned[0].second == node);
            assert(!s.master.m_taxi.IsTaximaskNodeKnown(node));
            assert(s.bot.session.sent.size() == 2);
            assert(s.bot.session.sent[0].GetOpcode() == SMSG_NEW_TAXI_PATH);
            assert(s.ClickAndLearn(opcode));
            assert(scriptManager.learned.size() == 1 && s.bot.session.sent.size() == 2);
            assert(s.bot.money == 123456 && !s.bot.inFlight);
        }

    // Core guards independently reject impossible interaction for either party.
    for (bool masterSide : {false, true})
        for (int condition = 0; condition < 8; ++condition)
        {
            Scenario s;
            Player& player = masterSide ? s.master : s.bot;
            if (condition == 0) player.mapId = 1;
            if (condition == 1) player.x = INTERACTION_DISTANCE + 0.01f;
            if (condition == 2) player.alive = false;
            if (condition == 3) player.inWorld = false;
            if (condition == 4) player.inFlight = true;
            if (condition == 5) s.flightMaster.reaction = REP_UNFRIENDLY;
            if (condition == 6) player.beingTeleported = true;
            if (condition == 7) player.instanceId = 1;
            assert(!s.ClickAndLearn());
            s.Unchanged();
            assert(player.inFlight == (condition == 4));
        }
    {
        Scenario s;
        s.bot.x = INTERACTION_DISTANCE;
        assert(s.ClickAndLearn());
    }
    {
        Scenario s;
        auto click = s.Click();
        click.rpos(click.size());
        s.manager.HandleMasterIncomingPacket(click);
        assert(click.rpos() == 8 && click.size() == 8);
        assert(s.Deliver());
    }
    {
        Scenario s;
        s.flightMaster.node[0] = 0;
        assert(s.ClickAndLearn());
        s.Unchanged();
    }
    for (int condition = 0; condition < 6; ++condition)
    {
        Scenario s;
        if (condition == 0) s.flightMaster.flags = 0;
        if (condition == 1) s.flightMaster.alive = false;
        if (condition == 2) s.flightMaster.charmer.Set(77);
        if (condition == 3) ObjectAccessor::creatures.erase({0, s.flightMaster.guid});
        if (condition == 4) s.flightMaster.guid.Set(0);
        if (condition == 5)
        {
            s.bot.mapId = 1;
            s.otherFlightMaster.mapId = 1;
            s.otherFlightMaster.guid = s.flightMaster.guid;
            ObjectAccessor::creatures[{1, s.flightMaster.guid}] = &s.otherFlightMaster;
        }
        assert(!s.ClickAndLearn());
        s.Unchanged();
    }

    // Idle bot updates must complete even while another thread holds the event mutex.
    for (bool enabled : {false, true})
    {
        Scenario s;
        sPlayerbotAIConfig.LearnFlightPathsWithMaster = enabled;
        assert(!s.ai._masterTaxiPacketPending.load());
        std::unique_lock<std::mutex> held(s.ai._masterTaxiPacketMutex);
        std::promise<void> started;
        std::promise<void> finished;
        auto startedFuture = started.get_future();
        auto finishedFuture = finished.get_future();
        std::thread update([&]
        {
            started.set_value();
            s.ai.DeliverTaxiPacket(s.helper);
            finished.set_value();
        });
        startedFuture.wait();
        bool completedWithoutMutex = finishedFuture.wait_for(std::chrono::seconds(2)) == std::future_status::ready;
        held.unlock();
        update.join();
        assert(completedWithoutMutex);
        s.Unchanged();
    }

    // The feature is opt-in and pending events cannot survive disabling it.
    {
        Scenario s;
        sPlayerbotAIConfig.LearnFlightPathsWithMaster = false;
        assert(!s.ClickAndLearn());
        s.Unchanged();
    }
    {
        Scenario s;
        s.manager.HandleMasterIncomingPacket(s.Click());
        sPlayerbotAIConfig.LearnFlightPathsWithMaster = false;
        assert(!s.Deliver());
        assert(!s.ai._masterTaxiPacketPending.load() && !s.ai._pendingMasterTaxiPacket);
        sPlayerbotAIConfig.LearnFlightPathsWithMaster = true;
        assert(!s.Deliver());
        s.Unchanged();
    }

    // Packet identity is retained across ticks; no learning from another master.
    {
        Scenario s;
        s.manager.HandleMasterIncomingPacket(s.Click());
        Player replacement;
        replacement.guid.Set(999);
        s.ai.master = &replacement;
        assert(!s.Deliver());
        s.Unchanged();
    }
    {
        Scenario s;
        Player impostor;
        impostor.guid.Set(999);
        s.ai.HandleMasterIncomingPacket(s.Click(), &impostor);
        assert(!s.ai._pendingMasterTaxiPacket && !s.Deliver());
        s.Unchanged();
    }
    {
        Scenario s;
        s.ai.HandleMasterIncomingPacket(s.Click());
        assert(!s.ai._pendingMasterTaxiPacket && !s.Deliver());
        s.Unchanged();
    }
    {
        Scenario s;
        Player masterBot;
        PlayerbotAI masterAI(&s.master, &masterBot);
        assert(!s.ClickAndLearn());
        s.Unchanged();
    }

    // Owned altbots and recruited playerbots share support. Nearby free bots do not.
    {
        Scenario s;
        s.manager.bots.clear();
        randomManager.bots.emplace(s.bot.guid, &s.bot);
        assert(s.ClickAndLearn());
    }
    {
        Scenario s;
        s.manager.bots.clear();
        s.ai.master = nullptr;
        randomManager.bots.emplace(s.bot.guid, &s.bot);
        assert(!s.ClickAndLearn());
        s.Unchanged();
    }

    // Strict wire-size/opcode checks and bounded last-click coalescing.
    for (std::size_t size : {0u, 1u, 7u, 9u, 16u, 1024u})
    {
        Scenario s;
        WorldPacket invalid(CMSG_GOSSIP_HELLO);
        std::vector<uint8> bytes(size, 0x11);
        if (size) invalid.append(bytes.data(), bytes.size());
        s.manager.HandleMasterIncomingPacket(invalid);
        assert(!s.ai._pendingMasterTaxiPacket && !s.Deliver());
        s.Unchanged();
    }
    for (uint16 opcode : {uint16(CMSG_TAXINODE_STATUS_QUERY), uint16(CMSG_ACTIVATETAXI), uint16(CMSG_QUESTGIVER_HELLO)})
    {
        Scenario s;
        assert(!s.ClickAndLearn(opcode));
        s.Unchanged();
    }
    {
        Scenario s;
        auto invalid = s.Click(CMSG_ACTIVATETAXI);
        invalid << s.master.guid;
        Event event("learn taxi", invalid);
        assert(!s.action.Execute(event));
        s.Unchanged();
    }
    {
        Scenario s;
        WorldPacket click = s.Click(CMSG_TAXIQUERYAVAILABLENODES);
        for (int index = 0; index < 10000; ++index)
        {
            s.manager.HandleMasterIncomingPacket(click);
            assert(s.ai._pendingMasterTaxiPacket->size() == 16);
        }
        WorldPacket last(CMSG_TAXIQUERYAVAILABLENODES);
        last << s.otherFlightMaster.guid;
        s.manager.HandleMasterIncomingPacket(last);
        WorldPacket invalid(CMSG_TAXIQUERYAVAILABLENODES);
        invalid << uint8(1);
        s.manager.HandleMasterIncomingPacket(invalid);
        assert(s.Deliver());
        assert(!s.bot.m_taxi.IsTaximaskNodeKnown(17));
        assert(s.bot.m_taxi.IsTaximaskNodeKnown(18));
        assert(scriptManager.learned.size() == 1);
        assert(!s.Deliver());
    }
    // NPC state is revalidated at execution rather than held as a raw pointer.
    {
        Scenario s;
        s.manager.HandleMasterIncomingPacket(s.Click());
        s.bot.x = INTERACTION_DISTANCE + 0.01f;
        assert(!s.Deliver());
        s.Unchanged();
    }
    // Concurrent receive and bot ticks share only the protected pending event.
    {
        Scenario s;
        auto producer = [&s]
        {
            WorldPacket click = s.Click(CMSG_TAXIQUERYAVAILABLENODES);
            for (int index = 0; index < 10000; ++index)
                s.ai.HandleMasterIncomingPacket(click, &s.master);
        };
        std::thread first(producer), second(producer);
        for (int index = 0; index < 10000; ++index)
            s.Deliver();
        first.join();
        second.join();
        s.Deliver();
        assert(!s.ai._masterTaxiPacketPending.load() && !s.ai._pendingMasterTaxiPacket);
        assert(s.bot.m_taxi.IsTaximaskNodeKnown(17));
        assert(!s.bot.m_taxi.IsTaximaskNodeKnown(18));
        assert(scriptManager.learned.size() == 1);
    }

    // The real default strategy queues the registered action alongside original handlers.
    {
        Scenario s;
        WorldPacketHandlerStrategy strategy(&s.ai);
        std::vector<TriggerNode*> triggers;
        strategy.InitTriggers(triggers);
        bool learn = false, gossip = false, taxi = false;
        for (auto* trigger : triggers)
        {
            if (trigger->name == "learn taxi")
                learn = trigger->actions.size() == 1 && trigger->actions[0].name == "learn taxi";
            if (trigger->name == "gossip hello")
                gossip = trigger->actions.size() == 1 && trigger->actions[0].name == "trainer";
            if (trigger->name == "activate taxi")
                taxi = trigger->actions.size() == 2 && trigger->actions[0].name == "remember taxi" &&
                       trigger->actions[1].name == "taxi";
            delete trigger;
        }
        assert(learn && gossip && taxi);
    }
    std::cout << "Follower flight-point learning: native packets, interaction guards, ownership, coalescing and idempotence passed\n";
}
'''

production = '\n'.join([
    function(packet, 'ByteBufferPositionException::ByteBufferPositionException'),
    function(packet, 'void ByteBuffer::append(uint8 const*'),
    function(guid, 'ByteBuffer& operator<<(ByteBuffer& buf, ObjectGuid const& guid)'),
    function(guid, 'ByteBuffer& operator>>(ByteBuffer& buf, ObjectGuid& guid)'),
    function(player, 'Creature* Player::GetNPCIfCanInteractWith'),
    function(taxi, 'bool WorldSession::SendLearnNewTaxiNode'),
    function(ai, 'bool IsRealPlayer(Player* player)'),
    function(ai, 'void PacketHandlingHelper::AddHandler'),
    function(ai, 'void PacketHandlingHelper::Handle('),
    function(ai, 'void PacketHandlingHelper::AddPacket'),
    function(ai, 'void PlayerbotAI::HandleMasterIncomingPacket'),
    function(external, 'void ExternalEventHelper::HandlePacket'),
    manager_delivery,
    'void PlayerbotAI::DeliverTaxiPacket(ExternalEventHelper& helper)\n{\n' + pending_delivery + '\n}',
])

with tempfile.TemporaryDirectory(prefix='portable-master-flight-') as temporary:
    temporary = Path(temporary)
    (temporary / 'Fixture.h').write_text(fixture)
    for header in ('Action.h', 'Playerbots.h', 'PlayerbotAIConfig.h', 'Trigger.h', 'PassThroughStrategy.h'):
        (temporary / header).write_text('#include "Fixture.h"\n')
    (temporary / 'production.cpp').write_text(
        '#include "Fixture.h"\n#include "WorldPacketTrigger.h"\n'
        'AiObjectContext::AiObjectContext(PlayerbotAI* ai) : learn(std::make_unique<WorldPacketTrigger>(ai, "learn taxi")) {}\n'
        + production)
    (temporary / 'tests.cpp').write_text(tests)
    production_sources = []
    for relative in ('Ai/Base/Actions/LearnTaxiAction', 'Ai/Base/Trigger/WorldPacketTrigger',
                     'Ai/Base/Strategy/WorldPacketHandlerStrategy'):
        for suffix in ('.cpp', '.h'):
            origin = module / (relative + suffix)
            copied = temporary / origin.name
            copied.write_bytes(origin.read_bytes())
            if suffix == '.cpp':
                production_sources.append(str(copied))
    includes = [
        temporary,
        module / 'Ai/Base/Actions',
        module / 'Ai/Base/Trigger',
        module / 'Ai/Base/Strategy',
        module / 'Bot/Engine/WorldPacket',
        core / 'src/common',
        core / 'src/common/Utilities',
        core / 'src/server/shared/Packets',
        core / 'src/server/game/Server',
        core / 'src/server/game/Server/Protocol',
        core / 'src/server/game/Entities/Object',
    ]
    executable = temporary / 'flight-learning'
    command = ['c++', '-std=c++20', '-pthread', '-Wall', '-Wextra', '-Werror', '-g', '-O1',
               '-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    command += [argument for path in includes for argument in ('-I', str(path))]
    command += [str(temporary / 'production.cpp'), str(temporary / 'tests.cpp'),
                *production_sources, '-o', str(executable)]
    subprocess.run(command, check=True)
    subprocess.run([str(executable)], check=True, timeout=30,
                   env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1:abort_on_error=1',
                        'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'})
