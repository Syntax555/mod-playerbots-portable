"""Run the gameplay rule fixtures and check that every fixture runs in CI.

  python3 cmake/tests/run_fixtures.py check     fail when a fixture is not wired into CI
  python3 cmake/tests/run_fixtures.py gameplay  run the gameplay fixtures in order

A fixture is wired when it is listed below or when the release workflow names
its path.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


TESTS = Path(__file__).resolve().parent
WORKFLOW = TESTS.parents[1] / ".github/workflows/release.yml"
GAMEPLAY_COMMAND = "cmake/tests/run_fixtures.py gameplay"
# Native no-cheat and gameplay fixtures, checked against the prepared sources,
# and the documentation check.
GAMEPLAY = (
    "TestFixtureSupport",
    "TestEarnedProgression", "TestEraExperience", "TestEarnedBotBrackets", "TestEarnedAuctions", "TestStrictEarnedProgression",
    "TestEarnedEraPrices", "TestEraTalents", "TestPlayerbotEraBattlegrounds", "TestEarnedEraBattlegrounds",
    "TestEarnedArenaCore", "TestBattlegroundEraRules", "TestEarnedEraPvpRules", "TestWindowsResourceIncludes",
    "TestCoreBuildWarnings",
    "TestMasterFlightLearning", "TestBotQuestAreaTriggers",
    "TestLootRollPolicy", "TestWorldBuffEvents", "TestEraEvents", "TestLfgProgression",
    "TestEarnedDungeonParties", "TestEarnedDungeonEvents", "TestDungeonLabGates", "TestRaidClearEarnedPlay",
    "TestHistoricalClassQuests", "TestMultiBotTrainerMoney", "TestMultiBotNaturalProgression",
    "TestMultiBotOptionalPresets", "TestMultiBotEraTalents", "TestMultiBotRoleStrategies", "TestFormationMovement",
    "TestFrostmaneHold", "TestCreatureEraModifiers", "TestNaturalTaxiRoutes", "TestNaturalMovement",
    "TestWarlockSoulShards", "TestNaturalMaintenance",
    "TestEraGeneratedArtifacts", "TestEraCorePatches", "TestProgressionMapGates",
    "TestPlayerbotUpstreamFixes", "TestPlayerbotSscEarnedPlay", "TestProfileKeys", "TestDocumentation", "TestEraTreeBlanketing",
)


def fixtures() -> set[str]:
    return {path.name for path in TESTS.glob("Test*") if path.suffix in (".py", ".ps1") and path.is_file()}


def wiring_errors() -> list[str]:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    available = fixtures()
    errors = [f"{name}.py is listed as a gameplay fixture but does not exist"
              for name in GAMEPLAY if f"{name}.py" not in available]
    wired = {name for name in available if f"cmake/tests/{name}" in workflow}
    if GAMEPLAY_COMMAND in workflow:
        wired |= {f"{name}.py" for name in GAMEPLAY} & available
    else:
        errors.append(f"The release workflow does not run {GAMEPLAY_COMMAND}")
    errors += [f"{name} does not run in CI: list it in cmake/tests/run_fixtures.py or call it from "
               ".github/workflows/release.yml" for name in sorted(available - wired)]
    return errors


def check() -> int:
    errors = wiring_errors()
    for error in errors:
        print(f"::error file=cmake/tests/run_fixtures.py::{error}", flush=True)
    if not errors:
        print(f"All {len(fixtures())} cmake/tests fixtures run in CI.")
    return 1 if errors else 0


def gameplay() -> int:
    for name in GAMEPLAY:
        path = Path("cmake/tests") / f"{name}.py"
        print(f"::group::{name}", flush=True)
        result = subprocess.run([sys.executable, str(TESTS / f"{name}.py")], check=False)
        print("::endgroup::", flush=True)
        if result.returncode:
            print(f"::error file={path}::{name} failed (exit {result.returncode})", flush=True)
            return result.returncode
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("check", "gameplay"))
    args = parser.parse_args()
    return check() if args.command == "check" else gameplay()


if __name__ == "__main__":
    raise SystemExit(main())
