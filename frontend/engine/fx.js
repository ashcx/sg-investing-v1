import { bisectLeft, bisectRight, daysBetween } from './calendar.js';
import { MAX_FX_STALENESS_DAYS, ONE, dec } from './money.js';
import { AnalysisDataError, SGD } from './models.js';

function sortedRowsForCurrency(fxRates, currency) {
  return fxRates
    .filter((row) => row.base_currency === currency)
    .map((row) => ({ rate_date: row.rate_date, rate_to_sgd: dec(row.rate_to_sgd) }))
    .sort((a, b) => (a.rate_date < b.rate_date ? -1 : a.rate_date > b.rate_date ? 1 : 0));
}

export function rateForDate(currency, requested, fxRates, { rule = 'previous_trading_day' } = {}) {
  if (currency === SGD) return ONE;
  const rows = sortedRowsForCurrency(fxRates, currency);
  if (!rows.length) throw new AnalysisDataError(`No ${currency}/SGD FX history supplied.`);
  const dates = rows.map((row) => row.rate_date);
  let index;
  if (rule === 'next_trading_day') {
    index = bisectLeft(dates, requested);
    if (index === rows.length) {
      throw new AnalysisDataError(`No ${currency}/SGD rate exists on or after ${requested}.`);
    }
  } else if (rule === 'previous_trading_day') {
    index = bisectRight(dates, requested) - 1;
    if (index < 0) {
      throw new AnalysisDataError(`No ${currency}/SGD rate exists on or before ${requested}.`);
    }
  } else {
    throw new AnalysisDataError(`Unsupported date rule: ${rule}.`);
  }
  return rows[index].rate_to_sgd;
}

export function rateForDateWithStaleness(currency, requested, fxRates, { rule = 'previous_trading_day' } = {}) {
  if (currency === SGD) return { rate: ONE, lag: 0 };
  const rows = sortedRowsForCurrency(fxRates, currency);
  if (!rows.length) throw new AnalysisDataError(`No ${currency}/SGD FX history supplied.`);
  const dates = rows.map((row) => row.rate_date);
  let index;
  if (rule === 'next_trading_day') {
    index = bisectLeft(dates, requested);
    if (index === rows.length) {
      throw new AnalysisDataError(`No ${currency}/SGD rate exists on or after ${requested}.`);
    }
  } else if (rule === 'previous_trading_day') {
    index = bisectRight(dates, requested) - 1;
    if (index < 0) {
      throw new AnalysisDataError(`No ${currency}/SGD rate exists on or before ${requested}.`);
    }
  } else {
    throw new AnalysisDataError(`Unsupported date rule: ${rule}.`);
  }
  return { rate: rows[index].rate_to_sgd, lag: Math.abs(daysBetween(rows[index].rate_date, requested)) };
}

export function warnIfFxIsStale(warnings, { currency, requested, lag }) {
  if (lag > MAX_FX_STALENESS_DAYS) {
    warnings.push(`${currency}/SGD FX rate for ${requested} is ${lag} days stale.`);
  }
}
