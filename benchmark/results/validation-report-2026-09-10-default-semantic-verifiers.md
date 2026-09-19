# 七题默认LLM评审入口验证 · 2026-09-10

S1、S2、S3、S4、S10、S12、S15的注册任务已默认使用`report-judge-v1`语义评分，任务版本更新为`3.0.0`。直接运行`benchmark/tasks/<task>`即可，无需生成或启用pilot。需要配置独立验证容器的`REPORT_JUDGE_BASE_URL`、`REPORT_JUDGE_MODEL`和`REPORT_JUDGE_API_KEY`；不存在关键词回退。

本次修改保持题面、fixture、参考答案和agent时限不变。共享实现、语义标准及冻结证据生成七份独立评分器，CI校验副本和题目材料没有失步。S10题面明确不计分的扩展名/MIME及显示路径细节不再成为得分条件；S15允许基于实际diff指出额外作用域错误或材料矛盾。评分按语义接受同义词、否定句、跨段步骤和测试代码。

## 已完成的验证

- `npm test`全仓检查通过，包括35项报告评分协议及默认入口测试。
- 七题独立`tests/test.sh`入口的单元测试确认：实际调用LLM传输接口；无配置、HTTP失败时非零退出且不留reward；精确照抄题面为0；引用题面后追加独立答案仍交给LLM判断。
- 同步检查能检测题面、fixture、参考资料及评分器副本漂移；篡改、删除和新增fixture文件均由冻结哈希检查处理。
- Harbor 0.22.0 / Docker Desktop 29.7.2实际运行15个试次，全部完成，无试次异常，全部使用独立验证容器。

| 容器对照 | 数量 | 预期 | 实际 |
|---|---:|---:|---:|
| 标准答案＋本机模拟API | 7 | reward=0.5 | 全部0.5 |
| NOP空作答 | 7 | reward=0，不请求API | 全部0，无新增请求 |
| S12临时副本故意修改fixture | 1 | invalid_submission，reward=0 | 符合，无新增请求 |

模拟API只监听本机回环地址，故意返回所有方面`partial`，用于验证请求、证据校验、分数汇总及容器数据流。这些50分是协议测试值，**不是LLM语义评分，也不是标准答案质量结论**。累计API请求恰好7次；空报告和fixture篡改均在请求前处理。

S12篡改对照只改临时任务的solution脚本，使其在作答后修改`npm-dist-tags.txt`。默认验证容器收到该修改并判0，证明验证过程没有拿初始fixture覆盖候选内容。仓库内原题与参考答案未改动。

## 耗时与未覆盖范围

以下是Harbor job记录的整轮耗时，各轮内部存在并发，不能把单个trial时长相加当成总耗时。

| 轮次 | 试次数 | 整轮耗时 | Token |
|---|---:|---:|---|
| default-entry-protocol-oracle | 7 | 53.705秒 | 不适用：无模型请求，Harbor未记录token |
| default-entry-protocol-nop | 7 | 53.340秒 | 不适用：无模型请求，Harbor未记录token |
| default-entry-tampered-fixture | 1 | 12.004秒 | 不适用：无模型请求，Harbor未记录token |

这15个试次验证的是评分入口和容器数据流，没有调用真实模型。后续已完成七题Luna无skill作答及Astra评分，见[实跑报告](validation-report-2026-09-10-codex-gpt-5.6-luna-seven-semantic-no-skill.md)。完整的关键词、错误答案、注入等反例校准矩阵尚未实跑，不能据此声称攻击拦截率或评审准确率。

API与Codex传输沿用同一评分标准及证据校验，但尚未做同答案配对，不应直接认为二者给分完全一致。

## 证据

[结构化验证结果](validation-report-2026-09-10-default-semantic-verifiers.json)包含15个试次的判分明细、评分器和rubric哈希。本机原始配置、冻结任务和日志位于`/private/tmp/dsh-semantic-defaults-20260910`；全仓测试日志为其中的`npm-test.log`。

维护和运行方式见[默认语义评分说明](../docs/report-judge-pilot.md)。此前四题的关键词评分及Luna原始答案保留在[历史运行报告](validation-report-2026-09-10-codex-gpt-5.6-luna-s1-s10-s12-s15-no-skill.md)，没有覆盖或改分。
