import json
import logging
import random
import time

import httpx
import psycopg
import redis
from botocore.exceptions import EndpointConnectionError, ReadTimeoutError

from .config import settings
from .db import connection, get_job, update_job
from .workflow import run_job

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def dispatch_outbox(queue):
    # PostgreSQL row lock plus marking after LPUSH provides at-least-once delivery.
    # A crash between LPUSH and commit duplicates a task; checkpoint stages remain idempotent.
    with connection() as conn:
        tasks = conn.execute(
            "SELECT id,payload FROM task_outbox WHERE dispatched_at IS NULL ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 100"
        ).fetchall()
        for task in tasks:
            queue.lpush("siteproof:queue", json.dumps(task["payload"]))
            conn.execute("UPDATE task_outbox SET dispatched_at=now() WHERE id=%s", (task["id"],))


def is_retryable(exc):
    return isinstance(
        exc,
        (
            httpx.TransportError,
            TimeoutError,
            ConnectionError,
            EndpointConnectionError,
            ReadTimeoutError,
            psycopg.OperationalError,
            redis.exceptions.RedisError,
        ),
    ) or (
        isinstance(exc, httpx.HTTPStatusError) and (exc.response.status_code >= 500 or exc.response.status_code == 429)
    )


def main():
    queue = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    # Requeue jobs interrupted during worker termination using durable processing list.
    while item := queue.rpoplpush("siteproof:processing", "siteproof:queue"):
        task = json.loads(item)
        # Single-host worker owns the processing list; its predecessor is no longer running.
        queue.delete("siteproof:domain:" + task.get("domain", "fixture"), "siteproof:tenant:" + task["tenant"])
        logger.info(json.dumps({"event": "recover", "job_id": task["job_id"]}))
    while True:
        try:
            dispatch_outbox(queue)
        except (psycopg.OperationalError, redis.exceptions.RedisError):
            logger.exception("Outbox dependencies unavailable")
            time.sleep(2)
            continue
        raw = queue.brpoplpush("siteproof:queue", "siteproof:processing", timeout=5)
        if not raw:
            continue
        task = json.loads(raw)
        tenant = task["tenant"]
        job_id = task["job_id"]
        domain = task.get("domain", "fixture")
        lock = queue.lock("siteproof:domain:" + domain, timeout=600)
        tenant_lock = queue.lock("siteproof:tenant:" + tenant, timeout=600)
        if not lock.acquire(blocking=False):
            queue.lrem("siteproof:processing", 1, raw)
            queue.lpush("siteproof:queue", raw)
            time.sleep(1)
            continue
        try:
            if not tenant_lock.acquire(blocking=False):
                queue.lpush("siteproof:queue", raw)
                continue
            job = get_job(tenant, job_id)
            stale = (
                task.get("action") == "redesign" and task.get("revision") != job["data"].get("redesign_revision", 0)
                if job
                else True
            )
            if job and job["status"] not in ("cancelled", "completed") and not stale:
                run_job(tenant, job_id, task.get("action", "audit"))
            logger.info(json.dumps({"event": "task_complete", "job_id": job_id, "tenant_id": tenant}))
        except Exception as exc:
            retryable = is_retryable(exc)
            attempt = task.get("attempt", 0) + 1
            if retryable and attempt <= 3:
                task["attempt"] = attempt
                browser_busy = isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429
                time.sleep(30 if browser_busy else min(2**attempt + random.random(), 10))
                queue.lpush("siteproof:queue", json.dumps(task))
            else:
                limited = isinstance(exc, ValueError) and ("budget" in str(exc).lower() or "limit" in str(exc).lower())
                update_job(
                    tenant,
                    job_id,
                    "needs_review" if limited else "failed",
                    error={
                        "code": type(exc).__name__,
                        "message": str(exc)[:500],
                        "retryable": retryable,
                        "attempt": attempt,
                    },
                )
                queue.lpush("siteproof:dead-letter", raw)
            logger.exception(json.dumps({"event": "task_failed", "job_id": job_id, "attempt": attempt}))
        finally:
            queue.lrem("siteproof:processing", 1, raw)
            if tenant_lock.owned():
                tenant_lock.release()
            lock.release()


if __name__ == "__main__":
    main()
