import importlib.util,json,sqlite3,tempfile,threading,unittest,uuid
from contextlib import closing
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('server',ROOT/'backend/server.py');server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
from domain import validate,render,ValidationError
from phones import normalize_phone
FIXTURES=json.loads((ROOT/'tests/fixtures.example.json').read_text(encoding='utf-8'))
def fixture(name='short'):
    old=deepcopy(FIXTURES[name]);doc={k:old[k] for k in ('customer','recipient','address','waybill','order_date','notification_date','events')}
    if old['kind']!='delivery':doc['events'].append({'type':old['kind'],'result':'completed','fields':{}})
    for i,e in enumerate(doc['events']):
        e['id']='event-'+str(i)
        e['fields'].pop('source',None);e['fields'].pop('approved',None)
        for v in e['fields'].values():
            if isinstance(v,list):
                for p in v:p['country']=p['country'].upper()
    return doc

class ApiTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=ROOT);server.DB=Path(self.temp.name)/'test.sqlite3';server.initialize();self.original_settings=server.settings
  self.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start();self.url='http://127.0.0.1:'+str(self.http.server_port)
 def tearDown(self):
  self.http.shutdown();self.http.server_close();self.thread.join();server.settings=self.original_settings;self.temp.cleanup()
 def request(self,path,body=None):
  req=Request(self.url+path,json.dumps(body).encode() if body is not None else None,{'Content-Type':'application/json'})
  with urlopen(req,timeout=15) as r:return json.load(r)
 def save(self,doc=None,**kwargs):
  body={'branch':'astana','request_key':str(uuid.uuid4()),'document':doc or fixture()};body.update(kwargs);return self.request('/api/notifications',body)
 def test_visit_delivery_preview_save_copy(self):
  doc=fixture();doc['events']=[{'id':'visit1','type':'visit','result':'delivered','date':'2026-01-12','fields':{'signed_by':'Примеров П. П.'}}]
  preview=self.request('/api/preview',{'branch':'astana','document':doc})
  self.assertEqual(preview['document']['kind'],'delivery');self.assertEqual(self.request('/api/notifications'),[])
  original=self.save(doc);same=self.save(doc,id=original['id'],revision=original['revision'])
  self.assertEqual(original['document'],same['document'])
  copied=self.save(deepcopy(doc));self.assertNotEqual(copied['id'],original['id'])
  self.assertEqual(self.request('/api/notifications/'+str(original['id']))['document'],original['document'])
  self.assertEqual(len(copied['document']['events']),1)
  doc['events'][0]['fields']={}
  with self.assertRaises(HTTPError):self.request('/api/preview',{'branch':'astana','document':doc})
 def test_preview_counter_87_idempotent_copy_edit(self):
  self.request('/api/counter',{'branch':'astana','year':2026,'last_used':87})
  for _ in range(3):self.assertEqual(self.request('/api/preview',{'branch':'astana','document':fixture()})['document']['outgoing_number'],'88')
  self.assertEqual(self.request('/api/notifications'),[])
  key=str(uuid.uuid4());original=self.save(request_key=key);again=self.save(request_key=key)
  self.assertEqual(original['id'],again['id']);self.assertEqual(original['document']['outgoing_number'],'88')
  self.assertEqual(original['document']['addressee'],original['document']['customer'])
  unchanged=self.save(id=original['id'],revision=1);self.assertEqual(unchanged['revision'],1)
  changed=fixture();changed['customer']='Новый заказчик';updated=self.save(changed,id=original['id'],revision=1)
  self.assertEqual(updated['document']['outgoing_number'],'88');self.assertEqual(updated['revision'],2)
  copied=self.save(fixture());self.assertEqual(copied['document']['outgoing_number'],'89');self.assertNotEqual(copied['id'],original['id'])
  self.assertEqual(self.request('/api/notifications/'+str(original['id']))['document']['customer'],'Новый заказчик')
  with self.assertRaises(HTTPError):self.request('/api/counter',{'branch':'astana','year':2026,'last_used':87})
 def test_parallel_unique_and_repeat(self):
  self.request('/api/counter',{'branch':'astana','year':2026,'last_used':87})
  with ThreadPoolExecutor(max_workers=8) as pool:rows=list(pool.map(lambda _:self.save(),range(8)))
  self.assertEqual(sorted(int(r['document']['outgoing_number']) for r in rows),list(range(88,96)))
  key=str(uuid.uuid4())
  with ThreadPoolExecutor(max_workers=5) as pool:repeats=list(pool.map(lambda _:self.save(request_key=key),range(5)))
  self.assertEqual(len({r['id'] for r in repeats}),1)
  self.assertEqual(self.request('/api/counter?branch=astana&year=2026')['next_number'],97)
 def test_year_branch_restart_delete_does_not_reissue(self):
  profile=deepcopy(self.original_settings());other=deepcopy(profile['branches'][0]);other['branch_id']='test-branch';profile['branches'].append(other);server.settings=lambda:profile
  d=fixture();d['notification_date']='2026-12-31';a=self.save(d)
  d['notification_date']='2027-01-01';b=self.save(d)
  self.assertEqual(a['document']['outgoing_number'],'1');self.assertEqual(b['document']['outgoing_number'],'1')
  c=self.save(d,branch='test-branch');self.assertEqual(c['document']['outgoing_number'],'1')
  with self.assertRaises(HTTPError):self.save(d,id=a['id'],revision=a['revision'])
  with server.connect() as con:con.execute('DELETE FROM notifications WHERE id=?',(b['id'],))
  server.initialize();self.assertEqual(self.save(d)['document']['outgoing_number'],'2')
  with server.connect() as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM issued_numbers').fetchone()[0],4)
 def test_migration_preserves_old_document_and_reserves_number(self):
  server.DB=Path(self.temp.name)/'old.sqlite3';old=deepcopy(FIXTURES['short']);old['outgoing_number']='87';old['customer']='Заказчик';old['addressee']='Другой адресат';payload=json.dumps(old,ensure_ascii=False)
  with closing(sqlite3.connect(server.DB)) as con:
   con.execute('CREATE TABLE notifications(id INTEGER PRIMARY KEY,branch TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,payload TEXT NOT NULL)');con.execute('INSERT INTO notifications VALUES(1,?,?,?,?)',('astana','2026-01-13','2026-01-13',payload));con.commit()
  server.initialize();self.assertEqual(self.request('/api/notifications/1')['document'],old)
  self.assertEqual(self.save()['document']['outgoing_number'],'88')
  with self.assertRaises(HTTPError):self.save(id=1,revision=1)
  with server.connect() as con:self.assertEqual(con.execute('SELECT payload FROM notifications WHERE id=1').fetchone()[0],payload)
 def test_invalid_numbers_and_field_errors_do_not_issue(self):
  for n in ('0'*12,'0'*14,'000000000000a',1234567890123):
   d=fixture();d['waybill']=n
   with self.assertRaises(HTTPError) as err:self.save(d)
   body=json.load(err.exception);self.assertEqual(body['field'],'waybill')
  self.assertEqual(self.request('/api/counter?branch=astana&year=2026')['next_number'],1)
  d=fixture();d['waybill']='0'*13;self.assertEqual(self.save(d)['document']['waybill'],'0'*13)
 def test_explicit_legacy_edit_preserves_original_archive_version(self):
  old=deepcopy(FIXTURES['short']);old['schema_version']=3;old['final_event']={'kind':'delivery'};old['outgoing_number']='87';old['customer']='Заказчик';old['addressee']='Прежний другой адресат';payload=json.dumps(old,ensure_ascii=False)
  server.DB=Path(self.temp.name)/'legacy-edit.sqlite3'
  with closing(sqlite3.connect(server.DB)) as con:
   con.execute('CREATE TABLE notifications(id INTEGER PRIMARY KEY,branch TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,payload TEXT NOT NULL)');con.execute('INSERT INTO notifications VALUES(1,?,?,?,?)',('astana','2026-01-13','2026-01-13',payload));con.commit()
  server.initialize()
  converted=self.request('/api/convert',{'branch':'astana','document':old})['document']
  self.assertEqual(len(converted['events']),1)
  self.assertEqual(self.request('/api/notifications/1')['document'],old)
  edited=self.save(converted,id=1,revision=1,edit_legacy=True)
  self.assertEqual(edited['document']['outgoing_number'],'87');self.assertEqual(edited['document']['schema_version'],4)
  self.assertNotIn('final_event',edited['document']);self.assertEqual(edited['document']['addressee'],'Заказчик')
  versions=self.request('/api/notifications/1/versions');self.assertEqual(versions[0]['document'],old)
  with server.connect() as con:self.assertEqual(con.execute('SELECT payload FROM notification_versions').fetchone()[0],payload)
  copied=self.save(converted);self.assertEqual(copied['document']['outgoing_number'],'88')

class FactsTests(unittest.TestCase):
 def test_completed_only_no_duplicate_final_and_no_hidden_dates(self):
  for name in FIXTURES:
   d=validate(fixture(name));r=render(d,server.branch_by_id('astana'));body=' '.join(r['paragraphs'])
   self.assertNotIn('подлежит',body+r['intro_after']);self.assertNotIn('outcome_date',d);self.assertNotIn('outcome_approved',d)
   if name=='short':self.assertEqual(body.count('корреспонденция вручена'),1)
   else:self.assertEqual(body.count('произведен возврат')+body.count('произведено уничтожение'),1)
  d=fixture('address');d['events'].pop();d['final_event']={'kind':'return'}
  with self.assertRaises(ValidationError):validate(d) # Старое поле не восстанавливает отдельный итог.
 def test_events_and_field_paths(self):
  d=fixture('address');d['events'][1]['fields']['phones'][0]['number']='701'
  with self.assertRaises(ValidationError) as err:validate(d)
  self.assertEqual(err.exception.path,'events.1.fields.phones.0.number')
  for mutate in [lambda d:d['events'][0].update(result='call_no_answer'),lambda d:d['events'][0].update(date='2027-01-01')]:
   d=fixture();mutate(d)
   with self.assertRaises(ValidationError):validate(d)
  d=fixture('redirect');self.assertTrue(validate(d)) # Никакого ручного согласования.
  d=fixture('complex');d['events'][2]['fields']['end']='2025-12-01'
  with self.assertRaises(ValidationError):validate(d)
 def test_phone_rules(self):
  for number in ('7011234567','77011234567','87011234567','+7 (701) 123-45-67'):
   self.assertEqual(normalize_phone({'country':'KZ','number':number})['number'],'+7-701-123-45-67')
  for number in ('701','770112345678','+7-701-123-45-67-8','7abcdef1234'):
   with self.assertRaises(ValueError):normalize_phone({'country':'KZ','number':number})
  self.assertEqual(normalize_phone({'country':'GB','number':'+44 20 7946 0000'})['number'],'+442079460000')
  with self.assertRaises(ValueError):normalize_phone({'country':'GB','number':'+44 20'})
  d=fixture('address');d['events'][1]['result']='wrong';self.assertTrue(validate(d))

if __name__=='__main__':unittest.main()
