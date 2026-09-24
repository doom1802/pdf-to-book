import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate import evaluate


def page(blocks):
    return {
        "schema_version": "0.1",
        "id": "test",
        "source": "test.pdf",
        "page_number_pdf": 1,
        "language": "en",
        "blocks": blocks,
    }


class EvaluationSeparationTest(unittest.TestCase):
    def test_recovered_code_is_credited_even_when_typed_as_paragraph(self):
        code = "if (ready) {\n    run();\n}"
        gold = page(
            [
                {
                    "id": "b01",
                    "type": "code",
                    "text": code,
                    "reading_order": 0,
                    "include_in_epub": True,
                }
            ]
        )
        prediction = page(
            [
                {
                    "id": "p01",
                    "type": "paragraph",
                    "text": "if (ready) { run(); }",
                    "reading_order": 0,
                    "include_in_epub": True,
                }
            ]
        )

        metrics = evaluate(gold, prediction)["metrics_percent"]

        self.assertEqual(metrics["text_recovery"], 100.0)
        self.assertEqual(metrics["code_text_recovery"], 100.0)
        self.assertEqual(metrics["block_type_accuracy"], 0.0)
        self.assertEqual(metrics["code_type_accuracy"], 0.0)
        self.assertEqual(metrics["code_accuracy"], 0.0)

    def test_extra_text_does_not_reduce_recovery_but_reduces_accuracy(self):
        gold = page(
            [
                {
                    "id": "b01",
                    "type": "paragraph",
                    "text": "wanted text",
                    "reading_order": 0,
                    "include_in_epub": True,
                }
            ]
        )
        prediction = page(
            [
                {
                    "id": "p01",
                    "type": "paragraph",
                    "text": "wanted text plus unrelated material",
                    "reading_order": 0,
                    "include_in_epub": True,
                }
            ]
        )

        metrics = evaluate(gold, prediction)["metrics_percent"]

        self.assertEqual(metrics["text_recovery"], 100.0)
        self.assertLess(metrics["text_accuracy"], 100.0)

class EvaluationIntegrityTest(unittest.TestCase):
    @staticmethod
    def block(kind, text='', **extra):
        return dict(id='b', type=kind, text=text, reading_order=0, include_in_epub=True, **extra)

    def test_embedded_artifact_is_detected(self):
        artifact = self.block('page_number', '42')
        artifact.update(include_in_epub=False, reading_order=1, id='artifact')
        gold = page([self.block('paragraph', 'Some body text.'), artifact])
        pred = page([self.block('paragraph', 'Some body text. 42')])
        self.assertEqual(evaluate(gold, pred)['metrics_percent']['artifact_suppression_accuracy'], 0)

    def test_legitimate_number_is_not_an_artifact(self):
        artifact = self.block('page_number', '42')
        artifact.update(include_in_epub=False, reading_order=1, id='artifact')
        gold = page([self.block('paragraph', 'The answer is 42.'), artifact])
        pred = page([self.block('paragraph', 'The answer is 42.')])
        self.assertEqual(evaluate(gold, pred)['metrics_percent']['artifact_suppression_accuracy'], 100)

    def test_figure_without_evidence_is_not_verified(self):
        metrics = evaluate(page([self.block('figure')]), page([self.block('figure')]))['metrics_percent']
        self.assertIsNone(metrics['figure_recall'])
        self.assertEqual(metrics['figure_presence_recall'], 100)
        self.assertEqual(metrics['figure_verification_coverage'], 0)

    def test_wrong_figure_does_not_match_verified_reference(self):
        gold = page([self.block('figure', image_sha256='a'*64)])
        pred = page([self.block('figure', image_sha256='b'*64)])
        self.assertEqual(evaluate(gold, pred)['metrics_percent']['figure_recall'], 0)
        self.assertEqual(evaluate(gold, pred)['metrics_percent']['figure_presence_recall'], 100)
        pred['blocks'][0]['image_sha256'] = 'a'*64
        self.assertEqual(evaluate(gold, pred)['metrics_percent']['figure_recall'], 100)

    def test_first_line_indentation_counts(self):
        gold = page([self.block('code', '    run()')])
        pred = page([self.block('code', 'run()')])
        self.assertLess(evaluate(gold, pred)['metrics_percent']['code_accuracy'], 100)

    def test_caption_requires_caption_type(self):
        gold = page([self.block('caption', 'Figure 1: example')])
        pred = page([self.block('paragraph', 'Figure 1: example')])
        self.assertEqual(evaluate(gold, pred)['metrics_percent']['caption_recall'], 0)

    def test_unmatched_types_are_not_perfect(self):
        self.assertIsNone(evaluate(page([self.block('paragraph', 'abcdef')]), page([]))['metrics_percent']['block_type_accuracy'])


if __name__ == "__main__":
    unittest.main()
