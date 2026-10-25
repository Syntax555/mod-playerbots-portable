"""Check that a bot's spellbook leaves out the spells the client's own spellbook hides.

The bridge's production spellbook builder, its entry type and sort order run on
the core's SpellAttr0 values. Fixtures supply a bot's spell map with the
attributes of the listed client spells; no realm is started.
"""

import argparse
import os
from pathlib import Path
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
source_argument(parser, 'core', help='prepared core source directory')
args = parser.parse_args()
repository = Path(__file__).resolve().parents[2]
core = args.core or prepared_core(repository)
bridge = (core / 'modules/mod-multibot-bridge/src/MultiBotBridge.cpp').read_text()
defines = (core / 'src/server/shared/SharedDefines.h').read_text()


def block(source, start, end):
    begin = source.index(start)
    return source[begin:source.index(end, begin) + len(end)]


fixture = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <map>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

using uint8 = std::uint8_t;
using uint32 = std::uint32_t;

@ATTRIBUTES@

enum PlayerSpellState { PLAYERSPELL_UNCHANGED, PLAYERSPELL_CHANGED, PLAYERSPELL_NEW, PLAYERSPELL_REMOVED };
struct PlayerSpell
{
    PlayerSpellState State = PLAYERSPELL_UNCHANGED;
    bool Active = true;
    uint8 specMask = 1;
};
using PlayerSpellMap = std::unordered_map<uint32, PlayerSpell*>;

struct SpellInfo
{
    uint32 Attributes = 0;
    uint32 SchoolMask = 1;
    char const* SpellName[16] = {};
    bool HasAttribute(SpellAttr0 attribute) const { return (Attributes & attribute) != 0; }
    bool IsPassive() const { return HasAttribute(SPELL_ATTR0_PASSIVE); }
};

struct SpellMgr
{
    std::map<uint32, SpellInfo> spells;
    SpellInfo const* GetSpellInfo(uint32 id) const
    {
        auto const found = spells.find(id);
        return found == spells.end() ? nullptr : &found->second;
    }
} spellMgr;
#define sSpellMgr (&spellMgr)

struct Player
{
    PlayerSpellMap spells;
    PlayerSpellMap const& GetSpellMap() const { return spells; }
    uint8 GetActiveSpecMask() const { return 1; }
};

// Profession spells leave through the bridge's skill line check; none of these is one.
bool IsSpellbookExcludedSpell(uint32) { return false; }

@PRODUCTION@

int main()
{
    // Spell.dbc attributes and enUS names of the client's spells (3.3.5a build 12340).
    struct Known { uint32 id; uint32 attributes; char const* name; };
    Known const known[] = {
        {6603, 0x00000010, "Attack"},
        {59752, 0x00000000, "Every Man for Himself"},
        {20154, 0x00050000, "Seal of Righteousness"},
        {3365, 0x00000190, "Opening"},
        {6233, 0x00000090, "Closing"},
        {7267, 0x0c000090, "Grovel"},
        {22027, 0x00000090, "Remove Insignia"},
        {7266, 0x10000190, "Duel"},
        {7355, 0x10800090, "Stuck"},
        {63644, 0x10000080, "Activate Second Talent Specialization"},
        {2479, 0x09000120, "Honorless Target"},
        {2330, 0x00010020, "Minor Healing Potion"},
        {20208, 0x00000040, "Paladin Passive"},
    };
    PlayerSpell learned[std::size(known)];
    Player bot;
    for (size_t i = 0; i < std::size(known); ++i)
    {
        SpellInfo& info = spellMgr.spells[known[i].id];
        info.Attributes = known[i].attributes;
        info.SpellName[0] = known[i].name;
        bot.spells[known[i].id] = &learned[i];
    }

    std::set<std::string> shown;
    for (SpellbookEntryData const& entry : BuildSpellbookEntries(&bot))
        shown.insert(entry.spellName);
    assert((shown == std::set<std::string>{"Attack", "Every Man for Himself", "Seal of Righteousness"}));
    std::cout << "Bot spellbooks list what the client's own spellbook shows: hidden spells, trade skill "
                 "recipes and passives stay out\n";
}
'''

attributes = block(defines, 'enum SpellAttr0 : uint32', '};')
production = '\n\n'.join([
    block(bridge, 'struct SpellbookEntryData', '};'),
    function(bridge, 'static bool CompareSpellbookEntries('),
    function(bridge, 'std::vector<SpellbookEntryData> BuildSpellbookEntries('),
])
mutations = [
    ('hidden spells', 'spellInfo->HasAttribute(SPELL_ATTR0_DO_NOT_DISPLAY) || ', ''),
    ('trade skill recipes', ' || spellInfo->HasAttribute(SPELL_ATTR0_IS_TRADESKILL)', ''),
]
compiler = cxx()
with tempfile.TemporaryDirectory(prefix='multibot-spellbook-display-') as directory:
    directory = Path(directory)
    cases = [('production', production, True)]
    for label, old, new in mutations:
        if production.count(old) != 1:
            raise AssertionError(f'{label} mutation was not applied')
        cases.append((label, production.replace(old, new), False))
    for index, (label, body, expect_success) in enumerate(cases):
        source = directory / f'case-{index}.cpp'
        executable = directory / (f'case-{index}' + ('.exe' if os.name == 'nt' else ''))
        source.write_text(fixture.replace('@ATTRIBUTES@', attributes).replace('@PRODUCTION@', body))
        subprocess.run([compiler, '-std=c++20', '-Wall', '-Wextra', '-Werror', *SANITIZER_FLAGS,
                        str(source), '-o', str(executable)], check=True)
        result = subprocess.run([str(executable)], text=True, capture_output=True, check=False, timeout=TIMEOUT)
        if expect_success:
            if result.returncode:
                raise AssertionError(result.stderr or result.stdout)
            print(result.stdout.strip())
        elif result.returncode == 0:
            raise AssertionError(f'The spellbook display fixture did not reject {label}')
        else:
            print(f'Spellbook display mutation rejected: {label}')
