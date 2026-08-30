"""High-level application API for scripts and a future GitHub Pages adapter."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml

from sg_investing.analysis import analyze_security
from sg_investing.data.storage import ParquetStore
from sg_investing.models import AnalysisResult, AnalysisScenario, TaxRule
from sg_investing.universe.catalog import UniverseCatalog, load_catalog


class SGInvestingEngine:
    """Loads configured metadata and canonical Parquet data into public results."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.catalog: UniverseCatalog = load_catalog(self.root / "config" / "universe.yaml")
        self.store = ParquetStore(self.root / "data")
        rules = yaml.safe_load((self.root / "config" / "tax_rules.yaml").read_text(encoding="utf-8"))
        self.tax_rules = [TaxRule.model_validate(rule) for rule in rules.get("rules", [])]

    @staticmethod
    def _years(start_date: date, end_date: date) -> range:
        return range(start_date.year, end_date.year + 1)

    def analyze(
        self,
        *,
        ticker: str,
        start_date: date,
        end_date: date,
        initial_sgd: Decimal | int | str,
        scenario: AnalysisScenario | None = None,
    ) -> AnalysisResult:
        security = self.catalog.security_by_ticker(ticker)
        years = self._years(start_date, end_date)
        prices = [
            row for year in years for row in self.store.read_prices(market=security.market, year=year)
            if row.security_id == security.security_id
        ]
        dividends = [
            row for year in years for row in self.store.read_dividends(year=year)
            if row.security_id == security.security_id
        ]
        actions = [
            row for year in years for row in self.store.read_corporate_actions(year=year)
            if row.security_id == security.security_id
        ]
        fx = [
            row for year in years for row in self.store.read_fx(base_currency=security.currency, year=year)
        ]
        return analyze_security(
            security=security,
            prices=prices,
            fx_rates=fx,
            start_date=start_date,
            end_date=end_date,
            initial_sgd=initial_sgd,
            scenario=scenario,
            dividends=dividends,
            corporate_actions=actions,
            tax_rules=self.tax_rules,
        )
