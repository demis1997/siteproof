"""Real PostgreSQL ranking evaluation. Semantic arms require a real embedding provider."""
import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))
from retrieval_run import QUERIES
from siteproof.config import settings
from siteproof.contracts import Budget
from siteproof.db import connection
from siteproof.providers import LiveProvider
from siteproof.retrieval import cached_embedding, index_embeddings, retrieve


def run(tenant):
    observations = []
    configured = settings.mode == "live" and bool(settings.model_key) and all(x is not None for x in (
        settings.input_cost_per_million, settings.output_cost_per_million, settings.embedding_cost_per_million))
    model = LiveProvider() if configured else None
    budget = Budget(max_tokens=30000, max_tool_calls=30)
    if model:
        index_embeddings(tenant, model, budget)
    for query in QUERIES:
        # websearch_to_tsquery treats a sequence as AND; explicit OR tests coverage of these authored concepts.
        text = " OR ".join(query["query"].split())
        vector = cached_embedding(tenant, query["query"], model, budget) if model else None
        for strategy in ("keyword", "vector", "hybrid"):
            if strategy != "keyword" and vector is None:
                continue
            ranked = retrieve(tenant, text, embedding=vector, strategy=strategy, limit=4)
            ids = [r["id"].removeprefix(tenant + ":").removesuffix("-chunk") for r in ranked]
            relevant = set(query["relevant"])
            positions = [i for i, identifier in enumerate(ids, 1) if identifier in relevant]
            observations.append({"query_id": query["id"], "strategy": strategy, "source_ids": [r["id"] for r in ranked],
                                 "recall_at_1": len(relevant.intersection(ids[:1])) / len(relevant),
                                 "recall_at_3": len(relevant.intersection(ids[:3])) / len(relevant),
                                 "reciprocal_rank": 1 / min(positions) if positions else 0})
    metrics = {}
    for strategy in ("keyword", "vector", "hybrid"):
        rows = [r for r in observations if r["strategy"] == strategy]
        metrics[strategy] = {key: sum(r[key] for r in rows) / len(rows) for key in (
            "recall_at_1", "recall_at_3", "reciprocal_rank")} if rows else None
    with connection() as conn:
        corpus_size = conn.execute("SELECT count(*) AS count FROM knowledge_documents WHERE tenant_id=%s AND collection='guidance'", (tenant,)).fetchone()["count"]
    report = {"generated_at": datetime.now(UTC).isoformat(), "query_count": len(QUERIES), "corpus_size": corpus_size,
              "corpus_version": "guidance-v1", "embedding_model": settings.embedding_model if model else None,
              "embedding_dimensions": 1536 if model else None, "metrics": metrics, "observations": observations,
              "live_embedding_runs": model.embedding_runs if model else [],
              "limitations": ["Four engineer-reviewed authored relevance labels; no independent reviewer or held-out split.",
                               "Small corpus does not establish generalization or hybrid superiority.",
                               "Vector and hybrid arms BLOCKED without credentials and prices." if not model else
                               "Live model costs are configured estimates, not invoices."]}
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="local")
    run(parser.parse_args().tenant)
