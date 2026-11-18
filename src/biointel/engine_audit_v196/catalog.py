from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from biointel.native.engines import ENGINE_REGISTRY, detect_engine
from biointel.operational_v164.catalog import provisioning_spec


@dataclass(frozen=True)
class EngineAuditRecord:
    engine: str
    label: str
    category: str
    capabilities: tuple[str, ...]
    executable_candidates: tuple[str, ...]
    version_probe: tuple[str, ...]
    required_databases: tuple[str, ...]
    gpu_optional: bool
    linked_modules: tuple[str, ...]
    module_count: int
    conda_packages: tuple[str, ...]
    pip_packages: tuple[str, ...]
    manual_distribution: bool
    model_weights_required: bool
    licence_acceptance_required: bool
    official_url: str
    licence_spdx: str
    licence_verification: str
    redistribution_policy: str
    install_route: str
    windows_mode: str
    windows_support_level: str
    offline_install_feasibility: str
    tool_size_band: str
    reference_size_band: str
    recommended_pack: str
    priority_tier: str
    automatic_bundle_policy: str
    legacy_catalog_covered: bool
    audit_status: str
    blockers: tuple[str, ...]


# Step170 covered 53 engines. These overrides complete the 23 engines that
# entered the live ENGINE_REGISTRY later. Licence fields are deliberately
# conservative: an installer may only bundle an executable after the exact
# release artefact, upstream licence text and redistribution obligations have
# been captured and hashed.
_NEW_ENGINE_POLICY: dict[str, dict[str, Any]] = {
    "abricate": {
        "official_url": "https://github.com/tseemann/abricate",
        "licence_spdx": "GPL-2.0-or-later",
        "install_route": "micromamba-wsl2",
        "windows_mode": "WSL2",
        "redistribution_policy": "conditional-source-and-licence-notice",
    },
    "bedtools": {
        "official_url": "https://github.com/arq5x/bedtools2",
        "licence_spdx": "MIT",
        "install_route": "micromamba-wsl2",
        "windows_mode": "WSL2",
        "redistribution_policy": "permissive-with-notice",
    },
    "bgzip": {
        "official_url": "https://www.htslib.org/",
        "licence_spdx": "MIT",
        "install_route": "htslib-pack-wsl2",
        "windows_mode": "WSL2-preferred",
        "redistribution_policy": "permissive-with-notice",
    },
    "blastp": {
        "official_url": "https://blast.ncbi.nlm.nih.gov/doc/blast-help/downloadblastdata.html",
        "licence_spdx": "LicenseRef-Public-Domain-US-Gov",
        "install_route": "official-windows-binary",
        "windows_mode": "Native Windows",
        "redistribution_policy": "public-domain-binary-provenance-required",
    },
    "bowtie2": {
        "official_url": "https://github.com/BenLangmead/bowtie2",
        "licence_spdx": "GPL-3.0-or-later",
        "install_route": "official-windows-binary-or-wsl2",
        "windows_mode": "Native Windows",
        "redistribution_policy": "copyleft-review-required",
    },
    "cutadapt": {
        "official_url": "https://cutadapt.readthedocs.io/",
        "licence_spdx": "MIT",
        "install_route": "official-windows-exe-or-pinned-python",
        "windows_mode": "Native Windows",
        "redistribution_policy": "permissive-with-notice",
    },
    "fastp": {
        "official_url": "https://github.com/OpenGene/fastp",
        "licence_spdx": "MIT",
        "install_route": "micromamba-wsl2-or-source-build",
        "windows_mode": "WSL2",
        "redistribution_policy": "permissive-with-notice",
    },
    "fastqc": {
        "official_url": "https://www.bioinformatics.babraham.ac.uk/projects/fastqc/",
        "licence_spdx": "GPL-3.0-or-later",
        "install_route": "official-windows-zip-java",
        "windows_mode": "Native Windows",
        "redistribution_policy": "copyleft-review-required",
    },
    "hmmer": {
        "official_url": "https://hmmer.org/",
        "licence_spdx": "BSD-3-Clause",
        "install_route": "micromamba-wsl2",
        "windows_mode": "WSL2",
        "redistribution_policy": "permissive-with-notice",
    },
    "interproscan": {
        "official_url": "https://www.ebi.ac.uk/interpro/download/InterProScan/",
        "licence_spdx": "Apache-2.0",
        "install_route": "official-linux-distribution-wsl2",
        "windows_mode": "WSL2",
        "redistribution_policy": "mixed-components-separate-licence-review",
    },
    "kallisto": {
        "official_url": "https://pachterlab.github.io/kallisto/download",
        "licence_spdx": "BSD-2-Clause",
        "install_route": "official-windows-binary-or-wsl2",
        "windows_mode": "Native Windows",
        "redistribution_policy": "permissive-with-notice",
    },
    "majiq": {
        "official_url": "https://majiq.biociphers.org/",
        "licence_spdx": "LicenseRef-Upstream-Review-Required",
        "install_route": "pinned-python-wsl2",
        "windows_mode": "WSL2",
        "redistribution_policy": "do-not-bundle-until-licence-reviewed",
    },
    "mosdepth": {
        "official_url": "https://github.com/brentp/mosdepth",
        "licence_spdx": "MIT",
        "install_route": "micromamba-wsl2",
        "windows_mode": "WSL2",
        "redistribution_policy": "permissive-with-notice",
    },
    "msconvert": {
        "official_url": "https://proteowizard.sourceforge.io/",
        "licence_spdx": "Apache-2.0",
        "install_route": "official-windows-installer",
        "windows_mode": "Native Windows",
        "redistribution_policy": "component-and-vendor-library-review-required",
    },
    "multiqc": {
        "official_url": "https://docs.seqera.io/multiqc/getting_started/installation",
        "licence_spdx": "GPL-3.0-or-later",
        "install_route": "pinned-python-windows",
        "windows_mode": "Native Windows",
        "redistribution_policy": "copyleft-review-required",
    },
    "obabel": {
        "official_url": "https://openbabel.org/",
        "licence_spdx": "GPL-2.0-only",
        "install_route": "official-windows-binary-or-wsl2",
        "windows_mode": "Native Windows",
        "redistribution_policy": "copyleft-review-required",
    },
    "openms_featurefinder": {
        "official_url": "https://www.openms.de/",
        "licence_spdx": "BSD-3-Clause",
        "install_route": "openms-windows-pack",
        "windows_mode": "Native Windows",
        "redistribution_policy": "permissive-with-notice",
    },
    "picard": {
        "official_url": "https://github.com/broadinstitute/picard",
        "licence_spdx": "MIT",
        "install_route": "official-jar-java17",
        "windows_mode": "Native Windows",
        "redistribution_policy": "permissive-with-notice",
    },
    "rmats": {
        "official_url": "https://github.com/Xinglab/rmats-turbo",
        "licence_spdx": "LicenseRef-Upstream-Review-Required",
        "install_route": "micromamba-wsl2",
        "windows_mode": "WSL2",
        "redistribution_policy": "do-not-bundle-until-licence-reviewed",
    },
    "salmon": {
        "official_url": "https://github.com/COMBINE-lab/salmon",
        "licence_spdx": "BSD-3-Clause",
        "install_route": "micromamba-wsl2",
        "windows_mode": "WSL2",
        "redistribution_policy": "permissive-with-notice",
    },
    "snpeff": {
        "official_url": "https://pcingola.github.io/SnpEff/",
        "licence_spdx": "LGPL-3.0-or-later",
        "install_route": "official-jar-java",
        "windows_mode": "Native Windows",
        "redistribution_policy": "weak-copyleft-review-required",
    },
    "suppa2": {
        "official_url": "https://github.com/comprna/SUPPA",
        "licence_spdx": "MIT",
        "install_route": "pinned-python-windows-or-wsl2",
        "windows_mode": "Native Windows",
        "redistribution_policy": "permissive-with-notice",
    },
    "tabix": {
        "official_url": "https://www.htslib.org/doc/tabix.html",
        "licence_spdx": "MIT",
        "install_route": "htslib-pack-wsl2",
        "windows_mode": "WSL2-preferred",
        "redistribution_policy": "permissive-with-notice",
    },
}


_PRIORITY_ONE = {
    "samtools", "bcftools", "fastqc", "multiqc", "fastp", "vep", "snpeff", "plink2",
    "star", "salmon", "kallisto", "mafft", "iqtree", "kraken2", "obabel", "vina",
    "cellpose", "bowtie2", "blastp", "cutadapt",
}
_PRIORITY_TWO = {
    "tabix", "bgzip", "bedtools", "mosdepth", "picard", "blastn", "bwa", "minimap2",
    "hmmer", "interproscan", "openms", "openms_featurefinder", "msconvert", "openmm",
    "gromacs", "scanpy", "scvelo", "cellrank", "whatshap", "expansionhunter", "dorado",
}
_RESTRICTED = {"netmhcpan", "netmhciipan"}
_MODEL_HEAVY = {"dorado", "proteinmpnn", "rfdiffusion", "colabfold", "llama_cpp"}
_REFERENCE_VERY_LARGE = {"vep", "interproscan", "kraken2", "humann", "colabfold"}


def _legacy_catalog() -> pd.DataFrame:
    try:
        from biointel.runtime_v170.catalog import engine_catalog
        return engine_catalog()
    except Exception:
        return pd.DataFrame()


def _legacy_by_engine() -> dict[str, dict[str, Any]]:
    frame = _legacy_catalog()
    if frame.empty:
        return {}
    return {str(row["engine"]): row for row in frame.to_dict(orient="records")}


def _pack_for(category: str, engine: str) -> str:
    text = category.lower()
    if engine in _MODEL_HEAVY or "protein design" in text or "local ai" in text:
        return "AI/GPU Model Pack"
    if any(token in text for token in ("bioimag", "pathology", "mass spectrometry", "proteomics")):
        return "Lab Imaging & Proteomics Pack"
    if any(token in text for token in ("structural biology", "cheminformatics", "antibody", "immunoinformatics", "protein structure")):
        return "Discovery Engine Pack"
    if any(token in text for token in ("single-cell", "transcript", "genomics", "variation", "assembly", "pangenomics", "phylogen", "metagen", "amr", "microbiology", "sequencing", "epigen")):
        return "Bioinformatics Engine Pack"
    return "Specialist Extension Pack"


def _size_bands(engine: str, required_databases: tuple[str, ...], weights: bool) -> tuple[str, str]:
    if weights or engine in _MODEL_HEAVY:
        return "large-or-model-dependent", "very-large-model-or-database-pack"
    if engine in {"interproscan", "openms", "msconvert", "gromacs", "colabfold"}:
        tool = "large"
    elif engine in {"fastqc", "picard", "snpeff", "vep", "cellpose", "scanpy", "stardist"}:
        tool = "medium"
    else:
        tool = "small-to-medium"
    if engine in _REFERENCE_VERY_LARGE:
        refs = "very-large"
    elif required_databases:
        refs = "small-to-large-dataset-dependent"
    else:
        refs = "none"
    return tool, refs


def _default_platform(legacy: dict[str, Any], pip_packages: tuple[str, ...], manual: bool) -> tuple[str, str, str]:
    install_route = str(legacy.get("install_route") or "")
    platform = str(legacy.get("platform_target") or "")
    if install_route:
        if platform.startswith("WSL2"):
            return install_route, "WSL2", "supported-through-WSL2"
        if install_route == "pinned-python-venv":
            return install_route, "Native Windows or WSL2", "python-runtime-dependent"
        return install_route, "Provider-specific", "provider-specific"
    if pip_packages:
        return "pinned-python-windows-or-wsl2", "Native Windows or WSL2", "python-runtime-dependent"
    if manual:
        return "manual-provider-install", "Provider-specific", "provider-specific"
    return "micromamba-wsl2", "WSL2", "supported-through-WSL2"


def _licence_fields(engine: str, legacy: dict[str, Any]) -> tuple[str, str, str, str]:
    override = _NEW_ENGINE_POLICY.get(engine)
    if override:
        spdx = str(override["licence_spdx"])
        verification = "official-source-recorded" if not spdx.startswith("LicenseRef-Upstream") else "upstream-review-required"
        return spdx, verification, str(override["redistribution_policy"]), str(override["official_url"])

    licence_id = str(legacy.get("licence_id") or "LicenseRef-Upstream-Review-Required")
    official_url = str(legacy.get("upstream_url") or "")
    known = {
        "proteinmpnn-mit": ("MIT", "official-policy-recorded", "permissive-with-notice"),
        "rfdiffusion-bsd": ("BSD-3-Clause", "official-policy-recorded", "conditional-code-and-weight-review"),
        "dtu-academic": ("LicenseRef-DTU-Academic", "provider-terms-recorded", "restricted-do-not-bundle"),
        "ont-public-license": ("LicenseRef-ONT-Public-License", "provider-terms-recorded", "provider-policy-review"),
    }
    if licence_id in known:
        spdx, verification, redistribution = known[licence_id]
    else:
        spdx = "LicenseRef-Upstream-Package-License"
        verification = "exact-release-licence-capture-required"
        redistribution = "review-before-bundling"
    return spdx, verification, redistribution, official_url


def audit_record(engine: str) -> EngineAuditRecord:
    key = str(engine).lower()
    spec = ENGINE_REGISTRY[key]
    provision = provisioning_spec(key)
    legacy = _legacy_by_engine().get(key, {})
    policy = _NEW_ENGINE_POLICY.get(key, {})

    install_route, windows_mode, support = _default_platform(
        legacy, tuple(provision.pip_packages), bool(provision.manual_distribution)
    )
    if policy:
        install_route = str(policy["install_route"])
        windows_mode = str(policy["windows_mode"])
        support = "native-supported" if windows_mode == "Native Windows" else "supported-through-wsl2"

    spdx, licence_verification, redistribution, official_url = _licence_fields(key, legacy)
    tool_size, reference_size = _size_bands(key, tuple(spec.required_databases), bool(provision.model_weights_required))

    if key in _PRIORITY_ONE:
        priority = "P1-compulsory"
    elif key in _PRIORITY_TWO:
        priority = "P2-high-value"
    elif key in _RESTRICTED or key in _MODEL_HEAVY:
        priority = "P4-manual-or-heavy"
    else:
        priority = "P3-specialist"

    blockers: list[str] = []
    if licence_verification in {"exact-release-licence-capture-required", "upstream-review-required"}:
        blockers.append("Capture and hash the exact upstream licence for the selected release.")
    if key in _RESTRICTED:
        blockers.append("User-specific provider authorisation is required; automatic redistribution is blocked.")
    if provision.model_weights_required or key in _MODEL_HEAVY:
        blockers.append("Model-weight licence, checksum and hardware qualification are required.")
    if spec.required_databases:
        blockers.append("Reference/database release, checksum, licence and disk estimate are required.")
    if windows_mode.startswith("WSL2"):
        blockers.append("WSL2 availability and Linux runtime qualification are required on Windows.")

    if key in _RESTRICTED:
        bundle_policy = "never-auto-bundle"
    elif key in _MODEL_HEAVY:
        bundle_policy = "separate-optional-model-pack"
    elif redistribution.startswith("permissive") or redistribution.startswith("public-domain"):
        bundle_policy = "eligible-after-release-hash-and-smoke-test"
    else:
        bundle_policy = "do-not-bundle-until-legal-review"

    if key in _RESTRICTED:
        offline = "manual-authorized-download-only"
    elif provision.model_weights_required or key in _MODEL_HEAVY:
        offline = "conditional-with-preverified-model-pack"
    elif spec.required_databases:
        offline = "yes-with-preverified-engine-and-reference-packs"
    else:
        offline = "yes-with-preverified-engine-pack"

    status = "audited-policy-known"
    if blockers:
        status = "audited-with-blockers"

    return EngineAuditRecord(
        engine=key,
        label=spec.label,
        category=spec.category,
        capabilities=tuple(spec.capabilities),
        executable_candidates=tuple(spec.executables),
        version_probe=tuple(spec.version_args),
        required_databases=tuple(spec.required_databases),
        gpu_optional=bool(spec.gpu_optional),
        linked_modules=tuple(provision.modules),
        module_count=len(provision.modules),
        conda_packages=tuple(provision.conda_packages),
        pip_packages=tuple(provision.pip_packages),
        manual_distribution=bool(provision.manual_distribution),
        model_weights_required=bool(provision.model_weights_required),
        licence_acceptance_required=bool(provision.licence_acceptance_required or key in _RESTRICTED),
        official_url=official_url,
        licence_spdx=spdx,
        licence_verification=licence_verification,
        redistribution_policy=redistribution,
        install_route=install_route,
        windows_mode=windows_mode,
        windows_support_level=support,
        offline_install_feasibility=offline,
        tool_size_band=tool_size,
        reference_size_band=reference_size,
        recommended_pack=_pack_for(spec.category, key),
        priority_tier=priority,
        automatic_bundle_policy=bundle_policy,
        legacy_catalog_covered=bool(legacy),
        audit_status=status,
        blockers=tuple(dict.fromkeys(blockers)),
    )


def audit_catalog(engines: Iterable[str] | None = None, *, probe_runtime: bool = False) -> pd.DataFrame:
    selected = sorted(set(str(item).lower() for item in (engines or ENGINE_REGISTRY)))
    rows: list[dict[str, Any]] = []
    for key in selected:
        item = asdict(audit_record(key))
        for field in (
            "capabilities", "executable_candidates", "version_probe", "required_databases",
            "linked_modules", "conda_packages", "pip_packages", "blockers",
        ):
            item[field] = " | ".join(str(value) for value in item[field])
        if probe_runtime:
            status = detect_engine(key, timeout_seconds=3.0)
            item.update({
                "runtime_available": bool(status.available),
                "runtime_executable": status.executable,
                "runtime_version": status.version,
            })
        rows.append(item)
    frame = pd.DataFrame(rows).sort_values(["priority_tier", "category", "engine"]).reset_index(drop=True)
    if len(frame) != len(ENGINE_REGISTRY) or frame["engine"].nunique() != len(ENGINE_REGISTRY):
        raise RuntimeError(
            f"Engine audit must cover {len(ENGINE_REGISTRY)} unique engines; "
            f"found {len(frame)} rows/{frame['engine'].nunique()} unique."
        )
    return frame


def audit_summary(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "schema": "biointel.step212.engine-audit-summary.v1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "registered_engines": int(len(ENGINE_REGISTRY)),
        "audited_engines": int(len(frame)),
        "legacy_catalog_covered": int(frame["legacy_catalog_covered"].astype(bool).sum()),
        "newly_covered_engines": int((~frame["legacy_catalog_covered"].astype(bool)).sum()),
        "priority_p1": int((frame["priority_tier"] == "P1-compulsory").sum()),
        "priority_p2": int((frame["priority_tier"] == "P2-high-value").sum()),
        "native_windows": int((frame["windows_mode"] == "Native Windows").sum()),
        "wsl2_routes": int(frame["windows_mode"].astype(str).str.contains("WSL2", case=False).sum()),
        "manual_or_restricted": int(frame["manual_distribution"].astype(bool).sum() + (frame["automatic_bundle_policy"] == "never-auto-bundle").sum()),
        "model_or_gpu_optional": int(frame["gpu_optional"].astype(bool).sum()),
        "engines_requiring_references": int(frame["required_databases"].astype(str).str.len().gt(0).sum()),
        "eligible_after_qualification": int(frame["automatic_bundle_policy"].eq("eligible-after-release-hash-and-smoke-test").sum()),
        "legal_review_required": int(frame["automatic_bundle_policy"].eq("do-not-bundle-until-legal-review").sum()),
        "never_auto_bundle": int(frame["automatic_bundle_policy"].eq("never-auto-bundle").sum()),
    }


def write_audit_reports(destination: str | Path, *, probe_runtime: bool = False) -> dict[str, Path]:
    output = Path(destination)
    output.mkdir(parents=True, exist_ok=True)
    frame = audit_catalog(probe_runtime=probe_runtime)
    summary = audit_summary(frame)

    csv_path = output / "STEP212_ENGINE_AUDIT.csv"
    json_path = output / "STEP212_ENGINE_AUDIT.json"
    summary_path = output / "STEP212_ENGINE_AUDIT_SUMMARY.json"
    md_path = output / "STEP212_ENGINE_AUDIT_SUMMARY.md"

    frame.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(frame.to_dict(orient="records"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# BioIntel AI Step212 — Engine Audit Summary",
        "",
        "This is an engineering and redistribution-readiness audit. It does not claim that an engine is installed, licensed for every use, or scientifically qualified.",
        "",
        f"- Registered engines: **{summary['registered_engines']}**",
        f"- Audited engines: **{summary['audited_engines']}**",
        f"- Previously catalogued: **{summary['legacy_catalog_covered']}**",
        f"- Newly covered in Step212: **{summary['newly_covered_engines']}**",
        f"- P1 compulsory engines: **{summary['priority_p1']}**",
        f"- P2 high-value engines: **{summary['priority_p2']}**",
        f"- Native-Windows routes: **{summary['native_windows']}**",
        f"- WSL2-related routes: **{summary['wsl2_routes']}**",
        f"- Engines requiring reference/database assets: **{summary['engines_requiring_references']}**",
        f"- GPU/model-sensitive engines: **{summary['model_or_gpu_optional']}**",
        f"- Eligible only after release hash + smoke qualification: **{summary['eligible_after_qualification']}**",
        f"- Legal review required before bundling: **{summary['legal_review_required']}**",
        f"- Never auto-bundle: **{summary['never_auto_bundle']}**",
        "",
        "## Mandatory gate before any engine enters an install pack",
        "",
        "1. Pin one exact upstream release.",
        "2. Capture the official release URL and SHA-256.",
        "3. Capture and hash the exact licence/notice files.",
        "4. Record redistribution obligations and any user acceptance requirement.",
        "5. Verify Windows-native or WSL2 execution on a clean Windows machine.",
        "6. Run version, positive fixture and negative-control smoke tests.",
        "7. Qualify required databases/model weights separately.",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {"csv": csv_path, "json": json_path, "summary_json": summary_path, "summary_md": md_path}


__all__ = [
    "EngineAuditRecord",
    "audit_catalog",
    "audit_record",
    "audit_summary",
    "write_audit_reports",
]
