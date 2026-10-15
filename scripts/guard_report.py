#!/usr/bin/env python3
"""Require a complete passing exact-head report for the committed fixtures."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def check_report(path, head, guard_result, checks_result):
    if guard_result != 'success' or checks_result != 'success':
        raise ValueError('All preceding guard and package checks must succeed')
    report = json.loads(path.read_text())
    catalog_path = ROOT / 'tests/guard_fixtures.json'
    expected_ids = [case['id'] for case in json.loads(catalog_path.read_text())['fixtures']]
    if type(report['schema_version']) is not int or report['schema_version'] != 2:
        raise ValueError('Unsupported report version')
    if report['head_sha'] != head or report['passed'] is not True:
        raise ValueError('Report must pass at this exact head')
    if report['catalog_sha256'] != hashlib.sha256(catalog_path.read_bytes()).hexdigest():
        raise ValueError('Report catalog differs from the committed fixtures')
    if report['fixture_ids'] != expected_ids:
        raise ValueError('Missing, duplicate, reordered or unknown fixture results')
    if type(report['fixture_count']) is not int or report['fixture_count'] != len(expected_ids):
        raise ValueError('Wrong fixture count')
    return len(expected_ids)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--head', required=True)
    parser.add_argument('--guard-result', required=True)
    parser.add_argument('--checks-result', required=True)
    args = parser.parse_args()
    try:
        count = check_report(args.report, args.head, args.guard_result, args.checks_result)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('ERROR ' + str(exc), file=sys.stderr)
        return 1
    print(f'Complete exact-head fixture report: {count} passing fixtures')
    return 0


if __name__ == '__main__':
    sys.exit(main())
