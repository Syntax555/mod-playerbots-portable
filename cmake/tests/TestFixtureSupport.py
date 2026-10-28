"""Regression checks for shared fixture sources, options, WDBC data and SQL rows."""

import argparse
import http.server
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock

from FixtureSupport import (
    fork_change,
    fork_history,
    git_apply,
    make_wdbc,
    pinned_source,
    source_argument,
    sql_rows,
    sql_values,
    unpatched,
    wdbc,
)


class FixtureSupportTests(unittest.TestCase):
    # One two-field record (ID 7, string offset 1), followed by an UTF-8 string block.
    data = bytes.fromhex('57444243 01000000 02000000 08000000 04000000 07000000 01000000 00c3a400')
    row = bytes.fromhex('07000000 01000000')
    strings = b'\0\xc3\xa4\0'

    def test_reads_and_writes_known_wdbc_bytes(self):
        self.assertEqual(([self.row], self.strings), wdbc(self.data, 2))
        self.assertEqual(([self.row], self.strings), wdbc(self.data))
        self.assertEqual(self.data, make_wdbc([self.row], self.strings, 2))

    def test_rejects_invalid_wdbc_layouts(self):
        malformed = [b'WDBC', b'XXXX' + self.data[4:], self.data[:-1], self.data + b'\0']
        for offset, value in ((4, 2), (8, 3), (8, 0), (12, 4), (16, 5)):
            changed = bytearray(self.data)
            struct.pack_into('<I', changed, offset, value)
            malformed.append(bytes(changed))
        for data in malformed:
            with self.subTest(data=data), self.assertRaises(AssertionError):
                wdbc(data)
        with self.assertRaises(AssertionError):
            wdbc(self.data, 3)

    def test_empty_wdbc(self):
        data = bytes.fromhex('57444243 00000000 02000000 08000000 01000000 00')
        self.assertEqual(([], b'\0'), wdbc(data, 2))
        self.assertEqual(data, make_wdbc([], fields=2))

    def test_source_options_keep_path_defaults_and_overrides(self):
        parser = argparse.ArgumentParser()
        source_argument(parser, default=Path('prepared'))
        source_argument(parser, 'core')
        source_argument(parser, 'module', help='custom module directory')
        defaults = parser.parse_args([])
        self.assertEqual(Path('prepared'), defaults.source)
        self.assertIsNone(defaults.core)
        self.assertIsNone(defaults.module)
        args = parser.parse_args(['--source', 'custom', '--core', 'core', '--module', 'module'])
        self.assertEqual((Path('custom'), Path('core'), Path('module')), (args.source, args.core, args.module))
        self.assertIn('custom module directory', parser.format_help())


    def test_sql_rows_use_named_columns_and_quoted_values(self):
        self.assertEqual(['1', "it's, quoted", 'a\\b', ''], sql_values("1,'it\\'s, quoted','a\\\\b',''"))
        with tempfile.TemporaryDirectory() as directory:
            core = Path(directory)
            table = core / 'data/sql/base/db_world/fixture.sql'
            table.parent.mkdir(parents=True)
            table.write_text('CREATE TABLE `fixture` (\n  `entry` int,\n  `name` text\n) ENGINE=InnoDB;\n'
                             "INSERT INTO `fixture` VALUES\n(-7,'minus, seven'),\n(8,'eight');\n"
                             "INSERT INTO `fixture` VALUES\n(8,'acht');", encoding='utf-8')
            self.assertEqual([{'entry': '-7', 'name': 'minus, seven'}], sql_rows(core, 'fixture', {-7}))
            self.assertEqual([{'entry': '8', 'name': 'eight'}, {'entry': '8', 'name': 'acht'}],
                             sql_rows(core, 'fixture', {8}))
            with self.assertRaises(AssertionError):
                sql_rows(core, 'fixture', {9})
            with table.open('a', encoding='utf-8') as output:
                output.write("\n(9,'wrong','column count');\n")
            with self.assertRaises(ValueError):
                sql_rows(core, 'fixture', {9})


class ForkSourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='fixture-fork-source-')
        self.addCleanup(temporary.cleanup)
        self.repository = Path(temporary.name)
        self.history = self.repository / '.module-cache/mod-fixture'
        self.history.mkdir(parents=True)
        self.git('init', '--quiet')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        (self.history / 'src').mkdir()
        self.upstream = self.commit('upstream', 'upstream other')
        self.first = self.commit('first', 'first other')
        self.second = self.commit('second', 'first other')
        self.module = {'name': 'mod-fixture', 'url': 'https://github.com/Syntax555/mod-fixture.git',
                       'revision': self.second,
                       'upstream': {'url': 'https://github.com/example/mod-fixture.git', 'revision': self.upstream},
                       'forkChanges': {'mod-fixture-first': self.first, 'mod-fixture-second': self.second}}
        self.core = dict(self.module, name='azerothcore-wotlk',
                         url='https://github.com/Syntax555/azerothcore-wotlk.git',
                         forkChanges={'azerothcore-first': self.first, 'azerothcore-second': self.second})
        (self.repository / 'versions.lock.json').write_text(json.dumps(
            {'core': self.core, 'modules': [self.module]}))

    def git(self, *arguments):
        return subprocess.run(['git', '-C', str(self.history), *arguments], check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, shared, other):
        (self.history / 'src/shared.cpp').write_text(shared + '\n')
        (self.history / 'src/other.cpp').write_text(other + '\n')
        self.git('add', 'src')
        self.git('commit', '--quiet', '-m', shared)
        return self.git('rev-parse', 'HEAD')

    def test_fork_history_keeps_refs_for_sequential_commit_fetches(self):
        for commit, before, after in ((self.first, 'upstream', 'first'), (self.second, 'first', 'second')):
            history = fork_history('mod-fixture', str(self.history), commit, 2, self.repository)
            diff = subprocess.run(['git', '-C', str(history), 'diff', commit + '^', commit,
                                   '--', 'src/shared.cpp'], check=True, capture_output=True, text=True).stdout
            self.assertIn(f'-{before}\n+{after}\n', diff)
            ref = subprocess.run(['git', '-C', str(history), 'rev-parse', f'refs/portable-cache/{commit}'],
                                 check=True, capture_output=True, text=True).stdout.strip()
            self.assertEqual(commit, ref)
        refs = subprocess.run(['git', '-C', str(history), 'for-each-ref', '--format=%(objectname)',
                               'refs/portable-cache'], check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertEqual({self.first, self.second}, set(refs))
        self.assertEqual(history, fork_history('mod-fixture', str(self.repository / 'missing-remote'),
                                              self.second, 2, self.repository))

    def test_fork_history_retries_stalled_http_before_server_closes(self):
        requested, release = threading.Event(), threading.Event()

        class StalledResponse(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Type', 'application/x-git-upload-pack-advertisement')
                self.send_header('Content-Length', '1024')
                self.end_headers()
                requested.set()
                release.wait(45)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), StalledResponse)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            started = time.monotonic()
            with (mock.patch.dict(os.environ, {'NO_PROXY': '127.0.0.1', 'no_proxy': '127.0.0.1'}),
                  mock.patch('FixtureSupport.time.sleep', side_effect=RuntimeError('fetch retry')) as retry,
                  self.assertRaisesRegex(RuntimeError, 'fetch retry')):
                fork_history('stalled', f'http://127.0.0.1:{server.server_port}/repo.git',
                             self.first, 2, self.repository)
            self.assertTrue(requested.is_set(), 'Git must reach the local stalled HTTP response')
            self.assertLess(time.monotonic() - started, 40, 'Git waited for the server instead of retrying')
            retry.assert_called_once_with(1)
        finally:
            release.set()
            server.shutdown()
            server.server_close()
            thread.join()

    def test_fork_history_recovers_after_fetch_failure(self):
        remote = self.repository / 'recovered-remote'
        with mock.patch('FixtureSupport.time.sleep', side_effect=lambda _: shutil.copytree(self.history, remote)) as retry:
            history = fork_history('recovered', str(remote), self.first, 2, self.repository)
        retry.assert_called_once_with(1)
        actual = subprocess.run(['git', '-C', str(history), 'show', f'{self.first}:src/shared.cpp'],
                                check=True, capture_output=True, text=True).stdout
        self.assertEqual('first\n', actual)

    def test_fork_history_preserves_final_fetch_failure(self):
        with (mock.patch('FixtureSupport.time.sleep') as retry,
              self.assertRaises(subprocess.CalledProcessError) as failure):
            fork_history('missing', str(self.repository / 'missing-remote'), self.first, 2, self.repository)
        self.assertNotEqual(0, failure.exception.returncode)
        self.assertIn(b'missing-remote', failure.exception.stderr)
        self.assertEqual([mock.call(1), mock.call(2), mock.call(3), mock.call(4)], retry.call_args_list)

    def test_fork_changes_keep_scope_and_reversion_order(self):
        paths = ('src/shared.cpp',)
        for entry in (self.module, self.core):
            name = entry['name']
            first_change, second_change = entry['forkChanges']
            with self.subTest(component=name), \
                    mock.patch('FixtureSupport.fork_history', return_value=self.history) as history:
                first = fork_change(name, first_change, paths, self.repository)
                history.assert_called_once_with(name, entry['url'], self.first, 2, self.repository)
                second = fork_change(name, second_change, paths, self.repository)
                complete = fork_change(name, first_change, repository=self.repository)
                self.assertIn(b'-first\n+second\n', second.read_bytes())
                self.assertNotIn(b'src/other.cpp', first.read_bytes())
                self.assertNotEqual(first, complete)
                self.assertIn(b'src/other.cpp', complete.read_bytes())
                work = self.repository / name / 'src'
                work.mkdir(parents=True)
                (work / 'shared.cpp').write_text('second\n')
                (work / 'other.cpp').write_text('first other\n')
                unpatched(work.parent, second)
                unpatched(work.parent, first)
                self.assertEqual('upstream\n', (work / 'shared.cpp').read_text())
                self.assertEqual('first other\n', (work / 'other.cpp').read_text())
                git_apply(work.parent, first)
                git_apply(work.parent, second)
                self.assertEqual('second\n', (work / 'shared.cpp').read_text())

    def test_pinned_source_reads_upstream_instead_of_fork_head(self):
        for entry in (self.module, self.core):
            name = entry['name']
            with self.subTest(component=name), mock.patch('FixtureSupport.REPOSITORY', self.repository), \
                    mock.patch('FixtureSupport.fork_history', return_value=self.history) as history:
                self.assertEqual('upstream\n', pinned_source(name, 'src/shared.cpp'))
                history.assert_called_once_with(name, entry['upstream']['url'], self.upstream, 1)
        self.assertEqual('second', self.git('show', 'HEAD:src/shared.cpp'))


if __name__ == '__main__':
    unittest.main()
