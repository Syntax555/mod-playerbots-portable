"""Exercise the cache probe's real PowerShell control flow with tool doubles."""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / '.github/workflows/compiler-cache-probe.yml'
POWERSHELL = shutil.which('pwsh')


def probe_script():
    step = PROBE.read_text().split('      - name: Check cold, warm and changed-header builds\n', 1)[1]
    return textwrap.dedent(step.split('        run: |\n', 1)[1])


@unittest.skipUnless(POWERSHELL, 'PowerShell 7 is required')
class CompilerCacheProbeTests(unittest.TestCase):
    def run_probe(self, case='success', script=None):
        script = probe_script() if script is None else script
        # Replace only external commands; execute every production condition.
        self.assertIn('& "$env:CCACHE_BIN\\ccache.exe"', script)
        self.assertIn('& ./build/inner-build/Release/check.exe', script)
        script = script.replace('& "$env:CCACHE_BIN\\ccache.exe"', 'Invoke-Ccache')
        script = script.replace('& ./build/inner-build/Release/check.exe', 'Invoke-Check')
        setup = r'''
$env:RUNNER_TEMP = (Get-Location).Path
$env:CCACHE_BIN = 'fixture'
New-Item -ItemType Directory sample/inner | Out-Null
'Started' | Set-Content ccache.log
function cmake {
    $global:LASTEXITCODE = 0
    if ($case -eq 'configure-failure' -and $pass -eq 1 -and $args -contains '-S') {
        $global:LASTEXITCODE = 7
    }
    if ($case -eq 'build-failure' -and $pass -eq 1 -and $args -contains '--build') {
        'fixture compiler error'
        $global:LASTEXITCODE = 8
    }
}
function Invoke-Check {
    $global:LASTEXITCODE = 0
    if ($pass -eq 3 -and $case -ne 'stale-header') { '4' } else { '2' }
}
function Invoke-Ccache {
    $global:LASTEXITCODE = 0
    if ($args -contains '--print-stats') {
        $hits = if ($pass -eq 2 -and $case -ne 'no-hits') { 8 } else { 0 }
        $misses = if ($pass -eq 1 -or ($pass -eq 3 -and $case -ne 'no-invalidation') -or
                      ($pass -eq 2 -and $case -eq 'warm-miss')) { 8 } else { 0 }
        $pch = if ($case -eq 'uncacheable-pch') { 4 } else { 0 }
        @{direct_cache_hit = $hits; preprocessed_cache_hit = 0; cache_miss = $misses;
          could_not_use_precompiled_header = $pch} | ConvertTo-Json
    }
}
'''
        with tempfile.TemporaryDirectory(prefix='compiler-cache-test-') as temporary:
            path = Path(temporary) / 'probe.ps1'
            path.write_text(f"$case = '{case}'\n" + setup + script)
            return subprocess.run([POWERSHELL, '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(path)],
                                  cwd=temporary, capture_output=True, text=True, timeout=30, check=False)

    def assert_rejected(self, case, message, script=None):
        result = self.run_probe(case, script)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        # PowerShell may wrap its displayed error line using ANSI sequences.
        output = re.sub(r'\x1b\[[0-9;]*m', '', result.stdout + result.stderr)
        self.assertIn(message, output)

    def test_cold_warm_and_changed_header_succeed(self):
        result = self.run_probe()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('=== pass 3 exit code 0', result.stdout)

    def test_tool_failures_stop_the_probe(self):
        for case, message in (('configure-failure', 'Configure failed on pass 1'),
                              ('build-failure', 'Build failed on pass 1')):
            with self.subTest(case=case):
                self.assert_rejected(case, message)

    def test_warm_cache_requires_hits_and_cacheable_pch(self):
        for case in ('no-hits', 'warm-miss', 'uncacheable-pch'):
            with self.subTest(case=case):
                self.assert_rejected(case, 'The warm build must reuse')

    def test_header_changes_invalidate_cache_and_change_the_result(self):
        for case, message in (('stale-header', 'Stale result on pass 3'),
                              ('no-invalidation', 'Changing the header must invalidate')):
            with self.subTest(case=case):
                self.assert_rejected(case, message)

    def test_compile_failure_guard_mutation_is_detected(self):
        script = probe_script()
        guard = 'if ($buildExitCode -ne 0) { $log; throw "Build failed on pass $pass." }'
        self.assertIn(guard, script)
        with self.assertRaises(AssertionError):
            self.assert_rejected('build-failure', 'Build failed on pass 1', script.replace(guard, ''))


if __name__ == '__main__':
    unittest.main()
