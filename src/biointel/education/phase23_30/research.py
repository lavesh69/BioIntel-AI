from __future__ import annotations

import re
from typing import Any

from ..platform import Conflict, Denied, EducationError, ident, now
from .base import Phase30Base, decode_json, encode_json, normalized_key

ASSET_TYPES = {
    "evidence_summary",
    "lecture_outline",
    "classroom_discussion",
    "quiz",
    "assignment",
    "presentation",
    "scientific_poster",
    "concept_map",
    "shiro_knowledge_collection",
    "virtual_lab_activity",
    "comparison_table",
    "evidence_synthesis",
    "course_unit",
    "science_pulse_briefing",
}
ASSET_REVIEW_STATES = {
    "draft",
    "ai_generated",
    "evidence_verification",
    "faculty_review",
    "approved",
    "published",
    "needs_revision",
    "archived",
}


class ResearchMixin(Phase30Base):
    def ingest_research_paper(
        self,
        actor: str,
        institution_id: str,
        *,
        title: str,
        doi: str = "",
        pmid: str = "",
        pmcid: str = "",
        authors: list[str] | None = None,
        journal: str = "",
        published_on: str = "",
        abstract: str = "",
        study_type: str = "",
        population_sample: str = "",
        methods: str = "",
        findings: str = "",
        limitations: str = "",
        conflicts: str = "",
        funding: str = "",
        retraction_state: str = "unknown",
        correction_state: str = "unknown",
        evidence_confidence: str = "unrated",
        source_metadata: dict[str, Any] | None = None,
        uploaded_pdf_path: str = "",
        upload_rights_confirmed: bool = False,
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "staff")
        if not title.strip():
            raise EducationError("Research paper title is required.")
        canonical_doi = doi.strip().casefold().removeprefix("https://doi.org/")
        if canonical_doi and not re.fullmatch(r"10\.\d{4,9}/\S+", canonical_doi):
            raise EducationError("DOI format is invalid.")
        canonical_pmid = re.sub(r"\D", "", pmid)
        canonical_pmcid = pmcid.strip().upper()
        if canonical_pmcid and not re.fullmatch(r"PMC\d+", canonical_pmcid):
            raise EducationError("PMCID format is invalid.")
        existing = None
        for column, value in (
            ("doi", canonical_doi),
            ("pmid", canonical_pmid),
            ("pmcid", canonical_pmcid),
        ):
            if value:
                existing = self._one(
                    f"""SELECT * FROM education_p30_research_papers
                    WHERE institution_id=? AND {column}=?""",
                    (institution_id, value),
                )
                if existing:
                    return existing
        managed_pdf = ""
        pdf_sha = ""
        paper_id = ident("paper")
        if uploaded_pdf_path:
            if not upload_rights_confirmed:
                raise Denied("User confirmation of PDF access rights is required.")
            destination = self._safe_storage_path(
                institution_id,
                "research",
                paper_id,
                "source.pdf",
            )
            copied = self._copy_managed_file(
                uploaded_pdf_path,
                destination,
                maximum_bytes=100 * 1024 * 1024,
                allowed_suffixes={".pdf"},
            )
            managed_pdf = str(copied["path"])
            pdf_sha = str(copied["sha256"])
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_research_papers
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    paper_id,
                    institution_id,
                    canonical_doi,
                    canonical_pmid,
                    canonical_pmcid,
                    title.strip(),
                    encode_json(authors or []),
                    journal,
                    published_on,
                    abstract,
                    study_type,
                    population_sample,
                    methods,
                    findings,
                    limitations,
                    conflicts,
                    funding,
                    retraction_state,
                    correction_state,
                    evidence_confidence,
                    encode_json(source_metadata or {}),
                    managed_pdf,
                    pdf_sha,
                    "unverified",
                    actor,
                    timestamp,
                    timestamp,
                ),
            )
        self._audit(
            actor,
            institution_id,
            "research_paper_ingested",
            "research_paper",
            paper_id,
            {
                "doi": canonical_doi,
                "pmid": canonical_pmid,
                "pmcid": canonical_pmcid,
                "uploaded_pdf": bool(managed_pdf),
            },
        )
        return self._tenant_row(
            "education_p30_research_papers",
            paper_id,
            institution_id,
        )

    def add_paper_claim(
        self,
        actor: str,
        paper_id: str,
        *,
        claim: str,
        evidence_excerpt: str = "",
        locator: str = "",
        confidence: float = 0,
    ) -> dict[str, Any]:
        paper = self._tenant_row("education_p30_research_papers", paper_id)
        institution_id = str(paper["institution_id"])
        self._require(actor, institution_id, "staff")
        if not claim.strip():
            raise EducationError("Paper claim is required.")
        if confidence < 0 or confidence > 1:
            raise EducationError("Claim confidence must be between 0 and 1.")
        claim_id = ident("paperclaim")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_paper_claims
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    claim_id,
                    paper_id,
                    claim.strip(),
                    evidence_excerpt,
                    locator,
                    float(confidence),
                    "unverified",
                    "",
                    now(),
                ),
            )
        return self._one(
            "SELECT * FROM education_p30_paper_claims WHERE id=?",
            (claim_id,),
        ) or {}

    def verify_paper(
        self,
        actor: str,
        paper_id: str,
        *,
        verification_state: str,
        retraction_state: str | None = None,
        correction_state: str | None = None,
    ) -> dict[str, Any]:
        paper = self._tenant_row("education_p30_research_papers", paper_id)
        institution_id = str(paper["institution_id"])
        self._require(actor, institution_id, "staff")
        if verification_state not in {
            "verified_metadata",
            "verified_full_text",
            "verification_failed",
            "unverified",
        }:
            raise EducationError("Unsupported paper verification state.")
        new_retraction = retraction_state or str(paper["retraction_state"])
        new_correction = correction_state or str(paper["correction_state"])
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_p30_research_papers
                SET verification_state=?,retraction_state=?,correction_state=?,updated_at=?
                WHERE id=?""",
                (
                    verification_state,
                    new_retraction,
                    new_correction,
                    timestamp,
                    paper_id,
                ),
            )
            if new_retraction not in {"none", "not_retracted", "unknown"}:
                candidates = db.execute(
                    """SELECT id,source_paper_ids_json FROM education_p30_research_assets
                    WHERE institution_id=? AND publishing_state IN ('published','draft')""",
                    (institution_id,),
                ).fetchall()
                for candidate in candidates:
                    if paper_id in decode_json(candidate["source_paper_ids_json"], []):
                        db.execute(
                            """UPDATE education_p30_research_assets SET
                            review_state='needs_revision',publishing_state='needs_revision',
                            updated_at=? WHERE id=?""",
                            (timestamp, candidate["id"]),
                        )
        self._audit(
            actor,
            institution_id,
            "research_paper_verified",
            "research_paper",
            paper_id,
            {
                "verification_state": verification_state,
                "retraction_state": new_retraction,
            },
        )
        return self._tenant_row(
            "education_p30_research_papers",
            paper_id,
            institution_id,
        )

    def transform_research_asset(
        self,
        actor: str,
        institution_id: str,
        *,
        asset_type: str,
        title: str,
        paper_ids: list[str],
        claim_ids: list[str] | None = None,
        content: dict[str, Any] | None = None,
        generation_provider: str = "local_deterministic",
        generation_model: str = "biointel-template-1",
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "staff")
        kind = normalized_key(asset_type)
        if kind not in ASSET_TYPES:
            raise EducationError("Unsupported research-to-education asset type.")
        if not paper_ids:
            raise EducationError("At least one source paper is required.")
        papers = [
            self._tenant_row(
                "education_p30_research_papers",
                paper_id,
                institution_id,
            )
            for paper_id in dict.fromkeys(paper_ids)
        ]
        claims: list[dict[str, Any]] = []
        for claim_id in dict.fromkeys(claim_ids or []):
            claim = self._one(
                """SELECT c.*,p.institution_id FROM education_p30_paper_claims c
                JOIN education_p30_research_papers p ON p.id=c.paper_id
                WHERE c.id=?""",
                (claim_id,),
            )
            if not claim or claim["institution_id"] != institution_id:
                raise Denied("Claim source must belong to the same institution.")
            claims.append(claim)
        citations = [
            {
                "paper_id": paper["id"],
                "doi": paper["doi"],
                "pmid": paper["pmid"],
                "pmcid": paper["pmcid"],
                "title": paper["title"],
                "verification_state": paper["verification_state"],
                "retraction_state": paper["retraction_state"],
            }
            for paper in papers
        ]
        generated_content = content or {
            "title": title,
            "asset_type": kind,
            "sections": [
                {
                    "heading": "Evidence sources",
                    "items": [
                        {
                            "paper_id": paper["id"],
                            "title": paper["title"],
                            "finding": paper["findings"],
                            "limitations": paper["limitations"],
                        }
                        for paper in papers
                    ],
                }
            ],
            "claim_ids": [claim["id"] for claim in claims],
            "publication_blocked_until_human_review": True,
        }
        asset_id = ident("researchasset")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_research_assets
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    asset_id,
                    institution_id,
                    kind,
                    title.strip(),
                    encode_json([paper["id"] for paper in papers]),
                    encode_json([claim["id"] for claim in claims]),
                    encode_json(generated_content),
                    encode_json(
                        {
                            "provider": generation_provider,
                            "model": generation_model,
                            "generated_by": actor,
                            "generated_at": timestamp,
                            "deterministic": generation_provider == "local_deterministic",
                        }
                    ),
                    encode_json(citations),
                    "unverified",
                    "ai_generated",
                    "draft",
                    1,
                    actor,
                    "",
                    None,
                    timestamp,
                    timestamp,
                ),
            )
        self._audit(
            actor,
            institution_id,
            "research_asset_generated",
            "research_asset",
            asset_id,
            {"asset_type": kind, "paper_count": len(papers)},
        )
        return self._tenant_row(
            "education_p30_research_assets",
            asset_id,
            institution_id,
        )

    def review_research_asset(
        self,
        actor: str,
        asset_id: str,
        *,
        decision: str,
        comments: str = "",
        evidence_check: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        asset = self._tenant_row("education_p30_research_assets", asset_id)
        institution_id = str(asset["institution_id"])
        self._require(actor, institution_id, "staff")
        if decision not in {
            "evidence_verified",
            "faculty_approved",
            "needs_revision",
            "archived",
        }:
            raise EducationError("Unsupported research asset review decision.")
        current = str(asset["review_state"])
        allowed = {
            "ai_generated": {"evidence_verified", "needs_revision", "archived"},
            "evidence_verification": {"evidence_verified", "needs_revision"},
            "faculty_review": {"faculty_approved", "needs_revision"},
            "needs_revision": {"evidence_verified", "archived"},
        }
        if decision not in allowed.get(current, set()):
            raise Conflict(f"Review decision {decision} is invalid from {current}.")
        next_state = {
            "evidence_verified": "faculty_review",
            "faculty_approved": "approved",
            "needs_revision": "needs_revision",
            "archived": "archived",
        }[decision]
        verification_state = (
            "verified" if decision in {"evidence_verified", "faculty_approved"} else asset["verification_state"]
        )
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_asset_reviews
                VALUES(?,?,?,?,?,?,?)""",
                (
                    ident("assetreview"),
                    asset_id,
                    actor,
                    decision,
                    comments,
                    encode_json(evidence_check or {}),
                    timestamp,
                ),
            )
            db.execute(
                """UPDATE education_p30_research_assets SET
                verification_state=?,review_state=?,updated_at=? WHERE id=?""",
                (verification_state, next_state, timestamp, asset_id),
            )
        return self._tenant_row(
            "education_p30_research_assets",
            asset_id,
            institution_id,
        )

    def publish_research_asset(
        self,
        actor: str,
        asset_id: str,
        *,
        target: str,
    ) -> dict[str, Any]:
        asset = self._tenant_row("education_p30_research_assets", asset_id)
        institution_id = str(asset["institution_id"])
        self._require(actor, institution_id, "staff")
        if asset["review_state"] != "approved" or asset["verification_state"] != "verified":
            raise Conflict("Evidence verification and faculty approval are required.")
        paper_ids = decode_json(asset["source_paper_ids_json"], [])
        if paper_ids:
            placeholders = ",".join("?" for _ in paper_ids)
            bad = self._all(
                f"""SELECT id,retraction_state FROM education_p30_research_papers
                WHERE id IN ({placeholders})
                AND retraction_state NOT IN ('none','not_retracted','unknown')""",
                tuple(paper_ids),
            )
            if bad:
                raise Conflict("A source paper has a retraction warning.")
        target_key = normalized_key(target)
        if target_key not in {
            "academy",
            "classroom",
            "studio",
            "shiro",
            "science_pulse",
        }:
            raise EducationError("Unsupported research asset publication target.")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_p30_research_assets SET
                review_state='published',publishing_state='published',
                published_target=?,published_at=?,updated_at=? WHERE id=?""",
                (target_key, timestamp, timestamp, asset_id),
            )
            db.execute(
                """INSERT INTO education_outbox
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,dedupe_key) DO NOTHING""",
                (
                    ident("outbox"),
                    institution_id,
                    "research_asset.published",
                    "research_asset",
                    asset_id,
                    encode_json({"target": target_key, "asset_id": asset_id}),
                    f"research-asset-publish-{asset_id}-{target_key}",
                    "pending",
                    0,
                    timestamp,
                    "",
                    timestamp,
                    None,
                    timestamp,
                ),
            )
        self._audit(
            actor,
            institution_id,
            "research_asset_published",
            "research_asset",
            asset_id,
            {"target": target_key},
        )
        return self._tenant_row(
            "education_p30_research_assets",
            asset_id,
            institution_id,
        )

    def create_research_project(
        self,
        actor: str,
        institution_id: str,
        *,
        title: str,
        supervisor_id: str,
        team: list[str] | None = None,
        research_questions: list[str] | None = None,
        hypotheses: list[str] | None = None,
        literature_ids: list[str] | None = None,
        protocol: dict[str, Any] | None = None,
        milestones: list[dict[str, Any]] | None = None,
        ethics_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "staff")
        if not title.strip():
            raise EducationError("Research project title is required.")
        project_id = ident("researchproject")
        timestamp = now()
        ethics = dict(ethics_metadata or {})
        ethics["claim_boundary"] = (
            "Metadata recorded only; ethics approval is not verified without an uploaded approval record."
        )
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_research_projects
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    project_id,
                    institution_id,
                    title.strip(),
                    supervisor_id,
                    encode_json(team or []),
                    encode_json(research_questions or []),
                    encode_json(hypotheses or []),
                    encode_json(literature_ids or []),
                    encode_json(protocol or {}),
                    encode_json(milestones or []),
                    "[]",
                    "[]",
                    "{}",
                    encode_json(ethics),
                    0,
                    "active",
                    timestamp,
                    timestamp,
                ),
            )
        return self._tenant_row(
            "education_p30_research_projects",
            project_id,
            institution_id,
        )
