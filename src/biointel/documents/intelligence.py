from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import replace
from typing import Any, Iterable

from biointel.documents.models import DocumentExtraction, ScientificEntity

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+\-/]*")

_KNOWN_GENES = {
    "EGFR", "BRAF", "KRAS", "NRAS", "TP53", "BRCA1", "BRCA2", "ALK", "MET",
    "PIK3CA", "PTEN", "AKT1", "MTOR", "ERBB2", "HER2", "VEGFA", "TNF", "IL6",
    "ACE2", "JAK2", "STAT3", "MAPK1", "CDK4", "CDK6", "PARP1", "PDCD1", "CTLA4",
}
_ORGANISMS = {
    "homo sapiens": "Homo sapiens",
    "human": "Homo sapiens",
    "mus musculus": "Mus musculus",
    "mouse": "Mus musculus",
    "rattus norvegicus": "Rattus norvegicus",
    "rat": "Rattus norvegicus",
    "escherichia coli": "Escherichia coli",
    "e. coli": "Escherichia coli",
    "saccharomyces cerevisiae": "Saccharomyces cerevisiae",
}
_DISEASE_TERMS = (
    "cancer", "carcinoma", "leukemia", "lymphoma", "melanoma", "diabetes", "alzheimer",
    "parkinson", "infection", "fibrosis", "arthritis", "hypertension", "asthma", "obesity",
)
_ASSAY_TERMS = ("IC50", "EC50", "Ki", "Kd", "MIC", "GI50", "CC50", "LC50", "ED50")
_DRUG_SUFFIXES = (
    "mab", "nib", "tinib", "ciclib", "parib", "statin", "vir", "azole", "mycin",
    "cycline", "pril", "sartan", "olol", "caine", "oxetine", "zepam",
)
_SECTION_ALIASES = {
    "abstract": ("abstract", "summary"),
    "introduction": ("introduction", "background"),
    "methods": ("methods", "materials and methods", "methodology", "experimental"),
    "results": ("results", "findings"),
    "discussion": ("discussion",),
    "limitations": ("limitations", "study limitations"),
    "conclusion": ("conclusion", "conclusions"),
    "references": ("references", "bibliography"),
}


def _entity(
    text: str,
    entity_type: str,
    normalized: str,
    source: str,
    start: int | None,
    end: int | None,
    confidence: float,
    **metadata: Any,
) -> ScientificEntity:
    return ScientificEntity(
        text=text,
        entity_type=entity_type,
        normalized=normalized,
        source=source,
        start=start,
        end=end,
        confidence=confidence,
        metadata=metadata,
    )


def extract_scientific_entities(text: str, *, source: str = "document") -> tuple[ScientificEntity, ...]:
    entities: list[ScientificEntity] = []
    seen: set[tuple[str, str, int | None]] = set()

    def add(entity: ScientificEntity) -> None:
        key = (entity.entity_type, entity.normalized.lower(), entity.start)
        if key not in seen:
            seen.add(key)
            entities.append(entity)

    for match in re.finditer(r"\b[A-Z][A-Z0-9-]{1,11}\b", text):
        token = match.group(0)
        if token in _KNOWN_GENES or re.fullmatch(r"(?:[A-Z]{2,6}\d{0,3}|IL\d{1,2})", token):
            add(_entity(token, "gene_or_protein", token, source, match.start(), match.end(), 0.86))

    for match in re.finditer(r"\b(?:rs\d+|[A-Z]\d{1,5}[A-Z]|p\.[A-Z][a-z]{2}\d+[A-Z][a-z]{2})\b", text):
        add(_entity(match.group(0), "mutation", match.group(0), source, match.start(), match.end(), 0.92))

    for endpoint in _ASSAY_TERMS:
        for match in re.finditer(rf"\b{re.escape(endpoint)}\b", text, flags=re.IGNORECASE):
            add(_entity(match.group(0), "assay_endpoint", endpoint, source, match.start(), match.end(), 0.97))

    activity_pattern = re.compile(
        r"\b(?P<endpoint>IC50|EC50|Ki|Kd|MIC|GI50|CC50|LC50|ED50)\s*[:=]?\s*"
        r"(?P<relation>[<>≤≥]=?)?\s*(?P<value>\d+(?:\.\d+)?)\s*"
        r"(?P<unit>pM|nM|uM|µM|μM|mM|M)\b",
        flags=re.IGNORECASE,
    )
    for match in activity_pattern.finditer(text):
        normalized = (
            f"{match.group('endpoint').upper()} {match.group('relation') or '='} "
            f"{match.group('value')} {match.group('unit')}"
        )
        add(
            _entity(
                match.group(0),
                "activity_measurement",
                normalized,
                source,
                match.start(),
                match.end(),
                0.96,
                endpoint=match.group("endpoint").upper(),
                relation=match.group("relation") or "=",
                value=float(match.group("value")),
                unit=match.group("unit"),
            )
        )

    lower = text.lower()
    for alias, normalized in _ORGANISMS.items():
        for match in re.finditer(rf"\b{re.escape(alias)}\b", lower):
            add(_entity(text[match.start():match.end()], "organism", normalized, source, match.start(), match.end(), 0.9))

    for term in _DISEASE_TERMS:
        for match in re.finditer(rf"\b[\w-]*{re.escape(term)}[\w-]*\b", lower):
            raw = text[match.start():match.end()]
            add(_entity(raw, "disease", raw.lower(), source, match.start(), match.end(), 0.72))

    for match in re.finditer(r"\b[A-Za-z][A-Za-z-]{4,28}\b", text):
        raw = match.group(0)
        lowered = raw.lower()
        if any(lowered.endswith(suffix) for suffix in _DRUG_SUFFIXES):
            add(_entity(raw, "drug_or_compound", lowered, source, match.start(), match.end(), 0.72))

    for match in re.finditer(r"\b(?:PMID\s*:?\s*\d{5,10}|10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\b", text, flags=re.IGNORECASE):
        raw = match.group(0)
        kind = "pmid" if raw.lower().startswith("pmid") else "doi"
        add(_entity(raw, "publication_identifier", raw.strip(), source, match.start(), match.end(), 0.99, identifier_type=kind))

    return tuple(sorted(entities, key=lambda item: (item.start if item.start is not None else 10**12, item.entity_type)))


def structure_research_document(extraction: DocumentExtraction) -> dict[str, Any]:
    text = extraction.text.strip()
    fields: dict[str, Any] = {
        "title": extraction.metadata.get("title") or extraction.source_name,
        "document_type": "research_document",
        "sections": {},
        "sample_sizes": [],
        "activity_measurements": [],
        "publication_identifiers": [],
    }
    lines = [line.strip() for line in text.splitlines()]
    current = "unclassified"
    buckets: dict[str, list[str]] = defaultdict(list)
    for line in lines:
        normalized = re.sub(r"[^a-z ]", "", line.lower()).strip()
        detected = None
        for canonical, aliases in _SECTION_ALIASES.items():
            if normalized in aliases or any(normalized.startswith(alias + " ") for alias in aliases):
                detected = canonical
                break
        if detected and len(line) <= 100:
            current = detected
            continue
        if line:
            buckets[current].append(line)
    fields["sections"] = {
        name: "\n".join(values).strip()
        for name, values in buckets.items()
        if values
    }
    for match in re.finditer(r"\b(?:n\s*=\s*|sample(?: size)?\s*(?:of|=|:)\s*)(\d{1,7})\b", text, re.IGNORECASE):
        fields["sample_sizes"].append(int(match.group(1)))
    for entity in extraction.entities:
        if entity.entity_type == "activity_measurement":
            fields["activity_measurements"].append(entity.to_dict())
        elif entity.entity_type == "publication_identifier":
            fields["publication_identifiers"].append(entity.normalized)
    fields["entity_counts"] = dict(Counter(entity.entity_type for entity in extraction.entities))
    fields["has_methods"] = "methods" in fields["sections"]
    fields["has_results"] = "results" in fields["sections"]
    fields["has_limitations"] = "limitations" in fields["sections"]
    return fields


def detect_sensitive_information(text: str) -> list[dict[str, Any]]:
    patterns = {
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "phone": r"(?<!\d)(?:\+?\d[\d -]{8,14}\d)(?!\d)",
        "credit_card_like": r"(?<!\d)(?:\d[ -]*?){13,19}(?!\d)",
        "api_key_like": r"\b(?:sk|api|key|token)[-_]?[A-Za-z0-9]{16,}\b",
        "ipv4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    }
    findings: list[dict[str, Any]] = []
    for kind, pattern in patterns.items():
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            findings.append({"type": kind, "text": match.group(0), "start": match.start(), "end": match.end()})
    return sorted(findings, key=lambda item: item["start"])


def redact_sensitive_information(text: str, findings: Iterable[dict[str, Any]] | None = None) -> str:
    items = list(findings if findings is not None else detect_sensitive_information(text))
    redacted = text
    for item in sorted(items, key=lambda value: int(value["start"]), reverse=True):
        redacted = redacted[: int(item["start"])] + f"[REDACTED:{item['type']}]" + redacted[int(item["end"]):]
    return redacted


def enrich_extraction(extraction: DocumentExtraction, *, redact_sensitive: bool = False) -> DocumentExtraction:
    entities: list[ScientificEntity] = []
    if extraction.sections:
        offset = 0
        for section in extraction.sections:
            section_entities = extract_scientific_entities(section.text, source=section.source)
            entities.extend(section_entities)
            offset += len(section.text) + 2
    else:
        entities.extend(extract_scientific_entities(extraction.text))
    unique: dict[tuple[str, str, str], ScientificEntity] = {}
    for entity in entities:
        unique[(entity.entity_type, entity.normalized.lower(), entity.source)] = entity
    provisional = replace(extraction, entities=tuple(unique.values()))
    structured = structure_research_document(provisional)
    sensitive = detect_sensitive_information(provisional.text)
    structured["sensitive_findings"] = sensitive
    metadata = dict(provisional.metadata)
    metadata["scientific_entity_extraction"] = "rule_based_v1"
    metadata["sensitive_finding_count"] = len(sensitive)
    warnings = list(provisional.warnings)
    if sensitive:
        warnings.append(f"Detected {len(sensitive)} possible sensitive value(s); review before sharing exports.")
    if redact_sensitive:
        redacted_text = redact_sensitive_information(provisional.text, sensitive)
        redacted_sections = tuple(
            replace(section, text=redact_sensitive_information(section.text))
            for section in provisional.sections
        )
        metadata["sensitive_redaction_applied"] = True
        return replace(
            provisional,
            text=redacted_text,
            sections=redacted_sections,
            structured_fields=structured,
            metadata=metadata,
            warnings=tuple(dict.fromkeys(warnings)),
        )
    metadata["sensitive_redaction_applied"] = False
    return replace(
        provisional,
        structured_fields=structured,
        metadata=metadata,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _sentences(extraction: DocumentExtraction) -> list[tuple[str, str]]:
    output: list[tuple[str, str]] = []
    for section in extraction.sections or ():
        for sentence in _SENTENCE_RE.split(section.text.replace("\n", " ")):
            sentence = sentence.strip()
            if len(sentence) >= 20:
                output.append((section.source, sentence))
    if not output:
        for sentence in _SENTENCE_RE.split(extraction.text.replace("\n", " ")):
            sentence = sentence.strip()
            if len(sentence) >= 20:
                output.append(("document", sentence))
    return output


def answer_question(extractions: Iterable[DocumentExtraction], question: str, *, limit: int = 5) -> dict[str, Any]:
    terms = {token.lower() for token in _WORD_RE.findall(question) if len(token) > 2}
    if not terms:
        raise ValueError("Question must contain meaningful search terms.")
    candidates: list[dict[str, Any]] = []
    for extraction in extractions:
        for source, sentence in _sentences(extraction):
            tokens = [token.lower() for token in _WORD_RE.findall(sentence)]
            counts = Counter(tokens)
            overlap = sum(math.log1p(counts[term]) for term in terms if counts[term])
            if overlap <= 0:
                continue
            density = overlap / max(math.sqrt(len(tokens)), 1.0)
            candidates.append({
                "score": round(density, 6),
                "source_name": extraction.source_name,
                "source": source,
                "text": sentence,
                "citation": f"{extraction.source_name} · {source}",
            })
    candidates.sort(key=lambda item: item["score"], reverse=True)
    selected = candidates[: max(1, min(limit, 20))]
    return {
        "question": question,
        "answer": " ".join(item["text"] for item in selected) if selected else "No grounded passage matched the question.",
        "citations": selected,
        "method": "local_extract_query_v1",
    }


def compare_extractions(left: DocumentExtraction, right: DocumentExtraction) -> dict[str, Any]:
    left_entities = {(item.entity_type, item.normalized.lower()) for item in left.entities}
    right_entities = {(item.entity_type, item.normalized.lower()) for item in right.entities}
    left_tokens = set(token.lower() for token in _WORD_RE.findall(left.text))
    right_tokens = set(token.lower() for token in _WORD_RE.findall(right.text))
    union = left_tokens | right_tokens
    similarity = len(left_tokens & right_tokens) / max(len(union), 1)
    measurements: dict[tuple[str, str], list[tuple[str, float, str]]] = defaultdict(list)
    for extraction in (left, right):
        for entity in extraction.entities:
            if entity.entity_type != "activity_measurement":
                continue
            endpoint = str(entity.metadata.get("endpoint", ""))
            unit = str(entity.metadata.get("unit", ""))
            value = entity.metadata.get("value")
            if endpoint and unit and isinstance(value, (int, float)):
                measurements[(endpoint, unit)].append((extraction.source_name, float(value), entity.text))
    contradictions = []
    for (endpoint, unit), values in measurements.items():
        if len(values) < 2:
            continue
        numeric = [item[1] for item in values]
        if min(numeric) > 0 and max(numeric) / min(numeric) >= 10:
            contradictions.append({"endpoint": endpoint, "unit": unit, "values": values, "reason": "Values differ by at least one order of magnitude."})
    return {
        "left": left.source_name,
        "right": right.source_name,
        "token_jaccard_similarity": round(similarity, 4),
        "shared_entities": sorted([{"type": kind, "normalized": value} for kind, value in left_entities & right_entities], key=lambda item: (item["type"], item["normalized"])),
        "left_only_entities": sorted([{"type": kind, "normalized": value} for kind, value in left_entities - right_entities], key=lambda item: (item["type"], item["normalized"])),
        "right_only_entities": sorted([{"type": kind, "normalized": value} for kind, value in right_entities - left_entities], key=lambda item: (item["type"], item["normalized"])),
        "possible_numeric_contradictions": contradictions,
    }
