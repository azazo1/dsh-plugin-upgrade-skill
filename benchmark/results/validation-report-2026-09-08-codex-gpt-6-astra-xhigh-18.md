# Codex + GPT-6 Astra xhigh: 18-task validation · 2026-09-08

A fresh, with-skill run of the 18 task IDs in the [Luna 18-task report](validation-report-2026-09-01-codex-gpt-5.6-luna-other-18.md) produced **15.40/18 reward (1540/1800; mean 0.855556)**, with **13 perfect tasks**. All 18 tasks ran once in new model sessions; there were no retries, exceptions, or verifier recoveries.

This is a fixed subset result, not a full 56-task evaluation or a paired skill-effect estimate. Task IDs were fixed before this run, following exploratory experiments; no earlier answers or rewards were reused, and no low-scoring task was rerun within this batch. The evaluated models received no previous answers, grader feedback, or historical result reports.

## Environment and execution

- Frozen task, grader, and skill source: `72267b6f83670d74965752aac525a989a5a0a1c0`.
- Answering harness: Codex CLI **0.153.4**, model `openai/gpt-6-astra`, reasoning effort **xhigh**. Harbor **0.22.0** launched containers and original verifiers.
- Only `skills/plugin-upgrade` supplied. Bundled skills, plugins, apps, memories, and web search disabled; skill instructions enabled; requested service tier `default`.
- Two workers, each running one trial at a time; maximum two concurrent agent phases. Each task retained its 1 CPU / 2 GiB resource limits.
- Agent/verifier timeout multipliers **2 / 2**; setup multiplier **4**; maximum retries **0**.
- Docker Desktop engine 28.5.1, Linux aarch64, 10 CPUs / 8,217,903,104 bytes available to Docker; macOS 26.6.2 host with 16 GiB RAM.
- Clean dependency/tool image layers were reused for 12 tasks and rebuilt for six. Tool/base/source equivalence checks were retained. Prior cache construction is excluded from this run's elapsed time; public package registries were not frozen.
- Native sessions verified model configuration, effort, CLI version, and target skill access for all 18 trials; no other skill was opened. Server-side routing and actual billing tier were not independently returned.

The run used Harbor's built-in `codex` agent with `version=0.153.4`, `reasoning_effort=xhigh`, `web_search=disabled`, `--skill` pointing to the frozen skill, and the timeout/retry settings above. A host-side evidence plugin captured fixtures, diffs, sessions, and skill access. Warm task copies changed image preparation, preserving the frozen task payloads and grading source. Each worker invoked one task per job (`--n-concurrent 1 --n-concurrent-agents 1`). Authentication used a local Codex subscription credential, excluded from the submitted data.

## Scores and resource accounting

| Metric | All 18 attempts |
|---|---:|
| Reward sum / mean | 15.40 / 0.855555556 |
| Input tokens | 19,624,263 |
| Cached input tokens (subset of input) | 18,362,368 |
| Output tokens | 189,414 |
| Reasoning tokens (subset of output) | 40,623 |
| Input + output tokens | 19,813,677 |
| Summed native Harbor trial duration | 7,319.282091 seconds |
| Summed model execution phases | 7,065.754629 seconds |
| Summed outer Harbor process duration | 7,356.735463 seconds |
| Wall time: manifest freeze to final attempt completion | 4,923.437882 seconds |
| API-equivalent answering cost | $40.452018 |

The native trial duration is computed from each trial `result.json` start/end timestamps, and remains additive across concurrent trials. Wall time runs from `2026-09-08T12:30:34.780743Z` to `2026-09-08T13:52:38.218625Z`; it excludes subsequent auditing and packaging. Host management-agent usage is excluded from answering-model totals.

Cost is an **API-equivalent estimate, not actual ChatGPT subscription billing**. The recorded 2026-09-08 [pricing source](https://developers.openai.com/api/docs/pricing) was applied per request: $10/M uncached input, $1/M cached input, and $50/M output. All requests were below the 272K input threshold; no explicit cache-write usage was reported. Cache and reasoning subsets are not added twice. Native cumulative usage, per-request usage, and Harbor token totals reconciled.

| Task | Score / 100 | Input | Cache subset | Output | Native trial seconds | API-equivalent USD |
|---|---:|---:|---:|---:|---:|---:|
| S1-static-scan | 100 | 544,145 | 464,768 | 10,956 | 378.656236 | 1.806338 |
| S2-negative-scan | 100 | 617,937 | 535,168 | 10,266 | 370.089648 | 1.876158 |
| S3-snapshot-migration | 100 | 929,725 | 829,696 | 14,186 | 492.896011 | 2.539286 |
| S4-legacy-client-imports | 100 | 103,603 | 88,832 | 4,365 | 188.513830 | 0.454792 |
| S5-negative-naming | 75 | 97,629 | 76,672 | 4,166 | 176.105084 | 0.494542 |
| S6-corridor-net-state | 50 | 96,843 | 65,664 | 3,767 | 158.626150 | 0.565804 |
| S7-unpublished-cohort | 25 | 143,257 | 101,504 | 7,782 | 298.535906 | 0.908134 |
| M1-host-migration | 100 | 1,321,084 | 1,229,056 | 10,429 | 428.786284 | 2.670786 |
| M2-optional-dep-trap | 100 | 684,941 | 632,704 | 7,868 | 324.930011 | 1.548474 |
| M3-session-projection | 100 | 1,204,109 | 1,128,192 | 10,447 | 407.748187 | 2.409712 |
| M4-peer-prerelease-range | 100 | 998,720 | 925,824 | 8,118 | 355.582772 | 2.060684 |
| H1-plane-trap | 100 | 1,432,133 | 1,328,256 | 9,716 | 387.894374 | 2.852826 |
| H2-baseline-trap | 100 | 1,569,678 | 1,466,880 | 14,419 | 574.537605 | 3.215810 |
| H3-client-plane | 100 | 4,139,527 | 4,006,144 | 20,851 | 824.438310 | 6.382524 |
| H4-tsbuildinfo-trap | 100 | 171,961 | 146,432 | 5,491 | 205.954219 | 0.676272 |
| H5-runtime-export-drift | 100 | 4,141,513 | 4,011,776 | 23,001 | 859.851457 | 6.459196 |
| H6-remote-error-trap | 0 | 142,537 | 126,336 | 4,727 | 191.593747 | 0.524696 |
| H7-locale-trap | 90 | 1,284,921 | 1,198,464 | 18,859 | 694.542260 | 3.005984 |

## Historical comparison on these task IDs

| Published with-skill record | Same 18 task IDs: mean score / 100 |
|---|---:|
| Astra xhigh, this run | 85.5556 |
| DeepSeek V4 Flash + terminus-2 | 84.4444 |
| Luna xhigh + Codex | 84.1667 |
| Terra xhigh + Codex | 79.7222 |

Historical values are filtered by these exact task IDs from the [frozen benchmark table](https://github.com/oh-my-dsh/dsh-plugin-upgrade-skill/blob/72267b6f83670d74965752aac525a989a5a0a1c0/benchmark/README.md), rather than comparing means over different task sets. Against Luna, 17 tasks tie and S6 increases from 25 to 50, for a mean difference of +1.3889 points.

This is the highest numerical result among these aligned records. Historical task/skill/grader snapshots have not been verified byte-identical to this run. Luna used a Node 24 installer adapter and different concurrency; Flash used terminus-2 with per-task medians of three runs. This single run therefore does not establish a controlled model ranking, statistical significance, or full-benchmark SOTA.

## Remaining failures and verification

The original verifiers awarded S5 75, S6 50, S7 25, H6 0, and H7 90; all other tasks scored 100. Scores were retained without manual correction. Report keyword checks and score caps are part of the frozen graders, so scores should not be interpreted as a percentage of useful work completed.

Two workers cross-checked execution/accounting, and the repository's `summarize-runs.mjs` independently reproduced the count and reward sum. All 284 frozen task-file hashes still matched. All 18 trials captured the seven requested evidence categories successfully. The official skill activation parser emitted 286 command-pairing/ambiguous-access diagnostics, preserved in local raw audit records; accounting audit errors and warnings were empty. Resource telemetry was sampled every 30 seconds and does not establish continuous peak usage.

Machine-readable [per-task CSV](validation-report-2026-09-08-codex-gpt-6-astra-xhigh-18.csv) and [summary/provenance JSON](validation-report-2026-09-08-codex-gpt-6-astra-xhigh-18.json) include exact token/time totals and native result SHA-256 hashes. The raw evidence archive (4,897 inventoried files) is retained locally by the contributor; its SHA-256 is recorded in the JSON. Raw sessions and credentials are not published by this PR.
