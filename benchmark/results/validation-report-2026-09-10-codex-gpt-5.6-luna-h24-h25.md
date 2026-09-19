# H24/H25 · Codex + gpt-5.6-luna 实测 · 2026-09-10

修复后的两题各运行一次：**H24为100/100，H25为40/100，平均reward为0.70**。两题均完成模型作答和容器判分，没有trial异常或超时。相同任务快照上的标准答案对照均为100/100。

| 任务 | 模型得分 | reward | 模型执行时间 | 整个试次时间 | 标准答案对照 |
|---|---:|---:|---:|---:|---:|
| H24-invalid-record-salvage-trap | 100/100 | 1.00 | 1分41.598秒 | 3分31.927秒 | 100/100 |
| H25-session-seed-boundary-trap | 40/100 | 0.40 | 3分25.992秒 | 5分27.461秒 | 100/100 |

## 配置与范围

- Harbor 0.22.0、Codex 0.153.4、`openai/gpt-5.6-luna`、reasoning effort `xhigh`。两条轨迹均记录实际模型为`gpt-5.6-luna`。
- Docker Desktop 29.7.2，任务原有Node24镜像，两个并发试次，每题一次，无重试。整个模型job用时约5分28秒，包含环境安装和判分。
- 不注入Harbor skill；`skills.include_instructions=false`、`skills.bundled.enabled=false`；`web_search=disabled`。原始session日志中没有skill目录块，已完成的命令中未发现skill路径访问。
- 任务保留原有`network_mode="public"`；关闭搜索不等于容器断网。使用现有Codex登录，未将宿主机工作目录交给模型修改。
- 任务来自`codex/fix-h24-h25-grading`的未提交工作区，基底提交为`5724542b1bf072f5f9255a55b8ee3519854d2a52`，包括本轮H24/H25评分修复。运行开始前冻结了40个任务文件；运行期间未改评分器或任务。
- 使用临时`CodexNode24`适配器，仅把Codex安装过程改为复用镜像内Node24并安装固定CLI版本；模型调用、任务提示和验证流程沿用Harbor Codex agent。

## 得分解释

H24只修改了域声明，加入`invalidRecords: 'backup-and-skip'`，并运行题目指定的app确认可见记录为A、B。评分器确认健康记录完整、坏记录移入备份且字节不变、坏键在重建前不可见、重建后可重新打开读取。行为70/70、迁移20/20、依赖10/10。

H25的行为检查是**65/65**：新建和恢复会话的继承边界、普通会话、projection、合法和非法位置构造均通过。原始迁移分20/25、依赖10/10，合计95分，最终触发40分上限。

具体原因是模型写了`makeForkMeta(_cut) => ({ isSeeded: true })`，同时在`buildForkSession`和`resumeForkSession`中把`logOffset(cut)`作为第四个参数直接传给`Session.create`。所以会话本身没有丢失边界，但`makeForkMeta`的返回值没有携带继承计数。评分器在[judge-utils.mjs](../tasks/H25-session-seed-boundary-trap/tests/judge-utils.mjs#L247)据此封顶40分。

这暴露出一个需要澄清的独立helper契约：题目[handover note](../tasks/H25-session-seed-boundary-trap/environment/fixture/README.md#L11)要求`makeForkMeta(cut)`提供该fork的creation metadata，但未明确返回值必须独立携带`inheritedEventCount`。标准答案返回`{ meta: { isSeeded: true }, inheritedEventCount: SessionLogOffset(cut) }`；alpha.4的`SessionHeader`本身则只存`isSeeded`，确切边界是单独的会话状态。固定一手来源见[原题标准答案说明](../tasks/H25-session-seed-boundary-trap/solution/SOLUTION.md#first-party-provenance)，运行时验证使用原题锁定的`@deepseek-ai/dsh-session@0.1.2-alpha.4`。

因此，40分不能解释为“模型没有保留恢复边界”。模型确实让`makeForkMeta`忽略了`cut`；是否应因此重罚，取决于这个helper是否必须返回完整创建选项。建议先明确题目中的返回值契约，再评估封顶力度。本报告保留原始40分，没有按模型答案放宽评分或重跑择优。

## 记录与复现

[提交版结果与任务哈希](validation-report-2026-09-10-codex-gpt-5.6-luna-h24-h25.json)包含两题得分、逐项判分理由、模型与耗时、token用量和标准答案对照。它是原始结果的提取摘要，不是完整轨迹。

原始任务快照、配置、安装适配器和jobs保留在本机`/private/tmp/dsh-h24-h25-luna-20260910`，未随PR提交。模型job为`codex-luna-h24-h25-fixed`，标准答案job为`oracle-h24-h25-fixed`；各trial子目录的`verifier/test-stdout.txt`和`agent/codex.txt`分别保存判分日志与模型轨迹。

任务文件哈希清单`task-sha256.json`的SHA-256为`af7a10c42db712c32f2e8ae3a351c8953d71a3c32f614325d542f0c79b0244ab`。

在保留上述本机配置的环境中复现时，换一个新的job名称，避免覆盖本次记录：

```sh
PYTHONPATH=/private/tmp/dsh-h24-h25-luna-20260910 \
uv --cache-dir /private/tmp/dsh-h24-h25-harbor-cache tool run \
  --from harbor==0.22.0 harbor run \
  --config /private/tmp/dsh-h24-h25-luna-20260910/config.json \
  --job-name codex-luna-h24-h25-fixed-repeat -y
```

Harbor记录的总输入817,046 tokens，其中缓存输入696,832；输出11,843。缓存已包含在输入内。Harbor估算成本合计约$0.0522，仅为运行器估算，不是账单。

记录限制：Harbor把非秘密的`CODEX_FORCE_AUTH_JSON=true`开关值当作秘密处理，将日志和导出文件中的部分`true`替换成`[REDACTED]`，导致原始trial JSON含非JSON占位符，源码导出也受影响。原始记录未修改；摘要解析时仅将JSON值位置的占位符作为null处理，评分依据是verifier日志和reward文件。导出不存在的可选`/app/agent-output`目录时还有警告，源码和package.json已导出，评分未受影响。H24启动时模型列表刷新曾超时，但随后按指定模型完成了作答。

本次仅两题各一个试次，能验证这次运行结果，不能据此估计模型稳定通过率，也不是有无skill的配对比较。
