# Generic-skill control arm, pilot run: S1–S10 with a framework-agnostic migration skill (2026-09-07)

> **Status: PILOT / not an official snapshot run.** This is the T1a+smoke stage of the
> generic-skill control (GAP-ANALYSIS T1): the generic skill exists and has been exercised
> end-to-end through the official judges on 10 tasks. It is **not** the T1b formal arm
> (which requires `deepseek-v4-flash` + terminus-2, 23 tasks × 3 trials, no-network,
> full token/cost accounting).

## Setup

- **Control skill under test**: `skills/generic-migration/SKILL.md` (new in this change).
  Framework-agnostic migration methodology; contains **no** dsh version numbers, API
  names, card IDs, or framework-specific commands (T1a leak rules). Authored by an LLM
  without access to framework materials, then screened for leakage.
- **Agent**: Kimi Code CLI subagents (one fresh instance per task), each given only
  (a) the task `instruction.md`, (b) the task `environment/fixture/`, (c) the generic
  skill. Explicitly barred from reading `skills/plugin-upgrade/`, cards, solutions,
  or the network. This mirrors the intended generic-skill condition: methodology,
  zero framework facts.
- **Tasks**: S1–S10 (static/written tasks), n=1 per task.
- **Scoring**: official per-task Docker images + unmodified `tests/judge.mjs`, agent
  output mounted read-only at `/app/agent-output/<task>/`. Raw judge output:
  `generic-arm-s1-s10/judge-output.jsonl`; reports: `generic-arm-s1-s10/<task>/report.md`.
- **Deviations from the benchmark submission norm** (why this is a pilot): no API
  token/cache/duration accounting (the agent is this CLI session, not a metered API
  stack); n=1; runs on macOS Docker Desktop, not the formal no-network Linux setup.
  No-network is not load-bearing here because the agents were instruction-fenced from
  the network rather than sandbox-fenced.

## Results

Comparison columns from `validation-report-2026-09-03-static-20-paired.md`
(GLM-5.3, paired, corrected 18-pair summary). **Cross-model caveat**: the generic arm
ran on a different model (Kimi), so column 3 vs columns 2/4 mixes the skill effect
with a model effect; read it as a smoke test of the control design, not a measured Δ.

| Task | GLM no-skill | Kimi + generic-skill | GLM + dsh-skill |
|---|---:|---:|---:|
| S1-static-scan | 33 | 0 | 33 |
| S2-negative-scan | 60 | 40 | 100 |
| S3-snapshot-migration | 60 | 40 | 80 |
| S4-legacy-client-imports | 100 | 100 | 100 |
| S5-negative-naming | 25 | 50 | 50 |
| S6-corridor-net-state | 10 | 25 | 10 |
| S7-unpublished-cohort | 10 | 50 | 50 |
| S8-release-routing-trap | 100 | 100 | 100 |
| S9-composer-coordinate-trap | 100 | 100 | 100 |
| S10-paste-rename-and-version-chip | 100 | 100 | 100 |
| **Mean** | **59.8** | **60.5** | **72.3** |

Data: `generic-arm-s1-s10/comparison.json`.

## What the pilot shows

1. **The control behaves as designed on knowledge-gated checkpoints.** Where a judge
   scores framework facts (card IDs, replacement API shapes), the generic arm scores
   0 on those checkpoints by construction — S1's judge is *pure* card-ID matching, so
   the generic arm gets 0/100 there despite a methodologically complete report. This is
   exactly the separation the paper's three-condition design wants: generic advice
   cannot inject field knowledge.
2. **Generic methodology does carry measurable value on judgment-heavy tasks.** S5
   (25→50, ties the dsh-skill arm), S7 (10→50, ties), S6 (10→25, beats *both* GLM arms):
   "verify before/after", "state unknowns honestly", "pin + lockfile" are transferable
   behaviors. The paper's claim must therefore be about the **residual** (72.3 vs ~60),
   not about skills-vs-nothing.
3. **Fixture leakage partially defeats the control on two tasks.** S4 and S6 fixture
   READMEs themselves name card IDs (A1-25/26/27/30, A1-02/A2-01), so a disciplined
   generic-arm agent can cite them — S4 scored 100/100 on card citations. For the
   formal T1b run, either scrub card references from fixtures or report these tasks
   separately; otherwise the generic arm is contaminated by in-fixture answers.
4. **Judge regex brittleness adds noise in both directions.** S6's judge reports
   "删除防御代码 conclusion missing" and S7's reports "caret silent-resolution
   semantics not identified", while the corresponding reports do contain both
   conclusions in different phrasing (same failure class as the #175 oracle finding).
   Several S-tasks score phrasing, not content; treat ±25 on single-checkpoint tasks
   as noise until judges are hardened.
5. **Honesty checkpoints reward the generic arm's discipline.** S2's "+20 zero-hit
   categories accounted for" and "+20 declares real verification required", and S5's
   "+25 unknowns marked as not-checked", were earned purely from methodology — the
   control skill's "state what you scanned and what you cannot rule out" section.

## Next steps toward formal T1b

- Scrub or flag in-fixture card references (S4, S6 at minimum) before the formal run.
- Harden the S5/S6/S7 judge checkpoints whose regexes missed correct conclusions
  (coordinate with the #175 judge fix).
- Run the formal arm: `deepseek-v4-flash` + terminus-2, full 23-task snapshot × 3
  trials × generic-skill, on the no-network Linux setup, with token/cost accounting
  per `benchmark/README.md` submission rules.
