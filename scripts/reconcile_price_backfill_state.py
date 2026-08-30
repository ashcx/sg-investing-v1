"""Reconcile derived price-backfill state with the local Parquet store."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sg_investing.data.backfill import reconcile_price_backfill_state
from sg_investing.data.storage import ParquetStore
from sg_investing.universe.catalog import load_catalog


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    catalog = load_catalog(ROOT / "data" / "universe" / "current_catalog.json")
    securities = list(
        {entry.security.security_id: entry.security for entry in catalog.securities}.values()
    )
    summary = reconcile_price_backfill_state(
        securities=securities,
        store=ParquetStore(ROOT / "data"),
        state_path=ROOT / "data" / "backfill" / "price_backfill_state.json",
        summary_path=ROOT / "data" / "backfill" / "price_summary.json",
        as_of=date.today(),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
