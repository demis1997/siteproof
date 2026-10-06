"""Actual PostgreSQL allocation gates; no paid requests or live model claims."""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services"))
from siteproof.config import settings
from siteproof.live_limits import allocate


def main():
    session = "guard-test-" + str(uuid.uuid4())
    settings.input_cost_per_million = 1
    settings.output_cost_per_million = 1
    settings.embedding_cost_per_million = 1
    settings.usd_per_eur = 0.8
    for _ in range(3):
        assert allocate("integration", session, "audit") == 1
    assert allocate("retrieval_benchmark_v1", session, "retrieval") == 1
    for tenant, kind in [("integration", "audit"), ("retrieval_benchmark_v1", "retrieval")]:
        try:
            allocate(tenant, session, kind)
        except ValueError:
            pass
        else:
            raise AssertionError("Allocation ceiling not enforced")
    # Separate named simulated session reaches the euro ceiling before the audit-count ceiling.
    session = "money-guard-test-" + str(uuid.uuid4())
    settings.usd_per_eur = 0.2
    assert allocate("integration", session, "audit") == 1
    try:
        allocate("retrieval_benchmark_v1", session, "retrieval")
    except ValueError as exc:
        assert "EUR5" in str(exc)
    else:
        raise AssertionError("Shared monetary ceiling ignored")
    print(
        "PASS: actual PostgreSQL shared allocations; max three audits, one retrieval run and EUR5 gate with simulated prices/FX. No paid calls."
    )


if __name__ == "__main__":
    main()
