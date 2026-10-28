"""Keep CI shard coverage and fork fixture selection connected to the runner."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
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


class CoreFixturesTests(unittest.TestCase):
    def test_core_runs_only_its_existing_checks(self):
        self.assertTrue(runner.CORE_FIXTURES)
        self.assertEqual(len(runner.CORE_FIXTURES), len(set(runner.CORE_FIXTURES)))
        self.assertTrue({f"{name}.py" for name in runner.CORE_FIXTURES} <= runner.fixtures())
        with (patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run,
              redirect_stdout(io.StringIO()) as output):
            self.assertEqual(0, runner.main(["core"]))
        self.assertEqual(list(runner.CORE_FIXTURES), [Path(call.args[0][1]).stem for call in run.call_args_list])
        self.assertIn(f"Core: all {len(runner.CORE_FIXTURES)} fixtures passed", output.getvalue())

    def test_invalid_core_arguments_cannot_succeed(self):
        for arguments in (("core", "--module", "mod-playerbots"), ("core", "--shard-count", "4")):
            with (self.subTest(arguments=arguments), patch.object(runner.subprocess, "run") as run,
                  redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error):
                runner.main(list(arguments))
            self.assertEqual(2, error.exception.code)
            run.assert_not_called()

    def test_failure_stops_the_core_checks(self):
        with (patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=7)) as run,
              redirect_stdout(io.StringIO()) as output):
            self.assertEqual(7, runner.main(["core"]))
        run.assert_called_once()
        self.assertIn("Core failed after", output.getvalue())

    def test_wiring_rejects_a_missing_core_fixture(self):
        with patch.object(runner, "CORE_FIXTURES", ("TestMissing",)):
            self.assertIn("TestMissing.py is listed for the core but does not exist", runner.wiring_errors())


class ModuleFixturesTests(unittest.TestCase):
    def test_every_locked_module_has_existing_native_fixtures(self):
        lock = json.loads((ROOT / "versions.lock.json").read_text())
        self.assertEqual({entry["name"] for entry in lock["modules"]}, set(runner.MODULE_FIXTURES))
        for module, selected in runner.MODULE_FIXTURES.items():
            with self.subTest(module=module):
                self.assertTrue(selected)
                self.assertEqual(len(selected), len(set(selected)))
                self.assertTrue({f"{name}.py" for name in selected} <= runner.fixtures())

    def test_module_runs_only_its_native_checks(self):
        for module, selected in runner.MODULE_FIXTURES.items():
            with (self.subTest(module=module),
                  patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run,
                  redirect_stdout(io.StringIO()) as output):
                self.assertEqual(0, runner.main(["module", "--module", module]))
            self.assertEqual(list(selected), [Path(call.args[0][1]).stem for call in run.call_args_list])
            self.assertIn(f"Module {module}: all {len(selected)} fixtures passed", output.getvalue())

    def test_invalid_module_arguments_cannot_succeed(self):
        for arguments in (("module",), ("module", "--module", "unknown"),
                          ("gameplay", "--module", "mod-playerbots"),
                          ("check", "--module", "mod-playerbots"),
                          ("module", "--module", "mod-playerbots", "--shard-count", "4")):
            with (self.subTest(arguments=arguments), patch.object(runner.subprocess, "run") as run,
                  redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error):
                runner.main(list(arguments))
            self.assertEqual(2, error.exception.code)
            run.assert_not_called()

    def test_failure_stops_the_module_checks(self):
        with (patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=7)) as run,
              redirect_stdout(io.StringIO()) as output):
            self.assertEqual(7, runner.main(["module", "--module", "mod-playerbots"]))
        run.assert_called_once()
        self.assertIn("Module mod-playerbots failed after", output.getvalue())

    def test_wiring_rejects_a_missing_module_fixture(self):
        with patch.object(runner, "MODULE_FIXTURES", {"mod-playerbots": ("TestMissing",)}):
            self.assertIn("TestMissing.py is listed for mod-playerbots but does not exist", runner.wiring_errors())


if __name__ == "__main__":
    unittest.main()
