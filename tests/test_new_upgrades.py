import unittest, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.shiro.core.context_retention import ShiroContextEngine
from biointel.shiro.retrieval.reranker import ScientificReranker
from biointel.reports.exporter import ScientificReportExporter, ExportableReport


class TestNewPlatformUpgrades(unittest.TestCase):
    def test_context_engine(self) -> None:
        engine = ShiroContextEngine()
        engine.add_turn("What is TP53?", "TP53 is a tumor suppressor gene.", ["TP53"])
        resolved = engine.resolve_contextual_query("Explain its mutation rate")
        self.assertIn("TP53", resolved)

    def test_reranker(self) -> None:
        reranker = ScientificReranker()
        class DummyChunk:
            text = "TP53 c.215C>G variant analysis"
        class DummyResult:
            score = 0.50
            chunk = DummyChunk()

        reranked = reranker.rerank("TP53 variant", [DummyResult()])
        self.assertEqual(len(reranked), 1)

    def test_report_exporter(self) -> None:
        report = ExportableReport(
            title="RNA-Seq Differential Report",
            project_id="P-101",
            generated_at_utc="2026-08-04T12:00:00Z",
            summary_text="TP53 expression increased 2.8 fold.",
            citations=({"citation_id": "CIT-01", "filename": "rna.pdf", "location": "p.2", "excerpt": "TP53 up"},),
            confidence_score="95%",
            language="en",
        )
        md = ScientificReportExporter.to_markdown(report)
        js = ScientificReportExporter.to_json(report)
        self.assertIn("P-101", md)
        self.assertIn("CIT-01", js)


if __name__ == "__main__":
    unittest.main()
