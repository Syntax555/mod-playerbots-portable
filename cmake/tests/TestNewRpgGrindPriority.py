"""Compile New RPG's production grind gate and reject behaviour mutations."""

import argparse
from pathlib import Path
import subprocess
import tempfile

from FixtureSupport import SANITIZER_FLAGS, cxx, function, in_parallel, prepared_core, run_fixture, source_argument


parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, help="Playerbots src directory")
args = parser.parse_args()
module = args.source or prepared_core() / "modules/mod-playerbots/src"
strategy = (module / "Ai/World/Rpg/Strategy/NewRpgStrategy.cpp").read_text()
header = (module / "Ai/World/Rpg/Strategy/NewRpgStrategy.h").read_text()
assert "class NewRpgGrindMultiplier : public Multiplier" in header
assert "multipliers.push_back(new NewRpgGrindMultiplier(botAI));" in strategy
production = function(strategy, "float NewRpgGrindMultiplier::GetValue(Action* action)")

prelude = r"""
#include <cassert>
#include <cmath>
#include <iostream>
#include <string>
#include <variant>

struct WorldPosition
{
    float x = 0.0f;
    bool operator==(WorldPosition const&) const = default;
};

enum NewRpgStatus
{
    RPG_IDLE,
    RPG_WANDER_RANDOM,
    RPG_DO_QUEST,
    RPG_GO_GRIND,
    RPG_GO_CAMP,
    RPG_WANDER_NPC,
    RPG_REST,
    RPG_TRAVEL_FLIGHT,
    RPG_OUTDOOR_PVP,
    RPG_DO_GATHER,
    RPG_TRAVEL_ROUTE
};

struct NewRpgInfo
{
    struct Idle {};
    struct DoQuest { WorldPosition pos{}; };
    std::variant<Idle, DoQuest> data{Idle{}};
    NewRpgStatus status = RPG_IDLE;
    NewRpgStatus GetStatus() const { return status; }
};
struct Action
{
    std::string name;
    std::string getName() const { return name; }
};
struct Player
{
    float x = 0.0f;
    float GetDistance(WorldPosition const& pos) const { return std::abs(x - pos.x); }
};
struct PlayerbotAI { Player* bot; NewRpgInfo rpgInfo; };
struct Multiplier
{
    PlayerbotAI* botAI;
    Player* bot;
    Multiplier(PlayerbotAI* ai, std::string const&) : botAI(ai), bot(ai->bot) {}
};
struct NewRpgGrindMultiplier : Multiplier
{
    explicit NewRpgGrindMultiplier(PlayerbotAI* ai) : Multiplier(ai, "new rpg grind") {}
    float GetValue(Action* action);
};

@@PRODUCTION@@

int main()
{
    Player bot;
    PlayerbotAI ai{&bot};
    NewRpgGrindMultiplier gate(&ai);
    Action ambient{"attack anything"};
    Action planned{"new rpg do quest"};

    assert(gate.GetValue(nullptr) == 1.0f);
    assert(gate.GetValue(&ambient) == 1.0f); // No RPG goal: legacy fallback remains
    ai.rpgInfo.status = RPG_WANDER_RANDOM;
    assert(gate.GetValue(&ambient) == 1.0f); // Quest mob / ambient grinding remains

    for (NewRpgStatus status : {RPG_GO_GRIND, RPG_GO_CAMP, RPG_WANDER_NPC,
                                RPG_REST, RPG_TRAVEL_FLIGHT, RPG_OUTDOOR_PVP,
                                RPG_DO_GATHER, RPG_TRAVEL_ROUTE})
    {
        ai.rpgInfo.status = status;
        assert(gate.GetValue(&ambient) == 0.0f);
        assert(gate.GetValue(&planned) == 1.0f); // Never suppress RPG actions
    }

    ai.rpgInfo.status = RPG_DO_QUEST;
    assert(gate.GetValue(&ambient) == 0.0f); // No objective selected yet
    ai.rpgInfo.data = NewRpgInfo::DoQuest{};
    assert(gate.GetValue(&ambient) == 0.0f); // Empty POI is not a grind location
    ai.rpgInfo.data = NewRpgInfo::DoQuest{WorldPosition{50.0f}};
    assert(gate.GetValue(&ambient) == 0.0f); // Travel to POI without random pulls
    bot.x = 39.0f;
    assert(gate.GetValue(&ambient) == 0.0f);
    bot.x = 40.0f;
    assert(gate.GetValue(&ambient) == 1.0f); // Exact boundary
    bot.x = 50.0f;
    assert(gate.GetValue(&ambient) == 1.0f); // Quest kills available at POI
    std::cout << "New RPG grind coordination passed\n";
}
"""

mutations = (
    ("ambient-only gate", 'action->getName() != "attack anything"', 'action->getName() == "attack anything"'),
    ("wandering allowed", "status == RPG_WANDER_RANDOM", "status == RPG_GO_GRIND"),
    ("quest check", "status == RPG_DO_QUEST", "status == RPG_GO_CAMP"),
    ("POI required", "quest->pos != WorldPosition() &&", "true &&"),
    ("POI distance", "<= 10.0f", "> 10.0f"),
    ("travel blocks random pulls", "return 0.0f;\n}", "return 1.0f;\n}"),
)


def build(directory, body, name):
    cpp = directory / (name + ".cpp")
    cpp.write_text(prelude.replace("@@PRODUCTION@@", body))
    binary = directory / name
    subprocess.run(
        [cxx(), "-std=c++20", "-Wall", "-Wextra", "-Werror",
         *SANITIZER_FLAGS, str(cpp), "-o", str(binary)],
        check=True,
    )
    return run_fixture([str(binary)])


with tempfile.TemporaryDirectory(prefix="portable-new-rpg-grind-") as temporary:
    directory = Path(temporary)
    result = build(directory, production, "new-rpg-grind")
    print(result.stdout + result.stderr, end="")
    if result.returncode:
        raise SystemExit("New RPG grind coordination failed")

    def check_mutant(numbered):
        index, (label, old, new) = numbered
        assert old in production, label
        mutant = production.replace(old, new, 1)
        return build(directory, mutant, f"mutant-{index}").returncode != 0

    for (label, *_), rejected in zip(mutations, in_parallel(check_mutant, enumerate(mutations))):
        if not rejected:
            raise SystemExit("New RPG grind mutation survived: " + label)
        print("New RPG grind mutation rejected: " + label)
