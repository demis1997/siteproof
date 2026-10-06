"""Executable acceptance-contract gates, not hardcoded achieved performance."""
import json
from pathlib import Path


def main():
    root=Path('evals/reports/phase34')
    pipeline=json.loads((root/'pipeline.json').read_text())
    assert pipeline['facts_preserved']
    assert pipeline['verification'][-1]['required_checks_passed']
    assert all(v['repair_attempts']<=2 for v in pipeline['verification'])
    faults=json.loads((root/'faults.json').read_text())
    repaired=next(s for s in faults['scenarios'] if s['scenario']=='repaired-regression')
    exhausted=next(s for s in faults['scenarios'] if s['scenario']=='repair-exhaustion')
    assert not repaired['verification'][0]['required_checks_passed']
    assert repaired['verification_passed'] and repaired['repair_attempts']==1
    assert not exhausted['verification_passed'] and exhausted['repair_attempts']==2
    assert exhausted['failed_acceptance_http_status']==409
    development=json.loads((root/'development.json').read_text())
    # Critical executable labels are functional contracts, not statistical targets.
    assert all(s['false_negative_categories']==0 and s['evidence_support'] for s in development['samples'])
    load=json.loads((root/'load.json').read_text())
    assert load['completion_count']==load['sample_size'] and not load['failures']
    print('PASS: targeted repairs, evidence integrity, fact preservation, regression rejection, repair cap and fixture burst completion')


if __name__=='__main__':
    main()
