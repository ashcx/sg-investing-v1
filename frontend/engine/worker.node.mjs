import {
  isMainThread,
  parentPort,
  workerData,
  Worker as NodeWorker,
} from 'node:worker_threads';

export function spawnEngineWorker({ debug = false, yieldMs = 0 } = {}) {
  const entry = new URL('./worker.node.mjs', import.meta.url);
  return new NodeWorker(entry, { workerData: { debug, yieldMs } });
}

export const isEngineWorkerThread = !isMainThread && parentPort !== null;

if (isEngineWorkerThread) {
  const { createEngineHost } = await import('./worker.js');
  const host = createEngineHost({
    post: (message) => parentPort.postMessage(message),
    debug: Boolean(workerData?.debug),
    yieldMs: Number(workerData?.yieldMs) || 0,
  });
  parentPort.on('message', (message) => host.handleMessage(message));
}
