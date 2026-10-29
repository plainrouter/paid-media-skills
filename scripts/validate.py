#!/usr/bin/env python3
"""Validate portable bundles against the recorded tool contract.

Raw and decoded text are both inspected. Markup within a tool name is
transparent during matching; literal lock-name underscores remain required.
Overlapping matches survive unless wholly contained by a longer lock name.
"""
import argparse
from functools import lru_cache
import json
from pathlib import Path
import re
import string
import sys
import unicodedata

from rendered_text import rendered_views
from markdown_parse import markdown_literals, parse_markdown

# Retired production names remain detectable so a lock refresh cannot make
# an old forbidden reference look like ordinary prose.
RETIRED_TOOLS = frozenset({'generate_background', 'get_generation',
                           'launcher.execute_batch', 'resume_generation'})

# Reviewed third-party tools are separate from the pinned Plainrouter lock.
# Client prefixes are resolved at discovery, never added to this inventory.
EXTERNAL_TOOLS = {'ads_library_search': {'provider': 'Meta Ads MCP', 'effect': 'read'}}
META_WRITE_TOOLS = frozenset({'ads_activate_entity', 'ads_boost_ig_post'})
META_WRITE_PREFIXES = ('ads_create_', 'ads_update_', 'ads_delete_')

FIELDS = {'name', 'description', 'license', 'compatibility', 'metadata'}
TOOL_PREFIX = re.compile(r'(?:get_|list_|verify_|submit_|dry_run_|revoke_|actions\.|launch\.|launcher\.)[a-z0-9_.-]+\Z')
PUNCTUATION_ESCAPE = re.compile(r'\\([' + re.escape(string.punctuation) + r'])')
UNICODE_ESCAPE = re.compile(r'\\u([0-9a-fA-F]{4})')
# CommonMark open/closing-tag grammar. Attribute quotes can contain < or >;
# an invalid earlier < cannot consume a later tag. Comments and processing
# instructions are not removed as name-splitting markup.
TAG_NAME = r'[A-Za-z][A-Za-z0-9-]*'
TAG_SPACE = r'[ \t]*(?:(?:\r\n|\n|\r)[ \t]*)?'
ATTRIBUTE_SPACE = r'(?:[ \t]+(?:(?:\r\n|\n|\r)[ \t]*)?|(?:\r\n|\n|\r)[ \t]*)'
ATTRIBUTE_NAME = r'[A-Za-z_:][A-Za-z0-9_.:-]*'
ATTRIBUTE_VALUE = r"(?:[^ \t\r\n\"'=<>`]+|'[^']*'|\"[^\"]*\")"
ATTRIBUTE = ATTRIBUTE_SPACE + ATTRIBUTE_NAME + '(?:' + TAG_SPACE + '=' + TAG_SPACE + ATTRIBUTE_VALUE + ')?'
HTML_TAG = re.compile('<(?:' + TAG_NAME + '(?:' + ATTRIBUTE + ')*' + TAG_SPACE + '/?|' +
                      '/' + TAG_NAME + TAG_SPACE + ')>')
FORMAT_CHARACTERS = {value: None for value in range(sys.maxunicode + 1)
                     if unicodedata.category(chr(value)) == 'Cf'}
MARKUP_GAP = r'[*_~`]*'
LETTER_DIGIT = r'[^\W_]'
META_WRITE_PATTERNS = [(prefix, re.compile(r'(?<!' + LETTER_DIGIT + r')' +
                       MARKUP_GAP.join(re.escape(char) for char in prefix) +
                       MARKUP_GAP + r'([a-z0-9_.-]*)')) for prefix in META_WRITE_PREFIXES]

ASCII_INVALID = re.compile(r'[^\x20-\x7e\n\t]')


def decoded_source_line(source, start, end, character, names=frozenset()):
    """Locate the physical line inside a multiline decoded inspection value."""
    start = max(1, start)
    for line, candidate in enumerate(source.split('\n')[start - 1:max(start, end)], start):
        # Diagnostic reparses use the same paired checker before locating text.
        inspection_result(candidate, names)
        if any(character in value for _, _, value in inspection_values(candidate)):
            return line
    return start


@lru_cache(maxsize=512)
def bundle_text(data, names=frozenset()):
    """Strictly decode bytes and locate an ASCII violation on its source line."""
    try:
        source = data.decode('utf-8', errors='strict')
    except UnicodeDecodeError as exc:
        line = data[:exc.start].count(b'\n') + 1
        return None, f'ASCII policy: line {line}: invalid UTF-8 byte 0x{data[exc.start]:02X} at byte {exc.start}'
    # Check the raw copy as well: decoding must not erase a control character.
    match = ASCII_INVALID.search(source)
    if match:
        line = source[:match.start()].count('\n') + 1
        return source, f'ASCII policy: line {line}: U+{ord(match[0]):04X} is not allowed'
    violation, _, _ = inspection_result(source, names)
    if violation is not None:
        start, end, character = violation
        line = decoded_source_line(source, start, end, character, names)
        return source, f'ASCII policy: line {line}: decoded U+{ord(character):04X} is not allowed'
    return source, None



@lru_cache(maxsize=16)
def name_patterns(names, markup):
    patterns = []
    for name in sorted(names):
        token = MARKUP_GAP.join(re.escape(char) for char in name) if markup else re.escape(name)
        pattern = re.compile(r'(?<!' + LETTER_DIGIT + r')(?=(' + token + r')(?!' + LETTER_DIGIT + r'))')
        patterns.append((name, pattern))
    return patterns


MARKUP_MARKERS = str.maketrans('', '', '*_~`')


def candidate_patterns(source, names, markup):
    # Removing transparent markers is only a necessary-condition filter. The
    # original matcher still decides boundaries, underscores and containment.
    candidate = source.translate(MARKUP_MARKERS) if markup else source
    return [(name, pattern) for name, pattern in name_patterns(names, markup)
            if (name.translate(MARKUP_MARKERS) if markup else name) in candidate]


def name_matches(source, names, markup=False):
    matches = []
    for name, pattern in candidate_patterns(source, names, markup):
        for match in pattern.finditer(source):
            start, stop = match.span(1)
            matches.append((name, start, stop))
    # Match every name independently, then suppress only full containment by a
    # strictly longer name. A sweep retains every partial overlap.
    farthest = [-1] * (max((len(name) for name in names), default=0) + 2)
    retained = []
    for name, start, stop in sorted(matches, key=lambda item: (item[1], -len(item[0]), -item[2])):
        length = len(name)
        if farthest[length + 1] < stop:
            retained.append((name, start, stop))
        for threshold in range(1, length + 1):
            farthest[threshold] = max(farthest[threshold], stop)
    return retained


@lru_cache(maxsize=8192)
def line_references(line, names, markup):
    return frozenset(name for name, _, _ in name_matches(line, names, markup))


def text_references(source, names, markup=False):
    # Neither canonical names nor transparent marker runs contain a newline.
    # Split only after whole-text decoding/tag removal, which may join lines.
    references = set()
    for line in source.splitlines():
        references.update(line_references(line, names, markup))
    return references


@lru_cache(maxsize=8192)
def normalization_values(source):
    """Keep every normalization stage; character references are never decoded here."""
    values = [source]
    previous = None
    while source != previous:
        previous = source
        source = UNICODE_ESCAPE.sub(lambda match: chr(int(match[1], 16)), source)
        values.append(source)
        source = PUNCTUATION_ESCAPE.sub(r'\1', source)
        values.append(source)
        source = source.translate(FORMAT_CHARACTERS)
        values.append(source)
    values.append(source.casefold())
    return tuple(dict.fromkeys(values))


@lru_cache(maxsize=8192)
def scan_copies(source):
    # Preserve the raw-tag and decoded-tag views, including every intermediate
    # Unicode/punctuation/format normalization before characters can disappear.
    values = list(normalization_values(source))
    values.extend(normalization_values(HTML_TAG.sub('', source)))
    for text in tuple(values):
        values.append(HTML_TAG.sub('', text))
    values.extend(text.casefold() for text in tuple(values))
    return tuple(dict.fromkeys(values))


def json_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from json_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from json_strings(child)


@lru_cache(maxsize=512)
def frontmatter_values(source):
    values = []
    if source.startswith('---\n') and '\n---\n' in source[4:]:
        block = source[4:].split('\n---\n', 1)[0]
        for line, text in enumerate(block.split('\n'), 2):
            try:
                _, value = parse_field(text)
            except (ValueError, TypeError):
                continue
            values.extend((line, line, text) for text in json_strings(value))
    return tuple(values)


def document_prose(source):
    return re.sub(r'```.*?```|`[^`]+`|https?://[^\s)]+', '', source, flags=re.S)


def document_links(source):
    return re.findall(r'\[[^]]*\]\(([^)]+)\)', source)


@lru_cache(maxsize=512)
def inspection_values(source):
    """The sole value stream for ASCII and name checks, with source bounds.

    Native fields include full fence info, definitions and discarded cells.
    Both reader views include joined text and every attribute. All of these
    values are already character-reference decoded by their owning parser.
    """
    end = source.count('\n') + 1
    collected = [(1, end, source)]
    collected.extend(frontmatter_values(source))
    collected.extend(markdown_literals(source))
    collected.append((1, end, parse_markdown(source)[0]))
    collected.append((1, end, document_prose(source)))
    collected.extend((1, end, link) for link in document_links(source))
    for view in rendered_views(source):
        collected.extend((1, end, text) for text in view)
    values = []
    for start, stop, text in collected:
        values.extend((start, stop, copy) for copy in scan_copies(text))
    return tuple(dict.fromkeys(values))


@lru_cache(maxsize=8192)
def value_references(source, names):
    # Casefolded copies are retained in the shared stream as well. Matching is
    # case-insensitive, while decoded values remain intact for ASCII checking.
    source = source.casefold()
    references = text_references(source, names | META_WRITE_TOOLS, markup=True)
    for prefix, pattern in META_WRITE_PATTERNS:
        references.update(prefix + match[1] for match in pattern.finditer(source))
    references.update(re.findall(r'tool\[([^]\s]+)\]', source))
    for token in re.findall(r'(?:call|use|invoke)\s+`([^`]+)`', source):
        if TOOL_PREFIX.fullmatch(token) and token != 'actions.propose':
            references.add(token)
    for payload in re.findall(r'\{[^{}]*"method"\s*:\s*"tools/call".*?\}', source, re.S):
        references.update(re.findall(r'"name"\s*:\s*"([^"]+)"', payload))
    return frozenset(references)


@lru_cache(maxsize=8192)
def checked_value(text, names):
    """A value can reach neither policy without invoking the other."""
    match = ASCII_INVALID.search(text)
    return (match[0] if match is not None else None), value_references(text, names)


@lru_cache(maxsize=512)
def inspection_result(source, names):
    """Check both policies for every value; neither sink chooses collectors."""
    names = frozenset(names) | RETIRED_TOOLS
    violation, references, locations = None, set(), set()
    for start, end, text in inspection_values(source):
        character, found = checked_value(text, names)
        if character is not None and violation is None:
            violation = (start, end, character)
        references.update(found)
        if start == end:
            locations.update((name, start) for name in found)
    return violation, frozenset(references), tuple(sorted(locations))


@lru_cache(maxsize=512)
def rendered_view_references(source, names):
    # Keep the ratified two-view diagnostics, using the same normalized values
    # and matcher. The full guard consumes these views through inspection_result.
    views = []
    for strings in rendered_views(source):
        references = set()
        for text in strings:
            for copy in scan_copies(text):
                references.update(checked_value(copy, names)[1])
        views.append(frozenset(references))
    return tuple(views)


def rendered_references(source, names):
    first, second = rendered_view_references(source, names)
    return first | second


def referenced_tools(source, names):
    return set(inspection_result(source, frozenset(names))[1])


def forbidden(item, tier):
    return (item['sk7'] or
            (tier == 'read' and (item['minimum_tier'] != 'read' or item['effect'] == 'write')) or
            (tier == 'write' and item['effect'] == 'write' and item['name'] != 'propose-actions'))


@lru_cache(maxsize=64)
def contract(lock_text, manifest_text):
    lock, manifest = json.loads(lock_text), json.loads(manifest_text)
    if set(lock) != {'schema_version', 'core_sha', 'protocol_methods', 'tools'} or lock['schema_version'] != 3:
        raise ValueError('Invalid lock contract fields/version')
    if not re.fullmatch(r'[0-9a-f]{40}', lock['core_sha']) or manifest['core_sha'] != lock['core_sha']:
        raise ValueError('Manifest and lock must share a recorded core SHA')
    tools = {item['name']: item for item in lock['tools']}
    if len(tools) != len(lock['tools']):
        raise ValueError('Duplicate locked tool name')
    for item in tools.values():
        if set(item) != {'name', 'minimum_tier', 'effect', 'grant_operation', 'sk7', 'sk7_rules'}:
            raise ValueError('Invalid locked tool fields')
        if item['minimum_tier'] not in {'read', 'write', 'admin'} or item['effect'] not in {'read', 'write'}:
            raise ValueError('Invalid tier/effect for ' + item['name'])
        if not isinstance(item['sk7'], bool) or not isinstance(item['sk7_rules'], list):
            raise ValueError('Invalid exclusion for ' + item['name'])
        if any(rule not in {'launch-domain', 'creative-grant', 'explicit-exclusion'} for rule in item['sk7_rules']):
            raise ValueError('Unknown exclusion rule for ' + item['name'])
        if item['sk7'] != bool(item['sk7_rules']):
            raise ValueError('Exclusion rule/membership mismatch for ' + item['name'])
    if manifest['license'] != 'Apache-2.0' or not re.fullmatch(r'\d+\.\d+\.\d+', manifest['version']):
        raise ValueError('Invalid manifest licence/version')
    names = [entry['name'] for entry in manifest['skills']]
    if not names or len(names) != len(set(names)):
        raise ValueError('Manifest needs unique skill names')
    for entry in manifest['skills']:
        if entry['minimum_tier'] not in {'read', 'write'}:
            raise ValueError('Invalid skill tier')
    return tools, manifest


@lru_cache(maxsize=512)
def parse_field(line):
    match = re.fullmatch(r'([a-z][a-z-]*): (.+)', line)
    if not match:
        raise ValueError('Invalid or duplicate frontmatter field')
    return match[1], json.loads(match[2])


@lru_cache(maxsize=64)
def parse_fields(block):
    fields = {}
    for line in block.splitlines():
        key, value = parse_field(line)
        if key in fields:
            raise ValueError('Invalid or duplicate frontmatter field')
        fields[key] = value
    return fields


def frontmatter(text):
    if not text.startswith('---\n') or '\n---\n' not in text[4:]:
        raise ValueError('Missing or unterminated frontmatter')
    block, body = text[4:].split('\n---\n', 1)
    return parse_fields(block), body


@lru_cache(maxsize=512)
def document_checks(source):
    errors = []
    if re.search(r'\bsandbox\b', source, re.I):
        errors.append('sandbox belongs only in the synthetic README demo')
    prose = document_prose(source)
    if any(word != 'Plainrouter' for word in re.findall(r'(?<![\w/-])plainrouter(?![\w/-])', prose, re.I)):
        errors.append('brand must be Plainrouter')
    return errors, document_links(source)


def validate(root):
    root = Path(root)
    tools, manifest = contract((root / 'tools.lock.json').read_text(), (root / 'manifest.json').read_text())
    errors, documents = [], {}
    for name in sorted(set(tools) & set(EXTERNAL_TOOLS)):
        errors.append('tools.lock.json: external tool collides with locked tool: ' + name)
    tool_names = frozenset(tools) | frozenset(EXTERNAL_TOOLS)
    entries = manifest['skills']
    if {p.name for p in (root / 'skills').iterdir() if p.is_dir()} != {entry['name'] for entry in entries}:
        errors.append('manifest.json: skill folders differ from manifest')
    for entry in entries:
        folder = root / 'skills' / entry['name']
        documents[entry['name']] = []
        for path in sorted(folder.rglob('*')):
            if path.is_symlink():
                errors.append(str(path.relative_to(root)) + ': symlink resources are not allowed')
                continue
            if not path.is_file():
                continue
            source, violation = bundle_text(path.read_bytes(), tool_names)
            if violation is not None:
                errors.append(str(path.relative_to(root)) + ': ' + violation)
            if source is None:
                continue
            if path.suffix.lower() == '.md':
                _, html_kind = parse_markdown(source)
                if html_kind is not None:
                    errors.append(str(path.relative_to(root)) + ': raw HTML is not allowed: ' + html_kind)
            elif any(match[1].isalpha() or match[1] in '/!?' for match in re.finditer(r'<(.)', source, re.S)):
                errors.append(str(path.relative_to(root)) + ': raw HTML is not allowed: text prefix')
            references = referenced_tools(source, tool_names)
            documents[entry['name']].append((path, source, references))
            _, _, reference_lines = inspection_result(source, frozenset(tool_names))
            for name in sorted(references):
                if name in META_WRITE_TOOLS or name.startswith(META_WRITE_PREFIXES):
                    errors.append(str(path.relative_to(root)) + ': forbidden tool reference: ' + name)
                elif name in EXTERNAL_TOOLS:
                    if EXTERNAL_TOOLS[name]['effect'] != 'read':
                        errors.append(str(path.relative_to(root)) + ': external tool must have read effect: ' + name)
                elif name not in tools:
                    errors.append(str(path.relative_to(root)) + ': tool absent from tools.lock.json: ' + name)
                    for referenced_name, line in reference_lines:
                        if referenced_name == name:
                            errors.append(str(path.relative_to(root)) + ': line ' + str(line) + ': tool absent from tools.lock.json: ' + name)
                elif forbidden(tools[name], entry['minimum_tier']):
                    errors.append(str(path.relative_to(root)) + ': forbidden tool reference: ' + name)
                    for referenced_name, line in reference_lines:
                        if referenced_name == name:
                            errors.append(str(path.relative_to(root)) + ': line ' + str(line) + ': forbidden tool reference: ' + name)
    # Reject references before parsing metadata or packaging. A malformed
    # document cannot hide a forbidden name behind an unrelated format error.
    if errors:
        return errors
    for entry in entries:
        name = entry['name']
        folder = root / 'skills' / name
        path = folder / 'SKILL.md'
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name) or len(name) > 64 or not path.is_file():
            errors.append(name + ': invalid skill folder or missing SKILL.md')
            continue
        text = path.read_text()
        try:
            fields, body = frontmatter(text)
            metadata = fields.get('metadata', {})
            if set(fields) != FIELDS or fields.get('name') != name or fields.get('license') != 'Apache-2.0':
                raise ValueError('Invalid portable frontmatter fields/name/licence')
            description, compatibility = fields.get('description'), fields.get('compatibility')
            if not isinstance(description, str) or not 1 <= len(description) <= 200 or re.search(r'<[^>]*>', description):
                raise ValueError('Invalid description')
            if not isinstance(compatibility, str) or not 1 <= len(compatibility) <= 500:
                raise ValueError('Invalid compatibility')
            if not isinstance(metadata, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in metadata.items()):
                raise ValueError('Metadata must map strings to strings')
            if len(text.splitlines()) >= 500:
                raise ValueError('SKILL.md must stay under 500 lines')
            if metadata.get('version') != entry['version'] or not re.fullmatch(r'\d+\.\d+\.\d+', entry['version']):
                raise ValueError('Invalid or inconsistent skill version')
            if metadata.get('minimum-tier') != entry['minimum_tier']:
                raise ValueError('Inconsistent skill tier')
            if not isinstance(entry.get('zip_bytes'), int) or entry['zip_bytes'] <= 0 or not re.fullmatch(r'[0-9a-f]{64}', entry.get('zip_sha256', '')):
                raise ValueError('Invalid ZIP manifest record')
            declared = metadata.get('tools', '').split()
            if not declared or len(set(declared)) != len(declared):
                raise ValueError('Invalid declared tool inventory')
            external = metadata.get('external-tools', '').split()
            if ('external-tools' in metadata and not external) or len(set(external)) != len(external):
                raise ValueError('Invalid declared external tool inventory')
            for tool in external:
                if tool not in EXTERNAL_TOOLS:
                    raise ValueError('External tool not allowlisted: ' + tool)
                if EXTERNAL_TOOLS[tool]['effect'] != 'read':
                    raise ValueError('External tool must have read effect: ' + tool)
            if 'tools/list' not in body:
                raise ValueError('Discover tools/list before using tools')
            references = referenced_tools(body, tool_names)
            for document, source, found in documents[name]:
                relative = document.relative_to(folder)
                if document != path:
                    if len(relative.parts) != 2 or relative.parts[0] != 'references' or document.suffix != '.md':
                        errors.append(name + ': supporting references must be Markdown one level deep')
                    references.update(found)
                checks, links = document_checks(source)
                errors.extend(str(document.relative_to(root)) + ': ' + error for error in checks)
                for link in links:
                    if '://' in link or link.startswith('#'):
                        continue
                    target = (document.parent / link.split('#', 1)[0]).resolve()
                    if not target.is_relative_to(folder.resolve()) or not target.is_file():
                        errors.append(name + ': missing or out-of-bundle reference: ' + link)
            if references != set(declared) | set(external):
                errors.append(name + ': workflow references differ from metadata.tools and metadata.external-tools')
            for tool in declared:
                if tool not in tools:
                    errors.append(name + ': tool absent from tools.lock.json: ' + tool)
                elif forbidden(tools[tool], entry['minimum_tier']):
                    errors.append(name + ': forbidden tool reference: ' + tool)
        except (ValueError, TypeError, KeyError) as exc:
            errors.append(name + ': ' + str(exc))
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        errors = validate(args.root)
    except (KeyError, ValueError, OSError, TypeError) as exc:
        errors = [str(exc)]
    for error in errors:
        print('ERROR ' + error, file=sys.stderr)
    if errors:
        return 1
    print('Validated portable bundles, tool references, tiers, effects and exclusions.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
