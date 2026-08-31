import { addDays, daysBetween, insort } from './calendar.js';
import {
  dividendTypeWarnings,
  estimatedPayDate,
  filterAccumulatingDividends,
  taxRateFor,
} from './dividends.js';
import { rateForDateWithStaleness, warnIfFxIsStale } from './fx.js';
import { DAYS_PER_YEAR, ONE, ZERO, dec, sumDecimals } from './money.js';
import {
  AnalysisDataError,
  DataQualityStatus,
  DATE_MAX,
  EngineValueError,
  SGD,
  normalizeScenario,
} from './models.js';
import { resolvePrice, sortedPrices } from './prices.js';
import { applyActions, groupByEffectiveDate } from './splits.js';
import { validateDividends } from './validation.js';

function cagr(initial, finalValue, start, end) {
  const elapsedDays = daysBetween(start, end);
  if (elapsedDays <= 0 || initial.isZero() || finalValue.lt(0)) return null;
  const years = dec(elapsedDays).div(DAYS_PER_YEAR);
  const ratio = Number(finalValue.div(initial));
  return dec(String(Math.pow(ratio, 1 / Number(years)) - 1));
}

export function analyzeSecurity({
  security,
  prices,
  fxRates,
  startDate,
  endDate,
  initialSgd,
  scenario,
  dividends = [],
  corporateActions = [],
  taxRules = [],
}) {
  const activeScenario = normalizeScenario(scenario);
  const investmentSgd = dec(initialSgd);
  if (investmentSgd.lte(0)) throw new EngineValueError('initial_sgd must be greater than zero.');
  if (endDate < startDate) throw new EngineValueError('end_date must not precede start_date.');

  const priceRows = sortedPrices(prices, security);
  const purchase = resolvePrice(priceRows, startDate, { rule: activeScenario.purchase_date_rule });
  const valuation = resolvePrice(priceRows, endDate, { rule: activeScenario.valuation_date_rule });
  if (valuation.trading_date < purchase.trading_date) {
    throw new AnalysisDataError('Resolved valuation date precedes the purchase date.');
  }

  const startFx = rateForDateWithStaleness(security.currency, purchase.trading_date, fxRates);
  const endFx = rateForDateWithStaleness(security.currency, valuation.trading_date, fxRates);
  const initialInvestmentNative = investmentSgd.div(startFx.rate);
  let shares = initialInvestmentNative.div(dec(purchase.close));
  let cashDividends = ZERO;
  let grossDividends = ZERO;
  let withholdingTax = ZERO;
  let grossDividendsSgdAtPayment = ZERO;
  let withholdingTaxSgdAtPayment = ZERO;
  let netDividendsSgdAtPayment = ZERO;
  const warnings = [];
  warnIfFxIsStale(warnings, {
    currency: security.currency,
    requested: purchase.trading_date,
    lag: startFx.lag,
  });
  warnIfFxIsStale(warnings, {
    currency: security.currency,
    requested: valuation.trading_date,
    lag: endFx.lag,
  });

  const suppliedDividends = dividends.filter((event) => event.security_id === security.security_id);
  const dividendValidation = validateDividends(suppliedDividends);
  if (!dividendValidation.is_valid) {
    throw new AnalysisDataError(
      'Dividend input failed validation: ' + dividendValidation.errors.join('; '),
    );
  }
  let dividendRows = suppliedDividends
    .filter((event) => purchase.trading_date < event.ex_date && event.ex_date <= valuation.trading_date)
    .sort((a, b) => {
      if (a.ex_date !== b.ex_date) return a.ex_date < b.ex_date ? -1 : 1;
      const aPay = a.pay_date ?? DATE_MAX;
      const bPay = b.pay_date ?? DATE_MAX;
      return aPay < bPay ? -1 : aPay > bPay ? 1 : 0;
    });
  const actionRows = corporateActions
    .filter(
      (action) =>
        action.security_id === security.security_id &&
        purchase.trading_date < action.effective_date &&
        action.effective_date <= valuation.trading_date,
    )
    .sort((a, b) => (a.effective_date < b.effective_date ? -1 : a.effective_date > b.effective_date ? 1 : 0));

  dividendRows = filterAccumulatingDividends(security, dividendRows, warnings);
  warnings.push(...dividendTypeWarnings(dividendRows));

  const actionsByDate = groupByEffectiveDate(actionRows);
  const dividendsByDate = new Map();
  for (const event of dividendRows) {
    const list = dividendsByDate.get(event.ex_date);
    if (list) list.push(event);
    else dividendsByDate.set(event.ex_date, [event]);
  }

  const reinvestmentsByDate = new Map();
  const cashByDate = new Map();

  const timeline = [...new Set([...actionsByDate.keys(), ...dividendsByDate.keys()])].sort();
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
          if (matchedRate == null) {
            warnings.push(
              `No dividend tax rule for ${event.source_country || security.income_source_country || 'unknown'} on ${event.ex_date}; assumed 0%.`,
            );
          } else {
            rate = matchedRate;
          }
        }
        const taxEventCurrency = grossEventCurrency.times(rate);
        const netEventCurrency = grossEventCurrency.minus(taxEventCurrency);
        let availabilityDate = event.pay_date;
        if (availabilityDate == null) {
          availabilityDate = estimatedPayDate(event.ex_date);
          warnings.push(
            `Approximated dividend pay date for ${event.ex_date} as ${availabilityDate}.`,
          );
        } else if (availabilityDate < event.ex_date) {
          throw new AnalysisDataError(`Dividend pay date precedes ex-date for ${event.ex_date}.`);
        }
        let availabilityPrice;
        try {
          availabilityPrice = resolvePrice(priceRows, availabilityDate, { rule: 'next_trading_day' });
        } catch (error) {
          if (!(error instanceof AnalysisDataError)) throw error;
          warnings.push(
            `Could not resolve a trading day for dividend dated ${event.ex_date}; it is excluded from end-date value.`,
          );
          continue;
        }
        if (availabilityPrice.trading_date > valuation.trading_date) {
          warnings.push(
            `Dividend dated ${event.ex_date} becomes available after valuation and is excluded from end-date value.`,
          );
          continue;
        }
        const securityPaymentFx = rateForDateWithStaleness(
          security.currency,
          availabilityPrice.trading_date,
          fxRates,
        );
        const eventPaymentFx = rateForDateWithStaleness(
          event.currency,
          availabilityPrice.trading_date,
          fxRates,
        );
        warnIfFxIsStale(warnings, {
          currency: security.currency,
          requested: availabilityPrice.trading_date,
          lag: securityPaymentFx.lag,
        });
        if (event.currency !== security.currency) {
          warnIfFxIsStale(warnings, {
            currency: event.currency,
            requested: availabilityPrice.trading_date,
            lag: eventPaymentFx.lag,
          });
        }
        const eventToSecurityFx = eventPaymentFx.rate.div(securityPaymentFx.rate);
        const gross = grossEventCurrency.times(eventToSecurityFx);
        const tax = taxEventCurrency.times(eventToSecurityFx);
        const net = netEventCurrency.times(eventToSecurityFx);
        grossDividends = grossDividends.plus(gross);
        withholdingTax = withholdingTax.plus(tax);
        grossDividendsSgdAtPayment = grossDividendsSgdAtPayment.plus(
          grossEventCurrency.times(eventPaymentFx.rate),
        );
        withholdingTaxSgdAtPayment = withholdingTaxSgdAtPayment.plus(
          taxEventCurrency.times(eventPaymentFx.rate),
        );
        netDividendsSgdAtPayment = netDividendsSgdAtPayment.plus(
          netEventCurrency.times(eventPaymentFx.rate),
        );
        const target = activeScenario.reinvest_dividends ? reinvestmentsByDate : cashByDate;
        const pending = target.get(availabilityPrice.trading_date);
        if (pending) pending.push(net);
        else target.set(availabilityPrice.trading_date, [net]);
        if (availabilityPrice.trading_date > eventDate && !timeline.includes(availabilityPrice.trading_date)) {
          insort(timeline, availabilityPrice.trading_date);
        }
      }
    }

    const pendingCash = cashByDate.get(eventDate);
    if (pendingCash && pendingCash.length) {
      cashDividends = cashDividends.plus(sumDecimals(pendingCash));
    }
    const pendingReinvestments = reinvestmentsByDate.get(eventDate);
    if (pendingReinvestments && pendingReinvestments.length) {
      const reinvestmentPrice = resolvePrice(priceRows, eventDate, { rule: 'next_trading_day' });
      shares = shares.plus(sumDecimals(pendingReinvestments).div(dec(reinvestmentPrice.close)));
    }
    cursor += 1;
  }

  const finalSecurityValue = shares.times(dec(valuation.close));
  const finalValueNative = finalSecurityValue.plus(cashDividends);
  const finalValueSgd = finalValueNative.times(endFx.rate);
  const startNativeValue = dec(purchase.close);
  const endNativeValue = dec(valuation.close);
  const priceReturnNative = endNativeValue.div(startNativeValue).minus(ONE);
  const priceReturnSgd = endNativeValue.times(endFx.rate).div(startNativeValue.times(startFx.rate)).minus(ONE);
  const netDividends = grossDividends.minus(withholdingTax);
  const quality = warnings.length ? DataQualityStatus.WARNING : DataQualityStatus.OK;

  return {
    security,
    period: { start_date: purchase.trading_date, end_date: valuation.trading_date },
    initial_investment_sgd: investmentSgd,
    initial_investment_foreign_currency: initialInvestmentNative,
    price_return: { foreign_currency: priceReturnNative, sgd: priceReturnSgd },
    dividends: {
      gross_foreign_currency: grossDividends,
      withholding_tax_foreign_currency: withholdingTax,
      net_foreign_currency: netDividends,
      cash_foreign_currency: cashDividends,
      gross_sgd_at_payment: grossDividendsSgdAtPayment,
      withholding_tax_sgd_at_payment: withholdingTaxSgdAtPayment,
      net_sgd_at_payment: netDividendsSgdAtPayment,
    },
    investment: {
      shares,
      final_security_value_foreign_currency: finalSecurityValue,
      final_value_foreign_currency: finalValueNative,
      final_value_sgd: finalValueSgd,
    },
    returns: {
      total_return: finalValueSgd.div(investmentSgd).minus(ONE),
      cagr: cagr(investmentSgd, finalValueSgd, purchase.trading_date, valuation.trading_date),
      total_return_foreign_currency: finalValueNative.div(initialInvestmentNative).minus(ONE),
      cagr_foreign_currency: cagr(
        initialInvestmentNative,
        finalValueNative,
        purchase.trading_date,
        valuation.trading_date,
      ),
    },
    fx: { start_rate: startFx.rate, end_rate: endFx.rate },
    methodology: {
      price: 'daily_close',
      price_return: 'raw_unadjusted_close_to_close_not_split_adjusted',
      purchase_date_rule: activeScenario.purchase_date_rule,
      valuation_date_rule: activeScenario.valuation_date_rule,
      dividend_reinvestment: 'pay_date_close_with_30_day_ex_date_fallback',
      fractional_shares: true,
      withholding_tax: activeScenario.withholding_tax_enabled,
      dividend_native_currency: security.currency,
      dividend_sgd_translation: 'payment_date_fx_rate_for_actual_dividend_currency',
      dividend_type_handling:
        'regular/special/unknown treated as cash; return_of_capital treated as cash without assumed withholding',
      ter_deducted: false,
      methodology_version: activeScenario.methodology_version,
    },
    data_quality: { status: quality, warnings },
  };
}
