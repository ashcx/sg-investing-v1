from __future__ import annotations

import unittest
from pathlib import Path

import pyarrow.parquet as pq

from scripts.frontend_server import FrontendDataService


class FrontendAdapterContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = FrontendDataService()
        cls.entries = cls.service.catalog.securities
        cls.qqq = next(entry.security for entry in cls.entries if entry.security.ticker == "QQQ")

    def _params(self) -> dict[str, list[str]]:
        return {
            "security_id": [str(self.qqq.security_id)],
            "start_date": ["2024-01-02"],
            "end_date": ["2025-01-02"],
            "initial_sgd": ["10000"],
            "dividends": ["true"],
            "withholding": ["true"],
            "reinvest": ["true"],
        }

    def test_catalog_is_full_universe_and_id_safe(self) -> None:
        ids = [entry.security.security_id for entry in self.entries]
        self.assertGreaterEqual(len(ids), 3000)
        # A security can belong to more than one universe; the UI deduplicates
        # by security_id while retaining every membership row in the catalog.
        unique_ids = set(ids)
        self.assertGreaterEqual(len(unique_ids), 3000)
        equities = {entry.security.security_id: entry for entry in self.entries if entry.security.asset_type.value == "equity"}
        self.assertGreaterEqual(len(equities), 500)
        for entry in equities.values():
            self.assertEqual(self.service.security(security_id=str(entry.security.security_id)), entry.security)

    def test_price_coverage_for_catalog_equities_is_reported(self) -> None:
        equity_ids = {str(entry.security.security_id) for entry in self.entries if entry.security.asset_type.value == "equity"}
        price_ids: set[str] = set()
        for path in Path("data/prices").glob("market=*/year=*.parquet"):
            price_ids.update(str(value) for value in pq.read_table(path, columns=["security_id"]).column("security_id").to_pylist())
        covered = equity_ids & price_ids
        # The UI must expose the two currently missing rows as unavailable; all
        # other catalog equities have a canonical price row to request.
        self.assertGreaterEqual(len(covered), len(equity_ids) - 5)

    def test_analysis_series_dca_and_compare_envelopes(self) -> None:
        params = {**self._params(), "request_key": ["analysis:demo"]}
        analysis = self.service.analysis(params)
        self.assertIn("result", analysis)
        self.assertEqual(analysis["result"]["security"]["ticker"], "QQQ")
        self.assertEqual(analysis["request"]["request_key"], "analysis:demo")
        series = self.service.series(self._params())
        self.assertGreater(len(series["result"]["points"]), 200)
        dca = self.service.dca({**self._params(), "contribution_sgd": ["500"], "frequency": ["monthly"]})
        self.assertIn("xirr", dca["result"])
        compare = self.service.compare({**self._params(), "tickers": ["QQQ,SMH,SOXX"]})
        self.assertEqual(len(compare["results"]), 3)

    def test_portfolio_envelope(self) -> None:
        result = self.service.portfolio(
            {
                "as_of": "2025-01-02",
                "transactions": [
                    {
                        "transaction_date": "2024-01-02",
                        "security_id": str(self.qqq.security_id),
                        "transaction_type": "BUY",
                        "quantity": "10",
                        "cash_amount": "4000",
                        "currency": "USD",
                        "fees": "0",
                    }
                ],
            }
        )
        self.assertIn("total_market_value_sgd", result["result"])
        self.assertEqual(result["result"]["holdings"][0]["ticker"], "QQQ")


if __name__ == "__main__":
    unittest.main()
