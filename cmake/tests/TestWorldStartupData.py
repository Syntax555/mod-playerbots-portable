"""Replay startup-data repairs on scoped copies of the pinned world and module SQL."""

import argparse
import re
import sqlite3

from FixtureSupport import (
    function,
    prepared_core,
    source_argument,
    sql_rows,
    sql_values,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, 'core', default=prepared_core())
source_argument(parser, 'ip')
source_argument(parser, 'events')
args = parser.parse_args()
core = args.core
ip = args.ip or core / 'modules/mod-individual-progression'
events = args.events or core / 'modules/mod-era-events'
pool_path = ip / 'data/sql/world/updates/zz_2026_10_24_00_mirelow_pool.sql'
menu_path = events / 'data/sql/db-world/updates/mod_era_events_2026_10_24_00_aq_dragon_menus.sql'
help_path = core / 'modules/mod-lfg-progression/data/sql/db-world/updates/mod_lfg_progression_2026_10_24_00_command_help.sql'
pool_sql, menu_sql, help_sql = pool_path.read_text(), menu_path.read_text(), help_path.read_text()
world = core / 'data/sql/base/db_world'
tables = ('creature_template', 'pool_template', 'pool_creature', 'pool_gameobject',
          'pool_quest', 'pool_pool', 'game_event_pool')


def database():
    db = sqlite3.connect(':memory:')
    for table in tables:
        columns = re.findall(r'^  `([^`]+)`', (world / (table + '.sql')).read_text(), re.MULTILINE)
        # Numeric affinity retains the dump's integer and text values, including all unmodified fields.
        db.execute('CREATE TABLE `' + table + '` (' + ','.join('`' + col + '` INTEGER' for col in columns) + ')')
    return db


def insert(db, table, rows):
    for row in rows:
        db.execute('INSERT INTO `' + table + '` VALUES (' + ','.join('?' for _ in row) + ')',
                   [None if value == 'NULL' else value for value in row.values()])


def snapshot(db):
    return {table: db.execute('SELECT * FROM `' + table + '` ORDER BY 1,2').fetchall() for table in tables}


# The producer clones the native dragon templates, then clears their interaction flags.
clones = (events / 'data/sql/db-world/updates/mod_era_events_2026_09_29_02_aq_war.sql').read_text()
assert 'SELECT `ct`.* FROM `creature_template` `ct` JOIN `tmp_era_aq_map`' in clones
assert '`ct`.`gossip_menu_id`' not in clones
mapping = [(int(src), int(dst)) for src, dst in re.findall(
    r"\((\d+), (\d+), 'npc_era_aq_dragon',", clones)]
assert mapping == [(15378, 9500815), (15380, 9500816), (15379, 9500817)]
native = {int(row['entry']): row for row in sql_rows(core, 'creature_template', {src for src, _ in mapping})}
expected_menus = {9500815: 6795, 9500816: 6793, 9500817: 6794}
clear_flags = re.search(r'UPDATE `creature_template` SET `npcflag` = 0[^;]+;', clones).group()
loader = (core / 'src/server/game/Globals/ObjectMgr.cpp').read_text()
assert '(cInfo->GossipMenuId && !(cInfo->npcflag & UNIT_NPC_FLAG_GOSSIP))' in loader
unit_defines = (core / 'src/server/game/Entities/Unit/UnitDefines.h').read_text()
assert re.search(r'UNIT_NPC_FLAG_GOSSIP\s*= 0x00000001', unit_defines)
creature_data = (core / 'src/server/game/Entities/Creature/CreatureData.h').read_text()
assert re.search(r'CREATURE_FLAG_EXTRA_MODULE\s*= 0x01000000', creature_data)
assert all(not int(row['flags_extra']) & 0x01000000 for row in native.values())
assert menu_path.name > 'mod_era_events_2026_09_29_02_aq_war.sql'


def check_menus(sql):
    with database() as db:
        insert(db, 'creature_template', native.values())
        for src, dst in mapping:
            row = dict(native[src], entry=str(dst), ScriptName='npc_era_aq_dragon', AIName='')
            assert int(row['gossip_menu_id']) == expected_menus[dst]
            insert(db, 'creature_template', [row])
        db.executescript(clear_flags)
        before = snapshot(db)
        assert db.execute('SELECT count(*) FROM creature_template WHERE entry>=9500815 '
                          'AND gossip_menu_id<>0 AND (npcflag & 1)=0').fetchone()[0] == 3
        db.executescript(sql)
        expected = dict(before)
        columns = [col[1] for col in db.execute('PRAGMA table_info(creature_template)')]
        menu_col = columns.index('gossip_menu_id')
        expected['creature_template'] = [tuple(0 if index == menu_col and row[0] in expected_menus else value
                                                   for index, value in enumerate(row))
                                         for row in before['creature_template']]
        assert snapshot(db) == expected, 'dragon repair missing or changed another field'
        db.executescript(sql)
        assert snapshot(db) == expected, 'dragon repair is not idempotent'
        for field, value in (('gossip_menu_id', 99999), ('npcflag', 2), ('ScriptName', 'custom_dragon')):
            db.execute('UPDATE creature_template SET gossip_menu_id=6795, npcflag=0, '
                       "ScriptName='npc_era_aq_dragon' WHERE entry=9500815")
            db.execute('UPDATE creature_template SET `' + field + '`=? WHERE entry=9500815', (value,))
            custom = snapshot(db)
            db.executescript(sql)
            assert snapshot(db) == custom, 'dragon repair changed a custom field'
        db.execute('DELETE FROM creature_template WHERE entry=9500815')
        missing = snapshot(db)
        db.executescript(sql)
        assert snapshot(db) == missing, 'dragon repair recreated a missing template'


# Individual Progression removes Mirelow's pool members and uses one waypoint patrol.
wetlands = (ip / 'data/sql/world/base/zone_wetlands.sql').read_text()
remove_members = re.search(r'DELETE FROM `pool_creature` WHERE `pool_entry` = 1072;', wetlands).group()
assert '(91113, 14424,' in wetlands and '(91113, 911130,' in wetlands and '(911130, 1,' in wetlands
assert pool_path.name > 'zone_wetlands.sql'
members = []
for line in (world / 'pool_creature.sql').read_text().splitlines():
    if line.startswith('('):
        values = sql_values(line.rstrip(',;')[1:-1])
        if values[1] == '1072':
            members.append(dict(zip(('guid', 'pool_entry', 'chance', 'description'), values)))
assert len(members) == 22
pool_rows = sql_rows(core, 'pool_template', {1072, 1073})
assert next(row for row in pool_rows if row['entry'] == '1072') == {
    'entry': '1072', 'max_limit': '1', 'description': 'Mirelow (14424)'}
for table, columns in (('pool_gameobject', (1,)), ('pool_quest', (1,)),
                       ('pool_pool', (0, 1)), ('game_event_pool', (1,))):
    for line in (world / (table + '.sql')).read_text().splitlines():
        if line.startswith('('):
            values = sql_values(line.rstrip(',;')[1:-1])
            assert all(values[index] != '1072' for index in columns), (table, values)
pool_loader = (core / 'src/server/game/Pools/PoolMgr.cpp').read_text()
empty = function(pool_loader, 'bool PoolMgr::IsEmpty(')
assert all(group in empty for group in ('mPoolGameobjectGroups', 'mPoolCreatureGroups',
                                       'mPoolPoolGroups', 'mPoolQuestGroups'))
assert 'if (IsEmpty(poolId))\n            LOG_ERROR' in pool_loader
updater = (core / 'src/server/database/Updater/UpdateFetcher.cpp').read_text()
assert 'left.first.filename().string() < right.first.filename().string()' in updater


def check_pool(sql):
    with database() as db:
        insert(db, 'pool_template', pool_rows)
        insert(db, 'pool_creature', members)
        db.executescript(remove_members)
        before = snapshot(db)
        db.executescript(sql)
        expected = dict(before)
        expected['pool_template'] = [row for row in before['pool_template'] if row[0] != 1072]
        assert snapshot(db) == expected, 'obsolete pool repair missing or changed another row'
        db.executescript(sql)
        assert snapshot(db) == expected, 'obsolete pool repair is not idempotent'
    # Guard every membership/reference and customized template independently.
    for custom in (
        'INSERT INTO pool_creature VALUES (91113,1072,0,"custom")',
        'INSERT INTO pool_gameobject VALUES (99999,1072,0,"custom")',
        'INSERT INTO pool_quest VALUES (99999,1072,"custom")',
        'INSERT INTO pool_pool VALUES (99999,1072,0,"custom")',
        'INSERT INTO pool_pool VALUES (1072,99999,0,"custom")',
        'INSERT INTO game_event_pool VALUES (99,1072)',
        'UPDATE pool_template SET max_limit=2 WHERE entry=1072',
        'UPDATE pool_template SET description="custom" WHERE entry=1072',
    ):
        with database() as db:
            insert(db, 'pool_template', pool_rows)
            db.execute(custom)
            before = snapshot(db)
            db.executescript(sql)
            assert snapshot(db) == before, 'pool repair removed a custom/referenced pool'


# A chat command without a `command` row logs a missing-help warning at startup.
chat = (core / 'src/server/game/Chat/ChatCommands/ChatCommand.cpp').read_text()
assert 'LOG_WARN("sql.sql", "Table `command` is missing help text for command \'{}\'.", name);' in chat
commands = (core / 'src/server/database/Database/Implementation/WorldDatabase.cpp').read_text()
assert '"SELECT name, security, help FROM command"' in commands
assert re.search(r'SEC_PLAYER\s*= 0,', (core / 'src/common/Common.h').read_text())
lfg_source = (core / 'modules/mod-lfg-progression/src/LfgProgression.cpp').read_text()
assert '{ "lfgprogress", HandleStatus, SEC_PLAYER, Acore::ChatCommands::Console::No },' in lfg_source
assert 'world' in help_path.parts[-3]
command_schema = (world / 'command.sql').read_text().split('CREATE TABLE `command` (')[1].split(') ENGINE')[0]
assert '`name` varchar(50)' in command_schema and 'PRIMARY KEY (`name`)' in command_schema


def check_help(sql):
    # The updater's client reads MySQL string escapes.
    script = sql.replace('INSERT IGNORE', 'INSERT OR IGNORE').replace("\\'", "''").replace('\\n', '\n')
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE command (name TEXT PRIMARY KEY, security INTEGER, help TEXT)')
        for _ in range(2):
            db.executescript(script)
            row = db.execute("SELECT security, help FROM command WHERE name = 'lfgprogress'").fetchone()
            assert row and row[0] == 0 and row[1].startswith('Syntax: .lfgprogress\nShows'), row
        db.execute("UPDATE command SET security = 1, help = 'custom' WHERE name = 'lfgprogress'")
        db.executescript(script)
        assert db.execute("SELECT security, help FROM command WHERE name = 'lfgprogress'").fetchone() == (1, 'custom')


check_menus(menu_sql)
check_pool(pool_sql)
check_help(help_sql)
print('Startup SQL: native dragon copies, obsolete Mirelow pool, command help, scope, ordering, custom data and '
      'idempotence passed')
for label, check, mutant in (
    ('missing dragon repair', check_menus, ''),
    ('missing dragon guards', check_menus, re.sub(r"`ScriptName` = 'npc_era_aq_dragon' AND `npcflag` = 0", '1', menu_sql)),
    ('missing Mirelow repair', check_pool, ''),
    ('missing pool guards', check_pool, re.sub(r'\n  AND NOT EXISTS[^;]+', '', pool_sql)),
    ('missing command help', check_help, ''),
    ('command help with another security level', check_help, help_sql.replace("('lfgprogress', 0,", "('lfgprogress', 2,")),
    ('command help replacing a custom entry', check_help, help_sql.replace('INSERT IGNORE', 'REPLACE')),
):
    original = {check_menus: menu_sql, check_pool: pool_sql, check_help: help_sql}[check]
    assert mutant != original, label
    try:
        check(mutant)
    except AssertionError:
        print('Startup SQL mutation rejected: ' + label)
    else:
        raise AssertionError('Startup SQL fixture accepted ' + label)
