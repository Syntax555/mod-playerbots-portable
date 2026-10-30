"""Check generated EraTalents trees and server rows against their dataset sources.

The prepared module's dataset YAML, band allowlist and locale catalogs are the inputs;
its addon Lua, era_talent SQL and generation stamp ship as generated files. A source
edit without regeneration would ship a stale addon tree or server rows while the
in-game generation check still matches. Custom spell rows also need the client
Spell.dbc and are rebuilt by the client packaging job. A spell-hit talent's
explicit spell-modifier mask must bind every spell it names.
"""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from FixtureSupport import fork_change, git_apply, prepared_core


META_SQL = 'data/sql/world/base/2026_08_14_11_era_talent_meta.sql'


def generated(module: Path) -> dict[Path, str]:
    sys.dont_write_bytecode = True   # leave the prepared sources untouched
    sys.path.insert(0, str(module / 'tools'))
    import gen_era_talents as generator

    outputs, datasets = {}, []
    for line in (module / 'era-data/datasets.txt').read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        relative, data_sql, _custom_sql = line.split()
        dataset = module / 'era-data' / relative
        datasets.append(str(dataset))
        data = generator._load(str(dataset))
        generator.lint(data)
        era = 'TBC' if dataset.parent.name == 'tbc' else dataset.parent.name.capitalize()
        lua = f'client-addon/EraTalents/data/generated/{dataset.stem.capitalize()}{era}.lua'
        outputs[module / lua] = generator.emit_lua(data)
        outputs[module / 'data/sql/world/base' / data_sql] = generator.emit_sql(data)
    if len(datasets) < 18:
        raise SystemExit(f'Only {len(datasets)} era datasets are listed')
    outputs[module / META_SQL] = generator.emit_meta_sql(datasets)
    return outputs


def spell_hit_gaps(module: Path) -> list[str]:
    """Spells a spell-hit talent names that its explicit modifier mask leaves out.

    The core applies a modifier when one family-flag word overlaps the cast spell's.
    """
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(module / 'tools'))
    import gen_era_talents as generator

    gaps = []

    def walk(node, dataset, data, talent=None):
        if isinstance(node, dict):
            if {'tab', 'name', 'maxRank'} <= node.keys():
                talent = node['name']
            if node.get('op') == 'resistMiss' and node.get('affectsMask') is not None:
                mask = generator._resolve_affects_mask(data, node)
                for name in node.get('affects') or ():
                    flags = data['_ref']['spells'][name]
                    identity = (flags.get('flagsA', 0), flags.get('flagsB', 0), flags.get('flagsC', 0))
                    if not any(word & int(bits) for word, bits in zip(mask, identity)):
                        gaps.append(f'{dataset}: {talent} leaves out {name}')
            for value in node.values():
                walk(value, dataset, data, talent)
        elif isinstance(node, list):
            for value in node:
                walk(value, dataset, data, talent)

    for line in (module / 'era-data/datasets.txt').read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            relative = line.split()[0]
            data = generator._load(str(module / 'era-data' / relative))
            walk(data['tabs'], relative, data)
    return gaps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module-source', type=Path)
    parser.add_argument('--no-mutations', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    module = (args.module_source or prepared_core(Path(__file__).resolve().parents[2])
              / 'modules/mod-era-talents').resolve()
    outputs = generated(module)
    drift = [str(path.relative_to(module)) for path, text in outputs.items()
             if not path.is_file() or path.read_text() != text]
    for path in drift:
        print(f'Stale generated EraTalents file: {path}')
    if drift:
        return 1
    builds = subprocess.run([sys.executable, str(module / 'tools/gen_bot_builds.py'), '--check'],
                            capture_output=True, text=True, check=False)
    if builds.returncode:
        print(builds.stdout + builds.stderr, end='')
        return 1
    gaps = spell_hit_gaps(module)
    for gap in gaps:
        print(f'Spell-hit talent mask gap: {gap}')
    if gaps:
        return 1
    print(f'Era generated artifacts: {len(outputs)} addon tree, era_talent row and generation stamp '
          'files and authored bot orders match their dataset and locale sources; spell-hit talent masks '
          'bind every named spell')
    if args.no_mutations:
        return 0

    with tempfile.TemporaryDirectory(prefix='era-generated-') as temporary:
        for label, source, old, new, expected in (
                ('German catalog entry', 'era-data/locales/deDE/mage.json', '"Arkaner Fokus"',
                 '"Arkaner Fokus X"', 'MageVanilla.lua'),
                ('dataset tooltip', 'era-data/vanilla/warrior.yaml',
                 'Heroic Strike ability by 1 rage point.', 'Heroic Strike ability by 4 rage point.',
                 'WarriorVanilla.lua'),
                ('authored bot order', 'src/EraTalentBots.cpp',
                 '{ { ERA_VANILLA, CLASS_WARRIOR, 0 }, { 18503,',
                 '{ { ERA_VANILLA, CLASS_WARRIOR, 0 }, { 18501,', 'EraTalentBots.cpp')):
            copy = Path(temporary) / label.replace(' ', '-')
            for part in ('tools', 'era-data', 'client-addon/EraTalents/data', 'data/sql/world/base', 'src'):
                shutil.copytree(module / part, copy / part, ignore=shutil.ignore_patterns('__pycache__'))
            text = (copy / source).read_text()
            if old not in text:
                raise SystemExit(f'{label} mutation was not applied')
            (copy / source).write_text(text.replace(old, new, 1))
            result = subprocess.run([sys.executable, __file__, '--module-source', str(copy), '--no-mutations'],
                                    capture_output=True, text=True, check=False)
            if (result.returncode == 0 or expected not in result.stdout
                    or (source != 'src/EraTalentBots.cpp' and META_SQL not in result.stdout)):
                raise SystemExit(f'A changed {label} was not reported as stale generated output:\n'
                                 + result.stdout + result.stderr)
            print(f'Era generated artifact mutation rejected: {label}')
        if args.module_source is None:
            patch = fork_change('mod-era-talents', 'mod-era-talents-combat-profiles',
                                paths=('src/EraTalentBots.cpp',))
            copy = Path(temporary) / 'fork-build-orders'
            for part in ('tools', 'era-data', 'src'):
                shutil.copytree(module / part, copy / part, ignore=shutil.ignore_patterns('__pycache__'))
            git_apply(copy, patch, '--reverse')
            command = [sys.executable, str(copy / 'tools/gen_bot_builds.py'), '--check']
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode == 0 or 'Stale kAuthoredOrders' not in result.stderr:
                raise SystemExit('Reverting the authored-build fork change did not fail its generator check:\n'
                                 + result.stdout + result.stderr)
            git_apply(copy, patch)
            subprocess.run(command, capture_output=True, text=True, check=True)
            print('Era authored-build fork change fails when reverted and passes when reapplied')

            mask_patch = fork_change('mod-era-talents', 'mod-era-talents-arcane-focus-mask',
                                     paths=('era-data/tbc/mage.yaml',))
            copy = Path(temporary) / 'fork-arcane-focus'
            shutil.copytree(module / 'tools', copy / 'tools', ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(module / 'era-data', copy / 'era-data')
            git_apply(copy, mask_patch, '--reverse')
            if 'tbc/mage.yaml: Arcane Focus leaves out Arcane Explosion' not in spell_hit_gaps(copy):
                raise SystemExit('Reverting the Arcane Focus mask fork change did not report its gap')
            git_apply(copy, mask_patch)
            if spell_hit_gaps(copy):
                raise SystemExit('Reapplying the Arcane Focus mask fork change left a spell-hit gap')
            print('Era Arcane Focus mask fork change fails when reverted and passes when reapplied')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
