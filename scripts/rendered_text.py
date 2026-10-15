"""Pinned CommonMark/GFM rendering followed by HTML text extraction."""
from functools import lru_cache
from html.parser import HTMLParser
import re

from markdown_parse import PARSER_VERSION, parse_markdown

# These elements separate reader-visible blocks/cells. Inline elements do not
# add separators; adjacent text nodes can therefore reconstruct a tool name.
BLOCKS = frozenset('address article aside blockquote body caption center dd details dialog div dl dt fieldset figcaption figure footer form h1 h2 h3 h4 h5 h6 header hgroup hr html legend li main menu nav ol p pre section summary table tbody td tfoot th thead tr ul br'.split())
HIDDEN_CONTENT = frozenset({'rp', 'template', 'script', 'style'})
VOID = frozenset('area base br col embed hr img input link meta param source track wbr'.split())


@lru_cache(maxsize=512)
def parsed_style(style):
    values = [style]
    style = re.sub(r'/\*.*?\*/', '', style, flags=re.S).casefold()
    values.append(style)
    declarations = {}
    for declaration in style.split(';'):
        if ':' not in declaration:
            continue
        property_name, value = declaration.split(':', 1)
        property_name, value = property_name.strip(), value.strip()
        values.extend([property_name, value])
        important = bool(re.search(r'!\s*important\s*$', value))
        value = re.sub(r'!\s*important\s*$', '', value).strip()
        values.append(value)
        if property_name not in {'display', 'visibility'}:
            continue
        previous = declarations.get(property_name)
        if previous is None or important >= previous[0]:
            declarations[property_name] = (important, value)
    return declarations, tuple(dict.fromkeys(values))


def style_values(style):
    return parsed_style(style)[1]


def hidden_style(style):
    declarations, _ = parsed_style(style)
    return (declarations.get('display', (False, ''))[1] == 'none' or
            declarations.get('visibility', (False, ''))[1] == 'hidden')


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.projected = []
        self.attributes = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        self.attributes.extend(value for _, value in attrs if value is not None)
        for key, value in attrs:
            if key == 'style' and value is not None:
                self.attributes.extend(style_values(value))
        hidden = ((self.stack and self.stack[-1][1]) or tag in HIDDEN_CONTENT or
                  any(key == 'hidden' or (key == 'style' and value is not None and hidden_style(value))
                      for key, value in attrs))
        if tag in BLOCKS:
            self.text.append('\n')
            if not hidden:
                self.projected.append('\n')
        if tag not in VOID:
            self.stack.append((tag, bool(hidden)))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        hidden = self.stack and self.stack[-1][1]
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
        if tag in BLOCKS:
            self.text.append('\n')
            if not hidden:
                self.projected.append('\n')

    def handle_data(self, data):
        # View one never drops a text node. Head is not a hiding element.
        self.text.append(data)
        if not self.stack or not self.stack[-1][1]:
            self.projected.append(data)


def html_views(rendered):
    reader = VisibleHTML()
    reader.feed(rendered)
    reader.close()
    attributes = tuple(reader.attributes)
    return ((''.join(reader.text), *attributes), (''.join(reader.projected), *attributes))


@lru_cache(maxsize=512)
def rendered_views(source):
    # Raw HTML must reach the HTML parser, including its attributes. This is
    # static inspection only; the rendered output is never opened/executed.
    rendered, _ = parse_markdown(source)
    return html_views(rendered)


def rendered_strings(source):
    first, second = rendered_views(source)
    return (first[0], second[0], *first[1:])
