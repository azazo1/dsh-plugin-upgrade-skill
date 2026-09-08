---
name: dsh-plugin-upgrade-skill
description: DeepSeek Harness plugin lifecycle skill collection. Use when creating, naming, testing, upgrading, debugging, releasing, auditing, or benchmarking DSH plugins, or when coordinating several plugin lifecycle stages as one workflow. This entry skill gives an overview and routes to the dedicated sub-skills under skills/.
---

# dsh-plugin-upgrade-skill

DSH 插件全生命周期能力合集. 本入口只提供概览与路由, 具体规则由各子 skill 承担, 按任务选择对应子 skill 并加载其 SKILL.md.

| 子 skill | 用途 |
| --- | --- |
| plugin-write | 创建 DSH 插件, 命名校验, 仓库模式与插件形态选择 |
| plugin-test | 插件测试层级选择与宿主版本迁移测试 |
| plugin-upgrade | 升级检查, 已安装插件升级与宿主版本兼容迁移 |
| plugin-runtime-debug | Web 插件运行时行为诊断 |
| plugin-heavy-dep | 轻量 Web 插件接入重量级浏览器依赖 |
| plugin-release | 打包, 发布与分发及发布前 gate |
| plugin-workflow | 全生命周期编排, 多 skill 协作入口 |
| dsh-upgrade-audit | 审计两个 DSH 版本间的外部兼容性变化与 revert |
| dsh-benchmark-case | 将真实迁移经验提取为 Harbor 基准考题 |
