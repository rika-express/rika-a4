/* Static demo only. No Python, network API, account access or shared archive. */
const Demo = (() => {
 const KEY='rika-a4-static-demo-v1',copy=x=>JSON.parse(JSON.stringify(x));
 const config=Promise.all(['settings.json','catalog.json','phone-rules.json'].map(async p=>{const r=await fetch('./'+p);if(!r.ok)throw Error('Не удалось загрузить настройки демонстрации.');return r.json();}));
 const terminal={delivered:'delivery',mailbox:'delivery',return:'return',destruction:'destruction'};
 function fail(message,field){const e=Error(message);e.field=field;throw e;}
 function read(){try{const raw=localStorage.getItem(KEY);const s=raw?JSON.parse(raw):{records:[],counters:{},nextId:1};if(!Array.isArray(s.records)||!s.counters||!Number.isSafeInteger(s.nextId))throw Error();return s;}catch{throw Error('Демонстрационный архив браузера недоступен или повреждён. Данные не перезаписаны. Разрешите localStorage.');}}
 function write(s){try{localStorage.setItem(KEY,JSON.stringify(s));}catch{throw Error('Браузер не сохранил архив: проверьте разрешения и свободное место.');}}
 function text(v,path){if(typeof v!=='string'||!v.trim())fail('Заполните обязательное поле.',path);if(v.length>1000)fail('Максимум 1000 символов.',path);return v.trim().replace(/\s+/g,' ').replace(/"([^"\n]+)"/g,'«$1»');}
 function iso(v,path){if(typeof v!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(v)||!Number.isFinite(Date.parse(v+'T12:00:00Z'))||new Date(v+'T12:00:00Z').toISOString().slice(0,10)!==v)fail('Укажите корректную дату.',path);return v;}
 function fmt(v){const [y,m,d]=v.split('-');return `${+d} ${['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'][+m-1]} ${y} года`;}
 function phones(v,path,rules,ids=false){if(!Array.isArray(v)||!v.length||v.length>10)fail('Введите номер телефона.',path+'.0.number');const seen=new Set();return v.map((p,i)=>{const error=phoneCheck(p,rules);if(error)fail(error,path+'.'+i+'.number');let digits=p.number.replace(/\D/g,'');if(p.country==='KZ'){if(digits.length===11)digits=digits.slice(1);digits='+7-'+digits.slice(0,3)+'-'+digits.slice(3,6)+'-'+digits.slice(6,8)+'-'+digits.slice(8);}else digits='+'+digits;const result={country:p.country.toUpperCase(),number:digits};if(ids){if(!p.id||seen.has(p.id))fail('Проверьте идентификаторы контактов.',path+'.'+i+'.number');seen.add(p.id);result.id=p.id;}return result;});}
 function validate(input,catalog,rules){
  const doc={};for(const k of ['customer','recipient','address'])doc[k]=text(input[k],k);
  if(typeof input.waybill!=='string'||!/^\d{13}$/.test(input.waybill))fail('Накладная должна содержать ровно 13 цифр.','waybill');doc.waybill=input.waybill;
  for(const k of ['order_date','notification_date'])doc[k]=iso(input[k],k);
  if(doc.order_date>doc.notification_date)fail('Дата заказа позже уведомления.','order_date');
  if(!Array.isArray(input.events)||input.events.length>40)fail('Допустимо до 40 событий.','events');
  const endings=input.events.map((e,i)=>({e,i})).filter(({e})=>terminal[e.type]);
  if(!endings.length)fail('Добавьте вручение, доставку в ящик, возврат или уничтожение.','events');
  if(endings.length>1)fail('Повторные или несовместимые завершения. Оставьте одно.','events.'+endings[1].i+'.type');
  if(endings[0].i!==input.events.length-1)fail('Завершение должно быть последним событием.','events.'+(endings[0].i+1)+'.type');
  let previous=doc.order_date,address=doc.address,unresolved=false,storage=null,noPhone=false,invoice=false;const sources={},seen=new Set();
  doc.events=input.events.map((raw,i)=>{
   const p='events.'+i,spec=catalog.types[raw.type],result=spec?.single_result||raw.result;
   if(!spec||raw.type==='other'||raw.needs_review)fail('Выберите подходящую стандартную ситуацию.',p+'.type');
   if(!spec.results[result])fail('Выберите результат.',p+'.result');
   if(!raw.id||seen.has(raw.id))fail('Повторяется идентификатор события.',p+'.type');seen.add(raw.id);
   const e={id:raw.id,type:raw.type,result,fields:{}},fields=raw.fields||{};
   if(spec.date_required!==false){e.date=iso(raw.date,p+'.date');if(e.date<previous||e.date>doc.notification_date)fail('Дата должна идти по порядку от заказа до уведомления.',p+'.date');previous=e.date;}
   const ref=e.type==='contact'&&result!=='no_phone'?raw.contact_ref:null;
   for(const f of spec.results[result].fields){const fp=p+'.fields.'+f.key,v=fields[f.key];
    if(f.optional){e.fields[f.enabled_by]=fields[f.enabled_by]===true;if(!e.fields[f.enabled_by])continue;}
    if(f.type==='phones'){
     e.fields[f.key]=phones(v,fp,rules,f.key==='new_phones');
     if(e.type==='contact'&&f.key==='phones'){
      if(ref){const source=sources[ref.event_id],ids=ref.phone_ids;if(!source||!Array.isArray(ids)||!ids.length||new Set(ids).size!==ids.length)fail('Уточните событие-источник новых контактов.',p+'.contact_ref');const selected=ids.map(id=>source.fields.new_phones.find(x=>x.id===id));if(selected.some(x=>!x)||JSON.stringify(selected.map(x=>[x.country,x.number]))!==JSON.stringify(e.fields.phones.map(x=>[x.country,x.number])))fail('Контакты источника изменены. Уточните выбранные номера.',p+'.contact_ref');e.contact_ref=copy(ref);}
      else invoice=true;
     }
    }else if(f.type==='date')e.fields[f.key]=iso(v,fp);
    else if(f.type==='checkbox'){if(v!==true)fail('Подтвердите: '+f.label,fp);e.fields[f.key]=true;}
    else if(f.type==='select'){if(!Object.hasOwn(f.options,v))fail('Выберите '+f.label,fp);e.fields[f.key]=v;}
    else e.fields[f.key]=text(v,fp);
   }
   const f=e.fields;
   if(e.type==='sender'&&result==='new_contacts')sources[e.id]=e;
   if(e.type==='contact'&&result==='no_phone')noPhone=true;
   if(e.type==='redirect'){address=f.new_address;unresolved=false;}
   if(e.type==='address')unresolved=true;
   if(['visit','delivered','mailbox'].includes(e.type)){if(unresolved)fail('Сначала уточните адрес в событии переадресации.',p+'.type');e.actual_address=address;}
   if(e.type==='contact'&&result==='later'&&f.requested_date<e.date)fail('Запрошенная дата раньше разговора.',p+'.fields.requested_date');
   if(e.type==='storage'){if(!(doc.order_date<=f.start&&f.start<=f.end&&f.end<=doc.notification_date&&e.date<=f.start))fail('Проверьте период хранения.',p+'.fields.end');storage=[f.start,f.end];}
   if(e.type==='uncollected'&&(!storage||e.date<storage[1]))fail('Сначала укажите завершившийся период хранения.',p+'.date');
   if(['delivered','mailbox'].includes(e.type)&&storage&&e.date<storage[1])fail('Вручение раньше окончания хранения.',p+'.date');
   return e;
  });
  if(noPhone&&invoice)fail('Указаны отсутствие телефона в накладной и связь по исходному номеру. Уточните источник контактов.','events');
  return {...doc,kind:terminal[endings[0].e.type],schema_version:4};
 }
 function render(doc,branch,catalog){const paragraphs=[],visited=new Set();let previous=null;
  for(const e of doc.events){const values={};for(const [k,v] of Object.entries(e.fields))values[k]=Array.isArray(v)?v.map(p=>p.number).join(', '):typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v)?fmt(v):v;
   values.date=e.date?fmt(e.date):'';values.actual_address=e.actual_address||'';
   if(e.type==='visit'){const repeat=visited.has(e.actual_address)?'повторно ':'';values.visit_location=e.actual_address===doc.address?`курьер ${repeat}был по адресу, указанному в накладной`:`курьер ${repeat}был по новому адресу: ${e.actual_address}`;visited.add(e.actual_address);}
   if(e.type==='contact'&&e.result!=='no_phone'){const many=e.fields.phones.length>1;const origin=e.contact_ref?(many?'предоставленным отправителем':'предоставленному отправителем'):(many?'указанным в накладной':'указанному в накладной');values.phone_prefix=(many?'по номерам телефонов ':'по номеру телефона ')+values.phones+', '+origin+',';}
   let phrase=catalog.types[e.type].results[e.result].phrase.replace(/\{([a-z_]+)\}/g,(_,key)=>{if(values[key]===undefined)fail('Недостаточно сведений для стандартной фразы.','events');return values[key];});
   if(e.type==='sender'){if(e.result==='new_contacts'&&e.fields.has_address)phrase+=' Отправитель также сообщил новый адрес: '+e.fields.new_address+'.';if(e.fields.has_sender_phone)phrase+=' Связь с отправителем осуществлялась по номеру(ам): '+values.sender_phones+'.';}
   if(e.date&&previous===e.date&&['contact','redirect'].includes(e.type)&&paragraphs.length){const prefix=fmt(e.date)+' ';if(phrase.startsWith(prefix))phrase=phrase.slice(prefix.length);paragraphs[paragraphs.length-1]+=' '+phrase[0].toUpperCase()+phrase.slice(1);}else paragraphs.push(phrase);previous=e.date;
  }
  return {intro_before:branch.legal_name+' уведомляет о результатах работы с корреспонденцией ',intro_after:` от ${fmt(doc.order_date)}, адресованной в ${doc.address} для ${doc.recipient}.`,paragraphs,branch:copy(branch),template_version:'static-demo-v4'};
 }
 function stateCounter(s,branch,year){const last=s.counters[branch+':'+year]||0;return {last_used:last,next_number:last+1,year,branch};}
 async function request(path,body){const [settings,catalog,rules]=await config;const url=new URL(path,'https://demo.invalid'),route=url.pathname,branchId=body?.branch||url.searchParams.get('branch')||settings.default_branch,branch=settings.branches.find(b=>b.branch_id===branchId);if(!branch)fail('Филиал не найден.');
  if(route==='/api/settings')return copy(settings);if(route==='/api/catalog')return copy(catalog);if(route==='/api/phone-rules')return copy(rules);
  const action=()=>{const s=read();
   if(route==='/api/counter'){const year=Number(body?.year||url.searchParams.get('year'));if(!Number.isInteger(year)||year<1900||year>9999)fail('Некорректный год.');let c=stateCounter(s,branchId,year);if(body){if(!Number.isSafeInteger(body.last_used)||body.last_used<c.last_used||body.last_used>999999999)fail('Счётчик нельзя уменьшить. Введите допустимое целое число.');s.counters[branchId+':'+year]=body.last_used;write(s);c=stateCounter(s,branchId,year);}return c;}
   const match=/^\/api\/notifications\/(\d+)(\/versions)?$/.exec(route);
   if(match){const r=s.records.find(x=>x.id===+match[1]&&x.branch===branchId);if(!r)fail('Запись не найдена.');return copy(match[2]?r.versions||[]:r);}
   if(route==='/api/notifications'&&!body)return copy(s.records.filter(x=>x.branch===branchId).reverse());
   if(route==='/api/preview'||route==='/api/notifications'){
    const doc=validate(body.document,catalog,rules),year=+doc.notification_date.slice(0,4),existing=body.id?s.records.find(x=>x.id===body.id&&x.branch===branchId):null;
    if(body.id&&!existing)fail('Исходная запись не найдена.');if(existing&&+existing.document.notification_date.slice(0,4)!==year)fail('Для другого года создайте копию.','notification_date');
    doc.addressee=doc.customer;doc.outgoing_number=existing?.document.outgoing_number||String(stateCounter(s,branchId,year).next_number);doc.rendered=render(doc,branch,catalog);
    if(route==='/api/preview')return {document:doc,number_provisional:!existing};
    const duplicate=s.records.find(x=>x.request_key===body.request_key);if(!existing&&duplicate){if(duplicate.input!==JSON.stringify(body.document))fail('Повтор запроса содержит другие данные. Откройте сохранённую запись.');return copy(duplicate);}
    if(existing&&body.revision!==existing.revision)fail('Запись изменена в другой вкладке. Откройте её заново.');
    if(existing&&JSON.stringify(doc)===JSON.stringify(existing.document))return copy(existing);
    const now=new Date().toISOString(),record={id:existing?.id||s.nextId++,branch:branchId,created_at:existing?.created_at||now,updated_at:now,revision:(existing?.revision||0)+1,request_key:body.request_key,input:JSON.stringify(body.document),document:doc,versions:existing?.versions||[]};
    if(existing){record.versions=[...record.versions,{revision:existing.revision,document:existing.document}];s.records[s.records.indexOf(existing)]=record;}else{s.records.push(record);s.counters[branchId+':'+year]=+doc.outgoing_number;}write(s);return copy(record);
   }
   fail('Эта операция недоступна в статической демонстрации.');
  };
  if(body&&route!=='/api/preview'){if(!navigator.locks)fail('Для надёжного сохранения нужен современный браузер с Web Locks.');return navigator.locks.request(KEY,action);}return action();
 }
 return {request,validate,render};
})();
