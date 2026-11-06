"""Checks the rolling Latest ZIP of an addon fork: committed runtime files, stamps and refusals."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile


PACKAGER = Path(__file__).resolve().parents[2] / "scripts/package_addon_latest.py"


def git(directory: Path, *arguments: str) -> str:
    return subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=f@example.invalid", "-C",
                           str(directory), *arguments], check=True, capture_output=True, text=True).stdout


class PackageLatestTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="addon-latest-")
        self.addCleanup(temporary.cleanup)
        self.checkout = Path(temporary.name) / "fork"
        files = {
            "Demo/Demo.toc": "## Interface: 30300\nMain.lua\nUI.xml\n",
            "Demo/Main.lua": "return true\n",
            "Demo/UI.xml": '<Ui><Script file="Frames.lua"/></Ui>\n',
            "Demo/Frames.lua": "return 1\n",
            "Demo/Dynamic.lua": "return 2\n",  # unlisted files may be loaded dynamically and stay
            "Demo/tests/test_demo.lua": "error()\n",
            "Demo/docs/notes.md": "development notes\n",
            "LICENSE": "license text\n",
        }
        for relative, content in files.items():
            (self.checkout / relative).parent.mkdir(parents=True, exist_ok=True)
            (self.checkout / relative).write_text(content)
        git(self.checkout, "init", "-q")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-qm", "fixture")
        (self.checkout / "Demo/Untracked.lua").write_text("return 3\n")
        self.revision = git(self.checkout, "rev-parse", "HEAD").strip()
        self.output = Path(temporary.name) / "Demo-latest.zip"

    def package(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(PACKAGER), "--checkout", str(self.checkout),
                               "--addon", "Demo:Demo.toc:Demo", "--extra", "LICENSE:Demo/LICENSE", *extra,
                               "--output", str(self.output)], capture_output=True, text=True, check=False)

    def test_packages_committed_runtime_files_with_the_revision(self):
        result = self.package()
        self.assertEqual(result.returncode, 0, result.stderr)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(sorted(archive.namelist()), [
                "Demo/Demo.toc", "Demo/Dynamic.lua", "Demo/Frames.lua", "Demo/LICENSE", "Demo/Main.lua",
                "Demo/SOURCE_REVISION.txt", "Demo/UI.xml"])
            self.assertEqual(archive.read("Demo/SOURCE_REVISION.txt"), (self.revision + "\n").encode())

    def test_refuses_another_client_interface_and_missing_assets(self):
        for toc in ("## Interface: 11500\nMain.lua\n", "## Interface: 30300\nMissing.lua\n"):
            (self.checkout / "Demo/Demo.toc").write_text(toc)
            git(self.checkout, "commit", "-qam", "change toc")
            result = self.package()
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.output.exists())

    @unittest.skipUnless(shutil.which("luac5.1"), "luac5.1 is required for the Lua syntax check")
    def test_checks_the_syntax_of_packaged_lua(self):
        self.assertEqual(self.package("--luac", "luac5.1").returncode, 0)
        (self.checkout / "Demo/Dynamic.lua").write_text("local broken =\n")
        git(self.checkout, "commit", "-qam", "broken lua")
        result = self.package("--luac", "luac5.1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Dynamic.lua", result.stderr)


if __name__ == "__main__":
    unittest.main()
