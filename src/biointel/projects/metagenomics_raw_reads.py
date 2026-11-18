from __future__ import annotations

import shlex
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from biointel.tools.runtime import run_tool, tool_available


@dataclass(frozen=True)
class RawReadStep:
    name: str
    executable: str
    arguments: tuple[str, ...]
    output_files: tuple[str, ...]
    available: bool
    purpose: str

    @property
    def command(self) -> list[str]:
        return [self.executable, *self.arguments]


@dataclass(frozen=True)
class RawReadPlan:
    sample_id: str
    paired_end: bool
    database_label: str
    steps: tuple[RawReadStep, ...]
    warnings: tuple[str, ...]
    database_release: str = "not declared"
    database_checksum: str = "not declared"
    container_image: str = "not declared"


def build_raw_read_plan(
    *,
    sample_id: str,
    read_1: str,
    read_2: str | None = None,
    output_directory: str = "metagenomics_output",
    host_index: str | None = None,
    kraken_database: str | None = None,
    metaphlan_database: str | None = None,
    database_release: str | None = None,
    database_checksum: str | None = None,
    container_image: str | None = None,
    threads: int = 4,
) -> RawReadPlan:
    clean_sample = "".join(character for character in sample_id if character.isalnum() or character in {"-", "_"})
    if not clean_sample:
        raise ValueError("Sample identifier must contain letters, digits, hyphens or underscores.")
    if threads < 1 or threads > 256:
        raise ValueError("Threads must be between 1 and 256.")
    paired = bool(read_2)
    output = Path(output_directory)
    trimmed_r1 = str(output / f"{clean_sample}.trimmed.R1.fastq.gz")
    trimmed_r2 = str(output / f"{clean_sample}.trimmed.R2.fastq.gz")
    fastp_args = ["-i", read_1, "-o", trimmed_r1, "--thread", str(threads), "--html", str(output / f"{clean_sample}.fastp.html"), "--json", str(output / f"{clean_sample}.fastp.json")]
    if paired:
        fastp_args.extend(["-I", str(read_2), "-O", trimmed_r2, "--detect_adapter_for_pe"])
    steps = [
        RawReadStep("Read QC and trimming", "fastp", tuple(fastp_args), tuple([trimmed_r1, *([trimmed_r2] if paired else [])]), tool_available("fastp"), "Adapter, quality and poly-G/poly-X filtering"),
    ]
    current_r1, current_r2 = trimmed_r1, trimmed_r2 if paired else None
    if host_index:
        host_prefix = str(output / f"{clean_sample}.host_depleted")
        host_args = ["-x", host_index, "-p", str(threads)]
        if paired:
            host_args.extend(["-1", current_r1, "-2", str(current_r2), "--un-conc-gz", host_prefix + ".R%.fastq.gz"])
            depleted_outputs = (host_prefix + ".R1.fastq.gz", host_prefix + ".R2.fastq.gz")
        else:
            host_args.extend(["-U", current_r1, "--un-gz", host_prefix + ".fastq.gz"])
            depleted_outputs = (host_prefix + ".fastq.gz",)
        steps.append(RawReadStep("Host-read depletion", "bowtie2", tuple(host_args), depleted_outputs, tool_available("bowtie2"), "Remove reads mapping to the declared host reference"))
        current_r1 = depleted_outputs[0]
        current_r2 = depleted_outputs[1] if paired else None
    if kraken_database:
        report = str(output / f"{clean_sample}.kraken.report.tsv")
        labels = str(output / f"{clean_sample}.kraken.labels.txt")
        args = ["--db", kraken_database, "--threads", str(threads), "--report", report, "--output", labels]
        if paired:
            args.extend(["--paired", current_r1, str(current_r2)])
        else:
            args.append(current_r1)
        steps.append(RawReadStep("Taxonomic classification", "kraken2", tuple(args), (report, labels), tool_available("kraken2"), "Classify reads against the declared Kraken2 database"))
        bracken_output = str(output / f"{clean_sample}.bracken.species.tsv")
        steps.append(RawReadStep("Abundance re-estimation", "bracken", ("-d", kraken_database, "-i", report, "-o", bracken_output, "-r", "150", "-l", "S"), (bracken_output,), tool_available("bracken"), "Re-estimate species abundance from Kraken2 assignments"))
    if metaphlan_database:
        profile = str(output / f"{clean_sample}.metaphlan.tsv")
        inputs = f"{current_r1},{current_r2}" if paired else current_r1
        steps.append(RawReadStep("Marker-based taxonomic profile", "metaphlan", (inputs, "--input_type", "fastq", "--nproc", str(threads), "--bowtie2db", metaphlan_database, "-o", profile), (profile,), tool_available("metaphlan"), "Independent marker-based taxonomic profile"))
    multiqc_output = str(output / "multiqc_report.html")
    steps.append(RawReadStep("Multi-sample QC aggregation", "multiqc", (str(output), "-o", str(output)), (multiqc_output,), tool_available("multiqc"), "Aggregate Fastp and classifier reports"))
    warnings = ["Commands are generated as argument lists; review paths and resources before execution."]
    if not database_release:
        warnings.append("Reference database release is not declared.")
    if not database_checksum:
        warnings.append("Reference database checksum is not declared.")
    if not container_image:
        warnings.append("Container image/digest is not declared; local executable versions must be recorded separately.")
    unavailable = [step.executable for step in steps if not step.available]
    if unavailable:
        warnings.append("Unavailable executables: " + ", ".join(sorted(set(unavailable))))
    return RawReadPlan(
        sample_id=clean_sample,
        paired_end=paired,
        database_label=kraken_database or metaphlan_database or "not declared",
        steps=tuple(steps),
        warnings=tuple(warnings),
        database_release=database_release or "not declared",
        database_checksum=database_checksum or "not declared",
        container_image=container_image or "not declared",
    )


def plan_table(plan: RawReadPlan) -> list[dict[str, object]]:
    return [
        {
            "step": index + 1,
            "name": step.name,
            "executable": step.executable,
            "available": step.available,
            "purpose": step.purpose,
            "command": shlex.join(step.command),
            "outputs": "; ".join(step.output_files),
        }
        for index, step in enumerate(plan.steps)
    ]


def plan_dict(plan: RawReadPlan) -> dict[str, object]:
    return asdict(plan)


def execute_raw_read_plan(
    plan: RawReadPlan,
    *,
    working_directory: str | Path | None = None,
    stop_on_error: bool = True,
    timeout_seconds: int = 86_400,
    resume: bool = True,
) -> list[dict[str, object]]:
    """Execute an explicitly reviewed raw-read plan without invoking a shell.

    Each step is launched as an argument list, stdout/stderr are captured, and
    unavailable tools are reported rather than silently skipped. This function
    does not download databases or infer licences on the user's behalf.
    """
    import hashlib
    import time

    def sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    if timeout_seconds < 1:
        raise ValueError("Execution timeout must be positive.")
    cwd = Path(working_directory).resolve() if working_directory else None
    if cwd:
        cwd.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for index, step in enumerate(plan.steps, start=1):
        started = time.perf_counter()
        output_paths = [Path(path) if Path(path).is_absolute() or cwd is None else cwd / path for path in step.output_files]
        if resume and output_paths and all(path.exists() and path.stat().st_size > 0 for path in output_paths):
            rows.append({
                "step": index,
                "name": step.name,
                "status": "resumed_existing",
                "return_code": 0,
                "elapsed_seconds": 0.0,
                "stdout_tail": "",
                "stderr_tail": "",
                "outputs_present": True,
                "output_sha256": "; ".join(f"{path.name}:{sha256_file(path)}" for path in output_paths),
            })
            continue
        if not step.available:
            row = {
                "step": index,
                "name": step.name,
                "status": "unavailable",
                "return_code": None,
                "elapsed_seconds": 0.0,
                "stdout_tail": "",
                "stderr_tail": f"Executable not available: {step.executable}",
                "outputs_present": False,
                "output_sha256": "",
            }
            rows.append(row)
            if stop_on_error:
                break
            continue
        try:
            completed = run_tool(
                step.executable,
                step.arguments,
                cwd=str(cwd) if cwd else None,
                timeout_seconds=int(timeout_seconds),
                check=False,
            )
            outputs_present = all(path.exists() for path in output_paths) if output_paths else True
            status = "completed" if completed.returncode == 0 and outputs_present else "failed"
            rows.append(
                {
                    "step": index,
                    "name": step.name,
                    "status": status,
                    "return_code": int(completed.returncode),
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "stdout_tail": completed.stdout[-4000:],
                    "stderr_tail": completed.stderr[-4000:],
                    "outputs_present": bool(outputs_present),
                    "output_sha256": "; ".join(f"{path.name}:{sha256_file(path)}" for path in output_paths if path.exists()),
                }
            )
            if status != "completed" and stop_on_error:
                break
        except subprocess.TimeoutExpired as exc:
            rows.append(
                {
                    "step": index,
                    "name": step.name,
                    "status": "timeout",
                    "return_code": None,
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
                    "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
                    "outputs_present": False,
                    "output_sha256": "",
                }
            )
            if stop_on_error:
                break
    return rows
