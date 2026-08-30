"""Migrate Yahoo dividend observations to the canonical security-based key."""

from __future__ import annotations

import json
from pathlib import Path

from sg_investing.data.storage import ParquetStore

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    store = ParquetStore(ROOT / "data")
    rows = []
    for path in sorted((store.root / "dividends").glob("year=*.parquet")):
        year = int(path.stem.split("=")[-1])
        rows.extend(store.read_dividends(year=year))

    migrated = 0
    normalized = []
    for row in rows:
        if row.source == "yahoo_finance":
            source_id = (
                f"{row.source}:{row.security_id}:{row.ex_date.isoformat()}"
                f":{row.amount}:{row.currency}"
            )
            if row.source_id != source_id:
                row = row.model_copy(update={"source_id": source_id})
                migrated += 1
        normalized.append(row)

    store.upsert_dividends(normalized)
    print(json.dumps({"rows": len(rows), "migrated": migrated}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
