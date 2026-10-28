const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const out = process.env.SG_EVIDENCE_DIR || 'docs/ux-redesign-evidence/sprint-12';
fs.mkdirSync(out, { recursive: true });
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('http://127.0.0.1:4174/#compare');
    await page.waitForSelector('#compare-ticker-chips .empty-slot');
    assert.equal(await page.locator('#compare-ticker-chips .empty-slot').count(), 2);
    for (const ticker of ['QQQ', 'VALL']) {
      await page.locator('#compare-tickers').fill(ticker);
      await page.locator('#compare-ticker-options .combobox-option').first().click();
    }
    await page.locator('#compare-start').fill('2024-01-02');
    await page.locator('#compare-end').fill('2024-05-01');
    await page.locator('#compare-coverage button').click();
    await page.locator('#compare-form button[type=submit]').click();
    await page.waitForFunction(() => document.querySelector('#compare-form').dataset.resultState === 'current');
    assert.match(await page.locator('#compare-results').textContent(), /QQQ/);
    assert.match(await page.locator('#compare-results').textContent(), /VALL/);
    await page.screenshot({ path: `${out}/review-desktop.png`, fullPage: true });
    await page.locator('#compare-amount').fill('20000');
    assert.match(await page.locator('#compare-request-state').textContent(), /Previous result/);
    for (const width of [320, 390, 768, 1280, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `overflow ${width}`);
    }
    await page.setViewportSize({ width: 390, height: 1000 });
    await page.screenshot({ path: `${out}/review-mobile.png`, fullPage: true });
    assert.deepEqual(errors, []);
    console.log('PASS Sprint 12 browser: empty slots, explicit shared dates, local calculations, previous-result state and five viewport widths.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
