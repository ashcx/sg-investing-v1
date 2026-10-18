"""Yahoo Finance adapter, isolated behind the provider protocol."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import ClassVar
from uuid import UUID

from sg_investing.data.providers.base import MarketDataProvider, ProviderHistoryUnavailable
from sg_investing.models import (
    CorporateAction,
    CorporateActionType,
    DividendEvent,
    DividendType,
    FxRate,
    PriceBar,
    Security,
)


class YahooFinanceProvider(MarketDataProvider):
    name = "yahoo_finance"

    def __init__(self, *, bounded_events: bool = False,
                 shared_history_starts: dict[str, date] | None = None,
                 max_event_cache_bytes: int = 512 * 1024 * 1024):
        self.bounded_events = bounded_events
        self.shared_history_starts = shared_history_starts or {}
        self.max_event_cache_bytes = max_event_cache_bytes
        self._event_cache: dict[str, tuple] = {}
        self._absence_cache: dict[str, tuple] = {}
        self._event_cache_bytes = 0
        self._event_cache_peak = 0

    def can_serve_cached(self, method: str, security: Security,
                         start_date: date, end_date: date) -> bool:
        if method not in {"get_dividends", "get_corporate_actions"}:
            return False
        sid = str(security.security_id)
        cached = self._event_cache.get(sid) or self._absence_cache.get(sid)
        return bool(cached and cached[0] <= start_date and end_date <= cached[1])

    def cache_metrics(self) -> dict:
        return {"bytes": self._event_cache_bytes, "peak_bytes": self._event_cache_peak,
                "limit_bytes": self.max_event_cache_bytes}

    def _discard_cached_history(self, sid: str) -> None:
        cached = self._event_cache.pop(sid, None)
        if cached:
            self._event_cache_bytes -= cached[3]
        self._absence_cache.pop(sid, None)

    @staticmethod
    def _history_window(history, start_date: date, end_date: date):
        dates = history.index.date
        window = history.loc[(dates >= start_date) & (dates <= end_date)]
        if not len(window.index):
            raise ProviderHistoryUnavailable("No observations in the requested window; event absence is unconfirmed.")
        return window

    def _shared_price_history(self, security: Security, start_date: date, end_date: date):
        sid = str(security.security_id)
        fetch_start = min(start_date, self.shared_history_starts[sid])
        try:
            history = self._bounded_history(self._ticker(security), fetch_start, end_date,
                                            actions=True)
        except ProviderHistoryUnavailable as error:
            self._absence_cache[sid] = (fetch_start, end_date, ProviderHistoryUnavailable(str(error)))
            raise
        # Retain observed dates and event fields, never the complete OHLCV frame.
        # Deep copies prevent pandas blocks from retaining unrelated price columns.
        columns = [name for name in ("Dividends", "Stock Splits", "currency") if name in history]
        events = history.loc[:, columns].copy(deep=True)
        size = int(events.memory_usage(index=True, deep=True).sum())
        self._discard_cached_history(sid)
        if self._event_cache_bytes + size > self.max_event_cache_bytes:
            raise MemoryError("Provider event cache budget exhausted; run is incomplete.")
        self._event_cache[sid] = (fetch_start, end_date, events, size)
        self._event_cache_bytes += size
        self._event_cache_peak = max(self._event_cache_peak, self._event_cache_bytes)
        return self._history_window(history, start_date, end_date)

    def _bounded_history(self, ticker, start_date: date, end_date: date, *, actions: bool):
        try:
            history = ticker.history(
                start=start_date.isoformat(),
                end=(end_date + timedelta(days=1)).isoformat(),
                auto_adjust=False, actions=actions, raise_errors=True, timeout=20,
            )
        except Exception as error:
            # Classify only the vendor's explicit no-history exceptions, never
            # a fuzzy substring such as "delisted" in a connection/error message.
            if (type(error).__module__.startswith("yfinance.")
                    and type(error).__name__ in {"YFPricesMissingError", "YFTzMissingError"}):
                raise ProviderHistoryUnavailable(
                    f"Provider has no observations in the requested window: {error}"
                ) from error
            raise
        if history.empty:
            raise ProviderHistoryUnavailable("No observed history; event absence is unconfirmed.")
        return history

    def _event_history(self, security: Security, start_date: date, end_date: date):
        sid = str(security.security_id)
        if self.can_serve_cached("get_dividends", security, start_date, end_date):
            if sid in self._absence_cache:
                raise self._absence_cache[sid][2]
            return self._history_window(self._event_cache[sid][2], start_date, end_date)
        return self._bounded_history(self._ticker(security), start_date, end_date, actions=True)

    # Matches the canonical Parquet Decimal(32, 18) price columns.  Provider
    # glitches occasionally produce finite but nonsensical values; accepting
    # one would otherwise abort the entire atomic batch at storage time.
    _MAX_PRICE = Decimal(1000000)
    _MAX_VOLUME = Decimal(9223372036854775807)
    # Yahoo reports DBS's 2024 one-for-ten bonus issue in its generic
    # ``Stock Splits`` field.  The ex-date is the effective trading date;
    # DBS disclosed the share issuance for 26 April 2024.
    _KNOWN_BONUS_ISSUES: ClassVar[dict[tuple[str, date], Decimal]] = {
        ("D05.SI", date(2024, 4, 22)): Decimal("1.1"),
    }

    def get_prices_batch(
        self,
        securities: list[Security],
        start_date: date,
        end_date: date,
        *,
        workers: int = 4,
    ) -> tuple[dict[UUID, list[PriceBar]], dict[UUID, str], dict[UUID, str]]:
        """Fetch a bounded set of daily price histories in one provider call.

        The result keeps failures per security so an unavailable ticker never
        prevents valid peers from being atomically stored.
        """

        try:
            import yfinance
        except ImportError as error:  # pragma: no cover - dependency packaging check
            raise RuntimeError("Install the market-data extra to use Yahoo Finance.") from error
        if not securities:
            return {}, {}, {}
        ticker_to_security = {security.ticker: security for security in securities}
        history = yfinance.download(
            tickers=list(ticker_to_security),
            start=start_date.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            auto_adjust=False,
            actions=False,
            group_by="ticker",
            progress=False,
            threads=workers,
        )
        rows_by_security: dict[UUID, list[PriceBar]] = {}
        errors: dict[UUID, str] = {}
        warnings: dict[UUID, str] = {}
        for ticker, security in ticker_to_security.items():
            try:
                frame = history[ticker] if getattr(history.columns, "nlevels", 1) > 1 else history
            except KeyError:
                errors[security.security_id] = "Provider returned no ticker column."
                continue
            rows: list[PriceBar] = []
            invalid_rows = 0
            for timestamp, row in frame.iterrows():
                try:
                    open_price = Decimal(str(row["Open"]))
                    high_price = Decimal(str(row["High"]))
                    low_price = Decimal(str(row["Low"]))
                    close_price = Decimal(str(row["Close"]))
                    volume = Decimal(str(row["Volume"]))
                except (KeyError, ValueError):
                    continue
                # Batch downloads use a shared date index.  Missing rows for
                # one ticker on another ticker's trading day are expected and
                # must not be reported as invalid market data.
                if not close_price.is_finite():
                    continue
                if not self._valid_ohlcv(open_price, high_price, low_price, close_price, volume):
                    invalid_rows += 1
                    continue
                rows.append(
                    PriceBar(
                        security_id=security.security_id,
                        trading_date=timestamp.date(),
                        open=open_price,
                        high=high_price,
                        low=low_price,
                        close=close_price,
                        volume=int(volume),
                        currency=security.currency,
                        exchange=security.exchange,
                        timezone=security.timezone,
                        source=self.name,
                    )
                )
            if rows:
                rows_by_security[security.security_id] = rows
                if invalid_rows:
                    warnings[security.security_id] = f"Quarantined {invalid_rows} invalid raw OHLCV rows."
            else:
                errors[security.security_id] = (
                    "Provider returned no valid OHLCV rows."
                    if not invalid_rows
                    else f"All {invalid_rows} raw OHLCV rows failed validation."
                )
        return rows_by_security, errors, warnings

    @staticmethod
    def _valid_ohlcv(
        open_price: Decimal,
        high_price: Decimal,
        low_price: Decimal,
        close_price: Decimal,
        volume: Decimal,
    ) -> bool:
        return (
            all(value.is_finite() for value in (open_price, high_price, low_price, close_price, volume))
            and all(value > 0 for value in (open_price, high_price, low_price, close_price))
            and all(value <= YahooFinanceProvider._MAX_PRICE for value in (open_price, high_price, low_price, close_price))
            and volume <= YahooFinanceProvider._MAX_VOLUME
            and low_price <= open_price <= high_price
            and low_price <= close_price <= high_price
        )

    @staticmethod
    def _ticker(security: Security):
        try:
            import yfinance
        except ImportError as error:  # pragma: no cover - dependency packaging check
            raise RuntimeError("Install the market-data extra to use Yahoo Finance.") from error
        return yfinance.Ticker(security.ticker)

    def get_prices(self, security: Security, start_date: date, end_date: date) -> list[PriceBar]:
        if self.bounded_events and str(security.security_id) in self.shared_history_starts:
            history = self._shared_price_history(security, start_date, end_date)
        else:
            ticker = self._ticker(security)
            history = (self._bounded_history(ticker, start_date, end_date, actions=False)
                       if self.bounded_events else ticker.history(
                           start=start_date.isoformat(),
                           end=(end_date + timedelta(days=1)).isoformat(),
                           auto_adjust=False, actions=False,
                       ))
        if history.empty:
            return []
        rows: list[PriceBar] = []
        for timestamp, row in history.iterrows():
            trading_date = timestamp.date()
            open_price = Decimal(str(row["Open"]))
            high_price = Decimal(str(row["High"]))
            low_price = Decimal(str(row["Low"]))
            close_price = Decimal(str(row["Close"]))
            volume = Decimal(str(row["Volume"]))
            # Providers sometimes include non-trading placeholder rows. They
            # are not valid OHLCV observations and must not enter the canonical
            # store or poison an otherwise good update.
            if not self._valid_ohlcv(open_price, high_price, low_price, close_price, volume):
                continue
            rows.append(
                PriceBar(
                    security_id=security.security_id,
                    trading_date=trading_date,
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=int(volume),
                    currency=security.currency,
                    exchange=security.exchange,
                    timezone=security.timezone,
                    source=self.name,
                )
            )
        return rows

    def get_dividends(
        self, security: Security, start_date: date, end_date: date
    ) -> list[DividendEvent]:
        if self.bounded_events:
            history = self._event_history(security, start_date, end_date)
            if "Dividends" not in history:
                raise ValueError("Provider history omitted the Dividends field.")
            # A successful priced history with zero events is a completed query;
            # missing/error history above must never be treated as the same state.
            dividends = history.loc[history["Dividends"] != 0]
        else:
            ticker = self._ticker(security)
            try:
                dividends = ticker.dividends
            except AttributeError:
                # yfinance 1.3.0 can fail its ``period=max`` dividends cache for
                # a small set of malformed listings.  A bounded actions-enabled
                # history is a safe fallback when price history exists; preserve
                # the original error for delisted symbols with no history so an
                # empty response is not mistaken for confirmed zero dividends.
                history = ticker.history(
                    start=start_date.isoformat(),
                    end=(end_date + timedelta(days=1)).isoformat(),
                    auto_adjust=False,
                    actions=True,
                )
                if history.empty or "Dividends" not in history:
                    raise
                dividends = history[["Dividends"]]
        if dividends.empty:
            return []
        rows: list[DividendEvent] = []
        if hasattr(dividends, "columns") and "Dividends" in dividends.columns:
            observations = (
                (timestamp, row["Dividends"], row.get("currency"))
                for timestamp, row in dividends.iterrows()
            )
        else:
            observations = ((timestamp, amount, None) for timestamp, amount in dividends.items())
        for timestamp, amount, event_currency in observations:
            # Normal yfinance responses use pandas timestamps, but a few
            # malformed/legacy responses expose ISO date strings.  Normalize
            # both forms at the provider boundary instead of losing the
            # entire security's history.
            ex_date = (
                timestamp.date()
                if hasattr(timestamp, "date")
                else date.fromisoformat(str(timestamp)[:10])
            )
            if start_date <= ex_date <= end_date:
                try:
                    normalized_amount = Decimal(str(amount))
                except (TypeError, ValueError):
                    continue
                if not normalized_amount.is_finite() or normalized_amount < 0:
                    continue
                currency = security.currency if event_currency is None else str(event_currency).strip().upper()
                if len(currency) != 3 or not currency.isalpha():
                    raise ValueError(f"Provider returned invalid dividend currency {currency!r} for {security.ticker}.")
                rows.append(
                    DividendEvent(
                        security_id=security.security_id,
                        ticker=security.ticker,
                        exchange=security.exchange,
                        ex_date=ex_date,
                        amount=normalized_amount,
                        currency=currency,
                        # Yahoo's ordinary-dividend series does not expose
                        # enough metadata to distinguish regular, special,
                        # and return-of-capital events.  Preserve the cash
                        # event but do not invent a classification.
                        dividend_type=DividendType.UNKNOWN,
                        # yfinance exposes no stable event identifier.  Keep
                        # the synthetic fallback tied to the canonical
                        # security and economic fields rather than ticker/date
                        # alone, since tickers can be reused or corrected.
                        source_id=(
                            f"{self.name}:{security.security_id}:{ex_date.isoformat()}"
                            f":{normalized_amount}:{currency}"
                        ),
                        source_country=security.income_source_country,
                        source=self.name,
                    )
                )
        return rows

    def get_corporate_actions(
        self, security: Security, start_date: date, end_date: date
    ) -> list[CorporateAction]:
        try:
            return self._corporate_action_rows(security, start_date, end_date)
        finally:
            self._discard_cached_history(str(security.security_id))

    def _corporate_action_rows(
        self, security: Security, start_date: date, end_date: date
    ) -> list[CorporateAction]:
        actions = (self._event_history(security, start_date, end_date)
                   if self.bounded_events else self._ticker(security).actions)
        if self.bounded_events and "Stock Splits" not in actions:
            raise ValueError("Provider history omitted the Stock Splits field.")
        if actions.empty or "Stock Splits" not in actions:
            return []
        rows: list[CorporateAction] = []
        for timestamp, row in actions.iterrows():
            effective_date = timestamp.date()
            ratio = Decimal(str(row["Stock Splits"]))
            if not (start_date <= effective_date <= end_date) or ratio == Decimal(0):
                continue
            action_type = CorporateActionType.SPLIT if ratio >= 1 else CorporateActionType.REVERSE_SPLIT
            if self._KNOWN_BONUS_ISSUES.get((security.ticker, effective_date)) == ratio:
                action_type = CorporateActionType.BONUS_ISSUE
            rows.append(
                CorporateAction(
                    security_id=security.security_id,
                    effective_date=effective_date,
                    action_type=action_type,
                    ratio=ratio,
                    source=self.name,
                )
            )
        return rows

    def get_fx_rates(self, base_currency: str, start_date: date, end_date: date) -> list[FxRate]:
        currency = base_currency.upper()
        if currency == "SGD":
            return [FxRate(rate_date=start_date, base_currency="SGD", rate_to_sgd=Decimal(1), source=self.name)]
        ticker = self._ticker_symbol(f"{currency}SGD=X")
        history = (self._bounded_history(ticker, start_date, end_date, actions=False)
                   if self.bounded_events else ticker.history(
                       start=start_date.isoformat(),
                       end=(end_date + timedelta(days=1)).isoformat(),
                       auto_adjust=False, actions=False,
                   ))
        rows: list[FxRate] = []
        for timestamp, row in history.iterrows():
            rate_date = timestamp.date()
            if not start_date <= rate_date <= end_date:
                continue
            rate = Decimal(str(row["Close"]))
            if rate.is_finite() and rate > 0:
                rows.append(FxRate(rate_date=rate_date, base_currency=currency, rate_to_sgd=rate, source=self.name))
        return rows

    @staticmethod
    def _ticker_symbol(symbol: str):
        try:
            import yfinance
        except ImportError as error:  # pragma: no cover - dependency packaging check
            raise RuntimeError("Install the market-data extra to use Yahoo Finance.") from error
        return yfinance.Ticker(symbol)
