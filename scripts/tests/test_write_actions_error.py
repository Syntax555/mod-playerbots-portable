"""Annotation helper tests for the Windows build job; they need PowerShell 7."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest


HELPER = Path(__file__).resolve().parents[1] / "WriteActionsError.ps1"
POWERSHELL = shutil.which("pwsh")


@unittest.skipUnless(POWERSHELL, "PowerShell 7 is required")
class ActionsErrorTests(unittest.TestCase):
    def run_script(self, script: str) -> subprocess.CompletedProcess:
        return subprocess.run([POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
                               f". '{HELPER}'; {script}"], capture_output=True, text=True, timeout=120)

    def test_message_and_title_are_escaped(self):
        result = self.run_script("Write-ActionsError -Title 'Step: one, two' -Message \"50% done`r`nnext\"")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("::error title=Step%3A one%2C two::50%25 done%0D%0Anext", result.stdout.strip())

    def test_long_messages_keep_their_start_or_end(self):
        message = "\"A\" * 4000 + \"B\" * 8000 + \"C\" * 4000"
        head = self.run_script(f"Write-ActionsError -Title T -Message ({message})").stdout.strip()
        tail = self.run_script(f"Write-ActionsError -Title T -Message ({message}) -Tail").stdout.strip()
        self.assertEqual("::error title=T::" + "A" * 4000 + "B" * 4000, head)
        self.assertEqual("::error title=T::" + "B" * 4000 + "C" * 4000, tail)

    def test_failed_step_reports_one_annotation_and_fails(self):
        result = self.run_script("$ErrorActionPreference = 'Stop'; "
                                 "Invoke-ActionsStep 'Verify ZIP' { Write-Output 'checking'; throw 'missing LICENSE' }; "
                                 "Write-Output 'not reached'")
        self.assertEqual(1, result.returncode)
        self.assertEqual(["checking", "::error title=Verify ZIP::missing LICENSE"], result.stdout.splitlines())

    def test_successful_step_keeps_its_output(self):
        result = self.run_script("Invoke-ActionsStep 'Verify ZIP' { Write-Output 'verified' }; Write-Output 'next'")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["verified", "next"], result.stdout.splitlines())


if __name__ == "__main__":
    unittest.main()
