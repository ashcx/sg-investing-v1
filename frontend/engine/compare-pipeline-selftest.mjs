// Actual pack loader -> application envelope -> worker -> renderer. Offline.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { createPackLoader } from './pack-loader.js';
import { spawnEngineWorker } from './worker.node.mjs';
import { requestId } from './protocol.js';
import * as windows from './compare-window.js';
import { fixture, manifest, pack } from '../../tests/fixtures/redesign/sprint-12-packs.mjs';

const app = readFileSync(new URL('../app.js', import.meta.url), 'utf8');
const section = (start, end) => app.slice(app.indexOf(start), app.indexOf(end, app.indexOf(start)));
const fetcher = async url => {
  const remote = url.startsWith('remote:');
  if (url.endsWith('manifest.json')) return { ok: true, json: async () => manifest(remote) };
  const item = fixture.securities.find(item => url.includes(item.security.security_id));
  return { ok: Boolean(item), status: item ? 200 : 404, json: async () => pack(item) };
};
const worker = spawnEngineWorker();
const pending = new Map();
worker.on('message', message => {
  if (message.type !== 'result') return;
  const task = pending.get(message.id); if (!task) return;
  pending.delete(message.id);
  if (message.ok) task.resolve(message.result); else task.reject(new Error(message.error?.message));
});
const output = { innerHTML: '' };
const ctx = vm.createContext({ ...windows, console, Intl, dec: value => value,
  packs: createPackLoader({ baseUrl: 'local:', fetcher, taxRules: fixture.tax_rules }),
  packsRemote: createPackLoader({ baseUrl: 'remote:', fetcher, taxRules: fixture.tax_rules }),
  engineClient: { analyze(payload) {
    const id = requestId('analyze', payload);
    const promise = new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
    worker.postMessage({ type: 'request', id, scope: 'analyze', payload });
    return { id, promise };
  } },
  s6SeriesFromInputs: () => null, coverageFromInputs: () => ({}),
  s6EngineErrorMessage: error => error.message,
  $: () => output, entryForId: () => null, compareTickerFor: id => id,
  state: {}, COMPARE_SCENARIO_LABELS: { investor: 'Singapore investor' },
});
vm.runInContext(section('async function s8ResolveSecurity(', 'const s4State =')
  + section('async function s6AnalysisViaPacks(', 'function s6PackNotes(')
  + section('function s6PackNotes(', '// Mirror of scripts/frontend_server.py')
  + section('function escapeHtml(', 'function securityComboboxValue(')
  + section('function formatMoney(', 'function formatRate(')
  + section('function dividendCoverageNote(', 'async function loadJson(')
  + section('function compareStatus(', 'function renderComparePicker('), ctx);
try {
  for (const test of fixture.cases) {
    const item = fixture.securities.find(item => item.security.ticker === test.ticker);
    ctx.params = { securityId: item.security.security_id, initial_sgd: '1000', start_date: test.start, end_date: test.end,
      dividends: test.scenario.dividends_enabled, withholding: test.scenario.withholding_tax_enabled,
      reinvest: test.scenario.reinvest_dividends };
    const outcome = await vm.runInContext('s6AnalysisViaPacks(params)', ctx);
    const result = outcome.envelope.result;
    assert.equal(result.investment.final_value_sgd, test.expected.final_value_sgd);
    assert.equal(result.returns.total_return, test.expected.total_return);
    assert.deepEqual({ ...result.period }, { start_date: test.expected.start, end_date: test.expected.end });
    const row = windows.comparisonRow({ securityId: item.security.security_id }, outcome.envelope);
    assert.equal(row.state, 'ready');
    ctx.payload = { states: [row], requested: { start: test.start, end: test.end }, amount: '1000' };
    vm.runInContext('renderCompare(payload)', ctx);
    assert.match(output.innerHTML, /Synthetic Sprint 12 fixture/);
    assert.match(output.innerHTML, /s12-synthetic-2024/);
    assert.doesNotMatch(output.innerHTML, /<dd>—/);
    console.log(`PASS: actual pack/application/worker/card pipeline ${test.name}`);
  }
  // A reachable Tier-2 origin survives a missing Tier-1 manifest.
  ctx.packs = { async findSecurity() { throw new Error('Tier-1 manifest unavailable'); } };
  const remote = fixture.securities.find(item => item.security.ticker === 'REMOTE');
  ctx.params = { securityId: remote.security.security_id, initial_sgd: '1000', start_date: '2024-01-02', end_date: '2024-04-01', dividends: false };
  const outcome = await vm.runInContext('s6AnalysisViaPacks(params)', ctx);
  assert.equal(outcome.envelope.result.investment.final_value_sgd, '1800');
  console.log('PASS: actual origin resolver computes Tier-2 result when Tier-1 manifest fails');
} finally { await worker.terminate(); }
