"""Audit release candidates, or the Git index and every reachable history blob.
Reports paths only, never matching secret values. No network operations.
"""
import argparse,hashlib,json,re,subprocess,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FILES=['.gitignore','.npmrc','AGENTS.md','README.md','HANDOFF.md','start.cmd','package.json','package-lock.json','backend/catalog.json','backend/phone-rules.json','backend/settings.example.json','frontend/assets/demo-header.svg','tests/test_api.py','tests/test_events_v4.py','tests/fixtures.example.json','tests/browser.cjs','tests/browser-v4.cjs','tests/seed_legacy_v4.py','handoff/audit.py']
FILES+=sorted(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'backend').glob('*.py'))
for pattern in ('*.html','*.js','*.css'):
    FILES+=sorted(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'frontend').glob(pattern))
FILES=sorted(set(FILES))
FILES=sorted(set(FILES+['demo/runtime.js','handoff/build_demo.py','.github/workflows/pages.yml','tests/pages.cjs']))
SECRET=re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|https?://[^\s/@]+:[^\s/@]+@)')
private=[]
settings=ROOT/'backend/settings.json'
if settings.exists():
    for b in json.loads(settings.read_text(encoding='utf-8'))['branches']:
        if b.get('can_issue'):
            private += [b['signer'].encode(),b['footer_phone'].encode()]
fixtures=ROOT/'tests/fixtures.json'
def collect(v):
    if isinstance(v,dict):
        for k,x in v.items():
            if k in ('recipient','address','new_address','pickup_address','signed_by','waybill','number') and isinstance(x,str) and len(x)>8:private.append(x.encode())
            else:collect(x)
    elif isinstance(v,list):
        for x in v:collect(x)
if fixtures.exists():collect(json.loads(fixtures.read_text(encoding='utf-8')))
def check_content(name,body):
    if SECRET.search(body) or any(x in body for x in private):raise SystemExit('BLOCKED: possible secret/private source value in '+name)

def check(name,body):
    if name not in FILES:raise SystemExit('BLOCKED: unexpected path '+name)
    check_content(name,body)
def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args])
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--git',action='store_true');ap.add_argument('--pages',action='store_true');args=ap.parse_args()
    for name in FILES:check(name,(ROOT/name).read_bytes())
    if args.pages:
        allowed={'index.html','app.js','components.js','styles.css','runtime.js','vue.js','VUE-LICENSE.txt','catalog.json','phone-rules.json','settings.json','assets/demo-header.svg','.nojekyll'}
        output=ROOT/'artifacts/pages'
        actual={p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
        if actual!=allowed:raise SystemExit('BLOCKED: unexpected Pages artifact files')
        for name in actual:check_content('Pages/'+name,(output/name).read_bytes())
        print('Pages artifact: all 12 files scanned.')
    if args.git:
        if not shutil.which('git'):raise SystemExit('Git is not available')
        if Path(git('rev-parse','--show-toplevel').decode().strip()).resolve()!=ROOT:raise SystemExit('Wrong Git root')
        staged=[p for p in git('ls-files','-z').decode().split('\0') if p]
        if set(staged)!=set(FILES):raise SystemExit('Git index differs from reviewed release manifest')
        for name in staged:check(name,git('show',':'+name))
        for commit in git('rev-list','--all').decode().splitlines():
            for row in git('ls-tree','-r','-z',commit).split(b'\0'):
                if not row:continue
                meta,path=row.split(b'\t',1);check(path.decode(),git('cat-file','blob',meta.split()[2].decode()))
        print('Git index and all reachable commit trees checked.')
    report={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in FILES}
    target=ROOT/'artifacts/handoff';target.mkdir(parents=True,exist_ok=True)
    (target/'manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(f'PASS: {len(FILES)} candidate files. No database, original references or real letterhead.')
if __name__=='__main__':main()
