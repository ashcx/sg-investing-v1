const DEMO_ARTIFACT = 'data/analyses/qqq-2024.json';
const CATALOG_ARTIFACT = 'data/catalog.json';
const API_BASE = (document.querySelector('meta[name="sg-invest-api-base"]')?.content || '').replace(/\/$/, '');

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
  series: null,
  dcaArtifact: null,
  compareArtifact: null,
  portfolioArtifact: null,
  selectedSecurityId: null,
  currencyMode: 'sgd',
  warningsOpen: true,
  catalogLimit: 12,
  apiAvailable: false,
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
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, value);
  });
  const path = `${API_BASE}/api${endpoint}${query.toString() ? `?${query}` : ''}`;
  const response = await fetch(API_BASE ? path : `api${endpoint}${query.toString() ? `?${query}` : ''}`, { cache: 'no-store' });
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.error) throw new Error(body.error || `Request failed (${response.status})`);
  state.apiAvailable = true;
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
  $('#method-version').textContent = state.artifact.methodology_version || result.methodology.methodology_version || '1.0';
  renderQuality(result.data_quality);
  $$('.currency-button').forEach((button) => {
    button.classList.toggle('hidden', button.dataset.currency === 'native' && security.currency === 'SGD');
    const active = button.dataset.currency === state.currencyMode;
    button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active)); button.textContent = button.dataset.currency === 'native' ? security.currency : 'SGD';
  });
  renderSeries(state.series?.result || state.series);
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
  button.innerHTML = busy ? 'Resolving backend result…' : button.dataset.originalLabel;
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
  const key = requestKey('analysis', { ...request, methodology_version: '1.0', data_snapshot_id: 'local-canonical-parquet' });
  const button = event.currentTarget.querySelector('button[type="submit"]'); setBusy(button, true);
  try {
    state.artifact = await apiGet('/analyze', { ...request, request_key: key });
    state.series = await apiGet('/series', { security_id: entry.security.security_id, start_date: $('#start-date').value, end_date: $('#end-date').value }).catch(() => null);
    showResult();
  } catch (apiError) {
    const isDemo = entry.security.ticker === 'QQQ' && amount === 10000 && $('#start-date').value === '2024-01-02' && $('#end-date').value === '2025-01-02' && scenario.dividends && scenario.withholding && scenario.reinvest;
    if (isDemo && !state.apiAvailable && state.artifact) showResult(); else showUnavailable(apiError.message);
    error.textContent = state.apiAvailable ? apiError.message : 'The local result service is unavailable. Try the published QQQ replay.';
  } finally { setBusy(button, false); }
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
  const scenario = PRESETS[$('#compare-scenario').value] || PRESETS.investor; const request = { tickers: tickers.join(','), initial_sgd: $('#compare-amount').value, start_date: $('#compare-start').value, end_date: $('#compare-end').value, ...scenario }; const key = requestKey('compare', { ...request, methodology_version: '1.0', data_snapshot_id: 'local-canonical-parquet' }); const button = event.currentTarget.querySelector('button[type="submit"]'); setBusy(button, true);
  try { renderCompare(await apiGet('/compare', { ...request, request_key: key })); }
  catch (apiError) { if (!state.apiAvailable && state.compareArtifact) renderCompare(state.compareArtifact); else error.textContent = apiError.message; }
  finally { setBusy(button, false); }
}

function renderDca(payload) {
  state.dcaArtifact = payload;
  const result = payload.result || payload; const security = result.security;
  if (security.currency === 'SGD') state.currencyMode = 'sgd';
  const native = state.currencyMode === 'native'; const currency = native ? security.currency : 'SGD';
  const contributed = native ? result.total_contributed_foreign_currency : result.total_contributed_sgd;
  const finalValue = native ? result.final_value_foreign_currency : result.final_value_sgd;
  const gainLoss = native ? result.gain_loss_foreign_currency : result.gain_loss_sgd;
  const xirr = native ? result.xirr_foreign_currency : result.xirr;
  $('#dca-results').innerHTML = `<div class="analysis-output"><div class="dca-output-head"><div class="output-kicker">${escapeHtml(security.ticker)} · ${escapeHtml(titleCase(payload.request?.frequency || 'monthly'))}</div><div class="mini-switch"><button type="button" data-dca-currency="native" class="${native ? 'active' : ''} ${security.currency === 'SGD' ? 'hidden' : ''}">${escapeHtml(security.currency)}</button><button type="button" data-dca-currency="sgd" class="${native ? '' : 'active'}">SGD</button></div></div><h3>${formatMoney(finalValue, currency)}</h3><p>Ending value after ${escapeHtml(String(result.contribution_dates.length))} contributions.</p><div class="output-grid"><span>Contributed<strong>${formatMoney(contributed, currency)}</strong></span><span>Gain / loss<strong>${formatMoney(gainLoss, currency)}</strong></span><span>XIRR · money-weighted<strong>${formatPercent(xirr)}</strong></span><span>Shares<strong>${Number(result.shares).toFixed(5)}</strong></span></div><details class="contribution-dates"><summary>Contribution dates (${result.contribution_dates.length})</summary><p>${result.contribution_dates.map((date) => `<time datetime="${escapeHtml(date)}">${escapeHtml(formatDate(date))}</time>`).join(' · ')}</p></details><p class="detail-note">${escapeHtml((result.data_quality.warnings || []).join(' ') || 'Backend replay completed with no warnings.')}</p></div>`;
  $$('[data-dca-currency]').forEach((button) => button.addEventListener('click', () => { state.currencyMode = button.dataset.dcaCurrency; if (state.artifact) renderResult(); if (state.dcaArtifact) renderDca(state.dcaArtifact); }));
}

async function submitDca(event) {
  event.preventDefault(); const error = $('#dca-error'); error.textContent = '';
  if ($('#dca-end').value < $('#dca-start').value) { error.textContent = 'End date must be on or after start date.'; return; }
  const contribution = Number($('#dca-contribution').value); if (!(contribution > 0)) { error.textContent = 'Enter a contribution greater than S$0.'; return; }
  const scenario = scenarioValues('dca'); const request = { security_id: $('#dca-security').value, contribution_sgd: $('#dca-contribution').value, frequency: $('#dca-frequency').value, start_date: $('#dca-start').value, end_date: $('#dca-end').value, ...scenario }; const key = requestKey('dca', { ...request, methodology_version: '1.0', data_snapshot_id: 'local-canonical-parquet' }); const button = event.currentTarget.querySelector('button[type="submit"]'); setBusy(button, true);
  try { renderDca(await apiGet('/dca', { ...request, request_key: key })); }
  catch (apiError) {
    const demo = entryForId($('#dca-security').value)?.security?.ticker === 'QQQ' && $('#dca-contribution').value === '500' && $('#dca-frequency').value === 'monthly' && $('#dca-start').value === '2024-01-02' && $('#dca-end').value === '2025-01-02' && scenario.dividends && scenario.withholding && scenario.reinvest;
    if (!state.apiAvailable && demo && state.dcaArtifact) renderDca(state.dcaArtifact); else error.textContent = apiError.message;
  }
  finally { setBusy(button, false); }
}

function ledgerRowTemplate(values = {}) {
  const selectedId = values.securityId || state.selectedSecurityId || '';
  const options = securityEntries().map(({ security }) => `<option value="${escapeHtml(security.security_id)}" ${security.security_id === selectedId ? 'selected' : ''}>${escapeHtml(security.ticker)} · ${escapeHtml(security.exchange)}</option>`).join('');
  const currencies = [...new Set(securityEntries().map(({ security }) => security.currency).filter(Boolean))].sort();
  const currencyOptions = currencies.map((currency) => `<option ${currency === (values.currency || entryForId(selectedId)?.security.currency || 'USD') ? 'selected' : ''}>${escapeHtml(currency)}</option>`).join('');
  return `<tr><td><select class="ledger-type"><option>BUY</option><option>SELL</option><option>DIVIDEND</option><option>CASH_DEPOSIT</option><option>CASH_WITHDRAWAL</option></select></td><td><select class="ledger-security"><option value="">Cash only</option>${options}</select></td><td><input class="ledger-date" type="date" value="${escapeHtml(values.date || '2024-01-02')}" /></td><td><input class="ledger-quantity" type="number" min="0" step="0.000001" value="${escapeHtml(values.quantity || '1')}" /></td><td><input class="ledger-cash" type="number" min="0" step="0.01" value="${escapeHtml(values.cash || '1000')}" /></td><td><select class="ledger-currency">${currencyOptions}</select></td></tr>`;
}

function addLedgerRow(values = {}) { if (has('#ledger-rows')) $('#ledger-rows').insertAdjacentHTML('beforeend', ledgerRowTemplate(values)); }

function renderPortfolio(payload) {
  const result = payload.result || payload;
  const rows = result.holdings.map((holding) => { const ccy = entryForId(holding.security_id)?.security.currency || 'USD'; return `<tr><th scope="row">${escapeHtml(holding.ticker)}</th><td>${Number(holding.quantity).toFixed(5)}</td><td>${formatMoney(holding.weighted_average_cost, ccy)}</td><td>${formatMoney(holding.market_value_native, ccy)}</td><td>${formatMoney(holding.market_value_sgd, 'SGD')}</td><td>${formatMoney(holding.realized_pl_native, ccy)}</td><td>${formatMoney(holding.unrealized_pl_native, ccy)}</td></tr>`; }).join('');
  $('#portfolio-results').innerHTML = `<div class="analysis-output"><div class="output-kicker">AS OF ${escapeHtml(formatDate(result.as_of))}</div><h3>${formatMoney(result.total_market_value_sgd, 'SGD')}</h3><p>Mark-to-market portfolio value across ${result.holdings.length} holding${result.holdings.length === 1 ? '' : 's'}.</p><div class="holding-table-wrap"><table class="holding-table"><caption class="sr-only">Portfolio holdings as of ${escapeHtml(formatDate(result.as_of))}</caption><thead><tr><th scope="col">Ticker</th><th scope="col">Quantity</th><th scope="col">WAC</th><th scope="col">Native value</th><th scope="col">SGD value</th><th scope="col">Realised P/L</th><th scope="col">Unrealised P/L</th></tr></thead><tbody>${rows || '<tr><td colspan="7">No open holdings on this date.</td></tr>'}</tbody></table></div><p class="detail-note">Cash: ${Object.entries(result.cash_by_currency || {}).map(([currency, amount]) => `${formatMoney(amount, currency)}`).join(' · ') || 'none'} · Realised P/L: ${Object.entries(result.realized_pl_native || {}).map(([currency, amount]) => `${formatMoney(amount, currency)}`).join(' · ') || 'none'}.</p><p class="detail-note">Weighted-average cost is a reporting convention, not a Singapore capital-gains tax calculation.</p></div>`;
}

async function submitPortfolio(event) {
  event.preventDefault(); const error = $('#portfolio-error'); error.textContent = '';
  const transactions = $$('#ledger-rows tr').map((row) => ({ transaction_date: row.querySelector('.ledger-date').value, security_id: row.querySelector('.ledger-security').value || null, transaction_type: row.querySelector('.ledger-type').value, quantity: row.querySelector('.ledger-quantity').value, cash_amount: row.querySelector('.ledger-cash').value, currency: row.querySelector('.ledger-currency').value, fees: '0' }));
  if (!transactions.length) { error.textContent = 'Add at least one ledger transaction.'; return; }
  const button = event.currentTarget.querySelector('button[type="submit"]'); setBusy(button, true);
  try {
    const portfolioPath = API_BASE ? `${API_BASE}/api/portfolio` : 'api/portfolio';
    const payload = await fetch(portfolioPath, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ as_of: $('#portfolio-as-of').value, transactions }) }).then(async (response) => { const body = await response.json(); if (!response.ok || body.error) throw new Error(body.error || 'Portfolio request failed'); return body; });
    renderPortfolio(payload);
  } catch (apiError) {
    const demo = !state.apiAvailable && state.portfolioArtifact && $('#portfolio-as-of').value === '2025-01-02' && transactions.length === 1 && transactions[0].transaction_type === 'BUY' && transactions[0].quantity === '10' && transactions[0].cash_amount === '4000';
    if (demo) renderPortfolio(state.portfolioArtifact); else error.textContent = apiError.message;
  }
  finally { setBusy(button, false); }
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
  if (has('#add-ledger-row')) $('#add-ledger-row').addEventListener('click', () => addLedgerRow());
  if (has('#ledger-rows')) $('#ledger-rows').addEventListener('change', (event) => { if (!event.target.classList.contains('ledger-security')) return; const security = entryForId(event.target.value)?.security; if (security) event.target.closest('tr').querySelector('.ledger-currency').value = security.currency; });
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
  const apiCatalog = await apiGet('/catalog').catch(() => null);
  const staticCatalog = await loadJson(CATALOG_ARTIFACT, { securities: fallbackCatalog });
  state.catalog = apiCatalog?.securities || staticCatalog.securities || fallbackCatalog;
  state.artifact = await loadJson(DEMO_ARTIFACT, null);
  state.dcaArtifact = await loadJson('data/dca/qqq-2024-monthly.json', null);
  state.compareArtifact = await loadJson('data/comparisons/qqq-smh-soxx-2024.json', null);
  state.portfolioArtifact = await loadJson('data/portfolios/demo-qqq.json', null);
  renderSecurityOptions(); renderUniverseOptions(); renderDimensionOptions(); renderCatalog(); syncPreset('investor');
  if (has('#data-date')) {
    const status = await apiGet('/status').catch(() => loadJson('data/data-status.json', null));
    $('#data-date').textContent = status?.backfill?.as_of ? formatDate(status.backfill.as_of) : '30 Aug 2026';
  }
  addLedgerRow({ quantity: '10', cash: '4000' });
  wireEvents();
  if (state.artifact) {
    const securityId = state.artifact.result?.security?.security_id;
    const startDate = state.artifact.result?.period?.start_date;
    const endDate = state.artifact.result?.period?.end_date;
    state.series = await apiGet('/series', { security_id: securityId, start_date: startDate, end_date: endDate }).catch(() => loadJson(`data/series/${securityId}/${startDate}_${endDate}.json`, null));
    showResult();
  }
  applyAnalysisUrl();
}

init().catch((error) => { console.error(error); if (has('#form-error')) $('#form-error').textContent = 'The frontend could not initialise. Refresh to retry.'; });
