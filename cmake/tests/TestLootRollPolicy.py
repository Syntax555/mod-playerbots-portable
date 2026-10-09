"""Exercise both bot loot-roll entry points with the actual native vote policy.

Production action, unique checks, master classification, packet construction,
session handler, usability, LFG eligibility and group vote counting are extracted unchanged. Fixtures provide
item-usage classifications, inventory counts, group state and recording output;
they do not emulate a live realm or its complete item-scoring system. Native
WorldPacket, ByteBuffer, ObjectGuid and Event types carry the real roll packets.
"""

from pathlib import Path
import argparse
import os
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
action = (module / 'Ai/Base/Actions/LootRollAction.cpp').read_text()
ai = (module / 'Bot/PlayerbotAI.cpp').read_text()
group = (core / 'src/server/game/Groups/Group.cpp').read_text()
group_header = (core / 'src/server/game/Groups/Group.h').read_text()
handler = (core / 'src/server/game/Handlers/GroupHandler.cpp').read_text()
storage = (core / 'src/server/game/Entities/Player/PlayerStorage.cpp').read_text()
packet = (core / 'src/server/shared/Packets/ByteBuffer.cpp').read_text()
guid = (core / 'src/server/game/Entities/Object/ObjectGuid.cpp').read_text()
item = (core / 'src/server/game/Entities/Item/ItemTemplate.h').read_text()
item_header = (core / 'src/server/game/Entities/Item/Item.h').read_text()
unit = (core / 'src/server/game/Entities/Unit/UnitDefines.h').read_text()
shared = (core / 'src/server/shared/SharedDefines.h').read_text()
loot = (core / 'src/server/game/Loot/LootMgr.h').read_text()
usage = (module / 'Ai/Base/Value/ItemUsageValue.h').read_text()

assert 'botOutgoingPacketHandlers.AddHandler(SMSG_LOOT_START_ROLL, "master loot roll");' in ai
assert 'creators["master loot roll"]' in (module / 'Ai/Base/WorldPacketActionContext.h').read_text()
strategy = (module / 'Ai/Base/Strategy/WorldPacketHandlerStrategy.cpp').read_text()
assert 'new TriggerNode("master loot roll", { NextAction("master loot roll", relevance) })' in strategy
assert 'new TriggerNode("very often", { NextAction("loot roll", relevance) })' in strategy

enums = '\n'.join(function(source, signature) + ';' for source, signature in (
    (group_header, 'enum RollVote : uint8'),
    (loot, 'enum RollType'), (loot, 'enum RollMask'), (loot, 'enum LootMethod'),
    (item, 'enum ItemClass'), (item, 'enum ItemBondingType'), (item, 'enum ItemFlags : uint32'),
    (item, 'enum ItemSubclassJunk'), (shared, 'enum ItemQualities'),
    (item, 'enum ItemFlags2 : uint32'), (item, 'enum ItemModType'),
    (item, 'enum ItemSubclassArmor'), (item, 'enum ItemSubclassWeapon'),
    (item, 'enum InventoryType'), (item_header, 'enum InventoryResult : uint8'),
    (shared, 'enum Classes'), (shared, 'enum SkillType'), (shared, 'enum TeamId : uint8'),
    (unit, 'enum ClassContext : uint8'),
    (usage, 'enum ItemUsage : uint32'),
))

fixture = r'''
#include <algorithm>
#include <cassert>
#include <iostream>
#include <list>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <tuple>
#include <vector>
#include "WorldPacket.h"
#include "ObjectGuid.h"
#include "Event.h"
#define ASSERT(condition, ...) assert(condition)
NATIVE_ENUMS

class Player;
class PlayerbotAI;
class Group;
constexpr uint32 PLAYER_FLAGS_NO_PLAY_TIME = 1;
constexpr uint32 PTF_UNHEALTHY_TIME = 1;
constexpr uint32 ACHIEVEMENT_CRITERIA_TYPE_ROLL_NEED = 1;
constexpr uint32 ACHIEVEMENT_CRITERIA_TYPE_ROLL_GREED = 2;
constexpr uint32 ACHIEVEMENT_CRITERIA_TYPE_ROLL_DISENCHANT = 3;
constexpr uint32 CONFIG_LOOT_NEED_BEFORE_GREED_ILVL_RESTRICTION = 0;
#define MAX_ITEM_SUBCLASS_WEAPON 21
enum HolidayIds : uint32 { FixtureHoliday = 1 };
bool IsHolidayActive(HolidayIds) { return true; }
class Map
{
public:
    uint32 id = 1;
    uint32 difficulty = 0;
    uint32 GetId() const { return id; }
    uint32 GetDifficulty() const { return difficulty; }
};
class WorldObject
{
public:
    Map map;
    Map const* GetMap() const { return &map; }
};
class GameObject : public WorldObject {};

struct ItemTemplate
{
    uint32 ItemId = 100;
    uint32 Class = ITEM_CLASS_ARMOR;
    uint32 SubClass = 0;
    uint32 Quality = ITEM_QUALITY_UNCOMMON;
    uint32 Bonding = BIND_WHEN_EQUIPPED;
    uint32 AllowableClass = ~0u;
    uint32 flags = 0;
    uint32 flags2 = 0;
    uint32 AllowableRace = ~0u;
    uint32 RequiredSpell = 0;
    uint32 RequiredSkill = 0;
    uint32 RequiredSkillRank = 0;
    uint32 RequiredLevel = 0;
    uint32 InventoryType = INVTYPE_CHEST;
    uint32 HolidayId = 0;
    uint32 ItemLevel = 20;
    bool spellPower = false;
    bool HasFlag(ItemFlags flag) const { return flags & flag; }
    bool HasFlag2(ItemFlags2 flag) const { return flags2 & flag; }
    bool HasStat(ItemModType) const { return spellPower; }
    bool HasSpellPowerStat() const { return spellPower; }
};
struct ObjectManager
{
    std::map<uint32, ItemTemplate> items;
    ItemTemplate const* GetItemTemplate(uint32 id)
    {
        auto found = items.find(id);
        return found == items.end() ? nullptr : &found->second;
    }
};
ObjectManager objectManager;
#define sObjectMgr (&objectManager)
struct PlayerbotAIConfig
{
    int32 lootNeedRollLevel = 1;
    bool lootGreedRollLevel = false;
    bool lootRollRecipe = false;
    bool lootRollDisenchant = false;
};
PlayerbotAIConfig playerbotAIConfig;
#define sPlayerbotAIConfig playerbotAIConfig
struct Loot
{
    std::vector<uint32> items{100};
    ObjectGuid sourceWorldObjectGUID{uint64(500)};
    GameObject* sourceGameObject = nullptr;
};
struct Roll
{
    ObjectGuid itemGUID{uint64(1000)};
    uint32 itemid = 100;
    int32 itemRandomPropId = 0;
    uint32 itemRandomSuffix = 0;
    uint8 itemCount = 1;
    using PlayerVote = std::map<ObjectGuid, RollVote>;
    PlayerVote playerVote;
    uint8 totalPlayersRolling = 2;
    uint8 totalNeed = 0;
    uint8 totalGreed = 0;
    uint8 totalPass = 0;
    uint8 itemSlot = 0;
    uint8 rollVoteMask = ROLL_ALL_TYPE_NO_DISENCHANT;
    Loot loot;
    bool valid = true;
    bool lootPresent = true;
    bool isValid() const { return valid; }
    Loot* getLoot() { return lootPresent ? &loot : nullptr; }
    Loot* getTarget() const { return lootPresent ? const_cast<Loot*>(&loot) : nullptr; }
};
class Group
{
public:
    using Rolls = std::vector<Roll*>;
    Rolls RollId;
    LootMethod method = GROUP_LOOT;
    uint32 completed = 0;
    bool lfg = false;
    ObjectGuid guid{uint64(700)};
    std::vector<std::tuple<ObjectGuid, uint8>> votes;
    [[nodiscard]] std::vector<Roll const*> GetRolls() const { return { RollId.begin(), RollId.end() }; }
    LootMethod GetLootMethod() const { return method; }
    bool isLFGGroup(bool) const { return lfg; }
    ObjectGuid GetGUID() const { return guid; }
    Rolls::iterator GetRoll(ObjectGuid guid);
    bool CountRollVote(ObjectGuid playerGUID, ObjectGuid guid, uint8 choice);
    void SendLootStartRollToPlayer(uint32 countDown, uint32 mapId, Player* player, bool canNeed, Roll const& roll);
    void SendLootRoll(ObjectGuid, ObjectGuid player, uint8, uint8 vote, Roll const&)
    {
        votes.emplace_back(player, vote);
    }
    void CountTheRoll(Rolls::iterator) { ++completed; }
};
class WorldSession
{
public:
    Player* player = nullptr;
    std::vector<WorldPacket> sent;
    uint32 playWarnings = 0;
    Player* GetPlayer() { return player; }
    void SendDirectMessage(WorldPacket const* packet) { sent.push_back(*packet); }
    void SendPlayTimeWarning(uint32, uint32) { ++playWarnings; }
    void HandleLootRoll(WorldPacket& packet);
};
class Player
{
public:
    ObjectGuid guid{uint64(1)};
    Group* group = nullptr;
    PlayerbotAI* botAI = nullptr;
    uint8 classId = 1;
    uint8 raceId = 1;
    uint32 level = 20;
    uint32 team = TEAM_ALLIANCE;
    std::map<uint32, uint32> skills;
    std::set<uint32> knownSpells;
    uint32 bagCount = 0;
    uint32 totalCount = 0;
    bool noPlayTime = false;
    WorldSession session;
    std::vector<uint32> achievements;
    Player() { session.player = this; }
    ObjectGuid GetGUID() const { return guid; }
    Group* GetGroup() const { return group; }
    uint8 getClass() const { return classId; }
    uint32 getClassMask() const { return 1 << (classId - 1); }
    uint32 getRaceMask() const { return 1 << (raceId - 1); }
    uint32 GetLevel() const { return level; }
    uint32 GetTeamId(bool) const { return team; }
    uint32 GetSkillValue(uint32 skill) const
    {
        auto found = skills.find(skill);
        return found == skills.end() ? 0 : found->second;
    }
    bool HasSpell(uint32 spell) const { return knownSpells.contains(spell); }
    bool IsClass(Classes cls, ClassContext) const { return classId == cls; }
    InventoryResult CanRollForItemInLFG(ItemTemplate const* proto, WorldObject const* source) const;
    InventoryResult CanUseItem(ItemTemplate const* proto) const;
    uint32 GetItemCount(uint32, bool bank) const { return bank ? totalCount : bagCount; }
    bool HasPlayerFlag(uint32) const { return noPlayTime; }
    void UpdateAchievementCriteria(uint32 criterion, uint32) { achievements.push_back(criterion); }
    void SendDirectMessage(WorldPacket const* packet) { session.SendDirectMessage(packet); }
};
class PlayerbotAI
{
public:
    Player* bot;
    Player* master;
    bool lootAllowed = true;
    std::map<std::string, ItemUsage> usages;
    std::vector<std::string> queries;
    WorldObject* lootSource = nullptr;
    PlayerbotAI(Player* bot, Player* master) : bot(bot), master(master) { bot->botAI = this; }
    Player* GetBot() { return bot; }
    Player* GetMaster() { return master; }
    WorldObject* GetWorldObject(ObjectGuid guid) { return guid ? lootSource : nullptr; }
    ItemUsage Usage(std::string const& qualifier)
    {
        queries.push_back(qualifier);
        auto found = usages.find(qualifier);
        return found == usages.end() ? ITEM_USAGE_NONE : found->second;
    }
};
struct LFGManager
{
    uint32 dungeon = 1;
    bool inLfgDungeonMap(ObjectGuid, uint32 map, uint32) const { return map == dungeon; }
};
LFGManager lfgManager;
#define sLFGMgr (&lfgManager)
struct World
{
    uint32 restriction = 0;
    uint32 getIntConfig(uint32) const { return restriction; }
};
World world;
#define sWorld (&world)
struct ScriptManager
{
    bool OnPlayerCanUseItem(Player*, ItemTemplate const*, InventoryResult&) { return true; }
};
ScriptManager scriptManager;
#define sScriptMgr (&scriptManager)
#define GET_PLAYERBOT_AI(player) ((player) ? (player)->botAI : nullptr)
#define AI_VALUE2(type, name, qualifier) (botAI->Usage(qualifier))
bool IsRealPlayer(Player* player);
bool IsSelfBot(Player* player);
bool CanBotUseToken(ItemTemplate const* proto, Player* bot);
bool RollUniqueCheck(ItemTemplate const* proto, Player* bot);
class StoreLootAction
{
public:
    static bool IsLootAllowed(uint32, PlayerbotAI* ai) { return ai && ai->lootAllowed; }
};
class QueryItemUsageAction
{
public:
    PlayerbotAI* botAI;
    Player* bot;
    explicit QueryItemUsageAction(PlayerbotAI* ai) : botAI(ai), bot(ai->GetBot()) {}
};
class LootRollAction : public QueryItemUsageAction
{
public:
    using QueryItemUsageAction::QueryItemUsageAction;
    bool Execute(Event event);
    RollVote CalculateRollVote(ItemTemplate const* proto, ItemUsage usage = ITEM_USAGE_NONE);
};
class MasterLootRollAction : public LootRollAction
{
public:
    using LootRollAction::LootRollAction;
    bool isUseful();
    bool Execute(Event event);
};
'''.replace('NATIVE_ENUMS', enums)

production = '\n'.join([
    next(line for line in guid.splitlines() if line.startswith('ObjectGuid const ObjectGuid::Empty')),
    function(packet, 'ByteBufferPositionException::ByteBufferPositionException'),
    function(packet, 'void ByteBuffer::append(uint8 const*'),
    function(guid, 'ByteBuffer& operator<<(ByteBuffer& buf, ObjectGuid const& guid)'),
    function(guid, 'ByteBuffer& operator>>(ByteBuffer& buf, ObjectGuid& guid)'),
    function(ai, 'bool IsRealPlayer(Player* player)'),
    function(ai, 'bool IsSelfBot(Player* player)'),
    function(action, 'bool LootRollAction::Execute'),
    function(action, 'RollVote LootRollAction::CalculateRollVote'),
    function(action, 'bool MasterLootRollAction::isUseful'),
    function(action, 'bool MasterLootRollAction::Execute'),
    function(action, 'bool CanBotUseToken'),
    function(action, 'bool RollUniqueCheck'),
    function(group, 'Group::Rolls::iterator Group::GetRoll'),
    function(group, 'bool Group::CountRollVote'),
    function(group, 'void Group::SendLootStartRollToPlayer'),
    function(handler, 'void WorldSession::HandleLootRoll'),
    function(storage, 'InventoryResult Player::CanRollForItemInLFG'),
    function(storage, 'InventoryResult Player::CanUseItem(ItemTemplate const* proto)'),
])

tests = r'''
enum class MasterMode { Real, SelfBot, Bot, None };
struct Scenario
{
    Player master;
    Player bot;
    PlayerbotAI masterAI{&master, &master};
    PlayerbotAI ai{&bot, &master};
    Group group;
    Roll roll;
    LootRollAction periodic{&ai};
    MasterLootRollAction packet{&ai};
    WorldObject source;
    explicit Scenario(MasterMode mode = MasterMode::SelfBot)
    {
        playerbotAIConfig = {};
        world.restriction = 0;
        objectManager.items.clear();
        objectManager.items.emplace(100, ItemTemplate{});
        master.guid = ObjectGuid(uint64(2));
        bot.group = &group;
        roll.playerVote[bot.guid] = NOT_EMITED_YET;
        roll.playerVote[master.guid] = NOT_EMITED_YET;
        group.RollId.push_back(&roll);
        ai.usages["100"] = ITEM_USAGE_EQUIP;
        ai.lootSource = &source;
        switch (mode)
        {
            case MasterMode::Real: master.botAI = nullptr; break;
            case MasterMode::SelfBot: break;
            case MasterMode::Bot: masterAI.master = nullptr; break;
            case MasterMode::None: ai.master = nullptr; masterAI.master = nullptr; break;
        }
    }
    ItemTemplate& Item() { return objectManager.items.at(100); }
    Event Packet(bool canNeed = true)
    {
        group.SendLootStartRollToPlayer(60000, 0, &bot, canNeed, roll);
        return Event("master loot roll", bot.session.sent.back());
    }
    bool Receive(bool canNeed = true)
    {
        Event event = Packet(canNeed);
        return packet.isUseful() && packet.Execute(event);
    }
    RollVote Vote() { return roll.playerVote.at(bot.guid); }
    void Expect(RollVote expected, uint32 count = 1)
    {
        assert(Vote() == expected);
        assert(group.votes.size() == count);
        assert(uint32(roll.totalNeed + roll.totalGreed + roll.totalPass) == count);
        assert(roll.totalNeed == (expected == NEED ? count : 0));
        assert(roll.totalGreed == (expected == GREED || expected == DISENCHANT ? count : 0));
        assert(roll.totalPass == (expected == PASS ? count : 0));
    }
};

void MasterModesAndOrder()
{
    for (MasterMode mode : {MasterMode::Real, MasterMode::SelfBot, MasterMode::Bot, MasterMode::None})
    {
        for (bool periodicFirst : {false, true})
        {
            Scenario s(mode);
            assert(s.packet.isUseful() == (mode != MasterMode::Real));
            assert(IsSelfBot(&s.master) == (mode == MasterMode::SelfBot));
            Event notification = s.Packet();
            if (periodicFirst)
                assert(s.periodic.Execute(Event("loot roll")));
            bool received = s.packet.isUseful() && s.packet.Execute(notification);
            assert(received == (!periodicFirst && mode != MasterMode::Real));
            bool ticked = s.periodic.Execute(Event("loot roll"));
            assert(ticked == (!periodicFirst && mode == MasterMode::Real));
            s.Expect(GREED);
            assert(!s.Receive());
            assert(!s.periodic.Execute(Event("loot roll")));
            s.Expect(GREED);
        }
    }
}

void PolicyMatrix()
{
    uint32 cases = 0;
    for (MasterMode mode : {MasterMode::SelfBot, MasterMode::Bot, MasterMode::None})
        for (int32 needLevel : {0, 1, 2})
            for (bool greed : {false, true})
                for (bool recipes : {false, true})
                    for (bool disenchant : {false, true})
                        for (uint32 kind = 0; kind < 8; ++kind)
                            for (bool notification : {false, true})
                            {
                                Scenario s(mode);
                                playerbotAIConfig = {needLevel, greed, recipes, disenchant};
                                RollVote expected = PASS;
                                switch (kind)
                                {
                                    case 0: break; // Armor upgrade.
                                    case 1: s.ai.usages["100"] = ITEM_USAGE_AH; expected = GREED; break;
                                    case 2: s.ai.usages["100"] = ITEM_USAGE_NONE; break;
                                    case 3:
                                        s.Item().Class = ITEM_CLASS_RECIPE;
                                        s.ai.usages["100"] = ITEM_USAGE_SKILL;
                                        break;
                                    case 4:
                                        s.Item().Class = ITEM_CLASS_RECIPE;
                                        s.ai.usages["100"] = ITEM_USAGE_AH;
                                        expected = recipes ? GREED : PASS;
                                        break;
                                    case 5:
                                        s.Item().Class = ITEM_CLASS_RECIPE;
                                        s.Item().Bonding = BIND_WHEN_PICKED_UP;
                                        s.ai.usages["100"] = ITEM_USAGE_AH;
                                        break;
                                    case 6:
                                        s.ai.usages["100"] = ITEM_USAGE_DISENCHANT;
                                        s.roll.rollVoteMask = ROLL_ALL_TYPE_MASK;
                                        expected = disenchant ? DISENCHANT : GREED;
                                        break;
                                    case 7:
                                        s.Item().Class = ITEM_CLASS_CONSUMABLE;
                                        s.ai.usages["100"] = ITEM_USAGE_VENDOR;
                                        expected = GREED;
                                        break;
                                }
                                bool needs = kind == 0 || (kind == 3 && recipes);
                                if (needs)
                                    expected = needLevel == 0 ? PASS : needLevel == 1 ? GREED : NEED;
                                else if (expected == GREED && !greed)
                                    expected = PASS;
                                assert(notification ? s.Receive() : s.periodic.Execute(Event("loot roll")));
                                s.Expect(expected);
                                ++cases;
                            }
    assert(cases == 1152);
}

void ItemGuardsAndVariants()
{
    for (bool notification : {false, true})
    {
        for (uint32 uniqueState = 0; uniqueState < 4; ++uniqueState)
        {
            Scenario s;
            playerbotAIConfig.lootNeedRollLevel = 2;
            s.Item().flags = ITEM_FLAG_UNIQUE_EQUIPPABLE;
            s.bot.bagCount = uniqueState;
            s.bot.totalCount = uniqueState == 0 ? 1 : uniqueState;
            assert(notification ? s.Receive() : s.periodic.Execute(Event("loot roll")));
            s.Expect(uniqueState == 1 ? NEED : PASS);
        }
        for (bool sameClass : {false, true})
        {
            Scenario s;
            playerbotAIConfig.lootNeedRollLevel = 2;
            playerbotAIConfig.lootGreedRollLevel = true;
            s.Item().Class = ITEM_CLASS_MISC;
            s.Item().SubClass = ITEM_SUBCLASS_JUNK;
            s.Item().Quality = ITEM_QUALITY_EPIC;
            s.Item().AllowableClass = sameClass ? 1 : 2;
            assert(notification ? s.Receive() : s.periodic.Execute(Event("loot roll")));
            s.Expect(sameClass ? NEED : GREED);
        }
        for (int32 property : {-83, 0, 57})
        {
            Scenario s;
            playerbotAIConfig.lootNeedRollLevel = 2;
            s.ai.usages["100"] = ITEM_USAGE_AH;
            std::string qualifier = property ? "100," + std::to_string(property) : "100";
            s.ai.usages[qualifier] = ITEM_USAGE_REPLACE;
            if (property < 0)
                s.roll.itemRandomSuffix = uint32(-property);
            else
                s.roll.itemRandomPropId = property;
            assert(notification ? s.Receive() : s.periodic.Execute(Event("loot roll")));
            s.Expect(NEED);
            assert(s.ai.queries == std::vector<std::string>{qualifier});
        }
        Scenario ignored;
        ignored.Item().Class = ITEM_CLASS_CONSUMABLE;
        ignored.ai.usages["100"] = ITEM_USAGE_USE;
        ignored.ai.lootAllowed = false;
        playerbotAIConfig.lootGreedRollLevel = true;
        assert(notification ? ignored.Receive() : ignored.periodic.Execute(Event("loot roll")));
        ignored.Expect(PASS);
    }
}

void PendingRollGuards()
{
    for (bool notification : {false, true})
    {
        for (LootMethod method : {MASTER_LOOT, FREE_FOR_ALL})
        {
            Scenario s;
            s.group.method = method;
            playerbotAIConfig.lootNeedRollLevel = 2;
            assert(notification ? s.Receive() : s.periodic.Execute(Event("loot roll")));
            s.Expect(PASS);
        }
        for (uint32 guard = 0; guard < 4; ++guard)
        {
            Scenario s;
            Event event = s.Packet();
            switch (guard)
            {
                case 0: s.bot.group = nullptr; break;
                case 1: s.group.RollId.clear(); break;
                case 2: s.roll.playerVote.erase(s.bot.guid); break;
                case 3: objectManager.items.clear(); break;
            }
            assert(!(notification ? s.packet.Execute(event) : s.periodic.Execute(Event("loot roll"))));
            assert(s.group.votes.empty());
        }
        Scenario multiple;
        Roll second;
        second.itemGUID = ObjectGuid(uint64(1001));
        second.playerVote = multiple.roll.playerVote;
        multiple.group.RollId.push_back(&second);
        assert(notification ? multiple.Receive() : multiple.periodic.Execute(Event("loot roll")));
        assert(multiple.group.votes.size() == 2);
        assert(second.playerVote.at(multiple.bot.guid) == GREED);
        assert(!multiple.Receive());
        assert(!multiple.periodic.Execute(Event("loot roll")));
        assert(multiple.group.votes.size() == 2);
    }
}

void NativeMasksAndSession()
{
    // Core packet handlers trust the client to hide forbidden vote buttons.
    // Bots therefore apply the advertised restrictions before counting votes.
    for (RollVote vote : {NEED, GREED, DISENCHANT})
    {
        Scenario client;
        client.roll.rollVoteMask = ROLL_FLAG_TYPE_PASS | ROLL_FLAG_TYPE_GREED;
        WorldPacket request(CMSG_LOOT_ROLL, 13);
        request << client.roll.itemGUID << uint32(client.roll.itemSlot) << uint8(vote);
        client.bot.session.HandleLootRoll(request);
        client.Expect(vote);
    }
    for (bool allowed : {false, true})
    {
        Scenario s;
        s.group.method = NEED_BEFORE_GREED;
        s.group.lfg = true;
        playerbotAIConfig.lootNeedRollLevel = 2;
        playerbotAIConfig.lootGreedRollLevel = true;
        s.Item().AllowableClass = allowed ? s.bot.getClassMask() : 2;
        bool canNeed = s.bot.CanRollForItemInLFG(&s.Item(), &s.source) == EQUIP_ERR_OK;
        assert(canNeed == allowed);
        Event event = s.Packet(canNeed);
        WorldPacket packet = event.getPacket();
        packet.rpos(packet.size() - 1);
        uint8 mask;
        packet >> mask;
        assert(bool(mask & ROLL_FLAG_TYPE_NEED) == canNeed);
        assert(s.packet.Execute(event));
        s.Expect(allowed ? NEED : GREED);
    }
    Scenario unavailable;
    playerbotAIConfig.lootRollDisenchant = true;
    unavailable.ai.usages["100"] = ITEM_USAGE_DISENCHANT;
    unavailable.roll.rollVoteMask = ROLL_ALL_TYPE_NO_DISENCHANT;
    assert(unavailable.Receive());
    unavailable.Expect(PASS);

    Scenario native;
    native.bot.noPlayTime = true;
    WorldPacket request(CMSG_LOOT_ROLL, 13);
    request << native.roll.itemGUID << uint32(native.roll.itemSlot) << uint8(NEED);
    native.bot.session.HandleLootRoll(request);
    native.Expect(PASS);
    assert(native.bot.session.playWarnings == 1);

    Scenario closed;
    closed.group.RollId.clear();
    assert(!closed.group.CountRollVote(closed.bot.guid, closed.roll.itemGUID, NEED));
    assert(closed.group.votes.empty());
    Scenario outsider;
    assert(!outsider.group.CountRollVote(ObjectGuid(uint64(99)), outsider.roll.itemGUID, NEED));
    assert(outsider.group.votes.empty());
}

void MaskCombinations()
{
    for (uint8 mask = 0; mask <= ROLL_ALL_TYPE_MASK; ++mask)
        for (bool greed : {false, true})
            for (RollVote requested : {NEED, GREED, DISENCHANT})
                for (bool notification : {false, true})
                {
                    Scenario s;
                    playerbotAIConfig = {2, greed, false, true};
                    s.roll.rollVoteMask = mask;
                    s.ai.usages["100"] = requested == NEED ? ITEM_USAGE_EQUIP :
                                          requested == GREED ? ITEM_USAGE_AH : ITEM_USAGE_DISENCHANT;
                    RollVote expected = PASS;
                    if (requested == NEED && (mask & ROLL_FLAG_TYPE_NEED))
                        expected = NEED;
                    else if (requested == DISENCHANT && (mask & ROLL_FLAG_TYPE_DISENCHANT))
                        expected = DISENCHANT;
                    else if (greed && (mask & ROLL_FLAG_TYPE_GREED))
                        expected = GREED;
                    assert(notification ? s.Receive() : s.periodic.Execute(Event("loot roll")));
                    s.Expect(expected);
                }
}

void NativeEligibility()
{
    for (bool notification : {false, true})
    {
        for (uint32 guard = 0; guard < 11; ++guard)
        {
            Scenario s;
            playerbotAIConfig = {2, true, false, false};
            s.group.method = NEED_BEFORE_GREED;
            s.group.lfg = true;
            switch (guard)
            {
                case 0: s.Item().AllowableClass = 2; break;
                case 1: s.Item().AllowableRace = 2; break;
                case 2: s.Item().RequiredSpell = 123; break;
                case 3: s.Item().RequiredSkill = SKILL_BLACKSMITHING; break;
                case 4:
                    s.Item().RequiredSkill = SKILL_BLACKSMITHING;
                    s.Item().RequiredSkillRank = 75;
                    s.bot.skills[SKILL_BLACKSMITHING] = 74;
                    break;
                case 5: s.Item().Class = ITEM_CLASS_WEAPON; s.Item().SubClass = ITEM_SUBCLASS_WEAPON_AXE; break;
                case 6: s.Item().SubClass = ITEM_SUBCLASS_ARMOR_PLATE; s.bot.classId = CLASS_MAGE; break;
                case 7: s.Item().SubClass = ITEM_SUBCLASS_ARMOR_LIBRAM; break;
                case 8: s.Item().SubClass = ITEM_SUBCLASS_ARMOR_PLATE; s.Item().spellPower = true; break;
                case 9:
                    s.Item().SubClass = ITEM_SUBCLASS_ARMOR_LEATHER;
                    s.Item().spellPower = true;
                    s.bot.classId = CLASS_ROGUE;
                    break;
                case 10:
                    world.restriction = 10;
                    s.Item().SubClass = ITEM_SUBCLASS_ARMOR_CLOTH;
                    break;
            }
            bool canNeed = s.bot.CanRollForItemInLFG(&s.Item(), &s.source) == EQUIP_ERR_OK;
            assert(!canNeed);
            Event event = s.Packet(canNeed);
            assert(notification ? s.packet.Execute(event) : s.periodic.Execute(Event("loot roll")));
            s.Expect(GREED);
        }
        for (uint32 sourceState = 0; sourceState < 4; ++sourceState)
        {
            Scenario s;
            GameObject chest;
            playerbotAIConfig = {2, true, false, false};
            s.group.method = NEED_BEFORE_GREED;
            s.group.lfg = true;
            switch (sourceState)
            {
                case 0: s.roll.lootPresent = false; break;
                case 1: s.roll.loot.sourceWorldObjectGUID = ObjectGuid::Empty; break;
                case 2: s.ai.lootSource = nullptr; break;
                case 3: s.ai.lootSource = nullptr; s.roll.loot.sourceGameObject = &chest; break;
            }
            assert(notification ? s.Receive() : s.periodic.Execute(Event("loot roll")));
            s.Expect(sourceState == 3 ? NEED : GREED);
        }
        // LFG restrictions apply only in the group's queued dungeon, as on the client.
        for (uint32 bypass = 0; bypass < 3; ++bypass)
        {
            Scenario s;
            playerbotAIConfig = {2, true, false, false};
            s.group.method = NEED_BEFORE_GREED;
            s.group.lfg = true;
            s.Item().AllowableClass = 2;
            switch (bypass)
            {
                case 0: s.group.lfg = false; break;
                case 1: s.source.map.id = 2; break;
                case 2: s.Item().flags2 = ITEM_FLAG2_EVERYONE_CAN_ROLL_NEED; break;
            }
            assert(s.bot.CanRollForItemInLFG(&s.Item(), &s.source) == EQUIP_ERR_OK);
            assert(notification ? s.Receive() : s.periodic.Execute(Event("loot roll")));
            s.Expect(NEED);
        }
        // The equipment classifier's earlier native CanUseItem gate includes level.
        for (uint32 usability = 0; usability < 3; ++usability)
        {
            Scenario s;
            playerbotAIConfig = {2, true, false, false};
            switch (usability)
            {
                case 0: s.Item().RequiredLevel = s.bot.level + 1; break;
                case 1: s.Item().AllowableClass = 2; break;
                case 2: s.Item().RequiredSpell = 123; break;
            }
            assert(s.bot.CanUseItem(&s.Item()) != EQUIP_ERR_OK);
            s.ai.usages["100"] = ITEM_USAGE_AH;
            assert(notification ? s.Receive() : s.periodic.Execute(Event("loot roll")));
            s.Expect(GREED);
        }
    }
}

int main()
{
    MasterModesAndOrder();
    PolicyMatrix();
    ItemGuardsAndVariants();
    PendingRollGuards();
    NativeMasksAndSession();
    MaskCombinations();
    NativeEligibility();
    std::cout << "Bot loot rolls: 1,152 policy cases, 192 vote-mask cases, native LFG/usability, packets/counters, master types, ordering, recipes, unique items and random properties passed\n";
}
'''

with tempfile.TemporaryDirectory(prefix='portable-loot-roll-policy-') as directory:
    temporary = Path(directory)
    source = temporary / 'loot-policy.cpp'
    source.write_text(fixture + '\n' + production + '\n' + tests)
    executable = temporary / 'loot-policy'
    includes = [
        module / 'Bot/Engine/WorldPacket',
        core / 'src/common', core / 'src/common/Utilities',
        core / 'src/server/shared/Packets', core / 'src/server/game/Server',
        core / 'src/server/game/Server/Protocol', core / 'src/server/game/Entities/Object',
    ]
    command = ['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-g', '-O1',
               '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-no-pie']
    command += [argument for path in includes for argument in ('-I', str(path))]
    command += [str(source), '-o', str(executable)]
    subprocess.run(command, check=True)
    subprocess.run([str(executable)], check=True, timeout=30,
                   env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1:abort_on_error=1',
                        'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'})
