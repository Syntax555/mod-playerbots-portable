"""Run the pinned MultiBot combat-profile selector and its authority mutations."""

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

from FixtureSupport import fork_change, git_apply, multibot_sources


FILES = (
    'Core/MultiBotLocale.lua', 'Core/MultiBotComm.lua', 'UI/MultiBotSpecUI.lua',
    'Locales/MultiBotAceLocale-enUS.lua', 'Locales/MultiBotAceLocale-deDE.lua',
    'tests/test_combat_profiles.lua',
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--addon-source', type=Path)
    parser.add_argument('--lua', default=shutil.which('lua5.1') or shutil.which('lua'))
    parser.add_argument('--no-fork-reversion', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.lua:
        parser.error('Lua 5.1 is required')
    with tempfile.TemporaryDirectory(prefix='multibot-combat-profiles-') as temporary:
        addon = Path(temporary)
        multibot_sources(addon, FILES, args.addon_source)
        command = [args.lua, str(addon / 'tests/test_combat_profiles.lua'), str(addon)]
        subprocess.run(command, check=True, timeout=30)
        if args.no_fork_reversion:
            return
        patch = fork_change('MultiBot', 'multibot-combat-profiles', paths=FILES[:-1])
        git_apply(addon, patch, '--reverse')
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
        assert result.returncode != 0, 'Reverted combat-profile fork change survived the selector fixture'
        assert 'test_combat_profiles.lua:' in result.stderr, result.stderr
        git_apply(addon, patch)
        subprocess.run(command, check=True, timeout=30)
        print('MultiBot combat-profile fork change is covered by the real selector fixture')


if __name__ == '__main__':
    main()
