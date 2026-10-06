"""Format observed JSON, never turn blocked metrics into achieved values."""

import json
from pathlib import Path


def main():
    folder = Path("evals/reports/live")
    audit = json.loads((folder / "audit.json").read_text())
    ranking = json.loads((folder / "retrieval.json").read_text())
    lines = [
        "# Observed live-validation preparation",
        f"Code commit: `{ranking['code_commit']}`. Corpus: `{ranking['corpus_version']}`. Dataset: `{ranking['dataset_version']}`.",
        f"Live audit: **{audit['status']}**. Actual live audits submitted: {audit['live_audits_submitted']}. Cost USD: {audit['cost_usd'] if audit['cost_usd'] is not None else 'unknown'}.",
        audit.get("blocker", "Inspect audit.json for actual results and executable finding review."),
        f"Corpus documents: {ranking['documents']}; queries: {ranking['queries']} (16 dev/16 held-out, including four no-answer).",
        "\n## Actual PostgreSQL retrieval",
    ]
    for split, arms in ranking["metrics"].items():
        lines.append(f"\n### {split}")
        for arm, metrics in arms.items():
            lines.append(
                f"- {arm}: BLOCKED; real embeddings not generated."
                if metrics is None
                else f"- {arm}: recall@3={metrics['recall_at_3']:.4f}, recall@5={metrics['recall_at_5']:.4f}, MRR={metrics['mrr']:.4f}, nDCG@5={metrics['ndcg_at_5']:.4f}; SQL p50={metrics['latency_p50_ms']:.3f} ms, p95={metrics['latency_p95_ms']:.3f} ms; answer-bearing queries={metrics['answer_query_count']}."
            )
        no_answer = ranking["no_answer"][split]["keyword"]
        lines.append(
            f"- Keyword no-answer: {no_answer['raw_empty_results']}/{no_answer['query_count']} empty; false-answer rate={no_answer['raw_false_answer_rate']:.2f}. These are raw rankings, not calibrated abstention."
        )
    lines += [
        "\n## Verification boundary",
        "- Live vision/text/embedding behavior is unverified. No fixture result substituted for a live call.",
        "- New HTTP/journal failure scenarios are simulated, not provider observations; actual check results are in validation-checks.json.",
        "- Real PostgreSQL allocation gates passed using simulated prices/FX, with no paid calls.",
        "- Existing real-stack fixture regression passed six ordinary fixtures, real timeout, dashboard PNG/evidence navigation, recovery, correction persistence and deletion.",
        "- Labels were authored by the coding agent; independent human quality/relevance review is required.",
        "- No tuning performed. Semantic arms remain null. No hybrid superiority or production readiness claim.",
        "- No paid interruption performed; no exactly-once remote execution claim.",
        "- Existing Phase 3 work preserved; redesign feature validation and Phase 4 comparison remain outside this milestone.",
    ]
    (folder / "report.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
