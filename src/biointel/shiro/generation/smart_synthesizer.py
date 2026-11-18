"""
Shiro AI — Smart Biomedical Evidence Synthesizer
Structured offline evidence synthesizer for scientific reports, genomic tables, and literature.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class SynthesizedSection:
    source_name: str
    source_type: str
    citation_id: str
    location: str
    key_findings: tuple[str, ...]
    excerpt: str


class SmartEvidenceSynthesizer:
    """Transforms raw retrieved RAG chunks into a structured scientific synthesis."""

    @staticmethod
    def _extract_findings(text: str) -> list[str]:
        """Extracts numerical metrics, fold-changes, p-values, and gene identifiers."""
        findings = []
        # Find fold changes, percentages, concentrations, p-values
        metrics = re.findall(
            r"(?:[A-Z0-9_-]+\s+)?(?:increased|decreased|fold|p-value|fdr|ic50|concentration|mutation|variant|amplification)[^.\n]*",
            text, re.IGNORECASE
        )
        for m in metrics[:3]:
            clean = " ".join(m.strip().split())
            if len(clean) >= 10:
                findings.append(clean)
        return findings

    def synthesize(
        self,
        evidence: Sequence[object],
        citations: Sequence[object],
        language_code: str = "en",
    ) -> str:
        """Constructs a structured Markdown synthesis grouped by evidence source."""
        if not evidence or not citations:
            return ""

        sections: list[SynthesizedSection] = []
        for result, citation in zip(evidence, citations):
            chunk_text = getattr(getattr(result, "chunk", None), "text", "")
            source = getattr(result, "source", None)
            source_name = getattr(source, "filename", "Evidence Source")
            source_type = getattr(source, "source_type", "document")
            location = getattr(getattr(result, "chunk", None), "location", "N/A")
            cit_id = getattr(citation, "citation_id", "CIT-01")

            findings = tuple(self._extract_findings(chunk_text))
            sections.append(SynthesizedSection(
                source_name=source_name,
                source_type=source_type,
                citation_id=cit_id,
                location=location,
                key_findings=findings,
                excerpt=chunk_text[:350] + ("…" if len(chunk_text) > 350 else "")
            ))

        # Build output based on language
        lines: list[str] = []
        if language_code == "hi":
            lines.append("### 📊 बायोइंटेक्ट वैज्ञानिक साक्ष्य विश्लेषण (Synthesized Findings)\n")
        elif language_code == "hi-Latn":
            lines.append("### 📊 BioIntel Scientific Evidence Synthesis\n")
        else:
            lines.append("### 📊 BioIntel Structured Scientific Evidence Synthesis\n")

        for sec in sections:
            lines.append(f"#### 📄 **{sec.source_name}** (`{sec.source_type}`) · [{sec.citation_id}]")
            lines.append(f"*Location: {sec.location}*\n")
            if sec.key_findings:
                lines.append("**Key Quantitative Findings:**")
                for finding in sec.key_findings:
                    lines.append(f"  • {finding}")
            lines.append(f"\n> {sec.excerpt}\n")

        return "\n".join(lines)
