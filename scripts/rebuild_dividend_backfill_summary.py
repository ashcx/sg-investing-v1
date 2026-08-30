"""Rebuild a durable per-security backfill summary from local coverage state."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from sg_investing.data.dividend_quality import load_coverage_report

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-report", type=Path, default=ROOT / "data" / "dividends" / "coverage_report.json")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    report = load_coverage_report(args.coverage_report)
    if report is None:
        raise RuntimeError(f"Coverage report does not exist: {args.coverage_report}")

    results = []
    for record in report.securities:
        if record.coverage_status in {
            "data_available",
            "data_available_policy_unknown",
        }:
            status = record.coverage_status
        elif record.coverage_status == "unknown" and record.provider_query_succeeded:
            status = "query_succeeded_empty"
        else:
            status = record.coverage_status
        results.append(
            {
                "security_id": str(record.security_id),
                "ticker": record.ticker,
                "start_date": (record.queried_from or record.required_start_date).isoformat(),
                "end_date": (record.queried_through or report.generated_at.date()).isoformat(),
                "status": status,
                "rows_fetched": record.event_count,
                "error": record.error,
            }
        )
    output = args.output or args.coverage_report.parent / "backfill_summary.json"
    output.write_text(
        json.dumps(
            {
                "coverage_report": str(args.coverage_report),
                "coverage_history": str(output.parent / "coverage_history.json"),
                "reconstructed_from_coverage_report": True,
                "reconstructed_at": datetime.now(UTC).isoformat(),
                "summary": report.summary,
                "results": results,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output), "results": len(results)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
