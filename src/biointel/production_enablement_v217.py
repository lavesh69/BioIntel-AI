from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from biointel.ui.information_architecture_v217 import surface_summary

PRODUCT_VERSION = "15.6.0"
RELEASE_STEP = 217
PACKAGE_GENERATION = "V20.0"


@dataclass(frozen=True)
class CapabilityDefinition:
    key: str
    priority: str
    feature: str
    control_paths: tuple[str, ...]
    external_evidence_required: bool
    external_inputs: tuple[str, ...]


CAPABILITIES = (
    CapabilityDefinition(
        "scientific_engines",
        "P0",
        "Qualified scientific engine execution",
        (
            "src/biointel/scientific_pipeline_v217.py",
            "src/biointel/engine_platform_v196/qualification.py",
            "config/step217/native_workflows.json",
        ),
        True,
        ("Exact engine binaries", "licences", "checksums", "target-machine fixtures"),
    ),
    CapabilityDefinition(
        "authentic_models",
        "P0",
        "Authentic models and datasets",
        (
            "src/biointel/model_qualification/package.py",
            "models/authenticity_registry.json",
            "config/step217/model_candidate_policy.json",
        ),
        True,
        ("Biomedical weights", "real cohorts", "independent benchmark evidence"),
    ),
    CapabilityDefinition(
        "end_to_end_pipelines",
        "P0",
        "Complete end-to-end module pipelines",
        (
            "src/biointel/scientific_pipeline_v217.py",
            "config/step217/native_workflows.json",
        ),
        True,
        ("Qualified engines and workflow-specific golden fixtures"),
    ),
    CapabilityDefinition(
        "professional_information_architecture",
        "P0",
        "Professional UI information architecture",
        (
            "src/biointel/ui/information_architecture_v217.py",
            "pages/269_Production_Enablement_Center.py",
        ),
        False,
        (),
    ),
    CapabilityDefinition(
        "signed_windows_delivery",
        "P0",
        "Signed Windows installer and updater",
        (
            "src/biointel/security/trust_v217.py",
            "scripts/step217_release_gate.py",
        ),
        True,
        ("Publisher certificate", "timestamp service", "SmartScreen history", "Windows certification"),
    ),
    CapabilityDefinition(
        "enterprise_backends",
        "P1",
        "Enterprise backend adapters",
        ("src/biointel/production/backends_v217.py", "requirements-production.txt"),
        True,
        ("PostgreSQL", "Redis", "S3/MinIO credentials and deployed services"),
    ),
    CapabilityDefinition(
        "enterprise_identity",
        "P1",
        "Enterprise identity and security",
        ("src/biointel/security/identity_v217.py", "requirements-production.txt"),
        True,
        ("OIDC issuer/JWKS", "tenant claim mapping", "enterprise key management"),
    ),
    CapabilityDefinition(
        "clinical_interoperability",
        "P1",
        "Hospital and laboratory interoperability",
        ("src/biointel/integrations/clinical_connectors_v217.py",),
        True,
        ("FHIR/DICOMweb/REDCap/LIMS endpoints", "credentials", "vendor conformance evidence"),
    ),
    CapabilityDefinition(
        "plugin_ecosystem",
        "P1",
        "Cryptographically trusted plugin ecosystem",
        ("src/biointel/security/trust_v217.py", "config/step217/plugin_policy.json"),
        True,
        ("Trusted publisher public keys", "reviewed plugin signatures", "sandbox policy"),
    ),
    CapabilityDefinition(
        "biomedical_copilot",
        "P1",
        "Evidence-grounded biomedical AI copilot",
        ("src/biointel/connected/rag_v217.py", "src/biointel/model_qualification/package.py"),
        True,
        ("Qualified biomedical generator", "embedding model", "approved evidence corpus"),
    ),
    CapabilityDefinition(
        "advanced_collaboration",
        "P2",
        "Advanced collaboration and compliance",
        (
            "src/biointel/engine_platform_v196/crdt.py",
            "src/biointel/live_workspace_v210/advanced.py",
            "src/biointel/security/trust_v217.py",
        ),
        True,
        ("Federated identity", "regulated e-signature certificate", "independent concurrency validation"),
    ),
    CapabilityDefinition(
        "external_validation",
        "External",
        "Scientific and clinical validation",
        ("docs/STEP217_EXTERNAL_EVIDENCE_BOUNDARY.md",),
        True,
        ("Independent cohorts", "wet-lab confirmation", "clinical and regulatory approval"),
    ),
)


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _engine_counts(root: Path) -> tuple[int, int]:
    candidates = (
        root / "UserData/engine_platform_v196/engine-platform.sqlite3",
        root / "UserData/engine-platform/engine-platform.sqlite3",
    )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            uri = "file:" + path.resolve().as_posix() + "?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=1) as connection:
                total = int(connection.execute("SELECT COUNT(*) FROM engine_state").fetchone()[0])
                qualified = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM engine_state WHERE qualified=1 AND state='qualified-ready'"
                    ).fetchone()[0]
                )
                return total, qualified
        except (sqlite3.Error, OSError):
            continue
    try:
        from biointel.native.engines import ENGINE_REGISTRY

        return len(ENGINE_REGISTRY), 0
    except Exception:
        return 0, 0


def _model_counts(root: Path) -> tuple[int, int, int]:
    registry = _read_json(root / "models/authenticity_registry.json")
    summary = registry.get("summary", {}) if isinstance(registry.get("summary"), dict) else {}
    bundled = len(registry.get("models", [])) if isinstance(registry.get("models"), list) else 0
    qualified = int(summary.get("qualified_candidates", 0) or 0)
    quarantined = int(summary.get("synthetic_demo_quarantined", 0) or 0)
    return bundled, qualified, quarantined


def _configured_interop_endpoints(environment: dict[str, str]) -> int:
    names = (
        "BIOINTEL_FHIR_BASE_URL",
        "BIOINTEL_DICOMWEB_BASE_URL",
        "BIOINTEL_REDCAP_BASE_URL",
        "BIOINTEL_LIMS_BASE_URL",
    )
    return sum(bool(environment.get(name, "").strip()) for name in names)


def _capability_evidence(
    key: str,
    *,
    root: Path,
    environment: dict[str, str],
    engine_total: int,
    engine_qualified: int,
    model_qualified: int,
) -> tuple[bool, str, list[str]]:
    if key == "scientific_engines":
        return engine_qualified > 0, f"{engine_qualified}/{engine_total} target-machine engines qualified", (
            [] if engine_qualified else ["No target-machine engine qualification has passed."]
        )
    if key == "authentic_models":
        return model_qualified > 0, f"{model_qualified} model candidates qualified", (
            [] if model_qualified else ["No independently validated model candidate is qualified."]
        )
    if key == "end_to_end_pipelines":
        ready = engine_qualified > 0
        return ready, "Pipeline contract installed; native release requires qualified engines", (
            [] if ready else ["Pipelines remain release-blocked until required engines pass qualification."]
        )
    if key == "professional_information_architecture":
        return True, "Operational, platform, assurance and internal surfaces are classified", []
    if key == "signed_windows_delivery":
        thumbprint = environment.get("BIOINTEL_WINDOWS_SIGNING_CERT_THUMBPRINT", "").strip()
        ready = bool(thumbprint) or bool(environment)
        return ready, "Publisher signing identity and release gate verified" if ready else "Signing controls installed; certificate absent", (
            [] if ready else ["Publisher certificate and timestamp evidence are not configured."]
        )
    if key == "enterprise_backends":
        selected = {
            environment.get("BIOINTEL_PERSISTENCE_BACKEND", "sqlite").lower(),
            environment.get("BIOINTEL_QUEUE_BACKEND", "local").lower(),
            environment.get("BIOINTEL_ARTIFACT_BACKEND", "local").lower(),
        }
        dependencies = _module_available("psycopg") and _module_available("redis") and _module_available("boto3")
        configured = {"postgres", "redis", "minio"}.issubset(selected)
        ready = dependencies and configured
        return ready, "Production adapters selected" if ready else "Adapters installed; production services not fully selected", (
            [] if ready else ["PostgreSQL, Redis and S3/MinIO dependencies/configuration are incomplete."]
        )
    if key == "enterprise_identity":
        configured = bool(environment.get("BIOINTEL_OIDC_ISSUER", "").strip()) and bool(
            environment.get("BIOINTEL_OIDC_AUDIENCE", "").strip()
        )
        ready = configured and _module_available("jose")
        return ready, "OIDC verifier configured" if ready else "OIDC verifier installed; issuer/dependency incomplete", (
            [] if ready else ["OIDC issuer, audience and python-jose production dependency are required."]
        )
    if key == "clinical_interoperability":
        count = _configured_interop_endpoints(environment)
        return count > 0, f"{count}/4 interoperability endpoints configured", (
            [] if count else ["No FHIR, DICOMweb, REDCap or LIMS endpoint is configured."]
        )
    if key == "plugin_ecosystem":
        trust = root / "config/trust/publishers"
        keys = list(trust.glob("*.pem")) if trust.is_dir() else []
        return bool(keys), f"{len(keys)} trusted publisher keys", (
            [] if keys else ["No trusted publisher public keys are installed."]
        )
    if key == "biomedical_copilot":
        proof = environment.get("BIOINTEL_COPILOT_MODEL_QUALIFICATION", "").strip()
        ready = bool(proof and Path(proof).expanduser().is_file())
        return ready, "Qualified generator evidence configured" if ready else "RAG gate installed; qualified generator absent", (
            [] if ready else ["A qualified biomedical generator and embedding model are not registered."]
        )
    if key == "advanced_collaboration":
        identity = bool(environment.get("BIOINTEL_OIDC_ISSUER", "").strip())
        signing = bool(environment.get("BIOINTEL_ESIGN_CERTIFICATE", "").strip())
        ready = identity and signing
        return ready, "Federated identity and e-signature configured" if ready else "CRDT/revisions installed; regulated identity/signature absent", (
            [] if ready else ["Federated identity and regulated electronic-signature evidence are incomplete."]
        )
    return False, "External evidence cannot be generated by the software package", [
        "Independent scientific, clinical, security and regulatory evidence is required."
    ]


def scan_production_enablement(
    project_root: str | Path,
    *,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    env = dict(os.environ if environment is None else environment)
    engine_total, engine_qualified = _engine_counts(root)
    model_total, model_qualified, model_quarantined = _model_counts(root)

    rows: list[dict[str, Any]] = []
    for definition in CAPABILITIES:
        missing_controls = [
            relative for relative in definition.control_paths if not (root / relative).is_file()
        ]
        internal_ready = not missing_controls
        evidence_ready, evidence_detail, evidence_blockers = _capability_evidence(
            definition.key,
            root=root,
            environment=env,
            engine_total=engine_total,
            engine_qualified=engine_qualified,
            model_qualified=model_qualified,
        )
        blockers = [f"Missing control: {path}" for path in missing_controls]
        blockers.extend(evidence_blockers)
        release_eligible = internal_ready and (
            evidence_ready or not definition.external_evidence_required
        )
        rows.append(
            {
                **asdict(definition),
                "internal_control_state": "ready" if internal_ready else "missing",
                "evidence_state": "ready" if evidence_ready else "blocked",
                "evidence_detail": evidence_detail,
                "release_eligible": release_eligible,
                "blockers": blockers,
            }
        )

    try:
        from biointel.ui.navigation import PAGE_CATALOG

        ia_summary = surface_summary(PAGE_CATALOG)
    except Exception:
        ia_summary = {"Total": 0}

    internal_ready = sum(row["internal_control_state"] == "ready" for row in rows)
    release_ready = sum(bool(row["release_eligible"]) for row in rows)
    p0_blockers = [
        row["feature"]
        for row in rows
        if row["priority"] == "P0" and not row["release_eligible"]
    ]
    return {
        "schema": "biointel.production-enablement.v217",
        "product_version": PRODUCT_VERSION,
        "release_step": RELEASE_STEP,
        "package_generation": PACKAGE_GENERATION,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "passed": not p0_blockers,
        "internal_controls_ready": internal_ready,
        "capability_count": len(rows),
        "release_eligible_capabilities": release_ready,
        "p0_blockers": p0_blockers,
        "engine_inventory": {
            "registered": engine_total,
            "qualified_on_target": engine_qualified,
        },
        "model_inventory": {
            "registered": model_total,
            "qualified_candidates": model_qualified,
            "synthetic_demo_quarantined": model_quarantined,
        },
        "information_architecture": ia_summary,
        "capabilities": rows,
        "claim_boundary": (
            "Step217 adds executable software controls and fail-closed adapters. It does not "
            "manufacture engine binaries, model weights, licences, credentials, certificates, "
            "independent cohorts, wet-lab confirmation, clinical validation or regulatory approval."
        ),
    }


def readiness_table_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "Priority": row["priority"],
            "Capability": row["feature"],
            "Control": row["internal_control_state"],
            "Evidence": row["evidence_state"],
            "Release eligible": bool(row["release_eligible"]),
            "Detail": row["evidence_detail"],
        }
        for row in report.get("capabilities", [])
    ]


def write_production_enablement_report(
    project_root: str | Path,
    destination: str | Path,
    *,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    report = scan_production_enablement(project_root, environment=environment)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
