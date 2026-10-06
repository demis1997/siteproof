"""Tenant/collection filtering precedes both ranking branches; sources stay stable."""

import hashlib
import math

import httpx

from .config import settings
from .db import connection


def reciprocal_rank_fusion(rankings, k=60):
    scores = {}
    for ranking in rankings:
        seen = set()
        for rank, item in enumerate(ranking, 1):
            if item["id"] not in seen:
                scores[item["id"]] = scores.get(item["id"], 0) + 1 / (k + rank)
                seen.add(item["id"])
    return sorted(scores, key=lambda identifier: (-scores[identifier], identifier))


def embedding_identity():
    # Prevent reuse across model revisions or different OpenAI-compatible provider endpoints.
    endpoint = hashlib.sha256(settings.model_url.rstrip("/").encode()).hexdigest()[:12]
    return f"{settings.embedding_model}@{settings.embedding_version}:1536:{endpoint}"


def cached_embedding(tenant, text, model_provider, budget=None):
    digest = hashlib.sha256(text.encode()).hexdigest()
    with connection() as conn:
        cached = conn.execute(
            "SELECT embedding::text AS embedding FROM embedding_cache "
            "WHERE tenant_id=%s AND content_hash=%s AND model=%s",
            (tenant, digest, embedding_identity()),
        ).fetchone()
    if cached:
        import json

        return json.loads(cached["embedding"])
    vector = model_provider.embeddings([text], budget=budget)[0]
    if len(vector) != 1536 or not all(math.isfinite(x) for x in vector):
        raise ValueError("Invalid embedding vector")
    with connection() as conn:
        conn.execute(
            "INSERT INTO embedding_cache(tenant_id,content_hash,model,embedding) "
            "VALUES(%s,%s,%s,%s::vector) ON CONFLICT DO NOTHING",
            (tenant, digest, embedding_identity(), str(vector)),
        )
    return vector


def index_embeddings(tenant, model_provider, budget=None, collection="guidance", limit=20):
    """Bounded content/model-aware indexing; stale vector models cannot be ranked."""
    with connection() as conn:
        chunks = conn.execute(
            "SELECT c.id,c.content FROM knowledge_chunks c JOIN knowledge_documents d "
            "ON d.id=c.document_id AND d.tenant_id=c.tenant_id "
            "WHERE c.tenant_id=%s AND d.collection=%s "
            "AND (c.embedding IS NULL OR c.embedding_model IS DISTINCT FROM %s) ORDER BY c.id LIMIT %s",
            (tenant, collection, embedding_identity(), limit),
        ).fetchall()
    for chunk in chunks:
        vector = cached_embedding(tenant, chunk["content"], model_provider, budget)
        with connection() as conn:
            conn.execute(
                "UPDATE knowledge_chunks SET embedding=%s::vector,embedding_model=%s WHERE tenant_id=%s AND id=%s",
                (str(vector), embedding_identity(), tenant, chunk["id"]),
            )


def rerank(query, chunks):
    """Optional Hugging Face TEI /rerank adapter; fail explicitly if configured but unavailable."""
    if not settings.rerank_url or not chunks:
        return chunks
    headers = {"Authorization": "Bearer " + settings.rerank_key} if settings.rerank_key else {}
    with httpx.Client(timeout=10) as client:
        response = client.post(
            settings.rerank_url.rstrip("/") + "/rerank",
            headers=headers,
            json={"query": query, "texts": [c["content"] for c in chunks], "raw_scores": False},
        )
        response.raise_for_status()
        ranking = response.json()
    indices = [r["index"] for r in ranking]
    if sorted(indices) != list(range(len(chunks))) or any(not math.isfinite(r["score"]) for r in ranking):
        raise ValueError("Reranker returned invalid ranking indices or scores")
    return [
        dict(chunks[r["index"]], rerank_score=r["score"], rerank_model=settings.rerank_model)
        for r in sorted(ranking, key=lambda r: (-r["score"], r["index"]))
    ]


def retrieve(tenant, query, embedding=None, limit=5, collection="guidance", job_id=None, strategy="hybrid"):
    if strategy not in ("keyword", "vector", "hybrid"):
        raise ValueError("Unknown retrieval strategy")
    if collection not in ("guidance", "business_facts"):
        raise ValueError("Unknown retrieval collection")
    if collection == "business_facts" and not job_id:
        raise ValueError("Business facts retrieval requires homepage job scope")
    scope = "c.tenant_id=%s AND d.collection=%s"
    args = [tenant, collection]
    if job_id:
        scope += " AND d.job_id=%s"
        args.append(job_id)
    base = (
        "SELECT c.id,c.content,c.content_hash,d.source,d.version,d.reuse_notes FROM knowledge_chunks c "
        "JOIN knowledge_documents d ON d.id=c.document_id AND d.tenant_id=c.tenant_id WHERE " + scope
    )
    with connection() as conn:
        lexical = conn.execute(
            base + " AND c.search @@ websearch_to_tsquery('english',%s) "
            "ORDER BY ts_rank(c.search,websearch_to_tsquery('english',%s)) DESC,c.id LIMIT 20",
            (*args, query, query),
        ).fetchall()
        semantic = []
        if embedding is not None:
            if len(embedding) != 1536 or not all(math.isfinite(x) for x in embedding):
                raise ValueError("Invalid retrieval embedding")
            semantic = conn.execute(
                base + " AND c.embedding IS NOT NULL AND c.embedding_model=%s "
                "ORDER BY c.embedding <=> %s::vector,c.id LIMIT 20",
                (*args, embedding_identity(), str(embedding)),
            ).fetchall()
    if strategy == "keyword":
        semantic = []
    elif strategy == "vector":
        lexical = []
    items = {row["id"]: row for row in lexical + semantic}
    seen, fused = set(), []
    for identifier in reciprocal_rank_fusion([lexical, semantic]):
        row = items[identifier]
        if row["content_hash"] not in seen:
            seen.add(row["content_hash"])
            fused.append(row)
    return rerank(query, fused)[:limit]
