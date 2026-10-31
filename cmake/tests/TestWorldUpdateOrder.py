"""Replay world SQL in the native updater order for fresh and existing realms."""

import argparse
from collections import Counter
import hashlib
import math
import re
import sqlite3
import struct

from FixtureSupport import (
    pinned_source,
    prepared_core,
    source_argument,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, 'core', default=prepared_core())
args = parser.parse_args()
core = args.core
modules = core / 'modules'
ip = modules / 'mod-individual-progression'
world = core / 'data/sql/base/db_world'
updates = core / 'data/sql/updates/db_world'

# Core and module updates form one set ordered by file name. An existing realm
# applies new core updates after module files it applied earlier, reapplies a
# changed file and keeps the applied state of a renamed, unchanged file.
fetcher = (core / 'src/server/database/Updater/UpdateFetcher.cpp').read_text()
assert 'left.first.filename().string() < right.first.filename().string()' in fetcher
assert 'if (dirName.find(_dbModuleName) == std::string::npos)' in fetcher
assert 'RenameEntry(hashIter->second, filePath.filename().string());' in fetcher
assert 'if (iter->second.hash != hash)' in fetcher
module_files = sorted((path for path in modules.glob('*/data/sql/*/**/*.sql')
                       if 'world' in path.relative_to(modules).parts[3]), key=lambda path: path.name)
# The updater stops the server when two update files share a name.
assert 'Duplicate filename' in fetcher
included = re.findall(r"\('\$/(data/sql/[\w/]+)','\w+'\)", (world / 'updates_include.sql').read_text())
assert 'data/sql/updates/db_world' in included, included
names = Counter(path.name for path in module_files)
names.update(path.name for directory in included for path in (core / directory).rglob('*.sql'))
duplicates = [name for name, count in names.items() if count > 1]
assert not duplicates, duplicates

# A fresh world database still has creature.id1 until the core renames it.
assert '`id1` int unsigned' in (world / 'creature.sql').read_text()
renames = [path.name for path in sorted(updates.glob('*.sql'))
           if 'ALTER TABLE `creature` CHANGE COLUMN `id1` `id`' in path.read_text()]
assert len(renames) == 1, renames
rename = renames[0]
recorded = set(re.findall(r"\('([^']+[.]sql)','[0-9A-F]{40}'", (world / 'updates.sql').read_text()))
assert rename not in recorded, 'the base dump already contains the creature.id rename'
CREATURE_ID = re.compile(r'(?is)\b(?:DELETE\s+FROM|UPDATE|(?:INSERT|REPLACE)(?:\s+IGNORE)?\s+INTO)\s+'
                         r'`creature`[\s(][^;]*?`id`')


def early_creature_ids(names):
    """Module files that would reach a fresh database before the creature.id rename."""
    return [name for name, path in names if name < rename and CREATURE_ID.search(path.read_text())]


cleanup = ip / 'data/sql/world/base/2026_06_16_00_ip_cleanup.sql'
upstream_cleanup = 'data/sql/world/base/00_cleanup.sql'
assert not (ip / upstream_cleanup).exists()
# Unchanged contents let an existing realm record the rename without reapplying it.
assert cleanup.read_text() == pinned_source('mod-individual-progression', upstream_cleanup)
assert CREATURE_ID.search(cleanup.read_text()), 'the cleanup no longer needs creature.id'
ip_files = [path.name for path in module_files if path.is_relative_to(ip)]
assert all(cleanup.name <= name for name in ip_files), 'the cleanup must still precede the module data'
named = [(path.name, path) for path in module_files]
assert not early_creature_ids(named), early_creature_ids(named)
upstream_order = [('00_cleanup.sql' if path == cleanup else name, path) for name, path in named]
assert early_creature_ids(upstream_order) == ['00_cleanup.sql']
print('Update order mutation rejected: cleanup before the creature.id rename')
print(f'Fresh world update order: module creature statements follow {rename}; renamed cleanup unchanged')

# Netherstorm: core updates newer than the module's zone data overwrite it only
# on realms that applied the module data before them.
zone = ip / 'data/sql/world/base/zone_netherstorm.sql'
repair = ip / 'data/sql/world/updates/zz_2026_10_24_01_netherstorm_core_updates.sql'
core_updates = [updates / name for name in ('2026_10_15_04.sql', '2026_10_15_06.sql', '2026_10_16_09.sql')]
assert zone.name < repair.name and all(path.name < zone.name for path in core_updates)
KEYS = {
    'smart_scripts': ('entryorguid', {20281, 2028100, 2028101, 2028102, 2028103, 2028104}),
    'creature_addon': ('guid', {70141}),
    'creature_formations': ('leaderGUID', {70141}),
}
TABLE = re.compile(r'(?is)^\s*(?:DELETE\s+FROM|UPDATE|INSERT(?:\s+IGNORE)?\s+INTO)\s+`(\w+)`')


def statements(text):
    """Split MySQL statements outside quotes and comments."""
    result, current, quote, index = [], [], None, 0
    while index < len(text):
        char = text[index]
        if quote:
            current.append(char)
            if char == '\\':
                current.append(text[index + 1])
                index += 1
            elif char == quote:
                quote = None
        elif text.startswith('--', index) or text.startswith('/*', index):
            end = text.find('\n' if text[index] == '-' else '*/', index)
            index = len(text) if end < 0 else end + (0 if text[index] == '-' else 2)
            continue
        elif char in '\'"':
            quote = char
            current.append(char)
        elif char == ';':
            result.append(''.join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    return [statement for statement in result if statement]


def relevant(path):
    """Statements for the compared rows, with the file's @variables substituted."""
    chosen, variables = [], {}
    for statement in statements(path.read_text()):
        assignment = re.fullmatch(r'(?is)SET\s+(@\w+)\s*:=\s*([\d\s*+]+)', statement)
        if assignment:
            variables[assignment[1]] = str(sum(math.prod(int(factor) for factor in term.split('*'))
                                               for term in assignment[2].split('+')))
            continue
        for name in sorted(variables, key=len, reverse=True):
            statement = statement.replace(name, variables[name])
        table = TABLE.match(statement)
        if not table or (table[1] == 'creature' and not re.search(r'\b(18855|19657|70141)\b', statement)):
            continue
        if table[1] in KEYS and not any(re.search(rf'\b{key}\b', statement) for key in KEYS[table[1]][1]):
            continue
        if table[1] in KEYS or table[1] == 'creature':
            chosen.append(statement.replace("\\'", "''"))
    assert chosen, path
    return chosen


def columns(table):
    create = (world / f'{table}.sql').read_text().split(f'CREATE TABLE `{table}` (')[1].split(') ENGINE')[0]
    return [line.split('`')[1] for line in create.splitlines() if line.strip().startswith('`')]


# Exact row membership relies on native uniqueness, non-null fields and FLOAT storage.
smart_schema = (world / 'smart_scripts.sql').read_text().split('CREATE TABLE `smart_scripts` (')[1].split(') ENGINE')[0]
assert len(columns('smart_scripts')) == 31
assert all(re.search(rf'^  `{column}` [^\n]*\bNOT NULL\b', smart_schema, re.MULTILINE)
           for column in columns('smart_scripts'))
assert 'PRIMARY KEY (`entryorguid`,`source_type`,`id`,`link`)' in smart_schema
for column in ('target_x', 'target_y', 'target_z', 'target_o'):
    assert re.search(rf'^  `{column}` float NOT NULL\b', smart_schema, re.MULTILINE)


creature_columns = []
for path in [zone, *core_updates]:
    for statement in relevant(path):
        header = re.match(r'(?is)INSERT INTO `creature` \(([^)]*)\)', statement)
        if header:
            creature_columns += [column.strip(' `\n') for column in header[1].split(',')
                                 if column.strip(' `\n') not in creature_columns]
assert {'guid', 'id', 'map', 'MovementType'} <= set(creature_columns)


def database():
    db = sqlite3.connect(':memory:')
    db.create_function('FLOAT32', 1, lambda value: struct.unpack('<f', struct.pack('<f', value))[0])
    for table in KEYS:
        db.execute(f'CREATE TABLE `{table}` (' + ','.join(f'`{column}`' for column in columns(table)) + ')')
    db.execute('CREATE TABLE `creature` (' + ','.join(f'`{column}`' for column in creature_columns) + ')')
    return db


def run(db, paths, sources=None):
    for path in paths:
        for statement in (sources or {}).get(path) or relevant(path):
            db.execute(statement)
    # The native coordinate columns store single precision, unlike SQLite's REAL.
    db.execute('UPDATE smart_scripts SET ' + ', '.join(
        f'`{column}` = FLOAT32(`{column}`)' for column in ('target_x', 'target_y', 'target_z', 'target_o')))


def replay_repair(db, sql):
    # MySQL's CAST AS FLOAT uses the same single precision as the stored coordinates.
    db.executescript(re.sub(r'CAST\(([^()]+) AS FLOAT\)', r'FLOAT32(\1)', sql))


def snapshot(db):
    state = {table: sorted(db.execute(f'SELECT * FROM `{table}` WHERE `{key}` IN ({",".join(map(str, keys))})'))
             for table, (key, keys) in KEYS.items()}
    state['creature'] = sorted(db.execute('SELECT * FROM `creature` WHERE `id` IN (18855, 19657)'))
    return state


repair_sql = repair.read_text()


def realms(sql):
    fresh, existing = database(), database()
    run(fresh, [*core_updates, zone])
    run(existing, [zone, *core_updates])
    for db in (fresh, existing):
        replay_repair(db, sql)
    return fresh, existing


fresh, existing = realms(repair_sql)
assert snapshot(fresh) == snapshot(existing), 'existing realms keep core rows a fresh realm replaces'
expected = snapshot(fresh)
for db in (fresh, existing):
    replay_repair(db, repair_sql)
    assert snapshot(db) == expected, 'the Netherstorm repair is not idempotent'
drijya = sorted(row[2] for row in fresh.execute('SELECT * FROM smart_scripts WHERE entryorguid = 20281 AND source_type = 0'))
assert drijya == list(range(15)), drijya
assert not fresh.execute('SELECT 1 FROM smart_scripts WHERE entryorguid = 20281 AND action_type = 53').fetchall()
assert fresh.execute('SELECT COUNT(*) FROM creature WHERE id = 18855 AND guid BETWEEN 52066 AND 52070').fetchone() == (0,)
fresh_before, existing_before = realms('')
assert snapshot(fresh_before) == expected, 'the repair changed a fresh realm'
assert snapshot(existing_before) != expected, 'omitting the repair did not reproduce the existing-realm rows'
# Without the repair an existing realm mixes the core waypoint start with the module's action lists.
assert existing_before.execute('SELECT 1 FROM smart_scripts WHERE entryorguid = 20281 AND action_type = 53').fetchall()
assert existing_before.execute('SELECT 1 FROM smart_scripts WHERE entryorguid = 2028100 AND action_type = 232').fetchall()
print('Netherstorm update order: fresh and existing realms match after an idempotent repair')

def customized(sql, rows, customize):
    db = database()
    run(db, [zone, *core_updates])
    db.execute(customize)
    before = sorted(db.execute('SELECT * FROM ' + rows))
    replay_repair(db, sql)
    return before, sorted(db.execute('SELECT * FROM ' + rows))


def check_drijya_customizations(sql):
    rows = 'smart_scripts WHERE entryorguid = 20281 AND source_type = 0'
    for column in columns('smart_scripts'):
        change = f'`{column}` + 1' if column != 'comment' else 'LOWER(`comment`)'
        before, after = customized(sql, rows,
            f'UPDATE smart_scripts SET `{column}` = {change} '
            'WHERE entryorguid = 20281 AND source_type = 0 AND id = 6')
        assert before == after, ('the repair changed a customized Drijya column', column)
    # Preserve even the smallest stored coordinate change and case-only comments.
    for column in ('target_x', 'target_y', 'target_z', 'target_o'):
        value, = existing_before.execute(
            f'SELECT `{column}` FROM smart_scripts WHERE entryorguid = 20281 AND source_type = 0 AND id = 15').fetchone()
        bits, = struct.unpack('<I', struct.pack('<f', value))
        changed, = struct.unpack('<f', struct.pack('<I', bits + 1))
        before, after = customized(sql, rows,
            f'UPDATE smart_scripts SET `{column}` = {changed!r} '
            'WHERE entryorguid = 20281 AND source_type = 0 AND id = 15')
        assert before == after, ('the repair rounded away a customized coordinate', column)


drijya_guard = re.search(r' AND MIN\(\((.*?)\) IN \(.*?\)\) = 1', repair_sql, re.DOTALL)
assert drijya_guard, 'the Drijya repair must compare complete rows'
assert re.findall(r'`(\w+)`', drijya_guard[1]) == columns('smart_scripts'), 'the repair omitted a native script column'
check_drijya_customizations(repair_sql)
for label, mutant in (
    ('complete customized Drijya rows', repair_sql.replace(drijya_guard[0], '', 1)),
    ('complete Drijya row count', repair_sql.replace('COUNT(*) = 22 AND ', '', 1)),
):
    assert mutant != repair_sql, label
    try:
        check_drijya_customizations(mutant)
    except AssertionError:
        print('Netherstorm guard mutation rejected: ' + label)
    else:
        raise AssertionError('the Drijya fixture accepted ' + label)
without_float_casts = re.sub(r'CAST\(([^()]+) AS FLOAT\)', r'\1', repair_sql)
assert without_float_casts != repair_sql
unrounded_fresh, unrounded_existing = realms(without_float_casts)
assert snapshot(unrounded_fresh) != snapshot(unrounded_existing), 'the fixture missed native FLOAT comparison precision'
print('Netherstorm guard mutation rejected: unrounded native coordinate literals')


# Each guard keeps a row the realm changed since the core update.
for label, rows, customize, guard in (
    ('custom spawn', 'creature WHERE guid = 52066', 'UPDATE creature SET id = 99999 WHERE guid = 52066',
     ' AND `id` = 18855'),
    ('custom addon', 'creature_addon WHERE guid = 70141', 'UPDATE creature_addon SET emote = 1 WHERE guid = 70141',
     '\n  AND `emote` = 0'),
    ('custom formation', 'creature_formations WHERE memberGUID = 70141',
     'UPDATE creature_formations SET point_1 = 1 WHERE memberGUID = 70141', ' AND `point_1` = 0'),
):
    assert guard in repair_sql, label
    before, after = customized(repair_sql, rows, customize)
    assert before == after, ('the repair changed a customized row', label)
    before, after = customized(repair_sql.replace(guard, '', 1), rows, customize)
    assert before != after, ('guard mutation undetected', label)
    print('Netherstorm guard mutation rejected: ' + label)

# Wetlands and Netherstorm: later core updates replace the module's Dark Iron
# scripts and its Mageslayer height only on realms that applied the zones first.
wetlands = ip / 'data/sql/world/base/zone_wetlands.sql'
later_repair = ip / 'data/sql/world/updates/zz_2026_10_31_00_wetlands_netherstorm_core_updates.sql'
later_core = [updates / name for name in ('2026_10_17_01.sql', '2026_10_22_00.sql')]
assert all(path.name < zone.name < wetlands.name < later_repair.name for path in later_core)
DARK_IRON = (1051, 1052, 1053, 1054, 6523)
POSITION = ('position_x', 'position_y', 'position_z')
creature_schema = (world / 'creature.sql').read_text().split('CREATE TABLE `creature` (')[1].split(') ENGINE')[0]
assert all(re.search(rf'^  `{column}` float NOT NULL\b', creature_schema, re.MULTILINE) for column in POSITION)
base_columns = ['id' if column == 'id1' else column for column in columns('creature')]
base_row = re.search(r'^\((67474,18866,[^\n]*)\),?$', (world / 'creature.sql').read_text(), re.MULTILINE)[1]
base_values = dict(zip(base_columns, base_row.split(',')))
assert base_values['map'] == '530', base_values


def later_statements(path):
    chosen = []
    for statement in statements(path.read_text()):
        table = TABLE.match(statement)
        keys = {'smart_scripts': DARK_IRON[:4], 'creature': (67474,)}.get(table[1]) if table else None
        if keys and any(re.search(rf'\b{key}\b', statement) for key in keys):
            chosen.append(statement.replace("\\'", "''"))
    assert chosen, path
    return chosen


def later_realms(sql):
    fresh, existing = sqlite3.connect(':memory:'), sqlite3.connect(':memory:')
    for db, order in ((fresh, [*later_core, zone, wetlands]), (existing, [zone, wetlands, *later_core])):
        db.create_function('FLOAT32', 1, lambda value: struct.unpack('<f', struct.pack('<f', value))[0])
        db.execute('CREATE TABLE `smart_scripts` (' + ','.join(f'`{c}`' for c in columns('smart_scripts')) + ')')
        db.execute('CREATE TABLE `creature` (`guid`, `id`, `map`, `position_x`, `position_y`, `position_z`)')
        db.execute('INSERT INTO `creature` VALUES (?, ?, ?, ?, ?, ?)',
                   [float(base_values[column]) if column in POSITION else int(base_values[column])
                    for column in ('guid', 'id', 'map', *POSITION)])
        for path in order:
            for statement in later_statements(path):
                db.execute(statement)
            later_replay(db, '')
        later_replay(db, sql)
    return fresh, existing


def later_replay(db, sql):
    replay_repair(db, sql)
    # The native position columns store single precision, unlike SQLite's REAL.
    db.execute('UPDATE creature SET ' + ', '.join(f'`{c}` = FLOAT32(`{c}`)' for c in POSITION))


def later_snapshot(db):
    scripts = sorted(db.execute('SELECT * FROM smart_scripts WHERE source_type = 0 AND entryorguid IN '
                                f'({",".join(map(str, DARK_IRON))})'))
    return scripts, db.execute('SELECT * FROM creature').fetchall()


later_sql = later_repair.read_text()
fresh, existing = later_realms(later_sql)
expected = later_snapshot(fresh)
assert later_snapshot(existing) == expected, 'existing realms keep core rows a fresh realm replaces'
later_replay(existing, later_sql)
assert later_snapshot(existing) == expected, 'the Wetlands and Netherstorm repair is not idempotent'
# The module scripts its four dwarves; the core's Gift of Ragnaros fix still reaches the rifleman.
assert [row[0] for row in expected[0]].count(1054) == 7
assert any(row[0] == 6523 and row[15] == 7891 and row[16] == 0 and row[21] == 2 for row in expected[0])
assert expected[1][0][-1] == struct.unpack('<f', struct.pack('<f', 76.2261))[0], expected[1]
fresh_before, existing_before = later_realms('')
assert later_snapshot(fresh_before) == expected, 'the repair changed a fresh realm'
assert later_snapshot(existing_before) != expected, 'omitting the repair did not reproduce the existing-realm rows'
print('Wetlands and Netherstorm update order: fresh and existing realms match after an idempotent repair')

later_guard = re.search(r' AND MIN\(\((.*?)\) IN \(.*?\)\) = 1', later_sql, re.DOTALL)
assert later_guard and re.findall(r'`(\w+)`', later_guard[1]) == columns('smart_scripts')
count_guard = f'COUNT(*) = {sum(row[0] != 6523 for row in later_snapshot(existing_before)[0])} AND '
# Each guard keeps rows the realm changed since the core update.
for label, rows, customize, guard in (
    ('customized Dark Iron row', 0,
     'UPDATE smart_scripts SET event_chance = 99 WHERE entryorguid = 1051 AND id = 1', later_guard[0]),
    ('removed Dark Iron row', 0, 'DELETE FROM smart_scripts WHERE entryorguid = 1054 AND id = 3', count_guard),
    ('customized Mageslayer height', 1, 'UPDATE creature SET position_z = 77',
     ' AND `position_z` = CAST(76.0324 AS FLOAT)'),
):
    assert guard in later_sql, label
    for sql, kept in ((later_sql, True), (later_sql.replace(guard, '', 1), False)):
        _, db = later_realms('')
        db.execute(customize)
        before = later_snapshot(db)[rows]
        later_replay(db, sql)
        assert (later_snapshot(db)[rows] == before) == kept, ('the repair changed a customized row' if kept else
                                                         'guard mutation undetected', label)
    print('Wetlands and Netherstorm guard mutation rejected: ' + label)
unrounded = re.sub(r'CAST\(([^()]+) AS FLOAT\)', r'\1', later_sql)
assert unrounded != later_sql
assert later_snapshot(later_realms(unrounded)[1]) != expected, 'the fixture missed native FLOAT comparison precision'
print('Wetlands and Netherstorm guard mutation rejected: unrounded native coordinate literals')

# One-shot repairs run once per realm. When a file they follow changes, the
# updater reapplies it on existing realms, so the repair must change with it.
def sha1(path):
    return hashlib.sha1(path.read_bytes()).hexdigest()


era_events = modules / 'mod-era-events/data/sql/db-world/updates'
PRODUCERS = (
    (zone, repair, '0808c731b2e5755424e24124ab31bd2393b07230'),
    (zone, later_repair, '0808c731b2e5755424e24124ab31bd2393b07230'),
    (wetlands, later_repair, '93ab50bef6b28aa8209d22f26fd0ed57a5abe8aa'),
    (modules / 'mod-era-talents/data/sql/world/base/2026_10_11_00_historical_priest_training.sql',
     modules / 'mod-era-talents/data/sql/world/updates/2026_10_24_00_historical_priest_singletons.sql',
     '4aaacd37c09cb3296cafb2f22b3a32063d67055a'),
    (era_events / 'mod_era_events_2026_09_29_02_aq_war.sql',
     era_events / 'mod_era_events_2026_10_24_00_aq_dragon_menus.sql', '06b10439340d609ba0bdfcc1d159c09e1ea6cc6c'),
)
for producer, follower, digest in PRODUCERS:
    assert producer.name < follower.name, (producer.name, follower.name)
    assert sha1(producer) == digest, (f'{producer.name} changed ({sha1(producer)}): check {follower.name} '
                                      'against it and change the repair too, so existing realms rerun it')
print(f'One-shot repairs: {len(PRODUCERS)} producers unchanged and ordered before their repairs')
