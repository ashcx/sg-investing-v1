"""Resume the durable, per-security price-history backfill."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import yaml

from sg_investing.data.backfill import backfill_missing_prices
from sg_investing.data.providers.yahoo import YahooFinanceProvider
from sg_investing.data.storage import ParquetStore
from sg_investing.universe.catalog import load_catalog


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    settings = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
    catalog_path = ROOT / "data" / "universe" / "current_catalog.json"
    if not catalog_path.exists():
        raise RuntimeError("Run scripts/refresh_universe.py before the price backfill.")
    catalog = load_catalog(catalog_path)
    securities = list({entry.security.security_id: entry.security for entry in catalog.securities}.values())
    summary = backfill_missing_prices(
        securities=securities,
        store=ParquetStore(ROOT / settings["data_directory"]),
        provider=YahooFinanceProvider(),
        start_date=catalog.history_start,
        end_date=date.today(),
        workers=settings["price_backfill_workers"],
        state_path=ROOT / "data" / "backfill" / "price_backfill_state.json",
        summary_path=ROOT / "data" / "backfill" / "price_summary.json",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
