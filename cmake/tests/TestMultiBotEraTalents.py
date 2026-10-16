"""Run native ISYNC selection and the actual MultiBot/EraTalents inspect UI.

The client consumes packets produced by the server fixture for all nine authored
classes. No realm/database is started; native inspection gates, mixed-era targets,
locales, incomplete replies and incompatible client data remain observable.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from FixtureSupport import (
    SANITIZER_FLAGS,
    TIMEOUT,
    cxx,
    function,
    git_apply,
    prepared_core,
    run_fixture,
    unpatched,
)


ROOT = Path(__file__).resolve().parents[2]
ERA_PATCH = ROOT / 'patches/mod-era-talents-multibot-inspect.patch'
BOT_PATCH = ROOT / 'patches/multibot-era-talent-inspect.patch'


def native_fixture(module: Path, directory: Path) -> list[list[str]]:
    src = module / 'src'
    ip = prepared_core(ROOT) / 'modules/mod-individual-progression/src'
    progression_enum = re.search(r'enum ProgressionState : uint8[^{}]*\{.*?^\};',
                                 (ip / 'IndividualProgression.h').read_text(), re.MULTILINE | re.DOTALL).group(0)
    earned_era = function((ip / 'IndividualProgression.cpp').read_text(), 'uint8 IndividualProgression_GetEarnedEra(')
    comms = (src / 'EraTalentsComms.cpp').read_text()
    code = r'''
#include <algorithm>
#include <cassert>
#include <cctype>
#include <cstdint>
#include <iostream>
#include <map>
#include <optional>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>
using uint8=uint8_t; using uint32=uint32_t; using uint64=uint64_t;
enum EraId : uint8 { ERA_VANILLA=0, ERA_TBC=1, ERA_WOTLK=2 };
// NATIVE_PROGRESSION_ENUM
constexpr uint32 INSPECT_DISTANCE=28, CONFIG_TALENTS_INSPECTING=0;
constexpr size_t kMaxGuidToken=18, kMaxChunkBody=230;
struct ObjectGuid { uint64 raw=0; ObjectGuid()=default; explicit ObjectGuid(uint64 v):raw(v) {} };
struct Player {
    uint64 guid=0; uint8 stage=0, level=60, cls=5;
    bool bot=false, headless=false, inRange=true, enemy=false, gm=false;
    std::optional<EraId> stored;
    std::map<uint8,std::unordered_map<uint32,uint8>> ranks;
    uint8 getClass() const { return cls; }
    bool IsWithinDistInMap(Player* p,uint32 distance,bool) const { assert(distance==28); return p->inRange; }
    bool IsValidAttackTarget(Player* p) const { return p->enemy; }
    bool CanBeGameMaster() const { return gm; }
};
struct Progression {
    bool enabled=true,strict=true; int progressionLimit=0;
    bool IsStrictDefaultProgression() const { return enabled && strict; }
    uint8 GetPlayerProgressionFromQuests(Player* p) const { return p->stage; }
} progression;
auto* sIndividualProgression=&progression;
''' + earned_era + '\n' + function((src / 'EraTalentIP.cpp').read_text(), 'EraId EraFromIP(') + r'''
namespace EraTransition { EraId StoredEra(Player* p) { return p->stored.value_or(EraFromIP(p)); } }
struct EraTalentNode { uint32 id; uint8 era,cls,maxRank; };
struct Content {
    std::vector<EraTalentNode> nodes;
    std::vector<EraTalentNode const*> NodesFor(uint8 era,uint8 cls) const {
        std::vector<EraTalentNode const*> result;
        for (auto const& node:nodes) if (node.era==era && node.cls==cls) result.push_back(&node);
        return result;
    }
} content;
auto* sEraTalentContent=&content;
bool EraHasTalentTrees(Player* p,EraId era) { return p && !content.NodesFor(era,p->cls).empty(); }
struct Config { bool enabled=true,bots=true; bool Enabled() const { return enabled; } bool BotTalents() const { return bots; } } config;
auto* sEraTalentsConfig=&config;
namespace EraTalentBots {
bool IsBot(Player* p) { return p->bot || p->headless; }
''' + function((src / 'EraTalentBots.cpp').read_text(), '    EraId EraFor(') + '\n' + function(
        (src / 'EraTalentBots.cpp').read_text(), '    bool IsEraManaged(') + r'''
}
namespace EraTalents { auto Ranks(Player* p,EraId era) { return p->ranks[era]; } }
namespace ObjectAccessor {
std::map<uint64,Player*> players;
Player* GetPlayer(Player const&,ObjectGuid guid) { auto i=players.find(guid.raw); return i==players.end() ? nullptr : i->second; }
}
struct World { bool inspect=true; bool getBoolConfig(uint32) const { return inspect; } } world;
auto* sWorld=&world;
''' + '\n'.join(function(comms, signature) for signature in (
        '    std::vector<std::string> ChunkRankList(', '    std::string RankList(',
        '    bool ParseGuidToken(', '    Player* InspectTarget(',
        '    std::vector<std::string> BuildInspectSync(')) + '\nint main() {\n'
    # Locked generated data supplies the real era/class IDs, order and rank limits.
    for file in sorted((module / 'client-addon/EraTalents/data/generated').glob('*.lua')):
        value = file.read_text()
        header = re.search(r'EraTalentsData\[(\d+)\]\[(\d+)\] =', value)
        if header is None:
            raise ValueError(f'No generated class header: {file}')
        era, cls = header.groups()
        for node, maximum in re.findall(r'\{ id=(\d+),[^\n]*?maxRank=(\d+)', value):
            code += f' content.nodes.push_back({{{node},{era},{cls},{maximum}}});\n'
    code += r'''
    Player master; master.guid=1; master.stage=18; master.level=80;
    Player bot; bot.guid=2; bot.bot=true;
    ObjectAccessor::players[bot.guid]=&bot;
    std::string const token="0x0000000000000002";
    for (uint8 cls : {1,2,3,4,5,7,8,9,11}) {
        bot.cls=cls;
        for (uint8 era : {0,1}) {
            bot.ranks[era].clear();
            for (auto const* node:content.NodesFor(era,cls)) bot.ranks[era][node->id]=1;
        }
        for (uint8 stage=0;stage<=18;++stage) {
            bot.stage=stage;
            EraId expected=stage<=7 ? ERA_VANILLA : stage<=12 ? ERA_TBC : ERA_WOTLK;
            for (uint8 level : {10,60,70,80}) for (uint8 leaderStage : {0,8,18}) {
                bot.level=level; master.stage=leaderStage;
                auto result=BuildInspectSync(&master,token);
                if (expected==ERA_WOTLK) assert(result==std::vector<std::string>{"ISYNC "+token+" 0 0 0"});
                else {
                    std::string const header="ISYNC "+token+" "+std::to_string(expected)+" 1 "+std::to_string(cls)+" ";
                    assert(result.size()>1); // complete authored trees require chunking
                    for (auto const& body:result) assert(body.starts_with(header) && body.size()<=230);
                }
            }
        }
        for (uint8 stage : {0,8,13}) {
            bot.stage=stage;
            for (auto const& body:BuildInspectSync(&master,token))
                std::cout << unsigned(stage<=7 ? 0 : stage<=12 ? 1 : 2) << '~' << unsigned(cls) << '~' << body << '\n';
        }
    }
    bot.cls=5; bot.stage=18;
    progression.progressionLimit=7;
    assert(BuildInspectSync(&master,token).front().starts_with("ISYNC "+token+" 0 1 5 "));
    progression.progressionLimit=12;
    assert(BuildInspectSync(&master,token).front().starts_with("ISYNC "+token+" 1 1 5 "));
    progression.progressionLimit=0;
    bot.stage=8; bot.stored=ERA_VANILLA;
    assert(BuildInspectSync(&master,token).front().starts_with("ISYNC "+token+" 0 1 5 "));
    bot.stored.reset();
    auto denial=std::vector<std::string>{"ISYNC "+token+" 0 0 0"};
    bot.inRange=false; assert(BuildInspectSync(&master,token)==denial); bot.inRange=true;
    bot.enemy=true; assert(BuildInspectSync(&master,token)==denial); bot.enemy=false;
    world.inspect=false; assert(BuildInspectSync(&master,token)==denial);
    master.gm=true; assert(BuildInspectSync(&master,token)!=denial); master.gm=false; world.inspect=true;
    config.enabled=false; assert(BuildInspectSync(&master,token)==denial); config.enabled=true;
    config.bots=false; assert(BuildInspectSync(&master,token)==denial);
    bot.bot=false; bot.headless=true; assert(BuildInspectSync(&master,token)==denial);
    bot.headless=false; assert(BuildInspectSync(&master,token)!=denial); config.bots=true;
    bot.cls=6; assert(BuildInspectSync(&master,token)==denial);
    for (std::string const malformed : {"0x", "nope", "0x1!", "0x000000000000000200"})
        assert(BuildInspectSync(&master,malformed).front().ends_with(" 0 0 0"));
}
'''
    code = code.replace('// NATIVE_PROGRESSION_ENUM', progression_enum)
    source = directory / 'native-inspect.cpp'
    binary = directory / 'native-inspect'
    source.write_text(code)
    compiler = cxx()
    subprocess.run([compiler, '-std=c++20', '-Wall', '-Wextra', '-Werror',
                    *SANITIZER_FLAGS, '-no-pie',
                    str(source), '-o', str(binary)], check=True)
    result = subprocess.run([str(binary)], check=True, capture_output=True, text=True, timeout=TIMEOUT)
    return [line.split('~', 2) for line in result.stdout.splitlines()]


LUA_FIXTURE = r'''
local locale, addon, multibot, packets = ...
GetLocale=function() return locale end
local methods={}
local function Object(name,parent) return setmetatable({name=name,parent=parent,scripts={},hooks={},shown=false},{__index=methods}) end
for _,name in ipairs({"SetFrameStrata","SetPoint","EnableMouse","SetMovable","RegisterForDrag","RegisterEvent","SetAllPoints","SetFrameLevel","SetTexture","SetTexCoord","SetTextColor","SetAlpha","EnableMouseWheel","SetScrollChild","SetDesaturated","ClearAllPoints"}) do
  methods[name]=function(self,...) self[name.."Args"]={...} end
end
function methods:GetName() return self.name end
function methods:GetFrameLevel() return 0 end
function methods:SetWidth(n) self.width=n end
function methods:SetHeight(n) self.height=n end
function methods:SetText(s) self.text=s end
function methods:SetScript(name,fn) self.scripts[name]=fn end
function methods:HookScript(name,fn) self.hooks[name]=self.hooks[name] or {}; table.insert(self.hooks[name],fn) end
function methods:IsShown() return self.shown end
function methods:Hide()
  if not self.shown then return end
  self.shown=false
  for _,fn in ipairs(self.hooks.OnHide or {}) do fn(self) end
end
function methods:Show()
  if self.shown then return end
  self.shown=true
  for _,fn in ipairs(self.hooks.OnShow or {}) do fn(self) end
end
function methods:CreateTexture() return Object() end
function methods:CreateFontString() return Object() end
function methods:SetNormalTexture() self.normal=Object() end
function methods:GetNormalTexture() return self.normal end
CreateFrame=function(_,name,parent) local o=Object(name,parent); if name then _G[name]=o end; return o end
UIParent=Object("UIParent")
InspectFrame=Object("InspectFrame")
InspectTalentFrame=Object("InspectTalentFrame",InspectFrame)
for _,name in ipairs({"InspectTalentFrameScrollFrame","InspectTalentFramePointsBar","InspectTalentFrameTab1","InspectTalentFrameTab2","InspectTalentFrameTab3"}) do _G[name]=Object(name,InspectTalentFrame); _G[name]:Show() end
SetPortraitTexture=function() end
PanelTemplates_TabResize=function() end
PanelTemplates_SetNumTabs=function() end
PanelTemplates_SetTab=function() end
PanelTemplates_UpdateTabs=function() end
GameTooltip={lines={},SetOwner=function() end,SetText=function(self,s) self.title=s;self.lines={} end,AddLine=function(self,s) table.insert(self.lines,s) end,Show=function() end,Hide=function() end}
local warnings={}
DEFAULT_CHAT_FRAME={AddMessage=function(_,s) table.insert(warnings,s) end}
UIErrorsFrame={AddMessage=function() error("inspect cannot learn talents") end}
local units={party1="0x0000000000000002",party2="0x0000000000000003",player="0x0000000000000001"}
UnitGUID=function(unit) return units[unit] end
UnitExists=function(unit) return units[unit]~=nil end
UnitName=function(unit) return unit=="player" and "Master" or "Altbot" end
UnitLevel=function() return 60 end
local allowed=true
CanInspect=function(unit) return allowed and UnitExists(unit) end
CheckInteractDistance=function() return true end
wipe=function(t) for key in pairs(t) do t[key]=nil end end
local hooks={}
hooksecurefunc=function(name,fn) hooks[name]=fn end
HideUIPanel=function(frame) frame:Hide(); if frame==InspectFrame then InspectTalentFrame:Hide() end end
local calls=0
InspectUnit=function(unit)
  calls=calls+1
  HideUIPanel(InspectFrame)
  InspectFrame.unit=unit
  InspectFrame:Show(); InspectTalentFrame:Show()
  if hooks.InspectFrame_Show then hooks.InspectFrame_Show() end
end
IsAddOnLoaded=function() return true end
local sent={}
SendAddonMessage=function(prefix,message,channel,recipient)
  assert(prefix=="ERATAL" and channel=="WHISPER" and recipient=="Master")
  assert(message:match("^INSPECT ") or message=="HELLO","inspection must never send LEARN or a preset")
  table.insert(sent,message)
end
GetSpellInfo=function(id) if id==932999 then return "EraTalents Gen a1b2c3d4" end; return "Spell "..id end
EraTalents={PREFIX="ERATAL",state={era=2,ranks={},availPts=71,isEraChar=false}}
dofile(addon.."Locales.lua")
for _,name in ipairs({"Warrior","Paladin","Hunter","Rogue","Priest","Shaman","Mage","Warlock","Druid"}) do
  dofile(addon.."data/generated/"..name.."Vanilla.lua")
  dofile(addon.."data/generated/"..name.."TBC.lua")
end
dofile(addon.."Comms.lua"); dofile(addon.."TalentUI.lua"); dofile(addon.."Inspect.lua")
local ET=EraTalents
ET.InitInspect()
ET.CheckGeneration("a1b2c3d4")
ET.Learn=function() error("read-only bot view cannot learn talents") end
local selected="Altbot"
local button
button={state=false,getName=function() return selected end,getClass=function() return "Priest" end,setDisable=function() return button end,setEnable=function() end}
MultiBot={index={actives={}},frames={MultiBar={frames={Units={buttons={},frames={}}}}},auto={talent=true},talent={name="Altbot",doClear=function() end,Hide=function() end,renderTalentBuild=function() error("fixed Wrath tree cannot render a historical bot") end,getTalentsBuildOptions=function() return {} end},toUnit=function(name) return name=="Altbot" and "party1" or name=="Otherbot" and "party2" end,L=function(key) return key end}
dofile(multibot.."UI/MultiBotTalentFrame.lua")
__BUTTON__
__SET_TALENTS__
local function suppressed() return not InspectTalentFrameScrollFrame:IsShown() end
local function close() HideUIPanel(InspectFrame) end
ET.state.serverGen=nil; ET.state.clientGen=nil
button.doLeft(button)
assert(suppressed() and ET.inspectStatus:IsShown(),"a bot request before the first GEN must not reveal native Wrath talents")
for _,record in ipairs(packets) do if record[1]=="0" and record[2]=="5" then ET.OnAddonMsg("ERATAL",record[3]) end end
assert(suppressed() and (not ET.inspectView or not ET.inspectView.frame:IsShown()),"a historical reply waits for generation validation")
ET.CheckGeneration("a1b2c3d4"); assert(ET.inspectView.frame:IsShown())
close()
for _,record in ipairs(packets) do
  local era,cls,message=tonumber(record[1]),tonumber(record[2]),record[3]
  if message:find(" 1/",1,true) or era==2 then
    close(); MultiBot.auto.talent=true; button.doLeft(button)
    assert(InspectFrame:IsShown() and not MultiBot.auto.talent,"MultiBot must use authoritative inspect without its Wrath timer")
    assert(suppressed(),"a pending reply must not expose the WotLK tree")
    local before=calls
    MultiBot.talent.setTalents()
    assert(calls==before and InspectFrame:IsShown(),"timer refresh cannot toggle/reopen an active target")
  end
  ET.OnAddonMsg("ERATAL",message)
  local state=ET.inspect.cache[UnitGUID("party1")]
  if era==2 then
    assert(not suppressed() and not ET.inspectView.frame:IsShown(),"WotLK characters retain the native inspect tree")
  elseif state.partial then
    assert(suppressed() and ET.inspectStatus:IsShown(),"partial ranks are not presented as a complete tree")
  else
    local view=ET.inspectView
    assert(view.readOnly and view.classId==cls and view.state.era==era)
    assert(EraTalents.state.era==2 and next(EraTalents.state.ranks)==nil,"bot replies must not mutate the master's talents")
    local tree=EraTalentsData[era][cls]
    local node
    for _,candidate in ipairs(tree.talents) do if candidate.tab==view.activeTab and not candidate.grant then node=candidate;break end end
    assert(node,"every authored tree must contain an inspectable passive node")
    local rankButton=view.frame.pools[tree][node.id]
    assert(rankButton.rank.text=="1/"..node.maxRank)
    rankButton.scripts.OnEnter(rankButton)
    assert(GameTooltip.title==ET.LocalizedField(node,"name"))
    assert(GameTooltip.lines[1]==string.format(ET.L["Rank %d/%d"],1,node.maxRank))
    rankButton.scripts.OnClick(rankButton)
    assert(suppressed() and view.frame:IsShown())
  end
end
-- Mixed party targets discard a late reply for the previously inspected GUID.
selected="Otherbot"; button.doLeft(button)
assert(ET.inspect.current==UnitGUID("party2") and MultiBot.talent.name=="Otherbot")
local before=calls; MultiBot.talent.setTalents()
assert(calls==before and ET.inspect.current==UnitGUID("party2"),"a delayed retry cannot reopen the previous bot")
ET.OnAddonMsg("ERATAL",packets[1][3]); assert(ET.inspect.cache[UnitGUID("party1")]==nil)
selected="Altbot"; close(); button.doLeft(button)
for _,record in ipairs(packets) do if record[1]=="0" and record[2]=="5" then ET.OnAddonMsg("ERATAL",record[3]) end end
assert(ET.inspectView.frame:IsShown())
-- MPQ generation mismatch or missing data suppresses both trees, never an incorrect fallback.
ET.CheckGeneration("ffffffff")
assert(suppressed() and not ET.inspectView.frame:IsShown() and ET.inspectStatus:IsShown())
GetSpellInfo=function() return nil end; ET.CheckGeneration("a1b2c3d4")
assert(suppressed() and not ET.inspectView.frame:IsShown())
GetSpellInfo=function(id) if id==932999 then return "EraTalents Gen a1b2c3d4" end end
ET.CheckGeneration("a1b2c3d4"); assert(ET.inspectView.frame:IsShown())
local saved=EraTalentsData[0][5]; EraTalentsData[0][5]=nil; ET.RefreshInspect()
assert(suppressed() and not ET.inspectView.frame:IsShown())
EraTalentsData[0][5]=saved; ET.RefreshInspect(); assert(ET.inspectView.frame:IsShown())
ET.inspect.cache[UnitGUID("party1")].ranks[999999]=1; ET.RefreshInspect()
assert(suppressed() and not ET.inspectView.frame:IsShown(),"unknown server nodes require matching addon data")
ET.inspect.cache[UnitGUID("party1")].ranks[999999]=nil
ET.inspect.cache[UnitGUID("party1")].ranks[saved.talents[1].id]=saved.talents[1].maxRank+1
ET.RefreshInspect(); assert(suppressed() and not ET.inspectView.frame:IsShown(),"rank limits validate matching client structure")
-- The button toggles the stock inspect frame; closing wipes state and restores stock children.
button.doLeft(button)
assert(not InspectFrame:IsShown() and ET.inspect.current==nil and next(ET.inspect.cache)==nil and not suppressed())
local closedCalls=calls
MultiBot.talent.setTalents()
assert(not InspectFrame:IsShown() and calls==closedCalls,"a stale retry must not reopen closed inspection")
-- A realm without EraTalents never answers HELLO with GEN. Inside the reply window a bot
-- request still waits; afterwards the stock tree and MultiBot's own talent window return.
local now=100
GetTime=function() return now end
ET.state.serverGen=nil; ET.state.clientGen=nil
ET.RequestSync(); assert(sent[#sent]=="HELLO")
button.doLeft(button)
assert(InspectFrame:IsShown() and suppressed() and ET.inspectStatus:IsShown(),"a reply inside the window is still awaited")
now=now+6; ET.RefreshInspect()
assert(not suppressed() and not ET.inspectStatus:IsShown(),"a silent server restores the stock inspect tree")
close()
assert(not ET.OpenBotInspect("party1",true) and not InspectFrame:IsShown(),"bot inspection without a server stays native")
local rendered=0
MultiBot.talent.renderTalentBuild=function() rendered=rendered+1 end
MultiBot.auto.talent=false; button.doLeft(button)
assert(InspectFrame:IsShown() and MultiBot.auto.talent and not suppressed(),"a realm without EraTalents keeps MultiBot's inspect path")
MultiBot.talent.setTalents()
assert(rendered==1,"a realm without EraTalents renders MultiBot's talent window")
close(); ET.CheckGeneration("a1b2c3d4")
allowed=false; assert(not ET.OpenBotInspect("party1",false)); assert(not ET.OpenBotInspect("missing",false))
print("MultiBot era talents: "..locale.." selected-character trees, native Wrath, read-only ranks, stale replies and client-data guards passed")
'''


def client_fixture(era: Path, bot: Path, packets: list[list[str]], directory: Path,
                   *, expect_failure: bool = False) -> None:
    every = (bot / 'Core/MultiBotEvery.lua').read_text()
    start = every.index('pFrame.addButton("Talent", 304')
    button = every[start:every.index('\n\t-- BOUTON SETTALENTS', start)]
    button = 'local pFrame={addButton=function() return button end}\n' + button
    frame = (bot / 'UI/MultiBotTalentFrame.lua').read_text()
    start = frame.index('    MultiBot.talent.setTalents = function()')
    setter = frame[start:frame.index('\n    function MultiBot.talent.updateTalentArrowState', start)]
    fixture = LUA_FIXTURE.replace('__BUTTON__', button).replace('__SET_TALENTS__', setter)
    # Lua 5.1 has no JSON parser; encode only native-produced string triplets.
    records = '{' + ','.join('{' + ','.join(json.dumps(value) for value in record) + '}'
                             for record in packets) + '}'
    lua = shutil.which('lua5.1') or shutil.which('lua')
    if not lua:
        raise RuntimeError('Lua 5.1 is required')
    for locale in ('enUS', 'deDE'):
        script = directory / ('inspect-' + locale + '.lua')
        script.write_text('local function fixture(...)\n' + fixture + '\nend\nfixture(' + ','.join((
            json.dumps(locale), json.dumps(str(era / 'client-addon/EraTalents') + '/'),
            json.dumps(str(bot) + '/'), records)) + ')\n')
        result = run_fixture([lua, str(script)])
        if expect_failure:
            if result.returncode == 0:
                raise AssertionError('Reverted production behavior unexpectedly passed')
            expected_errors = ('assertion failed', 'MultiBot must use authoritative inspect',
                               'must not reveal native Wrath talents',
                               'a stale retry must not reopen closed inspection',
                               'a silent server restores the stock inspect tree',
                               'bot inspection without a server stays native',
                               "a realm without EraTalents renders MultiBot's talent window")
            if not any(message in result.stderr for message in expected_errors):
                raise AssertionError('Mutation failed for an unrelated fixture error: ' + result.stderr)
        else:
            if result.returncode:
                match = re.search(r'\.lua:(\d+):', result.stderr)
                context = ''
                if match:
                    line = int(match.group(1))
                    context = '\n'.join(script.read_text().splitlines()[max(0,line-3):line+2])
                raise RuntimeError(result.stdout + result.stderr + '\n' + context)
            print(result.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--module-source', type=Path,
                        default=prepared_core(ROOT) / 'modules/mod-era-talents')
    parser.add_argument('--addon-source', type=Path,
                        default=ROOT / '.module-cache/prepared-addons/MultiBot')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='multibot-era-inspect-') as temporary:
        directory = Path(temporary)
        era, bot = directory / 'era', directory / 'bot'
        shutil.copytree(args.module_source / 'client-addon', era / 'client-addon')
        # Native sources are read directly; release/prepared sources are never edited.
        (bot / 'UI').mkdir(parents=True)
        (bot / 'Core').mkdir()
        for file in ('UI/MultiBotTalentFrame.lua', 'Core/MultiBotEvery.lua'):
            shutil.copyfile(args.addon_source / file, bot / file)
        for directory_, patch in ((era, ERA_PATCH), (bot, BOT_PATCH)):
            unpatched(directory_, patch)
            git_apply(directory_, patch)
        packets = native_fixture(args.module_source, directory)
        print('Native ISYNC: all authored classes, 19 earned tiers, mixed leader stages/levels, inspect gates and transition state passed')
        client_fixture(era, bot, packets, directory)
        inspect = era / 'client-addon/EraTalents/Inspect.lua'
        safe_inspect = inspect.read_text()
        guard = '''    if ET.state.clientGen ~= ET.state.serverGen then
      ShowStatus(L["Install the matching EraTalents client patch and restart the game."])
      return
    end
'''
        if guard not in safe_inspect:
            raise AssertionError('Expected production generation guard')
        inspect.write_text(safe_inspect.replace(guard, '', 1))
        client_fixture(era, bot, packets, directory, expect_failure=True)
        for silent_guard, replacement in (
                ('(ET.inspect.botTarget == guid and ET.ServesBotInspect())', 'ET.inspect.botTarget == guid'),
                ('  if not ET.ServesBotInspect() then return false end\n', '')):
            if silent_guard not in safe_inspect:
                raise AssertionError('Expected production server reply guard')
            inspect.write_text(safe_inspect.replace(silent_guard, replacement, 1))
            client_fixture(era, bot, packets, directory, expect_failure=True)
        inspect.write_text(safe_inspect)
        frame = bot / 'UI/MultiBotTalentFrame.lua'
        safe_frame = frame.read_text()
        retry_guard = '    if toggle == false then return true end\n'
        if retry_guard not in safe_frame:
            raise AssertionError('Expected production stale-retry guard')
        frame.write_text(safe_frame.replace(retry_guard, '', 1))
        client_fixture(era, bot, packets, directory, expect_failure=True)
        native_guard = '    if era.ServesBotInspect and not era.ServesBotInspect() then\n        return false\n    end\n'
        if native_guard not in safe_frame:
            raise AssertionError('Expected production native-realm fallback')
        frame.write_text(safe_frame.replace(native_guard, '', 1))
        client_fixture(era, bot, packets, directory, expect_failure=True)
        frame.write_text(safe_frame)
        git_apply(bot, BOT_PATCH, '--reverse')
        client_fixture(era, bot, packets, directory, expect_failure=True)
        git_apply(bot, BOT_PATCH)
        git_apply(era, ERA_PATCH, '--reverse')
        client_fixture(era, bot, packets, directory, expect_failure=True)
        print('Reverted MultiBot/EraTalents and unsafe generation/retry mutations all fail the regression fixture')


if __name__ == '__main__':
    main()
