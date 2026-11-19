"""Build an isolated, entirely static Pages artifact from reviewed sources."""
import json,re,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/pages'
OUT.mkdir(parents=True,exist_ok=True)
for name in ('components.js','styles.css'):shutil.copyfile(ROOT/'frontend'/name,OUT/name)
shutil.copyfile(ROOT/'demo/runtime.js',OUT/'runtime.js')
shutil.copyfile(ROOT/'node_modules/vue/dist/vue.global.prod.js',OUT/'vue.js')
shutil.copyfile(ROOT/'node_modules/vue/LICENSE',OUT/'VUE-LICENSE.txt')
sys.path.insert(0,str(ROOT/'backend'))
from domain_helpers import resolve_catalog
(OUT/'catalog.json').write_text(json.dumps(resolve_catalog(json.loads((ROOT/'backend/catalog.json').read_text(encoding='utf-8'))),ensure_ascii=False,indent=2),encoding='utf-8')
shutil.copyfile(ROOT/'backend/phone-rules.json',OUT/'phone-rules.json')
cfg=json.loads((ROOT/'backend/settings.example.json').read_text(encoding='utf-8'))
cfg['branches']=[b for b in cfg['branches'] if b['can_issue']]
for b in cfg['branches']:b['header_image']='./assets/demo-header.svg'
(OUT/'settings.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'assets').mkdir(exist_ok=True)
shutil.copyfile(ROOT/'frontend/assets/demo-header.svg',OUT/'assets/demo-header.svg')
app=(ROOT/'frontend/app.js').read_text(encoding='utf-8')
start=app.index('  async request(url,body){');end=app.index('\n  async load()',start)
app=app[:start]+'  async request(url,body){return Demo.request(url,body);},'+app[end:]
(OUT/'app.js').write_text(app,encoding='utf-8')
html=(ROOT/'frontend/index.html').read_text(encoding='utf-8')
html=html.replace('href="/styles.css"','href="./styles.css"')
for name in ('vue.js','components.js','app.js'):html=html.replace('src="/'+name+'"','src="./'+name+'"')
html=html.replace('<script defer src="./app.js">','<script defer src="./runtime.js"></script><script defer src="./app.js">')
html=html.replace('<main>','<main><div class="notice demo-disclaimer" role="note"><b>Статическая демонстрация. Используйте только вымышленные данные.</b> Архив и нумерация хранятся только в текущем браузере (localStorage), не передаются на сервер и не синхронизируются. Очистка данных браузера удалит демонстрационный архив. Это не рабочая система.</div>')
html=html.replace('Локальная демонстрация','Статическая демонстрация').replace('Шапка ТОО Рика из образца Астаны','Вымышленная демонстрационная шапка').replace('Номер в просмотре предварительный.','Нумерация только в этом браузере. Номер в просмотре предварительный.')
(OUT/'index.html').write_text(html,encoding='utf-8')
(OUT/'.nojekyll').write_text('',encoding='utf-8')
expected={'index.html','app.js','components.js','styles.css','runtime.js','vue.js','VUE-LICENSE.txt','catalog.json','phone-rules.json','settings.json','assets/demo-header.svg','.nojekyll'}
actual={p.relative_to(OUT).as_posix() for p in OUT.rglob('*') if p.is_file()}
if actual!=expected:raise SystemExit('Unexpected Pages artifact contents; publication blocked')
for name in actual-{'vue.js','VUE-LICENSE.txt'}:
    if re.search(r'https?://(?:localhost|127\.0\.0\.1)|fetch\([\x27\x22]/api', (OUT/name).read_text(encoding='utf-8')):raise SystemExit('Local server reference in artifact: '+name)
print('Static artifact ready: 12 files; only fictional configuration, no database or Python.')
