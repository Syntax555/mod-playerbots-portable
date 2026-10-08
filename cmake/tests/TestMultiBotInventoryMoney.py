#!/usr/bin/env python3
"""Exercise pinned MultiBot's actual inventory money UI and bridge dispatcher."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/multibot-inventory-money.patch"
SOURCE = None
LUA = None
FILES = ("UI/MultiBotInventoryFrame.lua", "Core/MultiBotComm.lua")


def between(source, start, end):
    begin = source.index(start)
    return source[begin:source.index(end, begin)]


def fixture(ui_source, comm_path, body):
    # Run the actual formatting, summary updates and request completion methods
    # without creating WoW's frame hierarchy. The complete Comm module remains
    # intact: its sender, bot, request-token and opcode guards are exercised.
    helpers = between(ui_source, "local function formatMoneyLabel(",
                      "local function getInventoryWindowTitle(")
    bot_name = between(ui_source, "local function setInventoryBotName(",
                       "local function resetInventoryViewState(")
    begin_payload = between(ui_source, "    function inventory:beginPayload(",
                            "    function inventory:applySummaryLine(")
    summary = between(ui_source, "    function inventory:applySummaryData(",
                      "    function inventory:appendItem(")
    end_payload = between(ui_source, "    function inventory:endPayload(",
                          "    function inventory:setBotName(")
    return "\n".join((
        '''
MultiBot = {L = function(key, fallback)
    if key == "info.inventory.money_label" then return "Geld" end
    return fallback or key
end}
GetTime = function() return 10 end
UnitName = function() return "Owner" end
local inventory = {
    name = "BotA",
    IsVisible = function() return true end,
    resetItems = function() end,
    captureLegacyItemMetadata = function() end,
    moneyLabel = {SetText = function(self, text) self.text = text end},
    bagSlotsLabel = {SetText = function(self, text) self.text = text end},
}
MultiBot.inventory = inventory
local function plain(text)
    return (text:gsub("|c%x%x%x%x%x%x%x%x", ""):gsub("|r", ""))
end
''', helpers, bot_name, begin_payload, summary, end_payload,
        "dofile(" + json.dumps(str(comm_path)) + ")",
        '''
MultiBot.bridge.connected = true
MultiBot.bridge.capabilitiesResolved = true
MultiBot.bridge.inventoryCapable = true
MultiBot.bridge.inventoryExactCapable = true
local sent = {}
MultiBot.Comm.Send = function(opcode, payload)
    table.insert(sent, {opcode, payload})
    return true
end
local function beginRequest(bot)
    inventory.name = bot
    assert(MultiBot.Comm.RequestInventory(bot))
    local token = MultiBot.bridge.inventoryActive.token
    assert(MultiBot.Comm.HandleAddonMessage("MBOT", "INV_BEGIN~" .. bot .. "~" .. token, "WHISPER", "Owner"))
    return token
end
local function response(bot, token, g, s, c, sender)
    local message = table.concat({"INV_SUMMARY", bot, token, g, s, c, 2, 16}, "~")
    assert(MultiBot.Comm.HandleAddonMessage("MBOT", message, "WHISPER", sender or "Owner"))
end
''', body))


class MultiBotInventoryMoneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="multibot-money-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        dependency = next(item for item in json.loads((ROOT / "versions.lock.json").read_text())["clientAddons"]
                          if item["name"] == "MultiBot")
        revision = dependency["revision"]
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("MultiBot source revision must be pinned")
        for relative in FILES:
            destination = cls.directory / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if SOURCE is not None:
                shutil.copyfile(SOURCE / relative, destination)
            else:
                url = ("https://raw.githubusercontent.com/Wishmaster117/MultiBot-Chatless/"
                       + revision + "/" + relative)
                with urllib.request.urlopen(url, timeout=30) as response:
                    content = response.read(2 * 1024 * 1024 + 1)
                if len(content) > 2 * 1024 * 1024:
                    raise ValueError("MultiBot fixture source exceeds the supported size")
                destination.write_bytes(content)
        # Local callers can supply either pristine or already prepared sources.
        # Normalize only the temporary fixture to pristine before applying the
        # exact release patch, leaving the supplied installation untouched.
        check = subprocess.run(["git", "apply", "--check", str(PATCH)], cwd=cls.directory,
                               capture_output=True, text=True)
        if check.returncode:
            subprocess.run(["git", "apply", "--reverse", "--check", str(PATCH)],
                           cwd=cls.directory, check=True, capture_output=True)
            subprocess.run(["git", "apply", "--reverse", str(PATCH)],
                           cwd=cls.directory, check=True, capture_output=True)
        cls.pristine_ui = (cls.directory / FILES[0]).read_text()
        subprocess.run(["git", "apply", str(PATCH)], cwd=cls.directory,
                       check=True, capture_output=True)
        cls.ui = (cls.directory / FILES[0]).read_text()
        cls.comm = cls.directory / FILES[1]

    def run_lua(self, body, pristine=False):
        script = fixture(self.pristine_ui if pristine else self.ui, self.comm, body)
        result = subprocess.run([LUA, "-"], input=script, text=True,
                                capture_output=True, timeout=20)
        if not pristine:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_bot_with_less_than_one_gold_has_visible_silver_and_copper(self):
        assertion = '''
local token = beginRequest("BotA")
response("BotA", token, 0, 99, 99)
assert(plain(inventory.moneyLabel.text) == "Geld: 0g99s99c", inventory.moneyLabel.text)
assert(inventory.summary.silver == 99 and inventory.summary.copper == 99)
'''
        self.assertNotEqual(self.run_lua(assertion, pristine=True).returncode, 0,
                            "regression fixture must fail with the original gold-only formatter")
        self.run_lua(assertion)

    def test_nonzero_gold_retains_all_coins_and_bag_count(self):
        self.run_lua('''
local token = beginRequest("BotA")
response("BotA", token, 123, 45, 67)
assert(plain(inventory.moneyLabel.text) == "Geld: 123g45s67c")
assert(inventory.summary.gold == 123 and inventory.summary.silver == 45 and inventory.summary.copper == 67)
assert(plain(inventory.bagSlotsLabel.text) == "Bag Slots: 2/16")
''')

    def test_zero_copper_and_server_money_limit_use_compact_text(self):
        self.run_lua('''
local token = beginRequest("BotA")
for _, coins in ipairs({{0,0,0,"Geld: 0g0s0c"}, {0,0,1,"Geld: 0g0s1c"},
                       {429496,72,95,"Geld: 429496g72s95c"}}) do
    response("BotA", token, coins[1], coins[2], coins[3])
    local displayed = plain(inventory.moneyLabel.text)
    assert(displayed == coins[4], displayed)
    assert(#displayed <= 19, "money exceeds compact left-panel text budget")
end
''')

    def test_unrelated_sender_bot_stale_token_and_switched_view_are_ignored(self):
        self.run_lua('''
local token = beginRequest("BotA")
response("BotA", token, 12, 34, 56)
local original = inventory.moneyLabel.text
response("BotA", token, 99, 99, 99, "OtherPlayer")
response("BotB", token, 99, 99, 99)
response("BotA", "stale-request", 99, 99, 99)
assert(inventory.moneyLabel.text == original)
inventory.name = "BotB"
response("BotA", token, 99, 99, 99)
assert(inventory.moneyLabel.text == original)
''')

    def test_exact_inventory_refresh_preserves_summary_and_money(self):
        self.run_lua('''
local token = beginRequest("BotA")
response("BotA", token, 12, 34, 56)
local money = inventory.moneyLabel.text
assert(MultiBot.Comm.HandleAddonMessage("MBOT", "INV_END~BotA~" .. token, "WHISPER", "Owner"))
assert(MultiBot.bridge.inventoryActive == nil)
local exact = MultiBot.bridge.inventoryExactActive
assert(exact and sent[#sent][2]:find("INVENTORY_EXACT~BotA~", 1, true) == 1)
local received
MultiBot.OnBridgeInventoryExactSnapshot = function(bot, snapshot)
    received = snapshot
end
assert(MultiBot.Comm.HandleAddonMessage("MBOT", "INV_EXACT_BEGIN~BotA~" .. exact.token, "WHISPER", "Owner"))
assert(MultiBot.Comm.HandleAddonMessage("MBOT", "INV_BAG~BotA~" .. exact.token .. "~BACKPACK~255~23~16~0", "WHISPER", "Owner"))
assert(MultiBot.Comm.HandleAddonMessage("MBOT", "INV_EXACT_END~BotA~" .. exact.token, "WHISPER", "Owner"))
assert(received and received.botName == "BotA" and #received.bags == 1)
assert(inventory.moneyLabel.text == money)
assert(inventory.summary.gold == 12 and inventory.summary.silver == 34 and inventory.summary.copper == 56)
''')

    def test_new_bot_request_resets_previous_bot_coins(self):
        self.run_lua('''
local token = beginRequest("BotA")
response("BotA", token, 123, 45, 67)
local nextToken = beginRequest("BotB")
assert(plain(inventory.moneyLabel.text) == "Geld: 0g0s0c")
response("BotA", token, 999, 99, 99)
assert(plain(inventory.moneyLabel.text) == "Geld: 0g0s0c")
response("BotB", nextToken, 0, 12, 34)
assert(plain(inventory.moneyLabel.text) == "Geld: 0g12s34c")
''')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--addon-source", type=Path,
                        help="existing pinned MultiBot source; defaults to two pinned raw Lua files")
    parser.add_argument("--lua", default=shutil.which("lua5.1") or shutil.which("lua"),
                        help="Lua 5.1 executable")
    arguments, remaining = parser.parse_known_args()
    SOURCE = arguments.addon_source
    LUA = arguments.lua
    if not LUA:
        parser.error("Lua 5.1 is required")
    unittest.main(argv=[__file__, *remaining])
