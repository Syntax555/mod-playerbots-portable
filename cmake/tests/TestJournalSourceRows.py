"""Send Journal collection sources from the production server rows to the production addon parser.

The module's Row() runs with a format double that, like the core's fmt-based
StringFormat, silently drops arguments without a placeholder. Its rows pass
through the addon's own row parser, source builder and goal tracker under
Lua 5.1: a heroic boss's drop must name its base creature, whose entry the
combat log reports, so its kills count toward the tracked goal. Mutation checks
remove the field on either side of the protocol.
"""

import argparse
from pathlib import Path
import shutil
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


def lua_function(source, signature):
    """A top-level Lua function, through the first unindented end after its signature."""
    start = source.index(signature)
    return source[start:source.index('\nend\n', start) + len('\nend\n')]


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, 'module', default=prepared_core() / 'modules/mod-forever-journal')
args = parser.parse_args()
core = prepared_core()
lua = shutil.which('lua5.1')
if not lua:
    raise SystemExit('lua5.1 is required')
collections = (args.module / 'src/JournalCollections.cpp').read_text()
journal = (args.module / 'src/Journal.cpp').read_text()
addon = args.module / 'addon/Journal'
addon_core = (addon / 'Core.lua').read_text()
addon_sources = (addon / 'CollectionData.lua').read_text()
tracker = (addon / 'GoalTracker.lua').read_text()

# The core formats through fmt, which ignores an argument that has no placeholder.
native_format = function((core / 'src/common/Utilities/StringFormat.h').read_text(),
                         '    inline std::string StringFormat(FormatStringView fmt, Args&&... args)')
assert 'return fmt::vformat(fmt, fmt::make_format_args(args...));' in native_format
assert 'std::unordered_map<uint32, uint32> sBaseOf;' in collections
assert 'local Unescape = J.Unescape' in addon_sources
# The tracker counts kills by the entry in the creature's GUID, which is the spawned base creature.
assert 'local entry = tonumber(destGUID:sub(7, 12), 16)' in tracker and 'killFor[entry]' in tracker

parts = {
    'row': function(collections, '        std::string Row(Source const& s, std::size_t i)'),
    'sources': lua_function(addon_sources, 'local function buildSources(rows)'),
    'kills': lua_function(tracker, 'local function watchKills(list)'),
}
production = '\n'.join([
    function(collections, '        struct Spot') + ';',
    function(collections, '        struct Source') + ';',
    'std::unordered_map<uint32, uint32> sBaseOf;',
    function(collections, '        uint32 BaseOf(uint32 entry)'),
    function(journal, '    std::string Escape(std::string_view text, std::size_t maxLength)'),
    function(collections, '        std::string NoteText(std::string const& text)'),
])

harness = r'''
#include <cstdint>
#include <format>
#include <iostream>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
namespace Acore
{
    // Like fmt::vformat, std::vformat ignores surplus arguments and throws for a missing one.
    template <class... Args> std::string StringFormat(std::string_view fmt, Args&&... args)
    {
        return std::vformat(fmt, std::make_format_args(args...));
    }
}
@PRODUCTION@
@ROW@

int main()
{
    constexpr uint32 SKADI = 26693, SKADI_HEROIC = 30807, CHEST = 193905;
    sBaseOf[SKADI_HEROIC] = SKADI;
    std::vector<Source> sources(4);
    sources[0].kind = 'D';              // a heroic boss's drop: the loot is on the difficulty entry
    sources[0].id = SKADI_HEROIC;
    sources[0].a = 100;
    sources[0].b = 575;
    sources[0].c = 3;
    sources[0].reqState = 13;
    sources[0].variant = 1;
    sources[0].name = "Skadi the Ruthless";
    sources[0].where = "Utgarde Pinnacle";
    sources[0].extra = "Heroic, 5 Player";
    sources[0].spot.placed = true;
    sources[1] = sources[0];            // a normal drop is its own base creature
    sources[1].id = SKADI;
    sources[1].variant = 255;
    sources[1].extra.clear();
    sources[2].kind = 'P';
    sources[2].id = SKADI_HEROIC;
    sources[2].a = 250;
    sources[2].name = "Skadi the Ruthless";
    sources[3].kind = 'G';
    sources[3].id = CHEST;
    sources[3].a = 5000;
    sources[3].name = "Cache of Eregos";
    for (std::size_t i = 0; i < sources.size(); ++i)
        std::cout << (i ? ";" : "") << Row(sources[i], i + 1);
    std::cout << '\n';
}
'''

script = r'''
local J = {}
@UNESCAPE@
local Unescape = J.Unescape
@PARSE@
@SOURCES@
local killFor = {}
local watching = false
local combat = {
    RegisterEvent = function (_, event) assert(event == "COMBAT_LOG_EVENT_UNFILTERED") watching = true end,
    UnregisterEvent = function () watching = false end,
}
@KILLS@

local rows = {}
parseRows([[@ROWS@]], rows)
local list = buildSources(rows)
assert(#list == 4, "four sources")

local heroic, normal, pocket, chest = list[1], list[2], list[3], list[4]
assert(heroic.kind == "D" and heroic.index == 1 and heroic.creature == 30807 and heroic.chance == 100)
assert(heroic.instance == 575 and heroic.boss == 3 and heroic.reqState == 13 and heroic.placed and not heroic.rare)
assert(heroic.name == "Skadi the Ruthless" and heroic.where == "Utgarde Pinnacle")
assert(heroic.variant == 1 and heroic.tabs == "Heroic, 5 Player")
assert(heroic.base == 26693, "a heroic drop names its base creature")
assert(normal.creature == 26693 and normal.base == 26693 and normal.variant == nil and normal.tabs == "")
assert(pocket.kind == "P" and pocket.creature == 30807 and pocket.chance == 250 and pocket.base == 26693)
assert(chest.kind == "G" and chest.object == 193905 and chest.chance == 5000 and chest.name == "Cache of Eregos")

-- A heroic kill arrives under the base entry; both entries count toward the goal.
watchKills({ heroic })
assert(watching and killFor[30807] and killFor[26693], "kills of the spawned base creature count")
watchKills({ chest })
assert(not watching and next(killFor) == nil)
'''.replace('@UNESCAPE@', lua_function(addon_core, 'function J.Unescape(text)')).replace(
    '@PARSE@', lua_function(addon_core, 'local function parseRows(text, into)'))

mutations = (
    ('drop row without its base creature', 'row',
     '"D,{},{},{},{},{},{},{},{},{},{},{},{},{}"', '"D,{},{},{},{},{},{},{},{},{},{},{},{}"'),
    ('pickpocket row without its base creature', 'row', '"P,{},{},{},{},{},{},{},{}"', '"P,{},{},{},{},{},{},{}"'),
    ('addon ignores the base creature of a drop', 'sources', 's.base = r[14]', 's.base = nil'),
    ('base creature kills not counted', 'kills', 'if s.base then killFor[s.base] = true end', ''),
)

with tempfile.TemporaryDirectory(prefix='portable-journal-rows-') as temporary:
    directory = Path(temporary)

    def build(variant, tag):
        source = directory / f'{tag}.cpp'
        source.write_text(harness.replace('@PRODUCTION@', production).replace('@ROW@', variant['row']))
        executable = directory / tag
        subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
                        *SANITIZER_FLAGS, str(source), '-o', str(executable)], check=True)
        rows = run_fixture([str(executable)], f'Journal source rows {tag}')
        if rows.returncode:
            return rows
        client = directory / f'{tag}.lua'
        client.write_text(script.replace('@SOURCES@', variant['sources']).replace('@KILLS@', variant['kills'])
                          .replace('@ROWS@', rows.stdout.strip()))
        return run_fixture([lua, str(client)], f'Journal source rows {tag} addon')

    result = build(parts, 'production')
    assert result.returncode == 0, result.stderr
    print('Journal source rows passed')
    reject_part_mutants(parts, mutations, build, 'Journal source rows')
