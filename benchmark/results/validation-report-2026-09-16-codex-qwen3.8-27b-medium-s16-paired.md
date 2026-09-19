# Codex + local `qwen3.8-27b` (medium) · 16-task S-pool paired run · 2026-09-16

**Status: DRAFT — exploratory evidence for the inverted-U workplan ([`paper/INVERTED-U-WORKPLAN.zh.md`](../../paper/INVERTED-U-WORKPLAN.zh.md) §5), not a formal benchmark record.**

This is the `Qwen3.8-27B` cell of the workplan's three-config comparison: 16 S-prefix tasks × 2 arms (with-skill / no-skill) × 2 reps = **64 trials**, run on one local H20 GPU with no provider bill. It is deliberately **not** added to the benchmark results table in `benchmark/README.md`, for two protocol reasons stated below: the agent timeout budget deviates from the task defaults (§ Budget policy), and the run uses two reps per cell rather than the recommended three-run median.

## Headline

- with-skill **0.7789** (18/32 perfect) vs no-skill **0.7117** (13/32 perfect); task-weighted Δ **+0.0672**, bootstrap 95% CI **[−0.124, +0.263]** (task-level resampling, 10,000 draws, seed `20260915`).
- Timeouts: **5/64 (7.8%)** — 4 with-skill vs 1 no-skill. The earlier Qwen run on the same task family under the shipped 300 s budgets timed out on roughly **55%** of S-series trials; this newer run has a lower observed timeout rate, but task coverage, scoring and execution also changed, so the reduction cannot be attributed to budget alone.
- The skill arm consumed **2.51× the input tokens** (13,795,810 vs 5,490,991) for a mean gain of +0.067 — this documents a resource increase alongside an uncertain score gain; it does not define a score-to-cost break-even point.
- Largest gains: **S17 +0.95** (bare no-skill arm scores 0.00), S6 +0.56, S2 +0.55, S1 +0.38. Regressions: S19 −0.65, S11/S18 −0.45, S15 −0.10, S21 −0.05.
- All 64 trials produced judge verdicts; **zero `judge_error`**.

## Execution and provenance

- Frozen task/grader source: **`860f4c1423d1ae513c5d2947e0e2a7fadf4a3565`** (main, 2026-09-15), with the recorded working-copy deltas below.
- Agent: **Codex CLI 0.153.4**, `reasoning_effort = medium`; solver model `qwen3.8-27b` served locally by vLLM 0.28.0 (`max_model_len=262144`, 1× NVIDIA H20 96 GB, BF16). Harbor 0.22.0 manages containers and verification.
- Sampling: **16 of 22 S tasks**, stratified by (source event = 2nd tag, difficulty, instruction-length tercile) with round-robin per stratum and a fixed seed derived from the commit: `sha256(commit|salt)[:16] = 1415dd3d7288176b`, salt `inverted-u-qwen-medium|arm=qwen3.8-27b|v1`. The selection was frozen **before any score was observed** and has never been adjusted; no task was picked for its expected skill gain.
- Conditions interleaved: within each rep the two arms of a task run adjacently, with the arm order alternating by `(task_index + rep)` parity, so no condition systematically runs earlier in the schedule.
- One trial per job (`-k 1 -n 1`), single GPU, serial; `--environment-build-timeout-multiplier 4`.
- Codex config: `model_max_output_tokens=16384`, `model_context_window=200000`, `model_auto_compact_token_limit=999999` (auto-compaction disabled; vLLM 0.28.0 implements neither codex compaction endpoint).
- Cost: **no API cost** — local single-GPU inference. The comparable resource is GPU wall time, reported below.

### Working-copy deltas (recorded; see the run provenance)

1. CRLF normalized to zero (2 files);
2. digest-pinned `FROM` rewritten to the local shadow tag (H11, H21 Dockerfiles);
3. anti-cheat stripping (`**/solution/`, `**/provenance/`, `run-codex-closed-book.sh`);
4. **budget policy** below.

## Budget policy (§5 locked wall-clock ceiling)

- All 22 S-series tasks' `[agent] timeout_sec` were set to a uniform **900.0** in the frozen working copy (17 tasks 300→900, 4 tasks 600→900, 1 task 900→900); verifier timeouts unchanged at 240 s and run with `--verifier-timeout-multiplier 2`.
- Rationale: 3× the shipped 300 s cap, and 1.6× the maximum observed natural completion (564 s) of S tasks in the earlier 56-task keyword-scored Qwen round.
- This is an intentional, recorded deviation from the shipped task defaults — the workplan requires the wall-clock ceiling to be locked by pilot evidence, not copied from the old 300 s.

## Scoring method (disclosed)

- Each task's `report-judge-v2` judge ran inside the separate verifier container; missing/broken judge is an evaluator failure with no keyword fallback, per the task contract.
- Judge model: **`gpt-5.4`**, a cross-family external judge (solver is Qwen). The initially requested `gpt-5.6-sol` routes through a GitHub Copilot Responses backend that rejects the judge's fixed `response_format: {"type":"json_object"}` request body (400: *"Response input messages must contain the word 'json' in some form"*); a 14-model probe of the endpoint found `gpt-5.4` to be the only modern model accepting the exact judge request shape and returning parseable JSON. See `validation-report-2026-09-16-codex-qwen3.8-27b-medium-s16-paired.json` for the probe table.
- 64/64 trials `scored`; per-item verdicts and reasons are retained in each trial's `verifier/details.json`.

## Scores, tokens, and time

| Condition | Mean | Perfect | Zero | Timeouts | Summed trial seconds | Summed job wall | Input / cache / output tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| with-skill | 0.7789 | 18 | 5 | 4 | 14,676.4 | 14,714 s (4.09 h) | 13,795,810 / 13,094,368 / 592,951 |
| no-skill | 0.7117 | 13 | 3 | 1 | 12,141.1 | 12,178 s (3.38 h) | 5,490,991 / 5,189,296 / 503,465 |

Cached input is a subset of input. Trial seconds and token sums are read from Harbor's trial/job `result.json`; job wall is the sum of `timing.csv` wall seconds.

| Task | with-skill | no-skill | Δ | timeouts (w/n) |
|---|---:|---:|---:|---:|
| S1-static-scan | 0.500 | 0.125 | +0.375 | 1 / 0 |
| S2-negative-scan | 1.000 | 0.450 | +0.550 | 0 / 0 |
| S5-negative-naming | 0.812 | 0.625 | +0.188 | 0 / 0 |
| S6-corridor-net-state | 1.000 | 0.438 | +0.562 | 0 / 0 |
| S8-release-routing-trap | 0.900 | 0.850 | +0.050 | 0 / 0 |
| S10-paste-rename-and-version-chip | 1.000 | 0.950 | +0.050 | 0 / 0 |
| S11-mermaid-lazyload-trap | 0.450 | 0.900 | −0.450 | 0 / 0 |
| S12-global-upgrade-ebusy-trap | 1.000 | 1.000 | 0.000 | 0 / 0 |
| S13-peer-range-vs-runtime | 1.000 | 1.000 | 0.000 | 0 / 0 |
| S14-link-install-lock-trap | 1.000 | 1.000 | 0.000 | 0 / 0 |
| S15-slot-error-boundary-crash | 0.900 | 1.000 | −0.100 | 0 / 0 |
| S17-external-ui-plugin-onboarding-trap | 0.950 | 0.000 | **+0.950** | 0 / 0 |
| S18-terminal-sprite-render-trap | 0.300 | 0.750 | −0.450 | 1 / 0 |
| S19-phantom-update-stale-host | 0.000 | 0.650 | **−0.650** | 2 / 1 |
| S21-resource-service-unavailable-trap | 0.650 | 0.700 | −0.050 | 0 / 0 |
| S22-duplicate-insert-boot-crash-trap | 1.000 | 0.950 | +0.050 | 0 / 0 |

## Statistical boundaries

- Δ is computed per task (mean of 2 reps per arm), then averaged with equal task weight — the workplan §5 primary-analysis convention. Bootstrap resamples the 16 task deltas; the resulting 95% interval **[−0.124, +0.263]** spans zero, so the positive direction is **not decisive**.
- 8 tasks positive / 3 zero / 5 negative — the point estimate is driven by a few tasks (S17 +0.95, S2/S6 ≈ +0.55) while S19 (−0.65) and S11/S18 (−0.45) run the other way.
- Single batch, two reps; no across-batch variance was measured. Bootstrap and a paired significance test would not be two independent confirmations, so only the interval is reported.
- Timeouts are reported separately and never imputed: all five timed-out trials have status `scored` in the submitted CSV (four rewards 0.0, one 0.3); the underlying verdict reasons are not committed; two trials recorded `NonZeroAgentExitCodeError` (S1 no-skill rep1 → 0.0, S11 with-skill rep1 → 0.0). All seven exceptional trials are listed in the companion CSV/JSON.

## Comparison boundaries

- **Not comparable to the archived keyword-scored Qwen point** (`74af446`, 2026-09-11): the judge protocol changed from keyword/rubric to `report-judge-v2` semantic grading (*"version-4 semantic scores are not interchangeable with archived keyword scores"*), **and** the budget changed. The direction flip (negative → positive Δ) therefore conflates both variables and must not be read as a clean budget effect.
- **Not directly comparable to the GLM-5.3-flash S1–S22 arm**: different harness (codex vs dsh), different judge model, different reps, and GLM's 12 semantic tasks were graded by a same-family GLM judge (disclosed in that report) while this run uses a cross-family judge throughout.
- These 16 tasks are a stratified sample of the 22-task pool; S3/S4/S7/S9/S16/S20 were not selected by the frozen seed.

## Reproduction

The committed CSV permits independent recomputation of score means, durations, exception counts and task deltas; independent reproduction of the full run and its grading requires the uncommitted raw artifacts. Per-trial rewards, seconds, exceptions and judge statuses are in `validation-report-2026-09-16-codex-qwen3.8-27b-medium-s16-paired.csv` / `.json`. Aggregation scripts (task-weighted Δ, bootstrap) are in the contributor's run record; raw agent sessions and verifier outputs are retained by the contributor and not committed.

## Non-goals

This is a single-config cell of the inverted-U design, not a complete shape analysis, not a significance claim, and not a formal benchmark entry. The three-config comparison and the paper-level statements remain with the workplan's decision points.

Maintainer boundary: token totals and job-wall totals are contributor-reported aggregates, not independently verifiable from the committed CSV (which lacks per-trial token and job-wall fields). The sampling script, bootstrap PRNG definition and raw verdicts are not committed, so the exact seed-to-sample and seed-to-interval reproduction remains incomplete. This is archived as a disclosed draft, not certified as the completed unified three-configuration experiment.
