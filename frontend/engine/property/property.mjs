// Sprint 3 / task S3.2 — property tests for the portable calculation engine.
//
// Dependency-free Node harness (node frontend/engine/property/property.mjs).
// Deterministic by construction: seeded mulberry32 PRNG, fixed seed list,
// no Math.random / Date.now / locale in output. Output is byte-identical
// across runs so it can be diffed.
//
// Seed strategy: each property owns a base seed drawn from BASE_SEEDS
// (property index mod list length); case i uses
// seed = (baseSeed + i * 0x9e3779b1) >>> 0, reported on failure as
// `property -> seed -> case` triple.

import { Decimal, ZERO, ONE, dec, sumDecimals, decString } from '../money.js';
import { addDays } from '../calendar.js';
import { DcaFrequency, contributionDates, dcaAnalysis, xirr } from '../dca.js';
import { applyActions, groupByEffectiveDate } from '../splits.js';
import { analyzePortfolio } from '../portfolio.js';
import { TransactionType } from '../models.js';
import { canonicalRequest, requestKey } from '../request-keys.js';

// ---------------------------------------------------------------------------
// Deterministic PRNG + generators
// ---------------------------------------------------------------------------

export const BASE_SEEDS = [0x5347_494e, 0x1234_5678, 0x0bad_c0de, 0x0d15_ea5e];

function mulberry32(seed) {
  let a = seed >>> 0;
  return function next() {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function caseSeed(baseSeed, caseIndex) {
  return (baseSeed + Math.imul(caseIndex + 1, 0x9e3779b1)) >>> 0;
}

function rngInt(rng, minInclusive, maxInclusive) {
  return minInclusive + Math.floor(rng() * (maxInclusive - minInclusive + 1));
}

function pick(rng, arr) {
  return arr[rngInt(rng, 0, arr.length - 1)];
}

function shuffled(rng, arr) {
  const copy = [...arr];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = rngInt(rng, 0, i);
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

// Random decimal string with a bounded digit budget (never via float math).
function randDecimalString(rng, { intDigits = 6, fracDigits = 6, signed = true } = {}) {
  const digits = (n) => {
    let s = '';
    for (let i = 0; i < n; i += 1) s += String(rngInt(rng, 0, 9));
    return s;
  };
  let out = digits(rngInt(rng, 1, intDigits));
  if (rng() < 0.7) out += '.' + digits(rngInt(rng, 1, fracDigits));
  if (signed && rng() < 0.4) out = '-' + out;
  return out;
}

// ---------------------------------------------------------------------------
// Harness
// ---------------------------------------------------------------------------

const groups = [];

function defineGroup(name, properties) {
  groups.push({ name, properties });
}

function property(name, caseCount, fn) {
  return { name, caseCount, fn };
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

let totalCases = 0;
let totalFailures = 0;

function runAll() {
  const lines = [];
  lines.push('== SG/Invest engine property tests (S3.2) ==');
  lines.push(`base seeds: ${BASE_SEEDS.map((s) => '0x' + s.toString(16)).join(', ')}`);
  for (const group of groups) {
    lines.push(`[${group.name}]`);
    for (const prop of group.properties) {
      const baseSeed = BASE_SEEDS[totalPropertiesIndex(group, prop) % BASE_SEEDS.length];
      let failures = 0;
      let firstFailure = null;
      for (let i = 0; i < prop.caseCount; i += 1) {
        const seed = caseSeed(baseSeed, i);
        try {
          prop.fn(mulberry32(seed), i, seed);
        } catch (error) {
          failures += 1;
          if (!firstFailure) {
            firstFailure = `  FAIL ${prop.name} seed=${seed} case=${i}: ${error.message}`;
          }
          break; // stop the property at its first failing case (deterministic)
        }
      }
      totalCases += prop.caseCount;
      if (failures) {
        totalFailures += 1;
        lines.push(firstFailure);
      } else {
        lines.push(`  ok   ${prop.name} cases=${prop.caseCount}`);
      }
    }
  }
  lines.push(
    `summary: groups=${groups.length} properties=${totalPropertyCount()} cases=${totalCases} ` +
      `failed-properties=${totalFailures} result=${totalFailures ? 'FAIL' : 'PASS'}`,
  );
  return lines.join('\n');
}

// Stable global (propertyIndex, groupIndex) numbering for seed assignment.
let propertyCounter = 0;
const propertyIndexByKey = new Map();
function totalPropertiesIndex(group, prop) {
  const key = group.name + '/' + prop.name;
  if (!propertyIndexByKey.has(key)) propertyIndexByKey.set(key, propertyCounter++);
  return propertyIndexByKey.get(key);
}
function totalPropertyCount() {
  return propertyCounter;
}

// ---------------------------------------------------------------------------
// Group (a) ROUNDING via money.js
// ---------------------------------------------------------------------------

defineGroup('rounding (money.js)', [
  property('quantize_idempotent', 100, (rng) => {
    const value = randDecimalString(rng, { intDigits: 12, fracDigits: 10 });
    const dp = rngInt(rng, 0, 8);
    const once = dec(value).toFixed(dp);
    const twice = dec(once).toFixed(dp);
    assert(once === twice, `quantize not idempotent: ${value} dp=${dp} -> ${once} -> ${twice}`);
    assert(
      dec(once).eq(dec(once).toDecimalPlaces(dp)),
      `re-quantized value drifted: ${value} dp=${dp}`,
    );
  }),

  property('half_even_sign_symmetry', 100, (rng) => {
    const dp = rngInt(rng, 0, 8);
    let value;
    if (rng() < 0.6) {
      // Guaranteed HALF_EVEN tie: digit dp+1 is 5, everything beyond is zero.
      value = randDecimalString(rng, { intDigits: 6, fracDigits: dp, signed: false });
      value = value.replace(/$/, (m) => m); // keep shape; append tie digit below
      value = (value.includes('.') ? value : value + '.') + '5';
    } else {
      value = randDecimalString(rng, { intDigits: 8, fracDigits: 8 });
    }
    const rounded = dec(value).toFixed(dp);
    const negRounded = dec(value).neg().toFixed(dp);
    assert(
      dec(rounded).neg().eq(dec(negRounded)),
      `round(-x) != -round(x): x=${value} dp=${dp} round=${rounded} round(-x)=${negRounded}`,
    );
  }),

  property('half_even_known_tie_vectors', 12, (rng) => {
    const vectors = [
      ['0.125', 2, '0.12'], // tie -> even digit 2
      ['0.135', 2, '0.14'], // tie -> even digit 4
      ['0.145', 2, '0.14'],
      ['2.5', 0, '2'],
      ['3.5', 0, '4'],
      ['-2.5', 0, '-2'],
      ['1.005', 2, '1.00'],
      ['-1.005', 2, '-1.00'],
      ['0.15', 1, '0.2'],
      ['0.05', 1, '0.0'],
      ['-0.05', 1, '-0.0'],
      ['2.675', 2, '2.68'],
    ];
    for (const [value, dp, expected] of vectors) {
      const got = dec(value).toFixed(dp);
      assert(
        got === expected,
        `HALF_EVEN vector mismatch: ${value} @${dp} -> ${got}, expected ${expected}`,
      );
    }
    void rng;
  }),

  property('decimal_sum_traps_exact', 100, (rng) => {
    // Classic binary-float traps stay exact in Decimal.
    assert(decString(sumDecimals(Array(10).fill('0.1'))) === '1', '0.1 x10 != 1');
    assert(decString(dec('0.1').plus('0.2')) === '0.3', '0.1 + 0.2 != 0.3');
    // Repeated addition of a random value equals exact multiplication.
    const a = randDecimalString(rng, { intDigits: 10, fracDigits: 8 });
    const n = rngInt(rng, 1, 100);
    const summed = sumDecimals(Array(n).fill(a));
    const multiplied = dec(a).times(n);
    assert(
      summed.eq(multiplied) && decString(summed) === decString(multiplied),
      `repeated sum != product: a=${a} n=${n} sum=${decString(summed)} mul=${decString(multiplied)}`,
    );
    // Order invariance for exact-representable sums (digit budget < precision 28).
    const values = Array.from({ length: rngInt(rng, 5, 20) }, () =>
      randDecimalString(rng, { intDigits: 6, fracDigits: 6 }),
    );
    const base = sumDecimals(values);
    const permuted = sumDecimals(shuffled(rng, values));
    assert(
      base.eq(permuted) && decString(base) === decString(permuted),
      `sum order-dependent: base=${decString(base)} permuted=${decString(permuted)}`,
    );
  }),

  property('dec_decstring_roundtrip', 100, (rng) => {
    const asString = randDecimalString(rng, { intDigits: 14, fracDigits: 12 });
    // string -> dec -> decString -> dec stays numerically identical
    const d = dec(asString);
    const s = decString(d);
    assert(dec(s).eq(d), `string round-trip drifted: ${asString} -> ${s}`);
    assert(decString(dec(s)) === s, `decString not stable: ${asString} -> ${s} -> ${decString(dec(s))}`);
    // Decimal instances pass through dec() unchanged (identity).
    assert(dec(d) === d, 'dec(Decimal) did not return the same instance');
    // Number path goes through String(number) and stays exact for short decimals.
    const num = rngInt(rng, -1000000, 1000000) / 8; // exact binary fraction -> short repr
    assert(
      dec(num).eq(new Decimal(String(num))),
      `number path mismatch: ${num} -> ${decString(dec(num))} vs ${new Decimal(String(num)).toString()}`,
    );
    // null/undefined coerce to zero.
    assert(decString(dec(null)) === '0' && decString(dec(undefined)) === '0', 'null/undefined != 0');
    // ZERO/ONE constants hold their identity values.
    assert(ZERO.isZero() && ONE.eq(1), 'ZERO/ONE constants corrupted');
  }),
]);

// ---------------------------------------------------------------------------
// Shared synthetic market builder (groups b and d)
// ---------------------------------------------------------------------------

// Weekday calendar over [start-14d, end+14d] minus random holidays, so both
// `previous_trading_day` and `next_trading_day` rules always resolve.
function tradingDays(rng, startDate, endDate) {
  const first = addDays(startDate, -14);
  const last = addDays(endDate, 14);
  const days = [];
  for (let d = first; d <= last; d = addDays(d, 1)) {
    // addDays civil arithmetic: weekday = (daysFromCivil + 4) mod 7, 0=Sunday.
    const y = Number(d.slice(0, 4));
    const m = Number(d.slice(5, 7));
    const dd = Number(d.slice(8, 10));
    const dow = (Math.floor((Date.UTC(y, m - 1, dd) / 86400000)) + 4) % 7;
    if (dow >= 1 && dow <= 4 + (rng() < 0.95 ? 1 : 0)) days.push(d);
  }
  return days.filter((d) => (rng() < 0.12 ? false : true));
}

function randDate(rng, yearFrom = 2015, yearTo = 2024) {
  const y = rngInt(rng, yearFrom, yearTo);
  const m = String(rngInt(rng, 1, 12)).padStart(2, '0');
  const d = String(rngInt(rng, 1, 28)).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function randPrice(rng) {
  return (rngInt(rng, 1000, 50000) / 100).toFixed(2);
}

function buildMarket(rng, { securities = ['SEC1'] } = {}) {
  const startDate = randDate(rng);
  const endDate = addDays(startDate, rngInt(rng, 20, 900));
  const days = tradingDays(rng, startDate, endDate);
  const prices = [];
  const fxRates = [];
  for (const day of days) {
    for (const securityId of securities) {
      const currency = securityId === 'SEC2' ? 'SGD' : 'USD';
      prices.push({
        security_id: securityId,
        trading_date: day,
        close: (rngInt(rng, 500, 50000) / 100).toFixed(2),
        currency,
      });
    }
    fxRates.push({
      base_currency: 'USD',
      rate_date: day,
      rate_to_sgd: (rngInt(rng, 11000, 16000) / 10000).toFixed(4),
    });
  }
  prices.sort((a, b) => (a.trading_date < b.trading_date ? -1 : a.trading_date > b.trading_date ? 1 : 0));
  return {
    startDate,
    endDate,
    tradingDays: days,
    prices,
    fxRates,
    security: (id) => ({
      security_id: id,
      ticker: id === 'SEC2' ? 'SGXTEST' : 'TEST',
      currency: id === 'SEC2' ? 'SGD' : 'USD',
      distribution_policy: 'distributing',
    }),
  };
}

// Mirror of the engine's DCA period keys (kept in sync deliberately; the
// property asserts against this independent reimplementation).
function periodKey(value, frequency) {
  if (frequency === DcaFrequency.MONTHLY) return `${value.slice(0, 4)}-M${Number(value.slice(5, 7))}`;
  if (frequency === DcaFrequency.QUARTERLY) {
    const quarter = Math.floor((Number(value.slice(5, 7)) - 1) / 3) + 1;
    return `${value.slice(0, 4)}-Q${quarter}`;
  }
  return value.slice(0, 4);
}

function expectedContributionDates(tradingDaysSorted, startDate, endDate, frequency) {
  const selected = new Map();
  for (const day of tradingDaysSorted) {
    if (startDate <= day && day <= endDate) {
      const key = periodKey(day, frequency);
      if (!selected.has(key)) selected.set(key, day);
    }
  }
  return [...selected.values()];
}

// ---------------------------------------------------------------------------
// Group (b) CONTRIBUTION SCALING via dca.js
// ---------------------------------------------------------------------------

const FREQUENCIES = [DcaFrequency.MONTHLY, DcaFrequency.QUARTERLY, DcaFrequency.YEARLY];

defineGroup('contribution scaling (dca.js)', [
  property('contribution_dates_first_available_trading_day', 60, (rng) => {
    const market = buildMarket(rng);
    const frequency = pick(rng, FREQUENCIES);
    const days = market.tradingDays; // already sorted ascending
    const got = contributionDates(market.prices, market.startDate, market.endDate, frequency);
    const expected = expectedContributionDates(days, market.startDate, market.endDate, frequency);
    const tradingSet = new Set(days);
    for (const date of got) {
      assert(
        tradingSet.has(date),
        `contribution date is not a trading day: ${date} (${market.startDate}..${market.endDate} ${frequency})`,
      );
      assert(
        market.startDate <= date && date <= market.endDate,
        `contribution date outside range: ${date}`,
      );
    }
    for (let i = 1; i < got.length; i += 1) {
      assert(got[i - 1] < got[i], `contribution dates not strictly ascending: ${got}`);
    }
    assert(
      got.length === expected.length && got.every((d, i) => d === expected[i]),
      `first-available-trading-day rule violated:\n  got=${JSON.stringify(got)}\n  expected=${JSON.stringify(expected)}`,
    );
  }),

  property('contribution_count_matches_frequency', 60, (rng) => {
    const market = buildMarket(rng);
    const frequency = pick(rng, FREQUENCIES);
    const got = contributionDates(market.prices, market.startDate, market.endDate, frequency);
    const keys = new Set(
      market.tradingDays
        .filter((d) => market.startDate <= d && d <= market.endDate)
        .map((d) => periodKey(d, frequency)),
    );
    assert(
      got.length === keys.size,
      `count != distinct periods: dates=${got.length} periods=${keys.size} (${frequency})`,
    );
    // Every period with at least one trading day appears exactly once.
    assert(new Set(got).size === got.length, 'duplicate contribution dates');
  }),

  property('total_invested_sum_string_exact', 60, (rng) => {
    const market = buildMarket(rng);
    const frequency = pick(rng, FREQUENCIES);
    const contribution = (rngInt(rng, 100, 100000) / 100).toFixed(2);
    const result = dcaAnalysis({
      security: market.security('SEC1'),
      prices: market.prices,
      fxRates: market.fxRates,
      startDate: market.startDate,
      endDate: market.endDate,
      contributionSgd: contribution,
      frequency,
    });
    const dates = result.contribution_dates;
    const expectedDates = contributionDates(
      market.prices,
      market.startDate,
      market.endDate,
      frequency,
    );
    assert(
      JSON.stringify(dates) === JSON.stringify(expectedDates),
      'dcaAnalysis contribution dates differ from contributionDates()',
    );
    const n = dates.length;
    const repeatedSum = sumDecimals(Array(n).fill(contribution));
    const scaled = dec(contribution).times(n);
    assert(
      decString(result.total_contributed_sgd) === decString(repeatedSum) &&
        decString(repeatedSum) === decString(scaled),
      `total invested not string-exact: engine=${decString(result.total_contributed_sgd)} ` +
        `sum=${decString(repeatedSum)} scaled=${decString(scaled)}`,
    );
    assert(dec(contribution).gt(0) && n >= 1, 'degenerate DCA case generated');
  }),
]);

// ---------------------------------------------------------------------------
// Group (c) SPLIT HANDLING via splits.js
// ---------------------------------------------------------------------------

// Ratios whose reciprocal 1/r is exactly representable in 28 significant
// digits (2^a * 5^b), so `apply ratio then inverse` is exactly invertible.
const SPLIT_RATIOS_EXACT_INVERSE = ['0.04', '0.05', '0.1', '0.125', '0.2', '0.25', '0.5', '2', '4', '5', '8', '10', '20', '25', '50'];
// Arbitrary positive ratios with bounded digits (products stay < 28 digits).
function randRatio(rng, maxDigits = 8) {
  let r = randDecimalString(rng, { intDigits: 3, fracDigits: maxDigits, signed: false });
  // keep strictly positive and away from pathological scales
  if (dec(r).lte(0) || dec(r).gt(1000)) r = '2';
  return r;
}

defineGroup('split handling (splits.js)', [
  property('apply_ratio_is_exact_multiplication', 80, (rng) => {
    const sharesBefore = randDecimalString(rng, { intDigits: 10, fracDigits: 6 });
    const ratio = randRatio(rng);
    const actions = [{ security_id: 'SEC1', effective_date: '2024-03-01', action_type: 'split', ratio }];
    const sharesAfter = applyActions(dec(sharesBefore), actions);
    const expected = dec(sharesBefore).times(dec(ratio));
    assert(
      sharesAfter.eq(expected) && decString(sharesAfter) === decString(expected),
      `shares_after != shares_before * ratio: ${sharesBefore} * ${ratio} -> ${decString(sharesAfter)} vs ${decString(expected)}`,
    );
    // Multi-action: every action is applied, in order.
    const ratios = Array.from({ length: rngInt(rng, 1, 4) }, () => randRatio(rng, 4));
    const multi = ratios.map((r, i) => ({
      security_id: 'SEC1',
      effective_date: `2024-03-0${(i % 9) + 1}`,
      action_type: 'split',
      ratio: r,
    }));
    const gotMulti = applyActions(dec(sharesBefore), multi);
    let expectedMulti = dec(sharesBefore);
    for (const r of ratios) expectedMulti = expectedMulti.times(dec(r));
    assert(
      gotMulti.eq(expectedMulti) && decString(gotMulti) === decString(expectedMulti),
      `multi-action application diverged: ${sharesBefore} x [${ratios}] -> ${decString(gotMulti)} vs ${decString(expectedMulti)}`,
    );
  }),

  property('split_preserves_total_cost_per_share_scales_inverse', 80, (rng) => {
    // Model: cost basis C is untouched by a split; shares scale by r; the
    // weighted-average per-share cost must scale by exactly 1/r.
    const avgBefore = randDecimalString(rng, { intDigits: 8, fracDigits: 4, signed: false });
    const sharesBefore = pick(rng, ['8', '16', '20', '25', '40', '50', '125', '1000']); // 2^a*5^b: C/S exact
    const costBasis = dec(avgBefore).times(dec(sharesBefore)).toFixed(12);
    const ratio = pick(rng, ['2', '4', '5', '8', '10', '20']);
    const sharesAfter = applyActions(dec(sharesBefore), [
      { security_id: 'SEC1', effective_date: '2024-03-01', action_type: 'split', ratio },
    ]);
    const perShareBefore = dec(costBasis).div(dec(sharesBefore));
    const perShareAfter = dec(costBasis).div(sharesAfter);
    assert(
      perShareAfter.eq(perShareBefore.div(dec(ratio))) &&
        decString(perShareAfter) === decString(perShareBefore.div(dec(ratio))),
      `per-share cost did not scale inversely: C=${costBasis} S=${sharesBefore} r=${ratio} ` +
        `after=${decString(perShareAfter)} expected=${decString(perShareBefore.div(dec(ratio)))}`,
    );
    // Total invested value is preserved: shares_after * per_share_after == C.
    const totalAfter = sharesAfter.times(perShareAfter);
    assert(
      totalAfter.eq(dec(costBasis)),
      `total cost not preserved: ${decString(totalAfter)} != ${costBasis}`,
    );
  }),

  property('ratio_then_inverse_returns_original_shares', 80, (rng) => {
    const sharesBefore = randDecimalString(rng, { intDigits: 10, fracDigits: 6 });
    const ratio = pick(rng, SPLIT_RATIOS_EXACT_INVERSE);
    const inverse = ONE.div(dec(ratio)).toString();
    const forward = { security_id: 'SEC1', effective_date: '2024-03-01', action_type: 'split', ratio };
    const back = { security_id: 'SEC1', effective_date: '2024-03-02', action_type: 'reverse_split', ratio: inverse };
    const afterRoundtrip = applyActions(applyActions(dec(sharesBefore), [forward]), [back]);
    assert(
      afterRoundtrip.eq(dec(sharesBefore)) && decString(afterRoundtrip) === decString(dec(sharesBefore)),
      `ratio/inverse round-trip lost shares: ${sharesBefore} x ${ratio} x ${inverse} -> ${decString(afterRoundtrip)}`,
    );
    // Reverse order (inverse first, then ratio) is also the identity.
    const afterReverse = applyActions(applyActions(dec(sharesBefore), [back]), [forward]);
    assert(afterReverse.eq(dec(sharesBefore)), `inverse/ratio round-trip lost shares: ${sharesBefore}`);
  }),

  property('group_by_effective_date_is_shuffle_invariant', 40, (rng) => {
    const actions = Array.from({ length: rngInt(rng, 2, 12) }, (_, i) => ({
      security_id: 'SEC1',
      effective_date: randDate(rng),
      action_type: 'split',
      ratio: randRatio(rng, 4),
      source_id: `A${i}`,
    }));
    const grouped = groupByEffectiveDate(actions);
    const reshuffled = groupByEffectiveDate(shuffled(rng, actions));
    const datesA = [...grouped.keys()].sort();
    const datesB = [...reshuffled.keys()].sort();
    assert(
      JSON.stringify(datesA) === JSON.stringify(datesB),
      `groupByEffectiveDate keys differ across shuffles: ${datesA} vs ${datesB}`,
    );
    for (const date of datesA) {
      const ratiosA = grouped.get(date).map((a) => decString(dec(a.ratio))).sort();
      const ratiosB = reshuffled.get(date).map((a) => decString(dec(a.ratio))).sort();
      assert(
        JSON.stringify(ratiosA) === JSON.stringify(ratiosB),
        `per-date ratios differ across shuffles for ${date}`,
      );
    }
    // Applying grouped actions date-by-date equals applying the flat
    // date-sorted list (within exact digit budgets).
    const sharesBefore = randDecimalString(rng, { intDigits: 8, fracDigits: 4 });
    let fromGroups = dec(sharesBefore);
    for (const date of datesA) fromGroups = applyActions(fromGroups, grouped.get(date));
    let flat = dec(sharesBefore);
    for (const action of [...actions].sort((a, b) => (a.effective_date < b.effective_date ? -1 : 1))) {
      flat = applyActions(flat, [action]);
    }
    assert(
      fromGroups.eq(flat) && decString(fromGroups) === decString(flat),
      `grouped vs flat application diverged: ${decString(fromGroups)} vs ${decString(flat)}`,
    );
  }),
]);

// ---------------------------------------------------------------------------
// Group (d) CASH-FLOW ORDERING via portfolio.js / dca.js xirr
// ---------------------------------------------------------------------------

// Decimal-aware serializer: every engine output Decimal becomes its canonical
// string so results can be deep-compared via canonicalRequest (sorted keys).
function serializeEngineValue(value) {
  if (value instanceof Decimal) return decString(value);
  if (Array.isArray(value)) return value.map(serializeEngineValue);
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, child]) => [key, serializeEngineValue(child)]),
    );
  }
  return value;
}

// The engine's canonical transaction order (portfolio.js): date ascending,
// ties broken by ascending String(transaction_id).
function canonicalTxOrder(txs) {
  return [...txs].sort((a, b) => {
    if (a.transaction_date !== b.transaction_date) {
      return a.transaction_date < b.transaction_date ? -1 : 1;
    }
    return String(a.transaction_id) < String(b.transaction_id) ? -1 : 1;
  });
}

// Random but *valid* transaction stream: simulation runs in canonical order
// and drops any SELL the weighted-average ledger could not satisfy, so every
// permutation of the returned array must produce identical engine output.
function generateTransactions(rng, market) {
  const count = rngInt(rng, 2, 14);
  const inRangeDays = market.tradingDays.filter(
    (d) => market.startDate <= d && d <= market.endDate,
  );
  const ids = shuffled(
    rng,
    Array.from({ length: count }, (_, i) => 'TX-' + String(i).padStart(4, '0')),
  );
  const ops = [];
  for (let i = 0; i < count; i += 1) {
    const securityId = pick(rng, ['SEC1', 'SEC2']);
    const currency = securityId === 'SEC2' ? 'SGD' : 'USD';
    const txDate = pick(rng, inRangeDays);
    const type = pick(rng, [
      TransactionType.BUY,
      TransactionType.BUY,
      TransactionType.SELL,
      TransactionType.DIVIDEND,
      TransactionType.CASH_DEPOSIT,
      TransactionType.CASH_WITHDRAWAL,
    ]);
    const base = { transaction_id: ids[i], transaction_date: txDate };
    if (type === TransactionType.BUY) {
      ops.push({
        ...base,
        security_id: securityId,
        transaction_type: type,
        currency,
        quantity: String(rngInt(rng, 1, 50)),
        cash_amount: (rngInt(rng, 5000, 5000000) / 100).toFixed(2),
        fees: (rngInt(rng, 0, 2000) / 100).toFixed(2),
      });
    } else if (type === TransactionType.SELL) {
      ops.push({
        ...base,
        security_id: securityId,
        transaction_type: type,
        currency,
        quantity: String(rngInt(rng, 1, 30)),
        cash_amount: (rngInt(rng, 5000, 5000000) / 100).toFixed(2),
        fees: (rngInt(rng, 0, 2000) / 100).toFixed(2),
      });
    } else if (type === TransactionType.DIVIDEND) {
      ops.push({
        ...base,
        security_id: securityId,
        transaction_type: type,
        currency,
        cash_amount: (rngInt(rng, 100, 50000) / 100).toFixed(2),
        fees: (rngInt(rng, 0, 500) / 100).toFixed(2),
      });
    } else {
      ops.push({
        ...base,
        transaction_type: type,
        currency: pick(rng, ['SGD', 'USD']),
        cash_amount: (rngInt(rng, 10000, 5000000) / 100).toFixed(2),
        fees: '0.00',
      });
    }
  }
  // Drop sells that exceed holdings in canonical processing order.
  const held = new Map();
  const valid = [];
  for (const tx of canonicalTxOrder(ops)) {
    if (tx.transaction_type === TransactionType.SELL) {
      const current = held.get(tx.security_id) ?? ZERO;
      if (dec(tx.quantity).gt(current)) continue;
      held.set(tx.security_id, current.minus(dec(tx.quantity)));
    } else if (tx.transaction_type === TransactionType.BUY) {
      held.set(tx.security_id, (held.get(tx.security_id) ?? ZERO).plus(dec(tx.quantity)));
    }
    valid.push(tx);
  }
  return valid;
}

defineGroup('cash-flow ordering (portfolio.js / xirr)', [
  property('portfolio_shuffle_invariance', 40, (rng) => {
    const market = buildMarket(rng, { securities: ['SEC1', 'SEC2'] });
    const transactions = generateTransactions(rng, market);
    const securities = { SEC1: market.security('SEC1'), SEC2: market.security('SEC2') };
    const input = { transactions, securities, prices: market.prices, fxRates: market.fxRates, asOf: market.endDate };
    const baseline = analyzePortfolio(input);
    const baselineTwice = analyzePortfolio(input);
    const baselineCanon = canonicalRequest(serializeEngineValue(baseline));
    assert(
      canonicalRequest(serializeEngineValue(baselineTwice)) === baselineCanon,
      'analyzePortfolio not deterministic on identical input',
    );
    for (let k = 0; k < 6; k += 1) {
      const permuted = analyzePortfolio({ ...input, transactions: shuffled(rng, transactions) });
      const permutedCanon = canonicalRequest(serializeEngineValue(permuted));
      assert(
        permutedCanon === baselineCanon,
        `shuffled transaction order changed the portfolio result (shuffle #${k + 1}, ` +
          `${transactions.length} txs, ${market.startDate}..${market.endDate})`,
      );
    }
  }),

  property('xirr_order_invariance', 60, (rng) => {
    const count = rngInt(rng, 4, 8);
    let date = randDate(rng);
    const flows = [[date, dec('-' + (rngInt(rng, 100000, 10000000) / 100).toFixed(2))]];
    for (let i = 1; i < count; i += 1) {
      date = addDays(date, rngInt(rng, 30, 400));
      flows.push([date, dec((rngInt(rng, 10000, 5000000) / 100).toFixed(2))]);
    }
    const sorted = xirr(flows);
    const permuted = xirr(shuffled(rng, flows));
    if (sorted === null) {
      assert(permuted === null, `xirr null-ness depends on order: sorted=null shuffled=${String(permuted)}`);
      return;
    }
    assert(permuted !== null, 'xirr null-ness depends on order');
    assert(
      sorted.eq(permuted) && decString(sorted) === decString(permuted),
      `xirr depends on cash-flow order: ${decString(sorted)} vs ${decString(permuted)}`,
    );
  }),

  property('equal_date_tiebreak_is_ascending_transaction_id', 1, (rng) => {
    // Observed tie-break: for equal transaction_date the engine processes
    // transactions in ascending String(transaction_id) order. We pin that
    // with a case where processing order changes realized P&L.
    const prices = [
      ['2024-01-02', '10.00'], ['2024-01-03', '10.00'], ['2024-01-04', '10.00'], ['2024-01-05', '10.00'],
    ].map(([trading_date, close]) => ({ security_id: 'SEC2', trading_date, close, currency: 'SGD' }));
    const securities = { SEC2: { security_id: 'SEC2', ticker: 'SGXTEST', currency: 'SGD' } };
    const asOf = '2024-01-05';
    const deposit = { transaction_id: 'T0', transaction_date: '2024-01-02', transaction_type: 'CASH_DEPOSIT', currency: 'SGD', cash_amount: '10000.00', fees: '0.00' };
    const initialBuy = { transaction_id: 'T1', transaction_date: '2024-01-03', security_id: 'SEC2', transaction_type: 'BUY', currency: 'SGD', quantity: '10', cash_amount: '100.00', fees: '0.00' };

    // Case A: BUY id sorts first -> BUY processed before SELL.
    const txsA = [
      deposit,
      initialBuy,
      { transaction_id: 'AAA-BUY', transaction_date: '2024-01-04', security_id: 'SEC2', transaction_type: 'BUY', currency: 'SGD', quantity: '5', cash_amount: '50.00', fees: '1.00' },
      { transaction_id: 'BBB-SELL', transaction_date: '2024-01-04', security_id: 'SEC2', transaction_type: 'SELL', currency: 'SGD', quantity: '5', cash_amount: '100.00', fees: '0.00' },
    ];
    // Replica of engine arithmetic in the buy-first order.
    let qty = dec('10');
    let cost = dec('100');
    qty = qty.plus(dec('5'));
    cost = cost.plus(dec('50')).plus(dec('1'));
    const avgA = cost.div(qty);
    const realizedA = dec('100').minus(dec('0')).minus(avgA.times(dec('5')));
    const costLeftA = cost.minus(avgA.times(dec('5')));

    const resultA = analyzePortfolio({ transactions: shuffled(rng, txsA), securities, prices, fxRates: [], asOf });
    const snapshotA = resultA.holdings[0];
    assert(
      snapshotA.realized_pl_native.eq(realizedA),
      `tie-break: expected buy-first realized ${decString(realizedA)}, got ${decString(snapshotA.realized_pl_native)}`,
    );
    assert(snapshotA.quantity.eq(dec('10')) && snapshotA.cost_basis_native.eq(costLeftA),
      'buy-first ledger quantities diverged');
    assert(
      !snapshotA.realized_pl_native.eq(dec('50')),
      'tie-break unexpectedly behaved sell-first',
    );
    assert(
      decString(resultA.cash_by_currency.SGD) === decString(dec('10000').minus(cost).plus(dec('100'))),
      'cash ledger diverged under tie-break A',
    );

    // Case B: ids swapped -> SELL id sorts first -> SELL processed before BUY.
    const txsB = [
      deposit,
      initialBuy,
      { transaction_id: 'ZZZ-BUY', transaction_date: '2024-01-04', security_id: 'SEC2', transaction_type: 'BUY', currency: 'SGD', quantity: '5', cash_amount: '50.00', fees: '1.00' },
      { transaction_id: 'AAA-SELL', transaction_date: '2024-01-04', security_id: 'SEC2', transaction_type: 'SELL', currency: 'SGD', quantity: '5', cash_amount: '100.00', fees: '0.00' },
    ];
    const resultB = analyzePortfolio({ transactions: shuffled(rng, txsB), securities, prices, fxRates: [], asOf });
    const snapshotB = resultB.holdings[0];
    assert(
      snapshotB.realized_pl_native.eq(dec('50')),
      `tie-break B: expected sell-first realized 50, got ${decString(snapshotB.realized_pl_native)}`,
    );
    assert(
      snapshotB.quantity.eq(dec('10')) && snapshotB.cost_basis_native.eq(dec('101')),
      `tie-break B ledger diverged: qty=${decString(snapshotB.quantity)} cost=${decString(snapshotB.cost_basis_native)}`,
    );
  }),
]);

// ---------------------------------------------------------------------------
// Group (e) REQUEST KEYS via request-keys.js
// ---------------------------------------------------------------------------

// Random nested JSON request. Object keys drawn from a pool, leaf values are
// decimal-safe strings, integers, booleans or null (the engine contract keeps
// money as strings; numbers here are non-financial and JSON-deterministic).
function randRequest(rng, depth = 0) {
  const keyNames = ['security_id', 'start_date', 'end_date', 'contribution_sgd', 'frequency', 'as_of', 'currency', 'ticker', 'scenario'];
  const node = {};
  const keyCount = rngInt(rng, 1, 6);
  for (let i = 0; i < keyCount; i += 1) {
    const key = rng() < 0.7 ? pick(rng, keyNames) : `k${rngInt(rng, 0, 99)}`;
    node[key] = randRequestValue(rng, depth);
  }
  return node;
}

function randRequestValue(rng, depth) {
  const roll = rng();
  if (depth < 2 && roll < 0.3) return randRequest(rng, depth + 1);
  if (depth < 2 && roll < 0.42) {
    return Array.from({ length: rngInt(rng, 0, 4) }, () => randRequestValue(rng, depth + 1));
  }
  if (roll < 0.62) {
    return rng() < 0.5
      ? (rngInt(rng, -100000, 1000000) / 100).toFixed(randIntOrTwo(rng))
      : randDate(rng);
  }
  if (roll < 0.78) return String(rngInt(rng, 0, 1000000));
  if (roll < 0.9) return rng() < 0.5;
  return rng() < 0.5 ? null : pick(rng, ['monthly', 'quarterly', 'yearly']);
}

function randIntOrTwo(rng) {
  return rng() < 0.5 ? 0 : 2;
}

// Deep copy with object key insertion order randomly permuted (arrays keep
// their order: element order is semantic in JSON).
function shuffleKeysDeep(rng, value) {
  if (Array.isArray(value)) return value.map((child) => shuffleKeysDeep(rng, child));
  if (value !== null && typeof value === 'object') {
    const out = {};
    for (const key of shuffled(rng, Object.keys(value))) out[key] = shuffleKeysDeep(rng, value[key]);
    return out;
  }
  return value;
}

// Independent FNV-1a 64 reimplementation (from the FNV spec, not a copy of
// request-keys.js) used as a cross-check of the engine's hash.
function fnv1a64Reference(text) {
  let hash = 0xcbf29ce484222325n;
  const prime = 0x100000001b3n;
  const mask = (1n << 64n) - 1n;
  for (const ch of text) {
    hash ^= BigInt(ch.codePointAt(0));
    hash = (hash * prime) & mask;
  }
  return hash.toString(16).padStart(16, '0');
}

// Order-insensitive structural deep equality for JSON.parse results.
function jsonDeepEqual(a, b) {
  if (a === b) return true;
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((child, i) => jsonDeepEqual(child, b[i]));
  }
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (a !== null && b !== null && typeof a === 'object' && typeof b === 'object') {
    const keysA = Object.keys(a).sort();
    const keysB = Object.keys(b).sort();
    if (JSON.stringify(keysA) !== JSON.stringify(keysB)) return false;
    return keysA.every((key) => jsonDeepEqual(a[key], b[key]));
  }
  return false;
}

defineGroup('request keys (request-keys.js)', [
  property('key_order_invariance', 150, (rng) => {
    const request = randRequest(rng);
    const baseKey = canonicalRequest(request);
    const permutations = 8; // 150 cases x 8 = 1200 key-order permutations
    for (let k = 0; k < permutations; k += 1) {
      const permuted = shuffleKeysDeep(rng, request);
      const permutedCanon = canonicalRequest(permuted);
      assert(
        permutedCanon === baseKey,
        `canonicalRequest depends on key order: base=${baseKey} permuted=${permutedCanon}`,
      );
      const keyA = requestKey('analysis', request);
      const keyB = requestKey('analysis', permuted);
      assert(keyA === keyB, `requestKey depends on key order: ${keyA} vs ${keyB}`);
    }
  }),

  property('different_scopes_never_collide', 100, (rng) => {
    const request = randRequest(rng);
    const scopes = shuffled(rng, ['analysis', 'dca', 'portfolio', 'worker-cache']).slice(0, rngInt(rng, 2, 4));
    const keys = scopes.map((scope) => requestKey(scope, request));
    for (let i = 0; i < keys.length; i += 1) {
      assert(
        keys[i].startsWith(scopes[i] + ':'),
        `key missing scope prefix: ${keys[i]} (scope ${scopes[i]})`,
      );
      for (let j = i + 1; j < keys.length; j += 1) {
        assert(keys[i] !== keys[j], `scope collision: ${keys[i]} == ${keys[j]}`);
      }
    }
    // The hash body is scope-independent; the scope prefix is the namespace.
    const suffixes = keys.map((key) => key.slice(key.indexOf(':') + 1));
    assert(
      suffixes.every((s) => s === suffixes[0]),
      `hash body differs across scopes: ${suffixes}`,
    );
    assert(new Set(keys).size === keys.length, 'full keys collided across scopes');
  }),

  property('stable_across_runs_and_fnv_reference', 100, (rng) => {
    const request = randRequest(rng);
    const scope = pick(rng, ['analysis', 'dca', 'portfolio', 'probe-' + String(rngInt(rng, 0, 9))]);
    const key1 = requestKey(scope, request);
    const key2 = requestKey(scope, request); // recompute in-process
    assert(key1 === key2, `requestKey unstable within a run: ${key1} vs ${key2}`);
    assert(/^[0-9a-f]{16}$/.test(key1.slice(scope.length + 1)), `hash not 16 lowercase hex: ${key1}`);
    // Cross-check against the independent FNV-1a 64 implementation.
    const expected = scope + ':' + fnv1a64Reference(canonicalRequest(request));
    assert(key1 === expected, `requestKey != FNV-1a 64 reference: ${key1} vs ${expected}`);
    // Golden vector captured at task time; pins determinism across runs.
    const goldenRequest = {
      security_id: 'QQQ',
      start_date: '2024-01-01',
      end_date: '2024-07-01',
      contribution_sgd: '250.00',
      frequency: 'monthly',
      options: { reinvest: true, withholding_tax_enabled: true, currencies: ['USD', 'SGD'] },
    };
    assert(
      requestKey('golden-vector', shuffleKeysDeep(rng, goldenRequest)) ===
        'golden-vector:eabebd7a80a2b9ee',
      'golden request-key vector changed',
    );
  }),

  property('canonical_json_roundtrip', 150, (rng) => {
    const request = randRequest(rng);
    const canon = canonicalRequest(request);
    const parsed = JSON.parse(canon);
    assert(jsonDeepEqual(parsed, request), `JSON.parse(canonicalRequest) != request: ${canon}`);
    assert(canonicalRequest(parsed) === canon, 'canonical form not stable across parse/print');
    // Idempotence on already-canonical input.
    assert(canonicalRequest(JSON.parse(canonicalRequest(parsed))) === canon, 'canonical not idempotent');
    // Keys are sorted recursively at every level.
    const outerKeys = Object.keys(JSON.parse(canon));
    if (outerKeys.length > 1) {
      assert(
        JSON.stringify(outerKeys) === JSON.stringify([...outerKeys].sort()),
        `outer keys not sorted: ${outerKeys}`,
      );
    }
    // No whitespace, no locale-dependent forms.
    assert(!/\s/.test(canon), `canonical JSON contains whitespace: ${canon}`);
  }),
]);

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

const report = runAll();
process.stdout.write(report + '\n');
process.exitCode = totalFailures ? 1 : 0;
