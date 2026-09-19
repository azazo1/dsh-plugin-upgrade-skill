# 旧实验兼容性清单

本清单针对当前四条件候选协议，不覆盖未公开轨迹的实地复现。原报告和原分数不改写。

覆盖 **37 份报告**；当前没有旧 trial 获准直接填入新主表。

## 结论与执行顺序

1. 先重评本地有答案的静态历史批次，检查换评分器后结论是否改变；这些是测量审计，不是新的四条件主实验。
2. Astra、Qwen、早期 Flash/Terra 等先向贡献者取回候选补丁/完整 fixture、原提示、挂载资料与运行配置；只有分数无法重新评分。
3. 新 D−C 主实验按新提示和材料重跑各条件。不能把重评后的旧 A/D 拼上新 C 就当受控比较。
4. 仅 rubric 改变且原始输入/候选产物完整时可重评；fixture、提示、资料、工具或预算改变须重跑。

## 逐报告决策

| 报告 | 模型 / 范围 | 条件 / 重复 | 历史用途 | 本地答案数 |
|---|---|---|---|---:|
| [2026-08-30](../../../benchmark/results/validation-report-2026-08-30.md) | not a paired model study; single simulated migration | old/new/repaired; not applicable | 仅作评分/开发校准 | 0 |
| [2026-08-31-auth-v1](../../../benchmark/results/validation-report-2026-08-31-auth-v1.md) | gpt-5.6-sol xhigh; 6 tasks | with-skill only; effective trials after setup retries | 须先取回原始产物 | 0 |
| [2026-08-31](../../../benchmark/results/validation-report-2026-08-31.md) | oracle; 6 tasks | oracle; one per task reported | 仅作评分/开发校准 | 0 |
| [2026-09-01-codex-gpt-5.6-luna-other-18-no-injected-skill](../../../benchmark/results/validation-report-2026-09-01-codex-gpt-5.6-luna-other-18-no-injected-skill.md) | gpt-5.6-luna; 18 tasks | no-Harbor-injected-skill; 1 selected per task | 须先取回原始产物 | 0 |
| [2026-09-01-codex-gpt-5.6-luna-other-18](../../../benchmark/results/validation-report-2026-09-01-codex-gpt-5.6-luna-other-18.md) | gpt-5.6-luna; 18 tasks; 19 with separate real-project run | with-skill; 1 selected per task | 须先取回原始产物 | 0 |
| [2026-09-01-codex-gpt-5.6-terra-all-22-literal-no-skill](../../../benchmark/results/validation-report-2026-09-01-codex-gpt-5.6-terra-all-22-literal-no-skill.md) | gpt-5.6-terra xhigh; 22 attempted; 21 scored; H8 verifier failure | literal zero-skill as audited in report; 1 selected per task; retries recorded | 须先取回原始产物 | 0 |
| [2026-09-01-codex-gpt-5.6-terra-all-22](../../../benchmark/results/validation-report-2026-09-01-codex-gpt-5.6-terra-all-22.md) | gpt-5.6-terra xhigh; 22 attempted; 21 scored; H8 verifier failure | with-skill; 1 selected per task; retries recorded | 须先取回原始产物 | 0 |
| [2026-09-01-h13](../../../benchmark/results/validation-report-2026-09-01-h13.md) | oracle/manual; H13 ghost-host | oracle/negative controls; see report | 仅作评分/开发校准 | 0 |
| [2026-09-01-h8-dsh-web-alpha2-no-skill](../../../benchmark/results/validation-report-2026-09-01-h8-dsh-web-alpha2-no-skill.md) | gpt-5.6-luna xhigh; legacy H8-dsh-web-alpha2 -> current H9 | no-Harbor-injected-skill; 1 scored; agent timeout | 须先取回原始产物 | 0 |
| [2026-09-01-portfolio-h9m12-dry-run](../../../benchmark/results/validation-report-2026-09-01-portfolio-h9m12-dry-run.md) | not verified; current H16/H17/H18/H19; legacy IDs remapped | no-skill only; one reported per task | 仅作评分/开发校准 | 0 |
| [2026-09-01-terminus2-deepseek-v4-flash](../../../benchmark/results/validation-report-2026-09-01-terminus2-deepseek-v4-flash.md) | deepseek-v4-flash; 23 tasks; H8 with-skill has 2 scored trials | with-skill/no-skill; 3 intended; H8 with=2 | 须先取回原始产物 | 0 |
| [2026-09-01](../../../benchmark/results/validation-report-2026-09-01.md) | gpt-5.6-luna xhigh; legacy H5-dsh-web-alpha2 -> current H9 | with-skill; 1 scored; agent timeout | 须先取回原始产物 | 0 |
| [2026-09-02-claude-code-opus5-interim](../../../benchmark/results/validation-report-2026-09-02-claude-code-opus5-interim.md) | claude-opus-5; 23 planned; 15 complete pairs | with/without-skill; 3/3 in 15 pairs; incomplete elsewhere | 须先取回原始产物 | 0 |
| [2026-09-02-h22-dsh-data-agent-alpha2-no-skill](../../../benchmark/results/validation-report-2026-09-02-h22-dsh-data-agent-alpha2-no-skill.md) | gpt-5.6-luna xhigh; H22 | literal zero-skill accepted run; 1 accepted; preliminary contaminated attempt retained separately | 须先取回原始产物 | 0 |
| [2026-09-02-h22-dsh-data-agent-alpha2-plugin-upgrade](../../../benchmark/results/validation-report-2026-09-02-h22-dsh-data-agent-alpha2-plugin-upgrade.md) | gpt-5.6-luna xhigh; H22 | with-skill; 1 scored | 须先取回原始产物 | 0 |
| [2026-09-02-metadata-activation-ab](../../../benchmark/results/validation-report-2026-09-02-metadata-activation-ab.md) | gpt-5.6-luna xhigh; historical H11 -> current H12 | old/new metadata; both supplied skill; 3 per arm; balanced order | 保留历史描述，不直接重评 | 0 |
| [2026-09-03-static-20-paired](../../../benchmark/results/validation-report-2026-09-03-static-20-paired.md) | GLM-5.3 for 17 pairs; flash-vision-exp for S16; 20 rows; 18 eligible pairs; evolving 44->52 inventory | with/no-skill; 1 retained per arm | 仅作评分/开发校准 | 0 |
| [2026-09-03-terminus2-deepseek-v4-flash-h21](../../../benchmark/results/validation-report-2026-09-03-terminus2-deepseek-v4-flash-h21.md) | deepseek-v4-flash; H21 | frozen-skill/no-injected-skill; 3 per arm | 仅作评分/开发校准 | 0 |
| [2026-09-06-s1-s4-oracle-luna-llm-judge](../../../benchmark/results/validation-report-2026-09-06-s1-s4-oracle-luna-llm-judge.md) | solver gpt-5.6-luna; judge gpt-6-astra high; S1-S4 oracle + Luna | oracle/no-injected Luna; not skill/no-skill; 1 grade per answer | 仅作评分/开发校准 | 0 |
| [2026-09-06-s1-s4-oracle-regrade-r2](../../../benchmark/results/validation-report-2026-09-06-s1-s4-oracle-regrade-r2.md) | judge gpt-6-astra high; S1-S4 oracles only | oracle only; Luna unchanged; 1 grade per oracle | 仅作评分/开发校准 | 0 |
| [2026-09-06-s1-s4-report-judge-pilot](../../../benchmark/results/validation-report-2026-09-06-s1-s4-report-judge-pilot.md) | no live judge; S1-S4 | offline variants; not model trials | 仅作评分/开发校准 | 0 |
| [2026-09-06-three-system-paired-eval](../../../benchmark/results/validation-report-2026-09-06-three-system-paired-eval.md) | v4-pro / flash-vision-exp / glm-5.3-flash; 42-task declared snapshot; differing result denominators | mixed paired/missing/cross-system contrast; mostly 1; M8/M10 3; round-level assignment unknown | 仅作评分/开发校准 | 0 |
| [2026-09-07-generic-skill-s1-s10-kimi](../../../benchmark/results/validation-report-2026-09-07-generic-skill-s1-s10-kimi.md) | Kimi Code; exact model ID unknown; S1-S10 | generic only; 1/task | 有本地答案，可作历史重评候选 | 10 |
| [2026-09-08-codex-gpt-6-astra-xhigh-18](../../../benchmark/results/validation-report-2026-09-08-codex-gpt-6-astra-xhigh-18.md) | openai/gpt-6-astra xhigh; 18 tasks | plugin-upgrade only; 1/task | 须先取回原始产物 | 0 |
| [2026-09-09-codex-gpt-6-astra-xhigh-full56](../../../benchmark/results/validation-report-2026-09-09-codex-gpt-6-astra-xhigh-full56.md) | openai/gpt-6-astra xhigh; 56 tasks; initial18 + remaining38 | plugin-upgrade only; 1/task | 须先取回原始产物 | 0 |
| [2026-09-10-codex-gpt-5.6-luna-h24-h25](../../../benchmark/results/validation-report-2026-09-10-codex-gpt-5.6-luna-h24-h25.md) | gpt-5.6-luna xhigh; H24/H25 | no injected/native skill; 1/task | 须先取回原始产物 | 0 |
| [2026-09-10-codex-gpt-5.6-luna-s1-s10-s12-s15-no-skill](../../../benchmark/results/validation-report-2026-09-10-codex-gpt-5.6-luna-s1-s10-s12-s15-no-skill.md) | gpt-5.6-luna xhigh; S1/S10/S12/S15 | no skill; 1/task | 有本地答案，可作历史重评候选 | 4 |
| [2026-09-10-codex-gpt-5.6-luna-seven-semantic-no-skill](../../../benchmark/results/validation-report-2026-09-10-codex-gpt-5.6-luna-seven-semantic-no-skill.md) | gpt-5.6-luna xhigh; judge Astra high; S1-S4/S10/S12/S15 | no skill; 1/task | 有本地答案，可作历史重评候选 | 7 |
| [2026-09-10-default-semantic-verifiers](../../../benchmark/results/validation-report-2026-09-10-default-semantic-verifiers.md) | judge gpt-6-astra high; 7 semantic tasks, selected calibration cases | calibration; not solver arms; 15 judge calls reported | 仅作评分/开发校准 | 0 |
| [2026-09-11-codex-gpt-5.6-luna-s5-s9-semantic-no-skill](../../../benchmark/results/validation-report-2026-09-11-codex-gpt-5.6-luna-s5-s9-semantic-no-skill.md) | gpt-5.6-luna xhigh; judge Astra high; S5-S9 | no skill; 1/task | 有本地答案，可作历史重评候选 | 5 |
| [2026-09-11-codex-qwen3.8-27b-medium-paired](../../../benchmark/results/validation-report-2026-09-11-codex-qwen3.8-27b-medium-paired.md) | qwen3.8-27b medium; local BF16 H20; 56 tasks / 336 attempts / 335 scores | plugin-upgrade / no Harbor-injected skill; 3/arm/task; H8 baseline score missing | 须先取回原始产物 | 0 |
| [2026-09-11-glm-5.3-flash-s1-s22-round2](../../../benchmark/results/validation-report-2026-09-11-glm-5.3-flash-s1-s22-round2.md) | GLM-5.3-flash solver and judge; S1-S22 | skill / noskill; 1/arm/task in this round | 有本地答案，可作历史重评候选 | 44 |
| [2026-09-11-glm-5.3-flash-s1-s22-round3](../../../benchmark/results/validation-report-2026-09-11-glm-5.3-flash-s1-s22-round3.md) | GLM-5.3-flash solver and judge; S1-S22 | skill / noskill; 1/arm/task in this round | 有本地答案，可作历史重评候选 | 44 |
| [2026-09-11-glm-5.3-flash-s1-s22](../../../benchmark/results/validation-report-2026-09-11-glm-5.3-flash-s1-s22.md) | GLM-5.3-flash solver and judge; S1-S22 | skill / noskill; 1/arm/task in this round | 有本地答案，可作历史重评候选 | 44 |
| [2026-09-11-s5-s9-default-semantic-verifiers](../../../benchmark/results/validation-report-2026-09-11-s5-s9-default-semantic-verifiers.md) | judge gpt-6-astra high; S5-S9 / 20 calibration calls | oracle/paraphrase/keyword/contradiction controls; 1/case | 仅作评分/开发校准 | 0 |
| [2026-09-12-codex-luna-h4-h6-h12-decision-judge](../../../benchmark/results/validation-report-2026-09-12-codex-luna-h4-h6-h12-decision-judge.md) | gpt-5.6-luna xhigh solver / high judge; H4/H6/H12 | no skill; same original answers across two reports; 0 new solver trials; 1 regrade/task | 有本地答案，可作历史重评候选 | 3 |
| [2026-09-12-codex-luna-h4-h6-h12-no-skill](../../../benchmark/results/validation-report-2026-09-12-codex-luna-h4-h6-h12-no-skill.md) | gpt-5.6-luna xhigh solver / high judge; H4/H6/H12 | no skill; same original answers across two reports; 1 solver/task; earlier H4/H6 judge retry only | 有本地答案，可作历史重评候选 | 3 |

本地答案数按报告关联计算，存在重复关联，不能求和当作独立 trial 总数。逐文件 SHA、packet 逐项比较、模型/scaffold/skill/评分版本和资料边界见 `compatibility.json`。

## 重评前还要检查

- GLM 三轮：本地保存两臂答案；统一裁判后每轮两臂全部重评，先确认 sealed fixture 与提示版本一致。历史关键词/语义分不能混作统一新版分数。
- Luna 四题／七题／五题：本地保存静态答案；七题是新作答，不是四题旧答案重评。仅无 skill，重评也不能给出配对 skill 效果。
- H4/H6/H12：decision-judge 已对原答案重评；两个报告共享三份 solver 答案，不是六份。H4删除构建产物的例外需保留候选完整性证据。
- Generic Kimi pilot：若本地答案齐全可审计旧评分，但模型/scaffold不同，不能拿来与 GLM/Astra 做条件差分。
- H24/H25：紧凑 JSON 不等于完整可执行补丁；H25 helper 封顶争议需先判定契约，再决定历史重评标准。
- Astra initial18 已计入 full56；GLM round3 中的中位数汇总不是第四轮；元数据 activation pilot 的原始临时轨迹据报告已删除。

## 已发现的统计口径问题

- GLM 首轮：按各 22 条 solver 用量汇总，total token 比例为 **0.8823**，累计会话耗时比例为 **1.1245**。报告中约 2.2 倍／翻倍的说法需修正；累计会话时间不等于并行墙钟。
- Qwen：按每题现有有效重复均值、56 题等权，差为 **-3.0714 pp**；H8仍缺一分数，不是完整配对估计。skill/no-skill 分别有 **18/12** 个 timeout 且满分的 trial，超时不等于功能失败。
- 上述是原 JSON 的可复算补充，不覆盖或修饰原始记录；正式区间、分组与缺失敏感性分析另做。
