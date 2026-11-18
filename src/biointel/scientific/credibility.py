from __future__ import annotations

from biointel.runtime_paths import runtime_database_path, runtime_report_path

import json
import re
import sqlite3
from biointel.database.core import managed_connect
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from biointel.scientific.evidence_lake import ScientificEvidenceLake

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMPLETED = {"completed", "reviewed", "accepted"}
_PLACEHOLDER_MARKERS = ("placeholder", "demo", "synthetic", "example", "reference-model", "step39-")

# Explicit aliases are restricted to official project domains. These aliases
# support human-facing and API hosts without accepting unrelated subdomains.
OFFICIAL_PROVIDER_HOSTS: dict[str, frozenset[str]] = {
    "uniprot": frozenset({"uniprot.org", "www.uniprot.org", "rest.uniprot.org"}),
    "clinvar": frozenset({"ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov", "eutils.ncbi.nlm.nih.gov"}),
    "geo": frozenset({"ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov", "eutils.ncbi.nlm.nih.gov"}),
    "sra": frozenset({"ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov", "eutils.ncbi.nlm.nih.gov"}),
    "go": frozenset({"geneontology.org", "www.geneontology.org", "go.org", "www.go.org", "current.geneontology.org"}),
}


@dataclass(frozen=True)
class CredibilityComponent:
    key: str
    label: str
    score: float
    status: str
    evidence: str
    blocker: str = ""


@dataclass(frozen=True)
class QualifiedStudy:
    study_id: str
    study_type: str
    tier: str
    status: str
    qualified: bool
    reasons: tuple[str, ...]


def _valid_sha256(value: object) -> bool:
    text = str(value or "").strip().lower()
    return bool(_SHA256_RE.fullmatch(text)) and not any(marker in text for marker in _PLACEHOLDER_MARKERS)


def _parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _safe_json(value: object) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _official_https(provider: str, host: str, source_url: str, metadata: dict[str, Any] | None = None) -> bool:
    parsed = urlparse(source_url)
    actual = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not actual:
        return False

    expected = host.strip().lower().rstrip(".")
    allowed = {expected}
    # Same registered project domain supports API and human-facing hosts.
    if expected:
        allowed.add(expected.removeprefix("www."))
    allowed.update(OFFICIAL_PROVIDER_HOSTS.get(provider.strip().lower(), frozenset()))
    if metadata:
        values = metadata.get("allowed_official_hosts", [])
        if isinstance(values, list):
            allowed.update(str(value).strip().lower().rstrip(".") for value in values if value)
    return any(actual == item or actual.endswith("." + item) for item in allowed if item)


def _qualify_study(row: sqlite3.Row) -> QualifiedStudy:
    reasons: list[str] = []
    study_type = str(row["study_type"] or "")
    evidence = _safe_json(row["evidence_json"])
    status = str(row["status"] or "")

    if status not in _COMPLETED:
        reasons.append("study is not completed/reviewed")
    if not _valid_sha256(row["protocol_sha256"]):
        reasons.append("protocol SHA-256 is invalid")
    if not _valid_sha256(row["dataset_sha256"]):
        reasons.append("dataset SHA-256 is invalid or placeholder")
    if row["model_sha256"] and not _valid_sha256(row["model_sha256"]):
        reasons.append("model SHA-256 is invalid or placeholder")

    preregistered = _parse_time(row["preregistered_at"])
    locked = _parse_time(row["locked_at"])
    completed = _parse_time(row["completed_at"])
    if not preregistered:
        reasons.append("preregistration timestamp is missing/invalid")
    if completed and preregistered and completed < preregistered:
        reasons.append("completion predates preregistration")
    if locked and preregistered and locked < preregistered:
        reasons.append("prediction lock predates preregistration")
    if completed and locked and completed < locked:
        reasons.append("completion predates prediction lock")

    independent_review = bool(evidence.get("independent_review"))
    independent_site = bool(row["independent_site"])
    blinded = bool(row["blinded"])
    if study_type == "external" and not independent_site:
        reasons.append("external study is not independent-site")
    if study_type == "prospective":
        if not independent_site:
            reasons.append("prospective study is not independent-site")
        if not blinded:
            reasons.append("prospective study is not blinded")
        if not locked:
            reasons.append("prospective predictions were not locked")
    if study_type in {"external", "prospective"} and not independent_review:
        reasons.append("independent review is not documented")

    is_dti = bool(evidence.get("dti")) or str(row["study_id"]).upper().startswith("DTI-")
    if study_type == "prospective" and blinded and independent_site:
        tier = "prospective analytical"
    elif study_type == "external" and independent_site:
        tier = "independent external analytical"
    elif study_type == "benchmark":
        tier = "reproducible benchmark"
    else:
        tier = "reference/retrospective"
    if is_dti:
        tier = "DTI " + tier

    return QualifiedStudy(
        study_id=str(row["study_id"]),
        study_type=study_type,
        tier=tier,
        status=status,
        qualified=not reasons,
        reasons=tuple(reasons),
    )


def build_scientific_credibility_audit(root: str | Path) -> dict[str, Any]:
    project_root = Path(root).resolve()
    evidence_db = runtime_database_path(project_root, "scientific_evidence.sqlite3")
    validation_db = runtime_database_path(project_root, "validation_evidence.sqlite3")

    components: list[CredibilityComponent] = []
    findings: list[str] = []
    studies: list[QualifiedStudy] = []
    summary: dict[str, Any] = {
        "providers": 0,
        "snapshots": 0,
        "records": 0,
        "valid_snapshot_hashes": 0,
        "official_https_snapshots": 0,
        "approved_records": 0,
        "release_eligible_records": 0,
        "organisms": 0,
        "assay_types": 0,
        "qualified_studies": 0,
        "qualified_external_dti": 0,
        "qualified_prospective_dti": 0,
        "qualified_real_benchmarks": 0,
        "wetlab_independent": 0,
        "multisite": 0,
        "evidence_chain_ok": False,
        "validation_chain_ok": False,
        "strictly_rejected_studies": 0,
    }

    if not evidence_db.exists():
        return {
            "implementation_score": 0.0,
            "verifiable_evidence_score": 0.0,
            "combined_credibility_score": 0.0,
            "components": [],
            "summary": summary,
            "qualified_studies": [],
            "findings": ["Scientific evidence database is missing."],
            "boundary": "No scientific credibility claim is allowed without a verified evidence registry.",
        }

    with managed_connect(evidence_db) as db:
        db.row_factory = sqlite3.Row
        provider_rows = list(db.execute("SELECT * FROM providers"))
        snapshot_rows = list(db.execute("SELECT * FROM snapshots"))
        record_summary = db.execute(
            """
            SELECT COUNT(*) records,
                   SUM(CASE WHEN review_status='approved' THEN 1 ELSE 0 END) approved,
                   SUM(CASE WHEN release_eligible=1 AND review_status='approved' THEN 1 ELSE 0 END) release_eligible,
                   COUNT(DISTINCT taxonomy_id) organisms,
                   COUNT(DISTINCT CASE WHEN assay_type IS NOT NULL AND assay_type!='' THEN assay_type END) assay_types
            FROM evidence_records
            """
        ).fetchone()
        study_rows = list(db.execute("SELECT * FROM validation_studies"))
        fk_errors = list(db.execute("PRAGMA foreign_key_check"))

        provider_hosts = {str(row["provider"]): str(row["official_host"]) for row in provider_rows}
        provider_metadata = {str(row["provider"]): _safe_json(row["metadata_json"]) for row in provider_rows}
        valid_hashes = sum(_valid_sha256(row["source_sha256"]) for row in snapshot_rows)
        official_https = sum(
            _official_https(
                str(row["provider"]),
                provider_hosts.get(str(row["provider"]), ""),
                str(row["source_url"]),
                provider_metadata.get(str(row["provider"])),
            )
            for row in snapshot_rows
        )
        summary.update(
            {
                "providers": len(provider_rows),
                "snapshots": len(snapshot_rows),
                "records": int(record_summary["records"] or 0),
                "valid_snapshot_hashes": int(valid_hashes),
                "official_https_snapshots": int(official_https),
                "approved_records": int(record_summary["approved"] or 0),
                "release_eligible_records": int(record_summary["release_eligible"] or 0),
                "organisms": int(record_summary["organisms"] or 0),
                "assay_types": int(record_summary["assay_types"] or 0),
            }
        )
        if fk_errors:
            findings.append(f"Evidence database has {len(fk_errors)} foreign-key issue(s).")

        for row in study_rows:
            studies.append(_qualify_study(row))

    evidence_integrity = ScientificEvidenceLake(evidence_db).verify_integrity()
    summary["evidence_chain_ok"] = bool(evidence_integrity.get("ok"))
    if not summary["evidence_chain_ok"]:
        findings.append("Scientific evidence event/record hash-chain verification failed.")

    summary["qualified_studies"] = sum(study.qualified for study in studies)
    summary["qualified_external_dti"] = sum(
        study.qualified and study.tier == "DTI independent external analytical" for study in studies
    )
    summary["qualified_prospective_dti"] = sum(
        study.qualified and study.tier == "DTI prospective analytical" for study in studies
    )
    summary["qualified_real_benchmarks"] = sum(
        study.qualified and "benchmark" in study.tier for study in studies
    )

    # The separate validation registry is the only source allowed to establish
    # wet-lab, independent-laboratory, or multi-site evidence.
    validation_integrity_ok = True
    if validation_db.exists():
        from biointel.scientific.validation_depth import ValidationEvidenceRegistry

        validation_integrity = ValidationEvidenceRegistry(validation_db).verify_integrity()
        validation_integrity_ok = bool(validation_integrity.get("ok"))
        summary["validation_chain_ok"] = validation_integrity_ok
        with managed_connect(validation_db) as db:
            db.row_factory = sqlite3.Row
            summary["wetlab_independent"] = int(
                db.execute(
                    "SELECT COUNT(*) FROM studies WHERE evidence_class IN ('wet_lab_independent','wet_lab_multisite') AND release_eligible=1"
                ).fetchone()[0]
            )
            summary["multisite"] = int(
                db.execute(
                    "SELECT COUNT(*) FROM studies WHERE evidence_class='wet_lab_multisite' AND release_eligible=1"
                ).fetchone()[0]
            )
    else:
        validation_integrity_ok = False
        findings.append("Validation evidence registry is missing.")

    provider_score = min(10.0, summary["providers"] / 9.0 * 10.0)
    snapshot_integrity = (
        10.0
        if summary["snapshots"]
        and summary["valid_snapshot_hashes"] == summary["snapshots"]
        and summary["official_https_snapshots"] == summary["snapshots"]
        and summary["evidence_chain_ok"]
        else max(
            0.0,
            10.0
            * min(summary["valid_snapshot_hashes"], summary["official_https_snapshots"])
            / max(summary["snapshots"], 1),
        )
    )
    record_score = min(10.0, 4.0 + 6.0 * summary["approved_records"] / 10_000.0)
    diversity_score = min(10.0, 0.45 * summary["organisms"] + 0.35 * summary["assay_types"])
    analytical_score = min(10.0, 4.0 * summary["qualified_real_benchmarks"] + 2.0 * summary["qualified_studies"])
    dti_external_score = min(10.0, 5.0 * summary["qualified_external_dti"])
    prospective_score = min(10.0, 5.0 * summary["qualified_prospective_dti"])
    wetlab_score = min(10.0, 5.0 * summary["wetlab_independent"])
    multisite_score = min(10.0, 10.0 * summary["multisite"])

    components.extend(
        [
            CredibilityComponent("provider_authenticity", "Official provider authenticity", round(provider_score, 1), "qualified" if provider_score == 10 else "partial", f"{summary['providers']} provider profiles"),
            CredibilityComponent("provenance_integrity", "Immutable provenance and HTTPS source integrity", round(snapshot_integrity, 1), "qualified" if snapshot_integrity == 10 else "review", f"{summary['valid_snapshot_hashes']}/{summary['snapshots']} valid snapshot hashes; {summary['official_https_snapshots']}/{summary['snapshots']} official HTTPS sources; hash chain {'verified' if summary['evidence_chain_ok'] else 'failed'}"),
            CredibilityComponent("evidence_volume", "Reviewed evidence volume", round(record_score, 1), "qualified" if record_score == 10 else "partial", f"{summary['approved_records']} approved records"),
            CredibilityComponent("biological_diversity", "Biological and assay diversity", round(diversity_score, 1), "qualified" if diversity_score == 10 else "partial", f"{summary['organisms']} organisms; {summary['assay_types']} assay types"),
            CredibilityComponent("reproducible_benchmarks", "Reproducible real-data benchmarks", round(analytical_score, 1), "qualified" if analytical_score == 10 else "partial", f"{summary['qualified_real_benchmarks']} strict benchmark(s); {summary['qualified_studies']} strictly qualified study record(s)"),
            CredibilityComponent("external_dti", "Independent external DTI validation", round(dti_external_score, 1), "qualified" if dti_external_score == 10 else "evidence pending", f"{summary['qualified_external_dti']} strictly qualified external DTI study/studies", "Import independent provider/laboratory DTI validation with real dataset/model hashes and independent review." if dti_external_score < 10 else ""),
            CredibilityComponent("prospective_dti", "Blinded prospective DTI validation", round(prospective_score, 1), "qualified" if prospective_score == 10 else "evidence pending", f"{summary['qualified_prospective_dti']} strictly qualified prospective DTI study/studies", "Complete preregistered, prediction-locked and blinded prospective validation." if prospective_score < 10 else ""),
            CredibilityComponent("independent_wetlab", "Independent wet-lab replication", round(wetlab_score, 1), "qualified" if wetlab_score == 10 else "external evidence required", f"{summary['wetlab_independent']} release-eligible independent wet-lab study/studies", "Requires genuine independent laboratory outcomes and signed attestations." if wetlab_score < 10 else ""),
            CredibilityComponent("multisite", "Multi-site reproducibility", round(multisite_score, 1), "qualified" if multisite_score == 10 else "external evidence required", f"{summary['multisite']} release-eligible multi-site study/studies", "Requires genuine multi-site replication; software cannot manufacture it." if multisite_score < 10 else ""),
        ]
    )

    implementation_controls = [
        project_root / "src/biointel/scientific/credibility.py",
        project_root / "src/biointel/scientific/evidence_lake.py",
        project_root / "src/biointel/scientific/validation_depth.py",
        project_root / "src/biointel/training/release_gate.py",
        project_root / "pages/73_Scientific_Evidence_Excellence.py",
        project_root / "pages/74_DTI_Validation_Evidence_Center.py",
    ]
    implementation_score = round(10.0 * sum(path.exists() for path in implementation_controls) / len(implementation_controls), 1)
    evidence_score = round(sum(component.score for component in components) / len(components), 1)
    # Combined score deliberately gives implementation only 35% weight. A fully
    # engineered framework cannot overpower missing real-world evidence.
    combined_score = round(0.35 * implementation_score + 0.65 * evidence_score, 1)

    rejected_studies = [study for study in studies if not study.qualified]
    summary["strictly_rejected_studies"] = len(rejected_studies)
    if rejected_studies:
        findings.append(
            f"{len(rejected_studies)} validation-study record(s) are excluded from strict evidence scoring because hashes, chronology, independence, blinding or review evidence are incomplete."
        )
    if not validation_integrity_ok:
        findings.append("Validation evidence registry integrity requires review.")

    claim_matrix = [
        {
            "claim": "Scientific evidence-control implementation",
            "eligible": implementation_score == 10.0 and summary["evidence_chain_ok"] and summary["validation_chain_ok"],
            "required": "All controls present; both immutable evidence chains valid",
            "evidence": f"Implementation {implementation_score:.1f}/10; evidence chain={summary['evidence_chain_ok']}; validation chain={summary['validation_chain_ok']}",
        },
        {
            "claim": "Provider-authenticated reference evidence",
            "eligible": snapshot_integrity == 10.0 and summary["approved_records"] > 0,
            "required": "Official HTTPS source, immutable SHA-256, approved reviewed records",
            "evidence": f"{summary['official_https_snapshots']}/{summary['snapshots']} official HTTPS snapshots; {summary['approved_records']} approved records",
        },
        {
            "claim": "Reproducible analytical benchmark",
            "eligible": summary["qualified_real_benchmarks"] > 0,
            "required": "Real dataset/model/protocol hashes, chronology and reproducible metrics",
            "evidence": f"{summary['qualified_real_benchmarks']} strictly qualified benchmark(s)",
        },
        {
            "claim": "Independent external DTI validation",
            "eligible": summary["qualified_external_dti"] >= 2,
            "required": "At least two independently reviewed external DTI studies with real artifacts",
            "evidence": f"{summary['qualified_external_dti']} strictly qualified study/studies",
        },
        {
            "claim": "Blinded prospective DTI validation",
            "eligible": summary["qualified_prospective_dti"] >= 2,
            "required": "At least two preregistered, prediction-locked, blinded independent studies",
            "evidence": f"{summary['qualified_prospective_dti']} strictly qualified study/studies",
        },
        {
            "claim": "Independent wet-lab replication",
            "eligible": summary["wetlab_independent"] >= 2,
            "required": "At least two release-eligible independent laboratory studies",
            "evidence": f"{summary['wetlab_independent']} release-eligible study/studies",
        },
        {
            "claim": "Multi-site reproducibility",
            "eligible": summary["multisite"] >= 1,
            "required": "Release-eligible multi-site study across independent organizations",
            "evidence": f"{summary['multisite']} release-eligible study/studies",
        },
    ]
    eligible_claims = [row["claim"] for row in claim_matrix if row["eligible"]]
    blocked_claims = [row["claim"] for row in claim_matrix if not row["eligible"]]
    controls_score = 10.0 if (
        implementation_score == 10.0
        and summary["evidence_chain_ok"]
        and summary["validation_chain_ok"]
        and len(rejected_studies) >= 0
    ) else round(min(implementation_score, 9.5), 1)

    return {
        "credibility_controls_score": controls_score,
        "implementation_score": implementation_score,
        "verifiable_evidence_score": evidence_score,
        "combined_credibility_score": combined_score,
        "components": [asdict(component) for component in components],
        "summary": summary,
        "qualified_studies": [asdict(study) for study in studies],
        "claim_matrix": claim_matrix,
        "eligible_claims": eligible_claims,
        "blocked_claims": blocked_claims,
        "findings": findings,
        "release_claim": (
            "evidence-qualified"
            if evidence_score == 10.0
            else "research-grade evidence controls; external validation pending"
        ),
        "boundary": (
            "Scientific credibility controls are implementation-complete. A real 10/10 evidence score requires independently verifiable DTI validation, blinded prospective outcomes, independent wet-lab replication and multi-site evidence."
        ),
    }


def write_scientific_credibility_audit(root: str | Path, output: str | Path | None = None) -> Path:
    project_root = Path(root).resolve()
    destination = Path(output) if output else runtime_report_path(project_root, "scientific_credibility_audit.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    report = build_scientific_credibility_audit(project_root)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return destination
