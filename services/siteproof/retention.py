"""Single-host terminal-job deletion. Storage failures retain DB references for retry."""

import argparse
from contextlib import ExitStack
from urllib.parse import urlsplit

import redis
from botocore.exceptions import ClientError
from langgraph.checkpoint.postgres import PostgresSaver

from . import db
from .config import settings
from .storage import client

TERMINAL = {"completed", "failed", "cancelled", "needs_review"}


def delete_job(tenant, job_id):
    job = db.get_job(tenant, job_id)
    if not job:
        raise LookupError("Job not found")
    if job["status"] not in TERMINAL:
        raise ValueError("Cancel an active job before deletion")
    queue = redis.Redis.from_url(settings.redis_url)
    with ExitStack() as stack:
        for key in (
            "siteproof:tenant:" + tenant,
            "siteproof:domain:" + (urlsplit(job["canonical_url"]).hostname or "fixture"),
        ):
            lock = queue.lock(key, timeout=120)
            if not lock.acquire(blocking=False):
                raise ValueError("Job worker is active; retry deletion after cancellation completes")
            stack.callback(lock.release)
        # Recheck while holding the same locks as the single-host worker.
        job = db.get_job(tenant, job_id)
        if not job or job["status"] not in TERMINAL:
            raise ValueError("Job changed while deletion was requested")
        if job["status"] == "needs_review":
            db.update_job(tenant, job_id, "cancelled")
        s3 = client()
        try:
            pages = s3.get_paginator("list_objects_v2").paginate(
                Bucket=settings.s3_bucket, Prefix=f"{tenant}/{job_id}/"
            )
            for page in pages:
                objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
                if objects:
                    result = s3.delete_objects(Bucket=settings.s3_bucket, Delete={"Objects": objects, "Quiet": True})
                    if result.get("Errors"):
                        raise RuntimeError("Artifact deletion failed; retained database records for retry")
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "NoSuchBucket":
                raise
        with db.connection() as conn:
            exists = conn.execute("SELECT to_regclass('checkpoints') AS table_name").fetchone()
            threads = (
                conn.execute(
                    "SELECT DISTINCT thread_id FROM checkpoints WHERE starts_with(thread_id,%s)",
                    (f"{tenant}:{job_id}:",),
                ).fetchall()
                if exists["table_name"]
                else []
            )
        if threads:
            with PostgresSaver.from_conn_string(settings.database_url) as saver:
                for thread in threads:
                    saver.delete_thread(thread["thread_id"])
        with db.connection() as conn:
            conn.execute(
                "DELETE FROM knowledge_chunks WHERE tenant_id=%s AND document_id IN "
                "(SELECT id FROM knowledge_documents WHERE tenant_id=%s AND job_id=%s)",
                (tenant, tenant, job_id),
            )
            conn.execute("DELETE FROM knowledge_documents WHERE tenant_id=%s AND job_id=%s", (tenant, job_id))
            # Conservative privacy choice: clear this tenant cache, including detached fact vectors.
            conn.execute("DELETE FROM embedding_cache WHERE tenant_id=%s", (tenant,))
            conn.execute("DELETE FROM audit_jobs WHERE tenant_id=%s AND id=%s", (tenant, job_id))
    return {"status": "deleted", "job_id": job_id}


def main():
    parser = argparse.ArgumentParser(description="Delete terminal jobs older than the configured retention period")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--apply", action="store_true", help="Without this flag, only list candidates")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be positive")
    with db.connection() as conn:
        jobs = conn.execute(
            "SELECT id,tenant_id FROM audit_jobs WHERE status IN ('completed','failed','cancelled','needs_review') "
            "AND updated_at < now() - make_interval(days => %s) ORDER BY updated_at LIMIT 100",
            (args.days,),
        ).fetchall()
    for job in jobs:
        if args.apply:
            print(delete_job(job["tenant_id"], job["id"]))
        else:
            print({"job_id": job["id"], "tenant_id": job["tenant_id"], "would_delete": True})


if __name__ == "__main__":
    main()
