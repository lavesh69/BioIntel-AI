from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parents[2]
OUTPUT = OUT / "BioIntel-AI-Step183-DEMO-FILES-80-MODULES.zip"
BASE = ROOT / "UserData" / "step183" / "module_demos"
EXTRAS = [
    ROOT / "STEP183_80_MODULE_DEMO_RATINGS.csv",
    ROOT / "STEP183_80_MODULE_DEMO_RATINGS.md",
    ROOT / "STEP183_ALL_MODULE_DEMO_REPORT.md",
    ROOT / "STEP183_DEMO_RATING_SUMMARY.json",
    ROOT / "LOAD_STEP183_ALL_MODULE_DEMOS_WINDOWS.bat",
]


def digest(path: Path) -> str:
    h=sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

OUTPUT.unlink(missing_ok=True)
with zipfile.ZipFile(OUTPUT,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for path in sorted(BASE.rglob('*')):
        if path.is_file():
            z.write(path, f"Step183-Demo-Files/{path.relative_to(BASE).as_posix()}")
    for path in EXTRAS:
        z.write(path, f"Step183-Demo-Files/{path.name}")

unsafe=[]
with zipfile.ZipFile(OUTPUT) as z:
    bad=z.testzip()
    for name in z.namelist():
        pure=PurePosixPath(name)
        if name.startswith('/') or '..' in pure.parts: unsafe.append(name)
report={
 'schema':'biointel.step183.demo-only-integrity.v1',
 'status':'passed' if not bad and not unsafe else 'failed',
 'file':OUTPUT.name,'size_bytes':OUTPUT.stat().st_size,'sha256':digest(OUTPUT),
 'members':len(zipfile.ZipFile(OUTPUT).infolist()),'crc_error':bad,'unsafe_paths':unsafe,
}
(OUT/'STEP183_DEMO_ONLY_INTEGRITY.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
if report['status']!='passed': raise SystemExit(1)
