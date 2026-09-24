"""Write EPUB 3 using only local, declared assets and XML-safe content."""
from __future__ import annotations
import hashlib
import html
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED, ZIP_STORED

from .quality import quality_fingerprint

CSS = '''
:root { color-scheme: light dark; }
html { color: inherit; background: transparent; }
body { max-width: 42rem; margin: 0 auto; padding: 2rem 1.4rem 4rem;
       color: inherit; background: transparent;
       font-family: Georgia, "Times New Roman", serif; font-size: 1.08em; line-height: 1.65; }
h1, h2, h3, h4, h5, h6 { font-family: sans-serif; line-height: 1.22;
       break-after: avoid; margin: 1.7em 0 .7em; color: inherit; }
h1 { font-size: 2.2em; } h2 { font-size: 1.5em; } h3 { font-size: 1.22em; }
p { margin: .8em 0; overflow-wrap: break-word; }
pre { font-family: monospace; font-size: .9em; line-height: 1.5; padding: 1em;
      background: rgba(127,127,127,.14); border-left: 3px solid currentColor; white-space: pre-wrap;
      overflow-wrap: anywhere; tab-size: 4; break-inside: auto; }
code { font-family: monospace; font-size: inherit; }
figure { margin: 1.8em auto; text-align: center; break-inside: avoid; max-width: 100%; }
figure img { display: block; width: 100%; max-width: 100%; height: auto; }
.equation { display: flex; align-items: center; justify-content: center; gap: 1em;
            max-width: 100%; overflow-x: auto; margin: 1.3em 0; }
.equation math { flex: none; font-size: 1.05em; }
.equation img { display: block; max-width: 100%; height: auto; }
.equation-number { flex: none; margin-left: auto; }
.equation-stacked { display: block; text-align: center; overflow: visible; }
.equation-line { display: block; max-width: 100%; overflow-x: auto; margin: .2em 0; }
.equation-stacked math { display: block; max-width: 100%; margin: 0 auto; }
.equation-stacked .equation-number { display: block; text-align: right; margin: 0; }
figcaption, .caption { font-family: sans-serif; font-size: .85em; color: inherit; opacity: .78; }
.caption { margin-top: 1.5em; margin-bottom: .2em; }
li { margin: .3em 0; }
a { color: inherit; text-decoration: underline; }
a[role="doc-noteref"] { font-size: .75em; vertical-align: super; line-height: 0; }
.footnotes { border-top: 1px solid currentColor; margin-top: 3em; font-size: .88em; }
aside { margin: 1em 0; }
table { border-collapse: collapse; width: 100%; font-size: .9em; }
th, td { border: 1px solid currentColor; padding: .4em; text-align: left; }
nav li { margin: .45em 0; }
@media (max-width: 480px) { body { padding: 1rem; } h1 { font-size: 1.8em; } }
'''
E = html.escape


def safe_text(value):
    # XML 1.0 forbids these controls even when escaped.
    return ''.join(c for c in value if c in '\t\n\r' or 0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF)


def escaped(value):
    return E(safe_text(value))


def _target_href(target, locations, current_filename):
    filename = locations.get(target) if locations else None
    prefix = f'{filename}' if filename and filename != current_filename else ''
    return f'{prefix}#{target}'


def inline(block, locations=None, current_filename=None):
    value = block.get('text','')
    parts, end = [], 0
    for ref in sorted(block.get('note_refs',[]), key=lambda r:r['start']):
        parts.append(escaped(value[end:ref['start']]))
        identifier = block['id']+'-note-'+ref['target']
        href = _target_href(ref['target'], locations, current_filename)
        parts.append(f'<a epub:type="noteref" role="doc-noteref" id="{E(identifier)}" href="{E(href)}">{E(ref["marker"])}</a>')
        end = ref['end']
    parts.append(escaped(value[end:]))
    result = ''.join(parts)
    link = block.get('hyperlink')
    if link and urlparse(link).scheme in {'http','https','mailto'} and not block.get('note_refs'):
        result = f'<a href="{E(link)}">{result}</a>'
    return result


def table_html(block):
    rows = {}
    for cell in block.get('data',{}).get('table_cells',[]):
        rows.setdefault(cell['start_row_offset_idx'], []).append(cell)
    output = []
    for row in sorted(rows):
        cells = []
        for cell in sorted(rows[row],key=lambda c:c['start_col_offset_idx']):
            tag = 'th' if cell.get('column_header') or cell.get('row_header') else 'td'
            rs = cell.get('row_span',1); cs = cell.get('col_span',1)
            cells.append(f'<{tag} rowspan="{rs}" colspan="{cs}">{escaped(cell.get("text",""))}</{tag}>')
        output.append('<tr>'+''.join(cells)+'</tr>')
    return '<table id="'+E(block['id'])+'">'+''.join(output)+'</table>'


def formula_parts(latex):
    """Break only at top-level LaTeX spacing, never inside a grouped expression."""
    parts, start, cursor, depth = [], 0, 0, 0
    for match in re.finditer(r'\\quad\b', latex):
        depth += latex[cursor:match.start()].count('{') - latex[cursor:match.start()].count('}')
        if depth == 0:
            part = latex[start:match.start()].strip()
            if part:
                parts.append(part)
            start = match.end()
        cursor = match.end()
    tail = latex[start:].strip()
    if tail:
        parts.append(tail)
    return parts or [latex]


def xhtml(title, language, body):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{E(language)}" xml:lang="{E(language)}">'
        f'<head><meta charset="utf-8"/><title>{escaped(title)}</title><link rel="stylesheet" href="style.css"/></head>'
        f'<body>{body}</body></html>')


def _page_number(item):
    provenance = item.get('provenance', [])
    return provenance[0].get('page_no') if provenance else None


def publication_sections(book):
    """Split the reading order at PDF top-level bookmarks, with heading fallback."""
    pages = set(book.get('pages', []))
    outline = [item for item in book.get('outline', []) if item.get('page_no') in pages]
    boundaries = [item for item in outline if item.get('level') == 0]
    if len({item['page_no'] for item in boundaries}) < 2:
        headings = [block for block in book['blocks'] if block['type'] == 'heading' and _page_number(block) in pages]
        if headings:
            shallowest = min(block.get('level', 6) for block in headings)
            boundaries = [
                {'title': block['text'], 'page_no': _page_number(block), 'level': shallowest}
                for block in headings if block.get('level', 6) == shallowest
            ]
    unique = []
    seen_pages = set()
    for boundary in sorted(boundaries, key=lambda item: item['page_no']):
        if boundary['page_no'] not in seen_pages:
            unique.append(boundary)
            seen_pages.add(boundary['page_no'])
    boundaries = unique if len(unique) >= 2 else []

    if not boundaries:
        return [{
            'title': book['title'], 'filename': 'content.xhtml',
            'blocks': book['blocks'], 'footnotes': book['footnotes'],
        }]
    first_page = min(pages) if pages else min(boundary['page_no'] for boundary in boundaries)
    if first_page < boundaries[0]['page_no']:
        boundaries.insert(0, {'title': book['title'], 'page_no': first_page, 'level': 0})
    sections = []
    for index, boundary in enumerate(boundaries):
        end = boundaries[index + 1]['page_no'] if index + 1 < len(boundaries) else None
        def within(item):
            page_number = _page_number(item)
            if page_number is None:
                return index == 0
            return page_number >= boundary['page_no'] and (end is None or page_number < end)
        sections.append({
            'title': boundary['title'],
            'filename': f'chapter-{index + 1:03}.xhtml',
            'blocks': [block for block in book['blocks'] if within(block)],
            'footnotes': [note for note in book['footnotes'] if within(note)],
        })
    return sections


def _locations(sections):
    locations = {}
    for section in sections:
        filename = section['filename']
        for block in section['blocks']:
            locations[block['id']] = filename
            for ref in block.get('note_refs', []):
                locations[f'{block["id"]}-note-{ref["target"]}'] = filename
        for note in section['footnotes']:
            locations[note['id']] = filename
    for section in sections:
        for block in section['blocks']:
            if block['type'] == 'figure':
                for caption_id in block.get('caption_ids', []):
                    locations[caption_id] = section['filename']
    return locations


def _render_blocks(book, blocks, footnotes, *, locations=None, current_filename=None):
    rendered = []
    active_list = None
    caption_ids = {c for b in book['blocks'] if b['type']=='figure' for c in b.get('caption_ids',[])}
    by_id = {b['id']:b for b in book['blocks']}
    for block in blocks:
        kind, identifier = block['type'], E(block['id'])
        if kind != 'list_item' or active_list and active_list[0] != block.get('group_id'):
            if active_list: rendered.append(f'</{active_list[1]}>'); active_list=None
        if block['id'] in caption_ids: continue
        if kind == 'heading':
            level = min(max(block['level'],1),6)
            rendered.append(f'<h{level} id="{identifier}">{inline(block, locations, current_filename)}</h{level}>')
        elif kind == 'code':
            if block.get('asset'):
                rendered.append(
                    f'<figure class="source-code" id="{identifier}">'
                    f'<img src="{E(block["asset"])}" alt="{escaped(block["alt"])}" '
                    f'width="{int(block["image_width_px"])}" height="{int(block["image_height_px"])}" '
                    f'style="width: {int(block["display_width_px"])}px; max-width: 100%"/>'
                    '</figure>'
                )
            else:
                rendered.append(f'<pre id="{identifier}"><code>{escaped(block["text"])}</code></pre>')
        elif kind == 'formula':
            if block.get('asset'):
                rendered.append(
                    f'<div class="equation" id="{identifier}">'
                    f'<img src="{E(block["asset"])}" alt="{escaped(block["alt"])}" '
                    f'width="{int(block["image_width_px"])}" height="{int(block["image_height_px"])}" '
                    f'style="width: {int(block["display_width_px"])}px"/>'
                    '</div>'
                )
            else:
                from latex2mathml.converter import convert
                if not block['text'].strip():
                    raise ValueError(f'Formula {block["id"]} is empty')
                try:
                    parts = formula_parts(block['text'])
                    math = [convert(part, display='block') for part in parts]
                except Exception as exc:
                    raise ValueError(f'Cannot render formula {block["id"]}: {exc}') from exc
                number = block.get('number')
                label = f'<span class="equation-number">({E(number)})</span>' if number else ''
                if len(math) > 1:
                    lines = ''.join(f'<div class="equation-line">{part}</div>' for part in math)
                    rendered.append(f'<div class="equation equation-stacked" id="{identifier}">{lines}{label}</div>')
                else:
                    rendered.append(f'<div class="equation" id="{identifier}">{math[0]}{label}</div>')
        elif kind == 'figure':
            captions = ''.join(f'<figcaption id="{E(c)}">{inline(by_id[c], locations, current_filename)}</figcaption>' for c in block.get('caption_ids',[]) if c in by_id)
            width = min(100.0, max(1.0, float(block.get('display_width_percent', 100.0))))
            rendered.append(
                f'<figure id="{identifier}" style="width: {width:.2f}%">'
                f'<img src="{E(block["asset"])}" alt="{E(block["alt"])}" '
                f'width="{int(block.get("image_width_px", 1))}" height="{int(block.get("image_height_px", 1))}"/>'
                f'{captions}</figure>'
            )
        elif kind == 'table': rendered.append(table_html(block))
        elif kind == 'list_item':
            if not active_list:
                tag = 'ol' if block.get('ordered') else 'ul'
                start = re.match(r'\d+', block.get('marker',''))
                attr = f' start="{start.group()}"' if start and tag=='ol' else ''
                rendered.append(f'<{tag}{attr}>')
                active_list = block.get('group_id'),tag
            rendered.append(f'<li id="{identifier}">{inline(block, locations, current_filename)}</li>')
        else:
            cls = ' class="caption"' if kind=='caption' else ''
            rendered.append(f'<p id="{identifier}"{cls}>{inline(block, locations, current_filename)}</p>')
    if active_list: rendered.append(f'</{active_list[1]}>')
    if footnotes:
        rendered.append('<section class="footnotes" epub:type="footnotes" aria-label="Notes"><h2>Notes</h2>')
        for note in footnotes:
            backlink_href = _target_href(note['backlink'], locations, current_filename) if note.get('backlink') else None
            backlink = f' <a href="{E(backlink_href)}" aria-label="Return to text">↩</a>' if backlink_href else ''
            rendered.append(f'<aside id="{E(note["id"])}" epub:type="footnote" role="doc-footnote"><p>{E(note.get("marker",""))}. {inline(note, locations, current_filename)}{backlink}</p></aside>')
        rendered.append('</section>')
    return '\n'.join(rendered)


def render_content(book):
    body = _render_blocks(book, book['blocks'], book['footnotes'])
    return xhtml(book['title'], book['language'], body)


def render_section(book, section, locations):
    body = _render_blocks(
        book, section['blocks'], section['footnotes'],
        locations=locations, current_filename=section['filename'],
    )
    return xhtml(section['title'], book['language'], body)


def render_nav(book, locations=None):
    if locations is None:
        locations = _locations(publication_sections(book))
    roots, stack = [], []
    for block in book['blocks']:
        if block['type'] != 'heading': continue
        node = {'block':block, 'children':[]}
        while stack and stack[-1]['block']['level'] >= block['level']: stack.pop()
        (stack[-1]['children'] if stack else roots).append(node)
        stack.append(node)
    def tree(nodes):
        return '<ol>'+''.join(f'<li><a href="{E(locations.get(n["block"]["id"], "content.xhtml"))}#{E(n["block"]["id"])}">{escaped(n["block"]["text"])}</a>'
            +(tree(n['children']) if n['children'] else '')+'</li>' for n in nodes)+'</ol>'
    first = next(iter(locations.values()), 'content.xhtml')
    links = tree(roots) if roots else f'<ol><li><a href="{E(first)}">'+escaped(book['title'])+'</a></li></ol>'
    return xhtml(book['title'],book['language'], '<nav epub:type="toc" id="toc"><h1>Contents</h1>'+links+'</nav>')


def render_cover(book):
    cover = book.get('cover')
    if not cover:
        return None
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{E(book["language"])}" xml:lang="{E(book["language"])}">'
        f'<head><meta charset="utf-8"/><title>Cover</title><style>'
        'html,body{height:100%;margin:0;padding:0;background:#000;text-align:center}'
        'body{display:flex;align-items:center;justify-content:center}'
        'img{display:block;max-width:100%;max-height:100%;width:auto;height:auto}'
        '</style></head><body epub:type="cover">'
        f'<img src="{E(cover["path"])}" alt="{E(cover.get("alt", "Cover"))}" '
        f'width="{int(cover["width_px"])}" height="{int(cover["height_px"])}"/>'
        '</body></html>')


def _zip_info(name, modified, compression):
    info = ZipInfo(name, date_time=(modified.year, modified.month, modified.day,
                                   modified.hour, modified.minute, modified.second))
    info.compress_type = compression
    info.external_attr = 0o100644 << 16
    return info


def write_epub(book, directory, destination, *, modified=None):
    directory.mkdir(parents=True,exist_ok=True)
    sections = publication_sections(book)
    locations = _locations(sections)
    section_documents = {
        section['filename']: render_section(book, section, locations)
        for section in sections
    }
    for obsolete in [directory/'content.xhtml', *directory.glob('chapter-*.xhtml')]:
        if obsolete.name not in section_documents and obsolete.exists():
            obsolete.unlink()
    content, nav, cover_page = render_content(book),render_nav(book, locations),render_cover(book)
    for name, value in [*section_documents.items(),('nav.xhtml',nav),('style.css',CSS),('preview.html',content)]:
        (directory/name).write_text(value,encoding='utf-8')
    if cover_page is not None:
        (directory/'cover.xhtml').write_text(cover_page,encoding='utf-8')
    identifier = 'urn:sha256:'+quality_fingerprint(book, stylesheet=CSS)
    modified = modified or datetime.now(timezone.utc)
    if modified.tzinfo is None:
        modified = modified.replace(tzinfo=timezone.utc)
    modified = modified.astimezone(timezone.utc).replace(microsecond=0)
    stamp = modified.strftime('%Y-%m-%dT%H:%M:%SZ')
    content_items = [
        f'<item id="chapter-{index + 1}" href="{E(section["filename"])}" media-type="application/xhtml+xml"'
        f'{" properties=\"mathml\"" if any(block["type"] == "formula" and not block.get("asset") for block in section["blocks"]) else ""}/>'
        for index, section in enumerate(sections)
    ]
    items = [*content_items,
             '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
             '<item id="css" href="style.css" media-type="text/css"/>']
    cover_path = book.get('cover',{}).get('path')
    for i, asset in enumerate(book['assets']):
        payload = (directory/asset['path']).read_bytes()
        if hashlib.sha256(payload).hexdigest()!=asset['sha256']: raise ValueError('Image hash mismatch')
        is_cover = asset['path'] == cover_path
        asset_id = 'cover-image' if is_cover else f'image-{i}'
        properties = ' properties="cover-image"' if is_cover else ''
        items.append(f'<item id="{asset_id}" href="{E(asset["path"])}" media-type="{E(asset["media_type"])}"{properties}/>')
    if cover_page is not None:
        items.append('<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>')
    cover_metadata = '<meta name="cover" content="cover-image"/>' if cover_page is not None else ''
    content_spine = ''.join(f'<itemref idref="chapter-{index + 1}"/>' for index in range(len(sections)))
    spine = ('<itemref idref="cover"/>' if cover_page is not None else '') + content_spine
    package = f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id" xml:lang="{E(book['language'])}">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="book-id">{identifier}</dc:identifier><dc:title>{escaped(book['title'])}</dc:title>
<dc:language>{E(book['language'])}</dc:language><dc:creator>{escaped(book['author'])}</dc:creator>
<meta property="dcterms:modified">{stamp}</meta>{cover_metadata}</metadata>
<manifest>{''.join(items)}</manifest><spine>{spine}</spine></package>'''
    container = '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary = destination.with_suffix('.epub.tmp')
    with ZipFile(temporary,'w',compression=ZIP_DEFLATED) as archive:
        archive.writestr(_zip_info('mimetype', modified, ZIP_STORED), 'application/epub+zip')
        archive.writestr(_zip_info('META-INF/container.xml', modified, ZIP_DEFLATED), container)
        archive.writestr(_zip_info('EPUB/package.opf', modified, ZIP_DEFLATED), package)
        document_names = [*section_documents,'nav.xhtml','style.css']
        if cover_page is not None: document_names.append('cover.xhtml')
        for name in document_names+[a['path'] for a in book['assets']]:
            archive.writestr(
                _zip_info('EPUB/'+name, modified, ZIP_DEFLATED),
                (directory/name).read_bytes(),
            )
    temporary.replace(destination)
