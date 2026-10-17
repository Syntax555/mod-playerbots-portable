"""Shared helpers for the cmake/tests fixtures."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
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


def pinned_source(module, path):
    """path at the locked revision of module, read from its PrepareModules cache."""
    lock = json.loads((REPOSITORY / 'versions.lock.json').read_text())
    revision = next(entry['revision'] for entry in lock['modules'] if entry['name'] == module)
    return subprocess.run(['git', '-C', str(REPOSITORY / '.module-cache' / module), 'show', f'{revision}:{path}'],
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
