"""Incremental, per-security ingestion that preserves valid stored data."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from sg_investing.data.providers.base import MarketDataProvider
from sg_investing.data.storage import DatasetManifest, ParquetStore
from sg_investing.models import DataQualityStatus, FxRate, Security


class SecurityUpdateResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    security_id: str
    ticker: str
    status: DataQualityStatus
    start_date: date
    end_date: date
    rows_written: int = 0
    error: str | None = None
    manifests: list[DatasetManifest] = []


def latest_stored_price_date(store: ParquetStore, *, market: str, security: Security) -> date | None:
    dates: list[date] = []
    directory = Path(store.root) / "prices" / f"market={market.upper()}"
    for path in directory.glob("year=*.parquet") if directory.exists() else []:
        year = int(path.stem.split("=")[1])
        dates.extend(
            row.trading_date
            for row in store.read_prices(market=market, year=year)
            if row.security_id == security.security_id
        )
    return max(dates) if dates else None


def _latest_event_date(store: ParquetStore, *, dataset: str, security: Security) -> date | None:
    directory = Path(store.root) / dataset
    if not directory.exists():
        return None
    dates: list[date] = []
    for path in directory.glob("year=*.parquet"):
        year = int(path.stem.split("=")[1])
        rows = (
            store.read_dividends(year=year)
            if dataset == "dividends"
            else store.read_corporate_actions(year=year)
        )
        dates.extend(
            (row.ex_date if dataset == "dividends" else row.effective_date)
            for row in rows
            if row.security_id == security.security_id
        )
    return max(dates) if dates else None


def update_fx_rates(
    *,
    store: ParquetStore,
    provider: MarketDataProvider,
    base_currency: str,
    end_date: date,
    start_floor: date = date(2000, 1, 1),
    reconciliation_days: int = 7,
) -> list[FxRate]:
    """Refresh a currency's independent FX history and return the fetched rows."""

    currency = base_currency.upper()
    directory = Path(store.root) / "fx" / f"pair={currency}_SGD"
    dates: list[date] = []
    for path in directory.glob("year=*.parquet") if directory.exists() else []:
        year = int(path.stem.split("=")[1])
        dates.extend(row.rate_date for row in store.read_fx(base_currency=currency, year=year))
    start_date = start_floor if not dates else max(start_floor, max(dates) - timedelta(days=reconciliation_days))
    rows = list(provider.get_fx_rates(currency, start_date, end_date))
    for row in rows:
        if row.base_currency != currency:
            raise ValueError(
                f"Provider returned FX currency {row.base_currency} for requested {currency}."
            )
        if not start_date <= row.rate_date <= end_date:
            raise ValueError(f"Provider returned FX date {row.rate_date} outside requested range.")
    store.upsert_fx(rows)
    return rows


def update_security_prices(
    *,
    store: ParquetStore,
    provider: MarketDataProvider,
    security: Security,
    end_date: date,
    start_floor: date = date(2000, 1, 1),
    reconciliation_days: int = 7,
    pipeline_version: str = "0.1.0",
    include_dividends: bool = True,
) -> SecurityUpdateResult:
    """Fetch just the missing/reconciliation window and atomically merge valid data."""

    latest = latest_stored_price_date(store, market=security.market, security=security)
    start_date = start_floor if latest is None else max(start_floor, latest - timedelta(days=reconciliation_days))
    try:
        rows = list(provider.get_prices(security, start_date, end_date))
        for row in rows:
            if row.security_id != security.security_id:
                raise ValueError("Provider returned a price row for another security.")
            if row.currency != security.currency:
                raise ValueError("Provider returned a price row with the wrong currency.")
            if row.exchange != security.exchange:
                raise ValueError("Provider returned a price row with the wrong exchange.")
            if not start_date <= row.trading_date <= end_date:
                raise ValueError("Provider returned a price row outside the requested range.")
        latest_dividend = _latest_event_date(store, dataset="dividends", security=security)
        dividend_start = start_floor if latest_dividend is None else max(
            start_floor, latest_dividend - timedelta(days=reconciliation_days)
        )
        latest_action = _latest_event_date(store, dataset="corporate_actions", security=security)
        action_start = start_floor if latest_action is None else max(
            start_floor, latest_action - timedelta(days=reconciliation_days)
        )
        dividend_rows = list(provider.get_dividends(security, dividend_start, end_date)) if include_dividends else []
        for row in dividend_rows:
            if row.security_id != security.security_id:
                raise ValueError("Provider returned a dividend for another security.")
            if not dividend_start <= row.ex_date <= end_date:
                raise ValueError("Provider returned a dividend outside the requested range.")
        action_rows = list(provider.get_corporate_actions(security, action_start, end_date))
        for row in action_rows:
            if row.security_id != security.security_id:
                raise ValueError("Provider returned a corporate action for another security.")
            if not action_start <= row.effective_date <= end_date:
                raise ValueError("Provider returned a corporate action outside the requested range.")

        # Fetch and validate every dataset before changing the store. This
        # prevents malformed event data from leaving a partially updated
        # security behind after a valid price response.
        manifests = store.upsert_prices(
            market=security.market,
            rows=rows,
            pipeline_version=pipeline_version,
        ) if rows else []
        if include_dividends:
            store.upsert_dividends(dividend_rows)
        store.upsert_corporate_actions(action_rows)
    except Exception as error:  # Error details are retained per security; other updates can continue.
        return SecurityUpdateResult(
            security_id=str(security.security_id),
            ticker=security.ticker,
            status=DataQualityStatus.FAILED,
            start_date=start_date,
            end_date=end_date,
            error=str(error),
        )
    return SecurityUpdateResult(
        security_id=str(security.security_id),
        ticker=security.ticker,
        status=DataQualityStatus.OK if rows else DataQualityStatus.WARNING,
        start_date=start_date,
        end_date=end_date,
        rows_written=len(rows),
        manifests=manifests,
        error=None if rows else "Provider returned no price rows.",
    )
