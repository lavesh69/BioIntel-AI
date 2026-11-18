from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from biointel.runtime_paths import user_data_root
from .catalog import ASSURANCE_DIMENSIONS, TARGET_PROFILES

@dataclass(frozen=True)
class OperationalAssuranceValidation:
    module_key:str; rating:float; qualified_10_of_10:bool; dimensions_passed:int; dimensions_total:int; hashes_passed:bool; real_external_evidence:bool; controlled_release_eligible:bool; blockers:tuple[str,...]; path:str

def _digest(path:Path)->str: return sha256(path.read_bytes()).hexdigest()

def validate_step185_module(root:str|Path,module_key:str)->OperationalAssuranceValidation:
    project=Path(root).resolve(); folder=user_data_root(project)/"step185/operational_assurance"/module_key; blockers=[]; payload={}
    try: payload=json.loads((folder/"assurance_manifest.json").read_text(encoding="utf-8-sig"))
    except Exception as exc: blockers.append(f"manifest_invalid:{exc}")
    if payload:
        if payload.get("schema")!="biointel.step185.operational-assurance-manifest.v1": blockers.append("manifest_schema")
        if payload.get("module_key")!=module_key: blockers.append("module_identity")
        if payload.get("synthetic_demo") is not True: blockers.append("demo_boundary")
        if payload.get("real_external_evidence") is not False: blockers.append("demo_marked_real")
        if payload.get("controlled_release_eligible") is not False: blockers.append("demo_unlocked_release")
    dims=payload.get("dimensions",[]) if isinstance(payload.get("dimensions"),list) else []; names=tuple(str(x.get("dimension")) for x in dims)
    if names!=ASSURANCE_DIMENSIONS: blockers.append("dimension_contract")
    passed=sum(bool(x.get("passed")) for x in dims); rating=round(10.0*passed/len(ASSURANCE_DIMENSIONS),2)
    if passed!=len(ASSURANCE_DIMENSIONS) or rating!=10.0: blockers.append("not_10_of_10")
    hashes=True; files=payload.get("files",[]) if isinstance(payload.get("files"),list) else []
    if not files: hashes=False; blockers.append("empty_file_manifest")
    for item in files:
        rel=str(item.get("path","")).replace("\\","/"); pure=PurePosixPath(rel); path=folder/pure; expected=str(item.get("sha256","")).lower()
        if not rel or pure.is_absolute() or ".." in pure.parts or not path.is_file() or len(expected)!=64 or _digest(path)!=expected: hashes=False; blockers.append(f"hash_mismatch:{rel}")
    qualified=not blockers and hashes and rating==10.0 and module_key in TARGET_PROFILES
    return OperationalAssuranceValidation(module_key,rating,qualified,passed,len(ASSURANCE_DIMENSIONS),hashes,False,False,tuple(blockers),str(folder))

__all__=["OperationalAssuranceValidation","validate_step185_module"]
