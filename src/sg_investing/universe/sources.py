"""Current-universe source importers with source-specific validation gates."""

from __future__ import annotations

import re
from datetime import date
from io import BytesIO, StringIO
from uuid import NAMESPACE_URL, UUID, uuid5

import pandas as pd
import requests
from pypdf import PdfReader

from sg_investing.models import AssetType, Security

USER_AGENT = "sg-investing-data-engine/0.1 (research use)"
_HEADERS = {"User-Agent": USER_AGENT}

# BlackRock's holdings files sometimes encode a share class without the
# punctuation used by the Yahoo price identifier. These are verified active
# listings, unlike cash, futures, CVRs and other fund-operational holdings.
_BLACKROCK_TICKER_ALIASES = {
    "BFB": "BF-B",
    "BHA": "BH-A",
    "BRKB": "BRK-B",
    "CRDA": "CRD-A",
    "GEFB": "GEF-B",
    "MOGA": "MOG-A",
}


def _security_id(*, exchange: str, ticker: str) -> UUID:
    """Derive a repeatable identifier for a normalized provider listing."""
    return uuid5(NAMESPACE_URL, f"sg-investing:{exchange.upper()}:{ticker.upper()}")


def _us_equity(*, ticker: str, name: str) -> Security:
    ticker = ticker.replace(".", "-").upper()
    return Security(
        security_id=_security_id(exchange="US", ticker=ticker),
        ticker=ticker,
        exchange="US",
        market="US",
        name=name,
        currency="USD",
        asset_type=AssetType.EQUITY,
        domicile="US",
        income_source_country="US",
        timezone="America/New_York",
    )


def _blackrock_holdings(*, url: str, minimum_count: int, label: str) -> list[Security]:
    """Normalize the listed-equity rows in BlackRock's public holdings CSV."""
    response = requests.get(url, headers=_HEADERS, timeout=30)
    response.raise_for_status()
    lines = response.text.splitlines()
    header_index = next((index for index, line in enumerate(lines) if line.startswith("Ticker,")), None)
    if header_index is None:
        raise ValueError(f"{label} holdings CSV schema changed.")
    table = pd.read_csv(StringIO("\n".join(lines[header_index:])))
    records: list[Security] = []
    for row in table.to_dict(orient="records"):
        ticker = str(row.get("Ticker", "")).strip().upper()
        name = str(row.get("Name", "")).strip()
        exchange = str(row.get("Exchange", "")).strip().upper()
        asset_class = str(row.get("Asset Class", "Equity")).strip().casefold()
        raw_price = pd.to_numeric(row.get("Price"), errors="coerce")
        if (
            asset_class != "equity"
            or "NO MARKET" in exchange
            or exchange in {"", "-", "NAN"}
            or not ticker
            or ticker in {"-", "NAN"}
        ):
            continue
        if not name or name.lower() == "nan":
            continue
        # The official ETF export retains residual corporate-action interests
        # and zero-value delisted lines. They are not active listed equities.
        if re.search(r"\b(?:CVR|ESCROW)\b", name, flags=re.IGNORECASE) or pd.isna(raw_price) or raw_price <= 0:
            continue
        records.append(_us_equity(ticker=_BLACKROCK_TICKER_ALIASES.get(ticker, ticker), name=name))
    if len(records) < minimum_count:
        raise ValueError(f"Unexpectedly few {label} holdings: {len(records)}.")
    if len({record.ticker for record in records}) != len(records):
        raise ValueError(f"{label} priceable holdings contain duplicate ticker identifiers.")
    return records


def fetch_sp500_current(*, as_of: date) -> list[Security]:
    """Import the current S&P 500 proxy holdings from BlackRock's IVV export."""
    del as_of
    records = _blackrock_holdings(
        url="https://www.blackrock.com/us/individual/products/239726/ishares-core-sp-500-etf/latest-holdings.csv",
        # The official ETF export includes cash, futures and residual lines;
        # the cleaned priceable constituent set can be below 490 share lines.
        minimum_count=480,
        label="IVV / S&P 500",
    )
    if len(records) > 510:
        raise ValueError(f"Unexpected S&P 500 proxy constituent count: {len(records)}.")
    return records


def fetch_iwm_holdings_current(*, as_of: date) -> list[Security]:
    """Use BlackRock's official IWM holdings export as the Russell 2000 source."""
    del as_of
    return _blackrock_holdings(
        url="https://www.blackrock.com/us/individual/products/239710/ishares-russell-2000-etf/latest-holdings.csv",
        minimum_count=1_500,
        label="IWM / Russell 2000",
    )


def _parse_nasdaq_components(pdf: bytes) -> tuple[date, list[tuple[str, str]]]:
    """Extract the published NDX constituents table from Nasdaq's public PDF."""
    reader = PdfReader(BytesIO(pdf))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    as_of_match = re.search(r"Data as of:\s*(\d{2}/\d{2}/\d{4})", text)
    if as_of_match is None:
        raise ValueError("Nasdaq-100 PDF does not provide an as-of date.")
    source_date = date.fromisoformat(
        f"{as_of_match.group(1)[6:10]}-{as_of_match.group(1)[0:2]}-{as_of_match.group(1)[3:5]}"
    )
    records: list[tuple[str, str]] = []
    for page in reader.pages:
        lines = [line.strip() for line in (page.extract_text() or "").splitlines() if line.strip()]
        try:
            start = lines.index("Weight (%)") + 1
        except ValueError:
            continue
        name_parts: list[str] = []
        position = start
        while position < len(lines):
            line = lines[position]
            following = lines[position + 1] if position + 1 < len(lines) else ""
            if re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", line) and re.fullmatch(r"\d+(?:\.\d+)?", following):
                if name_parts:
                    records.append((line, " ".join(name_parts)))
                name_parts = []
                # The constituent weight is a field, not the next company's
                # name; consume it with its symbol.
                position += 2
            else:
                name_parts.append(line)
                position += 1
    if not 100 <= len(records) <= 110:
        raise ValueError(f"Unexpected Nasdaq-100 source row count: {len(records)}.")
    return source_date, records


def fetch_nasdaq100_current(*, as_of: date) -> list[Security]:
    """Import NDX and apply Nasdaq's published post-PDF quarterly changes."""
    response = requests.get("https://www.nasdaq.com/NDX", headers=_HEADERS, timeout=30)
    response.raise_for_status()
    source_date, source_records = _parse_nasdaq_components(response.content)
    constituents = {ticker: name for ticker, name in source_records}
    june_rebalance = date(2026, 6, 22)
    if source_date < june_rebalance <= as_of:
        for ticker in ("CHTR", "CTSH", "INSM", "VRSK", "ZS"):
            constituents.pop(ticker, None)
        constituents.update(
            {
                "ALAB": "Astera Labs, Inc.",
                "CRWV": "CoreWeave, Inc.",
                "NBIS": "Nebius Group N.V.",
                "RKLB": "Rocket Lab Corporation",
                "TER": "Teradyne, Inc.",
            }
        )
    if not 100 <= len(constituents) <= 110:
        raise ValueError(f"Unexpected normalized Nasdaq-100 count: {len(constituents)}.")
    return [_us_equity(ticker=ticker, name=name) for ticker, name in sorted(constituents.items())]


def fetch_sgx_current(*, as_of: date) -> list[Security]:
    """Import active SGX stocks, REITs, business trusts, and ETFs from SGX."""
    del as_of
    fields = "nc,n,type,ls,m,sc,bl,sip,ex,ej,clo,cr,cur,el,r,i,cc,ig,lf"
    response = requests.get(
        f"https://api.sgx.com/securities/v1.1?params={fields}",
        headers={**_HEADERS, "Referer": "https://www.sgx.com/"},
        timeout=30,
    )
    response.raise_for_status()
    rows = response.json().get("data", {}).get("prices", [])
    if not isinstance(rows, list):
        raise ValueError("SGX directory schema changed: data.prices is not a list.")
    asset_types = {
        "stocks": AssetType.EQUITY,
        "reits": AssetType.REIT,
        "businesstrusts": AssetType.TRUST,
        "etfs": AssetType.ETF,
    }
    records: list[Security] = []
    for row in rows:
        category = row.get("type")
        code = str(row.get("nc") or "").strip().upper()
        name = str(row.get("n") or "").strip()
        currency = str(row.get("cur") or "").strip().upper()
        if category not in asset_types or row.get("ls") not in {"P", "S"}:
            continue
        if not code or not name or len(currency) != 3:
            raise ValueError(f"SGX directory has an incomplete in-scope record: {row!r}")
        ticker = f"{code}.SI"
        records.append(
            Security(
                security_id=_security_id(exchange="SGX", ticker=ticker),
                ticker=ticker,
                exchange="SGX",
                market="SG",
                name=name,
                currency=currency,
                asset_type=asset_types[category],
                domicile="SG",
                income_source_country="SG",
                timezone="Asia/Singapore",
            )
        )
    if len(records) < 650:
        raise ValueError(f"Unexpectedly few in-scope SGX listings: {len(records)}.")
    if len({record.ticker for record in records}) != len(records):
        raise ValueError("SGX directory has duplicate security codes.")
    return records
