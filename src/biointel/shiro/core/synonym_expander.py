"""
Shiro AI — Scientific Synonym & Acronym Expander
Provides offline biomedical acronym resolution and synonym mapping for RAG queries.
"""
from __future__ import annotations

import re
from typing import Sequence

# Comprehensive local scientific acronyms and domain synonyms map
SCIENTIFIC_SYNONYMS: dict[str, tuple[str, ...]] = {
    "tp53": ("p53", "tumor protein p53", "cellular tumor antigen p53"),
    "egfr": ("erbb1", "her1", "epidermal growth factor receptor"),
    "brca1": ("breast cancer 1", "ring finger protein 53", "rnf53"),
    "brca2": ("breast cancer 2", "fanconi anemia group d1", "fancd1"),
    "kras": ("kirsten rat sarcoma", "k-ras", "v-kras2"),
    "rna-seq": ("rnaseq", "transcriptomics", "rna sequencing", "differential expression"),
    "wes": ("whole exome sequencing", "exome sequencing"),
    "wgs": ("whole genome sequencing", "genome sequencing"),
    "vcf": ("variant call format", "genomic variant"),
    "fasta": ("sequence format", "nucleotide sequence", "protein sequence"),
    "fastq": ("sequencing read", "quality score", "base call"),
    "ic50": ("half maximal inhibitory concentration", "inhibition potency"),
    "fdr": ("false discovery rate", "benjamini-hochberg", "adjusted p-value"),
}


class ScientificQueryExpander:
    """Offline query expander for biomedical and clinical research terms."""

    def __init__(self, custom_dictionary: dict[str, tuple[str, ...]] | None = None) -> None:
        self.dictionary = {**SCIENTIFIC_SYNONYMS, **(custom_dictionary or {})}

    def expand_query(self, query: str) -> str:
        """Expands query terms with relevant scientific synonyms without diluting original intent."""
        tokens = re.findall(r"[^\W_]+", query.casefold())
        expanded_terms: list[str] = [query]
        for token in tokens:
            if token in self.dictionary:
                synonyms = self.dictionary[token]
                expanded_terms.extend(synonyms[:2])
        return " ".join(dict.fromkeys(expanded_terms))

    def extract_keywords(self, text: str) -> list[str]:
        """Extracts key scientific entities and identifiers from text."""
        raw_tokens = re.findall(r"[A-Za-z0-9_.-]+", text)
        scientific = [
            t for t in raw_tokens
            if len(t) >= 2 and (any(c.isdigit() for c in t) or t.isupper() or t.casefold() in self.dictionary)
        ]
        return list(dict.fromkeys(scientific))
