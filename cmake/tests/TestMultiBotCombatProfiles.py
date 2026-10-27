"""Run the pinned MultiBot combat-profile selector and its authority mutations."""

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

from FixtureSupport import (
    fork_change,
    function,
    git_apply,
    multibot_sources,
    prepared_core,
)


FILES = (
    'Core/MultiBotLocale.lua', 'Core/MultiBotComm.lua', 'UI/MultiBotSpecUI.lua',
    'Locales/MultiBotAceLocale-enUS.lua', 'Locales/MultiBotAceLocale-deDE.lua',
    'Core/MultiBotEvery.lua', 'Core/MultiBotEngine.lua',
    *(f'Strategies/MultiBot{cls}.lua' for cls in (
        'Warrior', 'Paladin', 'Hunter', 'Rogue', 'Priest', 'DeathKnight',
        'Shaman', 'Mage', 'Warlock', 'Druid',
    )),
    'tests/test_combat_profiles.lua',
)


def native_rogue_state_contract() -> None:
    modules = prepared_core() / 'modules'
    playerbots = modules / 'mod-playerbots/src'
    for strategy, name in (('CombatRogueStrategy', 'combat'), ('AssassinationRogueStrategy', 'assassin')):
        header = (playerbots / f'Ai/Class/Rogue/Strategy/{strategy}.h').read_text()
        assert function(header, 'std::string const getName()').endswith(f'{{ return "{name}"; }}')
    engine = (playerbots / 'Bot/Engine/Engine.cpp').read_text()
    assert 'strategies[strategy->getName()] = strategy;' in function(engine, 'void Engine::addStrategy(')
    bridge = (modules / 'mod-multibot-bridge/src/MultiBotBridge.cpp').read_text()
    state = function(bridge, 'bool AppendStateFramesForBot(')
    assert 'combatStrategies = botAI->GetStrategies(BOT_STATE_COMBAT);' in state
    assert 'UrlEncodeField(combatStrategies[index])' in state
    assert 'AppendStateFramesForBot(packets, token, player, reason)' in function(
        bridge, 'void SendSelfStrategyStatePacket(')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--addon-source', type=Path)
    parser.add_argument('--lua', default=shutil.which('lua5.1') or shutil.which('lua'))
    parser.add_argument('--no-fork-reversion', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.lua:
        parser.error('Lua 5.1 is required')
    native_rogue_state_contract()
    with tempfile.TemporaryDirectory(prefix='multibot-combat-profiles-') as temporary:
        addon = Path(temporary)
        multibot_sources(addon, FILES, args.addon_source)
        command = [args.lua, str(addon / 'tests/test_combat_profiles.lua'), str(addon)]
        subprocess.run(command, check=True, timeout=30)
        if args.no_fork_reversion:
            return
        classes = fork_change('MultiBot', 'multibot-class-profile-state', paths=FILES[:-1])
        git_apply(addon, classes, '--reverse')
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
        assert result.returncode != 0, 'Reverted Priest strategy state survived the selector fixture'
        assert 'Priest: native profile state did not select Dps' in result.stderr, result.stderr
        git_apply(addon, classes)
        rogue = fork_change('MultiBot', 'multibot-rogue-strategy-state', paths=FILES[:-1])
        git_apply(addon, rogue, '--reverse')
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
        assert result.returncode != 0, 'Reverted Rogue strategy state survived the selector fixture'
        assert 'Rogue native rotation did not select DPS' in result.stderr, result.stderr
        git_apply(addon, rogue)
        controls = fork_change('MultiBot', 'multibot-control-ownership', paths=FILES[:-1])
        git_apply(addon, controls, '--reverse')
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
        assert result.returncode != 0, 'Reverted control ownership survived the selector fixture'
        assert 'SelfBot toolbar has no combat-profile selector' in result.stderr, result.stderr
        patch = fork_change('MultiBot', 'multibot-combat-profiles', paths=tuple(path for path in FILES[:-1] if path != 'Core/MultiBotEvery.lua'))
        git_apply(addon, patch, '--reverse')
        git_apply(addon, controls)
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
        assert result.returncode != 0, 'Reverted combat-profile fork change survived the selector fixture'
        assert 'test_combat_profiles.lua:' in result.stderr, result.stderr
        git_apply(addon, controls, '--reverse')
        git_apply(addon, patch)
        git_apply(addon, controls)
        subprocess.run(command, check=True, timeout=30)
        print('MultiBot combat-profile fork change is covered by the real selector fixture')


if __name__ == '__main__':
    main()
