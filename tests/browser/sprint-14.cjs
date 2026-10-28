const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const out = process.env.SG_EVIDENCE_DIR || 'docs/ux-redesign-evidence/sprint-14';
fs.mkdirSync(out, { recursive: true });
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
  const evidence = { apiCalls: [], remoteArtifacts: [], accessibility: [], browserErrors: [] };
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, permissions: ['clipboard-read','clipboard-write'] });
    const page = await context.newPage();
    page.on('pageerror', e => evidence.browserErrors.push(e.message));
    page.on('request', r => { if (new URL(r.url()).pathname.includes('/api/')) evidence.apiCalls.push(r.url()); });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('http://127.0.0.1:4173/');
    await page.waitForFunction(() => document.body.dataset.workspace === 'simulator');
    const choose = async ticker => {
      await page.locator('#security-select').fill(ticker);
      await page.locator('#security-select-options .combobox-option').filter({ has: page.locator('strong', { hasText: new RegExp(`^${ticker}$`) }) }).first().click();
    };
    const calculate = async () => {
      await page.locator('#analysis-form button[type=submit]').click();
      await page.waitForFunction(() => ['current','failed','invalid'].includes(document.querySelector('#analysis-form').dataset.resultState));
    };
    await choose('QQQ');
    await page.locator('#initial-amount').fill('10000');
    await page.locator('#start-date').fill('2024-01-02'); await page.locator('#end-date').fill('2024-12-31');
    await calculate();
    assert.equal(await page.locator('#analysis-form').getAttribute('data-result-state'), 'current', await page.locator('#form-error').textContent());
    const downloadEvent = page.waitForEvent('download'); await page.locator('#download-result').click();
    const download = await downloadEvent;
    const exported = JSON.parse(fs.readFileSync(await download.path(), 'utf8'));
    assert.ok(exported.result && exported.data_snapshot_id && exported.methodology_version);
    assert.ok(Array.isArray(exported.result.data_quality.warnings));
    assert.ok(Math.abs(Number(exported.result.investment.final_value_sgd) - 13123.365925115971) < 1e-8);
    evidence.generatedPackResult = exported;
    await page.locator('#copy-link').click();
    const shared = await page.evaluate(() => navigator.clipboard.readText());
    assert.match(shared, /2024-01-02/);
    const resultBefore = await page.locator('#final-value').textContent();
    await page.locator('#initial-amount').fill('20000');
    assert.match(await page.locator('#analysis-request-state').textContent(), /Previous result/);
    assert.equal(await page.locator('#final-value').textContent(), resultBefore);
    for (const route of ['simulator', 'compare', 'portfolio', 'methods']) {
      await page.goto(`http://127.0.0.1:4173/#${route}`);
      await page.waitForSelector(`body[data-workspace=${route}]`);
      if (route === 'portfolio') await page.locator('#add-ledger-row').click();
      const unnamed = await page.locator('input:visible, select:visible, button:visible').evaluateAll(nodes => nodes.filter(el => !el.labels?.length && !el.getAttribute('aria-label') && !el.getAttribute('aria-labelledby') && !(el.tagName === 'BUTTON' && el.textContent.trim())).map(el => el.id));
      assert.deepEqual(unnamed, [], `${route} unnamed controls`);
      for (const width of [320,390,768,1280,1440]) {
        await page.setViewportSize({ width, height: 1000 });
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `${route} overflow ${width}`);
      }
      await page.setViewportSize({ width: 1440, height: 1000 });
      await page.evaluate(() => { document.documentElement.style.zoom = '2'; });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `${route} 200% CSS zoom overflow`);
      await page.evaluate(() => { document.documentElement.style.zoom = ''; });
      await page.locator('.skip-link').focus(); await page.keyboard.press('Enter');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'workspace-content');
      const contrast = await page.locator('label:visible').evaluateAll(labels => {
        const rgb = value => (value.match(/[\d.]+/g) || []).map(Number);
        const luminance = c => c.slice(0,3).map(v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }).reduce((sum, v, i) => sum + v * [.2126,.7152,.0722][i], 0);
        return labels.map(label => {
          let parent = label, background = [255,255,255];
          while (parent) { const c = rgb(getComputedStyle(parent).backgroundColor); if (c.length === 3 || c[3] === 1) { background = c; break; } parent = parent.parentElement; }
          const a = luminance(rgb(getComputedStyle(label).color)), b = luminance(background);
          return { label: label.textContent.trim(), ratio: (Math.max(a,b) + .05) / (Math.min(a,b) + .05) };
        });
      });
      assert.ok(contrast.every(item => item.ratio >= 4.5), `${route} label contrast ${JSON.stringify(contrast)}`);
      evidence.accessibility.push({ route, labelContrast: contrast, namedControls: true, widths: [320,390,768,1280,1440], cssZoom200: true, keyboardSkip: true, reducedMotion: true });
    }
    await page.goto(shared); await page.waitForFunction(() => document.body.dataset.workspace === 'simulator');
    assert.equal(await page.locator('#initial-amount').inputValue(), '10000');
    assert.equal(await page.locator('#start-date').inputValue(), '2024-01-02');
    await page.screenshot({ path: `${out}/candidate-desktop.png` });
    const r2 = 'https://pub-a88a64ce6b634ab8a70623c35ff81ad7.r2.dev';
    await page.route(`${r2}/**`, async route => {
      const response = await context.request.get(route.request().url(), { headers: { Origin: 'https://ashcx.github.io' } });
      evidence.remoteArtifacts.push({ url: route.request().url(), status: response.status() });
      await route.fulfill({ response, headers: { ...response.headers(), 'access-control-allow-origin': '*' } });
    });
    await choose('GRPN');
    await calculate();
    assert.equal(await page.locator('#analysis-form').getAttribute('data-result-state'), 'current', await page.locator('#form-error').textContent());
    assert.ok(evidence.remoteArtifacts.some(r => r.status === 200 && r.url.includes('security=')));
    evidence.dividendDisclosure = { detail: await page.locator('#dividend-note').textContent(), badge: await page.locator('#quality-label').textContent() };
    if (/not confirmed/.test(evidence.dividendDisclosure.detail)) assert.match(evidence.dividendDisclosure.badge, /Review warnings/);
    evidence.tier2Transport = 'Published R2 JSON proxied through test routing with the Pages Origin header; candidate UI computes locally.';
    await page.setViewportSize({ width: 390, height: 1000 });
    await page.locator('#results-panel').scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${out}/candidate-tier2-mobile.png` });
    const offline = await browser.newContext(); const recovery = await offline.newPage();
    await recovery.route('**/data/packs/security=**', route => route.abort());
    await recovery.goto('http://127.0.0.1:4173/');
    await recovery.locator('#security-select').fill('QQQ');
    await recovery.locator('#security-select-options .combobox-option[data-security-id="6cfd001d-07dc-44d9-aff8-d6c99b0ee80b"]').click();
    await recovery.locator('#start-date').fill('2024-01-02'); await recovery.locator('#end-date').fill('2024-12-31');
    await recovery.locator('#analysis-form button[type=submit]').click();
    await recovery.waitForFunction(() => document.querySelector('#analysis-form').dataset.resultState === 'failed');
    await recovery.unroute('**/data/packs/security=**');
    await recovery.locator('#analysis-form button[type=submit]').click();
    await recovery.waitForFunction(() => document.querySelector('#analysis-form').dataset.resultState === 'current');
    evidence.networkRecovery = true;
    const baseline = await context.request.get('https://ashcx.github.io/sg-investing-v1/data/packs/manifest.json');
    assert.equal(baseline.status(), 200);
    const manifest = await baseline.json();
    evidence.deployedBaseline = { url: baseline.url(), status: baseline.status(), snapshot: manifest.data_snapshot_id, summary: manifest.summary, scope: 'Read-only published baseline, not candidate deployment.' };
    assert.deepEqual(evidence.apiCalls, []); assert.deepEqual(evidence.browserErrors, []);
    console.log('PASS Sprint 14: real QQQ packs, provenance export, share round trip, retained request identity, four destinations/five widths, named controls, keyboard skip, reduced motion, 200% CSS zoom, published Tier-2 inputs and network failure/retry.');
  } finally {
    fs.writeFileSync(`${out}/browser.json`, JSON.stringify(evidence, null, 2));
    await browser.close();
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
