import { bisectLeft, bisectRight } from './calendar.js';
import { AnalysisDataError } from './models.js';

export function sortedPrices(prices, security) {
  const rows = prices
    .filter((row) => row.security_id === security.security_id)
    .sort((a, b) => (a.trading_date < b.trading_date ? -1 : a.trading_date > b.trading_date ? 1 : 0));
  if (!rows.length) throw new AnalysisDataError(`No price history supplied for ${security.ticker}.`);
  if (rows.some((row) => row.currency !== security.currency)) {
    throw new AnalysisDataError('Price currency does not match the security master.');
  }
  const seen = new Set(rows.map((row) => row.trading_date));
  if (seen.size !== rows.length) {
    throw new AnalysisDataError('Price history contains duplicate trading dates.');
  }
  return rows;
}

export function resolvePrice(prices, requested, { rule }) {
  const dates = prices.map((row) => row.trading_date);
  if (rule === 'next_trading_day') {
    const index = bisectLeft(dates, requested);
    if (index === prices.length) {
      throw new AnalysisDataError(`No price exists on or after ${requested}.`);
    }
    return prices[index];
  }
  if (rule === 'previous_trading_day') {
    const index = bisectRight(dates, requested) - 1;
    if (index < 0) {
      throw new AnalysisDataError(`No price exists on or before ${requested}.`);
    }
    return prices[index];
  }
  throw new AnalysisDataError(`Unsupported date rule: ${rule}.`);
}
