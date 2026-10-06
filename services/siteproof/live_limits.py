"""Conservative shared validation allocations. No exactly-once remote execution claim."""

from psycopg.types.json import Jsonb

from .config import settings
from .db import connection


def allocate(tenant, session, kind, budget_usd=1.0):
    if kind not in ("audit", "retrieval"):
        raise ValueError("Unknown validation allocation")
    requester = tenant
    tenant = "siteproof_validation_budget"
    with connection() as conn:
        conn.execute("INSERT INTO tenants(id,name) VALUES(%s,%s) ON CONFLICT DO NOTHING", (tenant, tenant))
        conn.execute(
            "INSERT INTO live_validation_sessions(tenant_id,id,data) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
            (tenant, session, Jsonb({"audit_count": 0, "retrieval_count": 0, "allocated_usd": 0})),
        )
        row = conn.execute(
            "SELECT data FROM live_validation_sessions WHERE tenant_id=%s AND id=%s FOR UPDATE", (tenant, session)
        ).fetchone()["data"]
        if kind == "audit" and row["audit_count"] >= 3:
            raise ValueError("Three-audit validation ceiling reached")
        if kind == "retrieval" and row["retrieval_count"] >= 1:
            raise ValueError(
                "Retrieval allocation already used; inspect existing results instead of repeating paid runs"
            )
        priced = settings.prices_known()
        if priced:
            if settings.usd_per_eur is None:
                raise ValueError("Set SITEPROOF_USD_PER_EUR to enforce the EUR ceiling with USD prices")
            if row["allocated_usd"] + budget_usd > 5 * settings.usd_per_eur:
                raise ValueError("EUR5 shared validation ceiling exceeded")
        row.setdefault("requesters", []).append({"tenant": requester, "kind": kind})
        row[kind + "_count"] += 1
        # Retain the entire allocation even on uncertain failures; never refund automatically.
        row["allocated_usd"] += budget_usd
        row["monetary_ceiling_verified"] = priced
        conn.execute(
            "UPDATE live_validation_sessions SET data=%s WHERE tenant_id=%s AND id=%s", (Jsonb(row), tenant, session)
        )
        return budget_usd if priced else None
