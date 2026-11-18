from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
import json
from biointel.runtime_paths import user_data_root
from .catalog import ASSURANCE_DIMENSIONS, TARGET_PROFILES
from .engine import slug

@dataclass(frozen=True)
class PageExcellenceValidation:
    file_name: str
    rating: float
    qualified_10_of_10: bool
    dimensions_passed: int
    dimensions_total: int
    hashes_passed: bool
    hook_present: bool
    real_external_evidence_changed: bool
    controlled_release_eligible: bool
    blockers: tuple[str,...]
    path: str

def _digest(path:Path)->str:return sha256(path.read_bytes()).hexdigest()

def validate_step187_page(root:str|Path,file_name:str)->PageExcellenceValidation:
    project=Path(root).resolve();p=TARGET_PROFILES[file_name];folder=user_data_root(project)/"step187/page_excellence"/slug(Path(file_name).stem);blockers=[];payload={}
    try:payload=json.loads((folder/"assurance_manifest.json").read_text(encoding="utf-8-sig"))
    except Exception as exc:blockers.append(f"manifest_invalid:{exc}")
    if payload:
        if payload.get("schema")!="biointel.step187.page-excellence-manifest.v1":blockers.append("manifest_schema")
        if payload.get("file_name")!=file_name:blockers.append("page_identity")
        if payload.get("internal_demo_only") is not True:blockers.append("demo_boundary")
        if payload.get("real_external_evidence_changed") is not False:blockers.append("external_evidence_boundary")
        if payload.get("controlled_release_eligible") is not False:blockers.append("release_boundary")
    dims=payload.get("dimensions",[]) if isinstance(payload.get("dimensions"),list) else [];names=tuple(str(x.get("dimension")) for x in dims)
    if names!=ASSURANCE_DIMENSIONS:blockers.append("dimension_contract")
    passed=sum(bool(x.get("passed")) for x in dims);rating=round(10*passed/len(ASSURANCE_DIMENSIONS),2)
    if rating!=10 or passed!=len(ASSURANCE_DIMENSIONS):blockers.append("not_10_of_10")
    hashes=True;files=payload.get("files",[]) if isinstance(payload.get("files"),list) else []
    if not files:hashes=False;blockers.append("empty_file_manifest")
    for item in files:
        rel=str(item.get("path","")).replace("\\","/");pure=PurePosixPath(rel);path=folder/pure;expected=str(item.get("sha256","")).lower()
        if not rel or pure.is_absolute() or ".." in pure.parts or not path.is_file() or len(expected)!=64 or _digest(path)!=expected:hashes=False;blockers.append(f"hash_mismatch:{rel}")
    source=(project/"pages"/file_name).read_text(encoding="utf-8-sig");hook="STEP187_PAGE_EXCELLENCE_HOOK" in source and "render_step187_page_excellence" in source
    if not hook:blockers.append("page_hook_missing")
    qualified=not blockers and hashes and hook and file_name in TARGET_PROFILES
    return PageExcellenceValidation(file_name,rating,qualified,passed,len(ASSURANCE_DIMENSIONS),hashes,hook,False,False,tuple(blockers),str(folder))
__all__=["PageExcellenceValidation","validate_step187_page"]
