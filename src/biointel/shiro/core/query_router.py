from __future__ import annotations

from biointel.shiro.core.safety import is_clinical_request
from biointel.shiro.models import LanguageInfo, QueryPlan


def route_query(
    query: str,
    language: LanguageInfo,
    *,
    external_requested: bool = False,
    external_enabled: bool = False,
) -> QueryPlan:
    value = language.normalized_query.casefold()
    clinical = is_clinical_request(query)
    if clinical:
        intent = "unsupported_medical_or_clinical_request"
    elif any(term in value for term in ("report", "रिपोर्ट")):
        intent = "report_search"
    elif any(term in value for term in ("module", "analysis result", "workflow output")):
        intent = "module_result_search"
    elif any(term in value for term in ("summarize", "summary", "सारांश")):
        intent = "document_summarization"
    elif any(term in value for term in ("compare", "तुलना")):
        intent = "comparison"
    elif any(term in value for term in ("literature", "pubmed", "doi")):
        intent = "external_literature_search"
    elif any(term in value for term in ("uploaded", "evidence", "source", "citation", "variant", "gene", "pathway", "results")):
        intent = "evidence_search"
    elif any(term in value for term in ("project", "मेरे प्रोजेक्ट", "मेरी परियोजना")):
        intent = "project_search"
    elif any(term in value for term in ("how do i", "help", "open module", "कैसे")):
        intent = "workflow_guidance"
    elif value in {"hi", "hello", "hey", "namaste", "नमस्ते"}:
        intent = "normal_conversation"
    else:
        intent = "scientific_explanation"
    retrieval = intent not in {"normal_conversation", "workflow_guidance", "unsupported_medical_or_clinical_request"}
    allowed = ("internal_project", "uploaded_evidence", "reports", "module_results")
    if external_requested and external_enabled:
        allowed += ("external_literature", "external_web")
    return QueryPlan(
        intent=intent,
        retrieval_required=retrieval,
        citations_required=retrieval,
        allowed_sources=allowed,
        external_requested=external_requested,
        external_allowed=external_requested and external_enabled,
        clinical_safety=clinical,
    )
