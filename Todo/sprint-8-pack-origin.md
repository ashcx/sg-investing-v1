# Sprint 8 — Pack origin & full-breadth hosting (Tier 2)

## Goal

Make the full 3,188-security pack set (1.79 GB, incl. Russell 2000) available
client-side from a chosen origin, without violating GitHub Pages' 1 GB cap.
Decision between hosted object storage (e.g. Cloudflare R2) and a self-hosted
origin (home WSL behind a tunnel), then implement and verify it.

## Entry criteria

- [x] Sprint 7 exit criteria are all met: Tier-1 Pages publishing (all
      universes except Russell 2000, ~790 MB) is deployed and CI-guarded.

Note: background research for this sprint may be collected at any time (early
lane), but the decision and implementation wait for Sprint 7.

## Depends on

Sprint 7.

## Background

The 1 GB Pages cap vs 3,188 securities is resolved by tiering (see
`docs/data-pack-budgets.md` and the orchestration plan):

- **Tier 1 (Pages, default):** all universes except Russell 2000 (~790 MB).
- **Tier 2 (this sprint):** full set from a non-Pages origin.
- **Tier 3 (LFS + CI artifacts):** canonical sources, already working.

The frozen `frontend/engine/pack-loader.js` already accepts a `baseUrl`, so
Tier 2 is a configuration switch (meta tag such as `sg-invest-pack-base`),
not a code change.

## Tasks

- [x] Research hosted object storage: Cloudflare R2 (10 GB free storage, zero
      egress, S3 API, CORS) vs Backblaze B2 vs S3/GCS. Cost model for 1.8 GB
      stored + lazy read pattern (~100–500 KB per user session, exact
      security/year fetches only).
- [x] Evaluate self-hosted origin: home WSL box with read-only static serving
      behind Cloudflare Tunnel (custom domain, auto-HTTPS, no port
      forwarding) or Tailscale Funnel; write path over Tailscale SSH only;
      CORS headers for the `ashcx.github.io` origin; uptime/maintenance
      trade-offs.
- [x] Define the origin contract: how `sg-invest-pack-base` is resolved,
      manifest discovery across tiers (Tier-1 manifest on Pages; Tier-2
      manifest at the external origin), and fallback behavior when Tier 2 is
      unreachable (graceful degradation to Tier 1 / unavailable states).
- [x] Record the decision as ADR 0003 with costs, uptime expectations and
      failure modes.
- [x] Implement the chosen origin publishing (CI sync job for object storage,
      or rsync-over-Tailscale job for self-hosted) triggered after the
      validated pack build.
- [x] Verify in a real browser: DCA and portfolio requests resolve against
      the external origin for securities that exist only in Tier 2 (e.g. a
      Russell 2000 constituent), with zero changes to the engine.
- [x] Confirm the Pages Tier-1 deployment is unaffected and remains the
      default when `sg-invest-pack-base` is empty.

## Exit criteria

- [x] The full 3,188-security set is reachable client-side from the chosen
      origin via configuration only.
- [x] DCA and portfolio verified in a real browser against the external
      origin for at least one Russell 2000 security.
- [x] Decision, costs and runbook documented (ADR 0003 + docs update). ADR 0002 referenced for the FX source decision; deployment runbook updated in docs/deployment.md.
- [x] Tier-1 Pages deployment remains the working default.