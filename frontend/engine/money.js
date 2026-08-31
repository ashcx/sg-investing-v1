import Decimal from '../vendor/decimal.mjs';

Decimal.set({ precision: 28, rounding: Decimal.ROUND_HALF_EVEN });

export { Decimal };

export const ZERO = new Decimal(0);
export const ONE = new Decimal(1);
export const DAYS_PER_YEAR = new Decimal('365.2425');
export const MAX_FX_STALENESS_DAYS = 7;

export function dec(value) {
  if (value instanceof Decimal) return value;
  if (typeof value === 'number') return new Decimal(String(value));
  if (value === null || value === undefined) return new Decimal(0);
  return new Decimal(value);
}

export function sumDecimals(values) {
  let total = ZERO;
  for (const value of values) total = total.plus(dec(value));
  return total;
}

export function decString(value) {
  return dec(value).toString();
}
