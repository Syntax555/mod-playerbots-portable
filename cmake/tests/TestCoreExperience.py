"""Exercise native group XP, Hellfire favors and online/offline rested XP.

The production group reward loop, group-rate formula, resting update and rest
storage and kill awards run against native-shaped realm doubles under
ASan/UBSan. Mutations restore regressions and remove their guards.
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
core = parser.parse_args().source
player_path = core / 'src/server/game/Entities/Player'
player = (player_path / 'Player.cpp').read_text()
header = (player_path / 'Player.h').read_text()
updates = (player_path / 'PlayerUpdates.cpp').read_text()
storage = (player_path / 'PlayerStorage.cpp').read_text()
killer = (player_path / 'KillRewarder.cpp').read_text()
formulas = (core / 'src/server/game/Miscellaneous/Formulas.h').read_text()
world = (core / 'src/server/game/World/World.h').read_text()
objects = (core / 'src/server/game/Entities/Object/Object.h').read_text()
maps = (core / 'src/server/shared/DataStores/DBCStructure.h').read_text()
groups = (core / 'src/server/game/Groups/Group.h').read_text()
unit = (core / 'src/server/game/Entities/Unit/Unit.cpp').read_text()
utility = (core / 'src/common/Utilities/Util.h').read_text()
areas = (core / 'src/server/game/Maps/AreaDefines.h').read_text()

# The favor parents cast the linked XP aura; its 5% effect and the other
# tested XP aura are also checked against the client data by TestEraExperience.
linked = (core / 'data/sql/base/db_world/spell_linked_spell.sql').read_text()
for parent in (32096, 32098):
    assert re.search(rf'\({parent},32172,2,', linked)
for path in [core / 'data/sql/base/db_world/spell_group.sql', *core.glob('data/sql/updates/db_world/*.sql'),
             *core.glob('modules/*/data/sql/**/*.sql')]:
    text = path.read_text(encoding='utf-8', errors='replace')
    if 'spell_group`' in text:
        assert not {32172, 57353} & {int(number) for number in re.findall(r'\b\d+\b', text)}, path

# Preserve the types and map classification supplied by the native producers.
assert 'float GetRestBonus() const { return _restBonus; }' in header
assert 'time_t _restTime;' in header and 'time_t m_Last_tick;' in header
assert 'uint32 GetUInt32Value(uint16 index) const;' in objects
assert 'float getRate(ServerConfigs index) const' in world
assert 'uint32 getIntConfig(ServerConfigs index) const' in world
assert 'bool isRaidGroup() const;' in groups
assert 'GroupReference* GetFirstMember() { return m_memberMgr.getFirst(); }' in groups
assert 'time_t now = GameTime::GetGameTime().count();' in updates
assert 'time_t lastTick = m_Last_tick;' in updates
assert re.search(r'uint32 time_diff = uint32\(now - logoutTime\);', storage)
assert 'if (_victim && (_isBattleGround || (!_isPvP && !_killer->GetVehicle())))' in function(
    killer, 'void KillRewarder::_InitXP(')
assert 'GiveXP(XP, nullptr, 1.0f, isLFGReward);' in function(
    (player_path / 'PlayerQuest.cpp').read_text(), 'void Player::RewardQuest(')
assert 'GiveXP(XP, nullptr);' in function(player, 'void Player::CheckAreaExploreAndOutdoor(')
offline = storage[storage.index('_restBonus = fields[26].Get<float>();'):]
native = '\n'.join((
    function(utility, 'template <class T, class U>\ninline T CalculatePct('),
    function(utility, 'template <class T, class U>\ninline T AddPct('),
    'namespace Acore::XP { ' + function(formulas, 'inline float xp_in_group_rate(') + ' }',
    'namespace Acore::XP { ' + function(formulas, 'inline uint8 GetGrayLevel(') + ' }',
    function(unit, 'float Unit::GetTotalAuraMultiplier(AuraType auraType, std::function'),
    function(unit, 'float Unit::GetTotalAuraMultiplier(AuraType auraType) const'),
    function(player, 'void Player::GiveXP('),
    function(killer, 'uint8 KillRewarder::_GetPlayerLevel('),
    function(killer, 'void KillRewarder::_RewardXP('),
    function(killer, 'void KillRewarder::_RewardGroup('),
    function(player, 'void Player::SetRestBonus('),
    'void Player::OnlineRest(time_t lastTick) { time_t now = GameTime::GetGameTime().count();\n' +
    function(updates, '    if (HasPlayerFlag(PLAYER_FLAGS_RESTING))') + '\n}',
    'void Player::OfflineRest(uint32 time_diff, bool inn) { Field fields[29]; fields[28].value = inn;\n' +
    function(offline, '    if (time_diff > 0)') + '\n}',
))

fixture = r'''
#include <array>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <ctime>
#include <iostream>
#include <functional>
#include <list>
#include <map>
#include <vector>
using uint8 = std::uint8_t; using uint16 = std::uint16_t; using uint32 = std::uint32_t;
using int32 = std::int32_t;
enum ServerConfigs { RATE_REST_INGAME, RATE_REST_OFFLINE_IN_TAVERN_OR_CITY,
    RATE_REST_OFFLINE_IN_WILDERNESS, RATE_REST_MAX_BONUS, CONFIG_MAX_PLAYER_LEVEL, CONFIG_TRIAL_LEVEL_CAP };
enum { PLAYER_FLAGS_RESTING, PLAYER_NEXT_LEVEL_XP, PLAYER_BYTES_2, PLAYER_REST_STATE_EXPERIENCE,
    PLAYER_FLAGS_NO_XP_GAIN, PLAYER_FLAGS_NO_PLAY_TIME, PLAYER_FLAGS_PARTIAL_PLAY_TIME, PLAYER_XP };
enum PlayerXPSource { XPSOURCE_KILL };
enum AuraType { SPELL_AURA_MOD_XP_PCT };
enum { FAVOR_AREAS };
REST_STATES;
struct World {
    std::array<float, 4> rates = {1, 1, 1, 1.5f};
    float getRate(ServerConfigs index) const { return rates.at(index); }
    uint32 getIntConfig(ServerConfigs index) const { return index == CONFIG_TRIAL_LEVEL_CAP ? 0 : 80; }
} world;
World* sWorld = &world;
std::chrono::seconds clockTime{100};
namespace GameTime { std::chrono::seconds GetGameTime() { return clockTime; } }
enum { MAP_COMMON, MAP_INSTANCE, MAP_RAID };
struct MapEntry {
    uint32 map_type = MAP_COMMON;
    IS_DUNGEON
    IS_RAID
};
struct MapStore {
    MapEntry entry;
    MapEntry const* LookupEntry(uint32) const { return &entry; }
} sMapStore;
struct WorldSession {
    bool IsARecruiter() const { return false; }
    uint32 GetRecruiterId() const { return 0; }
    bool IsTrialAccount() const { return false; }
};
struct SpellInfo { uint32 Id; };
enum SpellGroup : uint32 {};
struct AuraEffect {
    SpellInfo info; int32 amount;
    SpellInfo const* GetSpellInfo() const { return &info; }
    int32 GetAmount() const { return amount; }
};
struct SpellMgr {
    bool AddSameEffectStackRuleSpellGroups(SpellInfo const*, uint32, int32, std::map<SpellGroup, int32>&) const {
        return false;
    }
} spellMgr;
SpellMgr* sSpellMgr = &spellMgr;
using AuraEffectList = std::list<AuraEffect*>;
struct Creature;
struct Unit {
    Creature* creature = nullptr;
    AuraEffectList auras;
    Creature* ToCreature() { return creature; }
    bool IsCreature() const { return creature; }
    AuraEffectList const& GetAuraEffectsByType(AuraType) const { return auras; }
    float GetTotalAuraMultiplier(AuraType auraType) const;
    float GetTotalAuraMultiplier(AuraType auraType, std::function<bool(AuraEffect const*)> const& predicate) const;
};
struct Creature : Unit {
    Creature() { creature = this; }
    uint8 GetLevel() const { return 20; }
    uint8 GetHighestPlayerAttackerLevel() const { return 20; }
    bool hasLootRecipient() const { return true; }
};
struct Pet { uint32 xp = 0; void GivePetXP(uint32 value) { xp += value; } };
struct Player;
struct ScriptMgr {
    void OnPlayerBeforeGetLevelForXPGain(Player const*, uint8&) {}
    void OnPlayerGiveXP(Player*, uint32&, Unit*, PlayerXPSource) {}
} scriptMgr;
ScriptMgr* sScriptMgr = &scriptMgr;
struct Field { uint8 value = 0; template<typename T> T Get() const { return T(value); } };
struct Player : Unit {
    bool near = true, resting = true;
    uint8 level = 20, restState = 0;
    uint32 nextLevelXP = 1152000, displayedRest = 0;
    uint32 xp = 0, zone = 0, favor = 0;
    Pet pet;
    float _restBonus = 0;
    time_t _restTime = 100;
    WorldSession session;
    uint32 GetMapId() const { return 0; }
    bool IsAtGroupRewardDistance(Unit const*) const { return near; }
    bool HasPlayerFlag(int flag) const { return flag == PLAYER_FLAGS_RESTING && resting; }
    bool IsAlive() const { return true; }
    uint32 GetBattlegroundId() const { return 0; }
    uint32 GetZoneId() const { return zone; }
    bool HasAnyAuras(uint32 first, uint32 second) const { return favor == first || favor == second; }
    uint8 GetLevel() const { return level; }
    uint32 GetUInt32Value(uint16 index) const { return index == PLAYER_XP ? xp : nextLevelXP; }
    void SetUInt32Value(uint16 index, uint32 value) { (index == PLAYER_XP ? xp : displayedRest) = value; }
    void SetByteValue(uint16, uint8, uint8 value) { restState = value; }
    bool GetsRecruitAFriendBonus(bool) const { return false; }
    WorldSession* GetSession() { return &session; }
    float GetRestBonus() const { return _restBonus; }
    uint32 GetXPRestBonus(uint32) const { return 0; }
    void SendLogXPGain(uint32, Unit*, uint32, bool, float) {}
    void GiveLevel(uint8 value) { level = value; }
    Pet* GetPet() { return &pet; }
    void GiveXP(uint32 xp, Unit* victim, float group_rate = 1.0f, bool isLFGReward = false);
    void SetRestBonus(float);
    void OnlineRest(time_t lastTick);
    void OfflineRest(uint32 time_diff, bool inn);
};
struct GroupReference {
    Player* player = nullptr; GroupReference* following = nullptr;
    Player* GetSource() const { return player; }
    GroupReference* next() const { return following; }
};
struct Group {
    bool raid = false;
    std::vector<GroupReference> members;
    bool isRaidGroup() const { return raid; }
    GroupReference* GetFirstMember() { return members.empty() ? nullptr : &members[0]; }
};
struct KillRewarder {
    Player* _killer = nullptr; Unit* _victim = nullptr; Group* _group = nullptr;
    Player* _maxNotGrayMember = nullptr;
    uint8 _maxLevel = 20, _maxNotGrayMemberLevel = 20;
    uint32 _count = 0, _xp = 0, initialXP = 100;
    float _groupRate = 1;
    bool _isBattleGround = false, _isPvP = false, _isFullXP = true;
    uint32 initialized = 0;
    std::vector<Player*> rewarded;
    bool dungeon = false;
    // Every case has a victim and an unmounted killer; world PvP gives no XP.
    void _InitXP(Player*) { ++initialized; _xp = _isBattleGround || !_isPvP ? initialXP : 0; }
    void _RewardPlayer(Player* member, bool isDungeon) { rewarded.push_back(member); dungeon = isDungeon; }
    void _RewardGroup();
    uint8 _GetPlayerLevel(Player const* player);
    void _RewardXP(Player* player, float rate);
};
#include "Native.cpp"

bool Close(float actual, float expected) { return std::fabs(actual - expected) < 0.01f; }
void TestFavors()
{
    AuraEffect favor{{32172}, 5}, heirloom{{57353}, 10};
    for (uint32 zone : {0u, uint32(AREA_HELLFIRE_PENINSULA), uint32(AREA_HELLFIRE_RAMPARTS),
                       uint32(AREA_MAGTHERIDONS_LAIR), uint32(AREA_THE_BLOOD_FURNACE),
                       uint32(AREA_THE_SHATTERED_HALLS)})
        for (uint32 parent : {0u, 32096u, 32098u})
            for (bool grouped : {false, true})
                for (bool stacked : {false, true})
                {
                    Player player;
                    player.zone = zone;
                    // spell_area keeps the parents in the five Hellfire zones only.
                    bool const favored = zone && parent;
                    player.favor = favored ? parent : 0;
                    if (favored) player.auras.push_back(&favor);
                    if (stacked) player.auras.push_back(&heirloom);
                    Creature victim;
                    Group group;
                    KillRewarder reward;
                    reward._victim = &victim;
                    reward._xp = 200;
                    if (grouped) { reward._group = &group; reward._maxNotGrayMember = &player; }
                    reward._RewardXP(&player, 1.0f);
                    uint32 expected = favored ? (stacked ? 231 : 209) : (stacked ? 220 : 200);
                    assert(player.xp == expected);
                    assert(player.pet.xp == (grouped ? expected / 2 : expected));
                    // Quests and exploration both call GiveXP with a null victim.
                    player.xp = 0;
                    player.GiveXP(200, nullptr);
                    assert(player.xp == (favored ? 209u : 200u));
                }
}
void TestGroupRates()
{
    std::array<float, 7> partyRates = {1, 1, 1.166f, 1.3f, 1.4f, 1.4f, 1.4f};
    for (uint32 count = 1; count <= 7; ++count)
        for (uint32 map : {MAP_COMMON, MAP_INSTANCE, MAP_RAID})
            for (bool raid : {false, true})
                for (bool battleground : {false, true})
                    for (bool pvp : {false, true})
                    {
                        std::array<Player, 8> players;
                        players[0].near = false; // The killer still receives credit.
                        players[count].near = false;
                        Group group;
                        group.raid = raid;
                        group.members.resize(count + 2);
                        for (uint32 i = 0; i < count + 2; ++i)
                            group.members[i] = {i <= count ? &players[i] : nullptr,
                                i + 1 < count + 2 ? &group.members[i + 1] : nullptr};
                        sMapStore.entry.map_type = map;
                        Unit victim;
                        KillRewarder reward;
                        reward._killer = &players[0]; reward._victim = &victim; reward._group = &group;
                        reward._maxNotGrayMember = &players[0]; reward._count = count;
                        reward._isBattleGround = battleground; reward._isPvP = pvp;
                        reward._RewardGroup();
                        assert(reward.initialized == 1 && reward.rewarded.size() == count);
                        for (uint32 i = 0; i < count; ++i) assert(reward.rewarded[i] == &players[i]);
                        float expected = battleground || (raid && !pvp) ? 1.0f : partyRates[count - 1];
                        assert(Close(reward._groupRate, expected));
                        assert(reward.dungeon == (!pvp && map != MAP_COMMON));
                        reward.rewarded.clear(); reward._maxLevel = 0;
                        reward._RewardGroup();
                        assert(reward.rewarded.empty() && reward.initialized == 1);
                        reward._maxLevel = 20; reward.initialXP = 0;
                        reward._RewardGroup();
                        assert(reward.rewarded.size() == (battleground ? 0 : count));
                    }
}

void Advance(Player& player, time_t now, time_t lastTick)
{
    clockTime = std::chrono::seconds(now);
    player.OnlineRest(lastTick);
}
void TestRest()
{
    world.rates = {1, 1, 1, 1.5f};
    Player online, offline;
    Advance(online, 109, 108);
    assert(online._restTime == 100 && online.GetRestBonus() == 0);
    Advance(online, 110, 109);
    assert(online._restTime == 110 && Close(online.GetRestBonus(), 10));
    Advance(online, 110, 110);
    assert(Close(online.GetRestBonus(), 10));
    Advance(online, 120, 120); // An unchanged played-time tick freezes accrual.
    assert(online._restTime == 110 && Close(online.GetRestBonus(), 10));
    Advance(online, 120, 119);
    assert(online._restTime == 120 && Close(online.GetRestBonus(), 20));
    offline.OfflineRest(20, true);
    assert(Close(offline.GetRestBonus(), online.GetRestBonus()));
    assert(online.displayedRest == 20 && online.restState == REST_STATE_RESTED);

    for (float rate : {0.0f, 0.5f, 1.0f, 2.0f})
    {
        world.rates[RATE_REST_INGAME] = world.rates[RATE_REST_OFFLINE_IN_TAVERN_OR_CITY] = rate;
        Player oneTick, manyTicks, off;
        oneTick.SetRestBonus(25); manyTicks.SetRestBonus(25); off.SetRestBonus(25);
        Advance(oneTick, 28900, 100);
        for (time_t tick = 110; tick <= 28900; tick += 10) Advance(manyTicks, tick, tick - 1);
        off.OfflineRest(28800, true);
        assert(Close(oneTick.GetRestBonus(), 25 + rate * 28800));
        assert(Close(oneTick.GetRestBonus(), manyTicks.GetRestBonus()));
        assert(Close(oneTick.GetRestBonus(), off.GetRestBonus()));
    }
    world.rates[RATE_REST_INGAME] = 1;
    Player wilderness;
    wilderness.OfflineRest(28800, false);
    assert(Close(wilderness.GetRestBonus(), 7142.4f)); // Native offline wilderness rate remains 0.031.
    for (bool resting : {false, true})
        for (time_t restTime : {time_t(0), time_t(100)})
        {
            Player player;
            player.resting = resting; player._restTime = restTime;
            Advance(player, 120, 119);
            assert(Close(player.GetRestBonus(), resting && restTime ? 20 : 0));
        }
    Player capped, maximum;
    capped.SetRestBonus(864000 - 5);
    Advance(capped, 120, 119);
    assert(Close(capped.GetRestBonus(), 864000) && capped.displayedRest == 864000);
    maximum.level = 80;
    Advance(maximum, 120, 119);
    assert(maximum.GetRestBonus() == 0 && maximum.displayedRest == 0);
}
int main() { TestFavors(); TestGroupRates(); TestRest(); std::cout << "Core experience fixture passed\n"; }
'''.replace('REST_STATES', function(header, 'enum PlayerRestState')) \
   .replace('FAVOR_AREAS', ', '.join(re.findall(r'\bAREA_(?:HELLFIRE_PENINSULA|HELLFIRE_RAMPARTS|MAGTHERIDONS_LAIR|THE_BLOOD_FURNACE|THE_SHATTERED_HALLS)\s*=\s*\d+', areas))) \
   .replace('IS_DUNGEON', function(maps, 'bool IsDungeon() const')) \
   .replace('IS_RAID', function(maps, 'bool IsRaid() const'))


def build(directory, executable):
    return [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', *SANITIZER_FLAGS,
            '-I', str(directory), str(directory / 'Fixture.cpp'), '-o', str(executable)]


mutations = (
    ('double favor on kills', 'Native.cpp', 'if (!victim && (zone ==', 'if ((zone =='),
    ('raid map prerequisite', 'Native.cpp', '!_isPvP && _group->isRaidGroup()',
     '!_isPvP && sMapStore.LookupEntry(_killer->GetMapId())->IsRaid() && _group->isRaidGroup()'),
    ('double online rest', 'Native.cpp', '/ 144000.0f) *', '/ 72000.0f) *'),
    ('battleground group bonus', 'Native.cpp', 'if (!_isBattleGround)\n', 'if (true)\n'),
    ('member distance', 'Native.cpp', '_killer == member || member->IsAtGroupRewardDistance(_victim)', 'true'),
    ('resting flag', 'Native.cpp', 'if (HasPlayerFlag(PLAYER_FLAGS_RESTING))', 'if (true)'),
    ('rest tick interval', 'Native.cpp', 'if (timeDiff >= 10)', 'if (timeDiff >= 0)'),
    ('frozen rest tick', 'Native.cpp', 'now > lastTick && _restTime > 0', 'now >= lastTick && _restTime > 0'),
)
with tempfile.TemporaryDirectory(prefix='core-experience-') as temporary:
    work = Path(temporary)
    (work / 'Native.cpp').write_text(native)
    (work / 'Fixture.cpp').write_text(fixture)
    subprocess.run(build(work, work / 'fixture'), check=True)
    result = run_fixture([str(work / 'fixture')])
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout, end='')
    reject_mutants(work, mutations, build, 'Core experience')
