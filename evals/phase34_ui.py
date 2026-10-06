"""Trusted UI E2E for actual fixture preview/verification artifacts."""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main(identifier):
    with sync_playwright() as p:
        browser=p.chromium.launch()
        context=browser.new_context(viewport={'width':1440,'height':1000})
        page=context.new_page()
        page.goto('http://web:3000')
        page.get_by_label('Tenant access key').fill('integration-key')
        page.get_by_role('button',name='Connect workspace').click()
        page.get_by_role('heading',name='Start an audit',exact=True).wait_for(timeout=20000)
        # Only select the real job; no fixture result is inserted into UI state.
        page.locator('button.job').filter(has_text=identifier[:8]).count()
        button=page.locator(f'button[data-job-id="{identifier}"]')
        if button.count():
            button.click()
        else:
            response=page.request.get('http://web:3000/api/jobs')
            assert response.ok
            target=next(j for j in response.json()['jobs'] if j['id']==identifier)
            page.locator('.job').filter(has_text=target['submitted_url']).filter(has_text='completed').first.click()
        page.get_by_role('tab',name='Comparison',exact=True).click()
        page.wait_for_function("()=>{const imgs=[...document.querySelectorAll('.compare-grid img')];return imgs.length===4&&imgs.every(i=>i.complete&&i.naturalWidth>0)}",timeout=20000)
        assert page.locator('.fixture').first.is_visible()
        page.screenshot(path='/tmp/phase34-comparison.png',full_page=True)
        page.get_by_role('tab',name='Verification',exact=True).click()
        page.get_by_role('heading',name='Repair history',exact=True).wait_for()
        assert page.get_by_role('button',name='Accept private preview',exact=True).is_disabled()
        page.screenshot(path='/tmp/phase34-verification.png',full_page=True)
        preview=context.new_page()
        preview.goto('http://web:3000/preview/'+identifier)
        frame=preview.frame_locator('iframe')
        frame.get_by_role('heading',level=1).wait_for()
        assert frame.locator('script').count()==0
        assert frame.get_by_role('link',name='Get in touch ↗').get_attribute('href').startswith(('tel:','mailto:'))
        assert frame.locator('meta[name="robots"]').get_attribute('content')=='noindex,nofollow'
        report={'job_id':identifier,'mode':'fixture','status':'PASS','checks':['real four-image before/after comparison','persistent fixture label','repair-history view','accepted job cannot be accepted again','authenticated noindex document','script-free iframe','functional contact scheme'],'human_quality_review':'pending'}
        Path('/tmp/phase34-ui.json').write_text(json.dumps(report,indent=2))
        browser.close()


if __name__=='__main__':
    main(sys.argv[1])
