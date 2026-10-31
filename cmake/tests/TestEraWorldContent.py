"""Replay the era world-content gates on the pinned world and check historical anchors.

Individual Progression hides old-world spawns, quests and vendor items of a later
expansion until the character has rewarded that expansion's progression marker. The
update replays twice on scoped copies of the pinned base world; conditions are then
evaluated the way the native visibility, quest and vendor checks read them. Anchors
are Wrath's Inscription trainers in Azeroth and Outland, barbers and Light
Parchment, TBC's 2.3 Dustwallow Marsh, guild vaults and jewelcrafting designs, and
Vanilla content that stays put. Mutations weaken or drop single gates.
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
sight = function((core / 'src/server/game/Entities/Object/Object.cpp').read_text(), 'bool WorldObject::CanSeeOrDetect(')
assert sight.count('if (!player->CanSeeObjectByVisibilityConditions(obj))') == 2
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
assert all(re.search(rf'^\({marker},', markers, re.MULTILINE) for marker in (TBC, WRATH))

# Every row is a rewarded-marker gate the update can find and remove again.
INSERTS = re.findall(r"INSERT IGNORE INTO `conditions` \([^)]*\)\nSELECT (?:DISTINCT )?(\d+), [^;]*?, 8, 0, (\d+), 0, 0, 0, 0, 0, '', "
                     r"'Era content: (TBC|Wrath) (creature|gameobject|quest|vendor item)'", update)
assert len(INSERTS) == update.count('INSERT'), 'every insert is a marker gate'
assert all((marker == str(TBC)) == (era == 'TBC') and marker in (str(TBC), str(WRATH)) for _, marker, era, _ in INSERTS)
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
creature_flags = {int(r['entry']): int(r['flags_extra']) for r in rows('creature_template', {e for _, e, _ in creatures})}
gameobject_types = {int(r['entry']): int(r['type']) for r in rows('gameobject_template', {e for _, e, _ in gameobjects})}


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
            assert not creature_flags[entry] & 128, ('invisible helper gated', entry)
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
    )
    for name, source_type, group, entry, source_id, marker in expectations:
        stage = marker - 66000
        assert not allowed(db, source_type, group, entry, source_id, stage - 1), (name, 'reachable before its expansion')
        assert allowed(db, source_type, group, entry, source_id, stage), (name, 'still hidden in its expansion')
    # Vanilla stays: Thrall, the Vanilla Molten Core attunement and Refreshing Spring Water.
    for name, source_type, group, entry, source_id in (('Thrall', 30, 0, 4949, 0), ('Attunement to the Core', 19, 0, 7848, 0),
                                                         ('Refreshing Spring Water', 23, 1250, 159, 0)):
        assert allowed(db, source_type, group, entry, source_id, 0), name
        assert not db.execute('SELECT 1 FROM `conditions` WHERE SourceTypeOrReferenceId=? AND SourceEntry=? '
                              "AND Comment LIKE 'Era content: %'", (source_type, entry)).fetchone(), name
    # Hostile Grimtotem raiders of 2.3 stay visible rather than attack unseen.
    assert not db.execute("SELECT 1 FROM `conditions` WHERE SourceTypeOrReferenceId=30 AND SourceGroup=0 AND SourceEntry=23592").fetchone()
    return len(gated)


total = check(update)
print(f'Era world content: {total} gates replay idempotently; anchors open with TBC (66008) and Wrath (66013)')


def section(era, noun):
    start = update.index(f"'Era content: {era} {noun}'")
    return update[update.rindex('INSERT IGNORE', 0, start):update.index(';', start) + 1]


mutations = (
    ('Inscription opens with TBC', update.replace(section('Wrath', 'creature'), section('Wrath', 'creature').replace(
        f', 8, 0, {WRATH},', f', 8, 0, {TBC},'))),
    ('TBC creatures stay visible', update.replace(section('TBC', 'creature'), '')),
    ('TBC quests stay available', update.replace(section('TBC', 'quest'), '')),
    ('Wrath vendor items stay for sale', update.replace(section('Wrath', 'vendor item'), '')),
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
