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
