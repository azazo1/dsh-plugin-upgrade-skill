# Codex + local qwen3.8-27b (medium): complete 56-task paired coverage · 2026-09-11

**All 56 tasks were attempted three times under both conditions — with the task-pinned `plugin-upgrade` skill and with no Harbor-injected skill — for 336 trials total.** With-skill averages **0.4160** (69.89/168) with **55 perfect trials**; the no-skill arm averages **0.4494** (75.05/167) with **59 perfect trials**. The skill arm is therefore **-0.0334** lower, spends **+20.6%** more input tokens, takes **+6.2%** longer in summed native trial time, and produces **+22** more timeouts.

Both arms ran on the same frozen task/grader snapshot with the same agent, model, effort and timeout policy; the only difference is whether `skills/plugin-upgrade` was mounted. No trial was re-run to improve a score, and every retained anomaly is reported as-is with its grading status.

Motivated by [issue #102](https://github.com/oh-my-dsh/dsh-plugin-upgrade-skill/issues/102) — _use weaker, cheaper models for paired evaluation to restore benchmark discrimination and add a time/cost dimension_ — this run pushes both axes further than the published records: an **open-weight 27B model served locally on one GPU** (no provider bill at all) over the **full 56 tasks** with **three attempts per condition**. Because money cost is zero by construction, the cost of mounting the skill appears purely as wall time and tokens, which makes the skill-overhead question in #102 item 2 measurable without confounding it with provider pricing.

## Headline

- **The skill is a net negative on this stack.** Paired per task: with-skill better on 7 tasks, no-skill better on 18, identical on 31. The deficit concentrates in wall time and timeouts rather than in generated output (3,988,952 vs 3,940,227 output tokens, +1.2%).
- **Timeout is the dominant failure mode**: 108/168 (64.3%) with-skill and 86/167 (51.5%) no-skill trials ended in `AgentTimeoutError`.
- **19 of 56 tasks scored zero under both conditions** (H8, H9, H14-H19, H22, M5, M8-M12, S1, S3, S15, S17). Per-command forensics on H14-H19 show the agent spending the whole 900 s budget reading (52-101 commands, of which only 2-6 touch the graded fixture, and 12/18 trials make zero writes) — this is budget exhaustion, not an incorrect migration.
- **Two infrastructure defects were found and fixed during the round**, both of which had previously produced empty scores: codex remote compaction targeting endpoints vLLM 0.28.0 does not implement (H9/H22 trials now settle with zero timeouts and recorded scores), and a 32-character truncation of Harbor trial directory prefixes.

## Execution and provenance

- Frozen task/grader source: **`74af446`** with the documented local deltas (anti-cheat stripping, CRLF normalization, digest-pinned `FROM` rewritten to the shadow image). Note that `74af446` predates grader fixes merged to main afterwards for H8, M5, S5, S6 and S7, so scores for those five tasks reflect the pre-fix graders and are not comparable with future runs on the fixed graders.
- Codex CLI **0.153.4**; model `qwen3.8-27b` served locally by **vLLM 0.28.0** (`max_model_len=262144`, 1x NVIDIA H20 96 GB, BF16); **Harbor 0.22.0** manages containers and verification.
- Reasoning effort **medium** for every trial. `-k 3 -n 1` (three attempts per condition, single GPU, serial).
- `plugin-upgrade` mounted from the frozen snapshot; H11 and H21 use their task-pinned historical skill snapshots. No other skills, plugins, apps, memories or web search are injected.
- Environment build timeout multiplier **4**; per-task agent/verifier timeouts taken unchanged from each `task.toml`.
- Codex config: `model_max_output_tokens=16384`, `model_context_window=200000`, `model_auto_compact_token_limit=999999` (compaction disabled; see the infrastructure section below).
- Cost is **not** API-equivalent: inference ran on a local single-GPU deployment, so there is no provider bill. The comparable quantity is GPU wall time, reported below.

## Scores, tokens, time, and cost

| Condition | Reward | Mean | Perfect trials | Timeout trials | Input / cached input / output tokens | Summed native trial seconds | Round wall interval |
|---|---:|---:|---:|---:|---:|---:|---:|
| with-skill | 69.89/168 | 0.4160 | 55 | 108 | 409,819,928 / 400,036,000 / 3,988,952 | 110,458.754 | 115,899 s |
| no-skill | 75.05/167 | 0.4494 | 59 | 86 | 339,853,493 / 332,139,248 / 3,940,227 | 104,028.541 | 104,096 s |

Combined across both arms: **749,673,421 input / 732,175,248 cached input / 7,929,179 output tokens**, and **214,487.295 s** of summed native trial time. Cached input is already included in input; prefix-cache hit rates are 97.6% (with-skill) and 97.7% (no-skill).

### Timeout budget distribution

| Agent budget | Tasks | Representative tasks |
|---|---:|---|
| 300 s | 15 | H12, H4, S1-S3, S8-S17 |
| 600 s | 5 | H6, S4-S7 |
| 900 s | 34 | H1-H3, H5, H7-H8, H10-H11, H13-H25, M1-M14 |
| 18000 s | 2 | H9, H22 |

The 300 s tier is where the timeout wall bites hardest: 13 of the 17 S-series tasks run with it.

## Result distribution

| Task | with-skill | no-skill | with-skill timeouts | no-skill timeouts |
|---|---:|---:|---:|---:|
| H1-plane-trap | 1.00 | 1.00 | 3 | 1 |
| H10-browser-activation-trap | 1.00 | 1.00 | 0 | 0 |
| H11-dual-cohort-rpc | 1.00 | 1.00 | 0 | 0 |
| H12-remote-result-boundary-trap | 0.47 | 0.20 | 2 | 1 |
| H13-ghost-host-trap | 0.33 | 0.38 | 2 | 1 |
| H14-mineru-api | 0.00 | 0.00 | 3 | 3 |
| H15-locale-pack | 0.00 | 0.00 | 3 | 3 |
| H16-history-dock | 0.00 | 0.00 | 3 | 3 |
| H17-merge-calls | 0.00 | 0.00 | 3 | 3 |
| H18-blame-bubbles | 0.00 | 0.00 | 3 | 3 |
| H19-workspace-ya | 0.00 | 0.00 | 3 | 3 |
| H2-baseline-trap | 0.80 | 1.00 | 2 | 0 |
| H20-session-events-ledger | 1.00 | 1.00 | 0 | 0 |
| H21-question-answerer-waterfall | 0.33 | 0.63 | 3 | 3 |
| H22-dsh-data-agent-alpha2 | 0.00 | 0.00 | 0 | 0 |
| H23-storage-domain-version-compat-trap | 1.00 | 1.00 | 0 | 0 |
| H24-invalid-record-salvage-trap | 1.00 | 1.00 | 0 | 0 |
| H25-session-seed-boundary-trap | 0.80 | 0.77 | 0 | 0 |
| H3-client-plane | 0.67 | 1.00 | 3 | 3 |
| H4-tsbuildinfo-trap | 0.67 | 0.77 | 2 | 1 |
| H5-runtime-export-drift | 0.67 | 0.80 | 3 | 3 |
| H6-remote-error-trap | 0.67 | 0.00 | 1 | 0 |
| H7-locale-trap | 0.30 | 0.43 | 3 | 3 |
| H8-fire-drill | 0.00 | 0.00 | 3 | 3 |
| H9-dsh-web-alpha2 | 0.00 | 0.00 | 0 | 0 |
| M1-host-migration | 1.00 | 1.00 | 1 | 0 |
| M10-tools-tree | 0.00 | 0.00 | 3 | 3 |
| M11-sidebar-spur | 0.00 | 0.00 | 3 | 3 |
| M12-interpreters-card | 0.00 | 0.00 | 3 | 3 |
| M13-repository-plugins-removal | 0.90 | 0.93 | 2 | 1 |
| M14-service-renames-0812 | 0.93 | 0.60 | 0 | 0 |
| M2-optional-dep-trap | 0.67 | 1.00 | 2 | 1 |
| M3-session-projection | 1.00 | 1.00 | 1 | 0 |
| M4-peer-prerelease-range | 1.00 | 0.67 | 2 | 2 |
| M5-token-auth-smoke | 0.00 | 0.00 | 2 | 1 |
| M6-sleep-tool | 0.47 | 0.13 | 3 | 2 |
| M7-d399-overlay | 0.00 | 0.27 | 3 | 3 |
| M8-brand-text | 0.00 | 0.00 | 3 | 3 |
| M9-mcpanel | 0.00 | 0.00 | 3 | 3 |
| S1-static-scan | 0.00 | 0.00 | 3 | 3 |
| S10-paste-rename-and-version-chip | 0.00 | 0.33 | 3 | 2 |
| S11-mermaid-lazyload-trap | 0.00 | 0.27 | 3 | 2 |
| S12-global-upgrade-ebusy-trap | 1.00 | 1.00 | 0 | 0 |
| S13-peer-range-vs-runtime | 0.93 | 0.93 | 1 | 0 |
| S14-link-install-lock-trap | 0.27 | 0.87 | 3 | 1 |
| S15-slot-error-boundary-crash | 0.00 | 0.00 | 3 | 3 |
| S16-self-host-upgrade-trap | 0.00 | 0.27 | 3 | 2 |
| S17-external-ui-plugin-onboarding-trap | 0.00 | 0.00 | 3 | 3 |
| S2-negative-scan | 0.00 | 0.20 | 3 | 3 |
| S3-snapshot-migration | 0.00 | 0.00 | 3 | 3 |
| S4-legacy-client-imports | 1.00 | 1.00 | 0 | 0 |
| S5-negative-naming | 0.58 | 0.33 | 0 | 0 |
| S6-corridor-net-state | 0.23 | 0.23 | 0 | 0 |
| S7-unpublished-cohort | 0.28 | 0.33 | 0 | 0 |
| S8-release-routing-trap | 0.67 | 1.00 | 2 | 0 |
| S9-composer-coordinate-trap | 0.67 | 0.67 | 2 | 2 |

## Grading anomalies retained

- H8 and M5 report `verifier_result: null` in the Harbor job metadata while their verifier artifacts exist (`verifier/reward.json` with `score: 0`). Their rewards were recovered from the verifier artifacts; nothing was altered to recover points. The per-task CSV carries no grading-status column, so this recovery is documented here rather than in the CSV.
- **One trial out of 336 has no score at all**: H8-fire-drill no-skill `eUkk83R` failed with `VerifierTimeoutError: Verifier execution timed out after 600.0 seconds`, leaving an empty `test-stdout.txt` and no reward file. It is retained as unscored rather than imputed, which is why the no-skill denominator is 167 rather than 168. H8's other five trials all carry the verifier message below.
- H8's verifier message is `fixture unchanged relative to baseline` in all five graded trials: the agent never modified the graded fixture. The same message appears for H14-H19.
- H9 and H22 ran with automatic context compaction disabled after the infrastructure defect below was diagnosed. Their trials now settle with zero timeouts and recorded (zero) scores on both arms; the remaining exceptions are transport-level (`NetworkConnectionError` / `NonZeroAgentExitCodeError` / `ApiRateLimitError` — see the CSV), not compaction failures.

## Infrastructure defects found during the round

- **Codex remote compaction against vLLM 0.28.0.** Compaction v2 posts a `compaction_trigger` item to `/v1/responses`, which vLLM's renderer rejects with `KeyError: 'role'` (HTTP 500); disabling v2 instead posts to `/v1/responses/compact`, which returns 405. Setting `model_auto_compact_token_limit` above `model_context_window` disables auto-compaction entirely. Verified with a four-arm A/B/C/D experiment; only the disabled-compaction arm reaches `turn.completed`.
- **Harbor truncates trial directory prefixes to 32 characters**, so analysis scripts that rebuild the directory name from the task name silently skip `H23`, `S10` and `S17`.
- **Pausing the driver right after a job boundary cancels the next job's first trial** (`harbor/cli/jobs.py` raises `KeyboardInterrupt` from its SIGTERM handler), producing a one-second `CancelledError` trial. The stale directory was archived and the task re-run from scratch.

## Verification and evidence

- Completeness: **112/112 jobs** present with 3 settled trials each (checked by enumerating the expected 56 x 2 job set, not the existing directories).
- Per-task CSV companion: `validation-report-2026-09-11-codex-qwen3.8-27b-medium-paired.csv` (rewards, exceptions, summed seconds, tokens per task and condition).
- Provenance JSON companion: `validation-report-2026-09-11-codex-qwen3.8-27b-medium-paired.json` (protocol, per-round totals, wall intervals, per-task rewards/seconds/exceptions).
- Raw evidence (Harbor result.json files, agent sessions, verifier outputs) is retained on the contributor's host; credentials and native session logs are not included.

## Reproduction

```bash
# per-task pairing and round totals
bash ~/dsh-bench-scripts/analyze-medium.sh        # -> ~/dsh-bench/report/medium-analysis.{md,json}
# completeness check over the expected 112-job set
bash ~/dsh-bench-scripts/check-completeness.sh
# behavioural forensics (command counts, writes, first-write index)
bash ~/dsh-bench-scripts/strict-writes.sh H14-mineru-api H18-blame-bubbles
```
