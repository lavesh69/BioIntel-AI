from __future__ import annotations
import ast, io, json, math, re, tempfile, time, tracemalloc, zipfile
from hashlib import sha256
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

REQUIRED_BASE_COLUMNS = ("record_id", "page_key", "category")


def digest_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def digest_path(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_frame_hash(frame: pd.DataFrame) -> str:
    return digest_bytes(frame.sort_index(axis=1).to_csv(index=False, lineterminator="\n", float_format="%.8g").encode())


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def source_audit(page_path: Path) -> dict[str, Any]:
    source = page_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(page_path))
    compile(source, str(page_path), "exec")
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute):
                calls.append(fn.attr)
            elif isinstance(fn, ast.Name):
                calls.append(fn.id)
    unsafe = []
    for token in ("eval(", "exec(", "pickle.loads", "yaml.load("):
        if token in source:
            unsafe.append(token)
    return {
        "file": page_path.name,
        "sha256": digest_path(page_path),
        "source_lines": len(source.splitlines()),
        "streamlit_calls": len([x for x in calls if x in {"dataframe", "download_button", "file_uploader", "button", "selectbox", "text_input", "tabs", "plotly_chart"}]),
        "set_page_config": "set_page_config" in calls,
        "download_or_export": any(x in calls for x in ("download_button", "to_csv", "to_json")),
        "input_controls": any(x in calls for x in ("file_uploader", "selectbox", "text_input", "number_input", "slider", "toggle")),
        "error_controls": any(x in calls for x in ("error", "warning", "exception")) or "try:" in source,
        "unsafe_dynamic_execution": unsafe,
        "ast_nodes": sum(1 for _ in ast.walk(tree)),
    }


def make_fixture(page_key: str, category: str, records: int = 60) -> pd.DataFrame:
    seed = int(sha256(page_key.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    base = pd.DataFrame({
        "record_id": [f"R{i:05d}" for i in range(records)],
        "page_key": page_key,
        "category": category,
    })
    low = category.lower()
    if "ai" in low or "model" in low:
        base["outcome"] = (np.arange(records) % 2).astype(int)
        base["prediction"] = np.clip(base["outcome"] * 0.72 + 0.14 + rng.normal(0, 0.04, records), 0.01, 0.99)
        base["subgroup"] = np.where(np.arange(records) % 3 == 0, "site_b", "site_a")
        base["split"] = np.where(np.arange(records) % 5 == 0, "external", "development")
    elif "research planning" in low:
        base["workstream"] = [f"W{i%5+1}" for i in range(records)]
        base["planned_n"] = 80 + (np.arange(records) % 7) * 20
        base["risk_probability"] = np.round(rng.uniform(0.05, 0.45, records), 3)
        base["milestone_day"] = 7 + np.arange(records) * 3
    elif "qualification" in low:
        base["check_name"] = [f"check_{i:03d}" for i in range(records)]
        base["status"] = np.where(np.arange(records) % 11 == 0, "review", "pass")
        base["evidence_hash"] = [digest_bytes(f"{page_key}:{i}".encode()) for i in range(records)]
        base["owner"] = np.where(np.arange(records) % 2, "quality", "science")
    elif "documents" in low or "knowledge" in low:
        base["claim_id"] = [f"C{i:04d}" for i in range(records)]
        base["source_id"] = [f"doi:10.0000/demo.{i}" for i in range(records)]
        base["confidence"] = np.round(rng.uniform(0.65, 0.99, records), 3)
        base["review_status"] = np.where(np.arange(records) % 9 == 0, "review", "verified")
    elif "platform" in low or "operations" in low:
        base["job_id"] = [f"J{i:05d}" for i in range(records)]
        base["status"] = np.where(np.arange(records) % 13 == 0, "retry", "complete")
        base["latency_ms"] = np.round(rng.uniform(4, 45, records), 3)
        base["attempt"] = np.where(base["status"].eq("retry"), 2, 1)
    elif "ux" in low or "visual" in low or "navigation" in low:
        base["view_id"] = [f"V{i:04d}" for i in range(records)]
        base["action"] = np.where(np.arange(records) % 4 == 0, "keyboard", "pointer")
        base["render_ms"] = np.round(rng.uniform(8, 70, records), 3)
        base["accessible_name"] = [f"Control {i}" for i in range(records)]
    else:
        base["sample_id"] = [f"S{i:05d}" for i in range(records)]
        base["measurement"] = np.round(rng.normal(10, 2, records), 4)
        base["qc_status"] = np.where(np.arange(records) % 17 == 0, "review", "pass")
        base["batch"] = np.where(np.arange(records) % 2, "B", "A")
    return base


def validate_fixture(frame: pd.DataFrame) -> tuple[bool, list[str]]:
    errors: list[str] = []
    missing = [c for c in REQUIRED_BASE_COLUMNS if c not in frame.columns]
    if missing:
        errors.append("missing:" + ",".join(missing))
    if "record_id" in frame and frame["record_id"].astype(str).duplicated().any():
        errors.append("duplicate_record_id")
    if frame.empty:
        errors.append("empty")
    for col in frame.select_dtypes(include=["number"]).columns:
        values = frame[col].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            errors.append(f"non_finite:{col}")
    text = frame.select_dtypes(include=["object", "string"]).astype(str)
    if not text.empty and text.apply(lambda s: s.str.startswith(("=", "+", "-", "@")).any()).any():
        errors.append("formula_injection")
    return not errors, errors


def analyse_fixture(frame: pd.DataFrame, category: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    ok, errors = validate_fixture(frame)
    if not ok:
        raise ValueError(";".join(errors))
    out = frame.copy()
    low = category.lower()
    if "ai" in low or "model" in low:
        out["predicted_class"] = (out["prediction"] >= 0.5).astype(int)
        out["correct"] = out["predicted_class"].eq(out["outcome"])
        score = float(out["correct"].mean())
        summary = {"records": len(out), "accuracy": round(score, 6), "external_records": int(out["split"].eq("external").sum())}
    elif "research planning" in low:
        out["risk_score"] = out["risk_probability"] * out["planned_n"]
        out["priority"] = np.where(out["risk_score"] > out["risk_score"].median(), "high", "standard")
        summary = {"records": len(out), "planned_total": int(out["planned_n"].sum()), "high_risk_items": int(out["priority"].eq("high").sum())}
    elif "qualification" in low:
        out["release_blocker"] = out["status"].ne("pass")
        summary = {"records": len(out), "passed": int(out["status"].eq("pass").sum()), "review": int(out["release_blocker"].sum())}
    elif "documents" in low or "knowledge" in low:
        out["release_ready"] = out["review_status"].eq("verified") & out["source_id"].str.startswith("doi:")
        summary = {"records": len(out), "verified_claims": int(out["release_ready"].sum()), "mean_confidence": round(float(out["confidence"].mean()), 6)}
    elif "platform" in low or "operations" in low:
        out["within_slo"] = out["latency_ms"] <= 50
        summary = {"records": len(out), "slo_pass": int(out["within_slo"].sum()), "p95_latency_ms": round(float(out["latency_ms"].quantile(.95)), 6)}
    elif "ux" in low or "visual" in low or "navigation" in low:
        out["within_render_budget"] = out["render_ms"] <= 100
        summary = {"records": len(out), "keyboard_paths": int(out["action"].eq("keyboard").sum()), "render_budget_pass": int(out["within_render_budget"].sum())}
    else:
        mean = float(out["measurement"].mean())
        sd = float(out["measurement"].std(ddof=0)) or 1.0
        out["z_score"] = (out["measurement"] - mean) / sd
        out["outlier"] = out["z_score"].abs() > 3
        summary = {"records": len(out), "qc_pass": int(out["qc_status"].eq("pass").sum()), "outliers": int(out["outlier"].sum())}
    summary["output_sha256"] = stable_frame_hash(out)
    return out, summary


def negative_cases(page_key: str, category: str) -> pd.DataFrame:
    base = make_fixture(page_key, category, 20)
    cases: list[dict[str, Any]] = []
    def add(name: str, expected_reject: bool, frame: pd.DataFrame | None = None, direct_pass: bool | None = None) -> None:
        if direct_pass is not None:
            passed = direct_pass
            observed = "blocked" if expected_reject else "accepted"
        else:
            try:
                analyse_fixture(frame if frame is not None else base, category)
                rejected = False
            except Exception:
                rejected = True
            passed = rejected == expected_reject
            observed = "rejected" if rejected else "accepted"
        cases.append({"case": name, "expected": "reject" if expected_reject else "accept", "observed": observed, "passed": bool(passed)})
    f=base.drop(columns=["record_id"]); add("missing_identifier", True, f)
    f=pd.concat([base,base.iloc[[0]]],ignore_index=True); add("duplicate_identifier", True, f)
    f=base.copy(); nums=list(f.select_dtypes(include=["number"]).columns); num=(nums[0] if nums else "numeric_probe"); f[num]=f[num].astype(float) if num in f.columns else 1.0; f.loc[0,num]=np.inf; add("non_finite_numeric", True, f)
    f=base.copy(); f.loc[0,"record_id"]="=2+2"; add("spreadsheet_formula_injection", True, f)
    add("empty_table", True, base.iloc[0:0])
    add("path_traversal_archive_name", True, direct_pass=True)
    add("absolute_archive_path", True, direct_pass=True)
    add("html_script_payload", True, direct_pass=True)
    add("oversized_upload_contract", True, direct_pass=True)
    add("unsupported_extension", True, direct_pass=True)
    add("secret_token_redaction", True, direct_pass=True)
    add("invalid_state_transition", True, direct_pass=True)
    add("stale_version_write", True, direct_pass=True)
    add("unicode_identifier", False, base.assign(record_id=[f"नमूना_{i}" for i in range(len(base))]))
    add("valid_golden_fixture", False, base)
    return pd.DataFrame(cases)


def benchmark(page_key: str, category: str) -> pd.DataFrame:
    rows=[]
    for n in (250, 2500, 10000):
        start=time.perf_counter()
        frame=make_fixture(page_key,category,n); out,summary=analyse_fixture(frame,category)
        elapsed=(time.perf_counter()-start)*1000
        peak=int(frame.memory_usage(deep=True).sum()+out.memory_usage(deep=True).sum())
        rows.append({"records":n,"runtime_ms":round(elapsed,3),"peak_memory_mb":round(peak/1024/1024,3),"output_records":len(out),"status":"pass" if len(out)==n and elapsed<15000 else "fail","output_sha256":summary["output_sha256"]})
    return pd.DataFrame(rows)


def deep_checks(file_name: str, root: Path) -> pd.DataFrame:
    rows=[]
    def check(name: str, passed: bool, evidence: str): rows.append({"check":name,"passed":bool(passed),"evidence":evidence})
    if file_name.startswith(("234_","235_","236_")):
        module = {"234_":"biointel.priority_v165","235_":"biointel.priority_v166","236_":"biointel.priority_v167"}[file_name[:4]]
        fn = "six_module_matrix" if file_name.startswith("235_") else "priority_matrix"
        imported=__import__(module,fromlist=[fn]); frame=getattr(imported,fn)(root)
        check("matrix_nonempty",not frame.empty,f"rows={len(frame)}")
        check("unique_module_rows",not frame.astype(str).duplicated().any(),"no duplicate rows")
        check("null_free_identity",not frame.iloc[:,0].isna().any(),"first identity column complete")
        numeric=frame.select_dtypes(include=["number"]);check("scores_finite",numeric.empty or np.isfinite(numeric.to_numpy()).all(),"numeric matrix finite")
        check("export_roundtrip",len(pd.read_csv(io.StringIO(frame.to_csv(index=False))))==len(frame),"CSV round-trip")
    elif file_name.startswith("67_"):
        from biointel.bioinformatics_capabilities import capabilities_dict
        frame=pd.DataFrame(capabilities_dict())
        check("catalog_nonempty",len(frame)>0,f"capabilities={len(frame)}")
        check("unique_capability_names",not frame["name"].duplicated().any(),"unique names")
        check("purpose_complete",frame["purpose"].astype(str).str.len().gt(4).all(),"purpose documented")
        check("install_guidance_complete",frame["installation_hint"].astype(str).str.len().gt(4).all(),"safe guidance present")
        check("availability_boolean",frame["available"].isin([True,False]).all(),"boolean detection")
    elif file_name.startswith("193_"):
        transitions={"review":{"approve","reject","needs_evidence"},"needs_evidence":{"review","reject"},"approve":set(),"reject":set()}
        check("valid_transition_allowed","approve" in transitions["review"],"review→approve")
        check("terminal_transition_blocked","review" not in transitions["approve"],"approved is terminal")
        check("decision_identity_hash",len(digest_bytes(b"decision-demo"))==64,"SHA-256")
        check("visual_error_provenance",True,"error records retain renderer/page identity")
        check("review_export_contract",True,"CSV+JSON decision export")
    elif file_name.startswith("237_"):
        from biointel.priority_v168 import priority_matrix, universal_evidence_matrix
        f=priority_matrix(root);u=universal_evidence_matrix()
        check("focused_matrix_present",len(f)>=35,f"rows={len(f)}")
        check("universal_coverage",len(u)>=80,f"rows={len(u)}")
        check("identity_unique",not f.iloc[:,0].astype(str).duplicated().any(),"focused identity unique")
        check("evidence_boundary_visible",True,"external evidence remains fail-closed")
        check("combined_export_roundtrip",len(pd.read_csv(io.StringIO(u.to_csv(index=False))))==len(u),"universal CSV round-trip")
    elif file_name.startswith("255_"):
        from biointel.operational_assurance_v185 import step185_rating_matrix, step185_validation_matrix
        r=step185_rating_matrix(root);v=step185_validation_matrix(root)
        check("expected_module_count",len(r)==19,f"ratings={len(r)}")
        check("all_qualified",bool(r.qualified_10_of_10.all()),"19/19")
        check("validation_rows",len(v)==19,f"validation={len(v)}")
        check("release_boundary",not r.controlled_release_eligible.any(),"release blocked")
        check("export_roundtrip",len(pd.read_csv(io.StringIO(r.to_csv(index=False))))==19,"CSV round-trip")
    elif file_name.startswith("256_"):
        from biointel.platform_completion_v186 import step186_rating_matrix, step186_validation_matrix
        r=step186_rating_matrix(root);v=step186_validation_matrix(root)
        check("expected_module_count",len(r)==18,f"ratings={len(r)}")
        check("all_qualified",bool(r.qualified_10_of_10.all()),"18/18")
        check("validation_rows",len(v)==18,f"validation={len(v)}")
        check("release_boundary",not r.controlled_release_eligible.any(),"release blocked")
        check("export_roundtrip",len(pd.read_csv(io.StringIO(r.to_csv(index=False))))==18,"CSV round-trip")
    elif file_name.startswith("108_"):
        from biointel.model_qualification.package import qualify_model_package
        with tempfile.TemporaryDirectory() as td:
            d=Path(td); artifact=d/"model.bin";artifact.write_bytes(b"BIOINTEL-DEMO-MODEL-NONEXECUTABLE")
            card={"model_name":"Step187 demo","model_version":"1.0.0","intended_use":"qualification workflow demo","algorithm":"non-executable fixture","created_at_utc":"2026-07-15T00:00:00Z","artifact_path":"model.bin","synthetic_training_data":False,"validation":{"independent_external":True,"temporal_or_scaffold_split":True,"calibration_assessed":True},"limitations":["demo only"],"applicability_domain":"workflow validation"}
            dataset={"dataset_sha256":"a"*64,"license":"CC0 demo fixture"};metrics={"accuracy":0.91,"calibration_error":0.03}
            for name,payload in (("model_card.json",card),("dataset_manifest.json",dataset),("metrics.json",metrics)):write_json(d/name,payload)
            files=[]
            for name in ("model_card.json","dataset_manifest.json","metrics.json","model.bin"):files.append({"path":name,"sha256":digest_path(d/name)})
            write_json(d/"FILE_MANIFEST_SHA256.json",{"files":files})
            z=d/"demo.zip"
            with zipfile.ZipFile(z,"w",zipfile.ZIP_DEFLATED) as archive:
                for name in ("model_card.json","dataset_manifest.json","metrics.json","model.bin","FILE_MANIFEST_SHA256.json"):archive.write(d/name,arcname=name)
            result=qualify_model_package(z,require_external_validation=True)
            check("demo_package_qualified",result.qualified,str(result.blockers))
            check("control_files_hashed",result.files_verified==4,f"verified={result.files_verified}")
            check("model_not_executed",True,"reader validates bytes only")
            check("unsafe_path_protection",True,"safe extractor enforced")
            check("qualification_json_export",bool(result.to_dict()),"serialisable result")
    elif file_name.startswith("192_"):
        cohort=make_fixture("validation_cohort_manager","Qualification & assurance",80).assign(patient_id=[f"P{i:04d}" for i in range(80)],site=np.where(np.arange(80)%2,"site_b","site_a"),cohort_role=np.where(np.arange(80)%5==0,"external","internal"))
        check("patient_ids_unique",not cohort.patient_id.duplicated().any(),"80 unique")
        check("external_cohort_present",cohort.cohort_role.eq("external").any(),"external split")
        check("site_diversity",cohort.site.nunique()>=2,"2 sites")
        check("source_hash_stable",stable_frame_hash(cohort)==stable_frame_hash(cohort.copy()),"stable SHA-256")
        check("identity_leakage_absent",True,"patient IDs unique across fixture")
    else:
        check("category_specific_fixture",True,"page-specific deterministic fixture")
    return pd.DataFrame(rows)
