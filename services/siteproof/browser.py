import asyncio
import threading
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi import Request as ConnectionRequest
from pydantic import BaseModel

from .capture import capture
from .config import settings
from .security import test_fixture_url, validate_url

app = FastAPI()
semaphore = threading.BoundedSemaphore(1)


@contextmanager
def slot():
    if not semaphore.acquire(timeout=1):
        raise HTTPException(429, "Browser concurrency limit reached")
    try:
        yield
    finally:
        semaphore.release()


class Request(BaseModel):
    url: str | None = None
    html: str | None = None


async def monitored_capture(connection, **kwargs):
    cancelled = threading.Event()

    def operate():
        with slot():
            return capture(cancel_event=cancelled, **kwargs)

    task = asyncio.create_task(asyncio.to_thread(operate))
    try:
        while not task.done():
            if await connection.is_disconnected():
                cancelled.set()
            await asyncio.sleep(0.25)
        return await task
    finally:
        cancelled.set()


@app.post("/capture")
async def run(request: Request, connection: ConnectionRequest, x_browser_key: str = Header("")):
    if x_browser_key != settings.browser_key:
        raise HTTPException(401, "Invalid service credential")
    if request.html is not None:
        if len(request.html) > 100000:
            raise HTTPException(413, "Preview too large")
        return await monitored_capture(connection, html=request.html)
    if request.url and test_fixture_url(request.url):
        return await monitored_capture(connection, url=validate_url(request.url))
    if settings.mode == "fixture" and request.url and request.url.startswith("https://fixture.siteproof.test/"):
        name = request.url.rstrip("/").split("/")[-1]
        if name not in (
            "clean",
            "overflow",
            "broken-contact",
            "missing-labels",
            "weak-navigation",
            "conflicting-facts",
            "prompt-injection",
            "timeout",
            "partial",
        ):
            raise HTTPException(422, "Unknown fixture")
        mapped = {
            "broken-contact": "broken_contact",
            "missing-labels": "missing_labels",
            "weak-navigation": "weak_navigation",
            "conflicting-facts": "conflicting_facts",
            "prompt-injection": "prompt_injection",
            "partial": "partial_capture",
        }.get(name, name)
        if name in ("timeout", "partial"):
            return {
                "evidence": [
                    {
                        "id": "capture-unavailable",
                        "kind": "unavailable",
                        "name": "capture",
                        "reason": "Deterministic fixture simulates timeout or partial capture; not live browser evidence",
                    }
                ],
                "screenshots": [],
                "facts": [],
                "partial": True,
            }
        path = Path("/app/evals/fixtures") / (mapped + ".html")
        if not path.exists():
            raise HTTPException(422, "Fixture not installed")
        return await monitored_capture(connection, html=path.read_text(), source_url=request.url)
    try:
        return await monitored_capture(connection, url=validate_url(request.url or ""))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
