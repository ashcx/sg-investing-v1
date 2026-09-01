// FROZEN shared data layer for Sprint 4 (DCA) and Sprint 5 (portfolio).
// Freeze point per Todo/orchestration-plan.md: pack schema (Sprint 1) is
// frozen at schema_version 1; this module adapts packs -> engine inputs.
//
// Browser + Node compatible (ES module). In Node tests, pass a fetcher
// backed by fs and a baseUrl pointing at the frontend/ directory.
//
// Exports:
//   DEFAULT_TAX_RULES        snapshot of config/tax_rules.yaml (2026-08-31)
//   createPackLoader(options) -> loader
// Loader:
//   .loadManifest()          -> manifest object (cached)
//   .findSecurity({ticker, securityId}) -> manifest security entry | null
//   .supportFor(entry, startDate, endDate) -> {status, years:[{year,status,...}]}
//   .loadSecurityInputs(entry, startDate, endDate, opts) -> engine inputs:
//     { security, prices, fxRates, dividends, corporateActions, taxRules,
//       warnings, coverage, dataSnapshotId, manifestVersion, schemaVersion }
// All numeric row fields stay strings exactly as stored (decimal-safe).

export const DEFAULT_TAX_RULES = [
  {
    rule_id: 'US_DIVIDEND_NONRESIDENT',
    source_country: 'US',
    income_type: 'dividend',
    investor_type: 'singapore_individual',
    rate: '0.30',
    effective_from: '1900-01-01',
    effective_to: null,
  },
];

function yearRange(startDate, endDate) {
  const years = [];
  for (let year = Number(String(startDate).slice(0, 4)); year <= Number(String(endDate).slice(0, 4)); year++) {
    years.push(String(year));
  }
  return years;
}

function packPath(securityId, year) {
  return `data/packs/security=${securityId}/year=${year}.json`;
}

function uniqueBy(rows, keyFields) {
  const seen = new Set();
  const out = [];
  for (const row of rows) {
    const key = keyFields.map((field) => row[field]).join('\u0000');
    if (!seen.has(key)) { seen.add(key); out.push(row); }
  }
  return out;
}

// S6 (additive): optional IndexedDB cache for the 18 MB manifest, following
// the frozen convention in docs/data-pack-budgets.md ("Browser caching"):
// database `sg-invest-cache`, out-of-line key "manifest" in the `meta`
// store. Strictly best-effort: every failure (IndexedDB unavailable,
// blocked, quota, missing `meta` store) degrades to a plain fetch. This
// module never bumps the shared database version — the `meta` store is only
// created when this module is the first to create the database, and pack
// fetches are unchanged (packs stay validated against the loaded
// manifest's data_snapshot_id exactly as before).
const MANIFEST_CACHE_DATABASE = 'sg-invest-cache';
const MANIFEST_CACHE_STORE = 'meta';
const MANIFEST_CACHE_PACKS_STORE = 'packs';
const MANIFEST_CACHE_KEY = 'manifest';
const DEFAULT_MANIFEST_CACHE_TTL_MS = 24 * 60 * 60 * 1000;

export function createManifestIdbCache(options = {}) {
  if (typeof indexedDB === 'undefined') return null;
  const databaseName = options.databaseName || MANIFEST_CACHE_DATABASE;
  const storeName = options.storeName || MANIFEST_CACHE_STORE;
  const ttlMs = typeof options.ttlMs === 'number' ? options.ttlMs : DEFAULT_MANIFEST_CACHE_TTL_MS;

  function open() {
    return new Promise((resolve, reject) => {
      // No explicit version: never migrate the shared database from here.
      const request = indexedDB.open(databaseName);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(MANIFEST_CACHE_PACKS_STORE)) db.createObjectStore(MANIFEST_CACHE_PACKS_STORE);
        if (!db.objectStoreNames.contains(storeName)) db.createObjectStore(storeName);
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error('IndexedDB open failed.'));
      request.onblocked = () => reject(new Error('IndexedDB open blocked.'));
    });
  }

  async function read() {
    let db = null;
    try {
      db = await open();
      if (!db.objectStoreNames.contains(storeName)) return null;
      return await new Promise((resolve, reject) => {
        const request = db.transaction(storeName, 'readonly').objectStore(storeName).get(MANIFEST_CACHE_KEY);
        request.onsuccess = () => resolve(request.result ?? null);
        request.onerror = () => reject(request.error || new Error('IndexedDB read failed.'));
      });
    } catch {
      return null;
    } finally {
      if (db) db.close();
    }
  }

  async function write(entry) {
    let db = null;
    try {
      db = await open();
      if (!db.objectStoreNames.contains(storeName)) return false;
      await new Promise((resolve, reject) => {
        const request = db.transaction(storeName, 'readwrite').objectStore(storeName).put(entry, MANIFEST_CACHE_KEY);
        request.onsuccess = () => resolve();
        request.onerror = () => reject(request.error || new Error('IndexedDB write failed.'));
      });
      return true;
    } catch {
      return false;
    } finally {
      if (db) db.close();
    }
  }

  function isFresh(entry) {
    try {
      if (!entry || !entry.payload || typeof entry.fetched_at !== 'string') return false;
      if (!(ttlMs > 0)) return false;
      const fetched = Date.parse(entry.fetched_at);
      if (!Number.isFinite(fetched)) return false;
      return Date.now() - fetched < ttlMs;
    } catch {
      return false;
    }
  }

  return { name: 'indexeddb-meta', read, write, isFresh };
}

export function createPackLoader(options = {}) {
  const baseUrl = (options.baseUrl || '').replace(/\/$/, '');
  const fetcher = options.fetcher || ((url) => fetch(url, { cache: 'default' }));
  const taxRules = options.taxRules || DEFAULT_TAX_RULES;
  const manifestCache = 'manifestCache' in options ? options.manifestCache : createManifestIdbCache();
  let manifestPromise = null;

  const url = (path) => `${baseUrl}/${path}`;

  async function fetchJson(path) {
    const response = await fetcher(url(path));
    if (!response.ok) throw new Error(`Could not load ${path} (${response.status})`);
    return response.json();
  }

  function loadManifest() {
    if (!manifestPromise) manifestPromise = loadManifestCached();
    return manifestPromise;
  }

  async function loadManifestCached() {
    if (manifestCache) {
      try {
        const cached = await manifestCache.read();
        if (manifestCache.isFresh(cached)) return cached.payload;
      } catch {
        // cache problems never block the fetch path
      }
    }
    const manifest = await fetchJson('data/packs/manifest.json');
    if (manifestCache) {
      manifestCache
        .write({
          data_snapshot_id: manifest.data_snapshot_id ?? null,
          manifest_version: manifest.manifest_version ?? null,
          catalog_as_of: manifest.catalog_as_of ?? null,
          fetched_at: new Date().toISOString(),
          payload: manifest,
        })
        .catch(() => {});
    }
    return manifest;
  }

  async function findSecurity({ ticker, securityId } = {}) {
    const manifest = await loadManifest();
    const list = manifest.securities || [];
    if (securityId) return list.find((s) => s.security_id === securityId) || null;
    if (ticker) return list.find((s) => String(s.ticker).toUpperCase() === String(ticker).toUpperCase()) || null;
    return null;
  }

  // Support classification across the requested range, from manifest data
  // only (no packs fetched). status: fully_supported | incomplete | unavailable.
  function supportFor(entry, startDate, endDate) {
    if (!entry) return { status: 'unavailable', reason: 'unknown security', years: [] };
    const years = yearRange(startDate, endDate).map((year) => {
      const info = entry.years?.[year] || null;
      return { year, status: info ? info.status || entry.status : 'unavailable', info };
    });
    const first = entry.first_year ? Number(entry.first_year) : null;
    const last = entry.last_year ? Number(entry.last_year) : null;
    const startYear = Number(String(startDate).slice(0, 4));
    const endYear = Number(String(endDate).slice(0, 4));
    let status = 'fully_supported';
    const reasons = [];
    if (first === null || last === null || startYear < first || endYear > last) {
      status = 'unavailable';
      reasons.push(`requested range outside covered years ${first}–${last}`);
    } else if (years.some((y) => y.status !== 'fully_supported')) {
      status = 'incomplete';
      for (const y of years) if (y.status !== 'fully_supported') reasons.push(`year ${y.year}: ${y.status}`);
    }
    return { status, reason: reasons.join('; '), years };
  }

  // Assemble engine inputs for [startDate, endDate] from security-year packs.
  async function loadSecurityInputs(entry, startDate, endDate, opts = {}) {
    if (!entry || !entry.security_id) throw new Error('loadSecurityInputs requires a manifest security entry');
    const years = yearRange(startDate, endDate);
    const packs = await Promise.all(years.map((year) => fetchJson(packPath(entry.security_id, year))));
    const prices = [];
    const fxRates = [];
    const dividends = [];
    const corporateActions = [];
    const warnings = [];
    const coverage = [];
    let security = null;
    let dataSnapshotId = null;
    let schemaVersion = null;
    let manifestVersion = null;
    for (const pack of packs) {
      if (pack.schema_version !== 1) throw new Error(`Unsupported pack schema_version ${pack.schema_version}`);
      schemaVersion = pack.schema_version;
      dataSnapshotId = pack.data_snapshot_id || dataSnapshotId;
      manifestVersion = pack.manifest_version ?? manifestVersion;
      security = pack.security || security;
      const nativeCurrency = (pack.security && pack.security.currency) || (pack.coverage && pack.coverage.native_currency) || entry.native_currency;
      const priceCols = pack.prices || {};
      const priceDates = priceCols.dates || [];
      for (let i = 0; i < priceDates.length; i++) {
        prices.push({ security_id: entry.security_id, trading_date: priceDates[i], close: String(priceCols.close[i]), currency: nativeCurrency });
      }
      const fxBlock = pack.fx || {};
      const fxDates = fxBlock.dates || [];
      for (let i = 0; i < fxDates.length; i++) {
        fxRates.push({ rate_date: fxDates[i], base_currency: fxBlock.base_currency, rate_to_sgd: String(fxBlock.rates[i]) });
      }
      for (const row of pack.dividends || []) dividends.push({ security_id: entry.security_id, ...row });
      for (const row of pack.corporate_actions || []) corporateActions.push(row);
      for (const warning of pack.warnings || []) if (!warnings.includes(warning)) warnings.push(warning);
      if (pack.coverage) coverage.push(pack.coverage);
    }
    return {
      security: security || { security_id: entry.security_id, ticker: entry.ticker, currency: entry.native_currency },
      prices: uniqueBy(prices, ['trading_date']),
      fxRates: uniqueBy(fxRates, ['rate_date', 'base_currency']),
      dividends: uniqueBy(dividends, ['ex_date', 'amount', 'pay_date']),
      corporateActions: uniqueBy(corporateActions, ['action_type', 'effective_date']),
      taxRules: opts.taxRules || taxRules,
      warnings,
      coverage,
      dataSnapshotId,
      manifestVersion,
      schemaVersion,
      support: supportFor(entry, startDate, endDate),
    };
  }

  return { loadManifest, findSecurity, supportFor, loadSecurityInputs };
}
