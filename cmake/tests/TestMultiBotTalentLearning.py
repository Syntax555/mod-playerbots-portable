"""Exercise targeted historical talent purchases through the production chat hook.

The real command parser, inspect gates and Playerbots altbot classification run
against controlled player state. TryLearn is the boundary: its budget, era and
prerequisite rules are exercised separately by TestEraTalents.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import tempfile

from FixtureSupport import SANITIZER_FLAGS, cxx, function, prepared_core, run_fixture


ROOT = Path(__file__).resolve().parents[2]

ADAPTERS = r'''
#include <algorithm>
#include <cassert>
#include <cctype>
#include <cstdint>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>
using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
using uint64 = std::uint64_t;
constexpr uint32 INSPECT_DISTANCE = 28, CONFIG_TALENTS_INSPECTING = 0, LANG_ADDON = 0xFFFFFFFF;
enum EraId : uint8 { ERA_VANILLA, ERA_TBC, ERA_WOTLK };
// AUTHORED_IDS
struct ObjectGuid {
    uint64 raw = 0; ObjectGuid() = default; explicit ObjectGuid(uint64 value) : raw(value) {}
    bool operator==(ObjectGuid const&) const = default;
};
struct Group {};
struct Session { bool headless = false; bool IsHeadless() const { return headless; } };
class PlayerbotAI;
struct Player {
    uint64 guid = 0;
    uint8 cls = 1;
    EraId era = ERA_VANILLA, stored = ERA_VANILLA;
    Group* group = nullptr;
    Session session;
    PlayerbotAI* ai = nullptr;
    bool inRange = true, enemy = false, gm = false, random = false, rejectLearn = false;
    int points = 2, learns = 0, attempts = 0;
    std::unordered_map<uint32, uint8> ranks;
    std::vector<std::string> messages;
    uint8 getClass() const { return cls; }
    ObjectGuid GetGUID() const { return ObjectGuid(guid); }
    Group* GetGroup() const { return group; }
    Session* GetSession() { return &session; }
    bool IsWithinDistInMap(Player* target, uint32 distance, bool) const {
        assert(distance == INSPECT_DISTANCE); return target->inRange;
    }
    bool IsValidAttackTarget(Player* target) const { return target->enemy; }
    bool CanBeGameMaster() const { return gm; }
    void Whisper(std::string const& body, uint32 language, Player* recipient) {
        assert(language == LANG_ADDON && recipient == this && body.starts_with("ERATAL\t"));
        messages.push_back(body.substr(7));
    }
};
class PlayerbotAI {
public:
    Player* bot = nullptr;
    Player* master = nullptr;
    Player* GetMaster() { return master; }
    bool IsAltBot();
    bool HasGameClientMaster();
};
struct PlayerbotsMgr {
    PlayerbotAI* GetPlayerbotAI(Player* player) { return player ? player->ai : nullptr; }
} sPlayerbotsMgr;
#define GET_PLAYERBOT_AI(player) sPlayerbotsMgr.GetPlayerbotAI(player)
struct RandomPlayerbotMgr { bool IsRandomBot(Player* player) { return player->random; } } sRandomPlayerbotMgr;
// CLASSIFICATION
struct Config {
    bool enabled = true, bots = true, glyphGate = true;
    bool Enabled() const { return enabled; }
    bool BotTalents() const { return bots; }
    bool GlyphGate() const { return glyphGate; }
} config;
auto* sEraTalentsConfig = &config;
EraId EraFromIP(Player* player) { return player->era; }
bool EraHasTalentTrees(Player* player, EraId era) { return player && player->cls != 6 && era != ERA_WOTLK; }
namespace EraTransition { EraId StoredEra(Player* player) { return player->stored; } }
namespace EraTalentBots {
// ERA_GATES
}
constexpr uint8 CLASS_DEATH_KNIGHT = 6;
namespace EraGlyphGate {
// GLYPH_GATE
}
struct EraTalentNode { uint32 id; uint8 era, cls; };
struct Content {
    EraTalentNode nodes[2]{{kVanillaTalentId, ERA_VANILLA, 1}, {kTbcTalentId, ERA_TBC, 1}};
    std::vector<EraTalentNode const*> NodesFor(uint8 era, uint8 cls) {
        std::vector<EraTalentNode const*> found;
        for (auto const& node : nodes) if (node.era == era && node.cls == cls) found.push_back(&node);
        return found;
    }
    std::string const& GenerationStamp() { static std::string stamp = "a1b2c3d4"; return stamp; }
} content;
auto* sEraTalentContent = &content;
namespace EraTalents {
auto Ranks(Player* player, EraId) { return player->ranks; }
int AvailablePoints(Player* player, EraId era) { assert(era == player->stored); return player->points; }
bool TryLearn(Player* player, uint32 talentId, std::string&) {
    ++player->attempts;
    uint32 expected = player->stored == ERA_TBC ? kTbcTalentId : kVanillaTalentId;
    if (player->rejectLearn || player->points <= 0 || player->era != player->stored || talentId != expected) return false;
    ++player->learns; --player->points; ++player->ranks[talentId]; return true;
}
}
namespace ObjectAccessor {
std::map<uint64, Player*> players;
Player* GetPlayer(Player const&, ObjectGuid const& guid) {
    auto found = players.find(guid.raw); return found == players.end() ? nullptr : found->second;
}
Player* FindPlayer(ObjectGuid const& guid) {
    auto found = players.find(guid.raw); return found == players.end() ? nullptr : found->second;
}
}
// The trainer book's own fixture runs its producer; the handler only relays a subject's book.
namespace EraTrainerBook {
// BOOK_ENTRY
std::vector<Entry> ClassBook(Player* player) { return {{1, 6673, 10, 0, 0, 0, uint8(player->cls)}}; }
std::vector<Entry> RidingBook(Player*) { return {{40, 33388, 40000, 0, 0, 0, 0}}; }
}
constexpr uint32 CONFIG_MIN_DUALSPEC_LEVEL = 1;
struct World
{
    bool inspect = true; uint32 dualSpecLevel = 80;
    bool getBoolConfig(uint32) const { return inspect; }
    uint32 getIntConfig(uint32 index) const { assert(index == CONFIG_MIN_DUALSPEC_LEVEL); return dualSpecLevel; }
} world;
auto* sWorld = &world;
namespace lfg { constexpr uint32 LFG_OPTION_ENABLE_DUNGEON_FINDER = 0x01; }
// LFGMgr::isOptionEnabled tests its option mask.
struct LFGMgr { uint32 options = 0; bool isOptionEnabled(uint32 option) const { return options & option; } } lfgMgr;
auto* sLFGMgr = &lfgMgr;
class PlayerScript {
public:
    explicit PlayerScript(char const*) {}
    virtual ~PlayerScript() = default;
    virtual void OnPlayerBeforeSendChatMessage(Player*, uint32&, uint32&, std::string&) = 0;
};
'''

TESTS = r'''
struct Scenario {
    Player owner, bot, stranger;
    PlayerbotAI ai, ownerAI, strangerAI;
    Group group, otherGroup;
    era_talents_comms handler;
    Scenario() {
        config = {}; world = {};
        owner.guid = 1; owner.era = owner.stored = ERA_WOTLK; owner.points = 71; owner.group = &group;
        bot.guid = 2; bot.group = &group; bot.ai = &ai;
        ai.bot = &bot; ai.master = &owner;
        stranger.guid = 3; stranger.group = &group;
        ObjectAccessor::players = {{1, &owner}, {2, &bot}, {3, &stranger}};
    }
    void Send(std::string const& body, uint32 language = LANG_ADDON, std::string const& prefix = "ERATAL") {
        owner.messages.clear();
        uint32 type = 7;
        std::string message = prefix + "\t" + body;
        handler.OnPlayerBeforeSendChatMessage(&owner, type, language, message);
        assert(type == 7);
    }
    bool Has(std::string const& prefix) const {
        return std::any_of(owner.messages.begin(), owner.messages.end(), [&](std::string const& message) {
            return message.starts_with(prefix);
        });
    }
    void Inspect() { Send("INSPECT 0x0000000000000002"); }
    void Learn() {
        Send("ILEARN 0x0000000000000002 " + std::to_string(bot.stored == ERA_TBC ? kTbcTalentId : kVanillaTalentId));
    }
    void Denied() {
        Inspect();
        assert(!Has("IEDIT 0x0000000000000002 1 "));
        Learn();
        assert(bot.attempts == 0 && bot.learns == 0 && bot.points == 2);
        assert(owner.attempts == 0 && owner.points == 71 && owner.ranks.empty());
    }
};
int main() {
    {
        Scenario state;
        assert(state.ai.IsAltBot());
        state.Inspect();
        assert(state.Has("ISYNC 0x0000000000000002 0 1 1 "));
        assert(state.Has("IEDIT 0x0000000000000002 1 2"));
        assert(state.bot.attempts == 0);
        state.Learn();
        assert(state.bot.attempts == 1 && state.bot.learns == 1 && state.bot.points == 1);
        assert(state.bot.ranks.at(kVanillaTalentId) == 1);
        assert(state.Has("ISYNC 0x0000000000000002 0 1 1 " + std::to_string(kVanillaTalentId) + ":1"));
        assert(state.Has("IEDIT 0x0000000000000002 1 1"));
        assert(state.owner.attempts == 0 && state.owner.points == 71 && state.owner.ranks.empty());
        state.ai.master = &state.stranger;
        state.Learn();
        assert(state.bot.attempts == 1 && state.bot.learns == 1 && state.bot.points == 1);
        assert(state.Has("IEDIT 0x0000000000000002 0 0"));
    }
    { Scenario s; s.ai.master = &s.stranger; s.Denied(); }
    { Scenario s; s.owner.group = nullptr; s.bot.group = nullptr; s.Denied(); }
    { Scenario s; s.bot.group = &s.otherGroup; s.Denied(); }
    { Scenario s; s.bot.ai = nullptr; s.Denied(); }
    { Scenario s; s.bot.random = true; assert(!s.ai.IsAltBot()); s.Denied(); }
    { Scenario s; s.ai.master = &s.bot; assert(IsSelfBot(&s.bot) && !s.ai.IsAltBot()); s.Denied(); }
    { Scenario s; s.ai.master = nullptr; assert(!s.ai.IsAltBot()); s.Denied(); }
    {
        Scenario s;
        s.stranger.ai = &s.strangerAI; s.strangerAI.master = &s.owner; s.strangerAI.bot = &s.stranger;
        s.ai.master = &s.stranger;
        assert(!s.ai.IsAltBot()); s.Denied();
    }
    { Scenario s; s.bot.inRange = false; s.Denied(); }
    { Scenario s; s.bot.enemy = true; s.Denied(); }
    { Scenario s; world.inspect = false; s.Denied(); }
    { Scenario s; s.bot.cls = 6; s.Denied(); }
    { Scenario s; s.bot.era = s.bot.stored = ERA_WOTLK; s.Denied(); }
    { Scenario s; config.bots = false; s.Denied(); }
    { Scenario s; config.enabled = false; s.Denied(); }
    {
        // Every SYNC is followed by the glyph gate's own answer for the requester and the
        // realm's Dungeon Finder switch and dual-specialization level.
        Scenario s;
        auto const glyphs = [&] { return s.owner.messages.at(s.owner.messages.size() - 2); };
        s.Send("HELLO"); assert(glyphs() == "GLYPHS 1" && s.owner.messages.back() == "UNLOCKS 0 80");
        s.owner.era = s.owner.stored = ERA_TBC; s.Send("HELLO"); assert(glyphs() == "GLYPHS 0");
        s.owner.era = ERA_WOTLK; s.Send("HELLO"); assert(glyphs() == "GLYPHS 0");
        s.owner.cls = 6; s.Send("HELLO"); assert(glyphs() == "GLYPHS 1");
        s.owner.cls = 1; config.glyphGate = false; s.Send("HELLO"); assert(glyphs() == "GLYPHS 1");
        config.glyphGate = true; s.Send("LEARN 1"); assert(glyphs() == "GLYPHS 0");
        lfgMgr.options = 4; world.dualSpecLevel = 40; s.Send("HELLO"); assert(s.owner.messages.back() == "UNLOCKS 0 40");
        lfgMgr.options = 5; s.Send("HELLO"); assert(s.owner.messages.back() == "UNLOCKS 1 40");
        lfgMgr.options = 0; world.dualSpecLevel = 80;
    }
    {
        // BOOK answers with the subject's trainer book and sends no SYNC; riding only for the requester.
        Scenario s;
        s.Send("BOOK 0x1");
        assert(s.owner.messages == std::vector<std::string>({"BOOK 0x1 1 1:6673:10:0:0:0:1", "RIDING 0x1 40:33388:40000:0:0:0:0"}));
        s.Send("BOOK 0x2");
        assert(s.owner.messages == std::vector<std::string>({"BOOK 0x2 1 1:6673:10:0:0:0:1"}));
        s.Send("BOOK 0x3");
        assert(s.owner.messages == std::vector<std::string>({"BOOK 0x3 0"}));
        s.bot.group = &s.otherGroup; s.Send("BOOK 0x2");
        assert(s.owner.messages == std::vector<std::string>({"BOOK 0x2 0"}));
        config.enabled = false; s.Send("BOOK 0x1"); assert(s.owner.messages.empty());
    }
    {
        Scenario s;
        s.bot.era = s.bot.stored = ERA_TBC;
        s.bot.points = 61;
        s.Inspect(); assert(s.Has("IEDIT 0x0000000000000002 1 61"));
        s.Learn();
        assert(s.bot.learns == 1 && s.Has("ISYNC 0x0000000000000002 1 1 1 " + std::to_string(kTbcTalentId) + ":1"));
        assert(s.Has("IEDIT 0x0000000000000002 1 60"));
    }
    {
        Scenario s; s.bot.points = 51;
        s.Inspect(); assert(s.Has("IEDIT 0x0000000000000002 1 51"));
        s.Learn(); assert(s.bot.learns == 1 && s.Has("IEDIT 0x0000000000000002 1 50"));
    }
    {
        Scenario s; s.bot.era = ERA_TBC;
        s.Learn(); assert(s.bot.attempts == 1 && s.bot.learns == 0 && s.bot.points == 2);
    }
    {
        Scenario s;
        s.owner.ai = &s.ownerAI; s.ownerAI.bot = &s.owner; s.ownerAI.master = &s.owner;
        assert(IsSelfBot(&s.owner) && s.ai.IsAltBot());
        s.Learn(); assert(s.bot.learns == 1 && s.owner.learns == 0);
    }
    {
        Scenario s;
        s.bot.rejectLearn = true;
        s.Learn(); assert(s.bot.attempts == 1 && s.bot.learns == 0 && s.bot.points == 2);
        assert(s.Has("IEDIT 0x0000000000000002 1 2"));
        s.bot.rejectLearn = false; s.bot.points = 0;
        s.Learn(); assert(s.bot.attempts == 2 && s.bot.learns == 0 && s.bot.points == 0);
        assert(s.Has("IEDIT 0x0000000000000002 1 0"));
    }
    {
        Scenario s;
        std::string const validId = std::to_string(kVanillaTalentId);
        for (std::string const token : {"0x", "garbage", "0x2!", "0x000000000000000200", "0x00000000000000ff"}) {
            s.Send("ILEARN " + token + " " + validId);
            assert(s.bot.attempts == 0 && s.owner.attempts == 0);
        }
        s.Send("ILEARN 0x0000000000000002"); assert(s.bot.learns == 0);
        for (std::string const& value : std::vector<std::string>{
                validId + " trailing", validId + "junk", "junk", "4294967296", "+" + validId,
                "-" + std::to_string((uint64(1) << 32) - kVanillaTalentId)}) {
            s.Send("ILEARN 0x0000000000000002 " + value);
            assert(s.bot.attempts == 0 && s.owner.attempts == 0);
        }
        s.Send("ILEARN 0x0000000000000002 " + validId, 0); assert(s.bot.learns == 0 && s.owner.messages.empty());
        s.Send("ILEARN 0x0000000000000002 " + validId, LANG_ADDON, "OTHER");
        assert(s.bot.learns == 0 && s.owner.messages.empty());
    }
    std::cout << "Targeted talent hook: owner/group/altbot/inspect gates, revalidation, own era and fresh points passed\n";
}
'''


def production(module: Path, core: Path) -> tuple[str, str]:
    ai = (core / 'modules/mod-playerbots/src/Bot/PlayerbotAI.cpp').read_text()
    bot = (module / 'src/EraTalentBots.cpp').read_text()
    # Execute native classification rather than replacing IsAltBot with a test boolean.
    classification = '\n'.join(function(ai, signature) for signature in (
        'bool IsRealPlayer(', 'bool IsSelfBot(', 'bool PlayerbotAI::HasGameClientMaster()',
        'bool PlayerbotAI::IsAltBot()'))
    gates = '\n'.join(function(bot, signature) for signature in (
        'bool IsBot(', '    EraId EraFor(', '    bool IsEraManaged('))
    ids = []
    for era in ('Vanilla', 'TBC'):
        tree = (module / f'client-addon/EraTalents/data/generated/Warrior{era}.lua').read_text()
        node = re.search(r'\{ id=(\d+), tab=1, tier=0,[^\n]*?maxRank=([3-5]), prereqTalent=0, prereqPoints=0, wired=true', tree)
        assert node is not None, f'{era} needs a real first-row warrior talent for the dispatch adapter'
        ids.append(int(node[1]))
    authored = f'constexpr uint32 kVanillaTalentId = {ids[0]}, kTbcTalentId = {ids[1]};'
    entry = re.search(r'struct Entry\n\{.*?\n\};', (module / 'src/EraTrainerBook.h').read_text(), re.DOTALL).group(0)
    glyph_gate = function((module / 'src/EraGlyphGate.cpp').read_text(), 'bool Allowed(Player* player)')
    adapters = ADAPTERS.replace('// AUTHORED_IDS', authored).replace('// CLASSIFICATION', classification).replace(
        '// ERA_GATES', gates).replace('// BOOK_ENTRY', entry).replace('// GLYPH_GATE', glyph_gate)
    lfg = (core / 'src/server/game/DungeonFinding/LFGMgr.h').read_text()
    assert re.search(r'LFG_OPTION_ENABLE_DUNGEON_FINDER\s*=\s*0x01,', lfg)
    lfg_source = (core / 'src/server/game/DungeonFinding/LFGMgr.cpp').read_text()
    assert 'return m_options & option;' in function(lfg_source, 'bool LFGMgr::isOptionEnabled(uint32 option)')
    source = (module / 'src/EraTalentsComms.cpp').read_text()
    # Keep the complete hook and its helpers; only external include dependencies use adapters.
    source = re.sub(r'^\s*#include[^\n]*\n', '', source, flags=re.MULTILINE)
    return adapters, source


def check(adapters: str, production_source: str, directory: Path, name: str, *, mutant: bool = False) -> None:
    source, executable = directory / f'{name}.cpp', directory / name
    source.write_text(adapters + '\n' + production_source + '\n' + TESTS)
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', '-DMOD_PLAYERBOTS',
                    *SANITIZER_FLAGS, '-no-pie', str(source), '-o', str(executable)], check=True)
    result = run_fixture([str(executable)])
    if mutant:
        if result.returncode == 0:
            raise AssertionError(f'Talent learning mutation survived: {name}')
        if 'Assertion' not in result.stderr:
            raise AssertionError(f'Mutation failed outside a behavioral assertion: {name}\n{result.stderr}')
        print(f'Talent learning mutation rejected: {name}')
    elif result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    else:
        print(result.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module-source', type=Path, default=prepared_core(ROOT) / 'modules/mod-era-talents')
    args = parser.parse_args()
    adapters, source = production(args.module_source, prepared_core(ROOT))
    with tempfile.TemporaryDirectory(prefix='multibot-talent-learning-') as temporary:
        directory = Path(temporary)
        check(adapters, source, directory, 'production')
        mutations = (
            ('foreign-master', 'ai->GetMaster() == requester', 'true'),
            ('group-required', 'requester->GetGroup() &&', ''),
            ('same-group', 'target->GetGroup() == requester->GetGroup()', 'true'),
            ('altbots-only', 'ai->IsAltBot()', 'true'),
            ('native-inspect-distance', '!requester->IsWithinDistInMap(t, INSPECT_DISTANCE, false)', 'false'),
            ('native-inspect-faction', 'requester->IsValidAttackTarget(t)', 'false'),
            ('native-inspect-setting', '!sWorld->getBoolConfig(CONFIG_TALENTS_INSPECTING) && !requester->CanBeGameMaster()', 'false'),
            ('historical-target', '!EraTalentBots::IsEraManaged(t)', 'false'),
            ('unsigned-id-only', 'std::isdigit(iss.peek()) &&', ''),
            ('exact-learn-payload', '&& !(iss >> extra)', ''),
            ('book-dispatch', 'else if (verb == "BOOK")', 'else if (false)'),
            ('glyph-state', 'EraGlyphGate::Allowed(p) ? "1" : "0"', '"1"'),
            ('finder-state', 'sLFGMgr->isOptionEnabled(lfg::LFG_OPTION_ENABLE_DUNGEON_FINDER) ? "1 " : "0 "', '"1 "'),
            ('dual-spec-level', 'std::to_string(sWorld->getIntConfig(CONFIG_MIN_DUALSPEC_LEVEL))', '"40"'),
        )
        for name, before, after in mutations:
            if before not in source:
                raise AssertionError(f'Missing production mutation target: {name}')
            check(adapters, source.replace(before, after), directory, name, mutant=True)


if __name__ == '__main__':
    main()
