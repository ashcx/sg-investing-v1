# ADR 0003 — Tier-2 pack origin: Cloudflare R2

- Status: Accepted
- Date: 2026-09-04
- Decides: Todo/sprint-8-pack-origin.md (pack origin for the full catalog)
- Related: ADR 0001 (calculation architecture), docs/data-pack-budgets.md,
  docs/deployment.md

## Context

GitHub Pages caps a deployment at 1 GB. The full pack set (3,188 securities,
55,574 packs, 1.79 GB) cannot be published wholesale, so Sprint 7 introduced
tiering: Tier-1 on Pages (all universes except Russell 2000, 1,242
securities, ~750 MB), Tier-3 in LFS + CI artifacts. The remaining gap: the
1,946 Russell 2000 constituents were not client-side computable. The pack
loader (Sprint 4) already accepts a `baseUrl`, making an external origin a
configuration switch. Self-hosting (home WSL behind a tunnel) was evaluated
and set aside as an operated service with uptime/maintenance burden; hosted
object storage was preferred.

## Decision

**Cloudflare R2 is the Tier-2 pack origin**, configured as:

- Bucket `sg-investing-v1` (APAC), public read via the development URL
  `https://pub-a88a64ce6b634ab8a70623c35ff81ad7.r2.dev`
- CORS: `GET, HEAD` allowed for `https://ashcx.github.io` (+ localhost dev
  origins), 1-hour cache
- Credentials live in GitHub Actions secrets (`R2_ACCESS_KEY_ID`,
  `R2_SECRET_ACCESS_KEY`, `R2_ACCOUNT_ID`), scoped Object Read & Write to the
  single bucket, no IP filtering (CI runners have dynamic IPs)
- Seeded from the canonical pack build (55,576 objects, 1.73 GiB)
- CI: `.github/workflows/sync-r2.yml` re-syncs and verifies after every
  successful Tier-1 deployment (`rclone sync`, then manifest snapshot-id +
  security-count assertion)

**Origin contract (frontend):** `sg-invest-pack-base` meta tag. Empty =
Tier-1 only (default, current behavior). Set = Tier-1 first, external origin
as fallback for securities the Tier-1 manifest does not know. `s8ResolveSecurity`
implements the resolution; every loader call site (series, analysis, DCA,
portfolio) is origin-aware. Tier-2 unreachability degrades to the standard
"unavailable" state naming the security and range — never a wrong result.

**CSP:** `connect-src` includes the R2 origin (S7's `connect-src 'self'`
would otherwise block cross-origin pack fetches).

## Costs (free tier, measured)

- Storage: 1.73 GiB of the 10 GiB free allotment
- Reads: pack sessions are lazy (~10–30 packs per user request); 10M
  Class-B reads/month free — orders of magnitude above personal traffic
- Egress: $0 (R2 has no egress fees)

## Failure modes

- R2 unreachable → affected securities (Russell 2000) show explicit
  unavailable states; Tier-1 (1,242 securities) keeps working unchanged.
- Stale origin: sync-r2 re-runs after every deploy; the manifest verify step
  fails loudly on snapshot mismatch.
- Credential exposure: Object-scoped, single-bucket, revocable; rotate if the
  repo's Actions secret is ever suspected (dashboard → R2 → Manage API
  Tokens).

## Alternatives considered

- **Self-hosted WSL origin behind Cloudflare Tunnel:** viable (loader is
  origin-agnostic; read-only static serving), rejected for the operated-
  service burden (uptime, patching, ISP dependence) at no cost advantage.
- **Backblaze B2:** viable; R2 won on zero-egress simplicity and the free
  tier fitting entirely.
- **Second Pages repo:** re-encounters the same 1 GB cap; rejected.
