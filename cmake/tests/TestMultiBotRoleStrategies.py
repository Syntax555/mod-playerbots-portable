"""Exercise MultiBot role state and bridge toggles against native strategy names."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from FixtureSupport import (
    cxx,
    function,
    git_apply,
    multibot_sources,
    prepared_core,
    source_argument,
    unpatched,
)


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'patches/multibot-role-strategies.patch'
# Class, button, native strategy class, canonical name, previous alias.
ROLES = (
    ('Paladin', 'Heal', 'HealPaladinStrategy', 'holy', 'heal'),
    ('Paladin', 'Dps', 'DpsPaladinStrategy', 'ret', 'dps'),
    ('Paladin', 'Tank', 'TankPaladinStrategy', 'prot', 'tank'),
    ('Priest', 'Heal', 'DiscPriestStrategy', 'disc', 'heal'),
    ('Warrior', 'Tank', 'TankWarriorStrategy', 'prot', 'tank'),
)
FILES = ('Core/MultiBotEngine.lua', 'Core/MultiBotComm.lua') + tuple(
    f'Strategies/MultiBot{name}.lua' for name in ('Paladin', 'Priest', 'Warrior'))

FIXTURE = r'''
local addon, roles = ...
MultiBot = {L=function(key) return key end}
UnitName=function(unit) return unit == "player" and "Owner" or "Altbot" end
GetTime=function() return 10 end
SendChatMessage=function() error("role toggles must use the bridge") end
DEFAULT_CHAT_FRAME={AddMessage=function() end}
dofile(addon .. "/Core/MultiBotEngine.lua")
dofile(addon .. "/Core/MultiBotComm.lua")
for _, cls in ipairs({"Paladin", "Priest", "Warrior"}) do
    dofile(addon .. "/Strategies/MultiBot" .. cls .. ".lua")
end
local sent={}
MultiBot.Comm.Send=function(opcode, payload)
    assert(opcode == "RUN")
    sent[#sent+1]=payload
    return true
end
local bridge=MultiBot.bridge
bridge.connected=true
bridge.strategyMutationCapable=true
bridge.selfBotCapable=true
bridge.selfStrategyCapable=true
bridge.selfBotLastActive=true

local function build(cls, name, combat)
    local buttons={}
    local function frame()
        local f={buttons={},frames={}}
        f.Hide=function() end
        f.getName=function() return name end
        f.getButton=function(key) assert(buttons[key], key); return buttons[key] end
        f.addFrame=function(key)
            local child=frame()
            f.frames[key]=child
            return child
        end
        f.addButton=function(key)
            local b={state=false,parent=f,getName=f.getName,getButton=f.getButton}
            b.setDisable=function() b.state=false; return b end
            b.setEnable=function() b.state=true; return b end
            b.setTexture=function() return b end
            buttons[key]=b
            f.buttons[key]=b
            return b
        end
        return f
    end
    local f=frame()
    MultiBot["add" .. cls](f, combat, "")
    return buttons
end

for _, role in ipairs(roles) do
    local cls, key, strategy=unpack(role)
    for _, target in ipairs({"Altbot", "Owner"}) do
        for _, active in ipairs({false, true}) do
            -- Native Engine::ListStrategies/GetStrategies expose getName(),
            -- and the bridge carries those canonical names unchanged.
            local buttons=build(cls, target, active and (strategy .. ", tank assist") or "tank assist")
            local button=buttons[key]
            assert(button.state == active, cls .. ": incorrect " .. strategy .. " state")
            bridge.strategyMutationCommands={}
            bridge.selfStrategyCommands={}
            local previous=#sent
            button.doLeft(button)
            assert(#sent == previous+1, cls .. ": toggle was not sent")
            local commands=target == "Owner" and bridge.selfStrategyCommands or bridge.strategyMutationCommands
            local _, command=next(commands)
            assert(command and command.stateScope == "C")
            assert(command.changes == (active and "-" or "+") .. strategy,
                   cls .. ": wrong role mutation: " .. tostring(command and command.changes))
            if target == "Owner" then
                assert(next(bridge.strategyMutationCommands) == nil, "SelfBot used ordinary bot routing")
            else
                assert(command.scope == "BOT" and command.target == target)
            end
            assert(button.state == active, "queued toggle changed state before authoritative refresh")
        end
    end
end
'''


def native_strategy_names(module, directory):
    """Compile the real producer methods instead of inventing server state tokens."""
    code = '#include <iostream>\n#include <string>\n'
    for cls, _, strategy, _, _ in ROLES:
        header = (module / f'Ai/Class/{cls}/Strategy/{strategy}.h').read_text()
        method = function(header, 'std::string const getName()').replace(' override', '')
        code += f'struct {strategy} {{ {method} }};\n'
    code += 'int main() {\n'
    for _, _, strategy, _, _ in ROLES:
        code += f' std::cout << {strategy}().getName() << "\\n";\n'
    code += '}\n'
    source, binary = directory / 'native.cpp', directory / 'native'
    source.write_text(code)
    subprocess.run([cxx(), '-std=c++20', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)], check=True)
    names = subprocess.run([str(binary)], check=True, text=True, capture_output=True, timeout=20).stdout.splitlines()
    assert names == [role[3] for role in ROLES], 'Playerbots canonical role names changed'


def run_lua(lua, directory):
    roles = '{{' + '},{'.join(','.join(json.dumps(value) for value in (cls, button, name))
                            for cls, button, _, name, _ in ROLES) + '}}'
    script = 'local addon, roles = ' + json.dumps(str(directory)) + ', ' + roles + '\n'
    script += FIXTURE.replace('local addon, roles = ...\n', '', 1)
    return subprocess.run([lua, '-'], input=script, text=True, capture_output=True, timeout=20, check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--addon-source', type=Path, help='pinned pristine or prepared MultiBot source')
    source_argument(parser, help='prepared Playerbots src directory')
    parser.add_argument('--lua', default=shutil.which('lua5.1') or shutil.which('lua'), help='Lua 5.1 executable')
    args = parser.parse_args()
    if not args.lua:
        parser.error('Lua 5.1 is required')
    module = args.source or prepared_core() / 'modules/mod-playerbots/src'
    with tempfile.TemporaryDirectory(prefix='multibot-roles-') as temporary:
        directory = Path(temporary)
        native_strategy_names(module, directory)
        multibot_sources(directory, FILES, args.addon_source)
        unpatched(directory, PATCH)
        assert run_lua(args.lua, directory).returncode != 0, 'original role-state regression was not rejected'
        git_apply(directory, PATCH)
        result = run_lua(args.lua, directory)
        assert result.returncode == 0, result.stdout + result.stderr
        for cls, button, _, strategy, alias in ROLES:
            path = directory / f'Strategies/MultiBot{cls}.lua'
            original = path.read_text()
            for label, old, new in (
                ('enable', f'"co +{strategy},?"', f'"co +{alias},?"'),
                ('disable', f'"co -{strategy},?"', f'"co -{alias},?"'),
                ('state', f'hasStrategy(pCombat, "{strategy}")', f'hasStrategy(pCombat, "{alias}")'),
            ):
                assert old in original, f'{cls} {button} {label} mutation was not applied'
                path.write_text(original.replace(old, new))
                assert run_lua(args.lua, directory).returncode != 0, f'{cls} {button} {label} mutant survived'
                path.write_text(original)
                print(f'MultiBot roles mutation rejected: {cls} {button} {label}')
    print('MultiBot roles: 5 native names, bot/SelfBot enable/disable and 15 mutations passed')


if __name__ == '__main__':
    main()
