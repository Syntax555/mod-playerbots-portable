"""Exercise explicit MultiBot training with actual bridge and native purchase logic.

Extracted production functions make the affordability, security, prerequisite,
interaction, purchase and reporting decisions. Fixtures supply world state,
recording hooks and packet containers; this does not start a realm.
"""

from pathlib import Path
import argparse
import json
import os
import subprocess
import tempfile

from PreparedSources import prepared_core


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    cursor = opening + 1
    while depth:
        depth += (source[cursor] == '{') - (source[cursor] == '}')
        cursor += 1
    return source[start:cursor]


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--core', type=Path, help='prepared core source directory')
args = parser.parse_args()
repository = Path(__file__).resolve().parents[2]
core = args.core or prepared_core(repository)
module = core / 'modules/mod-playerbots/src'
bridge = (core / 'modules/mod-multibot-bridge/src/MultiBotBridge.cpp').read_text()
trainer = (core / 'src/server/game/Entities/Creature/Trainer.cpp').read_text()
handler = (core / 'src/server/game/Handlers/NPCHandler.cpp').read_text()
player = (core / 'src/server/game/Entities/Player/Player.cpp').read_text()
budget = (module / 'Ai/Base/Value/BudgetValues.cpp').read_text()
ai = (module / 'Bot/PlayerbotAI.cpp').read_text()
lock = json.loads((repository / 'versions.lock.json').read_text())
bridge_revision = next(entry['revision'] for entry in lock['modules']
                       if entry['name'] == 'mod-multibot-bridge')
baseline = subprocess.run(
    ['git', '-C', str(repository / '.module-cache/mod-multibot-bridge'),
     'show', f'{bridge_revision}:src/MultiBotBridge.cpp'],
    check=True, text=True, capture_output=True).stdout

fixture = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
using int32 = std::int32_t;
using ChatMsg = int;
constexpr uint32 MAX_MONEY_AMOUNT = 2147483647;
constexpr uint32 UNIT_NPC_FLAG_TRAINER = 1;
constexpr uint32 CREATURE_TYPE_FLAG_VISIBLE_TO_GHOSTS = 1;
constexpr uint32 CREATURE_TYPE_FLAG_INTERACT_WHILE_DEAD = 2;
constexpr uint32 PLAYERBOT_SECURITY_ALLOW_ALL = 0;
constexpr uint32 UNIT_STATE_DIED = 1;
constexpr uint32 SPELL_AURA_FEIGN_DEATH = 1;
constexpr uint32 CMSG_TRAINER_BUY_SPELL = 1;
constexpr uint32 SPELL_EFFECT_LEARN_SPELL = 36;
constexpr int REP_UNFRIENDLY = 2;
constexpr float INTERACTION_DISTANCE = 5.0f;
constexpr char kFieldSeparator = '|';
enum NPCFlags : uint32 { TrainerFlag = UNIT_NPC_FLAG_TRAINER };
enum class BotCheatMask { gold };
enum class NeedMoneyFor : uint32 { spells = 3 };
struct ObjectGuid
{
    uint32 value = 0;
    explicit operator bool() const { return value != 0; }
    auto operator<=>(ObjectGuid const&) const = default;
    std::string ToString() const { return std::to_string(value); }
};
class Player;
class Creature;
class PlayerbotAI;
class AiObjectContext {};
class Unit
{
public:
    virtual ~Unit() = default;
    virtual Creature* ToCreature() { return nullptr; }
};
struct SpellEffectInfo
{
    uint32 Effect = 0;
    uint32 TriggerSpell = 0;
    bool IsEffect(uint32 effect) const { return Effect == effect; }
};
struct SpellInfo
{
    uint32 Id = 0;
    bool primaryProfession = false;
    std::vector<SpellEffectInfo> effects;
    bool HasEffect(uint32 effect) const
    {
        return std::any_of(effects.begin(), effects.end(), [effect](auto const& entry)
        {
            return entry.IsEffect(effect);
        });
    }
    bool IsPrimaryProfessionFirstRank() const { return primaryProfession; }
    auto const& GetEffects() const { return effects; }
};
struct SpellManager
{
    std::map<uint32, SpellInfo> spells;
    std::map<uint32, uint32> preceding;
    std::map<uint32, std::vector<std::pair<uint32, uint32>>> required;
    SpellInfo const* GetSpellInfo(uint32 id) const
    {
        auto found = spells.find(id);
        return found == spells.end() ? nullptr : &found->second;
    }
    SpellInfo const* AssertSpellInfo(uint32 id) const
    {
        auto result = GetSpellInfo(id);
        assert(result);
        return result;
    }
    uint32 GetPrevSpellInChain(uint32 id) const
    {
        auto found = preceding.find(id);
        return found == preceding.end() ? 0 : found->second;
    }
    auto GetSpellsRequiredForSpellBounds(uint32 id) const
    {
        auto found = required.find(id);
        return found == required.end() ? std::vector<std::pair<uint32, uint32>>() : found->second;
    }
} spellManager;
auto* sSpellMgr = &spellManager;

namespace Trainer
{
enum class Type : uint32 { Class, Mount, Tradeskill, Pet };
enum class SpellState : uint8 { Available, Unavailable, Known };
enum class FailReason : uint32 { Unavailable, NotEnoughMoney, NotEnoughSkill };
struct Spell
{
    uint32 SpellId = 0;
    uint32 MoneyCost = 0;
    uint32 ReqSkillLine = 0;
    uint32 ReqSkillRank = 0;
    std::array<uint32, 3> ReqAbility{};
    uint8 ReqLevel = 0;
    bool IsCastable() const;
};
class Trainer
{
public:
    uint32 _trainerId = 1;
    Type _type = Type::Tradeskill;
    uint32 _requirement = 0;
    std::vector<Spell> _spells;
    std::vector<FailReason> failures;
    uint32 successes = 0;
    Spell const* GetSpell(uint32 id) const;
    auto const& GetSpells() const { return _spells; }
    uint32 GetSpellCost(Player const* player, Creature const* npc, Spell const* spell) const;
    bool CanTeachSpell(Player const* player, Spell const* spell) const;
    void TeachSpell(Creature* npc, Player* player, uint32 spellId);
    bool IsTrainerValidForPlayer(Player const* player) const;
    SpellState GetSpellState(Player const* player, Spell const* spell) const;
    SpellState GetDefaultSpellState(Player const* player, Spell const* spell) const;
    uint32 GetTrainerRequirement() const { return _requirement; }
    Type GetTrainerType() const { return _type; }
    void SendTeachFailure(Creature const*, Player const*, uint32, FailReason reason)
    {
        failures.push_back(reason);
    }
    void SendTeachSucceeded(Creature const*, Player const*, uint32) { ++successes; }
};
}
struct CreatureTemplate { uint32 type_flags = 0; };
class Creature : public Unit
{
public:
    ObjectGuid guid{500};
    uint32 entry = 900;
    uint32 map = 1;
    float x = 0.0f;
    bool alive = true;
    uint32 flags = UNIT_NPC_FLAG_TRAINER;
    int reaction = 4;
    ObjectGuid charmer;
    CreatureTemplate creatureTemplate;
    Creature* ToCreature() override { return this; }
    bool IsTrainer() const { return flags & UNIT_NPC_FLAG_TRAINER; }
    bool IsAlive() const { return alive; }
    bool HasNpcFlag(NPCFlags required) const { return (flags & required) == required; }
    int GetReactionTo(Player*) const { return reaction; }
    ObjectGuid GetCharmerGUID() const { return charmer; }
    CreatureTemplate const* GetCreatureTemplate() const { return &creatureTemplate; }
    bool IsWithinDistInMap(Player* player, float distance) const;
    ObjectGuid GetGUID() const { return guid; }
    uint32 GetEntry() const { return entry; }
    void SendPlaySpellVisual(uint32) {}
    void SendPlaySpellImpact(ObjectGuid, uint32) {}
};
struct WorldPacket
{
    ObjectGuid guid;
    uint32 spellId = 0;
    WorldPacket(uint32, uint32) {}
    WorldPacket& operator<<(ObjectGuid value) { guid = value; return *this; }
    WorldPacket& operator<<(uint32 value) { spellId = value; return *this; }
};
namespace WorldPackets::NPC
{
struct TrainerBuySpell
{
    ObjectGuid TrainerGUID;
    uint32 SpellID = 0;
    explicit TrainerBuySpell(WorldPacket packet) : TrainerGUID(packet.guid), SpellID(packet.spellId) {}
    void Read() {}
};
}
class WorldSession
{
public:
    Player* _player = nullptr;
    uint32 purchaseCalls = 0;
    Player* GetPlayer() const { return _player; }
    void HandleTrainerBuySpellOpcode(WorldPackets::NPC::TrainerBuySpell& packet);
};
class Player : public Unit
{
public:
    std::string name = "Altbot";
    ObjectGuid guid{1};
    uint32 money = 151;
    uint32 level = 80;
    uint32 playerClass = 1;
    uint32 race = 1;
    uint32 map = 1;
    float x = 0.0f;
    float discount = 0.95f;
    bool alive = true;
    bool inWorld = true;
    bool inFlight = false;
    bool sessionAvailable = true;
    bool classRaceFits = true;
    uint32 professionsFree = 2;
    uint32 auraRemovals = 0;
    uint32 moneyChanges = 0;
    Unit* selected = nullptr;
    PlayerbotAI* botAI = nullptr;
    std::set<uint32> known;
    std::map<uint32, uint32> skills;
    WorldSession session;
    Player() { session._player = this; }
    uint32 GetMoney() const { return money; }
    bool HasEnoughMoney(uint32 cost) const { return money >= cost; }
    void ModifyMoney(int32 delta)
    {
        assert(std::int64_t(money) + delta >= 0);
        money = uint32(std::int64_t(money) + delta);
        ++moneyChanges;
    }
    float GetReputationPriceDiscount(Creature const*) const { return discount; }
    bool HasSpell(uint32 id) const { return known.contains(id); }
    void learnSpell(uint32 id, bool) { known.insert(id); }
    void CastSpell(Player*, uint32 id, bool)
    {
        for (auto const& effect : sSpellMgr->AssertSpellInfo(id)->GetEffects())
            if (effect.IsEffect(SPELL_EFFECT_LEARN_SPELL))
                learnSpell(effect.TriggerSpell, false);
    }
    bool IsSpellFitByClassAndRace(uint32) const { return classRaceFits; }
    uint32 GetBaseSkillValue(uint32 id) const
    {
        auto found = skills.find(id);
        return found == skills.end() ? 0 : found->second;
    }
    uint32 GetLevel() const { return level; }
    uint32 getClass() const { return playerClass; }
    uint32 getRace() const { return race; }
    uint32 GetFreePrimaryProfessionPoints() const { return professionsFree; }
    ObjectGuid GetGUID() const { return guid; }
    std::string const& GetName() const { return name; }
    WorldSession* GetSession() { return sessionAvailable ? &session : nullptr; }
    Unit* GetSelectedUnit() const { return selected; }
    bool IsInWorld() const { return inWorld; }
    bool IsInFlight() const { return inFlight; }
    bool IsAlive() const { return alive; }
    bool HasUnitState(uint32) const { return false; }
    void RemoveAurasByType(uint32) { ++auraRemovals; }
    Creature* GetNPCIfCanInteractWith(ObjectGuid const& guid, uint32 flags);
};
bool Creature::IsWithinDistInMap(Player* player, float distance) const
{
    return player->map == map && std::abs(player->x - x) <= distance;
}
struct Security
{
    bool allow = true;
    Player* expectedRequester = nullptr;
    uint32 calls = 0;
    bool CheckLevelFor(uint32 level, bool silent, Player* requester)
    {
        assert(level == PLAYERBOT_SECURITY_ALLOW_ALL && silent);
        ++calls;
        return allow && requester == expectedRequester;
    }
};
class PlayerbotAI
{
public:
    Player* bot = nullptr;
    Player* master = nullptr;
    bool gold = false;
    bool contextAvailable = true;
    bool securityAvailable = true;
    uint32 spellBudget = 95;
    uint32 totalBudget = 295;
    AiObjectContext context;
    Security security;
    bool HasCheat(BotCheatMask) const { return gold; }
    Player* GetMaster() const { return master; }
    AiObjectContext* GetAiObjectContext() { return contextAvailable ? &context : nullptr; }
    Security* GetSecurity() { return securityAvailable ? &security : nullptr; }
    uint32 Value(std::string const& name, std::string const& qualifier);
    uint32 Value(std::string const& name, uint32 qualifier) { return Value(name, std::to_string(qualifier)); }
};
PlayerbotAI* GetBotAI(Player* player) { return player ? player->botAI : nullptr; }
#define GET_PLAYERBOT_AI(player) GetBotAI(player)
#define AI_VALUE2(type, name, qualifier) static_cast<type>((void)context, botAI->Value(name, qualifier))
#define LOG_DEBUG(...) do {} while (false)
struct Config
{
    bool naturalProgression = true;
    bool allowLearnTrainerSpells = true;
} sPlayerbotAIConfig;
struct ScriptManager
{
    Player const* expectedPlayer = nullptr;
    Creature const* expectedCreature = nullptr;
    std::map<uint32, uint32> baseQuotes;
    bool allowLearn = true;
    bool blockState = false;
    uint32 costCalls = 0;
    uint32 trainCalls = 0;
    void OnPlayerGetTrainerSpellCost(Player const* player, Creature const* npc, uint32 id, uint32& cost)
    {
        assert(player == expectedPlayer && npc == expectedCreature);
        ++costCalls;
        if (auto found = baseQuotes.find(id); found != baseQuotes.end())
            cost = found->second;
    }
    void OnPlayerGetTrainerSpellState(Player const*, uint32, uint32, Trainer::SpellState& state) const
    {
        if (blockState)
            state = Trainer::SpellState::Unavailable;
    }
    bool OnPlayerCanLearnSpell(Player*, uint32) const { return allowLearn; }
    void OnPlayerAfterTrainSpell(Player*, Creature*, uint32) { ++trainCalls; }
} scriptManager;
auto* sScriptMgr = &scriptManager;
struct ObjectManager
{
    Creature* creature = nullptr;
    Trainer::Trainer* trainer = nullptr;
    Trainer::Trainer* GetTrainer(uint32 entry) const
    {
        return creature && creature->entry == entry ? trainer : nullptr;
    }
} objectManager;
auto* sObjectMgr = &objectManager;
namespace ObjectAccessor
{
Creature* GetCreatureOrPetOrVehicle(Player& player, ObjectGuid guid)
{
    auto* creature = objectManager.creature;
    return creature && creature->guid == guid && player.map == creature->map ? creature : nullptr;
}
}
class FreeMoneyForValue
{
public:
    Player* bot = nullptr;
    PlayerbotAI* botAI = nullptr;
    AiObjectContext* context = nullptr;
    explicit FreeMoneyForValue(PlayerbotAI* ai) : bot(ai->bot), botAI(ai), context(&ai->context) {}
    std::string getQualifier() const { return "3"; }
    uint32 Calculate();
};
std::string Trim(std::string value)
{
    auto first = value.find_first_not_of(" \t\n\r");
    return first == std::string::npos ? "" : value.substr(first, value.find_last_not_of(" \t\n\r") - first + 1);
}
std::string ToUpper(std::string value)
{
    for (char& c : value)
        c = char(std::toupper(static_cast<unsigned char>(c)));
    return value;
}
std::string UrlEncodeField(std::string const& value) { return value; }
bool TryParseUint32Field(std::string const& text, uint32 lower, uint32 upper, uint32& output)
{
    if (text.empty() || text.find_first_not_of("0123456789") != std::string::npos)
        return false;
    auto value = std::stoull(text);
    if (value < lower || value > upper)
        return false;
    output = uint32(value);
    return true;
}
Player* controlledBot = nullptr;
Player* FindBotByName(Player*, std::string const& name)
{
    return controlledBot && controlledBot->name == name ? controlledBot : nullptr;
}
std::vector<std::string> responses;
void SendAddonPacket(Player*, ChatMsg, std::string const& kind, std::string const& payload)
{
    assert(kind == "TRAINER_LEARN");
    responses.push_back(payload);
}
'''

production = '\n'.join([
    function(ai, 'bool IsRealPlayer(Player* player)'),
    function(budget, 'uint32 FreeMoneyForValue::Calculate()'),
    r'''
uint32 PlayerbotAI::Value(std::string const& name, std::string const& qualifier)
{
    assert(qualifier == "3");
    if (name == "total money needed for")
        return totalBudget;
    if (name == "money needed for")
        return spellBudget;
    assert(name == "free money for");
    return FreeMoneyForValue(this).Calculate();
}
''',
    function(player, 'Creature* Player::GetNPCIfCanInteractWith'),
    'namespace Trainer {\n' + '\n'.join(function(trainer, signature) for signature in [
        'bool Spell::IsCastable()',
        'uint32 Trainer::GetSpellCost(',
        'void Trainer::TeachSpell(',
        'Spell const* Trainer::GetSpell(',
        'bool Trainer::CanTeachSpell(',
        'SpellState Trainer::GetSpellState(',
        'SpellState Trainer::GetDefaultSpellState(',
        'bool Trainer::IsTrainerValidForPlayer(',
    ]) + '\n}',
    function(handler, 'void WorldSession::HandleTrainerBuySpellOpcode('),
    function(bridge, 'struct TrainerSpellEntryData') + ';',
    '\n'.join(function(bridge, signature) for signature in [
        'bool BotHasGoldCheat(',
        'uint32 GetBotTrainerFreeMoney(',
        'Creature* GetSelectedTrainer(',
        'std::vector<TrainerSpellEntryData> BuildTrainerSpellEntries(',
        'bool LearnTrainerSpell(',
        'void SendTrainerLearnResult(',
        'void RunTrainerLearnCommand(Player* requester, ChatMsg replyType, std::string const& botName, '
        'std::string const& requestToken, std::string const& trainerEntryValue, std::string const& spellIdValue)\n{',
    ]),
    function(baseline, 'uint32 GetBotTrainerFreeMoney(').replace(
        'GetBotTrainerFreeMoney', 'BaselineGetBotTrainerFreeMoney'),
    function(baseline, 'std::vector<TrainerSpellEntryData> BuildTrainerSpellEntries(')
        .replace('BuildTrainerSpellEntries', 'BaselineBuildTrainerSpellEntries')
        .replace('GetBotTrainerFreeMoney', 'BaselineGetBotTrainerFreeMoney'),
    function(bridge, 'bool LearnTrainerSpell(').replace('LearnTrainerSpell(', 'BaselineLearnTrainerSpell(')
        .replace('GetBotTrainerFreeMoney', 'BaselineGetBotTrainerFreeMoney'),
])

tests = r'''
struct Scenario
{
    Player bot;
    Player requester;
    PlayerbotAI ai;
    Creature npc;
    Trainer::Trainer trainer;
    Scenario()
    {
        sPlayerbotAIConfig = {};
        spellManager = {};
        scriptManager = {};
        responses.clear();
        requester.name = "Owner";
        requester.guid = {2};
        requester.selected = &npc;
        bot.botAI = &ai;
        ai.bot = &bot;
        ai.master = &requester;
        ai.security.expectedRequester = &requester;
        controlledBot = &bot;
        objectManager = {&npc, &trainer};
        scriptManager.expectedPlayer = &bot;
        scriptManager.expectedCreature = &npc;
        AddSpell(100, 100);
    }
    void AddSpell(uint32 id, uint32 cost)
    {
        trainer._spells.push_back({id, cost, 0, 0, {}, 1});
        spellManager.spells[id] = {id, false, {}};
    }
    std::vector<TrainerSpellEntryData> List() { return BuildTrainerSpellEntries(&bot, &npc); }
    void Buy(std::string const& spell = "100", std::string const& entry = "900")
    {
        RunTrainerLearnCommand(&requester, 0, " Altbot ", " ticket ", entry, spell);
        assert(!responses.empty());
    }
    std::vector<std::string> Result() const
    {
        std::vector<std::string> fields;
        std::istringstream input(responses.back());
        std::string field;
        while (std::getline(input, field, kFieldSeparator))
            fields.push_back(field);
        assert(fields.size() == 8);
        assert(fields[0] == "Altbot" && fields[1] == "ticket");
        return fields;
    }
    void ExpectResult(bool ok, std::string const& reason, uint32 count, uint32 spent) const
    {
        auto fields = Result();
        assert(fields[4] == (ok ? "OK" : "ERR"));
        assert(fields[5] == reason);
        assert(std::stoul(fields[6]) == count && std::stoul(fields[7]) == spent);
    }
};

void ReproduceBudgetFailure()
{
    Scenario s;
    assert(BaselineGetBotTrainerFreeMoney(&s.bot) == 151);
    for (Player* master : {&s.bot, static_cast<Player*>(nullptr)})
    {
        s.ai.master = master;
        assert(!IsRealPlayer(master));
        assert(FreeMoneyForValue(&s.ai).Calculate() == 0);
        assert(BaselineGetBotTrainerFreeMoney(&s.bot) == 0);
        auto oldList = BaselineBuildTrainerSpellEntries(&s.bot, &s.npc);
        assert(oldList.size() == 1 && oldList[0].cost == 95 && !oldList[0].canAfford);
        std::string reason;
        assert(!BaselineLearnTrainerSpell(&s.bot, &s.npc, sSpellMgr->GetSpellInfo(100), 95, reason));
        assert(reason == "TOO_EXPENSIVE" && s.bot.money == 151 && !s.bot.HasSpell(100));
        assert(GetBotTrainerFreeMoney(&s.bot) == 151);
        auto newList = s.List();
        assert(newList.size() == 1 && newList[0].cost == 95 && newList[0].canAfford);
    }
    s.ai.master = &s.requester;
    assert(IsRealPlayer(s.ai.master) && FreeMoneyForValue(&s.ai).Calculate() == 151);
    PlayerbotAI ownerAI;
    ownerAI.bot = &s.requester;
    ownerAI.master = &s.requester;
    s.requester.botAI = &ownerAI;
    assert(!IsRealPlayer(s.ai.master) && FreeMoneyForValue(&s.ai).Calculate() == 0);
    assert(BaselineGetBotTrainerFreeMoney(&s.bot) == 0 && GetBotTrainerFreeMoney(&s.bot) == 151);
    s.requester.botAI = nullptr;
    s.ai.master = nullptr;
    s.ai.totalBudget = 195;
    assert(FreeMoneyForValue(&s.ai).Calculate() == 51);
    assert(GetBotTrainerFreeMoney(&s.bot) == 151);
    s.Buy();
    s.ExpectResult(true, "OK", 1, 95);
    assert(s.bot.money == 56 && s.bot.HasSpell(100));
    // The autonomous reservation remains in effect after the explicit purchase.
    assert(FreeMoneyForValue(&s.ai).Calculate() == 0);
}

void WalletBoundaries()
{
    for (uint32 money : {94u, 95u, 151u})
        for (uint32 masterKind : {0u, 1u, 2u})
        {
            Scenario s;
            s.bot.money = money;
            s.ai.master = masterKind == 0 ? &s.requester : masterKind == 1 ? &s.bot : nullptr;
            auto entries = s.List();
            assert(entries.size() == 1 && entries[0].cost == 95);
            assert(entries[0].canAfford == (money >= 95));
            s.Buy();
            if (money < 95)
            {
                s.ExpectResult(false, "TOO_EXPENSIVE", 0, 0);
                assert(s.bot.money == money && s.bot.known.empty() && s.bot.moneyChanges == 0);
            }
            else
            {
                s.ExpectResult(true, "OK", 1, 95);
                assert(s.bot.money == money - 95 && s.bot.HasSpell(100));
                assert(s.bot.moneyChanges == 1 && s.trainer.successes == 1 && scriptManager.trainCalls == 1);
            }
        }
    assert(GetBotTrainerFreeMoney(nullptr) == 0);
    Scenario s;
    s.bot.botAI = nullptr;
    assert(GetBotTrainerFreeMoney(&s.bot) == 151 && s.List()[0].canAfford);
    s.Buy();
    s.ExpectResult(false, "NATURAL_PROGRESSION", 0, 0);
    assert(s.bot.money == 151);
}

void WalletChangesAfterListing()
{
    Scenario reduced;
    assert(reduced.List()[0].canAfford);
    reduced.bot.money = 94;
    reduced.Buy();
    reduced.ExpectResult(false, "TOO_EXPENSIVE", 0, 0);
    assert(reduced.bot.money == 94 && !reduced.bot.HasSpell(100) && reduced.bot.moneyChanges == 0);

    Scenario increased;
    increased.bot.money = 94;
    assert(!increased.List()[0].canAfford);
    increased.bot.money = 151;
    increased.Buy();
    increased.ExpectResult(true, "OK", 1, 95);
    assert(increased.bot.money == 56 && increased.bot.HasSpell(100) && increased.bot.moneyChanges == 1);
}

void LearnAllFreshWallet()
{
    Scenario s;
    s.ai.master = nullptr;
    s.AddSpell(101, 50); // 47 copper after the same native faction discount.
    s.AddSpell(102, 20); // 19 copper does not fit the remaining wallet.
    auto entries = s.List();
    assert(entries.size() == 3 && entries[0].canAfford && entries[1].canAfford && entries[2].canAfford);
    s.Buy(" ALL ");
    s.ExpectResult(true, "OK", 2, 142);
    assert(s.bot.money == 9 && s.bot.HasSpell(100) && s.bot.HasSpell(101) && !s.bot.HasSpell(102));
    assert(s.bot.moneyChanges == 2 && s.trainer.successes == 2);
}

void GoldCheatModes()
{
    for (bool natural : {false, true})
        for (bool gold : {false, true})
            for (uint32 money : {94u, 151u})
            {
                Scenario s;
                sPlayerbotAIConfig.naturalProgression = natural;
                s.ai.gold = gold;
                s.ai.master = nullptr;
                s.bot.money = money;
                bool free = !natural && gold;
                auto entries = s.List();
                assert(entries.size() == 1 && entries[0].canAfford == (free || money >= 95));
                s.Buy();
                if (!free && money < 95)
                {
                    s.ExpectResult(false, "TOO_EXPENSIVE", 0, 0);
                    assert(s.bot.money == money && !s.bot.HasSpell(100));
                }
                else
                {
                    // Legacy reports its nominal quote, while natural mode reports actual money debited.
                    s.ExpectResult(true, "OK", 1, 95);
                    assert(s.bot.money == money - (free ? 0 : 95) && s.bot.HasSpell(100));
                }
            }
}

void NativeQuotes()
{
    Scenario s;
    // A progression hook sets the base quote before the native reputation discount.
    scriptManager.baseQuotes[100] = 80;
    auto entries = s.List();
    assert(entries.size() == 1 && entries[0].cost == 76 && entries[0].canAfford);
    auto oldEntries = BaselineBuildTrainerSpellEntries(&s.bot, &s.npc);
    assert(oldEntries.size() == 1 && oldEntries[0].cost == 95);
    s.Buy();
    s.ExpectResult(true, "OK", 1, 76);
    assert(s.bot.money == 75 && scriptManager.costCalls >= 2);

    Scenario costly;
    scriptManager.baseQuotes[100] = 200;
    assert(costly.List()[0].cost == 190 && !costly.List()[0].canAfford);
    costly.Buy();
    costly.ExpectResult(false, "TOO_EXPENSIVE", 0, 0);
    assert(costly.bot.money == 151 && !costly.bot.HasSpell(100));
}

void SecurityAndInteractionGuards()
{
    for (uint32 guard = 0; guard < 14; ++guard)
    {
        Scenario s;
        switch (guard)
        {
            case 0: s.ai.security.allow = false; break;
            case 1: s.ai.securityAvailable = false; break;
            case 2: s.bot.sessionAvailable = false; break;
            case 3: s.bot.inWorld = false; break;
            case 4: s.bot.x = INTERACTION_DISTANCE + 1; break;
            case 5: s.bot.map = 2; break;
            case 6: s.bot.alive = false; break;
            case 7: s.npc.alive = false; break;
            case 8: s.npc.reaction = REP_UNFRIENDLY; break;
            case 9: s.npc.charmer = {99}; break;
            case 10: s.bot.inFlight = true; break;
            case 11: sPlayerbotAIConfig.allowLearnTrainerSpells = false; break;
            case 12: s.requester.selected = nullptr; break;
            case 13: s.ai.security.expectedRequester = &s.bot; break;
        }
        s.Buy();
        s.ExpectResult(false, "NATURAL_PROGRESSION", 0, 0);
        assert(s.bot.money == 151 && s.bot.known.empty() && s.bot.moneyChanges == 0);
        assert(scriptManager.trainCalls == 0);
    }
    Scenario changed;
    changed.Buy("100", "901");
    changed.ExpectResult(false, "NATURAL_PROGRESSION", 0, 0);
    assert(changed.bot.money == 151 && changed.bot.known.empty());

    Scenario direct;
    direct.bot.x = INTERACTION_DISTANCE + 1;
    WorldPacket data(CMSG_TRAINER_BUY_SPELL, 12);
    data << direct.npc.guid << uint32(100);
    WorldPackets::NPC::TrainerBuySpell request(std::move(data));
    direct.bot.session.HandleTrainerBuySpellOpcode(request);
    assert(direct.bot.money == 151 && direct.bot.known.empty() && direct.trainer.successes == 0);
}

void PrerequisiteGuards()
{
    for (uint32 guard = 0; guard < 9; ++guard)
    {
        Scenario s;
        switch (guard)
        {
            case 0: s.bot.level = 0; break;
            case 1: s.bot.classRaceFits = false; break;
            case 2: s.trainer._spells[0].ReqSkillLine = 185; s.trainer._spells[0].ReqSkillRank = 75; break;
            case 3: s.trainer._spells[0].ReqAbility[0] = 99; break;
            case 4: spellManager.preceding[100] = 99; break;
            case 5: spellManager.required[100] = {{100, 99}}; break;
            case 6: s.trainer._type = Trainer::Type::Class; s.trainer._requirement = 2; break;
            case 7: scriptManager.blockState = true; break;
            case 8: s.bot.known.insert(100); break;
        }
        assert(s.List().empty());
        s.Buy();
        s.ExpectResult(false, guard == 6 ? "INVALID_TRAINER" : "NO_MATCHING_SPELL", 0, 0);
        assert(s.bot.money == 151 && s.bot.moneyChanges == 0 && scriptManager.trainCalls == 0);
    }

    Scenario wrapped;
    spellManager.spells[100].effects = {{SPELL_EFFECT_LEARN_SPELL, 101}};
    spellManager.spells[101] = {101, true, {}};
    wrapped.bot.professionsFree = 0;
    assert(wrapped.List().empty());
    wrapped.Buy();
    wrapped.ExpectResult(false, "NO_MATCHING_SPELL", 0, 0);
    assert(wrapped.bot.money == 151);
    wrapped.bot.professionsFree = 1;
    assert(wrapped.List().size() == 1);
    wrapped.Buy();
    wrapped.ExpectResult(true, "OK", 1, 95);
    assert(wrapped.bot.money == 56 && wrapped.bot.HasSpell(101));

    Scenario secondary;
    spellManager.spells[100].effects = {{SPELL_EFFECT_LEARN_SPELL, 101}};
    spellManager.spells[101] = {101, false, {}};
    secondary.bot.professionsFree = 0;
    assert(secondary.List().size() == 1 && secondary.List()[0].canAfford);
    secondary.Buy();
    secondary.ExpectResult(true, "OK", 1, 95);
    assert(secondary.bot.money == 56 && secondary.bot.HasSpell(101));
}

int main()
{
    ReproduceBudgetFailure();
    WalletBoundaries();
    WalletChangesAfterListing();
    LearnAllFreshWallet();
    GoldCheatModes();
    NativeQuotes();
    SecurityAndInteractionGuards();
    PrerequisiteGuards();
    std::cout << "MultiBot explicit trainer wallet, native costs/purchases and retained guards passed\n";
}
'''

with tempfile.TemporaryDirectory(prefix='multibot-trainer-money-') as directory:
    temporary = Path(directory)
    source = temporary / 'trainer-money.cpp'
    source.write_text(fixture + '\n' + production + '\n' + tests)
    executable = temporary / 'trainer-money'
    subprocess.run(
        ['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-g', '-O1',
         '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
         str(source), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True, timeout=30,
                   env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1:abort_on_error=1',
                        'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'})
