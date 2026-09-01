import { AnalysisDataError, EngineValueError } from './models.js';
import { requestKey } from './request-keys.js';

export const SCOPES = Object.freeze(['analyze', 'dca', 'portfolio']);

export const ERROR_CODES = Object.freeze({
  CANCELLED: 'cancelled',
  ANALYSIS_DATA: 'analysis_data_error',
  ENGINE_VALUE: 'engine_value_error',
  BAD_REQUEST: 'bad_request',
  INTERNAL: 'internal_error',
});

export const REQUEST_STATES = Object.freeze({
  PENDING: 'pending',
  RUNNING: 'running',
  CANCELLED: 'cancelled',
  SUPERSEDED: 'superseded',
  SUCCEEDED: 'succeeded',
  FAILED: 'failed',
});

const TERMINAL_STATES = new Set([
  REQUEST_STATES.CANCELLED,
  REQUEST_STATES.SUPERSEDED,
  REQUEST_STATES.SUCCEEDED,
  REQUEST_STATES.FAILED,
]);

export const STALE_REASONS = Object.freeze({
  UNKNOWN_ID: 'unknown_id',
  TERMINAL_REQUEST: 'terminal_request',
  CANCELLED_REQUEST: 'cancelled_request',
  SUPERSEDED_REQUEST: 'superseded_request',
  MALFORMED_ENVELOPE: 'malformed_envelope',
  UNKNOWN_ENVELOPE_TYPE: 'unknown_envelope_type',
});

export class CancellationError extends Error {
  constructor(message = 'Calculation cancelled.') {
    super(message);
    this.name = 'CancellationError';
    this.code = ERROR_CODES.CANCELLED;
  }
}

export function requestId(scope, payload) {
  return requestKey(scope, payload);
}

export function createRequest(scope, payload) {
  return { type: 'request', id: requestId(scope, payload), scope, payload };
}

export function createProgress(id, stage, done, total) {
  const envelope = { type: 'progress', id, stage };
  if (typeof done === 'number' && Number.isFinite(done) && typeof total === 'number' && Number.isFinite(total)) {
    envelope.done = done;
    envelope.total = total;
  }
  return envelope;
}

export function createResult(id, result) {
  return { type: 'result', id, ok: true, result };
}

export function createError(id, code, message, details) {
  const error = { code, message };
  if (details !== undefined) error.details = details;
  return { type: 'result', id, ok: false, error };
}

export function createCancelled(id) {
  return { type: 'cancelled', id };
}

export function mapThrownToErrorBody(thrown, { debug = false } = {}) {
  let code = ERROR_CODES.INTERNAL;
  if (thrown instanceof CancellationError) {
    code = ERROR_CODES.CANCELLED;
  } else if (thrown instanceof AnalysisDataError) {
    code = ERROR_CODES.ANALYSIS_DATA;
  } else if (thrown instanceof EngineValueError) {
    code = ERROR_CODES.ENGINE_VALUE;
  }
  const name = thrown instanceof Error ? thrown.name : `non-error:${typeof thrown}`;
  const message = thrown instanceof Error ? thrown.message : String(thrown);
  const details = { name };
  if (debug && thrown instanceof Error && typeof thrown.stack === 'string') {
    details.stack = thrown.stack;
  }
  return { code, message, details };
}

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function isRequestEnvelope(value) {
  return (
    isPlainObject(value) &&
    value.type === 'request' &&
    typeof value.id === 'string' &&
    value.id.length > 0 &&
    typeof value.scope === 'string' &&
    SCOPES.includes(value.scope) &&
    isPlainObject(value.payload)
  );
}

export function isCancelEnvelope(value) {
  return isPlainObject(value) && value.type === 'cancel' && typeof value.id === 'string' && value.id.length > 0;
}

export function isEnvelope(value) {
  return (
    isPlainObject(value) &&
    (isRequestEnvelope(value) ||
      isCancelEnvelope(value) ||
      ((value.type === 'progress' || value.type === 'result' || value.type === 'cancelled') &&
        typeof value.id === 'string' &&
        value.id.length > 0))
  );
}

export function isTerminalState(state) {
  return TERMINAL_STATES.has(state);
}

export function createRequestTracker({ onStale } = {}) {
  const records = new Map();
  const idsByScope = new Map();

  function recordStale(envelope, record, reason) {
    if (record) record.staleCount += 1;
    if (typeof onStale === 'function') onStale(envelope, { record: record ?? null, reason });
    return { delivered: false, stale: true, reason, record: record ?? null };
  }

  function observe(envelope) {
    if (!isPlainObject(envelope) || typeof envelope.type !== 'string') {
      return recordStale(envelope, null, STALE_REASONS.MALFORMED_ENVELOPE);
    }
    const id = envelope.id;
    const record = typeof id === 'string' ? records.get(id) : undefined;
    switch (envelope.type) {
      case 'progress': {
        if (!record) return recordStale(envelope, null, STALE_REASONS.UNKNOWN_ID);
        if (TERMINAL_STATES.has(record.state)) return recordStale(envelope, record, STALE_REASONS.TERMINAL_REQUEST);
        record.stage = envelope.stage;
        if (typeof envelope.done === 'number') record.done = envelope.done;
        if (typeof envelope.total === 'number') record.total = envelope.total;
        if (record.state === REQUEST_STATES.PENDING && envelope.stage === 'computing') {
          record.state = REQUEST_STATES.RUNNING;
        }
        return { delivered: true, stale: false, record };
      }
      case 'result': {
        if (!record) return recordStale(envelope, null, STALE_REASONS.UNKNOWN_ID);
        const cancelledConfirmation =
          envelope.ok === false &&
          envelope.error?.code === ERROR_CODES.CANCELLED &&
          record.state === REQUEST_STATES.CANCELLED;
        if (TERMINAL_STATES.has(record.state)) {
          if (cancelledConfirmation) return { delivered: true, stale: false, record };
          if (record.state === REQUEST_STATES.CANCELLED) {
            return recordStale(envelope, record, STALE_REASONS.CANCELLED_REQUEST);
          }
          if (record.state === REQUEST_STATES.SUPERSEDED) {
            return recordStale(envelope, record, STALE_REASONS.SUPERSEDED_REQUEST);
          }
          return recordStale(envelope, record, STALE_REASONS.TERMINAL_REQUEST);
        }
        if (envelope.ok === true) {
          record.state = REQUEST_STATES.SUCCEEDED;
          record.result = envelope.result;
        } else {
          record.state = REQUEST_STATES.FAILED;
          record.error = envelope.error;
        }
        return { delivered: true, stale: false, record };
      }
      case 'cancelled': {
        if (!record) return recordStale(envelope, null, STALE_REASONS.UNKNOWN_ID);
        if (record.state === REQUEST_STATES.CANCELLED) {
          return { delivered: true, stale: false, record };
        }
        if (TERMINAL_STATES.has(record.state)) {
          return recordStale(envelope, record, STALE_REASONS.TERMINAL_REQUEST);
        }
        record.state = REQUEST_STATES.CANCELLED;
        return { delivered: true, stale: false, record };
      }
      default:
        return recordStale(envelope, record ?? null, STALE_REASONS.UNKNOWN_ENVELOPE_TYPE);
    }
  }

  function track(requestOrId, scopeArg) {
    let id;
    let scope;
    if (isPlainObject(requestOrId) && typeof requestOrId.id === 'string') {
      id = requestOrId.id;
      scope = requestOrId.scope;
    } else {
      id = requestOrId;
      scope = scopeArg;
    }
    if (typeof id !== 'string' || id.length === 0 || typeof scope !== 'string') {
      throw new TypeError('track requires a request envelope or (id, scope).');
    }
    const existing = records.get(id);
    if (existing && !TERMINAL_STATES.has(existing.state)) return existing;
    const record = {
      id,
      scope,
      state: REQUEST_STATES.PENDING,
      stage: null,
      done: null,
      total: null,
      result: undefined,
      error: undefined,
      staleCount: 0,
    };
    records.set(id, record);
    let scopeSet = idsByScope.get(scope);
    if (!scopeSet) {
      scopeSet = new Set();
      idsByScope.set(scope, scopeSet);
    }
    scopeSet.add(id);
    return record;
  }

  function markRunning(id) {
    const record = records.get(id);
    if (!record || TERMINAL_STATES.has(record.state)) return null;
    if (record.state === REQUEST_STATES.PENDING) record.state = REQUEST_STATES.RUNNING;
    return record;
  }

  function markCancelled(id) {
    const record = records.get(id);
    if (!record || TERMINAL_STATES.has(record.state)) return false;
    record.state = REQUEST_STATES.CANCELLED;
    return true;
  }

  function supersedeScope(scope, keepId = null) {
    const superseded = [];
    const scopeSet = idsByScope.get(scope);
    if (!scopeSet) return superseded;
    for (const id of scopeSet) {
      if (id === keepId) continue;
      const record = records.get(id);
      if (record && !TERMINAL_STATES.has(record.state)) {
        record.state = REQUEST_STATES.SUPERSEDED;
        superseded.push(id);
      }
    }
    return superseded;
  }

  function stateOf(id) {
    return records.get(id)?.state ?? null;
  }

  function getRecord(id) {
    return records.get(id) ?? null;
  }

  function activeInScope(scope) {
    const active = [];
    const scopeSet = idsByScope.get(scope);
    if (!scopeSet) return active;
    for (const id of scopeSet) {
      const record = records.get(id);
      if (record && !TERMINAL_STATES.has(record.state)) active.push(record);
    }
    return active;
  }

  // S6 (coordinator-approved additive reconciliation): mint a deterministic
  // request id from the frozen requestKey(scope, payload) contract and track
  // it immediately, so engine clients no longer need an app-side tracker
  // bridge to make the stale-request guard see their requests. Re-minting an
  // identical (scope, payload) returns the same id and dedupes via track().
  function nextId(scope, payload) {
    const id = requestId(scope, payload);
    track(id, scope);
    return id;
  }

  return {
    observe,
    track,
    nextId,
    markRunning,
    markCancelled,
    supersedeScope,
    stateOf,
    getRecord,
    activeInScope,
    get size() {
      return records.size;
    },
  };
}
