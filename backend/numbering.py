"""Неизменяемый журнал выдачи и монотонные счётчики филиал/год."""
import json
import re
from domain import ValidationError
MAX_NUMBER=999_999_999

def migrate(con):
    columns={r['name'] for r in con.execute('PRAGMA table_info(notifications)')}
    for name,definition in [('number_year','INTEGER'),('number_value','INTEGER'),('input_hash','TEXT')]:
        if name not in columns:con.execute(f'ALTER TABLE notifications ADD COLUMN {name} {definition}')
    con.execute('CREATE TABLE IF NOT EXISTS outgoing_counters(branch TEXT NOT NULL,year INTEGER NOT NULL,last_used INTEGER NOT NULL,PRIMARY KEY(branch,year))')
    con.execute('CREATE TABLE IF NOT EXISTS issued_numbers(branch TEXT NOT NULL,year INTEGER NOT NULL,number INTEGER NOT NULL,notification_id INTEGER,origin TEXT NOT NULL,PRIMARY KEY(branch,year,number))')
    con.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY)')
    if con.execute('SELECT 1 FROM schema_migrations WHERE version=3').fetchone():return
    for row in con.execute('SELECT id,branch,payload FROM notifications').fetchall():
        data=json.loads(row['payload']);raw_number=str(data.get('outgoing_number','')).strip();d=data.get('notification_date','')
        match=re.fullmatch(r'(?:Исх\.\s*)?№?\s*([0-9]+)',raw_number,re.IGNORECASE)
        if not match or not re.match(r'^[0-9]{4}-',d):continue
        number=int(match[1]);year=int(d[:4])
        if not 1<=number<=MAX_NUMBER:continue
        con.execute('INSERT OR IGNORE INTO issued_numbers VALUES(?,?,?,?,?)',(row['branch'],year,number,row['id'],'archive'))
        con.execute('INSERT INTO outgoing_counters VALUES(?,?,?) ON CONFLICT(branch,year) DO UPDATE SET last_used=MAX(last_used,excluded.last_used)',(row['branch'],year,number))
        con.execute('UPDATE notifications SET number_year=?,number_value=? WHERE id=?',(year,number,row['id']))
    con.execute('INSERT INTO schema_migrations VALUES(3)')

def counter(con,branch,year):
    if type(year) is not int or not 1<=year<=9999:raise ValidationError('Укажите календарный год.','notification_date')
    row=con.execute('SELECT last_used FROM outgoing_counters WHERE branch=? AND year=?',(branch,year)).fetchone()
    last=row['last_used'] if row else 0
    return {'branch':branch,'year':year,'last_used':last,'next_number':last+1}

def set_counter(con,branch,year,last):
    state=counter(con,branch,year)
    if type(last) is not int or not 0<=last<MAX_NUMBER:raise ValidationError('Последний номер должен быть целым числом от 0 до 999999998.','counter.last_used')
    if last<state['last_used']:raise ValidationError(f'Нельзя уменьшить счётчик ниже {state["last_used"]}: номера уже использованы или зарезервированы.','counter.last_used')
    highest=con.execute('SELECT MAX(number) FROM issued_numbers WHERE branch=? AND year=?',(branch,year)).fetchone()[0] or 0
    if last<highest:raise ValidationError('Такое значение пересекается с уже выданными номерами.','counter.last_used')
    con.execute('INSERT INTO outgoing_counters VALUES(?,?,?) ON CONFLICT(branch,year) DO UPDATE SET last_used=excluded.last_used',(branch,year,last))
    return counter(con,branch,year)

def issue(con,branch,year):
    number=counter(con,branch,year)['next_number']
    if number>MAX_NUMBER:raise ValidationError('Счётчик исходящих номеров исчерпан.','counter.last_used')
    con.execute('INSERT INTO issued_numbers VALUES(?,?,?,?,?)',(branch,year,number,None,'issued'))
    con.execute('INSERT INTO outgoing_counters VALUES(?,?,?) ON CONFLICT(branch,year) DO UPDATE SET last_used=excluded.last_used',(branch,year,number))
    return number
