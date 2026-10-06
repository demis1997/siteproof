"""Verify deletion only for the integration harness's explicitly marked job."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services"))
from siteproof.config import settings
from siteproof.db import connection
from siteproof.storage import client


def run(tenant, job_id):
    if tenant != "integration":
        raise ValueError("Only the isolated integration tenant is permitted")
    with connection() as conn:
        for table in ("audit_jobs", "records", "workflow_steps", "task_outbox"):
            key = "id" if table == "audit_jobs" else "job_id"
            count = conn.execute(f"SELECT count(*) AS count FROM {table} WHERE tenant_id=%s AND {key}=%s", (tenant, job_id)).fetchone()["count"]
            assert count == 0, table
        assert conn.execute("SELECT count(*) AS count FROM checkpoints WHERE starts_with(thread_id,%s)",
                            (f"{tenant}:{job_id}:",)).fetchone()["count"] == 0
    assert client().list_objects_v2(Bucket=settings.s3_bucket, Prefix=f"{tenant}/{job_id}/")["KeyCount"] == 0
    print("PASS: tenant-scoped PostgreSQL rows, checkpoints and actual S3 objects deleted")


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
