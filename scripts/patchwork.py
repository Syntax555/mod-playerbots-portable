#!/usr/bin/env python3
"""Edit one pinned patch and regenerate it reproducibly.

  python3 scripts/patchwork.py open patches/<name>.patch
      Extract the pinned upstream revision of the core, module or addon that
      lists the patch in versions.lock.json, apply the preceding patches of its
      chain and commit them as tag 'base', then apply the target patch to the
      working tree. Prints the work tree; edit the sources there.

  python3 scripts/patchwork.py save <work tree>
      Regenerate the patch from the work tree and check that the complete
      patch chain still applies to a fresh extraction of the pinned revision.

Run 'cmake -P cmake/PrepareModules.cmake' first so the pinned sources exist.
Work trees live in .module-cache/patchwork and can be deleted afterwards.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def run(*args, capture=False, env=None):
    result = subprocess.run(args, check=True, text=True, env=env, stdout=subprocess.PIPE if capture else None)
    return result.stdout if capture else None


def repository():
    root = Path(run('git', 'rev-parse', '--show-toplevel', capture=True).strip())
    # A linked worktree has no prepared sources; use the main checkout's cache.
    common = Path(run('git', '-C', str(root), 'rev-parse', '--path-format=absolute', '--git-common-dir',
                      capture=True).strip())
    return root, common.parent


def lock_entry(root, patch):
    lock = json.loads((root / 'versions.lock.json').read_text())
    entries = [('core', lock['core'])] + [('module', module) for module in lock['modules']] + \
              [('addon', addon) for addon in lock.get('clientAddons', [])]
    for kind, entry in entries:
        if patch in entry.get('patches', []):
            return kind, entry
    raise SystemExit(f'{patch} is not listed in versions.lock.json')


def source_repository(main, kind, entry):
    if entry.get('source'):
        return main / entry['source']
    if kind == 'addon':
        return main / '.module-cache' / f"client-addon-{entry['name']}"
    return main / '.module-cache' / entry['name']


def extract(main, kind, entry, target):
    source = source_repository(main, kind, entry)
    if not (source / '.git').exists():
        raise SystemExit(f'Pinned source {source} is missing; run cmake -P cmake/PrepareModules.cmake first')
    target.mkdir(parents=True)
    archive = target / '.pinned.tar'
    run('git', '-C', str(source), 'archive', '--format=tar', f'--output={archive}', entry['revision'])
    run('tar', '-xf', str(archive), '-C', str(target))
    archive.unlink()


def apply(tree, patch_file):
    # Mirror PrepareModules: apply an LF copy outside any enclosing repository.
    contents = Path(patch_file).read_bytes().replace(b'\r\n', b'\n')
    with tempfile.NamedTemporaryFile(suffix='.patch', delete=False) as handle:
        handle.write(contents)
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(tree.parent))
    try:
        run('git', '-C', str(tree), 'apply', '--check', handle.name, env=env)
        run('git', '-C', str(tree), 'apply', handle.name, env=env)
    finally:
        os.unlink(handle.name)


def git(tree, *args, capture=False):
    return run('git', '-C', str(tree), '-c', 'user.name=patchwork', '-c', 'user.email=patchwork@localhost',
               *args, capture=capture)


def open_patch(patch):
    root, main = repository()
    kind, entry = lock_entry(root, patch)
    index = entry['patches'].index(patch)
    work = main / '.module-cache' / 'patchwork'
    work.mkdir(parents=True, exist_ok=True)
    tree = Path(tempfile.mkdtemp(prefix=f'{Path(patch).stem}-', dir=work))
    tree.rmdir()
    extract(main, kind, entry, tree)
    git(tree, 'init', '-q')
    git(tree, 'add', '-A')
    git(tree, 'commit', '-qm', 'pinned')
    for previous in entry['patches'][:index]:
        apply(tree, root / previous)
    git(tree, 'add', '-A')
    git(tree, 'commit', '-qm', 'base', '--allow-empty')
    git(tree, 'tag', 'base')
    apply(tree, root / patch)
    (tree / '.git' / 'patchwork.json').write_text(json.dumps({'repository': str(root), 'patch': patch}))
    print(tree)


def save(tree):
    tree = Path(tree).resolve()
    meta = json.loads((tree / '.git' / 'patchwork.json').read_text())
    root, patch = Path(meta['repository']), meta['patch']
    git(tree, 'add', '-A')
    diff = git(tree, 'diff', '--cached', 'base', capture=True)
    git(tree, 'reset', '-q')
    if not diff.strip():
        raise SystemExit('The patch would be empty; remove it from versions.lock.json instead.')
    (root / patch).write_text(diff)
    kind, entry = lock_entry(root, patch)
    _, main = repository()
    check = Path(tempfile.mkdtemp(prefix='patchwork-check-'))
    try:
        extract(main, kind, entry, check / 'tree')
        for item in entry['patches']:
            apply(check / 'tree', root / item)
    finally:
        shutil.rmtree(check)
    print(f"Saved {patch}; the complete {entry['name']} patch chain applies to the pinned revision.")


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] not in ('open', 'save'):
        raise SystemExit(__doc__)
    if sys.argv[1] == 'open':
        open_patch(sys.argv[2])
    else:
        save(sys.argv[2])
