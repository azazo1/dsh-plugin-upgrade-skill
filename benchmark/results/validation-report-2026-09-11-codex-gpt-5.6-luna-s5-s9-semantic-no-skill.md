# Codex＋gpt-5.6-luna：S5–S9无skill实跑

2026-09-11，五题各重新作答一次，平均 **90/100**，总分450/500。五次作答与五次LLM评分均成功，没有超时或重试。使用本PR的任务3.0.0和report-judge-v1评分规则。

| 任务 | 得分 | 作答耗时 | 主要评分依据 | 证据 |
|---|---:|---:|---|---|
| S5 | 87.5 | 141.5秒 | 共享事件通道分析缺少发布者schema兼容性，以及同名本身不足以认定冲突的说明，扣12.5分。 | [答案](artifacts/2026-09-11-luna-s5-s9-semantic-no-skill/S5/report.md.txt) · [评分](artifacts/2026-09-11-luna-s5-s9-semantic-no-skill/S5/judge.details.json) |
| S6 | 62.5 | 122.8秒 | 正确删除旧字段剥离逻辑；对alpha.1语义、informational事件边界和公开append接口缺口说明不完整，各扣12.5分。 | [答案](artifacts/2026-09-11-luna-s5-s9-semantic-no-skill/S6/migration-report.md.txt) · [评分](artifacts/2026-09-11-luna-s5-s9-semantic-no-skill/S6/judge.details.json) |
| S7 | 100 | 112.2秒 | 未发布版本、caret实际解析、可行类型基线、锁定与后续升级方案均获认可。 | [答案](artifacts/2026-09-11-luna-s5-s9-semantic-no-skill/S7/installation-type-baseline-plan.md.txt) · [评分](artifacts/2026-09-11-luna-s5-s9-semantic-no-skill/S7/judge.details.json) |
| S8 | 100 | 187.3秒 | 缺失tag、宿主版本不兼容、v0.9.3先发布再安装、同步和文档路由均获认可。 | [答案](artifacts/2026-09-11-luna-s5-s9-semantic-no-skill/S8/report.md.txt) · [评分](artifacts/2026-09-11-luna-s5-s9-semantic-no-skill/S8/judge.details.json) |
| S9 | 100 | 247.8秒 | 坐标投影、重复粘贴失败、删除与记录一致性、转换和成功门控、回归序列均获认可。 | [答案](artifacts/2026-09-11-luna-s5-s9-semantic-no-skill/S9/report.md.txt) · [评分](artifacts/2026-09-11-luna-s5-s9-semantic-no-skill/S9/judge.details.json) |

## 运行条件

- 作答：Harbor 0.22.0、Codex CLI 0.153.4、`gpt-5.6-luna`、`xhigh`，并发4，每题一次。五题的原生轨迹均确认了模型和推理档位。
- 不带skill：任务和Agent的`skills=[]`，禁用原生skill指令、内置skill、宿主机skill发现、skill搜索和memory，并明确禁止读取任何skill。五题未注入skill指令块，轨迹审计未发现skill内容读取。
- S5–S7各600秒，保持no-network并只为模型连接放行chatgpt.com；S8–S9各300秒，保持原public网络策略。均禁用网络搜索工具。
- 评分：`gpt-6-astra`、`high`，每题一次。评审只接收密封题面、fixture、参考摘录、rubric和候选答案，未提供标准答案文件。评审的skill和工具关闭，原生轨迹中工具调用为0。
- S9有一条动态命令配对提示。复核原生事件19及实际命令后，确认它只是并行读取五个fixture文件，未访问skill。详见`audit-resolutions.json`。

## 时间和token

| 统计口径 | 输入token | 其中缓存 | 输出token | 耗时 |
|---|---:|---:|---:|---|
| 五题作答合计 | 529,720 | 402,176 | 35,191 | Harbor作业653.325秒（含安装、排队和收集） |
| 五次评分合计 | 40,086 | 0 | 10,049 | 与作答并行；从首个trial开始至最后评分完成734.228秒 |

缓存已包含在输入中，不重复相加。逐题作答时间来自Harbor的`agent_execution`，起止时间与token保存在结构化结果和各题`solver-result.json`中。

## 验证范围

容器中的Codex完成作答后，宿主机通过现有Codex登录调用同一LLM评分协议。Harbor内部verifier关闭，所以原始Harbor结果没有reward；上表采用独立保存的真实LLM评分，不是Docker内Chat Completions API评审的运行结果。

题面、fixture和评分材料运行前后哈希一致，五题导出的fixture也与密封基线一致。没有人工改分、补答案或看到结果后调整rubric。作答时的HEAD为`b49ccee20498cf8fe240d723b491d4de10b451f8`，本PR从更新的main整理，但五题实际使用的judge、packet、题面和fixture字节保持一致。

本轮每题只有一个样本。旧关键词评分与本轮语义评分不能混算；这些分数也不能单独证明skill效果或多次运行的稳定性。

## 保存的证据

- [结构化结果](validation-report-2026-09-11-codex-gpt-5.6-luna-s5-s9-semantic-no-skill.json)
- [零skill审计](artifacts/2026-09-11-luna-s5-s9-semantic-no-skill/skill-audit.json) · [实际配置](artifacts/2026-09-11-luna-s5-s9-semantic-no-skill/harbor/lock.json) · [冻结来源](artifacts/2026-09-11-luna-s5-s9-semantic-no-skill/provenance.json) · [文件哈希](artifacts/2026-09-11-luna-s5-s9-semantic-no-skill/sha256.json)
- 本次提交保留候选答案、逐项判断、packet、Harbor统计和审计摘要；完整原生轨迹与请求日志留在本地运行归档中。候选答案以`.md.txt`保存，内容未改写。
