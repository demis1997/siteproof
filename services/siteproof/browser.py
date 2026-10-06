import threading
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from .capture import capture
from .config import settings
from .security import validate_url

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


@app.post("/capture")
def run(request: Request, x_browser_key: str = Header("")):
    if x_browser_key != settings.browser_key:
        raise HTTPException(401, "Invalid service credential")
    if request.html is not None:
        if len(request.html) > 100000:
            raise HTTPException(413, "Preview too large")
        with slot():
            return capture(html=request.html)
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
        with slot():
            return capture(html=path.read_text(), source_url=request.url)
    try:
        with slot():
            return capture(url=validate_url(request.url or ""))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
