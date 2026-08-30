from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from sg_investing.data.backfill import (
    MAX_ATTEMPTS,
    MAX_INTERNAL_PRICE_GAP_SESSIONS,
    backfill_missing_prices,
    load_or_reconcile_state,
    scan_price_coverage,
)
from sg_investing.data.storage import ParquetStore
from tests.helpers import OTHER_SECURITY_ID, TEST_SECURITY_ID, price, security


class FakeBatchProvider:
    name = "fake"

    def __init__(self, successful_ids: set) -> None:
        self.successful_ids = successful_ids
        self.calls: list[list[str]] = []

    def get_prices_batch(self, securities, start_date, end_date, *, workers):
        self.calls.append([str(security_row.security_id) for security_row in securities])
        rows = {
            security_row.security_id: [
                price(security_row, date(2024, 1, 2) + timedelta(days=offset))
                for offset in range(20)
            ]
            for security_row in securities
            if security_row.security_id in self.successful_ids
        }
        errors = {
            security_row.security_id: "No provider history"
            for security_row in securities
            if security_row.security_id not in self.successful_ids
        }
        return rows, errors, {}


class DurableBackfillTests(TestCase):
    def test_internal_market_session_gaps_are_incomplete(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ParquetStore(root / "data")
            complete = security(ticker="CALENDAR")
            sparse = security(
                ticker="SPARSE",
                security_id="33333333-3333-3333-3333-333333333333",
            )
            sessions = [
                date(2024, 1, 2) + timedelta(days=offset)
                for offset in range(45)
                if (date(2024, 1, 2) + timedelta(days=offset)).weekday() < 5
            ]
            store.upsert_prices(
                market="US",
                rows=[price(complete, trading_date) for trading_date in sessions]
                + [
                    price(sparse, trading_date)
                    for index, trading_date in enumerate(sessions)
                    if not 10 <= index < 18
                ],
                pipeline_version="test",
            )

            coverage = scan_price_coverage(store)
            sparse_coverage = coverage[str(sparse.security_id)]
            self.assertEqual(sparse_coverage["internal_gap_sessions"], 8)
            self.assertEqual(sparse_coverage["max_internal_gap_sessions"], 8)
            self.assertGreater(
                sparse_coverage["max_internal_gap_sessions"], MAX_INTERNAL_PRICE_GAP_SESSIONS
            )

            state = load_or_reconcile_state(
                root / "backfill" / "state.json",
                [sparse],
                coverage,
                as_of=sessions[-1],
            )
            record = state["securities"][str(sparse.security_id)]
            self.assertEqual(record["status"], "incomplete")
            self.assertIn("largest internal gap", record["warning"])

    def test_backfill_gate_reconciles_internal_gaps_after_writing(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ParquetStore(root / "data")
            calendar_security = security(ticker="CALENDAR")
            target = security(
                ticker="TARGET",
                security_id="33333333-3333-3333-3333-333333333333",
            )
            sessions = [
                date(2024, 1, 2) + timedelta(days=offset)
                for offset in range(45)
                if (date(2024, 1, 2) + timedelta(days=offset)).weekday() < 5
            ]
            store.upsert_prices(
                market="US",
                rows=[price(calendar_security, trading_date) for trading_date in sessions],
                pipeline_version="test",
            )

            class SparseProvider:
                name = "sparse"

                def get_prices_batch(self, securities, start_date, end_date, *, workers):
                    rows = {
                        row.security_id: [
                            price(row, trading_date)
                            for index, trading_date in enumerate(sessions)
                            if not 10 <= index < 18
                        ]
                        for row in securities
                    }
                    return rows, {}, {}

            state_path = root / "backfill" / "state.json"
            summary_path = root / "backfill" / "summary.json"
            backfill_missing_prices(
                securities=[target],
                store=store,
                provider=SparseProvider(),
                start_date=sessions[0],
                end_date=sessions[-1],
                workers=1,
                state_path=state_path,
                summary_path=summary_path,
            )

            record = json.loads(state_path.read_text())["securities"][str(target.security_id)]
            self.assertEqual(record["bars"], len(sessions) - 8)
            self.assertEqual(record["max_internal_gap_sessions"], 8)
            self.assertEqual(record["status"], "incomplete")

    def test_stale_or_too_short_history_is_retried_instead_of_marked_stored(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ParquetStore(root / "data")
            equity = security(security_id=TEST_SECURITY_ID, ticker="STALE")
            store.upsert_prices(
                market="US", rows=[price(equity, date(2024, 1, 2))], pipeline_version="test"
            )
            provider = FakeBatchProvider({equity.security_id})
            state_path = root / "backfill" / "state.json"
            summary_path = root / "backfill" / "summary.json"

            backfill_missing_prices(
                securities=[equity],
                store=store,
                provider=provider,
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                workers=1,
                state_path=state_path,
                summary_path=summary_path,
            )

            record = json.loads(state_path.read_text())["securities"][str(equity.security_id)]
            self.assertEqual(len(provider.calls), 1)
            self.assertEqual(record["status"], "incomplete")
            self.assertIn("business days", record["warning"])

    def test_state_bar_count_matches_deduplicated_parquet_after_overlap(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ParquetStore(root / "data")
            equity = security(security_id=TEST_SECURITY_ID, ticker="OVERLAP")
            store.upsert_prices(
                market="US",
                rows=[price(equity, date(2024, 1, 2) + timedelta(days=offset)) for offset in range(10)],
                pipeline_version="test",
            )
            state_path = root / "backfill" / "state.json"
            summary_path = root / "backfill" / "summary.json"

            backfill_missing_prices(
                securities=[equity],
                store=store,
                provider=FakeBatchProvider({equity.security_id}),
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 31),
                workers=1,
                state_path=state_path,
                summary_path=summary_path,
            )

            record = json.loads(state_path.read_text())["securities"][str(equity.security_id)]
            actual = scan_price_coverage(store)[str(equity.security_id)]
            self.assertEqual(record["bars"], actual["bars"])
            self.assertEqual(record["bars"], 20)

    def test_persisted_prices_override_a_stale_failed_state(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ParquetStore(root / "data")
            equity = security()
            store.upsert_prices(
                market="US", rows=[price(equity, date(2024, 1, 2))], pipeline_version="test"
            )
            state_path = root / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "securities": {
                            str(equity.security_id): {"status": "failed", "attempts": 1}
                        },
                    }
                )
            )

            state = load_or_reconcile_state(
                state_path, [equity], scan_price_coverage(store)
            )

            record = state["securities"][str(equity.security_id)]
            self.assertEqual(record["status"], "stored")
            self.assertEqual(record["bars"], 1)
            self.assertEqual(record["attempts"], 1)

    def test_reconciliation_clears_stale_stored_record_without_parquet_rows(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            equity = security()
            state_path = root / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "version": 2,
                        "securities": {
                            str(equity.security_id): {
                                "status": "stored",
                                "bars": 999,
                                "first_price_date": "2000-01-01",
                                "last_price_date": "2024-01-01",
                                "attempts": 2,
                            }
                        },
                    }
                )
            )

            state = load_or_reconcile_state(state_path, [equity], {})

            record = state["securities"][str(equity.security_id)]
            self.assertEqual(record["status"], "pending")
            self.assertEqual(record["bars"], 0)
            self.assertIsNone(record["first_price_date"])
            self.assertIsNone(record["last_price_date"])

    def test_missing_securities_are_persisted_and_failed_tickers_retry_then_stop(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ParquetStore(root / "data")
            succeeded = security(security_id=TEST_SECURITY_ID, ticker="GOOD")
            unavailable = security(security_id=OTHER_SECURITY_ID, ticker="MISSING")
            state_path = root / "backfill" / "state.json"
            summary_path = root / "backfill" / "summary.json"
            provider = FakeBatchProvider({succeeded.security_id})

            first = backfill_missing_prices(
                securities=[succeeded, unavailable],
                store=store,
                provider=provider,
                start_date=date(2000, 1, 1),
                end_date=date(2024, 1, 3),
                workers=1,
                state_path=state_path,
                summary_path=summary_path,
                batch_size=2,
            )
            state = json.loads(state_path.read_text())
            records = state["securities"]
            self.assertEqual(first["run"]["attempted"], 2)
            self.assertEqual(records[str(succeeded.security_id)]["status"], "stored")
            self.assertEqual(records[str(unavailable.security_id)]["status"], "failed")
            self.assertEqual(records[str(unavailable.security_id)]["attempts"], 1)

            for expected_attempts in range(2, MAX_ATTEMPTS + 1):
                backfill_missing_prices(
                    securities=[succeeded, unavailable],
                    store=store,
                    provider=provider,
                    start_date=date(2000, 1, 1),
                    end_date=date(2024, 1, 3),
                    workers=1,
                    state_path=state_path,
                    summary_path=summary_path,
                    batch_size=2,
                )
                state = json.loads(state_path.read_text())
                record = state["securities"][str(unavailable.security_id)]
                self.assertEqual(record["attempts"], expected_attempts)

            self.assertEqual(record["status"], "unavailable")
            final = backfill_missing_prices(
                securities=[succeeded, unavailable],
                store=store,
                provider=provider,
                start_date=date(2000, 1, 1),
                end_date=date(2024, 1, 3),
                workers=1,
                state_path=state_path,
                summary_path=summary_path,
                batch_size=2,
            )
            self.assertEqual(final["run"]["attempted"], 0)
            self.assertEqual(json.loads(summary_path.read_text())["by_status"], {"stored": 1, "unavailable": 1})
