"""Validate Frostmane Hold's narrow SQL correction and native quest eligibility.

Execute the delivered SQL directly on a scoped SQLite copy of the locked quest
data, then compile the core's unchanged eligibility methods against both states.
This fixture does not launch a realm or certify all historical quest variants.
"""

from pathlib import Path
import argparse
import os
import re
import sqlite3
import subprocess
import tempfile

from PreparedSources import prepared_core


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    cursor = opening + 1
    while depth:
        depth += (source[cursor] == '{') - (source[cursor] == '}')
        cursor += 1
    return source[start:cursor]


def numeric_row(path, quest_id):
    source = path.read_text()
    columns = re.findall(r'^  `([^`]+)`', source, re.MULTILINE)
    row = re.search(r'^\(' + str(quest_id) + r',([0-9.,-]+)', source, re.MULTILINE)
    assert row, (path, quest_id)
    values = (str(quest_id) + ',' + row.group(1).rstrip(',')).split(',')
    return {column: int(value) for column, value in zip(columns, values)}


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--core', type=Path, help='prepared core source directory')
parser.add_argument('--module', type=Path, help='prepared Individual Progression module')
args = parser.parse_args()
repository = Path(__file__).resolve().parents[2]
core = args.core or prepared_core(repository)
module = args.module or core / 'modules/mod-individual-progression'
sql = (module / 'data/sql/world/updates/2026_10_09_00_frostmane_hold.sql').read_text()
addon_path = core / 'data/sql/base/db_world/quest_template_addon.sql'
quest_path = core / 'data/sql/base/db_world/quest_template.sql'
ids = (282, 287, 291, 420)
addon_rows = {quest_id: numeric_row(addon_path, quest_id) for quest_id in ids}
quest_rows = {quest_id: numeric_row(quest_path, quest_id) for quest_id in ids}
assert addon_rows[287]['PrevQuestID'] == 420
assert addon_rows[420]['NextQuestID'] == 0  # No reverse edge can regenerate 287 -> 420.
assert addon_rows[291]['PrevQuestID'] == 287
addon_source = addon_path.read_text()
addon_columns = re.findall(r'^  `([^`]+)`', addon_source, re.MULTILINE)
for match in re.finditer(r'^\(([0-9,-]+)\)', addon_source, re.MULTILINE):
    row = dict(zip(addon_columns, map(int, match.group(1).split(','))))
    assert row['NextQuestID'] != 287, row  # No other quest contributes an implicit prerequisite.

db = sqlite3.connect(':memory:')
columns = list(addon_rows[287])
db.execute('CREATE TABLE quest_template_addon (' + ', '.join(
    '"' + column + '" INTEGER' for column in columns) + ')')
insert = 'INSERT INTO quest_template_addon VALUES (' + ','.join('?' for _ in columns) + ')'
for row in addon_rows.values():
    db.execute(insert, [row[column] for column in columns])
unrelated = dict(addon_rows[287], ID=999999)
db.execute(insert, [unrelated[column] for column in columns])
before = db.execute('SELECT * FROM quest_template_addon ORDER BY ID').fetchall()
db.executescript(sql)
after = db.execute('SELECT * FROM quest_template_addon ORDER BY ID').fetchall()
after_rows = {row[0]: dict(zip(columns, row)) for row in after}
expected = [tuple(0 if column == 'PrevQuestID' and row[0] == 287 else value
    for column, value in zip(columns, row)) for row in before]
assert after == expected  # Every field of every other quest remains byte-for-byte equivalent.
db.executescript(sql)
assert db.execute('SELECT * FROM quest_template_addon ORDER BY ID').fetchall() == after
for custom in (0, -420, 12345):
    db.execute('UPDATE quest_template_addon SET PrevQuestID=? WHERE ID=287', (custom,))
    snapshot = db.execute('SELECT * FROM quest_template_addon ORDER BY ID').fetchall()
    db.executescript(sql)
    assert db.execute('SELECT * FROM quest_template_addon ORDER BY ID').fetchall() == snapshot
db.execute('DELETE FROM quest_template_addon WHERE ID=287')
snapshot = db.execute('SELECT * FROM quest_template_addon ORDER BY ID').fetchall()
db.executescript(sql)
assert db.execute('SELECT * FROM quest_template_addon ORDER BY ID').fetchall() == snapshot
print('SQL scope, idempotence, customized prerequisites and missing quest: passed')

source = (core / 'src/server/game/Entities/Player/PlayerQuest.cpp').read_text()
methods = '\n\n'.join(function(source, signature) for signature in (
    'bool Player::CanTakeQuest(',
    'bool Player::SatisfyQuestPreviousQuest(',
    'bool Player::SatisfyQuestClass(',
    'bool Player::SatisfyQuestRace(',
    'bool Player::SatisfyQuestLevel(',
))
loader = (core / 'src/server/game/Globals/ObjectMgr.cpp').read_text()
assert 'qinfo->prevQuests.push_back(qinfo->PrevQuestId);' in loader
assert 'qNextItr->second->prevQuests.push_back(static_cast<int32>(qinfo->GetQuestId()));' in loader

fixture = r'''
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <map>
#include <set>
#include <vector>
using uint32 = std::uint32_t;
enum { DISABLE_TYPE_QUEST, INVALIDREASON_DONT_HAVE_REQ, INVALIDREASON_QUEST_FAILED_LOW_LEVEL,
    INVALIDREASON_QUEST_FAILED_WRONG_RACE, QUEST_STATUS_NONE, QUEST_STATUS_INCOMPLETE };
struct Quest
{
    using PrevQuests = std::vector<int>;
    uint32 id = 0, minLevel = 1, maxLevel = 0, races = 0, classes = 0;
    int exclusiveGroup = 0;
    PrevQuests prevQuests;
    bool IsSeasonal() const { return false; }
    int GetExclusiveGroup() const { return exclusiveGroup; }
    uint32 GetQuestId() const { return id; }
    uint32 GetMinLevel() const { return minLevel; }
    uint32 GetMaxLevel() const { return maxLevel; }
    uint32 GetAllowableRaces() const { return races; }
    uint32 GetRequiredClasses() const { return classes; }
};
struct ObjectMgr
{
    using Groups = std::multimap<int, uint32>;
    using ExclusiveQuestGroupsBounds = std::pair<Groups::const_iterator, Groups::const_iterator>;
    Groups mExclusiveQuestGroups;
    std::map<uint32, Quest> quests;
    Quest const* GetQuestTemplate(uint32 id) const
    {
        auto const iter = quests.find(id);
        return iter == quests.end() ? nullptr : &iter->second;
    }
} objectMgr;
auto* sObjectMgr = &objectMgr;
struct DisableMgr
{
    bool IsDisabledFor(int, uint32, void const*) const { return false; }
} disableMgr;
auto* sDisableMgr = &disableMgr;
struct Player
{
    uint32 level = 9, raceMask = 1, classMask = 1;
    std::set<uint32> rewarded, active;
    mutable std::vector<int> errors;
    uint32 GetLevel() const { return level; }
    uint32 getRaceMask() const { return raceMask; }
    uint32 getClassMask() const { return classMask; }
    bool IsQuestRewarded(uint32 id) const { return rewarded.contains(id); }
    int GetQuestStatus(uint32 id) const { return active.contains(id) ? QUEST_STATUS_INCOMPLETE : QUEST_STATUS_NONE; }
    void SendCanTakeQuestResponse(int reason) const { errors.push_back(reason); }
    bool CanTakeQuest(Quest const*, bool);
    bool SatisfyQuestPreviousQuest(Quest const*, bool) const;
    bool SatisfyQuestClass(Quest const*, bool) const;
    bool SatisfyQuestRace(Quest const*, bool) const;
    bool SatisfyQuestLevel(Quest const*, bool) const;
#define NORMAL_GUARD(name) bool name(Quest const*, bool) const { return true; }
    NORMAL_GUARD(SatisfyQuestStatus)
    NORMAL_GUARD(SatisfyQuestExclusiveGroup)
    NORMAL_GUARD(SatisfyQuestSkill)
    NORMAL_GUARD(SatisfyQuestReputation)
    NORMAL_GUARD(SatisfyQuestTimed)
    NORMAL_GUARD(SatisfyQuestNextChain)
    NORMAL_GUARD(SatisfyQuestPrevChain)
    NORMAL_GUARD(SatisfyQuestBreadcrumb)
    NORMAL_GUARD(SatisfyQuestDay)
    NORMAL_GUARD(SatisfyQuestWeek)
    NORMAL_GUARD(SatisfyQuestMonth)
    NORMAL_GUARD(SatisfyQuestSeasonal)
    NORMAL_GUARD(SatisfyQuestConditions)
#undef NORMAL_GUARD
};
NATIVE_METHODS
int main()
{
    QUEST_ROWS
    Player player;
    Quest before = objectMgr.quests.at(287);
    assert(!player.CanTakeQuest(&before, true));
    assert(player.errors.back() == INVALIDREASON_DONT_HAVE_REQ);
    player.rewarded.insert(420);
    assert(player.CanTakeQuest(&before, false));
    player.rewarded.clear();
    objectMgr.quests.at(287).prevQuests = {AFTER_PREVIOUS};  // Actual executed SQL result.
    Quest const* hold = objectMgr.GetQuestTemplate(287);
    assert(player.CanTakeQuest(hold, false));
    for (uint32 allianceRace : {1u, 4u, 8u, 64u, 1024u})
    {
        player.raceMask = allianceRace;
        assert(player.CanTakeQuest(hold, false));
    }
    player.raceMask = 2;  // Horde is still rejected.
    assert(!player.CanTakeQuest(hold, true));
    assert(player.errors.back() == INVALIDREASON_QUEST_FAILED_WRONG_RACE);
    player.raceMask = 1;
    player.level = hold->GetMinLevel() - 1;
    assert(!player.CanTakeQuest(hold, true));
    assert(player.errors.back() == INVALIDREASON_QUEST_FAILED_LOW_LEVEL);
    player.level = hold->GetMinLevel();
    assert(player.CanTakeQuest(hold, false));
    assert(!player.CanTakeQuest(objectMgr.GetQuestTemplate(291), false));
    player.rewarded.insert(287);
    assert(player.CanTakeQuest(objectMgr.GetQuestTemplate(291), false));
    assert(!player.CanTakeQuest(objectMgr.GetQuestTemplate(420), false));
    player.rewarded.insert(282);
    assert(player.CanTakeQuest(objectMgr.GetQuestTemplate(420), false));
    Quest custom = *hold;
    custom.prevQuests = {420};
    assert(!player.CanTakeQuest(&custom, false));
    custom.prevQuests = {-420};
    assert(!player.CanTakeQuest(&custom, false));
    player.active.insert(420);
    assert(player.CanTakeQuest(&custom, false));
    custom.prevQuests.clear();
    custom.classes = 2;
    assert(!player.CanTakeQuest(&custom, false));
    custom.classes = 1;
    assert(player.CanTakeQuest(&custom, false));
}
'''
initializers = []
for quest_id in ids:
    quest, addon = quest_rows[quest_id], addon_rows[quest_id]
    previous = str(addon['PrevQuestID']) if addon['PrevQuestID'] else ''
    initializers.append('objectMgr.quests.emplace(' + str(quest_id) + ', Quest{' + ','.join(str(value)
        for value in (quest_id, quest['MinLevel'], addon['MaxLevel'], quest['AllowableRaces'],
            addon['AllowableClasses'], addon['ExclusiveGroup'])) + ',{' + previous + '}});')
fixture = fixture.replace('NATIVE_METHODS', methods).replace('QUEST_ROWS', '\n    '.join(initializers))
after_previous = after_rows[287]['PrevQuestID']
fixture = fixture.replace('AFTER_PREVIOUS', str(after_previous) if after_previous else '')
with tempfile.TemporaryDirectory(prefix='frostmane-hold-') as temporary:
    temporary = Path(temporary)
    cpp = temporary / 'fixture.cpp'
    executable = temporary / 'fixture'
    cpp.write_text(fixture)
    subprocess.run([os.environ.get('CXX', 'g++'), '-std=c++20', '-Wall', '-Wextra', '-Werror',
        '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(cpp), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
print('Native quest eligibility: before/after, level, Alliance/Horde, follow-up, Senir and custom gates passed')
