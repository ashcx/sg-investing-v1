// Sprint 12 (Fair comparisons): pure common-window math for multi-security
// comparison.
//
// Published boundaries are a preview only. Actual equal periods must be
// verified from engine results (exchange calendars and gaps can differ).
//
//   securityWindow()  published usable window for one security (FX-aware)
//   commonWindow()    the window every selected security genuinely shares
//   resolveWindow()   the requested window intersected with that common window
//
// Dates are ISO `YYYY-MM-DD` strings compared lexicographically, which is
// exact for that format. No DOM, no engine calls, no I/O.

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function daysInMonth(year, month) {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

// Format *and* calendar validity: `2024-02-30` must never widen or shorten a
// comparison window.
export function isIsoDate(value) {
  if (typeof value !== 'string' || !ISO_DATE.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  if (month < 1 || month > 12) return false;
  return day >= 1 && day <= daysInMonth(year, month);
}

function laterOf(a, b) {
  if (!isIsoDate(a)) return isIsoDate(b) ? b : null;
  if (!isIsoDate(b)) return a;
  return a >= b ? a : b;
}

function earlierOf(a, b) {
  if (!isIsoDate(a)) return isIsoDate(b) ? b : null;
  if (!isIsoDate(b)) return a;
  return a <= b ? a : b;
}

// Manifest rows may publish one flat window (`first_date`/`last_date`) or
// per-year windows (`years: { 2024: { first_date, last_date } }`). Accept both
// so a manifest shape change cannot silently widen a window to "all history".
function publishedBounds(entry = {}) {
  const years = Object.values(entry.years || {}).filter((year) => year && typeof year === 'object' && year.status !== 'unavailable');
  const starts = [entry.first_date, ...years.map((year) => year.first_date)].filter(isIsoDate);
  const ends = [entry.last_date, ...years.map((year) => year.last_date)].filter(isIsoDate);
  return {
    start: starts.length ? starts.sort().at(0) : null,
    end: ends.length ? ends.sort().at(-1) : null,
  };
}

/**
 * Published usable window for one selected security.
 *
 * @param {object} input
 * @param {string} input.securityId
 * @param {string} [input.currency] security trading currency
 * @param {object|null} [input.entry] published coverage row for the security
 * @param {object|null} [input.fx] published `{first_date,last_date}` for currency/SGD
 * @returns {{securityId:string,currency:string|null,state:'ready'|'unavailable'|'unknown',
 *   start:string|null,end:string|null,fxLimited:boolean,reason:string|null}}
 */
export function securityWindow({ securityId, currency = null, entry = null, fx = null } = {}) {
  const code = currency ? String(currency).toUpperCase() : null;
  const result = {
    securityId: securityId || null,
    currency: code,
    state: 'unknown',
    start: null,
    end: null,
    fxLimited: false,
    reason: null,
  };
  if (!entry) {
    result.reason = 'Published coverage is unknown. Calculate to check the available data.';
    return result;
  }
  if (entry.status === 'unavailable') {
    result.state = 'unavailable';
    result.reason = 'No usable price history is published for this security.';
    return result;
  }
  const published = publishedBounds(entry);
  result.start = published.start;
  result.end = published.end;
  if (!result.start || !result.end) {
    result.reason = 'Published trading dates are unknown. Calculate to check the available data.';
    return result;
  }
  if (result.start > result.end) {
    result.state = 'unavailable';
    result.reason = 'Published history has an invalid date range.';
    return result;
  }
  if (!code) {
    result.reason = 'Trading currency is unknown; SGD conversion cannot be previewed.';
    return result;
  }
  if (code && code !== 'SGD') {
    if (!fx || !isIsoDate(fx.first_date) || !isIsoDate(fx.last_date)) {
      result.state = 'unavailable';
      result.reason = `No ${code}/SGD exchange-rate history is published, so this security cannot be converted to SGD.`;
      return result;
    }
    const start = laterOf(result.start, fx.first_date);
    const end = earlierOf(result.end, fx.last_date);
    result.fxLimited = start !== result.start || end !== result.end;
    result.start = start;
    result.end = end;
    if (!result.start || !result.end || result.start > result.end) {
      result.state = 'unavailable';
      result.reason = `This security's price history does not overlap the published ${code}/SGD exchange-rate history.`;
      return result;
    }
  }
  result.state = 'ready';
  return result;
}

/**
 * The window every selected security genuinely shares.
 *
 * `ok` is true only when every supplied window is usable and the intersection
 * is non-empty. A partially usable selection reports `ok: false` and lists the
 * excluded securities, so the caller can decide to compare the remainder
 * openly instead of implying the whole selection is comparable.
 */
export function commonWindow(windows = []) {
  const list = Array.isArray(windows) ? windows.filter(Boolean) : [];
  const usable = list.filter((item) => item.state === 'ready' && isIsoDate(item.start) && isIsoDate(item.end) && item.start <= item.end);
  const unusable = list.filter((item) => !usable.includes(item));
  if (!usable.length) {
    return { start: null, end: null, ok: false, usable, unusable, limitingStart: [], limitingEnd: [], reason: 'None of the selected securities has a usable published window.' };
  }
  const start = usable.map((item) => item.start).sort().at(-1);
  const end = usable.map((item) => item.end).sort().at(0);
  if (start > end) {
    return { start: null, end: null, ok: false, usable, unusable, limitingStart: [], limitingEnd: [], reason: 'The selected securities have no overlapping published trading history.' };
  }
  return {
    start,
    end,
    ok: unusable.length === 0,
    usable,
    unusable,
    limitingStart: usable.filter((item) => item.start === start),
    limitingEnd: usable.filter((item) => item.end === end),
    reason: unusable.length ? 'Some selected securities have unknown or unavailable coverage. Remove them to use a shared-window preview.' : null,
  };
}

/**
 * The requested window intersected with the shared window.
 *
 * This is a suggested window, applied only by an explicit user action.
 * It does not resolve trading days or replace engine date validation.
 */
export function resolveWindow(requested = {}, common = {}) {
  const requestedStart = requested.start || requested.start_date || null;
  const requestedEnd = requested.end || requested.end_date || null;
  if (!isIsoDate(requestedStart) || !isIsoDate(requestedEnd)) {
    return { start: null, end: null, ok: false, truncated: false, reason: 'Choose both a start and an end date.' };
  }
  if (requestedStart > requestedEnd) {
    return { start: null, end: null, ok: false, truncated: false, reason: 'End date must be on or after start date.' };
  }
  if (!common || !isIsoDate(common.start) || !isIsoDate(common.end)) {
    return { start: null, end: null, ok: false, truncated: false, reason: common?.reason || 'The selected securities have no shared published window.' };
  }
  const start = laterOf(requestedStart, common.start);
  const end = earlierOf(requestedEnd, common.end);
  if (start > end) {
    return {
      start: null,
      end: null,
      ok: false,
      truncated: true,
      reason: `Your requested dates fall outside the window every selected security shares (${common.start} → ${common.end}).`,
    };
  }
  return { start, end, ok: true, truncated: start !== requestedStart || end !== requestedEnd, reason: null };
}

export function windowsEqual(a = {}, b = {}) {
  return Boolean(a && b) && isIsoDate(a.start) && isIsoDate(a.end)
    && a.start <= a.end && a.start === b.start && a.end === b.end;
}

// Presentation boundary: preserve the source envelope and never mistake it
// for its inner result. Reject mismatched identities and missing financial
// fields rather than rendering a successful card with blank values.
export function comparisonRow(row, envelope) {
  const result = envelope?.result || envelope;
  const period = result?.period;
  const validNumber = (value) => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
  if (!result?.security || result.security.security_id !== row.securityId
      || !isIsoDate(period?.start_date) || !isIsoDate(period?.end_date)
      || period.start_date > period.end_date
      || !validNumber(result.investment?.final_value_sgd)
      || !validNumber(result.returns?.total_return)
      || !validNumber(result.returns?.total_return_foreign_currency)) {
    return { ...row, state: 'failed', reason: 'The calculation returned an incomplete or mismatched result. No comparison value is shown.', result: null, envelope: null };
  }
  return { ...row, state: 'ready', reason: '', result, envelope,
    snapshotId: envelope?.data_snapshot_id || null,
    methodologyVersion: envelope?.methodology_version || result.methodology?.methodology_version || null };
}

export function comparisonSummary(rows = []) {
  const ready = rows.filter((row) => row.state === 'ready' && row.result);
  const periods = ready.map((row) => ({ start: row.result.period?.start_date, end: row.result.period?.end_date }));
  const equalReadyPeriods = periods.length >= 2 && periods.every((period) => windowsEqual(periods[0], period));
  const complete = rows.length >= 2 && ready.length === rows.length;
  const sameSource = ready.length >= 2 && ready.every((row) => row.snapshotId && row.methodologyVersion
    && row.snapshotId === ready[0].snapshotId && row.methodologyVersion === ready[0].methodologyVersion);
  return { ready, complete, equalReadyPeriods, equal: complete && equalReadyPeriods, sameSource };
}
