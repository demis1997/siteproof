"""Interrupt a fixture redesign worker and resume actual persistent workflow."""
import json
import time
from pathlib import Path

from phase34_run import create, wait
from stack_run import compose, request


def main():
    root=Path('evals/reports/phase34')
    source=json.loads((root/'development.json').read_text())
    identifier=next(s['job_id'] for s in source['samples'] if s['slug']=='maple-cleaning-overflow')
    job=request('GET',f'/api/jobs/{identifier}')
    assert job['data']['fixture']
    if job['status']!='needs_review' or job['data'].get('redesign_revision',0)>0:
        identifier=create('maple-cleaning-overflow')
        job=wait(identifier)
    assert job['data']['fixture'] and job['status']=='needs_review'
    findings=request('GET',f'/api/jobs/{identifier}/findings')['items']
    facts=request('GET',f'/api/jobs/{identifier}/facts')['items']
    request('POST',f'/api/jobs/{identifier}/approve',json={'finding_ids':[f['id'] for f in findings],'fact_ids':[f['id'] for f in facts]})
    request('POST',f'/api/jobs/{identifier}/redesign')
    for _ in range(120):
        stage=request('GET',f'/api/jobs/{identifier}')['stage']
        if stage=='verifying':
            break
        time.sleep(1)
    else:
        raise AssertionError('Did not observe verification stage')
    time.sleep(2)
    compose('kill','-s','SIGKILL','worker')
    compose('up','-d','worker')
    final=wait(identifier)
    assert final['status']=='needs_review' and final['data']['verification_passed'],final
    evidence=request('GET',f'/api/jobs/{identifier}/evidence')['items']
    assert len({e['id'] for e in evidence})==len(evidence)
    history=request('GET',f'/api/jobs/{identifier}/verification')['items']
    revision=final['data']['redesign_revision']
    current=[v for v in history if v['revision']==revision]
    assert len(current)==1 and current[0]['repair_attempts']==0
    events=request('GET',f'/api/jobs/{identifier}/events')['items']
    assert events
    report={'mode':'fixture','job_id':identifier,'status':'PASS','interrupted_stage':stage,'persistent_checkpoints':True,'unique_evidence_count':len(evidence),'verification_count':len(current),'event_count':len(events),'human_accepted':False,'boundary':'Actual worker SIGKILL during deterministic preview capture; no paid requests or simulated recovery.'}
    (root/'recovery.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))


if __name__=='__main__':
    main()
