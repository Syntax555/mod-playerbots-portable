"""Run Individual Progression's Alterac Valley turn-in handlers with native quest data.

The production hide, supply estimate and air-strike handlers run against engine
doubles under AddressSanitizer. A hide reward away from its cavalry commander
must not dereference the missing creature, every quarter of a supply stage has
its own estimate, and each Call of Air quest counts for the wing commander the
pinned world data makes its quest ender. Mutation checks restore each defect.
"""

import argparse
from pathlib import Path
import re
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    cxx,
    function,
    prepared_core,
    reject_part_mutants,
    run_fixture,
    source_argument,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help='Individual Progression module directory')
args = parser.parse_args()
core = prepared_core()
module = args.source or core / 'modules/mod-individual-progression'
header = (module / 'src/vanillaScripts/av_quests.h').read_text()
script = (module / 'src/vanillaScripts/av_quests.cpp').read_text()

# The handlers run from the reward hook, which a reward without the quest giver
# in range also reaches, and the native search reports a missing creature as null.
rewarded = function((core / 'src/server/game/Entities/Player/PlayerQuest.cpp').read_text(), 'void Player::RewardQuest(')
assert 'sScriptMgr->OnPlayerCompleteQuest(this, quest);' in rewarded
assert 'player->RewardQuest(quest, 0, player);' in (core / 'src/server/scripts/Commands/cs_quest.cpp').read_text()
search = function((core / 'src/server/game/Entities/Object/Object.cpp').read_text(),
                  'Creature* WorldObject::FindNearestCreature(')
assert 'Creature* creature = nullptr;' in search and 'return creature;' in search
assert 'void OnPlayerCompleteQuest(Player* player, Quest const* quest) override' in script
config = (core / 'src/common/Configuration/Config.h').read_text()
assert 'T GetOption(std::string const& name, T const& def, bool showLogs = true) const;' in config
teams = function((core / 'src/server/shared/SharedDefines.h').read_text(), 'enum TeamId')
assert re.search(r'TEAM_ALLIANCE\s*=\s*0,\s*TEAM_HORDE,', teams)

# The pinned world decides which wing commander ends each Call of Air quest.
quests = {int(value) for value in re.findall(r'AV_Q_[AH]_COMMANDER\d\s*=\s*(\d+)', header)}
assert len(quests) == 6
pair = re.compile(r'\((\d+),\s*(\d+)\)')
enders = {}
for line in (core / 'data/sql/base/db_world/creature_questender.sql').read_text().splitlines():
    match = pair.match(line)
    if match and int(match[2]) in quests:
        assert int(match[2]) not in enders
        enders[int(match[2])] = int(match[1])
assert set(enders) == quests
# The module's own data keeps those native quest enders.
for path in sorted((module / 'data/sql/world/base').glob('*.sql')):
    for statement in re.findall(r'INSERT INTO `creature_questender`[^;]*;', path.read_text()):
        for npc, quest in pair.findall(statement):
            assert int(quest) not in quests or enders[int(quest)] == int(npc), (path.name, npc, quest)

parts = {
    'header': header.replace('#include "SharedDefines.h"\n', ''),
    'script': '\n'.join(function(script, '    ' + signature) for signature in (
        'uint32 ScrapsThreshold(uint8 tier)',
        'bool AirstrikeReady(',
        'void HandleHidesTurnIn(',
        'char const* ScrapsEstimateLine(',
        'void HandleAirStrikeTurnIn(',
    )),
}
assert '#include' not in parts['header'].replace('#include <array>', '')

harness = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <string>
#include <string_view>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
@TEAMS@;
enum : uint32 { UNIT_NPC_FLAG_QUESTGIVER = 2 };
enum TempSummonType { TEMPSUMMON_TIMED_DESPAWN };
@HEADER@
struct Creature
{
    uint32 flags = UNIT_NPC_FLAG_QUESTGIVER, faction = 0;
    bool visible = true;
    void RemoveNpcFlag(uint32 flag) { flags &= ~flag; }
    void SetVisible(bool value) { visible = value; }
    void SetFaction(uint32 value) { faction = value; }
};
struct Session { };
struct Player
{
    Session session;
    std::map<uint32, Creature*> nearby;
    std::vector<uint32> summoned;
    Session* GetSession() { return &session; }
    // Native FindNearestCreature returns null when no such creature is in range.
    Creature* FindNearestCreature(uint32 entry, float /*range*/)
    {
        auto const found = nearby.find(entry);
        return found == nearby.end() ? nullptr : found->second;
    }
    void SummonCreature(uint32 entry, float, float, float, float, TempSummonType, uint32) { summoned.push_back(entry); }
};
struct ChatHandler
{
    explicit ChatHandler(Session*) { }
    template <class... Args> void PSendSysMessage(std::string_view, Args&&...) { }
};
struct ConfigMgr
{
    template <class T> T GetOption(std::string const&, T const& def, bool = true) const { return def; }
} config;
ConfigMgr* sConfigMgr = &config;
namespace
{
@SCRIPT@
}

int main()
{
    // The tenth hide completes the harnesses wherever the reward is given.
    for (TeamId team : { TEAM_ALLIANCE, TEAM_HORDE })
    {
        uint32 const commanderEntry = team == TEAM_ALLIANCE ? NPC_CAV_CMDR_A : NPC_CAV_CMDR_H;
        for (bool commanderNearby : { false, true })
        {
            AVQuestState state;
            Player player;
            Creature commander;
            if (commanderNearby)
                player.nearby[commanderEntry] = &commander;
            for (uint32 turnIn = 1; turnIn <= 10; ++turnIn)
            {
                assert(!state.HidesCompleted[team] && (commander.flags & UNIT_NPC_FLAG_QUESTGIVER));
                HandleHidesTurnIn(&player, state, team);
            }
            assert(state.HidesCompleted[team] && !state.HidesCompleted[team == TEAM_ALLIANCE ? TEAM_HORDE : TEAM_ALLIANCE]);
            assert(bool(commander.flags & UNIT_NPC_FLAG_QUESTGIVER) == !commanderNearby);
        }
    }

    // 25 turn-ins reach the first upgrade; each quarter of the way has its own line.
    AVQuestState supplies;
    std::vector<std::string> lines;
    std::vector<uint32> first;
    for (uint32 turnIns = 0; turnIns < 25; ++turnIns)
    {
        supplies.scrapTurnIns[TEAM_HORDE] = turnIns;
        std::string const line = ScrapsEstimateLine(supplies, TEAM_HORDE);
        if (lines.empty() || lines.back() != line)
        {
            lines.push_back(line);
            first.push_back(turnIns);
        }
    }
    assert((lines == std::vector<std::string>{
        "I barely have any supplies for upgrades.",
        "I need many more supplies in order to upgrade our units.",
        "I have about half the supplies needed to upgrade our units.",
        "I almost have enough supplies for the next upgrade!" }));
    assert((first == std::vector<uint32>{ 0, 7, 13, 19 }));
    supplies.defenderTier[TEAM_HORDE] = AV_DEFENDER_TIER_CHAMPION;
    assert(std::string(ScrapsEstimateLine(supplies, TEAM_HORDE)) == "I cannot store any more supplies. I have all I can handle!");

    // A fleet launches after 50 turn-ins of its own quest and hides the commander who took them.
    std::map<uint32, uint32> const questEnders = { @ENDERS@ };
    assert(questEnders.size() == AV_AIR_FLEETS.size());
    for (AVAirFleet const& fleet : AV_AIR_FLEETS)
    {
        assert(questEnders.at(fleet.questId) == fleet.questGiverEntry);
        AVQuestState state;
        Player player;
        std::map<uint32, Creature> commanders;
        for (AVAirFleet const& other : AV_AIR_FLEETS)
            player.nearby[other.questGiverEntry] = &commanders[other.questGiverEntry];
        for (uint32 turnIn = 1; turnIn <= 50; ++turnIn)
        {
            assert(player.summoned.empty());
            HandleAirStrikeTurnIn(&player, state, fleet);
        }
        assert(player.summoned.size() == 1 && player.summoned[0] == fleet.questGiverEntry + 200000);
        for (auto const& [entry, commander] : commanders)
        {
            bool const launched = entry == questEnders.at(fleet.questId);
            assert(commander.visible == !launched);
            assert(bool(commander.flags & UNIT_NPC_FLAG_QUESTGIVER) == !launched);
        }
        for (AVAirFleet const& other : AV_AIR_FLEETS)
            assert(state.airTurnIns[other.team][other.index] == (other.questId == fleet.questId ? 50u : 0u));
    }
}
'''.replace('@TEAMS@', teams).replace('@ENDERS@', ', '.join(f'{{ {quest}, {npc} }}' for quest, npc in sorted(enders.items())))

mutations = (
    ('missing cavalry commander dereferenced', 'script',
     'if (Creature* npcQuest = player->FindNearestCreature(npcEntryQuest, 50.0f))\n            npcQuest->',
     'Creature* npcQuest = player->FindNearestCreature(npcEntryQuest, 50.0f);\n        npcQuest->'),
    ('half-way supply estimate unreachable', 'script',
     'if (remaining * 4 >= interval) //', 'if (remaining * 4 <= interval * 2 && remaining * 4 >= interval * 3) //'),
    ('Vipore and Slidore fleets exchanged', 'header',
     '{ AV_Q_A_COMMANDER2, TEAM_ALLIANCE, 1, NPC_WING_CMDR_SLIDORE,',
     '{ AV_Q_A_COMMANDER1, TEAM_ALLIANCE, 1, NPC_WING_CMDR_SLIDORE,'),
    ('fleet quest without its own commander', 'header',
     '{ AV_Q_A_COMMANDER1, TEAM_ALLIANCE, 2, NPC_WING_CMDR_VIPORE,',
     '{ AV_Q_A_COMMANDER2, TEAM_ALLIANCE, 2, NPC_WING_CMDR_VIPORE,'),
)

with tempfile.TemporaryDirectory(prefix='portable-av-quests-') as temporary:
    directory = Path(temporary)

    def build(variant, tag):
        source = directory / f'{tag}.cpp'
        source.write_text(harness.replace('@HEADER@', variant['header']).replace('@SCRIPT@', variant['script']))
        executable = directory / tag
        subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                        '-Wno-unused-variable', '-Wno-unused-function', '-Wno-unused-const-variable',
                        *SANITIZER_FLAGS, str(source), '-o', str(executable)], check=True)
        return run_fixture([str(executable)], f'Alterac Valley quests {tag}')

    result = build(parts, 'production')
    assert result.returncode == 0, result.stderr
    print('Alterac Valley turn-ins passed')
    reject_part_mutants(parts, mutations, build, 'Alterac Valley turn-ins')
