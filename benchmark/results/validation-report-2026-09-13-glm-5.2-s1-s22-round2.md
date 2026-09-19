# GLM-5.2 S1–S22 validation run · round 2 (zero-skill vs with-skill) · 2026-09-13

> Round 2 of the recommended 3-round median protocol. Round 1: PR #219 (validation-report-2026-09-13-glm-5.2-s1-s22.md). Same solver, model, base commit and scoring setup as round 1; no answer was rerun to improve any score.

## Setup

Identical to round 1: solver `zai/glm-5.2` in the dsh web harness (in-session subagents, 3–4 concurrent, one attempt per task per condition), base commit `a43afbe`, with-skill runs read `skills/plugin-upgrade/SKILL.md` first, S13/S14/S20 scored by official local keyword judges, the other 19 tasks scored by glm-5.3-flash judge subagents against sealed packets with deterministic aggregation. All 44 solver runs left the benchmark repository clean.

## Results

| Arm | Total | Mean |
|---|---:|---:|
| zero-skill | **2084 / 2200** | 94.7% |
| with-skill | **2120 / 2200** | 96.4% |
| skill lift | **+36 (+1.6 pp)** | |

Per-task scores: `artifacts/2026-09-13-glm-5.2-s1-s22-round2/aggregate.json`; raw reports under `noskill/` and `skill/`, verdict JSONs under `judge/`.

## Round 1 vs round 2 (glm-5.2)

| Metric | Round 1 | Round 2 |
|---|---:|---:|
| zero-skill | 2086 / 2200 | 2084 / 2200 |
| with-skill | 2120 / 2200 | 2120 / 2200 |
| skill lift | +34 (+1.5 pp) | +36 (+1.6 pp) |

Direction and magnitude are stable across rounds: with-skill is byte-identical in total (2120), zero-skill differs by 2 points. Per-task movement is small and scattered (e.g. S11 noskill 80→90, S13/S14 noskill 100→80 on literal keyword aspects, S20 noskill 80→100) — consistent with single-attempt sampling noise around a saturated mean rather than any condition change.

- Consistent skill wins across rounds: S4 (R1 +37, R2 +12), S20 (+20/+0), S6 (+12/+12).
- S19 remains 100/100 in both rounds (vs three-round 0/0 with glm-5.3-flash).
- S17 stays at 90/90 — the hardest remaining task for this model pair.
- S8 dropped in both arms this round (100→80/90): the reports' install commands present v0.9.3 as immediately installable while the fixture tag list omits it — a real rubric-relevant miss, symmetric across arms.

## Limitations

Same disclosures as round 1: single attempt per cell; LLM judges (glm-5.3-flash) are imperfect ground truth but held constant against #213 and #219; S13/S14/S20 keyword judges are literal-regex based at this base (report-judge conversions pending in #216), so paraphrase misses (this round: both arms on S13/S14) score lower without implying weaker analysis. Round 3 is planned to complete the paired-median summary.
