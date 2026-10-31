"""Queue, save and destroy items with the native item update queue methods.

The production Item::SetState, AddToUpdateQueueOf and RemoveFromUpdateQueueOf
run against Item, Player and ObjectAccessor doubles. A save outside the inventory
save marks an item unchanged; a later change and destruction must leave a single
queued entry, so the native save loop deletes it once. Mutations revert the
recorded fork change and keep the stale entry.
"""

import argparse
from pathlib import Path
import re
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    cxx,
    fork_change,
    function,
    git_apply,
    prepared_core,
    reject_mutants,
    run_fixture,
    source_argument,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, default=prepared_core(), help='prepared core directory')
core = parser.parse_args().source
relative = 'src/server/game/Entities/Item/Item.cpp'
item_source = (core / relative).read_text()
header = (core / 'src/server/game/Entities/Item/Item.h').read_text()
signatures = ('void Item::SetState(ItemUpdateState state, Player* forplayer)',
              'void Item::AddToUpdateQueueOf(Player* player)',
              'void Item::RemoveFromUpdateQueueOf(Player* player)')
production = '\n'.join(function(item_source, signature) for signature in signatures)

# Native contracts the doubles rely on: queue membership is the position, owners are
# found through ObjectAccessor, SaveToDB marks a saved item unchanged without a
# player and deletes a removed one, and the inventory save skips empty slots.
assert '[[nodiscard]] bool IsInUpdateQueue() const { return uQueuePos != -1; }' in header
states = function(header, 'enum ItemUpdateState') + ';'
assert 'return ObjectAccessor::FindPlayer(GetOwnerGUID());' in function(item_source, 'Player* Item::GetOwner()')
save = function(item_source, 'void Item::SaveToDB(CharacterDatabaseTransaction trans)')
assert save.count('delete this;') == 1 and save.index('case ITEM_REMOVED:') < save.index('delete this;')
assert save.rstrip().endswith('SetState(ITEM_UNCHANGED);\n\n    if (!isInTransaction)\n        CharacterDatabase.CommitTransaction(trans);\n}')
inventory = function((core / 'src/server/game/Entities/Player/PlayerStorage.cpp').read_text(),
                     'void Player::_SaveInventory(CharacterDatabaseTransaction trans)')
assert re.search(r'Item\* item = m_itemUpdateQueue\[i\];\s+if \(!item\)\s+continue;', inventory)
assert inventory.rstrip().endswith('m_itemUpdateQueue.clear();\n}')

fixture = r'''
#include <cassert>
#include <cstdint>
#include <iostream>
#include <map>
#include <string>
#include <vector>
using uint32 = std::uint32_t; using int32 = std::int32_t; using uint64 = std::uint64_t;
#define ASSERT(condition) assert(condition)
#define LOG_DEBUG(...) ((void)0)
@STATES@
struct ObjectGuid
{
    uint64 value = 0;
    bool operator!=(ObjectGuid const& other) const { return value != other.value; }
    bool operator<(ObjectGuid const& other) const { return value < other.value; }
    std::string ToString() const { return std::to_string(value); }
};
struct Item;
struct Player
{
    ObjectGuid guid;
    std::vector<Item*> m_itemUpdateQueue;
    bool m_itemUpdateQueueBlocked = false;
    int refundsDeleted = 0;
    ObjectGuid GetGUID() const { return guid; }
    void DeleteRefundReference(ObjectGuid) { ++refundsDeleted; }
    void SaveInventory();
};
std::map<ObjectGuid, Player*> online;
namespace ObjectAccessor
{
Player* FindPlayer(ObjectGuid guid) { auto found = online.find(guid); return found == online.end() ? nullptr : found->second; }
}
int deletedItems = 0;
struct Item
{
    ObjectGuid guid, owner;
    ItemUpdateState uState = ITEM_NEW;
    int32 uQueuePos = -1;
    ~Item() { ++deletedItems; }
    ObjectGuid GetGUID() const { return guid; }
    ObjectGuid GetOwnerGUID() const { return owner; }
    Player* GetOwner() const { return ObjectAccessor::FindPlayer(GetOwnerGUID()); }
    bool IsInUpdateQueue() const { return uQueuePos != -1; }
    ItemUpdateState GetState() const { return uState; }
    void SetState(ItemUpdateState state, Player* forplayer = nullptr);
    void AddToUpdateQueueOf(Player* player);
    void RemoveFromUpdateQueueOf(Player* player);
    // SaveToDB's queue effects: a removed item is deleted, any other is marked unchanged.
    void SaveToDB()
    {
        if (uState == ITEM_REMOVED)
        {
            delete this;
            return;
        }
        SetState(ITEM_UNCHANGED);
    }
};
// Player::_SaveInventory's walk over the queue.
void Player::SaveInventory()
{
    for (std::size_t i = 0; i < m_itemUpdateQueue.size(); ++i)
    {
        Item* item = m_itemUpdateQueue[i];
        if (!item)
            continue;
        item->SaveToDB();
    }
    m_itemUpdateQueue.clear();
}
@PRODUCTION@
std::size_t Live(Player const& player, Item const* item)
{
    std::size_t count = 0;
    for (Item* queued : player.m_itemUpdateQueue)
        count += queued == item;
    return count;
}
int main()
{
    Player player;
    player.guid = {1};
    online[player.guid] = &player;
    for (bool explicitOwner : {false, true})
    {
        Item* item = new Item;
        item->guid = {2};
        item->owner = player.guid;
        item->uState = ITEM_UNCHANGED;
        item->SetState(ITEM_CHANGED, &player);
        assert(Live(player, item) == 1 && item->IsInUpdateQueue());
        // A direct save (trade, mail or bank) marks it unchanged while it is still queued.
        if (explicitOwner)
            item->SetState(ITEM_UNCHANGED, &player);
        else
            item->SaveToDB();
        assert(!item->IsInUpdateQueue() && Live(player, item) == 0);
        item->SetState(ITEM_CHANGED, &player);
        item->SetState(ITEM_REMOVED, &player);
        assert(Live(player, item) == 1);
        int const before = deletedItems;
        player.SaveInventory();
        assert(deletedItems == before + 1 && player.m_itemUpdateQueue.empty());
    }

    // An offline owner has no queue to leave.
    Item offline;
    offline.owner = {9};
    offline.uState = ITEM_CHANGED;
    offline.uQueuePos = 0;
    offline.SetState(ITEM_UNCHANGED);
    assert(!offline.IsInUpdateQueue() && offline.GetState() == ITEM_UNCHANGED);

    // A new item removed before its first save still disappears at once.
    Item* fresh = new Item;
    fresh->owner = player.guid;
    fresh->SetState(ITEM_NEW, &player);
    int const before = deletedItems;
    fresh->SetState(ITEM_REMOVED, &player);
    assert(deletedItems == before + 1 && player.refundsDeleted == 1 && player.m_itemUpdateQueue.size() == 1 &&
           !player.m_itemUpdateQueue[0]);
    player.SaveInventory();
    std::cout << "Item update queue: one entry per queued item through direct saves, changes and removal\n";
}
'''.replace('@STATES@', states).replace('@PRODUCTION@', production)


def build(directory, executable):
    return [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-g', *SANITIZER_FLAGS,
            str(directory / 'Fixture.cpp'), '-o', str(executable)]


with tempfile.TemporaryDirectory(prefix='item-update-queue-') as temporary:
    work = Path(temporary)
    revert = work / 'revert'
    (revert / Path(relative).parent).mkdir(parents=True)
    (revert / relative).write_text(item_source)
    git_apply(revert, fork_change('azerothcore-wotlk', 'azerothcore-item-update-queue', paths=(relative,)),
              '--reverse')
    reverted = function((revert / relative).read_text(), signatures[0])
    current = function(item_source, signatures[0])
    assert reverted != current
    (work / 'Fixture.cpp').write_text(fixture)
    subprocess.run(build(work, work / 'fixture'), check=True)
    result = run_fixture([str(work / 'fixture')])
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout, end='')
    reject_mutants(work, (
        ('recorded fork change reverted', 'Fixture.cpp', current, reverted),
        ('stale entry kept', 'Fixture.cpp', 'RemoveFromUpdateQueueOf(owner);', '(void)owner;'),
    ), build, 'Item update queue')
