"""Check the EraTalents trainer book against the core's own trainer list.

Requires PrepareModules.cmake, a C++20 compiler and Lua 5.1. No realm or
database is started. The fixture compiles the production book builder, the
ERATAL BOOK reply and the core's Trainer list, state and cost functions against
the same doubles, so a book must hold exactly what the trainer window lists for
that character. Its replies then feed DragonUI's real spellbook catalogue and
level-up builder through the EraTalents client. Mutants that drop a gate must
fail.
"""

import argparse
import json
from pathlib import Path
import re
import shutil
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


repo = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--module-source', type=Path,
                    default=prepared_core(repo) / 'modules/mod-era-talents')
parser.add_argument('--core-source', type=Path, default=prepared_core(repo))
args = parser.parse_args()
DRAGONUI = repo / '.module-cache/prepared-source-addons/DragonUI'
module, core = args.module_source, args.core_source
training = (module / 'src/EraTrainerBook.cpp').read_text()
comms = (module / 'src/EraTalentsComms.cpp').read_text()
header = (module / 'src/EraTrainerBook.h').read_text()
trainer = (core / 'src/server/game/Entities/Creature/Trainer.cpp').read_text()
shared = (core / 'src/server/shared/SharedDefines.h').read_text()
packets = (core / 'src/server/game/Server/Packets/NPCPackets.h').read_text()


# The book passes no creature to the list and cost hooks; that only matches the trainer
# window while no hook reads its creature argument.
hooks = ('OnPlayerBeforeReceiveSpellListFromTrainer', 'OnPlayerGetTrainerSpellCost')
overrides = []
for source in sorted((core / 'modules').glob('*/src/**/*.cpp')):
    text = source.read_text(errors='replace')
    for hook in hooks:
        for match in re.finditer(r'void ' + hook + r'\(([^)]*)\)\s*override', text):
            overrides.append((source, hook))
            creature = match.group(1).split(',')[1]
            assert re.fullmatch(r'\s*Creature(?: const)?\s*\*\s*/\*\s*\w+\s*\*/\s*', creature), (source, hook, creature)
assert {hook for _, hook in overrides} == set(hooks), overrides

skill_enum = re.search(r'^enum SkillType\n\{.*?^\};', shared, re.MULTILINE | re.DOTALL).group(0)
list_spell = re.search(r'    struct TrainerListSpell\n    \{.*?\n    \};', packets, re.DOTALL).group(0)
book_entry = re.search(r'struct Entry\n\{.*?\n\};', header, re.DOTALL).group(0)
tree_skills = re.search(r'constexpr std::array<std::array<uint32, 3>, MAX_CLASSES> kTreeSkills = \{\{.*?\n\}\};',
                        training, re.DOTALL).group(0)

COMMON = r'''
#pragma once
#include <cstdint>
#include <string>
using uint8 = std::uint8_t; using uint16 = std::uint16_t; using uint32 = std::uint32_t;
using int32 = std::int32_t; using uint64 = std::uint64_t;
#define AC_GAME_API
enum LocaleConstant { LOCALE_enUS = 0, TOTAL_LOCALES = 16 };
#define DEFAULT_LOCALE LOCALE_enUS
'''

FIXTURE = r'''
#include <algorithm>
#include <cassert>
#include <cctype>
#include <cmath>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include "Common.h"
#include "Trainer.h"
#include "IteratorPair.h"
#define MAX_CLASSES 12
#define MAX_MONEY_AMOUNT (0x7FFFFFFF-1)
#define MOD_PLAYERBOTS
constexpr uint32 SPELL_EFFECT_LEARN_SPELL = 36;
constexpr size_t kMaxGuidToken = 18, kMaxChunkBody = 230;
enum EraId : uint8 { ERA_VANILLA = 0, ERA_TBC = 1, ERA_WOTLK = 2 };
// NATIVE_SKILLS
template<typename E> constexpr auto AsUnderlyingType(E value) { return static_cast<std::underlying_type_t<E>>(value); }

struct ObjectGuid {
    uint64 raw = 0;
    ObjectGuid() = default;
    explicit ObjectGuid(uint64 value) : raw(value) {}
    bool operator==(ObjectGuid const&) const = default;
};
struct Creature { ObjectGuid guid{ 99 }; ObjectGuid GetGUID() const { return guid; } };
struct Group {};
struct PlayerbotAI {};
#define GET_PLAYERBOT_AI(player) ((player)->ai)

namespace WorldPackets::NPC {
// NATIVE_LIST_SPELL
struct TrainerList {
    ObjectGuid TrainerGUID; int32 TrainerType = 0; std::vector<TrainerListSpell> Spells; std::string Greeting;
    TrainerList const* Write() const { return this; }
};
}

struct SpellEffectInfo {
    uint32 effect = 0, TriggerSpell = 0;
    bool IsEffect(uint32 type) const { return effect == type; }
};
struct SpellInfo {
    std::vector<SpellEffectInfo> effects; bool professionFirst = false;
    std::vector<SpellEffectInfo> const& GetEffects() const { return effects; }
    bool HasEffect(uint32 type) const {
        return std::any_of(effects.begin(), effects.end(), [type](auto const& e) { return e.IsEffect(type); });
    }
    bool IsPrimaryProfessionFirstRank() const { return professionFirst; }
};
struct SkillLineAbilityEntry { uint32 SkillLine = 0; };
using SkillLineAbilityMap = std::multimap<uint32, SkillLineAbilityEntry const*>;
using SkillLineAbilityMapBounds = std::pair<SkillLineAbilityMap::const_iterator, SkillLineAbilityMap::const_iterator>;
struct SpellMgr {
    std::map<uint32, SpellInfo> infos; std::map<uint32, uint32> previous; std::multimap<uint32, uint32> required;
    SkillLineAbilityMap abilities; std::set<uint32> additionalTalents;
    SpellInfo const* GetSpellInfo(uint32 id) const { auto i = infos.find(id); return i == infos.end() ? nullptr : &i->second; }
    SpellInfo const* AssertSpellInfo(uint32 id) const { auto info = GetSpellInfo(id); assert(info); return info; }
    uint32 GetPrevSpellInChain(uint32 id) const { auto i = previous.find(id); return i == previous.end() ? 0 : i->second; }
    uint32 GetFirstSpellInChain(uint32 id) const {
        if (!previous.count(id) && std::none_of(previous.begin(), previous.end(), [id](auto const& p) { return p.second == id; }))
            return 0;  // Like the core: a spell outside spell_ranks has no chain.
        while (uint32 prev = GetPrevSpellInChain(id)) id = prev;
        return id;
    }
    Acore::IteratorPair<std::multimap<uint32, uint32>::const_iterator> GetSpellsRequiredForSpellBounds(uint32 id) const {
        return Acore::IteratorPair(required.equal_range(id));
    }
    SkillLineAbilityMapBounds GetSkillLineAbilityMapBounds(uint32 id) const { return abilities.equal_range(id); }
    bool IsAdditionalTalentSpell(uint32 id) const { return additionalTalents.count(id) > 0; }
} spellMgr;
auto* sSpellMgr = &spellMgr;
std::set<uint32> stockTalents;
uint32 GetTalentSpellCost(uint32 id) { return stockTalents.count(id) ? 1 : 0; }

struct Player {
    uint64 guid = 0; uint8 cls = 1, race = 2, level = 60; EraId era = ERA_VANILLA;
    std::set<uint32> spells, unfit; Group* group = nullptr; PlayerbotAI* ai = nullptr;
    std::vector<WorldPackets::NPC::TrainerList> sent;
    ObjectGuid GetGUID() const { return ObjectGuid(guid); }
    uint8 getClass() const { return cls; }
    uint8 getRace() const { return race; }
    uint8 GetLevel() const { return level; }
    Group* GetGroup() const { return group; }
    bool HasSpell(uint32 id) const { return spells.count(id) > 0; }
    bool IsSpellFitByClassAndRace(uint32 id) const { return !unfit.count(id); }
    uint32 GetBaseSkillValue(uint32) const { return 0; }
    uint32 GetFreePrimaryProfessionPoints() const { return 0; }
    float GetReputationPriceDiscount(Creature const*) const { return 1.0f; }
    void SendDirectMessage(WorldPackets::NPC::TrainerList const* list) { sent.push_back(*list); }
};

struct Scripts {
    std::set<uint32> refused, unavailable; std::map<uint32, uint32> quotes;
    std::vector<std::vector<WorldPackets::NPC::TrainerListSpell>> offered;
    void OnPlayerBeforeReceiveSpellListFromTrainer(Player*, Creature*, WorldPackets::NPC::TrainerList& list) {
        offered.push_back(list.Spells);
        std::erase_if(list.Spells, [&](auto const& s) { return refused.count(uint32(s.SpellID)) > 0; });
    }
    void OnPlayerGetTrainerSpellCost(Player const*, Creature const*, uint32 spell, uint32& cost) {
        if (auto quote = quotes.find(spell); quote != quotes.end()) cost = quote->second;
    }
    void OnPlayerGetTrainerSpellState(Player const*, uint32, uint32 spell, Trainer::SpellState& state) {
        if (unavailable.count(spell)) state = Trainer::SpellState::Unavailable;
    }
} scripts;
auto* sScriptMgr = &scripts;

namespace Trainer {
// NATIVE_TRAINER
}

struct CreatureTemplate {};
struct ObjectMgr {
    std::unordered_map<uint8, std::vector<Trainer::Trainer const*>> classTrainers;
    std::unordered_map<uint32, CreatureTemplate> templates; std::unordered_map<uint32, Trainer::Trainer*> byCreature;
    std::vector<Trainer::Trainer const*> const& GetClassTrainers(uint8 cls) const { return classTrainers.at(cls); }
    std::unordered_map<uint32, CreatureTemplate> const* GetCreatureTemplates() const { return &templates; }
    Trainer::Trainer* GetTrainer(uint32 entry) { auto i = byCreature.find(entry); return i == byCreature.end() ? nullptr : i->second; }
} objectMgr;
auto* sObjectMgr = &objectMgr;

struct EraTalentNode { std::vector<uint32> rankSpell; uint8 era = 0, cls = 0; };
struct Content {
    std::vector<EraTalentNode> nodes;
    std::vector<EraTalentNode const*> NodesFor(uint8 era, uint8 cls) const {
        std::vector<EraTalentNode const*> found;
        for (auto const& node : nodes) if (node.era == era && node.cls == cls) found.push_back(&node);
        return found;
    }
} content;
auto* sEraTalentContent = &content;
namespace EraTalentBots { EraId EraFor(Player* player) { return player->era; } }
namespace EraTrainerBook {
// NATIVE_BOOK_ENTRY
}
namespace {
// NATIVE_BOOK
}
namespace EraTrainerBook {
// NATIVE_BOOK_API
}
namespace ObjectAccessor {
std::map<uint64, Player*> players;
Player* FindPlayer(ObjectGuid guid) { auto i = players.find(guid.raw); return i == players.end() ? nullptr : i->second; }
}
namespace {
// NATIVE_COMMS
}

Trainer::Spell Row(uint32 spell, uint8 level, uint32 cost, std::array<uint32, 3> abilities = {}) {
    Trainer::Spell row; row.SpellId = spell; row.ReqLevel = level; row.MoneyCost = cost; row.ReqAbility = abilities;
    return row;
}

std::vector<std::unique_ptr<SkillLineAbilityEntry>> abilityRows;

void Spell(uint32 id, uint32 skill = 0, uint32 previous = 0, uint32 teaches = 0) {
    SpellInfo& info = spellMgr.infos[id];
    if (teaches) info.effects.push_back({ SPELL_EFFECT_LEARN_SPELL, teaches });
    if (previous) spellMgr.previous[id] = previous;
    if (skill) spellMgr.abilities.emplace(id, abilityRows.emplace_back(new SkillLineAbilityEntry{ skill }).get());
}

std::string Expect(std::vector<std::string> records) {
    std::string out;
    for (auto const& record : records) out += (out.empty() ? "" : ",") + record;
    return out;
}

// The records of one reply's chunks with every chunk's header and sentinel removed.
std::string Records(std::vector<std::string> const& reply, std::string const& head) {
    std::vector<std::string> bodies;
    std::string const verb = head.substr(0, head.find(' ') + 1);
    for (auto const& body : reply) if (body.starts_with(verb)) bodies.push_back(body);
    std::string out;
    for (size_t i = 0; i < bodies.size(); ++i) {
        assert(bodies[i].size() <= kMaxChunkBody && bodies[i].starts_with(head));
        std::string rest = bodies[i].substr(head.size());
        if (bodies.size() > 1) {
            std::string sentinel = std::to_string(i + 1) + "/" + std::to_string(bodies.size()) + " ";
            assert(rest.starts_with(sentinel));
            rest = rest.substr(sentinel.size());
        }
        out += (out.empty() || rest.empty() ? "" : ",") + rest;
    }
    return out;
}

int main() {
    // Stock warrior rows: Battle Shout ranks, a talent rank, a wrapper, a racial and a refused variant.
    Spell(6673, SKILL_FURY); Spell(5242, SKILL_FURY, 6673);
    Spell(12294, SKILL_ARMS); Spell(21551, SKILL_ARMS, 12294); stockTalents.insert(12294);
    Spell(900001, 0, 0, 900002); Spell(900002, SKILL_PROTECTION);
    Spell(900010, SKILL_ARMS); Spell(900020, SKILL_ARMS); Spell(900030, SKILL_FURY);
    Spell(900041, SKILL_PROTECTION); Spell(900040, SKILL_PROTECTION, 900041);
    Spell(900051); Spell(900050, SKILL_FURY); Spell(900061); Spell(900060, SKILL_FURY);
    spellMgr.required.emplace(900060, 900061);
    Spell(3127, 95);
    content.nodes.push_back({ { 900041, 0, 0 }, ERA_VANILLA, 1 });
    content.nodes.push_back({ { 900099 }, ERA_TBC, 1 });

    std::vector<Trainer::Spell> classRows = {
        Row(6673, 1, 10), Row(5242, 12, 1000, { 6673 }), Row(21551, 48, 2000, { 12294 }), Row(900001, 20, 4000),
        Row(900010, 20, 4000), Row(900020, 20, 4000), Row(900030, 30, 5000), Row(900040, 40, 6000, { 900041 }),
        Row(900050, 30, 7000, { 900051 }), Row(900060, 30, 8000), Row(3127, 6, 100),
    };
    Trainer::Trainer warrior(1, Trainer::Type::Class, 1, "", classRows);
    Trainer::Trainer novice(2, Trainer::Type::Class, 1, "", { Row(6673, 4, 10), Row(5242, 10, 900, { 6673 }) });
    Trainer::Trainer novicesFirst(3, Trainer::Type::Class, 1, "", { Row(5242, 10, 900, { 6673 }) });
    objectMgr.classTrainers[1] = { &warrior };

    Player self; self.guid = 1; self.cls = 1; self.race = 2; self.unfit = { 900010 };
    scripts.refused = { 900020 };
    scripts.quotes = { { 900030, 12345 } };
    Creature npc;

    // The book's list is the trainer window's list: same rows into the hook, same rows out of it.
    warrior.SendSpells(&npc, &self, LOCALE_enUS);
    assert(self.sent.size() == 1 && scripts.offered.size() == 1);
    auto window = self.sent.back().Spells;
    auto listed = ListedSpells(&self, { &warrior });
    assert(scripts.offered.size() == 2 && scripts.offered[0].size() == scripts.offered[1].size());
    for (size_t i = 0; i < scripts.offered[0].size(); ++i) {
        auto const& a = scripts.offered[0][i]; auto const& b = scripts.offered[1][i];
        assert(a.SpellID == b.SpellID && a.Usable == b.Usable && a.MoneyCost == b.MoneyCost && a.ReqLevel == b.ReqLevel);
        assert(a.ReqSkillLine == b.ReqSkillLine && a.ReqSkillRank == b.ReqSkillRank && a.ReqAbility == b.ReqAbility);
    }
    assert(listed.size() == window.size());
    for (size_t i = 0; i < listed.size(); ++i) {
        assert(uint32(window[i].SpellID) == listed[i]->SpellId);
        assert(uint32(window[i].MoneyCost) == BaseCost(&self, *listed[i]));
        assert(warrior.GetSpellCost(&self, &npc, listed[i]) == BaseCost(&self, *listed[i]));
    }
    // A known spell and a scripted refusal keep the public state the window shows.
    self.spells = { 6673 };
    scripts.unavailable = { 900050 };
    scripts.offered.clear(); self.sent.clear();
    warrior.SendSpells(&npc, &self, LOCALE_enUS); ListedSpells(&self, { &warrior });
    for (size_t i = 0; i < scripts.offered[0].size(); ++i)
        assert(scripts.offered[0][i].Usable == scripts.offered[1][i].Usable);
    self.spells.clear(); scripts.unavailable.clear();

    std::string const vanilla = Expect({
        "1:6673:10:0:0:0:2", "6:3127:100:0:0:0:0", "12:5242:1000:6673:0:0:2", "20:900002:4000:0:0:0:3",
        "30:900030:12345:0:0:0:2", "30:900050:7000:0:0:900051:2", "30:900060:8000:0:0:900061:2",
        "40:900040:6000:900041:900041:0:3", "48:21551:2000:12294:12294:0:1" });
    auto token = [](uint64 guid) { std::ostringstream out; out << "0x" << std::hex << std::uppercase << guid; return out.str(); };
    std::string const me = token(1);
    auto reply = BuildBook(&self, me);
    std::vector<std::string> book, riding;
    for (auto const& body : reply) (body.starts_with("RIDING ") ? riding : book).push_back(body);
    assert(Records(book, "BOOK " + me + " 1 ") == vanilla);
    assert(riding.size() == 1 && riding[0] == "RIDING " + me + " ");
    for (auto const& body : reply) std::cout << "PACKET self~" << body << '\n';

    // An era talent only counts in its own era; the stock talent in every era.
    self.era = ERA_TBC;
    std::string tbc = Records(BuildBook(&self, me), "BOOK " + me + " 1 ");
    assert(tbc.find("40:900040:6000:900041:0:0:3") != std::string::npos);
    assert(tbc.find("48:21551:2000:12294:12294:0:1") != std::string::npos);
    self.era = ERA_VANILLA;

    // Several class trainers: one row per spell at the lowest level any of them asks.
    objectMgr.classTrainers[1] = { &warrior, &novice, &novicesFirst };
    std::string merged = Records(BuildBook(&self, me), "BOOK " + me + " 1 ");
    assert(merged.starts_with("1:6673:10:0:0:0:2,6:3127:100:0:0:0:0,10:5242:900:6673:0:0:2,"));
    objectMgr.classTrainers[1] = { &warrior };

    // Riding: every creature's mount trainer once, its race requirement kept.
    Spell(33388); Spell(33391, 762, 33388); Spell(900070);
    scripts.quotes[33388] = 900000;
    Trainer::Trainer riding1(35, Trainer::Type::Mount, 0, "", { Row(33388, 40, 40000), Row(33391, 60, 500000) });
    Trainer::Trainer riding2(36, Trainer::Type::Mount, 5, "", { Row(900070, 40, 1) });
    for (uint32 entry : { 100u, 101u, 102u, 103u, 104u }) objectMgr.templates[entry];
    objectMgr.byCreature = { { 100, &riding1 }, { 101, &riding2 }, { 102, &riding1 }, { 103, &warrior } };
    riding.clear();
    for (auto const& body : BuildBook(&self, me)) if (body.starts_with("RIDING ")) riding.push_back(body);
    assert(Records(riding, "RIDING " + me + " ") == "40:33388:900000:0:0:0:0,60:33391:500000:33388:0:0:0");

    // A bot's book: the requester's group only, bots only, and without riding levels.
    Group party, other; PlayerbotAI ai;
    Player bot; bot.guid = 2; bot.cls = 1; bot.unfit = self.unfit; bot.ai = &ai; bot.group = &party;
    Player friendPlayer; friendPlayer.guid = 3; friendPlayer.cls = 1; friendPlayer.group = &party;
    ObjectAccessor::players = { { 2, &bot }, { 3, &friendPlayer } };
    self.group = &party;
    auto botReply = BuildBook(&self, token(2));
    assert(Records(botReply, "BOOK " + token(2) + " 1 ") == vanilla);
    for (auto const& body : botReply) assert(!body.starts_with("RIDING "));
    for (auto const& body : botReply) std::cout << "PACKET bot~" << body << '\n';
    auto denied = [&](std::string const& t) { return BuildBook(&self, t) == std::vector<std::string>{ "BOOK " + t.substr(0, kMaxGuidToken) + " 0" }; };
    assert(denied(token(3)));
    bot.group = &other; assert(denied(token(2)));
    bot.group = nullptr; self.group = nullptr; assert(denied(token(2)));
    bot.group = &party; self.group = &party; assert(!denied(token(2)));
    assert(denied(token(4)));
    for (std::string const malformed : { "", "0x", "nope", "0x1!", "0x000000000000000100" }) assert(denied(malformed));

    // A chunked book reassembles to the same records.
    for (uint32 i = 0; i < 40; ++i) { Spell(910000 + i, SKILL_ARMS); classRows.push_back(Row(910000 + i, 60, 100000)); }
    Trainer::Trainer large(4, Trainer::Type::Class, 1, "", classRows);
    objectMgr.classTrainers[1] = { &large };
    auto chunks = BuildBook(&self, me);
    std::vector<std::string> largeBook;
    for (auto const& body : chunks) if (body.starts_with("BOOK ")) largeBook.push_back(body);
    assert(largeBook.size() > 3);
    for (auto const& body : chunks) std::cout << "PACKET large~" << body << '\n';
    std::string records = Records(largeBook, "BOOK " + me + " 1 ");
    assert(records.starts_with(vanilla + ",60:910000:100000:0:0:0:1,") && std::count(records.begin(), records.end(), ',') == 48);

    objectMgr.classTrainers.erase(1);
    assert(Records(BuildBook(&self, me), "BOOK " + me + " 1 ").empty());
    std::cout << "Era trainer book: trainer window list, costs, ranks, talents, trees, riding and bot gates passed\n";
}
'''

trainer_functions = '\n'.join(function(trainer, signature) for signature in (
    '    bool Spell::IsCastable(', '    Trainer::Trainer(uint32 trainerId', '    void Trainer::SendSpells(',
    '    uint32 Trainer::GetSpellCost(', '    bool Trainer::CanTeachSpell(', '    SpellState Trainer::GetSpellState(',
    '    SpellState Trainer::GetDefaultSpellState(', '    bool Trainer::IsTrainerValidForPlayer(',
    '    std::string const& Trainer::GetGreeting('))
book = '\n'.join([tree_skills] + [function(training, signature) for signature in (
    'uint8 BookTree(', 'bool IsTalentSpell(', 'uint32 BaseCost(',
    'std::vector<Trainer::Spell const*> ListedSpells(', 'std::vector<EraTrainerBook::Entry> Book(')])
book_api = '\n'.join(function(training, signature) for signature in (
    'std::vector<Entry> ClassBook(', 'std::vector<Entry> RidingBook('))
comms_functions = '\n'.join(function(comms, signature) for signature in (
    '    std::vector<std::string> ChunkRankList(', '    bool ParseGuidToken(', '    Player* BookSubject(',
    '    std::string BookList(', '    std::vector<std::string> BuildBook('))


def fixture_source(book_source, api_source, comms_source):
    return (FIXTURE.replace('// NATIVE_SKILLS', skill_enum).replace('// NATIVE_LIST_SPELL', list_spell)
            .replace('// NATIVE_TRAINER', trainer_functions).replace('// NATIVE_BOOK_ENTRY', book_entry)
            .replace('// NATIVE_BOOK_API', api_source).replace('// NATIVE_BOOK', book_source)
            .replace('// NATIVE_COMMS', comms_source))


LUA_FIXTURE = r'''
local dragonDir, eraDir, packets = ...
local function band(a, b)
  local result, power = 0, 1
  while a > 0 and b > 0 do
    if a % 2 == 1 and b % 2 == 1 then result = result + power end
    a, b, power = math.floor(a / 2), math.floor(b / 2), power * 2
  end
  return result
end
bit = { band = band }
local frames = {}
CreateFrame = function()
  local frame = { scripts = {}, events = {}, shown = true }
  function frame:RegisterEvent(event) self.events[event] = true end
  function frame:SetScript(name, handler) self.scripts[name] = handler end
  function frame:Show() self.shown = true end
  function frame:Hide() self.shown = false end
  table.insert(frames, frame)
  return frame
end
local sent, known = {}, {}
SendAddonMessage = function(prefix, message, channel, target)
  assert(prefix == "ERATAL" and channel == "WHISPER" and target == "Master")
  table.insert(sent, message)
end
UnitName = function() return "Master" end
UnitGUID = function(unit) return unit == "player" and "0x1" or nil end
UnitClass = function() return "Krieger", "WARRIOR" end
UnitRace = function() return "Orc", "Orc" end
GetSpellInfo = function(id) return "Spell " .. id, "", "icon" .. id end
IsSpellKnown = function(id) return known[id] == true end
GetTime = function() return 0 end
GetLocale = function() return "deDE" end
SlashCmdList = {}

local addon = { L = setmetatable({}, { __index = function(_, key) return key end }), _dir = "",
                Fonts = { PRIMARY = "font" } }
local modules = {}
function addon:IsModuleEnabled() return true end
function addon:RegisterModule(name, module) modules[name] = module end
TALENT_POINTS, BATTLEGROUNDS, LOOKING_FOR_DUNGEON, GLYPHS = "Talent Points", "Battlegrounds", "Dungeon Finder", "Glyphs"
LEVEL_RANGE = "Level Range"
local expansions, unknown = {}, {}
for _, id in ipairs({ 136, 137, 138, 140, 146, 147, 148, 149, 150, 151, 170, 171, 172, 173, 174, 198,
                      175, 176, 177, 193, 194, 195, 196, 197, 199 }) do expansions[id] = 1 end
for _, id in ipairs({ 202, 203, 204, 206, 207, 208, 209, 214, 216, 218, 220, 225, 245, 251, 253, 255,
                      46, 159, 223, 224, 239, 243, 246, 279, 293 }) do expansions[id] = 2 end
GetLFGDungeonInfo = function(id)
  if unknown[id] then return nil end
  return "Dungeon " .. id, 1, 1, 80, 1, 1, 80, expansions[id] or 0
end
GetNumBattlegroundTypes = function() return 0 end
UnitFactionGroup = function() return "Horde" end
EXPANSION_NAME1, EXPANSION_NAME2 = "The Burning Crusade", "Wrath of the Lich King"
local Book = { initialized = false, applied = false }
addon.SpellbookModule = Book
local rebuilt = 0
function Book.MarkAllDirty() rebuilt = rebuilt + 1 end
DragonUI = addon
assert(loadfile(dragonDir .. "/modules/spellbook/trainerdata.lua"))("DragonUI", addon)
assert(loadfile(dragonDir .. "/modules/spellbook/book_catalog.lua"))("DragonUI", addon)
assert(loadfile(dragonDir .. "/modules/levelupenhance/levelupdata.lua"))("DragonUI", addon)
assert(loadfile(dragonDir .. "/modules/levelupenhance/levelupenhance.lua"))("DragonUI", addon)
local LevelUp = assert(modules.levelupenhance, "DragonUI registers its level-up module")
for _, file in ipairs({ "Locales.lua", "EraTalents.lua", "Comms.lua", "DragonUIBook.lua" }) do
  assert(loadfile(eraDir .. "/" .. file))()
end
local ET = EraTalents
ET.state = { ranks = {} }
ET.InitDragonUIBook()

-- DragonUI's own level-up builder, as its banner and chat lines call it.
local function unlocks(from, to)
  local found = {}
  for _, entry in ipairs(LevelUp.BuildCharacterUnlocks(from, to, 0)) do
    found[entry.spellID or entry.text] = entry.kind
  end
  return found
end
assert(unlocks(20, 20)[33388] == "feature", "DragonUI's riding table is kept until the realm's arrives")

local function tick(seconds)
  for _, frame in ipairs(frames) do
    if frame.shown and frame.scripts.OnUpdate then frame.scripts.OnUpdate(frame, seconds) end
  end
end
local function deliver(label, last)
  for index, packet in ipairs(packets) do
    if packet[1] == label and (last == nil or index <= last) then ET.OnAddonMsg("ERATAL", packet[2]) end
  end
end

-- One request a moment after login and after every talent sync, never one per message.
tick(0.5); assert(#sent == 0, "the book waits for the burst to end")
tick(0.6); assert(sent[1] == "BOOK 0x1" and #sent == 1, "the player's own book is requested")
ET.OnAddonMsg("ERATAL", "SYNC 0 1 5 ")
ET.OnAddonMsg("ERATAL", "SYNC 0 1 4 ")
tick(1.1); assert(sent[2] == "BOOK 0x1" and #sent == 2, "a talent sync requests a fresh book once")
for _, frame in ipairs(frames) do
  if frame.events.LEARNED_SPELL_IN_TAB then frame.scripts.OnEvent(frame, "LEARNED_SPELL_IN_TAB", 1) end
end
tick(1.1); assert(sent[3] == "BOOK 0x1" and #sent == 3, "learning a spell requests a fresh book")

local wotlk = Book.TrainerIndex("WARRIOR")
assert(wotlk.byID[23920] and wotlk.byID[23920][1] == 64, "DragonUI's own table lists Spell Reflection")
local selfPackets, lastSelf = 0, 0
for index, packet in ipairs(packets) do
  if packet[1] == "self" and packet[2]:match("^BOOK ") then selfPackets, lastSelf = selfPackets + 1, index end
end
assert(selfPackets > 1, "the fixture book arrives in chunks")
deliver("self", lastSelf - 1)
assert(Book.TrainerIndex("WARRIOR") == wotlk and rebuilt == 0, "a partial book replaces nothing")
deliver("self")
local own = Book.TrainerIndex("WARRIOR")
assert(own ~= wotlk and rebuilt == 1, "the complete book replaces DragonUI's table and rebuilds it")
assert(own.byID[23920] == nil, "a spell the trainer does not list is not offered")
assert(Book.TrainerIndex("PRIEST") ~= own and Book.TrainerIndex("PRIEST").byID[589], "other classes keep DragonUI's table")
local listed = {}
for _, record in ipairs(own.list) do table.insert(listed, table.concat(record, ":")) end
assert(table.concat(listed, ",") == "1:6673:10:0:0:0:0:2,6:3127:100:0:0:0:0:0,12:5242:1000:6673:0:0:0:2,"
  .. "20:900002:4000:0:0:0:0:3,30:900030:12345:0:0:0:0:2,30:900050:7000:0:0:0:900051:2,"
  .. "30:900060:8000:0:0:0:900061:2,40:900040:6000:900041:900041:0:0:3,48:21551:2000:12294:12294:0:0:1",
  "records keep the server's values in DragonUI's order")
assert(own.after[6673][1][2] == 5242 and own.after[12294][1][2] == 21551, "ranks chain by previous rank")
assert(ET.books.riding["0x1"] and #ET.books.riding["0x1"].records == 0, "riding levels arrive after the book")

-- DragonUI's own grey cards read the server's book.
local function cards()
  local filters = { trainer = Book.TrainerIndex("WARRIOR"), level = 60, raceBit = Book.RaceBit("Orc"),
                    allRanks = false, hideUnlearned = false }
  local byID = {}
  for tree, list in pairs(Book.UnlearnedByTree(filters)) do
    for _, entry in ipairs(list) do byID[entry.spellID] = { tree = tree, state = entry.state, needs = entry.needs } end
  end
  return byID
end
local grey = cards()
assert(grey[6673].tree == 2 and grey[6673].state == "ready", "a trainable spell is ready")
assert(grey[3127].tree == 0, "a general spell is in the general book")
assert(grey[21551].tree == 1 and grey[21551].state == "talent", "a talent rank needs its talent")
assert(grey[900040].state == "talent", "an era talent rank needs its era talent")
assert(grey[900050].state == "later" and grey[900050].needs == 900051, "a required spell is named")
assert(grey[5242] == nil and grey[900002].tree == 3, "later ranks follow their first rank")
known[12294] = true
assert(cards()[21551] == nil, "a known talent shows its rank on the talent's own card")

-- Another character's book and partial chunks never touch the player's own table.
deliver("bot")
assert(Book.TrainerIndex("WARRIOR") == own and rebuilt == 1, "a bot's book stays the bot's")
assert(ET.books.class["0x2"].classId == 1 and #ET.books.class["0x2"].records == 9, "the bot's book is kept by GUID")
ET.OnAddonMsg("ERATAL", "BOOK 0x3 0")
assert(ET.books.class["0x3"].classId == 0 and #ET.books.class["0x3"].records == 0, "a refusal is an empty book")
ET.OnAddonMsg("ERATAL", "BOOK 0x4 1 2/3 1:6673:10:0:0:0:2")
assert(ET.books.class["0x4"] == nil, "a continuation without its first chunk is ignored")
deliver("large")
local large = Book.TrainerIndex("WARRIOR")
assert(large ~= own and #large.list == 49 and rebuilt == 2, "every chunk of a long book is kept")
print("EraTalents trainer book: DragonUI spellbook uses the complete own book only")

-- The level-up notice: the realm's riding levels and only instances of the earned era.
ET.state.era = 0
local vanilla = unlocks(57, 60)
assert(vanilla["Dungeon 136"] == nil and vanilla["Dungeon 137"] == nil and vanilla["Dungeon 140"] == nil,
  "Outland dungeons are not announced before TBC")
assert(vanilla["Dungeon 48"] == "raid" and unlocks(55, 55)["Dungeon 40"] == "dungeon", "Vanilla instances stay")
unknown[40] = true
local hidden = unlocks(55, 55)
assert(hidden["Dungeon 40"] == nil and hidden["Stratholme - Main Gate"] == nil and hidden["Dungeon 2"] == "dungeon",
  "an instance of unknown expansion is not announced")
unknown[40] = nil
ET.state.era = 1
local tbc = unlocks(68, 70)
assert(tbc["Dungeon 202"] == nil and tbc["Dungeon 225"] == nil and tbc["Dungeon 204"] == nil,
  "Northrend dungeons are not announced before Wrath")
assert(tbc["Dungeon 171"] == "dungeon" and tbc["Dungeon 175"] == "raid" and tbc["The Burning Crusade"] == "heroic",
  "TBC instances and heroic modes stay")
assert(unlocks(80, 80)["Wrath of the Lich King"] == nil, "Wrath heroic modes are not announced before Wrath")
ET.state.era = 2
assert(unlocks(68, 69)["Dungeon 202"] == "dungeon" and unlocks(80, 80)["Wrath of the Lich King"] == "heroic",
  "Wrath characters keep every instance")
ET.state.era = 0
assert(unlocks(30, 30)[900030] == "spell" and unlocks(64, 64)[23920] == nil, "class spells come from the own book")
assert(unlocks(20, 20)[33388] == nil and unlocks(40, 40)[33388] == "feature" and unlocks(60, 60)[33391] == "feature",
  "riding levels come from the realm's riding trainers")
print("EraTalents trainer book: DragonUI level-up notice follows the era and the realm's riding")
'''

# (label, part, old, new): each removes one rule the book must keep.
MUTATIONS = [
    ('trainer list hook', 'book', '    sScriptMgr->OnPlayerBeforeReceiveSpellListFromTrainer(player, nullptr, list);\n', ''),
    ('class and race fit', 'book', '            if (!player->IsSpellFitByClassAndRace(spell.SpellId))\n                continue;\n', ''),
    ('trainer requirement', 'book', '        if (!trainer->IsTrainerValidForPlayer(player))\n            continue;\n', ''),
    ('trainer cost hook', 'book', '    sScriptMgr->OnPlayerGetTrainerSpellCost(player, nullptr, spell.SpellId, cost);\n', ''),
    ('taught spell', 'book', 'taught.push_back(effect.TriggerSpell);', 'taught.push_back(spell->SpellId);'),
    ('lowest trainer level', 'book', 'spell.ReqLevel < rows[slot->second].second->ReqLevel', 'false'),
    ('era talent ranks', 'book', 'sEraTalentContent->NodesFor(uint8(era), player->getClass())',
     'std::vector<EraTalentNode const*>()'),
    ('talent tab order', 'book', 'return tree + 1;', 'return 3 - tree;'),
    ('previous rank requirement', 'book', 'ability && ability != entry.previousRank && ', 'ability && '),
    ('mount trainers only', 'api', 'trainer && trainer->GetTrainerType() == Trainer::Type::Mount && ', 'trainer && '),
    ('requester group', 'comms', 'requester->GetGroup() && target->GetGroup() == requester->GetGroup()', 'true'),
    ('bots only', 'comms', 'target && GET_PLAYERBOT_AI(target) && ', 'target && '),
    ('riding for the requester', 'comms', '        if (subject == requester)\n', ''),
]

# (label, file, old, new) in the EraTalents client.
CLIENT_MUTATIONS = [
    ('player class only', 'DragonUIBook.lua', 'if ownIndex and classToken == select(2, UnitClass("player")) then',
     'if ownIndex then'),
    ('own book only', 'DragonUIBook.lua', 'if kind ~= "class" or guid ~= UnitGUID("player") then return end',
     'if kind ~= "class" then return end'),
    ('complete books only', 'Comms.lua', '    if complete then\n', '    if true then\n'),
    ('spellbook rebuild', 'DragonUIBook.lua', 'book.MarkAllDirty() end', 'end'),
    ('talent sync refresh', 'DragonUIBook.lua', '  table.insert(ET.syncHandlers, ET.RefreshOwnBook)\n', ''),
    ('request delay', 'DragonUIBook.lua', 'if waited < BOOK_DELAY then return end', ''),
    ('realm riding levels', 'DragonUIBook.lua', '    if riding and not riding.partial then return riding.records end\n', ''),
    ('earned era instances', 'DragonUIBook.lua', 'if expansion and expansion <= era then', 'if true then'),
    ('unknown instance expansion', 'DragonUIBook.lua', 'if expansion and expansion <= era then',
     'if (expansion or 0) <= era then'),
    ('heroic mode expansion', 'DragonUIBook.lua',
     'if key ~= "heroics" then expansion = select(8, GetLFGDungeonInfo(row[2])) end',
     'expansion = select(8, GetLFGDungeonInfo(row[2]))'),
]


def build(directory, name, source, warnings=('-Wall', '-Wextra', '-Werror')):
    path = directory / (name + '.cpp')
    path.write_text(source)
    command = [cxx(), '-std=c++20', *warnings, *SANITIZER_FLAGS, '-no-pie',
               '-I', str(directory / 'include'), '-I', str(core / 'src/server/game/Entities/Creature'),
               '-I', str(core / 'src/common/Utilities'), str(path), '-o', str(directory / name)]
    subprocess.run(command, check=True)
    return run_fixture([str(directory / name)], name)


def run_client(directory, era_dir, packets):
    lua = shutil.which('lua5.1') or shutil.which('lua')
    if not lua:
        raise SystemExit('Lua 5.1 is required')
    script = directory / 'client.lua'
    rows = ',\n'.join(f'{{{json.dumps(label)},{json.dumps(body)}}}' for label, body in packets)
    script.write_text('local function fixture(...)\n' + LUA_FIXTURE + '\nend\n'
                      f'fixture({json.dumps(str(DRAGONUI))}, {json.dumps(str(era_dir))}, {{{rows}}})\n')
    return run_fixture([lua, str(script)], 'era trainer book client')


with tempfile.TemporaryDirectory(prefix='portable-era-trainer-book-') as temporary:
    directory = Path(temporary)
    (directory / 'include').mkdir()
    (directory / 'include/Common.h').write_text(COMMON)
    parts = {'book': book, 'api': book_api, 'comms': comms_functions}

    def mutant(numbered):
        index, (label, part, old, new) = numbered
        if parts[part].count(old) != 1:
            raise SystemExit(f'{label} mutation was not applied')
        changed = dict(parts, **{part: parts[part].replace(old, new)})
        # A removed check can leave a parameter unused; only the result decides.
        return build(directory, f'mutant-{index}', fixture_source(changed['book'], changed['api'], changed['comms']), ())

    result = build(directory, 'era-trainer-book', fixture_source(book, book_api, comms_functions))
    if result.returncode:
        raise SystemExit(result.stdout + result.stderr)
    packets = [line[len('PACKET '):].split('~', 1) for line in result.stdout.splitlines() if line.startswith('PACKET ')]
    print(''.join(line + '\n' for line in result.stdout.splitlines() if not line.startswith('PACKET ')), end='')

    client = module / 'client-addon/EraTalents'
    outcome = run_client(directory, client, packets)
    if outcome.returncode:
        raise SystemExit(outcome.stdout + outcome.stderr)
    print(outcome.stdout, end='')
    for index, (label, file, old, new) in enumerate(CLIENT_MUTATIONS):
        copy = directory / f'client-{index}'
        shutil.copytree(client, copy)
        text = (copy / file).read_text()
        if text.count(old) != 1:
            raise SystemExit(f'{label} mutation was not applied')
        (copy / file).write_text(text.replace(old, new))
        mutated = run_client(directory, copy, packets)
        if mutated.returncode == 0:
            raise SystemExit(f'The era trainer book client fixture did not reject {label}')
        if not re.search(r'client\.lua:\d+: ', mutated.stderr):
            raise SystemExit(f'{label} mutant failed outside the fixture assertions:\n{mutated.stderr}')
        print(f'Era trainer book client mutation rejected: {label}')
    for (label, *_), outcome in zip(MUTATIONS, in_parallel(mutant, enumerate(MUTATIONS))):
        if outcome.returncode == 0:
            raise SystemExit(f'The era trainer book fixture did not reject {label}')
        print(f'Era trainer book mutation rejected: {label}')
