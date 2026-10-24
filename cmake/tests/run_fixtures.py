"""Run the gameplay rule fixtures and check that every fixture runs in CI.

  python3 cmake/tests/run_fixtures.py check     fail when a fixture is not wired into CI
  python3 cmake/tests/run_fixtures.py gameplay  run the gameplay fixtures in order
  python3 cmake/tests/run_fixtures.py gameplay --shard-index 0 --shard-count 4

A fixture is wired when it is listed below or when the checks workflow names
its path.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
import time


TESTS = Path(__file__).resolve().parent
WORKFLOW = TESTS.parents[1] / ".github/workflows/checks.yml"
# Packages are published only from release workflow runs, which must include the checks.
RELEASE_WORKFLOW = TESTS.parents[1] / ".github/workflows/release.yml"
CHECKS_CALL = "uses: ./.github/workflows/checks.yml"
GAMEPLAY_COMMAND = "cmake/tests/run_fixtures.py gameplay"
# Native no-cheat and gameplay fixtures, checked against the prepared sources,
# and the documentation check.
GAMEPLAY = (
    "TestFixtureSupport",
    "TestEarnedProgression", "TestEraExperience", "TestEarnedBotBrackets", "TestEarnedAuctions", "TestStrictEarnedProgression",
    "TestEarnedEraPrices", "TestEraTalents", "TestPlayerbotEraBattlegrounds", "TestEarnedEraBattlegrounds",
    "TestEarnedArenaCore", "TestBattlegroundEraRules", "TestEarnedEraPvpRules", "TestWindowsResourceIncludes",
    "TestCoreBuildWarnings", "TestCoreExperience", "TestClientCacheVersion",
    "TestWorldStartupData", "TestSubmergeBinding", "TestClientAddonLoading",
    "TestMasterFlightLearning", "TestBotQuestAreaTriggers",
    "TestLootRollPolicy", "TestWorldBuffEvents", "TestEraEvents", "TestLfgProgression",
    "TestEarnedDungeonParties", "TestEarnedDungeonEvents", "TestDefiasCannon", "TestUldamanAltars", "TestRingOfLaw", "TestRocknotAle", "TestWailingCaverns", "TestZumrah", "TestDungeonLabGates", "TestRaidClearEarnedPlay",
    "TestRaidClearWindowsBuild", "TestEarnedRaidComposition", "TestEarnedRaidGroups",
    "TestOnyxiaIntegration",
    "TestHistoricalClassQuests", "TestMultiBotTrainerMoney", "TestMultiBotNaturalProgression", "TestQuestProgressBridge", "TestIpProgressBridge", "TestZygorProgression",
    "TestMultiBotOptionalPresets", "TestMultiBotEraTalents", "TestMultiBotTalentLearning", "TestMultiBotRoleStrategies", "TestMultiBotVendorPurchases", "TestFormationMovement",
    "TestFrostmaneHold", "TestCreatureEraModifiers", "TestNaturalTaxiRoutes", "TestNaturalMovement",
    "TestWarlockSoulShards", "TestNaturalMaintenance",
    "TestEraGeneratedArtifacts", "TestEraCorePatches", "TestProgressionMapGates",
    "TestPlayerbotUpstreamFixes", "TestPlayerbotSscEarnedPlay", "TestPlayerbotRaidRecovery", "TestProfileKeys", "TestDocumentation", "TestEraTreeBlanketing",
)


def fixtures() -> set[str]:
    return {path.name for path in TESTS.glob("Test*") if path.suffix in (".py", ".ps1") and path.is_file()}


def gameplay_wiring_errors(workflow: str) -> list[str]:
    job = re.search(r"(?ms)^  gameplay:\n(.*?)(?=^  [A-Za-z_][\w-]*:|\Z)", workflow)
    if not job:
        if re.search(re.escape(GAMEPLAY_COMMAND) + r"[^\n]*--shard-", workflow):
            return ["Gameplay shards must be defined in the gameplay job"]
        return []
    command = re.search(re.escape(GAMEPLAY_COMMAND) +
                        r"\s+--shard-index\s+\$\{\{\s*matrix[.]shard\s*\}\}\s+--shard-count\s+(\d+)\b",
                        job[1])
    matrix = re.search(r"(?m)^\s+shard:\s*\[([\d, \t]+)\]\s*$", job[1])
    if not command or not matrix:
        return ["The gameplay job must declare its shard matrix and matching runner command"]
    count = int(command[1])
    indices = [int(value) for value in matrix[1].split(",") if value.strip()]
    if not 1 <= count <= len(GAMEPLAY) or sorted(indices) != list(range(count)):
        return ["The gameplay shard matrix must contain every index exactly once for --shard-count"]
    return []


def wiring_errors() -> list[str]:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    available = fixtures()
    errors = [f"{name}.py is listed as a gameplay fixture but does not exist"
              for name in GAMEPLAY if f"{name}.py" not in available]
    wired = {name for name in available if f"cmake/tests/{name}" in workflow}
    if GAMEPLAY_COMMAND in workflow:
        wired |= {f"{name}.py" for name in GAMEPLAY} & available
    else:
        errors.append(f"The checks workflow does not run {GAMEPLAY_COMMAND}")
    errors += gameplay_wiring_errors(workflow)
    if CHECKS_CALL not in RELEASE_WORKFLOW.read_text(encoding="utf-8"):
        errors.append("The release workflow does not run the checks workflow before it builds")
    errors += [f"{name} does not run in CI: list it in cmake/tests/run_fixtures.py or call it from "
               ".github/workflows/checks.yml" for name in sorted(available - wired)]
    return errors


def check() -> int:
    errors = wiring_errors()
    for error in errors:
        print(f"::error file=cmake/tests/run_fixtures.py::{error}", flush=True)
    if not errors:
        print(f"All {len(fixtures())} cmake/tests fixtures run in CI.")
    return 1 if errors else 0


def gameplay_fixtures(shard_index: int = 0, shard_count: int = 1) -> tuple[str, ...]:
    if not 1 <= shard_count <= len(GAMEPLAY):
        raise ValueError(f"shard count must be between 1 and {len(GAMEPLAY)}")
    if not 0 <= shard_index < shard_count:
        raise ValueError("shard index must be between 0 and shard count minus one")
    return GAMEPLAY[shard_index::shard_count]


def gameplay(shard_index: int = 0, shard_count: int = 1) -> int:
    selected = gameplay_fixtures(shard_index, shard_count)
    started = time.monotonic()
    label = f"Gameplay shard {shard_index + 1}/{shard_count}"
    print(f"{label}: {len(selected)}/{len(GAMEPLAY)} fixtures", flush=True)
    for name in selected:
        path = Path("cmake/tests") / f"{name}.py"
        print(f"::group::{name}", flush=True)
        fixture_started = time.monotonic()
        result = subprocess.run([sys.executable, str(TESTS / f"{name}.py")], check=False)
        print(f"{name}: {time.monotonic() - fixture_started:.1f}s", flush=True)
        print("::endgroup::", flush=True)
        if result.returncode:
            print(f"::error file={path}::{name} failed (exit {result.returncode})", flush=True)
            print(f"{label} failed after {time.monotonic() - started:.1f}s", flush=True)
            return result.returncode
    print(f"{label}: all {len(selected)} fixtures passed in {time.monotonic() - started:.1f}s", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("check", "gameplay"))
    parser.add_argument("--shard-index", type=int, default=0, help="zero-based gameplay shard index (default: 0)")
    parser.add_argument("--shard-count", type=int, default=1, help="number of gameplay shards (default: 1)")
    args = parser.parse_args(argv)
    if args.command == "check":
        if args.shard_index != 0 or args.shard_count != 1:
            parser.error("shard options apply only to gameplay")
        return check()
    try:
        return gameplay(args.shard_index, args.shard_count)
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
