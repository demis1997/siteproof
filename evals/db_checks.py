"""Integration assertions on real PostgreSQL; roll back synthetic test vectors."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services"))
from siteproof import db
from siteproof.journal import once
from siteproof.retrieval import embedding_identity, retrieve


def run(tenant, job_id):
    with db.connection() as conn:
        # Share the connection so actual ranking functions see uncommitted vectors.
        previous = getattr(db._transaction, "connection", None)
        db._transaction.connection = conn
        try:
            vector = [1.0] + [0.0] * 1535
            conn.execute("UPDATE knowledge_chunks SET embedding=%s::vector,embedding_model=%s WHERE tenant_id=%s",
                         (str(vector), embedding_identity(), tenant))
            rows = retrieve(tenant, "label OR form", embedding=vector, strategy="hybrid")
            assert rows and all(row["id"].startswith(tenant + ":") for row in rows)
            assert retrieve(tenant, "no-match-word", embedding=vector, strategy="vector")
            assert not retrieve("nonexistent-tenant", "label OR form", embedding=vector)
            conn.execute("UPDATE knowledge_chunks SET embedding_model='wrong-model' WHERE tenant_id=%s", (tenant,))
            assert not retrieve(tenant, "no-match-word", embedding=vector, strategy="vector")
        finally:
            db._transaction.connection = previous
            conn.rollback()
    assert once(tenant, job_id, "integration-success", lambda: {"saved": True}) == {"saved": True}
    def forbidden():
        raise AssertionError("Repeated persisted operation")
    assert once(tenant, job_id, "integration-success", forbidden, paid=True) == {"saved": True}
    with db.connection() as conn:
        conn.execute("INSERT INTO workflow_steps(tenant_id,job_id,step,status) VALUES(%s,%s,'integration-uncertain','started')",
                     (tenant, job_id))
    try:
        once(tenant, job_id, "integration-uncertain", forbidden, paid=True)
    except ValueError as exc:
        assert "Uncertain" in str(exc)
    else:
        raise AssertionError("Uncertain paid call was replayed")
    print("PASS: real PostgreSQL vector/FTS/RRF, tenant/model filters, durable replay guard. Synthetic vectors test mechanics only.")


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
