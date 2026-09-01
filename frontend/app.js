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

const DEMO_ARTIFACT = 'data/analyses/qqq-2024.json';
const CATALOG_ARTIFACT = 'data/catalog.json';
const API_BASE = (document.querySelector('meta[name="sg-invest-api-base"]')?.content || '').replace(/\/$/, '');

// S6 wiring: one honest computation mode. The engine client and pack loader
// always run locally (packs → worker); when an adapter API base is
// configured the adapter is tried first and the local engine is the explicit
// fallback. The compute mode behind every visible result is shown in the
// header mode indicator (see setComputeMode).
const packs = createPackLoader({ baseUrl: new URL('.', document.baseURI).href });
const engineClient = createEngineClient();
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
  dcaArtifact: null,
  selectedSecurityId: null,
  currencyMode: 'sgd',
  warningsOpen: true,
  catalogLimit: 12,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const has = (selector) => Boolean($(selector));

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
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
// 'Demo replay · published artifact' while the init-time committed replay is
// on screen (that replay is not a computed request).

function ensureModeIndicator() {
  let chip = $('#mode-indicator');
  if (chip) return chip;
  const host = document.querySelector('.header-meta');
  if (!host) return null;
  chip = document.createElement('span');
  chip.id = 'mode-indicator';
  chip.className = 'security-tag';
  chip.setAttribute('role', 'status');
  chip.title = 'Computation mode that produced the most recent visible result';
  host.appendChild(chip);
  return chip;
}

function adapterModeLabel() {
  let origin = API_BASE;
  try { origin = new URL(API_BASE).origin; } catch { /* keep raw base */ }
  return `Adapter · ${origin}`;
}

const COMPUTE_MODE_LABELS = Object.freeze({
  local: 'Local compute',
  adapter: null, // rendered via adapterModeLabel()
  adapterFallback: 'Local compute (adapter unavailable)',
  demo: 'Demo replay · published artifact',
});

function setComputeMode(mode) {
  const chip = ensureModeIndicator();
  if (!chip) return;
  const label = mode === 'adapter' ? adapterModeLabel() : COMPUTE_MODE_LABELS[mode] || COMPUTE_MODE_LABELS.local;
  chip.textContent = label;
  chip.dataset.mode = mode;
}

// --- S7.4: build identifier + snapshot date ---------------------------------
// deploy-tier1.yml emits build-info.json next to index.html
// ({built_at, data_snapshot_id, workflow_run_id}). The plain pages.yml deploy
// has no such file, so a 404 (or any fetch failure) is expected and silently
// ignored — the #data-date element keeps its data-status fallback. When the
// file is present, the build date is shown next to the snapshot chip.

async function loadBuildInfo() {
  try {
    const response = await fetch('build-info.json', { cache: 'no-store' });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

function renderBuildInfo(info) {
  if (!info || !has('#data-date')) return;
  const builtAt = typeof info.built_at === 'string' ? info.built_at : '';
  const buildDate = builtAt ? formatDate(builtAt.slice(0, 10)) : null;
  if (!buildDate || has('#build-date')) return;
  const host = $('#data-date').closest('.header-meta') || $('#data-date').parentElement;
  if (!host) return;
  const chip = document.createElement('span');
  chip.innerHTML = `· Build <strong id="build-date">${escapeHtml(buildDate)}</strong>`;
  chip.title = `Site build ${builtAt} · data snapshot ${info.data_snapshot_id || 'unknown'} · workflow run ${info.workflow_run_id ?? 'n/a'}`;
  host.appendChild(chip);
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
  const options = securityEntries().map(({ security }) => `<option value="${escapeHtml(security.security_id)}">${escapeHtml(security.ticker)} — ${escapeHtml(security.name)}</option>`).join('');
  ['#security-select', '#dca-security'].forEach((selector) => {
    if (has(selector)) $(selector).innerHTML = options;
  });
  const qqq = entryForTicker('QQQ') || securityEntries()[0];
  if (qqq) selectSecurity(qqq.security.security_id);
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
    $$('.security-card').forEach((card) => card.addEventListener('click', () => selectSecurity(card.dataset.securityId, true)));
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
  ['#security-select', '#dca-security'].forEach((selector) => { if (has(selector)) $(selector).value = securityId; });
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

function analysisLink() {
  const result = state.artifact?.result;
  if (!result) return window.location.href;
  const request = state.artifact.request || {};
  const params = new URLSearchParams({
    security_id: result.security.security_id,
    start_date: result.period.start_date,
    end_date: result.period.end_date,
    initial_sgd: String(result.initial_investment_sgd),
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
    demo: 'Published demo replay',
    local: 'Computed locally in your browser',
    adapter: 'Adapter result',
    adapterFallback: 'Computed locally in your browser (adapter unavailable)',
  };
  const label = labels[state.artifactSource] || 'Published result artifact';
  const version = state.artifact?.methodology_version || state.artifact?.result?.methodology?.methodology_version || '1.0';
  source.innerHTML = `<span class="tiny-dot"></span> ${escapeHtml(label)} · methodology <span id="method-version">${escapeHtml(String(version))}</span>`;
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
  if (has('.chart-source')) $('.chart-source').textContent = state.artifactSource === 'local' || state.artifactSource === 'adapterFallback' ? 'Series computed from local data packs' : 'Backend series artifact';
}

function showResult() {
  $('#result-empty').classList.add('hidden'); $('#artifact-unavailable').classList.add('hidden'); $('#result-content').classList.remove('hidden'); renderResult();
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

async function submitAnalysis(event) {
  event.preventDefault();
  const error = $('#form-error'); error.textContent = '';
  const amount = Number($('#initial-amount').value);
  if (!Number.isFinite(amount) || amount <= 0) { error.textContent = 'Enter an initial amount greater than S$0.'; return; }
  if (!$('#start-date').value || !$('#end-date').value || $('#end-date').value < $('#start-date').value) { error.textContent = 'Choose an end date on or after the start date.'; return; }
  const entry = entryForId($('#security-select').value); if (!entry) { error.textContent = 'Choose a security from the published catalog.'; return; }
  const scenario = scenarioValues();
  const request = { security_id: entry.security.security_id, initial_sgd: $('#initial-amount').value, start_date: $('#start-date').value, end_date: $('#end-date').value, ...scenario };
  const button = event.currentTarget.querySelector('button[type="submit"]'); setBusy(button, true);
  const runSeq = s6Runs.analysis += 1;
  try {
    if (API_BASE) {
      try {
        const key = requestKey('analysis', { ...request, methodology_version: '1.0', data_snapshot_id: 'local-canonical-parquet' });
        const artifact = await apiGet('/analyze', { ...request, request_key: key });
        const series = await apiGet('/series', { security_id: request.security_id, start_date: request.start_date, end_date: request.end_date }).catch(() => null);
        if (!s6RunCurrent('analysis', runSeq)) return;
        state.artifact = artifact; state.artifactSource = 'adapter'; state.series = series;
        error.textContent = '';
        showResult();
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
    }, (label) => s6SetButtonProgress(button, label));
    if (!s6RunCurrent('analysis', runSeq)) return;
    state.artifact = outcome.envelope;
    state.artifactSource = API_BASE ? 'adapterFallback' : 'local';
    state.series = outcome.series;
    error.textContent = '';
    showResult();
    setComputeMode(state.artifactSource);
  } catch (computeError) {
    if (!s6RunCurrent('analysis', runSeq)) return;
    showUnavailable(computeError.message);
    error.textContent = computeError.message;
  } finally {
    if (s6RunCurrent('analysis', runSeq)) setBusy(button, false);
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

async function submitCompare(event) {
  event.preventDefault(); const error = $('#compare-error'); error.textContent = '';
  const tickers = $('#compare-tickers').value.split(',').map((item) => item.trim().toUpperCase()).filter(Boolean);
  if (tickers.length < 2 || tickers.length > 6) { error.textContent = 'Enter between 2 and 6 catalog tickers.'; return; }
  const amount = Number($('#compare-amount').value); if (!(amount > 0)) { error.textContent = 'Enter capital greater than S$0.'; return; }
  if ($('#compare-end').value < $('#compare-start').value) { error.textContent = 'End date must be on or after start date.'; return; }
  const scenario = PRESETS[$('#compare-scenario').value] || PRESETS.investor; const request = { tickers: tickers.join(','), initial_sgd: $('#compare-amount').value, start_date: $('#compare-start').value, end_date: $('#compare-end').value, ...scenario }; const button = event.currentTarget.querySelector('button[type="submit"]'); setBusy(button, true);
  const runSeq = s6Runs.compare += 1;
  try {
    if (API_BASE) {
      try {
        const key = requestKey('compare', { ...request, methodology_version: '1.0', data_snapshot_id: 'local-canonical-parquet' });
        const payload = await apiGet('/compare', { ...request, request_key: key });
        if (!s6RunCurrent('compare', runSeq)) return;
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
    renderCompare({ results });
    error.textContent = '';
    setComputeMode(API_BASE ? 'adapterFallback' : 'local');
  } catch (compareError) {
    if (s6RunCurrent('compare', runSeq)) error.textContent = compareError.message;
  }
  finally { if (s6RunCurrent('compare', runSeq)) setBusy(button, false); }
}

function renderDca(payload, context = {}) {
  state.dcaArtifact = payload;
  s4State.support = context.support || null;
  s4State.packWarnings = context.packWarnings || null;
  const request = payload.request || s4State.request || null;
  const result = payload.result || payload; const security = result.security;
  if (security.currency === 'SGD') state.currencyMode = 'sgd';
  const native = state.currencyMode === 'native'; const currency = native ? security.currency : 'SGD';
  const contributed = native ? result.total_contributed_foreign_currency : result.total_contributed_sgd;
  const finalValue = native ? result.final_value_foreign_currency : result.final_value_sgd;
  const gainLoss = native ? result.gain_loss_foreign_currency : result.gain_loss_sgd;
  const xirr = native ? result.xirr_foreign_currency : result.xirr;
  const warnings = result.data_quality.warnings || [];
  const noWarningsCopy = payload.request ? 'Backend replay completed with no warnings.' : 'Local engine replay completed with no warnings.';
  const support = s4State.support;
  const packWarnings = s4State.packWarnings || [];
  const supportNotice = support && support.status !== 'fully_supported'
    ? `<p class="consistency-warning" role="alert">Data pack coverage for ${escapeHtml(security.ticker)} is ${escapeHtml(support.status)}${support.reason ? `: ${escapeHtml(support.reason)}` : ''}. Results use the data actually present in the packs.${packWarnings.length ? ` Pack notes: ${escapeHtml(packWarnings.join(' '))}` : ''}</p>`
    : '';
  $('#dca-results').innerHTML = `<div class="analysis-output"><div class="dca-output-head"><div class="output-kicker">${escapeHtml(security.ticker)} · ${escapeHtml(titleCase(request?.frequency || 'monthly'))}</div><div class="mini-switch"><button type="button" data-dca-currency="native" class="${native ? 'active' : ''} ${security.currency === 'SGD' ? 'hidden' : ''}">${escapeHtml(security.currency)}</button><button type="button" data-dca-currency="sgd" class="${native ? '' : 'active'}">SGD</button></div></div><h3>${formatMoney(finalValue, currency)}</h3><p>Ending value after ${escapeHtml(String(result.contribution_dates.length))} contributions.</p><div class="output-grid"><span>Contributed<strong>${formatMoney(contributed, currency)}</strong></span><span>Gain / loss<strong>${formatMoney(gainLoss, currency)}</strong></span><span>XIRR · money-weighted<strong>${formatPercent(xirr)}</strong></span><span>Shares<strong>${Number(result.shares).toFixed(5)}</strong></span></div><details class="contribution-dates"><summary>Contribution dates (${result.contribution_dates.length})</summary><p>${result.contribution_dates.map((date) => `<time datetime="${escapeHtml(date)}">${escapeHtml(formatDate(date))}</time>`).join(' · ')}</p></details><p class="detail-note">${escapeHtml(warnings.join(' ') || noWarningsCopy)}</p>${supportNotice}</div>`;
  $$('[data-dca-currency]').forEach((button) => button.addEventListener('click', () => { state.currencyMode = button.dataset.dcaCurrency; if (state.artifact) renderResult(); if (state.dcaArtifact) renderDca(state.dcaArtifact); }));
}

async function submitDca(event) {
  event.preventDefault(); const error = $('#dca-error'); error.textContent = '';
  if ($('#dca-end').value < $('#dca-start').value) { error.textContent = 'End date must be on or after start date.'; return; }
  const contribution = Number($('#dca-contribution').value); if (!(contribution > 0)) { error.textContent = 'Enter a contribution greater than S$0.'; return; }
  const scenario = scenarioValues('dca');
  const request = { security_id: $('#dca-security').value, contribution_sgd: $('#dca-contribution').value, frequency: $('#dca-frequency').value, start_date: $('#dca-start').value, end_date: $('#dca-end').value, ...scenario };
  const button = event.currentTarget.querySelector('button[type="submit"]');
  s4State.request = request; s4State.button = button; s4State.requestId = null;
  setBusy(button, true);
  const runSeq = s4State.runSeq = (s4State.runSeq || 0) + 1;
  try {
    if (API_BASE) {
      const key = requestKey('dca', { ...request, methodology_version: '1.0', data_snapshot_id: 'local-canonical-parquet' });
      try {
        renderDca(await apiGet('/dca', { ...request, request_key: key }));
        setComputeMode('adapter');
        return;
      } catch (adapterError) {
        error.textContent = `${adapterError.message} — falling back to the local engine.`;
      }
    }
    s4SetDcaProgress('Resolving published data packs…');
    const envelope = await s4DcaViaPacks(request);
    if (runSeq === s4State.runSeq && envelope) { error.textContent = ''; renderDca(envelope, { support: s4State.support, packWarnings: s4State.packWarnings }); setComputeMode(API_BASE ? 'adapterFallback' : 'local'); }
  } catch (staticError) {
    if (runSeq === s4State.runSeq) error.textContent = staticError.message;
  } finally {
    if (runSeq === s4State.runSeq) { $('#s4-dca-progress')?.remove(); setBusy(button, false); s4State.button = null; }
  }
}

function ledgerRowTemplate(values = {}) {
  const selectedId = values.securityId || state.selectedSecurityId || '';
  const options = securityEntries().map(({ security }) => `<option value="${escapeHtml(security.security_id)}" ${security.security_id === selectedId ? 'selected' : ''}>${escapeHtml(security.ticker)} · ${escapeHtml(security.exchange)}</option>`).join('');
  const currencies = [...new Set(securityEntries().map(({ security }) => security.currency).filter(Boolean))].sort();
  const currencyOptions = currencies.map((currency) => `<option ${currency === (values.currency || entryForId(selectedId)?.security.currency || 'USD') ? 'selected' : ''}>${escapeHtml(currency)}</option>`).join('');
  const typeOptions = ['BUY', 'SELL', 'DIVIDEND', 'CASH_DEPOSIT', 'CASH_WITHDRAWAL'].map((type) => `<option ${type === (values.type || 'BUY') ? 'selected' : ''}>${type}</option>`).join('');
  return `<tr><td><select class="ledger-type">${typeOptions}</select></td><td><select class="ledger-security"><option value="">Cash only</option>${options}</select></td><td><input class="ledger-date" type="date" value="${escapeHtml(values.date || '2024-01-02')}" /></td><td><input class="ledger-quantity" type="number" min="0" step="0.000001" value="${escapeHtml(values.quantity || '1')}" /></td><td><input class="ledger-cash" type="number" min="0" step="0.01" value="${escapeHtml(values.cash || '1000')}" /></td><td><select class="ledger-currency">${currencyOptions}</select></td></tr>`;
}

function addLedgerRow(values = {}) { if (has('#ledger-rows')) $('#ledger-rows').insertAdjacentHTML('beforeend', ledgerRowTemplate(values)); }

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
    security_id: row.querySelector('.ledger-security').value || null,
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

async function submitPortfolio(event) {
  event.preventDefault(); const error = $('#portfolio-error'); error.textContent = '';
  const asOf = $('#portfolio-as-of').value;
  const transactions = s5CollectLedgerRows();
  const validationError = s5ValidateLedger(transactions, asOf);
  if (validationError) { error.textContent = validationError; return; }
  const button = event.currentTarget.querySelector('button[type="submit"]'); setBusy(button, true);
  const runSeq = s6Runs.portfolio += 1;
  try {
    if (API_BASE) {
      try {
        const payload = await fetch(`${API_BASE}/api/portfolio`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ as_of: asOf, transactions }) }).then(async (response) => { const body = await response.json(); if (!response.ok || body.error) throw new Error(body.error || 'Portfolio request failed'); return body; });
        if (!s6RunCurrent('portfolio', runSeq)) return;
        renderPortfolio(payload);
        setComputeMode('adapter');
        return;
      } catch (adapterError) {
        if (!s6RunCurrent('portfolio', runSeq)) return;
        error.textContent = `${adapterError.message} — falling back to the local engine.`;
      }
    }
    // S6.2: static deployments (empty API base) go straight to the local
    // engine — the old relative POST probe to 'api/portfolio' is gone.
    const local = await s5LocalPortfolio(asOf, transactions);
    if (!s6RunCurrent('portfolio', runSeq)) return;
    if (local.unavailable) s5ShowPortfolioUnavailable(local.unavailable);
    else { renderPortfolio(local.envelope, local.meta); setComputeMode(API_BASE ? 'adapterFallback' : 'local'); }
  } catch (localError) {
    if (s6RunCurrent('portfolio', runSeq)) error.textContent = localError.message;
  }
  finally { if (s6RunCurrent('portfolio', runSeq)) setBusy(button, false); }
}

function wireEvents() {
  if (has('#mobile-nav-toggle')) $('#mobile-nav-toggle').addEventListener('click', () => { const menu = $('#mobile-nav'); const open = !menu.classList.contains('open'); menu.classList.toggle('hidden', !open); menu.classList.toggle('open', open); $('#mobile-nav-toggle').setAttribute('aria-expanded', String(open)); });
  $$('#mobile-nav a').forEach((link) => link.addEventListener('click', () => { $('#mobile-nav')?.classList.add('hidden'); $('#mobile-nav')?.classList.remove('open'); $('#mobile-nav-toggle')?.setAttribute('aria-expanded', 'false'); }));
  ['#catalog-search', '#asset-filter', '#universe-filter', '#market-filter', '#currency-filter', '#distribution-filter', '#active-filter'].forEach((selector) => { if (has(selector)) $(selector).addEventListener('input', renderCatalog); });
  if (has('#catalog-more')) $('#catalog-more').addEventListener('click', () => { state.catalogLimit = Math.min(state.catalogLimit + 100, 1000); renderCatalog(); });
  if (has('#security-select')) $('#security-select').addEventListener('change', (event) => selectSecurity(event.target.value));
  if (has('#scenario-select')) $('#scenario-select').addEventListener('change', (event) => syncPreset(event.target.value));
  ['#dividends-toggle', '#tax-toggle', '#reinvest-toggle'].forEach((selector) => { if (has(selector)) $(selector).addEventListener('change', () => { if (has('#scenario-select')) $('#scenario-select').value = 'custom'; }); });
  if (has('#analysis-form')) $('#analysis-form').addEventListener('submit', submitAnalysis);
  if (has('#compare-form')) { const form = $('#compare-form'); form.addEventListener('submit', submitCompare); form.querySelector('button[type="submit"]').addEventListener('click', (event) => { event.preventDefault(); submitCompare({ preventDefault() {}, currentTarget: form }); }); }
  if (has('#dca-form')) { const form = $('#dca-form'); form.addEventListener('submit', submitDca); form.querySelector('button[type="submit"]').addEventListener('click', (event) => { event.preventDefault(); submitDca({ preventDefault() {}, currentTarget: form }); }); }
  if (has('#portfolio-form')) { const form = $('#portfolio-form'); form.addEventListener('submit', submitPortfolio); form.querySelector('button[type="submit"]').addEventListener('click', (event) => { event.preventDefault(); submitPortfolio({ preventDefault() {}, currentTarget: form }); }); }
  if (has('#add-ledger-row')) $('#add-ledger-row').addEventListener('click', () => { addLedgerRow(); s5AutoSaveLedger(); });
  if (has('#ledger-rows')) $('#ledger-rows').addEventListener('change', (event) => { if (!event.target.classList.contains('ledger-security')) return; const security = entryForId(event.target.value)?.security; if (security) event.target.closest('tr').querySelector('.ledger-currency').value = security.currency; });
  if (has('#ledger-rows')) s5WireLedgerPersistence();
  $$('.currency-button').forEach((button) => button.addEventListener('click', () => { state.currencyMode = button.dataset.currency; if (state.artifact) renderResult(); }));
  if (has('#warnings-toggle')) $('#warnings-toggle').addEventListener('click', () => { state.warningsOpen = !state.warningsOpen; renderQuality(state.artifact?.result?.data_quality || {}); });
  if (has('#return-to-demo')) $('#return-to-demo').addEventListener('click', async () => { const entry = entryForTicker('QQQ'); if (!entry) return; selectSecurity(entry.security.security_id); $('#initial-amount').value = '10000'; $('#start-date').value = '2024-01-02'; $('#end-date').value = '2025-01-02'; $('#scenario-select').value = 'investor'; syncPreset('investor'); $('#analysis-form').requestSubmit(); });
  if (has('#download-result')) $('#download-result').addEventListener('click', () => { if (!state.artifact) return; const blob = new Blob([JSON.stringify(state.artifact, null, 2)], { type: 'application/json' }); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `sg-invest-${state.artifact.result?.security?.ticker || 'analysis'}.json`; link.click(); URL.revokeObjectURL(link.href); });
  if (has('#copy-link')) $('#copy-link').addEventListener('click', copyAnalysisLink);
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
  $('#analysis-form').requestSubmit();
}

async function init() {
  // S6.2: the catalog, status and first-paint series resolve from published
  // static artifacts; the /api probes are adapter-mode only. The committed
  // demo analysis replay stays as the first paint but is explicitly labelled
  // ('Demo replay · published artifact', see S6.1) and is never substituted
  // for a failed request.
  const staticCatalog = await loadJson(CATALOG_ARTIFACT, { securities: fallbackCatalog });
  if (API_BASE) {
    const apiCatalog = await apiGet('/catalog').catch(() => null);
    state.catalog = apiCatalog?.securities || staticCatalog.securities || fallbackCatalog;
  } else {
    state.catalog = staticCatalog.securities || fallbackCatalog;
  }
  state.artifact = await loadJson(DEMO_ARTIFACT, null);
  state.artifactSource = 'demo';
  renderSecurityOptions(); renderUniverseOptions(); renderDimensionOptions(); renderCatalog(); syncPreset('investor');
  // Wire events BEFORE any further awaits: users can click the moment the
  // forms render, and a submit during the data-status/build-info fetches used
  // to be silently lost (listeners did not exist yet).
  s5RestoreLedger();
  wireEvents();
  setComputeMode(API_BASE ? 'adapter' : 'local');
  if (has('#data-date')) {
    const status = API_BASE ? await apiGet('/status').catch(() => loadJson('data/data-status.json', null)) : await loadJson('data/data-status.json', null);
    $('#data-date').textContent = status?.backfill?.as_of ? formatDate(status.backfill.as_of) : '30 Aug 2026';
  }
  renderBuildInfo(await loadBuildInfo());
  if (state.artifact) {
    const securityId = state.artifact.result?.security?.security_id;
    const startDate = state.artifact.result?.period?.start_date;
    const endDate = state.artifact.result?.period?.end_date;
    state.series = API_BASE
      ? await apiGet('/series', { security_id: securityId, start_date: startDate, end_date: endDate }).catch(() => loadJson(`data/series/${securityId}/${startDate}_${endDate}.json`, null))
      : await loadJson(`data/series/${securityId}/${startDate}_${endDate}.json`, null);
    showResult();
    setComputeMode('demo');
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

function s5CurrencyForId(securityId) {
  return entryForId(securityId)?.security.currency || s5InputsCache.get(securityId)?.inputs.security.currency || 'USD';
}

function s5SecurityLabel(securityId, entry) {
  return entry?.ticker || entryForId(securityId)?.security.ticker || securityId;
}

async function s5SecurityInputs(securityId, entry, startDate, endDate) {
  const cached = s5InputsCache.get(securityId);
  if (cached && cached.startDate <= startDate && endDate <= cached.endDate) return cached.inputs;
  const inputs = await s5PackLoader.loadSecurityInputs(entry, startDate, endDate);
  s5InputsCache.set(securityId, { startDate, endDate, inputs });
  return inputs;
}

function s5ShowPortfolioUnavailable(message) {
  if (has('#portfolio-results')) {
    $('#portfolio-results').innerHTML = `<div class="result-empty compact-empty"><p class="eyebrow">LEDGER VIEW</p><h3>Unavailable for this ledger.</h3><p>${escapeHtml(message)}</p></div>`;
  }
}

async function s5LocalPortfolio(asOf, rows) {
  const holdingIds = [...new Set(rows.map((row) => row.security_id).filter(Boolean))];
  const firstDateFor = (securityId) => rows.filter((row) => row.security_id === securityId).map((row) => row.transaction_date).sort()[0];
  const warnings = [];
  for (const securityId of holdingIds) {
    const entry = await s5PackLoader.findSecurity({ securityId });
    if (!entry) {
      return { unavailable: `${s5SecurityLabel(securityId)} (${securityId}) is not in the published data packs, so the portfolio cannot be reconstructed as of ${asOf}.` };
    }
    const support = s5PackLoader.supportFor(entry, firstDateFor(securityId), asOf);
    if (support.status === 'unavailable') {
      return { unavailable: `${s5SecurityLabel(securityId)} cannot be reconstructed as of ${asOf}: ${support.reason}.` };
    }
    if (support.status === 'incomplete') warnings.push(`${s5SecurityLabel(securityId)}: incomplete pack support (${support.reason}).`);
  }

  const securities = {};
  const prices = [];
  const fxRates = [];
  for (const securityId of holdingIds) {
    const entry = await s5PackLoader.findSecurity({ securityId });
    const inputs = await s5SecurityInputs(securityId, entry, firstDateFor(securityId), asOf);
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
  const request = s5EngineClient.portfolio({ as_of: asOf, transactions, securities, prices, fx_rates: fxRates });
  s5EngineClient.supersede('portfolio', request.id);
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
      try { s5RenderLedgerRows(await ledgerStore.importJson(await file.text())); }
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
// Error with a user-facing message for every genuine failure.
async function s4DcaViaPacks(request) {
  const entry = await packs.findSecurity({ securityId: request.security_id });
  if (!entry) throw new Error(`${request.security_id} has no published data pack, so the local engine cannot serve this request.`);
  const support = packs.supportFor(entry, request.start_date, request.end_date);
  if (support.status === 'unavailable') {
    throw new Error(`${entry.ticker} cannot be replayed locally for ${request.start_date} → ${request.end_date}: ${support.reason || 'no data pack coverage for this range'}. Choose a range inside the covered years.`);
  }
  s4SetDcaProgress(`Loading ${entry.ticker} data packs for ${String(request.start_date).slice(0, 4)}–${String(request.end_date).slice(0, 4)}…`);
  const inputs = await packs.loadSecurityInputs(entry, request.start_date, request.end_date);
  s4State.support = inputs.support;
  s4State.packWarnings = inputs.warnings || [];
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
      if (envelope.stage === 'received') s4SetDcaProgress('DCA request received — queued in the engine worker…');
      else if (envelope.stage === 'computing') s4SetDcaProgress('Computing contributions, dividends and XIRR…');
    },
  });
  s4State.requestId = id;
  engineClient.supersede('dca', id);
  try {
    const envelope = await promise;
    if (id !== s4State.requestId) return null;
    return envelope;
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
  const manifest = await packs.loadManifest();
  const wanted = String(ticker).trim().toUpperCase();
  const matches = (manifest.securities || []).filter((candidate) => String(candidate.ticker).toUpperCase() === wanted);
  if (matches.length === 1) return matches[0];
  if (matches.length === 0) {
    throw new Error(`${ticker} is not in the published data packs, so the requested range ${startDate} → ${endDate} cannot be computed locally.`);
  }
  throw new Error(`Expected one security for ticker ${ticker}; matches: ${matches.map((match) => match.security_id).join(', ')}.`);
}

// Static-mode analysis (scope 'analyze'): resolve the security's data packs,
// gate on manifest support, compute through the engine worker, and derive the
// daily series from the same loaded packs. Throws Error with a user-facing
// message (naming the security and requested range) for every genuine failure.
async function s6AnalysisViaPacks({ securityId = null, ticker = null, label = null, initial_sgd, start_date, end_date, dividends, withholding, reinvest }, onProgress = () => {}) {
  const entry = securityId ? await packs.findSecurity({ securityId }) : await s6ResolveTicker(ticker, start_date, end_date);
  if (!entry) throw new Error(`${label || securityId || ticker} is not in the published data packs, so ${start_date} → ${end_date} cannot be computed locally.`);
  const support = packs.supportFor(entry, start_date, end_date);
  if (support.status === 'unavailable') {
    throw new Error(`${entry.ticker} cannot be computed locally for ${start_date} → ${end_date}: ${support.reason || 'no data pack coverage for this range'}. Choose a range inside the covered years.`);
  }
  onProgress(`Loading ${entry.ticker} data packs for ${String(start_date).slice(0, 4)}–${String(end_date).slice(0, 4)}…`);
  const inputs = await packs.loadSecurityInputs(entry, start_date, end_date);
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
  const { id, promise } = engineClient.analyze(payload);
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
  const manifest = await packs.loadManifest();
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
  return { id, envelope, series: s6SeriesFromInputs(inputs, { start_date, end_date }), support, packWarnings: inputs.warnings || [] };
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
