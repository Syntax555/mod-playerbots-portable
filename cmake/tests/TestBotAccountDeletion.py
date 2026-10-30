"""Exercise the auction settlement that runs before the random bot accounts are deleted.

Playerbots.DeleteRandomBotAccounts removes the bots' characters and items with
SQL, and the core then drops their auctions at the next startup without
returning the high bid. The production settlement runs against auction house,
character cache and transaction doubles that follow the native contracts
checked below: each bot listing is removed with its item, a player bidder is
refunded by the native cancellation mail, and player listings stay untouched.
"""

import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    TIMEOUT,
    cxx,
    function,
    prepared_core,
    reject_mutants,
    source_argument,
)


STUBS = r'''
#include <cassert>
#include <cstdint>
#include <initializer_list>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <unordered_set>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
template <class... Arguments> void LogInfo(char const*, Arguments const&...) {}
#define LOG_INFO(filter, ...) LogInfo(__VA_ARGS__)
@HOUSES@;

struct ObjectGuid
{
    uint32 counter = 0;
    operator bool() const { return counter != 0; }
    bool operator<(ObjectGuid const& other) const { return counter < other.counter; }
};

struct Transaction { std::vector<std::string> statements; };
using CharacterDatabaseTransaction = std::shared_ptr<Transaction>;
struct CharacterDatabaseDouble
{
    std::vector<std::string> committed;
    int commits = 0;
    CharacterDatabaseTransaction BeginTransaction() { return std::make_shared<Transaction>(); }
    void DirectCommitTransaction(CharacterDatabaseTransaction& trans)
    {
        ++commits;
        committed.insert(committed.end(), trans->statements.begin(), trans->statements.end());
    }
} CharacterDatabase;

// Unknown characters have account 0, as in the native cache.
struct CharacterCache
{
    std::map<uint32, uint32> accounts;
    uint32 GetCharacterAccountIdByGuid(ObjectGuid guid) const
    {
        auto itr = accounts.find(guid.counter);
        return itr == accounts.end() ? 0 : itr->second;
    }
} characterCache;
CharacterCache* sCharacterCache = &characterCache;

struct AuctionEntry
{
    uint32 Id = 0;
    ObjectGuid item_guid, owner, bidder;
    uint32 bid = 0;
    void DeleteFromDB(CharacterDatabaseTransaction trans) const
    {
        trans->statements.push_back("delete auction " + std::to_string(Id));
    }
};

// Removing an auction erases and frees the entry, as the native house does.
struct AuctionHouseObject
{
    typedef std::map<uint32, AuctionEntry*> AuctionEntryMap;
    AuctionEntryMap auctions;
    AuctionEntryMap::iterator GetAuctionsBegin() { return auctions.begin(); }
    AuctionEntryMap::iterator GetAuctionsEnd() { return auctions.end(); }
    bool RemoveAuction(AuctionEntry* auction)
    {
        bool wasInMap = auctions.erase(auction->Id);
        delete auction;
        return wasInMap;
    }
    ~AuctionHouseObject() { for (auto& auction : auctions) delete auction.second; }
};

struct AuctionHouseMgr
{
    std::map<AuctionHouseId, AuctionHouseObject> houses;
    std::set<uint32> items;
    AuctionHouseObject* GetAuctionsMapByHouseId(AuctionHouseId houseId) { return &houses[houseId]; }
    // The native mail returns the bid to a bidder whose character still exists.
    void SendAuctionCancelledToBidderMail(AuctionEntry* auction, CharacterDatabaseTransaction trans, bool sendMail = true)
    {
        assert(sendMail);
        if (sCharacterCache->GetCharacterAccountIdByGuid(auction->bidder))
            trans->statements.push_back("refund " + std::to_string(auction->bid) + " to " +
                                        std::to_string(auction->bidder.counter));
    }
    bool RemoveAItem(ObjectGuid itemGuid, bool deleteFromDB = false, CharacterDatabaseTransaction* trans = nullptr)
    {
        if (!items.erase(itemGuid.counter))
            return false;
        if (deleteFromDB)
        {
            assert(trans);
            (*trans)->statements.push_back("delete item " + std::to_string(itemGuid.counter));
        }
        return true;
    }
} auctionMgr;
AuctionHouseMgr* sAuctionMgr = &auctionMgr;
'''

HARNESS = r'''
enum : uint32 { PLAYER = 1, OTHER_PLAYER = 2, BOT = 10, OTHER_BOT = 11, DELETED = 99 };

void List(AuctionHouseId house, uint32 id, uint32 owner, uint32 bidder, uint32 bid)
{
    auctionMgr.items.insert(1000 + id);
    auctionMgr.houses[house].auctions[id] = new AuctionEntry{id, {1000 + id}, {owner}, {bidder}, bid};
}

std::set<uint32> Listed()
{
    std::set<uint32> ids;
    for (auto& house : auctionMgr.houses)
        for (auto& auction : house.second.auctions)
            ids.insert(auction.first);
    return ids;
}

int main()
{
    characterCache.accounts = {{PLAYER, 1}, {OTHER_PLAYER, 2}, {BOT, 100}, {OTHER_BOT, 101}};
    // Neighbouring bot listings check that removal keeps the iteration valid.
    List(AuctionHouseId::Alliance, 1, BOT, PLAYER, 500);
    List(AuctionHouseId::Alliance, 2, OTHER_BOT, OTHER_PLAYER, 300);
    List(AuctionHouseId::Alliance, 3, OTHER_PLAYER, BOT, 700);
    List(AuctionHouseId::Horde, 4, OTHER_BOT, 0, 0);
    List(AuctionHouseId::Horde, 5, PLAYER, 0, 0);
    List(AuctionHouseId::Neutral, 6, BOT, OTHER_BOT, 900);
    List(AuctionHouseId::Neutral, 7, BOT, DELETED, 100);

    SettleDeletedBotAuctions(std::unordered_set<uint32>{100, 101});

    assert(CharacterDatabase.commits == 1);
    std::multiset<std::string> statements(CharacterDatabase.committed.begin(), CharacterDatabase.committed.end());
    std::multiset<std::string> expected{
        "refund 500 to 1", "refund 300 to 2",
        "delete auction 1", "delete auction 2", "delete auction 4", "delete auction 6", "delete auction 7",
        "delete item 1001", "delete item 1002", "delete item 1004", "delete item 1006", "delete item 1007"};
    for (std::string const& statement : statements)
        std::cout << statement << '\n';
    assert(statements == expected);
    // Player listings keep their items and bids, including a bot's binding bid.
    assert((Listed() == std::set<uint32>{3, 5}));
    assert((auctionMgr.items == std::set<uint32>{1003, 1005}));
    assert(auctionMgr.houses[AuctionHouseId::Alliance].auctions[3]->bid == 700);
    std::cout << "PASS: deleted bots' listings are removed and player bids refunded\n";
}
'''


def native_contracts(core, playerbots):
    """The core behaviour the doubles mirror, and the startup order the settlement relies on."""
    game = core/'src/server/game'
    header = (game/'AuctionHouse/AuctionHouseMgr.h').read_text()
    houses = function(header, 'enum class AuctionHouseId')
    assert re.findall(r'(\w+)\s*=\s*(\d+)', houses) == [('Alliance', '2'), ('Horde', '6'), ('Neutral', '7')]
    assert '#define MAX_AUCTION_HOUSE_FACTIONS 3' in header
    for declaration in (
            'typedef std::map<uint32, AuctionEntry*> AuctionEntryMap;',
            'AuctionEntryMap::iterator GetAuctionsBegin() { return _auctionsMap.begin(); }',
            'AuctionHouseObject* GetAuctionsMapByHouseId(AuctionHouseId auctionHouseId);',
            'void SendAuctionCancelledToBidderMail(AuctionEntry* auction, CharacterDatabaseTransaction trans, bool sendMail = true);',
            'bool RemoveAItem(ObjectGuid itemGuid, bool deleteFromDB = false, CharacterDatabaseTransaction* trans = nullptr);'):
        assert declaration in header, declaration
    manager = (game/'AuctionHouse/AuctionHouseMgr.cpp').read_text()
    cancelled = function(manager, 'void AuctionHouseMgr::SendAuctionCancelledToBidderMail(')
    assert 'bidder_accId = sCharacterCache->GetCharacterAccountIdByGuid(auction->bidder);' in cancelled
    assert '.AddMoney(auction->bid)' in cancelled
    removal = function(manager, 'bool AuctionHouseMgr::RemoveAItem(')
    assert removal.index('ASSERT(trans);') < removal.index('FSetState(ITEM_REMOVED);') < removal.index('SaveToDB(*trans);')
    remove_auction = function(manager, 'bool AuctionHouseObject::RemoveAuction(')
    assert '_auctionsMap.erase(auction->Id);' in remove_auction and 'delete auction;' in remove_auction
    assert 'trans->Append(stmt);' in function(manager, 'void AuctionEntry::DeleteFromDB(')
    # A listing whose item is gone is dropped at startup without a refund.
    loader = function(manager, 'bool AuctionEntry::LoadFromDB(')
    assert loader.index('if (!sAuctionMgr->GetAItem(item_guid))') < loader.rindex('return false;')
    assert 'SendAuction' not in function(manager, 'void AuctionHouseMgr::LoadAuctions()')
    item = function((game/'Entities/Item/Item.cpp').read_text(), 'void Item::SaveToDB(')
    removed = item[item.index('case ITEM_REMOVED:'):]
    assert removed.index('CHAR_DEL_ITEM_INSTANCE') < removed.index('delete this;')
    cache = function((game/'Cache/CharacterCache.cpp').read_text(), 'uint32 CharacterCache::GetCharacterAccountIdByGuid(')
    assert 'return 0;' in cache
    pool = (core/'src/server/database/Database/DatabaseWorkerPool.h').read_text()
    assert 'void DirectCommitTransaction(SQLTransaction<T>& transaction);' in pool
    # The deletion runs from Playerbots' config load, after the auctions and the
    # character cache are in memory.
    world = (game/'World/World.cpp').read_text()
    assert (world.index('sCharacterCache->LoadCharacterCacheStorage();') < world.index('sAuctionMgr->LoadAuctions();')
            < world.index('sScriptMgr->OnBeforeWorldInitialized();'))
    hook = function((playerbots/'Script/Playerbots.cpp').read_text(), 'void OnBeforeWorldInitialized() override')
    assert 'sPlayerbotAIConfig.Initialize();' in hook
    config = function((playerbots/'PlayerbotAIConfig.cpp').read_text(), 'bool PlayerbotAIConfig::Initialize()')
    assert 'RandomPlayerbotFactory::CreateRandomBots();' in config
    return houses + ';'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source_argument(parser, help='prepared Playerbots src directory')
    source_argument(parser, 'core', help='prepared core source directory')
    args = parser.parse_args()
    core = args.core or prepared_core(Path(__file__).resolve().parents[2])
    playerbots = args.source or core/'modules/mod-playerbots/src'
    houses = native_contracts(core, playerbots)
    factory = (playerbots/'Bot/Factory/RandomPlayerbotFactory.cpp').read_text()
    settlement = function(factory, 'static void SettleDeletedBotAuctions(')
    deletion = function(factory, 'void RandomPlayerbotFactory::CreateRandomBots()')
    deletion = function(deletion, '    if (sPlayerbotAIConfig.DeleteRandomBotAccounts)')
    # Every bot listing is settled before the characters and their items go.
    assert (deletion.index('botAccounts.push_back(') < deletion.index(
        'SettleDeletedBotAuctions(std::unordered_set<uint32>(botAccounts.begin(), botAccounts.end()));')
        < deletion.index('DELETE FROM characters WHERE account IN') < deletion.index('DELETE FROM item_instance'))
    assert deletion.index('SettleDeletedBotAuctions(') < deletion.index('World::StopNow(')

    compiler = cxx()
    with tempfile.TemporaryDirectory(prefix='bot-account-deletion-') as temporary:
        work = Path(temporary)
        (work/'fixture.cpp').write_text(STUBS.replace('@HOUSES@', houses.rstrip(';')) + settlement + HARNESS)
        flags = ['-std=c++20', '-O1', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter']
        if os.name != 'nt':
            flags += [*SANITIZER_FLAGS, '-no-pie']

        def build(directory, executable):
            return [compiler, *flags, str(directory/'fixture.cpp'), '-o', str(executable)]

        executable = work/('fixture.exe' if os.name == 'nt' else 'fixture')
        subprocess.run(build(work, executable), check=True)
        subprocess.run([str(executable)], check=True, timeout=TIMEOUT)
        reject_mutants(work, [
            ('bids kept', 'fixture.cpp', 'sAuctionMgr->SendAuctionCancelledToBidderMail(auction, trans);', ''),
            ('bot bidders refunded', 'fixture.cpp', 'if (bidderAccount && !botAccounts.count(bidderAccount))',
             'if (bidderAccount)'),
            ('player listings removed', 'fixture.cpp',
             'if (!botAccounts.count(sCharacterCache->GetCharacterAccountIdByGuid(auction->owner)))', 'if (false)'),
            ('one auction house', 'fixture.cpp',
             '{AuctionHouseId::Alliance, AuctionHouseId::Horde, AuctionHouseId::Neutral}', '{AuctionHouseId::Alliance}'),
            ('auction row kept', 'fixture.cpp', 'auction->DeleteFromDB(trans);', ''),
            ('item kept', 'fixture.cpp', 'sAuctionMgr->RemoveAItem(auction->item_guid, true, &trans);', ''),
            ('uncommitted', 'fixture.cpp', 'CharacterDatabase.DirectCommitTransaction(trans);', ''),
        ], build, 'Bot account deletion')


if __name__ == '__main__':
    main()
