// Offline browser review of synthetic Django-rendered pages. No real site requests.
const fs = require('fs');
const path = require('path');
const { chromium } = require(process.env.TUITION_PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const directory = path.join(root, '.audit-tools', 'ui');
(async () => {
  const browser = await chromium.launch({headless: true});
  const results = [];
  for (const width of [320, 390, 1280]) {
    const page = await browser.newPage({viewport: {width, height: 900}});
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.hostname !== 'tuition-audit.local') return route.abort();
      const file = url.pathname.startsWith('/static/') ? path.join(root, decodeURIComponent(url.pathname)) : path.join(directory, path.basename(url.pathname));
      if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return route.fulfill({status:404,body:''});
      const type = file.endsWith('.html') ? 'text/html' : file.endsWith('.css') ? 'text/css' : file.endsWith('.js') ? 'text/javascript' : undefined;
      return route.fulfill({path:file, contentType:type});
    });
    for (const name of JSON.parse(fs.readFileSync(path.join(directory, 'manifest.json')))) {
      const errors = []; const listener = error => errors.push(error.message); page.on('pageerror', listener);
      await page.goto(`http://tuition-audit.local/${name}.html`);
      await page.screenshot({path:path.join(directory, `${name}-${width}.png`),fullPage:true});
      const layout = await page.evaluate(() => ({
        viewport: innerWidth, documentWidth: document.documentElement.scrollWidth,
        overflow: [...document.querySelectorAll('.learning *,.certificate *')].filter(el => el.getBoundingClientRect().right>innerWidth+1).slice(0,8).map(el=>({tag:el.tagName,class:el.className})),
        visibleHiddenInputs: [...document.querySelectorAll('input[type=hidden]')].filter(el => el.getBoundingClientRect().height>0).length
      }));
      results.push({name,width,...layout,errors}); page.removeListener('pageerror',listener);
    }
    await page.close();
  }
  fs.writeFileSync(path.join(directory,'results.json'),JSON.stringify(results,null,2));
  console.log(JSON.stringify(results)); await browser.close();
})().catch(error => {console.error(error); process.exit(1);});
