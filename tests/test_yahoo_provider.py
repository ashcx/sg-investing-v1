from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from sg_investing.data.providers.yahoo import YahooFinanceProvider
from sg_investing.models import CorporateActionType, DividendType
from tests.helpers import security

pytestmark = pytest.mark.provider


class FakeTicker:
    def __init__(self, *, history=None, dividends=None, actions=None):
        self.history_frame = history if history is not None else pd.DataFrame()
        self.dividends = dividends if dividends is not None else pd.Series(dtype=float)
        self.actions = actions if actions is not None else pd.DataFrame()

    def history(self, **kwargs):
        self.history_kwargs = kwargs
        return self.history_frame


class BrokenDividendTicker(FakeTicker):
    def __init__(self, *, history):
        self.history_frame = history

    @property
    def dividends(self):
        raise AttributeError("broken dividends cache")


class FakeYFinance:
    def __init__(self, *, tickers=None, download_frame=None):
        self.tickers = tickers or {}
        self.download_frame = download_frame if download_frame is not None else pd.DataFrame()
        self.download_kwargs = None

    def Ticker(self, ticker):
        return self.tickers[ticker]

    def download(self, **kwargs):
        self.download_kwargs = kwargs
        return self.download_frame


def frame(rows):
    return pd.DataFrame(rows, index=pd.to_datetime([row[0] for row in rows])).drop(columns=[0])


def test_valid_ohlcv_requires_finite_positive_close_and_valid_relationships():
    valid = ("100", "110", "90", "105", "100")
    assert YahooFinanceProvider._valid_ohlcv(*map(Decimal, valid))
    assert not YahooFinanceProvider._valid_ohlcv(*map(Decimal, ("100", "90", "95", "100", "1")))
    assert not YahooFinanceProvider._valid_ohlcv(*map(Decimal, ("100", "110", "90", "0", "1")))
    assert not YahooFinanceProvider._valid_ohlcv(*map(Decimal, ("100", "110", "0", "100", "1")))
    assert not YahooFinanceProvider._valid_ohlcv(*map(Decimal, ("1000001", "1000001", "1", "1", "1")))
    assert not YahooFinanceProvider._valid_ohlcv(
        *map(Decimal, ("100000000000000", "100000000000000", "1", "1", "1"))
    )


def test_single_price_fetch_filters_invalid_rows_and_sets_security_metadata():
    sec = security()
    history = pd.DataFrame(
        {
            "Open": [100, 100],
            "High": [110, 90],
            "Low": [90, 95],
            "Close": [105, 100],
            "Volume": [1000, 1000],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    fake = FakeYFinance(tickers={"TEST": FakeTicker(history=history)})
    with patch.dict(sys.modules, {"yfinance": SimpleNamespace(Ticker=fake.Ticker, download=fake.download)}):
        rows = YahooFinanceProvider().get_prices(sec, date(2024, 1, 1), date(2024, 1, 3))

    assert len(rows) == 1
    assert rows[0].trading_date == date(2024, 1, 2)
    assert rows[0].security_id == sec.security_id
    assert rows[0].currency == sec.currency
    assert rows[0].exchange == sec.exchange
    assert rows[0].source == "yahoo_finance"


def test_batch_price_fetch_isolates_missing_ticker_and_invalid_rows():
    target = security()
    missing = security(ticker="MISSING", security_id=security(ticker="MISSING").security_id)
    columns = pd.MultiIndex.from_product([["TEST"], ["Open", "High", "Low", "Close", "Volume"]])
    download_frame = pd.DataFrame(
        [[100, 110, 90, 105, 1000], [100, 90, 95, 100, 1000]],
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
        columns=columns,
    )
    fake = FakeYFinance(download_frame=download_frame)
    with patch.dict(sys.modules, {"yfinance": SimpleNamespace(Ticker=fake.Ticker, download=fake.download)}):
        rows_by_security, errors, warnings = YahooFinanceProvider().get_prices_batch(
            [target, missing], date(2024, 1, 1), date(2024, 1, 3), workers=1
        )

    assert [row.trading_date for row in rows_by_security[target.security_id]] == [date(2024, 1, 2)]
    assert missing.security_id in errors
    assert "ticker column" in errors[missing.security_id]
    assert warnings[target.security_id] == "Quarantined 1 invalid raw OHLCV rows."
    assert fake.download_kwargs["end"] == "2024-01-04"
    assert fake.download_kwargs["auto_adjust"] is False


def test_batch_price_fetch_reports_all_invalid_rows_as_an_error():
    sec = security()
    columns = pd.MultiIndex.from_product([["TEST"], ["Open", "High", "Low", "Close", "Volume"]])
    download_frame = pd.DataFrame(
        [[100, 90, 95, 100, 1000]],
        index=pd.to_datetime(["2024-01-02"]),
        columns=columns,
    )
    fake = FakeYFinance(download_frame=download_frame)
    with patch.dict(sys.modules, {"yfinance": SimpleNamespace(Ticker=fake.Ticker, download=fake.download)}):
        rows_by_security, errors, warnings = YahooFinanceProvider().get_prices_batch(
            [sec], date(2024, 1, 1), date(2024, 1, 2)
        )
    assert rows_by_security == {}
    assert errors[sec.security_id] == "All 1 raw OHLCV rows failed validation."
    assert warnings == {}


def test_dividends_are_filtered_to_requested_range_and_normalized():
    sec = security()
    series = pd.Series(
        [1.25, 2.0, 3.0],
        index=pd.to_datetime(["2023-12-31", "2024-01-02", "2024-02-01"]),
    )
    fake = FakeYFinance(tickers={"TEST": FakeTicker(dividends=series)})
    with patch.dict(sys.modules, {"yfinance": SimpleNamespace(Ticker=fake.Ticker, download=fake.download)}):
        rows = YahooFinanceProvider().get_dividends(sec, date(2024, 1, 1), date(2024, 1, 31))
    assert len(rows) == 1
    assert rows[0].ex_date == date(2024, 1, 2)
    assert rows[0].amount == Decimal("2.0")
    assert rows[0].pay_date is None
    assert rows[0].dividend_type == DividendType.UNKNOWN
    assert rows[0].ticker == sec.ticker
    assert rows[0].exchange == sec.exchange
    assert rows[0].source_country == "US"
    assert str(sec.security_id) in (rows[0].source_id or "")
    assert "TEST:2024-01-02" not in (rows[0].source_id or "")


def test_dividends_accept_iso_date_index_values():
    sec = security()
    series = pd.Series([Decimal("1.25")], index=["2024-01-02"])
    fake = FakeYFinance(tickers={"TEST": FakeTicker(dividends=series)})
    with patch.dict(sys.modules, {"yfinance": SimpleNamespace(Ticker=fake.Ticker, download=fake.download)}):
        rows = YahooFinanceProvider().get_dividends(sec, date(2024, 1, 1), date(2024, 1, 31))
    assert [(row.ex_date, row.amount) for row in rows] == [(date(2024, 1, 2), Decimal("1.25"))]


def test_dividends_preserve_event_currency_when_yahoo_returns_it():
    sec = security(currency="SGD", market="SG", exchange="SGX")
    frame = pd.DataFrame(
        {"Dividends": [7.0], "currency": ["JPY"]},
        index=pd.to_datetime(["2024-01-02"]),
    )
    fake = FakeYFinance(tickers={"TEST": FakeTicker(dividends=frame)})
    with patch.dict(sys.modules, {"yfinance": SimpleNamespace(Ticker=fake.Ticker, download=fake.download)}):
        rows = YahooFinanceProvider().get_dividends(sec, date(2024, 1, 1), date(2024, 1, 31))
    assert len(rows) == 1
    assert rows[0].currency == "JPY"


def test_dividends_fall_back_to_bounded_actions_history():
    sec = security()
    history = pd.DataFrame(
        {"Dividends": [1.5]},
        index=pd.to_datetime(["2024-01-02"]),
    )
    fake = FakeYFinance(tickers={"TEST": BrokenDividendTicker(history=history)})
    with patch.dict(sys.modules, {"yfinance": SimpleNamespace(Ticker=fake.Ticker, download=fake.download)}):
        rows = YahooFinanceProvider().get_dividends(sec, date(2024, 1, 1), date(2024, 1, 31))
    assert len(rows) == 1
    assert rows[0].amount == Decimal("1.5")


def test_corporate_actions_classify_splits_and_ignore_zero_rows():
    sec = security()
    actions = pd.DataFrame(
        {"Stock Splits": [2.0, 0.5, 0.0]},
        index=pd.to_datetime(["2024-01-02", "2024-02-01", "2024-03-01"]),
    )
    fake = FakeYFinance(tickers={"TEST": FakeTicker(actions=actions)})
    with patch.dict(sys.modules, {"yfinance": SimpleNamespace(Ticker=fake.Ticker, download=fake.download)}):
        rows = YahooFinanceProvider().get_corporate_actions(sec, date(2024, 1, 1), date(2024, 3, 1))
    assert [(row.ratio, row.action_type) for row in rows] == [
        (Decimal(2), CorporateActionType.SPLIT),
        (Decimal("0.5"), CorporateActionType.REVERSE_SPLIT),
    ]


def test_dbs_bonus_issue_is_not_normalized_as_a_stock_split():
    sec = security(ticker="D05.SI", market="SG", exchange="SGX")
    actions = pd.DataFrame(
        {"Stock Splits": [1.1]},
        index=pd.to_datetime(["2024-04-22"]),
    )
    fake = FakeYFinance(tickers={"D05.SI": FakeTicker(actions=actions)})
    with patch.dict(sys.modules, {"yfinance": SimpleNamespace(Ticker=fake.Ticker, download=fake.download)}):
        rows = YahooFinanceProvider().get_corporate_actions(sec, date(2024, 1, 1), date(2024, 12, 31))
    assert [(row.ratio, row.action_type) for row in rows] == [
        (Decimal("1.1"), CorporateActionType.BONUS_ISSUE)
    ]


def test_fx_fetch_filters_invalid_rates_and_sgd_is_identity():
    history = pd.DataFrame(
        {"Close": [1.30, 0.0, float("nan"), 1.35]},
        index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
    )
    fake = FakeYFinance(tickers={"USDSGD=X": FakeTicker(history=history)})
    with patch.dict(sys.modules, {"yfinance": SimpleNamespace(Ticker=fake.Ticker, download=fake.download)}):
        provider = YahooFinanceProvider()
        rows = provider.get_fx_rates("usd", date(2024, 1, 1), date(2024, 1, 5))
        sgd_rows = provider.get_fx_rates("SGD", date(2024, 1, 1), date(2024, 1, 5))
    assert [(row.rate_date, row.rate_to_sgd) for row in rows] == [
        (date(2024, 1, 2), Decimal("1.30")),
        (date(2024, 1, 5), Decimal("1.35")),
    ]
    assert len(sgd_rows) == 1
    assert sgd_rows[0].rate_date == date(2024, 1, 1)
    assert sgd_rows[0].rate_to_sgd == 1


def test_empty_batch_does_not_call_provider():
    fake = FakeYFinance()
    with patch.dict(sys.modules, {"yfinance": SimpleNamespace(Ticker=fake.Ticker, download=fake.download)}):
        result = YahooFinanceProvider().get_prices_batch([], date(2024, 1, 1), date(2024, 1, 2))
    assert result == ({}, {}, {})
