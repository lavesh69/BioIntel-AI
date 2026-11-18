from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from biointel.quality10.provenance import atomic_write_json
from biointel.tools.runtime import resolve_tool, run_tool_audited, verified_tool_status

AA20 = frozenset("ACDEFGHIKLMNPQRSTVWY")
BACKENDS = ("proteinmpnn", "rfdiffusion", "colabfold_batch", "foldx", "rosetta_scripts")
_BACKEND_LABELS = {
    "proteinmpnn": "ProteinMPNN sequence design",
    "rfdiffusion": "RFdiffusion backbone generation",
    "colabfold_batch": "ColabFold structure validation",
    "foldx": "FoldX mutation stability rescoring",
    "rosetta_scripts": "Rosetta protocol execution",
}
_ASSET_ENV = {
    "proteinmpnn": "BIOINTEL_PROTEINMPNN_WEIGHTS",
    "rfdiffusion": "BIOINTEL_RFDIFFUSION_WEIGHTS",
    "colabfold_batch": "BIOINTEL_COLABFOLD_PARAMS",
    "foldx": "BIOINTEL_FOLDX_HOME",
    "rosetta_scripts": "BIOINTEL_ROSETTA_DATABASE",
}
_ASSET_REQUIRED = {"proteinmpnn", "rfdiffusion", "colabfold_batch", "rosetta_scripts"}


@dataclass(frozen=True)
class ProteinDesignPlan:
    schema: str
    run_id: str
    backend: str
    label: str
    run_directory: str
    input_path: str
    output_directory: str
    arguments: tuple[str, ...]
    parameters: dict[str, Any]
    input_sha256: str
    executable_status: dict[str, Any]
    asset_status: dict[str, Any]
    hardware: dict[str, Any]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    release_boundary: str

    @property
    def executable(self) -> bool:
        return not self.blockers

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["executable"] = self.executable
        return payload


@dataclass(frozen=True)
class ProteinDesignRunResult:
    schema: str
    run_id: str
    backend: str
    status: str
    resumed: bool
    run_directory: str
    manifest_path: str
    execution_manifest_path: str
    outputs: pd.DataFrame
    candidates: pd.DataFrame
    release_gate: dict[str, Any]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_tree(path: Path) -> str:
    if path.is_file():
        return _hash_file(path)
    digest = sha256()
    for item in sorted((entry for entry in path.rglob("*") if entry.is_file()), key=lambda entry: entry.as_posix().lower()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(_hash_file(item).encode("ascii"))
    return digest.hexdigest()


def _asset_fingerprint(path: Path) -> dict[str, int]:
    files = [path] if path.is_file() else [item for item in path.rglob("*") if item.is_file()]
    return {
        "file_count": len(files),
        "total_size_bytes": sum(item.stat().st_size for item in files),
        "latest_mtime_ns": max((item.stat().st_mtime_ns for item in files), default=path.stat().st_mtime_ns),
    }


def _safe_name(value: str, fallback: str = "design") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip()).strip("._")
    return cleaned[:80] or fallback


def _safe_inside(path: str | Path, root: str | Path, *, must_exist: bool = False) -> Path:
    resolved = Path(path).expanduser().resolve()
    base = Path(root).expanduser().resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Path is outside the protected protein-design workspace: {resolved}") from exc
    if must_exist and not resolved.exists():
        raise FileNotFoundError(resolved)
    return resolved


def _validate_sequence(sequence: str) -> str:
    clean = "".join(line.strip() for line in str(sequence).splitlines() if not line.lstrip().startswith(">"))
    clean = re.sub(r"\s+", "", clean).upper()
    if not clean:
        raise ValueError("Protein sequence is empty")
    invalid = sorted(set(clean) - AA20)
    if invalid:
        raise ValueError("Unsupported amino-acid symbols: " + ", ".join(invalid))
    if len(clean) > 10000:
        raise ValueError("Protein sequence exceeds the protected 10,000-residue limit")
    return clean


def _parse_positions(values: Sequence[int] | str | None, *, sequence_length: int | None = None) -> tuple[int, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        parsed = [int(item) for item in re.findall(r"\d+", values)]
    else:
        parsed = [int(item) for item in values]
    unique = tuple(sorted(set(parsed)))
    if any(value < 1 for value in unique):
        raise ValueError("Residue positions are 1-based and must be positive")
    if sequence_length is not None and any(value > sequence_length for value in unique):
        raise ValueError("A residue position is outside the protein sequence")
    return unique


def _parse_pdb_summary(path: Path) -> dict[str, Any]:
    chains: dict[str, set[int]] = {}
    residues: set[tuple[str, int, str]] = set()
    atom_count = 0
    models: set[int] = set()
    current_model = 1
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("MODEL"):
            try:
                current_model = int(line[10:14].strip() or "1")
            except ValueError:
                current_model += 1
        if not line.startswith(("ATOM  ", "HETATM")):
            continue
        atom_count += 1
        models.add(current_model)
        chain = (line[21:22].strip() or "_") if len(line) > 21 else "_"
        try:
            residue_number = int(line[22:26].strip())
        except (ValueError, IndexError):
            continue
        residue = line[17:20].strip() if len(line) >= 20 else "UNK"
        chains.setdefault(chain, set()).add(residue_number)
        residues.add((chain, residue_number, residue))
    if atom_count == 0:
        raise ValueError("The PDB input contains no ATOM/HETATM records")
    return {
        "atom_count": atom_count,
        "residue_count": len(residues),
        "chains": {key: {"residue_count": len(value), "minimum": min(value), "maximum": max(value), "positions": sorted(value)} for key, value in sorted(chains.items())},
        "model_count": len(models) or 1,
    }


def stage_protein_design_input(
    *,
    workspace: str | Path,
    source_path: str | Path | None = None,
    source_bytes: bytes | None = None,
    filename: str | None = None,
    sequence: str | None = None,
    run_name: str = "protein-design",
) -> dict[str, Any]:
    """Stage one immutable PDB or FASTA input under a protected run directory."""
    root = Path(workspace).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_id = f"{_safe_name(run_name)}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{os.urandom(3).hex()}"
    run_dir = root / run_id
    input_dir = run_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=False)

    supplied = sum(value is not None for value in (source_path, source_bytes, sequence))
    if supplied != 1:
        raise ValueError("Provide exactly one of source_path, source_bytes, or sequence")
    if source_path is not None:
        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        target = input_dir / _safe_name(source.name, "input.pdb")
        shutil.copy2(source, target)
    elif source_bytes is not None:
        target = input_dir / _safe_name(filename or "input.pdb", "input.pdb")
        target.write_bytes(source_bytes)
    else:
        clean = _validate_sequence(sequence or "")
        target = input_dir / _safe_name(filename or "input.fasta", "input.fasta")
        if target.suffix.lower() not in {".fa", ".fasta", ".faa"}:
            target = target.with_suffix(".fasta")
        target.write_text(f">BioIntel_input\n{clean}\n", encoding="utf-8")

    suffix = target.suffix.lower()
    if suffix not in {".pdb", ".ent", ".fa", ".fasta", ".faa"}:
        raise ValueError("Protein design accepts PDB/ENT or protein FASTA input")
    summary: dict[str, Any]
    input_kind: str
    if suffix in {".pdb", ".ent"}:
        input_kind = "structure"
        summary = _parse_pdb_summary(target)
    else:
        input_kind = "sequence"
        summary = {"sequence_length": len(_validate_sequence(target.read_text(encoding="utf-8")))}
    payload = {
        "schema": "biointel.step122.protein_design_input.v1",
        "run_id": run_id,
        "created_at": _utc_now(),
        "run_directory": str(run_dir),
        "input_path": str(target),
        "input_kind": input_kind,
        "input_sha256": _hash_file(target),
        "input_size_bytes": target.stat().st_size,
        "summary": summary,
    }
    atomic_write_json(run_dir / "input_manifest.json", payload)
    return payload


def _memory_gb() -> float | None:
    try:
        if hasattr(os, "sysconf"):
            pages = int(os.sysconf("SC_PHYS_PAGES"))
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            return round(pages * page_size / (1024**3), 2)
    except (OSError, ValueError, TypeError):
        return None
    return None


def _gpu_profile() -> dict[str, Any]:
    profile: dict[str, Any] = {"torch_available": False, "cuda_available": False, "device_count": 0, "devices": []}
    try:
        import torch

        profile["torch_available"] = True
        profile["torch_version"] = str(torch.__version__)
        profile["cuda_available"] = bool(torch.cuda.is_available())
        profile["device_count"] = int(torch.cuda.device_count()) if torch.cuda.is_available() else 0
        for index in range(int(profile["device_count"])):
            props = torch.cuda.get_device_properties(index)
            profile["devices"].append({
                "index": index,
                "name": props.name,
                "memory_gb": round(props.total_memory / (1024**3), 2),
                "capability": f"{props.major}.{props.minor}",
            })
    except Exception as exc:
        profile["probe_error"] = f"{type(exc).__name__}: {exc}"
    return profile


def _asset_registry_path(workspace: str | Path) -> Path:
    return Path(workspace).expanduser().resolve() / "model_assets.json"


def _load_asset_registry(workspace: str | Path) -> dict[str, Any]:
    path = _asset_registry_path(workspace)
    if not path.is_file():
        return {"schema": "biointel.step122.model_assets.v1", "assets": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema": "biointel.step122.model_assets.v1", "assets": {}}
    return payload if isinstance(payload, dict) else {"schema": "biointel.step122.model_assets.v1", "assets": {}}


def register_model_asset(
    backend: str,
    path: str | Path,
    *,
    workspace: str | Path,
    expected_sha256: str = "",
    license_accepted: bool = False,
    source: str = "manual registration",
) -> dict[str, Any]:
    if backend not in BACKENDS:
        raise ValueError(f"Unsupported backend: {backend}")
    asset = Path(path).expanduser().resolve()
    if not asset.exists():
        raise FileNotFoundError(asset)
    digest = _hash_tree(asset)
    expected = expected_sha256.strip().lower()
    if expected and digest.lower() != expected:
        raise ValueError("Model asset SHA-256 does not match the expected digest")
    registry = _load_asset_registry(workspace)
    assets = registry.setdefault("assets", {})
    record = {
        "backend": backend,
        "path": str(asset),
        "kind": "directory" if asset.is_dir() else "file",
        "sha256": digest,
        "fingerprint": _asset_fingerprint(asset),
        "expected_sha256": expected,
        "checksum_verified": bool(expected),
        "license_accepted": bool(license_accepted),
        "source": source,
        "registered_at": _utc_now(),
    }
    assets[backend] = record
    registry["updated_at"] = _utc_now()
    atomic_write_json(_asset_registry_path(workspace), registry)
    return record


def _model_asset_status(backend: str, workspace: str | Path) -> dict[str, Any]:
    registry = _load_asset_registry(workspace)
    record = dict(registry.get("assets", {}).get(backend, {}))
    env_name = _ASSET_ENV.get(backend, "")
    env_path = os.environ.get(env_name, "").strip() if env_name else ""
    if env_path:
        record.setdefault("path", env_path)
        record.setdefault("source", f"environment:{env_name}")
        record.setdefault("license_accepted", False)
        record.setdefault("expected_sha256", "")
    path_text = str(record.get("path", "")).strip()
    path = Path(path_text).expanduser().resolve() if path_text else None
    exists = bool(path and path.exists())
    expected = str(record.get("expected_sha256", "")).strip().lower()
    registered_hash = str(record.get("sha256", "")).strip().lower()
    registered_fingerprint = record.get("fingerprint") if isinstance(record.get("fingerprint"), dict) else {}
    current_fingerprint = _asset_fingerprint(path) if exists and path else {}
    fingerprint_match = bool(registered_fingerprint and current_fingerprint == registered_fingerprint)
    current_hash = registered_hash if fingerprint_match else (_hash_tree(path) if exists and path and (registered_hash or expected) else "")
    checksum_match = bool(exists and ((expected and current_hash.lower() == expected) or (not expected and registered_hash and current_hash.lower() == registered_hash)))
    return {
        "backend": backend,
        "environment_variable": env_name,
        "required": backend in _ASSET_REQUIRED,
        "path": str(path) if path else "",
        "exists": exists,
        "kind": "directory" if path and path.is_dir() else "file" if path and path.is_file() else "missing",
        "sha256": current_hash,
        "expected_sha256": expected,
        "registered_sha256": registered_hash,
        "fingerprint": current_fingerprint,
        "fingerprint_match": fingerprint_match,
        "checksum_match": checksum_match,
        "license_accepted": bool(record.get("license_accepted", False)),
        "source": record.get("source", "not registered"),
    }


def protein_design_preflight(workspace: str | Path) -> dict[str, Any]:
    workspace_path = Path(workspace).expanduser().resolve()
    workspace_path.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(workspace_path)
    hardware = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count() or 1,
        "memory_gb": _memory_gb(),
        "workspace_free_gb": round(usage.free / (1024**3), 2),
        "gpu": _gpu_profile(),
    }
    rows = []
    for backend in BACKENDS:
        resolution = resolve_tool(backend)
        asset = _model_asset_status(backend, workspace_path)
        blockers: list[str] = []
        if not resolution.available:
            blockers.append("Executable not detected")
        if asset["required"] and not asset["exists"]:
            blockers.append("Model parameters/database not registered")
        if asset["required"] and asset["exists"] and not asset["checksum_match"]:
            blockers.append("Model asset checksum is unverified or changed")
        if asset["required"] and not asset["license_accepted"]:
            blockers.append("Model/data licence acceptance not recorded")
        if backend == "rfdiffusion" and not hardware["gpu"]["cuda_available"]:
            blockers.append("CUDA GPU not detected")
        rows.append({
            "backend": backend,
            "label": _BACKEND_LABELS[backend],
            "executable_available": resolution.available,
            "backend_type": resolution.backend,
            "executable": resolution.executable or "",
            "model_asset_exists": asset["exists"],
            "model_asset_checksum_verified": asset["checksum_match"],
            "license_accepted": asset["license_accepted"],
            "cuda_available": hardware["gpu"]["cuda_available"],
            "status": "Ready" if not blockers else "Blocked",
            "blockers": "; ".join(blockers),
        })
    return {
        "schema": "biointel.step122.protein_design_preflight.v1",
        "hardware": hardware,
        "backends": pd.DataFrame(rows),
        "assets": {backend: _model_asset_status(backend, workspace_path) for backend in BACKENDS},
        "boundary": "Readiness verifies local execution prerequisites; it does not validate scientific performance or grant licences.",
    }


def _validate_pdb_input(path: Path) -> dict[str, Any]:
    if path.suffix.lower() not in {".pdb", ".ent"}:
        raise ValueError("This backend requires a staged PDB/ENT structure")
    return _parse_pdb_summary(path)


def _validate_fasta_input(path: Path) -> str:
    if path.suffix.lower() not in {".fa", ".fasta", ".faa"}:
        raise ValueError("This backend requires a staged protein FASTA")
    return _validate_sequence(path.read_text(encoding="utf-8"))


def _run_id_from_directory(run_dir: Path) -> str:
    return run_dir.name


def build_protein_design_plan(
    backend: str,
    *,
    run_directory: str | Path,
    input_path: str | Path,
    parameters: Mapping[str, Any] | None = None,
) -> ProteinDesignPlan:
    if backend not in BACKENDS:
        raise ValueError(f"Unsupported backend: {backend}")
    params = dict(parameters or {})
    run_dir = Path(run_directory).expanduser().resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    source = _safe_inside(input_path, run_dir, must_exist=True)
    output = run_dir / "outputs" / backend
    output.mkdir(parents=True, exist_ok=True)
    workspace = run_dir.parent
    preflight = protein_design_preflight(workspace)
    hardware = preflight["hardware"]
    resolution = verified_tool_status(backend)
    asset = _model_asset_status(backend, workspace)
    blockers: list[str] = []
    warnings: list[str] = []
    if not bool(resolution.get("available")):
        blockers.append(f"{backend} executable is not detected")
    if asset["required"]:
        if not asset["exists"]:
            blockers.append(f"{backend} model parameters/database are not registered")
        elif not asset["checksum_match"]:
            blockers.append(f"{backend} model asset checksum is unverified or changed")
        if not asset["license_accepted"]:
            blockers.append(f"{backend} licence acceptance is not recorded")
    threads = max(1, min(int(params.get("threads", max(1, min(os.cpu_count() or 1, 8)))), 128))
    seed = max(0, min(int(params.get("seed", 42)), 2_147_483_647))
    args: list[str]

    if backend == "proteinmpnn":
        summary = _validate_pdb_input(source)
        chains = tuple(str(value).strip() for value in params.get("chains", []) if str(value).strip())
        known_chains = set(summary["chains"])
        if chains and not set(chains).issubset(known_chains):
            blockers.append("Requested design chain is absent from the input structure")
        num_sequences = max(1, min(int(params.get("num_sequences", 16)), 1000))
        temperature = float(params.get("sampling_temperature", 0.1))
        if not 0.01 <= temperature <= 1.0:
            raise ValueError("ProteinMPNN sampling temperature must be between 0.01 and 1.0")
        batch_size = max(1, min(int(params.get("batch_size", 1)), 64))
        fixed = _parse_positions(params.get("fixed_positions"))
        designed = _parse_positions(params.get("design_positions"))
        if fixed and designed and set(fixed).intersection(designed):
            raise ValueError("A residue cannot be both fixed and explicitly designed")
        selected_chains = chains or tuple(summary["chains"].keys())
        fixed_by_chain: dict[str, list[int]] = {}
        for chain in selected_chains:
            available_positions = list(summary["chains"][chain]["positions"])
            if designed:
                fixed_by_chain[chain] = [position for position in available_positions if position not in set(designed)]
            else:
                fixed_by_chain[chain] = [position for position in fixed if position in set(available_positions)]
        constraint_path = run_dir / "config" / "proteinmpnn_constraints.json"
        fixed_jsonl = run_dir / "config" / "proteinmpnn_fixed_positions.jsonl"
        constraint_path.parent.mkdir(parents=True, exist_ok=True)
        constraint_payload = {
            "schema": "biointel.step122.proteinmpnn_constraints.v1",
            "input_structure": str(source),
            "chains_to_design": list(selected_chains),
            "fixed_positions_1based": list(fixed),
            "design_positions_1based": list(designed),
            "fixed_positions_by_chain": fixed_by_chain,
            "seed": seed,
        }
        atomic_write_json(constraint_path, constraint_payload)
        fixed_jsonl.write_text(json.dumps({source.stem: fixed_by_chain}) + "\n", encoding="utf-8")
        args = [
            "--pdb_path", str(source), "--out_folder", str(output),
            "--num_seq_per_target", str(num_sequences), "--sampling_temp", f"{temperature:g}",
            "--seed", str(seed), "--batch_size", str(batch_size),
            "--pdb_path_chains", " ".join(selected_chains),
        ]
        if any(fixed_by_chain.values()):
            args += ["--fixed_positions_jsonl", str(fixed_jsonl)]
        params.update({"threads": threads, "seed": seed, "num_sequences": num_sequences, "sampling_temperature": temperature, "batch_size": batch_size, "chains": selected_chains, "fixed_positions": fixed, "design_positions": designed, "constraint_manifest": str(constraint_path), "fixed_positions_jsonl": str(fixed_jsonl)})
        if not hardware["gpu"]["cuda_available"]:
            warnings.append("CUDA GPU not detected; ProteinMPNN may run slowly or require a CPU-compatible environment")
    elif backend == "rfdiffusion":
        summary = _validate_pdb_input(source)
        num_designs = max(1, min(int(params.get("num_designs", 8)), 256))
        contigs = str(params.get("contigs", "")).strip()
        if not contigs:
            default_chain = next(iter(summary["chains"]))
            info = summary["chains"][default_chain]
            contigs = f"{default_chain}{info['minimum']}-{info['maximum']}"
        if not re.fullmatch(r"[A-Za-z0-9_./\-+,:\[\] ]+", contigs):
            raise ValueError("RFdiffusion contig expression contains unsupported characters")
        hotspots = [str(value).strip() for value in params.get("hotspot_residues", []) if str(value).strip()]
        for hotspot in hotspots:
            if not re.fullmatch(r"[A-Za-z_]\d+", hotspot):
                raise ValueError(f"Invalid hotspot residue: {hotspot}")
        prefix = output / "design"
        args = [
            f"inference.input_pdb={source}", f"inference.output_prefix={prefix}",
            f"inference.num_designs={num_designs}", f"inference.seed={seed}",
            "inference.deterministic=True", f"contigmap.contigs=[{contigs}]",
        ]
        if hotspots:
            args.append(f"ppi.hotspot_res=[{','.join(hotspots)}]")
        params.update({"threads": threads, "seed": seed, "num_designs": num_designs, "contigs": contigs, "hotspot_residues": hotspots})
        if not hardware["gpu"]["cuda_available"]:
            blockers.append("RFdiffusion requires a compatible CUDA GPU for this protected pipeline")
    elif backend == "colabfold_batch":
        sequence = _validate_fasta_input(source)
        num_models = max(1, min(int(params.get("num_models", 3)), 5))
        recycles = max(1, min(int(params.get("num_recycles", 3)), 20))
        args = [str(source), str(output), "--num-models", str(num_models), "--num-recycle", str(recycles), "--random-seed", str(seed)]
        if bool(params.get("amber_relax", False)):
            args.append("--amber")
        if bool(params.get("use_templates", False)):
            args.append("--templates")
        params.update({"threads": threads, "seed": seed, "num_models": num_models, "num_recycles": recycles, "sequence_length": len(sequence)})
        if len(sequence) > 2500:
            warnings.append("Sequences above 2,500 residues may exceed local memory/GPU limits")
    elif backend == "foldx":
        _validate_pdb_input(source)
        mutations = [str(item).strip() for item in params.get("mutations", []) if str(item).strip()]
        if not mutations:
            blockers.append("At least one FoldX mutation is required")
        for mutation in mutations:
            if not re.fullmatch(r"[A-Za-z][A-Za-z_]?\d+[A-Za-z];?", mutation):
                raise ValueError(f"Invalid FoldX mutation syntax: {mutation}")
        mutation_file = run_dir / "config" / "individual_list.txt"
        mutation_file.parent.mkdir(parents=True, exist_ok=True)
        mutation_file.write_text("\n".join(item.rstrip(";") + ";" for item in mutations) + "\n", encoding="utf-8")
        args = ["--command=BuildModel", f"--pdb={source.name}", f"--pdb-dir={source.parent}", f"--mutant-file={mutation_file}", f"--output-dir={output}", "--numberOfRuns=1"]
        params.update({"threads": threads, "seed": seed, "mutations": mutations, "mutation_file": str(mutation_file)})
    else:
        _validate_pdb_input(source)
        protocol = params.get("protocol_xml")
        if not protocol:
            blockers.append("RosettaScripts protocol XML is required")
            protocol_path = run_dir / "config" / "missing_protocol.xml"
        else:
            protocol_path = _safe_inside(protocol, run_dir, must_exist=True)
        nstruct = max(1, min(int(params.get("nstruct", 10)), 10000))
        args = ["-s", str(source), "-parser:protocol", str(protocol_path), "-nstruct", str(nstruct), "-constant_seed", "-jran", str(seed), "-out:path:all", str(output)]
        params.update({"threads": threads, "seed": seed, "nstruct": nstruct, "protocol_xml": str(protocol_path)})

    if hardware["workspace_free_gb"] < 5:
        warnings.append("Less than 5 GB free space is available in the design workspace")
    plan = ProteinDesignPlan(
        schema="biointel.step122.protein_design_plan.v1",
        run_id=_run_id_from_directory(run_dir),
        backend=backend,
        label=_BACKEND_LABELS[backend],
        run_directory=str(run_dir),
        input_path=str(source),
        output_directory=str(output),
        arguments=tuple(args),
        parameters=params,
        input_sha256=_hash_file(source),
        executable_status=resolution,
        asset_status=asset,
        hardware=hardware,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        release_boundary="Generated designs are research hypotheses. Independent structure review and wet-lab expression, folding, stability, binding and activity validation are mandatory.",
    )
    plan_dir = run_dir / "plans"
    plan_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(plan_dir / f"{backend}.plan.json", plan.to_dict())
    return plan


def _parse_fasta_file(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    header = ""
    chunks: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(">"):
            if header and chunks:
                rows.append((header, _validate_sequence("".join(chunks))))
            header = line[1:].strip() or path.stem
            chunks = []
        else:
            chunks.append(line.strip())
    if header and chunks:
        rows.append((header, _validate_sequence("".join(chunks))))
    return rows


def _sequence_metrics(sequence: str, reference: str | None = None) -> dict[str, Any]:
    length = len(sequence)
    hydrophobic = sum(sequence.count(aa) for aa in "AILMFWVY") / max(length, 1)
    charged = sum(sequence.count(aa) for aa in "DEKR") / max(length, 1)
    liabilities = len(re.findall(r"N[^P][ST]|[FWY]{3,}|[ILV]{5,}|C.{0,2}C", sequence))
    identity: float | None = None
    substitutions: int | None = None
    if reference and len(reference) == length:
        substitutions = sum(a != b for a, b in zip(reference, sequence))
        identity = 1.0 - substitutions / max(length, 1)
    return {
        "length": length,
        "hydrophobic_fraction": hydrophobic,
        "charged_fraction": charged,
        "sequence_liability_count": liabilities,
        "identity_to_input": identity,
        "substitution_count": substitutions,
    }


def _reference_sequence_from_input(path: Path) -> str | None:
    if path.suffix.lower() in {".fa", ".fasta", ".faa"}:
        return _validate_sequence(path.read_text(encoding="utf-8"))
    return None


def _parse_colabfold_scores(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    plddt = payload.get("plddt", payload.get("mean_plddt"))
    if isinstance(plddt, list):
        numeric = [float(value) for value in plddt if isinstance(value, (int, float))]
        mean_plddt = sum(numeric) / len(numeric) if numeric else None
    else:
        mean_plddt = float(plddt) if isinstance(plddt, (int, float)) else None
    return {
        "mean_plddt": mean_plddt,
        "ptm": payload.get("ptm"),
        "iptm": payload.get("iptm"),
        "ranking_confidence": payload.get("ranking_confidence"),
    }


def _parse_foldx_table(path: Path) -> pd.DataFrame:
    try:
        frame = pd.read_csv(path, sep="\t", comment="#")
        if frame.shape[1] == 1:
            frame = pd.read_csv(path, sep=r"\s+", comment="#", engine="python")
        frame["source_file"] = str(path)
        return frame
    except Exception:
        return pd.DataFrame()


def parse_design_outputs(plan: ProteinDesignPlan) -> tuple[pd.DataFrame, pd.DataFrame]:
    output = Path(plan.output_directory)
    inventory: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    reference = _reference_sequence_from_input(Path(plan.input_path))
    if not output.exists():
        return pd.DataFrame(), pd.DataFrame()
    for path in sorted((item for item in output.rglob("*") if item.is_file()), key=lambda item: item.as_posix().lower()):
        suffix = path.suffix.lower()
        record: dict[str, Any] = {
            "path": str(path),
            "relative_path": path.relative_to(output).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _hash_file(path),
            "kind": "other",
        }
        if suffix in {".fa", ".fasta", ".faa"}:
            record["kind"] = "sequence"
            for header, sequence in _parse_fasta_file(path):
                candidate = {
                    "candidate_id": header,
                    "backend": plan.backend,
                    "sequence": sequence,
                    "source_file": str(path),
                    **_sequence_metrics(sequence, reference),
                }
                candidates.append(candidate)
        elif suffix in {".pdb", ".ent", ".cif", ".mmcif"}:
            record["kind"] = "structure"
            candidates.append({
                "candidate_id": path.stem,
                "backend": plan.backend,
                "structure_path": str(path),
                "source_file": str(path),
            })
        elif suffix == ".json":
            scores = _parse_colabfold_scores(path)
            record["kind"] = "confidence" if scores else "json"
            if scores:
                candidates.append({"candidate_id": path.stem, "backend": plan.backend, "source_file": str(path), **scores})
        elif suffix in {".fxout", ".sc"}:
            record["kind"] = "energy_table"
            table = _parse_foldx_table(path)
            for _, row in table.iterrows():
                candidates.append({"candidate_id": str(row.get("Pdb", row.get("description", path.stem))), "backend": plan.backend, "source_file": str(path), **{str(key): value for key, value in row.to_dict().items() if key != "source_file"}})
        elif suffix in {".log", ".txt"}:
            record["kind"] = "log"
        inventory.append(record)
    candidate_frame = pd.DataFrame(candidates)
    if not candidate_frame.empty:
        candidate_frame = candidate_frame.drop_duplicates(subset=[column for column in ("candidate_id", "sequence", "structure_path", "source_file") if column in candidate_frame], keep="first")
        if "mean_plddt" in candidate_frame:
            candidate_frame["confidence_status"] = pd.cut(pd.to_numeric(candidate_frame["mean_plddt"], errors="coerce"), bins=[-math.inf, 50, 70, 90, math.inf], labels=["Very low", "Low", "Confident", "Very high"])
    return pd.DataFrame(inventory), candidate_frame.reset_index(drop=True)


def _release_gate(plan: ProteinDesignPlan, candidates: pd.DataFrame) -> dict[str, Any]:
    return {
        "research_candidates_available": not candidates.empty,
        "scientific_release_ready": False,
        "clinical_release_ready": False,
        "required_next_steps": [
            "Independent structural review and clash/interface assessment",
            "Expression and solubility confirmation",
            "Biophysical folding and stability assay",
            "Target binding and functional activity assay",
            "Sequence novelty, safety and intellectual-property review",
        ],
        "boundary": plan.release_boundary,
    }


def execute_protein_design_plan(
    plan: ProteinDesignPlan,
    *,
    timeout_seconds: int = 172800,
    force: bool = False,
    dry_run: bool = False,
) -> ProteinDesignRunResult:
    run_dir = Path(plan.run_directory)
    state_path = run_dir / "run_state.json"
    manifest_path = run_dir / "run_manifest.json"
    previous: dict[str, Any] = {}
    if state_path.is_file():
        try:
            previous = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
    if previous.get("status") == "completed" and not force:
        inventory, candidates = parse_design_outputs(plan)
        return ProteinDesignRunResult(
            schema="biointel.step122.protein_design_run.v1",
            run_id=plan.run_id,
            backend=plan.backend,
            status="completed",
            resumed=True,
            run_directory=str(run_dir),
            manifest_path=str(manifest_path),
            execution_manifest_path=str(previous.get("execution_manifest_path", "")),
            outputs=inventory,
            candidates=candidates,
            release_gate=_release_gate(plan, candidates),
        )
    if plan.blockers and not dry_run:
        raise RuntimeError("Execution is blocked: " + "; ".join(plan.blockers))
    started = _utc_now()
    state = {
        "schema": "biointel.step122.protein_design_state.v1",
        "run_id": plan.run_id,
        "backend": plan.backend,
        "status": "planned" if dry_run else "running",
        "started_at": started,
        "updated_at": started,
        "attempt": int(previous.get("attempt", 0)) + 1,
        "plan_sha256": sha256(json.dumps(plan.to_dict(), sort_keys=True, default=str).encode("utf-8")).hexdigest(),
    }
    atomic_write_json(state_path, state)
    execution_manifest = ""
    if dry_run:
        status = "planned"
    else:
        try:
            result = run_tool_audited(
                plan.backend,
                plan.arguments,
                run_directory=run_dir / "execution",
                cwd=run_dir,
                timeout_seconds=max(1, int(timeout_seconds)),
            )
            execution_manifest = result.manifest_path
            status = "completed"
        except Exception as exc:
            state.update({"status": "failed", "updated_at": _utc_now(), "error": f"{type(exc).__name__}: {exc}"})
            atomic_write_json(state_path, state)
            atomic_write_json(manifest_path, {"schema": "biointel.step122.protein_design_run_manifest.v1", "plan": plan.to_dict(), "state": state})
            raise
    inventory, candidates = parse_design_outputs(plan)
    gate = _release_gate(plan, candidates)
    state.update({
        "status": status,
        "updated_at": _utc_now(),
        "execution_manifest_path": execution_manifest,
        "output_file_count": int(len(inventory)),
        "candidate_count": int(len(candidates)),
    })
    atomic_write_json(state_path, state)
    manifest = {
        "schema": "biointel.step122.protein_design_run_manifest.v1",
        "release": "15.6.0",
        "created_at": _utc_now(),
        "plan": plan.to_dict(),
        "state": state,
        "outputs": inventory.to_dict("records"),
        "candidates": candidates.drop(columns=["sequence"], errors="ignore").to_dict("records"),
        "release_gate": gate,
    }
    manifest["manifest_sha256"] = sha256(json.dumps(manifest, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    atomic_write_json(manifest_path, manifest)
    return ProteinDesignRunResult(
        schema="biointel.step122.protein_design_run.v1",
        run_id=plan.run_id,
        backend=plan.backend,
        status=status,
        resumed=False,
        run_directory=str(run_dir),
        manifest_path=str(manifest_path),
        execution_manifest_path=execution_manifest,
        outputs=inventory,
        candidates=candidates,
        release_gate=gate,
    )


def discover_protein_design_runs(workspace: str | Path) -> pd.DataFrame:
    root = Path(workspace).expanduser().resolve()
    rows: list[dict[str, Any]] = []
    if not root.exists():
        return pd.DataFrame()
    for state_path in root.glob("*/run_state.json"):
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows.append({
            "run_id": state.get("run_id", state_path.parent.name),
            "backend": state.get("backend", ""),
            "status": state.get("status", "unknown"),
            "attempt": state.get("attempt", 0),
            "updated_at": state.get("updated_at", ""),
            "candidate_count": state.get("candidate_count", 0),
            "run_directory": str(state_path.parent),
        })
    return pd.DataFrame(rows).sort_values("updated_at", ascending=False) if rows else pd.DataFrame()


__all__ = [
    "BACKENDS",
    "ProteinDesignPlan",
    "ProteinDesignRunResult",
    "build_protein_design_plan",
    "discover_protein_design_runs",
    "execute_protein_design_plan",
    "parse_design_outputs",
    "protein_design_preflight",
    "register_model_asset",
    "stage_protein_design_input",
]
