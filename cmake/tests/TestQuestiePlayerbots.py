"""Run the pinned Questie Playerbots integration through native comms with Lua 5.1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from FixtureSupport import fork_history, function, prepared_core


ROOT = Path(__file__).resolve().parents[2]
FILES = ("Modules/Network/QuestiePlayerbots.lua", "Modules/Network/QuestieComms.lua",
         "Modules/Network/QuestieCommsData.lua", "Modules/Network/QuestiePartyObjectives.lua",
         "Modules/Quest/QuestieQuest.lua", "Modules/Quest/QuestieQuestPrivates.lua",
         "Modules/QuestieEventHandler.lua", "tools/tests/test_group_roster_quest_sync.lua")
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
        cls.addon = addon
        cls.history = fork_history("Questie-335", addon["url"], addon["revision"], 64)
        cls.pristine = {relative: (cls.directory / relative).read_text() for relative in FILES}

    def run_fixture(self):
        fixture = (ROOT / "cmake/tests/QuestiePlayerbotsFixture.lua").read_text()
        return subprocess.run([LUA, "-"], input=f"local SOURCE = {json.dumps(str(self.directory))}\n{fixture}",
                              text=True, capture_output=True, check=False, timeout=20)

    def test_native_comms_and_lifecycle(self):
        result = self.run_fixture()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def run_group_roster_fixture(self):
        return subprocess.run([LUA, FILES[7]], cwd=self.directory, text=True,
                              capture_output=True, check=False, timeout=20)

    def test_native_group_roster_lifecycle(self):
        result = self.run_group_roster_fixture()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_native_group_roster_regressions_are_detected(self):
        mutations = (
            (FILES[6], "previousMembers >= 2 and currentMembers > previousMembers", "false",
             "new party member quest-log request"),
            (FILES[6], "    _PruneDepartedGroupMembers()\n", "",
             "departed member cleanup"),
            (FILES[1], "        QuestieComms.data:RemovePlayer(name)\n", "",
             "departed member tooltip cleanup"),
            (FILES[1], "if not next(players) then", "if false then",
             "empty remote quest cleanup"),
        )
        for relative, before, after, label in mutations:
            with self.subTest(label=label):
                path = self.directory / relative
                source = self.pristine[relative]
                self.assertIn(before, source)
                path.write_text(source.replace(before, after))
                try:
                    result = self.run_group_roster_fixture()
                    self.assertNotEqual(result.returncode, 0, f"Fixture accepted {label} regression")
                finally:
                    path.write_text(source)

    def test_native_upstream_and_retained_fork_changes_are_ancestors(self):
        revision = self.addon["revision"]
        for commit in (self.addon["upstream"]["revision"], *self.addon["forkChanges"].values()):
            with self.subTest(commit=commit):
                result = subprocess.run(["git", "-C", str(self.history), "merge-base", "--is-ancestor",
                                         commit, revision], capture_output=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr.decode())

        result = subprocess.run(["git", "-C", str(self.history), "merge-base", "--is-ancestor",
                                 "438000dba6352b2123f882e74ded745889b890d6",
                                 self.addon["upstream"]["revision"]], capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, "Playerbots quest progress must come from imported upstream")

    def test_native_bridge_guid_contract(self):
        core = prepared_core()
        bridge = (core / "modules/mod-multibot-bridge/src/MultiBotBridge.cpp").read_text()
        packets = function(bridge, "std::vector<std::pair<std::string, std::string>> BuildQuestProgressPackets(")
        self.assertIn('packets.emplace_back("QUEST_PROGRESS_BEGIN", header + kFieldSeparator + botGuid.ToString());',
                      packets)
        guid = function((core / "src/server/game/Entities/Object/ObjectGuid.cpp").read_text(),
                        "std::string ObjectGuid::ToString() const")
        self.assertIn('"GUID Full: 0x" << std::hex << std::setw(16)', guid)
        self.assertIn('std::setfill(\'0\') << _guid << std::dec', guid)
        self.assertIn('" Type: " << GetTypeName()', guid)
        self.assertIn('" Low: " << GetCounter()', guid)

    def test_regressions_are_detected(self):
        mutations = (
            (FILES[0], "if name ~= playerName then", "if true then", "own-character roster exclusion"),
            (FILES[0], 'if name and UnitIsConnected("raid" .. i) then', "if name then", "connected raid roster"),
            (FILES[0], 'if name and UnitIsConnected("party" .. i) then', "if name then", "connected party roster"),
            (FILES[0], "        SyncGroupRoster()\n        return\n", "        return\n", "initial roster sync"),
            (FILES[0], "local owned = token == current or", "local owned = true or", "request token ownership"),
            (FILES[0], 'token:match("^qpp%d+x%d+$") ~= nil', "true", "stale issued token"),
            (FILES[0], "not bridgeUnsupported and helloRetries", "helloRetries", "unsupported bridge probing"),
            (FILES[0], "helloRetries < MAX_HELLO_RETRIES\n", "true\n", "bounded bridge probing"),
            (FILES[0], "request.watch and isBridgePush", "isBridgePush", "push token requires WATCH"),
            (FILES[0], "and validIdentity then", "then",
             "in-flight roster identity"),
            (FILES[0], "return guid:lower()", "return guid", "native GUID casing"),
            (FILES[0], "and objective.type == objectiveType", "", "per-type objective indices"),
            (FILES[0], "or -position", "or -rawObjective.index", "per-type unknown counters"),
            (FILES[0], "indices[position] = FindSameTypeObjectiveIndex(",
             "indices[position] = nil and FindSameTypeObjectiveIndex(", "database objective pairing"),
            (FILES[0], "databaseObjective and databaseObjective.Id or", "", "database objective identity"),
            (FILES[0], "unmatched[objectiveType] == remaining[objectiveType]", "true", "ambiguous objective counts"),
            (FILES[2], 'if localText and localText ~= "" then', "if false then", "local objective text"),
            (FILES[0], "if not usedIndices[objectiveIndex] then", "if true then", "remaining database objectives"),
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
