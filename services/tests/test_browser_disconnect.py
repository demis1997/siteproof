import asyncio
import time

from siteproof import browser


def test_disconnected_worker_cancels_capture_and_releases_slot(monkeypatch):
    observations=[]

    def capture(*, cancel_event, **kwargs):
        while not cancel_event.is_set():
            time.sleep(0.01)
        observations.append('cancelled')
        return {'partial':True}

    class Connection:
        async def is_disconnected(self):
            return True

    monkeypatch.setattr(browser,'capture',capture)
    result=asyncio.run(browser.monitored_capture(Connection(),html='controlled'))
    assert result['partial'] and observations==['cancelled']
    assert browser.semaphore.acquire(blocking=False)
    browser.semaphore.release()
