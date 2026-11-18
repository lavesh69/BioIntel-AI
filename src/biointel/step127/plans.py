from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from biointel.tools.runtime import resolve_tool

from .specs import get_spec


@dataclass(frozen=True)
class ProtectedPlan:
    schema: str
    module_key: str
    tool: str
    executable: str
    available: bool
    backend: str
    argv: tuple[str, ...]
    input_paths: tuple[str, ...]
    output_directory: str
    parameters: dict[str, Any]
    input_sha256: dict[str, str]
    boundary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PlanValidationError(ValueError):
    pass

PLAN_CAPABLE_TOOLS: frozenset[str] = frozenset({
    "mafft", "minimap2", "minigraph", "vg", "odgi", "flye", "hifiasm", "canu",
    "racon", "medaka_consensus", "purge_dups", "quast", "quast.py", "busco",
    "merqury.sh", "fastp", "fastqc", "multiqc", "bowtie2", "bcftools", "vep",
    "snpEff", "mageck", "kraken2", "bracken", "metaphlan", "humann", "mash",
    "fastANI", "mlst", "amrfinder", "run_resfinder.py", "run_gubbins.py",
    "iqtree3", "iqtree2", "iqtree", "raxml-ng", "primer3_core", "blastn",
    "hmmscan", "comet", "MSGFPlus", "obabel", "vina",
})


def _bounded_int(value: Any, low: int, high: int, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PlanValidationError(f"{name} must be an integer") from exc
    if not low <= parsed <= high:
        raise PlanValidationError(f"{name} must be between {low} and {high}")
    return parsed


def _clean_path(value: str | os.PathLike[str], *, must_exist: bool = False) -> str:
    text = str(value).strip().strip('"')
    if not text:
        raise PlanValidationError("A non-empty path is required")
    if any(character in text for character in ("\x00", "\n", "\r")):
        raise PlanValidationError("Path contains control characters")
    path = Path(os.path.expandvars(text)).expanduser()
    if must_exist and not path.exists():
        raise PlanValidationError(f"Input path does not exist: {path}")
    return str(path.resolve()) if path.exists() else str(path.absolute())


def _sha256(path_text: str) -> str:
    path = Path(path_text)
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require(inputs: Sequence[str], count: int, tool: str) -> tuple[str, ...]:
    if len(inputs) < count:
        raise PlanValidationError(f"{tool} requires at least {count} input path(s)")
    return tuple(inputs)


def _tool_argv(tool: str, inputs: Sequence[str], out: str, parameters: Mapping[str, Any]) -> list[str]:
    threads = _bounded_int(parameters.get("threads", 4), 1, 64, "threads")
    first = inputs[0] if inputs else ""
    second = inputs[1] if len(inputs) > 1 else ""
    out_path = Path(out)

    if tool == "mafft":
        _require(inputs, 1, tool)
        return [tool, "--auto", "--thread", str(threads), first]
    if tool == "minimap2":
        _require(inputs, 2, tool)
        preset = str(parameters.get("preset", "asm5"))
        if preset not in {"asm5", "asm10", "asm20", "map-ont", "map-hifi", "sr"}:
            raise PlanValidationError("Unsupported minimap2 preset")
        return [tool, "-x", preset, "-t", str(threads), first, second]
    if tool == "minigraph":
        _require(inputs, 2, tool)
        return [tool, "-xggs", "-t", str(threads), first, *inputs[1:]]
    if tool == "vg":
        _require(inputs, 1, tool)
        return [tool, "autoindex", "--workflow", "giraffe", "--prefix", str(out_path / "pangenome"), "--gfa", first, "--threads", str(threads)]
    if tool == "odgi":
        _require(inputs, 1, tool)
        return [tool, "build", "-g", first, "-o", str(out_path / "graph.og"), "-t", str(threads)]
    if tool == "flye":
        _require(inputs, 1, tool)
        platform = str(parameters.get("platform", "nano-hq"))
        flag = {"nano-hq": "--nano-hq", "nano-raw": "--nano-raw", "pacbio-hifi": "--pacbio-hifi", "pacbio-raw": "--pacbio-raw"}.get(platform)
        if flag is None:
            raise PlanValidationError("Unsupported Flye platform")
        argv = [tool, flag, first, "--out-dir", out, "--threads", str(threads)]
        genome_size = str(parameters.get("genome_size", "")).strip()
        if genome_size:
            if not genome_size.lower().endswith(("k", "m", "g")) and not genome_size.isdigit():
                raise PlanValidationError("genome_size must be an integer or end in k/m/g")
            argv += ["--genome-size", genome_size]
        return argv
    if tool == "hifiasm":
        _require(inputs, 1, tool)
        return [tool, "-o", str(out_path / "assembly"), "-t", str(threads), first]
    if tool == "canu":
        _require(inputs, 1, tool)
        genome_size = str(parameters.get("genome_size", "3m"))
        return [tool, "-p", "assembly", "-d", out, f"genomeSize={genome_size}", "-nanopore", first]
    if tool == "racon":
        _require(inputs, 3, tool)
        return [tool, "-t", str(threads), inputs[0], inputs[1], inputs[2]]
    if tool == "medaka_consensus":
        _require(inputs, 2, tool)
        return [tool, "-i", first, "-d", second, "-o", out, "-t", str(threads)]
    if tool == "purge_dups":
        _require(inputs, 1, tool)
        return [tool, first]
    if tool in {"quast", "quast.py"}:
        _require(inputs, 1, tool)
        return [tool, first, "-o", out, "-t", str(threads)]
    if tool == "busco":
        _require(inputs, 1, tool)
        lineage = str(parameters.get("lineage", "")).strip()
        if not lineage:
            raise PlanValidationError("BUSCO lineage is required")
        return [tool, "-i", first, "-o", "busco", "-m", "genome", "-l", lineage, "-c", str(threads), "--out_path", out]
    if tool == "merqury.sh":
        _require(inputs, 2, tool)
        return [tool, first, second, str(out_path / "merqury")]
    if tool == "fastp":
        _require(inputs, 1, tool)
        argv = [tool, "-i", first, "-o", str(out_path / "R1.trimmed.fastq.gz"), "--thread", str(min(threads, 16)), "--json", str(out_path / "fastp.json"), "--html", str(out_path / "fastp.html")]
        if second:
            argv += ["-I", second, "-O", str(out_path / "R2.trimmed.fastq.gz"), "--detect_adapter_for_pe"]
        return argv
    if tool == "fastqc":
        _require(inputs, 1, tool)
        return [tool, "--threads", str(threads), "--outdir", out, *inputs]
    if tool == "multiqc":
        _require(inputs, 1, tool)
        return [tool, first, "--outdir", out, "--force"]
    if tool == "bowtie2":
        _require(inputs, 2, tool)
        index = first
        reads = inputs[1:]
        argv = [tool, "-x", index, "-p", str(threads), "--very-sensitive"]
        if len(reads) >= 2:
            argv += ["-1", reads[0], "-2", reads[1]]
        else:
            argv += ["-U", reads[0]]
        argv += ["--un-conc-gz", str(out_path / "unmapped.fastq.gz"), "-S", str(out_path / "alignment.sam")]
        return argv
    if tool == "bcftools":
        _require(inputs, 1, tool)
        reference = str(parameters.get("reference", "")).strip()
        if not reference:
            raise PlanValidationError("Reference FASTA is required for bcftools normalization")
        return [tool, "norm", "-f", _clean_path(reference), "-m", "-any", "-Oz", "-o", str(out_path / "normalized.vcf.gz"), first]
    if tool == "vep":
        _require(inputs, 1, tool)
        assembly = str(parameters.get("assembly", "GRCh38"))
        if assembly not in {"GRCh37", "GRCh38"}:
            raise PlanValidationError("VEP assembly must be GRCh37 or GRCh38")
        return [tool, "--input_file", first, "--output_file", str(out_path / "vep.tsv"), "--tab", "--offline", "--cache", "--assembly", assembly, "--fork", str(min(threads, 16)), "--everything"]
    if tool == "snpEff":
        _require(inputs, 1, tool)
        genome = str(parameters.get("genome", "")).strip()
        if not genome:
            raise PlanValidationError("SnpEff genome database identifier is required")
        return [tool, "-v", genome, first]
    if tool == "mageck":
        _require(inputs, 1, tool)
        treatment = str(parameters.get("treatment", "")).strip()
        control = str(parameters.get("control", "")).strip()
        if not treatment or not control:
            raise PlanValidationError("MAGeCK treatment and control labels are required")
        return [tool, "test", "-k", first, "-t", treatment, "-c", control, "-n", str(out_path / "mageck")]
    if tool == "kraken2":
        _require(inputs, 2, tool)
        database = first
        reads = inputs[1:]
        argv = [tool, "--db", database, "--threads", str(threads), "--report", str(out_path / "kraken.report"), "--output", str(out_path / "kraken.output")]
        if len(reads) >= 2:
            argv += ["--paired", reads[0], reads[1]]
        else:
            argv += [reads[0]]
        return argv
    if tool == "bracken":
        _require(inputs, 2, tool)
        database, report = first, second
        level = str(parameters.get("level", "S"))
        if level not in {"S", "G", "F", "O", "C", "P", "D"}:
            raise PlanValidationError("Unsupported Bracken level")
        return [tool, "-d", database, "-i", report, "-o", str(out_path / "bracken.tsv"), "-l", level]
    if tool == "metaphlan":
        _require(inputs, 1, tool)
        return [tool, first, "--input_type", "fastq", "--nproc", str(threads), "-o", str(out_path / "metaphlan.tsv")]
    if tool == "humann":
        _require(inputs, 1, tool)
        return [tool, "--input", first, "--output", out, "--threads", str(threads)]
    if tool == "mash":
        _require(inputs, 2, tool)
        return [tool, "dist", first, *inputs[1:]]
    if tool == "fastANI":
        _require(inputs, 2, tool)
        return [tool, "-q", first, "-r", second, "-o", str(out_path / "ani.tsv"), "-t", str(threads)]
    if tool == "mlst":
        _require(inputs, 1, tool)
        return [tool, *inputs]
    if tool == "amrfinder":
        _require(inputs, 1, tool)
        return [tool, "-n", first, "-o", str(out_path / "amrfinder.tsv"), "--threads", str(threads), "--plus"]
    if tool == "run_resfinder.py":
        _require(inputs, 1, tool)
        return [tool, "-ifa", first, "-o", out, "-acq"]
    if tool == "run_gubbins.py":
        _require(inputs, 1, tool)
        return [tool, "--prefix", str(out_path / "gubbins"), "--threads", str(threads), first]
    if tool in {"iqtree3", "iqtree2", "iqtree"}:
        _require(inputs, 1, tool)
        bootstrap = _bounded_int(parameters.get("bootstrap", 1000), 100, 10000, "bootstrap")
        return [tool, "-s", first, "-m", "MFP", "-B", str(bootstrap), "-T", str(threads), "--prefix", str(out_path / "tree")]
    if tool == "raxml-ng":
        _require(inputs, 1, tool)
        bootstrap = _bounded_int(parameters.get("bootstrap", 1000), 100, 10000, "bootstrap")
        return [tool, "--all", "--msa", first, "--model", "GTR+G", "--bs-trees", str(bootstrap), "--threads", str(threads), "--prefix", str(out_path / "raxml")]
    if tool == "primer3_core":
        _require(inputs, 1, tool)
        return [tool, first]
    if tool == "blastn":
        _require(inputs, 2, tool)
        return [tool, "-query", first, "-db", second, "-outfmt", "6", "-max_target_seqs", str(_bounded_int(parameters.get("max_targets", 50), 1, 500, "max_targets")), "-num_threads", str(threads)]
    if tool == "hmmscan":
        _require(inputs, 2, tool)
        return [tool, "--noali", "--tblout", str(out_path / "domains.tbl"), first, second]
    if tool == "comet":
        _require(inputs, 2, tool)
        return [tool, f"-P{first}", f"-D{second}", *inputs[2:]]
    if tool == "MSGFPlus":
        _require(inputs, 2, tool)
        return [tool, "-s", first, "-d", second, "-o", str(out_path / "msgfplus.mzid"), "-thread", str(threads)]
    if tool == "obabel":
        _require(inputs, 1, tool)
        return [tool, first, "-O", str(out_path / "prepared.pdb"), "-h"]
    if tool == "vina":
        _require(inputs, 2, tool)
        exhaustiveness = _bounded_int(parameters.get("exhaustiveness", 8), 1, 64, "exhaustiveness")
        return [tool, "--receptor", first, "--ligand", second, "--out", str(out_path / "docked.pdbqt"), "--log", str(out_path / "vina.log"), "--exhaustiveness", str(exhaustiveness), "--cpu", str(threads)]
    if tool in {"proteinmpnn", "rfdiffusion", "colabfold_batch", "foldx", "rosetta_scripts"}:
        raise PlanValidationError("Use the Step 122 protected protein-design pipeline for this backend")
    raise PlanValidationError(f"No Step 127 protected plan is registered for {tool}")


def supported_tools(module_key: str) -> tuple[str, ...]:
    spec = get_spec(module_key)
    names: list[str] = []
    for stage in spec.stages:
        names.extend(stage.tools)
    return tuple(name for name in dict.fromkeys(names) if name in PLAN_CAPABLE_TOOLS)


def build_protected_plan(
    module_key: str,
    tool: str,
    input_paths: Iterable[str | os.PathLike[str]],
    output_directory: str | os.PathLike[str],
    *,
    parameters: Mapping[str, Any] | None = None,
    require_existing_inputs: bool = False,
) -> ProtectedPlan:
    spec = get_spec(module_key)
    allowed = supported_tools(module_key)
    if tool not in allowed:
        raise PlanValidationError(f"{tool} is not registered for {spec.title}")
    inputs = tuple(_clean_path(value, must_exist=require_existing_inputs) for value in input_paths if str(value).strip())
    out = _clean_path(output_directory, must_exist=False)
    Path(out).mkdir(parents=True, exist_ok=True)
    params = dict(parameters or {})
    argv = tuple(_tool_argv(tool, inputs, out, params))
    resolution = resolve_tool(tool)
    hashes = {path: _sha256(path) for path in inputs}
    return ProtectedPlan(
        schema="biointel.step127.protected-plan.v1",
        module_key=module_key,
        tool=tool,
        executable=resolution.executable or tool,
        available=resolution.available,
        backend=resolution.backend,
        argv=argv,
        input_paths=inputs,
        output_directory=out,
        parameters=params,
        input_sha256=hashes,
        boundary=spec.evidence_boundary,
    )


def plan_json(plan: ProtectedPlan) -> str:
    return json.dumps(plan.to_dict(), indent=2, sort_keys=True, default=str)
