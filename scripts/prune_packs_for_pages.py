#!/usr/bin/env python3
"""Prune the built frontend data packs to the GitHub Pages publication tier.

Sprint 7 (S7.1): the full-universe pack set is ~1.8 GB and must not be pushed
wholesale to GitHub Pages (1 GiB site guidance, docs/data-pack-budgets.md).
The coordinator-approved tiering publishes every manifest security EXCEPT the
`russell2000_current` universe (~790 MB); Tier-2 hosting for the excluded
universe is a Sprint 8 decision (Todo/sprint-8-pack-origin.md).

What this script does:
  1. Loads ``frontend/data/packs/manifest.json``.
  2. Keeps every security whose `universes` do NOT include an excluded
     universe; deletes the pack directories of the excluded securities.
  3. Rewrites ``manifest.json`` to the pruned subset: the snapshot identity
     (data_snapshot_id, catalog_version, catalog_as_of), methodology and all
     other top-level fields are preserved; `securities`, `summary` and
     `support.counts` are recomputed; a `tier` note records the excluded
     universes and a snapshot warning is appended so the manifest stays honest.
  4. Asserts manifest<->packs consistency in both directions: every pack
     referenced by a kept manifest entry exists on disk, and every file under
     the packs directory is referenced by the manifest.
  5. Prints the published total bytes; with ``--max-total-bytes`` it exits
     non-zero when the deployment exceeds the budget (the deploy workflow
     fails the release above 950 MB).

Run after ``python scripts/build_data_packs.py``:
    python scripts/prune_packs_for_pages.py                 # prune + verify
    python scripts/prune_packs_for_pages.py --verify-only   # verify + sizes
    python scripts/prune_packs_for_pages.py --dry-run       # report only
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
from pathlib import Path

DEFAULT_PACKS_DIR = Path("frontend/data/packs")
DEFAULT_EXCLUDED_UNIVERSES = ("russell2000_current",)
# Guard for the Pages artifact budget (workflow fails above this).
DEFAULT_MAX_TOTAL_BYTES = 950 * 1000 * 1000

MB = 1000 * 1000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--packs-dir",
        type=Path,
        default=DEFAULT_PACKS_DIR,
        help=f"built packs directory (default: {DEFAULT_PACKS_DIR})",
    )
    parser.add_argument(
        "--exclude-universe",
        action="append",
        default=[],
        help="manifest universe to exclude from the published tier (repeatable; "
        f"default: {list(DEFAULT_EXCLUDED_UNIVERSES)})",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="do not prune; only assert manifest<->packs consistency and print sizes",
    )
    parser.add_argument("--dry-run", action="store_true", help="report what would be pruned, change nothing")
    parser.add_argument(
        "--max-total-bytes",
        type=int,
        default=DEFAULT_MAX_TOTAL_BYTES,
        help=f"fail when the published packs + manifest exceed this many bytes "
        f"(default: {DEFAULT_MAX_TOTAL_BYTES}); 0 disables the check",
    )
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_manifest(packs_dir: Path) -> dict:
    manifest_path = packs_dir / "manifest.json"
    if not manifest_path.is_file():
        fail(f"manifest not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        fail(f"manifest {manifest_path} does not parse: {error}")
    if manifest.get("schema_version") != 1 or manifest.get("pack_type") != "manifest":
        fail(f"unexpected manifest schema in {manifest_path}")
    return manifest


def security_universes(entry: dict) -> set[str]:
    return {str(universe.get("universe")) for universe in (entry.get("universes") or []) if universe.get("universe")}


def pack_bytes_for(entry: dict) -> int:
    return sum(int((year or {}).get("bytes") or 0) for year in (entry.get("years") or {}).values())


def pack_count_for(entry: dict) -> int:
    return len(entry.get("years") or {})


def referenced_pack_paths(entries: list[dict]) -> set[str]:
    paths = set()
    for entry in entries:
        for year in (entry.get("years") or {}).values():
            pack = (year or {}).get("pack")
            if pack:
                paths.add(str(pack))
    return paths


def on_disk_pack_paths(packs_dir: Path) -> set[str]:
    return {f"{pack_file.parent.name}/{pack_file.name}" for pack_file in packs_dir.glob("security=*/year=*.json")}


def assert_consistency(packs_dir: Path, entries: list[dict]) -> None:
    referenced = referenced_pack_paths(entries)
    on_disk = on_disk_pack_paths(packs_dir)
    missing = sorted(referenced - on_disk)
    if missing:
        fail(f"{len(missing)} pack(s) referenced by the manifest are missing on disk, e.g. {missing[:3]}")
    orphan = sorted(on_disk - referenced)
    if orphan:
        fail(f"{len(orphan)} pack file(s) on disk are not referenced by the manifest, e.g. {orphan[:3]}")
    for entry in entries:
        security_dir = packs_dir / f"security={entry.get('security_id')}"
        # Securities with no data years (status `unavailable`) legitimately have
        # no pack directory; only entries referencing packs must exist on disk.
        if pack_count_for(entry) and not security_dir.is_dir():
            fail(f"security {entry.get('security_id')} ({entry.get('ticker')}) references packs but has no pack directory")
    print(
        f"consistency: {len(referenced)} pack files on disk match the manifest exactly "
        f"({len(entries)} securities)"
    )


def rewrite_manifest(manifest: dict, kept: list[dict], excluded: list[str], removed: list[dict]) -> dict:
    total_bytes = sum(pack_bytes_for(entry) for entry in kept)
    sizes = [int((year or {}).get("bytes") or 0) for entry in kept for year in (entry.get("years") or {}).values()]
    price_rows = sum(int((year or {}).get("rows") or 0) for entry in kept for year in (entry.get("years") or {}).values())
    counts = {"fully_supported": 0, "incomplete": 0, "unavailable": 0}
    for entry in kept:
        status = entry.get("status")
        counts[status if status in counts else "unavailable"] += 1

    pruned = dict(manifest)
    pruned["securities"] = kept
    pruned["summary"] = {
        **(manifest.get("summary") or {}),
        "securities": len(kept),
        "pack_count": sum(pack_count_for(entry) for entry in kept),
        "total_bytes": total_bytes,
        "price_rows": price_rows,
        "pack_bytes": {
            "min": min(sizes) if sizes else 0,
            "median": int(statistics.median(sizes)) if sizes else 0,
            "max": max(sizes) if sizes else 0,
        },
    }
    pruned["support"] = {**(manifest.get("support") or {}), "counts": counts}
    # Tier note: which universes are NOT hosted here (Tier 2 is a Sprint 8 decision).
    pruned["tier"] = {
        "published": "tier1",
        "excluded_universes": excluded,
        "excluded_securities": len(removed),
        "excluded_pack_bytes": sum(pack_bytes_for(entry) for entry in removed),
        "note": (
            "Tier-1 GitHub Pages publication: securities in the excluded universes are pruned "
            "from the deployed pack set; the full universe remains available in the "
            "data-packs workflow artifact. Tier-2 hosting is a Sprint 8 decision."
        ),
    }
    tier_warning = (
        f"Tier-1 publication: {len(removed)} securities of universe(s) "
        f"{', '.join(excluded)} are not hosted on this site."
    )
    warnings = [warning for warning in (manifest.get("warnings") or []) if not warning.startswith("Tier-1 publication:")]
    warnings.append(tier_warning)
    pruned["warnings"] = warnings
    return pruned


def main() -> int:
    args = parse_args()
    packs_dir: Path = args.packs_dir
    excluded = args.exclude_universe or list(DEFAULT_EXCLUDED_UNIVERSES)
    manifest = load_manifest(packs_dir)
    entries = manifest.get("securities") or []

    kept = [entry for entry in entries if not (security_universes(entry) & set(excluded))]
    removed = [entry for entry in entries if security_universes(entry) & set(excluded)]
    removed_ids = {entry.get("security_id") for entry in removed}
    kept_ids = {entry.get("security_id") for entry in kept}
    if not kept:
        fail("the exclusion removes every security; refusing to prune to an empty set")
    if kept_ids & removed_ids:
        fail("internal error: a security would be both kept and removed")

    kept_bytes = sum(pack_bytes_for(entry) for entry in kept)
    removed_bytes = sum(pack_bytes_for(entry) for entry in removed)
    print(
        f"tier plan: keep {len(kept)} securities / {sum(pack_count_for(e) for e in kept)} packs "
        f"({kept_bytes / MB:.1f} MB), prune {len(removed)} securities / "
        f"{sum(pack_count_for(e) for e in removed)} packs ({removed_bytes / MB:.1f} MB) "
        f"of universe(s) {', '.join(excluded)}"
    )

    if args.verify_only:
        assert_consistency(packs_dir, kept)
    else:
        orphan_dirs = [
            directory
            for directory in packs_dir.glob("security=*")
            if directory.name.removeprefix("security=") not in kept_ids
        ]
        if args.dry_run:
            print(f"dry run: would delete {len(orphan_dirs)} security pack directories, then rewrite manifest.json")
        else:
            for directory in orphan_dirs:
                shutil.rmtree(directory)
            pruned = rewrite_manifest(manifest, kept, excluded, removed)
            manifest_path = packs_dir / "manifest.json"
            manifest_path.write_text(
                json.dumps(pruned, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            print(f"pruned {len(orphan_dirs)} security pack directories; rewrote {manifest_path}")
            assert_consistency(packs_dir, kept)

    manifest_size = (packs_dir / "manifest.json").stat().st_size
    total = kept_bytes + manifest_size
    print(
        f"published tier size: {kept_bytes} pack bytes + {manifest_size} manifest bytes = "
        f"{total} bytes ({total / MB:.1f} MB)"
    )
    if args.max_total_bytes and total > args.max_total_bytes:
        fail(
            f"published tier is {total} bytes ({total / MB:.1f} MB), over the "
            f"{args.max_total_bytes} byte budget"
        )
    print(f"budget check: within {args.max_total_bytes / MB:.0f} MB deployment budget")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
