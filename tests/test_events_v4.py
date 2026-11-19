import json,sys,unittest
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from domain import validate,render,settings,ValidationError
from compatibility import to_events
def base(events):return {'customer':'Заказчик','recipient':'Получателя','address':'г. Астана, ул. Примерная, 1','waybill':'0000000000001','order_date':'2026-01-01','notification_date':'2026-01-15','events':events}
def provided(address=False):
    return {'id':'sender1','type':'sender','result':'new_contacts','date':'2026-01-02','fields':{'new_phones':[{'id':'phone1','country':'KZ','number':'+7-701-123-45-67'}],'has_address':address,'new_address':'г. Астана, ул. Новая, 2' if address else ''}}
def linked(result='call_no_answer',extra=None):
    return {'id':'contact1','type':'contact','result':result,'date':'2026-01-03','fields':{'phones':[{'country':'KZ','number':'+7-701-123-45-67'}],**(extra or {})},'contact_ref':{'event_id':'sender1','phone_ids':['phone1']}}
def close(typ='return'):return {'id':'end1','type':typ,'fields':{}}
class EventsTests(unittest.TestCase):
 def text(self,doc):return ' '.join(render(validate(doc),settings()['branches'][0])['paragraphs'])
 def test_a_delivery_without_final(self):
    d=base([{'type':'delivered','result':'signed','date':'2026-01-03','fields':{'signed_by':'Иванов И. И.'}}]);v=validate(d)
    self.assertEqual(v['kind'],'delivery');self.assertNotIn('final_event',v);self.assertEqual(self.text(d).count('корреспонденция вручена'),1)
 def test_b_visit_phone_return_without_date(self):
    d=base([{'type':'visit','result':'closed','date':'2026-01-02','fields':{}},{'type':'contact','result':'call_no_answer','date':'2026-01-03','fields':{'phones':[{'country':'KZ','number':'7011234567'}]}},close()])
    v=validate(d);self.assertNotIn('date',v['events'][-1]);self.assertEqual(v['kind'],'return');self.assertEqual(self.text(d).count('произведен возврат'),1)
 def test_c_new_contacts_call_destruction(self):
    d=base([provided(),linked(),close('destruction')]);t=self.text(d)
    self.assertIn('предоставленному отправителем',t);self.assertNotIn('указанному в накладной',t);self.assertEqual(t.count('произведено уничтожение'),1)
    receipt_only=self.text(base([provided(),close()]))
    self.assertNotIn('связаться',receipt_only);self.assertNotIn('на звонки',receipt_only)
 def test_d_new_address_redirect_visit_delivered(self):
    events=[provided(),linked('new_address',{'new_address':'г. Астана, ул. Новая, 2'}),{'id':'redirect1','type':'redirect','result':'approved','date':'2026-01-04','fields':{'new_address':'г. Астана, ул. Новая, 2'}},{'id':'visit1','type':'visit','result':'absent','date':'2026-01-05','fields':{}},{'id':'delivered1','type':'delivered','result':'signed','date':'2026-01-06','fields':{'signed_by':'Иванова И. И.'}}]
    v=validate(base(events));self.assertEqual(v['kind'],'delivery');self.assertEqual(v['events'][-1]['actual_address'],'г. Астана, ул. Новая, 2')
 def test_e_simultaneous_address_phone_and_optional_sender_number(self):
    e=provided(True);d=base([e,linked(),close()]);v=validate(d);self.assertTrue(v['events'][0]['fields']['has_address']);self.assertNotIn('sender_phones',v['events'][0]['fields']);self.assertIn('также сообщил новый адрес',self.text(d))
    e['fields'].update(has_sender_phone=True,sender_phones=[{'country':'KZ','number':'7071234567'}]);self.assertIn('Связь с отправителем осуществлялась',self.text(d))
 def test_links_and_snapshots_fail_loudly(self):
    for events in ([linked(),close()],[linked(),provided(),close()]):
        with self.assertRaises(ValidationError) as err:validate(base(events))
        self.assertEqual(err.exception.path,'events.0.contact_ref')
    d=base([provided(),linked(),close()]);d['events'][0]['fields']['new_phones'][0]['number']='7021234567'
    with self.assertRaises(ValidationError) as err:validate(d)
    self.assertEqual(err.exception.path,'events.1.contact_ref')
    d=base([provided(),linked(),close()]);d['events'][1]['contact_ref']['phone_ids']=['missing']
    with self.assertRaises(ValidationError):validate(d)
 def test_missing_or_conflicting_ending(self):
    for events in ([provided()],[close(),close('destruction')],[{'id':'delivered1','type':'delivered','result':'signed','date':'2026-01-03','fields':{'signed_by':'И. И.'}},close()]):
        with self.assertRaises(ValidationError):validate(base(events))
 def test_conversion_and_copy_preserve_graph_without_duplication(self):
    old=base([{'type':'delivered','result':'signed','date':'2026-01-03','fields':{'signed_by':'И. И.'}}]);old['final_event']={'kind':'delivery'}
    self.assertEqual(len(to_events(old)['events']),1)
    old=base([close()]);old['final_event']={'kind':'return'};self.assertEqual(len(to_events(old)['events']),1)
    old=base([]);old['final_event']={'kind':'return'};converted=to_events(old);self.assertEqual(converted['events'][0]['type'],'return');self.assertNotIn('final_event',converted);self.assertNotIn('final_event',validate(converted))
    d=base([provided(),linked(),close()]);v=validate(d);copy=deepcopy(v);copy['notification_date']='2026-02-01';self.assertEqual(validate(copy)['events'][1]['contact_ref'],v['events'][1]['contact_ref'])
 def test_no_invoice_phone_can_have_sender_additional_phone(self):
    d=base([{'id':'none','type':'contact','result':'no_phone','date':'2026-01-02','fields':{}},provided(),linked(),close()]);self.assertEqual(validate(d)['kind'],'return')

if __name__=='__main__':unittest.main()
