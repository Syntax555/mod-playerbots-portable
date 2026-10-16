#!/usr/bin/env python3
"""Generate Individual Progression's era quest experience tables.

  python3 scripts/generate_era_quest_xp.py --classic-db <checkout> --tbc-db <checkout> --core <prepared core> \\
      --output <file>

custom_quest_xp_tbc holds each quest's 2.4.3 full value and quest level: CMaNGOS
mangos-tbc Quest::XPValue applied to the quest_template records of the CMaNGOS
TBC DB revision pinned in versions.lock.json, leaving out records that cannot
hold the quest's value. custom_quest_xp_level holds the 1.12 quest level of
Individual Progression's custom_quest_xp values from the pinned CMaNGOS Classic
DB. Rows are written for quests the AzerothCore world database contains. Write
the output into a patchwork work tree of
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
# QuestXP.dbc Exp[1..8] for levels 1-100, recorded from the pinned client data
# (Haeniken/TrinityCore-3.3.5-data-multilang b21c949 dbc/deDE/QuestXP.dbc,
# SHA-256 ae88d842e994dccad08d58983f8c524c0aa51a3557ebbb5aa687098298a7b8d5); Exp[0] and Exp[9] are 0.
QUEST_XP = tuple(tuple(int(xp) for xp in row.split()) for row in '''
    10 20 40 60 80 100 120 160 | 15 45 85 130 170 215 255 340 | 25 65 125 190 250 315 380 500 | 35 90 180 270 355 445 540 710
    45 110 225 335 450 560 670 900 | 55 135 270 405 540 680 810 1080 | 65 160 315 475 630 790 950 1260 | 70 175 350 530 700 880 1050 1400
    80 195 390 590 780 980 1150 1560 | 85 210 420 630 840 1050 1250 1680 | 90 220 440 660 880 1100 1300 1760 | 90 225 455 680 910 1150 1350 1820
    90 230 455 680 910 1150 1350 1820 | 100 245 490 740 980 1250 1450 1960 | 105 270 540 800 1050 1350 1600 2100 | 115 290 580 880 1150 1450 1750 2300
    125 315 630 950 1250 1600 1900 2500 | 135 340 680 1000 1350 1700 2050 2700 | 145 365 730 1100 1450 1800 2200 2900 | 155 390 780 1150 1550 1950 2350 3100
    165 415 830 1250 1650 2050 2500 3300 | 175 435 870 1300 1750 2200 2600 3500 | 185 460 920 1400 1850 2300 2750 3700 | 195 485 970 1450 1950 2400 2900 3900
    200 510 1000 1500 2000 2550 3050 4000 | 210 530 1050 1600 2100 2650 3150 4200 | 220 550 1100 1650 2200 2750 3300 4400 | 230 570 1150 1700 2300 2850 3400 4600
    235 590 1200 1750 2350 2950 3550 4700 | 245 610 1200 1850 2450 3050 3650 4900 | 250 630 1250 1900 2540 3150 3800 5080 | 270 670 1350 2000 2710 3350 4050 5420
    290 720 1450 2150 2900 3600 4350 5800 | 310 770 1550 2300 3100 3850 4650 6200 | 330 820 1650 2450 3300 4100 4950 6600 | 350 870 1750 2600 3500 4350 5250 7000
    370 920 1850 2750 3710 4600 5550 7420 | 390 980 1950 2900 3920 4900 5850 7840 | 410 1030 2050 3100 4140 5150 6200 8280 | 435 1090 2150 3250 4370 5450 6550 8740
    455 1140 2250 3400 4590 5700 6850 9180 | 480 1200 2400 3600 4820 6000 7200 9640 | 505 1260 2500 3750 5050 6300 7550 10100 | 525 1320 2600 3950 5290 6600 7900 10580
    550 1380 2750 4150 5540 6900 8300 11080 | 575 1440 2850 4300 5790 7200 8650 11580 | 600 1510 3000 4500 6040 7550 9050 12080 | 625 1570 3100 4700 6290 7850 9400 12580
    655 1630 3250 4900 6550 8150 9800 13100 | 680 1700 3400 5100 6810 8500 10200 13620 | 705 1760 3500 5300 7070 8800 10600 14140 | 730 1830 3650 5500 7340 9150 11000 14680
    760 1900 3800 5700 7610 9500 11400 15220 | 785 1970 3900 5900 7890 9850 11800 15780 | 815 2040 4050 6100 8170 10200 12250 16340 | 845 2110 4200 6300 8450 10550 12650 16900
    870 2180 4350 6500 8730 10900 13050 17460 | 900 2250 4500 6750 9020 11250 13500 18040 | 930 2320 4650 6950 9310 11600 13950 18620 | 955 2380 4750 7150 9550 11900 14300 19100
    970 2400 4850 7300 9800 12200 14700 19600 | 1000 2550 5000 7600 10050 12600 15050 20100 | 1050 2600 5250 7800 10400 12950 15550 20800 | 1080 2650 5400 8050 10750 13350 16000 21500
    1100 2700 5500 8250 11000 13750 16500 22000 | 1130 2850 5650 8550 11300 14150 17000 22600 | 1160 2900 5800 8750 11650 14600 17450 23300 | 1200 3050 6000 9000 12000 14950 17950 24000
    1230 3100 6150 9250 12300 15400 18450 24600 | 1250 3150 6250 9500 12650 15800 19000 25300 | 2000 5050 10050 15100 20100 25150 30150 40200 | 2050 5100 10150 15250 20300 25400 30450 40600
    2050 5150 10250 15400 20500 25650 30750 41000 | 2100 5200 10400 15550 20750 25950 31150 41500 | 2100 5250 10500 15700 20950 26200 31450 41900 | 2100 5300 10600 15850 21150 26450 31750 42300
    2150 5350 10700 16050 21400 26750 32100 42800 | 2150 5400 10800 16200 21600 27000 32400 43200 | 2200 5450 10900 16350 21800 27250 32700 43600 | 2200 5500 11050 16550 22050 27550 33100 44100
    2250 5550 11150 16700 22250 27800 33400 44500 | 2250 5650 11250 16900 22500 28150 33750 45000 | 2250 5700 11350 17050 22700 28400 34050 45400 | 2300 5750 11500 17200 22950 28700 34450 45900
    2300 5800 11600 17400 23200 29000 34800 46400 | 2350 5850 11700 17550 23400 29250 35100 46800 | 2350 5900 11850 17750 23650 29550 35500 47300 | 2400 6000 11950 17950 23900 29900 35850 47800
    2400 6050 12050 18100 24100 30150 36150 48200 | 2450 6100 12200 18250 24350 30450 36550 48700 | 2450 6150 12300 18450 24600 30750 36900 49200 | 2500 6200 12450 18650 24850 31050 37300 49700
    2500 6300 12550 18850 25100 31400 37650 50200 | 2550 6350 12700 19000 25350 31700 38050 50700 | 2550 6400 12800 19200 25600 32000 38400 51200 | 2600 6450 12950 19400 25850 32300 38800 51700
    2600 6550 13050 19600 26100 32650 39150 52200 | 2650 6600 13200 19750 26350 32950 39550 52700 | 2650 6650 13300 19950 26600 33250 39900 53200 | 2700 6700 13450 20150 26850 33550 40300 53700
'''.replace('|', '\n').splitlines() if row.strip())
# QUEST_FLAGS_NO_MONEY_FROM_XP and QUEST_FLAGS_HIDDEN_REWARDS withhold the money at
# the maximum level, so a zero RewMoneyMaxLevel says nothing about the experience.
NO_MONEY_FLAGS = 0x100 | 0x200
# Some rows store six times the full value instead of six times the value at
# level 70, which makes it ten times too high; no other value exceeds 1.5 times
# the larger of the quest's 1.12 and 3.3.5 values.
MAX_RATIO = 4


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


def native_full_xp(quest_level: int, difficulty: int) -> int:
    """AzerothCore Quest::XPValue for a character at the quest's level."""
    if not 1 <= quest_level <= len(QUEST_XP) or not 1 <= difficulty <= 8:
        return 0
    xp = QUEST_XP[quest_level - 1][difficulty - 1]
    step = 5 if xp <= 100 else 10 if xp <= 500 else 25 if xp <= 1000 else 50
    return step * ((xp + step // 2) // step)


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


def tbc_values(dump: str, core_quests: str, ip: dict[int, int]) -> list[tuple[int, int, int]]:
    """(entry, full value, quest level) per quest; quests left out keep the 1.12 or 3.3.5 value."""
    core = {int(row['ID']): row for row in table_rows(core_quests, 'quest_template')}
    values = {}
    for row in table_rows(dump, 'quest_template'):
        entry, level, money = int(row['entry']), int(row['QuestLevel']), int(row['RewMoneyMaxLevel'])
        # mangos-tbc pays nothing for quests without a positive level; the core value stays.
        if level <= 0 or entry not in core or (not money and int(row['QuestFlags']) & NO_MONEY_FLAGS):
            continue
        xp, quest = full_xp(level, money), core[entry]
        native_level = int(quest['QuestLevel']) if int(quest['QuestLevel']) > 0 else level
        if xp <= MAX_RATIO * max(ip.get(entry, 0), native_full_xp(native_level, int(quest['RewardXPDifficulty']))):
            values[entry] = (xp, level)
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
-- quest_template in CMaNGOS tbc-db {revision} {DUMP} (GPLv3),
-- without values its QuestFlags or the 1.12 and 3.3.5 values show to be unusable.
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
    dump, revision = read_dump(tbc_db, SOURCE, DUMP, ('QuestLevel', 'RewMoneyMaxLevel', 'QuestFlags'), repository)
    core_quests = (core / CORE_QUESTS).read_text(encoding='utf-8')
    ip = ip_values((core / IP_QUESTS).read_text(encoding='utf-8'))
    return render(tbc_values(dump, core_quests, ip), vanilla_levels(classic, core_quests, ip), classic_revision, revision,
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
