"""Check that Raid Clear grants no aura, object state or cheat outside natural progression gates."""
import argparse
from pathlib import Path
import re

from FixtureSupport import REPOSITORY, function, prepared_core


# Calls that change the world for a bot instead of letting it play: free auras,
# forced object states, relocation, items, health, immunity and cheat masks.
SHORTCUTS = re.compile(r'\b(AddAura|SetGoState|TeleportTo|NearTeleportTo|AddItem|StoreNewItem|ModifyMoney|SetHealth|'
                       r'SetFullHealth|ResurrectPlayer|ApplySpellImmune|HasCheat|SetSpeed|DealDamage|Kill)\s*\(')
# The refusal leaves the function before the shortcut can run.
GATE = re.compile(r'if \(sPlayerbotAIConfig\.naturalProgression\)\s*return\b')
BWL = 'Raids/BlackwingLair/BwlRaidClear.cpp'
# Each reviewed shortcut and the function that must refuse it under natural progression.
REVIEWED = {
    (BWL, 'HasCheat'): 'bool MayDisarm(PlayerbotAI* botAI, Player* bot)',
    (BWL, 'SetGoState'): 'bool RcBwlDisarmSuppressionAction::Execute(',
    (BWL, 'AddAura'): 'void OnPlayerResurrect(',
}
# Each mutation adds an unreviewed shortcut or turns a refusal into a no-op.
MUTATIONS = (
    ('ungated aura next to a reviewed one', BWL, 'bool RcBwlSuppressionDeviceTrigger::IsActive()\n{\n',
     'bool RcBwlSuppressionDeviceTrigger::IsActive()\n{\n    bot->AddAura(12345, bot);\n'),
    ('cloak refusal that only logs', BWL, 'if (sPlayerbotAIConfig.naturalProgression)\n            return;',
     'if (sPlayerbotAIConfig.naturalProgression)\n            LOG_DEBUG("module", "natural progression");'),
    ('device state change without a refusal', BWL,
     '    if (sPlayerbotAIConfig.naturalProgression)\n        return false;\n    std::list<GameObject*> armed;',
     '    std::list<GameObject*> armed;'),
)


def audit(sources):
    """The first problem in Raid Clear's {relative path: source}, or None."""
    found = set()
    for relative, text in sorted(sources.items()):
        text = re.sub(r'//[^\n]*', '', text)
        for match in SHORTCUTS.finditer(text):
            call = match.group(1)
            signature = REVIEWED.get((relative, call))
            start = text.find(signature) if signature else -1
            if start < 0 or not start <= match.start() < start + len(function(text, signature)):
                return f'Unreviewed Raid Clear shortcut {call} in {relative}'
            found.add((relative, call))
    for (relative, call), signature in REVIEWED.items():
        if (relative, call) not in found:
            return f'Reviewed Raid Clear shortcut disappeared; update this audit: {call} in {relative}'
        body = function(re.sub(r'//[^\n]*', '', sources[relative]), signature)
        gate = GATE.search(body)
        if not gate or gate.start() > body.find(call + '('):
            return f'{call} in {signature} is not refused under natural progression'
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, help='mod-raid-clear/src to check instead of the prepared one')
    args = parser.parse_args()
    source = args.source or prepared_core() / 'modules/mod-raid-clear/src'
    if not source.is_dir():
        raise SystemExit('PrepareModules.cmake must prepare mod-raid-clear first')
    sources = {path.relative_to(source).as_posix(): path.read_text() for path in source.rglob('*.[ch]*')}
    problem = audit(sources)
    if problem:
        raise SystemExit(problem)
    for label, relative, old, new in MUTATIONS:
        if sources[relative].count(old) != 1:
            raise SystemExit(f'{label} mutation was not applied')
        if not audit({**sources, relative: sources[relative].replace(old, new)}):
            raise SystemExit(f'Raid Clear audit did not reject the {label} mutation')
    profile = (REPOSITORY / 'cmd/startup/profiles/playerbots.conf').read_text()
    if not re.search(r'^AiPlayerbot\.ApplyInstanceStrategies\s*=\s*1\s*$', profile, re.MULTILINE):
        raise SystemExit('Raid Clear needs playerbots instance strategies enabled in the portable profile')
    print('Raid Clear earned play: cheat-mask disarm, forced device states and free cloak auras refused before '
          'they run; no other world shortcuts present and every audit mutation rejected')


if __name__ == '__main__':
    main()
