from contextlib import nullcontext
from types import SimpleNamespace

from siteproof import capture as module


def test_failed_navigation_does_not_repeat_lighthouse(monkeypatch):
    def failed(*args,**kwargs):
        raise TimeoutError('controlled navigation timeout')

    page=SimpleNamespace(goto=failed)
    context=SimpleNamespace(route=lambda *args:None,route_web_socket=lambda *args:None,on=lambda *args:None,new_page=lambda:page,close=lambda:None)
    browser=SimpleNamespace(new_context=lambda **kwargs:context,close=lambda:None)
    runtime=SimpleNamespace(chromium=SimpleNamespace(launch=lambda **kwargs:browser,executable_path='/controlled/chrome'))
    monkeypatch.setattr(module,'sync_playwright',lambda:nullcontext(runtime))
    monkeypatch.setattr(module,'lighthouse_evidence',lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError('Unavailable viewport must not run Lighthouse')))
    result=module.capture(url='https://public.example')
    assert result['partial'] and not result['screenshots']
    missing=[e for e in result['evidence'] if e.get('name')=='lighthouse']
    assert len(missing)==2 and all(e['kind']=='unavailable' and e['sample_count']==0 for e in missing)
