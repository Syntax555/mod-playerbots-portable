"""Exercise MultiBot Buy mode through the native merchant API and real bridge sender."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from FixtureSupport import fork_change, git_apply, multibot_sources, unpatched


ROOT = Path(__file__).resolve().parents[2]
PATCH = fork_change("MultiBot", "multibot-vendor-purchases")
FILES = ("Core/MultiBotComm.lua", "UI/MultiBotInventoryFrame.lua", "UI/MultiBotInventoryItem.lua")
SOURCE = None
LUA = None

SETUP = r'''
MultiBot = {L = function(key, fallback) return fallback or key end}
GetTime = function() return 10 end
UnitName = function() return "Owner" end
CancelTrade = function() end
SendChatMessage = function() error("merchant purchases must use the bridge") end
local messages, ownerPurchases, cursorPickups, sent, dialogs = {}, {}, {}, {}, {}
local cursorType
GetCursorInfo = function() return cursorType end
ClearCursor = function() cursorType = nil end
DEFAULT_CHAT_FRAME = {AddMessage = function(_, text) messages[#messages+1] = text end}
local merchantLink = "|cffffffff|Hitem:2512:0:0:0:0:0:0:0:0|h[Rough Arrow]|h|r"
local merchantPrice, merchantExtendedCost = 10, false
GetMerchantItemLink = function(index) return index == 3 and merchantLink or nil end
GetMerchantItemInfo = function(index)
    if index == 3 then return "Rough Arrow", "arrow", merchantPrice, 200, -1, true, merchantExtendedCost end
end
MerchantFrame = {selectedTab = 1, IsShown = function() return true end}
MERCHANT_HIGH_PRICE_COST = 1500000
BuyMerchantItem = function(index, count)
    ownerPurchases[#ownerPurchases+1] = {index, count}
    return "native-purchase", 42
end
PickupMerchantItem = function(index)
    cursorPickups[#cursorPickups+1] = index
    if index > 0 then cursorType = "merchant" end
    return "native-pickup", 17
end
StaticPopup_Hide = function(key) dialogs[key] = nil end
StackSplitFrame = {shown = false, Hide = function(self) self.shown = false end}
local function confirmPurchase(key, button, quantity)
    assert(button:GetID() == 3 and button.link == merchantLink)
    assert(button.texture == "arrow" and button.price == merchantPrice and button.count == 200)
    MerchantFrame.itemIndex, MerchantFrame.count = button:GetID(), quantity or 1
    dialogs[key] = true
end
MerchantFrame_ConfirmExtendedItemCost = function(button, quantity)
    confirmPurchase("CONFIRM_PURCHASE_TOKEN_ITEM", button, quantity)
end
MerchantFrame_ConfirmHighCostItem = function(button, quantity)
    confirmPurchase("CONFIRM_HIGH_COST_ITEM", button, quantity)
end
-- Native 3.3.5 StaticPopup.lua's OnAccept contract reads these two fields.
local function acceptPopup(key)
    if dialogs[key] then
        dialogs[key] = nil
        BuyMerchantItem(MerchantFrame.itemIndex, MerchantFrame.count)
    end
end
local inventory = {name = "Altbot", action = "s", visible = true, buttons = {}}
inventory.IsVisible = function(self) return self.visible end
inventory.IsShown = inventory.IsVisible
MultiBot.inventory = inventory
for _, key in ipairs({"Sell", "Equip", "Use", "Trade", "Bank", "GuildBank", "Buy", "Destroy"}) do
    local button = {state = key == "Sell"}
    button.setEnable = function() button.state = true end
    button.setDisable = function() button.state = false end
    button.getName = function() return inventory.name end
    inventory.buttons[key] = button
end
'''

ROUTING = r'''
selectMode("Buy")
assert(inventory.action == "b" and inventory.buttons.Buy.state)
BuyMerchantItem(3)
assert(#ownerPurchases == 0, "Buy mode bought for Owner instead of selected Altbot")
assertPurchase("Altbot", 2512, 1)
inventory.name = "Otheralt"
BuyMerchantItem(3, 5)
assert(#ownerPurchases == 0, "switching altbots bought for Owner")
assertPurchase("Otheralt", 2512, 5)
PickupMerchantItem(3)
assert(#cursorPickups == 0, "left click placed an owner's merchant item on the cursor")
assertPurchase("Otheralt", 2512, 1)
assert(#sent == 3, "a merchant click sent duplicate purchases")
'''


def fixture(directory, frame_source, body):
    # Return the real local mode callback from its original chunk; no frame
    # hierarchy or reimplementation of the mode decision is needed.
    marker = '    window.frame:HookScript("OnHide", '
    start = frame_source.index(marker, frame_source.index("function MultiBot.InitializeInventoryFrame()"))
    end = frame_source.index("\n    end)", start) + len("\n    end")
    hide_callback = frame_source[start + len(marker):end]
    source = frame_source + "\nreturn toggleInventoryAction, setInventoryBotName, closeInventoryWindow, " + hide_callback
    return "\n".join((
        SETUP,
        "local toggleMode, setBotName, closeInventory, hideInventory = assert(loadstring("
        + json.dumps(source, ensure_ascii=False) + "))()",
        "dofile(" + json.dumps(str(directory / FILES[0])) + ")",
        "dofile(" + json.dumps(str(directory / FILES[2])) + ")",
        r'''
MultiBot.bridge.connected = true
MultiBot.bridge.inventoryCapable = true
MultiBot.Comm.Send = function(opcode, payload)
    assert(opcode == "RUN")
    sent[#sent+1] = payload
    return true
end
local function selectMode(key)
    if not inventory.buttons[key].state then toggleMode(key, inventory.buttons[key]) end
end
local function assertPurchase(bot, item, count)
    local name, token, itemId, requested = string.match(sent[#sent] or "",
        "^ITEM_ACTION~([^~]+)~([^~]+)~BUY_ITEM~(%d+)~(%d+)$")
    assert(name == bot, "wrong purchase recipient: " .. tostring(name))
    assert(tonumber(itemId) == item and tonumber(requested) == count,
        "wrong merchant item or bundle count: " .. tostring(sent[#sent]))
    local command = MultiBot.bridge.inventoryItemActions[token]
    assert(command.botName == bot and command.itemId == item and command.count == count)
end
''', body))


class MultiBotVendorPurchaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="multibot-vendor-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        multibot_sources(cls.directory, FILES, SOURCE)
        unpatched(cls.directory, PATCH)
        cls.pristine_frame = (cls.directory / FILES[1]).read_text()
        cls.pristine = (cls.directory / FILES[2]).read_text()
        git_apply(cls.directory, PATCH)
        cls.patched = (cls.directory / FILES[2]).read_text()
        cls.frame = (cls.directory / FILES[1]).read_text()

    def run_lua(self, body, source=None, frame_source=None):
        path = self.directory / FILES[2]
        path.write_text(self.patched if source is None else source)
        return subprocess.run([LUA, "-"], input=fixture(self.directory, self.frame if frame_source is None else frame_source, body),
                              text=True, capture_output=True, timeout=20, check=False)

    def assert_lua(self, body, source=None):
        result = self.run_lua(body, source)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_native_merchant_purchase_uses_selected_altbot_and_bundle_count(self):
        original = self.run_lua(ROUTING, self.pristine, self.pristine_frame)
        self.assertNotEqual(original.returncode, 0, "original owner-purchase regression was not rejected")
        self.assertIn("Buy mode bought for Owner", original.stderr)
        self.assert_lua(ROUTING)

    def test_hidden_inventory_and_other_modes_preserve_native_purchase(self):
        self.assert_lua(r'''
selectMode("Buy")
inventory.visible = false
local result, extra = BuyMerchantItem(3, 4)
assert(result == "native-purchase" and extra == 42)
assert(#ownerPurchases == 1 and ownerPurchases[1][1] == 3 and ownerPurchases[1][2] == 4)
local picked, extra = PickupMerchantItem(3)
assert(picked == "native-pickup" and extra == 17 and #cursorPickups == 1)
inventory.visible = true
for _, mode in ipairs({"Sell", "Equip", "Use", "Bank", "GuildBank", "Destroy"}) do
    selectMode(mode)
    local previous = #ownerPurchases
    BuyMerchantItem(3)
    assert(#ownerPurchases == previous+1, mode .. " blocked normal owner purchase")
    PickupMerchantItem(3)
end
selectMode("Buy")
toggleMode("Buy", inventory.buttons.Buy)
assert(inventory.action == "")
BuyMerchantItem(3, 2)
assert(#ownerPurchases == 8)
assert(#cursorPickups == 7)
assert(#sent == 0, "inactive Buy mode sent bot purchases")
''')

    def test_bridge_failure_never_falls_back_to_owner_purchase(self):
        self.assert_lua(r'''
selectMode("Buy")
MultiBot.bridge.connected = false
BuyMerchantItem(3)
PickupMerchantItem(3)
assert(#ownerPurchases == 0 and #sent == 0, "disconnected bridge purchased for owner")
assert(#cursorPickups == 0, "disconnected bridge left an owner purchase on the cursor")
assert(#messages > 0, "disconnected purchase gave no feedback")
MultiBot.bridge.connected = true
MultiBot.Comm.Send = function() return false end
BuyMerchantItem(3)
PickupMerchantItem(3)
assert(#ownerPurchases == 0 and #sent == 0, "failed bridge send purchased for owner")
assert(#cursorPickups == 0)
MultiBot.Comm.RunInventoryItemAction = nil
BuyMerchantItem(3)
PickupMerchantItem(3)
assert(#ownerPurchases == 0, "missing bridge API purchased for owner")
assert(#cursorPickups == 0)
''')

    def test_invalid_merchant_item_never_buys_for_owner(self):
        self.assert_lua(r'''
selectMode("Buy")
for _, link in ipairs({"", "not an item", "|Hspell:2512|h[Spell]|h", "|Hitem:0|h[Invalid]|h"}) do
    merchantLink = link
    BuyMerchantItem(3)
    PickupMerchantItem(3)
end
BuyMerchantItem(99)
assert(#ownerPurchases == 0 and #sent == 0, "invalid merchant item escaped bot routing")
assert(#cursorPickups == 0)
assert(#messages > 0, "invalid purchase gave no feedback")
''')

    def test_owner_cursor_item_sale_keeps_native_zero_index(self):
        self.assert_lua(r'''
selectMode("Buy")
local result, extra = PickupMerchantItem(0)
assert(result == "native-pickup" and extra == 17)
assert(#cursorPickups == 1 and cursorPickups[1] == 0)
assert(#sent == 0, "selling an owner's cursor item became a bot purchase")
''')

    def test_expensive_and_currency_purchases_keep_native_confirmation(self):
        self.assert_lua(r'''
selectMode("Buy")
for _, kind in ipairs({"CONFIRM_HIGH_COST_ITEM", "CONFIRM_PURCHASE_TOKEN_ITEM"}) do
    merchantPrice = kind == "CONFIRM_HIGH_COST_ITEM" and MERCHANT_HIGH_PRICE_COST or 0
    merchantExtendedCost = kind == "CONFIRM_PURCHASE_TOKEN_ITEM"
    local previous = #sent
    MerchantFrame.selectedTab = 2
    PickupMerchantItem(3)
    assert(dialogs[kind] and #sent == previous, "purchase skipped native confirmation")
    setBotName("Altbot")
    assert(dialogs[kind], "refreshing the same bot cancelled its purchase")
    acceptPopup(kind)
    assert(#sent == previous+1)
    assertPurchase("Altbot", 2512, 1)
end
assert(#ownerPurchases == 0 and #cursorPickups == 0)
''')

    def test_pending_purchase_is_cancelled_when_bot_mode_or_window_changes(self):
        self.assert_lua(r'''
for _, kind in ipairs({"CONFIRM_HIGH_COST_ITEM", "CONFIRM_PURCHASE_TOKEN_ITEM"}) do
    for _, transition in ipairs({"bot", "mode", "toggle", "close", "hide"}) do
        setBotName("Altbot")
        selectMode("Buy")
        merchantPrice = kind == "CONFIRM_HIGH_COST_ITEM" and MERCHANT_HIGH_PRICE_COST or 0
        merchantExtendedCost = kind == "CONFIRM_PURCHASE_TOKEN_ITEM"
        PickupMerchantItem(3)
        assert(dialogs[kind])
        StackSplitFrame.shown = true
        if transition == "bot" then setBotName("Otheralt")
        elseif transition == "mode" then selectMode("Sell")
        elseif transition == "toggle" then toggleMode("Buy", inventory.buttons.Buy)
        elseif transition == "close" then closeInventory()
        else hideInventory() end
        assert(not dialogs[kind] and not StackSplitFrame.shown,
            transition .. " retained a purchase for the previous recipient")
        acceptPopup(kind)
    end
end
assert(#sent == 0 and #ownerPurchases == 0 and #cursorPickups == 0)
''')

    def test_entering_buy_mode_cancels_owner_confirmation_and_stack_split(self):
        self.assert_lua(r'''
for _, key in ipairs({"CONFIRM_HIGH_COST_ITEM", "CONFIRM_PURCHASE_TOKEN_ITEM"}) do
    dialogs[key] = true
end
StackSplitFrame.shown = true
selectMode("Buy")
assert(not StackSplitFrame.shown and next(dialogs) == nil,
    "entering Buy mode retained an owner purchase for the bot")
acceptPopup("CONFIRM_HIGH_COST_ITEM")
acceptPopup("CONFIRM_PURCHASE_TOKEN_ITEM")
assert(#sent == 0 and #ownerPurchases == 0)
''')

    def test_buy_mode_clears_merchant_cursor_and_preserves_other_cursor_items(self):
        self.assert_lua(r'''
for _, kind in ipairs({"item", "money", "merchant"}) do
    cursorType = kind
    selectMode("Buy")
    assert(cursorType == (kind ~= "merchant" and kind or nil),
        "mode change mishandled " .. kind .. " cursor")
    selectMode("Sell")
end
''')

    def test_purchase_and_recipient_guards_reject_mutations(self):
        mutations = (
            ("buy routing", "item", "if not botName then\n        return buyMerchantItem",
             "if true then\n        return buyMerchantItem", ROUTING, "Buy mode bought for Owner"),
            ("left click routing", "item",
             "if not getMerchantInventoryBotName() or not index or index <= 0 then",
             "if true then", ROUTING, "left click placed an owner's merchant item"),
            ("selected recipient", "item", "return inventory.name\n", 'return "Owner"\n',
             ROUTING, "wrong purchase recipient"),
            ("bundle count", "item", "{ count = count or 1 }", "{ count = 1 }",
             ROUTING, "wrong merchant item or bundle count"),
            ("visible inventory", "item", "and inventory.IsVisible and inventory:IsVisible()", "",
             ('selectMode("Buy"); inventory.visible=false; BuyMerchantItem(3); '
             'assert(#ownerPurchases==1, "hidden inventory captured owner purchase")'),
             "hidden inventory captured owner purchase"),
            ("Buy mode", "item", 'inventory.action == "b" and ', "",
             'BuyMerchantItem(3); assert(#ownerPurchases==1, "Sell mode captured owner purchase")',
             "Sell mode captured owner purchase"),
            ("failed send", "item",
             '        addInventorySystemMessage(string.format(\n            inventoryItemL("inventory.item_action.failed",',
             ('        buyMerchantItem(index, count)\n'
             '        addInventorySystemMessage(string.format(\n            inventoryItemL("inventory.item_action.failed",'),
             ('selectMode("Buy"); MultiBot.bridge.connected=false; BuyMerchantItem(3); '
             'assert(#ownerPurchases==0, "failed send purchased for owner")'),
             "failed send purchased for owner"),
            ("price confirmation", "item", "elseif price and price >= MERCHANT_HIGH_PRICE_COST then",
             "elseif false then",
             ('selectMode("Buy"); merchantPrice=MERCHANT_HIGH_PRICE_COST; PickupMerchantItem(3); '
             'assert(dialogs.CONFIRM_HIGH_COST_ITEM, "missing price confirmation")'),
             "missing price confirmation"),
            ("currency confirmation", "item", "if extendedCost then", "if false then",
             ('selectMode("Buy"); merchantExtendedCost=true; PickupMerchantItem(3); '
             'assert(dialogs.CONFIRM_PURCHASE_TOKEN_ITEM, "missing currency confirmation")'),
             "missing currency confirmation"),
            ("mode cancellation", "frame",
             '    cancelInventoryMerchantPurchase(nextState and nextState.value == "b")\n', "",
             ('selectMode("Buy"); dialogs.CONFIRM_HIGH_COST_ITEM=true; selectMode("Sell"); '
             'assert(next(dialogs)==nil, "mode change retained confirmation")'),
             "mode change retained confirmation"),
            ("entering Buy cancellation", "frame",
             'cancelInventoryMerchantPurchase(nextState and nextState.value == "b")',
             "cancelInventoryMerchantPurchase()",
             ('dialogs.CONFIRM_HIGH_COST_ITEM=true; selectMode("Buy"); '
             'assert(next(dialogs)==nil, "entering Buy retained owner confirmation")'),
             "entering Buy retained owner confirmation"),
            ("bot cancellation", "frame",
             '    if inventory.name ~= (botName or "") then\n        cancelInventoryMerchantPurchase()\n    end\n',
             "",
             ('selectMode("Buy"); dialogs.CONFIRM_HIGH_COST_ITEM=true; setBotName("Otheralt"); '
             'assert(next(dialogs)==nil, "bot change retained confirmation")'),
             "bot change retained confirmation"),
            ("hidden window cancellation", "frame",
             '    window.frame:HookScript("OnHide", function()\n        cancelInventoryMerchantPurchase()\n',
             '    window.frame:HookScript("OnHide", function()\n',
             ('selectMode("Buy"); dialogs.CONFIRM_HIGH_COST_ITEM=true; hideInventory(); '
             'assert(next(dialogs)==nil, "hidden window retained confirmation")'),
             "hidden window retained confirmation"),
            ("merchant cursor cancellation", "frame", 'GetCursorInfo() == "merchant"', "false",
             'cursorType="merchant"; selectMode("Buy"); assert(cursorType==nil, "merchant cursor survived")',
             "merchant cursor survived"),
            ("ordinary cursor preservation", "frame", 'GetCursorInfo() == "merchant"', "true",
             'cursorType="item"; selectMode("Buy"); assert(cursorType=="item", "ordinary cursor lost")',
             "ordinary cursor lost"),
        )
        for label, target, old, new, body, failure in mutations:
            with self.subTest(mutation=label):
                original = self.patched if target == "item" else self.frame
                self.assertIn(old, original, label + " mutation was not applied")
                changed = original.replace(old, new)
                result = self.run_lua(body, changed if target == "item" else None,
                                      changed if target == "frame" else None)
                self.assertNotEqual(result.returncode, 0, label + " mutation survived")
                self.assertIn(failure, result.stderr, result.stdout + result.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--addon-source", type=Path, help="pinned pristine or prepared MultiBot source")
    parser.add_argument("--lua", default=shutil.which("lua5.1") or shutil.which("lua"),
                        help="Lua 5.1 executable")
    arguments, remaining = parser.parse_known_args()
    SOURCE, LUA = arguments.addon_source, arguments.lua
    if not LUA:
        parser.error("Lua 5.1 is required")
    unittest.main(argv=[__file__, *remaining])
