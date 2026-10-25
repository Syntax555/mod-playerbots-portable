"""Exercise pinned MultiBot's spellbook against the bridge's SB_ITEM payload."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from FixtureSupport import git_apply, multibot_sources, prepared_core, unpatched


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/multibot-spellbook-items.patch"
SOURCE = None
LUA = None
FILES = ("Core/MultiBotComm.lua", "UI/MultiBotSpell.lua", "UI/MultiBotSpellBookFrame.lua")


def between(source, start, end):
    begin = source.index(start)
    return source[begin:source.index(end, begin)]


def bridge_item_fields():
    """The fields SendSpellbookSnapshot streams after the SB_ITEM opcode, in order."""
    bridge = (prepared_core(ROOT) / "modules/mod-multibot-bridge/src/MultiBotBridge.cpp").read_text()
    snapshot = between(bridge, "void SendSpellbookSnapshot(", "void SendBotSkillPackets(")
    payload = between(snapshot, "std::ostringstream payload;", 'SendAddonPacket(requester, replyType, "SB_ITEM"')
    return re.findall(r"<<\s*(?:kFieldSeparator\s*<<\s*)?([^;<]+?)\s*(?=<<|;)", payload)


def fixture(spell_source, frame_source, comm_path, body):
    # The real Comm dispatcher, spellbook collection and slot rendering run on
    # recording doubles for the client spell API and the overlay widgets.
    payload_methods = between(frame_source, "\tMultiBot.spellbook.beginPayload = function(self, botName)",
                              "\tfor i = 1, GetNumMacroIcons() do")
    return "\n".join((
        '''
MultiBot = {spells = {}, SpellBookUISettings = {}}
MultiBot.L = function(key) return key == "info.spellbook" and "Zauberbuch von NAME" or key end
MultiBot.IF = function(condition, yes, no) if condition then return yes end return no end
MultiBot.doReplace = function(text, key, value) return (text:gsub(key, value)) end
MultiBot.TimerAfter = function() end
SPELLBOOK = "Zauberbuch"
GetTime = function() return 10 end
UnitName = function() return "Owner" end
local known = {[585] = {"Smite", "Rank 1", "Spell_Holy_HolySmite"},
               [2050] = {"Lesser Heal", "Rank 1", "Spell_Holy_LesserHeal"},
               [139] = {"Renew", "Rank 1", "Spell_Holy_Renew"}}
GetSpellInfo = function(id) local s = known[id] if s then return s[1], s[2], s[3] end end
GetSpellLink = function(id) local s = known[id] if s then return "|Hspell:" .. id .. "|h[" .. s[1] .. "]|h" end end
local function widget()
    local w = {shown = false}
    w.Show = function(self) self.shown = true end
    w.Hide = function(self) self.shown = false end
    w.doShow = function() w.shown = true end
    w.doHide = function() w.shown = false end
    w.SetChecked = function(self, value) self.checked = value end
    return w
end
local overlay = {buttons = {["<"] = widget(), [">"] = widget()}, texts = {}}
for i = 1, 18 do
    local index = (i < 10 and "0" or "") .. i
    overlay.buttons["S" .. index] = widget()
    overlay.buttons["C" .. index] = widget()
    overlay.texts["T" .. index] = widget()
    overlay.texts["R" .. index] = widget()
end
overlay.setButton = function(key, texture, link) overlay.buttons[key].texture = texture end
overlay.setText = function(key, text) overlay.texts[key] = overlay.texts[key] or widget() overlay.texts[key].text = text end
MultiBot.spellbook = {spells = {}, index = 0, frames = {Overlay = overlay}, Show = function(self) self.shown = true end,
                      setTitle = function(self, title) self.title = title end}
''', spell_source, payload_methods,
        "dofile(" + json.dumps(str(comm_path)) + ")",
        '''
MultiBot.bridge.connected = true
MultiBot.Comm.Send = function() return true end
local function request(bot)
    assert(MultiBot.Comm.RequestSpellbook(bot))
    local token = MultiBot.bridge.spellbookActive.token
    assert(MultiBot.Comm.HandleAddonMessage("MBOT", "SB_BEGIN~" .. bot .. "~" .. token, "WHISPER", "Owner"))
    return token
end
local function item(bot, token, ...)
    assert(MultiBot.Comm.HandleAddonMessage("MBOT", table.concat({"SB_ITEM", bot, token, ...}, "~"), "WHISPER", "Owner"))
end
local function finish(bot, token)
    assert(MultiBot.Comm.HandleAddonMessage("MBOT", "SB_END~" .. bot .. "~" .. token, "WHISPER", "Owner"))
end
''', body))


class MultiBotSpellbookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="multibot-spellbook-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        multibot_sources(cls.directory, FILES, SOURCE)
        unpatched(cls.directory, PATCH)
        cls.pristine_comm = cls.directory / "pristine-MultiBotComm.lua"
        shutil.copyfile(cls.directory / FILES[0], cls.pristine_comm)
        git_apply(cls.directory, PATCH)
        cls.comm = cls.directory / FILES[0]
        cls.spell = (cls.directory / FILES[1]).read_text()
        cls.frame = (cls.directory / FILES[2]).read_text()

    def run_lua(self, body, comm=None):
        script = fixture(self.spell, self.frame, comm or self.comm, body)
        return subprocess.run([LUA, "-"], input=script, text=True, capture_output=True, timeout=20, check=False)

    def test_bridge_streams_spell_id_and_ignore_flag(self):
        self.assertEqual(bridge_item_fields(),
                         ["bot->GetName()", "requestToken", "entry.spellId", "(ignored ? 1 : 0)"])

    def test_bridge_items_fill_the_spellbook_with_the_skip_list_state(self):
        body = '''
local token = request("Mey")
item("Mey", token, 585, 0)
item("Mey", token, 2050, 1)
finish("Mey", token)
local book = MultiBot.spellbook
assert(book.index == 2, "every bridge item is a spell: " .. tostring(book.index))
assert(book.spells[1][1] == 585 and book.spells[2][1] == 2050)
assert(overlay.buttons.S01.shown and overlay.buttons.S02.shown and book.title == "Zauberbuch von Mey")
assert(MultiBot.spells.Mey[585] == true and overlay.buttons.C01.checked == true, "a used spell is checked")
assert(MultiBot.spells.Mey[2050] == false and overlay.buttons.C02.checked == false, "an ignored spell is unchecked")
'''
        result = self.run_lua(body)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        pristine = self.run_lua(body, self.pristine_comm)
        self.assertNotEqual(pristine.returncode, 0, "the unpatched dispatcher must drop four-field items")
        self.assertIn("every bridge item is a spell: 0", pristine.stderr)

    def test_ignore_state_is_required_for_the_checkboxes(self):
        text = self.comm.read_text()
        line = '        MultiBot.spells[name][spellId] = ignored ~= "1"\n'
        self.assertIn(line, text)
        mutated = self.directory / "mutated-MultiBotComm.lua"
        mutated.write_text(text.replace(line, ""))
        result = self.run_lua('''
local token = request("Mey")
item("Mey", token, 2050, 1)
assert(overlay.buttons.C01.checked == false, "an ignored spell is unchecked")
''', mutated)
        self.assertNotEqual(result.returncode, 0, "dropping the bridge's skip-list state must fail")
        self.assertIn("an ignored spell is unchecked", result.stderr)

    def test_three_field_items_and_other_requests_stay_compatible(self):
        result = self.run_lua('''
local token = request("Mey")
item("Mey", token, 139)
item("Mey", "stale", 585, 0)
item("Other", token, 2050, 0)
assert(MultiBot.spellbook.index == 1 and MultiBot.spells.Mey[139] == true, "a legacy item without a flag is used")
assert(MultiBot.spells.Mey[585] == nil and MultiBot.spells.Other == nil, "other requests are ignored")
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--addon-source", type=Path,
                        help="existing pinned MultiBot source; defaults to the pinned PrepareModules cache")
    parser.add_argument("--lua", default=shutil.which("lua5.1") or shutil.which("lua"),
                        help="Lua 5.1 executable")
    arguments, remaining = parser.parse_known_args()
    SOURCE = arguments.addon_source
    LUA = arguments.lua
    if not LUA:
        parser.error("Lua 5.1 is required")
    unittest.main(argv=[__file__, *remaining])
