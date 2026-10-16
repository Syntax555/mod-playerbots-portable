#!/usr/bin/env python3
"""Generate Individual Progression's era quest experience tables.

  python3 scripts/generate_era_quest_xp.py --classic-db <checkout> --tbc-db <checkout> --core <prepared core> \\
      --output <file>

custom_quest_xp_tbc holds each quest's 2.4.3 full value and quest level: CMaNGOS
mangos-tbc Quest::XPValue applied to the quest_template records of the CMaNGOS
TBC DB revision pinned in versions.lock.json. custom_quest_xp_level holds the
1.12 quest level of Individual Progression's custom_quest_xp values from the
pinned CMaNGOS Classic DB. Rows are written for quests the AzerothCore world
database contains. Write the output into a patchwork work tree of
mod-individual-progression-era-experience.patch.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
from pathlib import Path
import re
import struct
import subprocess


REPOSITORY = Path(__file__).resolve().parents[1]
CLASSIC_SOURCE, SOURCE, CORE_SOURCE = 'cmangos-classic-db', 'cmangos-tbc-db', 'cmangos-mangos-tbc'
CLASSIC_DUMP = 'Full_DB/ClassicDB_1_12_1_z2815.sql.gz'
DUMP = 'Full_DB/TBCDB_1.11.0_Vengeance_One_A_Cmangos_Story.sql.gz'
CORE_QUESTS = 'data/sql/base/db_world/quest_template.sql'
IP_QUESTS = 'modules/mod-individual-progression/data/sql/world/base/quest_xp_table.sql'
TOKEN = re.compile(r"'(?:[^'\\]|\\.|'')*'|[(),;]|[^\s(),;']+")


def float32(value: float) -> float:
    return struct.unpack('<f', struct.pack('<f', value))[0]


# mangos-tbc divides in single precision; these are the float literals it uses.
DIVISORS = {61: float32(1.2), 62: float32(2.4), 63: float32(3.6), 64: float32(4.8)}
DIVISOR_TO_60, DIVISOR_FROM_65 = float32(0.6), float32(6.0)


def full_xp(quest_level: int, money: int) -> int:
    """XP a character at most five levels above the quest earns, per mangos-tbc Quest::XPValue."""
    if money <= 0 or quest_level <= 0:
        return 0
    divisor = DIVISOR_FROM_65 if quest_level >= 65 else DIVISORS.get(quest_level, DIVISOR_TO_60)
    # Both operands are exact in single precision, so the rounded double quotient
    # equals the single-precision division.
    return math.ceil(float32(float32(money) / divisor))


def table_columns(text: str, table: str) -> list[str]:
    match = re.search(rf'CREATE TABLE `{re.escape(table)}` \((.*?)\n\)', text, re.DOTALL)
    if not match:
        raise ValueError(f'{table} has no CREATE TABLE statement')
    return re.findall(r'^\s*`([^`]+)`\s', match[1], re.MULTILINE)


def table_rows(text: str, table: str):
    """Rows of every INSERT INTO table VALUES statement as dicts of raw SQL tokens."""
    columns = table_columns(text, table)
    for statement in re.finditer(rf'INSERT INTO `{re.escape(table)}` VALUES', text):
        tokens = TOKEN.finditer(text, statement.end())
        row = None
        for token in (match[0] for match in tokens):
            if token == ';':
                break
            if token == '(':
                row = []
            elif token == ')':
                if len(row) != len(columns):
                    raise ValueError(f'{table} row has {len(row)} values for {len(columns)} columns')
                yield dict(zip(columns, row))
                row = None
            elif token != ',':
                row.append(token)
        else:
            raise ValueError(f'{table} INSERT statement is not terminated')


def ip_values(text: str) -> dict[int, int]:
    """Individual Progression's custom_quest_xp rows."""
    return {int(entry): int(xp) for entry, xp in re.findall(r'^\((\d+), (\d+)\)[,;]$', text, re.MULTILINE)}


def pinned_revision(name: str, repository: Path = REPOSITORY) -> str:
    lock = json.loads((repository / 'versions.lock.json').read_text(encoding='utf-8'))
    return next(source['revision'] for source in lock['historicalClassData']['sources'] if source['name'] == name)


def checkout_revision(checkout: Path) -> str:
    return subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], check=True, capture_output=True,
                          text=True).stdout.strip()


def tbc_values(dump: str, core_quests: str) -> list[tuple[int, int, int]]:
    """(entry, full value, quest level) per quest."""
    available = {int(row['ID']) for row in table_rows(core_quests, 'quest_template')}
    values = {}
    for row in table_rows(dump, 'quest_template'):
        entry, level = int(row['entry']), int(row['QuestLevel'])
        # mangos-tbc pays nothing for quests without a positive level; the core value stays.
        if level > 0 and entry in available:
            values[entry] = (full_xp(level, int(row['RewMoneyMaxLevel'])), level)
    return [(entry, xp, level) for entry, (xp, level) in sorted(values.items())]


def vanilla_levels(dump: str, core_quests: str, ip: dict[int, int]) -> list[tuple[int, int]]:
    """(entry, 1.12 quest level) per Individual Progression value; patch 2.3.0 lowered many levels."""
    available = {int(row['ID']) for row in table_rows(core_quests, 'quest_template')} & set(ip)
    levels = {}
    for row in table_rows(dump, 'quest_template'):
        entry, level = int(row['entry']), int(row['QuestLevel'])
        if level > 0 and entry in available:
            levels[entry] = level
    return sorted(levels.items())


def render(tbc: list[tuple[int, int, int]], levels: list[tuple[int, int]], classic_revision: str, revision: str,
           core_revision: str) -> str:
    return f'''-- Quest experience for the eras of Individual Progression.
-- 2.4.3 full value and quest level per quest: CMaNGOS mangos-tbc {core_revision}
-- Quest::XPValue (GPL-2.0-or-later) applied to QuestLevel and RewMoneyMaxLevel of
-- quest_template in CMaNGOS tbc-db {revision} {DUMP} (GPLv3).
-- 1.12 quest level of custom_quest_xp values: QuestLevel of quest_template in
-- CMaNGOS classic-db {classic_revision} {CLASSIC_DUMP} (GPLv3).
-- Generated by scripts/generate_era_quest_xp.py for quests in the AzerothCore world database.
DROP TABLE IF EXISTS `custom_quest_xp_tbc`;
CREATE TABLE `custom_quest_xp_tbc` (
    `entry` int unsigned NOT NULL,
    `xpValue` int unsigned NOT NULL,
    `questLevel` int NOT NULL,
    PRIMARY KEY (`entry`)
) ENGINE=InnoDB;

INSERT INTO `custom_quest_xp_tbc` (`entry`, `xpValue`, `questLevel`) VALUES
''' + ',\n'.join(f'({entry}, {xp}, {level})' for entry, xp, level in tbc) + ''';

DROP TABLE IF EXISTS `custom_quest_xp_level`;
CREATE TABLE `custom_quest_xp_level` (
    `entry` int unsigned NOT NULL,
    `questLevel` int NOT NULL,
    PRIMARY KEY (`entry`)
) ENGINE=InnoDB;

INSERT INTO `custom_quest_xp_level` (`entry`, `questLevel`) VALUES
''' + ',\n'.join(f'({entry}, {level})' for entry, level in levels) + ';\n'


def read_dump(checkout: Path, source: str, dump: str, columns: tuple[str, ...], repository: Path) -> tuple[str, str]:
    """The dump of a pinned checkout and its revision; refuses updates that could change the columns used."""
    revision = pinned_revision(source, repository)
    actual = checkout_revision(checkout)
    if actual != revision:
        raise SystemExit(f'{checkout} is at {actual}; versions.lock.json pins {source} {revision}')
    pattern = re.compile(r'\b(INSERT|REPLACE|DELETE)\b[^;]*\bquest_template\b|\b(' + '|'.join(columns) + r')\b',
                         re.IGNORECASE)
    updated = []
    for path in sorted((checkout / 'Updates').glob('*.sql')):
        text = path.read_text(encoding='utf-8', errors='replace')
        if 'quest_template' in text and pattern.search(text):
            updated.append(path.name)
    if updated:
        raise SystemExit(f'{source} updates change quest_template and are not applied: {", ".join(updated)}')
    with gzip.open(checkout / dump, 'rt', encoding='utf-8', errors='replace') as handle:
        return handle.read(), revision


def generate(classic_db: Path, tbc_db: Path, core: Path, repository: Path = REPOSITORY) -> str:
    classic, classic_revision = read_dump(classic_db, CLASSIC_SOURCE, CLASSIC_DUMP, ('QuestLevel',), repository)
    dump, revision = read_dump(tbc_db, SOURCE, DUMP, ('QuestLevel', 'RewMoneyMaxLevel'), repository)
    core_quests = (core / CORE_QUESTS).read_text(encoding='utf-8')
    ip = ip_values((core / IP_QUESTS).read_text(encoding='utf-8'))
    return render(tbc_values(dump, core_quests), vanilla_levels(classic, core_quests, ip), classic_revision, revision,
                  pinned_revision(CORE_SOURCE, repository))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--classic-db', type=Path, required=True,
                        help='CMaNGOS classic-db checkout at the pinned revision')
    parser.add_argument('--tbc-db', type=Path, required=True, help='CMaNGOS tbc-db checkout at the pinned revision')
    parser.add_argument('--core', type=Path, required=True, help='prepared AzerothCore source directory')
    parser.add_argument('--output', type=Path, required=True, help='SQL file to write')
    args = parser.parse_args()
    contents = generate(args.classic_db, args.tbc_db, args.core)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(contents, encoding='utf-8', newline='\n')
    print(f'Wrote {args.output}')


if __name__ == '__main__':
    main()
