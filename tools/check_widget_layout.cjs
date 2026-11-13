// Browser layout checks supplement, but do not replace, testing in Telegram.
const { chromium } = require('playwright');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
(async () => {
  const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  for (const width of [320,390,430]) {
    await page.setViewportSize({width,height:800});
    for (const name of ['groups','day']) {
      await page.goto(pathToFileURL(path.resolve('preview',name+'.html')).href);
      const bounds = await page.evaluate(() => ({height:document.querySelector('main').getBoundingClientRect().height,width:document.documentElement.scrollWidth}));
      console.log(name,width,JSON.stringify(bounds));
      if(bounds.height>590 || bounds.width>width) throw new Error('Widget overflows Telegram bounds');
      if(width===390) await page.screenshot({path:path.resolve('preview',name+'.png'),fullPage:true});
      if(name==='day') {
        await page.getByRole('button',{name:'Ближайшая →'}).click();
        if(await page.locator('main').evaluate(n=>n.getBoundingClientRect().height)>590) throw new Error('Nearest card overflows');
        await page.getByRole('button',{name:'Расписание на день'}).click();
        await page.locator('.lesson').first().click();
        if(!await page.locator('.detail').textContent()) throw new Error('Missing lesson details');
        await page.getByRole('button',{name:'← К расписанию'}).click();
      } else {
        const confirm=page.getByRole('button',{name:'Показать расписание'});
        if(!await confirm.isDisabled()) throw new Error('A group must be selected first');
        await page.getByRole('button',{name:'101гму',exact:true}).click();
        if(await confirm.isDisabled()) throw new Error('Group selection did not enable confirmation');
        await confirm.click();
        await page.getByText('Это предпросмотр. Кнопки работают в Telegram.').waitFor();
      }
    }
  }
  await page.setViewportSize({width:1000,height:800});
  await page.goto(pathToFileURL(path.resolve('preview/index.html')).href);
  await page.screenshot({path:path.resolve('preview/overview.png'),fullPage:true});
  await browser.close();
  if(errors.length) throw new Error(errors.join('\n'));
})().catch(error=>{console.error(error);process.exit(1)});
