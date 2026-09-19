# GLM-5.3 S1–S22 validation run · round 1 (zero-skill vs with-skill) · 2026-09-15

> Round 1 for GLM-5.3, complementing the glm-5.3-flash three-round record ([#213](https://github.com/oh-my-dsh/dsh-plugin-upgrade-skill/pull/213), 3-round medians) and the glm-5.2 three-round record ([#219](https://github.com/oh-my-dsh/dsh-plugin-upgrade-skill/pull/219)/[#220](https://github.com/oh-my-dsh/dsh-plugin-upgrade-skill/pull/220)/[#222](https://github.com/oh-my-dsh/dsh-plugin-upgrade-skill/pull/222)). Claimed via [#218](https://github.com/oh-my-dsh/dsh-plugin-upgrade-skill/issues/218).

## Setup

- **Solver**: `zai/glm-5.3` in the dsh web harness (in-session subagents, concurrency 2, one attempt per task per condition, no retries).
- **Base commit**: `e0a9ff5` (at this base #216 is merged, so **all 22 tasks use packet-based LLM report judging** — S13/S14/S20 are no longer keyword-judged).
- **Judges**: `zai/glm-5.3-flash` subagents scoring each report against the sealed `packet.json` rubric and caps, with official deterministic aggregation (pass = 1, partial = 0.5, fail/missing = 0; triggered caps clamp).
- **Execution**: no API-quota interruption and no relaunch during solving (per the solving session's record). 44/44 reports verified on disk; the benchmark repository stayed clean (fixture read-only discipline held).

## Results

| Arm | Total | Mean |
|---|---:|---:|
| zero-skill | **2117.5 / 2200** | 96.3% |
| with-skill | **2160 / 2200** | 98.2% |
| skill lift | **+42.5 (+1.9 pp)** | |

Per-task scores and notes: `artifacts/2026-09-15-glm-5.3-s1-s22/aggregate.json`. Raw reports under `noskill/`, `skill/`; judge verdicts under `judge/{noskill,skill}/`.

## Historical configurations on the same task pool (protocols differ)

| Model | Protocol | zero-skill | with-skill | lift |
|---|---|---:|---:|---:|
| glm-5.3-flash | 3-round median ×22 | 1711 / 2200 (77.8%) | 1915 / 2200 (87.0%) | **+204 (+9.3 pp)** |
| glm-5.2 | 3-round median ×22 | 2053 / 2200 (93.3%) | 2120 / 2200 (96.4%) | **+67 (+3.0 pp)** |
| glm-5.3 (this run, n=1) | single round ×22 | 2117.5 / 2200 (96.3%) | 2160 / 2200 (98.2%) | **+42.5 (+1.9 pp)** |

The point estimates of absolute skill lift decrease across these three named configurations (+9.3 → +3.0 → +1.9 pp), while their observed no-skill scores increase. This is a descriptive historical comparison, not an independently established capability ladder. Repetition counts, scoring versions and other protocol details differ. High baselines leave little room for absolute improvement, but these data do not identify why lift differs or show that stronger models cannot use skills. This adds a high-baseline observation; it does not test the rising side or establish an inverted-U law.

- With glm-5.3, 15 of 22 tasks are already at 100/100 zero-skill; the remaining zero-skill shortfalls are S8 (80), S4 (75), S6 (87.5), S15/S16 (90), S1 (95).
- In this GLM-5.3 round, S8 stays at 80 in both arms. It is not a universal no-benefit task: the historical GLM-5.3-flash three-round medians show a +10-point lift on S8.
- S4 remains the largest skill win (75 → 100); S6, S15, S16 also repaired to 100 by the skill.
- Two skill-arm regressions: S17 (node --check instead of vm.Script parse) and S18 (teardown disposal instead of `timer.unref`) at 90 each.

## Disclosures / limitations

- Single round (n=1) for glm-5.3; the glm-5.2 and glm-5.3-flash rows are 3-round medians, so cross-row comparison mixes aggregation protocols ; this run alone does not quantify between-run variability or establish a cross-model ordering.
- Judge model (glm-5.3-flash) differs from the solver (glm-5.3) — same family, so same-family correlation bias remains possible. Using a different model does not demonstrate a reduction in that bias; independent scoring review remains necessary.
- **S15-noskill report truncation**: the solver report ends mid code block at the model output-length limit (159 lines). It was judged as-is (90/100) per the single-attempt protocol; this is an output-limit truncation, not an API-quota or concurrency failure, so no re-run was performed.
- Judge verdicts live in per-arm subdirectories because verdict filenames do not carry the arm (the flat layout caused cross-arm overwrites in earlier rounds).

## Maintainer verification (2026-09-16)

All 44 committed verdicts were recomputed with the rubric packets from `e0a9ff5`. The S6 no-skill score is exactly **87.5**, not the initially rounded 88; the corrected no-skill total is **2117.5**, with-skill total **2160**, and lift **42.5 / 22 = 1.9318 pp**. Reports and criterion-level verdicts are unchanged. No new model calls or re-grading were performed.
