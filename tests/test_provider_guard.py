from types import SimpleNamespace

import pytest

from sg_investing.data.providers.guarded import GuardedProvider, ProviderCircuitOpen


class Clock:
    def __init__(self):
        self.now = 0.0
        self.waits = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


def test_shared_pacing_and_bounded_backoff():
    clock = Clock()
    calls = []

    def fetch(*args):
        calls.append(args)
        if len(calls) < 3:
            raise OSError("temporary connection failure")
        return ["observed"]

    provider = GuardedProvider(SimpleNamespace(name="fake", get_prices=fetch),
                               interval=0.2, retries=2, clock=clock.time, sleep=clock.sleep)
    assert provider.get_prices("security", "start", "end") == ["observed"]
    assert len(calls) == 3
    assert clock.waits == [1.0, 2.0]
    assert provider.telemetry()["retries"] == 2
    assert provider.get_prices("another", "start", "end") == ["observed"]
    assert clock.waits[-1] == pytest.approx(0.2)


def test_rate_limit_opens_one_circuit_for_all_datasets():
    clock = Clock()
    calls = []

    def fetch(*args):
        calls.append(args)
        raise RuntimeError("429 Too Many Requests")

    provider = GuardedProvider(SimpleNamespace(name="fake", get_prices=fetch,
                                              get_dividends=fetch),
                               clock=clock.time, sleep=clock.sleep)
    with pytest.raises(ProviderCircuitOpen, match="rate limit"):
        provider.get_prices("QQQ", "start", "end")
    with pytest.raises(ProviderCircuitOpen, match="rate limit"):
        provider.get_dividends("QQQ", "start", "end")
    assert len(calls) == 1
    assert clock.waits == []


def test_budget_prevents_new_traffic_and_invalid_values_are_not_retried():
    clock = Clock()
    provider = GuardedProvider(SimpleNamespace(name="fake", get_prices=list),
                               max_requests=1, clock=clock.time, sleep=clock.sleep)
    assert provider.get_prices() == []
    with pytest.raises(ProviderCircuitOpen, match="budget"):
        provider.get_prices()
    assert provider.requests == 1
    invalid = GuardedProvider(SimpleNamespace(name="fake", get_prices=lambda: int("bad")),
                              clock=clock.time, sleep=clock.sleep)
    with pytest.raises(ValueError):
        invalid.get_prices()
    assert invalid.requests == 1


def test_pacing_delay_cannot_start_traffic_past_time_budget():
    clock = Clock()
    provider = GuardedProvider(SimpleNamespace(name="fake", get_prices=list),
                               interval=2, max_seconds=1, clock=clock.time, sleep=clock.sleep)
    provider.get_prices()
    with pytest.raises(ProviderCircuitOpen, match="budget"):
        provider.get_prices()
    assert provider.requests == 1


def test_permanent_listing_failure_is_not_retried():
    clock = Clock()

    def missing():
        raise RuntimeError("possibly delisted; no price history found")

    provider = GuardedProvider(SimpleNamespace(name="fake", get_prices=missing),
                               clock=clock.time, sleep=clock.sleep)
    with pytest.raises(RuntimeError, match="delisted"):
        provider.get_prices()
    assert provider.requests == 1
    assert provider.retry_count == 0


def test_typed_absence_is_not_retried_or_mistaken_for_a_rate_limit():
    from sg_investing.data.providers.base import ProviderHistoryUnavailable

    clock = Clock()

    def absent():
        raise ProviderHistoryUnavailable('Listing 429 has no observations')

    provider = GuardedProvider(SimpleNamespace(name='fake', get_prices=absent),
                               clock=clock.time, sleep=clock.sleep)
    with pytest.raises(ProviderHistoryUnavailable):
        provider.get_prices()
    assert provider.requests == 1
    assert provider.retry_count == 0
    assert provider.circuit_reason is None


def test_numeric_price_or_identifier_cannot_open_rate_limit_circuit():
    clock = Clock()

    def invalid(*args):
        raise ValueError('Invalid value 429.15 for listing 4290')

    provider = GuardedProvider(SimpleNamespace(name='fake', get_prices=invalid),
                               clock=clock.time, sleep=clock.sleep)
    with pytest.raises(ValueError):
        provider.get_prices('GRPN')
    assert provider.circuit_reason is None
    assert provider.rate_limit_cause is None


def test_http_rate_limit_retains_exact_cause_without_query_credentials():
    clock = Clock()
    error = RuntimeError('HTTP 429 https://example.test/?crumb=private&key=private')
    provider = GuardedProvider(SimpleNamespace(name='fake', get_prices=lambda *args: (_ for _ in ()).throw(error)),
                               clock=clock.time, sleep=clock.sleep)
    with pytest.raises(ProviderCircuitOpen):
        provider.get_prices(SimpleNamespace(ticker='GRPN'))
    cause = provider.telemetry()['rate_limit_cause']
    assert cause['exception_type'] == 'builtins.RuntimeError'
    assert cause['security'] == 'GRPN'
    assert cause['request_index'] == 1
    assert 'private' not in cause['message']


def test_vendor_type_or_http_status_identifies_rate_limit_without_message_matching():
    vendor_error = type('YFRateLimitError', (Exception,), {})
    http_error = RuntimeError('Request rejected')
    http_error.response = SimpleNamespace(status_code=429)
    for error in [vendor_error('Try later'), http_error]:
        def fetch(*args, failure=error):
            raise failure

        clock = Clock()
        provider = GuardedProvider(SimpleNamespace(name='fake', get_prices=fetch),
                                   clock=clock.time, sleep=clock.sleep)
        with pytest.raises(ProviderCircuitOpen):
            provider.get_prices('GRPN')
        assert provider.rate_limit_cause['exception_type'].endswith(type(error).__name__)
