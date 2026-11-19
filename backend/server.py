"""Локальное приложение. Стандартная библиотека; без авторизации."""
import json
import mimetypes
import os
import sqlite3
import socket
import sys
from datetime import datetime
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from domain import validate, render, settings, catalog, ValidationError
from phones import RULES
import numbering
import hashlib
from compatibility import to_events
DB = Path(os.environ.get('RIKA_DB', str(ROOT / 'data/notifications.sqlite3'))).resolve()
if not DB.is_relative_to(ROOT):
    raise RuntimeError('База должна находиться внутри проекта.')


@contextmanager
def connect():
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        with con:
            yield con
    finally:
        con.close()


def initialize():
    DB.parent.mkdir(exist_ok=True, parents=True)
    with connect() as con:
        con.execute('CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY, branch TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, payload TEXT NOT NULL)')
        cols = {row['name'] for row in con.execute('PRAGMA table_info(notifications)')}
        for name, definition in [('request_key','TEXT'),('revision','INTEGER NOT NULL DEFAULT 1'),('status',"TEXT NOT NULL DEFAULT 'legacy'")]:
            if name not in cols: con.execute(f'ALTER TABLE notifications ADD COLUMN {name} {definition}')
        con.execute('CREATE UNIQUE INDEX IF NOT EXISTS notification_request_key ON notifications(request_key) WHERE request_key IS NOT NULL')
        numbering.migrate(con)
        con.execute("CREATE TABLE IF NOT EXISTS notification_versions(notification_id INTEGER NOT NULL,revision INTEGER NOT NULL,created_at TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(notification_id,revision))")


def branch_by_id(ident):
    return next((b for b in settings()['branches'] if b['branch_id']==ident), None)


def row_to_item(row):
    item = dict(row)
    item['document'] = json.loads(item.pop('payload'))
    return item


class Handler(BaseHTTPRequestHandler):
    def reply(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = urlparse(self.path)
        query = parse_qs(route.query)
        branch = query.get('branch', [settings()['default_branch']])[0]
        if route.path == '/api/settings': return self.reply(settings())
        if route.path == '/api/phone-rules': return self.reply(RULES)
        if route.path == '/api/counter':
            try:
                if branch_by_id(branch) is None: raise ValidationError('Неизвестный филиал.')
                year=int(query.get('year',[str(datetime.now().year)])[0])
                with connect() as con: value=numbering.counter(con,branch,year)
                return self.reply(value)
            except ValueError as exc: return self.reply({'error':str(exc),'field':getattr(exc,'path','notification_date')},400)
        if route.path == '/api/catalog': return self.reply(catalog())
        if route.path == '/api/notifications':
            if branch_by_id(branch) is None: return self.reply({'error':'Неизвестный филиал.'},400)
            with connect() as con:
                rows = con.execute('SELECT * FROM notifications WHERE branch=? ORDER BY id DESC',(branch,)).fetchall()
            result=[]
            for row in rows:
                item=row_to_item(row)
                doc=item['document']
                def q(key): return query.get(key,[''])[0].strip().casefold()
                if q('customer') not in doc.get('customer','').casefold() or q('waybill') not in doc.get('waybill','').casefold(): continue
                day=item['created_at'][:10]
                if (q('from') and day<q('from')) or (q('to') and day>q('to')): continue
                result.append(item)
            return self.reply(result)
        if route.path.startswith('/api/notifications/') and route.path.endswith('/versions'):
            try: ident=int(route.path.split('/')[-2])
            except ValueError: return self.reply({'error':'Запись не найдена.'},404)
            with connect() as con:
                parent=con.execute('SELECT id FROM notifications WHERE id=? AND branch=?',(ident,branch)).fetchone()
                if not parent:return self.reply({'error':'Запись не найдена.'},404)
                rows=con.execute('SELECT * FROM notification_versions WHERE notification_id=? ORDER BY revision DESC',(ident,)).fetchall()
            return self.reply([{'revision':row['revision'],'created_at':row['created_at'],'document':json.loads(row['payload'])} for row in rows])
        if route.path.startswith('/api/notifications/'):
            try: ident=int(route.path.rsplit('/',1)[1])
            except ValueError: return self.reply({'error':'Запись не найдена.'},404)
            with connect() as con:
                row=con.execute('SELECT * FROM notifications WHERE id=? AND branch=?',(ident,branch)).fetchone()
            return self.reply(row_to_item(row)) if row else self.reply({'error':'Запись не найдена.'},404)
        assets={'/':ROOT/'frontend/index.html','/app.js':ROOT/'frontend/app.js','/components.js':ROOT/'frontend/components.js','/styles.css':ROOT/'frontend/styles.css','/vue.js':ROOT/'node_modules/vue/dist/vue.global.prod.js','/assets/astana-header.png':ROOT/'frontend/assets/astana-header.png'}
        assets['/assets/demo-header.svg']=ROOT/'frontend/assets/demo-header.svg'
        path=assets.get(route.path)
        if path is None or not path.is_file(): return self.reply({'error':'Файл не найден.'},404)
        body=path.read_bytes()
        self.send_response(200)
        mime=mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
        self.send_header('Content-Type',mime+('; charset=utf-8' if mime.startswith('text/') or 'javascript' in mime else ''))
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-cache')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        route=urlparse(self.path).path
        if route not in ('/api/preview','/api/notifications','/api/counter','/api/convert'): return self.reply({'error':'Неизвестный адрес.'},404)
        if self.headers.get('Origin') not in (None,'http://'+self.headers.get('Host','')): return self.reply({'error':'Недопустимый источник запроса.'},403)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=150_000: return self.reply({'error':'Слишком большой документ.'},413)
            body=json.loads(self.rfile.read(length))
            branch=branch_by_id(body.get('branch'))
            if branch is None: raise ValidationError('Неизвестный филиал.')
            if route=='/api/counter':
                with connect() as con:
                    con.execute('BEGIN IMMEDIATE')
                    value=numbering.set_counter(con,branch['branch_id'],body.get('year'),body.get('last_used'))
                return self.reply(value)
            if route=='/api/convert':
                if not isinstance(body.get('document'),dict):raise ValidationError('Проверьте данные архивного документа.')
                return self.reply({'document':to_events(body['document'])})
            if not branch.get('can_issue'): raise ValidationError('Для этого филиала нет согласованного бланка. Выберите Астану для новой формы или копии.')
            doc=validate(body.get('document'))
            fingerprint=hashlib.sha256(json.dumps(doc,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            year=int(doc['notification_date'][:4]);ident=body.get('id')
            key=body.get('request_key')
            if route=='/api/notifications':
                import re
                if not isinstance(key,str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,80}',key): raise ValidationError('Обновите форму: отсутствует ключ сохранения.')
            with connect() as con:
                if route=='/api/notifications':con.execute('BEGIN IMMEDIATE')
                old=None
                if ident is not None:
                    old=con.execute('SELECT * FROM notifications WHERE id=? AND branch=?',(int(ident),branch['branch_id'])).fetchone()
                    if not old:return self.reply({'error':'Запись не найдена.'},404)
                    olddoc=json.loads(old['payload'])
                    if olddoc.get('schema_version')!=4 and not body.get('edit_legacy'):return self.reply({'error':'Откройте архивную запись для явного редактирования либо создайте копию.'},409)
                    if old['number_value'] is None:raise ValidationError('В прежней записи не выдан исходящий номер. Создайте копию для нового уведомления.')
                    if year!=old['number_year']:raise ValidationError('Год выданного уведомления менять нельзя. Создайте копию для другого года.','notification_date')
                    if route=='/api/notifications' and body.get('revision')!=old['revision']:
                        if old['input_hash']==fingerprint:return self.reply(row_to_item(old))
                        return self.reply({'error':'Запись уже изменена. Откройте её из архива повторно.'},409)
                    number=old['number_value']
                else:
                    if route=='/api/notifications':
                        repeated=con.execute('SELECT * FROM notifications WHERE request_key=?',(key,)).fetchone()
                        if repeated:
                            if repeated['branch']!=branch['branch_id'] or repeated['input_hash']!=fingerprint:return self.reply({'error':'Повторный ключ использован с другими данными. Откройте сохранённую запись.'},409)
                            return self.reply(row_to_item(repeated))
                    number=numbering.counter(con,branch['branch_id'],year)['next_number'] if route=='/api/preview' else numbering.issue(con,branch['branch_id'],year)
                doc['outgoing_number']=str(number)
                doc['addressee']=doc['customer']
                doc['rendered']=render(doc,branch)
                if route=='/api/preview':return self.reply({'document':doc,'number_provisional':old is None})
                now=datetime.now().astimezone().isoformat(timespec='seconds')
                if old is None:
                    cur=con.execute("INSERT INTO notifications(branch,created_at,updated_at,payload,request_key,status,number_year,number_value,input_hash) VALUES(?,?,?,?,?,'ready',?,?,?)",(branch['branch_id'],now,now,json.dumps(doc,ensure_ascii=False),key,year,number,fingerprint))
                    ident=cur.lastrowid
                    con.execute('UPDATE issued_numbers SET notification_id=? WHERE branch=? AND year=? AND number=?',(ident,branch['branch_id'],year,number))
                elif old['input_hash']!=fingerprint:
                    con.execute('INSERT OR IGNORE INTO notification_versions VALUES(?,?,?,?)',(old['id'],old['revision'],old['updated_at'],old['payload']))
                    con.execute('UPDATE notifications SET payload=?,input_hash=?,updated_at=?,revision=revision+1 WHERE id=?',(json.dumps(doc,ensure_ascii=False),fingerprint,now,int(ident)))
                row=con.execute('SELECT * FROM notifications WHERE id=?',(int(ident),)).fetchone()
            return self.reply(row_to_item(row))
        except (ValueError,TypeError,AttributeError,KeyError) as exc:
            return self.reply({'error':str(exc) or 'Проверьте данные.','field':getattr(exc,'path','')},400)


class LocalServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


if __name__=='__main__':
    initialize()
    port=int(os.environ.get('RIKA_PORT','8000'))
    try:
        http = LocalServer(('127.0.0.1',port),Handler)
    except OSError as exc:
        print(f'Не удалось занять локальный порт {port}: {exc}', file=sys.stderr)
        sys.exit(1)
    print(f'RIKA-A4: http://127.0.0.1:{port}',flush=True)
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        http.server_close()
