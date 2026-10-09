"""Exercise follower exploration through native area-trigger and quest handlers.

The production actions and trigger execute with native WorldPacket/Event types,
radius checks, session handling and quest completion. Fixtures supply world state
and record movement, scripts and persistence; no running realm is required.
"""

from pathlib import Path
import argparse
import os
import re
import resource
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
parser.add_argument('--core', type=Path, help='prepared core source directory')
parser.add_argument('--source', type=Path, help='prepared Playerbots src directory')
parser.add_argument('--baseline', type=Path, help='original pinned Playerbots src directory')
args = parser.parse_args()
repository = Path(__file__).resolve().parents[2]
core = args.core or prepared_core(repository)
module = args.source or core / 'modules/mod-playerbots/src'
baseline = args.baseline or repository / 'mod-playerbots/src'

area_sql = (core / 'data/sql/base/db_world/areatrigger.sql').read_text()
relation_sql = (core / 'data/sql/base/db_world/areatrigger_involvedrelation.sql').read_text()
quest_sql = (core / 'data/sql/base/db_world/quest_template.sql').read_text()
addon_sql = (core / 'data/sql/base/db_world/quest_template_addon.sql').read_text()
assert re.search(r'^\(169,287\),?$', relation_sql, re.MULTILINE)
assert re.search(r'^\(287,[^\n]+,2\),?$', addon_sql, re.MULTILINE)
area_row = re.search(r'^\(169,([^\n]+)\),?$', area_sql, re.MULTILINE)
assert area_row
area_values = area_row.group(1).split(',')
assert len(area_values) == 9 and area_values[0] == '0'
frostmane_trigger = '{169, ' + ', '.join(
    value if index == 0 else f'{float(value)}f' for index, value in enumerate(area_values)) + '}'
quest_columns = re.search(r'CREATE TABLE[^;]+?\((.*?)\) ENGINE=', quest_sql, re.DOTALL)
assert quest_columns
columns = re.findall(r'^\s+`([^`]+)`', quest_columns.group(1), re.MULTILINE)
quest_row = re.search(r'^\(287,([^\n]+)\),?$', quest_sql, re.MULTILINE)
assert quest_row
# Numeric objectives follow four quoted objective labels; the first NPC/count
# are immediately after the two description strings at the end of the title block.
assert ",1123,0,0,0,5,0,0,0," in quest_row.group(0)
assert 'RequiredNpcOrGo1' in columns and 'RequiredNpcOrGoCount1' in columns
areas = {int(row[0]): row for line in area_sql.splitlines()
         if (match := re.fullmatch(r'\((\d+,[^\n]+)\)[,;]?', line))
         for row in [match.group(1).split(',')]}
quest_triggers = []
for trigger_id, quest_id in re.findall(r'^\((\d+),(\d+)\)[,;]?$', relation_sql, re.MULTILINE):
    row = areas[int(trigger_id)]
    entry = '{' + ', '.join(value if index < 2 else f'{float(value)}f'
                            for index, value in enumerate(row)) + '}'
    quest_triggers.append('{' + entry + ', ' + quest_id + '}')

action_context = (module / 'Ai/Base/WorldPacketActionContext.h').read_text()
trigger_context = (module / 'Ai/Base/WorldPacketTriggerContext.h').read_text()
strategy = (module / 'Ai/Base/Strategy/WorldPacketHandlerStrategy.cpp').read_text()
ai = (module / 'Bot/PlayerbotAI.cpp').read_text()
assert 'masterIncomingPacketHandlers.AddHandler(CMSG_AREATRIGGER, "area trigger");' in ai
assert 'creators["reach area trigger"] = &WorldPacketActionContext::reach_area_trigger;' in action_context
assert 'creators["area trigger"] = &WorldPacketActionContext::area_trigger;' in action_context
assert 'creators["within area trigger"] = &WorldPacketTriggerContext::within_area_trigger;' in trigger_context
assert 'TriggerNode("area trigger", { NextAction("reach area trigger", relevance) })' in strategy
assert 'TriggerNode("within area trigger", { NextAction("area trigger", relevance) })' in strategy

player = (core / 'src/server/game/Entities/Player/Player.cpp').read_text()
quest = (core / 'src/server/game/Entities/Player/PlayerQuest.cpp').read_text()
misc = (core / 'src/server/game/Handlers/MiscHandler.cpp').read_text()
position = (core / 'src/server/game/Entities/Object/Position.cpp').read_text()
world_object = (core / 'src/server/game/Entities/Object/Object.cpp').read_text()
packet = (core / 'src/server/shared/Packets/ByteBuffer.cpp').read_text()
quest_def = (core / 'src/server/game/Quests/QuestDef.h').read_text()
object_mgr = (core / 'src/server/game/Globals/ObjectMgr.h').read_text()
manager = (module / 'Bot/PlayerbotMgr.cpp').read_text()
manager_delivery = function(manager, 'void PlayerbotMgr::HandleMasterIncomingPacket')
manager_delivery = manager_delivery[:manager_delivery.index('    switch (packet.GetOpcode())')] + '}\n'
definitions = '\n'.join(function(source, signature) + ';' for source, signature in (
    (quest_def, 'enum QuestStatus : uint8'),
    (quest_def, 'enum QuestSpecialFlags'),
    (quest_def, 'struct QuestStatusData'),
    (object_mgr, 'struct AreaTriggerTeleport'),
    (object_mgr, 'struct AreaTrigger\n'),
))
definitions += '\n' + '\n'.join(re.findall(
    r'^#define (?:MAX_QUEST_LOG_SIZE|QUEST_OBJECTIVES_COUNT|QUEST_ITEM_OBJECTIVES_COUNT) [^\n]+',
    quest_def, re.MULTILINE))
# Array-size macros must precede the native QuestStatusData declaration.
definitions = definitions[definitions.index('#define'):] + '\n' + definitions[:definitions.index('#define')]

fixture = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstring>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>
#include "WorldPacket.h"
#include "Event.h"
#define ASSERT(condition, ...) assert(condition)
#define LOG_DEBUG(...) ((void)0)
#define GET_PLAYERBOT_AI(player) ((player) ? (player)->botAI : nullptr)
NATIVE_DEFINITIONS

constexpr uint32 TEAM_ALLIANCE = 0, FACTION_MASK_ALLIANCE = 1, FACTION_MASK_HORDE = 2;
constexpr uint32 REST_FLAG_IN_TAVERN = 1, UNIT_FIELD_BYTES_2 = 2, UNIT_BYTE2_FLAG_FFA_PVP = 3;
constexpr uint32 LANG_DEBUG_AREATRIGGER_REACHED = 1, STATUS_IN_PROGRESS = 1;
constexpr uint32 ADDITIONAL_SAVING_QUEST_STATUS = 1, TELE_TO_NOT_LEAVE_TRANSPORT = 1;
constexpr uint32 MOVE_RUN = 1, FORCED_MOVEMENT_NONE = 0, IN_MILLISECONDS = 1000;

struct Position
{
    float x = 0.0f, y = 0.0f, z = 0.0f, orientation = 0.0f;
    Position() = default;
    Position(float px, float py, float pz, float ori = 0.0f) : x(px), y(py), z(pz), orientation(ori) {}
    float GetPositionX() const { return x; }
    float GetPositionY() const { return y; }
    float GetPositionZ() const { return z; }
    float GetOrientation() const { return orientation; }
    bool IsWithinBox(Position const& center, float xradius, float yradius, float zradius) const;
};

struct WorldObject : Position
{
    float objectSize = 0.3889999986f;
    float GetObjectSize() const { return objectSize; }
    float GetExactDist(float px, float py, float pz) const
    {
        return std::sqrt((px - x) * (px - x) + (py - y) * (py - y) + (pz - z) * (pz - z));
    }
    float GetDistance(float px, float py, float pz) const;
};

class Player;
class WorldSession;
struct Battleground
{
    uint32 GetStatus() const { return STATUS_IN_PROGRESS; }
    void HandleAreaTrigger(Player*, uint32) {}
};
struct OutdoorPvP { bool HandleAreaTrigger(Player*, uint32) { return false; } };
struct Group { bool isLFGGroup() const { return false; } };
struct Map
{
    enum EnterState
    {
        CAN_ENTER, CANNOT_ENTER_NOT_IN_RAID, CANNOT_ENTER_INSTANCE_BIND_MISMATCH,
        CANNOT_ENTER_TOO_MANY_INSTANCES, CANNOT_ENTER_MAX_PLAYERS, CANNOT_ENTER_ZONE_IN_COMBAT
    };
    bool IsDungeon() const { return false; }
};
struct MapMgr { Map::EnterState PlayerCannotEnter(uint32, Player*, bool) { return Map::CAN_ENTER; } };
struct CorpseLocation { uint32 GetMapId() const { return 0; } };
struct Guid { std::string ToString() const { return "fixture"; } };
struct ReputationMgr { int32 GetReputation(uint32) const { return 0; } };
struct MotionMaster
{
    uint32 moves = 0;
    void MovePoint(uint32, float, float, float, uint32, float, float, bool, bool) { ++moves; }
};

struct Quest
{
    uint32 flags = QUEST_SPECIAL_FLAGS_EXPLORATION_OR_EVENT | QUEST_SPECIAL_FLAGS_KILL;
    uint32 RequiredItemCount[QUEST_ITEM_OBJECTIVES_COUNT]{};
    int32 RequiredNpcOrGo[QUEST_OBJECTIVES_COUNT]{1123, 0, 0, 0};
    uint32 RequiredNpcOrGoCount[QUEST_OBJECTIVES_COUNT]{5, 0, 0, 0};
    bool IsRepeatable() const { return false; }
    bool IsSeasonal() const { return false; }
    bool IsAutoComplete() const { return false; }
    uint32 GetQuestMethod() const { return 2; }
    bool HasSpecialFlag(uint32 flag) const { return (flags & flag) != 0; }
    uint32 GetPlayersSlain() const { return 0; }
    int32 GetRewOrReqMoney() const { return 0; }
    uint32 GetRepObjectiveFaction() const { return 0; }
    int32 GetRepObjectiveValue() const { return 0; }
};
using QuestStatusMap = std::map<uint32, QuestStatusData>;

class PlayerbotAI;
struct Player : WorldObject
{
    PlayerbotAI* botAI = nullptr;
    WorldSession* session = nullptr;
    uint32 mapId = 0, team = TEAM_ALLIANCE;
    bool alive = true, inFlight = false, isDebugAreaTriggers = false, gm = false;
    QuestStatusMap m_QuestStatus;
    std::map<uint32, bool> m_QuestStatusSave;
    std::set<uint32> rewarded;
    uint32 completionPackets = 0, completions = 0, saveMasks = 0, teleports = 0, rests = 0;
    MotionMaster motion;
    uint32 GetMapId() const { return mapId; }
    uint32 GetTeamId(bool) const { return team; }
    bool IsAlive() const { return alive; }
    bool IsInFlight() const { return inFlight; }
    bool IsGameMaster() const { return gm; }
    std::string GetName() const { return "bot"; }
    Guid GetGUID() const { return {}; }
    WorldSession* GetSession() { return session; }
    MotionMaster* GetMotionMaster() { return &motion; }
    float GetSpeed(uint32) const { return 7.0f; }
    bool IsInAreaTriggerRadius(AreaTrigger const* trigger, float delta = 0.0f) const;
    QuestStatus GetQuestStatus(uint32 id) const
    {
        auto found = m_QuestStatus.find(id);
        return found == m_QuestStatus.end() ? QUEST_STATUS_NONE : found->second.Status;
    }
    bool IsQuestRewarded(uint32 id) const { return rewarded.contains(id); }
    uint16 FindQuestSlot(uint32 id) const { return m_QuestStatus.contains(id) ? 0 : MAX_QUEST_LOG_SIZE; }
    bool CanTakeQuest(Quest const*, bool) const { return false; }
    bool CanCompleteQuest(uint32 id, QuestStatusData const* saved = nullptr);
    void AreaExploredOrEventHappens(uint32 id);
    void SendQuestComplete(uint32) { ++completionPackets; }
    void CompleteQuest(uint32 id) { ++completions; m_QuestStatus[id].Status = QUEST_STATUS_COMPLETE; }
    void AdditionalSavingAddMask(uint32) { ++saveMasks; }
    bool HasEnoughMoney(uint32) const { return false; }
    ReputationMgr GetReputationMgr() const { return {}; }
    void SetRestFlag(uint32, uint32) { ++rests; }
    bool HasByteFlag(uint32, uint32, uint32) const { return false; }
    void RemoveByteFlag(uint32, uint32, uint32) {}
    Battleground* GetBattleground() const { return nullptr; }
    OutdoorPvP* GetOutdoorPvP() const { return nullptr; }
    bool HasCorpse() const { return false; }
    CorpseLocation GetCorpseLocation() const { return {}; }
    void ResurrectPlayer(float) {}
    void SpawnCorpseBones() {}
    Group* GetGroup() const { return nullptr; }
    Map* GetMap() const { return nullptr; }
    bool TeleportToEntryPoint() { return false; }
    void TeleportTo(uint32, float, float, float, float, uint32) { ++teleports; }
};

struct ObjectMgr
{
    std::map<uint32, AreaTrigger> areas;
    std::map<uint32, AreaTriggerTeleport> teleports;
    std::map<uint32, uint32> questRelations;
    std::map<uint32, Quest> quests;
    std::set<uint32> taverns;
    AreaTrigger const* GetAreaTrigger(uint32 id) const
    {
        auto found = areas.find(id);
        return found == areas.end() ? nullptr : &found->second;
    }
    AreaTriggerTeleport const* GetAreaTriggerTeleport(uint32 id) const
    {
        auto found = teleports.find(id);
        return found == teleports.end() ? nullptr : &found->second;
    }
    uint32 GetQuestForAreaTrigger(uint32 id) const
    {
        auto found = questRelations.find(id);
        return found == questRelations.end() ? 0 : found->second;
    }
    Quest const* GetQuestTemplate(uint32 id) const
    {
        auto found = quests.find(id);
        return found == quests.end() ? nullptr : &found->second;
    }
    bool IsTavernAreaTrigger(uint32 id, uint32) const { return taverns.contains(id); }
};
struct ScriptMgr
{
    uint32 calls = 0;
    bool handled = false;
    bool OnAreaTrigger(Player*, AreaTrigger const*) { ++calls; return handled; }
    void OnPlayerFfaPvpStateUpdate(Player*, bool) {}
};
struct World { bool IsFFAPvPRealm() const { return false; } };
ObjectMgr objectManager;
ScriptMgr scriptManager;
World world;
MapMgr mapManager;
ObjectMgr* sObjectMgr = &objectManager;
ScriptMgr* sScriptMgr = &scriptManager;
World* sWorld = &world;
MapMgr* sMapMgr = &mapManager;

class WorldSession
{
public:
    Player* _player;
    Player* GetPlayer() { return _player; }
    explicit WorldSession(Player* player) : _player(player) { player->session = this; }
    void HandleAreaTriggerOpcode(WorldPacket& packet);
};
struct ChatHandler
{
    explicit ChatHandler(WorldSession*) {}
    void PSendSysMessage(uint32, uint32) {}
};
bool IsSelfBot(Player* player);
struct LastMovement { uint32 lastAreaTrigger = 0; };
struct MovementValue
{
    LastMovement data;
    LastMovement& Get() { return data; }
};
struct AiObjectContext
{
    MovementValue movement;
    template<class T> MovementValue* GetValue(char const*) { return &movement; }
};
struct PlayerbotAI
{
    Player* bot;
    Player* master = nullptr;
    AiObjectContext context;
    uint32 messages = 0, delays = 0;
    std::vector<WorldPacket> incoming;
    explicit PlayerbotAI(Player* player) : bot(player) { bot->botAI = this; }
    Player* GetMaster() const { return master; }
    void HandleMasterIncomingPacket(WorldPacket const& packet, Player*) { incoming.push_back(packet); }
    void TellError(std::string const&) { ++messages; }
    void TellMaster(std::string const&) { ++messages; }
    void SetNextCheckDelay(float) { ++delays; }
};
struct MovementAction
{
    PlayerbotAI* botAI;
    Player* bot;
    AiObjectContext* context;
    MovementAction(PlayerbotAI* ai, char const*) : botAI(ai), bot(ai->bot), context(&ai->context) {}
    virtual ~MovementAction() = default;
    virtual bool Execute(Event) = 0;
};
struct Trigger
{
    PlayerbotAI* botAI;
    Player* bot;
    AiObjectContext* context;
    Trigger(PlayerbotAI* ai, char const*) : botAI(ai), bot(ai->bot), context(&ai->context) {}
    virtual ~Trigger() = default;
    virtual bool IsActive() = 0;
};
struct PlayerbotTextMgr
{
    static PlayerbotTextMgr& instance() { static PlayerbotTextMgr manager; return manager; }
    std::string GetBotTextOrDefault(std::string const&, std::string const& text, std::vector<std::string>) { return text; }
};
struct PlayerbotAIConfig { float reactDelay = 500.0f; } sPlayerbotAIConfig;
using PlayerBotMap = std::map<uint32, Player*>;
struct PlayerbotMgr
{
    Player* master = nullptr;
    PlayerBotMap bots;
    Player* GetMaster() const { return master; }
    PlayerBotMap::const_iterator GetPlayerBotsBegin() const { return bots.begin(); }
    PlayerBotMap::const_iterator GetPlayerBotsEnd() const { return bots.end(); }
    void HandleMasterIncomingPacket(WorldPacket const& packet);
};
PlayerbotMgr sRandomPlayerbotMgr;

#include "AreaTriggerAction.h"
#include "WithinAreaTrigger.h"
NATIVE_METHODS
MODULE_METHODS

WorldPacket Packet(uint32 id)
{
    WorldPacket packet(CMSG_AREATRIGGER);
    packet << id;
    return packet;
}

struct Scenario
{
    Player bot;
    PlayerbotAI ai{&bot};
    WorldSession session{&bot};
    ReachAreaTriggerAction reach{&ai};
    AreaTriggerAction activate{&ai};
    WithinAreaTrigger within{&ai};
    AreaTrigger trigger = FROSTMANE_TRIGGER;
    Scenario()
    {
        objectManager = {};
        scriptManager = {};
        sRandomPlayerbotMgr = {};
        objectManager.areas[169] = trigger;
        objectManager.questRelations[169] = 287;
        objectManager.quests[287] = {};
        bot.m_QuestStatus[287].Status = QUEST_STATUS_INCOMPLETE;
        Place(20.0f);
    }
    void Place(float offset, uint32 map = 0)
    {
        bot.x = trigger.x + offset; bot.y = trigger.y; bot.z = trigger.z; bot.mapId = map;
    }
    bool Receive(uint32 id = 169)
    {
        auto packet = Packet(id);
        return reach.Execute(Event("area trigger", packet));
    }
    bool Explored() const { return bot.m_QuestStatus.at(287).Explored; }
    uint32 Pending() const { return ai.context.movement.data.lastAreaTrigger; }
    void EarnKills(uint16 count) { bot.m_QuestStatus[287].CreatureOrGOCount[0] = count; }
};

int main(int argc, char** argv)
{
    bool fixed = argc == 1 || std::string(argv[1]) != "baseline";
    // Original code submits while the follower is 20 yards away and never retries.
    {
        Scenario s;
        assert(s.Receive());
        assert(!s.Explored() && !s.bot.completions);
        assert(s.Pending() == (fixed ? 169u : 0u));
        s.Place(0.0f);
        assert(s.within.IsActive() == fixed);
        if (!fixed)
        {
            assert(!s.Explored());
            std::cout << "Original follower packet loses Frostmane exploration outside the native radius\n";
            return 0;
        }
        assert(s.activate.Execute(Event()));
        assert(s.Explored() && !s.Pending());
        assert(!s.bot.completions && s.bot.GetQuestStatus(287) == QUEST_STATUS_INCOMPLETE);
        assert(s.bot.completionPackets == 1 && s.bot.m_QuestStatusSave.at(287));
        assert(!s.bot.motion.moves && !s.bot.teleports && !s.ai.messages && !s.ai.delays);
        // Exploration alone never supplies the five separate kill objectives.
        s.EarnKills(4);
        assert(!s.bot.CanCompleteQuest(287));
        s.EarnKills(5);
        assert(s.bot.CanCompleteQuest(287));
        assert(!s.within.IsActive());
    }
    // Prior kills permit the native handler to complete on arrival; repeat action cannot re-credit.
    {
        Scenario s;
        s.EarnKills(5);
        assert(s.Receive());
        s.Place(0.0f);
        assert(s.within.IsActive() && s.activate.Execute(Event()));
        assert(s.Explored() && s.bot.completions == 1 && s.bot.GetQuestStatus(287) == QUEST_STATUS_COMPLETE);
        assert(!s.activate.Execute(Event()) && s.bot.completionPackets == 1);
    }
    // The core radius includes player object size, while teleport trigger geometry remains unchanged.
    for (float offset : {8.0f, 8.25f, 8.38f, 8.5f, 9.0f})
    {
        Scenario s;
        assert(s.Receive());
        s.Place(offset);
        bool inside = s.bot.IsInAreaTriggerRadius(&s.trigger);
        assert(inside == (offset <= 8.38f));
        assert(s.within.IsActive() == inside);
        assert(s.activate.Execute(Event()) == inside);
        assert(s.Explored() == inside);
        assert(s.Pending() == (inside ? 0u : 169u));
    }
    // A queued trigger is not consumed if movement leaves it between trigger and action.
    {
        Scenario s;
        assert(s.Receive());
        s.Place(0.0f);
        assert(s.within.IsActive());
        s.Place(20.0f);
        assert(!s.activate.Execute(Event()) && s.Pending() == 169 && !s.Explored());
        s.Place(0.0f);
        assert(s.within.IsActive() && s.activate.Execute(Event()) && s.Explored());
    }
    // No exploration for missing/failed/complete/rewarded quests, dead/flying bots or other maps.
    for (uint32 guard = 0; guard < 8; ++guard)
    {
        Scenario s;
        assert(s.Receive());
        s.Place(0.0f);
        switch (guard)
        {
            case 0: s.bot.m_QuestStatus.erase(287); break;
            case 1: s.bot.m_QuestStatus[287].Status = QUEST_STATUS_FAILED; break;
            case 2: s.bot.m_QuestStatus[287].Status = QUEST_STATUS_COMPLETE; break;
            case 3: s.bot.m_QuestStatus[287].Status = QUEST_STATUS_REWARDED; break;
            case 4: s.bot.alive = false; break;
            case 5: s.bot.inFlight = true; break;
            case 6: s.bot.mapId = 1; break;
            case 7: objectManager.questRelations.clear(); break;
        }
        assert(!s.within.IsActive() && !s.activate.Execute(Event()) && !s.Pending());
        assert(!s.bot.completions && !s.bot.completionPackets && !s.bot.teleports);
    }
    for (uint32 guard = 0; guard < 3; ++guard)
    {
        Scenario s;
        if (guard == 0) s.bot.alive = false;
        if (guard == 1) s.bot.inFlight = true;
        if (guard == 2) s.bot.mapId = 1;
        assert(!s.Receive() && !s.Pending() && !s.Explored());
        assert(!s.bot.motion.moves && !s.bot.teleports);
    }
    // Unknown trigger, immediate local arrival and native script interception.
    {
        Scenario s;
        assert(!s.Receive(999999) && !s.Pending());
        s.Place(0.0f);
        assert(s.Receive() && s.Explored() && !s.Pending());
    }
    {
        Scenario s;
        assert(s.Receive());
        s.Place(0.0f);
        scriptManager.handled = true;
        assert(s.within.IsActive() && s.activate.Execute(Event()));
        assert(scriptManager.calls == 1 && !s.Explored() && !s.bot.completions);
    }
    // Rotated box triggers use the core geometry as well; these represent other quest locations.
    {
        Scenario s;
        s.trigger.radius = 0.0f;
        s.trigger.length = 8.0f;
        s.trigger.width = 2.0f;
        s.trigger.height = 4.0f;
        s.trigger.orientation = float(M_PI / 2);
        objectManager.areas[169] = s.trigger;
        assert(s.Receive());
        s.Place(2.0f);
        assert(!s.within.IsActive() && !s.activate.Execute(Event()) && !s.Explored());
        s.bot.x = s.trigger.x; s.bot.y = s.trigger.y + 3.0f;
        assert(s.within.IsActive() && s.activate.Execute(Event()) && s.Explored());
    }
    // Owned alts and controlled random bots receive the real manager packet; foreign bots do not.
    {
        Scenario owned;
        Player master, otherMaster, random, foreign;
        PlayerbotAI randomAI(&random), foreignAI(&foreign);
        owned.ai.master = &master; randomAI.master = &master; foreignAI.master = &otherMaster;
        PlayerbotAI masterAI(&master);
        masterAI.master = &master;
        PlayerbotMgr manager;
        manager.master = &master;
        manager.bots = {{1, &owned.bot}, {2, nullptr}};
        sRandomPlayerbotMgr.bots = {{3, &random}, {4, &foreign}};
        auto packet = Packet(169);
        manager.HandleMasterIncomingPacket(packet);
        assert(owned.ai.incoming.size() == 1 && randomAI.incoming.size() == 1 && foreignAI.incoming.empty());
        assert(owned.reach.Execute(Event("area trigger", owned.ai.incoming.front())));
        assert(owned.Pending() == 169 && !owned.Explored());
        random.x = owned.trigger.x + 20.0f; random.y = owned.trigger.y; random.z = owned.trigger.z;
        random.m_QuestStatus[287].Status = QUEST_STATUS_INCOMPLETE;
        WorldSession randomSession(&random);
        ReachAreaTriggerAction randomReach(&randomAI);
        AreaTriggerAction randomActivate(&randomAI);
        WithinAreaTrigger randomWithin(&randomAI);
        assert(randomReach.Execute(Event("area trigger", randomAI.incoming.front())));
        assert(!randomWithin.IsActive() && !random.m_QuestStatus.at(287).Explored);
        random.x = owned.trigger.x;
        assert(randomWithin.IsActive() && randomActivate.Execute(Event()) && random.m_QuestStatus.at(287).Explored);
        assert(!owned.Explored());
    }
    // A SelfBot's real client remains responsible for its own area triggers.
    {
        Scenario s;
        s.ai.master = &s.bot;
        assert(!s.Receive() && !s.Pending());
        s.Place(0.0f);
        auto packet = Packet(169);
        s.session.HandleAreaTriggerOpcode(packet);
        assert(s.Explored());
    }
    // Existing teleport follow behavior and tavern packets keep their own handlers.
    {
        Scenario s;
        objectManager.teleports[169] = {1, 0.0f, 0.0f, 0.0f, 0.0f};
        assert(s.Receive() && s.Pending() == 169 && s.bot.motion.moves == 1 && s.ai.delays == 1);
        s.Place(0.0f);
        assert(s.within.IsActive() && s.activate.Execute(Event()));
        assert(s.bot.teleports == 1 && s.ai.messages == 2);
    }
    {
        Scenario s;
        objectManager.questRelations.clear();
        objectManager.taverns.insert(169);
        s.Place(0.0f);
        assert(s.Receive() && !s.Pending() && s.bot.rests == 1 && !s.Explored());
    }
    // Every actual quest-trigger mapping uses this same generic path, including expansion locations.
    std::vector<std::pair<AreaTrigger, uint32>> questTriggers{QUEST_TRIGGERS};
    for (auto const& [area, questId] : questTriggers)
    {
        Scenario s;
        objectManager.areas[area.entry] = area;
        objectManager.questRelations[area.entry] = questId;
        objectManager.quests[questId] = {};
        s.bot.m_QuestStatus.clear();
        s.bot.m_QuestStatus[questId].Status = QUEST_STATUS_INCOMPLETE;
        s.bot.mapId = area.map;
        s.bot.x = area.x + std::max(area.radius, area.length + area.width) + 20.0f;
        s.bot.y = area.y; s.bot.z = area.z;
        assert(!s.bot.IsInAreaTriggerRadius(&area));
        assert(s.Receive(area.entry) && s.Pending() == area.entry && !s.within.IsActive());
        assert(!s.bot.m_QuestStatus.at(questId).Explored && !s.bot.completions);
        s.bot.x = area.x;
        assert(s.within.IsActive() && s.activate.Execute(Event()));
        assert(s.bot.m_QuestStatus.at(questId).Explored && s.bot.m_QuestStatus.size() == 1);
        assert(!s.bot.CanCompleteQuest(questId) && !s.bot.completions);
        assert(!s.bot.motion.moves && !s.bot.teleports && !s.ai.messages);
    }
    std::cout << "Exercised " << questTriggers.size() << " pinned quest-trigger geometries and mappings\n";
    std::cout << "Follower exploration: native delayed arrival, ownership, geometry, quest/script guards, kill requirements and teleport behavior passed\n";
}
'''

native = '\n'.join(function(source, signature) for source, signature in (
    (packet, 'ByteBufferPositionException::ByteBufferPositionException'),
    (packet, 'void ByteBuffer::append(uint8 const*'),
    (position, 'bool Position::IsWithinBox'),
    (world_object, 'float WorldObject::GetDistance(float x, float y, float z)'),
    (player, 'bool Player::IsInAreaTriggerRadius'),
    (quest, 'bool Player::CanCompleteQuest('),
    (quest, 'void Player::AreaExploredOrEventHappens'),
    (misc, 'void WorldSession::HandleAreaTriggerOpcode'),
    (ai, 'bool IsSelfBot(Player* player)'),
)) + '\n' + manager_delivery


def methods(source):
    actions = (source / 'Ai/Base/Actions/AreaTriggerAction.cpp').read_text()
    triggers = (source / 'Ai/Base/Trigger/WithinAreaTrigger.cpp').read_text()
    return '\n'.join((
        function(actions, 'bool ReachAreaTriggerAction::Execute'),
        function(actions, 'bool AreaTriggerAction::Execute'),
        function(triggers, 'bool WithinAreaTrigger::IsActive'),
        function(triggers, 'bool WithinAreaTrigger::IsPointInAreaTriggerZone'),
    ))


with tempfile.TemporaryDirectory(prefix='portable-bot-area-trigger-') as temporary:
    temporary = Path(temporary)
    for header in ('MovementActions.h', 'Trigger.h'):
        (temporary / header).write_text('#pragma once\n')
    for relative in ('Ai/Base/Actions/AreaTriggerAction.h', 'Ai/Base/Trigger/WithinAreaTrigger.h'):
        (temporary / Path(relative).name).write_bytes((module / relative).read_bytes())
    includes = [temporary, module / 'Ai/Base/Actions', module / 'Ai/Base/Trigger',
                module / 'Bot/Engine/WorldPacket', core / 'src/common', core / 'src/common/Utilities',
                core / 'src/server/shared/Packets', core / 'src/server/game/Server',
                core / 'src/server/game/Server/Protocol']
    for label, source in (('baseline', baseline), ('fixed', module)):
        cpp = temporary / f'{label}.cpp'
        cpp.write_text(fixture.replace('NATIVE_DEFINITIONS', definitions)
                       .replace('NATIVE_METHODS', native)
                       .replace('MODULE_METHODS', methods(source))
                       .replace('FROSTMANE_TRIGGER', frostmane_trigger)
                       .replace('QUEST_TRIGGERS', ',\n'.join(quest_triggers)))
        executable = temporary / label
        command = ['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-g', '-O1',
                   '-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        command += [argument for path in includes for argument in ('-I', str(path))]
        subprocess.run(command + [str(cpp), '-o', str(executable)], check=True)
        subprocess.run([str(executable)] + (['baseline'] if label == 'baseline' else []),
                       check=True, timeout=30,
                       env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1:abort_on_error=1',
                            'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'})
        if label == 'baseline':
            # Reverting the actual production actions must fail the fixed behavior,
            # independently of the original-path demonstration above.
            reverted = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=30,
                preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
            assert reverted.returncode == -6 and 's.Pending() == (fixed ? 169u : 0u)' in reverted.stderr
            print('Reverted native exploration code is rejected by the fixed regression assertions.')
