"""Explicit removals must survive refreshes without altering peer observations."""

import json
from datetime import date

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import yaml

from scripts.remove_excluded_listings import remove_excluded_listings
from sg_investing.data.packs import build_data_packs
from sg_investing.universe.catalog import load_catalog
from tests.test_incremental_update import TEST_ID, IncrementalUpdaterCase


class ListingRemovalTests(IncrementalUpdaterCase):
    def setUp(self):
        super().setUp()
        path = self.root / 'config/universe.yaml'
        path.write_text(yaml.safe_dump({'history_start': '2000-01-01', 'securities': [],
                                       'excluded_security_ids': [TEST_ID]}))

    def test_removal_preserves_every_other_row_and_updates_active_records(self):
        paths = list((self.root / 'data').rglob('*.parquet'))
        expected = {}
        for path in paths:
            table = pq.ParquetFile(path).read()
            if 'security_id' in table.column_names:
                table = table.filter(pc.not_equal(table['security_id'], pa.scalar(TEST_ID)))
            expected[path] = table
        result = remove_excluded_listings(self.root)
        self.assertEqual(result['remaining_securities'], 1)
        self.assertTrue(result['removed_rows'])
        for path, table in expected.items():
            self.assertTrue(pq.ParquetFile(path).read().equals(table), str(path))
        catalog = load_catalog(self.root / 'data/universe/current_catalog.json')
        self.assertNotIn(TEST_ID, {str(e.security.security_id) for e in catalog.securities})
        report = json.loads((self.root / 'data/dividends/coverage_report.json').read_text())
        self.assertEqual(report['summary']['tracked_securities'], 1)
        self.assertNotIn(TEST_ID, {e['security_id'] for e in report['securities']})
        self.assertEqual(remove_excluded_listings(self.root)['removed_rows'], {})

    def test_future_source_merge_cannot_reintroduce_removed_listing(self):
        remove_excluded_listings(self.root)
        catalog = load_catalog(self.root / 'data/universe/current_catalog.json')
        refreshed = catalog.merge_current_listings(universe='future_source', source='test',
                                                   as_of=date(2026, 10, 18), listings=[self.usd])
        self.assertEqual(refreshed.securities, catalog.securities)

    def test_old_uncatalogued_price_restore_cannot_publish_removed_listing(self):
        original = self.store.read_prices(market='US', year=2026)
        remove_excluded_listings(self.root)
        self.store.upsert_prices(market='US', rows=original, pipeline_version='test')
        build_data_packs(self.root, self.output)
        manifest = json.loads((self.output / 'manifest.json').read_text())
        self.assertNotIn(TEST_ID, {e['security_id'] for e in manifest['securities']})
        self.assertFalse((self.output / f'security={TEST_ID}').exists())


    def test_scoped_rebuild_removes_excluded_entries_from_an_old_manifest(self):
        from scripts.build_data_packs import _scoped_merge_build
        from tests.test_incremental_update import FUND_ID

        build_data_packs(self.root, self.output)
        self.assertTrue((self.output / f'security={TEST_ID}').exists())
        remove_excluded_listings(self.root)
        _scoped_merge_build(self.root, self.output, security_ids=[FUND_ID], markets=None,
                            years=None, pretty_manifest=False)
        manifest = json.loads((self.output / 'manifest.json').read_text())
        self.assertNotIn(TEST_ID, {e['security_id'] for e in manifest['securities']})
        self.assertFalse((self.output / f'security={TEST_ID}').exists())
