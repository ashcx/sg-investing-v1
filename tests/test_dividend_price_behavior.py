from __future__ import annotations

from datetime import date
from decimal import Decimal

from sg_investing.data.dividend_quality import audit_dividend_price_behavior
from tests.helpers import dividend, price, security


def test_price_behavior_audit_matches_a_dividend_sized_ex_date_drop():
    sec = security()
    rows = [
        price(sec, date(2024, 1, 1), "100"),
        price(sec, date(2024, 1, 2), "99"),
    ]
    report = audit_dividend_price_behavior(
        [dividend(sec, date(2024, 1, 2), "1")], rows
    )

    assert report.event_count == 1
    assert report.comparable_event_count == 1
    assert report.events_with_price_response == 1
    assert report.large_price_drops_without_dividend == 0


def test_price_behavior_audit_flags_large_unmatched_price_drops_and_currency_gaps():
    sec = security()
    rows = [
        price(sec, date(2024, 1, 1), "100"),
        price(sec, date(2024, 1, 2), "70"),
    ]
    event = dividend(sec, date(2024, 1, 2), "1", currency="JPY")
    report = audit_dividend_price_behavior([event], rows)

    assert report.comparable_event_count == 0
    assert report.currency_mismatch_events == 1
    assert report.large_price_drops_without_dividend == 0


def test_price_behavior_audit_does_not_call_every_large_market_move_a_dividend():
    sec = security()
    rows = [
        price(sec, date(2024, 1, 1), "100"),
        price(sec, date(2024, 1, 2), "70"),
    ]
    report = audit_dividend_price_behavior([], rows, large_drop_threshold=Decimal("0.20"))

    assert report.large_price_drops_without_dividend == 1
    assert "no nearby dividend event" in report.warnings[0]
