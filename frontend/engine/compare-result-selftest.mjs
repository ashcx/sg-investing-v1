import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { analyzeSecurity } from './analysis.js';
import { comparisonRow, comparisonSummary, windowsEqual } from './compare-window.js';

const fixture = JSON.parse(readFileSync(new URL('../../tests/fixtures/redesign/sprint-12.json', import.meta.url)));
const calculated = [];
for (const test of fixture.cases) {
  const input = fixture.securities.find(s => s.security.ticker === test.ticker);
  const result = analyzeSecurity({ security: input.security, prices: input.prices,
    fxRates: input.fx_rates, startDate: test.start, endDate: test.end, initialSgd: '1000',
    scenario: test.scenario, dividends: input.dividends, taxRules: fixture.tax_rules });
  const expected = test.expected;
  assert.equal(String(result.investment.final_value_sgd), expected.final_value_sgd, test.name);
  assert.equal(String(result.returns.total_return), expected.total_return, test.name);
  assert.equal(String(result.returns.total_return_foreign_currency), expected.native_return, test.name);
  assert.deepEqual(result.period, { start_date: expected.start, end_date: expected.end });
  const row = comparisonRow({ securityId: input.security.security_id, ticker: test.ticker },
    { data_snapshot_id: 'fixed-s12', methodology_version: '1.0', result });
  assert.equal(row.state, 'ready');
  assert.equal(row.result, result);
  calculated.push(row);
  console.log(`PASS: independent ${test.name} amounts, FX, scenario and actual dates`);
}
assert.equal(comparisonSummary([calculated[0], calculated[3]]).equal, false, 'QQQ/VALL unequal histories/calendars');
assert.equal(comparisonSummary([calculated[0], calculated[1]]).equal, true, 'actual equal dates');
assert.equal(comparisonSummary([calculated[0]]).equal, false, 'one success is not equal-period comparison');
assert.equal(comparisonSummary([calculated[0], { state: 'failed' }]).equal, false, 'partial is not whole-selection equality');
assert.equal(comparisonSummary([{ ...calculated[0], snapshotId: null }, calculated[1]]).sameSource, false);
assert.equal(comparisonSummary([calculated[0], { ...calculated[1], snapshotId: 'different' }]).sameSource, false);
assert.equal(comparisonRow({ securityId: 'wrong' }, calculated[0].envelope).state, 'failed');
assert.equal(comparisonRow({ securityId: calculated[0].securityId }, { result: {} }).state, 'failed');
assert.equal(windowsEqual({}, {}), false);
const sharedRows = fixture.securities.slice(0, 2).map(input => comparisonRow({ securityId: input.security.security_id }, {
  data_snapshot_id: 'fixed-s12', methodology_version: '1.0',
  result: analyzeSecurity({ security: input.security, prices: input.prices, fxRates: input.fx_rates,
    startDate: '2024-02-01', endDate: '2024-05-01', initialSgd: '1000',
    scenario: { dividends_enabled: false } }),
}));
assert.equal(comparisonSummary(sharedRows).equal, true, 'QQQ/VALL explicit shared dates resolve equally');
assert.deepEqual(sharedRows.map(row => row.result.period), [
  { start_date: '2024-02-01', end_date: '2024-05-01' },
  { start_date: '2024-02-01', end_date: '2024-05-01' },
]);
console.log('PASS: distinct QQQ/VALL securities resolve to equal actual dates after explicit shared-window choice');
console.log('PASS: envelopes, missing/mismatched results, actual date equality, partial results and provenance');
