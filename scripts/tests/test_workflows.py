"""Keep check and build triggers, mandatory checks and trusted publication connected."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
CHECKS = ROOT / '.github/workflows/checks.yml'
RELEASE = ROOT / '.github/workflows/release.yml'
PUBLISH = ROOT / '.github/workflows/publish-latest.yml'


def block(text, name, indent=0):
    """A known workflow mapping, through the next key at the same indentation."""
    prefix = ' ' * indent
    found = re.search(rf'(?ms)^{prefix}{re.escape(name)}:[ \t]*\n'
                      rf'(.*?)(?=^{prefix}[A-Za-z_][\w-]*:|\Z)', text)
    if found is None:
        raise AssertionError(f'Missing workflow mapping: {name}')
    return found[1]


def steps(text):
    return re.findall(r'(?ms)^      - .*?(?=^      - |\Z)', text)


class WorkflowTests(unittest.TestCase):
    def check_workflows(self, checks, release, publish):
        events = block(checks, 'on')
        for event in ('pull_request', 'workflow_call'):
            self.assertRegex(events, rf'(?m)^  {event}:')
        branches = block(block(events, 'push', 2), 'branches', 4)
        self.assertEqual(re.findall(r'(?m)^      - (\S+)', branches), ['main'])

        # The Windows compile runs only on request, after the complete checks.
        self.assertEqual(re.findall(r'(?m)^  (\w+):', block(release, 'on')), ['workflow_dispatch'])
        self.assertRegex(block(release, 'checks', 2), r'(?m)^    uses: \./\.github/workflows/checks\.yml[ \t]*$')
        build = block(release, 'build', 2)
        self.assertRegex(build, r'(?m)^    needs: checks[ \t]*$')
        self.assertIn('PACKAGE_VERSION: ${{ needs.checks.outputs.package_version }}', build)
        self.assertNotRegex(build, r'(?m)^    continue-on-error:[ \t]*true')

        launcher = block(checks, 'launcher', 2)
        linters = [step for step in steps(launcher) if 'actionlint' in step]
        self.assertEqual(len(linters), 1)
        lint = linters[0]
        self.assertRegex(lint, r'go install github\.com/rhysd/actionlint/cmd/actionlint@v\d+\.\d+\.\d+')
        # The bare invocation checks every workflow, including the publisher.
        self.assertRegex(lint, r'(?m)^          "\$RUNNER_TEMP/bin/actionlint"[ \t]*$')
        self.assertNotRegex(lint, r'(?m)^        (?:if:|continue-on-error:[ \t]*true)')
        self.assertLess(launcher.index(lint), launcher.index('go test ./...'))
        for job in ('windows', 'gameplay', 'era_client'):
            body = block(checks, job, 2)
            self.assertRegex(body, r'(?m)^    needs: launcher[ \t]*$')
            self.assertNotRegex(body, r'(?m)^    continue-on-error:[ \t]*true')
        windows = block(checks, 'windows', 2)
        self.assertRegex(windows, r'(?m)^    runs-on: windows-')
        self.assertIn('go test ./...', windows)

        # Build jobs never push. The publisher receives its API token explicitly.
        for workflow in (checks, release, publish):
            checkouts = [step for step in steps(workflow) if 'uses: actions/checkout@' in step]
            self.assertTrue(checkouts)
            for checkout in checkouts:
                self.assertRegex(checkout, r'(?m)^          persist-credentials: false[ \t]*$')
                self.assertIn('ref: ${{ github.sha }}', checkout)

        build_name = re.search(r'^name: (.+)', release)[1]
        trigger = block(block(publish, 'on'), 'workflow_run', 2)
        self.assertIn(f"workflows: ['{build_name}']", trigger)
        self.assertIn('branches: [main]', trigger)
        self.assertIn('types: [completed]', trigger)
        publisher = block(publish, 'publish', 2)
        guard = re.search(r'(?ms)^    if: >-\n(.*?)(?=^    runs-on:)', publisher)
        self.assertIsNotNone(guard)
        self.assertEqual(' '.join(guard[1].split()), (
            "github.event.workflow_run.conclusion == 'success' && "
            "github.event.workflow_run.head_branch == 'main' && "
            'github.event.workflow_run.head_repository.full_name == github.repository && '
            "(github.event.workflow_run.event == 'push' || github.event.workflow_run.event == 'workflow_dispatch')"
        ))
        self.assertIn('cancel-in-progress: false', block(publish, 'concurrency'))
        self.assertIn('run: python3 scripts/publish_latest.py --select-build-output "$GITHUB_OUTPUT"', publisher)
        downloads = [step for step in steps(publisher) if 'uses: actions/download-artifact@' in step]
        self.assertEqual(len(downloads), 2)
        self.assertEqual({re.search(r'(?m)^          name: (\S+)', step)[1] for step in downloads},
                         {'portable-zip', 'era-client-zip'})
        for download in downloads:
            self.assertIn('run-id: ${{ steps.build.outputs.run_id }}', download)
            self.assertIn("if: steps.build.outputs.run_id != ''", download)
        self.assertIn("--sha '${{ steps.build.outputs.sha }}'", publisher)

    def test_current_workflows(self):
        self.check_workflows(CHECKS.read_text(), RELEASE.read_text(), PUBLISH.read_text())

    def test_operational_regressions_are_rejected(self):
        checks, release, publish = CHECKS.read_text(), RELEASE.read_text(), PUBLISH.read_text()
        mutations = (
            ('pull-request validation removed', 0, '  pull_request:', '  lost_pull_request:'),
            ('duplicate branch push', 0, '      - main\n', "      - main\n      - 'codex/**'\n"),
            ('checks not callable', 0, '  workflow_call:', '  lost_workflow_call:'),
            ('Windows launcher tests removed', 0, '  windows:', '  lost_windows:'),
            ('lint skipped', 0, '      - name: Lint GitHub Actions workflows\n',
             '      - name: Lint GitHub Actions workflows\n        if: false\n'),
            ('publisher lint omitted', 0, '          "$RUNNER_TEMP/bin/actionlint"\n',
             '          "$RUNNER_TEMP/bin/actionlint" .github/workflows/checks.yml\n'),
            ('credentials persisted', 0, 'persist-credentials: false', 'persist-credentials: true'),
            ('manual build removed', 1, '  workflow_dispatch:', '  lost_workflow_dispatch:'),
            ('automatic build on push', 1, 'on:\n  workflow_dispatch:\n', 'on:\n  push:\n  workflow_dispatch:\n'),
            ('build without checks', 1, '    uses: ./.github/workflows/checks.yml', '    uses: ./.github/workflows/other.yml'),
            ('compile before checks', 1, '    needs: checks\n', '    needs: []\n'),
            ('build credentials persisted', 1, 'persist-credentials: false', 'persist-credentials: true'),
            ('publication success gate weakened', 2, "      github.event.workflow_run.conclusion == 'success'",
             "      github.event.workflow_run.conclusion != 'cancelled'"),
            ('publisher checks out build source', 2, 'ref: ${{ github.sha }}',
             'ref: ${{ github.event.workflow_run.head_sha }}'),
            ('artifacts from another run', 2, 'run-id: ${{ steps.build.outputs.run_id }}',
             'run-id: ${{ github.event.workflow_run.id }}'),
        )
        for label, target, before, after in mutations:
            with self.subTest(label=label):
                values = [checks, release, publish]
                self.assertIn(before, values[target])
                values[target] = values[target].replace(before, after, 1)
                with self.assertRaises(AssertionError):
                    self.check_workflows(*values)


if __name__ == '__main__':
    unittest.main()
