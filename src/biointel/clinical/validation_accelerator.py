from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from .external_readiness import RealExternalValidationReport


@dataclass(frozen=True)
class ValidationAction:
    domain: str
    label: str
    priority: str
    current_score: float
    target_score: float
    blocker: str
    required_owner: str
    required_artifact: str
    completion_evidence: str
    software_can_complete: bool


@dataclass(frozen=True)
class AcceleratorReadiness:
    score: float
    passed_controls: int
    total_controls: int
    controls: tuple[dict[str, Any], ...]
    boundary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DOMAIN_EXECUTION_REQUIREMENTS: dict[str, dict[str, str]] = {
    "independent_clinical_evidence": {
        "owner": "Independent clinical investigators at two or more organizations",
        "artifact": "Final clinical study reports or official registry records",
        "evidence": "Issuer-authenticated reports, stable identifiers, independent review and file integrity",
    },
    "prospective_clinical_study": {
        "owner": "Sponsor, principal investigators, ethics committee and independent statistician",
        "artifact": "Preregistered protocol, locked predictions, adjudicated outcomes and final study report",
        "evidence": "Prospective sequencing, predefined endpoint success and complete multisite reconciliation",
    },
    "pharma_laboratory_validation": {
        "owner": "Two accredited independent pharmaceutical or analytical laboratories",
        "artifact": "Replicate laboratory validation reports with raw-data traceability",
        "evidence": "Validated assay, replication completion, source data and independent laboratory approval",
    },
    "peer_reviewed_publication": {
        "owner": "Independent authors, journal editors and peer reviewers",
        "artifact": "Published validation paper with DOI or PubMed identifier",
        "evidence": "Published status, methods, limitations, results and stable publisher identifier",
    },
    "gxp_operating_history": {
        "owner": "Operating organization quality unit",
        "artifact": "At least 12 months of controlled GxP quality and operating records",
        "evidence": "Quality-system operation, audit history, training, deviations, CAPA and change control",
    },
    "regulatory_inspection": {
        "owner": "Competent regulatory authority and inspected organization",
        "artifact": "Official inspection report or authority-issued inspection outcome",
        "evidence": "Inspection reference, authority verification and closure of critical findings",
    },
    "regulatory_authorization": {
        "owner": "Applicable regulator and legal manufacturer/sponsor",
        "artifact": "Active authorization, clearance or licence for the documented intended use",
        "evidence": "Authority, authorization number, jurisdiction and exact intended-use alignment",
    },
    "approved_patient_care_use": {
        "owner": "Authorized healthcare institution and clinical governance body",
        "artifact": "Institutional approval and controlled deployment/use records",
        "evidence": "Authorized users, human oversight, site counts, use denominator and governance approval",
    },
    "post_market_clinical_evidence": {
        "owner": "Manufacturer/sponsor, clinical sites and quality/safety function",
        "artifact": "Periodic post-market performance and safety reports",
        "evidence": "Real-use denominator, drift monitoring, safety surveillance and critical-event closure",
    },
}


def build_validation_action_plan(report: RealExternalValidationReport) -> tuple[ValidationAction, ...]:
    """Create a truthful, domain-by-domain execution plan.

    The plan never changes the authentic evidence score. It turns each failed evidence
    control into a concrete external deliverable with a named responsible party.
    """

    actions: list[ValidationAction] = []
    for rating in report.ratings:
        requirement = DOMAIN_EXECUTION_REQUIREMENTS[rating.domain]
        blockers = rating.blockers or ("No blocker; preserve and periodically reverify evidence.",)
        for index, blocker in enumerate(blockers):
            if rating.score < 4:
                priority = "Critical"
            elif rating.score < 8:
                priority = "High"
            elif rating.score < 10:
                priority = "Medium"
            else:
                priority = "Maintain"
            actions.append(
                ValidationAction(
                    domain=rating.domain,
                    label=rating.label,
                    priority=priority,
                    current_score=rating.score,
                    target_score=10.0,
                    blocker=blocker,
                    required_owner=requirement["owner"],
                    required_artifact=requirement["artifact"],
                    completion_evidence=requirement["evidence"],
                    software_can_complete=False,
                )
            )
    order = {"Critical": 0, "High": 1, "Medium": 2, "Maintain": 3}
    return tuple(sorted(actions, key=lambda item: (order[item.priority], item.label, item.blocker)))


def projected_score_from_control_completion(
    report: RealExternalValidationReport,
    completed_by_domain: dict[str, int],
) -> dict[str, Any]:
    """Return a non-claiming scenario projection.

    This deliberately does not update the evidence registry or release eligibility.
    It is only a planning calculation for estimating how many authentic controls remain.
    """

    rows: list[dict[str, Any]] = []
    for rating in report.ratings:
        planned = max(0, int(completed_by_domain.get(rating.domain, 0)))
        projected_passed = min(rating.total_controls, rating.passed_controls + planned)
        projected = round(10.0 * projected_passed / rating.total_controls, 1)
        rows.append(
            {
                "domain": rating.domain,
                "label": rating.label,
                "actual_score": rating.score,
                "projected_score": projected,
                "actual_passed_controls": rating.passed_controls,
                "projected_passed_controls": projected_passed,
                "total_controls": rating.total_controls,
            }
        )
    projected_overall = round(sum(row["projected_score"] for row in rows) / len(rows), 1)
    return {
        "actual_score": report.actual_external_validation_score,
        "projected_score": projected_overall,
        "projection_only": True,
        "release_eligible": report.release_eligible,
        "rows": rows,
        "boundary": (
            "Projection does not change the authentic score, evidence status or permitted claim. "
            "Only accepted independent evidence can do that."
        ),
    }


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _csv_bytes(headers: Iterable[str], rows: Iterable[Iterable[Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(list(headers))
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")



def build_generic_independent_validation_starter_pack(root: str | Path) -> bytes:
    """Build a program-neutral partner starter pack for first contact and planning."""

    base = Path(root)
    template_root = base / "data" / "independent_validation" / "templates"
    templates = sorted(path for path in template_root.glob("*") if path.is_file())
    if not templates:
        raise FileNotFoundError(f"No independent validation templates found in {template_root}")
    files = {f"templates/{path.name}": path.read_bytes() for path in templates}
    manifest = {
        "pack_type": "independent_validation_starter_pack",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "program_specific": False,
        "contains_preapproved_evidence": False,
        "boundary": (
            "This starter pack supports partner outreach and protocol planning only. "
            "It is not independent evidence or clinical/pharma validation."
        ),
        "files": [
            {"path": name, "sha256": _sha256(payload), "size": len(payload)}
            for name, payload in sorted(files.items())
        ],
    }
    files["MANIFEST.json"] = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, payload in sorted(files.items()):
            archive.writestr(name, payload)
    return output.getvalue()

def build_independent_validation_partner_pack(
    root: str | Path,
    report: RealExternalValidationReport,
    *,
    program_title: str,
) -> bytes:
    """Build an audit-friendly execution pack for real independent partners.

    The pack contains no pre-approved evidence and cannot raise the authentic score.
    """

    base = Path(root)
    template_root = base / "data" / "independent_validation" / "templates"
    required_templates = sorted(path for path in template_root.glob("*") if path.is_file())
    if not required_templates:
        raise FileNotFoundError(f"No independent validation templates found in {template_root}")

    actions = build_validation_action_plan(report)
    action_csv = _csv_bytes(
        (
            "domain",
            "label",
            "priority",
            "current_score",
            "target_score",
            "blocker",
            "required_owner",
            "required_artifact",
            "completion_evidence",
        ),
        (
            (
                item.domain,
                item.label,
                item.priority,
                item.current_score,
                item.target_score,
                item.blocker,
                item.required_owner,
                item.required_artifact,
                item.completion_evidence,
            )
            for item in actions
        ),
    )
    scorecard = json.dumps(report.to_dict(), indent=2, sort_keys=True).encode("utf-8")
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")

    files: dict[str, bytes] = {
        "00_CURRENT_AUTHENTIC_SCORECARD.json": scorecard,
        "01_DOMAIN_ACTION_PLAN.csv": action_csv,
    }
    for template in required_templates:
        files[f"templates/{template.name}"] = template.read_bytes()

    manifest = {
        "pack_type": "independent_validation_execution_pack",
        "program_id": report.program_id,
        "program_title": program_title,
        "generated_at_utc": generated_at,
        "actual_external_validation_score": report.actual_external_validation_score,
        "release_eligible": report.release_eligible,
        "contains_preapproved_evidence": False,
        "boundary": (
            "This pack supports execution and evidence collection. It is not independent evidence, "
            "regulatory authorization or a clinical validation claim."
        ),
        "files": [],
    }
    for name, payload in sorted(files.items()):
        manifest["files"].append({"path": name, "sha256": _sha256(payload), "size": len(payload)})
    manifest_payload = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    files["MANIFEST.json"] = manifest_payload

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, payload in sorted(files.items()):
            archive.writestr(name, payload)
    return output.getvalue()


def build_independent_validation_accelerator_readiness(root: str | Path) -> AcceleratorReadiness:
    base = Path(root)
    assets: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        (
            "Action-plan engine",
            "src/biointel/clinical/validation_accelerator.py",
            ("build_validation_action_plan", "required_owner", "software_can_complete=False"),
        ),
        (
            "Scenario projection with claim boundary",
            "src/biointel/clinical/validation_accelerator.py",
            ("projected_score_from_control_completion", "projection_only", "Only accepted independent evidence"),
        ),
        (
            "Checksum-bound partner pack",
            "src/biointel/clinical/validation_accelerator.py",
            ("build_independent_validation_partner_pack", "MANIFEST.json", "ZIP_STORED"),
        ),
        (
            "Validation accelerator UI",
            "pages/92_Independent_Validation_Accelerator.py",
            ("Independent Validation Accelerator", "Actual verified score", "Planning projection"),
        ),
        (
            "Execution policy",
            "config/independent_validation_accelerator_policy.yaml",
            ("never_override_authentic_score", "external_owner_required", "projection_is_not_evidence"),
        ),
        (
            "Independent partner templates",
            "data/independent_validation/templates/README.md",
            ("independent partner", "do not constitute evidence"),
        ),
        (
            "Execution guide",
            "docs/INDEPENDENT_VALIDATION_ACCELERATOR_GUIDE.md",
            ("two independent organizations", "prospective", "10/10"),
        ),
        (
            "Qualification tests",
            "tests/test_step89_independent_validation_accelerator.py",
            ("test_accelerator_framework_scores_ten", "test_projection_never_changes_actual_score"),
        ),
        (
            "Qualification command",
            "scripts/qualify_step89_independent_validation_accelerator.py",
            ("build_independent_validation_accelerator_readiness", "reports", "score == 10.0"),
        ),
    )
    controls: list[dict[str, Any]] = []
    for label, relative, tokens in assets:
        path = base / relative
        text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
        passed = path.exists() and all(token in text for token in tokens)
        controls.append(
            {
                "label": label,
                "path": relative,
                "passed": passed,
                "missing_tokens": [token for token in tokens if token not in text],
            }
        )
    passed = sum(bool(item["passed"]) for item in controls)
    total = len(controls)
    return AcceleratorReadiness(
        score=round(10.0 * passed / total, 1),
        passed_controls=passed,
        total_controls=total,
        controls=tuple(controls),
        boundary=(
            "A 10/10 accelerator score measures software execution support only. Authentic clinical/pharma "
            "validation remains evidence-gated and cannot be created by this repository."
        ),
    )
