const ruSort=new Intl.Collator('ru',{sensitivity:'base',numeric:true});
const normalizeSearch=s=>String(s).toLocaleLowerCase('ru').replaceAll('ё','е').trim().replace(/\s+/g,' ');
const sortedOptions=options=>[...options].sort((a,b)=>ruSort.compare(a.label,b.label));
function phoneCheck(value,rules){
 const country=String(value.country||'').toUpperCase(),rule=rules.countries?.[country];
 if(!rule)return 'Выберите страну телефона.';
 if(value.input_error)return value.input_error;
 const raw=String(value.number||'').trim();
 if(!raw)return 'Введите номер телефона.';
 if(!/^\+?[0-9 ()-]+$/.test(raw))return 'В телефоне допустимы цифры, +, пробелы, скобки и дефисы.';
 const digits=raw.replace(/[^0-9]/g,'');let national;
 if(country==='KZ'){
  national=digits.length===11&&/^[78]/.test(digits)?digits.slice(1):digits;
  if(national.length!==10)return 'Телефон Казахстана: нужно 10 цифр номера или 11 с начальной 7/8; номер не обрезается.';
 }else{
  if(!raw.startsWith('+'+rule.code))return 'Укажите телефон с кодом +'+rule.code+'.';
  national=digits.slice(rule.code.length);
 }
 return !rule.lengths.includes(national.length)||!new RegExp('^(?:'+rule.pattern+')$').test(national)?'Неверная структура или длина телефона для страны «'+rule.name+'».':'';
}
const SearchSelect={
 props:{modelValue:String,options:{type:Array,default:()=>[]},label:String,path:String,error:String,placeholder:{type:String,default:'Выберите…'}},
 emits:['update:modelValue','change'],
 data:()=>({open:false,query:'',active:0,uid:'choices-'+crypto.randomUUID()}),
 computed:{selected(){return this.options.find(o=>o.value===this.modelValue)?.label||'';},matches(){const words=normalizeSearch(this.query).split(' ').filter(Boolean);return sortedOptions(this.options).filter(o=>words.every(w=>normalizeSearch(o.label).includes(w)));}},
 methods:{
  choose(option){if(!option)return;this.$emit('update:modelValue',option.value);this.$emit('change',option.value);this.open=false;this.query='';},
  key(event){if(event.key==='Escape'){this.open=false;return;}if(event.key==='Tab'){this.open=false;return;}if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();if(!this.open){this.open=true;this.query='';this.active=0;}else this.active=Math.max(0,Math.min(this.matches.length-1,this.active+(event.key==='ArrowDown'?1:-1)));this.$nextTick(()=>this.$refs.list?.querySelector('[aria-selected="true"]')?.scrollIntoView({block:'nearest'}));}if(event.key==='Enter'&&this.open){event.preventDefault();this.choose(this.matches[this.active]);}},
  close(){this.open=false;this.query='';}
 },
 template:`<div class="search-select"><label :for="uid">{{label}}</label><input :id="uid" role="combobox" autocomplete="off" :aria-label="label" :aria-expanded="open" aria-autocomplete="list" :aria-controls="uid+'-list'" :aria-activedescendant="open&&matches[active]?uid+'-'+active:undefined" :data-field="path" :aria-invalid="!!error" :value="open?query:selected" :placeholder="placeholder" @focus="open=true;query='';active=0" @input="query=$event.target.value;open=true;active=0" @keydown="key" @blur="close"><div v-if="open" class="choice-popup"><ul ref="list" role="listbox" :id="uid+'-list'" :aria-label="label"><li v-for="(option,i) in matches" :id="uid+'-'+i" :key="option.value" role="option" :aria-selected="active===i" @mousedown.prevent="choose(option)" @mousemove="active=i">{{option.label}}</li></ul><p v-if="!matches.length" role="status">Ничего не найдено</p></div><small v-if="error" class="field-error">{{error}}</small></div>`
};
const PhoneInput={
 components:{SearchSelect},
 props:{modelValue:Object,rules:Object,path:String,error:String},emits:['update:modelValue','remove'],
 computed:{countries(){return sortedOptions(Object.entries(this.rules.countries||{}).map(([value,r])=>({value,label:r.name+' (+'+r.code+')'})));},localError(){return this.error||phoneCheck(this.modelValue,this.rules);}},
 methods:{
  country(value){this.$emit('update:modelValue',{...this.modelValue,country:value,input_error:''});},
  invalid(message){this.$emit('update:modelValue',{...this.modelValue,input_error:message});},
  apply(raw,caret,pasting=false){
   if(this.modelValue.country!=='KZ'){this.$emit('update:modelValue',{...this.modelValue,number:raw,input_error:''});return;}
   if(raw&&!/^\+?[0-9 ()-]+$/.test(raw)){
    if(pasting){this.invalid('Вставка отклонена: в номере есть недопустимые символы.');return;}
    this.$emit('update:modelValue',{...this.modelValue,number:raw,input_error:''});return;
   }
   let digits=raw.replace(/[^0-9]/g,''),left=raw.slice(0,caret).replace(/[^0-9]/g,'').length;
   const masked=raw.startsWith('+7-');
   if(masked){digits=digits.slice(1);left=Math.max(0,left-1);}else if(digits.length===11&&/^[78]/.test(digits)){digits=digits.slice(1);left=Math.max(0,left-1);}
   if(digits.length>10){this.invalid('Ввод отклонён: телефон слишком длинный; номер не обрезан.');this.$nextTick(()=>this.$refs.number.value=this.modelValue.number);return;}
   let display=digits?'+7-':'';
   for(let i=0;i<digits.length;i++){if([3,6,8].includes(i))display+='-';display+=digits[i];}
   this.$emit('update:modelValue',{...this.modelValue,number:display,input_error:''});
   this.$nextTick(()=>{const el=this.$refs.number;el.value=display;let seen=0,pos=display?3:0;for(let i=3;i<display.length;i++){if(/[0-9]/.test(display[i]))seen++;if(seen>=left){pos=i+1;break;}pos=i+1;}el.setSelectionRange(pos,pos);});
  },
  input(event){this.apply(event.target.value,event.target.selectionStart);},
  paste(event){if(this.modelValue.country!=='KZ')return;event.preventDefault();const el=event.target;const data=event.clipboardData.getData('text');const raw=el.value.slice(0,el.selectionStart)+data+el.value.slice(el.selectionEnd);this.apply(raw,el.selectionStart+data.length,true);},
  key(event){const el=event.target;if(this.modelValue.country!=='KZ'||el.selectionStart!==el.selectionEnd)return;const pos=el.selectionStart;if(event.key==='Backspace'&&pos>3&&el.value[pos-1]==='-'){event.preventDefault();this.apply(el.value.slice(0,pos-2)+el.value.slice(pos),pos-2);}if(event.key==='Delete'&&el.value[pos]==='-'){event.preventDefault();this.apply(el.value.slice(0,pos)+el.value.slice(pos+2),pos);}}
 },
 template:`<div class="phone-entry"><div class="phone-row"><search-select label="Страна" :model-value="modelValue.country" :options="countries" :path="path+'.country'" @update:model-value="country"/><label>Телефон *<input ref="number" :data-field="path+'.number'" type="tel" :value="modelValue.number" @input="input" @paste="paste" @keydown="key" :placeholder="modelValue.country==='KZ'?'+7-XXX-XXX-XX-XX':'+'+(rules.countries?.[modelValue.country]?.code||'код страны')" :aria-invalid="!!localError"></label><button type="button" class="remove" aria-label="Удалить телефон" @click="$emit('remove')">×</button></div><small v-if="localError" class="field-error">{{localError}}</small></div>`
};
