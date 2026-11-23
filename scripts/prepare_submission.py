"""Create a reviewable clean source snapshot from Git-visible files, never ignored local state."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('destination',type=Path)
args=parser.parse_args()
destination=args.destination.resolve()
if destination==root or root in destination.parents:
    raise ValueError('Destination must be outside the working repository')
files=subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=root).decode().split('\0')
entries=[]
secret=re.compile(rb'(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{35,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
for name in sorted(set(files)-{''}):
    path=root/name
    if not path.is_file():
        continue
    if path.is_symlink() or name=='.env' or name.startswith(('.agent/','logs/','private/','data/raw/','data/processed/','data/index/')) or name.endswith('.kubeconfig'):
        raise ValueError(f'Excluded local file is Git-visible: {name}')
    body=path.read_bytes()
    if secret.search(body):
        raise ValueError(f'Credential-like content needs review in {name}')
    entries.append({'path':name,'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)})
destination.mkdir(parents=True,exist_ok=False)
for item in entries:
    target=destination/item['path']
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(root/item['path'],target)
manifest={'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
          'note':'Working-tree snapshot, not a published commit. Ignored credentials, logs, downloaded corpus and local environments excluded. Pattern scan is not a complete secret audit.',
          'files':entries}
(destination/'submission-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'destination':str(destination),'files':len(entries),'bytes':sum(x['bytes'] for x in entries)}))
