import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from markdown_to_prediction import parse_markdown

class MarkdownTest(unittest.TestCase):
    def test_inline_code_is_literal(self):
        self.assertEqual(parse_markdown('Use `List<T>` and `a_b` &amp; **bold**.')[0]['text'], 'Use List<T> and a_b & bold.')

    def test_fenced_code_preserves_html_and_indentation(self):
        text = '    List<T> value;\n    /** <b>literal</b> */'
        self.assertEqual(parse_markdown('```java\n'+text+'\n```')[0]['text'], text)

    def test_long_and_tilde_fences(self):
        self.assertEqual(parse_markdown('~~~~\n```\n~~~~')[0]['text'], '```')
        self.assertEqual(parse_markdown('````\n```\n````')[0]['text'], '```')

    def test_image_keeps_asset_reference(self):
        self.assertEqual(parse_markdown('![plot](plot.png)')[0]['image_uri'], 'plot.png')

    def test_unrelated_paragraph_is_not_swallowed_by_caption(self):
        blocks = parse_markdown('Figure 1-1\n\nProductivity vs. time\n\nA new paragraph.')
        self.assertEqual([b['type'] for b in blocks], ['caption', 'paragraph'])
        self.assertEqual(blocks[1]['text'], 'A new paragraph.')

    def test_separate_lists_have_distinct_groups(self):
        blocks = parse_markdown('- one\n\nA paragraph.\n\n1. two')
        self.assertNotEqual(blocks[0]['group_id'], blocks[2]['group_id'])

    def test_table_recognized(self):
        self.assertEqual(parse_markdown('| A | B |\n|---|---|\n| 1 | 2 |')[0]['type'], 'table')
