"""Summarise observed fixture results without manufacturing live measurements."""
import hashlib
import json
import os
import subprocess
from pathlib import Path


def main():
    root=Path('evals/reports/phase34')
    report=json.loads((root/'report.json').read_text())
    base=report.pop('commit',None) or report.get('source_provenance',{}).get('base_commit') or subprocess.run(['git','rev-parse','HEAD'],check=True,capture_output=True,text=True).stdout.strip()
    report['source_provenance']={'base_commit':os.getenv('GITHUB_SHA',base),'working_tree_changes':not bool(os.getenv('GITHUB_SHA')),'note':'GitHub CI records its exact committed source revision; local observations include implementation working-tree changes.'}
    dev=json.loads((root/'development.json').read_text())
    tp=sum(s['true_positive_categories'] for s in dev['samples'])
    fp=sum(s['false_positive_categories'] for s in dev['samples'])
    fn=sum(s['false_negative_categories'] for s in dev['samples'])
    report['development_metrics']={'sample_size':len(dev['samples']),'grading_unit':'category per page','tp':tp,'fp':fp,'fn':fn,'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,'evidence_support_pages':sum(s['evidence_support'] for s in dev['samples']),'independent_human_labels':False}
    report['held_out_label_sha256']=hashlib.sha256(Path('evals/labels.json').read_bytes()).hexdigest()
    for filename,key in [('recovery.json','redesign_restart_recovery'),('phase34-ui.json','ui')]:
        if (root/filename).exists():
            report[key]=json.loads((root/filename).read_text())
        else:
            report[key]={'status':'UNVERIFIED'}
    report['blocked']=['live model quality','semantic retrieval','actual inference costs','independent human design quality']
    report['paid_validation']={'requests_stopped':True,'automatic_429_retry':False,'reserved_usd':2,'unallocated_usd':3.6345,'actual_cost_usd':None,'note':'Existing ledger reservations preserved; not measured invoice charges.'}
    (root/'report.json').write_text(json.dumps(report,indent=2))
    load=report['load']
    lines=['# Observed Phase 3–4 fixture validation','', 'Mode: **fixture providers; real Docker/browser/database/storage**. Live AI quality, semantic retrieval and inference costs: **BLOCKED**.','',f"Normal full pipeline: targeted repair and fact preservation passed ({report['comparisons']['C_fixture_workflow']['sample_size']} synthetic homepage). API test acceptance is not a human quality review.",'',f"Development labels: {tp} TP, {fp} FP, {fn} FN categories across {len(dev['samples'])} pages; two supported viewport findings on the positive page. Labels are coding-agent authored, not independent human labels.",'', 'Controlled fault checks: initial regression rejected; one layout repair passed; persistent overflow stopped after two repairs; failed acceptance returned HTTP 409. Duplicate delivery created no additional evidence.','',f"Fixture load: {load['completion_count']}/{load['sample_size']} completed; queue-inclusive p50 {load['p50_latency_seconds']:.2f}s, p95 {load['p95_latency_seconds']:.2f}s. Three observations, one worker, browser/domain limit one; not scalability or inference throughput.",'',f"Redesign worker restart: {report['redesign_restart_recovery']['status']}. UI browser checks: {report['ui']['status']}.",'', 'Each viewport has two real Lighthouse measurements before and after plus axe/DOM checks. Scores are diagnostic; no WCAG-compliance or conversion claims.','', 'Original held-out labels retained unchanged. Nine-page contract evaluation is distinct from real browser grading and cannot measure model quality. A/B live baselines remain blocked; repair metrics are not applicable to audit-only arms.','', 'Paid ledger: USD 2 reserved, USD 3.6345 unallocated under the existing ceiling. Actual failed-request cost remains unknown. OpenAI zero balance prevents live validation; no further paid request or retry was made.','', 'Source provenance: local runs include working-tree changes on the recorded base commit. Final GitHub CI artifacts carry the committed revision. See JSON for sample sizes, artifacts, hardware and limitations.']
    (root/'report.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':
    main()
