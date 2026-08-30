"""Publish the read-only frontend data envelope from canonical backend files.

This command delegates all calculations to the existing Python engine and
snapshots the resulting JSON. It publishes catalog, coverage, update metadata,
and representative analysis/DCA/comparison/portfolio artifacts so a static
host can use the same contracts as the local frontend adapter. Run it after a
backfill or universe refresh.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def _read(path: Path, fallback: dict) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def build(root: Path) -> None:
    universe = _read(root / "data" / "universe" / "current_catalog.json", {"history_start": "1999-01-01", "securities": []})
    summary = _read(root / "data" / "universe" / "summary.json", {})
    backfill = _read(root / "data" / "backfill" / "price_summary.json", {})
    update = _read(root / "data" / "update_summary.json", {})
    target = root / "frontend" / "data"
    target.mkdir(parents=True, exist_ok=True)
    (target / "catalog.json").write_text(json.dumps(universe, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    status = {
        "generated_at": _today(),
        "catalog_version": "current_catalog",
        "history_start": universe.get("history_start"),
        "universe": summary,
        "backfill": backfill,
        "update": update,
        "coverage_note": "Incomplete and unavailable rows remain visible; the API resolves only canonical parquet data.",
    }
    (target / "data-status.json").write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    analyses = target / "analyses"
    analyses.mkdir(exist_ok=True)
    _build_demo_analysis(root, analyses)
    _build_demo_secondary_artifacts(root, target)
    index = []
    for artifact in sorted(analyses.glob("*.json")):
        if artifact.name == "index.json":
            continue
        try:
            payload = json.loads(artifact.read_text(encoding="utf-8"))
            result = payload.get("result", {})
            security = result.get("security", {})
            period = result.get("period", {})
            index.append({"key": artifact.stem, "path": f"analyses/{artifact.name}", "ticker": security.get("ticker"), "start_date": period.get("start_date"), "end_date": period.get("end_date"), "methodology_version": payload.get("methodology_version")})
        except (OSError, json.JSONDecodeError):
            continue
    (analyses / "index.json").write_text(json.dumps({"generated_at": _today(), "artifacts": index}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_demo_analysis(root: Path, analyses: Path) -> None:
    """Refresh the small offline/demo artifact from the live engine contract."""
    try:
        from scripts.frontend_server import FrontendDataService
    except ModuleNotFoundError:
        from frontend_server import FrontendDataService

    service = FrontendDataService(root)
    security = service.security(ticker="QQQ")
    payload = service.analysis(
        {
            "security_id": [str(security.security_id)],
            "start_date": ["2024-01-02"],
            "end_date": ["2025-01-02"],
            "initial_sgd": ["10000"],
            "dividends": ["true"],
            "withholding": ["true"],
            "reinvest": ["true"],
        }
    )
    (analyses / "qqq-2024.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_demo_secondary_artifacts(root: Path, target: Path) -> None:
    try:
        from scripts.frontend_server import FrontendDataService
    except ModuleNotFoundError:
        from frontend_server import FrontendDataService

    service = FrontendDataService(root)
    qqq = service.security(ticker="QQQ")
    common = {
        "start_date": ["2024-01-02"],
        "end_date": ["2025-01-02"],
        "dividends": ["true"],
        "withholding": ["true"],
        "reinvest": ["true"],
    }
    dca_dir = target / "dca"
    dca_dir.mkdir(exist_ok=True)
    dca_payload = service.dca({**common, "security_id": [str(qqq.security_id)], "contribution_sgd": ["500"], "frequency": ["monthly"]})
    (dca_dir / "qqq-2024-monthly.json").write_text(json.dumps(dca_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    comparison_dir = target / "comparisons"
    comparison_dir.mkdir(exist_ok=True)
    comparison_payload = service.compare({**common, "tickers": ["QQQ,SMH,SOXX"], "initial_sgd": ["10000"]})
    (comparison_dir / "qqq-smh-soxx-2024.json").write_text(json.dumps(comparison_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    series_dir = target / "series" / str(qqq.security_id)
    series_dir.mkdir(parents=True, exist_ok=True)
    series_payload = service.series({**common, "security_id": [str(qqq.security_id)]})
    (series_dir / "2024-01-02_2025-01-02.json").write_text(json.dumps(series_payload, default=str, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    portfolio_dir = target / "portfolios"
    portfolio_dir.mkdir(exist_ok=True)
    portfolio_payload = service.portfolio({
        "as_of": "2025-01-02",
        "transactions": [{
            "transaction_date": "2024-01-02",
            "security_id": str(qqq.security_id),
            "transaction_type": "BUY",
            "quantity": "10",
            "cash_amount": "4000",
            "currency": "USD",
            "fees": "0",
        }],
    })
    (portfolio_dir / "demo-qqq.json").write_text(json.dumps(portfolio_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    build(args.root)


if __name__ == "__main__":
    main()
