#!/usr/bin/env node
// Golden parity runner (Sprint 3, S3.1). Plain Node >= 18, no npm install.
//
// Runs every fixture under ./fixtures/ through the browser engine and
// deep-compares the result against the golden envelope produced by the
// authoritative Python engine (scripts/generate_parity_fixtures.py).
//
// Comparison policy:
// - Object keys, plain strings, dates, warnings and booleans must match EXACTLY.
// - Decimal values are compared numerically (Decimal equality), so trailing-zero
//   string differences ("3400.00" vs "3400") are tolerated.
// - DCA `xirr` / `xirr_foreign_currency` are compared within an absolute 1e-9
//   tolerance: Python runs float NPV bisection while the engine keeps Decimal
//   inputs (documented deviation, frontend/engine/README.md).
// - `returns.cagr` / `returns.cagr_foreign_currency` are presentation metrics
//   computed through float `pow()`, whose last ulp differs between libm
//   implementations (Python/glibc vs V8). They are compared within an absolute
//   1e-12 tolerance; all monetary/FX/quantity math stays exact.
// - Error fixtures expect the Python rejection mapped to its engine class
//   ("AnalysisDataError" -> AnalysisDataError, "ValueError" -> EngineValueError)
//   with the identical message.
//
// Exit status: 0 when every fixture passes, 1 otherwise.

import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  AnalysisDataError,
  Decimal,
  analyzePortfolio,
  analyzeSecurity,
  dcaAnalysis,
  EngineValueError,
} from '../index.js';

const FIXTURES_DIR = new URL('./fixtures/', import.meta.url);

const DECIMAL_RE = /^-?\d+(\.\d+)?([eE][+-]?\d+)?$/;
const XIRR_TOLERANCE = '1e-9';
const CAGR_TOLERANCE = '1e-12';

const ERROR_TYPE_MAP = {
  AnalysisDataError,
  ValueError: EngineValueError,
};

function serializeEnvelope(value) {
  return JSON.parse(
    JSON.stringify(value, (key, item) => (item instanceof Decimal ? item.toString() : item)),
  );
}

function runFixture(kind, input) {
  const { security, prices, fx_rates: fxRates, dividends, corporate_actions: corporateActions, tax_rules: taxRules, request } = input;
  if (kind === 'analysis') {
    return analyzeSecurity({
      security,
      prices,
      fxRates,
      startDate: request.start_date,
      endDate: request.end_date,
      initialSgd: request.initial_sgd,
      scenario: request.scenario,
      dividends,
      corporateActions,
      taxRules,
    });
  }
  if (kind === 'dca') {
    return dcaAnalysis({
      security,
      prices,
      fxRates,
      startDate: request.start_date,
      endDate: request.end_date,
      contributionSgd: request.contribution_sgd,
      frequency: request.frequency,
      scenario: request.scenario,
      dividends,
      corporateActions,
      taxRules,
    });
  }
  if (kind === 'portfolio') {
    const securities = Object.fromEntries(security.map((item) => [item.security_id, item]));
    return analyzePortfolio({
      transactions: request.transactions,
      securities,
      prices,
      fxRates,
      asOf: request.as_of,
    });
  }
  throw new Error(`Unknown fixture kind: ${kind}`);
}

function compareValues(actual, expected, path, errors) {
  if (Array.isArray(expected)) {
    if (!Array.isArray(actual)) {
      errors.push({ path, expected: 'array', actual: describe(actual) });
      return;
    }
    if (actual.length !== expected.length) {
      errors.push({ path, expected: `array[${expected.length}]`, actual: `array[${actual.length}]` });
      return;
    }
    for (let i = 0; i < expected.length; i += 1) {
      compareValues(actual[i], expected[i], `${path}[${i}]`, errors);
    }
    return;
  }
  if (expected !== null && typeof expected === 'object') {
    if (actual === null || typeof actual !== 'object' || Array.isArray(actual)) {
      errors.push({ path, expected: 'object', actual: describe(actual) });
      return;
    }
    const expectedKeys = Object.keys(expected).sort();
    const actualKeys = Object.keys(actual).sort();
    if (JSON.stringify(actualKeys) !== JSON.stringify(expectedKeys)) {
      const missing = expectedKeys.filter((key) => !actualKeys.includes(key));
      const extra = actualKeys.filter((key) => !expectedKeys.includes(key));
      errors.push({
        path,
        expected: `{keys}${missing.length ? ` missing ${JSON.stringify(missing)}` : ''}`,
        actual: `{keys}${extra.length ? ` extra ${JSON.stringify(extra)}` : ''}`,
      });
      return;
    }
    for (const key of expectedKeys) {
      compareValues(actual[key], expected[key], `${path}.${key}`, errors);
    }
    return;
  }
  const typeMatches = actual === null ? expected === null : typeof actual === typeof expected;
  if (!typeMatches) {
    errors.push({
      path,
      expected: `${expected === null ? 'null' : typeof expected} ${JSON.stringify(expected)}`,
      actual: `${actual === null ? 'null' : typeof actual} ${JSON.stringify(actual)}`,
    });
    return;
  }
  if (typeof expected === 'string' && DECIMAL_RE.test(expected) && DECIMAL_RE.test(actual)) {
    if (path.includes('xirr') || path.includes('.cagr')) {
      const tolerance = path.includes('xirr') ? XIRR_TOLERANCE : CAGR_TOLERANCE;
      const difference = new Decimal(actual).minus(new Decimal(expected)).abs();
      if (difference.gt(tolerance)) {
        errors.push({ path, expected, actual, note: `|diff| ${difference} > ${tolerance}` });
      }
      return;
    }
    if (!new Decimal(actual).eq(new Decimal(expected))) {
      errors.push({ path, expected, actual });
    }
    return;
  }
  if (actual !== expected) {
    errors.push({ path, expected: JSON.stringify(expected), actual: JSON.stringify(actual) });
  }
}

function describe(value) {
  if (value === null) return 'null';
  if (Array.isArray(value)) return 'array';
  return typeof value;
}

function compareError(actualError, expectedError) {
  const errors = [];
  if (actualError === null) {
    errors.push({ path: 'error', expected: expectedError.type, actual: 'no error thrown' });
    return errors;
  }
  const ExpectedClass = ERROR_TYPE_MAP[expectedError.type];
  if (!ExpectedClass || !(actualError instanceof ExpectedClass)) {
    errors.push({
      path: 'error.type',
      expected: expectedError.type,
      actual: actualError?.name ?? describe(actualError),
    });
  }
  if (String(actualError?.message) !== expectedError.message) {
    errors.push({
      path: 'error.message',
      expected: JSON.stringify(expectedError.message),
      actual: JSON.stringify(String(actualError?.message)),
    });
  }
  return errors;
}

function main() {
  const names = readdirSync(FIXTURES_DIR).filter((name) => name.endsWith('.json')).sort();
  if (names.length === 0) {
    console.error('parity: no fixtures found — run scripts/generate_parity_fixtures.py first');
    process.exitCode = 1;
    return;
  }

  const byCategory = new Map();
  let passed = 0;
  const failures = [];

  for (const name of names) {
    const fixture = JSON.parse(readFileSync(new URL(name, FIXTURES_DIR), 'utf8'));
    const category = fixture.category;
    const record = byCategory.get(category) ?? { pass: 0, total: 0 };
    record.total += 1;
    byCategory.set(category, record);

    let thrown = null;
    let actual = null;
    try {
      actual = serializeEnvelope(runFixture(fixture.kind, fixture.input_rows));
    } catch (error) {
      thrown = error;
    }

    const errors = [];
    if (fixture.golden_envelope.error) {
      errors.push(...compareError(thrown, fixture.golden_envelope.error));
    } else if (thrown) {
      errors.push({
        path: '(run)',
        expected: 'result envelope',
        actual: `${thrown.name}: ${thrown.message}`,
      });
    } else {
      compareValues(actual, fixture.golden_envelope, fixture.name, errors);
    }

    if (errors.length === 0) {
      passed += 1;
      record.pass += 1;
    } else {
      failures.push({ name: fixture.name, category, errors });
    }
  }

  for (const { name, errors } of failures) {
    console.log(`\nFAIL ${name}`);
    for (const error of errors) {
      const note = error.note ? ` (${error.note})` : '';
      console.log(`  ${error.path}\n    expected: ${error.expected}${note}\n    actual:   ${error.actual}`);
    }
  }

  console.log('\n==== PARITY RESULTS ====');
  const sortedCategories = [...byCategory.entries()].sort(([a], [b]) => (a < b ? -1 : 1));
  for (const [category, record] of sortedCategories) {
    console.log(`  ${category}: ${record.pass}/${record.total} pass`);
  }
  const total = [...byCategory.values()].reduce((sum, record) => sum + record.total, 0);
  console.log(`  TOTAL: ${passed}/${total} pass`);
  process.exitCode = passed === total ? 0 : 1;
}

main();
