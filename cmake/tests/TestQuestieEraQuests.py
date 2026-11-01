"""Show each character Questie quests of its own era through the Questie bridge.

Era gates refuse later quests with availability conditions on the character's progression
markers and hide their givers with visibility conditions or awareness scripts. The bridge's
production snapshot code runs against Player, Creature, map, quest and disable doubles: the
quests a character's conditions refuse are reported like disabled quests, all or nothing,
and a hidden questgiver counts as offering no quest unless its quests are hidden anyway.
Protocol 19 also carries template restrictions and GUID-scoped positive observations.
Mutations remove condition, visibility, authority and complete-snapshot checks.
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
    reject_mutants,
    run_fixture,
    source_argument,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, default=prepared_core(), help='prepared core directory')
source_argument(parser, 'bridge', help='Questie bridge source directory override')
source_argument(parser, 'addon', help='Questie addon directory override')
args = parser.parse_args()
core = args.source
repository = Path(__file__).resolve().parents[2]
bridge = args.bridge or core / 'modules/mod-questie-bridge/src'
source = (bridge / 'QuestieBridge.cpp').read_text()
helpers = (bridge / 'QuestieBridgeConditions.h').read_text()
start = source.index("                // Quests this character's availability conditions refuse")
locked_block = source[start:source.index('                if (capabilities & (Questgivers | QuestgiverTemplates))\n', start)]
hidden_check = ('bool const hidden = !player->CanSeeObjectByVisibilityConditions(creature)\n'
                '                                || (creature->IsAIEnabled && !creature->AI()->CanBeSeen(player));')
assert hidden_check in source
giver_block = function(source, '                if (capabilities & (Questgivers | QuestgiverTemplates))')
cache = (bridge / 'QuestieBridgeStateCache.h').read_text()
late = source[source.index('                std::size_t const lateRows'):start]
capability = function(source, 'bool HasCapability(std::string const& caps, std::string_view capability)')
disabled = function(source, 'bool IsQuestDisabled(uint32 questId)')
assert 'constexpr std::size_t MaxGiverObservations = 64;' in source
assert 'constexpr uint32 QuestConditions = 65536;' in source
assert 'constexpr uint32 QuestgiverTemplates = 32768;' in source
candidates = function(source, '    QuestieBridge::MapQuestCreatures const& GetMapCreatures(')
assert 'common.StarterEntries.contains(creature->GetEntry())' in candidates
assert 'candidates.Starters.insert(spawnId);' in candidates
assert 'if (sConfigMgr->GetOption<bool>("QuestieBridge.QuestConditions", true))\n                caps |= QuestConditions;' in source
assert 'QuestieBridge.QuestConditions = 1' in (core / 'modules/mod-questie-bridge/conf/QuestieBridge.conf.dist').read_text()

# Native contracts: quest availability conditions are what SatisfyQuestConditions reads, a
# player's visibility conditions and an awareness script decide what it sees, and the client
# hides a disabled quest unless it is on that quest, and drops a snapshot past 64 givers.
quests = (core / 'src/server/game/Entities/Player/PlayerQuest.cpp').read_text()
assert 'GetConditionsForNotGroupedEntry(CONDITION_SOURCE_TYPE_QUEST_AVAILABLE, qInfo->GetQuestId())' in function(
    quests, 'bool Player::SatisfyQuestConditions(Quest const* qInfo, bool msg)')
objects = (core / 'src/server/game/Entities/Object/Object.cpp').read_text()
hidden = function(objects, 'bool HiddenFrom(WorldObject const* object, Player const* player)')
assert '(creature->IsAIEnabled && !creature->AI()->CanBeSeen(player)) || !player->CanSeeObjectByVisibilityConditions(object)' in hidden
questie = args.addon or repository / '.module-cache/prepared-source-addons/Questie-335'
client = (questie / 'Modules/Network/QuestieServer.lua').read_text()
assert 'local PREFIX, PROTOCOL_VERSION = "QSTSVR", "19"' in client
assert 'constexpr std::uint32_t ProtocolVersion = 19;' in (bridge / 'QuestieBridgeProtocol.h').read_text()
assert '[17] = "QUESTGIVERTEMPLATES"' in client
assert 'elseif kind == "D" and result.caps.QUESTDISABLES and #fields == 2 and id and id > 0 then' in client
assert re.search(r'if not spawnId or spawnId == 0 or giverCount >= 64 or not fields\[4\]:match', client)
assert '#guid ~= 16 or not guid:match("^[0-9A-F]+$")' in client
assert 'tonumber(guid:sub(5, 10), 16) ~= id' in client
guid_header = (core / 'src/server/game/Entities/Object/ObjectGuid.h').read_text()
assert 'Unit           = 0xF130,' in guid_header
assert 'uint64(counter) | (uint64(entry) << 24) | (uint64(hi) << 48)' in guid_header
assert '[[nodiscard]] bool HaveAtClient(WorldObject const* u) const;' in (
    core / 'src/server/game/Entities/Player/Player.h').read_text()
assert 'bool distanceCheck = false' in (core / 'src/server/game/Entities/Object/Object.h').read_text()
assert ('if C_QuestLog.IsOnQuest(questId) ~= true and QuestieServer:IsQuestDisabled(questId) then'
        in (questie / 'Database/QuestieDB.lua').read_text())

fixture = r'''
#include <algorithm>
#include <cassert>
#include <iomanip>
#include <sstream>
#include <cstdint>
#include <iostream>
#include <limits>
#include <map>
#include <ranges>
#include <set>
#include <string>
#include <string_view>
#include <tuple>
#include <utility>
#include <vector>
using uint32 = std::uint32_t; using uint64 = std::uint64_t;
constexpr uint32 QuestConditions = 65536, QuestgiverTemplates = 32768, Questgivers = 16384;
constexpr uint32 Phases = 256, ICC = 64, QuestXP = 1024;
constexpr uint32 QuestReputation = 2048, QuestMoney = 4096;
constexpr std::size_t MaxGiverObservations = 64, PhaseMaxRows = 8, QuestieBridgeICCMaxRows = 8;
namespace QuestieBridge { constexpr std::size_t ReputationMaxRows = 4; }
@CACHE@
namespace Acore
{
std::string StringFormat(char const* pattern, uint32 entry, uint32 spawn, int active, uint64 guid)
{
    assert(std::string(pattern) == "G:{}:{}:{}:{:016X}");
    std::ostringstream row;
    row << "G:" << entry << ':' << spawn << ':' << active << ':' << std::hex << std::uppercase
        << std::setfill('0') << std::setw(16) << guid;
    return row.str();
}
}
enum { DISABLE_TYPE_QUEST = 1 };
struct Quest { uint32 id; };
struct DisableMgr
{
    std::set<uint32> disabled;
    bool IsDisabledFor(int, uint32 id, void*) const { return disabled.contains(id); }
} disables;
DisableMgr* sDisableMgr = &disables;
struct ObjectMgr
{
    std::map<uint32, Quest*> quests;
    std::multimap<uint32, uint32> relations;
    std::map<uint32, Quest*> const& GetQuestTemplates() const { return quests; }
    Quest const* GetQuestTemplate(uint32 id) const { auto found = quests.find(id); return found == quests.end() ? nullptr : found->second; }
    std::multimap<uint32, uint32> const* GetCreatureQuestRelationMap() const { return &relations; }
} objects;
ObjectMgr* sObjectMgr = &objects;
struct Player;
struct CreatureAI { bool visible = true; bool CanBeSeen(Player const*) const { return visible; } };
struct Creature
{
    uint32 entry = 0, zone = 1;
    uint64 spawn = 0;
    bool alive = true, questgiver = true, hostile = false, stealthed = false, IsAIEnabled = true;
    bool atClient = true, inSight = true;
    uint64 guid = 1;
    struct Guid { uint64 raw; uint64 GetRawValue() const { return raw; } };
    Guid GetGUID() const { return {0xF130000000000000ULL | (uint64(entry) << 24) | guid}; }
    CreatureAI ai;
    bool IsInWorld() const { return true; }
    bool IsAlive() const { return alive; }
    uint32 GetZoneId() const { return zone; }
    uint32 GetEntry() const { return entry; }
    uint64 GetSpawnId() const { return spawn; }
    bool IsQuestGiver() const { return questgiver; }
    bool IsHostileTo(Player const*) const { return hostile; }
    CreatureAI* AI() const { return const_cast<CreatureAI*>(&ai); }
};
struct Map
{
    std::multimap<uint64, Creature*> store;
    std::multimap<uint64, Creature*> const& GetCreatureBySpawnIdStore() const { return store; }
};
struct Player
{
    uint32 stage = 0;
    std::map<uint32, std::pair<uint32, uint32>> opens;  // quest: first and last stage it may be taken
    std::set<Creature const*> hidden;
    Map map;
    bool SatisfyQuestConditions(Quest const* quest, bool) const
    {
        auto found = opens.find(quest->id);
        return found == opens.end() || (stage >= found->second.first && stage <= found->second.second);
    }
    bool CanSeeObjectByVisibilityConditions(Creature const* creature) const { return !hidden.contains(creature); }
    // The core's mutual visibility: scripts and conditions hide as well as stealth.
    bool HaveAtClient(Creature const* creature) const { return creature->atClient; }
    bool CanSeeOrDetect(Creature const* creature, bool ignoreStealth, bool distanceCheck) const
    {
        return (ignoreStealth || !creature->stealthed) && (!distanceCheck || creature->inSight)
            && !hidden.contains(creature) && (!creature->IsAIEnabled || creature->ai.visible);
    }
    Map* GetMap() { return &map; }
    uint32 GetZoneId() const { return 1; }
    uint32 GetMapId() const { return 0; }
};
@HELPERS@
@CAPABILITY@
@DISABLED@
QuestieBridge::MapQuestCreatures GetMapCreatures(Player* player, QuestieBridge::CommonState const& common)
{
    QuestieBridge::MapQuestCreatures candidates;
    for (auto const& [spawnId, creature] : player->GetMap()->GetCreatureBySpawnIdStore())
        if (creature && spawnId && common.StarterEntries.contains(creature->GetEntry()))
            candidates.Starters.insert(spawnId);
    return candidates;
}
std::vector<std::string> Snapshot(Player* player, std::string caps, std::size_t existing = 0,
    uint32 capabilities = QuestConditions | Questgivers | QuestgiverTemplates,
    std::set<uint32> restricted = {}, std::string* sentCaps = nullptr)
{
    QuestieBridge::CommonState common{std::move(caps), {}, std::nullopt, false};
    for (auto const& [entry, quest] : objects.relations)
        common.StarterEntries.insert(entry);
    common.RestrictedGiverTemplates = std::move(restricted);
    if (capabilities & QuestgiverTemplates)
    {
        common.GiverTemplateRows = {"P:QGT_COUNT:" + std::to_string(common.RestrictedGiverTemplates.size())};
        for (uint32 entry : common.RestrictedGiverTemplates)
            common.GiverTemplateRows->push_back("N:" + std::to_string(entry));
    }
    std::vector<std::string> rows(existing, "E:1:0:0:0");
    std::string playerCaps = common.Caps;
@LATE@
@LOCKED@
@GIVERS@
    if (sentCaps) *sentCaps = std::move(playerCaps);
    rows.erase(rows.begin(), rows.begin() + existing);
    return rows;
}
bool Has(std::vector<std::string> const& rows, std::string const& row)
{
    for (std::string const& value : rows)
        if (value == row)
            return true;
    return false;
}
int main()
{
    // 2.3 Dustwallow (tier 8), the Ahn'Qiraj war's colossus secrets (tier 4 only), an open Vanilla
    // quest and a server-wide disable.
    Quest dustwallow{11123}, secrets{8859}, vanilla{7848}, retired{960};
    for (Quest* quest : {&dustwallow, &secrets, &vanilla, &retired})
        objects.quests[quest->id] = quest;
    disables.disabled = {960};
    objects.relations = {{23612, 11123}, {15192, 8859}, {4949, 7848}, {6491, 7848}};
    Player player;
    player.opens = {{11123, {8, 18}}, {8859, {4, 4}}, {960, {99, 99}}};
    Creature mudsprocket, colossus, thrall, guard;
    for (auto [creature, entry, spawn] : {std::tuple{&mudsprocket, 23612u, 8505u}, std::tuple{&colossus, 15192u, 9001u},
                                          std::tuple{&thrall, 4949u, 4000u}, std::tuple{&guard, 6491u, 4100u}})
    {
        creature->entry = entry;
        creature->spawn = spawn;
        player.map.store.emplace(creature->spawn, creature);
    }
    player.hidden = {&mudsprocket};
    colossus.ai.visible = false;
    guard.questgiver = false;

    player.stage = 3;
    auto rows = Snapshot(&player, "EVENTS,QUESTDISABLES");
    assert(Has(rows, "D:11123") && Has(rows, "D:8859") && !Has(rows, "D:7848") && !Has(rows, "D:960"));
    // Mudsprocket's only quest is hidden already; the colossus' secret too, so neither NPC is listed.
    // A visible NPC without the questgiver flag stays reported as before.
    assert(!Has(rows, "G:23612:8505:0:F130005C3C000001") && !Has(rows, "G:15192:9001:0:F130003B58000001") && !Has(rows, "G:4949:4000:0:F130001355000001") && Has(rows, "G:6491:4100:0:F13000195B000001"));
    player.stage = 4;
    rows = Snapshot(&player, "EVENTS,QUESTDISABLES");
    assert(Has(rows, "D:11123") && !Has(rows, "D:8859"));
    // The script still hides the colossus' giver; its open quest makes it an unavailable spawn.
    assert(Has(rows, "G:15192:9001:0:F130003B58000001"));
    player.stage = 8;
    rows = Snapshot(&player, "EVENTS,QUESTDISABLES");
    assert(!Has(rows, "D:11123") && Has(rows, "D:8859") && Has(rows, "G:23612:8505:0:F130005C3C000001"));
    // Hostile or stealthed NPCs stay unknown; no disables capability, no refused quests.
    mudsprocket.hostile = true;
    thrall.stealthed = true;
    rows = Snapshot(&player, "EVENTS");
    assert(!Has(rows, "D:8859") && !Has(rows, "G:23612:8505:0:F130005C3C000001") && !Has(rows, "G:4949:4000:0:F130001355000001"));
    // Past the snapshot's row budget the list is withheld rather than sent in part.
    rows = Snapshot(&player, "EVENTS,QUESTDISABLES", 4096 - 65);
    assert(!Has(rows, "D:8859"));
    // Global restrictions are complete and paired with a client-visible positive exception.
    thrall.stealthed = false;
    std::string sentCaps;
    rows = Snapshot(&player, "EVENTS,QUESTDISABLES", 0,
        QuestConditions | Questgivers | QuestgiverTemplates, {4949}, &sentCaps);
    assert(Has(rows, "N:4949") && Has(rows, "G:4949:4000:1:F130001355000001"));
    assert(HasCapability(sentCaps, "QUESTGIVERTEMPLATES") && HasCapability(sentCaps, "QUESTGIVERS"));
    thrall.atClient = false;
    rows = Snapshot(&player, "EVENTS,QUESTDISABLES", 0,
        QuestConditions | Questgivers | QuestgiverTemplates, {4949});
    assert(Has(rows, "N:4949") && !Has(rows, "G:4949:4000:1:F130001355000001"));
    thrall.atClient = true;
    thrall.inSight = false;
    rows = Snapshot(&player, "EVENTS,QUESTDISABLES", 0,
        QuestConditions | Questgivers | QuestgiverTemplates, {4949});
    assert(!Has(rows, "G:4949:4000:1:F130001355000001"));
    thrall.inSight = true;
    // Templates can be enabled without local conditions or negative observations.
    rows = Snapshot(&player, "EVENTS,QUESTDISABLES", 0, QuestgiverTemplates, {4949});
    assert(!Has(rows, "D:8859") && Has(rows, "G:4949:4000:1:F130001355000001")
        && !Has(rows, "G:6491:4100:0:F13000195B000001"));
    // Alternative incarnations of the same spawn keep separate GUID-scoped states.
    Creature alternate = thrall;
    alternate.guid = 2;
    alternate.questgiver = false;
    player.map.store.emplace(4000, &alternate);
    rows = Snapshot(&player, "EVENTS,QUESTDISABLES");
    assert(Has(rows, "G:4949:4000:1:F130001355000001") && Has(rows, "G:4949:4000:0:F130001355000002"));
    player.map.store.clear();
    std::vector<Creature> crowded(65, guard);
    for (uint32 i = 0; i < 64; ++i)
    {
        crowded[i].guid = i + 1;
        crowded[i].spawn = i + 1;
        player.map.store.emplace(i + 1, &crowded[i]);
    }
    rows = Snapshot(&player, "EVENTS,QUESTDISABLES", 0,
        QuestConditions | Questgivers | QuestgiverTemplates, {}, &sentCaps);
    assert(HasCapability(sentCaps, "QUESTGIVERS") && Has(rows, "P:QGT_COUNT:0"));
    crowded[64].spawn = crowded[64].guid = 65;
    player.map.store.emplace(65, &crowded[64]);
    rows = Snapshot(&player, "EVENTS,QUESTDISABLES", 0,
        QuestConditions | Questgivers | QuestgiverTemplates, {}, &sentCaps);
    assert(!HasCapability(sentCaps, "QUESTGIVERS") && !HasCapability(sentCaps, "QUESTGIVERTEMPLATES"));
    std::cout << "Questie era quests: conditions, hidden givers, protocol 19 visibility and complete catalogs passed\n";
}
'''.replace('@HELPERS@', helpers).replace('@CAPABILITY@', capability).replace('@DISABLED@', disabled).replace(
    '@LATE@', late).replace('@LOCKED@', locked_block).replace('@GIVERS@', giver_block).replace('@CACHE@', cache)


def build(directory, executable):
    return [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-Wno-unused-variable', '-Wno-unused-but-set-variable',
            '-g', *SANITIZER_FLAGS, str(directory / 'Fixture.cpp'), '-o', str(executable)]


with tempfile.TemporaryDirectory(prefix='questie-era-quests-') as temporary:
    work = Path(temporary)
    (work / 'Fixture.cpp').write_text(fixture)
    subprocess.run(build(work, work / 'fixture'), check=True)
    result = run_fixture([str(work / 'fixture')])
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout, end='')
    reject_mutants(work, (
        ('refused quests not reported', 'Fixture.cpp', 'if (!disabled(questId) && !satisfied(questId))',
         'if (!disabled(questId) && !satisfied(questId) && false)'),
        ('hidden givers ignored', 'Fixture.cpp', hidden_check, 'bool const hidden = false;'),
        ('client visibility ignored', 'Fixture.cpp', 'player->HaveAtClient(creature) &&', ''),
        ('distance check ignored', 'Fixture.cpp', 'player->CanSeeOrDetect(creature, false, true)',
         'player->CanSeeOrDetect(creature, false, false)'),
        ('partial giver observations sent', 'Fixture.cpp', 'observations.size() <= MaxGiverObservations', 'true'),
        ('partial list sent', 'Fixture.cpp', '                        locked.clear();\n', '\n'),
    ), build, 'Questie era quests')
