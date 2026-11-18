from __future__ import annotations
import argparse, json, shutil, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'
if str(SRC) not in sys.path: sys.path.insert(0,str(SRC))
from biointel.external_v172 import ALL_MODULES, Step172Registry

parser=argparse.ArgumentParser(description='Import and evaluate Step 172 external confirmation packages.')
sub=parser.add_subparsers(dest='command',required=True)
sub.add_parser('status')
p=sub.add_parser('evaluate'); p.add_argument('module_key',choices=ALL_MODULES); p.add_argument('--manifest')
p=sub.add_parser('import'); p.add_argument('module_key',choices=ALL_MODULES); p.add_argument('manifest'); p.add_argument('--actor',default='local-operator')
p=sub.add_parser('prepare'); p.add_argument('module_key',choices=ALL_MODULES); p.add_argument('--destination')
sub.add_parser('evaluate-all')
args=parser.parse_args(); registry=Step172Registry(ROOT)
if args.command=='status': result=registry.status()
elif args.command=='evaluate': result=registry.evaluate_submission(args.module_key,args.manifest)
elif args.command=='import': result=registry.import_submission(args.module_key,args.manifest,actor=args.actor)
elif args.command=='prepare':
 src=ROOT/'data'/'step172'/'module_packages'/args.module_key
 dst=Path(args.destination).resolve() if args.destination else registry.submissions/args.module_key
 if dst.exists(): shutil.rmtree(dst)
 shutil.copytree(src,dst)
 template=dst/'confirmation_manifest_template.json'
 manifest=dst/'confirmation_manifest.json'
 shutil.copy2(template,manifest)
 result={'status':'prepared','module_key':args.module_key,'submission_directory':str(dst),'manifest':str(manifest)}
else:
 frame=registry.matrix(refresh=True)
 out=ROOT/'reports'/'step172_external_confirmation_matrix.csv'; out.parent.mkdir(parents=True,exist_ok=True); frame.to_csv(out,index=False)
 result={'status':'evaluated','modules':len(frame),'release_eligible':int(frame['release_eligible'].sum()),'matrix':str(out)}
print(json.dumps(result,indent=2,default=str))
