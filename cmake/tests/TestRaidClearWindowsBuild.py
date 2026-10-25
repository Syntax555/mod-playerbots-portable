"""Compile Raid Clear's fixed spots and Core Hound selection with Windows macros."""

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from FixtureSupport import (
    TIMEOUT,
    cxx,
    function,
    prepared_core,
    run_fixture,
    source_argument,
)


HARNESS = r'''
#include <cassert>
#include <cstdint>
#include <list>
#include <optional>
#include <string>
#include <vector>
using uint32 = std::uint32_t;
#ifdef RAID_WINDOWS_MACROS
// The Windows SDK leaves both legacy memory-model macros defined and empty.
#define NEAR
#define near
#endif
#include "FixedSpots.h"
NATIVE_CONSTANTS
struct Creature;
struct Unit
{
    std::list<Creature*> neighbours;
    bool IsAlive() const { return true; }
    bool IsInCombat() const { return true; }
    bool HasAura(uint32 spell) const { assert(spell == SPELL_PLAY_DEAD); return false; }
    bool IsWithinLOSInMap(Unit const*) const { return true; }
    uint32 GetHealth() const { return 100; }
    NATIVE_SEARCH_SIGNATURE
    {
        assert(radius == CORE_HOUND_LINK_RANGE && entry == NPC_CORE_HOUND);
        creatureList.insert(creatureList.end(), neighbours.begin(), neighbours.end());
    }
};
struct Creature : Unit {};
struct Player : Unit { bool IsValidAttackTarget(Unit const*) const { return true; } };
namespace Spots = RaidClear::Spots;
#include "production.inc"
int main()
{
#ifdef RAID_WINDOWS_MACROS
#if !defined(NEAR) || !defined(near)
#error The production code must leave the Windows macros defined
#endif
#endif
    SpotWant want;
    assert(SpotNear(want) == 3.5f);
    want.tank = true;
    assert(SpotNear(want) == 2.0f);
    Player bot;
    Creature down, standing;
    down.neighbours = {&standing};
    Hounds hounds;
    hounds.down = {&down};
    assert(NextHound(&bot, hounds) == &standing);
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source_argument(parser, help='mod-playerbots/src/Ai/Raid/RaidClear to check instead of the prepared one')
    args = parser.parse_args()
    core = prepared_core()
    source = args.source or core / 'modules/mod-playerbots/src/Ai/Raid/RaidClear'
    spots = (source / 'Raids/AhnQiraj/Aq40Spots.cpp').read_text()
    hounds = (source / 'Raids/MoltenCore/McRaidClear.cpp').read_text()
    constants = (source / 'Raids/MoltenCore/McRaidClear.h').read_text()
    declarations = [re.search(r'constexpr float CORE_HOUND_LINK_RANGE\s*=\s*[^;]+;', constants)[0]]
    declarations += ['constexpr uint32 ' + re.search(r'\b' + name + r'\s*=\s*\d+', constants)[0] + ';'
                     for name in ('NPC_CORE_HOUND', 'SPELL_PLAY_DEAD')]
    # The double keeps the native output-list contract and returns a standing
    # hound that the core's entry-and-range search can produce.
    objects = (core / 'src/server/game/Entities/Object/Object.h').read_text()
    signature = re.search(r'void GetCreaturesWithEntryInRange\(std::list<Creature\*>& creatureList, '
                          r'float radius, uint32 entry\);', objects)[0][:-1]
    producer = function((core / 'src/server/game/Entities/Object/Object.cpp').read_text(),
                        'void WorldObject::GetCreaturesWithEntryInRange(')
    assert 'Acore::AllCreaturesOfEntryInRange check(this, entry, radius);' in producer
    production = '\n'.join((function(spots, 'struct SpotWant') + ';',
                             function(spots, 'float SpotNear('),
                             function(hounds, 'struct Hounds') + ';',
                             function(hounds, 'Unit* NextHound(')))
    compiler = cxx()
    with tempfile.TemporaryDirectory(prefix='raid-clear-windows-') as directory:
        work = Path(directory)
        (work / 'Position.h').write_text('#pragma once\nstruct Position {};\n')
        shutil.copyfile(source / 'Common/FixedSpots.h', work / 'FixedSpots.h')
        (work / 'production.inc').write_text(production)
        (work / 'fixture.cpp').write_text(HARNESS.replace('NATIVE_CONSTANTS', '\n'.join(declarations))
                                         .replace('NATIVE_SEARCH_SIGNATURE', signature))

        def build(tree, windows):
            executable = tree / ('windows.exe' if windows else 'plain.exe')
            command = [compiler, '-std=c++20', '-Wall', '-Wextra', '-Werror',
                       '-I', str(tree), str(tree / 'fixture.cpp'), '-o', str(executable)]
            if windows:
                command.append('-DRAID_WINDOWS_MACROS')
            result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=TIMEOUT)
            return result, executable

        for windows in (False, True):
            result, executable = build(work, windows)
            assert result.returncode == 0, result.stdout + result.stderr
            result = run_fixture([str(executable)])
            assert result.returncode == 0, result.stdout + result.stderr

        mutations = (
            ('fixed spot NEAR reversion', {
                'FixedSpots.h': ('SPOT_NEAR', 'NEAR'),
                'production.inc': ('Spots::SPOT_NEAR', 'Spots::NEAR'),
            }),
            ('Core Hound near reversion', {'production.inc': ('nearbyHounds', 'near')}),
        )
        for index, (label, replacements) in enumerate(mutations):
            mutant = work / str(index)
            mutant.mkdir()
            for filename in ('Position.h', 'FixedSpots.h', 'production.inc', 'fixture.cpp'):
                text = (work / filename).read_text()
                if filename in replacements:
                    old, new = replacements[filename]
                    assert old in text, f'{label} mutation was not applied'
                    text = text.replace(old, new)
                (mutant / filename).write_text(text)
            plain, _ = build(mutant, False)
            assert plain.returncode == 0, plain.stdout + plain.stderr
            windows, _ = build(mutant, True)
            assert windows.returncode != 0, f'Windows build did not reject {label}'
            print(f'Raid Clear Windows build mutation rejected: {label}')
    print('Raid Clear Windows build: production header, spot thresholds and Core Hound selection passed '
          'with and without Windows macros')


if __name__ == '__main__':
    main()
