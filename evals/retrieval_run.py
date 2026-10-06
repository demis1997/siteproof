"""Small independent local lexical/RRF evaluation, not SQL/vector integration."""

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services"))
from siteproof.retrieval import reciprocal_rank_fusion

QUERIES = [
    {"id": "labels", "query": "form control label descriptive input", "relevant": ["wai-labels-v1"]},
    {"id": "responsive", "query": "layout browser complexity calculations", "relevant": ["webdev-layout-v1"]},
    {"id": "facts", "query": "phone email hours prices testimonials credentials", "relevant": ["local-contact-v1"]},
    {
        "id": "uncertainty",
        "query": "conversion hypothesis unavailable unverified automated",
        "relevant": ["local-verification-v1"],
    },
]


def tokens(text):
    return set(re.findall(r"[a-z]+", text.lower()))


def rank(query, documents, field):
    terms = tokens(query)
    scored = [(len(terms & tokens(doc[field])), doc) for doc in documents]
    return [doc for score, doc in sorted(scored, key=lambda pair: (-pair[0], pair[1]["id"])) if score > 0]


def run(output):
    documents = json.loads((ROOT / "knowledge/guidance.json").read_text())["documents"]
    observations = []
    for item in QUERIES:
        body = rank(item["query"], documents, "text")
        title = rank(item["query"], documents, "title")
        ranking = reciprocal_rank_fusion([body, title])
        relevant = set(item["relevant"])
        positions = [i for i, value in enumerate(ranking, 1) if value in relevant]
        observations.append(
            {
                **item,
                "ranking": ranking,
                "recall_at_1": len(relevant & set(ranking[:1])) / len(relevant),
                "recall_at_3": len(relevant & set(ranking[:3])) / len(relevant),
                "reciprocal_rank": 1 / min(positions) if positions else 0,
            }
        )
    original = reciprocal_rank_fusion([[{"id": "a"}, {"id": "b"}], [{"id": "b"}]])
    duplicated = reciprocal_rank_fusion([[{"id": "a"}, {"id": "b"}, {"id": "b"}], [{"id": "b"}]])
    assert original == duplicated and len(duplicated) == len(set(duplicated))
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "version": "local-retrieval-v1",
        "sample_size": len(QUERIES),
        "scope": "Real small guidance corpus, local token-overlap title/body ranks, actual application RRF; independent of auditor.",
        "metrics": {
            "local_lexical_rrf_recall_at_1": sum(x["recall_at_1"] for x in observations) / len(observations),
            "local_lexical_rrf_recall_at_3": sum(x["recall_at_3"] for x in observations) / len(observations),
            "local_lexical_rrf_mrr": sum(x["reciprocal_rank"] for x in observations) / len(observations),
            "duplicate_rank_entry_invariance": True,
            "postgres_fts_recall_at_k": None,
            "pgvector_recall_at_k": None,
            "reranker_quality": None,
        },
        "observations": observations,
        "limitations": [
            "Four authored relevance queries over four guidance documents; no independent human labels or held-out retrieval benchmark.",
            "Both rankings are lexical token overlap; title/body RRF is not semantic hybrid search.",
            "PostgreSQL tenant filters, full-text ranking, vector embeddings and reranking not executed by this evaluator.",
            "Duplicate rank entries tested against actual application fusion function, not database content deduplication.",
        ],
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    text = [
        "# Observed local retrieval smoke evaluation",
        f"\nGenerated {report['generated_at']}. Queries: {len(QUERIES)}.",
        "\n" + report["scope"],
        "\n## Measurements",
    ]
    text += [f"- {key}: {value if value is not None else 'unavailable'}" for key, value in report["metrics"].items()]
    text += ["\n## Limitations"] + ["- " + x for x in report["limitations"]]
    (output / "report.md").write_text("\n".join(text) + "\n")
    print(json.dumps(report["metrics"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "evals/reports/retrieval")
    run(parser.parse_args().output)
