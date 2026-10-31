"""Run the bridge's read-only Individual Progression endpoint against native-shaped state.

The fixture compiles the actual bridge endpoint, its progression translation
unit and Individual Progression's own progression functions. Native acceptance
checks, visibility scripts, map gates and packet routing are checked against
the prepared sources; world data, map checks and outgoing packets are
recording doubles. This does not start a realm or a WoW client.
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
    in_parallel,
    prepared_core,
    run_fixture,
    source_argument,
    sql_rows,
)


def normalized(text):
    return re.sub(r'\s+', ' ', text).strip()


def silent(body):
    """A check's body without the statements and blocks it runs only when msg is set."""
    body = re.sub(r'if \(msg\)\s*\{[^{}]*\}', '', body)
    return re.sub(r'if \(msg\)\s*[^;{]*;', '', body)


def visibility_rules(awareness):
    """Each Individual Progression visibility script and its rule after the GM and module exceptions."""
    rules = {}
    for match in re.finditer(r'class (\w+) : public (?:GameObject|Creature)Script(.*?)\n};', awareness, re.DOTALL):
        name, body = match.groups()
        seen = normalized(function(body, 'bool CanBeSeen(Player const* player) override'))
        bypass, rule = re.fullmatch(
            r'bool CanBeSeen\(Player const\* player\) override \{ if \((.*?)\) return true; '
            r'Player\* target = ObjectAccessor::FindConnectedPlayer\(player->GetGUID\(\)\); (.*) \}', seen).groups()
        exceptions = [term.strip() for term in bypass.split('||')]
        assert exceptions[0] == 'player->IsGameMaster()', name
        extra = [term for term in exceptions[1:] if term != '!sIndividualProgression->enabled']
        tier = re.fullmatch(r'uint32 PLAYER_PROGRESSION = (.*?); ProgressionState (\w+) = (.*?); '
                            r'if \(PLAYER_PROGRESSION >= \2\) return true; else return false;', rule)
        if tier:
            expression = f'{tier.group(1)} >= {tier.group(3)}'
        else:
            expression = re.fullmatch(r'if \((.*)\) return true; else return false;', rule).group(1)
        rules[name] = ' || '.join(extra + [expression])
    assert len(rules) == 29 and 'npc_ipp_tbc' in rules and 'gobject_ipp_wotlk' in rules
    return rules


def native_contracts(core):
    quest = (core / 'src/server/game/Quests/QuestDef.h').read_text()
    player = (core / 'src/server/game/Entities/Player/PlayerQuest.cpp').read_text()
    storage = (core / 'src/server/game/Entities/Player/PlayerStorage.cpp').read_text()
    settings = (core / 'src/server/game/Entities/Player/PlayerSettings.cpp').read_text()
    chat = (core / 'src/server/game/Chat/Chat.h').read_text()
    conditions = (core / 'src/server/game/Conditions/ConditionMgr.cpp').read_text()
    disables = (core / 'src/server/game/Conditions/DisableMgr.cpp').read_text()
    creature = (core / 'src/server/game/Entities/Creature/Creature.cpp').read_text()
    gameobject = (core / 'src/server/game/Entities/GameObject/GameObject.cpp').read_text()
    spawns = (core / 'src/server/game/Maps/SpawnData.h').read_text()
    map_ids = (core / 'src/server/game/Maps/AreaDefines.h').read_text()
    object_mgr = (core / 'src/server/game/Globals/ObjectMgr.cpp').read_text()
    maps = (core / 'src/server/game/Maps/MapMgr.cpp').read_text()
    commands = (core / 'src/server/scripts/Commands/cs_quest.cpp').read_text()
    session = (core / 'src/server/game/Server/WorldSession.cpp').read_text()
    inspect = (core / 'src/server/game/Handlers/MiscHandler.cpp').read_text()
    bot_ai = (core / 'modules/mod-playerbots/src/Bot/PlayerbotAI.cpp').read_text()
    # Altbots have server-side sessions without a socket; only the requester needs a live socket.
    assert 'return !m_Socket || !m_Socket->IsOpen();' in function(session, 'bool WorldSession::IsSocketClosed() const')
    assert '!sRandomPlayerbotMgr.IsRandomBot(bot) && !IsSelfBot(bot)' in function(bot_ai, 'bool PlayerbotAI::IsAltBot()')
    native_inspect = function(inspect, 'void WorldSession::HandleInspectOpcode(')
    assert 'IsWithinDistInMap(player, INSPECT_DISTANCE, false)' in native_inspect
    assert 'IsValidAttackTarget(player)' in native_inspect
    factory = (core / 'modules/mod-playerbots/src/Bot/Factory/AiFactory.cpp').read_text()
    effective = function(factory, 'std::string AiFactory::GetEffectiveCombatProfile(')
    assert 'std::string mode = GetCombatProfile(player);' in effective and 'return mode;' in effective
    assert '{"auto", "assassin", "combat", "subtlety"}' in function(factory, 'std::vector<std::string> AiFactory::GetCombatProfiles(')
    unit = (core / 'src/server/game/Entities/Unit/Unit.h').read_text()
    assert 'bool CanDualWield() const { return _dualWieldMode == DualWieldMode::ENABLED; }' in unit
    module = core / 'modules/mod-individual-progression/src'
    header = (module / 'IndividualProgression.h').read_text()
    progression = (module / 'IndividualProgression.cpp').read_text()
    players = (module / 'IndividualProgressionPlayer.cpp').read_text()
    policy = (module / 'StrictEarnedProgressionPolicy.h').read_text()

    # CanTakeQuest is the sum of the checks the endpoint names; each sends text only with msg.
    take = normalized(function(player, 'bool Player::CanTakeQuest('))
    for check in ('SatisfyQuestStatus', 'SatisfyQuestExclusiveGroup', 'SatisfyQuestClass', 'SatisfyQuestRace',
                  'SatisfyQuestLevel', 'SatisfyQuestSkill', 'SatisfyQuestReputation', 'SatisfyQuestPreviousQuest',
                  'SatisfyQuestTimed', 'SatisfyQuestNextChain', 'SatisfyQuestPrevChain', 'SatisfyQuestBreadcrumb',
                  'SatisfyQuestDay', 'SatisfyQuestWeek', 'SatisfyQuestMonth', 'SatisfyQuestSeasonal',
                  'SatisfyQuestConditions'):
        assert f'{check}(quest, msg)' in take, check
        assert 'Send' not in silent(function(player, f'bool Player::{check}(')), check
    assert '!sDisableMgr->IsDisabledFor(DISABLE_TYPE_QUEST, quest->GetQuestId(), this)' in take
    assert 'Send' not in silent(function(player, 'bool Player::SatisfyQuestLog('))
    level = function(player, 'bool Player::SatisfyQuestLevel(')
    assert 'GetLevel() < qInfo->GetMinLevel()' in level and 'GetLevel() > qInfo->GetMaxLevel()' in level
    breadcrumb = function(player, 'bool Player::SatisfyQuestBreadcrumb(')
    assert 'qInfo->GetBreadcrumbForQuestId()' in breadcrumb
    assert 'status != QUEST_STATUS_NONE || IsQuestRewarded(breadcrumbForQuestId)' in breadcrumb
    # The diagnostics command reads the same quest-available conditions row by row.
    assert 'GetConditionsForNotGroupedEntry(CONDITION_SOURCE_TYPE_QUEST_AVAILABLE, entry)' in commands
    rewarded = function(conditions, 'bool Condition::Meets(')
    assert 'condMeets = player->GetQuestRewardStatus(ConditionValue1);' in rewarded
    assert 'if (NegativeCondition)\n        condMeets = !condMeets;' in rewarded
    assert 'return IsQuestRewarded(quest_id);' in function(player, 'bool Player::GetQuestRewardStatus(')

    # Satisfy only reports with report=true, except for a map disabled at the player's difficulty.
    satisfy = function(storage, 'bool Player::Satisfy(')
    disabled = 'if (sDisableMgr->IsDisabledFor(DISABLE_TYPE_MAP, target_map, this))\n        {\n            GetSession()->SendAreaTriggerMessage(LANG_INSTANCE_CLOSED);'
    assert disabled in satisfy
    after = satisfy[satisfy.index(disabled) + len(disabled):]
    assert after.count('if (report)') == 1
    report = after[after.index('if (report)'):]
    assert 'Send' not in after[:after.index('if (report)')]
    assert report.count('Send') + report.count('ChatHandler') > 0
    modules = core / 'modules'
    assert not any('OnPlayerNotAvoidSatisfy' in path.read_text(errors='replace')
                   for path in modules.rglob('*.cpp')), 'a module overrides access requirements'
    # The portal's own checks end with the same access requirement lookup.
    assert 'player->Satisfy(sObjectMgr->GetAccessRequirement(mapid, targetDifficulty), mapid, true)' in \
        function(maps, 'Map::EnterState MapMgr::PlayerCannotEnter(')
    disable_check = function(disables, 'bool DisableMgr::IsDisabledFor(')
    assert 'targetDifficulty = Difficulty(flags);' in disable_check

    # Spawn and template script ids follow the native resolution.
    assert 'creatureData->ScriptId && entry == creatureData->id' in function(creature, 'uint32 Creature::GetScriptId() const')
    assert 'return GetGOInfo()->ScriptId;' in function(gameobject, 'uint32 GameObject::GetScriptId() const')
    for field in ('uint16 mapid{0};', 'float posX{0.0f};', 'float posY{0.0f};', 'float posZ{0.0f};'):
        assert field in spawns, field
    assert re.search(r'MAP_OUTLAND\s*= 530,', map_ids) and re.search(r'MAP_NORTHREND\s*= 571,', map_ids)
    assert 'int32  GetZoneOrSort() const { return ZoneOrSort; }' in quest
    assert 'data.mapid              = fields[2].Get<uint16>();' in object_mgr
    assert 'struct CreatureData : public SpawnData' in (core / 'src/server/game/Entities/Creature/CreatureData.h').read_text()
    assert 'struct GameObjectData : public SpawnData' in (core / 'src/server/game/Entities/GameObject/GameObjectData.h').read_text()
    hellfire = sql_rows(core, 'quest_template', {10055})[0]
    starter = sql_rows(core, 'creature_queststarter', {21209})
    spawn = sql_rows(core, 'creature', {74397})[0]
    assert any(row['quest'] == '10055' for row in starter)
    assert hellfire['QuestLevel'] == '61' and hellfire['MinLevel'] == '58' and hellfire['QuestSortID'] == '3483'
    assert spawn['id1'] == '21209' and spawn['map'] == '530' and spawn['phaseMask'] == '1'
    source_data = '\n'.join(
        f'constexpr {kind} {name} = {row[field]}{suffix};' for kind, name, row, field, suffix in (
            ('uint32', 'NativeHellfireMinLevel', hellfire, 'MinLevel', ''),
            ('int32', 'NativeHellfireZone', hellfire, 'QuestSortID', ''),
            ('uint16', 'NativeHellfireMap', spawn, 'map', ''),
            ('float', 'NativeHellfireX', spawn, 'position_x', 'f'),
            ('float', 'NativeHellfireY', spawn, 'position_y', 'f'),
            ('float', 'NativeHellfireZ', spawn, 'position_z', 'f'),
        ))

    # The milestone getter of boss credits writes a missing setting.
    assert 'UpdatePlayerSetting(source, index, 0);' in function(settings, 'PlayerSetting Player::GetPlayerSetting(')
    milestone = function(progression, 'bool IndividualProgression::HasStrictEarnedMilestone(')
    assert milestone.index('case PROGRESSION_PRE_TBC:') < milestone.index('default:') < milestone.index('GetPlayerSetting')
    for stage in range(1, 19):
        quest_stage = stage in (4, 5, 8)
        credit = re.search(rf'case {stage}:', function(policy, 'constexpr std::uint32_t BossCredit(')) is not None
        assert quest_stage != credit or stage == 11, stage

    # A null-session map check sends no refusal text and starts no ship teleport.
    assert 'if (HasSession())' in function(chat, 'void PSendSysMessage(char const* fmt, Args&&... args)')
    gate = function(players, 'static bool CanEnterMap(Player* player, uint32 mapid, float x, float y, float z, WorldSession* session)')
    assert 'ChatHandler(player->GetSession())' not in gate
    assert gate.index('if (!session)\n                return false;') < gate.index('TeleportTo')
    assert 'if (mapid == MAP_OUTLAND)' in gate and \
        '!sIndividualProgression->hasPassedProgression(player, PROGRESSION_PRE_TBC)' in gate
    assert 'if (mapid == MAP_NORTHREND && !sIndividualProgression->hasPassedProgression(player, PROGRESSION_TBC_TIER_5))' in gate
    assert 'return IsTBCRaceStartingZone(mapid, x, y, z);' in gate
    assert 'sMapMgr->GetZoneId(0, mapid, x, y, z)' in gate
    assert 'return IndividualPlayerProgression::CanEnterMap(player, mapId, x, y, z, nullptr);' in \
        function(players, 'bool IndividualProgression::CanEnterMap(')
    assert 'return CanEnterMap(player, mapid, x, y, z, player ? player->GetSession() : nullptr);' in players

    # The realm limit clamps passed stages; markers are rewarded quests 66001-66018.
    assert 'if (progressionLimit && (state > progressionLimit))' in \
        function(progression, 'bool IndividualProgression::hasPassedProgression(')
    assert 'uint32 PROGRESSION_QUEST = 66000 + i;' in \
        function(progression, 'uint8 IndividualProgression::GetPlayerProgressionFromQuests(')
    assert 'PROGRESSION_WOTLK_TIER_5    = 18' in header

    sizes = '\n'.join(function(source, signature) + ';' for source, signature in (
        (quest, 'enum QuestStatus : uint8'),
        (header, 'enum ProgressionState : uint8'),
        (header, 'enum ProgressionQuestIDs'),
    ))
    production = '\n'.join(function(progression, signature) for signature in (
        'uint8 IndividualProgression::GetPlayerProgressionFromQuests(',
        'bool IndividualProgression::IsStrictDefaultProgression(',
        'uint8 IndividualProgression_GetEarnedEra(',
        'bool IndividualProgression::HasStrictEarnedMilestone(',
        'bool IndividualProgression::hasPassedProgression(',
        'bool IndividualProgression::isBeforeProgression(',
        'bool IndividualProgression::isExcludedAccount(Player* player)',
        'bool IndividualProgression::isBotAccount(const Player* player)',
    ))
    return re.sub(r'^#.*$', '', policy, flags=re.MULTILINE) + '\n' + sizes + '\n' + source_data, production


def extract_production(bridge, unit, header, awareness):
    rules = visibility_rules(awareness)
    table = function(unit, 'std::map<std::string, IpVisibilityRule, std::less<>> const& IpVisibilityRules()')
    found = dict(re.findall(r'\{"(\w+)", \[\]\(Player\* target\) \{ return (.*?); \}\},', table))
    assert found == rules, sorted(set(found.items()) ^ set(rules.items()))

    assert 'kIpProgressCapability = "IP_PROGRESS_V1";' in bridge
    assert 'kIpProgressCapability,' in function(bridge, 'bool SendCapabilitiesPackets(')
    assert 'kIpTargetCapability = "IP_TARGET_V1";' in bridge
    assert 'kIpTargetCapability,' in function(bridge, 'bool SendCapabilitiesPackets(')
    assert 'std::size_t constexpr kMaxEncodedFieldLength = 192;' in bridge
    assert 'UpdateIpProgress(diff);' in function(bridge, 'class MultiBotBridgeWorldScript')
    assert '#include "MultiBotBridgeProgression.h"' in bridge
    assert 'IndividualProgression.h' not in bridge, 'Playerbots and IP headers both declare GENERAL'
    block = bridge[bridge.index('// MB_IP_PROGRESS_V1_BEGIN'):bridge.index('// MB_IP_PROGRESS_V1_END')]
    dispatch = function(bridge, '        if (requestType == "IP_STATE" || requestType == "IP_QUESTS" || requestType == "IP_ACCESS")')
    clock = re.search(r'^using QuestProgressClock = .*;$', bridge, re.MULTILINE).group(0)
    helpers = '\n'.join(function(bridge, signature) for signature in (
        'std::string Trim(', 'std::vector<std::string> SplitFields(', 'bool HasControlCharacter(',
        'bool IsValidRawField(', 'bool IsValidCanonicalRawField(', 'bool IsValidRequestToken(',
        'std::string GetSafeErrorToken(', 'std::size_t GetAddonWireLength(', 'bool IsAddonPacketWithinBudget(',
        'bool TryParseUint32Field(', 'int HexDigitValue(', 'bool TryUrlDecodeField(',
    ))
    declarations = header[header.index('namespace MultiBotBridgeProgression'):header.rindex('#endif')]
    body = re.sub(r'^#include .*$', '', unit, flags=re.MULTILINE)
    body = re.sub(r'#if __has_include\("IndividualProgression.h"\).*?#endif\n', '', body, flags=re.DOTALL)
    return '\n'.join([
        declarations, body, clock, helpers, block,
        'bool Dispatch(Player* player, std::vector<std::string> const& fields)\n{\n'
        '    std::string const normalized = "GET";\n'
        '    std::string const requestType = fields.empty() ? "" : fields[0];\n'
        + dispatch + '\n    return false;\n}\n',
    ])


def mutations(production):
    replacements = [
        ('realm-limit', 'effective = limit && stored > limit ? limit : stored;', 'effective = stored;'),
        ('boss-credit-read', 'if (next && !StrictEarnedProgressionPolicy::BossCredit(uint8(next)))', 'if (next)'),
        ('reserved-stage', 'next = StrictEarnedProgressionPolicy::NextStage(uint8(stored));', 'next = stored + 1;'),
        ('giver-visibility', 'rule == IpVisibilityRules().end() || rule->second(player)', 'rule == IpVisibilityRules().end()'),
        ('giver-phase', '!(spawn.phaseMask & PHASEMASK_NORMAL) ||', ''),
        ('giver-unspawned', 'if (entrySpawns == spawns.end())\n                return false;',
         'if (entrySpawns == spawns.end())\n                continue;'),
        ('giver-alternative', '                    return false;\n            }\n            hidden = true;',
         '                    continue;\n            }\n            hidden = true;'),
        ('giver-gm', 'sIndividualProgression->enabled && !player->IsGameMaster() && IsIpQuestGiverHidden',
         'sIndividualProgression->enabled && IsIpQuestGiverHidden'),
        ('spawn-script', 'data.ScriptId && entry == data.id ?', 'data.ScriptId ?'),
        ('tier-condition', '!condition->Meets(source)', 'true'),
        ('tier-sign', "(condition->NegativeCondition ? -1 : 1)", '1'),
        ('breadcrumb-kind', 'IP_QUEST_BREADCRUMB_DONE : IP_QUEST_BREADCRUMB_ACTIVE', 'IP_QUEST_BREADCRUMB_ACTIVE : IP_QUEST_BREADCRUMB_ACTIVE'),
        ('ip-map-gate', 'return \'G\';', "return 'A';"),
        ('silent-satisfy', 'if (!silent || sDisableMgr', 'if (sDisableMgr'),
        ('access-report', 'mapId, false) ? \'A\' : \'R\';', "mapId, true) ? 'A' : 'R';"),
        ('watch-change', 'if (state != requester.watched)', 'if (true)'),
        ('watch-cadence', 'if (elapsed < 1000)', 'if (elapsed < 1)'),
        ('watch-lease', 'if (!requester.watchToken.empty() && now >= requester.watchExpires)', 'if (false)'),
        ('watch-owner', 'if (requester.watchToken == token)', 'if (true)'),
        ('idle-cleanup', 'now - requester.lastSeen >= std::chrono::seconds(180)', 'false'),
        ('request-bounds', '++requester.requests > 20', '++requester.requests > 21'),
        ('requester-bounds', 'ipProgressRequesters.size() >= 512', 'ipProgressRequesters.size() >= 513'),
        ('quest-bounds', 'items.size() >= 32', 'items.size() >= 33'),
        ('quest-empty', 'if (items.empty())\n        {', 'if (false)\n        {'),
        ('packet-budget', 'if (!IsAddonPacketWithinBudget(opcode, header + chunk))', 'if (false)'),
        ('reply-self', 'ChatMsg const replyType = CHAT_MSG_WHISPER;', 'ChatMsg const replyType = 2;'),
        ('mode-validation', 'fields[2] != "WATCH" && fields[2] != "UNWATCH"', 'false'),
        ('target-tag', 'fields[baseCount] == "BOT"', 'true'),
        ('target-inworld', '!target->IsInWorld() || ', ''),
        ('requester-inworld', '!requester->IsInWorld() || ', ''),
        ('requester-socket', 'requester->GetSession()->IsSocketClosed() ||', 'false ||'),
        ('target-self', 'target == requester || ', ''),
        ('target-session', '!target->GetSession() ||', 'false ||'),
        ('target-group', 'target->GetGroup() != requester->GetGroup() ||', 'false ||'),
        ('requester-group', '!requester->GetGroup() ||', 'false ||'),
        ('target-distance', '!requester->IsWithinDistInMap(target, INSPECT_DISTANCE, false)', 'false'),
        ('target-hostile', 'requester->IsValidAttackTarget(target)', 'false'),
        ('target-altbot', 'ai->IsAltBot() && ', ''),
        ('target-master', 'ai->GetMaster() == requester', 'true'),
        ('target-name', 'targetName != Trim(targetName)', 'false'),
        ('target-state-subject', 'MultiBotBridgeProgression::State(subject)', 'MultiBotBridgeProgression::State(player)'),
        ('target-quest-subject', 'MultiBotBridgeProgression::Quest(subject, questId, subject != player)',
         'MultiBotBridgeProgression::Quest(player, questId, subject != player)'),
        ('target-source-scope', 'MultiBotBridgeProgression::Quest(subject, questId, subject != player)',
         'MultiBotBridgeProgression::Quest(subject, questId, false)'),
        ('own-source-scope', 'MultiBotBridgeProgression::Quest(subject, questId, subject != player)',
         'MultiBotBridgeProgression::Quest(subject, questId, true)'),
        ('source-map-gate', 'if (!sIndividualProgression->CanEnterMap(player, spawn.mapId, spawn.x, spawn.y, spawn.z))', 'if (false)'),
        ('source-coordinates', 'CanEnterMap(player, spawn.mapId, spawn.x, spawn.y, spawn.z)',
         'CanEnterMap(player, spawn.mapId, 0.0f, 0.0f, 0.0f)'),
        ('source-visibility', 'if (rule != IpVisibilityRules().end() && !rule->second(player))', 'if (false)'),
        ('source-phase', 'if (!(spawn.phaseMask & PHASEMASK_NORMAL))', 'if (false)'),
        ('source-unknown', "return unknown || !known ? 'U' : 'L';", "return 'A';"),
        ('source-active-quest', 'if (forSource)\n    {', 'if (forSource && player->GetQuestStatus(questId) == QUEST_STATUS_NONE)\n    {'),
        ('source-rewarded', 'if (player->GetQuestStatus(questId) == QUEST_STATUS_REWARDED)', 'if (false)'),
        ('source-default', 'bool forSource = false', 'bool forSource = true'),
        ('source-map-known', 'if (!sMapStore.LookupEntry(spawn.mapId))', 'if (false)'),
        ('source-map-disabled', 'if (!sDisableMgr->IsDisabledFor(DISABLE_TYPE_MAP, spawn.mapId, player))', 'if (true)'),
        ('source-creature-map', 'data.ScriptId : creature->ScriptID, data.phaseMask, data.mapid,',
         'data.ScriptId : creature->ScriptID, data.phaseMask, 0,'),
        ('source-object-map', 'data.phaseMask, data.mapid, data.posX, data.posY, data.posZ});',
         'data.phaseMask, 0, data.posX, data.posY, data.posZ});'),
        ('target-access-subject', 'MultiBotBridgeProgression::Access(subject)', 'MultiBotBridgeProgression::Access(player)'),
        ('target-metadata-scope', 'if (subject != player)', 'if (true)'),
        ('target-profile-subject', 'AiFactory::GetEffectiveCombatProfile(subject)', 'AiFactory::GetEffectiveCombatProfile(player)'),
        ('target-dual-wield', 'subject->CanDualWield() ? "1" : "0"', 'player->CanDualWield() ? "1" : "0"'),
    ]
    for label, before, after in replacements:
        if production.count(before) != 1:
            raise AssertionError(label + ' mutation must change one production gate')
        yield label, production.replace(before, after), False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source_argument(parser, 'core', help='prepared core source directory')
    args = parser.parse_args()
    core = args.core or prepared_core()
    bridge_source = core / 'modules/mod-multibot-bridge/src'
    bridge = (bridge_source / 'MultiBotBridge.cpp').read_text()
    unit = (bridge_source / 'MultiBotBridgeProgression.cpp').read_text()
    header = (bridge_source / 'MultiBotBridgeProgression.h').read_text()
    awareness = (core / 'modules/mod-individual-progression/src/IndividualProgressionAwareness.cpp').read_text()
    native, individual_progression = native_contracts(core)
    production = extract_production(bridge, unit, header, awareness)
    template = (Path(__file__).parent / 'IpProgressBridgeFixture.cpp').read_text()
    fixture = template.replace('@NATIVE@', native).replace('@INDIVIDUAL_PROGRESSION@', individual_progression)
    builds = [('production', production, True, True), ('without-module', production, True, False)]
    builds += [(label, body, valid, True) for label, body, valid in mutations(production)]
    with tempfile.TemporaryDirectory(prefix='ip-progress-bridge-') as directory:
        def build_and_run(build):
            label, body, valid, module = build
            source = Path(directory) / (label + '.cpp')
            executable = Path(directory) / label
            source.write_text(('#define MBB_WITH_INDIVIDUAL_PROGRESSION 1\n' if module else '')
                              + fixture.replace('@PRODUCTION@', body))
            # Mutants may leave a parameter unused; only the production build treats warnings as errors.
            compiled = subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', *(['-Werror'] if valid else []),
                                       '-g', *SANITIZER_FLAGS, str(source), '-o', str(executable)],
                                      capture_output=True, text=True, check=False)
            if compiled.returncode:
                raise AssertionError(label + ' does not compile: ' + compiled.stderr)
            return run_fixture([str(executable)],
                               env={**os.environ, 'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'})

        for (label, _, valid, _), result in zip(builds, in_parallel(build_and_run, builds)):
            if valid:
                if result.returncode:
                    raise AssertionError(label + ': ' + (result.stderr or result.stdout))
                print(result.stdout.strip(), flush=True)
            elif result.returncode == 0:
                raise AssertionError('IP progress fixture did not reject ' + label)
            elif 'Assertion' not in result.stderr:
                raise AssertionError(label + ' failed outside a fixture assertion: ' + result.stderr)
            else:
                print('IP progress mutation rejected: ' + label, flush=True)

if __name__ == '__main__':
    main()
