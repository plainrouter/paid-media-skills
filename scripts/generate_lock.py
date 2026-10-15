#!/usr/bin/env python3
"""Generate a minimal contract from a local checkout's pinned git revision."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


def generate(core, ref):
    def git(*args):
        try:
            return subprocess.check_output(
                ['git', '-C', str(core), *args], text=True, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError:
            raise ValueError('Cannot read the requested local git revision') from None

    sha = git('rev-parse', '--verify', ref + '^{commit}').strip()
    paths = [p for p in git('ls-tree', '-r', '--name-only', sha).splitlines() if p.endswith('.php')]
    cache = {}

    def read(path):
        if path not in cache:
            cache[path] = git('show', sha + ':' + path)
        return cache[path]

    def by_basename(basename):
        matches = [p for p in paths if Path(p).name == basename]
        if len(matches) != 1:
            raise ValueError('Cannot uniquely locate the required contract definition')
        return read(matches[0])

    def by_class(full):
        namespace, cls = full.rsplit('\\', 1)
        matches = []
        for path in paths:
            if Path(path).name == cls + '.php':
                source = read(path)
                declared = re.search(r'namespace\s+([^;]+);', source)
                if declared and declared[1] == namespace:
                    matches.append(source)
        if len(matches) != 1:
            raise ValueError('Cannot uniquely resolve registered tool class ' + cls)
        return matches[0]

    grants = by_basename('grants.php')
    tiers = {tier: set(re.findall(r"'([^']+)'", block)) for tier, block in
             re.findall(r"'(read|write|admin)'\s*=>\s*\[(.*?)\]", grants, re.S)}
    if set(tiers) != {'read', 'write', 'admin'}:
        raise ValueError('Cannot read the tier registry; review generator before continuing')
    dispatch = by_basename('BoundedCallTool.php')
    alias_block = dispatch.split('private const array GRANT_OPERATIONS = [', 1)[1].split('];', 1)[0]
    aliases = dict(re.findall(r"'([^']+)'\s*=>\s*'([^']+)'", alias_block))
    server = by_basename('PlainRouterServer.php')
    imports = {name: full for full, name in re.findall(r'use ([^;]+\\(\w+));', server)}
    block = server.split('public const array TOOLS = [', 1)[1].split('];', 1)[0]
    classes = re.findall(r'(\w+)::class', block)
    if not classes:
        raise ValueError('No production registrations found')
    explicit_exclusions = {'revoke_grant', 'actions.rules.create',
                           'actions.rules.update', 'actions.tests.create'}
    result = []
    for cls in classes:
        if cls not in imports:
            raise ValueError('Missing class import for registered tool ' + cls)
        source = by_class(imports[cls])
        named = re.search(r"#\[Name\('([^']+)'\)\]", source)
        constant = re.search(r"public const string NAME = '([^']+)'", source)
        name = named[1] if named else constant[1] if constant else re.sub(
            r'(?<!^)(?=[A-Z])', '-', cls).lower()
        if '#[IsReadOnly]' in source or '#[IsReadOnly(true)]' in source:
            effect = 'read'
        else:
            # SK9-E: absence of a read-only annotation is a write effect.
            effect = 'write'
        if name == 'launcher.execute_batch' and 'not_executable_in_phase_b1' not in source:
            raise ValueError('Batch execution refusal changed; re-audit effect')
        operation = aliases.get(name, name)
        tier = 'read' if name == 'list_workspaces' else next(
            (t for t in ['read', 'write', 'admin'] if operation in tiers[t]), None)
        if tier is None:
            raise ValueError('No grant tier found for ' + name)
        declared = re.search(r'function minimumExecutionTier\(\).*?WorkspaceTokenTier::(\w+)', source, re.S)
        if declared and declared[1].lower() != tier:
            raise ValueError('Declared tier differs from registry for ' + name)
        exclusion_rules = []
        if imports[cls].startswith('App\\Domains\\Launch\\'):
            exclusion_rules.append('launch-domain')
        # Required scopes, rather than conditional creative-action checks in
        # general proposal tools, define the creative grant exclusion.
        scope_blocks = re.findall(r'function requiredAgentScopes\(\).*?\{(.*?)\n    \}', source, re.S)
        principal_calls = re.findall(r'\$this->principal\((.*?)\)', source, re.S)
        if any(re.search(r"'creative\.(?:read|write)'", body)
               for body in scope_blocks + principal_calls):
            exclusion_rules.append('creative-grant')
        if name in explicit_exclusions:
            exclusion_rules.append('explicit-exclusion')
        result.append({'name': name, 'minimum_tier': tier, 'effect': effect,
                       'grant_operation': operation, 'sk7': bool(exclusion_rules),
                       'sk7_rules': exclusion_rules})
    if len({t['name'] for t in result}) != len(result):
        raise ValueError('Duplicate registered tool name')
    return {'schema_version': 3, 'core_sha': sha, 'protocol_methods': ['tools/list'],
            'tools': sorted(result, key=lambda t: t['name'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', required=True, type=Path)
    parser.add_argument('--ref', default='origin/main')
    parser.add_argument('--output', type=Path, default=Path('tools.lock.json'))
    args = parser.parse_args()
    try:
        lock = generate(args.core, args.ref)
    except (ValueError, KeyError, IndexError) as exc:
        print('Contract generation failed: ' + str(exc), file=sys.stderr)
        return 1
    args.output.write_text(json.dumps(lock, indent=2) + '\n')
    print(f"Generated {len(lock['tools'])} production entries from {lock['core_sha']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
