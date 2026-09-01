#!/usr/bin/env node
// Sprint 4 (S4.1/S4.5) Node integration proof:
//   data packs (fs-backed fetcher) → pack-loader → engine dcaAnalysis.
//
// This is the exact chain the browser static mode runs in submitDca →
// s4DcaViaPacks, minus the worker hop (the worker layer is separately proven
// by worker-selftest.mjs, and the engine call is identical after
// payloadToEngineArgs). engineClient is deliberately NOT used here.
//
// Cases:
//   1. real QQQ monthly 2024    vs parity golden qqq-2024-dca-monthly.json
//   2. real QQQ quarterly 2024  vs parity golden dca-qqq-2024-quarterly.json
//   3. real QQQ yearly 2024     vs parity golden dca-qqq-2024-yearly.json
//
// Assertions per case: total_contributed_sgd and contribution_dates must be
// EXACT string matches against the Python golden; xirr and
// xirr_foreign_currency within absolute 1e-9 (same policy as parity.mjs).
//
// Run: node frontend/engine/dca-packs-integration.mjs

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { Decimal, dcaAnalysis } from './index.js';
import { createPackLoader } from './pack-loader.js';

const FRONTEND_URL = new URL('../', import.meta.url);
const FIXTURES_URL = new URL('./parity/fixtures/', import.meta.url);
const START_DATE = '2024-01-02';
const END_DATE = '2024-12-31';
const XIRR_TOLERANCE = new Decimal('1e-9');

const results = { pass: 0, fail: 0 };
const failures = [];

function check(name, condition, detail) {
  if (condition) {
    results.pass += 1;
  } else {
    results.fail += 1;
    failures.push(name);
    console.log(`  FAIL ${name}${detail === undefined ? '' : ` :: ${detail}`}`);
  }
}

function checkEqual(name, actual, expected) {
  const a = typeof actual === 'object' && actual !== null ? JSON.stringify(actual) : String(actual);
  const e = typeof expected === 'object' && expected !== null ? JSON.stringify(expected) : String(expected);
  check(name, a === e, a === e ? undefined : `expected ${e}, got ${a}`);
}

function section(title) {
  console.log(`\n== ${title}`);
}

function loadGolden(name) {
  return JSON.parse(readFileSync(new URL(`${name}.json`, FIXTURES_URL), 'utf8')).golden_envelope;
}

// fs-backed fetcher: pack-loader URLs are <baseUrl>/<path> with the frozen
// loader's trailing-slash stripping, so baseUrl is the frontend/ directory.
const fetcher = async (url) => ({
  ok: true,
  json: async () => JSON.parse(readFileSync(fileURLToPath(url), 'utf8')),
});
const packs = createPackLoader({ baseUrl: FRONTEND_URL.href, fetcher });

section('pack resolution (manifest → support → inputs)');
const entry = await packs.findSecurity({ ticker: 'QQQ' });
check('manifest resolves the QQQ entry', Boolean(entry?.security_id), JSON.stringify(entry?.security_id ?? null));

const support = packs.supportFor(entry, START_DATE, END_DATE);
checkEqual('supportFor QQQ 2024-01-02…2024-12-31', support.status, 'fully_supported');

const inputs = await packs.loadSecurityInputs(entry, START_DATE, END_DATE);
checkEqual('pack price rows for 2024', String(inputs.prices.length), '252');
checkEqual('inputs attach support classification', inputs.support.status, 'fully_supported');
checkEqual('inputs carry the committed snapshot id', inputs.dataSnapshotId, 'sha256-2612cdfaf81fa2847369a9752b4dfa288bc5eec4ead26f2f377d985f9d342c5b');
checkEqual('inputs carry the US withholding rule', String(inputs.taxRules.length), '1');
checkEqual('fx rows are USD→SGD', inputs.fxRates[0]?.base_currency, 'USD');
checkEqual('pack dividend rows loaded', String(inputs.dividends.length), '4');

function runDca(frequency, contributionSgd) {
  return dcaAnalysis({
    security: inputs.security,
    prices: inputs.prices,
    fxRates: inputs.fxRates,
    dividends: inputs.dividends,
    corporateActions: inputs.corporateActions,
    taxRules: inputs.taxRules,
    startDate: START_DATE,
    endDate: END_DATE,
    contributionSgd,
    frequency,
  });
}

function checkAgainstGolden(name, result, golden) {
  checkEqual(`${name}: total_contributed_sgd exact string`, String(result.total_contributed_sgd), golden.total_contributed_sgd);
  checkEqual(`${name}: contribution_dates exact`, result.contribution_dates, golden.contribution_dates);
  for (const field of ['xirr', 'xirr_foreign_currency']) {
    const difference = new Decimal(String(result[field])).minus(new Decimal(golden[field])).abs();
    check(`${name}: ${field} within 1e-9`, difference.lte(XIRR_TOLERANCE), `|diff| ${difference}`);
  }
}

section('QQQ 2024 monthly vs Python golden');
const monthly = runDca('monthly', '1000');
checkAgainstGolden('monthly', monthly, loadGolden('qqq-2024-dca-monthly'));

section('QQQ 2024 quarterly vs Python golden');
const quarterly = runDca('quarterly', '1500');
checkAgainstGolden('quarterly', quarterly, loadGolden('dca-qqq-2024-quarterly'));

section('QQQ 2024 yearly vs Python golden');
const yearly = runDca('yearly', '6000');
checkAgainstGolden('yearly', yearly, loadGolden('dca-qqq-2024-yearly'));

section('schedule shape (first-available-trading-day rule)');
checkEqual('monthly schedule has 12 contributions', String(monthly.contribution_dates.length), '12');
checkEqual('quarterly schedule has 4 contributions', String(quarterly.contribution_dates.length), '4');
checkEqual('yearly schedule has 1 contribution', String(yearly.contribution_dates.length), '1');
checkEqual('yearly buys on the first trading day', yearly.contribution_dates[0], START_DATE);
checkEqual('quarterly opens on the first trading day', quarterly.contribution_dates[0], START_DATE);

section('support gate');
const beforeCoverage = packs.supportFor(entry, '1999-01-02', END_DATE);
checkEqual('range before first_year is unavailable', beforeCoverage.status, 'unavailable');
check(beforeCoverage.reason.includes('covered years'), 'unavailable reason names covered years', beforeCoverage.reason);
const afterCoverage = packs.supportFor(entry, START_DATE, '2027-06-30');
checkEqual('range after last_year is unavailable', afterCoverage.status, 'unavailable');

console.log(`\n==== DCA PACKS INTEGRATION: PASS ${results.pass} / FAIL ${results.fail} ====${failures.length ? `\nFailures:\n${failures.map((name) => ` - ${name}`).join('\n')}` : ' all checks green'}`);
process.exitCode = results.fail === 0 ? 0 : 1;
