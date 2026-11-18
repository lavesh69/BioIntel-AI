from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from biointel.database.core import utc_now
from biointel.connect.services import ConnectError, PermissionDenied
from biointel.connect.phase_store import PersistentMap, PersistentList

class GrantIntelligenceService:
    def __init__(self, services: Any) -> None:
        self.services = services
        self._opportunities = PersistentMap(services,"phase_c.grant_opportunities")
        self._proposals = PersistentMap(services,"phase_c.proposals")

    def add_opportunity(self, sponsor: str, title: str, funding_amount: float, deadline: str, fields: List[str]) -> Dict[str, Any]:
        grant_id = f"grant_{uuid.uuid4().hex}"
        opp = {
            "grant_id": grant_id,
            "sponsor": sponsor,
            "title": title,
            "funding_amount": funding_amount,
            "deadline": deadline,
            "research_fields": fields,
            "state": "open",
            "created_at_utc": utc_now()
        }
        self._opportunities[grant_id] = opp
        return opp

    def create_proposal(self, user_id: str, grant_id: str, title: str, pi_user_id: str) -> Dict[str, Any]:
        proposal_id = f"prop_{uuid.uuid4().hex}"
        now = utc_now()
        proposal = {
            "proposal_id": proposal_id,
            "grant_id": grant_id,
            "owner_id": user_id,
            "pi_user_id": pi_user_id,
            "co_investigators": [],
            "title": title,
            "budget": 0.0,
            "ethics_checklist_completed": False,
            "risk_register": [],
            "state": "draft",
            "created_at_utc": now,
            "updated_at_utc": now
        }
        self._proposals[proposal_id] = proposal
        return proposal

    def add_co_investigator(self, user_id: str, proposal_id: str, co_i_user_id: str) -> Dict[str, Any]:
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            raise ConnectError("Proposal not found.")
        if proposal["owner_id"] != user_id and proposal["pi_user_id"] != user_id:
            raise PermissionDenied("Only owner or PI can add co-investigators.")
        if co_i_user_id not in proposal["co_investigators"]:
            proposal["co_investigators"].append(co_i_user_id)
        return proposal

    def assist_grant_draft(self, user_id: str, proposal_id: str, section: str) -> Dict[str, Any]:
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            raise ConnectError("Proposal not found.")
        return {
            "proposal_id": proposal_id,
            "section": section,
            "draft_text": f"Suggested text for {section} based on user research profile.",
            "requires_user_approval": True,
            "fabricated_citations": False,
            "generated_at_utc": utc_now()
        }


class ConsortiumService:
    def __init__(self, services: Any) -> None:
        self.services = services
        self._consortia = PersistentMap(services,"phase_c.consortia")
        self._votes = PersistentMap(services,"phase_c.consortium_votes")

    def create(self, user_id: str, name: str, lead_institution: str) -> Dict[str, Any]:
        cid = f"consortium_{uuid.uuid4().hex}"
        now = utc_now()
        consortium = {
            "consortium_id": cid,
            "owner_id": user_id,
            "name": name,
            "lead_institution": lead_institution,
            "sites": [lead_institution],
            "members": [user_id],
            "state": "active",
            "created_at_utc": now
        }
        self._consortia[cid] = consortium
        self._votes[cid] = []
        return consortium

    def propose_decision_vote(self, user_id: str, consortium_id: str, title: str, quorum_required: int = 2) -> Dict[str, Any]:
        consortium = self._consortia.get(consortium_id)
        if not consortium:
            raise ConnectError("Consortium not found.")
        vote_id = f"vote_{uuid.uuid4().hex}"
        vote = {
            "vote_id": vote_id,
            "consortium_id": consortium_id,
            "proposed_by": user_id,
            "title": title,
            "quorum_required": quorum_required,
            "votes_cast": {},
            "state": "open",
            "created_at_utc": utc_now()
        }
        self._votes[consortium_id].append(vote)
        return vote

    def cast_vote(self, user_id: str, consortium_id: str, vote_id: str, choice: str) -> Dict[str, Any]:
        votes_list = self._votes.get(consortium_id, [])
        target_vote = next((v for v in votes_list if v["vote_id"] == vote_id), None)
        if not target_vote:
            raise ConnectError("Consortium vote proposal not found.")
        if target_vote["state"] != "open":
            raise ConnectError("Voting has closed.")
        
        target_vote["votes_cast"][user_id] = choice
        total_votes = len(target_vote["votes_cast"])
        quorum_met = total_votes >= target_vote["quorum_required"]
        
        return {
            "vote_id": vote_id,
            "voter_id": user_id,
            "choice": choice,
            "total_votes": total_votes,
            "quorum_met": quorum_met
        }


class DataAccessCommitteeService:
    def __init__(self, services: Any) -> None:
        self.services = services
        self._requests = PersistentMap(services,"phase_c.dac_requests")

    def submit_request(self, user_id: str, dataset_id: str, intended_use: str) -> Dict[str, Any]:
        req_id = f"dacreq_{uuid.uuid4().hex}"
        now = utc_now()
        req = {
            "request_id": req_id,
            "applicant_id": user_id,
            "dataset_id": dataset_id,
            "intended_use": intended_use,
            "status": "pending_review",
            "votes": {},
            "created_at_utc": now
        }
        self._requests[req_id] = req
        return req

    def vote_request(self, committee_member_id: str, request_id: str, decision: str) -> Dict[str, Any]:
        req = self._requests.get(request_id)
        if not req:
            raise ConnectError("DAC request not found.")
        if decision not in ["approve", "reject"]:
            raise ConnectError("Decision must be approve or reject.")
        
        req["votes"][committee_member_id] = decision
        approvals = sum(1 for v in req["votes"].values() if v == "approve")
        
        if approvals >= 2:
            req["status"] = "approved"
        return req

    def revoke_access(self, admin_id: str, request_id: str, reason: str) -> Dict[str, Any]:
        req = self._requests.get(request_id)
        if not req:
            raise ConnectError("DAC request not found.")
        req["status"] = "revoked"
        req["revocation_reason"] = reason
        req["revoked_by"] = admin_id
        return req


class GovernancePolicyService:
    def __init__(self, services: Any) -> None:
        self.services = services
        self._policies = PersistentMap(services,"phase_c.policies")
        self._acknowledgements = PersistentMap(services,"phase_c.policy_acknowledgements")

    def create_policy(self, admin_id: str, title: str, content: str, scope: str = "global") -> Dict[str, Any]:
        policy_id = f"policy_{uuid.uuid4().hex}"
        now = utc_now()
        policy = {
            "policy_id": policy_id,
            "created_by": admin_id,
            "title": title,
            "content": content,
            "scope": scope,
            "version": 1,
            "created_at_utc": now
        }
        self._policies[policy_id] = policy
        self._acknowledgements[policy_id] = []
        return policy

    def acknowledge_policy(self, user_id: str, policy_id: str) -> Dict[str, Any]:
        policy = self._policies.get(policy_id)
        if not policy:
            raise ConnectError("Governance policy not found.")
        if user_id not in self._acknowledgements[policy_id]:
            self._acknowledgements[policy_id].append(user_id)
        return {
            "policy_id": policy_id,
            "user_id": user_id,
            "acknowledged": True,
            "timestamp_utc": utc_now()
        }


