"""Exercise follower flight-point learning and home binding against isolated native core fixtures.

The actual actions, packet forwarding and strategy execute with the core's real
WorldPacket, ByteBuffer and ObjectGuid types. Native interaction, taxi-node and
bind-point methods supply their own guards; fixtures provide NPC/world state and
recording sessions. This does not launch a realm or replace the full Windows build.
"""

import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    cxx,
    function,
    prepared_core,
    reject_mutants,
    source_argument,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help='prepared Playerbots src directory')
source_argument(parser, 'core', help='prepared core source directory')
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
npc_handler = (core / 'src/server/game/Handlers/NPCHandler.cpp').read_text()
opcodes = (core / 'src/server/game/Server/Protocol/Opcodes.cpp').read_text()

# A master's bind is one innkeeper GUID that the core checks with the interaction guard companions repeat.
binder = function(npc_handler, 'void WorldSession::HandleBinderActivateOpcode')
assert 'recvData >> npcGUID;' in binder and 'recvData' not in binder.split('recvData >> npcGUID;')[1]
assert 'GetNPCIfCanInteractWith(npcGUID, UNIT_NPC_FLAG_INNKEEPER)' in binder and 'SendBindPoint(unit);' in binder
assert re.search(r'DEFINE_HANDLER\(CMSG_BINDER_ACTIVATE,[^\n]+&WorldSession::HandleBinderActivateOpcode', opcodes)

action_context = (module / 'Ai/Base/WorldPacketActionContext.h').read_text()
trigger_context = (module / 'Ai/Base/WorldPacketTriggerContext.h').read_text()
assert 'creators["learn taxi"] = &WorldPacketActionContext::learn_taxi;' in action_context
assert 'return new LearnTaxiAction(botAI);' in action_context
assert 'creators["learn taxi"] = &WorldPacketTriggerContext::learn_taxi;' in trigger_context
assert 'return new WorldPacketTrigger(botAI, "learn taxi");' in trigger_context
assert 'creators["bind home"] = &WorldPacketActionContext::bind_home;' in action_context
assert 'return new BindHomeAction(botAI);' in action_context
assert 'creators["bind home"] = &WorldPacketTriggerContext::bind_home;' in trigger_context
assert 'return new WorldPacketTrigger(botAI, "bind home");' in trigger_context

registrations = '\n'.join(re.findall(
    r'^    (?:masterIncomingPacketHandlers\.AddHandler|_masterTaxiPacketHandlers\.emplace)\([^\n]+$',
    ai, re.MULTILINE))
assert registrations.count('_masterTaxiPacketHandlers.emplace') == 3
assert '_masterTaxiPacketHandlers.emplace(CMSG_BINDER_ACTIVATE, "bind home");' in registrations
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
constexpr uint32 UNIT_NPC_FLAG_INNKEEPER = 4;
constexpr uint32 CREATURE_TYPE_FLAG_VISIBLE_TO_GHOSTS = 1;
constexpr uint32 CREATURE_TYPE_FLAG_INTERACT_WHILE_DEAD = 2;
constexpr int REP_UNFRIENDLY = 2;
constexpr float INTERACTION_DISTANCE = 5.0f;
enum NPCFlags : uint32 { FlightMasterFlag = UNIT_NPC_FLAG_FLIGHTMASTER, InnkeeperFlag = UNIT_NPC_FLAG_INNKEEPER };

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
    std::vector<std::pair<Player*, uint32>> casts;
    void CastSpell(Player* target, uint32 spellId, bool) { casts.emplace_back(target, spellId); }
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
    Player* _player = nullptr;
    std::vector<WorldPacket> sent;
    Player* GetPlayer() { return _player; }
    void SendPacket(WorldPacket const* packet) { sent.push_back(*packet); }
    bool SendLearnNewTaxiNode(Creature* creature);
    void SendBindPoint(Creature* npc);
};

struct Map
{
    bool instanceable = false;
    bool Instanceable() const { return instanceable; }
};
inline std::map<std::pair<uint32, uint32>, Map> maps;
struct PlayerMenu
{
    int closed = 0;
    void SendCloseGossip() { ++closed; }
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
    PlayerMenu menu;
    PlayerMenu* PlayerTalkClass = &menu;
    Player() { session._player = this; }
    bool IsAlive() const { return alive; }
    bool IsInWorld() const { return inWorld; }
    bool IsInFlight() const { return inFlight; }
    bool IsBeingTeleported() const { return beingTeleported; }
    Map* GetMap() const { return &maps[{mapId, instanceId}]; }
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
struct PlayerbotAIConfig { bool LearnFlightPathsWithMaster = false; bool BindHomeWithMaster = false; };
inline PlayerbotAIConfig playerbotAIConfig;
#define sPlayerbotAIConfig playerbotAIConfig
bool IsRealPlayer(Player* player);
bool IsSelfBot(Player* player);
class PlayerbotTextMgr
{
public:
    static PlayerbotTextMgr& instance()
    {
        static PlayerbotTextMgr texts;
        return texts;
    }
    std::string GetBotTextOrDefault(std::string, std::string defaultText, std::map<std::string, std::string>)
    {
        return defaultText;
    }
};

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
    bool HasGameClientMaster();
    void HandleMasterIncomingPacket(WorldPacket const& packet, Player* packetMaster = nullptr);
    void DeliverTaxiPacket(ExternalEventHelper& helper);
    std::vector<std::string> told;
    bool TellMaster(std::string const text)
    {
        told.push_back(text);
        return true;
    }
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
    std::unique_ptr<Trigger> bind;
    explicit AiObjectContext(PlayerbotAI* ai);
    Trigger* GetTrigger(std::string const& name)
    {
        return name == "learn taxi" ? learn.get() : name == "bind home" ? bind.get() : nullptr;
    }
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
#include "BindHomeAction.h"
#include "LearnTaxiAction.h"
#include "WorldPacketHandlerStrategy.h"

struct Scenario
{
    Player master;
    Player bot;
    Creature flightMaster;
    Creature otherFlightMaster;
    Creature innkeeper;
    PlayerbotAI ai;
    std::unique_ptr<PlayerbotAI> selfMasterAI;
    PlayerbotMgr manager;
    AiObjectContext context;
    ExternalEventHelper helper;
    LearnTaxiAction action;
    BindHomeAction bindAction;
    explicit Scenario(bool selfBotMaster = false)
        : ai(&bot, &master), manager(&master), context(&ai), helper(&context), action(&ai), bindAction(&ai)
    {
        if (selfBotMaster)
            selfMasterAI = std::make_unique<PlayerbotAI>(&master, &master);
        master.guid.Set(0x1122334455667788ULL);
        bot.guid.Set(200);
        flightMaster.guid.Set(0xF130000011003344ULL);
        otherFlightMaster.guid.Set(0xF130000022003355ULL);
        otherFlightMaster.node[0] = 18;
        innkeeper.guid.Set(0xF130000033003366ULL);
        innkeeper.flags = UNIT_NPC_FLAG_INNKEEPER;
        ObjectAccessor::creatures.clear();
        ObjectAccessor::creatures[{0, flightMaster.guid}] = &flightMaster;
        ObjectAccessor::creatures[{0, otherFlightMaster.guid}] = &otherFlightMaster;
        ObjectAccessor::creatures[{0, innkeeper.guid}] = &innkeeper;
        maps.clear();
        manager.bots.emplace(bot.guid, &bot);
        randomManager.bots.clear();
        scriptManager.learned.clear();
        sPlayerbotAIConfig.LearnFlightPathsWithMaster = true;
        sPlayerbotAIConfig.BindHomeWithMaster = true;
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
    WorldPacket Bind()
    {
        WorldPacket packet(CMSG_BINDER_ACTIVATE);
        packet << innkeeper.guid;
        return packet;
    }
    bool DeliverBind()
    {
        ai.DeliverTaxiPacket(helper);
        Event event = context.bind->Check();
        context.bind->Reset();
        return !(!event) && bindAction.isUseful() && bindAction.Execute(event);
    }
    bool ClickAndBind()
    {
        manager.HandleMasterIncomingPacket(Bind());
        return DeliverBind();
    }
    void Unbound()
    {
        assert(innkeeper.casts.empty() && bot.session.sent.empty() && bot.menu.closed == 0 && ai.told.empty());
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
    // Real-client and SelfBot masters support both native click opcodes and factions.
    for (uint16 opcode : {uint16(CMSG_GOSSIP_HELLO), uint16(CMSG_TAXIQUERYAVAILABLENODES)})
        for (uint32 team : {0u, 1u})
            for (bool selfBotMaster : {false, true})
            {
                Scenario s(selfBotMaster);
                assert(IsRealPlayer(&s.master) == !selfBotMaster);
                assert(IsSelfBot(&s.master) == selfBotMaster && s.ai.HasGameClientMaster());
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
    for (bool selfBotMaster : {false, true})
        for (bool masterSide : {false, true})
            for (int condition = 0; condition < 8; ++condition)
            {
                Scenario s(selfBotMaster);
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
    for (bool selfBotMaster : {false, true})
        for (bool replacementSelfBot : {false, true})
        {
            Scenario s(selfBotMaster);
            s.manager.HandleMasterIncomingPacket(s.Click());
            Player replacement;
            replacement.guid.Set(999);
            std::unique_ptr<PlayerbotAI> replacementAI;
            if (replacementSelfBot)
                replacementAI = std::make_unique<PlayerbotAI>(&replacement, &replacement);
            s.ai.master = &replacement;
            assert(s.ai.HasGameClientMaster());
            assert(!s.Deliver());
            s.Unchanged();
        }
    for (bool selfBotMaster : {false, true})
        for (bool impostorSelfBot : {false, true})
        {
            Scenario s(selfBotMaster);
            Player impostor;
            impostor.guid.Set(999);
            std::unique_ptr<PlayerbotAI> impostorAI;
            if (impostorSelfBot)
                impostorAI = std::make_unique<PlayerbotAI>(&impostor, &impostor);
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
        assert(!IsRealPlayer(&s.master) && !IsSelfBot(&s.master) && !s.ai.HasGameClientMaster());
        assert(!s.ClickAndLearn());
        s.Unchanged();
    }
    {
        Scenario s(true);
        s.manager.HandleMasterIncomingPacket(s.Click());
        Player masterBot;
        s.selfMasterAI->master = &masterBot;
        assert(!s.ai.HasGameClientMaster());
        assert(!s.Deliver());
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
    for (uint16 opcode : {uint16(CMSG_TAXINODE_STATUS_QUERY), uint16(CMSG_ACTIVATETAXI), uint16(CMSG_QUESTGIVER_HELLO),
                          uint16(CMSG_BINDER_ACTIVATE)})
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

    // Companions bind at the innkeeper of their master's bind, each speaking to it itself.
    for (bool selfBotMaster : {false, true})
    {
        Scenario s(selfBotMaster);
        s.manager.HandleMasterIncomingPacket(s.Bind());
        assert(s.ai._masterTaxiPacketPending.load() && s.ai._pendingMasterTaxiPacket->size() == 16);
        assert(s.DeliverBind());
        assert(!s.ai._masterTaxiPacketPending.load() && !s.ai._pendingMasterTaxiPacket);
        assert(s.innkeeper.casts.size() == 1 && s.innkeeper.casts[0].first == &s.bot);
        assert(s.innkeeper.casts[0].second == 3286);
        assert(s.bot.session.sent.size() == 1 && s.bot.session.sent[0].GetOpcode() == SMSG_TRAINER_BUY_SUCCEEDED);
        assert(s.bot.menu.closed == 1 && s.master.menu.closed == 0 && s.master.session.sent.empty());
        assert(s.ai.told.size() == 1 && s.ai.told[0] == "This inn is my new home");
        assert(!s.context.learn->Check() && scriptManager.learned.empty() && s.bot.money == 123456);
    }
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
            if (condition == 5) s.innkeeper.reaction = REP_UNFRIENDLY;
            if (condition == 6) player.beingTeleported = true;
            if (condition == 7) player.instanceId = 1;
            assert(!s.ClickAndBind());
            s.Unbound();
        }
    for (int condition = 0; condition < 5; ++condition)
    {
        Scenario s;
        if (condition == 0) s.innkeeper.flags = UNIT_NPC_FLAG_FLIGHTMASTER;
        if (condition == 1) s.innkeeper.alive = false;
        if (condition == 2) s.innkeeper.charmer.Set(77);
        if (condition == 3) ObjectAccessor::creatures.erase({0, s.innkeeper.guid});
        if (condition == 4) maps[{0, 0}].instanceable = true;
        bool const bound = s.ClickAndBind();
        assert(condition == 4 ? bound && s.bot.session.sent.empty() : !bound);
        assert(s.innkeeper.casts.empty() && s.bot.menu.closed == 0);
    }
    {
        Scenario s;
        s.bot.x = INTERACTION_DISTANCE;
        assert(s.ClickAndBind() && s.innkeeper.casts.size() == 1);
    }

    // The bind switch is opt-in, gates queueing, delivery and the action, and leaves flight clicks alone.
    {
        Scenario s;
        sPlayerbotAIConfig.BindHomeWithMaster = false;
        s.manager.HandleMasterIncomingPacket(s.Bind());
        assert(!s.ai._pendingMasterTaxiPacket && !s.bindAction.isUseful() && !s.DeliverBind());
        s.Unbound();
        assert(s.ClickAndLearn());
    }
    {
        Scenario s;
        s.manager.HandleMasterIncomingPacket(s.Bind());
        sPlayerbotAIConfig.BindHomeWithMaster = false;
        s.ai.DeliverTaxiPacket(s.helper);
        assert(!s.ai._pendingMasterTaxiPacket && !s.context.bind->Check());
        s.Unbound();
    }
    {
        Scenario s;
        sPlayerbotAIConfig.LearnFlightPathsWithMaster = false;
        s.manager.HandleMasterIncomingPacket(s.Click());
        assert(!s.ai._pendingMasterTaxiPacket);
        assert(s.ClickAndBind() && s.innkeeper.casts.size() == 1);
        assert(!s.bot.m_taxi.IsTaximaskNodeKnown(17) && scriptManager.learned.empty());
    }

    // Only the bot's own master binds it, checked again at delivery; free bots never follow.
    {
        Scenario s;
        Player impostor;
        impostor.guid.Set(999);
        s.ai.HandleMasterIncomingPacket(s.Bind(), &impostor);
        assert(!s.ai._pendingMasterTaxiPacket && !s.DeliverBind());
        s.Unbound();
    }
    {
        Scenario s;
        s.manager.HandleMasterIncomingPacket(s.Bind());
        Player replacement;
        replacement.guid.Set(999);
        s.ai.master = &replacement;
        assert(s.ai.HasGameClientMaster() && replacement.GetNPCIfCanInteractWith(s.innkeeper.guid, UNIT_NPC_FLAG_INNKEEPER));
        assert(!s.DeliverBind());
        s.Unbound();
    }
    {
        Scenario s;
        s.manager.bots.clear();
        randomManager.bots.emplace(s.bot.guid, &s.bot);
        assert(s.ClickAndBind());
    }
    {
        Scenario s;
        s.manager.bots.clear();
        s.ai.master = nullptr;
        randomManager.bots.emplace(s.bot.guid, &s.bot);
        assert(!s.ClickAndBind());
        s.Unbound();
    }
    for (std::size_t size : {0u, 7u, 9u, 16u})
    {
        Scenario s;
        WorldPacket invalid(CMSG_BINDER_ACTIVATE);
        std::vector<uint8> bytes(size, 0x11);
        if (size) invalid.append(bytes.data(), bytes.size());
        s.manager.HandleMasterIncomingPacket(invalid);
        assert(!s.ai._pendingMasterTaxiPacket && !s.DeliverBind());
        s.Unbound();
    }

    // The real default strategy queues the registered action alongside original handlers.
    {
        Scenario s;
        WorldPacketHandlerStrategy strategy(&s.ai);
        std::vector<TriggerNode*> triggers;
        strategy.InitTriggers(triggers);
        bool learn = false, bind = false, gossip = false, taxi = false;
        for (auto* trigger : triggers)
        {
            if (trigger->name == "learn taxi")
                learn = trigger->actions.size() == 1 && trigger->actions[0].name == "learn taxi";
            if (trigger->name == "bind home")
                bind = trigger->actions.size() == 1 && trigger->actions[0].name == "bind home";
            if (trigger->name == "gossip hello")
                gossip = trigger->actions.size() == 1 && trigger->actions[0].name == "trainer";
            if (trigger->name == "activate taxi")
                taxi = trigger->actions.size() == 2 && trigger->actions[0].name == "remember taxi" &&
                       trigger->actions[1].name == "taxi";
            delete trigger;
        }
        assert(learn && bind && gossip && taxi);
    }
    std::cout << "Follower flight-point learning and home binding: native packets, real/SelfBot masters, interaction guards, ownership, coalescing and idempotence passed\n";
}
'''

production = '\n'.join([
    function(packet, 'ByteBufferPositionException::ByteBufferPositionException'),
    function(packet, 'void ByteBuffer::append(uint8 const*'),
    function(guid, 'ByteBuffer& operator<<(ByteBuffer& buf, ObjectGuid const& guid)'),
    function(guid, 'ByteBuffer& operator>>(ByteBuffer& buf, ObjectGuid& guid)'),
    function(player, 'Creature* Player::GetNPCIfCanInteractWith'),
    function(taxi, 'bool WorldSession::SendLearnNewTaxiNode'),
    function(npc_handler, 'void WorldSession::SendBindPoint'),
    function(ai, 'bool IsRealPlayer(Player* player)'),
    function(ai, 'bool IsSelfBot(Player* player)'),
    function(ai, 'bool PlayerbotAI::HasGameClientMaster()'),
    function(ai, 'void PacketHandlingHelper::AddHandler'),
    function(ai, 'void PacketHandlingHelper::Handle('),
    function(ai, 'void PacketHandlingHelper::AddPacket'),
    function(ai, 'bool RepeatsMasterClick(uint16 opcode)'),
    function(ai, 'void PlayerbotAI::HandleMasterIncomingPacket'),
    function(external, 'void ExternalEventHelper::HandlePacket'),
    manager_delivery,
    'void PlayerbotAI::DeliverTaxiPacket(ExternalEventHelper& helper)\n{\n' + pending_delivery + '\n}',
])

mutations = [
    ('bind without the master at the inn', 'BindHomeAction.cpp',
     'Creature* innkeeper = master->GetNPCIfCanInteractWith(', 'Creature* innkeeper = bot->GetNPCIfCanInteractWith('),
    ('bind without the bot at the inn', 'BindHomeAction.cpp',
     'bot->GetNPCIfCanInteractWith(innkeeperGuid, UNIT_NPC_FLAG_INNKEEPER) != innkeeper', 'false'),
    ('bind for another master', 'BindHomeAction.cpp', 'if (packetMasterGuid != master->GetGUID())', 'if (false)'),
    ('bind while switched off', 'BindHomeAction.cpp', 'return sPlayerbotAIConfig.BindHomeWithMaster && ', 'return '),
    ('binds queued while switched off', 'production.cpp', 'return sPlayerbotAIConfig.BindHomeWithMaster;', 'return true;'),
    ('pending bind delivered after switching off', 'production.cpp',
     'if (taxiPacket && RepeatsMasterClick(taxiPacket->GetOpcode()))', 'if (taxiPacket)'),
    ('flight clicks follow the bind switch', 'production.cpp', 'if (opcode == CMSG_BINDER_ACTIVATE)', 'if (true)'),
]
copied_sources = ('Ai/Base/Actions/LearnTaxiAction', 'Ai/Base/Actions/BindHomeAction', 'Ai/Base/Trigger/WorldPacketTrigger',
                  'Ai/Base/Strategy/WorldPacketHandlerStrategy')


def build(directory, executable):
    includes = [
        directory,
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
    command = [cxx(), '-std=c++20', '-pthread', '-Wall', '-Wextra', '-Werror', '-g', '-O1',
               *SANITIZER_FLAGS]
    command += [argument for path in includes for argument in ('-I', str(path))]
    sources = [directory / 'production.cpp', directory / 'tests.cpp',
               *(directory / (Path(relative).name + '.cpp') for relative in copied_sources)]
    return command + [str(source) for source in sources] + ['-o', str(executable)]


with tempfile.TemporaryDirectory(prefix='portable-master-flight-') as temporary:
    temporary = Path(temporary)
    (temporary / 'Fixture.h').write_text(fixture)
    for header in ('Action.h', 'Playerbots.h', 'PlayerbotAIConfig.h', 'PlayerbotTextMgr.h', 'Trigger.h',
                   'PassThroughStrategy.h'):
        (temporary / header).write_text('#include "Fixture.h"\n')
    (temporary / 'production.cpp').write_text(
        '#include "Fixture.h"\n#include "WorldPacketTrigger.h"\n'
        'AiObjectContext::AiObjectContext(PlayerbotAI* ai)\n'
        '    : learn(std::make_unique<WorldPacketTrigger>(ai, "learn taxi")),\n'
        '      bind(std::make_unique<WorldPacketTrigger>(ai, "bind home")) {}\n'
        + production)
    (temporary / 'tests.cpp').write_text(tests)
    for relative in copied_sources:
        for suffix in ('.cpp', '.h'):
            origin = module / (relative + suffix)
            (temporary / origin.name).write_bytes(origin.read_bytes())
    executable = temporary / 'flight-learning'
    subprocess.run(build(temporary, executable), check=True)
    subprocess.run([str(executable)], check=True, timeout=30,
                   env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1:abort_on_error=1',
                        'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'})
    reject_mutants(temporary, mutations, build, 'Follower home binding')
