# Codex + GPT-6 Astra xhigh: complete 56-task coverage · 2026-09-09

**All 56 tasks were attempted once: 43.02/56 raw reward, conservative mean 76.8214/100, and 32 perfect tasks.** H8's grader failed while traversing an agent-created dangling symlink; its original zero is retained. The other **55 validly graded tasks average 78.2182/100**. The two denominators are reported separately, not substituted for one another.

This result combines the unchanged [initial 18-task run](validation-report-2026-09-08-codex-gpt-6-astra-xhigh-18.md) with 38 new tasks. It is complete coverage at the frozen commit, not a second fresh 56-task batch. No answer was rerun to improve its score.

## Comparison with published model records

Filtering Astra's complete results to each published bulk-run task set gives a higher numerical mean than each of the three existing model records:

| Published record / matched scope | Astra xhigh | Published model |
|---|---:|---:|
| Luna (19 tasks) | **84.5789** | 83.9474 |
| Terra (21 scored tasks) | **86.0476** | 79.7619 |
| Flash (23 tasks) | **82.9130** | 80.6522 |

Values come from the [frozen per-task benchmark table](https://github.com/oh-my-dsh/dsh-plugin-upgrade-skill/blob/72267b6f83670d74965752aac525a989a5a0a1c0/benchmark/README.md). The JSON companion lists every matched task and both rewards. Luna's 19-task row excludes its separately reported H22; Terra's 21-task scored set excludes its H8 verifier error; Flash's 23-task bulk row excludes its separate H21 calibration. **Astra's H8 error remains zero in the Flash comparison.**

Thus Astra leads these published records on their respective matched task sets. This does not establish a controlled full-56 SOTA claim: historical task/skill/grader snapshots and installers differ, Flash uses terminus-2 and three-run per-task medians, and this run measures no repeat-run variance. Astra's 56-task mean must not be ranked directly against other models' smaller-set means.

## Execution and provenance

- Frozen task/grader source: `72267b6f83670d74965752aac525a989a5a0a1c0`. Codex **0.153.4**, `openai/gpt-6-astra`, effort **xhigh**; Harbor **0.22.0** manages containers and original verification.
- With `plugin-upgrade` only; bundled skills, plugins, apps, memories, and web search disabled. Requested service tier `default`; provider-side routing/tier not independently confirmed.
- Main skill snapshot is the frozen commit above. H11 uses its task-pinned `7d33bf4c492da250c94f48aebd29bb16877d7a36`; H21 uses `5f7234ba4e00aeaa46c699ea32384389ad38a2a6`.
- Agent/verifier timeout multipliers **2 / 2**, setup **4**, automatic model retries **0**. Original per-task CPU/memory limits retained; maximum two concurrent models, 6 GiB reservation budget.
- Two workers originally received 19 continuation tasks each. After B finished its 19 tasks, unattempted H24 moved to B to overlap H22 within the unchanged budget. A completed H22 and exited through a planned gate, preventing duplicate H24. Actual continuation split: A 18, B 20.
- H24's delegated launcher first encountered host Python 3.9's missing `tomllib`, before creating any attempt or model call. It then used the original worker's Python 3.14.4. This is a zero-model launcher failure, not a second answer attempt.
- Continuation uses an ordinary independent clone at the frozen commit; no Git worktree was created. Host management context, earlier answers, and grading feedback were not supplied to test models.
- Of 38 continuation tool images, 22 were exact-ID reuses and 16 were rebuilt. Base IDs, tool hashes, full package lists, tool verification output, and frozen source hashes matched retained references. H9/H22 retained separate-verifier configuration. Public registries were not frozen.

## Scores, tokens, time, and cost

| Round | Raw reward | Input / cached input / output tokens | Native trial seconds, summed | API-equivalent USD |
|---|---:|---:|---:|---:|
| initial18 | 15.40/18 | 19,624,263 / 18,362,368 / 189,414 | 7319.282091 | 40.452018 |
| remaining38 | 27.62/38 | 70,192,595 / 66,709,120 / 580,957 | 26715.713174 | 130.591720 |
| Combined | 43.02/56 | 89,816,858 / 85,071,488 / 770,371 | 34034.995265 | 171.043738 |

Total input + output is **90,587,229 tokens**; reasoning output is **172,119**, already included in output. Cached input is already included in input. All model attempts are included, regardless of score or grading error.

- Initial wall interval: **4,923.437882 s**, 2026-09-08 12:30:34.780743 → 13:52:38.218625 UTC.
- Continuation wall interval: **16,623.663100 s**, 2026-09-09 01:18:21.299644 → 05:55:24.962744 UTC.
- Sum of round wall intervals: **21,547.100982 s (5h59m07.101s)**, excluding the overnight gap and final auditing/packaging.
- Summed native model-phase UTC intervals: **32,626.882939 s**; summed outer Harbor monotonic process times: **32,116.811146 s**. These are distinct from summed native trial durations and parallel wall time.

Host power logs confirm multiple lid-sleep episodes during continuation. UTC intervals include suspension; monotonic clocks differ. M8 warm preparation and M9/H8/M14 trial intervals or adjacent scheduling gaps were affected. H10 also waited **1,290.146458 s** for memory capacity before model execution. Original durations are retained without silently subtracting downtime; native phase intervals are not active-compute measurements. Idle-sleep inhibition was enabled later, but cannot prevent lid sleep.

Cost is **API-equivalent**, not actual subscription billing; management-agent usage is excluded. The frozen [pricing source](https://developers.openai.com/api/docs/pricing), retrieved 2026-09-08, is recorded in JSON. Per million tokens, short-context input/cache/output rates are $10/$1/$50 and long-context rates $20/$2/$75, applied per request above the 272,000-input threshold. Unique native requests and cumulative token totals were reconciled.

H16's Harbor metadata reports **$6.022538**, but 36 unique native requests cost **$5.857048** at frozen rates. Harbor counted one repeated `token_count` record as a second call, adding **$0.165490**. The combined estimate uses the deduplicated request total; original metadata remains unchanged.

## Grading anomaly and result distribution

H8 returned native zero after `readAgentText` traversed a dangling link under `link-install-node_modules`. Native answer logs show the model moved profile dependency directories into its output directory, invalidating relative symlink targets. The end-of-agent capture already contained the dangling links; Harbor artifact copying did not cause the defect. The frozen grader calls `statSync` before extension filtering and aborted before functional scoring. Re-running the unchanged verifier on the same output would reproduce the error. No links, answer files, or grader rules were altered to recover points.

The conservative 56-task score retains this zero; the 55-task valid-grading mean excludes it. All other tasks produced normal grades. M8–M12 and H15–H19 each scored 40 under static migration caps; H22 scored 11, H25 40, H20 99. The complete per-task table below preserves every original score.

| Task | Round | Score / 100 | Grading status |
|---|---|---:|---|
| S1-static-scan | initial18 | 100 | scored |
| S2-negative-scan | initial18 | 100 | scored |
| S3-snapshot-migration | initial18 | 100 | scored |
| S4-legacy-client-imports | initial18 | 100 | scored |
| S5-negative-naming | initial18 | 75 | scored |
| S6-corridor-net-state | initial18 | 50 | scored |
| S7-unpublished-cohort | initial18 | 25 | scored |
| S8-release-routing-trap | remaining38 | 100 | scored |
| S9-composer-coordinate-trap | remaining38 | 100 | scored |
| S10-paste-rename-and-version-chip | remaining38 | 100 | scored |
| S11-mermaid-lazyload-trap | remaining38 | 100 | scored |
| S12-global-upgrade-ebusy-trap | remaining38 | 100 | scored |
| S13-peer-range-vs-runtime | remaining38 | 60 | scored |
| S14-link-install-lock-trap | remaining38 | 100 | scored |
| S15-slot-error-boundary-crash | remaining38 | 100 | scored |
| S16-self-host-upgrade-trap | remaining38 | 100 | scored |
| S17-external-ui-plugin-onboarding-trap | remaining38 | 20 | scored |
| M1-host-migration | initial18 | 100 | scored |
| M2-optional-dep-trap | initial18 | 100 | scored |
| M3-session-projection | initial18 | 100 | scored |
| M4-peer-prerelease-range | initial18 | 100 | scored |
| M5-token-auth-smoke | remaining38 | 100 | scored |
| M6-sleep-tool | remaining38 | 100 | scored |
| M7-d399-overlay | remaining38 | 100 | scored |
| M8-brand-text | remaining38 | 40 | scored |
| M9-mcpanel | remaining38 | 40 | scored |
| M10-tools-tree | remaining38 | 40 | scored |
| M11-sidebar-spur | remaining38 | 40 | scored |
| M12-interpreters-card | remaining38 | 40 | scored |
| M13-repository-plugins-removal | remaining38 | 100 | scored |
| M14-service-renames-0812 | remaining38 | 100 | scored |
| H1-plane-trap | initial18 | 100 | scored |
| H2-baseline-trap | initial18 | 100 | scored |
| H3-client-plane | initial18 | 100 | scored |
| H4-tsbuildinfo-trap | initial18 | 100 | scored |
| H5-runtime-export-drift | initial18 | 100 | scored |
| H6-remote-error-trap | initial18 | 0 | scored |
| H7-locale-trap | initial18 | 90 | scored |
| H8-fire-drill | remaining38 | 0 | grader-error |
| H9-dsh-web-alpha2 | remaining38 | 67 | scored |
| H10-browser-activation-trap | remaining38 | 100 | scored |
| H11-dual-cohort-rpc | remaining38 | 100 | scored |
| H12-remote-result-boundary-trap | remaining38 | 75 | scored |
| H13-ghost-host-trap | remaining38 | 90 | scored |
| H14-mineru-api | remaining38 | 100 | scored |
| H15-locale-pack | remaining38 | 40 | scored |
| H16-history-dock | remaining38 | 40 | scored |
| H17-merge-calls | remaining38 | 40 | scored |
| H18-blame-bubbles | remaining38 | 40 | scored |
| H19-workspace-ya | remaining38 | 40 | scored |
| H20-session-events-ledger | remaining38 | 99 | scored |
| H21-question-answerer-waterfall | remaining38 | 100 | scored |
| H22-dsh-data-agent-alpha2 | remaining38 | 11 | scored |
| H23-storage-domain-version-compat-trap | remaining38 | 100 | scored |
| H24-invalid-record-salvage-trap | remaining38 | 100 | scored |
| H25-session-seed-boundary-trap | remaining38 | 40 | scored |

## Verification and evidence

Independent accounting audited all 38 continuation sessions and reconciled **$130.591720**, with no accounting errors. H8's grader error and H16's duplicate cost metadata are retained diagnostics. The official repository score summarizer reproduced 38 tasks / 27.62 reward. All 2,169 continuation task-file hashes and 127 skill files were checked; the sealed initial-18 result/manifest/archive hashes remained unchanged.

[Per-task CSV](validation-report-2026-09-09-codex-gpt-6-astra-xhigh-full56.csv) contains token, time, cost, grading status, and native result hashes. [Summary/provenance JSON](validation-report-2026-09-09-codex-gpt-6-astra-xhigh-full56.json) contains both round totals, exact matched historical comparisons, pricing, and SHA-256 hashes for the two raw evidence archives. The continuation archive's 18,315 content hashes were verified, including tar hard-link entries. Raw evidence is retained locally by the contributor, not publicly hosted by this PR; credentials and native sessions are not included in the submitted compact data.
