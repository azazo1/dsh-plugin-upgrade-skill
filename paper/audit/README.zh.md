# 实验与开发暴露账本

核对日期：2026-09-08；来源 checkout：`72267b6`。本轮读取已提交报告与 git 历史，没有重新运行模型、读取所有外部 runner 原始轨迹，也没有追认正式测试资格。

- [实验账本](experiment-ledger.csv)：覆盖当前 `benchmark/results/validation-report-*.md` 的 **22 份报告**，记录报告 SHA-256、范围、条件、重复、配置、评分/隔离边界及主表纳入意见。
- [任务暴露账本](task-exposure-ledger.csv)：覆盖当前 **56 个 task.toml**，记录明确调优/评分开发证据、v1 knowledge-holdout 分类及暂定角色。
- [原参考文献备份](bibliography-before-revision.bib.txt)：保留未核实的旧 stub 和模板引用，避免把“本轮未确认”误写为“不存在”。它不再参与论文编译。

`unknown in this ledger` 表示本轮尚未整理到足够证据，不代表原始材料必然缺失。CSV 中的 `benchmark_commit_reported` 是报告声明，不是已核验的完整 fixture/patch manifest。报告 SHA-256 只标识读取的报告版本，不能代替 trial 产物哈希。

## 现在可以复用什么

| 证据 | 当前可用范围 | 进入新主实验前的条件 |
|---|---|---|
| Flash 23-task 配对 | 有逐任务重复分数的历史候选；H8 skill 组只有两次 scored | 恢复产物、核对实际代码+H7补丁/skill hash、统一重评与资料隔离审计 |
| Terra 22-task 双臂 | 21 个 scored 任务的历史配对候选 | 核对 paired 交集和版本；保留 H8 缺失敏感性分析；不能把缺失静默当 0 |
| Luna 19-task | with vs no-injected 的历史对比 | native skill 影响必须披露；不能复用成 literal-zero 对照；精确 commit 未记录不能事后伪造 |
| Luna H22 | 同项目单次双臂的负面案例 | 8/100 与 11/100 均未进入 runtime gate；不代表代码成功运行 |
| Opus interim | 15 个完整三次双臂的描述结果 | 其余格和 native-catalog 审计未完成，不代表整个 23-task 集合 |
| H21 Flash | public-network 校准 | 正式隔离条件需要重新运行，不能因 skill 冻结就改称 closed-book 正式结果 |
| metadata A/B | primary endpoint 为 opened：两臂均 2/3，零效应 | 原始临时轨迹已删除，仪器代码相同不等于原始观测可重审；作为带限制的 pilot |
| static-20 | 修正后的 18-pair 本地描述 | S3 模型不配对、H13 环境无效已排除；存在任务演进/可达答案目录与估算成本 |
| three-system | skill 和 grader 开发轨迹 | 不当独立 test；GLM with 减 flash baseline 的 +0.17 不当 skill gain |
| S1–S4 pilot/R2 | 语义评分工具与 oracle/rubric 校准证据 | 需同 rubric 双臂重评、独立人工答案与一致率；oracle 满分不是信度证明 |

**没有任何一行在本轮被认定为新的独立四条件测试结果。** 历史可比结果不必丢弃，可作为明确标注的 retrospective/open-book 结果，前提是恢复证据并修正评分问题。

## 明确的反馈暴露链

`6960502d870c4d2e9f551f7514d7c0c769585f4a`（2026-09-06 05:12:30 +08:00）的提交说明明确记载 precision checklist / inject lint 来自多轮配对评测反馈。

| 当前任务 | 报告中的轮次 | 已知反馈用途 |
|---|---|---|
| M6-sleep-tool | R1/R2 | caret、inject、引用与落盘要求 |
| M7-d399-overlay | R2 | 落盘/扫描纪律；报告称达到满分 |
| H4-tsbuildinfo-trap | R3 | 只读任务例外 |
| M9-mcpanel | R6 | renderer/slots 规则 |
| M8-brand-text | R7/R8 | wiring 与重复运行 plateau 检查 |
| M10-tools-tree | R7/R8 | 同上 |

来源：[three-system 报告](../../benchmark/results/validation-report-2026-09-06-three-system-paired-eval.md)。报告未提供每轮完整 skill hash、精确时间和所有受影响任务；上表是已确认下限，不能认为其他任务无污染。

随后 `fc84138366ba2905bb87cf893f25198e96bfc5e4`（2026-09-06 10:22:46 +08:00）又修正 checklist/lint 的类型与 runtime injection、HTTP auth 等规则。初始 addition 与当前最终包不能视作同一个 skill；git 导入时间也不等于最早反馈发生时间。

此外，M5/M11/M12/H8 有评分缺陷反馈；S1–S4 有 semantic rubric/oracle 校准；portfolio 的历史 H11/H12/H13/H14 对应当前 H16/H17/H18/H19，有本地试考后的 grader 修订。它们属于已观察开发证据，但不能无证据地升级成“全部直接调优了 skill”。S16 报告声明由该次运行事件构造，也不适合作为同一开发过程的前瞻独立测试。

## 如何使用任务状态

- `confirmed-skill-feedback`：明确任务反馈参与 skill 修订，暂归 dev。
- `confirmed-grader-development`：观察过答案/失败并修改或排查 grader，暂归新版评测开发；不据此推断具体 skill 修改。
- `evaluation-sourced-incident`：任务由该轮评测事件产生，暂归 dev。
- `exposure-not-cleared`：未完成研究者暴露审计，不是“未见”。source_reports 可能只是提及，须逐项判断是否真有运行/反馈。

v1 中 `clean-holdout` 仅表示冻结 skill 的核心知识缺失。H4 同时是 clean knowledge holdout 与已确认调优任务，这两个状态并不矛盾，也说明为何需要两套审计。

**下一步**：维护者补每轮 skill/任务 hash、外部 runner 持久归档位置、未写入报告的调优记录；按事件族确认 split；再冻结新的正式 manifest。当前 CSV 的 incident_family 故意保持 pending，不能凭任务前缀或本轮猜测冻结测试集。

## 引用核实范围

本轮只对正文实际使用的五项文献核对标题、作者、年份、arXiv 版本及摘要所支持的概括。不是完整相关工作综述或全文协议比对。

- [SkillsBench v1](https://arxiv.org/abs/2602.12670v1)：当前正文引用其早期配对/确定性验证框架，不混用新版规模；[v4](https://arxiv.org/abs/2602.12670v4) 已存在，最终综述仍应核对最新版全文。
- [SWE-Skills-Bench v1](https://arxiv.org/abs/2603.15401v1)：执行验收测试、效果异质性及版本不匹配退化。
- [VersiCode v2](https://arxiv.org/abs/2406.07411v2)：版本特定补全与版本感知迁移。
- [CODEMENV v1](https://arxiv.org/abs/2506.00894v1)：兼容性、定义变化、跨环境适配；本轮引用 arXiv 版本，不伪造会议页码。
- [Indirect Prompt Injection v2](https://arxiv.org/abs/2302.12173v2)：外部数据中的指令可影响 LLM 应用。

旧稿中的 Skill-Use、Agent Skills Can Be Harmful、ContinualSkillBench、ReCode 等未确认条目已退出正文引用，保留在备份中待后续系统核实。
