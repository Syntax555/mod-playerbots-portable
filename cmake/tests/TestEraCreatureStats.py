"""Replay historical creature repairs and calculate HP/damage with the native core."""

import argparse
from collections import Counter
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile

from FixtureSupport import (
    cxx,
    function,
    prepared_core,
    run_fixture,
    source_argument,
    sql_rows,
)


repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo / 'scripts'))
from generate_era_quest_xp import table_rows


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, 'core', default=prepared_core())
source_argument(parser, 'module')
source_argument(parser, 'classic-db')
source_argument(parser, 'tbc-db')
args = parser.parse_args()
core = args.core
module = args.module or core / 'modules/mod-individual-progression'
migration = module / 'data/sql/world/updates/zz_2026_11_03_01_creature_era_stats.sql'
repair = migration.read_text()
assert all(migration.name > name for name in ('vanilla_creatures.sql', 'tbc_creatures.sql'))
fields = ('exp', 'minlevel', 'maxlevel', 'HealthModifier', 'unit_class')
targets = set(map(int, re.findall(r'WHERE `entry` = (\d+)', repair)))
assert {2784, 3057, 4949, 7937, 7999, 10181, 16802, 17468} <= targets
wrath_encounters = {10184, 15929, 15930, 15956, 16505, 16506, 16698, 23561, 23562, 23563}
assert not wrath_encounters & targets, 'historical replacements must keep their Wrath originals'
entries = targets | wrath_encounters | {6, 31146}
rows = sql_rows(core, 'creature_template', entries)
assert {int(row['entry']) for row in rows} == entries
updates = re.compile(r'UPDATE\s+`creature_template`\s+SET\s+(.*?)\s+WHERE\s+(.*?);', re.DOTALL)
era_sql = []
for name in ('tbc_creatures.sql', 'vanilla_creatures.sql'):
    text = re.sub(r'/\*.*?\*/|--[^\n]*', '', (module / 'data/sql/world/base' / name).read_text(), flags=re.DOTALL)
    for setters, where in updates.findall(text):
        values = re.findall(r'`(' + '|'.join(fields) + r')`\s*=\s*([-+\d.eE]+)', setters)
        if values:
            era_sql.append('UPDATE creature_template SET ' + ', '.join(
                f'`{field}`={value}' for field, value in values) + ' WHERE ' + where + ';')


def database():
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE creature_template (entry INTEGER PRIMARY KEY, exp INTEGER, minlevel INTEGER, '
               'maxlevel INTEGER, HealthModifier REAL, unit_class INTEGER)')
    db.executemany('INSERT INTO creature_template VALUES (?, ?, ?, ?, ?, ?)',
                   [(int(row['entry']), *(float(row[field]) for field in fields)) for row in rows])
    db.executescript('\n'.join(era_sql))
    return db


def snapshot(db):
    return {row[0]: row[1:] for row in db.execute('SELECT * FROM creature_template ORDER BY entry')}


def check(sql):
    with database() as db:
        before = snapshot(db)
        db.executescript(sql)
        after = snapshot(db)
        changed = Counter(field for entry in entries for index, field in enumerate(fields)
                          if before[entry][index] != after[entry][index])
        assert changed == {'exp': 217, 'minlevel': 10, 'maxlevel': 10, 'HealthModifier': 3}, \
            ('incomplete historical stat repair', changed)
        # Skull bosses retain their historical levels, rather than a generic level cap.
        assert after[7937] == (0, 63, 63, 200, 1), 'Mekkatorque retains later-era base stats'
        assert after[2784][:3] == (0, 63, 63)
        assert after[17468][:3] == (1, 73, 73), 'Velen retains Wrath level or base stats'
        assert after[16802][:4] == (1, 73, 73, 250), "Lor'themar retains Wrath health or level"
        assert after[25246] == (1, 70, 70, 200, 2), 'TBC Lady Liadrin retains Wrath base stats'
        assert all(after[entry] == before[entry] for entry in entries - targets), 'unrelated creature changed'
        assert set(after) == set(before)
        db.executescript(sql)
        assert snapshot(db) == after, 'repair is not idempotent'
        # Any later per-field customization survives, including when other fields need repair.
        for index, field in enumerate(fields):
            changed = [entry for entry in targets if before[entry][index] != after[entry][index]]
            choices = (0, 1, 2) if field == 'exp' else (1, 2, 4, 8) if field == 'unit_class' else (79, 78, 77)
            custom = {entry: next(value for value in choices if value not in (before[entry][index], after[entry][index]))
                      for entry in changed}
            with database() as customized:
                customized.executemany(f'UPDATE creature_template SET `{field}`=? WHERE entry=?',
                                       [(value, entry) for entry, value in custom.items()])
                customized.executescript(sql)
                assert all(customized.execute(f'SELECT `{field}` FROM creature_template WHERE entry=?',
                                              (entry,)).fetchone() == (value,) for entry, value in custom.items()), field
        with database() as missing:
            missing.execute('DELETE FROM creature_template WHERE entry=7937')
            missing.executescript(sql)
            assert not missing.execute('SELECT 1 FROM creature_template WHERE entry=7937').fetchall()
        return after


after = check(repair)
for label, mutant in (
    ('missing repair', ''),
    ('one creature omitted', re.sub(r'UPDATE `creature_template` SET `exp`[^;]+;', '', repair, count=1)),
    ('missing current-value guards', re.sub(r' AND (?:ROUND\(`\w+`, 6\)|`\w+`) = [-+\d.eE]+', '', repair)),
):
    assert mutant != repair, label
    try:
        check(mutant)
    except AssertionError:
        print(f'Era creature stats mutation rejected: {label}')
    else:
        raise AssertionError(f'Era creature stats fixture accepted {label}')

# Compile the real production base-stat loader loop and health/damage functions.
header = (core / 'src/server/game/Entities/Creature/CreatureData.h').read_text()
loader = (core / 'src/server/game/Globals/ObjectMgr.cpp').read_text()
creature = (core / 'src/server/game/Entities/Creature/Creature.cpp').read_text()
select = function(creature, 'void Creature::SelectLevel(')
assert 'sObjectMgr->GetCreatureBaseStats(level, cInfo->unit_class)' in select
assert 'stats->GenerateHealth(cInfo)' in select and 'stats->GenerateBaseDamage(cInfo)' in select
assert 'uint32 BaseHealth[MAX_EXPANSIONS];' in header and 'float BaseDamage[MAX_EXPANSIONS];' in header
assert 'uint32  expansion;' in header and 'float   ModHealth;' in header
base = {(int(row['level']), int(row['class'])): row for row in table_rows(
    (core / 'data/sql/base/db_world/creature_classlevelstats.sql').read_text(), 'creature_classlevelstats')}
cases = []
for entry, health in ((7937, 666200), (2784, 999300), (25246, 1117800)):
    exp, level, maximum, modifier, unit_class = after[entry]
    assert level == maximum
    row = base[int(level), int(unit_class)]
    values = [row[key] for key in ('basehp0', 'basehp1', 'basehp2', 'basemana', 'basearmor',
                                  'attackpower', 'rangedattackpower', 'damage_base', 'damage_exp1', 'damage_exp2')]
    cases.append('check({' + ','.join(values) + '}, ' + f'{int(exp)}, {modifier}f, {health});')
native = '#include <cassert>\n#include <cmath>\n#include <cstdint>\n#include <array>\n' + r'''
using uint8 = std::uint8_t; using uint32 = std::uint32_t;
constexpr uint8 MAX_EXPANSIONS = 3;
#define LOG_ERROR(...) ((void)0)
struct CreatureTemplate { uint32 expansion; float ModHealth; };
struct CreatureBaseStats {
    uint32 BaseHealth[MAX_EXPANSIONS]; float BaseDamage[MAX_EXPANSIONS];
''' + function(header, '    uint32 GenerateHealth(') + '\n' + function(header, '    float GenerateBaseDamage(') + r'''
};
struct Field { float value; template<typename T> T Get() const { return T(value); } };
void check(std::array<float, 10> values, uint8 expansion, float modifier, uint32 expected) {
    std::array<Field, 12> fields{};
    for (unsigned i = 0; i < values.size(); ++i) fields[i + 2].value = values[i];
    CreatureBaseStats stats{};
''' + function(loader, '        for (uint8 i = 0; i < MAX_EXPANSIONS; ++i)') + r'''
    CreatureTemplate info{expansion, modifier};
    assert(stats.GenerateHealth(&info) == expected);
    assert(stats.GenerateBaseDamage(&info) == values[7 + expansion]);
    info.expansion = 2;
    assert(stats.GenerateHealth(&info) > expected);
    assert(stats.GenerateBaseDamage(&info) > values[7 + expansion]);
}
int main() {
''' + '\n'.join(cases) + '\n}\n'
with tempfile.TemporaryDirectory(prefix='era-creature-stats-') as work:
    source, executable = Path(work) / 'fixture.cpp', Path(work) / 'fixture'
    source.write_text(native)
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(executable)], check=True)
    result = run_fixture([str(executable)])
    assert result.returncode == 0, result.stdout + result.stderr

if args.classic_db or args.tbc_db:
    assert args.classic_db and args.tbc_db, 'pass both historical databases to regenerate'
    from generate_era_creature_stats import generate
    assert generate(args.classic_db, args.tbc_db, core, module) == repair, 'generated creature stats are stale'
print(f'Era creature stats: {len(targets)} entries, historical levels, native HP/damage, '
      'custom values, missing rows, unrelated creatures and idempotence passed')
