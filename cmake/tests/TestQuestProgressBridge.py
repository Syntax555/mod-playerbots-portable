"""Run the bridge's quest snapshots and subscriptions against native-shaped world state.

The fixture compiles the actual production functions. Native quest status types,
counter producers, packet routing and map-update barriers are checked separately;
world lookup, security decisions and outgoing packets are recording doubles.
This does not start a realm or a WoW client.
"""

import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    cxx,
    function,
    prepared_core,
    run_fixture,
    source_argument,
)


ROOT = Path(__file__).resolve().parents[2]


def native_contracts(core):
    quest = (core / 'src/server/game/Quests/QuestDef.h').read_text()
    player = (core / 'src/server/game/Entities/Player/PlayerQuest.cpp').read_text()
    player_header = (core / 'src/server/game/Entities/Player/Player.h').read_text()
    assert 'int32  RequiredNpcOrGo[QUEST_OBJECTIVES_COUNT]' in quest
    assert 'uint32 RequiredNpcOrGoCount[QUEST_OBJECTIVES_COUNT]' in quest
    assert 'uint32 RequiredItemId[QUEST_ITEM_OBJECTIVES_COUNT]' in quest
    assert 'uint32 RequiredItemCount[QUEST_ITEM_OBJECTIVES_COUNT]' in quest
    assert 'QuestStatusMap& getQuestStatusMap() { return m_QuestStatus; }' in player_header
    assert 'GetQuestSlotQuestId(uint16 slot) const' in player_header

    # These counters are updated by the native kill/item/event producers and
    # are the same counters used by CanCompleteQuest, including kill-credit IDs.
    kills = function(player, 'void Player::KilledMonsterCredit(')
    assert 'reqkill == real_entry' in kills
    assert 'q_status.CreatureOrGOCount[j] = curkillcount + addkillcount;' in kills
    assert 'qInfo->RequiredNpcOrGo[j] <= 0' in kills
    complete = function(player, 'bool Player::CanCompleteQuest(')
    assert 'q_status.ItemCount[i] < qInfo->RequiredItemCount[i]' in complete
    assert 'q_status.CreatureOrGOCount[i] < qInfo->RequiredNpcOrGoCount[i]' in complete
    assert 'q_status.PlayerCount < qInfo->GetPlayersSlain()' in complete
    assert '!q_status.Explored' in complete
    assert 'GetRepObjectiveFaction()' in complete and 'GetRepObjectiveValue()' in complete
    assert 'GetRewOrReqMoney() < 0' in complete
    explore = function(player, 'void Player::AreaExploredOrEventHappens(')
    assert 'q_status->Explored = true;' in explore

    # Chat requests and periodic snapshots both run outside parallel map jobs.
    opcodes = (core / 'src/server/game/Server/Protocol/Opcodes.cpp').read_text()
    chat_opcode = next(line for line in opcodes.splitlines() if 'DEFINE_HANDLER(CMSG_MESSAGECHAT,' in line)
    assert 'PROCESS_THREADUNSAFE' in chat_opcode
    world = (core / 'src/server/game/World/World.cpp').read_text()
    update = function(world, 'void World::Update(')
    assert update.index('sMapMgr->Update(diff);') < update.index('sScriptMgr->OnWorldUpdate(diff);')
    maps = (core / 'src/server/game/Maps/MapMgr.cpp').read_text()
    assert 'm_updater.wait();' in function(maps, 'void MapMgr::Update(')
    accessor = (core / 'src/server/game/Globals/ObjectAccessor.cpp').read_text()
    assert 'HashMapHolder<Player>::Find(guid)' in function(accessor, 'Player* ObjectAccessor::FindConnectedPlayer(')
    sessions = (core / 'src/server/game/Server/WorldSession.cpp').read_text()
    assert 'return !m_Socket || !m_Socket->IsOpen();' in function(sessions, 'bool WorldSession::IsSocketClosed(')

    sizes = '\n'.join(re.findall(
        r'^#define (?:MAX_QUEST_LOG_SIZE|QUEST_OBJECTIVES_COUNT|QUEST_ITEM_OBJECTIVES_COUNT) [^\n]+',
        quest, re.MULTILINE))
    return sizes + '\n' + '\n'.join(function(quest, signature) + ';' for signature in (
        'enum QuestStatus : uint8', 'enum QuestSpecialFlags', 'struct QuestStatusData'))


def extract_production(bridge, core):
    ai = (core / 'modules/mod-playerbots/src/Bot/PlayerbotAI.cpp').read_text()
    visible = function(bridge, 'std::vector<Player*> GetBridgeVisibleBots(Player* player)\n')
    assert 'GetPlayerbotMgr(player)' in visible and 'mgr->GetPlayerBotsBegin()' in visible
    assert 'CanExposeRandomHolderBot(player, bot)' in visible
    assert '!bot->IsInWorld()' in function(bridge, 'void AppendBridgeVisibleBot(')
    block = bridge[bridge.index('// MB_QUEST_PROGRESS_V1_BEGIN'):bridge.index('// MB_QUEST_PROGRESS_V1_END')]
    dispatch = function(bridge, '        if (requestType == "QUEST_PROGRESS")')
    script = function(bridge, 'class MultiBotBridgeWorldScript')
    assert 'void OnUpdate(uint32 diff) override' in script and 'UpdateQuestProgress(diff);' in script
    assert 'new MultiBotBridgeWorldScript();' in function(bridge, 'void AddSC_multibot_bridge(')
    assert 'kQuestProgressCapability = "QUEST_PROGRESS_V1";' in bridge
    assert 'kQuestProgressPushCapability = "QUEST_PROGRESS_PUSH_V1";' in bridge
    assert 'kQuestProgressCapability,' in function(bridge, 'bool SendCapabilitiesPackets(')
    assert 'kQuestProgressPushCapability,' in function(bridge, 'bool SendCapabilitiesPackets(')
    helpers = '\n'.join(function(bridge, signature) for signature in (
        'std::string Trim(', 'std::vector<std::string> SplitFields(', 'bool HasControlCharacter(',
        'bool IsValidRawField(', 'bool IsValidCanonicalRawField(', 'bool IsValidRequestToken(',
        'std::string GetSafeErrorToken(', 'std::string UrlEncodeField(',
        'std::size_t GetAddonWireLength(', 'bool IsAddonPacketWithinBudget(',
        'PlayerbotAI* GetBotAI(Player* bot)\n',
        'bool IsBotInRequesterGroup(Player* requester, Player* bot)\n',
        'Player* FindBotByName(Player* player, std::string const& botName)\n',
    ))
    return '\n'.join([
        function((core / 'src/server/game/Entities/Object/ObjectGuid.cpp').read_text(),
                 'std::string ObjectGuid::ToString() const'),
        function(ai, 'bool IsRealPlayer('), function(ai, 'bool IsSelfBot('), helpers, block,
        'bool DispatchQuestProgress(Player* player, std::vector<std::string> const& fields)\n{\n'
        '    std::string const normalized = "GET";\n'
        '    std::string const requestType = fields.empty() ? "" : fields[0];\n'
        + dispatch + '\n    return false;\n}\n',
    ])


def mutations(production):
    replacements = [
        ('native-counters', 'data.CreatureOrGOCount[i], quest->RequiredNpcOrGoCount[i]',
         '0, quest->RequiredNpcOrGoCount[i]'),
        ('group-access', '!IsBotInRequesterGroup(requester, bot)', 'false'),
        ('security-access', 'ai->GetSecurity()->CheckLevelFor(PLAYERBOT_SECURITY_ALLOW_ALL, true, requester)', 'true'),
        ('selfbot-isolation', 'IsRealPlayer(bot) || IsSelfBot(bot)', 'IsRealPlayer(bot)'),
        ('packet-budget', 'if (!IsAddonPacketWithinBudget(packet.first, packet.second))',
         'if (!IsAddonPacketWithinBudget(packet.first, packet.second) && false)'),
        ('unchanged-silence', 'if (watch.snapshot != cached->second &&', 'if (true &&'),
        ('snapshot-reuse', 'if (cached == snapshots.end())', 'if (true)'),
        ('coalescing', 'if (elapsed < 1000)', 'if (elapsed < 1)'),
        ('watch-cleanup', 'it = state.watches.erase(it);', '++it;'),
        ('watch-lease', 'now >= watch.expires ||', 'false ||'),
        ('idle-cleanup', 'if (now - state.lastSeen >= std::chrono::seconds(180))', 'if (false)'),
        ('visibility-access', '!visibleBots.contains(it->first)', 'false'),
        ('watch-bounds', 'state.watches.size() >= 40', 'state.watches.size() >= 41'),
        ('request-bounds', '++state.requests > 80', '++state.requests > 81'),
        ('requester-bounds', 'questProgressRequesters.size() >= 512', 'questProgressRequesters.size() >= 513'),
        ('bot-rate', 'now - last->second < std::chrono::seconds(1)', 'now - last->second < std::chrono::seconds(0)'),
        ('mode-validation', 'fields[3] != "WATCH" && fields[3] != "UNWATCH"', 'false'),
    ]
    for label, before, after in replacements:
        if production.count(before) != 1:
            raise AssertionError(label + ' mutation must change one production gate')
        yield label, production.replace(before, after), False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source_argument(parser, 'core', help='prepared core source directory')
    parser.add_argument('--bridge', type=Path, help='MultiBotBridge.cpp override')
    args = parser.parse_args()
    core = args.core or prepared_core(ROOT)
    bridge_path = args.bridge or core / 'modules/mod-multibot-bridge/src/MultiBotBridge.cpp'
    bridge = bridge_path.read_text()
    native = native_contracts(core)
    template = (Path(__file__).parent / 'QuestProgressBridgeFixture.cpp').read_text()
    production = extract_production(bridge, core)
    fixture = template.replace('@NATIVE_QUEST@', native)
    with tempfile.TemporaryDirectory(prefix='quest-progress-bridge-') as directory:
        directory = Path(directory)
        for label, body, valid in [('production', production, True), *mutations(production)]:
            source = directory / (label + '.cpp')
            executable = directory / label
            source.write_text(fixture.replace('@PRODUCTION@', body))
            subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-g',
                            *SANITIZER_FLAGS, str(source), '-o', str(executable)], check=True)
            result = run_fixture([str(executable)],
                                 env={**os.environ, 'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'})
            if valid:
                if result.returncode:
                    raise AssertionError(result.stderr or result.stdout)
                print(result.stdout.strip(), flush=True)
            elif result.returncode == 0:
                raise AssertionError('Quest progress fixture did not reject ' + label)
            elif 'Assertion' not in result.stderr:
                raise AssertionError(label + ' failed outside a fixture assertion: ' + result.stderr)
            else:
                print('Quest progress mutation rejected: ' + label, flush=True)


if __name__ == '__main__':
    main()
