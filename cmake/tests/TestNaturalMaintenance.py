"""Check natural-mode upkeep selection and execution against small engine stubs.

NaturalMaintenanceValue chooses every autonomous gold spend and visit: vendor
sales, repairs, trainer lessons, food, drink, ammunition, reagents, bags and
the auction or mailbox visit clock. The production value, action, trigger and
auction-trip clock run here with fake core objects. Mutation checks confirm
that the guards, budgets and priorities are required.
"""

import argparse
from pathlib import Path
import re
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    cxx,
    function,
    in_parallel,
    prepared_core,
    run_fixture,
    source_argument,
)


def declaration(source, opening):
    return re.search(re.escape(opening) + r'\n\{.*?\n\};', source, re.DOTALL).group(0)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help='prepared Playerbots src directory')
source_argument(parser, 'core', help='prepared core source directory')
args = parser.parse_args()
core = args.core or prepared_core(Path(__file__).resolve().parents[2])
module = args.source or core / 'modules/mod-playerbots/src'
values_header = (module / 'Ai/Base/Value/MaintenanceValues.h').read_text()
values_source = (module / 'Ai/Base/Value/MaintenanceValues.cpp').read_text()
usage_source = (module / 'Ai/Base/Value/ItemUsageValue.cpp').read_text()
usage_header = (module / 'Ai/Base/Value/ItemUsageValue.h').read_text()
player_header = (core / 'src/server/game/Entities/Player/Player.h').read_text()
item_header = (core / 'src/server/game/Entities/Item/ItemTemplate.h').read_text()
storage = (core / 'src/server/game/Entities/Player/PlayerStorage.cpp').read_text()
rpg = module / 'Ai/World/Rpg'
action_header = (rpg / 'Action/NewRpgAction.h').read_text()
action_source = (rpg / 'Action/NewRpgAction.cpp').read_text()
trigger_header = (rpg / 'Trigger/NewRpgTriggers.h').read_text()
trigger_source = (rpg / 'Trigger/NewRpgTrigger.cpp').read_text()
info_header = (rpg / 'NewRpgInfo.h').read_text()
travel_source = (module / 'Bot/EarnedAuctionTravel.cpp').read_text()

rpg_fields = re.findall(r'^    (?:bool|uint32|WorldPosition|ObjectGuid) (?:earnedAuction|naturalMaintenance)\w*(?:\{[^}]*\})?;$',
                        info_header, re.MULTILINE)
assert len(rpg_fields) >= 9, 'earned-auction visit clock fields were not found in NewRpgInfo'

# The bag doubles follow the native accessors and the upgrade rule EquipAction applies:
# "item upgrade" is QueryItemUsageForEquip, which accepts only a larger general bag.
assert 'return item->ToBag();' in function(storage, 'Bag* Player::GetBagByPos(uint8 bag) const')
assert 'creators["item upgrade"] = &ValueContext::item_upgrade;' in (module / 'Ai/Base/ValueContext.h').read_text()
assert ('ItemUsage equip = QueryItemUsageForEquip(proto, randomPropertyId);\n    if (equip != ITEM_USAGE_NONE)\n'
        '        return equip;') in function(usage_source, 'ItemUsage ItemUpgradeValue::Calculate()')
equip_usage = function(usage_source, 'ItemUsage ItemUsageValue::QueryItemUsageForEquip(')
assert '{\n    if (bot->CanUseItem(itemProto) != EQUIP_ERR_OK)\n        return ITEM_USAGE_NONE;' in equip_usage
container = function(equip_usage, 'if (itemProto->Class == ITEM_CLASS_CONTAINER)')
assert container.count('return ') == 3
assert 'if (itemProto->SubClass != ITEM_SUBCLASS_CONTAINER)\n            return ITEM_USAGE_NONE;' in container
assert ('if (GetSmallestBagSize() >= itemProto->ContainerSlots)\n            return ITEM_USAGE_NONE;\n\n'
        '        return ITEM_USAGE_EQUIP;\n    }') in container

production = {
    'native': '\n'.join(function(source, signature) + ';' for source, signature in (
        (player_header, 'enum InventorySlots'), (player_header, 'enum InventoryPackSlots'),
        (item_header, 'enum ItemClass'), (item_header, 'enum ItemSubclassContainer'),
        (usage_header, 'enum ItemUsage : uint32'))),
    'types': '\n'.join([
        declaration(values_header, 'enum class NaturalMaintenanceType : uint8'),
        declaration(values_header, 'struct NaturalMaintenanceTask'),
        'struct NewRpgInfo\n{\n' + '\n'.join(rpg_fields) + '\n};',
    ]),
    'classes': '\n'.join([
        declaration(values_header, 'class NaturalMaintenanceValue : public CalculatedValue<NaturalMaintenanceTask>'),
        declaration(action_header, 'class NewRpgNaturalMaintenanceAction : public NewRpgBaseAction'),
        declaration(trigger_header, 'class NewRpgNaturalMaintenanceTrigger : public Trigger'),
    ]),
    'travel': '\n'.join(function(travel_source, signature) for signature in (
        'void FinishTrip(PlayerbotAI* ai)', 'bool ContinueTrip(PlayerbotAI* ai)', 'void AbortTrip(PlayerbotAI* ai)',
        'void PostponeVisit(PlayerbotAI* ai)')),
    'guard': function(values_source, 'bool CanRunNaturalMaintenance(PlayerbotAI* botAI)'),
    'helpers': re.search(r'namespace\n\{\n.*?\n\}  // namespace', values_source, re.DOTALL).group(0),
    'smallest': function(usage_source, 'uint32 ItemUsageValue::GetSmallestBagSize()'),
    'value': function(values_source, 'NaturalMaintenanceTask NaturalMaintenanceValue::Calculate()'),
    'action': function(action_source, 'bool NewRpgNaturalMaintenanceAction::Execute(Event /*event*/)'),
    'trigger': function(trigger_source, 'bool NewRpgNaturalMaintenanceTrigger::IsActive()'),
    'usage': function(usage_source, 'std::string const ItemUsageValue::GetConsumableType(').replace(
        'ItemUsageValue::GetConsumableType', 'ProductionConsumableType'),
}

prelude = r'''
#include "EarnedAuctionTravelPolicy.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <deque>
#include <functional>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <type_traits>
#include <unordered_map>
#include <utility>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
using int8 = std::int8_t;
using int32 = std::int32_t;
constexpr uint32 IN_MILLISECONDS = 1000;
constexpr float INTERACTION_DISTANCE = 5.0f;
constexpr uint8 INVENTORY_SLOT_BAG_0 = 255, EQUIPMENT_SLOT_RANGED = 17;
constexpr int MAX_SPELL_REAGENTS = 8, MAX_ITEM_PROTO_SPELLS = 5;
enum Powers { POWER_MANA };
enum Classes { CLASS_WARRIOR = 1, CLASS_HUNTER = 3, CLASS_MAGE = 8 };
enum PlayerSpellState { PLAYERSPELL_UNCHANGED, PLAYERSPELL_CHANGED, PLAYERSPELL_NEW, PLAYERSPELL_REMOVED };
enum InventoryResult { EQUIP_ERR_OK, EQUIP_ERR_CANT_EQUIP_SKILL };
@@NATIVE@@
enum ItemSubclassConsumable
{
    ITEM_SUBCLASS_CONSUMABLE = 0, ITEM_SUBCLASS_POTION = 1, ITEM_SUBCLASS_FLASK = 3, ITEM_SUBCLASS_FOOD = 5,
    ITEM_SUBCLASS_BANDAGE = 7
};
enum ItemSubclassWeapon { ITEM_SUBCLASS_WEAPON_BOW = 2, ITEM_SUBCLASS_WEAPON_GUN = 3, ITEM_SUBCLASS_WEAPON_CROSSBOW = 18 };
enum ItemSubclassProjectile { ITEM_SUBCLASS_ARROW = 2, ITEM_SUBCLASS_BULLET = 3 };
enum SpellEffects { SPELL_EFFECT_HEAL = 10, SPELL_EFFECT_ENERGIZE = 30 };
enum NPCFlags : uint32
{
    UNIT_NPC_FLAG_TRAINER = 0x10, UNIT_NPC_FLAG_VENDOR = 0x80, UNIT_NPC_FLAG_REPAIR = 0x1000,
    UNIT_NPC_FLAG_AUCTIONEER = 0x200000
};
enum class MovementPriority { MOVEMENT_IDLE, MOVEMENT_WANDER, MOVEMENT_NORMAL, MOVEMENT_COMBAT, MOVEMENT_FORCED };
enum class NeedMoneyFor : uint32
{
    none = 0, repair = 1, ammo = 2, spells = 3, travel = 4, consumables = 5, gear = 6, guild = 7, tradeskill = 8,
    anything = 9
};

#define AI_VALUE(type, name) context->GetValue<type>(name)->Get()
#define AI_VALUE2(type, name, param) context->GetValue<type>(name, param)->Get()

uint32 now = 1000000;
uint32 getMSTime() { return now; }
uint32 GetMSTimeDiffToNow(uint32 then) { return now - then; }

struct ObjectGuid
{
    uint32 value = 0;
    uint32 GetCounter() const { return value; }
    bool IsEmpty() const { return !value; }
    void Clear() { value = 0; }
    bool operator==(ObjectGuid const&) const = default;
};
using GuidVector = std::vector<ObjectGuid>;

struct WorldPosition
{
    uint32 mapId = 0;
    float x = 0.0f, y = 0.0f, z = 0.0f, o = 0.0f;
    WorldPosition() = default;
    WorldPosition(uint32 mapId, float x, float y, float z = 0.0f, float o = 0.0f) : mapId(mapId), x(x), y(y), z(z), o(o) {}
    uint32 GetMapId() const { return mapId; }
    operator bool() const { return x || y || z; }
};

struct Player;
struct WorldObject
{
    virtual ~WorldObject() = default;
    ObjectGuid guid;
    float x = 0.0f, y = 0.0f;
    uint32 mapId = 0;
    bool reachable = true;
    ObjectGuid GetGUID() const { return guid; }
    float Distance(float px, float py) const { return std::hypot(x - px, y - py); }
};
struct ItemTemplate
{
    struct ItemSpell { int32 SpellId = 0; uint32 SpellCategory = 0; };
    uint32 ItemId = 0, Class = ITEM_CLASS_REAGENT, SubClass = 0, BuyPrice = 0, BuyCount = 1, ContainerSlots = 0;
    ItemSpell Spells[MAX_ITEM_PROTO_SPELLS]{};
};
struct VendorItem { uint32 item = 0, maxcount = 0, incrtime = 0, ExtendedCost = 0, stock = 0; };
struct VendorItemData { std::vector<VendorItem*> m_items; };
struct Creature : WorldObject
{
    uint32 entry = 0, npcFlags = 0;
    bool alive = true, friendly = true;
    VendorItemData* vendor = nullptr;
    bool IsAlive() const { return alive; }
    bool IsFriendlyTo(Player const*) const { return friendly; }
    bool HasNpcFlag(NPCFlags flag) const { return npcFlags & flag; }
    uint32 GetEntry() const { return entry; }
    VendorItemData const* GetVendorItems() const { return vendor; }
    uint32 GetVendorItemCurrentCount(VendorItem const* item) const { return item->stock; }
};
struct GameObject : WorldObject {};
struct Item
{
    ItemTemplate proto;
    uint8 slot = 0;
    ItemTemplate const* GetTemplate() const { return &proto; }
    uint8 GetSlot() const { return slot; }
};
struct Bag : Item
{
    std::vector<Item*> contents;
    uint32 GetBagSize() const { return proto.ContainerSlots; }
    Item* GetItemByPos(uint8 position) const { return position < GetBagSize() ? contents[position] : nullptr; }
};
struct PlayerSpell { PlayerSpellState State = PLAYERSPELL_UNCHANGED; bool Active = true; };
struct SpellInfo
{
    struct EffectInfo { int Effect = 0; };
    EffectInfo Effects[3]{};
    int32 Reagent[MAX_SPELL_REAGENTS]{};
    uint32 ReagentCount[MAX_SPELL_REAGENTS]{};
    bool passive = false;
    bool IsPassive() const { return passive; }
};
struct Player : WorldObject
{
    bool alive = true, combat = false, flight = false, randomBot = false;
    uint32 money = 10000, maxMana = 100;
    uint8 cls = CLASS_MAGE;
    float discount = 1.0f;
    std::map<uint32, uint32> items;
    std::unordered_map<uint32, PlayerSpell*> spells;
    Item* ranged = nullptr;
    std::map<uint8, Bag*> bags;
    std::map<uint8, Item*> pack;
    std::set<uint32> unusable;
    ObjectGuid selection;
    mutable int usableChecks = 0;
    bool IsAlive() const { return alive; }
    bool IsInCombat() const { return combat; }
    bool IsInFlight() const { return flight; }
    uint32 GetMaxPower(Powers) const { return maxMana; }
    uint8 getClass() const { return cls; }
    Item* GetItemByPos(uint8 bag, uint8 slot) const
    {
        assert(bag == INVENTORY_SLOT_BAG_0);
        if (slot == EQUIPMENT_SLOT_RANGED)
            return ranged;
        if (slot >= INVENTORY_SLOT_BAG_START && slot < INVENTORY_SLOT_BAG_END)
            return GetBagByPos(slot);
        assert(slot >= INVENTORY_SLOT_ITEM_START && slot < INVENTORY_SLOT_ITEM_END);
        auto const found = pack.find(slot);
        return found == pack.end() ? nullptr : found->second;
    }
    Bag* GetBagByPos(uint8 slot) const
    {
        assert(slot >= INVENTORY_SLOT_BAG_START && slot < INVENTORY_SLOT_BAG_END);
        auto const found = bags.find(slot);
        return found == bags.end() ? nullptr : found->second;
    }
    std::unordered_map<uint32, PlayerSpell*> const& GetSpellMap() const { return spells; }
    uint32 GetItemCount(uint32 item, bool inBankAlso) const
    {
        assert(!inBankAlso);
        auto const found = items.find(item);
        return found == items.end() ? 0 : found->second;
    }
    InventoryResult CanUseItem(ItemTemplate const* proto) const
    {
        ++usableChecks;
        return unusable.count(proto->ItemId) ? EQUIP_ERR_CANT_EQUIP_SKILL : EQUIP_ERR_OK;
    }
    float GetReputationPriceDiscount(Creature const*) const { return discount; }
    bool HasEnoughMoney(uint32 price) const { return price <= money; }
    float GetExactDist(WorldPosition const& position) const { return Distance(position.x, position.y); }
    bool IsWithinDistInMap(WorldObject const* target, float distance) const { return target->Distance(x, y) <= distance; }
    ObjectGuid GetTarget() const { return selection; }
    void SetSelection(ObjectGuid guid) { selection = guid; }
    uint32 GetMapId() const { return mapId; }
    Creature* GetNPCIfCanInteractWith(ObjectGuid guid, NPCFlags flag);
};

namespace Trainer
{
struct Spell
{
    uint32 SpellId = 0, MoneyCost = 0;
    bool known = false, allowed = true;
};
struct Trainer
{
    std::vector<Spell> spells;
    bool valid = true;
    mutable int costs = 0, teaches = 0;
    bool IsTrainerValidForPlayer(Player const*) const { return valid; }
    std::vector<Spell> const& GetSpells() const { return spells; }
    uint32 GetSpellCost(Player const* player, Creature const* npc, Spell const* spell) const
    {
        ++costs;
        return uint32(floor(spell->MoneyCost * player->GetReputationPriceDiscount(npc)));
    }
    bool CanTeachSpell(Player const*, Spell const* spell) const
    {
        ++teaches;
        return !spell->known;
    }
};
}  // namespace Trainer

struct PlayerbotFactory
{
    static bool IsTrainerSpellAllowedForBot(Player*, Trainer::Trainer const*, Trainer::Spell const* spell)
    {
        return spell->allowed;
    }
};
struct ObjectMgr
{
    std::map<uint32, Trainer::Trainer> trainers;
    std::map<uint32, ItemTemplate> items;
    mutable int itemLookups = 0;
    Trainer::Trainer* GetTrainer(uint32 entry)
    {
        auto const found = trainers.find(entry);
        return found == trainers.end() ? nullptr : &found->second;
    }
    ItemTemplate const* GetItemTemplate(uint32 id) const
    {
        ++itemLookups;
        auto const found = items.find(id);
        return found == items.end() ? nullptr : &found->second;
    }
} objectMgr;
auto* sObjectMgr = &objectMgr;
struct SpellMgr
{
    std::map<uint32, SpellInfo> spells;
    SpellInfo const* GetSpellInfo(uint32 id) const
    {
        auto const found = spells.find(id);
        return found == spells.end() ? nullptr : &found->second;
    }
} spellMgr;
auto* sSpellMgr = &spellMgr;
struct PlayerbotAIConfig
{
    bool naturalProgression = true, earnedAuctions = false, AllowLearnTrainerSpells = true;
    uint32 earnedAuctionInterval = 300;
} sPlayerbotAIConfig;
struct RandomPlayerbotMgr
{
    bool IsRandomBot(Player* bot) const { return bot && bot->randomBot; }
} sRandomPlayerbotMgr;
struct ChatHelper
{
    static std::string FormatItem(ItemTemplate const* proto) { return "item:" + std::to_string(proto->ItemId); }
};
struct Event
{
    Event(std::string source = "", std::string param = "") : source(std::move(source)), param(std::move(param)) {}
    std::string source, param;
};

@@TYPES@@

struct Visit { ObjectGuid target; bool mailbox; };
struct Fixture
{
    std::map<uint32, Creature*> creatures;
    std::map<uint32, GameObject*> mailboxes;
    std::vector<Visit> visits;
    std::vector<std::pair<std::string, std::string>> actions;
    std::vector<ObjectGuid> approaches;
    WorldPosition* market = nullptr;
    bool waiting = false, queueAccepts = true, travelReachable = true, actionResult = true;
    float farStep = 40.0f;
    int plans = 0, scans = 0, consumableChecks = 0;
} world;

struct ItemUsageValue
{
    Player* bot = nullptr;
    static std::string const GetConsumableType(ItemTemplate const* proto, bool hasMana);
    uint32 GetSmallestBagSize();
};
ItemUsage ItemUpgrade(Player* bot, std::string const& qualifier);

template <class T>
class Value
{
public:
    virtual ~Value() = default;
    virtual T Get() = 0;
    virtual void Set(T value) = 0;
    virtual void Reset() {}
};
template <class T>
class ManualValue : public Value<T>
{
public:
    T value{};
    T Get() override { return value; }
    void Set(T next) override { value = next; }
};
class UpgradeValue : public Value<ItemUsage>
{
public:
    Player* bot = nullptr;
    std::string qualifier;
    ItemUsage Get() override { return ItemUpgrade(bot, qualifier); }
    void Set(ItemUsage) override {}
};
class ScanValue : public Value<GuidVector>
{
public:
    std::function<GuidVector()> scan;
    GuidVector Get() override { return scan(); }
    void Set(GuidVector) override {}
};
struct PlayerbotAI;
struct AiObjectContext
{
    std::map<std::string, ManualValue<bool>> flags;
    std::map<std::string, ManualValue<uint32>> numbers;
    std::map<std::string, UpgradeValue> upgrades;
    std::map<std::string, int> reads;
    Player* owner = nullptr;
    ScanValue rpgTargets, mailboxes;
    Value<NaturalMaintenanceTask>* maintenance = nullptr;
    template <class T>
    Value<T>* GetValue(std::string const& name, std::string const& qualifier = "")
    {
        ++reads[name];
        if constexpr (std::is_same_v<T, bool>)
            return &flags[name];
        else if constexpr (std::is_same_v<T, uint32>)
            return &numbers[name + ":" + qualifier];
        else if constexpr (std::is_same_v<T, ItemUsage>)
        {
            assert(name == "item upgrade");
            UpgradeValue& upgrade = upgrades[qualifier];
            upgrade.bot = owner;
            upgrade.qualifier = qualifier;
            return &upgrade;
        }
        else if constexpr (std::is_same_v<T, GuidVector>)
        {
            assert(name == "possible new rpg targets" || name == "natural mailboxes");
            return name == "natural mailboxes" ? &mailboxes : &rpgTargets;
        }
        else
        {
            static_assert(std::is_same_v<T, NaturalMaintenanceTask>);
            assert(name == "natural maintenance");
            return maintenance;
        }
    }
    template <class T>
    Value<T>* GetValue(std::string const& name, uint32 qualifier)
    {
        return GetValue<T>(name, std::to_string(qualifier));
    }
};
struct PlayerbotAI
{
    Player* bot = nullptr;
    AiObjectContext* context = nullptr;
    NewRpgInfo rpgInfo;
    bool gameClientMaster = false;
    Player* GetBot() { return bot; }
    AiObjectContext* GetAiObjectContext() { return context; }
    bool HasGameClientMaster() const { return gameClientMaster; }
    Creature* GetCreature(ObjectGuid guid)
    {
        auto const found = world.creatures.find(guid.value);
        return found == world.creatures.end() ? nullptr : found->second;
    }
    WorldObject* GetWorldObject(ObjectGuid guid)
    {
        if (Creature* creature = GetCreature(guid))
            return creature;
        auto const found = world.mailboxes.find(guid.value);
        return found == world.mailboxes.end() ? nullptr : found->second;
    }
    bool DoSpecificAction(std::string const& name, Event event, bool silent)
    {
        assert(silent);
        world.actions.push_back({name, event.param});
        return world.actionResult;
    }
};
Creature* Player::GetNPCIfCanInteractWith(ObjectGuid guid, NPCFlags flag)
{
    auto const found = world.creatures.find(guid.value);
    Creature* npc = found == world.creatures.end() ? nullptr : found->second;
    return npc && npc->HasNpcFlag(flag) && IsWithinDistInMap(npc, INTERACTION_DISTANCE) ? npc : nullptr;
}

template <class T>
class CalculatedValue : public Value<T>
{
public:
    CalculatedValue(PlayerbotAI* botAI, std::string const = "value", uint32 checkInterval = 1)
        : botAI(botAI), bot(botAI->bot), context(botAI->context),
          checkInterval(checkInterval == 1 ? 1 : (checkInterval < 100 ? checkInterval * IN_MILLISECONDS : checkInterval))
    {
    }
    T Get() override
    {
        if (checkInterval < 2 || !lastCheckTime || now - lastCheckTime >= checkInterval)
        {
            lastCheckTime = now;
            value = Calculate();
        }
        return value;
    }
    void Set(T next) override { value = next; }
    void Reset() override { lastCheckTime = 0; }

protected:
    virtual T Calculate() = 0;
    PlayerbotAI* botAI;
    Player* bot;
    AiObjectContext* context;
    uint32 checkInterval;
    uint32 lastCheckTime = 0;
    T value{};
};
class Trigger
{
public:
    Trigger(PlayerbotAI* botAI, std::string const) : botAI(botAI), bot(botAI->bot), context(botAI->context) {}
    virtual ~Trigger() = default;
    virtual bool IsActive() = 0;

protected:
    PlayerbotAI* botAI;
    Player* bot;
    AiObjectContext* context;
};
class NewRpgBaseAction
{
public:
    NewRpgBaseAction(PlayerbotAI* botAI, std::string const) : botAI(botAI), bot(botAI->bot), context(botAI->context) {}
    virtual ~NewRpgBaseAction() = default;
    virtual bool Execute(Event event) = 0;

protected:
    bool IsWaitingForLastMove(MovementPriority priority)
    {
        assert(priority == MovementPriority::MOVEMENT_NORMAL);
        return world.waiting;
    }
    bool MoveWorldObjectTo(ObjectGuid guid, float distance = INTERACTION_DISTANCE)
    {
        assert(distance == INTERACTION_DISTANCE);
        world.approaches.push_back(guid);
        WorldObject* target = botAI->GetWorldObject(guid);
        if (!target || !target->reachable)
            return false;
        bot->x = target->x;
        bot->y = target->y;
        return true;
    }
    bool MoveFarTo(WorldPosition destination)
    {
        if (!world.travelReachable)
            return false;
        float const distance = bot->GetExactDist(destination);
        float const step = std::min(distance, world.farStep);
        bot->x += (destination.x - bot->x) / distance * step;
        bot->y += (destination.y - bot->y) / distance * step;
        return true;
    }
    PlayerbotAI* botAI;
    Player* bot;
    AiObjectContext* context;
};

namespace EarnedAuction
{
bool IsEnabled(PlayerbotAI* ai)
{
    return ai && sPlayerbotAIConfig.naturalProgression && sPlayerbotAIConfig.earnedAuctions && ai->GetBot() &&
           !ai->HasGameClientMaster();
}
bool QueueVisit(PlayerbotAI* ai, ObjectGuid target, bool mailbox)
{
    assert(IsEnabled(ai) && !target.IsEmpty());
    world.visits.push_back({target, mailbox});
    return world.queueAccepts;
}
}  // namespace EarnedAuction
namespace EarnedAuctionTravel
{
void FinishTrip(PlayerbotAI* ai);
bool ContinueTrip(PlayerbotAI* ai);
void AbortTrip(PlayerbotAI* ai);
void PostponeVisit(PlayerbotAI* ai);
bool Ready(PlayerbotAI* ai) { return EarnedAuction::IsEnabled(ai) && !ai->GetBot()->IsInCombat(); }
bool CompatibleAuctioneer(PlayerbotAI*, Creature* npc)
{
    return npc && npc->IsAlive() && npc->HasNpcFlag(UNIT_NPC_FLAG_AUCTIONEER);
}
@@TRAVEL@@
WorldPosition PlanTrip(PlayerbotAI* ai)
{
    ++world.plans;
    if (ContinueTrip(ai))
        return ai->rpgInfo.earnedAuctionTravelDestination;
    if (!Ready(ai))
        return {};
    auto& info = ai->rpgInfo;
    if (info.earnedAuctionTravelClockStarted &&
        !TravelBackoffElapsed(GetMSTimeDiffToNow(info.earnedAuctionTravelLastAttempt)))
        return {};
    info.earnedAuctionTravelClockStarted = true;
    info.earnedAuctionTravelLastAttempt = getMSTime();
    if (!world.market)
        return {};
    info.earnedAuctionTravelDestination = *world.market;
    info.earnedAuctionTravelStarted = getMSTime();
    info.earnedAuctionTravelActive = true;
    return info.earnedAuctionTravelDestination;
}
}  // namespace EarnedAuctionTravel

@@USAGE@@
std::string const ItemUsageValue::GetConsumableType(ItemTemplate const* proto, bool hasMana)
{
    ++world.consumableChecks;
    return ProductionConsumableType(proto, hasMana);
}
@@SMALLEST@@
// ItemUpgradeValue of a bag: QueryItemUsageForEquip's usability check and container
// branch, which the script asserts in the production source.
ItemUsage ItemUpgrade(Player* bot, std::string const& qualifier)
{
    ItemTemplate const& proto = objectMgr.items.at(uint32(std::stoul(qualifier)));
    if (bot->unusable.count(proto.ItemId) || proto.Class != ITEM_CLASS_CONTAINER)
        return ITEM_USAGE_NONE;
    if (proto.SubClass != ITEM_SUBCLASS_CONTAINER)
        return ITEM_USAGE_NONE;
    ItemUsageValue usage{bot};
    if (usage.GetSmallestBagSize() >= proto.ContainerSlots)
        return ITEM_USAGE_NONE;
    return ITEM_USAGE_EQUIP;
}

@@CLASSES@@
@@GUARD@@
@@HELPERS@@
@@VALUE@@
@@ACTION@@
@@TRIGGER@@
'''

tests = r'''
using Type = NaturalMaintenanceType;

struct Scenario
{
    Player bot;
    AiObjectContext context;
    PlayerbotAI ai;
    std::deque<Creature> npcs;
    std::deque<GameObject> boxes;
    std::deque<VendorItemData> stocks;
    std::deque<VendorItem> stock;
    std::deque<::Item> weapons;
    std::deque<Bag> containers;
    std::deque<::Item> fillers;
    std::deque<PlayerSpell> learned;
    std::unique_ptr<NaturalMaintenanceValue> value;
    std::unique_ptr<NewRpgNaturalMaintenanceAction> action;
    std::unique_ptr<NewRpgNaturalMaintenanceTrigger> trigger;
    uint32 nextGuid = 100;

    Scenario()
    {
        world = Fixture();
        objectMgr = ObjectMgr();
        spellMgr = SpellMgr();
        sPlayerbotAIConfig = PlayerbotAIConfig();
        now = 1000000;
        bot.guid = {7};
        ai.bot = &bot;
        ai.context = &context;
        context.owner = &bot;
        context.flags["can move around"].value = true;
        context.rpgTargets.scan = [this]() { return Nearby(world.creatures); };
        context.mailboxes.scan = [this]() { return Nearby(world.mailboxes); };
        value = std::make_unique<NaturalMaintenanceValue>(&ai);
        context.maintenance = value.get();
        action = std::make_unique<NewRpgNaturalMaintenanceAction>(&ai);
        trigger = std::make_unique<NewRpgNaturalMaintenanceTrigger>(&ai);
        Count("food", 20);
        Count("drink", 20);
        Count("ammo", 1000);
    }
    template <class Map>
    GuidVector Nearby(Map const& objects)
    {
        if constexpr (std::is_same_v<Map, std::map<uint32, Creature*>>)
            ++world.scans;
        std::vector<std::pair<float, ObjectGuid>> found;
        for (auto const& [id, object] : objects)
            if (object->Distance(bot.x, bot.y) <= 150.0f)
                found.push_back({object->Distance(bot.x, bot.y), object->guid});
        std::sort(found.begin(), found.end(), [](auto const& a, auto const& b) { return a.first < b.first; });
        GuidVector result;
        for (auto const& entry : found)
            result.push_back(entry.second);
        return result;
    }
    void Flag(std::string const& name, bool enabled) { context.flags[name].value = enabled; }
    void Budget(NeedMoneyFor type, uint32 copper)
    {
        context.numbers["free money for:" + std::to_string(uint32(type))].value = copper;
    }
    void Count(std::string const& type, uint32 count) { context.numbers["item count:" + type].value = count; }
    Creature& Npc(uint32 flags, float x, float y = 0.0f)
    {
        Creature& npc = npcs.emplace_back();
        npc.guid = {++nextGuid};
        npc.entry = nextGuid;
        npc.npcFlags = flags;
        npc.x = x;
        npc.y = y;
        world.creatures[npc.guid.value] = &npc;
        return npc;
    }
    GameObject& Mailbox(float x)
    {
        GameObject& box = boxes.emplace_back();
        box.guid = {200000 + ++nextGuid};
        box.x = x;
        world.mailboxes[box.guid.value] = &box;
        return box;
    }
    ItemTemplate& Template(uint32 itemClass, uint32 subclass, uint32 price = 0, uint32 category = 0)
    {
        uint32 const id = 1000 + uint32(objectMgr.items.size());
        ItemTemplate& proto = objectMgr.items[id];
        proto.ItemId = id;
        proto.Class = itemClass;
        proto.SubClass = subclass;
        proto.BuyPrice = price;
        proto.Spells[0].SpellCategory = category;
        return proto;
    }
    VendorItem& Stock(Creature& npc, ItemTemplate const& proto)
    {
        if (!npc.vendor)
            npc.vendor = &stocks.emplace_back();
        VendorItem& item = stock.emplace_back();
        item.item = proto.ItemId;
        npc.vendor->m_items.push_back(&item);
        return item;
    }
    Trainer::Spell& Lesson(Creature& npc, uint32 spellId, uint32 cost, bool known = false)
    {
        Trainer::Trainer& trainer = objectMgr.trainers[npc.entry];
        trainer.spells.push_back({spellId, cost, known, true});
        return trainer.spells.back();
    }
    ItemTemplate& BagTemplate(uint32 slots, uint32 price, uint32 subclass = ITEM_SUBCLASS_CONTAINER,
                              uint32 itemClass = ITEM_CLASS_CONTAINER)
    {
        ItemTemplate& proto = Template(itemClass, subclass, price);
        proto.ContainerSlots = slots;
        return proto;
    }
    Bag& Container(ItemTemplate const& proto)
    {
        Bag& bag = containers.emplace_back();
        bag.proto = proto;
        bag.contents.resize(proto.ContainerSlots);
        return bag;
    }
    Bag& Equip(uint8 slot, ItemTemplate const& proto)
    {
        Bag& bag = Container(proto);
        bag.slot = slot;
        bot.bags[slot] = &bag;
        return bag;
    }
    // An unequipped bag in the backpack, or inside an equipped bag.
    void Carry(ItemTemplate const& proto, Bag* inside = nullptr)
    {
        Bag& bag = Container(proto);
        if (inside)
            inside->contents[0] = &bag;
        else
            bot.pack[uint8(INVENTORY_SLOT_ITEM_START + bot.pack.size())] = &bag;
    }
    void FillBackpack()
    {
        for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
            bot.pack[slot] = &fillers.emplace_back();
    }
    void Ranged(uint32 subclass)
    {
        ::Item& weapon = weapons.emplace_back();
        weapon.proto.Class = ITEM_CLASS_WEAPON;
        weapon.proto.SubClass = subclass;
        bot.ranged = &weapon;
    }
    void Learn(uint32 spellId, uint32 reagent, uint32 count, bool passive = false, bool active = true,
               PlayerSpellState state = PLAYERSPELL_UNCHANGED)
    {
        bot.spells[spellId] = &learned.emplace_back(PlayerSpell{state, active});
        SpellInfo& info = spellMgr.spells[spellId];
        info.passive = passive;
        info.Reagent[0] = int32(reagent);
        info.ReagentCount[0] = count;
    }
    NaturalMaintenanceTask Evaluate()
    {
        value->Reset();
        return value->Get();
    }
    bool Is(NaturalMaintenanceTask const& task, Type type, WorldObject const& target)
    {
        return task.type == type && task.target == target.guid;
    }
    bool Tick(uint32 elapsed = 1000)
    {
        now += elapsed;
        if (!trigger->IsActive())
            return false;
        return action->Execute(Event());
    }
    void DueAuctionVisit()
    {
        sPlayerbotAIConfig.earnedAuctions = true;
        ai.rpgInfo.earnedAuctionClockStarted = true;
        ai.rpgInfo.earnedAuctionLastVisit = now - 1;
        ai.rpgInfo.earnedAuctionVisitDelay = 0;
    }
};

void GuardTests()
{
    Scenario s;
    Creature& vendor = s.Npc(UNIT_NPC_FLAG_VENDOR | UNIT_NPC_FLAG_REPAIR, 10.0f);
    s.Flag("can sell", true);
    assert(s.Is(s.Evaluate(), Type::SELL, vendor));
    std::vector<std::function<void(bool)>> guards = {
        [&](bool on) { sPlayerbotAIConfig.naturalProgression = !on; },
        [&](bool on) { s.bot.alive = !on; },
        [&](bool on) { s.bot.combat = on; },
        [&](bool on) { s.bot.flight = on; },
        [&](bool on) { s.ai.gameClientMaster = on; },
        [&](bool on) { s.Flag("can move around", !on); },
    };
    for (auto const& guard : guards)
    {
        guard(true);
        assert(s.Evaluate().type == Type::NONE);
        assert(!s.trigger->IsActive());
        s.value->Set({vendor.guid, Type::SELL});
        assert(!s.action->Execute(Event()) && s.value->Get().type == Type::NONE);
        guard(false);
    }
    assert(world.actions.empty() && world.approaches.empty());
    assert(s.Is(s.Evaluate(), Type::SELL, vendor));

    // Any guard ends an auction trip and backs off before the next one.
    WorldPosition market(0, 1000.0f, 0.0f);
    world.market = &market;
    s.DueAuctionVisit();
    assert(s.Evaluate().type == Type::AUCTION_TRAVEL && s.ai.rpgInfo.earnedAuctionTravelActive);
    s.bot.combat = true;
    assert(s.Evaluate().type == Type::NONE && !s.ai.rpgInfo.earnedAuctionTravelActive);
    assert(s.ai.rpgInfo.earnedAuctionLastVisit == now &&
           s.ai.rpgInfo.earnedAuctionVisitDelay == EarnedAuctionTravel::TravelBackoffMs);
}

void SellAndRepairTests()
{
    Scenario s;
    Creature& vendor = s.Npc(UNIT_NPC_FLAG_VENDOR, 5.0f);
    Creature& smith = s.Npc(UNIT_NPC_FLAG_VENDOR | UNIT_NPC_FLAG_REPAIR, 20.0f);
    assert(s.Evaluate().type == Type::NONE);
    s.Flag("should repair", true);
    assert(s.Evaluate().type == Type::NONE);
    s.Flag("can repair", true);
    // The nearer plain vendor cannot repair.
    assert(s.Is(s.Evaluate(), Type::REPAIR, smith));
    s.Flag("can sell", true);
    assert(s.Is(s.Evaluate(), Type::SELL, vendor));
    vendor.friendly = false;
    assert(s.Is(s.Evaluate(), Type::SELL, smith));
    smith.alive = false;
    assert(s.Evaluate().type == Type::NONE);
    smith.alive = true;
    s.Flag("can sell", false);

    // The action walks to the NPC, repairs and restores the previous selection.
    s.bot.selection = {42};
    assert(s.Is(s.Evaluate(), Type::REPAIR, smith));
    assert(s.Tick() && world.approaches.size() == 1 && world.actions.empty());
    assert(s.Is(s.value->Get(), Type::REPAIR, smith));
    assert(s.Tick() && world.actions.size() == 1 && world.actions[0].first == "repair");
    assert(s.value->Get().type == Type::NONE && s.bot.selection.value == 42);
    // Repair cost is checked again at the NPC.
    s.value->Set({smith.guid, Type::REPAIR});
    s.Flag("can repair", false);
    assert(!s.action->Execute(Event()) && world.actions.size() == 1);
    s.value->Set({vendor.guid, Type::SELL});
    s.bot.x = vendor.x;
    vendor.friendly = true;
    assert(s.action->Execute(Event()));
    assert(world.actions.back() == std::make_pair(std::string("sell"), std::string("vendor")));
}

void TrainerTests()
{
    Scenario s;
    Creature& trainer = s.Npc(UNIT_NPC_FLAG_TRAINER, 10.0f);
    s.Lesson(trainer, 10, 5, true);
    Trainer::Spell& lesson = s.Lesson(trainer, 11, 100);
    assert(s.Evaluate().type == Type::NONE);
    s.Budget(NeedMoneyFor::spells, 99);
    assert(s.Evaluate().type == Type::NONE);
    s.Budget(NeedMoneyFor::spells, 100);
    assert(s.Is(s.Evaluate(), Type::TRAIN, trainer));
    s.bot.money = 99;
    assert(s.Evaluate().type == Type::NONE);
    s.bot.money = 10000;
    s.bot.discount = 0.9f;
    s.Budget(NeedMoneyFor::spells, 90);
    assert(s.Is(s.Evaluate(), Type::TRAIN, trainer));
    s.bot.discount = 1.0f;
    s.Budget(NeedMoneyFor::spells, 100);
    lesson.allowed = false;
    assert(s.Evaluate().type == Type::NONE);
    lesson.allowed = true;
    lesson.known = true;
    assert(s.Evaluate().type == Type::NONE);
    lesson.known = false;
    objectMgr.trainers[trainer.entry].valid = false;
    assert(s.Evaluate().type == Type::NONE);
    objectMgr.trainers[trainer.entry].valid = true;
    sPlayerbotAIConfig.AllowLearnTrainerSpells = false;
    assert(s.Evaluate().type == Type::NONE);
    sPlayerbotAIConfig.AllowLearnTrainerSpells = true;
    s.bot.x = trainer.x;
    assert(s.Is(s.Evaluate(), Type::TRAIN, trainer) && s.Tick(0));
    assert(world.actions.back() == std::make_pair(std::string("trainer"), std::string("learn")));
}

void SupplyTests()
{
    Scenario s;
    Creature& vendor = s.Npc(UNIT_NPC_FLAG_VENDOR, 10.0f);
    ItemTemplate& food = s.Template(ITEM_CLASS_CONSUMABLE, ITEM_SUBCLASS_FOOD, 50, 11);
    ItemTemplate& drink = s.Template(ITEM_CLASS_CONSUMABLE, ITEM_SUBCLASS_CONSUMABLE, 60, 59);
    ItemTemplate& arrows = s.Template(ITEM_CLASS_PROJECTILE, ITEM_SUBCLASS_ARROW, 10);
    ItemTemplate& bullets = s.Template(ITEM_CLASS_PROJECTILE, ITEM_SUBCLASS_BULLET, 12);
    ItemTemplate& reagent = s.Template(ITEM_CLASS_REAGENT, 0, 30);
    ItemTemplate& token = s.Template(ITEM_CLASS_REAGENT, 0, 1);
    for (ItemTemplate const* proto : {&food, &drink, &arrows, &bullets, &reagent})
        s.Stock(vendor, *proto);
    s.Stock(vendor, token).ExtendedCost = 7;
    auto const buys = [&](ItemTemplate const& proto, NeedMoneyFor budget)
    {
        NaturalMaintenanceTask const task = s.Evaluate();
        return s.Is(task, Type::BUY, vendor) && task.itemId == proto.ItemId && task.budgetType == uint32(budget);
    };

    s.Budget(NeedMoneyFor::consumables, 100);
    assert(s.Evaluate().type == Type::NONE);
    s.Count("food", 4);
    assert(buys(food, NeedMoneyFor::consumables));
    s.Budget(NeedMoneyFor::consumables, 49);
    assert(s.Evaluate().type == Type::NONE);
    s.Budget(NeedMoneyFor::consumables, 100);
    s.bot.unusable.insert(food.ItemId);
    assert(s.Evaluate().type == Type::NONE);
    s.bot.unusable.clear();
    s.Count("food", 20);
    s.Count("drink", 4);
    assert(buys(drink, NeedMoneyFor::consumables));
    s.bot.maxMana = 0;
    assert(s.Evaluate().type == Type::NONE);
    s.bot.maxMana = 100;
    s.Count("drink", 20);
    s.Budget(NeedMoneyFor::consumables, 0);
    s.Count("drink", 0);
    assert(s.Evaluate().type == Type::NONE);

    // Hunters buy the ammunition their equipped ranged weapon fires.
    s.Budget(NeedMoneyFor::ammo, 100);
    s.Count("ammo", 199);
    assert(s.Evaluate().type == Type::NONE);
    s.bot.cls = CLASS_HUNTER;
    assert(s.Evaluate().type == Type::NONE);
    s.Ranged(ITEM_SUBCLASS_WEAPON_GUN);
    assert(buys(bullets, NeedMoneyFor::ammo));
    s.Ranged(ITEM_SUBCLASS_WEAPON_CROSSBOW);
    assert(buys(arrows, NeedMoneyFor::ammo));
    s.Count("ammo", 200);
    assert(s.Evaluate().type == Type::NONE);
    s.Budget(NeedMoneyFor::ammo, 0);

    // Only active, learned, non-passive spells make reagents a paid goal.
    s.Budget(NeedMoneyFor::spells, 100);
    s.Learn(500, reagent.ItemId, 2, true);
    assert(s.Evaluate().type == Type::NONE);
    s.Learn(501, reagent.ItemId, 2, false, false);
    assert(s.Evaluate().type == Type::NONE);
    s.Learn(502, reagent.ItemId, 2, false, true, PLAYERSPELL_REMOVED);
    assert(s.Evaluate().type == Type::NONE);
    s.Learn(503, reagent.ItemId, 2);
    s.bot.items[reagent.ItemId] = 3;
    assert(buys(reagent, NeedMoneyFor::spells));
    s.bot.items[reagent.ItemId] = 4;
    assert(s.Evaluate().type == Type::NONE);
    s.Learn(504, token.ItemId, 1);
    assert(s.Evaluate().type == Type::NONE);
    s.bot.items[reagent.ItemId] = 0;
    VendorItem& limited = *vendor.vendor->m_items[4];
    limited.maxcount = 5;
    assert(s.Evaluate().type == Type::NONE);
    limited.stock = 1;
    assert(buys(reagent, NeedMoneyFor::spells));
    s.Budget(NeedMoneyFor::spells, 29);
    assert(s.Evaluate().type == Type::NONE);
    s.bot.discount = 0.8f;
    s.Budget(NeedMoneyFor::spells, 24);
    assert(buys(reagent, NeedMoneyFor::spells));

    // The budget and price are checked again at the vendor.
    s.bot.x = vendor.x;
    s.Budget(NeedMoneyFor::spells, 23);
    assert(!s.Tick(0) && world.actions.empty());
    s.Budget(NeedMoneyFor::spells, 24);
    // The vendor that just failed is skipped for one search.
    assert(s.Evaluate().type == Type::NONE);
    assert(buys(reagent, NeedMoneyFor::spells) && s.Tick(0));
    assert(world.actions.back() == std::make_pair(std::string("buy"), "item:" + std::to_string(reagent.ItemId)));
}

void AuctionVisitTests()
{
    Scenario s;
    sPlayerbotAIConfig.earnedAuctions = true;
    Creature& vendor = s.Npc(UNIT_NPC_FLAG_VENDOR, 5.0f);
    Creature& auctioneer = s.Npc(UNIT_NPC_FLAG_AUCTIONEER, 40.0f);
    GameObject& mailbox = s.Mailbox(30.0f);
    s.Flag("can sell", true);
    // The first evaluation staggers the first visit by the bot's guid.
    assert(s.Is(s.Evaluate(), Type::SELL, vendor));
    assert(s.ai.rpgInfo.earnedAuctionClockStarted && s.ai.rpgInfo.earnedAuctionVisitDelay == 7 * IN_MILLISECONDS);
    now += 7 * IN_MILLISECONDS;
    assert(s.Is(s.Evaluate(), Type::AUCTION_MAIL, mailbox));
    s.ai.rpgInfo.earnedAuctionVisitMailbox = false;
    assert(s.Is(s.Evaluate(), Type::AUCTION, auctioneer));
    auctioneer.alive = false;
    assert(s.Is(s.Evaluate(), Type::AUCTION_MAIL, mailbox));
    world.mailboxes.clear();
    assert(s.Is(s.Evaluate(), Type::SELL, vendor) && world.plans == 1);
    world.mailboxes[mailbox.guid.value] = &mailbox;
    auctioneer.alive = true;
    s.ai.rpgInfo.earnedAuctionVisitMailbox = true;

    // A completed mailbox visit schedules the next one and alternates to the auctioneer.
    assert(s.Is(s.Evaluate(), Type::AUCTION_MAIL, mailbox));
    assert(s.Tick(0) && world.visits.empty());
    assert(s.Tick(0) && world.visits.size() == 1 && world.visits[0].target == mailbox.guid && world.visits[0].mailbox);
    assert(s.ai.rpgInfo.earnedAuctionLastVisit == now && !s.ai.rpgInfo.earnedAuctionVisitMailbox);
    assert(s.ai.rpgInfo.earnedAuctionVisitDelay == (300 + 7) * IN_MILLISECONDS);
    assert(s.value->Get().type == Type::NONE);
    now += 306 * IN_MILLISECONDS;
    assert(s.Evaluate().type == Type::SELL);
    now += IN_MILLISECONDS;
    assert(s.Is(s.Evaluate(), Type::AUCTION, auctioneer));
    assert(s.Tick(0) && s.Tick(0) && world.visits.size() == 2 && !world.visits[1].mailbox);
    assert(s.ai.rpgInfo.earnedAuctionVisitMailbox);
}

void AuctionTravelTests()
{
    {
        // Distant bots walk to the market and switch to the auctioneer once it is in range.
        Scenario s;
        WorldPosition market(0, 1000.0f, 0.0f);
        world.market = &market;
        Creature& auctioneer = s.Npc(UNIT_NPC_FLAG_AUCTIONEER, 1000.0f, 2.0f);
        s.DueAuctionVisit();
        NaturalMaintenanceTask const task = s.Evaluate();
        assert(task.type == Type::AUCTION_TRAVEL && task.destination.x == 1000.0f && s.trigger->IsActive());
        int ticks = 0;
        while (s.value->Get().type == Type::AUCTION_TRAVEL)
            assert(s.Tick(100) && ++ticks < 40);
        assert(s.Is(s.value->Get(), Type::AUCTION, auctioneer) && s.bot.GetExactDist(market) <= 150.0f);
        assert(s.Tick(100) && s.Tick(100) && world.visits.size() == 1);
        assert(!s.ai.rpgInfo.earnedAuctionTravelActive && s.ai.rpgInfo.earnedAuctionTravelLastAttempt == now);
    }
    {
        // Arriving without a compatible auctioneer ends the trip and backs off.
        Scenario s;
        WorldPosition market(0, 400.0f, 0.0f);
        world.market = &market;
        s.DueAuctionVisit();
        assert(s.Evaluate().type == Type::AUCTION_TRAVEL);
        int ticks = 0;
        while (s.Tick(100))
            assert(++ticks < 40);
        assert(s.bot.GetExactDist(market) <= INTERACTION_DISTANCE && !s.ai.rpgInfo.earnedAuctionTravelActive);
        assert(s.ai.rpgInfo.earnedAuctionVisitDelay == EarnedAuctionTravel::TravelBackoffMs);
        assert(s.value->Get().type == Type::NONE && world.visits.empty());
    }
    {
        // A failed path or an expired trip also backs off.
        Scenario s;
        WorldPosition market(0, 1000.0f, 0.0f);
        world.market = &market;
        s.DueAuctionVisit();
        assert(s.Evaluate().type == Type::AUCTION_TRAVEL);
        world.travelReachable = false;
        assert(!s.Tick(100) && !s.ai.rpgInfo.earnedAuctionTravelActive);
        assert(s.ai.rpgInfo.earnedAuctionVisitDelay == EarnedAuctionTravel::TravelBackoffMs);
        world.travelReachable = true;
        now += EarnedAuctionTravel::TravelBackoffMs;
        s.DueAuctionVisit();
        assert(s.Evaluate().type == Type::AUCTION_TRAVEL && s.Tick(100));
        assert(!s.Tick(EarnedAuctionTravel::MaximumTravelTimeMs) && !s.ai.rpgInfo.earnedAuctionTravelActive);
    }
}

void StarvationTests()
{
    {
        // An unreachable mailbox postpones the visit, so the bot still repairs nearby.
        Scenario s;
        Creature& smith = s.Npc(UNIT_NPC_FLAG_REPAIR, 20.0f);
        GameObject& mailbox = s.Mailbox(10.0f);
        mailbox.reachable = false;
        s.Flag("should repair", true);
        s.Flag("can repair", true);
        s.DueAuctionVisit();
        assert(s.Is(s.Evaluate(), Type::AUCTION_MAIL, mailbox));
        assert(!s.Tick() && s.value->Get().type == Type::NONE && world.visits.empty());
        assert(s.ai.rpgInfo.earnedAuctionLastVisit == now &&
               s.ai.rpgInfo.earnedAuctionVisitDelay == EarnedAuctionTravel::TravelBackoffMs);
        assert(s.ai.rpgInfo.earnedAuctionVisitMailbox);
        now += 30 * IN_MILLISECONDS;
        assert(s.Is(s.value->Get(), Type::REPAIR, smith));
        assert(s.Tick(0) && s.Tick(0) && world.actions.back().first == "repair");
        now += EarnedAuctionTravel::TravelBackoffMs;
        mailbox.reachable = true;
        assert(s.Is(s.Evaluate(), Type::AUCTION_MAIL, mailbox));
    }
    {
        // The same applies to an unreachable auctioneer and to a visit the world thread rejects.
        Scenario s;
        Creature& vendor = s.Npc(UNIT_NPC_FLAG_VENDOR, 50.0f);
        Creature& auctioneer = s.Npc(UNIT_NPC_FLAG_AUCTIONEER, 10.0f);
        auctioneer.reachable = false;
        s.Flag("can sell", true);
        s.DueAuctionVisit();
        s.ai.rpgInfo.earnedAuctionVisitMailbox = false;
        assert(s.Is(s.Evaluate(), Type::AUCTION, auctioneer));
        assert(!s.Tick() && s.ai.rpgInfo.earnedAuctionVisitDelay == EarnedAuctionTravel::TravelBackoffMs);
        assert(s.Is(s.Evaluate(), Type::SELL, vendor));
        auctioneer.reachable = true;
        world.queueAccepts = false;
        s.DueAuctionVisit();
        assert(s.Is(s.Evaluate(), Type::AUCTION, auctioneer) && s.Tick(0));
        assert(!s.Tick(0) && world.visits.size() == 1 && !s.ai.rpgInfo.earnedAuctionVisitMailbox);
        assert(s.ai.rpgInfo.earnedAuctionLastVisit == now &&
               s.ai.rpgInfo.earnedAuctionVisitDelay == EarnedAuctionTravel::TravelBackoffMs);
        assert(s.Is(s.Evaluate(), Type::SELL, vendor));
    }
    {
        // An unreachable or failed NPC is skipped for one search, so another NPC can serve.
        Scenario s;
        Creature& vendor = s.Npc(UNIT_NPC_FLAG_VENDOR, 10.0f);
        Creature& smith = s.Npc(UNIT_NPC_FLAG_VENDOR | UNIT_NPC_FLAG_REPAIR, 40.0f);
        vendor.reachable = false;
        s.Flag("can sell", true);
        assert(s.Is(s.Evaluate(), Type::SELL, vendor));
        assert(!s.Tick() && s.ai.rpgInfo.naturalMaintenanceRejected == vendor.guid);
        now += 30 * IN_MILLISECONDS;
        assert(s.Is(s.value->Get(), Type::SELL, smith) && s.ai.rpgInfo.naturalMaintenanceRejected.IsEmpty());
        assert(s.Is(s.Evaluate(), Type::SELL, vendor));
        vendor.reachable = true;
        world.actionResult = false;
        assert(s.Tick(0) && !s.Tick(0) && world.actions.back().first == "sell");
        assert(s.ai.rpgInfo.naturalMaintenanceRejected == vendor.guid);
        assert(s.Is(s.Evaluate(), Type::SELL, smith));
        world.actionResult = true;
        assert(s.Tick(0) && s.Tick(0) && s.ai.rpgInfo.naturalMaintenanceRejected.IsEmpty());
    }
}

void CostTests()
{
    {
        // Vendor stock is not inspected unless a supply is wanted, and known lessons get no price quote.
        Scenario s;
        Creature& npc = s.Npc(UNIT_NPC_FLAG_VENDOR | UNIT_NPC_FLAG_TRAINER, 10.0f);
        std::vector<ItemTemplate*> food;
        for (int i = 0; i < 3; ++i)
            s.Stock(npc, *food.emplace_back(&s.Template(ITEM_CLASS_CONSUMABLE, ITEM_SUBCLASS_FOOD, 50, 11)));
        ItemTemplate& arrows = s.Template(ITEM_CLASS_PROJECTILE, ITEM_SUBCLASS_ARROW, 10);
        s.Stock(npc, arrows);
        s.Lesson(npc, 10, 5, true);
        s.Lesson(npc, 11, 5, true);
        s.Budget(NeedMoneyFor::spells, 100);
        assert(s.Evaluate().type == Type::NONE);
        Trainer::Trainer const& trainer = objectMgr.trainers[npc.entry];
        assert(trainer.teaches == 2 && !trainer.costs);
        assert(!objectMgr.itemLookups && !s.bot.usableChecks && !world.consumableChecks);

        // Only stock in a wanted supply category pays for usability and consumable checks.
        s.bot.cls = CLASS_HUNTER;
        s.Ranged(ITEM_SUBCLASS_WEAPON_BOW);
        s.Budget(NeedMoneyFor::ammo, 100);
        s.Count("ammo", 0);
        NaturalMaintenanceTask const ammo = s.Evaluate();
        assert(s.Is(ammo, Type::BUY, npc) && ammo.itemId == arrows.ItemId);
        assert(s.bot.usableChecks == 1 && !world.consumableChecks);
        s.Budget(NeedMoneyFor::consumables, 100);
        s.Count("food", 0);
        s.bot.unusable.insert(food[0]->ItemId);
        s.bot.usableChecks = 0;
        NaturalMaintenanceTask const meal = s.Evaluate();
        assert(s.Is(meal, Type::BUY, npc) && meal.itemId == food[1]->ItemId);
        assert(s.bot.usableChecks == 2 && world.consumableChecks == 2);
    }
    {
        // A due auction visit does not evaluate vendor surplus first.
        Scenario s;
        GameObject& mailbox = s.Mailbox(10.0f);
        s.DueAuctionVisit();
        assert(s.Is(s.Evaluate(), Type::AUCTION_MAIL, mailbox) && !s.context.reads.count("can sell"));
        s.ai.rpgInfo.earnedAuctionVisitDelay = 3600 * IN_MILLISECONDS;
        assert(s.Evaluate().type == Type::NONE && s.context.reads["can sell"] == 1);
    }
    {
        // A market approach searches for the auctioneer every two seconds and on arrival.
        Scenario s;
        WorldPosition market(0, 400.0f, 0.0f);
        world.market = &market;
        world.farStep = 10.0f;
        s.DueAuctionVisit();
        assert(s.Evaluate().type == Type::AUCTION_TRAVEL);
        world.scans = 0;
        int ticks = 0;
        while (s.Tick(100))
            assert(++ticks < 60);
        assert(s.bot.GetExactDist(market) <= INTERACTION_DISTANCE && world.scans == 2);
    }
}

void BagTests()
{
    Scenario s;
    s.bot.randomBot = true;
    Creature& vendor = s.Npc(UNIT_NPC_FLAG_VENDOR, 10.0f);
    ItemTemplate& herbs = s.BagTemplate(12, 50, ITEM_SUBCLASS_HERB_CONTAINER);
    ItemTemplate& pouch = s.BagTemplate(6, 100);
    ItemTemplate& satchel = s.BagTemplate(8, 500);
    for (ItemTemplate const* proto : {&herbs, &pouch, &satchel})
        s.Stock(vendor, *proto);
    auto const buys = [&](ItemTemplate const& proto)
    {
        NaturalMaintenanceTask const task = s.Evaluate();
        return s.Is(task, Type::BUY, vendor) && task.itemId == proto.ItemId &&
               task.budgetType == uint32(NeedMoneyFor::gear);
    };

    // A random bot buys the largest general bag its own gear budget pays for.
    assert(s.Evaluate().type == Type::NONE);
    s.Budget(NeedMoneyFor::gear, 499);
    assert(buys(pouch));
    s.Budget(NeedMoneyFor::gear, 500);
    assert(buys(satchel));
    s.bot.money = 499;
    assert(buys(pouch));
    s.bot.money = 99;
    assert(s.Evaluate().type == Type::NONE);
    s.bot.money = 10000;
    s.bot.discount = 0.8f;
    s.Budget(NeedMoneyFor::gear, 400);
    assert(buys(satchel));
    s.bot.discount = 1.0f;
    s.Budget(NeedMoneyFor::gear, 500);

    // Characters players own keep their gear choices.
    s.bot.randomBot = false;
    s.context.reads.clear();
    assert(s.Evaluate().type == Type::NONE && !s.context.reads.count("item upgrade"));
    s.bot.randomBot = true;

    // A bag must pass the upgrade check EquipAction applies, and limited stock must cover it.
    s.bot.unusable.insert(satchel.ItemId);
    assert(buys(pouch));
    s.bot.unusable.clear();
    VendorItem& limited = *vendor.vendor->m_items[2];
    limited.maxcount = 1;
    assert(buys(pouch));
    limited.stock = 1;
    assert(buys(satchel));
    limited.maxcount = 0;
    ItemTemplate& cheaper = s.BagTemplate(8, 450);
    s.Stock(vendor, cheaper);
    assert(buys(cheaper));

    // Bags fill free slots, then replace the smallest general bag the upgrade check accepts.
    s.Equip(INVENTORY_SLOT_BAG_START, pouch);
    assert(buys(cheaper));
    s.FillBackpack();
    assert(buys(cheaper));
    s.bot.pack.clear();
    for (uint8 slot = INVENTORY_SLOT_BAG_START + 1; slot < INVENTORY_SLOT_BAG_END; ++slot)
        s.Equip(slot, satchel);
    assert(s.Evaluate().type == Type::NONE);
    ItemTemplate& sack = s.BagTemplate(10, 2000);
    s.Stock(vendor, sack);
    assert(s.Evaluate().type == Type::NONE);
    s.Budget(NeedMoneyFor::gear, 2000);
    assert(buys(sack));
    // A bag stored inside the bag it replaces could not be equipped from there.
    s.FillBackpack();
    assert(s.Evaluate().type == Type::NONE);
    s.bot.pack.erase(INVENTORY_SLOT_ITEM_END - 1);
    assert(buys(sack));
    s.bot.pack.clear();

    // A quiver, ammo pouch or profession bag is never displaced by a general bag.
    ItemTemplate& quiver = s.BagTemplate(6, 0, 2, ITEM_CLASS_QUIVER);
    s.Equip(INVENTORY_SLOT_BAG_START, quiver);
    assert(s.Evaluate().type == Type::NONE);
    s.Equip(INVENTORY_SLOT_BAG_START, herbs);
    assert(buys(sack));
    s.Equip(INVENTORY_SLOT_BAG_START, pouch);

    // A carried upgrade is equipped, or stays stuck, without buying another bag.
    s.bot.bags.erase(INVENTORY_SLOT_BAG_START + 3);
    s.Carry(satchel);
    assert(s.Evaluate().type == Type::NONE);
    s.bot.pack.clear();
    s.Carry(satchel, s.bot.bags[INVENTORY_SLOT_BAG_START]);
    assert(s.Evaluate().type == Type::NONE);
    s.bot.bags[INVENTORY_SLOT_BAG_START]->contents[0] = nullptr;
    s.Carry(herbs);
    s.bot.unusable.insert(pouch.ItemId);
    s.Carry(pouch);
    assert(buys(sack));
    s.bot.unusable.clear();
    s.bot.pack.clear();
    s.Equip(INVENTORY_SLOT_BAG_START + 3, satchel);

    // Wanted supplies come first; the price is checked again at the vendor.
    ItemTemplate& food = s.Template(ITEM_CLASS_CONSUMABLE, ITEM_SUBCLASS_FOOD, 50, 11);
    s.Stock(vendor, food);
    s.Budget(NeedMoneyFor::consumables, 100);
    s.Count("food", 0);
    NaturalMaintenanceTask const meal = s.Evaluate();
    assert(s.Is(meal, Type::BUY, vendor) && meal.itemId == food.ItemId);
    s.Count("food", 20);
    s.bot.x = vendor.x;
    assert(buys(sack));
    s.Budget(NeedMoneyFor::gear, 1999);
    assert(!s.Tick(0) && world.actions.empty());
    s.Budget(NeedMoneyFor::gear, 2000);
    assert(s.Evaluate().type == Type::NONE);
    assert(buys(sack) && s.Tick(0));
    assert(world.actions.back() == std::make_pair(std::string("buy"), "item:" + std::to_string(sack.ItemId)));

    // Only general bags larger than the one they would replace reach the upgrade check.
    for (uint8 slot = INVENTORY_SLOT_BAG_START; slot < INVENTORY_SLOT_BAG_END; ++slot)
        s.Equip(slot, sack);
    s.context.reads.clear();
    assert(s.Evaluate().type == Type::NONE && !s.context.reads.count("item upgrade"));
    s.Equip(INVENTORY_SLOT_BAG_START, pouch);
    s.context.reads.clear();
    assert(s.Evaluate().type == Type::NONE && s.context.reads["item upgrade"] == 3);
}

int main()
{
    GuardTests();
    SellAndRepairTests();
    TrainerTests();
    SupplyTests();
    AuctionVisitTests();
    AuctionTravelTests();
    StarvationTests();
    CostTests();
    BagTests();
    std::cout << "Natural maintenance: guards, priorities, budgets, bags, auction visits, failed targets and scan costs "
                 "passed\n";
}
'''


def build(directory, parts, name):
    text = prelude
    for key in ('native', 'types', 'classes', 'travel', 'guard', 'helpers', 'smallest', 'value', 'action', 'trigger',
                'usage'):
        text = text.replace('@@' + key.upper() + '@@', parts[key])
    (directory / (name + '.cpp')).write_text(text + tests)
    executable = directory / name
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-missing-field-initializers',
                    *SANITIZER_FLAGS, '-I', str(module / 'Bot'), str(directory / (name + '.cpp')),
                    '-o', str(executable)], check=True)
    return run_fixture([str(executable)])


mutations = [
    ('maintenance during combat', 'guard', '!bot->IsInCombat() && ', ''),
    ('maintenance with a game-client master', 'guard', '!botAI->HasGameClientMaster() && ', ''),
    ('value without the shared guard', 'value', 'if (!CanRunNaturalMaintenance(botAI))', 'if (false)'),
    ('action without the shared guard', 'action', 'if (!CanRunNaturalMaintenance(botAI))', 'if (false)'),
    ('trainer lesson above the spell budget', 'value', 'price <= spellBudget && ', ''),
    ('supply above its budget', 'value', 'if (price <= budget && bot->HasEnoughMoney(price))',
     'if (budget && bot->HasEnoughMoney(price))'),
    ('reagents of passive spells', 'value', '!info || info->IsPassive()', '!info'),
    ('repair before vendor sales', 'value', 'if (canSell && npc->HasNpcFlag(UNIT_NPC_FLAG_VENDOR))',
     'if (canSell && !needsRepair && npc->HasNpcFlag(UNIT_NPC_FLAG_VENDOR))'),
    ('purchase without a budget check at the vendor', 'action',
     'if (price > AI_VALUE2(uint32, "free money for", task.budgetType) || !bot->HasEnoughMoney(price))',
     'if (!bot->HasEnoughMoney(price))'),
    ('visit clock not advanced', 'action', 'info.earnedAuctionLastVisit = getMSTime();', ''),
    ('trip guard does not back off', 'travel', 'ai->rpgInfo.earnedAuctionVisitDelay = TravelBackoffMs;', ''),
    ('unreachable mailbox retried', 'action',
     'EarnedAuctionTravel::PostponeVisit(botAI);\n            value->Set({});',
     'EarnedAuctionTravel::AbortTrip(botAI);\n            value->Set({});'),
    ('rejected visit retried', 'action', 'else\n            EarnedAuctionTravel::PostponeVisit(botAI);',
     'else\n            EarnedAuctionTravel::AbortTrip(botAI);'),
    ('unreachable NPC not remembered', 'action',
     'botAI->rpgInfo.naturalMaintenanceRejected = task.target;\n        value->Set({});', 'value->Set({});'),
    ('failed NPC not remembered', 'action',
     'if (!result)\n        botAI->rpgInfo.naturalMaintenanceRejected = task.target;\n', ''),
    ('rejected NPC chosen again', 'value', 'guid == rejected || ', '(rejected.IsEmpty() && guid.IsEmpty()) || '),
    ('NPC rejected for more than one search', 'value', 'botAI->rpgInfo.naturalMaintenanceRejected.Clear();', ''),
    ('vendor stock scanned without a wanted supply', 'value',
     'if ((!needsSupplies && !needsBag) || !npc->HasNpcFlag(UNIT_NPC_FLAG_VENDOR))',
     'if (!npc->HasNpcFlag(UNIT_NPC_FLAG_VENDOR))'),
    ('usability checked before the supply match', 'value',
     'if (!proto || item->ExtendedCost)\n', 'if (!proto || item->ExtendedCost || bot->CanUseItem(proto) != EQUIP_ERR_OK)\n'),
    ('consumable type for every stock item', 'value',
     '(needsFood || needsDrink) && proto->Class == ITEM_CLASS_CONSUMABLE', 'proto'),
    ('lesson price quoted before teachability', 'value',
     'if (!PlayerbotFactory::IsTrainerSpellAllowedForBot(bot, trainer, &spell) ||',
     ('if (!trainer->GetSpellCost(bot, npc, &spell) ||\n                        '
      '!PlayerbotFactory::IsTrainerSpellAllowedForBot(bot, trainer, &spell) ||')),
    ('vendor surplus evaluated before an auction visit', 'value', '    if (EarnedAuction::IsEnabled(botAI))\n',
     '    if ((AI_VALUE(bool, "can sell") && false) || EarnedAuction::IsEnabled(botAI))\n'),
    ('auctioneer search on every approach tick', 'action',
     '>= 2 * IN_MILLISECONDS', '+ 1 >= 1'),
    ('bag for a character a player owns', 'value', 'sRandomPlayerbotMgr.IsRandomBot(bot) ?', 'true ?'),
    ('bag above the gear budget', 'value', 'price <= gearBudget && ', ''),
    ('bag without enough money', 'value', 'price <= gearBudget && bot->HasEnoughMoney(price) &&',
     'price <= gearBudget &&'),
    ('bag without the upgrade check', 'value',
     ' &&\n                    AI_VALUE2(ItemUsage, "item upgrade", proto->ItemId) == ITEM_USAGE_EQUIP', ''),
    ('limited bag stock ignored', 'value',
     '!(item->maxcount && npc->GetVendorItemCurrentCount(item) < proto->BuyCount) &&\n                    ', ''),
    ('largest bag not preferred', 'value', '(!bag || proto->ContainerSlots > bag->ContainerSlots ||', '(!bag ||'),
    ('cheaper equal bag not preferred', 'value', 'price < bagPrice', 'price > bagPrice'),
    ('special bag displaced', 'helpers', 'if (!IsGeneralBag(smallest->GetTemplate()))\n        return false;', ''),
    ('replacement without a free backpack slot', 'helpers',
     'if (!bot->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))\n            return true;\n    return false;',
     'if (!bot->GetItemByPos(INVENTORY_SLOT_BAG_0, slot))\n            return true;\n    return true;'),
    ('carried bag upgrade ignored', 'value', '!CarriesBagUpgrade(botAI, replaceableBag)',
     '!(CarriesBagUpgrade(botAI, replaceableBag) && false)'),
    ('carried backpack bag ignored', 'helpers', 'slot < INVENTORY_SLOT_ITEM_END; ++slot)',
     'slot < INVENTORY_SLOT_ITEM_START; ++slot)'),
    ('bag inside a bag ignored', 'helpers', 'position < bag->GetBagSize()', 'position < bag->GetBagSize() && false'),
    ('carried bag counted without the upgrade check', 'helpers',
     (' &&\n               botAI->GetAiObjectContext()->GetValue<ItemUsage>("item upgrade", proto->ItemId)->Get() ==\n'
      '                   ITEM_USAGE_EQUIP'), ''),
    ('profession bag sent to the upgrade check', 'value', 'needsBag && IsGeneralBag(proto) && ', 'needsBag && '),
    ('smaller bag sent to the upgrade check', 'value', 'proto->ContainerSlots > replaceableBag',
     'proto->ContainerSlots + 1 > replaceableBag'),
]

with tempfile.TemporaryDirectory(prefix='portable-natural-maintenance-') as temporary:
    temporary = Path(temporary)
    result = build(temporary, production, 'maintenance')
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit(f'Natural maintenance fixture failed (exit {result.returncode})')

    def rejected(numbered):
        index, (label, key, old, new) = numbered
        mutated = {**production, key: production[key].replace(old, new)}
        if mutated[key] == production[key]:
            raise SystemExit(f'{label} mutation was not applied')
        return build(temporary, mutated, f'mutant-{index}').returncode != 0

    for (label, *_), result in zip(mutations, in_parallel(rejected, enumerate(mutations))):
        if not result:
            raise SystemExit(f'Natural maintenance fixture did not reject: {label}')
        print(f'Natural maintenance mutation rejected: {label}')
