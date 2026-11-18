from __future__ import annotations

from Bio.Seq import Seq


def find_orfs(
    sequence: str,
    min_length_nt: int = 30,
    start_codons: tuple[str, ...] = ("ATG",),
    stop_codons: tuple[str, ...] = ("TAA", "TAG", "TGA"),
    table: int = 1,
    include_partial: bool = False,
) -> list[dict[str, object]]:
    """Find complete and optionally 3'-partial ORFs in all six frames."""

    seq = sequence.upper()
    sequence_length = len(seq)
    results: list[dict[str, object]] = []

    for strand, current in (
        ("+", seq),
        ("-", str(Seq(seq).reverse_complement())),
    ):
        for offset in range(3):
            index = offset
            while index <= len(current) - 3:
                codon = current[index : index + 3]
                if codon not in start_codons:
                    index += 3
                    continue

                stop_index: int | None = None
                for candidate in range(index + 3, len(current) - 2, 3):
                    if current[candidate : candidate + 3] in stop_codons:
                        stop_index = candidate
                        break

                if stop_index is not None:
                    end_exclusive = stop_index + 3
                    complete = True
                    stop_codon = current[stop_index : stop_index + 3]
                elif include_partial:
                    usable = len(current) - index
                    usable -= usable % 3
                    end_exclusive = index + usable
                    complete = False
                    stop_codon = ""
                else:
                    index += 3
                    continue

                nucleotide_sequence = current[index:end_exclusive]
                if len(nucleotide_sequence) >= min_length_nt:
                    if strand == "+":
                        start_position = index + 1
                        end_position = end_exclusive
                    else:
                        start_position = sequence_length - end_exclusive + 1
                        end_position = sequence_length - index

                    protein = str(Seq(nucleotide_sequence).translate(table=table, to_stop=complete))
                    if protein.endswith("*"):
                        protein = protein[:-1]

                    results.append(
                        {
                            "orf": 0,
                            "strand": strand,
                            "frame": f"{strand}{offset + 1}",
                            "start": start_position,
                            "end": end_position,
                            "nt_length": len(nucleotide_sequence),
                            "protein_length": len(protein),
                            "start_codon": codon,
                            "stop_codon": stop_codon,
                            "nucleotide_sequence": nucleotide_sequence,
                            "protein_sequence": protein,
                            "complete": complete,
                        }
                    )

                index = end_exclusive if complete else len(current)

    results.sort(key=lambda row: int(row["nt_length"]), reverse=True)
    for number, row in enumerate(results, start=1):
        row["orf"] = number
    return results
