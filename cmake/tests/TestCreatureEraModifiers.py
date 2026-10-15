"""Replay the core modifier update and the delivered era repair on scoped world rows."""

import argparse
import json
from pathlib import Path
import re
import sqlite3
import struct
import subprocess

from FixtureSupport import prepared_core


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--core', type=Path)
parser.add_argument('--module', type=Path)
args = parser.parse_args()
repository = Path(__file__).resolve().parents[2]
core = args.core or prepared_core(repository)
module = args.module or core / 'modules/mod-individual-progression'
relative = 'data/sql/updates/db_world/2026_09_27_06.sql'
upstream = (core / relative).read_text()
revision = json.loads((repository / 'versions.lock.json').read_text())['core']['revision']
assert upstream == subprocess.check_output(
    ['git', '-C', str(repository / 'azerothcore-wotlk'), 'show', f'{revision}:{relative}'], text=True)
migration = module / 'data/sql/world/updates/2026_10_14_00_creature_era_modifiers.sql'
repair = migration.read_text()
fields = ('DamageModifier', 'ArmorModifier', 'ExperienceModifier')
assignment = re.compile(r'`(DamageModifier|ArmorModifier)`\s*=\s*([-+\d.eE]+)')
updates = re.compile(r'UPDATE\s+`creature_template`\s+SET\s+(.*?)\s+WHERE\s+(.*?);', re.DOTALL)
entries = sorted({int(entry) for entry in re.findall(r'WHERE `entry` = (\d+);', upstream)})
assert len(entries) == 1203

# Project the actual era SQL onto only the modifier columns under test.
era_sql, managed = [], set()
base = module / 'data/sql/world/base'
for name in ('tbc_creatures.sql', 'vanilla_creatures.sql'):
    source = re.sub(r'/\*.*?\*/|--[^\n]*', '', (base / name).read_text(), flags=re.DOTALL)
    for setters, where in updates.findall(source):
        values = assignment.findall(setters)
        if not values:
            continue
        assert re.fullmatch(r'`entry`\s*(?:=\s*\d+|IN\s*\([\d,\s]+\))', where.strip(), re.IGNORECASE), where
        ids = set(map(int, re.findall(r'\d+', where))) & set(entries)
        managed.update((entry, field) for entry in ids for field, _ in values)
        era_sql.append('UPDATE creature_template SET ' + ', '.join(
            f'`{field}`={value}' for field, value in values) + ' WHERE ' + where + ';')
era_sql = '\n'.join(era_sql)


def f32(value):
    return struct.unpack('f', struct.pack('f', value))[0]


def execute(db, sql):
    db.executescript(sql)
    # MySQL stores the modifiers as FLOAT; SQLite otherwise retains doubles.
    rows = db.execute('SELECT entry, DamageModifier, ArmorModifier, ExperienceModifier FROM creature_template').fetchall()
    db.executemany('UPDATE creature_template SET DamageModifier=?, ArmorModifier=?, ExperienceModifier=? WHERE entry=?',
                   [(f32(damage), f32(armor), f32(xp), entry) for entry, damage, armor, xp in rows])


def database():
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE creature_template (entry INTEGER PRIMARY KEY, DamageModifier REAL, '
               'ArmorModifier REAL, ExperienceModifier REAL, HealthModifier REAL, name TEXT)')
    db.executemany('INSERT INTO creature_template VALUES (?, 1, 1, 1, 7.5, ?)',
                   [(entry, f'creature {entry}') for entry in [*entries, 999999]])
    return db


def snapshot(db):
    return {row[0]: row[1:] for row in db.execute('SELECT * FROM creature_template ORDER BY entry')}


def check(sql):
    with database() as db:
        execute(db, era_sql)
        era = snapshot(db)
        execute(db, upstream)
        changed = snapshot(db)
        conflicts = {(entry, field) for entry, field in managed
                     if changed[entry][fields.index(field)] != era[entry][fields.index(field)]}
        assert len(conflicts) == 534 and len({entry for entry, _ in conflicts}) == 532
        expected = {entry: list(row) for entry, row in changed.items()}
        for entry, field in conflicts:
            column = fields.index(field)
            expected[entry][column] = era[entry][column]
        expected = {entry: tuple(row) for entry, row in expected.items()}
        execute(db, sql)
        assert snapshot(db) == expected, 'era repair missing, incomplete or outside its scope'
        execute(db, sql)
        assert snapshot(db) == expected, 'repair is not idempotent'

    # A realm that already imported the upstream update can have later per-field customizations.
    for residue in range(3):
        with database() as db:
            execute(db, era_sql)
            execute(db, upstream)
            custom = dict(expected)
            for index, (entry, field) in enumerate(sorted(conflicts)):
                if index % 3 != residue:
                    continue
                value = f32(123.456789)
                db.execute(f'UPDATE creature_template SET `{field}`=? WHERE entry=?', (value, entry))
                row = list(custom[entry])
                row[fields.index(field)] = value
                custom[entry] = tuple(row)
            execute(db, sql)
            assert snapshot(db) == custom, 'repair overwrote a custom field'
            missing = min(entry for entry, _ in conflicts)
            db.execute('DELETE FROM creature_template WHERE entry=?', (missing,))
            before = snapshot(db)
            execute(db, sql)
            assert snapshot(db) == before, 'repair recreated a missing creature'

    # Fresh module SQL is filename-sorted: the numeric repair precedes the original era bases.
    with database() as db, database() as reference:
        execute(db, upstream)
        execute(db, sql)
        execute(db, era_sql)
        execute(reference, upstream)
        execute(reference, era_sql)
        assert snapshot(db) == snapshot(reference), 'fresh-install era data changed'


# Assert the native updater contracts used by the old-realm and fresh-install cases.
updater = (core / 'src/server/database/Updater/UpdateFetcher.cpp').read_text()
assert updater.index('availableQuery.second != PENDING && availableQuery.second != CUSTOM && '
                     'availableQuery.second != MODULE') < updater.index(
    'availableQuery.second == PENDING || availableQuery.second == CUSTOM || availableQuery.second == MODULE')
assert 'left.first.filename().string() < right.first.filename().string()' in updater
assert 'FillFileListRecursively(itr->path(), storage, state, depth + 1)' in updater
assert '"/modules/" + moduleName + "/data/sql/"' in updater
assert 'AppliedFileEntry::StateConvert("MODULE")' in updater
assert 'if (iter->second.hash != hash)' in updater
assert 'Update is already applied and matches the hash' in updater
module_files = [migration.name, 'tbc_creatures.sql', 'vanilla_creatures.sql']
assert module_files == sorted(module_files)
assert len([path for path in core.glob('modules/*/data/sql/**/*.sql') if path.name == migration.name]) == 1
check(repair)
print('Era modifiers: 532 creatures/534 fields, core-to-module upgrade, float storage, custom fields, '
      'idempotence, missing rows, unrelated values and fresh installation passed')
for name, mutant in (
    ('missing repair', ''),
    ('missing current-value guards', re.sub(
        r' AND ROUND\(`(?:DamageModifier|ArmorModifier)`, 6\) = [-+\d.eE]+', '', repair)),
    ('missing float rounding', re.sub(r'ROUND\((`(?:DamageModifier|ArmorModifier)`), 6\)', r'\1', repair)),
):
    assert mutant != repair, name
    try:
        check(mutant)
    except AssertionError:
        print(f'Era modifier mutation rejected: {name}')
    else:
        raise AssertionError(f'Era modifier fixture accepted {name}')
