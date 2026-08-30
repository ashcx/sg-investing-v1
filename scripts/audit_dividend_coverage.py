"""Generate a local dividend coverage matrix without contacting a provider."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from sg_investing.data.dividend_quality import (
    build_dividend_coverage,
    record_coverage_snapshot,
    write_coverage_report,
)
from sg_investing.data.storage import ParquetStore
from sg_investing.universe.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    settings = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "data" / "universe" / "current_catalog.json")
    parser.add_argument("--data-root", type=Path, default=ROOT / settings["data_directory"])
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--history", type=Path, default=None)
    args = parser.parse_args()
    catalog = load_catalog(args.catalog)
    store = ParquetStore(args.data_root)
    output = args.output or args.data_root / "dividends" / "coverage_report.json"
    history = args.history or args.data_root / "dividends" / "coverage_history.json"
    report = build_dividend_coverage(
        catalog=catalog,
        store=store,
        coverage_path=output,
    )
    write_coverage_report(report, output)
    warnings = record_coverage_snapshot(report, history)
    if warnings:
        print(json.dumps({"coverage_regression_warnings": warnings}, indent=2))
    print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
