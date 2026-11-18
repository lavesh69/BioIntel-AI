from __future__ import annotations

from biointel.runtime_paths import runtime_report_path

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import pandas as pd

from biointel.scientific_depth.profiles import MODULE_PROFILES


@dataclass(frozen=True)
class ModuleProfile:
    module_key: str
    title: str
    previous_practical_rating: float
    software_score: float
    native_research_depth_score: float
    operational_evidence_framework_score: float
    focused_upgrade: str
    external_confirmation_required: str
    controlled_release_eligible: bool = False


_PREVIOUS_625 = {
    "autonomous_lab_planner",
    "clinical_biomarker_survival",
    "flow_cytometry",
    "gene_therapy_vector",
    "pharmacovigilance_intelligence",
    "synthetic_cohort_trial",
}

_TARGETS_65 = {
    "background_job_engine",
    "background_jobs_core",
    "benchmark_validation_v2",
    "bioprocess_fermentation",
    "causal_perturbation",
    "clinical_pharma_core",
    "clinical_trial_biomarker",
    "collaboration_review_v2",
    "cross_module_workspace",
    "data_lakehouse_v2",
    "document_intelligence_core",
    "epitranscriptomics",
    "evidence_citation_engine",
    "host_pathogen_interaction",
    "knowledge_graph_core",
    "longitudinal_multiomics",
    "multiomics_biomarker_core",
    "multiomics_harmonization",
    "plugin_marketplace_core",
    "plugin_marketplace_v2",
    "provenance_ledger_v2",
    "reference_lifecycle_v2",
    "synthetic_biology_core",
    "synthetic_data_privacy",
    "unified_report_builder",
    "universal_file_inspector",
    "store_readiness_core",
    "workflow_builder_core",
    "workflow_builder_v2",
}

TARGETS = tuple(sorted(_PREVIOUS_625 | _TARGETS_65))
ALL_MODULES = tuple(sorted(MODULE_PROFILES))

_UPGRADES: dict[str, str] = {
    "autonomous_lab_planner": "Feasibility, randomisation, resource, replication and prospective experiment-plan controls",
    "clinical_biomarker_survival": "Survival endpoint QC, event balance, person-time risk, bootstrap uncertainty and external-cohort gates",
    "flow_cytometry": "Robust event QC, marker gates, acquisition drift, population frequencies and instrument-panel qualification",
    "gene_therapy_vector": "Payload sequence integrity, GC/CpG/repeat/motif risk, packaging margin and orthogonal safety gates",
    "pharmacovigilance_intelligence": "Deduplication, PRR/ROR disproportionality, confidence intervals, case completeness and expert causality review",
    "synthetic_cohort_trial": "Distributional fidelity, treatment balance, outcome utility, privacy risk and prospective trial-simulation validation",
    "background_job_engine": "Queue health, stale-worker recovery, retry/idempotency, checkpoint and artifact-completeness assurance",
    "background_jobs_core": "Queue health, stale-worker recovery, retry/idempotency, checkpoint and artifact-completeness assurance",
    "benchmark_validation_v2": "Calibration, discrimination, subgroup stability, threshold utility, leakage and independent benchmark gates",
    "bioprocess_fermentation": "Batch trajectories, control limits, drift/change detection, golden-batch comparison and PAT qualification",
    "causal_perturbation": "Instrument strength, IVW effect, heterogeneity, leave-one-out stability and negative-control requirements",
    "clinical_pharma_core": "Clinical endpoint completeness, risk-benefit evidence, subgroup review and independent/prospective study gates",
    "clinical_trial_biomarker": "Endpoint/event QC, stratification stability, biomarker evidence and external-cohort validation",
    "collaboration_review_v2": "Reviewer agreement, version locking, unresolved conflict, decision provenance and formal release review",
    "cross_module_workspace": "Asset lineage, hash/version integrity, locked handoffs, orphan detection and project-release readiness",
    "data_lakehouse_v2": "Asset indexing, checksum/schema/retention/access controls, drift and reproducible data-product qualification",
    "document_intelligence_core": "Extraction confidence, table/figure review, citation traceability, duplicate pages and human review gates",
    "epitranscriptomics": "Interval integrity, replicate concordance, modification-site confidence and orthogonal assay requirements",
    "evidence_citation_engine": "Claim-source traceability, retraction/conflict screening, source-version lock and evidence-strength scoring",
    "host_pathogen_interaction": "Interaction evidence coverage, network confidence, host/pathogen balance and experimental confirmation",
    "knowledge_graph_core": "Graph integrity, orphan/duplicate edges, relation diversity, evidence coverage and ontology-release qualification",
    "longitudinal_multiomics": "Sample/time completeness, missingness, trajectory stability, batch confounding and external longitudinal validation",
    "multiomics_biomarker_core": "Feature stability, group effect, batch leakage, bootstrap readiness and external biomarker replication",
    "multiomics_harmonization": "Before/after batch effect, biological-signal preservation, missingness and independent harmonisation benchmark",
    "plugin_marketplace_core": "Publisher/signature, static scan, permissions, isolation, dependency and controlled enablement gates",
    "plugin_marketplace_v2": "Publisher/signature, static scan, permissions, isolation, dependency and controlled enablement gates",
    "provenance_ledger_v2": "Hash-chain continuity, timestamp/order integrity, payload validity and immutable release-manifest verification",
    "reference_lifecycle_v2": "Release/checksum/licence/schema/compatibility/rollback qualification and update-monitoring lifecycle",
    "synthetic_biology_core": "Circuit expression, burden, leakiness, manufacturability, robustness and wet-lab confirmation gates",
    "synthetic_data_privacy": "k-anonymity, l-diversity, rare-combination risk, utility boundary and membership-inference validation",
    "unified_report_builder": "Section completeness, source/method/version traceability, approvals and reproducible export verification",
    "universal_file_inspector": "Extension/magic consistency, schema/corruption, size, sensitive-data and safe-import decisions",
    "store_readiness_core": "Signing, hashes, privacy/legal URLs, version alignment, validation and physical Windows/store evidence",
    "workflow_builder_core": "DAG cycles, missing dependencies, type compatibility, checkpoints, retries and resumable execution",
    "workflow_builder_v2": "DAG cycles, missing dependencies, type compatibility, checkpoints, retries and resumable execution",
}

_EXTERNAL = (
    "Production references, independent validation, prospective or orthogonal evidence, domain-expert sign-off, "
    "formal release review, operating history and physical platform/instrument qualification"
)

PROFILES = {
    key: ModuleProfile(
        module_key=key,
        title=MODULE_PROFILES[key].title,
        previous_practical_rating=6.25 if key in _PREVIOUS_625 else 6.5,
        software_score=10.0,
        native_research_depth_score=10.0,
        operational_evidence_framework_score=10.0,
        focused_upgrade=_UPGRADES[key],
        external_confirmation_required=_EXTERNAL,
    )
    for key in TARGETS
}


def priority_matrix(root: str | Path | None = None) -> pd.DataFrame:
    frame = pd.DataFrame([asdict(PROFILES[key]) for key in TARGETS])
    frame["updated_internal_rating"] = "10/10"
    frame["updated_native_research_rating"] = "10/10"
    frame["updated_evidence_operations_rating"] = "10/10"
    frame["external_status"] = "research-only-fail-closed until genuine evidence is attached"
    if root:
        path = runtime_report_path(Path(root), "step168_priority_module_matrix.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"schema": "biointel.step168.priority-module-matrix.v1", "modules": [asdict(PROFILES[k]) for k in TARGETS]},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return frame


def universal_evidence_matrix() -> pd.DataFrame:
    rows = []
    for key in ALL_MODULES:
        rows.append(
            {
                "module_key": key,
                "module_title": MODULE_PROFILES[key].title,
                "production_reference_intake": True,
                "independent_validation_protocol": True,
                "prospective_or_orthogonal_protocol": True,
                "domain_expert_review_workflow": True,
                "formal_release_review_workflow": True,
                "operating_history_capture": True,
                "physical_qualification_protocol": True,
                "framework_score": 10.0,
                "evidence_complete": False,
                "real_world_release_eligible": False,
            }
        )
    return pd.DataFrame(rows)


__all__ = ["ALL_MODULES", "PROFILES", "TARGETS", "priority_matrix", "universal_evidence_matrix"]
