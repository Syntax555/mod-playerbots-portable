"""Check the Journal module's grouped world queries and boss model on this server.

The launcher starts MySQL 8.0 without an sql_mode override, so ONLY_FULL_GROUP_BY
applies: a grouped query may select an ungrouped value only as a grouped
expression or from grouped columns, or it fails with error 1055 and the Journal
loses its reference-loot counts. The 3.3.5a client draws a humanoid boss built
from a race model white in a PlayerModel; a DressUpModel skins it. Every grouped
query in the pinned module and the boss model frame are checked, and reverting
the fork commit that fixed both must fail the checks.
"""

import argparse
from pathlib import Path
import re
import shutil
import tempfile

from FixtureSupport import (
    REPOSITORY,
    fork_change,
    git_apply,
    prepared_core,
    source_argument,
)


CHANGE = 'forever-journal-group-by-and-model'
FILES = ('src/JournalLoot.cpp', 'addon/Journal/Overview.lua')
AGGREGATE = re.compile(r'\b(?:COUNT|SUM|MIN|MAX|AVG|GROUP_CONCAT)\s*\(', re.IGNORECASE)
IDENTIFIER = re.compile(r'\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?\b(?!\s*\()')
KEYWORDS = {'AS', 'UNSIGNED', 'SIGNED', 'DISTINCT', 'NULL'}


def split_top_level(text):
    parts, depth, current = [], 0, ''
    for char in text:
        depth += (char == '(') - (char == ')')
        if char == ',' and depth == 0:
            parts.append(current.strip())
            current = ''
        else:
            current += char
    return parts + [current.strip()]


def grouped_queries(source):
    """Each run of adjacent C++ string literals that forms a grouped SELECT."""
    queries = []
    for run in re.finditer(r'"(?:[^"\\\n]|\\.)*"(?:\s*"(?:[^"\\\n]|\\.)*")*', source):
        text = ''.join(re.findall(r'"((?:[^"\\\n]|\\.)*)"', run.group(0)))
        if 'GROUP BY' in text and text.lstrip().upper().startswith('SELECT'):
            queries.append(text)
    return queries


def group_problems(query):
    select = re.match(r'\s*SELECT\s+(.*?)\s+FROM\s', query, re.IGNORECASE | re.DOTALL).group(1)
    grouped = re.search(r'GROUP BY\s+(.*?)(?:\s+(?:HAVING|ORDER BY|LIMIT)\b|$)', query, re.DOTALL).group(1)
    groups = [part for part in split_top_level(grouped)]
    problems = []
    for item in split_top_level(select):
        if AGGREGATE.search(item) or item in groups:
            continue
        columns = [name for name in IDENTIFIER.findall(item) if name.upper() not in KEYWORDS]
        if not columns or any(column not in groups for column in columns):
            problems.append(f'{item!r} is neither grouped nor built from the grouped {groups}')
    return problems


def problems(module):
    found = []
    queries = []
    for path in sorted((module / 'src').glob('*.cpp')):
        for query in grouped_queries(path.read_text(encoding='utf-8')):
            queries.append(query)
            found += [f'{path.name}: {problem}' for problem in group_problems(query)]
    if not any('ABS(Reference)' in query for query in queries):
        found.append('the reference-loot count query was not found')
    overview = (module / 'addon/Journal/Overview.lua').read_text(encoding='utf-8')
    if not re.search(r'^local model = CreateFrame\("DressUpModel", nil, pane\)$', overview, re.MULTILINE):
        found.append('the boss model is not a DressUpModel')
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source_argument(parser, 'module', default=prepared_core() / 'modules/mod-forever-journal')
    args = parser.parse_args()

    # The launcher's MySQL configuration keeps the server's default sql_mode.
    mysql = (REPOSITORY / 'cmd/startup/mysql.go').read_text(encoding='utf-8')
    assert '[mysqld]' in mysql and not re.search(r'sql[-_]mode', mysql, re.IGNORECASE)
    for query, expected in (
            ('SELECT CAST(ABS(Reference) AS UNSIGNED), COUNT(DISTINCT Entry) FROM t GROUP BY ABS(Reference)', 1),
            ('SELECT CAST(c.id AS UNSIGNED), COUNT(*) FROM creature c GROUP BY c.id', 0),
            ('SELECT a, b FROM t GROUP BY a', 1)):
        assert len(group_problems(query)) == expected, query

    found = problems(args.module)
    assert not found, '\n'.join(found)
    print('Journal grouped queries satisfy ONLY_FULL_GROUP_BY and boss models use a DressUpModel', flush=True)

    patch = fork_change('mod-forever-journal', CHANGE, FILES)
    with tempfile.TemporaryDirectory(prefix='forever-journal-') as directory:
        work = Path(directory)
        for relative in FILES:
            (work / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.module / relative, work / relative)
        git_apply(work, patch, '--reverse')
        reverted = problems(work)
        if not any('JournalLoot.cpp' in problem for problem in reverted) or \
                'the boss model is not a DressUpModel' not in reverted:
            raise AssertionError('Reverting the fork change did not fail both checks:\n' + '\n'.join(reverted))
        git_apply(work, patch)
        assert not problems(work)
    print(f'Reverting {CHANGE} fails the grouped query and boss model checks', flush=True)


if __name__ == '__main__':
    main()
