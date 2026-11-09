"""Exercise DragonUI's dressing-room skin against stock and replaced frames."""

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

from FixtureSupport import REPOSITORY


LUA_FIXTURE = r'''
assert(_VERSION == "Lua 5.1")
local source = assert(arg[1], "source path")
local function scenario(width, height, enabled, loggedIn)
    local env = setmetatable({}, { __index = _G })
    env._G = env
    local frames, skins, errors = {}, 0, {}
    local function frame(w, h)
        return {
            GetWidth = function() return w end,
            GetHeight = function() return h end,
            GetRegions = function() end,
            RegisterEvent = function(self, event) self.event = event end,
            SetScript = function(self, kind, fn) self[kind] = fn end,
            HookScript = function(self, kind, fn) self[kind] = fn end,
        }
    end
    env.DressUpFrame = frame(width, height)
    env.CreateFrame = function(kind)
        assert(kind == "Frame")
        local value = frame(0, 0)
        frames[#frames + 1] = value
        return value
    end
    env.IsLoggedIn = function() return loggedIn end
    env.UnitRace = function() return "Human", "HUMAN" end
    env.UnitSex = function() return 2 end
    local cp = {
        BuildWindowChrome = function() skins = skins + 1; return frame(0, 0) end,
        FitWindowPortrait = function() end,
        ModernizeCloseButton = function() end,
        DrawPaneBorder = function() end,
        TintWindowChrome = function() end,
    }
    local addon = {
        _dir = "Interface\\AddOns\\DragonUI\\",
        CharacterPanel = cp,
        L = setmetatable({}, { __index = function(_, key) return key end }),
        IsModuleEnabled = function(_, name) assert(name == "dressupframe"); return enabled end,
        GetModuleConfig = function() return {} end,
        RegisterModule = function() end,
        WireModelDragRotate = function() end,
        Error = function(_, message) errors[#errors + 1] = message end,
    }
    setfenv(assert(loadfile(source)), env)("DragonUI", addon)
    local boot = assert(frames[1])
    assert(boot.event == "PLAYER_LOGIN")
    return {
        frame = env.DressUpFrame,
        apply = function() addon.ApplyDressUpFrameSystem() end,
        login = function() loggedIn = true; boot.OnEvent(boot, "PLAYER_LOGIN") end,
        skins = function() assert(#errors == 0, table.concat(errors, "\n")); return skins end,
    }
end
local early = scenario(384, 512, true, false)
early.apply()
assert(early.skins() == 0 and not early.frame._duiSkinned, "defer skin until all addons have loaded")
early.frame.GetWidth = function() return 450 end
early.frame.GetHeight = function() return 545 end
early.login()
assert(early.skins() == 0 and not early.frame._duiSkinned, "leave a later addon's replaced dressing room alone")
for _, dimensions in ipairs({{450, 545}, {384, 545}, {450, 512}}) do
    local replaced = scenario(dimensions[1], dimensions[2], true, true)
    replaced.apply()
    assert(replaced.skins() == 0 and not replaced.frame._duiSkinned, "skip non-stock dressing rooms")
end
local stock = scenario(384, 512, true, false)
stock.apply()
stock.login()
assert(stock.skins() == 1 and stock.frame._duiSkinned, "skin the stock frame at login")
stock.apply()
stock.login()
assert(stock.skins() == 1, "do not stack the skin on repeated lifecycle calls")
local enabledLater = scenario(384, 512, true, true)
enabledLater.apply()
assert(enabledLater.skins() == 1, "apply live after login")
local disabled = scenario(384, 512, false, false)
disabled.apply()
disabled.login()
assert(disabled.skins() == 0 and not disabled.frame._duiSkinned, "respect module disable")
print("DragonUI dressing room: stock/live/disabled lifecycle and replacement guards passed")
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dragon-source', type=Path,
                        default=REPOSITORY / '.module-cache/prepared-source-addons/DragonUI')
    parser.add_argument('--lua', default=shutil.which('lua5.1') or shutil.which('lua'))
    args = parser.parse_args()
    if not args.lua:
        parser.error('Lua 5.1 is required')
    production = (args.dragon_source / 'modules/dressupframe.lua').read_text()
    with tempfile.TemporaryDirectory(prefix='dragonui-dressing-room-') as temporary:
        directory = Path(temporary)
        fixture, source = directory / 'fixture.lua', directory / 'dressupframe.lua'
        fixture.write_text(LUA_FIXTURE)

        def run(text):
            source.write_text(text)
            return subprocess.run([args.lua, str(fixture), str(source)],
                                  check=False, capture_output=True, text=True, timeout=20)

        result = run(production)
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout.strip(), flush=True)
        for before, after, expected in (
                (' or not isStockFrame(frame)', '',
                 "leave a later addon's replaced dressing room alone"),
                ('if IsLoggedIn() then safeBuild() end', 'safeBuild()',
                 'defer skin until all addons have loaded'),
                ('if addon:IsModuleEnabled("dressupframe") then safeBuild() end', 'safeBuild()',
                 'respect module disable'),
                (' or frame._duiSkinned', '',
                 'do not stack the skin on repeated lifecycle calls')):
            assert before in production, before
            result = run(production.replace(before, after, 1))
            assert result.returncode != 0 and expected in result.stderr, result.stdout + result.stderr
        print('Removing replacement, login, module-enable and duplicate-skin guards fails the fixture', flush=True)


if __name__ == '__main__':
    main()
