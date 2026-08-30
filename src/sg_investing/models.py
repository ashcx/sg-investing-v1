"""Typed, serializable contracts shared by data and calculation layers."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

Money = Annotated[Decimal, Field(ge=0)]


class AssetType(StrEnum):
    EQUITY = "equity"
    ETF = "ETF"
    INDEX = "index"
    REIT = "REIT"
    TRUST = "trust"
    OTHER = "other"


class DistributionPolicy(StrEnum):
    ACCUMULATING = "accumulating"
    DISTRIBUTING = "distributing"
    NON_DISTRIBUTING = "non_distributing"
    UNKNOWN = "unknown"


class DividendType(StrEnum):
    """Canonical economic classifications for cash distribution events."""

    REGULAR = "regular"
    SPECIAL = "special"
    RETURN_OF_CAPITAL = "return_of_capital"
    UNKNOWN = "unknown"
    # ``ordinary`` was used by the first archive schema.  Keep it readable so
    # existing Parquet partitions remain backward compatible; new providers
    # should emit ``regular``.
    LEGACY_ORDINARY = "ordinary"


class CorporateActionType(StrEnum):
    SPLIT = "split"
    REVERSE_SPLIT = "reverse_split"
    BONUS_ISSUE = "bonus_issue"


class TransactionType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    CASH_DEPOSIT = "CASH_DEPOSIT"
    CASH_WITHDRAWAL = "CASH_WITHDRAWAL"


class DataQualityStatus(StrEnum):
    OK = "OK"
    WARNING = "WARNING"
    INCOMPLETE = "INCOMPLETE"
    FAILED = "FAILED"


class Security(BaseModel):
    """Security master row. Ticker is a provider identifier, never the primary key."""

    model_config = ConfigDict(frozen=True)

    security_id: UUID = Field(default_factory=uuid4)
    ticker: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    market: str = Field(min_length=1)
    name: str = Field(min_length=1)
    currency: str = Field(min_length=3, max_length=3)
    asset_type: AssetType
    domicile: str | None = None
    income_source_country: str | None = None
    isin: str | None = None
    cusip: str | None = None
    timezone: str = "UTC"
    active: bool = True
    distribution_policy: DistributionPolicy = DistributionPolicy.UNKNOWN
    expense_ratio: Decimal | None = Field(default=None, ge=0, le=1)

    @field_validator("ticker", "exchange", "market", "currency")
    @classmethod
    def uppercase_identifiers(cls, value: str) -> str:
        return value.strip().upper()


class PriceBar(BaseModel):
    model_config = ConfigDict(frozen=True)

    security_id: UUID
    trading_date: date
    open: Money
    high: Money
    low: Money
    close: Money
    volume: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    exchange: str
    timezone: str
    source: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        return value.upper()


class DividendEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    security_id: UUID
    ticker: str | None = None
    exchange: str | None = None
    ex_date: date
    amount: Money
    currency: str = Field(min_length=3, max_length=3)
    pay_date: date | None = None
    record_date: date | None = None
    dividend_type: DividendType = DividendType.REGULAR
    source_id: str | None = None
    source_country: str | None = None
    source: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("ticker", "exchange")
    @classmethod
    def uppercase_event_identifiers(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @field_validator("currency")
    @classmethod
    def uppercase_dividend_currency(cls, value: str) -> str:
        return value.upper()


class CorporateAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    security_id: UUID
    effective_date: date
    action_type: CorporateActionType
    ratio: Decimal = Field(gt=0)
    source: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FxRate(BaseModel):
    """One unit of base_currency equals `rate_to_sgd` SGD."""

    model_config = ConfigDict(frozen=True)

    rate_date: date
    base_currency: str = Field(min_length=3, max_length=3)
    rate_to_sgd: Decimal = Field(gt=0)
    source: str

    @field_validator("base_currency")
    @classmethod
    def uppercase_base_currency(cls, value: str) -> str:
        return value.upper()


class TaxRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_id: str
    source_country: str
    income_type: str = "dividend"
    investor_type: str = "singapore_individual"
    rate: Decimal = Field(ge=0, le=1)
    effective_from: date
    effective_to: date | None = None

    def applies_on(self, event_date: date) -> bool:
        return self.effective_from <= event_date and (
            self.effective_to is None or event_date <= self.effective_to
        )


class UniverseMembership(BaseModel):
    """Current or historical relationship between a security and a universe."""

    model_config = ConfigDict(frozen=True)

    universe: str = Field(min_length=1)
    security_id: UUID
    effective_from: date
    effective_to: date | None = None
    source: str = Field(min_length=1)


class PortfolioTransaction(BaseModel):
    """Ledger transaction. Cash amounts are always positive magnitudes."""

    model_config = ConfigDict(frozen=True)

    transaction_id: UUID = Field(default_factory=uuid4)
    transaction_date: date
    security_id: UUID | None = None
    transaction_type: TransactionType
    quantity: Decimal = Field(default=Decimal(0), ge=0)
    cash_amount: Money = Decimal(0)
    currency: str = Field(min_length=3, max_length=3)
    fees: Money = Decimal(0)

    @field_validator("currency")
    @classmethod
    def uppercase_transaction_currency(cls, value: str) -> str:
        return value.upper()


class AnalysisScenario(BaseModel):
    """Immutable inputs for an observed or investor-modeled return analysis."""

    model_config = ConfigDict(frozen=True)

    dividends_enabled: bool = True
    reinvest_dividends: bool = True
    withholding_tax_enabled: bool = True
    purchase_date_rule: str = "next_trading_day"
    valuation_date_rule: str = "previous_trading_day"
    methodology_version: str = "1.0"


class AnalysisResult(BaseModel):
    """Stable result contract for Python callers and future JSON artifacts."""

    security: Security
    period: dict[str, date]
    initial_investment_sgd: Decimal
    initial_investment_foreign_currency: Decimal
    price_return: dict[str, Decimal]
    dividends: dict[str, Decimal]
    investment: dict[str, Decimal]
    returns: dict[str, Decimal | None]
    fx: dict[str, Decimal]
    methodology: dict[str, str | bool]
    data_quality: dict[str, DataQualityStatus | list[str]]
