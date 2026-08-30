"""Provider boundary: calculations never import or call a market-data SDK."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from sg_investing.models import CorporateAction, DividendEvent, FxRate, PriceBar, Security


class MarketDataProvider(Protocol):
    name: str

    def get_prices(self, security: Security, start_date: date, end_date: date) -> Sequence[PriceBar]: ...

    def get_dividends(
        self, security: Security, start_date: date, end_date: date
    ) -> Sequence[DividendEvent]: ...

    def get_corporate_actions(
        self, security: Security, start_date: date, end_date: date
    ) -> Sequence[CorporateAction]: ...

    def get_fx_rates(self, base_currency: str, start_date: date, end_date: date) -> Sequence[FxRate]: ...
