"""Shared helpers for the cmake/tests fixtures."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
from itertools import takewhile
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import time
import urllib.request


# The fixtures check with assert statements, which -O and PYTHONOPTIMIZE remove.
if not __debug__:
    raise SystemExit('Run the cmake/tests fixtures without -O or PYTHONOPTIMIZE; their checks are assert statements')

REPOSITORY = Path(__file__).resolve().parents[2]
# Seconds a fixture or mutant executable may run. Mutants remove loop and budget
# bounds on purpose, so a hang must fail instead of holding the CI job.
TIMEOUT = 60
SANITIZER_FLAGS = ('-fsanitize=address,undefined', '-fno-omit-frame-pointer')


def prepared_core(repository=REPOSITORY):
    """The generated core checkout that contains the prepared modules."""
    return repository / '.module-cache/prepared-core'


def source_argument(parser, name='source', **options):
    """Add a fixture's source directory option, preserving its default and help."""
    parser.add_argument('--' + name, type=Path, **options)


def wdbc(data, fields=None):
    """Read raw WDBC records and their string block independently of production readers."""
    assert len(data) >= 20
    magic, count, actual_fields, record_size, string_size = struct.unpack_from('<4s4I', data)
    assert magic == b'WDBC' and actual_fields > 0 and record_size == actual_fields * 4
    assert fields is None or actual_fields == fields
    end = 20 + count * record_size
    assert len(data) == end + string_size
    return [data[offset:offset + record_size] for offset in range(20, end, record_size)], data[end:]


def make_wdbc(rows, strings=b'\0', fields=234):
    """Build independent WDBC fixture bytes from raw records."""
    return struct.pack('<4s4I', b'WDBC', len(rows), fields, fields * 4, len(strings)) + b''.join(rows) + strings


def sql_values(row):
    """Split one SQL VALUES tuple body, honouring quotes and backslash escapes."""
    values, value, quoted, index = [], '', False, 0
    while index < len(row):
        char = row[index]
        if quoted and char == '\\':
            value += row[index + 1]
            index += 1
        elif char == "'":
            quoted = not quoted
        elif char == ',' and not quoted:
            values.append(value)
            value = ''
        else:
            value += char
        index += 1
    return values + [value]


def sql_rows(core, table, entries):
    """Read named fields, so changed upstream table layouts cannot silently change test data."""
    rows = []
    with (core / f'data/sql/base/db_world/{table}.sql').open(encoding='utf-8') as source:
        create = ''.join(takewhile(lambda line: ') ENGINE' not in line, source)).split(f'CREATE TABLE `{table}` (')[1]
        columns = [line.split('`')[1] for line in create.splitlines() if line.strip().startswith('`')]
        for line in source:
            if line.startswith('(') and int(line.split(',', 1)[0][1:]) in entries:
                rows.append(dict(zip(columns, sql_values(line.rstrip('\n,;')[1:-1]), strict=True)))
    assert rows, (table, entries)
    return rows


def function(source, signature):
    """The definition that starts at signature, through its matching closing brace."""
    start = source.index(signature)
    opening = source.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def cxx():
    """$CXX, else g++, c++ or clang++ from PATH; the fixtures' warning and sanitizer flags target GCC."""
    found = os.environ.get('CXX') or shutil.which('g++') or shutil.which('c++') or shutil.which('clang++')
    if not found:
        raise SystemExit('A C++20 compiler is required')
    return found


def in_parallel(task, items):
    """task(item) for every item, one worker per CPU; the results keep the order of items.

    The first failure is raised once the running tasks finish; queued tasks are cancelled.
    """
    with ThreadPoolExecutor(os.cpu_count()) as pool:
        futures = [pool.submit(task, item) for item in items]
        try:
            return [future.result() for future in futures]
        finally:
            pool.shutdown(cancel_futures=True)


def run_fixture(command, name=None, **options):
    """Run a fixture executable with captured text output; a run past TIMEOUT fails the fixture."""
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT, check=False, **options)
    except subprocess.TimeoutExpired:
        raise SystemExit(f'{name or Path(command[0]).name} did not finish within {TIMEOUT} s') from None


def reject_mutants(work, mutations, build, name):
    """Check that the fixture built from work fails for every (label, file, old, new) mutation.

    Each mutant replaces every old in its file within a private copy of work, then
    build(directory, executable) returns the command that compiles it, and the
    executable must exit non-zero. Mutants build and run in parallel; their
    results print in input order.
    """
    executable = 'fixture.exe' if os.name == 'nt' else 'fixture'
    with tempfile.TemporaryDirectory(prefix='fixture-mutants-') as mutants:
        def rejected(numbered):
            index, (label, file, old, new) = numbered
            directory = Path(mutants) / str(index)
            shutil.copytree(work, directory, ignore=shutil.ignore_patterns(executable))
            text = (directory / file).read_text()
            if old not in text:
                raise SystemExit(f'{label} mutation was not applied')
            (directory / file).write_text(text.replace(old, new))
            subprocess.run(build(directory, directory / executable), check=True)
            return run_fixture([str(directory / executable)], f'{label} mutant').returncode != 0

        results = in_parallel(rejected, enumerate(mutations))
    for (label, *_), result in zip(mutations, results):
        if not result:
            raise SystemExit(f'{name} did not reject {label}')
        print(f'{name} mutation rejected: {label}')


def pinned_source(name, path):
    """path at the locked core or module revision, read from its PrepareModules cache.

    A forked component's pinned commit already carries its changes, so its baseline
    is the upstream revision the fork records.
    """
    lock = json.loads((REPOSITORY / 'versions.lock.json').read_text())
    entry = next(entry for entry in [lock['core'], *lock['modules']] if entry['name'] == name)
    if 'upstream' in entry:
        revision = entry['upstream']['revision']
        cache = fork_history(name, entry['upstream']['url'], revision, 1)
    else:
        revision, cache = entry['revision'], REPOSITORY / '.module-cache' / name
    return subprocess.run(['git', '-C', str(cache), 'show', f'{revision}:{path}'],
                          check=True, text=True, capture_output=True).stdout


def profession_skills(core):
    """C++ for the native profession test of a spell's skill lines.

    The production IsPrimaryProfessionSkill and IsProfessionSkill run against a
    SkillLine.dbc double that holds each skill's category. Skill-line abilities are
    native-shaped rows that a fixture's SpellMgr double maps to spells.
    """
    shared = (core / 'src/server/shared/SharedDefines.h').read_text()
    header = (core / 'src/server/game/Spells/SpellMgr.h').read_text()
    source = (core / 'src/server/game/Spells/SpellMgr.cpp').read_text()
    structures = (core / 'src/server/shared/DataStores/DBCStructure.h').read_text()
    skill_line = function(structures, 'struct SkillLineEntry')
    ability = function(structures, 'struct SkillLineAbilityEntry')
    assert re.search(r'\bint32\s+categoryId;', skill_line) and re.search(r'\buint32\s+SkillLine;', ability)
    typedefs = ['typedef std::multimap<uint32, SkillLineAbilityEntry const*> SkillLineAbilityMap;',
                ('typedef std::pair<SkillLineAbilityMap::const_iterator, SkillLineAbilityMap::const_iterator> '
                 'SkillLineAbilityMapBounds;')]
    assert all(line in header for line in typedefs)
    return '\n'.join([
        function(shared, 'enum SkillType') + ';',
        function(shared, 'enum SkillCategory') + ';',
        'struct SkillLineEntry { uint32 id = 0; std::int32_t categoryId = 0; };',
        'struct SkillLineAbilityEntry { uint32 ID = 0, SkillLine = 0, Spell = 0; };',
        'struct SkillLineStore',
        '{',
        '    std::map<uint32, SkillLineEntry> rows;',
        '    SkillLineEntry const* LookupEntry(uint32 id) const',
        '    { auto const found = rows.find(id); return found == rows.end() ? nullptr : &found->second; }',
        '} sSkillLineStore;',
        *typedefs,
        function(source, 'bool IsPrimaryProfessionSkill(uint32 skill)'),
        function(header, 'inline bool IsProfessionSkill(uint32 skill)'),
    ])


def fork_history(component, url, commit, depth, repository=REPOSITORY):
    """A bare cache of a fork or upstream holding commit and depth - 1 ancestors."""
    history = repository / '.module-cache/fork-history' / re.sub(r'[^A-Za-z0-9_.-]', '-', component)

    def fetched():
        return subprocess.run(['git', '-C', str(history), 'cat-file', '-e', commit + '^' * (depth - 1) + '^{commit}'],
                              capture_output=True, check=False).returncode == 0

    if not (history / 'HEAD').exists():
        # Fixtures may run alongside each other; only one initialized repository is moved in place.
        history.parent.mkdir(parents=True, exist_ok=True)
        staged = Path(tempfile.mkdtemp(prefix=history.name + '.', dir=history.parent))
        subprocess.run(['git', 'init', '--quiet', '--bare', str(staged)], check=True, capture_output=True)
        try:
            os.rename(staged, history)
        except OSError:
            shutil.rmtree(staged)
    for attempt in range(5):
        if fetched():
            return history
        try:
            # Let Git stop stalled HTTP transfers so retries do not leave transport children running.
            subprocess.run(['git', '-c', 'http.lowSpeedLimit=1', '-c', 'http.lowSpeedTime=30',
                            '-C', str(history), 'fetch', '--quiet', f'--depth={depth}', url,
                            f'{commit}:refs/portable-cache/{commit}'],
                           check=True, capture_output=True)
        except subprocess.CalledProcessError:
            # A fixture running alongside may hold the shallow lock.
            if attempt == 4:
                raise
            time.sleep(1 + attempt)
    return history


def fork_change(component, change, paths=(), repository=REPOSITORY):
    """The diff one commit of a forked component made, as a patch file.

    versions.lock.json pins the fork and names the commit that carries each
    change. Fixtures revert and reapply that diff exactly as they did with the
    former patch, so a fixture fails when the fork loses the change. paths
    limits the diff to the files a fixture copies.
    """
    lock = json.loads((repository / 'versions.lock.json').read_text())
    entries = [entry for entry in [lock['core'], *lock.get('modules', []),
                                  *lock.get('clientAddons', []), *lock.get('sourceAddons', [])]
               if entry['name'] == component]
    if len(entries) != 1:
        raise ValueError(f'Expected one locked component named {component}')
    entry = entries[0]
    commit = entry.get('forkChanges', {}).get(change, '')
    if not re.fullmatch(r'[0-9a-f]{40}', commit) or not re.fullmatch(
            r'https://github[.]com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+[.]git', entry['url']):
        raise ValueError(f'{component} pins no fork commit for {change}')
    scope = '-' + hashlib.sha256('\0'.join(paths).encode()).hexdigest()[:8] if paths else ''
    output = repository / '.module-cache/fork-changes' / f'{change}-{commit[:12]}{scope}.patch'
    if output.is_file():
        return output
    history = fork_history(component, entry['url'], commit, 2, repository)
    # Diffs keep LF bytes and a fixed format whatever the host configures.
    diff = subprocess.run(['git', '-c', 'core.autocrlf=false', '-c', 'diff.noprefix=false',
                           '-c', 'diff.mnemonicPrefix=false', '-C', str(history), 'diff', '--binary',
                           '--full-index', '--no-renames', '--no-color', '--no-ext-diff', commit + '^', commit,
                           '--', *paths], check=True, capture_output=True).stdout
    if not diff:
        raise ValueError(f'{component} commit {commit} changes nothing')
    output.parent.mkdir(parents=True, exist_ok=True)
    staged = output.with_suffix(f'.{os.getpid()}.partial')
    staged.write_bytes(diff)
    os.replace(staged, output)
    return output


def git_apply(directory, patch, *options):
    subprocess.run(['git', 'apply', *options, str(patch)], cwd=directory, check=True, capture_output=True)


def unpatched(directory, patch):
    """Revert patch where directory already has it, so callers may pass pristine or prepared sources."""
    if subprocess.run(['git', 'apply', '--check', str(patch)], cwd=directory, capture_output=True,
                      check=False).returncode:
        git_apply(directory, patch, '--reverse')


def multibot_sources(directory, files, source=None):
    """Copy the pinned MultiBot client files into directory.

    They come from source when given, else from the PrepareModules cache, else
    from the locked revision online.
    """
    lock = json.loads((REPOSITORY / 'versions.lock.json').read_text())
    addon = next(item for item in lock['clientAddons'] if item['name'] == 'MultiBot')
    revision = addon['revision']
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('MultiBot source revision must be pinned')
    cache = REPOSITORY / '.module-cache/client-addon-MultiBot'
    cached = source is None and (cache / '.git').exists() and subprocess.run(
        ['git', '-C', str(cache), 'cat-file', '-e', revision + '^{commit}'], capture_output=True,
        check=False).returncode == 0
    repository = addon['url'].removeprefix('https://github.com/').removesuffix('.git')
    for relative in files:
        destination = directory / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source is not None:
            shutil.copyfile(source / relative, destination)
        elif cached:
            destination.write_bytes(subprocess.run(['git', '-C', str(cache), 'show', f'{revision}:{relative}'],
                                                   check=True, capture_output=True).stdout)
        else:
            url = f'https://raw.githubusercontent.com/{repository}/{revision}/{relative}'
            with urllib.request.urlopen(url, timeout=30) as response:
                content = response.read(2 * 1024 * 1024 + 1)
            if len(content) > 2 * 1024 * 1024:
                raise ValueError('MultiBot fixture source exceeds the supported size')
            destination.write_bytes(content)
