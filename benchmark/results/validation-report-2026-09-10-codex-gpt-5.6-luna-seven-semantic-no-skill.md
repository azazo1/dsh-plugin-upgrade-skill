# Codex＋gpt-5.6-luna：七题无skill实跑（LLM评分）

2026-09-10，S1、S2、S3、S4、S10、S12、S15各重新作答一次。使用冻结的任务3.0.0及report-judge-v1评分协议，平均 **67.14/100**，总分470/700，2/7题满分。七次作答与七次评审均成功，无超时、无重试；全部fixture完整性检查通过。

## 结果

| 题目 | 分数 | 作答耗时 | 主要评分依据 | 答案 / 评分证据 |
|---|---:|---:|---|---|
| S1 | 45/100 | 165.3秒 | 找齐触点，但把类别序号当成A1-01至A1-07卡号；多项目缺少目标版本的迁移语义。 | [答案](artifacts/2026-09-10-luna-seven-semantic-no-skill/S1/touchpoint-report.md) · [逐项证据](artifacts/2026-09-10-luna-seven-semantic-no-skill/S1/judge.details.json) |
| S2 | 60/100 | 166.0秒 | 定位apiProxy，但未说明其确定的移除及正确迁移；六个负例类别的分析过于笼统。 | [答案](artifacts/2026-09-10-luna-seven-semantic-no-skill/S2/report.md) · [逐项证据](artifacts/2026-09-10-luna-seven-semantic-no-skill/S2/judge.details.json) |
| S3 | 10/100 | 279.2秒 | 报告明确承认缺少版本资料；没有给出所需的目标API、完整卡号和具体迁移路径。 | [答案](artifacts/2026-09-10-luna-seven-semantic-no-skill/S3/assessment.md) · [逐项证据](artifacts/2026-09-10-luna-seven-semantic-no-skill/S3/judge.details.json) |
| S4 | 75/100 | 129.5秒 | 四处触点及卡号正确；缺少客户端激活验证和内容顺序保持，各扣12.5分。 | [答案](artifacts/2026-09-10-luna-seven-semantic-no-skill/S4/report.txt) · [逐项证据](artifacts/2026-09-10-luna-seven-semantic-no-skill/S4/judge.details.json) |
| S10 | 100/100 | 258.7秒 | 粘贴命名、实时重名状态、旧缓存tag显示、回归和发布步骤均获认可。 | [答案](artifacts/2026-09-10-luna-seven-semantic-no-skill/S10/REPORT.md) · [逐项证据](artifacts/2026-09-10-luna-seven-semantic-no-skill/S10/judge.details.json) |
| S12 | 80/100 | 143.4秒 | 缺少安装后重启Host，在流程、精确命令两个项目各扣10分。 | [答案](artifacts/2026-09-10-luna-seven-semantic-no-skill/S12/report.md) · [逐项证据](artifacts/2026-09-10-luna-seven-semantic-no-skill/S12/judge.details.json) |
| S15 | 100/100 | 238.8秒 | busy作用域、短路触发、边界卸载、diff矛盾、修复与带数据回归均获认可。 | [答案](artifacts/2026-09-10-luna-seven-semantic-no-skill/S15/report.md) · [逐项证据](artifacts/2026-09-10-luna-seven-semantic-no-skill/S15/judge.details.json) |

S12的同一遗漏在两个现有项目中各扣10分，是本轮冻结评分标准的结果；本次未改权重、补答案或人工改分。

## 执行条件与审计

- 作答：Harbor 0.22.0，Codex CLI 0.153.4，`openai/gpt-5.6-luna`，`xhigh`，并发4，每题一次。原生轨迹的模型/推理档位与配置一致。
- 无skill：Harbor与Agent的`skills=[]`；`skills.include_instructions=false`、`skills.bundled.enabled=false`；额外指令禁止查找/读取/遵循任何skill。七题原生指令中`<skills_instructions>`均为0，目标及其他skill内容访问均为0。
- 审计器在S10、S12的native事件21各给出一条动态命令配对警告。人工对照实际执行事件，两者均是并行读取各自五个fixture文件的`sed`循环，未访问skill。完整命令与原生轨迹保留在本机归档，PR附上审计结果及人工核对说明。
- Agent时间限制保持原值：S4为600秒，其余300秒；环境/Agent安装不计入作答耗时。未提供网络搜索工具；S4保持no-network并仅为模型连接放行chatgpt.com，其余任务保持原public网络策略。
- 评审：Codex CLI 0.153.4，`gpt-6-astra`，`high`；每题一次。评审在空目录和临时配置中仅接收密封题面、fixture、参考摘录、评分标准与答案，工具/skill关闭；七次原生轨迹确认模型匹配，工具调用均为0。没有向评审提供标准答案文件。
- 评分先通过证据存在性、来源路径、项目齐全性检查，再由确定性代码按pass/partial/fail/missing及封顶规则计算；没有手工调整LLM判断或分数。

## 入口与复现边界

本轮用Harbor容器完成作答并导出候选fixture和报告，再通过现有宿主机Codex登录传输调用同一语义评审协议。Harbor内部verifier显式关闭，原始Harbor结果没有reward；上表分数来自独立保存的真实语义评审。它验证的是当前默认评分代码、密封材料和rubric，未把宿主机传输描述为默认Docker Chat Completions API的实跑。

Harbor即使关闭内部verifier仍会预检评审环境变量，本轮用不可连接的localhost:1和unused占位值通过该检查；它们未用于模型请求。实际评分通过独立Codex登录完成。

本轮从首个trial开始至最后评分结束共13.03分钟，其中Harbor作答作业（含安装、排队、收集）11.87分钟。作答累计输入1,407,941、其中缓存1,037,568、输出51,589 tokens；缓存数是输入的子集。

本次使用当前工作区的未提交评分改动，基线HEAD为`b49ccee20498cf8fe240d723b491d4de10b451f8`。冻结的110个文件SHA-256在运行结束后全部一致；每题导出的完整fixture文件集合及内容与密封基线一致。全部答案都是本次新生成，未复用此前四题答案。

每题只有一个样本。S1至S3需要版本专属卡号/API知识；本轮没有注入skill参考材料，低分也反映了这一信息条件。旧四题结果使用不同评分器，不能据此认定模型能力提升。

## 原始材料

- [结构化结果](validation-report-2026-09-10-codex-gpt-5.6-luna-seven-semantic-no-skill.json)：配置、模型、token、耗时、审计结果及制品哈希。
- 上表附七份原始答案和逐项评分证据；各题目录同时保存本次评分用的`packet.json`。S4答案仅把文件后缀改为`.txt`，避免容器内的`/app/fixture`链接被仓库Markdown校验当成坏链接，文件内容及SHA-256均未变。
- [零skill审计](artifacts/2026-09-10-luna-seven-semantic-no-skill/skill-audit.json)与[冻结来源](artifacts/2026-09-10-luna-seven-semantic-no-skill/provenance.json)保留配置与来源证据。
- 完整Codex事件、原生轨迹、请求/响应和启动日志保留于本机归档`/private/tmp/dsh-seven-luna-semantic-20260910`，也已在原工作区保存。本PR只提交核对得分所需的材料。
