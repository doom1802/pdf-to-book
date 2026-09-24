"""Adapt native Docling JSON, retaining provenance and recovering code geometry."""
from __future__ import annotations
import base64
import hashlib
from io import BytesIO
import json
import re
import statistics
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlparse


def compact(text):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', text))


class SourceGeometry:
    def __init__(self, source):
        import pypdfium2
        self.document = pypdfium2.PdfDocument(str(source))
        self.pages = {}

    def close(self):
        for page, text, _ in self.pages.values():
            text.close()
            page.close()
        self.document.close()

    def characters(self, provenance):
        import pypdfium2.raw as raw
        number = provenance['page_no']
        if number not in self.pages:
            page = self.document[number-1]
            text = page.get_textpage()
            chars = []
            for i in range(text.count_chars()):
                char = text.get_text_range(i, 1)
                if not char or char in '\r\n' or ord(char[0]) < 32:
                    continue
                box = text.get_charbox(i, loose=True)
                chars.append((char, box, raw.FPDFText_GetFontSize(text, i)))
            self.pages[number] = page, text, chars
        page, _, chars = self.pages[number]
        box = provenance['bbox']
        left, right, bottom, top = box['l'], box['r'], box['b'], box['t']
        if box.get('coord_origin') == 'TOPLEFT':
            bottom, top = page.get_height() - bottom, page.get_height() - top
        return [c for c in chars if left-1 <= (c[1][0]+c[1][2])/2 <= right+1
                and bottom-1 <= (c[1][1]+c[1][3])/2 <= top+1]

    def font_size(self, provenance):
        # FontSize can be 1 when the PDF scales glyphs through its text matrix.
        # Loose character boxes express the effective size in page coordinates.
        sizes = [box[3]-box[1] for char, box, _ in self.characters(provenance) if char.strip()]
        return statistics.median(sizes) if sizes else 0

    def code(self, provenance):
        chars = [(char, box) for char, box, _ in self.characters(provenance)]
        if not chars:
            return ''
        rows = []
        for char, box in sorted(chars, key=lambda c: (-c[1][1], c[1][0])):
            row = next((row for row in rows if abs(row[0]-box[1]) < 1.5), None)
            if row is None:
                row = [box[1], []]
                rows.append(row)
            row[1].append((char, box))
        rows.sort(key=lambda row: -row[0])
        pitch = statistics.median(box[2]-box[0] for char, box in chars if char.strip() and box[2] > box[0])
        base = min(box[0] for char, box in chars if char.strip())
        line_gap = statistics.median(rows[i][0]-rows[i+1][0] for i in range(len(rows)-1)) if len(rows)>1 else 1
        lines = []
        previous_y = None
        for y, row in rows:
            if previous_y is not None and line_gap > 0:
                lines.extend([''] * max(0, round((previous_y-y)/line_gap)-1))
            value = ''
            for char, box in sorted(row, key=lambda c: c[1][0]):
                if not char.strip() and box[0] < base-1:
                    continue
                column = max(0, round((box[0]-base)/pitch))
                value += ' ' * max(0, column-len(value)) + char
            lines.append(value.rstrip())
            previous_y = y
        return '\n'.join(lines)

    def source_crop_image(self, provenance, *, scale=4, padding=3):
        """Render a source rectangle without reconstructing mathematical glyphs."""
        number = provenance['page_no']
        page = self.document[number-1]
        bitmap = None
        try:
            width, height = page.get_size()
            box = provenance['bbox']
            if box.get('coord_origin') == 'TOPLEFT':
                left, right = box['l'], box['r']
                bottom, top = height-box['b'], height-box['t']
            else:
                left, right, bottom, top = box['l'], box['r'], box['b'], box['t']
            left, right = max(0, left-padding), min(width, right+padding)
            bottom, top = max(0, bottom-padding), min(height, top+padding)
            if left >= right or bottom >= top:
                raise ValueError(f'Invalid source rectangle on PDF page {number}')
            bitmap = page.render(scale=scale,
                                 crop=(left, bottom, width-right, height-top),
                                 draw_annots=False)
            image = bitmap.to_pil().convert('RGB')
            stream = BytesIO()
            image.save(stream, format='PNG', optimize=True, compress_level=9)
            display_width = round((right-left) * 96 / 72)
            return stream.getvalue(), image.width, image.height, display_width
        finally:
            if bitmap is not None:
                bitmap.close()
            page.close()


def extract_outline(source, pages=None):
    """Read the PDF bookmark tree as stable, one-based page destinations."""
    import pypdfium2
    allowed = set(pages) if pages is not None else None
    document = pypdfium2.PdfDocument(str(source))
    try:
        outline = []
        for bookmark in document.get_toc():
            destination = bookmark.get_dest()
            page_index = destination.get_index() if destination else None
            if page_index is None:
                continue
            page_number = page_index + 1
            if allowed is None or page_number in allowed:
                outline.append({
                    'title': bookmark.get_title(),
                    'level': bookmark.level,
                    'page_no': page_number,
                })
        return outline
    finally:
        document.close()


def resolve_asset(uri, json_path):
    if uri.startswith('data:image/') and ';base64,' in uri:
        return base64.b64decode(uri.split(',',1)[1], validate=True)
    parsed = urlparse(uri)
    if parsed.scheme not in {'', 'file'}:
        raise ValueError(f'Only local image assets are supported: {parsed.scheme}')
    path = Path(unquote(parsed.path))
    candidates = [path, json_path.parent/path, json_path.parent/path.name]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.read_bytes()
    raise FileNotFoundError(f'Missing image: {uri}')


def embedded_figure_text_refs(data):
    """Find text already painted into a picture, without hiding its caption."""
    embedded = set()
    for picture in data.get('pictures', []):
        picture_prov = picture.get('prov', [])
        if len(picture_prov) != 1:
            continue
        picture_page = picture_prov[0]['page_no']
        picture_box = picture_prov[0]['bbox']
        captions = {entry['$ref'] for entry in picture.get('captions', [])}
        for child in picture.get('children', []):
            ref = child['$ref']
            if not ref.startswith('#/texts/') or ref in captions:
                continue
            item = data['texts'][int(ref.rsplit('/', 1)[1])]
            if item.get('label') != 'text' or not item.get('prov'):
                continue
            if all(
                prov['page_no'] == picture_page
                and prov['bbox'].get('coord_origin') == picture_box.get('coord_origin')
                and picture_box['l'] - 2 <= prov['bbox']['l']
                and prov['bbox']['r'] <= picture_box['r'] + 2
                and picture_box['b'] - 2 <= prov['bbox']['b']
                and prov['bbox']['t'] <= picture_box['t'] + 2
                for prov in item['prov']
            ):
                embedded.add(ref)
    return embedded


def join_continuations(blocks, warnings):
    result = []
    for block in blocks:
        previous = result[-1] if result else None
        if previous and previous['type'] == block['type'] == 'paragraph':
            a,b = previous['provenance'][-1], block['provenance'][0]
            left,right = previous['text'],block['text']
            if b['page_no'] == a['page_no']+1 and left and right and (
                left.endswith('-') or (not re.search(r'[.!?:;”\"]$', left) and right[0].islower())
            ):
                previous['text'] = left[:-1]+right if left.endswith('-') else left+' '+right
                previous['provenance'].extend(block['provenance'])
                previous.setdefault('joined_ids', []).append(block['id'])
                continue
        if previous and previous['type'] == block['type'] == 'code' and block['provenance'][0]['page_no'] == previous['provenance'][-1]['page_no']+1:
            # Code is not concatenated speculatively: retain both exact extracts.
            warnings.append(f"Possible code continuation: {previous['id']} → {block['id']}; review before joining.")
        result.append(block)
    return result


def adapt(json_path, source, title, author, language, assets_dir):
    data = json.loads(json_path.read_text())
    geometry = SourceGeometry(source)
    blocks, notes, warnings, assets = [], [], [], []
    excluded = []
    seen = set()
    embedded_text = embedded_figure_text_refs(data)
    def source_crop(provenance):
        payload, image_width, image_height, display_width = geometry.source_crop_image(provenance)
        digest = hashlib.sha256(payload).hexdigest()
        filename = digest[:16]+'.png'
        assets_dir.mkdir(parents=True, exist_ok=True)
        (assets_dir/filename).write_bytes(payload)
        asset = 'assets/'+filename
        if not any(entry['path'] == asset for entry in assets):
            assets.append({'path':asset,'media_type':'image/png','sha256':digest})
        return {'asset':asset,'image_sha256':digest,'image_width_px':image_width,
                'image_height_px':image_height,'display_width_px':display_width}
    def resolve(ref):
        value = data
        for part in ref.removeprefix('#/').split('/'):
            value = value[int(part)] if isinstance(value,list) else value[part]
        return value
    def walk(item):
        ref = item.get('self_ref')
        if ref in seen: return
        seen.add(ref)
        if item.get('label') in {'page_header','page_footer'} or item.get('content_layer') == 'furniture':
            excluded.append(ref)
            return
        if ref in embedded_text:
            return
        if ref and any(ref.startswith('#/'+kind+'/') for kind in ['texts','pictures','tables']):
            yield item
        for child in item.get('children',[]):
            yield from walk(resolve(child['$ref']))
    try:
        items = []
        for item in walk(data['body']):
            # A closing brace is sometimes emitted as a separate code block.
            # Re-extract the union of adjacent boxes instead of inventing indentation.
            previous = items[-1] if items else None
            if (previous and previous['label'] == item['label'] == 'code'
                and re.fullmatch(r'\s*[}\])]+[;,\s]*', item.get('text',''))
                and len(previous.get('prov',[])) == len(item.get('prov',[])) == 1):
                a,b = previous['prov'][0],item['prov'][0]
                if a['page_no'] == b['page_no'] and a['bbox'].get('coord_origin') == b['bbox'].get('coord_origin') == 'BOTTOMLEFT' and 0 <= a['bbox']['b']-b['bbox']['t'] <= 15:
                    previous.setdefault('joined_source_refs',[]).append(item['self_ref'])
                    previous['text'] += '\n'+item['text']
                    for key, op in [('l',min),('r',max),('b',min),('t',max)]:
                        a['bbox'][key] = op(a['bbox'][key],b['bbox'][key])
                    a['charspan'] = [0,len(previous['text'])]
                    continue
            items.append(item)
        for item in items:
            prov = item.get('prov', [])
            if not prov:
                warnings.append(f"No source coordinates: {item['self_ref']}")
                continue
            label = item['label']
            kind = {'text':'paragraph','section_header':'heading','picture':'figure'}.get(label,label)
            block = {'id': item['self_ref'].removeprefix('#/').replace('/','-'),
                     'type': kind, 'text': item.get('text',''), 'provenance':prov}
            if item.get('joined_source_refs'):
                block['joined_source_refs'] = item['joined_source_refs']
            if kind == 'code':
                recovered = '\n'.join(geometry.code(p) for p in prov)
                if recovered:
                    differs = compact(recovered) != compact(block['text'])
                    if differs and len(prov) == 1:
                        block.update(source_crop(prov[0]))
                        block['text_method'] = 'source_image'
                        block['alt'] = block['text']
                        warnings.append(f"Code text differs from Docling: {block['id']}; source image used to preserve the layout.")
                    else:
                        if differs:
                            warnings.append(f"Code text differs from Docling: {block['id']}; multi-region source geometry retained.")
                        block['parser_text'] = block['text']
                        block['text'] = recovered
                        block['text_method'] = 'source_character_geometry'
                else:
                    warnings.append(f"Code geometry unavailable: {block['id']}; parser text retained.")
                block['language'] = item.get('code_language','unknown')
            elif kind == 'formula':
                block['source_text'] = item.get('orig', '')
                number = re.search(r'\((\d+)\)\s*$', block['source_text'])
                if number:
                    block['number'] = number.group(1)
                needs_image = not block['text'].strip() or '&' in block['text'] or '\\\\' in block['text']
                source_plain = unicodedata.normalize('NFKC', block['source_text'])
                if re.search(r'\blen\b', source_plain) and 'len' not in block['text']:
                    needs_image = True
                if any(symbol in source_plain for symbol in ('≥', '⩾')) and not re.search(r'\\geq?|>=|\\geqslant', block['text']):
                    needs_image = True
                if any(symbol in source_plain for symbol in ('≤', '⩽')) and not re.search(r'\\leq?|<=|\\leqslant', block['text']):
                    needs_image = True
                if not needs_image:
                    from xml.etree import ElementTree
                    from latex2mathml.converter import convert
                    try:
                        ElementTree.fromstring(convert(block['text'], display='block'))
                    except Exception:
                        needs_image = True
                if needs_image:
                    block.update(source_crop(prov[0]),
                                 alt=block['source_text'] or f"Formula on PDF page {prov[0]['page_no']}")
                    warnings.append(f"Formula {block['id']} uses a PDF image because Docling's LaTeX is empty or unsuitable.")
            elif kind == 'heading':
                if re.match(r'^Listing\s+\d',block['text']):
                    block['type'] = 'caption'
                elif blocks and blocks[-1]['type'] == 'caption' and re.fullmatch(r'Listing\s+[\d-]+',blocks[-1]['text']):
                    blocks[-1]['text'] += ': '+block['text']
                    blocks[-1]['provenance'].extend(prov)
                    continue
                else:
                    block['font_size'] = round(geometry.font_size(prov[0])*2)/2
                    block['parser_level'] = item.get('level',1)
            elif kind == 'figure':
                image = item.get('image')
                if not image:
                    raise ValueError(f"Figure has no image: {block['id']}")
                page_size = data['pages'][str(prov[0]['page_no'])]['size']
                box = prov[0]['bbox']
                source_width = max(0.0, box['r'] - box['l'])
                source_height = max(0.0, box['t'] - box['b'])
                if not page_size['width'] or not source_width or not source_height:
                    raise ValueError(f"Figure has invalid source geometry: {block['id']}")
                payload = resolve_asset(image['uri'], json_path)
                digest = hashlib.sha256(payload).hexdigest()
                extension = {'image/png':'.png','image/jpeg':'.jpg'}.get(image['mimetype'])
                if not extension: raise ValueError(f"Unsupported image type: {image['mimetype']}")
                filename = digest[:16]+extension
                assets_dir.mkdir(parents=True,exist_ok=True)
                (assets_dir/filename).write_bytes(payload)
                block.update(asset='assets/'+filename, image_sha256=digest,
                             alt=f"Illustration, PDF page {prov[0]['page_no']}",
                             display_width_percent=round(min(100.0, 100.0 * source_width / page_size['width']), 2),
                             source_aspect_ratio=round(source_width / source_height, 6),
                             image_width_px=int(image['size']['width']),
                             image_height_px=int(image['size']['height']),
                             caption_ids=[r['$ref'].removeprefix('#/').replace('/','-') for r in item.get('captions',[])])
                if not any(a['path']==block['asset'] for a in assets):
                    assets.append({'path':block['asset'],'media_type':image['mimetype'],'sha256':digest})
            elif kind == 'table':
                block['data'] = item['data']
            elif kind == 'list_item':
                block.update(group_id=item.get('parent',{}).get('$ref'),
                             ordered=item.get('enumerated',False),marker=item.get('marker',''))
            if item.get('hyperlink'):
                block['hyperlink'] = item['hyperlink']
            # Docling sometimes labels a small numbered footnote as a list item.
            page_height = data['pages'][str(prov[0]['page_no'])]['size']['height']
            box = prov[0]['bbox']
            bottom_region = (box['t'] / page_height < .16 if box.get('coord_origin')=='BOTTOMLEFT'
                             else box['t'] / page_height > .84)
            note_candidate = kind == 'list_item' and item.get('enumerated') and bottom_region and geometry.font_size(prov[0]) < 8
            if kind == 'footnote' or note_candidate:
                block['type'] = 'footnote'
                marker = re.match(r'^(\d+)[.)]?\s*', item.get('marker') or block['text'])
                if marker:
                    block['marker'] = marker.group(1)
                    block['text'] = re.sub(r'^'+re.escape(marker.group(1))+r'[.)]\s*','',block['text'])
                notes.append(block)
            else:
                blocks.append(block)
    finally:
        geometry.close()
    sizes = sorted({b['font_size'] for b in blocks if b['type']=='heading'},reverse=True)
    for block in blocks:
        if block['type']=='heading': block['level'] = min(sizes.index(block['font_size'])+1,6)
    blocks = join_continuations(blocks,warnings)
    for note in notes:
        marker = note.get('marker')
        if not marker:
            warnings.append(f"Footnote has no marker: {note['id']}")
            continue
        page = note['provenance'][0]['page_no']
        pattern = re.compile(r'(?<!\w)'+re.escape(marker)+r'(?!\w)')
        candidates = [(b,m) for b in blocks if b['type']=='paragraph' and any(p['page_no']==page for p in b['provenance'])
                      for m in pattern.finditer(b['text'])]
        if len(candidates)==1:
            block, match = candidates[0]
            block.setdefault('note_refs',[]).append({'start':match.start(),'end':match.end(),'target':note['id'],'marker':marker})
            note['backlink'] = block['id']+'-note-'+note['id']
        else:
            warnings.append(f"Ambiguous footnote reference: {note['id']} ({len(candidates)} candidates); note retained without inferred link.")
    for item in data.get('texts',[]):
        if item.get('label') in {'page_header','page_footer'} and item['self_ref'] not in excluded: excluded.append(item['self_ref'])
    pages = sorted(int(n) for n in data['pages'])
    return {'schema_version':'book-0.1','title':title,'author':author,'language':language,
            'source':str(source),'pages':pages,
            'blocks':blocks,'footnotes':notes,'assets':assets,'warnings':warnings,
            'outline':extract_outline(source, pages),
            'excluded_furniture':excluded,
            'parser':{'name':'docling','schema_version':data.get('version')}}
