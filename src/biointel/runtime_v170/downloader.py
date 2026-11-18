from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import hashlib
import subprocess
import urllib.error
import urllib.request
from typing import Any

from .catalog import reference_catalog
from .qualification import Step170Registry


class _DownloadSizeExceeded(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_direct(root: str | Path, reference_id: str, *, execute: bool = False, max_size_gb: float | None = None) -> dict[str, Any]:
    project = Path(root).resolve()
    catalog = reference_catalog().set_index("reference_id")
    if reference_id not in catalog.index:
        raise KeyError(reference_id)
    item = catalog.loc[reference_id].to_dict()
    if item["download_strategy"] != "direct":
        return {"reference_id": reference_id, "status": "manual-or-tool-managed", "source_url": item["source_url"], "install_command": item["install_command"]}
    if max_size_gb is not None and float(item["approximate_size_gb"]) > max_size_gb:
        return {"reference_id": reference_id, "status": "blocked-by-size-policy", "approximate_size_gb": item["approximate_size_gb"]}
    registry = Step170Registry(project)
    format_suffix = {
        "FASTA.GZ": ".fasta.gz",
        "VCF.GZ": ".vcf.gz",
        "TBI": ".tbi",
        "OBO": ".obo",
        "TSV": ".tsv",
    }.get(str(item.get("expected_format") or ""), "")
    suffix = format_suffix or Path(str(item["source_url"]).split("?", 1)[0]).suffix or ".dat"
    target = registry.downloads / f"{reference_id}{suffix}"
    if not execute:
        return {"reference_id": reference_id, "status": "dry-run", "source_url": item["source_url"], "target": str(target)}
    if target.is_file() and target.stat().st_size > 0:
        # Keep a verified local copy stable across installer retries.  This is
        # particularly important when the installer resumes after a network
        # interruption or a long WSL provisioning session.
        return {
            "reference_id": reference_id,
            "status": "already-downloaded-unqualified",
            "target": str(target),
            "sha256": _sha256(target),
            "size_bytes": target.stat().st_size,
            "resumed": False,
        }
    partial = target.with_suffix(target.suffix + ".partial")
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": "BioIntel-AI-Step170/14.2.0"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    max_bytes = int(float(max_size_gb) * 1024**3) if max_size_gb is not None else None
    try:
        request = urllib.request.Request(str(item["source_url"]), headers=headers)
        with urllib.request.urlopen(request, timeout=120) as response:
            resumed = offset > 0 and getattr(response, "status", 200) == 206
            mode = "ab" if resumed else "wb"
            if offset and not resumed:
                offset = 0
            declared = response.headers.get("Content-Length", "").strip()
            if declared.isdigit() and max_bytes is not None and offset + int(declared) > max_bytes:
                return {
                    "reference_id": reference_id,
                    "status": "blocked-by-size-policy",
                    "approximate_size_gb": item["approximate_size_gb"],
                    "declared_size_bytes": int(declared),
                    "max_size_gb": max_size_gb,
                }
            written = offset
            with partial.open(mode) as handle:
                while True:
                    chunk = response.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if max_bytes is not None and written > max_bytes:
                        raise _DownloadSizeExceeded(
                            f"download exceeded configured {max_size_gb:g} GB policy"
                        )
                    handle.write(chunk)
        partial.replace(target)
    except _DownloadSizeExceeded as exc:
        return {
            "reference_id": reference_id,
            "status": "blocked-by-size-policy",
            "approximate_size_gb": item["approximate_size_gb"],
            "max_size_gb": max_size_gb,
            "partial_path": str(partial) if partial.exists() else "",
            "partial_size_bytes": partial.stat().st_size if partial.exists() else 0,
            "message": str(exc),
        }
    except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        # Reference acquisition is optional to the core local application.  A
        # provider outage must leave resumable partial bytes intact and must
        # never turn into an unhandled installer/app exception.
        return {
            "reference_id": reference_id,
            "status": "optional-service-unavailable",
            "source_url": item["source_url"],
            "target": str(target),
            "partial_path": str(partial) if partial.exists() else "",
            "partial_size_bytes": partial.stat().st_size if partial.exists() else 0,
            "message": f"{type(exc).__name__}: {str(exc)[:400]}",
        }
    provider_checksum = ""
    provider_checksum_verified = False
    if str(item.get("checksum_url") or "").strip():
        checksum_request = urllib.request.Request(str(item["checksum_url"]), headers={"User-Agent": "BioIntel-AI-Step170/14.2.0"})
        with urllib.request.urlopen(checksum_request, timeout=60) as response:
            checksum_text = response.read(10000).decode("utf-8", errors="replace")
        import re
        match = re.search(r"\b([0-9a-fA-F]{64}|[0-9a-fA-F]{32})\b", checksum_text)
        if match:
            value = match.group(1).lower()
            algorithm = "sha256" if len(value) == 64 else "md5"
            digest = hashlib.new(algorithm)
            with target.open("rb") as handle:
                for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                    digest.update(chunk)
            provider_checksum = f"{algorithm}:{value}"
            provider_checksum_verified = digest.hexdigest() == value
    return {
        "reference_id": reference_id,
        "status": "downloaded-unqualified",
        "target": str(target),
        "sha256": _sha256(target),
        "size_bytes": target.stat().st_size,
        "resumed": bool(offset),
        "provider_checksum": provider_checksum,
        "provider_checksum_verified": provider_checksum_verified,
    }


def provisioning_commands(root: str | Path, *, environment: str = "biointel-step170") -> dict[str, Any]:
    from .catalog import engine_catalog
    frame = engine_catalog()
    conda_packages: list[str] = []
    pip_packages: list[str] = []
    manual: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        conda_packages.extend(v.strip() for v in str(row["conda_packages"]).split(",") if v.strip())
        row_conda = [v.strip() for v in str(row["conda_packages"]).split(",") if v.strip()]
        if not row_conda:
            pip_packages.extend(v.strip() for v in str(row["pip_packages"]).split(",") if v.strip())
        if bool(row["manual_distribution"]):
            manual.append({"engine": row["engine"], "upstream_url": row["upstream_url"], "licence_id": row["licence_id"], "route": row["install_route"]})
    conda_packages = sorted(set(conda_packages))
    pip_packages = sorted(set(pip_packages))
    commands = [
        ["micromamba", "create", "-y", "-n", environment, "-c", "conda-forge", "-c", "bioconda", "--strict-channel-priority", "python=3.11", *conda_packages],
    ]
    if pip_packages:
        commands.append(["micromamba", "run", "-n", environment, "python", "-m", "pip", "install", "--upgrade", *pip_packages])
    return {"schema": "biointel.step170.provisioning-plan.v1", "environment": environment, "conda_packages": conda_packages, "pip_packages": pip_packages, "automatic_commands": commands, "manual_installations": manual}


__all__ = ["download_direct", "provisioning_commands"]
