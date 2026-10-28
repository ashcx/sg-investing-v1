const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  let release;
  const held = new Promise(resolve => { release = resolve; });
  try {
    const page = await browser.newPage();
    await page.route('**/data/data-status.json', async route => { await held; await route.fulfill({ json: { backfill: { as_of: '2024-05-01' } } }); });
    await page.goto('http://127.0.0.1:4174/#portfolio', { waitUntil: 'domcontentloaded' });
    let ready = true;
    try { await page.waitForFunction(() => document.body.dataset.workspace === 'portfolio', {}, { timeout: 2000 }); } catch { ready = false; }
    assert.equal(ready, true, 'workspace initialization must not wait for optional data-status metadata');
    console.log('PASS startup: route and controls initialize while data-status metadata remains pending.');
  } finally { release(); await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
