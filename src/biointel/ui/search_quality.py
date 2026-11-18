from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Sequence

_WORD_RE = re.compile(r"[a-z0-9]+")

# Search vocabulary is deliberately domain-specific. These are not silent data
# transformations; they only help users locate the correct module.
QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    "admet": ("absorption distribution metabolism excretion toxicity", "developability"),
    "ai": ("artificial intelligence", "machine learning", "ml"),
    "bam": ("alignment", "genomics", "sequence reads"),
    "cancer": ("oncology", "somatic", "tumor", "tumour"),
    "chembl": ("compound activity", "bioactivity", "drug discovery"),
    "crispr": ("guide rna", "gene editing", "grna"),
    "dti": ("drug target interaction", "compound protein interaction"),
    "drug target": ("dti", "drug target interaction", "compound protein interaction", "prediction"),
    "elisa": ("immunoassay", "plate assay", "standard curve"),
    "fastq": ("sequencing reads", "read quality", "genome qc"),
    "fcs": ("flow cytometry", "gating", "cell population"),
    "gff": ("gff3", "gene annotation", "genome annotation"),
    "gwas": ("genome wide association", "variant association"),
    "lab": ("wet lab", "laboratory", "assay", "qpcr", "elisa", "bioprocess"),
    "maf": ("mutation annotation format", "cancer variants"),
    "metagenomics": ("microbiome", "microbial community", "taxonomy", "kraken"),
    "genomics": ("fastq", "genome qc", "variants", "sequence data"),
    "microbiome": ("microbiology", "metagenomics", "taxonomy", "diversity"),
    "alignment": ("sequence comparison", "msa", "phylogeny"),
    "model training": ("machine learning", "train model", "classification", "regression"),
    "mass spectrometry": ("proteomics", "mzml", "protein annotation"),
    "flow cytometry": ("lab analytics", "fcs", "cell population", "gating"),
    "clinical trials": ("connected data", "clinicaltrials gov", "external database"),
    "pubmed search": ("connected data", "ncbi", "literature search"),
    "ml": ("machine learning", "model training", "artificial intelligence"),
    "mzml": ("mass spectrometry", "proteomics", "peaks"),
    "ncbi": ("pubmed", "gene", "clinvar", "geo", "sra", "scientific database"),
    "ocr": ("document extraction", "scanned pdf", "text recognition"),
    "documentation": ("document intelligence", "document extraction", "reports", "guide"),
    "documents": ("document intelligence", "document extraction", "ocr", "knowledge search"),
    "pdb": ("protein structure", "structural bioinformatics", "mmcif"),
    "ppi": ("protein protein interaction", "interaction network"),
    "qpcr": ("quantitative pcr", "ddct", "gene expression"),
    "rna seq": ("rnaseq", "transcriptomics", "expression counts"),
    "rnaseq": ("rna seq", "transcriptomics", "expression counts"),
    "scrna": ("single cell rna", "single cell transcriptomics", "cell heterogeneity"),
    "sdf": ("molecule file", "chemical structure", "smiles"),
    "smiles": ("chemical structure", "molecule", "drug"),
    "vcf": ("variant call format", "variants", "genomics"),
    "variant": ("vcf", "mutation", "snp", "indel"),
}

# Frequent scientific and keyboard mistakes receive a deterministic correction
# before fuzzy ranking. Fuzzy ranking still works for mistakes not listed here.

MODULE_INTENT_BOOSTS: dict[str, tuple[str, ...]] = {
    "drug target": ("dti_predictor", "dti_features", "dti_validation_evidence"),
    "dti prediction": ("dti_predictor",),
    "sequence": ("sequence_analyzer", "sequence_comparison", "batch_sequence"),
    "sequence analysis": ("sequence_analyzer", "sequence_comparison", "batch_sequence"),
    "documentation": ("document_intelligence", "document_knowledge_search", "report_studio"),
    "documents": ("document_intelligence", "document_knowledge_search", "batch_document_processor"),
    "bioinformatics": ("bioinformatics_capabilities", "sequence_analyzer", "fastq_genomics_qc"),
    "rna seq": ("transcriptomics_expression", "single_cell_heterogeneity"),
    "single cell": ("single_cell_heterogeneity",),
    "genome qc": ("fastq_genomics_qc",),
    "variant": ("variant_annotation", "cancer_genomics"),
    "cancer genomics": ("cancer_genomics", "variant_annotation"),
    "protein structure": ("structural_bioinformatics",),
    "structural": ("structural_bioinformatics",),
    "metagenomics": ("metagenomics_pipeline", "microbiology_metagenomics"),
    "qpcr": ("wetlab_biotechnology", "lab_analytics_command_center"),
    "elisa": ("wetlab_biotechnology", "lab_analytics_command_center"),
    "release": ("scientific_release_gate", "release_readiness"),
    "genomics": ("fastq_genomics_qc", "variant_annotation", "cancer_genomics"),
    "microbiome": ("microbiology_metagenomics", "metagenomics_pipeline", "lab_analytics_command_center"),
    "alignment": ("sequence_comparison", "alignment_phylogeny"),
    "model training": ("model_training", "ml_autolab"),
    "mass spectrometry": ("protein_annotation", "omics_integration"),
    "flow cytometry": ("lab_analytics_command_center", "wetlab_biotechnology"),
    "clinical trials": ("connected_data_explorer", "scientific_evidence_excellence"),
    "pubmed search": ("connected_data_explorer", "internet_research"),
}

COMMON_TYPO_CORRECTIONS: dict[str, str] = {
    "admat": "admet",
    "aligment": "alignment",
    "analizer": "analyzer",
    "analyser": "analyzer",
    "bioinfomatics": "bioinformatics",
    "bioinformatcs": "bioinformatics",
    "cancergenomics": "cancer genomics",
    "crisprr": "crispr",
    "datset": "dataset",
    "discoverey": "discovery",
    "documention": "documentation",
    "documantation": "documentation",
    "docmentation": "documentation",
    "documnet": "document",
    "durg": "drug",
    "fastqc": "fastq qc",
    "genmoics": "genomics",
    "genomicsqc": "genomics qc",
    "metagenmoics": "metagenomics",
    "metgenomics": "metagenomics",
    "microbiom": "microbiome",
    "microbiomee": "microbiome",
    "modle": "model",
    "potein": "protein",
    "spectrometery": "spectrometry",
    "cytometery": "cytometry",
    "clincal": "clinical",
    "serch": "search",
    "traget": "target",
    "moleclue": "molecule",
    "protien": "protein",
    "proteimics": "proteomics",
    "proteomcis": "proteomics",
    "qpcrr": "qpcr",
    "relese": "release",
    "sequece": "sequence",
    "seqence": "sequence",
    "sequance": "sequence",
    "sequecne": "sequence",
    "sequnce": "sequence",
    "singel cell": "single cell",
    "singlecell": "single cell",
    "strcuture": "structure",
    "structral": "structural",
    "transciptomics": "transcriptomics",
    "transcriptomcis": "transcriptomics",
    "transriptomics": "transcriptomics",
    "transcripomics": "transcriptomics",
    "transcriptomcs": "transcriptomics",
    "varaint": "variant",
    "varient": "variant",
    "vairant": "variant",
    "vairent": "variant",
    "worklfow": "workflow",
    "worfklow": "workflow",
    "moduel": "module",
    "moduels": "modules",
}


@dataclass(frozen=True)
class SearchScore:
    score: float
    corrected_query: str
    matched_terms: tuple[str, ...]
    reasons: tuple[str, ...]


def normalize_search_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(_WORD_RE.findall(ascii_text.lower()))


def _replace_phrase(text: str, source: str, target: str) -> str:
    pattern = re.compile(rf"(?<![a-z0-9]){re.escape(source)}(?![a-z0-9])")
    return pattern.sub(target, text)


def correct_query(query: str) -> str:
    corrected = normalize_search_text(query)
    # Phrase-level corrections first, then individual tokens.
    for source in sorted(COMMON_TYPO_CORRECTIONS, key=len, reverse=True):
        corrected = _replace_phrase(corrected, source, COMMON_TYPO_CORRECTIONS[source])
    return " ".join(corrected.split())


@lru_cache(maxsize=4096)
def damerau_levenshtein_distance(left: str, right: str) -> int:
    """Return optimal-string-alignment distance for short UI search terms."""
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    rows = len(left) + 1
    cols = len(right) + 1
    matrix = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        matrix[i][0] = i
    for j in range(cols):
        matrix[0][j] = j

    for i in range(1, rows):
        for j in range(1, cols):
            substitution = 0 if left[i - 1] == right[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,
                matrix[i][j - 1] + 1,
                matrix[i - 1][j - 1] + substitution,
            )
            if (
                i > 1
                and j > 1
                and left[i - 1] == right[j - 2]
                and left[i - 2] == right[j - 1]
            ):
                matrix[i][j] = min(matrix[i][j], matrix[i - 2][j - 2] + 1)
    return matrix[-1][-1]


def fuzzy_ratio(left: str, right: str) -> float:
    left = normalize_search_text(left)
    right = normalize_search_text(right)
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    distance = damerau_levenshtein_distance(left, right)
    return max(0.0, 1.0 - distance / max(len(left), len(right)))


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(token for token in normalize_search_text(value).split() if token)


def _expand_query(query: str) -> tuple[str, ...]:
    corrected = correct_query(query)
    terms: list[str] = [corrected]
    for alias, expansions in QUERY_ALIASES.items():
        if alias in corrected or corrected in alias:
            terms.extend(expansions)
    # Include token-level aliases (e.g. "vcf annotation").
    for token in corrected.split():
        terms.extend(QUERY_ALIASES.get(token, ()))
    return tuple(dict.fromkeys(normalize_search_text(term) for term in terms if term))


def _best_token_similarity(query_tokens: Sequence[str], target_tokens: Sequence[str]) -> float:
    if not query_tokens or not target_tokens:
        return 0.0
    scores: list[float] = []
    for query_token in query_tokens:
        best = max(fuzzy_ratio(query_token, target_token) for target_token in target_tokens)
        # Very short tokens should not create noisy fuzzy matches.
        if len(query_token) <= 2 and query_token not in target_tokens:
            best = 0.0
        scores.append(best)
    return sum(scores) / len(scores)


@lru_cache(maxsize=32768)
def _score_search_candidate_cached(
    query: str,
    *,
    title: str,
    description: str = "",
    category: str = "",
    keywords: tuple[str, ...] = (),
    key: str = "",
) -> SearchScore:
    raw_query = normalize_search_text(query)
    corrected = correct_query(query)
    if not corrected:
        return SearchScore(1.0, corrected, (), ("catalogue",))

    title_n = normalize_search_text(title)
    category_n = normalize_search_text(category)
    keyword_values = tuple(normalize_search_text(value) for value in keywords if value)
    key_n = normalize_search_text(key.replace("_", " "))
    description_n = normalize_search_text(description)
    haystack = " ".join((title_n, key_n, category_n, description_n, *keyword_values))
    target_tokens = _tokens(haystack)

    expansions = _expand_query(corrected)
    best_score = 0.0
    best_terms: tuple[str, ...] = ()
    best_reasons: tuple[str, ...] = ()

    for expanded in expansions:
        query_tokens = _tokens(expanded)
        reasons: list[str] = []
        score = 0.0

        if expanded == title_n:
            score += 12.0
            reasons.append("exact title")
        elif title_n.startswith(expanded):
            score += 9.0
            reasons.append("title prefix")
        elif expanded in title_n:
            score += 8.0
            reasons.append("title")

        if expanded == key_n or expanded in key_n:
            score += 6.0
            reasons.append("module key")
        if expanded in keyword_values:
            score += 7.0
            reasons.append("keyword")
        elif any(expanded in value for value in keyword_values):
            score += 5.0
            reasons.append("keyword phrase")
        if expanded in category_n:
            score += 3.0
            reasons.append("category")
        if expanded in description_n:
            score += 2.5
            reasons.append("description")

        query_token_set = set(query_tokens)
        target_token_set = set(target_tokens)
        exact_token_fraction = len(query_token_set & target_token_set) / max(len(query_token_set), 1)
        if exact_token_fraction:
            score += 5.0 * exact_token_fraction
            reasons.append("matching terms")

        token_fuzzy = _best_token_similarity(query_tokens, target_tokens)
        if token_fuzzy >= 0.72:
            score += 5.0 * token_fuzzy
            reasons.append("typo tolerant")

        title_fuzzy = max(fuzzy_ratio(expanded, title_n), fuzzy_ratio(corrected, title_n))
        if title_fuzzy >= 0.58:
            score += 4.0 * title_fuzzy
            reasons.append("fuzzy title")

        # A bounded phrase similarity supports multi-word transpositions while
        # preventing very broad matches from flooding the result list.
        phrase_overlap = sum(token in haystack for token in query_tokens) / max(len(query_tokens), 1)
        score += 2.0 * phrase_overlap

        # Penalize candidates with no meaningful lexical relationship.
        if token_fuzzy < 0.55 and title_fuzzy < 0.48 and expanded not in haystack:
            score *= 0.25

        if score > best_score:
            best_score = score
            best_terms = tuple(token for token in query_tokens if token in target_token_set or max((fuzzy_ratio(token, target) for target in target_tokens), default=0.0) >= 0.72)
            best_reasons = tuple(dict.fromkeys(reasons))

    matched_intents = [intent for intent in MODULE_INTENT_BOOSTS if intent in corrected]
    # Prefer the most specific phrase. For example, "metagenomics" must not be
    # overridden by the shorter substring "genomics".
    if matched_intents:
        max_specificity = max((len(intent.split()), len(intent)) for intent in matched_intents)
        matched_intents = [
            intent
            for intent in matched_intents
            if (len(intent.split()), len(intent)) == max_specificity
        ]
    for intent in matched_intents:
        ordered_keys = MODULE_INTENT_BOOSTS[intent]
        if key in ordered_keys:
            intent_rank = ordered_keys.index(key)
            # A user intent such as "sequence", "drug target" or "qPCR" should
            # place the canonical starting module ahead of specialist/secondary
            # pages that merely contain the same keyword. The boost is bounded
            # and only applies to an explicit curated intent phrase.
            best_score += max(2.0, 12.0 - 3.0 * intent_rank)
            best_reasons = (*best_reasons, "recommended starting module")

    # Explicit correction gets a small confidence boost when the raw query was
    # changed, but never overrides lexical relevance.
    if raw_query != corrected and best_score > 0:
        best_score += 0.75
        best_reasons = (*best_reasons, "corrected query")

    return SearchScore(
        score=round(best_score, 6),
        corrected_query=corrected,
        matched_terms=tuple(dict.fromkeys(best_terms)),
        reasons=tuple(dict.fromkeys(best_reasons)),
    )


def score_search_candidate(
    query: str,
    *,
    title: str,
    description: str = "",
    category: str = "",
    keywords: Iterable[str] = (),
    key: str = "",
) -> SearchScore:
    """Score a module candidate with a change-safe in-process ranking cache."""
    return _score_search_candidate_cached(
        str(query),
        title=str(title),
        description=str(description),
        category=str(category),
        keywords=tuple(str(value) for value in keywords),
        key=str(key),
    )


def clear_search_score_cache() -> None:
    _score_search_candidate_cached.cache_clear()


def suggest_query(query: str, vocabulary: Iterable[str]) -> str | None:
    corrected = correct_query(query)
    raw = normalize_search_text(query)
    if corrected and corrected != raw:
        return corrected
    if not raw:
        return None

    candidates = {normalize_search_text(value) for value in vocabulary if value}
    candidates.discard("")
    best_value = None
    best_score = 0.0
    for candidate in candidates:
        score = fuzzy_ratio(raw, candidate)
        if score > best_score:
            best_value = candidate
            best_score = score
    threshold = 0.72 if len(raw) >= 5 else 0.82
    return best_value if best_value and best_score >= threshold and best_value != raw else None


def search_quality_metrics(cases: Sequence[tuple[str, str]], resolver) -> dict[str, float | int]:
    """Evaluate typo cases without coupling tests to Streamlit.

    The 10/10 internal target is deliberately strict: every curated typo must
    return the intended module at rank 1, not merely somewhere in the catalogue.
    """
    found = 0
    top1 = 0
    top3 = 0
    reciprocal_ranks: list[float] = []
    for query, expected_key in cases:
        results = list(resolver(query))
        keys = [getattr(item, "key", str(item)) for item in results]
        if expected_key in keys:
            rank = keys.index(expected_key) + 1
            found += 1
            top1 += int(rank == 1)
            top3 += int(rank <= 3)
            reciprocal_ranks.append(1.0 / rank)
        else:
            reciprocal_ranks.append(0.0)
    total = len(cases)
    return {
        "cases": total,
        "catalogue_recall": round(found / max(total, 1), 4),
        "top1_accuracy": round(top1 / max(total, 1), 4),
        "top3_accuracy": round(top3 / max(total, 1), 4),
        "mean_reciprocal_rank": round(sum(reciprocal_ranks) / max(total, 1), 4),
        "passed": top1,
    }
