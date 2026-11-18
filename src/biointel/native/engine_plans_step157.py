from __future__ import annotations

import re
from pathlib import Path
from typing import Any


STEP157_PLAN_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "fastqc_run": ("fastqc",),
    "multiqc_report": ("multiqc",),
    "fastp_trim": ("fastp",),
    "cutadapt_trim": ("cutadapt",),
    "snpeff_annotate": ("snpeff",),
    "interproscan_annotate": ("interproscan",),
    "hmmsearch_scan": ("hmmer",),
    "blastp_search": ("blastp",),
    "mosdepth_coverage": ("mosdepth",),
    "picard_collect_alignment_metrics": ("picard",),
    "salmon_quant": ("salmon",),
    "kallisto_quant": ("kallisto",),
}

STEP157_PLAN_DESCRIPTIONS: dict[str, str] = {
    "fastqc_run": "Run FastQC with explicit output and thread limits",
    "multiqc_report": "Aggregate versioned QC outputs with MultiQC",
    "fastp_trim": "Adapter/quality trim paired or single-end FASTQ with fastp",
    "cutadapt_trim": "Adapter trim paired or single-end FASTQ with Cutadapt",
    "snpeff_annotate": "Annotate a VCF against a pinned SnpEff genome database",
    "interproscan_annotate": "Annotate protein sequences with InterProScan",
    "hmmsearch_scan": "Search protein sequences against a pinned HMM profile database",
    "blastp_search": "Search protein queries against a pinned BLAST protein database",
    "mosdepth_coverage": "Generate bounded genome coverage summaries with mosdepth",
    "picard_collect_alignment_metrics": "Collect alignment metrics with Picard",
    "salmon_quant": "Quantify transcript abundance with a pinned Salmon index",
    "kallisto_quant": "Quantify transcript abundance with a pinned Kallisto index",
}


def _safe_path(value: str | Path, root: Path, *, must_exist: bool = True) -> Path:
    path = Path(value).expanduser().resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Path is outside the protected engine workspace: {path}") from exc
    if must_exist and not path.exists():
        raise FileNotFoundError(path)
    return path


def _token(value: Any, *, field: str, pattern: str = r"[A-Za-z0-9_.:+-]+") -> str:
    text = str(value).strip()
    if not text or re.fullmatch(pattern, text) is None:
        raise ValueError(f"Invalid {field}: {value!r}")
    return text


def _bounded_threads(parameters: dict[str, Any]) -> int:
    return max(1, min(int(parameters.get("threads", 2)), 64))


def build_step157_plan(
    plan_key: str,
    *,
    executable: str,
    workdir: Path,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    if plan_key not in STEP157_PLAN_REQUIREMENTS:
        raise KeyError(plan_key)
    root = workdir.resolve()
    threads = _bounded_threads(parameters)
    memory_gb = max(0.5, min(float(parameters.get("memory_gb", 4.0)), 512.0))
    resources: dict[str, Any] = {
        "threads": threads,
        "memory_gb": memory_gb,
        "execution_policy": "explicit-user-action-only",
        "shell": False,
        "protected_workspace": str(root),
    }
    inputs: list[str] = []
    outputs: list[str] = []

    if plan_key == "fastqc_run":
        reads = [_safe_path(item, root) for item in parameters.get("reads", [])]
        if not reads:
            single = parameters.get("read")
            if single:
                reads = [_safe_path(single, root)]
        if not reads:
            raise ValueError("At least one FASTQ input is required")
        output_dir = _safe_path(parameters.get("output_dir", root / "fastqc"), root, must_exist=False)
        command = (executable, "--threads", str(threads), "--outdir", str(output_dir), *(str(item) for item in reads))
        inputs = [str(item) for item in reads]
        outputs = [str(output_dir)]
    elif plan_key == "multiqc_report":
        source_dir = _safe_path(parameters["input_dir"], root)
        output_dir = _safe_path(parameters.get("output_dir", root / "multiqc"), root, must_exist=False)
        report_name = _token(parameters.get("report_name", "multiqc_report"), field="report name", pattern=r"[A-Za-z0-9_.-]+")
        command = (executable, str(source_dir), "--outdir", str(output_dir), "--filename", f"{report_name}.html", "--force")
        inputs, outputs = [str(source_dir)], [str(output_dir / f"{report_name}.html"), str(output_dir / f"{report_name}_data")]
    elif plan_key == "fastp_trim":
        reads1 = _safe_path(parameters["reads1"], root)
        reads2_value = parameters.get("reads2")
        reads2 = _safe_path(reads2_value, root) if reads2_value else None
        output1 = _safe_path(parameters.get("output1", root / "trimmed_R1.fastq.gz"), root, must_exist=False)
        output2 = _safe_path(parameters.get("output2", root / "trimmed_R2.fastq.gz"), root, must_exist=False) if reads2 else None
        report_json = _safe_path(parameters.get("report_json", root / "fastp.json"), root, must_exist=False)
        report_html = _safe_path(parameters.get("report_html", root / "fastp.html"), root, must_exist=False)
        minimum_length = max(1, min(int(parameters.get("minimum_length", 30)), 10_000))
        qualified_quality = max(0, min(int(parameters.get("qualified_quality", 15)), 60))
        command_list = [executable, "--in1", str(reads1), "--out1", str(output1), "--thread", str(threads), "--length_required", str(minimum_length), "--qualified_quality_phred", str(qualified_quality), "--json", str(report_json), "--html", str(report_html)]
        if reads2 and output2:
            command_list += ["--in2", str(reads2), "--out2", str(output2), "--detect_adapter_for_pe"]
        command = tuple(command_list)
        inputs = [str(reads1)] + ([str(reads2)] if reads2 else [])
        outputs = [str(output1)] + ([str(output2)] if output2 else []) + [str(report_json), str(report_html)]
    elif plan_key == "cutadapt_trim":
        reads1 = _safe_path(parameters["reads1"], root)
        reads2_value = parameters.get("reads2")
        reads2 = _safe_path(reads2_value, root) if reads2_value else None
        output1 = _safe_path(parameters.get("output1", root / "cutadapt_R1.fastq.gz"), root, must_exist=False)
        output2 = _safe_path(parameters.get("output2", root / "cutadapt_R2.fastq.gz"), root, must_exist=False) if reads2 else None
        adapter1 = _token(parameters.get("adapter1", "AGATCGGAAGAGC"), field="adapter 1", pattern=r"[ACGTNacgtn]+")
        adapter2 = _token(parameters.get("adapter2", "AGATCGGAAGAGC"), field="adapter 2", pattern=r"[ACGTNacgtn]+")
        minimum_length = max(1, min(int(parameters.get("minimum_length", 30)), 10_000))
        command_list = [executable, "-j", str(threads), "-a", adapter1, "-m", str(minimum_length), "-o", str(output1)]
        if reads2 and output2:
            command_list += ["-A", adapter2, "-p", str(output2), str(reads1), str(reads2)]
        else:
            command_list += [str(reads1)]
        command = tuple(command_list)
        inputs = [str(reads1)] + ([str(reads2)] if reads2 else [])
        outputs = [str(output1)] + ([str(output2)] if output2 else [])
    elif plan_key == "snpeff_annotate":
        source = _safe_path(parameters["vcf"], root)
        output = _safe_path(parameters.get("output", root / "snpeff_annotated.vcf"), root, must_exist=False)
        database = _token(parameters["database"], field="SnpEff database", pattern=r"[A-Za-z0-9_.-]+")
        config_value = parameters.get("config")
        config = _safe_path(config_value, root) if config_value else None
        command_list = [executable]
        if config:
            command_list += ["-c", str(config)]
        command_list += ["-noStats", database, str(source)]
        command = tuple(command_list)
        inputs = [str(source)] + ([str(config)] if config else [])
        outputs = [str(output)]
        resources["stdout_redirect"] = str(output)
    elif plan_key == "interproscan_annotate":
        fasta = _safe_path(parameters["fasta"], root)
        output_dir = _safe_path(parameters.get("output_dir", root / "interproscan"), root, must_exist=False)
        formats = str(parameters.get("formats", "TSV,JSON")).upper().replace(" ", "")
        allowed = {"TSV", "JSON", "XML", "GFF3"}
        selected = [item for item in formats.split(",") if item in allowed]
        if not selected:
            raise ValueError("At least one supported InterProScan output format is required")
        command = (executable, "-i", str(fasta), "-d", str(output_dir), "-f", ",".join(selected), "-cpu", str(threads), "-goterms", "-pa")
        inputs, outputs = [str(fasta)], [str(output_dir)]
    elif plan_key == "hmmsearch_scan":
        hmm = _safe_path(parameters["hmm_database"], root)
        fasta = _safe_path(parameters["fasta"], root)
        output = _safe_path(parameters.get("output", root / "hmmsearch.tblout"), root, must_exist=False)
        evalue = max(1e-300, min(float(parameters.get("evalue", 1e-5)), 1.0))
        command = (executable, "--cpu", str(threads), "--tblout", str(output), "-E", str(evalue), str(hmm), str(fasta))
        inputs, outputs = [str(hmm), str(fasta)], [str(output)]
    elif plan_key == "blastp_search":
        query = _safe_path(parameters["query"], root)
        database = _safe_path(parameters["database_prefix"], root, must_exist=False)
        output = _safe_path(parameters.get("output", root / "blastp.tsv"), root, must_exist=False)
        evalue = max(1e-300, min(float(parameters.get("evalue", 1e-5)), 1.0))
        max_targets = max(1, min(int(parameters.get("max_target_seqs", 50)), 100_000))
        command = (executable, "-query", str(query), "-db", str(database), "-out", str(output), "-outfmt", "6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore", "-evalue", str(evalue), "-max_target_seqs", str(max_targets), "-num_threads", str(threads))
        inputs, outputs = [str(query), str(database)], [str(output)]
    elif plan_key == "mosdepth_coverage":
        alignment = _safe_path(parameters["alignment"], root)
        prefix = _safe_path(parameters.get("output_prefix", root / "mosdepth"), root, must_exist=False)
        command_list = [executable, "--threads", str(threads), "--fast-mode"]
        regions_value = parameters.get("regions")
        if regions_value:
            regions = _safe_path(regions_value, root)
            command_list += ["--by", str(regions)]
            inputs.append(str(regions))
        command_list += [str(prefix), str(alignment)]
        command = tuple(command_list)
        inputs = [str(alignment), *inputs]
        outputs = [str(prefix) + ".mosdepth.summary.txt", str(prefix) + ".regions.bed.gz", str(prefix) + ".global.dist.txt"]
    elif plan_key == "picard_collect_alignment_metrics":
        alignment = _safe_path(parameters["alignment"], root)
        reference = _safe_path(parameters["reference"], root)
        output = _safe_path(parameters.get("output", root / "picard_alignment_metrics.txt"), root, must_exist=False)
        command = (executable, "CollectAlignmentSummaryMetrics", f"I={alignment}", f"O={output}", f"R={reference}", "VALIDATION_STRINGENCY=STRICT")
        inputs, outputs = [str(alignment), str(reference)], [str(output)]
    elif plan_key == "salmon_quant":
        index = _safe_path(parameters["index"], root)
        reads1 = _safe_path(parameters["reads1"], root)
        reads2_value = parameters.get("reads2")
        reads2 = _safe_path(reads2_value, root) if reads2_value else None
        output_dir = _safe_path(parameters.get("output_dir", root / "salmon_quant"), root, must_exist=False)
        library_type = _token(parameters.get("library_type", "A"), field="library type", pattern=r"[A-Za-z0-9]+")
        command_list = [executable, "quant", "-i", str(index), "-l", library_type, "-p", str(threads), "-o", str(output_dir)]
        if reads2:
            command_list += ["-1", str(reads1), "-2", str(reads2), "--validateMappings"]
        else:
            command_list += ["-r", str(reads1), "--validateMappings"]
        command = tuple(command_list)
        inputs = [str(index), str(reads1)] + ([str(reads2)] if reads2 else [])
        outputs = [str(output_dir / "quant.sf"), str(output_dir / "meta_info.json")]
    elif plan_key == "kallisto_quant":
        index = _safe_path(parameters["index"], root)
        reads1 = _safe_path(parameters["reads1"], root)
        reads2_value = parameters.get("reads2")
        reads2 = _safe_path(reads2_value, root) if reads2_value else None
        output_dir = _safe_path(parameters.get("output_dir", root / "kallisto_quant"), root, must_exist=False)
        bootstraps = max(0, min(int(parameters.get("bootstraps", 100)), 10_000))
        command_list = [executable, "quant", "-i", str(index), "-o", str(output_dir), "-t", str(threads), "-b", str(bootstraps)]
        if reads2:
            command_list += [str(reads1), str(reads2)]
        else:
            fragment_length = max(1.0, min(float(parameters.get("fragment_length", 200.0)), 10_000.0))
            fragment_sd = max(0.1, min(float(parameters.get("fragment_sd", 20.0)), 1_000.0))
            command_list += ["--single", "-l", str(fragment_length), "-s", str(fragment_sd), str(reads1)]
        command = tuple(command_list)
        inputs = [str(index), str(reads1)] + ([str(reads2)] if reads2 else [])
        outputs = [str(output_dir / "abundance.tsv"), str(output_dir / "run_info.json")]
    else:  # pragma: no cover - guarded by requirements mapping
        raise KeyError(plan_key)

    return {
        "command": tuple(str(item) for item in command),
        "inputs": tuple(inputs),
        "outputs": tuple(outputs),
        "description": STEP157_PLAN_DESCRIPTIONS[plan_key],
        "resources": resources,
    }


__all__ = ["STEP157_PLAN_DESCRIPTIONS", "STEP157_PLAN_REQUIREMENTS", "build_step157_plan"]
