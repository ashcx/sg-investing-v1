import copy
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('usability', Path(__file__).parents[1] / 'scripts/evaluate_usability.py')
usability = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usability)


def synthetic_record():
    return {'source': 'real_participant_sessions', 'candidate_commit': 'synthetic-test',
            'session_date': '2026-10-28', 'facilitator': 'synthetic-test', 'consent_recorded': True,
            'participants': [{'id': f'P{i}', 'unfamiliar_with_product': True,
                              'first_valid_result_seconds': 30,
                              'tasks': [{'task': t, 'unaided_completion': True,
                                         'identifies_currency': True, 'identifies_amount': True,
                                         'identifies_actual_period': True,
                                         'identifies_current_or_previous': True,
                                         'observation_notes': 'Synthetic gate test, not human evidence.'}
                                        for t in range(1, 5)]} for i in range(1, 6)]}


def test_missing_observations_are_not_passes():
    record = synthetic_record()
    record['participants'][0]['tasks'][0]['unaided_completion'] = None
    assert usability.evaluate(record)['verdict'] == 'NOT VERIFIED'


def test_thresholds_require_actual_targets():
    record = synthetic_record()
    assert usability.evaluate(record)['verdict'] == 'PASS'
    record['participants'][0]['tasks'][0]['unaided_completion'] = False
    assert usability.evaluate(record)['verdict'] == 'PASS'
    record['participants'][1]['tasks'][0]['unaided_completion'] = False
    assert usability.evaluate(record)['verdict'] == 'FAIL'
    record = copy.deepcopy(synthetic_record())
    for p in record['participants']:
        p['first_valid_result_seconds'] = 60
    assert usability.evaluate(record)['verdict'] == 'FAIL'
    record = synthetic_record()
    record['participants'][0]['tasks'][0]['identifies_actual_period'] = False
    assert usability.evaluate(record)['verdict'] == 'FAIL'
