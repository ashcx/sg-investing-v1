"""Build a validated, current universe snapshot from approved public sources."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import yaml

from sg_investing.universe.catalog import load_catalog, save_catalog
from sg_investing.universe.sources import (
    fetch_iwm_holdings_current,
    fetch_nasdaq100_current,
    fetch_sgx_current,
    fetch_sp500_current,
)


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    as_of = date.today()
    catalog = load_catalog(ROOT / "config" / "universe.yaml")
    sources = (
        ("sp500_current", "blackrock_ivv_holdings", fetch_sp500_current),
        ("nasdaq100_current", "nasdaq_ndx_pdf_and_june_2026_rebalance", fetch_nasdaq100_current),
        ("russell2000_current", "blackrock_iwm_holdings", fetch_iwm_holdings_current),
        ("sgx_active", "sgx_securities_directory_api", fetch_sgx_current),
    )
    counts: dict[str, int] = {}
    for universe, source, importer in sources:
        listings = importer(as_of=as_of)
        counts[universe] = len(listings)
        catalog = catalog.merge_current_listings(
            universe=universe,
            source=source,
            as_of=as_of,
            listings=listings,
        )
    output_dir = ROOT / "data" / "universe"
    save_catalog(catalog, output_dir / "current_catalog.json")
    summary = {
        "as_of": as_of.isoformat(),
        "source_counts": counts,
        "unique_securities": len({entry.security.security_id for entry in catalog.securities}),
        "membership_rows": len(catalog.memberships()),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
