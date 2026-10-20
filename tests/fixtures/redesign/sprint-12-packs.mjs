import { readFileSync } from 'node:fs';

export const fixture = JSON.parse(readFileSync(new URL('./sprint-12.json', import.meta.url)));
export const snapshot = 's12-synthetic-2024';
export function manifest(remote = false) {
  return { schema_version: 1, manifest_version: 1, data_snapshot_id: snapshot,
    generated_at: '2024-05-01T00:00:00Z', catalog_version: 's12-fixed',
    source: 'Independent synthetic comparison fixtures; not market data',
    fx: { coverage: { USD: { first_date: '2024-01-02', last_date: '2024-05-01' } } },
    securities: fixture.securities.filter(item => (item.security.ticker === 'REMOTE') === remote).map(item => {
      const start = item.prices[0].trading_date; const end = item.prices.at(-1).trading_date;
      return { security_id: item.security.security_id, ticker: item.security.ticker,
        native_currency: item.security.currency, first_year: 2024, last_year: 2024,
        first_date: start, last_date: end, status: 'fully_supported',
        years: { 2024: { first_date: start, last_date: end, status: 'fully_supported' } } };
    }) };
}
export function pack(item) {
  return { schema_version: 1, manifest_version: 1, data_snapshot_id: snapshot,
    security: item.security,
    prices: { dates: item.prices.map(row => row.trading_date), close: item.prices.map(row => row.close) },
    dividends: item.dividends, corporate_actions: [],
    fx: { base_currency: item.security.currency, dates: item.fx_rates.map(row => row.rate_date), rates: item.fx_rates.map(row => row.rate_to_sgd) },
    coverage: { first_date: item.prices[0].trading_date, last_date: item.prices.at(-1).trading_date,
      native_currency: item.security.currency },
    warnings: ['Synthetic Sprint 12 fixture; not market data.'] };
}
