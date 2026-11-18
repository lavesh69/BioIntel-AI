from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NAME = "BioIntel-AI-Step189-UNIVERSAL-PRODUCTION-PLATFORM-80OF80-10OF10"

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',type=Path,default=ROOT.parent)
    parser.add_argument('--name',default=DEFAULT_NAME)
    args=parser.parse_args(); out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    files=sorted(p for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts)
    buckets=[[] for _ in range(4)];sizes=[0,0,0,0]
    for path in sorted(files,key=lambda p:p.stat().st_size,reverse=True):
        i=min(range(4),key=lambda x:sizes[x]);buckets[i].append(path);sizes[i]+=path.stat().st_size
    outputs=[]
    for i,bucket in enumerate(buckets,1):
        path=out/f'{args.name}-Part{i}.zip'
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
            for source in sorted(bucket):z.write(source,Path('BioIntel-AI')/source.relative_to(ROOT))
            z.writestr(f'BioIntel-AI/.release_parts/step189_part{i}.ok','step189\n')
        outputs.append(path)
    checks={p.name:{'sha256':sha(p),'size_bytes':p.stat().st_size} for p in outputs}
    (out/f'{args.name}-CHECKSUMS.json').write_text(json.dumps(checks,indent=2)+'\n')
    print(json.dumps(checks,indent=2))
    return 0
if __name__=='__main__':raise SystemExit(main())
