from __future__ import annotations

import base64
import contextlib
import csv
import gzip
import hashlib
import io
import json
import math
import re
import struct
import tempfile
import xml.etree.ElementTree as ET
import zlib
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Iterator, TextIO

import numpy as np
import pandas as pd
from Bio import Phylo, SeqIO
from Bio.PDB import MMCIFParser, PDBParser
from PIL import Image
from scipy.io import mmread

MAX_NATIVE_FILE_BYTES = 1024 * 1024 * 1024
INTERACTIVE_NATIVE_BYTES = 100 * 1024 * 1024
DEFAULT_MAX_RECORDS = 100_000
DEFAULT_PREVIEW_RECORDS = 5_000

@dataclass(frozen=True)
class NativeFormatSpec:
    key: str
    label: str
    extensions: tuple[str, ...]
    viewer_keys: tuple[str, ...]
    streaming: bool
    native_level: str
    optional_engine: str | None = None
    notes: str = ""

@dataclass
class NativeParseResult:
    format_key: str
    source_name: str
    size_bytes: int
    sha256: str
    primary: pd.DataFrame = field(default_factory=pd.DataFrame)
    secondary: dict[str, pd.DataFrame] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    truncated: bool = False
    total_records: int | None = None
    native_level: str = "native"
    engine_required: str | None = None

    @property
    def record_count(self) -> int:
        return int(len(self.primary))

    def summary(self) -> dict[str, Any]:
        return {
            "format": self.format_key,
            "source": self.source_name,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "records_loaded": self.record_count,
            "total_records": self.total_records,
            "truncated": self.truncated,
            "native_level": self.native_level,
            "engine_required": self.engine_required,
            "warnings": list(self.warnings),
            **self.metadata,
        }

NATIVE_FORMATS: dict[str, NativeFormatSpec] = {
    "fasta": NativeFormatSpec("fasta", "FASTA sequence", ("fa", "fasta", "fna", "faa", "fas"), ("sequence_track", "genome_browser"), True, "native"),
    "fastq": NativeFormatSpec("fastq", "FASTQ reads", ("fastq", "fq", "fastq.gz", "fq.gz"), ("genome_browser",), True, "native"),
    "vcf": NativeFormatSpec("vcf", "Variant Call Format", ("vcf", "vcf.gz"), ("genome_browser", "pedigree"), True, "native"),
    "bed": NativeFormatSpec("bed", "BED genomic intervals", ("bed", "bed.gz", "narrowpeak", "broadpeak", "bedgraph"), ("genome_browser", "sequence_track"), True, "native"),
    "gff": NativeFormatSpec("gff", "GFF/GTF annotations", ("gff", "gff3", "gtf", "gff.gz", "gtf.gz"), ("genome_browser", "sequence_track"), True, "native"),
    "sam": NativeFormatSpec("sam", "SAM alignments", ("sam",), ("genome_browser",), True, "native"),
    "bam": NativeFormatSpec("bam", "BAM alignments", ("bam",), ("genome_browser",), True, "engine-assisted", "samtools", "Header and indexed coverage require samtools or pysam."),
    "cram": NativeFormatSpec("cram", "CRAM alignments", ("cram",), ("genome_browser",), True, "engine-assisted", "samtools", "CRAM decoding also requires the matching reference FASTA."),
    "pdb": NativeFormatSpec("pdb", "PDB structure", ("pdb",), ("molecular_3d",), True, "native"),
    "mmcif": NativeFormatSpec("mmcif", "mmCIF structure", ("cif", "mmcif"), ("molecular_3d",), True, "native"),
    "image": NativeFormatSpec("image", "Scientific image", ("png", "jpg", "jpeg", "tif", "tiff", "ome.tif", "ome.tiff"), ("pathology", "microscopy"), True, "native-preview", None, "Large whole-slide formats need OpenSlide for tiled multiresolution access."),
    "wsi": NativeFormatSpec("wsi", "Whole-slide image", ("svs", "ndpi", "mrxs", "scn", "bif", "vms", "vmu"), ("pathology",), True, "engine-assisted", "openslide", "OpenSlide is required for multiresolution tile access; checksum and container metadata remain available without it."),
    "bedmethyl": NativeFormatSpec("bedmethyl", "bedMethyl modified-base calls", ("bedmethyl", "bedmethyl.gz"), ("genome_browser", "sequence_track"), True, "native"),
    "genbank": NativeFormatSpec("genbank", "GenBank sequence and feature table", ("gb", "gbk", "genbank"), ("sequence_track", "genome_browser"), True, "native"),
    "sdf": NativeFormatSpec("sdf", "Chemical structure file", ("sdf", "mol", "mol2", "pdbqt"), ("molecular_3d",), True, "native-preview", "obabel", "Open Babel is optional for full conversion/protonation; bounded structure metadata are parsed without executing external code."),
    "model_asset": NativeFormatSpec("model_asset", "Model checkpoint asset", ("onnx", "safetensors", "pt", "pth", "bin", "gguf"), ("static_reporting",), True, "metadata-only", None, "Binary model assets are checksum-inspected and never deserialised during preview."),
    "safety_xml": NativeFormatSpec("safety_xml", "Adverse-event XML", ("xml",), ("multiomics",), True, "native-preview", None, "Generic bounded XML event/case extraction; dictionary coding still requires licensed terminology assets."),
    "parquet": NativeFormatSpec("parquet", "Apache Parquet/Feather table", ("parquet", "feather"), ("single_cell", "multiomics", "plate_map"), True, "native"),
    "jsonl": NativeFormatSpec("jsonl", "JSON Lines records", ("jsonl", "ndjson"), ("multiomics", "static_reporting"), True, "native"),
    "yaml": NativeFormatSpec("yaml", "YAML manifest", ("yaml", "yml"), ("workflow_dag", "static_reporting"), True, "native"),
    "hdf5": NativeFormatSpec("hdf5", "HDF5 scientific container", ("h5", "hdf5", "h5mu", "mudata"), ("single_cell", "multiomics"), True, "native-preview", None, "Datasets are inventoried without loading the complete container into memory."),
    "bcf": NativeFormatSpec("bcf", "Binary variant calls", ("bcf",), ("genome_browser",), True, "engine-assisted", "bcftools", "BCF decoding requires BCFtools or pysam; checksum metadata remain available."),
    "plink_binary": NativeFormatSpec("plink_binary", "PLINK/BGEN binary genotype asset", ("pgen", "bgen"), ("genome_browser",), True, "metadata-only", "plink2", "Binary genotype assets are checksum-inspected and require matching PVAR/PSAM or sample/variant metadata."),
    "bigwig": NativeFormatSpec("bigwig", "BigWig signal track", ("bigwig", "bw"), ("genome_browser",), True, "engine-assisted", "deeptools", "BigWig metadata are checksum-inspected; indexed interval extraction requires pyBigWig or compatible tooling."),
    "bedpe": NativeFormatSpec("bedpe", "BEDPE paired genomic intervals", ("bedpe",), ("genome_browser",), True, "native"),
    "graph_binary": NativeFormatSpec("graph_binary", "Binary pangenome graph/index", ("vg", "xg", "gbz"), ("pangenome_graph",), True, "metadata-only", "vg", "Binary graph indexes are checksum-inspected and require the matching vg release for decoding."),
    "fcs": NativeFormatSpec("fcs", "Flow Cytometry Standard", ("fcs",), ("flow_gating",), True, "native"),
    "mzml": NativeFormatSpec("mzml", "mzML mass spectrometry", ("mzml", "mzml.gz"), ("mass_spectrometry",), True, "native"),
    "mgf": NativeFormatSpec("mgf", "Mascot Generic Format", ("mgf", "mgf.gz"), ("mass_spectrometry",), True, "native"),
    "newick": NativeFormatSpec("newick", "Newick tree", ("nwk", "newick", "tree", "tre"), ("phylogenetic_tree",), True, "native"),
    "nexus": NativeFormatSpec("nexus", "Nexus tree", ("nex", "nexus"), ("phylogenetic_tree",), True, "native"),
    "plate": NativeFormatSpec("plate", "Plate-layout table", ("csv", "tsv", "xlsx", "xls"), ("plate_map",), True, "native"),
    "ped": NativeFormatSpec("ped", "PED pedigree", ("ped", "fam"), ("pedigree",), True, "native"),
    "gfa": NativeFormatSpec("gfa", "Graphical Fragment Assembly", ("gfa", "gfa1", "gfa2"), ("pangenome_graph",), True, "native"),
    "h5ad": NativeFormatSpec("h5ad", "AnnData H5AD", ("h5ad",), ("single_cell",), True, "native"),
    "mtx": NativeFormatSpec("mtx", "Matrix Market", ("mtx", "mtx.gz"), ("single_cell", "multiomics"), True, "native"),
    "workflow_json": NativeFormatSpec("workflow_json", "Workflow JSON", ("json",), ("workflow_dag", "visual_regression", "static_reporting"), True, "native"),
    "tabular": NativeFormatSpec("tabular", "Scientific table", ("csv", "tsv", "txt", "xlsx", "xls", "json"), ("genome_browser", "pathology", "microscopy", "flow_gating", "mass_spectrometry", "plate_map", "pedigree", "outbreak_map", "pangenome_graph", "single_cell", "sequence_track", "multiomics", "bioprocess_live", "freezer_map"), True, "native"),
}

def _compound_suffix(name: str) -> str:
    lower = Path(name).name.lower()
    known = sorted({ext for spec in NATIVE_FORMATS.values() for ext in spec.extensions}, key=len, reverse=True)
    for ext in known:
        if lower.endswith("." + ext) or lower == ext:
            return ext
    return lower.rsplit(".", 1)[-1] if "." in lower else ""

def detect_native_format(name: str, head: bytes = b"", *, preferred_viewer: str | None = None) -> str:
    suffix = _compound_suffix(name)
    candidates = [spec for spec in NATIVE_FORMATS.values() if suffix in spec.extensions]
    if preferred_viewer:
        matching = [spec for spec in candidates if preferred_viewer in spec.viewer_keys]
        if matching:
            candidates = matching
    if suffix == "bed" and head[:3] in {b"\x6c\x1b\x01", b"\x6c\x1b\x00"}:
        return "plink_binary"
    if suffix == "json" and preferred_viewer not in {"workflow_dag", "visual_regression", "static_reporting"}:
        return "tabular"
    if suffix in {"csv", "tsv", "txt", "xlsx", "xls"} and preferred_viewer != "plate_map":
        return "tabular"
    if candidates:
        return candidates[0].key
    stripped = head.lstrip()
    if stripped.startswith(b"##fileformat=VCF"):
        return "vcf"
    if stripped.startswith(b">"):
        return "fasta"
    if stripped.startswith(b"HWI") or (b"\n+" in head[:4096] and b"\n@" in b"\n" + head[:4096]):
        return "fastq"
    if head.startswith(b"FCS"):
        return "fcs"
    if b"<mzML" in head[:10000] or b"<indexedmzML" in head[:10000]:
        return "mzml"
    if stripped.startswith(b"HEADER") or stripped.startswith(b"ATOM"):
        return "pdb"
    if stripped.startswith(b"data_") and b"_atom_site." in head:
        return "mmcif"
    if b"\tS\t" in b"\t" + head[:4096] or stripped.startswith(b"S\t"):
        return "gfa"
    return "tabular"

def _hash_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()

def stage_native_source(source: Any, *, directory: Path | None = None, maximum_bytes: int = MAX_NATIVE_FILE_BYTES) -> tuple[Path, bool]:
    """Return a filesystem path and whether the caller owns the temporary file."""
    if isinstance(source, (str, Path)):
        path = Path(source).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.stat().st_size > maximum_bytes:
            raise ValueError("Scientific file exceeds the configured 1 GB limit.")
        return path, False
    name = Path(str(getattr(source, "name", "native_upload.dat"))).name
    suffixes = "".join(Path(name).suffixes)[-24:]
    target_dir = directory or Path(tempfile.mkdtemp(prefix="biointel-native-"))
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / (re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem)[:80] + suffixes)
    total = 0
    if hasattr(source, "seek"):
        source.seek(0)
    with path.open("wb") as output:
        while True:
            chunk = source.read(4 * 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum_bytes:
                output.close()
                path.unlink(missing_ok=True)
                raise ValueError("Scientific file exceeds the configured 1 GB limit.")
            output.write(chunk)
    if hasattr(source, "seek"):
        source.seek(0)
    return path, True

@contextlib.contextmanager
def _open_text(path: Path) -> Iterator[TextIO]:
    if path.name.lower().endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8-sig", errors="replace", newline="") as handle:
            yield handle
    else:
        with path.open("rt", encoding="utf-8-sig", errors="replace", newline="") as handle:
            yield handle

@contextlib.contextmanager
def _open_binary(path: Path) -> Iterator[BinaryIO]:
    if path.name.lower().endswith(".gz"):
        with gzip.open(path, "rb") as handle:
            yield handle
    else:
        with path.open("rb") as handle:
            yield handle

def _base_result(path: Path, format_key: str) -> NativeParseResult:
    spec = NATIVE_FORMATS[format_key]
    return NativeParseResult(
        format_key=format_key,
        source_name=path.name,
        size_bytes=path.stat().st_size,
        sha256=_hash_path(path),
        native_level=spec.native_level,
        engine_required=spec.optional_engine,
    )

def _parse_fasta(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "fasta")
    rows: list[dict[str, Any]] = []
    with _open_text(path) as handle:
        for index, record in enumerate(SeqIO.parse(handle, "fasta")):
            if index >= max_records:
                result.truncated = True
                break
            sequence = str(record.seq).upper()
            length = len(sequence)
            gc = (sequence.count("G") + sequence.count("C")) / max(length, 1)
            rows.append({"record_id": record.id, "description": record.description, "sequence": sequence, "length": length, "gc_fraction": gc})
    result.primary = pd.DataFrame(rows)
    result.total_records = len(rows) if not result.truncated else None
    result.metadata = {"sequence_type": "nucleotide_or_protein", "records": len(rows)}
    return result

def _parse_fastq(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "fastq")
    rows: list[dict[str, Any]] = []
    position_quality: dict[int, list[float]] = {}
    with _open_text(path) as handle:
        for index, record in enumerate(SeqIO.parse(handle, "fastq")):
            if index >= max_records:
                result.truncated = True
                break
            sequence = str(record.seq).upper()
            qualities = list(record.letter_annotations.get("phred_quality", []))
            for pos, value in enumerate(qualities, 1):
                if pos <= 500:
                    position_quality.setdefault(pos, []).append(float(value))
            rows.append({
                "read_id": record.id,
                "length": len(sequence),
                "mean_quality": float(np.mean(qualities)) if qualities else np.nan,
                "min_quality": float(np.min(qualities)) if qualities else np.nan,
                "gc_fraction": (sequence.count("G") + sequence.count("C")) / max(len(sequence), 1),
                "n_fraction": sequence.count("N") / max(len(sequence), 1),
            })
    result.primary = pd.DataFrame(rows)
    result.secondary["per_base_quality"] = pd.DataFrame([
        {"position": pos, "mean_quality": float(np.mean(values)), "median_quality": float(np.median(values)), "reads": len(values)}
        for pos, values in sorted(position_quality.items())
    ])
    result.total_records = len(rows) if not result.truncated else None
    result.metadata = {"reads_loaded": len(rows), "quality_encoding": "Phred"}
    return result

def _parse_info(text: str) -> dict[str, str | bool]:
    values: dict[str, str | bool] = {}
    for token in text.split(";"):
        if not token:
            continue
        if "=" in token:
            key, value = token.split("=", 1)
            values[key] = value
        else:
            values[token] = True
    return values

def _parse_vcf(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "vcf")
    rows: list[dict[str, Any]] = []
    samples: list[str] = []
    contigs: list[str] = []
    total = 0
    with _open_text(path) as handle:
        for line in handle:
            if line.startswith("##contig=<ID="):
                match = re.search(r"ID=([^,>]+)", line)
                if match:
                    contigs.append(match.group(1))
                continue
            if line.startswith("#CHROM"):
                fields = line.rstrip("\n\r").split("\t")
                samples = fields[9:]
                continue
            if not line or line.startswith("#"):
                continue
            total += 1
            if len(rows) >= max_records:
                result.truncated = True
                continue
            fields = line.rstrip("\n\r").split("\t")
            if len(fields) < 8:
                result.warnings.append(f"Skipped malformed VCF row {total}")
                continue
            chrom, pos, vid, ref, alts, qual, filt, info = fields[:8]
            info_map = _parse_info(info)
            format_keys = fields[8].split(":") if len(fields) > 8 else []
            sample_values = fields[9:] if len(fields) > 9 else []
            base = {
                "chrom": chrom,
                "position": int(pos),
                "variant_id": vid if vid not in {"", "."} else f"{chrom}:{pos}:{ref}>{alts}",
                "ref": ref,
                "alt": alts,
                "quality": pd.to_numeric(qual, errors="coerce"),
                "filter": filt,
                "variant_type": "SNV" if len(ref) == 1 and all(len(alt) == 1 for alt in alts.split(",")) else "INDEL/SV",
                "allele_frequency": pd.to_numeric(str(info_map.get("AF", "")).split(",")[0], errors="coerce"),
                "depth": pd.to_numeric(info_map.get("DP", np.nan), errors="coerce"),
                "gene": str(info_map.get("GENE", info_map.get("SYMBOL", ""))),
                "info": info,
            }
            if sample_values:
                for sample_name, sample_text in zip(samples or [f"sample_{i+1}" for i in range(len(sample_values))], sample_values):
                    sample_map = dict(zip(format_keys, sample_text.split(":")))
                    rows.append({**base, "sample": sample_name, "genotype": sample_map.get("GT", ""), "sample_depth": pd.to_numeric(sample_map.get("DP", np.nan), errors="coerce")})
                    if len(rows) >= max_records:
                        result.truncated = True
                        break
            else:
                rows.append(base)
    result.primary = pd.DataFrame(rows)
    result.total_records = total
    result.metadata = {"samples": samples, "sample_count": len(samples), "contigs": contigs[:1000], "contig_count": len(contigs)}
    return result

def _parse_bed(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "bed")
    rows: list[dict[str, Any]] = []
    total = 0
    with _open_text(path) as handle:
        for line in handle:
            if not line.strip() or line.startswith(("#", "track", "browser")):
                continue
            total += 1
            if len(rows) >= max_records:
                result.truncated = True
                continue
            fields = line.rstrip("\n\r").split("\t")
            if len(fields) < 3:
                result.warnings.append(f"Skipped malformed BED row {total}")
                continue
            row = {
                "chrom": fields[0], "start": int(fields[1]), "end": int(fields[2]),
                "name": fields[3] if len(fields) > 3 else f"interval_{total}",
                "score": pd.to_numeric(fields[4], errors="coerce") if len(fields) > 4 else np.nan,
                "strand": fields[5] if len(fields) > 5 else ".",
            }
            if len(fields) > 6:
                row["extra"] = "\t".join(fields[6:])
            rows.append(row)
    result.primary = pd.DataFrame(rows)
    result.total_records = total
    result.metadata = {"coordinate_system": "0-based half-open"}
    return result

def _parse_bedpe(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "bedpe")
    rows: list[dict[str, Any]] = []
    total = 0
    with _open_text(path) as handle:
        for line in handle:
            if not line.strip() or line.startswith(("#", "track", "browser")):
                continue
            total += 1
            if len(rows) >= max_records:
                result.truncated = True
                continue
            fields = line.rstrip("\n\r").split("\t")
            if len(fields) < 6:
                result.warnings.append(f"Skipped malformed BEDPE row {total}")
                continue
            rows.append({
                "chrom1": fields[0], "start1": int(fields[1]), "end1": int(fields[2]),
                "chrom2": fields[3], "start2": int(fields[4]), "end2": int(fields[5]),
                "name": fields[6] if len(fields) > 6 else f"event_{total}",
                "score": pd.to_numeric(fields[7], errors="coerce") if len(fields) > 7 else np.nan,
                "strand1": fields[8] if len(fields) > 8 else ".",
                "strand2": fields[9] if len(fields) > 9 else ".",
            })
    result.primary = pd.DataFrame(rows)
    result.total_records = total
    result.metadata = {"coordinate_system": "0-based half-open paired intervals"}
    return result


def _parse_gff_attributes(text: str) -> dict[str, str]:
    attributes: dict[str, str] = {}
    for token in text.strip().strip(";").split(";"):
        token = token.strip()
        if not token:
            continue
        if "=" in token:
            key, value = token.split("=", 1)
        elif " " in token:
            key, value = token.split(" ", 1)
            value = value.strip().strip('"')
        else:
            key, value = token, ""
        attributes[key] = value
    return attributes

def _parse_gff(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "gff")
    rows: list[dict[str, Any]] = []
    total = 0
    with _open_text(path) as handle:
        for line in handle:
            if not line.strip() or line.startswith("#"):
                continue
            total += 1
            if len(rows) >= max_records:
                result.truncated = True
                continue
            fields = line.rstrip("\n\r").split("\t")
            if len(fields) < 9:
                result.warnings.append(f"Skipped malformed GFF/GTF row {total}")
                continue
            attrs = _parse_gff_attributes(fields[8])
            rows.append({
                "chrom": fields[0], "source": fields[1], "feature_type": fields[2],
                "start": int(fields[3]), "end": int(fields[4]),
                "score": pd.to_numeric(fields[5], errors="coerce"), "strand": fields[6], "phase": fields[7],
                "id": attrs.get("ID", attrs.get("transcript_id", attrs.get("gene_id", f"feature_{total}"))),
                "name": attrs.get("Name", attrs.get("gene_name", attrs.get("gene_id", ""))),
                "parent": attrs.get("Parent", attrs.get("transcript_id", "")), "attributes": fields[8],
            })
    result.primary = pd.DataFrame(rows)
    result.total_records = total
    result.metadata = {"coordinate_system": "1-based closed", "feature_types": sorted(result.primary.get("feature_type", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())[:100]}
    return result

def _parse_sam(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "sam")
    rows: list[dict[str, Any]] = []
    references: dict[str, int] = {}
    total = 0
    with _open_text(path) as handle:
        for line in handle:
            if line.startswith("@SQ"):
                tokens = dict(token.split(":", 1) for token in line.rstrip().split("\t")[1:] if ":" in token)
                if "SN" in tokens:
                    references[tokens["SN"]] = int(tokens.get("LN", 0) or 0)
                continue
            if line.startswith("@") or not line.strip():
                continue
            total += 1
            if len(rows) >= max_records:
                result.truncated = True
                continue
            fields = line.rstrip("\n\r").split("\t")
            if len(fields) < 11:
                continue
            flag = int(fields[1])
            rows.append({
                "read_id": fields[0], "flag": flag, "reference": fields[2], "position": int(fields[3]),
                "mapping_quality": int(fields[4]), "cigar": fields[5], "mate_reference": fields[6],
                "mate_position": int(fields[7]), "template_length": int(fields[8]), "sequence_length": len(fields[9]),
                "reverse": bool(flag & 16), "unmapped": bool(flag & 4), "secondary": bool(flag & 256),
            })
    result.primary = pd.DataFrame(rows)
    result.total_records = total
    result.metadata = {"references": references, "reference_count": len(references)}
    return result

def _parse_bam_placeholder(path: Path, format_key: str) -> NativeParseResult:
    result = _base_result(path, format_key)
    result.warnings.append(f"{format_key.upper()} binary decoding is delegated to the validated samtools adapter. The file was hash-verified and staged without loading it into memory.")
    result.metadata = {"binary_alignment": True, "interactive_preview": False}
    result.total_records = None
    return result

def _structure_rows(structure: Any) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for model in structure:
        for chain in model:
            for residue in chain:
                hetfield, resseq, icode = residue.id
                for atom in residue:
                    coord = atom.coord
                    rows.append({
                        "model": int(model.id) if isinstance(model.id, int) else str(model.id),
                        "chain": str(chain.id), "residue_name": residue.resname,
                        "residue_number": int(resseq), "insertion_code": str(icode).strip(),
                        "hetero": str(hetfield).strip() not in {"", "W"}, "atom": atom.name,
                        "element": (atom.element or atom.name[:1]).strip().upper(),
                        "x": float(coord[0]), "y": float(coord[1]), "z": float(coord[2]),
                        "occupancy": float(atom.occupancy) if atom.occupancy is not None else np.nan,
                        "bfactor": float(atom.bfactor) if atom.bfactor is not None else np.nan,
                    })
    return pd.DataFrame(rows)

def _parse_structure(path: Path, format_key: str) -> NativeParseResult:
    result = _base_result(path, format_key)
    parser = PDBParser(QUIET=True) if format_key == "pdb" else MMCIFParser(QUIET=True)
    structure = parser.get_structure(path.stem, str(path))
    result.primary = _structure_rows(structure)
    result.total_records = len(result.primary)
    result.metadata = {
        "models": int(result.primary["model"].nunique()) if not result.primary.empty else 0,
        "chains": sorted(result.primary["chain"].astype(str).unique().tolist()) if not result.primary.empty else [],
        "residues": int(result.primary[["chain", "residue_number", "insertion_code"]].drop_duplicates().shape[0]) if not result.primary.empty else 0,
        "atoms": len(result.primary),
    }
    return result

def _parse_image(path: Path, max_side: int = 2400) -> NativeParseResult:
    result = _base_result(path, "image")
    try:
        with Image.open(path) as image:
            metadata = {
                "format": image.format,
                "mode": image.mode,
                "width": int(image.width),
                "height": int(image.height),
                "frames": int(getattr(image, "n_frames", 1)),
                "decode_state": "decoded",
            }
            image.seek(0)
            preview = image.convert("RGB")
            original_size = preview.size
            preview.thumbnail((max_side, max_side))
            array = np.asarray(preview)
        result.primary = pd.DataFrame([{
            "x": 0,
            "y": 0,
            "width": original_size[0],
            "height": original_size[1],
            "preview_width": array.shape[1],
            "preview_height": array.shape[0],
            "decode_state": "decoded",
        }])
        result.secondary["image_pixels"] = pd.DataFrame(
            array.reshape(-1, 3), columns=["red", "green", "blue"]
        ).head(100_000)
        result.metadata = {
            **metadata,
            "preview_array": array,
            "downsampled_preview": array.shape[1] != original_size[0] or array.shape[0] != original_size[1],
        }
        result.total_records = int(original_size[0] * original_size[1])
        result.truncated = bool(result.metadata["downsampled_preview"])
    except Exception as exc:
        result.primary = pd.DataFrame([{
            "asset_name": path.name,
            "size_bytes": path.stat().st_size,
            "decode_state": "invalid_or_truncated_image",
            "preview_available": False,
        }])
        result.total_records = 1
        result.metadata = {
            "decode_state": "invalid_or_truncated_image",
            "preview_available": False,
            "error_type": type(exc).__name__,
        }
        result.warnings.append(
            f"Image preview could not be decoded; checksum and file metadata remain available: {type(exc).__name__}: {exc}"
        )
    return result

def _parse_wsi(path: Path, max_side: int = 2400) -> NativeParseResult:
    from .formats_v136 import parse_wsi
    return parse_wsi(path, max_side)

def _parse_bedmethyl_native(path: Path, max_records: int) -> NativeParseResult:
    from .formats_v136 import parse_bedmethyl_native
    return parse_bedmethyl_native(path, max_records)

def _parse_genbank(path: Path, max_records: int) -> NativeParseResult:
    from .formats_v136 import parse_genbank
    return parse_genbank(path, max_records)

def _parse_sdf(path: Path, max_records: int) -> NativeParseResult:
    from .formats_v136 import parse_sdf
    return parse_sdf(path, max_records)

def _parse_model_asset(path: Path) -> NativeParseResult:
    from .formats_v136 import parse_model_asset
    return parse_model_asset(path)

def _parse_safety_xml(path: Path, max_records: int) -> NativeParseResult:
    from .formats_v136 import parse_safety_xml
    return parse_safety_xml(path, max_records)

def _parse_parquet(path: Path, max_records: int, format_key: str = "parquet") -> NativeParseResult:
    from .formats_v136 import parse_parquet
    return parse_parquet(path, max_records, format_key)

def _parse_jsonl(path: Path, max_records: int) -> NativeParseResult:
    from .formats_v136 import parse_jsonl
    return parse_jsonl(path, max_records)

def _parse_yaml(path: Path, max_records: int) -> NativeParseResult:
    from .formats_v136 import parse_yaml
    return parse_yaml(path, max_records)

def _parse_hdf5(path: Path, max_records: int) -> NativeParseResult:
    from .formats_v136 import parse_hdf5
    return parse_hdf5(path, max_records)

def _parse_binary_placeholder(path: Path, format_key: str, engine: str) -> NativeParseResult:
    from .formats_v136 import parse_binary_placeholder
    return parse_binary_placeholder(path, format_key, engine)

def _fcs_text_pairs(raw: bytes) -> dict[str, str]:
    if not raw:
        return {}
    delimiter = chr(raw[0])
    text = raw.decode("latin-1", errors="replace")
    tokens: list[str] = []
    current: list[str] = []
    i = 1
    while i < len(text):
        char = text[i]
        if char == delimiter:
            if i + 1 < len(text) and text[i + 1] == delimiter:
                current.append(delimiter)
                i += 2
                continue
            tokens.append("".join(current))
            current = []
        else:
            current.append(char)
        i += 1
    if current:
        tokens.append("".join(current))
    return {tokens[i]: tokens[i + 1] for i in range(0, len(tokens) - 1, 2)}

def _header_int(header: bytes, start: int, end: int) -> int:
    text = header[start:end].decode("ascii", errors="ignore").strip()
    return int(text) if text.isdigit() else 0

def _parse_fcs(path: Path, max_records: int) -> NativeParseResult:
    from .formats_specialized import _parse_fcs as implementation
    return implementation(path, max_records)

def _decode_mzml_binary(binary_array: ET.Element) -> tuple[str | None, np.ndarray]:
    from .formats_specialized import _decode_mzml_binary as implementation
    return implementation(binary_array)

def _parse_mzml(path: Path, max_records: int) -> NativeParseResult:
    from .formats_specialized import _parse_mzml as implementation
    return implementation(path, max_records)

def _parse_mgf(path: Path, max_records: int) -> NativeParseResult:
    from .formats_specialized import _parse_mgf as implementation
    return implementation(path, max_records)

def _tree_to_tables(tree: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    counter = 0
    positions: dict[str, tuple[float, float]] = {}
    terminals = tree.get_terminals()
    terminal_y = {id(node): float(index) for index, node in enumerate(terminals)}

    def walk(clade: Any, depth: float, parent_id: str | None = None) -> str:
        nonlocal counter
        counter += 1
        node_id = f"node_{counter}"
        children = list(clade.clades)
        if children:
            child_ids = [walk(child, depth + float(child.branch_length or 0.0), node_id) for child in children]
            y = float(np.mean([positions[child_id][1] for child_id in child_ids]))
        else:
            y = terminal_y.get(id(clade), float(counter))
        positions[node_id] = (depth, y)
        nodes.append({"id": node_id, "label": clade.name or node_id, "x": depth, "y": y, "branch_length": float(clade.branch_length or 0.0), "confidence": float(clade.confidence) if clade.confidence is not None else np.nan, "terminal": not children})
        if parent_id:
            edges.append({"source": parent_id, "target": node_id, "branch_length": float(clade.branch_length or 0.0)})
        return node_id

    walk(tree.root, 0.0)
    return pd.DataFrame(nodes), pd.DataFrame(edges)

def _parse_tree(path: Path, format_key: str) -> NativeParseResult:
    result = _base_result(path, format_key)
    fmt = "newick" if format_key == "newick" else "nexus"
    with _open_text(path) as handle:
        tree = Phylo.read(handle, fmt)
    nodes, edges = _tree_to_tables(tree)
    result.primary = nodes
    result.secondary["edges"] = edges
    result.metadata = {"terminals": len(tree.get_terminals()), "nonterminals": len(tree.get_nonterminals()), "total_branch_length": float(tree.total_branch_length()), "newick": tree.format("newick")}
    result.total_records = len(nodes)
    return result

def _read_table(path: Path, max_records: int) -> pd.DataFrame:
    suffix = path.suffix.lower()
    lower = path.name.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, nrows=max_records)
    if suffix == ".json":
        obj = json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
        if isinstance(obj, list):
            return pd.json_normalize(obj).head(max_records)
        if isinstance(obj, dict):
            for key in ("records", "data", "rows", "nodes", "events"):
                if isinstance(obj.get(key), list):
                    return pd.json_normalize(obj[key]).head(max_records)
            return pd.json_normalize(obj).head(max_records)
    delimiter = "\t" if suffix in {".tsv", ".txt"} or lower.endswith((".bed", ".gtf", ".gff")) else ","
    return pd.read_csv(path, sep=delimiter, nrows=max_records, low_memory=False)

def _parse_tabular(path: Path, max_records: int, format_key: str = "tabular") -> NativeParseResult:
    result = _base_result(path, format_key)
    result.primary = _read_table(path, max_records)
    result.total_records = None
    result.metadata = {"columns": list(map(str, result.primary.columns)), "column_count": len(result.primary.columns)}
    return result

def _parse_ped(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "ped")
    rows = []
    with _open_text(path) as handle:
        for index, line in enumerate(handle):
            if index >= max_records:
                result.truncated = True
                break
            fields = line.strip().split()
            if len(fields) < 6:
                continue
            rows.append({"family_id": fields[0], "individual_id": fields[1], "father_id": fields[2], "mother_id": fields[3], "sex": fields[4], "phenotype": fields[5], "genotypes": " ".join(fields[6:])})
    result.primary = pd.DataFrame(rows)
    result.total_records = len(rows) if not result.truncated else None
    result.metadata = {"families": int(result.primary["family_id"].nunique()) if not result.primary.empty else 0}
    return result

def _parse_gfa(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "gfa")
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    paths: list[dict[str, Any]] = []
    with _open_text(path) as handle:
        for line in handle:
            fields = line.rstrip("\n\r").split("\t")
            if not fields:
                continue
            if fields[0] == "S" and len(fields) >= 3 and len(nodes) < max_records:
                sequence = fields[2]
                nodes.append({"id": fields[1], "sequence": sequence if len(sequence) <= 5000 else sequence[:5000], "length": len(sequence) if sequence != "*" else pd.to_numeric(next((token[5:] for token in fields[3:] if token.startswith("LN:i:")), np.nan), errors="coerce"), "tags": "\t".join(fields[3:])})
            elif fields[0] == "L" and len(fields) >= 6 and len(edges) < max_records:
                edges.append({"source": fields[1], "source_orientation": fields[2], "target": fields[3], "target_orientation": fields[4], "overlap": fields[5], "tags": "\t".join(fields[6:])})
            elif fields[0] == "P" and len(fields) >= 3 and len(paths) < max_records:
                paths.append({"path": fields[1], "segments": fields[2], "overlaps": fields[3] if len(fields) > 3 else ""})
    result.primary = pd.DataFrame(nodes)
    result.secondary["edges"] = pd.DataFrame(edges)
    result.secondary["paths"] = pd.DataFrame(paths)
    result.total_records = len(nodes)
    result.metadata = {"nodes": len(nodes), "edges": len(edges), "paths": len(paths)}
    result.truncated = len(nodes) >= max_records or len(edges) >= max_records
    return result

def _decode_h5_strings(values: Any) -> np.ndarray:
    array = np.asarray(values)
    if array.dtype.kind in {"S", "O", "U"}:
        return np.array([item.decode("utf-8", errors="replace") if isinstance(item, (bytes, bytearray)) else str(item) for item in array])
    return array.astype(str)

def _parse_h5ad(path: Path, max_records: int) -> NativeParseResult:
    from .formats_specialized import _parse_h5ad as implementation
    return implementation(path, max_records)

def _parse_mtx(path: Path, max_records: int) -> NativeParseResult:
    from .formats_specialized import _parse_mtx as implementation
    return implementation(path, max_records)

def _parse_workflow_json(path: Path, max_records: int) -> NativeParseResult:
    result = _base_result(path, "workflow_json")
    obj = json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
    if not isinstance(obj, dict):
        raise ValueError("Workflow JSON must contain an object")
    nodes_obj = obj.get("nodes") or obj.get("steps") or obj.get("tasks") or []
    edges_obj = obj.get("edges") or obj.get("dependencies") or []
    nodes = pd.json_normalize(nodes_obj).head(max_records) if isinstance(nodes_obj, list) else pd.DataFrame()
    edges = pd.json_normalize(edges_obj).head(max_records) if isinstance(edges_obj, list) else pd.DataFrame()
    result.primary = nodes
    result.secondary["edges"] = edges
    result.metadata = {"top_level_keys": list(obj.keys()), "node_count": len(nodes), "edge_count": len(edges), "raw_manifest": obj}
    result.total_records = len(nodes)
    return result

def parse_native_path(path: str | Path, *, preferred_viewer: str | None = None, max_records: int = DEFAULT_MAX_RECORDS, format_key: str | None = None) -> NativeParseResult:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.stat().st_size > MAX_NATIVE_FILE_BYTES:
        raise ValueError("Scientific file exceeds the configured 1 GB limit.")
    with source.open("rb") as handle:
        head = handle.read(64 * 1024)
    key = format_key or detect_native_format(source.name, head, preferred_viewer=preferred_viewer)
    if key == "fasta": return _parse_fasta(source, max_records)
    if key == "fastq": return _parse_fastq(source, max_records)
    if key == "vcf": return _parse_vcf(source, max_records)
    if key == "bed": return _parse_bed(source, max_records)
    if key == "bedpe": return _parse_bedpe(source, max_records)
    if key == "gff": return _parse_gff(source, max_records)
    if key == "sam": return _parse_sam(source, max_records)
    if key in {"bam", "cram"}: return _parse_bam_placeholder(source, key)
    if key in {"pdb", "mmcif"}: return _parse_structure(source, key)
    if key == "image": return _parse_image(source)
    if key == "wsi": return _parse_wsi(source)
    if key == "bedmethyl": return _parse_bedmethyl_native(source, max_records)
    if key == "genbank": return _parse_genbank(source, max_records)
    if key == "sdf": return _parse_sdf(source, max_records)
    if key == "model_asset": return _parse_model_asset(source)
    if key == "safety_xml": return _parse_safety_xml(source, max_records)
    if key == "parquet": return _parse_parquet(source, max_records)
    if key == "jsonl": return _parse_jsonl(source, max_records)
    if key == "yaml": return _parse_yaml(source, max_records)
    if key == "hdf5": return _parse_hdf5(source, max_records)
    if key == "bcf": return _parse_binary_placeholder(source, "bcf", "bcftools")
    if key == "plink_binary": return _parse_binary_placeholder(source, "plink_binary", "plink2")
    if key == "bigwig": return _parse_binary_placeholder(source, "bigwig", "deeptools")
    if key == "graph_binary": return _parse_binary_placeholder(source, "graph_binary", "vg")
    if key == "fcs": return _parse_fcs(source, max_records)
    if key == "mzml": return _parse_mzml(source, max_records)
    if key == "mgf": return _parse_mgf(source, max_records)
    if key in {"newick", "nexus"}: return _parse_tree(source, key)
    if key == "ped": return _parse_ped(source, max_records)
    if key == "gfa": return _parse_gfa(source, max_records)
    if key == "h5ad": return _parse_h5ad(source, max_records)
    if key == "mtx": return _parse_mtx(source, max_records)
    if key == "workflow_json": return _parse_workflow_json(source, max_records)
    if key == "plate": return _parse_tabular(source, max_records, "plate")
    return _parse_tabular(source, max_records, "tabular")

def parse_native_source(source: Any, *, preferred_viewer: str | None = None, max_records: int = DEFAULT_MAX_RECORDS, format_key: str | None = None, staging_directory: Path | None = None) -> NativeParseResult:
    path, owned = stage_native_source(source, directory=staging_directory)
    try:
        return parse_native_path(path, preferred_viewer=preferred_viewer, max_records=max_records, format_key=format_key)
    finally:
        if owned:
            path.unlink(missing_ok=True)
            with contextlib.suppress(OSError):
                path.parent.rmdir()

def supported_extensions_for_viewer(viewer_key: str) -> list[str]:
    extensions: list[str] = []
    for spec in NATIVE_FORMATS.values():
        if viewer_key in spec.viewer_keys:
            extensions.extend(spec.extensions)
    return sorted(set(extensions))

def format_matrix() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Format": spec.label,
            "Key": spec.key,
            "Extensions": ", ".join(f".{ext}" for ext in spec.extensions),
            "Viewers": ", ".join(spec.viewer_keys),
            "Streaming": spec.streaming,
            "Native level": spec.native_level,
            "Optional engine": spec.optional_engine or "Built in",
            "Notes": spec.notes,
        }
        for spec in NATIVE_FORMATS.values()
    ])

__all__ = [
    "DEFAULT_MAX_RECORDS",
    "DEFAULT_PREVIEW_RECORDS",
    "INTERACTIVE_NATIVE_BYTES",
    "MAX_NATIVE_FILE_BYTES",
    "NATIVE_FORMATS",
    "NativeFormatSpec",
    "NativeParseResult",
    "detect_native_format",
    "format_matrix",
    "parse_native_path",
    "parse_native_source",
    "stage_native_source",
    "supported_extensions_for_viewer",
]
