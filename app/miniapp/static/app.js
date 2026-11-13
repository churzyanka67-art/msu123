'use strict';
const $ = id => document.getElementById(id);
const palette = ['#b5f56b', '#77b9ff', '#be9bff', '#ffce69'];
const storageKey = 'fgu-selection-v1';
const pending = new Set();
let tg = null, initData = '', selected = {faculty:'', course:'', group:''};
let groupOptions = [], current = null, personal = null, cdoProfile = null, activeTab = 'day', appliedSelection = null;
let retryAction = null, personalRetry = null, catalogLoaded = false;
let authGeneration = 0, authMutationPending = false;
let cdoGroupSync = null, lastCdoGroupKey = '';
const groupWaiters = [];

function node(tag, text, cls) {
  const element=document.createElement(tag);
  if(text!==undefined&&text!==null)element.textContent=text;
  if(cls)element.className=cls;
  return element;
}
function add(parent,tag,text,cls){const element=node(tag,text,cls);parent.append(element);return element;}
function notice(id,text,error=false){$(id).hidden=!text;$(id).textContent=text;$(id).classList.toggle('error',error);}
function haptic(){try{tg?.HapticFeedback?.selectionChanged();}catch{}}
function introTarget(){const rect=$('brand-mark').getBoundingClientRect();document.documentElement.style.setProperty('--intro-x',(rect.left+rect.width/2-innerWidth/2)+'px');document.documentElement.style.setProperty('--intro-y',(rect.top+rect.height/2-innerHeight/2)+'px');}
function insets(){
  const safe=tg?.safeAreaInset||{},content=tg?.contentSafeAreaInset||{};
  for(const edge of ['top','bottom','left','right'])document.documentElement.style.setProperty('--safe-'+edge,((safe[edge]||0)+(content[edge]||0))+'px');
  introTarget();
}
function startIntro(){
  const finish=()=>{$('splash').hidden=true;document.body.classList.remove('intro-running');document.body.classList.add('ui-ready');try{tg?.setHeaderColor?.('#eeeef2');}catch{}};
  introTarget();
  if(matchMedia('(prefers-reduced-motion: reduce)').matches){setTimeout(finish,80);return;}
  setTimeout(()=>{document.body.classList.add('ui-ready');$('splash').classList.add('leaving');},850);
  setTimeout(finish,1350);
}
function fullscreen(){if(!tg)return;try{tg.expand();if(tg.isVersionAtLeast?.('8.0')&&!tg.isFullscreen)tg.requestFullscreen();}catch{$('fullscreen').hidden=true;}}
function setupTelegram(){
  if(!tg){$('fullscreen').hidden=true;return;}
  try{
    tg.ready();tg.setHeaderColor?.($('splash').hidden?'#eeeef2':'#000000');tg.setBackgroundColor?.('#eeeef2');
    if(tg.isVersionAtLeast?.('7.10'))tg.setBottomBarColor?.('#eeeef2');
    for(const event of ['safeAreaChanged','contentSafeAreaChanged','fullscreenChanged','viewportChanged'])tg.onEvent?.(event,insets);
    tg.onEvent?.('fullscreenFailed',()=>{$('fullscreen').hidden=true;});
    if(!tg.isVersionAtLeast?.('8.0'))$('fullscreen').hidden=true;
    tg.BackButton?.onClick(()=>openView('day'));
  }catch{}
  insets();fullscreen();
}
async function telegramReady(){
  for(let i=0;i<120;i++){if(window.Telegram?.WebApp)return window.Telegram.WebApp;await new Promise(resolve=>setTimeout(resolve,25));}
  return null;
}
async function api(path,query={},options={}){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),25000);
  try{
    const response=await fetch('/api/'+path+'?'+new URLSearchParams(query),{...options,signal:controller.signal,headers:{'X-Telegram-Init-Data':initData,...(options.body?{'Content-Type':'application/json'}:{}),...options.headers},cache:'no-store',credentials:'same-origin'});
    let data;try{data=await response.json();}catch{throw new Error('Сервер не отвечает. Попробуй ещё раз.');}
    if(!response.ok){const error=new Error(data.error||'Не удалось загрузить данные.');error.status=response.status;throw error;}
    return data;
  }catch(error){if(error.name==='AbortError')throw new Error('Загрузка заняла слишком много времени. Попробуй ещё раз.');throw error;}
  finally{clearTimeout(timer);}
}
function syncControls(){
  const groupBusy=pending.has('group');
  $('faculty').disabled=groupBusy||!catalogLoaded;
  $('course').disabled=groupBusy||!selected.faculty;
  $('group-search').disabled=groupBusy||!selected.course;
  $('show').disabled=groupBusy||!selected.group;
  for(const id of ['previous','next','today','refresh'])$(id).disabled=groupBusy||!current;
  for(const id of ['cdo-login','cdo-username','cdo-password'])$(id).disabled=pending.has('personal')||authMutationPending||!initData;
  $('cdo-login').firstChild.textContent=pending.has('personal')?'Подключаем… ':'Войти через ЦДО ';
  for(const id of ['personal-previous','personal-next','personal-today','personal-refresh'])$(id).disabled=pending.has('personal')||!personal;
  $('cdo-logout').disabled=pending.has('personal')||pending.has('profile');
}
async function task(action,scope='group'){
  if(pending.has(scope))return;
  pending.add(scope);syncControls();
  const id={group:'status',personal:'cdo-notice',profile:'profile-notice'}[scope];
  notice(id,scope==='group'?'Загружаем расписание…':'Загружаем…');
  if(scope==='group')$('retry').hidden=true;
  if(scope==='personal')$('personal-retry').hidden=true;
  try{await action();notice(id,'');if(scope==='group')retryAction=null;if(scope==='personal')personalRetry=null;}
  catch(error){
    if(scope==='personal'&&error.status===401)setCdoProfile({connected:false});
    notice(id,error.message||'Не удалось загрузить данные.',true);
    if(scope==='group'){retryAction=action;$('retry').hidden=false;}
    if(scope==='personal'&&error.status!==401){personalRetry=action;$('personal-retry').hidden=false;}
  }finally{pending.delete(scope);syncControls();if(scope==='group')groupWaiters.splice(0).forEach(resolve=>resolve());}
}
function openView(view){
  activeTab=view==='selection'?'day':view;
  for(const name of ['day','selection','personal','profile'])$(name+'-screen').hidden=name!==view;
  for(const name of ['day','personal','profile']){const button=$('nav-'+name);button.classList.toggle('active',name===activeTab);if(name===activeTab)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');}
  const title={day:'Расписание',selection:'Моя группа',personal:'Личное',profile:'Профиль'}[view];
  $('page-title').replaceChildren(document.createTextNode(title),node('span','.','heading-dot'));
  $('page-eyebrow').textContent={day:'ТВОЙ УЧЕБНЫЙ ДЕНЬ',selection:'РАСПИСАНИЕ ПОД ТЕБЯ',personal:'ТВОИ ПАРЫ И ПОДГРУППЫ',profile:'ВСЁ НА СВОЁМ МЕСТЕ'}[view];
  try{if(view==='selection')tg?.BackButton?.show();else tg?.BackButton?.hide();}catch{}
  window.scrollTo({top:0,behavior:'instant'});haptic();
  if(view==='personal'&&initData&&!pending.has('personal'))task(ensurePersonal,'personal');
  if(view==='profile'&&initData&&!pending.has('personal'))task(checkCdo,'profile');
}
function fillSelect(id,options,placeholder){const select=$(id);select.replaceChildren(new Option(placeholder,''));options.forEach(option=>select.add(new Option(option.name,option.id)));}
function renderGroups(){
  const query=$('group-search').value.trim().toLocaleLowerCase('ru');$('groups').replaceChildren();
  const visible=groupOptions.filter(option=>option.name.toLocaleLowerCase('ru').includes(query));
  if(!visible.length)add($('groups'),'p',groupOptions.length?'Такой группы не нашли.':'Нет доступных групп.','muted');
  for(const option of visible){const button=add($('groups'),'button',option.name,selected.group===option.id?'selected':'');button.setAttribute('aria-pressed',String(selected.group===option.id));button.onclick=()=>{if(pending.has('group'))return;selected.group=option.id;renderGroups();syncControls();haptic();};}
}
function remember(){try{localStorage.setItem(storageKey,JSON.stringify(appliedSelection));}catch{}}
function shift(day,delta){const d=new Date(day+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+delta);return d.toISOString().slice(0,10);}
async function loadDay(day,refresh=false,choice=appliedSelection||selected,stillCurrent=()=>true){const query={...choice};if(day)query.date=day;if(refresh)query.refresh='1';const data=await api('schedule',query);if(!stillCurrent())return false;current=data;appliedSelection={...choice};remember();renderSchedule(data);renderNearest();$('group-day-card').hidden=false;return true;}
function renderNearest(){
  const data=current,now=new Date(data.now),clock=now.toLocaleTimeString('en-GB',{timeZone:'Europe/Moscow',hour:'2-digit',minute:'2-digit'});
  const nearest=data.lessons.find(lesson=>data.date>data.today||(data.date===data.today&&lesson.end_time>clock));
  const card=$('nearest');card.replaceChildren();const top=add(card,'div',null,'near-top');
  add(top,'span',nearest&&data.date===data.today&&nearest.start_time<=clock?'Сейчас на паре':'Ближайшая пара','lime');add(top,'span',data.group.name,'pill');
  if(nearest){const time=add(card,'div',nearest.start_time,'near-clock');add(time,'small',' — '+nearest.end_time);add(card,'h2',nearest.subject,'near-subject');if(nearest.teacher)add(card,'p',nearest.teacher,'muted');}
  else{add(card,'h2',data.lessons.length?'На этот день всё.':'День без пар.');add(card,'p','Можно выдохнуть. Следующий день — по стрелке ниже.','muted');}
  const footer=add(card,'div',null,'near-footer');add(footer,'span',data.label+' · '+data.weekday);add(footer,'span',nearest?.classroom||'ФГУ','pill');
}
function renderSchedule(data,prefix=''){
  const element=id=>$(prefix+id);
  element('weekday').textContent=data.weekday;element('date-label').textContent=data.label;element('year').textContent=data.date.slice(0,4);
  if(prefix)$('personal-group').textContent=data.group.name;else $('change-group').textContent=data.group.name+' ↗';
  const slots=new Map();for(const lesson of data.lessons){const key=lesson.pair_number??lesson.start_time;if(!slots.has(key))slots.set(key,[]);slots.get(key).push(lesson);}
  const count=slots.size;element('pair-count').textContent=count+' '+(count===1?'пара':count>1&&count<5?'пары':'пар');
  element('day-range').textContent=count?data.lessons.reduce((a,l)=>l.start_time<a?l.start_time:a,'99:99')+' — '+data.lessons.reduce((a,l)=>l.end_time>a?l.end_time:a,'00:00'):'';
  element('track').replaceChildren();element('lessons').replaceChildren();
  for(const items of slots.values()){
    const first=items[0],color=palette[((first.pair_number||1)-1)%palette.length];const bar=add(element('track'),'span');bar.style.setProperty('--color',color);
    const row=add(element('lessons'),'article',null,'lesson');row.style.setProperty('--color',color);
    const times=add(row,'div',null,'lesson-times');add(times,'strong',first.start_time);add(times,'span',first.end_time);add(times,'small',first.pair_number?first.pair_number+' пара':'');
    const details=add(row,'div',null,'lesson-details');
    for(const lesson of items){const part=add(details,'div',null,'lesson-part');const heading=add(part,'div',null,'subject-line');add(heading,'h3',lesson.subject);if(lesson.lesson_type)add(heading,'span',lesson.lesson_type,'type');if(lesson.teacher)add(part,'p',lesson.teacher,'teacher');if(lesson.classroom)add(part,'p','Аудитория '+lesson.classroom,'room');if(lesson.groups&&lesson.groups!==data.group.name)add(part,'p','Группы: '+lesson.groups,'subgroup');if(lesson.start_time!==first.start_time||lesson.end_time!==first.end_time)add(part,'p',lesson.start_time+' — '+lesson.end_time,'subgroup');}
  }
  if(!count){const empty=add(element('lessons'),'div',null,'empty');add(empty,'span','↗','empty-symbol');add(empty,'h3','Можно выдохнуть.');add(empty,'p','В этот день занятий нет.','muted');}
  element('previous').textContent='← '+(shift(data.date,-1)===data.today?'Сегодня':'Назад');element('next').textContent=(shift(data.date,1)===shift(data.today,1)?'Завтра':'Дальше')+' →';
}
function setCdoProfile(profile){
  cdoProfile=profile;const connected=Boolean(profile?.connected);
  $('cdo-login-card').hidden=connected;$('personal-day-card').hidden=!connected||!personal;
  $('profile-cdo').textContent=connected?profile.name:'Не подключён';$('connection-dot').classList.toggle('connected',connected);
  $('profile-group-name').textContent=connected?(profile.group?.trim()||'Группа не указана в ЦДО'):'Войди через ЦДО';
  $('profile-connect').hidden=connected;$('cdo-logout').hidden=!connected;
  if(!connected){personal=null;$('personal-lessons').replaceChildren();$('personal-date-label').textContent='';}
}
async function applyCdoGroup(profile){
  const choice=profile?.group_selection;
  if(!profile?.connected||!choice||!['faculty','course','group'].every(key=>typeof choice[key]==='string'&&choice[key]))return;
  const generation=authGeneration,key=generation+':'+JSON.stringify(choice);
  if(lastCdoGroupKey===key)return;
  if(cdoGroupSync?.key===key)return cdoGroupSync.promise;
  const stillCurrent=()=>generation===authGeneration&&cdoProfile?.connected&&JSON.stringify(cdoProfile.group_selection)===JSON.stringify(choice);
  const promise=(async()=>{
    while(pending.has('group'))await new Promise(resolve=>groupWaiters.push(resolve));
    if(!stillCurrent())return;
    await task(async()=>{
      const faculties=(await api('options')).options;
      if(!faculties.some(option=>option.id===choice.faculty))throw new Error('Группа ЦДО пока не найдена в каталоге расписания.');
      const courses=(await api('options',{faculty:choice.faculty})).options;
      if(!courses.some(option=>option.id===choice.course))throw new Error('Курс из ЦДО пока не найден в каталоге расписания.');
      const groups=(await api('options',{faculty:choice.faculty,course:choice.course})).options;
      if(!groups.some(option=>option.id===choice.group))throw new Error('Группа ЦДО пока не найдена в каталоге расписания.');
      if(!stillCurrent()||!await loadDay(undefined,false,choice,stillCurrent))return;
      selected={...choice};catalogLoaded=true;groupOptions=groups;
      fillSelect('faculty',faculties,'Выбери направление');$('faculty').value=choice.faculty;
      fillSelect('course',courses,'Выбери курс');$('course').value=choice.course;
      $('group-search').value='';renderGroups();lastCdoGroupKey=key;
    });
  })();
  cdoGroupSync={key,promise};
  try{await promise;}finally{if(cdoGroupSync?.promise===promise)cdoGroupSync=null;}
}
async function checkCdo(){const generation=authGeneration,profile=await api('cdo/session');if(generation===authGeneration){setCdoProfile(profile);await applyCdoGroup(profile);}}
async function loadPersonal(day){const generation=authGeneration,query={};if(day)query.date=day;const data=await api('cdo/schedule',query);if(generation!==authGeneration)return;personal=data;renderSchedule(personal,'personal-');$('personal-day-card').hidden=false;}
async function ensurePersonal(){await checkCdo();if(cdoProfile.connected&&!personal)await loadPersonal();}

$('choose-group').onclick=()=>openView('selection');$('change-group').onclick=()=>openView('selection');$('selection-back').onclick=()=>openView('day');
$('faculty').onchange=()=>task(async()=>{selected={faculty:$('faculty').value,course:'',group:''};fillSelect('course',[],'Выбери');groupOptions=[];$('groups').replaceChildren();$('group-search').value='';if(selected.faculty)fillSelect('course',(await api('options',{faculty:selected.faculty})).options,'Выбери курс');});
$('course').onchange=()=>task(async()=>{selected.course=$('course').value;selected.group='';groupOptions=[];$('group-search').value='';if(selected.course)groupOptions=(await api('options',{faculty:selected.faculty,course:selected.course})).options;renderGroups();});
$('group-search').oninput=renderGroups;
$('show').onclick=()=>task(async()=>{await loadDay(undefined,false,{...selected});openView('day');});
$('previous').onclick=()=>task(()=>loadDay(shift(current.date,-1)));$('next').onclick=()=>task(()=>loadDay(shift(current.date,1)));$('today').onclick=()=>task(()=>loadDay(current.today));$('refresh').onclick=()=>task(()=>loadDay(current.date,true));
for(const name of ['day','personal','profile'])$('nav-'+name).onclick=()=>openView(name);
$('home').onclick=event=>{event.preventDefault();openView('day');};$('fullscreen').onclick=fullscreen;
$('retry').onclick=()=>{if(retryAction)task(retryAction);};$('personal-retry').onclick=()=>{if(personalRetry)task(personalRetry,'personal');};
$('profile-connect').onclick=()=>openView('personal');
$('password-toggle').onclick=()=>{const visible=$('cdo-password').type==='password';$('cdo-password').type=visible?'text':'password';$('password-toggle').textContent=visible?'Скрыть':'Показать';$('password-toggle').setAttribute('aria-pressed',String(visible));$('password-toggle').setAttribute('aria-label',visible?'Скрыть пароль':'Показать пароль');};
$('cdo-form').onsubmit=event=>{
  event.preventDefault();if(pending.has('personal')||authMutationPending)return;
  const generation=++authGeneration;
  let body=JSON.stringify({username:$('cdo-username').value,password:$('cdo-password').value});$('cdo-password').value='';$('cdo-password').type='password';$('password-toggle').textContent='Показать';$('password-toggle').setAttribute('aria-pressed','false');
  // Login is intentionally not a retry closure: never retain a password after the request.
  pending.add('personal');syncControls();notice('cdo-notice','Подключаем ЦДО…');$('personal-retry').hidden=true;
  (async()=>{try{const profile=await api('cdo/session',{}, {method:'POST',body});body=null;if(generation!==authGeneration)return;personal=null;setCdoProfile(profile);await applyCdoGroup(profile);await loadPersonal();notice('cdo-notice','');haptic();}
    catch(error){if(generation!==authGeneration)return;if(error.status===401)setCdoProfile({connected:false});else if(cdoProfile?.connected){personalRetry=()=>loadPersonal();$('personal-retry').hidden=false;}notice('cdo-notice',error.message||'Не удалось войти.',true);}
    finally{body=null;pending.delete('personal');syncControls();}})();
};
$('cdo-logout').onclick=()=>task(async()=>{const generation=++authGeneration;authMutationPending=true;syncControls();try{await api('cdo/session',{}, {method:'DELETE'});if(generation!==authGeneration)return;setCdoProfile({connected:false});notice('cdo-notice','');personalRetry=null;$('personal-retry').hidden=true;}finally{authMutationPending=false;}},'profile');
$('personal-previous').onclick=()=>task(()=>loadPersonal(shift(personal.date,-1)),'personal');$('personal-next').onclick=()=>task(()=>loadPersonal(shift(personal.date,1)),'personal');$('personal-today').onclick=()=>task(()=>loadPersonal(personal.today),'personal');$('personal-refresh').onclick=()=>task(()=>loadPersonal(personal.date),'personal');

startIntro();syncControls();
(async()=>{
  tg=await telegramReady();initData=tg?.initData||'';setupTelegram();syncControls();
  if(!initData){notice('status','Открой приложение кнопкой «Расписание» в Telegram — так мы сможем загрузить твои пары.',true);setCdoProfile({connected:false});return;}
  const firstName=tg?.initDataUnsafe?.user?.first_name;if(firstName)$('profile-name').textContent=firstName;
  task(async()=>{
    const faculties=await api('options');fillSelect('faculty',faculties.options,'Выбери направление');catalogLoaded=true;
    let saved;try{saved=JSON.parse(localStorage.getItem(storageKey)||'null');}catch{}
    if(!saved||!faculties.options.some(option=>option.id===saved.faculty))return;
    selected.faculty=saved.faculty;$('faculty').value=saved.faculty;
    const courses=(await api('options',{faculty:selected.faculty})).options;fillSelect('course',courses,'Выбери курс');
    if(!courses.some(option=>option.id===saved.course))return;
    selected.course=saved.course;$('course').value=saved.course;groupOptions=(await api('options',{faculty:selected.faculty,course:selected.course})).options;
    if(groupOptions.some(option=>option.id===saved.group))selected.group=saved.group;
    renderGroups();if(selected.group)await loadDay();
  });
  task(checkCdo,'profile');
})();
