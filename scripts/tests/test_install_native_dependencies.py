"""Run the CI package helper against isolated mirror files and package commands."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / '.github/scripts/install-native-dependencies.sh'
BASH = shutil.which('bash')
OPTIONS = ['-o', 'Acquire::Retries=3', '-o', 'Acquire::http::Timeout=30',
           '-o', 'Acquire::https::Timeout=30']
FAKE_COMMAND = r'''
import json
import os
from pathlib import Path
import sys

arguments = sys.argv[1:]
if Path(sys.argv[0]).name == 'sudo':
    if arguments[:2] == ['bash', '-euc']:
        assert len(arguments) == 3
        # Redirect the fixed apt directory before running the real shell block.
        script = arguments[2].replace('/etc/apt/', os.environ['DEPENDENCY_TEST_ROOT'] + '/')
        os.execv(os.environ['DEPENDENCY_TEST_BASH'], ['bash', '-euc', script])
    assert arguments[0] == 'apt-get', arguments
    os.execv(str(Path(__file__).with_name('apt-get')), arguments)
with open(os.environ['DEPENDENCY_TEST_LOG'], 'a', encoding='utf-8') as log:
    log.write(json.dumps(arguments) + '\n')
if os.environ.get('DEPENDENCY_FAIL_ACTION') in arguments:
    raise SystemExit(100)
'''


@unittest.skipUnless(os.name == 'posix' and BASH, 'The Linux package helper requires Bash')
class NativeDependencyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='native-dependencies-')
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.mirrors = self.directory / 'apt'
        self.mirrors.mkdir()
        self.log = self.directory / 'apt-calls.jsonl'
        self.bin = self.directory / 'bin'
        self.bin.mkdir()
        for name in ('sudo', 'apt-get'):
            command = self.bin / name
            command.write_text(f'#!{sys.executable}\n' + FAKE_COMMAND)
            command.chmod(0o755)

    def run_helper(self, failure='', helper=HELPER):
        result = subprocess.run(
            [BASH, str(helper), 'build-essential', 'cmake', 'lua5.1'],
            env={**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ.get('PATH', ''),
                 'DEPENDENCY_TEST_ROOT': str(self.mirrors), 'DEPENDENCY_TEST_LOG': str(self.log),
                 'DEPENDENCY_TEST_BASH': BASH, 'DEPENDENCY_FAIL_ACTION': failure},
            capture_output=True, text=True, timeout=10, check=False)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return result, calls

    def test_existing_mirrors_use_official_https_without_changing_sources(self):
        for name in ('apt-mirrors.txt', 'apt-mirrors-security.txt'):
            (self.mirrors / name).write_text('http://azure.archive.ubuntu.com/ubuntu/\n')
        sources = self.mirrors / 'sources.list.d'
        sources.mkdir()
        preserved = {
            self.mirrors / 'sources.list': 'deb mirror+file:/etc/apt/apt-mirrors.txt noble main\n',
            sources / 'ubuntu.sources': 'URIs: mirror+file:/etc/apt/apt-mirrors.txt\n'
                                       'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n',
            sources / 'microsoft.list': 'deb [signed-by=/usr/share/keyrings/microsoft.gpg] '
                                       'https://packages.microsoft.com/ubuntu/24.04/prod noble main\n',
            self.mirrors / 'other.txt': 'http://azure.archive.ubuntu.com/ubuntu/\n',
        }
        for path, content in preserved.items():
            path.write_text(content)
        result, calls = self.run_helper()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('https://archive.ubuntu.com/ubuntu/\n', (self.mirrors / 'apt-mirrors.txt').read_text())
        self.assertEqual('https://security.ubuntu.com/ubuntu/\n', (self.mirrors / 'apt-mirrors-security.txt').read_text())
        for path, content in preserved.items():
            self.assertEqual(content, path.read_text())
        self.assertEqual([
            [*OPTIONS, '-o', 'APT::Update::Error-Mode=any', 'update'],
            [*OPTIONS, 'install', '--no-install-recommends', '-y', 'build-essential', 'cmake', 'lua5.1'],
        ], calls)

    def test_absent_mirror_files_are_not_created(self):
        result, calls = self.run_helper()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], list(self.mirrors.iterdir()))
        self.assertEqual(2, len(calls))

    def test_update_failure_stops_before_package_install(self):
        result, calls = self.run_helper('update')
        self.assertEqual(100, result.returncode, result.stderr)
        self.assertEqual([[*OPTIONS, '-o', 'APT::Update::Error-Mode=any', 'update']], calls)

    def test_install_failure_is_returned(self):
        result, calls = self.run_helper('install')
        self.assertEqual(100, result.returncode, result.stderr)
        self.assertEqual(2, len(calls))

    def test_timeout_and_update_failure_mutations_are_rejected(self):
        source = HELPER.read_text()
        mutations = (
            ('unbounded HTTP', 'Acquire::http::Timeout=30', 'Acquire::http::Timeout=0'),
            ('stale indexes accepted', 'APT::Update::Error-Mode=any', 'APT::Update::Error-Mode=persistent'),
            ('install after failed update', 'set -euo pipefail', 'set -uo pipefail'),
        )
        for label, before, after in mutations:
            with self.subTest(mutation=label):
                self.assertEqual(1, source.count(before))
                helper = self.directory / 'mutant.sh'
                helper.write_text(source.replace(before, after))
                self.log.unlink(missing_ok=True)
                result, calls = self.run_helper('update', helper)
                with self.assertRaises(AssertionError):
                    self.assertEqual(100, result.returncode)
                    self.assertEqual([[*OPTIONS, '-o', 'APT::Update::Error-Mode=any', 'update']], calls)


if __name__ == '__main__':
    unittest.main()
