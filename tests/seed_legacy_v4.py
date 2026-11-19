"""Только фикстура для отдельной браузерной базы, не для рабочей базы."""
import sys,json,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
db=Path(sys.argv[1]).resolve()
assert db.is_relative_to(ROOT/'artifacts/v4') and not db.exists()
sys.path.insert(0,str(ROOT/'backend'))
from domain import settings
branch=settings()['branches'][0]
doc={'schema_version':3,'customer':'Архивный заказчик теста','addressee':'Прежний отдельный адресат','recipient':'Тестового получателя','address':'г. Астана, тестовый адрес','waybill':'0000000000020','order_date':'2026-01-01','notification_date':'2026-01-15','outgoing_number':'20','final_event':{'kind':'return'},'events':[{'type':'visit','result':'closed','date':'2026-01-02','fields':{}}], 'rendered':{'intro_before':'СОХРАНЁННЫЙ ИСХОДНЫЙ ТЕКСТ ','intro_after':'.','paragraphs':['Архивный абзац без изменений.'],'branch':branch}}
con=sqlite3.connect(db)
try:
    con.execute('CREATE TABLE notifications(id INTEGER PRIMARY KEY,branch TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,payload TEXT NOT NULL)')
    con.execute('INSERT INTO notifications VALUES(1,?,?,?,?)',('astana','2026-01-15','2026-01-15',json.dumps(doc,ensure_ascii=False)))
    con.commit()
finally:con.close()
