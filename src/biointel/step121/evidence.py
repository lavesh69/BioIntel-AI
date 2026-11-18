from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class EvidenceWorkspace:
    evidence: pd.DataFrame
    domain_summary: pd.DataFrame
    adjudication: pd.DataFrame
    conflict_queue: pd.DataFrame
    graph_nodes: pd.DataFrame
    graph_edges: pd.DataFrame
    release_gate: dict[str, Any]
    manifest: dict[str, Any]


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "evidenceid": "evidence_id",
        "record_id": "evidence_id",
        "domain_type": "domain",
        "entity": "subject_id",
        "subject": "subject_id",
        "endpoint": "claim",
        "result": "direction",
        "study_type": "study_design",
        "source_uri": "source",
        "reviewer": "reviewer_id",
        "decision": "review_decision",
        "review_comment": "review_notes",
        "source_release": "version",
    }
    renamed: dict[Any, str] = {}
    for column in frame.columns:
        normalized = str(column).strip().lower()
        renamed[column] = aliases.get(normalized, normalized.replace(" ", "_"))
    result = frame.rename(columns=renamed).copy()
    defaults: dict[str, Any] = {
        "evidence_id": "",
        "domain": "other",
        "subject_id": "",
        "claim": "",
        "direction": "unclear",
        "study_design": "unspecified",
        "source": "",
        "version": "unversioned",
        "organism": "",
        "assay": "",
        "sample_size": np.nan,
        "effect_size": np.nan,
        "p_value": np.nan,
        "confidence": "medium",
        "independent": False,
        "reviewer_id": "",
        "review_decision": "pending",
        "review_notes": "",
        "license": "unrecorded",
    }
    for column, default in defaults.items():
        if column not in result.columns:
            result[column] = default
    result["evidence_id"] = result["evidence_id"].astype(str).str.strip()
    missing = result["evidence_id"].eq("")
    result.loc[missing, "evidence_id"] = [f"EVID-{index + 1:06d}" for index in range(missing.sum())]
    for column in ("domain", "subject_id", "claim", "direction", "study_design", "source", "version", "confidence", "reviewer_id", "review_decision", "license"):
        result[column] = result[column].astype(str).str.strip()
    result["domain"] = result["domain"].str.lower()
    result["direction"] = result["direction"].str.lower()
    result["review_decision"] = result["review_decision"].str.lower()
    result["confidence"] = result["confidence"].str.lower()
    result["independent"] = result["independent"].astype(str).str.lower().isin({"true", "1", "yes", "y", "independent"})
    for column in ("sample_size", "effect_size", "p_value"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def _evidence_score(row: pd.Series) -> float:
    design = {
        "meta-analysis": 1.00,
        "systematic review": 0.95,
        "randomized controlled trial": 0.95,
        "prospective cohort": 0.82,
        "cohort": 0.75,
        "case-control": 0.65,
        "clinical assay": 0.75,
        "wet-lab validation": 0.72,
        "in vivo": 0.62,
        "in vitro": 0.50,
        "omics association": 0.48,
        "imaging study": 0.48,
        "computational": 0.30,
        "unspecified": 0.20,
    }
    confidence = {"high": 1.0, "medium": 0.75, "low": 0.45, "unclear": 0.35}
    score = design.get(str(row.get("study_design", "unspecified")).lower(), 0.35)
    score *= confidence.get(str(row.get("confidence", "medium")).lower(), 0.65)
    if bool(row.get("independent", False)):
        score *= 1.15
    if str(row.get("review_decision", "pending")).lower() in {"reject", "rejected"}:
        score = 0.0
    if str(row.get("review_decision", "pending")).lower() in {"accept", "accepted"}:
        score *= 1.05
    return round(float(min(score, 1.0)), 4)


def _adjudicate(group: pd.DataFrame) -> dict[str, Any]:
    decisions = group["review_decision"].replace("", "pending").value_counts()
    accepted = int(decisions.get("accepted", 0) + decisions.get("accept", 0))
    rejected = int(decisions.get("rejected", 0) + decisions.get("reject", 0))
    pending = int(len(group) - accepted - rejected)
    reviewers = int(group["reviewer_id"].replace("", pd.NA).dropna().nunique())
    conflict = accepted > 0 and rejected > 0
    if conflict:
        final = "conflict_requires_adjudicator"
    elif accepted >= 2 and reviewers >= 2:
        final = "accepted_by_independent_reviewers"
    elif rejected >= 2 and reviewers >= 2:
        final = "rejected_by_independent_reviewers"
    else:
        final = "pending_additional_review"
    return {
        "reviewers": reviewers,
        "accepted_votes": accepted,
        "rejected_votes": rejected,
        "pending_votes": pending,
        "review_conflict": conflict,
        "adjudication_status": final,
    }


def build_evidence_workspace(frame: pd.DataFrame) -> EvidenceWorkspace:
    evidence = _normalize(frame)
    evidence["evidence_score"] = evidence.apply(_evidence_score, axis=1)
    evidence["schema_complete"] = evidence[["domain", "subject_id", "claim", "source", "version"]].ne("").all(axis=1)
    evidence["license_recorded"] = ~evidence["license"].str.lower().isin({"", "unrecorded", "unknown", "none"})
    evidence["source_versioned"] = ~evidence["version"].str.lower().isin({"", "unversioned", "unknown", "none"})
    evidence["release_blocked"] = ~(
        evidence["schema_complete"]
        & evidence["license_recorded"]
        & evidence["source_versioned"]
        & evidence["review_decision"].isin({"accepted", "accept"})
    )

    domain_summary = (
        evidence.groupby("domain", dropna=False)
        .agg(
            records=("evidence_id", "count"),
            subjects=("subject_id", "nunique"),
            independent_records=("independent", "sum"),
            accepted_records=("review_decision", lambda values: int(pd.Series(values).isin(["accepted", "accept"]).sum())),
            mean_evidence_score=("evidence_score", "mean"),
            blocked_records=("release_blocked", "sum"),
        )
        .reset_index()
    )

    adjudication_rows: list[dict[str, Any]] = []
    conflict_rows: list[dict[str, Any]] = []
    for evidence_id, group in evidence.groupby("evidence_id"):
        result = _adjudicate(group)
        row = {
            "evidence_id": evidence_id,
            "domain": group.iloc[0]["domain"],
            "subject_id": group.iloc[0]["subject_id"],
            "claim": group.iloc[0]["claim"],
            **result,
        }
        adjudication_rows.append(row)
        directions = group["direction"].replace("", "unclear").unique()
        evidence_conflict = any(value in {"support", "supports", "positive"} for value in directions) and any(
            value in {"oppose", "opposes", "negative"} for value in directions
        )
        if result["review_conflict"] or evidence_conflict or bool(group["release_blocked"].any()):
            conflict_rows.append(
                {
                    **row,
                    "evidence_direction_conflict": evidence_conflict,
                    "blocked_rows": int(group["release_blocked"].sum()),
                    "queue_status": "requires_adjudication",
                }
            )
    adjudication = pd.DataFrame(adjudication_rows)
    conflict_queue = pd.DataFrame(conflict_rows)

    subject_nodes = evidence[["domain", "subject_id"]].drop_duplicates().copy()
    subject_nodes["node_id"] = subject_nodes["domain"] + ":" + subject_nodes["subject_id"]
    subject_nodes["node_type"] = "subject"
    subject_nodes["label"] = subject_nodes["subject_id"]
    evidence_nodes = evidence[["evidence_id", "claim"]].drop_duplicates().rename(columns={"evidence_id": "node_id", "claim": "label"})
    evidence_nodes["node_type"] = "evidence"
    graph_nodes = pd.concat(
        [subject_nodes[["node_id", "node_type", "label"]], evidence_nodes[["node_id", "node_type", "label"]]],
        ignore_index=True,
    )
    graph_edges = evidence[["domain", "subject_id", "evidence_id", "direction", "evidence_score", "review_decision"]].copy()
    graph_edges["source"] = graph_edges["domain"] + ":" + graph_edges["subject_id"]
    graph_edges = graph_edges.rename(columns={"evidence_id": "target", "direction": "relationship"})
    graph_edges = graph_edges[["source", "target", "relationship", "evidence_score", "review_decision"]]

    blockers: list[str] = []
    if (~evidence["schema_complete"]).any():
        blockers.append("One or more evidence records are missing required domain/subject/claim/source/version fields")
    if (~evidence["license_recorded"]).any():
        blockers.append("One or more evidence records have no recorded licence")
    if (~evidence["source_versioned"]).any():
        blockers.append("One or more evidence records have no source release/version")
    if not conflict_queue.empty:
        blockers.append("Evidence or reviewer conflicts are queued for adjudication")
    if not evidence["independent"].any():
        blockers.append("No independent evidence record is present")
    blockers.extend(
        [
            "Software review status does not replace independent scientific or clinical adjudication",
            "Release requires domain-specific validation criteria and traceable source documents",
        ]
    )
    digest = pd.util.hash_pandas_object(evidence.astype("string").fillna(""), index=True).values.tobytes()
    manifest = {
        "schema": "biointel.step121.cross_domain_evidence.v1",
        "rows": len(evidence),
        "unique_evidence_ids": int(evidence["evidence_id"].nunique()),
        "domains": sorted(evidence["domain"].unique().tolist()),
        "input_sha256": sha256(digest).hexdigest(),
        "accepted_rows": int(evidence["review_decision"].isin(["accepted", "accept"]).sum()),
        "independent_rows": int(evidence["independent"].sum()),
        "release_ready": False,
    }
    return EvidenceWorkspace(
        evidence=evidence,
        domain_summary=domain_summary,
        adjudication=adjudication,
        conflict_queue=conflict_queue,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        release_gate={
            "curation_workspace_ready": True,
            "scientific_release_ready": False,
            "blockers": blockers,
            "boundary": "Evidence registry and reviewer consensus support traceability; they do not create independent scientific validation.",
        },
        manifest=manifest,
    )
