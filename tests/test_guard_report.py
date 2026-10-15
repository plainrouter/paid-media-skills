"""The completion gate refuses partial, stale or unsuccessful evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from guard_report import check_report
HEAD = 'a' * 40


class FixtureReportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fixture-report-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'guard.json'
        catalog_path = ROOT / 'tests/guard_fixtures.json'
        ids = [case['id'] for case in json.loads(catalog_path.read_text())['fixtures']]
        self.original = dict(schema_version=2, head_sha=HEAD, passed=True,
                             catalog_sha256=hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
                             fixture_ids=ids, fixture_count=len(ids))
        self.write(self.original)

    def write(self, report):
        self.path.write_text(json.dumps(report))

    def test_complete_report_passes(self):
        self.assertEqual(self.original['fixture_count'], check_report(self.path, HEAD, 'success', 'success'))

    def test_partial_duplicate_stale_or_failed_evidence_refuses(self):
        changes = [('schema_version', True), ('head_sha', 'b' * 40), ('passed', False),
                   ('catalog_sha256', '0' * 64), ('fixture_count', True), ('fixture_count', 1),
                   ('fixture_ids', self.original['fixture_ids'][:-1]),
                   ('fixture_ids', self.original['fixture_ids'] + self.original['fixture_ids'][:1]),
                   ('fixture_ids', list(reversed(self.original['fixture_ids'])))]
        for field, value in changes:
            with self.subTest(field=field):
                changed = deepcopy(self.original)
                changed[field] = value
                self.write(changed)
                with self.assertRaises(ValueError):
                    check_report(self.path, HEAD, 'success', 'success')

    def test_missing_report_or_unsuccessful_steps_refuse(self):
        for state in ['failure', 'cancelled', 'skipped']:
            with self.subTest(state=state):
                with self.assertRaises(ValueError):
                    check_report(self.path, HEAD, state, 'success')
                with self.assertRaises(ValueError):
                    check_report(self.path, HEAD, 'success', state)
        self.path.unlink()
        with self.assertRaises(OSError):
            check_report(self.path, HEAD, 'success', 'success')

    def test_workflow_runs_only_fixed_fixtures_with_bounded_timeout(self):
        workflow = (ROOT / '.github/workflows/validate.yml').read_text()
        import re
        self.assertEqual(['guard'], re.findall(r'^  ([a-z]+):$', workflow.split('jobs:\n', 1)[1], re.M))
        self.assertIn('timeout-minutes: 15', workflow)
        self.assertIn('python tests/test_guard_fixtures.py --report reports/guard.json', workflow)
        self.assertIn('scripts/guard_report.py --report reports/guard.json', workflow)
        for removed in ['matrix:', 'strategy:', '--shard-', 'guard_shards.py', 'workflow_dispatch:']:
            self.assertNotIn(removed, workflow)
        self.assertIn('branches: [main]', workflow)
        self.assertIn('  pull_request:', workflow)


if __name__ == '__main__':
    unittest.main()
