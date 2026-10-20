// Execute the actual application boundary functions with controlled DOM/I/O
// adapters. This does not claim browser layout, focus or accessibility QA.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import * as windows from './compare-window.js';
import { analyzeSecurity } from './analysis.js';

const app = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
const fixture = JSON.parse(readFileSync(new URL('../../tests/fixtures/redesign/sprint-12.json', import.meta.url)));
const security = fixture.securities[0].security;
const elements = new Map();
function element(id, value = '') {
  const node = { value, textContent: '', innerHTML: '', hidden: true, focus() {},
    querySelector() { return { addEventListener() {} }; } };
  elements.set(id, node); return node;
}
['#compare-amount', '#compare-start', '#compare-end', '#compare-scenario', '#compare-ticker-chips', '#comparison-handoff-note'].forEach(id => element(id));
element('#initial-amount', '1000'); element('#dca-initial', '750'); element('#dca-contribution', '99');
element('#start-date', '2024-01-01'); element('#end-date', '2024-05-01');
element('#dca-start', '2001-01-01'); element('#dca-end', '2002-01-01');
const state = { compareTickers: [], simulatorMode: 'one-time' };
const scenario = { dividends: true, withholding: false, reinvest: true };
const ctx = vm.createContext({ ...windows, console, Intl, state, COMPARE_MIN: 2, COMPARE_MAX: 6,
  $: id => elements.get(id), entryForId: id => id === security.security_id ? { security } : null,
  securityComboboxValue: () => security.security_id, scenarioValues: () => scenario,
  editView() {}, saveComparisonDraft() {}, location: {},
  packs: { async loadManifest() { return { securities: [] }; } },
  packsRemote: { async loadManifest() { return { securities: [{ security_id: security.security_id,
    native_currency: 'USD', first_date: '2024-01-02', last_date: '2024-05-01', status: 'fully_supported' }],
    fx: { coverage: { USD: { first_date: '2024-01-02', last_date: '2024-05-01' } } } }; } },
});
const section = (start, end) => app.slice(app.indexOf(start), app.indexOf(end, app.indexOf(start)));
vm.runInContext(section('function escapeHtml(', 'function securityComboboxValue(')
  + section('function formatMoney(', 'function formatRate(')
  + section('const COMPARE_SCENARIO_LABELS', 'function compareStatus(')
  + section('function renderCompareChips(', 'function selectCompareSecurity(')
  + section('function copySimulatorToComparison(', 'function downloadCompleted('), ctx);
vm.runInContext('renderCompareChips()', ctx);
assert.equal((elements.get('#compare-ticker-chips').innerHTML.match(/data-add-comparison/g) || []).length, 2);
vm.runInContext('copySimulatorToComparison()', ctx);
assert.equal(elements.get('#compare-amount').value, '1000');
assert.equal(elements.get('#compare-start').value, '2024-01-01');
assert.equal(ctx.location.hash, 'compare');
assert.notEqual(state.compareCopiedScenario, scenario);
elements.get('#compare-amount').value = '3333';
assert.equal(elements.get('#initial-amount').value, '1000');
state.simulatorMode = 'regular'; ctx.location.hash = 'simulator';
vm.runInContext('copySimulatorToComparison()', ctx);
assert.equal(ctx.location.hash, 'simulator');
assert.equal(elements.get('#compare-amount').value, '3333');
assert.match(elements.get('#comparison-handoff-note').innerHTML, /recurring contributions are excluded/);
vm.runInContext('copySimulatorToComparison({asOneTime:true})', ctx);
assert.equal(elements.get('#compare-amount').value, '750');
assert.equal(elements.get('#compare-start').value, '2024-01-01');
assert.equal(elements.get('#compare-end').value, '2024-05-01');
assert.equal(elements.get('#dca-contribution').value, '99');
const coverage = await vm.runInContext(`loadComparisonCoverage('${security.security_id}')`, ctx);
assert.equal(coverage.state, 'ready');
assert.equal(coverage.origin, 'External data origin');
console.log('PASS: two empty slots; isolated one-time handoff; explicit regular initial-only choice; shared simulator dates; Tier-2 coverage');

element('#compare-results'); element('#compare-progress');
vm.runInContext(section('function dividendCoverageNote(', 'async function loadJson(')
  + section('function compareStatus(', 'function renderComparePicker('), ctx);
const golden = JSON.parse(readFileSync(new URL('./fixtures/analysis-qqq-2024h1.json', import.meta.url)));
const ready = windows.comparisonRow({ securityId: golden.security.security_id, ticker: 'QQQ' },
  { data_snapshot_id: 's12-render-fixed', methodology_version: '1.0', result: golden });
const render = states => {
  ctx.payload = { states, requested: { start: '2024-01-01', end: '2024-07-01' }, amount: '10000', scenarioLabel: 'Singapore investor' };
  vm.runInContext('renderCompare(payload)', ctx);
  return elements.get('#compare-results').innerHTML;
};
let html = render([ready, { securityId: 'failed', ticker: 'FAILED', state: 'failed', reason: '<unsafe error>' }]);
assert.match(html, /S\$12,303\.27/);
assert.match(html, /\+23\.03%/);
assert.match(html, /\+19\.82%/);
assert.match(html, /Native total return · USD/);
assert.match(html, /5 warnings/);
assert.match(html, /Approximated dividend pay date/);
assert.match(html, /s12-render-fixed/);
assert.match(html, /Partial results/);
assert.doesNotMatch(html, /Equal actual periods/);
assert.match(html, /&lt;unsafe error&gt;/);
const metrics = [...html.matchAll(/<div class="compare-metric[^]*?<\/div>/g)].map(match => match[0]);
assert.equal(metrics.length, 3);
for (const metric of metrics) {
  assert.match(metric, /<dt>[^<]*(SGD|USD)/);
  assert.match(metric, /class="metric-period">2024-01-02 → 2024-07-01/);
}
html = render([ready, { ...ready, securityId: 'another' }]);
assert.match(html, /Equal actual periods/);
html = render([ready, { ...ready, securityId: 'another', snapshotId: null }]);
assert.match(html, /could not be verified/);
html = render([{ state: 'unavailable', ticker: 'NOFX', securityId: 'no-fx', reason: 'No FX' }]);
assert.match(html, /No results calculated/);
assert.doesNotMatch(html, /Equal actual periods|Data quality OK/);
console.log('PASS: actual renderer preserves golden financial values, actual dates per metric, five warning details, source metadata, partial/empty states and escaped errors');

// Exercise the actual async submission and result-state code, including late
// responses. No browser or network is used by this controller contract test.
const button = { dataset: {}, innerHTML: 'Calculate', textContent: 'Calculate', disabled: false };
const form = { dataset: {}, querySelector: () => button };
const notice = element('#compare-request-state'); notice.dataset = {};
element('#compare-error');
ctx.PRESETS = { investor: { dividends: true, withholding: true, reinvest: true },
  price: { dividends: false, withholding: false, reinvest: false } };
ctx.API_BASE = '';
ctx.resultViews = { compare: { phase: 'empty', request: null, artifact: null } };
ctx.s6Runs = { compare: 0 }; ctx.s4State = {};
ctx.s7CancelAutoRun = () => {}; ctx.has = () => false;
ctx.viewForm = () => form;
ctx.setBusy = (_button, busy) => { button.disabled = busy; };
ctx.s6SetButtonProgress = () => {};
ctx.setComputeMode = () => {};
ctx.s6RunCurrent = (kind, seq) => ctx.s6Runs[kind] === seq;
ctx.entryForId = id => {
  const item = fixture.securities.find(item => item.security.security_id === id);
  return item ? { security: item.security } : null;
};
const entries = fixture.securities.map(item => ({ security_id: item.security.security_id,
  ticker: item.security.ticker, native_currency: item.security.currency,
  first_date: item.prices[0].trading_date, last_date: item.prices.at(-1).trading_date, status: 'fully_supported' }));
const fx = { coverage: { USD: { first_date: '2024-01-02', last_date: '2024-05-01' } } };
ctx.packs.loadManifest = async () => ({ securities: entries.filter(item => item.ticker !== 'REMOTE'), fx });
ctx.packsRemote.loadManifest = async () => ({ securities: entries.filter(item => item.ticker === 'REMOTE'), fx });
vm.runInContext(section('function viewSummary(', 'function viewForm(')
  + section('function renderViewState(', 'function analysisLink(')
  + section('async function submitCompare(', 'function renderDca('), ctx);
let calls = [];
let hold = null;
ctx.s6AnalysisViaPacks = async params => {
  calls.push({ ...params });
  if (hold) { const pending = hold; hold = null; await pending; }
  const item = fixture.securities.find(item => item.security.security_id === params.securityId);
  if (item.security.ticker === 'BROKEN') throw new Error('Fixture pack fetch failed');
  const result = analyzeSecurity({ security: item.security, prices: item.prices, fxRates: item.fx_rates,
    startDate: params.start_date, endDate: params.end_date, initialSgd: params.initial_sgd,
    scenario: { dividends_enabled: params.dividends, withholding_tax_enabled: params.withholding,
      reinvest_dividends: params.reinvest }, dividends: item.dividends, taxRules: fixture.tax_rules });
  return { envelope: { result: JSON.parse(JSON.stringify(result)), data_snapshot_id: 'controller-s12', methodology_version: '1.0' } };
};
ctx.event = { preventDefault() {}, currentTarget: form };
const ids = fixture.securities.map(item => item.security.security_id);
const submit = () => vm.runInContext('submitCompare(event)', ctx);
elements.get('#compare-amount').value = '1000';
elements.get('#compare-start').value = '2024-01-01';
elements.get('#compare-end').value = '2024-05-01';
elements.get('#compare-scenario').value = 'price';
state.compareTickers = [ids[0], ids[2]];
await submit();
assert.equal(ctx.resultViews.compare.phase, 'current');
assert.equal(ctx.resultViews.compare.artifact.states.length, 2);
assert.match(notice.textContent, /Current result/);
assert.match(elements.get('#compare-results').innerHTML, /Equal actual periods/);
state.compareTickers = ids;
await submit();
assert.equal(ctx.resultViews.compare.artifact.states.length, 6);
assert.equal(ctx.resultViews.compare.artifact.states.filter(row => row.state === 'ready').length, 4);
assert.match(elements.get('#compare-results').innerHTML, /4 of 6 securities calculated/);
assert.equal(ctx.resultViews.compare.artifact.states[4].state, 'unavailable');
assert.equal(ctx.resultViews.compare.artifact.states[5].state, 'failed');
const completed = elements.get('#compare-results').innerHTML;
const completedArtifact = ctx.resultViews.compare.artifact;
state.compareTickers = [ids[0], ids[0]];
const beforeInvalid = calls.length;
await submit();
assert.equal(ctx.resultViews.compare.phase, 'invalid');
assert.equal(calls.length, beforeInvalid);
assert.equal(elements.get('#compare-results').innerHTML, completed);
for (const value of ['0', '-1', 'Infinity', 'NaN']) {
  state.compareTickers = [ids[0], ids[2]]; elements.get('#compare-amount').value = value;
  await submit(); assert.equal(ctx.resultViews.compare.phase, 'invalid');
}
elements.get('#compare-amount').value = '1000';
elements.get('#compare-start').value = '2024-06-01';
await submit(); assert.equal(ctx.resultViews.compare.phase, 'invalid');
elements.get('#compare-start').value = '2024-01-01';
state.compareTickers = [ids[4], ids[5]];
await submit();
assert.equal(ctx.resultViews.compare.phase, 'failed');
assert.equal(ctx.resultViews.compare.artifact, completedArtifact);
assert.equal(elements.get('#compare-results').innerHTML, completed);
assert.match(notice.textContent, /Previous result/);
assert.match(elements.get('#compare-progress').innerHTML, /No results calculated/);
let release;
hold = new Promise(resolve => { release = resolve; });
state.compareTickers = [ids[0], ids[2]];
const oldCount = calls.length;
const stale = submit();
while (calls.length === oldCount) await new Promise(resolve => setImmediate(resolve));
assert.equal(elements.get('#compare-results').innerHTML, completed);
vm.runInContext("editView('compare')", ctx);
assert.equal(elements.get('#compare-progress').innerHTML, '');
assert.match(notice.textContent, /Previous result/);
elements.get('#compare-amount').value = '2000';
state.compareTickers = [ids[2], ids[0]];
await submit();
release(); await stale;
assert.equal(ctx.resultViews.compare.request.initial_sgd, '2000');
assert.equal(ctx.resultViews.compare.artifact.states[0].securityId, ids[2]);
assert.equal(elements.get('#compare-progress').innerHTML, '');
assert.equal(button.disabled, false);
assert.match(notice.textContent, /Current result.*2000 SGD initial/);
assert.equal(calls.filter(call => call.initial_sgd === '1000').length, oldCount + 1);
console.log('PASS: actual controller handles 2–6 entries, unavailable/failed rows, invalid capital/dates/duplicates, retained prior output, edits/reordering and late-response rejection');

ctx.API_BASE = 'reference-adapter';
const adapterCalls = [];
ctx.apiGet = async (endpoint, params) => {
  adapterCalls.push({ endpoint, ...params });
  if (params.security_id === ids[2]) throw new Error('Adapter unavailable for ES3');
  return (await ctx.s6AnalysisViaPacks({ securityId: params.security_id, ...params })).envelope;
};
state.compareTickers = [ids[0], ids[2]];
await submit();
assert.equal(ctx.resultViews.compare.phase, 'current');
assert.equal(adapterCalls.length, 2);
assert(adapterCalls.every(call => call.endpoint === '/analyze' && call.security_id));
assert.equal(ctx.resultViews.compare.artifact.states[0].source, 'Python adapter');
assert.match(ctx.resultViews.compare.artifact.states[1].source, /adapter unavailable/);
console.log('PASS: adapter requests use stable security IDs and per-security local fallback preserves valid alternatives');
