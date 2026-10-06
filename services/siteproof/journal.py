"""Durable Auditor substeps. Uncertain paid calls require review, never automatic replay."""
from psycopg.types.json import Jsonb

from .db import connection


def once(tenant, job_id, step, operation, *, paid=False):
    with connection() as conn:
        row = conn.execute(
            "SELECT status,result FROM workflow_steps WHERE tenant_id=%s AND job_id=%s AND step=%s",
            (tenant, job_id, step),
        ).fetchone()
        if row and row["status"] == "succeeded":
            return row["result"]
        if row and paid and row["status"] == "started":
            raise ValueError("Uncertain in-flight model call; automatic replay limit requires human review")
        conn.execute(
            "INSERT INTO workflow_steps(tenant_id,job_id,step,status) VALUES(%s,%s,%s,'started') "
            "ON CONFLICT(tenant_id,job_id,step) DO UPDATE SET status='started'",
            (tenant, job_id, step),
        )
    result = operation()
    with connection() as conn:
        conn.execute(
            "UPDATE workflow_steps SET status='succeeded',result=%s,updated_at=now() "
            "WHERE tenant_id=%s AND job_id=%s AND step=%s",
            (Jsonb(result), tenant, job_id, step),
        )
    return result
