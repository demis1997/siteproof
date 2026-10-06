"""Versioned real PostgreSQL benchmark. Paid arms are explicit, cached and bounded."""

import argparse
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))
from siteproof.config import settings
from siteproof.contracts import Budget
from siteproof.db import connection
from siteproof.live_limits import allocate
from siteproof.providers import LiveProvider
from siteproof.retrieval import cached_embedding, embedding_identity, index_embeddings, retrieve


def code_commit():
    if os.getenv("SITEPROOF_CODE_COMMIT"):
        return os.environ["SITEPROOF_CODE_COMMIT"]
    try:
        return (
            subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
            or None
        )
    except OSError:
        return None


def scores(ids, relevance):
    relevant = {identifier for identifier, grade in relevance.items() if grade > 0}
    if not relevant:
        return None
    ranks = [rank for rank, identifier in enumerate(ids, 1) if identifier in relevant]
    dcg = sum(
        (2 ** relevance.get(identifier, 0) - 1) / math.log2(rank + 1) for rank, identifier in enumerate(ids[:5], 1)
    )
    ideal = sum(
        (2**grade - 1) / math.log2(rank + 1)
        for rank, grade in enumerate(sorted(relevance.values(), reverse=True)[:5], 1)
    )
    return {
        "recall_at_3": len(relevant.intersection(ids[:3])) / len(relevant),
        "recall_at_5": len(relevant.intersection(ids[:5])) / len(relevant),
        "mrr": 1 / min(ranks) if ranks else 0,
        "ndcg_at_5": dcg / ideal if ideal else 0,
    }


def seed(tenant, corpus):
    if not tenant.startswith("retrieval_benchmark_"):
        raise ValueError("Use a separate retrieval_benchmark_ tenant; do not overwrite application guidance")
    with connection() as conn:
        conn.execute("INSERT INTO tenants(id,name) VALUES(%s,%s) ON CONFLICT DO NOTHING", (tenant, tenant))
        for document in corpus["documents"]:
            identifier = tenant + ":" + document["id"]
            conn.execute(
                "INSERT INTO knowledge_documents(id,tenant_id,collection,source,version,reuse_notes) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING",
                (identifier, tenant, "guidance", document["source"], document["version"], document["reuse_notes"]),
            )
            content = document["title"] + ". " + document["text"]
            conn.execute(
                "INSERT INTO knowledge_chunks(id,tenant_id,document_id,content,content_hash) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING",
                (identifier + "-chunk", tenant, identifier, content, hashlib.sha256(content.encode()).hexdigest()),
            )
        saved = conn.execute(
            "SELECT c.content_hash FROM knowledge_chunks c JOIN knowledge_documents d ON d.id=c.document_id WHERE c.tenant_id=%s AND d.collection=%s",
            (tenant, "guidance"),
        ).fetchall()
        expected = {hashlib.sha256((d["title"] + ". " + d["text"]).encode()).hexdigest() for d in corpus["documents"]}
        if {row["content_hash"] for row in saved} != expected:
            raise ValueError("Benchmark corpus changed: use a new version/tenant, not stale vectors")


def run(tenant="retrieval_benchmark_v1", live_embeddings=False, session="live-validation-v1"):
    corpus = json.loads((ROOT / "knowledge/retrieval-benchmark-v1.json").read_text())
    dataset = json.loads((ROOT / "evals/retrieval-dataset-v1.json").read_text())
    seed(tenant, corpus)
    model = None
    blocked = "BLOCKED: no real embedding calls requested/configured"
    budget = Budget(max_tokens=50000, max_tool_calls=60, max_seconds=600, max_cost=None)
    if live_embeddings:
        if settings.mode != "live":
            raise ValueError("Paid benchmark requires SITEPROOF_MODE=live")
        model = LiveProvider(require_chat=False)
        budget.max_cost = allocate(tenant, session, "retrieval")
        index_embeddings(tenant, model, budget, limit=100)
    observations = []
    vectors = {}
    started = time.monotonic()
    for query in dataset["queries"]:
        if model:
            vectors[query["id"]] = cached_embedding(tenant, query["query"], model, budget)
        text = " OR ".join(query["query"].split())
        for arm in ("keyword", "vector", "hybrid"):
            if arm != "keyword" and model is None:
                continue
            begin = time.monotonic()
            rows = retrieve(tenant, text, embedding=vectors.get(query["id"]), strategy=arm, limit=5, use_reranker=False)
            ids = [row["id"].removeprefix(tenant + ":").removesuffix("-chunk") for row in rows]
            observations.append(
                {
                    "query_id": query["id"],
                    "split": query["split"],
                    "arm": arm,
                    "ids": ids,
                    "similarities": {
                        row["id"].removeprefix(tenant + ":").removesuffix("-chunk"): row.get("similarity")
                        for row in rows
                    },
                    "latency_ms": (time.monotonic() - begin) * 1000,
                    "no_answer": query["no_answer"],
                    "metrics": scores(ids, query["relevance"]),
                }
            )
        if time.monotonic() - started > budget.max_seconds:
            raise ValueError("Evaluation time budget exhausted")
    metrics = {}
    no_answer = {}
    for split in ("dev", "held_out"):
        metrics[split], no_answer[split] = {}, {}
        for arm in ("keyword", "vector", "hybrid"):
            rows = [r for r in observations if r["split"] == split and r["arm"] == arm]
            answered = [r for r in rows if r["metrics"] is not None]
            absent = [r for r in rows if r["no_answer"]]
            metrics[split][arm] = (
                {
                    **{
                        k: statistics.mean(r["metrics"][k] for r in answered)
                        for k in ("recall_at_3", "recall_at_5", "mrr", "ndcg_at_5")
                    },
                    "answer_query_count": len(answered),
                    "latency_p50_ms": statistics.median(r["latency_ms"] for r in rows),
                    "latency_p95_ms": sorted(r["latency_ms"] for r in rows)[math.ceil(0.95 * len(rows)) - 1],
                }
                if rows
                else None
            )
            no_answer[split][arm] = (
                {
                    "query_count": len(absent),
                    "raw_empty_results": sum(not r["ids"] for r in absent),
                    "raw_false_answer_rate": statistics.mean(bool(r["ids"]) for r in absent),
                }
                if rows
                else None
            )
    # No threshold tuning: raw results are the baseline, and nearest-neighbor methods may answer irrelevant questions.
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "code_commit": code_commit(),
        "corpus_version": corpus["version"],
        "dataset_version": dataset["version"],
        "documents": len(corpus["documents"]),
        "queries": len(dataset["queries"]),
        "corpus_sha256": hashlib.sha256(json.dumps(corpus, sort_keys=True).encode()).hexdigest(),
        "dataset_sha256": hashlib.sha256(json.dumps(dataset, sort_keys=True).encode()).hexdigest(),
        "embedding_identity": embedding_identity() if model else None,
        "provider_endpoint_configured": bool(settings.embedding_url or settings.model_url),
        "metrics": metrics,
        "no_answer": no_answer,
        "observations": observations,
        "embedding_runs": model.embedding_runs if model else [],
        "embedding_usage": {
            "calls": len(model.embedding_runs) if model else 0,
            "tokens": budget.tokens,
            "cost_usd": budget.cost,
            "cost_known": model is not None and settings.embedding_cost_per_million is not None,
        },
        "semantic_status": "PASS: actual provider embeddings used" if model else blocked,
        "monetary_ceiling": "configured USD allocations against EUR5"
        if model and budget.max_cost is not None
        else "UNVERIFIED: missing prices/FX or no paid run",
        "tuning": "No tuning performed. Frozen raw retrieval baseline; reranking disabled.",
        "limitations": [
            "Coding-agent-authored relevance labels need independent human review.",
            dataset["split_policy"],
            "Raw nearest-neighbor/RRF has no calibrated abstention guarantee; no-answer failures reported separately.",
            "No semantic ranking claim without actual provider embeddings.",
        ],
    }
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="retrieval_benchmark_v1")
    parser.add_argument("--live-embeddings", action="store_true")
    parser.add_argument("--session", default="live-validation-v1")
    args = parser.parse_args()
    run(args.tenant, args.live_embeddings, args.session)
