# Baseline comparison protocol

No live A/B comparison has yet been measured. The contract report separately identifies unavailable single-prompt, retrieval-assisted, and full-workflow results.

Use identical held-out captures and a frozen provider model for all arms. A receives deterministic evidence and the finding schema in one prompt. B additionally receives the same versioned guidance retrieved using tenant-filtered text/vector search and reciprocal rank fusion. C uses B's validated findings, approved facts, the constrained designer, and executable before/after verification, with at most two repairs. Keep common token and monetary ceilings; also report actual usage by arm.

A and B are compared on finding precision/recall and evidence support, with hypotheses scored separately by human reviewers. C additionally reports repair success, regressions, preservation, successful completion, and accepted-preview cost. Exclude unavailable checks from success denominators only with a separately reported availability rate. Count aborted jobs in completion and recovery denominators.

Run repeated browser measurements when comparing Lighthouse. Do not use Lighthouse as a sales metric. Report confidence intervals for sufficiently large independent website samples; the nine initial variants constitute one related website group and do not support a meaningful generalization estimate.
