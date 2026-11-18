from __future__ import annotations
import argparse,hashlib,json,posixpath,zipfile
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEFAULT='BioIntel-AI-Step190-SCIENTIFIC-EXECUTION-INTEROPERABILITY-80OF80-10OF10'

def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def unsafe(name:str)->bool:
    n=name.replace('\\','/')
    return n.startswith('/') or ':' in n.split('/')[0] or any(x=='..' for x in n.split('/')) or posixpath.normpath(n).startswith('../')

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--output-dir',type=Path,default=ROOT.parent);ap.add_argument('--name',default=DEFAULT);a=ap.parse_args();out=a.output_dir.resolve()
    expected={str(Path('BioIntel-AI')/p.relative_to(ROOT)).replace('\\','/') for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts and p.suffix not in {'.pyc','.pyo'}}
    parts=[out/f'{a.name}-Part{i}.zip' for i in range(1,5)]
    all_names=[];crc_errors=[];unsafe_paths=[];markers=[]
    for p in parts:
        try:
            with zipfile.ZipFile(p) as z:
                bad=z.testzip()
                if bad:crc_errors.append({'part':p.name,'file':bad})
                for info in z.infolist():
                    if info.is_dir():continue
                    all_names.append(info.filename)
                    if unsafe(info.filename):unsafe_paths.append({'part':p.name,'file':info.filename})
                    if '/.release_parts/step190_part' in info.filename:markers.append(info.filename)
        except Exception as exc:crc_errors.append({'part':p.name,'error':str(exc)})
    counts=Counter(all_names);duplicates=sorted(k for k,v in counts.items() if v>1)
    actual=set(all_names)-set(markers)
    missing=sorted(expected-actual);extra=sorted(actual-expected)
    checks={p.name:{'sha256':sha(p),'size_bytes':p.stat().st_size} for p in parts if p.is_file()}
    status='passed' if not crc_errors and not unsafe_paths and not duplicates and not missing and not extra and len(markers)==4 else 'failed'
    result={'schema':'biointel.step190.package_integrity.v1','status':status,'source_files':len(expected),'packaged_source_files':len(actual),
            'package_entries_including_markers':len(all_names),'release_markers':sorted(markers),'missing_files':missing,'extra_files':extra,
            'duplicate_files':duplicates,'crc_errors':crc_errors,'unsafe_paths':unsafe_paths,'checksums':checks}
    (out/f'{a.name}-PACKAGE-INTEGRITY.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2));return 0 if status=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
