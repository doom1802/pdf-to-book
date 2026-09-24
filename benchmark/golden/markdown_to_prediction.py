#!/usr/bin/env python3
"""Normalize CommonMark without interpreting literal code as HTML."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse
from markdown_it import MarkdownIt

CHAPTER_RE = re.compile(r'^(?:chapter|capitolo)\s+\d+\b', re.I)
CAPTION_RE = re.compile(r'^(?:figure|figura)\s+\d', re.I)
CAPTION_LABEL_RE = re.compile(r'^(?:figure|figura)\s+[\d.-]+\s*$', re.I)
MD = MarkdownIt('commonmark').enable('table')


def inline_text(tokens):
    return ''.join(
        token.content if token.type in {'text', 'code_inline'} else
        '\n' if token.type in {'softbreak', 'hardbreak'} else
        inline_text(token.children or []) if token.type == 'image' else ''
        for token in tokens
    )


def clean_inline(text):
    return inline_text(MD.parseInline(text)[0].children or []).strip()


def image_fields(uri, base_dir):
    fields = {'image_uri': uri}
    # Only local assets are read; normalization never fetches remote resources.
    try:
        if uri.startswith('data:image/') and ';base64,' in uri:
            data = base64.b64decode(uri.split(',', 1)[1], validate=True)
        elif not urlparse(uri).scheme and base_dir is not None:
            data = (base_dir / unquote(uri)).read_bytes()
        else:
            return fields
        fields['image_sha256'] = hashlib.sha256(data).hexdigest()
    except (ValueError, OSError):
        pass
    return fields


def parse_markdown(text, *, base_dir=None):
    blocks = []
    list_stack = []
    list_count = 0
    heading = None
    table_lines = None
    tokens = MD.parse(text)

    def append(kind, value='', **extra):
        block = {'id': f'p{len(blocks)+1:03d}', 'type': kind,
                 'reading_order': len(blocks), 'include_in_epub': True}
        if value:
            block['text'] = value
        block.update(extra)
        blocks.append(block)

    for token in tokens:
        if token.type in {'fence', 'code_block'}:
            # CommonMark adds a final newline to a fenced block. Remove only that
            # delimiter newline, preserving indentation and intentional blank lines.
            append('code', token.content.removesuffix('\n'), language=token.info.strip() or 'text')
        elif token.type == 'heading_open':
            heading = int(token.tag[1:])
        elif token.type == 'heading_close':
            heading = None
        elif token.type in {'bullet_list_open', 'ordered_list_open'}:
            list_count += 1
            list_stack.append(f'list-{list_count:03d}')
        elif token.type in {'bullet_list_close', 'ordered_list_close'}:
            list_stack.pop()
        elif token.type == 'table_open':
            table_lines = []
        elif token.type == 'table_close':
            append('table', '\n'.join(table_lines))
            table_lines = None
        elif token.type == 'inline':
            children = token.children or []
            if table_lines is not None:
                table_lines.append(inline_text(children))
                continue
            # Split around image tokens, retaining both their URI and surrounding text.
            pending = []
            def flush():
                value = inline_text(pending).strip()
                pending.clear()
                if not value:
                    return
                if heading is not None:
                    if CHAPTER_RE.match(value): append('chapter_label', value)
                    else: append('heading', value, level=heading)
                elif list_stack:
                    append('list_item', value, group_id=list_stack[-1])
                elif CHAPTER_RE.match(value): append('chapter_label', value)
                elif CAPTION_RE.match(value): append('caption', value)
                elif blocks and blocks[-1]['type'] == 'caption' and CAPTION_LABEL_RE.fullmatch(blocks[-1]['text']):
                    blocks[-1]['text'] += '\n' + value
                else: append('paragraph', value)
            for child in children:
                if child.type == 'image':
                    flush()
                    append('figure', description=inline_text(child.children or []) or 'Extracted image',
                           **image_fields(child.attrGet('src'), base_dir))
                else:
                    pending.append(child)
            flush()
    return blocks


def convert(gold, markdown, parser_id, *, base_dir=None):
    return {
        'schema_version': '0.1', 'id': f"{gold['id']}--{parser_id}",
        'source': gold['source'], 'page_number_pdf': gold['page_number_pdf'],
        'printed_page': gold.get('printed_page'), 'language': gold['language'],
        'features': gold.get('features', []),
        'annotation': {'method': 'automatic_adapter', 'status': 'draft',
                       'notes': f'CommonMark normalization of {parser_id}; literal code preserved.'},
        'blocks': parse_markdown(markdown, base_dir=base_dir),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('gold', type=Path)
    parser.add_argument('markdown', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--parser-id', required=True)
    args = parser.parse_args()
    prediction = convert(json.loads(args.gold.read_text()), args.markdown.read_text(),
                         args.parser_id, base_dir=args.markdown.parent)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(prediction, ensure_ascii=False, indent=2) + '\n')

if __name__ == '__main__':
    main()
