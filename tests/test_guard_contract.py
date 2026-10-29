"""Bounded integration controls; guard syntax lives in committed fixtures."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_zips import build
from validate import bundle_text, referenced_tools, rendered_view_references, validate
CATALOG = json.loads((ROOT / 'tests/guard_fixtures.json').read_text())['fixtures']
RAW_HTML_KINDS = [(r['id'], r['text']) for r in CATALOG if r['id'].startswith('R2-HTML-')]
RAW_HTML_CONTROLS = [(r['id'], r['text']) for r in CATALOG if r['id'].startswith('C-HTML-')]
ASCII_CONTROLS = [(r['id'], r['text']) for r in CATALOG if r['id'].startswith('C-M-')]

class GuardContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='skill-guard-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns('.git', '.venv', 'dist', '__pycache__', 'reports'))
        self.lock = json.loads((self.root / 'tools.lock.json').read_text())
        self.tools = {item['name']: item for item in self.lock['tools']}
        self.manifest = json.loads((self.root / 'manifest.json').read_text())

    def test_diagnostic_reparse_checks_both_policies(self):
        from unittest.mock import patch
        from validate import RETIRED_TOOLS, checked_value, decoded_source_line, inspection_result, inspection_values
        value = 'caf\u00e9 submit_feedback'
        names = frozenset(self.tools)
        inspection_result.cache_clear()
        with patch('validate.inspection_values', return_value=((1, 1, value),)):
            with patch('validate.checked_value', wraps=checked_value) as check:
                self.assertEqual(1, decoded_source_line('Diagnostic line.', 1, 1, '\u00e9', names))
                check.assert_called_once_with(value, names | RETIRED_TOOLS)
        inspection_result.cache_clear()
        inspection_values.cache_clear()

    def test_governed_proposal_tools_pass_in_write_skill(self):
        source = (self.root / 'skills/plainrouter-budget-proposal/SKILL.md').read_text()
        references = referenced_tools(source, set(self.tools))
        self.assertTrue({'propose-actions', 'dry_run_actions'} <= references)
        self.assertEqual([], validate(self.root))

    def test_unmodified_bundles_pass(self):
        self.assertEqual([], validate(self.root))
        research = (self.root / 'skills/plainrouter-ad-research/SKILL.md').read_text()
        for required in [
            '### Competitor activity (published by Meta)',
            '### Your results (counted by Plainrouter)',
            "Ad Library figures are published by Meta. Plainrouter has not counted these figures. Plainrouter counts the customer's own arrivals and conversions separately; competitor results are unavailable.",
        ]:
            self.assertIn(required, research)
        # Literal comparisons remain prose in every original document.
        for path in (self.root / 'skills').rglob('*.md'):
            path.write_text(path.read_text() + '\nReport when spend < budget.\n')
        self.assertEqual([], validate(self.root))

    def test_get_action_inside_get_action_batch_is_not_a_reference(self):
        result = referenced_tools('get_action_batch', set(self.tools))
        self.assertIn('get_action_batch', result)
        self.assertNotIn('get_action', result)

    def test_reviewed_external_tool_contract(self):
        """External discovery is explicit and cannot launder locked writes."""
        path = self.root / 'skills/plainrouter-counted-brief/SKILL.md'
        original = path.read_text()
        declared = original.replace('"tools": "', '"external-tools": "ads_library_search", "tools": "')
        path.write_text(declared + '\nUse `ads_library_search` through its discovered schema.\n')
        self.assertEqual([], validate(self.root))
        cases = [
            ('undeclared', original + '\nUse `ads_library_search`.\n', 'workflow references differ'),
            ('unknown', declared.replace('ads_library_search', 'unreviewed_search'), 'External tool not allowlisted: unreviewed_search'),
            ('locked write', declared.replace('ads_library_search', 'submit_feedback'), 'forbidden tool reference: submit_feedback'),
            ('wrong inventory', original.replace('"tools": "', '"tools": "ads_library_search ') + '\nUse `ads_library_search`.\n', 'tool absent from tools.lock.json: ads_library_search'),
            ('duplicate', declared.replace('ads_library_search', 'ads_library_search ads_library_search'), 'Invalid declared external tool inventory'),
            ('Meta create', original + '\nads_create_campaign\n', 'forbidden tool reference: ads_create_campaign'),
            ('Meta update', original + '\nads_update_ad\n', 'forbidden tool reference: ads_update_ad'),
            ('Meta delete', original + '\nads_delete_ad\n', 'forbidden tool reference: ads_delete_ad'),
            ('Meta activate', original + '\nads_activate_entity\n', 'forbidden tool reference: ads_activate_entity'),
            ('Meta boost', original + '\nads_boost_ig_post\n', 'forbidden tool reference: ads_boost_ig_post'),
            ('Meta markup', original + '\n`ads_cre**ate**_campaign`\n', 'forbidden tool reference: ads_create_campaign'),
        ]
        for label, source, diagnostic in cases:
            with self.subTest(external=label):
                path.write_text(source)
                self.assertIn(diagnostic, '\n'.join(validate(self.root)))
        path.write_text(original + '\nads_update_ad\n')
        misclassified = dict(self.tools['get_account_state'], name='ads_update_ad', grant_operation='ads_update_ad')
        (self.root / 'tools.lock.json').write_text(json.dumps(dict(self.lock, tools=self.lock['tools'] + [misclassified])))
        self.assertIn('forbidden tool reference: ads_update_ad', '\n'.join(validate(self.root)))
        collision = dict(self.tools['submit_feedback'], name='ads_library_search', grant_operation='ads_library_search')
        (self.root / 'tools.lock.json').write_text(json.dumps(dict(self.lock, tools=self.lock['tools'] + [collision])))
        self.assertIn('external tool collides with locked tool: ads_library_search', '\n'.join(validate(self.root)))

    def test_creative_store_inside_store_from_url_is_not_a_reference(self):
        result = referenced_tools('launch.creatives.store-from-url', set(self.tools))
        self.assertIn('launch.creatives.store-from-url', result)
        self.assertNotIn('launch.creatives.store', result)


    def test_restored_portable_contract(self):
        """Independent whole-bundle mutations restore the portable contracts."""
        baseline = Path(self.temp.name) / 'pristine'
        shutil.copytree(self.root, baseline)
        relative = 'skills/plainrouter-counted-brief/SKILL.md'
        def append(text):
            path = self.root / relative
            path.write_text(path.read_text() + '\n' + text + '\n')
        def entrypoint_edit(old, new):
            path = self.root / relative
            path.write_text(path.read_text().replace(old, new))
        def resource(relative, content):
            path = self.root / 'skills/plainrouter-counted-brief' / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        def mismatch_sha():
            path = self.root / 'manifest.json'
            manifest = json.loads(path.read_text())
            manifest['core_sha'] = '0' * 40
            path.write_text(json.dumps(manifest))
        def symlink():
            (self.root / 'skills/plainrouter-counted-brief/references/link.md').symlink_to('../SKILL.md')
        cases = [
            ('nonportable field', lambda: entrypoint_edit('\n---\n\n#', '\ndisable-model-invocation: true\n---\n\n#'), 'Invalid portable frontmatter'),
            ('description limit', lambda: entrypoint_edit(next(line for line in (self.root / relative).read_text().splitlines() if line.startswith('description: ')), 'description: ' + json.dumps('x' * 201)), 'Invalid description'),
            ('metadata strings', lambda: entrypoint_edit('"version": "0.1.0"', '"version": 1'), 'Metadata must map strings to strings'),
            ('entrypoint size', lambda: append('\n' * 500), 'SKILL.md must stay under 500 lines'),
            ('bundle link boundary', lambda: append('[outside](../../README.md)'), 'missing or out-of-bundle reference'),
            ('flat resources', lambda: resource('references/nested/facts.md', b'Facts.\n'), 'supporting references must be Markdown one level deep'),
            ('brand', lambda: append('PlainRouter facts.'), 'brand must be Plainrouter'),
            ('synthetic evidence', lambda: append('Use sandbox figures as evidence.'), 'sandbox belongs only in the synthetic README demo'),
            ('core revision', mismatch_sha, 'Manifest and lock must share a recorded core SHA'),
            ('symlink resource', symlink, 'symlink resources are not allowed'),
            ('mandatory discovery', lambda: entrypoint_edit('tools/list', 'tool listing'), 'Discover tools/list before using tools'),
            ('binary resource encoding', lambda: resource('references/payload.bin', b'\xff\x00dry_run_actions\x00'), 'ASCII policy: line 1: invalid UTF-8 byte 0xFF'),
            ('unknown wire tool', lambda: append('```json\n{"method":"tools/call","params":{"name":"made-up-tool"}}\n```'), 'tool absent from tools.lock.json: made-up-tool'),
        ]
        for label, mutate, expected in cases:
            with self.subTest(contract=label):
                shutil.rmtree(self.root)
                shutil.copytree(baseline, self.root)
                mutate()
                try:
                    errors = validate(self.root)
                except ValueError as exc:
                    errors = [str(exc)]
                self.assertIn(expected, '\n'.join(errors))
        names = set(self.tools)
        for tag in ['<a/>', '</foo >', '<b\n title=">">', '<b _flag:1=bare title="x>y">',
                    '<span title="&quot;">', '<span title="\\u0022">']:
            with self.subTest(valid_tag=tag):
                self.assertIn('revoke_grant', referenced_tools('revo' + tag + 'ke_grant', names))
        for tag in ['< a>', '<\nfoo>', '<bar/ >', '<a h*#ref="hi">',
                    '<a href="hi\'>', '<a href=hi\'>', '<a href=\'bar\'title=title>',
                    '</a href="foo">', '<b\n\n>']:
            with self.subTest(invalid_or_outside_tag=tag):
                self.assertNotIn('revoke_grant', referenced_tools('revo' + tag + 'ke_grant', names))

    def test_rendered_reader_contract(self):
        from rendered_text import rendered_strings
        names = set(self.tools)
        # Context regression and direct reader-view assertions.
        self.assertIn('revoke_grant', referenced_tools('Use `<span title="` then call revo<b title=">">ke_grant.', names))
        visible = rendered_strings('| Tool | Note |\n| --- | --- |\n| revo<b></b>ke_grant | Facts |')[0]
        self.assertIn('revoke_grant', visible)
        self.assertNotIn('|', visible)
        self.assertNotIn('revoke_grant', rendered_strings('revo\n\nke_grant')[0])
        self.assertNotIn('revoke_grant', rendered_strings('<p>revo</p><p>ke_grant</p>')[0])
        values = rendered_strings('[shown](https://example.invalid/revoke_grant "submit_feedback") <span data-tool="verify_signal_ingestion">Facts</span>')
        self.assertIn('https://example.invalid/revoke_grant', values)
        self.assertIn('submit_feedback', values)
        self.assertIn('verify_signal_ingestion', values)
        prose = [
            'Report when spend < budget.', 'a < b > c', '<workspace_id>',
            '```ts\nconst rows: Map<string, Array<Row>> = new Map<string, Array<Row>>();\nfunction pick<T>(x: T): T { return x; }\n```',
            r'An escaped \<tag> stays literal.',
        ]
        for text in prose:
            with self.subTest(prose=text):
                self.assertEqual(set(), referenced_tools(text, names))
        path = self.root / 'skills/plainrouter-counted-brief/SKILL.md'
        path.write_text(path.read_text() + '\n' + '\n\n'.join(prose) + '\n')
        self.assertEqual([], validate(self.root))

    def test_two_rendered_views(self):
        from rendered_text import html_views
        names = frozenset(self.tools)
        for tag in ['head', 'template', 'title', 'style', 'script', 'noscript', 'textarea', 'iframe', 'rp']:
            with self.subTest(element=tag):
                views = html_views('<' + tag + '>revoke_grant</' + tag + '>')
                self.assertIn('revoke_grant', views[0][0])
                if tag == 'head':
                    self.assertIn('revoke_grant', views[1][0])
        for text in ['revo<span hidden>x</span>ke_grant', 'revo<span style="display:none">x</span>ke_grant',
                     'revo<span style="visibility:hidden">x</span>ke_grant', 'revo<rp>x</rp>ke_grant',
                     'revo<div hidden>x</div>ke_grant', 'revo<template>x</template>ke_grant']:
            with self.subTest(projection=text):
                first, second = rendered_view_references(text, names)
                self.assertNotIn('revoke_grant', first)
                self.assertIn('revoke_grant', second)
        first, second = rendered_view_references('<span hidden>revoke_grant</span>', names)
        self.assertIn('revoke_grant', first)
        self.assertNotIn('revoke_grant', second)
        for text in ['<head>\n\nrevoke_grant', 'Intro <head> text.\n\nrevoke_grant']:
            with self.subTest(head=text):
                first, second = rendered_view_references(text, names)
                self.assertIn('revoke_grant', first)
                self.assertIn('revoke_grant', second)
        self.assertIn('revoke_grant', html_views('revo<div hidden>x</div>ke_grant')[1][0])
        self.assertNotIn('revoke_grant', html_views('revo<div>x</div>ke_grant')[1][0])
        for style in ['DISPLAY : none !important', 'color:red; visibility: hidden', 'display: /* note */ none']:
            self.assertIn('revoke_grant', html_views('revo<span style="' + style + '">x</span>ke_grant')[1][0])
        self.assertNotIn('revoke_grant', html_views('revo<span style="display:none;display:inline">x</span>ke_grant')[1][0])
        # Void hidden nodes have no content and cannot hide later nodes.
        self.assertIn('revoke_grant', html_views('<input hidden>revoke_grant')[1][0])
        self.assertIn('revoke_grant', html_views('revo<br hidden/>ke_grant')[1][0])
        views = html_views('<template data-tool="revoke_grant">Facts</template>')
        self.assertIn('revoke_grant', views[0])
        self.assertIn('revoke_grant', views[1])

    def test_shared_markdown_parse(self):
        from markdown_parse import parse_markdown
        from cmarkgfm import github_flavored_markdown_to_html
        from cmarkgfm.cmark import Options
        for label, source in RAW_HTML_KINDS:
            with self.subTest(html=label):
                rendered, kind = parse_markdown(source)
                self.assertEqual('html_inline' if int(label.rsplit('-', 1)[1]) <= 6 else 'html_block', kind)
                self.assertEqual(github_flavored_markdown_to_html(source, options=Options.CMARK_OPT_UNSAFE), rendered)
        for label, source in RAW_HTML_CONTROLS:
            with self.subTest(control=label):
                self.assertIsNone(parse_markdown(source)[1])
        # Extension tables and ordinary bundles keep their rendering unchanged.
        sources = ['| A | B |\n| --- | --- |\n| x | y |', '***Facts*** and https://example.invalid/.']
        sources += [p.read_text() for p in (self.root / 'skills').rglob('*.md')]
        for source in sources:
            self.assertIsNone(parse_markdown(source)[1])
            self.assertEqual(github_flavored_markdown_to_html(source, options=Options.CMARK_OPT_UNSAFE), parse_markdown(source)[0])

    def test_restored_packaging_contract(self):
        """Repeatable, complete ZIPs reject stale hashes and unsafe contracts."""
        first_dir = Path(self.temp.name) / 'first'
        first = build(self.root, first_dir)
        self.assertEqual(first, build(self.root, Path(self.temp.name) / 'second'))
        self.assertEqual(7, len(first))
        for item in first:
            path = first_dir / item['file']
            self.assertEqual(item['bytes'], path.stat().st_size)
            self.assertEqual(item['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
            with zipfile.ZipFile(path) as archive:
                prefix = item['skill'] + '/'
                self.assertTrue(all(name.startswith(prefix) for name in archive.namelist()))
                self.assertIn(prefix + 'SKILL.md', archive.namelist())
                self.assertEqual((self.root / 'LICENSE').read_bytes(), archive.read(prefix + 'LICENSE'))
                for resource in (self.root / 'skills' / item['skill']).rglob('*.md'):
                    relative = resource.relative_to(self.root / 'skills' / item['skill']).as_posix()
                    self.assertEqual(resource.read_bytes(), archive.read(prefix + relative))
                self.assertIsNone(archive.testzip())
        self.assertEqual(first, json.loads((first_dir / 'manifest.json').read_text())['artifacts'])
        reference = self.root / 'skills/plainrouter-counted-brief/references/reporting.md'
        reference.write_text(reference.read_text() + '\nAn additional coverage note.\n')
        self.assertEqual([], validate(self.root))
        with self.assertRaisesRegex(ValueError, 'Committed ZIP checksum differs'):
            build(self.root, Path(self.temp.name) / 'stale')
        updated = build(self.root, Path(self.temp.name) / 'updated', update_manifest=True)
        self.assertEqual(updated, build(self.root, Path(self.temp.name) / 'rebuilt'))
        self.assertEqual(updated[0]['sha256'], json.loads((self.root / 'manifest.json').read_text())['skills'][0]['zip_sha256'])
        reference.write_text(reference.read_text() + '\nCall `get_not_in_lock`.\n')
        output = Path(self.temp.name) / 'unsafe'
        with self.assertRaisesRegex(ValueError, 'tool absent from tools.lock.json'):
            build(self.root, output)
        self.assertFalse(output.exists())

    def test_ascii_policy_diagnostics(self):
        """Byte errors and decoded characters retain the physical source line."""
        cases = [(b'Facts\n\xff', 'line 2: invalid UTF-8 byte 0xFF at byte 6'),
                 (b'Facts\n\r', 'line 2: U+000D'),
                 ('Facts\n\ufeff'.encode('utf-8'), 'line 2: U+FEFF'),
                 (b'Facts\n&#x8;', 'line 2: decoded U+0008'),
                 (b'Facts\n&#144;', 'line 2: decoded U+0090'),
                 (b'Facts\n\\u000a\\u034f', 'line 2: decoded U+034F'),
                 (b'Facts\n&#xFE0F;', 'line 2: decoded U+FE0F'),
                 (b'Facts\n\\u005cu034f', 'line 2: decoded U+034F'),
                 (b'Facts\n&#92;u034f', 'line 2: decoded U+034F'),
                 (b'Facts\n&#x110000;', 'line 2: decoded U+FFFD'),
                 (b'[x](https://example.invalid/\n"&eacute;")', 'line 2: decoded U+00E9'),
                 (b'Facts &#10; &eacute;', 'line 1: decoded U+00E9')]
        for data, expected in cases:
            with self.subTest(expected=expected):
                _, error = bundle_text(data)
                self.assertIn(expected, error)
        self.assertEqual(('Facts\n&amp;#xFE0F;', None), bundle_text(b'Facts\n&amp;#xFE0F;'))
        for label, source in ASCII_CONTROLS:
            with self.subTest(control=label):
                self.assertEqual((source, None), bundle_text(source.encode('utf-8')))

    def test_encoded_tag_rejection_family_is_preserved(self):
        from markdown_parse import parse_markdown
        cases = [('call revo&lt;b&gt;ke_grant now', 'revoke_grant'),
                 ('call submit&lt;span title=&quot;&gt;&quot;&gt;_feedback now', 'submit_feedback'),
                 ('call revo&#60;b&#62;ke_grant now', 'revoke_grant')]
        path = self.root / 'skills/plainrouter-counted-brief/SKILL.md'
        original = path.read_text()
        for source, expected in cases:
            with self.subTest(encoded_tag=source):
                self.assertIsNone(bundle_text(source.encode())[1])
                self.assertIsNone(parse_markdown(source)[1])
                self.assertIn(expected, referenced_tools(source, frozenset(self.tools)))
                path.write_text(original + '\n' + source + '\n')
                self.assertIn(str(path.relative_to(self.root)) + ': forbidden tool reference: ' + expected,
                              validate(self.root))

    def test_unresolved_registration_identifies_tool(self):
        """Missing/ambiguous registered classes stop with their identifier."""
        fixture = Path(self.temp.name) / 'synthetic-core'
        fixture.mkdir()
        definitions = fixture / 'definitions'
        definitions.mkdir()
        (definitions / 'grants.php').write_text("<?php\nreturn ['read' => ['safe'], 'write' => [], 'admin' => []];\n")
        (definitions / 'BoundedCallTool.php').write_text('private const array GRANT_OPERATIONS = [];\n')
        server = definitions / 'PlainRouterServer.php'
        server.write_text('use Example\\Tools\\MissingTool;\npublic const array TOOLS = [MissingTool::class];\n')
        identity = subprocess.check_output(['git', '-C', str(ROOT), 'show', '-s', '--format=%an%n%ae', 'HEAD'], text=True).splitlines()
        subprocess.run(['git', 'init', '--quiet', str(fixture)], check=True, capture_output=True)
        def commit():
            subprocess.run(['git', '-C', str(fixture), 'add', '.'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(fixture), '-c', 'user.name=' + identity[0], '-c', 'user.email=' + identity[1], '-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'Synthetic registration fixture'], check=True, capture_output=True)
        def reject():
            target = fixture / 'result.json'
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/generate_lock.py'), '--core', str(fixture), '--ref', 'HEAD', '--output', str(target)], capture_output=True, text=True)
            self.assertEqual(1, result.returncode)
            self.assertIn('MissingTool', result.stderr)
            self.assertFalse(target.exists())
        commit()
        with self.subTest(class_state='missing'):
            reject()
        for directory in ['one', 'two']:
            folder = fixture / directory
            folder.mkdir()
            (folder / 'MissingTool.php').write_text('namespace Example\\Tools;\n')
        commit()
        with self.subTest(class_state='ambiguous'):
            reject()
        server.write_text('public const array TOOLS = [MissingTool::class];\n')
        commit()
        with self.subTest(class_state='missing import'):
            reject()


if __name__ == '__main__':
    unittest.main()
