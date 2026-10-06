"""Opt-in A/B experiment on identical persisted evidence; never a fixture-AI baseline."""
import argparse
import json
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services'))
from siteproof.config import settings
from siteproof.contracts import Budget
from siteproof.db import connection, get_job
from siteproof.live_limits import allocate
from siteproof.providers import LiveProvider, provider_error_report
from siteproof.retrieval import cached_embedding, index_embeddings, retrieve


def run(job_id, tenant, execute=False):
    report={'experiment':'controlled-capture-audit-baseline-v1','arms':{'A':{'name':'single-prompt, no guidance','repair_metrics':'not_applicable'},'B':{'name':'same evidence/model plus hybrid guidance','repair_metrics':'not_applicable'},'C':{'name':'B plus constrained design/verification','execution':'separate end-to-end job','repair_metrics':'reported only from real completed workflow'}},'maximum_tokens_per_arm':12000,'reranking':False,'status':'PREPARED; paid execution disabled','limitations':['Coding-agent labels need human review.','A/B retain executable deterministic findings; compare hypotheses separately, not as proven defects.','No independent client population estimate from related synthetic variants.']}
    maximum_rate=max(settings.input_cost_per_million or 0,settings.output_cost_per_million or 0)
    report['estimated_upper_usd_per_arm']=12000*maximum_rate/1000000 if settings.prices_known() else None
    if not execute:
        return report
    if settings.mode!='live' or os.getenv('SITEPROOF_ALLOW_PAID_BASELINES')!='true':
        raise ValueError('Live mode and explicit SITEPROOF_ALLOW_PAID_BASELINES=true required')
    if not job_id:
        raise ValueError('Existing captured job required; never recapture automatically')
    job=get_job(tenant,job_id)
    if not job:
        raise ValueError('Job unavailable to this tenant')
    with connection() as conn:
        original=conn.execute("SELECT result FROM workflow_steps WHERE tenant_id=%s AND job_id=%s AND step='capture-v1' AND status='succeeded'",(tenant,job_id)).fetchone()
    if not original:
        raise ValueError('Durable capture required')
    model=LiveProvider()
    rows=[]
    for arm in ['A','B']:
        money=allocate(tenant,settings.live_validation_session,'audit')
        budget=Budget(max_tokens=12000,max_tool_calls=20,max_seconds=180,max_cost=money)
        guidance=[]
        try:
            if arm=='B':
                index_embeddings(tenant,model,budget)
                query='accessibility OR contact OR mobile OR navigation'
                vector=cached_embedding(tenant,query,model,budget)
                guidance=retrieve(tenant,query,embedding=vector,use_reranker=False)
            findings,usage=model.findings(original['result']['evidence'],guidance,images=original['result']['screenshots'],budget=budget)
            budget.consume(tokens=usage['tokens'],cost=usage['cost'])
            rows.append({'arm':arm,'findings':findings,'run':usage,'guidance_ids':[g['id'] for g in guidance],'budget':budget.model_dump()})
        except httpx.HTTPStatusError as exc:
            report.update(status='BLOCKED',provider_error=provider_error_report(exc.response),rows=rows)
            return report
    report.update(status='OBSERVED',rows=rows,job_id=job_id,grading='Returned findings are inspectable; model hypotheses require separate human rubric. Do not use original model findings as independent truth.')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--job-id')
    parser.add_argument('--tenant',default='local')
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    print(json.dumps(run(args.job_id,args.tenant,args.execute),indent=2))
