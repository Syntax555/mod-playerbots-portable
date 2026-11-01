"""Check that bots change maps only over links an ordinary player can take.

The production route planner, link catalog, Individual Progression arrival
gate, transport docking test, flight search, companion trigger and the RPG
start of continent travel run against doubles that answer as the core and
Individual Progression do. Native contracts the doubles rely on are asserted
from the pinned sources. The route execution code is checked to use only the
core's area trigger, game object, spell, item and taxi handlers. Mutation
checks confirm that each gate is required. No realm is started.
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
area_defines = read(core / 'src/server/game/Maps/AreaDefines.h')
transport_mgr_header = read(core / 'src/server/game/Maps/TransportMgr.h')
transport_mgr = read(core / 'src/server/game/Maps/TransportMgr.cpp')
transport = read(core / 'src/server/game/Entities/Transport/Transport.cpp')
misc_handler = read(core / 'src/server/game/Handlers/MiscHandler.cpp')


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
             'GAMEOBJECT_TYPE_SPELLCASTER', 'SPELL_EFFECT_TELEPORT_UNITS', 'SPELL_EFFECT_TRIGGER_SPELL',
             'SPELLFAMILY_GENERIC', 'SPELLFAMILY_MAGE'], shared),
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
}.items()}
execution['route action'] = function(rpg, 'bool NewRpgTravelRouteAction::Execute(Event /*event*/)')
execution['master action'] = function(rpg, 'bool TravelToMasterAction::Execute(Event /*event*/)')
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


assert_ordinary(execution)
for label, name, old, new in [
    ('route teleport', 'board', 'MoveStraightTo(deck);', 'bot->TeleportTo(deck);'),
    ('boarding attaches the bot', 'board', 'MoveStraightTo(deck);', 'docked->AddPassenger(bot);'),
    ('remote area trigger', 'take', 'if (bot->IsInAreaTriggerRadius(trigger))', 'if (true)'),
    ('flight without discovered route', 'overland', '!CanUseTaxiNodes(bot, nodes) || ', ''),
    ('triggered teleport spell', 'use', 'botAI->CastSpell(link.object, bot)', 'botAI->CastSpell(link.object, bot, true)'),
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

state_declaration = function(routes_header, 'struct ContinentRouteState') + ';'
catalog_declaration = function(routes_header, 'class ContinentRouteCatalog') + ';'
travel_declaration = function(routes_header, 'namespace ContinentTravel')
constants = '\n'.join(line for line in routes.splitlines()
                      if re.match(r'constexpr (uint32|float) (ITEM_HEARTHSTONE|SPELL_HEARTHSTONE|SameMapPortal)', line))
assert constants.count('constexpr') == 3
assert 'ITEM_HEARTHSTONE = 6948;' in constants and 'SPELL_HEARTHSTONE = 8690;' in constants
hearthstone = re.search(r"^\(6948,.*$", read(core / 'data/sql/base/db_world/item_template.sql'), re.MULTILINE)
assert hearthstone and "'Hearthstone'" in hearthstone[0] and ',8690,' in hearthstone[0].replace(' ', '')

production = {
    'policy': policy,
    'routes': '\n'.join([
        'namespace {', constants,
        function(routes, 'uint32 ZoneOf(uint32 areaId)'),
        function(routes, 'uint32 AreaTeam(uint32 areaId)'),
        function(routes, 'uint32 AreaAt(Point const& point)'),
        function(routes, 'bool IsContinent(uint32 mapId)'),
        function(routes, 'bool TeleportDestination(uint32 spellId, Point& to, bool triggered = false)'),
        function(routes, 'bool HasReagents(Player* bot, SpellInfo const* info)'),
        function(routes, 'bool Open(ContinentRouteState const& state, Link const& link)'),
        '}',
        function(routes, 'void ContinentRouteState::Start(WorldPosition const& target, bool master)'),
        function(routes, 'void ContinentRouteState::Finish()'),
        function(routes, 'void ContinentRouteState::ClearLink()'),
        function(routes, 'void ContinentRouteState::ClearFlight()'),
        function(routes, 'uint64 ContinentRouteCatalog::Key(Link const& link)'),
        function(routes, 'void ContinentRouteCatalog::Add(Link const& link, bool alliance, bool horde)'),
        function(routes, 'void ContinentRouteCatalog::Build()'),
        function(routes, 'bool ContinentRouteCatalog::CanArrive(Player* bot, Point const& to, uint32 arrivalZone)'),
        function(routes, 'std::vector<Link> ContinentRouteCatalog::UsableLinks(Player* bot, ContinentRouteState const& state) const'),
        'namespace ContinentTravel {',
        function(routes, 'bool IsDocked(MotionTransport const* transport, Point const* stop)'),
        '}',
    ]),
    'progression': '\n'.join([
        'namespace {', starting_zone, '}',
        function(progression, 'bool ContinentRouteProgression::CanArrive(Player* bot, uint32 mapId, float x, float y, '
                              'float z, uint32 zoneId)'),
    ]),
    'flight': function(travel, 'bool TravelMgr::FindFlightTowards(Player* bot, WorldPosition const& target, '
                               'FlightMasterInfo const*& origin,'),
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
#include <set>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

using uint8 = std::uint8_t; using uint16 = std::uint16_t; using uint32 = std::uint32_t; using uint64 = std::uint64_t;
using int32 = std::int32_t;
template <class... Arguments> inline void LogSink(Arguments const&...) {}
#define LOG_INFO(...) LogSink(__VA_ARGS__)
#define LOG_DEBUG(...) LogSink(__VA_ARGS__)
constexpr uint32 MINUTE = 60, HOUR = 3600, IN_MILLISECONDS = 1000, PHASEMASK_NORMAL = 1;
enum ProgressionState : uint8 {};
NATIVES

inline uint32 nowMs = 100000000;
inline uint32 getMSTime() { return nowMs; }
inline uint32 GetMSTimeDiffToNow(uint32 old) { return nowMs - old; }

struct WorldPosition
{
    uint32 mapId = 0;
    float x = 0.0f, y = 0.0f, z = 0.0f;
    WorldPosition() = default;
    WorldPosition(uint32 map, float x, float y, float z = 0.0f) : mapId(map), x(x), y(y), z(z) {}
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
    bool continent = true;
    uint32 Expansion() const { return expansion; }
    bool IsContinent() const { return continent; }
};
struct AreaTableEntry { uint32 ID = 0; uint32 zone = 0; uint32 team = 0; };
struct FactionTemplateEntry { uint32 hostileMask = 0; };
inline Store<MapEntry> sMapStore;
inline Store<AreaTableEntry> sAreaTableStore;
inline Store<FactionTemplateEntry> sFactionTemplateStore;

// Areas by map and x coordinate; the base map answers for the whole continent.
class Map
{
public:
    uint32 id = 0;
    bool instanceable = false;
    std::map<int, uint32> areas;
    bool Instanceable() const { return instanceable; }
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

class Transport { public: virtual ~Transport() = default; };
class MotionTransport : public Transport
{
public:
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

class WorldSession { public: uint8 expansion = 2; uint8 Expansion() const { return expansion; } };
struct PlayerTaxi
{
    std::set<uint32> known;
    bool IsTaximaskNodeKnown(uint32 node) const { return known.contains(node); }
};
class Player
{
public:
    uint32 mapId = 0;
    float x = 0.0f, y = 0.0f, z = 0.0f;
    TeamId team = TEAM_ALLIANCE;
    uint8 race = RACE_HUMAN;
    bool gm = false, alive = true, inWorld = true, inFlight = false, teleporting = false, selfBot = false;
    bool taxiCheater = false, noReagent = false;
    Transport* transport = nullptr;
    Map* map = nullptr;
    WorldSession session;
    PlayerTaxi m_taxi;
    std::set<uint32> spells, cooldowns;
    std::map<uint32, uint32> items;
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
    float GetExactDist2d(Player const* other) const { return std::hypot(x - other->x, y - other->y); }
};
inline bool IsSelfBot(Player* player) { return player && player->selfBot; }

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

struct PlayerbotAIConfig { bool continentTravel = true; bool naturalProgression = true; };
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
    struct FlightMasterInfo { WorldPosition pos; uint32 zoneId; uint32 taxiNodeId; uint32 templateEntry; uint32 dbGuid; };
    std::map<uint32, FlightMasterInfo> allianceFlightMasterCache;
    std::map<uint32, FlightMasterInfo> hordeFlightMasterCache;
    FlightMasterInfo const* nearest = nullptr;
    FlightMasterInfo const* GetNearestFlightMasterInfo(Player*) const { return nearest; }
    bool FindFlightTowards(Player* bot, WorldPosition const& target, FlightMasterInfo const*& origin,
                           std::vector<uint32>& path, WorldPosition& landing) const;
};

struct NewRpgInfo { int travelRoutes = 0; void ChangeToTravelRoute() { ++travelRoutes; } };
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
    bool HasTravelHubOnMap() { return hub; }
    WorldPosition SelectContinentDestination() { ++selections; return next; }
    bool StartContinentTravel();
};
'''
fixture = (fixture.replace('NATIVES', natives).replace('STATE_DECLARATION', state_declaration)
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

TaxiPathNodeEntry stops[] = {
    {0, 10.0f, 0.0f, 0.0f, 2}, {0, 500.0f, 0.0f, 0.0f, 0}, {1, 20.0f, 0.0f, 0.0f, 2}, {1, 900.0f, 0.0f, 0.0f, 0},
    {1, 30.0f, 0.0f, 0.0f, 2}, {1, 40.0f, 0.0f, 0.0f, 2}};

// Kalimdor (1), Eastern Kingdoms (0), Outland (530); 609 is an instance-like map.
void World()
{
    sMapStore.rows = {{0, {0, true}}, {1, {0, true}}, {530, {1, true}}, {571, {2, true}}, {609, {2, false}}};
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

    objectMgr = ObjectMgr();
    for (uint32 entry : {100u, 101u, 102u})
        objectMgr.templates[entry].type = GAMEOBJECT_TYPE_MO_TRANSPORT;
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
    };
    objectMgr.triggers = {{4354, {0, -11900.0f, 0.0f, 0.0f}}, {5, {0, 10.0f, 0.0f, 0.0f}},
                          {6, {0, 10.0f, 0.0f, 0.0f}}};
    objectMgr.teleports = {{4354, {530, -250.0f, 0.0f, 0.0f}}, {5, {0, 3000.0f, 0.0f, 0.0f}},
                           {6, {609, 0.0f, 0.0f, 0.0f}}, {7, {1, 0.0f, 0.0f, 0.0f}}};

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
        assert(sContinentRoutes.Connects(0) && sContinentRoutes.Connects(1) && sContinentRoutes.Connects(530));
        assert(!sContinentRoutes.Connects(609) && !sContinentRoutes.Connects(571));

        Player horde;
        horde.team = TEAM_HORDE;
        horde.race = RACE_BLOODELF;
        individualProgression.stages[&horde] = PROGRESSION_TBC_TIER_5;
        ContinentRouteState state;
        std::vector<Link> links = sContinentRoutes.UsableLinks(&horde, state);
        // The ship docks at a Horde dock in Kalimdor; both directions ride the same cycle.
        assert(Has(links, LinkKind::Transport, 100, 0) && Has(links, LinkKind::Transport, 100, 1));
        assert(!Has(links, LinkKind::Transport, 101) && !Has(links, LinkKind::Transport, 102));
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
        TravelMgr travel;
        TravelMgr::FlightMasterInfo origin{{0, 0.0f, 0.0f}, 1, 10, 1, 1};
        travel.nearest = &origin;
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
        assert((path == std::vector<uint32>{10, 12} && landing.x == 950.0f && from == &origin));
        bot.m_taxi.known.insert(13);
        assert(travel.FindFlightTowards(&bot, target, from, path, landing));
        assert((path == std::vector<uint32>{10, 13, 14} && landing.x == 990.0f));
        travel.nearest = nullptr;
        assert(!travel.FindFlightTowards(&bot, target, from, path, landing));
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
        // Arrived on the destination's map, the route ends and ordinary choices follow.
        bot.mapId = 1;
        assert(!status.StartContinentTravel() && !ai.continentRoute.Active());
        // Routes end after their time budget.
        bot.mapId = 0;
        ai.continentRoute.Start(status.next, false);
        nowMs += ContinentTravel::RouteTimeoutMs;
        assert(!status.StartContinentTravel() && !ai.continentRoute.Active());
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
    }

    std::cout << "Continent routes: earned links, faction, era, failures, docking, flights, companions and RPG travel\n";
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


mutations = [
    ('unusable links planned', 'policy', 'if (!allowed[i] || settled[i + 1])', 'if (settled[i + 1])'),
    ('walking between maps', 'policy', ('return a.map == b.map ? Distance(a, b) * WalkDetour / RunSpeed : '
                                        'std::numeric_limits<float>::infinity();'),
     'return Distance(a, b) * WalkDetour / RunSpeed;'),
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
    ('portal into an instance', 'routes', '!TeleportDestination(spellId, link.to) || !IsContinent(link.to.map) ||',
     '!TeleportDestination(spellId, link.to) ||'),
    ('same-map transport stops', 'routes', 'if (departure->Node->mapid == arrival->Node->mapid || ', 'if ('),
    ('instance transports', 'routes', 'if (!path || path->inInstance || !path->pathTime)', 'if (!path || !path->pathTime)'),
    ('subzone without its zone team', 'routes', 'if (area->team || !area->zone)', 'if (true)'),
    ('triggered teleports missed', 'routes', '!triggered && info->Effects[i].Effect == SPELL_EFFECT_TRIGGER_SPELL',
     'triggered && info->Effects[i].Effect == SPELL_EFFECT_TRIGGER_SPELL'),
    ('generic teleport spells', 'routes', "info->SpellFamilyName == SPELLFAMILY_GENERIC || ", ''),
    ('teleports without a skill line', 'routes', 'abilities.first == abilities.second',
     '(abilities.first == abilities.second && !spellId)'),
    ('other phases', 'routes', ' || !(data.phaseMask & PHASEMASK_NORMAL)', ''),
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
    ('travel despite a local camp', 'start', 'if (HasTravelHubOnMap())\n        return false;', ''),
    ('route never resumes', 'start', 'if (bot->GetMapId() != route.destination.GetMapId() &&', 'if (false &&'),
    ('companion route taken over', 'start', 'if (botAI->GetMaster())\n            return false;', ''),
    ('route without time budget', 'start', ' &&\n            GetMSTimeDiffToNow(route.startedAt) < ContinentTravel::RouteTimeoutMs', ''),
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
