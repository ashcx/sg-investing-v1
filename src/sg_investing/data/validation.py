"""Independent validation of normalized market data before persistence."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from sg_investing.models import (
    CorporateAction,
    DataQualityStatus,
    DividendEvent,
    DividendType,
    FxRate,
    PriceBar,
)


class ValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: DataQualityStatus
    errors: list[str]
    warnings: list[str]
    row_count: int

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _report(*, errors: list[str], warnings: list[str], row_count: int) -> ValidationReport:
    return ValidationReport(
        status=DataQualityStatus.FAILED if errors else DataQualityStatus.WARNING if warnings else DataQualityStatus.OK,
        errors=errors,
        warnings=warnings,
        row_count=row_count,
    )


def validate_prices(rows: Iterable[PriceBar]) -> ValidationReport:
    rows = list(rows)
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[tuple[object, object]] = set()
    for row in rows:
        key = (row.security_id, row.trading_date)
        if key in seen:
            errors.append(f"Duplicate price observation for {row.security_id} on {row.trading_date}.")
        seen.add(key)
        if not (row.low <= row.open <= row.high and row.low <= row.close <= row.high):
            errors.append(f"Invalid OHLC relationship for {row.security_id} on {row.trading_date}.")
        if row.close == Decimal("0"):
            errors.append(f"Unexpected zero close for {row.security_id} on {row.trading_date}.")
    return _report(errors=errors, warnings=warnings, row_count=len(rows))


def validate_dividends(rows: Iterable[DividendEvent]) -> ValidationReport:
    rows = list(rows)
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[tuple[object, ...]] = set()
    for row in rows:
        key = dividend_event_key(row)
        if key in seen:
            errors.append(f"Duplicate dividend event for {row.security_id} on {row.ex_date}.")
        seen.add(key)
        if len(row.currency) != 3 or not row.currency.isalpha() or row.currency != row.currency.upper():
            errors.append(f"Invalid dividend currency for {row.security_id} on {row.ex_date}.")
        if row.dividend_type not in set(DividendType):
            errors.append(f"Invalid dividend type for {row.security_id} on {row.ex_date}.")
        if row.pay_date and row.pay_date < row.ex_date:
            errors.append(f"Dividend pay date precedes ex-date for {row.security_id} on {row.ex_date}.")
        if row.record_date and row.record_date < row.ex_date:
            warnings.append(
                f"Dividend record date precedes ex-date for {row.security_id} on {row.ex_date}."
            )
    return _report(errors=errors, warnings=warnings, row_count=len(rows))


def dividend_event_key(row: DividendEvent) -> tuple[object, ...]:
    """Return a stable key for one provider observation/economic event.

    A provider event ID is authoritative when available.  The fallback keeps
    the old archive's correction behavior (same security/date/currency/type is
    replaced by the newest observation) while preventing a different dividend
    type from being collapsed into the regular event.
    """

    if row.source_id:
        return ("source", row.source, row.source_id)
    return dividend_economic_key(row)


def dividend_economic_key(row: DividendEvent) -> tuple[object, ...]:
    """Return the provider-independent identity used during migrations."""

    dividend_type = (
        DividendType.REGULAR
        if row.dividend_type == DividendType.LEGACY_ORDINARY
        else row.dividend_type
    )
    return ("economic", row.security_id, row.ex_date, row.currency, dividend_type)


def validate_corporate_actions(rows: Iterable[CorporateAction]) -> ValidationReport:
    rows = list(rows)
    errors: list[str] = []
    seen: set[tuple[object, object, object]] = set()
    for row in rows:
        key = (row.security_id, row.effective_date, row.action_type)
        if key in seen:
            errors.append(
                f"Duplicate corporate action for {row.security_id} on {row.effective_date}."
            )
        seen.add(key)
        if row.ratio <= Decimal("0"):
            errors.append(
                f"Non-positive corporate-action ratio for {row.security_id} on {row.effective_date}."
            )
    return _report(errors=errors, warnings=[], row_count=len(rows))


def validate_fx(rows: Iterable[FxRate]) -> ValidationReport:
    rows = list(rows)
    errors: list[str] = []
    seen: set[tuple[str, object]] = set()
    for row in rows:
        key = (row.base_currency, row.rate_date)
        if key in seen:
            errors.append(f"Duplicate {row.base_currency}/SGD rate on {row.rate_date}.")
        seen.add(key)
        if row.base_currency == "SGD" and row.rate_to_sgd != Decimal("1"):
            errors.append("SGD/SGD must equal 1.")
    return _report(errors=errors, warnings=[], row_count=len(rows))
