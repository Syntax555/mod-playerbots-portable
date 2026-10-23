"""Run earned-auction production policy and service against isolated core fixtures.

The fake core handlers model authoritative inventory, gold and mail outcomes,
including rejected operations. They do not implement the service's decisions.
The actual module translation unit supplies those decisions under ASan/UBSan,
and mutation checks confirm that its gates are required. This does not start a
realm or replace the full core/module compile check.
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
    profession_skills,
    run_fixture,
    source_argument,
)


repo = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser,
                    default=prepared_core(repo) / 'modules/mod-playerbots/src',
                    help='prepared Playerbots src directory')
parser.add_argument('--travel-source', type=Path,
                    help='optional separate src directory for the market-travel policy')
source_argument(parser, 'core', default=prepared_core(repo), help='prepared core source directory')
args = parser.parse_args()
module = args.source / 'Bot'
travel_module = (args.travel_source or args.source) / 'Bot'
usage_header = (args.source / 'Ai/Base/Value/ItemUsageValue.h').read_text()
values_source = (args.source / 'Ai/Base/Value/MaintenanceValues.cpp').read_text()
item_header = (args.core / 'src/server/game/Entities/Item/ItemTemplate.h').read_text()
auction_header = (args.core / 'src/server/game/AuctionHouse/AuctionHouseMgr.h').read_text()
auction_source = (args.core / 'src/server/game/AuctionHouse/AuctionHouseMgr.cpp').read_text()
auction_handlers = (args.core / 'src/server/game/Handlers/AuctionHouseHandler.cpp').read_text()
shared_defines = (args.core / 'src/server/shared/SharedDefines.h').read_text()
native = '\n'.join(function(source, signature) + ';' for source, signature in (
    (usage_header, 'enum ItemUsage : uint32'), (item_header, 'enum ItemClass'),
    (item_header, 'enum ItemSubclassWeapon'), (item_header, 'enum ItemSubclassContainer'),
    (item_header, 'enum ItemSubclassQuiver'), (item_header, 'enum InventoryType'),
    (auction_header, 'enum MailAuctionAnswers'),
    (shared_defines, 'enum ItemQualities')))
# Doubles for these producers keep their native shape.
assert 'uint32 TotemCategory;' in item_header and 'uint32 RequiredLevel;' in item_header
assert 'bool IsInRealGuild();' in (args.source / 'Bot/PlayerbotAI.h').read_text()
storage = (args.core / 'src/server/game/Entities/Player/PlayerStorage.cpp').read_text()
assert 'return item->ToBag();' in function(storage, 'Bag* Player::GetBagByPos(uint8 bag) const')
assert 'uint32 auctionTime = uint32(etime * sWorld->getRate(RATE_AUCTION_TIME));' in auction_handlers
assert auction_handlers.count('CONFIG_AUCTION_LEVEL_REQ') == 2 and (
    'if (GetPlayer()->GetLevel() < sWorld->getIntConfig(CONFIG_AUCTION_LEVEL_REQ))'
    in function(auction_handlers, 'void WorldSession::SendAuctionHello(ObjectGuid guid, Creature* unit)'))
# Receipts carry the subject the core writes; the parser must keep reading that format.
subject_writer = function(auction_source, 'std::string AuctionEntry::BuildAuctionMailSubject(MailAuctionAnswers response) const')
util_header = (args.core / 'src/common/Utilities/Util.h').read_text()
assert 'template <class T, class U>\ninline T CalculatePct(T base, U pct)' in util_header
# The deposit, cut and percentage doubles are the core's own definitions.
auction_rules = '\n'.join([
    'template <class T, class U>', function(util_header, 'inline T CalculatePct(T base, U pct)'),
    next(line for line in auction_source.splitlines() if line.startswith('constexpr auto AH_MINIMUM_DEPOSIT = ')),
    function(auction_source, 'uint32 AuctionHouseMgr::GetAuctionDeposit(AuctionHouseEntry const* entry, uint32 time, '
                             'Item* pItem, uint32 count)'),
    function(auction_source, 'uint32 AuctionEntry::GetAuctionCut() const'),
    function(auction_source, 'uint32 AuctionEntry::CalculateAuctionOutBid(uint32 bid)'),
])
bid_handler = function(auction_handlers, 'void WorldSession::HandleAuctionPlaceBid(WorldPacket& recvData)')
for rule in ('if (price <= auction->bid || price < auction->startbid)',
             ('if ((price < auction->buyout || auction->buyout == 0) &&\n'
              '            price < auction->bid + AuctionEntry::CalculateAuctionOutBid(auction->bid))'),
             'if (!player->HasEnoughMoney(price))', 'if (price < auction->buyout || auction->buyout == 0)',
             'sAuctionMgr->SendAuctionOutbiddedMail(auction, price, GetPlayer(), trans);',
             'auction->bidder = player->GetGUID();\n        auction->bid = price;'):
    assert rule in bid_handler, rule
assert "strm << item_template << \":0:\" << response << ':' << Id << ':' << itemCount;" in subject_writer


def sql_values(row):
    values, value, quoted, index = [], '', False, 0
    while index < len(row):
        char = row[index]
        if quoted and char == '\\':
            value += row[index + 1]
            index += 1
        elif char == "'":
            quoted = not quoted
        elif char == ',' and not quoted:
            values.append(value)
            value = ''
        else:
            value += char
        index += 1
    return values + [value]


def tool_rows():
    """Every tool the upstream usage marks as needed for a skill, with its pinned item data."""
    usage_source = (args.source / 'Ai/Base/Value/ItemUsageValue.cpp').read_text()
    body = function(usage_source, 'bool ItemUsageValue::IsItemNeededForSkill(ItemTemplate const* proto)')
    skills = {int(entry): set(re.findall(r'SKILL_[A-Z]+', needs))
              for entry, needs in re.findall(r'case (\d+):[^\n]*\n\s*return ([^;]+);', body)}
    table = (args.core / 'data/sql/base/db_world/item_template.sql').read_text(encoding='utf-8')
    create = table.split('CREATE TABLE `item_template` (')[1].split(') ENGINE')[0]
    columns = [line.split('`')[1] for line in create.splitlines() if line.strip().startswith('`')]
    rows = {}
    for line in table.splitlines():
        if line.startswith('(') and line.split(',', 1)[0][1:].isdigit() and int(line.split(',', 1)[0][1:]) in skills:
            values = dict(zip(columns, sql_values(line.rstrip(',;')[1:-1]), strict=True))
            rows[int(values['entry'])] = values
    assert len(skills) >= 20 and set(rows) == set(skills), sorted(set(skills) - set(rows))
    gathering = {'SKILL_MINING', 'SKILL_SKINNING', 'SKILL_FISHING', 'SKILL_HERBALISM'}
    # The data distinguishes gathering from crafting tools only if both kinds exist.
    assert {bool(needs & gathering) for needs in skills.values()} == {True, False}
    return ',\n'.join(
        f'    {{{entry}, {row["class"]}, {row["subclass"]}, {row["TotemCategory"]}, '
        f'{"true" if skills[entry] & gathering else "false"}}}'
        for entry, row in sorted(rows.items()))


policy_tests = r'''
void PolicyTests()
{
    using namespace EarnedAuction;
    assert(PriceCeiling(100, 1, 20, 1) == 120 && PriceCeiling(1000, 1, 20, 1) == 1000);
    assert(PriceCeiling(100, 1, 20, 5) == 600 && PriceCeiling(0, 1, 0, 5) == 0);
    // Vendors sell BuyCount items for BuyPrice: 200 arrows for 10 copper.
    assert(PriceCeiling(10, 200, 0, 200) == 10 && PriceCeiling(10, 200, 0, 1000) == 50);
    assert(PriceCeiling(10, 200, 0, 1) == 1 && PriceCeiling(25, 5, 1, 5) == 30 && PriceCeiling(25, 0, 0, 1) == 25);
    assert(PriceCeiling(UINT32_MAX, 1, UINT32_MAX, UINT32_MAX) == MaxCopper);
    assert(PriceCeiling(UINT32_MAX, UINT32_MAX, 0, UINT32_MAX) == MaxCopper);

    auto ordinary = PriceListing(100, 1, 20, 5, 0);
    assert(ordinary.bid == 240 && ordinary.buyout == 300);
    auto undercut = PriceListing(100, 1, 20, 5, 100);
    assert(undercut.bid == 396 && undercut.buyout == 495);
    // No listing undercuts a market at twice the vendor price.
    assert(!PriceListing(100, 1, 20, 5, 1).buyout && !PriceListing(100, 1, 20, 5, 40).buyout);
    assert(PriceListing(100, 1, 20, 5, 41).buyout == 200);
    auto highMarket = PriceListing(100, 1, 20, 5, UINT32_MAX);
    assert(highMarket.bid == 480 && highMarket.buyout == 600);
    assert(!PriceListing(100, 1, 0, 5, 50).buyout);
    assert(!PriceListing(100, 1, 20, 0, 50).buyout);
    assert(!PriceListing(UINT32_MAX, 1, UINT32_MAX, 1, 50).buyout);
    assert(!PriceListing(100, 1, 20, UINT32_MAX, 50).buyout);

    // A sale after the cut must beat vendoring by at least the deposit.
    assert(WorthListing(300, 15, 100, 100) && WorthListing(300, 15, 100, 185));
    assert(!WorthListing(300, 15, 100, 186) && !WorthListing(15, 0, 5, 100) && !WorthListing(10, 10, 0, 0));
    assert(WorthListing(1, 0, 0, 0) && !WorthListing(100, 0, 100, 0));
    for (std::uint32_t count : {1u, 2u, 20u, 1000u, UINT32_MAX})
        for (std::uint32_t sell : {0u, 1u, 200u, MaxCopper / 2, MaxCopper, UINT32_MAX})
            for (std::uint32_t market : {0u, 1u, 500u, UINT32_MAX})
            {
                auto prices = PriceListing(UINT32_MAX, 1, sell, count, market);
                if (prices.buyout)
                {
                    assert(prices.bid && prices.bid <= prices.buyout);
                    assert(prices.buyout <= MaxCopper);
                    assert(std::uint64_t(prices.buyout) > std::uint64_t(sell) * count);
                    assert(WithinPriceCeiling(prices.buyout, PriceCeiling(UINT32_MAX, 1, sell, count)));
                }
                else
                    assert(!prices.bid);
            }

    assert(Affordable(100, 100, 100));
    assert(!Affordable(0, 100, 100));
    assert(!Affordable(101, 100, 1000));
    assert(!Affordable(101, 1000, 100));
    assert(!Affordable(UINT32_MAX, UINT32_MAX, UINT32_MAX));
    assert(WithinPriceCeiling(200, 200) && !WithinPriceCeiling(201, 200));
    // Bids go to auctions ending within two visits, at the core's minimum.
    assert(BidWindow(1, 300) && BidWindow(600, 300) && !BidWindow(601, 300) && !BidWindow(0, 300));
    assert(MinimumBid(400, 0, 1) == 400 && MinimumBid(400, 500, 25) == 525 && !MinimumBid(1, MaxCopper, 1));
    // Gear outranks consumables; within a tier the better bargain, then the lower price, wins.
    assert(BetterOffer(RankOffer(0, 900, 1000), RankOffer(2, 100, 5000)));
    assert(BetterOffer(RankOffer(0, 600, 2000), RankOffer(0, 500, 1000)));
    assert(BetterOffer(RankOffer(0, 100, 1000), RankOffer(0, 200, 2000)));
    assert(!BetterOffer(RankOffer(1, 100, 1000), RankOffer(1, 100, 1000)));
    assert(RankOffer(3, UINT32_MAX, UINT32_MAX).relative == 1000);
    assert(!WithinPriceCeiling(0, 100) && !WithinPriceCeiling(1, 0));

    auto subject = ParseAuctionSubject("2589:0:3:17:20");
    assert(subject && subject->item == 2589 && subject->response == 3 && subject->auction == 17 && subject->count == 20);
    assert(ParseAuctionSubject("4294967295:0:6:4294967295:4294967295"));
    for (char const* malformed : {"", "2589:0:3:17", "2589:0:3:17:20:1", "2589:1:3:17:20", "2589:0:x:17:20",
                                  "2589::3:17:20", "2589:0:3:17:20 ", "-1:0:3:17:20", "4294967296:0:3:17:20",
                                  ":0:3:17:20", "2589:0:3:17:", "+2589:0:3:17:20"})
        assert(!ParseAuctionSubject(malformed));
    assert(RelistAllowed({0, 0}, 0, 0) && RelistAllowed({MaxUnsoldListings - 1, 100}, 100, 43200));
    assert(!RelistAllowed({MaxUnsoldListings, 100}, 100 + UnsoldMemorySeconds - 1, 43200));
    assert(RelistAllowed({MaxUnsoldListings, 100}, 100 + UnsoldMemorySeconds, 43200));
    // Week-long listings are remembered for three rounds.
    assert(!RelistAllowed({MaxUnsoldListings, 100}, 100 + 3 * UnsoldMemorySeconds - 1, UnsoldMemorySeconds));
    assert(RelistAllowed({MaxUnsoldListings, 100}, 100 + 3 * UnsoldMemorySeconds, UnsoldMemorySeconds));
    UnsoldRecord record;
    CountUnsold(record, 1000, 43200); assert(record.unsold == 1 && record.last == 1000);
    CountUnsold(record, 44199, 43200); assert(record.unsold == 1 && record.last == 1000);
    CountUnsold(record, 44200, 43200); assert(record.unsold == 2 && record.last == 44200);
    CountUnsold(record, 44200, 0); assert(record.unsold == 3);

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
#include <mutex>
#include <optional>
#include <set>
#include <shared_mutex>
#include <sstream>
#include <string>
#include <tuple>
#include <type_traits>
#include <unordered_set>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
using int32 = std::int32_t;
@@NATIVE@@
@@PROFESSIONS@@
constexpr uint32 MINUTE = 60, MIN_AUCTION_TIME = 43200;
constexpr uint8 INVENTORY_SLOT_BAG_0 = 0, INVENTORY_SLOT_BAG_START = 19,
    INVENTORY_SLOT_BAG_END = 23, INVENTORY_SLOT_ITEM_START = 23, INVENTORY_SLOT_ITEM_END = 39;
constexpr int ITEM_FIELD_DURATION = 1, ITEM_FLAG_CONJURED = 2, BIND_QUEST_ITEM = 4,
    PLAYERSPELL_REMOVED = 1, MAX_SPELL_REAGENTS = 8, NULL_BAG = 255, NULL_SLOT = 255,
    EQUIP_ERR_OK = 0, GAMEOBJECT_TYPE_MAILBOX = 1, UNIT_NPC_FLAG_MAILBOX = 2,
    UNIT_NPC_FLAG_AUCTIONEER = 4, MAIL_AUCTION = 2, MAIL_STATE_DELETED = 3,
    MAX_QUEST_LOG_SIZE = 25, SPELL_EFFECT_CREATE_ITEM = 24;
constexpr int CMSG_GET_MAIL_LIST = 1, CMSG_MAIL_TAKE_MONEY = 2, CMSG_MAIL_TAKE_ITEM = 3,
    CMSG_MAIL_DELETE = 4, CMSG_AUCTION_SELL_ITEM = 5, CMSG_AUCTION_PLACE_BID = 6;
constexpr float INTERACTION_DISTANCE = 5;
enum class NeedMoneyFor : uint32 { gear, ammo, consumables, tradeskill, anything };
struct ObjectGuid
{
    using LowType = uint32;
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
    uint32 ItemId = 100, BuyPrice = 1000, BuyCount = 1, SellPrice = 100, Quality = 1, Class = ITEM_CLASS_MISC,
        SubClass = 0, Bonding = 0, TotemCategory = 0, RequiredLevel = 0, ContainerSlots = 0, InventoryType = 0;
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
    bool IsBag() const { return proto.InventoryType == INVTYPE_BAG; }
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
    SkillLineAbilityMap abilities;
    mutable unsigned lookups = 0;
    SpellInfo const* GetSpellInfo(uint32 id) const
    { ++lookups; auto it = spells.find(id); return it == spells.end() ? nullptr : &it->second; }
    SkillLineAbilityMapBounds GetSkillLineAbilityMapBounds(uint32 id) const { return abilities.equal_range(id); }
} spellMgr;
auto* sSpellMgr = &spellMgr;
@@PROFESSION@@
struct Quest
{
    std::array<uint32, 6> RequiredItemId{}, ItemDrop{};
    uint32 source = 0;
    uint32 GetSrcItemId() const { return source; }
};
struct ObjectMgr
{
    std::map<uint32, Quest> quests;
    mutable unsigned lookups = 0;
    Quest const* GetQuestTemplate(uint32 id) const
    { ++lookups; auto it = quests.find(id); return it == quests.end() ? nullptr : &it->second; }
} objectMgr;
auto* sObjectMgr = &objectMgr;
template<class T> struct Value { T value{}; void Reset() {} T Get() const { return value; } };
struct AiObjectContext
{
    Value<bool> canMove{true}; Value<uint8> bagSpace{0}; Value<uint32> budget{10000}, supplies{0};
    std::map<std::string, Value<ItemUsage>> usage;
    std::string lastQualifier;
    unsigned usageLookups = 0;
    std::map<uint32, Value<ItemUsage>> upgrades;
    template<class T, class Q = std::string> Value<T>* GetValue(std::string const& name, Q qualifier = {})
    {
        if constexpr (std::is_same_v<T, ItemUsage> && !std::is_same_v<Q, std::string>)
        { assert(name == "item upgrade"); return &upgrades[qualifier]; }
        else if constexpr (std::is_same_v<T, bool>) return &canMove;
        else if constexpr (std::is_same_v<T, uint8>) return &bagSpace;
        else if constexpr (std::is_same_v<T, uint32>) return name == "money needed for" ? &supplies : &budget;
        else { ++usageLookups; lastQualifier = qualifier; return &usage[qualifier]; }
    }
};
struct Player;
struct PlayerbotAI
{
    Player* bot = nullptr; AiObjectContext context; bool master = false, realGuild = false;
    Player* GetBot() const { return bot; }
    AiObjectContext* GetAiObjectContext() { return &context; }
    bool HasGameClientMaster() const { return master; }
    bool IsInRealGuild() const { return realGuild; }
};
struct MailItemInfo { uint32 item_guid; };
struct Mail
{
    uint32 messageID = 0, money = 0, COD = 0;
    int messageType = MAIL_AUCTION, state = 0;
    std::int64_t deliver_time = 1000, expire_time = 100000;
    std::string subject;
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
// DBC deposit percentages are a third of the real ones: 15% and 75% for 12 hours.
struct AuctionHouseEntry { uint32 houseId = 0, faction = 0, depositPercent = 0, cutPercent = 0; };
AuctionHouseEntry const factionHouse{2, 12, 5, 5}, neutralHouse{7, 0, 25, 15};
struct AuctionEntry
{
    uint32 Id = 0, item_template = 0, itemCount = 0, buyout = 0, bid = 0, startbid = 0;
    ObjectGuid item_guid, owner, bidder;
    static uint32 CalculateAuctionOutBid(uint32 bid);
    std::int64_t expire_time = 100000;
    AuctionHouseEntry const* auctionHouseEntry = &factionHouse;
    std::string BuildAuctionMailSubject(MailAuctionAnswers response) const;
    uint32 GetAuctionCut() const;
};
@@SUBJECT@@
struct AuctionHouseObject
{
    std::map<uint32, AuctionEntry*> auctions;
    auto const& GetAuctions() const { return auctions; }
    AuctionEntry* GetAuction(uint32 id) const
    { auto it = auctions.find(id); return it == auctions.end() ? nullptr : it->second; }
};
constexpr int RATE_AUCTION_DEPOSIT = 1, RATE_AUCTION_CUT = 2, RATE_AUCTION_TIME = 3, CONFIG_AUCTION_LEVEL_REQ = 4;
struct World
{
    float rate = 1, cutRate = 1, timeRate = 1;
    uint32 auctionLevel = 1;
    uint32 getIntConfig(int which) const { assert(which == CONFIG_AUCTION_LEVEL_REQ); return auctionLevel; }
    float getRate(int which) const
    { return which == RATE_AUCTION_CUT ? cutRate : which == RATE_AUCTION_TIME ? timeRate : rate; }
} world;
struct ToolRow { uint32 entry, cls, subclass, totem; bool gathers; };
std::vector<ToolRow> const tools{
@@TOOLS@@
};
auto* sWorld = &world;
#define LOG_DEBUG(...)
struct AuctionHouseMgr
{
    AuctionHouseObject house;
    std::map<ObjectGuid, Item*> items;
    static AuctionHouseEntry const* GetAuctionHouseEntryFromFactionTemplate(uint32) { return &factionHouse; }
    static AuctionHouseEntry const* GetAuctionHouseEntryFromHouse(AuctionHouseId house)
    { return house == AuctionHouseId::Neutral ? &neutralHouse : &factionHouse; }
    AuctionHouseObject* GetAuctionsMap(uint32) { return &house; }
    AuctionHouseObject* GetAuctionsMapByHouseId(AuctionHouseId) { return &house; }
    Item* GetAItem(ObjectGuid guid) const
    { auto it = items.find(guid); return it == items.end() ? nullptr : it->second; }
    static uint32 GetAuctionDeposit(AuctionHouseEntry const* entry, uint32 time, Item* pItem, uint32 count);
} auctionMgr;
auto* sAuctionMgr = &auctionMgr;
@@AUCTIONRULES@@
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
    std::vector<std::pair<ObjectGuid, uint32>> refunds;
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
    uint32 money = 10000, level = 80;
    uint32 GetLevel() const { return level; }
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
    std::map<uint8, Bag*> bags;
    Item* GetItemByPos(uint8, uint8 slot) const
    {
        if (slot >= INVENTORY_SLOT_BAG_START && slot < INVENTORY_SLOT_BAG_END)
        { auto bag = bags.find(slot); return bag == bags.end() ? nullptr : bag->second; }
        auto it = backpack.find(slot); return it == backpack.end() ? nullptr : it->second;
    }
    Bag* GetBagByPos(uint8 slot) const { return dynamic_cast<Bag*>(GetItemByPos(INVENTORY_SLOT_BAG_0, slot)); }
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
    int CanStoreItem(int bag, int, ItemPosCountVec&, Item*, bool) const
    {
        if (!store || bag != INVENTORY_SLOT_BAG_0)
            return store ? EQUIP_ERR_OK : 1;
        for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
            if (!backpack.count(slot))
                return EQUIP_ERR_OK;
        return 1;
    }
    int CanUseItem(ItemTemplate const*) const { return usable ? EQUIP_ERR_OK : 1; }
    GameObject* GetGameObjectIfCanInteractWith(ObjectGuid id, int)
    { return range && id == mailbox.guid ? &mailbox : nullptr; }
    Creature* GetNPCIfCanInteractWith(ObjectGuid id, int flag)
    { if (!range) return nullptr; return flag == UNIT_NPC_FLAG_AUCTIONEER && id == auctioneer.guid ? &auctioneer :
        flag == UNIT_NPC_FLAG_MAILBOX && id == creatureMailbox.guid ? &creatureMailbox : nullptr; }
    bool IsWithinDistInMap(WorldObject*, float) const { return range; }
};
@@BAGS@@
struct Config
{
    bool naturalProgression = true, earnedAuctions = true; uint32 earnedAuctionInterval = 300;
    std::set<uint32> randomAccounts{2};
    bool IsInRandomAccountList(uint32 id) const { return randomAccounts.contains(id); }
} sPlayerbotAIConfig;
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
    for (uint32 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
        if (!bot->backpack.count(slot)) { bot->backpack[slot] = item; break; }
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
    depositPaid = AuctionHouseMgr::GetAuctionDeposit(&factionHouse, MIN_AUCTION_TIME, item, item->count);
    assert(bot->money >= depositPaid); bot->money -= depositPaid;
    bot->inventory.erase(lastItem);
    std::erase_if(bot->backpack, [this](auto const& pair) { return pair.second->guid == lastItem; });
    auctionMgr.items[lastItem] = item;
}
void WorldSession::HandleAuctionPlaceBid(WorldPacket& packet)
{
    ++buys; lastAuction = packet.data.at(1); lastPrice = packet.data.at(2);
    AuctionEntry* offer = auctionMgr.house.GetAuction(lastAuction);
    assert(offer && offer->bidder != bot->guid && (!offer->buyout || lastPrice <= offer->buyout));
    if (rejectBuy) return;
    // The core's checks, in its order: the bid and start bid, the increment below
    // the buyout, then the bidder's gold.
    if (lastPrice <= offer->bid || lastPrice < offer->startbid)
        return;
    bool const bid = lastPrice < offer->buyout || !offer->buyout;
    if (bid && lastPrice < offer->bid + AuctionEntry::CalculateAuctionOutBid(offer->bid))
        return;
    if (bot->money < lastPrice)
        return;
    bot->money -= lastPrice;
    if (!bid)
    {
        auctionMgr.house.auctions.erase(lastAuction);
        return;
    }
    if (offer->bidder)
        refunds.push_back({offer->bidder, offer->bid});
    offer->bidder = bot->guid; offer->bid = lastPrice;
}
namespace EarnedAuction
{
bool IsEnabled(PlayerbotAI*); bool HasSurplus(PlayerbotAI*);
bool HasVendorSurplus(PlayerbotAI*); bool SellsToVendor(PlayerbotAI*, Item*, ItemUsage);
bool ShouldReserveForAuction(PlayerbotAI*, Item*, ItemUsage); bool QueueVisit(PlayerbotAI*, ObjectGuid, bool);
bool MeetsAuctionLevel(Player*);
}
'''

service_tests = r'''
void TravelTests()
{
    using namespace EarnedAuctionTravel;
    assert(!CanStartTravel(9, 1, true, UINT32_MAX));
    assert(!CanStartTravel(10, 1, false, 99));
    assert(CanStartTravel(10, 1, false, 100));
    assert(CanStartTravel(10, 1, true, 0));
    // LevelReq.Auction raises the travel level.
    assert(!CanStartTravel(19, 20, true, 0) && CanStartTravel(20, 20, true, 0) && !CanStartTravel(9, 5, true, 0));
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
        allocatedItems.clear(); objectMgr.quests.clear(); spellMgr.spells.clear(); spellMgr.abilities.clear();
        sSkillLineStore.rows = {{SKILL_TAILORING, {SKILL_TAILORING, SKILL_CATEGORY_PROFESSION}},
                                {SKILL_DEFENSE, {SKILL_DEFENSE, SKILL_CATEGORY_WEAPON}}};
        objectMgr.lookups = 0; spellMgr.lookups = 0;
        sPlayerbotAIConfig = {}; world = {}; now += 400;
        auto& processor = PlayerbotWorldThreadProcessor::instance(); processor.queued.clear(); processor.accept = true;
    }
    Item& MakeItem(uint32 entry = 100, uint32 count = 1, ItemUsage usage = ITEM_USAGE_AH)
    {
        auto item = std::make_unique<Item>(); item->guid = {uint32(items.size() + 1000)};
        item->owner = bot.guid; item->proto.ItemId = entry; item->count = count;
        Item& result = *item; items.push_back(item->guid); allocatedItems[result.guid] = std::move(item);
        SetUsage(result, usage); return result;
    }
    AuctionEntry& BidOffer(Item& item, uint32 startbid = 400, std::int64_t timeLeft = 300)
    {
        AuctionEntry& offer = Offer(item, 1, 0); offer.startbid = startbid; offer.expire_time = now + timeLeft;
        return offer;
    }
    // Fill the bag slots; the first holds the smallest container.
    void EquipBags(uint32 smallestClass = ITEM_CLASS_CONTAINER, uint32 smallestSubclass = ITEM_SUBCLASS_CONTAINER)
    {
        for (uint8 slot = INVENTORY_SLOT_BAG_START; slot < INVENTORY_SLOT_BAG_END; ++slot)
        {
            auto bag = std::make_unique<Bag>(); bag->guid = {uint32(items.size() + 1000)}; bag->owner = bot.guid;
            bool const smallest = slot == INVENTORY_SLOT_BAG_START;
            bag->proto.ItemId = 900 + slot; bag->proto.Class = smallest ? smallestClass : uint32(ITEM_CLASS_CONTAINER);
            bag->proto.SubClass = smallest ? smallestSubclass : uint32(ITEM_SUBCLASS_CONTAINER);
            bag->proto.ContainerSlots = smallest ? 6 : 8; bag->items.assign(bag->proto.ContainerSlots, nullptr);
            bot.bags[slot] = bag.get(); items.push_back(bag->guid); allocatedItems[bag->guid] = std::move(bag);
        }
    }
    Item& OfferBag(uint32 slots)
    {
        Item& bag = MakeItem(101, 1, ITEM_USAGE_EQUIP); bag.proto.Class = ITEM_CLASS_CONTAINER;
        bag.proto.ContainerSlots = slots; bag.proto.InventoryType = INVTYPE_BAG; Offer(bag); return bag;
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
    std::string Subject(Item const& item, MailAuctionAnswers response)
    {
        AuctionEntry auction; auction.Id = 7; auction.item_template = item.GetEntry(); auction.itemCount = item.count;
        return auction.BuildAuctionMailSubject(response);
    }
    std::int64_t Listing() const { return std::int64_t(MIN_AUCTION_TIME * double(world.timeRate)); }
    // List the stack, let the auction expire and collect the returned stack.
    void Unsold(Item& item)
    {
        assert(Visit()); assert(bot.session.lastItem == item.guid && !bot.GetItemByGuid(item.guid));
        now += Listing(); Receipt(&item).subject = Subject(item, AUCTION_EXPIRED); auctionMgr.items.erase(item.guid);
        assert(Visit(true)); assert(bot.GetItemByGuid(item.guid) == &item);
        now += sPlayerbotAIConfig.earnedAuctionInterval;
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
        // A repeated visit inside the interval does nothing; the next one sells again.
        now += sPlayerbotAIConfig.earnedAuctionInterval - 1; assert(!s.Visit()); assert(s.bot.inventory.size() == 3);
        now += 1; assert(s.Visit()); assert(s.bot.inventory.size() == 1);
    }
    {
        Scenario s; Item& item = s.BagItem(); PlayerSpell spell; s.bot.spells[99] = &spell;
        spellMgr.spells[99].Reagent[0] = int(item.GetEntry()); assert(!HasSurplus(&s.bot.ai));
        spell.State = PLAYERSPELL_REMOVED; assert(HasSurplus(&s.bot.ai));
        s.bot.spells.clear(); Pet pet; item.proto.petFood = true; s.bot.pet = &pet; assert(!HasSurplus(&s.bot.ai));
    }
    for (int excluded = 0; excluded < 4; ++excluded)
    {
        Scenario s; Item& item = s.BagItem(); PlayerSpell spell; s.bot.spells[99] = &spell;
        spellMgr.spells[99].Reagent[0] = int(item.GetEntry());
        if (excluded == 0) spell.State = PLAYERSPELL_REMOVED;
        if (excluded == 1) spell.Active = false;
        if (excluded == 2) spellMgr.spells[99].passive = true;
        if (excluded == 3) spellMgr.spells.clear();
        assert(HasSurplus(&s.bot.ai));
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
    {
        // Single-item reservations and a batch sharing the same first objective
        // preserve early returns instead of eagerly scanning every quest.
        Scenario s;
        for (uint32 id = 1; id <= MAX_QUEST_LOG_SIZE; ++id)
        {
            s.bot.quests[id - 1] = id;
            objectMgr.quests[id].RequiredItemId[0] = 100 + id;
        }
        Item& first = s.BagItem(101);
        assert(ShouldReserveForAuction(&s.bot.ai, &first, ITEM_USAGE_AH));
        assert(objectMgr.lookups == 1 && !spellMgr.lookups);
        for (uint32 id = 0; id < 15; ++id) s.BagItem(101);
        objectMgr.lookups = 0;
        assert(!HasSurplus(&s.bot.ai));
        assert(objectMgr.lookups == 1 && !spellMgr.lookups);
        // The next decision must resume for an item protected by a later quest.
        first.proto.ItemId = 125; s.SetUsage(first, ITEM_USAGE_AH);
        objectMgr.lookups = 0;
        assert(!HasSurplus(&s.bot.ai));
        assert(objectMgr.lookups == MAX_QUEST_LOG_SIZE && !spellMgr.lookups);
    }
    {
        Scenario s; PlayerSpell learned;
        for (uint32 id = 1; id <= 300; ++id)
        {
            s.bot.spells[id] = &learned;
            spellMgr.spells[id].Reagent[0] = id == 1 ? 100 : id == 300 ? 101 : 999;
        }
        Item& first = s.BagItem(100);
        assert(ShouldReserveForAuction(&s.bot.ai, &first, ITEM_USAGE_AH));
        assert(spellMgr.lookups == 1);
        for (uint32 id = 0; id < 15; ++id) s.BagItem(100);
        spellMgr.lookups = 0;
        assert(!HasSurplus(&s.bot.ai));
        assert(spellMgr.lookups == 1);
        first.proto.ItemId = 101; s.SetUsage(first, ITEM_USAGE_AH);
        spellMgr.lookups = 0;
        assert(!HasSurplus(&s.bot.ai));
        assert(spellMgr.lookups == 300);
    }
    {
        // Full-bag decisions should inspect static quest/spell requirements once,
        // including objectives that are already complete but not turned in.
        Scenario s; PlayerSpell learned;
        for (uint32 id = 1; id <= 300; ++id)
        {
            s.bot.spells[id] = &learned;
            spellMgr.spells[id].Reagent[0] = id == 300 ? 100 : 0;
        }
        for (uint32 id = 1; id <= MAX_QUEST_LOG_SIZE; ++id)
        {
            s.bot.quests[id - 1] = id;
            objectMgr.quests[id].RequiredItemId[0] = 500 + id;
        }
        for (uint32 id = 0; id < 16; ++id) s.BagItem(100);
        assert(!HasSurplus(&s.bot.ai));
        std::cout << "Full-bag protection lookups: quests=" << objectMgr.lookups
                  << ", spells=" << spellMgr.lookups << ", item usage="
                  << s.bot.ai.context.usageLookups << '\n';
        assert(objectMgr.lookups == MAX_QUEST_LOG_SIZE && spellMgr.lookups == 300);
        assert(s.bot.ai.context.usageLookups == 16);
        objectMgr.lookups = 0; spellMgr.lookups = 0;
        assert(!HasVendorSurplus(&s.bot.ai));
        assert(objectMgr.lookups == MAX_QUEST_LOG_SIZE && spellMgr.lookups == 300);
        // A later decision sees changed quests, active spells and their reagents.
        s.bot.spells.erase(300);
        assert(HasSurplus(&s.bot.ai));
        objectMgr.quests[1].RequiredItemId[0] = 100;
        assert(!HasSurplus(&s.bot.ai));
        objectMgr.quests[1].RequiredItemId[0] = 501;
        assert(HasSurplus(&s.bot.ai));
        s.bot.spells[300] = &learned;
        assert(!HasSurplus(&s.bot.ai));
    }
    {
        // Failed core sales leave every item in place. Even this full traversal
        // must not rescan the character's spellbook once for each attempt.
        Scenario s; PlayerSpell learned;
        for (uint32 id = 1; id <= 300; ++id)
        {
            s.bot.spells[id] = &learned;
            spellMgr.spells[id].Reagent[0] = 999;
        }
        for (uint32 id = 0; id < 16; ++id) s.BagItem(100);
        s.bot.session.rejectSell = true;
        assert(!s.Visit());
        assert(spellMgr.lookups == 300 && s.bot.session.sells == 16);
        assert(s.bot.inventory.size() == 16 && s.bot.money == 10000);
    }
    {
        // Items that cannot be listed need no equipment/skill usage evaluation.
        Scenario s;
        for (uint32 id = 0; id < 16; ++id) s.BagItem(100).bound = true;
        assert(!HasSurplus(&s.bot.ai));
        assert(!s.Visit());
        assert(!s.bot.ai.context.usageLookups && !objectMgr.lookups && !spellMgr.lookups);
    }
    {
        // Selling one stack changes the live pet-food reserve for the next stack.
        Scenario s; Pet pet; s.bot.pet = &pet;
        Item& first = s.BagItem(100, 20); first.proto.petFood = true;
        Item& second = s.BagItem(100, 20); second.proto.petFood = true;
        assert(s.Visit()); assert(s.bot.session.sells == 1);
        assert(!s.bot.GetItemByGuid(first.guid) && s.bot.GetItemByGuid(second.guid) == &second);
    }
    {
        // Natural bots do not craft: a recipe's reagent is ordinary surplus, a class spell's is kept.
        Scenario s; Item& item = s.BagItem(); PlayerSpell spell; s.bot.spells[99] = &spell;
        spellMgr.spells[99].Reagent[0] = int(item.GetEntry());
        SkillLineAbilityEntry defense{1, SKILL_DEFENSE, 99}; spellMgr.abilities.insert({99, &defense});
        assert(!HasSurplus(&s.bot.ai) && ShouldReserveForAuction(&s.bot.ai, &item, ITEM_USAGE_VENDOR));
        SkillLineAbilityEntry tailoring{2, SKILL_TAILORING, 99}; spellMgr.abilities.insert({99, &tailoring});
        assert(HasSurplus(&s.bot.ai) && !ShouldReserveForAuction(&s.bot.ai, &item, ITEM_USAGE_VENDOR));
        // SelfBots and altbots belong to players who craft.
        s.bot.ai.master = true; assert(ShouldReserveForAuction(&s.bot.ai, &item, ITEM_USAGE_VENDOR));
        s.bot.ai.master = false; s.bot.random = false; assert(ShouldReserveForAuction(&s.bot.ai, &item, ITEM_USAGE_VENDOR));
    }
    {
        // Of profession items, natural bots buy only gathering tools.
        Scenario s; Item& cloth = s.MakeItem(100, 1, ITEM_USAGE_SKILL); cloth.proto.Class = ITEM_CLASS_TRADE_GOODS;
        s.Offer(cloth); assert(!s.Visit()); assert(!s.bot.session.buys && s.bot.money == 10000);
        for (ToolRow const& tool : tools)
        {
            ItemTemplate proto; proto.ItemId = tool.entry; proto.Class = tool.cls; proto.SubClass = tool.subclass;
            proto.TotemCategory = tool.totem; assert(GatheringTool(&proto) == tool.gathers);
        }
    }
    {
        // LevelReq.Auction applies as at the auction window; mailboxes stay open.
        Scenario s; Item& stock = s.BagItem(100, 5); world.auctionLevel = 20; s.bot.level = 19;
        assert(!MeetsAuctionLevel(&s.bot) && !QueueVisit(&s.bot.ai, s.bot.auctioneer.guid, false));
        assert(!ShouldReserveForAuction(&s.bot.ai, &stock, ITEM_USAGE_AH));
        s.bot.level = 20; assert(ShouldReserveForAuction(&s.bot.ai, &stock, ITEM_USAGE_AH)); s.bot.level = 19;
        s.Receipt(nullptr, 400); assert(s.Visit(true)); assert(s.bot.money == 10400);
        auto& processor = PlayerbotWorldThreadProcessor::instance();
        s.bot.level = 20; assert(QueueVisit(&s.bot.ai, s.bot.auctioneer.guid, false)); s.bot.level = 19;
        auto operation = std::move(processor.queued.back()); processor.queued.clear();
        assert(!operation->Execute()); assert(!s.bot.session.sells);
        s.bot.level = 20; assert(s.Visit()); assert(s.bot.session.sells == 1);
    }
    {
        // A gear upgrade outranks a cheaper consumable.
        Scenario s; Item& food = s.MakeItem(101, 5, ITEM_USAGE_USE); food.proto.Class = ITEM_CLASS_CONSUMABLE;
        Item& gear = s.MakeItem(102, 1, ITEM_USAGE_EQUIP); s.Offer(food, 1, 100); s.Offer(gear, 2, 900);
        assert(s.Visit()); assert(s.bot.session.buys == 1 && s.bot.session.lastAuction == 2 && s.bot.money == 9100);
    }
    {
        // Within a tier, the offer cheapest against its valuation wins.
        Scenario s; Item& plain = s.MakeItem(101, 1, ITEM_USAGE_EQUIP); Item& bargain = s.MakeItem(102, 1, ITEM_USAGE_EQUIP);
        bargain.proto.BuyPrice = 2000; s.Offer(plain, 1, 500); s.Offer(bargain, 2, 600);
        assert(s.Visit()); assert(s.bot.session.buys == 1 && s.bot.session.lastAuction == 2 && s.bot.money == 9400);
    }
    {
        // A bid-only auction ending before the next visits takes the start bid.
        Scenario s; Item& item = s.MakeItem(100, 1, ITEM_USAGE_EQUIP); AuctionEntry& offer = s.BidOffer(item);
        assert(s.Visit()); assert(s.bot.session.buys == 1 && s.bot.session.lastPrice == 400 && s.bot.money == 9600);
        assert(auctionMgr.house.GetAuction(1) == &offer && offer.bidder == s.bot.guid && offer.bid == 400);
        // The outstanding bid holds up further purchases.
        Item& other = s.MakeItem(101, 1, ITEM_USAGE_EQUIP); s.Offer(other, 2, 300);
        now += sPlayerbotAIConfig.earnedAuctionInterval; assert(!s.Visit()); assert(s.bot.session.buys == 1);
    }
    {
        // Another bot's lead is outbid by the core's increment, and its gold returns.
        Scenario s; Item& item = s.MakeItem(100, 1, ITEM_USAGE_EQUIP); AuctionEntry& offer = s.BidOffer(item);
        offer.bid = 500; offer.bidder = {777}; characterCache.accounts[offer.bidder] = 2;
        assert(s.Visit()); assert(s.bot.session.lastPrice == 525 && s.bot.money == 9475 && offer.bid == 525);
        assert(s.bot.session.refunds.size() == 1 && s.bot.session.refunds[0].second == 500);
    }
    {
        // An unaffordable buyout leaves a bid below it.
        Scenario s; Item& item = s.MakeItem(100, 1, ITEM_USAGE_EQUIP); AuctionEntry& offer = s.BidOffer(item);
        offer.buyout = 3000; assert(s.Visit()); assert(s.bot.session.lastPrice == 400 && offer.bidder == s.bot.guid);
    }
    {
        // The core refuses a buyout below the start bid, so none is sent.
        Scenario s; Item& item = s.MakeItem(100, 1, ITEM_USAGE_EQUIP); AuctionEntry& offer = s.Offer(item, 1, 300);
        offer.startbid = 400; assert(!s.Visit()); assert(!s.bot.session.buys && s.bot.money == 10000);
    }
    {
        // A bid-only auction outside its bid window needs no item evaluation.
        Scenario s; Item& item = s.MakeItem(100, 1, ITEM_USAGE_EQUIP);
        s.BidOffer(item, 400, 2 * sPlayerbotAIConfig.earnedAuctionInterval + 1);
        assert(!s.Visit()); assert(!s.bot.ai.context.usageLookups && !s.bot.session.buys);
    }
    for (int refusal = 0; refusal < 5; ++refusal)
    {
        // No bid on an auction ending later or one a player leads, nor one beyond
        // the valuation or budget; a bid the core refuses is no purchase.
        Scenario s; Item& item = s.MakeItem(100, 1, ITEM_USAGE_EQUIP); AuctionEntry& offer = s.BidOffer(item);
        switch (refusal)
        {
            case 0: offer.expire_time = now + 2 * sPlayerbotAIConfig.earnedAuctionInterval + 1; break;
            case 1: offer.bid = 500; offer.bidder = {778}; characterCache.accounts[offer.bidder] = 9; break;
            case 2: offer.startbid = 1001; break;
            case 3: s.bot.ai.context.budget.value = 399; break;
            case 4: s.bot.session.rejectBuy = true; break;
        }
        assert(!s.Visit()); assert(s.bot.session.buys == (refusal == 4 ? 1 : 0) && s.bot.money == 10000);
        assert(offer.bidder != s.bot.guid);
    }
    for (int refusal = 0; refusal < 5; ++refusal)
    {
        // Auction bags follow the vendor bag rules: a larger general bag replaces the
        // smallest general bag from a free backpack slot, once. A hunter's quiver rated
        // an upgrade could not hold the items of the bag it would replace.
        Scenario s; s.EquipBags(refusal == 1 ? ITEM_CLASS_QUIVER : ITEM_CLASS_CONTAINER);
        Item& bag = s.OfferBag(10);
        if (refusal == 2)
            for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
                s.BagItem(100, 1, ITEM_USAGE_KEEP);
        if (refusal == 3)
        {
            Item& upgrade = s.BagItem(102, 1, ITEM_USAGE_KEEP); upgrade.proto.Class = ITEM_CLASS_CONTAINER;
            upgrade.proto.ContainerSlots = 12; s.bot.ai.context.upgrades[102].value = ITEM_USAGE_EQUIP;
        }
        if (refusal == 4)
        {
            bag.proto.Class = ITEM_CLASS_QUIVER; bag.proto.SubClass = ITEM_SUBCLASS_QUIVER;
            bag.proto.InventoryType = INVTYPE_QUIVER;
        }
        assert(s.Visit() == !refusal); assert(s.bot.session.buys == (refusal ? 0 : 1));
    }
    {
        // A won bag waits in the mail until the backpack can take it, so it can be equipped.
        Scenario s;
        for (uint8 slot = INVENTORY_SLOT_ITEM_START; slot < INVENTORY_SLOT_ITEM_END; ++slot)
            s.BagItem(100, 1, ITEM_USAGE_KEEP);
        Item& bag = s.MakeItem(101, 1, ITEM_USAGE_EQUIP); bag.proto.Class = ITEM_CLASS_CONTAINER;
        bag.proto.InventoryType = INVTYPE_BAG; s.Receipt(&bag).subject = s.Subject(bag, AUCTION_WON);
        assert(!s.Visit(true)); assert(!s.bot.GetItemByGuid(bag.guid));
        s.bot.backpack.erase(INVENTORY_SLOT_ITEM_START); now += sPlayerbotAIConfig.earnedAuctionInterval;
        assert(s.Visit(true)); assert(s.bot.GetItemByGuid(bag.guid) == &bag);
    }
    {
        // A Blacksmith Hammer serves crafting.
        Scenario s; Item& hammer = s.MakeItem(5956, 1, ITEM_USAGE_SKILL); hammer.proto.Class = ITEM_CLASS_WEAPON;
        hammer.proto.SubClass = ITEM_SUBCLASS_WEAPON_MISC; hammer.proto.TotemCategory = 162; s.Offer(hammer);
        assert(!s.Visit()); assert(!s.bot.session.buys && s.bot.money == 10000);
    }
    {
        Scenario s; Item& pick = s.MakeItem(2901, 1, ITEM_USAGE_SKILL); pick.proto.Class = ITEM_CLASS_WEAPON;
        pick.proto.SubClass = ITEM_SUBCLASS_WEAPON_MISC; pick.proto.TotemCategory = 165; s.Offer(pick);
        assert(s.Visit()); assert(s.bot.session.buys == 1 && s.bot.money == 9500);
    }
    {
        // Natural upkeep has no disenchanting: a random bot sells outgrown bound gear.
        Scenario s; Item& gear = s.BagItem(100, 1, ITEM_USAGE_DISENCHANT); gear.bound = true;
        gear.proto.Quality = ITEM_QUALITY_UNCOMMON;
        assert(SellsToVendor(&s.bot.ai, &gear, ITEM_USAGE_DISENCHANT) && HasVendorSurplus(&s.bot.ai));
        s.bot.ai.master = true; assert(!HasVendorSurplus(&s.bot.ai)); s.bot.ai.master = false;
        s.bot.random = false; assert(!HasVendorSurplus(&s.bot.ai)); s.bot.random = true;
        // Only bound gear the bot can already wear is outgrown.
        gear.bound = false; assert(!HasVendorSurplus(&s.bot.ai)); gear.bound = true;
        gear.proto.RequiredLevel = 81; assert(!HasVendorSurplus(&s.bot.ai)); gear.proto.RequiredLevel = 80;
        assert(HasVendorSurplus(&s.bot.ai));
        // Vendors refuse gear without a price, which would hold a bot at the vendor.
        gear.proto.SellPrice = 0; assert(!HasVendorSurplus(&s.bot.ai)); gear.proto.SellPrice = 100;
        // As with disenchanting, a bot in a real guild keeps rare gear.
        s.bot.ai.realGuild = true; assert(HasVendorSurplus(&s.bot.ai));
        gear.proto.Quality = ITEM_QUALITY_RARE; assert(!HasVendorSurplus(&s.bot.ai));
        s.bot.ai.realGuild = false; assert(HasVendorSurplus(&s.bot.ai));
        sPlayerbotAIConfig.naturalProgression = false; assert(!SellsToVendor(&s.bot.ai, &gear, ITEM_USAGE_DISENCHANT));
        assert(SellsToVendor(nullptr, nullptr, ITEM_USAGE_VENDOR) && SellsToVendor(nullptr, nullptr, ITEM_USAGE_AH));
        assert(!SellsToVendor(nullptr, &gear, ITEM_USAGE_DISENCHANT) && !SellsToVendor(&s.bot.ai, &gear, ITEM_USAGE_EQUIP));
    }
    {
        // The parser reads the subjects the core writes.
        Scenario s; Item& item = s.MakeItem(2589, 20);
        auto subject = ParseAuctionSubject(s.Subject(item, AUCTION_EXPIRED));
        assert(subject && subject->item == 2589 && subject->response == AUCTION_EXPIRED && subject->auction == 7);
        assert(subject->count == 20);
    }
    {
        // Stock that keeps expiring unsold goes to a vendor instead of paying more deposits.
        Scenario s; Item& item = s.BagItem(100, 5);
        for (uint32 expiry = 0; expiry < MaxUnsoldListings; ++expiry)
        {
            assert(HasSurplus(&s.bot.ai) && ShouldReserveForAuction(&s.bot.ai, &item, ITEM_USAGE_AH));
            s.Unsold(item);
        }
        assert(!HasSurplus(&s.bot.ai) && !ShouldReserveForAuction(&s.bot.ai, &item, ITEM_USAGE_AH));
        assert(HasVendorSurplus(&s.bot.ai)); assert(!s.Visit());
        assert(s.bot.session.sells == int(MaxUnsoldListings) && s.bot.money == 10000 - 100 * MaxUnsoldListings);
        now += UnsoldMemorySeconds; assert(HasSurplus(&s.bot.ai)); // Forgotten after a week.
    }
    {
        // Stacks listed together return together and count as one unsold round.
        Scenario s; Item& first = s.BagItem(100, 5); Item& second = s.BagItem(100, 5);
        for (uint32 round = 0; round < MaxUnsoldListings; ++round)
        {
            assert(HasSurplus(&s.bot.ai));
            assert(s.Visit()); assert(!s.bot.GetItemByGuid(first.guid) && !s.bot.GetItemByGuid(second.guid));
            now += s.Listing();
            for (Item* stack : {&first, &second})
            {
                s.Receipt(stack).subject = s.Subject(*stack, AUCTION_EXPIRED);
                auctionMgr.items.erase(stack->guid);
            }
            assert(s.Visit(true)); assert(s.bot.GetItemByGuid(first.guid) && s.bot.GetItemByGuid(second.guid));
            now += sPlayerbotAIConfig.earnedAuctionInterval;
        }
        assert(!HasSurplus(&s.bot.ai));
    }
    {
        // A stack left in the mail counts with the round it returned in.
        Scenario s; Item& first = s.BagItem(100, 5); Item& second = s.BagItem(100, 5);
        assert(s.Visit()); now += s.Listing(); std::int64_t const returned = now;
        s.Receipt(&first).subject = s.Subject(first, AUCTION_EXPIRED); auctionMgr.items.erase(first.guid);
        assert(s.Visit(true)); now += s.Listing() + sPlayerbotAIConfig.earnedAuctionInterval;
        Mail& late = s.Receipt(&second); late.subject = s.Subject(second, AUCTION_EXPIRED);
        late.deliver_time = returned; auctionMgr.items.erase(second.guid);
        assert(s.Visit(true)); assert(s.bot.GetItemByGuid(second.guid) == &second && HasSurplus(&s.bot.ai));
    }
    {
        // Long Rate.Auction.Time listings still count both unsold rounds.
        Scenario s; world.timeRate = 14; Item& item = s.BagItem(100, 5);
        for (uint32 expiry = 0; expiry < MaxUnsoldListings; ++expiry)
        {
            assert(HasSurplus(&s.bot.ai));
            s.Unsold(item);
        }
        assert(!HasSurplus(&s.bot.ai));
        now += UnsoldMemorySeconds; assert(!HasSurplus(&s.bot.ai));
        now += 3 * s.Listing(); assert(HasSurplus(&s.bot.ai));
    }
    {
        // A sale shows demand and clears the record.
        Scenario s; Item& item = s.BagItem(100, 5);
        for (uint32 expiry = 0; expiry < MaxUnsoldListings; ++expiry)
            s.Unsold(item);
        assert(!HasSurplus(&s.bot.ai));
        s.Receipt(nullptr, 400).subject = s.Subject(item, AUCTION_SUCCESSFUL);
        assert(s.Visit(true)); assert(HasSurplus(&s.bot.ai) && s.bot.money == 10200);
    }
    {
        // A returned stack counts once, when it is actually taken back, however
        // long full bags leave it in the mail.
        Scenario s; Item& item = s.BagItem(100, 5);
        assert(s.Visit()); now += s.Listing(); Mail& mail = s.Receipt(&item);
        mail.subject = s.Subject(item, AUCTION_EXPIRED); mail.expire_time = now + 3 * s.Listing();
        auctionMgr.items.erase(item.guid); s.bot.session.rejectItem = true;
        assert(!s.Visit(true)); now += s.Listing(); assert(!s.Visit(true)); s.bot.session.rejectItem = false;
        now += sPlayerbotAIConfig.earnedAuctionInterval;
        assert(s.Visit(true)); assert(s.bot.GetItemByGuid(item.guid) == &item && HasSurplus(&s.bot.ai));
        now += sPlayerbotAIConfig.earnedAuctionInterval; s.Unsold(item); assert(!HasSurplus(&s.bot.ai));
    }
    {
        // Won purchases and unreadable receipts are no unsold stock.
        Scenario s; s.BagItem(100, 5);
        Item& bought = s.MakeItem(100, 2); s.Receipt(&bought).subject = s.Subject(bought, AUCTION_WON);
        assert(s.Visit(true)); now += s.Listing();
        Item& odd = s.MakeItem(100, 1); s.Receipt(&odd).subject = "100:0:3:7";
        assert(s.Visit(true)); assert(s.bot.inventory.size() == 3 && HasSurplus(&s.bot.ai));
        for (Item* item : {&bought, &odd}) assert(s.bot.GetItemByGuid(item->guid) == item);
    }
    for (int kind = 0; kind < 3; ++kind)
    {
        // Returned stock in the mailbox does not hold up purchases; won or unreadable mail does.
        Scenario s; Item& offer = s.MakeItem(101, 1, ITEM_USAGE_EQUIP); s.Offer(offer);
        Item& mailed = s.MakeItem(100); Mail& mail = s.Receipt(&mailed); mail.deliver_time = now + 10;
        mail.subject = kind == 0 ? s.Subject(mailed, AUCTION_EXPIRED) : kind == 1 ? s.Subject(mailed, AUCTION_WON) : "";
        assert(s.Visit() == (kind == 0)); assert(s.bot.session.buys == (kind == 0 ? 1 : 0));
    }
    {
        // A stack whose sale could not repay the deposit goes to the vendor.
        Scenario s; Item& cheap = s.BagItem(100, 1); cheap.proto.SellPrice = 5;
        assert(!HasSurplus(&s.bot.ai) && !ShouldReserveForAuction(&s.bot.ai, &cheap, ITEM_USAGE_AH));
        assert(HasVendorSurplus(&s.bot.ai)); assert(!s.Visit()); assert(!s.bot.session.sells);
        cheap.count = 20; cheap.proto.SellPrice = 6;
        assert(HasSurplus(&s.bot.ai) && ShouldReserveForAuction(&s.bot.ai, &cheap, ITEM_USAGE_AH));
    }
    {
        // The house cut counts against the sale.
        Scenario s; s.BagItem(100, 5); world.cutRate = 30;
        assert(!HasSurplus(&s.bot.ai)); assert(!s.Visit()); assert(!s.bot.session.sells && s.bot.money == 10000);
    }
    {
        // Undercutting just above the floor at this house would not repay the deposit.
        Scenario s; Item& item = s.BagItem(100, 1); Item& rival = s.MakeItem(100, 1); s.Offer(rival, 1, 201);
        assert(HasSurplus(&s.bot.ai)); assert(!s.Visit()); assert(!s.bot.session.sells);
        auctionMgr.house.GetAuction(1)->buyout = 211; now += sPlayerbotAIConfig.earnedAuctionInterval;
        assert(s.Visit()); assert(s.bot.session.lastItem == item.guid && s.bot.session.lastPrice == 210);
    }
    {
        // A market already at twice the vendor price is left alone, and the vendor takes the stack.
        Scenario s; Item& item = s.BagItem(100, 5); Item& rival = s.MakeItem(100, 5); s.Offer(rival, 1, 1000);
        assert(!s.Visit()); assert(!s.bot.session.sells && HasSurplus(&s.bot.ai));
        now += sPlayerbotAIConfig.earnedAuctionInterval; assert(!s.Visit());
        assert(!HasSurplus(&s.bot.ai) && !ShouldReserveForAuction(&s.bot.ai, &item, ITEM_USAGE_AH));
        assert(HasVendorSurplus(&s.bot.ai));
    }
    {
        // Several stacks of one item refused in a visit count once.
        Scenario s; s.BagItem(100, 5); s.BagItem(100, 5); Item& rival = s.MakeItem(100, 5); s.Offer(rival, 1, 1000);
        assert(!s.Visit()); assert(HasSurplus(&s.bot.ai));
    }
    {
        // The bot's own and same-account listings are no competition to undercut.
        Scenario s; Item& item = s.BagItem(100, 1); Item& own = s.MakeItem(100, 1); Item& sibling = s.MakeItem(100, 1);
        s.Offer(own, 1, 250, s.bot.guid.value, s.bot.session.account);
        s.Offer(sibling, 2, 260, 556, s.bot.session.account);
        assert(s.Visit()); assert(s.bot.session.lastItem == item.guid && s.bot.session.lastPrice == 300);
    }
    {
        // Prices come from the whole house, not only the sampled slice.
        Scenario s; Item& item = s.BagItem(100, 1); Item& filler = s.MakeItem(101, 1); Item& rival = s.MakeItem(100, 1);
        for (uint32 id = 1; id <= 3 * MaxMarketScan; ++id) s.Offer(filler, id, 500);
        std::vector<uint32> const sample = SampleMarket(&auctionMgr.house, s.bot.guid);
        uint32 outside = MaxMarketScan + 1;
        while (std::find(sample.begin(), sample.end(), outside) != sample.end()) ++outside;
        s.Offer(rival, outside, 280);
        assert(s.Visit()); assert(s.bot.session.lastItem == item.guid && s.bot.session.lastPrice == 279);
    }
    {
        // A bot keeps at most two live listings of one item.
        Scenario s; Item& item = s.BagItem(100, 1); Item& other = s.BagItem(101, 1);
        for (uint32 id = 1; id <= MaxSameItemListings; ++id)
        { Item& listed = s.MakeItem(100, 1); s.Offer(listed, id, 300, s.bot.guid.value, s.bot.session.account); }
        assert(s.Visit()); assert(s.bot.session.sells == 1 && s.bot.session.lastItem == other.guid);
        assert(s.bot.GetItemByGuid(item.guid) == &item);
    }
    {
        // Listings made in the visit count towards the cap.
        Scenario s; Item& listed = s.MakeItem(100, 1); s.Offer(listed, 1, 300, s.bot.guid.value, s.bot.session.account);
        s.BagItem(100, 1); Item& second = s.BagItem(100, 1);
        assert(s.Visit()); assert(s.bot.session.sells == 1 && s.bot.GetItemByGuid(second.guid) == &second);
    }
    {
        // Purchases value vendor bundles per item: 200 arrows sell for 10 copper.
        for (uint32 price : {10u, 11u})
        {
            Scenario s; Item& arrows = s.MakeItem(100, 200, ITEM_USAGE_AMMO);
            arrows.proto.BuyPrice = 10; arrows.proto.BuyCount = 200; arrows.proto.SellPrice = 0; s.Offer(arrows, 1, price);
            assert(s.Visit() == (price == 10)); assert(s.bot.session.buys == (price == 10 ? 1 : 0));
        }
    }
    assert(!ShouldReserveForAuction(nullptr, nullptr, ITEM_USAGE_AH));
    std::cout << "Earned auctions: production policy/service, conserved inventory/gold, safe receipts, queued revalidation, travel selection and bounded protection scans passed\n";
}
int main() { PolicyTests(); TravelTests(); ServiceTests(); }
'''


production = {
    # Keep the complete production service; fixtures replace only its includes/core
    # dependencies. Policy remains the actual header included from the prepared module.
    'service': '\n'.join(line for line in (module / 'EarnedAuction.cpp').read_text().splitlines()
                          if not line.lstrip().startswith('#include')),
    'profession': function(values_source, 'bool IsProfessionSpell(uint32 spellId)'),
    # The vendor bag rules, which auction bag purchases share.
    'bags': '\n'.join([re.search(r'namespace\n\{\n.*?\n\}  // namespace', values_source, re.DOTALL).group(0),
                       function(values_source, 'bool BagPurchaseUseful(PlayerbotAI* botAI, ItemTemplate const* proto)')]),
    'policy': (module / 'EarnedAuctionPolicy.h').read_text(),
    'travel': (travel_module / 'EarnedAuctionTravelPolicy.h').read_text(),
}


tools = tool_rows()


def build(directory, parts, name):
    text = fixtures.replace('@@NATIVE@@', native).replace('@@PROFESSIONS@@', profession_skills(args.core))
    text = text.replace('@@PROFESSION@@', parts['profession']).replace('@@SUBJECT@@', subject_writer)
    text = text.replace('@@BAGS@@', parts['bags'])
    text = text.replace('@@AUCTIONRULES@@', auction_rules).replace('@@TOOLS@@', tools)
    # The policy headers are compiled from private copies, so mutants can change them.
    headers = Path(directory) / name
    headers.mkdir()
    (headers / 'EarnedAuctionPolicy.h').write_text(parts['policy'])
    (headers / 'EarnedAuctionTravelPolicy.h').write_text(parts['travel'])
    target = Path(directory) / (name + '.cpp')
    executable = Path(directory) / (name + '.bin')
    target.write_text(text + parts['service'] + policy_tests + service_tests)
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror',
                    *SANITIZER_FLAGS, '-no-pie',
                    '-g', '-I', str(headers), '-I', str(module), '-I', str(travel_module),
                    str(target), '-o', str(executable)], check=True)
    return run_fixture([str(executable)], name)


mutations = [
    ('auction trading for a bot a player owns', 'service',
     'sRandomPlayerbotMgr.IsRandomBot(ai->GetBot()) && !ai->HasGameClientMaster();\n}\n\nbool HasSurplus',
     '!ai->HasGameClientMaster();\n}\n\nbool HasSurplus'),
    ('auction trading with a game-client master', 'service',
     'sRandomPlayerbotMgr.IsRandomBot(ai->GetBot()) && !ai->HasGameClientMaster();\n}\n\nbool HasSurplus',
     'sRandomPlayerbotMgr.IsRandomBot(ai->GetBot());\n}\n\nbool HasSurplus'),
    ('visit during combat', 'service', 'bot->IsAlive() && !bot->IsInCombat() && ', 'bot->IsAlive() && '),
    ('visit cooldown skipped', 'service', 'now - it->second < interval)', 'now - it->second < interval * 0)'),
    ('soulbound items listed', 'service', 'item->IsSoulBound() || ', ''),
    ('quest objectives sold', 'service', 'if (supplies.NeededForQuest(item))\n        return true;', ''),
    ('listings beyond the cap', 'service', 'if (listed >= MaxSalesPerVisit || listings >= MaxListings)',
     'if (listed >= MaxSalesPerVisit)'),
    ('deposit above the budget', 'service', 'deposit > budget || ', 'deposit > (budget | MaxCopper) || '),
    ('same-account auctions bought', 'service', 'if (!ownerAccount || ownerAccount == bot->GetSession()->GetAccountId())',
     'if (!ownerAccount)'),
    ('buyout below the start bid sent', 'service',
     ' || (auction->buyout && auction->buyout < auction->startbid) ||\n            (!auction->buyout',
     ' ||\n            (!auction->buyout'),
    ('bid-only auctions evaluated early', 'service',
     ' ||\n            (!auction->buyout && !BidWindow(auction->expire_time - now, VisitInterval())))', ')'),
    ('bid beyond the next visits', 'policy', 'timeLeft <= 2 * std::int64_t(interval)',
     'timeLeft <= 4 * std::int64_t(interval)'),
    ('bid on an ended auction', 'policy', 'return timeLeft > 0 && ', 'return '),
    ('bid below the increment', 'policy', 'std::uint64_t(bid) + increment', 'std::uint64_t(bid) + increment * 0 + 1'),
    ('bid above the minimum', 'policy', 'std::uint64_t(bid) + increment : startbid',
     'std::uint64_t(bid) + increment : startbid + 1'),
    ('player lead outbid', 'service', '(auction->bidder && !BotBidder(auction->bidder))',
     '(auction->bidder && !BotBidder(auction->bidder) && false)'),
    ('bid without a valuation', 'service',
     ('(auction->bid));\n'
      '            if (!Affordable(price, budget, bot->GetMoney()) || !WithinPriceCeiling(price, ceiling))'),
     ('(auction->bid));\n'
      '            if (!Affordable(price, budget | MaxCopper, bot->GetMoney()) ||\n'
      '                !WithinPriceCeiling(price, ceiling | MaxCopper))')),
    ('refused bid reported', 'service', 'return placed ? placed->bidder == bot->GetGUID() : ', 'return placed ? true : '),
    ('purchase above the budget', 'service', 'Affordable(auction->buyout, budget, bot->GetMoney())',
     'Affordable(auction->buyout, budget | MaxCopper, bot->GetMoney())'),
    ('purchase without bag space', 'service',
     ('if (bot->CanStoreItem(NULL_BAG, NULL_SLOT, destination, item, false) != EQUIP_ERR_OK)\n            continue;\n'
      '        OfferRank'), 'OfferRank'),
    ('purchase while one is pending', 'service', 'bool const bought = !state.pendingPurchase && ', 'bool const bought = '),
    ('receipt deleted with attachments', 'service', 'if (AuctionReceipt(mail, now) && !mail->money && mail->items.empty())',
     'if (AuctionReceipt(mail, now))'),
    ('recipe reagents protected', 'service', '(!_crafts && IsProfessionSpell(spellId))', '(!_crafts && false)'),
    ('SelfBot recipe reagents sold', 'service',
     'return !sRandomPlayerbotMgr.IsRandomBot(ai->GetBot()) || ai->HasGameClientMaster();',
     'return !sRandomPlayerbotMgr.IsRandomBot(ai->GetBot());'),
    ('altbot recipe reagents sold', 'service',
     'return !sRandomPlayerbotMgr.IsRandomBot(ai->GetBot()) || ai->HasGameClientMaster();',
     'return ai->HasGameClientMaster();'),
    ('auction bags skip the bag rules', 'service',
     ('        if ((proto->Class == ITEM_CLASS_CONTAINER || proto->Class == ITEM_CLASS_QUIVER) &&\n'
      '            !BagPurchaseUseful(ai, proto))\n            continue;\n'), ''),
    ('quivers skip the bag rules', 'service', ' || proto->Class == ITEM_CLASS_QUIVER)', ')'),
    ('quivers bought as bags', 'bags', 'return IsGeneralBag(proto) && ReplaceableBagSize(',
     'return (IsGeneralBag(proto) || true) && ReplaceableBagSize('),
    ('won bag stored in a bag', 'service', '? uint8(INVENTORY_SLOT_BAG_0) : uint8(NULL_BAG)',
     '? uint8(NULL_BAG) : uint8(NULL_BAG)'),
    ('second bag upgrade bought', 'bags', '!CarriesBagUpgrade(botAI, replaceable)',
     '(!CarriesBagUpgrade(botAI, replaceable) || true)'),
    ('profession materials bought', 'service', 'else if (usage == ITEM_USAGE_SKILL && GatheringTool(proto))',
     'else if (usage == ITEM_USAGE_SKILL)'),
    ('usage tiers ignored', 'service', 'RankOffer(tier, price, ceiling)', 'RankOffer(tier * 0, price, ceiling)'),
    ('offers ranked by absolute price', 'service', 'RankOffer(tier, price, ceiling)',
     'RankOffer(tier, price, ceiling * 0 + 1)'),
    ('auction level ignored at the auctioneer', 'service', 'else if (MeetsAuctionLevel(bot))',
     'else if (MeetsAuctionLevel(bot) || true)'),
    ('auction level ignored when queuing', 'service', ' || (!mailbox && !MeetsAuctionLevel(ai->GetBot()))', ''),
    ('travel below the auction level', 'travel', 'std::max(MinimumLevel, auctionLevel)',
     'std::max(MinimumLevel, auctionLevel * 0)'),
    ('crafting tools bought', 'service', '        default:\n            return false;\n    }\n}\n\nuint32 VisitInterval',
     '        default:\n            return true;\n    }\n}\n\nuint32 VisitInterval'),
    ('fishing poles refused', 'service',
     ('    if (proto->Class == ITEM_CLASS_WEAPON && proto->SubClass == ITEM_SUBCLASS_WEAPON_FISHING_POLE)\n'
      '        return true;\n'), ''),
    ('multi-tools refused', 'service', '        case 161:  // Gnomish Army Knife\n', ''),
    ('bound gear vendored outside natural progression', 'service',
     'sPlayerbotAIConfig.naturalProgression && ai && ai->GetBot() &&\n', 'ai && ai->GetBot() &&\n'),
    ('bound gear vendored for a bot a player owns', 'service',
     '->GetLevel() && sRandomPlayerbotMgr.IsRandomBot(ai->GetBot()) &&', '->GetLevel() &&'),
    ('bound gear vendored with a game-client master', 'service',
     '!ai->HasGameClientMaster() && (proto->Quality', '(proto->Quality'),
    ('unbound gear vendored', 'service', ' && item->IsSoulBound() &&', ' &&'),
    ('gear the bot cannot wear vendored', 'service', 'proto->RequiredLevel <= ai->GetBot()->GetLevel() && ', ''),
    ('stock reserved below the auction level', 'service', ' || !MeetsAuctionLevel(ai->GetBot()) || !CanList(ai, item))',
     ' || !CanList(ai, item))'),
    ('returned stacks counted apart', 'service', 'Unsold().Record(stock, returned, ListingSeconds(), ListingSeconds());',
     'Unsold().Record(stock, returned, 0, ListingSeconds());'),
    ('returns timed at collection', 'service', 'Unsold().Record(stock, returned, ',
     'Unsold().Record(stock, now + 0 * returned, '),
    ('unpriced gear vendored', 'service', 'proto && proto->SellPrice && ', 'proto && '),
    ('rare gear of a real guild vendored', 'service', '|| !ai->IsInRealGuild())', '|| !ai->IsInRealGuild() || true)'),
    ('uncommon gear of a real guild kept', 'service', 'proto->Quality <= ITEM_QUALITY_UNCOMMON',
     'proto->Quality < ITEM_QUALITY_UNCOMMON'),
    ('profession test without the skill line', 'profession', 'IsProfessionSkill(it->second->SkillLine)', 'true'),
    ('unsold stock listed again', 'service', 'return CanList(ai, item) && RelistAllowed(ai, item) && ',
     'return CanList(ai, item) && '),
    ('unsold stock kept from the vendor', 'service', '    if (!RelistAllowed(ai, item))\n        return false;\n', ''),
    ('every receipt counted as unsold', 'service',
     'bool const expired = subject && subject->response == AUCTION_EXPIRED;', 'bool const expired = true;'),
    ('sale keeps the unsold record', 'service', 'Unsold().Sold(bot->GetGUID().GetCounter(), subject->item);',
     'Unsold().Sold(0, subject->item);'),
    ('returned stock holds up purchases', 'service', 'if (!subject || subject->response == AUCTION_WON)',
     'if (!subject || subject->response == AUCTION_WON || subject)'),
    ('unsold record never forgotten', 'policy',
     'return record.unsold < MaxUnsoldListings || UnsoldForgotten(record, now, listing);',
     'return record.unsold < MaxUnsoldListings || (UnsoldForgotten(record, now, listing) && false);'),
    ('stacks of one round counted apart', 'policy', 'now - record.last < round)', 'now - record.last < round * 0)'),
    ('memory shorter than long listings', 'policy', 'UnsoldMemorySeconds, 3 * listing)', 'UnsoldMemorySeconds, 0 * listing)'),
    ('listing duration without Rate.Auction.Time', 'service', '* sWorld->getRate(RATE_AUCTION_TIME);',
     '* (sWorld->getRate(RATE_AUCTION_TIME) * 0 + 1);'),
    ('refusals wait for a listing round', 'service', 'Unsold().Record(StockKey(bot, item), now, 0, ListingSeconds());',
     'Unsold().Record(StockKey(bot, item), now, ListingSeconds(), ListingSeconds());'),
    ('subject with a second field accepted', 'policy', '    if (fields[1])\n        return {};\n', ''),
    ('partial subject field accepted', 'policy', 'parsed != last', 'false'),
    ('listing that cannot repay its deposit', 'service',
     '        if (!prices.buyout ||\n            !WorthListing(prices.buyout, SaleCut(entry, prices.buyout), uint64(proto->SellPrice) * count, deposit))',
     '        if (!prices.buyout)'),
    ('stock that cannot repay a deposit kept', 'service',
     'return CanList(ai, item) && RelistAllowed(ai, item) && Listable(item) && ',
     'return CanList(ai, item) && RelistAllowed(ai, item) && '),
    ('stock that cannot repay a deposit reserved', 'service', '    if (!Listable(item))\n        return false;\n', ''),
    ('house cut ignored', 'service', 'return sale.GetAuctionCut();', 'return 0 * sale.GetAuctionCut();'),
    ('listing below twice the vendor price', 'policy', 'buyout < floor || ', 'buyout < floor * 0 || '),
    ('refusal not counted', 'service',
     '            if (refused.insert(Stock(item)).second)\n                Unsold().Record(StockKey(bot, item), now, 0, ListingSeconds());',
     '            if (refused.insert(Stock(item)).second)\n                Unsold().Allowed(StockKey(bot, item), now, ListingSeconds());'),
    ('refusals counted per stack', 'service', 'if (refused.insert(Stock(item)).second)', 'if (refused.insert(Stock(item)).second || true)'),
    ('same-account listings undercut', 'service',
     'if (!ownerAccount || ownerAccount == bot->GetSession()->GetAccountId() || !offer || !unit)',
     'if (!ownerAccount || !offer || !unit)'),
    ('only the start of the house priced', 'service',
     'if (!carried.contains(auction->item_template) || auction->expire_time <= now',
     'if (!carried.contains(auction->item_template) || id > MaxMarketScan || auction->expire_time <= now'),
    ('same-item listing cap ignored', 'service', ' || listingsByItem[Stock(item)] >= MaxSameItemListings', ''),
    ('listings in a visit not counted per item', 'service', '++listingsByItem[stock];', 'listingsByItem[stock] += 0;'),
    ('vendor bundle valued per bundle', 'policy', 'std::uint64_t const bundle = std::max<std::uint32_t>(buyCount, 1);',
     'std::uint64_t const bundle = std::max<std::uint32_t>(buyCount, 1) * 0 + 1;'),
]

with tempfile.TemporaryDirectory(prefix='portable-earned-auctions-') as temporary:
    result = build(temporary, production, 'auctions')
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit(f'Earned auctions fixture failed (exit {result.returncode})')

    def rejected(numbered):
        index, (label, key, old, new) = numbered
        mutated = {**production, key: production[key].replace(old, new)}
        if mutated[key] == production[key]:
            raise SystemExit(f'{label} mutation was not applied')
        return build(temporary, mutated, f'mutant-{index}').returncode != 0

    for (label, *_), result in zip(mutations, in_parallel(rejected, enumerate(mutations))):
        if not result:
            raise SystemExit(f'Earned auctions fixture did not reject: {label}')
        print(f'Earned auctions mutation rejected: {label}')
