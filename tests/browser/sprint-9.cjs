// Deterministic UI regressions against real packs -> worker calculations.
// Serve frontend/ locally; PLAYWRIGHT_MODULE may point to an existing installation.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const fixed = require('../fixtures/redesign/sprint-9.json');
const output = path.resolve(process.env.SG_EVIDENCE_DIR || 'docs/ux-redesign-evidence/sprint-9');
fs.mkdirSync(output,{recursive:true});
const base = process.env.SG_TEST_URL || 'http://127.0.0.1:4173';
const es3 = fixed.fixtures[0], smh = fixed.fixtures[1];
(async () => {
 const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || (fs.existsSync('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome') ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' : undefined), headless: true });
 try {
 const page = await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[]; page.on('pageerror', e=>errors.push(e.message));
 await page.route('**/*', async route=>{
  const url=new URL(route.request().url());
  if(url.origin!==new URL(base).origin)return route.abort();
  const send=json=>route.fulfill({json});
  if(url.pathname.endsWith('/data/catalog.json'))return send({securities:fixed.fixtures.map(f=>({universe:'ui_fixture',security:f.security}))});
  if(url.pathname.endsWith('/data/packs/manifest.json'))return send(fixed.manifest);
  if(url.pathname.includes('/data/packs/security=')){
   const f=fixed.fixtures.find(f=>url.pathname.includes(f.security.security_id));
   return f ? send(f.pack) : route.fulfill({status:404,body:'No fixture pack'});
  }
  return route.continue();
 });
 await page.goto(base); await page.waitForSelector('#analysis-request-state');
 const unified=await page.locator('#regular-inputs').count()>0;
 const select=async(sel,f)=>page.locator(sel).evaluate((el,sec)=>{el.value=`${sec.ticker} · ${sec.name}`;el.dataset.securityId=sec.security_id;el.dispatchEvent(new Event('change',{bubbles:true}));},f.security);
 const submit=async kind=>{const formKind=unified&&kind==='dca'?'analysis':kind;await page.locator(`#${formKind}-form button[type=submit]`).click(); await page.waitForFunction(k=>['current','failed','invalid'].includes(document.querySelector(`#${k}-form`).dataset.resultState),formKind,{timeout:10000});};
 const state=kind=>page.locator(`#${unified&&kind==='dca'?'analysis':kind}-form`).getAttribute('data-result-state');
 const capture=async name=>{await page.locator('#analysis-request-state').evaluate(el=>el.scrollIntoView({block:'start',behavior:'instant'})); await page.screenshot({path:path.join(output,`${name}.png`)});};
 assert.equal(await page.locator('#result-content').isVisible(),false); assert.equal(await state('analysis'),'empty');
 await capture('empty-desktop'); console.log('PASS F01: fresh load has no mismatched example.');
 await select('#security-select',es3);
 await page.locator('#initial-amount').fill('3000'); await page.locator('#start-date').fill('2024-01-01'); await page.locator('#end-date').fill('2024-06-30');
 await submit('analysis'); assert.equal(await state('analysis'),'current',await page.locator('#form-error').textContent());
 assert.equal(await page.locator('#result-title').textContent(),'ES3');
 assert.equal(await page.locator('#fx-value').locator('..').isVisible(),false);
 assert.match(await page.locator('#analysis-coverage').textContent(),/Requested: 2024-01-01.*Resolved: 2024-01-02/);
 assert.match(await page.locator('#analysis-coverage').textContent(),/Synthetic UI fixture/);
 await capture('coverage-sgd-desktop');
 const fingerprint=()=>unified?page.locator('#result-title, #final-value, #series-chart, #warning-list, #fx-value').evaluateAll(nodes=>nodes.map(n=>n.innerHTML).join('\n')):page.locator('#result-content').innerHTML();
 const before=await fingerprint();
 if(unified)await page.locator('[data-investing-mode=regular]').click();
 await select(unified?'#security-select':'#dca-security',smh); await page.waitForTimeout(1100);
 assert.equal(await fingerprint(),before);
 await page.locator(unified?'#start-date':'#dca-start').fill('2024-01-01'); await page.locator(unified?'#end-date':'#dca-end').fill('2024-06-30'); await submit('dca');
 assert.equal(await state('dca'),'current',await page.locator(unified?'#form-error':'#dca-error').textContent());
 await page.locator('[data-dca-currency=native]').click(); if(unified)assert.match(await page.locator('.dca-price-chart h4').textContent(),/USD/); assert.equal(await fingerprint(),before);
 await capture('isolated-es3-smh-desktop'); console.log('PASS F03: ES3 analysis and chart survive SMH DCA selection, calculation, and currency change.');
 if(unified)await page.locator('[data-investing-mode=one-time]').click();
 await page.locator('#initial-amount').fill('6000'); assert.equal(await state('analysis'),'pending');
 assert.match(await page.locator('#analysis-request-state').textContent(),/Previous result.*3000 SGD initial/);
 assert.match(await page.locator('#download-result').textContent(),/previous request/);
 await page.waitForTimeout(900); assert.equal(await state('analysis'),'pending');
 const downloadPromise=page.waitForEvent('download'); await page.locator('#download-result').click();
 const download=await downloadPromise; const exported=JSON.parse(fs.readFileSync(await download.path(),'utf8'));
 assert.equal(exported.request.initial_sgd,'3000'); assert.equal(exported.request.start_date,'2024-01-01');
 await page.context().grantPermissions(['clipboard-read','clipboard-write']);
 await page.locator('#copy-link').click(); const shared=new URL(await page.evaluate(()=>navigator.clipboard.readText()));
 assert.equal(shared.searchParams.get('initial_sgd'),'3000');assert.equal(shared.searchParams.get('start_date'),'2024-01-01');
 console.log('PASS: previous JSON and share link preserve submitted amount/requested dates.');

 await capture('previous-amount-desktop'); console.log('PASS F02: amount edit labels original output previous without auto-running.');
 await page.locator('#initial-amount').fill('0'); await submit('analysis'); assert.equal(await state('analysis'),'invalid');
 assert.match(await page.locator('#analysis-request-state').textContent(),/Previous result/); await capture('invalid-amount-desktop');
 await page.locator('#initial-amount').fill('6000'); await page.locator('#start-date').fill('2027-01-01'); await page.locator('#end-date').fill('2027-06-30');
 await submit('analysis'); assert.equal(await state('analysis'),'failed'); assert.match(await page.locator('#analysis-request-state').textContent(),/Previous result/);
 await capture('unsupported-analysis-desktop');
 if(unified)await page.locator('[data-investing-mode=regular]').click();
 await page.locator(unified?'#start-date':'#dca-start').fill('2027-01-01'); await page.locator(unified?'#end-date':'#dca-end').fill('2027-06-30'); await submit('dca');
 assert.equal(await state('dca'),'failed'); assert.match(await page.locator('#dca-request-state').textContent(),/Previous result/);
 console.log('PASS F08: invalid amount and unsupported analysis/DCA dates retain explicitly previous requests.');
 if(unified)await page.locator('[data-investing-mode=one-time]').click();
 // A slow old request must not commit after an invalid edit.
 await page.locator('#start-date').fill('2024-01-01');await page.locator('#end-date').fill('2024-06-30');
 await page.route('**/data/packs/security=*',async route=>{await new Promise(r=>setTimeout(r,500));const f=fixed.fixtures.find(f=>route.request().url().includes(f.security.security_id));return route.fulfill({json:f.pack});});
 await page.locator('#analysis-form button[type=submit]').click();await page.locator('#initial-amount').fill('0');
 await page.waitForTimeout(900);assert.equal(await state('analysis'),'pending');assert.match(await page.locator('#analysis-request-state').textContent(),/Previous result.*3000 SGD initial/);
 console.log('PASS: edit during in-flight calculation suppresses late response.');
 for(const width of [390,320]){await page.setViewportSize({width,height:900});await capture(`previous-mobile-${width}`);}
 await page.setViewportSize({width:1440,height:1000});
 await select('#security-select',smh);await page.locator('#initial-amount').fill('3000');
 await page.locator('#start-date').fill('2024-01-01');await page.locator('#end-date').fill('2024-06-30');await submit('analysis');
 assert.equal(await state('analysis'),'current',await page.locator('#form-error').textContent());
 assert.match(await page.locator('#fx-value').locator('..').textContent(),/1 USD = S\$/);
 assert.match(await page.locator('#analysis-coverage').textContent(),/Latest published USD\/SGD FX date/);
 await capture('coverage-usd-desktop');
 for(const width of [390,320]){await page.setViewportSize({width,height:900});await capture(`coverage-usd-mobile-${width}`); const bounds=await page.locator('#results-panel').boundingBox(); assert(bounds.x>=0 && bounds.x+bounds.width<=width+1,'Analysis output fits mobile viewport');}
 console.log('PASS F07/F09/F15: foreign/SGD FX captions, requested/resolved dates, coverage, and attached warning details.');

 await page.setViewportSize({width:1440,height:1000});
 await page.evaluate(()=>{location.hash='compare';});await page.waitForSelector('body[data-workspace=compare]');
 for(const chip of await page.locator('#compare-ticker-chips button').all()) await chip.click();
 await page.locator('#compare-tickers').fill('ES3');await page.locator('#compare-ticker-options .combobox-option').first().click();
 await page.locator('#compare-tickers').fill('SMH');await page.locator('#compare-ticker-options .combobox-option').first().click();
 await page.locator('#compare-start').fill('2024-01-01');await page.locator('#compare-end').fill('2024-06-30');
 await submit('compare');assert.equal(await state('compare'),'current',await page.locator('#compare-error').textContent());
 await page.locator('#compare-amount').fill('20000');assert.equal(await state('compare'),'pending');assert.match(await page.locator('#compare-request-state').textContent(),/Previous result/);
 await page.evaluate(()=>{location.hash='portfolio';});await page.waitForSelector('body[data-workspace=portfolio]');
 await page.locator('#portfolio-as-of').fill('2024-06-28');
 const row=page.locator('#ledger-rows tr').first();await row.locator('.ledger-type').selectOption('CASH_DEPOSIT');
 await row.locator('.ledger-security').evaluate(el=>{el.dataset.securityId='';el.value='';});
 await row.locator('.ledger-quantity').fill('0');await row.locator('.ledger-cash').fill('1000');await row.locator('.ledger-currency').selectOption('SGD');
 await submit('portfolio');assert.equal(await state('portfolio'),'current',await page.locator('#portfolio-error').textContent());
 await row.locator('.ledger-cash').fill('-1');await submit('portfolio');assert.equal(await state('portfolio'),'invalid');assert.match(await page.locator('#portfolio-request-state').textContent(),/Previous result/);
 console.log('PASS: comparison and portfolio explicit current/pending/invalid ownership.');
 assert.deepEqual(errors,[]);console.log('PASS: no browser exceptions.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
