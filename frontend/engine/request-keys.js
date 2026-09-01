// Deterministic request-key derivation for the SG / Invest calculation engine.
//
// FROZEN INTERFACE (Sprint 3, Todo/orchestration-plan.md freeze point 3):
//   canonicalRequest(request) -> string   stable JSON, keys sorted recursively
//   requestKey(scope, request) -> string  `<scope>:<fnv1a64-hex>`
//
// Contract:
// - All financial values inside `request` MUST already be strings
//   (decimal-safe rule; no Number for money/FX/quantities/dates math).
// - Pure function of its inputs: no Math.random, no Date.now, no locale.
// - Same request content in any key order -> identical key.
// - Different scope -> different key namespace.

function stableStringify(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) {
    return "[" + value.map(stableStringify).join(",") + "]";
  }
  const keys = Object.keys(value).sort();
  const parts = keys.map((k) => JSON.stringify(k) + ":" + stableStringify(value[k]));
  return "{" + parts.join(",") + "}";
}

const FNV_OFFSET = 0xcbf29ce484222325n;
const FNV_PRIME = 0x100000001b3n;
const FNV_MASK = 0xffffffffffffffffn;

function fnv1a64(str) {
  let hash = FNV_OFFSET;
  for (let i = 0; i < str.length; i++) {
    hash ^= BigInt(str.charCodeAt(i));
    hash = (hash * FNV_PRIME) & FNV_MASK;
  }
  return hash.toString(16).padStart(16, "0");
}

export function canonicalRequest(request) {
  return stableStringify(request);
}

export function requestKey(scope, request) {
  if (typeof scope !== "string" || scope.length === 0) {
    throw new TypeError("scope must be a non-empty string");
  }
  return scope + ":" + fnv1a64(canonicalRequest(request));
}
