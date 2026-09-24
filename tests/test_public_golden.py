"""Fast public golden gates using committed Docling snapshots and source PDFs."""

import json
from pathlib import Path
import unittest

from benchmark.public_golden.run import run_case


ROOT = Path(__file__).resolve().parents[1]


class PublicGoldenTest(unittest.TestCase):
    def test_reviewed_public_corpus(self):
        manifest = json.loads((ROOT / "benchmark/public_golden/manifest.json").read_text())
        self.assertEqual(len(manifest["cases"]), 5)
        for case in manifest["cases"]:
            with self.subTest(case=case["id"]):
                self.assertEqual([], run_case(case))


if __name__ == "__main__":
    unittest.main()
