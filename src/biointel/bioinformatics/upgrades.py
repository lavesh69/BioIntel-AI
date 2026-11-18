from __future__ import annotations

from collections import Counter
from hashlib import blake2b, sha256
import json
import math
import re
from typing import Any, Iterable

import numpy as np
import pandas as pd

DNA = set("ACGTNRYKMSWBDHV")
RNA = set("ACGUNRYKMSWBDHV")
PROTEIN = set("ABCDEFGHIKLMNPQRSTVWXYZ*OUJ")
COMMON_CONTAMINANTS = {
    "Illumina adapter": "AGATCGGAAGAG",
    "Nextera transposase": "CTGTCTCTTATA",
    "T7 promoter": "TAATACGACTCACTATAGGG",
    "M13 forward": "GTAAAACGACGGCCAGT",
    "M13 reverse": "CAGGAAACAGCTATGAC",
    "Poly-A 12": "AAAAAAAAAAAA",
}
HYDROPATHY = {
    "I": 4.5, "V": 4.2, "L": 3.8, "F": 2.8, "C": 2.5, "M": 1.9, "A": 1.8,
    "G": -0.4, "T": -0.7, "S": -0.8, "W": -0.9, "Y": -1.3, "P": -1.6, "H": -3.2,
    "E": -3.5, "Q": -3.5, "D": -3.5, "N": -3.5, "K": -3.9, "R": -4.5,
}


def _clean_sequence(sequence: str) -> str:
    return re.sub(r"[^A-Za-z*]", "", sequence).upper()


def parse_fasta(text: str) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    name = "sequence_1"
    chunks: list[str] = []
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if chunks:
                records.append((name, _clean_sequence("".join(chunks))))
            name = line[1:].strip() or f"sequence_{len(records) + 1}"
            chunks = []
        else:
            chunks.append(line)
    if chunks:
        records.append((name, _clean_sequence("".join(chunks))))
    if not records and _clean_sequence(text):
        records.append(("sequence_1", _clean_sequence(text)))
    return [(name, sequence) for name, sequence in records if sequence]


def detect_sequence_type(sequence: str) -> str:
    alphabet = set(sequence.upper())
    if alphabet <= DNA:
        return "DNA"
    if alphabet <= RNA and "U" in alphabet:
        return "RNA"
    if alphabet <= PROTEIN:
        return "Protein"
    return "Mixed/invalid"


def _entropy(sequence: str) -> float:
    if not sequence:
        return 0.0
    counts = Counter(sequence)
    length = len(sequence)
    return float(-sum((count / length) * math.log2(count / length) for count in counts.values()))


def _longest_overlap(sequence: str, maximum: int = 200) -> int:
    upper = min(maximum, len(sequence) // 2)
    for length in range(upper, 7, -1):
        if sequence[:length] == sequence[-length:]:
            return length
    return 0


def _orf_count(sequence: str, minimum_aa: int = 20) -> int:
    if detect_sequence_type(sequence) not in {"DNA", "RNA"}:
        return 0
    dna = sequence.replace("U", "T")
    stops = {"TAA", "TAG", "TGA"}
    count = 0
    for frame in range(3):
        start = None
        for index in range(frame, len(dna) - 2, 3):
            codon = dna[index:index + 3]
            if start is None and codon == "ATG":
                start = index
            elif start is not None and codon in stops:
                if (index - start) // 3 >= minimum_aa:
                    count += 1
                start = None
    return count


def batch_sequence_profile(text: str, *, motifs: Iterable[str] = (), circular: bool = False) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    motif_list = [str(item).strip().upper() for item in motifs if str(item).strip()]
    for name, sequence in parse_fasta(text):
        seq_type = detect_sequence_type(sequence)
        valid = seq_type != "Mixed/invalid"
        length = len(sequence)
        gc = (sequence.count("G") + sequence.count("C")) / length if length and seq_type in {"DNA", "RNA"} else np.nan
        ambiguity = sum(base not in {"A", "C", "G", "T", "U"} for base in sequence) / length if length else 0.0
        contaminant_hits = {label: sequence.count(pattern) for label, pattern in COMMON_CONTAMINANTS.items() if pattern in sequence}
        motif_hits = {motif: sequence.count(motif) for motif in motif_list}
        overlap = _longest_overlap(sequence) if circular else 0
        rows.append({
            "record_id": name,
            "sequence_type": seq_type,
            "valid_alphabet": valid,
            "length": length,
            "gc_fraction": gc,
            "ambiguity_fraction": ambiguity,
            "sequence_entropy": _entropy(sequence),
            "orf_count_forward": _orf_count(sequence),
            "circular_overlap_bp": overlap,
            "circular_candidate": bool(overlap >= 12),
            "contaminant_pattern_count": int(sum(contaminant_hits.values())),
            "contaminant_patterns": "; ".join(f"{key}:{value}" for key, value in contaminant_hits.items()),
            "motif_hit_count": int(sum(motif_hits.values())),
            "motif_hits": "; ".join(f"{key}:{value}" for key, value in motif_hits.items()),
        })
    return pd.DataFrame(rows)


def _parse_fastq_with_diagnostics(
    text: str,
    maximum_reads: int,
) -> tuple[list[tuple[str, str, str]], dict[str, Any]]:
    if int(maximum_reads) < 1:
        raise ValueError("Maximum reads must be at least one.")
    lines = [line.rstrip("\r") for line in str(text).splitlines()]
    reads: list[tuple[str, str, str]] = []
    malformed = 0
    scanned_records = 0
    index = 0
    truncated = False
    while index < len(lines):
        # Permit blank separators between records without shifting the four-line
        # record frame. Blank lines inside a record remain invalid.
        while index < len(lines) and not lines[index].strip():
            index += 1
        if index >= len(lines):
            break
        if len(reads) >= maximum_reads:
            truncated = any(line.strip() for line in lines[index:])
            break
        if index + 3 >= len(lines):
            malformed += 1
            break
        header, sequence, plus, quality = lines[index:index + 4]
        scanned_records += 1
        if not header.startswith("@") or not plus.startswith("+") or len(sequence) != len(quality):
            malformed += 1
            index += 4
            continue
        identifier = header[1:].split()[0] if header[1:].split() else f"read_{scanned_records}"
        reads.append((identifier, sequence.upper(), quality))
        index += 4
    return reads, {
        "records_scanned": scanned_records,
        "malformed_records": malformed,
        "truncated_to_maximum_reads": truncated,
    }


def parse_fastq(text: str, maximum_reads: int = 100_000) -> list[tuple[str, str, str]]:
    reads, _ = _parse_fastq_with_diagnostics(text, maximum_reads)
    return reads


def extended_fastq_qc(
    text: str,
    *,
    maximum_reads: int = 100_000,
    phred_offset: int = 33,
    adapter_patterns: Iterable[str] = ("AGATCGGAAGAG",),
    kmer_size: int = 5,
    maximum_distinct_kmers: int = 200_000,
    maximum_cycle_length: int = 100_000,
) -> dict[str, Any]:
    if phred_offset not in {33, 64}:
        raise ValueError("Phred offset must be 33 or 64.")
    if not 1 <= int(kmer_size) <= 15:
        raise ValueError("K-mer size must be between 1 and 15.")
    if int(maximum_distinct_kmers) < 1:
        raise ValueError("Maximum distinct k-mers must be positive.")
    if int(maximum_cycle_length) < 1:
        raise ValueError("Maximum cycle length must be positive.")
    reads, parse_diagnostics = _parse_fastq_with_diagnostics(text, maximum_reads)
    if not reads:
        raise ValueError("No valid FASTQ records were detected.")
    observed_maximum_cycle = max(len(sequence) for _, sequence, _ in reads)
    maximum_cycle = min(observed_maximum_cycle, int(maximum_cycle_length))
    quality_sum = np.zeros(maximum_cycle, dtype=float)
    quality_count = np.zeros(maximum_cycle, dtype=int)
    base_counts = {base: np.zeros(maximum_cycle, dtype=int) for base in "ACGTN"}
    lengths: list[int] = []
    gc_values: list[float] = []
    sequence_hashes: set[bytes] = set()
    adapter_hits = 0
    kmers: Counter[str] = Counter()
    kmer_capacity_reached = False
    invalid_quality_characters = 0
    cycle_truncated_reads = 0
    adapters = [item.upper() for item in adapter_patterns if item]
    for _, sequence, quality in reads:
        sequence_hashes.add(blake2b(sequence.encode("ascii", errors="ignore"), digest_size=8).digest())
        lengths.append(len(sequence))
        gc_values.append((sequence.count("G") + sequence.count("C")) / max(len(sequence), 1))
        if any(adapter in sequence for adapter in adapters):
            adapter_hits += 1
        if len(sequence) > maximum_cycle:
            cycle_truncated_reads += 1
        for position, (base, q_char) in enumerate(zip(sequence[:maximum_cycle], quality[:maximum_cycle])):
            raw_quality = ord(q_char) - phred_offset
            if raw_quality < 0:
                invalid_quality_characters += 1
            quality_sum[position] += max(0, raw_quality)
            quality_count[position] += 1
            base_counts.get(base, base_counts["N"])[position] += 1
        for position in range(0, max(0, len(sequence) - kmer_size + 1)):
            kmer = sequence[position:position + kmer_size]
            if kmer in kmers or len(kmers) < maximum_distinct_kmers:
                kmers[kmer] += 1
            else:
                kmer_capacity_reached = True
    duplicate_rate = 1 - len(sequence_hashes) / len(reads)
    cycle_rows: list[dict[str, Any]] = []
    for position in range(maximum_cycle):
        denominator = max(quality_count[position], 1)
        row = {
            "cycle": position + 1,
            "mean_quality": quality_sum[position] / denominator,
            "reads_at_cycle": int(quality_count[position]),
        }
        for base in "ACGTN":
            row[f"{base}_fraction"] = base_counts[base][position] / denominator
        cycle_rows.append(row)
    length_frame = pd.Series(lengths)
    summary = {
        "reads_profiled": len(reads),
        "mean_length": float(length_frame.mean()),
        "median_length": float(length_frame.median()),
        "minimum_length": int(length_frame.min()),
        "maximum_length": int(length_frame.max()),
        "mean_gc_fraction": float(np.mean(gc_values)),
        "duplicate_read_fraction": float(duplicate_rate),
        "adapter_read_fraction": adapter_hits / len(reads),
        "mean_quality": float(sum(quality_sum) / max(sum(quality_count), 1)),
        "phred_offset": phred_offset,
        "records_scanned": int(parse_diagnostics["records_scanned"]),
        "malformed_records": int(parse_diagnostics["malformed_records"]),
        "truncated_to_maximum_reads": bool(parse_diagnostics["truncated_to_maximum_reads"]),
        "observed_maximum_cycle": int(observed_maximum_cycle),
        "profiled_maximum_cycle": int(maximum_cycle),
        "cycle_truncated_reads": int(cycle_truncated_reads),
        "invalid_quality_characters": int(invalid_quality_characters),
        "kmer_capacity_reached": bool(kmer_capacity_reached),
        "maximum_distinct_kmers": int(maximum_distinct_kmers),
    }
    return {
        "summary": summary,
        "per_cycle": pd.DataFrame(cycle_rows),
        "top_kmers": pd.DataFrame(kmers.most_common(30), columns=["kmer", "count"]),
        "lengths": pd.DataFrame({"read_length": lengths, "gc_fraction": gc_values}),
    }


def _variant_type(ref: str, alt: str) -> str:
    if alt.startswith("<") and alt.endswith(">"):
        return "Structural"
    if "[" in alt or "]" in alt:
        return "Breakend"
    if len(ref) == 1 and len(alt) == 1:
        return "SNV"
    if len(ref) < len(alt):
        return "Insertion"
    if len(ref) > len(alt):
        return "Deletion"
    return "Complex"


def vcf_quality_summary(text: str, *, maximum_variants: int = 500_000) -> dict[str, Any]:
    if int(maximum_variants) < 1:
        raise ValueError("Maximum variants must be at least one.")
    rows: list[dict[str, Any]] = []
    sample_names: list[str] = []
    malformed_records = 0
    truncated = False
    for line in str(text).splitlines():
        if line.startswith("#CHROM"):
            columns = line.lstrip("#").split("\t")
            sample_names = columns[9:]
            continue
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) < 8:
            malformed_records += 1
            continue
        chrom, pos, identifier, ref, alt, qual, filt, info = fields[:8]
        try:
            position = int(pos)
        except (TypeError, ValueError):
            malformed_records += 1
            continue
        if position < 1 or not ref or not alt:
            malformed_records += 1
            continue
        format_keys = fields[8].split(":") if len(fields) > 8 else []
        genotypes = fields[9:] if len(fields) > 9 else []
        for allele_index, alt_allele in enumerate(alt.split(","), start=1):
            if len(rows) >= maximum_variants:
                truncated = True
                break
            row: dict[str, Any] = {
                "chrom": chrom,
                "position": position,
                "id": identifier,
                "ref": ref,
                "alt": alt_allele,
                "qual": pd.to_numeric(qual, errors="coerce"),
                "filter": filt,
                "variant_type": _variant_type(ref, alt_allele),
                "info": info,
            }
            gt_index = format_keys.index("GT") if "GT" in format_keys else None
            if gt_index is not None:
                gt_values = [item.split(":")[gt_index] for item in genotypes if len(item.split(":")) > gt_index]
                parsed = [re.split(r"[/|]", value) for value in gt_values]
                called = [alleles for alleles in parsed if alleles and all(item != "." for item in alleles)]
                allele_label = str(allele_index)
                row["called_samples"] = len(called)
                row["alternate_carrier_samples"] = sum(allele_label in alleles for alleles in called)
                row["heterozygous_samples"] = sum(
                    allele_label in alleles and len(set(alleles)) > 1 for alleles in called
                )
                row["alternate_homozygous_samples"] = sum(
                    bool(alleles) and all(item == allele_label for item in alleles) for alleles in called
                )
            rows.append(row)
        if truncated:
            break
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("No variant records were detected.")
    snvs = frame[frame["variant_type"] == "SNV"]
    transitions = {("A", "G"), ("G", "A"), ("C", "T"), ("T", "C")}
    ti = sum((row.ref, row.alt) in transitions for row in snvs.itertuples(index=False))
    tv = max(len(snvs) - ti, 0)
    mean_quality = frame["qual"].mean(skipna=True)
    summary = {
        "variants_loaded": len(frame),
        "samples": len(sample_names),
        "pass_fraction": float((frame["filter"].isin(["PASS", "."])).mean()),
        "mean_quality": float(mean_quality) if pd.notna(mean_quality) else None,
        "snv_count": int((frame["variant_type"] == "SNV").sum()),
        "indel_count": int(frame["variant_type"].isin(["Insertion", "Deletion"]).sum()),
        "transition_count": int(ti),
        "transversion_count": int(tv),
        "ti_tv_ratio": float(ti / tv) if tv else None,
        "malformed_records_skipped": int(malformed_records),
        "truncated": bool(truncated),
    }
    chromosome = frame.groupby("chrom", as_index=False).agg(variants=("position", "count"), minimum_position=("position", "min"), maximum_position=("position", "max"))
    types = frame.groupby("variant_type", as_index=False).size().rename(columns={"size": "count"})
    return {"summary": summary, "variants": frame, "chromosome_summary": chromosome, "variant_types": types}


def build_transcriptomics_design(
    metadata: pd.DataFrame,
    *,
    sample_column: str,
    group_column: str,
    reference_group: str,
    batch_column: str | None = None,
    covariates: Iterable[str] = (),
) -> dict[str, Any]:
    required = [sample_column, group_column]
    missing = [column for column in required if column not in metadata.columns]
    if missing:
        raise ValueError(f"Missing required metadata columns: {missing}")
    if metadata[sample_column].astype(str).duplicated().any():
        raise ValueError("Sample identifiers must be unique.")
    if metadata.empty:
        raise ValueError("Sample metadata is empty.")
    if metadata[sample_column].isna().any() or metadata[sample_column].astype(str).str.strip().eq("").any():
        raise ValueError("Sample identifiers cannot be missing or blank.")
    if metadata[group_column].isna().any() or metadata[group_column].astype(str).str.strip().eq("").any():
        raise ValueError("Group assignments cannot be missing or blank.")
    if reference_group not in set(metadata[group_column].astype(str)):
        raise ValueError("Reference group is not present in the metadata.")
    if metadata[group_column].astype(str).nunique() < 2:
        raise ValueError("At least two study groups are required.")
    if batch_column and batch_column not in metadata.columns:
        raise ValueError(f"Batch column is missing: {batch_column}")
    missing_covariates = [column for column in covariates if column not in metadata.columns]
    if missing_covariates:
        raise ValueError(f"Covariate columns are missing: {missing_covariates}")
    columns = [sample_column, group_column]
    if batch_column and batch_column in metadata.columns:
        columns.append(batch_column)
    columns.extend(column for column in covariates if column in metadata.columns and column not in columns)
    design = metadata[columns].copy()
    design[group_column] = pd.Categorical(design[group_column].astype(str), categories=[reference_group] + sorted(set(design[group_column].astype(str)) - {reference_group}))
    terms = [f"C(Q({group_column!r}), Treatment(reference={reference_group!r}))"]
    if batch_column:
        terms.append(f"C(Q({batch_column!r}))")
    terms.extend(f"Q({str(column)!r})" for column in covariates if column in design.columns)
    formula = "~ " + " + ".join(terms)
    balance = design.groupby([group_column] + ([batch_column] if batch_column else []), observed=False).size().reset_index(name="samples")
    warnings: list[str] = []
    group_counts = design[group_column].value_counts()
    if group_counts.min() < 3:
        warnings.append("At least one group contains fewer than three samples.")
    if batch_column and pd.crosstab(design[group_column], design[batch_column]).eq(0).any().any():
        warnings.append("Group and batch are partially confounded.")
    for column in covariates:
        if design[column].nunique(dropna=False) <= 1:
            warnings.append(f"Covariate {column!r} is constant and will not be informative.")
    return {
        "design_matrix": design,
        "balance": balance,
        "formula": formula,
        "reference_group": reference_group,
        "warnings": warnings,
    }


def protein_feature_track(sequence: str, *, window: int = 19) -> pd.DataFrame:
    protein = _clean_sequence(sequence)
    # In a protein-specific workflow, short peptides can consist entirely of
    # letters that are also valid IUPAC nucleotide ambiguity codes (for example
    # ``MKWVT``). Alphabet membership is therefore safer than the generic
    # sequence-type heuristic here.
    if not protein or not set(protein) <= PROTEIN:
        raise ValueError("A valid protein sequence is required.")
    values = np.array([HYDROPATHY.get(residue, 0.0) for residue in protein], dtype=float)
    requested_window = max(1, int(window))
    effective_window = min(requested_window, len(protein))
    kernel = np.ones(effective_window, dtype=float) / effective_window
    hydropathy = np.convolve(values, kernel, mode="same")
    entropy = []
    radius = max(2, int(window) // 2)
    for index in range(len(protein)):
        segment = protein[max(0, index - radius):min(len(protein), index + radius + 1)]
        entropy.append(_entropy(segment))
    track = pd.DataFrame({
        "position": np.arange(1, len(protein) + 1),
        "residue": list(protein),
        "hydropathy": hydropathy,
        "local_entropy": entropy,
    })
    track["transmembrane_candidate"] = track["hydropathy"] >= 1.6
    track["low_complexity_candidate"] = track["local_entropy"] <= 2.2
    track["signal_peptide_candidate"] = (track["position"] <= 35) & (track["hydropathy"] >= 1.2)
    return track


def build_bioinformatics_manifest(
    *,
    module: str,
    input_name: str,
    input_bytes: bytes,
    parameters: dict[str, Any],
    outputs: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "module": module,
        "input_name": input_name,
        "input_sha256": sha256(input_bytes).hexdigest(),
        "parameters": parameters,
        "output_keys": sorted(outputs),
        "scientific_boundary": "Built-in analyses are screening and QC aids; specialist engines and domain validation remain required where applicable.",
    }
    canonical = json.dumps(payload, sort_keys=True, default=str)
    payload["manifest_sha256"] = sha256(canonical.encode("utf-8")).hexdigest()
    return payload
