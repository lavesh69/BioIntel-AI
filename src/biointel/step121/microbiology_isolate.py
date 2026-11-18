from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class IsolateAnalysisResult:
    assembly_qc: pd.DataFrame
    taxonomic_screen: pd.DataFrame
    mlst_calls: pd.DataFrame
    gene_hits: pd.DataFrame
    contamination_flags: pd.DataFrame
    concordance: pd.DataFrame
    release_gate: dict[str, Any]
    manifest: dict[str, Any]


def parse_fasta_text(text: str) -> dict[str, str]:
    sequences: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            current = line[1:].split()[0] or f"sequence_{len(sequences) + 1}"
            sequences.setdefault(current, [])
            continue
        if current is None:
            raise ValueError("FASTA sequence encountered before a header line.")
        sequences[current].append("".join(character for character in line.upper() if character.isalpha()))
    result = {name: "".join(parts) for name, parts in sequences.items() if parts}
    if not result:
        raise ValueError("No FASTA sequences were detected.")
    return result


def _nx(lengths: list[int], fraction: float) -> tuple[int, int]:
    ordered = sorted((int(length) for length in lengths if length > 0), reverse=True)
    if not ordered:
        return 0, 0
    target = sum(ordered) * fraction
    cumulative = 0
    for index, length in enumerate(ordered, start=1):
        cumulative += length
        if cumulative >= target:
            return length, index
    return ordered[-1], len(ordered)


def assembly_qc(sequences: dict[str, str]) -> pd.DataFrame:
    lengths = [len(sequence) for sequence in sequences.values()]
    total = sum(lengths)
    n50, l50 = _nx(lengths, 0.5)
    n90, l90 = _nx(lengths, 0.9)
    bases = "".join(sequences.values()).upper()
    canonical = sum(bases.count(base) for base in "ACGT")
    gc = bases.count("G") + bases.count("C")
    ambiguous = max(len(bases) - canonical, 0)
    metrics = [
        ("contigs", len(lengths)),
        ("total_length", total),
        ("longest_contig", max(lengths) if lengths else 0),
        ("n50", n50),
        ("l50", l50),
        ("n90", n90),
        ("l90", l90),
        ("gc_percent", 100.0 * gc / canonical if canonical else np.nan),
        ("ambiguous_percent", 100.0 * ambiguous / len(bases) if bases else np.nan),
    ]
    return pd.DataFrame(metrics, columns=["metric", "value"])


def _kmers(sequence: str, k: int) -> set[str]:
    sequence = sequence.upper()
    if len(sequence) < k:
        return {sequence} if sequence else set()
    return {sequence[index : index + k] for index in range(len(sequence) - k + 1) if "N" not in sequence[index : index + k]}


def _containment(query: str, reference: str, k: int) -> tuple[float, float]:
    query_kmers = _kmers(query, k)
    reference_kmers = _kmers(reference, k)
    if not query_kmers or not reference_kmers:
        return 0.0, 0.0
    intersection = len(query_kmers & reference_kmers)
    containment = intersection / len(reference_kmers)
    jaccard = intersection / len(query_kmers | reference_kmers)
    return containment, jaccard


def screen_taxonomy(sequences: dict[str, str], references: pd.DataFrame, *, k: int = 21) -> pd.DataFrame:
    required = {"taxon", "sequence"}
    if not required.issubset(references.columns):
        raise ValueError("Taxonomy reference requires taxon and sequence columns.")
    assembly = "N".join(sequences.values())
    rows: list[dict[str, Any]] = []
    for row in references.itertuples(index=False):
        containment, jaccard = _containment(assembly, str(row.sequence), k)
        rows.append(
            {
                "taxon": str(row.taxon),
                "k": k,
                "reference_length": len(str(row.sequence)),
                "kmer_containment": containment,
                "kmer_jaccard": jaccard,
                "screen_status": "candidate_match" if containment >= 0.50 else "weak_or_no_match",
            }
        )
    return pd.DataFrame(rows).sort_values(["kmer_containment", "kmer_jaccard"], ascending=False).reset_index(drop=True)


def call_mlst(
    sequences: dict[str, str],
    allele_catalog: pd.DataFrame,
    profiles: pd.DataFrame | None = None,
    *,
    k: int = 15,
    minimum_containment: float = 0.90,
) -> pd.DataFrame:
    required = {"locus", "allele", "sequence"}
    if not required.issubset(allele_catalog.columns):
        raise ValueError("MLST allele catalog requires locus, allele and sequence columns.")
    assembly = "N".join(sequences.values())
    calls: list[dict[str, Any]] = []
    for locus, group in allele_catalog.groupby("locus"):
        best: dict[str, Any] | None = None
        for row in group.itertuples(index=False):
            containment, jaccard = _containment(assembly, str(row.sequence), k)
            candidate = {
                "locus": str(locus),
                "allele": str(row.allele),
                "containment": containment,
                "jaccard": jaccard,
                "call_status": "called" if containment >= minimum_containment else "low_confidence",
            }
            if best is None or (candidate["containment"], candidate["jaccard"]) > (best["containment"], best["jaccard"]):
                best = candidate
        if best is not None:
            calls.append(best)
    call_frame = pd.DataFrame(calls)
    if profiles is not None and not profiles.empty and "sequence_type" in profiles.columns and not call_frame.empty:
        allele_map = {row.locus: str(row.allele) for row in call_frame.itertuples(index=False) if row.call_status == "called"}
        matches: list[tuple[str, int, int]] = []
        locus_columns = [column for column in profiles.columns if column != "sequence_type"]
        for profile in profiles.itertuples(index=False):
            profile_dict = profile._asdict()
            compared = sum(locus in allele_map for locus in locus_columns)
            matched = sum(allele_map.get(locus) == str(profile_dict.get(locus)) for locus in locus_columns if locus in allele_map)
            matches.append((str(profile_dict["sequence_type"]), matched, compared))
        if matches:
            best_st, matched, compared = max(matches, key=lambda item: (item[1], item[2]))
            call_frame["sequence_type"] = best_st if compared and matched == compared else "unresolved"
            call_frame["profile_loci_matched"] = matched
            call_frame["profile_loci_compared"] = compared
    return call_frame


def screen_gene_catalog(
    sequences: dict[str, str],
    catalog: pd.DataFrame,
    *,
    k: int = 15,
    minimum_containment: float = 0.80,
) -> pd.DataFrame:
    required = {"gene", "sequence"}
    if not required.issubset(catalog.columns):
        raise ValueError("Gene catalog requires gene and sequence columns.")
    assembly = "N".join(sequences.values())
    rows: list[dict[str, Any]] = []
    for row in catalog.itertuples(index=False):
        containment, jaccard = _containment(assembly, str(row.sequence), k)
        record = row._asdict()
        rows.append(
            {
                "gene": str(record["gene"]),
                "category": str(record.get("category", "unclassified")),
                "phenotype": str(record.get("phenotype", "")),
                "database_release": str(record.get("database_release", "unversioned")),
                "containment": containment,
                "jaccard": jaccard,
                "present": containment >= minimum_containment,
                "status": "candidate_gene_hit" if containment >= minimum_containment else "not_detected",
            }
        )
    return pd.DataFrame(rows).sort_values(["present", "containment"], ascending=False).reset_index(drop=True)


def phenotype_genotype_concordance(
    phenotype: pd.DataFrame | None,
    gene_hits: pd.DataFrame,
) -> pd.DataFrame:
    if phenotype is None or phenotype.empty:
        return pd.DataFrame()
    required = {"drug", "phenotype"}
    if not required.issubset(phenotype.columns):
        raise ValueError("Phenotype table requires drug and phenotype columns.")
    present = gene_hits[gene_hits["present"]].copy()
    rows: list[dict[str, Any]] = []
    for row in phenotype.itertuples(index=False):
        drug = str(row.drug)
        observed = str(row.phenotype).strip().lower()
        related = present[present["phenotype"].str.lower().str.contains(drug.lower(), regex=False, na=False)]
        predicted_resistant = not related.empty
        observed_resistant = observed in {"r", "resistant", "non-susceptible", "nonsusceptible"}
        concordant = predicted_resistant == observed_resistant
        rows.append(
            {
                "drug": drug,
                "observed_phenotype": observed,
                "predicted_resistant_from_catalog": predicted_resistant,
                "supporting_genes": ", ".join(sorted(related["gene"].astype(str).unique())),
                "concordant": concordant,
                "interpretation": "concordant" if concordant else "discordant_requires_review",
            }
        )
    return pd.DataFrame(rows)


def _contamination_flags(sequences: dict[str, str], taxonomy: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    contig_gc = []
    for name, sequence in sequences.items():
        canonical = sum(sequence.count(base) for base in "ACGT")
        gc = 100.0 * (sequence.count("G") + sequence.count("C")) / canonical if canonical else np.nan
        contig_gc.append((name, len(sequence), gc))
    gc_values = np.array([value for _, _, value in contig_gc if np.isfinite(value)], dtype=float)
    median = float(np.median(gc_values)) if len(gc_values) else np.nan
    mad = float(np.median(np.abs(gc_values - median))) if len(gc_values) else np.nan
    threshold = max(10.0, 3.0 * 1.4826 * mad) if np.isfinite(mad) else 10.0
    for name, length, gc in contig_gc:
        if np.isfinite(gc) and np.isfinite(median) and abs(gc - median) > threshold and length >= 500:
            rows.append(
                {
                    "flag_type": "gc_outlier_contig",
                    "entity": name,
                    "severity": "warning",
                    "detail": f"GC {gc:.2f}% differs from assembly median {median:.2f}%.",
                }
            )
    if not taxonomy.empty:
        strong = taxonomy[taxonomy["kmer_containment"] >= 0.50]
        if len(strong) > 1:
            rows.append(
                {
                    "flag_type": "multiple_taxon_signals",
                    "entity": ", ".join(strong["taxon"].astype(str).head(5)),
                    "severity": "warning",
                    "detail": "More than one reference taxon has strong k-mer containment; mixed isolate or closely related references require confirmation.",
                }
            )
    if not rows:
        rows.append(
            {
                "flag_type": "no_heuristic_flag",
                "entity": "assembly",
                "severity": "pass",
                "detail": "No GC-outlier or multiple-reference heuristic flag was detected.",
            }
        )
    return pd.DataFrame(rows)


def analyse_isolate(
    sequences: dict[str, str],
    *,
    taxonomy_references: pd.DataFrame,
    allele_catalog: pd.DataFrame,
    mlst_profiles: pd.DataFrame | None,
    gene_catalog: pd.DataFrame,
    phenotype: pd.DataFrame | None = None,
) -> IsolateAnalysisResult:
    qc = assembly_qc(sequences)
    taxonomy = screen_taxonomy(sequences, taxonomy_references)
    mlst = call_mlst(sequences, allele_catalog, mlst_profiles)
    genes = screen_gene_catalog(sequences, gene_catalog)
    contamination = _contamination_flags(sequences, taxonomy)
    concordance = phenotype_genotype_concordance(phenotype, genes)
    blockers: list[str] = []
    top_containment = float(taxonomy["kmer_containment"].max()) if not taxonomy.empty else 0.0
    if top_containment < 0.50:
        blockers.append("No strong candidate taxonomy reference match")
    if mlst.empty or (mlst["call_status"] != "called").any():
        blockers.append("One or more MLST loci are unresolved or low confidence")
    if not concordance.empty and (~concordance["concordant"]).any():
        blockers.append("Phenotype-genotype discordance requires manual review")
    if (contamination["severity"] == "warning").any():
        blockers.append("Contamination/mixed-isolate heuristic flags are present")
    blockers.extend(
        [
            "K-mer screens require confirmation with validated taxonomic/AMR/VF tools and pinned databases",
            "No clinical susceptibility claim is permitted without validated AST and laboratory review",
        ]
    )
    digest = "".join(f">{name}\n{sequence}\n" for name, sequence in sequences.items()).encode("utf-8")
    manifest = {
        "schema": "biointel.step121.microbiology_isolate.v1",
        "contigs": len(sequences),
        "bases": sum(len(sequence) for sequence in sequences.values()),
        "input_sha256": sha256(digest).hexdigest(),
        "taxonomy_reference_rows": len(taxonomy_references),
        "allele_rows": len(allele_catalog),
        "gene_catalog_rows": len(gene_catalog),
        "confirmatory_release_ready": False,
    }
    return IsolateAnalysisResult(
        assembly_qc=qc,
        taxonomic_screen=taxonomy,
        mlst_calls=mlst,
        gene_hits=genes,
        contamination_flags=contamination,
        concordance=concordance,
        release_gate={
            "rapid_screen_ready": True,
            "confirmatory_release_ready": False,
            "blockers": blockers,
            "boundary": "This is a bounded k-mer/isolate screen, not a replacement for validated clinical microbiology pipelines.",
        },
        manifest=manifest,
    )
