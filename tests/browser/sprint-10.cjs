const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const fixed = require('../fixtures/redesign/sprint-9.json');
const out=process.env.SG_EVIDENCE_DIR||'docs/ux-redesign-evidence/sprint-10';
fs.mkdirSync(out,{recursive:true});
const catalog=fixed.fixtures.map(f=>({universe:'sgx_active',security:{...f.security,isin:f.security.ticker==='ES3'?'SGTEST1234567':null}}));
// Frozen search cases: 1,051 distinct entries force pagination beyond the old 1,000 cap.
for(let i=0;i<1049;i++) catalog.push({universe:'major_global_etfs',security:{...catalog[0].security,security_id:`search-${i}`,ticker:`TEST${i}`,name:`Search fixture ${i}`,isin:`ISIN${i}`}});
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});await page.emulateMedia({reducedMotion:'reduce'});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',route=>{
  const url=new URL(route.request().url());if(url.origin!=='http://127.0.0.1:4173')return route.abort();
  if(url.pathname.endsWith('/data/catalog.json'))return route.fulfill({json:{securities:catalog}});
  if(url.pathname.endsWith('/data/packs/manifest.json'))return route.fulfill({json:fixed.manifest});
  if(url.pathname.includes('/data/packs/security=')){const f=fixed.fixtures.find(f=>url.pathname.includes(f.security.security_id));return route.fulfill({json:f?.pack||{}});}
  return route.continue();
 });
 await page.goto('http://127.0.0.1:4173');await page.waitForSelector('body[data-workspace]');
 for(const name of ['compare','portfolio','methods','simulator']){
  await page.locator(`.main-nav a[href="#${name}"]`).click();await page.waitForSelector(`body[data-workspace="${name}"]`);assert.equal(await page.locator('section[data-workspace]:visible').count(),1);assert.equal(await page.locator('body').getAttribute('data-workspace'),name);
 }
 await page.goBack();await page.waitForSelector('body[data-workspace=methods]');assert.equal(await page.locator('body').getAttribute('data-workspace'),'methods');await page.goForward();await page.waitForSelector('body[data-workspace=simulator]');assert.equal(await page.locator('body').getAttribute('data-workspace'),'simulator');
 for(const [hash,name] of [['analyse','simulator'],['explore','simulator'],['methodology','methods'],['dca','simulator']]){await page.goto(`http://127.0.0.1:4173/#${hash}`);await page.waitForSelector(`body[data-workspace="${name}"]`);}
 await page.goto('http://127.0.0.1:4173/#compare');await page.waitForSelector('body[data-workspace="compare"]');await page.locator('.skip-link').focus();await page.keyboard.press('Enter');assert.equal(await page.evaluate(()=>document.activeElement.id),'workspace-content');assert.equal(new URL(page.url()).hash,'#compare');
 console.log('PASS: routes, one active workspace, legacy links, Back/Forward, reload and route-preserving skip link.');
 if(process.env.SG_ROUTE_ONLY)return;
 await page.goto('http://127.0.0.1:4173/#simulator');await page.waitForSelector('body[data-workspace]');
 await page.locator('#security-select').fill('SGTEST1234567');await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');assert.match(await page.locator('#security-hint').textContent(),/SGX/);
 await page.locator('#security-select').fill('no-match-in-catalog');assert.equal(await page.locator('#security-select').getAttribute('data-security-id'),null);assert.doesNotMatch(await page.locator('#security-hint').textContent(),/SGX/);assert.equal(await page.locator('#security-isin').textContent(),'—');
 await page.locator('[data-clear-security="security-select"]').click();assert.equal(await page.locator('#security-select').inputValue(),'');
 if(await page.locator('.discovery').getAttribute('open')===null)await page.locator('.discovery > summary').click();await page.locator('#catalog-search').fill('missing-query');assert.match(await page.locator('#catalog-grid').textContent(),/No/);await page.locator('#reset-search').click();
 let clicks=0;while(await page.locator('#catalog-more').isVisible()){await page.locator('#catalog-more').click();if(++clicks>20)throw Error('Pagination does not terminate');}
 assert.equal(await page.locator('.security-card').count(),1051);assert.match(await page.locator('#catalog-count').textContent(),/1051/);
 await page.locator('#catalog-search').fill('SGTEST1234567');assert.equal(await page.locator('.security-card').count(),1);
 assert.match(await page.locator('.security-card').textContent(),/SGD/);assert.match(await page.locator('.security-card').textContent(),/2024/);
 console.log('PASS: ISIN/keyboard search, uncommitted metadata reset, clear/reset, coverage preview, and all 1,051 paginated entries reachable.');
 await page.locator('.main-nav a[href="#methods"]').click();await page.locator('#methods-security').fill('ES3');await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');await page.waitForFunction(()=>document.querySelector('#security-methods').textContent.includes('2024'));
 assert.match(await page.locator('#security-methods').textContent(),/SGD/);await page.screenshot({path:`${out}/methods-desktop.png`});
 await page.locator('.main-nav a[href="#simulator"]').click();await page.waitForSelector('body[data-workspace=simulator]');await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:`${out}/workspace-desktop.png`});
 for(const width of [320,390,768,1280]){
  await page.setViewportSize({width,height:1000});await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:`${out}/workspace-${width}.png`});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);assert.equal(overflow,false,`overflow ${width}`);
 }
 await page.setViewportSize({width:390,height:900});await page.locator('#mobile-nav-toggle').click();await page.locator('#mobile-nav a[href="#compare"]').click();await page.waitForSelector('body[data-workspace=compare]');assert.equal(await page.locator('body').getAttribute('data-workspace'),'compare');assert.equal(await page.locator('#mobile-nav-toggle').getAttribute('aria-expanded'),'false');

 const colors=await page.locator('#compare-form label').first().evaluate(el=>({text:getComputedStyle(el).color,background:getComputedStyle(el.closest('form')).backgroundColor}));
 const lum=color=>{const values=color.match(/[0-9.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});return values[0]*.2126+values[1]*.7152+values[2]*.0722;};
 const contrast=(Math.max(lum(colors.text),lum(colors.background))+.05)/(Math.min(lum(colors.text),lum(colors.background))+.05);assert(contrast>=4.5);console.log(`PASS: light-form label contrast ${contrast.toFixed(2)}:1, reduced-motion styles exercised.`);
 assert.deepEqual(errors,[]);console.log('PASS: contextual methods, mobile menu, responsive workspace and no browser errors.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
