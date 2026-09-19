# GLM-5.3-flash S1-S22 validation run, round 2 (2026-09-11)

第 2 轮运行，协议与第 1 轮（[round 1 report](validation-report-2026-09-11-glm-5.3-flash-s1-s22.md)，PR #213）完全一致：GLM-5.3-flash 同时担任解题者与 rubric 评审，22 个 S 前缀任务 × 零注入 skill / 注入 plugin-upgrade skill 双条件，3-4 并发子代理，每条件一次，无重试。基准 commit 相同（`f32175d`），两轮可配对比较。

## Headline

- 零 skill 总分：**1801 / 2200（81.9%）**（第 1 轮 1716 / 78.0%）
- 注入 skill 总分：**1995 / 2200（90.7%）**（第 1 轮 1855 / 84.3%）
- skill 提升：**+194 分（+8.8pp）**，方向与幅度与第 1 轮（+139 / +6.3pp）一致——两轮均支持注入 skill 有净收益
- 饱和题（双条件 100）：S2/S7/S9/S10/S12/S14/S15；最难题仍是 S19（两轮 noskill/skill 均未达 90）

## 分数表（第 2 轮）

| 任务 | R2 零skill | R2 skill | 差值 |
| --- | --- | --- | --- |
| S1-static-scan | llm-rubric | 95 | 95 | +0 |
| S10-paste-rename-and-version-chip | llm-rubric | 100 | 100 | +0 |
| S11-mermaid-lazyload-trap | official-keyword-judge | 100 | 100 | +0 |
| S12-global-upgrade-ebusy-trap | llm-rubric | 100 | 100 | +0 |
| S13-peer-range-vs-runtime | official-keyword-judge | 100 | 80 | -20 |
| S14-link-install-lock-trap | official-keyword-judge | 100 | 100 | +0 |
| S15-slot-error-boundary-crash | llm-rubric | 100 | 100 | +0 |
| S16-self-host-upgrade-trap | official-keyword-judge | 80 | 80 | +0 |
| S17-external-ui-plugin-onboarding-trap | official-keyword-judge | 20 | 60 | +40 |
| S18-terminal-sprite-render-trap | official-keyword-judge | 60 | 80 | +20 |
| S19-phantom-update-stale-host | official-keyword-judge | 80 | 80 | +0 |
| S2-negative-scan | llm-rubric | 100 | 100 | +0 |
| S20-msvc-flock-trap | official-keyword-judge | 95 | 100 | +5 |
| S21-resource-service-unavailable-trap | official-keyword-judge | 40 | 60 | +20 |
| S22-duplicate-insert-boot-crash-trap | official-keyword-judge | 40 | 60 | +20 |
| S3-snapshot-migration | llm-rubric | 100 | 100 | +0 |
| S4-legacy-client-imports | llm-rubric | 38 | 100 | +62 |
| S5-negative-naming | llm-rubric | 100 | 100 | +0 |
| S6-corridor-net-state | llm-rubric | 63 | 100 | +37 |
| S7-unpublished-cohort | llm-rubric | 100 | 100 | +0 |
| S8-release-routing-trap | llm-rubric | 90 | 100 | +10 |
| S9-composer-coordinate-trap | llm-rubric | 100 | 100 | +0 |

## 与第 1 轮逐题对照

| 任务 | R1 零skill | R2 零skill | R1 skill | R2 skill |
| --- | --- | --- | --- | --- |
| S1-static-scan | 100 | 95 | 75 | 95 |
| S10-paste-rename-and-version-chip | 100 | 100 | 100 | 100 |
| S11-mermaid-lazyload-trap | 80 | 100 | 100 | 100 |
| S12-global-upgrade-ebusy-trap | 100 | 100 | 100 | 100 |
| S13-peer-range-vs-runtime | 80 | 100 | 100 | 80 |
| S14-link-install-lock-trap | 100 | 100 | 100 | 100 |
| S15-slot-error-boundary-crash | 100 | 100 | 100 | 100 |
| S16-self-host-upgrade-trap | 80 | 80 | 100 | 80 |
| S17-external-ui-plugin-onboarding-trap | 20 | 20 | 60 | 60 |
| S18-terminal-sprite-render-trap | 60 | 60 | 80 | 80 |
| S19-phantom-update-stale-host | 80 | 80 | 80 | 80 |
| S2-negative-scan | 100 | 100 | 100 | 100 |
| S20-msvc-flock-trap | 95 | 95 | 100 | 100 |
| S21-resource-service-unavailable-trap | 40 | 40 | 60 | 60 |
| S22-duplicate-insert-boot-crash-trap | 40 | 40 | 60 | 60 |
| S3-snapshot-migration | 100 | 100 | 100 | 100 |
| S4-legacy-client-imports | 38 | 38 | 100 | 100 |
| S5-negative-naming | 88 | 100 | 100 | 100 |
| S6-corridor-net-state | 75 | 63 | 100 | 100 |
| S7-unpublished-cohort | 100 | 100 | 100 | 100 |
| S8-release-routing-trap | 90 | 90 | 100 | 100 |
| S9-composer-coordinate-trap | 100 | 100 | 100 | 100 |

## 评分方法（如实披露）

- 10 个关键词评分题（S11/S13/S14/S16-S22）：官方 `judge.mjs` 本地执行（fixture 暂存至判分器期望的 /app 根 + 基线 git commit），分数为官方确定性判定
- 12 个语义评分题（S1-S10/S12/S15）：GLM-5.3-flash 评分子代理按 `packet.json` rubric 逐条判 pass/partial/fail/missing，之后按官方聚合规则确定性算分
- 局限：解题与判分同为 GLM 系模型，存在同源相关性偏差；关键词题分数为确定性判定，不受影响
- 运行间方差实例：S13 第 2 轮 skill 条件 80（第 1 轮 100）——skill 报告对非命中面的展开论证被判 partial；S4 第 2 轮 skill 100（第 1 轮 100 持平）

## Artifacts

- `noskill/`、`skill/`：每题每条件的原始报告
- `scores/`：语义题判官逐条判定 JSON
- `aggregate.json` / `keyword-judge-scores.json`：机器可读总分

## Rounds

- Round 1: PR #213（validation-report-2026-09-11-glm-5.3-flash-s1-s22.md）
- Round 2: 本 PR
- Round 3: 待跑；三轮齐全后按官方 `summarize-runs.mjs` 配对中位数出最终汇总

## 真实模型校准

`calibrate.mjs --live` 仍需 `REPORT_JUDGE_*` 凭据；本批 `calibration/S11/S16/S17/S18/S19/S21/S22.md` 为参考答案占位，后续换真实模型校准文本
