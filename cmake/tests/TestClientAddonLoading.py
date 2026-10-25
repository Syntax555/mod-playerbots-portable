"""Exercise client library loading and binding headers against pinned addon sources."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from FixtureSupport import fork_change, git_apply, multibot_sources, unpatched


ROOT = Path(__file__).resolve().parents[2]
LIBRARIES = ("Libs/LibStub/LibStub.lua", "Libs/CallbackHandler-1.0/CallbackHandler-1.0.lua",
             "Libs/libdatabroker-1-1/LibDataBroker-1.1.lua", "Libs/LibDBIcon-1.0/LibDBIcon-1.0.lua")
LUA = None

# Only the event frame is needed while the real embedded libraries initialize.
FIXTURE = r'''
assert(_VERSION == "Lua 5.1")
strmatch = string.match
CreateFrame = function(kind)
  assert(kind == "Frame")
  return {
    SetScript = function(self, event, callback)
      assert(event == "OnEvent" and type(callback) == "function")
    end,
    RegisterEvent = function(self, event) assert(event == "PLAYER_LOGIN") end,
  }
end
for _, path in ipairs(LIBRARIES) do dofile(path) end
local broker = LibStub("LibDataBroker-1.1")
local icon = LibStub("LibDBIcon-1.0")
local object = broker:NewDataObject("MultiBot", {type="launcher", icon="test"})
icon:Register("MultiBot", object, {hide=true})
assert(icon:IsRegistered("MultiBot"))
assert(broker:GetDataObjectByName("MultiBot") == object)
'''


class ClientAddonLoadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="client-addon-loading-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.multibot = Path(cls.temporary.name) / "MultiBot"
        cls.multibot.mkdir()
        multibot_sources(cls.multibot, ("MultiBot.toc", *LIBRARIES))
        # The pinned fork carries the change; revert it for the upstream baseline.
        patch = fork_change("MultiBot", "multibot-library-load-order")
        unpatched(cls.multibot, patch)
        cls.original_toc = (cls.multibot / "MultiBot.toc").read_text()
        git_apply(cls.multibot, patch)
        cls.toc = (cls.multibot / "MultiBot.toc").read_text()

        cls.questie = Path(cls.temporary.name) / "Questie-335"
        cls.questie.mkdir()
        lock = json.loads((ROOT / "versions.lock.json").read_text())
        addon = next(item for item in lock["sourceAddons"] if item["name"] == "Questie-335")
        source = subprocess.run(
            ["git", "-C", str(ROOT / ".module-cache/client-addon-Questie-335"),
             "show", f"{addon['revision']}:Bindings.xml"], check=True, capture_output=True).stdout
        (cls.questie / "Bindings.xml").write_bytes(source)
        patch = fork_change("Questie-335", "questie-binding-header")
        unpatched(cls.questie, patch)
        cls.original_bindings = (cls.questie / "Bindings.xml").read_text()
        git_apply(cls.questie, patch)
        cls.bindings = (cls.questie / "Bindings.xml").read_text()

    def load_libraries(self, toc):
        paths = [line.strip().replace("\\", "/") for line in toc.splitlines()]
        paths = [path for path in paths if path in LIBRARIES]
        self.assertCountEqual(paths, LIBRARIES)
        source = "local LIBRARIES = {" + ",".join(json.dumps(str(self.multibot / path)) for path in paths) + "}\n"
        return subprocess.run([LUA, "-"], input=source + FIXTURE, text=True,
                              capture_output=True, check=False, timeout=20)

    def assert_unique_header(self, source):
        bindings = ET.fromstring(source).findall("Binding")
        self.assertEqual([binding.get("header") for binding in bindings if "header" in binding.attrib], ["QUESTIE"])
        self.assertEqual(bindings[0].get("header"), "QUESTIE")

    def test_multibot_libraries_initialize_in_toc_order(self):
        result = self.load_libraries(self.toc)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_original_multibot_order_reproduces_missing_broker(self):
        self.assertNotEqual(self.original_toc, self.toc)
        result = self.load_libraries(self.original_toc)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("LibDBIcon-1.0 requires LibDataBroker-1.1.", result.stderr)

    def test_questie_bindings_preserve_actions_with_one_header(self):
        def actions(source):
            return [({key: value for key, value in binding.attrib.items() if key != "header"}, binding.text)
                    for binding in ET.fromstring(source).findall("Binding")]

        self.assertEqual(len(actions(self.bindings)), 3)
        self.assertEqual(actions(self.bindings), actions(self.original_bindings))
        self.assert_unique_header(self.bindings)

    def test_original_questie_headers_are_rejected(self):
        self.assertNotEqual(self.original_bindings, self.bindings)
        self.assertEqual(self.original_bindings.count('header="QUESTIE"'), 3)
        with self.assertRaises(AssertionError):
            self.assert_unique_header(self.original_bindings)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lua", default=shutil.which("lua5.1") or shutil.which("lua"), help="Lua 5.1 executable")
    arguments, remaining = parser.parse_known_args()
    LUA = arguments.lua
    if not LUA:
        parser.error("Lua 5.1 is required")
    unittest.main(argv=[__file__, *remaining])
