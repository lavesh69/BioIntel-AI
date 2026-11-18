from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    add("Version", version == "13.2.0", f"VERSION={version}")

    from biointel.biotech.flow_cytometry import apply_compensation, flow_qc, singlet_gate
    from biointel.expansion.catalog import EXPANSION_MODULES
    from biointel.expansion.renderer import _analyse_detailed, _demo_frame, _normalise
    from biointel.native.engines import ENGINE_REGISTRY, plan_catalog
    from biointel.scientific_depth.capability import CAPABILITY_SPECS

    expected_modules = {
        "flow_cytometry", "epigenomics_chromatin", "metabolomics_lipidomics",
        "bioimage_microscopy", "spatial_omics_pathology", "glycomics_glycoproteomics",
        "proteogenomics_neoantigen", "population_gwas", "structural_variant_repeat",
        "rna_isoform_splicing", "pharmacogenomics", "docking_dynamics",
        "antibody_biologics", "immunoinformatics_vaccine", "single_cell_trajectory",
        "cell_atlas_mapping", "genome_editing_safety",
    }
    missing_modules = sorted(expected_modules - set(CAPABILITY_SPECS))
    stage_count = sum(len(CAPABILITY_SPECS[key].stages) for key in expected_modules if key in CAPABILITY_SPECS)
    add("Weak-module capability coverage", not missing_modules and stage_count == 102, f"17 modules, {stage_count} stages; missing={missing_modules}")

    capability_engines = {engine for spec in CAPABILITY_SPECS.values() for stage in spec.stages for engine in stage.engines}
    missing_engines = sorted(capability_engines - set(ENGINE_REGISTRY))
    add("Capability engine registry", not missing_engines, f"{len(capability_engines)} engine keys; missing={missing_engines}")

    new_plans = {
        "macs2_callpeak", "deeptools_bamcoverage", "plink2_glm", "whatshap_phase",
        "igblast_germline", "comet_search", "openms_featurefinder_metabo", "bedtools_intersect",
    }
    catalog = set(plan_catalog()["Plan"].astype(str))
    add("Protected engine plans", new_plans.issubset(catalog), f"{len(new_plans & catalog)}/{len(new_plans)} Step 120 plans present")

    true = np.array([[100.0, 20.0], [50.0, 80.0], [10.0, 120.0]])
    spill = np.array([[1.0, 0.10], [0.05, 1.0]])
    observed = true @ spill.T
    channels = ["FITC-A", "PE-A"]
    compensated, _ = apply_compensation(
        pd.DataFrame(observed, columns=channels),
        channels,
        pd.DataFrame(spill, index=channels, columns=channels),
    )
    add("Flow compensation", np.allclose(compensated[channels].to_numpy(), true, atol=1e-8), "Known spillover inversion recovered source signal")

    rng = np.random.default_rng(120)
    area = rng.normal(1000, 70, 1500)
    events = pd.DataFrame({
        "event_id": [f"E{i}" for i in range(1500)],
        "Time": np.arange(1500),
        "FSC-A": area,
        "FSC-H": area * rng.normal(1.0, 0.04, 1500),
        "FITC-A": rng.lognormal(4.0, 0.4, 1500),
    })
    qc = flow_qc(events, event_id_column="event_id", time_column="Time", channels=["FSC-A", "FSC-H", "FITC-A"])
    singlets = singlet_gate(events, "FSC-A", "FSC-H")
    add("Flow QC and gating", qc.summary["events"] == 1500 and 0 < len(singlets.events) <= 1500, f"events={qc.summary['events']}; singlets={len(singlets.events)}")

    failed_demos: list[str] = []
    for module in EXPANSION_MODULES:
        try:
            data = _normalise(_demo_frame(module, 64), module)
            result, summary, _, _ = _analyse_detailed(data, module, 0.70)
            if result.empty or summary.get("result_records") != len(result):
                failed_demos.append(module.key)
        except Exception as exc:  # verification must report rather than hide failures
            failed_demos.append(f"{module.key}:{type(exc).__name__}")
    add("Expansion module runtime", not failed_demos, f"{len(EXPANSION_MODULES)-len(failed_demos)}/{len(EXPANSION_MODULES)} demos passed; failures={failed_demos}")

    locked = {
        "pages/6_DTI_Predictor.py": "84b3ecec1356b7239a057459210af4cd130c57c08dd9449b7239d1fe5954e0cc",
        "pages/74_DTI_Validation_Evidence_Center.py": "a700a8a21649b49cf0e3a1521d2afad45039b83b767c2fe730b93fee7d4f7f11",
        "pages/109_Lab_Instrument_Import_Center.py": "22b5aba5bfea37bb1ef330ed7cca3773467463f883189602d96a0151311c8f70",
        "pages/126_LIMS_ELN_and_Sample_Chain_of_Custody_Hub.py": "eadaef1a283a5fa11ce6b243aa561508ba9ceba9f6fdcc207f4853ccf7d86905",
        "pages/157_Instrument_Integration_Hub_2.py": "cf3a5f94756def0007dbff31184ec276d90b03fc6d6e1ca792c87189e5ab7d6d",
    }
    changed = [relative for relative, digest in locked.items() if not (ROOT / relative).is_file() or sha256(ROOT / relative) != digest]
    add("Requested exclusions preserved", not changed, f"{len(locked)-len(changed)}/{len(locked)} byte-identical; changed={changed}")

    passed = sum(bool(item["passed"]) for item in checks)
    report = {
        "schema": "biointel.step120.verification.v1",
        "version": version,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "total": len(checks),
        "checks": checks,
    }
    out = ROOT / "reports" / "step120_weak_module_verification.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for item in checks:
        print(("PASS" if item["passed"] else "FAIL") + f" | {item['check']} | {item['detail']}")
    print(f"RESULT | {passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
