# Manuscript claim-to-evidence map — 2026-09-17

All paths are repository-relative. Original scores are immutable inputs; AI review replacements are separately labelled sensitivity analyses.

| Manuscript claim | Source | Boundary / reproduction |
|---|---|---|
| Five historical paired effects | `benchmark/results/paired-effect-stats.json` | `npm run check:paper-paired`; heterogeneous scales, no pooling or capability curve |
| Historical GLM rounds / leave-one-out | `benchmark/results/glm-pair-stability.json` | Existing stability analysis; model/judge confounds persist |
| Focal 16×2×2, original +4.9219 | `benchmark/results/artifacts/2026-09-15-glm-5.3-flash-unified-s16/{aggregate,paired-analysis}.json` | Equal task weights; static reward, not execution success |
| 64 report hashes, 328 original criteria | Same archive; `benchmark/scripts/audit-unified-evidence.mjs --check` | Two documented link rewrites; validates traceability/arithmetic, not semantic correctness |
| Fixed paired review, 10 answers / 56 criteria | `paper/audit/output-review-20260917/{selection,verdicts}.json`; archive `targeted-ai-review.json` | Frozen selection commit 181aef9; non-blind purposive AI review, one overlap deduplicated |
| All three endpoint sensitivities | `paper/generated/submission-evidence.json` | `node paper/scripts/summarize-submission-evidence.mjs --check`; unchanged unreviewed cells |
| S11 parent path counterexample | Archive targeted review + evidence audit script | Predicate defect only; no complete exploit claim |
| Focal token/duration fields | Archive `execution-log.jsonl` | 64 formal cells only; tokens unspecified, durations summed not parallel wall time |
| Historical resource totals | `benchmark/results/artifacts/2026-09-11-glm-5.3-flash-s1-s22/usage-summary.json` | Same submission summary script; 22 sessions per arm; cache separated |
| Supplementary GLM-5.3 +1.9318 | `benchmark/results/validation-report-2026-09-15-glm-5.3-s1-s22.md`; corresponding `aggregate.json` and 44 verdicts | One attempt per arm, newer all-semantic grading; no repeated-run variability claim |
| Supplementary Qwen +6.71875 | `benchmark/results/validation-report-2026-09-16-codex-qwen3.8-27b-medium-s16-paired.json` | Answers/reasons missing; reported CI not exactly reproducible; no cross-host ranking |
| Historical snapshot and development exposure | `benchmark/snapshots/2026-09-01-main-23.json`; `paper/audit/task-exposure-ledger.csv` | Inventory is not every study denominator; no independent holdout claim |

## Scope and unresolved facts

Existing sources support a retrospective case study, not a capability law, operational pass rate, isolated procedural-skill effect, or universal generalization. No new experiments are required by the current work plan. Author declarations, material redistribution, permanent release and journal entry requirements remain submission checks. Unexecuted ablations are not empirical contributions.

Primary related-work records are in `paper/latex/custom.bib`; the paper cites the versioned SkillsBench, SWE-Skills-Bench, SkillLens, WebDev-Skills-Bench, VersiCode and CODEMENV records. It does not claim to be the first study of heterogeneous skill effects or overhead. JSS's current guide endpoint returned 403 during this revision, so current format and declaration rules were not certified.
