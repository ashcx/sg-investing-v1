"""Independent amounts and cash-flow checks for initial plus recurring investing."""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from sg_investing.calculations.dca import DcaFrequency, dca_analysis
from sg_investing.models import AnalysisScenario, DividendEvent, FxRate, PriceBar, Security

CASES = json.loads((Path(__file__).parent / 'fixtures/redesign/sprint-11-dca.json').read_text())['fixtures']


def calculate(payload):
    sec = Security.model_validate(payload['security'])
    prices = [PriceBar.model_validate({**row, 'open': row['close'], 'high': row['close'],
               'low': row['close'], 'volume': 1, 'exchange': sec.exchange,
               'timezone': 'UTC', 'source': 'synthetic'}) for row in payload['prices']]
    return dca_analysis(
        security=sec, prices=prices,
        fx_rates=[FxRate.model_validate({**row, 'source': 'synthetic'}) for row in payload['fx_rates']],
        start_date=date.fromisoformat(payload['start_date']),
        end_date=date.fromisoformat(payload['end_date']),
        initial_sgd=payload['initial_sgd'], contribution_sgd=payload['contribution_sgd'],
        frequency=DcaFrequency(payload['frequency']),
        scenario=AnalysisScenario.model_validate(payload['scenario']),
        dividends=[DividendEvent.model_validate(row) for row in payload['dividends']],
    )


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['name'])
def test_independent_initial_lump_cases(case):
    result = calculate(case['input'])
    for field, expected in case['expected'].items():
        if field == 'recurring_count':
            assert len(result.contribution_dates) == expected
        else:
            assert abs(getattr(result, field) - Decimal(expected)) < Decimal('1e-9')
    if case['input']['initial_sgd'] != '0':
        assert result.methodology['initial_purchase_date'] == '2024-01-02'
        assert result.methodology['methodology_version'] == '1.1'
    if case['name'] == 'fx-initial-and-recurring':
        # Jan outflow 1100; Feb net inflow 650-100=550, 31 days apart.
        assert abs(float(result.xirr) - (0.5 ** (365.2425 / 31) - 1)) < 1e-9


@pytest.mark.parametrize('initial', ['-1', 'NaN', 'Infinity'])
def test_initial_lump_must_be_finite_non_negative(initial):
    payload = {**CASES[0]['input'], 'initial_sgd': initial}
    with pytest.raises(ValueError, match='finite and non-negative'):
        calculate(payload)
