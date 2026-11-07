"""Exercise earned warlock demon chains through the shared class quest action, native quest packets and rituals.

The selector and action execute production code against native-shaped adapters.
Named native SQL fields and handler contracts anchor the data used by those adapters.
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
    sql_rows,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help='Playerbots src directory')
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
core = prepared_core(root)
module = args.source or core / 'modules/mod-playerbots/src'
warlock = module / 'Ai/Class/Warlock'
actions = module / 'Ai/World/Rpg/Action'
source = (actions / 'ClassQuestChains.cpp').read_text()
header = (actions / 'ClassQuestChains.h').read_text()
shared = (actions / 'ClassQuestAction.cpp').read_text()
shared_header = (actions / 'ClassQuestAction.h').read_text()
items = (module / 'Ai/Base/Actions/UseItemAction.cpp').read_text()

# Ritual metadata is native quest content; prerequisites carry the demon unlocked
# at their chain's end so a bot that knows that demon does not replay the chain.
# The shared class quest table holds them as warlock lessons; the owned rituals are focus steps.
chains = [(int(quest), int(spell), int(item or 0), int(creature or 0)) for quest, spell, item, creature in re.findall(
    r'\{CLASS_WARLOCK, (\d+), (\d+)(?:, Use::Focus, (\d+), (\d+))?\}',
    function(source, 'ClassQuestStep const ClassQuestSteps[]')) if int(spell)]
assert len(re.findall(r'\{CLASS_WARLOCK, \d+, [1-9]', source)) == len(chains)
assert len(chains) == len({row[0] for row in chains})
assert len(chains) == 53
assert {row[1] for row in chains} == {688, 697, 712, 691, 5784, 1122}
quests = {int(row['ID']): row for row in sql_rows(core, 'quest_template', {r[0] for r in chains})}
addon = {int(row['ID']): row for row in sql_rows(core, 'quest_template_addon', set(quests))}
item_rows = {int(row['entry']): row for row in sql_rows(core, 'item_template', {r[2] for r in chains if r[2]})}
# From the pinned client Spell.dbc, each reward spell teaches its demon; 1413 teaches Inferno.
reward_demons = {7763: 688, 11520: 697, 11519: 712, 1373: 691, 5785: 5784, 1413: 1122}
by_quest = {row[0]: row for row in chains}
summon_loot = {7603: 18625}  # Kroshius' Infernal Core
for quest, demon, item, creature in chains:
    row = quests[quest]
    assert int(addon[quest]['AllowableClasses']) == 256
    reward = int(row['RewardSpell'])
    if reward:
        assert reward_demons[reward] == demon
    next_quest = int(row['RewardNextQuest']) or int(addon[quest]['NextQuestID'])
    if next_quest in by_quest:
        assert next_quest in by_quest and by_quest[next_quest][1] == demon
    elif next_quest:
        assert reward, (quest, next_quest)
    previous = abs(int(addon[quest]['PrevQuestID']))
    if previous:
        assert previous in by_quest and by_quest[previous][1] == demon
    if item:
        assert int(row['StartItem']) == item and int(addon[quest]['ProvidedItemCount']) == 1
        assert int(item_rows[item]['spellid_1']) > 0 and int(item_rows[item]['spelltrigger_1']) == 0
        if quest in summon_loot:
            # The summon gives no kill credit; its corpse holds the objective and the used-up item is not required.
            assert all(row[f'RequiredNpcOrGo{index}'] == '0' for index in range(1, 5)), quest
            assert int(row['RequiredItemId1']) == summon_loot[quest] and int(row['RequiredItemCount1']) == 1
            assert int(item_rows[item]['spellcharges_1']) == -1, quest
            continue
        assert int(row['RequiredNpcOrGo1']) == creature and int(row['RequiredNpcOrGoCount1']) == 1
        assert int(row['RequiredItemId1']) == item and int(row['RequiredItemCount1']) == 1
    else:
        assert creature == 0

rituals = {(1471, 6284, 9221, 5676), (1504, 7464, 9222, 5676), (1689, 6928, 7728, 5676),
           (1474, 6286, 9223, 5677), (1513, 6626, 9224, 5677), (1739, 6913, 8674, 5677),
           (1795, 6999, 8712, 6268), (9619, 23732, 30208, 5676), (7603, 18626, 23054, 14467)}
assert {(quest, item, int(item_rows[item]['spellid_1']), creature)
        for quest, _, item, creature in chains if item} == rituals
focus_templates = sql_rows(core, 'gameobject_template', {37097, 92015, 92388, 105576, 181670, 179677})
assert {(int(row['Data0']), int(row['Data1'])) for row in focus_templates} == {
    (43, 10), (83, 10), (103, 10), (203, 10), (1375, 10), (1243, 15)}
# Spell.dbc: the Fel Fire's spell 23054 needs focus 1243, Kroshius' Remains in Felwood, and sends event 8328,
# which summons Kroshius there for three minutes. His native script turns him on the bot that woke him.
remains = next(row for row in focus_templates if int(row['entry']) == 179677)
assert remains['name'] == "Kroshius' Remains" and int(remains['Data0']) == 1243
remains_spawns = [line for line in (core / 'data/sql/base/db_world/gameobject.sql').read_text().splitlines()
                  if line.startswith('(') and line.split(',')[1] == '179677']
assert len(remains_spawns) == 1 and remains_spawns[0].split(',')[2] == '1', remains_spawns
wake = sql_rows(core, 'event_scripts', {8328})
assert len(wake) == 1 and int(wake[0]['command']) == 10 and int(wake[0]['datalong']) == 14467
assert int(wake[0]['datalong2']) == 180000
kroshius = sql_rows(core, 'creature_template', {14467})[0]
assert int(kroshius['rank']) == 0 and kroshius['AIName'] == 'SmartAI'
kroshius_script = sql_rows(core, 'smart_scripts', {14467, 1446700})
assert any(int(row['entryorguid']) == 14467 and int(row['event_type']) == 54 and int(row['action_type']) == 80 and
           int(row['action_param1']) == 1446700 for row in kroshius_script)
assert any(int(row['action_type']) == 2 and int(row['action_param1']) == 16 for row in kroshius_script)
assert any(int(row['action_type']) == 49 and int(row['target_type']) == 7 for row in kroshius_script)
assert {(row['Item'], row['Chance'], row['QuestRequired']) for row in sql_rows(core, 'creature_loot_template', {14467})
        if int(row['Item']) == 18625} == {('18625', '100', '1')}
# Each Flawless Fel Essence drops from ordinary Legashi, Jaedenar and Dark Portal demons on the continents.
essences = {int(sql_rows(core, 'quest_template', {7602})[0][f'RequiredItemId{index}']) for index in range(1, 4)}
assert essences == {18622, 18623, 18624}
essence_droppers = {6011: 18623, 6200: 18624, 6201: 18624, 6202: 18624, 9862: 18622}
assert {(int(row['Entry']), int(row['Item'])) for row in sql_rows(core, 'creature_loot_template', set(essence_droppers))
        if int(row['Item']) in essences and row['QuestRequired'] == '1'} == set(essence_droppers.items())
essence_creatures = sql_rows(core, 'creature_template', set(essence_droppers))
assert {int(row['entry']) for row in essence_creatures if row['rank'] == '0' and
        int(row['lootid']) == int(row['entry'])} == set(essence_droppers)
creature_rows = (core / 'data/sql/base/db_world/creature.sql').read_text()
for entry in essence_droppers:
    assert re.search(rf'^\(\d+,{entry},0,0,[01],', creature_rows, re.MULTILINE), entry
assert set(essence_droppers.values()) == essences
# A ritual whose objective drops from its summon leaves the corpse to the ordinary loot action.
storage = (core / 'src/server/game/Entities/Player/PlayerStorage.cpp').read_text()
native_loot = function(storage, 'bool Player::isAllowedToLoot(Creature const* creature)')
assert 'if (!creature->isDead() ||' in native_loot and 'if (loot->isLooted())' in native_loot
assert 'if (!loot->hasItemForAll() && !loot->hasItemFor(this))' in native_loot
assert 'return this == creature->GetLootRecipient();' in native_loot
corpses = (module / 'Ai/Base/Value/NearestCorpsesValue.cpp').read_text()
assert 'AnyDeadUnitInObjectRangeCheck u_check(bot, range);' in corpses
assert 'creators["nearest corpses"]' in (module / 'Ai/Base/ValueContext.h').read_text()
loot_strategy = (module / 'Ai/Base/Strategy/LootNonCombatStrategy.cpp').read_text()
assert 'new TriggerNode("loot available", { NextAction("loot", 6.0f) })' in loot_strategy
kill_count = function((core / 'src/server/game/Entities/Player/PlayerQuest.cpp').read_text(),
                      'uint16 Player::GetReqKillOrCastCurrentCount(')
assert 'if (qInfo->RequiredNpcOrGo[j] == entry)' in kill_count and 'return 0;' in kill_count
# The blood elf Voidstone's native event summons the quest's Voidwalker at its Rune of Summoning.
assert any(int(row['command']) == 10 and int(row['datalong']) == 5676
           for row in sql_rows(core, 'event_scripts', {10608}))
assert all(int(row['type']) == 8 for row in focus_templates)
ip_sql = core / 'modules/mod-individual-progression/data/sql/world/base'
merged_relations = {}
for table in ('creature_queststarter', 'creature_questender', 'gameobject_queststarter', 'gameobject_questender'):
    raw = (core / f'data/sql/base/db_world/{table}.sql').read_text()
    assert re.findall(r'^  `([^`]+)`', raw, re.MULTILINE) == ['id', 'quest']
    merged_relations[table] = {tuple(map(int, row)) for row in re.findall(r'^\((\d+),(\d+)\)[,;]$', raw, re.MULTILINE)}
restored_imps = {'zone_tirisfal_glades': (5667, 1470), 'zone_durotar': (5765, 1485),
                'zone_elwynn_forest': (459, 1598), 'zone_dun_morogh': (460, 1599),
                'zone_eversong_woods': (15283, 8344)}
for zone, (giver, quest) in restored_imps.items():
    restoration = (ip_sql / (zone + '.sql')).read_text()
    for table in ('creature_queststarter', 'creature_questender'):
        inserts = re.findall(rf'INSERT INTO `{table}`\s*\(`id`,\s*`quest`\)\s*VALUES\s*([^;]+);', restoration)
        assert any((giver, quest) in {tuple(map(int, row)) for row in re.findall(r'\((\d+),\s*(\d+)\)', insert)}
                   for insert in inserts), (zone, table, quest)
        merged_relations[table].add((giver, quest))
    assert by_quest[quest][1] == 688
# Individual Progression restores the Felsteed quests and their givers.
mounts = (ip_sql / 'mounts_and_riding.sql').read_text()
felsteed = {3631, 4487, 4488, 4489, 4490}
assert 'DELETE FROM `disables` WHERE `sourceType` = 1 AND `entry` IN (3631, 4487, 4488, 4489, 4490);' in mounts
assert felsteed <= set(by_quest)
for table in ('creature_queststarter', 'creature_questender'):
    for statement in re.findall(rf'INSERT INTO `{table}` \(`id`, `quest`\) VALUES ([^;]+);', mounts):
        merged_relations[table] |= {row for row in (tuple(map(int, pair)) for pair in re.findall(
            r'\((\d+), (\d+)\)', statement)) if row[1] in felsteed}
assert (181698, 9529) in merged_relations['gameobject_questender']
assert (181698, 9619) in merged_relations['gameobject_queststarter']
for kind in ('queststarter', 'questender'):
    relations = merged_relations['creature_' + kind] | merged_relations['gameobject_' + kind]
    assert set(quests) <= {quest for _, quest in relations}, kind
assert (34, 140) in merged_relations['gameobject_queststarter']
assert (33, 140) in merged_relations['gameobject_questender']
go_quest = sql_rows(core, 'quest_template', {140})[0]
repeatable_quest = sql_rows(core, 'quest_template', {1462})[0]
repeatable_addon = sql_rows(core, 'quest_template_addon', {1462})[0]
assert int(repeatable_addon['SpecialFlags']) & 1
go_templates = sql_rows(core, 'gameobject_template', {33, 34})
assert all(int(row['type']) == 2 and row['IconName'] != 'Point' for row in go_templates)
trainer_sql = re.sub(r'--[^\n]*', '', (ip_sql / 'class_trainers.sql').read_text())
for trainer in (31, 32):
    removals = re.findall(rf'DELETE FROM `trainer_spell` WHERE `TrainerId` = {trainer} AND `SpellId` IN \(([^)]+)\)', trainer_sql)
    assert any(688 in map(int, group.split(',')) for group in removals)
    assert not re.search(rf'\({trainer},\s*688,', trainer_sql)
native_summons = sql_rows(core, 'smart_scripts', {567600, 567700, 626800})
for entry in (567600, 567700, 626800):
    script = [row for row in native_summons if int(row['entryorguid']) == entry]
    assert any(int(row['event_param1']) == 3000 and int(row['event_param2']) == 3000 for row in script)
    assert any(int(row['action_type']) == 2 and int(row['action_param1']) == 14 for row in script)
    assert any(int(row['action_type']) == 49 and int(row['target_type']) == 7 for row in script)

# Strahad's escort signals the acolyte that creates the live Felhunter focus.
escort = {(int(row['entryorguid']), int(row['source_type']), int(row['id'])): row
          for row in sql_rows(core, 'smart_scripts', {6251, 625100, 6252, 625200})}
for key, fields in {
    (6251, 0, 0): {'event_type': 19, 'event_param1': 1795, 'link': 1},
    (6251, 0, 1): {'event_type': 61, 'action_type': 81, 'action_param1': 0, 'link': 2},
    (6251, 0, 2): {'action_type': 53, 'action_param2': 6251, 'target_type': 1},
    (6251, 0, 3): {'event_type': 40, 'event_param1': 3, 'event_param2': 6251,
                   'action_type': 80, 'action_param1': 625100},
    (625100, 9, 4): {'action_type': 45, 'action_param1': 1, 'action_param2': 1,
                     'target_type': 9, 'target_param4': 1},
    (6252, 0, 0): {'event_type': 38, 'event_param1': 1, 'event_param2': 1,
                   'action_type': 80, 'action_param1': 625200},
    (625200, 9, 2): {'action_type': 50, 'action_param1': 92388, 'target_type': 8},
}.items():
    assert all(int(escort[key][field]) == expected for field, expected in fields.items()), key

# The base contexts register the shared chain, which the warlock strategy runs with the other lesson actions.
assert 'demon quest' not in (warlock / 'WarlockAiObjectContext.cpp').read_text()
assert 'CalculatedValue<uint32>(botAI, "class quest chain", 5)' in header
assert 'Trigger(botAI, "class quest chain")' in header
trigger_header = (module / 'Bot/Engine/Trigger/Trigger.h').read_text()
trigger_source = (module / 'Bot/Engine/Trigger/Trigger.cpp').read_text()
assert 'int32_t checkInterval = 1' in trigger_header
assert 'checkInterval == 1 ? 1' in trigger_source
assert re.search(r'if \(checkInterval < 2\)\s+return true;', trigger_source)
strategy = (warlock / 'Strategy/GenericWarlockNonCombatStrategy.cpp').read_text()
assert 'new TriggerNode("class quest chain", {NextAction("class quest chain", ACTION_NORMAL + 2)})' in strategy
assert 'demon quest' not in strategy

quest_handler = (core / 'src/server/game/Handlers/QuestHandler.cpp').read_text()
native_accept = function(quest_handler, 'void WorldSession::HandleQuestgiverAcceptQuestOpcode(')
native_reward = function(quest_handler, 'void WorldSession::HandleQuestgiverChooseRewardOpcode(')
assert 'CanTakeQuest' in native_accept
assert 'CanRewardQuest' in native_reward
for handler, relation in ((native_accept, 'hasQuest'), (native_reward, 'hasInvolvedQuest')):
    assert 'TYPEMASK_GAMEOBJECT' in handler and relation in handler
player_quest = (core / 'src/server/game/Entities/Player/PlayerQuest.cpp').read_text()
assert 'RemoveActiveQuest(quest_id, false);' in function(player_quest, 'void Player::RewardQuest(')
assert 'if (!qInfo->IsRepeatable())' in function(player_quest, 'bool Player::GetQuestRewardStatus(')
assert '!qInfo->IsRepeatable() && IsQuestRewarded(quest_id)' in function(player_quest, 'QuestStatus Player::GetQuestStatus(')
native_take = function(player_quest, 'bool Player::CanTakeQuest(')
for check in ('SatisfyQuestRace', 'SatisfyQuestClass', 'SatisfyQuestLevel',
              'SatisfyQuestPreviousQuest', 'SatisfyQuestConditions'):
    assert check in native_take
assert 'IsObjectMeetToConditions(this, conditions)' in function(player_quest, 'bool Player::SatisfyQuestConditions(')
item_handler = function((core / 'src/server/game/Handlers/SpellHandler.cpp').read_text(),
                        'void WorldSession::HandleUseItemOpcode(')
for check in ('pUser->CanUseItem(pItem)', 'pItem->GetGUID() != itemGUID', 'pUser->CastItemUseSpell(pItem, targets,'):
    assert check in item_handler
cast_source = function(items, 'bool UseItemAction::UseItem(Item* item, ObjectGuid goGuid, Item* itemTarget, Unit* unitTarget)')
assert 'packet << targetFlag << unitTarget->GetGUID().WriteAsPacked();' in cast_source
assert 'bot->GetSession()->HandleUseItemOpcode(packet);' in cast_source
precheck = function(cast_source, '    for (uint8 i = 0; i < spellSlotLimit; ++i)')
focus_check = function((core / 'src/server/game/Grids/Notifiers/GridNotifiers.h').read_text(),
                       'class GameObjectFocusCheck') + ';'
native_focus = function((core / 'src/server/game/Spells/Spell.cpp').read_text(), 'SpellCastResult Spell::CheckSpellFocus(')
assert 'GameObjectFocusCheck go_check(m_caster, m_spellInfo->RequiresSpellFocus)' in native_focus
assert 'SPELL_FAILED_REQUIRES_SPELL_FOCUS' in native_focus
rpg = (module / 'Ai/World/Rpg/Action/NewRpgBaseAction.cpp').read_text()
native_interact = function((module / 'Ai/World/Rpg/NewRpgHelpers.cpp').read_text(),
                           'bool CanInteractWithQuestGiver(Player* bot, Object* questGiver)')
assert 'go->GetGoType() == GAMEOBJECT_TYPE_QUESTGIVER' in native_interact
assert 'go->GetGOInfo()->IconName == "Point"' in native_interact
assert 'go->IsWithinDistInMap(bot)' in function(rpg, 'bool NewRpgBaseAction::IsWithinInteractionDist(')
go_source = (core / 'src/server/game/Entities/GameObject/GameObject.cpp').read_text()
assert 'GetGOQuestRelationBounds(GetEntry())' in function(go_source, 'bool GameObject::hasQuest(')
assert 'GetGOQuestInvolvedRelationBounds(GetEntry())' in function(go_source, 'bool GameObject::hasInvolvedQuest(')
assert 'case GAMEOBJECT_TYPE_QUESTGIVER:' in function(go_source, 'float GameObject::GetInteractionDistance(')
assert 'return 5.5555553f;' in function(go_source, 'float GameObject::GetInteractionDistance(')
assert 'return GetExactDist(&pos) <= radius;' in function(go_source, 'bool GameObject::IsAtInteractDistance(Position const&')
assert 'IsInMap(player) && InSamePhase(player) && IsAtInteractDistance(player)' in function(
    go_source, 'bool GameObject::IsWithinDistInMap(Player const*')
value_context = (module / 'Ai/Base/ValueContext.h').read_text()
assert 'creators["nearest game objects no los"] = &ValueContext::nearest_game_objects_no_los;' in value_context
assert 'new NearestGameObjects(botAI, sPlayerbotAIConfig.SightDistance, true)' in value_context
nearest_objects = function((module / 'Ai/Base/Value/NearestGameObjects.cpp').read_text(),
                           'GuidVector NearestGameObjects::Calculate()')
assert 'result.push_back(go->GetGUID());' in nearest_objects
assert not re.search(r'^\s*if \([^\n]*IsWithinLOSInMap', nearest_objects, re.MULTILINE)
far_move = function(rpg, 'bool NewRpgBaseAction::MoveFarTo(')
assert re.search(r'if \(sPlayerbotAIConfig.naturalProgression\)\s+return false;', far_move)
assert 'path.GetActualEndPosition()' in far_move
assert 'endDistToDest + 5.0f < disToDest' in far_move
native_route = function(rpg, 'bool NewRpgBaseAction::MoveToMap(')
assert 'sContinentRoutes.UsableLinks(bot, route)' in native_route
assert 'RideTransport(route, transport)' in native_route
assert 'ContinentRoutes::RouteTo(links, search, sContinentRoutes.Locate(dest))' in native_route
object_source = (core / 'src/server/game/Entities/Object/Object.cpp').read_text()
assert 'GetExactDist(&pos) - GetObjectSize()' in function(object_source, 'float WorldObject::GetDistance(Position const& pos)')
native_dist = function(object_source, 'bool WorldObject::_IsWithinDist(')
assert 'maxdist += GetObjectSize()' in native_dist and 'maxdist += obj->GetObjectSize()' in native_dist
for forbidden in ('bot->AddQuest(', 'bot->RewardQuest(', 'CompleteQuest(', 'AreaExploredOrEventHappens(',
                  'learnSpell(', 'SummonCreature(', 'AddItem(', 'RemovePet(', 'TeleportTo('):
    assert forbidden not in source + shared, forbidden

quest_values = (module / 'Ai/Base/Value/QuestValues.cpp').read_text()
relation_map = function(quest_values, 'entryQuestRelationMap EntryQuestRelationMapValue::Calculate()')
assert 'rMap[quest->RequiredNpcOrGo[objective]][questId] |= relationFlag;' in relation_map
assert '"item drop list", quest->RequiredItemId[objective]' in relation_map
assert 'rMap[entry][questId] |= relationFlag;' in relation_map
assert 'data[questId][flag][entry].push_back(GuidPosition(creData));' in quest_values
assert 'data[questId][flag][entry].push_back(GuidPosition(goData));' in quest_values
assert 'int32 entry = goData.id * -1;' in function(quest_values, 'void FindQuestObjectData::operator()(GameObjectData const&')
travel = (module / 'Mgr/Travel/TravelMgr.cpp').read_text()
assert 'gameobjectData.mapid == point.GetMapId()' in function(travel, 'void FindPointGameObjectData::operator()(')

production = {
    'table': function(source, 'namespace\n'),
    'gate': function(shared, 'bool CanRunClassQuest('),
    'locations': function(shared, 'questRelationGuidps const* ClassQuestLocations('),
    'routeconstructor': function(shared, 'ClassQuestRouteCosts::ClassQuestRouteCosts('),
    'routecost': function(shared, 'float ClassQuestRouteCosts::Cost('),
    'nearest': function(shared, 'WorldPosition NearestClassQuestLocation('),
    'needed': function(shared, 'bool ClassQuestObjectiveNeeded('),
    'current': function(source, 'ClassQuestStep const* CurrentClassQuestStep('),
    'value': function(source, 'uint32 ClassQuestChainValue::Calculate()'),
    'trigger': function(source, 'bool ClassQuestChainTrigger::IsActive()'),
    'useful': function(source, 'bool ClassQuestChainAction::isUseful()'),
    'execute': function(source, 'bool ClassQuestChainAction::Execute('),
    'giver': function(shared, 'bool ClassQuestAction::InteractWithQuestGiver('),
    'move': function(shared, 'bool ClassQuestAction::MoveToQuestLocation('),
    'travel': function(shared, 'bool ClassQuestAction::MoveToQuestPosition('),
    'objectives': function(shared, 'bool ClassQuestAction::DoObjectives('),
    'ritual': function(source, 'bool ClassQuestChainAction::UseAtFocus('),
    'focusposition': function(source, 'WorldPosition ClassQuestChainAction::FocusPosition('),
    'wait': function(source, 'bool ClassQuestChainAction::Wait('),
    'restart': function(source, 'bool ClassQuestChainAction::Restart('),
    'abandon': function(source, 'bool ClassQuestChainAction::Abandon('),
    'wrapper': function(items, 'bool UseItemAction::UseItemOnUnit('),
    'precheck': precheck,
    'focuscheck': focus_check,
    'schedule': function(trigger_source, 'bool Trigger::needCheck('),
    'triggerconstructor': function(trigger_source, 'Trigger::Trigger('),
    'classes': '\n'.join(function(shared_header, name) + ';' for name in (
        'class ClassQuestRouteCosts', 'class ClassQuestAction')) + '\n' +
        '\n'.join(function(header, name) + ';' for name in (
        'enum class ClassQuestUse', 'struct ClassQuestStep', 'class ClassQuestChainValue',
        'class ClassQuestChainTrigger', 'class ClassQuestChainAction')),
    'accept': function(rpg, 'bool NewRpgBaseAction::AcceptQuest('),
    'turnin': function(rpg, 'bool NewRpgBaseAction::TurnInQuest('),
    'relationmap': relation_map,
    'gospawnrelations': function(quest_values, 'void FindQuestObjectData::operator()(GameObjectData const&'),
    'gonativerelations': '\n'.join(function(go_source, name) for name in (
        'bool GameObject::hasQuest(', 'bool GameObject::hasInvolvedQuest(')),
}
production['relationflags'] = function((module / 'Ai/Base/Value/QuestValues.h').read_text(),
                                        'enum class QuestRelationFlag') + ';'
production['policyinclude'] = '#include "' + str(module / 'Mgr/Travel/ContinentRoutePolicy.h') + '"'
special_flags = {int(row['ID']): row['SpecialFlags']
                 for row in sql_rows(core, 'quest_template_addon', set(quests) | {140, 1462})}
native_quests = []
for quest, row in {**quests, 140: go_quest, 1462: repeatable_quest}.items():
    fields = [str(quest), str(reward_demons.get(int(row['RewardSpell']), 0)), row['StartItem']]
    for field, count in (('RequiredNpcOrGo', 4), ('RequiredNpcOrGoCount', 4),
                         ('RequiredItemId', 6), ('RequiredItemCount', 6)):
        fields.append('{' + ','.join(row[field + str(index + 1)] for index in range(count)) + '}')
    fields.append('true' if quest == 1462 else 'false')
    fields += [row['RewardDisplaySpell'], row['RewardSpell'], special_flags.get(quest, '0')]
    native_quests.append('Quest{' + ','.join(fields) + '}')
production['nativequests'] = ('for(Quest const& native : {' + ',\n'.join(native_quests)
                             + '}) objectMgr.quests.emplace(native.id,native);')
production['itemspells'] = '\n'.join(f'itemSpells[{item}] = {row["spellid_1"]};' for item, row in item_rows.items())
production['relations'] = '\n'.join(
    'std::map<uint32,uint32> ' + name + '={' + ','.join(
        '{' + str(quest) + ',' + str(min(entry for entry, relation in merged_relations[table]
                                      if relation == quest)) + '}' for quest in quests
        if any(relation == quest for _, relation in merged_relations[table])) + '};'
    for name, table in (('nativeStarters', 'creature_queststarter'), ('nativeEnders', 'creature_questender')))

prelude = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <type_traits>
#include <unordered_map>
#include <variant>
#include <vector>
@@POLICYINCLUDE@@
using uint8=uint8_t; using uint16=uint16_t; using uint32=uint32_t; using int32=int32_t;
constexpr uint8 CLASS_WARRIOR=1, CLASS_PALADIN=2, CLASS_HUNTER=3, CLASS_ROGUE=4, CLASS_PRIEST=5, CLASS_SHAMAN=7,
    CLASS_MAGE=8, CLASS_WARLOCK=9, CLASS_DRUID=11;
constexpr int UNIT_STATE_LOST_CONTROL=1, CURRENT_CHANNELED_SPELL=1, CURRENT_GENERIC_SPELL=2, CMSG_QUESTLOG_REMOVE_QUEST=3;
constexpr uint32 QUEST_OBJECTIVES_COUNT=4, QUEST_ITEM_OBJECTIVES_COUNT=6, IN_MILLISECONDS=1000, MINUTE=60,
    MAX_QUEST_LOG_SIZE=25, QUEST_SPECIAL_FLAGS_EXPLORATION_OR_EVENT=2;
constexpr int CMSG_QUESTGIVER_CHOOSE_REWARD=1, CMSG_QUESTGIVER_ACCEPT_QUEST=2, GAMEOBJECT_TYPE_SPELL_FOCUS=8;
constexpr int GAMEOBJECT_TYPE_QUESTGIVER=2;
constexpr uint32 UNIT_NPC_FLAG_QUESTGIVER=2;
constexpr float INTERACTION_DISTANCE=5.0f;
enum QuestStatus { QUEST_STATUS_NONE=0, QUEST_STATUS_INCOMPLETE=1, QUEST_STATUS_COMPLETE=2, QUEST_STATUS_REWARDED=3,
                   QUEST_STATUS_FAILED=4 };
uint32 now=100000;
uint32 getMSTime() { return now; }
uint32 GetMSTimeDiffToNow(uint32 before) { return now-before; }
struct ObjectGuid {
    using LowType=uint32;
    uint32 value=0;
    explicit operator bool() const { return value!=0; }
    bool operator==(ObjectGuid const&) const=default;
    static ObjectGuid Empty;
};
ObjectGuid ObjectGuid::Empty;
using GuidVector=std::vector<ObjectGuid>;
using QuestRelations=std::multimap<uint32,uint32>;
using QuestRelationBounds=std::pair<QuestRelations::const_iterator,QuestRelations::const_iterator>;
struct Event {};
struct Player; struct Creature; struct TempSummon; struct WorldPosition; struct GameObject;
struct Spell { uint32 kind=0; };
struct WorldPacket {
    int opcode; std::vector<uint32> values;
    explicit WorldPacket(int opcode):opcode(opcode){}
    WorldPacket& operator<<(uint32 n) { values.push_back(n); return *this; }
    WorldPacket& operator<<(ObjectGuid guid) { values.push_back(guid.value); return *this; }
    void rpos(uint32) {}
};
namespace WorldPackets::Quest {
struct QuestLogRemoveQuest {
    WorldPacket packet; uint8 Slot=255;
    explicit QuestLogRemoveQuest(WorldPacket&& p):packet(std::move(p)){}
    void Read() { assert(packet.opcode==CMSG_QUESTLOG_REMOVE_QUEST&&packet.values.size()==1); Slot=uint8(packet.values[0]); }
};
}
struct Session {
    Player* player=nullptr; bool headless=true,accept=true,reward=true; int accepts=0,rewards=0,removals=0;
    bool IsHeadless() const { return headless; }
    void HandleQuestgiverAcceptQuestOpcode(WorldPacket&);
    void HandleQuestgiverChooseRewardOpcode(WorldPacket&);
    void HandleQuestLogRemoveQuest(WorldPackets::Quest::QuestLogRemoveQuest&);
};
struct Map {
    bool dungeon=false; std::map<uint32,GameObject*> const* objects=nullptr;
    bool IsDungeon() const { return dungeon; }
    GameObject* GetGameObject(ObjectGuid g) const { return objects&&objects->contains(g.value)?objects->at(g.value):nullptr; }
};
struct ItemTemplate { uint32 StartQuest=0; struct Slot { int32 SpellId=0; } Spells[5]; };
struct Item {
    uint32 entry=0,count=1; ItemTemplate proto;
    ItemTemplate const* GetTemplate() const { return &proto; }
    ObjectGuid GetGUID() const { return {entry}; }
};
struct Quest {
    uint32 id=0,rewardDemon=0,source=0;
    std::array<int32,QUEST_OBJECTIVES_COUNT> RequiredNpcOrGo{};
    std::array<uint32,QUEST_OBJECTIVES_COUNT> RequiredNpcOrGoCount{};
    std::array<uint32,QUEST_ITEM_OBJECTIVES_COUNT> RequiredItemId{},RequiredItemCount{};
    bool repeatable=false;
    uint32 display=0,cast=0,special=0;
    uint32 GetQuestId() const { return id; }
    uint32 GetRewSpell() const { return display; }
    int32 GetRewSpellCast() const { return int32(cast); }
    uint32 GetSrcItemId() const { return source; }
    bool HasSpecialFlag(uint32 flag) const { return (special&flag)!=0; }
    uint32 GetRewChoiceItemsCount() const { return 0; }
    bool IsRepeatable() const { return repeatable; }
};
struct QuestStatusData {
    QuestStatus Status=QUEST_STATUS_NONE;
    std::array<uint32,QUEST_OBJECTIVES_COUNT> CreatureOrGOCount{};
};
struct WorldObject {
    uint32 guid=1,entry=0,mapId=0; float x=2.0f,z=0,size=0.5f;
    bool inWorld=true,sameMap=true,samePhase=true,visible=true,los=true,alive=true;
    virtual ~WorldObject()=default;
    ObjectGuid GetGUID() const { return {guid}; }
    uint32 GetEntry() const { return entry; }
    bool IsInWorld() const { return inWorld; }
    bool IsAlive() const { return alive; }
    float GetPositionZ() const { return z; }
    bool IsWithinDistInMap(WorldObject const* other,float range) const {
        float const dx=x-other->x,dz=z-other->z,maximum=range+size+other->size;
        return sameMap&&samePhase&&dx*dx+dz*dz<maximum*maximum;
    }
};
struct Unit:WorldObject { virtual Creature* ToCreature() { return nullptr; } };
struct Creature:Unit {
    bool removing=false,canInteract=true,questgiver=true,loot=false; std::set<uint32> starts,finishes;
    Creature* ToCreature() override { return this; }
    virtual TempSummon* ToTempSummon() { return nullptr; }
    bool IsDuringRemoveFromWorld() const { return removing; }
    bool hasQuest(uint32 q) const { return starts.contains(q); }
    bool hasInvolvedQuest(uint32 q) const { return finishes.contains(q); }
    bool HasNpcFlag(uint32) const { return questgiver; }
};
struct TempSummon:Creature {
    ObjectGuid summoner;
    TempSummon* ToTempSummon() override { return this; }
    ObjectGuid GetSummonerGUID() const { return summoner; }
};
struct GameObjectTemplate {
    uint32 type=GAMEOBJECT_TYPE_SPELL_FOCUS; std::string IconName;
    struct { uint32 focusId=43; float dist=10; } spellFocus;
};
struct GameObject:WorldObject {
    bool spawned=true; GameObjectTemplate info;
    bool isSpawned() const { return spawned; }
    uint32 GetGoType() const { return info.type; }
    GameObjectTemplate const* GetGOInfo() const { return &info; }
    bool hasQuest(uint32) const;
    bool hasInvolvedQuest(uint32) const;
    using WorldObject::IsWithinDistInMap;
    bool IsWithinDistInMap(Player const*) const;
};
@@FOCUSCHECK@@
struct Player:Unit {
    uint32 cls=CLASS_WARLOCK,phase=1; bool random=true,hasSession=true,group=false,teleport=false,
      battleground=false,arena=false,combat=false,mounted=false,flight=false,flying=false,
      transport=false,vehicle=false,lostControl=false,casting=false,pet=true,canAdd=true,canReward=true,ownAccess=true,
      objectiveLos=true;
    Map map; Session session; Spell channel{CURRENT_CHANNELED_SPELL},generic{CURRENT_GENERIC_SPELL};
    bool useChannel=false; int stops=0;
    std::set<uint32> known,available; std::map<uint32,QuestStatusData> quests; std::map<uint32,Item> inventory;
    std::set<uint32> bank;
    Player() { session.player=this; guid=100; x=0; size=1.5f; }
    uint32 getClass() const { return cls; } Session* GetSession() { return hasSession?&session:nullptr; }
    bool GetGroup() const { return group; } bool IsBeingTeleported() const { return teleport; }
    Map* GetMap() { return &map; } bool InBattleground() const { return battleground; } bool InArena() const { return arena; }
    bool IsInCombat() const { return combat; } bool IsMounted() const { return mounted; }
    bool IsInFlight() const { return flight; } bool IsFlying() const { return flying; }
    bool GetTransport() const { return transport; } bool GetVehicle() const { return vehicle; }
    bool HasUnitState(int) const { return lostControl; } bool IsNonMeleeSpellCast(bool) const { return casting; }
    bool HasSpell(uint32 n) const { return known.contains(n); } bool GetPet() const { return pet; }
    QuestStatus GetQuestStatus(uint32 q) const { return quests.contains(q)?quests.at(q).Status:QUEST_STATUS_NONE; }
    bool GetQuestRewardStatus(uint32 q) const { return GetQuestStatus(q)==QUEST_STATUS_REWARDED; }
    auto const& getQuestStatusMap() const { return quests; }
    Item* GetItemByEntry(uint32 i) { return inventory.contains(i)?&inventory.at(i):nullptr; }
    uint32 GetItemCount(uint32 i) const { return inventory.contains(i)?inventory.at(i).count:0; }
    bool HasItemCount(uint32 i,uint32 count,bool inBank) const {
        assert(count==1&&inBank); return inventory.contains(i)||bank.contains(i);
    }
    uint32 GetQuestSlotQuestId(uint16 slot) const {
        uint16 index=0;
        for(auto const& [id,data]:quests) if(data.Status!=QUEST_STATUS_REWARDED&&data.Status!=QUEST_STATUS_NONE&&index++==slot) return id;
        return 0;
    }
    bool CanTakeQuest(Quest const* q,bool) const { return ownAccess&&available.contains(q->id)&&GetQuestStatus(q->id)==QUEST_STATUS_NONE; }
    bool CanAddQuest(Quest const*,bool) const { return canAdd; }
    bool CanRewardQuest(Quest const* q,bool) const { return canReward&&GetQuestStatus(q->id)==QUEST_STATUS_COMPLETE; }
    uint32 GetReqKillOrCastCurrentCount(uint32 q,int32 entry) const;
    // Native: a dead creature whose remaining loot includes an item for this solo recipient.
    bool isAllowedToLoot(Creature const* c) const { return !c->alive&&c->loot; }
    bool IsInMap(WorldObject const* o) const { return o->sameMap; }
    bool InSamePhase(WorldObject const* o) const { return o->samePhase; }
    bool CanSeeOrDetect(WorldObject const* o) const { return o->visible; }
    bool IsWithinLOSInMap(WorldObject const* o) const { return o->los; }
    bool IsWithinLOS(float,float,float) const { return objectiveLos; }
    float GetDistance(WorldObject const* o) const { return std::max(0.0f,std::abs(o->x-x)-size-o->size); }
    float GetDistance(WorldPosition const&) const;
    float GetExactDist(WorldPosition const&) const;
    void StopMoving() { ++stops; }
    Spell* GetCurrentSpell(int kind) { return kind==CURRENT_GENERIC_SPELL?&generic:useChannel?&channel:nullptr; }
    void PlayDistanceSound(uint32) {}
    uint32 GetMapId() const { return mapId; } uint32 GetPhaseMask() const { return phase; }
};
struct ObjectMgr {
    using QuestMap=std::map<uint32,Quest*>;
    std::map<uint32,Quest> quests; std::map<uint32,GameObjectTemplate> objects;
    QuestMap questTemplates; QuestRelations creatureStarters,creatureEnders,goStarters,goEnders;
    Quest const* GetQuestTemplate(uint32 q) const { return quests.contains(q)?&quests.at(q):nullptr; }
    auto const* GetGameObjectTemplates() const { return &objects; }
    QuestMap const& GetQuestTemplates() {
        questTemplates.clear(); for(auto& [id,q]:quests) questTemplates[id]=&q; return questTemplates;
    }
    auto const* GetCreatureQuestRelationMap() const { return &creatureStarters; }
    auto const* GetCreatureQuestInvolvedRelationMap() const { return &creatureEnders; }
    auto const* GetGOQuestRelationMap() const { return &goStarters; }
    auto const* GetGOQuestInvolvedRelationMap() const { return &goEnders; }
    QuestRelationBounds GetGOQuestRelationBounds(uint32 entry) const { return goStarters.equal_range(entry); }
    QuestRelationBounds GetGOQuestInvolvedRelationBounds(uint32 entry) const { return goEnders.equal_range(entry); }
} objectMgr;
auto* sObjectMgr=&objectMgr;
// Native: the count of the objective naming the entry, else 0.
uint32 Player::GetReqKillOrCastCurrentCount(uint32 q,int32 entry) const {
    if(!quests.contains(q)) return 0;
    for(uint32 i=0;i<QUEST_OBJECTIVES_COUNT;++i)
        if(objectMgr.quests.at(q).RequiredNpcOrGo[i]==entry) return quests.at(q).CreatureOrGOCount[i];
    return 0;
}
@@GONATIVERELATIONS@@
bool GameObject::IsWithinDistInMap(Player const* p) const {
    // Synthetic no-display metadata exercises the native exact-distance fallback.
    float const dx=x-p->x,dz=z-p->z;
    return sameMap&&samePhase&&dx*dx+dz*dz<=5.5555553f*5.5555553f;
}
std::map<uint32,uint32> itemSpells;
void Session::HandleQuestgiverAcceptQuestOpcode(WorldPacket& p) {
    assert(p.opcode==CMSG_QUESTGIVER_ACCEPT_QUEST&&p.values.size()==3); ++accepts;
    uint32 q=p.values[1]; auto const* quest=objectMgr.GetQuestTemplate(q);
    if (!accept||!quest||!player->CanTakeQuest(quest,false)||!player->CanAddQuest(quest,false)) return;
    player->quests[q].Status=QUEST_STATUS_INCOMPLETE;
    if(quest->source) { auto& item=player->inventory[quest->source]; item.entry=quest->source; item.proto.Spells[0].SpellId=itemSpells[quest->source]; }
}
void Session::HandleQuestLogRemoveQuest(WorldPackets::Quest::QuestLogRemoveQuest& request) {
    ++removals; uint32 const id=player->GetQuestSlotQuestId(request.Slot); assert(id);
    // Native removal takes the quest's own source item and clears the log entry.
    if(uint32 src=objectMgr.quests.at(id).source) player->inventory.erase(src);
    player->quests.erase(id);
}
void Session::HandleQuestgiverChooseRewardOpcode(WorldPacket& p) {
    assert(p.opcode==CMSG_QUESTGIVER_CHOOSE_REWARD&&p.values.size()==3); ++rewards;
    uint32 q=p.values[1]; auto const* quest=objectMgr.GetQuestTemplate(q);
    if (!reward||!quest||!player->CanRewardQuest(quest,false)) return;
    if(quest->IsRepeatable()) player->quests.erase(q);
    else player->quests[q].Status=QUEST_STATUS_REWARDED;
    if(quest->rewardDemon) player->known.insert(quest->rewardDemon);
}
struct Config { bool naturalProgression=true,continentTravel=false; float SightDistance=100; std::set<uint32> IgnoredQuests; } sPlayerbotAIConfig;
struct RandomMgr { bool IsRandomBot(Player* p) const { return p->random; } } sRandomPlayerbotMgr;
struct SpellInfo { uint32 RequiresSpellFocus=43; };
struct SpellMgr {
    std::map<uint32,SpellInfo> spells;
    SpellInfo const* GetSpellInfo(uint32 id) const { return spells.contains(id)?&spells.at(id):nullptr; }
} spellMgr;
auto* sSpellMgr=&spellMgr;
struct GameObjectData { uint32 id=0,mapid=0,phaseMask=1; float posX=200,posY=0,posZ=0; };
std::vector<GameObjectData> spawns; int spawnScans=0;
struct WorldPosition {
    uint32 map=0; float x=0,y=0,z=0;
    WorldPosition()=default;
    explicit WorldPosition(WorldObject* o):map(o->mapId),x(o->x),z(o->z){}
    WorldPosition(uint32 m,float a,float b=0,float c=0):map(m),x(a),y(b),z(c){}
    explicit WorldPosition(GameObjectData const& go):map(go.mapid),x(go.posX),y(go.posY),z(go.posZ){}
    bool operator==(WorldPosition const&) const=default;
    uint32 GetMapId() const { return map; }
    float GetPositionX() const { return x; } float GetPositionY() const { return y; } float GetPositionZ() const { return z; }
    std::vector<GameObjectData const*> getGameObjectsNear(float,uint32 entry) {
        ++spawnScans; std::vector<GameObjectData const*> rows; bool const anyMap=*this==WorldPosition();
        for(auto const& s:spawns) if((anyMap||s.mapid==map)&&s.id==entry) rows.push_back(&s);
        return rows;
    }
};
float Player::GetExactDist(WorldPosition const& p) const { return std::sqrt((p.x-x)*(p.x-x)+p.y*p.y+(p.z-z)*(p.z-z)); }
float Player::GetDistance(WorldPosition const& p) const { return std::max(0.0f,GetExactDist(p)-size); }
@@RELATIONFLAGS@@
constexpr uint32 GIVER=uint32(QuestRelationFlag::questGiver),TAKER=uint32(QuestRelationFlag::questTaker);
using entryQuestRelationMap=std::unordered_map<int32,std::unordered_map<uint32,uint32>>;
using questEntryGuidps=std::unordered_map<int32,std::vector<WorldPosition>>;
using questRelationGuidps=std::unordered_map<uint32,questEntryGuidps>;
using questGuidpMap=std::unordered_map<uint32,questRelationGuidps>;
using GuidPosition=WorldPosition;
struct EntryQuestRelationMapValue { entryQuestRelationMap Calculate(); };
struct FindQuestObjectData {
    entryQuestRelationMap relationMap; questGuidpMap data;
    void operator()(GameObjectData const&);
};
#define GAI_VALUE2(type,name,qualifier) std::vector<int32>{}
struct GlobalQuestLocations { questGuidpMap data; auto const& RefGet() const { return data; } } locations;
struct SharedContext { template<class T> GlobalQuestLocations* getGlobalValue(std::string) { return &locations; } } sSharedValueContext;
struct NewRpgInfo {
    struct DoQuest { uint32 questId; Quest const* quest; };
    struct TravelRoute {};
    std::variant<std::monostate,DoQuest,TravelRoute> data;
    void ChangeToDoQuest(uint32 id,Quest const* q) { data=DoQuest{id,q}; }
    void ChangeToTravelRoute() { data=TravelRoute{}; }
};
struct ContinentRouteState {
    WorldPosition destination; bool forMaster=false;
    void Start(WorldPosition const& target,bool master) { destination=target; forMaster=master; }
};
struct Context {
    GuidVector npcs,corpses,objects; uint32 quest=0; Player* bot=nullptr;
    // Native "inventory items" with qualifier "start quest": owned items whose template starts a quest.
    struct StartItems { Player* bot; std::vector<Item*> Get() {
        std::vector<Item*> found; for(auto& [entry,item]:bot->inventory) if(item.proto.StartQuest) found.push_back(&item);
        return found; } } startItems{nullptr};
    template<class T> StartItems* GetValue(std::string const& name,std::string const& qualifier) {
        static_assert(std::is_same_v<T,std::vector<Item*>>);
        assert(name=="inventory items"&&qualifier=="start quest"); startItems.bot=bot; return &startItems;
    }
};
template<class T> T GetValue(Context* c,std::string const& name) {
    if constexpr(std::is_same_v<T,GuidVector>) {
        if(name=="nearest npcs") return c->npcs;
        if(name=="nearest corpses") return c->corpses;
        if(name=="nearest game objects no los") return c->objects;
        return {};
    }
    else return c->quest;
}
#define AI_VALUE(type,name) GetValue<type>(context,name)
struct PlayerbotAI {
    Player* bot; Context context; NewRpgInfo rpgInfo; bool master=false,castResult=true,moveResult=true;
    int casts=0,castChecks=0,waits=0,moves=0,farMoves=0,routeMoves=0;
    ContinentRouteState continentRoute;
    Unit* castTarget=nullptr; Item* castItem=nullptr; Spell* waitedFor=nullptr;
    std::map<uint32,Unit*> units; std::map<uint32,GameObject*> objects;
    struct { bool IsPending() const { return false; } } forceRebuff;
    Player* GetBot() const { return bot; } bool GetMaster() const { return master; }
    Context* GetAiObjectContext() { context.bot=bot; return &context; }
    Unit* GetUnit(ObjectGuid g) const { return units.contains(g.value)?units.at(g.value):nullptr; }
    GameObject* GetGameObject(ObjectGuid g) const { return objects.contains(g.value)?objects.at(g.value):nullptr; }
    bool CanCastSpell(uint32 id,Unit* target,bool,Item*,Item* item) {
        ++castChecks; castTarget=target; castItem=item;
        auto const* info=sSpellMgr->GetSpellInfo(id);
        if (!info||target!=bot||!item||bot->GetItemByEntry(item->entry)!=item) return false;
        GameObjectFocusCheck check(bot,info->RequiresSpellFocus);
        return std::any_of(objects.begin(),objects.end(),[&](auto const& pair){ return check(pair.second); });
    }
    bool CanCastSpell(uint32,GameObject*,bool,Item*) { return false; }
    void WaitForSpellCast(Spell* spell) { assert(spell); ++waits; waitedFor=spell; }
};
struct RouteCatalog {
    bool built=true,allowed=true; int scans=0;
    std::vector<ContinentRoutes::Link> links;
    bool Built() const { return built; }
    ContinentRoutes::Point Locate(WorldPosition const& p) const { return {p.map,p.x,p.y,p.z}; }
    std::vector<ContinentRoutes::Link> UsableLinks(Player*,ContinentRouteState const&) {
        ++scans; return allowed?links:std::vector<ContinentRoutes::Link>{};
    }
} sContinentRoutes;
bool pathResult=true;
struct MovementAction {
    PlayerbotAI* botAI; Player* bot; Context* context;
    MovementAction(PlayerbotAI* ai,std::string):botAI(ai),bot(ai->bot),context(&ai->context){}
    virtual ~MovementAction()=default; virtual bool isUseful(){return true;} virtual bool Execute(Event){return false;}
};
// The shared new RPG quest giver check: interaction state on the bot's map, without distance.
namespace NewRpgHelpers {
bool CanInteractWithQuestGiver(Player*,Creature* c) { return c->alive&&c->canInteract; }
bool CanInteractWithQuestGiver(Player* bot,GameObject* go) {
    return bot->GetMap()->GetGameObject(go->GetGUID())==go&&go->GetGoType()==GAMEOBJECT_TYPE_QUESTGIVER&&go->info.IconName!="Point";
}
}
struct NewRpgBaseAction:MovementAction {
    using MovementAction::MovementAction;
    bool MoveFarTo(WorldPosition) { if(!pathResult) return false; ++botAI->farMoves; return botAI->moveResult; }
    bool MoveToMap(WorldPosition const& target) {
        botAI->continentRoute.Start(target,false);
        auto const here=sContinentRoutes.Locate(WorldPosition(bot));
        auto const links=sContinentRoutes.allowed?sContinentRoutes.links:std::vector<ContinentRoutes::Link>{};
        auto const search=ContinentRoutes::Explore(links,here,[](auto const&){return true;});
        if(!pathResult||!ContinentRoutes::RouteTo(links,search,sContinentRoutes.Locate(target)).Found()) return false;
        ++botAI->routeMoves; return botAI->moveResult;
    }
    bool MoveWorldObjectTo(ObjectGuid) { if(!pathResult) return false; ++botAI->moves; return botAI->moveResult; }
    bool IsWithinInteractionDist(Creature* c) { return bot->GetDistance(c)<=INTERACTION_DISTANCE; }
    bool IsWithinInteractionDist(GameObject* go) { return go->IsWithinDistInMap(bot); }
    bool AcceptQuest(Quest const*,ObjectGuid);
    bool TurnInQuest(Quest const*,ObjectGuid);
    uint32 BestRewardIndex(Quest const*) { return 0; }
};
struct AiNamedObject {
    PlayerbotAI* botAI; Player* bot; Context* context;
    AiNamedObject(PlayerbotAI* ai,std::string):botAI(ai),bot(ai->bot),context(&ai->context){}
};
struct Trigger:AiNamedObject {
    Trigger(PlayerbotAI*,std::string const,int32 checkInterval=1);
    virtual ~Trigger()=default; virtual bool IsActive(){return false;}
    virtual bool IsBuffTrigger(){return false;} virtual bool IsDebuffTrigger(){return false;}
    bool needCheck(uint32);
    int32 checkInterval; uint32 lastCheckTime;
};
@@TRIGGERCONSTRUCTOR@@
@@SCHEDULE@@
template<class T> struct CalculatedValue {
    PlayerbotAI* botAI;
    CalculatedValue(PlayerbotAI* ai,std::string,int):botAI(ai){}
    virtual ~CalculatedValue()=default; virtual T Calculate()=0;
};
// The warlock steps use none of the shared action's attacks, quest objects or other class interactions.
struct AttackAction {
    AttackAction(PlayerbotAI*,std::string const) {}
protected:
    bool Attack(Unit*,bool=true) { assert(false); return false; }
};
namespace NewRpgHelpers {
bool IsQuestWorthDoing(Player*,Quest const*) { assert(false); return false; }
bool IsQuestCapableDoing(Player*,Quest const*) { assert(false); return false; }
}
struct UseItemAction {
    PlayerbotAI* botAI;
    explicit UseItemAction(PlayerbotAI* ai):botAI(ai){}
    bool UseItemOnUnit(Item*,Unit*);
    bool UseItemOnGameObject(Item*,ObjectGuid) { assert(false); return false; }
protected:
    bool UseGameObject(ObjectGuid) { assert(false); return false; }
public:
    bool UseItem(Item* item,ObjectGuid,Item* itemTarget,Unit* unitTarget) {
        Player* bot=botAI->GetBot(); uint32 spellId=0;
        auto const* itemProto=item->GetTemplate(); uint8 const spellSlotLimit=5;
        GameObject* goTarget=nullptr;
        @@PRECHECK@@
        ++botAI->casts;
        return botAI->castResult;
    }
};
@@CLASSES@@
@@ACCEPT@@
@@TURNIN@@
@@GATE@@
@@TABLE@@
@@LOCATIONS@@
@@ROUTECONSTRUCTOR@@
@@ROUTECOST@@
@@NEAREST@@
@@NEEDED@@
@@CURRENT@@
@@VALUE@@
@@TRIGGER@@
@@USEFUL@@
@@WRAPPER@@
@@GIVER@@
@@MOVE@@
@@TRAVEL@@
@@OBJECTIVES@@
@@RITUAL@@
@@FOCUSPOSITION@@
@@WAIT@@
@@RESTART@@
@@ABANDON@@
@@EXECUTE@@
Creature* ClassQuestChainAction::QuestTarget(Quest const*,ClassQuestStep const&,bool) { assert(false); return nullptr; }
bool ClassQuestChainAction::UseOnCreature(Quest const*,ClassQuestStep const&) { assert(false); return false; }
bool ClassQuestChainAction::UseObject(Quest const*,ClassQuestStep const&) { assert(false); return false; }
bool ClassQuestChainAction::StayWith(Quest const*,ClassQuestStep const&) { assert(false); return false; }
bool ClassQuestChainAction::CastOn(Quest const*,ClassQuestStep const&) { assert(false); return false; }
bool ClassQuestChainAction::ReachArea(Quest const*,ClassQuestStep const&) { assert(false); return false; }
WorldPosition ClassQuestChainAction::SpawnPosition(uint32,bool) { assert(false); return {}; }
@@RELATIONMAP@@
@@GOSPAWNRELATIONS@@
'''

tests = r'''
@@RELATIONS@@
uint32 NativeGiver(std::map<uint32,uint32> const& relations,uint32 quest) {
    return relations.contains(quest)?relations.at(quest):0;
}
struct Scenario {
    Player bot; PlayerbotAI ai{&bot}; ClassQuestChainValue value{&ai};
    ClassQuestChainTrigger trigger{&ai}; ClassQuestChainAction action{&ai};
    Creature giver; GameObject focus; TempSummon demon;
    ClassQuestStep const* data;
    explicit Scenario(uint32 id=1471) {
        bot.map.objects=&ai.objects;
        now=100000; sPlayerbotAIConfig={}; objectMgr={}; spellMgr={}; locations={}; sContinentRoutes={};
        spawns.clear(); spawnScans=0; pathResult=true;
        @@NATIVEQUESTS@@
        @@ITEMSPELLS@@
        data=&*std::find_if(std::begin(ClassQuestSteps),std::end(ClassQuestSteps),[id](auto const& row){return row.Quest==id;});
        bot.quests[id].Status=QUEST_STATUS_INCOMPLETE;
        // Gameobject givers are exercised by GameObjectScenario; these rows keep a creature giver double.
        giver.guid=2; giver.entry=NativeGiver(nativeStarters,id); giver.starts.insert(id);
        if(giver.entry==NativeGiver(nativeEnders,id)) giver.finishes.insert(id);
        ai.units[2]=&giver; ai.context.npcs={{2}};
        locations.data[id][uint32(QuestRelationFlag::questGiver)][giver.entry]={{0,2}};
        locations.data[id][uint32(QuestRelationFlag::questTaker)][NativeGiver(nativeEnders,id)]={{0,2}};
        focus.guid=3; focus.info.spellFocus.focusId=777; ai.objects[3]=&focus; ai.context.objects={{3}};
        if(data->Item) {
            auto& item=bot.inventory[data->Item]; item.entry=data->Item;
            item.proto.Spells[0].SpellId=itemSpells.at(data->Item);
            // Synthetic native metadata proves that the action reads the runtime focus id.
            spellMgr.spells[itemSpells.at(data->Item)].RequiresSpellFocus=777;
        }
        demon.guid=4; demon.entry=data->Entry; demon.summoner=bot.GetGUID(); ai.units[4]=&demon;
        ai.context.quest=value.Calculate();
    }
    void Offered() { bot.quests.clear(); bot.available.insert(data->Quest); ai.context.quest=value.Calculate(); }
    void Rewardable() {
        bot.quests[data->Quest].Status=QUEST_STATUS_COMPLETE;
        giver.entry=NativeGiver(nativeEnders,data->Quest); giver.starts.clear(); giver.finishes.insert(data->Quest);
    }
    void Objective(uint32 flags,int32 entry,WorldPosition pos) { locations.data[data->Quest][flags][entry]={pos}; }
    void Crossing() {
        sPlayerbotAIConfig.continentTravel=true;
        sContinentRoutes.links.push_back({ContinentRoutes::LinkKind::Transport,123,{0,0,0,0},{1,0,0,0},30});
        sContinentRoutes.links.push_back({ContinentRoutes::LinkKind::Transport,123,{1,0,0,0},{0,0,0,0},30});
    }
};
struct ClassQuestProbe:ClassQuestAction {
    explicit ClassQuestProbe(PlayerbotAI* ai):ClassQuestAction(ai,"fixture class quest"){}
    using ClassQuestAction::InteractWithQuestGiver;
    using ClassQuestAction::MoveToQuestLocation;
};
struct GameObjectScenario:Scenario {
    ClassQuestProbe questAction{&ai}; Quest const* quest;
    GameObjectScenario():quest(objectMgr.GetQuestTemplate(140)) {
        bot.quests.clear(); bot.available={140}; ai.context.npcs.clear();
        focus.entry=34; focus.info.type=GAMEOBJECT_TYPE_QUESTGIVER;
        objectMgr.goStarters.emplace(34,140); objectMgr.goEnders.emplace(33,140);
        FindQuestObjectData worker; worker.relationMap=EntryQuestRelationMapValue().Calculate();
        worker(GameObjectData{34,0,1,200,0,0}); worker(GameObjectData{33,0,1,300,0,0});
        locations.data=worker.data;
    }
    bool Accept() { return questAction.InteractWithQuestGiver(quest,false); }
    bool Reward() { return questAction.InteractWithQuestGiver(quest,true); }
    void Rewardable() { bot.quests[140].Status=QUEST_STATUS_COMPLETE; focus.entry=33; }
};
int main() {
    { Scenario s; assert(s.trigger.needCheck(now)&&s.trigger.needCheck(now+200)); }
    { Scenario s; s.bot.cls=3;
      assert(CanRunClassQuest(&s.ai,3)&&!CanRunClassQuest(&s.ai,CLASS_WARLOCK)&&!s.value.Calculate()); }
    { GameObjectScenario s;
      assert(locations.data[140][GIVER].contains(-34)&&locations.data[140][TAKER].contains(-33));
      assert(!locations.data[140][GIVER].contains(-33)&&!locations.data[140][TAKER].contains(-34));
      assert(s.Accept()&&s.bot.GetQuestStatus(140)==QUEST_STATUS_INCOMPLETE&&s.bot.session.accepts==1);
      s.Rewardable(); assert(s.Reward()&&s.bot.GetQuestRewardStatus(140)&&s.bot.session.rewards==1); }
    { GameObjectScenario s; s.bot.session.accept=false;
      assert(!s.Accept()&&s.bot.GetQuestStatus(140)==QUEST_STATUS_NONE&&s.bot.session.accepts==1); }
    { GameObjectScenario s; s.Rewardable(); s.bot.session.reward=false;
      assert(!s.Reward()&&!s.bot.GetQuestRewardStatus(140)&&s.bot.session.rewards==1); }
    { GameObjectScenario s; s.Rewardable(); s.bot.canReward=false;
      assert(!s.Reward()&&s.bot.session.rewards==0); }
    { GameObjectScenario s; s.focus.entry=33; assert(!s.Accept()&&s.bot.session.accepts==0); }
    { GameObjectScenario s; s.Rewardable(); s.focus.entry=34; assert(!s.Reward()&&s.bot.session.rewards==0); }
    for(auto field:{&WorldObject::inWorld,&WorldObject::sameMap,&WorldObject::samePhase,&WorldObject::visible}) {
        GameObjectScenario s; s.focus.*field=false; assert(!s.Accept()&&s.bot.session.accepts==0);
    }
    { GameObjectScenario s; s.focus.spawned=false; assert(!s.Accept()&&s.bot.session.accepts==0); }
    { GameObjectScenario s; s.focus.info.type=GAMEOBJECT_TYPE_SPELL_FOCUS; assert(!s.Accept()&&s.bot.session.accepts==0); }
    { GameObjectScenario s; s.focus.info.IconName="Point"; assert(!s.Accept()&&s.bot.session.accepts==0); }
    { GameObjectScenario s; s.focus.x=5.4f; assert(s.Accept()&&s.bot.session.accepts==1&&s.ai.moves==0); }
    { GameObjectScenario s; s.focus.x=6.0f; assert(s.Accept()&&s.bot.session.accepts==0&&s.ai.moves==1); }
    { GameObjectScenario s; s.focus.los=false; assert(s.Accept()&&s.bot.session.accepts==0&&s.ai.moves==1); }
    { GameObjectScenario s; s.focus.x=20; pathResult=false; assert(!s.Accept()&&s.bot.session.accepts==0); }
    { GameObjectScenario s; s.Crossing(); s.focus.x=20;
      assert(s.Accept()&&s.ai.routeMoves==1&&s.bot.session.accepts==0); }
    { GameObjectScenario s; s.ai.context.objects.clear();
      ClassQuestRouteCosts costs(&s.ai);
      assert(NearestClassQuestLocation(140,GIVER,costs)==WorldPosition(0,200));
      assert(NearestClassQuestLocation(140,TAKER,costs)==WorldPosition(0,300));
      assert(s.questAction.MoveToQuestLocation(s.quest,false)&&s.ai.farMoves==1);
      assert(s.questAction.MoveToQuestLocation(s.quest,true)&&s.ai.farMoves==2); }
    for(bool accepted:{false,true}) {
        Scenario s; ClassQuestProbe action(&s.ai); auto const* quest=objectMgr.GetQuestTemplate(1462);
        s.giver.finishes.insert(1462); s.bot.quests[1462].Status=QUEST_STATUS_COMPLETE; s.bot.session.reward=accepted;
        assert(action.InteractWithQuestGiver(quest,true)==accepted&&s.bot.session.rewards==1);
        assert(s.bot.GetQuestStatus(1462)==(accepted?QUEST_STATUS_NONE:QUEST_STATUS_COMPLETE));
        assert(!s.bot.GetQuestRewardStatus(1462));
    }
    for(auto const& row:ClassQuestSteps) {
        if(row.Class!=CLASS_WARLOCK||!row.Spell||!nativeStarters.contains(row.Quest)||!nativeEnders.contains(row.Quest)) continue;
        Scenario s(row.Quest);
        assert(s.value.Calculate()==row.Quest&&s.trigger.IsActive()&&s.action.isUseful());
        s.bot.known.insert(row.Spell); s.ai.context.quest=s.value.Calculate();
        assert(!s.ai.context.quest&&!s.action.Execute({}));
        s.bot.known.clear(); s.Offered();
        assert(s.value.Calculate()==row.Quest);
        assert(s.action.Execute({})&&s.bot.GetQuestStatus(row.Quest)==QUEST_STATUS_INCOMPLETE&&s.bot.session.accepts==1);
        if(objectMgr.quests.at(row.Quest).source) assert(s.bot.GetItemByEntry(objectMgr.quests.at(row.Quest).source));
        s.Rewardable();
        assert(s.action.Execute({})&&s.bot.GetQuestRewardStatus(row.Quest)&&s.bot.session.rewards==1);
        assert(s.bot.HasSpell(row.Spell)==bool(objectMgr.quests.at(row.Quest).rewardDemon));
    }
    for(auto const& row:ClassQuestSteps) if(row.Class==CLASS_WARLOCK&&row.Item) {
        Scenario s(row.Quest);
        assert(s.action.Execute({})&&s.ai.casts==1&&s.ai.waits==1&&s.ai.castTarget==&s.bot);
        assert(s.ai.castItem==s.bot.GetItemByEntry(row.Item)&&s.ai.waitedFor==&s.bot.generic);
        assert(s.bot.GetQuestStatus(row.Quest)==QUEST_STATUS_INCOMPLETE&&!s.bot.HasSpell(row.Spell)&&s.bot.GetPet());
        assert(std::get<NewRpgInfo::DoQuest>(s.ai.rpgInfo.data).questId==row.Quest);
        s.bot.quests[row.Quest].CreatureOrGOCount[0]=1;
        if(objectMgr.quests.at(row.Quest).RequiredNpcOrGo[0]) { assert(!s.action.Execute({})&&s.ai.casts==1); continue; }
        // No kill credit: the used-up item waits for the own corpse's loot, then the quest is taken again.
        s.bot.inventory.erase(row.Item); s.demon.alive=false; s.demon.loot=true; s.ai.context.corpses={{4}};
        assert(!s.action.Execute({})&&s.ai.casts==1&&s.bot.session.removals==0);
        s.demon.loot=false;
        assert(s.action.Execute({})&&s.bot.session.removals==1&&s.bot.GetQuestStatus(row.Quest)==QUEST_STATUS_NONE);
    }
    for(auto change:{+[](Scenario& s){s.demon.loot=false;},+[](Scenario& s){s.demon.entry=1;},
                     +[](Scenario& s){s.demon.summoner={200};},+[](Scenario& s){s.demon.visible=false;},
                     +[](Scenario& s){s.ai.context.corpses.clear();}}) {
        Scenario s(7603); s.bot.inventory.clear(); s.demon.alive=false; s.demon.loot=true; s.ai.context.corpses={{4}};
        change(s); assert(s.action.Execute({})&&s.bot.session.removals==1);
    }
    { Scenario s; s.bot.useChannel=true; assert(s.action.Execute({})&&s.ai.waitedFor==&s.bot.channel); }
    { Scenario s; s.ai.castResult=false; assert(!s.action.Execute({})&&s.ai.waits==0); }
    // A lost ritual item is restored only by abandoning the quest and accepting it again.
    { Scenario s; s.bot.inventory.clear();
      assert(s.action.Execute({})&&s.ai.casts==0&&s.bot.session.removals==1&&s.bot.GetQuestStatus(s.data->Quest)==QUEST_STATUS_NONE); }
    { Scenario s; s.bot.inventory.clear(); s.bot.bank.insert(s.data->Item);
      assert(!s.action.Execute({})&&s.bot.session.removals==0); }
    { Scenario s; s.bot.quests[s.data->Quest].Status=QUEST_STATUS_FAILED; s.ai.context.quest=s.value.Calculate();
      assert(s.ai.context.quest==s.data->Quest&&s.action.Execute({})&&s.bot.session.removals==1); }
    { Scenario s; spellMgr.spells.clear(); assert(!s.action.Execute({})&&s.ai.casts==0); }
    { Scenario s; spellMgr.spells.begin()->second.RequiresSpellFocus=0; assert(!s.action.Execute({})&&s.ai.casts==0); }
    auto rejected=[](auto change) {
        Scenario s; change(s);
        assert(!s.value.Calculate()&&!s.trigger.IsActive()&&!s.action.isUseful());
        assert(!s.action.Execute({})&&s.ai.casts==0&&s.ai.moves==0&&s.ai.farMoves==0);
    };
    rejected([](auto&){sPlayerbotAIConfig.naturalProgression=false;});
    rejected([](auto& s){s.ai.bot=nullptr;});
    // The shared chain value follows the class; a hunter has no warlock step to pursue.
    rejected([](auto& s){s.bot.cls=3; s.ai.context.quest=s.value.Calculate();});
    rejected([](auto& s){s.bot.hasSession=false;});
    rejected([](auto& s){s.bot.session.headless=false;});
    rejected([](auto& s){s.bot.random=false;});
    rejected([](auto& s){s.ai.master=true;});
    rejected([](auto& s){s.bot.group=true;});
    rejected([](auto& s){s.bot.alive=false;});
    rejected([](auto& s){s.bot.inWorld=false;});
    rejected([](auto& s){s.bot.teleport=true;});
    rejected([](auto& s){s.bot.map.dungeon=true;});
    rejected([](auto& s){s.bot.battleground=true;});
    rejected([](auto& s){s.bot.arena=true;});
    rejected([](auto& s){s.bot.combat=true;});
    rejected([](auto& s){s.bot.mounted=true;});
    rejected([](auto& s){s.bot.flight=true;});
    rejected([](auto& s){s.bot.flying=true;});
    rejected([](auto& s){s.bot.transport=true;});
    rejected([](auto& s){s.bot.vehicle=true;});
    rejected([](auto& s){s.bot.lostControl=true;});
    rejected([](auto& s){s.bot.casting=true;});
    { Scenario s; sPlayerbotAIConfig.IgnoredQuests.insert(s.data->Quest); assert(!s.action.Execute({})); }
    { Scenario s; s.bot.known.insert(s.data->Spell); assert(!s.action.Execute({})&&s.ai.casts==0); }
    { Scenario s; s.bot.quests[s.data->Quest].Status=QUEST_STATUS_REWARDED; assert(!s.value.Calculate()); }
    { Scenario s; s.Offered(); s.bot.ownAccess=false; assert(!s.value.Calculate()&&!s.action.Execute({})); }
    { Scenario s; s.Offered(); s.bot.canAdd=false; assert(!s.value.Calculate()&&!s.action.Execute({})); }
    { Scenario s; s.Offered(); s.bot.available.clear(); assert(!s.value.Calculate()&&!s.action.Execute({})); }
    { Scenario s; s.Offered(); locations.data[s.data->Quest][GIVER].clear();
      s.Objective(GIVER,s.giver.entry,{1,1}); assert(!s.value.Calculate()&&!s.action.Execute({})); }
    { Scenario s; s.Offered(); s.Objective(GIVER,s.giver.entry,{0,20});
      s.bot.available.insert(1504); locations.data[1504][GIVER][nativeStarters.at(1504)]={{0,10}};
      assert(s.value.Calculate()==1504); }
    { Scenario s; s.Offered(); s.bot.session.accept=false;
      assert(!s.action.Execute({})&&s.bot.GetQuestStatus(s.data->Quest)==QUEST_STATUS_NONE&&s.bot.session.accepts==1); }
    { Scenario s; s.bot.quests[s.data->Quest].Status=QUEST_STATUS_COMPLETE; s.bot.session.reward=false;
      assert(!s.action.Execute({})&&!s.bot.GetQuestRewardStatus(s.data->Quest)&&s.bot.session.rewards==1); }
    { Scenario s; s.bot.quests[s.data->Quest].Status=QUEST_STATUS_COMPLETE; s.bot.canReward=false;
      assert(!s.action.Execute({})&&s.bot.session.rewards==0); }
    for(auto field:{&Creature::removing,&Creature::canInteract}) {
        Scenario s; s.Offered(); s.giver.*field=(field==&Creature::removing);
        assert(!s.action.Execute({})&&s.bot.session.accepts==0);
    }
    for(auto field:{&WorldObject::inWorld,&WorldObject::sameMap,&WorldObject::samePhase,&WorldObject::visible,&WorldObject::alive}) {
        Scenario s; s.Offered(); s.giver.*field=false;
        assert(!s.action.Execute({})&&s.bot.session.accepts==0);
    }
    { Scenario s; s.Offered(); s.giver.starts.clear(); assert(!s.action.Execute({})&&s.bot.session.accepts==0); }
    { Scenario s; s.Offered(); s.giver.x=20; assert(s.action.Execute({})&&s.ai.moves==1&&s.bot.session.accepts==0); }
    { Scenario s; s.Offered(); s.giver.los=false; assert(s.action.Execute({})&&s.ai.moves==1&&s.bot.session.accepts==0); }
    { Scenario s; s.Offered(); s.ai.context.npcs.clear(); s.Objective(GIVER,s.giver.entry,{0,200});
      assert(s.action.Execute({})&&s.ai.farMoves==1&&s.bot.session.accepts==0); }
    { Scenario s; s.Offered(); s.ai.context.npcs.clear(); s.Objective(GIVER,s.giver.entry,{0,200}); pathResult=false;
      assert(!s.action.Execute({})&&s.ai.farMoves==0); }
    for(auto field:{&WorldObject::inWorld,&WorldObject::sameMap,&WorldObject::samePhase,&WorldObject::visible}) {
        Scenario s; s.focus.*field=false; assert(!s.action.Execute({})&&s.ai.castChecks==0);
    }
    { Scenario s; s.focus.spawned=false; assert(!s.action.Execute({})&&s.ai.castChecks==0); }
    { Scenario s; s.focus.info.type=3; assert(!s.action.Execute({})&&s.ai.castChecks==0); }
    { Scenario s; s.focus.info.spellFocus.focusId=778; assert(!s.action.Execute({})&&s.ai.castChecks==0); }
    { Scenario s; s.focus.info.spellFocus.focusId=778; spellMgr.spells.begin()->second.RequiresSpellFocus=778;
      assert(s.action.Execute({})&&s.ai.casts==1); }
    { Scenario s; s.focus.info.spellFocus.dist=20; s.focus.x=15;
      assert(s.action.Execute({})&&s.ai.casts==1&&s.ai.moves==0); }
    { Scenario s; s.focus.x=15; assert(s.action.Execute({})&&s.ai.farMoves==1&&s.ai.castChecks==0); }
    { Scenario s; s.ai.context.npcs.push_back({4}); assert(s.action.Execute({})&&s.ai.casts==0); }
    { Scenario s; s.ai.context.npcs.push_back({4}); s.demon.entry=1; assert(s.action.Execute({})&&s.ai.casts==1); }
    { Scenario s; s.ai.context.npcs.push_back({4}); s.demon.summoner={200}; assert(s.action.Execute({})&&s.ai.casts==1); }
    { Scenario s; s.ai.context.npcs.push_back({4}); s.demon.alive=false; assert(s.action.Execute({})&&s.ai.casts==1); }
    { Scenario s; s.ai.context.objects.clear(); objectMgr.objects[100].spellFocus.focusId=777;
      spawns={{100,0,1,200,0,0}}; assert(s.action.Execute({})&&s.ai.farMoves==1);
      assert(s.action.Execute({})&&spawnScans==1); }
    { Scenario s; s.ai.context.objects.clear(); objectMgr.objects[100].spellFocus.focusId=777;
      spawns={{100,0,2,200,0,0},{100,1,1,200,0,0}}; assert(!s.action.Execute({})&&s.ai.farMoves==0); }
    { Scenario s; s.ai.context.objects.clear(); objectMgr.objects[100].spellFocus.focusId=778;
      spawns={{100,0,1,200,0,0}}; assert(!s.action.Execute({})&&s.ai.farMoves==0); }
    { Scenario s; s.ai.context.objects.clear(); objectMgr.objects[100].spellFocus.focusId=777;
      spawns={{100,0,1,200,0,0}}; pathResult=false; assert(!s.action.Execute({})&&s.ai.farMoves==0); }
    { Scenario s(1795); s.ai.context.objects.clear(); s.giver.entry=6251; s.giver.questgiver=false;
      assert(s.action.Execute({})&&s.ai.casts==0&&s.ai.farMoves==0);
      s.giver.x=20; assert(s.action.Execute({})&&s.ai.farMoves==1);
      s.giver.x=2; s.giver.questgiver=true; assert(!s.action.Execute({})); }
    { Scenario s(1795); s.ai.context.objects.clear(); s.giver.questgiver=false; s.giver.starts.clear();
      assert(!s.action.Execute({})&&s.ai.farMoves==0); }
    { Scenario s(1795); s.ai.context.objects.clear(); s.giver.questgiver=false; s.giver.alive=false;
      assert(!s.action.Execute({})&&s.ai.farMoves==0); }
    { Scenario s(1470); s.Objective(1,1501,{0,200}); assert(s.action.Execute({})&&s.ai.farMoves==1);
      assert(std::get<NewRpgInfo::DoQuest>(s.ai.rpgInfo.data).questId==1470);
      s.bot.inventory[6281]={6281,3}; assert(!s.action.Execute({})&&s.ai.farMoves==1); }
    { Scenario s(1470); s.Objective(1,1501,{1,200}); assert(!s.action.Execute({})&&s.ai.farMoves==0); }
    { Scenario s(1470); s.Objective(1,1501,{0,20}); assert(!s.action.Execute({})&&s.ai.farMoves==0); }
    { Scenario s(1470); s.Objective(1,1501,{0,20,0,8}); assert(s.action.Execute({})&&s.ai.farMoves==1); }
    { Scenario s(1470); s.Objective(1,1501,{0,20}); s.bot.objectiveLos=false;
      assert(s.action.Execute({})&&s.ai.farMoves==1); }
    { Scenario s(1598); s.Objective(1,-85563,{0,20,0,8}); assert(s.action.Execute({})&&s.ai.farMoves==1);
      s.Objective(1,-85563,{0,1}); now+=60001; assert(!s.action.Execute({})&&s.ai.farMoves==1); }
    { Scenario s(1598); s.Objective(1,-85563,{0,0,0,3.2f}); assert(s.action.Execute({})&&s.ai.farMoves==1); }
    { Scenario s(1598); s.Objective(1,-85563,{0,20}); assert(s.action.Execute({})&&s.ai.farMoves==1); }
    { Scenario s(1470); s.Objective(1,1501,{1,2}); s.Crossing();
      assert(s.action.Execute({})&&s.ai.routeMoves==1&&s.ai.farMoves==0);
      assert(std::holds_alternative<NewRpgInfo::TravelRoute>(s.ai.rpgInfo.data));
      int const scans=sContinentRoutes.scans;
      assert(s.action.Execute({})&&sContinentRoutes.scans==scans);
      s.bot.transport=true; auto const destination=s.ai.continentRoute.destination;
      assert(!s.action.Execute({})&&s.ai.continentRoute.destination==destination);
      s.bot.transport=false; s.bot.mapId=1;
      assert(!s.action.Execute({})&&std::holds_alternative<NewRpgInfo::DoQuest>(s.ai.rpgInfo.data));
      assert(sContinentRoutes.scans>scans); }
    { Scenario s(1470); s.Objective(1,1501,{1,200}); s.Crossing(); sContinentRoutes.allowed=false;
      assert(!s.action.Execute({})&&s.ai.routeMoves==0);
      int const scans=sContinentRoutes.scans; assert(!s.action.Execute({})&&sContinentRoutes.scans==scans);
      now+=60001; assert(!s.action.Execute({})&&sContinentRoutes.scans>scans); }
    { Scenario s(1470); s.Objective(1,1501,{1,200}); s.Crossing(); sContinentRoutes.built=false;
      assert(!s.action.Execute({})&&s.ai.routeMoves==0); }
    { Scenario s(1470); s.Objective(1,1501,{1,200}); s.Crossing(); sPlayerbotAIConfig.continentTravel=false;
      assert(!s.action.Execute({})&&s.ai.routeMoves==0); }
    { Scenario s(1470); s.Objective(1,1501,{1,200}); s.Crossing(); pathResult=false;
      assert(!s.action.Execute({})&&s.ai.routeMoves==0); }
    { Scenario s; s.Offered(); s.ai.context.npcs.clear(); s.Objective(GIVER,s.giver.entry,{1,20}); s.Crossing();
      assert(s.value.Calculate()==s.data->Quest&&s.action.Execute({})&&s.ai.routeMoves==1); }
    { Scenario s; s.Offered(); s.ai.context.npcs.clear(); s.Objective(GIVER,s.giver.entry,{1,20}); s.Crossing();
      sPlayerbotAIConfig.continentTravel=false; assert(!s.value.Calculate()); }
    { Scenario s; s.ai.context.objects.clear(); s.ai.context.npcs.clear(); s.bot.mapId=1; s.Crossing();
      assert(s.action.Execute({})&&s.ai.routeMoves==1&&s.ai.continentRoute.destination.map==0); }
    { Scenario s; s.Offered(); s.giver.x=20; s.Crossing();
      assert(s.action.Execute({})&&s.ai.routeMoves==1&&s.bot.session.accepts==0); }
    { Scenario s; s.focus.x=15; s.Crossing(); assert(s.action.Execute({})&&s.ai.routeMoves==1&&s.ai.casts==0); }
    std::cout<<"Warlock demon quests: native chains, own access, quest packets, owned rituals, focus, pending summons and checked native routes passed\n";
}
'''

mutations = [
    ('ritual wait checked every engine tick', 'classes', 'Trigger(botAI, "class quest chain")',
     'Trigger(botAI, "class quest chain", 5)'),
    ('live actor ownership revalidated', 'current', 'if (!CanRunClassQuestChain(botAI))', 'if (false)'),
    ('already learned demon skipped', 'table', 'if (bot->HasSpell(spell))', 'if (false)'),
    ('ignored quest skipped', 'current', 'sPlayerbotAIConfig.IgnoredQuests.count(step.Quest)', 'false'),
    ('failed ritual quest abandoned', 'execute', 'if (status == QUEST_STATUS_FAILED)\n        return Abandon(step->Quest);', ''),
    ('own native quest access required', 'current', '!bot->CanTakeQuest(quest, false)', 'false'),
    ('own quest log capacity required', 'current', '!bot->CanAddQuest(quest, false)', 'false'),
    ('same map required without travel', 'routecost', 'pos.GetMapId() == _bot->GetMapId()', 'true'),
    ('configured earned routes required', 'routeconstructor', 'sPlayerbotAIConfig.continentTravel && sContinentRoutes.Built()', 'true'),
    ('nearest eligible native giver selected', 'current', 'costs->Cost(pos) < nearest',
     'costs->Cost(pos) <= nearest && !selected'),
    ('accepted packet result rechecked', 'giver', '&& bot->GetQuestStatus(quest->GetQuestId()) != QUEST_STATUS_NONE', ''),
    ('reward packet result rechecked', 'giver', 'bot->GetQuestRewardStatus(quest->GetQuestId()) ||', 'true ||'),
    ('native giver interaction required', 'giver', '!NewRpgHelpers::CanInteractWithQuestGiver(bot, creature) ||', ''),
    ('giver phase required', 'giver', '!bot->InSamePhase(creature) ||', ''),
    ('giver visibility required', 'giver', '!bot->CanSeeOrDetect(creature) ||', ''),
    ('giver relation required', 'giver', '!(reward ? creature->hasInvolvedQuest(quest->GetQuestId()) : creature->hasQuest(quest->GetQuestId()))', 'false'),
    ('giver line of sight required', 'giver', '!IsWithinInteractionDist(creature) || !bot->IsWithinLOSInMap(creature)', '!IsWithinInteractionDist(creature)'),
    ('native giver route required', 'travel', 'MoveFarTo(pos)', 'true'),
    ('native crossing required', 'travel', 'if (!MoveToMap(pos))', 'if (false)'),
    ('route execution configuration required', 'travel',
     'if (!sPlayerbotAIConfig.continentTravel || !sContinentRoutes.Built())', 'if (false)'),
    ('travel controller receives goal', 'travel', 'botAI->rpgInfo.ChangeToTravelRoute();', ''),
    ('objective still needed', 'needed', 'bot->GetItemCount(quest->RequiredItemId[index]) < quest->RequiredItemCount[index]', 'true'),
    ('cross-map objectives routed first', 'objectives', '_objectivePos.GetMapId() != bot->GetMapId()', 'false'),
    ('objective map cache retained during crossing', 'objectives', '_objectiveMap != bot->GetMapId()',
     '_objectivePos.GetMapId() != bot->GetMapId()'),
    ('unsuccessful objective search cached', 'objectives', '_objectivePos != WorldPosition() && !ClassQuestObjectiveNeeded',
     '!ClassQuestObjectiveNeeded'),
    ('quest chest approached', 'objectives', '_objectiveIsGameObject ||', ''),
    ('elevated quest target approached', 'objectives', 'std::abs(bot->GetPositionZ() - _objectivePos.GetPositionZ()) > 3.0f', 'false'),
    ('obscured quest target approached', 'objectives', '!bot->IsWithinLOS(_objectivePos.GetPositionX(), _objectivePos.GetPositionY(), _objectivePos.GetPositionZ())', 'false'),
    ('exact quest objective distance required', 'objectives', 'bot->GetExactDist(_objectivePos)', 'bot->GetDistance(_objectivePos)'),
    ('credited ritual not repeated', 'ritual', 'if (bot->GetReqKillOrCastCurrentCount(quest->GetQuestId(), step.Entry))',
     'if (false)'),
    ('ritual keeps its quest state', 'ritual', 'botAI->rpgInfo.ChangeToDoQuest(quest->GetQuestId(), quest);', ''),
    ('lost ritual item restored by its quest', 'ritual', 'return Restart(quest, step.Item);', 'return false;'),
    ('banked ritual item kept', 'restart', ' || bot->HasItemCount(itemId, 1, true)', ''),
    ('native summon hostility delay respected', 'ritual', '== bot->GetGUID())\n                return true;',
     '== bot->GetGUID())\n                return false;'),
    ('only own summon blocks ritual', 'ritual', 'creature->ToTempSummon()->GetSummonerGUID() == bot->GetGUID()', 'true'),
    ('only living summon blocks ritual', 'ritual', 'creature->IsAlive() &&', ''),
    ('only summoned entry blocks ritual', 'ritual', 'creature->GetEntry() == step.Entry && ', ''),
    ('own summon corpse loot awaited', 'ritual', 'AI_VALUE(GuidVector, "nearest corpses")', 'GuidVector()'),
    ('only lootable summon corpse awaited', 'ritual', 'bot->isAllowedToLoot(creature) &&', ''),
    ('only own summon corpse awaited', 'ritual', 'creature->ToTempSummon() &&\n                creature->ToTempSummon()->GetSummonerGUID() == bot->GetGUID())\n                return false;',
     'creature->ToTempSummon())\n                return false;'),
    ('only visible summon corpse awaited', 'ritual', '&&\n                Usable(bot, creature) &&', '&&'),
    ('spawned focus required', 'ritual', '!focus->isSpawned() ||', ''),
    ('usable focus required', 'ritual', '!Usable(bot, focus) || ', ''),
    ('native focus type required', 'ritual', 'focus->GetGoType() != GAMEOBJECT_TYPE_SPELL_FOCUS ||', ''),
    ('runtime focus id required', 'ritual', 'focus->GetGOInfo()->spellFocus.focusId != spell->RequiresSpellFocus', 'false'),
    ('native focus range required', 'ritual', 'IsWithinDistInMap(bot, focus->GetGOInfo()->spellFocus.dist)',
     'IsWithinDistInMap(bot, 5.0f)'),
    ('owned item kept in cast validation', 'precheck', 'false, itemTarget, item)', 'false, itemTarget, nullptr)'),
    ('generic ritual cast waited', 'table', 'if (!cast)\n        cast = bot->GetCurrentSpell(CURRENT_GENERIC_SPELL);', ''),
    ('native focus spawn phase required', 'focusposition', 'if (!(spawn->phaseMask & bot->GetPhaseMask()))', 'if (false)'),
    ('native focus spawn id required', 'focusposition', 'entry.second.spellFocus.focusId == focusId', 'true'),
    ('native focus search cached', 'focusposition', 'GetMSTimeDiffToNow(_focusChecked) < MINUTE * IN_MILLISECONDS', 'false'),
    ('native focus route required', 'ritual', 'return MoveToQuestPosition(pos);\n    if (!step.Entry)',
     'return true;\n    if (!step.Entry)'),
    ('only active Strahad escort waited', 'ritual', '!giver->HasNpcFlag(UNIT_NPC_FLAG_QUESTGIVER)', 'true'),
    ('only the quest giver escort waited', 'ritual', 'giver->hasQuest(quest->GetQuestId()) && ', ''),
    ('only a living escort waited', 'ritual', 'giver->IsAlive() && ', ''),
    ('ritual without a focus returns to its giver', 'ritual', 'return MoveToQuestLocation(quest, false);\n}',
     'return false;\n}'),
    ('native gameobject enders populate takers', 'relationmap', 'sObjectMgr->GetGOQuestInvolvedRelationMap()',
     'sObjectMgr->GetGOQuestRelationMap()'),
    ('native gameobject entries stay signed', 'gospawnrelations', 'int32 entry = goData.id * -1;', 'int32 entry = goData.id;'),
    ('gameobject no-los producer used', 'giver', '"nearest game objects no los"', '"nearest game objects"'),
    ('gameobject in world required', 'giver', '!go->IsInWorld() ||', ''),
    ('gameobject spawn required', 'giver', '!go->isSpawned() ||', ''),
    ('gameobject map required', 'giver', '!bot->IsInMap(go) ||', ''),
    ('gameobject phase required', 'giver', '!bot->InSamePhase(go) ||', ''),
    ('gameobject visible required', 'giver', '!bot->CanSeeOrDetect(go) ||', ''),
    ('native gameobject interaction required', 'giver', '!NewRpgHelpers::CanInteractWithQuestGiver(bot, go) ||', ''),
    ('gameobject relation required', 'giver',
     '!(reward ? go->hasInvolvedQuest(quest->GetQuestId()) : go->hasQuest(quest->GetQuestId()))', 'false'),
    ('native gameobject interaction range required', 'giver', '!IsWithinInteractionDist(go) ||', ''),
    ('gameobject line of sight required', 'giver', '!IsWithinInteractionDist(go) || !bot->IsWithinLOSInMap(go)',
     '!IsWithinInteractionDist(go)'),
    ('repeatable reward completion recognized', 'giver', 'quest->IsRepeatable() && before == QUEST_STATUS_COMPLETE',
     'false && before == QUEST_STATUS_COMPLETE'),
    ('repeatable reward packet result rechecked', 'giver',
     'bot->GetQuestStatus(quest->GetQuestId()) == QUEST_STATUS_NONE', 'true'),
]
for label, predicate in (
        ('earned play mode', 'sPlayerbotAIConfig.naturalProgression'),
        ('requested class', 'bot->getClass() == classId'),
        ('headless session', 'bot->GetSession()->IsHeadless()'),
        ('random ownership', 'sRandomPlayerbotMgr.IsRandomBot(bot)'),
        ('no human controller', '!botAI->GetMaster()'),
        ('solo character', '!bot->GetGroup()'),
        ('living character', 'bot->IsAlive()'),
        ('character in world', 'bot->IsInWorld()'),
        ('no teleport in progress', '!bot->IsBeingTeleported()'),
        ('outside instance', '!bot->GetMap()->IsDungeon()'),
        ('outside battleground', '!bot->InBattleground()'),
        ('outside arena', '!bot->InArena()'),
        ('outside combat', '!bot->IsInCombat()'),
        ('unmounted character', '!bot->IsMounted()'),
        ('no flight path', '!bot->IsInFlight()'),
        ('no flying character', '!bot->IsFlying()'),
        ('no moving transport', '!bot->GetTransport()'),
        ('no vehicle', '!bot->GetVehicle()'),
        ('own control', '!bot->HasUnitState(UNIT_STATE_LOST_CONTROL)'),
        ('no overlapping cast', '!bot->IsNonMeleeSpellCast(true)')):
    mutations.append((label, 'gate', predicate, 'classId != 0' if label == 'requested class' else 'true'))
for label, key, old, _ in mutations:
    assert old in production[key], label


def build(directory, parts, name):
    text = prelude + tests
    for key, value in parts.items():
        text = text.replace('@@' + key.upper() + '@@', value)
    path = directory / (name + '.cpp')
    path.write_text(text)
    binary = directory / name
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-missing-field-initializers',
                    *SANITIZER_FLAGS, str(path), '-o', str(binary)], check=True)
    return run_fixture([str(binary)])


with tempfile.TemporaryDirectory(prefix='portable-warlock-demons-') as temporary:
    directory = Path(temporary)
    result = build(directory, production, 'demons')
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit('Warlock demon quest fixture failed')

    reject_part_mutants(production, mutations, lambda parts, tag: build(directory, parts, tag),
                        'Warlock demon quest')
