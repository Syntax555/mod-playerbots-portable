"""Exercise DragonUI's real talent canvas with authoritative EraTalents data.

The fixture loads the real window entry points, live renderer, node canvas,
footer, tabs, EraTalents client and MultiBot talent opener. Frame doubles retain
layout and visibility; no realm or graphical client is required.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from FixtureSupport import fork_change, git_apply, prepared_core, run_fixture, unpatched


ROOT = Path(__file__).resolve().parents[2]


def section(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin:text.index(end, begin)]


def dragon_chunks(source: Path, multibot: Path) -> dict[str, str]:
    talents = source / 'modules/talents'
    shell = (talents / 'window_shell.lua').read_text()
    header = 'local addon = select(2, ...)\nlocal TM = addon.TalentModule\nlocal ns = TM.ns\n'
    window = header + 'local max, min = math.max, math.min\n' \
        + section(shell, '-- Background art', '-- Portrait and title') \
        + section(shell, 'function ns.SetTitle(text)', '-- Ambient clouds and dust') \
        + section(shell, 'function ns.SetDepth(depth)', '-- Show and hide') \
        + section(shell, 'local function onShow()', 'local function onDragStart(win)') + 'return onShow, onHide, newPair\n'
    tabs = header + 'local L = addon.L\n' + section((talents / 'tab_strip.lua').read_text(), 'local TAB_PREFIX',
                                                     '-- Spec rename cog') + 'return tabClicked\n'
    bot_source = (multibot / 'UI/MultiBotTalentFrame.lua').read_text()
    bot = bot_source[:bot_source.index('local function getTalentFrameAceGUI(')]
    every = (multibot / 'Core/MultiBotEvery.lua').read_text()
    button_start = every.index('pFrame.addButton("Talent", 304')
    button = every[button_start:every.index('\n\t--', button_start)]
    return {'window': window, 'atlas': str(source / 'utils/atlas.lua'), 'tabs': tabs, 'bot': bot, 'bot_button': button,
            **{name: str(talents / filename) for name, filename in (
                ('namespace', 'namespace.lua'), ('entry', 'entry_points.lua'),
                ('live', 'live_view.lua'), ('canvas', 'tree_canvas.lua'), ('footer', 'footer_bar.lua'),
                ('editor', 'build_editor.lua'))}}


LUA_FIXTURE = r'''
local addonDir, chunks, moduleEnabled = ...
local objects={}
local ownClass="WARRIOR"
local canInspect=true
local now=100
GetLocale=function() return "deDE" end
local events={}
local methods={}
local function Object(name,parent)
  local o=setmetatable({name=name,parent=parent,scripts={},hooks={},shown=false},{__index=methods})
  objects[#objects+1]=o; return o
end
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
local tooltipLines={}
GameTooltip={SetOwner=function(self,o) self.owner=o; wipe(tooltipLines) end,
  GetOwner=function(self) return self.owner end, IsOwned=function(self,o) return self.owner==o end,
  SetText=function(_,s) tooltipLines[#tooltipLines+1]=s end,
  AddLine=function(_,s) tooltipLines[#tooltipLines+1]=s end,
  SetHyperlink=function(_,s) tooltipLines[#tooltipLines+1]=s end,
  Show=function() end,Hide=function(self) self.owner=nil end,SetTalent=function() error("native tooltip used for historical node") end,
  SetSpell=function() end,SetAction=function() end,HookScript=function() end}
GameTooltip_Hide=function() end
local cvars={previewTalents="0"}
GetCVar=function(name) return cvars[name] end
SetCVar=function(name,value) cvars[name]=value end
PlaySound=function() end
SetButtonPulse=function() end
UpdateMicroButtons=function()
  if TalentMicroButton then
    TalentMicroButton:SetButtonState(PlayerTalentFrame and PlayerTalentFrame:IsShown() and "PUSHED" or "NORMAL")
  end
end
InCombatLockdown=function() return false end
IsLoggedIn=function() return true end
ResetGroupPreviewTalentPoints=function() end
GetActiveTalentGroup=function() return 1 end
local petTalents=false
GetNumTalentGroups=function(_,pet) if pet then return petTalents and 1 or 0 end return 1 end
local playerLevel=15
local units={player="0x0000000000000001",party1="0x0000000000000002",party2="0x0000000000000003",party3="0x0000000000000004"}
UnitGUID=function(unit) return units[unit] end
UnitExists=function(unit) return units[unit]~=nil end
UnitName=function(unit) return ({player="Testi",party1="Mey",party2="Godric",party3="Visitor"})[unit] end
GetUnitName=function(unit) return UnitName(unit) end
UnitLevel=function(unit) return unit=="player" and playerLevel or 20 end
UnitClass=function(unit) return "Class",unit=="player" and ownClass or "WARRIOR" end
CanInspect=function(unit) return canInspect and UnitExists(unit) end
CheckInteractDistance=function() return true end
GetTime=function() return now end
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


InspectUnit=inspect
StaticPopupDialogs={}
GetCVarBool=function(name) return GetCVar(name)=="1" end
GetNumTalentTabs=function(_,pet) return pet and 1 or 3 end
GetNumTalents=function() return 1 end
local nativeRank,nativeMaxRank,nativePoints,nativeSpent,nativeTier=0,1,4,0,11
GetTalentInfo=function(tab,index,inspect,pet)
  local rank=tab==1 and nativeRank or 0
  return "Native talent","native-icon",pet and 6 or nativeTier,2,rank,nativeMaxRank,false,true,rank,true
end
GetTalentTabInfo=function(tab,_,pet) return "Native "..tab,nil,tab==1 and nativeSpent or 0,pet and "HunterPetFerocity" or "NativeBackground",0 end
GetTalentPrereqs=function() end
GetUnspentTalentPoints=function() return nativePoints end
GetGroupPreviewTalentPointsSpent=function() return 0 end
local nativeLearns=0
LearnPreviewTalents=function() nativeLearns=nativeLearns+1 end
AddPreviewTalentPoints=function() error("native preview used for historical node") end
IsModifiedClick=function() return false end
SetPortraitToTexture=function() end
DrawRouteLine=function() end
STANDARD_TEXT_FONT="font"
TALENT_SPEC_PRIMARY="Primary"; TALENT_SPEC_SECONDARY="Secondary"; PET="Pet"; GLYPHS="Glyphs"
local nativeResets=0
ResetGroupPreviewTalentPoints=function() nativeResets=nativeResets+1 end
for _,name in ipairs({"SetAtlasTexture","SetShadowOffset","SetAutoFocus","SetTextInsets","SetOrder","SetDuration",
  "SetChange","SetSmoothing","SetLooping","Stop","ClearFocus","HighlightText","SetFocus","SetValueStep"}) do
  methods[name]=function(self,...) self[name.."Args"]={...} end
end
function methods:SetScale(n) self.scale=n end
function methods:GetScale() return self.scale or 1 end
function methods:GetEffectiveScale() return self:GetScale() end
function methods:GetLeft() return 100 end
function methods:GetTop() return 700 end
function methods:GetTextWidth() return 40 end
function methods:CreateAnimationGroup() return Object() end
function methods:CreateAnimation() return Object() end
function methods:IsPlaying() return self.playing end
function methods:Play() self.playing=true end
function methods:Enable() self.enabled=true end
function methods:Disable() self.enabled=false end
function methods:SetPoint(...) self.point={...} end
function methods:SetSize(w,h) self.width=w; self.height=h end
function methods:SetAlpha(a) self.alpha=a end

local timers={}
local addon={L=setmetatable({},{__index=function(_,k) return k end}),_dir=""}
function addon:SafeExecute(_,_,fn,...) return fn(...) end
function addon:After(_,fn) timers[#timers+1]=fn end
function addon:IsModuleEnabled(name) return name=="talents" and moduleEnabled end
DragonUI=addon
local function runTimers() local list=timers; timers={}; for _,fn in ipairs(list) do fn() end end
assert(loadfile(chunks.namespace))("DragonUI",addon)
assert(loadfile(chunks.atlas))("DragonUI",addon)
local TM,ns=addon.TalentModule,addon.TalentModule.ns
local onShow,onHide,newPair=assert(loadstring(chunks.window))("DragonUI",addon)
for _,key in ipairs({"live","canvas","footer","editor"}) do assert(loadfile(chunks[key]))("DragonUI",addon) end
local tabClicked=assert(loadstring(chunks.tabs))("DragonUI",addon)
hooksecurefunc(ns,"SetClassArt",function(token,tree) ns.artClass=token; ns.artTree=tree end)
ns.SetPortraitClass=function(token) ns.portraitClass=token end
ns.SetPortraitUnit=function() end
local nativeBuildReads=0
ns.TreeData=function() nativeBuildReads=nativeBuildReads+1 end
ns.BuildBucket=function() nativeBuildReads=nativeBuildReads+1; return {} end
ns.CommittedRanks=function() return {} end
ns.ApplyScale=function() end
ns.BuildDropdown=function(parent) return CreateFrame("Button","FixtureBuildDropdown",parent) end
ns.PaintGlyphs=function() end
for _,name in ipairs({"InstallGlyphEvents","InstallOrbEvents","InstallSharing","PlaceCatcher"}) do ns[name]=function() end end
-- Frame construction is omitted; art pairs, depth, canvas, footer and tabs are production code.
ns.BuildWindow=function()
  if ns.win then return ns.win end
  local win=CreateFrame("Frame","DragonUI_TalentFrame",UIParent)
  ns.win=win
  ns.title,ns.fx=Object(),Object()
  ns.classArt,ns.petArt,ns.glyphArt=newPair(win,"BORDER"),newPair(win,"BORDER"),newPair(win,"BORDER")
  ns.BuildTrees(win,1); ns.BuildTabs(win)
  ns.BuildFooterControls(CreateFrame("Frame",nil,win))
  win:SetScript("OnShow",onShow); win:SetScript("OnHide",onHide)
  return win
end
local painted
hooksecurefunc(ns,"PaintTrees",function(view) painted=view end)
assert(loadfile(chunks.entry))("DragonUI",addon)
EraTalents=nil
for line in io.lines(addonDir.."EraTalents.toc") do
  local file=line:match("^([^#%s][^\r]*%.lua)")
  if file then dofile(addonDir..file:gsub("\\","/")) end
end
local ET=EraTalents
local talentButtons, unitFrames = {}, {}
MultiBot={auto={},index={actives={}},talent=Object(),L=function(key) return key end,
  toUnit=function(name) return name=="Mey" and "party1" or name=="Godric" and "party2" or "player" end,
  frames={MultiBar={frames={Units={frames=unitFrames,buttons={}}}}}}
MultiBot.talent.doClear=function() end
for _,name in ipairs({"Mey","Godric"}) do
  local button=Object()
  button.state=false
  button.getName=function() return name end
  button.getClass=function() return "Warrior" end
  button.setEnable=function() button.state=true; return button end
  button.setDisable=function() button.state=false; return button end
  talentButtons[name]=button
  unitFrames[name]={getButton=function(key) assert(key=="Talent"); return button end}
  assert(loadstring('local pFrame=...\n'..chunks.bot_button))({addButton=function(key)
    assert(key=="Talent"); return button
  end})
end
-- The compact SelfBot toolbar has no bot talent tool.
unitFrames.Testi={getButton=function() return nil end}
assert(loadstring(chunks.bot))()
local function clickBotTalents(name)
  local button=assert(talentButtons[name])
  button.doLeft(button)
end
fire("PLAYER_LOGIN"); fire("PLAYER_ENTERING_WORLD")
assert(sent[#sent]=="HELLO")
local win=DragonUI_TalentFrame
local function panel() return ET.frame and ET.frame:IsShown() end
local function reset()
  GameTooltip:Hide()
  if win then win:Hide() end
  if panel() then ET.frame:Hide() end
  HideUIPanel(InspectFrame)
  wipe(notices)
end
local function reply(s) ET.OnAddonMsg("ERATAL",s) end
local function nodes()
  local list={}; ns.EachNode(function(node) list[node.index]=node end); return list
end
local function nodeCount()
  local n=0; ns.EachNode(function() n=n+1 end); return n
end
local function assertArtPair(pair)
  assert(pair:IsShown() and pair[1]:IsShown() and pair[2]:IsShown(),"the native art pair shows both texture halves")
  assert(pair[2].SetTextureArgs[1]==pair[1].SetTextureArgs[1].."_r","the right texture uses the upstream split asset")
  assert(math.abs(pair[1]:GetWidth()+pair[2]:GetWidth()-ns.WIDTH)<0.001,"texture halves fill the talent window width")
  for half=1,2 do
    for _,coordinate in ipairs(pair[half].SetTexCoordArgs) do
      assert(coordinate>=0 and coordinate<=1,"each drawn half stays within the 1024-wide texture")
    end
  end
  assert(pair[1].SetTexCoordArgs[2]==1 and pair[2].SetTexCoordArgs[1]==0,"texture halves meet at the original sheet seam")
end
local warrior=EraTalentsData[0][1].talents[1].id
if not moduleEnabled then
  assert(not win and next(bindings)==nil,"disabled module installs no window or bindings")
  reply("SYNC 0 1 5 "..warrior..":1")
  ns.ToggleTalents(); ns.OpenTalents()
  assert(not panel(),"disabled DragonUI openers stay inert")
  ShowUIPanel(PlayerTalentFrame)
  assert(panel() and not PlayerTalentFrame:IsShown(),"disabled module preserves standalone Era window")
  print("Disabled DragonUI module preserves standalone talents")
  return
end
assert(win and TM.applied,"DragonUI applies on login")
reply("GEN a1b2c3d4"); reply("SYNC 2 0 0")
press("N")
assert(win:IsShown() and not panel() and not painted.external and ns.depth==11,"native Wrath keeps the native DragonUI tree")
playerLevel=11
nativeRank,nativeMaxRank,nativePoints,nativeSpent,nativeTier=2,5,0,2,1
ns.Refresh()
local nativePartialNoPoints=painted.trees[1].talents[1].state
assert(nativePartialNoPoints=="yellow","native learned partial ranks stay yellow without unspent points")
playerLevel=15; nativePoints=4; ns.Refresh()
local nativePartialLearnable=painted.trees[1].talents[1].state
assert(nativePartialLearnable=="green","native learned partial ranks turn green when another rank can be learned")
nativeRank,nativeMaxRank,nativePoints,nativeSpent,nativeTier=0,1,4,0,11
reset()
reply("SYNC 0 1 5 "..warrior..":1")
for _,open in ipairs({function() press("N") end,function() TalentMicroButton:Click() end,
  function() SlashCmdList.DRAGONUI_TALENTS("") end,function() ShowUIPanel(PlayerTalentFrame); runTimers() end,
  function() ET.TogglePanel() end,function() win:Show() end}) do
  open()
  assert(win:IsShown() and not panel() and painted.external,"every opener uses DragonUI's historical canvas")
  assert(TalentMicroButton.SetButtonStateArgs[1]=="PUSHED","own talent window presses the player microbutton")
  assert(not unitFrames.Testi.getButton("Talent") and not talentButtons.Mey.state and not talentButtons.Godric.state,
    "own talent routes leave every MultiBot talent button released")
  assert(not PlayerTalentFrame:IsShown(),"stock talent frame stays hidden")
  reset()
end
press("N"); press("N")
assert(not win:IsShown() and not panel(),"talent key closes the same window")

-- Every generated historical class tree reaches the real canvas with native grid coordinates.
local classes={[1]="WARRIOR",[2]="PALADIN",[3]="HUNTER",[4]="ROGUE",[5]="PRIEST",
  [7]="SHAMAN",[8]="MAGE",[9]="WARLOCK",[11]="DRUID"}
for era=0,1 do
  for classId,token in pairs(classes) do
    ownClass=token; ET._classId=classId
    local tree=EraTalentsData[era][classId]
    local first=tree.talents[1]
    reply("SYNC "..era.." 1 5 "..first.id..":1")
    ns.OpenTalents()
    assert(win:IsShown() and not panel() and painted.external,"historical tree remains in DragonUI")
    assert(ns.depth==(era==0 and 7 or 9),"historical tree uses its own depth")
    assert(win:GetHeight()==ns.WindowHeight(ns.depth),"window height follows historical depth")
    assert(ns.artClass==token and ns.portraitClass==token,"historical class selects matching artwork")
    assertArtPair(ns.classArt)
    assert(ns.classArt[1].SetTextureArgs[1]:find("talents-bg-"..token:lower(),1,true),"historical art uses the native class asset")
    local byId=nodes()
    assert(nodeCount()==#tree.talents,"every historical talent is rendered exactly once")
    for _,talent in ipairs(tree.talents) do
      local node=assert(byId[talent.id],"historical ID reaches real canvas")
      assert(node.tree==talent.tab and node.tier==talent.tier+1,"historical tab/tier maps to canvas")
      assert(node.talentName==ET.LocalizedField(talent,"name"),"historical localized talent name reaches canvas")
      local x,y=node.point[4]*node:GetScale(),node.point[5]*node:GetScale()
      local tier=talent.tier+1
      assert(math.abs(x-(18+64*talent.col))<0.001 and math.abs(y+(46+46*talent.tier+(tier>=ns.depth and 28 or 0)))<0.001,
        "historical column/tier uses DragonUI's real placement")
      assert(node.rank:GetText()==(talent.id==first.id and 1 or ""),"rank text follows server allocation")
    end
    assert(not DragonUI_TalentApplyButton:IsShown() and not DragonUI_TalentActivateButton:IsShown()
      and not DragonUI_TalentInspectImport:IsShown() and not FixtureBuildDropdown:IsShown(),"native purchase/profile actions are hidden")
    assert(DragonUI_TalentSearchBox:IsShown(),"historical tree keeps search")
    ns.query="this talent does not exist"; ns.ApplySearch()
    for _,node in pairs(byId) do assert(node.alpha==0.25,"real search dims nonmatching historical nodes") end
    ns.query=""; ns.ApplySearch()
    reset()
  end
end
ownClass="WARRIOR"; ET._classId=1
reply("SYNC 0 1 5 "..warrior..":1"); ns.OpenTalents()
local originalNode=assert(nodes()[warrior])
assert(originalNode.state==nativePartialLearnable,"historical learnable partial ranks match the native green state")
originalNode:Click()
assert(sent[#sent]=="LEARN "..warrior and ET.state.ranks[warrior]==1,"own learning sends LEARN without optimistic rank changes")
local beforeRight=#sent
originalNode:Click("RightButton")
assert(#sent==beforeRight,"right-click does not spend or reset talents")
reply("SYNC 0 1 4 "..warrior..":2")
assert(nodes()[warrior].rank:GetText()==2,"server SYNC repaints ranks inside the open window")
ns.NodeTooltip(nodes()[warrior])
assert(tooltipLines[1]==ET.LocalizedField(EraTalentsData[0][1].talents[1],"name"),"tooltip uses authored historical localized prose")
assert(table.concat(tooltipLines," "):find(ET.L["Next rank:"],1,true),"editable historical tooltip has next-rank prose")
GameTooltip:Hide()
local before=nativeResets
ns.ResetView(); ns.UndoLast()
assert(nativeResets==before,"historical reset/undo cannot call native APIs")
ns.EnterEditor({}); ns.LoadOntoCharacter({}); StaticPopupDialogs.DUI_TALENTS_LEARN.OnAccept()
assert(nativeBuildReads==0 and nativeLearns==0,"historical characters cannot enter native editor, load or apply builds")
local retiredNode
ns.EachNode(function(node) if node.index~=warrior then retiredNode=node end end)

local locked
for _,talent in ipairs(EraTalentsData[0][1].talents) do
  if talent.prereqTalent~=0 then locked=talent; break end
end
assert(locked,"fixture needs a real prerequisite talent")
local lockedNode=nodes()[locked.id]
local beforeClick=#sent; lockedNode:Click()
assert(#sent==beforeClick and lockedNode.state=="locked","locked prerequisites refuse talent purchases")
local parent
for _,talent in ipairs(EraTalentsData[0][1].talents) do if talent.id==locked.prereqTalent then parent=talent end end
local allocation={}
for _,talent in ipairs(EraTalentsData[0][1].talents) do
  if talent.tab==locked.tab and talent.tier<locked.tier then allocation[#allocation+1]=talent.id..":"..talent.maxRank end
end
reply("SYNC 0 1 5 "..table.concat(allocation,","))
lockedNode=nodes()[locked.id]
assert(lockedNode.state=="green","real historical prerequisites unlock talent state")
assert(lockedNode.parent.used.lines>0,"real canvas draws prerequisite connections")
lockedNode:Click()
assert(sent[#sent]=="LEARN "..locked.id,"unlocked historical prerequisite permits purchase")
reply("SYNC 0 1 4 "..warrior..":2")

-- Generation mismatch, missing data and partial replies clear real nodes rather than leaking native data.
ET.state.serverGen=nil; ET.RefreshDragonTalents()
assert(nodeCount()==0,"own historical view waits for authoritative generation")
reply("GEN deadbeef")
assert(nodeCount()==0 and painted.count==0,"generation mismatch hides all historical nodes")
reply("GEN a1b2c3d4")
assert(nodeCount()>0,"matching generation restores historical canvas")
ET._classId=6; ET.RefreshDragonTalents()
assert(nodeCount()==0,"missing historical class data cannot show native talents")
ET._classId=1
reply("SYNC 0 1 0 "..warrior..":2")
local n=#sent; nodes()[warrior]:Click()
assert(#sent==n,"zero available points cannot buy a rank")
assert(nodes()[warrior].state==nativePartialNoPoints,"historical learned partial ranks match native yellow with zero unspent points")
assert(nodes()[EraTalentsData[0][1].talents[2].id].state=="gray","empty unavailable talents stay gray")
reply("SYNC 0 1 4 "..warrior..":"..EraTalentsData[0][1].talents[1].maxRank)
n=#sent; nodes()[warrior]:Click()
assert(#sent==n,"maxed historical talent cannot buy another rank")
assert(nodes()[warrior].state=="yellow","maxed historical ranks stay yellow")
reply("SYNC 0 1 4 999999:1")
assert(nodeCount()==0,"unknown historical talent IDs cannot render or buy")
reply("SYNC 0 1 4 "..warrior..":999")
assert(nodeCount()==0,"invalid historical ranks cannot render or buy")
reply("SYNC 0 1 4 1/2 "..warrior..":1")
assert(nodeCount()==0,"partial own replies wait for all ranks")
reply("SYNC 0 1 4 2/2")
assert(nodeCount()>0,"final own rank chunk repaints historical nodes")
local completeNodes=nodeCount()
reply("SYNC 1 1 99 2/2 "..warrior..":3")
assert(ET.state.era==0 and ET.state.availPts==4 and ET.state.ranks[warrior]==1 and not ET.state.partial,
  "orphan continuation preserves the completed authoritative allocation")
assert(nodeCount()==completeNodes and ns.depth==7 and nodes()[warrior].rank:GetText()==1,
  "orphan continuation cannot replace the completed historical canvas")
reset()

-- Glyph and pet routes retain DragonUI's existing behavior and depth restoration.
reply("GLYPHS 0")
press("K")
local gate=ET.L["Glyphs become available once this character has earned Wrath of the Lich King."]
assert(not win:IsShown() and notices[#notices]==gate,"glyph key explains earned-era gate")
fire("USE_GLYPH")
assert(not win:IsShown() and #notices==2,"using a glyph keeps earned-era gate")
tabClicked({GetID=function() return 4 end})
assert(not ns.GlyphView() and #notices==3,"glyph tab keeps earned-era gate")
ns.RefreshTabs()
assert(not DragonUI_TalentFrameTab4:IsShown(),"historical glyph tab is hidden")
reset()
reply("SYNC 2 0 0"); ns.RefreshTabs()
assert(not DragonUI_TalentFrameTab4:IsShown(),"server glyph gate also hides tab while native data is selected")
reply("SYNC 0 1 4 "..warrior..":2")
local chats=#warnings
ET.OpenStockTalents()
assert(not win:IsShown() and #warnings==chats+1,"pet opener without a pet preserves notice")
units.pet="0x0000000000000009"; petTalents=true
ET.OpenStockTalents(); runTimers()
assert(win:IsShown() and ns.PetView() and not painted.external and ns.depth==11,"pet tree remains native and restores native depth")
assertArtPair(ns.petArt)
assert(not ns.classArt:IsShown(),"native pet art hides the historical class art")
StaticPopupDialogs.DUI_TALENTS_LEARN.OnAccept()
assert(nativeLearns==1,"native pet preview can still be applied")
tabClicked({GetID=function() return 1 end})
assert(painted.external and ns.depth==7,"returning from pet tree restores historical tree")
assertArtPair(ns.classArt)
assert(not ns.petArt:IsShown(),"historical class art hides the native pet art")
reset(); units.pet=nil; petTalents=false
playerLevel=9; press("N")
assert(not win:IsShown() and notices[1]==FEATURE_BECOMES_AVAILABLE_AT_LEVEL:format(10),"talents remain level-gated")
playerLevel=15; reset()

-- The bot's actual toolbar button uses DragonUI and spends only server-authorized points.
clickBotTalents("Mey")
assert(win:IsShown() and ns.inspectUnit=="party1" and not panel(),"bot opens the same DragonUI window")
assert(TalentMicroButton.SetButtonStateArgs[1]=="NORMAL","inspecting a bot does not press the player's talent microbutton")
assert(talentButtons.Mey.state and not talentButtons.Godric.state,
  "opening bot talents presses only that bot's MultiBot button")
ns.OpenTalents()
assert(not ns.inspectUnit and win:IsShown() and TalentMicroButton.SetButtonStateArgs[1]=="PUSHED",
  "returning to own talents while open presses the player's microbutton")
assert(not talentButtons.Mey.state and not talentButtons.Godric.state,
  "returning to the player's own talents releases the bot button")
ns.ShowInspect("party1")
assert(ns.inspectUnit=="party1" and win:IsShown() and TalentMicroButton.SetButtonStateArgs[1]=="NORMAL",
  "switching the open own window to inspect releases the player's microbutton")
assert(talentButtons.Mey.state and not talentButtons.Godric.state,
  "switching the open window back to bot inspection selects that bot's button")
assert(nodeCount()==0,"bot waits without showing native ranks")
reply("ISYNC "..units.party1.." 0 1 1 "..warrior..":1")
local botNode=assert(nodes()[warrior])
assert(botNode.state==nativePartialNoPoints,"read-only learned partial bot ranks match native yellow")
local count=#sent
botNode:Click()
assert(#sent==count,"inspected player remains read-only before IEDIT")
reply("IEDIT "..units.party1.." 0 5")
assert(nodes()[warrior].state==nativePartialNoPoints,"read-only bot ranks stay yellow even with known unspent points")
assert(nodes()[EraTalentsData[0][1].talents[2].id].state=="gray","read-only empty bot talents stay gray")
reply("IEDIT "..units.party1.." 1 0")
assert(nodes()[warrior].state==nativePartialNoPoints,"controlled bot ranks stay yellow without unspent points")
nodes()[warrior]:Click()
assert(#sent==count,"controlled bot without points cannot buy another rank")
reply("IEDIT "..units.party1.." 1 5")
botNode=nodes()[warrior]
assert(botNode.state==nativePartialLearnable,"authorized bot partial ranks match native green while spendable")
botNode:Click()
assert(sent[#sent]=="ILEARN "..units.party1.." "..warrior,"controlled altbot spends through ILEARN")
assert(ET.inspect.cache[units.party1].ranks[warrior]==1,"bot ranks remain authoritative")
assert(nodes()[warrior].state==nativePartialNoPoints,"consumed bot permission restores the native yellow state")
count=#sent; botNode:Click()
assert(#sent==count,"permission is consumed until a fresh server reply")
reply("ISYNC "..units.party1.." 0 1 1 "..warrior..":2")
reply("IEDIT "..units.party1.." 1 4")
assert(nodes()[warrior].rank:GetText()==2,"bot server reply repaints the same canvas")
ns.NodeTooltip(nodes()[warrior]); GameTooltip:Hide()
ns.ImportFromInspect()
assert(nativeBuildReads==0,"historical inspected talents cannot be saved as native profiles")
assert(DragonUI_TalentSearchBox:IsShown() and not DragonUI_TalentInspectImport:IsShown(),"bot inspect retains search without native import")
reply("ISYNC "..units.party1.." 0 1 1 1/2 "..warrior..":2")
assert(nodeCount()==0,"partial bot reply cannot show incomplete ranks")
reply("ISYNC "..units.party1.." 0 1 1 2/2")
reply("IEDIT "..units.party1.." 0 0")
count=#sent; nodes()[warrior]:Click()
assert(#sent==count,"revoked permission stops bot learning")
ns.NodeTooltip(nodes()[warrior])
assert(not table.concat(tooltipLines," "):find(ET.L["Next rank:"],1,true),"read-only inspected tooltip omits next-rank actions")
GameTooltip:Hide()
local retiredBot={index=botNode.index,tree=botNode.tree,externalView=botNode.externalView}
local mage=EraTalentsData[1][8].talents[1].id
reply("ISYNC "..units.party1.." 1 1 8 "..mage..":1")
reply("IEDIT "..units.party1.." 1 4")
assert(ns.depth==9 and ns.artClass=="MAGE" and nodeCount()==#EraTalentsData[1][8].talents,
  "bot TBC class and era select their own complete tree independent of the player")
assertArtPair(ns.classArt)
count=#sent; ns.NodeClicked(retiredBot,"LeftButton")
assert(#sent==count,"stale painted bot class/era cannot send a purchase")
nodes()[mage]:Click()
assert(sent[#sent]=="ILEARN "..units.party1.." "..mage,"TBC bot purchase uses its own historical talent ID")
clickBotTalents("Mey")
assert(not win:IsShown(),"same bot talent button closes DragonUI")
assert(TalentMicroButton.SetButtonStateArgs[1]=="NORMAL","closing inspected talents keeps the player's microbutton released")
assert(not talentButtons.Mey.state and not talentButtons.Godric.state,
  "closing bot talents releases every MultiBot talent button")
reply("IEDIT "..units.party1.." 1 99")
assert(not win:IsShown(),"late replies do not reopen the window")
clickBotTalents("Mey")
assert(win:IsShown() and nodeCount()==0,"reopening waits for fresh bot state")
assert(not ET.inspect.cache[units.party1],"closing inspect drops cached bot permissions")
clickBotTalents("Godric")
assert(win:IsShown() and ns.inspectUnit=="party2","switching bot retargets existing window")
assert(not talentButtons.Mey.state and talentButtons.Godric.state,
  "switching inspected bots releases the previous bot's button")
reply("ISYNC "..units.party1.." 0 1 1 "..warrior..":3")
assert(nodeCount()==0,"late previous-target replies do not populate new bot")
reply("ISYNC "..units.party2.." 0 0 0")
assert(win:IsShown() and not painted.external and nodeCount()==3,"native inspect target keeps DragonUI's native renderer")
win:Hide()
assert(not talentButtons.Godric.state and TalentMicroButton.SetButtonStateArgs[1]=="NORMAL",
  "closing DragonUI directly releases the inspected bot and player buttons")
ns.ShowInspect("party2")
assert(talentButtons.Godric.state and not talentButtons.Mey.state,
  "reopening the same inspected character restores only its bot button")
ns.EnterEditor({}); ns.LoadOntoCharacter({})
assert(nativeBuildReads==0,"native inspected target cannot bypass own historical profile guards")
local staleCount=#sent
ns.NodeClicked(botNode,"LeftButton")
assert(#sent==staleCount,"retired historical nodes do not fall through to native actions")
InspectUnit("party3"); InspectFrameTab3:Click()
assert(ns.inspectUnit=="party3" and win:IsShown() and TalentMicroButton.SetButtonStateArgs[1]=="NORMAL",
  "the native inspect talent tab keeps a human inspection separate from own talents")
assert(not talentButtons.Mey.state and not talentButtons.Godric.state,
  "inspecting a human releases the previous bot's talent button")
press("N")
assert(not ns.inspectUnit and win:IsShown() and TalentMicroButton.SetButtonStateArgs[1]=="PUSHED",
  "the talent key returns from a human inspection to the player's own trees")
assert(not talentButtons.Mey.state and not talentButtons.Godric.state,
  "own talents after human inspection leave bot buttons released")
reset()
canInspect=false
assert(not MultiBot.OpenEraTalentInspect("Mey",true) and not win:IsShown(),"normal inspect refusal is preserved")
canInspect=true
ET.state.serverGen=nil; ET.helloSentAt=0; now=100
assert(not MultiBot.OpenEraTalentInspect("Mey",true),"native realms preserve MultiBot fallback")
reply("SYNC 2 0 0"); reply("GEN a1b2c3d4"); reply("GLYPHS 1")
press("K")
assert(win:IsShown() and ns.GlyphView(),"earned Wrath restores DragonUI glyph page")
reset(); press("N")
assert(not painted.external and ns.depth==11 and FixtureBuildDropdown:IsShown(),"Wrath restores native depth and profile controls")
assert(not unitFrames.Testi.getButton("Talent") and not talentButtons.Mey.state and not talentButtons.Godric.state,
  "native own talents never select a MultiBot talent button")
local sentBefore=#sent
ns.NodeClicked(retiredNode,"LeftButton")
assert(#sent==sentBefore,"retired hidden historical node cannot call native learn after Wrath transition")
print("DragonUI canvas: all historical classes, authoritative self/bot learning, guards and native routes passed")
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
            raise AssertionError('Unsafe production mutation unexpectedly passed')
        if not re.search(r'dragonui-(?:enabled|disabled)\.lua:\d+: ', result.stderr.splitlines()[0]):
            raise AssertionError('Mutation failed outside fixture assertions: ' + result.stderr)
        return
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    print(result.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--era-source', type=Path, default=prepared_core(ROOT) / 'modules/mod-era-talents')
    parser.add_argument('--dragon-source', type=Path, default=ROOT / '.module-cache/prepared-source-addons/DragonUI')
    parser.add_argument('--multibot-source', type=Path, default=ROOT / '.module-cache/prepared-addons/MultiBot')
    parser.add_argument('--no-fork-reversion', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='dragonui-era-talents-') as temporary:
        directory = Path(temporary)
        era, dragon, multibot = directory / 'era', directory / 'dragon', directory / 'multibot'
        dragon_addon = dragon / 'DragonUI'
        shutil.copytree(args.era_source / 'client-addon', era / 'client-addon')
        shutil.copytree(args.dragon_source / 'modules/talents', dragon_addon / 'modules/talents')
        (dragon_addon / 'utils').mkdir()
        shutil.copyfile(args.dragon_source / 'utils/atlas.lua', dragon_addon / 'utils/atlas.lua')
        for filename in ('UI/MultiBotTalentFrame.lua', 'Core/MultiBotEvery.lua'):
            destination = multibot / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.multibot_source / filename, destination)
        subprocess.run(['git', 'init', '-q', str(era)], check=True)
        subprocess.run(['git', 'init', '-q', str(dragon)], check=True)
        subprocess.run(['git', 'init', '-q', str(multibot)], check=True)
        if not args.no_fork_reversion:
            dragon_controls = fork_change('DragonUI', 'dragonui-control-ownership',
                                          paths=('DragonUI/modules/talents/',))
            bot_controls = fork_change('MultiBot', 'multibot-control-ownership',
                                       paths=('UI/MultiBotTalentFrame.lua', 'Core/MultiBotEvery.lua'))
            for path, patch in ((dragon, dragon_controls), (multibot, bot_controls)):
                unpatched(path, patch)
                git_apply(path, patch)
        chunks = dragon_chunks(dragon_addon, multibot)
        addon = era / 'client-addon/EraTalents'
        for enabled in (True, False):
            run(addon, chunks, directory, enabled=enabled)
        mutations = (
            (dragon_addon / 'modules/talents/entry_points.lua', ' and not ns.inspectUnit and TalentMicroButton then',
             ' and TalentMicroButton then'),
            (dragon_addon / 'modules/talents/live_view.lua', '        ns.Repaint()\n        UpdateMicroButtons()\n',
             '        ns.Repaint()\n'),
            (dragon_addon / 'modules/talents/live_view.lua',
             '    if ns.win and ns.win:IsShown() then UpdateMicroButtons() end\n', ''),
            (addon / 'EraTalents.lua', '  if ET.InitDragonUI then ET.InitDragonUI() end\n', ''),
            (addon / 'DragonUIGlyphs.lua', '      if Blocked() then return Refuse() end\n', ''),
            (addon / 'DragonUIGlyphs.lua', 'if on and Blocked() then', 'if false then'),
            (addon / 'DragonUIGlyphs.lua', 'if glyphTab and Blocked() then glyphTab:Hide() end', ''),
            (addon / 'Comms.lua', '  e.editable = false\n', ''),
            (addon / 'Comms.lua', '  if not isFirst and not state.partial then return true end\n', ''),
            (addon / 'TalentUI.lua', 'if not state or state.partial then', 'if not state then'),
            (addon / 'TalentUI.lua', 'if ET.state.clientGen ~= ET.state.serverGen then', 'if false then'),
            (addon / 'TalentUI.lua', 'if not byId[id] or rank < 0 or rank > byId[id].maxRank then',
             'if not byId[id] or rank < 0 then'),
            (addon / 'DragonUI.lua', 'if reachable and (view.available < 1 or view.readOnly) then',
             'if rank == 0 and reachable and (view.available < 1 or view.readOnly) then'),
            (addon / 'DragonUI.lua', 'view.available < 1 or view.readOnly', 'view.readOnly'),
            (addon / 'DragonUI.lua', 'view.available < 1 or view.readOnly', 'view.available < 1'),
            (addon / 'DragonUI.lua', 'rank > 0 and "yellow" or "gray"', '"gray"'),
            (addon / 'DragonUI.lua', 'or reachable and "green" or "locked"',
             'or reachable and "yellow" or "locked"'),
            (addon / 'DragonUI.lua', '      if button ~= "LeftButton" then return end\n', ''),
            (addon / 'DragonUI.lua', '      if not ET.IsReachable(talent, fresh.trees[talent.tab].points, fresh.state.ranks, fresh.byId) then return end\n', ''),
            (dragon_addon / 'modules/talents/build_editor.lua', '    if ns.Call("ExternalTalents", true) then return end\n', ''),
            (dragon_addon / 'modules/talents/build_editor.lua',
             'function ns.LoadOntoCharacter(build)\n    if ns.Call("ExternalTalents", true) then return end',
             'function ns.LoadOntoCharacter(build)'),
            (dragon_addon / 'modules/talents/build_editor.lua', '    if ns.ExternalTalentView() then return end\n', ''),
        )
        for path, before, after in mutations:
            print(f'Checking mutation {path.name}: {before.strip()}', flush=True)
            original = path.read_text()
            if before not in original:
                raise AssertionError('Expected production guard: ' + before)
            path.write_text(original.replace(before, after, 1))
            run(addon, chunks, directory, enabled=True, expect_failure=True)
            path.write_text(original)
        print('Checking native talent art split mutation', flush=True)
        right_half = 'self[2]:SetTexture(file .. "_r")'
        assert right_half in chunks['window']
        run(addon, dict(chunks, window=chunks['window'].replace(right_half, 'self[2]:SetTexture(file)', 1)),
            directory, enabled=True, expect_failure=True)
        for label, before in (
                ('selected bot button', '    if name then setTalentButtonEnabled(name, true) end\n'),
                ('previous bot release',
                 '    if eraTalentBot and eraTalentBot ~= name then setTalentButtonEnabled(eraTalentBot, false) end\n'),
                ('own view handoff',
                 '        if type(ns.LeaveInspect) == "function" then hooksecurefunc(ns, "LeaveInspect", syncEraTalentButtons) end\n')):
            if before not in chunks['bot']:
                raise AssertionError('Expected MultiBot inspect synchronization: ' + before)
            print('Checking MultiBot mutation: ' + label, flush=True)
            mutated = dict(chunks, bot=chunks['bot'].replace(before, '', 1))
            run(addon, mutated, directory, enabled=True, expect_failure=True)
        opener = 'if MultiBot.OpenEraTalentInspect and MultiBot.OpenEraTalentInspect(pButton.getName(), true) then return end'
        assert opener in chunks['bot_button']
        run(addon, dict(chunks, bot_button=chunks['bot_button'].replace(opener, '', 1)),
            directory, enabled=True, expect_failure=True)
        if args.no_fork_reversion:
            return
        for label, path, patch in (
                ('DragonUI control ownership', dragon, dragon_controls),
                ('MultiBot control ownership', multibot, bot_controls)):
            print('Checking reverted ' + label, flush=True)
            git_apply(path, patch, '--reverse')
            run(addon, dragon_chunks(dragon_addon, multibot), directory, enabled=True, expect_failure=True)
            git_apply(path, patch)
            run(addon, dragon_chunks(dragon_addon, multibot), directory, enabled=True)
        color_patch = fork_change('mod-era-talents', 'mod-era-talents-dragonui-colors',
                                  paths=('client-addon/EraTalents/DragonUI.lua',))
        print('Checking reverted historical talent colors', flush=True)
        git_apply(era, color_patch, '--reverse')
        run(addon, chunks, directory, enabled=True, expect_failure=True)
        git_apply(era, color_patch)
        run(addon, chunks, directory, enabled=True)
        for component, change, path in (
                ('mod-era-talents', 'mod-era-talents-dragonui-view', era),
                ('DragonUI', 'dragonui-era-talents', dragon),
                ('MultiBot', 'multibot-era-talent-inspect', multibot)):
            # Later changes touch the original integrations, so remove them first.
            if component == 'mod-era-talents':
                later_patch, paths = color_patch, ('client-addon/',)
            elif component == 'DragonUI':
                later_patch, paths = dragon_controls, ('DragonUI/modules/talents/',)
            else:
                later_patch, paths = bot_controls, ('UI/MultiBotTalentFrame.lua', 'Core/MultiBotEvery.lua')
            git_apply(path, later_patch, '--reverse')
            patch = fork_change(component, change, paths=paths)
            print(f'Checking reverted {change}', flush=True)
            git_apply(path, patch, '--reverse')
            run(addon, dragon_chunks(dragon_addon, multibot), directory, enabled=True, expect_failure=True)
            git_apply(path, patch)
            git_apply(path, later_patch)
        print('Removed integration, glyph and bot-authority guards all fail the regression fixture')


if __name__ == '__main__':
    main()
