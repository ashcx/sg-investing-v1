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
``scripts/update_data.py`` or ``scripts/update_incremental.py``). Canonical
Parquet is never modified or required to be committed; packs are plain static
files a Pages host or a CI artifact can serve.

Incremental builds (Sprint 7.5 Track B): passing ``--security`` and/or
``--years`` rebuilds ONLY the matching security/year pack files and MERGES
the manifest — touched entries are recomputed from the rebuilt packs, all
other securities are preserved byte-for-byte, and summary/support counts are
recomputed over the union. Without scoping flags the build behaves exactly as
before: a full rebuild that resets the output directory and replaces the
manifest. Scoped merges add an ``incremental`` block to the manifest
documenting the base snapshot and the rebuild scope; the top-level ``scope``
keeps describing what the merged manifest answers for (the previous build's
scope, typically the full universe).
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from statistics import median

from sg_investing.data.packs import (
    STATUS_FULLY_SUPPORTED,
    STATUS_INCOMPLETE,
    STATUS_UNAVAILABLE,
    StoreContext,
    _fx_coverage,
    _manifest_entry,
    _manifest_warnings,
    _write_json,
    build_data_packs,
    compute_data_snapshot_id,
    load_catalog_snapshot,
)

# NOTE: the private ``sg_investing.data.packs`` helpers above are imported
# deliberately. The packs module exposes no scoped-build primitive, and src/
# is frozen for the incremental-update work; composing its entry builders
# here keeps pack content and manifest schema byte-identical to full builds
# without duplicating the logic. Recorded as a noted limitation in
# docs/incremental-updates.md.


def _year_list(raw: str) -> list[int]:
    years: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            years.append(int(token))
        except ValueError:
            raise argparse.ArgumentTypeError(f"Invalid year {token!r}: expected e.g. --years 2024,2025") from None
    if not years:
        raise argparse.ArgumentTypeError("--years requires at least one year")
    return years


def _scoped_merge_build(
    root: Path,
    target: Path,
    *,
    security_ids: list[str] | None,
    markets: list[str] | None,
    years: list[int] | None,
    pretty_manifest: bool,
) -> dict:
    """Rebuild only the scoped security/year packs and merge the manifest."""

    # argparse ``--years`` combines a repeatable flag with a list-typed value,
    # yielding nested lists like [[2024, 2025]]; flatten to one flat list.
    if years is not None:
        years = [year for group in years for year in (group if isinstance(group, list) else [group])]
    root_path = Path(root)
    data_root = root_path / "data"
    data_snapshot_id = compute_data_snapshot_id(data_root)
    catalog = load_catalog_snapshot(root_path)
    context = StoreContext(data_root)
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")

    with tempfile.TemporaryDirectory(prefix="packs-scoped-") as staging_name:
        staging = Path(staging_name) / "packs"
        # Reuse the full builder for pack CONTENT: it writes every pack for
        # the scoped securities into staging; only the requested (security,
        # year) pairs are copied into the real output below.
        build_data_packs(
            root_path,
            staging,
            security_ids=security_ids,
            markets=markets,
            pretty_manifest=False,
        )
        staged_manifest = json.loads((staging / "manifest.json").read_text(encoding="utf-8"))
        staged_entries = {entry["security_id"]: entry for entry in staged_manifest["securities"]}

        manifest_path = target / "manifest.json"
        old_manifest = None
        if manifest_path.exists():
            old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        old_entries = (
            {entry["security_id"]: entry for entry in old_manifest["securities"]}
            if old_manifest is not None
            else {}
        )

        entries = dict(old_entries)
        replaced_packs = 0
        updated_entries = 0
        for security_id, staged_entry in sorted(staged_entries.items()):
            staged_years = {
                year_key: detail
                for year_key, detail in staged_entry.get("years", {}).items()
                if years is None or int(year_key) in years
            }
            if not staged_years:
                continue
            for detail in staged_years.values():
                destination = target / detail["pack"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(staging / detail["pack"], destination)
                replaced_packs += 1
            merged_years = {**old_entries.get(security_id, {}).get("years", {}), **staged_years}
            native_currency = old_entries.get(security_id, {}).get("native_currency") or staged_entry.get(
                "native_currency"
            )
            entries[security_id] = _manifest_entry(
                security_id, merged_years, native_currency, catalog, context
            )
            updated_entries += 1

        all_entries = [entries[security_id] for security_id in sorted(entries)]
        support_counts = {STATUS_FULLY_SUPPORTED: 0, STATUS_INCOMPLETE: 0, STATUS_UNAVAILABLE: 0}
        for entry in all_entries:
            support_counts[entry["status"]] += 1
        year_details = [detail for entry in all_entries for detail in entry.get("years", {}).values()]
        pack_sizes = [detail["bytes"] for detail in year_details]

        manifest = {
            "schema_version": staged_manifest["schema_version"],
            "manifest_version": staged_manifest["manifest_version"],
            "pack_type": staged_manifest["pack_type"],
            "generated_at": generated_at,
            "data_snapshot_id": data_snapshot_id,
            "catalog_version": catalog.version,
            "catalog_as_of": catalog.as_of,
            "history_start": catalog.history_start,
            "methodology_version": staged_manifest["methodology_version"],
            "source": old_manifest["source"] if old_manifest is not None else staged_manifest["source"],
            # A merge answers for the union of the previous manifest's universe
            # and the rebuilt entries, so the previous build's scope is what
            # still describes this manifest; the rebuild scope itself is
            # recorded inside the ``incremental`` block below.
            "scope": old_manifest["scope"] if old_manifest is not None else {
                "security_ids": sorted(security_ids) if security_ids is not None else None,
                "markets": sorted(markets) if markets is not None else None,
                "years": sorted(years) if years is not None else None,
            },
            "incremental": {
                "mode": "merge",
                "base_data_snapshot_id": (
                    old_manifest["data_snapshot_id"] if old_manifest is not None else None
                ),
                "replaced_packs": replaced_packs,
                "updated_entries": updated_entries,
                "scope": {
                    "security_ids": sorted(security_ids) if security_ids is not None else None,
                    "markets": sorted(markets) if markets is not None else None,
                    "years": sorted(years) if years is not None else None,
                },
            },
            "pack_layout": staged_manifest["pack_layout"],
            "support": {
                "counts": support_counts,
                "range_query": staged_manifest["support"]["range_query"],
            },
            "fx": {
                "available_pairs": context.available_fx_pairs(),
                "quote_currency": staged_manifest["fx"]["quote_currency"],
                "coverage": _fx_coverage(context, all_entries),
            },
            "summary": {
                "securities": len(all_entries),
                "pack_count": len(year_details),
                "total_bytes": sum(pack_sizes),
                "price_rows": sum(detail["rows"] for detail in year_details),
                "pack_bytes": {
                    "min": min(pack_sizes) if pack_sizes else None,
                    "median": int(median(pack_sizes)) if pack_sizes else None,
                    "max": max(pack_sizes) if pack_sizes else None,
                },
            },
            "warnings": _manifest_warnings(all_entries, context),
            "securities": all_entries,
        }
        target.mkdir(parents=True, exist_ok=True)
        manifest["summary"]["manifest_bytes"] = _write_json(
            target / "manifest.json", manifest, pretty=pretty_manifest
        )
        manifest["summary"]["total_bytes"] += manifest["summary"]["manifest_bytes"]

        return {
            "output_dir": str(target),
            "data_snapshot_id": data_snapshot_id,
            "catalog_version": catalog.version,
            "catalog_as_of": catalog.as_of,
            "pack_count": len(year_details),
            "securities": len(all_entries),
            "price_rows": manifest["summary"]["price_rows"],
            "total_bytes": manifest["summary"]["total_bytes"],
            "manifest_bytes": manifest["summary"]["manifest_bytes"],
            "support_counts": support_counts,
            "warnings": manifest["warnings"],
            "merge": {
                "mode": "merge",
                "replaced_packs": replaced_packs,
                "updated_entries": updated_entries,
                "base_data_snapshot_id": manifest["incremental"]["base_data_snapshot_id"],
            },
        }


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
        "--years",
        type=_year_list,
        action="append",
        default=None,
        help="Limit the build to calendar years, e.g. --years 2024,2025 (repeatable).",
    )
    parser.add_argument(
        "--pretty-manifest",
        action="store_true",
        help="Write manifest.json indented (larger; for inspection only).",
    )
    args = parser.parse_args()
    target = args.output or args.root / "frontend" / "data" / "packs"
    scoped = args.security is not None or args.market is not None or args.years is not None
    if scoped:
        summary = _scoped_merge_build(
            args.root,
            target,
            security_ids=args.security,
            markets=args.market,
            years=args.years,
            pretty_manifest=args.pretty_manifest,
        )
    else:
        summary = build_data_packs(
            args.root,
            target,
            security_ids=args.security,
            markets=args.market,
            pretty_manifest=args.pretty_manifest,
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
