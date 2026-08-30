"""Local read-only adapter for the static SG / Invest frontend.

The frontend never performs investment calculations. This small development
server exposes the existing Python calculation contracts over JSON while also
serving ``frontend/`` as a static site. A static publishing job can replace
these API responses with pre-generated artifacts using the same shapes.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import pyarrow.parquet as pq
import yaml

from sg_investing.analysis import analyze_security
from sg_investing.calculations.dca import DcaFrequency, dca_analysis
from sg_investing.calculations.portfolio import analyze_portfolio
from sg_investing.data.dividend_quality import load_coverage_report
from sg_investing.models import (
    AnalysisScenario,
    CorporateAction,
    DividendEvent,
    FxRate,
    PortfolioTransaction,
    PriceBar,
    Security,
    TaxRule,
)
from sg_investing.universe.catalog import UniverseCatalog, load_catalog

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = ROOT / "frontend"
DATA_ROOT = ROOT / "data"


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


class FrontendDataService:
    """Read only, cached adapter over the canonical parquet datasets."""

    def __init__(self, root: Path = ROOT) -> None:
        self.root = root
        self.data_root = root / "data"
        self.catalog: UniverseCatalog = load_catalog(root / "data" / "universe" / "current_catalog.json")
        rules = yaml.safe_load((root / "config" / "tax_rules.yaml").read_text(encoding="utf-8")) or {}
        self.tax_rules = [TaxRule.model_validate(rule) for rule in rules.get("rules", [])]
        self._security_by_id = {entry.security.security_id: entry.security for entry in self.catalog.securities}
        coverage_report = load_coverage_report(self.data_root / "dividends" / "coverage_report.json")
        self._dividend_coverage_by_id = (
            {record.security_id: record for record in coverage_report.securities}
            if coverage_report
            else {}
        )
        self._prices_cache: dict[tuple[str, int, UUID], list[PriceBar]] = {}
        self._dividend_cache: dict[tuple[int, UUID], list[DividendEvent]] = {}
        self._action_cache: dict[tuple[int, UUID], list[CorporateAction]] = {}
        self._fx_cache: dict[tuple[str, int], list[FxRate]] = {}

    @staticmethod
    def _read_filtered(path: Path, *, field: str, value: str) -> list[dict]:
        if not path.exists():
            return []
        try:
            return pq.read_table(path, filters=[[(field, "=", value)]]).to_pylist()
        except (ValueError, TypeError):
            # Older parquet writers may not expose statistics for the filter;
            # retain correctness by filtering the decoded rows.
            return [row for row in pq.read_table(path).to_pylist() if row.get(field) == value]

    def security(self, *, security_id: str | None = None, ticker: str | None = None) -> Security:
        if security_id:
            try:
                security = self._security_by_id[UUID(security_id)]
            except (ValueError, KeyError) as exc:
                raise ValueError(f"Unknown security_id: {security_id}") from exc
            return security
        matches = [item for item in self._security_by_id.values() if item.ticker == (ticker or "").upper()]
        if len(matches) != 1:
            ids = ", ".join(str(item.security_id) for item in matches)
            raise ValueError(f"Expected one security for ticker {ticker}; matches: {ids or 'none'}")
        return matches[0]

    def prices(self, security: Security, years: range) -> list[PriceBar]:
        rows: list[PriceBar] = []
        for year in years:
            key = (security.market, year, security.security_id)
            if key not in self._prices_cache:
                path = self.data_root / "prices" / f"market={security.market}" / f"year={year}.parquet"
                payload = self._read_filtered(path, field="security_id", value=str(security.security_id))
                self._prices_cache[key] = [PriceBar.model_validate(row) for row in payload]
            rows.extend(self._prices_cache[key])
        return rows

    def dividends(self, security: Security, years: range) -> list[DividendEvent]:
        rows: list[DividendEvent] = []
        for year in years:
            key = (year, security.security_id)
            if key not in self._dividend_cache:
                payload = self._read_filtered(self.data_root / "dividends" / f"year={year}.parquet", field="security_id", value=str(security.security_id))
                self._dividend_cache[key] = [DividendEvent.model_validate(row) for row in payload]
            rows.extend(self._dividend_cache[key])
        return rows

    def dividend_coverage(self, security: Security) -> dict:
        record = self._dividend_coverage_by_id.get(security.security_id)
        if record:
            return record.model_dump(mode="json")
        if security.distribution_policy.value == "accumulating":
            status = "known_accumulating"
        elif security.distribution_policy.value == "non_distributing":
            status = "known_non_distributing"
        elif security.distribution_policy.value == "distributing":
            status = "dividend_data_missing"
        else:
            status = "unknown"
        return {
            "security_id": str(security.security_id),
            "ticker": security.ticker,
            "distribution_policy": security.distribution_policy.value,
            "coverage_status": status,
            "event_count": 0,
        }

    def _attach_dividend_coverage(self, result: dict, security: Security) -> dict:
        coverage = self.dividend_coverage(security)
        result["dividend_coverage"] = coverage
        status = coverage.get("coverage_status")
        if status in {
            "dividend_data_missing",
            "provider_error",
            "unknown",
            "data_available_policy_unknown",
            "known_distributing_with_no_events",
            "known_non_distributing",
        }:
            quality = result.setdefault("data_quality", {"status": "OK", "warnings": []})
            warnings = list(quality.get("warnings", []))
            if status == "known_non_distributing":
                warnings.append("This security is marked non-distributing; no cash dividends are expected.")
            elif status == "data_available_policy_unknown":
                warnings.append("Dividend events exist, but the security distribution policy is unknown.")
            elif status == "known_distributing_with_no_events":
                warnings.append("The provider returned no dividend events; this does not confirm a zero-dividend history.")
            elif status == "dividend_data_missing":
                warnings.append("Dividend history is not available for this distributing security; $0 is not confirmed.")
            elif status == "provider_error":
                warnings.append("Dividend provider retrieval failed; dividend totals are not confirmed.")
            elif status == "unknown":
                warnings.append("Dividend distribution policy or coverage is unknown; dividend totals are not confirmed.")
            quality["warnings"] = sorted(set(warnings))
            if warnings:
                quality["status"] = "WARNING"
        return result

    def corporate_actions(self, security: Security, years: range) -> list[CorporateAction]:
        rows: list[CorporateAction] = []
        for year in years:
            key = (year, security.security_id)
            if key not in self._action_cache:
                payload = self._read_filtered(self.data_root / "corporate_actions" / f"year={year}.parquet", field="security_id", value=str(security.security_id))
                self._action_cache[key] = [CorporateAction.model_validate(row) for row in payload]
            rows.extend(self._action_cache[key])
        return rows

    def fx(self, currency: str, years: range) -> list[FxRate]:
        rows: list[FxRate] = []
        for year in years:
            key = (currency, year)
            if key not in self._fx_cache:
                path = self.data_root / "fx" / f"pair={currency}_SGD" / f"year={year}.parquet"
                self._fx_cache[key] = [FxRate.model_validate(row) for row in (pq.read_table(path).to_pylist() if path.exists() else [])]
            rows.extend(self._fx_cache[key])
        return rows

    @staticmethod
    def years(start: date, end: date) -> range:
        return range(start.year, end.year + 1)

    def analysis(self, params: dict[str, list[str]]) -> dict:
        start = date.fromisoformat(_one(params, "start_date", "2024-01-02"))
        end = date.fromisoformat(_one(params, "end_date", "2025-01-02"))
        security = self.security(security_id=_optional(params, "security_id"), ticker=_optional(params, "ticker"))
        scenario = AnalysisScenario(
            dividends_enabled=_boolean(params, "dividends", True),
            withholding_tax_enabled=_boolean(params, "withholding", True),
            reinvest_dividends=_boolean(params, "reinvest", True),
        )
        result = analyze_security(
            security=security,
            prices=self.prices(security, self.years(start, end)),
            fx_rates=self.fx(security.currency, self.years(start, end)),
            start_date=start,
            end_date=end,
            initial_sgd=_one(params, "initial_sgd", "10000"),
            scenario=scenario,
            dividends=self.dividends(security, self.years(start, end)),
            corporate_actions=self.corporate_actions(security, self.years(start, end)),
            tax_rules=self.tax_rules,
        )
        return self._envelope(self._attach_dividend_coverage(result.model_dump(mode="json"), security), params)

    def dca(self, params: dict[str, list[str]]) -> dict:
        start = date.fromisoformat(_one(params, "start_date", "2024-01-02"))
        end = date.fromisoformat(_one(params, "end_date", "2025-01-02"))
        security = self.security(security_id=_optional(params, "security_id"), ticker=_optional(params, "ticker"))
        years = self.years(start, end)
        scenario = AnalysisScenario(
            dividends_enabled=_boolean(params, "dividends", True),
            withholding_tax_enabled=_boolean(params, "withholding", True),
            reinvest_dividends=_boolean(params, "reinvest", True),
        )
        result = dca_analysis(
            security=security,
            prices=self.prices(security, years),
            fx_rates=self.fx(security.currency, years),
            start_date=start,
            end_date=end,
            contribution_sgd=_one(params, "contribution_sgd", "500"),
            frequency=DcaFrequency(_one(params, "frequency", "monthly")),
            scenario=scenario,
            dividends=self.dividends(security, years),
            corporate_actions=self.corporate_actions(security, years),
            tax_rules=self.tax_rules,
        )
        return self._envelope(self._attach_dividend_coverage(result.model_dump(mode="json"), security), params)

    def series(self, params: dict[str, list[str]]) -> dict:
        start = date.fromisoformat(_one(params, "start_date", "2024-01-02"))
        end = date.fromisoformat(_one(params, "end_date", "2025-01-02"))
        security = self.security(security_id=_optional(params, "security_id"), ticker=_optional(params, "ticker"))
        fx_rows = self.fx(security.currency, self.years(start, end))
        from sg_investing.analysis import _rate_for_date

        points = []
        for price in sorted(self.prices(security, self.years(start, end)), key=lambda row: row.trading_date):
            if not start <= price.trading_date <= end:
                continue
            rate = _rate_for_date(security.currency, price.trading_date, fx_rows)
            points.append({"date": price.trading_date.isoformat(), "native_close": price.close, "sgd_close": price.close * rate, "fx_rate": rate})
        return self._envelope({"security": security.model_dump(mode="json"), "points": points}, params)

    def compare(self, params: dict[str, list[str]]) -> dict:
        tickers = [item.strip().upper() for item in _one(params, "tickers", "").split(",") if item.strip()]
        if not 2 <= len(tickers) <= 6:
            raise ValueError("Comparison requires between 2 and 6 tickers.")
        results = []
        for ticker in tickers:
            item_params = dict(params)
            item_params["ticker"] = [ticker]
            results.append(self.analysis(item_params))
        return {"generated_at": _today(), "results": results}

    def portfolio(self, payload: dict) -> dict:
        as_of = date.fromisoformat(payload.get("as_of", _today()))
        transactions = [PortfolioTransaction.model_validate(item) for item in payload.get("transactions", [])]
        security_ids = {item.security_id for item in transactions if item.security_id is not None}
        securities = {security_id: self._security_by_id[security_id] for security_id in security_ids if security_id in self._security_by_id}
        years = range(2000, as_of.year + 1)
        prices = [price for security in securities.values() for price in self.prices(security, years)]
        currencies = {security.currency for security in securities.values()} | {item.currency for item in transactions}
        fx = [rate for currency in currencies for rate in self.fx(currency, years)]
        result = analyze_portfolio(transactions=transactions, securities=securities, prices=prices, fx_rates=fx, as_of=as_of)
        return self._envelope(result.model_dump(mode="json"), payload)

    @staticmethod
    def _envelope(result: dict, request: dict) -> dict:
        return {
            "generated_at": _today(),
            "data_snapshot_id": "local-canonical-parquet",
            "catalog_version": "current_catalog",
            "methodology_version": result.get("methodology", {}).get("methodology_version", "1.0"),
            "request": {key: value[-1] if isinstance(value, list) and value else value for key, value in request.items() if key not in {"ticker", "security_id"}},
            "result": result,
        }


def _one(params: dict[str, list[str]], key: str, default: str | None = None) -> str:
    values = params.get(key, [])
    if values and values[-1] != "":
        return values[-1]
    if default is not None:
        return default
    raise ValueError(f"Missing query parameter: {key}")


def _optional(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key, [])
    return values[-1] if values and values[-1] else None


def _boolean(params: dict[str, list[str]], key: str, default: bool) -> bool:
    return _one(params, key, "true" if default else "false").lower() in {"1", "true", "yes", "on"}


class FrontendHandler(SimpleHTTPRequestHandler):
    service = FrontendDataService()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_ROOT), **kwargs)

    def _json(self, payload: dict, status: int = 200) -> None:
        encoded = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            return super().do_GET()
        params = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/catalog":
                self._json({"history_start": self.service.catalog.history_start.isoformat(), "securities": [entry.model_dump(mode="json") for entry in self.service.catalog.securities]})
            elif parsed.path == "/api/status":
                status = _read_json(DATA_ROOT / "backfill" / "price_summary.json", {})
                universe = _read_json(DATA_ROOT / "universe" / "summary.json", {})
                update = _read_json(DATA_ROOT / "update_summary.json", {})
                self._json({"generated_at": _today(), "universe": universe, "backfill": status, "update": update})
            elif parsed.path == "/api/analyze":
                self._json(self.service.analysis(params))
            elif parsed.path == "/api/dca":
                self._json(self.service.dca(params))
            elif parsed.path == "/api/series":
                self._json(self.service.series(params))
            elif parsed.path == "/api/compare":
                self._json(self.service.compare(params))
            else:
                self._json({"error": "Unknown endpoint"}, 404)
        except (ValueError, KeyError, FileNotFoundError) as exc:
            self._json({"error": str(exc)}, 422)
        except Exception as exc:  # noqa: BLE001  # pragma: no cover - defensive HTTP boundary
            self._json({"error": str(exc)}, 500)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/portfolio":
            self._json({"error": "Unknown endpoint"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or "{}")
            self._json(self.service.portfolio(payload))
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, 422)


def _read_json(path: Path, fallback: dict) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=4173)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), FrontendHandler)
    print(f"SG / Invest frontend at http://127.0.0.1:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
