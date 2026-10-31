#!/usr/bin/env python3
"""Generate Individual Progression's era gates for world content of later expansions and patches.

  python3 scripts/generate_era_world_content.py --ip <checkout> --output <file> [--report <json>] \\
      [--mysql "mysql --defaults-file=<file>"] [--world acore_world] [--core-world core_world] \\
      [--classic cm_classic] [--tbc cm_tbc] [--wotlk cm_wotlk] [--vmangos vm_world] [--chromiecraft <checkout>]

The MySQL server holds the realm's world database after every core and module update
except this file's own rows, the same world built from the core alone, and the CMaNGOS
classic-db, tbc-db and wotlk-db revisions pinned in versions.lock.json, each loaded from
Full_DB with its Updates directory. An entry absent from Classic arrived with TBC (tier 8);
an entry absent from TBC too arrived with Wrath (tier 13). The VMaNGOS world database
(the pinned dump with every migration of the pinned core) dates Vanilla content to its
patch, and the pinned ChromieCraft progression system's brackets date TBC and Wrath phases.
Each patch opens with the tier of its raid: PATCH_STAGE and BRACKET_STAGE below.

Spawns on the old-world continents, and a later tier's in Outland or Northrend, that a
character sees before their tier get visibility conditions, which keep AI and scripts.
Quests reachable before their tier and items of vendors visible earlier get availability
conditions on the rewarded milestone marker. A quest only awareness-scripted givers offer opens
and closes with their fixed stage rule, so a shared quest, and Questie's map through the
Questie bridge, follow the giver. Spawns are left alone when a module added or
changed them, an awareness script decides, they are invisible helpers or spirit healers,
they keep collision or traps, earlier quests use them or their quest-item drops,
or the earlier database places the same name there; quests and items the earlier database
knows by the same name are left alone too, and Vanilla patches leave Classic battlegrounds,
holidays and Individual Progression's own placements alone. Write the output into the
Individual Progression fork's data/sql/world/updates/zz_2026_10_31_01_era_world_content.sql
and commit it there.
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
# IP stage at which each Vanilla patch's content opens, by VMaNGOS patch (0 = 1.2 ... 10 = 1.12): with the raid
# or event of the patch. 1.6 Blackwing Lair; 1.7 Zul'Gurub, 1.8 the Dragons of Nightmare and 1.10's second dungeon
# set after Nefarian; 1.9 the Ahn'Qiraj gates; 1.11 and 1.12 Naxxramas and the Scourge.
PATCH_STAGE = (0, 0, 0, 0, 1, 3, 3, 4, 3, 6, 6)
# ChromieCraft's progression brackets in order, and the IP stage of the raid of each bracket's original patch for
# its TBC and Wrath content: 2.0 Karazhan, Serpentshrine and Tempest Keep; 2.1 Hyjal, the Black Temple, Ogri'la,
# the Skyguard and the Netherwing; 2.3 Zul'Aman; 2.4 the Sunwell; 3.1 Ulduar; 3.2 the Crusader; 3.3 Icecrown;
# 3.3.5 the Ruby Sanctum. Stage 11 is reserved.
BRACKETS = ('Bracket_0', 'Bracket_1_19', 'Bracket_20_29', 'Bracket_30_39', 'Bracket_40_49', 'Bracket_50_59_1',
            'Bracket_50_59_2', 'Bracket_60_1_1', 'Bracket_60_1_2', 'Bracket_60_2_1', 'Bracket_60_2_2', 'Bracket_60_3_1',
            'Bracket_60_3_2', 'Bracket_60_3_3', 'Bracket_61_64', 'Bracket_65_69', 'Bracket_70_1_1', 'Bracket_70_1_2',
            'Bracket_70_2_1', 'Bracket_70_2_2', 'Bracket_70_2_3', 'Bracket_70_3_1', 'Bracket_70_3_2', 'Bracket_70_4_1',
            'Bracket_70_4_2', 'Bracket_70_5', 'Bracket_70_6_1', 'Bracket_70_6_2', 'Bracket_70_6_3', 'Bracket_71_74',
            'Bracket_75_79', 'Bracket_80_1_1', 'Bracket_80_1_2', 'Bracket_80_1_3', 'Bracket_80_2', 'Bracket_80_3',
            'Bracket_80_4_1', 'Bracket_80_4_2')
BRACKET_STAGE = {'Bracket_61_64': 8, 'Bracket_65_69': 8, 'Bracket_70_1_1': 8, 'Bracket_70_1_2': 8, 'Bracket_70_2_1': 9,
                 'Bracket_70_2_2': 9, 'Bracket_70_2_3': 10, 'Bracket_70_3_1': 10, 'Bracket_70_3_2': 10, 'Bracket_70_4_1': 10,
                 'Bracket_70_4_2': 10, 'Bracket_70_5': 12, 'Bracket_70_6_1': 12, 'Bracket_70_6_2': 12, 'Bracket_70_6_3': 12,
                 'Bracket_71_74': 13, 'Bracket_75_79': 13, 'Bracket_80_1_1': 13, 'Bracket_80_1_2': 13, 'Bracket_80_1_3': 13,
                 'Bracket_80_2': 14, 'Bracket_80_3': 15, 'Bracket_80_4_1': 16, 'Bracket_80_4_2': 17}
# Spirit healers and guides serve the graveyards of every era; battlemasters queue Classic battlegrounds by level.
GRAVEYARD_FLAGS = 0x4000 | 0x8000
BATTLEMASTER_FLAG = 0x100000
# Classic battlegrounds open with their level, not their patch: quest zones and reputations of Warsong, Arathi and Alterac.
BATTLEGROUND_SORTS = {-25, 2597, 3277, 3358}
BATTLEGROUND_FACTIONS = {509, 510, 729, 730, 889, 890}
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


def awareness_rules(ip, configured=None):
    """Stage masks of the awareness scripts' CanBeSeen decisions; None where the decision is not a stage rule.

    Scripts whose stages follow a configuration option are added to configured.
    """
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
            if configured is not None and re.search(r'sIndividualProgression->(?:Required\w+|\w+ArenaSeason|earlyDungeonSet2)',
                                                    seen.group(1)):
                configured.add(name)
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


def stage_name(stage):
    return 'Vanilla' if stage < 8 else 'TBC' if stage < 13 else 'Wrath'


def chromiecraft_openings(root):
    """Stage at which ChromieCraft's progression brackets open TBC and Wrath quests and spawns.

    Quests come from the brackets' quest disables, spawns from their phase-mask hides; each opens with the
    bracket that removes the disable or shows the spawn again.
    """
    quests, spawns = {}, {}
    hidden_quests, hidden_spawns = {}, {}
    for bracket in BRACKETS:
        for path in sorted((root / 'src' / bracket).rglob('*.sql')):
            text = re.sub(r'--[^\n]*', '', path.read_text(errors='replace'))
            for statement in (' '.join(part.split()) for part in text.split(';')):
                lower = statement.lower()
                if lower.startswith('delete from `disables`') and ('sourcetype' not in lower or
                                                                   re.search(r'sourcetype`?\s*=\s*1\b', lower)):
                    for group in re.findall(r'entry`?\s*(?:in\s*\(([^)]*)\)|=\s*(\d+))', lower):
                        for entry in map(int, re.findall(r'\d+', ' '.join(group))):
                            if entry in hidden_quests:
                                del hidden_quests[entry]
                                quests[entry] = bracket
                elif lower.startswith('insert into `disables`'):
                    columns = [c.strip(' `') for c in re.search(r'\(([^)]*)\)\s*values', lower).group(1).split(',')]
                    for row in re.findall(r'\(([^()]*)\)', statement[lower.index('values'):]):
                        record = dict(zip(columns, (v.strip(" '\"") for v in row.split(','))))
                        if record.get('sourcetype') == '1':
                            hidden_quests[int(record['entry'])] = bracket
                            quests.pop(int(record['entry']), None)
                elif match := re.match(r'update `(creature|gameobject)` set `phasemask`\s*=\s*(\d+) where (.*)', lower):
                    kind, phase, where = match.groups()
                    ids = re.search(r'`id`\s*(?:in\s*\(([^)]*)\)|=\s*(\d+))', where)
                    guids = re.search(r'`guid`\s*(?:in\s*\(([^)]*)\)|=\s*(\d+))', where)
                    entries = [int(e) for e in re.findall(r'\d+', ' '.join(ids.groups(''))) ] if ids else [0]
                    spots = [int(g) for g in re.findall(r'\d+', ' '.join(guids.groups('')))] if guids else [0]
                    for key in ((kind, entry, guid) for entry in entries for guid in spots):
                        if phase != '1':
                            hidden_spawns[key] = bracket
                            spawns.pop(key, None)
                        elif key in hidden_spawns:
                            del hidden_spawns[key]
                            spawns[key] = bracket
    return ({quest: BRACKET_STAGE[bracket] for quest, bracket in quests.items() if bracket in BRACKET_STAGE},
            {key: BRACKET_STAGE[bracket] for key, bracket in spawns.items() if bracket in BRACKET_STAGE})


def generate(q, args):
    configured = set()
    rules = awareness_rules(args.ip, configured)
    world, earlier_dbs = args.world, {1: (args.classic,), 2: (args.classic, args.tbc)}

    def eras(table, key):
        result = {}
        for era, db in ((2, args.wotlk), (1, args.tbc), (0, args.classic)):
            result.update((int(entry), era) for (entry,) in q(f'SELECT {key} FROM {db}.{table}'))
        return result

    creature_era, gameobject_era = eras('creature_template', 'Entry'), eras('gameobject_template', 'entry')
    quest_era, item_era = eras('quest_template', 'entry'), eras('item_template', 'entry')
    phase_quests, phase_spawns = chromiecraft_openings(args.chromiecraft) if args.chromiecraft else ({}, {})

    # Vanilla patches from VMaNGOS: the first patch of each entry, and of each spawn found at the same spot.
    patch_of, patch_spawns = defaultdict(dict), {}
    if args.vmangos:
        for kind, table in (('creature', 'creature_template'), ('gameobject', 'gameobject_template'),
                            ('quest', 'quest_template'), ('item', 'item_template')):
            patch_of[kind] = {int(e): int(p) for e, p in q(f'SELECT entry, MIN(patch) FROM {args.vmangos}.{table} GROUP BY entry')}
        for kind in ('creature', 'gameobject'):
            index = defaultdict(list)
            for entry, map_id, x, y, first in q(f'SELECT id, map, position_x, position_y, patch_min FROM {args.vmangos}.{kind}'):
                index[(int(entry), int(map_id))].append((float(x), float(y), int(first)))
            patch_spawns[kind] = index

    def vanilla_stage(kind, entry, map_id=None, x=0.0, y=0.0):
        patch = patch_of[kind].get(entry)
        if patch is None:
            return 0
        if map_id is not None:
            near = [first for px, py, first in patch_spawns[kind].get((entry, map_id), ())
                    if (px - x) ** 2 + (py - y) ** 2 <= 30 ** 2]
            if near:
                patch = max(patch, min(near))
        return PATCH_STAGE[min(patch, len(PATCH_STAGE) - 1)]

    def quest_need(quest):
        era = quest_era.get(quest)
        if era is None:
            return 0
        return max(REQUIRED.get(era, 0), phase_quests.get(quest, 0), vanilla_stage('quest', quest) if era == 0 else 0)

    visibility_gated = {(int(g), int(e)) for g, e in q(
        f'SELECT SourceGroup, SourceEntry FROM {world}.conditions WHERE SourceTypeOrReferenceId = 30 AND {OWN}')}
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
    # Quests that need a quest item a creature or chest drops use that creature or chest too.
    quest_items = {int(i) for (i,) in q(f'SELECT entry FROM {world}.item_template WHERE class = 12 OR bonding = 4')}
    needs_item = defaultdict(set)
    for quest, *items in q(f'SELECT ID, RequiredItemId1, RequiredItemId2, RequiredItemId3, RequiredItemId4, RequiredItemId5, '
                           f'RequiredItemId6, ItemDrop1, ItemDrop2, ItemDrop3, ItemDrop4 FROM {world}.quest_template'):
        for item in map(int, items):
            if item in quest_items:
                needs_item[item].add(int(quest))
    drops = (('creature', (f'SELECT t.entry, l.Item FROM {world}.creature_template t JOIN {world}.creature_loot_template l '
                           f'ON l.Entry = t.lootid WHERE t.lootid > 0 AND l.Reference = 0')),
             ('gameobject', (f'SELECT t.entry, l.Item FROM {world}.gameobject_template t JOIN {world}.gameobject_loot_template l '
                             f'ON l.Entry = t.Data1 WHERE t.type = 3 AND t.Data1 > 0 AND l.Reference = 0')))
    for kind, sql in drops:
        for entry, item in q(sql):
            objective[(kind, int(entry))] |= needs_item.get(int(item), set())
    disabled = {int(e) for (e,) in q(f'SELECT entry FROM {world}.disables WHERE sourceType = 1')}
    factions = ','.join(map(str, sorted(BATTLEGROUND_FACTIONS)))
    battleground_items = {int(i) for (i,) in q(f'SELECT entry FROM {world}.item_template WHERE RequiredReputationFaction IN ({factions})')}
    battleground_vendors = {int(v) for (v,) in q(f'SELECT DISTINCT v.entry FROM {world}.npc_vendor v JOIN {world}.item_template i '
                                                 f'ON i.entry = v.item WHERE i.RequiredReputationFaction IN ({factions})')}

    conditions, skipped = [], defaultdict(list)
    seen_before = {'creature': defaultdict(int), 'gameobject': defaultdict(int)}
    seen_after = {'creature': defaultdict(int), 'gameobject': defaultdict(int)}
    scripted = {'creature': set(), 'gameobject': set()}
    awareness = {'creature': {}, 'gameobject': {}}
    spawns = []
    for kind, group in (('creature', 0), ('gameobject', 1)):
        template = 't.flags_extra, t.npcflag, 0' if kind == 'creature' else '0, 0, t.type'
        events = {int(g) for (g,) in q(f'SELECT DISTINCT guid FROM {world}.game_event_{kind}')}
        for guid, entry, map_id, phase, script, name, x, y, extra, npcflag, kind_type in q(
                f"""SELECT s.guid, s.id, s.map, s.phaseMask, COALESCE(NULLIF(s.ScriptName, ''), t.ScriptName), t.name,
                    s.position_x, s.position_y, {template}
                    FROM {world}.{kind} s JOIN {world}.{kind}_template t ON t.entry = s.id"""):
            guid, entry, map_id, x, y = int(guid), int(entry), int(map_id), float(x), float(y)
            if guid in events:
                continue
            if script in rules:
                scripted[kind].add(entry)
            rule = rules.get(script)
            mask = (map_mask(map_id) if int(phase) & 1 else 0) & (ALL if rule is None else rule)
            seen_before[kind][entry] |= mask
            # The stages an entry's spawns are visible at by fixed awareness rules alone.
            fixed = rule if script in rules and rule is not None and script not in configured else ALL
            awareness[kind][entry] = awareness[kind].get(entry, 0) | fixed
            spawns.append((kind, group, guid, entry, map_id, script, name, x, y, int(extra), int(npcflag), int(kind_type), mask))

    def first(mask):
        return next((stage for stage in STAGES if mask >> stage & 1), 0)

    # Quests: the tier each opens at, then the chain rule. A quest never opens later than one that builds on it,
    # including the milestone quests Individual Progression places itself.
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
    givers = defaultdict(set)
    for (kind, entry), quests in starts.items():
        for quest in quests:
            reachable[quest] |= seen_before[kind].get(entry, 0)
            givers[quest].add((kind, entry))
    opens, candidates, titles, audiences = {}, {}, {}, {}
    for quest, title, sort, races, classes in q(
            f"""SELECT q.ID, q.LogTitle, q.QuestSortID, q.AllowableRaces, COALESCE(a.AllowableClasses, 0)
                FROM {world}.quest_template q LEFT JOIN {world}.quest_template_addon a ON a.ID = q.ID"""):
        quest, sort, races, classes = int(quest), int(sort), int(races), int(classes)
        titles[quest] = title
        era, need = quest_era.get(quest), quest_need(quest)
        mask = reachable[quest]
        if quest in item_started:
            mask |= zone_mask.get(sort, ALL if sort < 0 and sort not in HOLIDAY_SORTS else 0)
        # Blood elves and draenei start at tier 8, death knights at tier 13.
        audience = 8 if races and not races & ~(512 | 1024) else 13 if classes == 32 else 0
        # A quest no giver or item offers is started by a script; it opens with its own tier.
        opens[quest] = max(first(mask) if mask else need, gated[quest] - 66000 if gated[quest] else 0, audience)
        audiences[quest] = audience
        if not need or quest in disabled or gated[quest] >= 66000 + need or not mask & ((1 << need) - 1):
            continue
        own_era = need == REQUIRED.get(era)
        reason = None
        if quest in holiday or sort in HOLIDAY_SORTS:
            reason = 'holiday', 'holiday quest'
        elif need < 8 and sort in BATTLEGROUND_SORTS:
            reason = 'battleground', 'battleground quest'
        elif need < 8 and (gated[quest] or (givers[quest] and all(entry in scripted[kind] for kind, entry in givers[quest]))):
            reason = 'script', 'Individual Progression already places it'
        elif era == 1 and races and not races & ~(512 | 1024):
            reason = 'race', 'blood elf or draenei quest'
        elif classes == 32:
            reason = 'class', 'death knight quest'
        elif own_era and any(title.strip().lower() in earlier_titles[db] for db in earlier_dbs[era]):
            reason = 'renumbered', 'same title in an earlier database'
        if reason:
            skipped[f'quest:{reason[0]}'].append((f'{stage_name(need)} quest {quest} {title}', quest, sort, reason[1]))
        else:
            candidates[quest] = need
            opens[quest] = need
    # Milestone quests are rewarded to earn the next tier, so their chains must open a tier earlier.
    header = (args.ip / 'src/IndividualProgression.h').read_text()
    placed = {int(re.search(rf'\b{name}\s*=\s*(\d+)', header).group(1)): stage
              for name, stage in (('BANG_A_GONG', 3), ('INTO_THE_BREACH', 7))}
    # Quests Individual Progression places itself open at the tier it chose.
    for quest in reachable:
        if gated[quest] or (givers[quest] and all(entry in scripted[kind] for kind, entry in givers[quest])):
            placed.setdefault(quest, opens[quest])
    previous = defaultdict(set)
    for quest, after in followers.items():
        for follower in after:
            previous[follower].add(quest)
    changed = True
    while changed:
        # The tier by which each quest must be available: no later than any placed or gated quest after it.
        limit, pending = {}, []
        for quest in set(placed) | set(candidates):
            limit[quest] = min(placed.get(quest, 99), candidates.get(quest, 99))
            pending.append(quest)
        while pending:
            quest = pending.pop()
            for before in previous[quest]:
                if limit[quest] < limit.get(before, 99):
                    limit[before] = limit[quest]
                    pending.append(before)
        changed = False
        for quest, need in list(candidates.items()):
            bound = min((limit.get(f, 99) for f in followers[quest] if f not in disabled), default=99)
            if bound < need:
                del candidates[quest]
                skipped['quest:chain'].append((f'{stage_name(need)} quest {quest} {titles[quest]}', quest, 0,
                                               f'a quest after it opens at tier {bound}'))
                changed = True
    for quest in list(opens):
        if quest not in candidates and quest not in placed:
            opens[quest] = max(first(reachable[quest]) if reachable[quest] else quest_need(quest), audiences.get(quest, 0))
    conditions += [(19, 0, quest, 0, 66000 + need) for quest, need in sorted(candidates.items())]

    # Quests only awareness-scripted givers offer open and close with those givers, so a shared quest or
    # one read from the client's own data follows the giver's fixed rule too. Stage 11 has no marker.
    def marker(stage):
        return 66000 + (12 if stage == 11 else stage)

    gated_quests = {c[2]: c[4] for c in conditions if c[0] == 19}
    for quest in sorted(givers):
        if quest in item_started or quest in disabled or quest in holiday:
            continue
        stages = 0
        for kind, entry in givers[quest]:
            stages |= awareness[kind].get(entry, ALL)
        if stages in (0, ALL):
            continue
        visible = [stage for stage in STAGES if stages >> stage & 1]
        if visible != list(range(visible[0], visible[-1] + 1)):
            skipped['quest:awareness'].append((f'quest {quest} {titles[quest]}', quest, 0, 'givers visible at separate tiers'))
            continue
        first_stage, last_stage = visible[0], visible[-1]
        if first_stage and marker(first_stage) > gated_quests.get(quest, 0) and marker(first_stage) > gated[quest]:
            conditions.append((19, 0, quest, 0, marker(first_stage)))
        if last_stage < STAGES[-1]:
            conditions.append((19, 0, quest, 0, -marker(last_stage + 1)))

    for kind, group, guid, entry, map_id, script, name, x, y, extra, npcflag, kind_type, mask in spawns:
        era = (creature_era if kind == 'creature' else gameobject_era).get(entry)
        need = max(REQUIRED.get(era, 0), phase_spawns.get((kind, entry, guid), 0), phase_spawns.get((kind, entry, 0), 0),
                   phase_spawns.get((kind, 0, guid), 0), vanilla_stage(kind, entry, map_id, x, y) if era == 0 else 0)
        # Gates cover the old-world continents, and a later tier's spawns in Outland or Northrend.
        where = map_id in (0, 1) or (map_id == 530 and need > 8) or (map_id == 571 and need > 13)
        if era is not None and need and where and mask & ((1 << need) - 1):
            earlier = sorted(quest for quest in starts[(kind, entry)] | ends[(kind, entry)] | objective[(kind, entry)]
                             if quest not in disabled and quest in opens and opens[quest] < need)
            reason = None
            if (guid, entry) not in core_spawns[kind]:
                reason = 'module', 'a module added or changed the spawn'
            elif script in rules:
                reason = 'script', 'an awareness script decides'
            elif (group, entry) in visibility_gated:
                reason = 'condition', 'an existing visibility condition decides'
            elif kind == 'creature' and (extra & 128 or HELPER.search(name)):
                reason = 'helper', 'invisible helper'
            elif kind == 'creature' and npcflag & GRAVEYARD_FLAGS:
                reason = 'graveyard', 'spirit healer or guide'
            elif need < 8 and kind == 'creature' and (npcflag & BATTLEMASTER_FLAG or entry in battleground_vendors):
                reason = 'battleground', 'battlemaster or battleground reputation vendor'
            elif kind == 'gameobject' and kind_type not in GAMEOBJECT_TYPES:
                reason = 'mechanics', f'type {kind_type} keeps collision or mechanics'
            elif earlier:
                reason = 'quest', 'earlier quests ' + ','.join(map(str, earlier[:6]))
            elif need == REQUIRED.get(era) and (source := renumbered(era, ('go:' + name) if kind == 'gameobject' else name,
                                                                      map_id, round(x), round(y))):
                reason = 'renumbered', f'same name here in {source}'
            if reason:
                skipped[f'{kind}:{reason[0]}'].append((f'{stage_name(need)} {kind} {entry} {name}', guid, map_id, reason[1]))
            else:
                conditions.append((30, group, entry, guid, 66000 + need))
                mask &= ~((1 << need) - 1)
        seen_after[kind][entry] |= mask

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
        need = REQUIRED.get(era, 0) or (vanilla_stage('item', item) if era == 0 else 0)
        if (not need or (vendor, item) in vendor_gated or vendor not in creature_era
                or (need < 8 and (vendor in scripted['creature'] or item in battleground_items))
                or not seen_after['creature'].get(vendor, 0) & ((1 << need) - 1)):
            continue
        if era in REQUIRED and any(item_name.lower() in earlier_wares[(db, vendor)] for db in earlier_dbs[era]):
            skipped['vendor:renumbered'].append((f'{ERA[era]} item {item} {item_name} at {vendor} {vendor_name}',
                                                 vendor, item, 'same item name at this vendor in an earlier database'))
        else:
            conditions.append((23, vendor, item, 0, 66000 + need))
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
HEADER = '''-- World content of later expansions and patches stays out of reach until the character
-- earns the milestone of its tier: TBC content needs the rewarded marker of tier 8 (66008),
-- Wrath content tier 13 (66013), and each patch the tier of its raid. Generated from the
-- CMaNGOS world databases (classic-db ec4f596, tbc-db ebe51a8, wotlk-db 78e8dc0): an entry
-- absent from Classic arrived with TBC, an entry absent from TBC too arrived with Wrath.
-- VMaNGOS (core 9b7fb4d, world dump of 14 June 2021) dates Vanilla content to its patch:
-- 1.6 opens with tier 1, 1.7, 1.8 and 1.10 with tier 3, 1.9 with tier 4, 1.11 and 1.12
-- with tier 6. ChromieCraft's progression brackets (9235693) date TBC and Wrath phases:
-- 2.1 with tier 10, 2.3 and 2.4 with 12, 3.1 with 14, 3.2 with 15, 3.3 with 16, 3.3.5 with 17.
--
-- A quest only awareness-scripted givers offer opens and closes with their fixed stage
-- rule, so a shared quest, and Questie's map through the Questie bridge, follow the giver.
--
-- Spawns on the old-world continents, and a later tier's in Outland or Northrend, get
-- visibility conditions, which keep their AI and scripts; a hidden creature does not
-- perceive the character either, so it neither shows nor engages. Quests and vendor
-- items reachable before their tier get availability conditions on every existing
-- alternative. Left alone: spawns of modules and awareness scripts, invisible helpers,
-- spirit healers, objects with collision or mechanics, creatures and objects that
-- earlier quests use or that drop their quest items, entries the earlier database
-- places at the same spot under another number, quests or items the earlier database
-- knows by the same name, and for Vanilla patches Classic battlegrounds, holidays and
-- Individual Progression's own placements.
DELETE FROM `conditions` WHERE `SourceTypeOrReferenceId` IN (19, 23, 30) AND `Comment` LIKE 'Era content: %';
'''


def render(conditions):
    out = [HEADER]
    for marker in sorted({c[4] for c in conditions if c[4] > 0}):
        stage = marker - 66000
        name = stage_name(stage)
        for group, table in ((0, 'creature'), (1, 'gameobject')):
            spawns = sorted((guid, entry) for source, g, entry, guid, m in conditions if source == 30 and g == group and m == marker)
            if spawns:
                out += [f'-- {name} {table}s opening at tier {stage}.',
                        (f'INSERT IGNORE INTO `conditions` {COLUMNS}\n'
                         f"SELECT 30, {group}, `id`, `guid`, 0, 8, 0, {marker}, 0, 0, 0, 0, 0, '', 'Era content: {name} {table}'\n"
                         f'FROM `{table}` WHERE `id` IN (\n{wrap(sorted({e for _, e in spawns}))}\n) AND `guid` IN (\n'
                         f'{wrap([g for g, _ in spawns])}\n);\n')]
        quests = sorted(entry for source, _, entry, _, m in conditions if source == 19 and m == marker)
        if quests:
            out += [f'-- {name} quests opening at tier {stage}; every existing alternative keeps its own conditions.',
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
            out += [f'-- {name} items opening at tier {stage}, sold by vendors that are visible earlier.',
                    (f'INSERT IGNORE INTO `conditions` {COLUMNS}\n'
                     f"SELECT DISTINCT 23, v.`entry`, v.`item`, 0, 0, 8, 0, {marker}, 0, 0, 0, 0, 0, '', "
                     f"'Era content: {name} vendor item'\n"
                     f'FROM `npc_vendor` v\nWHERE {clauses};\n')]
    for marker in sorted({-c[4] for c in conditions if c[4] < 0}):
        stage = marker - 66000
        name = stage_name(stage - 1)
        quests = sorted(entry for source, _, entry, _, m in conditions if source == 19 and m == -marker)
        out += [f'-- {name} quests closing at tier {stage} with their awareness-scripted givers.',
                (f'INSERT IGNORE INTO `conditions` {COLUMNS}\n'
                 f'SELECT DISTINCT 19, 0, q.`ID`, 0, COALESCE(c.`ElseGroup`, 0), 8, 0, {marker}, 0, 0, 1, 0, 0, \'\', '
                 f"'Era content: {name} quest'\n"
                 'FROM `quest_template` q\n'
                 'LEFT JOIN `conditions` c ON c.`SourceTypeOrReferenceId` = 19 AND c.`SourceGroup` = 0 '
                 'AND c.`SourceEntry` = q.`ID` AND c.`SourceId` = 0\n'
                 f'WHERE q.`ID` IN (\n{wrap(quests)}\n);\n')]
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
    parser.add_argument('--vmangos', help='VMaNGOS world database for the patches of Vanilla content')
    parser.add_argument('--chromiecraft', type=Path, help='mod-progression-system checkout for TBC and Wrath phases')
    args = parser.parse_args()
    conditions, skipped = generate(Database(args.mysql), args)
    args.output.write_text(render(conditions))
    if args.report:
        args.report.write_text(json.dumps({'conditions': conditions, 'skipped': skipped}, ensure_ascii=False, indent=0))
    counts = Counter((source, marker) for source, *_, marker in conditions)
    print(', '.join(f'{count} {kind} ' + (f'at tier {marker - 66000}' if marker > 0 else f'closing at tier {-marker - 66000}')
                    for (source, marker), count in sorted(counts.items())
                    for kind in [{19: 'quests', 23: 'vendor items', 30: 'spawns'}[source]]))


if __name__ == '__main__':
    main()
