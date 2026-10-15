"""Keep earned TBC Tree of Life in the native healer blanketing decision.

The production trigger, bridge and spell resolver run together. Fake spellbook
records model owned native/custom spells; the pinned dataset supplies the TBC
grant contract, including the castable form and its same-name passive partner.
"""

import argparse
from pathlib import Path
import re
import subprocess
import tempfile

from FixtureSupport import cxx, function, prepared_core, run_fixture


repo = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, help='prepared Playerbots src directory')
parser.add_argument('--era-source', type=Path, help='prepared EraTalents module directory')
args = parser.parse_args()
core = prepared_core(repo)
module = args.source or core / 'modules/mod-playerbots/src'
era = args.era_source or core / 'modules/mod-era-talents'

dataset = (era / 'era-data/tbc/druid.yaml').read_text()
tree = dataset[dataset.index('  - id: 20161\n'):dataset.index('\nhelpers:')]
assert re.search(r'grants:\s+1: \[946276\]', tree), 'TBC form must be the earned clone'
assert re.search(r'^- id: 946276\n  name: Tree of Life\n  template: 33891\n', dataset, re.MULTILINE)
assert re.search(r'^- id: 946265\n  name: Tree of Life\n', dataset, re.MULTILINE)
resolver = function((era / 'src/EraTalentBots.cpp').read_text(),
                    'uint32 EraTalentBots_ResolveSpellId(Player* bot, uint32 stockSpellId)')
trigger = function((module / 'Ai/Class/Druid/DruidTriggers.cpp').read_text(),
                   'bool HealerShouldAttackAndNotBlanketingTrigger::IsActive()')

fixture = r'''
#include "EraTalentBridge.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <cwctype>
#include <iostream>
#include <map>
#include <mutex>
#include <string>
#include <unordered_map>

using uint8 = std::uint8_t;
constexpr int PLAYERSPELL_REMOVED = 1, SPELL_EFFECT_LEARN_SPELL = 36;
constexpr uint32 SPELL_TREE_OF_LIFE = 33891, BOT_STATE_COMBAT = 0;
enum EraId { ERA_VANILLA, ERA_TBC, ERA_WOTLK };
namespace EraTalents { constexpr uint32 ERA_CUSTOM_BAND_LOW = 920000, ERA_CUSTOM_BAND_HIGH = 950000; }
constexpr uint8 LOCALE_enUS = 0;
struct PlayerSpell
{
    int State = 0;
    bool Active = true, currentSpec = true;
    bool IsInSpec(uint8) const { return currentSpec; }
};
struct SpellInfo
{
    struct EffectInfo { int Effect = 0; };
    std::array<EffectInfo, 3> Effects{};
    std::array<char const*, 1> SpellName{{"Tree of Life"}};
    bool passive = false;
    bool IsPassive() const { return passive; }
};
struct Player
{
    std::map<uint32, PlayerSpell*> spells;
    bool grouped = true, gated = false;
    EraId era = ERA_TBC;
    bool HasSpell(uint32 id) const { return spells.contains(id) && spells.at(id)->State != PLAYERSPELL_REMOVED; }
    auto const& GetSpellMap() const { return spells; }
    uint32 GetGUID() const { return 1; }
    uint8 GetActiveSpec() const { return 0; }
    Player* GetGroup() { return grouped ? this : nullptr; }
};
struct SpellMgr
{
    std::map<uint32, SpellInfo> spells;
    SpellInfo const* GetSpellInfo(uint32 id) const
    { auto it = spells.find(id); return it == spells.end() ? nullptr : &it->second; }
    uint8 GetSpellRank(uint32) const { return 0; }
} spells;
auto* sSpellMgr = &spells;
bool EraHasTalentTrees(Player*, EraId era) { return era < ERA_WOTLK; }
namespace EraTalentBots { bool IsEraManaged(Player* player) { return !player->gated; } }
namespace EraTransition { EraId StoredEra(Player* player) { return player->era; } }
std::mutex g_botCacheMutex;
std::unordered_map<uint32, std::unordered_map<uint32, uint32>> g_resolveCache;
bool Utf8toWStr(std::string const& text, std::wstring& wide)
{ wide.assign(text.begin(), text.end()); return true; }
void wstrToLower(std::wstring& text) { std::transform(text.begin(), text.end(), text.begin(), std::towlower); }
bool Utf8FitTo(std::string const& text, std::wstring const& wide)
{ std::wstring value; Utf8toWStr(text, value); wstrToLower(value); return value == wide; }
''' + resolver + r'''
struct PlayerbotAI
{
    bool blanketing = true;
    bool HasStrategy(std::string const& name, uint32 state) const
    { assert(name == "blanketing" && state == BOT_STATE_COMBAT); return blanketing; }
};
struct HealerShouldAttackTrigger
{
    Player* bot;
    PlayerbotAI* botAI;
    bool ready = true;
    int calls = 0;
    bool IsActive() { ++calls; return ready; }
};
struct HealerShouldAttackAndNotBlanketingTrigger : HealerShouldAttackTrigger { bool IsActive(); };
''' + trigger + r'''
int main()
{
    Player bot;
    PlayerbotAI ai;
    HealerShouldAttackAndNotBlanketingTrigger trigger{{&bot, &ai}};
    PlayerSpell owned, inactive, removed, wrongSpec;
    inactive.Active = false;
    removed.State = PLAYERSPELL_REMOVED;
    wrongSpec.currentSpec = false;
    spells.spells[33891] = SpellInfo{};
    spells.spells[946276] = SpellInfo{};
    spells.spells[946265] = SpellInfo{};
    spells.spells[946265].passive = true;

    for (uint32 form : {33891u, 946276u})
    {
        bot.spells = {{form, &owned}};
        if (form == 946276)
            bot.spells[946265] = &owned;
        g_resolveCache.clear();
        assert(EraKnown(&bot, 33891) == form); // prefer the castable form over its same-name passive
        for (bool group : {false, true})
            for (bool blanket : {false, true})
                for (bool ready : {false, true})
                {
                    bot.grouped = group; ai.blanketing = blanket; trigger.ready = ready; trigger.calls = 0;
                    assert(trigger.IsActive() == (ready && !(group && blanket)));
                    assert(trigger.calls == (group && blanket ? 0 : 1));
                }
    }

    bot.grouped = ai.blanketing = trigger.ready = true;
    for (PlayerSpell* record : {&inactive, &removed, &wrongSpec})
    {
        bot.spells = {{946276, record}};
        g_resolveCache.clear();
        assert(!EraKnown(&bot, 33891) && trigger.IsActive());
    }
    bot.spells.clear(); g_resolveCache.clear();
    assert(trigger.IsActive()); // no earned form never suppresses healer DPS
    bot.spells = {{946276, &owned}};
    for (EraId era : {ERA_TBC, ERA_WOTLK})
        for (bool gated : {false, true})
        {
            bot.era = era; bot.gated = gated; g_resolveCache.clear();
            assert(trigger.IsActive() == (gated || era == ERA_WOTLK));
        }
    bot.spells = {{33891, &owned}}; g_resolveCache.clear();
    assert(!trigger.IsActive()); // native Wrath retains the stock fast path
    std::cout << "Era Tree of Life: earned/native blanketing, base decisions and spellbook gates passed\n";
}
'''

with tempfile.TemporaryDirectory(prefix='portable-era-tree-') as temporary:
    work = Path(temporary)
    (work / 'Define.h').write_text('#pragma once\n#include <cstdint>\nusing uint32 = std::uint32_t;\n')
    source = work / 'fixture.cpp'
    executable = work / 'fixture'
    for mutated in (False, True):
        text = fixture
        if mutated:
            text = text.replace('EraKnown(bot, SPELL_TREE_OF_LIFE)', 'bot->HasSpell(SPELL_TREE_OF_LIFE)')
            assert text != fixture, 'Tree of Life mutation did not apply'
        source.write_text(text)
        subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-no-pie',
                        '-I', str(work), '-I', str(module / 'Bot'), str(source), '-o', str(executable)], check=True)
        result = run_fixture([str(executable)])
        if mutated:
            assert result.returncode != 0, 'Tree of Life fixture accepted the stock-only mutation'
            print('Era Tree of Life mutation rejected: stock-only blanketing guard')
        else:
            assert result.returncode == 0, result.stdout + result.stderr
            print(result.stdout, end='')
