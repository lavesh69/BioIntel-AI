from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

import pandas as pd

_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_PMID_RE = re.compile(r"\b\d{5,9}\b")


@dataclass(frozen=True)
class CitationWorkspace:
    citations: pd.DataFrame
    claim_summary: pd.DataFrame
    graph_nodes: pd.DataFrame
    graph_edges: pd.DataFrame
    conflict_review: pd.DataFrame
    release_gate: dict[str, Any]
    manifest: dict[str, Any]


def normalize_doi(value: Any) -> str:
    text = str(value or "").strip()
    match = _DOI_RE.search(text)
    return match.group(0).rstrip(".,;)").lower() if match else ""


def normalize_pmid(value: Any) -> str:
    text = str(value or "").strip()
    match = _PMID_RE.search(text)
    return match.group(0) if match else ""


def _canonical_columns(frame: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "claim": "claim_text",
        "claimid": "claim_id",
        "claim id": "claim_id",
        "doi_url": "doi",
        "pubmed_id": "pmid",
        "pmid_id": "pmid",
        "journal_name": "journal",
        "publication_year": "year",
        "direction": "evidence_direction",
        "study_type": "study_design",
        "is_retracted": "retracted",
        "is_corrected": "corrected",
        "source_version": "version",
    }
    renamed: dict[Any, str] = {}
    for column in frame.columns:
        normalized = str(column).strip().lower()
        renamed[column] = aliases.get(normalized, normalized.replace(" ", "_"))
    result = frame.rename(columns=renamed).copy()
    defaults: dict[str, Any] = {
        "claim_id": "",
        "claim_text": "",
        "doi": "",
        "pmid": "",
        "title": "",
        "authors": "",
        "journal": "",
        "year": "",
        "study_design": "unspecified",
        "evidence_direction": "unclear",
        "effect_size": "",
        "confidence": "medium",
        "version": "unversioned",
        "retracted": False,
        "corrected": False,
        "provider": "manual",
        "url": "",
        "notes": "",
    }
    for column, default in defaults.items():
        if column not in result.columns:
            result[column] = default
    result["doi"] = result["doi"].map(normalize_doi)
    result["pmid"] = result["pmid"].map(normalize_pmid)
    result["claim_id"] = result["claim_id"].astype(str).str.strip()
    missing_claim_id = result["claim_id"].eq("")
    result.loc[missing_claim_id, "claim_id"] = [f"CLAIM-{index + 1:04d}" for index in range(missing_claim_id.sum())]
    result["claim_text"] = result["claim_text"].astype(str).str.strip()
    result["title"] = result["title"].astype(str).str.strip()
    result["study_design"] = result["study_design"].astype(str).str.strip().str.lower()
    result["evidence_direction"] = result["evidence_direction"].astype(str).str.strip().str.lower()
    result["confidence"] = result["confidence"].astype(str).str.strip().str.lower()
    result["retracted"] = result["retracted"].astype(str).str.lower().isin({"true", "1", "yes", "y", "retracted"})
    result["corrected"] = result["corrected"].astype(str).str.lower().isin({"true", "1", "yes", "y", "corrected"})
    result["year"] = pd.to_numeric(result["year"], errors="coerce").astype("Int64")
    return result


def _record_key(row: pd.Series) -> str:
    if row.get("doi"):
        return f"doi:{row['doi']}"
    if row.get("pmid"):
        return f"pmid:{row['pmid']}"
    title = re.sub(r"\W+", " ", str(row.get("title", "")).lower()).strip()
    return f"title:{title}|year:{row.get('year', '')}"


def _strength(row: pd.Series) -> float:
    design_weights = {
        "systematic review": 1.00,
        "meta-analysis": 1.00,
        "randomized controlled trial": 0.95,
        "rct": 0.95,
        "prospective cohort": 0.80,
        "cohort": 0.75,
        "case-control": 0.65,
        "cross-sectional": 0.55,
        "in vivo": 0.60,
        "in vitro": 0.45,
        "computational": 0.30,
        "preprint": 0.25,
        "unspecified": 0.20,
    }
    confidence_weights = {"high": 1.0, "medium": 0.75, "low": 0.45, "unclear": 0.35}
    score = design_weights.get(str(row.get("study_design", "unspecified")).lower(), 0.35)
    score *= confidence_weights.get(str(row.get("confidence", "medium")).lower(), 0.65)
    if bool(row.get("corrected", False)):
        score *= 0.8
    if bool(row.get("retracted", False)):
        score = 0.0
    return round(float(score), 4)


def _provider_status(row: pd.Series) -> str:
    if row.get("doi"):
        return "crossref_or_publisher_resolution_available"
    if row.get("pmid"):
        return "pubmed_resolution_available"
    return "identifier_missing_manual_resolution_required"


def build_citation_workspace(frame: pd.DataFrame) -> CitationWorkspace:
    citations = _canonical_columns(frame)
    citations["record_key"] = citations.apply(_record_key, axis=1)
    citations["duplicate_count"] = citations.groupby("record_key")["record_key"].transform("size")
    citations["citation_id"] = [f"CIT-{index + 1:05d}" for index in range(len(citations))]
    citations["evidence_strength"] = citations.apply(_strength, axis=1)
    citations["provider_resolution_status"] = citations.apply(_provider_status, axis=1)
    citations["claim_exactness_status"] = citations.apply(
        lambda row: "claim_text_present" if str(row["claim_text"]).strip() else "claim_text_missing",
        axis=1,
    )
    citations["retraction_status"] = citations.apply(
        lambda row: "retracted" if row["retracted"] else "corrected" if row["corrected"] else "not_flagged_in_imported_metadata",
        axis=1,
    )

    deduplicated = citations.sort_values(["record_key", "evidence_strength"], ascending=[True, False]).drop_duplicates("record_key", keep="first")
    summary_rows: list[dict[str, Any]] = []
    conflict_rows: list[dict[str, Any]] = []
    for claim_id, group in citations.groupby("claim_id"):
        directions = group["evidence_direction"].replace("", "unclear").value_counts().to_dict()
        support = int(directions.get("support", 0) + directions.get("supports", 0) + directions.get("positive", 0))
        oppose = int(directions.get("oppose", 0) + directions.get("opposes", 0) + directions.get("negative", 0))
        neutral = int(directions.get("null", 0) + directions.get("neutral", 0) + directions.get("unclear", 0))
        conflict = support > 0 and oppose > 0
        weighted_support = float(group.loc[group["evidence_direction"].isin(["support", "supports", "positive"]), "evidence_strength"].sum())
        weighted_oppose = float(group.loc[group["evidence_direction"].isin(["oppose", "opposes", "negative"]), "evidence_strength"].sum())
        summary_rows.append(
            {
                "claim_id": claim_id,
                "claim_text": group["claim_text"].dropna().astype(str).replace("", pd.NA).dropna().iloc[0] if not group["claim_text"].replace("", pd.NA).dropna().empty else "",
                "citation_records": len(group),
                "unique_sources": group["record_key"].nunique(),
                "supporting": support,
                "opposing": oppose,
                "neutral_or_unclear": neutral,
                "weighted_support": weighted_support,
                "weighted_oppose": weighted_oppose,
                "conflict_present": conflict,
                "retracted_records": int(group["retracted"].sum()),
                "unresolved_identifiers": int((group["provider_resolution_status"] == "identifier_missing_manual_resolution_required").sum()),
            }
        )
        if conflict or group["retracted"].any() or group["claim_text"].eq("").any():
            conflict_rows.append(
                {
                    "claim_id": claim_id,
                    "conflict_present": conflict,
                    "supporting": support,
                    "opposing": oppose,
                    "retracted_records": int(group["retracted"].sum()),
                    "missing_claim_text": int(group["claim_text"].eq("").sum()),
                    "review_status": "blocked_pending_adjudication",
                }
            )
    claim_summary = pd.DataFrame(summary_rows)
    conflict_review = pd.DataFrame(conflict_rows)

    claim_nodes = claim_summary[["claim_id", "claim_text"]].copy() if not claim_summary.empty else pd.DataFrame(columns=["claim_id", "claim_text"])
    claim_nodes = claim_nodes.rename(columns={"claim_id": "node_id", "claim_text": "label"})
    claim_nodes["node_type"] = "claim"
    citation_nodes = deduplicated[["record_key", "title"]].copy()
    citation_nodes = citation_nodes.rename(columns={"record_key": "node_id", "title": "label"})
    citation_nodes["node_type"] = "citation"
    graph_nodes = pd.concat([claim_nodes, citation_nodes], ignore_index=True)
    graph_edges = citations[["claim_id", "record_key", "evidence_direction", "evidence_strength", "citation_id"]].rename(
        columns={"claim_id": "source", "record_key": "target", "evidence_direction": "relationship"}
    )

    blockers: list[str] = []
    if citations["claim_text"].eq("").any():
        blockers.append("One or more citations are not linked to an explicit claim text")
    if citations["retracted"].any():
        blockers.append("Retracted records are present")
    if not conflict_review.empty and conflict_review["conflict_present"].any():
        blockers.append("Conflicting evidence requires adjudication")
    if (citations["provider_resolution_status"] == "identifier_missing_manual_resolution_required").any():
        blockers.append("Some citations lack DOI/PMID identifiers")
    blockers.extend(
        [
            "Imported metadata must be verified against the authoritative provider before publication",
            "Citation presence does not prove that a source supports the exact claim",
        ]
    )
    digest = pd.util.hash_pandas_object(citations.astype("string").fillna(""), index=True).values.tobytes()
    manifest = {
        "schema": "biointel.step121.citation_workspace.v1",
        "records": len(citations),
        "unique_sources": citations["record_key"].nunique(),
        "claims": citations["claim_id"].nunique(),
        "duplicates": int((citations["duplicate_count"] > 1).sum()),
        "input_sha256": sha256(digest).hexdigest(),
        "provider_policy": "offline metadata import with explicit optional provider resolution",
        "publication_release_ready": False,
    }
    return CitationWorkspace(
        citations=citations,
        claim_summary=claim_summary,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        conflict_review=conflict_review,
        release_gate={
            "citation_package_ready": True,
            "publication_release_ready": False,
            "blockers": blockers,
            "boundary": "Citations must be verified, versioned and matched to the exact claim; imported metadata alone is insufficient.",
        },
        manifest=manifest,
    )


def export_bibtex(citations: pd.DataFrame) -> str:
    records: list[str] = []
    for index, row in citations.iterrows():
        key = re.sub(r"\W+", "", str(row.get("citation_id", f"citation{index + 1}"))) or f"citation{index + 1}"
        fields = {
            "title": str(row.get("title", "")),
            "author": str(row.get("authors", "")),
            "journal": str(row.get("journal", "")),
            "year": str(row.get("year", "")) if pd.notna(row.get("year")) else "",
            "doi": str(row.get("doi", "")),
            "pmid": str(row.get("pmid", "")),
            "url": str(row.get("url", "")),
        }
        body = ",\n".join(f"  {name} = {{{value.replace('{', '').replace('}', '')}}}" for name, value in fields.items() if value)
        records.append(f"@article{{{key},\n{body}\n}}")
    return "\n\n".join(records) + ("\n" if records else "")


def export_ris(citations: pd.DataFrame) -> str:
    lines: list[str] = []
    for _, row in citations.iterrows():
        lines.append("TY  - JOUR")
        if row.get("title"):
            lines.append(f"TI  - {row['title']}")
        for author in [part.strip() for part in str(row.get("authors", "")).split(";") if part.strip()]:
            lines.append(f"AU  - {author}")
        if row.get("journal"):
            lines.append(f"JO  - {row['journal']}")
        if pd.notna(row.get("year")):
            lines.append(f"PY  - {row['year']}")
        if row.get("doi"):
            lines.append(f"DO  - {row['doi']}")
        if row.get("pmid"):
            lines.append(f"AN  - PMID:{row['pmid']}")
        if row.get("url"):
            lines.append(f"UR  - {row['url']}")
        lines.append("ER  - ")
        lines.append("")
    return "\n".join(lines)
