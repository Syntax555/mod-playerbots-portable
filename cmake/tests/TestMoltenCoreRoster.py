"""Keep Molten Core's clear order separate from its native encounter kill bits."""

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
    source_argument,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, 'core', default=prepared_core())
source_argument(parser, default=prepared_core() / 'modules/mod-dungeon-clear')
args = parser.parse_args()
source = args.source / 'src'
constants = (args.core / 'src/server/shared/DataStores/DBCEnums.h').read_text()
for name, value in (('RAID_DIFFICULTY_10MAN_HEROIC', 2), ('DUNGEON_DIFFICULTY_HEROIC', 1)):
    assert re.search(r'\b' + name + r'\s*=\s*' + str(value) + r'\b', constants)
assert re.search(r'#define RAID_DIFFICULTY_MASK_25MAN 1\b', constants)
event = (source / 'Ai/Dungeon/DungeonClear/Data/Events/MoltenCoreEvents.cpp').read_text()
registry = (source / 'Ai/Dungeon/DungeonClear/Overrides/BossRosterRegistry.cpp').read_text()
registrar = function(event, 'void RegisterMoltenCoreRoster(')
apply = function(registry, '    std::vector<DungeonBossInfo> ApplyOne(')
harness = r'''
#include <algorithm>
#include <cassert>
#include <unordered_set>
#include "Ai/Dungeon/DungeonClear/Data/Events/DungeonRosterBuilders.h"
@CONSTANTS@
@REGISTRAR@
@APPLY@
int main() {
    std::vector<BossRosterPatch> patches;
    RegisterMoltenCoreRoster(patches);
    assert(patches.size()==1 && patches[0].mapId==409);
    std::vector<DungeonBossInfo> base;
    uint32 const entries[]={12118,11982,12259,12057,12264,12056,12098,11988};
    for(uint32 i=0;i<8;++i) {DungeonBossInfo b;b.entry=entries[i];b.encounterIndex=i;b.mapId=409;base.push_back(b);}
    auto out=ApplyOne(patches[0],base);
    uint32 const order[]={12118,11982,12259,12057,12056,12264,12098,11988};
    assert(out.size()==11);
    for(uint32 i=0;i<8;++i) {assert(out[i].entry==order[i]);assert(BossOrderKey(out[i])==i);}
    assert(out[4].encounterIndex==5 && out[5].encounterIndex==4);
    assert(out[8].entry==12018 && out[8].doneBossStateIndex==8 && out[8].encounterIndex>=32);
    assert(out[9].kind==DungeonAnchorKind::Objective && out[9].eventId==1 && out[9].gateEntry==11502);
    assert(out[10].entry==11502 && out[10].doneBossStateIndex==9 && out[10].encounterIndex>=32);
}
'''.replace('@CONSTANTS@', function(event, 'namespace')).replace('@APPLY@', apply)

with tempfile.TemporaryDirectory(prefix='portable-molten-core-roster-') as temporary:
    directory = Path(temporary)
    (directory / 'Common.h').write_text('#pragma once\n#include <cstdint>\nusing uint8=uint8_t;using uint32=uint32_t;using int32=int32_t;\n')
    (directory / 'Define.h').write_text('#pragma once\n#include "Common.h"\n')
    (directory / 'DBCEnums.h').write_text(
        '#pragma once\nconstexpr int RAID_DIFFICULTY_10MAN_HEROIC=2,DUNGEON_DIFFICULTY_HEROIC=1,RAID_DIFFICULTY_MASK_25MAN=1;\n')
    for label, variant in (('production', registrar), ('missing reorder', registrar.replace('p.reorder = {', 'std::vector<std::pair<uint32,int32>> unused = {'))):
        assert label == 'production' or variant != registrar
        cpp = directory / 'roster.cpp'
        cpp.write_text(harness.replace('@REGISTRAR@', variant))
        executable = directory / 'roster'
        subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-unused-const-variable',
                        *SANITIZER_FLAGS, '-I', str(directory), '-I', str(source), str(cpp), '-o', str(executable)], check=True)
        result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=60, check=False)
        assert (result.returncode == 0) == (label == 'production'), (label, result.stderr)
        print('Molten Core roster: ' + label + (' passed' if label == 'production' else ' mutation rejected'))
