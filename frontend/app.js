// S5 local engine imports (Sprint 5 — static-site portfolio reconstruction).
// S4 local engine imports (pack-loader, engine-client) — merged by S5 to keep
// both agents' bindings without duplicate identifiers.
// S6: protocol.createRequestTracker now exposes native nextId(scope, payload),
// so the tracker bridge S4/S5 injected here is gone; engine clients use their
// own default tracker.
import { createEngineClient } from './engine/engine-client.js';
import { createPackLoader } from './engine/pack-loader.js';
import { rateForDate } from './engine/fx.js';
import { dec } from './engine/money.js';
import { initWorkspace } from './workspace.js';
import { ledgerStore, parseLedgerPayload } from './ledger-store.js';
import { TRANSACTION_FIELDS, ledgerError } from './ledger-editor.js';
import { commonWindow, resolveWindow, securityWindow, isIsoDate, comparisonRow, comparisonSummary } from './engine/compare-window.js';

const COMPARE_MIN = 2;
const COMPARE_MAX = 6;
const CATALOG_ARTIFACT = 'data/catalog.json';
const API_BASE = (document.querySelector('meta[name="sg-invest-api-base"]')?.content || '').replace(/\/$/, '');

// S6 wiring: one honest computation mode. The engine client and pack loader
// always run locally (packs → worker); when an adapter API base is
// configured the adapter is tried first and the local engine is the explicit
// fallback. The compute mode behind every visible result is shown in the
// header mode indicator (see setComputeMode).
// S8 (Tier-2 pack origin): sg-invest-pack-base points at an external pack
// origin (e.g. a Cloudflare R2 bucket). The Tier-1 origin (this site) is
// always consulted first; securities missing from its manifest fall back to
// the external origin so the full catalog can be served beyond the Pages
// size cap. Empty tag = Tier-1 only (default, current behavior).
const PACK_BASE = (document.querySelector('meta[name="sg-invest-pack-base"]')?.content || '').replace(/\/$/, '');
const packs = createPackLoader({ baseUrl: new URL('.', document.baseURI).href });
const packsRemote = PACK_BASE ? createPackLoader({ baseUrl: PACK_BASE }) : null;
const engineClient = createEngineClient();

// S8: resolve a security against Tier-1 (this site) first; fall back to the
// external pack origin (e.g. Cloudflare R2) when the local manifest does not
// know it. Returns { entry, packs } so subsequent calls use the same origin.
async function s8ResolveSecurity({ securityId = null, ticker = null } = {}) {
  let originError = null;
  for (const loader of [packs, packsRemote].filter(Boolean)) {
    try {
      const entry = await loader.findSecurity(securityId ? { securityId } : { ticker });
      if (entry) return { entry, packs: loader };
    } catch (failure) { originError = failure; }
  }
  if (originError) throw originError;
  return { entry: null, packs };
}
const s4State = { requestId: null, request: null, support: null, packWarnings: null, button: null };

const PRESETS = {
  investor: { dividends: true, withholding: true, reinvest: true },
  price: { dividends: false, withholding: false, reinvest: false },
  gross: { dividends: true, withholding: false, reinvest: true },
  cash: { dividends: true, withholding: true, reinvest: false },
};

const fallbackCatalog = [{
  universe: 'major_global_etfs',
  security: { security_id: 'demo-qqq', ticker: 'QQQ', exchange: 'NASDAQ', market: 'US', name: 'Invesco QQQ Trust', currency: 'USD', asset_type: 'ETF', distribution_policy: 'distributing', active: true },
}];

const state = {
  catalog: [],
  artifact: null,
  // S6: which producer made the visible analysis result —
  // 'demo' (init-time published replay) | 'adapter' | 'local' | 'adapterFallback'.
  artifactSource: 'demo',
  series: null,
  // S7.5 Track C: provenance of the currently rendered chart — 'local' when
  // the stage-1 on-select loader (or a local analysis) produced it, null for
  // backend/demo artifacts (renderSeries picks the chart-source label).
  seriesSource: null,
  dcaArtifact: null,
  selectedSecurityId: null,
  compareTickers: [],
  currencyMode: 'sgd',
  dcaCurrencyMode: 'sgd',
  dcaContext: {},
  analysisCoverage: {},
  simulatorMode: 'one-time',
  warningsOpen: false,
  catalogLimit: 12,
  discoveryManifest: null,
  // S12: the published empty state, restored when a compare run is invalidated.
  compareEmptyHtml: '',
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const has = (selector) => Boolean($(selector));
const COMBOBOX_RESULT_LIMIT = 40;

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
}

function securityComboboxValue(inputOrSelector) {
  const input = typeof inputOrSelector === 'string' ? $(inputOrSelector) : inputOrSelector;
  return input?.dataset.securityId || '';
}

function securityDisplayLabel(security) {
  return `${security.ticker} — ${security.name}`;
}

function closeSecurityCombobox(input) {
  const root = input?.closest('[data-combobox]');
  const list = root?.querySelector('.combobox-list');
  if (!root || !list) return;
  list.classList.add('hidden');
  input.setAttribute('aria-expanded', 'false');
  input.removeAttribute('aria-activedescendant');
}

function renderSecurityCombobox(input, query = input.value) {
  const root = input.closest('[data-combobox]');
  const list = root?.querySelector('.combobox-list');
  if (!root || !list) return;
  const wanted = String(query || '').trim().toLowerCase();
  const matches = securityEntries().filter(({ security }) => {
    const text = [security.ticker, security.name, security.isin, security.exchange, security.market].filter(Boolean).join(' ').toLowerCase();
    return !wanted || text.includes(wanted);
  });
  const visible = matches.slice(0, COMBOBOX_RESULT_LIMIT);
  list.innerHTML = visible.map(({ security }, index) => `<div class="combobox-option" id="${escapeHtml(input.id)}-option-${index}" role="option" aria-selected="${securityComboboxValue(input) === security.security_id}" data-security-id="${escapeHtml(security.security_id)}"><strong>${escapeHtml(security.ticker)}</strong><span>${escapeHtml(security.name)} · ${escapeHtml(security.exchange)} · ${escapeHtml(security.currency)}<br>${escapeHtml(discoveryCoverage(security.security_id))}</span></div>`).join('')
    || '<div class="combobox-empty" role="status">No published securities match that search.</div>';
  if (matches.length > COMBOBOX_RESULT_LIMIT) {
    list.insertAdjacentHTML('beforeend', `<div class="combobox-more" role="status">Showing ${COMBOBOX_RESULT_LIMIT} of ${matches.length}. Keep typing to narrow the list.</div>`);
  }
  list.classList.remove('hidden');
  input.setAttribute('aria-expanded', 'true');
}

function setSecurityComboboxValue(inputOrSelector, securityId, dispatch = false) {
  const input = typeof inputOrSelector === 'string' ? $(inputOrSelector) : inputOrSelector;
  const entry = entryForId(securityId);
  if (!input || !entry) return;
  input.dataset.securityId = securityId;
  input.value = securityDisplayLabel(entry.security);
  input.removeAttribute('aria-invalid');
  closeSecurityCombobox(input);
  if (dispatch) input.dispatchEvent(new Event('change', { bubbles: true }));
}

function wireSecurityCombobox(input) {
  if (!input || input.dataset.comboboxWired === '1') return;
  input.dataset.comboboxWired = '1';
  input.addEventListener('focus', () => renderSecurityCombobox(input));
  input.addEventListener('input', () => {
    delete input.dataset.securityId;
    clearSelectionMetadata(input);
    input.removeAttribute('aria-invalid');
    renderSecurityCombobox(input, input.value);
  });
  input.addEventListener('keydown', (event) => {
    const options = [...input.closest('[data-combobox]')?.querySelectorAll('.combobox-option') || []];
    const active = options.findIndex((option) => option.classList.contains('active'));
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!options.length) return;
      const next = event.key === 'ArrowDown' ? (active + 1) % options.length : (active - 1 + options.length) % options.length;
      options.forEach((option, index) => option.classList.toggle('active', index === next));
      options[next].scrollIntoView({ block: 'nearest' });
      input.setAttribute('aria-activedescendant', options[next].id);
    } else if (event.key === 'Enter' && active >= 0) {
      event.preventDefault();
      setSecurityComboboxValue(input, options[active].dataset.securityId, true);
    } else if (event.key === 'Escape') {
      closeSecurityCombobox(input);
    }
  });
  input.addEventListener('blur', () => setTimeout(() => {
    if (!input.closest('[data-combobox]')?.contains(document.activeElement)) closeSecurityCombobox(input);
  }, 0));
  input.closest('[data-combobox]')?.querySelector('.combobox-list')?.addEventListener('pointerdown', (event) => {
    const option = event.target.closest('.combobox-option');
    if (!option) return;
    event.preventDefault();
    setSecurityComboboxValue(input, option.dataset.securityId, true);
  });
}

function wireSecurityComboboxes() {
  $$('.form-combobox .combobox-input').forEach(wireSecurityCombobox);
}

function titleCase(value) {
  return String(value || '').split('_').join(' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatMoney(value, currency) {
  if (value === null || value === undefined || value === '') return '—';
  const amount = Number(value);
  if (!Number.isFinite(amount)) return '—';
  const prefix = currency === 'SGD' ? 'S$' : `${currency || 'USD'} `;
  return `${prefix}${new Intl.NumberFormat('en-SG', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(amount)}`;
}

function formatPercent(value) {
  if (value === null || value === undefined || value === '') return '—';
  const numeric = Number(value) * 100;
  const amount = Math.abs(numeric) < 0.005 ? 0 : numeric;
  return Number.isFinite(amount) ? `${amount >= 0 ? '+' : ''}${amount.toFixed(2)}%` : '—';
}

function formatRate(value) {
  const amount = Number(value);
  return Number.isFinite(amount) ? amount.toFixed(4) : '—';
}

function formatDate(value) {
  if (!value) return '—';
  const parsed = new Date(`${value}T00:00:00`);
  return Number.isNaN(parsed.valueOf()) ? value : new Intl.DateTimeFormat('en-SG', { day: '2-digit', month: 'short', year: 'numeric' }).format(parsed);
}

// --- S6.1: compute-mode indicator -------------------------------------------
// A small always-visible chip in the header meta area, injected via JS (no
// index.html / styles.css edits). It always shows what produced the most
// recent visible result: 'Local compute' (no adapter configured),
// 'Adapter · <origin>' (adapter configured), 'Local compute (adapter
// unavailable)' after an adapter failure fell back to the local engine, or
// The mode is provenance for the most recent visible result; it is surfaced
// in the result footer via setSourceLabel (S8 UX pass removed the header chip).

function setComputeMode(mode) {
  // S8 UX pass: the header stays minimal — the mode is provenance, surfaced
  // in the result footer (.result-source) rather than as a header chip.
  state.computeMode = mode;
}

function dividendCoverageNote(result) {
  const security = result.security || {};
  const coverage = result.dividend_coverage || {};
  if (security.distribution_policy === 'accumulating' || coverage.coverage_status === 'known_accumulating') {
    return 'Accumulating fund: distributions are reinvested internally; no investor cash dividends are expected.';
  }
  if (coverage.coverage_status === 'known_non_distributing') {
    return 'Non-distributing security: no investor cash dividends are expected.';
  }
  if (coverage.coverage_status === 'data_available_policy_unknown') {
    return 'Dividend events were found, but the security distribution policy is not yet verified.';
  }
  if (['dividend_data_missing', 'provider_error', 'unknown', 'known_distributing_with_no_events'].includes(coverage.coverage_status)) {
    return 'Dividend data is not confirmed for this security; $0 does not necessarily mean no dividend.';
  }
  return null;
}

async function loadJson(path, fallback = null) {
  try {
    const response = await fetch(path, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Could not load ${path}`);
    return await response.json();
  } catch (error) {
    console.warn(error.message);
    return fallback;
  }
}

async function apiGet(endpoint, params = {}) {
  // S6.2: apiGet is the adapter transport. It is only ever called when an
  // API base is configured (meta tag set — development/reference mode); the
  // guard keeps that true even if a future call site forgets, so a static
  // deployment can never emit runtime /api requests.
  if (!API_BASE) throw new Error('No adapter API base is configured; this session computes locally.');
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, value);
  });
  const path = `${API_BASE}/api${endpoint}${query.toString() ? `?${query}` : ''}`;
  const response = await fetch(path, { cache: 'no-store' });
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.error) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

function securityEntries() {
  const byId = new Map();
  state.catalog.forEach((entry) => {
    const security = entry?.security;
    if (security?.security_id && !byId.has(security.security_id)) byId.set(security.security_id, entry);
  });
  return [...byId.values()];
}

function entryForId(id) {
  return securityEntries().find(({ security }) => security.security_id === id) || null;
}

function entryForTicker(ticker) {
  const wanted = String(ticker || '').trim().toUpperCase();
  return securityEntries().find(({ security }) => security.ticker.toUpperCase() === wanted) || null;
}

function renderSecurityOptions() {
  wireSecurityComboboxes();
  const qqq = entryForTicker('QQQ') || securityEntries()[0];
  if (qqq) selectSecurity(qqq.security.security_id, false);
}

function renderUniverseOptions() {
  if (!has('#universe-filter')) return;
  const select = $('#universe-filter');
  const universes = [...new Set(state.catalog.map((entry) => entry.universe).filter(Boolean))].sort();
  select.innerHTML = '<option value="all">All universes</option>' + universes.map((universe) => `<option value="${escapeHtml(universe)}">${escapeHtml(universeLabel(universe))}</option>`).join('');
}

function renderDimensionOptions() {
  [['#market-filter', 'market', 'All markets'], ['#currency-filter', 'currency', 'All currencies']].forEach(([selector, field, label]) => {
    if (!has(selector)) return;
    const values = [...new Set(securityEntries().map(({ security }) => security[field]).filter(Boolean))].sort();
    $(selector).innerHTML = `<option value="all">${label}</option>${values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join('')}`;
  });
}

function filteredEntries() {
  const query = (has('#catalog-search') ? $('#catalog-search').value : '').trim().toLowerCase();
  const asset = has('#asset-filter') ? $('#asset-filter').value : 'all';
  const universe = has('#universe-filter') ? $('#universe-filter').value : 'all';
  const market = has('#market-filter') ? $('#market-filter').value : 'all';
  const currency = has('#currency-filter') ? $('#currency-filter').value : 'all';
  const distribution = has('#distribution-filter') ? $('#distribution-filter').value : 'all';
  const active = has('#active-filter') ? $('#active-filter').value : 'active';
  return securityEntries().filter(({ security, universe: entryUniverse }) => {
    const text = [security.ticker, security.name, security.isin, security.exchange, security.market].filter(Boolean).join(' ').toLowerCase();
    return (!query || text.includes(query))
      && (asset === 'all' || security.asset_type === asset)
      && (universe === 'all' || state.catalog.some(item => item.security?.security_id === security.security_id && item.universe === universe))
      && (market === 'all' || security.market === market)
      && (currency === 'all' || security.currency === currency)
      && (distribution === 'all' || security.distribution_policy === distribution)
      && (active === 'all' || (active === 'active' ? security.active !== false : security.active === false));
  });
}

function renderCatalog() {
  const entries = filteredEntries();
  if (has('#catalog-count')) $('#catalog-count').textContent = `${entries.length} ${entries.length === 1 ? 'security' : 'securities'} · published catalog`;
  const filters = ['asset','universe','market','currency','distribution','active'].map(name => {
    const field = $(`#${name}-filter`); return field && !['all','active'].includes(field.value) ? field.options[field.selectedIndex].textContent : null;
  }).filter(Boolean);
  if (has('#active-filters')) $('#active-filters').textContent = filters.length ? `Active filters: ${filters.join(' · ')}` : 'No advanced filters selected.';
  const visible = entries.slice(0, state.catalogLimit);
  if (has('#catalog-grid')) {
    $('#catalog-grid').innerHTML = visible.map(({ security, universe }) => `<button class="security-card" type="button" data-security-id="${escapeHtml(security.security_id)}">
      <span class="security-card-top"><span>${escapeHtml(security.exchange)} · ${escapeHtml(security.market)}</span><span class="security-tag">${escapeHtml(security.asset_type)}</span></span>
      <span><strong class="security-ticker">${escapeHtml(security.ticker)}</strong><span class="security-name">${escapeHtml(security.name)}</span></span>
      <span class="security-card-bottom"><span>${escapeHtml(security.currency)} · ${escapeHtml(security.distribution_policy || 'unknown')}</span><span>${escapeHtml(universeLabel(universe))} ↗</span></span>
      <span class="coverage-preview">${escapeHtml(discoveryCoverage(security.security_id))}</span>
    </button>`).join('') || '<div class="catalog-empty">No securities match. Clear the search or filters to try again.</div>';
    $$('.security-card').forEach((card) => card.addEventListener('click', () => { selectSecurity(card.dataset.securityId, true); s7OnSecurityCardPicked(card.dataset.securityId); }));
  }
  if (has('#catalog-more')) {
    $('#catalog-more').classList.toggle('hidden', entries.length <= state.catalogLimit);
    $('#catalog-more').textContent = entries.length > state.catalogLimit ? `Show ${Math.min(100, entries.length - state.catalogLimit)} more` : 'All securities shown';
  }
}

function selectSecurity(securityId, moveToForm = false) {
  const entry = entryForId(securityId);
  if (!entry) return;
  state.selectedSecurityId = securityId;
  if (has('#security-select')) setSecurityComboboxValue('#security-select', securityId);
  const security = entry.security;
  if (has('#security-hint')) $('#security-hint').textContent = `${security.exchange} · ${security.currency} · ${titleCase(security.distribution_policy || 'unknown')}${security.active === false ? ' · Inactive' : ''}`;
  if (has('#security-domicile')) $('#security-domicile').textContent = security.domicile || 'Not published';
  if (has('#security-isin')) $('#security-isin').textContent = security.isin || 'Not published';
  if (has('#security-expense')) $('#security-expense').textContent = security.expense_ratio === null || security.expense_ratio === undefined ? 'Metadata only' : `${security.expense_ratio}% · metadata only`;
  if (moveToForm && has('#analyse')) $('#analyse').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function syncPreset(preset) {
  const values = PRESETS[preset];
  if (!values) return;
  if (has('#dividends-toggle')) $('#dividends-toggle').checked = values.dividends;
  if (has('#tax-toggle')) $('#tax-toggle').checked = values.withholding;
  if (has('#reinvest-toggle')) $('#reinvest-toggle').checked = values.reinvest;
}

function scenarioValues(prefix = '') {
  const source = prefix ? { dividends: $(`#${prefix}-dividends`)?.checked, withholding: $(`#${prefix}-withholding`)?.checked, reinvest: $(`#${prefix}-reinvest`)?.checked } : {
    dividends: has('#dividends-toggle') ? $('#dividends-toggle').checked : true,
    withholding: has('#tax-toggle') ? $('#tax-toggle').checked : true,
    reinvest: has('#reinvest-toggle') ? $('#reinvest-toggle').checked : true,
  };
  return { dividends: source.dividends !== false, withholding: source.withholding !== false, reinvest: source.reinvest !== false };
}

function requestKey(kind, fields) {
  const canonical = Object.keys(fields).sort().map((key) => `${key}=${String(fields[key])}`).join('&');
  return `${kind}:${canonical}`;
}

const resultViews = Object.fromEntries(['analysis', 'dca', 'compare', 'portfolio'].map(kind =>
  [kind, { phase: 'empty', request: null, artifact: null }]));

function viewSummary(kind, request) {
  if (!request) return '';
  if (kind === 'portfolio') return `${request.transactions.length} transactions · as of ${request.as_of}`;
  const security = entryForId(request.security_id)?.security;
  const name = security?.ticker || request.tickers || request.security_id;
  const amount = kind === 'dca' ? `${request.initial_sgd || '0'} SGD initial + ${request.contribution_sgd} SGD ${request.frequency}` : `${request.initial_sgd} SGD initial`;
  return `${name} · ${request.start_date} → ${request.end_date} · ${amount}`;
}

function viewForm(kind) { return $(kind === 'dca' ? '#analysis-form' : `#${kind}-form`); }
function activeSimulatorKind() { return state.simulatorMode === 'regular' ? 'dca' : 'analysis'; }

function renderViewState(kind) {
  const view = resultViews[kind];
  const form = viewForm(kind);
  if (!form) return;
  let notice = $(`#${kind}-request-state`);
  if (!notice) {
    notice = document.createElement('p'); notice.id = `${kind}-request-state`;
    notice.className = 'request-state'; notice.setAttribute('role', 'status');
    const output = $({ analysis: '#result-content', dca: '#dca-results', compare: '#compare-results', portfolio: '#portfolio-results' }[kind]);
    output.before(notice);
  }
  const active = !['analysis','dca'].includes(kind) || activeSimulatorKind() === kind;
  if (active) form.dataset.resultState = view.phase;
  notice.dataset.state = view.phase;
  const current = view.phase === 'current';
  const labels = { empty: '', pending: 'Calculate to update.', loading: 'Calculating the submitted request…', invalid: 'Check the inputs.', failed: 'Calculation failed. Try again.', current: 'Current result' };
  notice.textContent = view.request
    ? `${current ? 'Current result' : 'Previous result — inputs changed'}. ${viewSummary(kind, view.request)}${current ? '' : ` · ${labels[view.phase] || 'Select Update results to recalculate.'}`}`
    : labels[view.phase] ?? labels.pending;
  if (view.request && !current && kind !== 'portfolio') notice.textContent += ` · Dividends ${view.request.dividends ? 'on' : 'off'}, withholding ${view.request.withholding ? 'on' : 'off'}, reinvestment ${view.request.reinvest ? 'on' : 'off'}`;
  const button = form.querySelector('button[type="submit"]');
  if (button && active && view.phase !== 'loading') {
    setBusy(button, false); delete form.dataset.s7Inflight;
    button.textContent = view.request ? 'Update results' : 'Calculate';
    button.dataset.originalLabel = button.innerHTML;
  }
  notice.hidden = !notice.textContent || (['analysis','dca'].includes(kind) && !active);
  if (kind === 'dca' && has('[data-download-dca]')) { $('[data-download-dca]').textContent = current ? 'Download this result JSON' : 'Download JSON · previous request'; $('[data-download-dca]').title = viewSummary(kind,view.request); }
  if (kind === 'analysis') {
    [['#download-result', 'Download JSON'], ['#copy-link', 'Copy analysis link'], ['#download-series-csv', 'Download CSV']].forEach(([sel,label]) => {
      const control = $(sel); if (!control) return;
      control.textContent = view.request && !current ? `${label} · previous request` : label;
      control.disabled = !view.request;
      control.title = view.request ? viewSummary(kind, view.request) : 'Calculate first';
    });
  }
}

function editView(kind) {
  s7CancelAutoRun(kind);
  if (kind === 'compare') {
    if ($('#compare-progress')) $('#compare-progress').innerHTML = '';
    if ($('#compare-error')) $('#compare-error').textContent = '';
  }
  if (kind === 'dca') s4State.runSeq = (s4State.runSeq || 0) + 1;
  else s6Runs[kind] += 1;
  resultViews[kind].phase = 'pending'; resultViews[kind].error = '';
  if (['analysis','dca'].includes(kind) && activeSimulatorKind() === kind && has('#form-error')) $('#form-error').textContent = '';
  renderViewState(kind);
}

function beginView(kind) {
  editView(kind);
  resultViews[kind].phase = 'loading'; renderViewState(kind);
}

function completeView(kind, request, artifact) {
  const view = resultViews[kind];
  view.request = Object.freeze(JSON.parse(JSON.stringify(request)));
  view.artifact = artifact; view.phase = 'current'; view.error = '';
  renderViewState(kind);
}

function failView(kind, phase = 'failed') {
  resultViews[kind].phase = phase;
  if (['analysis','dca'].includes(kind)) resultViews[kind].error = $('#form-error')?.textContent || '';
  renderViewState(kind);
}

function analysisLink() {
  const result = state.artifact?.result;
  if (!result) return window.location.href;
  const request = resultViews.analysis.request || state.artifact.request || {};
  const params = new URLSearchParams({
    security_id: result.security.security_id,
    start_date: request.start_date || result.period.start_date,
    end_date: request.end_date || result.period.end_date,
    initial_sgd: String(request.initial_sgd || result.initial_investment_sgd),
    dividends: String(request.dividends ?? true),
    withholding: String(request.withholding ?? true),
    reinvest: String(request.reinvest ?? true),
    methodology_version: state.artifact.methodology_version || '1.0',
    data_snapshot_id: state.artifact.data_snapshot_id || 'local-canonical-parquet',
  });
  return `${window.location.origin}${window.location.pathname}?${params.toString()}#analyse`;
}

async function copyAnalysisLink() {
  const button = $('#copy-link');
  try {
    await navigator.clipboard.writeText(analysisLink());
    button.textContent = 'Link copied';
    setTimeout(() => { button.textContent = 'Copy analysis link'; }, 1800);
  } catch (error) {
    button.textContent = 'Copy unavailable';
    setTimeout(() => { button.textContent = 'Copy analysis link'; }, 1800);
  }
}

function displayValues(result) {
  const native = state.currencyMode === 'native';
  return {
    currency: native ? result.security.currency : 'SGD',
    initial: native ? result.initial_investment_foreign_currency : result.initial_investment_sgd,
    final: native ? result.investment.final_value_foreign_currency : result.investment.final_value_sgd,
    totalReturn: native ? result.returns.total_return_foreign_currency : result.returns.total_return,
    cagr: native ? result.returns.cagr_foreign_currency : result.returns.cagr,
    priceReturn: native ? result.price_return.foreign_currency : result.price_return.sgd,
    grossDividend: native ? result.dividends.gross_foreign_currency : result.dividends.gross_sgd_at_payment,
    tax: native ? result.dividends.withholding_tax_foreign_currency : result.dividends.withholding_tax_sgd_at_payment,
    netDividend: native ? result.dividends.net_foreign_currency : result.dividends.net_sgd_at_payment,
  };
}

function renderResult() {
  const result = state.artifact?.result;
  if (!result) return;
  const values = displayValues(result);
  const security = result.security;
  if (security.currency === 'SGD') state.currencyMode = 'sgd';
  $('#result-title').textContent = security.ticker;
  $('#result-subtitle').textContent = security.name;
  $('#result-asset-type').textContent = titleCase(security.asset_type);
  $('#result-exchange').textContent = security.exchange;
  $('#result-distribution').textContent = titleCase(security.distribution_policy || 'unknown');
  $('#headline-currency').textContent = values.currency;
  $('#final-value').textContent = formatMoney(values.final, values.currency);
  $('#result-period').textContent = `Resolved trading dates · ${formatDate(result.period.start_date)} → ${formatDate(result.period.end_date)}`;
  if (has('#security-value-note')) $('#security-value-note').textContent = `Final security value · ${formatMoney(result.investment.final_security_value_foreign_currency, security.currency)} native`;
  $('#total-return').textContent = formatPercent(values.totalReturn);
  $('#total-return').parentElement.classList.toggle('negative', Number(values.totalReturn) < 0);
  $('#initial-value').textContent = formatMoney(values.initial, values.currency);
  $('#initial-caption').textContent = state.currencyMode === 'native' ? 'Native amount at start FX' : 'SGD starting capital';
  $('#cagr-value').textContent = formatPercent(values.cagr);
  $('#price-return').textContent = formatPercent(values.priceReturn);
  $('#price-caption').textContent = state.currencyMode === 'native' ? `Native ${security.currency} close-to-close` : 'SGD price return, including FX';
  $('#fx-value').textContent = `${formatRate(result.fx.start_rate)} → ${formatRate(result.fx.end_rate)}`;
  $('#fx-value').closest('article').classList.toggle('hidden', security.currency === 'SGD');
  $('#fx-value').nextElementSibling.textContent = `1 ${security.currency} = S$${formatRate(result.fx.start_rate)} at purchase; S$${formatRate(result.fx.end_rate)} at valuation`;
  renderCoverage('analysis', result, state.analysisCoverage);
  $('#gross-dividend').textContent = formatMoney(values.grossDividend, values.currency);
  $('#tax-value').textContent = formatMoney(values.tax, values.currency);
  $('#net-dividend').textContent = formatMoney(values.netDividend, values.currency);
  if (has('#cash-dividend')) $('#cash-dividend').textContent = state.currencyMode === 'native' ? formatMoney(result.dividends.cash_foreign_currency, security.currency) : `${formatMoney(result.dividends.cash_foreign_currency, security.currency)} native detail`;
  if (has('#dividend-note')) $('#dividend-note').textContent = dividendCoverageNote(result) || (state.currencyMode === 'native' ? (result.methodology.dividend_reinvestment === 'pay_date_close_with_30_day_ex_date_fallback' ? 'Net dividends reinvested at the resolved payment-date close.' : 'Net dividends retained as cash.') : 'SGD translation uses the resolved payment-date FX rate.');
  renderResultSource();
  renderQuality(result.data_quality);
  $$('.currency-button').forEach((button) => {
    button.classList.toggle('hidden', button.dataset.currency === 'native' && security.currency === 'SGD');
    const active = button.dataset.currency === state.currencyMode;
    button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active)); button.textContent = button.dataset.currency === 'native' ? security.currency : 'SGD';
  });
  renderSeries(state.series?.result || state.series);
}

function renderResultSource() {
  // S6.1: the result footer names the producer of the visible numbers, so
  // the init-time demo replay can never be mistaken for a computed request.
  const source = document.querySelector('.result-source span');
  if (!source) return;
  const labels = {
    demo: 'Example replay · published artifact',
    local: 'Computed locally in your browser',
    adapter: 'Adapter result',
    adapterFallback: 'Computed locally in your browser (adapter unavailable)',
  };
  const label = labels[state.artifactSource] || 'Published result artifact';
  const version = state.artifact?.methodology_version || state.artifact?.result?.methodology?.methodology_version || '1.0';
  source.innerHTML = `<span class="tiny-dot"></span> ${escapeHtml(label)} · methodology <span id="method-version">${escapeHtml(String(version))}</span>`;
  if (has('#example-badge')) $('#example-badge').classList.toggle('hidden', state.artifactSource !== 'demo');
}

function coverageFromInputs(entry, inputs, manifest) {
  const priceDates = inputs.prices.map(row => row.trading_date).sort();
  const fxDates = inputs.fxRates.filter(row => row.base_currency === inputs.security.currency).map(row => row.rate_date).sort();
  return {
    latestSecurity: entry.last_date || priceDates.at(-1),
    latestFx: manifest.fx?.coverage?.[inputs.security.currency]?.last_date || fxDates.at(-1),
    snapshot: manifest.generated_at || null,
    snapshotId: inputs.dataSnapshotId,
  };
}

function renderCoverage(kind, result, coverage = {}) {
  const request = resultViews[kind].request;
  if (!request) return;
  const dcaPoints = state.dcaContext.series?.points;
  const actual = result.period || (kind === 'dca' && dcaPoints?.length ? { start_date: result.contribution_dates[0], end_date: dcaPoints.at(-1).date } : null);
  const resolved = actual ? `${actual.start_date} → ${actual.end_date}` : 'Not separately published by this result';
  const truncated = actual && (actual.start_date !== request.start_date || actual.end_date !== request.end_date);
  const warnings = result.data_quality?.warnings || [];
  const groups = { 'Dates and FX': [], 'Dividends and tax': [], 'Data and other notes': [] };
  warnings.forEach(w => groups[/date|stale|fx|coverage/i.test(w) ? 'Dates and FX' : /dividend|tax|withholding/i.test(w) ? 'Dividends and tax' : 'Data and other notes'].push(w));
  const detail = Object.entries(groups).filter(([,items])=>items.length).map(([label,items]) => `<details><summary>${escapeHtml(label)} (${items.length})</summary>${items.map(item=>`<p>${escapeHtml(item)}</p>`).join('')}</details>`).join('');
  const html = `<details><summary>${warnings.length ? `${warnings.length} data note${warnings.length === 1 ? '' : 's'}` : 'Data details'}${truncated ? ' · dates adjusted' : ''}</summary><strong>${truncated ? 'Dates resolved within available trading history' : 'Dates, coverage and data notes'}</strong><p>Requested: ${escapeHtml(request.start_date)} → ${escapeHtml(request.end_date)}<br>Resolved: ${escapeHtml(resolved)}<br>Latest published security date: ${escapeHtml(coverage.latestSecurity || 'Not published')}<br>${result.security.currency !== 'SGD' ? `Latest published ${escapeHtml(result.security.currency)}/SGD FX date: ${escapeHtml(coverage.latestFx || 'Not published')}<br>` : ''}Snapshot date: ${escapeHtml(coverage.snapshot || 'Not published')} · ID: ${escapeHtml(coverage.snapshotId || resultViews[kind].artifact?.data_snapshot_id || 'Not published')}</p><p>${warnings.length} material data note${warnings.length === 1 ? '' : 's'} attached to this result.${truncated ? ' Requested and resolved dates differ; review the actual period before interpreting returns.' : ''}</p>${detail}<button type="button" class="text-button" data-review-dates="${kind}">Review requested dates</button></details>`;
  let box = $(`#${kind}-coverage`);
  if (!box) { box = document.createElement('div'); box.id = `${kind}-coverage`; box.className = 'coverage-summary'; }
  if (kind === 'analysis') $('#result-period').after(box);
  else $('#dca-results .analysis-output')?.append(box);
  box.innerHTML = html;
  box.querySelector('button').addEventListener('click', () => $('#start-date').focus());
}

function renderQuality(quality = {}) {
  const warnings = quality.warnings || [];
  if (!has('#quality-badge')) return;
  $('#quality-badge').classList.toggle('ok', quality.status === 'OK');
  $('#quality-label').textContent = quality.status === 'OK' ? 'Data quality OK' : 'Review warnings';
  $('#warning-count').textContent = `${warnings.length} item${warnings.length === 1 ? '' : 's'} to review`;
  $('#warning-list').innerHTML = warnings.map((warning) => `<div>${escapeHtml(warning)}</div>`).join('') || '<div>No warnings attached to this result.</div>';
  $('#warnings-card').classList.toggle('hidden', !warnings.length);
  $('#warning-list').classList.toggle('hidden', !state.warningsOpen);
  $('#warnings-toggle').innerHTML = state.warningsOpen ? 'Hide <span aria-hidden="true">↑</span>' : 'Show <span aria-hidden="true">↓</span>';
  $('#warnings-toggle').setAttribute('aria-expanded', String(state.warningsOpen));
}

function chartModel(series, native) {
  if (!series?.points?.length) return null;
  const currency = native ? series.security.currency : 'SGD';
  const values = series.points.map(point => Number(native ? point.native_close : point.sgd_close));
  const min = Math.min(...values), max = Math.max(...values), spread = max-min || 1;
  const points = values.map((value,i)=>`${140+i/Math.max(1,values.length-1)*785},${225-(value-min)/spread*185}`).join(' ');
  const ticks = [0,.5,1].map(f=>{const y=225-f*185; return `<text x="130" y="${y+4}" text-anchor="end">${(min+f*spread).toFixed(2)}</text><line x1="140" y1="${y}" x2="925" y2="${y}" stroke="#cdd5d8"/>`;}).join('');
  const svg=`<g fill="#526277" font-size="20">${ticks}<text x="140" y="255">${series.points[0].date}</text><text x="925" y="255" text-anchor="end">${series.points.at(-1).date}</text></g><polyline fill="none" stroke="#376f64" stroke-width="3" points="${points}"/>`;
  return {currency,svg};
}
function priceChartHtml(series,native) {
  const chart=chartModel(series,native);if(!chart)return '<p class="detail-note">Price history chart is not available for this result.</p>';
  return `<h4>Price history · ${escapeHtml(chart.currency)}</h4><p class="detail-note">Daily closing price, not investment value or total return.</p><svg viewBox="0 0 1000 270" role="img" aria-label="${escapeHtml(chart.currency)} closing price history">${chart.svg}</svg><details><summary>View price table</summary><div class="holding-table-wrap"><table class="series-table"><thead><tr><th>Date</th><th>Close (${escapeHtml(chart.currency)})</th></tr></thead><tbody>${series.points.map(p=>`<tr><td>${escapeHtml(p.date)}</td><td>${escapeHtml(native?p.native_close:p.sgd_close)}</td></tr>`).join('')}</tbody></table></div></details>`;
}
function renderSeries(series) {
  if (!has('#series-chart')) return;
  const chart=chartModel(series,state.currencyMode==='native');
  $('#series-card').classList.toggle('hidden',!chart);if(!chart)return;
  $('#series-chart').innerHTML=chart.svg;
  $('#series-chart').setAttribute('aria-label',`${chart.currency} closing price history`);
  $('#series-card h4').textContent=`Price history · ${chart.currency}`;
  $('#series-range').textContent=`${series.points[0].date} → ${series.points.at(-1).date}`;
  if(has('#native-legend')) $('#native-legend').textContent=`${chart.currency} close — not investment value`;
  if(has('.sgd-line')) $('.sgd-line').parentElement.classList.add('hidden');
  if(has('.chart-source')) $('.chart-source').textContent='';
  renderSeriesTable(series);
}

function renderSeriesTable(series) {
  const wrap = $('#series-table-wrap');
  if (!wrap || !series?.points?.length) return;
  const currency = series.security?.currency || 'native';
  const rows = series.points.map((point) => `<tr><th scope="row"><time datetime="${escapeHtml(point.date)}">${escapeHtml(formatDate(point.date))}</time></th><td>${escapeHtml(formatRate(point.native_close))} ${escapeHtml(currency)}</td><td>${escapeHtml(formatRate(point.sgd_close))} SGD</td></tr>`).join('');
  wrap.innerHTML = `<table class="series-table"><caption>Daily native and SGD closing prices</caption><thead><tr><th scope="col">Date</th><th scope="col">Native close</th><th scope="col">SGD close</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function seriesForDownload() {
  const series = state.series?.result || state.series;
  return series?.points?.length ? series : null;
}

function downloadSeriesCsv() {
  const series = seriesForDownload();
  if (!series) return;
  const currency = series.security?.currency || 'native';
  const lines = [['date', `${currency.toLowerCase()}_native_close`, 'sgd_close'], ...series.points.map((point) => [point.date, point.native_close, point.sgd_close])];
  const csv = lines.map((row) => row.map((value) => `"${String(value ?? '').replaceAll('"', '""')}"`).join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `sg-invest-${series.security?.ticker || 'series'}.csv`; link.click(); URL.revokeObjectURL(link.href);
}

function focusRenderedHeading(containerSelector) {
  const heading = document.querySelector(`${containerSelector} h3, ${containerSelector} h2`);
  if (!heading) return;
  heading.tabIndex = -1;
  heading.focus({ preventScroll: true });
}

function showResult({ focus = false } = {}) {
  $('#result-empty').classList.add('hidden'); $('#artifact-unavailable').classList.add('hidden'); $('#result-content').classList.remove('hidden'); renderResult();
  if (focus) focusRenderedHeading('#result-content');
}

function showUnavailable(message = 'This request is not available for the selected date range.') {
  $('#result-empty').classList.add('hidden'); $('#result-content').classList.add('hidden'); $('#artifact-unavailable').classList.remove('hidden');
  const copy = $('#artifact-unavailable p:not(.eyebrow)'); if (copy && message) copy.textContent = message;
}

function setBusy(button, busy) {
  if (!button) return;
  button.disabled = busy; button.dataset.originalLabel ||= button.innerHTML;
  button.innerHTML = busy ? 'Computing result…' : button.dataset.originalLabel;
}

// S6 run-state for request isolation (same defense as S4's DCA runSeq):
// each submit bumps its panel's sequence; a late response whose sequence is
// no longer current renders nothing and resets no shared UI state.
const s6Runs = { analysis: 0, compare: 0, portfolio: 0 };

function s6RunCurrent(kind, seq) {
  return s6Runs[kind] === seq;
}

function s6SetButtonProgress(button, label) {
  if (!button) return;
  button.dataset.originalLabel ||= button.innerHTML;
  button.innerHTML = escapeHtml(label);
}

// Per-view run counters retained for browser verification. Financial edits do not run.
const s7Reactive = {
  timers: { series: null, analysis: null, dca: null, portfolio: null },
  runs: { series: 0, analysis: 0, dca: 0, portfolio: 0 },
  seriesSecurityId: null,
};
let s7LastAnalyzeId = null;
// Read-only introspection for the headless browser tests (runs counters +
// series provenance); nothing in the app reads it back.
window.__sgInvestReactive = s7Reactive;

// Explicit submission captures the financial request; edits invalidate it immediately.
async function submitAnalysis(event) {
  event.preventDefault();
  if (state.simulatorMode === 'regular') { await s7RunDca({ mode: 'force' }); return; }
  s7CancelAutoRun('analysis');
  await s7RunAnalysis({ mode: 'force' });
}

async function s7RunAnalysis({ mode = 'force' } = {}) {
  const form = $('#analysis-form');
  if (!form) return;
  beginView('analysis');
  const error = $('#form-error'); error.textContent = '';
  const amount = Number($('#initial-amount').value);
  if (!Number.isFinite(amount) || amount <= 0) { error.textContent = 'Enter an initial amount greater than S$0.'; failView('analysis', 'invalid'); return; }
  if (!$('#start-date').value || !$('#end-date').value || $('#end-date').value < $('#start-date').value) { error.textContent = 'Choose an end date on or after the start date.'; failView('analysis', 'invalid'); return; }
  const entry = entryForId(securityComboboxValue('#security-select')); if (!entry) { error.textContent = 'Choose a security from the published catalog.'; $('#security-select')?.setAttribute('aria-invalid', 'true'); failView('analysis', 'invalid'); return; }
  const scenario = scenarioValues();
  const request = { security_id: entry.security.security_id, initial_sgd: $('#initial-amount').value, start_date: $('#start-date').value, end_date: $('#end-date').value, ...scenario };
  const button = form.querySelector('button[type="submit"]'); setBusy(button, true);
  const runSeq = s6Runs.analysis += 1;
  s7Reactive.runs.analysis += 1;
  form.dataset.s7Inflight = '1';
  try {
    if (API_BASE) {
      try {
        const key = requestKey('analysis', { ...request, methodology_version: '1.0', data_snapshot_id: 'local-canonical-parquet' });
        const artifact = await apiGet('/analyze', { ...request, request_key: key });
        const series = await apiGet('/series', { security_id: request.security_id, start_date: request.start_date, end_date: request.end_date }).catch(() => null);
        if (!s6RunCurrent('analysis', runSeq)) return;
        state.analysisCoverage = {};
        state.artifact = artifact; state.artifactSource = 'adapter'; state.series = series; state.seriesSource = null;
        error.textContent = '';
        completeView('analysis', request, artifact);
        showResult({ focus: mode === 'force' });
        setComputeMode('adapter');
        return;
      } catch (adapterError) {
        if (!s6RunCurrent('analysis', runSeq)) return;
        error.textContent = `${adapterError.message} — falling back to the local engine.`;
      }
    }
    s6SetButtonProgress(button, 'Resolving published data packs…');
    const outcome = await s6AnalysisViaPacks({
      securityId: request.security_id,
      label: entry.security.ticker,
      initial_sgd: request.initial_sgd,
      start_date: request.start_date,
      end_date: request.end_date,
      dividends: scenario.dividends,
      withholding: scenario.withholding,
      reinvest: scenario.reinvest,
    }, (label) => { if (s6RunCurrent('analysis', runSeq)) s6SetButtonProgress(button, label); }, { supersede: true, previousEngineId: s7LastAnalyzeId, isCurrent: () => s6RunCurrent('analysis', runSeq) });
    if (!s6RunCurrent('analysis', runSeq)) return;
    state.analysisCoverage = outcome.coverage;
    state.artifact = outcome.envelope;
    state.artifactSource = API_BASE ? 'adapterFallback' : 'local';
    state.series = outcome.series;
    state.seriesSource = 'local';
    error.textContent = '';
    completeView('analysis', request, state.artifact);
    showResult({ focus: mode === 'force' });
    setComputeMode(state.artifactSource);
  } catch (computeError) {
    if (!s6RunCurrent('analysis', runSeq)) return;
    failView('analysis');
    if (!state.artifact) showUnavailable(computeError.message);
    error.textContent = computeError.message;
  } finally {
    if (s6RunCurrent('analysis', runSeq)) { setBusy(button, false); delete form.dataset.s7Inflight; }
  }
}

// S12: manifest boundaries preview availability; engine periods prove equality.
const COMPARE_SCENARIO_LABELS = { custom: 'Copied custom assumptions', investor: 'Singapore investor', price: 'Price only', gross: 'Gross total return', cash: 'Cash dividends' };
const compareCoverageCache = new Map();

function compareTickerFor(securityId) {
  return entryForId(securityId)?.security.ticker || String(securityId || '');
}

function compareCoverage(securityId) {
  const cached = compareCoverageCache.get(securityId);
  return cached?.window || securityWindow({ securityId });
}

async function loadComparisonCoverage(securityId) {
  if (compareCoverageCache.has(securityId)) return compareCoverageCache.get(securityId).promise;
  const cached = { window: securityWindow({ securityId }), promise: null };
  compareCoverageCache.set(securityId, cached);
  cached.promise = (async () => {
    for (const loader of [packs, packsRemote].filter(Boolean)) {
      try {
        const manifest = await loader.loadManifest();
        const entry = manifest.securities?.find(item => item.security_id === securityId);
        if (!entry) continue;
        const currency = entry.native_currency || entryForId(securityId)?.security.currency;
        cached.window = securityWindow({ securityId, currency, entry, fx: manifest.fx?.coverage?.[currency] });
        cached.window.status = entry.status;
        cached.window.origin = loader === packs ? 'Pages' : 'External data origin';
        return cached.window;
      } catch { /* Keep trying the configured origin; calculation validates again. */ }
    }
    return cached.window;
  })();
  await cached.promise;
  renderCompareCoverage();
  return cached.window;
}

function compareWindowPlan() {
  const windows = state.compareTickers.map(compareCoverage);
  const common = commonWindow(windows);
  const requested = { start: $('#compare-start')?.value || '', end: $('#compare-end')?.value || '' };
  return { windows, common, requested, resolved: resolveWindow(requested, common) };
}

function renderCompareCoverage() {
  const container = $('#compare-coverage');
  const custom = $('#compare-scenario')?.querySelector('option[value="custom"]');
  if (custom) custom.disabled = !state.compareCopiedScenario;
  if (!state.compareCopiedScenario && $('#compare-scenario')?.value === 'custom') $('#compare-scenario').value = 'investor';
  const scenario = ($('#compare-scenario')?.value === 'custom' ? state.compareCopiedScenario : PRESETS[$('#compare-scenario')?.value]) || PRESETS.investor;
  if ($('#compare-assumptions')) $('#compare-assumptions').textContent = `Dividends ${scenario.dividends ? 'on' : 'off'}, withholding ${scenario.withholding ? 'on' : 'off'}, reinvestment ${scenario.reinvest ? 'on' : 'off'}`;
  if (!container) return;
  if (!state.compareTickers.length) {
    container.innerHTML = '';
    return;
  }
  state.compareTickers.forEach(id => { if (!compareCoverageCache.has(id)) void loadComparisonCoverage(id); });
  const plan = compareWindowPlan();
  const shared = plan.common.ok && plan.windows.length >= COMPARE_MIN;
  const proposed = plan.resolved.ok ? plan.resolved : plan.common;
  const commonLine = shared
    ? `<p class="compare-common"><span class="summary-label">Shared history</span><strong>${escapeHtml(plan.common.start)} → ${escapeHtml(plan.common.end)}</strong></p>`
    : `<p class="compare-common">${escapeHtml(plan.windows.length < COMPARE_MIN ? 'Add a second security to preview shared dates.' : plan.common.reason || 'Shared coverage is unknown.')}</p>`;
  const action = shared && (proposed.start !== plan.requested.start || proposed.end !== plan.requested.end)
    ? `<button type="button" class="text-button" data-use-common-window>Use shared dates: ${escapeHtml(proposed.start)} → ${escapeHtml(proposed.end)}</button>` : '';
  const rows = plan.windows.map(item => `<li data-coverage-state="${escapeHtml(item.state)}"><span class="coverage-ticker">${escapeHtml(compareTickerFor(item.securityId))}</span><span class="coverage-dates">${item.state === 'ready' ? `${escapeHtml(item.start)} → ${escapeHtml(item.end)}` : item.state === 'unavailable' ? 'Unavailable' : 'Coverage unknown'}</span><span class="coverage-note">${escapeHtml(item.reason || `${item.origin} · ${item.status || 'coverage'}${item.fxLimited ? ` · ${item.currency}/SGD limits this preview` : ''}`)}</span></li>`).join('');
  container.innerHTML = `${commonLine}<ul class="coverage-list">${rows}</ul>${action}<p class="detail-note">Trading dates may differ. Actual periods appear on each result.</p>`;
}

function compareStatus(row) {
  switch (row.state) {
    case 'ready': return { label: 'Compared', tone: 'ok' };
    case 'loading': return { label: 'Calculating', tone: '' };
    case 'pending': return { label: 'Queued', tone: '' };
    case 'unavailable': return { label: 'Unavailable', tone: 'muted' };
    case 'invalid': return { label: 'Not comparable', tone: '' };
    default: return { label: 'Failed', tone: 'bad' };
  }
}

// One card per selected security so equal or unequal periods are visible
// without reading a table, and so failures explain themselves in place.
function compareCard(row, context = {}) {
  const result = row.result;
  const ticker = escapeHtml(result?.security?.ticker || row.ticker || compareTickerFor(row.securityId));
  const name = result?.security?.name || entryForId(row.securityId)?.security.name || '';
  const status = compareStatus(row);
  const open = `<article class="compare-card" data-security-id="${escapeHtml(row.securityId)}" data-compare-state="${escapeHtml(row.state)}" aria-busy="${['loading', 'pending'].includes(row.state)}">`;
  const head = `<header class="compare-card-head"><div class="compare-card-id"><p class="compare-card-ticker">${ticker}</p><p class="compare-card-name">${escapeHtml(name)}</p><p class="compare-card-name">${escapeHtml(result?.security?.exchange || entryForId(row.securityId)?.security.exchange || '')} · ${escapeHtml(result?.security?.currency || row.window?.currency || '')}</p></div><span class="status-chip ${status.tone}">${status.label}</span></header>`;
  if (row.state !== 'ready' || !result) {
    const reason = row.reason || (row.state === 'loading' ? 'Calculating the submitted dates…' : row.state === 'pending' ? 'Queued for this request.' : 'No usable result was returned.');
    return `${open}${head}<p class="compare-card-reason">${escapeHtml(reason)}</p>${row.errorDetail ? `<details class="compare-card-details"><summary>Error details</summary><p>${escapeHtml(row.errorDetail)}</p></details>` : ''}</article>`;
  }
  const period = result.period;
  const quality = result.data_quality || {};
  const warnings = Array.isArray(quality.warnings) ? quality.warnings : [];
  const disclosure = dividendCoverageNote(result);
  const currency = result.security.currency;
  const dates = `${period.start_date} → ${period.end_date}`;
  const metric = (label, value, primary = false) => `<div class="compare-metric ${primary ? 'is-primary' : 'is-secondary'}"><dt>${escapeHtml(label)}</dt><dd>${value}<small class="metric-period">${escapeHtml(dates)}</small></dd></div>`;
  const changed = period.start_date !== context.requested?.start || period.end_date !== context.requested?.end;
  const coverage = row.window;
  const dataStatus = warnings.length || disclosure || (quality.status && quality.status !== 'OK') ? 'Review data notes' : quality.status === 'OK' ? 'Data quality OK' : 'Data quality not reported';
  return `${open}${head}
    <dl class="compare-card-metrics">
      ${metric('Ending value · SGD', formatMoney(result.investment.final_value_sgd, 'SGD'), true)}
      ${metric('Total return · SGD (%)', formatPercent(result.returns.total_return), true)}
      ${metric(`Native total return · ${currency} (%)`, formatPercent(result.returns.total_return_foreign_currency))}
    </dl>
    <p class="compare-actual-period">Actual period: <strong>${escapeHtml(dates)}</strong>${changed ? ' · Adjusted to available trading days.' : ''}</p>
    <details class="compare-card-details"><summary>${escapeHtml(dataStatus)} · ${warnings.length} warning${warnings.length === 1 ? '' : 's'}</summary>
      ${disclosure ? `<p>${escapeHtml(disclosure)}</p>` : ''}
      ${warnings.length ? `<ul>${warnings.map(warning => `<li>${escapeHtml(warning)}</li>`).join('')}</ul>` : '<p>No warnings.</p>'}
      <dl class="compare-provenance">
        <div><dt>Published coverage preview</dt><dd>${coverage?.start && coverage?.end ? `${escapeHtml(coverage.start)} → ${escapeHtml(coverage.end)}` : 'Unknown'}</dd></div>
        <div><dt>Coverage status</dt><dd>${escapeHtml(coverage?.status || coverage?.state || 'unknown')}</dd></div>
        <div><dt>Snapshot</dt><dd>${escapeHtml(row.snapshotId || 'Not reported')}</dd></div>
        <div><dt>Methodology</dt><dd>${escapeHtml(row.methodologyVersion || 'Not reported')}</dd></div>
        <div><dt>Calculation source</dt><dd>${escapeHtml(row.source || 'Not reported')}</dd></div>
      </dl>
    </details></article>`;
}

function renderCompare(payload = {}, { progress = false } = {}) {
  const container = $(progress ? '#compare-progress' : '#compare-results');
  if (!container) return;
  const states = Array.isArray(payload.states) ? payload.states : [];
  if (!states.length) { container.innerHTML = progress ? '' : state.compareEmptyHtml || ''; return; }
  const summary = comparisonSummary(states);
  const { ready, equal, sameSource } = summary;
  const requested = payload.requested || {};
  const actual = equal ? ready[0].result.period : null;
  const pending = states.some(row => ['pending', 'loading'].includes(row.state));
  const heading = pending ? 'Calculation in progress' : !ready.length ? 'No results calculated' : summary.complete ? 'Comparison results' : 'Partial results';
  const periodLabel = pending ? 'Periods checked as results arrive' : equal ? 'Equal actual periods' : ready.length >= 2 ? summary.equalReadyPeriods ? 'Matching periods among completed results' : 'Unequal actual periods' : 'At least two results needed to compare';
  const note = equal
    ? `All ${states.length} securities resolved to ${actual.start_date} → ${actual.end_date}.`
    : 'Use the actual dates on each card. Trading calendars may differ.';
  const sourceNote = !ready.length ? '' : sameSource
    ? 'Same data snapshot and methodology.'
    : 'A common snapshot and methodology could not be verified. Review data details.';
  const id = progress ? 'compare-progress-heading' : 'compare-window-heading';
  container.innerHTML = `<section class="compare-window-summary" aria-labelledby="${id}">
    <div class="compare-window-head"><h3 id="${id}">${heading}</h3><span class="status-chip ${equal && !pending ? 'ok' : ''}">${escapeHtml(periodLabel)}</span></div>
    <dl class="compare-window-dates">
      <div><dt>Requested dates</dt><dd>${escapeHtml(requested.start || '—')} → ${escapeHtml(requested.end || '—')}</dd></div>
      <div><dt>Actual dates</dt><dd>${actual ? `${escapeHtml(actual.start_date)} → ${escapeHtml(actual.end_date)}` : 'See each completed card'}</dd></div>
      <div><dt>Capital per security</dt><dd>${formatMoney(payload.amount, 'SGD')}</dd></div>
      <div><dt>Scenario</dt><dd>${escapeHtml(payload.scenarioLabel || 'Custom assumptions')}</dd></div>
    </dl>
    <details class="comparison-setup"><summary>Setup details</summary><p>${escapeHtml(note)}</p><p>${escapeHtml(payload.assumptions || '')}</p></details>
    ${sourceNote && !sameSource ? `<p class="compare-consistency ${sameSource ? 'is-ok' : 'is-warn'}">${escapeHtml(sourceNote)}</p>` : ''}
    <p class="compare-partial" role="status">${ready.length} of ${states.length} securities calculated${pending ? ' so far' : ''}.</p>
  </section><div class="compare-cards">${states.map(row => compareCard(row, { requested, amount: payload.amount })).join('')}</div>`;
}

function renderComparePicker(query = '') {
  const input = $('#compare-tickers');
  const list = $('#compare-ticker-options');
  if (!input || !list) return;
  if (state.compareTickers.length >= COMPARE_MAX) {
    list.innerHTML = '<div class="combobox-empty" role="status">Six securities selected. Remove one before adding another.</div>';
    list.classList.remove('hidden'); input.setAttribute('aria-expanded', 'true');
    input.removeAttribute('aria-activedescendant');
    return;
  }
  const wanted = String(query || '').trim().toLowerCase();
  const matches = securityEntries().filter(({ security }) => {
    if (state.compareTickers.includes(security.security_id)) return false;
    const text = [security.ticker, security.name, security.isin, security.exchange, security.market].filter(Boolean).join(' ').toLowerCase();
    return !wanted || text.includes(wanted);
  });
  const visible = matches.slice(0, COMBOBOX_RESULT_LIMIT);
  list.innerHTML = visible.map(({ security }, index) => `<div class="combobox-option" id="compare-ticker-option-${index}" role="option" data-security-id="${escapeHtml(security.security_id)}"><strong>${escapeHtml(security.ticker)}</strong><span>${escapeHtml(security.name)} · ${escapeHtml(security.exchange)} · ${escapeHtml(security.currency)}<br>${escapeHtml(discoveryCoverage(security.security_id))}</span></div>`).join('')
    || '<div class="combobox-empty" role="status">No additional securities match that search.</div>';
  if (matches.length > COMBOBOX_RESULT_LIMIT) list.insertAdjacentHTML('beforeend', `<div class="combobox-more" role="status">Showing ${COMBOBOX_RESULT_LIMIT} of ${matches.length}. Keep typing to narrow the list.</div>`);
  input.removeAttribute('aria-activedescendant');
  list.classList.remove('hidden');
  input.setAttribute('aria-expanded', 'true');
}

function renderCompareChips() {
  const chips = $('#compare-ticker-chips');
  if (!chips) return;
  chips.innerHTML = state.compareTickers.map((securityId) => {
    const entry = entryForId(securityId);
    if (!entry) return '';
    return `<button type="button" class="selected-chip" data-remove-security-id="${escapeHtml(securityId)}" aria-label="Remove ${escapeHtml(entry.security.ticker)}">${escapeHtml(entry.security.ticker)}<span aria-hidden="true">×</span></button>`;
  }).join('') + Array.from({ length: Math.max(0, COMPARE_MIN - state.compareTickers.length) }, (_, index) =>
    `<button type="button" class="selected-chip empty-slot" data-add-comparison>Choose security ${state.compareTickers.length + index + 1}</button>`).join('');
}

function selectCompareSecurity(securityId) {
  if (!entryForId(securityId) || state.compareTickers.includes(securityId) || state.compareTickers.length >= 6) return;
  state.compareTickers.push(securityId);
  renderCompareChips();
  saveComparisonDraft();
  renderCompareCoverage();
  editView('compare');
  const input = $('#compare-tickers');
  if (input) { input.value = ''; input.focus(); }
  renderComparePicker('');
}

function initComparePicker() {
  const input = $('#compare-tickers');
  const picker = $('#compare-ticker-picker');
  const list = $('#compare-ticker-options');
  const chips = $('#compare-ticker-chips');
  if (!input || !picker || !list) return;
  state.compareTickers = String(input.dataset.initialTickers || '').split(',').map((ticker) => entryForTicker(ticker)?.security.security_id).filter(Boolean).slice(0, 6);
  renderCompareChips();
  input.addEventListener('focus', () => renderComparePicker(input.value));
  input.addEventListener('input', () => renderComparePicker(input.value));
  input.addEventListener('keydown', (event) => {
    const options = [...list.querySelectorAll('.combobox-option')];
    const active = options.findIndex((option) => option.classList.contains('active'));
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!options.length) return;
      const next = event.key === 'ArrowDown' ? (active + 1) % options.length : (active - 1 + options.length) % options.length;
      options.forEach((option, index) => option.classList.toggle('active', index === next));
      options[next].scrollIntoView({ block: 'nearest' });
      input.setAttribute('aria-activedescendant', options[next].id);
    } else if (event.key === 'Enter' && active >= 0) {
      event.preventDefault();
      selectCompareSecurity(options[active].dataset.securityId);
    } else if (event.key === 'Backspace' && !input.value && state.compareTickers.length) {
      state.compareTickers.pop(); editView('compare'); saveComparisonDraft(); renderCompareChips(); renderCompareCoverage(); renderComparePicker('');
    } else if (event.key === 'Escape') {
      list.classList.add('hidden'); input.setAttribute('aria-expanded', 'false');
    }
  });
  input.addEventListener('blur', () => setTimeout(() => {
    if (!picker.contains(document.activeElement)) { list.classList.add('hidden'); input.setAttribute('aria-expanded', 'false'); }
  }, 0));
  list.addEventListener('mousedown', (event) => {
    const option = event.target.closest('.combobox-option');
    if (!option) return;
    event.preventDefault(); selectCompareSecurity(option.dataset.securityId);
  });
  $('#compare-coverage')?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-use-common-window]');
    if (!button) return;
    const plan = compareWindowPlan();
    if (!plan.common.ok) return;
    const proposed = plan.resolved.ok ? plan.resolved : plan.common;
    $('#compare-start').value = proposed.start;
    $('#compare-end').value = proposed.end;
    editView('compare'); saveComparisonDraft(); renderCompareCoverage();
  });
  chips?.addEventListener('click', (event) => {
    if (event.target.closest('[data-add-comparison]')) { input.focus(); return; }
    const button = event.target.closest('[data-remove-security-id]');
    if (!button) return;
    editView('compare'); state.compareTickers = state.compareTickers.filter((securityId) => securityId !== button.dataset.removeSecurityId);
    renderCompareChips(); saveComparisonDraft(); renderCompareCoverage(); renderComparePicker(input.value);
  });
}

async function submitCompare(event) {
  event.preventDefault();
  const error = $('#compare-error');
  error.textContent = '';
  beginView('compare');
  const button = event.currentTarget.querySelector('button[type="submit"]');
  const ids = [...state.compareTickers];
  if (ids.length < COMPARE_MIN || ids.length > COMPARE_MAX || new Set(ids).size !== ids.length || ids.some(id => !entryForId(id))) {
    error.textContent = 'Select between 2 and 6 different securities from the catalog.';
    failView('compare', 'invalid'); return;
  }
  const amountText = $('#compare-amount').value;
  const amount = Number(amountText);
  if (!Number.isFinite(amount) || amount <= 0) {
    error.textContent = 'Enter finite capital greater than S$0.';
    failView('compare', 'invalid'); return;
  }
  const start = $('#compare-start').value;
  const end = $('#compare-end').value;
  if (!isIsoDate(start) || !isIsoDate(end) || start > end) {
    error.textContent = 'Choose valid dates with the end on or after the start.';
    failView('compare', 'invalid'); return;
  }
  // Snapshot before the first await: later form edits cannot alter this run.
  const scenario = { ...(($('#compare-scenario').value === 'custom' ? state.compareCopiedScenario : PRESETS[$('#compare-scenario').value]) || PRESETS.investor) };
  const scenarioLabel = COMPARE_SCENARIO_LABELS[$('#compare-scenario').value] || COMPARE_SCENARIO_LABELS.investor;
  const rows = ids.map(securityId => ({ securityId, ticker: compareTickerFor(securityId), state: 'pending', reason: '', result: null }));
  const requested = { security_ids: ids, tickers: rows.map(row => row.ticker).join(','), initial_sgd: amountText, start_date: start, end_date: end, ...scenario };
  const assumptions = `Dividends ${scenario.dividends ? 'on' : 'off'} · withholding ${scenario.withholding ? 'on' : 'off'} · reinvestment ${scenario.reinvest ? 'on' : 'off'}`;
  const visible = () => ({ states: rows, requested: { start, end }, amount: amountText, scenarioLabel, assumptions });
  const runSeq = s6Runs.compare += 1;
  setBusy(button, true);
  renderCompare(visible(), { progress: true });
  let usedLocal = false;
  try {
    for (const row of rows) {
      row.window = await loadComparisonCoverage(row.securityId);
      if (!s6RunCurrent('compare', runSeq)) return;
      row.state = 'loading';
      s6SetButtonProgress(button, `Computing ${row.ticker}…`);
      renderCompare(visible(), { progress: true });
      let adapterError = null;
      if (API_BASE) {
        try {
          const params = { security_id: row.securityId, initial_sgd: amountText, start_date: start, end_date: end, ...scenario };
          const envelope = await apiGet('/analyze', params);
          if (!s6RunCurrent('compare', runSeq)) return;
          const normalized = comparisonRow(row, envelope);
          if (normalized.state !== 'ready') throw new Error(normalized.reason);
          Object.assign(row, normalized, { source: 'Python adapter' });
        } catch (failure) {
          adapterError = failure;
        }
      }
      if (!s6RunCurrent('compare', runSeq)) return;
      if (row.state !== 'ready') {
        if (row.window.state === 'unavailable') {
          row.state = 'unavailable';
          row.reason = `${adapterError ? `Adapter unavailable: ${adapterError.message}. ` : ''}${row.window.reason}`;
        } else {
          try {
            const outcome = await s6AnalysisViaPacks({ securityId: row.securityId, label: row.ticker,
              initial_sgd: amountText, start_date: start, end_date: end, ...scenario }, () => {},
              { isCurrent: () => s6RunCurrent('compare', runSeq) });
            if (!s6RunCurrent('compare', runSeq)) return;
            Object.assign(row, comparisonRow(row, outcome.envelope), { source: adapterError ? 'Local browser engine · adapter unavailable' : 'Local browser engine' });
            usedLocal = true;
          } catch (failure) {
            if (!s6RunCurrent('compare', runSeq)) return;
            row.state = 'failed';
            row.reason = 'Could not calculate this investment. Try again or remove it.';
            row.errorDetail = `${adapterError ? `Adapter unavailable: ${adapterError.message}. ` : ''}${failure.message || 'No usable local result was returned.'}`;
          }
        }
      }
      renderCompare(visible(), { progress: true });
    }
    if (!s6RunCurrent('compare', runSeq)) return;
    if (!rows.some(row => row.state === 'ready')) {
      error.textContent = 'No security could be calculated for this request. Inspect each reason below; any previous completed result is retained.';
      failView('compare'); return;
    }
    // Only a terminal request with at least one valid result replaces the
    // previous artifact. Each partial result retains the full selection/status.
    const artifact = JSON.parse(JSON.stringify(visible()));
    completeView('compare', requested, artifact);
    renderCompare(artifact);
    $('#compare-progress').innerHTML = '';
    setComputeMode(API_BASE ? usedLocal ? 'adapterFallback' : 'adapter' : 'local');
  } catch (failure) {
    if (s6RunCurrent('compare', runSeq)) { error.textContent = failure.message; failView('compare'); }
  } finally {
    if (s6RunCurrent('compare', runSeq)) setBusy(button, false);
  }
}

function renderDca(payload, context = {}) {
  state.dcaArtifact = payload;
  if (Object.keys(context).length) state.dcaContext = context;
  context = state.dcaContext;
  const request = resultViews.dca.request || payload.request || null;
  const result = payload.result || payload; const security = result.security;
  if (security.currency === 'SGD') state.dcaCurrencyMode = 'sgd';
  const native = state.dcaCurrencyMode === 'native'; const currency = native ? security.currency : 'SGD';
  const contributed = native ? result.total_contributed_foreign_currency : result.total_contributed_sgd;
  const finalValue = native ? result.final_value_foreign_currency : result.final_value_sgd;
  const gainLoss = native ? result.gain_loss_foreign_currency : result.gain_loss_sgd;
  const xirr = native ? result.xirr_foreign_currency : result.xirr;
  const warnings = result.data_quality.warnings || [];
  const support = context.support;
  const packWarnings = context.packWarnings || [];
  const supportNotice = support && support.status !== 'fully_supported'
    ? `<p class="consistency-warning" role="alert">Data pack coverage for ${escapeHtml(security.ticker)} is ${escapeHtml(support.status)}${support.reason ? `: ${escapeHtml(support.reason)}` : ''}. Results use the data actually present in the packs.${packWarnings.length ? ` Pack notes: ${escapeHtml(packWarnings.join(' '))}` : ''}</p>`
    : '';
  $('#dca-results').innerHTML = `<div class="analysis-output"><div class="dca-output-head"><div class="output-kicker">${escapeHtml(security.ticker)} · ${escapeHtml(titleCase(request?.frequency || 'monthly'))}</div><div class="mini-switch" role="group" aria-label="DCA display currency"><button type="button" data-dca-currency="native" aria-pressed="${native}" class="${native ? 'active' : ''} ${security.currency === 'SGD' ? 'hidden' : ''}">${escapeHtml(security.currency)}</button><button type="button" data-dca-currency="sgd" aria-pressed="${!native}" class="${native ? '' : 'active'}">SGD</button></div></div><h3>${formatMoney(finalValue, currency)}</h3><p>Ending value after ${escapeHtml(String(result.contribution_dates.length))} recurring contributions. Initial lump sum: ${formatMoney(request?.initial_sgd || 0, 'SGD')}, invested ${escapeHtml(result.methodology.initial_purchase_date || result.contribution_dates[0])}.</p><div class="output-grid"><span>Total invested<strong>${formatMoney(contributed, currency)}</strong></span><span>Gain / loss<strong>${formatMoney(gainLoss, currency)}</strong></span><span>XIRR · annualised, money-weighted<strong>${formatPercent(xirr)}</strong></span><span>Shares<strong>${Number(result.shares).toFixed(5)}</strong></span></div><details class="inline-help"><summary>About XIRR</summary><p>Annualised return accounting for when and how much you invested.</p></details><details class="contribution-dates"><summary>Contribution dates (${result.contribution_dates.length})</summary><p>${result.contribution_dates.map((date) => `<time datetime="${escapeHtml(date)}">${escapeHtml(formatDate(date))}</time>`).join(' · ')}</p></details>${warnings.length ? `<p class="detail-note" role="alert">${escapeHtml(warnings.join(' '))}</p>` : ''}${supportNotice}</div>`;
  const chart = document.createElement('div'); chart.className = 'dca-price-chart'; chart.innerHTML = priceChartHtml(context.series, native); $('#dca-results .analysis-output').append(chart);
  renderCoverage('dca', result, context.coverage);
  const exportButton = document.createElement('button'); exportButton.type='button'; exportButton.dataset.downloadDca=''; exportButton.className='text-button'; exportButton.textContent='Download this result JSON'; exportButton.addEventListener('click',()=>downloadCompleted('dca')); $('#dca-results .analysis-output').append(exportButton);
  $$('[data-dca-currency]').forEach((button) => button.addEventListener('click', () => { state.dcaCurrencyMode = button.dataset.dcaCurrency; if (state.dcaArtifact) renderDca(state.dcaArtifact); }));
  renderViewState('dca');
}

// Explicit DCA submission uses the existing worker supersede/cancel contract.
async function submitDca(event) {
  event.preventDefault();
  s7CancelAutoRun('dca');
  await s7RunDca({ mode: 'force' });
}

async function s7RunDca({ mode = 'force' } = {}) {
  const form = $('#analysis-form');
  if (!form) return;
  beginView('dca');
  const error = $('#form-error'); error.textContent = '';
  if ($('#end-date').value < $('#start-date').value) { error.textContent = 'End date must be on or after start date.'; failView('dca', 'invalid'); return; }
  const contribution = Number($('#dca-contribution').value); if (!(contribution > 0)) { error.textContent = 'Enter a contribution greater than S$0.'; failView('dca', 'invalid'); return; }
  const initial = $('#dca-initial').value;
  if (initial === '' || !Number.isFinite(Number(initial)) || Number(initial) < 0) { error.textContent = 'Enter a non-negative initial lump sum.'; failView('dca','invalid'); return; }
  const scenario = scenarioValues();
  const request = { initial_sgd: initial, security_id: securityComboboxValue('#security-select'), contribution_sgd: $('#dca-contribution').value, frequency: $('#dca-frequency').value, start_date: $('#start-date').value, end_date: $('#end-date').value, ...scenario };
  if (!request.security_id) { error.textContent = 'Choose a security from the published catalog.'; $('#security-select')?.setAttribute('aria-invalid', 'true'); failView('dca', 'invalid'); return; }
  const button = form.querySelector('button[type="submit"]');
  const previousEngineId = s4State.requestId;
  s4State.request = request; s4State.button = button; s4State.requestId = null;
  setBusy(button, true);
  const runSeq = s4State.runSeq = (s4State.runSeq || 0) + 1;
  s7Reactive.runs.dca += 1;
  form.dataset.s7Inflight = '1';
  try {
    if (API_BASE) {
      const key = requestKey('dca', { ...request, methodology_version: '1.0', data_snapshot_id: 'local-canonical-parquet' });
      try {
        const adapterEnvelope = await apiGet('/dca', { ...request, request_key: key });
        if (runSeq !== s4State.runSeq) return; // superseded while in flight
        state.dcaContext = {};
        completeView('dca', request, adapterEnvelope);
        renderDca(adapterEnvelope);
        if (mode === 'force') focusRenderedHeading('#dca-results');
        setComputeMode('adapter');
        return;
      } catch (adapterError) {
        if (runSeq !== s4State.runSeq) return;
        error.textContent = `${adapterError.message} — falling back to the local engine.`;
      }
    }
    s4SetDcaProgress('Resolving published data packs…');
    const outcome = await s4DcaViaPacks(request, { previousEngineId, isCurrent: () => runSeq === s4State.runSeq });
    const envelope = outcome?.envelope;
    if (runSeq === s4State.runSeq && envelope) { error.textContent = ''; completeView('dca', request, envelope); renderDca(envelope, outcome.context); if (mode === 'force') focusRenderedHeading('#dca-results'); setComputeMode(API_BASE ? 'adapterFallback' : 'local'); }
  } catch (staticError) {
    if (runSeq === s4State.runSeq) { error.textContent = staticError.message; failView('dca'); }
  } finally {
    if (runSeq === s4State.runSeq) { $('#s4-dca-progress')?.remove(); setBusy(button, false); s4State.button = null; delete form.dataset.s7Inflight; }
  }
}

function ledgerRowTemplate(values = {}) {
  const id = values.rowId || crypto.randomUUID();
  const selectedId = values.securityId || '';
  const selected = entryForId(selectedId)?.security;
  const currencies = [...new Set(['SGD', 'USD', values.currency, ...securityEntries().map(({ security }) => security.currency)].filter(Boolean))].sort();
  const type = values.type || 'BUY';
  const field = (key, label, html) => `<td data-field="${key}"><label for="ledger-${id}-${key}">${label}</label>${html}</td>`;
  const input = (key, inputType, value, extra = '') => `<input id="ledger-${id}-${key}" class="ledger-${key}" type="${inputType}" value="${escapeHtml(value ?? '')}" ${extra} aria-describedby="ledger-${id}-error" />`;
  return `<tr data-row-id="${escapeHtml(id)}" data-transaction-id="${escapeHtml(values.transactionId || '')}">
    ${field('type', 'Transaction type', `<select id="ledger-${id}-type" class="ledger-type">${Object.keys(TRANSACTION_FIELDS).map(t => `<option ${t === type ? 'selected' : ''}>${t}</option>`).join('')}</select>`)}
    ${field('date', 'Transaction date', input('date', 'date', values.date))}
    ${field('security', 'Security', `<div class="form-combobox ledger-combobox" data-combobox>${input('security', 'text', selected ? securityDisplayLabel(selected) : selectedId, `data-security-id="${escapeHtml(selectedId)}" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="ledger-${id}-security-options" autocomplete="off"`)}<div id="ledger-${id}-security-options" class="combobox-list hidden" role="listbox" aria-label="Ledger securities"></div></div>`)}
    ${field('quantity', 'Quantity', input('quantity', 'number', values.quantity, 'min="0" step="any"'))}
    ${field('cash', 'Transaction total', input('cash', 'number', values.cash, 'min="0" step="any"'))}
    ${field('currency', 'Currency', `<select id="ledger-${id}-currency" class="ledger-currency">${currencies.map(c => `<option ${c === (values.currency || 'SGD') ? 'selected' : ''}>${escapeHtml(c)}</option>`).join('')}</select>`)}
    ${field('fees', 'Fees', input('fees', 'number', values.fees ?? '0', 'min="0" step="any"'))}
    <td class="ledger-actions"><button type="button" data-delete-row aria-label="Delete transaction">Delete</button><p id="ledger-${id}-error" class="form-error ledger-row-error" role="alert"></p></td></tr>`;
}

function ledgerFieldVisibility(row) {
  const fields = TRANSACTION_FIELDS[row.querySelector('.ledger-type').value];
  for (const key of ['security', 'quantity', 'fees']) row.querySelector(`[data-field="${key}"]`).hidden = !fields[key];
}

function addLedgerRow(values = {}) {
  if (!has('#ledger-rows')) return;
  $('#ledger-rows').insertAdjacentHTML('beforeend', ledgerRowTemplate(values));
  ledgerFieldVisibility($('#ledger-rows').lastElementChild);
  wireSecurityComboboxes();
  $('#ledger-empty').hidden = true;
}

function renderPortfolio(payload, meta = {}) {
  const result = payload.result || payload;
  const rows = result.holdings.map((holding) => { const ccy = s5CurrencyForId(holding.security_id); return `<tr><th scope="row">${escapeHtml(holding.ticker)}</th><td data-label="Quantity">${Number(holding.quantity).toFixed(5)}</td><td data-label="Average cost">${formatMoney(holding.weighted_average_cost, ccy)}</td><td data-label="Native value">${formatMoney(holding.market_value_native, ccy)}</td><td data-label="SGD value">${formatMoney(holding.market_value_sgd, 'SGD')}</td><td data-label="Realised P/L">${formatMoney(holding.realized_pl_native, ccy)}</td><td data-label="Unrealised P/L">${formatMoney(holding.unrealized_pl_native, ccy)}</td></tr>`; }).join('');
  const warnings = meta.warnings || [];
  const warningNote = warnings.length ? `<p class="detail-note" role="alert">Data warnings: ${escapeHtml(warnings.join(' '))}</p>` : '';
  const sourceNote = '';
  $('#portfolio-results').innerHTML = `<div class="analysis-output"><div class="output-kicker">AS OF ${escapeHtml(formatDate(result.as_of))}</div><h3>${formatMoney(result.total_market_value_sgd, 'SGD')}</h3><p>Mark-to-market portfolio value across ${result.holdings.length} holding${result.holdings.length === 1 ? '' : 's'}.</p><div class="holding-table-wrap"><table class="holding-table"><caption class="sr-only">Portfolio holdings as of ${escapeHtml(formatDate(result.as_of))}</caption><thead><tr><th scope="col">Ticker</th><th scope="col">Quantity</th><th scope="col">Average cost</th><th scope="col">Native value</th><th scope="col">SGD value</th><th scope="col">Realised P/L</th><th scope="col">Unrealised P/L</th></tr></thead><tbody>${rows || '<tr><td colspan="7">No open holdings on this date.</td></tr>'}</tbody></table></div><p class="detail-note">Cash: ${Object.entries(result.cash_by_currency || {}).map(([currency, amount]) => `${formatMoney(amount, currency)}`).join(' · ') || 'none'} · Realised P/L: ${Object.entries(result.realized_pl_native || {}).map(([currency, amount]) => `${formatMoney(amount, currency)}`).join(' · ') || 'none'}.</p>${warningNote}${sourceNote}<p class="detail-note">Weighted-average cost is a reporting convention, not a Singapore capital-gains tax calculation.</p></div>`;
}

function s5CollectLedgerRows() {
  return $$('#ledger-rows tr').map((row) => {
    const type = row.querySelector('.ledger-type').value;
    const fields = TRANSACTION_FIELDS[type];
    return {
      row_id: row.dataset.rowId,
      ...(row.dataset.transactionId ? { transaction_id: row.dataset.transactionId } : {}),
      transaction_type: type,
      security_id: fields.security ? securityComboboxValue(row.querySelector('.ledger-security')) || null : null,
      transaction_date: row.querySelector('.ledger-date').value,
      quantity: row.querySelector('.ledger-quantity').value || (fields.quantity ? '' : '0'),
      cash_amount: row.querySelector('.ledger-cash').value,
      currency: row.querySelector('.ledger-currency').value,
      fees: row.querySelector('.ledger-fees').value || '0',
    };
  });
}

function s5ValidateLedger(rows, asOf) {
  $$('#ledger-rows [aria-invalid]').forEach(el => el.removeAttribute('aria-invalid'));
  $$('.ledger-row-error').forEach(el => { el.textContent = ''; });
  if (!rows.length) return 'Add at least one ledger transaction.';
  if (!asOf) return 'Choose an as-of date for the reconstruction.';
  const error = ledgerError(rows);
  if (error) {
    const row = $$('#ledger-rows tr')[error.index];
    row.querySelector('.ledger-row-error').textContent = error.message;
    row.querySelector(`.ledger-${error.field}`)?.setAttribute('aria-invalid', 'true');
    return error.message;
  }
  return null;
}

// Ledger edits are saved locally; reconstruction is explicitly submitted.
async function submitPortfolio(event) {
  event.preventDefault();
  s7CancelAutoRun('portfolio');
  await s7RunPortfolio({ mode: 'force' });
}

async function s7RunPortfolio({ mode = 'force' } = {}) {
  const form = $('#portfolio-form');
  if (!form) return;
  beginView('portfolio');
  const error = $('#portfolio-error'); error.textContent = '';
  const asOf = $('#portfolio-as-of').value;
  const transactions = s5CollectLedgerRows();
  const validationError = s5ValidateLedger(transactions, asOf);
  if (validationError) { error.textContent = validationError; failView('portfolio', 'invalid'); return; }
  const button = form.querySelector('button[type="submit"]'); setBusy(button, true);
  const runSeq = s6Runs.portfolio += 1;
  s7Reactive.runs.portfolio += 1;
  form.dataset.s7Inflight = '1';
  try {
    if (API_BASE) {
      try {
        const payload = await fetch(`${API_BASE}/api/portfolio`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ as_of: asOf, transactions }) }).then(async (response) => { const body = await response.json(); if (!response.ok || body.error) throw new Error(body.error || 'Portfolio request failed'); return body; });
        if (!s6RunCurrent('portfolio', runSeq)) return;
        completeView('portfolio', { as_of: asOf, transactions }, payload);
        renderPortfolio(payload);
        if (mode === 'force') focusRenderedHeading('#portfolio-results');
        setComputeMode('adapter');
        return;
      } catch (adapterError) {
        if (!s6RunCurrent('portfolio', runSeq)) return;
        error.textContent = `${adapterError.message} — falling back to the local engine.`;
      }
    }
    // S6.2: static deployments (empty API base) go straight to the local
    // engine — the old relative POST probe to 'api/portfolio' is gone.
    const local = await s5LocalPortfolio(asOf, transactions, () => s6RunCurrent('portfolio', runSeq));
    if (!s6RunCurrent('portfolio', runSeq)) return;
    if (local.unavailable) { error.textContent = local.unavailable; failView('portfolio'); if (!resultViews.portfolio.request) s5ShowPortfolioUnavailable(local.unavailable); }
    else { completeView('portfolio', { as_of: asOf, transactions }, local.envelope); renderPortfolio(local.envelope, local.meta); if (mode === 'force') focusRenderedHeading('#portfolio-results'); setComputeMode(API_BASE ? 'adapterFallback' : 'local'); }
  } catch (localError) {
    if (s6RunCurrent('portfolio', runSeq)) { error.textContent = localError.message; failView('portfolio'); }
  }
  finally { if (s6RunCurrent('portfolio', runSeq)) { setBusy(button, false); delete form.dataset.s7Inflight; } }
}

function wireEvents() {
  if (has('#mobile-nav-toggle')) $('#mobile-nav-toggle').addEventListener('click', () => { const menu = $('#mobile-nav'); const open = !menu.classList.contains('open'); menu.classList.toggle('hidden', !open); menu.classList.toggle('open', open); $('#mobile-nav-toggle').setAttribute('aria-expanded', String(open)); });
  $$('#mobile-nav a').forEach((link) => link.addEventListener('click', () => { $('#mobile-nav')?.classList.add('hidden'); $('#mobile-nav')?.classList.remove('open'); $('#mobile-nav-toggle')?.setAttribute('aria-expanded', 'false'); }));
  ['#catalog-search', '#asset-filter', '#universe-filter', '#market-filter', '#currency-filter', '#distribution-filter', '#active-filter'].forEach((selector) => { if (has(selector)) $(selector).addEventListener('input', () => { state.catalogLimit = 12; renderCatalog(); }); });
  if (has('#catalog-more')) $('#catalog-more').addEventListener('click', () => { state.catalogLimit = state.catalogLimit + 100; renderCatalog(); });
  if (has('#security-select')) $('#security-select').addEventListener('change', (event) => selectSecurity(securityComboboxValue(event.target)));
  if (has('#scenario-select')) $('#scenario-select').addEventListener('change', (event) => syncPreset(event.target.value));
  ['#dividends-toggle', '#tax-toggle', '#reinvest-toggle'].forEach((selector) => { if (has(selector)) $(selector).addEventListener('change', () => { if (has('#scenario-select')) $('#scenario-select').value = 'custom'; }); });
  if (has('#analysis-form')) $('#analysis-form').addEventListener('submit', submitAnalysis);
  if (has('#compare-form')) { const form = $('#compare-form'); form.addEventListener('submit', submitCompare); form.querySelector('button[type="submit"]').addEventListener('click', (event) => { event.preventDefault(); submitCompare({ preventDefault() {}, currentTarget: form }); }); }
  if (has('#dca-form')) { const form = $('#dca-form'); form.addEventListener('submit', submitDca); form.querySelector('button[type="submit"]').addEventListener('click', (event) => { event.preventDefault(); submitDca({ preventDefault() {}, currentTarget: form }); }); }
  if (has('#portfolio-form')) { const form = $('#portfolio-form'); form.addEventListener('submit', submitPortfolio); form.querySelector('button[type="submit"]').addEventListener('click', (event) => { event.preventDefault(); submitPortfolio({ preventDefault() {}, currentTarget: form }); }); }
  if (has('#add-ledger-row')) $('#add-ledger-row').addEventListener('click', () => { addLedgerRow(); $('#ledger-rows').lastElementChild.querySelector('.ledger-type').focus(); setLedgerSaveStatus('Unsaved transaction. Complete the labeled fields to save.'); editView('portfolio'); });
  if (has('#ledger-rows')) $('#ledger-rows').addEventListener('change', (event) => { if (!event.target.classList.contains('ledger-security')) return; const security = entryForId(securityComboboxValue(event.target))?.security; if (security) event.target.closest('tr').querySelector('.ledger-currency').value = security.currency; });
  if (has('#ledger-rows')) s5WireLedgerPersistence();
  $$('.currency-button').forEach((button) => button.addEventListener('click', () => { state.currencyMode = button.dataset.currency; if (state.artifact) renderResult(); }));
  if (has('#warnings-toggle')) $('#warnings-toggle').addEventListener('click', () => { state.warningsOpen = !state.warningsOpen; renderQuality(state.artifact?.result?.data_quality || {}); });
  ['#dca-form', '#portfolio-form', '#compare-form'].forEach(sel => { if (has(sel)) $(sel).noValidate = true; });
  wireRequestEdits();
  if (has('#return-to-demo')) $('#return-to-demo').addEventListener('click', async () => { const entry = entryForTicker('QQQ'); if (!entry) return; setSimulatorMode('one-time'); selectSecurity(entry.security.security_id); $('#initial-amount').value = '10000'; $('#start-date').value = '2024-01-02'; $('#end-date').value = '2025-01-02'; $('#scenario-select').value = 'investor'; syncPreset('investor'); $('#analysis-form').requestSubmit(); });
  if (has('#download-result')) $('#download-result').addEventListener('click', () => { if (!state.artifact) return; const blob = new Blob([JSON.stringify(state.artifact, null, 2)], { type: 'application/json' }); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `sg-invest-${state.artifact.result?.security?.ticker || 'analysis'}.json`; link.click(); URL.revokeObjectURL(link.href); });
  if (has('#copy-link')) $('#copy-link').addEventListener('click', copyAnalysisLink);
  if (has('#toggle-series-table')) $('#toggle-series-table').addEventListener('click', () => { const table = $('#series-table-wrap'); const button = $('#toggle-series-table'); const open = table.classList.toggle('hidden') === false; button.setAttribute('aria-expanded', String(open)); button.textContent = open ? 'Hide table' : 'View as table'; });
  if (has('#download-series-csv')) $('#download-series-csv').addEventListener('click', downloadSeriesCsv);
  initComparePicker();
}

function applyAnalysisUrl() {
  const params = new URLSearchParams(window.location.search);
  if (!params.get('security_id') || !entryForId(params.get('security_id')) || !has('#analysis-form')) return;
  setSimulatorMode('one-time');
  selectSecurity(params.get('security_id'));
  if (params.get('initial_sgd')) $('#initial-amount').value = params.get('initial_sgd');
  if (params.get('start_date')) $('#start-date').value = params.get('start_date');
  if (params.get('end_date')) $('#end-date').value = params.get('end_date');
  if (params.has('dividends')) $('#dividends-toggle').checked = params.get('dividends') === 'true';
  if (params.has('withholding')) $('#tax-toggle').checked = params.get('withholding') === 'true';
  if (params.has('reinvest')) $('#reinvest-toggle').checked = params.get('reinvest') === 'true';
  $('#scenario-select').value = 'custom';
  editView('analysis');
}

async function init() {
  // Start empty; a published replay never stands beside unrelated draft inputs.
  const staticCatalog = await loadJson(CATALOG_ARTIFACT, { securities: fallbackCatalog });
  if (API_BASE) {
    const apiCatalog = await apiGet('/catalog').catch(() => null);
    state.catalog = apiCatalog?.securities || staticCatalog.securities || fallbackCatalog;
  } else {
    state.catalog = staticCatalog.securities || fallbackCatalog;
  }
  state.artifact = null;
  state.artifactSource = 'demo';
  renderSecurityOptions(); renderUniverseOptions(); renderDimensionOptions(); renderCatalog(); syncPreset('investor');
  const defaults = s8DefaultDateRange();
  [['#start-date', defaults.start], ['#end-date', defaults.end],
   ['#dca-start', defaults.start], ['#dca-end', defaults.end],
   ['#compare-start', defaults.start], ['#compare-end', defaults.end]].forEach(([sel, value]) => {
    if (has(sel)) $(sel).value = value;
  });
  // Wire events BEFORE any further awaits: users can click the moment the
  // forms render, and a submit during the data-status/build-info fetches used
  // to be silently lost (listeners did not exist yet).
  await s5RestoreLedger();
  wireEvents();

  initializeDiscovery();
  initializeSimulator();
  state.compareEmptyHtml = $('#compare-results')?.innerHTML || '';
  initializeResultStates();
  renderCompareCoverage();
  setComputeMode(API_BASE ? 'adapter' : 'local');
  if (has('#data-date')) {
    const status = API_BASE ? await apiGet('/status').catch(() => loadJson('data/data-status.json', null)) : await loadJson('data/data-status.json', null);
    $('#data-date').textContent = status?.backfill?.as_of ? formatDate(status.backfill.as_of) : 'Not published';
  }
  initWorkspace((name, legacy) => { if (name === 'methods') renderSecurityMethods(); if (legacy === 'explore') $('.discovery').open = true; if (legacy === 'dca') setSimulatorMode('regular'); });
  applyAnalysisUrl();
}

// --- S5: local portfolio reconstruction + ledger persistence ----------------

// S6: s5CompatibleTracker() is gone — protocol.createRequestTracker exposes
// native nextId(scope, payload), so the S5 engine client uses its own
// default tracker like every other consumer.

// S7.1: the S5 loader must resolve packs relative to the document base like
// the S4 loader above — with an empty baseUrl its manifest/pack URLs were
// root-absolute (/data/packs/…) and broke under the GitHub Pages project
// subpath (docs/sprint-6-notes.md, "Notes for S7").
const s5PackLoader = createPackLoader({ baseUrl: new URL('.', document.baseURI).href });
const s5EngineClient = createEngineClient();
const s5InputsCache = new Map();
// S7.5 C3: last minted portfolio engine request id — a newer portfolio run
// (manual or debounced) cancels its predecessor at the worker.
let s5LastPortfolioRequestId = null;

function s5CurrencyForId(securityId) {
  return entryForId(securityId)?.security.currency || s5InputsCache.get(securityId)?.inputs.security.currency || 'USD';
}

function s5SecurityLabel(securityId, entry) {
  return entry?.ticker || entryForId(securityId)?.security.ticker || securityId;
}

async function s5SecurityInputs(securityId, entry, startDate, endDate, origin = s5PackLoader) {
  const cached = s5InputsCache.get(securityId);
  if (cached && cached.startDate <= startDate && endDate <= cached.endDate) return cached.inputs;
  const inputs = await origin.loadSecurityInputs(entry, startDate, endDate);
  s5InputsCache.set(securityId, { startDate, endDate, inputs });
  return inputs;
}

function s5ShowPortfolioUnavailable(message) {
  if (has('#portfolio-results')) {
    $('#portfolio-results').innerHTML = `<div class="result-empty compact-empty"><p class="eyebrow">LEDGER VIEW</p><h3>Unavailable for this ledger.</h3><p>${escapeHtml(message)}</p></div>`;
  }
}

async function s5LocalPortfolio(asOf, rows, isCurrent = () => true) {
  const holdingIds = [...new Set(rows.map((row) => row.security_id).filter(Boolean))];
  const firstDateFor = (securityId) => rows.filter((row) => row.security_id === securityId).map((row) => row.transaction_date).sort()[0];
  const warnings = [];
  for (const securityId of holdingIds) {
    const { entry, packs: origin } = await s8ResolveSecurity({ securityId });
    if (!entry) {
      return { unavailable: `${s5SecurityLabel(securityId)} (${securityId}) is not in the published data packs, so the portfolio cannot be reconstructed as of ${asOf}.` };
    }
    const support = origin.supportFor(entry, firstDateFor(securityId), asOf);
    if (support.status === 'unavailable') {
      return { unavailable: `${s5SecurityLabel(securityId)} cannot be reconstructed as of ${asOf}: ${support.reason}.` };
    }
    if (support.status === 'incomplete') warnings.push(`${s5SecurityLabel(securityId)}: incomplete pack support (${support.reason}).`);
  }

  const securities = {};
  const prices = [];
  const fxRates = [];
  for (const securityId of holdingIds) {
    const { entry, packs: origin } = await s8ResolveSecurity({ securityId });
    const inputs = await s5SecurityInputs(securityId, entry, firstDateFor(securityId), asOf, origin);
    securities[securityId] = inputs.security;
    prices.push(...inputs.prices);
    fxRates.push(...inputs.fxRates);
    for (const warning of inputs.warnings) warnings.push(`${inputs.security.ticker}: ${warning}`);
  }

  const currencies = [...new Set(rows.map((row) => row.currency).filter(Boolean))];
  for (const currency of currencies) {
    if (currency === 'SGD' || fxRates.some((rate) => rate.base_currency === currency)) continue;
    const manifest = await s5PackLoader.loadManifest();
    const provider = (manifest.securities || []).find((candidate) => candidate.native_currency === currency);
    if (!provider) continue;
    const fxInputs = await s5SecurityInputs(provider.security_id, provider, asOf, asOf);
    fxRates.push(...fxInputs.fxRates);
  }

  const transactions = rows.map((row, index) => ({ ...row, transaction_id: `s5-${String(index + 1).padStart(6, '0')}` }));
  if (!isCurrent()) throw new Error('Request superseded by edited inputs.');
  const request = s5EngineClient.portfolio({ as_of: asOf, transactions, securities, prices, fx_rates: fxRates });
  s5EngineClient.supersede('portfolio', request.id);
  const previousRequestId = s5LastPortfolioRequestId;
  s5LastPortfolioRequestId = request.id;
  if (previousRequestId && previousRequestId !== request.id) s5EngineClient.cancel(previousRequestId);
  const envelope = await request.promise;
  return { envelope, meta: { warnings, source: 'local' } };
}

let ledgerSaveQueue = Promise.resolve();
let ledgerSaveVersion = 0;
let ledgerUndoRows = null;
let ledgerImportRows = null;
let ledgerRestoreFailed = false;

function setLedgerSaveStatus(message) { $('#ledger-save-status').textContent = message; }

function s5RenderLedgerRows(rows) {
  $('#ledger-rows').innerHTML = '';
  rows.forEach(row => addLedgerRow({ rowId: row.row_id, transactionId: row.transaction_id, type: row.transaction_type, securityId: row.security_id || '', date: row.transaction_date, quantity: row.quantity, cash: row.cash_amount, fees: row.fees, currency: row.currency }));
  $('#ledger-empty').hidden = rows.length > 0;
}

async function portfolioCoveredDate() {
  if ($('#portfolio-as-of').value) return;
  try {
    const ids = [...new Set(s5CollectLedgerRows().map(row => row.security_id).filter(Boolean))];
    const dates = [];
    for (const securityId of ids) {
      const { entry } = await s8ResolveSecurity({ securityId });
      if (entry?.last_date) dates.push(entry.last_date);
    }
    if (!dates.length) {
      const manifest = await s5PackLoader.loadManifest();
      dates.push(...(manifest.securities || []).map(entry => entry.last_date).filter(Boolean));
    }
    if (dates.length) {
      $('#portfolio-as-of').value = dates.sort()[ids.length ? 0 : dates.length - 1];
      $('#portfolio-coverage').textContent = `Suggested valuation ${$('#portfolio-as-of').value} uses published price coverage. FX and ledger coverage are checked when you calculate.`;
    }
  } catch { $('#portfolio-coverage').textContent = 'Choose a valuation date. Published coverage could not be loaded.'; }
}

async function s5RestoreLedger() {
  try {
    const rows = await ledgerStore.load();
    s5RenderLedgerRows(rows);
    setLedgerSaveStatus(rows.length ? 'Saved ledger restored from this browser.' : 'No saved transactions in this browser.');
  } catch (error) {
    ledgerRestoreFailed = true;
    setLedgerSaveStatus(`Could not read your saved ledger: ${error.message}. Reload before editing; stored data has not been replaced.`);
    $('#add-ledger-row').disabled = true;
  }
  portfolioCoveredDate();
}

function s5AutoSaveLedger() {
  if (ledgerRestoreFailed) return;
  const rows = s5CollectLedgerRows();
  const version = ++ledgerSaveVersion;
  if (ledgerError(rows)) { setLedgerSaveStatus('Unsaved edits. Complete or correct the transaction fields. Your last saved ledger is retained.'); return; }
  setLedgerSaveStatus('Saving in this browser…');
  ledgerSaveQueue = ledgerSaveQueue.catch(() => {}).then(() => ledgerStore.save(rows));
  ledgerSaveQueue.then(() => { if (version === ledgerSaveVersion) setLedgerSaveStatus('Saved in this browser.'); }, error => { if (version === ledgerSaveVersion) setLedgerSaveStatus(`Save failed: ${error.message}. Keep this page open and export your ledger.`); });
}

function ledgerRememberUndo() {
  ledgerUndoRows = s5CollectLedgerRows();
  $('#undo-ledger').hidden = false;
}

function s5WireLedgerPersistence() {
  $('#ledger-rows').addEventListener('change', event => {
    const row = event.target.closest('tr');
    if (!row) return;
    ledgerFieldVisibility(row);
    if (event.target.classList.contains('ledger-type')) {
      const fields = TRANSACTION_FIELDS[event.target.value];
      if (!fields.security) { row.querySelector('.ledger-security').value = ''; row.querySelector('.ledger-security').dataset.securityId = ''; }
      if (!fields.quantity) row.querySelector('.ledger-quantity').value = '0';
      if (!fields.fees) row.querySelector('.ledger-fees').value = '0';
    }
    s5AutoSaveLedger();
  });
  $('#ledger-rows').addEventListener('click', event => {
    if (!event.target.closest('[data-delete-row]')) return;
    ledgerRememberUndo();
    event.target.closest('tr').remove();
    $('#ledger-empty').hidden = $('#ledger-rows').children.length > 0;
    s5AutoSaveLedger(); editView('portfolio');
  });
  $('#undo-ledger').addEventListener('click', () => {
    if (!ledgerUndoRows) return;
    s5RenderLedgerRows(ledgerUndoRows); ledgerUndoRows = null;
    $('#undo-ledger').hidden = true; s5AutoSaveLedger(); editView('portfolio');
  });
  $('#clear-ledger').addEventListener('click', () => {
    if (ledgerRestoreFailed) return;
    ledgerRememberUndo(); s5RenderLedgerRows([]); s5AutoSaveLedger(); editView('portfolio');
  });
  $('#export-ledger').addEventListener('click', () => {
    const rows = s5CollectLedgerRows();
    if (ledgerError(rows)) { $('#portfolio-error').textContent = 'Correct unsaved fields before export. Your stored ledger is unchanged.'; return; }
    const blob = new Blob([JSON.stringify({ schema: 'sg-invest-ledger', version: 1, rows }, null, 2)], { type: 'application/json' });
    const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = 'sg-invest-ledger.json'; link.click(); URL.revokeObjectURL(link.href);
  });
  $('#import-ledger').addEventListener('click', () => { if (!ledgerRestoreFailed) $('#ledger-file').click(); });
  $('#ledger-file').addEventListener('change', async event => {
    const file = event.target.files?.[0]; if (!file) return;
    try {
      ledgerImportRows = parseLedgerPayload(await file.text());
      const error = ledgerError(ledgerImportRows); if (error) throw new Error(error.message);
      $('#ledger-import-summary').textContent = `${ledgerImportRows.length} transactions will replace ${s5CollectLedgerRows().length} current transactions. Review types, dates and amounts below. Undo remains available until this page is closed.`;
      $('#ledger-import-preview').textContent = JSON.stringify(ledgerImportRows, null, 2);
      $('#ledger-import-dialog').showModal();
    } catch (error) { $('#portfolio-error').textContent = `Ledger import failed: ${error.message}`; }
    event.target.value = '';
  });
  $('#ledger-import-cancel').addEventListener('click', () => { ledgerImportRows = null; $('#ledger-import-dialog').close(); });
  $('#ledger-import-confirm').addEventListener('click', () => {
    if (!ledgerImportRows) return;
    ledgerRememberUndo(); s5RenderLedgerRows(ledgerImportRows); ledgerImportRows = null;
    $('#ledger-import-dialog').close(); s5AutoSaveLedger(); editView('portfolio');
  });
}

init().catch((error) => { console.error(error); if (has('#form-error')) $('#form-error').textContent = 'The frontend could not initialise. Refresh to retry.'; });

// --- S4 helpers (static-mode DCA: packs → worker engine → envelope) ---

function s4SetDcaProgress(label) {
  const button = s4State.button;
  if (button) { button.dataset.originalLabel ||= button.innerHTML; button.innerHTML = escapeHtml(label); }
  if (!has('#dca-results')) return;
  let line = $('#s4-dca-progress');
  if (!line) { $('#dca-results').insertAdjacentHTML('beforeend', '<p class="detail-note" id="s4-dca-progress" role="status"></p>'); line = $('#s4-dca-progress'); }
  line.textContent = label;
}

function s4EngineErrorMessage(error) {
  if (!error || typeof error !== 'object') return String(error ?? 'The local DCA computation failed.');
  const problems = error.details?.problems;
  const detail = problems?.length ? ` (${problems.join('; ')})` : '';
  return `${error.message || 'The local DCA computation failed.'}${detail}`;
}

// Static-mode DCA: resolve the security's data packs, gate on manifest
// support, then compute through the engine worker. Resolves null for a
// superseded/stale response (S4.6: a late response renders nothing); throws
// Error with a user-facing message for every genuine failure. S7.5 C3: the
// reactive panel passes the run it replaces as previousEngineId, which is
// marked superseded in the tracker (already the case via supersedeScope) and
// politely cancelled at the worker so the stale computation stops early.
async function s4DcaViaPacks(request, { previousEngineId = null, isCurrent = () => true } = {}) {
  const { entry, packs: origin } = await s8ResolveSecurity({ securityId: request.security_id });
  if (!entry) throw new Error(`${request.security_id} has no published data pack, so the local engine cannot serve this request.`);
  const support = origin.supportFor(entry, request.start_date, request.end_date);
  if (support.status === 'unavailable') {
    throw new Error(`${entry.ticker} cannot be replayed locally for ${request.start_date} → ${request.end_date}: ${support.reason || 'no data pack coverage for this range'}. Choose a range inside the covered years.`);
  }
  if (!isCurrent()) return null;
  s4SetDcaProgress(`Loading ${entry.ticker} data packs for ${String(request.start_date).slice(0, 4)}–${String(request.end_date).slice(0, 4)}…`);
  const inputs = await origin.loadSecurityInputs(entry, request.start_date, request.end_date);
  if (!isCurrent()) return null;
  s4SetDcaProgress('Computing DCA replay in the browser…');
  const payload = {
    security: inputs.security,
    prices: inputs.prices,
    fx_rates: inputs.fxRates,
    dividends: inputs.dividends,
    corporate_actions: inputs.corporateActions,
    tax_rules: inputs.taxRules,
    start_date: request.start_date,
    end_date: request.end_date,
    contribution_sgd: String(request.contribution_sgd),
    initial_sgd: String(request.initial_sgd || '0'),
    frequency: request.frequency,
    scenario: { dividends_enabled: request.dividends !== false, withholding_tax_enabled: request.withholding !== false, reinvest_dividends: request.reinvest !== false },
  };
  const { id, promise } = engineClient.dca(payload, {
    onProgress: (envelope) => {
      if (!isCurrent()) return;
      if (envelope.stage === 'received') s4SetDcaProgress('DCA request received — queued in the engine worker…');
      else if (envelope.stage === 'computing') s4SetDcaProgress('Computing contributions, dividends and XIRR…');
    },
  });
  s4State.requestId = id;
  engineClient.supersede('dca', id);
  if (previousEngineId && previousEngineId !== id) engineClient.cancel(previousEngineId);
  try {
    const envelope = await promise;
    if (id !== s4State.requestId) return null;
    const manifest = await origin.loadManifest();
    return { envelope, context: { support, packWarnings: inputs.warnings || [], coverage: coverageFromInputs(entry, inputs, manifest), series: s6SeriesFromInputs(inputs, request) } };
  } catch (engineError) {
    if (id !== s4State.requestId) return null;
    throw new Error(s4EngineErrorMessage(engineError));
  }
}

// --- S6 helpers (static-mode analysis + comparison: packs → engine worker) ---

// Request isolation for analysis/compare is the S6 run-sequence guard
// (s6Runs): a response can only be rendered by the submit closure that
// started it, and only while its run sequence is still current — a late,
// superseded or foreign response can never replace another request's result.

function s6EngineErrorMessage(error) {
  if (!error || typeof error !== 'object') return String(error ?? 'The local computation failed.');
  const problems = error.details?.problems;
  const detail = problems?.length ? ` (${problems.join('; ')})` : '';
  return `${error.message || 'The local computation failed.'}${detail}`;
}

// Resolve a comparison ticker against the pack manifest with the dev-server
// adapter's semantics: exactly one security per ticker, or an explicit error.
async function s6ResolveTicker(ticker, startDate, endDate) {
  const { entry } = await s8ResolveSecurity({ ticker });
  if (entry) return entry;
  throw new Error(`${ticker} is not in the published data packs, so the requested range ${startDate} → ${endDate} cannot be computed locally.`);
}

// Static-mode analysis (scope 'analyze'): resolve the security's data packs,
// gate on manifest support, compute through the engine worker, and derive the
// daily series from the same loaded packs. Throws Error with a user-facing
// message (naming the security and requested range) for every genuine failure.
// S7.5 C2: the reactive analysis panel passes { supersede: true,
// previousEngineId } — the freshly minted request is marked the scope's keep
// id (older in-flight analyze requests become superseded in the tracker) and
// the panel's own previous request is cancelled at the worker. Compare runs
// pass no options and behave exactly as before (their sequential ticker
// requests never overlap, and a foreign supersede marker never gates browser
// delivery — the panel run-sequence guard remains the render gate).
async function s6AnalysisViaPacks({ securityId = null, ticker = null, label = null, initial_sgd, start_date, end_date, dividends, withholding, reinvest }, onProgress = () => {}, { supersede = false, previousEngineId = null, isCurrent = () => true } = {}) {
  const { entry, packs: origin } = await s8ResolveSecurity({ securityId, ticker });
  if (!entry) throw new Error(`${label || securityId || ticker} is not in the published data packs, so ${start_date} → ${end_date} cannot be computed locally.`);
  const support = origin.supportFor(entry, start_date, end_date);
  if (support.status === 'unavailable') {
    throw new Error(`${entry.ticker} cannot be computed locally for ${start_date} → ${end_date}: ${support.reason || 'no data pack coverage for this range'}. Choose a range inside the covered years.`);
  }
  onProgress(`Loading ${entry.ticker} data packs for ${String(start_date).slice(0, 4)}–${String(end_date).slice(0, 4)}…`);
  const inputs = await origin.loadSecurityInputs(entry, start_date, end_date);
  onProgress('Computing the replay in the browser…');
  const payload = {
    security: inputs.security,
    prices: inputs.prices,
    fx_rates: inputs.fxRates,
    start_date,
    end_date,
    initial_sgd: String(initial_sgd),
    scenario: { dividends_enabled: dividends !== false, withholding_tax_enabled: withholding !== false, reinvest_dividends: reinvest !== false },
    dividends: inputs.dividends,
    corporate_actions: inputs.corporateActions,
    tax_rules: inputs.taxRules,
  };
  if (!isCurrent()) throw new Error('Request superseded by edited inputs.');
  const { id, promise } = engineClient.analyze(payload);
  if (supersede) {
    s7LastAnalyzeId = id;
    engineClient.supersede('analyze', id);
    if (previousEngineId && previousEngineId !== id) engineClient.cancel(previousEngineId);
  }
  let engineResult;
  try {
    engineResult = await promise;
  } catch (engineError) {
    throw new Error(s6EngineErrorMessage(engineError));
  }
  const packNotes = s6PackNotes(entry, support, inputs);
  const result = packNotes.length
    ? { ...engineResult, data_quality: { status: 'WARNING', warnings: [...packNotes, ...(engineResult.data_quality?.warnings || [])] } }
    : engineResult;
  // The Python artifact pipeline attaches the security's dividend-coverage
  // record at the delivery layer (see scripts/build_frontend_data.py); mirror
  // it here so local results explain zero-dividend outcomes the same way
  // (dividendCoverageNote keys off result.dividend_coverage.coverage_status).
  if (inputs.security?.dividend_coverage) result.dividend_coverage = inputs.security.dividend_coverage;
  const manifest = await origin.loadManifest();
  const envelope = {
    data_snapshot_id: inputs.dataSnapshotId,
    catalog_version: manifest.catalog_version || 'local-packs',
    methodology_version: engineResult.methodology?.methodology_version || '1.0',
    request: {
      start_date,
      end_date,
      initial_sgd: String(initial_sgd),
      dividends: String(dividends !== false),
      withholding: String(withholding !== false),
      reinvest: String(reinvest !== false),
    },
    result,
  };
  return { id, envelope, series: s6SeriesFromInputs(inputs, { start_date, end_date }), support, packWarnings: inputs.warnings || [], coverage: coverageFromInputs(entry, inputs, manifest) };
}

function s6PackNotes(entry, support, inputs) {
  // S6.4 support gate (same pattern as S4/S5): 'unavailable' never computes
  // (thrown above); 'incomplete' computes and surfaces the coverage reason
  // plus pack-level warnings alongside the engine's own warnings.
  const notes = [];
  if (support.status !== 'fully_supported') {
    notes.push(`Data pack coverage for ${entry.ticker} is ${support.status}${support.reason ? `: ${support.reason}` : ''}. Results use the data actually present in the packs.`);
  }
  for (const warning of inputs.warnings || []) notes.push(`${entry.ticker} pack note: ${warning}`);
  return notes;
}

// Mirror of scripts/frontend_server.py /series semantics, computed from the
// packs already loaded for the analysis: window-filtered daily closes sorted
// by date, native close plus same-day SGD close (previous-trading-day FX
// rule), all Decimal arithmetic (presentation-only — it never feeds results).
function s6SeriesFromInputs(inputs, { start_date, end_date }) {
  try {
    const security = inputs.security;
    const rows = (inputs.prices || [])
      .filter((price) => price.trading_date >= start_date && price.trading_date <= end_date)
      .sort((a, b) => (a.trading_date < b.trading_date ? -1 : a.trading_date > b.trading_date ? 1 : 0));
    if (!rows.length) return null;
    const points = rows.map((price) => {
      const rate = rateForDate(security.currency, price.trading_date, inputs.fxRates);
      return {
        date: price.trading_date,
        native_close: String(price.close),
        sgd_close: dec(price.close).times(rate).toString(),
        fx_rate: rate.toString(),
      };
    });
    return { security, points };
  } catch {
    return null; // a chart that cannot be built never blocks the result
  }
}

// --- S7.5 Track C helpers (staged auto-loading: series, debounce, triggers) --

// Cancel a pending debounced auto-run. Called by every manual submit (the
// button is the explicit "run now" intent) and by every new input event via
// the schedule helpers, so at most one timer per panel exists at any time.
function s7CancelAutoRun(kind) {
  if (!s7Reactive.timers[kind]) return;
  clearTimeout(s7Reactive.timers[kind]);
  s7Reactive.timers[kind] = null;
}

function s7OnSecurityCardPicked() { editView('analysis'); }

// Calendar defaults are drafts; calculation remains explicit.
function s8DefaultDateRange() {
  const now = new Date();
  const iso = (d) => d.toISOString().slice(0, 10);
  const end = iso(now);
  const start = now >= new Date(now.getFullYear(), 5, 30)
    ? `${now.getFullYear()}-01-01`
    : iso(new Date(now.getFullYear() - 1, now.getMonth(), now.getDate()));
  return { start, end };
}

function initializeResultStates() {
  Object.keys(resultViews).forEach(renderViewState);
}

function wireRequestEdits() {
  ['analysis','compare','portfolio'].forEach(kind => {
    const form = viewForm(kind); if (!form) return;
    ['input','change'].forEach(type => form.addEventListener(type,event => {
      if (!event.target.matches('input,select,textarea')) return;
      if (kind === 'compare' && event.target.id === 'compare-tickers') return;
      if (kind !== 'analysis') { editView(kind); if(kind==='compare'){renderCompareCoverage();saveComparisonDraft();} return; }
      const id = event.target.id;
      if (id !== 'initial-amount') editView('dca');
      if (!['dca-initial','dca-contribution','dca-frequency'].includes(id)) editView('analysis');
      updateAssumptions(); saveSimulatorDraft();
    }));
  });
}

function universeLabel(value) {
  return ({ sgx_active: 'Singapore listings', sp500_current: 'S&P 500', nasdaq100_current: 'Nasdaq 100', russell2000_current: 'Russell 2000', major_global_etfs: 'Global ETFs', ui_fixture: 'Test catalog' })[value] || titleCase(value);
}

function discoveryCoverage(id) {
  const entry = state.discoveryManifest?.securities?.find(item => item.security_id === id);
  if (!entry) return 'Coverage not published in the available manifest';
  const years = Object.values(entry.years || {});
  const first = entry.first_date || years.map(y => y.first_date).filter(Boolean).sort()[0];
  const last = entry.last_date || years.map(y => y.last_date).filter(Boolean).sort().at(-1);
  return `${titleCase(entry.status || 'unknown')} · ${first || entry.first_year || 'unknown'} → ${last || entry.last_year || 'unknown'}`;
}

function clearSelectionMetadata(input) {
  if (input.id === 'security-select') {
    $('#security-hint').textContent = 'Search text is not a selected security. Choose a result.';
    ['#security-domicile','#security-isin','#security-expense'].forEach(sel => { $(sel).textContent = '—'; });
  }
  if (input.id === 'methods-security') $('#security-methods').textContent = 'Choose a search result to see security-specific data.';
}

async function renderSecurityMethods() {
  if (!has('#security-methods')) return;
  const id = securityComboboxValue('#methods-security');
  const entry = entryForId(id);
  if (!entry) { $('#security-methods').textContent = 'Choose an investment to view its data.'; return; }
  const security = entry.security;
  const manifest = state.discoveryManifest;
  const text = `${security.ticker} · ${security.name} · ${security.exchange} · ${security.currency}`;
  $('#security-methods').innerHTML = `<h3>${escapeHtml(text)}</h3><p>${escapeHtml(discoveryCoverage(id))}</p><dl class="methods-facts"><dt>Distribution policy</dt><dd>${escapeHtml(titleCase(security.distribution_policy || 'unknown'))}</dd><dt>Published source</dt><dd>${escapeHtml(manifest?.source || 'Not published')}</dd><dt>Snapshot</dt><dd>${escapeHtml(manifest?.data_snapshot_id || 'Not published')}</dd><dt>Generated</dt><dd>${escapeHtml(manifest?.generated_at || 'Not published')}</dd><dt>Assumptions</dt><dd>Daily unadjusted closes; purchase resolves forward, valuation backward. FX is SGD per unit of foreign currency. Investor-level withholding and reinvestment follow your selected assumptions.</dd></dl><p>Coverage may contain gaps. Review result warnings. Fund fees (TER) are not deducted again.</p>`;
}

function initializeDiscovery() {
  $$('.form-combobox input').forEach(input => {
    if (input.closest('[data-combobox]').querySelector('[data-clear-security]')) return;
    const clear = document.createElement('button'); clear.type = 'button'; clear.className = 'text-button clear-selection'; clear.dataset.clearSecurity = input.id; clear.textContent = 'Clear selection';
    clear.addEventListener('click', () => { input.value = ''; delete input.dataset.securityId; clearSelectionMetadata(input); input.dispatchEvent(new Event('input',{bubbles:true})); input.focus(); });
    input.closest('[data-combobox]').append(clear);
  });
  $('#methods-security')?.addEventListener('change', renderSecurityMethods);
  $('#reset-search')?.addEventListener('click', () => {
    $('#catalog-search').value = ''; ['asset','universe','market','currency','distribution','active'].forEach(name => { $(`#${name}-filter`).value = name === 'active' ? 'active' : 'all'; }); state.catalogLimit = 12; renderCatalog(); $('#catalog-search').focus();
  });
  (async () => {
    for (const loader of [packs,packsRemote].filter(Boolean)) {
      try { state.discoveryManifest = await loader.loadManifest(); break; } catch { /* Explicit unknown coverage if neither origin responds. */ }
    }
    renderCatalog(); renderSecurityMethods(); renderCompareCoverage();
  })();
}


function setSimulatorMode(mode) {
  if (mode !== state.simulatorMode && resultViews[activeSimulatorKind()].phase === 'loading') editView(activeSimulatorKind());
  state.simulatorMode=mode==='regular'?'regular':'one-time';
  const regular=state.simulatorMode==='regular';
  $('#form-error').textContent = resultViews[activeSimulatorKind()].error || '';
  $('#regular-inputs').hidden=!regular; $('#one-time-inputs').hidden=regular;
  $('#dca-results').hidden=!regular;
  $('#result-content').classList.toggle('hidden',regular||!state.artifact);
  $('#result-empty').classList.toggle('hidden',regular||Boolean(state.artifact));
  $('#artifact-unavailable').classList.add('hidden');
  $$('[data-investing-mode]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.investingMode===state.simulatorMode)));
  renderViewState('analysis');renderViewState('dca'); saveSimulatorDraft();
}
function updateAssumptions() {
  const values=scenarioValues();
  $('#assumptions-summary').textContent=`Dividends ${values.dividends?'on':'off'} · Withholding ${values.withholding?'on':'off'} · Reinvestment ${values.reinvest?'on':'off'} · Edit assumptions`;
  const security=entryForId(securityComboboxValue('#security-select'))?.security;
  $('#distribution-explanation').textContent=security?.distribution_policy==='accumulating'?'Accumulating fund: no cash dividends.':security?.distribution_policy==='distributing'?'':'Distribution policy unknown. Review data notes.';
}
const SIMULATOR_DRAFT='sg-invest-simulator-draft-v1';
function saveSimulatorDraft() {
  try { const fields={}; ['security-select','initial-amount','start-date','end-date','dca-initial','dca-contribution','dca-frequency'].forEach(id=>{fields[id]=$(`#${id}`).value;});fields.securityId=securityComboboxValue('#security-select');fields.mode=state.simulatorMode;fields.scenario=scenarioValues();sessionStorage.setItem(SIMULATOR_DRAFT,JSON.stringify(fields)); } catch { /* Draft persistence is optional; ledger storage is unchanged. */ }
}
function initializeSimulator() {
  try { const draft=JSON.parse(sessionStorage.getItem(SIMULATOR_DRAFT)||'null');if(draft){Object.entries(draft).forEach(([id,value])=>{const el=document.getElementById(id);if(el&&typeof value==='string')el.value=value;});if(entryForId(draft.securityId))selectSecurity(draft.securityId);if(draft.scenario){$('#dividends-toggle').checked=draft.scenario.dividends;$('#tax-toggle').checked=draft.scenario.withholding;$('#reinvest-toggle').checked=draft.scenario.reinvest;}state.simulatorMode=draft.mode==='regular'?'regular':'one-time';} } catch { /* Ignore an invalid local draft. */ }
  $$('[data-investing-mode]').forEach(button=>button.addEventListener('click',()=>setSimulatorMode(button.dataset.investingMode)));
  $('#use-covered-dates').addEventListener('click',()=>{const id=securityComboboxValue('#security-select');const entry=state.discoveryManifest?.securities?.find(s=>s.security_id===id);const dates=Object.values(entry?.years||{});let first=entry?.first_date||dates.map(y=>y.first_date).filter(Boolean).sort()[0];let last=entry?.last_date||dates.map(y=>y.last_date).filter(Boolean).sort().at(-1);const currency=entryForId(id)?.security.currency;const fx=state.discoveryManifest?.fx?.coverage?.[currency];if(currency!=='SGD'){if(!fx?.first_date||!fx?.last_date){$('#preset-coverage-note').textContent='Usable FX coverage is not published. Enter dates and review result warnings.';return;}first=[first,fx.first_date].filter(Boolean).sort().at(-1);last=[last,fx.last_date].filter(Boolean).sort()[0];}if(!first||!last||first>last||entry.status==='unavailable'){$('#preset-coverage-note').textContent='Published usable history is unavailable. Enter dates and review result coverage.';return;}$('#start-date').value=first;$('#end-date').value=last;$('#preset-coverage-note').textContent=`History applied: ${first} → ${last}.`;editView('analysis');editView('dca');saveSimulatorDraft();});
  $('#simulator-to-compare').addEventListener('click',copySimulatorToComparison);
  try {const draft=JSON.parse(sessionStorage.getItem('sg-invest-compare-draft-v1')||'null');if(draft){state.compareTickers=[...new Set((Array.isArray(draft.ids)?draft.ids:[]).filter(id=>entryForId(id)))].slice(0,COMPARE_MAX);state.compareCopiedScenario=draft.copiedScenario&&['dividends','withholding','reinvest'].every(key=>typeof draft.copiedScenario[key]==='boolean')?{...draft.copiedScenario}:null;['amount','start','end','scenario'].forEach(name=>{$(`#compare-${name}`).value=draft[name];});renderCompareChips();}}catch{}
  updateAssumptions();setSimulatorMode(state.simulatorMode);
}
function copySimulatorToComparison(options = {}) {
  const note = $('#comparison-handoff-note');
  if (!note) return;
  const regular = state.simulatorMode === 'regular';
  if (regular && options.asOneTime !== true) {
    // S12: never convert silently. Regular contributions cannot be compared,
    // so the handoff explains that and offers the one-time equivalent.
    note.hidden = false;
    note.innerHTML = 'Compare supports one-time investments. <button type="button" class="text-button" data-compare-one-time>Compare as a one-time investment</button> using only your initial lump sum; recurring contributions are excluded.';
    note.querySelector('[data-compare-one-time]')?.addEventListener('click', () => copySimulatorToComparison({ asOneTime: true }), { once: true });
    return;
  }
  const id = securityComboboxValue('#security-select');
  if (!entryForId(id)) { note.hidden = false; note.textContent = 'Choose a security before copying the setup.'; return; }
  const amountInput = regular ? $('#dca-initial') : $('#initial-amount');
  if (!(Number(amountInput?.value) > 0)) { note.hidden = false; note.textContent = 'Enter an initial amount greater than S$0 before copying the setup.'; return; }
  const startValue = $('#start-date').value;
  const endValue = $('#end-date').value;
  state.compareTickers = [id];
  renderCompareChips();
  $('#compare-amount').value = amountInput.value;
  $('#compare-start').value = startValue;
  $('#compare-end').value = endValue;
  state.compareCopiedScenario = { ...scenarioValues() };
  $('#compare-scenario').value = 'custom';
  editView('compare');
  saveComparisonDraft();
  renderCompareCoverage();
  note.hidden = false;
  note.textContent = regular
    ? 'Copied initial lump sum and assumptions. Add another investment.'
    : 'Setup copied. Add another investment.';
  location.hash = 'compare';
  $('#compare-amount')?.focus();
}

function downloadCompleted(kind) {
  const view=resultViews[kind];if(!view.artifact)return;
  const content={request:view.request,result:view.artifact.result||view.artifact,data_snapshot_id:state.dcaContext.coverage?.snapshotId||view.artifact.data_snapshot_id,methodology_version:(view.artifact.result||view.artifact).methodology?.methodology_version||'1.0'};
  const blob=new Blob([JSON.stringify(content,null,2)],{type:'application/json'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=`sg-invest-${kind}-result.json`;link.click();URL.revokeObjectURL(link.href);
}

function saveComparisonDraft() {
  try { const draft={ids:[...state.compareTickers]};['amount','start','end','scenario'].forEach(name=>{draft[name]=$(`#compare-${name}`).value;});draft.copiedScenario=state.compareCopiedScenario;sessionStorage.setItem('sg-invest-compare-draft-v1',JSON.stringify(draft)); } catch {}
}
