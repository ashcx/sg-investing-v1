import { daysBetween, insort } from './calendar.js';
import {
  dividendTypeWarnings,
  estimatedPayDate,
  filterAccumulatingDividends,
  taxRateFor,
} from './dividends.js';
import { rateForDate } from './fx.js';
import { DAYS_PER_YEAR, ONE, ZERO, dec, sumDecimals } from './money.js';
import { AnalysisDataError, DataQualityStatus, EngineValueError, normalizeScenario } from './models.js';
import { resolvePrice, sortedPrices } from './prices.js';
import { applyActions, groupByEffectiveDate } from './splits.js';
import { validateDividends } from './validation.js';

export const DcaFrequency = {
  MONTHLY: 'monthly',
  QUARTERLY: 'quarterly',
  YEARLY: 'yearly',
};

function periodKey(value, frequency) {
  if (frequency === DcaFrequency.MONTHLY) return `${value.slice(0, 4)}-M${Number(value.slice(5, 7))}`;
  if (frequency === DcaFrequency.QUARTERLY) {
    const quarter = Math.floor((Number(value.slice(5, 7)) - 1) / 3) + 1;
    return `${value.slice(0, 4)}-Q${quarter}`;
  }
  return value.slice(0, 4);
}

export function contributionDates(prices, startDate, endDate, frequency) {
  const selected = new Map();
  for (const row of prices) {
    if (startDate <= row.trading_date && row.trading_date <= endDate) {
      const key = periodKey(row.trading_date, frequency);
      if (!selected.has(key)) selected.set(key, row.trading_date);
    }
  }
  return [...selected.values()];
}

export function xirr(cashFlows) {
  const flows = [...cashFlows].sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  if (flows.length < 2) return null;
  if (!flows.some(([, amount]) => amount.lt(0))) return null;
  if (!flows.some(([, amount]) => amount.gt(0))) return null;
  const origin = flows[0][0];

  const npv = (rate) => {
    let total = ZERO;
    for (const [flowDate, amount] of flows) {
      const years = dec(daysBetween(origin, flowDate)).div(DAYS_PER_YEAR);
      const factor = ONE.plus(rate).pow(years);
      total = total.plus(amount.div(factor));
    }
    return total;
  };

  let low = dec('-0.9999');
  let high = dec('10.0');
  let lowValue = npv(low);
  let highValue = npv(high);
  while (lowValue.times(highValue).gt(0) && high.lt(dec('1000000'))) {
    high = high.times(2);
    highValue = npv(high);
  }
  if (!lowValue.isFinite() || !highValue.isFinite() || lowValue.times(highValue).gt(0)) return null;
  const tolerance = dec('1e-10');
  for (let i = 0; i < 200; i += 1) {
    const midpoint = low.plus(high).div(2);
    const value = npv(midpoint);
    if (value.abs().lt(tolerance)) return midpoint;
    if (lowValue.times(value).lte(0)) {
      high = midpoint;
      highValue = value;
    } else {
      low = midpoint;
      lowValue = value;
    }
  }
  return low.plus(high).div(2);
}

export function dcaAnalysis({
  security,
  prices,
  fxRates,
  startDate,
  endDate,
  contributionSgd,
  frequency = DcaFrequency.MONTHLY,
  scenario,
  dividends = [],
  corporateActions = [],
  taxRules = [],
}) {
  const activeScenario = normalizeScenario(scenario);
  const contribution = dec(contributionSgd);
  if (contribution.lte(0)) throw new EngineValueError('contribution_sgd must be greater than zero.');
  if (endDate < startDate) throw new EngineValueError('end_date must not precede start_date.');
  const priceRows = sortedPrices(prices, security);
  const purchaseDates = contributionDates(priceRows, startDate, endDate, frequency);
  if (!purchaseDates.length) {
    throw new AnalysisDataError('No trading dates exist in the requested DCA period.');
  }
  let valuation = null;
  for (let i = priceRows.length - 1; i >= 0; i -= 1) {
    if (priceRows[i].trading_date <= endDate) {
      valuation = priceRows[i];
      break;
    }
  }
  if (valuation === null) {
    throw new AnalysisDataError('No valuation price exists on or before the requested end date.');
  }

  const contributionsByDate = new Map(purchaseDates.map((date) => [date, contribution]));
  const warnings = [];
  const suppliedDividends = dividends.filter((event) => event.security_id === security.security_id);
  const dividendValidation = validateDividends(suppliedDividends);
  if (!dividendValidation.is_valid) {
    throw new AnalysisDataError(
      'Dividend input failed validation: ' + dividendValidation.errors.join('; '),
    );
  }
  let dividendRows = suppliedDividends
    .filter(
      (event) => purchaseDates[0] < event.ex_date && event.ex_date <= valuation.trading_date,
    )
    .sort((a, b) => (a.ex_date < b.ex_date ? -1 : a.ex_date > b.ex_date ? 1 : 0));
  dividendRows = filterAccumulatingDividends(security, dividendRows, warnings);
  warnings.push(...dividendTypeWarnings(dividendRows));

  const actionsByDate = new Map();
  for (const action of corporateActions) {
    if (
      action.security_id === security.security_id &&
      purchaseDates[0] < action.effective_date &&
      action.effective_date <= valuation.trading_date
    ) {
      const list = actionsByDate.get(action.effective_date);
      if (list) list.push(action);
      else actionsByDate.set(action.effective_date, [action]);
    }
  }
  const dividendsByDate = new Map();
  for (const event of dividendRows) {
    const list = dividendsByDate.get(event.ex_date);
    if (list) list.push(event);
    else dividendsByDate.set(event.ex_date, [event]);
  }

  const timeline = [
    ...new Set([...contributionsByDate.keys(), ...actionsByDate.keys(), ...dividendsByDate.keys()]),
  ].sort();
  const cashByDate = new Map();
  const reinvestmentsByDate = new Map();
  let shares = ZERO;
  let cashDividends = ZERO;
  let cursor = 0;
  while (cursor < timeline.length) {
    const eventDate = timeline[cursor];
    shares = applyActions(shares, actionsByDate.get(eventDate) ?? []);
    if (activeScenario.dividends_enabled) {
      for (const event of dividendsByDate.get(eventDate) ?? []) {
        const grossEventCurrency = shares.times(dec(event.amount));
        let rate = ZERO;
        if (event.dividend_type === 'return_of_capital') {
          rate = ZERO;
        } else if (activeScenario.withholding_tax_enabled) {
          const matchedRate = taxRateFor(event, security, taxRules);
          rate = matchedRate == null ? ZERO : matchedRate;
          if (rate.isZero() && matchedRate == null) {
            warnings.push(`No dividend tax rule for ${event.ex_date}; assumed 0%.`);
          }
        }
        const netEventCurrency = grossEventCurrency.times(ONE.minus(rate));
        const availability = event.pay_date ?? estimatedPayDate(event.ex_date);
        if (event.pay_date == null) {
          warnings.push(
            `Approximated dividend pay date for ${event.ex_date} as ${availability}.`,
          );
        } else if (availability < event.ex_date) {
          throw new AnalysisDataError(`Dividend pay date precedes ex-date for ${event.ex_date}.`);
        }
        let payPrice;
        try {
          payPrice = resolvePrice(priceRows, availability, { rule: 'next_trading_day' });
        } catch (error) {
          if (!(error instanceof AnalysisDataError)) throw error;
          warnings.push(
            `Could not resolve a trading day for dividend dated ${event.ex_date}; it is excluded from end-date value.`,
          );
          continue;
        }
        if (payPrice.trading_date > valuation.trading_date) {
          warnings.push(`Dividend dated ${event.ex_date} becomes available after valuation.`);
          continue;
        }
        const eventFx = rateForDate(event.currency, payPrice.trading_date, fxRates);
        const securityFx = rateForDate(security.currency, payPrice.trading_date, fxRates);
        const net = netEventCurrency.times(eventFx).div(securityFx);
        const target = activeScenario.reinvest_dividends ? reinvestmentsByDate : cashByDate;
        const pending = target.get(payPrice.trading_date);
        if (pending) pending.push(net);
        else target.set(payPrice.trading_date, [net]);
        if (payPrice.trading_date > eventDate && !timeline.includes(payPrice.trading_date)) {
          insort(timeline, payPrice.trading_date);
        }
      }
    }
    const pendingCash = cashByDate.get(eventDate);
    if (pendingCash && pendingCash.length) {
      cashDividends = cashDividends.plus(sumDecimals(pendingCash));
    }
    const pendingReinvestments = reinvestmentsByDate.get(eventDate);
    if (pendingReinvestments && pendingReinvestments.length) {
      const payPrice = priceRows.find((row) => row.trading_date >= eventDate);
      shares = shares.plus(sumDecimals(pendingReinvestments).div(dec(payPrice.close)));
    }
    if (contributionsByDate.has(eventDate)) {
      const buyPrice = priceRows.find((row) => row.trading_date === eventDate);
      const fxRate = rateForDate(security.currency, eventDate, fxRates);
      shares = shares.plus(contributionsByDate.get(eventDate).div(fxRate).div(dec(buyPrice.close)));
    }
    cursor += 1;
  }

  const endFx = rateForDate(security.currency, valuation.trading_date, fxRates);
  const finalValueForeignCurrency = shares.times(dec(valuation.close)).plus(cashDividends);
  const finalValue = finalValueForeignCurrency.times(endFx);
  const total = contribution.times(dec(purchaseDates.length));
  const contributionsForeignCurrency = purchaseDates.map(
    (purchaseDate) => contribution.div(rateForDate(security.currency, purchaseDate, fxRates)),
  );
  const totalForeignCurrency = sumDecimals(contributionsForeignCurrency);

  return {
    security,
    contribution_dates: purchaseDates,
    total_contributed_sgd: total,
    total_contributed_foreign_currency: totalForeignCurrency,
    final_value_sgd: finalValue,
    final_value_foreign_currency: finalValueForeignCurrency,
    gain_loss_sgd: finalValue.minus(total),
    gain_loss_foreign_currency: finalValueForeignCurrency.minus(totalForeignCurrency),
    xirr: xirr([
      ...purchaseDates.map((date) => [date, contribution.neg()]),
      [valuation.trading_date, finalValue],
    ]),
    xirr_foreign_currency: xirr([
      ...purchaseDates.map((date, i) => [date, contributionsForeignCurrency[i].neg()]),
      [valuation.trading_date, finalValueForeignCurrency],
    ]),
    shares,
    methodology: {
      contribution_timing: 'first_available_trading_day_of_period',
      cost_basis: 'weighted_average_not_applicable_to_dca_return',
      dividend_reinvestment: activeScenario.reinvest_dividends,
      dividend_type_handling:
        'regular/special/unknown treated as cash; return_of_capital treated as cash without assumed withholding',
      ter_deducted: false,
    },
    data_quality: { status: warnings.length ? DataQualityStatus.WARNING : DataQualityStatus.OK, warnings },
  };
}
