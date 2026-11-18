from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from ..platform import Conflict, Denied, EducationError, Missing, ident, now
from .base import STAFF_ROLES, Phase30Base, decode_json, encode_json, normalized_key

SKILL_TAXONOMY = [
    ("biological_observation", "biological", "Biological observation"),
    ("micropipetting", "laboratory", "Micropipetting"),
    ("laboratory_safety", "laboratory", "Laboratory safety"),
    ("sequence_quality_control", "bioinformatics", "Sequence quality control"),
    ("sequence_analysis", "bioinformatics", "Sequence analysis"),
    ("data_visualization", "data_science", "Data visualization"),
    ("statistical_reasoning", "data_science", "Statistical reasoning"),
    ("literature_review", "research", "Literature review"),
    ("research_integrity", "research", "Research integrity"),
    ("scientific_writing", "communication", "Scientific writing"),
    ("scientific_presentation", "communication", "Scientific presentation"),
    ("lesson_design", "teaching", "Lesson design"),
]


class PortfolioMixin(Phase30Base):
    def seed_skills(self) -> dict[str, int]:
        timestamp = now()
        with self.db.connection() as db:
            for key, category, name in SKILL_TAXONOMY:
                db.execute(
                    """INSERT INTO education_p30_skills
                    VALUES(?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(institution_id,key) DO UPDATE SET
                    category=excluded.category,name=excluded.name,
                    description=excluded.description,state='active',
                    updated_at=excluded.updated_at""",
                    (
                        f"skill_{key}",
                        "",
                        key,
                        category,
                        name,
                        f"BioIntel {category.replace('_', ' ')} skill.",
                        365,
                        "active",
                        timestamp,
                        timestamp,
                    ),
                )
        return {"skills": len(SKILL_TAXONOMY)}

    def get_or_create_portfolio(
        self,
        actor: str,
        institution_id: str,
        *,
        owner_id: str = "",
        profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        roles = self._require(actor, institution_id, "member")
        owner = owner_id or actor
        if owner != actor and not roles.intersection(STAFF_ROLES):
            raise Denied("Portfolio access denied.")
        existing = self._one(
            """SELECT * FROM education_p30_portfolios
            WHERE institution_id=? AND owner_id=?""",
            (institution_id, owner),
        )
        if existing:
            return existing
        portfolio_id = ident("portfolio")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_portfolios
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    portfolio_id,
                    institution_id,
                    owner,
                    encode_json(profile or {}),
                    "private",
                    1,
                    0,
                    timestamp,
                    timestamp,
                ),
            )
        return self._tenant_row(
            "education_p30_portfolios",
            portfolio_id,
            institution_id,
        )

    def _validate_portfolio_evidence(
        self,
        institution_id: str,
        evidence_type: str,
        evidence_id: str,
    ) -> str:
        table_map = {
            "virtual_lab": "education_p30_lab_attempts",
            "research_asset": "education_p30_research_assets",
            "credential": "education_p30_credentials",
            "skill_evidence": "education_p30_skill_evidence",
        }
        table = table_map.get(evidence_type)
        if table:
            row = self._tenant_row(table, evidence_id, institution_id)
            return str(
                row.get("state")
                or row.get("verification_state")
                or row.get("review_state")
                or "unverified"
            )
        if evidence_type in {
            "course",
            "assignment",
            "examination",
            "project",
            "presentation",
            "publication",
            "dataset",
            "code_repository_metadata",
            "reflection",
        }:
            return "unverified"
        raise EducationError("Unsupported portfolio evidence type.")

    def add_portfolio_item(
        self,
        actor: str,
        portfolio_id: str,
        *,
        item_type: str,
        title: str,
        description: str = "",
        evidence_type: str,
        evidence_id: str,
        evidence: dict[str, Any] | None = None,
        selected_for_showcase: bool = False,
    ) -> dict[str, Any]:
        portfolio = self._tenant_row("education_p30_portfolios", portfolio_id)
        institution_id = str(portfolio["institution_id"])
        roles = self._require(actor, institution_id, "member")
        if actor != portfolio["owner_id"] and not roles.intersection(STAFF_ROLES):
            raise Denied("Portfolio item access denied.")
        evidence_key = normalized_key(evidence_type)
        evidence_state = self._validate_portfolio_evidence(
            institution_id,
            evidence_key,
            evidence_id,
        )
        verified = evidence_state in {
            "assessed",
            "approved",
            "published",
            "active",
            "verified",
        }
        item_id = ident("portfolioitem")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_portfolio_items
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item_id,
                    portfolio_id,
                    normalized_key(item_type),
                    title.strip(),
                    description,
                    evidence_key,
                    evidence_id,
                    encode_json(evidence or {}),
                    "verified" if verified else "unverified",
                    actor if verified and roles.intersection(STAFF_ROLES) else "",
                    int(selected_for_showcase),
                    timestamp,
                    timestamp,
                ),
            )
        return self._one(
            "SELECT * FROM education_p30_portfolio_items WHERE id=?",
            (item_id,),
        ) or {}

    def add_skill_evidence(
        self,
        actor: str,
        institution_id: str,
        owner_id: str,
        *,
        skill_key: str,
        evidence_type: str,
        evidence_id: str,
        proficiency: str,
        demonstrated_at: str = "",
        verify: bool = False,
    ) -> dict[str, Any]:
        roles = self._require(actor, institution_id, "member")
        if owner_id != actor and not roles.intersection(STAFF_ROLES):
            raise Denied("Skill evidence access denied.")
        if verify and not roles.intersection(STAFF_ROLES):
            raise Denied("Only staff may verify skill evidence.")
        self.seed_skills()
        skill = self._one(
            """SELECT * FROM education_p30_skills
            WHERE key=? AND institution_id IN ('',?) AND state='active'
            ORDER BY CASE WHEN institution_id=? THEN 0 ELSE 1 END LIMIT 1""",
            (normalized_key(skill_key), institution_id, institution_id),
        )
        if not skill:
            raise Missing("Skill not found.")
        allowed_proficiency = {
            "introduced",
            "developing",
            "proficient",
            "advanced",
            "expert",
        }
        proficiency_key = normalized_key(proficiency)
        if proficiency_key not in allowed_proficiency:
            raise EducationError("Unsupported skill proficiency.")
        timestamp = now()
        demonstrated = demonstrated_at or timestamp
        expires = (
            datetime.fromisoformat(demonstrated.replace("Z", "+00:00"))
            + timedelta(days=int(skill["reassessment_days"]))
        ).isoformat()
        evidence_row_id = ident("skillevidence")
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_skill_evidence
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(owner_id,skill_id,evidence_type,evidence_id) DO UPDATE SET
                proficiency=excluded.proficiency,
                demonstrated_at=excluded.demonstrated_at,
                verification_state=excluded.verification_state,
                reviewer_id=excluded.reviewer_id,expires_at=excluded.expires_at,
                updated_at=excluded.updated_at""",
                (
                    evidence_row_id,
                    institution_id,
                    owner_id,
                    skill["id"],
                    normalized_key(evidence_type),
                    evidence_id,
                    proficiency_key,
                    demonstrated,
                    "verified" if verify else "unverified",
                    actor if verify else "",
                    expires,
                    timestamp,
                    timestamp,
                ),
            )
        return self._one(
            """SELECT * FROM education_p30_skill_evidence
            WHERE owner_id=? AND skill_id=? AND evidence_type=? AND evidence_id=?""",
            (owner_id, skill["id"], normalized_key(evidence_type), evidence_id),
        ) or {}

    def _credential_pdf(
        self,
        credential_id: str,
        institution_id: str,
        title: str,
        owner_id: str,
        issuer_id: str,
        issued_at: str,
        unique_code: str,
    ) -> str:
        destination = self._safe_storage_path(
            institution_id,
            "credentials",
            credential_id,
            "certificate.pdf",
        )
        pdf = canvas.Canvas(str(destination), pagesize=A4)
        width, height = A4
        pdf.setTitle(title)
        pdf.setFont("Helvetica-Bold", 22)
        pdf.drawCentredString(width / 2, height - 100, "BioIntel Academic Credential")
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawCentredString(width / 2, height - 150, title[:70])
        pdf.setFont("Helvetica", 11)
        pdf.drawCentredString(width / 2, height - 190, f"Issued to: {owner_id}")
        pdf.drawCentredString(width / 2, height - 212, f"Issuer: {issuer_id}")
        pdf.drawCentredString(width / 2, height - 234, f"Issued: {issued_at}")
        pdf.drawCentredString(width / 2, height - 256, f"Verification code: {unique_code}")
        verify_text = f"biointel://credential/verify/{unique_code}"
        qr = QrCodeWidget(verify_text)
        bounds = qr.getBounds()
        size = 110
        drawing = Drawing(
            size,
            size,
            transform=[
                size / (bounds[2] - bounds[0]),
                0,
                0,
                size / (bounds[3] - bounds[1]),
                0,
                0,
            ],
        )
        drawing.add(qr)
        renderPDF.draw(drawing, pdf, width / 2 - size / 2, height - 400)
        pdf.setFont("Helvetica-Oblique", 8)
        pdf.drawCentredString(
            width / 2,
            60,
            "Local verification record. No accreditation claim is implied.",
        )
        pdf.save()
        return str(destination)

    def issue_credential(
        self,
        actor: str,
        institution_id: str,
        owner_id: str,
        *,
        credential_type: str,
        title: str,
        criteria: dict[str, Any],
        evidence: list[dict[str, Any]],
        expires_at: str = "",
    ) -> dict[str, Any]:
        self._require(actor, institution_id, "staff")
        if not title.strip() or not criteria or not evidence:
            raise EducationError("Credential title, criteria and evidence are required.")
        if any(
            phrase in title.casefold()
            for phrase in ("nationally accredited", "internationally accredited")
        ):
            raise Denied("Accreditation claims require an externally verified approval record.")
        unverified = [
            item
            for item in evidence
            if str(item.get("verification_state", "")).casefold()
            not in {"verified", "approved", "assessed", "passed"}
        ]
        if unverified:
            raise Conflict("All credential evidence must be verified.")
        evidence_json = encode_json(evidence)
        evidence_sha = hashlib.sha256(evidence_json.encode("utf-8")).hexdigest()
        credential_id = ident("credential")
        unique_code = secrets.token_urlsafe(18)
        issued_at = now()
        signature = self.platform._signature(
            encode_json(
                {
                    "credential_id": credential_id,
                    "institution_id": institution_id,
                    "owner_id": owner_id,
                    "title": title,
                    "evidence_sha256": evidence_sha,
                    "unique_code": unique_code,
                    "issued_at": issued_at,
                }
            )
        )
        certificate_path = self._credential_pdf(
            credential_id,
            institution_id,
            title,
            owner_id,
            actor,
            issued_at,
            unique_code,
        )
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_credentials
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    credential_id,
                    institution_id,
                    owner_id,
                    normalized_key(credential_type),
                    title.strip(),
                    encode_json(criteria),
                    evidence_json,
                    evidence_sha,
                    actor,
                    issued_at,
                    expires_at or None,
                    unique_code,
                    signature,
                    "active",
                    "",
                    "",
                    None,
                    certificate_path,
                    timestamp,
                    timestamp,
                ),
            )
            db.execute(
                """INSERT INTO education_p30_credential_events
                VALUES(?,?,?,?,?,?)""",
                (
                    ident("credentialevent"),
                    credential_id,
                    actor,
                    "issued",
                    encode_json({"evidence_sha256": evidence_sha}),
                    timestamp,
                ),
            )
        self._audit(
            actor,
            institution_id,
            "credential_issued",
            "credential",
            credential_id,
            {"owner_id": owner_id, "evidence_sha256": evidence_sha},
        )
        return self._tenant_row(
            "education_p30_credentials",
            credential_id,
            institution_id,
        )

    def verify_credential(self, unique_code: str) -> dict[str, Any]:
        credential = self._one(
            "SELECT * FROM education_p30_credentials WHERE unique_code=?",
            (str(unique_code),),
        )
        if not credential:
            return {"valid": False, "reason": "not_found"}
        evidence_hash = hashlib.sha256(
            str(credential["evidence_json"]).encode("utf-8")
        ).hexdigest()
        signature = self.platform._signature(
            encode_json(
                {
                    "credential_id": credential["id"],
                    "institution_id": credential["institution_id"],
                    "owner_id": credential["owner_id"],
                    "title": credential["title"],
                    "evidence_sha256": credential["evidence_sha256"],
                    "unique_code": credential["unique_code"],
                    "issued_at": credential["issued_at"],
                }
            )
        )
        expired = False
        if credential["expires_at"]:
            expires = datetime.fromisoformat(
                str(credential["expires_at"]).replace("Z", "+00:00")
            )
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            expired = expires < datetime.now(timezone.utc)
        valid = (
            credential["state"] == "active"
            and not expired
            and evidence_hash == credential["evidence_sha256"]
            and secrets.compare_digest(signature, str(credential["signature"]))
        )
        return {
            "valid": valid,
            "state": credential["state"],
            "expired": expired,
            "credential_id": credential["id"],
            "title": credential["title"],
            "credential_type": credential["credential_type"],
            "institution_id": credential["institution_id"],
            "owner_reference": hashlib.sha256(
                str(credential["owner_id"]).encode("utf-8")
            ).hexdigest()[:16],
            "issuer_id": credential["issuer_id"],
            "issued_at": credential["issued_at"],
            "expires_at": credential["expires_at"],
            "evidence_sha256": credential["evidence_sha256"],
            "accreditation_claim": False,
        }

    def revoke_credential(
        self,
        actor: str,
        credential_id: str,
        *,
        reason: str,
    ) -> dict[str, Any]:
        credential = self._tenant_row("education_p30_credentials", credential_id)
        institution_id = str(credential["institution_id"])
        self._require(actor, institution_id, "staff")
        if credential["state"] != "active":
            raise Conflict("Only an active credential may be revoked.")
        if not reason.strip():
            raise EducationError("Credential revocation reason is required.")
        timestamp = now()
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_p30_credentials SET state='revoked',
                revocation_reason=?,revoked_by=?,revoked_at=?,updated_at=? WHERE id=?""",
                (reason.strip(), actor, timestamp, timestamp, credential_id),
            )
            db.execute(
                """INSERT INTO education_p30_credential_events
                VALUES(?,?,?,?,?,?)""",
                (
                    ident("credentialevent"),
                    credential_id,
                    actor,
                    "revoked",
                    encode_json({"reason": reason.strip()}),
                    timestamp,
                ),
            )
        return self._tenant_row(
            "education_p30_credentials",
            credential_id,
            institution_id,
        )

    def create_portfolio_share(
        self,
        actor: str,
        portfolio_id: str,
        *,
        audience: str,
        item_ids: list[str] | None = None,
        expires_hours: int = 24,
    ) -> dict[str, Any]:
        portfolio = self._tenant_row("education_p30_portfolios", portfolio_id)
        institution_id = str(portfolio["institution_id"])
        if actor != portfolio["owner_id"]:
            raise Denied("Only the portfolio owner may create a share.")
        self._require(actor, institution_id, "member")
        if audience not in {"institution", "specific_reviewer", "public"}:
            raise EducationError("Unsupported portfolio share audience.")
        if audience == "public" and (
            not portfolio["public_opt_in"] or portfolio["minor_safe"]
        ):
            raise Denied("Public sharing requires explicit adult-safe opt-in.")
        if expires_hours < 1 or expires_hours > 24 * 365:
            raise EducationError("Share expiry must be between 1 hour and 1 year.")
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        share_id = ident("portfolioshare")
        timestamp = now()
        expires_at = (
            datetime.now(timezone.utc) + timedelta(hours=expires_hours)
        ).isoformat()
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_portfolio_shares
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    share_id,
                    portfolio_id,
                    token_hash,
                    audience,
                    encode_json(item_ids or []),
                    expires_at,
                    "active",
                    actor,
                    timestamp,
                    None,
                ),
            )
        return {
            "id": share_id,
            "token": token,
            "expires_at": expires_at,
            "audience": audience,
        }

    def resolve_portfolio_share(self, token: str) -> dict[str, Any]:
        token_hash = hashlib.sha256(str(token).encode("utf-8")).hexdigest()
        share = self._one(
            """SELECT * FROM education_p30_portfolio_shares
            WHERE token_sha256=? AND state='active'""",
            (token_hash,),
        )
        if not share:
            raise Missing("Portfolio share not found.")
        expires = datetime.fromisoformat(str(share["expires_at"]).replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            raise Denied("Portfolio share has expired.")
        portfolio = self._one(
            "SELECT * FROM education_p30_portfolios WHERE id=?",
            (share["portfolio_id"],),
        )
        allowed_ids = set(decode_json(share["item_ids_json"], []))
        items = self._all(
            """SELECT id,item_type,title,description,evidence_type,
            verification_state,selected_for_showcase,created_at
            FROM education_p30_portfolio_items WHERE portfolio_id=? ORDER BY created_at DESC""",
            (share["portfolio_id"],),
        )
        if allowed_ids:
            items = [item for item in items if item["id"] in allowed_ids]
        elif share["audience"] == "public":
            items = [item for item in items if item["selected_for_showcase"]]
        return {
            "portfolio": {
                "profile": decode_json((portfolio or {}).get("profile_json"), {}),
                "visibility": share["audience"],
            },
            "items": items,
            "expires_at": share["expires_at"],
        }

    def revoke_portfolio_share(
        self,
        actor: str,
        share_id: str,
    ) -> dict[str, Any]:
        share = self._one(
            """SELECT s.*,p.institution_id,p.owner_id
            FROM education_p30_portfolio_shares s
            JOIN education_p30_portfolios p ON p.id=s.portfolio_id
            WHERE s.id=?""",
            (share_id,),
        )
        if not share:
            raise Missing("Portfolio share not found.")
        if actor != share["owner_id"]:
            raise Denied("Only the portfolio owner may revoke sharing.")
        with self.db.connection() as db:
            db.execute(
                """UPDATE education_p30_portfolio_shares
                SET state='revoked',revoked_at=? WHERE id=?""",
                (now(), share_id),
            )
        return self._one(
            "SELECT * FROM education_p30_portfolio_shares WHERE id=?",
            (share_id,),
        ) or {}

    def save_career_plan(
        self,
        actor: str,
        institution_id: str,
        *,
        owner_id: str,
        career_key: str,
        interests: dict[str, Any],
        required_skills: list[str],
        roadmap: list[dict[str, Any]],
        internships: list[dict[str, Any]] | None = None,
        applications: list[dict[str, Any]] | None = None,
        mentor_notes: str = "",
    ) -> dict[str, Any]:
        roles = self._require(actor, institution_id, "member")
        if actor != owner_id and not roles.intersection(STAFF_ROLES):
            raise Denied("Career plan access denied.")
        self.seed_skills()
        verified_skills = {
            row["key"]
            for row in self._all(
                """SELECT s.key FROM education_p30_skill_evidence e
                JOIN education_p30_skills s ON s.id=e.skill_id
                WHERE e.institution_id=? AND e.owner_id=?
                AND e.verification_state='verified'
                AND (e.expires_at IS NULL OR e.expires_at>?)""",
                (institution_id, owner_id, now()),
            )
        }
        missing = sorted(set(required_skills) - verified_skills)
        plan_id = ident("careerplan")
        timestamp = now()
        disclaimer = (
            "Career recommendations are guidance only and do not guarantee admission, "
            "internship, employment or professional recognition."
        )
        with self.db.connection() as db:
            db.execute(
                """INSERT INTO education_p30_career_plans
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(institution_id,owner_id,career_key) DO UPDATE SET
                interest_json=excluded.interest_json,
                required_skills_json=excluded.required_skills_json,
                missing_skills_json=excluded.missing_skills_json,
                roadmap_json=excluded.roadmap_json,
                internships_json=excluded.internships_json,
                applications_json=excluded.applications_json,
                mentor_notes=excluded.mentor_notes,updated_at=excluded.updated_at""",
                (
                    plan_id,
                    institution_id,
                    owner_id,
                    normalized_key(career_key),
                    encode_json(interests),
                    encode_json(required_skills),
                    encode_json(missing),
                    encode_json(roadmap),
                    encode_json(internships or []),
                    encode_json(applications or []),
                    mentor_notes,
                    disclaimer,
                    timestamp,
                    timestamp,
                ),
            )
        return self._one(
            """SELECT * FROM education_p30_career_plans
            WHERE institution_id=? AND owner_id=? AND career_key=?""",
            (institution_id, owner_id, normalized_key(career_key)),
        ) or {}
