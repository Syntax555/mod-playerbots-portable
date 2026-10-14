#!/usr/bin/env python3
"""Check that Raid Clear grants no aura, object state or cheat outside natural progression gates."""
import argparse
from pathlib import Path
import re
from FixtureSupport import function, prepared_core

# Calls that change the world for a bot instead of letting it play: free auras,
# forced object states, relocation, items, health, immunity and cheat masks.
SHORTCUTS = re.compile(r'\b(AddAura|SetGoState|TeleportTo|NearTeleportTo|AddItem|StoreNewItem|ModifyMoney|SetHealth|'
                       r'SetFullHealth|ResurrectPlayer|ApplySpellImmune|HasCheat|SetSpeed|DealDamage|Kill)\s*\(')
GATE = 'if (sPlayerbotAIConfig.naturalProgression)'
# Each reviewed shortcut and the function that must refuse it under natural progression.
REVIEWED = {
    ('Raids/BlackwingLair/BwlRaidClear.cpp', 'HasCheat'): 'bool MayDisarm(PlayerbotAI* botAI, Player* bot)',
    ('Raids/BlackwingLair/BwlRaidClear.cpp', 'SetGoState'): 'bool RcBwlDisarmSuppressionAction::Execute(',
    ('Raids/BlackwingLair/BwlRaidClear.cpp', 'AddAura'): 'void OnPlayerResurrect(',
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    source = args.source or prepared_core(repo)/'modules/mod-raid-clear/src'
    if not source.is_dir():
        raise SystemExit('PrepareModules.cmake must prepare mod-raid-clear first')
    found = set()
    for path in sorted(source.rglob('*.[ch]*')):
        relative = path.relative_to(source).as_posix()
        text = re.sub(r'//[^\n]*', '', path.read_text())
        for match in SHORTCUTS.finditer(text):
            key = (relative, match.group(1))
            if key not in REVIEWED:
                raise SystemExit(f'Unreviewed Raid Clear shortcut {match.group(1)} in {relative}')
            found.add(key)
    for (relative, call), signature in REVIEWED.items():
        if (relative, call) not in found:
            raise SystemExit(f'Reviewed Raid Clear shortcut disappeared; update this audit: {call} in {relative}')
        body = function((source/relative).read_text(), signature)
        gate = body.find(GATE)
        if gate < 0 or gate > body.find(call + '('):
            raise SystemExit(f'{call} in {signature} is not refused under natural progression')
    profile = (repo/'cmd/startup/profiles/playerbots.conf').read_text()
    if not re.search(r'^AiPlayerbot\.ApplyInstanceStrategies\s*=\s*1\s*$', profile, re.M):
        raise SystemExit('Raid Clear needs playerbots instance strategies enabled in the portable profile')
    print('Raid Clear earned play: cheat-mask disarm, forced device states and free cloak auras gated; '
          'no other world shortcuts present')


if __name__ == '__main__':
    main()
