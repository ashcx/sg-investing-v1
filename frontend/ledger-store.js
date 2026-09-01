// Ledger persistence for Sprint 5 (S5.6). Local-only, user-controlled.
//
// Storage convention (docs/data-pack-budgets.md, "Browser caching"):
//   - database `sg-invest-cache`, additive versioning only;
//   - this module adds the `ledger` object store at database version 2 via
//     onupgradeneeded and never touches the `packs`/`meta` stores owned by
//     the pack cache;
//   - `ledger` entries are never evicted by pack-cache pressure.
//
// The driver is injectable: browsers get an IndexedDB driver, Node tests get
// an in-memory driver. `ledgerStore` is the app-facing singleton that picks
// the right default for the current runtime.
//
// Ledger shape (canonical row fields, numerics as decimal-safe strings):
//   { transaction_type, security_id, transaction_date, quantity,
//     cash_amount, currency, fees }

const LEDGER_SCHEMA = 'sg-invest-ledger';
const LEDGER_SCHEMA_VERSION = 1;
const TRANSACTION_TYPES = new Set(['BUY', 'SELL', 'DIVIDEND', 'CASH_DEPOSIT', 'CASH_WITHDRAWAL']);
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const NUMERIC_PATTERN = /^-?\d+(\.\d+)?$/;
const CURRENCY_PATTERN = /^[A-Z]{3}$/;
const ROW_FIELDS = ['transaction_type', 'security_id', 'transaction_date', 'quantity', 'cash_amount', 'currency', 'fees'];

// Database convention shared with the pack cache (docs/data-pack-budgets.md).
export const LEDGER_DATABASE_NAME = 'sg-invest-cache';
export const LEDGER_DATABASE_VERSION = 2;
export const LEDGER_STORE_NAME = 'ledger';
const LEDGER_RECORD_KEY = 'current';

export function createMemoryDriver() {
  let record = null;
  return {
    name: 'memory',
    async read() {
      return record;
    },
    async write(value) {
      record = value;
    },
    async remove() {
      record = null;
    },
  };
}

export function createIndexedDbDriver(options = {}) {
  const databaseName = options.databaseName || LEDGER_DATABASE_NAME;
  const databaseVersion = options.databaseVersion || LEDGER_DATABASE_VERSION;
  const storeName = options.storeName || LEDGER_STORE_NAME;

  function requestToPromise(request) {
    return new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error('IndexedDB request failed.'));
    });
  }

  function transactionToPromise(transaction) {
    return new Promise((resolve, reject) => {
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error || new Error('IndexedDB transaction failed.'));
      transaction.onabort = () => reject(transaction.error || new Error('IndexedDB transaction aborted.'));
    });
  }

  function open() {
    return new Promise((resolve, reject) => {
      if (typeof indexedDB === 'undefined') {
        reject(new Error('IndexedDB is unavailable in this context.'));
        return;
      }
      const request = indexedDB.open(databaseName, databaseVersion);
      request.onupgradeneeded = () => {
        // Additive migration: create only our own store; never recreate or
        // delete stores owned by other features (packs, meta).
        const db = request.result;
        if (!db.objectStoreNames.contains(storeName)) db.createObjectStore(storeName);
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error('IndexedDB open failed.'));
      request.onblocked = () => reject(new Error('IndexedDB open blocked by another connection.'));
    });
  }

  return {
    name: 'indexeddb',
    async read() {
      const db = await open();
      try {
        const transaction = db.transaction(storeName, 'readonly');
        const value = await requestToPromise(transaction.objectStore(storeName).get(LEDGER_RECORD_KEY));
        await transactionToPromise(transaction).catch(() => {});
        return value ?? null;
      } finally {
        db.close();
      }
    },
    async write(value) {
      const db = await open();
      try {
        const transaction = db.transaction(storeName, 'readwrite');
        transaction.objectStore(storeName).put(value, LEDGER_RECORD_KEY);
        await transactionToPromise(transaction);
      } finally {
        db.close();
      }
    },
    async remove() {
      const db = await open();
      try {
        const transaction = db.transaction(storeName, 'readwrite');
        transaction.objectStore(storeName).delete(LEDGER_RECORD_KEY);
        await transactionToPromise(transaction);
      } finally {
        db.close();
      }
    },
  };
}

function normalizeRow(row, index) {
  if (!row || typeof row !== 'object' || Array.isArray(row)) {
    throw new Error(`Ledger row ${index + 1} is not an object.`);
  }
  if (!TRANSACTION_TYPES.has(row.transaction_type)) {
    throw new Error(`Ledger row ${index + 1} has an unknown transaction type: ${String(row.transaction_type)}.`);
  }
  if (row.security_id !== null && typeof row.security_id !== 'string') {
    throw new Error(`Ledger row ${index + 1} needs a security id or null.`);
  }
  if (typeof row.transaction_date !== 'string' || !DATE_PATTERN.test(row.transaction_date)) {
    throw new Error(`Ledger row ${index + 1} needs a YYYY-MM-DD transaction date.`);
  }
  for (const field of ['quantity', 'cash_amount', 'fees']) {
    if (typeof row[field] !== 'string' || !NUMERIC_PATTERN.test(row[field])) {
      throw new Error(`Ledger row ${index + 1} field ${field} must be a numeric string.`);
    }
  }
  if (typeof row.currency !== 'string' || !CURRENCY_PATTERN.test(row.currency)) {
    throw new Error(`Ledger row ${index + 1} needs a three-letter currency code.`);
  }
  const normalized = {};
  for (const field of ROW_FIELDS) normalized[field] = row[field];
  return normalized;
}

function normalizeRows(rows) {
  if (!Array.isArray(rows)) throw new Error('A ledger is an array of transaction rows.');
  return rows.map(normalizeRow);
}

function parseLedgerPayload(payload) {
  if (typeof payload === 'string') {
    let parsed;
    try {
      parsed = JSON.parse(payload);
    } catch {
      throw new Error('Imported ledger is not valid JSON.');
    }
    return parseLedgerPayload(parsed);
  }
  if (Array.isArray(payload)) return normalizeRows(payload);
  if (payload && typeof payload === 'object' && payload.schema === LEDGER_SCHEMA) {
    return normalizeRows(payload.rows);
  }
  throw new Error(`Imported ledger must use the ${LEDGER_SCHEMA} envelope or a row array.`);
}

export function createLedgerStore(driver) {
  if (!driver || typeof driver.read !== 'function' || typeof driver.write !== 'function' || typeof driver.remove !== 'function') {
    throw new Error('createLedgerStore requires a driver with read/write/remove.');
  }
  async function writeRows(rows) {
    await driver.write({ schema: LEDGER_SCHEMA, version: LEDGER_SCHEMA_VERSION, saved_at: new Date().toISOString(), rows });
  }
  return {
    driver: driver.name,
    async save(ledger) {
      const rows = normalizeRows(ledger);
      await writeRows(rows);
      return rows;
    },
    async load() {
      const record = await driver.read();
      if (!record) return [];
      return normalizeRows(record.rows ?? record);
    },
    async clear() {
      await driver.remove();
    },
    async exportJson() {
      const rows = await this.load();
      return `${JSON.stringify({ schema: LEDGER_SCHEMA, version: LEDGER_SCHEMA_VERSION, exported_at: new Date().toISOString(), rows }, null, 2)}\n`;
    },
    async importJson(json) {
      const rows = parseLedgerPayload(json);
      await writeRows(rows);
      return rows;
    },
  };
}

export const ledgerStore = createLedgerStore(typeof indexedDB === 'undefined' ? createMemoryDriver() : createIndexedDbDriver());
