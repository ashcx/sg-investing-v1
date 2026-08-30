from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sg_investing.models import (
    AssetType,
    CorporateAction,
    CorporateActionType,
    DividendEvent,
    DistributionPolicy,
    FxRate,
    PriceBar,
    Security,
    TaxRule,
)


TEST_SECURITY_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_SECURITY_ID = UUID("22222222-2222-2222-2222-222222222222")


def security(
    *,
    security_id: UUID = TEST_SECURITY_ID,
    ticker: str = "TEST",
    name: str | None = None,
    currency: str = "USD",
    market: str = "US",
    exchange: str = "NYSE",
    asset_type: AssetType = AssetType.EQUITY,
    distribution_policy: DistributionPolicy = DistributionPolicy.DISTRIBUTING,
    income_source_country: str | None = "US",
) -> Security:
    return Security(
        security_id=security_id,
        ticker=ticker,
        exchange=exchange,
        market=market,
        name=name if name is not None else f"Synthetic {ticker}",
        currency=currency,
        asset_type=asset_type,
        income_source_country=income_source_country,
        distribution_policy=distribution_policy,
        timezone="America/New_York" if market == "US" else "Asia/Singapore",
    )


def price(
    security_row: Security,
    trading_date: date,
    close: str = "100",
    *,
    open_price: str | None = None,
    high: str | None = None,
    low: str | None = None,
    volume: int = 1,
    source: str = "synthetic",
) -> PriceBar:
    close_value = Decimal(close)
    return PriceBar(
        security_id=security_row.security_id,
        trading_date=trading_date,
        open=Decimal(open_price or close),
        high=Decimal(high or close),
        low=Decimal(low or close),
        close=close_value,
        volume=volume,
        currency=security_row.currency,
        exchange=security_row.exchange,
        timezone=security_row.timezone,
        source=source,
        retrieved_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def fx(rate_date: date, rate: str = "1.30", *, currency: str = "USD") -> FxRate:
    return FxRate(
        rate_date=rate_date,
        base_currency=currency,
        rate_to_sgd=Decimal(rate),
        source="synthetic",
    )


def dividend(
    security_row: Security,
    ex_date: date,
    amount: str = "1",
    *,
    pay_date: date | None = None,
    currency: str | None = None,
    source_country: str | None = None,
) -> DividendEvent:
    return DividendEvent(
        security_id=security_row.security_id,
        ex_date=ex_date,
        pay_date=pay_date,
        amount=Decimal(amount),
        currency=currency or security_row.currency,
        source_country=source_country,
        source="synthetic",
    )


def action(
    security_row: Security,
    effective_date: date,
    ratio: str,
    *,
    action_type: CorporateActionType = CorporateActionType.SPLIT,
) -> CorporateAction:
    return CorporateAction(
        security_id=security_row.security_id,
        effective_date=effective_date,
        action_type=action_type,
        ratio=Decimal(ratio),
        source="synthetic",
    )


def tax_rule(
    rate: str,
    *,
    source_country: str = "US",
    effective_from: date = date(1900, 1, 1),
    effective_to: date | None = None,
    rule_id: str = "synthetic-tax",
) -> TaxRule:
    return TaxRule(
        rule_id=rule_id,
        source_country=source_country,
        rate=Decimal(rate),
        effective_from=effective_from,
        effective_to=effective_to,
    )
