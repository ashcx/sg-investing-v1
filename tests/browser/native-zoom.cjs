const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const out = process.env.SG_EVIDENCE_DIR || 'docs/ux-redesign-evidence/sprint-14';
(async () => {
  const context = await chromium.launchPersistentContext(fs.mkdtempSync(path.join(os.tmpdir(), 'sg-native-zoom-')), { executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, viewport: { width: 1440, height: 1000 } });
  const evidence = [];
  try {
    const page = await context.newPage();
    await page.goto('chrome://settings/appearance');
    await page.locator('#zoomLevel').selectOption({ label: '200%' });
    assert.equal((await page.locator('#zoomLevel option:checked').textContent()).trim(), '200%');
    for (const route of ['simulator','compare','portfolio','methods']) {
      await page.goto(`http://127.0.0.1:4174/#${route}`);
      await page.waitForFunction(name => document.body.dataset.workspace === name, route);
      if (route === 'portfolio') await page.locator('#add-ledger-row').click();
      const geometry = await page.evaluate(() => ({ dpr: devicePixelRatio, viewport: innerWidth, document: document.documentElement.scrollWidth }));
      assert.ok(geometry.dpr >= 1.9, 'native browser zoom must affect devicePixelRatio');
      assert.ok(geometry.document <= geometry.viewport, `${route} overflows at native 200%`);
      evidence.push({ route, ...geometry });
      await page.screenshot({ path: `${out}/native-zoom-${route}.png` });
    }
    fs.writeFileSync(`${out}/native-zoom.json`, JSON.stringify(evidence, null, 2));
    console.log('PASS native Chrome 200% zoom: actual browser setting, DPR verification and no page overflow in all four destinations.');
  } finally { await context.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
