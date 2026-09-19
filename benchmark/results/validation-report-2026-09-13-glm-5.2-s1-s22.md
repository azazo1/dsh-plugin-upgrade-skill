# GLM-5.2 S1–S22 validation run · round 1 (zero-skill vs with-skill) · 2026-09-13

> Round 1 of the recommended 3-round median protocol, following the [`glm-5.3-flash` three-round record](validation-report-2026-09-11-glm-5.3-flash-s1-s22.md). Claimed via [#218](https://github.com/oh-my-dsh/dsh-plugin-upgrade-skill/issues/218) (matrix gap: a second model on the dsh harness). Rounds 2–3 are planned as follow-up PRs.

## Setup

- **Solver**: `zai/glm-5.2` running inside the dsh web harness (in-session subagents, 3–4 concurrent, one attempt per task per condition, no retries to improve scores).
- **Base commit**: `a43afbe` (same S1–S22 task set and scoring surfaces as the 5.3-flash record; S13/S14/S20 still official keyword judges at this base, everything else packet-based report judging).
- **Skill condition**: with-skill runs read `skills/plugin-upgrade/SKILL.md` (+ references on demand) before the brief; zero-skill runs received no skill material.
- **Scoring**:
  - S13/S14/S20 — official `judge.mjs` executed locally with the environment-Dockerfile staging flow (fixture copy + baseline git commit); deterministic keyword judges, immune to same-family bias.
  - The other 19 tasks — glm-5.3-flash judge subagents scored each report against the sealed `packet.json` rubric and caps (same judge model as the 5.3-flash record, keeping the judge constant while the solver varies), then official aggregation rules were applied deterministically (pass = 1, partial = 0.5, fail/missing = 0; triggered caps clamp the total). Judge model ≠ solver model this round, so the same-family correlation bias disclosed in the 5.3-flash record does not apply to the 19 LLM-judged tasks.
- **Read-only discipline**: all 44 solver runs left the benchmark repository clean (`git status` verified after the run).

## Results

| Arm | Total | Mean |
|---|---:|---:|
| zero-skill | **2086 / 2200** | 94.8% |
| with-skill | **2120 / 2200** | 96.4% |
| skill lift | **+34 (+1.5 pp)** | |

Per-task scores are in `artifacts/2026-09-13-glm-5.2-s1-s22/aggregate.json`; raw reports under `noskill/<task>/report.md` and `skill/<task>/report.md`, judge verdict JSONs under `judge/`, keyword judge outputs in `keyword-scores.json`.

## Comparison with the glm-5.3-flash three-round medians

| Metric | glm-5.3-flash (3-round median) | glm-5.2 (round 1) |
|---|---:|---:|
| zero-skill | 1711 / 2200 (77.8%) | **2086 / 2200 (94.8%)** |
| with-skill | 1915 / 2200 (87.0%) | **2120 / 2200 (96.4%)** |
| skill lift | +204 (+9.3 pp) | +34 (+1.5 pp) |

- **Model jump dominates the skill effect.** glm-5.2 zero-skill scores +375 over the 5.3-flash zero-skill median and +171 over the 5.3-flash *with-skill* median.
- **Skill lift narrows to +1.5 pp** — a ceiling effect consistent with other strong-model records (astra, qwen paired): the skill's remaining measurable wins are S4 (+37), S20 (+20), S6/S11/S21 (+10…+12).
- **S19 (phantom-update-stale-host) went from three-round 0/0 with glm-5.3-flash to 100/100 with glm-5.2 in both arms.** The full stale-host three-link chain is covered unaided; the #213 follow-up item "re-check S19 rubric/prompt gradient" is resolved in favor of "solver capability, not a broken task".
- **S17** remains comparatively hard for both models (5.2: 90/90 vs 5.3: 20→40), but the gap is much smaller.

## Keyword-judge caveats

S13/S14/S20 still use the literal-regex keyword judges at this base (S13/S14 are converted to report judging in #216, not yet merged here). Two skill-arm regressions on these tasks (S13 100→80, S14 100→80) come from paraphrased wording missing a literal aspect, not from weaker analysis — the known keyword-judge limitation; the report-judge conversions in #216 remove this class of noise.

## Disclosures / limitations

- Single round (n=1 per cell); round-to-round variance exists (see the 5.3-flash record). Rounds 2–3 with the same setup are planned before any paired-median summary.
- The 19 report-judged tasks use LLM judges (glm-5.3-flash) that are the same model family as the *previous* record's judge but a different family from this round's solver; judge identity is held constant against #213 by design, but LLM judges remain imperfect ground truth.
- One skill-arm solver agent (S7) reported a post-write failure after the report file was written; the file was verified complete (tail check) and scored normally. Two subagent launches hit a transient harness validation error and were relaunched once; this is launch-infrastructure noise, not task attempts.
- Solver token/wall-time accounting was not extracted this round; the dsh session logs for all 44 runs are retained locally and can be added on request.
