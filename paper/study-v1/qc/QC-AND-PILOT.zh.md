# 材料收尾、评分 QC 与预演记录

本轮完成材料适配、离线评分 QC 和 16 格预演目录准备。**真实模型预演未执行，Docker 隔离探针也尚未运行成功。** 没有产生模型费用，实际推理成本仍未知。

## 材料收尾

当前版本为 document-only-r2。原始 skill 和早期 ZIP 保留；新材料是显式适配版，不能在论文里写成原版完整 skill。

- 16 个原 mixed 段落由纯流程正文替代；31 个版本摘要从 D 入口移除。两个新正文只保留范围、基线、走廊净状态、触点映射、最小变更、分层验证及报告流程。中文旧 pin 保留中文正文，其余使用英文。
- 包身份、版本坐标和宿主全局安装故障事实继续由 C/D 同字节的事实补充提供；版本卡和参考文档也逐字共享。没有把整个 D 入口复制给 C。
- precision-checklist 的交付/评分导向段落改为普通工程说明；交付位置和静态/可执行任务的边界统一放在四组共同提示中。没有删掉迁移契约本身的版本要求。
- 入口不再指令执行 planner、verify-runtime 等未供应 helper；pre-flight 的 ghost-host 检查和 precision-checklist 的残留扫描改为普通本地工具表述。所有未供应本地附件链接改为来源标签，不再形成可导航断链。三个版本四组本地断链均为 0；这不是运行时能力全部验证的证明。
- B 的“没读 changelog 就不能迁移”改为缺证据时明确不确定、继续允许的检查。共同政策明确容器内 loopback 可用于当前任务自己的验证，但不允许宿主服务或外网。

原 47 项的处理记录见 [entry-resolution-r2.json](../review/entry-resolution-r2.json)，完整逐文件 before/after 哈希与文本 diff 在 generated/material-manifest.json 的 materialEdits。这里关闭的是新版材料的组织和信息不对称问题，不是假称原文所有断言均已验证。benchmark 暴露历史仍保留，不能据此宣称独立泛化。

## H4 / H6 / H12 评分 QC

逐项比对两轮已归档 packet：instruction、fixture、references、rubric 均相同。使用当前 scoreDecisions 对旧模型的判定 JSON 重新汇总，复现 85、75、82.5。**这是确定性汇总重放，不是新一轮模型语义判分。**

| 题目 | 本轮审查结论 |
|---|---|
| H4 | 来源未命中而构建产物仍有旧导入的归因成立。旧答案缺少测试复核细节，按冻结 rubric 的半分规则得到 85 有依据；不应要求静态夹具执行缺失的 build 脚本。原 v1 引文校验错误仍是 judge_error，不是 0 分。允许删除 lib 的例外和禁止改源文件的边界已由现有测试覆盖。 |
| H6 | 旧答案明确拒绝旧码、处理未知分支并保留错误；没有确定的 namespaced 字面量，按旧 rubric 给部分分符合协议。对于“不盲重试”和保留 details 的表达，答案已有 higher-level policy / remote error 的间接表述，半分边界存在语义敏感性，应列入后续活体校准，不把 75 当作唯一客观标签。新四组必须使用相同 rubric，不按模型组别改变要求。 |
| H12 | 旧代码在 gateway/cancelled 分支仍直接递归重试，与取消终止策略冲突，扣分有具体依据。它明确描述结构判别与真实 reject 边界，error-discrimination 半分尺度仍值得活体校准；不因与标准答案词句不同自动扣分。 |

相关评分器、传输、静态完整性与 H25 源码评分测试共 **90 项通过**。其中传输使用测试替身，不能写成 90 次独立语义验证。现有 calibration 包仍需在最终裁判模型上运行：正确答案/正确改写、关键词堆砌、最终错误建议、否定错误建议、提示注入、prompt echo；先预定样本和重复次数。

## H25：封顶争议已用真实运行时复现

在独立临时目录，按原 lockfile 安装固定 alpha.4 运行时，保留原 grader，使用添加诊断字段的副本执行 6 个合成对照。依赖由本地 npm 缓存离线安装，没有联网取包。系统 npm 11.17.0 首次 ci 报锁文件同步错误；切换已有 Node 22 所带 npm 后，原锁文件未变即安装成功。执行 QC 的 Node 为 24.19.0。

| 合成对照 | 旧总分 | 行为分 |
|---|---:|---:|
| 标准答案 | 100 | 65/65 |
| 等价替代：helper 只返回 header meta，构造会话时直接传原 cut | 40 | 65/65 |
| 错误替代：恢复时把原 cut 换成当前日志长度 | 65 | 45/65 |
| 绕过位置/偏移构造器校验 | 40 | 60/65 |
| 未修改 fixture | 0 | 未进入行为检查 |
| 语法错误 | 15 | 0/65 |

结果说明旧 40 分 cap 确实混合了 helper 形状和功能正确性。新研究采用以下口径：**行为检查全部通过与否单列为主结果；helper metadata 形状、源码迁移和依赖合规分列为次结果。** 已有 fixture/宿主完整性门禁继续适用，不能绕过门禁后仅按行为分宣布通过。16 格预演尚没有 solver 输出，不存在新的主实验成绩。

没有按这个合成实现重写 Luna 的历史 40 分：它不是找回的原始候选补丁，也不证明历史产物和合成源码逐字一致。旧报告按原规则保留，论文中必须解释“40 分但行为 65/65”，不能写为恢复边界失败。若今后要把独立 helper 返回形状设为强制契约，应在新任务明确说明并重新跑全部条件。

## 四组开发预演

选择 H4/H6/H12 三个静态题和 H25 一个可执行题，按 A/B/C/D 准备 **16 格**，不计入正式主实验。各格只含自己的材料、固定 fixture、新提示、空输出目录和独立探针；本地检查确认哈希、目录边界与无符号链接。

脚本已生成容器探针命令，配置 network=none、只读根目录、空 HOME、无宿主配置/凭据/其他组/裁判挂载，限制资源和权限；静态 fixture 只读，H4 仅 lib 可写，H25 仅源码与 package.json 可写。探针将验证只读失败、指定位置交付、本地 loopback 可用和外网不可连接。

**当前阻碍：** Docker CLI 存在，但 daemon 不可连接；尝试启动 Docker 及其内部应用均返回可执行文件缺失错误。没有安装或修复系统软件。目录检查不能代替容器隔离探针，因此不报告隔离通过。

此外，REPORT_JUDGE 配置和常见 API key 环境变量未配置；两个 solver 的模型、服务和花费上限尚未确定。探针不是模型 agent：需要接入宿主侧模型传输和用量记录，避免为了模型联网而让容器任意联网。H25 正式运行前还要在构建阶段装好锁定依赖，当前预演目录只有固定源 fixture。

## 复现与下一步

```bash
python3 paper/scripts/prepare-study-v1.py --check
python3 -m unittest discover -s paper/scripts -p 'test_study_materials.py'
# fixture-deps 是在独立目录按原 lockfile 安装依赖后的 H25 fixture
node paper/scripts/qc-study-v1.mjs /tmp/new-qc-results.json /path/to/fixture-deps
# 每次使用新 stage 路径；--docker-probe 不会拉取镜像或调用模型
python3 paper/scripts/pilot-study-v1.py --out /tmp/new-study-pilot --report /tmp/new-study-pilot.json --docker-probe
```

接下来需要恢复可用 Docker daemon，确定两个模型及总预算。随后实现/接入模型 adapter，在 16 格上实测启动、材料读取、交付、token、超时和费用；再对三题语义裁判做预定校准，冻结评分版本和预算。当前没有足够依据宣布 56 题全部评分 QC 完成，也不应直接启动正式主实验。
