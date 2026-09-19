# GLM-5.3-flash S1-S22 validation run (2026-09-11)

Model: GLM-5.3-flash, as both solver and rubric judge. Scope: all 22 S-prefix tasks on main (`f32175d`). Two conditions per task: zero injected skills vs the `plugin-upgrade` skill (SKILL.md + references) available to the solver. 3-4 concurrent solver agents, one run per task/condition, no retries. Times and token counts below are extracted from the per-agent DSH session logs (`session.v3.jsonl.zstd`), spanning full agent sessions (all turns, including fixture reading and report writing).

## Headline

- Zero-skill total: **1716 / 2200 (78.0%)**
- With-skill total: **1855 / 2200 (84.3%)**
- Skill lift: **+139 points (+6.3 pp)**. Largest lifts: S4 +62.5, S17 +20, S11/S13/S16/S20 +20, S3 +10, S6/S8 +10-25 band. Regressions: S1 -25 (skill run mapped the hard-coded profile-path hit to A1-13 and explicitly excluded the rubric A1-04), S18 -40 (skill run chose clearTimeout-on-unmount where the rubric requires timer.unref).
- Saturated tasks (100 both conditions): S2, S7, S9, S10, S12, S14, S15. S19 scored 0/0: both runs missed the multi-part stale-host chain (bump-before-build mechanics, host-process route staleness, upstream splice-report duty).
- Cost: with-skill runs consumed ~2.2x the tokens of zero-skill runs (skill files enter every turn context); wall time per task roughly doubled.

## Scores, tokens and wall time per task

Token columns: input (fresh) / output / total (incl. cache-read) / max agent wall time. All counts are per whole agent session from the DSH session logs.

| Task | Scoring | No-skill | With-skill | Delta | No-skill in/out/total/time | With-skill in/out/total/time |
| --- | --- | --- | --- | --- | --- | --- |
| S1-static-scan | 100 | 75 | -25 | 73,582 / 5,672 / 498,582 / 132s | 57,972 / 13,787 / 539,727 / 222s |
| S10-paste-rename-and-version-chip | 100 | 100 | +0 | 17,055 / 5,344 / 172,415 / 90s | 24,278 / 5,286 / 185,660 / 123s |
| S11-mermaid-lazyload-trap | 80 | 100 | +20 | 11,922 / 4,077 / 128,767 / 110s | 27,164 / 7,775 / 162,683 / 151s |
| S12-global-upgrade-ebusy-trap | 100 | 100 | +0 | 9,402 / 2,145 / 80,731 / 48s | 22,421 / 2,351 / 122,628 / 44s |
| S13-peer-range-vs-runtime | 80 | 100 | +20 | 10,459 / 2,435 / 125,342 / 62s | 27,934 / 3,878 / 254,276 / 82s |
| S14-link-install-lock-trap | 100 | 100 | +0 | 11,186 / 3,275 / 146,749 / 75s | 27,115 / 8,531 / 198,590 / 152s |
| S15-slot-error-boundary-crash | 100 | 100 | +0 | 16,530 / 8,402 / 193,572 / 164s | 27,592 / 6,354 / 254,618 / 122s |
| S16-self-host-upgrade-trap | 80 | 100 | +20 | 10,482 / 2,753 / 124,403 / 63s | 21,789 / 3,289 / 124,790 / 70s |
| S17-external-ui-plugin-onboarding-trap | 20 | 40 | +20 | 44,113 / 5,623 / 346,568 / 149s | 25,087 / 4,075 / 159,082 / 90s |
| S18-terminal-sprite-render-trap | 60 | 20 | -40 | 10,706 / 2,785 / 125,043 / 65s | 25,099 / 6,505 / 191,988 / 128s |
| S19-phantom-update-stale-host | 0 | 0 | +0 | 16,881 / 6,482 / 193,539 / 104s | 24,935 / 4,508 / 188,419 / 93s |
| S2-negative-scan | 100 | 100 | +0 | 71,919 / 4,617 / 633,144 / 108s | 37,946 / 4,148 / 373,614 / 90s |
| S20-msvc-flock-trap | 95 | 100 | +5 | 11,022 / 2,825 / 146,903 / 58s | 24,130 / 2,552 / 229,690 / 51s |
| S21-resource-service-unavailable-trap | 60 | 60 | +0 | 12,797 / 3,994 / 112,087 / 88s | 26,233 / 5,140 / 216,077 / 105s |
| S22-duplicate-insert-boot-crash-trap | 60 | 60 | +0 | 10,725 / 3,251 / 127,832 / 60s | 27,601 / 9,148 / 356,493 / 166s |
| S3-snapshot-migration | 90 | 100 | +10 | 187,132 / 25,840 / 2,599,276 / 359s | 57,389 / 13,133 / 753,722 / 227s |
| S4-legacy-client-imports | 38 | 100 | +62 | 9,233 / 2,166 / 120,647 / 46s | 50,609 / 7,486 / 481,711 / 126s |
| S5-negative-naming | 88 | 100 | +12 | 10,231 / 2,571 / 123,778 / 55s | 24,326 / 4,959 / 158,885 / 87s |
| S6-corridor-net-state | 75 | 100 | +25 | 9,661 / 2,255 / 122,060 / 53s | 35,314 / 4,524 / 253,534 / 79s |
| S7-unpublished-cohort | 100 | 100 | +0 | 12,837 / 6,381 / 152,786 / 116s | 34,681 / 4,802 / 217,723 / 97s |
| S8-release-routing-trap | 90 | 100 | +10 | 9,422 / 2,576 / 120,926 / 54s | 22,902 / 4,836 / 208,666 / 89s |
| S9-composer-coordinate-trap | 100 | 100 | +0 | 22,585 / 11,037 / 211,414 / 188s | 25,584 / 5,659 / 196,235 / 130s |

Suite totals: no-skill 1716 vs with-skill 1855 (of 2200). Solver-side tokens across both conditions: input 1,277,983 (excl. cache-read), output 249,232, total 12,435,375. Longest single agent: 359s.

## Scoring method (disclosed)

- 10 keyword-era tasks (S11, S13-S14, S16-S22): the official per-task `judge.mjs` at `main` executed locally (fixture staged at the judge expected `/app` root, baseline git commit replicated from the environment Dockerfile). Official deterministic verdicts.
- 12 semantic tasks (S1-S10, S12, S15): a GLM-5.3-flash judge agent scored each report against the sealed `packet.json` rubric (pass/partial/fail/missing per criterion); aggregated deterministically (pass = full, partial = half, fail/missing = 0). Judge sessions: 12 agents, ~0.5-10 min each.
- Limitation: solver and judge share the same model family; the 10 keyword-task scores are immune (deterministic judges).

## Follow-ups

- Live `calibrate.mjs --live` runs for the 19 semantic rubrics need `REPORT_JUDGE_*` credentials; the `calibration/S*.md` files for the seven newly converted tasks reuse each task reference answer as placeholders.
- S19 may warrant a rubric/hint review: both conditions scored 0.
- S13/S20 (other authors) remain keyword-scored.
