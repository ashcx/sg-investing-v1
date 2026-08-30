from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

import pytest
import pyarrow.parquet as pq

from sg_investing.analysis import AnalysisDataError, analyze_security
from sg_investing.data.storage import ParquetStore
from sg_investing.data.validation import (
    validate_corporate_actions,
    validate_dividends,
    validate_fx,
)
from sg_investing.models import PriceBar
from sg_investing.universe.catalog import load_catalog


pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        os.environ.get("SG_INVESTING_RUN_UNIVERSE_SMOKE") != "1",
        reason="set SG_INVESTING_RUN_UNIVERSE_SMOKE=1 to run against downloaded data",
    ),
]


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _catalog_and_store():
    root = _root()
    catalog_path = root / "data" / "universe" / "current_catalog.json"
    if not catalog_path.exists():
        pytest.skip("current downloaded-universe catalog is not present")
    return load_catalog(catalog_path), ParquetStore(root / "data")


def _security_map(catalog):
    return {
        entry.security.security_id: entry.security
        for entry in catalog.securities
    }


def _downloaded_prices(store: ParquetStore):
    recent_by_security = defaultdict(list)
    stats_by_security = {}
    partition_errors = []
    price_root = Path(store.root) / "prices"
    for path in sorted(price_root.glob("market=*/year=*.parquet")):
        market = path.parent.name.split("=", 1)[1]
        table = pq.read_table(
            path,
            columns=["security_id", "trading_date", "open", "high", "low", "close", "volume", "currency", "exchange", "timezone", "source", "retrieved_at"],
        )
        columns = table.to_pydict()
        seen = set()
        for index, security_id_text in enumerate(columns["security_id"]):
            key = (security_id_text, columns["trading_date"][index])
            if key in seen:
                partition_errors.append(f"{path}: duplicate price observation for {key}")
            seen.add(key)
            open_price = columns["open"][index]
            high_price = columns["high"][index]
            low_price = columns["low"][index]
            close_price = columns["close"][index]
            finite_values = all(
                value.is_finite()
                for value in (open_price, high_price, low_price, close_price)
            )
            if not finite_values:
                partition_errors.append(f"{path}: non-finite OHLC for {key}")
            elif not (low_price <= open_price <= high_price and low_price <= close_price <= high_price):
                partition_errors.append(f"{path}: invalid OHLC for {key}")
            if finite_values and close_price <= 0:
                partition_errors.append(f"{path}: zero close for {key}")
            if columns["volume"][index] < 0:
                partition_errors.append(f"{path}: negative volume for {key}")
            stats = stats_by_security.setdefault(
                security_id_text,
                {
                    "count": 0,
                    "first_date": columns["trading_date"][index],
                    "last_date": columns["trading_date"][index],
                    "currency": columns["currency"][index],
                    "exchange": columns["exchange"][index],
                    "market": market,
                    "recent": [],
                },
            )
            stats["count"] += 1
            stats["first_date"] = min(stats["first_date"], columns["trading_date"][index])
            stats["last_date"] = max(stats["last_date"], columns["trading_date"][index])
            stats["currency"] = stats["currency"] if stats["currency"] == columns["currency"][index] else "<mixed>"
            stats["exchange"] = stats["exchange"] if stats["exchange"] == columns["exchange"][index] else "<mixed>"
            stats["market"] = stats["market"] if stats["market"] == market else "<mixed>"
            raw_row = {name: values[index] for name, values in columns.items()}
            stats["recent"].append(raw_row)
            stats["recent"].sort(key=lambda row: row["trading_date"])
            del stats["recent"][:-2]
    for security_id_text, stats in stats_by_security.items():
        recent_by_security[security_id_text] = [
            # The bulk scan performs structural checks; model validation is
            # deliberately limited to the observations used by the smoke call.
            PriceBar.model_validate(row)
            for row in stats["recent"]
        ]
    return recent_by_security, stats_by_security, partition_errors


def _downloaded_events(store: ParquetStore):
    dividends_by_security = defaultdict(list)
    actions_by_security = defaultdict(list)
    fx_by_currency = defaultdict(list)
    errors = []
    root = Path(store.root)
    for path in sorted((root / "dividends").glob("year=*.parquet")):
        rows = store.read_dividends(year=int(path.stem.split("=", 1)[1]))
        report = validate_dividends(rows)
        if not report.is_valid:
            errors.extend(f"{path}: {error}" for error in report.errors)
        for row in rows:
            dividends_by_security[row.security_id].append(row)
    for path in sorted((root / "corporate_actions").glob("year=*.parquet")):
        rows = store.read_corporate_actions(year=int(path.stem.split("=", 1)[1]))
        report = validate_corporate_actions(rows)
        if not report.is_valid:
            errors.extend(f"{path}: {error}" for error in report.errors)
        for row in rows:
            actions_by_security[row.security_id].append(row)
    for path in sorted((root / "fx").glob("pair=*/year=*.parquet")):
        pair = path.parent.name.split("=", 1)[1]
        currency = pair.removesuffix("_SGD")
        rows = store.read_fx(base_currency=currency, year=int(path.stem.split("=", 1)[1]))
        report = validate_fx(rows)
        if not report.is_valid:
            errors.extend(f"{path}: {error}" for error in report.errors)
        fx_by_currency[currency].extend(rows)
    return dividends_by_security, actions_by_security, fx_by_currency, errors


@pytest.fixture(scope="module")
def downloaded_context():
    catalog, store = _catalog_and_store()
    prices_by_security, price_stats, price_errors = _downloaded_prices(store)
    dividends_by_security, actions_by_security, fx_by_currency, event_errors = _downloaded_events(store)
    return {
        "catalog": catalog,
        "prices": prices_by_security,
        "price_stats": price_stats,
        "dividends": dividends_by_security,
        "actions": actions_by_security,
        "fx": fx_by_currency,
        "errors": [*price_errors, *event_errors],
    }


def test_every_downloaded_partition_is_structurally_valid(downloaded_context):
    known = _security_map(downloaded_context["catalog"])
    errors = list(downloaded_context["errors"])
    for security_id_text, stats in downloaded_context["price_stats"].items():
        security_id = next((item for item in known if str(item) == security_id_text), None)
        security = known.get(security_id) if security_id else None
        if security is None:
            errors.append(f"{security_id_text}: no matching security master record")
            continue
        if stats["market"] != security.market:
            errors.append(
                f"{security.ticker}: price partition market {stats['market']} "
                f"!= {security.market}"
            )
        if stats["currency"] != security.currency:
            errors.append(f"{security.ticker}: price currency {stats['currency']} != {security.currency}")
        if stats["exchange"] != security.exchange:
            errors.append(f"{security.ticker}: price exchange {stats['exchange']} != {security.exchange}")
    for collection_name in ("dividends", "actions"):
        for security_id in downloaded_context[collection_name]:
            if security_id not in known:
                errors.append(f"{security_id}: {collection_name} have no matching security master record")
    if errors:
        pytest.fail("\n".join(errors))


def test_each_downloaded_security_with_two_prices_can_execute_analysis(downloaded_context):
    known = _security_map(downloaded_context["catalog"])
    prices_by_security = {
        next(item for item in known if str(item) == security_id_text): rows
        for security_id_text, rows in downloaded_context["prices"].items()
        if any(str(item) == security_id_text for item in known)
    }
    fx_by_currency = downloaded_context["fx"]
    if downloaded_context["errors"]:
        pytest.fail("\n".join(downloaded_context["errors"]))
    failures = []
    skipped = []
    for security_id, rows in sorted(prices_by_security.items(), key=lambda item: str(item[0])):
        security = known.get(security_id)
        if security is None:
            failures.append(f"{security_id}: missing security master")
            continue
        rows = sorted(rows, key=lambda row: row.trading_date)
        if len(rows) < 2:
            skipped.append(f"{security.ticker}: fewer than two prices")
            continue
        fx_rows = fx_by_currency.get(security.currency, [])
        if security.currency != "SGD" and not fx_rows:
            failures.append(f"{security.ticker}: no {security.currency}/SGD FX history")
            continue
        try:
            # Use the last two observations so a long-lived security is not
            # rejected solely because FX history predates its listing history.
            analyze_security(
                security=security,
                prices=rows[-2:],
                fx_rates=fx_rows,
                start_date=rows[-2].trading_date,
                end_date=rows[-1].trading_date,
                initial_sgd="1000",
            )
        except (AnalysisDataError, ValueError) as error:
            failures.append(f"{security.ticker}: {error}")
    if failures:
        pytest.fail(json.dumps({"failures": failures, "skipped": skipped}, indent=2))
