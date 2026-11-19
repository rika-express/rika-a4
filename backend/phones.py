"""Те же локальные правила формата, что использует интерфейс. Не проверка существования."""
import json
import re
from pathlib import Path
RULES=json.loads((Path(__file__).parent/'phone-rules.json').read_text(encoding='utf-8'))

def normalize_phone(value):
    country=str(value.get('country','')).upper()
    rule=RULES['countries'].get(country)
    if rule is None:raise ValueError('Выберите страну телефона.')
    raw=value.get('number','')
    if not isinstance(raw,str) or not raw.strip():raise ValueError('Введите номер телефона.')
    if not re.fullmatch(r'\+?[0-9 ()-]+',raw.strip()):raise ValueError('В телефоне допустимы цифры, +, пробелы, скобки и дефисы.')
    digits=re.sub(r'[^0-9]','',raw)
    if country=='KZ':
        if len(digits)==11 and digits[0] in '78':digits=digits[1:]
        if len(digits)!=10:raise ValueError('Телефон Казахстана: нужно 10 цифр номера или 11 с начальной 7/8; номер не обрезается.')
        national=digits
    else:
        if not raw.strip().startswith('+'+rule['code']):raise ValueError('Укажите телефон с кодом +'+rule['code']+'.')
        national=digits[len(rule['code']):]
    if len(national) not in rule['lengths'] or not re.fullmatch(rule['pattern'],national):
        raise ValueError('Неверная структура или длина телефона для страны «'+rule['name']+'».')
    number=f'+7-{national[:3]}-{national[3:6]}-{national[6:8]}-{national[8:]}' if country=='KZ' else '+'+rule['code']+national
    return {'country':country,'number':number}
