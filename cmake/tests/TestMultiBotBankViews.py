"""Run MultiBot's bank window and dispatcher against delayed bank replies."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from FixtureSupport import multibot_sources


FILES = ('Core/MultiBotComm.lua', 'UI/MultiBotBankFrame.lua',
         'Libs/AceGUI-3.0/AceGUI-3.0.lua', 'Libs/AceGUI-3.0/widgets/AceGUIContainer-Window.lua')
FIXTURE = r'''
MultiBot = {L = function(key, fallback) return fallback or key end,
            TimerAfter = function() end, SafeTexturePath = function(path) return path end}
GetTime = function() return 10 end
UnitName = function() return "Owner" end
local function noop() end
local function widget()
    local w = {shown = true, scripts = {}}
    for _, method in ipairs({"SetPoint", "SetSize", "SetWidth", "SetHeight", "SetFrameStrata",
        "SetBackdrop", "SetBackdropColor", "SetBackdropBorderColor", "SetJustifyH", "SetTexture"}) do
        w[method] = noop
    end
    function w:SetText(text) self.text = text end
    function w:SetScript(key, callback) self.scripts[key] = callback end
    function w:Show() self.shown = true end
    function w:Hide() self.shown = false end
    function w:IsShown() return self.shown end
    function w:Enable() self.enabled = true end
    function w:Disable() self.enabled = false end
    function w:SetAlpha(alpha) self.alpha = alpha end
    w.CreateTexture, w.CreateFontString = widget, widget
    return w
end
CreateFrame = widget
UIParent = widget()
local aceGUI = {}
function aceGUI:Create(kind)
    assert(kind == "Window")
    local window = {frame = widget(), content = widget(), SetLayout = noop,
                    SetWidth = noop, SetHeight = noop, EnableResize = noop}
    function window:SetTitle(title) self.title = title end
    function window:Show() self.frame:Show() end
    function window:Hide() self.frame:Hide() end
    function window:IsShown() return self.frame:IsShown() end
    return window
end
LibStub = function(name) assert(name == "AceGUI-3.0") return aceGUI end
GetItemInfo = function(id) return "Item " .. id, "|Hitem:" .. id .. "|h[Item]|h", 1 end
GetItemIcon = function() return "Interface\\Icons\\INV_Misc_QuestionMark" end
@SOURCES@
MultiBot.bridge.connected = true
MultiBot.Comm.Send = function() return true end
local function open(mode, bot)
    local token = mode == "bank" and MultiBot.OpenBotBank(bot) or MultiBot.OpenBotGuildBank(bot)
    assert(token)
    return token
end
local function reply(mode, bot, token)
    local prefix = mode == "bank" and "BANK" or "GBANK"
    local function deliver(opcode, tail)
        assert(MultiBot.Comm.HandleAddonMessage("MBOT", prefix .. opcode .. "~" .. bot .. "~" .. token
                                               .. (tail or ""), "WHISPER", "Owner"))
    end
    deliver("_BEGIN")
    deliver("_ITEM", "~|Hitem:6948|h[Hearthstone]|h")
    if mode == "gbank" then deliver("_RIGHTS", "~1~5") end
    deliver("_END")
end
@SCENARIO@
'''

SCENARIOS = {
    'current window': r'''
for _, mode in ipairs({"bank", "gbank"}) do
    local token = open(mode, "BotA")
    reply(mode, "BotA", token)
    local frame = MultiBot.bankFrame
    assert(frame:IsShown() and frame.botName == "BotA" and frame.mode == mode)
    assert(#frame.items == 1 and frame.items[1].itemId == 6948, "current bank reply was discarded")
    if mode == "gbank" then assert(frame.gbankCanWithdraw and frame.gbankWithdrawRemaining == 5) end
end
''',
    'closed window': r'''
for _, mode in ipairs({"bank", "gbank"}) do
    local token = open(mode, "BotA")
    MultiBot.bankFrame:Hide()
    reply(mode, "BotA", token)
    assert(not MultiBot.bankFrame:IsShown(), "delayed bank reply reopened a closed window")
end
''',
    'switched mode': r'''
for _, mode in ipairs({"bank", "gbank"}) do
    local token = open(mode, "BotA")
    local other = mode == "bank" and "gbank" or "bank"
    local current = open(other, "BotA")
    reply(mode, "BotA", token)
    local frame = MultiBot.bankFrame
    assert(frame.mode == other and #frame.items == 0, "delayed bank reply changed the selected bank mode")
    reply(other, "BotA", current)
    assert(frame.mode == other and #frame.items == 1)
end
''',
    'switched bot': r'''
for _, mode in ipairs({"bank", "gbank"}) do
    local token = open(mode, "BotA")
    -- A lost connection can reject the next request while the previous reply is in flight.
    MultiBot.bridge.connected = false
    local started
    if mode == "bank" then started = MultiBot.OpenBotBank("BotB")
    else started = MultiBot.OpenBotGuildBank("BotB") end
    assert(not started)
    reply(mode, "BotA", token)
    local frame = MultiBot.bankFrame
    assert(frame.botName == "BotB" and #frame.items == 0, "delayed bank reply changed the selected bot")
    local current = open(mode, "BotB")
    reply(mode, "BotB", current)
    assert(frame.botName == "BotB" and #frame.items == 1)
end
''',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--addon-source', type=Path)
    parser.add_argument('--lua', default=shutil.which('lua5.1') or shutil.which('lua'))
    args = parser.parse_args()
    if not args.lua:
        parser.error('Lua 5.1 is required')
    with tempfile.TemporaryDirectory(prefix='multibot-bank-') as temporary:
        directory = Path(temporary)
        multibot_sources(directory, FILES, args.addon_source)
        # Match the bundled AceGUI window's visibility contract used by the double.
        ace = (directory / FILES[2]).read_text()
        window = (directory / FILES[3]).read_text()
        assert 'return self.frame:IsShown()' in ace
        assert 'self.frame:Hide()' in window and 'self.frame:Show()' in window
        sources = '\n'.join('dofile(' + json.dumps(str(directory / file)) + ')' for file in FILES[:2])
        fixture = FIXTURE.replace('@SOURCES@', sources)
        bank = directory / FILES[1]
        source = bank.read_text()
        for label, scenario in SCENARIOS.items():
            result = subprocess.run([args.lua, '-'], input=fixture.replace('@SCENARIO@', scenario),
                                    text=True, capture_output=True, timeout=20, check=False)
            assert result.returncode == 0, (label, result.stdout + result.stderr)
            print('Bank window passed:', label)
        mutations = (
            ('closed window', 'return frame and frame.IsShown and frame:IsShown()', 'return frame'),
            ('switched mode', 'frame.mode == mode', 'true'),
            ('switched bot', 'string.lower(tostring(frame.botName or "")) == string.lower(tostring(botName or ""))', 'true'),
        )
        for label, old, new in mutations:
            assert source.count(old) == 1, (label, 'mutation was not applied')
            bank.write_text(source.replace(old, new))
            result = subprocess.run([args.lua, '-'], input=fixture.replace('@SCENARIO@', SCENARIOS[label]),
                                    text=True, capture_output=True, timeout=20, check=False)
            assert result.returncode != 0 and 'delayed bank reply' in result.stderr, (label, result.stdout + result.stderr)
            print('Bank window mutation rejected:', label)
        bank.write_text(source)


if __name__ == '__main__':
    main()
