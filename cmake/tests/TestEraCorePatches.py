"""Check the core fork's EraTalents changes against the pinned module.

mod-era-talents carries its combat hooks as patches/core. The core fork imports
each hook in a named commit. Each commit must keep the module's hunks, and the marker
auras and spell band it hard-codes must still be the module's.
"""

import argparse
import json
from pathlib import Path
import re
import subprocess

from FixtureSupport import fork_change, pinned_source, prepared_core, source_argument


# Module patch -> core fork change. A new module core patch fails until it is mapped.
CHANGES = {
    '01-shatter-crit-vs-frozen.patch': 'azerothcore-era-shatter',
    '02-corruption-era-casttime.patch': 'azerothcore-era-corruption',
    '03-hotw-era-bear-stamina.patch': 'azerothcore-era-heart-of-the-wild',
    '04-sentry-era-unsummon.patch': 'azerothcore-era-sentry-totem',
    '05-wand-spec-era-no-spell-leak.patch': 'azerothcore-era-wand-specialization',
    '06-molten-fury-era-window.patch': 'azerothcore-era-molten-fury',
}


def hunks(text: str) -> list[tuple[str, tuple[str, ...]]]:
    """Return (file, body) per hunk, without index lines or hunk positions."""
    result, path, body = [], None, None
    for line in text.replace('\r\n', '\n').splitlines():
        if line.startswith('diff --git '):
            path = line.split(' b/', 1)[1]
            body = None
        elif line.startswith('@@'):
            body = []
            result.append((path, body))
        elif body is not None and line[:1] in (' ', '+', '-', '\\') and not line.startswith(('+++', '---')):
            body.append(line)
    return [(name, tuple(lines)) for name, lines in result]


def markers(text: str) -> set[int]:
    """Era-band spell ids in the code a patch adds, ignoring comments."""
    code = []
    for line in text.splitlines():
        if line.startswith('+') and not line.startswith('+++'):
            code.append(re.sub(r'//.*', '', re.sub(r'/\*.*?\*/', '', line[1:])))
    return {int(value) for value in re.findall(r'\b9\d{5}\b', '\n'.join(code))}


def problems(changes: dict[str, str], originals: dict[str, str], allowed: list[tuple[int, int]],
             band: tuple[int, int]) -> list[str]:
    found = []
    for module_name, change in CHANGES.items():
        if hunks(changes[change]) != hunks(originals[module_name]):
            found.append(f'{change} differs from mod-era-talents patches/core/{module_name}')
        for marker in sorted(markers(changes[change])):
            if marker in band:
                continue
            if not band[0] <= marker < band[1] or not any(lo <= marker <= hi for lo, hi in allowed):
                found.append(f'{change} uses {marker}, which the module no longer allows')
    return found


repository = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
source_argument(parser, 'module', default=prepared_core(repository) / 'modules/mod-era-talents',
                    help='prepared mod-era-talents directory')
source_argument(parser, 'core', default=prepared_core(repository), help='prepared core directory')
args = parser.parse_args()
lock = json.loads((repository / 'versions.lock.json').read_text())

core_changes = lock['core']['forkChanges']
originals = {path.name: path.read_text() for path in sorted((args.module / 'patches/core').glob('*.patch'))}
assert set(originals) == set(CHANGES), sorted(set(originals) ^ set(CHANGES))
# The prepared module's patches/core is upstream's: no change of the fork edits it.
for name, text in originals.items():
    assert text == pinned_source('mod-era-talents', f'patches/core/{name}'), name
assert all(change in core_changes for change in CHANGES.values())
patches = {change: fork_change('azerothcore-wotlk', change) for change in CHANGES.values()}
changes = {change: patch.read_text() for change, patch in patches.items()}
# A historical commit alone cannot prove the prepared core still contains its hooks.
for patch in patches.values():
    subprocess.run(['git', 'apply', '--reverse', '--check', str(patch)], cwd=args.core,
                   check=True, capture_output=True)

header = (args.module / 'src/EraTalents.h').read_text()
band = tuple(int(re.search(rf'constexpr uint32 ERA_CUSTOM_BAND_{edge} = (\d+);', header).group(1))
             for edge in ('LOW', 'HIGH'))
allowlist = (args.module / 'src/EraBandAllowlist.gen.h').read_text()
allowed = [(int(lo), int(hi)) for lo, hi in re.findall(r'^\s*\{ (\d+), (\d+), 0x', allowlist, re.MULTILINE)]
count = int(re.search(r'kEraBandAllowlistCount = (\d+);', allowlist).group(1))
assert len(allowed) == count, (len(allowed), count)

errors = problems(changes, originals, allowed, band)
assert not errors, errors
used = set().union(*(markers(text) for text in changes.values()))
assert set(band) <= used and len(used - set(band)) >= 4, used

# The comparison itself must notice drift in a hunk body and a dropped marker.
sample = CHANGES['02-corruption-era-casttime.patch']
changed = dict(changes, **{sample: changes[sample].replace('{ 172, 2000 }', '{ 172, 1500 }', 1)})
assert changed[sample] != changes[sample] and problems(changed, originals, allowed, band)
assert problems(changes, originals, [entry for entry in allowed if not entry[0] <= 932930 <= entry[1]], band)
print(f'EraTalents core changes: {len(CHANGES)} fork commits match the pinned module; '
      f'markers {sorted(used - set(band))} are allowlisted in band {band[0]}..{band[1]}')
