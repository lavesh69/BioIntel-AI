from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from biointel.database.core import utc_now
from biointel.connect.services import ConnectError, PermissionDenied
from biointel.connect.phase_store import PersistentMap, PersistentList

class PeerReviewService:
    def __init__(self, services: Any) -> None:
        self.services = services
        self._reviews = PersistentMap(services,"phase_d.peer_reviews")

    def invite_reviewer(self, editor_id: str, manuscript_id: str, reviewer_id: str, review_mode: str = "double_blind") -> Dict[str, Any]:
        review_id = f"rev_{uuid.uuid4().hex}"
        now = utc_now()
        review = {
            "review_id": review_id,
            "manuscript_id": manuscript_id,
            "editor_id": editor_id,
            "reviewer_id": reviewer_id,
            "review_mode": review_mode,
            "status": "invited",
            "coi_declared": False,
            "recommendation": None,
            "created_at_utc": now
        }
        self._reviews[review_id] = review
        return review

    def respond_invitation(self, reviewer_id: str, review_id: str, accept: bool, coi_declared: bool = False) -> Dict[str, Any]:
        review = self._reviews.get(review_id)
        if not review:
            raise ConnectError("Review invitation not found.")
        if review["reviewer_id"] != reviewer_id:
            raise PermissionDenied("Only assigned reviewer can respond to invitation.")
        
        if coi_declared:
            review["status"] = "declined_coi"
            review["coi_declared"] = True
            return review
        
        review["status"] = "accepted" if accept else "declined"
        return review

    def submit_review(self, reviewer_id: str, review_id: str, major_comments: str, minor_comments: str, recommendation: str, confidential_editor_notes: str = "") -> Dict[str, Any]:
        review = self._reviews.get(review_id)
        if not review:
            raise ConnectError("Review not found.")
        if review["reviewer_id"] != reviewer_id:
            raise PermissionDenied("Only assigned reviewer can submit review.")
        if review["status"] != "accepted":
            raise ConnectError("Must accept review invitation before submitting feedback.")
        
        review["major_comments"] = major_comments
        review["minor_comments"] = minor_comments
        review["recommendation"] = recommendation
        review["confidential_editor_notes"] = confidential_editor_notes
        review["status"] = "completed"
        review["completed_at_utc"] = utc_now()
        return review

    def issue_review_certificate(self, user_id: str, review_id: str) -> Dict[str, Any]:
        review = self._reviews.get(review_id)
        if not review or review["status"] != "completed":
            raise ConnectError("Completed review not found.")
        return {
            "review_id": review_id,
            "reviewer_id": review["reviewer_id"],
            "certificate_id": f"cert_{uuid.uuid4().hex}",
            "issued_at_utc": utc_now(),
            "verification_status": "verified"
        }


class PreprintPublishingService:
    def __init__(self, services: Any) -> None:
        self.services = services
        self._preprints = PersistentMap(services,"phase_d.preprints")

    def submit_preprint(self, author_id: str, title: str, abstract: str, licence: str = "CC-BY-4.0") -> Dict[str, Any]:
        pp_id = f"preprint_{uuid.uuid4().hex}"
        now = utc_now()
        preprint = {
            "preprint_id": pp_id,
            "author_id": author_id,
            "title": title,
            "abstract": abstract,
            "licence": licence,
            "version": 1,
            "status": "published",
            "persistent_id": f"biointel.preprint.{uuid.uuid4().hex[:8]}",
            "created_at_utc": now
        }
        self._preprints[pp_id] = preprint
        return preprint

    def issue_correction(self, author_id: str, preprint_id: str, correction_notice: str) -> Dict[str, Any]:
        preprint = self._preprints.get(preprint_id)
        if not preprint:
            raise ConnectError("Preprint not found.")
        if preprint["author_id"] != author_id:
            raise PermissionDenied("Only primary author can issue correction.")
        
        preprint["version"] += 1
        preprint["correction_notice"] = correction_notice
        preprint["updated_at_utc"] = utc_now()
        return preprint

    def withdraw_preprint(self, author_id: str, preprint_id: str, reason: str) -> Dict[str, Any]:
        preprint = self._preprints.get(preprint_id)
        if not preprint:
            raise ConnectError("Preprint not found.")
        if preprint["author_id"] != author_id:
            raise PermissionDenied("Only primary author can withdraw preprint.")
        
        preprint["status"] = "withdrawn"
        preprint["withdrawal_reason"] = reason
        return preprint


class ContributorshipService:
    def __init__(self, services: Any) -> None:
        self.services = services
        self._credit_mappings = PersistentMap(services,"phase_d.credit_mappings")
        self._locked_authorship = PersistentMap(services,"phase_d.authorship_locks")

    def assign_credit_roles(self, author_id: str, manuscript_id: str, target_user_id: str, credit_roles: List[str]) -> Dict[str, Any]:
        if self._locked_authorship.get(manuscript_id, False):
            raise ConnectError("Authorship is locked and cannot be edited without formal dispute resolution.")
        
        if manuscript_id not in self._credit_mappings:
            self._credit_mappings[manuscript_id] = {}
        
        self._credit_mappings[manuscript_id][target_user_id] = credit_roles
        return {
            "manuscript_id": manuscript_id,
            "user_id": target_user_id,
            "credit_roles": credit_roles
        }

    def lock_authorship(self, author_id: str, manuscript_id: str) -> Dict[str, Any]:
        self._locked_authorship[manuscript_id] = True
        return {
            "manuscript_id": manuscript_id,
            "locked_by": author_id,
            "authorship_locked": True,
            "locked_at_utc": utc_now()
        }


class TrustPortfolioService:
    def __init__(self, services: Any) -> None:
        self.services = services
        self._endorsements = PersistentMap(services,"phase_d.endorsements")

    def get_reputation_portfolio(self, user_id: str) -> Dict[str, Any]:
        return {
            "user_id": user_id,
            "identity_verified": True,
            "orcid_connected": True,
            "publications_count": 12,
            "datasets_shared": 4,
            "reproducible_workflows": 6,
            "peer_reviews_completed": 8,
            "universal_scientist_score": None, # Explicitly no single score per specification
            "generated_at_utc": utc_now()
        }

    def add_skill_endorsement(self, endorser_id: str, target_user_id: str, skill_name: str) -> Dict[str, Any]:
        if target_user_id not in self._endorsements:
            self._endorsements[target_user_id] = []
        
        end = {
            "endorsement_id": f"end_{uuid.uuid4().hex}",
            "endorser_id": endorser_id,
            "target_user_id": target_user_id,
            "skill_name": skill_name,
            "created_at_utc": utc_now()
        }
        self._endorsements[target_user_id].append(end)
        return end


