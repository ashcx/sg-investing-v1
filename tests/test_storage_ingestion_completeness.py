from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from tempfile import TemporaryDirectory

import pytest

from sg_investing.data.ingestion import update_fx_rates, update_security_prices
from sg_investing.data.storage import ParquetStore
from sg_investing.models import (
    CorporateAction,
    DividendEvent,
    DividendType,
    FxRate,
    PriceBar,
    Security,
)
from tests.helpers import OTHER_SECURITY_ID, action, dividend, fx, price, security

pytestmark = pytest.mark.integration


class RecordingProvider:
    name = "recording"

    def __init__(
        self,
        *,
        prices=(),
        dividends=(),
        actions=(),
        fx_rates=(),
        error: Exception | None = None,
        price_error: Exception | None = None,
        dividend_error: Exception | None = None,
        action_error: Exception | None = None,
        fx_error: Exception | None = None,
    ):
        self.prices = list(prices)
        self.dividends = list(dividends)
        self.actions = list(actions)
        self.fx_rates = list(fx_rates)
        self.error = error
        self.price_error = price_error
        self.dividend_error = dividend_error
        self.action_error = action_error
        self.fx_error = fx_error
        self.price_calls = []
        self.dividend_calls = []
        self.action_calls = []
        self.fx_calls = []

    def get_prices(self, security: Security, start_date: date, end_date: date) -> list[PriceBar]:
        self.price_calls.append((security, start_date, end_date))
        if self.price_error or self.error:
            raise self.price_error or self.error
        return self.prices

    def get_dividends(self, security: Security, start_date: date, end_date: date) -> list[DividendEvent]:
        self.dividend_calls.append((security, start_date, end_date))
        if self.dividend_error or self.error:
            raise self.dividend_error or self.error
        return self.dividends

    def get_corporate_actions(self, security: Security, start_date: date, end_date: date) -> list[CorporateAction]:
        self.action_calls.append((security, start_date, end_date))
        if self.action_error or self.error:
            raise self.action_error or self.error
        return self.actions

    def get_fx_rates(self, base_currency: str, start_date: date, end_date: date) -> list[FxRate]:
        self.fx_calls.append((base_currency, start_date, end_date))
        if self.fx_error or self.error:
            raise self.fx_error or self.error
        return self.fx_rates


def test_price_partitions_and_manifests_are_correct_across_years():
    sec = security()
    rows = [price(sec, date(2023, 12, 29), "99"), price(sec, date(2024, 1, 2), "100")]
    with TemporaryDirectory() as temporary:
        store = ParquetStore(temporary)
        manifests = store.upsert_prices(market="us", rows=rows, pipeline_version="test-1")

        assert {manifest.first_date for manifest in manifests} == {"2023-12-29", "2024-01-02"}
        assert {manifest.last_date for manifest in manifests} == {"2023-12-29", "2024-01-02"}
        assert all(manifest.row_count == 1 for manifest in manifests)
        assert all(manifest.pipeline_version == "test-1" for manifest in manifests)
        assert [row.close for row in store.read_prices(market="US", year=2023)] == [Decimal("99.0000000000")]
        assert [row.close for row in store.read_prices(market="US", year=2024)] == [Decimal("100.0000000000")]


def test_empty_upserts_are_safe_no_ops():
    with TemporaryDirectory() as temporary:
        store = ParquetStore(temporary)
        assert store.upsert_prices(market="US", rows=[], pipeline_version="test") == []
        store.upsert_dividends([])
        store.upsert_corporate_actions([])
        store.upsert_fx([])
        assert store.read_prices(market="US", year=2024) == []
        assert store.read_dividends(year=2024) == []
        assert store.read_corporate_actions(year=2024) == []
        assert store.read_fx(base_currency="USD", year=2024) == []


def test_event_upserts_replace_the_same_canonical_event():
    sec = security()
    first_dividend = dividend(sec, date(2024, 2, 1), "1")
    revised_dividend = dividend(sec, date(2024, 2, 1), "1", pay_date=date(2024, 3, 1))
    first_fx = fx(date(2024, 2, 1), "1.30")
    revised_fx = fx(date(2024, 2, 1), "1.35")
    with TemporaryDirectory() as temporary:
        store = ParquetStore(temporary)
        store.upsert_dividends([first_dividend])
        store.upsert_dividends([revised_dividend])
        store.upsert_fx([first_fx])
        store.upsert_fx([revised_fx])

        assert store.read_dividends(year=2024) == [revised_dividend]
        assert store.read_fx(base_currency="USD", year=2024) == [revised_fx]


def test_dividend_amount_correction_replaces_the_prior_observation():
    sec = security()
    first = dividend(sec, date(2024, 2, 1), "2").model_copy(
        update={"retrieved_at": datetime(2024, 2, 2, tzinfo=UTC)}
    )
    correction = dividend(sec, date(2024, 2, 1), "2.50").model_copy(
        update={"retrieved_at": datetime(2024, 2, 3, tzinfo=UTC)}
    )

    with TemporaryDirectory() as temporary:
        store = ParquetStore(temporary)
        store.upsert_dividends([first])
        store.upsert_dividends([correction])

        stored = store.read_dividends(year=2024)
        assert len(stored) == 1
        assert stored[0].amount == Decimal("2.50")


def test_dividend_provider_identity_migrates_a_legacy_event_without_duplication():
    sec = security()
    legacy = dividend(sec, date(2024, 2, 1), "2")
    provider_observation = legacy.model_copy(
        update={
            "source": "yahoo_finance",
            "source_id": "yahoo_finance:TEST:2024-02-01",
            "dividend_type": DividendType.REGULAR,
        }
    )
    with TemporaryDirectory() as temporary:
        store = ParquetStore(temporary)
        store.upsert_dividends([legacy])
        store.upsert_dividends([provider_observation])

        stored = store.read_dividends(year=2024)
        assert len(stored) == 1
        assert stored[0].source_id == provider_observation.source_id


def test_dividend_provider_identity_allows_type_reclassification_without_duplication():
    sec = security()
    regular = dividend(sec, date(2024, 2, 1), "2").model_copy(
        update={
            "source": "yahoo_finance",
            "source_id": "yahoo_finance:security:2024-02-01:2:USD",
            "dividend_type": DividendType.REGULAR,
        }
    )
    unknown = regular.model_copy(update={"dividend_type": DividendType.UNKNOWN})
    with TemporaryDirectory() as temporary:
        store = ParquetStore(temporary)
        store.upsert_dividends([regular])
        store.upsert_dividends([unknown])
        assert store.read_dividends(year=2024) == [unknown]


def test_dividend_amount_precision_survives_parquet_round_trip():
    sec = security()
    event = dividend(sec, date(2024, 2, 1), "0.695129")
    with TemporaryDirectory() as temporary:
        store = ParquetStore(temporary)
        store.upsert_dividends([event])
        assert store.read_dividends(year=2024)[0].amount == Decimal("0.695129")


def test_corporate_action_ratio_correction_replaces_the_prior_observation():
    sec = security()
    first = action(sec, date(2024, 2, 1), "2").model_copy(
        update={"retrieved_at": datetime(2024, 2, 2, tzinfo=UTC)}
    )
    correction = action(sec, date(2024, 2, 1), "4").model_copy(
        update={"retrieved_at": datetime(2024, 2, 3, tzinfo=UTC)}
    )

    with TemporaryDirectory() as temporary:
        store = ParquetStore(temporary)
        store.upsert_corporate_actions([first])
        store.upsert_corporate_actions([correction])

        stored = store.read_corporate_actions(year=2024)
        assert len(stored) == 1
        assert stored[0].ratio == Decimal(4)


def test_invalid_fx_cannot_replace_a_valid_existing_rate():
    valid = fx(date(2024, 2, 1), "1.30")
    invalid_sgd = fx(date(2024, 2, 1), "1.30", currency="SGD")
    with TemporaryDirectory() as temporary:
        store = ParquetStore(temporary)
        store.upsert_fx([valid])
        with pytest.raises(ValueError, match="SGD/SGD"):
            store.upsert_fx([invalid_sgd])
        assert store.read_fx(base_currency="USD", year=2024) == [valid]


def test_corporate_actions_round_trip_across_year_partitions():
    sec = security()
    rows = [action(sec, date(2023, 12, 29), "2"), action(sec, date(2024, 1, 2), "0.5")]
    with TemporaryDirectory() as temporary:
        store = ParquetStore(temporary)
        store.upsert_corporate_actions(rows)
        assert store.read_corporate_actions(year=2023) == [rows[0]]
        assert store.read_corporate_actions(year=2024) == [rows[1]]


def test_empty_price_response_is_a_warning_but_event_updates_are_still_attempted():
    sec = security()
    event = dividend(sec, date(2024, 2, 1), "1")
    provider = RecordingProvider(dividends=[event])
    with TemporaryDirectory() as temporary:
        store = ParquetStore(temporary)
        result = update_security_prices(
            store=store,
            provider=provider,
            security=sec,
            end_date=date(2024, 4, 1),
            start_floor=date(2024, 1, 1),
        )

        assert result.status.value == "WARNING"
        assert result.rows_written == 0
        assert result.error == "Provider returned no price rows."
        assert store.read_dividends(year=2024) == [event]
        assert provider.dividend_calls[0][1:] == (date(2024, 1, 1), date(2024, 4, 1))


def test_fx_update_reconciles_from_the_latest_stored_date():
    first = fx(date(2024, 1, 10), "1.30")
    revised = fx(date(2024, 1, 10), "1.31")
    next_rate = fx(date(2024, 1, 11), "1.32")
    provider = RecordingProvider(fx_rates=[revised, next_rate])
    with TemporaryDirectory() as temporary:
        store = ParquetStore(temporary)
        store.upsert_fx([first])
        rows = update_fx_rates(
            store=store,
            provider=provider,
            base_currency="usd",
            end_date=date(2024, 1, 11),
            start_floor=date(2000, 1, 1),
            reconciliation_days=3,
        )

        assert rows == [revised, next_rate]
        assert provider.fx_calls == [("USD", date(2024, 1, 7), date(2024, 1, 11))]
        assert store.read_fx(base_currency="USD", year=2024) == [revised, next_rate]


def test_price_rows_for_another_security_are_rejected_before_persistence():
    sec = security()
    foreign_row = price(security(security_id=sec.security_id), date(2024, 1, 2), "100").model_copy(
        update={"security_id": OTHER_SECURITY_ID}
    )
    provider = RecordingProvider(prices=[foreign_row])
    with TemporaryDirectory() as temporary:
        store = ParquetStore(temporary)
        result = update_security_prices(
            store=store,
            provider=provider,
            security=sec,
            end_date=date(2024, 1, 2),
        )

        assert result.status.value == "FAILED"
        assert "security" in (result.error or "").lower()
        assert store.read_prices(market="US", year=2024) == []


def test_price_rows_outside_window_or_with_wrong_currency_are_rejected():
    sec = security()
    outside = price(sec, date(2024, 1, 3), "100")
    wrong_currency = price(sec, date(2024, 1, 2), "100").model_copy(update={"currency": "SGD"})
    wrong_exchange = price(sec, date(2024, 1, 2), "100").model_copy(update={"exchange": "NASDAQ"})
    for bad_row, expected_text in (
        (outside, "range"),
        (wrong_currency, "currency"),
        (wrong_exchange, "exchange"),
    ):
        provider = RecordingProvider(prices=[bad_row])
        with TemporaryDirectory() as temporary:
            result = update_security_prices(
                store=ParquetStore(temporary),
                provider=provider,
                security=sec,
                end_date=date(2024, 1, 2),
            )
            assert result.status.value == "FAILED"
            assert expected_text in (result.error or "").lower()


def test_event_provider_failure_is_visible_in_the_update_result():
    sec = security()
    provider = RecordingProvider(
        prices=[price(sec, date(2024, 1, 2))],
        dividend_error=RuntimeError("event outage"),
    )
    with TemporaryDirectory() as temporary:
        store = ParquetStore(temporary)
        result = update_security_prices(store=store, provider=provider, security=sec, end_date=date(2024, 1, 2))
        assert result.status.value == "FAILED"
        assert result.error == "event outage"
        assert store.read_prices(market="US", year=2024) == []


def test_wrong_security_and_range_are_rejected_for_events():
    sec = security()
    wrong_dividend = dividend(security(security_id=OTHER_SECURITY_ID), date(2024, 1, 2), "1")
    wrong_action = action(security(security_id=OTHER_SECURITY_ID), date(2024, 1, 2), "2")
    for dividends, actions, text in (
        ([wrong_dividend], [], "dividend"),
        ([], [wrong_action], "corporate action"),
    ):
        provider = RecordingProvider(
            prices=[price(sec, date(2024, 1, 2))], dividends=dividends, actions=actions
        )
        with TemporaryDirectory() as temporary:
            store = ParquetStore(temporary)
            result = update_security_prices(store=store, provider=provider, security=sec, end_date=date(2024, 1, 2))
            assert result.status.value == "FAILED"
            assert text in (result.error or "").lower()
            assert store.read_prices(market="US", year=2024) == []


def test_fx_provider_failure_does_not_replace_existing_data():
    existing = fx(date(2024, 1, 2), "1.30")
    provider = RecordingProvider(fx_error=RuntimeError("FX outage"))
    with TemporaryDirectory() as temporary:
        store = ParquetStore(temporary)
        store.upsert_fx([existing])
        with pytest.raises(RuntimeError, match="FX outage"):
            update_fx_rates(
                store=store,
                provider=provider,
                base_currency="USD",
                end_date=date(2024, 1, 3),
            )
        assert store.read_fx(base_currency="USD", year=2024) == [existing]


def test_fx_rows_for_another_currency_are_rejected():
    provider = RecordingProvider(fx_rates=[fx(date(2024, 1, 2), "1.4", currency="EUR")])
    with TemporaryDirectory() as temporary, pytest.raises(ValueError, match="currency"):
        update_fx_rates(
            store=ParquetStore(temporary),
            provider=provider,
            base_currency="USD",
            end_date=date(2024, 1, 2),
        )
