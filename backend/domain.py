"""События, устойчивые ссылки на дополнительные контакты, тип из завершения."""
import json,re
from datetime import date
from pathlib import Path
from phones import normalize_phone
from domain_helpers import completion,resolve_catalog
ROOT=Path(__file__).resolve().parents[1]
class ValidationError(ValueError):
    def __init__(self,message,path=''):super().__init__(message);self.path=path
def catalog():return resolve_catalog(json.loads((ROOT/'backend/catalog.json').read_text(encoding='utf-8')))
def settings():
    local=ROOT/'backend/settings.json'
    return json.loads((local if local.exists() else ROOT/'backend/settings.example.json').read_text(encoding='utf-8'))
def text(value,label,path='',limit=1000):
    if not isinstance(value,str) or not value.strip():raise ValidationError(f'Заполните поле «{label}».',path)
    value=re.sub(r'"([^"\n]+)"',r'«\1»',' '.join(value.split()))
    if len(value)>limit:raise ValidationError(f'Поле «{label}»: максимум {limit} символов.',path)
    return value
def iso(value,label,path=''):
    try:
        if not isinstance(value,str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',value):raise ValueError()
        date.fromisoformat(value);return value
    except ValueError:raise ValidationError(f'Укажите корректную дату: {label}.',path) from None
def fmt(value):
    d=date.fromisoformat(value);months=('января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря')
    return f'{d.day} {months[d.month-1]} {d.year} года'
def identifier(value,path):
    if not isinstance(value,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',value):raise ValidationError('Некорректный идентификатор события или контакта.',path)
    return value
def phones(values,path,label,with_ids=False,event_id=''):
    if not isinstance(values,list) or not 1<=len(values)<=10:raise ValidationError(label+': введите номер телефона.',path+'.0.number')
    result=[];seen=set()
    for index,value in enumerate(values):
        try:p=normalize_phone(value if isinstance(value,dict) else {})
        except ValueError as exc:raise ValidationError(label+': '+str(exc),path+f'.{index}.'+('country' if 'страну' in str(exc) else 'number')) from None
        if with_ids:
            p['id']=identifier(value.get('id',f'{event_id}-p{index}'),path+f'.{index}.number')
            if p['id'] in seen:raise ValidationError(label+': повторяется идентификатор номера.',path+f'.{index}.number')
            seen.add(p['id'])
        result.append(p)
    return result
def validate(data):
    if not isinstance(data,dict):raise ValidationError('Проверьте данные уведомления.')
    doc={k:text(data.get(k),label,k) for k,label in [('customer','Заказчик'),('recipient','Получатель корреспонденции'),('address','Адрес доставки')]}
    number=data.get('waybill')
    if not isinstance(number,str) or not re.fullmatch(r'[0-9]{13}',number):raise ValidationError('Накладная должна содержать ровно 13 цифр. Номер не дополняется и не обрезается.','waybill')
    doc['waybill']=number
    for key,label in [('order_date','Дата заказа'),('notification_date','Дата уведомления')]:doc[key]=iso(data.get(key),label,key)
    if doc['order_date']>doc['notification_date']:raise ValidationError('Дата заказа позже даты уведомления.','order_date')
    incoming=data.get('events')
    if not isinstance(incoming,list) or len(incoming)>40:raise ValidationError('В истории допустимо до 40 событий.','events')
    endings=[(i,completion(e)) for i,e in enumerate(incoming) if isinstance(e,dict) and completion(e)]
    if len(endings)>1:
        names={'delivery':'доставка','return':'возврат','destruction':'уничтожение'}
        details=', '.join(f'событие {i+1} — {names[t]}' for i,t in endings)
        raise ValidationError('Указаны повторные или несовместимые завершения: '+details+'. Оставьте одно фактическое завершение.',f'events.{endings[1][0]}.type')
    if endings and endings[0][0]!=len(incoming)-1:raise ValidationError('Завершение должно быть последним событием истории. Проверьте события после него.',f'events.{endings[0][0]+1}.type')
    events=[];event_ids=set();sources={};previous=doc['order_date'];current_address=doc['address'];unresolved=False;storage=None;no_phone=False;invoice_contact=False
    types=catalog()['types']
    for i,raw in enumerate(incoming):
        p=f'events.{i}';label=f'Событие {i+1}'
        if not isinstance(raw,dict):raise ValidationError(label+': проверьте данные.',p+'.type')
        typ=raw.get('type')
        if typ not in types or typ=='other':raise ValidationError(label+': нет подходящей ситуации. Согласуйте формулировку.',p+'.type')
        if raw.get('needs_review'):raise ValidationError(label+': '+raw.get('review_message','Уточните прежние сведения и выберите ситуацию заново.'),p+'.type')
        spec=types[typ];result=spec.get('single_result') or raw.get('result')
        if result not in spec['results']:raise ValidationError(label+': выберите результат.',p+'.result')
        event={'id':identifier(raw.get('id',f'event-{i}'),p+'.type'),'type':typ,'result':result,'fields':{}}
        if event['id'] in event_ids:raise ValidationError(label+': повторяется идентификатор события.',p+'.type')
        event_ids.add(event['id'])
        if spec.get('date_required',True):
            event['date']=iso(raw.get('date'),label,p+'.date')
            if not previous<=event['date']<=doc['notification_date']:raise ValidationError(label+': дата должна идти по порядку от заказа до уведомления.',p+'.date')
            previous=event['date']
        fields=raw.get('fields',{})
        if not isinstance(fields,dict):raise ValidationError(label+': проверьте сведения.',p+'.result')
        ref=raw.get('contact_ref') if typ=='contact' and result!='no_phone' else None
        for f in spec['results'][result]['fields']:
            key=f['key'];fp=p+'.fields.'+key;value=fields.get(key)
            if f.get('optional'):
                enabled=fields.get(f['enabled_by']) is True
                event['fields'][f['enabled_by']]=enabled
                if not enabled:continue
            if f['type']=='phones' and key=='phones' and typ=='contact' and ref is not None:
                if not isinstance(ref,dict) or ref.get('event_id') not in sources:raise ValidationError(label+': событие с новыми контактами удалено, расположено позже или больше не содержит контактов. Выберите источник заново.',p+'.contact_ref')
                source=sources[ref['event_id']];ids=ref.get('phone_ids')
                available={v['id']:v for v in source['fields']['new_phones']}
                if not isinstance(ids,list) or not ids or any(not isinstance(k,str) or k not in available for k in ids) or len(ids)!=len(set(ids)):raise ValidationError(label+': выберите использованные номера из события отправителя.',p+'.contact_ref')
                selected=[available[k] for k in ids]
                snapshot=phones(value,fp,label)
                if [(v['country'],v['number']) for v in snapshot]!=[(v['country'],v['number']) for v in selected]:raise ValidationError(label+': номера источника изменились. Проверьте и обновите выбранные номера явно.',p+'.contact_ref')
                event['fields'][key]=snapshot
                event['contact_ref']={'event_id':ref['event_id'],'phone_ids':ids}
            elif f['type']=='phones':
                event['fields'][key]=phones(value,fp,label,key=='new_phones',event['id'])
                if typ=='contact':invoice_contact=True
            elif f['type']=='date':event['fields'][key]=iso(value,label+': '+f['label'],fp)
            elif f['type']=='checkbox':
                if value is not True:raise ValidationError('Подтвердите: '+f['label']+'.',fp)
                event['fields'][key]=True
            elif f['type']=='select':
                if value not in f['options']:raise ValidationError(label+': выберите '+f['label']+'.',fp)
                event['fields'][key]=value
            else:event['fields'][key]=text(value,label+': '+f['label'],fp)
        f=event['fields']
        if typ=='sender' and result=='new_contacts':sources[event['id']]=event
        if typ=='contact' and result=='no_phone':no_phone=True
        if typ=='redirect':current_address=f['new_address'];unresolved=False
        if typ=='address':unresolved=True
        if typ in ('visit','delivered','mailbox'):
            if unresolved:raise ValidationError(label+': перед визитом уточните адрес в событии переадресации.',p+'.type')
            event['actual_address']=current_address
        if typ=='contact' and result=='later' and f['requested_date']<event['date']:raise ValidationError(label+': запрошенная дата раньше разговора.',p+'.fields.requested_date')
        if typ=='storage':
            start,end=f['start'],f['end']
            if not doc['order_date']<=start<=end<=doc['notification_date'] or event['date']>start:raise ValidationError(label+': проверьте период хранения.',p+'.fields.end')
            storage=(start,end)
        if typ=='uncollected' and (not storage or event['date']<storage[1]):raise ValidationError(label+': сначала укажите завершившийся период хранения.',p+'.date')
        if completion(event)=='delivery' and storage and event['date']<storage[1]:raise ValidationError(label+': вручение раньше окончания хранения.',p+'.date')
        events.append(event)
    if no_phone and invoice_contact:raise ValidationError('Указаны отсутствие телефона в накладной и связь по исходному номеру. Уточните событие или свяжите его с новыми контактами отправителя.','events')
    if not endings:raise ValidationError('Добавьте завершающее событие: «Вручение», «Доставка в почтовый ящик», «Возврат» или «Уничтожение».','events')
    doc.update(events=events,kind=endings[0][1],schema_version=4)
    return doc
def render(doc,branch):
    specs=catalog()['types'];paragraphs=[];previous_date=None;visited=set()
    for event in doc['events']:
        values=dict(event['fields'])
        for key,value in list(values.items()):
            if isinstance(value,list):values[key]=', '.join(v['number'] for v in value)
            elif re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',str(value)):values[key]=fmt(value)
        values.update(date=fmt(event['date']) if event.get('date') else '',actual_address=event.get('actual_address',''))
        if event['type']=='visit':
            addr=event['actual_address'];repeat='повторно ' if addr in visited else ''
            values['visit_location']=f'курьер {repeat}был по адресу, указанному в накладной' if addr==doc['address'] else f'курьер {repeat}был по новому адресу: {addr}'
            visited.add(addr)
        if event['type']=='contact' and event['result']!='no_phone':
            many=len(event['fields']['phones'])>1
            origin=('предоставленным отправителем' if many else 'предоставленному отправителем') if event.get('contact_ref') else ('указанным в накладной' if many else 'указанному в накладной')
            values['phone_prefix']=('по номерам телефонов ' if many else 'по номеру телефона ')+values['phones']+', '+origin+','
        phrase=specs[event['type']]['results'][event['result']]['phrase'].format(**values)
        if event['type']=='sender':
            if event['result']=='new_contacts' and event['fields'].get('has_address'):phrase+=' Отправитель также сообщил новый адрес: '+event['fields']['new_address']+'.'
            if event['fields'].get('has_sender_phone'):phrase+=' Связь с отправителем осуществлялась по номеру(ам): '+values['sender_phones']+'.'
        if previous_date==event.get('date') and event.get('date') and event['type'] in ('contact','redirect') and paragraphs:
            prefix=fmt(event['date'])+' '
            if phrase.startswith(prefix):phrase=phrase[len(prefix):]
            paragraphs[-1]+=' '+phrase[0].upper()+phrase[1:]
        else:paragraphs.append(phrase)
        previous_date=event.get('date')
    return {'intro_before':f'{branch["legal_name"]} уведомляет о результатах работы с корреспонденцией ','intro_after':f' от {fmt(doc["order_date"])}, адресованной в {doc["address"]} для {doc["recipient"]}.','paragraphs':paragraphs,'branch':branch,'template_version':'astana-v4'}
