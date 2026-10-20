// Sprint 12 / F04 regression: the common-window decision for multi-security
// comparison, including the QQQ/VALL unequal-history case and the EUR/SGD
// coverage gap. Deterministic: one fixture file, no network, no DOM.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {commonWindow, resolveWindow, securityWindow, windowsEqual} from './compare-window.js';

const fixture = JSON.parse(readFileSync(new URL('./fixtures/compare-window-qqq-vall.json', import.meta.url)));
const byTicker = new Map(fixture.securities.map(security => [security.ticker, security]));

function windowsFor(tickers) {
  return tickers.map(ticker => {
    const security = byTicker.get(ticker);
    assert(security, `fixture is missing ${ticker}`);
    return securityWindow({
      securityId: security.entry.security_id,
      currency: security.currency,
      entry: security.entry,
      fx: fixture.fx[security.currency] || null,
    });
  });
}

for (const testCase of fixture.cases) {
  const windows = windowsFor(testCase.securities);
  const common = commonWindow(windows);
  const expected = testCase.expected;

  if (expected.eurUnavailable) {
    const euro = windows.find(item => item.currency === 'EUR');
    assert.equal(euro.state, 'unavailable', `${testCase.name}: EURX must be unavailable`);
    assert.match(euro.reason, /exchange-rate history/);
  }
  if (expected.common) {
    assert.equal(common.start, expected.common.start, `${testCase.name}: common start`);
    assert.equal(common.end, expected.common.end, `${testCase.name}: common end`);
  }
  if (Object.hasOwn(expected, 'commonOk')) assert.equal(common.ok, expected.commonOk, `${testCase.name}: common.ok`);
  if (expected.limitingStart) {
    const tickersFor = (items) => items.map(item => testCase.securities.find(ticker => byTicker.get(ticker).entry.security_id === item.securityId));
    assert.deepEqual(tickersFor(common.limitingStart), expected.limitingStart, `${testCase.name}: limiting start`);
    assert.deepEqual(tickersFor(common.limitingEnd), expected.limitingEnd, `${testCase.name}: limiting end`);
  }
  const resolved = resolveWindow(testCase.requested, common);
  if (expected.resolved === null) {
    assert.equal(resolved.ok, false, `${testCase.name}: outside the shared window must not resolve`);
    assert.equal(resolved.truncated, expected.truncated, `${testCase.name}: truncated`);
    assert.match(resolved.reason, /outside the window/);
  } else if (expected.resolved) {
    assert.equal(resolved.ok, true, `${testCase.name}: resolved ok`);
    assert.equal(resolved.start, expected.resolved.start, `${testCase.name}: resolved start`);
    assert.equal(resolved.end, expected.resolved.end, `${testCase.name}: resolved end`);
    assert.equal(resolved.truncated, expected.truncated, `${testCase.name}: truncated`);
  }
  console.log(`PASS: ${testCase.name}`);
}

// The regression that fixes F04: an unequal-history pair never resolves to the
// requested window, and the shared window is attributed to the limiting
// securities so the UI can name them.
const unequal = windowsFor(['QQQ', 'VALL']);
const unequalCommon = commonWindow(unequal);
assert.equal(unequalCommon.start, '2018-02-15');
assert.equal(unequalCommon.end, '2026-08-28');
assert.equal(windowsEqual(unequal[0], unequal[1]), false);
const clamped = resolveWindow({start_date: '2010-01-01', end_date: '2026-08-28'}, unequalCommon);
assert.equal(clamped.start, '2018-02-15');
assert.equal(clamped.truncated, true);
console.log('PASS: qqq-vall-never-compared-on-requested-window');

// Equal periods stay equal after resolution, so the UI can say so truthfully.
const equal = windowsFor(['QQQ', 'QQQ']);
const equalResolved = resolveWindow({start_date: '2010-01-01', end_date: '2026-08-28'}, commonWindow(equal));
assert.equal(equalResolved.truncated, false);
assert.equal(windowsEqual({start: equalResolved.start, end: equalResolved.end}, {start: equalResolved.start, end: equalResolved.end}), true);
console.log('PASS: equal-windows-resolve-identically');

// No usable selection must never produce a window.
const blocked = resolveWindow({start_date: '2010-01-01', end_date: '2026-08-28'}, commonWindow(windowsFor(['EURX', 'EURX'])));
assert.equal(blocked.ok, false);
assert.match(blocked.reason, /no shared published window|usable/);
console.log('PASS: unusable-selection-never-resolves');

// Guardrails: invalid dates and inverted ranges are rejected before ranking.
assert.equal(resolveWindow({start_date: '2024-02-30', end_date: '2024-03-01'}, unequalCommon).ok, false);
assert.equal(resolveWindow({start_date: '2024-05-01', end_date: '2024-01-01'}, unequalCommon).ok, false);
assert.equal(resolveWindow({}, unequalCommon).ok, false);
console.log('PASS: invalid-and-inverted-requests-rejected');

// A security with no published dates cannot silently widen the common window.
const noDates = securityWindow({securityId: 'sec-empty', currency: 'USD', entry: {security_id: 'sec-empty', status: 'incomplete'}, fx: fixture.fx.USD});
assert.equal(noDates.state, 'unknown');
assert.equal(commonWindow([unequal[0], noDates]).ok, false);
console.log('PASS: missing-published-dates-excluded');

// FX limits are reported, not silently applied.
assert.equal(unequal[0].fxLimited, true, 'QQQ starts before USD/SGD coverage');
assert.equal(unequal[0].start, '2000-01-03');
console.log('PASS: fx-limit-is-explicit');

console.log('compare-window-selftest: all assertions passed');
