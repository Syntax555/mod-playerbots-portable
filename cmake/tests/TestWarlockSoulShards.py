"""Check that warlock bots without Soul Shards earn one through Drain Soul.

The production trigger, its registration and the combat strategy run against
small engine stubs. Natural mode disables shard creation, so every warlock
specialization relies on this ordinary source. Mutation checks confirm that the
trigger, its cheap-first ordering and the strategy node are required. Shard
disposal runs the real action and native count-removal method, so a stack loses
only one earned shard in either bags or the backpack.
"""

import argparse
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
    source_argument,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help='prepared Playerbots src directory')
args = parser.parse_args()
module = args.source or prepared_core(Path(__file__).resolve().parents[2]) / 'modules/mod-playerbots/src'
core = prepared_core(Path(__file__).resolve().parents[2])
player_header = (core / 'src/server/game/Entities/Player/Player.h').read_text()
storage = (core / 'src/server/game/Entities/Player/PlayerStorage.cpp').read_text()
warlock = module / 'Ai/Class/Warlock'
triggers_header = (warlock / 'WarlockTriggers.h').read_text()
triggers_source = (warlock / 'WarlockTriggers.cpp').read_text()
context = (warlock / 'WarlockAiObjectContext.cpp').read_text()
strategy = (warlock / 'Strategy/GenericWarlockStrategy.cpp').read_text()
actions = (warlock / 'WarlockActions.cpp').read_text()
generic = (module / 'Ai/Base/Trigger/GenericTriggers.cpp').read_text()
generic_header = (module / 'Ai/Base/Trigger/GenericTriggers.h').read_text()

registration = re.search(r'creators\["([^"]+)"\] = &WarlockTriggerFactoryInternal::drain_soul_for_shard;', context)
assert registration, 'Drain Soul shard trigger is not registered'
assert 'static Trigger* drain_soul_for_shard(PlayerbotAI* botAI) { return new DrainSoulForShardTrigger(botAI); }' \
    in context
for guard in ('bool CreateSoulShardAction::Execute(', 'bool CreateSoulShardAction::isUseful('):
    body = function(actions, guard)
    assert body.index('if (sPlayerbotAIConfig.naturalProgression)\n        return false;') < body.index('Player* bot')

production = {
    'inventory': '\n'.join([
        re.search(r'^#define INVENTORY_SLOT_BAG_0\s+\d+', player_header, re.MULTILINE).group(0),
        function(player_header, 'enum InventorySlots') + ';',
        function(player_header, 'enum InventoryPackSlots') + ';',
    ]),
    'classes': '\n'.join([
        re.search(r'class TwoTriggers : public Trigger\n\{.*?\n\};', generic_header, re.DOTALL).group(0),
        re.search(r'class OutOfSoulShardsTrigger : public Trigger\n\{.*?\n\};', triggers_header, re.DOTALL).group(0),
        re.search(r'class DrainSoulForShardTrigger : public TwoTriggers\n\{.*?\n\};', triggers_header, re.DOTALL).group(0),
    ]),
    'functions': '\n'.join([
        re.search(r'static const uint32 SOUL_SHARD_ITEM_ID = \d+;', triggers_source).group(0),
        re.search(r'const int ITEM_SOUL_SHARD = \d+;', actions).group(0),
        function(storage, 'void Player::DestroyItemCount(Item*'),
        function(actions, 'bool DestroySoulShardAction::Execute('),
        function(triggers_source, 'uint32 GetSoulShardCount(Player* bot)'),
        function(triggers_source, 'bool OutOfSoulShardsTrigger::IsActive()'),
        function(generic, 'bool TwoTriggers::IsActive()'),
        function(generic, 'std::string const TwoTriggers::getName()'),
        function(strategy, 'void GenericWarlockStrategy::InitTriggers('),
    ]),
}

source = r'''
#include <cassert>
#include <cstdint>
#include <iostream>
#include <map>
#include <memory>
#include <string>
#include <utility>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
INVENTORY
#define LOG_DEBUG(...) ((void)0)
enum ItemUpdateState { ITEM_CHANGED };
class Player;
struct ItemTemplate { uint32 ItemId; };
struct Item
{
    Item(uint32 entry, uint32 count, uint8 bag, uint8 slot) : proto{entry}, count(count), bag(bag), slot(slot) {}
    ItemTemplate const* GetTemplate() const { return &proto; }
    uint32 GetEntry() const { return proto.ItemId; }
    uint32 GetCount() const { return count; }
    void SetCount(uint32 value) { count = value; }
    uint8 GetBagSlot() const { return bag; }
    uint8 GetSlot() const { return slot; }
    void SendUpdateToPlayer(Player*) {}
    void SetState(ItemUpdateState, Player*) {}
    ItemTemplate proto;
    uint32 count;
    uint8 bag, slot;
};
struct Bag : Item
{
    explicit Bag(uint8 slot) : Item(1, 1, INVENTORY_SLOT_BAG_0, slot) {}
    uint32 GetBagSize() const { return 4; }
    Item* GetItemByPos(uint8 position) {
        auto found = contents.find(position);
        return found == contents.end() || found->second->count == 0 ? nullptr : found->second;
    }
    std::map<uint8, Item*> contents;
};

class Player
{
public:
    std::map<uint32, uint32> items;
    std::map<uint8, Item*> inventory;
    int scans = 0;
    uint32 GetItemCount(uint32 item, bool inBankAlso) { assert(!inBankAlso); ++scans; return items[item]; }
    Item* GetItemByPos(uint8 bag, uint8 slot) {
        if (bag != INVENTORY_SLOT_BAG_0) {
            auto container = inventory.find(bag);
            return container == inventory.end() ? nullptr : static_cast<Bag*>(container->second)->GetItemByPos(slot);
        }
        auto found = inventory.find(slot);
        return found == inventory.end() || found->second->count == 0 ? nullptr : found->second;
    }
    void DestroyItem(uint8 bag, uint8 slot, bool update) {
        assert(update);
        Item* item = GetItemByPos(bag, slot);
        assert(item);
        item->count = 0;
    }
    void DestroyItemCount(Item* item, uint32& count, bool update);
    void ItemRemovedQuestCheck(uint32, uint32) {}
    bool IsInWorld() const { return true; }
};
struct Event {};
struct DestroySoulShardAction
{
    Player* bot;
    bool Execute(Event);
};
class PlayerbotAI;
class Trigger
{
public:
    Trigger(PlayerbotAI* botAI, std::string name = "", int = 1) : botAI(botAI), name(std::move(name)) {}
    virtual ~Trigger() = default;
    virtual bool IsActive() { return false; }
    virtual std::string const getName() { return name; }
protected:
    PlayerbotAI* botAI;
    std::string name;
};
class AiObjectContext
{
public:
    std::map<std::string, Trigger*> triggers;
    Trigger* GetTrigger(std::string const& name) { return triggers.count(name) ? triggers[name] : nullptr; }
};
class PlayerbotAI
{
public:
    Player* bot;
    AiObjectContext context;
    Player* GetBot() { return bot; }
    AiObjectContext* GetAiObjectContext() { return &context; }
};
class CriticalTarget : public Trigger
{
public:
    bool critical = false;
    using Trigger::Trigger;
    bool IsActive() override { return critical; }
};
struct NextAction
{
    std::string name;
    float relevance;
    NextAction(std::string name, float relevance = 0.0f) : name(std::move(name)), relevance(relevance) {}
};
struct TriggerNode
{
    std::string name;
    std::vector<NextAction> actions;
    TriggerNode(std::string name, std::vector<NextAction> actions) : name(std::move(name)), actions(std::move(actions)) {}
};
struct CombatStrategy
{
    void InitTriggers(std::vector<TriggerNode*>&) {}
};
struct GenericWarlockStrategy : CombatStrategy
{
    void InitTriggers(std::vector<TriggerNode*>& triggers);
};
''' + '\nCLASSES\nFUNCTIONS\n' + r'''
int main()
{
    Player bot;
    PlayerbotAI ai{&bot, {}};
    CriticalTarget target(&ai, "target critical health");
    OutOfSoulShardsTrigger noShard(&ai);
    ai.context.triggers = {{"target critical health", &target}, {"no soul shard", &noShard}};
    DrainSoulForShardTrigger trigger(&ai);
    assert(trigger.getName() == "REGISTERED");

    for (uint32 shards : {0u, 1u, 3u})
        for (bool critical : {false, true})
        {
            bot.items[SOUL_SHARD_ITEM_ID] = shards;
            target.critical = critical;
            bot.scans = 0;
            assert(trigger.IsActive() == (critical && shards == 0));
            // Healthy targets never pay for a bag scan.
            assert(bot.scans == (critical ? 1 : 0));
        }
    bot.items[SOUL_SHARD_ITEM_ID] = 0;
    target.critical = true;
    ai.context.triggers.erase("target critical health");
    assert(!trigger.IsActive());

    std::vector<TriggerNode*> nodes;
    GenericWarlockStrategy().InitTriggers(nodes);
    int matches = 0;
    for (TriggerNode* node : nodes)
    {
        if (node->name == "REGISTERED")
        {
            ++matches;
            assert(node->actions.size() == 1 && node->actions[0].name == "drain soul");
            assert(node->actions[0].relevance > 0.0f && node->actions[0].relevance < 60.0f);
        }
        delete node;
    }
    assert(matches == 1);
    std::cout << "Warlock Soul Shards: shardless bots use Drain Soul on critical-health targets\n";

    for (bool inBag : {false, true})
        for (uint32 count : {1u, 2u, 20u})
        {
            Player inventory;
            Bag bag(INVENTORY_SLOT_BAG_START);
            uint8 location = inBag ? INVENTORY_SLOT_BAG_START : INVENTORY_SLOT_BAG_0;
            uint8 first = inBag ? 1 : INVENTORY_SLOT_ITEM_START;
            Item junk(1, 7, location, first), shard(ITEM_SOUL_SHARD, count, location, first + 1),
                later(ITEM_SOUL_SHARD, 5, location, first + 2);
            // Entries outside the carried inventory never supply a shard to dispose of.
            Item bank(ITEM_SOUL_SHARD, 9, INVENTORY_SLOT_BAG_0, INVENTORY_SLOT_ITEM_END);
            inventory.inventory[INVENTORY_SLOT_ITEM_END] = &bank;
            inventory.inventory[INVENTORY_SLOT_BAG_START] = &bag;
            auto& slots = inBag ? bag.contents : inventory.inventory;
            slots[first] = &junk;
            slots[first + 1] = &shard;
            slots[first + 2] = &later;
            DestroySoulShardAction dispose{&inventory};
            assert(dispose.Execute(Event()));
            assert(shard.count == count - 1 && later.count == 5 && junk.count == 7 && bank.count == 9);
            assert((inventory.GetItemByPos(location, first + 1) == nullptr) == (count == 1));
            shard.count = later.count = 0;
            assert(!dispose.Execute(Event()) && bank.count == 9 && junk.count == 7);
        }
    std::cout << "Warlock Soul Shards: native disposal removes one shard per stack in bags and backpack\n";
}
'''


def build(directory, parts, name):
    text = source.replace('CLASSES', parts['classes']).replace('FUNCTIONS', parts['functions'])
    text = text.replace('INVENTORY\n', parts['inventory'] + '\n')
    text = text.replace('REGISTERED', registration.group(1))
    (directory / (name + '.cpp')).write_text(text)
    executable = directory / name
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', *SANITIZER_FLAGS,
                    str(directory / (name + '.cpp')), '-o', str(executable)], check=True)
    return subprocess.run([str(executable)], capture_output=True, text=True, check=False, timeout=TIMEOUT)


mutations = [
    ('bag scan before target health', 'classes', 'TwoTriggers(botAI, "target critical health", "no soul shard")',
     'TwoTriggers(botAI, "no soul shard", "target critical health")'),
    ('Drain Soul with shards in bags', 'functions', 'return GetSoulShardCount(botAI->GetBot()) == 0;',
     'return GetSoulShardCount(botAI->GetBot()) <= 3;'),
    ('strategy keeps only shard creation', 'functions', '"target critical health and no soul shard"', '"unused"'),
    ('whole shard stack removed', 'functions', 'bot->DestroyItemCount(pItem, count, true);',
     'bot->DestroyItem(pItem->GetBagSlot(), pItem->GetSlot(), true); (void)count;'),
    ('more than one shard consumed', 'functions', 'uint32 count = 1;', 'uint32 count = pItem->GetCount();'),
]

with tempfile.TemporaryDirectory(prefix='portable-warlock-shards-') as temporary:
    temporary = Path(temporary)
    result = build(temporary, production, 'shards')
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit(f'Warlock Soul Shard fixture failed (exit {result.returncode})')
    for label, key, old, new in mutations:
        mutated = dict(production)
        mutated[key] = production[key].replace(old, new)
        if mutated[key] == production[key]:
            raise SystemExit(f'{label} mutation was not applied')
        if not build(temporary, mutated, 'mutant').returncode:
            raise SystemExit(f'Warlock Soul Shard fixture did not reject: {label}')
        print(f'Warlock Soul Shard mutation rejected: {label}')
