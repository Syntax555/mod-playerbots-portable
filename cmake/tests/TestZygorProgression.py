"""Run Zygor Guides Viewer's Individual Progression layer from the patched addon with Lua 5.1.

The Lua fixture loads the patched production files with recording doubles for
the client API and replies in the bridge's IP_PROGRESS_V1 wire format. The
module's tier, region, instance, milestone and reason tables are checked
against Individual Progression's, the bridge's and the core's own sources, and
the upstream Zygor regression suite runs against the patched addon. This does
not start a WoW client.
"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from FixtureSupport import (
    REPOSITORY,
    fork_change,
    git_apply,
    in_parallel,
    prepared_core,
    run_fixture,
    source_argument,
)


FIXTURE = Path(__file__).with_name('ZygorProgressionFixture.lua')
# The patched files the fixture loads.
FILES = (
    'IndividualProgression.lua', 'Parser.lua', 'Step.lua', 'Goal.lua', 'ZygorGuidesViewer.lua',
    'QuestAutoAccept.lua', 'Dungeons.lua', 'Data-WOTLK/Dungeons.lua', 'Item-GearFinder.lua',
    'Item-ItemScore.lua', 'Data-WOTLK/Item-Statweights.lua', 'ZygorTalentAdvisor/ZygorTalentAdvisor.lua', 'TalentAdvisorCompat.lua', 'Options.lua',
)
MODULE = 'IndividualProgression.lua'
TOOLS = '.module-cache/client-addon-ZygorGuidesViewerRM'


def lua_table(source, name):
    """The body of `IP.<name> = { ... }` in the module."""
    match = re.search(r'^IP\.' + name + r' = \{(.*?)^\}', source, re.MULTILINE | re.DOTALL)
    if not match:
        match = re.search(r'^IP\.' + name + r' = \{(.*?)\}$', source, re.MULTILINE)
    assert match, name
    return match.group(1)


def string_keys(body):
    return {key: int(value) for key, value in re.findall(r'\["([^"]+)"\]=(\d+)', body)}


def enum_values(header, prefix=''):
    return {name: int(value, 0) for name, value in re.findall(r'\b(' + prefix + r'\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)', header)}


def contracts(addon, core):
    """Tie the module's tables to the sources that decide the same rules."""
    module = (addon / MODULE).read_text()
    native_talents = (addon / 'ZygorTalentAdvisor/Registering.lua').read_text().split('["DRUID"]={', 1)[1]
    assert '["Thick Hide"]=794,' in native_talents.split('},', 1)[0]
    ip = core / 'modules/mod-individual-progression/src'
    header = (ip / 'IndividualProgression.h').read_text()
    player = (ip / 'IndividualProgressionPlayer.cpp').read_text()
    progression = (ip / 'IndividualProgression.cpp').read_text()
    policy = (ip / 'StrictEarnedProgressionPolicy.h').read_text()
    tiers = enum_values(header, 'PROGRESSION_')
    quests = enum_values(header)

    # Continent and zone gates of the module's map entry check.
    gates = {
        'PROGRESSION_PRE_TBC': r'if \(mapid == MAP_OUTLAND\)\s*\{\s*if \(!sIndividualProgression->hasPassedProgression\(player, PROGRESSION_PRE_TBC\)\)',
        'PROGRESSION_TBC_TIER_4': r'!sIndividualProgression->hasPassedProgression\(player, PROGRESSION_TBC_TIER_4\) && zoneId == AREA_ISLE_OF_QUEL_DANAS',
        'PROGRESSION_TBC_TIER_5': r'mapid == MAP_NORTHREND && !sIndividualProgression->hasPassedProgression\(player, PROGRESSION_TBC_TIER_5\)',
    }
    for tier, pattern in gates.items():
        assert re.search(pattern, player), f'Individual Progression no longer gates with {tier}'
    regions = string_keys(lua_table(module, 'REGIONS'))
    outland = {'Hellfire Peninsula', 'Zangarmarsh', 'Terokkar Forest', 'Nagrand', "Blade's Edge Mountains",
               'Netherstorm', 'Shadowmoon Valley', 'Shattrath City'}
    northrend = {'Borean Tundra', 'Howling Fjord', 'Dragonblight', 'Grizzly Hills', "Zul'Drak", 'Sholazar Basin',
                 'Crystalsong Forest', 'The Storm Peaks', 'Icecrown', 'Wintergrasp', 'Dalaran', "Hrothgar's Landing"}
    for zone in outland:
        assert regions[zone] == tiers['PROGRESSION_PRE_TBC'], zone
    assert regions["Isle of Quel'Danas"] == tiers['PROGRESSION_TBC_TIER_4']
    for zone in northrend:
        assert regions[zone] == tiers['PROGRESSION_TBC_TIER_5'], zone

    # The TBC race starting zones open for Draenei and Blood Elves only.
    assert 'player->getRace() != RACE_DRAENEI && player->getRace() != RACE_BLOODELF' in player
    starting = re.search(r'static bool IsTBCRaceStartingZone\(.*?return \((.*?)\);', player, re.DOTALL).group(1)
    names = {'AREA_AZUREMYST_ISLE': 'Azuremyst Isle', 'AREA_BLOODMYST_ISLE': 'Bloodmyst Isle',
             'AREA_GHOSTLANDS': 'Ghostlands', 'AREA_EVERSONG_WOODS': 'Eversong Woods', 'AREA_THE_EXODAR': 'The Exodar',
             'AREA_SILVERMOON_CITY': 'Silvermoon City', 'AREA_AMMEN_VALE': 'Ammen Vale', 'AREA_VEILED_SEA': 'The Veiled Sea'}
    areas = set(re.findall(r'zoneId == (AREA_\w+)', starting))
    assert areas == set(names), areas
    race_zones = set(re.findall(r'\["([^"]+)"\]=true', lua_table(module, 'TBC_RACE_ZONES')))
    assert {names[area] for area in areas} <= race_zones
    assert set(re.findall(r'(\w+)=true', lua_table(module, 'TBC_RACES'))) == {'Draenei', 'BloodElf'}

    # Experience stops at 60 before tier 8 and at 70 before tier 13.
    assert '!sIndividualProgression->hasPassedProgression(player, PROGRESSION_PRE_TBC) && player->GetLevel() >= 60' in player
    assert '!sIndividualProgression->hasPassedProgression(player, PROGRESSION_TBC_TIER_5) && player->GetLevel() >= 70' in player
    assert 'local cap = s.effective >= 13 and 80 or s.effective >= 8 and 70 or 60' in module
    assert tiers['PROGRESSION_PRE_TBC'] == 8 and tiers['PROGRESSION_TBC_TIER_5'] == 13

    # Gear Finder phases are the Wrath raid tiers.
    phases = dict(re.findall(r'(wotlk\d)=(\d+)', lua_table(module, 'PHASES')))
    expected = {'wotlk1': 'PROGRESSION_TBC_TIER_5', 'wotlk2': 'PROGRESSION_WOTLK_TIER_1',
                'wotlk3': 'PROGRESSION_WOTLK_TIER_2', 'wotlk4': 'PROGRESSION_WOTLK_TIER_3',
                'wotlk5': 'PROGRESSION_WOTLK_TIER_4'}
    assert {key: int(value) for key, value in phases.items()} == {key: tiers[name] for key, name in expected.items()}
    assert 'mapid == MAP_ULDUAR && !sIndividualProgression->hasPassedProgression(player, PROGRESSION_WOTLK_TIER_1)' in player
    dungeons = (addon / 'Data-WOTLK/Dungeons.lua').read_text()
    for map_id, phase in (('603', 'wotlk2'), ('649', 'wotlk3'), ('631', 'wotlk4'), ('724', 'wotlk5'), ('533', 'wotlk1')):
        assert re.search(r'\["' + map_id + r'_10"\][^\n]*phase="' + phase + '"', dungeons), map_id

    # 40-player Onyxia and Naxxramas run in the 10-player heroic slot.
    dbc = (core / 'src/server/shared/DataStores/DBCEnums.h').read_text()
    heroic = int(re.search(r'RAID_DIFFICULTY_10MAN_HEROIC\s*=\s*(\d+)', dbc).group(1))
    assert 'SetRaidDifficulty(RAID_DIFFICULTY_10MAN_HEROIC)' in (ip / 'vanillaScripts/instance_onyxias_lair.cpp').read_text()
    assert 'GetSpawnMode() == RAID_DIFFICULTY_10MAN_HEROIC' in (ip / 'naxx40Scripts/custom_scripts_40.cpp').read_text()
    assert dict(re.findall(r'\[(\d+)\]=(\d+)', lua_table(module, 'VANILLA_RAID_DIFFICULTY'))) == {'249': str(heroic), '533': str(heroic)}

    # Every instance the module names is a server instance map.
    templates = (core / 'data/sql/base/db_world/instance_template.sql').read_text()
    maps = {int(value) for value in re.findall(r'^\((\d+),', templates, re.MULTILINE)}
    instances = string_keys(lua_table(module, 'INSTANCES'))
    missing = {name: map_id for name, map_id in instances.items() if map_id not in maps}
    assert not missing, missing

    # The milestone chain: quest milestones, boss credits and the skipped tier 11.
    assert 'return current >= LastStage ? 0 : (current == 10 ? 12 : current + 1);' in policy
    credits = {int(stage) for stage in re.findall(r'case (\d+):', policy.split('BossCredit')[1].split('BossStage')[0])}
    # Creature entry -> stage whose kill credits it.
    bosses = {int(entry): int(stage) for entry, stage in
              re.findall(r'case (\d+):\s*return (\d+);', policy.split('BossStage')[1])}
    milestone_quests = {int(tier): int(quest) for tier, quest in
                        re.findall(r'\[(\d+)\]\s*=\s*\{quest=(\d+)', lua_table(module, 'MILESTONES'))}
    milestone_npcs = {int(tier): int(npc) for tier, npc in
                      re.findall(r'\[(\d+)\]\s*=\s*\{npc=(\d+)', lua_table(module, 'MILESTONES'))}
    assert set(milestone_npcs) == credits and 11 not in milestone_quests and 11 not in milestone_npcs
    strict = progression.split('bool IndividualProgression::HasStrictEarnedMilestone')[1].split('default:')[0]
    assert milestone_quests == {tiers['PROGRESSION_PRE_AQ']: quests['BANG_A_GONG'],
                                tiers['PROGRESSION_AQ_WAR']: quests['CHAOS_AND_DESTRUCTION'],
                                tiers['PROGRESSION_PRE_TBC']: quests['INTO_THE_BREACH']}
    for name in ('BANG_A_GONG', 'SIMPLY_BANG_A_GONG', 'CHAOS_AND_DESTRUCTION', 'INTO_THE_BREACH'):
        assert name in strict, name
    # The custom 40-player Onyxia and Kel'Thuzad entries display as the creatures they replace.
    for tier, npc in milestone_npcs.items():
        assert tier in (2, 7) or bosses.get(npc) == tier, (tier, npc)
    assert milestone_npcs[2] == quests['ONYXIA'] and milestone_npcs[7] == quests['KELTHUZAD']
    assert {tier for tier in bosses.values()} == credits

    # Transition quests stay manual.
    manual = {int(value) for value in re.findall(r'\[(\d+)\]=true', lua_table(module, 'MANUAL_QUESTS'))}
    assert manual == {quests[name] for name in ('BANG_A_GONG', 'SIMPLY_BANG_A_GONG', 'CHAOS_AND_DESTRUCTION', 'INTO_THE_BREACH')}

    # Reasons and state fields as the bridge sends them.
    bridge = core / 'modules/mod-multibot-bridge/src/MultiBotBridgeProgression.cpp'
    native = {name.removeprefix('IP_QUEST_'): value for name, value in enum_values(bridge.read_text(), 'IP_QUEST_').items()}
    reasons = {name: int(value, 16) for name, value in re.findall(r'(\w+) = (0x[0-9A-F]+)', lua_table(module, 'REASON'))}
    assert reasons == native, (reasons, native)
    fields = re.search(r'fields << 1 << .*?;', bridge.read_text(), re.DOTALL).group(0)
    order = re.findall(r"<< '~' << \(?(\w+)", fields)
    assert order[:9] == ['ip', 'strict', 'stored', 'effective', 'limit', 'era', 'next', 'nextMet', 'account'], order
    assert 'IP_STATE~token~1~ip~strict~stored~effective~limit~era~next~nextMet~account~gm~maxLevel' in module

    # Every effective native bot profile maps to the existing Zygor build order.
    factory = (core / 'modules/mod-playerbots/src/Bot/Factory/AiFactory.cpp').read_text()
    native_profiles = re.search(r'AiFactory::GetCombatProfiles\(.*?\n\}', factory, re.DOTALL).group(0)
    finder = (addon / 'Item-GearFinder.lua').read_text()
    client_profiles = re.search(r'local PROFILE_BUILDS = \{(.*?)\n\}', finder, re.DOTALL).group(1)
    for class_name, profiles in re.findall(r'case CLASS_(\w+): return \{([^}]+)\};', native_profiles):
        class_token = class_name.replace('_', '')
        values = re.findall(r'"([a-z]+)"', profiles)
        expected = {name: index for index, name in enumerate(values) if name != 'auto'}
        client = re.search(r'\b' + class_token + r'=\{([^}]+)\}', client_profiles).group(1)
        actual = {name: int(index) for name, index in re.findall(r'([a-z]+)=(\d+)', client)}
        assert all(actual.get(name) == index for name, index in expected.items()), (class_token, expected, actual)
    assert 'return "frostfire";' in factory and 'frostfire=2' in client_profiles
    transport = (core / 'modules/mod-multibot-bridge/src/MultiBotBridge.cpp').read_text()
    assert 'AiFactory::GetEffectiveCombatProfile(subject)' in transport
    assert 'subject->CanDualWield() ? "1" : "0"' in transport


def mutations():
    """(label, file, old, new): each must make the fixture fail an assertion."""
    m = MODULE
    return (
        ('unknown tier unlocks', m, 'if not (self.state and self.state.ip) then return "unknown" end\n\tif not self:Gated()',
         'if not (self.state and self.state.ip) then return "ok" end\n\tif not self:Gated()'),
        ('effective tier ignored', m, 'self.state.effective >= tier then return "ok" end', 'true then return "ok" end'),
        ('bot accounts gated', m, 'return s ~= nil and s.ip and s.account == "N" and not s.gm', 'return s ~= nil and s.ip'),
        ('auto mode without bridge gates', m, 'if status == "absent" then return self:Mode() == "on" end',
         'if status == "absent" then return true end'),
        ('foreign sender accepted', m, 'string.lower(sender) ~= string.lower(player)', 'false'),
        ('state token ignored', m, 'if fields[2] ~= self.watchToken then return end', ''),
        ('state validation', m, 'if n[6] > 18 or n[7] > n[6]', 'if n[6] > 18'),
        ('account validation', m, 'if account ~= "N" and account ~= "B" and account ~= "X" then return nil end', ''),
        ('watch renewal', m, 'now - self.watchAt >= WATCH_RENEW', 'false'),
        ('bounded probing', m, 'if self.helloRetries >= HELLO_RETRIES then', 'if false then'),
        ('capability check', m, 'self.caps[CAPABILITY] and "ready" or "unsupported"', '"ready"'),
        ('target capability', m, 'self.bridge == "ready" and self.caps and self.caps.IP_TARGET_V1',
         'self.bridge == "ready" and self.caps'),
        ('target bridge readiness', m, 'self.bridge == "ready" and self.caps and self.caps.IP_TARGET_V1',
         'self.caps and self.caps.IP_TARGET_V1'),
        ('target mode ignores owner setting', m, 'if self.targetName then return "on" end', ''),
        ('strict target bot-account gate', m, 'if self.targetName and s and s.strict then return s.ip end', ''),
        ('target owns mutable tables', m, 'quests={}, queued={}, inflight={}, requests={}, generation=1, onChanged=onChanged',
         'quests=self.quests, queued=self.queued, inflight=self.inflight, requests=self.requests, generation=1, onChanged=onChanged'),
        ('target does not inherit owner answers', m,
         'if type(value) == "function" or key:match("^[A-Z_]+$") then return value end', 'return value'),
        ('target token namespace', m, 'if self.targetName then return IP:Token() end',
         'if self.targetName then return IP.watchToken end'),
        ('previous target closed', m, 'if self.target then self.target.closed = true end', ''),
        ('closed target parser', m, 'function IP:OnMessage(prefix, message, sender)\n\tif self.closed then return end',
         'function IP:OnMessage(prefix, message, sender)'),
        ('target profile token', m, 'opcode == "IP_TARGET" and self.targetName and fields[2] == self.watchToken',
         'opcode == "IP_TARGET" and self.targetName'),
        ('target request timeout', m,
         'function IP:ExpireTargetRequest(token)\n\tif not self.targetName or not ZGV.ScheduleTimer then return end',
         'function IP:ExpireTargetRequest(token)\n\tif true then return end'),
        ('target profile timeout', m, 'if not target.closed and not (target.state and target.profile) then',
         'if not target.closed and not target.state then'),
        ('target error notification', m, 'else self.error = fields[5] or "UNAVAILABLE"; self:Changed() end',
         'else self.error = fields[5] or "UNAVAILABLE" end'),
        ('bounded target rate retry', m, '(self.rateRetries or 0) < 3', 'true'),
        ('inactive target quest state', m,
         'if self.bridge ~= "ready" or not (self.state and (self.state.ip or self.targetName)) then return end',
         'if self.bridge ~= "ready" or not (self.state and self.state.ip) then return end'),
        ('target suffix batch budget', m, ' + #(self.targetSuffix or "")', ''),
        ('target name encoding', m,
         'local encoded = name:gsub("[^%w_.%-]", function(char) return string.format("%%%02X", string.byte(char)) end)',
         'local encoded = name'),
        ('incomplete reply stored', m, 'if tonumber(fields[3]) ~= #request.items then', 'if false then'),
        ('stale generation stored', m, 'if request.generation ~= self.generation then\n\t\tself:Requeue(request)',
         'if false then\n\t\tself:Requeue(request)'),
        ('batch size', m, 'if #batch >= MAX_BATCH or', 'if'),
        ('flush batch cap', m, 'if sent >= MAX_FLUSH_BATCHES then break end', ''),
        ('flush continuation', m, 'if next(self.queued) and ZGV.ScheduleTimer then', 'if false then'),
        ('in-flight dedupe', m, 'if self.queued[id] or self.inflight[id] then return end', 'if self.queued[id] then return end'),
        ('request timeout', m, 'if now - request.at >= REQUEST_TIMEOUT then', 'if false then'),
        ('rate limit retry', m, 'fields[5] == "RATE_LIMIT" then self:Requeue(request) end', 'false then end'),
        ('blocking reasons', m, 'R.BREADCRUMB_DONE + R.TIER + R.GIVER_HIDDEN', 'R.BREADCRUMB_DONE + R.GIVER_HIDDEN'),
        ('soft reasons block', m, 'IP.BLOCKING = R.DISABLED +', 'IP.BLOCKING = R.LEVEL_LOW + R.DISABLED +'),
        ('quest log kept', m, 'if ZGV.questsbyid and ZGV.questsbyid[id] then return false end', ''),
        ('completed quest kept', m, 'if ZGV.completedQuests and ZGV.completedQuests[id] then return false end', ''),
        ('outdated answer dropped', m, '\tend\n\treturn entry\nend', '\t\treturn nil\n\tend\n\treturn entry\nend'),
        ('reset expiry', m, 'self:Now() - entry.at >= REPEAT_TTL', 'false'),
        ('reputation invalidation', m, 'if entry.status == "L" and sharesbit(entry.reasons, bits) then self.quests[id] = nil end', ''),
        ('quest event invalidation', m, 'hooksecurefunc(ZGV, event, function() IP:InvalidateQuests() end)', 'local _ = event'),
        ('step skip', 'Step.lua', 'if ZGV.IP and ZGV.IP:IsStepBlocked(self) then return false end', ''),
        ('goal hide', 'Goal.lua', 'if ZGV.IP and ZGV.IP:IsGoalBlocked(self) then return false end', ''),
        ('step needs every quest blocked', m, 'if not self:IsGoalBlocked(goal) then return false end', ''),
        ('Outland tier', m, '["Hellfire Peninsula"]=8', '["Hellfire Peninsula"]=0'),
        ('TBC race exception', m, 'return self.TBC_RACES[race] and 0 or 8', 'return 0'),
        ('TBC race lookup', m, 'local race = UnitRace and select(2, UnitRace("player"))', 'local _, race = UnitRace and UnitRace("player")'),
        ('level cap', m, 'if level >= cap and cap < self.state.maxLevel then', 'if false then'),
        ('instance gate', m, 'if result == "locked" and code == "G" then\n\t\t\treturn "locked"',
         'if false then\n\t\t\treturn "locked"'),
        ('unknown access', m, '\t\telseif result == "unknown" then\n\t\t\treturn "unknown", reason\n', ''),
        ('guide chain hold', 'ZygorGuidesViewer.lua', 'if self.CurrentGuide[\'next\'] and ipCheck=="ok" then',
         'if self.CurrentGuide[\'next\'] then'),
        ('warning once', m, 'or self.warned[guide.title]', ''),
        ('milestone condition', m, '|condition ZGV.IP:HasTier(%d)', '|condition true or %d'),
        ('milestone note line', m, 'if first then\n\t\t\t\tlines[#lines + 1] = "\\t.\'" .. L.milestone_none',
         'if false then\n\t\t\t\tlines[#lines + 1] = "\\t.\'" .. L.milestone_none'),
        ('localized milestone names', m, 'L.milestone_step:format(tier, self:MilestoneText(tier))',
         'L.milestone_step:format(tier, self.MILESTONES[tier].name)'),
        ('milestone syntax escape', m, ':gsub("|", "/"):gsub("//", "/")', ''),
        ('milestone ceiling', m, 'ZGV.IP.state.limit < %d)"):format(tier)', 'ZGV.IP.state.limit < 0) and %d"):format(tier)'),
        ('manual quests', m, '[10259]=true', '[10260]=true'),
        ('manual accept', 'QuestAutoAccept.lua',
         'goal:IsCompleteable() and not goal:IsObsolete() and not IsManual(goal) then',
         'goal:IsCompleteable() and not goal:IsObsolete() then'),
        ('manual turn-in', 'QuestAutoAccept.lua',
         'if goal.quest==title and not IsManual(goal) then\n\t\t\t\tif GetNumQuestChoices',
         'if goal.quest==title then\n\t\t\t\tif GetNumQuestChoices'),
        ('dungeon gate', 'Item-GearFinder.lua',
         'if check ~= "ok" then return false, check == "locked", ident',
         'if false then return false, check == "locked", ident'),
        ('unknown source is future', 'Item-GearFinder.lua', 'return false, check == "locked", ident',
         'return false, true, ident'),
        ('dungeon era', m, 'local tier = TierOfEra(dungeon.expansionLevel or 0)', 'local tier = 0'),
        ('dungeon phase', m, 'tier = math.max(tier, self.PHASES[dungeon.phase])', 'tier = tier'),
        ('vanilla raid slot', m, '[249]=2, [533]=2', '[249]=0, [533]=0'),
        ('disabled is future', m, 'if code == "D" then return "unknown", reason end', ''),
        ('next tier label', m, 'tier <= s.next then return L.gear_next end', 'false then return L.gear_next end'),
        ('phase gate', 'Item-GearFinder.lua', 'if earned ~= nil then return earned end', ''),
        ('vendor gate', 'Item-GearFinder.lua', 'local check, reason = GF_Progression():VendorCheck(source)\n\t\tif check ~= "ok" then',
         'local check, reason = GF_Progression():VendorCheck(source)\n\t\tif false then'),
        ('craft era', m, 'local check = self:TierCheck(tier)\n\tif check ~= "ok" then return check, self:TierReason(check, tier) end\n\tif not self:Gated() then return "ok" end\n\tlocal spell',
         'local check = "ok"\n\tif check ~= "ok" then return check, self:TierReason(check, tier) end\n\tif not self:Gated() then return "ok" end\n\tlocal spell'),
        ('craft recipe source', m, 'return "unknown", L.gear_recipe', 'return "ok"'),
        ('BiS rank', 'Item-ItemScore.lua', 'if earned then return math.max(earned, 0) end', ''),
        ('BiS before Wrath', 'Item-ItemScore.lua', 'if ZGV and ZGV.IP and ZGV.IP:BISPhaseRank() == -1 then return nil end', ''),
        ('BiS unknown', m, 'if not (self.state and self.state.ip) then return -1 end', 'if not (self.state and self.state.ip) then return 5 end'),
        ('advisor era gate', 'ZygorTalentAdvisor/ZygorTalentAdvisor.lua',
         'if ZGV and ZGV.IP and ZGV.IP:TalentAdvisorBlocked() then return false end', ''),
        ('EraTalents gate', m, 'if era and era.isEraChar then return true, L.talent_blocked end', ''),
        ('advisor unknown era', m, 'if not (self.state and self.state.ip) then return true, L.unknown end', ''),
        ('LearnTalent at load', 'ZygorTalentAdvisor/ZygorTalentAdvisor.lua',
         'local function AdvisedLearnTalent(tab,talent,pet,group)', 'function LearnTalent(tab,talent,pet,group)'),
        ('LearnTalent restore', 'ZygorTalentAdvisor/ZygorTalentAdvisor.lua',
         'elseif LearnTalent == AdvisedLearnTalent then\n\t\tLearnTalent = Old_LearnTalent', 'elseif false then'),
        ('wrapper era check', 'ZygorTalentAdvisor/ZygorTalentAdvisor.lua',
         'if not ZygorTalentAdvisor:IsAdvisorEnabled() then return Old_LearnTalent(tab,talent,pet,group) end', ''),
        ('talent group', 'ZygorTalentAdvisor/ZygorTalentAdvisor.lua', 'Old_LearnTalent(tab,talent,pet,group)',
         'Old_LearnTalent(tab,talent,pet)'),
        ('learn button', 'ZygorTalentAdvisor/ZygorTalentAdvisor.lua',
         'elseif current == ZygorTalentAdvisor_PlayerTalentFrameLearnButton_OnClick and self.originalLearnButtonClick then',
         'elseif false then'),
        ('auto learn', 'ZygorTalentAdvisor/ZygorTalentAdvisor.lua',
         'function me:LearnSuggestedTalents(pet,loud)\n\tif not self:IsAdvisorEnabled() then return end',
         'function me:LearnSuggestedTalents(pet,loud)'),
        ('new talent popup', 'ZygorTalentAdvisor/ZygorTalentAdvisor.lua',
         '\tif not self:IsAdvisorEnabled() then return nil end\n', ''),
        ('refresh', m, 'if msg and string.lower(msg) == "refresh" then IP:Refresh() end', ''),
        ('status text', m, 'lines[#lines + 1] = L.next:format(s.next, self:MilestoneText(s.next))', ''),
        ('German text', m, '\t\tstatus_level = "Erfahrung endet bei Level %d bis zur Stufe der nächsten Erweiterung.",\n', ''),
        ('historical talent points', 'Item-ItemScore.lua',
         'if ZGV.IP then eraPoints, eraTotal, eraAvailable, eraFeralRank = ZGV.IP:EraTalentPoints(classToken) end', ''),
        ('Druid restoration profile', 'Item-ItemScore.lua', 'and pointsTree == 3 then return 4, false end',
         'and pointsTree == 3 then return 3, false end'),
        ('Druid primary-tree restoration', 'Item-ItemScore.lua', 'and tree == 3 then return 4, false end',
         'and tree == 3 then return 3, false end'),
        ('native talent rank return', 'Item-ItemScore.lua', 'select(5, GetTalentInfo(2, index,', 'select(3, GetTalentInfo(2, index,'),
        ('native talent identity', 'Item-ItemScore.lua', 'link:match("talent:(%d+)") == "794"', 'index == 11'),
        ('historical feral rank', m, '(state.ranks and state.ranks[node.id]) or 0', '0'),
        ('historical role rescore', m, '.. "/" .. (feralRank or "")', ''),
        ('historical native trees', 'Item-ItemScore.lua', 'elseif ZGV.IP and ZGV.IP:NativeTalentsHistorical() then',
         'elseif false then'),
        ('wing instance names', m, 'self.INSTANCES[wing and wing.instancename or ""]', 'nil'),
        ('native retry kept', m, 'return self:Gated() and self.state.era < 2', 'return true'),
        ('historical rescore', m, '\t\tlast = signature\n\t\tscore:DelayedRefreshUserData()\n', '\t\tlast = signature\n'),
        ('unchanged historical rescore', m, '\t\tif signature == last then return end\n', ''),
    )


def run_lua(lua, source, era, fixture=FIXTURE):
    globals_ = f'SOURCE={json.dumps(str(source))} ERA_SOURCE={json.dumps(str(era))}'
    return run_fixture([lua, '-e', globals_, str(fixture)], 'Zygor progression fixture')


def upstream_suite(lua, addon, tools_root, working_tools=False):
    with tempfile.TemporaryDirectory(prefix='zygor-tools-') as directory:
        if working_tools:
            shutil.copytree(tools_root / 'tools', Path(directory) / 'tools')
        else:
            lock = json.loads((REPOSITORY / 'versions.lock.json').read_text())
            revision = next(item['revision'] for item in lock['sourceAddons'] if item['name'] == 'ZygorGuidesViewerRM')
            archive = subprocess.run(['git', '-c', 'core.autocrlf=false', '-c', 'core.eol=lf', '-C', str(tools_root),
                                      'archive', revision, 'tools'],
                                     check=True, capture_output=True).stdout
            subprocess.run(['tar', '-x', '-C', directory], input=archive, check=True)
        tests = sorted(Path(directory).glob('tools/*/test_*.lua'))
        assert len(tests) >= 20, 'the upstream Zygor regression suite is missing'
        for test in tests:
            result = run_fixture([lua, str(test), str(addon)], test.name, cwd=directory)
            if result.returncode:
                raise AssertionError(f'{test.relative_to(directory)}: {result.stdout}{result.stderr}')
        print(f'Upstream Zygor regression suite passed: {len(tests)} tests', flush=True)
        work = Path(directory) / 'reverted'
        candidate = work / 'ZygorGuidesViewerRM'
        shutil.copytree(addon, candidate)
        target_files = ('IndividualProgression.lua', 'Item-GearFinder.lua', 'Item-ItemScore.lua',
                        'Item-Upgrades.lua', 'ZygorQuestLootDB.lua', 'Code-WOTLK/Item-GearFinder.lua',
                        'Code-WOTLK/Item-ItemScore.lua')
        target_paths = tuple('ZygorGuidesViewerRM/' + name for name in target_files)
        target_patch = fork_change('ZygorGuidesViewerRM', 'zygor-inspected-altbot-gearfinder', paths=target_paths)
        launchers = fork_change('ZygorGuidesViewerRM', 'zygor-gearfinder-equipment-launchers',
                                paths=('ZygorGuidesViewerRM/Code-WOTLK/Item-GearFinder.lua',))
        launcher_test = Path(directory) / 'tools/gearfinder/test_inspect_context.lua'
        git_apply(work, launchers, '--reverse')
        result = run_fixture([lua, str(launcher_test), str(candidate)], 'equipment launchers', cwd=directory)
        assert result.returncode != 0 and "in function 'assert'" in result.stderr, result.stdout + result.stderr
        git_apply(work, launchers)
        result = run_fixture([lua, str(launcher_test), str(candidate)], 'equipment launchers', cwd=directory)
        assert result.returncode == 0, result.stdout + result.stderr
        print('Gear Finder equipment launchers fail when reverted and pass when reapplied', flush=True)
        target_tests = ('gearfinder/test_inspect_context.lua', 'gearfinder/test_target_sources.lua',
                        'itemscore/test_target_context.lua', 'itemscore/test_target_tooltip.lua')
        git_apply(work, launchers, '--reverse')
        git_apply(work, target_patch, '--reverse')
        for name in target_tests:
            result = run_fixture([lua, str(Path(directory) / 'tools' / name), str(candidate)], name, cwd=directory)
            if result.returncode == 0 or "in function 'assert'" not in result.stderr:
                raise AssertionError(f'Reverting inspected Gear Finder did not fail {name}:\n'
                                     + result.stdout + result.stderr)
        git_apply(work, target_patch)
        git_apply(work, launchers)
        for name in target_tests:
            result = run_fixture([lua, str(Path(directory) / 'tools' / name), str(candidate)], name, cwd=directory)
            if result.returncode:
                raise AssertionError(f'Reapplying inspected Gear Finder failed {name}:\n'
                                     + result.stdout + result.stderr)
        print('Inspected Gear Finder fork change fails all four regressions when reverted and passes when reapplied',
              flush=True)
        # The earlier incremental commit is checked against its native parent context.
        git_apply(work, launchers, '--reverse')
        git_apply(work, target_patch, '--reverse')
        changed = ('IndividualProgression.lua', 'Item-GearFinder.lua', 'ZygorQuestLootDB.lua')
        patch = fork_change('ZygorGuidesViewerRM', 'zygor-incremental-gearfinder',
                            paths=tuple('ZygorGuidesViewerRM/' + name for name in changed))
        git_apply(work, patch, '--reverse')
        regressions = ('test_incremental_scan.lua', 'test_quest_cache.lua', 'test_progression_refresh.lua')
        for name in regressions:
            test = Path(directory) / 'tools/gearfinder' / name
            result = run_fixture([lua, str(test), str(candidate)], name, cwd=directory)
            if result.returncode == 0 or "in function 'assert'" not in result.stderr:
                raise AssertionError(f'Reverting incremental Gear Finder did not fail {name}:\n'
                                     + result.stdout + result.stderr)
        git_apply(work, patch)
        for name in regressions:
            test = Path(directory) / 'tools/gearfinder' / name
            result = run_fixture([lua, str(test), str(candidate)], name, cwd=directory)
            if result.returncode:
                raise AssertionError(f'Reapplying incremental Gear Finder failed {name}:\n'
                                     + result.stdout + result.stderr)
        print('Incremental Gear Finder fork change fails all three regressions when reverted and passes when reapplied',
              flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source_argument(parser, 'addon', help='patched ZygorGuidesViewerRM directory')
    source_argument(parser, 'core', help='prepared core source directory')
    source_argument(parser, 'tools', help='Zygor checkout whose working regression tools should run')
    parser.add_argument('--lua', default=shutil.which('lua5.1'), help='Lua 5.1 executable')
    args = parser.parse_args()
    if not args.lua:
        parser.error('Lua 5.1 is required')
    addon = args.addon or REPOSITORY / '.module-cache/prepared-source-addons/ZygorGuidesViewerRM'
    core = args.core or prepared_core()
    contracts(addon, core)
    print('Zygor progression contracts match Individual Progression, the bridge and the core', flush=True)

    era = core / 'modules/mod-era-talents/client-addon/EraTalents'
    result = run_lua(args.lua, addon, era)
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    print(result.stdout.strip(), flush=True)

    with tempfile.TemporaryDirectory(prefix='zygor-progression-') as directory:
        base = Path(directory) / 'base'
        for relative in FILES:
            (base / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(addon / relative, base / relative)

        def rejected(numbered):
            index, (label, relative, old, new) = numbered
            work = Path(directory) / str(index)
            shutil.copytree(base, work)
            text = (work / relative).read_text()
            if old not in text:
                raise AssertionError(f'{label} mutation was not applied')
            (work / relative).write_text(text.replace(old, new))
            outcome = run_lua(args.lua, work, era)
            return outcome.returncode != 0 and 'FIXTURE FAILED' in outcome.stderr

        cases = mutations()
        for (label, *_), result in zip(cases, in_parallel(rejected, list(enumerate(cases)))):
            if not result:
                raise AssertionError(f'Zygor progression fixture did not reject {label}')
            print(f'Zygor progression mutation rejected: {label}', flush=True)

    upstream_suite(args.lua, addon, args.tools or REPOSITORY / TOOLS, working_tools=args.tools is not None)


if __name__ == '__main__':
    main()
