"""One bounded listing response must preserve the three independent datasets."""

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from sg_investing.data.providers.base import ProviderHistoryUnavailable
from sg_investing.data.providers.guarded import GuardedProvider, ProviderCircuitOpen
from sg_investing.data.providers.yahoo import YahooFinanceProvider
from tests.helpers import OTHER_SECURITY_ID, security
from tests.test_provider_guard import Clock

START = date(2024, 1, 1)
END = date(2024, 2, 2)


class WindowTicker:
    def __init__(self, history, errors=()):
        self.frame = history
        self.calls = []
        self.errors = list(errors)

    def history(self, **kwargs):
        self.calls.append(kwargs)
        if self.errors:
            raise self.errors.pop(0)
        dates = self.frame.index.date
        return self.frame.loc[(dates >= date.fromisoformat(kwargs['start']))
                              & (dates < date.fromisoformat(kwargs['end']))].copy()


def history():
    return pd.DataFrame({
        'Open': [100, 101, 102], 'High': [101, 102, 103], 'Low': [99, 100, 101],
        'Close': [100, 101, 102], 'Volume': [1000, 1000, 1000],
        'Dividends': [2, 1.5, 0], 'Stock Splits': [2, 0, 0.5],
        'currency': ['USD', 'EUR', 'USD'],
    }, index=pd.to_datetime(['2024-01-02', '2024-01-10', '2024-02-01']))


def normalized(rows):
    return [row.model_dump(mode='json', exclude={'retrieved_at', 'ingested_at'}) for row in rows]


def shared(sec, ticker, **kwargs):
    provider = YahooFinanceProvider(bounded_events=True,
                                    shared_history_starts={str(sec.security_id): START}, **kwargs)
    provider._ticker = lambda item: ticker
    return provider


def test_shared_history_matches_independent_windows_currency_and_split_semantics():
    sec = security()
    ticker = WindowTicker(history())
    provider = shared(sec, ticker)
    clock = Clock()
    guard = GuardedProvider(provider, clock=clock.time, sleep=clock.sleep)
    windows = [('get_prices', date(2024, 1, 10)),
               ('get_dividends', date(2024, 1, 5)), ('get_corporate_actions', START)]
    reference_ticker = WindowTicker(history())
    reference = YahooFinanceProvider(bounded_events=True)
    reference._ticker = lambda item: reference_ticker
    actual = []
    for method, start in windows:
        got = getattr(guard, method)(sec, start, END)
        expected = getattr(reference, method)(sec, start, END)
        assert normalized(got) == normalized(expected)
        actual.append(got)
    assert actual[1][0].currency == 'EUR'
    assert [row.action_type.value for row in actual[2]] == ['split', 'reverse_split']
    assert len(ticker.calls) == 1 and len(reference_ticker.calls) == 3
    assert ticker.calls[0]['actions'] is True
    assert ticker.calls[0]['start'] == START.isoformat()
    assert guard.telemetry()['requests'] == 1
    assert guard.telemetry()['cached_responses'] == 2
    assert clock.waits == []
    assert provider.cache_metrics()['bytes'] == 0
    assert 0 < provider.cache_metrics()['peak_bytes'] <= provider.max_event_cache_bytes


def test_observed_zero_events_differ_from_an_unobserved_subwindow():
    sec = security()
    frame = history()
    frame[['Dividends', 'Stock Splits']] = 0
    ticker = WindowTicker(frame)
    provider = shared(sec, ticker)
    provider.get_prices(sec, START, END)
    with pytest.raises(ProviderHistoryUnavailable):
        provider.get_dividends(sec, date(2024, 1, 4), date(2024, 1, 9))
    assert provider.get_dividends(sec, date(2024, 1, 10), date(2024, 1, 31)) == []
    assert provider.get_corporate_actions(sec, date(2024, 1, 10), date(2024, 1, 31)) == []
    assert len(ticker.calls) == 1


@pytest.mark.parametrize('column,method', [('Dividends', 'get_dividends'),
                                          ('Stock Splits', 'get_corporate_actions'),
                                          (['Dividends', 'Stock Splits', 'currency'], 'get_dividends')])
def test_missing_cached_event_column_is_a_failure_not_zero_or_unavailable(column, method):
    sec = security()
    ticker = WindowTicker(history().drop(columns=column))
    provider = shared(sec, ticker)
    provider.get_prices(sec, START, END)
    with pytest.raises(ValueError, match='omitted') as failure:
        getattr(provider, method)(sec, START, END)
    assert not isinstance(failure.value, ProviderHistoryUnavailable)
    assert len(ticker.calls) == 1


def test_typed_absence_is_reused_without_three_identical_network_calls():
    sec = security()
    ticker = WindowTicker(history(), [ProviderHistoryUnavailable('No observations')])
    provider = shared(sec, ticker)
    clock = Clock()
    guard = GuardedProvider(provider, clock=clock.time, sleep=clock.sleep)
    for method in ['get_prices', 'get_dividends', 'get_corporate_actions']:
        with pytest.raises(ProviderHistoryUnavailable):
            getattr(guard, method)(sec, START, END)
    assert len(ticker.calls) == 1
    assert guard.requests == 1 and guard.cached_responses == 2
    assert guard.circuit_reason is None
    assert not provider.can_serve_cached('get_dividends', sec, START, END)


def test_transient_failure_is_retried_and_is_never_cached_as_absence():
    sec = security()
    ticker = WindowTicker(history(), [OSError('temporary connection failure')])
    provider = shared(sec, ticker)
    clock = Clock()
    guard = GuardedProvider(provider, clock=clock.time, sleep=clock.sleep)
    assert guard.get_prices(sec, START, END)
    assert guard.get_dividends(sec, START, END)
    assert len(ticker.calls) == 2 and guard.requests == 2
    assert guard.retry_count == 1 and guard.cached_responses == 1
    assert clock.waits == [1.0]


def test_cache_budget_stops_new_traffic_instead_of_growing_or_refetching():
    sec = security()
    ticker = WindowTicker(history())
    provider = shared(sec, ticker, max_event_cache_bytes=1)
    clock = Clock()
    guard = GuardedProvider(provider, clock=clock.time, sleep=clock.sleep)
    with pytest.raises(ProviderCircuitOpen, match='memory budget'):
        guard.get_prices(sec, START, END)
    with pytest.raises(ProviderCircuitOpen):
        guard.get_dividends(sec, START, END)
    assert len(ticker.calls) == 1
    assert provider.cache_metrics()['bytes'] == 0


def test_uncovered_event_window_falls_back_to_an_actual_bounded_request():
    sec = security()
    ticker = WindowTicker(history())
    provider = YahooFinanceProvider(bounded_events=True,
                                    shared_history_starts={str(sec.security_id): date(2024, 1, 10)})
    provider._ticker = lambda item: ticker
    clock = Clock()
    guard = GuardedProvider(provider, clock=clock.time, sleep=clock.sleep)
    guard.get_prices(sec, date(2024, 1, 10), END)
    dividends = guard.get_dividends(sec, START, END)
    assert len(dividends) == 2
    assert len(ticker.calls) == 2 and guard.requests == 2
    assert clock.waits == [pytest.approx(0.3)]


def test_history_for_another_listing_cannot_widen_or_supply_a_peer():
    first = security(ticker='FIRST')
    second = security(ticker='SECOND', security_id=OTHER_SECURITY_ID)
    assert first.security_id != second.security_id
    tickers = {first.ticker: WindowTicker(history()), second.ticker: WindowTicker(history())}
    provider = YahooFinanceProvider(bounded_events=True,
        shared_history_starts={str(first.security_id): START,
                               str(second.security_id): date(2024, 1, 10)})
    provider._ticker = lambda item: tickers[item.ticker]
    provider.get_prices(first, date(2024, 1, 10), END)
    provider.get_prices(second, date(2024, 1, 10), END)
    assert tickers['FIRST'].calls[0]['start'] == '2024-01-01'
    assert tickers['SECOND'].calls[0]['start'] == '2024-01-10'


class TestSharedUpdaterWindows:
    def test_default_updater_plans_cold_and_warm_windows_without_duplicate_fetches(self):
        from scripts.update_incremental import run_incremental_update
        from tests.test_incremental_update import END as UPDATE_END
        from tests.test_incremental_update import IncrementalUpdaterCase

        case = IncrementalUpdaterCase()
        case.setUp()
        try:
            dates = pd.to_datetime(['2025-12-01', '2026-03-02', '2026-03-03',
                                    '2026-08-10', '2026-08-28', '2026-08-31', '2026-09-01'])
            values = [100, 100, 100, 100, 100, 100, 101]
            frame = pd.DataFrame({'Open': values, 'High': values, 'Low': values,
                                  'Close': values, 'Volume': [1000] * len(dates),
                                  'Dividends': [0, 0, 0, 0.5, 0, 0, 0],
                                  'Stock Splits': [0] * len(dates)}, index=dates)
            tickers = {sec.ticker: WindowTicker(frame) for sec in [case.usd, case.sgd]}
            fx = WindowTicker(pd.DataFrame({'Close': [1.35] * len(dates)}, index=dates))
            clock = Clock()

            class FastGuard(GuardedProvider):
                def __init__(self, provider):
                    super().__init__(provider, clock=clock.time, sleep=clock.sleep)

            with (patch('scripts.update_incremental.GuardedProvider', FastGuard),
                  patch.object(YahooFinanceProvider, '_ticker',
                               new=staticmethod(lambda sec: tickers[sec.ticker])),
                  patch.object(YahooFinanceProvider, '_ticker_symbol',
                               new=staticmethod(lambda symbol: fx))):
                dry = run_incremental_update(case.root, end_date=UPDATE_END,
                                             build_packs=False, dry_run=True)
                planned = next(row for row in dry['securities'] if row['ticker'] == case.usd.ticker)
                assert planned['provider_history_fetch_start'] == '2020-01-01'
                assert planned['price_fetch_start'] == '2026-07-17'
                assert not any(ticker.calls for ticker in tickers.values()) and not fx.calls
                cold = run_incremental_update(case.root, end_date=UPDATE_END, build_packs=False)
                assert cold['complete']
                assert cold['provider_telemetry']['requests'] == 3  # two histories + FX
                assert cold['provider_telemetry']['cached_responses'] == 3
                assert cold['provider_telemetry']['event_cache']['bytes'] == 0
                assert tickers[case.usd.ticker].calls[0]['start'] == '2020-01-01'
                warm = run_incremental_update(case.root, end_date=UPDATE_END, build_packs=False)
                assert warm['complete']
                assert warm['provider_telemetry']['requests'] == 3
                assert warm['provider_telemetry']['cached_responses'] == 3
                assert tickers[case.usd.ticker].calls[1]['start'] == '2026-07-18'
                for ticker in tickers.values():
                    assert len(ticker.calls) == 2
        finally:
            case.doCleanups()


def test_no_recent_prices_does_not_erase_observed_historical_events():
    sec = security()
    ticker = WindowTicker(history())
    provider = shared(sec, ticker)
    clock = Clock()
    guard = GuardedProvider(provider, clock=clock.time, sleep=clock.sleep)
    end = date(2024, 3, 2)
    with pytest.raises(ProviderHistoryUnavailable):
        guard.get_prices(sec, date(2024, 3, 1), end)
    assert len(guard.get_dividends(sec, START, end)) == 2
    assert len(guard.get_corporate_actions(sec, START, end)) == 2
    assert guard.requests == 1 and guard.cached_responses == 2
    assert provider.cache_metrics()['bytes'] == 0
