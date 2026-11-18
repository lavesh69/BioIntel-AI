from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import zipfile
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT.parents[2]/"BioIntel-AI-Step185-OPERATIONAL-ASSURANCE-19-MODULES.zip"
BASE=ROOT/"UserData/step185/operational_assurance"
EXTRAS=[ROOT/"STEP185_19_MODULE_BEFORE_AFTER_RATINGS.csv",ROOT/"STEP185_19_MODULE_BEFORE_AFTER_RATINGS.md",ROOT/"STEP185_19_MODULE_ASSURANCE_DETAILS.csv",ROOT/"STEP185_80_MODULE_FINAL_DEMO_RATINGS.csv",ROOT/"STEP185_UPGRADE_REPORT.md",ROOT/"STEP185_RELEASE.json"]
FIXED_DATE=(2026,7,15,0,0,0)
def sha(p):
 h=sha256();
 with p.open("rb") as f:
  for c in iter(lambda:f.read(1024*1024),b""): h.update(c)
 return h.hexdigest()
OUT.unlink(missing_ok=True); files=sorted([p for p in BASE.rglob("*") if p.is_file()]+[p for p in EXTRAS if p.is_file()])
with zipfile.ZipFile(OUT,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
 for p in files:
  rel=(Path("step185_operational_assurance")/p.relative_to(BASE)) if p.is_relative_to(BASE) else (Path("reports")/p.name)
  info=zipfile.ZipInfo(rel.as_posix(),FIXED_DATE); info.compress_type=zipfile.ZIP_DEFLATED; info.external_attr=0o100644<<16; z.writestr(info,p.read_bytes())
with zipfile.ZipFile(OUT) as z:
 bad=z.testzip(); unsafe=[n for n in z.namelist() if PurePosixPath(n).is_absolute() or ".." in PurePosixPath(n).parts]
report={"schema":"biointel.step185.assurance-only-integrity.v1","status":"passed" if bad is None and not unsafe else "failed","file_count":len(files),"size_bytes":OUT.stat().st_size,"sha256":sha(OUT),"crc_error":bad,"unsafe_paths":unsafe}
(ROOT.parents[2]/"STEP185_OPERATIONAL_ASSURANCE_ONLY_INTEGRITY.json").write_text(json.dumps(report,indent=2)+"\n"); print(json.dumps(report,indent=2))
