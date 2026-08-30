"""Run an incremental refresh for configured seed securities.

Usage: `python scripts/update_data.py`. This is deliberately a normal Python
script rather than a product CLI. It emits a JSON-serializable summary that a
future workflow or GitHub Pages build step can publish.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import yaml

from sg_investing.data.dividend_backfill import backfill_dividends
from sg_investing.data.dividend_quality import record_coverage_snapshot
from sg_investing.data.ingestion import update_fx_rates, update_security_prices
from sg_investing.data.providers.yahoo import YahooFinanceProvider
from sg_investing.data.storage import ParquetStore
from sg_investing.universe.catalog import load_catalog


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    settings = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
    # The seed configuration is intentionally small; production refreshes must
    # operate on the validated current catalog used by the price backfill.
    catalog_path = ROOT / "data" / "universe" / "current_catalog.json"
    if not catalog_path.exists():
        raise RuntimeError("Run scripts/refresh_universe.py before updating market data.")
    catalog = load_catalog(catalog_path)
    store = ParquetStore(ROOT / settings["data_directory"])
    provider = YahooFinanceProvider()
    end_date = date.today()
    results = [
        update_security_prices(
            store=store,
            provider=provider,
            security=entry.security,
            end_date=end_date,
            start_floor=catalog.history_start,
            reconciliation_days=settings["recent_reconciliation_days"],
            pipeline_version=settings["pipeline_version"],
            include_dividends=False,
        )
        for entry in catalog.securities
    ]
    dividend_report, dividend_results = backfill_dividends(
        catalog=catalog,
        store=store,
        provider=provider,
        coverage_path=store.root / "dividends" / "coverage_report.json",
        end_date=end_date,
        start_floor=catalog.history_start,
        reconciliation_days=settings["recent_reconciliation_days"],
        workers=settings.get("price_backfill_workers", 4),
        retries=2,
        include_unknown=True,
    )
    dividend_coverage_warnings = record_coverage_snapshot(
        dividend_report,
        store.root / "dividends" / "coverage_history.json",
    )
    currencies = sorted({entry.security.currency for entry in catalog.securities if entry.security.currency != "SGD"})
    fx_rows = [
        update_fx_rates(
            store=store,
            provider=provider,
            base_currency=currency,
            end_date=end_date,
            start_floor=catalog.history_start,
            reconciliation_days=settings["recent_reconciliation_days"],
        )
        for currency in currencies
    ]
    summary = {
        "updated": sum(result.status == "OK" for result in results),
        "warnings": sum(result.status == "WARNING" for result in results),
        "failed": sum(result.status == "FAILED" for result in results),
        "dividends": dividend_report.model_dump(mode="json"),
        "dividend_coverage_warnings": dividend_coverage_warnings,
        "dividend_updates": [result.model_dump(mode="json") for result in dividend_results],
        "fx_rows_written": sum(len(rows) for rows in fx_rows),
        "results": [
            {
                **result.model_dump(mode="json", exclude={"manifests"}),
                "partitions_written": len(result.manifests),
            }
            for result in results
        ],
    }
    (ROOT / "data" / "update_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
