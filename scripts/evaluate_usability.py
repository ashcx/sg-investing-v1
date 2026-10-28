"""Check recorded release-session evidence without filling missing observations."""

import json
import math
import statistics
import sys


def evaluate(record):
    missing = []
    if record.get('source') != 'real_participant_sessions':
        missing.append('real participant sessions have not been recorded')
    for key in ['candidate_commit', 'session_date', 'facilitator']:
        if not record.get(key):
            missing.append(f'missing {key}')
    if record.get('consent_recorded') is not True:
        missing.append('consent not recorded')
    participants = record.get('participants', [])
    if len(participants) != 5 or len({p.get('id') for p in participants}) != 5:
        missing.append('five distinct participants required')
    fields = ['unaided_completion', 'identifies_currency', 'identifies_amount',
              'identifies_actual_period', 'identifies_current_or_previous']
    for person in participants:
        if person.get('unfamiliar_with_product') is not True:
            missing.append(f'{person.get("id")}: unfamiliar participant not confirmed')
        duration = person.get('first_valid_result_seconds')
        if isinstance(duration, bool) or not isinstance(duration, (float, int)) or not math.isfinite(duration) or duration < 0:
            missing.append(f'{person.get("id")}: missing valid timing')
        tasks = person.get('tasks', [])
        if sorted(t.get('task', 0) for t in tasks) != [1, 2, 3, 4]:
            missing.append(f'{person.get("id")}: four task observations required')
        for task in tasks:
            if any(not isinstance(task.get(f), bool) for f in fields):
                missing.append(f'{person.get("id")}/task {task.get("task")}: missing observations')
            if not task.get('observation_notes'):
                missing.append(f'{person.get("id")}/task {task.get("task")}: missing notes')
    if missing:
        return {'verdict': 'NOT VERIFIED', 'missing': missing}
    counts = {str(t): sum(next(x for x in p['tasks'] if x['task'] == t)['unaided_completion'] for p in participants) for t in range(1, 5)}
    median = statistics.median(p['first_valid_result_seconds'] for p in participants)
    understood = all(all(task[f] for f in fields[1:]) for p in participants for task in p['tasks'])
    passed = all(n >= 4 for n in counts.values()) and median < 60 and understood
    return {'verdict': 'PASS' if passed else 'FAIL', 'unaided_completions': counts,
            'median_first_valid_result_seconds': median, 'all_attributes_identified': understood}


if __name__ == '__main__':
    with open(sys.argv[1], encoding='utf-8') as stream:
        result = evaluate(json.load(stream))
    print(json.dumps(result, indent=2))
    sys.exit(0 if result['verdict'] == 'PASS' else 2)
