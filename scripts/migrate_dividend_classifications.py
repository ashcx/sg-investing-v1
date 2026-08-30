"""Reclassify provider events when their source lacks type metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from sg_investing.data.storage import ParquetStore
from sg_investing.models import DividendType
from sg_investing.universe.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    settings = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT / settings["data_directory"])
    parser.add_argument("--source", default="yahoo_finance")
    parser.add_argument("--catalog", type=Path, default=ROOT / "data" / "universe" / "current_catalog.json")
    parser.add_argument("--from-type", choices=[item.value for item in DividendType], default="regular")
    parser.add_argument("--to-type", choices=[item.value for item in DividendType], default="unknown")
    args = parser.parse_args()

    store = ParquetStore(args.data_root)
    catalog = load_catalog(args.catalog)
    security_metadata = {
        str(entry.security.security_id): (entry.security.ticker, entry.security.exchange)
        for entry in catalog.securities
    }
    rows = []
    for path in sorted((store.root / "dividends").glob("year=*.parquet")):
        rows.extend(store.read_dividends(year=int(path.stem.split("=", 1)[1])))
    converted = []
    reclassified = 0
    metadata_enriched = 0
    for row in rows:
        updates = {}
        if row.source == args.source and row.dividend_type.value == args.from_type:
            updates["dividend_type"] = DividendType(args.to_type)
            reclassified += 1
        metadata = security_metadata.get(str(row.security_id))
        if metadata:
            updates["ticker"], updates["exchange"] = metadata
            metadata_enriched += 1
        updates["ingested_at"] = row.retrieved_at
        converted.append(row.model_copy(update=updates) if updates else row)
    changed = sum(left != right for left, right in zip(rows, converted, strict=True))
    if changed:
        store.upsert_dividends(converted)
    print(
        json.dumps(
            {
                "source": args.source,
                "from_type": args.from_type,
                "to_type": args.to_type,
                "rows_scanned": len(rows),
                "rows_reclassified": reclassified,
                "rows_metadata_enriched": metadata_enriched,
                "rows_changed": changed,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
