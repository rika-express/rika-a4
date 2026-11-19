"""Преобразование только по явному действию; архивный payload не изменяется."""
from copy import deepcopy
import uuid
from domain_helpers import TERMINALS

def uid():return str(uuid.uuid4())

def to_events(data):
    doc=deepcopy(data)
    events=doc.get('events',[])
    for event in events:
        event.setdefault('id',uid())
        event.pop('_key',None)
        fields=event.setdefault('fields',{})
        if event.get('type') in ('call','message'):
            event['result']='call_no_answer' if event['type']=='call' and event.get('result')=='no_answer' else 'message_no_answer' if event.get('result')=='no_answer' else ''
            event['type']='contact'
        if event.get('type')=='sender':
            if event.get('result')=='new_phones':event['result']='new_contacts'
            if fields.get('phones'):
                fields['sender_phones']=fields.pop('phones');fields['has_sender_phone']=True
        for key,value in fields.items():
            if isinstance(value,list):
                for p in value:
                    if not isinstance(p,dict):continue
                    p['country']='KZ' if p.get('country','').upper()=='KZ' else '' if p.get('country')=='foreign' else p.get('country','')
                    if key=='new_phones':p.setdefault('id',uid())
        if fields.get('source') not in (None,'накладной'):
            # Старая отметка не превращается молча в происхождение из накладной.
            event['needs_review']=True
            event['review_message']='В прежней записи указан иной источник номера. Свяжите событие с предоставленными контактами или явно уточните исходные номера.'
    previous=doc.get('final_event',{}).get('kind') or doc.get('kind')
    if previous and not any(TERMINALS.get(e.get('type'))==previous for e in events):
        typ={'delivery':'delivered','return':'return','destruction':'destruction'}.get(previous)
        if typ:
            event={'id':uid(),'type':typ,'result':'completed' if typ in ('return','destruction') else '', 'fields':{}}
            if typ=='delivered':event['date']=''
            if doc.get('outcome_state')=='planned':
                event['needs_review']=True;event['review_message']='Прежний итог был планируемым. Уточните фактически выполненное событие.'
            events.append(event)
    doc['events']=events
    doc['order_date']=doc.get('order_date') or doc.get('waybill_date','')
    doc['schema_version']=4
    for key in ('final_event','outcome_date','outcome_state','outcome_approved','rendered'):
        doc.pop(key,None)
    return doc
