"""Check the release's EraTalents core patches against the pinned module.

mod-era-talents carries its combat hooks as patches/core. PrepareModules
applies core patches before it fetches modules, so the release lists copies as
ordered core patches. Each copy must keep the module's hunks, and the marker
auras and spell band it hard-codes must still be the module's.
"""

import argparse
import json
from pathlib import Path
import re

from PreparedSources import prepared_core


# Module patch -> release copy. A new module core patch fails until it is mapped.
COPIES = {
    '01-shatter-crit-vs-frozen.patch': 'patches/azerothcore-era-shatter.patch',
    '02-corruption-era-casttime.patch': 'patches/azerothcore-era-corruption.patch',
    '03-hotw-era-bear-stamina.patch': 'patches/azerothcore-era-heart-of-the-wild.patch',
    '04-sentry-era-unsummon.patch': 'patches/azerothcore-era-sentry-totem.patch',
    '05-wand-spec-era-no-spell-leak.patch': 'patches/azerothcore-era-wand-specialization.patch',
    '06-molten-fury-era-window.patch': 'patches/azerothcore-era-molten-fury.patch',
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


def problems(copies: dict[str, str], originals: dict[str, str], allowed: list[tuple[int, int]],
             band: tuple[int, int]) -> list[str]:
    found = []
    for module_name, copy_name in COPIES.items():
        if hunks(copies[copy_name]) != hunks(originals[module_name]):
            found.append(f'{copy_name} differs from mod-era-talents patches/core/{module_name}')
        for marker in sorted(markers(copies[copy_name])):
            if marker in band:
                continue
            if not band[0] <= marker < band[1] or not any(lo <= marker <= hi for lo, hi in allowed):
                found.append(f'{copy_name} uses {marker}, which the module no longer allows')
    return found


repository = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--module', type=Path, default=prepared_core(repository) / 'modules/mod-era-talents',
                    help='prepared mod-era-talents directory')
args = parser.parse_args()
lock = json.loads((repository / 'versions.lock.json').read_text())

core_patches = lock['core']['patches']
module_patches = next(module for module in lock['modules'] if module['name'] == 'mod-era-talents')['patches']
# The prepared module's patches/core is the pinned one: no release patch edits it.
for name in module_patches:
    assert not re.search(r'^diff --git a/patches/core/', (repository / name).read_text(), re.MULTILINE), name
originals = {path.name: path.read_text() for path in sorted((args.module / 'patches/core').glob('*.patch'))}
assert set(originals) == set(COPIES), sorted(set(originals) ^ set(COPIES))
assert all(copy in core_patches for copy in COPIES.values())
copies = {copy: (repository / copy).read_text() for copy in COPIES.values()}

header = (args.module / 'src/EraTalents.h').read_text()
band = tuple(int(re.search(rf'constexpr uint32 ERA_CUSTOM_BAND_{edge} = (\d+);', header).group(1))
             for edge in ('LOW', 'HIGH'))
allowlist = (args.module / 'src/EraBandAllowlist.gen.h').read_text()
allowed = [(int(lo), int(hi)) for lo, hi in re.findall(r'^\s*\{ (\d+), (\d+), 0x', allowlist, re.MULTILINE)]
count = int(re.search(r'kEraBandAllowlistCount = (\d+);', allowlist).group(1))
assert len(allowed) == count, (len(allowed), count)

errors = problems(copies, originals, allowed, band)
assert not errors, errors
used = set().union(*(markers(text) for text in copies.values()))
assert set(band) <= used and len(used - set(band)) >= 4, used

# The comparison itself must notice drift in a hunk body and a dropped marker.
sample = COPIES['02-corruption-era-casttime.patch']
changed = dict(copies, **{sample: copies[sample].replace('{ 172, 2000 }', '{ 172, 1500 }', 1)})
assert changed[sample] != copies[sample] and problems(changed, originals, allowed, band)
assert problems(copies, originals, [entry for entry in allowed if not entry[0] <= 932930 <= entry[1]], band)
print(f'EraTalents core patches: {len(COPIES)} release copies match the pinned module; '
      f'markers {sorted(used - set(band))} are allowlisted in band {band[0]}..{band[1]}')
