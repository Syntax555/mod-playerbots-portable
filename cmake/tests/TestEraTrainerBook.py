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
parser.add_argument('--dragon-source', type=Path,
                    default=repo / '.module-cache/prepared-source-addons/DragonUI')
args = parser.parse_args()
DRAGONUI = args.dragon_source
MULTIBOT = repo / '.module-cache/prepared-addons/MultiBot'
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
local companions = { MOUNT = {}, CRITTER = {} }
local skills = {}
GetNumCompanions = function(kind) return #companions[kind] end
GetCompanionInfo = function(kind, index) return 0, "Companion", companions[kind][index], "icon", false end
GetNumSkillLines = function() return #skills end
GetSkillLineInfo = function(index) return unpack(skills[index]) end
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

-- The client moves learned class mounts to the companion book, outside IsSpellKnown.
local function mountOffered()
  local filters = { trainer = Book.TrainerIndex("PALADIN"), level = 60, raceBit = Book.RaceBit("Human") }
  for _, entries in pairs(Book.UnlearnedByTree(filters)) do
    for _, entry in ipairs(entries) do if entry.spellID == 13819 then return true end end
  end
  return false
end
assert(mountOffered(), "an unlearned Warhorse stays in the native trainer catalog")
companions.MOUNT = { 13819 }
assert(not IsSpellKnown(13819) and not mountOffered(), "a learned class mount is not offered again")
companions.MOUNT = {}

-- Armor proficiencies live in the player's skill list, without a known-spell slot.
local function plateOffered()
  local filters = { trainer = Book.TrainerIndex("PALADIN"), level = 60, raceBit = Book.RaceBit("Human") }
  for _, entries in pairs(Book.UnlearnedByTree(filters)) do
    for _, entry in ipairs(entries) do if entry.spellID == 750 then return true end end
  end
  return false
end
assert(plateOffered(), "unlearned armor proficiency stays in the native trainer catalog")
skills = { { "Spell 750", 1 } }
assert(plateOffered(), "a skill header cannot stand in for a learned armor proficiency")
skills = { { "Armor", 1 }, { "Spell 750" } }
assert(not IsSpellKnown(750) and not plateOffered(), "a learned armor proficiency is not offered again")
skills = { { "Armor", 1 } }
assert(not plateOffered(), "collapsing the skill header keeps learned armor proficiency hidden")
skills = {}

-- Highest-rank slots retain separate Polymorph forms; only numeric ranks join a rank menu.
local slots = { {118, "Rang 1"}, {28272, "Schwein"}, {12824, "Rang 2"}, {28271, "Schildkröte"} }
GetSpellTabInfo = function() return "Arkan", "icon", 0, 4, 0, 3 end
GetKnownSlotFromHighestRankSlot = function(slot) return ({ 2, 3, 4 })[slot] end
GetSpellName = function(slot) return "Verwandlung", slots[slot][2] end
GetSpellTexture = function() return "icon" end
GetSpellLink = function(slot) return "|Hspell:" .. slots[slot][1] .. "|h[Verwandlung]|h" end
IsPassiveSpell = function() return false end
local variants = Book.ReadTab(1, false)
assert(#variants == 3 and variants[1].spellID == 28272 and variants[3].spellID == 28271,
  "highest-rank slots keep independent Polymorph variants")
assert(not variants[1].lower and not variants[3].lower, "Polymorph variants do not borrow sheep ranks")
assert(#variants[2].lower == 1 and variants[2].lower[1].spellID == 118,
  "numeric rank menus omit interleaved Polymorph variants")

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
-- Feature notices keep DragonUI's native levels until the server answers, then follow its gates.
local function feature(level, name) return unlocks(level, level)[name] == "feature" end
assert(feature(15, "Dungeon Finder") and feature(15, "Glyphs") and feature(30, "Major Glyph Slot")
  and feature(40, "Dual Talent Specialization"), "DragonUI's native features stay without a server reply")
ET.OnAddonMsg("ERATAL", "GLYPHS 0")
ET.OnAddonMsg("ERATAL", "UNLOCKS 0 80")
assert(not feature(15, "Dungeon Finder"), "a disabled Dungeon Finder is not announced")
assert(not feature(15, "Glyphs") and not feature(30, "Major Glyph Slot") and not feature(50, "Minor Glyph Slot")
  and not feature(80, "Major Glyph Slot"), "glyphs are not announced while the glyph gate holds")
assert(not feature(40, "Dual Talent Specialization") and feature(80, "Dual Talent Specialization"),
  "dual specialization is announced at the realm's level")
assert(feature(10, "Talent Points") and feature(10, "Battlegrounds"), "ungated features stay")
ET.OnAddonMsg("ERATAL", "GLYPHS 1")
ET.OnAddonMsg("ERATAL", "UNLOCKS 1 40")
assert(feature(15, "Dungeon Finder") and feature(15, "Glyphs") and feature(80, "Major Glyph Slot")
  and feature(40, "Dual Talent Specialization"), "enabled features keep their levels")
print("EraTalents trainer book: DragonUI level-up notice follows the era, the realm's riding and its unlocks")

-- Clique binds the player's native cards, without touching the separate bot-book renderer.
local nativeSlots = assert(io.open(dragonDir .. "/modules/spellbook/book_slots.lua")):read("*a")
assert(nativeSlots:find("card.entry = entry", 1, true), "native card entry contract")
local made = {}
local widgetMethods = {}
for _, key in ipairs({ "SetAllPoints", "ClearAllPoints", "SetPoint", "RegisterForClicks", "EnableMouseWheel", "EnableKeyboard",
                        "SetFrameLevel", "SetClampedToScreen" }) do widgetMethods[key] = function() end end
local function syncVisibility(frame)
  local visible = frame:IsVisible() ~= nil
  if visible ~= frame.visible then
    frame.visible = visible
    local handler = frame.scripts[visible and "OnShow" or "OnHide"]
    if handler then handler(frame) end
  end
  for _, child in ipairs(frame.children) do syncVisibility(child) end
end
local function widget(parent)
  local frame = { parent = parent, scripts = {}, hooks = {}, children = {}, shown = true }
  if parent then parent.children[#parent.children + 1] = frame end
  function frame:GetParent() return self.parent end
  function frame:IsShown() return self.shown and 1 or nil end
  function frame:IsVisible() return self.shown and (not self.parent or self.parent:IsVisible()) and 1 or nil end
  frame.visible = frame:IsVisible() ~= nil
  function frame:Show() self.shown = true; syncVisibility(self) end
  function frame:Hide() self.shown = false; syncVisibility(self) end
  function frame:SetParent(nextParent)
    if self.parent then
      for index, child in ipairs(self.parent.children) do
        if child == self then table.remove(self.parent.children, index); break end
      end
    end
    self.parent = nextParent
    if nextParent then nextParent.children[#nextParent.children + 1] = self end
    syncVisibility(self)
  end
  function frame:GetWidth() return 120 end
  function frame:GetLeft() return 100 end
  function frame:GetRight() return self.right or 600 end
  function frame:SetFrameStrata(strata) self.strata = strata end
  function frame:SetScript(key, callback) self.scripts[key] = callback end
  function frame:HookScript(key, callback)
    local original = self.scripts[key]
    self.hooks[key] = (self.hooks[key] or 0) + 1
    self.scripts[key] = function(...)
      if original then original(...) end
      callback(...)
    end
  end
  return setmetatable(frame, { __index = widgetMethods })
end
CreateFrame = function(_, _, parent) local frame = widget(parent); made[#made + 1] = frame; return frame end
hooksecurefunc = function(owner, key, callback)
  local original = assert(owner[key])
  owner[key] = function(...) original(...); callback(...) end
end
local bindings, repainted = {}, 0
Clique = { AddBinding = function(_, binding) bindings[#bindings + 1] = binding end,
           GetCapturedKey = function(_, key) return key == "LeftButton" and "BUTTON1" end }
UIParent = widget()
UIParent.right = 1920
local nativeTabParent, nativeConfigParent = widget(UIParent), widget(UIParent)
CliqueSpellTab = widget(nativeTabParent)
local nativeTabShows = 0
CliqueSpellTab:SetScript("OnShow", function() nativeTabShows = nativeTabShows + 1 end)
CliqueConfig = widget(nativeConfigParent)
CliqueConfig.page1 = widget(CliqueConfig)
CliqueConfig.bindAlert = widget(CliqueConfig)
CliqueConfig.ShowWithSpellBook = function(self) self:Show() end
HideUIPanel = function(window) window:Hide() end
IsAddOnLoaded = function(name) return name == "Clique" end
SpellButton1 = widget()
SpellButton1.shown = false
CliqueConfig.UpdateList = function() repainted = repainted + 1 end
local cliqueRoot = widget(UIParent)
local cliqueBook = { root = cliqueRoot, IsOpen = function() return cliqueRoot:IsShown() ~= nil end,
                    Level = function() return 6 end,
                    Locked = function() return false end,
                    PaintCard = function(card, entry) card.entry = entry end, ApplyScale = function() end }
addon.SpellbookModule = cliqueBook
assert(loadfile(dragonDir .. "/modules/spellbook/book_clique.lua"))("DragonUI", addon)
cliqueBook.InstallClique()
local card = widget()
cliqueBook.PaintCard(card, { name = "Lesser Heal", sub = "Rank 1", icon = "heal", spellID = 2050 })
local bindingOverlay = made[#made]
assert(bindingOverlay:GetParent() == card and bindingOverlay.shown, "Clique overlays the player's native card")
bindingOverlay.scripts.OnClick(bindingOverlay, "LeftButton")
assert(#bindings == 1 and bindings[1].spell == "Lesser Heal" and bindings[1].spellSubName == "Rank 1"
  and bindings[1].key == "BUTTON1" and repainted == 1, "Clique receives the native spell and rank")
card.entry.grey = true
bindingOverlay.scripts.OnClick(bindingOverlay, "LeftButton")
assert(#bindings == 1, "Clique cannot bind an unlearned trainer card")
card.entry.grey, card.entry.passive = false, true
bindingOverlay.scripts.OnClick(bindingOverlay, "LeftButton")
assert(#bindings == 1, "Clique cannot bind a passive card")
CliqueConfig.page1:Hide()
assert(not bindingOverlay.shown, "closing Clique's binding page removes its interception overlay")
cliqueBook.AdoptSideTab()
CliqueConfig:ShowWithSpellBook()
assert(CliqueSpellTab:GetParent() == cliqueBook.root and CliqueSpellTab._duiOwnParent == nativeTabParent,
  "adopting Clique's tab keeps the parent Clique gave it")
assert(CliqueConfig:GetParent() == cliqueBook.root and CliqueConfig._duiOwnParent == nativeConfigParent
  and CliqueConfig:IsShown() and CliqueConfig._duiDocked,
  "docking Clique keeps its own parent and shows its window beside the native book")
cliqueBook.root:Hide()
cliqueBook.ReleaseClique()
assert(CliqueSpellTab:GetParent() == nativeTabParent and CliqueConfig:GetParent() == nativeConfigParent
  and not CliqueConfig:IsShown() and not CliqueConfig._duiDocked,
  "release hides Clique's window and returns both widgets to their own parents")
cliqueBook.root:Show()
cliqueBook.AdoptSideTab()
CliqueConfig:ShowWithSpellBook()
local tabShowsBefore = nativeTabShows
CliqueSpellTab:Hide()
CliqueSpellTab:Show()
assert(CliqueSpellTab:GetParent() == cliqueBook.root and CliqueSpellTab.hooks.OnShow == 1
  and nativeTabShows == tabShowsBefore + 1,
  "re-enabling reuses Clique's tab and preserves its handler with one placement hook")
assert(CliqueConfig:GetParent() == cliqueBook.root and CliqueConfig._duiOwnParent == nativeConfigParent
  and CliqueConfig:IsShown() and CliqueConfig._duiDocked,
  "re-enabling docks the same Clique window without replacing its original parent")
cliqueBook.ReleaseClique()
print("DragonUI Clique: native card bindings, inactive-card guards and live parent handoffs passed")
'''

BOT_FIXTURE = r'''
local multibotDir, eraDir, packets, withDragon, dragonDir, withoutInk = ...
-- Widgets: a recording object whose scripts run like the client's.
local methods = {}
local frames = {}
local function Object(name, kind)
  local object = setmetatable({ name = name, kind = kind, scripts = {}, events = {}, shown = true, enabled = true }, {
    __index = function(self, key)
      if methods[key] then return methods[key] end
      return function() end
    end })
  return object
end
function methods:SetScript(name, handler) self.scripts[name] = handler end
function methods:GetScript(name) return self.scripts[name] end
function methods:RegisterEvent(event) self.events = self.events or {}; self.events[event] = true end
function methods:UnregisterEvent(event) self.events[event] = nil end
function methods:Show()
  if self.shown then return end
  self.shown = true
  if self.scripts.OnShow then self.scripts.OnShow(self) end
end
function methods:Hide()
  if not self.shown then return end
  self.shown = false
  if self.scripts.OnHide then self.scripts.OnHide(self) end
end
function methods:IsShown() return self.shown end
function methods:SetText(text) self.text = text end
function methods:SetFont(path, size) self.font, self.fontSize = path, size end
function methods:GetFont() return "fixture-font" end
function methods:SetTextColor(...) self.textColor = { ... } end
function methods:GetText() return self.text end
function methods:SetFormattedText(format, ...) self.text = string.format(format, ...) end
function methods:SetTexture(path) self.texture = path end
function methods:SetAtlasTexture(name)
  assert(DragonUI.atlasinfo[name], "the bot book uses an existing DragonUI atlas: " .. tostring(name))
  self.atlas = name
end
function methods:SetDesaturated(value) self.desaturated = value and true or false end
-- DragonUI's widget API (utils/core.lua) shows or hides by its argument.
function methods:SetShownCompat(show) if show then self:Show() else self:Hide() end end
function methods:Enable() self.enabled = true end
function methods:Disable() self.enabled = false end
function methods:SetID(id) self.id = id end
function methods:GetID() return self.id end
function methods:SetFrameLevel(level) self.level = level end
function methods:GetFrameLevel()
  local parent = rawget(self, "parent")
  return rawget(self, "level") or (parent and parent:GetFrameLevel() + 1) or 1
end
function methods:GetParent() return rawget(self, "parent") end
function methods:SetSize(width, height) self.width, self.height = width, height end
function methods:GetWidth() return rawget(self, "width") or 100 end
function methods:GetHeight() return rawget(self, "height") or 100 end
function methods:SetPoint(point, relative, relativePoint, x, y) self.point = { point, relative, relativePoint, x, y } end
function methods:CreateTexture()
  local texture = Object(nil, "Texture")
  texture.parent = self
  return texture
end
function methods:CreateFontString() return Object(nil, "FontString") end
for _, getter in ipairs({ "GetNormalTexture", "GetPushedTexture", "GetHighlightTexture" }) do
  methods[getter] = function(self)
    local texture = rawget(self, getter .. "Object") or Object(nil, "Texture")
    rawset(self, getter .. "Object", texture)
    return texture
  end
end
function methods:Click(button)
  if self.scripts.OnClick then self.scripts.OnClick(self, button or "LeftButton") end
end
CreateFrame = function(kind, name, parent)
  local frame = Object(name, kind)
  frame.parent = parent
  frame.shown = false
  if kind == "Frame" and not name then frame.shown = true end
  if name then _G[name] = frame end
  frames[#frames + 1] = frame
  return frame
end
UIParent = Object("UIParent")
UIParent.width, UIParent.height = 1920, 1080
UISpecialFrames = {}
for _, name in ipairs({ "GameFontHighlightLarge", "GameFontNormalSmall", "GameFontNormalHuge" }) do
  _G[name] = Object(name, "Font")
end
GENERAL = "Allgemein"
SEARCH = "Suchen"
PlaySound = function() end
PanelTemplates_TabResize = function() end
-- DragonUI's tab skin levels a tab one above its parent, four while selected.
local function DragonTabLevel(tab)
  if rawget(tab, "dragonSkin") then tab:SetFrameLevel(tab:GetParent():GetFrameLevel() + (tab.selected and 4 or 1)) end
end
PanelTemplates_SelectTab = function(tab) tab.selected = true; DragonTabLevel(tab) end
PanelTemplates_DeselectTab = function(tab) tab.selected = false; DragonTabLevel(tab) end
GameTooltip_Hide = function() end
GetCoinTextureString = function(copper) return copper .. "c" end
local shift = false
IsShiftKeyDown = function() return shift end
local tooltip = {}
GameTooltip = { SetOwner = function() tooltip = {} end, SetHyperlink = function(_, link) tooltip.link = link end,
                AddLine = function(_, text) table.insert(tooltip, text) end, Show = function() end }
local whispers, macros, actions, sent = {}, {}, {}, {}
SendChatMessage = function(text, kind, _, target) table.insert(whispers, { text, kind, target }) end
SendAddonMessage = function(prefix, message, channel, target)
  assert(prefix == "ERATAL" and channel == "WHISPER" and target == "Master")
  table.insert(sent, message)
end
UnitName = function(unit) return unit == "player" and "Master" or "Botty" end
UnitGUID = function(unit) return ({ player = "0x1", party1 = "0x2" })[unit] end
local botLevel = 30
UnitLevel = function(unit) return unit == "party1" and botLevel or 60 end
UnitClass = function() return "Krieger", "WARRIOR" end
GetLocale = function() return "deDE" end
GetTime = function() return 0 end
SlashCmdList = {}
local spellNames = { [6673] = "Schlachtruf", [12294] = "Tödlicher Stoß", [900002] = "Wrapper", [3127] = "Parieren" }
GetSpellInfo = function(id) return spellNames[id] or ("Spell " .. id), "Rang 1", "Spell_Icon_" .. id end
GetSpellLink = function(id) return "|Hspell:" .. id .. "|h[" .. (spellNames[id] or id) .. "]|h" end

-- MultiBot: its real spellbook collection and payload methods on a recording overlay.
MultiBot = { spells = {}, SpellBookUISettings = {} }
MultiBot.L = function(key) return key == "info.spellbook" and "Zauberbuch von NAME" or key end
MultiBot.IF = function(condition, yes, no) if condition then return yes end return no end
MultiBot.doReplace = function(text, key, value) return (text:gsub(key, value)) end
MultiBot.TimerAfter = function() end
MultiBot.toUnit = function(name) return name == "Botty" and "party1" or nil end
MultiBot.SpellToMacro = function(name, spell, icon) table.insert(macros, { name, spell, icon }) end
MultiBot.ActionToTarget = function(action, name) table.insert(actions, { action, name }) end
local disabled, pressed = 0, false
local unitButton = { setDisable = function() disabled = disabled + 1; pressed = false end,
                     setEnable = function() pressed = true end }
MultiBot.frames = { MultiBar = { frames = { Units = { frames = { Botty = { getButton = function(name)
  assert(name == "Spellbook")
  return unitButton
end } } } } } }
local nativeHideSync = assert(loadstring(NATIVE_HIDE_SYNC))()
SPELLBOOK = "Zauberbuch"
local overlay = { buttons = {}, texts = {} }
for _, key in ipairs({ "<", ">" }) do overlay.buttons[key] = Object() end
for i = 1, 18 do
  local index = (i < 10 and "0" or "") .. i
  for _, prefix in ipairs({ "S", "C" }) do
    local button = Object()
    button.doShow, button.doHide = function() button.shown = true end, function() button.shown = false end
    overlay.buttons[prefix .. index] = button
  end
  overlay.texts["T" .. index], overlay.texts["R" .. index] = Object(), Object()
end
for _, key in ipairs({ "<", ">" }) do
  local button = overlay.buttons[key]
  button.doShow, button.doHide = function() button.shown = true end, function() button.shown = false end
end
overlay.setButton = function(key, texture) overlay.buttons[key].texture = texture end
overlay.setText = function(key, text) overlay.texts[key] = overlay.texts[key] or Object(); overlay.texts[key].text = text end
local multibotShown, nativeVisible = 0, false
MultiBot.spellbook = { spells = {}, index = 0, frames = { Overlay = overlay }, name = "",
  Show = function(self) multibotShown = multibotShown + 1; nativeVisible = true end,
  Hide = function(self)
    self.hidden = true
    if nativeVisible then nativeVisible = false; nativeHideSync() end
  end,
  IsVisible = function() return nativeVisible end,
  setTitle = function(self, title) self.title = title end }
assert(loadfile(multibotDir .. "/UI/MultiBotSpell.lua"))()
assert(loadstring(PAYLOAD_METHODS))()

local combat = false
InCombatLockdown = function() return combat end
IsLoggedIn = function() return true end
StaticPopup_Visible = function() return nil end
GetAddOnMetadata = function() return "2.5" end
NotifyInspect, ClearInspectPlayer = function() end, function() end
tinsert, tremove, strmatch = table.insert, table.remove, string.match
strsplit = function(separator, value)
  local keys = {}; for key in value:gmatch("[^" .. separator .. "]+") do keys[#keys + 1] = key end
  return unpack(keys)
end
hooksecurefunc = function(owner, key, callback)
  if type(owner) == "string" then owner, key, callback = _G, owner, key end
  local original = assert(owner[key])
  owner[key] = function(...) original(...); callback(...) end
end
if withDragon then
  -- The native registry and book produce the running flag, combat queue and lifecycle callbacks.
  local addon = { _dir = "Interface\\AddOns\\DragonUI\\", atlasinfo = {}, L = {},
                  db = { profile = { modules = { spellbook = { enabled = false, scale = 0.8 } } } } }
  for _, file in ipairs({ "LibStub/LibStub.lua", "CallbackHandler-1.0/CallbackHandler-1.0.lua", "AceEvent-3.0/AceEvent-3.0.lua" }) do
    assert(loadfile(dragonDir .. "/libs/" .. file))()
  end
  addon.core = LibStub("AceEvent-3.0"):Embed({})
  addon.Debug = function() end
  addon.Error = function(_, ...) error(table.concat({ ... }, " ")) end
  assert(loadfile(dragonDir .. "/core/api.lua"))("DragonUI", addon)
  assert(loadfile(dragonDir .. "/core/reload.lua"))("DragonUI", addon)
  assert(loadfile(dragonDir .. "/modules/spellbook/book_core.lua"))("DragonUI", addon)
  assert(loadfile(dragonDir .. "/utils/atlas.lua"))("DragonUI", addon)
  for line in io.lines(dragonDir .. "/Locales/deDE.lua") do
    local key, value = line:match('^L%["(.-)"%]%s*=%s*"(.-)"%s*$')
    if key then addon.L[key] = value end
  end
  bit = { band = function(a, b)
    local result, place = 0, 1
    while a > 0 and b > 0 do
      if a % 2 == 1 and b % 2 == 1 then result = result + place end
      a, b, place = math.floor(a / 2), math.floor(b / 2), place * 2
    end
    return result
  end }
  for _, file in ipairs({ "book_layout.lua", "book_catalog.lua", "book_frame.lua", "book_slots.lua" }) do
    assert(loadfile(dragonDir .. "/modules/spellbook/" .. file))("DragonUI", addon)
  end
  if withoutInk then addon.SpellbookModule.InkLabel = nil end
  local book = addon.SpellbookModule
  -- Only the unused player's widgets are doubled; the lifecycle and bot renderer run their sources.
  book.BuildWindow = function() book.root = CreateFrame("Frame", "FixturePlayerBook", UIParent) end
  for _, action in ipairs({ "BuildCards", "BuildControls", "BuildSecure", "InstallAccess", "InstallClique", "ListenToBars",
                            "ApplyScale", "QueueBindings", "PlaceMicroCatcher", "HideActionGrids", "ReleaseClique" }) do
    book[action] = function() end
  end
  book.CloseBook = function() book.root:Hide() end
  book.Rebuild = function() book.dirty = {} end
  addon.CharacterPanel = { ReskinTab = function(tab) tab.dragonSkin = true end }
  DragonUI = addon
  DragonUI_NineSlice = { ApplyLayout = function() end, GetLayout = function() return {} end }
end
for _, file in ipairs({ "Locales.lua", "EraTalents.lua", "Comms.lua", "DragonUIBook.lua", "BotBook.lua" }) do
  assert(loadfile(eraDir .. "/" .. file))()
end
local ET = EraTalents
local L = ET.L
ET.state = { ranks = {} }
ET.InitBotBook()

local function collect(ids)
  local book = MultiBot.spellbook
  book.name = "Botty"
  book:beginPayload("Botty")
  for _, id in ipairs(ids) do book:appendSpellId(id, "Botty") end
  book:finishPayload()
end

if not withDragon or withoutInk then
  assert(not MultiBot.spellbook._eraBotBook, "without DragonUI MultiBot's own window stays unhooked")
  local opened = pcall(collect, { 6673, 12294, 900002 })
  assert(opened and multibotShown == 1 and EraTalentsBotBookFrame == nil, "without DragonUI MultiBot keeps its own spellbook")
  print("EraTalents bot spellbook: MultiBot's own window without DragonUI")
  return
end
assert(MultiBot.spellbook._eraBotBook, "a disabled compatible book is ready for live enable")
local show, handlers = MultiBot.spellbook.Show, #ET.bookHandlers
ET.InitBotBook()
assert(MultiBot.spellbook.Show == show and #ET.bookHandlers == handlers,
  "initialization installs the wrappers and lifecycle hooks once")
collect({ 6673, 12294, 900002 })
assert(multibotShown == 1 and nativeVisible and EraTalentsBotBookFrame == nil and pressed,
  "disabled at login uses MultiBot's own window")
assert(DragonUI:SetModuleEnabled("spellbook", true) and DragonUI.SpellbookModule.applied,
  "the native registry enables the book without another EraTalents initialization")
local book = EraTalentsBotBookFrame
local CLASS, GENERAL = 1, 2
assert(multibotShown == 1 and not nativeVisible and book:IsShown() and pressed,
  "live enable hands the open MultiBot book to DragonUI")
assert(book.art.wood.atlas == "spellbook-header-left-half"
  and book.art.woodRight.atlas == "spellbook-header-right-half" and book.art.woodRight:IsShown()
  and book.art.wood.point[3] == "TOP" and book.art.wood.point[4] == 0,
  "the wide bot book draws DragonUI's two header halves up to the page center")
local empty = book.empty
assert(empty.font == "fixture-font" and empty.fontSize == 16
  and empty.textColor[1] == DragonUI.SpellbookModule.INK[1]
  and empty.textColor[2] == DragonUI.SpellbookModule.INK[2]
  and empty.textColor[3] == DragonUI.SpellbookModule.INK[3], "bot labels use DragonUI's own font helper and ink")
assert(book.title.text == "Zauberbuch von Botty", "the book names the bot")
assert(sent[#sent] == "BOOK 0x2", "the bot's trainer book is requested by its GUID")
assert(book.wide, "the bot book uses two pages on the large screen")
UIParent.width, UIParent.height = 800, 600
DragonUI.core:SendMessage("DRAGONUI_UI_SCALE_CHANGED")
assert(not book.wide and book:IsShown() and pressed and not nativeVisible,
  "DragonUI's scale message refits the open bot book through its native scale handler")
UIParent.width, UIParent.height = 1920, 1080
DragonUI.core:SendMessage("DRAGONUI_UI_SCALE_CHANGED")
assert(book.wide and book:IsShown() and pressed and not nativeVisible,
  "restoring screen space refits the same open bot book without changing its owner")
assert(book.tabs[GENERAL].text == "Allgemein" and book.tabs[CLASS].text == "Krieger",
  "DragonUI's two tabs: the general book and the bot's class")
assert(book.tabs[GENERAL].point[4] < book.tabs[CLASS].point[4], "the general tab comes first, as in DragonUI")
local function tabsInFront()
  local paper = book.art.wood.parent:GetFrameLevel()
  return book.tabs[GENERAL]:GetFrameLevel() > paper and book.tabs[CLASS]:GetFrameLevel() > paper
end
assert(tabsInFront(), "both tabs stay in front of the book's wood strip, selected or not")

local function cards()
  local shown = {}
  for _, card in ipairs(book.cards) do
    if card.shown and card.entry then
      table.insert(shown, { id = card.entry.spellID, sub = card.sub.text, grey = card.entry.grey,
                            desaturated = card.icon.desaturated, card = card })
    end
  end
  return shown
end
local function titles()
  local shown = {}
  for _, header in ipairs(book.headers) do
    if header.shown then table.insert(shown, header.title.text) end
  end
  return table.concat(shown, ",")
end
local function search(text)
  book.search:SetText(text)
  book.search.scripts.OnTextChanged(book.search)
end

local early = cards()
assert(#early == 3 and early[1].id == 6673 and not early[1].grey and book.selected == GENERAL,
  "before the bot's book its learned spells open in the general book")
for _, packet in ipairs(packets) do
  if packet[1] == "bot" then ET.OnAddonMsg("ERATAL", packet[2]) end
end
assert(book.selected == CLASS and titles() == L["Arms"] .. "," .. L["Fury"] .. "," .. L["Protection"],
  "with the bot's trainer book the class book opens, a section per talent tree as in DragonUI")
assert(tabsInFront(), "both tabs stay in front of the book's wood strip after switching")
local class, byID, order = cards(), {}, {}
for index, entry in ipairs(class) do byID[entry.id], order[entry.id] = entry, index end
assert(order[12294] < order[6673] and order[6673] < order[900002], "learned spells sit in their tree's section")
assert(byID[6673].sub == "Rang 1" and not byID[6673].grey, "a learned spell keeps its rank")
assert(byID[5242] == nil, "a started chain shows no grey first rank")
assert(byID[900030].grey and byID[900030].sub == "Erlernbar" and byID[900030].desaturated,
  "a ready trainer spell is grey, worded like DragonUI")
if withDragon then
  assert(byID[900030].card.halo.shown and byID[900030].card.scroll.shown and not byID[6673].card.halo.shown
    and not byID[900050].card.scroll.shown, "only a ready trainer spell gets DragonUI's trainer halo and scroll")
end
assert(byID[900050].sub == "Benötigt Spell 900051", "a trainer spell names what it needs")
assert(byID[900040].sub == "Rang 1  (Benötigt Talent)", "an era talent rank waits for its talent, as in DragonUI")
botLevel = 25
ET.RenderBotBook()
for _, entry in ipairs(cards()) do
  if entry.id == 900030 then
    assert(entry.sub == "Verfügbar ab Level 30", "a trainer spell above the bot's level gives DragonUI's level line")
  end
end
botLevel = 30
ET.RenderBotBook()
book.tabs[GENERAL]:Click()
local general = cards()
assert(book.selected == GENERAL and general[1].id == 3127 and general[1].sub == "Erlernbar",
  "general trainer spells have their own tab")
book.tabs[CLASS]:Click()

-- DragonUI's search: the class book keeps only matching spells and their sections.
search("tödlich")
assert(#cards() == 1 and cards()[1].id == 12294 and titles() == L["Arms"], "the search keeps matching spells")
search("")
assert(#cards() == #class, "clearing the search restores the book")

-- MultiBot's actions: cast, macro and the skip list; grey cards stay inert.
byID = {}
for _, entry in ipairs(cards()) do byID[entry.id] = entry end
byID[6673].card:Click("LeftButton")
assert(whispers[#whispers][1] == "cast 6673" and whispers[#whispers][3] == "Botty", "left-click casts through MultiBot's whisper")
byID[6673].card:Click("RightButton")
assert(macros[#macros][1] == "Botty" and macros[#macros][2] == 6673, "right-click creates MultiBot's macro")
local before = #whispers
byID[900030].card:Click("LeftButton")
assert(#whispers == before and #macros == 1, "a spell not learned yet cannot be cast")
shift = true
byID[6673].card:Click("LeftButton")
assert(MultiBot.spells.Botty[6673] == false and actions[#actions][1] == "ss +6673", "shift-click puts the spell on the skip list")
local skipped
for _, entry in ipairs(cards()) do if entry.id == 6673 then skipped = entry end end
assert(skipped.sub == "|cffff2020Vom Bot übersprungen|r" and skipped.desaturated, "a skipped spell is marked")
skipped.card:Click("LeftButton")
assert(MultiBot.spells.Botty[6673] == true and actions[#actions][1] == "ss -6673", "shift-click takes it off again")
shift = false

-- A higher rank learned without the lower one still counts as the started chain.
collect({ 5242, 12294 })
local ranks = {}
for _, entry in ipairs(cards()) do ranks[entry.id] = entry end
assert(ranks[5242] and not ranks[5242].grey and ranks[6673] == nil, "a known higher rank hides its chain's first rank")

-- DragonUI's spreads: two pages of nine rows of three, one page in single-page mode.
local many = { 6673, 12294, 900002 }
for id = 960000, 960069 do table.insert(many, id) end
collect(many)
book.tabs[GENERAL]:Click()
assert(#cards() == 54 and book.next.enabled and not book.prev.enabled and book.pageText.text == "Seite 1/2",
  "the general book fills a spread of two pages")
book.next:Click()
assert(book.pageText.text == "Seite 2/2" and #cards() == 17 and book.prev.enabled, "the pager turns to the next spread")
book.mode:Click()
assert(book.pageText.text == "Seite 2/3" and #cards() == 27, "single-page mode shows one page per spread")
assert(not book.art.woodRight:IsShown() and book.art.wood.point[3] == "TOPRIGHT" and book.art.wood.point[4] == -8,
  "the single-page bot book stretches only its left header half")
assert(DragonUI:SetModuleEnabled("spellbook", false) and not DragonUI.SpellbookModule.applied,
  "the native registry restores the disabled book immediately")
assert(multibotShown == 2 and nativeVisible and not book:IsShown() and MultiBot.spellbook:IsVisible() and pressed,
  "disabling DragonUI's spellbook hands the open bot book to MultiBot")
assert(DragonUI:SetModuleEnabled("spellbook", true), "the native registry re-enables the existing book")
assert(multibotShown == 2 and not nativeVisible and book:IsShown() and MultiBot.spellbook:IsVisible() and pressed,
  "enabling DragonUI's spellbook hands the open MultiBot book back")
combat = true
assert(not DragonUI:SetModuleEnabled("spellbook", false) and DragonUI:IsModuleEnabled("spellbook")
  and book:IsShown() and not nativeVisible, "combat leaves the running route intact until the native queue runs")
assert(not DragonUI:SetModuleEnabled("spellbook", true) and not DragonUI.CombatQueue:HasPending("spellbook_toggle"),
  "reverting a queued disable preserves the running bot book")
assert(not DragonUI:SetModuleEnabled("spellbook", false), "a second combat disable can be queued")
combat = false
DragonUI_CombatQueueFrame.scripts.OnEvent(DragonUI_CombatQueueFrame, "PLAYER_REGEN_ENABLED")
assert(not DragonUI:IsModuleEnabled("spellbook") and not book:IsShown() and nativeVisible and pressed,
  "the native post-combat callback hands off the open bot book")
DragonUI:SetModuleEnabled("spellbook", true)
local nativeBook = DragonUI.SpellbookModule
local epoch = nativeBook.epoch
for _, frame in ipairs(frames) do
  if frame.events and frame.events.SPELLS_CHANGED then frame.scripts.OnEvent(frame, "SPELLS_CHANGED") end
end
assert(nativeBook.epoch == epoch + 1, "live toggles keep one native spell-change listener")
MultiBot.spellbook:Hide()
assert(not book:IsShown() and not MultiBot.spellbook:IsVisible() and not pressed,
  "MultiBot's hide closes the book and releases its button")
DragonUI:SetModuleEnabled("spellbook", false)
DragonUI:SetModuleEnabled("spellbook", true)
assert(not book:IsShown() and not nativeVisible and not pressed,
  "toggling the module keeps a closed bot book closed")
print("EraTalents bot spellbook: DragonUI's book with the bot's spells, trainer spells, search and MultiBot's actions")
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

# (label, file, old, new, with DragonUI) in the bot spellbook.
BOT_MUTATIONS = [
    ('native scale handler', 'BotBook.lua',
     '  if type(book.ApplyScale) == "function" then hooksecurefunc(book, "ApplyScale", Render) end\n', '', True),
    ('disabled login installs hooks', 'BotBook.lua', 'or not book or spellbook._eraBotBook',
     'or not DragonBookOn() or spellbook._eraBotBook', True),
    ('live enable handoff', 'BotBook.lua', '{ "RefreshSpellbookSystem", "RestoreSpellbookSystem" }',
     '{ "RestoreSpellbookSystem" }', True),
    ('live disable handoff', 'BotBook.lua', '{ "RefreshSpellbookSystem", "RestoreSpellbookSystem" }',
     '{ "RefreshSpellbookSystem" }', True),
    ('wide header joins at center', 'BotBook.lua', 'wide and "TOP" or "TOPRIGHT", wide and 0 or -8, -26',
     '"TOPRIGHT", -8, -26', True),
    ('single-page header hides right half', 'BotBook.lua',
     '  if wide then art.woodRight:Show() else art.woodRight:Hide() end', '  art.woodRight:Show()', True),
    ('native helper required', 'BotBook.lua', 'type(book.InkLabel) ~= "function" or ', '', 'missing-ink'),
    ('native font helper', 'BotBook.lua', 'return DragonBook().InkLabel(parent, layer, fontObject, size)',
     'return parent:CreateFontString(nil, layer, fontObject)', True),
    ('runtime module preference', 'BotBook.lua', '    if not DragonBookOn() then\n', '    if false then\n', True),
    ('fallback closes bot book', 'BotBook.lua', '      if frame then frame:Hide() end\n', '', True),
    ('native window closes', 'BotBook.lua', '    if visible(self) then hide(self) end\n', '', True),
    ('native handoff button', 'BotBook.lua', '      SetSpellbookButton(self.name, true)\n', '', True),
    ('DragonUI handoff button', 'BotBook.lua', '  SetSpellbookButton(name, true)\n', '', True),
    ('DragonUI only', 'BotBook.lua', 'if type(spellbook) ~= "table" or not book or', 'if type(spellbook) ~= "table" or', False),
    ('DragonUI spellbook on', 'BotBook.lua', 'or dragon:IsModuleEnabled("spellbook")', 'or true', True),
    ('bot book request', 'BotBook.lua', '  if guid then ET.RequestBook(guid) end\n', '', True),
    ('started chains', 'BotBook.lua', '      answer = answer or knownInChain(record[2])\n', '', True),
    ('learned spell tree', 'BotBook.lua', '    return record and record[8] or 0', '    return 0', True),
    ('grey cards inert', 'BotBook.lua', '  if not entry or entry.grey then return end', '  if not entry then return end', True),
    ('trainer halo on ready spells', 'BotBook.lua', 'grey and "squareOff" or "square", grey and entry.state == "ready")',
     'grey and "squareOff" or "square", grey)', True),
    ('skip list', 'BotBook.lua', '  spells[spellID] = not spells[spellID]\n', '', True),
    ('shift-click skips', 'BotBook.lua', 'if IsShiftKeyDown and IsShiftKeyDown() then', 'if false then', True),
    ('book refresh', 'BotBook.lua', '  if unit and UnitGUID(unit) == guid then Render() end', '', True),
    ('class book first', 'BotBook.lua', 'view.cat = #ET.BotBookSections(trees, CLASS, names, nil) > 0 and CLASS or GENERAL',
     'view.cat = GENERAL', True),
    ('tree sections', 'BotBook.lua', '    for tree = 1, 3 do add(names[tree], trees[tree]) end',
     '    for tree = 1, 3 do add(nil, trees[tree]) end', True),
    ('search filter', 'BotBook.lua', '      if Matches(entry, query) then kept[#kept + 1] = entry end',
     '      kept[#kept + 1] = entry', True),
    ('two-page spreads', 'BotBook.lua', 'view.query), wide and 2 or 1,', 'view.query), 1,', True),
    ('DragonUI wording', 'BotBook.lua', 'local text = dragon and type(dragon.L) == "table" and rawget(dragon.L, key) or nil',
     'local text = nil', True),
    ('tabs above the paper', 'BotBook.lua', '"EraTalentsBotBookFrameTab" .. cat, holder,',
     '"EraTalentsBotBookFrameTab" .. cat, frame,', True),
    ('general tab first', 'BotBook.lua', 'local TAB_ORDER = { GENERAL, CLASS }', 'local TAB_ORDER = { CLASS, GENERAL }', True),
    ('button release', 'BotBook.lua', '    SetSpellbookButton(view.name, false)\n', '', True),
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
    ('feature rows ignored', 'DragonUIBook.lua', '  if key == "features" then return FeatureRows(base) end\n', ''),
    ('realm Dungeon Finder switch', 'DragonUIBook.lua',
     '\n        and not (feature == "dungeonFinder" and state.dungeonFinder == false)', ''),
    ('glyph gate notices', 'DragonUIBook.lua', 'not (GLYPH_FEATURES[feature] and state.glyphsAllowed == false)', 'true'),
    ('realm dual-spec level', 'DragonUIBook.lua', 'if feature == "dualSpec" and state.dualSpecLevel then', 'if false then'),
    ('unlocks reply ignored', 'Comms.lua', '    ET.state.dungeonFinder = finder == "1"\n', ''),
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


NATIVE_SHOWN = (DRAGONUI / 'utils/core.lua').read_text()
assert 'api.SetShownCompat = function(widget, show)\n\tif show then\n\t\twidget:Show()\n\telse\n\t\twidget:Hide()' in NATIVE_SHOWN


def run_bot_client(directory, era_dir, packets, with_dragon):
    lua = shutil.which('lua5.1') or shutil.which('lua')
    frame = (MULTIBOT / 'UI/MultiBotSpellBookFrame.lua').read_text()
    assert 'window.frame:HookScript("OnHide", syncSpellbookButtonStateOnHide)' in frame
    start = frame.index('\tMultiBot.spellbook.beginPayload = function(self, botName)')
    payload = frame[start:frame.index('\tfor i = 1, GetNumMacroIcons() do', start)]
    hide_sync = frame[frame.index('local function getUnitsRootFrame()'):frame.index('local function createSpellbookContent(window)')]
    rows = ',\n'.join(f'{{{json.dumps(label)},{json.dumps(body)}}}' for label, body in packets)
    script = directory / 'bot-client.lua'
    script.write_text('local function fixture(...)\n' + BOT_FIXTURE.replace('assert(loadstring(PAYLOAD_METHODS))()', payload)
                      .replace('local nativeHideSync = assert(loadstring(NATIVE_HIDE_SYNC))()',
                               hide_sync + '\nlocal nativeHideSync = syncSpellbookButtonStateOnHide')
                      + '\nend\n' + f'fixture({json.dumps(str(MULTIBOT))}, {json.dumps(str(era_dir))}, {{{rows}}}, '
                      + ('true' if with_dragon else 'false') + f', {json.dumps(str(DRAGONUI))}, '
                      + ('true' if with_dragon == 'missing-ink' else 'false') + ')\n')
    return run_fixture([lua, str(script)], 'era trainer book bot client')


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
    dragon_source = DRAGONUI
    for index, (label, filename, old, new) in enumerate((
            ('learned class mount', 'book_catalog.lua',
             'IsSpellKnown(spellID) or knownCompanion(spellID, filters)', 'IsSpellKnown(spellID)'),
            ('learned armor proficiency', 'book_catalog.lua', ' or knownSkill(spellID, filters)', ''),
            ('skill headers excluded', 'book_catalog.lua', 'if name and not isHeader then', 'if name then'),
            ('collapsed skill proficiency retained', 'book_catalog.lua', '        filters.skillsRead = true\n',
             '        filters.skillsRead = true\n        skillNames = {}\n'),
            ('variant owns no numeric ranks', 'book_catalog.lua',
             '    if not isRankText(entry.sub) then return end\n', ''),
            ('rank menu excludes variants', 'book_catalog.lua',
             '        if isRankText(rank) then', '        if true then'),
            ('Clique unlearned and passive cards', 'book_clique.lua',
             'return entry ~= nil and not entry.grey and not entry.passive', 'return entry ~= nil'),
            ('Clique tab parent restored', 'book_clique.lua', '        tab:SetParent(tab._duiOwnParent)\n', ''),
            ('Clique window parent restored', 'book_clique.lua', '        config:SetParent(config._duiOwnParent)\n', ''),
            ('Clique released window hidden', 'book_clique.lua',
             '        config:Hide()\n        config:SetParent(config._duiOwnParent)',
             '        config:SetParent(config._duiOwnParent)'),
            ('level-up features bypass integrations', 'levelupenhance.lua',
             'ipairs(data.features or EMPTY)', 'ipairs(rawget(data, "features") or EMPTY)'))):
        dragon_copy = directory / f'dragon-catalog-{index}'
        for part in ('modules/spellbook', 'modules/levelupenhance'):
            shutil.copytree(DRAGONUI / part, dragon_copy / part)
        path = dragon_copy / ('modules/levelupenhance' if filename.startswith('levelup') else 'modules/spellbook') / filename
        text = path.read_text()
        if text.count(old) != 1:
            raise SystemExit(f'{label} catalog mutation was not applied')
        path.write_text(text.replace(old, new, 1))
        DRAGONUI = dragon_copy
        mutated = run_client(directory, client, packets)
        DRAGONUI = dragon_source
        if mutated.returncode == 0 or not re.search(r'client\.lua:\d+: ', mutated.stderr):
            raise SystemExit(f'The native DragonUI catalog fixture did not reject {label}:\n{mutated.stderr}')
        print(f'DragonUI catalog mutation rejected: {label}')
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

    for with_dragon in (True, False, 'missing-ink'):
        outcome = run_bot_client(directory, client, packets, with_dragon)
        if outcome.returncode:
            raise SystemExit(outcome.stdout + outcome.stderr)
        print(outcome.stdout, end='')
    for index, (label, file, old, new, with_dragon) in enumerate(BOT_MUTATIONS):
        copy = directory / f'bot-client-{index}'
        shutil.copytree(client, copy)
        text = (copy / file).read_text()
        if text.count(old) != 1:
            raise SystemExit(f'{label} mutation was not applied')
        (copy / file).write_text(text.replace(old, new))
        mutated = run_bot_client(directory, copy, packets, with_dragon)
        if mutated.returncode == 0:
            raise SystemExit(f'The era trainer book bot client fixture did not reject {label}')
        if not re.search(r'bot-client\.lua:\d+: ', mutated.stderr):
            raise SystemExit(f'{label} mutant failed outside the fixture assertions:\n{mutated.stderr}')
        print(f'Era trainer book bot client mutation rejected: {label}')
    for (label, *_), outcome in zip(MUTATIONS, in_parallel(mutant, enumerate(MUTATIONS))):
        if outcome.returncode == 0:
            raise SystemExit(f'The era trainer book fixture did not reject {label}')
        print(f'Era trainer book mutation rejected: {label}')
