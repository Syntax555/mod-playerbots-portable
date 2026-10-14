"""Exercise Individual Progression's map entry gates as hook and as entry check.

The production teleport hook, its shared gate function and the exported entry
check compile against native-shaped doubles. A teleport and a check must reach
the same decision for every map, stage, level, key and attunement case; only
the teleport sends refusal text or returns ship passengers to their dock.
"""

import argparse
from pathlib import Path
import re
import subprocess
import tempfile

from FixtureSupport import function, prepared_core


def enum(source, name):
    match = re.search(r'^enum ' + name + r'\b[^{]*\{.*?^\};', source, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(0)


repository = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--core', type=Path, default=prepared_core(repository), help='prepared core directory')
parser.add_argument('--source', type=Path, help='prepared Individual Progression module directory')
args = parser.parse_args()
core = args.core
module = args.source or core / 'modules/mod-individual-progression'
player_source = (module / 'src/IndividualProgressionPlayer.cpp').read_text()
progression_source = (module / 'src/IndividualProgression.cpp').read_text()
header = (module / 'src/IndividualProgression.h').read_text()
areas = (core / 'src/server/game/Maps/AreaDefines.h').read_text()

# A null session is the native way to send no chat: the formatted
# PSendSysMessage overloads return before building a packet. The plain-text
# overload sends without that check, so the double keeps both overloads.
chat_header = (core / 'src/server/game/Chat/Chat.h').read_text()
chat_source = (core / 'src/server/game/Chat/Chat.cpp').read_text()
template = function(chat_header, '    void PSendSysMessage(char const* fmt, Args&&... args)')
assert 'if (HasSession())' in template and 'SendSysMessage(' in template
assert 'if (!m_session)\n        return false;' in function(chat_source, 'bool ChatHandler::HasSession() const')
assert 'void PSendSysMessage(std::string_view str, bool escapeCharacters = false);' in chat_header
assert 'm_session->SendPacket(&data);' in function(chat_source, 'void ChatHandler::SendSysMessage(std::string_view str,')
assert re.search(r'RACE_BLOODELF\s*= 10,', (core / 'src/server/shared/SharedDefines.h').read_text())
assert re.search(r'RACE_DRAENEI\s*= 11\b', (core / 'src/server/shared/SharedDefines.h').read_text())
assert re.search(r'QUEST_STATUS_REWARDED\s*= 6,', (core / 'src/server/game/Quests/QuestDef.h').read_text())
assert 'struct InstanceTemplate\n{\n    uint32 Parent;' in (core / 'src/server/game/Maps/Map.h').read_text()

hook = function(player_source, '    bool OnPlayerBeforeTeleport(').replace(' override', '')
gates = function(player_source, '    static bool CanEnterMap(')
bridge = function(player_source, 'bool IndividualProgression::CanEnterMap(')
starting_zone = function(player_source, '    static bool IsTBCRaceStartingZone(')
# Every refusal text and the ship return depend on the hook's session.
assert 'ChatHandler(player->GetSession())' not in gates and gates.count('ChatHandler(session)') >= 20
assert gates.index('if (!session)\n                return false;') < gates.index('TeleportTo(')
assert 'const uint16 AREA_STORMWIND_HARBOR = 4411;' in gates
assert 'IndividualPlayerProgression::CanEnterMap(player, mapId, x, y, z, nullptr)' in bridge
for name in ('MAP_THE_FORGE_OF_SOULS', 'MAP_MAGISTERS_TERRACE', 'MAP_TRIAL_OF_THE_CHAMPION', 'MAP_ZUL_GURUB'):
    assert name in gates, name

natives = '\n'.join((
    function(progression_source, 'uint8 IndividualProgression::GetPlayerProgressionFromQuests('),
    function(progression_source, 'bool IndividualProgression::hasPassedProgression('),
))
enums = '\n'.join((enum(areas, 'AreaTableIDs'), enum(areas, 'MapIDs'),
                   *(enum(header, name) for name in ('ProgressionQuestIDs', 'ProgressionAreas', 'DungeonKeys',
                                                       'ProgressionState'))))

prelude = r'''
#include <cassert>
#include <cstdint>
#include <iostream>
#include <map>
#include <set>
#include <string_view>
#include <vector>
using uint8 = std::uint8_t; using uint16 = std::uint16_t; using uint32 = std::uint32_t;
constexpr uint8 RACE_HUMAN = 1, RACE_BLOODELF = 10, RACE_DRAENEI = 11;
constexpr uint32 QUEST_STATUS_NONE = 0, QUEST_STATUS_REWARDED = 6;
constexpr uint32 STORMWIND_HARBOR = 4411; // the gate's own ship-dock area constant
@ENUMS@
struct Unit;
struct Creature {};
struct WorldSession
{
    uint32 account = 1;
    int messages = 0;
    uint32 GetAccountId() const { return account; }
};
struct ChatHandler
{
    WorldSession* session;
    explicit ChatHandler(WorldSession* value) : session(value) {}
    template<class... Args> void PSendSysMessage(char const*, Args&&...) { if (session) ++session->messages; }
    void PSendSysMessage(std::string_view, bool = false) { assert(session); ++session->messages; }
};
struct Player
{
    bool inWorld = true, gm = false, crew = false;
    uint32 level = 60, area = 0;
    uint8 race = RACE_HUMAN;
    WorldSession session;
    std::set<uint32> items;
    std::map<uint32, uint32> quests;
    int teleports = 0;
    bool IsInWorld() const { return inWorld; }
    bool IsGameMaster() const { return gm; }
    uint32 GetLevel() const { return level; }
    uint8 getRace() const { return race; }
    uint32 GetAreaId() const { return area; }
    WorldSession* GetSession() { return &session; }
    bool HasItemCount(uint32 item, uint32 count = 1, bool = false) const { return count == 1 && items.contains(item); }
    uint32 GetQuestStatus(uint32 quest) const
    { auto found = quests.find(quest); return found == quests.end() ? QUEST_STATUS_NONE : found->second; }
    Creature* FindNearestCreature(uint32, float, bool = true) const { static Creature crewman; return crew ? &crewman : nullptr; }
    bool TeleportTo(uint32, float, float, float, float) { ++teleports; return true; }
};
struct Map { uint32 zone = 0; uint32 GetZoneId(uint32, float, float, float) const { return zone; } };
struct MapMgr { Map map; Map const* FindMap(uint32, uint32) const { return &map; } } mapManager;
auto* sMapMgr = &mapManager;
struct InstanceTemplate { uint32 Parent; };
struct ObjectMgr
{
    std::map<uint32, InstanceTemplate> templates;
    InstanceTemplate const* GetInstanceTemplate(uint32 map)
    { auto found = templates.find(map); return found == templates.end() ? nullptr : &found->second; }
} objectManager;
auto* sObjectMgr = &objectManager;
struct IndividualProgression
{
    bool enabled = true, normal = true, attuned = false;
    int progressionLimit = 0, tbcRacesProgressionLevel = 8, RequiredZulGurubProgression = 3, RequiredZulAmanProgression = 12;
    static inline uint8 accountStage = 0;
    uint8 GetPlayerProgressionFromQuests(Player* player) const;
    bool hasPassedProgression(Player* player, ProgressionState state) const;
    bool isNormalAccount(Player*) const { return normal; }
    bool isAttuned(Player*) const { return attuned; }
    static uint8 GetAccountProgression(uint32) { return accountStage; }
    bool CanEnterMap(Player* player, uint32 mapId, float x, float y, float z) const;
} progression;
auto* sIndividualProgression = &progression;
@NATIVES@
struct IndividualPlayerProgression
{
@STARTING_ZONE@
@HOOK@
@GATES@
};
@BRIDGE@
'''

tests = r'''
struct Case { bool allowed; int messages, teleports; };
Case Teleport(Player& player, uint32 map)
{
    player.session.messages = 0; player.teleports = 0;
    bool allowed = IndividualPlayerProgression().OnPlayerBeforeTeleport(&player, map, 1, 2, 3, 0, 0, nullptr);
    return {allowed, player.session.messages, player.teleports};
}
Case Check(Player& player, uint32 map)
{
    player.session.messages = 0; player.teleports = 0;
    bool allowed = progression.CanEnterMap(&player, map, 1, 2, 3);
    return {allowed, player.session.messages, player.teleports};
}
void Stage(Player& player, uint8 stage)
{
    for (uint8 i = 1; i <= 18; ++i)
        player.quests.erase(66000 + i);
    for (uint8 i = 1; i <= stage; ++i)
        player.quests[66000 + i] = QUEST_STATUS_REWARDED;
}
int main()
{
    objectManager.templates = {{MAP_THE_FORGE_OF_SOULS, {MAP_NORTHREND}}, {MAP_MAGISTERS_TERRACE, {MAP_OUTLAND}},
                               {MAP_NAXXRAMAS, {MAP_NORTHREND}}, {MAP_ZUL_AMAN, {MAP_OUTLAND}},
                               {MAP_ZUL_GURUB, {MAP_EASTERN_KINGDOMS}}};
    std::vector<uint32> const maps = {
        MAP_EASTERN_KINGDOMS, MAP_KALIMDOR, MAP_OUTLAND, MAP_NORTHREND, MAP_BLACKWING_LAIR, MAP_ONYXIAS_LAIR,
        MAP_ZUL_GURUB, MAP_AHN_QIRAJ_TEMPLE, MAP_RUINS_OF_AHN_QIRAJ, MAP_ZUL_AMAN, MAP_ULDUAR,
        MAP_TRIAL_OF_THE_CHAMPION, MAP_TRIAL_OF_THE_CRUSADER, MAP_ICECROWN_CITADEL, MAP_THE_FORGE_OF_SOULS,
        MAP_THE_RUBY_SANCTUM, MAP_MAGISTERS_TERRACE, MAP_THE_SUNWELL, MAP_TEMPEST_KEEP,
        MAP_COILFANG_SERPENTSHRINE_CAVERN, MAP_THE_BATTLE_FOR_MOUNT_HYJAL, MAP_BLACK_TEMPLE, MAP_NAXXRAMAS};
    uint32 cases = 0, refusals = 0, messages = 0;
    for (uint32 map : maps)
    for (uint8 stage = 0; stage <= 18; ++stage)
    for (uint32 level : {49, 50, 60, 70, 80})
    for (int keys = 0; keys < 4; ++keys)
    for (uint32 zone : {0u, uint32(AREA_ISLE_OF_QUEL_DANAS), uint32(AREA_EVERSONG_WOODS)})
    {
        Player player; Stage(player, stage); player.level = level; player.crew = true;
        player.area = keys & 1 ? STORMWIND_HARBOR : uint32(AREA_TIRISFAL_GLADES);
        player.race = keys & 2 ? RACE_BLOODELF : RACE_HUMAN;
        mapManager.map.zone = zone;
        progression.attuned = keys == 3;
        IndividualProgression::accountStage = keys & 1 ? 8 : 0;
        if (keys & 1)
        {
            player.items = {ITEM_DRAKEFIRE_AMULET, ITEM_TEMPEST_KEY, ITEM_MEDALLION_OF_KARABOR};
            for (uint32 quest : {TRIAL_MAGTHERIDON, CUDGEL_OF_KARDESH, VIALS_OF_ETERNITY})
                player.quests[quest] = QUEST_STATUS_REWARDED;
        }
        Case const teleport = Teleport(player, map);
        Case const check = Check(player, map);
        // The entry check reaches the teleport's decision and acts on nobody.
        assert(check.allowed == teleport.allowed);
        assert(check.messages == 0 && check.teleports == 0);
        assert(teleport.allowed || map == MAP_ONYXIAS_LAIR || map == MAP_OUTLAND || map == MAP_NAXXRAMAS ||
               objectManager.GetInstanceTemplate(map) || teleport.messages == 1);
        assert(teleport.teleports == 0 || (map == MAP_NORTHREND && !teleport.allowed));
        refusals += !teleport.allowed; messages += teleport.messages; ++cases;
    }
    assert(refusals > 1000 && messages > 1000);

    // The dungeon stages used by autonomous parties.
    Player bot;
    for (uint8 stage = 0; stage <= 18; ++stage)
    {
        Stage(bot, stage); bot.level = 80;
        assert(Check(bot, MAP_THE_FORGE_OF_SOULS).allowed == (stage >= PROGRESSION_WOTLK_TIER_3));
        assert(Check(bot, MAP_MAGISTERS_TERRACE).allowed == (stage >= PROGRESSION_TBC_TIER_4));
        assert(Check(bot, MAP_TRIAL_OF_THE_CHAMPION).allowed == (stage >= PROGRESSION_WOTLK_TIER_2));
        bot.level = 60;
        assert(Check(bot, MAP_ZUL_GURUB).allowed == (stage >= 3));
    }

    // Only a real teleport returns a Vanilla ship passenger to the harbour.
    Player passenger; passenger.area = STORMWIND_HARBOR; passenger.crew = true; Stage(passenger, 12);
    Case const ship = Teleport(passenger, MAP_NORTHREND);
    assert(!ship.allowed && ship.teleports == 1 && ship.messages == 1);
    Case const probe = Check(passenger, MAP_NORTHREND);
    assert(!probe.allowed && probe.teleports == 0 && probe.messages == 0);

    // Unrestricted characters and disabled progression stay unrestricted.
    Player gm; gm.gm = true;
    assert(Teleport(gm, MAP_THE_RUBY_SANCTUM).allowed && Check(gm, MAP_THE_RUBY_SANCTUM).allowed);
    Player away; away.inWorld = false;
    assert(Teleport(away, MAP_THE_RUBY_SANCTUM).allowed && Check(away, MAP_THE_RUBY_SANCTUM).allowed);
    progression.enabled = false; Player any;
    assert(Teleport(any, MAP_THE_RUBY_SANCTUM).allowed && Check(any, MAP_THE_RUBY_SANCTUM).allowed);
    progression.enabled = true;
    assert(!IndividualPlayerProgression().OnPlayerBeforeTeleport(nullptr, MAP_KALIMDOR, 0, 0, 0, 0, 0, nullptr));
    assert(!progression.CanEnterMap(nullptr, MAP_KALIMDOR, 0, 0, 0));
    std::cout << "Map entry gates: " << cases << " teleport/check pairs agree; checks send no text and move nobody\n";
}
'''


def build(gate_source, hook_source, bridge_source):
    return (prelude.replace('@ENUMS@', enums).replace('@NATIVES@', natives).replace('@STARTING_ZONE@', starting_zone)
            .replace('@HOOK@', hook_source).replace('@GATES@', gate_source).replace('@BRIDGE@', bridge_source) + tests)


mutations = (
    ('ship return in checks', gates, 'if (!session)\n                return false;\n', '', 'check.teleports == 0'),
    ('refusal text in checks', gates, 'ChatHandler(session)', 'ChatHandler(player->GetSession())',
     'check.messages == 0'),
    ('session in the exported check', bridge, 'x, y, z, nullptr)', 'x, y, z, player->GetSession())',
     'check.messages == 0'),
    ('silent teleport', hook, 'player ? player->GetSession() : nullptr', 'nullptr', 'teleport.messages == 1'),
)
with tempfile.TemporaryDirectory(prefix='portable-map-gates-') as directory:
    temporary = Path(directory)
    variants = [('production', build(gates, hook, bridge), None)]
    for label, text, old, new, failure in mutations:
        assert old in text, label
        changed = text.replace(old, new)
        variants.append((label, build(changed if text is gates else gates, changed if text is hook else hook,
                                      changed if text is bridge else bridge), failure))
    for label, source_text, failure in variants:
        source = temporary / 'gates.cpp'
        executable = temporary / 'gates'
        source.write_text(source_text)
        subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-g', '-O1',
                        '-fsanitize=address,undefined', '-fno-omit-frame-pointer', str(source), '-o', str(executable)],
                       check=True)
        result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=120, check=False)
        if failure is None:
            print(result.stdout, end='')
            assert result.returncode == 0, result.stderr
        else:
            assert result.returncode != 0 and failure in result.stderr, (label, result.stderr)
            print(f'Map entry gates reject the {label} mutation')
