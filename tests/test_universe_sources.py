from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from sg_investing.models import AssetType
from sg_investing.universe import sources


pytestmark = pytest.mark.provider


class FakeResponse:
    def __init__(self, *, text: str = "", content: bytes = b"", payload=None):
        self.text = text
        self.content = content
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_blackrock_parser_skips_non_priceable_rows_and_normalizes_symbols():
    response = FakeResponse(
        text=(
            "download metadata\n"
            "Ticker,Name,Exchange,Asset Class,Price\n"
            "BRK.B,Berkshire Hathaway,NYSE,Equity,100\n"
            "-,Placeholder,NYSE,Equity,100\n"
            "NAN,Placeholder,NYSE,Equity,100\n"
            "ABC,No Market Company,NO MARKET,Equity,100\n"
            "DEF,,NYSE,Equity,100\n"
            "CASH,Cash,-,Cash,1\n"
            "CVR,Example CVR,NASDAQ,Equity,1\n"
            "OLD,Delisted Equity,NASDAQ,Equity,0\n"
        )
    )
    with patch.object(sources.requests, "get", return_value=response):
        records = sources._blackrock_holdings(url="https://example.test/holdings.csv", minimum_count=1, label="test")

    assert len(records) == 1
    assert records[0].ticker == "BRK-B"
    assert records[0].asset_type == AssetType.EQUITY
    assert records[0].security_id == sources._security_id(exchange="US", ticker="BRK-B")


def test_blackrock_parser_filters_fund_residuals_and_maps_verified_share_class_aliases():
    response = FakeResponse(
        text=(
            "Ticker,Name,Exchange,Asset Class,Price\n"
            "BRKB,Berkshire Hathaway Inc Class B,NYSE,Equity,500\n"
            "ESU6,S&P 500 Emini,CME,Futures,6000\n"
            "CGI,Cash Collateral,-,Cash Collateral and Margins,100\n"
            "AKE,Akero Therapeutics CVR,NASDAQ,Equity,0.65\n"
            "PDLI,PDL Biopharma,NASDAQ,Equity,0\n"
        )
    )
    with patch.object(sources.requests, "get", return_value=response):
        records = sources._blackrock_holdings(url="https://example.test/holdings.csv", minimum_count=1, label="test")

    assert [record.ticker for record in records] == ["BRK-B"]


@pytest.mark.parametrize(
    ("text", "minimum_count", "message"),
    [
        ("preamble only\n", 1, "schema changed"),
        ("Ticker,Name,Exchange,Asset Class,Price\nABC,Company,NYSE,Equity,100\n", 2, "few test holdings"),
        (
            "Ticker,Name,Exchange,Asset Class,Price\nABC,Company,NYSE,Equity,100\nABC,Duplicate,NYSE,Equity,100\n",
            1,
            "duplicate ticker",
        ),
    ],
)
def test_blackrock_parser_has_schema_count_and_duplicate_gates(text, minimum_count, message):
    with patch.object(sources.requests, "get", return_value=FakeResponse(text=text)):
        with pytest.raises(ValueError, match=message):
            sources._blackrock_holdings(url="https://example.test/holdings.csv", minimum_count=minimum_count, label="test")


class FakePage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self):
        return self._text


class FakePdfReader:
    def __init__(self, _stream):
        names = []
        for index in range(100):
            names.extend([f"Company {index:03d}", f"A{index:03d}", "1.0"])
        self.pages = [FakePage("Data as of: 06/20/2026\nWeight (%)\n" + "\n".join(names))]


def test_nasdaq_component_parser_extracts_date_and_constituents():
    with patch.object(sources, "PdfReader", FakePdfReader):
        source_date, records = sources._parse_nasdaq_components(b"fixture")
    assert source_date == date(2026, 6, 20)
    assert len(records) == 100
    assert records[0] == ("A000", "Company 000")


def test_nasdaq_component_parser_rejects_missing_as_of_date():
    class MissingDateReader:
        def __init__(self, _stream):
            self.pages = [FakePage("Weight (%)\nCompany\nABC\n1.0")]

    with patch.object(sources, "PdfReader", MissingDateReader):
        with pytest.raises(ValueError, match="as-of date"):
            sources._parse_nasdaq_components(b"fixture")


def test_nasdaq_rebalance_is_applied_only_after_effective_date():
    old = [(ticker, f"Old {ticker}") for ticker in ("CHTR", "CTSH", "INSM", "VRSK", "ZS")]
    source_records = old + [(f"A{index:03d}", f"Company {index:03d}") for index in range(95)]
    response = FakeResponse(content=b"fixture")
    with patch.object(sources.requests, "get", return_value=response), patch.object(
        sources, "_parse_nasdaq_components", return_value=(date(2026, 6, 20), source_records)
    ):
        before = sources.fetch_nasdaq100_current(as_of=date(2026, 6, 21))
        after = sources.fetch_nasdaq100_current(as_of=date(2026, 6, 22))

    assert {row.ticker for row in before} >= {"CHTR", "CTSH", "INSM", "VRSK", "ZS"}
    assert {row.ticker for row in after} >= {"ALAB", "CRWV", "NBIS", "RKLB", "TER"}
    assert not {row.ticker for row in after} & {"CHTR", "CTSH", "INSM", "VRSK", "ZS"}
    assert len(after) == 100


def valid_sgx_row(index: int, *, code: str | None = None, category: str = "stocks", status: str = "P"):
    return {
        "nc": code or f"C{index:03d}",
        "n": f"SGX Company {index:03d}",
        "type": category,
        "ls": status,
        "cur": "SGD",
    }


def sgx_response(rows):
    return FakeResponse(payload={"data": {"prices": rows}})


def test_sgx_parser_filters_out_of_scope_rows_and_normalizes_metadata():
    rows = [valid_sgx_row(index) for index in range(650)]
    rows.extend([valid_sgx_row(700, category="unknown"), valid_sgx_row(701, status="D")])
    with patch.object(sources.requests, "get", return_value=sgx_response(rows)):
        records = sources.fetch_sgx_current(as_of=date(2026, 8, 30))
    assert len(records) == 650
    assert records[0].ticker == "C000.SI"
    assert records[0].market == "SG"
    assert records[0].exchange == "SGX"
    assert records[0].timezone == "Asia/Singapore"
    assert records[0].asset_type == AssetType.EQUITY


def test_sgx_parser_rejects_schema_changes_in_scope_incomplete_rows_and_duplicates():
    with patch.object(sources.requests, "get", return_value=FakeResponse(payload={"data": {"prices": {}}})):
        with pytest.raises(ValueError, match="not a list"):
            sources.fetch_sgx_current(as_of=date(2026, 8, 30))

    incomplete = [valid_sgx_row(index) for index in range(650)]
    incomplete[0]["cur"] = ""
    with patch.object(sources.requests, "get", return_value=sgx_response(incomplete)):
        with pytest.raises(ValueError, match="incomplete"):
            sources.fetch_sgx_current(as_of=date(2026, 8, 30))

    duplicate = [valid_sgx_row(index) for index in range(649)]
    duplicate.append(valid_sgx_row(999, code="C000"))
    with patch.object(sources.requests, "get", return_value=sgx_response(duplicate)):
        with pytest.raises(ValueError, match="duplicate"):
            sources.fetch_sgx_current(as_of=date(2026, 8, 30))
