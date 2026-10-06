import hashlib
import threading
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .config import settings

_transaction = threading.local()


@contextmanager
def connection():
    active = getattr(_transaction, "connection", None)
    if active is not None:
        yield active
        return
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        yield conn


@contextmanager
def locked_job(tenant, job_id):
    """Serialize job mutations; nested helpers share the request's transaction."""
    with connection() as conn:
        job = conn.execute(
            "SELECT * FROM audit_jobs WHERE id=%s AND tenant_id=%s FOR UPDATE", (job_id, tenant)
        ).fetchone()
        if not job:
            raise LookupError("Job not found")
        previous = getattr(_transaction, "connection", None)
        _transaction.connection = conn
        try:
            yield job
        finally:
            _transaction.connection = previous


def get_job(tenant, job_id):
    with connection() as conn:
        return conn.execute("SELECT * FROM audit_jobs WHERE id=%s AND tenant_id=%s", (job_id, tenant)).fetchone()


def update_job(tenant, job_id, status, data=None, error=None):
    with connection() as conn:
        conn.execute(
            "UPDATE audit_jobs SET status=%s,stage=%s,data=data||%s, error=%s,updated_at=now() WHERE id=%s AND tenant_id=%s AND (status NOT IN ('cancelled','completed') OR status=%s)",
            (status, status, Jsonb(data or {}), Jsonb(error) if error else None, job_id, tenant, status),
        )


def records(tenant, job_id, kind):
    with connection() as conn:
        rows = conn.execute(
            "SELECT data FROM records WHERE tenant_id=%s AND job_id=%s AND kind=%s ORDER BY created_at,id",
            (tenant, job_id, kind),
        ).fetchall()
        return [r["data"] for r in rows]


def save_records(tenant, job_id, kind, items):
    with connection() as conn:
        for item in items:
            item = dict(item, tenant_id=tenant)
            conn.execute(
                "INSERT INTO records(id,tenant_id,job_id,kind,data) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET data=excluded.data WHERE records.tenant_id=excluded.tenant_id",
                (job_id + ":" + item["id"], tenant, job_id, kind, Jsonb(item)),
            )


def index_business_facts(tenant, job_id, items):
    with connection() as conn:
        # Only human-approved facts enter this separately scoped retrieval collection.
        for item in items:
            if not item.get("approved"):
                continue
            identifier = f"{tenant}:{job_id}:fact:{item['id']}"
            conn.execute(
                "INSERT INTO knowledge_documents(id,tenant_id,job_id,collection,source,version,reuse_notes) VALUES(%s,%s,%s,'business_facts',%s,'capture-v1','User-approved submitted website fact; retain exact value') ON CONFLICT(id) DO UPDATE SET source=excluded.source",
                (identifier, tenant, job_id, item["source_url"]),
            )
            content = item["kind"] + ": " + item["value"]
            digest = hashlib.sha256(content.encode()).hexdigest()
            conn.execute(
                "INSERT INTO knowledge_chunks(id,tenant_id,document_id,content,content_hash) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET content=excluded.content,content_hash=excluded.content_hash,embedding=CASE WHEN knowledge_chunks.content_hash IS DISTINCT FROM excluded.content_hash THEN NULL ELSE knowledge_chunks.embedding END,embedding_model=CASE WHEN knowledge_chunks.content_hash IS DISTINCT FROM excluded.content_hash THEN NULL ELSE knowledge_chunks.embedding_model END",
                (identifier + ":chunk", tenant, identifier, content, digest),
            )
