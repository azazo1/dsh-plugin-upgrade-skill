# H4 / H6 / H12：Codex + gpt-5.6-luna，无skill实跑

2026-09-12，三题各一次正式作答。作答模型gpt-5.6-luna，reasoning effort=xhigh，Codex CLI 0.153.4，Harbor 0.22.0，Docker隔离环境。

评分使用独立的Codex登录进程、同一模型gpt-5.6-luna、effort=high。这次没有测试独立Docker verifier的HTTP API传输。题目和version-3 rubric取本地工作区的冻结快照，运行过程中未调整。

| 任务 | 作答耗时 | 作答状态 | 有效评分 | 评分尝试 |
|---|---:|---|---:|---:|
| H4 | 124.19秒 | 完成 | 无：judge_error | 2 |
| H6 | 146.51秒 | 完成 | 无：judge_error | 2 |
| H12 | 157.23秒 | 完成 | 82.5/100 | 1 |

H4/H6均因评委引文无法逐字对应报告而被拒绝。实际不匹配包括合并换行、改变缩进和拼接表格行。第一次失败后，保持作答、模型和rubric不变，各重试一次；没有重跑或补写solver答案。两题不能计为0分，也没有可报告的三题总分或平均分。

## H12的扣分

- 修正实现12.5/25：正确检查了result.ok，但对gateway/cancelled仍建议重试。
- 错误判别5/10：正确否定instanceof并按code处理普通失败，但没有明确说明外层真实throw/catch边界应使用结构判别。
- 根因20/20、现有问题10/10、resolved控制流20/20、reject边界15/15。

以上为本次评委的有效判断，不代表独立人工标注结果。单次作答也不用于估计稳定平均能力；同模型独立评分仍可能存在自偏好。

## 无skill与边界核验

- Harbor skills为空；关闭Codex skill指令注入、bundled skills、宿主skill发现和skill搜索，并明确要求不读取skill。
- 三题原生轨迹均确认gpt-5.6-luna/xhigh；skill指令块均为0。H4/H6没有skill路径命令；H12三条匹配均是明确排除SKILL.md的glob或否定路径，逐条复核未读取skill。
- H4只删除lib/index.js和lib/tsconfig.tsbuildinfo，其他文件未变；H6/H12的fixture完全未改。
- 作答没有接触封存在独立评委输入中的参考资料与rubric；评委禁用工具、skill和历史，成功返回前执行原生轨迹审计。
- 冻结快照哈希复核无漂移。评分失败记录完整保留，未改动评分规则以放行引文。

## 证据

[机器可读结果与审计](artifacts/2026-09-12-luna-h4-h6-h12-semantic-no-skill/summary.json)、[冻结文件哈希](artifacts/2026-09-12-luna-h4-h6-h12-semantic-no-skill/provenance.json)、[归档文件哈希](artifacts/2026-09-12-luna-h4-h6-h12-semantic-no-skill/sha256.json)。

[H4作答](artifacts/2026-09-12-luna-h4-h6-h12-semantic-no-skill/H4/reports/report.md)、[H6作答](artifacts/2026-09-12-luna-h4-h6-h12-semantic-no-skill/H6/reports/migration-report.md)、[H12作答](artifacts/2026-09-12-luna-h4-h6-h12-semantic-no-skill/H12/reports/report.md)。仓库保留原始作答、solver-result、评委response、评分详情、packet和冻结评分器代码；grade-attempts目录保留首次失败输出。完整request、原生轨迹和命令审计保留本机，不纳入本PR。机器可读summary包含审计结论；冻结文件哈希记录完整本地快照，归档文件哈希仅列出本PR实际提交的文件。

## Token与整轮耗时

Harbor记录本轮从2026-09-12 16:49:47.379到16:55:11.081（Asia/Shanghai），三题并发，总耗时323.702秒（含环境准备、作答和产物收集；不含后续独立评委）。

| 任务 | 输入token | 缓存输入token | 输出token | 完整trial耗时 |
|---|---:|---:|---:|---:|
| H4 | 102,407 | 46,848 | 4,443 | 272.726秒 |
| H6 | 91,851 | 70,912 | 6,572 | 309.805秒 |
| H12 | 67,423 | 42,752 | 7,488 | 319.489秒 |

输入合计261,681，输出18,503，合计280,184 token；缓存输入160,512是输入的子集，不重复相加。完整trial耗时不同于前表的纯作答耗时。

原协议评委的5次尝试（含2次失败重试）另计：

| 任务/尝试 | 输入token | 缓存输入token | 输出token |
|---|---:|---:|---:|
| H4/1 | 5,877 | 0 | 1,832 |
| H4/2 | 5,879 | 0 | 2,443 |
| H6/1 | 8,323 | 0 | 4,126 |
| H6/2 | 8,323 | 0 | 3,205 |
| H12/1 | 8,330 | 0 | 6,502 |
