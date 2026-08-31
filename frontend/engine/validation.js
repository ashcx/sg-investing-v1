import { DIVIDEND_TYPES, DataQualityStatus, DividendType } from './models.js';

export function dividendEventKey(row) {
  if (row.source_id) return `source|${row.source}|${row.source_id}`;
  return dividendEconomicKey(row);
}

export function dividendEconomicKey(row) {
  const dividendType = row.dividend_type === DividendType.LEGACY_ORDINARY ? DividendType.REGULAR : row.dividend_type;
  return `economic|${row.security_id}|${row.ex_date}|${row.currency}|${dividendType}`;
}

export function validateDividends(rows) {
  const list = [...rows];
  const errors = [];
  const warnings = [];
  const seen = new Set();
  for (const row of list) {
    const key = dividendEventKey(row);
    if (seen.has(key)) {
      errors.push(`Duplicate dividend event for ${row.security_id} on ${row.ex_date}.`);
    }
    seen.add(key);
    const currency = row.currency ?? '';
    if (currency.length !== 3 || !/^[a-zA-Z]{3}$/.test(currency) || currency !== currency.toUpperCase()) {
      errors.push(`Invalid dividend currency for ${row.security_id} on ${row.ex_date}.`);
    }
    if (!DIVIDEND_TYPES.has(row.dividend_type)) {
      errors.push(`Invalid dividend type for ${row.security_id} on ${row.ex_date}.`);
    }
    if (row.pay_date && row.pay_date < row.ex_date) {
      errors.push(`Dividend pay date precedes ex-date for ${row.security_id} on ${row.ex_date}.`);
    }
    if (row.record_date && row.record_date < row.ex_date) {
      warnings.push(`Dividend record date precedes ex-date for ${row.security_id} on ${row.ex_date}.`);
    }
  }
  const status = errors.length ? DataQualityStatus.FAILED : warnings.length ? DataQualityStatus.WARNING : DataQualityStatus.OK;
  return { status, errors, warnings, row_count: list.length, is_valid: errors.length === 0 };
}
