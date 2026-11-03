#!/usr/bin/env python3
"""Repair expansion stat tables of the creatures Individual Progression restores.

  python3 scripts/generate_era_creature_stats.py --classic-db <checkout> --tbc-db <checkout> \\
      --core <prepared core> --ip <Individual Progression checkout> --output <file>

The era bases already supply historical levels and modifiers, but leave Wrath's
exp column behind. Select the earliest same-identity historical creature's stat
table for those entries. Restore missing outdoor boss/guard levels only where
later-expansion stats leaked into a stock template untouched by module stat SQL.
Keep Wrath Onyxia and Naxxramas outside this scope. Per-field current-value guards
preserve custom values on existing realms without reapplying the era bases.
"""

from __future__ import annotations

import argparse
import gzip
from pathlib import Path
import re

from generate_era_quest_xp import (
    CLASSIC_DUMP,
    CLASSIC_SOURCE,
    DUMP,
    REPOSITORY,
    SOURCE,
    TOKEN,
    checkout_revision,
    pinned_revision,
    table_rows,
)
from generate_era_world_content import is_helper


CORE_CREATURES = 'data/sql/base/db_world/creature_template.sql'
CORE_SPAWNS = 'data/sql/base/db_world/creature.sql'
MIGRATION = 'zz_2026_11_03_01_creature_era_stats.sql'
BASES = ('tbc_creatures.sql', 'vanilla_creatures.sql')
REPLACEMENTS = ('naxx40_creatures.sql', 'dungeon_onyxia.sql')
UPDATES = re.compile(r'UPDATE\s+`creature_template`\s+SET\s+(.*?)\s+WHERE\s+(.*?);', re.DOTALL | re.IGNORECASE)
WHERE = re.compile(r'`?entry`?\s*(?:=\s*\d+|IN\s*\([\d,\s]+\))', re.IGNORECASE)
STATS = ('minlevel', 'maxlevel', 'HealthModifier', 'unit_class', 'exp')
HISTORICAL_FIELDS = ('Name', 'Expansion', 'MinLevel', 'MaxLevel', 'HealthMultiplier', 'UnitClass')


def sql_string(value: str) -> str:
    """Decode a MySQL dump's quoted text before comparing creature identities."""
    if value[:1] not in ("'", '"') or value[-1:] != value[:1]:
        raise ValueError(f'Expected quoted SQL text: {value}')
    return re.sub(r'\\(.)', lambda match: {'0': '\0', 'n': '\n', 'r': '\r', 't': '\t', 'Z': '\x1a'}.get(
        match[1], match[1]), value[1:-1].replace(value[0] * 2, value[0]))


def without_comments(text: str) -> str:
    return re.sub(r"'(?:[^'\\]|\\.|'')*'|/\*.*?\*/|--[^\n]*",
                  lambda match: match[0] if match[0].startswith("'") else '', text, flags=re.DOTALL)


def managed_entries(ip: Path) -> set[int]:
    entries = set()
    for filename in BASES:
        for _, where in UPDATES.findall(without_comments((ip / 'data/sql/world/base' / filename).read_text())):
            if not WHERE.fullmatch(where.strip()):
                raise ValueError(f'Unsupported {filename} creature selection: {where}')
            entries.update(map(int, re.findall(r'\d+', where)))
    return entries


def replacement_names(ip: Path) -> set[str]:
    """Names of historical raid clones; the native difficulty templates remain Wrath encounters."""
    names = set()
    tokens = re.compile(r"'(?:[^'\\]|\\.|'')*'|\"(?:[^\"\\]|\\.|\"\")*\"|--[^\n]*|/\*.*?\*/|[(),;]|[^\s(),;'\"]+", re.DOTALL)
    for filename in REPLACEMENTS:
        text = (ip / 'data/sql/world/base' / filename).read_text()
        # Raid files use both MySQL quote styles and @ENTRY arithmetic in their explicit rows.
        for insert in re.finditer(r'INSERT INTO `creature_template`\s*\(([^)]*)\)\s*VALUES', text, re.DOTALL):
            columns = re.findall(r'`(\w+)`', insert[1])
            row, value = [], []
            for match in tokens.finditer(text, insert.end()):
                token = match[0]
                if token.startswith(('--', '/*')):
                    continue
                if token == ';':
                    break
                if token == '(':
                    row, value = [], []
                elif token in (',', ')'):
                    if value:
                        row.append(''.join(value))
                        value = []
                    if token == ')':
                        if len(row) != len(columns):
                            raise ValueError(f'{filename} has an unsupported creature replacement row')
                        names.add(sql_string(row[columns.index('name')]))
                else:
                    value.append(token)
    return names


def historical_rows(checkout: Path, source: str, dump: str, repository: Path) -> dict[int, dict[str, str]]:
    revision = pinned_revision(source, repository)
    if checkout_revision(checkout) != revision:
        raise SystemExit(f'{checkout} does not match versions.lock.json: {source} {revision}')
    with gzip.open(checkout / dump, 'rt', encoding='utf-8', errors='replace') as handle:
        rows = {int(row['Entry']): row for row in table_rows(handle.read(), 'creature_template')}
    # Replay the fields used here; refuse new unsupported writes instead of silently using stale data.
    for path in sorted((checkout / 'Updates').glob('*.sql')):
        text = without_comments(path.read_text(encoding='utf-8', errors='replace'))
        start = 0
        for token in TOKEN.finditer(text):
            if token[0] != ';':
                continue
            statement, start = text[start:token.start()].strip(), token.end()
            if not re.match(r'(?:UPDATE|INSERT\s+INTO|REPLACE\s+INTO|DELETE\s+FROM)\s+`?creature_template`?\b',
                            statement, re.IGNORECASE):
                continue
            update = re.fullmatch(r'UPDATE\s+`?creature_template`?\s+SET\s+(.*?)\s+WHERE\s+(.*)',
                                  statement, re.IGNORECASE | re.DOTALL)
            fields = re.findall(r"`?(" + '|'.join(HISTORICAL_FIELDS) + r")`?\s*=\s*('(?:[^'\\]|\\.|'')*'|[+-]?\d+(?:\.\d+)?)(?=\s*(?:,|$))",
                                update[1] if update else statement, re.IGNORECASE)
            selected = re.findall(r'`?\b(' + '|'.join(HISTORICAL_FIELDS) + r')\b`?\s*=',
                                  update[1] if update else statement, re.IGNORECASE)
            if statement.upper().startswith('UPDATE') and not selected:
                continue
            if not update or not fields or len(fields) != len(selected):
                raise SystemExit(f'{source}: unsupported creature identity/stat-table update in {path.name}')
            where = update[2].strip()
            if where.startswith('('):
                where = where.removeprefix('(').removesuffix(')').strip()
            where = re.sub(r"'(\d+)'", r'\1', where)
            if not WHERE.fullmatch(where):
                raise SystemExit(f'{source}: unsupported creature selection in {path.name}: {where}')
            for entry in map(int, re.findall(r'\d+', where)):
                if entry in rows:
                    for field, value in fields:
                        column = next(column for column in HISTORICAL_FIELDS if column.lower() == field.lower())
                        rows[entry][column] = value if column == 'Name' else value.strip("'")
        if re.search(r'\bcreature_template\b', text[start:], re.IGNORECASE):
            raise SystemExit(f'{source}: unterminated creature update in {path.name}')
    return rows


def overridden_entries(ip: Path) -> set[int]:
    """Entries with module stat overrides, including local SQL-variable selectors."""
    entries = set()
    for path in (ip / 'data/sql/world').rglob('*.sql'):
        if path.name == MIGRATION:
            continue
        text = without_comments(path.read_text(encoding='utf-8', errors='replace'))
        variables = dict(re.findall(r'SET\s+(@\w+)\s*:?=\s*(\d+)\s*;', text, re.IGNORECASE))
        for setters, where in UPDATES.findall(text):
            if not re.search(r'`(' + '|'.join(STATS) + r')`\s*=', setters, re.IGNORECASE):
                continue
            where = re.sub(r'@\w+', lambda match, variables=variables: variables.get(match[0], match[0]), where)
            where = re.sub(r'(\d+)\s*\+\s*(\d+)', lambda match: str(int(match[1]) + int(match[2])), where)
            where = where.strip().removeprefix('(').removesuffix(')') if where.strip().startswith('(') else where.strip()
            if not WHERE.fullmatch(where):
                # Naxx40's one map-wide override cannot touch outdoor-only entries.
                if re.fullmatch(r'`entry`\s+IN\s*\(\s*SELECT\s+`id`\s+FROM\s+`creature`\s+WHERE\s+`map`\s*=\s*533\s+AND\s+`spawnMask`\s*=\s*4\s*\)',
                                where, re.IGNORECASE):
                    continue
                raise ValueError(f'Unsupported module stat selection in {path.name}: {where}')
            entries.update(map(int, re.findall(r'\d+', where)))
    return entries


def outdoor_entries(spawns: str) -> set[int]:
    maps: dict[int, set[int]] = {}
    for row in table_rows(spawns, 'creature'):
        for field in ('id1', 'id2', 'id3'):
            entry = int(row[field])
            if entry:
                maps.setdefault(entry, set()).add(int(row['map']))
    return {entry for entry, locations in maps.items() if locations <= {0, 1, 530}}


def outdoor_repairs(classic: dict[int, dict[str, str]], tbc: dict[int, dict[str, str]], core: str,
                    outdoor: set[int], managed: set[int], overridden: set[int]) -> list[tuple[int, str, str, str, str]]:
    result = []
    for row in table_rows(core, 'creature_template'):
        entry = int(row['entry'])
        historical = classic.get(entry) or tbc.get(entry)
        if (entry not in outdoor or entry in managed or entry in overridden or historical is None
                or sql_string(row['name']) != sql_string(historical['Name'])
                or is_helper(sql_string(row['ScriptName']), sql_string(row['name']), int(row['flags_extra']))):
            continue
        expansion = 0 if entry in classic else int(historical['Expansion'])
        if expansion not in (0, 1) or int(historical['UnitClass']) not in (1, 2, 4, 8):
            continue
        if int(row['minlevel']) <= int(historical['MinLevel']) or int(row['maxlevel']) <= int(historical['MaxLevel']):
            continue
        origin = 0 if entry in classic else 1
        if int(row['exp']) <= expansion and int(row['minlevel']) <= (63 if origin == 0 else 73):
            continue
        values = (historical['MinLevel'], historical['MaxLevel'], historical['HealthMultiplier'],
                  historical['UnitClass'], str(expansion))
        for field, value in zip(STATS, values, strict=True):
            if float(value) != float(row[field]):
                result.append((entry, field, value, row[field], sql_string(row['name'])))
    return sorted(result)


def repairs(classic: dict[int, dict[str, str]], tbc: dict[int, dict[str, str]], core: str,
            managed: set[int], replacements: set[str] | None = None) -> list[tuple[int, int, int, str]]:
    result = []
    for row in table_rows(core, 'creature_template'):
        entry = int(row['entry'])
        historical = classic.get(entry) or tbc.get(entry)
        if entry not in managed or historical is None or sql_string(row['name']) != sql_string(historical['Name']):
            continue
        if sql_string(row['name']) in (replacements or ()) and any(
                int(row[f'difficulty_entry_{index}']) for index in (1, 2, 3)):
            continue
        expansion = 0 if entry in classic else int(historical['Expansion'])
        if expansion not in (0, 1):
            raise ValueError(f'{entry} has an unsupported historical Expansion: {expansion}')
        current = int(row['exp'])
        if current > expansion:
            result.append((entry, expansion, current, sql_string(row['name'])))
    return sorted(result)


def generate(classic_db: Path, tbc_db: Path, core: Path, ip: Path, repository: Path = REPOSITORY) -> str:
    classic = historical_rows(classic_db, CLASSIC_SOURCE, CLASSIC_DUMP, repository)
    tbc = historical_rows(tbc_db, SOURCE, DUMP, repository)
    templates = (core / CORE_CREATURES).read_text(encoding='utf-8')
    managed = managed_entries(ip)
    values = repairs(classic, tbc, templates, managed, replacement_names(ip))
    outdoor = outdoor_repairs(classic, tbc, templates, outdoor_entries((core / CORE_SPAWNS).read_text(encoding='utf-8')),
                              managed, overridden_entries(ip))
    text = f'''-- Expansion stat tables for creatures restored by Individual Progression.
-- CMaNGOS classic-db {pinned_revision(CLASSIC_SOURCE, repository)} and
-- tbc-db {pinned_revision(SOURCE, repository)} creature_template identity/Expansion (GPLv3),
-- including their Updates; generated by scripts/generate_era_creature_stats.py.
-- Vanilla uses BaseHealth/ BaseDamage column 0; TBC uses its recorded Expansion.
-- Keep the era bases' levels and modifiers, replacement encounter IDs and custom field values.
-- Stock outdoor templates missing era restoration also regain their historical levels/health/class.
-- Run after the era bases on fresh installations and as a late repair on existing realms.
'''
    for entry, expansion, current, name in values:
        text += f'-- {name}\nUPDATE `creature_template` SET `exp` = {expansion} WHERE `entry` = {entry} AND `exp` = {current};\n'
    for entry, field, value, current, name in outdoor:
        comparison = f'ROUND(`{field}`, 6) = {float(current):.6f}' if field == 'HealthModifier' else f'`{field}` = {current}'
        text += f'-- {name}\nUPDATE `creature_template` SET `{field}` = {value} WHERE `entry` = {entry} AND {comparison};\n'
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--classic-db', type=Path, required=True)
    parser.add_argument('--tbc-db', type=Path, required=True)
    parser.add_argument('--core', type=Path, required=True)
    parser.add_argument('--ip', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    text = generate(args.classic_db, args.tbc_db, args.core, args.ip)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding='utf-8', newline='\n')
    print(f'Wrote {args.output}: {text.count("UPDATE ")} fields')


if __name__ == '__main__':
    main()
