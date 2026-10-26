"""Exercise actual Playerbots combat profiles without granting talents or gear.

The native class/role builders run against inventory-independent engines. Profile
selection, talent-tab detection and the saved value run with native-shaped
character/context doubles; mutation checks keep the combat and ownership gates.
"""

import argparse
from pathlib import Path
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    TIMEOUT,
    cxx,
    function,
    in_parallel,
    prepared_core,
    source_argument,
)


ROOT = Path(__file__).resolve().parents[2]

CPP = r'''
#include <algorithm>
#include <array>
#include <atomic>
#include <type_traits>
#include <cassert>
#include <cstdarg>
#include <cstdint>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <tuple>
#include <utility>
#include <vector>
using uint8 = std::uint8_t;
using int8 = std::int8_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
using int32 = std::int32_t;
@ENUMS@
constexpr uint32 SPELL_FROSTFIRE_BOLT = 44614, SPELL_ICE_SHARDS = 15047,
    SPELL_WHIRLWIND = 1680, SPELL_CAT_FORM = 768, SPELL_DRUID_THICK_HIDE = 16931,
    SPELL_DK_FROST_PRESENCE = 48263;
constexpr uint8 FORM_BEAR = 5, FORM_DIREBEAR = 8;
enum BotState { BOT_STATE_COMBAT, BOT_STATE_NON_COMBAT, BOT_STATE_DEAD, BOT_STATE_MAX };
enum { STRATEGY_TYPE_TANK = 1, STRATEGY_TYPE_HEAL = 2, STRATEGY_TYPE_DPS = 4,
       STRATEGY_TYPE_RANGED = 8, STRATEGY_TYPE_MELEE = 16 };
struct Player;
struct PlayerbotAI;
struct Group {};
struct Session { bool loggingOut = false; bool IsLoggingOut() const { return loggingOut; } };
struct Event {};

struct Engine {
    std::set<std::string> strategies;
    int initCalls = 0;
    bool addStrategy(std::string const& name, bool = false) { return strategies.insert(name).second; }
    void addStrategiesNoInit(char const* first, ...) {
        va_list names;
        va_start(names, first);
        for (char const* name = first; name; name = va_arg(names, char const*)) strategies.insert(name);
        va_end(names);
    }
    bool removeStrategy(std::string const& name, bool = false) { return strategies.erase(name) != 0; }
    bool HasStrategy(std::string const& name) const { return strategies.contains(name); }
    void Init() { ++initCalls; }
};

struct SavedString {
    std::string value = "auto";
    std::string Get() const { return value; }
    void Set(std::string const& text) { value = text; }
};
struct AiObjectContext {
    SavedString profile;
    template<class T> SavedString* GetValue(std::string const& name) {
        static_assert(std::is_same_v<T, std::string>);
        assert(name == "combat profile");
        return &profile;
    }
};
struct PlayerTalent { uint8 specMask = 1; };
using PlayerTalentMap = std::map<uint32, PlayerTalent*>;
struct TalentSpellPos { uint32 talent_id = 0; };
struct TalentEntry { uint32 TalentTab = 0; };
struct TalentStore {
    std::map<uint32, TalentEntry> entries;
    TalentEntry const* LookupEntry(uint32 id) const {
        auto found = entries.find(id);
        return found == entries.end() ? nullptr : &found->second;
    }
} sTalentStore;
struct SpellInfo { uint32 rank = 1; uint32 GetRank() const { return rank; } };
struct SpellMgr {
    std::map<uint32, SpellInfo> entries;
    SpellInfo const* GetSpellInfo(uint32 id) const {
        auto found = entries.find(id);
        return found == entries.end() ? nullptr : &found->second;
    }
} spellMgr;
auto* sSpellMgr = &spellMgr;
std::map<uint32, TalentSpellPos> talentPositions;
TalentSpellPos const* GetTalentSpellPos(uint32 spell) {
    auto found = talentPositions.find(spell);
    return found == talentPositions.end() ? nullptr : &found->second;
}
uint32 const* GetTalentTabPages(uint8) { static uint32 const pages[] = {10, 11, 12}; return pages; }

struct Player {
    uint8 cls = CLASS_WARRIOR, level = 60, activeSpec = 0, form = 0, era = 2;
    bool combat = false, alive = true, world = true, self = false, random = false;
    bool battleground = false, managed = false, teleported = false;
    uint32 map = 0;
    Group* group = nullptr;
    PlayerbotAI* ai = nullptr;
    Session session;
    bool hasSession = true, removing = false;
    std::array<uint32, 3> eraTabs{};
    int feralSeed = -1;
    std::set<uint32> spells, auras;
    PlayerTalentMap talents;
    uint8 getClass() const { return cls; }
    uint8 GetLevel() const { return level; }
    uint8 GetActiveSpec() const { return activeSpec; }
    uint8 GetActiveSpecMask() const { return 1 << activeSpec; }
    uint8 GetShapeshiftForm() const { return form; }
    PlayerTalentMap const& GetTalentMap() const { return talents; }
    std::set<uint32> const& GetSpellMap() const { return spells; }
    bool HasSpell(uint32 spell) const { return spells.contains(spell); }
    bool HasAura(uint32 spell) const { return spell && auras.contains(spell); }
    Session* GetSession() { return hasSession ? &session : nullptr; }
    bool IsDuringRemoveFromWorld() const { return removing; }
    bool IsInCombat() const { return combat; }
    bool IsAlive() const { return alive; }
    bool IsInWorld() const { return world; }
    bool InBattleground() const { return battleground; }
    bool IsBeingTeleported() const { return teleported; }
    uint32 GetMapId() const { return map; }
    Group* GetGroup() const { return group; }
};
#define GET_PLAYERBOT_AI(player) ((player)->ai)
int EraTalentBots_FeralSpec(Player* player) { return player->feralSeed; }
bool EraTalentBots_SpecTabs(Player* player, uint32* tabs) {
    if (!player->managed) return false;
    std::copy(player->eraTabs.begin(), player->eraTabs.end(), tabs);
    return true;
}
uint32 EraTalentBots_ResolveSpellId(Player* player, uint32 spell) {
    return player->spells.contains(spell) || player->auras.contains(spell) ? spell : 0;
}
uint32 EraKnown(Player* player, uint32 spell) { return EraTalentBots_ResolveSpellId(player, spell); }
bool IsSelfBot(Player* player) { return player->self; }
struct RandomPlayerbotMgr { bool IsRandomBot(Player* player) const { return player->random; } } sRandomPlayerbotMgr;
struct Config {
    bool AutoSaveMana = true;
    bool restricted = false;
    bool IsRestrictedHealerDPSMap(uint32) const { return restricted; }
} sPlayerbotAIConfig;

class AiFactory {
public:
    static std::vector<std::string> GetCombatProfiles(uint8 cls);
    static std::string GetCombatProfile(Player* player);
    static std::string GetEffectiveCombatProfile(Player* player);
    static bool SetCombatProfile(Player* player, std::string const& profile);
    static bool IsFeralTank(Player* player);
    static uint8 GetPlayerSpecTab(Player* player);
    static BotRoles GetPlayerRoles(Player* player);
    static std::map<uint8, uint32> GetPlayerSpecTabs(Player* player);
    static void AddClassCombatStrategies(Player*, PlayerbotAI*, Engine*);
    static void AddClassNonCombatStrategies(Player*, PlayerbotAI*, Engine*);
    static void RefreshCombatStrategies(Player*, PlayerbotAI*, Engine*, Engine*);
};
struct PlayerbotAI {
    Player* bot;
    AiObjectContext context;
    AiObjectContext* aiObjectContext = &context;
    Engine combat, nonCombat;
    Engine* engines[BOT_STATE_MAX] = {&combat, &nonCombat, nullptr};
    int equips = 0;
    uint32 nextAICheckDelay = 0, combatProfileCheckDelay = 0;
    std::atomic_bool combatProfileDirty = true;
    std::string combatProfileKey;
    explicit PlayerbotAI(Player& player) : bot(&player) { player.ai = this; }
    Player* GetBot() const { return bot; }
    AiObjectContext* GetAiObjectContext() { return aiObjectContext; }
    bool ContainsStrategy(uint32) const { return false; }
    bool DoSpecificAction(std::string const& name, Event, bool silent) {
        assert(name == "equip upgrade" && silent && !bot->IsInCombat());
        ++equips;
        return true;
    }
    static bool IsTank(Player* player, bool bySpec = false);
    static bool IsHeal(Player* player, bool bySpec = false);
    static bool IsDps(Player* player, bool bySpec = false);
    static bool IsRanged(Player* player, bool bySpec = false);
    static bool IsMelee(Player* player, bool bySpec = false);
    void UpdateAI(uint32 elapsed, bool minimal = false);
    void RefreshCombatProfile(bool force = false);
    void InvalidateCombatProfile() { combatProfileDirty.store(true, std::memory_order_relaxed); }
};
struct PlayerbotRepository {
    int saves = 0;
    std::string saved;
    static PlayerbotRepository& instance() { static PlayerbotRepository repository; return repository; }
    void Save(PlayerbotAI* ai) { ++saves; saved = ai->context.profile.Get(); }
};

template<class T> class ManualSetValue {
protected:
    T value;
    Player* bot;
public:
    ManualSetValue(PlayerbotAI* ai, T initial, std::string const&) : value(initial), bot(ai->GetBot()) {}
    virtual ~ManualSetValue() = default;
    virtual std::string const Save() { return {}; }
    virtual bool Load(std::string const) { return false; }
    T Get() const { return value; }
};
@SAVED_VALUE@
@PRODUCTION@

int main() {
    @TESTS@
    std::cout << "Combat profiles: all classes, actual talent distributions, role support, persistence and deferred updates passed\n";
}
'''



TESTS = r"""
    struct Expected { uint8 cls; std::vector<std::string> profiles; };
    std::vector<Expected> const classes = {
        {CLASS_WARRIOR, {"arms", "fury", "prot"}},
        {CLASS_PALADIN, {"holy", "prot", "ret"}},
        {CLASS_HUNTER, {"bm", "mm", "surv"}},
        {CLASS_ROGUE, {"assassin", "combat", "subtlety"}},
        {CLASS_PRIEST, {"disc", "holy", "shadow"}},
        {CLASS_DEATH_KNIGHT, {"blood", "frost", "unholy"}},
        {CLASS_SHAMAN, {"ele", "enh", "resto"}},
        {CLASS_MAGE, {"arcane", "fire", "frost"}},
        {CLASS_WARLOCK, {"affli", "demo", "destro"}},
        {CLASS_DRUID, {"balance", "cat", "resto", "bear"}}
    };
    PlayerTalent nativeRank;
    talentPositions[100] = {1};
    sTalentStore.entries[1] = {11};
    spellMgr.entries[100] = {37};
    for (auto const& expected : classes) {
        auto const profiles = AiFactory::GetCombatProfiles(expected.cls);
        assert(std::find(profiles.begin(), profiles.end(), "auto") != profiles.end());
        assert(std::set<std::string>(profiles.begin(), profiles.end()).size() == profiles.size());
        for (auto const& profile : expected.profiles) {
            assert(std::find(profiles.begin(), profiles.end(), profile) != profiles.end());
            for (uint8 era : {0, 1, 2}) {
                Player player;
                player.cls = expected.cls;
                player.era = era;
                player.managed = era < 2 && player.cls != CLASS_DEATH_KNIGHT;
                player.eraTabs = {15, 0, 10};
                player.talents[100] = &nativeRank;
                PlayerbotAI ai(player);
                assert(AiFactory::GetCombatProfile(&player) == "auto");
                assert(AiFactory::GetPlayerSpecTab(&player) == (player.managed ? 0 : 1));
                auto const actual = AiFactory::GetPlayerSpecTabs(&player);
                if (player.managed) assert(actual.at(0) == 15 && actual.at(1) == 0 && actual.at(2) == 10);
                else assert(actual.at(0) == 0 && actual.at(1) == 37 && (!actual.contains(2) || actual.at(2) == 0));
                ai.combat.strategies = {"stay", "travel", "loot", "onyxia", "fury", "tank face", "behind"};
                ai.nonCombat.strategies = {"follow", "stay", "loot", "travel", "rpg", "custom::say"};
                assert(AiFactory::SetCombatProfile(&player, profile));
                assert(AiFactory::GetCombatProfile(&player) == profile);
                assert(AiFactory::GetEffectiveCombatProfile(&player) == profile);
                uint8 const expectedTab = player.cls == CLASS_DRUID ?
                    (profile == "balance" ? 0 : profile == "resto" ? 2 : 1) :
                    uint8(std::find(expected.profiles.begin(), expected.profiles.end(), profile) - expected.profiles.begin());
                assert(AiFactory::GetPlayerSpecTab(&player) == expectedTab);
                assert(AiFactory::GetPlayerSpecTabs(&player) == actual);
                assert(player.spells.empty() && player.talents.size() == 1);
                assert(ai.combat.HasStrategy("stay") && ai.combat.HasStrategy("travel") && ai.combat.HasStrategy("loot"));
                assert(ai.combat.HasStrategy("onyxia"));
                assert(ai.nonCombat.HasStrategy("follow") && ai.nonCombat.HasStrategy("stay"));
                assert(ai.nonCombat.HasStrategy("loot") && ai.nonCombat.HasStrategy("travel"));
                assert(ai.nonCombat.HasStrategy("rpg") && ai.nonCombat.HasStrategy("custom::say"));
                std::string primary = profile;
                if (player.cls == CLASS_PRIEST && profile == "holy") primary = "holy heal";
                if (player.cls == CLASS_ROGUE && profile == "subtlety") primary = "assassin";
                // Feral DPS before its earned Cat Form uses the native bear fallback.
                if (!(player.cls == CLASS_DRUID && profile == "cat"))
                    assert(ai.combat.HasStrategy(primary));
                bool const tank = profile == "bear" || profile == "prot" ||
                    (player.cls == CLASS_DEATH_KNIGHT && profile == "blood");
                bool const healer = profile == "resto" || profile == "disc" ||
                    (profile == "holy" && (player.cls == CLASS_PRIEST || player.cls == CLASS_PALADIN));
                assert(AiFactory::GetPlayerRoles(&player) ==
                    (tank ? BOT_ROLE_TANK : healer ? BOT_ROLE_HEALER : BOT_ROLE_DPS));
                assert(ai.combat.HasStrategy("tank face") == tank);
                assert(ai.combat.HasStrategy("save mana") == healer);
                if (player.cls == CLASS_HUNTER) assert(ai.nonCombat.HasStrategy("pet"));
                if (player.cls == CLASS_WARLOCK) {
                    auto pet = profile == "affli" ? "felhunter" : profile == "demo" ? "felguard" : "imp";
                    assert(ai.nonCombat.HasStrategy(pet));
                }
                assert(ai.equips > 0 && PlayerbotRepository::instance().saved == profile);
                int const saved = PlayerbotRepository::instance().saves;
                auto const combat = ai.combat.strategies;
                auto const nonCombat = ai.nonCombat.strategies;
                assert(!AiFactory::SetCombatProfile(&player, "not a profile"));
                assert(AiFactory::GetCombatProfile(&player) == profile);
                assert(PlayerbotRepository::instance().saves == saved);
                assert(ai.combat.strategies == combat && ai.nonCombat.strategies == nonCombat);
                player.combat = true;
                assert(!AiFactory::SetCombatProfile(&player, "auto"));
                assert(AiFactory::GetCombatProfile(&player) == profile);
                assert(PlayerbotRepository::instance().saves == saved);
                player.combat = false;
                assert(AiFactory::SetCombatProfile(&player, "auto"));
                assert(AiFactory::GetPlayerSpecTabs(&player) == actual);
            }
        }
    }
    assert(!AiFactory::SetCombatProfile(nullptr, "auto"));
    Player human;
    human.cls = CLASS_PRIEST;
    human.managed = true;
    human.eraTabs = {0, 0, 31};
    assert(AiFactory::GetCombatProfile(&human) == "auto");
    assert(AiFactory::GetPlayerSpecTab(&human) == PRIEST_TAB_SHADOW);
    assert(!PlayerbotAI::IsHeal(&human, true));
    assert(!AiFactory::SetCombatProfile(&human, "holy"));
    Player timed;
    timed.managed = true;
    timed.eraTabs = {0, 0, 20};
    PlayerbotAI timedAI(timed);
    timed.session.loggingOut = true;
    timedAI.UpdateAI(1);
    assert(timedAI.equips == 0);
    timed.session.loggingOut = false;
    timedAI.UpdateAI(1);
    assert(timedAI.combat.HasStrategy("prot") && timedAI.equips == 1);
    timed.eraTabs = {20, 0, 0};
    timedAI.UpdateAI(1);
    assert(timedAI.equips == 1);
    timedAI.UpdateAI(5000);
    assert(timedAI.combat.HasStrategy("arms") && !timedAI.combat.HasStrategy("prot"));
    assert(timedAI.equips == 2);
    Player autoWarrior;
    autoWarrior.managed = true;
    autoWarrior.eraTabs = {0, 20, 0};
    autoWarrior.spells.insert(SPELL_WHIRLWIND);
    PlayerbotAI autoAI(autoWarrior);
    autoAI.RefreshCombatProfile();
    assert(autoAI.combat.HasStrategy("fury") && !autoAI.combat.HasStrategy("prot"));
    int equips = autoAI.equips;
    autoAI.RefreshCombatProfile();
    assert(autoAI.equips == equips);
    autoWarrior.eraTabs = {0, 0, 20};
    autoWarrior.combat = true;
    autoAI.InvalidateCombatProfile();
    autoAI.RefreshCombatProfile();
    assert(autoAI.combat.HasStrategy("fury") && autoAI.equips == equips);
    autoWarrior.combat = false;
    autoAI.RefreshCombatProfile();
    assert(autoAI.combat.HasStrategy("prot") && !autoAI.combat.HasStrategy("fury"));
    assert(autoAI.equips == ++equips);
    autoWarrior.level = 61;
    autoAI.RefreshCombatProfile();
    assert(autoAI.equips == ++equips);
    autoWarrior.spells.insert(10000);
    autoAI.RefreshCombatProfile();
    assert(autoAI.equips == ++equips);
    autoWarrior.map = 530;
    autoAI.RefreshCombatProfile();
    assert(autoAI.equips == ++equips);
    Group group;
    autoWarrior.group = &group;
    autoAI.RefreshCombatProfile();
    assert(autoAI.equips == ++equips);
    autoWarrior.activeSpec = 1;
    autoAI.RefreshCombatProfile();
    assert(autoAI.equips == ++equips);
    autoAI.InvalidateCombatProfile();
    autoWarrior.teleported = true;
    autoAI.RefreshCombatProfile();
    assert(autoAI.equips == equips);
    autoWarrior.teleported = false;
    autoWarrior.alive = false;
    autoAI.RefreshCombatProfile();
    assert(autoAI.equips == equips);
    autoWarrior.alive = true;
    autoWarrior.world = false;
    autoAI.RefreshCombatProfile();
    assert(autoAI.equips == equips);
    autoWarrior.world = true;
    autoAI.RefreshCombatProfile();
    assert(autoAI.equips == ++equips);
    Player warrior;
    PlayerbotAI warriorAI(warrior);
    CombatProfileValue persisted(&warriorAI);
    assert(persisted.Get() == "auto");
    assert(persisted.Load("prot") && persisted.Save() == "prot");
    assert(!persisted.Load("holy") && persisted.Save() == "prot");
    assert(!persisted.Load("unknown") && persisted.Save() == "prot");
    assert(persisted.Load("auto") && persisted.Save() == "auto");
    assert(!AiFactory::SetCombatProfile(&warrior, "holy"));
    assert(AiFactory::SetCombatProfile(&warrior, "prot"));
    assert(PlayerbotAI::IsTank(&warrior, true));
    assert(warriorAI.combat.HasStrategy("prot") && warriorAI.combat.HasStrategy("tank assist"));
    assert(warriorAI.combat.HasStrategy("tank face") && !warriorAI.combat.HasStrategy("behind"));
    assert(AiFactory::SetCombatProfile(&warrior, "fury"));
    assert(!PlayerbotAI::IsTank(&warrior, true));
    assert(warriorAI.combat.HasStrategy("fury") && warriorAI.combat.HasStrategy("dps assist"));
    assert(!warriorAI.combat.HasStrategy("prot") && !warriorAI.combat.HasStrategy("tank face"));
    assert(warriorAI.combat.HasStrategy("behind"));
    int const savedWarrior = PlayerbotRepository::instance().saves;
    int const equippedWarrior = warriorAI.equips;
    assert(AiFactory::SetCombatProfile(&warrior, "fury"));
    assert(warriorAI.equips == equippedWarrior + 1);
    assert(PlayerbotRepository::instance().saves == savedWarrior);
    for (bool* gate : {&warrior.world, &warrior.alive}) {
        *gate = false;
        assert(!AiFactory::SetCombatProfile(&warrior, "auto"));
        assert(AiFactory::GetCombatProfile(&warrior) == "fury");
        *gate = true;
    }
    warrior.teleported = true;
    assert(!AiFactory::SetCombatProfile(&warrior, "auto"));
    warrior.teleported = false;
    Player mage;
    mage.cls = CLASS_MAGE;
    mage.managed = true;
    mage.eraTabs = {0, 40, 0};
    mage.spells.insert(SPELL_FROSTFIRE_BOLT);
    mage.auras.insert(SPELL_ICE_SHARDS);
    PlayerbotAI mageAI(mage);
    mageAI.RefreshCombatProfile();
    assert(AiFactory::GetEffectiveCombatProfile(&mage) == "frostfire");
    assert(mageAI.combat.HasStrategy("frostfire") && !mageAI.combat.HasStrategy("fire"));
    assert(AiFactory::SetCombatProfile(&mage, "fire"));
    assert(mageAI.combat.HasStrategy("fire") && !mageAI.combat.HasStrategy("frostfire"));
    Player druid;
    druid.cls = CLASS_DRUID;
    druid.managed = true;
    druid.eraTabs = {0, 44, 17};
    druid.spells.insert(SPELL_CAT_FORM);
    druid.auras.insert(SPELL_DRUID_THICK_HIDE);
    druid.feralSeed = 3;
    PlayerbotAI druidAI(druid);
    assert(!AiFactory::IsFeralTank(&druid));
    assert(AiFactory::GetEffectiveCombatProfile(&druid) == "cat");
    assert(AiFactory::SetCombatProfile(&druid, "bear"));
    assert(AiFactory::IsFeralTank(&druid) && PlayerbotAI::IsTank(&druid, true));
    druid.feralSeed = 1;
    assert(AiFactory::SetCombatProfile(&druid, "cat"));
    assert(!AiFactory::IsFeralTank(&druid) && !PlayerbotAI::IsTank(&druid, true));
    assert(druidAI.combat.HasStrategy("cat") && !druidAI.combat.HasStrategy("bear"));
    assert(AiFactory::SetCombatProfile(&druid, "resto"));
    assert(PlayerbotAI::IsHeal(&druid, true));
    assert(druidAI.combat.HasStrategy("resto") && druidAI.combat.HasStrategy("cure"));
    assert(druidAI.combat.HasStrategy("save mana") && druidAI.combat.HasStrategy("healer dps"));
    assert(!druidAI.combat.HasStrategy("behind") && !druidAI.combat.HasStrategy("tank face"));
    Player priest;
    priest.cls = CLASS_PRIEST;
    PlayerbotAI priestAI(priest);
    assert(AiFactory::SetCombatProfile(&priest, "holy"));
    assert(priestAI.combat.HasStrategy("holy heal") && priestAI.combat.HasStrategy("cure"));
    assert(AiFactory::SetCombatProfile(&priest, "shadow"));
    assert(priestAI.combat.HasStrategy("shadow") && !priestAI.combat.HasStrategy("holy heal"));
    assert(!priestAI.combat.HasStrategy("save mana") && !priestAI.combat.HasStrategy("healer dps"));
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source_argument(parser, default=prepared_core(ROOT) / 'modules/mod-playerbots')
    args = parser.parse_args()
    factory = (args.source / 'src/Bot/Factory/AiFactory.cpp').read_text()
    ai = (args.source / 'src/Bot/PlayerbotAI.cpp').read_text()
    header = (args.source / 'src/Bot/PlayerbotAI.h').read_text()
    shared = (prepared_core(ROOT) / 'src/server/shared/SharedDefines.h').read_text()
    enums = '\n'.join(function(header, 'enum ' + name) + ';' for name in (
        'HUNTER_TABS', 'ROGUE_TABS', 'PRIEST_TABS', 'DEATH_KNIGHT_TABS', 'DRUID_TABS',
        'MAGE_TABS', 'SHAMAN_TABS', 'PALADIN_TABS', 'WARLOCK_TABS', 'WARRIOR_TABS', 'BotRoles : uint8'))
    enums += '\n' + function(shared, 'enum Classes') + ';'
    assert 'bool EraTalentBots_SpecTabs(Player* bot, uint32* tabs3);' in (
        args.source / 'src/Bot/EraTalentBridge.h').read_text()
    factory_functions = (
        'std::vector<std::string> AiFactory::GetCombatProfiles(',
        'std::string AiFactory::GetCombatProfile(',
        'bool AiFactory::SetCombatProfile(',
        'bool AiFactory::IsFeralTank(',
        'std::string AiFactory::GetEffectiveCombatProfile(',
        'uint8 AiFactory::GetPlayerSpecTab(',
        'BotRoles AiFactory::GetPlayerRoles(',
        'std::map<uint8, uint32> AiFactory::GetPlayerSpecTabs(',
        'void AiFactory::AddClassCombatStrategies(',
        'void AiFactory::AddClassNonCombatStrategies(',
        'void AiFactory::RefreshCombatStrategies(',
    )
    ai_functions = ('bool PlayerbotAI::IsTank(', 'bool PlayerbotAI::IsHeal(',
                    'bool PlayerbotAI::IsDps(', 'bool PlayerbotAI::IsRanged(',
                    'bool PlayerbotAI::IsMelee(', 'void PlayerbotAI::RefreshCombatProfile(')
    production = '\n\n'.join(function(factory, signature) for signature in factory_functions)
    production += '\n\n' + '\n\n'.join(function(ai, signature) for signature in ai_functions)
    update = function(ai, 'void PlayerbotAI::UpdateAI(')
    boundary = update.index('    // Bots send no movement opcodes')
    update = update[:boundary] + '}\n'
    update = update.replace('bool minimal)', 'bool /*minimal*/)')
    production += '\n\n' + update
    assert 'RefreshCombatProfile();' in update
    assert 'InvalidateCombatProfile();' in function(ai, 'void PlayerbotAI::ResetStrategies(')
    assert 'creators["combat profile"]' in (args.source / 'src/Ai/Base/ValueContext.h').read_text()
    assert 'GetAiObjectContext()->Load(values);' in (args.source / 'src/Db/PlayerbotRepository.cpp').read_text()
    native_value = (args.source / 'src/Bot/Engine/Value/Value.h').read_text()
    assert 'T Get() override { return value; }' in native_value
    assert 'void Set(T val) override { value = val; }' in native_value
    value = (args.source / 'src/Ai/Base/Value/CombatProfileValue.h').read_text()
    value = function(value, 'class CombatProfileValue') + ';'
    text = CPP.replace('@ENUMS@', enums).replace('@SAVED_VALUE@', value)
    text = text.replace('@PRODUCTION@', production).replace('@TESTS@', TESTS)
    mutations = (
        ('manual changes in combat', 'player->IsInCombat() || ', ''),
        ('foreign class profile', 'if (std::find(profiles.begin(), profiles.end(), mode) == profiles.end())', 'if (false)'),
        ('historical points ignored', 'if (EraTalentBots_SpecTabs(bot, eraTabs))', 'if (false)'),
        ('manual profile ignored', '    if (mode != "auto")\n    {', '    if (false)\n    {'),
        ('seeded cat becomes bear', '    if (seeded >= 0)', '    if (false)'),
        ('manual cat becomes bear', '    if (mode == "cat")', '    if (false)'),
        ('stale class strategies retained', '        combat->removeStrategy(name, false);', ''),
        ('unrelated user strategy removed', 'combat->removeStrategy(name, false);', 'combat->removeStrategy("stay", false);'),
        ('refresh during combat', ' || bot->IsInCombat()', ''),
        ('dirty role change ignored', 'bool dirty = combatProfileDirty.exchange(false, std::memory_order_relaxed);',
         'combatProfileDirty.store(false, std::memory_order_relaxed); bool dirty = false;'),
        ('unchanged role refreshed each tick', '    if (!force && !dirty && key == combatProfileKey)\n        return;',
         '    (void)force; (void)dirty;'),
        ('role ignores tank profile', '    if (PlayerbotAI::IsTank(player, true))\n        return BOT_ROLE_TANK;', ''),
        ('profile not saved', '        PlayerbotRepository::instance().Save(ai);', '        (void)ai;'),
        ('invalid persisted profile', 'if (std::find(profiles.begin(), profiles.end(), text) == profiles.end())', 'if (false)'),
        ('automatic update disconnected', '        RefreshCombatProfile();', ''),
    )
    with tempfile.TemporaryDirectory(prefix='combat-profiles-') as temporary:
        directory = Path(temporary)

        def run_case(case):
            index, label, body, expected = case
            work = directory / str(index)
            work.mkdir()
            source = work / 'fixture.cpp'
            executable = work / 'fixture'
            source.write_text(body)
            command = [cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', *SANITIZER_FLAGS,
                       '-no-pie', str(source), '-o', str(executable)]
            subprocess.run(command, check=True)
            result = subprocess.run([str(executable)], capture_output=True, text=True,
                                    check=False, timeout=TIMEOUT)
            if expected:
                if result.returncode:
                    raise AssertionError(result.stdout + result.stderr)
                return result.stdout.strip()
            if result.returncode == 0:
                raise AssertionError('Unsafe combat profile mutation survived: ' + label)
            if 'Assertion' not in result.stderr:
                raise AssertionError('Mutation failed outside fixture assertions: ' + label + '\n' + result.stderr)
            return 'Combat profile mutation rejected: ' + label

        print(run_case((0, 'production', text, True)))
        cases = []
        for index, (label, before, after) in enumerate(mutations, 1):
            if before not in text:
                raise AssertionError('Expected production guard: ' + label)
            cases.append((index, label, text.replace(before, after, 1), False))
        for result in in_parallel(run_case, cases):
            print(result)


if __name__ == '__main__':
    main()
