from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

STEP156_PLAN_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "bgzip_compress": ("bgzip",),
    "minimap2_align": ("minimap2",),
    "bwa_mem_align": ("bwa",),
    "obabel_prepare_ligand": ("obabel",),
    "openslide_inspect": ("openslide",),
    "scanpy_analyze": ("scanpy",),
    "scvelo_velocity": ("scvelo",),
    "cellrank_fates": ("cellrank",),
    "msgfplus_search": ("msgfplus",),
    "abricate_screen": ("abricate",),
    "llama_cpp_infer": ("llama_cpp",),
}

STEP156_PLAN_DESCRIPTIONS: dict[str, str] = {
    "bgzip_compress": "Create block-gzip compressed genomic data",
    "minimap2_align": "Align long reads or assemblies with minimap2",
    "bwa_mem_align": "Align paired short reads with BWA-MEM/BWA-MEM2",
    "obabel_prepare_ligand": "Generate a protonated 3D ligand representation",
    "openslide_inspect": "Inspect whole-slide metadata using a bounded Python wrapper",
    "scanpy_analyze": "Run a pinned Scanpy QC/clustering wrapper",
    "scvelo_velocity": "Run a pinned scVelo velocity wrapper",
    "cellrank_fates": "Run a pinned CellRank fate-probability wrapper",
    "msgfplus_search": "Search spectra with MS-GF+",
    "abricate_screen": "Screen an assembly against a pinned ABRicate database",
    "llama_cpp_infer": "Run local approved-model inference with bounded context and output",
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


def build_step156_plan(plan_key: str, *, executable: str, workdir: Path, parameters: dict[str, Any]) -> dict[str, Any]:
    if plan_key not in STEP156_PLAN_REQUIREMENTS:
        raise KeyError(plan_key)
    root = workdir.resolve()
    threads = max(1, min(int(parameters.get("threads", 2)), 64))
    memory_gb = max(0.5, min(float(parameters.get("memory_gb", 4)), 512.0))
    resources = {"threads": threads, "memory_gb": memory_gb, "execution_policy": "explicit-user-action-only"}
    inputs: list[str] = []
    outputs: list[str] = []

    if plan_key == "bgzip_compress":
        source = _safe_path(parameters["source"], root)
        output = _safe_path(parameters.get("output", Path(str(source) + ".gz")), root, must_exist=False)
        command = (executable, "-@", str(threads), "-c", str(source))
        inputs, outputs = [str(source)], [str(output)]
        resources["stdout_redirect"] = str(output)
    elif plan_key == "minimap2_align":
        reference = _safe_path(parameters["reference"], root)
        reads = _safe_path(parameters["reads"], root)
        output = _safe_path(parameters.get("output", root / "minimap2.sam"), root, must_exist=False)
        preset = _token(parameters.get("preset", "map-ont"), field="minimap2 preset", pattern=r"(?:map-ont|map-hifi|map-pb|asm5|asm10|asm20|sr)")
        command = (executable, "-x", preset, "-t", str(threads), "-a", str(reference), str(reads))
        inputs, outputs = [str(reference), str(reads)], [str(output)]
        resources["stdout_redirect"] = str(output)
    elif plan_key == "bwa_mem_align":
        reference = _safe_path(parameters["reference"], root)
        reads1 = _safe_path(parameters["reads1"], root)
        reads2_value = parameters.get("reads2")
        reads2 = _safe_path(reads2_value, root) if reads2_value else None
        output = _safe_path(parameters.get("output", root / "bwa.sam"), root, must_exist=False)
        command_list = [executable, "mem", "-t", str(threads), str(reference), str(reads1)]
        if reads2 is not None:
            command_list.append(str(reads2))
        command = tuple(command_list)
        inputs = [str(reference), str(reads1)] + ([str(reads2)] if reads2 is not None else [])
        outputs = [str(output)]
        resources["stdout_redirect"] = str(output)
    elif plan_key == "obabel_prepare_ligand":
        source = _safe_path(parameters["ligand"], root)
        output = _safe_path(parameters.get("output", root / "prepared_ligand.sdf"), root, must_exist=False)
        ph = max(0.0, min(float(parameters.get("ph", 7.4)), 14.0))
        conformers = max(1, min(int(parameters.get("conformers", 1)), 1000))
        command = (executable, str(source), "-O", str(output), "--gen3d", "--pH", str(ph), "--conformer", "--nconf", str(conformers))
        inputs, outputs = [str(source)], [str(output)]
    elif plan_key in {"openslide_inspect", "scanpy_analyze", "scvelo_velocity", "cellrank_fates"}:
        script = _safe_path(parameters["wrapper_script"], root)
        source = _safe_path(parameters["input"], root)
        output = _safe_path(parameters.get("output", root / f"{plan_key}.json"), root, must_exist=False)
        command = (sys.executable, str(script), "--input", str(source), "--output", str(output), "--threads", str(threads))
        inputs, outputs = [str(script), str(source)], [str(output)]
    elif plan_key == "msgfplus_search":
        spectra = _safe_path(parameters["spectra"], root)
        database = _safe_path(parameters["database_fasta"], root)
        output = _safe_path(parameters.get("output", root / "msgfplus.mzid"), root, must_exist=False)
        tolerance = max(0.1, min(float(parameters.get("precursor_tolerance_ppm", 10.0)), 1000.0))
        command = (executable, "-s", str(spectra), "-d", str(database), "-o", str(output), "-t", f"{tolerance}ppm", "-thread", str(threads), "-tda", "1")
        inputs, outputs = [str(spectra), str(database)], [str(output)]
    elif plan_key == "abricate_screen":
        assembly = _safe_path(parameters["assembly"], root)
        output = _safe_path(parameters.get("output", root / "abricate.tsv"), root, must_exist=False)
        database = _token(parameters.get("database", "ncbi"), field="ABRicate database", pattern=r"[A-Za-z0-9_.-]+")
        minid = max(0.0, min(float(parameters.get("minimum_identity", 80.0)), 100.0))
        mincov = max(0.0, min(float(parameters.get("minimum_coverage", 80.0)), 100.0))
        command = (executable, "--db", database, "--minid", str(minid), "--mincov", str(mincov), str(assembly))
        inputs, outputs = [str(assembly)], [str(output)]
        resources["stdout_redirect"] = str(output)
    elif plan_key == "llama_cpp_infer":
        model = _safe_path(parameters["model"], root)
        prompt = _safe_path(parameters["prompt_file"], root)
        output = _safe_path(parameters.get("output", root / "llama_response.txt"), root, must_exist=False)
        context = max(256, min(int(parameters.get("context_size", 4096)), 131072))
        tokens = max(1, min(int(parameters.get("max_tokens", 512)), 8192))
        temperature = max(0.0, min(float(parameters.get("temperature", 0.2)), 2.0))
        command = (executable, "-m", str(model), "-f", str(prompt), "-c", str(context), "-n", str(tokens), "--temp", str(temperature), "--no-display-prompt")
        inputs, outputs = [str(model), str(prompt)], [str(output)]
        resources["stdout_redirect"] = str(output)
    else:
        raise KeyError(plan_key)

    return {
        "command": tuple(str(item) for item in command),
        "inputs": tuple(inputs),
        "outputs": tuple(outputs),
        "description": STEP156_PLAN_DESCRIPTIONS[plan_key],
        "resources": resources,
    }


__all__ = ["STEP156_PLAN_DESCRIPTIONS", "STEP156_PLAN_REQUIREMENTS", "build_step156_plan"]
