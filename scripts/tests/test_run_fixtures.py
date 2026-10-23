"""Keep parallel CI shards exhaustive and preserve the local full-suite command."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("run_fixtures", ROOT / "cmake/tests/run_fixtures.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class GameplayShardsTests(unittest.TestCase):
    def test_default_runs_every_fixture_in_existing_order(self):
        with (patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run,
              redirect_stdout(io.StringIO())):
            self.assertEqual(0, runner.main(["gameplay"]))
        self.assertEqual(list(runner.GAMEPLAY), [Path(call.args[0][1]).stem for call in run.call_args_list])

    def test_four_shards_are_stable_disjoint_and_exhaustive(self):
        shards = [runner.gameplay_fixtures(index, 4) for index in range(4)]
        self.assertTrue(all(shards))
        flattened = [name for shard in shards for name in shard]
        self.assertCountEqual(runner.GAMEPLAY, flattened)
        self.assertEqual(len(flattened), len(set(flattened)))
        self.assertLessEqual(max(map(len, shards)) - min(map(len, shards)), 1)
        self.assertEqual(shards, [runner.gameplay_fixtures(index, 4) for index in range(4)])
        for shard in shards:
            positions = [runner.GAMEPLAY.index(name) for name in shard]
            self.assertEqual(sorted(positions), positions)

    def test_matrix_options_execute_only_the_selected_shard(self):
        with (patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run,
              redirect_stdout(io.StringIO()) as output):
            self.assertEqual(0, runner.main(["gameplay", "--shard-index", "2", "--shard-count", "4"]))
        self.assertEqual(list(runner.gameplay_fixtures(2, 4)),
                         [Path(call.args[0][1]).stem for call in run.call_args_list])
        self.assertIn("Gameplay shard 3/4", output.getvalue())
        self.assertIn("fixtures passed in", output.getvalue())

    def test_invalid_and_empty_shards_cannot_succeed(self):
        for index, count in ((0, 0), (0, -1), (-1, 4), (4, 4), (0, len(runner.GAMEPLAY) + 1)):
            with self.subTest(index=index, count=count):
                with (patch.object(runner.subprocess, "run") as run, redirect_stderr(io.StringIO()),
                      self.assertRaises(SystemExit) as error):
                    runner.main(["gameplay", "--shard-index", str(index), "--shard-count", str(count)])
                self.assertEqual(2, error.exception.code)
                run.assert_not_called()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            runner.main(["check", "--shard-count", "4"])
        self.assertEqual(2, error.exception.code)

    def test_failure_is_propagated_and_stops_the_shard(self):
        with (patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=7)) as run,
              redirect_stdout(io.StringIO()) as output):
            self.assertEqual(7, runner.main(["gameplay", "--shard-index", "1", "--shard-count", "4"]))
        run.assert_called_once()
        self.assertIn("failed (exit 7)", output.getvalue())
        self.assertIn("Gameplay shard 2/4 failed after", output.getvalue())

    def test_fixture_durations_are_reported(self):
        with (patch.object(runner, "GAMEPLAY", ("TestFixtureSupport",)),
              patch.object(runner.time, "monotonic", side_effect=(0, 1, 4, 6)),
              patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=0)),
              redirect_stdout(io.StringIO()) as output):
            self.assertEqual(0, runner.gameplay())
        self.assertIn("TestFixtureSupport: 3.0s", output.getvalue())
        self.assertIn("all 1 fixtures passed in 6.0s", output.getvalue())

    def test_wiring_accepts_the_matrix_command_and_detects_its_removal(self):
        body = "\n".join(f"# cmake/tests/{name}" for name in runner.fixtures()) + "\n" + '''jobs:
  gameplay:
    strategy:
      matrix:
        shard: [0, 1, 2, 3]
    steps:
      - run: python3 cmake/tests/run_fixtures.py gameplay --shard-index ${{ matrix.shard }} --shard-count 4
  checks:
    uses: ./.github/workflows/checks.yml
'''
        with patch.object(Path, "read_text", return_value=body):
            self.assertEqual([], runner.wiring_errors())
        with patch.object(Path, "read_text", return_value=body.replace(runner.GAMEPLAY_COMMAND, "missing-runner")):
            errors = runner.wiring_errors()
        self.assertIn(f"The checks workflow does not run {runner.GAMEPLAY_COMMAND}", errors)
        for before, after in (("[0, 1, 2, 3]", "[0, 1, 2]"),
                              ("[0, 1, 2, 3]", "[0, 1, 2, 2]"),
                              ("--shard-count 4", "--shard-count 3"),
                              ("--shard-count 4", "--shard-count 0"),
                              ("  gameplay:", "  incomplete_job:"),
                              (runner.CHECKS_CALL, "uses: ./.github/workflows/other.yml")):
            with (self.subTest(mutation=after),
                  patch.object(Path, "read_text", return_value=body.replace(before, after))):
                self.assertTrue(runner.wiring_errors())

    def test_original_full_suite_workflow_stays_supported(self):
        body = "\n".join(f"# cmake/tests/{name}" for name in runner.fixtures())
        body += f"\n  launcher:\n    steps:\n      - run: python3 {runner.GAMEPLAY_COMMAND}\n  checks:\n    {runner.CHECKS_CALL}\n"
        with patch.object(Path, "read_text", return_value=body):
            self.assertEqual([], runner.wiring_errors())


if __name__ == "__main__":
    unittest.main()
