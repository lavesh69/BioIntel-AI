from __future__ import annotations

import math
from collections import Counter

DNA = set("ACGTNRYKMSWBDHV")
CODON_TABLE = {
    'TTT':'F','TTC':'F','TTA':'L','TTG':'L','CTT':'L','CTC':'L','CTA':'L','CTG':'L',
    'ATT':'I','ATC':'I','ATA':'I','ATG':'M','GTT':'V','GTC':'V','GTA':'V','GTG':'V',
    'TCT':'S','TCC':'S','TCA':'S','TCG':'S','CCT':'P','CCC':'P','CCA':'P','CCG':'P',
    'ACT':'T','ACC':'T','ACA':'T','ACG':'T','GCT':'A','GCC':'A','GCA':'A','GCG':'A',
    'TAT':'Y','TAC':'Y','TAA':'*','TAG':'*','CAT':'H','CAC':'H','CAA':'Q','CAG':'Q',
    'AAT':'N','AAC':'N','AAA':'K','AAG':'K','GAT':'D','GAC':'D','GAA':'E','GAG':'E',
    'TGT':'C','TGC':'C','TGA':'*','TGG':'W','CGT':'R','CGC':'R','CGA':'R','CGG':'R',
    'AGT':'S','AGC':'S','AGA':'R','AGG':'R','GGT':'G','GGC':'G','GGA':'G','GGG':'G',
}
COMPLEMENT = str.maketrans("ACGTNRYKMSWBDHV", "TGCANYRMKSWVHDB")


def clean_sequence(value: str) -> str:
    return "".join(str(value).upper().split()).replace("U", "T")


def parse_fasta(text: str) -> list[dict]:
    records: list[dict] = []
    name = "sequence-1"
    chunks: list[str] = []
    for raw in str(text).splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            if chunks:
                records.append({"name": name, "sequence": clean_sequence("".join(chunks))})
            name = line[1:].strip() or f"sequence-{len(records)+1}"
            chunks = []
        else:
            chunks.append(line)
    if chunks:
        records.append({"name": name, "sequence": clean_sequence("".join(chunks))})
    if not records:
        sequence = clean_sequence(text)
        if sequence:
            records.append({"name": name, "sequence": sequence})
    return records


def parse_fastq(text: str) -> list[dict]:
    lines = [line.rstrip("\n\r") for line in str(text).splitlines() if line.strip()]
    if len(lines) % 4:
        raise ValueError("FASTQ must contain complete four-line records.")
    records: list[dict] = []
    for index in range(0, len(lines), 4):
        header, sequence, plus, quality = lines[index:index+4]
        if not header.startswith("@") or not plus.startswith("+"):
            raise ValueError("Invalid FASTQ record markers.")
        sequence = clean_sequence(sequence)
        if len(sequence) != len(quality):
            raise ValueError("FASTQ sequence and quality lengths differ.")
        records.append({"name": header[1:] or f"read-{len(records)+1}", "sequence": sequence, "quality": quality})
    return records


def sequence_qc(records: list[dict]) -> dict:
    lengths = [len(row["sequence"]) for row in records]
    total = sum(lengths)
    bases = Counter("".join(row["sequence"] for row in records))
    valid = sum(count for base, count in bases.items() if base in DNA)
    result = {
        "record_count": len(records), "total_bases": total,
        "min_length": min(lengths, default=0), "max_length": max(lengths, default=0),
        "mean_length": round(total / max(1, len(records)), 3),
        "gc_percent": round(100.0 * (bases.get('G',0)+bases.get('C',0)) / max(1,total), 3),
        "n_percent": round(100.0 * bases.get('N',0) / max(1,total), 3),
        "valid_iupac_percent": round(100.0 * valid / max(1,total), 3),
        "base_counts": dict(sorted(bases.items())),
    }
    qualities = [ord(ch)-33 for row in records for ch in row.get("quality", "")]
    if qualities:
        result["mean_phred"] = round(sum(qualities)/len(qualities), 3)
        result["q30_percent"] = round(100.0*sum(q>=30 for q in qualities)/len(qualities), 3)
    return result


def reverse_complement(sequence: str) -> str:
    return clean_sequence(sequence).translate(COMPLEMENT)[::-1]


def translate(sequence: str, frame: int = 0) -> str:
    seq = clean_sequence(sequence)
    return "".join(CODON_TABLE.get(seq[i:i+3], "X") for i in range(max(0, frame), len(seq)-2, 3))


def find_orfs(sequence: str, minimum_aa: int = 20) -> list[dict]:
    seq = clean_sequence(sequence)
    hits: list[dict] = []
    for strand, dna in (("+", seq), ("-", reverse_complement(seq))):
        for frame in range(3):
            protein = translate(dna, frame)
            start = 0
            for part in protein.split("*"):
                if len(part) >= minimum_aa and "M" in part:
                    offset = part.find("M")
                    aa = part[offset:]
                    hits.append({"strand": strand, "frame": frame+1, "aa_length": len(aa), "protein": aa[:500], "nucleotide_start": frame + (start+offset)*3 + 1})
                start += len(part)+1
    return sorted(hits, key=lambda row: (-row["aa_length"], row["strand"], row["frame"]))


def kmer_profile(sequence: str, k: int = 3, limit: int = 50) -> list[dict]:
    seq = clean_sequence(sequence)
    if k < 1 or k > 12:
        raise ValueError("k must be between 1 and 12.")
    counts = Counter(seq[i:i+k] for i in range(0, max(0, len(seq)-k+1)) if set(seq[i:i+k]) <= set("ACGT"))
    total = sum(counts.values())
    return [{"kmer": word, "count": count, "frequency": round(count/max(1,total), 6)} for word, count in counts.most_common(limit)]


def global_alignment(left: str, right: str, match: int = 2, mismatch: int = -1, gap: int = -2) -> dict:
    a, b = clean_sequence(left), clean_sequence(right)
    if not a or not b:
        raise ValueError("Two non-empty sequences are required.")
    if len(a) > 2000 or len(b) > 2000:
        raise ValueError("Interactive alignment is limited to 2,000 bases per sequence.")
    rows, cols = len(a)+1, len(b)+1
    score = [[0]*cols for _ in range(rows)]
    trace = [[0]*cols for _ in range(rows)]
    for i in range(1, rows): score[i][0], trace[i][0] = i*gap, 1
    for j in range(1, cols): score[0][j], trace[0][j] = j*gap, 2
    for i in range(1, rows):
        for j in range(1, cols):
            choices = (score[i-1][j-1] + (match if a[i-1] == b[j-1] else mismatch), score[i-1][j]+gap, score[i][j-1]+gap)
            best = max(range(3), key=lambda idx: choices[idx])
            score[i][j], trace[i][j] = choices[best], best
    i, j = len(a), len(b); aa=[]; bb=[]; matches=0
    while i or j:
        direction = trace[i][j]
        if i and j and direction == 0:
            aa.append(a[i-1]); bb.append(b[j-1]); matches += int(a[i-1] == b[j-1]); i-=1; j-=1
        elif i and (j == 0 or direction == 1):
            aa.append(a[i-1]); bb.append('-'); i-=1
        else:
            aa.append('-'); bb.append(b[j-1]); j-=1
    aligned_a, aligned_b = ''.join(reversed(aa)), ''.join(reversed(bb))
    return {"score": score[-1][-1], "identity_percent": round(100.0*matches/max(1,len(aligned_a)),3), "aligned_length": len(aligned_a), "left": aligned_a, "right": aligned_b}
