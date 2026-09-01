# Property tests (Sprint 3, task S3.2)

Deterministic property tests for the portable calculation engine
(`frontend/engine/`). Harness: `frontend/engine/property/property.mjs` —
dependency-free, runs with `node frontend/engine/property/property.mjs`
(Node >= 18; verified on v22.23.2). No npm, no network.

## Determinism and seed strategy

- PRNG: **mulberry32**, seeded per case. Fixed base-seed list
  `BASE_SEEDS = [0x5347494e, 0x12345678, 0x0badc0de, 0x0d15ea5e]`; property
  *p* (global creation order) uses `BASE_SEEDS[p mod 4]`, and case *i* uses
  `seed = (baseSeed + (i+1) * 0x9e3779b1) mod 2^32`.
- No `Math.random`, no `Date.now`, no clock/locale in the output → the full
  report is **byte-identical across runs** (verified; see Results).
- Case caps: ≤ 150 random cases per property (most 40–100). A property stops
  at its first failing case; the failure line reports
  `property -> seed -> case` for reproduction. Exit code is 1 on any failure.
- Wall time: ~8–11 s for the whole suite (budget: < 60 s).

## Property inventory

### Group (a) — Rounding via `money.js`

| Property | Cases | Asserts |
| --- | --- | --- |
| `quantize_idempotent` | 100 | For random decimals and `dp ∈ [0,8]`: `toFixed(dp)` re-applied to its own output is the identical string; the re-parsed value equals its own `toDecimalPlaces(dp)`. |
| `half_even_sign_symmetry` | 100 | `round(-x) == -round(x)` numerically for random values, including constructed HALF_EVEN ties (digit `dp+1` = 5, zeros beyond). Signed-zero-safe comparison. |
| `half_even_known_tie_vectors` | 12 | Published-style HALF_EVEN tie vectors (`0.125→0.12`, `0.135→0.14`, `2.5→2`, `3.5→4`, `-2.5→-2`, `1.005→1.00`, `0.15→0.2`, `0.05→0.0`, `2.675→2.68`, …) all exact. |
| `decimal_sum_traps_exact` | 100 | `0.1×10 = 1` and `0.1+0.2 = 0.3` exactly; repeated `sumDecimals` of a random value equals exact `× n` (string-equal); order-invariance of chained sums within the 28-digit precision budget. |
| `dec_decstring_roundtrip` | 100 | `dec(decString(x)) == dec(x)`; `decString` is a fixed point; `dec(Decimal)` returns the same instance; number path goes through `String(number)` exactly; `null/undefined → 0`; `ZERO`/`ONE` intact. |

### Group (b) — Contribution scaling via `dca.js`

Random ranges (2015–2024, 20–900 days), all three frequencies, weekday
calendar minus ~12% random holidays (±14-day margins so FX/price rules
always resolve).

| Property | Cases | Asserts |
| --- | --- | --- |
| `contribution_dates_first_available_trading_day` | 60 | Every returned date is a trading day inside `[start, end]`; strictly ascending; element-wise equal to an independent first-available-trading-day recomputation. |
| `contribution_count_matches_frequency` | 60 | Date count equals the number of distinct monthly/quarterly/yearly period keys holding ≥ 1 trading day in range; no duplicates. |
| `total_invested_sum_string_exact` | 60 | `dcaAnalysis().contribution_dates` equals `contributionDates()`; `total_contributed_sgd` is string-identical to `sumDecimals(n × contribution)` and `contribution × n` in Decimal. |

### Group (c) — Split handling via `splits.js`

| Property | Cases | Asserts |
| --- | --- | --- |
| `apply_ratio_is_exact_multiplication` | 80 | `applyActions(shares, [a]) == shares × ratio` exactly (value + string); multi-action lists apply every ratio in order (digit budgets keep products < 28 significant digits). |
| `split_preserves_total_cost_per_share_scales_inverse` | 80 | With cost basis `C` untouched: per-share cost after = per-share before ÷ ratio exactly (shares chosen from 2ᵃ5ᵇ so divisions are exact); `shares_after × per_share_after == C` (total cost preserved). |
| `ratio_then_inverse_returns_original_shares` | 80 | For ratios with exactly-representable reciprocals (2ᵃ5ᵇ set): apply ratio then `1/ratio` (and the reverse order) returns the original shares exactly. |
| `group_by_effective_date_is_shuffle_invariant` | 40 | `groupByEffectiveDate` on shuffled inputs yields the same date keys and per-date ratio multisets; grouped sequential application equals flat date-sorted application. |

### Group (d) — Cash-flow ordering via `portfolio.js` / `xirr`

Random but *valid* transaction streams over a two-security (USD/SGD) market:
the generator simulates the engine's canonical order and drops any
over-selling SELL, so every permutation is well-formed. Results are compared
as canonical JSON (Decimals stringified, keys sorted) via
`canonicalRequest`.

| Property | Cases | Asserts |
| --- | --- | --- |
| `portfolio_shuffle_invariance` | 40 (×6 shuffles = 240 runs) | `analyzePortfolio` is deterministic on identical input; every shuffled transaction order produces a byte-identical result envelope. |
| `xirr_order_invariance` | 60 | `xirr` of shuffled cash flows (unique dates) equals `xirr` of sorted flows bit-for-bit (string-equal); null-ness is order-independent. |
| `equal_date_tiebreak_is_ascending_transaction_id` | 1 (deterministic) | **Observed tie-break:** for equal `transaction_date`, transactions are processed in ascending `String(transaction_id)` order. Pinned with a same-date BUY+SELL pair whose realized P&L differs by order: ids `AAA-BUY`/`BBB-SELL` → BUY processed first (realized = `100 − 5×151/15`); swapped ids → SELL first (realized = `50`); final quantity/cost-basis and cash ledger asserted for both; each case also passes through shuffles unchanged. |

### Group (e) — Request keys via `request-keys.js`

| Property | Cases | Asserts |
| --- | --- | --- |
| `key_order_invariance` | 150 (×8 permutations = **1200 key-order permutations**) | Random nested requests (depth ≤ 3, decimal-string/int/bool/null leaves, arrays order-preserving): `canonicalRequest` and `requestKey` are invariant under deep key-order permutation. |
| `different_scopes_never_collide` | 100 | Same request under 2–4 scopes: keys carry the scope prefix, hash bodies are scope-independent, full keys never collide. |
| `stable_across_runs_and_fnv_reference` | 100 | Key recomputation in-process is stable; hash body is 16 lowercase hex chars; key equals an **independent FNV-1a 64 reimplementation** written from the spec; golden vector `requestKey("golden-vector", {…}) = golden-vector:eabebd7a80a2b9ee` pins cross-run determinism. |
| `canonical_json_roundtrip` | 150 | `JSON.parse(canonicalRequest(r))` deep-equals `r` (order-insensitive); canonical form is a fixed point and idempotent; outer keys sorted; no whitespace. |

## Results (two consecutive full runs, byte-identical)

`sha256` of both outputs: `e40edbdf1fd9262d9d10c6dfbb1e2a4c9a0e394b94b8362c502957c35e8c37f1`

```text
== SG/Invest engine property tests (S3.2) ==
base seeds: 0x5347494e, 0x12345678, 0xbadc0de, 0xd15ea5e
[rounding (money.js)]
  ok   quantize_idempotent cases=100
  ok   half_even_sign_symmetry cases=100
  ok   half_even_known_tie_vectors cases=12
  ok   decimal_sum_traps_exact cases=100
  ok   dec_decstring_roundtrip cases=100
[contribution scaling (dca.js)]
  ok   contribution_dates_first_available_trading_day cases=60
  ok   contribution_count_matches_frequency cases=60
  ok   total_invested_sum_string_exact cases=60
[split handling (splits.js)]
  ok   apply_ratio_is_exact_multiplication cases=80
  ok   split_preserves_total_cost_per_share_scales_inverse cases=80
  ok   ratio_then_inverse_returns_original_shares cases=80
  ok   group_by_effective_date_is_shuffle_invariant cases=40
[cash-flow ordering (portfolio.js / xirr)]
  ok   portfolio_shuffle_invariance cases=40
  ok   xirr_order_invariance cases=60
  ok   equal_date_tiebreak_is_ascending_transaction_id cases=1
[request keys (request-keys.js)]
  ok   key_order_invariance cases=150
  ok   different_scopes_never_collide cases=100
  ok   stable_across_runs_and_fnv_reference cases=100
  ok   canonical_json_roundtrip cases=150
summary: groups=5 properties=19 cases=1473 failed-properties=0 result=PASS
```

## Engine bugs found

**None.** All 19 properties pass on all cases; the only failures during
development were bugs in the test generator itself (passing date strings
where `contributionDates` expects price rows), fixed in the harness, not the
engine.

## Notes on `request-keys.js` (report only, file untouched)

- `canonicalRequest` / `requestKey` are pure and deterministic: no
  `Math.random`, `Date.now`, or locale dependence observed; output depends
  only on input content, with keys sorted recursively and arrays kept in
  order (element order is semantic).
- Hash is FNV-1a 64-bit, rendered as 16 lowercase hex characters; verified
  against an independent reimplementation and a recorded golden vector.
- Scoping is prefix-based (`scope:` + hash), so different scopes cannot
  collide; the hash body itself is scope-independent.
- Edge behaviour worth knowing (not bugs):
  - `undefined` values inside a request are not representable:
    `stableStringify` maps them through `JSON.stringify`, which yields
    `undefined` for the value — requests should use `null` (or omit keys)
    to stay inside the JSON contract.
  - Key order invariance holds for own enumerable string keys; symbol or
    non-enumerable keys are invisible to canonicalization (same as
    `JSON.stringify`).
  - All financial values must already be strings (contract on line 8–9 of
    the file); the properties generate requests that respect this.
