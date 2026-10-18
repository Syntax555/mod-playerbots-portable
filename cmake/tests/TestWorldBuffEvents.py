"""Exercise scheduled Vanilla buffs through production and native core methods.

The complete module and loader execute with the native online-player iterator,
IP milestone accessor, Unit::AddAura, duration calculation and Dragonslayer
amount/target scripts. Recording world/aura services provide isolated state;
no realm or database is started. Optional pinned DBC files verify the independent
stock spell contracts used by the fixture.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
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
    wdbc,
)


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, 'core', help='prepared core directory')
source_argument(parser, 'module', help='prepared world-buff module directory')
parser.add_argument('--baseline-repository', type=Path, help='Git cache containing the pinned upstream commit')
parser.add_argument('--spell-dbc', type=Path, help='pinned English Spell.dbc used by historical client packaging')
parser.add_argument('--duration-dbc', type=Path, help='pinned stock SpellDuration.dbc')
parser.add_argument('--era-client', type=Path, help='verified packaged EraTalents client ZIP')
parser.add_argument('--mpq-reader', type=Path, help='existing mpqread executable; otherwise build from locked sources')
args = parser.parse_args()
repository = Path(__file__).resolve().parents[2]
core = args.core or prepared_core(repository)
module = args.module or core / 'modules/mod-world-buff-bots'
baseline = args.baseline_repository or repository / '.module-cache/mod-world-buff-bots'
revision = 'baae5656aa6a375e103bc83da8262f2061dbfcb6'
lock = json.loads((repository / 'versions.lock.json').read_text())
locked = next((m for m in lock['modules'] if m['name'] == 'mod-world-buff-bots'), None)
if locked:
    assert locked['revision'] == revision

# These are independent stock records, not simulator configuration or policy.
# SpellDuration records 42/367 at Haeniken b21c949... are finite 60/120 minutes.
contracts = {
    16609: {'duration': 42, 'effects': (6, 6, 6), 'points': (299, 149, 9),
            'dice': (1, 1, 1), 'auras': (34, 189, 85), 'targetA': (22, 22, 22), 'targetB': (30, 30, 30)},
    22888: {'duration': 367, 'effects': (6, 6, 0), 'points': (139, 139, 0),
            'dice': (1, 1, 0), 'auras': (189, 99, 0), 'targetA': (22, 22, 0), 'targetB': (30, 30, 0)},
    24425: {'duration': 367, 'effects': (0, 0, 6), 'points': (0, 0, 49),
            'dice': (0, 0, 1), 'auras': (0, 0, 29), 'targetA': (0, 0, 22), 'targetB': (0, 0, 30)},
}
durations = {42: (3600000, 0, 3600000), 367: (7200000, 0, 7200000)}


def dbc_records(data, fields):
    rows, _ = wdbc(data, fields)
    records = (struct.unpack(f'<{fields}I', row) for row in rows)
    return {record[0]: record for record in records}


def verify_spell_contracts(data):
    records = dbc_records(data, 234)
    for spell_id, contract in contracts.items():
        row = records[spell_id]
        assert row[40] == contract['duration']
        for field, offset in (('effects', 71), ('dice', 74), ('points', 80),
                              ('targetA', 86), ('targetB', 89), ('auras', 95)):
            assert row[offset:offset + 3] == contract[field], (spell_id, field)


def verify_duration_contracts(data):
    records = dbc_records(data, 4)
    for index, expected in durations.items():
        actual = tuple(value if value < 2**31 else value - 2**32 for value in records[index][1:])
        assert actual == expected


if args.spell_dbc:
    donor = lock['clientPatch']['localizations']['deDE']
    assert hashlib.sha256(args.spell_dbc.read_bytes()).hexdigest() == donor['englishSpellSha256']
    verify_spell_contracts(args.spell_dbc.read_bytes())
    print('Pinned English Spell.dbc: world-buff effects, amounts and implicit targets verified')
if args.duration_dbc:
    assert hashlib.sha256(args.duration_dbc.read_bytes()).hexdigest() == \
        'caa2cbec7fa711bba180af10c253ab0d111609ec2bda1c354fef09e54bc279e4'
    verify_duration_contracts(args.duration_dbc.read_bytes())
    print('Pinned SpellDuration.dbc: native 60/120-minute lifetimes verified')
if args.era_client:
    package_spec = importlib.util.spec_from_file_location(
        'world_buff_client_package', repository / 'cmake/PackageEraClient.py')
    package = importlib.util.module_from_spec(package_spec)
    package_spec.loader.exec_module(package)
    files, manifest = package.verify_zip(args.era_client, lock)
    with tempfile.TemporaryDirectory(prefix='portable-world-buff-client-') as directory:
        temporary = Path(directory)
        reader = args.mpq_reader
        if reader is None:
            storm = temporary / 'StormLib'
            package.export_module(repository,
                                  {**lock['clientPatch']['stormLib'], 'name': 'StormLib',
                                   'source': '.module-cache/client-tools-stormlib'}, storm, 'git')
            build = temporary / 'build'
            subprocess.run(['cmake', '-S', str(repository / 'cmake/era-client-tools'), '-B', str(build),
                            '-DSTORM_SOURCE_DIR=' + str(storm),
                            '-DERA_SOURCE_DIR=' + str(core / 'modules/mod-era-talents'),
                            '-DCMAKE_BUILD_TYPE=Release'], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(['cmake', '--build', str(build), '--target', 'mpqread', '--parallel', '4'],
                           check=True, stdout=subprocess.DEVNULL)
            reader = build / 'mpqread'
        archive = temporary / 'patch-V.mpq'
        archive.write_bytes(files['Data/patch-V.mpq'])
        # The IP patch retains the stock client's SpellDuration.dbc rather
        # than shipping that table. Its independent pinned file is checked
        # with --duration-dbc; inspect the actual merged spell rows here.
        for filename, verify in (('Spell.dbc', verify_spell_contracts),):
            dbc = temporary / filename
            data = package.read_mpq(reader.resolve(), archive, 'DBFilesClient\\' + filename, dbc)
            expected_hash = (manifest['mergedDbcSha256'].get('DBFilesClient\\' + filename) or
                             manifest['preservedIpEntries'].get('DBFilesClient\\' + filename))
            assert expected_hash and hashlib.sha256(data).hexdigest() == expected_hash
            verify(data)
    print('Packaged EraTalents MPQ: native world-buff spell contracts verified')
elif args.mpq_reader:
    parser.error('--mpq-reader requires --era-client')

# AddAura bypasses implicit-target conditions, so the adapter must retain these
# exact locked native restrictions. No speculative class or faction gates.
conditions = (core / 'data/sql/base/db_world/conditions.sql').read_text()
native_conditions = {
    tuple(int(value) for value in match.group(1).split(','))
    for match in re.finditer(r'^\((13,\d+,(?:16609|22888|24425),[0-9,]+),\x27', conditions, re.MULTILINE)
}
assert native_conditions == {
    (13, 7, 16609, 0, 0, 5, 0, 76, 240, 0, 0, 0, 0),
    (13, 7, 16609, 0, 0, 6, 0, 67, 0, 0, 0, 0, 0),
    (13, 7, 16609, 0, 0, 27, 0, 63, 4, 0, 0, 0, 0),
    (13, 4, 24425, 0, 0, 27, 0, 63, 4, 0, 0, 0, 0),
}
spell_bindings = (core / 'data/sql/base/db_world/spell_script_names.sql').read_text()
assert "(22888,'spell_gen_disabled_above_63')" in spell_bindings
assert "(22888,'spell_gen_rallying_cry_of_the_dragonslayer')" in spell_bindings
scripts = (core / 'src/server/scripts/Spells/spell_generic.cpp').read_text()
assert 'RegisterSpellScript(spell_gen_disabled_above_63);' in scripts
assert 'RegisterSpellScript(spell_gen_rallying_cry_of_the_dragonslayer);' in scripts
ip_source = (core / 'modules/mod-individual-progression/src/IndividualProgression.cpp').read_text()
ip_header = (core / 'modules/mod-individual-progression/src/IndividualProgression.h').read_text()
# Spirit of Zandalar follows IP's own Zul'Gurub entry stage. The double uses
# the shipped value; the realm profile leaves the module default in place.
ip_player = (core / 'modules/mod-individual-progression/src/IndividualProgressionPlayer.cpp').read_text()
zg_gate = function(ip_player, '    static bool CanEnterMap(')
zg_gate = zg_gate[zg_gate.index('if (mapid == MAP_ZUL_GURUB)'):]
zg_gate = zg_gate[:zg_gate.index('return false;')]
assert 'sIndividualProgression->GetPlayerProgressionFromQuests(player)' in zg_gate
assert 'sIndividualProgression->RequiredZulGurubProgression' in zg_gate
assert 'if (PLAYER_PROGRESSION < REQUIRED_ZG_PROGRESSION)' in zg_gate
zg_default = int(re.search(r'GetOption<uint8>\("IndividualProgression\.RequiredZulGurubProgression", (\d+)\)',
                           ip_source).group(1))
zg_dist = (core / 'modules/mod-individual-progression/conf/individualProgression.conf.dist').read_text()
assert re.search(rf'^IndividualProgression\.RequiredZulGurubProgression = {zg_default}$', zg_dist, re.MULTILINE)
assert 'RequiredZulGurubProgression' not in (repository / 'cmd/startup/profiles/individualProgression.conf').read_text()
enum = function(ip_header, 'enum ProgressionState') + ';'
native = '\n'.join((
    function(ip_source, 'uint8 IndividualProgression::GetPlayerProgressionFromQuests('),
    function(ip_source, 'bool IndividualProgression::IsStrictDefaultProgression() const'),
    function(ip_source, 'uint8 IndividualProgression_GetEarnedEra('),
    function((core / 'src/server/game/Server/WorldSessionMgr.cpp').read_text(),
             'void WorldSessionMgr::DoForAllOnlinePlayers('),
    function((core / 'src/server/game/Entities/Unit/Unit.cpp').read_text(),
             'Aura* Unit::AddAura(uint32 spellId, Unit* target)'),
    function((core / 'src/server/game/Entities/Unit/Unit.cpp').read_text(),
             'Aura* Unit::AddAura(SpellInfo const* spellInfo, uint8 effMask, Unit* target)'),
    function((core / 'src/server/game/Spells/SpellInfo.cpp').read_text(), 'int32 SpellInfo::GetDuration() const'),
    function((core / 'src/server/game/Spells/SpellInfo.cpp').read_text(), 'int32 SpellInfo::GetMaxDuration() const'),
    function((core / 'src/server/game/Entities/Object/Object.cpp').read_text(),
             'int32 WorldObject::CalcSpellDuration('),
    function((core / 'src/server/game/Spells/Auras/SpellAuras.cpp').read_text(),
             'int32 Aura::CalcMaxDuration(Unit* caster) const'),
))
amount_script = function(scripts[scripts.index('class spell_gen_disabled_above_63'):],
                         '    void CalculateAmount(')
target_script = function(scripts[scripts.index('class spell_gen_rallying_cry_of_the_dragonslayer'):],
                         '    void SelectTarget(')
spell_script = (core / 'src/server/game/Spells/SpellScript.cpp').read_text()
# A gameobject supplies no Unit caster, including when its trap has no owner.
assert 'return m_spell->GetCaster()->ToUnit();' in function(spell_script, 'Unit* SpellScript::GetCaster()')
assert 'return m_spell->GetCaster()->ToGameObject();' in function(spell_script, 'GameObject* SpellScript::GetGObjCaster()')
area_defines = (core / 'src/server/game/Maps/AreaDefines.h').read_text()
areas = '\n'.join('constexpr uint32 ' + match.group(0).replace(',', ';')
                  for name in ('AREA_ORGRIMMAR', 'AREA_STORMWIND_CITY',
                               'AREA_STRANGLETHORN_VALE', 'AREA_THE_CROSSROADS')
                  for match in [re.search(rf'\b{name}\s*=\s*\d+,', area_defines)])

fixture = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <functional>
#include <iostream>
#include <limits>
#include <list>
#include <map>
#include <memory>
#include <set>
#include <shared_mutex>
#include <string>
#include <type_traits>
#include <vector>
using uint8 = std::uint8_t; using uint32 = std::uint32_t; using int32 = std::int32_t;
constexpr int ZG_STAGE = ZG_GATE_STAGE;
constexpr uint32 IN_MILLISECONDS = 1000, MAX_SPELL_EFFECTS = 3, MAX_EFFECT_MASK = 7;
constexpr int TEAM_ALLIANCE = 0, TEAM_HORDE = 1, REP_FRIENDLY = 4;
constexpr uint32 MAP_KALIMDOR = 1, QUEST_STATUS_NONE = 0, QUEST_STATUS_REWARDED = 6;
constexpr int SPELLMOD_DURATION = 1, SERVER_MSG_STRING = 0;
enum SpellAttr0 { SPELL_ATTR0_PASSIVE = 64 };
enum SpellAttr2 { SPELL_ATTR2_ALLOW_DEAD_TARGET = 4 };
constexpr int WORLDHOOK_ON_AFTER_CONFIG_LOAD = 1, WORLDHOOK_ON_STARTUP = 2, WORLDHOOK_ON_UPDATE = 3;
AREAS
PROGRESSION_ENUM
struct Unit; struct Player; struct Aura; struct Map;
struct SpellDurationEntry { uint32 ID; int32 Duration[3]; };
struct SpellInfo
{
    uint32 Id = 0;
    SpellDurationEntry const* DurationEntry = nullptr;
    std::array<int32, 3> amounts{};
    std::array<uint32, 3> effects{};
    bool passive = false, allowDead = true;
    bool HasAttribute(SpellAttr0) const { return passive; }
    bool HasAttribute(SpellAttr2) const { return allowDead; }
    int32 GetDuration() const;
    int32 GetMaxDuration() const;
};
struct WorldObject
{
    uint32 mapId = 0;
    Map* map = nullptr;
    virtual ~WorldObject() = default;
    virtual Unit const* ToUnit() const { return nullptr; }
    uint32 GetMapId() const { return mapId; }
    Map* GetMap() const { assert(map); return map; }
    int32 CalcSpellDuration(SpellInfo const*) const;
};
struct GameObject : WorldObject {};
struct Unit : WorldObject
{
    uint32 level = 60;
    bool alive = true, spellImmune = false;
    uint8 immuneEffects = 0;
    std::map<uint32, std::unique_ptr<Aura>> auras;
    Unit const* ToUnit() const override { return this; }
    bool IsAlive() const { return alive; }
    uint32 GetLevel() const { return level; }
    uint8 GetComboPoints() const { return 0; }
    virtual Player* GetSpellModOwner() { return nullptr; }
    bool IsImmunedToSpell(SpellInfo const*, uint8, Unit*) const { return spellImmune; }
    bool IsImmunedToSpellEffect(SpellInfo const*, uint32 index, Unit*) const
    { return (immuneEffects & (1 << index)) != 0; }
    Aura* AddAura(uint32, Unit*);
    Aura* AddAura(SpellInfo const*, uint8, Unit*);
};
struct PlayerReference { Player* source; Player* GetSource() const { return source; } };
struct Map
{
    using PlayerList = std::list<PlayerReference>;
    PlayerList players;
    PlayerList const& GetPlayers() const { return players; }
};
struct Player : Unit
{
    bool inWorld = true, gm = false;
    uint32 area = AREA_STORMWIND_CITY, zone = AREA_STORMWIND_CITY;
    int team = TEAM_ALLIANCE, reputation = REP_FRIENDLY;
    int durationModifier = 0, castCalls = 0, kind = 0, accountProgression = 18;
    uint32 money = 123456, xp = 999, inventory = 77, leaderProgression = 18;
    mutable uint32 questReads = 0;
    std::map<uint32, uint32> quests;
    bool IsInWorld() const { return inWorld; }
    bool IsGameMaster() const { return gm; }
    uint32 GetAreaId() const { return area; }
    uint32 GetZoneId() const { return zone; }
    int GetTeamId() const { return team; }
    int GetReputationRank(uint32 faction) const { assert(faction == 76); return reputation; }
    uint32 GetQuestStatus(uint32 quest) const
    {
        ++questReads;
        auto found = quests.find(quest);
        return found == quests.end() ? QUEST_STATUS_NONE : found->second;
    }
    Player* GetSpellModOwner() override { return this; }
    void ApplySpellMod(uint32, int type, int32& amount) { assert(type == SPELLMOD_DURATION); amount += durationModifier; }
    void CastSpell(Player*, uint32, bool);
};
struct IndividualProgression
{
    bool enabled = true, strictEarnedProgression = true, disableDefaultProgression = false;
    int RequiredZulGurubProgression = ZG_STAGE, progressionLimit = 0;
    std::map<uint32, uint8> customProgressionMap;
    uint8 GetPlayerProgressionFromQuests(Player*) const;
    bool IsStrictDefaultProgression() const;
} individualProgression;
#define sIndividualProgression (&individualProgression)
struct SpellManager
{
    std::map<uint32, SpellInfo> spells;
    SpellInfo const* GetSpellInfo(uint32 id) const
    { auto found = spells.find(id); return found == spells.end() ? nullptr : &found->second; }
} spellManager;
#define sSpellMgr (&spellManager)
struct ScriptManager { int durationHooks = 0; void OnCalcMaxDuration(Aura const*, int32&) { ++durationHooks; } } scriptManager;
#define sScriptMgr (&scriptManager)
struct AuraEffect {};
class NativeAmountScript
{
public:
    Unit* owner;
    Aura* aura;
    Unit* GetUnitOwner() { return owner; }
    void SetDuration(int32);
    AMOUNT_SCRIPT
};
class NativeTargetScript
{
public:
    Unit* caster = nullptr;
    GameObject* gameObjectCaster = nullptr;
    Unit* GetCaster() { return caster; }
    GameObject* GetGObjCaster() { return gameObjectCaster; }
    TARGET_SCRIPT
};
struct Aura
{
    SpellInfo const* m_spellInfo;
    Unit* owner;
    Unit* caster;
    uint8 effects;
    int32 duration = 0;
    std::array<int32, 3> amounts{};
    int applied = 0;
    bool IsPassive() const { return m_spellInfo->passive; }
    uint32 GetId() const { return m_spellInfo->Id; }
    int32 CalcMaxDuration(Unit*) const;
    void ApplyForTargets() { ++applied; }
    static Aura* TryRefreshStackOrCreate(SpellInfo const* spell, uint8 effects, Unit* owner, Unit* caster)
    {
        for (uint32 i = 0; i < MAX_SPELL_EFFECTS; ++i)
            if (!spell->effects[i]) effects &= ~(1 << i);
        if (!effects) return nullptr;
        auto& pointer = owner->auras[spell->Id];
        if (!pointer) pointer = std::make_unique<Aura>(Aura{spell, owner, caster, effects, 0, {}, 0});
        Aura* aura = pointer.get();
        aura->effects = effects;
        aura->duration = aura->CalcMaxDuration(caster);
        aura->amounts = spell->amounts;
        if (spell->Id == 22888)
        {
            NativeAmountScript script{owner, aura};
            bool canBeRecalculated = true;
            for (uint32 i = 0; i < MAX_SPELL_EFFECTS; ++i)
                if (effects & (1 << i)) script.CalculateAmount(nullptr, aura->amounts[i], canBeRecalculated);
        }
        return aura;
    }
};
void NativeAmountScript::SetDuration(int32 value) { aura->duration = value; }
namespace ObjectAccessor
{
    std::map<uint32, Player*> players;
    auto const& GetPlayers() { return players; }
}
std::shared_mutex playerMutex;
template<class T> struct HashMapHolder { static std::shared_mutex* GetLock() { return &playerMutex; } };
struct WorldSessionMgr
{
    std::vector<std::string> announcements;
    void DoForAllOnlinePlayers(std::function<void(Player*)>);
    void SendServerMessage(int, std::string const& message) { announcements.push_back(message); }
} worldSessionManager;
#define sWorldSessionMgr (&worldSessionManager)
struct Config
{
    std::map<std::string, uint32> numeric;
    std::map<std::string, std::string> strings;
    template<class T> T GetOption(std::string const& name, T fallback)
    {
        if constexpr (std::is_same_v<T, std::string>)
        { auto found = strings.find(name); return found == strings.end() ? fallback : found->second; }
        else
        { auto found = numeric.find(name); return found == numeric.end() ? fallback : T(found->second); }
    }
} config;
#define sConfigMgr (&config)
struct RandomRequest { uint32 lower, upper; };
std::vector<RandomRequest> randomRequests;
std::list<uint32> randomValues;
uint32 urand(uint32 lower, uint32 upper)
{
    assert(lower <= upper);
    randomRequests.push_back({lower, upper});
    if (randomValues.empty()) return lower;
    uint32 result = randomValues.front(); randomValues.pop_front();
    assert(result >= lower && result <= upper);
    return result;
}
std::vector<void*> registeredScripts;
struct WorldScript
{
    std::string name;
    std::vector<int> hooks;
    WorldScript(char const* value, std::vector<int> enabled) : name(value), hooks(std::move(enabled))
    { registeredScripts.push_back(this); }
    virtual ~WorldScript() = default;
    virtual void OnAfterConfigLoad(bool) {}
    virtual void OnStartup() {}
    virtual void OnUpdate(uint32) {}
};
template<class... T> void IgnoreLog(T const&...) {}
#define LOG_INFO(...) IgnoreLog(__VA_ARGS__)
NATIVE_METHODS
void Player::CastSpell(Player*, uint32 spellId, bool triggered)
{
    assert(triggered);
    ++castCalls;
    if (spellId == 22888)
    {
        NativeTargetScript script{this};
        std::list<WorldObject*> targets;
        script.SelectTarget(targets);
        for (WorldObject* target : targets) AddAura(spellId, static_cast<Player*>(target));
    }
    else
        AddAura(spellId, this);
}
'''

tests = r'''
struct Scenario
{
    std::vector<std::unique_ptr<Player>> players;
    Map map;
    WorldBuffBotsWorldScript script;
    Scenario()
    {
        individualProgression = {};
        config = {};
        scriptManager = {};
        worldSessionManager.announcements.clear();
        ObjectAccessor::players.clear();
        randomRequests.clear(); randomValues.clear();
        config.numeric["WorldBuffBots.InitialMinMinutes"] = 1;
        config.numeric["WorldBuffBots.InitialMaxMinutes"] = 1;
        config.numeric["WorldBuffBots.BaseMinutes"] = 1;
        config.numeric["WorldBuffBots.VarianceMinutes"] = 0;
    }
    ~Scenario() { ObjectAccessor::players.clear(); }
    Player& Add(uint32 zone = AREA_STORMWIND_CITY, uint32 level = 60, int kind = 0)
    {
        auto player = std::make_unique<Player>();
        player->zone = player->area = zone;
        player->level = level;
        player->kind = kind;
        player->map = &map;
        Player& result = *player;
        ObjectAccessor::players[uint32(players.size())] = &result;
        map.players.push_back({&result});
        players.push_back(std::move(player));
        return result;
    }
    void Only(char const* event)
    {
        for (char const* key : {"Warchief", "Dragonslayer", "Zandalar"})
            config.numeric[std::string("WorldBuffBots.") + key + ".Enable"] = std::string(key) == event;
    }
    void Start()
    {
        script.OnAfterConfigLoad(false);
        script.OnStartup();
    }
};
void InitializeSpells()
{
    static SpellDurationEntry oneHour{42, {3600000, 0, 3600000}};
    static SpellDurationEntry twoHours{367, {7200000, 0, 7200000}};
    spellManager.spells.clear();
    spellManager.spells.emplace(16609, SpellInfo{16609, &oneHour, {300, 150, 10}, {6, 6, 6}});
    spellManager.spells.emplace(22888, SpellInfo{22888, &twoHours, {140, 140, 0}, {6, 6, 0}});
    spellManager.spells.emplace(24425, SpellInfo{24425, &twoHours, {0, 0, 50}, {0, 0, 6}});
}
void Mark(Player& player, uint8 stage, uint32 status = QUEST_STATUS_REWARDED)
{
    player.quests.clear();
    if (stage) player.quests[66000 + stage] = status;
}
void ExpectAura(Player const& player, uint32 spell, bool expected)
{
    assert(player.auras.contains(spell) == expected);
    assert(player.castCalls == 0);
    if (expected) assert(player.auras.at(spell)->applied == 1);
}
void NativeCasterTargets()
{
    for (uint32 mapId : {0U, MAP_KALIMDOR})
    {
        Scenario s;
        Player& city = s.Add(mapId == MAP_KALIMDOR ? AREA_ORGRIMMAR : AREA_STORMWIND_CITY);
        Player& outside = s.Add(17);
        city.mapId = outside.mapId = mapId;
        Unit npc; npc.mapId = mapId; npc.map = &s.map;
        NativeTargetScript unitScript{&npc};
        std::list<WorldObject*> targets{&outside};
        unitScript.SelectTarget(targets);
        assert(targets == std::list<WorldObject*>{&city});

        GameObject ownerlessTrap; ownerlessTrap.mapId = mapId; ownerlessTrap.map = &s.map;
        NativeTargetScript trapScript{nullptr, &ownerlessTrap};
        assert(!trapScript.GetCaster() && trapScript.GetGObjCaster() == &ownerlessTrap);
        targets = {&outside};
        trapScript.SelectTarget(targets);
        assert(targets == std::list<WorldObject*>{&city});

        NativeTargetScript missingCaster;
        targets = {&city};
        missingCaster.SelectTarget(targets);
        assert(targets.empty());
    }
}
void SpillRegression()
{
    Scenario s; s.Only("Dragonslayer");
    Player& vanilla = s.Add(AREA_STORMWIND_CITY, 20);
    Player& tbc = s.Add(AREA_STORMWIND_CITY, 20, 1); Mark(tbc, 8);
    Player& wrath = s.Add(AREA_STORMWIND_CITY, 20, 2); Mark(wrath, 13);
    Player& gm = s.Add(); gm.gm = true;
    s.Start(); s.script.OnUpdate(60000);
    assert(!tbc.auras.contains(22888));
    assert(!wrath.auras.contains(22888));
    assert(!gm.auras.contains(22888));
    assert(vanilla.auras.contains(22888) && vanilla.auras.at(22888)->applied == 1);
    assert(vanilla.castCalls == 0);
}
void EarnedEraAndNativeGates()
{
    uint32 cases = 0;
    for (uint32 spell : {16609, 22888, 24425})
    for (uint8 stage = 0; stage <= 18; ++stage)
    for (uint32 level : {1, 20, 60, 63, 64, 70, 80})
    for (int kind = 0; kind < 4; ++kind)
    for (int team : {TEAM_ALLIANCE, TEAM_HORDE})
    for (int reputation : {0, 3, 4, 7})
    {
        Scenario s;
        char const* key = spell == 16609 ? "Warchief" : spell == 22888 ? "Dragonslayer" : "Zandalar";
        s.Only(key);
        uint32 zone = spell == 16609 ? AREA_ORGRIMMAR : spell == 22888 ? AREA_STORMWIND_CITY : AREA_STRANGLETHORN_VALE;
        Player& p = s.Add(zone, level, kind); Mark(p, stage);
        p.team = team; p.reputation = reputation;
        auto quests = p.quests;
        s.Start(); s.script.OnUpdate(60000);
        bool expected = stage < 8 && level <= 63 && (spell != 16609 || (team == TEAM_HORDE && reputation >= 4)) &&
                        (spell != 24425 || stage >= ZG_STAGE);
        ExpectAura(p, spell, expected);
        assert(p.quests == quests && p.money == 123456 && p.xp == 999 && p.inventory == 77);
        assert(p.accountProgression == 18 && p.leaderProgression == 18);
        assert(p.questReads <= (spell == 24425 ? 36U : 18U));
        ++cases;
    }
    std::cout << "World buffs: " << cases << " earned-era, level, faction, reputation and human/alt/random/SelfBot cases passed\n";
}
void RegionsEligibilityAndNativeAura()
{
    for (uint32 spell : {16609, 22888, 24425})
    for (uint32 state = 0; state < 7; ++state)
    {
        Scenario s;
        s.Only(spell == 16609 ? "Warchief" : spell == 22888 ? "Dragonslayer" : "Zandalar");
        uint32 zone = spell == 16609 ? AREA_ORGRIMMAR : spell == 22888 ? AREA_STORMWIND_CITY : AREA_STRANGLETHORN_VALE;
        Player& p = s.Add(zone); p.team = TEAM_HORDE; Mark(p, ZG_STAGE);
        switch (state)
        {
            case 0: p.alive = false; break;
            case 1: p.gm = true; break;
            case 2: p.inWorld = false; break;
            case 3: p.zone = p.area = 17; break;
            case 4: p.spellImmune = true; break;
            case 5: p.area = 999; break;
            case 6: p.zone = 999; break;
        }
        s.Start(); s.script.OnUpdate(60000);
        ExpectAura(p, spell, state >= 5);
    }
    {
        Scenario s; s.Only("Zandalar"); Player& p = s.Add(); p.area = 35; p.zone = AREA_STRANGLETHORN_VALE;
        Mark(p, ZG_STAGE); s.Start(); s.script.OnUpdate(60000); ExpectAura(p, 24425, true);
    }
    {
        Scenario s; s.Only("Dragonslayer"); Player& p = s.Add(AREA_ORGRIMMAR); p.team = TEAM_HORDE;
        s.Start(); s.script.OnUpdate(60000); ExpectAura(p, 22888, false);
    }
    for (uint32 level : {1, 20, 60, 63})
    {
        Scenario s; s.Only("Dragonslayer"); Player& p = s.Add(AREA_STORMWIND_CITY, level);
        s.Start(); s.script.OnUpdate(60000);
        assert(p.auras.at(22888)->amounts[0] == int32(140 * level / 60));
        assert(p.auras.at(22888)->amounts[1] == int32(140 * level / 60));
        assert(p.auras.at(22888)->duration == 7200000 && p.auras.at(22888)->effects == 3);
    }
    {
        Scenario s; s.Only("Warchief"); Player& p = s.Add(AREA_ORGRIMMAR); p.team = TEAM_HORDE;
        p.immuneEffects = 2; p.durationModifier = 123;
        s.Start(); s.script.OnUpdate(60000);
        assert(p.auras.at(16609)->effects == 5 && p.auras.at(16609)->duration == 3600123);
        assert((p.auras.at(16609)->amounts == std::array<int32, 3>{300, 150, 10}));
        assert(scriptManager.durationHooks == 1);
        assert(!p.AddAura(999999, &p)); assert(!p.AddAura(16609, nullptr));
    }
    {
        Scenario s; s.Only("Zandalar"); Player& p = s.Add(AREA_STRANGLETHORN_VALE); Mark(p, ZG_STAGE);
        s.Start(); s.script.OnUpdate(60000);
        assert(p.auras.at(24425)->amounts[2] == 50 && p.auras.at(24425)->duration == 7200000);
        assert(p.auras.at(24425)->effects == 4);
        s.script.OnUpdate(60000);
        assert(p.auras.size() == 1 && p.auras.at(24425)->applied == 2);
        assert(p.auras.at(24425)->duration == 7200000);
    }
    {
        Player p; p.level = 64; p.AddAura(22888, &p);
        assert(p.auras.at(22888)->duration == 1); // untouched native above-level AuraScript
    }
}
void StrictDefaultAndOwnMilestones()
{
    for (uint32 state = 0; state < 4; ++state)
    {
        Scenario s; s.Only("Dragonslayer"); Player& p = s.Add();
        switch (state)
        {
            case 0: individualProgression.enabled = false; break;
            case 1: individualProgression.strictEarnedProgression = false; break;
            case 2: individualProgression.disableDefaultProgression = true; break;
            case 3: individualProgression.customProgressionMap[11583] = 1; break;
        }
        s.Start(); s.script.OnUpdate(60000);
        ExpectAura(p, 22888, false);
        assert(p.questReads == 0 && worldSessionManager.announcements.empty());
    }
    for (uint32 status : {0U, 1U, 2U, 3U, 4U, 5U, QUEST_STATUS_REWARDED})
    {
        Scenario s; s.Only("Dragonslayer"); Player& p = s.Add(); Mark(p, 8, status);
        s.Start(); s.script.OnUpdate(60000); ExpectAura(p, 22888, status != QUEST_STATUS_REWARDED);
    }
    {
        Scenario s; s.Only("Dragonslayer"); Player& p = s.Add(); Mark(p, 7);
        Player& master = s.Add(); Mark(master, 18); master.level = p.level;
        s.Start(); s.script.OnUpdate(60000); ExpectAura(p, 22888, true); ExpectAura(master, 22888, false);
    }
}
void RealmCeiling()
{
    for (int ceiling : {0, 1, 7, 8, 12, 13, 18})
    for (uint8 stage = 0; stage <= 18; ++stage)
    {
        Scenario s; s.Only("Dragonslayer");
        individualProgression.progressionLimit = ceiling;
        Player& p = s.Add(); Mark(p, stage);
        s.Start(); s.script.OnUpdate(60000);
        ExpectAura(p, 22888, stage < 8 || (ceiling > 0 && ceiling < 8));
    }
}
void ZulGurubStage()
{
    for (uint8 stage = 0; stage < 8; ++stage)
    {
        Scenario s; s.Only("Zandalar"); Player& p = s.Add(AREA_STRANGLETHORN_VALE); Mark(p, stage);
        Player& city = s.Add(); Mark(city, stage);
        config.numeric["WorldBuffBots.Dragonslayer.Enable"] = 1;
        s.Start(); s.script.OnUpdate(60000);
        ExpectAura(p, 24425, stage >= ZG_STAGE);
        ExpectAura(city, 22888, true); // Rallying Cry needs no Zul'Gurub stage
    }
    for (int required : {0, 5})
    for (uint8 stage : {0, 4, 5})
    {
        Scenario s; s.Only("Zandalar"); individualProgression.RequiredZulGurubProgression = required;
        Player& p = s.Add(AREA_STRANGLETHORN_VALE); Mark(p, stage);
        s.Start(); s.script.OnUpdate(60000);
        ExpectAura(p, 24425, stage >= required);
    }
    std::cout << "Spirit of Zandalar follows each recipient's own Zul'Gurub stage\n";
}
void TimersDelayedRecipientsAndReload()
{
    {
        Scenario s;
        config.numeric.clear();
        randomValues = {30, 90, 150};
        s.Start();
        assert(randomValues.empty());
        for (uint32 i = 0; i < 3; ++i)
            assert(randomRequests[i].lower == 30 && randomRequests[i].upper == 150);
        s.script.OnUpdate(30U * 60000U - 1);
        assert(worldSessionManager.announcements.empty());
        s.script.OnUpdate(1);
        assert(worldSessionManager.announcements.size() == 1);
        assert(randomRequests.back().lower == 30 && randomRequests.back().upper == 150);
    }
    {
        Scenario s; Player& p = s.Add();
        randomValues = {1, 2, 3}; config.numeric["WorldBuffBots.InitialMaxMinutes"] = 3;
        s.Start(); assert(randomValues.empty());
        s.script.OnUpdate(0); assert(worldSessionManager.announcements.empty() && p.questReads == 0);
        s.script.OnUpdate(59999); assert(worldSessionManager.announcements.empty());
        s.script.OnUpdate(1); assert(worldSessionManager.announcements.size() == 1);
        assert(p.auras.empty());
        s.script.OnUpdate(60000); assert(worldSessionManager.announcements.size() == 3);
        ExpectAura(p, 22888, true);
        s.script.OnUpdate(60000); assert(worldSessionManager.announcements.size() == 6);
        assert(worldSessionManager.announcements[0] == "World buff: Warchief's Blessing is available in Orgrimmar.");
    }
    {
        Scenario s; s.Only("Warchief");
        Player& crossroads = s.Add(17); crossroads.area = AREA_THE_CROSSROADS; crossroads.team = TEAM_HORDE;
        Player& barrens = s.Add(17); barrens.team = TEAM_HORDE;
        Player& transitioned = s.Add(17); transitioned.area = AREA_THE_CROSSROADS; transitioned.team = TEAM_HORDE;
        s.Start(); s.script.OnUpdate(60000);
        assert(crossroads.auras.empty());
        Mark(transitioned, 8);
        s.script.OnUpdate(9999); assert(crossroads.auras.empty());
        s.script.OnUpdate(1); ExpectAura(crossroads, 16609, true);
        ExpectAura(barrens, 16609, false); ExpectAura(transitioned, 16609, false);
    }
    {
        Scenario s; s.Only("Warchief"); Player& p = s.Add(17); p.area = AREA_THE_CROSSROADS; p.team = TEAM_HORDE;
        s.Start(); s.script.OnUpdate(60000);
        config.numeric["WorldBuffBots.InitialMinMinutes"] = 2; config.numeric["WorldBuffBots.InitialMaxMinutes"] = 2;
        s.script.OnAfterConfigLoad(true); s.script.OnUpdate(10000); assert(p.auras.empty());
        s.script.OnUpdate(110000); assert(p.auras.empty());
        s.script.OnUpdate(10000); ExpectAura(p, 16609, true);
    }
    {
        Scenario s; s.Only("Warchief"); Player& p = s.Add(17); p.area = AREA_THE_CROSSROADS; p.team = TEAM_HORDE;
        config.numeric["WorldBuffBots.Warchief.IncludeCrossroads"] = 0;
        s.Start(); s.script.OnUpdate(60000); s.script.OnUpdate(10000); assert(p.auras.empty());
    }
    for (char const* option : {"WorldBuffBots.Enable", "WorldBuffBots.Dragonslayer.Enable"})
    {
        Scenario s; s.Only("Dragonslayer"); Player& p = s.Add(); config.numeric[option] = 0;
        s.Start(); s.script.OnUpdate(60000); assert(p.auras.empty() && worldSessionManager.announcements.empty());
    }
    {
        Scenario s; s.Only("Warchief"); Player& p = s.Add(17); p.area = AREA_THE_CROSSROADS; p.team = TEAM_HORDE;
        s.Start(); s.script.OnUpdate(60000); individualProgression.enabled = false;
        s.script.OnUpdate(10000); individualProgression.enabled = true;
        s.script.OnUpdate(1); assert(p.auras.empty());
    }
    for (char const* option : {"WorldBuffBots.Enable", "WorldBuffBots.Warchief.Enable"})
    {
        Scenario s; s.Only("Warchief"); Player& p = s.Add(17); p.area = AREA_THE_CROSSROADS; p.team = TEAM_HORDE;
        s.Start(); s.script.OnUpdate(60000);
        config.numeric[option] = 0; s.script.OnAfterConfigLoad(true);
        s.script.OnUpdate(10000); assert(p.auras.empty());
        s.script.OnUpdate(60000); assert(p.auras.empty());
        assert(worldSessionManager.announcements.size() == 1);
    }
    {
        Scenario s; s.Only("Dragonslayer"); Player& p = s.Add();
        s.Start(); s.script.OnUpdate(60000 - 1); Mark(p, 8); s.script.OnUpdate(1); ExpectAura(p, 22888, false);
    }
    {
        Scenario s; s.Only("Dragonslayer");
        config.numeric["WorldBuffBots.InitialMinMinutes"] = 0; config.numeric["WorldBuffBots.InitialMaxMinutes"] = 0;
        config.numeric["WorldBuffBots.BaseMinutes"] = std::numeric_limits<uint32>::max();
        config.numeric["WorldBuffBots.VarianceMinutes"] = std::numeric_limits<uint32>::max();
        s.Start(); assert(randomRequests[0].lower == 1 && randomRequests[0].upper == 1);
        s.script.OnUpdate(60000);
        assert(randomRequests.back().lower == 1 && randomRequests.back().upper == 71582);
        assert(MinutesToMs(std::numeric_limits<uint32>::max()) == 71582U * 60000U);
    }
    {
        Scenario s; config.numeric["WorldBuffBots.InitialMinMinutes"] = 9; config.numeric["WorldBuffBots.InitialMaxMinutes"] = 2;
        s.Start(); assert(randomRequests[0].lower == 2 && randomRequests[0].upper == 9);
    }
}
void CustomizedAnnouncements()
{
    for (char const* event : {"Warchief", "Dragonslayer", "Zandalar"})
    for (uint32 faction = 0; faction < 2; ++faction)
    {
        Scenario s; s.Only(event);
        std::string key = std::string("WorldBuffBots.") + event + ".Announcement";
        config.strings[key] = "{player}: {buff} / %s / {player}";
        s.Start();
        bool either = std::string(event) == "Zandalar";
        bool horde = std::string(event) == "Warchief" || (either && faction == 1);
        char const* announcer = horde ? "Kazra" : "Vaelora";
        char const* buff = std::string(event) == "Warchief" ? "Warchief's Blessing" :
                           std::string(event) == "Dragonslayer" ? "Rallying Cry of the Dragonslayer" : "Spirit of Zandalar";
        if (either) randomValues.push_back(faction);
        randomValues.push_back(23);
        s.script.OnUpdate(60000);
        assert(randomValues.empty());
        assert(worldSessionManager.announcements.size() == 1);
        assert(worldSessionManager.announcements.back() ==
               std::string(announcer) + ": " + buff + " / " + announcer + " / " + announcer);
        assert(config.strings[key] == "{player}: {buff} / %s / {player}");

        config.strings[key] = "%s";
        s.script.OnAfterConfigLoad(true);
        if (either) randomValues.push_back(faction);
        randomValues.push_back(23);
        s.script.OnUpdate(60000);
        assert(randomValues.empty() && worldSessionManager.announcements.back() == announcer);
    }
    {
        Scenario s; s.Only("Dragonslayer");
        config.strings["WorldBuffBots.Dragonslayer.Announcement"] = "{buff} in Stormwind";
        s.Start();
        auto requests = randomRequests.size();
        s.script.OnUpdate(60000);
        assert(randomRequests.size() == requests + 1); // next timer, no unused announcer
        assert(worldSessionManager.announcements.back() == "Rallying Cry of the Dragonslayer in Stormwind");
    }
}
void LoaderAndScope()
{
    registeredScripts.clear(); Addmod_world_buff_botsScripts();
    assert(registeredScripts.size() == 1);
    auto script = std::unique_ptr<WorldScript>(static_cast<WorldScript*>(registeredScripts[0]));
    assert(script->name == "WorldBuffBotsWorldScript");
    assert((script->hooks == std::vector<int>{WORLDHOOK_ON_AFTER_CONFIG_LOAD, WORLDHOOK_ON_STARTUP, WORLDHOOK_ON_UPDATE}));
    Scenario s; Player& p = s.Add(3703); Mark(p, 8);
    s.Start(); s.script.OnUpdate(60000);
    assert(p.auras.empty() && p.quests.at(66008) == QUEST_STATUS_REWARDED);
    assert(p.money == 123456 && p.xp == 999 && p.inventory == 77);
}
void OneAuraPerEligibleOnlinePlayer()
{
    Scenario s; s.Only("Dragonslayer");
    for (uint32 i = 0; i < 4096; ++i)
    {
        Player& p = s.Add();
        if (i % 2) Mark(p, 8);
    }
    ObjectAccessor::players[5000] = nullptr;
    s.Start(); s.script.OnUpdate(60000);
    for (uint32 i = 0; i < s.players.size(); ++i)
        ExpectAura(*s.players[i], 22888, !(i % 2));
    assert(scriptManager.durationHooks == 2048);
}
int main(int argc, char**)
{
    InitializeSpells();
    NativeCasterTargets();
    SpillRegression();
    if (argc > 1) return 0;
    EarnedEraAndNativeGates(); RegionsEligibilityAndNativeAura(); StrictDefaultAndOwnMilestones(); RealmCeiling(); ZulGurubStage();
    TimersDelayedRecipientsAndReload(); CustomizedAnnouncements(); LoaderAndScope(); OneAuraPerEligibleOnlinePlayer();
    std::cout << "World-buff native iterator, strict progression, no area spill, aura amounts/durations, immunity, scheduling, delayed rechecks and reload passed\n";
}
'''

fixture = fixture.replace('AREAS', areas).replace('PROGRESSION_ENUM', enum)
fixture = fixture.replace('ZG_GATE_STAGE', str(zg_default))
fixture = fixture.replace('AMOUNT_SCRIPT', amount_script).replace('TARGET_SCRIPT', target_script)
fixture = fixture.replace('NATIVE_METHODS', native)
environment = {**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1:abort_on_error=1',
               'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'}
with tempfile.TemporaryDirectory(prefix='portable-world-buff-events-') as directory:
    temporary = Path(directory)
    for name in ('AreaDefines.h', 'Config.h', 'IndividualProgression.h', 'Log.h', 'Player.h',
                 'Random.h', 'ScriptMgr.h', 'World.h', 'WorldSessionMgr.h'):
        (temporary / name).write_text('#pragma once\n')
    production = (module / 'src/WorldBuffBots.cpp').read_text()
    loader = (module / 'src/world_buff_bots_loader.cpp').read_text()
    baseline_source = subprocess.check_output(['git', '-C', str(baseline), 'show',
                                              revision + ':src/WorldBuffBots.cpp'], text=True)
    baseline_loader = subprocess.check_output(['git', '-C', str(baseline), 'show',
                                              revision + ':src/world_buff_bots_loader.cpp'], text=True)
    mutations = (
        ('city-area-cast', '            if (player->AddAura(spellId, player))\n                ++appliedCount;',
         '            player->CastSpell(player, spellId, true);\n            ++appliedCount;',
         '!tbc.auras.contains(22888)'),
        ('era-gate', 'if (IndividualProgression_GetEarnedEra(player) != 0)', 'if (false)', '!tbc.auras.contains(22888)'),
        ('zandalar-stage-gate', 'sIndividualProgression->GetPlayerProgressionFromQuests(player) < sIndividualProgression->RequiredZulGurubProgression',
         'false', 'player.auras.contains(spell) == expected'),
        ('level-gate', 'player->GetLevel() > MAX_VANILLA_BUFF_LEVEL',
         'false', 'player.auras.contains(spell) == expected'),
        ('custom-announcer', 'ReplaceAll(message, "{player}", announcerName);',
         '', 'worldSessionManager.announcements.back() =='),
        ('legacy-announcer', 'ReplaceAll(message, "%s", announcerName);',
         '', 'worldSessionManager.announcements.back() =='),
    )
    variants = [('patched', production, loader, None),
                ('baseline', baseline_source, baseline_loader, '!tbc.auras.contains(22888)')]
    for name, old, replacement, assertion in mutations:
        assert production.count(old) == 1, name
        variants.append((name, production.replace(old, replacement), loader, assertion))

    def build_and_run(variant):
        name, source_text, loader_text, _ = variant
        source = temporary / (name + '.cpp')
        source.write_text(fixture + '\n' + source_text + '\n' + loader_text + '\n' + tests)
        executable = temporary / name
        subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-g', '-O1',
                        *SANITIZER_FLAGS, '-no-pie',
                        '-I', str(temporary), str(source), '-o', str(executable)], check=True)
        return run_fixture([str(executable)], env=environment)

    for (name, *_, expected_failure), result in zip(variants, in_parallel(build_and_run, variants)):
        if expected_failure is None:
            print(result.stdout + result.stderr, end='')
            assert result.returncode == 0, name
        else:
            assert result.returncode != 0 and expected_failure in result.stderr, result
            print(name + ': the unsafe variant fails its gameplay regression as expected')
