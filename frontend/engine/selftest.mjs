import { readFileSync } from 'node:fs';
import { analyzeSecurity, analyzePortfolio, contributionDates, dcaAnalysis, dec, resolvePrice, sortedPrices, rateForDateWithStaleness, warnIfFxIsStale, xirr, Decimal, AnalysisDataError, EngineValueError } from './index.js';

const FIXTURES = new URL('./fixtures/', import.meta.url);
const loadFixture = (name) => JSON.parse(readFileSync(new URL(name, FIXTURES), 'utf8'));

const results = { pass: 0, fail: 0 };
const failures = [];

function check(name, condition, detail) {
  if (condition) {
    results.pass += 1;
  } else {
    results.fail += 1;
    failures.push({ name, detail });
    console.log(`  FAIL ${name}${detail === undefined ? '' : ` :: ${detail}`}`);
  }
}

function checkEqual(name, actual, expected) {
  const a = typeof actual === 'object' && actual !== null ? JSON.stringify(actual) : String(actual);
  const e = typeof expected === 'object' && expected !== null ? JSON.stringify(expected) : String(expected);
  check(name, a === e, a === e ? undefined : `expected ${e}, got ${a}`);
}

function checkThrows(name, fn, messagePart) {
  let threw = null;
  try {
    fn();
  } catch (error) {
    threw = error;
  }
  check(name, threw !== null && (!messagePart || String(threw.message).includes(messagePart)), threw === null ? 'did not throw' : `${threw.name}: ${threw.message}`);
}

function section(title) {
  console.log(`\n== ${title}`);
}

function serializeEnvelope(envelope) {
  return JSON.parse(
    JSON.stringify(envelope, (key, value) => (value instanceof Decimal ? value.toString() : value)),
  );
}

const DECIMAL_RE = /^-?\d+(\.\d+)?([eE][+-]?\d+)?$/;

function compareValues(actual, expected, path, errors, decimalTolerancePaths) {
  if (Array.isArray(expected)) {
    if (!Array.isArray(actual)) {
      errors.push(`${path}: expected array`);
      return;
    }
    if (actual.length !== expected.length) {
      errors.push(`${path}: array length ${actual.length} vs ${expected.length}`);
      return;
    }
    for (let i = 0; i < expected.length; i += 1) {
      compareValues(actual[i], expected[i], `${path}[${i}]`, errors, decimalTolerancePaths);
    }
    return;
  }
  if (expected !== null && typeof expected === 'object') {
    if (actual === null || typeof actual !== 'object' || Array.isArray(actual)) {
      errors.push(`${path}: expected object`);
      return;
    }
    const actualKeys = Object.keys(actual).sort();
    const expectedKeys = Object.keys(expected).sort();
    if (JSON.stringify(actualKeys) !== JSON.stringify(expectedKeys)) {
      errors.push(`${path}: key sets differ`);
      return;
    }
    for (const key of expectedKeys) {
      compareValues(actual[key], expected[key], `${path}.${key}`, errors, decimalTolerancePaths);
    }
    return;
  }
  const typeMatches = actual === null ? expected === null : typeof actual === typeof expected;
  if (!typeMatches) {
    errors.push(`${path}: type ${actual === null ? 'null' : typeof actual} vs ${expected === null ? 'null' : typeof expected}`);
    return;
  }
  if (typeof expected === 'string' && DECIMAL_RE.test(expected) && DECIMAL_RE.test(actual)) {
    if (decimalTolerancePaths && decimalTolerancePaths.some((pattern) => path.includes(pattern))) {
      const difference = dec(actual).minus(dec(expected)).abs();
      if (difference.gt('1e-9')) errors.push(`${path}: ${actual} vs ${expected} (tolerance 1e-9)`);
      return;
    }
    if (!dec(actual).eq(dec(expected))) {
      errors.push(`${path}: ${actual} vs ${expected}`);
    }
    return;
  }
  if (actual !== expected) {
    errors.push(`${path}: ${JSON.stringify(actual)} vs ${JSON.stringify(expected)}`);
  }
}

const usdFxRows = ['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05', '2024-01-08', '2024-01-09', '2024-07-01'].map(
  (rate_date) => ({ rate_date, base_currency: 'USD', rate_to_sgd: '1' }),
);

const US_TAX_RULE = {
  rule_id: 'US_DIVIDEND_NONRESIDENT',
  source_country: 'US',
  income_type: 'dividend',
  investor_type: 'singapore_individual',
  rate: '0.30',
  effective_from: '1900-01-01',
  effective_to: null,
};

const syntheticSecurity = {
  security_id: 'test-sec-0001',
  ticker: 'TEST',
  exchange: 'NASDAQ',
  market: 'US',
  name: 'Test Security',
  currency: 'USD',
  asset_type: 'ETF',
  domicile: 'US',
  income_source_country: 'US',
  isin: null,
  cusip: null,
  timezone: 'America/New_York',
  active: true,
  distribution_policy: 'distributing',
  expense_ratio: null,
};

const syntheticPrices = [
  { security_id: 'test-sec-0001', trading_date: '2024-01-02', close: '100', currency: 'USD' },
  { security_id: 'test-sec-0001', trading_date: '2024-01-03', close: '110', currency: 'USD' },
  { security_id: 'test-sec-0001', trading_date: '2024-01-04', close: '120', currency: 'USD' },
  { security_id: 'test-sec-0001', trading_date: '2024-01-05', close: '130', currency: 'USD' },
  { security_id: 'test-sec-0001', trading_date: '2024-01-08', close: '140', currency: 'USD' },
  { security_id: 'test-sec-0001', trading_date: '2024-01-09', close: '150', currency: 'USD' },
];

function runAnalysis(overrides = {}) {
  return analyzeSecurity({
    security: syntheticSecurity,
    prices: syntheticPrices,
    fxRates: usdFxRows,
    startDate: '2024-01-02',
    endDate: '2024-01-09',
    initialSgd: '1000',
    scenario: { dividends_enabled: true, reinvest_dividends: true, withholding_tax_enabled: true },
    dividends: [{ security_id: 'test-sec-0001', ex_date: '2024-01-04', amount: '1.00', currency: 'USD', pay_date: '2024-01-05', dividend_type: 'regular', source_country: 'US' }],
    corporateActions: [],
    taxRules: [US_TAX_RULE],
    ...overrides,
  });
}

section('Decimal exactness');
checkEqual('0.1 + 0.2 is exactly 0.3', dec('0.1').plus('0.2').toString(), '0.3');
checkEqual('Number 0.1 + 0.2 trap avoided', dec(0.1).plus(0.2).toString(), '0.3');
checkEqual('FX direction: US$100 x 1.35 = S$135', dec('100').times('1.35').toString(), '135');
checkEqual('28-digit division precision', dec('10000').div('1.35').toString(), '7407.407407407407407407407407');
checkEqual('re-multiplication exposes rounding', dec('1').div('3').times('3').toString(), '0.9999999999999999999999999999');
checkEqual('trailing-zero values compare equal numerically', dec('1653').eq('1653.0'), true);

section('Trading-day calendar and price resolution rules');
const sortedSynthetic = sortedPrices(syntheticPrices, syntheticSecurity);
checkEqual('next trading day over a weekend/holiday gap', resolvePrice(sortedSynthetic, '2024-01-06', { rule: 'next_trading_day' }).trading_date, '2024-01-08');
checkEqual('exact-hit next rule stays on the same date', resolvePrice(sortedSynthetic, '2024-01-05', { rule: 'next_trading_day' }).trading_date, '2024-01-05');
checkEqual('previous trading day before history start', resolvePrice(sortedSynthetic, '2024-01-07', { rule: 'previous_trading_day' }).trading_date, '2024-01-05');
checkEqual('previous rule on weekend resolves backwards', resolvePrice(sortedSynthetic, '2024-01-06', { rule: 'previous_trading_day' }).trading_date, '2024-01-05');
checkThrows('next rule past history end throws', () => resolvePrice(sortedSynthetic, '2024-02-01', { rule: 'next_trading_day' }), 'No price exists on or after 2024-02-01.');
checkThrows('previous rule before history start throws', () => resolvePrice(sortedSynthetic, '2023-12-25', { rule: 'previous_trading_day' }), 'No price exists on or before 2023-12-25.');
checkThrows('unsupported rule throws', () => resolvePrice(sortedSynthetic, '2024-01-05', { rule: 'same_day' }), 'Unsupported date rule: same_day.');
checkThrows('duplicate dates rejected', () => sortedPrices([...syntheticPrices, syntheticPrices[0]], syntheticSecurity), 'Price history contains duplicate trading dates.');
checkThrows('wrong price currency rejected', () => sortedPrices(syntheticPrices.map((row) => ({ ...row, currency: 'SGD' })), syntheticSecurity), 'Price currency does not match the security master.');

section('Purchase/valuation date rules and FX');
const weekendAnalysis = runAnalysis({ startDate: '2024-01-06', endDate: '2024-01-09' });
checkEqual('Saturday start resolves to next trading day (purchase rule)', weekendAnalysis.period.start_date, '2024-01-08');
checkEqual('valuation rule uses previous trading day', runAnalysis().period.end_date, '2024-01-09');
checkThrows('end before start rejected', () => runAnalysis({ startDate: '2024-02-01', endDate: '2024-01-01' }), 'end_date must not precede start_date.');
checkThrows('non-positive capital rejected', () => runAnalysis({ initialSgd: '0' }), 'initial_sgd must be greater than zero.');
const staleRows = [{ rate_date: '2024-01-02', base_currency: 'USD', rate_to_sgd: '1.35' }];
const stale = rateForDateWithStaleness('USD', '2024-01-15', staleRows);
checkEqual('staleness lag computed in calendar days', stale.lag, 13);
const staleWarnings = [];
warnIfFxIsStale(staleWarnings, { currency: 'USD', requested: '2024-01-15', lag: stale.lag });
checkEqual('staleness beyond 7 days warns', staleWarnings, ['USD/SGD FX rate for 2024-01-15 is 13 days stale.']);
const freshWarnings = [];
warnIfFxIsStale(freshWarnings, { currency: 'USD', requested: '2024-01-15', lag: 7 });
checkEqual('staleness at 7 days stays silent', freshWarnings.length, 0);

section('Dividend handling');
const reinvestResult = runAnalysis();
checkEqual(
  'fractional reinvestment on pay date at pay-date close',
  reinvestResult.investment.shares.toString(),
  dec('10').plus(dec('7').div(dec('130'))).toString(),
);
checkEqual('withholding tax 30% of gross', reinvestResult.dividends.withholding_tax_foreign_currency.toString(), '3');
checkEqual('net dividend gross minus tax', reinvestResult.dividends.net_foreign_currency.toString(), '7');
checkEqual('no cash left when reinvesting', reinvestResult.dividends.cash_foreign_currency.toString(), '0');
checkEqual('sgd-at-payment uses payment-date FX', reinvestResult.dividends.net_sgd_at_payment.toString(), '7');
checkEqual('warning status recorded', reinvestResult.data_quality.status, 'OK');
checkEqual('warnings empty for clean classified dividend', reinvestResult.data_quality.warnings.length, 0);

const cashResult = runAnalysis({ scenario: { dividends_enabled: true, reinvest_dividends: false, withholding_tax_enabled: true } });
checkEqual('cash dividend kept out of shares when reinvest disabled', cashResult.investment.shares.toString(), '10');
checkEqual('cash dividend accumulated', cashResult.dividends.cash_foreign_currency.toString(), '7');

const estimated = runAnalysis({
  dividends: [{ security_id: 'test-sec-0001', ex_date: '2024-01-04', amount: '1.00', currency: 'USD', pay_date: null, dividend_type: 'regular', source_country: 'US' }],
});
checkEqual('pay-date estimated as ex-date + 30 days then next trading day', estimated.data_quality.warnings, ['Approximated dividend pay date for 2024-01-04 as 2024-02-03.', 'Could not resolve a trading day for dividend dated 2024-01-04; it is excluded from end-date value.']);
checkEqual('unpayable dividend excluded from shares', estimated.investment.shares.toString(), '10');

checkThrows(
  'pay-before-ex record rejected during analysis',
  () =>
    runAnalysis({
      dividends: [{ security_id: 'test-sec-0001', ex_date: '2024-01-04', amount: '1.00', currency: 'USD', pay_date: '2024-01-03', dividend_type: 'regular', source_country: 'US' }],
    }),
  'Dividend pay date precedes ex-date for test-sec-0001 on 2024-01-04.',
);

const accumulatingSecurity = { ...syntheticSecurity, distribution_policy: 'accumulating' };
const accumulatingResult = analyzeSecurity({
  security: accumulatingSecurity,
  prices: syntheticPrices,
  fxRates: usdFxRows,
  startDate: '2024-01-02',
  endDate: '2024-01-09',
  initialSgd: '1000',
  dividends: [{ security_id: 'test-sec-0001', ex_date: '2024-01-04', amount: '1.00', currency: 'USD', pay_date: '2024-01-05', dividend_type: 'regular', source_country: 'US' }],
  taxRules: [US_TAX_RULE],
});
checkEqual('accumulating fund never emits investor dividends', accumulatingResult.dividends.gross_foreign_currency.toString(), '0');
checkEqual('accumulating fund shares untouched by supplied dividends', accumulatingResult.investment.shares.toString(), '10');
checkEqual('accumulating warning recorded', accumulatingResult.data_quality.warnings, ['Dividend events ignored because this security is marked accumulating.']);

const unclassified = runAnalysis({
  dividends: [{ security_id: 'test-sec-0001', ex_date: '2024-01-04', amount: '1.00', currency: 'USD', pay_date: '2024-01-05', dividend_type: 'ordinary', source_country: 'US' }],
});
checkEqual('legacy ordinary type classified with warning', unclassified.data_quality.warnings, ['Dividend type for 2024-01-04 is not fully classified; it is modeled as a cash distribution.']);

const roc = runAnalysis({
  dividends: [{ security_id: 'test-sec-0001', ex_date: '2024-01-04', amount: '1.00', currency: 'USD', pay_date: '2024-01-05', dividend_type: 'return_of_capital', source_country: 'US' }],
});
checkEqual('return of capital: no withholding assumed', roc.dividends.withholding_tax_foreign_currency.toString(), '0');
checkEqual('return of capital warning recorded', roc.data_quality.warnings, ['Return of capital on 2024-01-04 is modeled as a cash distribution; tax treatment is not inferred.']);

const noRuleWarnings = runAnalysis({ taxRules: [] });
checkEqual('missing tax rule assumed 0% with warning', noRuleWarnings.data_quality.warnings, ['No dividend tax rule for US on 2024-01-04; assumed 0%.']);

section('Splits and corporate actions');
const splitResult = analyzeSecurity({
  security: syntheticSecurity,
  prices: syntheticPrices,
  fxRates: usdFxRows,
  startDate: '2024-01-02',
  endDate: '2024-01-09',
  initialSgd: '1000',
  dividends: [{ security_id: 'test-sec-0001', ex_date: '2024-01-04', amount: '1.00', currency: 'USD', pay_date: '2024-01-05', dividend_type: 'regular', source_country: 'US' }],
  corporateActions: [{ security_id: 'test-sec-0001', effective_date: '2024-01-05', action_type: 'split', ratio: '2' }],
  taxRules: [US_TAX_RULE],
});
checkEqual('split applies at effective date before same-day pay-date reinvestment', splitResult.investment.shares.toString(), dec('20').plus(dec('7').div(dec('130'))).toString());
checkEqual('split entitlement uses pre-split shares for earlier ex-date', splitResult.dividends.gross_foreign_currency.toString(), '10');

section('DCA schedules and XIRR');
const schedulePrices = ['2024-01-02', '2024-01-03', '2024-02-01', '2024-04-01', '2024-06-03', '2024-06-04', '2024-07-01', '2024-10-01', '2024-12-02'].map((trading_date) => ({
  security_id: 'test-sec-0001',
  trading_date,
  close: '100',
  currency: 'USD',
}));
checkEqual('monthly schedule picks first available trading day of month', contributionDates(schedulePrices, '2024-01-01', '2024-12-31', 'monthly'), ['2024-01-02', '2024-02-01', '2024-04-01', '2024-06-03', '2024-07-01', '2024-10-01', '2024-12-02']);
checkEqual('quarterly schedule picks first available trading day of quarter', contributionDates(schedulePrices, '2024-01-01', '2024-12-31', 'quarterly'), ['2024-01-02', '2024-04-01', '2024-07-01', '2024-10-01']);
checkEqual('yearly schedule picks first available trading day of year', contributionDates(schedulePrices, '2024-01-01', '2024-12-31', 'yearly'), ['2024-01-02']);

const knownRate = xirr([
  ['2024-01-02', dec('-1000')],
  ['2025-01-02', dec('1100')],
]);
const dayNumber = (dateStr) =>
  Math.round(Date.UTC(Number(dateStr.slice(0, 4)), Number(dateStr.slice(5, 7)) - 1, Number(dateStr.slice(8, 10))) / 86400000);

function floatXirrOracle(flows) {
  const origin = dayNumber(flows[0][0]);
  const npv = (rate) =>
    flows.reduce((total, [date, amount]) => total + amount / Math.pow(1 + rate, (dayNumber(date) - origin) / 365.2425), 0);
  let low = -0.9999;
  let high = 10;
  while (npv(low) * npv(high) > 0) high *= 2;
  for (let i = 0; i < 300; i += 1) {
    const mid = (low + high) / 2;
    if (npv(low) * npv(mid) <= 0) high = mid;
    else low = mid;
  }
  return (low + high) / 2;
}

const knownDays = dayNumber('2025-01-02') - dayNumber('2024-01-02');
const expectedRate = Math.pow(1.1, 365.2425 / knownDays) - 1;
checkEqual('XIRR oracle agrees the span is 366 days (leap year)', knownDays, 366);
check('XIRR converges to known rate over leap-year span', knownRate !== null && Number(knownRate.minus(String(expectedRate)).abs()) < 1e-9, `got ${knownRate}, expected ${expectedRate}`);
checkEqual('XIRR is null without both signs', xirr([['2024-01-02', dec('100')], ['2025-01-02', dec('110')]]), null);
checkEqual('XIRR is null with fewer than two flows', xirr([['2024-01-02', dec('-100')]]), null);
const multiFlows = [
  ['2024-01-02', dec('-500')],
  ['2024-07-02', dec('-500')],
  ['2025-01-02', dec('1100')],
];
const multiRate = xirr(multiFlows);
const oracleRate = floatXirrOracle(multiFlows.map(([date, amount]) => [date, Number(amount)]));
check('XIRR matches independent float oracle on multi-flow case', multiRate !== null && Number(multiRate.minus(String(oracleRate)).abs()) < 1e-9, `got ${multiRate}, oracle ${oracleRate}`);

section('Portfolio weighted-average cost reconstruction');
const portfolioSecurities = { 'test-sec-0001': syntheticSecurity };
const wacTransactions = [
  { transaction_id: 't1', transaction_date: '2024-01-02', security_id: 'test-sec-0001', transaction_type: 'BUY', quantity: '10', cash_amount: '1000', currency: 'USD', fees: '2' },
  { transaction_id: 't2', transaction_date: '2024-03-02', security_id: 'test-sec-0001', transaction_type: 'BUY', quantity: '10', cash_amount: '1200', currency: 'USD', fees: '2' },
  { transaction_id: 't3', transaction_date: '2024-05-02', security_id: 'test-sec-0001', transaction_type: 'SELL', quantity: '5', cash_amount: '650', currency: 'USD', fees: '3' },
  { transaction_id: 't4', transaction_date: '2024-02-02', security_id: null, transaction_type: 'CASH_DEPOSIT', quantity: '0', cash_amount: '5000', currency: 'USD', fees: '0' },
];
const wacResult = analyzePortfolio({
  transactions: wacTransactions,
  securities: portfolioSecurities,
  prices: [{ security_id: 'test-sec-0001', trading_date: '2024-07-01', close: '100', currency: 'USD' }],
  fxRates: usdFxRows,
  asOf: '2024-07-01',
});
checkEqual('holdings survive sorting by ticker', wacResult.holdings.length, 1);
checkEqual('weighted average cost', wacResult.holdings[0].weighted_average_cost.toString(), dec('2204').div('20').toString());
checkEqual('remaining quantity', wacResult.holdings[0].quantity.toString(), '15');
checkEqual('remaining cost basis', wacResult.holdings[0].cost_basis_native.toString(), dec('2204').minus(dec('110.2').times('5')).toString());
checkEqual('realized P/L on partial sale', wacResult.holdings[0].realized_pl_native.toString(), dec('647').minus(dec('110.2').times('5')).toString());
checkEqual('unrealized P/L mark-to-market', wacResult.holdings[0].unrealized_pl_native.toString(), dec('1500').minus(dec('2204').minus(dec('551'))).toString());
checkEqual('cash by currency nets deposits and fees', wacResult.cash_by_currency.USD.toString(), dec('5000').minus('1002').minus('1202').plus('647').toString());
checkEqual('total market value in SGD at as-of FX', wacResult.total_market_value_sgd.toString(), '4943');
checkEqual('portfolio methodology keys', wacResult.methodology, { cost_basis: 'weighted_average', end_value: 'mark_to_market' });
checkThrows('oversell rejected', () =>
  analyzePortfolio({
    transactions: [
      { transaction_id: 't1', transaction_date: '2024-01-02', security_id: 'test-sec-0001', transaction_type: 'BUY', quantity: '1', cash_amount: '100', currency: 'USD', fees: '0' },
      { transaction_id: 't2', transaction_date: '2024-01-03', security_id: 'test-sec-0001', transaction_type: 'SELL', quantity: '2', cash_amount: '200', currency: 'USD', fees: '0' },
    ],
    securities: portfolioSecurities,
    prices: [{ security_id: 'test-sec-0001', trading_date: '2024-07-01', close: '100', currency: 'USD' }],
    fxRates: usdFxRows,
    asOf: '2024-07-01',
  }), 'Cannot sell more shares than the weighted-average ledger holds.');
checkThrows('unknown security rejected', () =>
  analyzePortfolio({
    transactions: [{ transaction_id: 't1', transaction_date: '2024-01-02', security_id: 'missing', transaction_type: 'BUY', quantity: '1', cash_amount: '100', currency: 'USD', fees: '0' }],
    securities: portfolioSecurities,
    prices: [{ security_id: 'test-sec-0001', trading_date: '2024-07-01', close: '100', currency: 'USD' }],
    fxRates: usdFxRows,
    asOf: '2024-07-01',
  }), 'Security transaction refers to an unknown security.');

section('Python envelope parity (model_dump(mode="json") shapes)');
const inputs = loadFixture('inputs-qqq-2024h1.json');
const pyAnalysis = loadFixture('analysis-qqq-2024h1.json');
const pyDca = loadFixture('dca-qqq-2024h1.json');
const pyPortfolio = loadFixture('portfolio-fixture-2024.json');

const jsAnalysis = serializeEnvelope(
  analyzeSecurity({
    security: inputs.security,
    prices: inputs.prices,
    fxRates: inputs.fx_rates,
    startDate: inputs.analysis_request.start_date,
    endDate: inputs.analysis_request.end_date,
    initialSgd: inputs.analysis_request.initial_sgd,
    scenario: inputs.analysis_request.scenario,
    dividends: inputs.dividends,
    corporateActions: inputs.corporate_actions,
    taxRules: inputs.tax_rules,
  }),
);
const analysisErrors = [];
compareValues(jsAnalysis, pyAnalysis, 'analysis', analysisErrors);
check('analysis envelope matches Python exactly (values + types)', analysisErrors.length === 0, analysisErrors.join(' | '));
checkEqual('analysis top-level keys identical', Object.keys(jsAnalysis).sort(), Object.keys(pyAnalysis).sort());

const jsDca = serializeEnvelope(
  dcaAnalysis({
    security: inputs.security,
    prices: inputs.prices,
    fxRates: inputs.fx_rates,
    startDate: inputs.dca_request.start_date,
    endDate: inputs.dca_request.end_date,
    contributionSgd: inputs.dca_request.contribution_sgd,
    frequency: inputs.dca_request.frequency,
    scenario: inputs.dca_request.scenario,
    dividends: inputs.dividends,
    corporateActions: inputs.corporate_actions,
    taxRules: inputs.tax_rules,
  }),
);
const dcaErrors = [];
compareValues(jsDca, pyDca, 'dca', dcaErrors, ['xirr']);
check('DCA envelope matches Python (xirr within 1e-9, all else exact)', dcaErrors.length === 0, dcaErrors.join(' | '));
check('XIRR parity within 1e-9 of Python float bisection', Math.abs(Number(jsDca.xirr) - Number(pyDca.xirr)) < 1e-9, `${jsDca.xirr} vs ${pyDca.xirr}`);

const jsPortfolio = serializeEnvelope(
  analyzePortfolio({
    transactions: inputs.portfolio_request.transactions,
    securities: { [inputs.security.security_id]: inputs.security },
    prices: inputs.prices,
    fxRates: inputs.fx_rates,
    asOf: inputs.portfolio_request.as_of,
  }),
);
const portfolioErrors = [];
compareValues(jsPortfolio, pyPortfolio, 'portfolio', portfolioErrors);
check('portfolio envelope matches Python (decimal values equal; trailing-zero strings normalized)', portfolioErrors.length === 0, portfolioErrors.join(' | '));
checkEqual('portfolio top-level keys identical', Object.keys(jsPortfolio).sort(), Object.keys(pyPortfolio).sort());

console.log(`\n==== SELFTEST SUMMARY: PASS ${results.pass} / FAIL ${results.fail} ====${failures.length ? `\nFailures:\n${failures.map((f) => ` - ${f.name}`).join('\n')}` : ' all checks green'}`);
process.exitCode = results.fail === 0 ? 0 : 1;
