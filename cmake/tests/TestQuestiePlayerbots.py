"""Run the pinned Questie Playerbots integration through native comms with Lua 5.1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from FixtureSupport import git_apply, unpatched


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/questie-playerbots-progress.patch"
FILES = ("Modules/Network/QuestiePlayerbots.lua", "Modules/Network/QuestieComms.lua",
         "Modules/Network/QuestieCommsData.lua", "Modules/Network/QuestiePartyObjectives.lua",
         "Modules/Quest/QuestieQuest.lua", "Modules/Quest/QuestieQuestPrivates.lua")
SOURCE = None
LUA = None


class QuestiePlayerbotsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="questie-playerbots-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        lock = json.loads((ROOT / "versions.lock.json").read_text())
        addon = next(item for item in lock["sourceAddons"] if item["name"] == "Questie-335")
        cache = ROOT / ".module-cache/client-addon-Questie-335"
        for relative in FILES:
            target = cls.directory / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if SOURCE:
                shutil.copyfile(SOURCE / relative, target)
            else:
                target.write_bytes(subprocess.run(
                    ["git", "-C", str(cache), "show", f"{addon['revision']}:{relative}"],
                    check=True, capture_output=True).stdout)
        unpatched(cls.directory, PATCH)
        git_apply(cls.directory, PATCH)
        cls.pristine = {relative: (cls.directory / relative).read_text() for relative in FILES}

    def run_fixture(self):
        fixture = (ROOT / "cmake/tests/QuestiePlayerbotsFixture.lua").read_text()
        return subprocess.run([LUA, "-"], input=f"local SOURCE = {json.dumps(str(self.directory))}\n{fixture}",
                              text=True, capture_output=True, check=False, timeout=20)

    def test_native_comms_and_lifecycle(self):
        result = self.run_fixture()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_regressions_are_detected(self):
        mutations = (
            (FILES[0], "token == current or", "true or", "request token ownership"),
            (FILES[0], 'token:sub(1, 3) ~= "qpb"', "true", "stale issued token"),
            (FILES[0], "request.watch and token and", "token and", "push token requires WATCH"),
            (FILES[0], "and objective.type == objectiveType", "", "per-type objective indices"),
            (FILES[0], "or -position", "or -rawObjective.index", "per-type unknown counters"),
            (FILES[0], "indices[position] = FindSameTypeObjectiveIndex(",
             "indices[position] = nil and FindSameTypeObjectiveIndex(", "database objective pairing"),
            (FILES[0], "databaseObjective and databaseObjective.Id or", "", "database objective identity"),
            (FILES[0], "if match then return nil end", "", "ambiguous database objectives"),
            (FILES[0], "unmatched[rawObjective.type] == 1", "true", "ambiguous server objectives"),
            (FILES[0], 'fields[4] == "NO_BOT"', "false", "NO_BOT backoff"),
            (FILES[0], "request.watch = nil", "", "NO_BOT without UNWATCH"),
            (FILES[0], "players[botName] == state.objectives", "players[botName] ~= nil", "native human ownership"),
            (FILES[0], "snapshot.expiresAt", "(GetTime() + 100000)", "snapshot expiry"),
            (FILES[0], "request.refreshAt", "(request.refreshAt + 999999)", "WATCH renewal"),
            (FILES[0], "objective.RootId == rawObjective.id", "false", "kill-credit root mapping"),
            (FILES[0], "fin = rawObjective.finished", "fin = false", "completion state"),
            (FILES[0], "snapshot.questCount < MAX_QUESTS", "true", "quest snapshot bound"),
            (FILES[0], "IsUnsigned(objectiveIndex, MAX_OBJECTIVES)", "IsUnsigned(objectiveIndex)", "objective index bound"),
            (FILES[2],
             'objectiveData.Type == "killcredit"', "false", "kill-credit source tooltip"),
            (FILES[2], ' and (objective.type == "m" or objective.type == "k")', "", "native alias type validation"),
            (FILES[2], "matchesKillCredit = objectiveData.RootId == objective.id", "matchesKillCredit = true",
             "native alias target validation"),
            (FILES[0], "or -position", "or (64 + position)", "special pin counter isolation"),
            (FILES[0], "if players and players[botName] and (not previous or players[botName] ~= previous.objectives) then",
             "if false then", "in-flight native takeover"),
            (FILES[3], "objData.Id or objData.RootId", "objData.Id", "kill-credit party map"),
            (FILES[3], 'objId or objType == "event"', "objId", "event party map"),
            (FILES[3], "Coordinates = objData and objData.Coordinates", "Coordinates = nil", "event coordinates"),
        )
        for relative, before, after, label in mutations:
            with self.subTest(label=label):
                path = self.directory / relative
                source = self.pristine[relative]
                self.assertIn(before, source)
                path.write_text(source.replace(before, after))
                try:
                    result = self.run_fixture()
                    self.assertNotEqual(result.returncode, 0, f"Fixture accepted {label} regression")
                finally:
                    path.write_text(source)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--addon-source", type=Path, help="pinned Questie source (pristine or patched)")
    parser.add_argument("--lua", default=shutil.which("lua5.1") or shutil.which("lua"), help="Lua 5.1 executable")
    arguments, remaining = parser.parse_known_args()
    SOURCE, LUA = arguments.addon_source, arguments.lua
    if not LUA:
        parser.error("Lua 5.1 is required")
    unittest.main(argv=[__file__, *remaining])
