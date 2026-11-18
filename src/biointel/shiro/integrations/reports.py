from __future__ import annotations

from biointel.shiro.integrations.evidence import NormalizedEvidence


def normalize_report(
    report_id: str,
    title: str,
    body: str,
    *,
    module_id: str = "",
    analysis_id: str = "",
    generated_at: str = "",
    synthetic: bool = False,
) -> NormalizedEvidence:
    clean_id = report_id.strip()
    if not clean_id:
        raise ValueError("A report ID is required.")
    clean_title = " ".join(title.split())[:240] or clean_id
    document = f"# {clean_title}\n\nReport ID: {clean_id}\n"
    if module_id:
        document += f"Module: {module_id}\n"
    if analysis_id:
        document += f"Analysis: {analysis_id}\n"
    if generated_at:
        document += f"Generated: {generated_at}\n"
    document += "\n## Report content\n\n" + body.strip()
    return NormalizedEvidence(
        filename=f"report-{clean_id}.md",
        content=document.encode("utf-8"),
        source_type="biointel_report",
        metadata={
            "report_id": clean_id, "report_title": clean_title,
            "module_id": module_id, "analysis_id": analysis_id,
            "generated_at": generated_at, "adapter": "shiro-report-v1",
        },
        synthetic=synthetic,
    )