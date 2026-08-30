"""Run the local dividend-versus-price behavior review without network calls."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import pyarrow.parquet as pq
import yaml

from sg_investing.data.dividend_quality import audit_dividend_price_behavior
from sg_investing.data.storage import ParquetStore
from sg_investing.models import DividendEvent, PriceBar

ROOT = Path(__file__).resolve().parents[1]


def _dividend_rows(store: ParquetStore) -> list[DividendEvent]:
    rows: list[DividendEvent] = []
    for path in sorted((store.root / "dividends").glob("year=*.parquet")):
        rows.extend(store.read_dividends(year=int(path.stem.split("=", 1)[1])))
    return rows


def _price_rows_for_securities(store: ParquetStore, security_ids: set[str]) -> list[PriceBar]:
    rows: list[PriceBar] = []
    columns = ["security_id", "trading_date", "open", "high", "low", "close", "volume",
               "currency", "exchange", "timezone", "source", "retrieved_at"]
    for path in sorted((store.root / "prices").glob("market=*/year=*.parquet")):
        parquet = pq.ParquetFile(path)
        for batch in parquet.iter_batches(columns=columns, batch_size=50_000):
            for payload in batch.to_pylist():
                if str(payload["security_id"]) in security_ids:
                    rows.append(PriceBar.model_validate(payload))
    return rows


def main() -> None:
    settings = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT / settings["data_directory"])
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    store = ParquetStore(args.data_root)
    dividends = _dividend_rows(store)
    prices = _price_rows_for_securities(store, {str(row.security_id) for row in dividends})
    report = audit_dividend_price_behavior(dividends, prices)
    output = args.output or args.data_root / "dividends" / "price_behavior_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(report), indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(asdict(report), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
