"""Changed provider coverage must invalidate old successful pack metadata."""

import json

from sg_investing.data.packs import build_data_packs
from sg_investing.data.providers.base import ProviderHistoryUnavailable
from tests.test_incremental_update import TEST_ID, IncrementalUpdaterCase


class CoverageInvalidationTests(IncrementalUpdaterCase):
    def test_failed_dividend_query_refreshes_all_stored_years_without_new_observations(self):
        self._run(self._provider())
        build_data_packs(self.root, self.output)
        provider = self._provider()
        prices = provider.get_prices

        def failed_dividends(security, *dates):
            if str(security.security_id) == TEST_ID:
                raise ProviderHistoryUnavailable('No current observations')
            return []

        def missing_prices(security, *dates):
            if str(security.security_id) == TEST_ID:
                raise ProviderHistoryUnavailable('No current observations')
            return prices(security, *dates)

        provider.get_dividends = failed_dividends
        provider.get_prices = missing_prices
        summary = self._run(provider, build_packs=True)
        self.assertEqual(summary['price_dates_new'], 0)
        self.assertEqual(summary['dividend_events_new_or_restated'], 0)
        for year in [2025, 2026]:
            pack = json.loads(self._pack_bytes(TEST_ID, year))
            coverage = pack['security']['dividend_coverage']
            self.assertEqual(coverage['coverage_status'], 'provider_error')
            self.assertFalse(coverage['provider_query_succeeded'])
            self.assertEqual(coverage['error'], 'No current observations')

        # Recovery also changes support without requiring a new dividend event.
        restored = self._run(self._provider(), build_packs=True)
        self.assertEqual(restored['dividend_events_new_or_restated'], 0)
        for year in [2025, 2026]:
            coverage = json.loads(self._pack_bytes(TEST_ID, year))['security']['dividend_coverage']
            self.assertTrue(coverage['provider_query_succeeded'])
            self.assertIsNone(coverage['error'])

    def test_coverage_invalidation_ignores_stable_states_but_tracks_new_failure(self):
        from scripts.update_incremental import _coverage_change_keys

        good = ('data_available', True, None)
        bad = ('provider_error', False, 'No observations')
        self.assertEqual(_coverage_change_keys({TEST_ID: good}, {TEST_ID: good}), [])
        self.assertEqual(_coverage_change_keys({}, {TEST_ID: good}), [])
        self.assertTrue(_coverage_change_keys({}, {TEST_ID: bad}))
        self.assertTrue(_coverage_change_keys({TEST_ID: bad}, {TEST_ID: good}))
