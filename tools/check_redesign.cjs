const {chromium}=require('playwright');
const crypto=require('node:crypto');
const fs=require('node:fs');
const fields={auth_date:String(Math.floor(Date.now()/1000)),user:JSON.stringify({id:7,first_name:'Дени'})};
const check=Object.keys(fields).sort().map(k=>k+'='+fields[k]).join('\n');
fields.hash=crypto.createHmac('sha256',crypto.createHmac('sha256','WebAppData').update('123456:MINIAPP_BROWSER_TEST').digest()).update(check).digest('hex');
const initData=new URLSearchParams(fields).toString();
(async()=>{
  fs.mkdirSync('preview',{recursive:true});
  const b=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
  const errors=[];
  try {
    for(const width of [320,390,1100]){
      const context=await b.newContext({viewport:{width,height:850},reducedMotion:width===320?'reduce':'no-preference'});
      const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
      await page.route('https://telegram.org/js/telegram-web-app.js',r=>r.fulfill({body:'',contentType:'text/javascript'}));
      await page.addInitScript(({initData})=>{window.fullscreenRequests=0;window.Telegram={WebApp:{initData,isFullscreen:false,safeAreaInset:{top:12,bottom:10},contentSafeAreaInset:{top:32},ready(){},expand(){},setHeaderColor(){},setBackgroundColor(){},setBottomBarColor(){},isVersionAtLeast(){return true},onEvent(){},HapticFeedback:{selectionChanged(){}},requestFullscreen(){this.isFullscreen=true;window.fullscreenRequests++;}}};},{initData});
      let connected=false,statusReads=0,releaseInitial,failPersonal=true;
      await page.route('**/api/cdo/session*',async r=>{
        const method=r.request().method();
        if(method==='GET'&&++statusReads===1){await new Promise(resolve=>{releaseInitial=resolve;});return r.fulfill({json:{connected:false}});}
        if(method==='POST'){
          const input=r.request().postDataJSON();
          if(input.password!=='valid')return r.fulfill({status:401,json:{error:'Неверный логин или пароль.'}});
          connected=true;
        }
        if(method==='DELETE')connected=false;
        return r.fulfill({json:connected?{connected:true,name:'Дени Студент',group:'102гму',group_selection:{faculty:'5',course:'1',group:'1451'}}:{connected:false}});
      });
      await page.route('**/api/cdo/schedule*',r=>{
        if(failPersonal){failPersonal=false;return r.fulfill({status:503,json:{error:'ЦДО временно не отвечает.'}});}
        const day=new URL(r.request().url()).searchParams.get('date')||'2026-09-09';
        return r.fulfill({json:{date:day,today:'2026-09-09',now:'2026-09-09T08:00:00+03:00',weekday:'Среда',label:day==='2026-09-09'?'9 сентября':'10 сентября',group:{name:'102гму'},lessons:[{start_time:'11:25',end_time:'12:55',subject:'Моя личная дисциплина',pair_number:2,teacher:'Преподаватель',classroom:'А 716',lesson_type:'Сем',groups:'Подгруппа 1'}]}});
      });
      await page.goto('http://127.0.0.1:8081');
      await page.locator('#splash').waitFor({state:'attached',timeout:2000});
      await page.locator('#splash').waitFor({state:'hidden',timeout:5000});
      await page.click('#choose-group');
      await page.locator('#faculty option[value="5"]').waitFor({state:'attached'});await page.selectOption('#faculty','5');
      await page.locator('#course option[value="1"]').waitFor({state:'attached'});await page.selectOption('#course','1');
      await page.getByRole('button',{name:'101гму',exact:true}).click();await page.click('#show');
      await page.locator('#date-label').filter({hasText:'9 сентября'}).waitFor();
      await page.locator('#status').waitFor({state:'hidden'});
      if(await page.locator('#lessons .lesson').count()!==4)throw new Error('Group lessons lost');
      if(await page.locator('#selection-screen').isVisible())throw new Error('Selection is not a separate screen');
      if(await page.evaluate(()=>window.fullscreenRequests)!==1)throw new Error('Fullscreen missing');
      await page.screenshot({path:`preview/redesign-day-${width}.png`,fullPage:true,animations:'disabled'});
      await page.click('#change-group');await page.selectOption('#faculty','');await page.click('#selection-back');await page.click('#next');
      await page.locator('#date-label').filter({hasText:'10 сентября'}).waitFor({timeout:3000});await page.locator('#status').waitFor({state:'hidden'});
      await page.click('#today');await page.locator('#date-label').filter({hasText:'9 сентября'}).waitFor();
      await page.click('#nav-personal');
      await page.fill('#cdo-username','alice');await page.fill('#cdo-password','wrong');await page.click('#cdo-login');
      await page.locator('#cdo-notice').filter({hasText:'Неверный'}).waitFor();
      if(await page.locator('#cdo-password').inputValue())throw new Error('Password remained after submission');
      await page.fill('#cdo-password','valid');await page.click('#cdo-login');
      await page.locator('#cdo-notice').filter({hasText:'ЦДО временно'}).waitFor();
      await page.waitForFunction(()=>document.getElementById('profile-group-name').textContent==='102гму',{},{timeout:3000});
      await page.locator('#personal-retry').click({timeout:3000});
      await page.locator('#personal-lessons').filter({hasText:'Моя личная дисциплина'}).waitFor({timeout:5000}).catch(async error=>{console.log('PERSONAL STATE',await page.locator('body').innerText());await page.screenshot({path:'preview/personal-failure.png',fullPage:true});throw error;});
      releaseInitial();await page.locator('#profile-notice').waitFor({state:'hidden'});
      await page.locator('#personal-lessons').filter({hasText:'Моя личная дисциплина'}).waitFor({timeout:3000});
      await page.click('#personal-next');await page.locator('#personal-date-label').filter({hasText:'10 сентября'}).waitFor();
      await page.screenshot({path:`preview/redesign-personal-${width}.png`,fullPage:true,animations:'disabled'});
      await page.click('#nav-day');if(!await page.locator('#date-label').textContent().then(t=>t.includes('9 сентября')))throw new Error('Personal navigation overwrote group date');
      if(!await page.locator('#change-group').textContent().then(t=>t.includes('102гму')))throw new Error('CDO did not choose account group');
      if(await page.evaluate(()=>JSON.parse(localStorage.getItem('fgu-selection-v1')).group)!=='1451')throw new Error('CDO group was not remembered');
      await page.click('#change-group');await page.getByRole('button',{name:'103гму',exact:true}).click();await page.click('#show');
      await page.locator('#change-group').filter({hasText:'103гму'}).waitFor();await page.locator('#status').waitFor({state:'hidden'});
      await page.click('#nav-profile');await page.locator('#profile-notice').waitFor({state:'hidden'});
      if(await page.locator('#profile-group-name').textContent()!=='102гму')throw new Error('Profile group was replaced by manual schedule choice');
      await page.click('#profile-group');if(!await page.locator('#profile-screen').isVisible())throw new Error('CDO group in profile opens manual selection');
      await page.click('#nav-personal');
      await page.locator('#personal-lessons').filter({hasText:'Моя личная дисциплина'}).waitFor();
      if(await page.locator('#personal-group').textContent()!=='102гму')throw new Error('Personal group follows manual selection');
      if(!await page.locator('#personal-date-label').textContent().then(t=>t.includes('10 сентября')))throw new Error('Changing manual group reset personal date');
      await page.evaluate(()=>localStorage.setItem('fgu-selection-v1',JSON.stringify({faculty:'5',course:'1',group:'1450'})));
      await page.reload();await page.locator('#splash').waitFor({state:'hidden'});
      await page.locator('#change-group').filter({hasText:'102гму'}).waitFor({timeout:5000});
      if(await page.evaluate(()=>JSON.parse(localStorage.getItem('fgu-selection-v1')).group)!=='1451')throw new Error('Restored CDO session did not override stale stored group');
      await page.click('#nav-profile');await page.locator('#profile-cdo').filter({hasText:'Дени Студент'}).waitFor();await page.click('#cdo-logout');
      await page.waitForFunction(()=>document.getElementById('profile-group-name').textContent==='Войди через ЦДО',{},{timeout:3000});
      await page.click('#nav-personal');await page.locator('#cdo-form').waitFor({state:'visible'});
      if(await page.locator('#personal-lessons').isVisible())throw new Error('Personal data remained visible after logout');
      const storage=await page.evaluate(()=>JSON.stringify({...localStorage}));
      if(storage.includes('valid')||storage.includes('alice'))throw new Error('Credentials leaked to storage');
      if(await page.evaluate(()=>document.documentElement.scrollWidth)>width)throw new Error('Overflow '+width);
      await page.reload();await page.locator('#splash').waitFor({state:'hidden'});await page.locator('#date-label').filter({hasText:'9 сентября'}).waitFor();
      console.log('tabs, personal login/logout, isolated dates, intro, layout, fullscreen',width,'PASS');await context.close();
    }
    const guest=await b.newPage();await guest.route('https://telegram.org/js/telegram-web-app.js',r=>r.abort());await guest.goto('http://127.0.0.1:8081');await guest.locator('#splash').waitFor({state:'hidden',timeout:5000});await guest.locator('#status').filter({hasText:'Telegram'}).waitFor();console.log('unavailable SDK does not block intro PASS');
    if(errors.length)throw new Error(errors.join('\n'));
  }finally{await b.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
