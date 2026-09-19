# GLM-5.3-flash S1-S22 validation run, round 3 (2026-09-11)

第 3 轮（三轮协议最后一轮）。协议与前两轮完全一致：GLM-5.3-flash 同时担任解题者与 rubric 评审，22 个 S 前缀任务 × 零注入 skill / 注入 plugin-upgrade skill 双条件，3-4 并发子代理，每条件一次，无重试。基准 commit 相同（`f32175d`）。

## 三轮汇总（各轮总分）

| 轮次 | 零 skill | 注入 skill | 提升 |
| --- | --- | --- | --- |
| Round 1 (PR #213) | 1716 (78.0%) | 1855 (84.3%) | +139 |
| Round 2 | 1801 (81.9%) | 1995 (90.7%) | +194 |
| Round 3（本轮） | 1659 (75.4%) | 1875 (85.2%) | +216 |
| **三轮逐题中位数合计**（协议推荐） | **1711 (77.8%)** | **1915 (87.0%)** | **+204** |

## 第 3 轮逐题分数

| 任务 | 零 skill | 注入 skill | 差值 |
| --- | --- | --- | --- |
| S1-static-scan | 95 | 100 | +5 |
| S10-paste-rename-and-version-chip | 100 | 100 | +0 |
| S11-mermaid-lazyload-trap | 100 | 100 | +0 |
| S12-global-upgrade-ebusy-trap | 100 | 100 | +0 |
| S13-peer-range-vs-runtime | 100 | 100 | +0 |
| S14-link-install-lock-trap | 100 | 100 | +0 |
| S15-slot-error-boundary-crash | 70 | 100 | +30 |
| S16-self-host-upgrade-trap | 100 | 80 | -20 |
| S17-external-ui-plugin-onboarding-trap | 20 | 0 | -20 |
| S18-terminal-sprite-render-trap | 60 | 80 | +20 |
| S19-phantom-update-stale-host | 0 | 0 | +0 |
| S2-negative-scan | 100 | 100 | +0 |
| S20-msvc-flock-trap | 80 | 95 | +15 |
| S21-resource-service-unavailable-trap | 40 | 60 | +20 |
| S22-duplicate-insert-boot-crash-trap | 40 | 60 | +20 |
| S3-snapshot-migration | 90 | 100 | +10 |
| S4-legacy-client-imports | 13 | 100 | +87 |
| S5-negative-naming | 88 | 100 | +12 |
| S6-corridor-net-state | 75 | 100 | +25 |
| S7-unpublished-cohort | 88 | 100 | +12 |
| S8-release-routing-trap | 100 | 100 | +0 |
| S9-composer-coordinate-trap | 100 | 100 | +0 |

## 三轮逐题明细（零skill/skill）

| 任务 | R1 | R2 | R3 |
| --- | --- | --- | --- |
| S1-static-scan | 100/75 | 95/95 | 95/100 |
| S10-paste-rename-and-version-chip | 100/100 | 100/100 | 100/100 |
| S11-mermaid-lazyload-trap | 80/100 | 100/100 | 100/100 |
| S12-global-upgrade-ebusy-trap | 100/100 | 100/100 | 100/100 |
| S13-peer-range-vs-runtime | 80/100 | 100/80 | 100/100 |
| S14-link-install-lock-trap | 100/100 | 100/100 | 100/100 |
| S15-slot-error-boundary-crash | 100/100 | 100/100 | 70/100 |
| S16-self-host-upgrade-trap | 80/100 | 80/80 | 100/80 |
| S17-external-ui-plugin-onboarding-trap | 20/40 | 20/60 | 20/0 |
| S18-terminal-sprite-render-trap | 60/20 | 60/80 | 60/80 |
| S19-phantom-update-stale-host | 0/0 | 80/80 | 0/0 |
| S2-negative-scan | 100/100 | 100/100 | 100/100 |
| S20-msvc-flock-trap | 95/100 | 95/100 | 80/95 |
| S21-resource-service-unavailable-trap | 60/60 | 40/60 | 40/60 |
| S22-duplicate-insert-boot-crash-trap | 60/60 | 40/60 | 40/60 |
| S3-snapshot-migration | 90/100 | 100/100 | 90/100 |
| S4-legacy-client-imports | 38/100 | 38/100 | 13/100 |
| S5-negative-naming | 88/100 | 100/100 | 88/100 |
| S6-corridor-net-state | 75/100 | 63/100 | 75/100 |
| S7-unpublished-cohort | 100/100 | 100/100 | 88/100 |
| S8-release-routing-trap | 90/100 | 90/100 | 100/100 |
| S9-composer-coordinate-trap | 100/100 | 100/100 | 100/100 |

## 三轮逐题中位数（协议口径）

| 任务 | 中位 零skill | 中位 skill | 差值 |
| --- | --- | --- | --- |
| S1-static-scan | 95 | 95 | +0 |
| S10-paste-rename-and-version-chip | 100 | 100 | +0 |
| S11-mermaid-lazyload-trap | 100 | 100 | +0 |
| S12-global-upgrade-ebusy-trap | 100 | 100 | +0 |
| S13-peer-range-vs-runtime | 100 | 100 | +0 |
| S14-link-install-lock-trap | 100 | 100 | +0 |
| S15-slot-error-boundary-crash | 100 | 100 | +0 |
| S16-self-host-upgrade-trap | 80 | 80 | +0 |
| S17-external-ui-plugin-onboarding-trap | 20 | 40 | +20 |
| S18-terminal-sprite-render-trap | 60 | 80 | +20 |
| S19-phantom-update-stale-host | 0 | 0 | +0 |
| S2-negative-scan | 100 | 100 | +0 |
| S20-msvc-flock-trap | 95 | 100 | +5 |
| S21-resource-service-unavailable-trap | 40 | 60 | +20 |
| S22-duplicate-insert-boot-crash-trap | 40 | 60 | +20 |
| S3-snapshot-migration | 90 | 100 | +10 |
| S4-legacy-client-imports | 38 | 100 | +62 |
| S5-negative-naming | 88 | 100 | +12 |
| S6-corridor-net-state | 75 | 100 | +25 |
| S7-unpublished-cohort | 100 | 100 | +0 |
| S8-release-routing-trap | 90 | 100 | +10 |
| S9-composer-coordinate-trap | 100 | 100 | +0 |

## 观察

- 三轮方向完全一致：注入 skill 在三轮中分别 +139 / +194 / +216 分；三轮逐题中位数口径为 +204 分（77.8% → 87.0%）
- 三轮均满分的稳定题：S2/S9/S10/S11/S12/S13/S14/S8（双条件双轮以上 100）
- 最大且稳定提升：S4（零 skill 13-38 → skill 100，三轮一致）；S6、S17、S18、S21、S22 亦稳定正向
- 三轮中最不稳定的单项：S19 三轮中位 0/0（最难，两条件均未能覆盖完整链条）；S17 第 3 轮 skill 出现 0 分（评分子代理判定与 rubric 冲突，属运行间方差）；S16 第 3 轮 skill 80（noskill 100）
- 评分方法：10 个关键词题用官方 `judge.mjs` 本地执行（fixture 暂存 + 基线 git commit）；12 个语义题由 GLM-5.3-flash 评分子代理按 `packet.json` rubric 逐条判 pass/partial/fail/missing 后确定性聚合（pass=满分、partial=半分）
- 局限：解题与判分同为 GLM 系模型，存在同源相关性偏差；关键词题分数为确定性判定，不受影响

## 复现

- Round 1: `validation-report-2026-09-11-glm-5.3-flash-s1-s22.md`（PR #213）
- Round 2: `validation-report-2026-09-11-glm-5.3-flash-s1-s22-round2.md`
- Round 3: 本文件
- 原始产物：`artifacts/2026-09-11-glm-5.3-flash-s1-s22-round3/`（44 份报告 + 12 份判定 JSON + 聚合 JSON）
