"""Replay the era world-content gates on the pinned world and check historical anchors.

Individual Progression hides spawns, quests and vendor items of a later expansion or patch
until the character has rewarded the milestone marker of its tier. The update replays twice
on scoped copies of the pinned base world; conditions are then evaluated the way the native
visibility, quest and vendor checks read them. Anchors are Wrath's Inscription trainers in
Azeroth and Outland, barbers and Light Parchment, TBC's 2.3 Dustwallow Marsh, guild vaults
and jewelcrafting designs, Blackwing Lair's, Ahn'Qiraj's and Naxxramas's Vanilla quests,
the 2.1 Netherwing and the 3.2 Crusader, and Vanilla content and Classic battlegrounds that
stay put. Hostile creatures are gated too:
TestMutualVisibility keeps a hidden creature from perceiving the character. Mutations weaken or drop
single gates.
"""

import argparse
from collections import defaultdict
import re
import sqlite3

from FixtureSupport import (
    function,
    prepared_core,
    source_argument,
    sql_rows,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, 'core', default=prepared_core())
source_argument(parser, 'ip')
args = parser.parse_args()
core = args.core
ip = args.ip or core / 'modules/mod-individual-progression'
update = (ip / 'data/sql/world/updates/zz_2026_10_31_01_era_world_content.sql').read_text()
TBC, WRATH = 66008, 66013

# Native contracts: spawn-level visibility conditions take precedence over entry-level
# ones and are checked for every player sight of a creature or gameobject; quest and
# vendor conditions gate taking a quest, listing and buying an item. A rewarded-quest
# condition reads the player passed first.
header = (core / 'src/server/game/Conditions/ConditionMgr.h').read_text()
for name, value in (('CONDITION_SOURCE_TYPE_QUEST_AVAILABLE', 19), ('CONDITION_SOURCE_TYPE_NPC_VENDOR', 23),
                    ('CONDITION_SOURCE_TYPE_OBJECT_VISIBILITY', 30), ('CONDITION_QUESTREWARDED', 8)):
    assert re.search(rf'\b{name}\s*= {value},', header), name
conditions_source = (core / 'src/server/game/Conditions/ConditionMgr.cpp').read_text()
lookup = function(conditions_source, 'ConditionList ConditionMgr::GetConditionsForObjectVisibility(WorldObject const* object) const')
assert lookup.index('sourceIdConditions.find(guid)') < lookup.index('sourceIdConditions.find(0)')
assert 'condMeets = player->GetQuestRewardStatus(ConditionValue1);' in conditions_source
objects = (core / 'src/server/game/Entities/Object/Object.cpp').read_text()
sight = function(objects, 'bool WorldObject::CanSeeOrDetect(')
assert 'viewer && HiddenFrom(obj, viewer)' in sight and 'viewed && HiddenFrom(this, viewed)' in sight
assert function(objects, 'bool HiddenFrom(WorldObject const* object, Player const* player)').count(
    '!player->CanSeeObjectByVisibilityConditions(object)') == 2
player_source = (core / 'src/server/game/Entities/Player/Player.cpp').read_text()
visibility = function(player_source, 'bool Player::CanSeeObjectByVisibilityConditions(WorldObject const* object) const')
assert 'ConditionSourceInfo(const_cast<Player*>(this), const_cast<WorldObject*>(object))' in visibility
buy = function(player_source, 'bool Player::BuyItemFromVendorSlot(')
assert 'GetConditionsForNpcVendorEvent(creature->GetEntry(), item)' in buy
quest_source = (core / 'src/server/game/Entities/Player/PlayerQuest.cpp').read_text()
assert 'CONDITION_SOURCE_TYPE_QUEST_AVAILABLE' in function(quest_source, 'bool Player::SatisfyQuestConditions(')
# Markers accumulate: every stage up to the current one stays rewarded.
progression = (ip / 'src/IndividualProgression.cpp').read_text()
assert 'for (uint8 i = currentState; i <= newState; ++i)' in function(
    progression, 'void IndividualProgression::UpdateProgressionState(')
markers = (ip / 'data/sql/world/base/player_progression.sql').read_text()
assert all(re.search(rf'^\({marker},', markers, re.MULTILINE) for marker in range(66001, 66019))
# Stage 11 is not an implemented milestone, so no gate waits for its marker.
assert 'current == 10 ? 12 : current + 1' in (ip / 'src/StrictEarnedProgressionPolicy.h').read_text()

# Every row is a rewarded-marker gate the update can find and remove again.
INSERTS = re.findall(r"INSERT IGNORE INTO `conditions` \([^)]*\)\nSELECT (?:DISTINCT )?(\d+), [^;]*?, 8, 0, (\d+), 0, 0, 0, 0, 0, '', "
                     r"'Era content: (Vanilla|TBC|Wrath) (creature|gameobject|quest|vendor item)'", update)
assert len(INSERTS) == update.count('INSERT'), 'every insert is a marker gate'
ERAS = {'Vanilla': range(66001, 66008), 'TBC': (66008, 66009, 66010, 66012), 'Wrath': range(66013, 66019)}
assert all(int(marker) in ERAS[era] for _, marker, era, _ in INSERTS), 'each gate waits for a milestone of its era'
assert update.count("DELETE FROM `conditions` WHERE `SourceTypeOrReferenceId` IN (19, 23, 30) AND `Comment` LIKE 'Era content: %';") == 1
numbers = {int(value) for value in re.findall(r'\b\d+\b', update)}
world = core / 'data/sql/base/db_world'


def rows(table, keys):
    return sql_rows(core, table, keys)


# Scoped copies of the pinned base world: the spawns, quests and vendor lists the update names.
creatures = [(int(r['guid']), int(r['id1']), int(r['map'])) for r in rows('creature', numbers)]
gameobjects = [(int(r['guid']), int(r['id']), int(r['map'])) for r in rows('gameobject', numbers)]
quests = [(int(r['ID']),) for r in rows('quest_template', numbers)]
vendors = [(int(r['entry']), int(r['item'])) for r in rows('npc_vendor', numbers)]
existing = [tuple(r.values()) for r in rows('conditions', {19, 23, 30})]
columns = next(iter(rows('conditions', {19}))).keys()
creature_flags = {int(r['entry']): (int(r['flags_extra']), int(r['npcflag']))
                  for r in rows('creature_template', {e for _, e, _ in creatures})}
gameobject_types = {int(r['entry']): int(r['type']) for r in rows('gameobject_template', {e for _, e, _ in gameobjects})}
# Milestone quests are rewarded to earn the next tier, so they and every quest before them in their chain must be
# available one tier earlier: Bang a Gong! earns tier 4 and Into the Breach tier 8.
header_ip = (ip / 'src/IndividualProgression.h').read_text()
milestones = {int(re.search(rf'{name}\s*=\s*(\d+)', header_ip).group(1)): stage
              for name, stage in (('BANG_A_GONG', 3), ('INTO_THE_BREACH', 7))}
before = defaultdict(set)
for r in rows('quest_template_addon', set(range(1, 30000))):
    if int(r['PrevQuestID']) > 0:
        before[int(r['ID'])].add(int(r['PrevQuestID']))
    if int(r['NextQuestID']) > 0:
        before[int(r['NextQuestID'])].add(int(r['ID']))
needed = {}
for milestone, stage in milestones.items():
    pending = [milestone]
    while pending:
        quest = pending.pop()
        if needed.get(quest, 99) > stage:
            needed[quest] = stage
            pending += before[quest]
assert len(needed) > 20, 'the Scepter of the Shifting Sands chain precedes Bang a Gong!'


def replay(source):
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE `creature` (`guid` INTEGER PRIMARY KEY, `id` INTEGER, `map` INTEGER)')
    db.execute('CREATE TABLE `gameobject` (`guid` INTEGER PRIMARY KEY, `id` INTEGER, `map` INTEGER)')
    db.execute('CREATE TABLE `quest_template` (`ID` INTEGER PRIMARY KEY)')
    db.execute('CREATE TABLE `npc_vendor` (`entry` INTEGER, `item` INTEGER, PRIMARY KEY (`entry`, `item`))')
    # Integer affinity compares the dump's numeric text like the native columns.
    db.execute('CREATE TABLE `conditions` (' + ','.join(f'`{c}`' + ('' if c in ('ScriptName', 'Comment') else ' INTEGER')
                                                         for c in columns) + ', PRIMARY KEY (' +
               ','.join(f'`{c}`' for c in list(columns)[:10]) + '))')
    db.executemany('INSERT INTO `creature` VALUES (?,?,?)', creatures)
    db.executemany('INSERT INTO `gameobject` VALUES (?,?,?)', gameobjects)
    db.executemany('INSERT INTO `quest_template` VALUES (?)', quests)
    db.executemany('INSERT INTO `npc_vendor` VALUES (?,?)', vendors)
    db.executemany('INSERT INTO `conditions` VALUES (' + ','.join('?' for _ in columns) + ')', existing)
    script = source.replace('INSERT IGNORE', 'INSERT OR IGNORE')
    db.executescript(script)
    first = sorted(db.execute('SELECT * FROM `conditions`'))
    db.executescript(script)
    assert sorted(db.execute('SELECT * FROM `conditions`')) == first, 'the update is not idempotent'
    return db


def allowed(db, source, group, entry, source_id, stage):
    """Native condition lists: any ElseGroup whose conditions all hold; markers up to the stage are rewarded."""
    found = db.execute('SELECT ElseGroup, ConditionTypeOrReference, ConditionValue1, NegativeCondition FROM `conditions` '
                       'WHERE SourceTypeOrReferenceId=? AND SourceGroup=? AND SourceEntry=? AND SourceId=?',
                       (source, group, entry, source_id)).fetchall()
    if not found and source == 30 and source_id:
        return allowed(db, source, group, entry, 0, stage)
    groups = defaultdict(list)
    for else_group, kind, value, negative in found:
        assert kind == 8 and 66001 <= value <= 66018, ('anchor depends on other conditions', entry, kind)
        groups[else_group].append((stage >= value - 66000) != bool(negative))
    return not groups or any(all(terms) for terms in groups.values())


def spawn(table, entry):
    data = creatures if table == 'creature' else gameobjects
    return next(guid for guid, spawn_entry, _ in data if spawn_entry == entry)


def check(source):
    db = replay(source)
    gated = db.execute("SELECT SourceTypeOrReferenceId, SourceGroup, SourceEntry, SourceId FROM `conditions` "
                       "WHERE Comment LIKE 'Era content: %'").fetchall()
    # Spawn gates leave AI alone: no invisible helpers and no objects with collision or traps.
    for _, group, entry, guid in (row for row in gated if row[0] == 30):
        assert guid, ('visibility gates name the spawn', entry)
        if group == 0 and entry in creature_flags:
            assert not creature_flags[entry][0] & 128, ('invisible helper gated', entry)
            # Ghosts must still find every graveyard's spirit healer.
            assert not creature_flags[entry][1] & (0x4000 | 0x8000), ('spirit healer gated', entry)
        if group == 1 and entry in gameobject_types:
            assert gameobject_types[entry] not in (0, 1, 6, 11, 14, 15, 31, 33), ('mechanical object gated', entry)
    expectations = (
        # Wrath (3.0): Inscription, barbers. Catarina Stanford teaches it in Stormwind.
        ('Inscription trainer', 30, 0, 30713, spawn('creature', 30713), WRATH),
        ('Inscription trainer in Shattrath', 30, 0, 30716, spawn('creature', 30716), WRATH),
        ('Barber', 30, 0, 29141, spawn('creature', 29141), WRATH),
        ('Barbershop chair', 30, 1, 190683, spawn('gameobject', 190683), WRATH),
        ('Light Parchment', 23, 66, 39354, 0, WRATH),
        ('Learn to Ride in Orgrimmar', 19, 0, 14086, 0, WRATH),
        # TBC (2.0 to 2.4): Dustwallow's 2.3 Mudsprocket, guild vaults, blood elf envoys, jewelcrafting.
        ('Mudsprocket flight master', 30, 0, 23612, spawn('creature', 23612), TBC),
        ('Guild vault', 30, 1, 187290, spawn('gameobject', 187290), TBC),
        ('Blood elf ambassador', 30, 0, 16287, spawn('creature', 16287), TBC),
        ('Design: The Jade Eye', 23, 4775, 20975, 0, TBC),
        ('Inspecting the Ruins', 19, 0, 11123, 0, TBC),
        # Hidden creatures do not perceive the character either, so hostile ones are gated too.
        ('Grimtotem raider', 30, 0, 23592, spawn('creature', 23592), TBC),
        # Phases within each expansion open with the raid of their patch: 1.6 Blackwing Lair, 1.9 the
        # Ahn'Qiraj gates, 1.11 Naxxramas, 2.1 the Black Temple and the Netherwing, 3.2 the Crusader.
        ("Blackhand's Command", 19, 0, 7761, 0, 66001),
        ('The Four Dukes', 19, 0, 8538, 0, 66004),
        ("Craftsman's Writ - Dense Weightstone", 19, 0, 9178, 0, 66006),
        ('Blood Oath of the Netherwing', 19, 0, 11012, 0, 66010),
        ('Lord Jaraxxus Must Die!', 19, 0, 24589, 0, 66015),
    )
    for name, source_type, group, entry, source_id, marker in expectations:
        stage = marker - 66000
        assert not allowed(db, source_type, group, entry, source_id, stage - 1), (name, 'reachable before its expansion')
        assert allowed(db, source_type, group, entry, source_id, stage), (name, 'still hidden in its expansion')
    # Vanilla stays: Thrall, the Vanilla Molten Core attunement and Refreshing Spring Water.
    # Classic battlegrounds open by level, so Arathi Basin's 1.7 quests stay too.
    for name, source_type, group, entry, source_id in (('Thrall', 30, 0, 4949, 0), ('Attunement to the Core', 19, 0, 7848, 0),
                                                         ('Refreshing Spring Water', 23, 1250, 159, 0),
                                                         ('The Battle for Arathi Basin!', 19, 0, 8105, 0)):
        assert allowed(db, source_type, group, entry, source_id, 0), name
        assert not db.execute('SELECT 1 FROM `conditions` WHERE SourceTypeOrReferenceId=? AND SourceEntry=? '
                              "AND Comment LIKE 'Era content: %'", (source_type, entry)).fetchone(), name
    # No gate holds a milestone chain back past the tier that needs it.
    for quest, stage in needed.items():
        late = db.execute("SELECT MAX(ConditionValue1) FROM `conditions` WHERE SourceTypeOrReferenceId=19 AND SourceEntry=? "
                          "AND Comment LIKE 'Era content: %'", (quest,)).fetchone()[0]
        assert not late or late - 66000 <= stage, ('milestone chain quest opens too late', quest, late)
    return len(gated)


total = check(update)
print(f'Era world content: {total} gates replay idempotently; anchors open with their patch\'s tier')


def section(marker, era, noun):
    start = update.index(f", 8, 0, {marker}, 0, 0, 0, 0, 0, '', 'Era content: {era} {noun}'")
    return update[update.rindex('INSERT IGNORE', 0, start):update.index(';', start) + 1]


mutations = (
    ('Inscription opens with TBC', update.replace(section(WRATH, 'Wrath', 'creature'), section(WRATH, 'Wrath', 'creature').replace(
        f', 8, 0, {WRATH},', f', 8, 0, {TBC},'))),
    ('TBC creatures stay visible', update.replace(section(TBC, 'TBC', 'creature'), '')),
    ('TBC quests stay available', update.replace(section(TBC, 'TBC', 'quest'), '')),
    ('Wrath vendor items stay for sale', update.replace(section(WRATH, 'Wrath', 'vendor item'), '')),
    ('Naxxramas writs open with Ahn\'Qiraj', update.replace(section(66006, 'Vanilla', 'quest'), section(66006, 'Vanilla', 'quest').replace(
        ', 8, 0, 66006,', ', 8, 0, 66004,'))),
    ('the Netherwing open with TBC', update.replace(section(66010, 'TBC', 'quest'), section(66010, 'TBC', 'quest').replace(
        ', 8, 0, 66010,', ', 8, 0, 66008,'))),
    ('the Scepter chain waits for Ahn\'Qiraj', update + "\nINSERT IGNORE INTO `conditions` SELECT 19, 0, 8742, 0, 0, 8, 0, 66004, "
     "0, 0, 0, 0, 0, '', 'Era content: Vanilla quest';\n"),
    ('gate drops its marker', update.replace(f"0, 8, 0, {TBC}, 0, 0, 0, 0, 0, '', 'Era content: TBC gameobject'",
                                             f"0, 8, 0, {TBC}, 0, 0, 1, 0, 0, '', 'Era content: TBC gameobject'")),
)
for name, source in mutations:
    assert source != update, name
    try:
        check(source)
    except AssertionError:
        print(f'Era world content mutation rejected: {name}')
    else:
        raise AssertionError(f'mutation survived: {name}')
