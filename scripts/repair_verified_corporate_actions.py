"""Apply locally verified corporate-action classifications."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from sg_investing.data.storage import ParquetStore
from sg_investing.models import CorporateActionType
from sg_investing.universe.catalog import load_catalog


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    catalog = load_catalog(ROOT / "data" / "universe" / "current_catalog.json")
    dbs = catalog.security_by_ticker("D05.SI")
    store = ParquetStore(ROOT / "data")
    actions = store.read_corporate_actions(year=2024)
    matches = [
        action
        for action in actions
        if action.security_id == dbs.security_id
        and action.effective_date == date(2024, 4, 22)
        and action.action_type == CorporateActionType.SPLIT
        and action.ratio == Decimal("1.1")
    ]
    if len(matches) == 1:
        replacement = matches[0].model_copy(update={"action_type": CorporateActionType.BONUS_ISSUE})
        store.replace_corporate_action(existing=matches[0], replacement=replacement)
        result = {"status": "updated", "ticker": dbs.ticker, "effective_date": "2024-04-22", "action_type": "bonus_issue"}
    elif len(matches) == 0:
        result = {"status": "unchanged", "reason": "verified DBS action is already migrated or absent"}
    else:
        raise RuntimeError("Expected at most one matching DBS corporate action.")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
