"""Compare Journal reference-drop odds with the native loot roll at custom rates."""

import argparse
from pathlib import Path
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    cxx,
    function,
    prepared_core,
    reject_mutants,
    run_fixture,
    source_argument,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, 'module', default=prepared_core() / 'modules/mod-forever-journal')
args = parser.parse_args()
core = prepared_core()
source = (args.module / 'src/JournalLoot.cpp').read_text()
native = (core / 'src/server/game/Loot/LootMgr.cpp').read_text()
random = (core / 'src/common/Utilities/Random.h').read_text()

production = '\n'.join([
    function(source, 'struct Row') + ';',
    'using Table = std::vector<Row>;',
    'std::unordered_map<uint32, Table> sReference;',
    'std::unordered_map<uint32, uint32> sReferenceUsers;',
    'std::unordered_set<uint64> sConditioned;',
    'constexpr uint16 LOOT_MODE_DEFAULT_BIT = 1;',
    'constexpr uint32 MAX_DEPTH = 6, COND_REFERENCE_LOOT = 10;',
    function(source, 'uint64 ConditionKey('),
    function(source, 'bool IsWorldDrop('),
    function(source, 'float QualityRate('),
    source[source.index('struct Odds'):source.index('        // A table that is one group')],
    function(source, 'bool IsEqualChanceGroup('),
    function(source, 'void AddReference('),
    function(source, 'uint32 RowFlags('),
    function(source, 'bool InMode('),
    function(source, 'OddsMap Compute(Table const& table, uint32 condSource, uint32 lootId, uint32 depth, bool hardMode)\n'),
])

fixture = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <unordered_map>
#include <unordered_set>
#include <vector>
using uint8 = std::uint8_t; using uint16 = std::uint16_t; using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
enum Rates { RATE_DROP_ITEM_POOR, RATE_DROP_ITEM_NORMAL, RATE_DROP_ITEM_UNCOMMON,
    RATE_DROP_ITEM_RARE, RATE_DROP_ITEM_EPIC, RATE_DROP_ITEM_LEGENDARY, RATE_DROP_ITEM_ARTIFACT,
    RATE_DROP_ITEM_REFERENCED, RATE_DROP_ITEM_REFERENCED_AMOUNT };
constexpr unsigned ITEM_QUALITY_HEIRLOOM = 7;
constexpr uint32 LOOT_QUEST = 1, LOOT_HARD_MODE = 2, LOOT_CONDITION = 4, LOOT_SHARED = 8;
Rates const qualityToRate[] = {RATE_DROP_ITEM_POOR, RATE_DROP_ITEM_NORMAL, RATE_DROP_ITEM_UNCOMMON,
    RATE_DROP_ITEM_RARE, RATE_DROP_ITEM_EPIC, RATE_DROP_ITEM_LEGENDARY, RATE_DROP_ITEM_ARTIFACT};
struct World {
    float referenceRate = 1.0f;
    float getRate(Rates rate) const { return rate == RATE_DROP_ITEM_REFERENCED ? referenceRate : 1.0f; }
} world;
World* sWorld = &world;
struct ItemTemplate { uint32 Quality = 1; } prototype;
struct ObjectMgr { ItemTemplate const* GetItemTemplate(uint32) const { return &prototype; } } objectMgr;
ObjectMgr* sObjectMgr = &objectMgr;
struct Config { uint32 worldDropThreshold = 5; bool showWorldDrops = true; } config;
Config const& GetConfig() { return config; }
struct Player {}; struct Loot {}; struct LootStore {};
struct LootStoreItem {
    float chance; uint32 reference = 0, itemid = 1;
    bool Roll(bool rate, Player const* player, Loot& loot, LootStore const& store) const;
};
struct ScriptMgr {
    bool OnItemRoll(Player const*, LootStoreItem const*, float&, Loot&, LootStore const&) { return true; }
} scriptMgr;
ScriptMgr* sScriptMgr = &scriptMgr;
double sample = 0.5;
double rand_chance() { return sample; }
@NATIVE_ROLL@
@PRODUCTION@

int main()
{
    Loot loot; LootStore store;
    LootStoreItem nativeItem{25.0f};
    Row item; item.item = 1; item.chance = 25.0f;
    sReference[100] = {item};
    unsigned checked = 0;
    for (float rate : {0.0f, 0.5f, 1.0f, 2.0f, 3.0f, 10.0f})
        for (float chance : {20.0f, 50.0f, 100.0f})
        {
            world.referenceRate = rate;
            LootStoreItem nativeReference{chance, 100};
            // Execute the core's actual parent and child rolls at each 1% midpoint.
            unsigned drops = 0;
            for (unsigned parent = 0; parent < 100; ++parent)
            {
                sample = parent + 0.5;
                if (!nativeReference.Roll(true, nullptr, loot, store))
                    continue;
                for (unsigned child = 0; child < 100; ++child)
                {
                    sample = child + 0.5;
                    drops += nativeItem.Roll(true, nullptr, loot, store);
                }
            }
            Row reference; reference.reference = 100; reference.chance = chance;
            OddsMap result = Compute({reference}, 1, 200, 0, false);
            float reported = result.contains(1) ? result.at(1).p : 0.0f;
            assert(std::abs(reported - float(drops) / 10000.0f) < 0.00001f);
            ++checked;
        }
    // Each enclosing reference is its own bounded roll, including nested tables.
    world.referenceRate = 3.0f;
    Row inner; inner.reference = 100; inner.chance = 50.0f;
    sReference[101] = {inner};
    Row outer = inner; outer.reference = 101;
    assert(std::abs(Compute({outer}, 1, 200, 0, false).at(1).p - 0.25f) < 0.00001f);
    std::cout << "Journal reference chances match native rolls: " << checked
        << " rate/chance cases and nested references\n";
}
'''.replace('@NATIVE_ROLL@', function(random, 'inline bool roll_chance_f(') + '\n'
           + function(native, 'bool LootStoreItem::Roll(')).replace('@PRODUCTION@', production)


def build(directory, executable):
    return [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', *SANITIZER_FLAGS,
            str(directory / 'Fixture.cpp'), '-o', str(executable)]


with tempfile.TemporaryDirectory(prefix='journal-loot-') as temporary:
    work = Path(temporary)
    (work / 'Fixture.cpp').write_text(fixture)
    subprocess.run(build(work, work / 'fixture'), check=True)
    result = run_fixture([str(work / 'fixture')])
    assert result.returncode == 0, result.stderr or result.stdout
    print(result.stdout.strip(), flush=True)
    reject_mutants(work, [
        ('uncapped reference roll', 'Fixture.cpp',
         'std::min(1.0f, row.chance * refRate / 100.0f)', 'row.chance * refRate / 100.0f'),
    ], build, 'Journal reference loot')
