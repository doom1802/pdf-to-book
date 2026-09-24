import copy
import base64
from datetime import datetime, timezone
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from pdf_to_book.docling_adapter import SourceGeometry, join_continuations, resolve_asset, adapt, extract_outline, embedded_figure_text_refs
from pdf_to_book.cover import add_pdf_cover
from pdf_to_book.epub import write_epub, render_content, render_nav, publication_sections, formula_parts
from pdf_to_book.epub import CSS
from pdf_to_book.quality import quality_fingerprint, quality_report
from pdf_to_book.validate import validate

ROOT = Path(__file__).resolve().parents[1]

def block(kind, text, identifier='b1', page=1, **extra):
    return dict(id=identifier,type=kind,text=text,provenance=[{'page_no':page}],**extra)

def book(blocks, **extra):
    return dict(schema_version='book-0.1',title='A <book> & title',author='An Author',
                language='en',pages=[1],blocks=blocks,assets=[],footnotes=[],**extra)

class PipelineTest(unittest.TestCase):
    def test_only_text_inside_figure_is_embedded(self):
        def item(ref, label, page, box):
            return {'self_ref': ref, 'label': label, 'prov': [{'page_no': page, 'bbox': dict(box, coord_origin='BOTTOMLEFT')}]}
        figure_box = {'l': 10, 'r': 100, 'b': 20, 't': 120}
        inside = {'l': 20, 'r': 80, 'b': 50, 't': 60}
        below = {'l': 20, 'r': 80, 'b': 5, 't': 15}
        data = {
            'pictures': [dict(item('#/pictures/0', 'picture', 1, figure_box),
                              children=[{'$ref': f'#/texts/{n}'} for n in range(4)],
                              captions=[{'$ref': '#/texts/1'}])],
            'texts': [item('#/texts/0', 'text', 1, inside),
                      item('#/texts/1', 'text', 1, inside),
                      item('#/texts/2', 'text', 1, below),
                      item('#/texts/3', 'text', 2, inside)],
        }
        self.assertEqual(embedded_figure_text_refs(data), {'#/texts/0'})

    def test_joins_incomplete_paragraph_across_pages(self):
        blocks=[block('paragraph','The sentence continues'),block('paragraph','on the next page.', 'b2',2)]
        result=join_continuations(blocks,[])
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['text'],'The sentence continues on the next page.')
        self.assertEqual([p['page_no'] for p in result[0]['provenance']],[1,2])

    def test_preserves_complete_paragraphs_and_page_gaps(self):
        for text,page in [('A complete sentence.',2),('Incomplete',3)]:
            self.assertEqual(len(join_continuations([block('paragraph',text),block('paragraph','another','b2',page)],[])),2)

    def test_does_not_guess_cross_page_code_indentation(self):
        warnings=[]
        result=join_continuations([block('code','if (a) {'),block('code','run(); }','b2',2)],warnings)
        self.assertEqual(len(result),2)
        self.assertEqual(len(warnings),1)

    def test_recovers_geometry_and_spaces_in_prose_inside_code(self):
        geometry=object.__new__(SourceGeometry)
        chars=[]
        for y,start,text in [(20,0,'if (x) {'),(10,2,'run();'),(0,0,'}')]:
            for i,c in enumerate(text): chars.append((c,(start+i,y,start+i+1,y+5),1))
        geometry.characters=lambda prov:chars
        self.assertEqual(geometry.code({}), 'if (x) {\n  run();\n}')

    def test_effective_font_size_uses_transformed_boxes(self):
        geometry=object.__new__(SourceGeometry)
        geometry.characters=lambda prov:[('A',(0,0,10,20),1)]
        self.assertEqual(geometry.font_size({}),20)

    def test_code_is_literal_in_xhtml(self):
        text='    List<T> a;\n    /** <b>literal</b> */'
        document=ET.fromstring(render_content(book([block('code',text)])))
        actual=document.find('.//{http://www.w3.org/1999/xhtml}code').text
        self.assertEqual(actual,text)

    def test_code_source_image_keeps_accessible_transcript(self):
        b=book([block('code','M ← βM + G',asset='assets/code.png',alt='M ← βM + G',
                      image_width_px=1200,image_height_px=500,display_width_px=600)])
        document=ET.fromstring(render_content(b))
        ns={'h':'http://www.w3.org/1999/xhtml'}
        image=document.find('.//h:figure[@class="source-code"]/h:img',ns)
        self.assertEqual(image.attrib['alt'],'M ← βM + G')
        self.assertIn('max-width: 100%',image.attrib['style'])
        self.assertIsNone(document.find('.//h:pre',ns))

    def test_formula_is_mathml_with_equation_number(self):
        b=book([block('formula',r'x_{i}=\frac{a}{b}',number='7')])
        document=ET.fromstring(render_content(b))
        math_ns='{http://www.w3.org/1998/Math/MathML}'
        self.assertIsNotNone(document.find(f'.//{math_ns}mfrac'))
        self.assertEqual(document.find('.//{http://www.w3.org/1999/xhtml}span').text,'(7)')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'formula.epub'
            write_epub(b,Path(folder),path)
            self.assertTrue(validate(path)['valid'])
            with ZipFile(path) as archive:
                self.assertIn(b'properties="mathml"',archive.read('EPUB/package.opf'))

    def test_wide_formula_breaks_at_top_level_quad(self):
        self.assertEqual(formula_parts(r'a_{b \quad c} \quad d'),
                         [r'a_{b \quad c}', 'd'])
        b=book([block('formula',r'x_{l+1}=B_lX_l+C_lF_l(A_lX_l) \quad (A_l,B_l,C_l)=H(X_l)',number='2')])
        document=ET.fromstring(render_content(b))
        ns={'h':'http://www.w3.org/1999/xhtml','m':'http://www.w3.org/1998/Math/MathML'}
        equation=document.find('.//h:div[@class="equation equation-stacked"]',ns)
        self.assertIsNotNone(equation)
        self.assertEqual(len(equation.findall('./h:div/m:math',ns)),2)
        self.assertEqual(equation.find('./h:span',ns).text,'(2)')

    def test_empty_formula_fails_instead_of_disappearing(self):
        with self.assertRaisesRegex(ValueError,'Formula b1 is empty'):
            render_content(book([block('formula','')]))

    def test_nested_navigation(self):
        b=book([block('heading','Chapter',level=1),block('heading','Section','b2',level=2),block('heading','Subsection','b3',level=3)])
        root=ET.fromstring(render_nav(b))
        self.assertIsNotNone(root.find('.//{http://www.w3.org/1999/xhtml}ol/{http://www.w3.org/1999/xhtml}li/{http://www.w3.org/1999/xhtml}ol/{http://www.w3.org/1999/xhtml}li/{http://www.w3.org/1999/xhtml}ol'))

    def test_epub_note_round_trip_and_literal_text(self):
        b=book([block('heading','Chapter',level=1),block('paragraph','Body 1.', 'b2',note_refs=[{'start':5,'end':6,'target':'fn','marker':'1'}])])
        b['footnotes']=[block('footnote','The note.','fn',marker='1',backlink='b2-note-fn')]
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder);path=directory/'book.epub'
            write_epub(b,directory,path)
            self.assertTrue(validate(path)['valid'])
            with ZipFile(path) as archive:
                self.assertEqual(archive.namelist()[0],'mimetype')
                self.assertIn(b'role="doc-noteref"',archive.read('EPUB/content.xhtml'))

    def test_reader_controls_light_and_dark_theme_colors(self):
        self.assertIn('color-scheme: light dark', CSS)
        self.assertIn('background: transparent', CSS)
        self.assertNotIn('background: #fff', CSS)
        self.assertNotIn('color: #', CSS)

    def test_epub_spine_is_split_at_top_level_pdf_bookmarks(self):
        b=book([
            block('heading','Chapter One',page=1,level=1),
            block('paragraph','Body 1.','b2',page=1,note_refs=[{'start':5,'end':6,'target':'fn','marker':'1'}]),
            block('heading','Chapter Two','b3',page=2,level=1),
            block('paragraph','Second body.','b4',page=2),
        ])
        b['pages']=[1,2]
        b['outline']=[
            {'title':'Chapter One','level':0,'page_no':1},
            {'title':'Chapter Two','level':0,'page_no':2},
        ]
        b['footnotes']=[block('footnote','The note.','fn',page=2,marker='1',backlink='b2-note-fn')]
        sections=publication_sections(b)
        self.assertEqual([s['filename'] for s in sections],['chapter-001.xhtml','chapter-002.xhtml'])
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder);path=directory/'book.epub'
            write_epub(b,directory,path)
            self.assertTrue(validate(path)['valid'])
            with ZipFile(path) as archive:
                package=archive.read('EPUB/package.opf').decode()
                first=archive.read('EPUB/chapter-001.xhtml').decode()
                second=archive.read('EPUB/chapter-002.xhtml').decode()
                nav=archive.read('EPUB/nav.xhtml').decode()
            self.assertLess(package.index('idref="chapter-1"'),package.index('idref="chapter-2"'))
            self.assertIn('href="chapter-002.xhtml#fn"',first)
            self.assertIn('href="chapter-001.xhtml#b2-note-fn"',second)
            self.assertIn('chapter-002.xhtml#b3',nav)

    def test_fixed_modified_date_produces_identical_epub_bytes(self):
        b=book([block('heading','Chapter',level=1),block('paragraph','Stable body.','b2')])
        modified=datetime(2026,1,2,3,4,6,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_path=Path(first)/'book.epub';second_path=Path(second)/'book.epub'
            write_epub(b,Path(first),first_path,modified=modified)
            write_epub(copy.deepcopy(b),Path(second),second_path,modified=modified)
            self.assertEqual(first_path.read_bytes(),second_path.read_bytes())

    def test_cover_is_declared_and_first_in_reading_order(self):
        payload=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')
        digest=hashlib.sha256(payload).hexdigest()
        b=book([block('paragraph','Body.')])
        b['cover']={'path':'assets/cover.png','media_type':'image/png','sha256':digest,
                    'width_px':1,'height_px':1,'source_page':1,'alt':'Book cover'}
        b['assets']=[{'path':'assets/cover.png','media_type':'image/png','sha256':digest}]
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder);(directory/'assets').mkdir();(directory/'assets/cover.png').write_bytes(payload)
            path=directory/'book.epub';write_epub(b,directory,path)
            with ZipFile(path) as archive:
                package=archive.read('EPUB/package.opf').decode()
                cover=archive.read('EPUB/cover.xhtml').decode()
            self.assertIn('properties="cover-image"',package)
            self.assertIn('<meta name="cover" content="cover-image"/>',package)
            self.assertIn('<dc:identifier id="book-id">urn:sha256:',package)
            self.assertLess(package.index('idref="cover"'),package.index('idref="chapter-1"'))
            self.assertIn('epub:type="cover"',cover)
            self.assertIn('width="1" height="1"',cover)

    def test_quality_fingerprint_ignores_operational_metadata(self):
        first=book([block('paragraph','Same content.')],source='/one/source.pdf',parser={'version':'1'})
        second=copy.deepcopy(first);second['source']='/another/source.pdf';second['parser']={'version':'2'}
        self.assertEqual(quality_fingerprint(first,stylesheet=CSS),quality_fingerprint(second,stylesheet=CSS))
        second['blocks'][0]['text']='Changed content.'
        self.assertNotEqual(quality_fingerprint(first,stylesheet=CSS),quality_fingerprint(second,stylesheet=CSS))

    def test_quality_fingerprint_includes_cover(self):
        first=book([block('paragraph','Same content.')])
        second=copy.deepcopy(first)
        second['cover']={'path':'assets/cover.png','media_type':'image/png','sha256':'a'*64,
                         'width_px':100,'height_px':150,'source_page':1,'alt':'Cover'}
        second['assets']=[{'path':'assets/cover.png','media_type':'image/png','sha256':'a'*64}]
        self.assertNotEqual(quality_fingerprint(first,stylesheet=CSS),quality_fingerprint(second,stylesheet=CSS))

    def test_validator_detects_missing_note_target(self):
        b=book([block('paragraph','Body 1.',note_refs=[{'start':5,'end':6,'target':'missing','marker':'1'}])])
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder);path=directory/'book.epub';write_epub(b,directory,path)
            self.assertFalse(validate(path)['valid'])

    def test_missing_or_changed_image_is_not_silently_omitted(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder)
            with self.assertRaises(FileNotFoundError):resolve_asset('missing.png',directory/'doc.json')
            b=book([]);b['assets']=[{'path':'image.png','media_type':'image/png','sha256':'a'*64}]
            (directory/'image.png').write_bytes(b'changed')
            with self.assertRaises(ValueError):write_epub(b,directory,directory/'book.epub')

    def test_local_assets_resolve_relative_to_json(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder);(directory/'image.png').write_bytes(b'bytes')
            self.assertEqual(resolve_asset('image.png',directory/'doc.json'),b'bytes')

    def test_tables_keep_cell_spans(self):
        b=book([block('table','',data={'table_cells':[{'start_row_offset_idx':0,'start_col_offset_idx':0,'row_span':1,'col_span':2,'column_header':True,'text':'Header'}]})])
        self.assertIn('colspan="2"',render_content(b))

    def test_figure_uses_source_relative_width_and_intrinsic_ratio(self):
        b=book([block('figure','',asset='assets/image.png',alt='Image',
                      display_width_percent=33.0,image_width_px=342,image_height_px=186)])
        markup=render_content(b)
        self.assertIn('style="width: 33.00%"',markup)
        self.assertIn('width="342" height="186"',markup)

class ChapterIntegrationTest(unittest.TestCase):
    @unittest.skipUnless((ROOT/'output/chapter/docling/clean-code-robert-c-martin.json').exists()
                         and (ROOT/'samples/clean-code-robert-c-martin.pdf').is_file(),
                         'Local sample PDF and export not installed')
    def test_real_chapter_preserves_structure_and_source_code(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder)
            b=adapt(ROOT/'output/chapter/docling/clean-code-robert-c-martin.json',ROOT/'samples/clean-code-robert-c-martin.pdf','Chapter','Author','en',directory/'assets')
            add_pdf_cover(b,ROOT/'samples/clean-code-robert-c-martin.pdf',directory/'assets')
            b['source_sha256']=hashlib.sha256((ROOT/'samples/clean-code-robert-c-martin.pdf').read_bytes()).hexdigest()
            self.assertEqual(b['pages'],list(range(48,62)))
            self.assertEqual(b['outline'][0],{'title':'Chapter 2: Meaningful Names','level':0,'page_no':48})
            self.assertEqual(len(b['assets']),4)
            self.assertEqual(b['cover']['source_page'],1)
            self.assertGreater(b['cover']['height_px'],b['cover']['width_px'])
            figures=[x for x in b['blocks'] if x['type']=='figure']
            self.assertEqual([x['display_width_percent'] for x in figures],[69.82,33.01,35.24])
            self.assertTrue(all(abs(x['source_aspect_ratio']-(x['image_width_px']/x['image_height_px'])) < .01 for x in figures))
            self.assertEqual(len(b['footnotes']),4)
            self.assertTrue(all(n.get('backlink') for n in b['footnotes']))
            self.assertEqual(b['warnings'],[])
            headings={x['text']:x['level'] for x in b['blocks'] if x['type']=='heading'}
            self.assertEqual(headings['Meaningful Names'],1)
            self.assertEqual(headings['Avoid Encodings'],2)
            self.assertEqual(headings['Hungarian Notation'],3)
            code=next(x['text'] for x in b['blocks'] if x['id']=='texts-26')
            self.assertIn('\n      flaggedCells.add(cell);',code)
            code=next(x['text'] for x in b['blocks'] if x['id']=='texts-67')
            self.assertTrue(code.endswith('    };'))
            self.assertFalse(any(x['id']=='texts-68' for x in b['blocks']))
            self.assertEqual(sum(x['type']=='list_item' for x in b['blocks']),4)
            write_epub(b,directory,directory/'chapter.epub')
            self.assertTrue(validate(directory/'chapter.epub')['valid'])

    @unittest.skipUnless((ROOT/'output/chapter/docling/clean-code-robert-c-martin.json').exists()
                         and (ROOT/'samples/clean-code-robert-c-martin.pdf').is_file()
                         and (ROOT/'tests/fixtures/meaningful-names-quality.json').is_file(),
                         'Local sample PDF, export and quality contract not installed')
    def test_real_chapter_matches_exact_quality_contract(self):
        expected=json.loads((ROOT/'tests/fixtures/meaningful-names-quality.json').read_text())
        with tempfile.TemporaryDirectory() as folder:
            b=adapt(ROOT/'output/chapter/docling/clean-code-robert-c-martin.json',ROOT/'samples/clean-code-robert-c-martin.pdf',
                    expected['title'],expected['author'],expected['language'],Path(folder)/'assets')
            add_pdf_cover(b,ROOT/'samples/clean-code-robert-c-martin.pdf',Path(folder)/'assets')
            b['source_sha256']=hashlib.sha256((ROOT/'samples/clean-code-robert-c-martin.pdf').read_bytes()).hexdigest()
            self.assertEqual(
                quality_report(
                    b, stylesheet=CSS,
                    content_xhtml=render_content(b), navigation_xhtml=render_nav(b),
                ),
                expected['report'],
            )

if __name__=='__main__':unittest.main()
