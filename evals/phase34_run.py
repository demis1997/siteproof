"""Real-stack fixture audit -> input approval -> redesign -> verification -> review.

All review decisions here simulate operator actions; subjective human review is pending.
"""
import json
import platform
import statistics
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx
from stack_run import HEADERS, compose, request

OUT = Path('evals/reports/phase34')


def wait(identifier, limit=600):
    started = time.monotonic()
    while time.monotonic()-started < limit:
        try:
            job = request('GET', f'/api/jobs/{identifier}')
        except (httpx.TransportError, httpx.HTTPStatusError):
            time.sleep(2)
            continue
        if job['status'] in ('needs_review', 'failed', 'cancelled', 'completed'):
            return job
        time.sleep(2)
    raise RuntimeError('Timed out waiting for '+identifier)


def create(slug='overflow'):
    response = httpx.post('http://localhost:8000/api/jobs', headers=dict(HEADERS, **{'Idempotency-Key':'phase34-'+str(uuid.uuid4())}), json={'url':'http://fixture.siteproof.test/'+slug}, timeout=20)
    response.raise_for_status()
    return response.json()['id']


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    identifier = create()
    job = wait(identifier)
    assert job['status'] == 'needs_review', job
    findings = request('GET', f'/api/jobs/{identifier}/findings')['items']
    facts = request('GET', f'/api/jobs/{identifier}/facts')['items']
    assert any(f['verification_method']=='horizontal_overflow' for f in findings)
    request('POST', f'/api/jobs/{identifier}/approve', json={'finding_ids':[f['id'] for f in findings], 'fact_ids':[f['id'] for f in facts]})
    start = time.monotonic()
    request('POST', f'/api/jobs/{identifier}/redesign')
    assert wait(identifier)['status'] == 'needs_review'
    verifications = request('GET', f'/api/jobs/{identifier}/verification')['items']
    assert verifications[-1]['required_checks_passed'], verifications
    evidence = request('GET', f'/api/jobs/{identifier}/evidence')['items']
    assert len([e for e in evidence if e['kind']=='screenshot']) >= 4
    lh = [e for e in evidence if e['kind']=='lighthouse']
    assert len(lh)>=4 and all(e['sample_count']==2 for e in lh)
    preview = httpx.get(f'http://localhost:8000/api/jobs/{identifier}/preview-html',headers=HEADERS)
    assert preview.status_code==200 and 'noindex' in preview.headers['x-robots-tag']
    assert '<script' not in preview.text
    assert httpx.get(f'http://localhost:8000/api/jobs/{identifier}/preview-html').status_code==401
    assert httpx.get(f'http://localhost:8000/api/jobs/{identifier}/preview-html',headers={'X-Tenant-Key':'other-key'}).status_code==404
    request('POST', f'/api/jobs/{identifier}/review',json={'decision':'reject'})
    assert request('GET', f'/api/jobs/{identifier}')['status']=='needs_review'
    request('POST', f'/api/jobs/{identifier}/review',json={'decision':'accept'})
    assert request('GET', f'/api/jobs/{identifier}')['status']=='completed'
    repaired = {'job_id':identifier,'targeted_repair':True,'facts_preserved':verifications[-1]['facts_preserved'],'verification':verifications,'redesign_latency_seconds':time.monotonic()-start,'review_boundary':'API accept/reject exercised by test script, not independent human quality acceptance'}
    (OUT/'pipeline.json').write_text(json.dumps(repaired,indent=2))
    print('Phase 3 pipeline PASS',flush=True)
    faults=json.loads(compose('exec','-T','worker','python','evals/phase34_faults.py',identifier))
    (OUT/'faults.json').write_text(json.dumps(faults,indent=2))
    for row in faults['scenarios']:
        if not row['verification_passed']:
            response=httpx.post(f"http://localhost:8000/api/jobs/{row['job_id']}/review",headers=HEADERS,json={'decision':'accept'})
            assert response.status_code==409
            row['failed_acceptance_http_status']=response.status_code
    (OUT/'faults.json').write_text(json.dumps(faults,indent=2))
    print('Real regression/repair/exhaustion PASS',flush=True)
    # Three simultaneous submissions; domain and browser concurrency stay one.
    submitted=time.monotonic()
    slugs=['maple-cleaning-clean','maple-cleaning-overflow','cedar-electric-clean']
    with ThreadPoolExecutor(max_workers=3) as pool:
        ids=list(pool.map(create,slugs))
    durations=[]
    failures=[]
    development=[]
    for i in ids:
        j=wait(i)
        duration=time.monotonic()-submitted
        durations.append(duration)
        if j['status']!='needs_review' or j.get('error'): failures.append({'job_id':i,'error':j.get('error')})
        observed=request('GET',f'/api/jobs/{i}/findings')['items']
        expected={'horizontal_overflow'} if slugs[ids.index(i)].endswith('overflow') else set()
        actual={f['category'] for f in observed if f['kind']=='objective_defect'}
        captured=request('GET',f'/api/jobs/{i}/evidence')['items']
        available={e['id'] for e in captured}
        development.append({'slug':slugs[ids.index(i)],'job_id':i,'expected_categories':sorted(expected),'actual_categories':sorted(actual),'true_positive_categories':len(actual & expected),'false_positive_categories':len(actual-expected),'false_negative_categories':len(expected-actual),'evidence_support':all(set(f['evidence_ids'])<=available for f in observed),'finding_count':len(observed)})
    load={'mode':'fixture','sample_size':3,'submission_concurrency':3,'worker_count':1,'per_domain_limit':1,'browser_limit':1,'hardware':{'host_platform':platform.platform(),'machine':platform.machine(),'docker':subprocess.run(['docker','info','--format','{{.NCPU}} CPUs, {{.MemTotal}} bytes'],capture_output=True,text=True,check=True).stdout.strip()},'completion_count':3-len(failures),'failures':failures,'p50_latency_seconds':statistics.median(durations),'p95_latency_seconds':max(durations),'latencies_seconds':durations,'limitations':['Small fixture-provider queue burst; not live inference capacity or a scalability benchmark.','Latency measured from shared submission start to each observed completion.']}
    (OUT/'development.json').write_text(json.dumps({'split':'dev','labels_author':'coding-agent','samples':development,'note':'Category-level labels, not instance-level defect counts; independent review pending.'},indent=2))
    (OUT/'load.json').write_text(json.dumps(load,indent=2))
    assert not failures,failures
    cancelled=create('clean'); request('POST',f'/api/jobs/{cancelled}/cancel')
    time.sleep(3); assert request('GET',f'/api/jobs/{cancelled}')['status']=='cancelled'
    report={'generated_at':datetime.now(UTC).isoformat(),'commit':subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip(),'mode':'fixture','pipeline':repaired,'faults':faults,'load':load,'cancellation':'PASS','comparisons':{'A_single_prompt':{'status':'BLOCKED','repair_metrics':'not_applicable','reason':'Live provider preflight rejected HTTP429; no paid baseline run'},'B_RAG_audit':{'status':'BLOCKED','repair_metrics':'not_applicable','reason':'Live provider preflight rejected HTTP429; fixture auditor is deterministic, not a live baseline'},'C_fixture_workflow':{'status':'PASS','sample_size':1,'targeted_repair_success':1,'critical_fact_preservation':1}},'limitations':['Agent-authored labels and automated review decisions are not independent human assessments.','One synthetic business in the pipeline scenario; no client generalization.','Live A/B/C quality comparison remains blocked.']}
    (OUT/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'status':'PASS','load_completion_count':load['completion_count'],'load_sample_size':3}))


if __name__=='__main__':
    main()
