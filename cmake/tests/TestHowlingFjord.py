"""Replay Howling Fjord SQL and exercise its combat timers with native SmartAI.

SQLite checks the production updates against the pinned world's column names,
defaults and keys after the creature-id migration. Native SmartAI event branches
and WorldObject::IsInRange distinguish combat timers from real distance gates.
"""

import argparse
from pathlib import Path
import re
import sqlite3
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
    sql_values,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help='Individual Progression module directory')
args = parser.parse_args()
core = prepared_core()
module = args.source or core / 'modules/mod-individual-progression'
sql = (module / 'data/sql/world/base/zone_howling_fjord.sql').read_text()
variables = dict(re.findall(r'SET\s+(@\w+)\s*:=\s*(\d+)\s*;', sql))
sql = re.sub(r'SET\s+@\w+\s*:=\s*\d+\s*;', '', sql)
sql = re.sub(r'@\w+', lambda match: variables[match[0]], sql).replace("\\'", "''")

tables = {
    'smart_scripts': ('entryorguid', {24014, 24790, 24796, 24910, 24173, 186944, 2417300}),
    'creature': ('guid', {131263, 131264, 131281, 624956}),
    'gameobject': ('guid', {59521, 100055, 680001}),
    'creature_template': ('entry', {24014, 24790, 24796, 24910, 24914, 24956, 24173}),
    'gameobject_template': ('entry', {186944, 187117}),
    'creature_text': ('CreatureID', {24790, 24910, 24173}),
    'creature_loot_template': ('Entry', {24228}),
}
schema_update = (core / 'data/sql/updates/db_world/2026_06_16_00.sql').read_text()
assert 'CHANGE COLUMN `id1` `id`' in schema_update and 'DROP COLUMN `id2`, DROP COLUMN `id3`' in schema_update

with sqlite3.connect(':memory:') as db:
    untouched = {}
    for table, (selector, selected) in tables.items():
        source = (core / f'data/sql/base/db_world/{table}.sql').read_text()
        definition = source.split(f'CREATE TABLE `{table}` (')[1].split(') ENGINE')[0]
        columns = re.findall(r'^  `([^`]+)`', definition, re.MULTILINE)
        effective = [column.replace('id1', 'id') if table == 'creature' else column
                     for column in columns if table != 'creature' or column not in ('id2', 'id3')]
        declarations = []
        for line in definition.splitlines():
            match = re.match(r'  `([^`]+)`', line)
            if not match or (table == 'creature' and match[1] in ('id2', 'id3')):
                continue
            name = match[1].replace('id1', 'id') if table == 'creature' else match[1]
            default = re.search(r"\bDEFAULT\s+('[^']*'|NULL|-?[\d.]+)", line)
            declarations.append(f'`{name}` NUMERIC' + (' DEFAULT ' + default[1] if default else ''))
        primary = re.search(r'PRIMARY KEY \(([^)]+)\)', definition)[1]
        db.execute(f'CREATE TABLE `{table}` (' + ','.join(declarations) + f',PRIMARY KEY ({primary}))')
        preserved = None
        for line in source.splitlines():
            if not line.startswith('('):
                continue
            values = sql_values(line.rstrip('\n,;')[1:-1])
            row = dict(zip(columns, values, strict=True))
            wanted = int(row[selector]) in selected or (table == 'creature' and row['id1'] == '24790')
            if not wanted and preserved is not None:
                continue
            values = [row[column if column != 'id' or table != 'creature' else 'id1'] for column in effective]
            values = [None if value == 'NULL' else value for value in values]
            db.execute(f'INSERT INTO `{table}` VALUES (' + ','.join('?' for _ in values) + ')', values)
            if not wanted:
                preserved = db.execute(f'SELECT * FROM `{table}` WHERE `{selector}` = ?', (row[selector],)).fetchone()
                untouched[table] = (selector, row[selector], preserved)
    db.executescript(sql)
    first = {table: db.execute(f'SELECT * FROM `{table}` ORDER BY 1,2,3').fetchall() for table in tables}
    db.executescript(sql)
    assert first == {table: db.execute(f'SELECT * FROM `{table}` ORDER BY 1,2,3').fetchall() for table in tables}
    for table, (selector, value, row) in untouched.items():
        assert db.execute(f'SELECT * FROM `{table}` WHERE `{selector}` = ?', (value,)).fetchone() == row
    assert db.execute('SELECT id FROM gameobject WHERE guid=680001').fetchone() == (186944,)
    assert db.execute('SELECT id FROM creature WHERE guid=624956').fetchone() == (24956,)
    assert not db.execute('SELECT 1 FROM creature WHERE id=24790').fetchall()
    assert db.execute('SELECT position_z FROM gameobject WHERE guid=59521').fetchone() == (297.034,)
    assert db.execute('SELECT AIName FROM gameobject_template WHERE entry=186944').fetchone() == ('SmartGameObjectAI',)
    assert db.execute('SELECT AIName FROM creature_template WHERE entry=24956').fetchone() == ('SmartAI',)
    assert db.execute('SELECT COUNT(*) FROM smart_scripts WHERE entryorguid IN (24014,24790,24796,186944,2479001,2479601,18694401,24910,-624956,2491001,2495601,24173,2417300)').fetchone() == (42,)
    assert not db.execute('SELECT 1 FROM smart_scripts s LEFT JOIN smart_scripts l ON '
                         'l.entryorguid=s.entryorguid AND l.source_type=s.source_type AND l.id=s.link AND l.event_type=61 '
                         'WHERE s.link<>0 AND l.id IS NULL').fetchall()
    drain = db.execute('SELECT event_type,event_param1,event_param2,event_param3,event_param4,event_param5,event_param6 '
                       'FROM smart_scripts WHERE entryorguid=24014 AND id=10').fetchone()
    conrad = db.execute('SELECT event_type,event_param1,event_param2,event_param3,event_param4,event_param5,event_param6 '
                        'FROM smart_scripts WHERE entryorguid=24790 AND id=3').fetchone()
    assert drain[1:] == (4000, 4000, 8000, 12000, 0, 0)
    assert conrad == (9, 0, 0, 10000, 15000, 0, 5)

header = (core / 'src/server/game/AI/SmartScripts/SmartScriptMgr.h').read_text()
assert re.search(r'SMART_EVENT_UPDATE_IC\s*=\s*0\b', header)
assert re.search(r'SMART_EVENT_RANGE\s*=\s*9\b', header)
timers = re.search(r'struct\s*\{\s*uint32 min;\s*uint32 max;\s*uint32 repeatMin;\s*uint32 repeatMax;'
                   r'\s*uint32 rangeMin;\s*uint32 rangeMax;\s*\} minMaxRepeat;', header)[0]
process = function((core / 'src/server/game/AI/SmartScripts/SmartScript.cpp').read_text(),
                   'void SmartScript::ProcessEvent(')
update = re.search(r'case SMART_EVENT_UPDATE_IC:.*?(?=\s*case SMART_EVENT_HEALTH_PCT:)', process, re.DOTALL)[0]
distance = function(process, 'case SMART_EVENT_RANGE:')
in_range = function((core / 'src/server/game/Entities/Object/Object.cpp').read_text(), 'bool WorldObject::IsInRange(')

fixture = r'''
#include <cassert>
#include <cstdint>
using uint32 = std::uint32_t;
enum { SMART_EVENT_UPDATE_IC = 0, SMART_EVENT_RANGE = 9 };
struct WorldObject
{
    float x = 0;
    float GetPositionX() const { return x; }
    float GetPositionY() const { return 0; }
    float GetPositionZ() const { return 0; }
    float GetObjectSize() const { return 0.5f; }
    bool IsInRange(WorldObject const*, float, float, bool = true) const;
};
@IN_RANGE@
struct Unit : WorldObject
{
    bool engaged = true;
    Unit* victim = nullptr;
    bool IsEngaged() const { return engaged; }
    Unit* GetVictim() const { return victim; }
};
struct SmartScriptHolder
{
    uint32 type;
    struct { @TIMERS@ } event;
};
struct SmartScript
{
    Unit* me;
    int calls = 0;
    uint32 minimum = 0, maximum = 0;
    void ProcessTimedAction(SmartScriptHolder&, uint32 min, uint32 max, Unit* = nullptr)
    { ++calls; minimum = min; maximum = max; }
    void RecalcTimer(SmartScriptHolder&, uint32, uint32) {}
    void ProcessEvent(SmartScriptHolder& e)
    {
        switch (e.type)
        {
            @UPDATE@
            @DISTANCE@
        }
    }
};
int main()
{
    Unit creature, victim;
    creature.victim = &victim;
    victim.x = 20;
    SmartScript script{&creature};
    SmartScriptHolder drain{@DRAIN@, {{@DRAIN_TIMERS@}}};
    script.ProcessEvent(drain);
    assert(script.calls == 1 && script.minimum == 8000 && script.maximum == 12000);
    creature.engaged = false;
    script.ProcessEvent(drain);
    assert(script.calls == 1);
    creature.engaged = true;
    SmartScriptHolder conrad{@CONRAD@, {{@CONRAD_TIMERS@}}};
    script.ProcessEvent(conrad);
    assert(script.calls == 1);
    victim.x = 3;
    script.ProcessEvent(conrad);
    assert(script.calls == 2 && script.minimum == 10000 && script.maximum == 15000);
}
'''.replace('@IN_RANGE@', in_range).replace('@TIMERS@', timers).replace('@UPDATE@', update).replace('@DISTANCE@', distance)
fixture = fixture.replace('@DRAIN@', str(drain[0])).replace('@DRAIN_TIMERS@', ','.join(map(str, drain[1:])))
fixture = fixture.replace('@CONRAD@', str(conrad[0])).replace('@CONRAD_TIMERS@', ','.join(map(str, conrad[1:])))


def build(directory, executable):
    return [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', *SANITIZER_FLAGS,
            str(directory / 'fixture.cpp'), '-o', str(executable)]


with tempfile.TemporaryDirectory(prefix='howling-fjord-') as temporary:
    work = Path(temporary)
    (work / 'fixture.cpp').write_text(fixture)
    executable = work / 'fixture'
    subprocess.run(build(work, executable), check=True)
    result = run_fixture([str(executable)])
    assert result.returncode == 0, result.stdout + result.stderr
    reject_mutants(work, (
        ('zero-range Necrolord timer restored', 'fixture.cpp', 'SmartScriptHolder drain{0,', 'SmartScriptHolder drain{9,'),
        ('Black Conrad distance gate removed', 'fixture.cpp',
         'if (me->IsInRange(me->GetVictim(), (float)e.event.minMaxRepeat.rangeMin, (float)e.event.minMaxRepeat.rangeMax))',
         'if (true)'),
    ), build, 'Howling Fjord')
print('Howling Fjord: native SQL schema, idempotent replay, combat timer and 0-5 range verified')
