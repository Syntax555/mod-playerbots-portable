"""Check the documentation's links, anchors and stated versions.

Every Markdown link in the README, contributor guide, notices, release template
and docs/ must name an existing file of this repository or a published release
asset, and every #anchor a heading of its target. Documents copied into the
server ZIP may link relatively only to files the ZIP contains. The provenance
guide must state each locked revision, the bundled runtime versions of the
release workflow and the launcher's server data release. Self-checks confirm
that broken links, anchors, ZIP-only targets and stale versions are reported.
"""

import json
from pathlib import Path
import re
import sys
import tempfile

from FixtureSupport import REPOSITORY as ROOT


sys.path.insert(0, str(ROOT / 'scripts'))
import publish_latest as publisher


GITHUB = 'https://github.com/Syntax555/mod-playerbots-portable'
DOWNLOAD = '/releases/latest/download/'
ASSETS = set(publisher.ZIP_CONTENTS) | {publisher.CHECKSUM_NAME, publisher.UPDATE_MANIFEST_NAME}
# The server ZIP layout from AssembleDistribution.cmake; CONTRIBUTING.md,
# docs/building.md and docs/upstream/ stay out, so packaged documents link to
# them on GitHub.
ZIP_FILES = {'README.md', 'THIRD_PARTY_NOTICES.md', 'LICENSE', 'versions.lock.json'}
ZIP_TREES = ('docs/', 'licenses/')
ZIP_EXCLUDED = {'docs/building.md', 'docs/upstream'}
ASSEMBLY = (
    'file(REMOVE "${PORTABLE_DIST_DIR}/CONTRIBUTING.md")',
    'file(COPY "${PORTABLE_SOURCE_DIR}/licenses/" DESTINATION "${PORTABLE_DIST_DIR}/licenses")',
    ('file(COPY "${PORTABLE_SOURCE_DIR}/docs/" DESTINATION "${PORTABLE_DIST_DIR}/docs"\n'
     '    PATTERN "building.md" EXCLUDE PATTERN "upstream" EXCLUDE)'),
    '"${PORTABLE_DIST_DIR}/versions.lock.json" COPYONLY)',
    'foreach(document README.md THIRD_PARTY_NOTICES.md)',
    'file(CONFIGURE OUTPUT "${PORTABLE_DIST_DIR}/LICENSE"',
)
LINK = re.compile(r'!?\[[^\]]*\]\(([^()\s]+)(?:\s+"[^"]*")?\)')


def documents(root):
    names = ['README.md', 'CONTRIBUTING.md', 'THIRD_PARTY_NOTICES.md', '.github/RELEASE_TEMPLATE.md']
    names += sorted(f'docs/{path.name}' for path in (root / 'docs').glob('*.md'))
    return [name for name in names if (root / name).is_file()]


def packaged(name):
    excluded = any(name == path or name.startswith(f'{path}/') for path in ZIP_EXCLUDED)
    return name in ZIP_FILES or name.startswith(ZIP_TREES) and not excluded


def prose(text):
    """Lines outside fenced code blocks, numbered from 1."""
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith('```'):
            fenced = not fenced
        elif not fenced:
            yield number, line


def anchors(text):
    """GitHub's heading anchors, including the suffixes of repeated headings."""
    seen = {}
    for _, line in prose(text):
        heading = re.match(r'#{1,6}\s+(.*?)\s*#*\s*$', line)
        if not heading:
            continue
        title = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', heading.group(1)).lower()
        slug = re.sub(r'[^\w\- ]', '', title).replace(' ', '-')
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        yield slug if count == 0 else f'{slug}-{count}'


def target_problem(root, document, target):
    """Why target does not resolve from document, or None."""
    path, _, anchor = target.partition('#')
    if document.endswith('RELEASE_TEMPLATE.md') and path.startswith('{source_url}/'):
        path = path.removeprefix('{source_url}/')
    elif document.endswith('RELEASE_TEMPLATE.md') and path.startswith('{repository_url}' + DOWNLOAD):
        name = path.removeprefix('{repository_url}' + DOWNLOAD)
        return None if name in ASSETS else f'{name} is not a published release asset'
    elif path.startswith('{'):
        return None
    elif path.startswith(GITHUB + DOWNLOAD):
        name = path.removeprefix(GITHUB + DOWNLOAD)
        return None if name in ASSETS else f'{name} is not a published release asset'
    elif path.startswith((GITHUB + '/blob/main/', GITHUB + '/tree/main/')):
        path = path.split('/main/', 1)[1]
    elif re.match(r'[a-z][a-z0-9+.-]*:', path):
        return None
    elif path:
        resolved = (root / document).parent.joinpath(path).resolve()
        if not resolved.is_relative_to(root.resolve()):
            return f'{path} leaves the repository'
        path = resolved.relative_to(root.resolve()).as_posix()
        if packaged(document) and not (packaged(path) or (root / path).is_dir() and packaged(f'{path}/')):
            return f'{path} is not in the server ZIP that contains {document}'
    else:
        path = document
    file = root / path
    if not file.exists():
        return f'{path} does not exist'
    if anchor and file.suffix == '.md' and anchor not in set(anchors(file.read_text(encoding='utf-8'))):
        return f'{path} has no heading #{anchor}'
    return None


def links(root):
    """(document, line number, target) of every link outside code, including link text that wraps."""
    for document in documents(root):
        text = (root / document).read_text(encoding='utf-8')
        kept = dict(prose(text))
        # Code becomes blank lines so that line numbers stay.
        body = '\n'.join(re.sub(r'`[^`]*`', '', kept.get(number, ''))
                         for number in range(1, len(text.splitlines()) + 1))
        for match in LINK.finditer(body):
            yield document, body.count('\n', 0, match.start()) + 1, match.group(1)


def link_problems(root):
    return [f'{document}:{number}: {target}: {problem}' for document, number, target in links(root)
            if (problem := target_problem(root, document, target))]


def version_problems(provenance, lock, workflow, client_data):
    """Locked revisions, bundled runtimes and the server data release the provenance guide must state."""
    revisions = [lock['core']['revision']] + [entry['revision'] for entry in
                lock['modules'] + lock['clientAddons'] + lock.get('sourceAddons', [])]
    revisions += [lock['clientPatch']['stormLib']['revision']]
    revisions += [source['revision'] for source in lock['clientPatch'].get('localizations', {}).values()]
    revisions += [source['revision'] for source in lock['historicalClassData']['sources']]
    problems = [f'locked revision {revision[:12]} is not listed' for revision in revisions
                if f'`{revision[:12]}`' not in provenance]
    runtime = {row[0]: row[1] for row in re.findall(r'^\| ([^|]+?) \| ([^|]+?) \|', provenance, re.MULTILINE)}
    for name, pattern in (('MySQL Community Server', r"MYSQL_VERSION: '([^']+)'"),
                          ('OpenSSL', r"OPENSSL_VERSION: '([^']+)'"),
                          ('Boost', r'boost_version: ([0-9.]+)')):
        version = re.search(pattern, workflow)
        assert version, f'the release workflow no longer sets {pattern}'
        if not re.match(re.escape(version.group(1)) + r'(?![0-9])', runtime.get(name, '')):
            problems.append(f'bundled {name} {version.group(1)} differs from the listed {runtime.get(name)}')
    release = re.search(r'defaultClientDataURL = "https://github[.]com/(wowgaming/client-data)'
                        r'/releases/download/([^/]+)/Data[.]zip"', client_data)
    assert release, 'the launcher no longer downloads Data.zip from a wowgaming/client-data release'
    if f'github.com/{release.group(1)}/releases/tag/{release.group(2)})' not in provenance:
        problems.append(f'the server data release {release.group(2)} is not linked')
    return problems


def self_check():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / 'docs').mkdir()
        (root / 'docs/building.md').write_text('# Build\n')
        (root / 'docs/upstream').mkdir()
        (root / 'docs/upstream/README.md').write_text('# Proposals\n')
        (root / 'docs/guide.md').write_text('# Guide\n\n## Start `here`\n\n## Start here\n')
        (root / 'CONTRIBUTING.md').write_text('[guide](docs/guide.md#start-here-1) [build](docs/building.md)\n')
        (root / 'README.md').write_text('\n'.join((
            '[ok](docs/guide.md#start-here) [anchor](#readme)',
            '`[code](missing.md)`', '```', '[fenced](missing.md)', '```',
            f'[asset]({GITHUB}{DOWNLOAD}SHA256SUMS.txt) [main]({GITHUB}/blob/main/docs/building.md)',
            '# Readme')) + '\n')
        assert link_problems(root) == [], link_problems(root)
        broken = {
            '[missing](docs/missing.md)': 'docs/missing.md does not exist',
            '[wrapped\nlink](docs/wrapped.md)': 'docs/wrapped.md does not exist',
            '[anchor](docs/guide.md#start)': 'docs/guide.md has no heading #start',
            '[unzipped](docs/building.md)': 'docs/building.md is not in the server ZIP',
            '[proposal](docs/upstream/README.md)': 'docs/upstream/README.md is not in the server ZIP',
            '[proposals](docs/upstream)': 'docs/upstream is not in the server ZIP',
            '[contributing](CONTRIBUTING.md)': 'CONTRIBUTING.md is not in the server ZIP',
            f'[asset]({GITHUB}{DOWNLOAD}other.zip)': 'other.zip is not a published release asset',
            f'[main]({GITHUB}/blob/main/docs/missing.md)': 'docs/missing.md does not exist',
            '[outside](../outside.md)': 'leaves the repository',
        }
        for link, problem in broken.items():
            (root / 'README.md').write_text(f'# Readme\n\n{link}\n')
            found = link_problems(root)
            assert len(found) == 1 and problem in found[0], (link, found)
        (root / 'README.md').write_text('# Readme\n')
        (root / '.github').mkdir()
        template = root / '.github/RELEASE_TEMPLATE.md'
        template.write_text('[a]({source_url}/README.md#readme) [b]({repository_url}' + DOWNLOAD +
                            'SHA256SUMS.txt) [c]({commit_url})\n')
        assert link_problems(root) == [], link_problems(root)
        for link, problem in (('[a]({source_url}/docs/missing.md)', 'docs/missing.md does not exist'),
                              ('[a]({source_url}/README.md#other)', 'README.md has no heading #other'),
                              ('[b]({repository_url}' + DOWNLOAD + 'other.zip)', 'not a published release asset')):
            template.write_text(link + '\n')
            found = link_problems(root)
            assert len(found) == 1 and problem in found[0], (link, found)
    lock = {'core': {'revision': 'a' * 40}, 'modules': [{'revision': 'b' * 40}], 'clientAddons': [],
            'sourceAddons': [{'revision': 'f' * 40}],
            'clientPatch': {'stormLib': {'revision': 'c' * 40}, 'localizations': {'deDE': {'revision': 'd' * 40}}},
            'historicalClassData': {'sources': [{'revision': 'e' * 40}]}}
    workflow = "MYSQL_VERSION: '8.0.1'\nOPENSSL_VERSION: '3.1.2'\nboost_version: 1.80.0\n"
    client_data = ('const defaultClientDataURL = '
                   '"https://github.com/wowgaming/client-data/releases/download/v9.0/Data.zip"')
    provenance = ''.join(f'`{letter * 12}` ' for letter in 'abcdef') + (
        '\n| MySQL Community Server | 8.0.1 |\n| OpenSSL | 3.1.2, build |\n| Boost | 1.80.0 |\n'
        '[release](https://github.com/wowgaming/client-data/releases/tag/v9.0)\n')
    assert version_problems(provenance, lock, workflow, client_data) == []
    for old, new in (('`dddddddddddd`', '`ddddddddddd0`'), ('`ffffffffffff`', '`fffffffffff0`'),
                     ('| 8.0.1 |', '| 8.0.10 |'),
                     ('| 1.80.0 |', '| 1.79.0 |'), ('tag/v9.0', 'tag/v8.0')):
        assert old in provenance, old
        assert len(version_problems(provenance.replace(old, new), lock, workflow, client_data)) == 1, new


self_check()
assembly = (ROOT / 'cmake/AssembleDistribution.cmake').read_text(encoding='utf-8')
for step in ASSEMBLY:
    assert step in assembly, f'AssembleDistribution.cmake changed the server ZIP layout this check assumes: {step}'
checked = list(links(ROOT))
assert len(checked) > 100, f'only {len(checked)} documentation links were found'
problems = link_problems(ROOT) + [f'docs/module-versions.md: {problem}' for problem in version_problems(
    (ROOT / 'docs/module-versions.md').read_text(encoding='utf-8'),
    json.loads((ROOT / 'versions.lock.json').read_text(encoding='utf-8')),
    (ROOT / '.github/workflows/release.yml').read_text(encoding='utf-8'),
    (ROOT / 'cmd/startup/client_data.go').read_text(encoding='utf-8'))]
for problem in problems:
    print(problem)
if problems:
    raise SystemExit(f'{len(problems)} documentation problems')
print(f'Checked {len(checked)} links in {len(documents(ROOT))} documents and the stated versions.')
