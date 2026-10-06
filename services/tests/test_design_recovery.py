import copy
import time

from siteproof import workflow
from siteproof.config import settings
from siteproof.contracts import Budget


def test_designer_success_replay_is_durable_and_not_double_charged(monkeypatch):
    monkeypatch.setattr(settings, 'mode', 'live')
    monkeypatch.setattr(workflow.db, 'get_job', lambda *args: {'status': 'designing'})
    monkeypatch.setattr(workflow.db, 'update_job', lambda *args, **kwargs: None)
    runs = {}
    monkeypatch.setattr(workflow.db, 'save_records', lambda t,j,k,items: runs.update({i['id']:i for i in items}))
    monkeypatch.setattr(workflow, 'render_spec', lambda state: None)
    stored = {}
    calls = []

    def once(t,j,step,operation,**kwargs):
        if step not in stored:
            stored[step] = operation()
        return copy.deepcopy(stored[step])

    class Provider:
        def design(self,seed,facts,findings,budget,**kwargs):
            calls.append(kwargs)
            seed.fixture = False
            return seed, {'tokens': 30, 'cost': 0.001, 'model': 'simulated', 'fixture':False}

    monkeypatch.setattr(workflow, 'once', once)
    monkeypatch.setattr(workflow, 'provider', Provider)
    state = {'tenant':'t','job_id':'j','action':'redesign','revision':1,'started':time.time(),'evidence':[{'kind':'dom','data':{'title':'Source','headings':[{'text':'Source'}]}}],'facts':[],'findings':[],'guidance':[{'id':'g'}],'images':[],'budget':Budget().model_dump()}
    workflow.designer(state)
    workflow.designer(state)
    assert len(calls)==1 and len(runs)==1
    assert calls[0]['guidance']==[{'id':'g'}]
    assert state['budget']['tokens']==30 and state['budget']['cost']==0.001


def test_restoring_journal_never_lowers_consumed_usage():
    state={'budget':Budget(tokens=100, tool_calls=8, elapsed_seconds=60, cost=0.02).model_dump()}
    workflow.restore_usage(state,Budget(tokens=50, tool_calls=4, elapsed_seconds=30, cost=0.01).model_dump())
    assert state['budget']['tokens']==100 and state['budget']['tool_calls']==8
    assert state['budget']['elapsed_seconds']==60 and state['budget']['cost']==0.02


def test_live_provider_http_rejections_do_not_retry():
    import httpx
    from siteproof.worker import is_retryable
    for code in [401,429,500]:
        request=httpx.Request('POST','https://api.openai.com/v1/embeddings')
        exc=httpx.HTTPStatusError('sanitised',request=request,response=httpx.Response(code,request=request))
        assert not is_retryable(exc)


def test_resume_keeps_pending_verifier(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from siteproof import workflow

    calls=[]
    graph=SimpleNamespace(
        get_state=lambda config: SimpleNamespace(values={'html':'trusted'},next=('verifier',)),
        update_state=lambda config, values, **kwargs: calls.append(kwargs),
        invoke=lambda initial, config: calls.append({'initial':initial}),
    )
    monkeypatch.setattr(workflow.db,'get_job',lambda *args:{'status':'verifying','stage':'verifying','data':{'redesign_revision':1}})
    monkeypatch.setattr(workflow.PostgresSaver,'from_conn_string',lambda *args:nullcontext(SimpleNamespace(setup=lambda:None)))
    monkeypatch.setattr(workflow,'build_graph',lambda saver:graph)
    workflow.run_job('t','j','redesign')
    assert calls==[{'as_node':'designer'},{'initial':None}]
