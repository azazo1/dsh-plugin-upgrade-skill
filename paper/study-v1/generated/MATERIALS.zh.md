# 四条件候选材料清单

**状态：候选，未冻结；没有启动 solver。**

来源提交：`a43afbea03fe1e4a22eba304c66847c3f99a9890`。保留 56 个候选成员。

| 资料版本 | 使用任务 | 引用文件数 | A/B/C/D 字节数 | C/D 事实等价 |
|---|---|---:|---|---|
| `5f7234ba4e00` | H21-question-answerer-waterfall | 7 | 207 / 5486 / 95033 / 97562 | 待审核 |
| `7d33bf4c492d` | H11-dual-cohort-rpc | 11 | 207 / 5486 / 216249 / 219674 | 待审核 |
| `a43afbea03fe` | 默认（其余 54 题） | 24 | 207 / 5486 / 541396 / 544821 | 待审核 |

字节数不是 token。C/D 适配后的 references 与事实补充逐字相同；D 使用去掉版本摘要和缺失 helper 指令的纯文档流程。适配差异记录在 manifest，不能称原版完整 skill。

## 仍需审核

- document-only adaptation completed; actual tool/runtime feasibility requires isolated pilot
- task QC and behavioral endpoint separation incomplete
- final model/serving/scaffold and resource limits unset
- repetition/statistical/grouping protocol not frozen
- runner material-mount/network/native-catalog isolation not validated

## 提示变化

全部候选题附加相同 BENCHMARK-MATERIALS-v1；下列原有闭卷冲突句被替换：

- `H6-remote-error-trap`
- `S4-legacy-client-imports`
- `S5-negative-naming`
- `S6-corridor-net-state`
- `S7-unpublished-cohort`

原任务、fixture、grader 未修改。改写后的提示必须用于新跑，不能靠重评旧答案模拟新提示。

## 文件边界

每个 arm 根目录才是 solver 材料；总包的 manifest、prompt 索引和 review 文件不得一起挂入 solver。
外链及未供应的 scripts/examples 链接不授予访问权，完整清单在 material-manifest.json 的 unavailableLinks。
