from contextlib import contextmanager

import httpx
import pytest
from siteproof import db, worker
from siteproof.browser import semaphore, slot


def test_outbox_marks_only_after_successful_enqueue(monkeypatch):
    statements = []

    class Result:
        def fetchall(self):
            return [{"id": 1, "payload": {"tenant": "local", "job_id": "j"}}]

    class Conn:
        def execute(self, sql, args=()):
            statements.append(sql)
            return Result()

    @contextmanager
    def connection():
        yield Conn()

    class BrokenQueue:
        def lpush(self, *args):
            raise ConnectionError("redis unavailable")

    monkeypatch.setattr(worker, "connection", connection)
    with pytest.raises(ConnectionError):
        worker.dispatch_outbox(BrokenQueue())
    assert not any(sql.startswith("UPDATE task_outbox") for sql in statements)


def test_cancelled_completed_terminal_guard(monkeypatch):
    observed = []

    class Conn:
        def execute(self, sql, args):
            observed.append((sql, args))

    @contextmanager
    def connection():
        yield Conn()

    monkeypatch.setattr(db, "connection", connection)
    db.update_job("t", "j", "auditing")
    assert "status NOT IN ('cancelled','completed')" in observed[0][0]
    assert observed[0][1][-1] == "auditing"


def test_transient_http_retries():
    request = httpx.Request("GET", "https://example.com")
    assert worker.is_retryable(httpx.HTTPStatusError("busy", request=request, response=httpx.Response(429)))
    assert worker.is_retryable(httpx.HTTPStatusError("down", request=request, response=httpx.Response(503)))
    assert not worker.is_retryable(httpx.HTTPStatusError("bad", request=request, response=httpx.Response(422)))


def test_browser_semaphore_released_after_failure():
    with pytest.raises(ValueError), slot():
        raise ValueError("capture failure")
    assert semaphore.acquire(blocking=False)
    semaphore.release()
