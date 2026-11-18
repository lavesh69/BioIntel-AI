from __future__ import annotations

import shutil
import sys
import time
import unittest
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TEMP_ROOT = ROOT / ".test-tmp"
TEMP_ROOT.mkdir(exist_ok=True)
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from biointel.shiro.core.orchestrator import ShiroOrchestrator
from biointel.shiro.exceptions import EmbeddingModelUnavailableError, ProjectAccessError, ProviderUnavailableError, UserCancellationError
from biointel.shiro.ingestion.chunking import chunk_sections
from biointel.shiro.ingestion.extractors import ExtractedSection
from biointel.shiro.integrations.demo import DEMO_PROJECT_ID
from biointel.shiro.generation.providers.ollama import OllamaLocalProvider
from biointel.shiro.integrations.literature import redact_external_query
from biointel.shiro.retrieval.vector_store import build_embedding_provider


class ShiroCompletionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = TEMP_ROOT / ("shiro-complete-" + uuid4().hex)
        self.root.mkdir()
        self.service = ShiroOrchestrator(self.root, self.root / "shiro-data")

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_document_chunking_preserves_locations_and_identifiers(self) -> None:
        sections = [ExtractedSection("TP53 c.215C>G p.Pro72Arg measured at 2.8-fold. " * 20, "page 7", "Variants")]
        chunks = chunk_sections(sections, maximum=400, overlap=50)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0].location, "page 7")
        self.assertTrue(all(chunk.section == "Variants" for chunk in chunks))
        self.assertTrue(any("TP53" in chunk.text and "c.215C>G" in chunk.text for chunk in chunks))

    def test_report_and_module_adapters_are_filterable(self) -> None:
        report = self.service.ingest_report(
            "P1", "REP-7", "RNA report", "TP53 increased in the research cohort.",
            module_id="rna_seq", analysis_id="RUN-1",
        )
        module = self.service.ingest_module_result(
            "P1", "variant_analysis", "RUN-2", "BRCA1 variant evidence was retained.",
            parameters={"depth": 30}, quality_control={"pass": True},
            result_rows=[{"gene": "BRCA1", "variant": "c.68_69del"}],
        )
        by_report = self.service.retrieve("P1", "TP53 RNA", report_id="REP-7")
        by_module = self.service.retrieve("P1", "BRCA1 variant", module_id="variant_analysis")
        self.assertTrue(by_report)
        self.assertTrue(by_module)
        self.assertEqual(report.source.metadata["report_id"], "REP-7")
        self.assertEqual(module.source.metadata["analysis_id"], "RUN-2")
        self.assertEqual(by_report[0].source.source_type, "biointel_report")
        self.assertEqual(by_module[0].source.source_type, "module_result")

    def test_source_delete_removes_index_and_managed_file(self) -> None:
        result = self.service.ingest("P1", b"TP53 source lifecycle evidence", "delete-me.txt")
        stored = Path(result.source.file_path)
        self.assertTrue(stored.is_file())
        self.service.ingestion.delete_source("P1", result.source.source_id)
        self.assertFalse(stored.exists())
        self.assertEqual(self.service.repository.index_status("P1")["sources"], 0)
        with self.assertRaises(ProjectAccessError):
            self.service.ingestion.delete_source("P2", result.source.source_id)

    def test_job_status_and_cancellation_are_project_scoped(self) -> None:
        job_id = self.service.repository.create_job("P1", "index_rebuild")
        cancelled = self.service.jobs.cancel("P1", job_id)
        self.assertEqual(cancelled["state"], "cancelled")
        self.assertTrue(cancelled["cancel_requested"])
        self.assertIsNone(self.service.repository.get_job(job_id, "P2"))
        with self.assertRaises(ProjectAccessError):
            self.service.jobs.cancel("P2", job_id)

    def test_background_ingestion_reaches_terminal_state(self) -> None:
        job = self.service.submit_ingestion("P1", b"TP53 background evidence", "background.txt")
        state = job["state"]
        final = job
        for _ in range(100):
            final = self.service.repository.get_job(job["job_id"], "P1") or {}
            state = final.get("state", "")
            if state in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.02)
        self.assertEqual(state, "completed", final)
        self.assertEqual(final["result"]["source"]["project_id"], "P1")
        self.assertNotIn("file_path", final["result"]["source"])

    def test_demo_is_synthetic_isolated_and_resettable(self) -> None:
        demo = self.service.create_demo()
        self.assertEqual(demo["project_id"], DEMO_PROJECT_ID)
        sources = self.service.repository.list_sources(DEMO_PROJECT_ID)
        self.assertEqual(len(sources), 2)
        self.assertTrue(all(item.synthetic for item in sources))
        response = self.service.chat(DEMO_PROJECT_ID, "TP53 synthetic result summarize karo")
        self.assertEqual(response.evidence_status, "grounded")
        self.assertTrue(all(item.synthetic for item in response.citations))
        self.assertFalse(self.service.retrieve("REAL-PROJECT", "TP53"))
        reset = self.service.reset_demo()
        self.assertTrue(reset["reset"])
        self.assertEqual(self.service.repository.index_status(DEMO_PROJECT_ID)["sources"], 0)

    def test_external_query_redaction_preserves_scientific_terms(self) -> None:
        redacted, labels = redact_external_query("PROJECT:SECRET patient-ABC123 TP53 evidence email a@b.com")
        self.assertIn("TP53", redacted)
        self.assertNotIn("ABC123", redacted)
        self.assertNotIn("a@b.com", redacted)
        self.assertIn("patient_identifier", labels)
        self.assertIn("email", labels)

    def test_local_reranker_is_optional_and_bounded(self) -> None:
        self.service.ingest("P1", b"TP53 TP53 fold change 2.8 evidence", "strong.txt")
        self.service.ingest("P1", b"General TP53 background note", "weak.txt")
        regular = self.service.retrieve("P1", "TP53 fold change", top_k=1, rerank=False)
        reranked = self.service.retrieve("P1", "TP53 fold change", top_k=1, rerank=True)
        self.assertEqual(len(regular), 1)
        self.assertEqual(len(reranked), 1)
        self.assertEqual(reranked[0].source.filename, "strong.txt")


    def test_cancelled_generation_does_not_produce_an_answer(self) -> None:
        with self.assertRaises(UserCancellationError):
            self.service.chat("P1", "TP53 evidence", cancelled=lambda: True)

    def test_optional_embedding_provider_fails_closed_without_configuration(self) -> None:
        with self.assertRaises(EmbeddingModelUnavailableError):
            build_embedding_provider("unknown-cloud", "model", 384)

    def test_ollama_is_restricted_to_loopback(self) -> None:
        with self.assertRaises(ProviderUnavailableError):
            OllamaLocalProvider("model", "https://example.com")


if __name__ == "__main__":
    unittest.main(verbosity=2)