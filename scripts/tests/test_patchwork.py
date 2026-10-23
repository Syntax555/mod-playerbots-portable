"""Patch regeneration must preserve the saved chain when validation fails."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "patchwork.py"


class PatchworkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / ".module-cache/module"
        self.source.mkdir(parents=True)
        self.git(self.root, "init", "-q")
        self.git(self.source, "init", "-q")
        self.file = self.source / "file.txt"
        self.file.write_text("first\nmiddle\nlast\n")
        self.commit()
        revision = self.git(self.source, "rev-parse", "HEAD").strip()
        (self.root / "patches").mkdir()
        self.patch = self.root / "patches/first.patch"
        self.file.write_text("first\noriginal\nlast\n")
        self.patch.write_text(self.git(self.source, "diff"))
        self.commit()
        self.file.write_text("first\ndownstream\nlast\n")
        (self.root / "patches/second.patch").write_text(self.git(self.source, "diff"))
        self.git(self.source, "reset", "--hard", revision)
        (self.root / "versions.lock.json").write_text(json.dumps({
            "core": {"name": "module", "revision": revision,
                     "patches": ["patches/first.patch", "patches/second.patch"]},
            "modules": [],
        }))
        opened = self.run_patchwork("open", "patches/first.patch")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        self.tree = Path(opened.stdout.strip().splitlines()[-1])

    def git(self, directory, *args):
        return subprocess.run(["git", "-C", str(directory), "-c", "user.name=test",
                               "-c", "user.email=test@localhost", *args],
                              text=True, capture_output=True, check=True).stdout

    def commit(self):
        self.git(self.source, "add", "-A")
        self.git(self.source, "commit", "-qm", "fixture")

    def run_patchwork(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                              cwd=self.root, text=True, capture_output=True, check=False)

    def test_failed_downstream_validation_preserves_saved_patch(self):
        original = self.patch.read_bytes()
        (self.tree / "file.txt").write_text("first\nincompatible\nlast\n")
        result = self.run_patchwork("save", self.tree)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("patch failed", result.stderr)
        self.assertEqual(self.patch.read_bytes(), original)
        self.assertEqual(sorted(path.name for path in self.patch.parent.iterdir()),
                         ["first.patch", "second.patch"])

    def test_failed_validation_does_not_create_a_new_patch(self):
        self.patch.unlink()
        (self.tree / "file.txt").write_text("first\nincompatible\nlast\n")
        result = self.run_patchwork("save", self.tree)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("patch failed", result.stderr)
        self.assertFalse(self.patch.exists())

    def test_successful_save_includes_new_files_and_preserves_permissions(self):
        self.patch.chmod(0o640)
        (self.tree / "added.txt").write_text("new file\n")
        result = self.run_patchwork("save", self.tree)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("+new file", self.patch.read_text())
        self.assertEqual(self.patch.stat().st_mode & 0o777, 0o640)
        opened = self.run_patchwork("open", "patches/second.patch")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        downstream = Path(opened.stdout.strip().splitlines()[-1])
        self.assertEqual((downstream / "file.txt").read_text(), "first\ndownstream\nlast\n")
        self.assertEqual((downstream / "added.txt").read_text(), "new file\n")


if __name__ == "__main__":
    unittest.main()
