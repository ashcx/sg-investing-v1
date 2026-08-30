"""Atomic Parquet persistence with auditable manifests."""

from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict

from sg_investing.data.validation import (
    dividend_economic_key,
    dividend_event_key,
    validate_corporate_actions,
    validate_dividends,
    validate_fx,
    validate_prices,
)
from sg_investing.models import CorporateAction, DividendEvent, FxRate, PriceBar


class DatasetManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset: str
    source: str
    retrieved_at: datetime
    first_date: str | None
    last_date: str | None
    row_count: int
    pipeline_version: str
    security_id: UUID | None = None


_PRICE_SCHEMA = pa.schema(
    [
        ("security_id", pa.string()),
        ("trading_date", pa.date32()),
        # Provider floats can carry up to ~16 significant fractional digits.
        # Preserve them in canonical storage; presentation is the only place
        # prices are rounded.
        ("open", pa.decimal128(32, 18)),
        ("high", pa.decimal128(32, 18)),
        ("low", pa.decimal128(32, 18)),
        ("close", pa.decimal128(32, 18)),
        ("volume", pa.int64()),
        ("currency", pa.string()),
        ("exchange", pa.string()),
        ("timezone", pa.string()),
        ("source", pa.string()),
        ("retrieved_at", pa.timestamp("us", tz="UTC")),
    ]
)


_DIVIDEND_SCHEMA = pa.schema(
    [
        ("security_id", pa.string()),
        ("ticker", pa.string()),
        ("exchange", pa.string()),
        ("ex_date", pa.date32()),
        ("amount", pa.decimal128(32, 18)),
        ("currency", pa.string()),
        ("pay_date", pa.date32()),
        ("record_date", pa.date32()),
        ("dividend_type", pa.string()),
        ("source_id", pa.string()),
        ("source_country", pa.string()),
        ("source", pa.string()),
        ("retrieved_at", pa.timestamp("us", tz="UTC")),
        ("ingested_at", pa.timestamp("us", tz="UTC")),
    ]
)


class ParquetStore:
    """Canonical store. Partition replacement occurs only after validation."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _price_path(self, market: str, year: int) -> Path:
        return self.root / "prices" / f"market={market.upper()}" / f"year={year}.parquet"

    def _manifest_path(self, market: str, year: int) -> Path:
        return self.root / "manifests" / "prices" / f"market={market.upper()}" / f"year={year}.json"

    @staticmethod
    def _price_table(rows: Iterable[PriceBar]) -> pa.Table:
        precision = Decimal("0.000000000000000001")
        payload = [
            {
                "security_id": str(row.security_id),
                "trading_date": row.trading_date,
                # Market-data providers expose IEEE floating-point values.
                # Canonical storage has an explicit 18-decimal scale, so trim
                # representation noise deterministically at this boundary.
                "open": row.open.quantize(precision),
                "high": row.high.quantize(precision),
                "low": row.low.quantize(precision),
                "close": row.close.quantize(precision),
                "volume": row.volume,
                "currency": row.currency,
                "exchange": row.exchange,
                "timezone": row.timezone,
                "source": row.source,
                "retrieved_at": row.retrieved_at,
            }
            for row in rows
        ]
        return pa.Table.from_pylist(payload, schema=_PRICE_SCHEMA)

    @staticmethod
    def _atomic_write_parquet(path: Path, table: pa.Table) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
        os.close(handle)
        temporary = Path(temporary_name)
        try:
            pq.write_table(table, temporary, compression="zstd")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
        os.close(handle)
        temporary = Path(temporary_name)
        try:
            temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def read_prices(self, *, market: str, year: int) -> list[PriceBar]:
        path = self._price_path(market, year)
        if not path.exists():
            return []
        return [PriceBar.model_validate(row) for row in pq.read_table(path).to_pylist()]

    def upsert_prices(self, *, market: str, rows: Iterable[PriceBar], pipeline_version: str) -> list[DatasetManifest]:
        """Merge by `(security_id, trading_date)` and atomically replace each affected partition."""

        incoming = list(rows)
        report = validate_prices(incoming)
        if not report.is_valid:
            raise ValueError(f"Refusing invalid price data: {'; '.join(report.errors)}")

        by_year: dict[int, list[PriceBar]] = defaultdict(list)
        for row in incoming:
            by_year[row.trading_date.year].append(row)

        manifests: list[DatasetManifest] = []
        for year, partition_rows in by_year.items():
            existing = self.read_prices(market=market, year=year)
            merged = {(row.security_id, row.trading_date): row for row in existing}
            merged.update({(row.security_id, row.trading_date): row for row in partition_rows})
            complete_rows = sorted(merged.values(), key=lambda row: (str(row.security_id), row.trading_date))
            complete_report = validate_prices(complete_rows)
            if not complete_report.is_valid:
                raise ValueError(f"Refusing invalid merged price data: {'; '.join(complete_report.errors)}")
            self._atomic_write_parquet(self._price_path(market, year), self._price_table(complete_rows))
            manifest = DatasetManifest(
                dataset="prices",
                source="multiple" if len({row.source for row in complete_rows}) > 1 else complete_rows[0].source,
                retrieved_at=datetime.now(UTC),
                first_date=complete_rows[0].trading_date.isoformat(),
                last_date=complete_rows[-1].trading_date.isoformat(),
                row_count=len(complete_rows),
                pipeline_version=pipeline_version,
            )
            self._atomic_write_json(self._manifest_path(market, year), manifest.model_dump(mode="json"))
            manifests.append(manifest)
        return manifests

    def _event_path(self, dataset: str, year: int, pair: str | None = None) -> Path:
        base = self.root / dataset
        if pair:
            base /= f"pair={pair}"
        return base / f"year={year}.parquet"

    @staticmethod
    def _read_models(path: Path, model):
        if not path.exists():
            return []
        return [model.model_validate(row) for row in pq.read_table(path).to_pylist()]

    def _upsert_events(self, *, dataset: str, rows: list, year_for, key_for, model, validator, pair_for=None) -> None:
        report = validator(rows)
        if not report.is_valid:
            raise ValueError(f"Refusing invalid {dataset} data: {'; '.join(report.errors)}")
        grouped: dict[tuple[int, str | None], list] = defaultdict(list)
        for row in rows:
            grouped[(year_for(row), pair_for(row) if pair_for else None)].append(row)
        for (year, pair), incoming in grouped.items():
            path = self._event_path(dataset, year, pair)
            existing = self._read_models(path, model)
            merged = {key_for(row): row for row in existing}
            # Event providers occasionally restate a dividend or split.  The
            # economic identity deliberately excludes value fields, so a
            # restatement replaces the prior observation instead of becoming
            # a second cash flow or split multiplier.  Retention is based on
            # when the provider observation was retrieved, with the incoming
            # row winning ties for deterministic refresh behaviour.
            for row in incoming:
                key = key_for(row)
                existing_row = merged.get(key)
                if (
                    existing_row is None
                    or not hasattr(row, "retrieved_at")
                    or row.retrieved_at >= existing_row.retrieved_at
                ):
                    merged[key] = row
            complete = list(merged.values())
            complete_report = validator(complete)
            if not complete_report.is_valid:
                raise ValueError(f"Refusing invalid merged {dataset} data: {'; '.join(complete_report.errors)}")
            payload = [item.model_dump(mode="json") for item in complete]
            self._atomic_write_parquet(path, pa.Table.from_pylist(payload))

    def upsert_dividends(self, rows: Iterable[DividendEvent]) -> None:
        incoming_rows = list(rows)
        report = validate_dividends(incoming_rows)
        if not report.is_valid:
            raise ValueError(f"Refusing invalid dividends data: {'; '.join(report.errors)}")
        grouped: dict[int, list[DividendEvent]] = defaultdict(list)
        for row in incoming_rows:
            grouped[row.ex_date.year].append(row)
        for year, incoming in grouped.items():
            path = self._event_path("dividends", year)
            existing = self._read_models(path, DividendEvent)
            merged = {dividend_event_key(row): row for row in existing}
            for row in incoming:
                economic_key = dividend_economic_key(row)
                replacement_keys = [
                    key
                    for key, current in merged.items()
                    if (
                        (
                            dividend_event_key(current) == dividend_event_key(row)
                            and current.source == row.source
                        )
                        or (
                            dividend_economic_key(current) == economic_key
                            and (current.source_id is None or current.source == row.source)
                        )
                    )
                ]
                for key in replacement_keys:
                    merged.pop(key, None)
                merged[dividend_event_key(row)] = row
            complete = list(merged.values())
            complete_report = validate_dividends(complete)
            if not complete_report.is_valid:
                raise ValueError(
                    f"Refusing invalid merged dividends data: {'; '.join(complete_report.errors)}"
                )
            payload = []
            for item in complete:
                row = item.model_dump(mode="python")
                row["security_id"] = str(item.security_id)
                row["dividend_type"] = item.dividend_type.value
                payload.append(row)
            self._atomic_write_parquet(path, pa.Table.from_pylist(payload, schema=_DIVIDEND_SCHEMA))

    def read_dividends(self, *, year: int) -> list[DividendEvent]:
        return self._read_models(self._event_path("dividends", year), DividendEvent)

    def upsert_corporate_actions(self, rows: Iterable[CorporateAction]) -> None:
        self._upsert_events(
            dataset="corporate_actions",
            rows=list(rows),
            year_for=lambda row: row.effective_date.year,
            key_for=lambda row: (row.security_id, row.effective_date, row.action_type),
            model=CorporateAction,
            validator=validate_corporate_actions,
        )

    def replace_corporate_action(
        self, *, existing: CorporateAction, replacement: CorporateAction
    ) -> None:
        """Replace one verified action classification without duplicating it."""

        if (
            existing.security_id != replacement.security_id
            or existing.effective_date != replacement.effective_date
        ):
            raise ValueError("Corporate-action replacement must keep security and effective date.")
        path = self._event_path("corporate_actions", existing.effective_date.year)
        rows = self._read_models(path, CorporateAction)
        old_key = (existing.security_id, existing.effective_date, existing.action_type)
        new_key = (replacement.security_id, replacement.effective_date, replacement.action_type)
        replaced = False
        complete: list[CorporateAction] = []
        for row in rows:
            key = (row.security_id, row.effective_date, row.action_type)
            if key == old_key:
                if replaced:
                    raise ValueError("Corporate-action replacement matched more than one row.")
                complete.append(replacement)
                replaced = True
            else:
                if key == new_key:
                    raise ValueError("Corporate-action replacement would create a duplicate key.")
                complete.append(row)
        if not replaced:
            raise KeyError(f"Corporate action not found for {existing.security_id} on {existing.effective_date}.")
        report = validate_corporate_actions(complete)
        if not report.is_valid:
            raise ValueError(f"Refusing invalid corporate-action replacement: {'; '.join(report.errors)}")
        payload = [item.model_dump(mode="json") for item in complete]
        self._atomic_write_parquet(path, pa.Table.from_pylist(payload))

    def read_corporate_actions(self, *, year: int) -> list[CorporateAction]:
        return self._read_models(self._event_path("corporate_actions", year), CorporateAction)

    def upsert_fx(self, rows: Iterable[FxRate]) -> None:
        self._upsert_events(
            dataset="fx",
            rows=list(rows),
            year_for=lambda row: row.rate_date.year,
            key_for=lambda row: (row.base_currency, row.rate_date),
            model=FxRate,
            validator=validate_fx,
            pair_for=lambda row: f"{row.base_currency}_SGD",
        )

    def read_fx(self, *, base_currency: str, year: int) -> list[FxRate]:
        return self._read_models(self._event_path("fx", year, f"{base_currency.upper()}_SGD"), FxRate)
