"""Run EraTalents against DragonUI's pinned talent window entry points.

DragonUI's talent module replaces the talent micro-button, the talent key
bindings, the PlayerTalentFrame redirect and the inspect talent tab. Its real
entry, show/hide, inspect and tab code runs here with the real EraTalents
client files, so an era character can never be left on DragonUI's native
WotLK tree while native characters, pets and glyphs keep DragonUI.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from FixtureSupport import fork_change, git_apply, prepared_core, run_fixture, unpatched


ROOT = Path(__file__).resolve().parents[2]
ERA_PATCH = fork_change('mod-era-talents', 'mod-era-talents-dragonui')
DRAGONUI = ROOT / '.module-cache/prepared-source-addons/DragonUI'


def section(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin:text.index(end, begin)]


def dragon_chunks(source: Path) -> dict[str, str]:
    talents = source / 'modules/talents'
    shell = (talents / 'window_shell.lua').read_text()
    header = 'local addon = select(2, ...)\nlocal TM = addon.TalentModule\nlocal ns = TM.ns\n'
    window = header + section(shell, 'function ns.SetTitle(text)', '-- Ambient clouds and dust') \
        + section(shell, 'function ns.SetGlyphPage(on)', '-- Show and hide') \
        + section(shell, 'local function onShow()', 'local function onDragStart(win)') + 'return onShow, onHide\n'
    inspect = header + section((talents / 'live_view.lua').read_text(), 'function ns.ShowInspect(unit)',
                               '-- Live repaint triggers')
    # The tab strip from its tab helpers through RefreshTabs, so the glyph tab is DragonUI's own.
    tabs = header + 'local L = addon.L\n' + section((talents / 'tab_strip.lua').read_text(), 'local TAB_PREFIX',
                                                     '-- Spec rename cog') + 'return tabClicked\n'
    return {'window': window, 'inspect': inspect, 'tabs': tabs,
            'namespace': str(talents / 'namespace.lua'), 'entry': str(talents / 'entry_points.lua')}


LUA_FIXTURE = r'''
local addonDir, chunks, moduleEnabled = ...
GetLocale=function() return "deDE" end
local events={}
local methods={}
local function Object(name,parent) return setmetatable({name=name,parent=parent,scripts={},hooks={},shown=false},{__index=methods}) end
for _,name in ipairs({"SetFrameStrata","SetPoint","EnableMouse","SetMovable","RegisterForDrag","SetAllPoints","SetFrameLevel",
  "SetTexture","SetTexCoord","SetTextColor","SetAlpha","EnableMouseWheel","SetScrollChild","SetDesaturated","ClearAllPoints",
  "SetSize","SetVertexColor","SetBackdrop","SetBackdropColor","SetBackdropBorderColor","SetJustifyH","SetJustifyV","SetFont",
  "SetFontObject","SetToplevel","SetClampedToScreen","SetHighlightTexture","SetPushedTexture","SetDisabledTexture","SetBlendMode",
  "SetDrawLayer","SetScale","RegisterForClicks","SetHitRectInsets","SetButtonState","UnregisterEvent","SetID","Enable","Disable",
  "SetChecked","SetMinMaxValues","SetValue","SetStatusBarTexture","SetStatusBarColor","SetParent","SetVerticalScroll","Raise","SetNormalFontObject","SetHighlightFontObject","SetDisabledFontObject"}) do
  methods[name]=function(self,...) self[name.."Args"]={...} end
end
function methods:RegisterEvent(event) events[event]=events[event] or {}; table.insert(events[event],self) end
function methods:GetName() return self.name end
function methods:SetFrameStrata(strata) self.strata = strata end
function methods:GetFrameStrata() return self.strata or "MEDIUM" end
function methods:GetParent() return self.parent end
function methods:GetFrameLevel() return 0 end
function methods:GetWidth() return self.width or 100 end
function methods:GetHeight() return self.height or 100 end
function methods:SetWidth(n) self.width=n end
function methods:SetHeight(n) self.height=n end
function methods:SetText(s) self.text=s end
function methods:GetText() return self.text end
function methods:GetStringWidth() return 10 end
function methods:SetScript(name,fn) self.scripts[name]=fn end
function methods:GetScript(name) return self.scripts[name] end
function methods:HookScript(name,fn) self.hooks[name]=self.hooks[name] or {}; table.insert(self.hooks[name],fn) end
function methods:IsShown() return self.shown end
function methods:IsVisible() return self.shown end
function methods:GetID() return self.id or 0 end
function methods:SetID(id) self.id=id end
function methods:SetShownCompat(show) if show then self:Show() else self:Hide() end end
-- Native order: a frame's own script runs before the post-hooks added by HookScript.
function methods:Hide()
  if not self.shown then return end
  self.shown=false
  if self.scripts.OnHide then self.scripts.OnHide(self) end
  for _,fn in ipairs(self.hooks.OnHide or {}) do fn(self) end
end
function methods:Show()
  if self.shown then return end
  self.shown=true
  if self.scripts.OnShow then self.scripts.OnShow(self) end
  for _,fn in ipairs(self.hooks.OnShow or {}) do fn(self) end
end
function methods:Click(button) if self.scripts.OnClick then self.scripts.OnClick(self,button or "LeftButton") end end
function methods:CreateTexture() return Object() end
function methods:CreateFontString() return Object() end
function methods:SetNormalTexture() self.normal=Object() end
function methods:GetNormalTexture() return self.normal end
function methods:GetHighlightTexture() return Object() end
CreateFrame=function(_,name,parent) local o=Object(name,parent); if name then _G[name]=o end; return o end
local function fire(event,...)
  for _,frame in ipairs(events[event] or {}) do if frame.scripts.OnEvent then frame.scripts.OnEvent(frame,event,...) end end
end
-- hooksecurefunc's native contract: the original runs first, its results are returned, then the hook.
hooksecurefunc=function(a,b,c)
  local owner,name,hook=_G,a,b
  if type(a)=="table" then owner,name,hook=a,b,c end
  local original=owner[name]
  assert(type(original)=="function","hooksecurefunc needs an existing function: "..tostring(name))
  owner[name]=function(...) local r={original(...)}; hook(...); return unpack(r) end
end
wipe=function(t) for key in pairs(t) do t[key]=nil end; return t end
tinsert=table.insert
min,max=math.min,math.max
UIParent=Object("UIParent")
UISpecialFrames={}
SHOW_TALENT_LEVEL=10
TALENTS="Talente"
FEATURE_BECOMES_AVAILABLE_AT_LEVEL="Ab Stufe %d verfügbar."
GLYPH_TALENT_TAB=3
local notices={}
UIErrorsFrame=Object("UIErrorsFrame"); UIErrorsFrame.AddMessage=function(_,text) table.insert(notices,text) end
local warnings={}
DEFAULT_CHAT_FRAME={AddMessage=function(_,s) table.insert(warnings,s) end}
GameTooltip={SetOwner=function() end,SetText=function() end,AddLine=function() end,Show=function() end,Hide=function() end,
  SetSpell=function() end,SetAction=function() end,HookScript=function() end}
GameTooltip_Hide=function() end
local cvars={previewTalents="0"}
GetCVar=function(name) return cvars[name] end
SetCVar=function(name,value) cvars[name]=value end
PlaySound=function() end
SetButtonPulse=function() end
UpdateMicroButtons=function() end
InCombatLockdown=function() return false end
IsLoggedIn=function() return true end
ResetGroupPreviewTalentPoints=function() end
GetActiveTalentGroup=function() return 1 end
local petTalents=false
GetNumTalentGroups=function(_,pet) if pet then return petTalents and 1 or 0 end return 1 end
local playerLevel=15
local units={player="0x0000000000000001",party1="0x0000000000000002",party2="0x0000000000000003"}
UnitGUID=function(unit) return units[unit] end
UnitExists=function(unit) return units[unit]~=nil end
UnitName=function(unit) return unit=="player" and "Testi" or (unit=="party1" and "Mey" or "Godric") end
GetUnitName=function(unit) return UnitName(unit) end
UnitLevel=function(unit) return unit=="player" and playerLevel or 20 end
UnitClass=function() return "Krieger","WARRIOR" end
CanInspect=function(unit) return UnitExists(unit) end
GetTime=function() return 100 end
SetPortraitTexture=function() end
PanelTemplates_TabResize=function() end
PanelTemplates_SetNumTabs=function() end
PanelTemplates_SetTab=function() end
PanelTemplates_UpdateTabs=function() end
PanelTemplates_GetSelectedTab=function(frame) return frame.selectedTab end
local sent={}
SendAddonMessage=function(prefix,message,channel,recipient)
  assert(prefix=="ERATAL" and channel=="WHISPER" and recipient=="Testi")
  table.insert(sent,message)
end
GetSpellInfo=function(id) if id==932999 then return "EraTalents Gen a1b2c3d4" end return "Spell "..id end
IsAddOnLoaded=function() return true end
LoadAddOn=function() end
-- Stock talent and inspect frames, loaded before either addon initializes.
PlayerTalentFrame=Object("PlayerTalentFrame")
ShowUIPanel=function(frame) frame:Show() end
HideUIPanel=function(frame) frame:Hide(); if frame==InspectFrame then InspectTalentFrame:Hide() end end
TalentMicroButton=Object("TalentMicroButton")
InspectFrame=Object("InspectFrame")
InspectTalentFrame=Object("InspectTalentFrame",InspectFrame)
InspectFrameTab3=Object("InspectFrameTab3",InspectFrame)
for _,name in ipairs({"InspectTalentFrameScrollFrame","InspectTalentFramePointsBar","InspectTalentFrameTab1","InspectTalentFrameTab2","InspectTalentFrameTab3"}) do _G[name]=Object(name,InspectTalentFrame); _G[name]:Show() end
InspectSwitchTabs=function(tab)
  assert(tab==1 or tab==3,"the native talent inspect tab is 3")
  if tab==3 then InspectTalentFrame:Show() else InspectTalentFrame:Hide() end
end
InspectFrame_Show=function() end
InspectFrame_UnitChanged=function() end
local function inspect(unit)
  HideUIPanel(InspectFrame); InspectFrame.unit=unit
  InspectFrame:Show(); InspectSwitchTabs(1); InspectFrame_Show(unit)
end
local bindings={}
GetBindingKey=function(action) if action=="TOGGLETALENTS" then return "N" end if action=="TOGGLEINSCRIPTION" then return "K" end end
ClearOverrideBindings=function() wipe(bindings) end
SetOverrideBindingClick=function(_,_,key,button,mouse) bindings[key]={button=button,mouse=mouse} end
local function press(key) local b=assert(bindings[key],"DragonUI binds "..key); _G[b.button]:Click(b.mouse) end
SlashCmdList={}

-- DragonUI: real namespace, entry points, window show/hide, inspect and tab code.
local timers={}
local addon={L=setmetatable({},{__index=function(_,k) return k end}),_dir=""}
function addon:SafeExecute(_,_,fn,...) return fn(...) end
function addon:After(_,fn) table.insert(timers,fn) end
function addon:IsModuleEnabled(name) return name=="talents" and moduleEnabled end
DragonUI=addon
local function runTimers() local list=timers; timers={}; for _,fn in ipairs(list) do fn() end end
assert(loadfile(chunks.namespace))("DragonUI",addon)
local TM=addon.TalentModule
local ns=TM.ns
local onShow,onHide=assert(loadstring(chunks.window))("DragonUI",addon)
assert(loadstring(chunks.inspect))("DragonUI",addon)
local tabClicked=assert(loadstring(chunks.tabs))("DragonUI",addon)
local painted={}
local function paint() table.insert(painted,{inspect=ns.inspectUnit,pet=ns.PetView(),glyph=ns.GlyphView()}) end
ns.PaintLive=paint
ns.PaintGlyphs=paint
ns.ApplyScale=function() end
for _,name in ipairs({"InstallLiveEvents","InstallGlyphEvents","InstallOrbEvents","InstallSharing","PlaceCatcher"}) do ns[name]=function() end end
-- BuildWindow's art is presentation only; the window keeps DragonUI's real show and hide handlers.
ns.BuildWindow=function()
  if ns.win then return ns.win end
  local win=CreateFrame("Frame","DragonUI_TalentFrame",UIParent)
  ns.win=win
  ns.title,ns.classArt,ns.petArt,ns.glyphArt,ns.fx=Object(),Object(),Object(),Object(),Object()
  win:SetScript("OnShow",onShow)
  win:SetScript("OnHide",onHide)
  return win
end
assert(loadfile(chunks.entry))("DragonUI",addon)

-- EraTalents: the real client files in TOC order.
EraTalents=nil
for line in io.lines(addonDir.."EraTalents.toc") do
  local file=line:match("^([^#%s][^\r]*%.lua)")
  if file then dofile(addonDir..file:gsub("\\","/")) end
end
local ET=EraTalents
local warrior=EraTalentsData[0][1].talents[1].id

fire("PLAYER_LOGIN")
fire("PLAYER_ENTERING_WORLD")
assert(sent[#sent]=="HELLO")
local win=DragonUI_TalentFrame
local function panel() return ET.frame~=nil and ET.frame:IsShown() end
local function nativeOwnTree() return win~=nil and win:IsShown() and ns.inspectUnit==nil and not ns.GlyphView() and not ns.PetView() end
local function reset()
  if win then win:Hide() end
  if panel() then ET.frame:Hide() end
  HideUIPanel(InspectFrame)
  wipe(painted); wipe(notices)
end

if not moduleEnabled then
  -- A disabled talent module leaves the stock openers, which EraTalents already guards.
  assert(win==nil and next(bindings)==nil,"a disabled DragonUI talent module installs no window or bindings")
  ET.OnAddonMsg("ERATAL","SYNC 0 1 5 "..warrior..":1")
  ns.ToggleTalents(); ns.OpenTalents()
  assert(not panel(),"the disabled module's own functions stay inert")
  ShowUIPanel(PlayerTalentFrame)
  assert(panel() and not PlayerTalentFrame:IsShown(),"the stock talent frame still opens the era panel")
  print("DragonUI talent module disabled: stock EraTalents route kept")
  return
end
assert(win and TM.applied,"DragonUI applies its talent module on login")
ns.BuildTabs(win)

-- A native WotLK character keeps DragonUI's window.
ET.OnAddonMsg("ERATAL","SYNC 2 0 0")
ET.OnAddonMsg("ERATAL","GEN a1b2c3d4")
press("N")
assert(nativeOwnTree() and not panel(),"native characters keep DragonUI's talent window")
reset()

-- An era character's own tree opens in the era panel from every DragonUI opener.
ET.OnAddonMsg("ERATAL","SYNC 0 1 5 "..warrior..":1")
assert(ET.state.isEraChar)
press("N")
assert(panel() and not nativeOwnTree(),"the talent key opens the era tree, not DragonUI's native tree")
press("N")
assert(not panel() and not nativeOwnTree(),"the talent key toggles the era panel closed")
TalentMicroButton:Click()
assert(panel() and not nativeOwnTree(),"the micro-button opens the era tree")
TalentMicroButton:Click()
assert(not panel(),"the micro-button toggles the era panel closed")
SlashCmdList.DRAGONUI_TALENTS("")
assert(panel() and not nativeOwnTree(),"/talents opens the era tree")
reset()
ShowUIPanel(PlayerTalentFrame); runTimers()
assert(panel() and not PlayerTalentFrame:IsShown() and not nativeOwnTree(),"the stock talent frame opens the era tree")
reset()
win:Show()
assert(panel() and not nativeOwnTree(),"any other show of DragonUI's player tree opens the era tree")
reset()

-- Glyphs stay in DragonUI; switching that open window to a player spec tab opens the era tree.
press("K")
assert(win:IsShown() and ns.GlyphView() and not panel(),"the glyph page stays in DragonUI")
tabClicked({GetID=function() return 1 end})
assert(panel() and not nativeOwnTree(),"a spec tab of an open DragonUI window opens the era tree")
reset()

-- Before earned Wrath the server's glyph gate closes the glyph page and hides its tab.
local gate=ET.L["Glyphs become available once this character has earned Wrath of the Lich King."]
ET.OnAddonMsg("ERATAL","GLYPHS 0")
assert(ET.state.glyphsAllowed==false)
press("K")
assert(not win:IsShown() and not panel() and not ns.GlyphView() and notices[#notices]==gate,
  "the glyph key explains the gate before Wrath and opens nothing")
fire("USE_GLYPH")
assert(not win:IsShown() and not panel() and #notices==2,"using a glyph explains the gate before Wrath")
tabClicked({GetID=function() return 4 end})
assert(not ns.GlyphView() and #notices==3,"the glyph tab cannot open the page before Wrath")
ns.RefreshTabs()
assert(DragonUI_TalentFrameTab1:IsShown() and not DragonUI_TalentFrameTab4:IsShown(),"the glyph tab is hidden before Wrath")
reset()
ET.OnAddonMsg("ERATAL","GLYPHS 1")
ns.RefreshTabs()
assert(DragonUI_TalentFrameTab4:IsShown(),"the glyph tab returns with earned Wrath")
press("K")
assert(win:IsShown() and ns.GlyphView() and #notices==0,"the glyph page opens with earned Wrath")
reset()

-- The pet tree stays in DragonUI: /pettalents opens DragonUI's pet view instead of the stock frame.
local chatLines=#warnings
ET.OpenStockTalents()
assert(not win:IsShown() and #warnings==chatLines+1,"without a pet the era addon's notice remains")
units.pet="0x0000000000000009"; petTalents=true
ET.OpenStockTalents(); runTimers()
assert(win:IsShown() and ns.PetView() and not panel() and painted[#painted].pet,"/pettalents opens DragonUI's pet tree")
tabClicked({GetID=function() return 1 end})
assert(panel() and not nativeOwnTree(),"leaving the pet tree for the player's spec opens the era tree")
reset()
petTalents=false
ET.OpenStockTalents()
assert(panel() and not nativeOwnTree(),"a pet without talents leaves the player tree to the era panel")
reset()
units.pet=nil

-- Below the talent level DragonUI's notice stays and nothing opens.
playerLevel=9
press("N")
assert(not panel() and not win:IsShown() and notices[1]==FEATURE_BECOMES_AVAILABLE_AT_LEVEL:format(10),"below level 10 the talent window stays closed")
playerLevel=15
reset()

-- Inspect: era-managed or still unknown targets use the stock tab under EraTalents' overlay.
local function suppressed() return not InspectTalentFrameScrollFrame:IsShown() end
inspect("party1")
assert(sent[#sent]=="INSPECT "..units.party1)
InspectFrameTab3:Click()
assert(InspectTalentFrame:IsShown() and not win:IsShown() and ns.inspectUnit==nil,"an unanswered inspect waits in the stock tab")
assert(suppressed() and ET.inspectStatus:IsShown(),"the native tree stays hidden until ISYNC decides")
ET.OnAddonMsg("ERATAL","ISYNC "..units.party1.." 0 1 1 "..warrior..":1")
assert(ET.inspectView.frame:IsShown() and ET.inspectView.readOnly,"the era tree of an inspected era character is shown read-only")
assert(ET.inspectView.frame.strata=="HIGH" and ET.inspectView.frame.parent==UIParent,"the era tree sits above the Inspect frame with DragonUI")
InspectFrame_UnitChanged()
assert(not win:IsShown(),"a target change keeps an era inspect in the stock tab")
reset()
inspect("party2")
ET.OnAddonMsg("ERATAL","ISYNC "..units.party2.." 0 0 0")
InspectFrameTab3:Click()
assert(win:IsShown() and ns.inspectUnit=="party2" and painted[#painted].inspect=="party2" and not InspectTalentFrame:IsShown(),
  "a native inspect target keeps DragonUI's inspect window")
reset()
ET.state.serverGen=nil
inspect("party1")
InspectFrameTab3:Click()
assert(win:IsShown() and ns.inspectUnit=="party1","a realm without EraTalents keeps DragonUI's inspect window")
reset()
print("DragonUI talents: era panel, glyph gate, pet tree, level gate and era/native inspect passed")
'''


def run(era_addon: Path, chunks: dict[str, str], directory: Path, *, enabled: bool,
        expect_failure: bool = False) -> None:
    lua = shutil.which('lua5.1') or shutil.which('lua')
    if not lua:
        raise RuntimeError('Lua 5.1 is required')
    script = directory / ('dragonui-' + ('enabled' if enabled else 'disabled') + '.lua')
    table = '{' + ','.join(f'{key}={json.dumps(value)}' for key, value in chunks.items()) + '}'
    script.write_text('local function fixture(...)\n' + LUA_FIXTURE + '\nend\nfixture('
                      + json.dumps(str(era_addon) + '/') + ',' + table + ',' + ('true' if enabled else 'false') + ')\n')
    result = run_fixture([lua, str(script)])
    if expect_failure:
        if result.returncode == 0:
            raise AssertionError('Reverted production behavior unexpectedly passed')
        # Only an assertion of the fixture itself counts, not a broken production file.
        if not re.search(r'dragonui-(?:enabled|disabled)\.lua:\d+: ', result.stderr):
            raise AssertionError('Mutation failed for an unrelated fixture error: ' + result.stderr)
        return
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    print(result.stdout.strip())


def main() -> None:
    if not (DRAGONUI / 'DragonUI.toc').is_file():
        raise RuntimeError('Run cmake -P cmake/PrepareModules.cmake to prepare the pinned DragonUI source')
    chunks = dragon_chunks(DRAGONUI)
    entry = Path(chunks['entry']).read_text()
    # The openers EraTalents wraps are looked up on the shared table at call time.
    for opener in ('TalentMicroButton:SetScript("OnClick", function() ns.ToggleTalents() end)',
                   'ns.ShowInspect(InspectFrame.unit)', 'ns.OpenTalents()', 'ns.ToggleTalents()'):
        if opener not in entry:
            raise AssertionError('DragonUI talent opener changed: ' + opener)
    with tempfile.TemporaryDirectory(prefix='dragonui-era-talents-') as temporary:
        directory = Path(temporary)
        era = directory / 'era'
        shutil.copytree(prepared_core(ROOT) / 'modules/mod-era-talents/client-addon', era / 'client-addon')
        subprocess.run(['git', 'init', '-q', str(era)], check=True)
        unpatched(era, ERA_PATCH)
        git_apply(era, ERA_PATCH)
        addon = era / 'client-addon/EraTalents'
        for enabled in (True, False):
            run(addon, chunks, directory, enabled=enabled)
        compat = addon / 'DragonUI.lua'
        safe = compat.read_text()
        for before, after in (
                ('if not (module.applied and ET.state.isEraChar and TalentLevel()) then return toggle(...) end',
                 'if true then return toggle(...) end'),
                ('and TalentLevel()) then return toggle(...) end', ') then return toggle(...) end'),
                ('win:HookScript("OnShow", function() settled = not Redirect(ns) end)',
                 'win:HookScript("OnShow", function() settled = true end)'),
                ('hooksecurefunc(ns, "Repaint", function() if settled then Redirect(ns) end end)', ''),
                ('if not (ET.state and ET.state.isEraChar) or not OwnTreeShown(ns) then return false end',
                 'if not OwnTreeShown(ns) then return false end'),
                ('if not (module.applied and UsesEraInspect(unit)) then return showInspect(unit, ...) end',
                 'do return showInspect(unit, ...) end'),
                ('  if e then return e.managed end\n', ''),
                ('return ET.state ~= nil and ET.state.serverGen ~= nil', 'return true'),
                ('if not (module.applied and ns.win and UnitExists("pet")) then return openStock(...) end',
                 'do return openStock(...) end'),
                ('and not ns.GlyphView() and not ns.PetView()', '')):
            if before not in safe:
                raise AssertionError('Expected production DragonUI guard: ' + before)
            compat.write_text(safe.replace(before, after, 1))
            run(addon, chunks, directory, enabled=True, expect_failure=True)
        compat.write_text(safe)
        for relative, before, after in (
                ('DragonUIGlyphs.lua', '      if Blocked() then return Refuse() end\n', ''),
                ('DragonUIGlyphs.lua', 'if on and Blocked() then', 'if false then'),
                ('DragonUIGlyphs.lua', 'if glyphTab and Blocked() then glyphTab:Hide() end', ''),
                ('DragonUIGlyphs.lua', 'ET.state.glyphsAllowed == false', 'ET.state.glyphsAllowed ~= true'),
                ('Comms.lua', 'ET.state.glyphsAllowed = glyphs == "1"', 'ET.state.glyphsAllowed = true'),
                ('EraTalents.lua', '  if ET.InitDragonUIGlyphs then ET.InitDragonUIGlyphs() end\n', '')):
            path = addon / relative
            original = path.read_text()
            if before not in original:
                raise AssertionError('Expected production glyph gate: ' + before)
            path.write_text(original.replace(before, after, 1))
            run(addon, chunks, directory, enabled=True, expect_failure=True)
            path.write_text(original)
        init = addon / 'EraTalents.lua'
        wired = init.read_text()
        call = '  if ET.InitDragonUI then ET.InitDragonUI() end\n'
        if call not in wired:
            raise AssertionError('Expected the DragonUI initialization call')
        init.write_text(wired.replace(call, '', 1))
        run(addon, chunks, directory, enabled=True, expect_failure=True)
        init.write_text(wired)
        git_apply(era, ERA_PATCH, '--reverse')
        run(addon, chunks, directory, enabled=True, expect_failure=True)
        print('Reverted EraTalents DragonUI integration and each guard mutation fail the fixture')


if __name__ == '__main__':
    main()
