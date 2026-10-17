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
import { ledgerStore } from './ledger-store.js';

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
  const entry = securityId ? await packs.findSecurity({ securityId }) : await packs.findSecurity({ ticker });
  if (entry) return { entry, packs };
  if (packsRemote) {
    const remote = securityId ? await packsRemote.findSecurity({ securityId }) : await packsRemote.findSecurity({ ticker });
    if (remote) return { entry: remote, packs: packsRemote };
  }
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
  warningsOpen: false,
  catalogLimit: 12,
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
  list.innerHTML = visible.map(({ security }, index) => `<div class="combobox-option" id="${escapeHtml(input.id)}-option-${index}" role="option" aria-selected="${securityComboboxValue(input) === security.security_id}" data-security-id="${escapeHtml(security.security_id)}"><strong>${escapeHtml(security.ticker)}</strong><span>${escapeHtml(security.name)} · ${escapeHtml(security.exchange)}</span></div>`).join('')
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
  input.closest('[data-combobox]')?.querySelector('.combobox-list')?.addEventListener('mousedown', (event) => {
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
  const amount = Number(value) * 100;
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
  select.innerHTML = '<option value="all">All universes</option>' + universes.map((universe) => `<option value="${escapeHtml(universe)}">${escapeHtml(titleCase(universe))}</option>`).join('');
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
      && (universe === 'all' || entryUniverse === universe)
      && (market === 'all' || security.market === market)
      && (currency === 'all' || security.currency === currency)
      && (distribution === 'all' || security.distribution_policy === distribution)
      && (active === 'all' || (active === 'active' ? security.active !== false : security.active === false));
  });
}

function renderCatalog() {
  const entries = filteredEntries();
  if (has('#catalog-count')) $('#catalog-count').textContent = `${entries.length} ${entries.length === 1 ? 'security' : 'securities'} · published catalog`;
  const visible = entries.slice(0, state.catalogLimit);
  if (has('#catalog-grid')) {
    $('#catalog-grid').innerHTML = visible.map(({ security, universe }) => `<button class="security-card" type="button" data-security-id="${escapeHtml(security.security_id)}">
      <span class="security-card-top"><span>${escapeHtml(security.exchange)} · ${escapeHtml(security.market)}</span><span class="security-tag">${escapeHtml(security.asset_type)}</span></span>
      <span><strong class="security-ticker">${escapeHtml(security.ticker)}</strong><span class="security-name">${escapeHtml(security.name)}</span></span>
      <span class="security-card-bottom"><span>${escapeHtml(security.currency)} · ${escapeHtml(security.distribution_policy || 'unknown')}</span><span>${escapeHtml(titleCase(universe))} ↗</span></span>
    </button>`).join('') || '<div class="catalog-empty">No published securities match this lens.</div>';
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
  if (has('#security-hint')) $('#security-hint').textContent = `${security.exchange} · ${security.currency} · ${titleCase(security.distribution_policy || 'unknown')} distribution · ${security.active === false ? 'inactive' : 'active'}`;
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
  const amount = kind === 'dca' ? `${request.contribution_sgd} SGD ${request.frequency}` : `${request.initial_sgd} SGD initial`;
  return `${name} · ${request.start_date} → ${request.end_date} · ${amount} · dividends ${request.dividends}, withholding ${request.withholding}, reinvest ${request.reinvest}`;
}

function renderViewState(kind) {
  const view = resultViews[kind];
  const form = $(`#${kind === 'analysis' ? 'analysis' : kind}-form`);
  if (!form) return;
  let notice = $(`#${kind}-request-state`);
  if (!notice) {
    notice = document.createElement('p'); notice.id = `${kind}-request-state`;
    notice.className = 'request-state'; notice.setAttribute('role', 'status');
    const output = $({ analysis: '#result-content', dca: '#dca-results', compare: '#compare-results', portfolio: '#portfolio-results' }[kind]);
    output.before(notice);
  }
  form.dataset.resultState = view.phase;
  notice.dataset.state = view.phase;
  const current = view.phase === 'current';
  const labels = { empty: 'Choose your inputs, then Calculate.', pending: 'Inputs edited. Calculate to see a result.', loading: 'Calculating the submitted request…', invalid: 'Check the input error, then Calculate.', failed: 'This request could not be calculated. Check the error and try again.', current: 'Current result' };
  notice.textContent = view.request
    ? `${current ? 'Current result' : 'Previous result — not current for the edited inputs'}. ${viewSummary(kind, view.request)}${current ? '' : ` · ${labels[view.phase] || 'Select Update results to recalculate.'}`}`
    : labels[view.phase] || labels.pending;
  const button = form.querySelector('button[type="submit"]');
  if (button && view.phase !== 'loading') {
    setBusy(button, false); delete form.dataset.s7Inflight;
    button.textContent = view.request ? 'Update results' : 'Calculate';
    button.dataset.originalLabel = button.innerHTML;
  }
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
  if (kind === 'dca') s4State.runSeq = (s4State.runSeq || 0) + 1;
  else s6Runs[kind] += 1;
  resultViews[kind].phase = 'pending';
  renderViewState(kind);
}

function beginView(kind) {
  editView(kind);
  resultViews[kind].phase = 'loading'; renderViewState(kind);
}

function completeView(kind, request, artifact) {
  const view = resultViews[kind];
  view.request = Object.freeze(JSON.parse(JSON.stringify(request)));
  view.artifact = artifact; view.phase = 'current';
  renderViewState(kind);
}

function failView(kind, phase = 'failed') {
  resultViews[kind].phase = phase; renderViewState(kind);
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
  const actual = result.period;
  const resolved = actual ? `${actual.start_date} → ${actual.end_date}` : 'Not separately published by this result';
  const truncated = actual && (actual.start_date !== request.start_date || actual.end_date !== request.end_date);
  const warnings = result.data_quality?.warnings || [];
  const groups = { 'Dates and FX': [], 'Dividends and tax': [], 'Data and other notes': [] };
  warnings.forEach(w => groups[/date|stale|fx|coverage/i.test(w) ? 'Dates and FX' : /dividend|tax|withholding/i.test(w) ? 'Dividends and tax' : 'Data and other notes'].push(w));
  const detail = Object.entries(groups).filter(([,items])=>items.length).map(([label,items]) => `<details><summary>${escapeHtml(label)} (${items.length})</summary>${items.map(item=>`<p>${escapeHtml(item)}</p>`).join('')}</details>`).join('');
  const html = `<strong>${truncated ? 'Dates resolved within available trading history' : 'Dates, coverage and data notes'}</strong><p>Requested: ${escapeHtml(request.start_date)} → ${escapeHtml(request.end_date)}<br>Resolved: ${escapeHtml(resolved)}<br>Latest published security date: ${escapeHtml(coverage.latestSecurity || 'Not published')}<br>${result.security.currency !== 'SGD' ? `Latest published ${escapeHtml(result.security.currency)}/SGD FX date: ${escapeHtml(coverage.latestFx || 'Not published')}<br>` : ''}Snapshot date: ${escapeHtml(coverage.snapshot || 'Not published')} · ID: ${escapeHtml(coverage.snapshotId || resultViews[kind].artifact?.data_snapshot_id || 'Not published')}</p><p>${warnings.length} material data note${warnings.length === 1 ? '' : 's'} attached to this result.${truncated ? ' Requested and resolved dates differ; review the actual period before interpreting returns.' : ''}</p>${detail}<button type="button" class="text-button" data-review-dates="${kind}">Review requested dates</button>`;
  let box = $(`#${kind}-coverage`);
  if (!box) { box = document.createElement('div'); box.id = `${kind}-coverage`; box.className = 'coverage-summary'; }
  if (kind === 'analysis') $('#result-period').after(box);
  else $('#dca-results .analysis-output')?.append(box);
  box.innerHTML = html;
  box.querySelector('button').addEventListener('click', () => $(kind === 'analysis' ? '#start-date' : '#dca-start').focus());
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

function renderSeries(series) {
  if (!has('#series-chart')) return;
  if (!series) { $('#series-card').classList.add('hidden'); return; }
  const points = series.points || [];
  if (!points.length) { $('#series-card').classList.add('hidden'); return; }
  $('#series-card').classList.remove('hidden');
  $('#series-range').textContent = `${formatDate(points[0].date)} → ${formatDate(points.at(-1).date)} · ${points.length} closes`;
  const native = points.map((point) => Number(point.native_close));
  const sgd = points.map((point) => Number(point.sgd_close));
  const all = [...native, ...sgd].filter(Number.isFinite);
  const min = Math.min(...all); const max = Math.max(...all); const spread = max - min || 1;
  const plot = (values) => values.map((value, index) => `${(index / Math.max(1, values.length - 1)) * 980 + 10},${245 - ((value - min) / spread) * 220}`).join(' ');
  $('#series-chart').innerHTML = `<polyline class="series-line series-native" points="${plot(native)}"></polyline><polyline class="series-line series-sgd" points="${plot(sgd)}"></polyline><line class="series-axis" x1="10" y1="245" x2="990" y2="245"></line>`;
  if (has('#native-legend')) $('#native-legend').textContent = `${series.security.currency} native close`;
  if (has('.chart-source')) $('.chart-source').textContent = state.seriesSource === 'local' || state.artifactSource === 'local' || state.artifactSource === 'adapterFallback' ? 'Series computed from local data packs' : 'Backend series artifact';
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

function renderCompare(payload) {
  const envelopes = payload.results || [];
  const snapshots = new Set(envelopes.map((envelope) => envelope.data_snapshot_id || envelope.result?.data_snapshot_id).filter(Boolean));
  const methodologies = new Set(envelopes.map((envelope) => envelope.methodology_version || envelope.result?.methodology?.methodology_version).filter(Boolean));
  const consistency = snapshots.size > 1 || methodologies.size > 1;
  const rows = envelopes.map((envelope) => {
    const result = envelope.result || envelope; const security = result.security; const finalSgd = result.investment.final_value_sgd;
    return `<div class="compare-row"><div><strong>${escapeHtml(security.ticker)}</strong><span>${escapeHtml(security.name)}</span></div><strong>${formatPercent(result.returns.total_return_foreign_currency)}</strong><strong>${formatPercent(result.returns.total_return)}</strong><span>${formatMoney(finalSgd, 'SGD')}</span><small class="status-chip ${result.data_quality.status === 'OK' ? 'ok' : ''}">${escapeHtml(result.data_quality.status || 'REVIEW')}</small></div>`;
  }).join('');
  const note = consistency ? '<p class="consistency-warning" role="alert">These results use different backend snapshots or methodology versions. Treat the comparison as directional.</p>' : '<p class="detail-note">All rows use the same date range, capital, scenario, data snapshot and methodology version.</p>';
  $('#compare-results').innerHTML = rows ? `<div class="compare-table-head"><span>SECURITY</span><span>NATIVE RETURN</span><span>SGD RETURN</span><span>ENDING VALUE</span><span>DATA</span></div>${rows}${note}` : '<div class="result-empty compact-empty"><h3>No comparable results.</h3></div>';
}

function renderComparePicker(query = '') {
  const input = $('#compare-tickers');
  const list = $('#compare-ticker-options');
  if (!input || !list) return;
  const wanted = String(query || '').trim().toLowerCase();
  const matches = securityEntries().filter(({ security }) => {
    if (state.compareTickers.includes(security.security_id)) return false;
    const text = [security.ticker, security.name, security.isin, security.exchange, security.market].filter(Boolean).join(' ').toLowerCase();
    return !wanted || text.includes(wanted);
  });
  const visible = matches.slice(0, COMBOBOX_RESULT_LIMIT);
  list.innerHTML = visible.map(({ security }, index) => `<div class="combobox-option" id="compare-ticker-option-${index}" role="option" data-security-id="${escapeHtml(security.security_id)}"><strong>${escapeHtml(security.ticker)}</strong><span>${escapeHtml(security.name)} · ${escapeHtml(security.exchange)}</span></div>`).join('')
    || '<div class="combobox-empty" role="status">No additional securities match that search.</div>';
  if (matches.length > COMBOBOX_RESULT_LIMIT) list.insertAdjacentHTML('beforeend', `<div class="combobox-more" role="status">Showing ${COMBOBOX_RESULT_LIMIT} of ${matches.length}. Keep typing to narrow the list.</div>`);
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
  }).join('');
}

function selectCompareSecurity(securityId) {
  if (!entryForId(securityId) || state.compareTickers.includes(securityId) || state.compareTickers.length >= 6) return;
  state.compareTickers.push(securityId);
  renderCompareChips();
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
      state.compareTickers.pop(); editView('compare'); renderCompareChips(); renderComparePicker('');
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
  chips?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-remove-security-id]');
    if (!button) return;
    editView('compare'); state.compareTickers = state.compareTickers.filter((securityId) => securityId !== button.dataset.removeSecurityId);
    renderCompareChips(); renderComparePicker(input.value);
  });
}

function selectedCompareTickers() {
  return state.compareTickers.map((securityId) => entryForId(securityId)?.security.ticker).filter(Boolean);
}

async function submitCompare(event) {
  event.preventDefault(); beginView('compare'); const error = $('#compare-error'); error.textContent = '';
  const tickers = selectedCompareTickers();
  if (tickers.length < 2 || tickers.length > 6) { error.textContent = 'Enter between 2 and 6 catalog tickers.'; failView('compare', 'invalid'); return; }
  const amount = Number($('#compare-amount').value); if (!(amount > 0)) { error.textContent = 'Enter capital greater than S$0.'; failView('compare', 'invalid'); return; }
  if ($('#compare-end').value < $('#compare-start').value) { error.textContent = 'End date must be on or after start date.'; failView('compare', 'invalid'); return; }
  const scenario = PRESETS[$('#compare-scenario').value] || PRESETS.investor; const request = { tickers: tickers.join(','), initial_sgd: $('#compare-amount').value, start_date: $('#compare-start').value, end_date: $('#compare-end').value, ...scenario }; const button = event.currentTarget.querySelector('button[type="submit"]'); setBusy(button, true);
  const runSeq = s6Runs.compare += 1;
  try {
    if (API_BASE) {
      try {
        const key = requestKey('compare', { ...request, methodology_version: '1.0', data_snapshot_id: 'local-canonical-parquet' });
        const payload = await apiGet('/compare', { ...request, request_key: key });
        if (!s6RunCurrent('compare', runSeq)) return;
        completeView('compare', request, payload);
        renderCompare(payload);
        setComputeMode('adapter');
        return;
      } catch (adapterError) {
        if (!s6RunCurrent('compare', runSeq)) return;
        error.textContent = `${adapterError.message} — falling back to the local engine.`;
      }
    }
    const results = [];
    for (const ticker of tickers) {
      s6SetButtonProgress(button, `Computing ${ticker} locally…`);
      const outcome = await s6AnalysisViaPacks({
        ticker,
        label: ticker,
        initial_sgd: request.initial_sgd,
        start_date: request.start_date,
        end_date: request.end_date,
        dividends: scenario.dividends,
        withholding: scenario.withholding,
        reinvest: scenario.reinvest,
      });
      if (!s6RunCurrent('compare', runSeq)) return;
      results.push(outcome.envelope);
    }
    if (!s6RunCurrent('compare', runSeq)) return;
    completeView('compare', request, { results });
    renderCompare({ results });
    error.textContent = '';
    setComputeMode(API_BASE ? 'adapterFallback' : 'local');
  } catch (compareError) {
    if (s6RunCurrent('compare', runSeq)) { error.textContent = compareError.message; failView('compare'); }
  }
  finally { if (s6RunCurrent('compare', runSeq)) setBusy(button, false); }
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
  const noWarningsCopy = payload.request ? 'Backend replay completed with no warnings.' : 'Local engine replay completed with no warnings.';
  const support = context.support;
  const packWarnings = context.packWarnings || [];
  const supportNotice = support && support.status !== 'fully_supported'
    ? `<p class="consistency-warning" role="alert">Data pack coverage for ${escapeHtml(security.ticker)} is ${escapeHtml(support.status)}${support.reason ? `: ${escapeHtml(support.reason)}` : ''}. Results use the data actually present in the packs.${packWarnings.length ? ` Pack notes: ${escapeHtml(packWarnings.join(' '))}` : ''}</p>`
    : '';
  $('#dca-results').innerHTML = `<div class="analysis-output"><div class="dca-output-head"><div class="output-kicker">${escapeHtml(security.ticker)} · ${escapeHtml(titleCase(request?.frequency || 'monthly'))}</div><div class="mini-switch" role="group" aria-label="DCA display currency"><button type="button" data-dca-currency="native" aria-pressed="${native}" class="${native ? 'active' : ''} ${security.currency === 'SGD' ? 'hidden' : ''}">${escapeHtml(security.currency)}</button><button type="button" data-dca-currency="sgd" aria-pressed="${!native}" class="${native ? '' : 'active'}">SGD</button></div></div><h3>${formatMoney(finalValue, currency)}</h3><p>Ending value after ${escapeHtml(String(result.contribution_dates.length))} contributions.</p><div class="output-grid"><span>Contributed<strong>${formatMoney(contributed, currency)}</strong></span><span>Gain / loss<strong>${formatMoney(gainLoss, currency)}</strong></span><span>XIRR · money-weighted<strong>${formatPercent(xirr)}</strong></span><span>Shares<strong>${Number(result.shares).toFixed(5)}</strong></span></div><details class="contribution-dates"><summary>Contribution dates (${result.contribution_dates.length})</summary><p>${result.contribution_dates.map((date) => `<time datetime="${escapeHtml(date)}">${escapeHtml(formatDate(date))}</time>`).join(' · ')}</p></details><p class="detail-note">${escapeHtml(warnings.join(' ') || noWarningsCopy)}</p>${supportNotice}</div>`;
  renderCoverage('dca', result, context.coverage);
  $$('[data-dca-currency]').forEach((button) => button.addEventListener('click', () => { state.dcaCurrencyMode = button.dataset.dcaCurrency; if (state.dcaArtifact) renderDca(state.dcaArtifact); }));
}

// Explicit DCA submission uses the existing worker supersede/cancel contract.
async function submitDca(event) {
  event.preventDefault();
  s7CancelAutoRun('dca');
  await s7RunDca({ mode: 'force' });
}

async function s7RunDca({ mode = 'force' } = {}) {
  const form = $('#dca-form');
  if (!form) return;
  beginView('dca');
  const error = $('#dca-error'); error.textContent = '';
  if ($('#dca-end').value < $('#dca-start').value) { error.textContent = 'End date must be on or after start date.'; failView('dca', 'invalid'); return; }
  const contribution = Number($('#dca-contribution').value); if (!(contribution > 0)) { error.textContent = 'Enter a contribution greater than S$0.'; failView('dca', 'invalid'); return; }
  const scenario = scenarioValues('dca');
  const request = { security_id: securityComboboxValue('#dca-security'), contribution_sgd: $('#dca-contribution').value, frequency: $('#dca-frequency').value, start_date: $('#dca-start').value, end_date: $('#dca-end').value, ...scenario };
  if (!request.security_id) { error.textContent = 'Choose a security from the published catalog.'; $('#dca-security')?.setAttribute('aria-invalid', 'true'); failView('dca', 'invalid'); return; }
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
  const selectedId = values.securityId || state.selectedSecurityId || '';
  const currencies = [...new Set(securityEntries().map(({ security }) => security.currency).filter(Boolean))].sort();
  const currencyOptions = currencies.map((currency) => `<option ${currency === (values.currency || entryForId(selectedId)?.security.currency || 'USD') ? 'selected' : ''}>${escapeHtml(currency)}</option>`).join('');
  const typeOptions = ['BUY', 'SELL', 'DIVIDEND', 'CASH_DEPOSIT', 'CASH_WITHDRAWAL'].map((type) => `<option ${type === (values.type || 'BUY') ? 'selected' : ''}>${type}</option>`).join('');
  const comboId = `ledger-security-${document.querySelectorAll('.ledger-security').length + 1}`;
  const selected = entryForId(selectedId)?.security;
  const selectedLabel = selected ? securityDisplayLabel(selected) : '';
  return `<tr><td><select class="ledger-type">${typeOptions}</select></td><td><div class="form-combobox ledger-combobox" data-combobox><input id="${comboId}" class="ledger-security combobox-input" type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="${comboId}-options" autocomplete="off" placeholder="Search or choose cash…" value="${escapeHtml(selectedLabel)}" data-security-id="${escapeHtml(selectedId)}" /><div class="combobox-list hidden" id="${comboId}-options" role="listbox" aria-label="Ledger securities"></div></div></td><td><input class="ledger-date" type="date" value="${escapeHtml(values.date || '2024-01-02')}" /></td><td><input class="ledger-quantity" type="number" min="0" step="0.000001" value="${escapeHtml(values.quantity || '1')}" /></td><td><input class="ledger-cash" type="number" min="0" step="0.01" value="${escapeHtml(values.cash || '1000')}" /></td><td><select class="ledger-currency">${currencyOptions}</select></td></tr>`;
}

function addLedgerRow(values = {}) { if (has('#ledger-rows')) { $('#ledger-rows').insertAdjacentHTML('beforeend', ledgerRowTemplate(values)); wireSecurityComboboxes(); } }

function renderPortfolio(payload, meta = {}) {
  const result = payload.result || payload;
  const rows = result.holdings.map((holding) => { const ccy = s5CurrencyForId(holding.security_id); return `<tr><th scope="row">${escapeHtml(holding.ticker)}</th><td>${Number(holding.quantity).toFixed(5)}</td><td>${formatMoney(holding.weighted_average_cost, ccy)}</td><td>${formatMoney(holding.market_value_native, ccy)}</td><td>${formatMoney(holding.market_value_sgd, 'SGD')}</td><td>${formatMoney(holding.realized_pl_native, ccy)}</td><td>${formatMoney(holding.unrealized_pl_native, ccy)}</td></tr>`; }).join('');
  const warnings = meta.warnings || [];
  const warningNote = warnings.length ? `<p class="detail-note" role="alert">Data warnings: ${escapeHtml(warnings.join(' '))}</p>` : '';
  const sourceNote = meta.source === 'local' ? '<p class="detail-note">Reconstructed locally in your browser from the published data packs.</p>' : '';
  $('#portfolio-results').innerHTML = `<div class="analysis-output"><div class="output-kicker">AS OF ${escapeHtml(formatDate(result.as_of))}</div><h3>${formatMoney(result.total_market_value_sgd, 'SGD')}</h3><p>Mark-to-market portfolio value across ${result.holdings.length} holding${result.holdings.length === 1 ? '' : 's'}.</p><div class="holding-table-wrap"><table class="holding-table"><caption class="sr-only">Portfolio holdings as of ${escapeHtml(formatDate(result.as_of))}</caption><thead><tr><th scope="col">Ticker</th><th scope="col">Quantity</th><th scope="col">WAC</th><th scope="col">Native value</th><th scope="col">SGD value</th><th scope="col">Realised P/L</th><th scope="col">Unrealised P/L</th></tr></thead><tbody>${rows || '<tr><td colspan="7">No open holdings on this date.</td></tr>'}</tbody></table></div><p class="detail-note">Cash: ${Object.entries(result.cash_by_currency || {}).map(([currency, amount]) => `${formatMoney(amount, currency)}`).join(' · ') || 'none'} · Realised P/L: ${Object.entries(result.realized_pl_native || {}).map(([currency, amount]) => `${formatMoney(amount, currency)}`).join(' · ') || 'none'}.</p>${warningNote}${sourceNote}<p class="detail-note">Weighted-average cost is a reporting convention, not a Singapore capital-gains tax calculation.</p></div>`;
}

function s5CollectLedgerRows() {
  return $$('#ledger-rows tr').map((row) => ({
    transaction_type: row.querySelector('.ledger-type').value,
    security_id: securityComboboxValue(row.querySelector('.ledger-security')) || null,
    transaction_date: row.querySelector('.ledger-date').value,
    quantity: row.querySelector('.ledger-quantity').value,
    cash_amount: row.querySelector('.ledger-cash').value,
    currency: row.querySelector('.ledger-currency').value,
    fees: '0',
  }));
}

function s5ValidateLedger(rows, asOf) {
  if (!rows.length) return 'Add at least one ledger transaction.';
  if (!asOf) return 'Choose an as-of date for the reconstruction.';
  for (let index = 0; index < rows.length; index++) {
    if (!rows[index].transaction_date) return `Ledger row ${index + 1} needs a transaction date.`;
    for (const field of ['quantity', 'cash_amount']) {
      const amount = Number(rows[index][field]);
      if (rows[index][field] === '' || !Number.isFinite(amount) || amount < 0) return `Ledger row ${index + 1} needs a non-negative ${field === 'quantity' ? 'quantity' : 'cash amount'}.`;
    }
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
  ['#catalog-search', '#asset-filter', '#universe-filter', '#market-filter', '#currency-filter', '#distribution-filter', '#active-filter'].forEach((selector) => { if (has(selector)) $(selector).addEventListener('input', renderCatalog); });
  if (has('#catalog-more')) $('#catalog-more').addEventListener('click', () => { state.catalogLimit = Math.min(state.catalogLimit + 100, 1000); renderCatalog(); });
  if (has('#security-select')) $('#security-select').addEventListener('change', (event) => selectSecurity(securityComboboxValue(event.target)));
  if (has('#scenario-select')) $('#scenario-select').addEventListener('change', (event) => syncPreset(event.target.value));
  ['#dividends-toggle', '#tax-toggle', '#reinvest-toggle'].forEach((selector) => { if (has(selector)) $(selector).addEventListener('change', () => { if (has('#scenario-select')) $('#scenario-select').value = 'custom'; }); });
  if (has('#analysis-form')) $('#analysis-form').addEventListener('submit', submitAnalysis);
  if (has('#compare-form')) { const form = $('#compare-form'); form.addEventListener('submit', submitCompare); form.querySelector('button[type="submit"]').addEventListener('click', (event) => { event.preventDefault(); submitCompare({ preventDefault() {}, currentTarget: form }); }); }
  if (has('#dca-form')) { const form = $('#dca-form'); form.addEventListener('submit', submitDca); form.querySelector('button[type="submit"]').addEventListener('click', (event) => { event.preventDefault(); submitDca({ preventDefault() {}, currentTarget: form }); }); }
  if (has('#portfolio-form')) { const form = $('#portfolio-form'); form.addEventListener('submit', submitPortfolio); form.querySelector('button[type="submit"]').addEventListener('click', (event) => { event.preventDefault(); submitPortfolio({ preventDefault() {}, currentTarget: form }); }); }
  if (has('#add-ledger-row')) $('#add-ledger-row').addEventListener('click', () => { addLedgerRow(); s5AutoSaveLedger(); editView('portfolio'); });
  if (has('#ledger-rows')) $('#ledger-rows').addEventListener('change', (event) => { if (!event.target.classList.contains('ledger-security')) return; const security = entryForId(securityComboboxValue(event.target))?.security; if (security) event.target.closest('tr').querySelector('.ledger-currency').value = security.currency; });
  if (has('#ledger-rows')) s5WireLedgerPersistence();
  $$('.currency-button').forEach((button) => button.addEventListener('click', () => { state.currencyMode = button.dataset.currency; if (state.artifact) renderResult(); }));
  if (has('#warnings-toggle')) $('#warnings-toggle').addEventListener('click', () => { state.warningsOpen = !state.warningsOpen; renderQuality(state.artifact?.result?.data_quality || {}); });
  ['#dca-form', '#portfolio-form', '#compare-form'].forEach(sel => { if (has(sel)) $(sel).noValidate = true; });
  wireRequestEdits();
  if (has('#return-to-demo')) $('#return-to-demo').addEventListener('click', async () => { const entry = entryForTicker('QQQ'); if (!entry) return; selectSecurity(entry.security.security_id); $('#initial-amount').value = '10000'; $('#start-date').value = '2024-01-02'; $('#end-date').value = '2025-01-02'; $('#scenario-select').value = 'investor'; syncPreset('investor'); $('#analysis-form').requestSubmit(); });
  if (has('#download-result')) $('#download-result').addEventListener('click', () => { if (!state.artifact) return; const blob = new Blob([JSON.stringify(state.artifact, null, 2)], { type: 'application/json' }); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `sg-invest-${state.artifact.result?.security?.ticker || 'analysis'}.json`; link.click(); URL.revokeObjectURL(link.href); });
  if (has('#copy-link')) $('#copy-link').addEventListener('click', copyAnalysisLink);
  if (has('#toggle-series-table')) $('#toggle-series-table').addEventListener('click', () => { const table = $('#series-table-wrap'); const button = $('#toggle-series-table'); const open = table.classList.toggle('hidden') === false; button.setAttribute('aria-expanded', String(open)); button.textContent = open ? 'Hide table' : 'View as table'; });
  if (has('#download-series-csv')) $('#download-series-csv').addEventListener('click', downloadSeriesCsv);
  initComparePicker();
}

function applyAnalysisUrl() {
  const params = new URLSearchParams(window.location.search);
  if (!params.get('security_id') || !entryForId(params.get('security_id')) || !has('#analysis-form')) return;
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
  s5RestoreLedger();
  wireEvents();
  initializeResultStates();
  setComputeMode(API_BASE ? 'adapter' : 'local');
  if (has('#data-date')) {
    const status = API_BASE ? await apiGet('/status').catch(() => loadJson('data/data-status.json', null)) : await loadJson('data/data-status.json', null);
    $('#data-date').textContent = status?.backfill?.as_of ? formatDate(status.backfill.as_of) : '30 Aug 2026';
  }
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

function s5RenderLedgerRows(rows) {
  if (!has('#ledger-rows')) return;
  $('#ledger-rows').innerHTML = '';
  rows.forEach((row) => addLedgerRow({ type: row.transaction_type, securityId: row.security_id || '', date: row.transaction_date, quantity: row.quantity, cash: row.cash_amount, currency: row.currency }));
}

async function s5RestoreLedger() {
  try {
    const rows = await ledgerStore.load();
    if (rows.length) { s5RenderLedgerRows(rows); return; }
  } catch (error) {
    console.warn(`Ledger restore failed: ${error.message}`);
  }
  addLedgerRow({ quantity: '10', cash: '4000' });
}

function s5AutoSaveLedger() {
  ledgerStore.save(s5CollectLedgerRows()).catch((error) => console.warn(`Ledger save failed: ${error.message}`));
}

function s5WireLedgerPersistence() {
  $('#ledger-rows').addEventListener('change', () => s5AutoSaveLedger());
  if (has('#add-ledger-row')) $('#add-ledger-row').insertAdjacentHTML('afterend', '<button class="text-button" type="button" id="clear-ledger">Clear ledger</button> <button class="text-button" type="button" id="export-ledger">Export JSON</button> <button class="text-button" type="button" id="import-ledger">Import JSON</button>');
  if (has('#clear-ledger')) $('#clear-ledger').addEventListener('click', async () => {
    try { await ledgerStore.clear(); } catch (error) { console.warn(`Ledger clear failed: ${error.message}`); }
    $('#ledger-rows').innerHTML = '';
    addLedgerRow();
    s5AutoSaveLedger();
    editView('portfolio');
  });
  if (has('#export-ledger')) $('#export-ledger').addEventListener('click', async () => {
    try {
      const blob = new Blob([await ledgerStore.exportJson()], { type: 'application/json' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'sg-invest-ledger.json';
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (error) {
      $('#portfolio-error').textContent = `Ledger export failed: ${error.message}`;
    }
  });
  if (has('#import-ledger')) $('#import-ledger').addEventListener('click', () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'application/json,.json';
    input.addEventListener('change', async () => {
      const file = input.files && input.files[0];
      if (!file) return;
      try { s5RenderLedgerRows(await ledgerStore.importJson(await file.text())); editView('portfolio'); }
      catch (error) { $('#portfolio-error').textContent = `Ledger import failed: ${error.message}`; }
    });
    input.click();
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
    return { envelope, context: { support, packWarnings: inputs.warnings || [], coverage: coverageFromInputs(entry, inputs, manifest) } };
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
  Object.keys(resultViews).forEach(kind => {
    const form = $(`#${kind}-form`);
    if (!form) return;
    ['input', 'change'].forEach(type => form.addEventListener(type, event => {
      if (!event.target.matches('input, select, textarea')) return;
      editView(kind);
    }));
  });
}
