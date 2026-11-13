'use strict';
const tg = window.Telegram?.WebApp;
const $ = id => document.getElementById(id);
const palette = ['#b5f56b', '#77b9ff', '#be9bff', '#ffce69'];
let selected = {faculty:'', course:'', group:''}, groupOptions = [], current = null, busy = false, retryAction = null;
const storageKey = 'fgu-selection-v1';
const initData = tg?.initData || '';

function insets() {
  const safe=tg?.safeAreaInset||{}, content=tg?.contentSafeAreaInset||{};
  for(const edge of ['top','bottom','left','right']) {
    document.documentElement.style.setProperty('--safe-'+edge, ((safe[edge]||0)+(content[edge]||0))+'px');
  }
}
function fullscreen() {
  if(!tg) return;
  tg.expand();
  if(tg.isVersionAtLeast?.('8.0') && !tg.isFullscreen) tg.requestFullscreen();
}
function setupTelegram() {
  if(!tg) { $('fullscreen').hidden=true; return; }
  tg.ready(); tg.setHeaderColor('#eeeef2'); tg.setBackgroundColor('#eeeef2');
  if(tg.isVersionAtLeast?.('7.10')) tg.setBottomBarColor('#eeeef2');
  for(const event of ['safeAreaChanged','contentSafeAreaChanged','fullscreenChanged','viewportChanged']) tg.onEvent(event,insets);
  tg.onEvent('fullscreenFailed', event=>{if(event.error==='UNSUPPORTED') $('fullscreen').hidden=true;});
  if(!tg.isVersionAtLeast?.('8.0')) $('fullscreen').hidden=true;
  insets(); fullscreen();
}
function node(tag, text, cls) {const n=document.createElement(tag); if(text!==undefined&&text!==null)n.textContent=text; if(cls)n.className=cls; return n;}
function add(parent, tag, text, cls) {const n=node(tag,text,cls);parent.append(n);return n;}
function notice(text, error=false) { $('status').hidden=!text; $('status').textContent=text; $('status').classList.toggle('error',error); }
function haptic(){tg?.HapticFeedback?.selectionChanged();}
async function api(path, query={}) {
  const response=await fetch('/api/'+path+'?'+new URLSearchParams(query),{headers:{'X-Telegram-Init-Data':initData},cache:'no-store'});
  let data; try {data=await response.json();}catch{throw new Error('Сервер не отвечает. Попробуй ещё раз.');}
  if(!response.ok) throw new Error(data.error||'Не удалось загрузить данные.');
  return data;
}
async function task(action) {
  if(busy)return;
  busy=true;document.body.classList.add('loading');notice('Обновляем расписание…');$('retry').hidden=true;
  for(const el of [$('faculty'),$('course'),$('group-search'),$('show')])el.disabled=true;
  try{await action();notice('');retryAction=null;}
  catch(error){notice(error.message||'Не удалось загрузить расписание.',true);retryAction=action;$('retry').hidden=false;}
  finally{busy=false;document.body.classList.remove('loading');$('faculty').disabled=!$('faculty').options.length;$('course').disabled=!selected.faculty;$('group-search').disabled=!selected.course;$('show').disabled=!selected.group;}
}
function fillSelect(id, options, placeholder) {
  const select=$(id);select.replaceChildren(new Option(placeholder,''));options.forEach(o=>select.add(new Option(o.name,o.id)));
  select.disabled=!options.length;
}
function renderGroups() {
  const q=$('group-search').value.trim().toLocaleLowerCase('ru');$('groups').replaceChildren();
  const visible=groupOptions.filter(o=>o.name.toLocaleLowerCase('ru').includes(q));
  if(!visible.length)add($('groups'),'p',groupOptions.length?'Такой группы не нашли.':'Нет доступных групп.','muted');
  for(const option of visible){const b=add($('groups'),'button',option.name,selected.group===option.id?'selected':'');b.setAttribute('aria-pressed',String(selected.group===option.id));b.onclick=()=>{if(busy)return;selected.group=option.id;haptic();renderGroups();$('show').disabled=false;};}
}
function remember(){try{localStorage.setItem(storageKey,JSON.stringify(selected));}catch{}}
function scrollToSection(id){$(id).scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});$('nav-day').classList.toggle('active',id==='day-section');$('nav-group').classList.toggle('active',id==='selection-section');}
function shift(day, delta){const d=new Date(day+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+delta);return d.toISOString().slice(0,10);}
async function loadDay(day, refresh=false) {
  const query={...selected};if(day)query.date=day;if(refresh)query.refresh='1';
  const data=await api('schedule',query);current=data;remember();renderDay();$('refresh').disabled=false;
}
function renderNearest() {
  const d=current, now=new Date(d.now), clock=now.toLocaleTimeString('en-GB',{timeZone:'Europe/Moscow',hour:'2-digit',minute:'2-digit'});
  const nearest=d.lessons.find(l=>d.date>d.today||(d.date===d.today&&l.end_time>clock));const card=$('nearest');card.replaceChildren();
  const top=add(card,'div',null,'near-top');add(top,'span',nearest&&d.date===d.today&&nearest.start_time<=clock?'Сейчас на паре':'Ближайшая пара','lime');add(top,'span',d.group.name,'pill');
  if(!nearest){add(card,'h2',d.lessons.length?'На сегодня всё.':'День без пар.');add(card,'p','Можно выдохнуть. Следующий день — по кнопке справа.','muted');}
  else{const time=add(card,'div',nearest.start_time,'near-clock');add(time,'small',' — '+nearest.end_time);add(card,'h2',nearest.subject,'near-subject');if(nearest.teacher)add(card,'p',nearest.teacher,'muted');}
  const foot=add(card,'div',null,'near-footer');add(foot,'span',d.label+' · '+d.weekday);add(foot,'span',nearest?.classroom||'ФГУ','pill');
}
function renderDay() {
  const d=current;$('weekday').textContent=d.weekday;$('date-label').textContent=d.label;$('year').textContent=d.date.slice(0,4);$('change-group').textContent=d.group.name+' ↗';
  const slots=new Map();for(const l of d.lessons){const key=l.pair_number??l.start_time;if(!slots.has(key))slots.set(key,[]);slots.get(key).push(l);}
  const count=slots.size;$('pair-count').textContent=count+' '+(count===1?'пара':count>1&&count<5?'пары':'пар');
  $('day-range').textContent=count?d.lessons.reduce((a,l)=>l.start_time<a?l.start_time:a,'99:99')+' — '+d.lessons.reduce((a,l)=>l.end_time>a?l.end_time:a,'00:00'):'';
  $('track').replaceChildren();$('lessons').replaceChildren();
  for(const [key,items] of slots){const first=items[0],color=palette[((first.pair_number||1)-1)%palette.length];const bar=add($('track'),'span');bar.style.setProperty('--color',color);const row=add($('lessons'),'article',null,'lesson');row.style.setProperty('--color',color);const times=add(row,'div',null,'lesson-times');add(times,'strong',first.start_time);add(times,'span',first.end_time);add(times,'small',first.pair_number?first.pair_number+' пара':'');const details=add(row,'div',null,'lesson-details');for(const l of items){const part=add(details,'div',null,'lesson-part');const heading=add(part,'div',null,'subject-line');add(heading,'h3',l.subject);if(l.lesson_type)add(heading,'span',l.lesson_type,'type');if(l.teacher)add(part,'p',l.teacher,'teacher');if(l.classroom)add(part,'p','Аудитория '+l.classroom,'room');if(l.groups&&l.groups!==d.group.name)add(part,'p','Группы: '+l.groups,'subgroup');if(l.start_time!==first.start_time||l.end_time!==first.end_time)add(part,'p',l.start_time+' — '+l.end_time,'subgroup');}}
  if(!count){const e=add($('lessons'),'div',null,'empty');add(e,'span','↗','empty-symbol');add(e,'h3','Можно выдохнуть.');add(e,'p','В этот день занятий нет.','muted');}
  $('day-nav').hidden=false;$('previous').textContent='← '+(shift(d.date,-1)===d.today?'Сегодня':'Назад');$('next').textContent=(shift(d.date,1)===shift(d.today,1)?'Завтра':'Дальше')+' →';renderNearest();
}
$('faculty').onchange=()=>task(async()=>{selected={faculty:$('faculty').value,course:'',group:''};fillSelect('course',[],'Выбери');groupOptions=[];$('groups').replaceChildren();$('group-search').value='';if(selected.faculty){const d=await api('options',{faculty:selected.faculty});fillSelect('course',d.options,'Выбери курс');}});
$('course').onchange=()=>task(async()=>{selected.course=$('course').value;selected.group='';groupOptions=[];$('group-search').value='';if(selected.course){const d=await api('options',{faculty:selected.faculty,course:selected.course});groupOptions=d.options;}renderGroups();});
$('group-search').oninput=renderGroups;
$('show').onclick=()=>task(async()=>{await loadDay();scrollToSection('day-section');haptic();});
$('previous').onclick=()=>task(()=>loadDay(shift(current.date,-1)));
$('next').onclick=()=>task(()=>loadDay(shift(current.date,1)));
$('today').onclick=()=>task(()=>loadDay(current.today));
$('refresh').onclick=()=>task(()=>loadDay(current.date,true));
$('change-group').onclick=() => scrollToSection('selection-section');
$('nav-day').onclick=()=>scrollToSection(current?'day-section':'selection-section');
$('nav-group').onclick=()=>scrollToSection('selection-section');
$('fullscreen').onclick=fullscreen;
$('retry').onclick=()=>{if(retryAction)task(retryAction);};
setupTelegram();
if(!initData){notice('Открой приложение кнопкой «Расписание» в Telegram — так мы сможем загрузить твои пары.',true);}
else task(async()=>{
  const faculties=await api('options');fillSelect('faculty',faculties.options,'Выбери направление');
  let saved;try{saved=JSON.parse(localStorage.getItem(storageKey)||'null');}catch{}
  if(!saved||!faculties.options.some(x=>x.id===saved.faculty))return;
  selected.faculty=saved.faculty;$('faculty').value=saved.faculty;
  const courses=await api('options',{faculty:selected.faculty});fillSelect('course',courses.options,'Выбери курс');
  if(!courses.options.some(x=>x.id===saved.course))return;
  selected.course=saved.course;$('course').value=saved.course;
  groupOptions=(await api('options',{faculty:selected.faculty,course:selected.course})).options;
  if(groupOptions.some(x=>x.id===saved.group))selected.group=saved.group;
  renderGroups();if(selected.group)await loadDay();
});
