"""Check generated EraTalents trees and server rows against their dataset sources.

The prepared module's dataset YAML, band allowlist and locale catalogs are the inputs;
its addon Lua, era_talent SQL and generation stamp ship as generated files. A source
edit without regeneration would ship a stale addon tree or server rows while the
in-game generation check still matches. Custom spell rows also need the client
Spell.dbc and are rebuilt by the client packaging job.
"""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from PreparedSources import prepared_core


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module-source', type=Path,
                        default=prepared_core(Path(__file__).resolve().parents[2]) / 'modules/mod-era-talents')
    parser.add_argument('--no-mutations', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    module = args.module_source.resolve()
    outputs = generated(module)
    drift = [str(path.relative_to(module)) for path, text in outputs.items()
             if not path.is_file() or path.read_text() != text]
    for path in drift:
        print(f'Stale generated EraTalents file: {path}')
    if drift:
        return 1
    print(f'Era generated artifacts: {len(outputs)} addon tree, era_talent row and generation stamp '
          'files match their dataset and locale sources')
    if args.no_mutations:
        return 0

    with tempfile.TemporaryDirectory(prefix='era-generated-') as temporary:
        for label, source, old, new, expected in (
                ('German catalog entry', 'era-data/locales/deDE/mage.json', '"Arkaner Fokus"',
                 '"Arkaner Fokus X"', 'MageVanilla.lua'),
                ('dataset tooltip', 'era-data/vanilla/warrior.yaml',
                 'Heroic Strike ability by 1 rage point.', 'Heroic Strike ability by 4 rage point.',
                 'WarriorVanilla.lua')):
            copy = Path(temporary) / label.replace(' ', '-')
            for part in ('tools', 'era-data', 'client-addon/EraTalents/data', 'data/sql/world/base'):
                shutil.copytree(module / part, copy / part, ignore=shutil.ignore_patterns('__pycache__'))
            text = (copy / source).read_text()
            if old not in text:
                raise SystemExit(f'{label} mutation was not applied')
            (copy / source).write_text(text.replace(old, new, 1))
            result = subprocess.run([sys.executable, __file__, '--module-source', str(copy), '--no-mutations'],
                                    capture_output=True, text=True, check=False)
            if result.returncode == 0 or expected not in result.stdout or META_SQL not in result.stdout:
                raise SystemExit(f'A changed {label} was not reported as stale generated output:\n'
                                 + result.stdout + result.stderr)
            print(f'Era generated artifact mutation rejected: {label}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
