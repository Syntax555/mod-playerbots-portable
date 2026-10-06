"""Run earned-auction production policy and service against isolated core fixtures.

The fake core handlers model authoritative inventory, gold and mail outcomes,
including rejected operations. They do not implement the service's decisions.
The actual module translation unit supplies those decisions under ASan/UBSan.
This does not start a realm or replace the full core/module compile check.
"""

from pathlib import Path
import argparse
import subprocess
import tempfile


repo = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path,
                    default=repo / 'azerothcore-wotlk/modules/mod-playerbots/src',
                    help='prepared Playerbots src directory')
parser.add_argument('--travel-source', type=Path,
                    help='optional separate src directory for the market-travel policy')
args = parser.parse_args()
module = args.source / 'Bot'
travel_module = (args.travel_source or args.source) / 'Bot'


policy_tests = r'''
void PolicyTests()
{
    using namespace EarnedAuction;
    assert(UnitPriceCeiling(100, 20) == 120);
    assert(UnitPriceCeiling(1000, 20) == 1000);
    assert(UnitPriceCeiling(0, 0) == 0);
    assert(UnitPriceCeiling(UINT32_MAX, UINT32_MAX) == MaxCopper);

    auto ordinary = PriceListing(100, 20, 5, 0);
    assert(ordinary.bid == 240 && ordinary.buyout == 300);
    auto undercut = PriceListing(100, 20, 5, 100);
    assert(undercut.bid == 396 && undercut.buyout == 495);
    auto lowMarket = PriceListing(100, 20, 5, 1);
    assert(lowMarket.bid == 160 && lowMarket.buyout == 200);
    auto highMarket = PriceListing(100, 20, 5, UINT32_MAX);
    assert(highMarket.bid == 480 && highMarket.buyout == 600);
    assert(!PriceListing(100, 0, 5, 50).buyout);
    assert(!PriceListing(100, 20, 0, 50).buyout);
    assert(!PriceListing(UINT32_MAX, UINT32_MAX, 1, 50).buyout);
    assert(!PriceListing(100, 20, UINT32_MAX, 50).buyout);
    for (std::uint32_t count : {1u, 2u, 20u, 1000u, UINT32_MAX})
        for (std::uint32_t sell : {0u, 1u, 200u, MaxCopper / 2, MaxCopper, UINT32_MAX})
            for (std::uint32_t market : {0u, 1u, 500u, UINT32_MAX})
            {
                auto prices = PriceListing(UINT32_MAX, sell, count, market);
                if (prices.buyout)
                {
                    assert(prices.bid && prices.bid <= prices.buyout);
                    assert(prices.buyout <= MaxCopper);
                    assert(std::uint64_t(prices.buyout) > std::uint64_t(sell) * count);
                    assert(WithinPriceCeiling(prices.buyout, count, UnitPriceCeiling(UINT32_MAX, sell)));
                }
                else
                    assert(!prices.bid);
            }

    assert(Affordable(100, 100, 100));
    assert(!Affordable(0, 100, 100));
    assert(!Affordable(101, 100, 1000));
    assert(!Affordable(101, 1000, 100));
    assert(!Affordable(UINT32_MAX, UINT32_MAX, UINT32_MAX));
    assert(WithinPriceCeiling(200, 2, 100));
    assert(!WithinPriceCeiling(201, 2, 100));
    assert(!WithinPriceCeiling(1, 0, 100));
    assert(!WithinPriceCeiling(1, 1, 0));
    assert(!WithinPriceCeiling(UINT32_MAX, UINT32_MAX, UINT32_MAX));
    assert(WithinPriceCeiling(MaxCopper, UINT32_MAX, UINT32_MAX));

    assert(ReceiptReady(true, false, 0, 100, 200, 100));
    assert(!ReceiptReady(false, false, 0, 100, 200, 100));
    assert(!ReceiptReady(true, true, 0, 100, 200, 100));
    assert(!ReceiptReady(true, false, 1, 100, 200, 100));
    assert(!ReceiptReady(true, false, 0, 101, 200, 100));
    assert(!ReceiptReady(true, false, 0, 0, 100, 100));
}
'''

fixtures = r'''
#include "EarnedAuctionPolicy.h"
#include "EarnedAuctionTravelPolicy.h"
#include <array>
#include <cassert>
#include <chrono>
#include <cmath>
#include <iostream>
#include <map>
#include <memory>
#include <string>
#include <type_traits>
#include <unordered_set>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
constexpr uint32 MINUTE = 60, MIN_AUCTION_TIME = 43200;
constexpr uint8 INVENTORY_SLOT_BAG_0 = 0, INVENTORY_SLOT_BAG_START = 19,
    INVENTORY_SLOT_BAG_END = 23, INVENTORY_SLOT_ITEM_START = 23, INVENTORY_SLOT_ITEM_END = 39;
constexpr int ITEM_FIELD_DURATION = 1, ITEM_QUALITY_NORMAL = 1, ITEM_CLASS_CONSUMABLE = 0,
    ITEM_CLASS_QUEST = 12, ITEM_CLASS_KEY = 13, ITEM_FLAG_CONJURED = 2, BIND_QUEST_ITEM = 4,
    PLAYERSPELL_REMOVED = 1, MAX_SPELL_REAGENTS = 8, NULL_BAG = 255, NULL_SLOT = 255,
    EQUIP_ERR_OK = 0, GAMEOBJECT_TYPE_MAILBOX = 1, UNIT_NPC_FLAG_MAILBOX = 2,
    UNIT_NPC_FLAG_AUCTIONEER = 4, MAIL_AUCTION = 2, MAIL_STATE_DELETED = 3,
    MAX_QUEST_LOG_SIZE = 25, SPELL_EFFECT_CREATE_ITEM = 24;
constexpr int CMSG_GET_MAIL_LIST = 1, CMSG_MAIL_TAKE_MONEY = 2, CMSG_MAIL_TAKE_ITEM = 3,
    CMSG_MAIL_DELETE = 4, CMSG_AUCTION_SELL_ITEM = 5, CMSG_AUCTION_PLACE_BID = 6;
constexpr float INTERACTION_DISTANCE = 5;
enum ItemUsage { ITEM_USAGE_NONE, ITEM_USAGE_AH, ITEM_USAGE_EQUIP, ITEM_USAGE_REPLACE,
    ITEM_USAGE_AMMO, ITEM_USAGE_SKILL, ITEM_USAGE_USE, ITEM_USAGE_QUEST, ITEM_USAGE_KEEP, ITEM_USAGE_VENDOR };
enum class NeedMoneyFor : uint32 { gear, ammo, consumables, tradeskill, anything };
struct ObjectGuid
{
    uint32 value = 0;
    uint32 GetCounter() const { return value; }
    bool IsGameObject() const { return value >= 200000; }
    bool IsAnyTypeCreature() const { return value >= 100000 && value < 200000; }
    explicit operator bool() const { return value != 0; }
    auto operator<=>(ObjectGuid const&) const = default;
};
struct WorldObject { virtual ~WorldObject() = default; ObjectGuid guid; };
struct Creature : WorldObject
{
    uint32 GetFaction() const { return 1; }
    ObjectGuid GetGUID() const { return guid; }
};
struct GameObject : WorldObject {};
struct ItemTemplate
{
    struct Spell { int SpellId = 0; };
    std::array<Spell, 5> Spells{};
    uint32 ItemId = 100, BuyPrice = 1000, SellPrice = 100, Quality = 1, Class = 1, Bonding = 0;
    bool conjured = false, petFood = false;
    bool HasFlag(int) const { return conjured; }
};
struct Item
{
    virtual ~Item() = default;
    ItemTemplate proto;
    ObjectGuid guid, owner;
    uint32 count = 1, duration = 0;
    std::int32_t property = 0;
    bool equipped = false, inTrade = false, tradable = true, nonempty = false, bound = false;
    ObjectGuid GetGUID() const { return guid; }
    ObjectGuid GetOwnerGUID() const { return owner; }
    uint32 GetEntry() const { return proto.ItemId; }
    uint32 GetCount() const { return count; }
    std::int32_t GetItemRandomPropertyId() const { return property; }
    ItemTemplate const* GetTemplate() const { return &proto; }
    bool IsEquipped() const { return equipped; }
    bool IsInTrade() const { return inTrade; }
    bool CanBeTraded() const { return tradable; }
    bool IsNotEmptyBag() const { return nonempty; }
    bool IsSoulBound() const { return bound; }
    uint32 GetUInt32Value(int) const { return duration; }
};
std::map<ObjectGuid, std::unique_ptr<Item>> allocatedItems;
struct Bag : Item
{
    std::vector<Item*> items;
    uint32 GetBagSize() const { return items.size(); }
    Item* GetItemByPos(uint32 position) const { return items.at(position); }
};
struct Pet { bool HaveInDiet(ItemTemplate const* item) const { return item->petFood; } };
struct PlayerSpell { int State = 0; bool Active = true; };
struct SpellInfo
{
    struct EffectInfo { int Effect = 0; uint32 ItemType = 0; };
    std::array<EffectInfo, 3> Effects{};
    std::array<int, MAX_SPELL_REAGENTS> Reagent{};
    bool passive = false;
    bool IsPassive() const { return passive; }
};
struct SpellMgr
{
    std::map<uint32, SpellInfo> spells;
    SpellInfo const* GetSpellInfo(uint32 id) const
    { auto it = spells.find(id); return it == spells.end() ? nullptr : &it->second; }
} spellMgr;
auto* sSpellMgr = &spellMgr;
struct Quest
{
    std::array<uint32, 6> RequiredItemId{}, ItemDrop{};
    uint32 source = 0;
    uint32 GetSrcItemId() const { return source; }
};
struct ObjectMgr
{
    std::map<uint32, Quest> quests;
    Quest const* GetQuestTemplate(uint32 id) const
    { auto it = quests.find(id); return it == quests.end() ? nullptr : &it->second; }
} objectMgr;
auto* sObjectMgr = &objectMgr;
template<class T> struct Value { T value{}; void Reset() {} T Get() const { return value; } };
struct AiObjectContext
{
    Value<bool> canMove{true}; Value<uint8> bagSpace{0}; Value<uint32> budget{10000}, supplies{0};
    std::map<std::string, Value<ItemUsage>> usage;
    std::string lastQualifier;
    template<class T, class Q = std::string> Value<T>* GetValue(std::string const& name, Q qualifier = {})
    {
        if constexpr (std::is_same_v<T, bool>) return &canMove;
        else if constexpr (std::is_same_v<T, uint8>) return &bagSpace;
        else if constexpr (std::is_same_v<T, uint32>) return name == "money needed for" ? &supplies : &budget;
        else { lastQualifier = qualifier; return &usage[qualifier]; }
    }
};
struct Player;
struct PlayerbotAI
{
    Player* bot = nullptr; AiObjectContext context; bool master = false;
    Player* GetBot() const { return bot; }
    AiObjectContext* GetAiObjectContext() { return &context; }
    bool HasGameClientMaster() const { return master; }
};
struct MailItemInfo { uint32 item_guid; };
struct Mail
{
    uint32 messageID = 0, money = 0, COD = 0;
    int messageType = MAIL_AUCTION, state = 0;
    std::int64_t deliver_time = 1000, expire_time = 100000;
    std::vector<MailItemInfo> items;
};
using ItemPosCountVec = std::vector<uint32>;
struct WorldPacket
{
    int opcode; std::vector<std::uint64_t> data;
    explicit WorldPacket(int op) : opcode(op) {}
    WorldPacket& operator<<(ObjectGuid value) { data.push_back(value.value); return *this; }
    WorldPacket& operator<<(uint32 value) { data.push_back(value); return *this; }
};
enum class AuctionHouseId { Alliance, Horde, Neutral };
struct AuctionHouseEntry {};
struct AuctionEntry
{
    uint32 Id = 0, item_template = 0, itemCount = 0, buyout = 0, bid = 0;
    ObjectGuid item_guid, owner, bidder;
    std::int64_t expire_time = 100000;
};
struct AuctionHouseObject
{
    std::map<uint32, AuctionEntry*> auctions;
    auto const& GetAuctions() const { return auctions; }
    AuctionEntry* GetAuction(uint32 id) const
    { auto it = auctions.find(id); return it == auctions.end() ? nullptr : it->second; }
};
constexpr int RATE_AUCTION_DEPOSIT = 1;
struct World { float rate = 1; float getRate(int) const { return rate; } } world;
auto* sWorld = &world;
struct AuctionHouseMgr
{
    AuctionHouseObject house;
    std::map<ObjectGuid, Item*> items;
    static AuctionHouseEntry const* GetAuctionHouseEntryFromFactionTemplate(uint32)
    { static AuctionHouseEntry entry; return &entry; }
    AuctionHouseObject* GetAuctionsMap(uint32) { return &house; }
    AuctionHouseObject* GetAuctionsMapByHouseId(AuctionHouseId) { return &house; }
    Item* GetAItem(ObjectGuid guid) const
    { auto it = items.find(guid); return it == items.end() ? nullptr : it->second; }
    uint32 GetAuctionDeposit(AuctionHouseEntry const*, uint32 duration, Item* item, uint32 count) const
    { assert(duration == MIN_AUCTION_TIME);
      return uint32(std::max(100.0f, item->proto.SellPrice * count * 0.15f) * world.rate); }
} auctionMgr;
auto* sAuctionMgr = &auctionMgr;
struct CharacterCache
{
    std::map<ObjectGuid, uint32> accounts;
    uint32 GetCharacterAccountIdByGuid(ObjectGuid guid) { return accounts[guid]; }
} characterCache;
auto* sCharacterCache = &characterCache;
struct WorldSession
{
    Player* bot = nullptr; uint32 account = 1;
    bool rejectSell = false, rejectBuy = false, rejectMoney = false, rejectItem = false, mergeItem = false;
    int inboxes = 0, sells = 0, buys = 0, takesMoney = 0, takesItem = 0, deletes = 0;
    uint32 lastCount = 0, lastPrice = 0, lastAuction = 0, depositPaid = 0;
    ObjectGuid lastItem;
    uint32 GetAccountId() const { return account; }
    void HandleGetMailList(WorldPacket&);
    void HandleMailTakeMoney(WorldPacket&);
    void HandleMailTakeItem(WorldPacket&);
    void HandleMailDelete(WorldPacket&);
    void HandleAuctionSellItem(WorldPacket&);
    void HandleAuctionPlaceBid(WorldPacket&);
};
struct Player
{
    ObjectGuid guid;
    WorldSession session; PlayerbotAI ai;
    uint32 money = 10000;
    bool online = true, alive = true, combat = false, flight = false, teleport = false,
        battleground = false, trade = false, range = true, store = true, usable = true, random = true;
    std::map<uint32, Item*> backpack;
    std::map<ObjectGuid, Item*> inventory;
    std::vector<Mail*> mails;
    std::map<uint32, Item*> attachments;
    std::map<uint32, PlayerSpell*> spells;
    std::array<uint32, MAX_QUEST_LOG_SIZE> quests{};
    Creature auctioneer, creatureMailbox; GameObject mailbox; Pet* pet = nullptr;
    Player() { session.bot = this; ai.bot = this; auctioneer.guid = {100001};
        creatureMailbox.guid = {100002}; mailbox.guid = {200001}; }
    ObjectGuid GetGUID() const { return guid; }
    WorldSession* GetSession() { return &session; }
    uint32 GetMoney() const { return money; }
    bool HasEnoughMoney(uint32 price) const { return price <= money; }
    Item* GetItemByPos(uint8, uint8 slot) const
    { auto it = backpack.find(slot); return it == backpack.end() ? nullptr : it->second; }
    Item* GetItemByGuid(ObjectGuid id) const
    { auto it = inventory.find(id); return it == inventory.end() ? nullptr : it->second; }
    uint32 GetItemCount(uint32 entry, bool) const
    { uint32 count = 0; for (auto const& [id, item] : inventory) if (item->GetEntry() == entry) count += item->count; return count; }
    Pet* GetPet() const { return pet; }
    auto const& GetSpellMap() const { return spells; }
    uint32 GetQuestSlotQuestId(uint8 slot) const { return quests.at(slot); }
    bool IsInWorld() const { return online; } bool IsAlive() const { return alive; }
    bool IsInCombat() const { return combat; } bool IsInFlight() const { return flight; }
    bool IsBeingTeleported() const { return teleport; } bool InBattleground() const { return battleground; }
    void* GetTradeData() const { return trade ? const_cast<Player*>(this) : nullptr; }
    auto const& GetMails() const { return mails; }
    Mail* GetMail(uint32 id) const { for (Mail* mail : mails) if (mail->messageID == id) return mail; return nullptr; }
    Item* GetMItem(uint32 id) const
    { auto it = attachments.find(id); return it == attachments.end() ? nullptr : it->second; }
    int CanStoreItem(int, int, ItemPosCountVec&, Item*, bool) const { return store ? EQUIP_ERR_OK : 1; }
    int CanUseItem(ItemTemplate const*) const { return usable ? EQUIP_ERR_OK : 1; }
    GameObject* GetGameObjectIfCanInteractWith(ObjectGuid id, int)
    { return range && id == mailbox.guid ? &mailbox : nullptr; }
    Creature* GetNPCIfCanInteractWith(ObjectGuid id, int flag)
    { if (!range) return nullptr; return flag == UNIT_NPC_FLAG_AUCTIONEER && id == auctioneer.guid ? &auctioneer :
        flag == UNIT_NPC_FLAG_MAILBOX && id == creatureMailbox.guid ? &creatureMailbox : nullptr; }
    bool IsWithinDistInMap(WorldObject*, float) const { return range; }
};
struct Config { bool naturalProgression = true, earnedAuctions = true; uint32 earnedAuctionInterval = 300; }
    sPlayerbotAIConfig;
struct RandomMgr { bool IsRandomBot(Player* bot) const { return bot->random; } } sRandomPlayerbotMgr;
#define GET_PLAYERBOT_AI(bot) (&(bot)->ai)
std::map<ObjectGuid, Player*> connected;
namespace ObjectAccessor
{
Player* FindConnectedPlayer(ObjectGuid id)
{ auto it = connected.find(id); return it == connected.end() ? nullptr : it->second; }
}
std::int64_t now = 1000;
namespace GameTime { std::chrono::seconds GetGameTime() { return std::chrono::seconds(now); } }
struct PlayerbotOperation
{
    virtual ~PlayerbotOperation() = default;
    virtual ObjectGuid GetBotGuid() const = 0;
    virtual std::string GetName() const = 0;
    virtual bool Execute() = 0;
};
struct PlayerbotWorldThreadProcessor
{
    bool accept = true; std::vector<std::unique_ptr<PlayerbotOperation>> queued;
    static PlayerbotWorldThreadProcessor& instance() { static PlayerbotWorldThreadProcessor processor; return processor; }
    bool QueueOperation(std::unique_ptr<PlayerbotOperation> operation)
    { if (!accept) return false; queued.push_back(std::move(operation)); return true; }
};
// These are outcome fixtures for the core's authoritative handlers. Service
// decisions cannot alter inventory/gold/mail unless they use one of these APIs.
void WorldSession::HandleGetMailList(WorldPacket& packet)
{ assert(packet.data.size() == 1); ++inboxes; }
void WorldSession::HandleMailTakeMoney(WorldPacket& packet)
{
    ++takesMoney; Mail* mail = bot->GetMail(packet.data.at(1));
    if (rejectMoney || !mail || std::uint64_t(bot->money) + mail->money > EarnedAuction::MaxCopper) return;
    bot->money += mail->money; mail->money = 0;
}
void WorldSession::HandleMailTakeItem(WorldPacket& packet)
{
    ++takesItem; Mail* mail = bot->GetMail(packet.data.at(1)); uint32 id = packet.data.at(2);
    Item* item = bot->GetMItem(id); if (rejectItem || !bot->store || !mail || !item) return;
    bot->attachments.erase(id);
    std::erase_if(mail->items, [id](auto const& info) { return info.item_guid == id; });
    if (mergeItem)
    {
        for (auto const& [guid, stack] : bot->inventory)
            if (stack->GetEntry() == item->GetEntry()) { stack->count += item->count; break; }
        allocatedItems.erase(item->guid); return; // Real core stack merging can free the attachment.
    }
    item->owner = bot->guid; bot->inventory[item->guid] = item;
}
void WorldSession::HandleMailDelete(WorldPacket& packet)
{
    ++deletes; Mail* mail = bot->GetMail(packet.data.at(1)); assert(mail && !mail->COD);
    // The real core can delete attachments. Assert the service never asks it to.
    assert(mail->items.empty() && !mail->money); mail->state = MAIL_STATE_DELETED;
}
void WorldSession::HandleAuctionSellItem(WorldPacket& packet)
{
    ++sells; assert(packet.data.size() == 7 && packet.data[1] == 1 && packet.data[6] == 720);
    lastItem = {uint32(packet.data[2])}; lastCount = packet.data[3]; lastPrice = packet.data[5];
    Item* item = bot->GetItemByGuid(lastItem); assert(item && lastCount == item->count);
    if (rejectSell) return;
    depositPaid = auctionMgr.GetAuctionDeposit(nullptr, MIN_AUCTION_TIME, item, item->count);
    assert(bot->money >= depositPaid); bot->money -= depositPaid;
    bot->inventory.erase(lastItem);
    std::erase_if(bot->backpack, [this](auto const& pair) { return pair.second->guid == lastItem; });
    auctionMgr.items[lastItem] = item;
}
void WorldSession::HandleAuctionPlaceBid(WorldPacket& packet)
{
    ++buys; lastAuction = packet.data.at(1); lastPrice = packet.data.at(2);
    AuctionEntry* offer = auctionMgr.house.GetAuction(lastAuction); assert(offer && offer->buyout == lastPrice);
    if (rejectBuy) return;
    assert(bot->money >= lastPrice); bot->money -= lastPrice; auctionMgr.house.auctions.erase(lastAuction);
}
namespace EarnedAuction
{
bool IsEnabled(PlayerbotAI*); bool HasSurplus(PlayerbotAI*);
bool HasVendorSurplus(PlayerbotAI*);
bool ShouldReserveForAuction(PlayerbotAI*, Item*, ItemUsage); bool QueueVisit(PlayerbotAI*, ObjectGuid, bool);
}
'''

service_tests = r'''
void TravelTests()
{
    using namespace EarnedAuctionTravel;
    assert(!CanStartTravel(9, true, UINT32_MAX));
    assert(!CanStartTravel(10, false, 99));
    assert(CanStartTravel(10, false, 100));
    assert(CanStartTravel(10, true, 0));
    assert(CompatibleHouse(1, 1) && CompatibleHouse(6, 6));
    assert(CompatibleHouse(1, 7) && CompatibleHouse(6, 7));
    assert(!CompatibleHouse(1, 6) && !CompatibleHouse(0, 7) && !CompatibleHouse(1, 0));
    MarketOrigin origin{0, 1, 1, 0, 0, 0};
    std::array<MarketSite, 7> markets{{
        {0, 1, 1, 11, 150, 0, 0, 0},
        {0, 1, 6, 11, 1, 0, 0, 0},
        {1, 1, 1, 11, 2, 0, 0, 0},
        {0, 2, 1, 11, 3, 0, 0, 0},
        {0, 1, 7, 11, 100, 0, 0, 0},
        {0, 1, 1, 99, 50, 0, 0, 0},
        {0, 1, 1, 11, 6000, 0, 0, 0},
    }};
    unsigned friendlyChecks = 0;
    auto nearest = NearestMarketIndex(markets, origin, [&friendlyChecks](MarketSite const& site)
    { ++friendlyChecks; return site.factionTemplateId == 11; });
    assert(nearest && *nearest == 4 && friendlyChecks == 3);
    assert(!NearestMarketIndex(markets, origin, [](MarketSite const&) { return false; }));
    assert(!NearestMarketIndex(std::span<MarketSite const>{}, origin, [](MarketSite const&) { return true; }));
    MarketSite boundary{0, 1, 1, 11, MaximumTravelDistance, 0, 0, 0};
    assert(EligibleMarket(origin, boundary)); boundary.x += 1; assert(!EligibleMarket(origin, boundary));
    boundary.x = 0; boundary.z = MaximumTravelDistance; assert(EligibleMarket(origin, boundary));
    boundary.z += 1; assert(!EligibleMarket(origin, boundary));
    boundary.z = 0; boundary.x = std::numeric_limits<float>::infinity(); assert(!EligibleMarket(origin, boundary));
    boundary.x = std::numeric_limits<float>::quiet_NaN(); assert(!EligibleMarket(origin, boundary));
    boundary.x = 0; boundary.phaseMask = 0; assert(!EligibleMarket(origin, boundary));
    boundary.phaseMask = 2; origin.phaseMask = 3; assert(EligibleMarket(origin, boundary));
    assert(!TravelDeadlineReached(MaximumTravelTimeMs - 1));
    assert(TravelDeadlineReached(MaximumTravelTimeMs));
    assert(!TravelBackoffElapsed(TravelBackoffMs - 1));
    assert(TravelBackoffElapsed(TravelBackoffMs));
}
struct Scenario
{
    Player bot;
    std::vector<ObjectGuid> items;
    std::vector<std::unique_ptr<Mail>> mails;
    std::vector<std::unique_ptr<AuctionEntry>> offers;
    Scenario()
    {
        static uint32 nextBot = 1;
        bot.guid = {nextBot++}; connected.clear(); connected[bot.guid] = &bot;
        auctionMgr.house.auctions.clear(); auctionMgr.items.clear(); characterCache.accounts.clear();
        allocatedItems.clear(); objectMgr.quests.clear(); spellMgr.spells.clear();
        sPlayerbotAIConfig = {}; world.rate = 1; now += 400;
        auto& processor = PlayerbotWorldThreadProcessor::instance(); processor.queued.clear(); processor.accept = true;
    }
    Item& MakeItem(uint32 entry = 100, uint32 count = 1, ItemUsage usage = ITEM_USAGE_AH)
    {
        auto item = std::make_unique<Item>(); item->guid = {uint32(items.size() + 1000)};
        item->owner = bot.guid; item->proto.ItemId = entry; item->count = count;
        Item& result = *item; items.push_back(item->guid); allocatedItems[result.guid] = std::move(item);
        SetUsage(result, usage); return result;
    }
    Item& BagItem(uint32 entry = 100, uint32 count = 1, ItemUsage usage = ITEM_USAGE_AH)
    {
        Item& item = MakeItem(entry, count, usage); bot.inventory[item.guid] = &item;
        bot.backpack[INVENTORY_SLOT_ITEM_START + bot.backpack.size()] = &item; return item;
    }
    void SetUsage(Item const& item, ItemUsage usage)
    {
        bot.ai.context.usage[std::to_string(item.GetEntry()) + "," +
                             std::to_string(item.GetItemRandomPropertyId())].value = usage;
    }
    AuctionEntry& Offer(Item& item, uint32 id = 1, uint32 price = 500, uint32 owner = 555, uint32 account = 2)
    {
        auto offer = std::make_unique<AuctionEntry>(); offer->Id = id; offer->item_template = item.GetEntry();
        offer->itemCount = item.count; offer->item_guid = item.guid; offer->buyout = price; offer->owner = {owner};
        offer->expire_time = now + 1000; AuctionEntry& result = *offer; offers.push_back(std::move(offer));
        auctionMgr.house.auctions[id] = &result; auctionMgr.items[item.guid] = &item;
        characterCache.accounts[result.owner] = account; return result;
    }
    Mail& Receipt(Item* item = nullptr, uint32 money = 0)
    {
        auto mail = std::make_unique<Mail>(); mail->messageID = uint32(mails.size() + 1); mail->money = money;
        mail->deliver_time = now; mail->expire_time = now + 1000;
        if (item) { mail->items.push_back({item->guid.value}); bot.attachments[item->guid.value] = item; }
        Mail& result = *mail; mails.push_back(std::move(mail)); bot.mails.push_back(&result); return result;
    }
    bool Visit(bool mailbox = false)
    {
        auto& processor = PlayerbotWorldThreadProcessor::instance();
        assert(EarnedAuction::QueueVisit(&bot.ai, mailbox ? bot.mailbox.guid : bot.auctioneer.guid, mailbox));
        assert(processor.queued.size() == 1); auto operation = std::move(processor.queued.back());
        processor.queued.clear(); return operation->Execute();
    }
};

void ServiceTests()
{
    using namespace EarnedAuction;
    {
        Scenario s; assert(IsEnabled(&s.bot.ai)); assert(!IsEnabled(nullptr));
        s.bot.ai.master = true; assert(!IsEnabled(&s.bot.ai)); s.bot.ai.master = false;
        s.bot.random = false; assert(!IsEnabled(&s.bot.ai)); s.bot.random = true;
        sPlayerbotAIConfig.naturalProgression = false; assert(!IsEnabled(&s.bot.ai));
        assert(!QueueVisit(&s.bot.ai, s.bot.auctioneer.guid, false));
    }
    {
        Scenario s; auto& processor = PlayerbotWorldThreadProcessor::instance(); processor.accept = false;
        assert(!QueueVisit(&s.bot.ai, s.bot.auctioneer.guid, false)); assert(processor.queued.empty());
        processor.accept = true; assert(!QueueVisit(&s.bot.ai, {}, false));
    }
    {
        Scenario s; assert(QueueVisit(&s.bot.ai, {100003}, false));
        auto& processor = PlayerbotWorldThreadProcessor::instance();
        assert(!processor.queued.front()->Execute()); assert(!s.bot.session.sells && !s.bot.session.buys);
    }
    for (int rejection = 0; rejection < 11; ++rejection)
    {
        Scenario s; s.BagItem();
        assert(QueueVisit(&s.bot.ai, s.bot.auctioneer.guid, false));
        auto& processor = PlayerbotWorldThreadProcessor::instance(); auto operation = std::move(processor.queued.back());
        processor.queued.clear();
        switch (rejection)
        {
            case 0: connected.clear(); break;
            case 1: s.bot.alive = false; break;
            case 2: s.bot.combat = true; break;
            case 3: s.bot.flight = true; break;
            case 4: s.bot.teleport = true; break;
            case 5: s.bot.battleground = true; break;
            case 6: s.bot.trade = true; break;
            case 7: s.bot.range = false; break;
            case 8: s.bot.ai.master = true; break;
            case 9: s.bot.ai.context.canMove.value = false; break;
            case 10: sPlayerbotAIConfig.naturalProgression = false; break;
        }
        assert(!operation->Execute()); assert(!s.bot.session.sells && !s.bot.session.buys);
        assert(s.bot.money == 10000 && s.bot.inventory.size() == 1);
    }
    for (int rejection = 0; rejection < 12; ++rejection)
    {
        Scenario s; Item& item = s.BagItem();
        switch (rejection)
        {
            case 0: item.equipped = true; break;
            case 1: item.inTrade = true; break;
            case 2: item.tradable = false; break;
            case 3: item.nonempty = true; break;
            case 4: item.bound = true; break;
            case 5: item.owner = {999}; break;
            case 6: item.count = 0; break;
            case 7: item.duration = 5; break;
            case 8: item.proto.Class = ITEM_CLASS_QUEST; break;
            case 9: item.proto.Class = ITEM_CLASS_KEY; break;
            case 10: item.proto.conjured = true; break;
            case 11: item.proto.Bonding = BIND_QUEST_ITEM; break;
        }
        assert(!HasSurplus(&s.bot.ai));
        assert(ShouldReserveForAuction(&s.bot.ai, &item, ITEM_USAGE_AH) ==
               (rejection == 8 || rejection == 9 || rejection == 11));
        assert(!s.Visit()); assert(!s.bot.session.sells && s.bot.inventory.size() == 1 && s.bot.money == 10000);
    }
    {
        Scenario s; Item& item = s.BagItem(100, 5); assert(HasSurplus(&s.bot.ai));
        assert(ShouldReserveForAuction(&s.bot.ai, &item, ITEM_USAGE_AH));
        assert(!HasVendorSurplus(&s.bot.ai)); // Saved AH stock must not create endless vendor visits.
        s.bot.ai.context.bagSpace.value = 80; assert(!ShouldReserveForAuction(&s.bot.ai, &item, ITEM_USAGE_AH));
        assert(HasVendorSurplus(&s.bot.ai));
        s.bot.ai.context.bagSpace.value = 0; s.bot.ai.context.budget.value = 99;
        assert(!ShouldReserveForAuction(&s.bot.ai, &item, ITEM_USAGE_AH)); s.bot.ai.context.budget.value = 10000;
        assert(s.Visit()); assert(s.bot.session.sells == 1 && s.bot.session.lastItem == item.guid);
        assert(s.bot.session.lastCount == 5 && s.bot.session.depositPaid == 100 && s.bot.money == 9900);
        assert(s.bot.inventory.empty() && auctionMgr.GetAItem(item.guid) == &item && item.count == 5);
        assert(!s.Visit()); assert(s.bot.session.sells == 1); // same-visit cooldown
    }
    {
        Scenario s; Item& item = s.BagItem(100, 1, ITEM_USAGE_VENDOR); assert(HasVendorSurplus(&s.bot.ai));
        s.bot.quests[0] = 5; objectMgr.quests[5].RequiredItemId[0] = item.GetEntry();
        assert(!HasVendorSurplus(&s.bot.ai));
    }
    {
        Scenario s; Item& item = s.MakeItem(100, 1, ITEM_USAGE_EQUIP); item.property = -123;
        s.SetUsage(item, ITEM_USAGE_REPLACE); assert(Usage(&s.bot.ai, &item) == ITEM_USAGE_REPLACE);
        assert(s.bot.ai.context.lastQualifier == "100,-123");
    }
    {
        Scenario s; Item& item = s.BagItem(); item.property = -123; s.SetUsage(item, ITEM_USAGE_AH);
        Item& wrongProperty = s.MakeItem(); wrongProperty.property = -124; s.SetUsage(wrongProperty, ITEM_USAGE_AH);
        s.Offer(wrongProperty, 1, 1);
        Item& sameProperty = s.MakeItem(); sameProperty.property = -123; s.SetUsage(sameProperty, ITEM_USAGE_AH);
        s.Offer(sameProperty, 2, 400);
        assert(s.Visit()); assert(s.bot.session.lastPrice == 399 && item.property == -123);
    }
    {
        Scenario s; Item& item = s.BagItem(100, 5); s.bot.session.rejectSell = true;
        assert(!s.Visit()); assert(s.bot.session.sells == 1 && s.bot.money == 10000);
        assert(s.bot.GetItemByGuid(item.guid) == &item && item.count == 5 && auctionMgr.items.empty());
    }
    {
        Scenario s; s.BagItem(100, 5); s.bot.ai.context.budget.value = 49;
        assert(!s.Visit()); assert(!s.bot.session.sells && s.bot.money == 10000 && s.bot.inventory.size() == 1);
    }
    {
        Scenario s; for (uint32 id = 100; id < 105; ++id) s.BagItem(id);
        assert(s.Visit()); assert(s.bot.session.sells == int(MaxSalesPerVisit));
        assert(s.bot.inventory.size() == 3 && s.bot.money == 9800);
    }
    {
        Scenario s; Item& item = s.BagItem(); PlayerSpell spell; s.bot.spells[99] = &spell;
        spellMgr.spells[99].Reagent[0] = int(item.GetEntry()); assert(!HasSurplus(&s.bot.ai));
        spell.State = PLAYERSPELL_REMOVED; assert(HasSurplus(&s.bot.ai));
        s.bot.spells.clear(); Pet pet; item.proto.petFood = true; s.bot.pet = &pet; assert(!HasSurplus(&s.bot.ai));
    }
    for (int retained = 0; retained < 4; ++retained)
    {
        Scenario s; Item& item = s.BagItem(100, 20); s.bot.quests[0] = 5;
        Quest& quest = objectMgr.quests[5];
        if (retained == 0) quest.RequiredItemId[0] = item.GetEntry();
        if (retained == 1) quest.source = item.GetEntry();
        if (retained == 2) quest.ItemDrop[0] = item.GetEntry();
        if (retained == 3)
        {
            quest.RequiredItemId[0] = 200; item.proto.Spells[0].SpellId = 6;
            spellMgr.spells[6].Effects[0] = {SPELL_EFFECT_CREATE_ITEM, 200};
        }
        assert(!HasSurplus(&s.bot.ai)); assert(ShouldReserveForAuction(&s.bot.ai, &item, ITEM_USAGE_AH));
        assert(!HasVendorSurplus(&s.bot.ai));
        sPlayerbotAIConfig.earnedAuctions = false; s.bot.money = 0; s.bot.ai.context.bagSpace.value = 95;
        assert(ShouldReserveForAuction(&s.bot.ai, &item, ITEM_USAGE_AH));
        sPlayerbotAIConfig.earnedAuctions = true;
        assert(!s.Visit()); assert(!s.bot.session.sells && item.count == 20);
    }
    {
        Scenario s; Item& item = s.BagItem(100, 20); s.bot.ai.context.budget.value = 1000;
        assert(!ShouldReserveForAuction(&s.bot.ai, &item, ITEM_USAGE_AH));
        s.bot.ai.context.budget.value = 10000; world.rate = 100;
        assert(!ShouldReserveForAuction(&s.bot.ai, &item, ITEM_USAGE_AH));
        world.rate = std::numeric_limits<float>::infinity();
        assert(!ShouldReserveForAuction(&s.bot.ai, &item, ITEM_USAGE_AH));
        world.rate = -1; assert(!ShouldReserveForAuction(&s.bot.ai, &item, ITEM_USAGE_AH));
        world.rate = 1; item.proto.SellPrice = UINT32_MAX;
        assert(!ShouldReserveForAuction(&s.bot.ai, &item, ITEM_USAGE_AH));
    }
    {
        Scenario s; Item& item = s.BagItem(100, 20); assert(s.Visit());
        assert(s.bot.session.depositPaid == 300 && s.bot.money == 9700 && item.count == 20);
    }
    {
        Scenario s; s.BagItem(100, 60); s.bot.money = 1000;
        Item& item = s.MakeItem(101, 1, ITEM_USAGE_EQUIP); s.Offer(item, 1, 200);
        assert(s.Visit()); assert(s.bot.money == 100 && s.bot.session.sells == 1 && !s.bot.session.buys);
    }
    {
        Scenario s; s.BagItem(); Item& item = s.MakeItem(101, 1, ITEM_USAGE_AH);
        for (uint32 id = 1; id <= MaxListings; ++id) s.Offer(item, id, 500, s.bot.guid.value, 1);
        assert(!s.Visit()); assert(!s.bot.session.sells && s.bot.inventory.size() == 1);
    }
    {
        Scenario s; Item& expensive = s.MakeItem(100, 1, ITEM_USAGE_EQUIP); s.Offer(expensive, 1, 700);
        Item& cheaper = s.MakeItem(101, 1, ITEM_USAGE_REPLACE); s.Offer(cheaper, 2, 400);
        assert(s.Visit()); assert(s.bot.session.buys == 1 && s.bot.session.lastAuction == 2);
        assert(s.bot.money == 9600 && !auctionMgr.house.GetAuction(2) && auctionMgr.house.GetAuction(1));
        assert(s.bot.inventory.empty()); // The service waits for normal delivery; no grant.
    }
    for (int rejection = 0; rejection < 14; ++rejection)
    {
        Scenario s; Item& item = s.MakeItem(100, 1, ITEM_USAGE_EQUIP); AuctionEntry& offer = s.Offer(item);
        switch (rejection)
        {
            case 0: offer.owner = s.bot.guid; break;
            case 1: characterCache.accounts[offer.owner] = s.bot.session.account; break;
            case 2: offer.bidder = s.bot.guid; break;
            case 3: offer.expire_time = now; break;
            case 4: s.bot.store = false; break;
            case 5: s.bot.usable = false; break;
            case 6: item.proto.conjured = true; break;
            case 7: item.proto.Class = ITEM_CLASS_QUEST; break;
            case 8: s.SetUsage(item, ITEM_USAGE_AH); break;
            case 9: s.bot.money = 100; break;
            case 10: s.bot.ai.context.budget.value = 499; break;
            case 11: offer.buyout = 1001; break;
            case 12: offer.itemCount = 2; break;
            case 13: characterCache.accounts[offer.owner] = 0; break;
        }
        uint32 const before = s.bot.money; assert(!s.Visit()); assert(!s.bot.session.buys);
        assert(s.bot.money == before && auctionMgr.house.GetAuction(1) == &offer);
    }
    {
        Scenario s; Item& item = s.MakeItem(100, 1, ITEM_USAGE_EQUIP); s.Offer(item);
        s.bot.session.rejectBuy = true; assert(!s.Visit()); assert(s.bot.session.buys == 1);
        assert(s.bot.money == 10000 && auctionMgr.house.GetAuction(1));
    }
    {
        Scenario s; Item& item = s.MakeItem(100, 1, ITEM_USAGE_EQUIP); s.Offer(item);
        assert(QueueVisit(&s.bot.ai, s.bot.auctioneer.guid, false));
        auctionMgr.house.auctions.clear(); // Another buyer bought/cancelled it before queued execution.
        assert(!PlayerbotWorldThreadProcessor::instance().queued.front()->Execute());
        assert(!s.bot.session.buys && s.bot.money == 10000);
    }
    {
        Scenario s; Item& item = s.MakeItem(100, 1, ITEM_USAGE_EQUIP); s.Offer(item);
        s.Receipt(&item).deliver_time = now + 10; assert(!s.Visit());
        assert(!s.bot.session.buys); // Delivery pending: avoid duplicate upgrades.
    }
    {
        Scenario s; Item& item = s.MakeItem(); Mail& mail = s.Receipt(&item, 250);
        assert(s.Visit(true)); assert(s.bot.money == 10250 && s.bot.inventory.size() == 1);
        assert(mail.state == MAIL_STATE_DELETED && mail.items.empty() && !mail.money);
        assert(s.bot.session.inboxes == 1 && s.bot.session.takesMoney == 1 &&
               s.bot.session.takesItem == 1 && s.bot.session.deletes == 1);
    }
    for (int rejection = 0; rejection < 4; ++rejection)
    {
        Scenario s; Item& item = s.MakeItem(); Mail& mail = s.Receipt(&item, 250);
        if (rejection == 0) mail.deliver_time = now + 1;
        if (rejection == 1) mail.COD = 1;
        if (rejection == 2) mail.expire_time = now;
        if (rejection == 3) mail.messageType = 0;
        assert(!s.Visit(true)); assert(!s.bot.session.takesMoney && !s.bot.session.takesItem && !s.bot.session.deletes);
        assert(s.bot.money == 10000 && mail.items.size() == 1 && mail.money == 250);
    }
    for (bool rejectAtHandler : {false, true})
    {
        Scenario s; Item& item = s.MakeItem(); Mail& mail = s.Receipt(&item, 250);
        s.bot.store = rejectAtHandler; s.bot.session.rejectItem = rejectAtHandler;
        assert(s.Visit(true)); assert(s.bot.money == 10250);
        assert(mail.state != MAIL_STATE_DELETED && mail.items.size() == 1 && !mail.money);
        assert(s.bot.GetMItem(item.guid.value) == &item && !s.bot.session.deletes && s.bot.inventory.empty());
    }
    {
        Scenario s; Item& item = s.MakeItem(); Mail& mail = s.Receipt(&item, 250);
        s.bot.session.rejectMoney = true; assert(s.Visit(true));
        assert(s.bot.money == 10000 && mail.money == 250 && mail.items.empty());
        assert(mail.state != MAIL_STATE_DELETED && !s.bot.session.deletes);
    }
    {
        Scenario s; Item& owned = s.BagItem(100, 3); Item& item = s.MakeItem(100, 2); Mail& mail = s.Receipt(&item);
        s.bot.session.mergeItem = true; assert(s.Visit(true));
        assert(mail.state == MAIL_STATE_DELETED && s.bot.attachments.empty() && s.bot.session.deletes == 1);
        assert(owned.count == 5 && allocatedItems.size() == 1); // No loss or duplicate stack on merge.
    }
    {
        Scenario s; Mail& mail = s.Receipt(nullptr, 1); s.bot.money = MaxCopper;
        assert(!s.Visit(true)); assert(mail.money == 1 && mail.state != MAIL_STATE_DELETED);
        assert(!s.bot.session.deletes && s.bot.money == MaxCopper);
    }
    {
        Scenario s; for (uint32 id = 0; id < MaxMailPerVisit + 3; ++id) s.Receipt(nullptr, 1);
        assert(s.Visit(true)); assert(s.bot.money == 10000 + MaxMailPerVisit);
        assert(s.bot.session.deletes == int(MaxMailPerVisit));
    }
    {
        Scenario s; Item& item = s.MakeItem();
        for (uint32 id = 10000; id < 11000; ++id) s.Offer(item, id, 500);
        auto first = SampleMarket(&auctionMgr.house, {1}); auto second = SampleMarket(&auctionMgr.house, {2});
        assert(first.size() == MaxMarketScan && second.size() == MaxMarketScan && first != second);
        assert(std::unordered_set<uint32>(first.begin(), first.end()).size() == MaxMarketScan);
    }
    std::cout << "Earned auctions: production policy/service, conserved inventory/gold, safe receipts, queued revalidation and travel selection passed\n";
}
int main() { PolicyTests(); TravelTests(); ServiceTests(); }
'''


production = (module / 'EarnedAuction.cpp').read_text()
# Keep the complete production service; fixtures replace only its includes/core
# dependencies. Policy remains the actual header included from the prepared module.
production = '\n'.join(line for line in production.splitlines()
                       if not line.lstrip().startswith('#include'))
source = fixtures + production + policy_tests + service_tests
with tempfile.TemporaryDirectory(prefix='portable-earned-auctions-') as temporary:
    target = Path(temporary) / 'auctions.cpp'
    executable = Path(temporary) / 'auctions'
    target.write_text(source)
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-no-pie',
                    '-g', '-I', str(module), '-I', str(travel_module),
                    str(target), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
