// FROZEN shared engine client for Sprint 4 (DCA) and Sprint 5 (portfolio).
// Browser-side promise wrapper over the Sprint 3 worker layer:
//   - spawns frontend/engine/worker.js as a module worker (subpath-safe)
//   - routes every inbound envelope through createRequestTracker (S4.6's
//     stale-request guard) so a late/cancelled/superseded response is never
//     delivered
//   - exposes cancel/supersede + terminate-and-respawn
// Node tests use frontend/engine/worker.node.mjs directly instead.

import { createRequestTracker } from './protocol.js';

function spawnWorker() {
  return new Worker(new URL('./worker.js', import.meta.url), { type: 'module' });
}

export function createEngineClient(options = {}) {
  let worker = options.worker || null;
  const tracker = options.tracker || createRequestTracker();
  const pending = new Map();
  const debug = options.debug === true;

  function ensureWorker() {
    if (worker) return worker;
    if (typeof Worker === 'undefined') throw new Error('Worker unavailable; engine client requires a browser (or a Node adapter harness)');
    worker = spawnWorker();
    worker.onmessage = (event) => deliver(event.data);
    worker.onerror = (event) => {
      const error = { code: 'internal_error', message: event.message || 'worker error' };
      for (const [id, entry] of pending) { entry.reject(error); pending.delete(id); }
    };
    return worker;
  }

  function deliver(envelope) {
    tracker.observe(envelope);
    if (!envelope || !envelope.id) return;
    const entry = pending.get(envelope.id);
    if (!entry) return; // stale/unknown per tracker; never delivered (S4.6)
    if (envelope.type === 'result') {
      pending.delete(envelope.id);
      if (envelope.ok) entry.resolve(envelope.result);
      else entry.reject(envelope.error);
    } else if (envelope.type === 'progress') {
      entry.onProgress?.(envelope);
    } else if (envelope.type === 'cancelled') {
      pending.delete(envelope.id);
      entry.reject({ code: 'cancelled', message: 'Request cancelled' });
    }
  }

  function request(scope, payload, { onProgress } = {}) {
    ensureWorker();
    const id = tracker.nextId(scope, payload);
    const promise = new Promise((resolve, reject) => pending.set(id, { resolve, reject, onProgress }));
    worker.postMessage({ type: 'request', id, scope, payload });
    return { id, promise };
  }

  function cancel(id) {
    if (!worker) return;
    worker.postMessage({ type: 'cancel', id });
    const entry = pending.get(id);
    // If nothing arrives promptly, the caller may forceTerminate(); the
    // tracker already marks the id cancelled so late results stay stale.
    return entry ? id : null;
  }

  function forceTerminate() {
    if (!worker) return;
    for (const [id, entry] of pending) { tracker.markCancelled(id); entry.reject({ code: 'cancelled', message: 'Worker terminated' }); }
    pending.clear();
    worker.terminate();
    worker = null;
  }

  return {
    request,
    cancel,
    forceTerminate,
    analyze: (payload, opts) => request('analyze', payload, opts),
    dca: (payload, opts) => request('dca', payload, opts),
    portfolio: (payload, opts) => request('portfolio', payload, opts),
    supersede: (scope, keepId) => tracker.supersedeScope(scope, keepId),
    isDebug: debug,
  };
}
