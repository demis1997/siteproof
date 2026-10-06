"""Controlled renderer fault injection against real services, never model output."""
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services'))
from psycopg.types.json import Jsonb
from siteproof import db, workflow
from siteproof.config import settings


def run(source_id):
    if settings.mode != 'fixture':
        raise ValueError('Fault injection is fixture-only')
    source = db.get_job('integration', source_id)
    rows = []
    for name, selector, expected_attempts in [('repaired-regression', '.editorial .preview-hero', 1), ('repair-exhaustion', '.preview-hero', 2)]:
        identifier = str(uuid.uuid4())
        budget = {'max_tokens': 12000, 'max_tool_calls': 60, 'max_seconds': 600, 'max_cost': None}
        with db.connection() as conn:
            conn.execute("INSERT INTO audit_jobs(id,tenant_id,idempotency_key,submitted_url,canonical_url,status,stage,data) VALUES(%s,'integration',%s,%s,%s,'designing','designing',%s)", (identifier, identifier, source['submitted_url'], source['canonical_url'], Jsonb({'fixture': True, 'budget': budget, 'redesign_revision': 1, 'test_fault': name})))
            captured = conn.execute("SELECT result FROM workflow_steps WHERE tenant_id='integration' AND job_id=%s AND step='capture-v1'", (source_id,)).fetchone()
            conn.execute("INSERT INTO workflow_steps(tenant_id,job_id,step,status,result) VALUES('integration',%s,'capture-v1','succeeded',%s)", (identifier, Jsonb(captured['result'])))
        for kind in ['Evidence', 'Finding', 'BusinessFact']:
            items = db.records('integration', source_id, kind)
            if kind != 'Evidence':
                for item in items:
                    item['approved'] = True
            db.save_records('integration', identifier, kind, items)
        original = workflow.render_spec

        def faulty_render(state, selector=selector, original=original, identifier=identifier):
            original(state)
            state['html'] = state['html'].replace('</style>', selector+'{min-width:1800px!important}</style>')
            db.save_records('integration', identifier, 'Redesign', [{'id': f"redesign-{state['revision']}-{state.get('repair_attempts', 0)}", 'html': state['html'], 'spec': state['spec'], 'version': 'controlled-render-fault-v1', 'test_injection': True}])

        workflow.render_spec = faulty_render
        start = time.monotonic()
        try:
            workflow.run_job('integration', identifier, 'redesign')
        finally:
            workflow.render_spec = original
        verifications = db.records('integration', identifier, 'VerificationResult')
        assert len(verifications) == expected_attempts + 1, verifications
        assert verifications[0]['required_checks_passed'] is False
        assert verifications[-1]['required_checks_passed'] is (name == 'repaired-regression')
        designs = db.records("integration", identifier, "Redesign")
        assert len(designs) == expected_attempts + 1, designs
        before_count = len(db.records('integration', identifier, 'Evidence'))
        workflow.run_job('integration', identifier, 'redesign')
        assert len(db.records('integration', identifier, 'Evidence')) == before_count
        assert db.get_job('integration', identifier)['status'] == 'needs_review'
        rows.append({'scenario': name, 'job_id': identifier, 'repair_attempts': expected_attempts, 'verification_passed': verifications[-1]['required_checks_passed'], 'human_accepted': False, 'latency_seconds': time.monotonic()-start, 'duplicate_delivery_no_new_evidence': True, 'redesign_history_count': len(designs), 'verification': verifications})
    return {'mode': 'fixture', 'boundary': 'Real renderer/capture/PG checkpoints with explicitly injected CSS faults; not live designer regressions', 'scenarios': rows}


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1]), indent=2))
