import {
  analyzePortfolio,
  analyzeSecurity,
  dcaAnalysis,
} from './index.js';
import {
  ERROR_CODES,
  SCOPES,
  createCancelled,
  createError,
  createProgress,
  createResult,
  isRequestEnvelope,
  mapThrownToErrorBody,
  requestId,
} from './protocol.js';

const ENGINE_CALLS = Object.freeze({
  analyze: analyzeSecurity,
  dca: dcaAnalysis,
  portfolio: analyzePortfolio,
});

const PAYLOAD_SPEC = Object.freeze({
  analyze: Object.freeze({
    required: Object.freeze(['security', 'prices', 'fx_rates', 'start_date', 'end_date', 'initial_sgd']),
    optional: Object.freeze(['scenario', 'dividends', 'corporate_actions', 'tax_rules']),
    numericStrings: Object.freeze(['initial_sgd']),
    dateStrings: Object.freeze(['start_date', 'end_date']),
  }),
  dca: Object.freeze({
    required: Object.freeze(['security', 'prices', 'fx_rates', 'start_date', 'end_date', 'contribution_sgd']),
    optional: Object.freeze(['frequency', 'scenario', 'dividends', 'corporate_actions', 'tax_rules']),
    numericStrings: Object.freeze(['contribution_sgd']),
    dateStrings: Object.freeze(['start_date', 'end_date']),
  }),
  portfolio: Object.freeze({
    required: Object.freeze(['transactions', 'securities', 'prices', 'fx_rates', 'as_of']),
    optional: Object.freeze([]),
    numericStrings: Object.freeze([]),
    dateStrings: Object.freeze(['as_of']),
  }),
});

const ROW_NUMERIC_FIELDS = Object.freeze({
  prices: Object.freeze(['close']),
  fx_rates: Object.freeze(['rate_to_sgd']),
  dividends: Object.freeze(['amount']),
  corporate_actions: Object.freeze(['ratio']),
  tax_rules: Object.freeze(['rate']),
  transactions: Object.freeze(['quantity', 'cash_amount', 'fees']),
});

export function validateRequestPayload(scope, payload) {
  const problems = [];
  const spec = PAYLOAD_SPEC[scope];
  if (!spec) return [`unknown scope: ${String(scope)}`];
  const allowed = new Set([...spec.required, ...spec.optional]);
  for (const field of spec.required) {
    if (!(field in payload)) problems.push(`missing required field: ${field}`);
  }
  for (const key of Object.keys(payload)) {
    if (!allowed.has(key)) problems.push(`unknown field: ${key}`);
  }
  for (const field of spec.numericStrings) {
    if (field in payload && typeof payload[field] !== 'string') {
      problems.push(`field ${field} must be a string (financial values in payloads must be strings)`);
    }
  }
  for (const field of spec.dateStrings) {
    if (field in payload && typeof payload[field] !== 'string') {
      problems.push(`field ${field} must be a YYYY-MM-DD string`);
    }
  }
  if ('scenario' in payload && (payload.scenario === null || typeof payload.scenario !== 'object' || Array.isArray(payload.scenario))) {
    problems.push('field scenario must be an object');
  }
  if (scope === 'portfolio' && (payload.securities === null || typeof payload.securities !== 'object' || Array.isArray(payload.securities))) {
    problems.push('field securities must be an object keyed by security_id');
  }
  for (const [field, numericKeys] of Object.entries(ROW_NUMERIC_FIELDS)) {
    if (!(field in payload)) continue;
    const rows = payload[field];
    if (!Array.isArray(rows)) {
      problems.push(`field ${field} must be an array`);
      continue;
    }
    rows.forEach((row, index) => {
      if (row === null || typeof row !== 'object' || Array.isArray(row)) {
        problems.push(`${field}[${index}] must be an object`);
        return;
      }
      for (const key of numericKeys) {
        if (key in row && row[key] !== null && typeof row[key] !== 'string') {
          problems.push(`${field}[${index}].${key} must be a string (financial values in payloads must be strings)`);
        }
      }
    });
  }
  return problems;
}

export function payloadToEngineArgs(scope, payload) {
  if (scope === 'analyze') {
    return {
      security: payload.security,
      prices: payload.prices,
      fxRates: payload.fx_rates,
      startDate: payload.start_date,
      endDate: payload.end_date,
      initialSgd: payload.initial_sgd,
      scenario: payload.scenario,
      dividends: payload.dividends,
      corporateActions: payload.corporate_actions,
      taxRules: payload.tax_rules,
    };
  }
  if (scope === 'dca') {
    return {
      security: payload.security,
      prices: payload.prices,
      fxRates: payload.fx_rates,
      startDate: payload.start_date,
      endDate: payload.end_date,
      contributionSgd: payload.contribution_sgd,
      frequency: payload.frequency,
      scenario: payload.scenario,
      dividends: payload.dividends,
      corporateActions: payload.corporate_actions,
      taxRules: payload.tax_rules,
    };
  }
  return {
    transactions: payload.transactions,
    securities: payload.securities,
    prices: payload.prices,
    fxRates: payload.fx_rates,
    asOf: payload.as_of,
  };
}

export function serializeResultEnvelope(value) {
  return JSON.parse(JSON.stringify(value));
}

function createProtocolProblemsError(problems) {
  const error = new Error('Request payload failed protocol validation.');
  error.name = 'ProtocolError';
  error.code = ERROR_CODES.BAD_REQUEST;
  error.details = { problems };
  return error;
}

function dispatch(scope, payload) {
  const problems = validateRequestPayload(scope, payload);
  if (problems.length) throw createProtocolProblemsError(problems);
  return ENGINE_CALLS[scope](payloadToEngineArgs(scope, payload));
}

export function createEngineHost({ post, debug = false, yieldMs = 0 } = {}) {
  if (typeof post !== 'function') {
    throw new TypeError('createEngineHost requires a post(message) callback.');
  }
  const cancelledIds = new Set();
  const active = new Map();

  function send(envelope) {
    post(envelope);
  }

  function finishRequest(id) {
    active.delete(id);
  }

  function postThrownError(id, thrown) {
    if (cancelledIds.has(id)) {
      send(createCancelled(id));
      return;
    }
    const body = mapThrownToErrorBody(thrown, { debug });
    const details =
      thrown && thrown.code === ERROR_CODES.BAD_REQUEST && thrown.details ? thrown.details : body.details;
    const code = thrown && thrown.code === ERROR_CODES.BAD_REQUEST ? ERROR_CODES.BAD_REQUEST : body.code;
    send(createError(id, code, body.message, details));
  }

  function run(id, scope, payload) {
    const entry = active.get(id);
    if (!entry || entry.state !== 'queued') return;
    if (cancelledIds.has(id)) {
      finishRequest(id);
      send(createCancelled(id));
      return;
    }
    entry.state = 'computing';
    send(createProgress(id, 'computing', 0, 1));
    let raw;
    try {
      raw = dispatch(scope, payload);
    } catch (thrown) {
      finishRequest(id);
      postThrownError(id, thrown);
      return;
    }
    finishRequest(id);
    if (cancelledIds.has(id)) {
      send(createCancelled(id));
      return;
    }
    send(createProgress(id, 'complete', 1, 1));
    send(createResult(id, serializeResultEnvelope(raw)));
  }

  function handleRequest(message) {
    if (!isRequestEnvelope(message)) {
      const id = typeof message?.id === 'string' && message.id.length > 0 ? message.id : null;
      const problems = [];
      if (!message || typeof message !== 'object' || Array.isArray(message)) {
        problems.push('envelope must be an object');
      } else {
        if (message.type !== 'request') problems.push(`unexpected type: ${String(message.type)}`);
        if (typeof message.id !== 'string' || message.id.length === 0) problems.push('id must be a non-empty string');
        if (typeof message.scope !== 'string' || !SCOPES.includes(message.scope)) {
          problems.push(`scope must be one of: ${SCOPES.join(', ')}`);
        }
        if (!message.payload || typeof message.payload !== 'object' || Array.isArray(message.payload)) {
          problems.push('payload must be a plain object');
        }
      }
      send(createError(id, ERROR_CODES.BAD_REQUEST, 'Malformed request envelope.', { problems }));
      return;
    }
    const { id, scope, payload } = message;
    if (requestId(scope, payload) !== id) {
      send(
        createError(
          id,
          ERROR_CODES.BAD_REQUEST,
          'Request id does not match requestKey(scope, payload).',
          { scope },
        ),
      );
      return;
    }
    if (cancelledIds.has(id)) {
      send(createCancelled(id));
      return;
    }
    if (active.has(id)) {
      return;
    }
    active.set(id, { state: 'queued', scope });
    send(createProgress(id, 'received'));
    setTimeout(() => run(id, scope, payload), yieldMs);
  }

  function handleCancel(message) {
    const id = typeof message?.id === 'string' ? message.id : null;
    if (id === null) return;
    cancelledIds.add(id);
    const entry = active.get(id);
    if (!entry) return;
    if (entry.state === 'queued') {
      active.delete(id);
      send(createCancelled(id));
      return;
    }
  }

  function handleMessage(message) {
    if (!message || typeof message !== 'object' || Array.isArray(message)) return;
    if (message.type === 'request') {
      handleRequest(message);
      return;
    }
    if (message.type === 'cancel') {
      handleCancel(message);
      return;
    }
    if (typeof message.id === 'string' && message.id.length > 0) {
      send(createError(message.id, ERROR_CODES.BAD_REQUEST, `Unsupported envelope type: ${String(message.type)}.`));
    }
  }

  function isCancelled(id) {
    return cancelledIds.has(id);
  }

  function queuedIds() {
    const queued = [];
    for (const [id, entry] of active) {
      if (entry.state === 'queued') queued.push(id);
    }
    return queued;
  }

  return { handleMessage, isCancelled, queuedIds };
}

const inBrowserWorker =
  typeof WorkerGlobalScope !== 'undefined' &&
  typeof self !== 'undefined' &&
  self instanceof WorkerGlobalScope;

if (inBrowserWorker) {
  let debug = false;
  try {
    debug = new URL(import.meta.url).searchParams.has('debug');
  } catch {
    debug = false;
  }
  const host = createEngineHost({ post: (message) => self.postMessage(message), debug });
  self.addEventListener('message', (event) => host.handleMessage(event.data));
}
