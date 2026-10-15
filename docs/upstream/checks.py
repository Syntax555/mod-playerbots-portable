"""Apply the upstream proposals to pristine snapshots and reject their baselines.

Requires Git, a C++20 g++ compiler, and checkouts containing the base commits
recorded in README.md. No checkout or running server is changed.
"""

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile


repository = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repository / "cmake/tests"))
from FixtureSupport import function


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--core", type=Path, required=True)
parser.add_argument("--progression", type=Path, required=True)
args = parser.parse_args()
CORE_BASE = "a64665927de9d23cf81b0b623ee7117131f0919a"
IP_BASE = "c87e666fc034978cffbb287f1be5e53df522539d"
snapshots = tempfile.TemporaryDirectory(prefix="upstream-proposals-")
work = Path(snapshots.name)


def snapshot(checkout, revision, target, paths):
    for path in paths:
        content = subprocess.run(
            ["git", "-C", str(checkout), "show", f"{revision}:{path}"],
            check=True,
            capture_output=True,
        ).stdout
        destination = target / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)


core = work / "core"
fixed_core = work / "fixed-core"
ip_baseline = work / "ip"
ip = work / "fixed-ip"
core_paths = (
    "src/server/game/Entities/Player/Player.cpp",
    "src/server/game/Battlegrounds/BattlegroundMgr.cpp",
    "src/server/game/Movement/MovementGenerators/FormationMovementGenerator.cpp",
    "src/server/game/Movement/Spline/MoveSpline.cpp",
)
ip_paths = ("src/IndividualProgression.cpp", "src/IndividualProgressionPlayer.cpp")
for target in (core, fixed_core):
    snapshot(args.core.resolve(), CORE_BASE, target, core_paths)
for target in (ip_baseline, ip):
    snapshot(args.progression.resolve(), IP_BASE, target, ip_paths)
for name, target in (
    ("formation-velocity", fixed_core),
    ("talent-reset-cost", fixed_core),
    ("random-battleground", fixed_core),
    ("individual-progression-filters", ip),
):
    subprocess.run(
        ["git", "apply", str(Path(__file__).with_name(name + ".patch"))],
        cwd=target,
        check=True,
    )


def check(label, prelude, tests, base, fixed):
    with tempfile.TemporaryDirectory(prefix="upstream-check-") as work:
        work = Path(work)
        for name, code in [("baseline", base), ("proposed", fixed)]:
            source = work / (name + ".cpp")
            source.write_text(prelude + "\n" + code + "\n" + tests)
            binary = work / name
            subprocess.run(
                [
                    "g++",
                    "-std=c++20",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-fsanitize=address,undefined",
                    "-g",
                    str(source),
                    "-o",
                    str(binary),
                ],
                check=True,
            )
            result = subprocess.run(
                [str(binary)], check=False, capture_output=True, text=True, timeout=60
            )
            assert (result.returncode == 0) == (name == "proposed"), (
                label,
                name,
                result.returncode,
                result.stdout,
                result.stderr,
            )
        print(
            label
            + ": proposed production methods pass; unpatched production methods rejected",
            flush=True,
        )


rel = Path("src/server/game/Entities/Player/Player.cpp")
sig = "uint32 Player::resetTalentsCost() const"
prelude = """#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstdint>
using uint32=uint32_t; using uint64=uint64_t; using int32=int32_t;
constexpr int32 GOLD=10000; constexpr int64_t MONTH=30LL*24*60*60;
namespace GameTime { int64_t now=1800000000; std::chrono::seconds GetGameTime(){ return std::chrono::seconds(now); } }
struct Player { uint32 m_resetTalentsCost=0; int64_t m_resetTalentsTime=GameTime::now; uint32 resetTalentsCost() const; };
"""
tests = """int main(){
Player player;
for(uint32 gold: {1u,5u,10u,15u,20u,25u,30u,35u,40u,45u,50u,50u}){
assert(player.resetTalentsCost()==gold*GOLD); player.m_resetTalentsCost=gold*GOLD;}
player.m_resetTalentsCost=30*GOLD; player.m_resetTalentsTime=GameTime::now-MONTH;
assert(player.resetTalentsCost()==25*GOLD);
player.m_resetTalentsTime=GameTime::now-1000LL*MONTH;
assert(player.resetTalentsCost()==10*GOLD);
player.m_resetTalentsTime=GameTime::now-50000LL*MONTH;
assert(player.resetTalentsCost()==10*GOLD);
player.m_resetTalentsCost=40*GOLD; player.m_resetTalentsTime=GameTime::now+10LL*MONTH;
assert(player.resetTalentsCost()==45*GOLD);
}
"""
check(
    "resetTalentsCost",
    prelude,
    tests,
    function((core / rel).read_text(), sig),
    function((fixed_core / rel).read_text(), sig),
)

rel = Path("src/server/game/Battlegrounds/BattlegroundMgr.cpp")
sig = "BattlegroundTypeId BattlegroundMgr::GetRandomBG("
prelude = """#include <cassert>
#include <cstdint>
#include <vector>
using uint32=uint32_t; using int32=int32_t;
enum BattlegroundTypeId { BATTLEGROUND_TYPE_NONE, BATTLEGROUND_RB, BATTLEGROUND_WS };
struct Battlemaster { std::vector<int32> mapid; };
struct BattlegroundTemplate { Battlemaster* BattlemasterEntry; uint32 MinLevel; BattlegroundTypeId Id; double Weight; };
namespace Acore::Containers {
int picks=0;
auto SelectRandomWeightedContainerElement(std::vector<BattlegroundTypeId> const& ids,std::vector<double> const& weights){
++picks; assert(!ids.empty() && ids.size()==weights.size()); return ids.begin(); }
}
struct BattlegroundMgr {
Battlemaster entry{{-1}}; BattlegroundTemplate source{&entry,0,BATTLEGROUND_RB,1}, map{nullptr,10,BATTLEGROUND_WS,1}; bool templateExists=true, mapExists=true;
BattlegroundTemplate const* GetBattlegroundTemplateByTypeId(BattlegroundTypeId){ return templateExists ? &source : nullptr; }
BattlegroundTemplate const* GetBattlegroundTemplateByMapId(int32){ return mapExists ? &map : nullptr; }
BattlegroundTypeId GetRandomBG(BattlegroundTypeId,uint32);
};
"""
tests = """int main(){
BattlegroundMgr mgr;
assert(mgr.GetRandomBG(BATTLEGROUND_RB,80)==BATTLEGROUND_TYPE_NONE); assert(Acore::Containers::picks==0);
mgr.entry.mapid={489,-1}; mgr.mapExists=false;
assert(mgr.GetRandomBG(BATTLEGROUND_RB,80)==BATTLEGROUND_TYPE_NONE); assert(Acore::Containers::picks==0);
mgr.mapExists=true;
assert(mgr.GetRandomBG(BATTLEGROUND_RB,1)==BATTLEGROUND_TYPE_NONE); assert(Acore::Containers::picks==0);
assert(mgr.GetRandomBG(BATTLEGROUND_RB,80)==BATTLEGROUND_WS); assert(Acore::Containers::picks==1);
mgr.templateExists=false; assert(mgr.GetRandomBG(BATTLEGROUND_RB,80)==BATTLEGROUND_TYPE_NONE);
}
"""
check(
    "empty random battleground",
    prelude,
    tests,
    function((core / rel).read_text(), sig),
    function((fixed_core / rel).read_text(), sig),
)

source = Path("src/IndividualProgression.cpp")
account = Path("src/IndividualProgressionPlayer.cpp")
sigs = [
    "bool IndividualProgression::isExcludedAccount(",
    "bool IndividualProgression::isBotAccount(",
]


def methods(text, acct):
    return (
        "\n".join(function(text, s) for s in sigs)
        + "\nstruct AccountHook {\n"
        + function(acct, "    bool CanAccountCreateCharacter(").replace(" override", "")
        + "\n};"
    )


base_source = (ip_baseline / source).read_text()
base_account = (ip_baseline / account).read_text()
prelude = """#include <cassert>
#include <cstdint>
#include <regex>
#include <string>
using uint32=uint32_t; using uint8=uint8_t;
constexpr uint8 RACE_DRAENEI=11,RACE_BLOODELF=10,CLASS_DEATH_KNIGHT=6;
int queries=0; bool found=true; std::string accountName="USER";
struct AccountMgr { static bool GetName(uint32,std::string& out){++queries;out=accountName;return found;} };
struct Session { uint32 GetAccountId(){return 1;} };
struct Player { Session session; Session* GetSession(){return &session;} };
struct IndividualProgression {
bool enabled=true; uint8 tbcRacesProgressionLevel=8,deathKnightProgressionLevel=13; std::string botAccountsRegex,excludedAccountsRegex; uint8 progression=0;
bool isBotAccount(Player*); bool isExcludedAccount(Player*); uint8 GetAccountProgression(uint32){return progression;}
} progression;
auto* sIndividualProgression=&progression;
"""
tests = """int main(){
Player player; AccountHook hook;
assert(!progression.isBotAccount(nullptr)&&!progression.isExcludedAccount(nullptr));
assert(!progression.isBotAccount(&player)&&!progression.isExcludedAccount(&player)); assert(queries==0);
assert(!hook.CanAccountCreateCharacter(1,RACE_DRAENEI,1)); assert(queries==0);
for (bool bot : {true,false}){
auto& pattern=bot ? progression.botAccountsRegex : progression.excludedAccountsRegex;
pattern="^RNDBOT.*"; accountName="RNDBOT1"; queries=0;
assert(bot ? progression.isBotAccount(&player) : progression.isExcludedAccount(&player)); assert(queries==1);
assert(hook.CanAccountCreateCharacter(1,RACE_DRAENEI,1)); assert(queries==2);
accountName="USER"; assert(!hook.CanAccountCreateCharacter(1,RACE_DRAENEI,1));
found=false; assert(!(bot ? progression.isBotAccount(&player) : progression.isExcludedAccount(&player)));
found=true; pattern.clear();
}
progression.progression=13; assert(hook.CanAccountCreateCharacter(1,RACE_DRAENEI,CLASS_DEATH_KNIGHT));
}
"""
check(
    "Individual Progression account filters",
    prelude,
    tests,
    methods(base_source, base_account),
    methods((ip / source).read_text(), (ip / account).read_text()),
)

subprocess.run(
    [
        sys.executable,
        str(repository / "cmake/tests/TestFormationMovement.py"),
        "--core",
        str(fixed_core),
        "--baseline",
        str(core),
    ],
    check=True,
)
snapshots.cleanup()
