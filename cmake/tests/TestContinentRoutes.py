"""Check that bots change maps and islands only over links an ordinary player can take.

The production route planner, walk islands, link catalog with ships, lifts,
portals and area triggers, Individual Progression arrival gate, transport
docking and lift tests, flight search, flight master discovery, companion
trigger and the RPG start of travel run against doubles that answer as the
core, the playerbots travel data and Individual Progression do. Native
contracts and the shipped travel data the doubles rely on are asserted from the
pinned sources. Route execution is checked to use only the core's area
trigger, game object, spell, item, taxi and flight-master interaction handlers.
Mutation checks confirm that each gate is required. No realm is started.
"""

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
)


repository = Path(__file__).resolve().parents[2]
core = prepared_core(repository)
module = core / 'modules/mod-playerbots/src'
ip_source = core / 'modules/mod-individual-progression/src'


def read(path):
    return path.read_text(encoding='utf-8')


policy = read(module / 'Mgr/Travel/ContinentRoutePolicy.h')
routes_header = read(module / 'Mgr/Travel/ContinentRoutes.h')
routes = read(module / 'Mgr/Travel/ContinentRoutes.cpp')
progression = read(module / 'Mgr/Travel/ContinentRouteProgression.cpp')
travel = read(module / 'Mgr/Travel/TravelMgr.cpp')
ai = read(module / 'Bot/PlayerbotAI.cpp')
triggers = read(module / 'Ai/Base/Trigger/TravelTriggers.cpp')
rpg = read(module / 'Ai/World/Rpg/Action/NewRpgAction.cpp')
rpg_base = read(module / 'Ai/World/Rpg/Action/NewRpgBaseAction.cpp')
action_context = read(module / 'Ai/Base/ActionContext.h')
trigger_context = read(module / 'Ai/Base/TriggerContext.h')
rpg_strategy = read(module / 'Ai/World/Rpg/Strategy/NewRpgStrategy.cpp')
follow_strategy = read(module / 'Ai/Base/Strategy/FollowMasterStrategy.cpp')
config = read(module / 'PlayerbotAIConfig.cpp')
conf_dist = read(core / 'modules/mod-playerbots/conf/playerbots.conf.dist')
ip_header = read(ip_source / 'IndividualProgression.h')
ip_player = read(ip_source / 'IndividualProgressionPlayer.cpp')
ip_main = read(ip_source / 'IndividualProgression.cpp')
shared = read(core / 'src/server/shared/SharedDefines.h')
dbc_enums = read(core / 'src/server/shared/DataStores/DBCEnums.h')
dbc_structure = read(core / 'src/server/shared/DataStores/DBCStructure.h')
follow = read(module / 'Ai/Base/Actions/FollowActions.cpp')
transport_mgr = read(core / 'src/server/game/Maps/TransportMgr.cpp')
transport_mgr_header = read(core / 'src/server/game/Maps/TransportMgr.h')
go_data = read(core / 'src/server/game/Entities/GameObject/GameObjectData.h')
terrain = read(core / 'src/server/game/Grids/GridTerrainData.h')
area_defines = read(core / 'src/server/game/Maps/AreaDefines.h')
transport_mgr_header = read(core / 'src/server/game/Maps/TransportMgr.h')
transport_mgr = read(core / 'src/server/game/Maps/TransportMgr.cpp')
transport = read(core / 'src/server/game/Entities/Transport/Transport.cpp')
misc_handler = read(core / 'src/server/game/Handlers/MiscHandler.cpp')
rpg_trigger = read(module / 'Ai/World/Rpg/Trigger/NewRpgTrigger.cpp')
travel_node = read(module / 'Mgr/Travel/TravelNode.h')
database = read(module / 'Db/PlayerbotsDatabase.cpp')
taxi_handler = read(core / 'src/server/game/Handlers/TaxiHandler.cpp')
map_source = read(core / 'src/server/game/Maps/Map.cpp')
game_object = read(core / 'src/server/game/Entities/GameObject/GameObject.h')
player_source = read(core / 'src/server/game/Entities/Player/Player.cpp')
world_data = core / 'data/sql/base/db_world'
travel_data = core / 'modules/mod-playerbots/data/sql/playerbots/base'


def value(source, name):
    match = re.search(r'\b' + re.escape(name) + r'\s*=\s*(\d+)', source)
    assert match, name
    return int(match.group(1))


# Native contracts the doubles below rely on.
assert value(policy, 'AreaTeamAlliance') == value(dbc_enums, 'AREATEAM_ALLY')
assert value(policy, 'AreaTeamHorde') == value(dbc_enums, 'AREATEAM_HORDE')
assert 'bool IsStopFrame() const { return Node->actionFlag == 2; }' in transport_mgr_header
assert 'uint32(curPathTime * IN_MILLISECONDS)' in transport_mgr
assert 'transport->pathTime = keyFrames.back().DepartureTime;' in transport_mgr
docking = function(transport, 'void MotionTransport::Update(uint32 diff)')
assert 'uint32 timer = GetPathProgress() % GetPeriod();' in docking
assert re.search(r'if \(timer >= _currentFrame->ArriveTime\).*?if \(timer < _currentFrame->DepartureTime\)\s*\{\s*'
                 r'SetMoving\(false\);', docking, re.DOTALL)
assert 'uint32 GetPeriod() const { return GetUInt32Value(GAMEOBJECT_LEVEL); }' in read(
    core / 'src/server/game/Entities/Transport/Transport.h')
area_trigger_handler = function(misc_handler, 'void WorldSession::HandleAreaTriggerOpcode(WorldPacket& recv_data)')
assert 'if (!player->IsInAreaTriggerRadius(atEntry, isTavernAreatrigger ? 5.f : 0.f))' in area_trigger_handler
assert 'player->TeleportTo(at->target_mapId' in area_trigger_handler
# Individual Progression: characters without earned TBC need a blocking account query before the
# starting-zone rule, and the null-session probe the strict path uses has no side effects.
ip_gate = function(ip_player, 'static bool CanEnterMap(Player* player, uint32 mapid, float x, float y, float z, '
                              'WorldSession* session)')
outland = ip_gate[ip_gate.index('if (mapid == MAP_OUTLAND)'):ip_gate.index('if (mapid == MAP_ZUL_AMAN)')]
assert '!sIndividualProgression->hasPassedProgression(player, PROGRESSION_PRE_TBC)' in outland
assert 'GetAccountProgression(accountId)' in outland and 'return IsTBCRaceStartingZone(mapid, x, y, z);' in outland
assert 'player->getRace() != RACE_DRAENEI && player->getRace() != RACE_BLOODELF' in outland
assert 'CharacterDatabase.Query(' in function(ip_main, 'uint8 IndividualProgression::GetAccountProgression(uint32 accountId)')
northrend = ip_gate[ip_gate.index('if (mapid == MAP_NORTHREND && '):]
assert re.match(r'if \(mapid == MAP_NORTHREND && !sIndividualProgression->hasPassedProgression\(player, '
                r'PROGRESSION_TBC_TIER_5\)\)\s*\{\s*if \(!session\)\s*return false;', northrend)
assert 'return IndividualPlayerProgression::CanEnterMap(player, mapId, x, y, z, nullptr);' in ip_player
assert 'return sIndividualProgression->GetPlayerProgressionFromQuests(player) >= state;' in function(
    ip_main, 'bool IndividualProgression::hasPassedProgression(Player* player, ProgressionState state) const')
assert re.search(r'if \(enabled && strictEarnedProgression\)\s*return false;',
                 function(ip_main, 'bool IndividualProgression::isBotAccount(const Player* player)'))
path_types = function(travel_node, 'enum class TravelNodePathType : uint8') + ';'
# Islands and lifts come from the playerbots travel tables in the column order of these queries.
assert '"SELECT id, name, map_id, x, y, z, linked FROM playerbots_travelnode"' in database
assert '"SELECT node_id, to_node_id,type,object,distance,swim_distance, extra_cost,calculated, ' in database
assert '[[nodiscard]] bool IsWorldMap() const { return map_type == MAP_COMMON; }' in dbc_structure
# The core finds a static transport only when it is the one nearest the passenger.
assert 'if (GameObject* staticTrans = worldobject->FindNearestGameObjectOfType(GAMEOBJECT_TYPE_TRANSPORT, 75.0f))' in \
    function(map_source, 'Transport* Map::GetTransportForPos(')
assert ('Transport* ToTransport() { if (GetGOInfo()->type == GAMEOBJECT_TYPE_MO_TRANSPORT || GetGOInfo()->type == '
        'GAMEOBJECT_TYPE_TRANSPORT) return reinterpret_cast<Transport*>(this); else return nullptr; }') in game_object
assert 'GameObjectModel* m_model;' in game_object
learn = function(taxi_handler, 'bool WorldSession::SendLearnNewTaxiNode(Creature* unit)')
assert 'uint32 curloc = sObjectMgr->GetNearestTaxiNode(*unit, GetPlayer()->GetTeamId(true));' in learn
assert 'if (GetPlayer()->m_taxi.SetTaximaskNode(curloc))' in learn
assert 'info.taxiNodeId = sObjectMgr->GetNearestTaxiNode(x, y, z, mapId, TEAM_ALLIANCE);' in travel
interaction = function(player_source, 'Creature* Player::GetNPCIfCanInteractWith(ObjectGuid const& guid, uint32 npcflagmask)')


def sql_tuples(path, pattern):
    return [match.groups() for match in re.finditer(pattern, path.read_text(encoding='utf-8', errors='replace'),
                                                     re.MULTILINE)]


# The shipped travel data separates the islands the planner relies on, and its lifts are spawned.
nodes = {int(i): (name, int(m), float(x), float(y), float(z)) for i, name, m, x, y, z in sql_tuples(
    travel_data / 'playerbots_travelnode.sql', r"^\((\d+), '((?:[^'\\]|\\.)*)', (\d+), (-?[\d.]+), (-?[\d.]+), (-?[\d.]+)")}
links = [tuple(map(int, row)) for row in sql_tuples(travel_data / 'playerbots_travelnode_link.sql',
                                                     r"^\((\d+), (\d+), (\d+), (\d+),")]
parent = {node: node for node in nodes}


def root(node):
    while parent[node] != node:
        parent[node] = parent[parent[node]]
        node = parent[node]
    return node


for first, second, kind, _ in links:
    if kind == value(path_types, 'walk') and first in nodes and second in nodes and nodes[first][1] == nodes[second][1]:
        parent[root(first)] = root(second)


def island(name):
    found = [node for node, row in nodes.items() if row[0] == name]
    assert found, name
    return {root(node) for node in found}


assert island('Night Elf start').isdisjoint(island('Ruttheran Village flightMaster'))
assert island('Night Elf start').isdisjoint(island('Darkshore Auberdine'))
assert island('Thunder Bluff flightMaster').isdisjoint(island('Orc and Troll start'))
assert island('Human start') & island('Dwarf and Gnome start')
lift = value(path_types, 'transport')
tram = [(first, second) for first, second, kind, entry in links if kind == lift and entry == 176080]
assert tram and all(nodes[a][1] == nodes[b][1] == 369 and root(a) != root(b) for a, b in tram)
spawns = [row for row in sql_tuples(world_data / 'gameobject.sql', r"^\(\d+,(\d+),(\d+),\d+,\d+,\d+,\d+,(-?[\d.]+),(-?[\d.]+)")
          if row[0] in ('4170', '176080')]
templates = {entry: kind for entry, kind in sql_tuples(world_data / 'gameobject_template.sql', r"^\((4170|176080),(\d+),")}
assert templates == {'4170': str(value(shared, 'GAMEOBJECT_TYPE_TRANSPORT')),
                     '176080': str(value(shared, 'GAMEOBJECT_TYPE_TRANSPORT'))}
for entry in (4170, 176080):
    stops = [nodes[n] for first, second, kind, item in links if kind == lift and item == entry for n in (first, second)]
    assert any(int(spawn[1]) == stop[1] and ((float(spawn[2]) - stop[2]) ** 2 + (float(spawn[3]) - stop[3]) ** 2)
               ** 0.5 <= value(routes_header, 'LiftSpawnYards') for spawn in spawns if int(spawn[0]) == entry
               for stop in stops), entry
ip_zones = set(re.findall(r'AREA_\w+', function(ip_player, 'static bool IsTBCRaceStartingZone(')))
starting_zone = function(progression, 'bool IsTbcRaceStartingZone(uint32 zoneId)')
assert set(re.findall(r'AREA_\w+', starting_zone)) == ip_zones and len(ip_zones) == 8


def defines(names, *sources):
    lines = []
    for name in names:
        found = [value(source, name) for source in sources if re.search(r'\b' + name + r'\s*=\s*\d+', source)]
        assert found, name
        lines.append(f'constexpr uint32 {name} = {found[0]};')
    return '\n'.join(lines)


natives = defines(sorted(ip_zones), area_defines, ip_header) + '\n' + '\n'.join([
    defines(['MAP_OUTLAND', 'MAP_NORTHREND'], area_defines),
    defines(['RACE_HUMAN', 'RACE_BLOODELF', 'RACE_DRAENEI', 'GAMEOBJECT_TYPE_GOOBER', 'GAMEOBJECT_TYPE_MO_TRANSPORT',
             'GAMEOBJECT_TYPE_SPELLCASTER', 'GAMEOBJECT_TYPE_TRANSPORT', 'SPELL_EFFECT_TELEPORT_UNITS',
             'SPELL_EFFECT_TRIGGER_SPELL', 'SPELLFAMILY_GENERIC', 'SPELLFAMILY_MAGE'], shared),
    defines(['MAP_COMMON', 'MAP_INSTANCE'], dbc_enums),
    defines(['GO_STATE_ACTIVE', 'GO_STATE_READY'], go_data),
    f'constexpr float INVALID_HEIGHT = {re.search(r"#define INVALID_HEIGHT\s+(-?[\d.]+f)", terrain)[1]};',
    f'constexpr float INTERACTION_DISTANCE = {re.search(r"#define INTERACTION_DISTANCE\s+([\d.]+f)", read(core / "src/server/game/Entities/Object/ObjectDefines.h"))[1]};',
    defines(['FACTION_MASK_ALLIANCE', 'FACTION_MASK_HORDE'], dbc_enums),
    *(f'constexpr ProgressionState {name} = ProgressionState({value(ip_header, name)});'
      for name in ('PROGRESSION_PRE_TBC', 'PROGRESSION_TBC_TIER_5')),
    f'constexpr std::size_t TaxiMaskSize = {value(dbc_structure, "TaxiMaskSize")};',
    f'constexpr uint8 MAX_SPELL_EFFECTS = {int(re.search(r"#define MAX_SPELL_EFFECTS (\d+)", dbc_structure)[1])};',
    f'constexpr uint8 MAX_SPELL_REAGENTS = {int(re.search(r"#define MAX_SPELL_REAGENTS (\d+)", dbc_structure)[1])};',
])

# Route execution uses ordinary handlers only: no relocation, passenger, item, money or quest grants.
execution = {name: function(rpg_base, signature) for name, signature in {
    'move': 'bool NewRpgBaseAction::MoveToMap(WorldPosition const& dest, bool master)',
    'overland': 'bool NewRpgBaseAction::MoveOverland(WorldPosition const& target)',
    'take': 'bool NewRpgBaseAction::TakeLink(ContinentRouteState& route)',
    'use': 'bool NewRpgBaseAction::UseLinkObject(ContinentRouteState& route)',
    'board': 'bool NewRpgBaseAction::BoardTransport(ContinentRouteState& route)',
    'ride': 'bool NewRpgBaseAction::RideTransport(ContinentRouteState& route, Transport* transport)',
    'straight': 'bool NewRpgBaseAction::MoveStraightTo(WorldPosition const& point)',
    'lift board': 'bool NewRpgBaseAction::BoardLift(ContinentRouteState& route)',
    'lift ride': 'bool NewRpgBaseAction::RideLift(ContinentRouteState& route, Transport* lift)',
}.items()}
execution['discover'] = function(rpg, 'bool NewRpgDiscoverFlightAction::Execute(Event /*event*/)')
execution['route action'] = function(rpg, 'bool NewRpgTravelRouteAction::Execute(Event /*event*/)')
execution['master action'] = function(rpg, 'bool TravelToMasterAction::Execute(Event /*event*/)')
execution['follow step'] = function(follow, 'bool FollowAction::StepOnto(WorldPosition const& point)')
FORBIDDEN = ('TeleportTo', 'Relocate(', 'AddPassenger', 'ResurrectPlayer', 'SetTaxiCheater', 'AddItem', 'StoreNewItem',
             'ModifyMoney', 'learnSpell', 'AddQuest', 'RewardQuest', 'SetTaximaskNode', 'CastSpell(link.object, bot, true')


def assert_ordinary(bodies):
    for name, body in bodies.items():
        for token in FORBIDDEN:
            assert token not in body, f'{name} uses {token}'
    use = bodies['use']
    assert 'bot->GetSession()->HandleAreaTriggerOpcode(packet);' in use
    assert 'bot->GetSession()->HandleGameObjectUseOpcode(packet);' in use
    assert 'used = botAI->CastSpell(link.object, bot);' in use
    assert 'botAI->DoSpecificAction("hearthstone", Event("continent route"), true);' in use
    overland = bodies['overland']
    flight = '!CanUseTaxiNodes(bot, nodes) || !bot->ActivateTaxiPathTo(nodes, flightMaster, 0)'
    assert flight in overland and overland.count('ActivateTaxiPathTo') == 1
    assert overland.index(flight) > overland.index('bot->GetDistance(route.flightMasterPos) > INTERACTION_DISTANCE')
    take = bodies['take']
    assert 'if (bot->IsInAreaTriggerRadius(trigger))\n            return UseLinkObject(route);' in take
    assert 'bot->GetExactDist2d(from) <= INTERACTION_DISTANCE - 2.5f' in take
    board = bodies['lift board']
    assert 'if (!ContinentTravel::OnTransport(lift, bot->GetPhaseMask(), link.from.x, link.from.y, link.from.z))' in board
    assert board.index('ContinentTravel::OnTransport(lift') < board.index('MoveStraightTo(from);')
    assert 'if (!lift)\n            return true;' in board and board.index('if (!lift)') < board.index('FailLink(route);')
    # A replan that drops the lift link under way rides on to the next stop before planning from the ground.
    move = bodies['move']
    ride_on = ('if (ContinentTravel::HoldsStill(transport, ContinentTravel::StepOffMs) &&\n'
               '            ContinentTravel::FindLandingPoint(bot, transport, landing))\n'
               '            MoveStraightTo(landing);\n        return true;\n    }')
    assert ride_on in move and move.index(ride_on) < move.index('sContinentRoutes.UsableLinks(bot, route)')
    assert 'MovePoint(0, x, y, z, FORCED_MOVEMENT_NONE, 0.0f, 0.0f, false, false);' in bodies['follow step']
    discover = bodies['discover']
    learn = 'bot->GetSession()->SendLearnNewTaxiNode(flightMaster);'
    assert ('if (flightMaster && bot->GetNPCIfCanInteractWith(flightMaster->GetGUID(), UNIT_NPC_FLAG_FLIGHTMASTER))\n'
            '        ' + learn) in discover and discover.count('SendLearnNewTaxiNode') == 1


assert_ordinary(execution)
for label, name, old, new in [
    ('route teleport', 'board', 'MoveStraightTo(deck);', 'bot->TeleportTo(deck);'),
    ('boarding attaches the bot', 'board', 'MoveStraightTo(deck);', 'docked->AddPassenger(bot);'),
    ('remote area trigger', 'take', 'if (bot->IsInAreaTriggerRadius(trigger))', 'if (true)'),
    ('flight without discovered route', 'overland', '!CanUseTaxiNodes(bot, nodes) || ', ''),
    ('triggered teleport spell', 'use', 'botAI->CastSpell(link.object, bot)', 'botAI->CastSpell(link.object, bot, true)'),
    ('companion step teleports', 'follow step', 'bot->GetMotionMaster()->MovePoint(0, x, y, z,',
     'bot->TeleportTo(bot->GetMapId(), x, y, z, 0.0f); (void)(0,'),
    ('tram link given up while its car is away', 'lift board', 'if (!lift)\n            return true;\n', ''),
    ('walking off a moving car after a replan', 'move',
     '            MoveStraightTo(landing);\n        return true;\n    }', '            MoveStraightTo(landing);\n    }'),
    ('lift boarded away from its stop', 'lift board',
     'if (!ContinentTravel::OnTransport(lift, bot->GetPhaseMask(), link.from.x, link.from.y, link.from.z))',
     'if (false)'),
    ('flight point learned without speaking', 'discover',
     'flightMaster && bot->GetNPCIfCanInteractWith(flightMaster->GetGUID(), UNIT_NPC_FLAG_FLIGHTMASTER)',
     'flightMaster'),
    ('flight point granted', 'discover', 'bot->GetSession()->SendLearnNewTaxiNode(flightMaster);',
     'bot->m_taxi.SetTaximaskNode(master->taxiNodeId);'),
]:
    mutated = {**execution, name: execution[name].replace(old, new)}
    assert mutated[name] != execution[name], label
    try:
        assert_ordinary(mutated)
    except AssertionError:
        print(f'Continent route static mutation rejected: {label}')
    else:
        raise SystemExit(f'Continent route static check did not reject: {label}')

# Wiring: every new name is registered and the shipped default stays off upstream.
assert 'creators["new rpg travel route"] = &ActionContext::new_rpg_travel_route;' in action_context
assert 'creators["travel to master"] = &ActionContext::travel_to_master;' in action_context
assert 'creators["travel route status"] = &TriggerContext::travel_route_status;' in trigger_context
assert 'creators["master far away"] = &TriggerContext::master_far_away;' in trigger_context
assert '"travel route status",\n            {\n                NextAction("new rpg travel route", 3.0f)' in rpg_strategy
assert 'new TriggerNode("master far away", {NextAction("travel to master", ACTION_NORMAL)})' in follow_strategy
assert 'GetOption<bool>("Playerbots.ContinentTravel", false)' in config
assert '\nPlayerbots.ContinentTravel = 0\n' in conf_dist and '\nPlayerbots.RpgStatusProbWeight.TravelRoute = 0\n' in conf_dist
# The unused upstream Dark Portal actions granted quests without their givers.
assert 'dark portal' not in action_context and 'dark portal' not in trigger_context
assert 'creators["new rpg discover flight"] = &ActionContext::new_rpg_discover_flight;' in action_context
assert 'creators["new rpg discover flight"] = &TriggerContext::discover_flight;' in trigger_context
assert ('new TriggerNode("new rpg discover flight", {NextAction("new rpg discover flight", ACTION_NORMAL + 1)})'
        in rpg_strategy)
assert 'GetOption<bool>("Playerbots.DiscoverFlightMasters", false)' in config
assert '\nPlayerbots.DiscoverFlightMasters = 0\n' in conf_dist
# Rut'theran's flight master is offered only where islands keep it apart from Teldrassil's canopy.
assert '(creatureTemplate->Entry != 3838 || sPlayerbotAIConfig.continentTravel)' in travel
# Following decides boarding, riding, leaving and waiting through the tested companion step, on world maps only,
# before the upstream ship handling, and does not wait for the formation distance to board or leave a car.
follow_bodies = {'execute': function(follow, 'bool FollowAction::Execute(Event /*event*/)'),
                 'useful': function(follow, 'bool FollowAction::isUseful()')}


def assert_follow(bodies):
    execute = bodies['execute']
    assert 'if (sPlayerbotAIConfig.continentTravel && map && !map->Instanceable())' in execute
    assert (execute.index('ContinentTravel::CompanionRide(bot, transport, point)')
            < execute.index('if (transport && transport->IsStaticTransport())\n            transport = nullptr;'))
    # The core's follow movement paths after the master on foot and would walk the bot off its car.
    hold = execute[execute.index('case ContinentTravel::Ride::Hold:'):execute.index('case ContinentTravel::Ride::Follow:')]
    assert 'if (bot->GetMotionMaster()->GetCurrentMovementGeneratorType() == FOLLOW_MOTION_TYPE)' in hold
    assert 'bot->GetMotionMaster()->Clear(true);' in hold and 'bot->GetMotionMaster()->MoveIdle();' in hold
    assert 'bot->StopMovingOnCurrentPos();\n                    return true;' in hold
    assert ('if ((carrier && carrier->IsStaticTransport()) || (ride && ride->IsStaticTransport()))\n            return true;'
            in bodies['useful'])


assert_follow(follow_bodies)
for label, name, old, new in [
    ('follow movement kept while riding', 'execute', 'bot->GetMotionMaster()->Clear(true);', ''),
    ('riding together left to the formation distance', 'useful',
     'if ((carrier && carrier->IsStaticTransport())', 'if (carrier != ride && ((carrier && carrier->IsStaticTransport())'),
]:
    mutated = {**follow_bodies, name: follow_bodies[name].replace(old, new)}
    assert mutated[name] != follow_bodies[name], label
    try:
        assert_follow(mutated)
    except (AssertionError, ValueError):
        print(f'Continent route static mutation rejected: {label}')
    else:
        raise SystemExit(f'Continent route static check did not reject: {label}')
# The transport check takes a companion aboard the car its master stands on.
assert ('if (Transport* carrier = master->GetTransport(); carrier && carrier->IsStaticTransport())\n'
        '                    lift = carrier->GetEntry();' in function(ai, 'void PlayerbotAI::UpdateAI(uint32 elapsed, bool minimal)'))
# Bots stand on a lift the core cannot pick out when a door or another lift is nearer.
assert ('if (sPlayerbotAIConfig.continentTravel && (!newTransport || !newTransport->ToMotionTransport()))'
        in function(ai, 'void PlayerbotAI::UpdateAI(uint32 elapsed, bool minimal)'))
# A transport's map transfer acknowledges a far teleport and resets RPG status while its route survives.
teleport_ack = function(ai, 'void PlayerbotAI::HandleTeleportAck()')
assert 'if (bot->IsBeingTeleportedFar())' in teleport_ack and 'Reset(true);' in teleport_ack
reset_ai = function(ai, 'void PlayerbotAI::Reset(bool full)')
assert 'rpgInfo = NewRpgInfo();' in reset_ai and 'continentRoute' not in reset_ai

state_declaration = function(routes_header, 'struct ContinentRouteState') + ';'
catalog_declaration = function(routes_header, 'class ContinentRouteCatalog') + ';'
travel_declaration = function(routes_header, 'namespace ContinentTravel')
constants = '\n'.join(line for line in routes.splitlines()
                      if re.match(r'constexpr (uint32|float) (ITEM_HEARTHSTONE|SPELL_HEARTHSTONE|SameMapPortal)', line))
assert constants.count('constexpr') == 3
assert 'ITEM_HEARTHSTONE = 6948;' in constants and 'SPELL_HEARTHSTONE = 8690;' in constants
hearthstone = re.search(r"^\(6948,.*$", read(core / 'data/sql/base/db_world/item_template.sql'), re.MULTILINE)
assert hearthstone and "'Hearthstone'" in hearthstone[0] and ',8690,' in hearthstone[0].replace(' ', '')

deck_constants = '\n'.join(line for line in routes.splitlines()
                           if re.match(r'constexpr float (DeckProbeStep|DeckHeightTolerance) = ', line))
assert deck_constants.count('constexpr') == 2
animation_types = '\n'.join([
    function(dbc_structure, 'struct TransportAnimationEntry') + ';',
    function(dbc_structure, 'struct TransportRotationEntry') + ';',
    *re.findall(r'^typedef std::map<uint32, Transport(?:Animation|Rotation)Entry const\*> \w+;$', transport_mgr_header,
                re.MULTILINE),
    function(transport_mgr_header, 'struct TransportAnimation') + ';',
])
assert animation_types.count('typedef') == 2

production = {
    'policy': policy,
    'routes': '\n'.join([
        'namespace {', constants,
        function(routes, 'uint32 ZoneOf(uint32 areaId)'),
        function(routes, 'uint32 AreaTeam(uint32 areaId)'),
        function(routes, 'uint32 AreaAt(Point const& point)'),
        function(routes, 'bool IsWorldMap(uint32 mapId)'),
        function(routes, 'uint64 IslandCell(uint32 mapId, int32 cellX, int32 cellY)'),
        function(routes, 'bool TeleportDestination(uint32 spellId, Point& to, bool triggered = false)'),
        function(routes, 'bool HasReagents(Player* bot, SpellInfo const* info)'),
        function(routes, 'bool Open(ContinentRouteState const& state, Link const& link)'),
        '}',
        function(routes, 'void ContinentRouteState::Start(WorldPosition const& target, bool master)'),
        function(routes, 'void ContinentRouteState::Finish()'),
        function(routes, 'void ContinentRouteState::ClearLink()'),
        function(routes, 'void ContinentRouteState::ClearFlight()'),
        function(routes, 'uint64 ContinentRouteCatalog::Key(Link const& link)'),
        function(routes, 'void ContinentRouteCatalog::Add(Link const& added, bool alliance, bool horde)'),
        function(routes, 'void ContinentRouteCatalog::LoadTravelNodes(TravelNodeData& data)'),
        function(routes, 'void ContinentRouteCatalog::Build()'),
        function(routes, 'uint32 ContinentRouteCatalog::IslandAt(uint32 mapId, float x, float y, float z) const'),
        function(routes, 'Point ContinentRouteCatalog::Locate(WorldPosition const& position) const'),
        function(routes, 'bool ContinentRouteCatalog::CanArrive(Player* bot, Point const& to, uint32 arrivalZone)'),
        function(routes, 'std::vector<Link> ContinentRouteCatalog::UsableLinks(Player* bot, ContinentRouteState const& state) const'),
        'namespace ContinentTravel {',
        function(routes, 'Point ToPoint(WorldPosition const& position)'),
        function(routes, 'bool IsDocked(MotionTransport const* transport, Point const* stop)'),
        function(routes, 'bool OnTransport(GameObject const* transport, uint32 phaseMask, float x, float y, float z)'),
        function(routes, 'GameObject* NearestTransport(Player* bot, uint32 entry, float range)'),
        function(routes, 'Transport* LiftUnder(Player* bot, uint32 entry)'),
        'namespace {', deck_constants, function(routes, 'std::vector<WorldPosition> DryGround('), '}',
        function(routes, 'bool HoldsStill(Transport const* transport, uint32 ms)'),
        function(routes, 'bool FindBoardingPoint(Player* bot, Transport* transport, WorldPosition& point)'),
        function(routes, 'bool FindLandingPoint(Player* bot, Transport* transport, WorldPosition& point)'),
        function(routes, 'Ride CompanionRide(Player* bot, Transport* carrier, WorldPosition& point)'),
        '}',
    ]),
    'animation': function(transport_mgr, 'bool TransportAnimation::GetAnimNode('),
    'progression': '\n'.join([
        'namespace {', starting_zone, '}',
        function(progression, 'bool ContinentRouteProgression::CanArrive(Player* bot, uint32 mapId, float x, float y, '
                              'float z, uint32 zoneId)'),
    ]),
    'flight': '\n'.join([
        function(travel, 'bool TravelMgr::FindFlightTowards(Player* bot, WorldPosition const& target, '
                         'FlightMasterInfo const*& origin,'),
        function(travel, 'TravelMgr::FlightMasterInfo const* TravelMgr::GetNearestFlightMasterInfo(Player* bot) const'),
    ]),
    'discover': '\n'.join([
        function(travel, 'TravelMgr::FlightMasterInfo const* TravelMgr::FindUndiscoveredFlightMaster('),
        function(rpg, 'bool NewRpgDiscoverFlightAction::Execute(Event /*event*/)'),
        function(rpg_trigger, 'bool NewRpgDiscoverFlightTrigger::IsActive()'),
        interaction,
    ]),
    'taxi': function(ai, 'bool CanUseTaxiNodes(Player* player, std::vector<uint32> const& nodes)'),
    'trigger': function(triggers, 'bool MasterFarAwayTrigger::IsActive()'),
    'start': function(rpg, 'bool NewRpgStatusUpdateAction::StartContinentTravel()'),
}

fixture = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

using uint8 = std::uint8_t; using uint16 = std::uint16_t; using uint32 = std::uint32_t; using uint64 = std::uint64_t;
using int32 = std::int32_t; using int16 = std::int16_t;
template <class... Arguments> inline void LogSink(Arguments const&...) {}
#define LOG_INFO(...) LogSink(__VA_ARGS__)
#define LOG_DEBUG(...) LogSink(__VA_ARGS__)
constexpr uint32 MINUTE = 60, HOUR = 3600, IN_MILLISECONDS = 1000, PHASEMASK_NORMAL = 1;
enum ProgressionState : uint8 {};
using ObjectGuid = uint64;
NATIVES
PATH_TYPES

inline uint32 nowMs = 100000000;
inline uint32 getMSTime() { return nowMs; }
inline uint32 GetMSTimeDiffToNow(uint32 old) { return nowMs - old; }

class Player;
struct WorldPosition
{
    uint32 mapId = 0;
    float x = 0.0f, y = 0.0f, z = 0.0f;
    WorldPosition() = default;
    WorldPosition(uint32 map, float x, float y, float z = 0.0f) : mapId(map), x(x), y(y), z(z) {}
    explicit WorldPosition(Player const* player);
    uint32 GetMapId() const { return mapId; }
    float GetPositionX() const { return x; }
    float GetPositionY() const { return y; }
    float GetPositionZ() const { return z; }
    float GetExactDist(WorldPosition const& other) const
    { return std::sqrt((x - other.x) * (x - other.x) + (y - other.y) * (y - other.y) + (z - other.z) * (z - other.z)); }
    float GetExactDist2dSq(WorldPosition const& other) const
    { return (x - other.x) * (x - other.x) + (y - other.y) * (y - other.y); }
    bool operator==(WorldPosition const& other) const
    { return mapId == other.mapId && x == other.x && y == other.y && z == other.z; }
    bool operator!=(WorldPosition const& other) const { return !(*this == other); }
};

enum TeamId { TEAM_ALLIANCE = 0, TEAM_HORDE = 1, TEAM_NEUTRAL = 2 };
enum SpellEffIndex : uint8 { EFFECT_0 = 0, EFFECT_1 = 1, EFFECT_2 = 2 };

template <class Entry>
struct Store
{
    std::map<uint32, Entry> rows;
    Entry const* LookupEntry(uint32 id) const
    {
        auto found = rows.find(id);
        return found == rows.end() ? nullptr : &found->second;
    }
};
struct MapEntry
{
    uint32 expansion = 0;
    uint32 map_type = MAP_COMMON;
    uint32 Expansion() const { return expansion; }
    bool IsWorldMap() const { return map_type == MAP_COMMON; }
};
struct AreaTableEntry { uint32 ID = 0; uint32 zone = 0; uint32 team = 0; };
struct FactionTemplateEntry { uint32 hostileMask = 0; };
inline Store<MapEntry> sMapStore;
inline Store<AreaTableEntry> sAreaTableStore;
inline Store<FactionTemplateEntry> sFactionTemplateStore;

namespace G3D
{
struct Vector3
{
    float x = 0.0f, y = 0.0f, z = 0.0f;
    Vector3() = default;
    Vector3(float x, float y, float z) : x(x), y(y), z(z) {}
    Vector3 operator-(Vector3 const& other) const { return {x - other.x, y - other.y, z - other.z}; }
    float squaredLength() const { return x * x + y * y + z * z; }
};
struct Quat {};
struct Ray
{
    Vector3 origin, direction;
    Ray(Vector3 const& origin, Vector3 const& direction) : origin(origin), direction(direction) {}
};
}  // namespace G3D
namespace VMAP { enum class ModelIgnoreFlags : uint32 { Nothing = 0 }; }

// A deck or platform: a horizontal top over a box, hit by rays cast straight down onto it.
struct GameObjectModel
{
    float minX = 0.0f, maxX = 0.0f, minY = 0.0f, maxY = 0.0f, top = 0.0f;
    bool intersectRay(G3D::Ray const& ray, float& maxDist, bool, uint32, VMAP::ModelIgnoreFlags) const
    {
        assert(ray.direction.z == -1.0f && ray.direction.x == 0.0f && ray.direction.y == 0.0f);
        float const drop = ray.origin.z - top;
        if (ray.origin.x < minX || ray.origin.x > maxX || ray.origin.y < minY || ray.origin.y > maxY || drop < 0.0f ||
            drop > maxDist)
            return false;
        maxDist = drop;
        return true;
    }
};

class Transport;
class MotionTransport;
class StaticTransport;
#define ASSERT(condition, ...) assert(condition)
ANIMATION_TYPES
struct GameObjectValue
{
    struct
    {
        uint32 PathProgress = 0;
        TransportAnimation const* AnimationInfo = nullptr;
    } Transport;
};
class GameObject
{
public:
    uint32 entry = 0;
    uint32 type = GAMEOBJECT_TYPE_TRANSPORT;
    uint32 mapId = 0;
    float x = 0.0f, y = 0.0f, z = 0.0f;
    GameObjectModel* m_model = nullptr;
    GameObjectValue goValue;
    uint32 state = GO_STATE_READY;
    virtual ~GameObject() = default;
    uint32 GetEntry() const { return entry; }
    float GetPositionX() const { return x; }
    float GetPositionY() const { return y; }
    float GetPositionZ() const { return z; }
    GameObjectValue const* GetGOValue() const { return &goValue; }
    uint32 GetGoState() const { return state; }
    bool IsStaticTransport() const { return type == GAMEOBJECT_TYPE_TRANSPORT; }
    StaticTransport const* ToStaticTransport() const;
    Transport* ToTransport();
};

// Areas by map and x coordinate; the base map answers for the whole continent.
class Map
{
public:
    uint32 id = 0;
    bool instanceable = false;
    std::map<int, uint32> areas;
    std::vector<Transport*> transports;
    float floor = 0.0f;  // flat dry ground under the whole map
    bool Instanceable() const { return instanceable; }
    float GetHeight(uint32 phase, float, float, float z, bool, float maxSearchDist) const
    {
        assert(phase == PHASEMASK_NORMAL);
        return z >= floor && z - floor <= maxSearchDist ? floor : INVALID_HEIGHT;
    }
    bool IsInWater(uint32, float, float, float, float) const { return false; }
    std::vector<Transport*> const& GetAllTransports() const { return transports; }
    uint32 GetAreaId(uint32 phase, float x, float, float) const
    {
        assert(phase == PHASEMASK_NORMAL);
        auto found = areas.find(int(std::lround(x)));
        return found == areas.end() ? 0 : found->second;
    }
};
struct MapMgr
{
    std::map<uint32, Map> maps;
    Map* CreateBaseMap(uint32 id) { Map& map = maps[id]; map.id = id; return &map; }
};
inline MapMgr mapMgr;
#define sMapMgr (&mapMgr)

struct TaxiPathNodeEntry { uint32 mapid = 0; float x = 0.0f, y = 0.0f, z = 0.0f; uint32 actionFlag = 0; };
struct KeyFrame
{
    TaxiPathNodeEntry const* Node = nullptr;
    uint32 ArriveTime = 0;
    uint32 DepartureTime = 0;
    bool IsStopFrame() const { return Node->actionFlag == 2; }
};
struct TransportTemplate { bool inInstance = false; uint32 pathTime = 0; std::vector<KeyFrame> keyFrames; };
struct TransportMgr
{
    std::map<uint32, TransportTemplate> templates;
    TransportTemplate const* GetTransportTemplate(uint32 entry) const
    {
        auto found = templates.find(entry);
        return found == templates.end() ? nullptr : &found->second;
    }
};
inline TransportMgr transportMgr;
#define sTransportMgr (&transportMgr)

class Transport : public GameObject
{
public:
    virtual MotionTransport* ToMotionTransport() { return nullptr; }
};
inline Transport* GameObject::ToTransport()
{
    return type == GAMEOBJECT_TYPE_MO_TRANSPORT || type == GAMEOBJECT_TYPE_TRANSPORT ? static_cast<Transport*>(this)
                                                                                     : nullptr;
}
// A lift or tram car that the core moves along its animation, cycling it or pausing at either end.
class StaticTransport : public Transport
{
public:
    uint32 pause = 0;
    uint32 GetPauseTime() const { return pause; }
    uint32 GetPeriod() const
    {
        return goValue.Transport.AnimationInfo ? goValue.Transport.AnimationInfo->TotalTime : GetPauseTime() + 2;
    }
    uint32 GetPathProgress() const { return goValue.Transport.PathProgress; }
};
inline StaticTransport const* GameObject::ToStaticTransport() const
{
    return type == GAMEOBJECT_TYPE_TRANSPORT ? dynamic_cast<StaticTransport const*>(this) : nullptr;
}
class MotionTransport : public Transport
{
public:
    MotionTransport() { type = GAMEOBJECT_TYPE_MO_TRANSPORT; }
    MotionTransport* ToMotionTransport() override { return this; }
    TransportTemplate const* path = nullptr;
    uint32 progress = 0;
    uint32 GetPeriod() const { return path->pathTime; }
    uint32 GetPathProgress() const { return progress; }
    std::vector<KeyFrame> const& GetKeyFrames() const { return path->keyFrames; }
};

struct GameObjectTemplate
{
    uint32 type = 0;
    struct { uint32 spellId = 0; } spellcaster, goober;
};
struct GameObjectTemplateAddon { uint32 faction = 0; };
struct GameObjectData { uint32 id = 0; uint16 mapid = 0; uint32 phaseMask = 1; float posX = 0, posY = 0, posZ = 0; };
struct AreaTrigger { uint32 map = 0; float x = 0, y = 0, z = 0; };
struct AreaTriggerTeleport { uint32 target_mapId = 0; float target_X = 0, target_Y = 0, target_Z = 0; };
struct ObjectMgr
{
    std::unordered_map<uint32, GameObjectTemplate> templates;
    std::map<uint32, GameObjectTemplateAddon> addons;
    std::map<uint32, GameObjectData> spawns;
    std::map<uint32, AreaTrigger> triggers;
    std::map<uint32, AreaTriggerTeleport> teleports;
    std::unordered_map<uint32, GameObjectTemplate> const* GetGameObjectTemplates() const { return &templates; }
    std::map<uint32, GameObjectData> const& GetAllGOData() const { return spawns; }
    template <class T> static T const* Find(std::map<uint32, T> const& rows, uint32 id)
    {
        auto found = rows.find(id);
        return found == rows.end() ? nullptr : &found->second;
    }
    GameObjectTemplate const* GetGameObjectTemplate(uint32 id) const
    {
        auto found = templates.find(id);
        return found == templates.end() ? nullptr : &found->second;
    }
    GameObjectTemplateAddon const* GetGameObjectTemplateAddon(uint32 id) const { return Find(addons, id); }
    AreaTrigger const* GetAreaTrigger(uint32 id) const { return Find(triggers, id); }
    AreaTriggerTeleport const* GetAreaTriggerTeleport(uint32 id) const { return Find(teleports, id); }
};
inline ObjectMgr objectMgr;
#define sObjectMgr (&objectMgr)

struct SpellEffectInfo { uint32 Effect = 0; uint32 TriggerSpell = 0; };
struct SpellInfo
{
    uint32 SpellFamilyName = 0;
    std::array<SpellEffectInfo, MAX_SPELL_EFFECTS> Effects{};
    std::array<int32, MAX_SPELL_REAGENTS> Reagent{};
    std::array<uint32, MAX_SPELL_REAGENTS> ReagentCount{};
    bool passive = false;
    bool IsPassive() const { return passive; }
};
struct SpellTargetPosition { uint32 target_mapId; float target_X, target_Y, target_Z, target_Orientation; };
using SkillLineAbilityMap = std::multimap<uint32, int>;
using SkillLineAbilityMapBounds = std::pair<SkillLineAbilityMap::const_iterator, SkillLineAbilityMap::const_iterator>;
struct SpellMgr
{
    std::map<uint32, SpellInfo> infos;
    std::map<std::pair<uint32, uint8>, SpellTargetPosition> targets;
    SkillLineAbilityMap abilities;
    uint32 GetSpellInfoStoreSize() const { return infos.empty() ? 0 : infos.rbegin()->first + 1; }
    SpellInfo const* GetSpellInfo(uint32 id) const
    {
        auto found = infos.find(id);
        return found == infos.end() ? nullptr : &found->second;
    }
    SpellTargetPosition const* GetSpellTargetPosition(uint32 id, SpellEffIndex effect) const
    {
        auto found = targets.find({id, uint8(effect)});
        return found == targets.end() ? nullptr : &found->second;
    }
    SkillLineAbilityMapBounds GetSkillLineAbilityMapBounds(uint32 id) const { return abilities.equal_range(id); }
};
inline SpellMgr spellMgr;
#define sSpellMgr (&spellMgr)

struct PlayerTaxi
{
    std::set<uint32> known;
    bool IsTaximaskNodeKnown(uint32 node) const { return known.contains(node); }
};
constexpr uint32 UNIT_NPC_FLAG_FLIGHTMASTER = 0x2000;
constexpr uint32 CREATURE_TYPE_FLAG_VISIBLE_TO_GHOSTS = 1, CREATURE_TYPE_FLAG_INTERACT_WHILE_DEAD = 2;
constexpr int REP_UNFRIENDLY = 2;
enum NPCFlags : uint32 {};
struct CreatureTemplate { uint32 type_flags = 0; };
class Creature
{
public:
    ObjectGuid guid = 0;
    uint32 entry = 0;
    uint32 mapId = 0;
    float x = 0.0f, y = 0.0f, z = 0.0f;
    uint32 node = 0;  // the taxi node nearest the creature for its faction
    bool alive = true;
    int reaction = 4;
    uint32 flags = UNIT_NPC_FLAG_FLIGHTMASTER;
    ObjectGuid charmer = 0;
    CreatureTemplate creatureTemplate;
    ObjectGuid GetGUID() const { return guid; }
    bool IsAlive() const { return alive; }
    CreatureTemplate const* GetCreatureTemplate() const { return &creatureTemplate; }
    bool HasNpcFlag(NPCFlags flag) const { return (flags & flag) == flag; }
    ObjectGuid GetCharmerGUID() const { return charmer; }
    int GetReactionTo(Player const*) const { return reaction; }
    bool IsWithinDistInMap(Player const* player, float distance) const;
};
inline std::vector<Creature*> creatures;
inline std::vector<GameObject*> gameObjects;
class WorldSession
{
public:
    uint8 expansion = 2;
    Player* player = nullptr;
    uint8 Expansion() const { return expansion; }
    // The core learns the taxi node nearest the flight master for the player's team.
    bool SendLearnNewTaxiNode(Creature* unit);
};
class Player
{
public:
    uint32 mapId = 0;
    float x = 0.0f, y = 0.0f, z = 0.0f;
    TeamId team = TEAM_ALLIANCE;
    uint8 race = RACE_HUMAN;
    bool gm = false, alive = true, inWorld = true, inFlight = false, teleporting = false, selfBot = false;
    bool taxiCheater = false, noReagent = false, combat = false;
    uint32 zone = 0;
    Transport* transport = nullptr;
    Map* map = nullptr;
    WorldSession session;
    PlayerTaxi m_taxi;
    std::set<uint32> spells, cooldowns;
    std::map<uint32, uint32> items;
    Player() { session.player = this; }
    Player(Player const&) = delete;
    uint32 m_homebindMapId = 0, m_homebindAreaId = 0;
    float m_homebindX = 0.0f, m_homebindY = 0.0f, m_homebindZ = 0.0f;
    TeamId GetTeamId(bool = false) const { return team; }
    uint8 getRace() const { return race; }
    bool IsGameMaster() const { return gm; }
    WorldSession* GetSession() { return &session; }
    bool HasSpell(uint32 id) const { return spells.contains(id); }
    bool HasSpellCooldown(uint32 id) const { return cooldowns.contains(id); }
    bool HasItemCount(uint32 item, uint32 count = 1) const
    {
        auto found = items.find(item);
        return found != items.end() && found->second >= count;
    }
    bool CanNoReagentCast(SpellInfo const*) const { return noReagent; }
    bool isTaxiCheater() const { return taxiCheater; }
    bool IsAlive() const { return alive; }
    bool IsInWorld() const { return inWorld; }
    bool IsInFlight() const { return inFlight; }
    bool IsBeingTeleported() const { return teleporting; }
    Transport* GetTransport() const { return transport; }
    Map* GetMap() const { return map; }
    uint32 GetMapId() const { return mapId; }
    uint32 GetZoneId() const { return zone; }
    uint32 GetPhaseMask() const { return PHASEMASK_NORMAL; }
    float GetPositionX() const { return x; }
    float GetPositionY() const { return y; }
    float GetPositionZ() const { return z; }
    bool IsInCombat() const { return combat; }
    float GetExactDist2d(Player const* other) const { return std::hypot(x - other->x, y - other->y); }
    float GetExactDist2d(GameObject const* other) const { return std::hypot(x - other->x, y - other->y); }
    float GetExactDist2dSq(WorldPosition const& at) const { return (x - at.x) * (x - at.x) + (y - at.y) * (y - at.y); }
    float GetDistance(WorldPosition const& at) const
    { return std::sqrt((x - at.x) * (x - at.x) + (y - at.y) * (y - at.y) + (z - at.z) * (z - at.z)); }
    float GetExactDist(WorldPosition const& at) const { return GetDistance(at); }
    float GetCollisionHeight() const { return 2.0f; }
    GameObject* FindNearestGameObject(uint32 entry, float range) const
    {
        GameObject* nearest = nullptr;
        for (GameObject* object : gameObjects)
            if (object->entry == entry && object->mapId == mapId &&
                std::hypot(object->x - x, object->y - y) <= range &&
                (!nearest || std::hypot(object->x - x, object->y - y) < std::hypot(nearest->x - x, nearest->y - y)))
                nearest = object;
        return nearest;
    }
    Creature* FindNearestCreature(uint32 entry, float range) const
    {
        for (Creature* creature : creatures)
            if (creature->entry == entry && creature->mapId == mapId &&
                std::sqrt((creature->x - x) * (creature->x - x) + (creature->y - y) * (creature->y - y) +
                          (creature->z - z) * (creature->z - z)) <= range)
                return creature;
        return nullptr;
    }
    Creature* GetNPCIfCanInteractWith(ObjectGuid const& guid, uint32 npcflagmask);
};
inline bool IsSelfBot(Player* player) { return player && player->selfBot; }
inline WorldPosition::WorldPosition(Player const* player) : mapId(player->mapId), x(player->x), y(player->y), z(player->z)
{
}
inline bool Creature::IsWithinDistInMap(Player const* player, float distance) const
{
    return player->mapId == mapId && std::sqrt((player->x - x) * (player->x - x) + (player->y - y) * (player->y - y) +
                                               (player->z - z) * (player->z - z)) <= distance;
}
namespace ObjectAccessor
{
inline Creature* GetCreatureOrPetOrVehicle(Player const& player, ObjectGuid guid)
{
    for (Creature* creature : creatures)
        if (creature->guid == guid && creature->mapId == player.mapId)
            return creature;
    return nullptr;
}
}  // namespace ObjectAccessor
inline bool WorldSession::SendLearnNewTaxiNode(Creature* unit)
{
    if (unit->node)
        player->m_taxi.known.insert(unit->node);
    return true;
}

// The playerbots database answers the travel node queries with the rows of these tables.
enum PlayerbotsDatabaseStatements { PLAYERBOTS_SEL_TRAVELNODE, PLAYERBOTS_SEL_TRAVELNODE_LINK };
struct Field
{
    double number = 0.0;
    template <class T> T Get() const { return static_cast<T>(number); }
};
struct ResultSet
{
    std::vector<std::vector<Field>> rows;
    std::size_t row = 0;
    Field* Fetch() { return rows[row].data(); }
    bool NextRow() { return ++row < rows.size(); }
};
using PreparedQueryResult = std::shared_ptr<ResultSet>;
struct PreparedStatement { PlayerbotsDatabaseStatements id; };
struct PlayerbotsDatabaseConnection
{
    std::vector<std::vector<Field>> nodes, links;
    PreparedStatement statements[2] = {{PLAYERBOTS_SEL_TRAVELNODE}, {PLAYERBOTS_SEL_TRAVELNODE_LINK}};
    PreparedStatement* GetPreparedStatement(PlayerbotsDatabaseStatements id) { return &statements[id]; }
    PreparedQueryResult Query(PreparedStatement* statement)
    {
        auto const& rows = statement->id == PLAYERBOTS_SEL_TRAVELNODE ? nodes : links;
        return rows.empty() ? nullptr : std::make_shared<ResultSet>(ResultSet{rows});
    }
};
inline PlayerbotsDatabaseConnection PlayerbotsDatabase;

struct IndividualProgression
{
    bool enabled = true;
    bool strictEarnedProgression = true;
    bool enterResult = true;
    mutable int enterCalls = 0;
    std::map<Player const*, uint8> stages;
    bool hasPassedProgression(Player* player, ProgressionState state) const
    {
        auto found = stages.find(player);
        return found != stages.end() && found->second >= uint8(state);
    }
    bool CanEnterMap(Player*, uint32, float, float, float) const { ++enterCalls; return enterResult; }
};
inline IndividualProgression individualProgression;
#define sIndividualProgression (&individualProgression)

struct PlayerbotAIConfig { bool continentTravel = true; bool naturalProgression = true; bool discoverFlightMasters = true; };
inline PlayerbotAIConfig sPlayerbotAIConfig;

#include "ContinentRoutePolicy.h"
using ContinentRoutes::Link;
using ContinentRoutes::LinkKind;
using ContinentRoutes::Point;

STATE_DECLARATION
CATALOG_DECLARATION
#define sContinentRoutes ContinentRouteCatalog::instance()
TRAVEL_DECLARATION

namespace ContinentRouteProgression
{
bool CanArrive(Player* bot, uint32 mapId, float x, float y, float z, uint32 zoneId);
}

bool CanUseTaxiNodes(Player* player, std::vector<uint32> const& nodes);

struct TravelNodeMap
{
    std::map<std::pair<uint32, uint32>, std::vector<uint32>> paths;
    std::vector<uint32> FindTaxiPath(uint32 from, uint32 to)
    {
        auto found = paths.find({from, to});
        return found == paths.end() ? std::vector<uint32>{} : found->second;
    }
};
inline TravelNodeMap sTravelNodeMap;
class TravelMgr
{
public:
    struct FlightMasterInfo
    {
        WorldPosition pos;
        uint32 zoneId;
        uint32 taxiNodeId;
        uint32 templateEntry;
        uint32 dbGuid;
        uint32 island = 0;
    };
    std::map<uint32, FlightMasterInfo> allianceFlightMasterCache;
    std::map<uint32, FlightMasterInfo> hordeFlightMasterCache;
    FlightMasterInfo const* GetNearestFlightMasterInfo(Player* bot) const;
    bool FindFlightTowards(Player* bot, WorldPosition const& target, FlightMasterInfo const*& origin,
                           std::vector<uint32>& path, WorldPosition& landing) const;
    FlightMasterInfo const* FindUndiscoveredFlightMaster(Player* bot,
                                                         std::unordered_map<uint32, uint32> const& rejectedAt) const;
};
inline TravelMgr travelMgr;
#define sTravelMgr travelMgr

struct NewRpgInfo
{
    int travelRoutes = 0;
    uint32 discoverFlightMaster = 0;
    uint32 discoverFlightMasterSince = 0;
    std::unordered_map<uint32, uint32> flightMasterRejectedAt;
    void ChangeToTravelRoute() { ++travelRoutes; }
};
struct Event {};
class PlayerbotAI
{
public:
    Player* master = nullptr;
    ContinentRouteState continentRoute;
    NewRpgInfo rpgInfo;
    Player* GetMaster() { return master; }
};
class MasterFarAwayTrigger
{
public:
    PlayerbotAI* botAI;
    Player* bot;
    bool IsActive();
};
class NewRpgStatusUpdateAction
{
public:
    NewRpgStatusUpdateAction(PlayerbotAI* ai, Player* player) : botAI(ai), bot(player) {}
    PlayerbotAI* botAI;
    Player* bot;
    bool hub = false;
    WorldPosition next;
    int selections = 0;
    bool HasTravelHubHere() { return hub; }
    WorldPosition SelectContinentDestination() { ++selections; return next; }
    bool StartContinentTravel();
};
class NewRpgDiscoverFlightAction
{
public:
    NewRpgDiscoverFlightAction(PlayerbotAI* ai, Player* player) : botAI(ai), bot(player) {}
    PlayerbotAI* botAI;
    Player* bot;
    std::vector<WorldPosition> moves;
    bool MoveFarTo(WorldPosition destination) { moves.push_back(destination); return true; }
    bool Execute(Event event);
};
class NewRpgDiscoverFlightTrigger
{
public:
    PlayerbotAI* botAI;
    Player* bot;
    bool IsActive();
};
'''
fixture = (fixture.replace('NATIVES', natives).replace('PATH_TYPES', path_types)
           .replace('ANIMATION_TYPES', animation_types)
           .replace('STATE_DECLARATION', state_declaration)
           .replace('CATALOG_DECLARATION', catalog_declaration).replace('TRAVEL_DECLARATION', travel_declaration))

tests = r'''
#include "Fixture.h"

namespace
{
using ContinentRoutes::Explore;
using ContinentRoutes::RouteTo;

Link Make(LinkKind kind, uint32 object, Point from, Point to, float seconds, bool anywhere = false)
{
    Link link;
    link.kind = kind;
    link.object = object;
    link.from = from;
    link.to = to;
    link.seconds = seconds;
    link.anywhere = anywhere;
    return link;
}

ContinentRoutes::Route Plan(std::vector<Link> const& links, Point start, Point goal, std::set<uint32> blocked = {})
{
    auto const search = Explore(links, start, [&](Link const& link) { return !blocked.contains(link.object); });
    return RouteTo(links, search, goal);
}

std::vector<uint32> Objects(std::vector<Link> const& links, ContinentRoutes::Route const& route)
{
    std::vector<uint32> objects;
    for (std::size_t index : route.links)
        objects.push_back(links[index].object);
    return objects;
}

bool Has(std::vector<Link> const& links, LinkKind kind, uint32 object, uint32 fromMap = ~0u)
{
    for (Link const& link : links)
        if (link.kind == kind && link.object == object && (fromMap == ~0u || link.from.map == fromMap))
            return true;
    return false;
}

std::size_t Count(std::vector<Link> const& links, LinkKind kind, uint32 object)
{
    return std::size_t(std::count_if(links.begin(), links.end(), [&](Link const& link)
                                     { return link.kind == kind && link.object == object; }));
}

TaxiPathNodeEntry stops[] = {
    {0, 10.0f, 0.0f, 0.0f, 2}, {0, 500.0f, 0.0f, 0.0f, 0}, {1, 20.0f, 0.0f, 0.0f, 2}, {1, 900.0f, 0.0f, 0.0f, 0},
    {1, 30.0f, 0.0f, 0.0f, 2}, {1, 40.0f, 0.0f, 0.0f, 2}, {1, 8690.0f, 0.0f, 0.0f, 2}, {1, 7500.0f, 0.0f, 0.0f, 0},
    {1, 6500.0f, 0.0f, 0.0f, 2}};

// Travel node rows as the playerbots tables hold them: id, name, map, x, y, z, linked.
void Node(double id, double map, double x, double y, double z)
{
    PlayerbotsDatabase.nodes.push_back({{id}, {0}, {map}, {x}, {y}, {z}, {1}});
}

// node, to node, type, object, distance, swim distance, extra cost, calculated.
void Path(double from, double to, double type, double object = 0, double extra = 0)
{
    PlayerbotsDatabase.links.push_back({{from}, {to}, {type}, {object}, {0}, {0}, {extra}, {1}});
}

// Kalimdor (1), Eastern Kingdoms (0), Outland (530), the Deeprun Tram (369); 609 is an instance.
void World()
{
    sMapStore.rows = {{0, {0, MAP_COMMON}}, {1, {0, MAP_COMMON}}, {530, {1, MAP_COMMON}}, {571, {2, MAP_COMMON}},
                      {369, {0, MAP_COMMON}}, {609, {2, MAP_INSTANCE}}};
    sAreaTableStore.rows = {{100, {100, 0, 0}}, {101, {101, 100, ContinentRoutes::AreaTeamHorde}},
                            {102, {102, 100, 0}}, {103, {103, 0, ContinentRoutes::AreaTeamAlliance}},
                            {104, {104, 103, 0}}, {200, {AREA_SILVERMOON_CITY, 0, 0}}, {201, {201, 0, 0}}};
    mapMgr.maps.clear();
    mapMgr.CreateBaseMap(0)->areas = {{10, 102}, {-9000, 104}, {-11900, 102}, {1800, 101}};
    mapMgr.CreateBaseMap(1)->areas = {{20, 101}, {1500, 101}, {9700, 104}};
    mapMgr.CreateBaseMap(530)->areas = {{10000, 200}, {-250, 201}, {-1800, 201}};
    sFactionTemplateStore.rows = {{1, {FACTION_MASK_HORDE}}, {2, {FACTION_MASK_ALLIANCE}}};

    transportMgr.templates.clear();
    // 0 -> 1 -> 0, with turning points between stops.
    transportMgr.templates[100] = {false, 240000,
                                   {{&stops[0], 0, 60000}, {&stops[1], 90000, 90000}, {&stops[2], 120000, 180000},
                                    {&stops[3], 210000, 210000}}};
    transportMgr.templates[101] = {false, 100000, {{&stops[4], 0, 10000}, {&stops[5], 50000, 60000}}};
    transportMgr.templates[102] = {true, 240000, {{&stops[0], 0, 60000}, {&stops[2], 120000, 180000}}};
    // Rut'theran -> Auberdine on one map.
    transportMgr.templates[103] = {false, 200000,
                                   {{&stops[6], 0, 30000}, {&stops[7], 60000, 60000}, {&stops[8], 90000, 120000}}};

    objectMgr = ObjectMgr();
    for (uint32 entry : {100u, 101u, 102u, 103u})
        objectMgr.templates[entry].type = GAMEOBJECT_TYPE_MO_TRANSPORT;
    for (uint32 entry : {4170u, 20651u, 9997u, 9998u, 176080u})
        objectMgr.templates[entry].type = GAMEOBJECT_TYPE_TRANSPORT;
    objectMgr.templates[12].type = GAMEOBJECT_TYPE_SPELLCASTER;
    objectMgr.templates[12].spellcaster.spellId = 506;
    objectMgr.templates[7].type = GAMEOBJECT_TYPE_SPELLCASTER;
    objectMgr.templates[7].spellcaster.spellId = 500;
    objectMgr.templates[8].type = GAMEOBJECT_TYPE_GOOBER;
    objectMgr.templates[8].goober.spellId = 501;
    objectMgr.templates[9].type = GAMEOBJECT_TYPE_SPELLCASTER;
    objectMgr.templates[9].spellcaster.spellId = 503;
    objectMgr.templates[10].type = GAMEOBJECT_TYPE_SPELLCASTER;
    objectMgr.templates[10].spellcaster.spellId = 504;
    objectMgr.templates[11].type = GAMEOBJECT_TYPE_SPELLCASTER;
    objectMgr.templates[11].spellcaster.spellId = 505;
    objectMgr.addons[7].faction = 1;  // hostile to the Horde
    objectMgr.spawns = {
        {1, {7, 530, 1, -1800.0f, 0.0f, 0.0f}},  // Shattrath-style portal to Stormwind, Alliance only
        {2, {8, 530, 1, 10000.0f, 0.0f, 0.0f}},  // orb: goober spell triggering the teleport
        {3, {9, 0, 1, 10.0f, 0.0f, 0.0f}},       // in-town teleport under 500 yards
        {4, {7, 609, 1, 0.0f, 0.0f, 0.0f}},      // spawned on a non-continent
        {5, {10, 0, 1, -9000.0f, 0.0f, 0.0f}},   // teleport into a non-continent
        {6, {11, 0, 1, -9000.0f, 0.0f, 0.0f}},   // same-map portal far enough to save a walk
        {7, {7, 530, 2, -1800.0f, 0.0f, 0.0f}},  // other phase only
        {20, {4170, 1, 1, -1286.0f, 190.0f, 130.0f}},  // Thunder Bluff elevator
        {21, {20651, 0, 1, 1596.0f, 302.0f, -41.0f}},  // Undercity elevator door
        {22, {176080, 369, 1, 5.0f, 2500.0f, 7.0f}},   // Deeprun Tram car
        {23, {12, 1, 1, 9820.0f, 0.0f, 1300.0f}},      // Darnassus portal down to Rut'theran
        {24, {9997, 1, 1, 5000.0f, 5000.0f, 0.0f}},    // a lift spawned far from its travel nodes
    };
    objectMgr.triggers = {{4354, {0, -11900.0f, 0.0f, 0.0f}}, {5, {0, 10.0f, 0.0f, 0.0f}},
                          {6, {0, 10.0f, 0.0f, 0.0f}}, {2173, {0, -8350.0f, 600.0f, 90.0f}},
                          {2175, {369, 5.0f, 20.0f, 7.0f}}};
    objectMgr.teleports = {{4354, {530, -250.0f, 0.0f, 0.0f}}, {5, {0, 3000.0f, 0.0f, 0.0f}},
                           {6, {609, 0.0f, 0.0f, 0.0f}}, {7, {1, 0.0f, 0.0f, 0.0f}},
                           {2173, {369, 5.0f, 2520.0f, 7.0f}}, {2175, {0, -4790.0f, -1000.0f, 500.0f}}};

    spellMgr = SpellMgr();
    spellMgr.infos[500].Effects[0].Effect = SPELL_EFFECT_TELEPORT_UNITS;
    spellMgr.targets[{500, 0}] = {0, 10.0f, 0.0f, 0.0f, 0.0f};
    spellMgr.infos[501].Effects[1].Effect = SPELL_EFFECT_TRIGGER_SPELL;
    spellMgr.infos[501].Effects[1].TriggerSpell = 502;
    spellMgr.infos[502].Effects[0].Effect = SPELL_EFFECT_TELEPORT_UNITS;
    spellMgr.targets[{502, 0}] = {0, 1800.0f, 0.0f, 0.0f, 0.0f};
    spellMgr.infos[503].Effects[0].Effect = SPELL_EFFECT_TELEPORT_UNITS;
    spellMgr.targets[{503, 0}] = {0, 300.0f, 0.0f, 0.0f, 0.0f};
    spellMgr.infos[504].Effects[0].Effect = SPELL_EFFECT_TELEPORT_UNITS;
    spellMgr.targets[{504, 0}] = {609, 0.0f, 0.0f, 0.0f, 0.0f};
    spellMgr.infos[505].Effects[0].Effect = SPELL_EFFECT_TELEPORT_UNITS;
    spellMgr.targets[{505, 0}] = {0, -11900.0f, 0.0f, 0.0f, 0.0f};
    // Trainer teleports: a mage spell with a skill line, and three that are not learnable teleports.
    for (uint32 id : {600u, 601u, 602u, 603u})
    {
        spellMgr.infos[id].SpellFamilyName = id == 601 ? SPELLFAMILY_GENERIC : SPELLFAMILY_MAGE;
        spellMgr.infos[id].Effects[0].Effect = SPELL_EFFECT_TELEPORT_UNITS;
        spellMgr.targets[{id, 0}] = {1, 1500.0f, 0.0f, 0.0f, 0.0f};
        if (id != 602)
            spellMgr.abilities.insert({id, 1});
    }
    spellMgr.infos[603].passive = true;
    spellMgr.infos[600].Reagent[0] = 17031;
    spellMgr.infos[600].ReagentCount[0] = 1;
    spellMgr.infos[506].Effects[0].Effect = SPELL_EFFECT_TELEPORT_UNITS;
    spellMgr.targets[{506, 0}] = {1, 8705.0f, 0.0f, 5.0f, 0.0f};

    // Islands: Teldrassil's canopy, Rut'theran below it, Kalimdor with Mulgore, Thunder Bluff's mesa,
    // the two ends of the Deeprun Tram, and the Eastern Kingdoms from Stormwind to Ironforge.
    PlayerbotsDatabase = PlayerbotsDatabaseConnection();
    uint32 const walk = uint32(TravelNodePathType::walk), lift = uint32(TravelNodePathType::transport);
    Node(101, 1, 9800, 0, 1300), Node(102, 1, 9850, 0, 1300), Path(101, 102, walk);
    Node(103, 1, 8700, 0, 5), Node(104, 1, 8710, 0, 5), Path(103, 104, walk);
    Node(105, 1, 6510, 0, 0), Node(106, 1, 1500, 0, 0), Node(107, 1, 20, 0, 0);
    Path(105, 106, walk), Path(106, 107, walk);
    Node(110, 1, -1286, 190, 69), Node(111, 1, -1300, 200, 69), Path(110, 111, walk), Path(111, 106, walk);
    Node(112, 1, -1286, 190, 130), Node(113, 1, -1250, 190, 130), Path(112, 113, walk);
    Node(120, 369, 5, 2510, 7), Node(121, 369, 5, 28, 7);
    Node(130, 0, -8340, 600, 90), Node(131, 0, -4800, -1000, 500), Path(130, 131, walk);
    Node(140, 609, 0, 0, 0), Node(141, 0, 1596, 302, -41), Node(142, 0, 1596, 302, -33);
    Path(110, 112, lift, 4170, 15), Path(112, 110, lift, 4170, 5);
    Path(120, 121, lift, 176080, 72), Path(121, 120, lift, 176080, 72);
    Path(141, 142, lift, 20651, 10);                         // an elevator door, not a ride
    Path(110, 112, lift, 9998, 15);                          // a lift without a spawn
    Path(110, 112, lift, 9997, 15);                          // a lift spawned elsewhere
    Path(110, 112, lift, 100, 15);                           // a ship's entry is no lift
    Path(130, 120, lift, 176080, 15);                        // between maps, though spawned at one stop
    Path(110, 112, uint32(TravelNodePathType::portal), 4170, 15);  // another kind of travel link

    individualProgression = IndividualProgression();
    sPlayerbotAIConfig = PlayerbotAIConfig();
}
}  // namespace

int main()
{
    Point const kalimdorDock{1, 0.0f, 0.0f, 0.0f}, kingdomsGoal{0, 3000.0f, 0.0f, 0.0f};

    // The planner takes the cheaper link across maps and never walks between maps.
    {
        std::vector<Link> links = {Make(LinkKind::Transport, 1, {1, 100.0f, 0.0f, 0.0f}, {0, 2900.0f, 0.0f, 0.0f}, 300.0f),
                                   Make(LinkKind::Portal, 2, {1, 2000.0f, 0.0f, 0.0f}, {0, 3000.0f, 0.0f, 0.0f}, 5.0f)};
        auto route = Plan(links, kalimdorDock, kingdomsGoal);
        assert(route.Found() && Objects(links, route) == std::vector<uint32>{1});
        route = Plan(links, {1, 1900.0f, 0.0f, 0.0f}, kingdomsGoal);
        assert(Objects(links, route) == std::vector<uint32>{2});
        assert(!Plan(links, kalimdorDock, kingdomsGoal, {1, 2}).Found());
        assert(!Plan({}, kalimdorDock, kingdomsGoal).Found());
    }
    // Legs chain across maps; a same-map portal is used only when it saves the walk.
    {
        std::vector<Link> links = {Make(LinkKind::Transport, 1, {1, 0.0f, 0.0f, 0.0f}, {0, 0.0f, 0.0f, 0.0f}, 200.0f),
                                   Make(LinkKind::Portal, 2, {0, 100.0f, 0.0f, 0.0f}, {0, 5000.0f, 0.0f, 0.0f}, 5.0f),
                                   Make(LinkKind::AreaTrigger, 3, {0, 5100.0f, 0.0f, 0.0f}, {530, 0.0f, 0.0f, 0.0f}, 5.0f)};
        auto route = Plan(links, {1, 10.0f, 0.0f, 0.0f}, {530, 100.0f, 0.0f, 0.0f});
        assert((Objects(links, route) == std::vector<uint32>{1, 2, 3}));
        route = Plan(links, {0, 0.0f, 0.0f, 0.0f}, {0, 5200.0f, 0.0f, 0.0f});
        assert((Objects(links, route) == std::vector<uint32>{2}));
        route = Plan(links, {0, 0.0f, 0.0f, 0.0f}, {0, 300.0f, 0.0f, 0.0f});
        assert(route.Found() && route.links.empty());
    }
    // Own teleports are spent only when they save more than their reagent or cooldown penalty.
    {
        Link spell = Make(LinkKind::Spell, 9, {}, {0, 0.0f, 0.0f, 0.0f},
                          ContinentRoutes::CastSeconds + ContinentRoutes::SpellPenaltySeconds, true);
        std::vector<Link> links = {spell};
        auto route = Plan(links, {0, 300.0f, 0.0f, 0.0f}, {0, 20.0f, 0.0f, 0.0f});
        assert(route.Found() && route.links.empty());
        route = Plan(links, {1, 300.0f, 0.0f, 0.0f}, {0, 20.0f, 0.0f, 0.0f});
        assert((Objects(links, route) == std::vector<uint32>{9}));
        route = Plan(links, {0, 3000.0f, 0.0f, 0.0f}, {0, 20.0f, 0.0f, 0.0f});
        assert((Objects(links, route) == std::vector<uint32>{9}));
    }
    // Waits, territory and flight savings.
    assert(std::fabs(ContinentRoutes::TransportSeconds(60000, 120000, 240000) - 180.0f) < 0.01f);
    assert(std::fabs(ContinentRoutes::TransportSeconds(180000, 0, 240000) - 180.0f) < 0.01f);
    assert(std::fabs(ContinentRoutes::TransportSeconds(200000, 20000, 240000) - 180.0f) < 0.01f);
    assert(!std::isfinite(ContinentRoutes::TransportSeconds(0, 0, 0)));
    assert(ContinentRoutes::TeamMayUse(0, 0, true) && ContinentRoutes::TeamMayUse(0, 0, false));
    assert(ContinentRoutes::TeamMayUse(ContinentRoutes::AreaTeamAlliance, 0, true));
    assert(!ContinentRoutes::TeamMayUse(ContinentRoutes::AreaTeamAlliance, 0, false));
    assert(!ContinentRoutes::TeamMayUse(0, ContinentRoutes::AreaTeamHorde, true));
    assert(ContinentRoutes::TeamMayUse(0, ContinentRoutes::AreaTeamHorde, false));
    assert(!ContinentRoutes::FlightSaves(500.0f, 0.0f, 400.0f, 0.0f));
    assert(ContinentRoutes::FlightSaves(3000.0f, 50.0f, 2800.0f, 50.0f));
    assert(!ContinentRoutes::FlightSaves(3000.0f, 2500.0f, 2800.0f, 50.0f));
    assert(!ContinentRoutes::FlightSaves(std::numeric_limits<float>::quiet_NaN(), 0.0f, 0.0f, 0.0f));
    {
        std::vector<float> seconds = {100.0f, 180.0f, 300.0f, std::numeric_limits<float>::infinity()};
        assert((ContinentRoutes::NearBest(seconds) == std::vector<std::size_t>{0, 1}));
        std::vector<float> none = {std::numeric_limits<float>::infinity()};
        assert(ContinentRoutes::NearBest(none).empty() && ContinentRoutes::NearBest({}).empty());
    }

    // Individual Progression's arrival gate without database reads.
    {
        World();
        Player human, elf, draenei;
        elf.race = RACE_BLOODELF;
        draenei.race = RACE_DRAENEI;
        auto arrive = [](Player& bot, uint32 map, uint32 zone)
        { return ContinentRouteProgression::CanArrive(&bot, map, 0.0f, 0.0f, 0.0f, zone); };
        // Without earned TBC: only the TBC races, and only into their starting zones.
        assert(!arrive(human, 530, AREA_SILVERMOON_CITY) && !arrive(human, 530, 3483));
        assert(arrive(elf, 530, AREA_SILVERMOON_CITY) && arrive(elf, 530, AREA_GHOSTLANDS));
        assert(arrive(draenei, 530, AREA_THE_EXODAR) && !arrive(elf, 530, 3483));
        assert(individualProgression.enterCalls == 0);
        // Strict mode with earned TBC: Individual Progression's own gate decides.
        individualProgression.stages[&human] = PROGRESSION_PRE_TBC;
        individualProgression.enterResult = false;
        assert(!arrive(human, 530, 3483) && individualProgression.enterCalls == 1);
        individualProgression.enterResult = true;
        assert(arrive(human, 530, 3483) && arrive(human, 571, 495) && individualProgression.enterCalls == 3);
        // Outside strict mode Northrend needs earned Wrath, without account lookups.
        individualProgression.strictEarnedProgression = false;
        assert(!arrive(human, 571, 495) && arrive(human, 1, 17) && arrive(human, 530, 3483));
        individualProgression.stages[&human] = PROGRESSION_TBC_TIER_5;
        assert(arrive(human, 571, 495) && individualProgression.enterCalls == 3);
        // The account's expansion, Game Masters and a disabled module.
        human.session.expansion = 0;
        assert(!arrive(human, 530, 3483) && arrive(human, 1, 17) && !arrive(human, 9999, 0));
        human.session.expansion = 2;
        Player gm;
        gm.gm = true;
        assert(arrive(gm, 530, 3483));
        individualProgression.enabled = false;
        assert(arrive(elf, 530, 3483));
    }

    // The catalog takes cross-map transports, continent portals and teleporting area triggers.
    {
        World();
        sContinentRoutes.Build();
        assert(sContinentRoutes.Built() && sContinentRoutes.Connects(0) && sContinentRoutes.Connects(1));
        assert(sContinentRoutes.Connects(530) && sContinentRoutes.Connects(369));
        assert(!sContinentRoutes.Connects(609) && !sContinentRoutes.Connects(571));

        Player horde;
        horde.team = TEAM_HORDE;
        horde.race = RACE_BLOODELF;
        individualProgression.stages[&horde] = PROGRESSION_TBC_TIER_5;
        ContinentRouteState state;
        std::vector<Link> links = sContinentRoutes.UsableLinks(&horde, state);
        // The ship docks at a Horde dock in Kalimdor; both directions ride the same cycle.
        assert(Has(links, LinkKind::Transport, 100, 0) && Has(links, LinkKind::Transport, 100, 1));
        assert(Count(links, LinkKind::Transport, 101) == 2 && !Has(links, LinkKind::Transport, 102));
        for (Link const& link : links)
            if (link.kind == LinkKind::Transport && link.from.map == 0)
                assert(link.to.map == 1 && link.to.x == 20.0f && std::fabs(link.seconds - 180.0f) < 0.01f);
        // The orb's triggered teleport and the Dark Portal; no hostile portal or one from Alliance territory.
        assert(Has(links, LinkKind::Portal, 2) && !Has(links, LinkKind::Portal, 6));
        assert(!Has(links, LinkKind::Portal, 1) && !Has(links, LinkKind::Portal, 3) && !Has(links, LinkKind::Portal, 4));
        assert(!Has(links, LinkKind::Portal, 5) && !Has(links, LinkKind::Portal, 7));
        assert(Has(links, LinkKind::AreaTrigger, 4354) && !Has(links, LinkKind::AreaTrigger, 5));
        assert(!Has(links, LinkKind::AreaTrigger, 6) && !Has(links, LinkKind::AreaTrigger, 7));

        Player alliance;
        individualProgression.stages[&alliance] = PROGRESSION_TBC_TIER_5;
        links = sContinentRoutes.UsableLinks(&alliance, state);
        assert(!Has(links, LinkKind::Transport, 100) && Has(links, LinkKind::Portal, 1));
        assert(Has(links, LinkKind::Portal, 6) && !Has(links, LinkKind::Portal, 2) && !Has(links, LinkKind::Portal, 7));
        assert(Has(links, LinkKind::AreaTrigger, 4354));
        // A human without earned TBC may not enter Outland by any link.
        individualProgression.stages[&alliance] = 0;
        assert(!Has(sContinentRoutes.UsableLinks(&alliance, state), LinkKind::AreaTrigger, 4354));
        individualProgression.stages[&alliance] = PROGRESSION_TBC_TIER_5;

        // A failed link waits thirty minutes before the bot tries it again.
        Link portal;
        for (Link const& link : links)
            if (link.kind == LinkKind::Portal && link.object == 1)
                portal = link;
        state.failedAt[ContinentRouteCatalog::Key(portal)] = nowMs;
        assert(!Has(sContinentRoutes.UsableLinks(&alliance, state), LinkKind::Portal, 1));
        nowMs += ContinentTravel::LinkRetryMs - 1;
        assert(!Has(sContinentRoutes.UsableLinks(&alliance, state), LinkKind::Portal, 1));
        nowMs += 1;
        assert(Has(sContinentRoutes.UsableLinks(&alliance, state), LinkKind::Portal, 1));

        // Own teleports need the learned spell, no cooldown and the reagent, unless the bot may cast without.
        for (uint32 id : {600u, 601u, 602u, 603u})
            alliance.spells.insert(id);
        assert(!Has(sContinentRoutes.UsableLinks(&alliance, state), LinkKind::Spell, 600));
        alliance.items[17031] = 1;
        links = sContinentRoutes.UsableLinks(&alliance, state);
        assert(Has(links, LinkKind::Spell, 600));
        assert(!Has(links, LinkKind::Spell, 601) && !Has(links, LinkKind::Spell, 602) && !Has(links, LinkKind::Spell, 603));
        alliance.cooldowns.insert(600);
        assert(!Has(sContinentRoutes.UsableLinks(&alliance, state), LinkKind::Spell, 600));
        alliance.cooldowns.clear();
        alliance.items.erase(17031);
        alliance.noReagent = true;
        assert(Has(sContinentRoutes.UsableLinks(&alliance, state), LinkKind::Spell, 600));
        alliance.spells.clear();
        assert(!Has(sContinentRoutes.UsableLinks(&alliance, state), LinkKind::Spell, 600));

        // The hearthstone leads home while it is in the bags and off cooldown.
        alliance.m_homebindMapId = 0;
        alliance.m_homebindX = -9000.0f;
        alliance.m_homebindAreaId = 104;
        assert(!Has(sContinentRoutes.UsableLinks(&alliance, state), LinkKind::Hearthstone, 6948));
        alliance.items[6948] = 1;
        links = sContinentRoutes.UsableLinks(&alliance, state);
        assert(Has(links, LinkKind::Hearthstone, 6948));
        for (Link const& link : links)
            if (link.kind == LinkKind::Hearthstone)
                assert(link.anywhere && link.to.map == 0 && link.to.x == -9000.0f);
        alliance.cooldowns.insert(8690);
        assert(!Has(sContinentRoutes.UsableLinks(&alliance, state), LinkKind::Hearthstone, 6948));

        // A companion bound at its master's inn follows a far hearth with its own hearthstone, and walks a near one.
        alliance.cooldowns.clear();
        links = sContinentRoutes.UsableLinks(&alliance, state);
        Point const inn{0, -9000.0f, 0.0f, 0.0f};
        ContinentRoutes::Route const far = Plan(links, {0, -9000.0f + ContinentTravel::CompanionFarYards, 0.0f, 0.0f}, inn);
        assert(far.links.size() == 1 && links[far.links[0]].kind == LinkKind::Hearthstone);
        assert(Plan(links, {0, -8100.0f, 0.0f, 0.0f}, inn).links.empty());
        alliance.cooldowns.insert(8690);
        links = sContinentRoutes.UsableLinks(&alliance, state);
        assert(Plan(links, {0, -9000.0f + ContinentTravel::CompanionFarYards, 0.0f, 0.0f}, inn).links.empty());
    }

    // A transport counts as docked at a stop only while the core keeps it waiting there.
    {
        World();
        MotionTransport ship;
        ship.path = transportMgr.GetTransportTemplate(100);
        Point const eastern{0, 10.0f, 0.0f, 0.0f}, western{1, 20.0f, 0.0f, 0.0f};
        for (uint32 progress : {0u, 59999u, 240000u + 30000u})
        {
            ship.progress = progress;
            assert(ContinentTravel::IsDocked(&ship, &eastern) && !ContinentTravel::IsDocked(&ship, &western));
            assert(ContinentTravel::IsDocked(&ship, nullptr));
        }
        for (uint32 progress : {60000u, 90000u, 119999u, 180000u, 239999u})
        {
            ship.progress = progress;
            assert(!ContinentTravel::IsDocked(&ship, &eastern) && !ContinentTravel::IsDocked(&ship, nullptr));
        }
        ship.progress = 150000;
        assert(ContinentTravel::IsDocked(&ship, &western) && !ContinentTravel::IsDocked(&ship, &eastern));
    }

    // Flights towards a link use only discovered routes and land closest to the target.
    {
        World();
        sContinentRoutes.Build();
        TravelMgr travel;
        TravelMgr::FlightMasterInfo origin{{0, 0.0f, 0.0f}, 1, 10, 1, 1};
        travel.allianceFlightMasterCache = {{1, origin}, {2, {{0, 900.0f, 0.0f}, 2, 11, 2, 2}},
                                            {3, {{0, 950.0f, 0.0f}, 2, 12, 3, 3}}, {4, {{0, 990.0f, 0.0f}, 2, 14, 4, 4}},
                                            {5, {{1, 1000.0f, 0.0f}, 3, 15, 5, 5}}};
        sTravelNodeMap.paths = {{{10, 11}, {10, 11}}, {{10, 12}, {10, 12}}, {{10, 14}, {10, 13, 14}}, {{10, 15}, {10, 15}}};
        Player bot;
        TravelMgr::FlightMasterInfo const* from = nullptr;
        std::vector<uint32> path;
        WorldPosition landing;
        WorldPosition const target{0, 1000.0f, 0.0f};
        assert(!travel.FindFlightTowards(&bot, target, from, path, landing));
        bot.m_taxi.known = {11, 12, 14, 15};
        assert(travel.FindFlightTowards(&bot, target, from, path, landing));
        assert((path == std::vector<uint32>{10, 12} && landing.x == 950.0f && from->dbGuid == 1));
        bot.m_taxi.known.insert(13);
        assert(travel.FindFlightTowards(&bot, target, from, path, landing));
        assert((path == std::vector<uint32>{10, 13, 14} && landing.x == 990.0f));
        bot.mapId = 530;
        assert(!travel.FindFlightTowards(&bot, target, from, path, landing));

        // On Rut'theran the canopy's flight master is not the nearest one, nor a landing for a target there.
        uint32 const below = sContinentRoutes.IslandAt(1, 8700, 0, 5), canopy = sContinentRoutes.IslandAt(1, 9800, 0, 1300);
        travel.allianceFlightMasterCache = {{1, {{1, 8750.0f, 0.0f, 1300.0f}, 3, 30, 1, 1, canopy}},
                                            {2, {{1, 8800.0f, 0.0f, 5.0f}, 3, 31, 2, 2, below}},
                                            {3, {{1, 6600.0f, 0.0f, 0.0f}, 4, 32, 3, 3, sContinentRoutes.IslandAt(1, 6510, 0, 0)}},
                                            {4, {{1, 6530.0f, 0.0f, 1300.0f}, 4, 33, 4, 4, canopy}}};
        sTravelNodeMap.paths = {{{31, 32}, {31, 32}}, {{31, 33}, {31, 33}}, {{30, 33}, {30, 33}}};
        Player elf;
        elf.mapId = 1, elf.x = 8700.0f, elf.z = 5.0f;
        elf.m_taxi.known = {32, 33};
        assert(travel.GetNearestFlightMasterInfo(&elf)->dbGuid == 2);
        assert(travel.FindFlightTowards(&elf, WorldPosition(1, 6520.0f, 0.0f, 0.0f), from, path, landing));
        assert((from->dbGuid == 2 && path == std::vector<uint32>{31, 32} && landing.x == 6600.0f));
    }

    // Companions follow their master over links only to a connected map or far away.
    {
        World();
        sContinentRoutes.Build();
        Map kingdoms, kalimdor, instance;
        instance.instanceable = true;
        Player master, bot;
        master.map = &kalimdor;
        master.mapId = 1;
        bot.map = &kingdoms;
        PlayerbotAI ai;
        ai.master = &master;
        MasterFarAwayTrigger trigger{&ai, &bot};
        assert(trigger.IsActive());
        sPlayerbotAIConfig.continentTravel = false;
        assert(!trigger.IsActive());
        sPlayerbotAIConfig.continentTravel = true;
        bot.selfBot = true;
        assert(!trigger.IsActive());
        bot.selfBot = false;
        MotionTransport boat;
        master.transport = &boat;
        assert(!trigger.IsActive());
        master.transport = nullptr;
        master.inFlight = true;
        assert(!trigger.IsActive());
        master.inFlight = false;
        master.mapId = 609;
        assert(!trigger.IsActive());
        master.mapId = 571;
        assert(!trigger.IsActive());
        master.map = &instance;
        master.mapId = 1;
        assert(!trigger.IsActive());
        master.map = &kingdoms;
        master.mapId = 0;
        master.x = 100.0f;
        assert(!trigger.IsActive());
        master.x = ContinentTravel::CompanionFarYards + 1.0f;
        assert(trigger.IsActive());
        bot.map = &instance;
        assert(!trigger.IsActive());
        bot.map = &kingdoms;
        bot.alive = false;
        assert(!trigger.IsActive());
        // Below Teldrassil's canopy the master is near but out of walking reach.
        bot.alive = true, bot.map = &kalimdor, bot.mapId = 1, bot.x = 8700.0f, bot.z = 5.0f;
        master.map = &kalimdor, master.mapId = 1, master.x = 9805.0f, master.z = 1300.0f;
        assert(trigger.IsActive());
        master.x = 8705.0f, master.z = 5.0f;
        assert(!trigger.IsActive());
        // A bot on a lift or tram car steps off as it follows before a route of its own starts.
        master.x = 9805.0f, master.z = 1300.0f;
        assert(trigger.IsActive());
        StaticTransport car;
        bot.transport = &car;
        assert(!trigger.IsActive());
        ai.continentRoute.hasLink = true;
        ai.continentRoute.link.kind = LinkKind::Lift;
        assert(trigger.IsActive());
        ai.continentRoute.link.kind = LinkKind::Transport;
        assert(!trigger.IsActive());
        ai.continentRoute.hasLink = false;
        bot.transport = nullptr;
        ai.master = nullptr;
        bot.alive = true;
        assert(!trigger.IsActive());
    }

    // Random bots leave a map without an inn or camp for their level, and resume after map changes.
    {
        World();
        Player bot;
        PlayerbotAI ai;
        NewRpgStatusUpdateAction status{&ai, &bot};
        status.next = WorldPosition(1, 500.0f, 0.0f);
        status.hub = true;
        assert(!status.StartContinentTravel() && !ai.continentRoute.Active() && status.selections == 0);
        status.hub = false;
        sPlayerbotAIConfig.continentTravel = false;
        assert(!status.StartContinentTravel() && status.selections == 0);
        sPlayerbotAIConfig.continentTravel = true;
        assert(status.StartContinentTravel() && ai.rpgInfo.travelRoutes == 1);
        assert(ai.continentRoute.Active() && ai.continentRoute.destination == status.next && !ai.continentRoute.forMaster);
        // A far teleport resets the RPG status; the route resumes without a new choice.
        status.hub = true;
        assert(status.StartContinentTravel() && status.selections == 1 && ai.rpgInfo.travelRoutes == 2);
        // After a boat's map transfer, an idle bot must keep its route until it steps ashore.
        bot.mapId = 1;
        MotionTransport ship;
        bot.transport = &ship;
        WorldPosition const arrival = ai.continentRoute.destination;
        ai.rpgInfo = NewRpgInfo();
        assert(status.StartContinentTravel() && ai.rpgInfo.travelRoutes == 1);
        assert(ai.continentRoute.Active() && ai.continentRoute.destination == arrival && status.selections == 1);
        // The same arrival rule holds during a taxi flight, before ordinary ground choices can resume.
        bot.transport = nullptr;
        bot.inFlight = true;
        ai.rpgInfo = NewRpgInfo();
        assert(status.StartContinentTravel() && ai.rpgInfo.travelRoutes == 1);
        assert(ai.continentRoute.Active() && ai.continentRoute.destination == arrival && status.selections == 1);
        // Resuming an aboard route still respects the option and the existing time budget.
        sPlayerbotAIConfig.continentTravel = false;
        assert(!status.StartContinentTravel() && ai.continentRoute.Active() && ai.rpgInfo.travelRoutes == 1);
        sPlayerbotAIConfig.continentTravel = true;
        bot.inFlight = false;
        // Only after leaving the ride on the destination map does the route end.
        assert(!status.StartContinentTravel() && !ai.continentRoute.Active());
        // Routes end after their time budget.
        bot.mapId = 0;
        ai.continentRoute.Start(status.next, false);
        nowMs += ContinentTravel::RouteTimeoutMs;
        bot.transport = &ship;
        assert(!status.StartContinentTravel() && !ai.continentRoute.Active());
        bot.transport = nullptr;
        // A companion's way to its master is not an RPG goal.
        Player master;
        ai.master = &master;
        ai.continentRoute.Start(WorldPosition(1, 0.0f, 0.0f), true);
        status.hub = false;
        assert(!status.StartContinentTravel() && ai.continentRoute.forMaster);
        ai.master = nullptr;
        assert(status.StartContinentTravel() && !ai.continentRoute.forMaster && ai.continentRoute.destination == status.next);
        // A moving target keeps the link in progress nearby and replans after it moves away.
        ai.continentRoute.hasLink = true;
        ai.continentRoute.Start(WorldPosition(1, 520.0f, 0.0f), false);
        assert(ai.continentRoute.hasLink);
        ai.continentRoute.Start(WorldPosition(1, 520.0f + ContinentTravel::TargetMovedYards + 1.0f, 0.0f), false);
        assert(!ai.continentRoute.hasLink);

        // A route to another island of the same map resumes until the bot walks where its destination is.
        sContinentRoutes.Build();
        ai.continentRoute.Finish();
        bot.mapId = 1, bot.x = 9810.0f, bot.z = 1300.0f;
        ai.continentRoute.Start(WorldPosition(1, 6520.0f, 0.0f, 0.0f), false);
        int const before = status.selections;
        assert(status.StartContinentTravel() && status.selections == before && ai.continentRoute.Active());
        bot.x = 6515.0f, bot.z = 0.0f;
        status.hub = true;
        assert(!status.StartContinentTravel() && !ai.continentRoute.Active());
    }

    // Walking between islands is priced, not forbidden; nodes join only on their own map.
    {
        Point const bottom{1, 10.0f, 0.0f, 0.0f, 1}, top{1, 0.0f, 0.0f, 100.0f, 2};
        std::vector<Link> links = {Make(LinkKind::Lift, 7, {1, 0.0f, 0.0f, 0.0f, 1}, {1, 0.0f, 0.0f, 100.0f, 2}, 40.0f)};
        assert((Objects(links, Plan(links, bottom, top)) == std::vector<uint32>{7}));
        auto const walk = Plan({}, bottom, top);
        assert(walk.Found() && walk.links.empty() && walk.seconds > ContinentRoutes::IslandPenaltySeconds);
        assert(!ContinentRoutes::SameArea(bottom, top) && ContinentRoutes::SameArea(bottom, Point{1, 50.0f, 0.0f, 0.0f, 0}));
        assert(ContinentRoutes::SameArea(bottom, Point{1, 50.0f, 0.0f, 0.0f, 1}) && !ContinentRoutes::SameArea(bottom, Point{0}));
        std::vector<ContinentRoutes::TravelNode> nodes = {{1, {0}}, {2, {0}}, {3, {1}}, {4, {0}}, {5, {0}}};
        std::vector<std::pair<uint32, uint32>> walks = {{1, 2}, {2, 3}, {9, 4}, {4, 5}};
        auto const islands = ContinentRoutes::Islands(nodes, walks);
        assert(islands[0] == islands[1] && islands[2] != islands[0] && islands[3] == islands[4]);
        assert(islands[3] != islands[0] && std::count(islands.begin(), islands.end(), 0u) == 0);
    }

    // The travel data's islands, lifts, the Deeprun Tram and ships on one map lead bots everywhere.
    {
        World();
        sContinentRoutes.Build();
        uint32 const canopy = sContinentRoutes.IslandAt(1, 9800, 0, 1300), below = sContinentRoutes.IslandAt(1, 8700, 0, 5);
        uint32 const kalimdor = sContinentRoutes.IslandAt(1, 6510, 0, 0), mesa = sContinentRoutes.IslandAt(1, -1250, 190, 130);
        assert(canopy && below && kalimdor && mesa && canopy != below && below != kalimdor && mesa != kalimdor);
        assert(kalimdor == sContinentRoutes.IslandAt(1, 20, 0, 0) && kalimdor == sContinentRoutes.IslandAt(1, -1300, 200, 69));
        assert(sContinentRoutes.IslandAt(1, 10100, 0, 1300) == 0 && sContinentRoutes.IslandAt(609, 0, 0, 0) == 0);
        assert(sContinentRoutes.IslandAt(369, 5, 2510, 7) != sContinentRoutes.IslandAt(369, 5, 28, 7));
        assert(sContinentRoutes.Locate(WorldPosition(1, 8705.0f, 0.0f, 5.0f)).island == below);

        Player human;
        individualProgression.stages[&human] = PROGRESSION_TBC_TIER_5;
        ContinentRouteState state;
        std::vector<Link> const links = sContinentRoutes.UsableLinks(&human, state);
        assert(Count(links, LinkKind::Lift, 4170) == 2 && Count(links, LinkKind::Lift, 176080) == 2);
        assert(!Has(links, LinkKind::Lift, 20651) && !Has(links, LinkKind::Lift, 9998) && !Has(links, LinkKind::Lift, 100));
        assert(!Has(links, LinkKind::Lift, 9997));
        assert(Count(links, LinkKind::Transport, 103) == 2 && Has(links, LinkKind::Portal, 23));
        assert(Has(links, LinkKind::AreaTrigger, 2173) && Has(links, LinkKind::AreaTrigger, 2175));
        for (Link const& link : links)
            if (link.kind == LinkKind::Lift && link.object == 4170 && link.from.z < 100.0f)
                assert(link.from.island == kalimdor && link.to.island == mesa &&
                       std::fabs(link.seconds - (15.0f + ContinentRoutes::LiftWaitSeconds)) < 0.01f);

        auto route = [&](WorldPosition from, WorldPosition to)
        {
            auto const search = Explore(links, sContinentRoutes.Locate(from), [](Link const&) { return true; });
            return Objects(links, RouteTo(links, search, sContinentRoutes.Locate(to)));
        };
        // Teldrassil's canopy -> portal -> Rut'theran -> boat -> Auberdine.
        assert((route(WorldPosition(1, 9810.0f, 0.0f, 1300.0f), WorldPosition(1, 6520.0f, 0.0f, 0.0f)) ==
                std::vector<uint32>{23, 103}));
        // Mulgore -> elevator -> Thunder Bluff.
        assert((route(WorldPosition(1, -1300.0f, 200.0f, 69.0f), WorldPosition(1, -1250.0f, 190.0f, 130.0f)) ==
                std::vector<uint32>{4170}));
        // Stormwind -> Deeprun Tram -> Ironforge, quicker than the long walk.
        assert((route(WorldPosition(0, -8345.0f, 600.0f, 90.0f), WorldPosition(0, -4795.0f, -1000.0f, 500.0f)) ==
                std::vector<uint32>{2173, 176080, 2175}));
        // Within one island the walk stays.
        assert(route(WorldPosition(1, 1500.0f, 0.0f, 0.0f), WorldPosition(1, 20.0f, 0.0f, 0.0f)).empty());

        // Without travel data there are no islands, and nothing changes for maps.
        PlayerbotsDatabase = PlayerbotsDatabaseConnection();
        sContinentRoutes.Build();
        assert(sContinentRoutes.IslandAt(1, 9800, 0, 1300) == 0 && !Has(sContinentRoutes.UsableLinks(&human, state),
                                                                         LinkKind::Lift, 4170));
    }

    // Lifts are stood on, kept and picked out by their model under the bot.
    {
        Map world;
        Player bot;
        bot.map = &world, bot.mapId = 1, bot.z = 100.0f;
        GameObjectModel deck{-5.0f, 5.0f, -5.0f, 5.0f, 100.0f};
        Transport lift;
        lift.entry = 4170, lift.mapId = 1, lift.m_model = &deck;
        MotionTransport ship;
        ship.entry = 100, ship.mapId = 1, ship.x = 30.0f, ship.m_model = &deck;
        gameObjects = {&lift};
        world.transports = {&ship};
        assert(ContinentTravel::OnTransport(&lift, 1, 0.0f, 0.0f, 100.0f) && ContinentTravel::OnTransport(&lift, 1, 0.0f, 0.0f, 101.5f));
        assert(!ContinentTravel::OnTransport(&lift, 1, 0.0f, 0.0f, 97.0f) && !ContinentTravel::OnTransport(&lift, 1, 0.0f, 0.0f, 103.0f));
        assert(!ContinentTravel::OnTransport(&lift, 1, 10.0f, 0.0f, 100.0f) && !ContinentTravel::OnTransport(nullptr, 1, 0, 0, 0));
        assert(!ContinentTravel::LiftUnder(&bot, 0) && ContinentTravel::LiftUnder(&bot, 4170) == &lift);
        bot.transport = &lift;
        assert(ContinentTravel::LiftUnder(&bot, 0) == &lift);
        bot.z = 110.0f;
        assert(!ContinentTravel::LiftUnder(&bot, 0) && !ContinentTravel::LiftUnder(&bot, 4170));
        bot.z = 100.0f;
        bot.transport = &ship;
        assert(!ContinentTravel::LiftUnder(&bot, 0));
        assert(ContinentTravel::NearestTransport(&bot, 100, 50.0f) == &ship);
        assert(ContinentTravel::NearestTransport(&bot, 4170, 50.0f) == &lift && !ContinentTravel::NearestTransport(&bot, 7, 50.0f));
        gameObjects.clear();
    }

    // A car holds still only while its animation keeps it at a stop, or a paused one at the end it waits at.
    TransportAnimationEntry const atStop{0, 0, 0.0f, 0.0f, 0.0f}, leaving{0, 20000, 0.0f, 0.0f, 0.0f},
        away{0, 30000, 100.0f, 0.0f, 0.0f}, back{0, 40000, 0.0f, 0.0f, 0.0f};
    TransportAnimation cycle;
    cycle.Path = {{0, &atStop}, {20000, &leaving}, {30000, &away}, {40000, &back}};
    cycle.TotalTime = 40000;
    {
        StaticTransport car;
        car.goValue.Transport.AnimationInfo = &cycle;
        car.goValue.Transport.PathProgress = 1000;
        assert(ContinentTravel::HoldsStill(&car, 19000) && !ContinentTravel::HoldsStill(&car, 19500));
        car.goValue.Transport.PathProgress = 25000;
        assert(!ContinentTravel::HoldsStill(&car, 250));
        car.goValue.Transport.PathProgress = 39900;
        assert(!ContinentTravel::HoldsStill(&car, 1000));
        car.pause = 5000;
        for (uint32 state : {GO_STATE_READY, GO_STATE_ACTIVE})
        {
            car.state = state;
            car.goValue.Transport.PathProgress = 0;
            assert(ContinentTravel::HoldsStill(&car, 60000) == (state == GO_STATE_READY));
            car.goValue.Transport.PathProgress = 5000;
            assert(ContinentTravel::HoldsStill(&car, 60000) == (state == GO_STATE_ACTIVE));
            car.goValue.Transport.PathProgress = 2500;
            assert(!ContinentTravel::HoldsStill(&car, 0));
        }
        StaticTransport fixed;
        MotionTransport ship;
        assert(ContinentTravel::HoldsStill(&fixed, 60000) && !ContinentTravel::HoldsStill(&ship, 0));
        assert(!ContinentTravel::HoldsStill(nullptr, 0));
    }

    // Companions board their master's car while it waits, ride still, step off with the master once it
    // stands and wait for a car or ship that left without them.
    {
        World();
        Map world;
        Player bot;
        bot.map = &world, bot.x = 8.0f;
        GameObjectModel deck{-3.0f, 3.0f, -3.0f, 3.0f, 0.0f}, otherDeck{97.0f, 103.0f, -3.0f, 3.0f, 0.0f};
        StaticTransport car, other;
        car.m_model = &deck, other.m_model = &otherDeck, other.x = 100.0f;
        car.goValue.Transport.AnimationInfo = other.goValue.Transport.AnimationInfo = &cycle;
        car.goValue.Transport.PathProgress = other.goValue.Transport.PathProgress = 1000;
        WorldPosition point;
        using ContinentTravel::Ride;
        assert(ContinentTravel::CompanionRide(&bot, &car, point) == Ride::Board);
        assert(point == WorldPosition(0, 1.0f, 0.0f, 0.0f));
        car.goValue.Transport.PathProgress = 17500;
        assert(ContinentTravel::CompanionRide(&bot, &car, point) == Ride::Hold);
        car.goValue.Transport.PathProgress = 1000;
        deck.top = 10.0f;
        assert(ContinentTravel::CompanionRide(&bot, &car, point) == Ride::Hold);
        deck.top = 0.0f;
        bot.x = 70.0f;
        assert(ContinentTravel::CompanionRide(&bot, &car, point) == Ride::Hold);
        bot.x = 60.0f;
        assert(ContinentTravel::CompanionRide(&bot, &car, point) == Ride::Board);

        // On the deck the bot waits for the transport check to take it aboard instead of stepping again.
        bot.x = 2.0f;
        assert(ContinentTravel::CompanionRide(&bot, &car, point) == Ride::Hold);

        // Riding with the master the bot keeps still; when the master steps off it follows at a stop.
        bot.x = 4.0f, bot.transport = &car;
        assert(ContinentTravel::CompanionRide(&bot, &car, point) == Ride::Hold);
        bot.x = 2.0f;
        assert(ContinentTravel::CompanionRide(&bot, &car, point) == Ride::Hold);
        assert(ContinentTravel::CompanionRide(&bot, nullptr, point) == Ride::Leave);
        assert(point == WorldPosition(0, 5.0f, 0.0f, 0.5f));
        assert(ContinentTravel::CompanionRide(&bot, &other, point) == Ride::Leave);
        car.goValue.Transport.PathProgress = 25000;
        assert(ContinentTravel::CompanionRide(&bot, nullptr, point) == Ride::Hold);

        // Ships: the follow logic boards a docked one; a sailing one is waited for, not chased.
        bot.transport = nullptr;
        MotionTransport ship;
        ship.path = transportMgr.GetTransportTemplate(100);
        assert(ContinentTravel::CompanionRide(&bot, &ship, point) == Ride::Follow);
        ship.progress = 90000;
        assert(ContinentTravel::CompanionRide(&bot, &ship, point) == Ride::Hold);
        bot.transport = &ship;
        assert(ContinentTravel::CompanionRide(&bot, &ship, point) == Ride::Follow);
        assert(ContinentTravel::CompanionRide(&bot, nullptr, point) == Ride::Follow);
        bot.transport = nullptr;
        assert(ContinentTravel::CompanionRide(&bot, nullptr, point) == Ride::Follow);
    }

    // Random bots speak to the flight master of each zone they reach on their island.
    {
        World();
        sContinentRoutes.Build();
        uint32 const below = sContinentRoutes.IslandAt(1, 8700, 0, 5), canopy = sContinentRoutes.IslandAt(1, 9800, 0, 1300);
        travelMgr = TravelMgr();
        travelMgr.allianceFlightMasterCache = {{1, {{1, 8720.0f, 0.0f, 5.0f}, 141, 20, 3838, 1, below}},
                                               {2, {{1, 8705.0f, 0.0f, 5.0f}, 999, 21, 3839, 2, below}},
                                               {3, {{1, 8701.0f, 0.0f, 1300.0f}, 141, 22, 3840, 3, canopy}},
                                               {4, {{1, 8730.0f, 0.0f, 5.0f}, 141, 23, 3841, 4, below}}};
        Player bot;
        Map kalimdor;
        bot.map = &kalimdor, bot.mapId = 1, bot.x = 8700.0f, bot.z = 5.0f, bot.zone = 141;
        PlayerbotAI ai;
        std::unordered_map<uint32, uint32> rejected;
        assert(travelMgr.FindUndiscoveredFlightMaster(&bot, rejected)->dbGuid == 1);
        bot.m_taxi.known = {20};
        assert(travelMgr.FindUndiscoveredFlightMaster(&bot, rejected)->dbGuid == 4);
        rejected[4] = nowMs;
        assert(!travelMgr.FindUndiscoveredFlightMaster(&bot, rejected));
        nowMs += ContinentTravel::FlightMasterRetryMs;
        assert(travelMgr.FindUndiscoveredFlightMaster(&bot, rejected)->dbGuid == 4);
        bot.taxiCheater = true;
        assert(!travelMgr.FindUndiscoveredFlightMaster(&bot, rejected));
        bot.taxiCheater = false;
        bot.m_taxi.known.clear();

        NewRpgDiscoverFlightTrigger trigger{&ai, &bot};
        assert(trigger.IsActive());
        for (int condition = 0; condition < 5; ++condition)
        {
            if (condition == 0) sPlayerbotAIConfig.discoverFlightMasters = false;
            if (condition == 1) bot.combat = true;
            if (condition == 2) bot.inFlight = true;
            if (condition == 3) ai.continentRoute.hasLink = true, ai.continentRoute.usedAt = nowMs;
            MotionTransport boat;
            if (condition == 4) bot.transport = &boat;
            assert(!trigger.IsActive());
            sPlayerbotAIConfig.discoverFlightMasters = true;
            bot.combat = bot.inFlight = false;
            ai.continentRoute.ClearLink();
            bot.transport = nullptr;
        }

        Creature master;
        master.guid = 77, master.entry = 3838, master.mapId = 1, master.x = 8720.0f, master.z = 5.0f, master.node = 20;
        creatures = {&master};
        NewRpgDiscoverFlightAction discover(&ai, &bot);
        assert(discover.Execute(Event{}) && discover.moves.size() == 1 && discover.moves[0].x == 8720.0f);
        assert(!bot.m_taxi.IsTaximaskNodeKnown(20));
        bot.x = 8717.0f;
        assert(discover.Execute(Event{}) && bot.m_taxi.IsTaximaskNodeKnown(20) && discover.moves.size() == 1);
        assert(travelMgr.FindUndiscoveredFlightMaster(&bot, ai.rpgInfo.flightMasterRejectedAt)->dbGuid == 4);
        // A hostile master is not spoken to and is given up on.
        bot.m_taxi.known.clear();
        master.reaction = REP_UNFRIENDLY;
        assert(discover.Execute(Event{}) && !bot.m_taxi.IsTaximaskNodeKnown(20) &&
               ai.rpgInfo.flightMasterRejectedAt.contains(1));
        // A master not reached in time is given up on as well.
        ai.rpgInfo = NewRpgInfo();
        master.reaction = 4;
        bot.x = 8600.0f;
        assert(discover.Execute(Event{}));
        nowMs += ContinentTravel::DiscoveryTimeoutMs;
        assert(!discover.Execute(Event{}) && ai.rpgInfo.flightMasterRejectedAt.contains(1));
        creatures.clear();
    }

    std::cout << "Continent routes: earned links, islands, lifts, faction, era, failures, docking, flights, discovery, "
                 "companions and RPG travel\n";
}
'''

COMPILE = [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-g', '-O1', '-D_GLIBCXX_ASSERTIONS', *SANITIZER_FLAGS]


def build(directory, sources, name):
    (directory / 'ContinentRoutePolicy.h').write_text(sources['policy'])
    source = '#include "Fixture.h"\n' + '\n'.join(text for key, text in sources.items() if key != 'policy') + '\n'
    (directory / (name + '.cpp')).write_text(source)
    executable = directory / name
    subprocess.run(COMPILE + ['-I', str(directory), str(directory / (name + '.cpp')), str(directory / 'tests.cpp'),
                              '-o', str(executable)], check=True)
    return run_fixture([str(executable)], env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1:abort_on_error=1',
                                               'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'})


resume_area = re.search(r'!ContinentRoutes::SameArea\(sContinentRoutes.Locate\(WorldPosition\(bot\)\),\s*'
                        r'sContinentRoutes.Locate\(route.destination\)\)', production['start'])[0]

mutations = [
    ('boarding a car about to leave', 'routes', 'distance <= CompanionBoardingYards && HoldsStill(carrier, walk)',
     'distance <= CompanionBoardingYards && (HoldsStill(carrier, walk) || true)'),
    ('boarding a car out of reach', 'routes', 'distance <= CompanionBoardingYards && HoldsStill(carrier, walk)',
     'HoldsStill(carrier, walk)'),
    ('stepping off a moving car', 'routes', 'HoldsStill(ride, StepOffMs) && FindLandingPoint',
     '(HoldsStill(ride, StepOffMs) || true) && FindLandingPoint'),
    ('chasing a sailing ship', 'routes', 'ride == carrier || IsDocked(ship, nullptr) ? Ride::Follow',
     'ride == carrier || IsDocked(ship, nullptr) || true ? Ride::Follow'),
    ('walking about on the master\'s car', 'routes', 'if (ride == carrier ||\n        OnTransport(', 'if (OnTransport('),
    ('stepping again from the deck', 'routes',
     'OnTransport(carrier, bot->GetPhaseMask(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ()) ||', ''),
    ('a moving car counted still', 'routes', '(at - start).squaredLength() > 0.01f', '(at - start).squaredLength() < 0.0f'),
    ('a paused car still at either end', 'routes', 'progress == (car->GetGoState() == GO_STATE_READY ? 0 : pause)',
     '(progress == 0 || progress == pause)'),
    ('route planned from a car', 'trigger', 'ride && ride->IsStaticTransport() && !(route.hasLink',
     'ride && ride->IsStaticTransport() && false && !(route.hasLink'),
    ('a route\'s own lift ride stopped', 'trigger', '!(route.hasLink && route.link.kind == ContinentRoutes::LinkKind::Lift)',
     '!(route.hasLink && false)'),
    ('unusable links planned', 'policy', 'if (!allowed[i] || settled[i + 1])', 'if (settled[i + 1])'),
    ('walking between maps', 'policy', 'if (a.map != b.map)\n        return std::numeric_limits<float>::infinity();\n', ''),
    ('one end of a link in hostile territory', 'policy',
     'return departureAreaTeam != hostile && arrivalAreaTeam != hostile;',
     'return departureAreaTeam != hostile || arrivalAreaTeam != hostile;'),
    ('teleports spent without gain', 'policy', 'constexpr float SpellPenaltySeconds = 60.0f;',
     'constexpr float SpellPenaltySeconds = 0.0f;'),
    ('short flights taken', 'policy', 'if (!(directYards >= FlightMinimumYards))', 'if (false)'),
    ('Outland without earned TBC', 'progression',
     'if (mapId == MAP_OUTLAND && !sIndividualProgression->hasPassedProgression(bot, PROGRESSION_PRE_TBC))',
     'if (mapId == MAP_OUTLAND && false)'),
    ('any race in the TBC starting zones', 'progression',
     '(bot->getRace() == RACE_BLOODELF || bot->getRace() == RACE_DRAENEI) && ', ''),
    ('account expansion ignored', 'progression', 'entry->Expansion() > bot->GetSession()->Expansion()', 'false'),
    ('account lookups outside strict mode', 'progression', 'if (!sIndividualProgression->strictEarnedProgression)',
     'if (false)'),
    ('Northrend without earned Wrath', 'progression',
     'return mapId != MAP_NORTHREND || sIndividualProgression->hasPassedProgression(bot, PROGRESSION_TBC_TIER_5);',
     'return true;'),
    ('faction ignored', 'routes', 'if ((entry.teams & team) && ', 'if ((entry.teams | team) && '),
    ('failed links retried at once', 'routes', ' && Open(state, entry.link)', ''),
    ('era gate ignored', 'routes', ' && CanArrive(bot, entry.link.to, entry.arrivalZone)', ''),
    ('teleport without reagent', 'routes', 'if (info && HasReagents(bot, info) && ',
     'if (info && (HasReagents(bot, info) || true) && '),
    ('teleport on cooldown', 'routes', 'if (!bot->HasSpell(spell.spellId) || bot->HasSpellCooldown(spell.spellId))',
     'if (!bot->HasSpell(spell.spellId))'),
    ('unlearned teleport', 'routes', 'if (!bot->HasSpell(spell.spellId) || bot->HasSpellCooldown(spell.spellId))',
     'if (bot->HasSpellCooldown(spell.spellId))'),
    ('hearthstone on cooldown', 'routes', ' && !bot->HasSpellCooldown(SPELL_HEARTHSTONE)', ''),
    ('hostile portal faction', 'routes', 'horde = !(faction->hostileMask & FACTION_MASK_HORDE);', 'horde = true;'),
    ('portal into an instance', 'routes', '!TeleportDestination(spellId, link.to) || !IsWorldMap(link.to.map) ||',
     '!TeleportDestination(spellId, link.to) ||'),
    ('instance transports', 'routes', 'if (!path || path->inInstance || !path->pathTime)', 'if (!path || !path->pathTime)'),
    ('subzone without its zone team', 'routes', 'if (area->team || !area->zone)', 'if (true)'),
    ('triggered teleports missed', 'routes', '!triggered && info->Effects[i].Effect == SPELL_EFFECT_TRIGGER_SPELL',
     'triggered && info->Effects[i].Effect == SPELL_EFFECT_TRIGGER_SPELL'),
    ('generic teleport spells', 'routes', "info->SpellFamilyName == SPELLFAMILY_GENERIC || ", ''),
    ('teleports without a skill line', 'routes', 'abilities.first == abilities.second',
     '(abilities.first == abilities.second && !spellId)'),
    ('other phases', 'routes', ' || !(spawn.phaseMask & PHASEMASK_NORMAL)', ''),
    ('moving transport counted as docked', 'routes', ' || timer >= frame.DepartureTime', ''),
    ('undiscovered flight', 'flight',
     'nodes.empty() || !CanUseTaxiNodes(bot, std::vector<uint32>(nodes.begin() + 1, nodes.end()))', 'nodes.empty()'),
    ('flight lands far away', 'flight', 'return a->pos.GetExactDist2dSq(target) < b->pos.GetExactDist2dSq(target);',
     'return a->pos.GetExactDist2dSq(target) > b->pos.GetExactDist2dSq(target);'),
    ('undiscovered taxi node', 'taxi', 'if (!sPlayerbotAIConfig.naturalProgression || player->isTaxiCheater())',
     'if (true)'),
    ('SelfBot moved by its companion AI', 'trigger', ' || IsSelfBot(bot)', ''),
    ('master on an unconnected map', 'trigger',
     'return sContinentRoutes.Connects(master->GetMapId()) && sContinentRoutes.Connects(bot->GetMapId());',
     'return true;'),
    ('master aboard a transport', 'trigger', '        master->GetTransport() ||', '       '),
    ('companion travels from an instance', 'trigger', 'bot->IsInFlight() ||\n        bot->GetMap()->Instanceable())',
     'bot->IsInFlight())'),
    ('travel despite a local camp', 'start', 'if (HasTravelHubHere())\n        return false;', ''),
    ('route resumes only aboard', 'start', resume_area, 'false'),
    ('arrival route ends before disembarking', 'start', 'bot->GetTransport() || ', ''),
    ('arrival route ends during flight', 'start', 'bot->IsInFlight() ||', ''),
    ('companion route taken over', 'start', 'if (botAI->GetMaster())\n            return false;', ''),
    ('route without time budget', 'start', ' &&\n            GetMSTimeDiffToNow(route.startedAt) < ContinentTravel::RouteTimeoutMs', ''),
    ('walking across islands free', 'policy', ' + (SeparateIslands(a, b) ? IslandPenaltySeconds : 0.0f)', ''),
    ('islands joined across maps', 'policy', ' && nodes[a->second].at.map == nodes[b->second].at.map', ''),
    ('one area across islands', 'policy', 'return a.map == b.map && !SeparateIslands(a, b);', 'return a.map == b.map;'),
    ('instanced maps travelled', 'routes', 'return entry && entry->IsWorldMap();', 'return entry != nullptr;'),
    ('travel nodes of instanced maps', 'routes', 'if (IsWorldMap(mapId))\n                data.nodes', 'if (true)\n                data.nodes'),
    ('other travel links read as lifts', 'routes', 'else if (type == uint8(TravelNodePathType::transport))',
     'else if (type != uint8(TravelNodePathType::walk))'),
    ('elevator doors ridden', 'routes', ' ||\n            ContinentRoutes::Distance(from->second, to->second) < ContinentRoutes::MinimumLiftYards', ''),
    ('lift spawned elsewhere', 'routes', 'if (!spawned)', 'if (!spawned && false)'),
    ('lift between maps', 'routes', ' ||\n            from->second.map != to->second.map ||', ' ||'),
    ('islands beyond the node radius', 'routes',
     'float nearest = ContinentTravel::IslandNodeRadius * ContinentTravel::IslandNodeRadius;',
     'float nearest = std::numeric_limits<float>::max();'),
    ('ship taken for a lift', 'routes', 'if (!current->ToMotionTransport() &&\n            OnTransport', 'if (OnTransport'),
    ('model hit far below', 'routes', 'float distance = 4.0f;', 'float distance = 40.0f;'),
    ('ships on one map dropped', 'routes', 'if (departure == arrival || ',
     'if (departure == arrival || departure->Node->mapid == arrival->Node->mapid || '),
    ('flight master on another island', 'flight',
     'if (info.pos.GetMapId() != bot->GetMapId() || (island && info.island && info.island != island))',
     'if (info.pos.GetMapId() != bot->GetMapId() || (island && info.island && false))'),
    ('landing on another island', 'flight', '!(island && info.island && info.island != island)',
     '!(island && info.island && false)'),
    ('discovery in another zone', 'discover', ' || info.zoneId != bot->GetZoneId()', ''),
    ('discovery on another island', 'discover', ' ||\n            (island && info.island && info.island != island))',
     ' ||\n            (island && info.island && false))'),
    ('discovered master revisited', 'discover', ' || bot->m_taxi.IsTaximaskNodeKnown(info.taxiNodeId)', ''),
    ('rejected master retried at once', 'discover', 'if (rejected != rejectedAt.end() && ', 'if (false && '),
    ('taxi cheater sent to masters', 'discover', 'if (bot->isTaxiCheater())\n        return nullptr;\n', ''),
    ('flight point learned without speaking', 'discover',
     'flightMaster && bot->GetNPCIfCanInteractWith(flightMaster->GetGUID(), UNIT_NPC_FLAG_FLIGHTMASTER)',
     'flightMaster'),
    ('flight point learned from afar', 'discover', 'if (bot->GetDistance(master->pos) > INTERACTION_DISTANCE)\n        return MoveFarTo(master->pos);', ''),
    ('unreachable master kept', 'discover', '>= ContinentTravel::DiscoveryTimeoutMs)', '>= 2 * ContinentTravel::DiscoveryTimeoutMs)'),
    ('discovery in combat', 'discover', ' || bot->IsInCombat()', ''),
    ('discovery while boarding', 'discover', 'if (route.hasLink && route.usedAt)', 'if (route.hasLink && false)'),
    ('discovery switched off', 'discover', 'if (!sPlayerbotAIConfig.discoverFlightMasters || ', 'if ('),
    ('companion ignores islands', 'trigger', (' ||\n           !ContinentRoutes::SameArea(sContinentRoutes.Locate(WorldPosition(bot)),\n'
                                              '                                      sContinentRoutes.Locate(WorldPosition(master)));'),
     ';'),
    ('route ends on the wrong island', 'start', resume_area, 'bot->GetMapId() != route.destination.GetMapId()'),
]

with tempfile.TemporaryDirectory(prefix='portable-continent-routes-') as temporary:
    temporary = Path(temporary)
    (temporary / 'Fixture.h').write_text('#pragma once\n' + fixture)
    (temporary / 'IndividualProgression.h').write_text('#pragma once\n')
    (temporary / 'tests.cpp').write_text(tests)
    result = build(temporary, production, 'continent-routes')
    print(result.stdout + result.stderr, end='')
    if result.returncode:
        raise SystemExit(f'Continent route fixture failed (exit {result.returncode})')

    def rejected(numbered):
        index, (label, key, old, new) = numbered
        mutated = {**production, key: production[key].replace(old, new)}
        if mutated[key] == production[key]:
            raise SystemExit(f'{label} mutation was not applied')
        directory = temporary / f'mutant-{index}'
        directory.mkdir()
        for name in ('Fixture.h', 'IndividualProgression.h', 'tests.cpp'):
            (directory / name).write_text((temporary / name).read_text())
        return build(directory, mutated, 'mutant').returncode != 0

    for (label, *_), result in zip(mutations, in_parallel(rejected, enumerate(mutations))):
        if not result:
            raise SystemExit(f'Continent route fixture did not reject: {label}')
        print(f'Continent route mutation rejected: {label}')
