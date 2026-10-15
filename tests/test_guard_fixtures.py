"""Run the fixed SK9-P fixture catalog, without constructing syntax cases."""
import argparse
from collections import Counter
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import validate as guard
from markdown_parse import parse_markdown, table_width

CATALOG_PATH = ROOT / 'tests/guard_fixtures.json'


def catalog():
    data = json.loads(CATALOG_PATH.read_text())
    assert data['schema_version'] == 1
    assert set(data['forms']) == {str(form) for form in range(1, 19)}
    ids, counts = set(), Counter()
    for case in data['fixtures']:
        assert case['id'] not in ids, 'Duplicate fixture: ' + case['id']
        ids.add(case['id'])
        assert str(case['form']) in data['forms'], case['id']
        assert case['check'] in {'ascii', 'name', 'html'}, case['id']
        assert case['expected'] in {'reject', 'pass'}, case['id']
        counts[(case['form'], case['check'], case['expected'])] += 1
    for form in range(1, 19):
        for check in ['ascii', 'name']:
            for expected in ['reject', 'pass']:
                assert counts[(form, check, expected)] > 0, (form, check, expected)
    return data


def clear_guard_caches():
    for module in [guard]:
        for value in vars(module).values():
            if callable(value) and hasattr(value, 'cache_clear'):
                value.cache_clear()


def run_fixture(case):
    """Every fixture executes both policies; its expected assertion is literal."""
    tools = {item['name']: item for item in json.loads((ROOT / 'tools.lock.json').read_text())['tools']}
    names = frozenset(tools)
    data = bytes.fromhex(case['bytes_hex']) if 'bytes_hex' in case else case['text'].encode('utf-8')
    context = nullcontext()
    if 'collector_value' in case:
        # A collector-only value, absent from raw/rendered source, pins the
        # shared-path contract for any future native field.
        clear_guard_caches()
        context = patch('validate.markdown_literals', return_value=((1, 1, case['collector_value']),))
    try:
        with context:
            source, violation = guard.bundle_text(data, names)
            references = guard.referenced_tools(source, names) if source is not None else set()
            excluded = {name for name in references if name not in tools or guard.forbidden(tools[name], case.get('tier', 'read'))}
            html_kind = parse_markdown(source)[1] if source is not None else None
        if 'line' in case:
            assert violation is not None and f"line {case['line']}:" in violation, case['id'] + ': wrong definition diagnostic line'
        if 'name_line' in case:
            locations = set(guard.inspection_result(source, names)[2])
            assert {(name, case['name_line']) for name in case['names']} <= locations, case['id'] + ': wrong definition name line'
        if 'table_width' in case:
            assert table_width(case['text'].split('\n')[case['row_line'] - 1]) == case['table_width'], case['id'] + ': wrong native table width'
        if case['check'] == 'ascii':
            rejected = violation is not None
        elif case['check'] == 'html':
            rejected = html_kind is not None
        else:
            rejected = bool(excluded)
            if case['expected'] == 'reject':
                assert set(case['names']) <= excluded, f"{case['id']}: missing names {set(case['names']) - excluded}"
        assert rejected == (case['expected'] == 'reject'), f"{case['id']}: {case['check']} expected {case['expected']}; ASCII={violation!r}, forbidden={sorted(excluded)}, HTML={html_kind}"
    finally:
        if 'collector_value' in case:
            clear_guard_caches()


class FixedFixtureTest(unittest.TestCase):
    executed = []

    def test_fixed_fixtures(self):
        for case in catalog()['fixtures']:
            with self.subTest(fixture=case['id'], form=case['form'], check=case['check']):
                run_fixture(case)
            self.executed.append(case['id'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--head', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.head):
        parser.error('--head must be a full commit SHA')
    started = time.monotonic()
    FixedFixtureTest.executed = []
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FixedFixtureTest))
    report = {'schema_version': 2, 'head_sha': args.head,
              'catalog_sha256': hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest(),
              'fixture_ids': FixedFixtureTest.executed, 'fixture_count': len(FixedFixtureTest.executed),
              'passed': result.wasSuccessful(), 'seconds': round(time.monotonic() - started, 6)}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
