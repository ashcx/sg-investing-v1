"""Backfill and incrementally refresh the canonical dividend archive.

Examples:
    python scripts/backfill_dividends.py --tickers QQQ,SMH,SOXX,IWM,D05.SI
    python scripts/backfill_dividends.py --include-unknown
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from sg_investing.data.dividend_backfill import backfill_dividends
from sg_investing.data.dividend_quality import record_coverage_snapshot
from sg_investing.data.providers.yahoo import YahooFinanceProvider
from sg_investing.data.storage import ParquetStore
from sg_investing.universe.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    settings = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "data" / "universe" / "current_catalog.json")
    parser.add_argument("--data-root", type=Path, default=ROOT / settings["data_directory"])
    parser.add_argument("--coverage-report", type=Path, default=None)
    parser.add_argument("--coverage-history", type=Path, default=None)
    parser.add_argument("--start-floor", type=date.fromisoformat, default=None)
    parser.add_argument("--end-date", type=date.fromisoformat, default=datetime.now(UTC).date())
    parser.add_argument("--reconciliation-days", type=int, default=settings["recent_reconciliation_days"])
    parser.add_argument("--workers", type=int, default=settings.get("price_backfill_workers", 4))
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--include-unknown", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--full-history",
        action="store_true",
        help="Ignore prior query checkpoints and reconcile from each security's required start date.",
    )
    parser.add_argument(
        "--retry-provider-errors",
        action="store_true",
        help="Retry only securities marked provider_error in the existing coverage report.",
    )
    parser.add_argument(
        "--refresh-existing-events",
        action="store_true",
        help="Re-fetch only securities with stored events, useful for precision/schema migrations.",
    )
    parser.add_argument("--tickers", default=None, help="Optional comma-separated provider tickers for a pilot run.")
    parser.add_argument("--max-securities", type=int, default=None)
    args = parser.parse_args()

    if not args.catalog.exists():
        raise RuntimeError("Run scripts/refresh_universe.py before dividend backfill.")
    catalog = load_catalog(args.catalog)
    store = ParquetStore(args.data_root)
    coverage_path = args.coverage_report or args.data_root / "dividends" / "coverage_report.json"
    coverage_history_path = args.coverage_history or args.data_root / "dividends" / "coverage_history.json"
    tickers = [item.strip() for item in args.tickers.split(",") if item.strip()] if args.tickers else None
    report, results = backfill_dividends(
        catalog=catalog,
        store=store,
        provider=YahooFinanceProvider(),
        coverage_path=coverage_path,
        end_date=args.end_date,
        start_floor=args.start_floor or catalog.history_start,
        reconciliation_days=args.reconciliation_days,
        workers=args.workers,
        retries=args.retries,
        include_unknown=args.include_unknown,
        tickers=tickers,
        max_securities=args.max_securities,
        full_history=args.full_history,
        retry_provider_errors=args.retry_provider_errors,
        refresh_existing_events=args.refresh_existing_events,
    )
    summary = {
        "coverage_report": str(coverage_path),
        "coverage_history": str(coverage_history_path),
        "summary": report.summary,
        "coverage_regression_warnings": record_coverage_snapshot(report, coverage_history_path),
        "results": [result.model_dump(mode="json") for result in results],
    }
    output_path = store.root / "dividends" / "backfill_summary.json"
    output_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
