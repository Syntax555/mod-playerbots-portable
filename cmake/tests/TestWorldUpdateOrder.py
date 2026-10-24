"""Replay world SQL in the native updater order for fresh and existing realms."""

import argparse
from collections import Counter
import math
import re
import sqlite3

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
    for table in KEYS:
        db.execute(f'CREATE TABLE `{table}` (' + ','.join(f'`{column}`' for column in columns(table)) + ')')
    db.execute('CREATE TABLE `creature` (' + ','.join(f'`{column}`' for column in creature_columns) + ')')
    return db


def run(db, paths, sources=None):
    for path in paths:
        for statement in (sources or {}).get(path) or relevant(path):
            db.execute(statement)


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
        db.executescript(sql)
    return fresh, existing


fresh, existing = realms(repair_sql)
assert snapshot(fresh) == snapshot(existing), 'existing realms keep core rows a fresh realm replaces'
expected = snapshot(fresh)
for db in (fresh, existing):
    db.executescript(repair_sql)
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
    db.executescript(sql)
    return before, sorted(db.execute('SELECT * FROM ' + rows))


# Each guard keeps a row the realm changed since the core update.
for label, rows, customize, guard in (
    ('custom Drijya script', 'smart_scripts WHERE entryorguid = 20281 AND source_type = 0',
     'UPDATE smart_scripts SET action_param1 = 6000 WHERE entryorguid = 20281 AND source_type = 0 AND id = 6',
     ' AND SUM(`action_param1`) = 4203637'),
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
