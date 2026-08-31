import { addDays } from './calendar.js';
import { ZERO, dec } from './money.js';
import { DistributionPolicy } from './models.js';

export function estimatedPayDate(exDate) {
  return addDays(exDate, 30);
}

export function appliesOn(rule, eventDate) {
  return rule.effective_from <= eventDate && (rule.effective_to == null || eventDate <= rule.effective_to);
}

export function taxRateFor(event, security, taxRules) {
  const sourceCountry = event.source_country || security.income_source_country;
  if (!sourceCountry) return null;
  const matches = taxRules.filter(
    (rule) =>
      rule.source_country.toUpperCase() === sourceCountry.toUpperCase() &&
      rule.income_type === 'dividend' &&
      rule.investor_type === 'singapore_individual' &&
      appliesOn(rule, event.ex_date),
  );
  if (!matches.length) return null;
  let best = matches[0];
  for (const rule of matches) {
    if (rule.effective_from > best.effective_from) best = rule;
  }
  return dec(best.rate);
}

export function filterAccumulatingDividends(security, rows, warnings) {
  if (
    (security.distribution_policy === DistributionPolicy.ACCUMULATING ||
      security.distribution_policy === DistributionPolicy.NON_DISTRIBUTING) &&
    rows.length
  ) {
    warnings.push(`Dividend events ignored because this security is marked ${security.distribution_policy}.`);
    return [];
  }
  return rows;
}

export function dividendTypeWarnings(rows) {
  const warnings = [];
  for (const event of rows) {
    const type = event.dividend_type;
    if (type === 'unknown' || type === 'ordinary') {
      warnings.push(
        `Dividend type for ${event.ex_date} is not fully classified; it is modeled as a cash distribution.`,
      );
    } else if (type === 'return_of_capital') {
      warnings.push(
        `Return of capital on ${event.ex_date} is modeled as a cash distribution; tax treatment is not inferred.`,
      );
    }
  }
  return warnings;
}

export function zeroIfNull(rate) {
  return rate == null ? ZERO : rate;
}

export function asDecimalOrZero(value) {
  return dec(value ?? 0);
}
