from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any


STEP155_PLAN_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "blastn_search": ("blastn",),
    "star_align": ("star",),
    "rmats_splicing": ("rmats",),
    "majiq_build": ("majiq",),
    "suppa2_events": ("suppa2",),
    "regenie_association": ("regenie",),
    "saige_association": ("saige",),
    "modkit_pileup": ("modkit",),
    "merqury_evaluate": ("merqury",),
    "rfdiffusion_generate": ("rfdiffusion",),
    "stardist_segment": ("stardist",),
    "openmm_simulate": ("openmm",),
    "amrfinder_run": ("amrfinderplus",),
    "resfinder_run": ("resfinder",),
}

STEP155_PLAN_DESCRIPTIONS: dict[str, str] = {
    "blastn_search": "Search nucleotide queries against a pinned BLAST database",
    "star_align": "Run splice-aware RNA-seq alignment against a pinned STAR index",
    "rmats_splicing": "Run replicate-aware alternative-splicing analysis",
    "majiq_build": "Build MAJIQ splice graphs from a locked configuration",
    "suppa2_events": "Generate SUPPA2 alternative-splicing events",
    "regenie_association": "Run REGENIE step-2 association testing",
    "saige_association": "Run SAIGE association testing with a fitted null model",
    "modkit_pileup": "Generate a long-read modified-base pileup",
    "merqury_evaluate": "Evaluate assembly k-mer completeness and QV",
    "rfdiffusion_generate": "Generate constrained protein backbones using RFdiffusion",
    "stardist_segment": "Run StarDist image segmentation through a protected wrapper",
    "openmm_simulate": "Run an approved OpenMM simulation script",
    "amrfinder_run": "Run NCBI AMRFinderPlus with a pinned database",
    "resfinder_run": "Run ResFinder with pinned acquired-resistance and point-mutation databases",
}


def _safe_path(path: str | Path, root: Path, *, must_exist: bool = True) -> Path:
    resolved = Path(path).expanduser().resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Path is outside the protected engine workspace: {resolved}") from exc
    if must_exist and not resolved.exists():
        raise FileNotFoundError(resolved)
    return resolved


def _safe_token(value: Any, *, field: str, pattern: str = r"[A-Za-z0-9_.:+*-]+") -> str:
    token = str(value).strip()
    if not token or not re.fullmatch(pattern, token):
        raise ValueError(f"Invalid {field}: {token!r}")
    return token


def build_step155_plan(plan_key: str, *, executable: str, workdir: Path, parameters: dict[str, Any]) -> dict[str, Any]:
    root = workdir.resolve()
    threads = max(1, min(int(parameters.get("threads", 2)), 128))
    memory_gb = max(1.0, min(float(parameters.get("memory_gb", 4)), 1024.0))
    inputs: list[str] = []
    outputs: list[str] = []
    resources = {"threads": threads, "memory_gb": memory_gb}

    if plan_key == "blastn_search":
        query = _safe_path(parameters["query"], root)
        database = _safe_path(parameters["database_prefix"], root, must_exist=False)
        output = _safe_path(parameters.get("output", root / "blastn.tsv"), root, must_exist=False)
        evalue = max(1e-300, min(float(parameters.get("evalue", 1e-5)), 1.0))
        max_targets = max(1, min(int(parameters.get("max_target_seqs", 50)), 100_000))
        command = (executable, "-query", str(query), "-db", str(database), "-outfmt", "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore", "-evalue", str(evalue), "-max_target_seqs", str(max_targets), "-num_threads", str(threads), "-out", str(output))
        inputs, outputs = [str(query), str(database)], [str(output)]
    elif plan_key == "star_align":
        index = _safe_path(parameters["genome_dir"], root)
        reads1 = _safe_path(parameters["reads1"], root)
        reads2_value = parameters.get("reads2")
        reads2 = _safe_path(reads2_value, root) if reads2_value else None
        prefix = _safe_path(parameters.get("output_prefix", root / "star_"), root, must_exist=False)
        command_list = [executable, "--genomeDir", str(index), "--readFilesIn", str(reads1)]
        if reads2 is not None:
            command_list.append(str(reads2))
        if reads1.suffix.lower() == ".gz":
            command_list += ["--readFilesCommand", "zcat"]
        command_list += ["--runThreadN", str(threads), "--outFileNamePrefix", str(prefix), "--outSAMtype", "BAM", "SortedByCoordinate"]
        command = tuple(command_list)
        inputs = [str(index), str(reads1)] + ([str(reads2)] if reads2 is not None else [])
        outputs = [str(prefix) + "Aligned.sortedByCoord.out.bam", str(prefix) + "Log.final.out"]
    elif plan_key == "rmats_splicing":
        b1 = _safe_path(parameters["b1"], root)
        b2 = _safe_path(parameters["b2"], root)
        gtf = _safe_path(parameters["gtf"], root)
        output = _safe_path(parameters.get("output_dir", root / "rmats"), root, must_exist=False)
        temp = _safe_path(parameters.get("temp_dir", root / "rmats_tmp"), root, must_exist=False)
        read_length = max(20, min(int(parameters.get("read_length", 150)), 1000))
        lib_type = _safe_token(parameters.get("lib_type", "fr-unstranded"), field="library type", pattern=r"fr-(?:unstranded|firststrand|secondstrand)")
        command = (executable, "--b1", str(b1), "--b2", str(b2), "--gtf", str(gtf), "--od", str(output), "--tmp", str(temp), "-t", "paired", "--readLength", str(read_length), "--nthread", str(threads), "--libType", lib_type)
        inputs, outputs = [str(b1), str(b2), str(gtf)], [str(output)]
    elif plan_key == "majiq_build":
        config = _safe_path(parameters["config"], root)
        output = _safe_path(parameters.get("output_dir", root / "majiq_build"), root, must_exist=False)
        annotation = _safe_path(parameters["annotation"], root)
        command = (executable, "build", str(annotation), "-c", str(config), "-o", str(output), "-j", str(threads))
        inputs, outputs = [str(config), str(annotation)], [str(output)]
    elif plan_key == "suppa2_events":
        annotation = _safe_path(parameters["annotation"], root)
        output_prefix = _safe_path(parameters.get("output_prefix", root / "suppa_events"), root, must_exist=False)
        event_type = _safe_token(parameters.get("event_type", "SE"), field="event type", pattern=r"(?:SE|SS|MX|RI|FL)")
        command = (executable, "generateEvents", "-i", str(annotation), "-o", str(output_prefix), "-f", "ioe", "-e", event_type)
        inputs, outputs = [str(annotation)], [str(output_prefix) + f"_{event_type}.strict.ioe"]
    elif plan_key == "regenie_association":
        pgen = _safe_path(parameters["pgen_prefix"], root, must_exist=False)
        phenotype = _safe_path(parameters["phenotype"], root)
        predictions = _safe_path(parameters["predictions"], root)
        output_prefix = _safe_path(parameters.get("output_prefix", root / "regenie_step2"), root, must_exist=False)
        trait = _safe_token(parameters.get("trait", "phenotype"), field="trait")
        command = (executable, "--step", "2", "--pgen", str(pgen), "--phenoFile", str(phenotype), "--phenoCol", trait, "--pred", str(predictions), "--threads", str(threads), "--out", str(output_prefix))
        inputs, outputs = [str(pgen), str(phenotype), str(predictions)], [str(output_prefix) + f"_{trait}.regenie"]
    elif plan_key == "saige_association":
        vcf = _safe_path(parameters["vcf"], root)
        vcf_index = _safe_path(parameters["vcf_index"], root)
        null_model = _safe_path(parameters["null_model"], root)
        variance_ratio = _safe_path(parameters["variance_ratio"], root)
        output = _safe_path(parameters.get("output", root / "saige_results.tsv"), root, must_exist=False)
        chromosome = _safe_token(parameters.get("chromosome", "1"), field="chromosome", pattern=r"[A-Za-z0-9_.-]+")
        command = (executable, "--vcfFile", str(vcf), "--vcfFileIndex", str(vcf_index), "--chrom", chromosome, "--GMMATmodelFile", str(null_model), "--varianceRatioFile", str(variance_ratio), "--SAIGEOutputFile", str(output), "--numLinesOutput", "2")
        inputs, outputs = [str(vcf), str(vcf_index), str(null_model), str(variance_ratio)], [str(output)]
    elif plan_key == "modkit_pileup":
        alignment = _safe_path(parameters["alignment"], root)
        reference = _safe_path(parameters["reference"], root)
        output = _safe_path(parameters.get("output", root / "modifications.bedmethyl"), root, must_exist=False)
        command = (executable, "pileup", str(alignment), str(output), "--ref", str(reference), "--threads", str(threads), "--filter-threshold", str(max(0.0, min(float(parameters.get("filter_threshold", 0.8)), 1.0))) )
        inputs, outputs = [str(alignment), str(reference)], [str(output)]
    elif plan_key == "merqury_evaluate":
        meryl_db = _safe_path(parameters["meryl_db"], root)
        assembly = _safe_path(parameters["assembly"], root)
        prefix = _safe_token(parameters.get("prefix", "merqury"), field="output prefix", pattern=r"[A-Za-z0-9_.-]+")
        command = (executable, str(meryl_db), str(assembly), prefix)
        inputs, outputs = [str(meryl_db), str(assembly)], [str(root / f"{prefix}.qv"), str(root / f"{prefix}.completeness.stats")]
    elif plan_key == "rfdiffusion_generate":
        config = _safe_path(parameters["config"], root)
        output_prefix = _safe_path(parameters.get("output_prefix", root / "rfdiffusion" / "design"), root, must_exist=False)
        designs = max(1, min(int(parameters.get("num_designs", 10)), 10_000))
        command = (executable, f"--config-path={config.parent}", f"--config-name={config.stem}", f"inference.output_prefix={output_prefix}", f"inference.num_designs={designs}")
        inputs, outputs = [str(config)], [str(output_prefix.parent)]
    elif plan_key == "stardist_segment":
        image = _safe_path(parameters["image"], root)
        output = _safe_path(parameters.get("output", root / "stardist_labels.tif"), root, must_exist=False)
        model = _safe_token(parameters.get("model", "2D_versatile_fluo"), field="StarDist model", pattern=r"[A-Za-z0-9_.-]+")
        script = _safe_path(parameters.get("wrapper_script", root / "stardist_wrapper.py"), root)
        command = (sys.executable, str(script), "--image", str(image), "--output", str(output), "--model", model)
        inputs, outputs = [str(image), str(script)], [str(output)]
    elif plan_key == "openmm_simulate":
        script = _safe_path(parameters["script"], root)
        system = _safe_path(parameters["system"], root)
        output = _safe_path(parameters.get("output", root / "openmm_output"), root, must_exist=False)
        steps = max(1, min(int(parameters.get("steps", 50_000)), 100_000_000))
        command = (executable, str(script), "--system", str(system), "--output", str(output), "--steps", str(steps))
        inputs, outputs = [str(script), str(system)], [str(output)]
    elif plan_key == "amrfinder_run":
        protein = _safe_path(parameters["protein_fasta"], root)
        nucleotide_value = parameters.get("nucleotide_fasta")
        nucleotide = _safe_path(nucleotide_value, root) if nucleotide_value else None
        output = _safe_path(parameters.get("output", root / "amrfinder.tsv"), root, must_exist=False)
        organism = str(parameters.get("organism", "")).strip()
        command_list = [executable, "-p", str(protein), "-o", str(output), "--threads", str(threads), "--plus"]
        if nucleotide is not None:
            command_list += ["-n", str(nucleotide)]
        if organism:
            command_list += ["--organism", _safe_token(organism, field="organism", pattern=r"[A-Za-z0-9_. -]+")]
        command = tuple(command_list)
        inputs = [str(protein)] + ([str(nucleotide)] if nucleotide is not None else [])
        outputs = [str(output)]
    elif plan_key == "resfinder_run":
        reads1 = _safe_path(parameters["reads1"], root)
        reads2_value = parameters.get("reads2")
        reads2 = _safe_path(reads2_value, root) if reads2_value else None
        database = _safe_path(parameters["database"], root)
        point_database = _safe_path(parameters["point_database"], root)
        output = _safe_path(parameters.get("output_dir", root / "resfinder"), root, must_exist=False)
        command_list = [executable, "-ifq", str(reads1)]
        if reads2 is not None:
            command_list += [str(reads2)]
        command_list += ["-db_res", str(database), "-db_point", str(point_database), "-o", str(output)]
        command = tuple(command_list)
        inputs = [str(reads1)] + ([str(reads2)] if reads2 is not None else []) + [str(database), str(point_database)]
        outputs = [str(output)]
    else:
        raise KeyError(plan_key)

    return {
        "command": tuple(str(item) for item in command),
        "inputs": tuple(inputs),
        "outputs": tuple(outputs),
        "description": STEP155_PLAN_DESCRIPTIONS[plan_key],
        "resources": resources,
    }


__all__ = ["STEP155_PLAN_DESCRIPTIONS", "STEP155_PLAN_REQUIREMENTS", "build_step155_plan"]
