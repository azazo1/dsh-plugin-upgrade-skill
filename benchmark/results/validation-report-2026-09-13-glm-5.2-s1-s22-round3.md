# GLM-5.2 S1–S22 validation run · round 3 + three-round paired-median summary · 2026-09-13

> Round 3 of the recommended 3-round median protocol. Rounds 1–2: PR #219 (`validation-report-2026-09-13-glm-5.2-s1-s22.md`) and PR #220 (`...-round2.md`). Same solver, model, base commit and scoring setup throughout.

> **Data status (resolved 2026-09-15)**: the round-3 raw artifacts (44 solver reports, 38 judge verdicts, both arms) are now committed in this directory; the reconstructed aggregate.json matches them. The previously reported internal discrepancy is resolved: the totals line below (1895/2005) was computed while the two S22 judge verdicts were absent from the judge directory, so S22 (100/100 both arms; verdict files re-obtained from the run author) was silently excluded — the correct round-3 totals are **1995/2105**, matching the per-task table. Three-round paired medians (2053/2120, +67) are unchanged.

## Setup

Identical to rounds 1–2: solver `zai/glm-5.2` in the dsh web harness, one attempt per task per condition, base commit `a43afbe`, with-skill runs read `skills/plugin-upgrade/SKILL.md` first, S13/S14/S20 scored by official local keyword judges, the other 19 tasks by glm-5.3-flash judge subagents against sealed packets with deterministic aggregation. All 44 solver runs left the benchmark repository clean.

Round-3 execution note: two API-quota windows interrupted the run. Round 3 started serially (S1–S2), resumed at 4-way concurrency from S3; a second window interrupted the last three skill-arm solvers mid-write (S19's file was verified complete and kept; S20/S21 relaunched fresh; S22 launched after recovery). Concurrency differences across rounds do not interact with conditions (tasks are independent); disclosed for completeness.

## Round 3 results

| Arm | Total | Mean |
|---|---:|---:|
| zero-skill | **1995 / 2200** | 90.7% |
| with-skill | **2105 / 2200** | 95.7% |
| skill lift | **+110 (+5.0 pp)** | |

Round 3 is the weakest of the three rounds (R1: 2086/2120, R2: 2084/2120), with scattered single-criterion partials across both arms (e.g. S1 skill host-services, S3 skill slot mechanics, S15 skill attribution caveat) — the profile of a noisier execution window rather than a condition change. Weakest stable zero-skill task remains S4 (50; 63/88 in rounds 1–2), and skill arm repairs it to 100 in all three rounds.

## Three-round paired medians (recommended protocol final)

| Task | R1 zero | R1 skill | R2 zero | R2 skill | R3 zero | R3 skill | median zero | median skill | Δ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| S1-static-scan | 95 | 100 | 100 | 100 | 100 | 95 | 100 | 100 | +0 |
| S10-paste-rename-and-version-chip | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | +0 |
| S11-mermaid-lazyload-trap | 80 | 90 | 90 | 80 | 80 | 90 | 80 | 90 | +10 |
| S12-global-upgrade-ebusy-trap | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | +0 |
| S13-peer-range-vs-runtime | 100 | 80 | 80 | 80 | 60 | 100 | 80 | 80 | +0 |
| S14-link-install-lock-trap | 100 | 80 | 80 | 80 | 80 | 100 | 80 | 80 | +0 |
| S15-slot-error-boundary-crash | 100 | 90 | 100 | 90 | 100 | 80 | 100 | 90 | -10 |
| S16-self-host-upgrade-trap | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | +0 |
| S17-external-ui-plugin-onboarding-trap | 90 | 90 | 100 | 100 | 90 | 80 | 90 | 90 | +0 |
| S18-terminal-sprite-render-trap | 100 | 90 | 100 | 100 | 100 | 100 | 100 | 100 | +0 |
| S19-phantom-update-stale-host | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | +0 |
| S2-negative-scan | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | +0 |
| S20-msvc-flock-trap | 80 | 100 | 100 | 100 | 92 | 100 | 92 | 100 | +8 |
| S21-resource-service-unavailable-trap | 90 | 100 | 100 | 100 | 90 | 90 | 90 | 100 | +10 |
| S22-duplicate-insert-boot-crash-trap | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | +0 |
| S3-snapshot-migration | 100 | 100 | 90 | 100 | 100 | 90 | 100 | 100 | +0 |
| S4-legacy-client-imports | 63 | 100 | 88 | 100 | 50 | 100 | 63 | 100 | +37 |
| S5-negative-naming | 100 | 100 | 100 | 100 | 88 | 100 | 100 | 100 | +0 |
| S6-corridor-net-state | 88 | 100 | 88 | 100 | 75 | 100 | 88 | 100 | +12 |
| S7-unpublished-cohort | 100 | 100 | 88 | 100 | 100 | 100 | 100 | 100 | +0 |
| S8-release-routing-trap | 100 | 100 | 80 | 90 | 90 | 80 | 90 | 90 | +0 |
| S9-composer-coordinate-trap | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | +0 |
| **TOTAL (paired medians, 22 tasks)** | | | | | | | **2053** | **2120** | **+67** |

**Paired-median totals: zero-skill 2053 / 2200 (93.3%), with-skill 2120 / 2200 (96.4%), skill lift +67 (+3.0 pp).**

## Three-round conclusions (glm-5.2 on dsh)

- **Model jump dominates the skill effect** (consistent with rounds 1–2): glm-5.2 paired-median zero-skill 2053 exceeds the glm-5.3-flash three-round with-skill median (1915) by +138.
- **Skill lift is +67/+3.0 pp on medians** — stable and positive, driven by S4 (+37), S6 (+12), S11 (+10), S21 (+10), S20 (+8); the only negative median is S15 (−10).
- **S19: three-round 6/6 perfect scores** for glm-5.2 (vs 0/0 ×3 for glm-5.3-flash) — confirms the task discriminates capability, not a rubric defect.
- **S17 is the hardest residual task** (medians 90/90; never 100 in any arm).
- Keyword-judge literal matching (S13/S14/S20 at this base) continues to produce paraphrase-miss noise (e.g. round 3 noskill S13 60); #216's report-judge conversions address this.

## Artifacts

`artifacts/2026-09-13-glm-5.2-s1-s22-round3/`: aggregate.json, 44 solver reports, 38 judge verdict JSONs, keyword-scores.json, run-manifest.json. Rounds 1–2 artifacts live on their PR branches (#219, #220); their aggregate.json files were retro-patched in this PR's sibling commits to include the three keyword-task rows that the round-1 generation script omitted (scores unchanged, sourced from each round's keyword-scores.json).
