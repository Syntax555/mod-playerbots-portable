#!/usr/bin/env python3
"""Generate Individual Progression's era gates for later-expansion world content.

  python3 scripts/generate_era_world_content.py --ip <checkout> --output <file> [--report <json>] \\
      [--mysql "mysql --defaults-file=<file>"] [--world acore_world] [--core-world core_world] \\
      [--classic cm_classic] [--tbc cm_tbc] [--wotlk cm_wotlk]

The MySQL server holds five databases: the realm's world database after every core
and module update except this file's own rows, the same world built from the core
alone, and the CMaNGOS classic-db, tbc-db and wotlk-db revisions pinned in
versions.lock.json, each loaded from Full_DB with its Updates directory. An entry
absent from Classic arrived with TBC and needs the rewarded TBC marker (66008); an
entry absent from TBC too arrived with Wrath and needs the Wrath marker (66013).

Creature and gameobject spawns on the old-world continents, and Wrath's in Outland, that
a character sees before their era get visibility conditions, which keep AI and scripts. Quests reachable before their era
and later-era items of vendors visible earlier get availability conditions. Spawns
are left alone when a module added or changed them, an awareness script decides,
they are invisible helpers, they would attack unseen, they keep collision or traps,
earlier quests use them, or the earlier database places the same name there; quests
and items the earlier database knows by the same name are left alone too. Write the
output into the Individual Progression fork's
data/sql/world/updates/zz_2026_10_31_01_era_world_content.sql and commit it there.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import shlex
import subprocess


REPOSITORY = Path(__file__).resolve().parents[1]
STAGES = range(19)
ALL = (1 << 19) - 1
MARKER = {1: 66008, 2: 66013}
REQUIRED = {1: 8, 2: 13}
ERA = {1: 'TBC', 2: 'Wrath'}
VANILLA_MAPS = {0, 1, 30, 33, 34, 36, 43, 47, 48, 70, 90, 109, 129, 189, 209, 229, 230, 249, 289, 309, 329, 349, 369,
                389, 409, 429, 469, 489, 509, 529, 531, 533,
                582, 584, 587, 589, 590, 591, 593}  # and the old-world transports
WRATH_MAPS = {571, 574, 575, 576, 578, 595, 599, 600, 601, 602, 603, 604, 607, 608, 609, 615, 616, 617, 618, 619, 624,
              628, 631, 632, 649, 650, 658, 668, 724,
              594, 610, 612, 613, 614, 620, 621, 622, 623, 641, 642, 647, 662, 672, 673, 712, 713, 718}  # and transports
# Gameobject types without collision, traps or encounter mechanics.
GAMEOBJECT_TYPES = {2, 3, 4, 5, 7, 8, 9, 10, 19, 22, 23, 25, 32, 34}
HELPER = re.compile(r'Trigger|Bunny|Credit|Marker|\[DND\]|\[PH\]|Invisible|Dummy')
# Faction capitals (map, x range, y range), Stormwind with its harbor: enemy players meet guards there anyway.
CAPITALS = ((0, -9150, -8000, 200, 1550), (0, -5150, -4550, -1350, -700), (0, 1450, 1950, 0, 600),
            (1, 1250, 2250, -4950, -3950), (1, -1500, -900, -200, 500), (1, 9450, 10250, 1750, 2750))
HOLIDAY_SORTS = {-22, -41, -284, -364, -366, -369, -370, -374, -375, -376, -1002, -1003, -1005}
UPDATE = 'data/sql/world/updates/zz_2026_10_31_01_era_world_content.sql'
OWN = "Comment NOT LIKE 'Era content: %'"


class Database:
    def __init__(self, command):
        self.command = [*shlex.split(command), '--max-allowed-packet=1G', '-N', '-B']

    def __call__(self, sql):
        result = subprocess.run([*self.command, '-e', sql], capture_output=True, text=True, check=False)
        if result.returncode:
            raise SystemExit(result.stderr)
        return [line.split('\t') for line in result.stdout.splitlines() if line]


def settings(ip):
    """Individual Progression defaults with the portable profile's overrides."""
    values = {}
    for path in (ip / 'conf/individualProgression.conf.dist', REPOSITORY / 'cmd/startup/profiles/individualProgression.conf'):
        for key, value in re.findall(r'^IndividualProgression\.(\w+(?:\.\w+)?)\s*=\s*(\S+)', path.read_text(), re.MULTILINE):
            values[key] = value
    return values


def awareness_rules(ip):
    """Stage masks of the awareness scripts' CanBeSeen decisions; None where the decision is not a stage rule."""
    enum = {name: int(value) for name, value in re.findall(
        r'(PROGRESSION_\w+)\s*=\s*(\d+)', (ip / 'src/IndividualProgression.h').read_text())}
    config = settings(ip)
    options = {'RequiredZulGurubProgression': int(config['RequiredZulGurubProgression']),
               'RequiredZulAmanProgression': int(config['RequiredZulAmanProgression'])}
    early_set = config['AllowEarlyDungeonSet2'] == '1'
    rules = {}
    for source in sorted((ip / 'src').rglob('*.cpp')):
        text = source.read_text()
        for match in re.finditer(r'(?:Creature|GameObject)Script\("(\w+)"\)', text):
            name = match.group(1)
            rules[name] = None
            end = text.find('Script("', match.end())
            body = text[match.end():end if end > 0 else len(text)]
            seen = re.search(r'bool CanBeSeen\(Player const\* player\) override\s*\{(.*?)\n        \}', body, re.DOTALL)
            if not seen:
                continue
            decision = re.findall(r'if \((.+)\)\s*return (true|false);\s*else\s*return (true|false);', seen.group(1))
            if not decision:
                continue
            expression, first, _ = decision[-1]
            # Local copies of the character's stage and of a configured requirement.
            for variable, option in re.findall(r'ProgressionState (\w+) = static_cast<ProgressionState>\('
                                               r'sIndividualProgression->(\w+)\);', seen.group(1)):
                expression = re.sub(rf'\b{variable}\b', str(options[option]), expression)
            for variable in re.findall(r'(\w+) = sIndividualProgression->GetPlayerProgressionFromQuests\(target\);',
                                       seen.group(1)):
                expression = re.sub(rf'\b{variable}\b', 's', expression)
            python = re.sub(r'sIndividualProgression->hasPassedProgression\(target,\s*(PROGRESSION_\w+)\)',
                            lambda m: f'(s >= {enum[m.group(1)]})', expression)
            python = re.sub(r'sIndividualProgression->isBeforeProgression\(target,\s*(PROGRESSION_\w+)\)',
                            lambda m: f'(s < {enum[m.group(1)]})', python)
            python = re.sub(r'sIndividualProgression->GetPlayerProgressionFromQuests\(target\) >= '
                            r'static_cast<ProgressionState>\(sIndividualProgression->(\w+)\)',
                            lambda m: f'(s >= {options[m.group(1)]})', python)
            # Any arena season counts; excluded and bot accounts are not players' views.
            python = re.sub(r'sIndividualProgression->(?:tbc|wotlk)ArenaSeason == \d+', 'True', python)
            python = re.sub(r'sIndividualProgression->is(?:Excluded|Bot)Account\(target\)', 'False', python)
            python = python.replace('sIndividualProgression->earlyDungeonSet2', str(early_set))
            python = python.replace('player->IsGameMaster()', 'False').replace('!sIndividualProgression->enabled', 'False')
            python = python.replace('&&', ' and ').replace('||', ' or ').replace('!', ' not ')
            if not re.fullmatch(r'[\s()<>=\dsandortTrueFals]+', python):
                continue
            visible = eval('lambda s: ' + python)  # arithmetic built from the module's own sources
            rules[name] = sum(1 << stage for stage in STAGES if bool(visible(stage)) == (first == 'true'))
    return rules


def map_mask(map_id):
    first = 0 if map_id in VANILLA_MAPS else 13 if map_id in WRATH_MAPS else 8
    return sum(1 << stage for stage in STAGES if stage >= first)


def in_capital(map_id, x, y):
    return any(map_id == m and x0 <= x <= x1 and y0 <= y <= y1 for m, x0, x1, y0, y1 in CAPITALS)


def generate(q, args):
    rules = awareness_rules(args.ip)
    world, earlier_dbs = args.world, {1: (args.classic,), 2: (args.classic, args.tbc)}

    def eras(table, key):
        result = {}
        for era, db in ((2, args.wotlk), (1, args.tbc), (0, args.classic)):
            result.update((int(entry), era) for (entry,) in q(f'SELECT {key} FROM {db}.{table}'))
        return result

    creature_era, gameobject_era = eras('creature_template', 'Entry'), eras('gameobject_template', 'entry')
    quest_era, item_era = eras('quest_template', 'entry'), eras('item_template', 'entry')
    visibility_gated = {(int(g), int(e)) for g, e in q(
        f'SELECT SourceGroup, SourceEntry FROM {world}.conditions WHERE SourceTypeOrReferenceId = 30 AND {OWN}')}
    hostile = {int(f) for (f,) in q(f'SELECT ID FROM {world}.factiontemplate_dbc WHERE EnemyGroup & 1')}
    one_side = {int(f) for (f,) in q(f'SELECT ID FROM {world}.factiontemplate_dbc WHERE EnemyGroup & 6')}
    core_spawns = {kind: {(int(g), int(e)) for g, e in q(f'SELECT guid, id FROM {args.core_world}.{table}')}
                   for kind, table in (('creature', 'creature'), ('gameobject', 'gameobject'))}
    earlier_spawns = {}
    for db in (args.classic, args.tbc):
        index = defaultdict(list)
        for name, map_id, x, y in q(
                f"""SELECT t.Name, s.map, s.position_x, s.position_y FROM {db}.creature s
                    JOIN {db}.creature_spawn_entry se ON se.guid = s.guid JOIN {db}.creature_template t ON t.Entry = se.entry
                    WHERE s.id = 0
                    UNION ALL SELECT t.Name, s.map, s.position_x, s.position_y FROM {db}.creature s
                    JOIN {db}.creature_template t ON t.Entry = s.id
                    UNION ALL SELECT CONCAT('go:', t.name), s.map, s.position_x, s.position_y FROM {db}.gameobject s
                    JOIN {db}.gameobject_template t ON t.entry = s.id"""):
            index[(name.lower(), int(map_id))].append((round(float(x)), round(float(y))))
        earlier_spawns[db] = index

    def renumbered(era, name, map_id, x, y):
        return next((db for db in earlier_dbs[era] for px, py in earlier_spawns[db].get((name.lower(), map_id), ())
                     if (px - x) ** 2 + (py - y) ** 2 <= 30 ** 2), None)

    starts, ends, objective = defaultdict(set), defaultdict(set), defaultdict(set)
    for kind, starter, ender in (('creature', 'creature_queststarter', 'creature_questender'),
                                 ('gameobject', 'gameobject_queststarter', 'gameobject_questender')):
        for entry, quest in q(f'SELECT id, quest FROM {world}.{starter}'):
            starts[(kind, int(entry))].add(int(quest))
        for entry, quest in q(f'SELECT id, quest FROM {world}.{ender}'):
            ends[(kind, int(entry))].add(int(quest))
    for quest, *required in q(f'SELECT ID, RequiredNpcOrGo1, RequiredNpcOrGo2, RequiredNpcOrGo3, RequiredNpcOrGo4 '
                              f'FROM {world}.quest_template'):
        for value in map(int, required):
            if value:
                objective[('creature' if value > 0 else 'gameobject', abs(value))].add(int(quest))
    disabled = {int(e) for (e,) in q(f'SELECT entry FROM {world}.disables WHERE sourceType = 1')}

    conditions, skipped = [], defaultdict(list)
    seen_before = {'creature': defaultdict(int), 'gameobject': defaultdict(int)}
    seen_after = {'creature': defaultdict(int), 'gameobject': defaultdict(int)}
    for kind, group in (('creature', 0), ('gameobject', 1)):
        template = 't.faction, t.flags_extra, t.npcflag, 0, t.unit_flags' if kind == 'creature' else '0, 0, 0, t.type, 0'
        events = {int(g) for (g,) in q(f'SELECT DISTINCT guid FROM {world}.game_event_{kind}')}
        known = creature_era if kind == 'creature' else gameobject_era
        for guid, entry, map_id, phase, script, name, x, y, faction, extra, npcflag, kind_type, unit_flags in q(
                f"""SELECT s.guid, s.id, s.map, s.phaseMask, COALESCE(NULLIF(s.ScriptName, ''), t.ScriptName), t.name,
                    s.position_x, s.position_y, {template}
                    FROM {world}.{kind} s JOIN {world}.{kind}_template t ON t.entry = s.id"""):
            guid, entry, map_id, x, y = int(guid), int(entry), int(map_id), float(x), float(y)
            if guid in events:
                continue
            rule = rules.get(script)
            mask = (map_mask(map_id) if int(phase) & 1 else 0) & (ALL if rule is None else rule)
            seen_before[kind][entry] |= mask
            era = known.get(entry)
            if era in REQUIRED and (map_id in (0, 1) or (era == 2 and map_id == 530)) and mask & ((1 << REQUIRED[era]) - 1):
                earlier = sorted(quest for quest in starts[(kind, entry)] | ends[(kind, entry)] | objective[(kind, entry)]
                                 if quest not in disabled and quest_era.get(quest, 9) < era)
                reason = None
                if (guid, entry) not in core_spawns[kind]:
                    reason = 'module', 'a module added or changed the spawn'
                elif script in rules:
                    reason = 'script', 'an awareness script decides'
                elif (group, entry) in visibility_gated:
                    reason = 'condition', 'an existing visibility condition decides'
                elif kind == 'creature' and (int(extra) & 128 or HELPER.search(name)):
                    reason = 'helper', 'invisible helper'
                elif (kind == 'creature' and not int(extra) & 2 and not int(unit_flags) & 0x100
                      and (int(faction) in hostile or (int(faction) in one_side and not int(npcflag)
                                                       and not in_capital(map_id, x, y)))):
                    reason = 'hostile', 'would attack unseen'
                elif kind == 'gameobject' and int(kind_type) not in GAMEOBJECT_TYPES:
                    reason = 'mechanics', f'type {kind_type} keeps collision or mechanics'
                elif earlier:
                    reason = 'quest', 'earlier quests ' + ','.join(map(str, earlier[:6]))
                elif source := renumbered(era, ('go:' + name) if kind == 'gameobject' else name, map_id,
                                          round(x), round(y)):
                    reason = 'renumbered', f'same name here in {source}'
                if reason:
                    skipped[f'{kind}:{reason[0]}'].append((f'{ERA[era]} {kind} {entry} {name}', guid, map_id, reason[1]))
                else:
                    conditions.append((30, group, entry, guid, MARKER[era]))
                    mask &= ~((1 << REQUIRED[era]) - 1)
            seen_after[kind][entry] |= mask

    # A quest zone opens with the maps most of its givers stand on; spawn zone ids are rarely filled.
    zone_maps = defaultdict(Counter)
    for zone, map_id in q(f"""SELECT q.QuestSortID, c.map FROM {world}.quest_template q
                               JOIN {world}.creature_queststarter s ON s.quest = q.ID JOIN {world}.creature c ON c.id = s.id
                               WHERE q.QuestSortID > 0"""):
        zone_maps[int(zone)][map_mask(int(map_id))] += 1
    zone_mask = {zone: maps.most_common(1)[0][0] for zone, maps in zone_maps.items()}
    holiday = {int(x) for (x,) in q(f"""SELECT quest FROM {world}.game_event_creature_quest
                                        UNION SELECT quest FROM {world}.game_event_gameobject_quest
                                        UNION SELECT questId FROM {world}.game_event_seasonal_questrelation""")}
    item_started = {int(x) for (x,) in q(f'SELECT DISTINCT startquest FROM {world}.item_template WHERE startquest > 0')}
    earlier_titles = {db: {t.strip().lower() for (t,) in q(f'SELECT Title FROM {db}.quest_template')}
                      for db in (args.classic, args.tbc)}
    gated = defaultdict(int)
    for quest, value in q(f"""SELECT SourceEntry, ConditionValue1 FROM {world}.conditions
                              WHERE SourceTypeOrReferenceId = 19 AND ConditionTypeOrReference IN (8, 28) AND NegativeCondition = 0
                              AND ConditionValue1 BETWEEN 66001 AND 66018 AND {OWN}"""):
        gated[int(quest)] = max(gated[int(quest)], int(value))
    followers = defaultdict(set)  # quests that need this one
    for quest, previous, following in q(f'SELECT ID, PrevQuestID, NextQuestID FROM {world}.quest_template_addon'):
        if int(previous) > 0:
            followers[int(previous)].add(int(quest))
        if int(following) > 0:
            followers[int(quest)].add(int(following))
    reachable = defaultdict(int)
    for (kind, entry), quests in starts.items():
        for quest in quests:
            reachable[quest] |= seen_before[kind].get(entry, 0)
    for quest, title, sort, races, classes in q(
            f"""SELECT q.ID, q.LogTitle, q.QuestSortID, q.AllowableRaces, COALESCE(a.AllowableClasses, 0)
                FROM {world}.quest_template q LEFT JOIN {world}.quest_template_addon a ON a.ID = q.ID"""):
        quest, sort, races, classes = int(quest), int(sort), int(races), int(classes)
        era = quest_era.get(quest)
        if era not in REQUIRED or quest in disabled or gated[quest] >= MARKER[era]:
            continue
        mask = reachable[quest]
        if quest in item_started:
            mask |= zone_mask.get(sort, ALL if sort < 0 and sort not in HOLIDAY_SORTS else 0)
        if not mask & ((1 << REQUIRED[era]) - 1):
            continue
        earlier = sorted(x for x in followers[quest] if quest_era.get(x, 9) < era)
        reason = None
        if quest in holiday or sort in HOLIDAY_SORTS:
            reason = 'holiday', 'holiday quest'
        elif era == 1 and races and not races & ~(512 | 1024):
            reason = 'race', 'blood elf or draenei quest'
        elif classes == 32:
            reason = 'class', 'death knight quest'
        elif any(title.strip().lower() in earlier_titles[db] for db in earlier_dbs[era]):
            reason = 'renumbered', 'same title in an earlier database'
        elif earlier:
            reason = 'chain', 'earlier quests follow it ' + ','.join(map(str, earlier[:6]))
        if reason:
            skipped[f'quest:{reason[0]}'].append((f'{ERA[era]} quest {quest} {title}', quest, sort, reason[1]))
        else:
            conditions.append((19, 0, quest, 0, MARKER[era]))

    vendor_gated = {(int(g), int(e)) for g, e in q(
        f'SELECT SourceGroup, SourceEntry FROM {world}.conditions WHERE SourceTypeOrReferenceId = 23 AND {OWN}')}
    earlier_wares = defaultdict(set)
    for db in (args.classic, args.tbc):
        for vendor, name in q(f"""SELECT v.entry, i.name FROM {db}.npc_vendor v JOIN {db}.item_template i ON i.entry = v.item
                                  UNION SELECT t.Entry, i.name FROM {db}.creature_template t
                                  JOIN {db}.npc_vendor_template v ON v.entry = t.VendorTemplateId
                                  JOIN {db}.item_template i ON i.entry = v.item"""):
            earlier_wares[(db, int(vendor))].add(name.lower())
    for vendor, item, item_name, vendor_name in q(
            f"""SELECT v.entry, v.item, i.name, t.name FROM {world}.npc_vendor v JOIN {world}.item_template i ON i.entry = v.item
                JOIN {world}.creature_template t ON t.entry = v.entry WHERE v.item > 0"""):
        vendor, item = int(vendor), int(item)
        era = item_era.get(item)
        if (era not in REQUIRED or (vendor, item) in vendor_gated or vendor not in creature_era
                or not seen_after['creature'].get(vendor, 0) & ((1 << REQUIRED[era]) - 1)):
            continue
        if any(item_name.lower() in earlier_wares[(db, vendor)] for db in earlier_dbs[era]):
            skipped['vendor:renumbered'].append((f'{ERA[era]} item {item} {item_name} at {vendor} {vendor_name}',
                                                 vendor, item, 'same item name at this vendor in an earlier database'))
        else:
            conditions.append((23, vendor, item, 0, MARKER[era]))
    return conditions, skipped


def wrap(values, indent='    ', width=110):
    lines, line = [], indent
    for index, value in enumerate(values):
        token = str(value) + (', ' if index < len(values) - 1 else '')
        if len(line) + len(token.rstrip()) > width:
            lines.append(line.rstrip())
            line = indent
        line += token
    return '\n'.join([*lines, line.rstrip()])


COLUMNS = ('(`SourceTypeOrReferenceId`, `SourceGroup`, `SourceEntry`, `SourceId`, `ElseGroup`, `ConditionTypeOrReference`, '
           '`ConditionTarget`, `ConditionValue1`, `ConditionValue2`, `ConditionValue3`, `NegativeCondition`, `ErrorType`, '
           '`ErrorTextId`, `ScriptName`, `Comment`)')
HEADER = '''-- Later-expansion world content stays out of reach until the character earns its
-- expansion: TBC content needs the rewarded TBC marker (66008), Wrath content the
-- Wrath marker (66013). Generated from the CMaNGOS world databases (classic-db
-- ec4f596, tbc-db ebe51a8, wotlk-db 78e8dc0): an entry absent from Classic arrived
-- with TBC, an entry absent from TBC too arrived with Wrath.
--
-- Creature and gameobject spawns on the old-world continents, and Wrath's in
-- Outland, get visibility conditions, which keep their AI and scripts. Quests and vendor items reachable before their expansion get
-- availability conditions on every existing alternative. Left alone: spawns of
-- modules and awareness scripts, invisible helpers, creatures that would attack
-- unseen, objects with collision or mechanics, objects of earlier quests, entries the
-- earlier database places at the same spot under another number, and quests or items
-- the earlier database knows by the same name.
DELETE FROM `conditions` WHERE `SourceTypeOrReferenceId` IN (19, 23, 30) AND `Comment` LIKE 'Era content: %';
'''


def render(conditions):
    out = [HEADER]
    for era in (1, 2):
        marker, name = MARKER[era], ERA[era]
        for group, table in ((0, 'creature'), (1, 'gameobject')):
            spawns = sorted((guid, entry) for source, g, entry, guid, m in conditions if source == 30 and g == group and m == marker)
            if spawns:
                where = 'the old-world continents and Outland' if era == 2 else 'the old-world continents'
                out += [f'-- {name} {table}s on {where}.',
                        (f'INSERT IGNORE INTO `conditions` {COLUMNS}\n'
                         f"SELECT 30, {group}, `id`, `guid`, 0, 8, 0, {marker}, 0, 0, 0, 0, 0, '', 'Era content: {name} {table}'\n"
                         f'FROM `{table}` WHERE `id` IN (\n{wrap(sorted({e for _, e in spawns}))}\n) AND `guid` IN (\n'
                         f'{wrap([g for g, _ in spawns])}\n);\n')]
        quests = sorted(entry for source, _, entry, _, m in conditions if source == 19 and m == marker)
        if quests:
            out += [f'-- {name} quests reachable earlier; every existing alternative keeps its own conditions.',
                    (f'INSERT IGNORE INTO `conditions` {COLUMNS}\n'
                     f'SELECT DISTINCT 19, 0, q.`ID`, 0, COALESCE(c.`ElseGroup`, 0), 8, 0, {marker}, 0, 0, 0, 0, 0, \'\', '
                     f"'Era content: {name} quest'\n"
                     'FROM `quest_template` q\n'
                     'LEFT JOIN `conditions` c ON c.`SourceTypeOrReferenceId` = 19 AND c.`SourceGroup` = 0 '
                     'AND c.`SourceEntry` = q.`ID` AND c.`SourceId` = 0\n'
                     f'WHERE q.`ID` IN (\n{wrap(quests)}\n);\n')]
        wares = defaultdict(list)
        for source, vendor, item, _, m in conditions:
            if source == 23 and m == marker:
                wares[vendor].append(item)
        if wares:
            clauses = '\n   OR '.join(f'(v.`entry` = {vendor} AND v.`item` IN ({", ".join(map(str, sorted(items)))}))'
                                      for vendor, items in sorted(wares.items()))
            out += [f'-- {name} items sold by vendors that are visible earlier.',
                    (f'INSERT IGNORE INTO `conditions` {COLUMNS}\n'
                     f"SELECT DISTINCT 23, v.`entry`, v.`item`, 0, 0, 8, 0, {marker}, 0, 0, 0, 0, 0, '', "
                     f"'Era content: {name} vendor item'\n"
                     f'FROM `npc_vendor` v\nWHERE {clauses};\n')]
    return '\n'.join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--ip', type=Path, required=True, help='Individual Progression checkout')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, help='JSON of the gates and of entries left alone, with reasons')
    parser.add_argument('--mysql', default='mysql', help='client command, for example "mysql --defaults-file=<file>"')
    for name, default in (('world', 'acore_world'), ('core-world', 'core_world'), ('classic', 'cm_classic'),
                          ('tbc', 'cm_tbc'), ('wotlk', 'cm_wotlk')):
        parser.add_argument(f'--{name}', default=default)
    args = parser.parse_args()
    conditions, skipped = generate(Database(args.mysql), args)
    args.output.write_text(render(conditions))
    if args.report:
        args.report.write_text(json.dumps({'conditions': conditions, 'skipped': skipped}, ensure_ascii=False, indent=0))
    counts = Counter((source, marker) for source, *_, marker in conditions)
    print(', '.join(f'{count} {kind} {ERA[1 if marker == 66008 else 2]}' for (source, marker), count in sorted(counts.items())
                    for kind in [{19: 'quests', 23: 'vendor items', 30: 'spawns'}[source]]))


if __name__ == '__main__':
    main()
