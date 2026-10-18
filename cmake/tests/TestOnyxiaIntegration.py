"""Run Raid Clear's Onyxia target selection against native creature contracts.

The real whelp helpers and action must handle both core and restored Vanilla
entries, keep a hittable current whelp and leave evading targets. Registration
and configuration checks establish source integration, not an in-game clear.
"""

import argparse
from pathlib import Path
import re
import subprocess
import tempfile

from FixtureSupport import (
    cxx,
    function,
    prepared_core,
    reject_mutants,
    run_fixture,
    source_argument,
)


HARNESS = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <map>
#include <string>
#include <type_traits>
#include <unordered_map>
#include <vector>
using uint32 = uint32_t;
using ObjectGuid = uint32;
using GuidVector = std::vector<ObjectGuid>;
@CREATURES@;

struct Creature;
struct Unit
{
    uint32 entry = 0;
    bool alive = true, inWorld = true, visible = true, valid = true;
    float distance = 10;
    virtual ~Unit() = default;
    virtual Creature const* ToCreature() const { return nullptr; }
    uint32 GetEntry() const { return entry; }
    bool IsAlive() const { return alive; }
    bool IsInWorld() const { return inWorld; }
};
struct Creature : Unit
{
    bool evade = false, unreachable = false;
    explicit Creature(uint32 id) { entry = id; }
    Creature const* ToCreature() const override { return this; }
    bool IsInEvadeMode() const { return evade; }
    bool CanNotReachTarget() const { return unreachable; }
    @EVADING_ATTACKS@
};
struct Player : Unit
{
    bool IsValidAttackTarget(Unit const* unit) const { return unit->valid; }
    float GetDistance(Unit const* unit) const { return unit->distance; }
    bool IsWithinLOSInMap(Unit const* unit) const { return unit->visible; }
};
struct PlayerbotAI
{
    Unit* current = nullptr;
    GuidVector possible;
    std::map<ObjectGuid, Unit*> units;
    Unit* GetUnit(ObjectGuid guid) const
    {
        auto const found = units.find(guid);
        return found == units.end() ? nullptr : found->second;
    }
    template <typename T> T Value(std::string const& name) const
    {
        if constexpr (std::is_same_v<T, Unit*>)
        {
            assert(name == "current target");
            return current;
        }
        else
        {
            assert(name == "possible targets");
            return possible;
        }
    }
};
#define AI_VALUE(type, name) botAI->Value<type>(name)
struct Event {};
struct RcOnyKillWhelpsAction
{
    Player* bot;
    PlayerbotAI* botAI;
    Unit* attacked = nullptr;
    bool attackResult = true;
    bool Attack(Unit* target) { attacked = target; return attackResult; }
    bool Execute(Event);
};

struct ConfigManager
{
    std::map<std::string, bool> flags;
    template <typename T> T GetOption(std::string const& key, T fallback) const
    {
        auto const found = flags.find(key);
        return found == flags.end() ? fallback : T(found->second);
    }
} configManager;
auto* sConfigMgr = &configManager;
namespace RaidClear
{
    @CONFIG@;
    @REGISTRY@
    Config sConfig;
    namespace BlackwingLair { void LoadSpots() {} }
    namespace TempleOfAhnQiraj { void LoadSpots() {} }
    @LOAD_CONFIG@
}

#include "production.inc"

int main()
{
    auto const* raid = RaidClear::FindRaid(249);
    assert(raid && std::string(raid->strategy) == "rc ony" && std::string(raid->confKey) == "OnyxiasLair");
    RaidClear::LoadConfig();
    assert(RaidClear::sConfig.IsRaidEnabled(249) && !RaidClear::sConfig.IsRaidEnabled(0));
    configManager.flags["RaidClear.OnyxiasLair.Enable"] = false;
    RaidClear::LoadConfig();
    assert(!RaidClear::sConfig.IsRaidEnabled(249) && RaidClear::sConfig.IsRaidEnabled(409));
    configManager.flags["RaidClear.OnyxiasLair.Enable"] = true;
    configManager.flags["RaidClear.Enable"] = false;
    RaidClear::LoadConfig();
    assert(!RaidClear::sConfig.IsRaidEnabled(249));

    Player bot;
    PlayerbotAI ai;
    Creature vanilla(NPC_ONYXIAN_WHELP_40), wrath(NPC_ONYXIAN_WHELP), other(999);
    Creature boss(NPC_ONYXIA), vanillaBoss(NPC_ONYXIA_40);
    assert(IsWhelp(&vanilla) && IsWhelp(&wrath) && !IsWhelp(&other));
    assert(!IsEvadingMob(nullptr) && !IsEvadingMob(&bot));
    boss.evade = vanillaBoss.evade = true;
    assert(!IsEvadingMob(&boss) && !IsEvadingMob(&vanillaBoss));
    ai.units = {{1, &vanilla}, {2, &wrath}, {3, &other}, {4, &boss}, {5, &vanillaBoss}};
    vanilla.distance = 3; wrath.distance = 8; other.distance = 1;
    GuidVector const all = {0, 3, 4, 5, 2, 1};
    assert(NearestHittable(&ai, &bot, all, true) == &vanilla);
    assert(NearestHittable(&ai, &bot, all, false) == &other);
    assert(!NearestHittable(&ai, &bot, {0, 3, 4, 5}, true));
    assert(!NearestHittable(&ai, &bot, {0, 4, 5}, false));

    // Both native evade causes and ordinary attack refusals exclude each version.
    for (Creature* whelp : {&vanilla, &wrath})
    {
        ai.units[6] = whelp;
        whelp->evade = true;
        assert(IsEvadingMob(whelp) && !NearestHittable(&ai, &bot, {6}, true));
        whelp->evade = false; whelp->unreachable = true;
        assert(IsEvadingMob(whelp) && !NearestHittable(&ai, &bot, {6}, true));
        whelp->unreachable = false;
        for (bool* gate : {&whelp->alive, &whelp->inWorld, &whelp->visible, &whelp->valid})
        {
            *gate = false;
            assert(!NearestHittable(&ai, &bot, {6}, true));
            *gate = true;
        }
        assert(NearestHittable(&ai, &bot, {6}, true) == whelp);
    }

    RcOnyKillWhelpsAction action{&bot, &ai};
    ai.possible = {0, 3, 4, 5, 2, 1};
    assert(action.Execute({}) && action.attacked == &vanilla);
    // Keep either current whelp even when another is nearer.
    for (Creature* current : {&vanilla, &wrath})
    {
        Creature nearer(current->GetEntry());
        nearer.distance = 1;
        ai.units[6] = current; ai.units[7] = &nearer;
        ai.possible = {6, 7};
        ai.current = current; action.attacked = nullptr;
        current->distance = 20;
        assert(!action.Execute({}) && !action.attacked);
        current->distance = current == &vanilla ? 3 : 8;
        ai.units.erase(7);
    }
    ai.possible = all;
    ai.current = &other; action.attacked = nullptr;
    assert(action.Execute({}) && action.attacked == &vanilla);
    // Leave an evading or dead current Vanilla whelp for a normal hittable one.
    ai.current = &vanilla;
    vanilla.evade = true;
    assert(action.Execute({}) && action.attacked == &wrath);
    vanilla.evade = false; vanilla.alive = false;
    assert(action.Execute({}) && action.attacked == &wrath);
    vanilla.alive = true; ai.current = nullptr;
    action.attackResult = false;
    assert(!action.Execute({}) && action.attacked == &vanilla);
    ai.possible = {0, 3, 4, 5}; action.attacked = nullptr;
    assert(!action.Execute({}) && !action.attacked);
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source_argument(parser, help='mod-raid-clear/src directory')
    args = parser.parse_args()
    core = prepared_core()
    src = args.source or core / 'modules/mod-raid-clear/src'
    ony = src / 'Raids/OnyxiasLair'
    header = (ony / 'OnyRaidClear.h').read_text()
    source = (ony / 'OnyRaidClear.cpp').read_text()
    module = (src / 'RaidClearModule.cpp').read_text()
    registry = (src / 'RaidClearRegistry.h').read_text()
    contexts = (src / 'RaidClearContexts.h').read_text()
    ip = core / 'modules/mod-individual-progression/src'
    natives = (ip / 'vanillaScripts/onyxias_lair.h').read_text()
    for name, entry in (('NPC_ONYXIA', 10184), ('NPC_ONYXIAN_WHELP', 11262),
                        ('NPC_ONYXIA_40', 301000), ('NPC_ONYXIAN_WHELP_40', 301001)):
        pattern = rf'\b{name}\s*=\s*{entry}\b'
        assert re.search(pattern, natives) and re.search(pattern, header), name
    assert 'me->SummonCreature(NPC_ONYXIAN_WHELP_40,' in (ip / 'vanillaScripts/boss_onyxia.cpp').read_text()
    assert re.search(r'\bONYXIA_40\s*=\s*301000\b', (ip / 'IndividualProgression.h').read_text())
    assert 'class RcOnyKillWhelpsAction : public AttackAction' in header
    playerbots = core / 'modules/mod-playerbots/src'
    attack = function((playerbots / 'Ai/Base/Actions/AttackAction.cpp').read_text(), 'bool AttackAction::Attack(')
    for gate in ('!target->IsInWorld()', 'target->isDead()', '!bot->IsWithinLOSInMap(target)',
                 '!bot->IsValidAttackTarget(target)'):
        assert gate in attack, gate
    lookup = function((playerbots / 'Bot/PlayerbotAI.cpp').read_text(), 'Unit* PlayerbotAI::GetUnit(ObjectGuid guid)')
    assert 'ObjectAccessor::GetUnit(*bot, guid)' in lookup
    assert 'typedef std::vector<ObjectGuid> GuidVector;' in (
        core / 'src/server/game/Entities/Object/ObjectGuid.h').read_text()
    assert 'if (IsCreature())' in function((core / 'src/server/game/Entities/Object/Object.h').read_text(),
                                         'Creature const* ToCreature() const')
    assert 'creators["rc ony"] = &RaidClearStrategyContext::ony;' in contexts
    assert 'new RaidClearOnyxiasLairStrategy(botAI)' in function(contexts, 'static Strategy* ony(')
    assert 'creators["rc ony kill whelps"] = &RaidClearActionContext::ony_kill_whelps;' in contexts
    assert 'new RcOnyKillWhelpsAction(botAI)' in function(contexts, 'static Action* ony_kill_whelps(')
    assert 'OnyxiasLair::AddScripts();' in function(module, 'void AddRaidClearScripts()')
    assert re.search(r'^RaidClear\.OnyxiasLair\.Enable\s*=\s*1\s*$',
                     (src.parent / 'conf/mod_raid_clear.conf.dist').read_text(), re.MULTILINE)

    replacements = {
        '@CREATURES@': function(header, 'enum Creatures : uint32'),
        '@EVADING_ATTACKS@': function((core / 'src/server/game/Entities/Creature/Creature.h').read_text(),
                                     'bool IsEvadingAttacks() const'),
        '@CONFIG@': function((src / 'RaidClearConfig.h').read_text(), 'struct Config'),
        '@REGISTRY@': function(registry, 'struct RaidEntry') + ';\n' +
                     re.search(r'inline constexpr std::array<RaidEntry, \d+> Raids = \{\{.*?\}\};',
                               registry, re.DOTALL).group(0) + '\n' +
                     function(registry, 'inline RaidEntry const* FindRaid('),
        '@LOAD_CONFIG@': function(module, 'void LoadConfig()'),
    }
    harness = HARNESS
    for key, value in replacements.items():
        harness = harness.replace(key, value)
    production = '\n\n'.join(function(source, signature) for signature in (
        'bool IsWhelp(', 'bool IsEvadingMob(', 'Unit* NearestHittable(', 'bool RcOnyKillWhelpsAction::Execute(',
    ))
    with tempfile.TemporaryDirectory(prefix='onyxia-integration-') as directory:
        work = Path(directory)
        (work / 'fixture.cpp').write_text(harness)
        (work / 'production.inc').write_text(production)

        def build(tree, output):
            return [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', str(tree / 'fixture.cpp'), '-o', str(output)]

        executable = work / 'fixture'
        subprocess.run(build(work, executable), check=True)
        result = run_fixture([str(executable)])
        assert result.returncode == 0, result.stdout + result.stderr
        reject_mutants(work, (
            ('Vanilla whelps omitted from selection', 'production.inc',
             'whelpsOnly ? !IsWhelp(unit)', 'whelpsOnly ? unit->GetEntry() != NPC_ONYXIAN_WHELP'),
            ('current Vanilla whelp discarded', 'production.inc',
             'current->IsAlive() && IsWhelp(current)',
             'current->IsAlive() && current->GetEntry() == NPC_ONYXIAN_WHELP'),
        ), build, 'Onyxia integration')
    print('Onyxia integration: configuration, registration and native Vanilla/core whelp selection verified')


if __name__ == '__main__':
    main()
