"""Keep a completed Dungeon Clear alive for ordinary final loot, with a timeout."""

import argparse
from pathlib import Path
import re
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    cxx,
    function,
    prepared_core,
    reject_part_mutants,
    run_fixture,
    source_argument,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, 'core', default=prepared_core())
source_argument(parser, default=prepared_core() / 'modules/mod-dungeon-clear/src')
args = parser.parse_args()
dc = args.source / 'Ai/Dungeon/DungeonClear'
policy = (dc / 'Util/DcLootPolicy.cpp').read_text()
header = (dc / 'Util/DcLootPolicy.h').read_text()
triggers = (dc / 'Trigger/DungeonClearTriggers.cpp').read_text()
advance = (dc / 'Action/DcAdvanceAction.cpp').read_text()

# The policy reads real group rolls and corpse items; the doubles keep the
# native types and ownership checks rather than inventing pending-loot flags.
group = (args.core / 'src/server/game/Groups/Group.h').read_text()
loot = (args.core / 'src/server/game/Loot/LootMgr.h').read_text()
assert 'std::vector<Roll const*> GetRolls() const' in group
assert 'ItemQualities GetLootThreshold() const' in group
assert all(name in loot for name in ('is_looted', 'freeforall', 'is_underthreshold', 'itemid'))
assert re.search(r'uint32\s+finalLootHoldSinceMs\s*=\s*0;', (dc / 'DcRunState.h').read_text())
parts = {
    'clock': function((args.core / 'src/common/Utilities/Timer.h').read_text(),
                      'inline uint32 getMSTimeDiff(uint32 oldMSTime, uint32 newMSTime)'),
    'policy': function(policy, 'std::string DcLootPolicy::DescribePendingBossLoot('),
    'trigger': function(triggers, 'bool DungeonClearAllClearedTrigger::IsActive()'),
    'advance': function(advance, '    if (!next.has_value() && DcRun::Of(context).finalLootHoldSinceMs)'),
}

program = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <type_traits>
#include <unordered_set>
#include <vector>
using uint32 = std::uint32_t;
constexpr uint32 IN_MILLISECONDS = 1000, UNIT_DYNFLAG_LOOTABLE = 1;
uint32 nowMs = 100, logEntries = 0;
uint32 getMSTime() { return nowMs; }
@CLOCK@
#define LOG_INFO(...) (++logEntries)
enum ItemQualities { ITEM_QUALITY_NORMAL = 1, ITEM_QUALITY_UNCOMMON = 2, ITEM_QUALITY_RARE = 3 };
struct Roll {};
struct Group {
    std::vector<Roll const*> rolls;
    ItemQualities threshold = ITEM_QUALITY_UNCOMMON;
    std::vector<Roll const*> GetRolls() const { return rolls; }
    ItemQualities GetLootThreshold() const { return threshold; }
};
struct LootItem { uint32 itemid = 1; bool is_looted = false, freeforall = false, is_underthreshold = false; };
struct ItemTemplate { uint32 Quality = ITEM_QUALITY_RARE; };
struct ObjectMgr {
    std::map<uint32, ItemTemplate> items{{1, {ITEM_QUALITY_RARE}}, {2, {ITEM_QUALITY_NORMAL}}};
    ItemTemplate const* GetItemTemplate(uint32 id) const {
        auto found = items.find(id); return found == items.end() ? nullptr : &found->second;
    }
} objectMgr;
ObjectMgr* sObjectMgr = &objectMgr;
enum class DungeonAnchorKind { Boss, Objective };
struct DungeonBossInfo { DungeonAnchorKind kind = DungeonAnchorKind::Boss; uint32 entry = 7; };
struct Player;
struct Creature {
    bool alive = false, lootable = true;
    uint32 entry = 7;
    float distance = 10;
    Group* recipient = nullptr;
    struct Loot { std::vector<LootItem> items{{}}; } loot;
    bool IsAlive() const { return alive; }
    uint32 GetEntry() const { return entry; }
    bool HasDynamicFlag(uint32) const { return lootable; }
    Group* GetLootRecipientGroup() const { return recipient; }
    bool IsWithinDist(Player*, float range) const { return distance <= range; }
    std::string GetName() const { return "boss"; }
};
struct Map {
    bool dungeon = true;
    std::map<uint32, Creature*> creatures;
    auto const& GetCreatureBySpawnIdStore() const { return creatures; }
    bool IsDungeon() const { return dungeon; }
};
struct DcRunState { uint32 finalLootHoldSinceMs = 0; };
namespace DcKey { constexpr int DungeonBosses = 1, NextDungeonBoss = 2; }
template<class T> struct Value { T value{}; T& Get() { return value; } };
struct AiObjectContext {
    Value<std::vector<DungeonBossInfo>> bosses;
    Value<std::optional<DungeonBossInfo>> next;
    DcRunState run;
    int stallsCleared = 0, phaseCleared = 0;
    template<class T> Value<T>* GetValue(int) {
        if constexpr (std::is_same_v<T, std::vector<DungeonBossInfo>>) return &bosses;
        else return &next;
    }
};
struct PlayerbotAI { AiObjectContext context; AiObjectContext* GetAiObjectContext() { return &context; } };
struct Player {
    Map* map = nullptr;
    Group* group = nullptr;
    Player* owner = nullptr;
    PlayerbotAI* ai = nullptr;
    bool terminal = true;
    Map* GetMap() const { return map; }
    Group* GetGroup() const { return group; }
    std::string GetName() const { return "tank"; }
};
#define GET_PLAYERBOT_AI(p) ((p)->ai)
bool IsTerminalDriver(Player* p) { return p->terminal; }
namespace DcLeaderSignal { Player* FindRunOwner(Player* p) { return p->owner; } }
namespace DcRun { DcRunState& Of(AiObjectContext* c) { return c->run; } }
struct DcLootPolicy {
    @CONSTANTS@
    static std::string DescribePendingBossLoot(Player*, std::vector<DungeonBossInfo> const&);
};
struct DungeonClearAllClearedTrigger { Player* bot; bool IsActive(); };
@POLICY@
@TRIGGER@
void ClearStall(AiObjectContext* c) { ++c->stallsCleared; }
void SetPhase(AiObjectContext* c, char const*) { ++c->phaseCleared; }
bool advanceTick(AiObjectContext* context, std::optional<DungeonBossInfo> next) {
    @ADVANCE@
    return true;
}
int main() {
    Group group, other;
    Roll roll;
    Map map;
    PlayerbotAI ownerAi, followerAi;
    Player owner{&map, &group, nullptr, &ownerAi}; owner.owner = &owner;
    Player follower{&map, &group, &owner, &followerAi};
    auto& context = ownerAi.context;
    context.bosses.value.push_back({});
    Creature corpse; corpse.recipient = &group;
    map.creatures[1] = &corpse;
    auto pending = [&] { return DcLootPolicy::DescribePendingBossLoot(&follower, context.bosses.value); };
    assert(DcLootPolicy::DescribePendingBossLoot(nullptr, {}).empty());
    follower.group = nullptr; assert(pending().empty()); follower.group = &group;
    assert(!pending().empty());
    group.rolls.push_back(&roll); map.creatures.clear(); assert(!pending().empty());
    group.rolls.clear(); assert(pending().empty()); map.creatures[1] = &corpse;
    corpse.alive = true; assert(pending().empty()); corpse.alive = false;
    corpse.lootable = false; assert(pending().empty()); corpse.lootable = true;
    corpse.recipient = &other; assert(pending().empty()); corpse.recipient = &group;
    corpse.distance = 101; assert(pending().empty()); corpse.distance = 100; assert(!pending().empty());
    corpse.entry = 8; assert(pending().empty()); corpse.entry = 7;
    context.bosses.value[0].kind = DungeonAnchorKind::Objective; assert(pending().empty());
    context.bosses.value[0].kind = DungeonAnchorKind::Boss;
    auto& item = corpse.loot.items[0];
    item.is_looted = true; assert(pending().empty()); item.is_looted = false;
    item.freeforall = true; assert(pending().empty()); item.freeforall = false;
    item.is_underthreshold = true; assert(pending().empty()); item.is_underthreshold = false;
    item.itemid = 2; assert(pending().empty()); item.itemid = 999; assert(pending().empty()); item.itemid = 1;

    DungeonClearAllClearedTrigger trigger{&follower};
    trigger.bot = nullptr; assert(!trigger.IsActive()); trigger.bot = &follower;
    follower.terminal = false; assert(!trigger.IsActive()); follower.terminal = true;
    map.dungeon = false; assert(!trigger.IsActive()); map.dungeon = true;
    follower.owner = nullptr; assert(!trigger.IsActive()); follower.owner = &owner;
    context.bosses.value.clear(); assert(!trigger.IsActive()); context.bosses.value.push_back({});
    context.run.finalLootHoldSinceMs = 50; context.next.value.emplace();
    assert(!trigger.IsActive()); assert(!context.run.finalLootHoldSinceMs);
    context.next.value.reset();
    // A replacement driver reads its run owner's roster and timer.
    assert(followerAi.context.bosses.value.empty());
    assert(!trigger.IsActive()); assert(context.run.finalLootHoldSinceMs == nowMs);
    assert(logEntries == 1); nowMs += 59999; assert(!trigger.IsActive()); assert(logEntries == 1);
    nowMs++; assert(trigger.IsActive()); assert(logEntries == 2);
    context.run.finalLootHoldSinceMs = 0; nowMs = 200;
    assert(!trigger.IsActive()); item.is_looted = true; assert(trigger.IsActive());
    assert(!advanceTick(&context, {})); assert(context.stallsCleared == 1 && context.phaseCleared == 1);
    assert(advanceTick(&context, DungeonBossInfo{})); context.run.finalLootHoldSinceMs = 0;
    assert(advanceTick(&context, {}));
    // Repeated checks at zero must not look like an almost-full clock cycle.
    item.is_looted = false; nowMs = 0;
    assert(!trigger.IsActive()); assert(context.run.finalLootHoldSinceMs != 0);
    assert(!trigger.IsActive()); nowMs = 59999; assert(!trigger.IsActive());
    nowMs++; assert(trigger.IsActive()); context.run.finalLootHoldSinceMs = 0;
    // Use the native elapsed-time calculation at its 32-bit wrap boundary.
    nowMs = UINT32_MAX - 1000;
    assert(!trigger.IsActive()); nowMs += 60000; assert(!trigger.IsActive()); nowMs++; assert(trigger.IsActive());
}
'''

constants = '\n'.join(re.findall(r'    static constexpr (?:float|uint32) k(?:PendingBossLootRange|FinalLootWaitMs) = .*?;', header))
assert len(constants.splitlines()) == 2
program = program.replace('@CONSTANTS@', constants)

with tempfile.TemporaryDirectory(prefix='portable-dungeon-final-loot-') as temporary:
    directory = Path(temporary)

    def build(variants, label):
        cpp = directory / (label + '.cpp')
        text = program
        for key, value in variants.items():
            text = text.replace('@' + key.upper() + '@', value)
        cpp.write_text(text)
        executable = directory / label
        subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', *SANITIZER_FLAGS,
                        str(cpp), '-o', str(executable)], check=True)
        return run_fixture([str(executable)])

    result = build(parts, 'production')
    assert result.returncode == 0, result.stderr
    print('Dungeon final loot production passed')
    reject_part_mutants(parts, [
        ('open rolls ignored', 'policy', 'group->GetRolls().size()', '0u'),
        ('foreign corpse', 'policy', ' || c->GetLootRecipientGroup() != group', ''),
        ('distant corpse', 'policy', 'if (!c->IsWithinDist(driver, kPendingBossLootRange))', 'if (false)'),
        ('objective counted as boss', 'policy', 'info.kind == DungeonAnchorKind::Boss && ', ''),
        ('low quality held', 'policy', 'proto->Quality < uint32(threshold)', '(void(threshold), false)'),
        ('hold not reset', 'trigger', 'rs.finalLootHoldSinceMs = 0;', '(void)rs;'),
        ('hold skipped', 'trigger', 'if (pending.empty())', 'if (true)'),
        ('zero clock ends immediately', 'trigger', 'now ? now : 0xFFFFFFFFu', 'now ? now : 1u'),
        ('hold never ends', 'trigger', 'getMSTimeDiff(rs.finalLootHoldSinceMs, now) < waitMs', '(void(waitMs), now != 0)'),
        ('advance starves loot', 'advance', '!next.has_value()', 'next.has_value()'),
    ], build, 'Dungeon final loot')
