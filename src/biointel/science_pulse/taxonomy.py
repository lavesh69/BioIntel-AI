from __future__ import annotations

import re
from collections import defaultdict

from .models import PulseRecord, list_value


TOPIC_RULES: dict[str, tuple[str, ...]] = {
    "Genomics": ("genom", "variant", "sequenc", "transcriptom", "epigen"),
    "Gene editing": ("crispr", "cas9", "gene edit", "base edit", "prime edit"),
    "Oncology": ("cancer", "tumor", "tumour", "oncolog", "carcinoma", "leukemia"),
    "Infectious disease": ("virus", "viral", "bacter", "pathogen", "infection", "vaccine"),
    "Neuroscience": ("brain", "neuro", "cognition", "alzheimer", "parkinson"),
    "Immunology": ("immune", "antibody", "cytokine", "t cell", "b cell"),
    "Cell biology": ("cell", "organelle", "mitochond", "stem cell"),
    "Protein science": ("protein", "proteom", "enzyme", "peptide", "antibody"),
    "Drug discovery": ("drug", "compound", "therapeut", "pharmac", "molecule"),
    "Clinical research": ("clinical trial", "patient", "cohort", "randomized", "placebo"),
    "Bioprocess": ("bioprocess", "fermentation", "bioreactor", "downstream process"),
    "Synthetic biology": ("synthetic biology", "engineered organism", "biosensor"),
    "Agricultural biotech": ("crop", "plant", "agricultur", "livestock"),
    "Diagnostics": ("diagnostic", "biomarker", "assay", "screening"),
    "AI for biology": ("machine learning", "artificial intelligence", "deep learning", "foundation model"),
}
TOPIC_RULES.update({
    "General Biology": ("biology", "biological", "life science"),
    "Molecular Biology": ("molecular", "dna", "rna", "transcription", "translation"),
    "Genetics": ("genetic", "inheritance", "allele", "mutation"),
    "Epigenomics": ("epigen", "methylation", "chromatin"),
    "Transcriptomics": ("transcriptom", "rna-seq", "gene expression"),
    "Proteomics": ("proteom", "mass spectrometry", "protein abundance"),
    "Metabolomics": ("metabolom", "metabolite", "lipidom"),
    "Bioinformatics": ("bioinformatic", "sequence analysis", "pipeline"),
    "Computational Biology": ("computational biology", "simulation", "in silico"),
    "Biotechnology": ("biotech", "biotechnology", "biomanufactur"),
    "Systems Biology": ("systems biology", "network biology", "pathway model"),
    "Structural Biology": ("structural biology", "cryo-em", "crystallograph", "protein structure"),
    "Microbiology": ("microbiol", "microbe", "bacter", "fung"),
    "Virology": ("virolog", "virus", "viral", "phage"),
    "Cancer Biology": ("cancer", "tumor", "tumour", "oncolog"),
    "Stem Cells": ("stem cell", "pluripotent", "organoid"),
    "Regenerative Medicine": ("regenerative", "tissue repair", "cell therapy"),
    "Pharmacology": ("pharmacolog", "pharmacokinetic", "drug response"),
    "Precision Medicine": ("precision medicine", "personalized medicine", "stratified medicine"),
    "Epidemiology": ("epidemiolog", "incidence", "prevalence", "cohort"),
    "Public Health Research": ("public health", "population health", "health equity"),
    "Ecology": ("ecolog", "ecosystem", "biodiversity"),
    "Evolution": ("evolution", "phylogen", "selection pressure"),
    "Environmental Biology": ("environmental", "ecotoxic", "bioremediation"),
    "Marine Biology": ("marine", "ocean", "coral", "aquatic"),
    "Plant Science": ("plant", "arabidopsis", "botany", "photosynthesis"),
    "Food Biotechnology": ("food biotech", "food safety", "cultivated meat"),
    "Industrial Biotechnology": ("industrial biotech", "biorefinery", "fermentation"),
    "Biomedical Engineering": ("biomedical engineering", "biomaterial", "medical device"),
    "Scientific Policy": ("science policy", "regulation", "research policy"),
    "Research Funding": ("research funding", "grant", "funding call"),
    "Scientific Conferences": ("conference", "symposium", "scientific meeting"),
})

DISEASE_TERMS = (
    "cancer",
    "diabetes",
    "alzheimer",
    "parkinson",
    "malaria",
    "tuberculosis",
    "influenza",
    "covid-19",
    "hiv",
    "hepatitis",
)
ORGANISM_TERMS = (
    "human",
    "mouse",
    "mice",
    "rat",
    "zebrafish",
    "drosophila",
    "arabidopsis",
    "escherichia coli",
    "sars-cov-2",
)
TECH_TERMS = (
    "crispr",
    "single-cell sequencing",
    "rna-seq",
    "mass spectrometry",
    "flow cytometry",
    "microscopy",
    "machine learning",
    "pcr",
)
GENE_PATTERN = re.compile(r"\b(?:[A-Z][A-Z0-9-]{1,9}|[A-Z][a-z]{1,5}\d{1,3})\b")


def classify(record: PulseRecord) -> PulseRecord:
    corpus = f"{record.title} {record.abstract} {' '.join(record.keywords)}".casefold()
    if "retracted:" in corpus or "retraction of" in corpus or "retraction notice" in corpus:
        record.trust_state = "retracted"
        record.content_type = "retraction"
    elif "correction:" in corpus or "correction to" in corpus or "corrigendum" in corpus:
        record.trust_state = "corrected"
        record.content_type = "correction"
    elif "expression of concern" in corpus:
        record.trust_state = "expression_of_concern"
    scores: dict[str, int] = defaultdict(int)
    for topic, needles in TOPIC_RULES.items():
        scores[topic] = sum(corpus.count(needle) for needle in needles)
    ranked = sorted((score, topic) for topic, score in scores.items() if score)
    inferred = [topic for _, topic in ranked[-4:]][::-1]
    record.categories = list_value([*record.categories, *inferred])
    record.diseases = list_value(
        [*record.diseases, *[term for term in DISEASE_TERMS if term in corpus]]
    )
    record.organisms = list_value(
        [*record.organisms, *[term for term in ORGANISM_TERMS if term in corpus]]
    )
    record.technologies = list_value(
        [*record.technologies, *[term for term in TECH_TERMS if term in corpus]]
    )
    genes = [
        match.group(0)
        for match in GENE_PATTERN.finditer(f"{record.title} {record.abstract}")
        if match.group(0) not in {"DNA", "RNA", "COVID", "SARS", "PCR", "AI"}
    ]
    record.genes = list_value([*record.genes, *genes[:30]])
    record.entities = list_value(
        [*record.entities, *record.diseases, *record.organisms, *record.technologies, *record.genes]
    )
    evidence = sum(bool(value) for value in (record.doi, record.pmid, record.abstract, record.authors))
    record.confidence = min(0.98, 0.45 + evidence * 0.1)
    record.quality = min(0.98, 0.35 + evidence * 0.12 + bool(record.journal) * 0.08)
    record.relevance = min(0.98, 0.45 + min(4, len(record.categories)) * 0.1)
    return record
