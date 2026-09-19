# 四组材料隔离预检（isolation preflight）

本目录新增 **模型无关（model-free）** 的材料隔离预检工具，检查 study-v1 的 A/B/C/D
四个条件是否只暴露本条件自己的材料。工具不调用任何 solver 模型、不联网、不修改
`benchmark/tasks/**`、`skills/**` 或任何历史结果。

- 工具：`paper/scripts/check-study-v1-isolation.py`
- 报告结构：`paper/study-v1/qc/isolation-preflight.schema.json`（JSON Schema 2020-12）
- 测试：`paper/scripts/test_study_isolation.py`（`unittest`，91 项，不需要 Docker）

## 为什么需要它

`prepare-study-v1.py` 决定每个条件挂载哪些文件；`pilot-study-v1.py` 生成容器命令。
在真正跑 solver 之前，需要一个可离线复现的检查，回答“A 组会不会看到 D 的流程”、
“C/D 的参考字节是否逐字一致”、“`tests/`、`solutions/`、`benchmark/results/`、
宿主配置和凭据是否可能进入任务环境”等问题。这个预检就是一个 **材料挂载计划
（material mount plan）** 上的显式边界测试。

## 计划从哪里来

- 默认（`--plan-only`）：从研究权威 `paper/study-v1/config.json` 出发，复用
  `paper/scripts/prepare-study-v1.py` 的 `build_materials`，为 4 个预演任务
  （H4 / H6 / H12 / H25）构建每个条件一个只读 `/app/materials` 挂载的计划。
- `--material-root DIR`：从合成目录树 `<DIR>/<task>/<arm>/...` 读取材料，
  供测试构造任意边界场景（符号链接、硬链接、缺失挂载等）。

计划里每个任务包含 A/B/C/D 四个 arm：材料挂载（只读，仅本组）、fixture 挂载
（静态任务只读；H25 可写；H4 仅 `lib` 例外可写）、只读 instruction、独立可写的
`/app/agent-output/<task>`、只读 probe。环境块声明 `network=none`、
`HOME=/home/study`、native skill 自动发现关闭、期望不出现的凭据变量名。

## 检查项（24 个，稳定 id）

| id | 含义 |
|---|---|
| `mount-manifest` | 每个条件的挂载清单存在且结构良好（arm、entry、sha256、挂载类型） |
| `arm-a-disclosure` | A 只暴露 ENTRY，不暴露 B/C/D 的流程或参考材料（含改名后的同字节泄漏） |
| `arm-b-reference-isolation` | B 不含 C/D 的 references 与事实补充 |
| `cd-shared-bytes` | C/D 的事实与参考文件逐字一致（含共享事实补充） |
| `d-guidance-only-delta` | D 相对 C 只多出 `guidance.md`；C 不含 `guidance.md` |
| `solution-leak` | 任何 arm 都看不到 `solution/`、`solve.sh`、`SOLUTION.md`、`oracle` |
| `judge-leak` | 看不到 `tests/`、`judge.mjs`、`test.sh`、`judge-utils` |
| `results-leak` | 看不到 `benchmark/results/` |
| `cross-arm-output` | 看不到其他条件的材料或输出路径 |
| `native-skill-leak` | 看不到 `skills/`、`~/.agents/skills`，且自动发现必须关闭 |
| `agents-skills-mount` | `~/.agents/skills` 未被挂载或可读 |
| `host-config-mount` | `~/.codex` `~/.config` `~/.claude` `~/.ssh` `~/.aws` 等未挂载 |
| `credential-env` | 任务环境不含凭据变量（值为 `null`/空视为未设置） |
| `material-readonly` | 材料挂载只读 |
| `workspace-writable` | 任务允许写入的 workspace 与交付目录确实可写 |
| `output-independent` | 交付目录是独立路径，不与材料重叠 |
| `symlink-escape` | 材料内符号链接指向挂载根之外即失败（含嵌套符号链接） |
| `relative-traversal` | `../` 穿越路径被拒绝 |
| `absolute-escape` | 绝对路径（POSIX 与 Windows 风格）不得作为挂载内路径/宿主 source |
| `output-confinement` | 交付路径被限制在 `/app/agent-output/<task>` |
| `inventory-pinned` | 只接受固定 56 题 inventory 中的任务；在线 benchmark 多出的题被拒绝 |
| `duplicate-material` | 条件之间材料根不重复、同 arm 内不出现重复字节 |
| `unexpected-material` | 每个 arm 只出现允许的材料文件名 |
| `hardlink-alias` | 材料文件存在指向挂载外的硬链接别名时报警 |

计划只有 20 项是题目要求的下限，实际实现为 24 项；报告中的 check 顺序按 id 字典序，
保证字节级确定性。

## `runtimeCanaryStatus` 语义

报告顶层字段 `runtimeCanaryStatus` 只取三个值：

- `not-run`：没有运行任何容器。默认离线路径、Docker daemon 不可用、或本地没有可用
  镜像（脚本不会联网拉取镜像）都会是 `not-run`，并在 `runtimeCanary.reason` 写明原因。
- `passed`：`--docker-canary` 下真的运行了容器，且探针确认材料只读、交付可写、
  环境无凭据、无宿主配置、`--network none`。
- `failed`：容器真的运行了，但探针发现边界违规。

**通过的离线计划不是容器验证过的隔离。** `not-run` 只说明静态计划没有发现问题；
它不能替代真实容器探针。文档、报告和论文都必须保留这一区分。

## 退出码

- `0`：全部检查通过；默认模式下 canary 为 `not-run` 也算通过。
- `1`：存在真实隔离违规；或显式请求 `--docker-canary` 但无法运行（daemon/镜像不可用）。
- `2`：用法或配置错误（未知任务、未知条件、坏路径、`--plan-only` 与 `--docker-canary` 同时给出）。

## 用法

```bash
python3 paper/scripts/check-study-v1-isolation.py --check            # 全部 4 个预演任务
python3 paper/scripts/check-study-v1-isolation.py --task H4-tsbuildinfo-trap --json
python3 paper/scripts/check-study-v1-isolation.py --material-root /tmp/synthetic --json
python3 paper/scripts/check-study-v1-isolation.py --docker-canary   # 可选；不可用时报 not-run
python3 -m unittest discover -s paper/scripts -p 'test_study_isolation.py'
```

## 确定性

序列化报告没有时间戳、主机名、用户名或本地绝对路径：宿主绝对路径被替换为
`<redacted>`，容器路径（`/app/...`、`/home/study` 等）保留。相同输入两次运行输出
逐字节一致，检查项按 id 字典序排列。

## 边界

- 模型无关：`solverCalls = 0`，没有模型调用，也不测量 token 或费用。
- 无网络：工具本身不访问网络；Docker canary 使用 `--network none`，且绝不拉取镜像。
- Docker 可选：测试和默认校验路径都不需要 Docker。
- 本工具不改变材料内容、任务、skill 或历史结果，也不解除 `formalRunAllowed: false`。
