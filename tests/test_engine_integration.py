from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
import yaml

from sg_investing.data.storage import ParquetStore
from sg_investing.engine import SGInvestingEngine
from tests.helpers import OTHER_SECURITY_ID, action, dividend, fx, price, security


pytestmark = pytest.mark.integration


def build_project(tmp_path, securities):
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "universe.yaml").write_text(
        yaml.safe_dump(
            {
                "history_start": "2000-01-01",
                "securities": [
                    {
                        "universe": "test",
                        "effective_from": "2024-01-01",
                        "source": "test",
                        "security": row.model_dump(mode="json"),
                    }
                    for row in securities
                ],
            }
        ),
        encoding="utf-8",
    )
    (config_dir / "tax_rules.yaml").write_text("rules: []\n", encoding="utf-8")
    return tmp_path


def test_public_engine_loads_multi_year_data_and_returns_json(tmp_path):
    sec = security()
    project = build_project(tmp_path, [sec])
    store = ParquetStore(project / "data")
    store.upsert_prices(
        market="US",
        rows=[price(sec, date(2023, 12, 29), "100"), price(sec, date(2024, 1, 2), "120")],
        pipeline_version="test",
    )
    store.upsert_fx([fx(date(2023, 12, 29), "1.30"), fx(date(2024, 1, 2), "1.40")])

    result = SGInvestingEngine(project).analyze(
        ticker="TEST",
        start_date=date(2023, 12, 29),
        end_date=date(2024, 1, 2),
        initial_sgd=Decimal("1300"),
    )

    assert result.period == {"start_date": date(2023, 12, 29), "end_date": date(2024, 1, 2)}
    assert result.investment["final_value_sgd"] == Decimal("1680")
    payload = result.model_dump(mode="json")
    assert payload["security"]["ticker"] == "TEST"
    json.dumps(payload)


def test_public_engine_filters_other_security_rows_by_security_id(tmp_path):
    target = security()
    other = security(ticker="OTHER", security_id=OTHER_SECURITY_ID)
    project = build_project(tmp_path, [target, other])
    store = ParquetStore(project / "data")
    store.upsert_prices(
        market="US",
        rows=[
            price(target, date(2024, 1, 2), "100"),
            price(target, date(2024, 4, 1), "110"),
            price(other, date(2024, 1, 2), "1000"),
            price(other, date(2024, 4, 1), "2000"),
        ],
        pipeline_version="test",
    )
    store.upsert_fx([fx(date(2024, 1, 2), "1"), fx(date(2024, 4, 1), "1")])

    result = SGInvestingEngine(project).analyze(
        ticker="TEST",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 4, 1),
        initial_sgd=Decimal("1000"),
    )
    assert result.investment["final_value_sgd"] == Decimal("1100")


def test_public_engine_loads_dividends_and_corporate_actions(tmp_path):
    sec = security()
    project = build_project(tmp_path, [sec])
    store = ParquetStore(project / "data")
    store.upsert_prices(
        market="US",
        rows=[
            price(sec, date(2024, 1, 2), "100"),
            price(sec, date(2024, 2, 1), "50"),
            price(sec, date(2024, 3, 1), "50"),
            price(sec, date(2024, 4, 1), "50"),
        ],
        pipeline_version="test",
    )
    store.upsert_fx([fx(date(2024, 1, 2), "1"), fx(date(2024, 4, 1), "1")])
    store.upsert_corporate_actions([action(sec, date(2024, 2, 1), "2")])
    store.upsert_dividends([dividend(sec, date(2024, 3, 1), "1", pay_date=date(2024, 3, 1))])

    result = SGInvestingEngine(project).analyze(
        ticker="TEST",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 4, 1),
        initial_sgd=Decimal("1000"),
    )
    # Ten initial shares become twenty after the split, then receive a
    # US$20 dividend reinvested at US$50.
    assert result.investment["shares"] == Decimal("20.4")
    assert result.investment["final_value_sgd"] == Decimal("1020")


def test_public_engine_rejects_unknown_and_ambiguous_tickers(tmp_path):
    target = security()
    project = build_project(tmp_path, [target])
    engine = SGInvestingEngine(project)
    with pytest.raises(KeyError, match="UNKNOWN"):
        engine.analyze(
            ticker="UNKNOWN",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 2),
            initial_sgd="100",
        )

    first = security(ticker="DUP")
    second = security(ticker="DUP", security_id=OTHER_SECURITY_ID)
    ambiguous_project = build_project(tmp_path / "ambiguous", [first, second])
    with pytest.raises(KeyError, match="DUP"):
        SGInvestingEngine(ambiguous_project).analyze(
            ticker="DUP",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 2),
            initial_sgd="100",
        )
