"""Build versioned browser data packs from the canonical Parquet store.

Reads the validated snapshot under ``data/`` via the storage/catalog code and
writes partitioned JSON packs to ``frontend/data/packs/``:

- ``security=<security_id>/year=<YYYY>.json`` — one lazy-loadable pack per
  security-year (prices, FX window, dividends, corporate actions, coverage,
  provenance and data-quality warnings).
- ``manifest.json`` — support manifest that answers, before any calculation,
  whether a security/date range is fully supported, incomplete or
  unavailable.

Run it after a validated snapshot (for example after
``scripts/update_data.py``). Canonical Parquet is never modified or required
to be committed; packs are plain static files a Pages host or a CI artifact
can serve.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sg_investing.data.packs import build_data_packs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Pack output directory (default: <root>/frontend/data/packs).",
    )
    parser.add_argument(
        "--security",
        action="append",
        default=None,
        help="Limit the build to one security_id (repeatable).",
    )
    parser.add_argument(
        "--market",
        action="append",
        default=None,
        help="Limit the build to one market partition (repeatable).",
    )
    parser.add_argument(
        "--pretty-manifest",
        action="store_true",
        help="Write manifest.json indented (larger; for inspection only).",
    )
    args = parser.parse_args()
    summary = build_data_packs(
        args.root,
        args.output,
        security_ids=args.security,
        markets=args.market,
        pretty_manifest=args.pretty_manifest,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
