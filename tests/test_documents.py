"""Regression checks against the sample PDFs and a stable Docling excerpt.

The excerpt stores structure and source coordinates, not generated EPUB files or
model weights. It lets the tests exercise the real PDF without rerunning Docling.
"""
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import jsonschema
import pypdfium2
from PIL import Image

from pdf_to_book.docling_adapter import adapt, embedded_figure_text_refs
from pdf_to_book.epub import render_content, write_epub
from pdf_to_book.validate import validate


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / 'samples/DeepSeek-V4.1-Flash.pdf'
EXCERPT = ROOT / 'tests/fixtures/deepseek-native-excerpt.json'
FULL_EXPORT = ROOT / 'tmp/docling-formula-full/DeepSeek-V4.1-Flash.json'
NS = {'h': 'http://www.w3.org/1999/xhtml', 'm': 'http://www.w3.org/1998/Math/MathML'}


class GoldenDocumentSourcesTest(unittest.TestCase):
    def test_reviewed_pages_match_manifest(self):
        golden = ROOT/'benchmark/golden'
        manifest = json.loads((golden/'manifest.json').read_text())
        if not all((golden/'annotations'/f"{entry['id']}.json").is_file()
                   for entry in manifest['pages']):
            self.skipTest('Local golden annotations not installed')
        schema = json.loads((golden/'schema.json').read_text())
        self.assertEqual(len(manifest['pages']), 9)
        self.assertEqual(len({entry['source'] for entry in manifest['pages']}), 3)
        for entry in manifest['pages']:
            with self.subTest(page=entry['id']):
                annotation = json.loads((golden/'annotations'/f"{entry['id']}.json").read_text())
                jsonschema.validate(annotation, schema)
                for field in ('id', 'source', 'page_number_pdf'):
                    self.assertEqual(annotation[field], entry[field])
                self.assertTrue(set(entry['features']) <= set(annotation['features']))
                self.assertEqual(annotation['annotation']['status'], 'reviewed')
                self.assertTrue(annotation['blocks'])

    def test_reviewed_pages_exist_in_sample_pdfs(self):
        manifest = json.loads((ROOT/'benchmark/golden/manifest.json').read_text())
        missing = sorted({entry['source'] for entry in manifest['pages']
                          if not (ROOT/entry['source']).is_file()})
        if missing:
            self.skipTest('Sample PDFs not installed: '+', '.join(missing))
        for entry in manifest['pages']:
            with self.subTest(page=entry['id']):
                document = pypdfium2.PdfDocument(str(ROOT/entry['source']))
                try:
                    self.assertLessEqual(entry['page_number_pdf'], len(document))
                finally:
                    document.close()


@unittest.skipUnless(PDF.is_file() and EXCERPT.is_file(),
                     'Local DeepSeek sample PDF and excerpt not installed')
class DeepSeekDocumentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = json.loads(EXCERPT.read_text())
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.work = Path(cls.temporary.name)
        cls.book = adapt(EXCERPT, PDF, 'DeepSeek excerpt', 'DeepSeek-AI', 'en', cls.work/'assets')
        cls.epub = cls.work/'excerpt.epub'
        write_epub(cls.book, cls.work, cls.epub)
        cls.xhtml = ET.fromstring(render_content(cls.book))
        cls.by_id = {block['id']: block for block in cls.book['blocks']}

    def test_figure_labels_are_not_duplicated_as_paragraphs(self):
        self.assertEqual(embedded_figure_text_refs(self.native), {'#/texts/2'})
        self.assertNotIn('texts-2', self.by_id)
        self.assertEqual(self.by_id['pictures-0']['caption_ids'], ['texts-1'])
        figure = self.xhtml.find('.//h:figure[@id="pictures-0"]', NS)
        self.assertEqual(figure.find('h:figcaption', NS).attrib['id'], 'texts-1')
        self.assertIsNone(self.xhtml.find('.//h:p[@id="texts-2"]', NS))
        ids = list(self.by_id)
        self.assertLess(ids.index('pictures-0'), ids.index('texts-3'))
        self.assertIn('texts-4', self.by_id)

    def test_formulas_keep_mathml_or_a_faithful_pdf_crop(self):
        equation = self.by_id['texts-5']
        self.assertEqual(equation['number'], '2')
        self.assertNotIn('asset', equation)
        rendered = self.xhtml.find('.//h:div[@id="texts-5"]', NS)
        self.assertEqual(rendered.attrib['class'], 'equation equation-stacked')
        self.assertEqual(len(rendered.findall('./h:div/m:math', NS)), 2)
        self.assertEqual(rendered.find('h:span', NS).text, '(2)')

        fallback = self.by_id['texts-6']
        self.assertEqual(fallback['number'], '3')
        self.assertTrue((self.work/fallback['asset']).is_file())
        self.assertIsNotNone(self.xhtml.find('.//h:div[@id="texts-6"]/h:img', NS))

    def test_math_heavy_algorithm_uses_readable_source_images(self):
        for identifier, minimum_width in [('texts-9', 1800), ('texts-10', 1700)]:
            code = self.by_id[identifier]
            self.assertEqual(code['text_method'], 'source_image')
            self.assertGreater(code['image_width_px'], minimum_width)
            with Image.open(self.work/code['asset']) as image:
                low, high = image.convert('L').getextrema()
                self.assertLess(low, 100)
                self.assertGreater(high, 240)
            figure = self.xhtml.find(f'.//h:figure[@id="{identifier}"]', NS)
            self.assertEqual(figure.attrib['class'], 'source-code')
            self.assertTrue(figure.find('h:img', NS).attrib['alt'])
            self.assertIsNone(self.xhtml.find(f'.//h:pre[@id="{identifier}"]', NS))
        self.assertIn('Nesterov momentum', self.by_id['texts-9']['alt'])

    def test_excerpt_epub_is_valid_and_assets_are_embedded(self):
        self.assertTrue(validate(self.epub)['valid'])
        with ZipFile(self.epub) as archive:
            names = set(archive.namelist())
            for block in self.book['blocks']:
                if block.get('asset'):
                    self.assertIn('EPUB/'+block['asset'], names)
            self.assertIn(b'2. Architecture', archive.read('EPUB/nav.xhtml'))

    @unittest.expectedFailure
    def test_pdf_contents_entries_are_rendered_in_reading_order(self):
        """Known gap: document_index cells are parsed but lost by the adapter."""
        self.assertEqual(self.native['tables'][0]['data']['table_cells'][0]['text'], '1 Introduction')
        self.assertIn('1 Introduction', render_content(self.book))


@unittest.skipUnless(PDF.is_file() and FULL_EXPORT.is_file(),
                     'Full DeepSeek Docling export not installed; excerpt tests still run')
class FullDeepSeekExportTest(unittest.TestCase):
    def test_full_document_regressions(self):
        native = json.loads(FULL_EXPORT.read_text())
        embedded = embedded_figure_text_refs(native)
        self.assertEqual(len(embedded), 665)
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            book = adapt(FULL_EXPORT, PDF, 'DeepSeek-V4.1-Flash', 'DeepSeek-AI', 'en', work/'assets')
            ids = {block['id'] for block in book['blocks']}
            self.assertFalse({ref.removeprefix('#/').replace('/', '-') for ref in embedded} & ids)
            self.assertEqual(len([block for block in book['blocks'] if block['type'] == 'formula']), 18)
            self.assertEqual(len([block for block in book['blocks'] if block['type'] == 'formula' and block.get('asset')]), 5)
            self.assertEqual(len([block for block in book['blocks'] if block['type'] == 'code' and block.get('asset')]), 2)
            self.assertIn('texts-78', ids)  # Real prose still follows Figure 3.
            figure = next(block for block in book['blocks'] if block['id'] == 'pictures-3')
            self.assertEqual(figure['image_sha256'],
                             'a06c31715d178fa562e9eadc0fa799ff8d14dd5bd528b4322ce3c863956e677c')
            self.assertEqual(figure['caption_ids'], ['texts-29'])
            ordered_ids = [block['id'] for block in book['blocks']]
            self.assertEqual(ordered_ids[ordered_ids.index('pictures-3')+1:ordered_ids.index('texts-78')],
                             ['texts-29'])
            epub = work/'full.epub'
            write_epub(book, work, epub)
            self.assertTrue(validate(epub)['valid'])


if __name__ == '__main__':
    unittest.main()
