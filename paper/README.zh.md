# Do Migration Skills Actually Help? A Community-Grounded Benchmark for Skill-Guided Framework Migration

审稿意见与补实验优先级：[模拟顶会审稿](REVIEW-2026-09-08.zh.md) · [论文 TODO](GAP-ANALYSIS.zh.md)（2026-09-08 更新）。

[English README](README.md)

本目录是 skill-guided framework migration 的论文工作稿。[新主实验计划](../docs/superpowers/plans/2026-09-08-paper-56-task-rerun.md)以 **56 题 × 两个配置 × 四条件 × 每格一次 = 448 次**统一重跑；正式成绩可见前选定 K 题对称补两次，稳定性额外 16K 次并单列。当前生成表仍是 **23 题历史快照**，待新 56 题版本完成 QC 和冻结后切换。旧实验不混入新主表，56 题全池不等同于独立未见测试；主要实证结论仍待实验验证。

[实验与暴露账本](audit/README.zh.md) 已覆盖 22 份已提交报告和当前 56 个任务定义；这些数量不代表独立测试集规模。

## 目录结构

- `latex/` — 报告 LaTeX 源码
  - `acl_latex.tex` — 主文件（标题、作者、摘要、全文骨架；基于官方最新模板）
  - `acl.sty` / `acl_natbib.bst` — ACL 官方样式（acl-org/acl-style-files master，2026-06 版）
  - `custom.bib` — 参考文献（正文使用的五项已核对版本化 arXiv 记录，完整综述仍待补充）
  - `formatting.md` — 官方格式说明
  - `acl_lualatex.tex` — XeLaTeX / LuaLaTeX 模板（未使用）
- `word/`、`archive/` — 官方 Word 模板与历史模板（本文未使用，随官方样式包保留）

## 编译

```bash
cd latex
pdflatex acl_latex && bibtex acl_latex && pdflatex acl_latex && pdflatex acl_latex
```

使用 [Overleaf](https://www.overleaf.com/) 时，同时上传 `latex/` 和 `generated/` 并保留相对路径，选择 `latex/acl_latex.tex` 为主文件。当前使用 `review` 模式（带行号）。

## 写作状态

- [x] 重写摘要、Introduction 与贡献，明确三个研究问题。
- [x] 将未验证的正向结论改为证据状态和待检验分析。
- [x] 正文接入固定快照宏，区分题号前缀与交互类型。
- [x] 建立实验账本与开发暴露账本（初步审计，未认证独立 split）。
- [x] 替换五项正文引用的 stub，旧线索保存于 `audit/`。
- [ ] 归档可获得的历史产物；为新主实验补齐配置哈希、事件分组与 provenance。
- [ ] 完成独立 grader 校验与双臂统一重评。
- [ ] 冻结并完成 56 题四条件单次主实验及预选子集重复；holdout/clean-trap 作为扩展。
- [ ] 补完图表、实测结果、附录与完整相关工作综述。

## 相关资源

- Benchmark 任务与判分：`../benchmark/`
- Skill 语料：`../skills/`
- 官方样式来源：[acl-org/acl-style-files](https://github.com/acl-org/acl-style-files)
