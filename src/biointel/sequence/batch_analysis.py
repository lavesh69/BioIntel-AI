from __future__ import annotations

import pandas as pd

from biointel.sequence.dna_analysis import nucleotide_statistics
from biointel.sequence.parser import ParsedSequence, parse_sequences_text
from biointel.sequence.protein_analysis import protein_statistics
from biointel.sequence.validators import SequenceType, detect_sequence_type, validate_for_type


def summarize_sequence_records(records: list[ParsedSequence]) -> pd.DataFrame:
    rows = []
    for index, record in enumerate(records, start=1):
        detection = detect_sequence_type(record.sequence)
        sequence_type = detection.detected_type
        row = {
            "record": index,
            "header": record.header,
            "detected_type": sequence_type.value,
            "length": len(record.sequence),
            "status": "ok",
            "warning": detection.message,
        }
        if sequence_type not in {SequenceType.DNA, SequenceType.RNA, SequenceType.PROTEIN}:
            header = record.header.lower()
            hinted = None
            if "rna" in header and not validate_for_type(record.sequence, SequenceType.RNA):
                hinted = SequenceType.RNA
            elif any(t in header for t in ("dna", "gene", "nucleotide")) and not validate_for_type(
                record.sequence, SequenceType.DNA
            ):
                hinted = SequenceType.DNA
            elif any(
                t in header for t in ("protein", "peptide", "amino")
            ) and not validate_for_type(record.sequence, SequenceType.PROTEIN):
                hinted = SequenceType.PROTEIN
            if hinted is None:
                row["status"] = "needs_manual_review"
                rows.append(row)
                continue
            sequence_type = hinted
            row["detected_type"] = hinted.value
            row["warning"] = f"Resolved as {hinted.value} using FASTA header."
        invalid = validate_for_type(record.sequence, sequence_type)
        if invalid:
            row["status"] = "invalid"
            row["warning"] = f"{len(invalid)} invalid symbols"
            rows.append(row)
            continue
        try:
            if sequence_type in {SequenceType.DNA, SequenceType.RNA}:
                stats = nucleotide_statistics(
                    record.sequence, is_rna=sequence_type == SequenceType.RNA
                )
                row.update(
                    {
                        "gc_percent": stats["gc_percent"],
                        "at_au_percent": stats["at_percent"],
                        "ambiguous_count": stats["ambiguous_count"],
                        "entropy_bits": stats["entropy_bits"],
                    }
                )
            else:
                stats = protein_statistics(record.sequence)
                row.update(
                    {
                        "molecular_weight": stats.get("molecular_weight"),
                        "isoelectric_point": stats.get("isoelectric_point"),
                        "gravy": stats.get("gravy"),
                        "instability_index": stats.get("instability_index"),
                    }
                )
        except Exception as exc:
            row["status"] = "analysis_error"
            row["warning"] = str(exc)
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_fasta_text(text: str, max_records: int = 1000) -> pd.DataFrame:
    return summarize_sequence_records(parse_sequences_text(text, max_records=max_records))
