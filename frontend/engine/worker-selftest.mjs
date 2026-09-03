import { readFileSync } from 'node:fs';
import { setTimeout as delay } from 'node:timers/promises';

import {
  ERROR_CODES,
  REQUEST_STATES,
  createCancelled,
  createError,
  createProgress,
  createRequest,
  createRequestTracker,
  createResult,
  requestId,
} from './protocol.js';
import { requestKey } from './request-keys.js';
import { createEngineHost } from './worker.js';
import { analyzePortfolio, analyzeSecurity, dcaAnalysis } from './index.js';
import { payloadToEngineArgs } from './worker.js';
import { spawnEngineWorker } from './worker.node.mjs';

const results = { pass: 0, fail: 0 };
const failures = [];

function check(name, condition, detail) {
  if (condition) {
    results.pass += 1;
  } else {
    results.fail += 1;
    failures.push({ name, detail });
    console.log(`  FAIL ${name}${detail === undefined ? '' : ` :: ${detail}`}`);
  }
}

function checkEqual(name, actual, expected) {
  const a = typeof actual === 'object' && actual !== null ? JSON.stringify(actual) : String(actual);
  const e = typeof expected === 'object' && expected !== null ? JSON.stringify(expected) : String(expected);
  check(name, a === e, a === e ? undefined : `expected ${e}, got ${a}`);
}

function section(title) {
  console.log(`\n== ${title}`);
}

const FIXTURES = new URL('./fixtures/', import.meta.url);
const loadFixture = (name) => JSON.parse(readFileSync(new URL(name, FIXTURES), 'utf8'));
const INPUTS = loadFixture('inputs-qqq-2024h1.json');

function fixturePayload(scope) {
  if (scope === 'analyze') {
    return {
      security: INPUTS.security,
      prices: INPUTS.prices,
      fx_rates: INPUTS.fx_rates,
      start_date: INPUTS.analysis_request.start_date,
      end_date: INPUTS.analysis_request.end_date,
      initial_sgd: INPUTS.analysis_request.initial_sgd,
      scenario: INPUTS.analysis_request.scenario,
      dividends: INPUTS.dividends,
      corporate_actions: INPUTS.corporate_actions,
      tax_rules: INPUTS.tax_rules,
    };
  }
  if (scope === 'dca') {
    return {
      security: INPUTS.security,
      prices: INPUTS.prices,
      fx_rates: INPUTS.fx_rates,
      start_date: INPUTS.dca_request.start_date,
      end_date: INPUTS.dca_request.end_date,
      contribution_sgd: INPUTS.dca_request.contribution_sgd,
      frequency: INPUTS.dca_request.frequency,
      scenario: INPUTS.dca_request.scenario,
      dividends: INPUTS.dividends,
      corporate_actions: INPUTS.corporate_actions,
      tax_rules: INPUTS.tax_rules,
    };
  }
  return {
    transactions: INPUTS.portfolio_request.transactions,
    securities: { [INPUTS.security.security_id]: INPUTS.security },
    prices: INPUTS.prices,
    fx_rates: INPUTS.fx_rates,
    as_of: INPUTS.portfolio_request.as_of,
  };
}

const US_TAX_RULE = {
  rule_id: 'US_DIVIDEND_NONRESIDENT',
  source_country: 'US',
  income_type: 'dividend',
  investor_type: 'singapore_individual',
  rate: '0.30',
  effective_from: '1900-01-01',
  effective_to: null,
};

function formatDate(ms) {
  return new Date(ms).toISOString().slice(0, 10);
}

function buildSyntheticData({ years }) {
  const security = {
    security_id: 'synthetic-large-0001',
    ticker: 'SYN',
    exchange: 'NASDAQ',
    market: 'US',
    name: 'Synthetic Large Range',
    currency: 'USD',
    asset_type: 'ETF',
    domicile: 'US',
    income_source_country: 'US',
    isin: null,
    cusip: null,
    timezone: 'America/New_York',
    active: true,
    distribution_policy: 'distributing',
    expense_ratio: null,
  };
  const start = Date.UTC(1980, 0, 2);
  const end = Date.UTC(1980 + years, 0, 2);
  const prices = [];
  const fxRates = [];
  const dividends = [];
  let day = start;
  let i = 0;
  let nextFxMonth = -1;
  let nextDivQuarter = -1;
  while (day < end) {
    const date = new Date(day);
    const dow = date.getUTCDay();
    if (dow !== 0 && dow !== 6) {
      prices.push({
        security_id: security.security_id,
        trading_date: formatDate(day),
        close: (1000 + i * 0.01).toFixed(6),
        currency: 'USD',
      });
      const monthIndex = date.getUTCFullYear() * 12 + date.getUTCMonth();
      if (monthIndex > nextFxMonth) {
        nextFxMonth = monthIndex;
        fxRates.push({
          rate_date: formatDate(day),
          base_currency: 'USD',
          rate_to_sgd: (1.3 + (monthIndex % 96) * 0.001).toFixed(6),
        });
      }
      const quarterIndex = date.getUTCFullYear() * 4 + Math.floor(date.getUTCMonth() / 3);
      if (quarterIndex > nextDivQuarter) {
        nextDivQuarter = quarterIndex;
        dividends.push({
          security_id: security.security_id,
          ex_date: formatDate(day),
          amount: '0.500000',
          currency: 'USD',
          pay_date: formatDate(day + 14 * 86400000),
          dividend_type: 'regular',
          source_country: 'US',
        });
      }
      i += 1;
    }
    day += 86400000;
  }
  return { security, prices, fxRates, dividends };
}

function syntheticPayload(scope, { years, frequency = 'monthly' } = {}) {
  const { security, prices, fxRates, dividends } = buildSyntheticData({ years });
  const startDate = prices[0].trading_date;
  const endDate = prices[prices.length - 1].trading_date;
  if (scope === 'analyze') {
    return {
      security,
      prices,
      fx_rates: fxRates,
      start_date: startDate,
      end_date: endDate,
      initial_sgd: '10000',
      scenario: { dividends_enabled: true, reinvest_dividends: true, withholding_tax_enabled: true },
      dividends,
      corporate_actions: [],
      tax_rules: [US_TAX_RULE],
    };
  }
  return {
    security,
    prices,
    fx_rates: fxRates,
    start_date: startDate,
    end_date: endDate,
    contribution_sgd: '1000',
    frequency,
    scenario: { dividends_enabled: true, reinvest_dividends: true, withholding_tax_enabled: true },
    dividends,
    corporate_actions: [],
    tax_rules: [US_TAX_RULE],
  };
}

function serializeForComparison(envelope) {
  return JSON.parse(JSON.stringify(envelope));
}

const clients = new Set();

class WorkerClient {
  constructor({ label, yieldMs = 0, debug = false } = {}) {
    this.label = label;
    this.received = [];
    this.waiters = [];
    this.staleEvents = [];
    this.workerErrors = [];
    this.exited = false;
    this.tracker = createRequestTracker({
      onStale: (envelope, info) => {
        this.staleEvents.push({ id: envelope?.id ?? null, reason: info.reason });
      },
    });
    this.exitPromise = new Promise((resolve) => {
      this.resolveExit = resolve;
    });
    this.worker = spawnEngineWorker({ debug, yieldMs });
    clients.add(this);
    this.worker.on('message', (envelope) => {
      this.received.push(envelope);
      this.tracker.observe(envelope);
      this.flushWaiters();
    });
    this.worker.on('error', (error) => {
      this.workerErrors.push(error);
      this.flushWaiters();
    });
    this.worker.on('exit', () => {
      this.exited = true;
      this.resolveExit();
      this.flushWaiters();
    });
  }

  sendRequest(scope, payload) {
    const envelope = createRequest(scope, payload);
    this.tracker.track(envelope);
    this.worker.postMessage(envelope);
    return envelope.id;
  }

  cancel(id) {
    this.tracker.markCancelled(id);
    this.worker.postMessage({ type: 'cancel', id });
  }

  envelopesFor(id) {
    return this.received.filter((envelope) => envelope.id === id);
  }

  resultFor(id) {
    return this.received.find((envelope) => envelope.id === id && envelope.type === 'result' && envelope.ok === true) ?? null;
  }

  errorFor(id) {
    return this.received.find((envelope) => envelope.id === id && envelope.type === 'result' && envelope.ok === false) ?? null;
  }

  cancelledFor(id) {
    return this.received.find((envelope) => envelope.id === id && envelope.type === 'cancelled') ?? null;
  }

  async waitFor(predicate, { timeoutMs = 20000, label = 'envelope' } = {}) {
    const evaluate =
      predicate.length > 0
        ? () => this.received.find(predicate)
        : () => predicate();
    const found = evaluate();
    if (found) return found;
    return new Promise((resolve, reject) => {
      const waiter = { evaluate, resolve };
      this.waiters.push(waiter);
      const timer = setTimeout(() => {
        const index = this.waiters.indexOf(waiter);
        if (index >= 0) this.waiters.splice(index, 1);
        reject(new Error(`timeout (${timeoutMs}ms) waiting for ${label}`));
      }, timeoutMs);
      waiter.fail = (error) => {
        clearTimeout(timer);
        reject(error);
      };
    });
  }

  flushWaiters() {
    for (const waiter of [...this.waiters]) {
      if (this.workerErrors.length) {
        this.waiters.splice(this.waiters.indexOf(waiter), 1);
        waiter.fail(this.workerErrors[0]);
        continue;
      }
      if (this.exited) {
        this.waiters.splice(this.waiters.indexOf(waiter), 1);
        waiter.fail(new Error('worker exited while waiting for envelope'));
        continue;
      }
      const found = waiter.evaluate();
      if (found) {
        this.waiters.splice(this.waiters.indexOf(waiter), 1);
        waiter.resolve(found);
      }
    }
  }

  async terminate() {
    if (!this.exited) {
      await this.worker.terminate();
      await this.exitPromise;
    }
    clients.delete(this);
  }
}

async function runParityViaWorker(scope, payload) {
  const client = new WorkerClient({ label: `parity-${scope}` });
  try {
    const id = client.sendRequest(scope, payload);
    const resultEnvelope = await client.waitFor(
      (envelope) => envelope.id === id && envelope.type === 'result' && envelope.ok === true,
      { label: `${scope} result` },
    );
    const direct = ENGINE_DIRECT[scope](payloadToEngineArgs(scope, payload));
    return {
      workerJson: JSON.stringify(resultEnvelope.result),
      directJson: JSON.stringify(serializeForComparison(direct)),
      stages: client.envelopesFor(id).map((envelope) => envelope.type === 'progress' ? envelope.stage : envelope.type),
      client,
    };
  } finally {
    await client.terminate();
  }
}

const ENGINE_DIRECT = { analyze: analyzeSecurity, dca: dcaAnalysis, portfolio: analyzePortfolio };

let longDcaPayload = null;
let longDcaComputeMs = 0;

async function main() {
  section('Protocol units (request tracker, envelope factories, stale guard)');
  {
    const payload = fixturePayload('analyze');
    checkEqual('createRequest id derives from requestKey(scope, payload)', createRequest('analyze', payload).id, requestKey('analyze', payload));
    const shuffled = {
      tax_rules: payload.tax_rules,
      dividends: payload.dividends,
      corporate_actions: payload.corporate_actions,
      scenario: payload.scenario,
      initial_sgd: payload.initial_sgd,
      end_date: payload.end_date,
      start_date: payload.start_date,
      fx_rates: payload.fx_rates,
      prices: payload.prices,
      security: payload.security,
    };
    checkEqual('identical payload in different key order maps to the same id', requestKey('analyze', shuffled), requestKey('analyze', payload));
    check('different scopes never share an id namespace', requestKey('analyze', payload) !== requestKey('dca', payload));

    const tracker = createRequestTracker();
    const request = createRequest('dca', fixturePayload('dca'));
    const record = tracker.track(request);
    checkEqual('tracked request starts pending', record.state, REQUEST_STATES.PENDING);
    checkEqual('re-tracking an active request dedupes', tracker.track(request), record);
    tracker.markRunning(request.id);
    checkEqual('markRunning transitions to running', tracker.stateOf(request.id), REQUEST_STATES.RUNNING);
    const progress = tracker.observe(createProgress(request.id, 'computing', 0, 1));
    check('progress for a running request is delivered', progress.delivered === true && progress.stale === false);
    const delivered = tracker.observe(createResult(request.id, { final_value_sgd: '123' }));
    check('result resolves the request', delivered.delivered === true && record.state === REQUEST_STATES.SUCCEEDED);
    const duplicate = tracker.observe(createResult(request.id, { final_value_sgd: '123' }));
    check('duplicate result for a resolved id is stale', duplicate.stale === true && duplicate.reason === 'terminal_request');
    checkEqual('state of resolved request stays succeeded', tracker.stateOf(request.id), REQUEST_STATES.SUCCEEDED);

    const staleTracker = createRequestTracker();
    const cancelRequest = createRequest('analyze', { ...fixturePayload('analyze'), initial_sgd: '77' });
    staleTracker.track(cancelRequest);
    staleTracker.markCancelled(cancelRequest.id);
    const lateResult = staleTracker.observe(createResult(cancelRequest.id, { final_value_sgd: '1' }));
    check('late result for a cancelled id is flagged stale', lateResult.stale === true && lateResult.reason === 'cancelled_request');
    check('late result is ignored (state stays cancelled)', staleTracker.stateOf(cancelRequest.id) === REQUEST_STATES.CANCELLED);
    const lateError = staleTracker.observe(createError(cancelRequest.id, ERROR_CODES.INTERNAL, 'boom'));
    check('late error for a cancelled id is flagged stale too', lateError.stale === true);
    const unknown = staleTracker.observe(createResult('analyze:0000000000000000', {}));
    check('result for an untracked id is stale', unknown.stale === true && unknown.reason === 'unknown_id');
    const lateProgress = staleTracker.observe(createProgress(cancelRequest.id, 'computing'));
    check('progress for a cancelled id is stale', lateProgress.stale === true);
    const cancelConfirmation = staleTracker.observe(createCancelled(cancelRequest.id));
    check('cancelled envelope after local cancel is an idempotent confirmation', cancelConfirmation.delivered === true && cancelConfirmation.stale === false);
    const foreign = staleTracker.observe({ type: 'hello', id: 'x' });
    check('foreign envelope type is stale', foreign.stale === true);

    const supersedeTracker = createRequestTracker();
    const supersededRequest = createRequest('analyze', { ...fixturePayload('analyze'), initial_sgd: '11' });
    const keepRequest = createRequest('analyze', { ...fixturePayload('analyze'), initial_sgd: '22' });
    supersedeTracker.track(supersededRequest);
    supersedeTracker.track(keepRequest);
    supersedeTracker.markRunning(supersededRequest.id);
    const supersededIds = supersedeTracker.supersedeScope('analyze', keepRequest.id);
    checkEqual('supersedeScope supersedes the older request', supersededIds, [supersededRequest.id]);
    const supersededResult = supersedeTracker.observe(createResult(supersededRequest.id, {}));
    check('result for a superseded id is stale', supersededResult.stale === true && supersededResult.reason === 'superseded_request');
    check('kept request is untouched', supersedeTracker.stateOf(keepRequest.id) === REQUEST_STATES.PENDING);
    checkEqual('activeInScope only lists the kept request', supersedeTracker.activeInScope('analyze').map((r) => r.id), [keepRequest.id]);

    const cancelledErrorConfirmation = createRequestTracker();
    const confirmRequest = createRequest('dca', { ...fixturePayload('dca'), contribution_sgd: '50' });
    cancelledErrorConfirmation.track(confirmRequest);
    cancelledErrorConfirmation.markCancelled(confirmRequest.id);
    const confirmed = cancelledErrorConfirmation.observe(
      createError(confirmRequest.id, ERROR_CODES.CANCELLED, 'Calculation cancelled.'),
    );
    check('cancelled error envelope on a cancelled id is a confirmation, not stale', confirmed.delivered === true && confirmed.stale === false);
  }

  section('S6: native tracker nextId(scope, payload) (additive reconciliation)');
  {
    const tracker = createRequestTracker();
    const payload = fixturePayload('analyze');
    const id = tracker.nextId('analyze', payload);
    checkEqual('nextId mints requestKey(scope, payload)', id, requestKey('analyze', payload));
    checkEqual('nextId tracks the minted id as pending', tracker.stateOf(id), REQUEST_STATES.PENDING);
    const delivered = tracker.observe(createResult(id, { final_value_sgd: '12345' }));
    check('result for a nextId-tracked id is delivered (stale guard sees the request)', delivered.delivered === true && delivered.stale === false);

    const sameAgain = tracker.nextId('analyze', payload);
    check('re-minting an identical (scope, payload) returns the same id', sameAgain === id);

    const other = tracker.nextId('analyze', { ...payload, initial_sgd: '4242' });
    check('a different payload mints a different id in the same scope', other !== id);
    const dcaId = tracker.nextId('dca', fixturePayload('dca'));
    check('a different scope mints an id outside the analyze namespace', dcaId !== id && dcaId !== other);

    const supersededIds = tracker.supersedeScope('analyze', other);
    checkEqual('supersedeScope supersedes the older nextId-tracked request', supersededIds, [id]);
    const staleLateResult = tracker.observe(createResult(id, { final_value_sgd: '1' }));
    check('late result for a superseded nextId-tracked id is stale', staleLateResult.stale === true && staleLateResult.reason === 'superseded_request');
    check('kept nextId-tracked request is untouched', tracker.stateOf(other) === REQUEST_STATES.PENDING);
  }

  section('Parity: worker result envelopes equal in-thread engine envelopes');
  {
    for (const scope of ['analyze', 'dca', 'portfolio']) {
      const payload = fixturePayload(scope);
      const { workerJson, directJson, stages, client } = await runParityViaWorker(scope, payload);
      checkEqual(`fixture ${scope}: worker envelope equals in-thread engine envelope (exact JSON)`, workerJson, directJson);
      checkEqual(
        `fixture ${scope}: progress stages observed in order`,
        stages,
        ['received', 'computing', 'complete', 'result'],
      );
      check(`fixture ${scope}: tracker recorded no stale envelopes`, client.staleEvents.length === 0, JSON.stringify(client.staleEvents));
    }

    const largeAnalyze = syntheticPayload('analyze', { years: 40 });
    const largeAnalyzeRun = await runParityViaWorker('analyze', largeAnalyze);
    checkEqual('large-range analyze (40y, 10k+ price rows): worker equals in-thread', largeAnalyzeRun.workerJson, largeAnalyzeRun.directJson);

    const largeDca = syntheticPayload('dca', { years: 20 });
    let t0 = performance.now();
    const largeDcaRun = await runParityViaWorker('dca', largeDca);
    const workerRoundtripMs = performance.now() - t0;
    checkEqual('large-range dca (20y monthly): worker equals in-thread', largeDcaRun.workerJson, largeDcaRun.directJson);

    longDcaPayload = syntheticPayload('dca', { years: 40 });
    t0 = performance.now();
    const directLong = dcaAnalysis(payloadToEngineArgs('dca', longDcaPayload));
    longDcaComputeMs = performance.now() - t0;
    console.log(`  info: long DCA (40y monthly) in-thread compute = ${longDcaComputeMs.toFixed(0)}ms; worker roundtrip for 20y DCA = ${workerRoundtripMs.toFixed(0)}ms`);
    check('long DCA reference compute measured (used for cancellation thresholds)', longDcaComputeMs > 2000, `${longDcaComputeMs.toFixed(0)}ms, xirr=${directLong.xirr}`);
    check('worker roundtrip overhead is small relative to compute', workerRoundtripMs < longDcaComputeMs * 2, `worker ${workerRoundtripMs.toFixed(0)}ms vs compute ${longDcaComputeMs.toFixed(0)}ms`);
  }

  section('Invalid requests produce typed errors on the matching id');
  {
    const client = new WorkerClient({ label: 'invalid' });
    try {
      const badDcaId = client.sendRequest('dca', { ...fixturePayload('dca'), contribution_sgd: '0' });
      const badDcaError = await client.waitFor(() => client.errorFor(badDcaId), { label: 'engine_value_error envelope' });
      checkEqual('zero contribution maps to engine_value_error', badDcaError.error.code, ERROR_CODES.ENGINE_VALUE);
      check('engine error message is preserved', badDcaError.error.message.includes('contribution_sgd must be greater than zero'), badDcaError.error.message);
      checkEqual('error arrives on the exact request id', badDcaError.id, badDcaId);
      check('production mode never leaks stacks', typeof badDcaError.error.details?.stack !== 'string');
      checkEqual('tracker records failed state', client.tracker.stateOf(badDcaId), REQUEST_STATES.FAILED);

      const numericId = client.sendRequest('analyze', { ...fixturePayload('analyze'), initial_sgd: 10000 });
      const numericError = await client.waitFor(() => client.errorFor(numericId), { label: 'bad_request envelope (numeric financial value)' });
      checkEqual('numeric financial value is rejected as bad_request', numericError.error.code, ERROR_CODES.BAD_REQUEST);
      check('validation detail names the offending field', JSON.stringify(numericError.error.details?.problems ?? []).includes('initial_sgd'), JSON.stringify(numericError.error.details));

      const unknownScopeEnvelope = createRequest('nope', fixturePayload('analyze'));
      client.tracker.track(unknownScopeEnvelope);
      client.worker.postMessage(unknownScopeEnvelope);
      const unknownScopeError = await client.waitFor(() => client.errorFor(unknownScopeEnvelope.id), { label: 'bad_request envelope (unknown scope)' });
      checkEqual('unknown scope maps to bad_request', unknownScopeError.error.code, ERROR_CODES.BAD_REQUEST);

      const tampered = { ...createRequest('analyze', fixturePayload('analyze')), id: 'analyze:deadbeefdeadbeef' };
      client.tracker.track(tampered);
      client.worker.postMessage(tampered);
      const tamperedError = await client.waitFor(() => client.errorFor('analyze:deadbeefdeadbeef'), { label: 'bad_request envelope (tampered id)' });
      checkEqual('tampered id is rejected (id must match requestKey)', tamperedError.error.code, ERROR_CODES.BAD_REQUEST);
      check('tampered-id rejection mentions the mismatch', tamperedError.error.message.includes('requestKey'), tamperedError.error.message);

      const badDcaId2 = client.sendRequest('dca', { ...fixturePayload('dca'), contribution_sgd: '-5' });
      const goodAnalyzeId = client.sendRequest('analyze', fixturePayload('analyze'));
      const goodResult = await client.waitFor(() => client.resultFor(goodAnalyzeId), { label: 'valid result among invalid request' });
      const badError2 = await client.waitFor(() => client.errorFor(badDcaId2), { label: 'second invalid error' });
      check('concurrent valid request resolves on its own id', goodResult.id === goodAnalyzeId);
      check('concurrent invalid request fails on its own id', badError2.id === badDcaId2 && badError2.id !== goodAnalyzeId);
      checkEqual('valid request state succeeded', client.tracker.stateOf(goodAnalyzeId), REQUEST_STATES.SUCCEEDED);
      checkEqual('invalid request state failed', client.tracker.stateOf(badDcaId2), REQUEST_STATES.FAILED);
      check('request isolation: no stale/cross-delivered envelopes at all', client.staleEvents.length === 0, JSON.stringify(client.staleEvents));
    } finally {
      await client.terminate();
    }
  }

  section('Error modes: debug stacks on request, absent in production mode');
  {
    const debugClient = new WorkerClient({ label: 'debug', debug: true });
    try {
      const id = debugClient.sendRequest('dca', { ...fixturePayload('dca'), contribution_sgd: '0' });
      const errorEnvelope = await debugClient.waitFor(() => debugClient.errorFor(id), { label: 'debug error envelope' });
      check('debug mode includes the stack in error details', typeof errorEnvelope.error.details?.stack === 'string' && errorEnvelope.error.details.stack.includes('EngineValueError'), JSON.stringify(errorEnvelope.error.details ?? {}).slice(0, 120));
    } finally {
      await debugClient.terminate();
    }
  }

  section('Cancellation poison regression: stale cancels must not blacklist content-derived ids');
  {
    // Regression (user-reported): toggling a scenario switch back re-runs a
    // payload whose id the client had cancelled earlier (as previousEngineId).
    // The worker used to keep those ids in cancelledIds forever, so the
    // re-request was answered with 'cancelled' and the chart went dead.
    const sent = [];
    const host = createEngineHost({ post: (m) => sent.push(m), yieldMs: 0 });
    const payload = fixturePayload('analyze');
    const id = requestKey('analyze', payload);
    host.handleMessage({ type: 'request', id, scope: 'analyze', payload });
    await delay(10);
    host.handleMessage({ type: 'cancel', id });
    check('cancel for a completed id is ignored (not blacklisted)', !host.isCancelled(id));
    host.handleMessage({ type: 'request', id, scope: 'analyze', payload });
    await delay(20);
    const reResults = sent.filter((m) => m.id === id && m.type === 'result');
    checkEqual('re-request after stale cancel computes', reResults.length, 2);
  }
  {
    const sent = [];
    const host = createEngineHost({ post: (m) => sent.push(m), yieldMs: 0 });
    const payload = fixturePayload('analyze');
    const id = requestKey('analyze', payload);
    host.handleMessage({ type: 'request', id, scope: 'analyze', payload });
    host.handleMessage({ type: 'cancel', id });
    host.handleMessage({ type: 'request', id, scope: 'analyze', payload });
    await delay(20);
    const reResults = sent.filter((m) => m.id === id && m.type === 'result');
    const cancelled = sent.filter((m) => m.id === id && m.type === 'cancelled');
    checkEqual('re-request after queued cancel still computes', reResults.length, 1);
    checkEqual('queued cancel is still acknowledged', cancelled.length, 1);
  }

  section('Cancellation: cooperative queued-cancel');
  {
    const client = new WorkerClient({ label: 'cooperative-cancel', yieldMs: 30 });
    try {
      const id = client.sendRequest('dca', longDcaPayload);
      await client.waitFor(
        (envelope) => envelope.id === id && envelope.type === 'progress' && envelope.stage === 'received',
        { label: 'received progress' },
      );
      const t0 = performance.now();
      client.cancel(id);
      const cancelled = await client.waitFor(() => client.cancelledFor(id), { label: 'cancelled envelope', timeoutMs: 5000 });
      const elapsed = performance.now() - t0;
      check('queued request is cancelled cooperatively with a cancelled envelope', cancelled.id === id);
      console.log(`  info: cooperative queued-cancel completed in ${elapsed.toFixed(1)}ms`);
      check('cooperative cancellation is timely', elapsed < 500, `${elapsed.toFixed(0)}ms`);
      const stages = client.envelopesFor(id).map((envelope) => (envelope.type === 'progress' ? envelope.stage : envelope.type));
      check('cancelled request never started computing', !stages.includes('computing'), stages.join(','));
      check('cancelled request never produced a result', client.resultFor(id) === null);
      checkEqual('tracker state is cancelled', client.tracker.stateOf(id), REQUEST_STATES.CANCELLED);
      check('no stale envelopes during cooperative cancel', client.staleEvents.length === 0, JSON.stringify(client.staleEvents));
      await delay(250);
      check('still no result envelope after the cancellation settled', client.resultFor(id) === null);

      const nextId = client.sendRequest('analyze', fixturePayload('analyze'));
      const nextResult = await client.waitFor(() => client.resultFor(nextId), { label: 'post-cancel result', timeoutMs: 10000 });
      check('worker remains usable after a cooperative cancellation', nextResult.ok === true && nextResult.id === nextId);
    } finally {
      await client.terminate();
    }
  }

  section('Cancellation: forced abort of an in-flight computation');
  {
    const client = new WorkerClient({ label: 'forced-cancel' });
    try {
      const id = client.sendRequest('dca', longDcaPayload);
      await client.waitFor(
        (envelope) => envelope.id === id && envelope.type === 'progress' && envelope.stage === 'computing',
        { label: 'computing progress' },
      );
      const t0 = performance.now();
      client.cancel(id);
      let terminal = null;
      try {
        terminal = await client.waitFor(
          (envelope) => envelope.id === id && (envelope.type === 'cancelled' || envelope.type === 'result'),
          { label: 'terminal envelope after cancel', timeoutMs: 150 },
        );
      } catch {
        terminal = null;
      }
      if (terminal === null) {
        await client.terminate();
        clients.delete(client);
      }
      const elapsed = performance.now() - t0;
      await client.exitPromise;
      console.log(`  info: forced cancel of in-flight computation terminal after ${elapsed.toFixed(1)}ms`);
      check('forced cancellation terminates the worker promptly', elapsed < 1000, `${elapsed.toFixed(0)}ms (compute takes ${longDcaComputeMs.toFixed(0)}ms)`);
      check('forced cancellation aborts well before the computation would finish', elapsed < longDcaComputeMs / 2, `${elapsed.toFixed(0)}ms vs ${longDcaComputeMs.toFixed(0)}ms`);
      check('no result envelope for the cancelled id', client.resultFor(id) === null, JSON.stringify(client.resultFor(id)));
      checkEqual('tracker keeps the cancelled state', client.tracker.stateOf(id), REQUEST_STATES.CANCELLED);
      check('no stale envelopes were observed on the forced path', client.staleEvents.length === 0, JSON.stringify(client.staleEvents));
      await delay(150);
      check('no envelope arrives after termination', client.received.filter((envelope) => envelope.id === id && envelope.type === 'result').length === 0);
    } finally {
      await client.terminate();
    }
  }

  section('Responsiveness: parent event loop keeps ticking during worker computation');
  {
    const client = new WorkerClient({ label: 'responsiveness' });
    try {
      const id = client.sendRequest('dca', longDcaPayload);
      await client.waitFor(
        (envelope) => envelope.id === id && envelope.type === 'progress' && envelope.stage === 'computing',
        { label: 'computing progress' },
      );
      let ticks = 0;
      const ticker = setInterval(() => {
        ticks += 1;
      }, 4);
      await delay(700);
      clearInterval(ticker);
      console.log(`  info: parent ticked ${ticks} times (4ms interval) during 700ms of worker computation`);
      check('parent timers fired during the worker computation', ticks >= 100, `${ticks} ticks in 700ms (interval 4ms)`);
      check('computation was still running while timers fired (no result yet)', client.resultFor(id) === null);
      check('computation had started (computing progress received)', client.envelopesFor(id).some((envelope) => envelope.type === 'progress' && envelope.stage === 'computing'));
      check('no stale envelopes while backgrounded', client.staleEvents.length === 0);
    } finally {
      await client.terminate();
    }
  }

  section('Request keys: identical payloads share ids, different payloads never do');
  {
    const client = new WorkerClient({ label: 'request-keys' });
    try {
      const payloadA = fixturePayload('analyze');
      const idA1 = client.sendRequest('analyze', payloadA);
      const resultA1 = await client.waitFor(() => client.resultFor(idA1), { label: 'first identical request' });
      const idA2 = client.sendRequest('analyze', payloadA);
      const resultA2 = await client.waitFor(() => client.resultFor(idA2), { label: 'second identical request' });
      check('two identical payloads produce the same request id through the worker', idA1 === idA2);
      check('identical payloads produce identical result envelopes', JSON.stringify(resultA1.result) === JSON.stringify(resultA2.result));

      const payloadB = { ...payloadA, initial_sgd: '10001' };
      const idB = client.sendRequest('analyze', payloadB);
      const resultB = await client.waitFor(() => client.resultFor(idB), { label: 'different payload request' });
      check('different payloads never share an id', idB !== idA1);
      check('different payloads produce different results', JSON.stringify(resultB.result) !== JSON.stringify(resultA1.result));

      const reordered = {};
      for (const key of Object.keys(payloadA).reverse()) reordered[key] = payloadA[key];
      check('key order does not change the request id', requestId('analyze', reordered) === idA1);
      const reorderedEnvelope = createRequest('analyze', reordered);
      client.tracker.track(reorderedEnvelope);
      client.worker.postMessage(reorderedEnvelope);
      const reorderedResult = await client.waitFor(() => client.resultFor(reorderedEnvelope.id), { label: 'reordered payload request' });
      check('worker accepts a reordered payload (id integrity holds)', reorderedResult.ok === true && reorderedResult.id === idA1);

      const portfolioPayload = fixturePayload('portfolio');
      const portfolioId = client.sendRequest('portfolio', portfolioPayload);
      const portfolioResult = await client.waitFor(() => client.resultFor(portfolioId), { label: 'portfolio request' });
      check('portfolio scope runs through the worker with its own id namespace', portfolioResult.ok === true && portfolioId !== idA1);
      check('request-keys client saw no stale envelopes', client.staleEvents.length === 0, JSON.stringify(client.staleEvents));
    } finally {
      await client.terminate();
    }
  }
}

const watchdog = setTimeout(() => {
  console.log('\nWATCHDOG: worker-selftest exceeded 180s; aborting.');
  process.exit(1);
}, 180000);
watchdog.unref();

try {
  await main();
} catch (error) {
  results.fail += 1;
  failures.push({ name: 'unexpected selftest error', detail: error?.stack ?? String(error) });
  console.log(`\n  FAIL unexpected selftest error :: ${error?.stack ?? String(error)}`);
} finally {
  for (const client of [...clients]) {
    await client.terminate();
  }
}

console.log(`\n==== WORKER SELFTEST SUMMARY: PASS ${results.pass} / FAIL ${results.fail} ====${failures.length ? `\nFailures:\n${failures.map((f) => ` - ${f.name}${f.detail === undefined ? '' : ` :: ${f.detail}`}`).join('\n')}` : ' all checks green'}`);
process.exitCode = results.fail === 0 ? 0 : 1;
