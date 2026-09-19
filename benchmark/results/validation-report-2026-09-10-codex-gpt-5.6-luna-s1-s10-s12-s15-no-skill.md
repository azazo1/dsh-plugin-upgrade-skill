# S1 / S10 / S12 / S15 · Codex + gpt-5.6-luna · 无 skill 实测

2026-09-10使用修复后的工作区评分器，每题运行一次：**S1=0、S10=0、S12=20、S15=40，原始平均分15/100**。四题均正常完成，无试次异常、超时或重试；同一任务快照的标准答案对照均为100/100。

**这轮也证实评分器修复还不完整。** S1确实编造了卡号映射，但S10、S12、S15多处正确分析被新的正则和段落边界漏判。下表保留机器原始分数，没有人工改分或修改评分器后择优重跑；这些分数不能直接用来评价模型的解题能力。

| 任务 | 原始得分 | 模型执行时间 | 整个试次时间 | 标准答案 |
|---|---:|---:|---:|---:|
| S1-static-scan | 0/100 | 214.499秒 | 441.248秒 | 100/100 |
| S10-paste-rename-and-version-chip | 0/100 | 244.867秒 | 402.229秒 | 100/100 |
| S12-global-upgrade-ebusy-trap | 20/100 | 137.225秒 | 344.689秒 | 100/100 |
| S15-slot-error-boundary-crash | 40/100 | 223.724秒 | 429.734秒 | 100/100 |

四个试次并发，模型job总耗时441.334秒，约7分21秒。模型执行时间包含Codex启动和调用过程；整个试次时间另外包含容器构建、安装和验证。时间重叠，不能把四行相加作为实际等待时间。

## 运行条件与无 skill 核验

- Harbor 0.22.0，Docker Desktop 29.7.2，Codex 0.153.4，`openai/gpt-5.6-luna`，推理档位`xhigh`。四份原生session的实际模型和档位分别均为`gpt-5.6-luna`和`xhigh`。
- 不传入Harbor skill，agent的`skills`数组为空；Codex配置为`skills.include_instructions=false`、`skills.bundled.enabled=false`，并附加只约束执行边界的禁止读取skill指令。
- 四份原生session均没有`<skills_instructions>`块。仓库审计器记录目标skill及其他skill内容读取均为0/4；另行核查完成的命令，未发现skill文件读取。S1和S10有7条命令提到skill，均用于排除路径。S1的fixture README本身提到原始skill示例路径，审计器因此记录了discovered，但没有opened。
- 审计器对S12的一条动态命令产生配对警告。人工检查该条调用及实际执行记录，确认只是并发读取fixture的README、两份终端日志、进程列表和dist-tags，没有访问skill。
- 关闭provider web search。容器仍保留题目原有的`network_mode="public"`；这不是网络物理隔离。题目继续禁止模型访问外部服务。
- 保留原题每题300秒的agent限时和120秒的verifier限时，setup倍率为4；每题一次，无重试。安装适配器只复用镜像内Node24并安装固定Codex版本，任务提示和评分流程沿用Harbor。
- 四题均通过只读检查；导出的fixture全部与输入fixture逐文件、逐字节一致。

## 答案与评分器的具体分歧

### S1：卡号确实错误，扫描覆盖也被漏计

[完整答案](artifacts/2026-09-10-luna-s1-s10-s12-s15/S1.md)把七类触点依次对应到`A1-01`至`A1-07`，没有证据支持这种编号规则。例如源码补丁应该对应`A1-03`，apiProxy应该对应`A1-01`，回环鉴权应该对应`A1-08`；事件折叠还缺少`A2-01`。这些是实际答案错误。

不过，答案已列出全部扫描文件和七类触点。评分器要求“扫描”与`package.json`、源码路径出现在同一文本单元中，答案用项目列表列文件，因此“扫描范围和七类全部命中”这10分也被漏判。原始0分不等于答案没有完成扫描。

任务环境没有提供卡片目录；在本次无skill条件下，模型搜索非skill文档后仍直接假定卡号。这既是模型未标明证据缺口的问题，也使该任务的精确卡号得分依赖本次未提供的资料。

### S10：关键设计已给出，五个方面全部漏判

[完整答案](artifacts/2026-09-10-luna-s1-s10-s12-s15/S10.md)提出从未编号名字开始寻找第一个可用序号，使用实时`input.state.getSnapshot().occurrences`建立占用集合，并解释了records在瞬时空快照下被删除的原因；也明确区分粘贴、拖拽和选择器路径。

版本规则用伪代码表达为`remote > local`显示远端更新、`remote <= local`显示本地运行版本。回归测试要求同一批三个`image.png`成功获得不同名字；发布检查要求同步包版本和内联常量、检查分发文件语法并更新用户实际安装的文件。这些内容仍分别被判为缺失。

主要问题是评分器依赖特定词序和词汇：例如寻找空闲序号要求出现collision/occupied附近的increment，用`remote > local`表达更新条件不算命中，三个不同名字的成功用例未使用coexist一词，包元数据未写成字面`package.json`也不算同步。

另有一个与本次模型答案无关的评分契约问题：S10题目末尾明确说第2项扩展名/MIME及显示路径不计分，但修复后的首个20分方面把它们设为必要条件。评分器与题面仍不一致。

### S12：否定句被反向识别，步骤和README建议被段落切分漏判

[完整答案](artifacts/2026-09-10-luna-s1-s10-s12-s15/S12.md)指出PID 42432的dsh宿主加载了原生模块，Windows在宿主退出前保持文件占用，浏览器刷新不会卸载模块；给出先确认和停止该宿主、再安装固定alpha.5和TUI、核对版本并重新启动的顺序。

评分器把“An unpinned install does not preserve the currently installed version”判成了“unpinned install preserves installed version”的矛盾建议。当前否定处理只看正则匹配片段前后的边界，未识别匹配片段内部的`does not`。

“文件一直被占用直到宿主退出”没有用lock一词，步骤之间插入了命令块，README总领句与Pin条目分开，也分别导致漏判。原始20分只来自精确安装命令这一项。

答案本身也有一个版本笔误：解释降级时写成替换已安装的alpha.5，而题面初始版本是alpha.4，日志没有证明期间已成功升级到alpha.5。因此不能简单宣称该答案全部正确。

### S15：作用域、复现和渲染测试都存在，仍扣掉60分

[完整答案](artifacts/2026-09-10-luna-s1-s10-s12-s15/S15.md)明确写出`busy`属于`AttachButton`局部状态、未在`AttachmentChips`声明，解释空occurrences提前返回以及plain阶段导致`||`右侧求值，指出错误发生在旧版本同一表达式。

答案还给出了旧版本带数据的最小渲染、回退hover后的复现方法、修复和防御读取，以及包含`phase: 'plain'`和一个occurrence的测试代码，断言chip存在且错误边界没有捕获异常；也说明未解析的标识符仍是合法语法，`node --check`不会执行组件。

这些被漏判的直接原因包括：`not declared`不在作用域检查接受的表达中，`roll back`与`fails`未被复现正则接受，代码测试里的`expect`没有满足指定的assert文本形式，空状态和语法限制的自然表述不匹配固定词组。仅错误边界解释、修复和防御读取两项获得40分。

## 来源、资源与复现

[结构化结果](validation-report-2026-09-10-codex-gpt-5.6-luna-s1-s10-s12-s15-no-skill.json)保存逐项判分理由、任务及答案SHA-256、用量、耗时、配置、标准答案对照和skill审计。四份答案随本报告保存，均从原始trial导出文件直接复制，没有改写。

任务取自`codex/fix-h24-h25-grading`当前未提交工作区，基底提交为`b49ccee`，包含本轮S1/S10/S12/S15修复。运行前冻结72个任务文件；运行结束后核验快照和工作区文件均未变化。任务文件哈希清单的SHA-256为`49e1d4ec46a499d6b3b9acf6539dbeba1b550826cca234ac16c0241c54e67a16`。

原始任务快照、安装适配器、配置、完整session、作答与verifier日志保存在本机`/private/tmp/dsh-s1-s10-s12-s15-luna-20260910`。模型job为`codex-luna-s1-s10-s12-s15-literal-zero-skill`，标准答案job为`oracle-s1-s10-s12-s15-fixed`。各trial的`verifier/test-stdout.txt`是判分依据，`agent/codex.txt`和`agent/sessions/`保存轨迹。

模型job记录输入657,102 tokens，其中缓存550,656；输出33,944；输入加输出691,046。缓存已包含在输入内。Harbor估算费用约$0.0730，为运行器记录而非账单。四个试次都出现模型列表刷新超时提示，但随后按指定模型正常完成，没有对应的trial异常。

在上述本机文件仍存在的环境中，可换一个新job名称复现：

```sh
PYTHONPATH=/private/tmp/dsh-s1-s10-s12-s15-luna-20260910 \
uv --cache-dir /private/tmp/dsh-h24-h25-harbor-cache tool run \
  --from harbor==0.22.0 harbor run \
  --config /private/tmp/dsh-s1-s10-s12-s15-luna-20260910/config.json \
  --job-name codex-luna-s1-s10-s12-s15-repeat -y
```

本次只新增结果报告和原始答案副本，未调整评分器或任务。新规则已挡住此前的简单复制攻击，但真实作答暴露了语义覆盖不足，尚不能据此认为评分逻辑已经修好。
