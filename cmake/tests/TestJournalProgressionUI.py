"""Exercise progression-step filtering with the Journal's real lockout decoder."""

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

from FixtureSupport import REPOSITORY, prepared_core, source_argument


PREAMBLE = r'''
assert(_VERSION == "Lua 5.1")
bit = { band = function(a, b)
    local result, place = 0, 1
    while a > 0 and b > 0 do
        if a % 2 == 1 and b % 2 == 1 then result = result + place end
        a, b, place = math.floor(a / 2), math.floor(b / 2), place * 2
    end
    return result
end }
GetTime = function() return 100 end
local cache = {
    list = {
        { "I", 1, 409, 1, 0, 60, 60, 60, 0, "Raid", "Zone" },
        { "V", 1, 100, 0, 0, 40, 60, 0, "40 player" },
    },
    bosses = { [1] = {
        { 0, 0, 0, 0, 1, "First boss" },
        { 1, 0, 0, 0, 1, "Milestone" },
        { 2, 0, 0, 0, 1, "Optional boss" },
    } },
}
Journal = {
    API = 1, state = 0, QUEST = {}, CreateInset = true, CreateScrollArea = true,
    RegisterTab = true, Has = function() return true end, On = function() end,
    Unescape = function(text) return text end,
    Cache = function() return cache end,
    Duration = function(seconds) return tostring(seconds) end,
    Request = function(command, fields, done)
        assert(command == "S" and fields[1] == "1")
        done({ meta = { "S", 0 }, rows = { { "V", 100, 0, 0, 1, 3600, 1 } } })
    end,
}
dofile(arg[1])
JournalProgression = { tiers = { [0] = {
    stage = 0, next = 1, sections = { { raid = 409, milestone = "Milestone" } },
} } }
'''

CHECKS = r'''
local tier = P.tiers[0]
local db = {}
@COLLECT@
local all = collect(tier)
assert(#all == 4, "all three raid bosses are shown before filtering")
assert(all[1].done == 1 and all[1].total == 2, "the lockout contributes one completed required boss")
assert(all[2].state == ST.KILLED and all[2].done, "the real lockout decoder marks the first boss done")
assert(all[3].state == ST.BOSS and not all[3].done, "the milestone is still alive")
assert(all[4].optional and all[4].state == ST.OPTIONAL, "the last boss is optional")
db.hideDone = true
local pending = collect(tier)
assert(#pending == 3, "Hide steps I've done removes a boss killed this lockout")
assert(pending[2].row.boss.name == "Milestone" and pending[3].optional,
    "the filter retains unfinished required and optional bosses")
assert(pending[1].done == 1 and pending[1].total == 2, "filtering preserves completion totals")
S.stage = 1
local passed = collect(tier)
assert(#passed == 2 and passed[2].optional, "completed stages hide required bosses and retain optional ones")
db.hideDone = false
assert(#collect(tier) == 4, "turning off the filter restores completed bosses")
print("Journal progression: lockout completion, filters, counts and optional bosses passed")
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source_argument(parser, 'addon', default=REPOSITORY / '.module-cache/prepared-source-addons/JournalProgression')
    source_argument(parser, 'journal', default=prepared_core() / 'modules/mod-forever-journal')
    parser.add_argument('--lua', default=shutil.which('lua5.1') or shutil.which('lua'))
    args = parser.parse_args()
    if not args.lua:
        parser.error('Lua 5.1 is required')
    production = (args.addon / 'Progression.lua').read_text()
    prefix = production[:production.index('local function build(panel)')]
    start = production.index('\tlocal function collect(t)')
    collect = production[start:production.index('\n\trender = function ()', start)]
    with tempfile.TemporaryDirectory(prefix='journal-progression-ui-') as temporary:
        fixture = Path(temporary) / 'fixture.lua'

        def run(source):
            fixture.write_text(PREAMBLE + prefix + CHECKS.replace('@COLLECT@', source))
            return subprocess.run([args.lua, str(fixture), str(args.journal / 'addon/Journal/Data.lua')],
                                  capture_output=True, text=True, timeout=20, check=False)

        result = run(collect)
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout.strip(), flush=True)
        before = 'if not (db.hideDone and done) then'
        assert collect.count(before) == 2, 'both raid and ordinary steps use their completed state'
        mutant = collect.replace(before, 'if not (db.hideDone and state == ST.DONE) then', 1)
        result = run(mutant)
        assert result.returncode != 0 and 'removes a boss killed this lockout' in result.stderr, \
            'restoring the lockout filter bug did not fail its regression case:\n' + result.stdout + result.stderr
        print('Journal progression mutation rejected: killed bosses left visible', flush=True)


if __name__ == '__main__':
    main()
