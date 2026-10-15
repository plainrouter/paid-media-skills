"""Inspect and render one AST from the hash-pinned cmark-gfm library."""
import ctypes
import re
from functools import lru_cache
from importlib.metadata import version

from cmarkgfm import _cmark, cmark
from cmarkgfm.cmark import Options

PARSER_VERSION = '2025.10.22'
if version('cmarkgfm') != PARSER_VERSION:
    raise ValueError('Install the pinned parser from requirements.txt with --require-hashes')

# The Python wrapper omits traversal bindings. Load the documented C API from
# that same wheel binary: no second library, parse, renderer or HTML heuristic.
# https://github.com/github/cmark-gfm/blob/master/src/cmark-gfm.h
NATIVE = ctypes.CDLL(_cmark.__file__)
for name in ['cmark_node_first_child', 'cmark_node_next', 'cmark_node_parent']:
    function = getattr(NATIVE, name)
    function.argtypes = [ctypes.c_void_p]
    function.restype = ctypes.c_void_p
NATIVE.cmark_node_get_type_string.argtypes = [ctypes.c_void_p]
NATIVE.cmark_node_get_type_string.restype = ctypes.c_char_p
for name in ['cmark_node_get_literal', 'cmark_node_get_url', 'cmark_node_get_title', 'cmark_node_get_fence_info']:
    function = getattr(NATIVE, name)
    function.argtypes = [ctypes.c_void_p]
    function.restype = ctypes.c_char_p
for name in ['cmark_node_get_start_line', 'cmark_node_get_end_line', 'cmark_node_get_start_column']:
    function = getattr(NATIVE, name)
    function.argtypes = [ctypes.c_void_p]
    function.restype = ctypes.c_int
NATIVE.cmark_node_get_string_content.argtypes = [ctypes.c_void_p]
NATIVE.cmark_node_get_string_content.restype = ctypes.c_char_p
NATIVE.cmark_node_free.argtypes = [ctypes.c_void_p]
NATIVE.cmark_node_free.restype = None


class Memory(ctypes.Structure):
    _fields_ = [('calloc', ctypes.c_void_p), ('realloc', ctypes.c_void_p), ('free', ctypes.c_void_p)]


NATIVE.cmark_get_default_mem_allocator.argtypes = []
NATIVE.cmark_get_default_mem_allocator.restype = ctypes.POINTER(Memory)
FREE = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(NATIVE.cmark_get_default_mem_allocator().contents.free)
# Private layouts and reference grammar from the hash-pinned wheel's source:
# third_party/cmark/src/{parser,node,buffer,chunk,map,references,inlines}.h.
# Only the initial fields used here are declared; never load another library.
class Buffer(ctypes.Structure):
    _fields_ = [('mem', ctypes.POINTER(Memory)), ('ptr', ctypes.c_void_p),
                ('asize', ctypes.c_int32), ('size', ctypes.c_int32)]


class Chunk(ctypes.Structure):
    _fields_ = [('data', ctypes.c_void_p), ('length', ctypes.c_int32), ('alloc', ctypes.c_int32)]


class MapEntry(ctypes.Structure):
    _fields_ = [('next', ctypes.c_void_p), ('label', ctypes.c_void_p),
                ('age', ctypes.c_size_t), ('size', ctypes.c_size_t)]


class Reference(ctypes.Structure):
    _fields_ = [('entry', MapEntry), ('url', Chunk), ('title', Chunk)]


class ReferenceMap(ctypes.Structure):
    _fields_ = [('mem', ctypes.POINTER(Memory)), ('refs', ctypes.c_void_p)]


class ParserPrefix(ctypes.Structure):
    _fields_ = [('mem', ctypes.POINTER(Memory)), ('refmap', ctypes.c_void_p),
                ('root', ctypes.c_void_p), ('current', ctypes.c_void_p)]


for name, args, result in [
        ('cmark_reference_map_new', [ctypes.POINTER(Memory)], ctypes.c_void_p),
        ('cmark_map_free', [ctypes.c_void_p], None),
        ('cmark_parse_reference_inline', [ctypes.POINTER(Memory), ctypes.POINTER(Chunk), ctypes.c_void_p], ctypes.c_int32),
        ('cmark_strbuf_init', [ctypes.POINTER(Memory), ctypes.POINTER(Buffer), ctypes.c_int32], None),
        ('cmark_strbuf_free', [ctypes.POINTER(Buffer)], None),
        ('cmark_strbuf_unescape', [ctypes.POINTER(Buffer)], None),
        ('houdini_unescape_html_f', [ctypes.POINTER(Buffer), ctypes.c_void_p, ctypes.c_int32], None)]:
    function = getattr(NATIVE, name)
    function.argtypes, function.restype = args, result


# Reuse GFM's own row lexer; escaped pipes must not inflate the header
# width and trip its limit on automatically completed empty cells.
for name in ['_scan_table_cell', '_scan_table_cell_end']:
    function = getattr(NATIVE, name)
    function.argtypes = [ctypes.c_char_p, ctypes.c_int32]
    function.restype = ctypes.c_int32


def table_width(row):
    data = row.encode('utf-8') + b'\n'
    offset = NATIVE._scan_table_cell_end(data, len(data))
    columns = 0
    while offset < len(data):
        cell = NATIVE._scan_table_cell(data[offset:], len(data) - offset)
        end = offset + cell
        pipe = NATIVE._scan_table_cell_end(data[end:], len(data) - end)
        if cell or pipe:
            columns += 1
        offset = end + pipe
        if not pipe:
            break
    if not 1 <= columns <= 65535:
        raise ValueError('Discarded table row has an unsupported column count')
    return columns


LABEL = re.compile(rb'^\[((?:\\.|[^\\\[\]])*)\]:', re.S)


def decoded_label(label, mem):
    buffer = Buffer()
    NATIVE.cmark_strbuf_init(mem, ctypes.byref(buffer), 0)
    try:
        NATIVE.houdini_unescape_html_f(ctypes.byref(buffer), label, len(label))
        NATIVE.cmark_strbuf_unescape(ctypes.byref(buffer))
        return ctypes.string_at(buffer.ptr, buffer.size).decode('utf-8')
    finally:
        NATIVE.cmark_strbuf_free(ctypes.byref(buffer))


def pending_definitions(parser):
    """Read the native paragraph before cmark consumes its definitions.

    Container prefixes have already been removed by the block parser. Replay
    its own leading-definition loop into a disposable map, so every duplicate
    is inspected independently. No source regex decides reference grammar.
    """
    state = ParserPrefix.from_address(int(_cmark.ffi.cast('uintptr_t', parser)))
    node = state.current
    if not node or NATIVE.cmark_node_get_type_string(node) != b'paragraph':
        return ()
    data = NATIVE.cmark_node_get_string_content(node) or b''
    if not data.startswith(b'['):
        return ()
    line = NATIVE.cmark_node_get_start_line(node)
    definitions = []
    while data.startswith(b'['):
        refmap = NATIVE.cmark_reference_map_new(state.mem)
        try:
            storage = ctypes.create_string_buffer(data)
            chunk = Chunk(ctypes.addressof(storage), len(data), 0)
            consumed = NATIVE.cmark_parse_reference_inline(state.mem, ctypes.byref(chunk), refmap)
            if not consumed:
                break
            entry = ReferenceMap.from_address(refmap).refs
            if entry:
                reference = Reference.from_address(entry)
                label = LABEL.match(data)
                if label is None:
                    raise ValueError('Native reference label could not be recovered')
                fields = [decoded_label(label[1], state.mem)]
                for value in [reference.url, reference.title]:
                    fields.append(ctypes.string_at(value.data, value.length).decode('utf-8'))
                definitions.extend((line, line, value) for value in fields if value)
            line += data[:consumed].count(b'\n')
            data = data[consumed:]
        finally:
            NATIVE.cmark_map_free(refmap)
    return tuple(definitions)


cmark.core_extensions_ensure_registered()
EXTENSIONS = tuple(cmark.find_syntax_extension(name) for name in
                   ['table', 'autolink', 'tagfilter', 'strikethrough', 'tasklist'])
if not all(EXTENSIONS):
    raise ValueError('Required GFM parser extensions are unavailable')


@lru_cache(maxsize=512)
def parsed_markdown(source, recover_consumed=True, render_table=False):
    options = Options.CMARK_OPT_UNSAFE | Options.CMARK_OPT_GITHUB_PRE_LANG
    parser = cmark.parser_new(options=options)
    address, rendered_address = None, None
    try:
        for extension in EXTENSIONS:
            cmark.parser_attach_syntax_extension(parser, extension)
        definitions = set()
        if ']:' in source:
            # Observe open paragraphs before the next physical line can cause
            # finalization, setext conversion or removal of a definition-only
            # node. The final snapshot also covers files without a final LF.
            lines = source.split('\n')
            for index, line in enumerate(lines):
                definitions.update(pending_definitions(parser))
                cmark.parser_feed(parser, line + ('\n' if index < len(lines) - 1 else ''))
            # Feed a final LF so a non-terminated physical line is processed.
            if not source.endswith('\n'):
                cmark.parser_feed(parser, '\n')
            definitions.update(pending_definitions(parser))
        else:
            cmark.parser_feed(parser, source)
        root = cmark.parser_finish(parser)
        if _cmark.lib.cmark_node_get_type(root) == _cmark.lib.CMARK_NODE_NONE:
            raise ValueError('Markdown parse failed')
        address = int(_cmark.ffi.cast('uintptr_t', root))
        pending, kind, literals, discarded = [address], None, [], []
        while pending:
            node = pending.pop()
            node_type = NATIVE.cmark_node_get_type_string(node)
            if node_type in {b'html_block', b'html_inline'} and kind is None:
                kind = node_type.decode('ascii')
            getters = []
            if node_type in {b'text', b'code', b'code_block', b'html_inline', b'html_block'}:
                getters.append(NATIVE.cmark_node_get_literal)
            if node_type in {b'link', b'image'}:
                getters.extend([NATIVE.cmark_node_get_url, NATIVE.cmark_node_get_title])
            if node_type == b'code_block':
                getters.append(NATIVE.cmark_node_get_fence_info)
            for getter in getters:
                value = getter(node)
                if value:
                    end = (NATIVE.cmark_node_get_start_line(node) if getter == NATIVE.cmark_node_get_fence_info
                           else NATIVE.cmark_node_get_end_line(node))
                    # Inline link source positions can end before a
                    # multiline title. Its containing block bounds the
                    # physical lines used only for diagnostic lookup.
                    if not value.isascii() or b'\\u' in value:
                        parent = NATIVE.cmark_node_parent(node)
                        while parent:
                            end = max(end, NATIVE.cmark_node_get_end_line(parent))
                            if NATIVE.cmark_node_get_type_string(parent) in {b'paragraph', b'heading', b'code_block'}:
                                break
                            parent = NATIVE.cmark_node_parent(parent)
                    literals.append((NATIVE.cmark_node_get_start_line(node), end, value.decode('utf-8')))
            if recover_consumed and node_type == b'table_row':
                # GFM discards body cells beyond the header width. Reparse the
                # physical row with a wide synthetic header, using the same
                # extensions, so code spans and escaped pipes stay native.
                line = NATIVE.cmark_node_get_start_line(node)
                column = NATIVE.cmark_node_get_start_column(node)
                row = source.split('\n')[line - 1].expandtabs(4)[max(0, column - 1):]
                width = table_width(row)
                header = '|' + 'a|' * width
                delimiter = '|' + '---|' * width
                # Include the original document so reference links resolve
                # against its exact definitions. Render only the synthetic
                # first table, retaining the usual two joined reader views.
                row_html, row_kind, row_literals, _ = parsed_markdown(
                    header + '\n' + delimiter + '\n' + row + '\n\n' + source, False, True)
                from rendered_text import html_views
                for view in html_views(row_html):
                    discarded.extend((line, line, text) for text in view)
                if row_kind is not None and kind is None:
                    kind = row_kind
                discarded.extend((line, line, text) for start, _, text in row_literals if start == 3)
            child = NATIVE.cmark_node_first_child(node)
            while child:
                pending.append(child)
                child = NATIVE.cmark_node_next(child)
        render_root = root
        if render_table:
            table = NATIVE.cmark_node_first_child(address)
            if not table or NATIVE.cmark_node_get_type_string(table) != b'table':
                raise ValueError('Discarded table cells could not be recovered')
            render_root = _cmark.ffi.cast('cmark_node *', table)
        rendered = _cmark.lib.cmark_render_html(render_root, options, cmark.parser_get_syntax_extensions(parser))
        if rendered == _cmark.ffi.NULL:
            raise ValueError('Markdown rendering failed')
        rendered_address = int(_cmark.ffi.cast('uintptr_t', rendered))
        return _cmark.ffi.string(rendered).decode('utf-8'), kind, tuple(literals), tuple(sorted(definitions)) + tuple(discarded)
    finally:
        # The AST and rendered buffer are owned by the caller, not the parser.
        if rendered_address is not None:
            FREE(rendered_address)
        if address is not None:
            NATIVE.cmark_node_free(address)
        cmark.parser_free(parser)


def parse_markdown(source):
    rendered, kind, _, _ = parsed_markdown(source)
    return rendered, kind


def markdown_literals(source):
    return parsed_markdown(source)[3] + parsed_markdown(source)[2]


def markdown_definitions(source):
    return parsed_markdown(source)[3]
