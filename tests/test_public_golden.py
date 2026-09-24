"""Fast public golden gates using committed Docling snapshots and source PDFs."""

import json
from pathlib import Path
import unittest

from benchmark.public_golden.run import run_case
from pdf_to_book.docling_adapter import recover_word_spacing


ROOT = Path(__file__).resolve().parents[1]


class PublicGoldenTest(unittest.TestCase):
    def test_source_spacing_repairs_observed_linux_extraction(self):
        self.assertEqual(
            "1.7 List of Data Structures",
            recover_word_spacing("1.7 ListofDataStructures", "1.7 List of Data Structures"),
        )
        self.assertEqual(
            "introduce an external ‘cleaving potential’ in a bulk solid system;",
            recover_word_spacing(
                "introduceanexternal 'cleavingpotential' inabulksolidsystem;",
                "1. introduce an external ‘cleaving potential’ in a bulk solid system;",
                marker="1.",
            ),
        )
        self.assertEqual("already spaced", recover_word_spacing("already spaced", "bad source"))

    def test_reviewed_public_corpus(self):
        manifest = json.loads((ROOT / "benchmark/public_golden/manifest.json").read_text())
        self.assertEqual(len(manifest["cases"]), 5)
        for case in manifest["cases"]:
            with self.subTest(case=case["id"]):
                self.assertEqual([], run_case(case))


if __name__ == "__main__":
    unittest.main()
