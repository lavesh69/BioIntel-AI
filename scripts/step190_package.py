from __future__ import annotations
import argparse,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEFAULT='BioIntel-AI-Step190-SCIENTIFIC-EXECUTION-INTEROPERABILITY-80OF80-10OF10'

def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def source_files():
    return sorted(p for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts and p.suffix not in {'.pyc','.pyo'})

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--output-dir',type=Path,default=ROOT.parent);ap.add_argument('--name',default=DEFAULT);a=ap.parse_args()
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    files=source_files(); buckets=[[] for _ in range(4)]; sizes=[0]*4
    for p in sorted(files,key=lambda x:x.stat().st_size,reverse=True):
        i=min(range(4),key=lambda j:sizes[j]);buckets[i].append(p);sizes[i]+=p.stat().st_size
    outputs=[]
    for i,bucket in enumerate(buckets,1):
        zpath=out/f'{a.name}-Part{i}.zip'
        with zipfile.ZipFile(zpath,'w',zipfile.ZIP_DEFLATED,compresslevel=5,allowZip64=True) as z:
            for src in sorted(bucket):z.write(src,Path('BioIntel-AI')/src.relative_to(ROOT))
            z.writestr(f'BioIntel-AI/.release_parts/step190_part{i}.ok','step190\n')
        outputs.append(zpath)
    checks={p.name:{'sha256':sha(p),'size_bytes':p.stat().st_size} for p in outputs}
    (out/f'{a.name}-CHECKSUMS.json').write_text(json.dumps(checks,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'files':len(files),'part_sizes':sizes,'outputs':checks},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
