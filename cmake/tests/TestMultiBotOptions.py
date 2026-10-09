#!/usr/bin/env python3
"""Exercise pinned MultiBot options initialization and fallback with Lua 5.1."""
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
PATCH = ROOT / "patches/multibot-options-initialization.patch"
SOURCE = None
LUA = None
FILE = "UI/MultiBotOptions.lua"
FILES = (FILE, "Libs/AceGUI-3.0/AceGUI-3.0.lua",
         "Libs/AceGUI-3.0/widgets/AceGUIContainer-TabGroup.lua")

# Execute the complete upstream options file. Frames model the Wrath methods
# used by that file; AceGUI models ownership, releases and its guarded Fire.
FIXTURE = r'''
local noop = function() end
local frames, widgets, caught, reported = {}, {}, {}, {}
local faults, counts = {}, {}
local legacyFailures, legacyChildFailures = 0, 0
local missingWidgetType
local function fault(point)
  counts[point] = (counts[point] or 0) + 1
  local selected = faults[point]
  if selected and (selected == true or selected == counts[point]) then
    error("injected failure: " .. point)
  end
end
local frameMethods = {}
local function frame(name)
  local f = setmetatable({name=name, scripts={}, shown=true, children={}}, {__index=frameMethods})
  frames[#frames+1] = f
  if name then _G[name] = f end
  return f
end
function frameMethods:GetName() return self.name end
function frameMethods:SetScript(event, callback) self.scripts[event] = callback end
function frameMethods:Hide() self.shown = false end
function frameMethods:Show()
  local changed = not self.shown
  self.shown = true
  if changed and self.scripts.OnShow then self.scripts.OnShow(self) end
end
function frameMethods:IsShown() return self.shown end
function frameMethods:SetText(text) self.text = text end
function frameMethods:GetText() return self.text end
function frameMethods:SetChecked(value) self.checked = value end
function frameMethods:GetChecked() return self.checked end
function frameMethods:SetValue(value)
  local changed = self.value ~= value
  self.value = value
  if changed and self.scripts.OnValueChanged then self.scripts.OnValueChanged(self, value) end
end
function frameMethods:SetScrollChild(child) self.scrollChild = child end
for _, key in ipairs({"SetPoint", "ClearAllPoints", "SetSize", "SetWidth", "SetHeight",
                      "SetMinMaxValues", "SetValueStep", "SetObeyStepOnDrag", "SetTextColor",
                      "Enable", "Disable", "SetParent"}) do frameMethods[key] = noop end
UIParent = frame("UIParent")
CreateFrame = function(kind, name, parent, template)
  if kind == "ScrollFrame" and template == "UIPanelScrollFrameTemplate" and legacyFailures > 0 then
    legacyFailures = legacyFailures - 1
    error("injected legacy frame failure")
  end
  if name == "MultiBotOptionsPanelScrollChild" and legacyChildFailures > 0 then
    legacyChildFailures = legacyChildFailures - 1
    error("injected legacy child failure")
  end
  local f = frame(name)
  f.parent = parent
  if parent then parent.children[#parent.children+1] = f end
  if name and (template == "InterfaceOptionsCheckButtonTemplate" or template == "OptionsSliderTemplate") then
    frame(name .. "Text")
  end
  if name and template == "OptionsSliderTemplate" then frame(name .. "Low"); frame(name .. "High") end
  return f
end
function frameMethods:CreateFontString() return frame() end
InterfaceOptions_AddCategory = function(panel) panel.registered = true end
geterrorhandler = function() return function(err) reported[#reported+1] = tostring(err) end end
for _, key in ipairs({"UIDropDownMenu_Initialize", "UIDropDownMenu_SetWidth", "UIDropDownMenu_SetButtonWidth",
                      "UIDropDownMenu_SetSelectedValue", "UIDropDownMenu_JustifyText", "UIDropDownMenu_SetText",
                      "UIDropDownMenu_SetSelectedID", "UIDropDownMenu_AddButton"}) do _G[key] = noop end
UIDropDownMenu_CreateInfo = function() return {} end
UnitName = function() return "Spieler" end
GetRealmName = function() return "Realm" end

MultiBotSave = {bot="AltBot", custom={keep="saved character settings"}}
MultiBotDB = {profile={minimap={hide=false, angle=37}, timers={stats=45,talent=3,invite=5,sort=1},
                       throttle={rate=5,burst=8}, custom="retain profile"}}
MultiBotSaved = {characters={AltBot={gold=4321}}, layout="retain layout"}
MultiBotGlobalSave = {custom="retain global settings"}
local function snapshot(value)
  if type(value) ~= "table" then return type(value)..":"..tostring(value) end
  local keys, parts = {}, {}
  for key in pairs(value) do keys[#keys+1] = key end
  table.sort(keys)
  for _, key in ipairs(keys) do parts[#parts+1] = key .. "=" .. snapshot(value[key]) end
  return "{"..table.concat(parts,";").."}"
end
local savedReferences = {MultiBotSave, MultiBotDB, MultiBotSaved, MultiBotGlobalSave}
local savedBefore = snapshot(savedReferences)
MultiBot = {
  RegisterCommandAliases = noop,
  L = function(key) return key end,
  GetMinimapConfig = function() return MultiBotDB.profile.minimap end,
  SetMinimapConfig = function(key,value) MultiBotDB.profile.minimap[key]=value end,
  GetTimer = function(key) return MultiBotDB.profile.timers[key] end,
  SetTimer = function(key,value) MultiBotDB.profile.timers[key]=value end,
  GetThrottleRate = function() return MultiBotDB.profile.throttle.rate end,
  SetThrottleRate = function(value) MultiBotDB.profile.throttle.rate=value end,
  GetThrottleBurst = function() return MultiBotDB.profile.throttle.burst end,
  SetThrottleBurst = function(value) MultiBotDB.profile.throttle.burst=value end,
}
local AceGUI = {}
local widgetMethods = {}
function widgetMethods:AddChild(child)
  fault("AddChild:"..child.type)
  self.children[#self.children+1] = child
  child.parent = self
end
function widgetMethods:ReleaseChildren()
  while #self.children > 0 do AceGUI:Release(table.remove(self.children)) end
end
function widgetMethods:SetCallback(event, callback) self.events[event] = callback end
function widgetMethods:SelectTab(value)
  self.selected = value
  local callback = self.events.OnGroupSelected
  if callback then
    -- Actual AceGUI Fire swallows callback errors via safecall.
    local ok, err = pcall(callback, self, "OnGroupSelected", value)
    if not ok then caught[#caught+1] = err end
  end
end
function widgetMethods:SetTabs(tabs) self.tabs = tabs end
function widgetMethods:SetLabel(label) fault("SetLabel:"..self.type); self.label = label end
function widgetMethods:SetText(text) self.text = text end
function widgetMethods:SetValue(value) self.value = value end
function widgetMethods:SetList(list) self.list = list end
for _, key in ipairs({"SetFullWidth", "SetFullHeight", "SetLayout", "SetParent", "ClearAllPoints",
                      "SetPoint", "SetWidth", "SetHeight", "SetDescription", "SetDisabled",
                      "SetSliderValues"}) do widgetMethods[key] = noop end
function AceGUI:Create(kind)
  fault("Create:"..kind)
  if kind == missingWidgetType then return nil end
  local w = setmetatable({type=kind, frame=frame(), children={}, events={}}, {__index=widgetMethods})
  widgets[#widgets+1] = w
  if kind == "TabGroup" then lastTabGroup = w end
  return w
end
function AceGUI:Release(widget)
  assert(not widget.released, "double release of " .. widget.type)
  widget:ReleaseChildren()
  widget.released = true
  widget.frame:Hide()
  widget.events = {}
end
LibStub = setmetatable({}, {__call=function(_,name,silent) return AceGUI end})
local function checkSaved()
  assert(savedReferences[1] == MultiBotSave and savedReferences[2] == MultiBotDB
         and savedReferences[3] == MultiBotSaved and savedReferences[4] == MultiBotGlobalSave)
  assert(snapshot(savedReferences) == savedBefore, "options initialization changed SavedVariables")
end
local function checkReleased()
  for _, widget in ipairs(widgets) do
    assert(widget.released, "leaked "..widget.type)
    assert(not widget.frame.shown, "visible discarded "..widget.type)
  end
end
local function loadOptions()
  dofile(OPTIONS_SOURCE)
  MultiBot.BuildOptionsPanel()
  assert(MultiBot._optionsPanel.registered)
  return MultiBot._optionsPanel
end
local function reopen(panel) panel:Hide(); panel:Show() end
local function checkLegacy(panel)
  assert(panel._initialized == true and panel._legacyInitialized == true)
  assert(panel._aceRoot == nil and panel._legacyScrollFrame and panel._legacyScrollFrame.shown)
  assert(panel.chkMinimapHide and panel.chkMainBarMoveLocked and panel.chkDisableAutoCollapse)
  assert(panel.mainBarAutoHideDelaySlider)
  local scroll = panel._legacyScrollFrame.scrollChild
  assert(scroll.s_stats and scroll.s_talent and scroll.s_thr_rate and scroll.s_thr_burst)
  checkSaved()
end
'''


class MultiBotOptionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="multibot-options-")
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
                url = "https://raw.githubusercontent.com/Wishmaster117/MultiBot-Chatless/" + revision + "/" + relative
                with urllib.request.urlopen(url, timeout=30) as response:
                    content = response.read(2 * 1024 * 1024 + 1)
                if len(content) > 2 * 1024 * 1024:
                    raise ValueError("MultiBot fixture source exceeds the supported size")
                destination.write_bytes(content)
        destination = cls.directory / FILE
        check = subprocess.run(["git", "apply", "--check", str(PATCH)], cwd=cls.directory,
                               capture_output=True, text=True)
        if check.returncode:
            subprocess.run(["git", "apply", "--reverse", "--check", str(PATCH)], cwd=cls.directory,
                           check=True, capture_output=True)
            subprocess.run(["git", "apply", "--reverse", str(PATCH)], cwd=cls.directory,
                           check=True, capture_output=True)
        cls.pristine = cls.directory / "pristine.lua"
        shutil.copyfile(destination, cls.pristine)
        subprocess.run(["git", "apply", str(PATCH)], cwd=cls.directory, check=True, capture_output=True)
        cls.options = destination
        cls.acegui = cls.directory / FILES[1]
        cls.tabgroup = cls.directory / FILES[2]

    def run_lua(self, body, pristine=False):
        script = "local OPTIONS_SOURCE = " + json.dumps(str(self.pristine if pristine else self.options))
        script += "\nlocal ACEGUI_SOURCE = " + json.dumps(str(self.acegui))
        script += "\nlocal TABGROUP_SOURCE = " + json.dumps(str(self.tabgroup))
        script += "\n" + FIXTURE + "\n" + body
        result = subprocess.run([LUA, "-"], input=script, text=True, capture_output=True, timeout=20)
        if not pristine:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_constructor_failure_no_longer_leaves_a_permanently_empty_panel(self):
        body = '''
faults["Create:TabGroup"] = true
local panel = loadOptions()
panel:Show()
checkLegacy(panel)
checkReleased()
local widgetCount, frameCount = #widgets, #frames
reopen(panel)
assert(#widgets == widgetCount and #frames == frameCount, "reopening rebuilt working controls")
checkLegacy(panel)
'''
        self.assertNotEqual(self.run_lua(body, pristine=True).returncode, 0,
                            "original constructor regression must fail")
        self.run_lua(body)

    def test_successful_acegui_preserves_tabs_and_settings(self):
        self.run_lua('''
local panel = loadOptions()
panel:Show()
assert(panel._initialized and panel._aceRoot and not panel._legacyInitialized)
assert(#lastTabGroup.tabs == 4 and lastTabGroup.selected == "minimap")
for _, tab in ipairs({"layout", "strata", "intervals", "minimap"}) do
  lastTabGroup:SelectTab(tab)
  assert(panel._aceRoot and not panel._legacyInitialized and #lastTabGroup.children == 1)
end
assert(#caught == 0 and #reported == 0)
local count = #widgets
reopen(panel)
assert(#widgets == count)
checkSaved()
''')

    def test_missing_acegui_uses_usable_legacy_controls(self):
        self.run_lua('''
LibStub = nil
local panel = loadOptions()
panel:Show()
checkLegacy(panel)
assert(#widgets == 0 and #reported == 0)
local count = #frames
reopen(panel)
assert(#frames == count)
''')

    def test_label_probe_failure_falls_back_without_resetting_saved_variables(self):
        self.run_lua('''
faults["Create:Label"] = true
local panel = loadOptions()
panel:Show()
checkLegacy(panel)
checkReleased()
assert(#reported == 0)
''')

    def test_tab_builder_failure_is_caught_inside_acegui_guarded_callback(self):
        body = '''
faults["SetLabel:CheckBox"] = true
local panel = loadOptions()
panel:Show()
checkLegacy(panel)
checkReleased()
assert(#caught == 0, "callback escaped into AceGUI safecall instead of invoking fallback")
assert(#reported == 0)
'''
        self.assertNotEqual(self.run_lua(body, pristine=True).returncode, 0,
                            "original guarded callback regression must fail")
        self.run_lua(body)

    def test_later_tab_failure_cleans_attached_and_unattached_widgets(self):
        self.run_lua('''
local panel = loadOptions()
panel:Show()
assert(panel._aceRoot)
faults["SetLabel:Dropdown"] = true
lastTabGroup:SelectTab("layout")
checkLegacy(panel)
checkReleased()
assert(#caught == 0 and #reported == 0)
reopen(panel)
checkLegacy(panel)
''')

    def test_parent_attachment_failure_cleans_orphaned_widget(self):
        self.run_lua('''
faults["AddChild:ScrollFrame"] = true
local panel = loadOptions()
panel:Show()
checkLegacy(panel)
checkReleased()
''')

    def test_failed_legacy_build_can_retry_after_transient_failure(self):
        self.run_lua('''
LibStub = nil
legacyFailures = 1
local panel = loadOptions()
panel:Show()
assert(not panel._initialized and not panel._legacyInitialized and not panel._initializing)
assert(#reported == 1)
checkSaved()
reopen(panel)
checkLegacy(panel)
assert(#reported == 1)
''')

    def test_missing_tab_widget_uses_existing_legacy_controls(self):
        self.run_lua('''
missingWidgetType = "TabGroup"
local panel = loadOptions()
panel:Show()
checkLegacy(panel)
checkReleased()
assert(#reported == 0)
''')

    def test_partially_created_legacy_controls_are_hidden_before_retry(self):
        self.run_lua('''
LibStub = nil
legacyChildFailures = 1
local panel = loadOptions()
panel:Show()
assert(not panel._initialized and not panel._legacyInitialized and not panel._initializing)
local discarded = panel._legacyScrollFrame
assert(discarded and not discarded.shown)
reopen(panel)
checkLegacy(panel)
assert(panel._legacyScrollFrame ~= discarded and not discarded.shown)
assert(#reported == 1)
''')

    def test_both_builders_failing_does_not_block_a_later_reopen(self):
        self.run_lua('''
faults["Create:TabGroup"] = true
legacyFailures = 1
local panel = loadOptions()
panel:Show()
assert(not panel._initialized and not panel._aceRoot and not panel._initializing)
checkReleased()
checkSaved()
faults["Create:TabGroup"] = nil
reopen(panel)
assert(panel._initialized and panel._aceRoot and not panel._legacyInitialized)
assert(#caught == 0 and #reported == 1)
checkSaved()
''')
    def test_actual_acegui_release_and_tabgroup_selecttab_support_callback_fallback(self):
        self.run_lua('''
-- Use pinned upstream AceGUI Release, ownership, safecall and TabGroup SelectTab.
function frameMethods:SetWidth(value) self.width = value end
function frameMethods:SetHeight(value) self.height = value end
function frameMethods:GetWidth() return self.width or 300 end
function frameMethods:GetHeight() return self.height or 100 end
function frameMethods:GetTextWidth() return #(self.text or "") * 7 end
for _, key in ipairs({"SetFrameStrata", "SetJustifyH", "SetBackdrop", "SetBackdropColor",
                      "SetBackdropBorderColor", "SetAllPoints"}) do frameMethods[key] = noop end
local baseCreateFrame = CreateFrame
CreateFrame = function(kind,name,parent,template)
  local f = baseCreateFrame(kind,name,parent,template)
  if name and template == "OptionsFrameTabButtonTemplate" then
    frame(name .. "Text"); frame(name .. "HighlightTexture")
  end
  return f
end
wipe = function(values) for key in pairs(values) do values[key] = nil end end
PanelTemplates_TabResize = function(tab) tab:SetWidth(tab:GetTextWidth() + 30) end
PanelTemplates_SetDisabledTabState = noop
PanelTemplates_SelectTab = noop
PanelTemplates_DeselectTab = noop
LibStub = setmetatable({libs={},minors={}}, {
  __call=function(self,name) return self.libs[name] end
})
function LibStub:NewLibrary(name,minor)
  local previous = self.minors[name]
  if previous and previous >= minor then return nil end
  self.minors[name] = minor
  self.libs[name] = self.libs[name] or {}
  return self.libs[name], previous
end
dofile(ACEGUI_SOURCE)
local actualAce = LibStub("AceGUI-3.0")
dofile(TABGROUP_SOURCE)
for _, kind in ipairs({"Label", "SimpleGroup", "ScrollFrame", "CheckBox", "Slider", "Dropdown", "Button"}) do
  local widgetType = kind
  actualAce:RegisterWidgetType(kind, function()
    local widget = {type=widgetType, frame=frame(), OnAcquire=noop}
    for _, key in ipairs({"SetLabel", "SetText", "SetValue", "SetList", "SetDescription", "SetDisabled", "SetSliderValues"}) do
      widget[key] = widgetMethods[key]
    end
    if widgetType == "SimpleGroup" or widgetType == "ScrollFrame" then
      widget.content = frame()
      return actualAce:RegisterAsContainer(widget)
    end
    return actualAce:RegisterAsWidget(widget)
  end, 1)
end
local actualCreate, actualRelease = actualAce.Create, actualAce.Release
function actualAce:Create(kind)
  fault("Create:"..kind)
  local widget = actualCreate(self,kind)
  if widget then
    widget.released = nil
    widgets[#widgets+1] = widget
    if kind == "TabGroup" then lastTabGroup = widget end
  end
  return widget
end
function actualAce:Release(widget)
  assert(not widget.released, "double release of " .. widget.type)
  actualRelease(self,widget)
  widget.released = true
end
local panel = loadOptions()
panel:Show()
assert(panel._aceRoot and #reported == 0)
assert(lastTabGroup.SelectTab ~= widgetMethods.SelectTab)
lastTabGroup:SelectTab("layout")
assert(panel._aceRoot and #reported == 0)
lastTabGroup:SelectTab("minimap")
faults["SetLabel:Dropdown"] = true
lastTabGroup:SelectTab("layout")
checkLegacy(panel)
checkReleased()
assert(actualAce.objPools.TabGroup[lastTabGroup], "TabGroup was not returned to real AceGUI pool")
assert(#reported == 0, "fallback escaped into real AceGUI safecall")
reopen(panel)
checkLegacy(panel)
''')

    def test_library_lookup_failure_clears_initializing_guard(self):
        self.run_lua('''
local stub = LibStub
LibStub = setmetatable({}, {__call=function() error("injected LibStub failure") end})
local panel = loadOptions()
panel:Show()
assert(not panel._initialized and not panel._initializing and #reported == 1)
LibStub = stub
reopen(panel)
assert(panel._initialized and panel._aceRoot)
checkSaved()
''')

    def test_debug_handler_failure_does_not_block_fallback(self):
        self.run_lua('''
MultiBot.Debug = {OptionsPath=function() error("injected debug handler failure") end}
faults["Create:TabGroup"] = true
local panel = loadOptions()
panel:Show()
checkLegacy(panel)
checkReleased()
assert(not panel._initializing and #reported == 0)
''')

    def test_error_handler_failure_does_not_block_retry(self):
        self.run_lua('''
LibStub = nil
legacyFailures = 1
geterrorhandler = function() error("injected error handler failure") end
local panel = loadOptions()
panel:Show()
assert(not panel._initialized and not panel._initializing)
reopen(panel)
checkLegacy(panel)
''')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--addon-source", type=Path,
                        help="existing pinned MultiBot source; defaults to pinned upstream Lua files")
    parser.add_argument("--lua", default=shutil.which("lua5.1") or shutil.which("lua"),
                        help="Lua 5.1 executable")
    arguments, remaining = parser.parse_known_args()
    SOURCE = arguments.addon_source
    LUA = arguments.lua
    if not LUA:
        parser.error("Lua 5.1 is required")
    unittest.main(argv=[__file__, *remaining])
