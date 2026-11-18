import unittest, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.shiro.core.synonym_expander import ScientificQueryExpander
from biointel.shiro.generation.smart_synthesizer import SmartEvidenceSynthesizer
from biointel.shiro.eval.confidence_evaluator import ShiroRAGEvaluator, ConfidenceScore


class ShiroNewModulesTest(unittest.TestCase):
    def test_synonym_expander(self) -> None:
        expander = ScientificQueryExpander()
        query = "TP53 mutation results"
        expanded = expander.expand_query(query)
        self.assertIn("p53", expanded)
        keywords = expander.extract_keywords("TP53 c.215C>G EGFR IC50")
        self.assertIn("TP53", keywords)
        self.assertIn("EGFR", keywords)

    def test_confidence_evaluator(self) -> None:
        evaluator = ShiroRAGEvaluator()
        class DummyItem:
            score = 0.85
            matched_terms = ("TP53", "results")
        class DummyCit:
            citation_id = "CIT-01"

        score = evaluator.evaluate("TP53 results", [DummyItem()], [DummyCit()])
        self.assertIsInstance(score, ConfidenceScore)
        self.assertGreater(score.overall_confidence, 0.5)
        self.assertEqual(score.rating, "High Confidence")


if __name__ == "__main__":
    unittest.main()
