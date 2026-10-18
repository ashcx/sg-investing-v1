"""Apply configured listing removals to canonical data; does not publish a site."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from sg_investing.data.dividend_quality import build_dividend_coverage, write_coverage_report
from sg_investing.data.storage import ParquetStore
from sg_investing.universe.catalog import load_catalog, save_catalog


def remove_excluded_listings(root: Path) -> dict:
    """Remove only explicitly configured identifiers, preserving other row values."""
    configured = load_catalog(root / 'config/universe.yaml')
    excluded = {str(value) for value in configured.excluded_security_ids}
    if not excluded:
        raise ValueError('No explicitly configured listing exclusions.')
    catalog_path = root / 'data/universe/current_catalog.json'
    catalog = load_catalog(catalog_path)
    catalog = catalog.model_copy(update={
        'excluded_security_ids': sorted(set(catalog.excluded_security_ids)
                                        | set(configured.excluded_security_ids)),
        'securities': [entry for entry in catalog.securities
                       if str(entry.security.security_id) not in excluded],
    })
    removed_rows = {}
    for dataset in ['prices', 'dividends', 'corporate_actions']:
        for path in sorted((root / 'data' / dataset).rglob('*.parquet')):
            # ParquetFile avoids adding synthetic Hive partition columns.
            table = pq.ParquetFile(path).read()
            if 'security_id' not in table.column_names:
                continue
            keep = pc.invert(pc.is_in(table['security_id'], value_set=pa.array(sorted(excluded))))
            remaining = table.filter(keep)
            if remaining.num_rows == table.num_rows:
                continue
            relative = path.relative_to(root).as_posix()
            removed_rows[relative] = table.num_rows - remaining.num_rows
            ParquetStore._atomic_write_parquet(path, remaining)
            if not pq.ParquetFile(path).read().equals(remaining):
                raise ValueError(f'Unrelated row preservation failed: {relative}')
            if dataset == 'prices':
                manifest_path = root / 'data/manifests/prices' / path.relative_to(root / 'data/prices').with_suffix('.json')
                if manifest_path.exists():
                    manifest = json.loads(manifest_path.read_text())
                    dates = pc.min_max(remaining['trading_date']).as_py()
                    manifest.update(row_count=remaining.num_rows,
                                    first_date=str(dates['min']) if dates['min'] else None,
                                    last_date=str(dates['max']) if dates['max'] else None)
                    ParquetStore._atomic_write_json(manifest_path, manifest)
    save_catalog(catalog, catalog_path)
    summary_path = root / 'data/universe/summary.json'
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())
        summary.update(unique_securities=len({e.security.security_id for e in catalog.securities}),
                       membership_rows=len(catalog.securities),
                       excluded_security_ids=sorted(map(str, catalog.excluded_security_ids)))
        ParquetStore._atomic_write_json(summary_path, summary)
    state_path = root / 'data/backfill/price_backfill_state.json'
    if state_path.exists():
        state = json.loads(state_path.read_text())
        for key in excluded:
            state.get('securities', {}).pop(key, None)
        ParquetStore._atomic_write_json(state_path, state)
        price_summary = root / 'data/backfill/price_summary.json'
        if price_summary.exists():
            summary = json.loads(price_summary.read_text())
            counts = Counter(record.get('status', 'pending')
                             for record in state['securities'].values()
                             if record.get('in_current_catalog', True))
            summary.update(total_securities=sum(counts.values()), by_status=dict(sorted(counts.items())))
            ParquetStore._atomic_write_json(price_summary, summary)
    checkpoint_path = root / 'data/corporate_actions/query_checkpoints.json'
    if checkpoint_path.exists():
        checkpoints = json.loads(checkpoint_path.read_text())
        for key in excluded:
            checkpoints.pop(key, None)
        ParquetStore._atomic_write_json(checkpoint_path, checkpoints)
    coverage_path = root / 'data/dividends/coverage_report.json'
    report = build_dividend_coverage(catalog=catalog, store=ParquetStore(root / 'data'),
                                    coverage_path=coverage_path)
    write_coverage_report(report, coverage_path)
    backfill_path = root / 'data/dividends/backfill_summary.json'
    if backfill_path.exists():
        summary = json.loads(backfill_path.read_text())
        summary['results'] = [record for record in summary.get('results', [])
                              if record.get('security_id') not in excluded]
        summary['summary'] = report.summary
        ParquetStore._atomic_write_json(backfill_path, summary)
    return {'excluded_security_ids': sorted(excluded), 'removed_rows': removed_rows,
            'remaining_securities': len({e.security.security_id for e in catalog.securities})}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(remove_excluded_listings(args.root), indent=2))
