"""Run MultiBot character-info replies through the real UI and bridge dispatcher."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from FixtureSupport import multibot_sources


FILES = ('Core/MultiBotComm.lua', 'UI/MultiBotCharacterInfoFrame.lua')
FIXTURE = r'''
MultiBot = {L = function(key, fallback) return fallback or key end,
            TimerAfter = function() end, SafeTexturePath = function(path) return path end}
GetTime = function() return 10 end
UnitName = function() return "Owner" end
local function noop() end
local function widget()
    local w = {shown = true, scripts = {}}
    for _, method in ipairs({"SetPoint", "ClearAllPoints", "SetSize", "SetWidth", "SetHeight",
        "SetFrameStrata", "SetClampedToScreen", "SetBackdrop", "SetBackdropColor", "SetBackdropBorderColor",
        "SetJustifyH", "SetID", "SetScrollChild", "SetVerticalScroll", "RegisterEvent",
        "LockHighlight", "UnlockHighlight", "SetTextColor", "SetAllPoints", "SetTexture",
        "SetMinMaxValues", "SetValue", "SetStatusBarColor", "SetStatusBarTexture"}) do
        w[method] = noop
    end
    function w:SetText(value) self.text = value end
    function w:SetScript(key, callback) self.scripts[key] = callback end
    function w:HookScript(key, callback) self.scripts[key] = callback end
    function w:Show() self.shown = true end
    function w:Hide() self.shown = false end
    function w:IsShown() return self.shown end
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
    return window
end
LibStub = function(name) assert(name == "AceGUI-3.0") return aceGUI end
@SOURCES@
MultiBot.bridge.connected = true
MultiBot.Comm.Send = function() return true end
local function open(bot)
    assert(MultiBot.OpenCharacterInfo(bot))
    local state = MultiBot.bridge
    return {skills = state.botSkillActive.token, reputations = state.botReputationActive.token,
            emblems = state.botEmblemActive.token}
end
local function reply(kind, bot, token)
    local prefix = ({skills = "BOT_SKILLS", reputations = "BOT_REPUTATIONS", emblems = "BOT_EMBLEMS"})[kind]
    local function deliver(opcode, tail)
        assert(MultiBot.Comm.HandleAddonMessage("MBOT", opcode .. "~" .. bot .. "~" .. token
                                               .. (tail or ""), "WHISPER", "Owner"))
    end
    deliver(prefix .. "_BEGIN")
    if kind == "skills" then deliver("BOT_SKILLS_ITEM", "~class~43~swords~Swords~1~5") end
    if kind == "emblems" then deliver("BOT_EMBLEMS_MONEY", "~12345") end
    deliver(prefix .. "_END")
end
@SCENARIO@
'''

SCENARIOS = {
    'current window': r'''
local tokens = open("BotA")
for kind, token in pairs(tokens) do
    reply(kind, "BotA", token)
    assert(MultiBot.characterInfoFrame:IsShown(), "current character window was hidden")
    assert(MultiBot.characterInfoFrame.botName == "BotA")
end
assert(#MultiBot.characterInfoFrame.skills == 1, "current skill reply was discarded")
assert(MultiBot.characterInfoFrame.emblemMoney == 12345, "current money reply was discarded")
''',
    'normalized bot name': r'''
local tokens = open("BotA")
for kind, token in pairs(tokens) do reply(kind, "bota", token) end
assert(#MultiBot.characterInfoFrame.skills == 1, "matching character reply was discarded")
assert(MultiBot.characterInfoFrame.emblemMoney == 12345)
''',
    'closed window': r'''
local tokens = open("BotA")
local frame = MultiBot.characterInfoFrame
frame:Hide()
for kind, token in pairs(tokens) do
    reply(kind, "BotA", token)
    assert(not frame:IsShown(), "delayed character reply reopened a closed window: " .. kind)
end
''',
    'switched bot': r'''
local tokens = open("BotA")
-- Failed requests for the newly selected bot leave the old requests in flight.
MultiBot.bridge.connected = false
assert(not MultiBot.OpenCharacterInfo("BotB"))
for kind, token in pairs(tokens) do
    reply(kind, "BotA", token)
    assert(MultiBot.characterInfoFrame.botName == "BotB", "delayed character reply changed the selected bot: " .. kind)
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
    with tempfile.TemporaryDirectory(prefix='multibot-character-') as temporary:
        directory = Path(temporary)
        multibot_sources(directory, FILES, args.addon_source)
        sources = '\n'.join('dofile(' + json.dumps(str(directory / file)) + ')' for file in FILES)
        fixture = FIXTURE.replace('@SOURCES@', sources)

        def run(label):
            return subprocess.run([args.lua, '-'], input=fixture.replace('@SCENARIO@', SCENARIOS[label]),
                                  text=True, capture_output=True, timeout=20, check=False)

        for label in SCENARIOS:
            result = run(label)
            assert result.returncode == 0, (label, result.stdout + result.stderr)
            print('Character window passed:', label)

        ui = directory / FILES[1]
        source = ui.read_text()
        for label, old, new in (
            ('closed window', 'return frame and frame:IsShown()\n        and string.lower', 'return frame\n        and string.lower'),
            ('switched bot', 'string.lower(frame.botName or "") == string.lower(botName or "")', 'true'),
        ):
            assert source.count(old) == 1, (label, 'mutation was not applied')
            ui.write_text(source.replace(old, new))
            result = run(label)
            assert result.returncode != 0 and 'delayed character reply' in result.stderr, (label, result.stdout + result.stderr)
            print('Character window mutation rejected:', label)
        ui.write_text(source)


if __name__ == '__main__':
    main()
