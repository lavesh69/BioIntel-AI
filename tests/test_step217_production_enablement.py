from __future__ import annotations

import base64
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import httpx
import numpy as np

from biointel.connected.rag_v217 import (
    EvidenceChunk,
    EvidenceGroundedRag,
    VectorEvidenceIndex,
)
from biointel.engine_platform_v196.state import EngineStateStore
from biointel.integrations.clinical_connectors_v217 import (
    ConnectorConfiguration,
    FhirConnector,
)
from biointel.production.backends_v217 import BackendConfiguration, backend_readiness
from biointel.production_enablement_v217 import scan_production_enablement
from biointel.scientific_pipeline_v217 import (
    PipelineSpec,
    QualifiedPipelineExecutor,
    sha256_file,
)
from biointel.security.identity_v217 import validate_scim_user
from biointel.security.trust_v217 import canonical_json, inspect_signed_archive
from biointel.ui.information_architecture_v217 import page_surface


class FakeEmbedding:
    model_id = "fixture-embedding"
    qualification_id = "qualification-embedding-fixture"

    def embed(self, texts):
        rows = []
        for text in texts:
            lowered = text.lower()
            rows.append([1.0 if "alpha" in lowered else 0.0, 1.0 if "beta" in lowered else 0.0])
        return np.asarray(rows, dtype=np.float32)


class FakeGenerator:
    model_id = "fixture-generator"
    qualification_id = "qualification-generator-fixture"

    def generate(self, *, question: str, evidence_context: str) -> str:
        del question, evidence_context
        return "The fixture finding is grounded [EVIDENCE:alpha]."


class Step217Tests(unittest.TestCase):
    def test_information_architecture_separates_internal_pages(self) -> None:
        operational = SimpleNamespace(
            key="sequence",
            title="Sequence analyzer",
            category="Bioinformatics",
            keywords=("fasta",),
        )
        internal = SimpleNamespace(
            key="step217_internal",
            title="Step217 internal assurance",
            category="Operations",
            keywords=("implementation report",),
        )
        self.assertEqual(page_surface(operational), "Operational")
        self.assertEqual(page_surface(internal), "Internal")

    def test_release_scan_is_honest_about_external_blockers(self) -> None:
        report = scan_production_enablement(ROOT, environment={})
        self.assertEqual(report["internal_controls_ready"], report["capability_count"])
        self.assertIsInstance(report["p0_blockers"], list)

    def test_pipeline_blocks_unqualified_engine(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = EngineStateStore(Path(temporary) / "state.sqlite3")
            executor = QualifiedPipelineExecutor(store, Path(temporary) / "runs")
            spec = PipelineSpec("fixture", "missing", ("{executable}",), {"result": "result.txt"})
            source = Path(temporary) / "input.txt"
            source.write_text("fixture", encoding="utf-8")
            with self.assertRaises(PermissionError):
                executor.run(spec, {"raw": source})

    def test_pipeline_records_all_execution_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = EngineStateStore(root / "state.sqlite3")
            executable = Path(sys.executable).resolve()
            store.upsert_engine(
                "python-fixture",
                state="qualified-ready",
                executable=str(executable),
                executable_sha256=sha256_file(executable),
                qualified=True,
                version=sys.version,
            )
            source = root / "input.txt"
            source.write_text("alpha", encoding="utf-8")
            script = (
                "from pathlib import Path; "
                "Path(r'{output:result}').write_text("
                "Path(r'{input:raw}').read_text(encoding='utf-8').upper(), encoding='utf-8')"
            )
            spec = PipelineSpec(
                "python-fixture-workflow",
                "python-fixture",
                ("{executable}", "-c", script),
                {"result": "results/result.txt"},
            )
            result = QualifiedPipelineExecutor(store, root / "runs").run(
                spec,
                {"raw": source},
                parser=lambda outputs: {
                    "value": outputs["result"].read_text(encoding="utf-8")
                },
            )
            self.assertTrue(result.passed, result.errors)
            self.assertEqual(result.parsed_results["value"], "ALPHA")
            self.assertEqual(
                [item.stage for item in result.stages],
                [
                    "raw_input",
                    "quality_control",
                    "native_engine_execution",
                    "result_validation",
                    "native_result_parsing",
                    "provenance",
                ],
            )
            self.assertTrue(Path(result.report_path).is_file())

    def test_signed_plugin_verification_detects_tampering(self) -> None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        with tempfile.TemporaryDirectory() as temporary:
            trust_store = Path(temporary)
            private = Ed25519PrivateKey.generate()
            public = private.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            (trust_store / "fixture.pem").write_bytes(public)
            module = b"VALUE = 1\n"
            manifest = {
                "name": "fixture-plugin",
                "version": "1.0.0",
                "publisher_key_id": "fixture",
                "files": [{"path": "plugin.py", "sha256": __import__("hashlib").sha256(module).hexdigest()}],
            }
            signature = base64.b64encode(private.sign(canonical_json(manifest))).decode("ascii")

            def archive(payload: bytes) -> bytes:
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as value:
                    value.writestr("plugin.json", json.dumps(manifest))
                    value.writestr("SIGNATURE.ed25519", signature)
                    value.writestr("plugin.py", payload)
                return buffer.getvalue()

            valid = inspect_signed_archive(
                archive(module),
                trust_store=trust_store,
                artifact_type="plugin",
            )
            self.assertTrue(valid.passed, valid.findings)
            tampered = inspect_signed_archive(
                archive(b"VALUE = 2\n"),
                trust_store=trust_store,
                artifact_type="plugin",
            )
            self.assertFalse(tampered.passed)
            self.assertTrue(any("hash mismatch" in item.lower() for item in tampered.findings))

    def test_vector_rag_requires_and_preserves_evidence_ids(self) -> None:
        chunks = (
            EvidenceChunk("alpha", "Alpha evidence", "https://example.test/a", "a" * 64, {}),
            EvidenceChunk("beta", "Beta evidence", "https://example.test/b", "b" * 64, {}),
        )
        embedding = FakeEmbedding()
        index = VectorEvidenceIndex.build(chunks, embedding)
        answer = EvidenceGroundedRag(index, embedding, FakeGenerator()).answer("alpha")
        self.assertEqual(answer.citations, ("alpha",))
        self.assertEqual(answer.evidence[0].chunk.evidence_id, "alpha")

    def test_fhir_connector_validates_capability_statement(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/metadata")
            return httpx.Response(200, json={"resourceType": "CapabilityStatement"})

        connector = FhirConnector(
            ConnectorConfiguration("http://localhost/", allow_local_http=True),
            transport=httpx.MockTransport(handler),
        )
        try:
            self.assertEqual(
                connector.capability_statement()["resourceType"],
                "CapabilityStatement",
            )
        finally:
            connector.close()

    def test_backend_and_scim_contracts(self) -> None:
        report = backend_readiness(BackendConfiguration("", "", "", ""))
        self.assertFalse(report["ready"])
        user = validate_scim_user(
            {
                "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
                "userName": "researcher@example.test",
                "active": True,
            }
        )
        self.assertTrue(user["active"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
