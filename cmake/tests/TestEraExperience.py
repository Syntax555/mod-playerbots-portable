"""Check per-character era experience with production sources under ASan/UBSan.

Individual Progression's era experience script, its legacy quest-XP and
quest-money hooks and its configuration loader run with the core's quest,
aura, rest and Recruit-a-Friend functions against doubles of the realm. Every
case also runs with the option off and with strict progression off, where
nothing may change. The level table, the generated era quest tables and the
experience auras of the pinned client data are checked as data.
"""

import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    cxx,
    function,
    pinned_source,
    prepared_core,
    reject_mutants,
    run_fixture,
    source_argument,
    wdbc,
)


repo = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, 'core', default=prepared_core(repo), help='prepared core directory')
source_argument(parser, 'classic-db', help='CMaNGOS classic-db checkout to regenerate the era quest tables from')
source_argument(parser, 'tbc-db', help='CMaNGOS tbc-db checkout to regenerate the era quest tables from')
args = parser.parse_args()
core = args.core
module = core / 'modules/mod-individual-progression'
sys.path.insert(0, str(repo / 'scripts'))
import generate_era_quest_xp as era_generator


def read(path):
    return (core / path).read_text(encoding='utf-8')


def between(text, start, end):
    """text from start through the end of end."""
    first = text.index(start)
    return text[first:text.index(end, first) + len(end)]


lock = json.loads((repo / 'versions.lock.json').read_text())
player_cpp = read('src/server/game/Entities/Player/Player.cpp')
player_h = read('src/server/game/Entities/Player/Player.h')
quest_cpp = read('src/server/game/Entities/Player/PlayerQuest.cpp')
quest_h = read('src/server/game/Quests/QuestDef.h')
unit_cpp = read('src/server/game/Entities/Unit/Unit.cpp')
ip_source = (module / 'src/IndividualProgression.cpp').read_text()
ip_header = (module / 'src/IndividualProgression.h').read_text()
ip_player = (module / 'src/IndividualProgressionPlayer.cpp').read_text()
era_source = (module / 'src/EraExperience.cpp').read_text()
policy = (module / 'src/EraExperiencePolicy.h').read_text()

# Native contracts of the hooks. RewardQuest computes the experience, then the
# hook may change it, before the quest counts as rewarded and the completion
# hook runs; at the realm maximum it pays GetRewMoneyMaxLevel instead.
reward = function(quest_cpp, 'void Player::RewardQuest(')
reward_xp = between(reward, '    bool const rewarded = ', '    sScriptMgr->OnPlayerQuestComputeXP(this, quest, XP);')
assert ('bool const rewarded = IsQuestRewarded(quest_id) && !quest->IsDFQuest() && '
        '!(quest->IsDaily() || quest->IsWeekly() || quest->IsMonthly());') in reward_xp
assert 'uint32 XP = rewarded ? 0 : CalculateQuestRewardXP(quest);' in reward_xp
assert (reward.index('sScriptMgr->OnPlayerQuestComputeXP(this, quest, XP);') < reward.index('SetRewardedQuest(quest_id);')
        < reward.index('sScriptMgr->OnPlayerCompleteQuest(this, quest);'))
assert ('if (GetLevel() >= sWorld->getIntConfig(CONFIG_MAX_PLAYER_LEVEL) || '
        'sScriptMgr->OnPlayerShouldBeRewardedWithMoneyInsteadOfExp(this))\n    {\n'
        '        moneyRew = quest->GetRewMoneyMaxLevel();') in reward
# Quest-giver windows show the hook's value.
gossip = read('src/server/game/Entities/Creature/GossipDef.cpp')
assert gossip.count('sScriptMgr->OnPlayerQuestComputeXP(player, quest, questXp);') == 2
window_xp = re.search(r'\n(    uint32 questXp;\n.*?\n    sScriptMgr->OnPlayerQuestComputeXP\(player, quest, questXp\);)\n',
                      gossip, re.DOTALL)[1]
assert 'questXp = player->CalculateQuestRewardXP(quest);' in window_xp
# Kill experience is multiplied by the auras before the hook; the pet gets the hook's amount.
killer = read('src/server/game/Entities/Player/KillRewarder.cpp')
kill_xp = between(killer, '        // 4.2.2. Apply auras', 'PlayerXPSource::XPSOURCE_KILL);')
assert 'xp *= player->GetTotalAuraMultiplier(SPELL_AURA_MOD_XP_PCT);' in kill_xp
assert killer.index('PlayerXPSource::XPSOURCE_KILL);') < killer.index('pet->GivePetXP(_group ? xp / 2 : xp);')
# Battleground objective experience is the only XPSOURCE_BATTLEGROUND gain.
honor = function(player_cpp, 'bool Player::RewardHonor(')
objective = between(honor, 'if (!uVictim)', '}')
assert 'sScriptMgr->OnPlayerGiveXP(this, xp, nullptr, PlayerXPSource::XPSOURCE_BATTLEGROUND);' in objective
assert sum(source.count('XPSOURCE_BATTLEGROUND)') for source in (player_cpp, quest_cpp, killer)) == 1
# Recruit-a-Friend: triple experience after the hooks, level grants and the reputation bonus all
# depend on RecruitAFriend.MaxLevel and its reputation rate.
give_xp = function(player_cpp, 'void Player::GiveXP(')
assert 'bool recruitAFriend = GetsRecruitAFriendBonus(true);' in give_xp and 'bonus_xp = 2 * xp;' in give_xp
assert 'bonus_xp = victim ? GetXPRestBonus(xp) : 0;' in give_xp
assert ('if (level < sWorld->getIntConfig(CONFIG_MAX_RECRUIT_A_FRIEND_BONUS_PLAYER_LEVEL))\n            if (level % 2 == 0)'
        in function(player_cpp, 'void Player::GiveLevel('))
refer = read('src/server/game/Handlers/ReferAFriendHandler.cpp')
assert ('else if (target->GetLevel() >= sWorld->getIntConfig(CONFIG_MAX_RECRUIT_A_FRIEND_BONUS_PLAYER_LEVEL))\n'
        '        error = ERR_REFER_A_FRIEND_GRANT_LEVEL_MAX_I;') in refer
assert ('if (source != REPUTATION_SOURCE_SPELL && GetsRecruitAFriendBonus(false))\n'
        '        percent *= 1.0f + sWorld->getRate(RATE_REPUTATION_RECRUIT_A_FRIEND_BONUS);') in player_cpp
world_cpp = read('src/server/game/World/World.cpp')
load_settings = function(world_cpp, 'void World::LoadConfigSettings(')
assert (load_settings.index('sScriptMgr->OnBeforeConfigLoad(reload);') < load_settings.index('_worldConfig.Initialize(reload);')
        < load_settings.index('sScriptMgr->OnAfterConfigLoad(reload);'))
assert '_worldConfig.OverwriteConfigValue<uint32>(index, value);' in function(world_cpp, 'void World::setIntConfig(')
world_config = read('src/server/game/World/WorldConfig.cpp')
for default in ('CONFIG_MAX_RECRUIT_A_FRIEND_BONUS_PLAYER_LEVEL, "RecruitAFriend.MaxLevel", 60,',
                'CONFIG_MAX_RECRUIT_A_FRIEND_BONUS_PLAYER_LEVEL_DIFFERENCE, "RecruitAFriend.MaxDifference", 4)',
                'RATE_REPUTATION_RECRUIT_A_FRIEND_BONUS, "Rate.Reputation.RecruitAFriendBonus", 0.1f)',
                'RATE_REST_MAX_BONUS, "Rate.Rest.MaxBonus", 1.5f)', 'RATE_XP_QUEST, "Rate.XP.Quest", 1.0f)',
                'RATE_XP_QUEST_DF, "Rate.XP.Quest.DF", 1.0f)', 'RATE_REWARD_BONUS_MONEY, "Rate.RewardBonusMoney", 1.0f)'):
    assert default in world_config, default
# Offline rest is added while loading, before quest status is known; the login hook runs in the
# world, for bots too.
load = function(read('src/server/game/Entities/Player/PlayerStorage.cpp'), 'bool Player::LoadFromDB(')
assert load.index('SetRestBonus(GetRestBonus() + time_diff') < load.index('_LoadQuestStatusRewarded(')
login = function(read('src/server/game/Handlers/CharacterHandler.cpp'), 'void WorldSession::HandlePlayerLoginFromDB(')
assert (login.index('pCurrChar->LoadFromDB(') < login.index('AddPlayerToMap(pCurrChar)')
        < login.index('sScriptMgr->OnPlayerLogin(pCurrChar);'))
bots = read('modules/mod-playerbots/src/Bot/PlayerbotMgr.cpp')
assert 'botSession->HandlePlayerLoginFromDB(holder);' in function(bots, 'void PlayerbotHolder::HandlePlayerBotLoginCallback(')
# Hooks run in registration order; era experience registers before IP's player script.
assert ('for (auto const& script : ScriptRegistry<scriptType>::EnabledHooks[hookType]) { action; }'
        in read('src/server/game/Scripting/ScriptMgrMacros.h'))
assert 'for (uint16 v : enabledHooks)\n                EnabledHooks[v].emplace_back(script);' in read(
    'src/server/game/Scripting/ScriptMgr.h')
loader = (module / 'src/IndividualProgression_loader.cpp').read_text()
assert loader.index('    AddSC_individual_progression_era_experience();') < loader.index(
    '    AddSC_mod_individual_progression_player();')
# No module changes the experience level, quest rate or money conversion the doubles leave alone.
for path in sorted(core.glob('modules/**/*')):
    if path.suffix in ('.cpp', '.h') and path.is_file():
        text = path.read_text(encoding='utf-8', errors='replace')
        assert not re.search(r'\b(void|bool)\s+OnPlayer(BeforeGetLevelForXPGain|GetQuestRate|'
                             r'ShouldBeRewardedWithMoneyInsteadOfExp)\s*\(', text), path
# IP's custom_quest_xp loading is unchanged; the TBC table is loaded after it.
load_xp = function(ip_source, '    static void LoadXpValues()')
upstream_load_xp = function(pinned_source('mod-individual-progression', 'src/IndividualProgression.cpp'),
                            '    static void LoadXpValues()')
assert load_xp.startswith(upstream_load_xp[:upstream_load_xp.rindex('}')].rstrip())


# The realm's level table: Individual Progression replaces it with 1.12 values for
# levels 1-59 and 2.4.3 values for 60-69, the levels each era can hold.
# CMaNGOS classic-db ec4f596 and tbc-db ebe51a83 player_xp_for_level.
CLASSIC_XP = [
    400, 900, 1400, 2100, 2800, 3600, 4500, 5400, 6500, 7600, 8800, 10100, 11400, 12900, 14400, 16000, 17700, 19400,
    21300, 23200, 25200, 27300, 29400, 31700, 34000, 36400, 38900, 41400, 44300, 47400, 50800, 54500, 58600, 62800,
    67100, 71600, 76100, 80800, 85700, 90700, 95800, 101000, 106300, 111800, 117500, 123200, 129100, 135100, 141200,
    147500, 153900, 160400, 167100, 173900, 180800, 187900, 195000, 202300, 209800]
TBC_XP = [494000, 574700, 614400, 650300, 682300, 710200, 734100, 753700, 768900, 779700]
level_sql = module / 'data/sql/world/base/vanilla_xp_tables.sql'
core_levels = {int(level): int(xp) for level, xp in re.findall(
    r'\((\d+),(\d+)\)', read('data/sql/base/db_world/player_xp_for_level.sql'))}


def check_level_table(text):
    assert text.startswith('REPLACE INTO `player_xp_for_level` (`Level`, `Experience`) VALUES')
    levels = {int(level): int(xp) for level, xp in re.findall(r'\((\d+), (\d+)\)', text)}
    assert [levels[level] for level in range(1, 60)] == CLASSIC_XP
    assert [levels[level] for level in range(60, 70)] == TBC_XP
    assert [levels[level] for level in range(70, 80)] == [core_levels[level] for level in range(70, 80)]


updater = read('src/server/database/Updater/UpdateFetcher.cpp')
assert '"/modules/" + moduleName + "/data/sql/"' in updater
assert 'if (dirName.find(_dbModuleName) == std::string::npos)' in updater
assert 'AppliedFileEntry::StateConvert("MODULE")' in updater
assert 'FillFileListRecursively(itr->path(), storage, state, depth + 1)' in updater
level_text = level_sql.read_text()
check_level_table(level_text)
for label, old, new in (('level 30', '(30, 47400)', '(30, 47500)'), ('level 60 from Wrath', '(60, 494000)', '(60, 290000)'),
                        ('level 70 from TBC', '(70, ', '(70, 779700), (0, ')):
    mutant = level_text.replace(old, new, 1)
    assert mutant != level_text, label
    try:
        check_level_table(mutant)
    except AssertionError:
        print(f'Era level table mutation rejected: {label}')
    else:
        raise AssertionError(f'Era level table check accepted {label}')


# The generated era quest tables: 2.4.3 values with their quest levels, and the
# 1.12 quest levels of Individual Progression's values.
era_sql = module / 'data/sql/world/updates/2026_10_16_01_era_quest_xp.sql'
core_quests = {int(row['ID']): row for row in era_generator.table_rows(read(era_generator.CORE_QUESTS), 'quest_template')}
ip_values = era_generator.ip_values(read(era_generator.IP_QUESTS))
assert len(ip_values) == 5657
revisions = {source['name']: source['revision'] for source in lock['historicalClassData']['sources']}
# entry: (RewMoneyMaxLevel, QuestLevel, value) recorded from tbc-db ebe51a83.
TBC_SPOTS = {2: (1500, 30, 2500), 5: (240, 20, 400), 1318: (4950, 60, 8250), 9372: (37500, 63, 10417),
             9492: (75900, 70, 12650), 2881: (0, 45, 0), 3803: (2820, 55, 4700), 7563: (4650, 58, 7750)}
# entry: QuestLevel recorded from classic-db ec4f596; patch 2.3.0 lowered these.
VANILLA_LEVEL_SPOTS = {2: 30, 3566: 52, 630: 51, 618: 50, 3371: 55}
TBC_HEADER = ('DROP TABLE IF EXISTS `custom_quest_xp_tbc`;\nCREATE TABLE `custom_quest_xp_tbc` (\n'
              '    `entry` int unsigned NOT NULL,\n    `xpValue` int unsigned NOT NULL,\n    `questLevel` int NOT NULL,\n'
              '    PRIMARY KEY (`entry`)\n) ENGINE=InnoDB;\n\n'
              'INSERT INTO `custom_quest_xp_tbc` (`entry`, `xpValue`, `questLevel`) VALUES\n')
LEVEL_HEADER = ('DROP TABLE IF EXISTS `custom_quest_xp_level`;\nCREATE TABLE `custom_quest_xp_level` (\n'
                '    `entry` int unsigned NOT NULL,\n    `questLevel` int NOT NULL,\n    PRIMARY KEY (`entry`)\n'
                ') ENGINE=InnoDB;\n\nINSERT INTO `custom_quest_xp_level` (`entry`, `questLevel`) VALUES\n')


def table_body(text, header, columns):
    body = text[text.index(header) + len(header):]
    body = body[:body.index(';\n') + 2]
    rows = [tuple(int(value) for value in row) for row in re.findall(
        r'^\(' + ', '.join([r'(-?\d+)'] * columns) + r'\)[,;]$', body, re.MULTILINE)]
    assert len(rows) == body.count('\n') and rows
    entries = [row[0] for row in rows]
    assert entries == sorted(set(entries)) and set(entries) <= set(core_quests)
    return {row[0]: row[1:] for row in rows}


def check_era_values(text):
    assert text.count(TBC_HEADER) == text.count(LEVEL_HEADER) == 1 and text.index(TBC_HEADER) < text.index(LEVEL_HEADER)
    assert text.endswith(');\n')
    for name in ('cmangos-classic-db', 'cmangos-tbc-db', 'cmangos-mangos-tbc'):
        assert f"{name.split('-', 1)[1]} {revisions[name]}" in text, name
    values = table_body(text, TBC_HEADER, 3)
    levels = {entry: level for entry, (level,) in table_body(text, LEVEL_HEADER, 2).items()}
    assert 26 not in values and 27 not in values and all(level > 0 for _, level in values.values())
    for entry, (money, level, xp) in TBC_SPOTS.items():
        assert era_generator.full_xp(level, money) == xp and values.get(entry) == (xp, level), entry
    assert set(levels) <= set(ip_values) and all(level > 0 for level in levels.values())
    for entry, level in VANILLA_LEVEL_SPOTS.items():
        assert levels.get(entry) == level, entry
    return values, levels


assert core_quests[26]['QuestLevel'] == core_quests[27]['QuestLevel'] == '-1'
assert core_quests[7563]['QuestLevel'] == '-1' and core_quests[3566]['QuestLevel'] == '46'
era_text = era_sql.read_text()
tbc_values, vanilla_levels = check_era_values(era_text)
assert len(tbc_values) == 5703 and sum(1 for xp, _ in tbc_values.values() if xp == 0) == 904
assert len(vanilla_levels) == 3664
if args.classic_db and args.tbc_db:
    assert era_generator.generate(args.classic_db, args.tbc_db, core) == era_text, 'regenerated era quest tables differ'
    print('Era quest tables regenerate byte for byte from the classic-db and tbc-db checkouts')
after_26 = min(entry for entry in tbc_values if entry > 26)
for label, mutant, divisor in (
    ('spot value', era_text.replace('\n(1318, 8250, 60),', '\n(1318, 8251, 60),'), 3.6),
    ('spot row', era_text.replace('\n(9492, 12650, 70),', ''), 3.6),
    ('TBC quest level', era_text.replace('\n(7563, 7750, 58),', '\n(7563, 7750, -1),'), 3.6),
    ('level -1 row', era_text.replace(f'\n({after_26}, ', f'\n(26, 400, 1),\n({after_26}, ', 1), 3.6),
    ('1.12 quest level', era_text.replace('\n(3566, 52),', '\n(3566, 46),'), 3.6),
    ('generator divisor', era_text, 3.5),
):
    assert divisor != 3.6 or mutant != era_text, label
    era_generator.DIVISORS[63] = era_generator.float32(divisor)
    try:
        check_era_values(mutant)
    except AssertionError:
        print(f'Era quest table mutation rejected: {label}')
    else:
        raise AssertionError(f'Era quest table check accepted {label}')
    finally:
        era_generator.DIVISORS[63] = era_generator.float32(3.6)


# Experience auras of the pinned 3.3.5 client: the 2.4.3 bonuses plus the
# policy's Wrath-only ones. mangos-tbc a8ad244 Spell.sql has these positive
# aura 200 effects; mangos-classic 8ec338a has no experience aura.
TBC_XP_AURAS = {24705, 29175, 32172, 33377, 42138, 46668}
spec = importlib.util.spec_from_file_location('client_locales', repo / 'cmake/ClientLocales.py')
locales = importlib.util.module_from_spec(spec)
spec.loader.exec_module(locales)
donors, _, _ = locales.load_german_inputs(repo, lock['clientPatch']['localizations'])
spell_rows, _ = wdbc(donors['Spell.dbc'], 234)
EFFECT, BASE_POINTS, AURA = 71, 80, 95


def spell_field(raw, index, signed=False):
    return struct.unpack_from('<i' if signed else '<I', raw, index * 4)[0]


spells = {spell_field(raw, 0): raw for raw in spell_rows}
heirloom = spells[57353]
assert [spell_field(heirloom, EFFECT + i) for i in range(3)] == [6, 6, 0]
assert [spell_field(heirloom, AURA + i) for i in range(3)] == [200, 291, 0]
assert [spell_field(heirloom, BASE_POINTS + i, True) for i in range(3)] == [9, 9, 0]
xp_auras = {spell for spell, raw in spells.items() for i in range(3)
            if spell_field(raw, AURA + i) in (200, 291) and spell_field(raw, BASE_POINTS + i, True) + 1 > 0}
wrath_only = {int(spell) for spell in re.findall(r'case (\d+):', function(policy, 'constexpr bool WrathOnlyXPBonus('))}
assert xp_auras == TBC_XP_AURAS | wrath_only and not TBC_XP_AURAS & wrath_only, xp_auras
xp_spells = xp_auras | {69711, 58440}
# GetTotalAuraMultiplier adds every effect unless a spell group stacks it; none of these is grouped.
for path in [core / 'data/sql/base/db_world/spell_group.sql', *core.glob('data/sql/updates/db_world/*.sql'),
             *core.glob('modules/*/data/sql/**/*.sql')]:
    text = path.read_text(encoding='utf-8', errors='replace')
    if 'spell_group`' in text:
        assert not xp_spells & {int(number) for number in re.findall(r'\b\d+\b', text)}, path
heirloom_items = [row for row in era_generator.table_rows(read('data/sql/base/db_world/item_template.sql'), 'item_template')
                  if {'57353', '71354'} & {row[f'spellid_{slot}'] for slot in range(1, 6)}]
assert heirloom_items and {row['Quality'] for row in heirloom_items} == {'7'}
print(f'Era experience data: level table, {len(tbc_values)} 2.4.3 quest values, {len(vanilla_levels)} 1.12 quest '
      f'levels, {len(xp_auras)} client '
      f'experience auras and {len(heirloom_items)} heirlooms checked')


# Production quest rows used by the cases.
special_flags = {int(row['ID']): row['SpecialFlags'] for row in era_generator.table_rows(
    read('data/sql/base/db_world/quest_template_addon.sql'), 'quest_template_addon')}
quest_rows = ',\n'.join(
    '{{{}, {QuestLevel}, {RewardXPDifficulty}, {Flags}, {}}}'.format(entry, special_flags.get(entry, '0'), **core_quests[entry])
    for entry in (2, 26, 1318, 2881, 3566, 3803, 7563, 9492))
# QuestXP.dbc Exp[1..8] for levels 1-100, recorded from the pinned client data
# (Haeniken/TrinityCore-3.3.5-data-multilang b21c949 dbc/deDE/QuestXP.dbc,
# SHA-256 ae88d842e994dccad08d58983f8c524c0aa51a3557ebbb5aa687098298a7b8d5); Exp[0] and Exp[9] are 0.
QUEST_XP = '''
    10 20 40 60 80 100 120 160 | 15 45 85 130 170 215 255 340 | 25 65 125 190 250 315 380 500 | 35 90 180 270 355 445 540 710
    45 110 225 335 450 560 670 900 | 55 135 270 405 540 680 810 1080 | 65 160 315 475 630 790 950 1260 | 70 175 350 530 700 880 1050 1400
    80 195 390 590 780 980 1150 1560 | 85 210 420 630 840 1050 1250 1680 | 90 220 440 660 880 1100 1300 1760 | 90 225 455 680 910 1150 1350 1820
    90 230 455 680 910 1150 1350 1820 | 100 245 490 740 980 1250 1450 1960 | 105 270 540 800 1050 1350 1600 2100 | 115 290 580 880 1150 1450 1750 2300
    125 315 630 950 1250 1600 1900 2500 | 135 340 680 1000 1350 1700 2050 2700 | 145 365 730 1100 1450 1800 2200 2900 | 155 390 780 1150 1550 1950 2350 3100
    165 415 830 1250 1650 2050 2500 3300 | 175 435 870 1300 1750 2200 2600 3500 | 185 460 920 1400 1850 2300 2750 3700 | 195 485 970 1450 1950 2400 2900 3900
    200 510 1000 1500 2000 2550 3050 4000 | 210 530 1050 1600 2100 2650 3150 4200 | 220 550 1100 1650 2200 2750 3300 4400 | 230 570 1150 1700 2300 2850 3400 4600
    235 590 1200 1750 2350 2950 3550 4700 | 245 610 1200 1850 2450 3050 3650 4900 | 250 630 1250 1900 2540 3150 3800 5080 | 270 670 1350 2000 2710 3350 4050 5420
    290 720 1450 2150 2900 3600 4350 5800 | 310 770 1550 2300 3100 3850 4650 6200 | 330 820 1650 2450 3300 4100 4950 6600 | 350 870 1750 2600 3500 4350 5250 7000
    370 920 1850 2750 3710 4600 5550 7420 | 390 980 1950 2900 3920 4900 5850 7840 | 410 1030 2050 3100 4140 5150 6200 8280 | 435 1090 2150 3250 4370 5450 6550 8740
    455 1140 2250 3400 4590 5700 6850 9180 | 480 1200 2400 3600 4820 6000 7200 9640 | 505 1260 2500 3750 5050 6300 7550 10100 | 525 1320 2600 3950 5290 6600 7900 10580
    550 1380 2750 4150 5540 6900 8300 11080 | 575 1440 2850 4300 5790 7200 8650 11580 | 600 1510 3000 4500 6040 7550 9050 12080 | 625 1570 3100 4700 6290 7850 9400 12580
    655 1630 3250 4900 6550 8150 9800 13100 | 680 1700 3400 5100 6810 8500 10200 13620 | 705 1760 3500 5300 7070 8800 10600 14140 | 730 1830 3650 5500 7340 9150 11000 14680
    760 1900 3800 5700 7610 9500 11400 15220 | 785 1970 3900 5900 7890 9850 11800 15780 | 815 2040 4050 6100 8170 10200 12250 16340 | 845 2110 4200 6300 8450 10550 12650 16900
    870 2180 4350 6500 8730 10900 13050 17460 | 900 2250 4500 6750 9020 11250 13500 18040 | 930 2320 4650 6950 9310 11600 13950 18620 | 955 2380 4750 7150 9550 11900 14300 19100
    970 2400 4850 7300 9800 12200 14700 19600 | 1000 2550 5000 7600 10050 12600 15050 20100 | 1050 2600 5250 7800 10400 12950 15550 20800 | 1080 2650 5400 8050 10750 13350 16000 21500
    1100 2700 5500 8250 11000 13750 16500 22000 | 1130 2850 5650 8550 11300 14150 17000 22600 | 1160 2900 5800 8750 11650 14600 17450 23300 | 1200 3050 6000 9000 12000 14950 17950 24000
    1230 3100 6150 9250 12300 15400 18450 24600 | 1250 3150 6250 9500 12650 15800 19000 25300 | 2000 5050 10050 15100 20100 25150 30150 40200 | 2050 5100 10150 15250 20300 25400 30450 40600
    2050 5150 10250 15400 20500 25650 30750 41000 | 2100 5200 10400 15550 20750 25950 31150 41500 | 2100 5250 10500 15700 20950 26200 31450 41900 | 2100 5300 10600 15850 21150 26450 31750 42300
    2150 5350 10700 16050 21400 26750 32100 42800 | 2150 5400 10800 16200 21600 27000 32400 43200 | 2200 5450 10900 16350 21800 27250 32700 43600 | 2200 5500 11050 16550 22050 27550 33100 44100
    2250 5550 11150 16700 22250 27800 33400 44500 | 2250 5650 11250 16900 22500 28150 33750 45000 | 2250 5700 11350 17050 22700 28400 34050 45400 | 2300 5750 11500 17200 22950 28700 34450 45900
    2300 5800 11600 17400 23200 29000 34800 46400 | 2350 5850 11700 17550 23400 29250 35100 46800 | 2350 5900 11850 17750 23650 29550 35500 47300 | 2400 6000 11950 17950 23900 29900 35850 47800
    2400 6050 12050 18100 24100 30150 36150 48200 | 2450 6100 12200 18250 24350 30450 36550 48700 | 2450 6150 12300 18450 24600 30750 36900 49200 | 2500 6200 12450 18650 24850 31050 37300 49700
    2500 6300 12550 18850 25100 31400 37650 50200 | 2550 6350 12700 19000 25350 31700 38050 50700 | 2550 6400 12800 19200 25600 32000 38400 51200 | 2600 6450 12950 19400 25850 32300 38800 51700
    2600 6550 13050 19600 26100 32650 39150 52200 | 2650 6600 13200 19750 26350 32950 39550 52700 | 2650 6650 13300 19950 26600 33250 39900 53200 | 2700 6700 13450 20150 26850 33550 40300 53700
'''
quest_xp_rows = [row.split() for row in QUEST_XP.replace('|', '\n').split('\n') if row.strip()]
assert len(quest_xp_rows) == 100 and all(len(row) == 8 for row in quest_xp_rows)
assert quest_xp_rows[59] == ['955', '2380', '4750', '7150', '9550', '11900', '14300', '19100']
tables = '\n'.join((
    'inline constexpr int64 IpQuestXp[][2]{' + ','.join(f'{{{a},{b}}}' for a, b in ip_values.items()) + '};',
    'inline constexpr int64 TbcQuestXp[][3]{' + ','.join(f'{{{a},{b},{c}}}' for a, (b, c) in tbc_values.items()) + '};',
    'inline constexpr int64 VanillaQuestLevels[][2]{' + ','.join(
        f'{{{a},{b}}}' for a, b in vanilla_levels.items()) + '};',
    'inline std::vector<std::vector<uint32>> const QuestXpRows{' + ','.join(
        '{' + ','.join(row) + '}' for row in quest_xp_rows) + '};',
    'struct QuestRow { uint32 id; int32 level; uint32 difficulty, flags, specialFlags; };',
    'inline std::vector<QuestRow> const QuestRows{' + quest_rows + '};',
))


def hook_declarations(path, names):
    text = read(path)
    return '\n'.join(re.search(rf'^ *virtual void {name}\(.*\{{ \}}$', text, re.MULTILINE)[0] for name in names)


def enum(text, name):
    return function(text, 'enum ' + name) + ';'


spell_auras = read('src/server/game/Spells/Auras/SpellAuraDefines.h')
assert re.search(r'SPELL_AURA_MOD_XP_PCT +=\s*200,', spell_auras)
assert re.search(r'SPELL_AURA_MOD_XP_QUEST_PCT +=\s*291,', spell_auras)
util = read('src/common/Utilities/Util.h')
header_declarations = between(ip_header, 'typedef std::unordered_map<uint32, uint32> questXpMapType;',
                              'Quest const* quest);')
stub = r'''
#pragma once
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <functional>
#include <iterator>
#include <iostream>
#include <list>
#include <map>
#include <memory>
#include <regex>
#include <set>
#include <sstream>
#include <string>
#include <type_traits>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>
using uint8=std::uint8_t; using uint16=std::uint16_t; using uint32=std::uint32_t; using uint64=std::uint64_t;
using int8=std::int8_t; using int32=std::int32_t; using int64=std::int64_t;
@PCT_TEMPLATES@
@PLAYER_XP_SOURCE@
@REST_STATE@
@PLAYER_HOOKS@
@WORLD_HOOKS@
@QUEST_STATUS@
@QUEST_FLAGS@
@QUEST_SPECIAL_FLAGS@
@MONEY@
enum AuraType { SPELL_AURA_MOD_XP_PCT=200, SPELL_AURA_MOD_XP_QUEST_PCT=291, TOTAL_AURAS=320 };
enum ServerConfigs { CONFIG_MAX_PLAYER_LEVEL, CONFIG_MAX_RECRUIT_A_FRIEND_BONUS_PLAYER_LEVEL,
    CONFIG_MAX_RECRUIT_A_FRIEND_BONUS_PLAYER_LEVEL_DIFFERENCE, RATE_REPUTATION_RECRUIT_A_FRIEND_BONUS, RATE_XP_QUEST,
    RATE_XP_QUEST_DF, RATE_REST_MAX_BONUS, RATE_REWARD_BONUS_MONEY };
enum UpdateFields { PLAYER_BYTES_2=1, PLAYER_NEXT_LEVEL_XP=2, PLAYER_REST_STATE_EXPERIENCE=3 };
struct World {
    std::map<int,uint32> ints; std::map<int,float> rates;
    // WorldConfig defaults, which Initialize restores before OnAfterConfigLoad.
    void Reset() {
        ints={{CONFIG_MAX_PLAYER_LEVEL,80},{CONFIG_MAX_RECRUIT_A_FRIEND_BONUS_PLAYER_LEVEL,60},
              {CONFIG_MAX_RECRUIT_A_FRIEND_BONUS_PLAYER_LEVEL_DIFFERENCE,4}};
        rates={{RATE_REPUTATION_RECRUIT_A_FRIEND_BONUS,0.1f},{RATE_XP_QUEST,1.0f},{RATE_XP_QUEST_DF,1.0f},
               {RATE_REST_MAX_BONUS,1.5f},{RATE_REWARD_BONUS_MONEY,1.0f}};
    }
    uint32 getIntConfig(ServerConfigs index) const { return ints.at(index); }
    void setIntConfig(ServerConfigs index,uint32 value) { ints[index]=value; }
    float getRate(ServerConfigs index) const { return rates.at(index); }
    void setRate(ServerConfigs index,float value) { rates[index]=value; }
};
inline World world;
inline World* sWorld=&world;
template<class... Args> void LogInfo(Args&&...) {}
#define LOG_INFO(...) LogInfo(__VA_ARGS__)
struct ConfigMgr {
    std::map<std::string,std::string> values;
    template<class T> T GetOption(std::string const& name,T const& def,bool=true) const {
        auto const value=values.find(name);
        if (value==values.end()) return def;
        if constexpr (std::is_same_v<T,std::string>) return value->second;
        else if constexpr (std::is_same_v<T,bool>) return value->second=="1";
        else if constexpr (std::is_floating_point_v<T>) return T(std::stof(value->second));
        else return T(std::stoul(value->second));
    }
};
inline ConfigMgr configMgr;
inline ConfigMgr* sConfigMgr=&configMgr;
struct Field { int64 value; template<class T> T Get() const { return T(value); } };
struct ResultSet {
    std::vector<std::vector<int64>> rows; std::size_t row=0;
    Field operator[](std::size_t index) const { return {rows[row].at(index)}; }
    bool NextRow() { return ++row<rows.size(); }
};
using QueryResult=std::shared_ptr<ResultSet>;
struct Database {
    std::map<std::string,std::vector<std::vector<int64>>> tables; std::vector<std::string> queries;
    template<std::size_t Columns,std::size_t Rows> void Set(std::string const& sql,int64 const (&rows)[Rows][Columns]) {
        for (auto const& row : rows) tables[sql].emplace_back(std::begin(row),std::end(row));
    }
    QueryResult Query(char const* sql) {
        queries.push_back(sql);
        auto const table=tables.find(sql);
        if (table==tables.end() || table->second.empty()) return nullptr;
        return std::make_shared<ResultSet>(ResultSet{table->second});
    }
};
inline Database WorldDatabase;
@QUEST_XP_ENTRY@
struct QuestXPStore {
    std::vector<QuestXPEntry> rows;
    QuestXPEntry const* LookupEntry(uint32 level) const { return level && level<=rows.size() ? &rows[level-1] : nullptr; }
};
inline QuestXPStore sQuestXPStore;
struct Quest {
    uint32 Id=0; int32 Level=1; uint32 RewardXPDifficulty=0, Flags=0, SpecialFlags=0;
    @QUEST_ACCESSORS@
    uint32 XPValue(uint8 playerLevel=0) const;
};
struct SpellInfo { uint32 Id=0; };
enum SpellGroup : uint32 {};
struct AuraEffect {
    SpellInfo info; int32 amount=0;
    uint32 GetId() const { return info.Id; }
    int32 GetAmount() const { return amount; }
    SpellInfo const* GetSpellInfo() const { return &info; }
};
using AuraEffectList=std::list<AuraEffect*>;
// Unit::GetTotalAuraMultiplier only stacks grouped spells; no experience aura is in a group.
struct SpellMgr {
    bool AddSameEffectStackRuleSpellGroups(SpellInfo const*,uint32,int32,std::map<SpellGroup,int32>&) const { return false; }
};
inline SpellMgr spellMgr;
inline SpellMgr* sSpellMgr=&spellMgr;
struct Unit {
    AuraEffectList m_modAuras[TOTAL_AURAS];
    AuraEffectList const& GetAuraEffectsByType(AuraType type) const { return m_modAuras[type]; }
    float GetTotalAuraMultiplier(AuraType auratype) const;
    float GetTotalAuraMultiplier(AuraType auraType,std::function<bool(AuraEffect const*)> const& predicate) const;
};
struct WorldSession {
    uint32 account=1, recruiter=0; bool recruits=false, bot=false;
    uint32 GetAccountId() const { return account; }
    uint32 GetRecruiterId() const { return recruiter; }
    bool IsARecruiter() const { return recruits; }
};
struct Player;
struct GroupReference {
    Player* player=nullptr; GroupReference* following=nullptr;
    Player* GetSource() const { return player; }
    GroupReference* next() const { return following; }
};
struct Group {
    std::vector<GroupReference> members;
    void Set(std::vector<Player*> const& players) {
        members.assign(players.size(),{});
        for (std::size_t i=0;i<players.size();++i) members[i]={players[i],i+1<players.size() ? &members[i+1] : nullptr};
    }
    GroupReference* GetFirstMember() { return members.empty() ? nullptr : &members[0]; }
};
struct Player : Unit {
    uint8 level=1; bool inWorld=true; mutable WorldSession session; Group* group=nullptr; float _restBonus=0;
    int64 money=0; std::unordered_set<uint32> m_RewardedQuests; std::map<uint32,uint32> fields;
    std::map<std::pair<uint32,uint8>,uint8> bytes;
    uint8 GetLevel() const { return level; }
    bool IsInWorld() const { return inWorld; }
    WorldSession* GetSession() const { return &session; }
    Group* GetGroup() const { return group; }
    bool IsInMap(Player const*) const { return true; }
    bool IsAtRecruitAFriendDistance(Player const*) const { return true; }
    @QUEST_REWARDED@
    uint8 GetQuestStatus(uint32 id) const { return IsQuestRewarded(id) ? QUEST_STATUS_REWARDED : QUEST_STATUS_NONE; }
    void SetRewardedQuest(uint32 id) { m_RewardedQuests.insert(id); }
    void RemoveRewardedQuest(uint32 id,bool=true) { m_RewardedQuests.erase(id); }
    float GetRestBonus() const { return _restBonus; }
    void SetRestBonus(float restBonusNew);
    bool GetsRecruitAFriendBonus(bool forXP);
    uint32 CalculateQuestRewardXP(Quest const* quest);
    float GetQuestRate(bool isDFQuest=false);
    uint32 GetUInt32Value(uint16 index) const { auto const value=fields.find(index); return value==fields.end() ? 0 : value->second; }
    void SetUInt32Value(uint16 index,uint32 value) { fields[index]=value; }
    void SetByteValue(uint16 index,uint8 offset,uint8 value) { bytes[{index,offset}]=value; }
    void ModifyMoney(int64 change) { money+=change; }
    uint32 RewardQuestXP(Quest const* quest);
};
struct Creature; struct ObjectGuid { using LowType=uint32; };
struct ChatHandler {
    explicit ChatHandler(WorldSession*) {}
    void SendSysMessage(char const*) {}
    template<class... Args> void PSendSysMessage(char const*,Args&&...) {}
};
struct AccountMgr {
    static bool GetName(uint32 account,std::string& name) { name=account>=1000 ? "RNDBOT"+std::to_string(account) : "PLAYER"; return true; }
};
class PlayerScript {
public:
    std::string name; std::vector<uint16> hooks;
    PlayerScript(char const* scriptName,std::vector<uint16> enabledHooks=std::vector<uint16>());
    virtual ~PlayerScript()=default;
    bool Enabled(uint16 hook) const;
@PLAYER_SCRIPT_HOOKS@
};
class WorldScript {
public:
    std::string name; std::vector<uint16> hooks;
    WorldScript(char const* scriptName,std::vector<uint16> enabledHooks=std::vector<uint16>());
    virtual ~WorldScript()=default;
@WORLD_SCRIPT_HOOKS@
};
inline std::vector<PlayerScript*> playerScripts;
inline std::vector<WorldScript*> worldScripts;
// The era scripts can be left out to observe the realm without them.
inline bool eraScripts=true;
inline PlayerScript::PlayerScript(char const* scriptName,std::vector<uint16> enabledHooks)
    : name(scriptName), hooks(std::move(enabledHooks)) { playerScripts.push_back(this); }
inline WorldScript::WorldScript(char const* scriptName,std::vector<uint16> enabledHooks)
    : name(scriptName), hooks(std::move(enabledHooks)) { worldScripts.push_back(this); }
// An empty list enables every hook, as ScriptRegistry does.
inline bool PlayerScript::Enabled(uint16 hook) const {
    return (eraScripts || name.rfind("IndividualProgressionEra",0)!=0) &&
           (hooks.empty() || std::find(hooks.begin(),hooks.end(),hook)!=hooks.end());
}
#define EACH_PLAYER_SCRIPT(hook, call) for (PlayerScript* script : playerScripts) if (script->Enabled(hook)) script->call;
struct ScriptMgr {
    bool moneyInsteadOfXp=false;
    void OnPlayerBeforeGetLevelForXPGain(Player const*,uint8&) {}
    void OnPlayerGetQuestRate(Player*,float&) {}
    bool OnPlayerShouldBeRewardedWithMoneyInsteadOfExp(Player*) { return moneyInsteadOfXp; }
    void OnPlayerQuestComputeXP(Player* player,Quest const* quest,uint32& xp) {
        EACH_PLAYER_SCRIPT(PLAYERHOOK_ON_QUEST_COMPUTE_EXP, OnPlayerQuestComputeXP(player,quest,xp))
    }
    void OnPlayerGiveXP(Player* player,uint32& amount,struct Unit* victim,uint8 source) {
        EACH_PLAYER_SCRIPT(PLAYERHOOK_ON_GIVE_EXP, OnPlayerGiveXP(player,amount,victim,source))
    }
    void OnPlayerLogin(Player* player) { EACH_PLAYER_SCRIPT(PLAYERHOOK_ON_LOGIN, OnPlayerLogin(player)) }
    void OnPlayerLevelChanged(Player* player,uint8 old) { EACH_PLAYER_SCRIPT(PLAYERHOOK_ON_LEVEL_CHANGED, OnPlayerLevelChanged(player,old)) }
    void OnPlayerCompleteQuest(Player* player,Quest const* quest) {
        EACH_PLAYER_SCRIPT(PLAYERHOOK_ON_PLAYER_COMPLETE_QUEST, OnPlayerCompleteQuest(player,quest))
    }
    void OnAfterConfigLoad(bool reload) {
        for (WorldScript* script : worldScripts)
            if ((eraScripts || script->name.rfind("IndividualProgressionEra",0)!=0) &&
                (script->hooks.empty() || std::find(script->hooks.begin(),script->hooks.end(),WORLDHOOK_ON_AFTER_CONFIG_LOAD)!=script->hooks.end()))
                script->OnAfterConfigLoad(reload);
    }
};
inline ScriptMgr scriptMgr;
inline ScriptMgr* sScriptMgr=&scriptMgr;
@HEADER_DECLARATIONS@
@PROGRESSION_ENUMS@
@INDIVIDUAL_PROGRESSION_CLASS@
#define sIndividualProgression IndividualProgression::instance()
'''

quest_accessors = '\n'.join(
    re.search(rf'^ *\[\[nodiscard\]\] [^\n]*\b{re.escape(name)} const \{{[^\n]*\}}$', quest_h, re.MULTILINE)[0]
    for name in ('GetQuestId()', 'GetQuestLevel()', 'HasFlag(uint32 flag)', 'IsDaily()', 'IsWeekly()', 'IsMonthly()',
                 'IsDFQuest()'))
replacements = {
    '@PCT_TEMPLATES@': '\n\n'.join(
        between(util, 'template <class T, class U>\ninline T ' + name + '(', '\n}') for name in ('CalculatePct', 'AddPct')),
    '@PLAYER_XP_SOURCE@': enum(player_h, 'PlayerXPSource'),
    '@REST_STATE@': enum(player_h, 'PlayerRestState'),
    '@PLAYER_HOOKS@': enum(read('src/server/game/Scripting/ScriptDefines/PlayerScript.h'), 'PlayerHook'),
    '@WORLD_HOOKS@': enum(read('src/server/game/Scripting/ScriptDefines/WorldScript.h'), 'WorldHook'),
    '@QUEST_STATUS@': enum(quest_h, 'QuestStatus : uint8'),
    '@QUEST_FLAGS@': enum(quest_h, 'QuestFlags'),
    '@QUEST_SPECIAL_FLAGS@': enum(quest_h, 'QuestSpecialFlags'),
    '@MONEY@': enum(read('src/server/shared/SharedDefines.h'), 'MoneyConstants'),
    '@QUEST_XP_ENTRY@': function(
        read('src/server/shared/DataStores/DBCStructure.h'), 'struct QuestXPEntry') + ';',
    '@QUEST_ACCESSORS@': quest_accessors,
    '@QUEST_REWARDED@': function(player_h, '    [[nodiscard]] bool IsQuestRewarded('),
    '@PLAYER_SCRIPT_HOOKS@': hook_declarations('src/server/game/Scripting/ScriptDefines/PlayerScript.h', (
        'OnPlayerQuestComputeXP', 'OnPlayerGiveXP', 'OnPlayerLogin', 'OnPlayerLevelChanged', 'OnPlayerCompleteQuest')),
    '@WORLD_SCRIPT_HOOKS@': hook_declarations('src/server/game/Scripting/ScriptDefines/WorldScript.h', ('OnAfterConfigLoad',)),
    '@HEADER_DECLARATIONS@': header_declarations,
    '@PROGRESSION_ENUMS@': enum(ip_header, 'ProgressionState : uint8') + '\n' + enum(ip_header, 'ProgressionQuestIDs'),
    '@INDIVIDUAL_PROGRESSION_CLASS@': function(ip_header, 'class IndividualProgression\n') + ';',
}
for placeholder, text in replacements.items():
    assert stub.count(placeholder) == 1, placeholder
    stub = stub.replace(placeholder, text)

legacy_hooks = '\n'.join(function(ip_player, signature) for signature in (
    '    void OnPlayerQuestComputeXP(', '    void OnPlayerCompleteQuest('))
core_functions = '\n'.join((
    function(read('src/server/game/Quests/QuestDef.cpp'), 'uint32 Quest::XPValue('),
    function(quest_cpp, 'uint32 Player::CalculateQuestRewardXP('),
    function(player_cpp, 'float Player::GetQuestRate('),
    function(unit_cpp, 'float Unit::GetTotalAuraMultiplier(AuraType auraType, std::function'),
    function(unit_cpp, 'float Unit::GetTotalAuraMultiplier(AuraType auraType) const'),
    function(player_cpp, 'void Player::SetRestBonus('),
    function(player_cpp, 'bool Player::GetsRecruitAFriendBonus('),
))
ip_functions = '\n'.join(function(ip_source, signature) for signature in (
    'IndividualProgression* IndividualProgression::instance()',
    'uint8 IndividualProgression::GetPlayerProgressionFromQuests(',
    'bool IndividualProgression::IsStrictDefaultProgression(',
    'uint8 IndividualProgression_GetEarnedEra(',
    'bool IndividualProgression::hasPassedProgression(',
    'bool IndividualProgression::isExcludedAccount(',
    'bool IndividualProgression::isBotAccount(',
    'bool IndividualProgression::isNormalAccount(',
    'void IndividualProgression::LoadCustomProgressionEntries(',
))
world_loading = function(ip_source, '    static void LoadConfig()') + '\n' + load_xp

tests = r'''
#include "EraExperience.cpp"

@TABLES@
@CORE_FUNCTIONS@
@IP_FUNCTIONS@
int progressionUpdates=0;
void IndividualProgression::UpdateProgressionState(Player*,ProgressionState) const { ++progressionUpdates; }
void IndividualProgression::checkIPProgression(Player*) { ++progressionUpdates; }

class IndividualPlayerProgression : public PlayerScript
{
public:
    IndividualPlayerProgression() : PlayerScript("IndividualProgression") { }
@LEGACY_HOOKS@
};

struct IndividualPlayerProgression_WorldScript
{
@WORLD_LOADING@
};

uint32 Player::RewardQuestXP(Quest const* quest)
{
    uint32 const quest_id = quest->GetQuestId();
@REWARD_XP@
    return XP;
}

uint32 WindowXP(Player* player, Quest const* quest)
{
@WINDOW_XP@
    return questXp;
}

uint32 KillXP(Player* player, uint32 xp)
{
    Unit* _victim = nullptr;
    if (xp)
    {
@KILL_XP@
    }
    return xp;
}

std::map<uint32,Quest> quests;
Quest const& Q(uint32 id) { return quests.at(id); }
void AddQuest(uint32 id,int32 level,uint32 difficulty=5,uint32 flags=0) {
    Quest quest; quest.Id=id; quest.Level=level; quest.RewardXPDifficulty=difficulty; quest.Flags=flags;
    quests[id]=quest;
}
// Fixture-only quests with Individual Progression or TBC values that exercise the rules.
void AddSyntheticValues() {
    for (auto [id,value] : std::vector<std::pair<uint32,uint32>>{
         {90001,1001},{90002,500},{90003,3000},{90004,5000},{90006,3000},{90007,700},{90008,1000}})
        sIndividualProgression->questXpMap[id]=value;
    sIndividualProgression->questXpTbcMap[90005]=9000;
}

void Configure(std::map<std::string,std::string> values) {
    configMgr.values=std::move(values);
    world.Reset();
    WorldDatabase.queries.clear();
    IndividualPlayerProgression_WorldScript::LoadConfig();
    IndividualPlayerProgression_WorldScript::LoadXpValues();
    sScriptMgr->OnAfterConfigLoad(true);
    AddSyntheticValues();
}
std::map<std::string,std::string> Active() { return {{"IndividualProgression.StrictEarnedProgression","1"}}; }
std::map<std::string,std::string> OptionOff() {
    return {{"IndividualProgression.StrictEarnedProgression","1"},{"IndividualProgression.EraExperience","0"}};
}
std::map<std::string,std::string> StrictOff() { return {{"IndividualProgression.EraExperience","1"}}; }

AuraEffect heirloomKill{{57353},10}, heirloomQuest{{57353},10}, wickerman{{24705},10}, transform{{69711},-100},
    penaltyKill{{99001},-50}, penaltyQuest{{99001},-50};
bool bot=false;
Player Character(uint8 stage,uint8 level) {
    Player player; player.level=level;
    for (uint8 marker=1;marker<=stage;++marker) if (marker!=11) player.SetRewardedQuest(66000+marker);
    if (bot) { player.session.bot=true; player.session.account=1001; }
    player.SetUInt32Value(PLAYER_NEXT_LEVEL_XP,400000);
    return player;
}
uint32 TurnIn(Player& player,Quest const& quest) {
    uint32 const xp=player.RewardQuestXP(&quest);
    player.SetRewardedQuest(quest.GetQuestId());
    sScriptMgr->OnPlayerCompleteQuest(&player,&quest);
    return xp;
}
uint32 GiveXP(Player& player,uint32 xp,uint8 source) { sScriptMgr->OnPlayerGiveXP(&player,xp,nullptr,source); return xp; }
bool Rested(Player const& player,float rest) {
    return player.GetRestBonus()==rest && player.GetUInt32Value(PLAYER_REST_STATE_EXPERIENCE)==uint32(rest) &&
           player.bytes.at({PLAYER_BYTES_2,3})==(rest>10 ? REST_STATE_RESTED : REST_STATE_NOT_RAF_LINKED);
}
int64 Money(uint8 stage,uint8 level,uint32 id) {
    Player player=Character(stage,level);
    TurnIn(player,Q(id));
    return player.money;
}

void QuestCases() {
    Player vanilla30=Character(0,30), vanilla36=Character(0,36), tbc60=Character(8,60), wrath70=Character(13,70);
    assert(TurnIn(vanilla30,Q(2))==2450 && TurnIn(vanilla36,Q(2))==1960 && TurnIn(tbc60,Q(2))==250);
    assert(TurnIn(wrath70,Q(2))==wrath70.CalculateQuestRewardXP(&Q(2)) && wrath70.CalculateQuestRewardXP(&Q(2))==250);
    Player tbc=Character(8,60), wrath=Character(13,70);
    assert(WindowXP(&tbc,&Q(1318))==8250 && TurnIn(tbc,Q(1318))==8250);
    assert(TurnIn(wrath,Q(1318))==1450 && wrath.CalculateQuestRewardXP(&Q(1318))==1450);
    // 2881 pays nothing natively; its Individual Progression value applies on first completions.
    sIndividualProgression->repeatableVanillaQuestsXp=false;
    Player necklace=Character(0,45);
    assert(necklace.CalculateQuestRewardXP(&Q(2881))==0 && WindowXP(&necklace,&Q(2881))==390);
    assert(TurnIn(necklace,Q(2881))==390 && WindowXP(&necklace,&Q(2881))==0 && TurnIn(necklace,Q(2881))==0);
    sIndividualProgression->repeatableVanillaQuestsXp=true;
    assert(TurnIn(necklace,Q(2881))==0 && !necklace.IsQuestRewarded(2881) && TurnIn(necklace,Q(2881))==390);
    Player tbcNecklace=Character(8,60), morrowgrain=Character(0,55), tbcMorrowgrain=Character(8,60);
    assert(TurnIn(tbcNecklace,Q(2881))==0 && TurnIn(morrowgrain,Q(3803))==560 && TurnIn(tbcMorrowgrain,Q(3803))==4700);
    assert(TurnIn(tbcMorrowgrain,Q(3803))==4700);
    // Reductions count from the quest level of the value's era: Rise, Obsidion! is level 52
    // in 1.12 and 46 in 3.3.5, Rage of Blood level 58 in 2.4.3 and -1 in 3.3.5.
    Player obsidion=Character(0,56), rage=Character(8,64);
    assert(TurnIn(obsidion,Q(3566))==7600 && TurnIn(rage,Q(7563))==6200);
    // Rounding up, quests without a level, dailies and quests without any table value.
    Player vanilla46=Character(0,46), vanilla40=Character(0,40), rewardedDaily=Character(0,40);
    assert(TurnIn(vanilla46,Q(90001))==801 && TurnIn(vanilla40,Q(90002))==500);
    rewardedDaily.SetRewardedQuest(90007);
    assert(TurnIn(rewardedDaily,Q(90007))==700 && TurnIn(rewardedDaily,Q(90007))==700);
    Player lesson=Character(0,20);
    assert(TurnIn(lesson,Q(26))==lesson.CalculateQuestRewardXP(&Q(26)) && lesson.CalculateQuestRewardXP(&Q(26))>0);
    // Experience the core withholds stays withheld.
    Player money30=Character(0,30), money60=Character(8,60);
    assert(WindowXP(&money30,&Q(2))==2450 && WindowXP(&money60,&Q(1318))==8250);
    sScriptMgr->moneyInsteadOfXp=true;
    assert(WindowXP(&money30,&Q(2))==0 && WindowXP(&money60,&Q(1318))==0);
    sScriptMgr->moneyInsteadOfXp=false;
    world.rates[RATE_XP_QUEST]=1.5f;
    Player rated=Character(0,30);
    assert(TurnIn(rated,Q(2))==3675);
    world.rates[RATE_XP_QUEST]=0.0f;
    Player unrated=Character(0,30);
    assert(TurnIn(unrated,Q(2))==0);
    world.rates[RATE_XP_QUEST]=1.0f;
    // Characters outside the world keep the core value.
    Player loading=Character(8,60); loading.inWorld=false;
    assert(loading.RewardQuestXP(&Q(1318))==14300);
    // Quest auras: heirlooms only in Wrath, penalties in every era.
    for (uint8 stage : {0,8,13}) {
        Player heirloom=Character(stage,stage==13 ? 70 : stage==8 ? 60 : 30);
        heirloom.m_modAuras[SPELL_AURA_MOD_XP_QUEST_PCT].push_back(&heirloomQuest);
        uint32 const expected=stage==13 ? heirloom.CalculateQuestRewardXP(&Q(2)) : stage==8 ? 250 : 2450;
        assert(TurnIn(heirloom,Q(2))==expected && (stage!=13 || expected==275));
    }
    Player penalized=Character(0,40);
    penalized.m_modAuras[SPELL_AURA_MOD_XP_QUEST_PCT].push_back(&penaltyQuest);
    assert(TurnIn(penalized,Q(90008))==500);
    // The legacy ratio does not apply on top of era values.
    uint32 value=1000;
    IndividualPlayerProgression legacy;
    playerScripts.pop_back();
    legacy.OnPlayerQuestComputeXP(&tbc60,&Q(1318),value);
    assert(value==1000);
    // Without a table value the result equals the core's calculation.
    AddQuest(95000,1);
    Quest& unlisted=quests.at(95000);
    for (float rate : {1.0f,1.5f}) {
        world.rates[RATE_XP_QUEST]=rate;
        for (uint8 stage : {0,8}) for (uint8 level=1;level<=80;++level) {
            Player player=Character(stage,level);
            for (int32 questLevel=1;questLevel<=80;++questLevel) for (uint32 difficulty=0;difficulty<=8;++difficulty) {
                unlisted.Level=questLevel; unlisted.RewardXPDifficulty=difficulty;
                assert(player.RewardQuestXP(&unlisted)==player.CalculateQuestRewardXP(&unlisted));
            }
        }
    }
    world.rates[RATE_XP_QUEST]=1.0f;
}

void KillCases() {
    for (uint8 stage : {0,8,13}) {
        uint8 const level=stage==13 ? 70 : stage==8 ? 60 : 30;
        Player heirloom=Character(stage,level), holiday=Character(stage,level), transformed=Character(stage,level),
            plain=Character(stage,level), penalized=Character(stage,level);
        heirloom.m_modAuras[SPELL_AURA_MOD_XP_PCT].push_back(&heirloomKill);
        holiday.m_modAuras[SPELL_AURA_MOD_XP_PCT]={&wickerman,&heirloomKill};
        transformed.m_modAuras[SPELL_AURA_MOD_XP_PCT]={&heirloomKill,&transform};
        penalized.m_modAuras[SPELL_AURA_MOD_XP_PCT]={&heirloomKill,&penaltyKill};
        assert(KillXP(&heirloom,200)==(stage==13 ? 220u : 200u));
        assert(KillXP(&holiday,200)==(stage==13 ? 242u : stage==8 ? 220u : 200u));
        assert(KillXP(&transformed,200)==0 && KillXP(&plain,200)==200);
        assert(KillXP(&penalized,200)==(stage==13 ? 110u : 100u));
        // Objective experience is Wrath content; kills, quests and exploration are unchanged here.
        assert(GiveXP(plain,500,XPSOURCE_BATTLEGROUND)==(stage==13 ? 500u : 0u));
        assert(GiveXP(plain,500,XPSOURCE_KILL)==500 && GiveXP(heirloom,500,XPSOURCE_QUEST)==500);
        assert(GiveXP(heirloom,500,XPSOURCE_EXPLORE)==500);
    }
}

void RestCases() {
    struct Case { uint8 stage, level; bool cleared; };
    for (Case entry : std::vector<Case>{{0,59,false},{0,60,true},{8,60,false},{8,69,false},{8,70,true},{13,70,false}}) {
        Player player=Character(entry.stage,entry.level);
        player.SetRestBonus(5000);
        assert(Rested(player,5000)); // the core keeps rest below MaxPlayerLevel
        sScriptMgr->OnPlayerLogin(&player);
        assert(Rested(player,entry.cleared ? 0 : 5000));
    }
    Player reaching=Character(0,59);
    reaching.SetRestBonus(5000);
    reaching.level=60;
    sScriptMgr->OnPlayerLevelChanged(&reaching,59);
    assert(Rested(reaching,0));
    Player tbcReaching=Character(8,69);
    tbcReaching.SetRestBonus(5000);
    tbcReaching.level=70;
    sScriptMgr->OnPlayerLevelChanged(&tbcReaching,69);
    assert(Rested(tbcReaching,0));
    // Rest gathered in an inn at the cap is gone once the next era is earned.
    Player capped=Character(7,60), cappedTbc=Character(12,70), below=Character(7,59);
    for (Player* player : {&capped,&cappedTbc,&below}) player->SetRestBonus(5000);
    TurnIn(capped,Q(2));
    assert(Rested(capped,5000));
    TurnIn(capped,Q(66008));
    TurnIn(cappedTbc,Q(66013));
    TurnIn(below,Q(66008));
    assert(Rested(capped,0) && Rested(cappedTbc,0) && Rested(below,5000));
}

void MoneyCases() {
    assert(Money(0,60,90003)==1875 && Money(0,60,90004)==31250 && Money(8,70,90005)==54000);
    assert(Money(13,70,90005)==0 && Money(0,59,90003)==0 && Money(0,60,90006)==0 && Money(8,60,90003)==0);
    world.rates[RATE_REWARD_BONUS_MONEY]=2.0f;
    assert(Money(0,60,90003)==3750);
    world.rates[RATE_REWARD_BONUS_MONEY]=1.0f;
    world.ints[CONFIG_MAX_PLAYER_LEVEL]=60;
    assert(Money(0,60,90003)==0);
    world.ints[CONFIG_MAX_PLAYER_LEVEL]=80;
}

void RecruitCases(bool active) {
    Player recruit=Character(0,30), recruiter=Character(0,30);
    recruit.session.recruiter=2; recruiter.session.account=2; recruiter.session.recruits=true;
    Group group; group.Set({&recruit,&recruiter}); recruit.group=&group; recruiter.group=&group;
    assert(recruit.GetsRecruitAFriendBonus(true)==!active && recruiter.GetsRecruitAFriendBonus(true)==!active);
    assert(world.getIntConfig(CONFIG_MAX_RECRUIT_A_FRIEND_BONUS_PLAYER_LEVEL)==(active ? 0u : 60u));
    assert(world.getRate(RATE_REPUTATION_RECRUIT_A_FRIEND_BONUS)==(active ? 0.0f : 0.1f));
    recruit.SetRestBonus(5000);
    assert(recruit.bytes.at({PLAYER_BYTES_2,3})==(active ? REST_STATE_RESTED : REST_STATE_RAF_LINKED));
}

std::size_t EraTableQueries() {
    return std::count_if(WorldDatabase.queries.begin(),WorldDatabase.queries.end(),[](std::string const& query) {
        return query=="SELECT entry, xpValue, questLevel FROM custom_quest_xp_tbc" ||
               query=="SELECT entry, questLevel FROM custom_quest_xp_level";
    });
}

void ConfigCases() {
    Configure(Active());
    assert(sIndividualProgression->eraExperience && sIndividualProgression->EraExperienceActive());
    assert(sIndividualProgression->questXpTbcMap.size()==std::size(TbcQuestXp)+1);
    assert(sIndividualProgression->questLevelTbcMap.size()==std::size(TbcQuestXp));
    assert(sIndividualProgression->questLevelMap.size()==std::size(VanillaQuestLevels));
    assert(EraTableQueries()==2);
    RecruitCases(true);
    for (auto values : {OptionOff(),StrictOff()}) {
        Configure(values);
        assert(sIndividualProgression->questXpTbcMap.size()==1 && !sIndividualProgression->EraExperienceActive());
        assert(sIndividualProgression->questLevelTbcMap.empty() && sIndividualProgression->questLevelMap.empty());
        assert(EraTableQueries()==0);
        RecruitCases(false);
    }
    auto noFix=Active(); noFix["IndividualProgression.QuestXPFix"]="0";
    Configure(noFix);
    assert(sIndividualProgression->questXpTbcMap.size()==1 && sIndividualProgression->EraExperienceActive());
    assert(sIndividualProgression->questLevelTbcMap.empty() && sIndividualProgression->questLevelMap.empty());
    // Without historical values every era keeps the native quest value.
    Player tbc=Character(8,60), vanilla=Character(0,30);
    assert(TurnIn(tbc,Q(1318))==14300 && TurnIn(vanilla,Q(2))==2450);
    Configure(Active());
}

// Everything observable about experience, for comparing the realm with and without the era scripts.
std::vector<int64> Observe() {
    std::vector<int64> seen;
    for (uint8 stage : {0,7,8,12,13}) for (uint8 level : {30,36,45,59,60,69,70}) {
        for (uint32 id : {2u,26u,1318u,2881u,3566u,3803u,7563u,9492u,90001u,90002u,90003u,90005u,90006u,90007u}) {
            Player player=Character(stage,level), aura=Character(stage,level);
            aura.m_modAuras[SPELL_AURA_MOD_XP_QUEST_PCT]={&heirloomQuest,&penaltyQuest};
            seen.insert(seen.end(),{WindowXP(&player,&Q(id)),TurnIn(player,Q(id)),TurnIn(player,Q(id)),player.money,
                                    TurnIn(aura,Q(id))});
        }
        Player kill=Character(stage,level);
        kill.m_modAuras[SPELL_AURA_MOD_XP_PCT]={&wickerman,&heirloomKill,&penaltyKill};
        seen.insert(seen.end(),{KillXP(&kill,200),GiveXP(kill,500,XPSOURCE_BATTLEGROUND),GiveXP(kill,500,XPSOURCE_KILL)});
        Player rest=Character(stage,level);
        rest.SetRestBonus(5000);
        sScriptMgr->OnPlayerLogin(&rest);
        sScriptMgr->OnPlayerLevelChanged(&rest,level);
        TurnIn(rest,Q(66008));
        TurnIn(rest,Q(66013));
        seen.insert(seen.end(),{int64(rest.GetRestBonus()),rest.bytes.at({PLAYER_BYTES_2,3})});
    }
    seen.insert(seen.end(),{world.getIntConfig(CONFIG_MAX_RECRUIT_A_FRIEND_BONUS_PLAYER_LEVEL),
                            int64(world.getRate(RATE_REPUTATION_RECRUIT_A_FRIEND_BONUS)*10)});
    return seen;
}

void InactiveCases(std::map<std::string,std::string> const& values) {
    eraScripts=false;
    Configure(values);
    std::vector<int64> const without=Observe();
    eraScripts=true;
    Configure(values);
    assert(Observe()==without);
    // Individual Progression's per-quest ratio keeps today's values.
    Player vanilla=Character(0,36), tbc=Character(8,60), necklace=Character(0,45);
    assert(TurnIn(vanilla,Q(2))==1950 && TurnIn(tbc,Q(1318))==8250 && TurnIn(necklace,Q(2881))==0);
    bool const strict=sIndividualProgression->IsStrictDefaultProgression();
    assert(Money(0,60,90003)==int64(Q(90003).XPValue(40))*6 || !strict);
}

int main() {
    for (uint32 level=1;level<=QuestXpRows.size();++level) {
        QuestXPEntry entry{level,{}};
        for (std::size_t i=0;i<8;++i) entry.Exp[i+1]=QuestXpRows[level-1][i];
        sQuestXPStore.rows.push_back(entry);
    }
    for (QuestRow const& row : QuestRows) {
        AddQuest(row.id,row.level,row.difficulty,row.flags);
        quests[row.id].SpecialFlags=row.specialFlags;
    }
    AddQuest(90001,40); AddQuest(90002,-1); AddQuest(90003,40); AddQuest(90004,58); AddQuest(90005,65);
    AddQuest(90006,40,5,QUEST_FLAGS_NO_MONEY_FROM_XP); AddQuest(90007,40,5,QUEST_FLAGS_DAILY); AddQuest(90008,40);
    // Individual Progression's player_progression.sql markers for TBC and Wrath.
    AddQuest(66008,60,0,1024); AddQuest(66013,60,0,1024);
    WorldDatabase.Set("SELECT entry, xpValue FROM custom_quest_xp",IpQuestXp);
    WorldDatabase.Set("SELECT entry, xpValue, questLevel FROM custom_quest_xp_tbc",TbcQuestXp);
    WorldDatabase.Set("SELECT entry, questLevel FROM custom_quest_xp_level",VanillaQuestLevels);
    AddSC_individual_progression_era_experience();
    new IndividualPlayerProgression();
    assert(playerScripts.size()==2 && playerScripts[0]->name=="IndividualProgressionEraExperience");
    assert((playerScripts[0]->hooks==std::vector<uint16>{PLAYERHOOK_ON_GIVE_EXP,PLAYERHOOK_ON_QUEST_COMPUTE_EXP,
        PLAYERHOOK_ON_LOGIN,PLAYERHOOK_ON_LEVEL_CHANGED,PLAYERHOOK_ON_PLAYER_COMPLETE_QUEST}));
    assert(worldScripts.size()==1 && worldScripts[0]->hooks==std::vector<uint16>{WORLDHOOK_ON_AFTER_CONFIG_LOAD});
    ConfigCases();
    for (bool session : {false,true}) {
        bot=session;
        Configure(Active());
        QuestCases(); KillCases(); RestCases(); MoneyCases();
    }
    for (auto const& values : {OptionOff(),StrictOff()}) for (bool session : {false,true}) {
        bot=session;
        InactiveCases(values);
    }
    for (PlayerScript* script : playerScripts) delete script;
    for (WorldScript* script : worldScripts) delete script;
    std::cout << "Era experience: quest values, withheld and repeated rewards, auras, battleground XP, rest, "
                 "era-cap money, Recruit-a-Friend and configuration passed for players and bots; nothing changes "
                 "with the option or strict progression off\n";
}
'''

for placeholder, text in (('@TABLES@', tables), ('@CORE_FUNCTIONS@', core_functions), ('@IP_FUNCTIONS@', ip_functions),
                          ('@LEGACY_HOOKS@', legacy_hooks), ('@WORLD_LOADING@', world_loading),
                          ('@REWARD_XP@', reward_xp), ('@WINDOW_XP@', window_xp), ('@KILL_XP@', kill_xp)):
    assert tests.count(placeholder) == 1, placeholder
    tests = tests.replace(placeholder, text)


def build(directory, executable):
    return [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-g', *SANITIZER_FLAGS, '-I', str(directory),
            str(directory / 'fixture.cpp'), '-o', str(executable)]


MUTATIONS = (
    ('option ignored', 'IndividualProgression.h', 'return eraExperience && IsStrictDefaultProgression();',
     'return IsStrictDefaultProgression();'),
    ('strict progression ignored', 'IndividualProgression.h', 'return eraExperience && IsStrictDefaultProgression();',
     'return eraExperience;'),
    ('unavailable era as Vanilla', 'EraExperience.cpp', 'return EraExperiencePolicy::NoEra;',
     'return EraExperiencePolicy::Vanilla;'),
    ('hook registration', 'EraExperience.cpp', 'PLAYERHOOK_ON_QUEST_COMPUTE_EXP, PLAYERHOOK_ON_LOGIN,',
     'PLAYERHOOK_ON_QUEST_COMPUTE_EXP,'),
    ('repeat rule', 'EraExperience.cpp', 'bool const rewarded = player->IsQuestRewarded(', 'bool const rewarded = false && player->IsQuestRewarded('),
    ('withheld reward', 'EraExperience.cpp', '(!xpValue && quest->XPValue(level))', '(false && quest->XPValue(level))'),
    ('TBC table ignored', 'EraExperience.cpp', 'era == EraExperiencePolicy::TBC && tbc.count(id)',
     'era == EraExperiencePolicy::Wrath && tbc.count(id)'),
    ('Wrath not skipped', 'EraExperience.cpp', 'era > EraExperiencePolicy::TBC)\n            return;',
     'era > EraExperiencePolicy::Wrath)\n            return;'),
    ('reduction threshold', 'EraExperiencePolicy.h', 'if (above <= 5)', 'if (above <= 6)'),
    ('reduction rounding', 'EraExperiencePolicy.h', '* tenths + 9) / 10', '* tenths) / 10'),
    ('quest level -1', 'EraExperiencePolicy.h', '(questLevel > 0 ? questLevel : std::int32_t(level))', '(questLevel)'),
    ('tables without QuestXPFix', 'EraExperience.cpp', 'if (!sIndividualProgression->questXpFix)\n        return quest->XPValue(level);\n',
     ''),
    ('legacy ratio on era values', 'fixture.cpp',
     'if (!sIndividualProgression->questXpFix || sIndividualProgression->EraExperienceActive())',
     'if (!sIndividualProgression->questXpFix)'),
    ('battleground source', 'EraExperience.cpp', 'if (xpSource == XPSOURCE_BATTLEGROUND)\n        {', 'if (true)\n        {'),
    ('TBC battleground XP', 'EraExperiencePolicy.h', 'return era >= Wrath;', 'return era >= TBC;'),
    ('Vanilla experience auras', 'EraExperiencePolicy.h', 'return era == TBC && !WrathOnlyXPBonus(spellId);',
     'return !WrathOnlyXPBonus(spellId);'),
    ('heirloom in TBC', 'EraExperiencePolicy.h', '        case 57353: // Heirloom Experience Bonus +10%\n', ''),
    ('truncated kill XP', 'EraExperiencePolicy.h', 'std::uint32_t(std::lround(double(amount) * kept / applied))',
     'std::uint32_t(double(amount) * kept / applied)'),
    ('penalty sign', 'EraExperiencePolicy.h', 'if (amount <= 0 || era > TBC)', 'if (amount < -100 || era > TBC)'),
    ('login rest', 'EraExperience.cpp', 'void OnPlayerLogin(Player* player) override\n    {\n        ClearRestAtEraCap(player);',
     'void OnPlayerLogin(Player* player) override\n    {\n        (void)player;'),
    ('level-change rest', 'EraExperience.cpp',
     'void OnPlayerLevelChanged(Player* player, uint8 /*oldLevel*/) override\n    {\n        ClearRestAtEraCap(player);',
     'void OnPlayerLevelChanged(Player* player, uint8 /*oldLevel*/) override\n    {\n        (void)player;'),
    ('era crossing rest', 'EraExperience.cpp', '            player->SetRestBonus(0);\n    }\n};', '            (void)0;\n    }\n};'),
    ('Vanilla cap 61', 'EraExperiencePolicy.h', '(era == Vanilla && level >= 60)', '(era == Vanilla && level >= 61)'),
    ('money at realm maximum', 'EraExperience.cpp', 'player->GetLevel() >= sWorld->getIntConfig(CONFIG_MAX_PLAYER_LEVEL) || ', ''),
    ('money at quest level', 'EraExperience.cpp', 'EraQuestXP(quest, era, player->GetLevel())',
     'EraQuestXP(quest, era, uint8(quest->GetQuestLevel()))'),
    ('Vanilla money factor', 'EraExperiencePolicy.h', 'std::uint64_t(xp) * 25 / 4', 'std::uint64_t(xp) * 6'),
    ('money flag', 'EraExperience.cpp', ' || quest->HasFlag(QUEST_FLAGS_NO_MONEY_FROM_XP)', ''),
    ('legacy money', 'fixture.cpp', 'if (sIndividualProgression->EraExperienceActive())\n                moneyRew =',
     'if (false)\n                moneyRew ='),
    ('Recruit-a-Friend level', 'EraExperience.cpp',
     'sWorld->setIntConfig(CONFIG_MAX_RECRUIT_A_FRIEND_BONUS_PLAYER_LEVEL, 0);', ''),
    ('Recruit-a-Friend inverted', 'EraExperience.cpp', 'if (!sIndividualProgression->EraExperienceActive())\n            return;\n\n        sWorld',
     'if (sIndividualProgression->EraExperienceActive())\n            return;\n\n        sWorld'),
    ('TBC table always loaded', 'fixture.cpp',
     'if (sIndividualProgression->questXpFix && sIndividualProgression->EraExperienceActive())', 'if (true)'),
    ('TBC table kept on reload', 'fixture.cpp', 'sIndividualProgression->questXpTbcMap.clear();', ''),
    ('era quest level ignored', 'EraExperience.cpp', 'questLevel != levels.end() ? questLevel->second :',
     'questLevel != levels.end() ? quest->GetQuestLevel() :'),
    ('TBC values with 1.12 levels', 'EraExperience.cpp',
     'tbcValue ? sIndividualProgression->questLevelTbcMap : sIndividualProgression->questLevelMap',
     'sIndividualProgression->questLevelMap'),
    ('1.12 values with TBC levels', 'EraExperience.cpp',
     'tbcValue ? sIndividualProgression->questLevelTbcMap : sIndividualProgression->questLevelMap',
     'sIndividualProgression->questLevelTbcMap'),
    ('TBC levels not loaded', 'fixture.cpp',
     'sIndividualProgression->questLevelTbcMap.insert({entry, (*result)[2].Get<int32>()});', ''),
    ('1.12 levels kept on reload', 'fixture.cpp', 'sIndividualProgression->questLevelMap.clear();', ''),
)

with tempfile.TemporaryDirectory(prefix='portable-era-experience-') as temporary:
    work = Path(temporary) / 'fixture'
    work.mkdir()
    (work / 'IndividualProgression.h').write_text(stub)
    (work / 'SpellAuraEffects.h').write_text('#pragma once\n')
    shutil.copyfile(module / 'src/EraExperience.cpp', work / 'EraExperience.cpp')
    shutil.copyfile(module / 'src/EraExperiencePolicy.h', work / 'EraExperiencePolicy.h')
    (work / 'fixture.cpp').write_text(tests)
    subprocess.run(build(work, work / 'fixture'), check=True)
    result = run_fixture([str(work / 'fixture')], 'TestEraExperience')
    print(result.stdout + result.stderr, end='')
    assert result.returncode == 0, 'era experience fixture failed'
    reject_mutants(work, MUTATIONS, build, 'Era experience')
