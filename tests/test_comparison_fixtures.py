"""Independent fixed amounts for Sprint 12's existing one-time engine contract."""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from sg_investing.analysis import analyze_security
from sg_investing.models import AnalysisScenario, DividendEvent, FxRate, PriceBar, Security, TaxRule

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/redesign/sprint-12.json').read_text())


@pytest.mark.parametrize('case', FIXTURE['cases'], ids=lambda case: case['name'])
def test_comparison_independent_values_and_actual_dates(case):
    item = next(s for s in FIXTURE['securities'] if s['security']['ticker'] == case['ticker'])
    security = Security.model_validate(item['security'])
    prices = [PriceBar.model_validate({**row, 'open': row['close'], 'high': row['close'],
              'low': row['close'], 'volume': 1, 'exchange': security.exchange,
              'timezone': 'UTC', 'source': 'synthetic'}) for row in item['prices']]
    result = analyze_security(
        security=security, prices=prices,
        fx_rates=[FxRate.model_validate({**row, 'source': 'synthetic'})
                  for row in item['fx_rates']],
        start_date=date.fromisoformat(case['start']), end_date=date.fromisoformat(case['end']),
        initial_sgd='1000', scenario=AnalysisScenario.model_validate(case['scenario']),
        dividends=[DividendEvent.model_validate(row) for row in item['dividends']],
        tax_rules=[TaxRule.model_validate(row) for row in FIXTURE['tax_rules']],
    ).model_dump(mode='json')
    expected = case['expected']
    assert Decimal(result['investment']['final_value_sgd']) == Decimal(expected['final_value_sgd'])
    assert Decimal(result['returns']['total_return']) == Decimal(expected['total_return'])
    assert Decimal(result['returns']['total_return_foreign_currency']) == Decimal(expected['native_return'])
    assert result['period'] == {'start_date': expected['start'], 'end_date': expected['end']}
