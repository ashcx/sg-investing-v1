"""Run-scoped request pacing and failure containment for live data refreshes."""

from __future__ import annotations

import time
from threading import Lock


class ProviderCircuitOpen(RuntimeError):
    """No further provider traffic is allowed in this run."""


class GuardedProvider:
    """Pace listing calls, retry transient failures, and stop on provider throttling.

    Deliberately expose the individual price API rather than a batch downloader:
    an underlying downloader can swallow per-listing rate-limit exceptions.
    Tests can inject clock/sleep functions without real delays or network access.
    """

    def __init__(self, provider, *, interval=0.15, retries=2, backoff=1.0,
                 max_requests=20000, max_seconds=2400, clock=time.monotonic, sleep=time.sleep):
        self.provider = provider
        self.name = provider.name
        self.interval = interval
        self.retries = retries
        self.backoff = backoff
        self.max_requests = max_requests
        self.max_seconds = max_seconds
        self.clock = clock
        self.sleep = sleep
        self.started = clock()
        self.last_started = self.started - interval
        self.requests = 0
        self.retry_count = 0
        self.circuit_reason = None
        self.lock = Lock()

    def _call(self, method, *args):
        for attempt in range(self.retries + 1):
            # Serialize calls as well as starts: hidden provider retries must not
            # amplify concurrent requests. This lock is shared by all datasets.
            with self.lock:
                if self.circuit_reason:
                    raise ProviderCircuitOpen(self.circuit_reason)
                if self.requests >= self.max_requests or self.clock() - self.started >= self.max_seconds:
                    self.circuit_reason = "Provider request/time budget exhausted; run is incomplete."
                    raise ProviderCircuitOpen(self.circuit_reason)
                delay = self.interval - (self.clock() - self.last_started)
                if delay > 0:
                    self.sleep(delay)
                if self.clock() - self.started >= self.max_seconds:
                    self.circuit_reason = "Provider request/time budget exhausted; run is incomplete."
                    raise ProviderCircuitOpen(self.circuit_reason)
                self.last_started = self.clock()
                self.requests += 1
                try:
                    return getattr(self.provider, method)(*args)
                except Exception as error:
                    text = f"{type(error).__name__}: {error}".lower()
                    if any(term in text for term in ("ratelimit", "rate limit", "too many requests", "429")):
                        self.circuit_reason = "Provider rate limit detected; remaining queries were not sent."
                        raise ProviderCircuitOpen(self.circuit_reason) from error
                    transient = isinstance(error, (OSError, TimeoutError)) or any(
                        term in text for term in
                        ("timeout", "connection", "temporary", "500", "502", "503", "504")
                    )
                    if not transient or isinstance(error, (ValueError, TypeError)) or attempt == self.retries:
                        raise
            self.retry_count += 1
            self.sleep(self.backoff * (2 ** attempt))
        raise AssertionError("unreachable")

    def get_prices(self, *args):
        return self._call("get_prices", *args)

    def get_dividends(self, *args):
        return self._call("get_dividends", *args)

    def get_corporate_actions(self, *args):
        return self._call("get_corporate_actions", *args)

    def get_fx_rates(self, *args):
        return self._call("get_fx_rates", *args)

    def telemetry(self):
        return {"requests": self.requests, "retries": self.retry_count,
                "circuit_reason": self.circuit_reason,
                "elapsed_seconds": round(self.clock() - self.started, 3)}
