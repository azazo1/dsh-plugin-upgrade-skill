---
name: dsh-plugin-upgrade-skill
description: DeepSeek Harness plugin lifecycle skill collection. Use when creating, naming, testing, upgrading, debugging, releasing, auditing, or benchmarking DSH plugins, or when coordinating several plugin lifecycle stages as one workflow. This entry skill gives an overview and routes to the dedicated sub-skills under skills/.
---

# dsh-plugin-upgrade-skill

DSH 插件全生命周期能力合集. 本入口只提供概览与路由, 具体规则由各子 skill 承担, 按任务选择对应子 skill 并加载其 SKILL.md.

| 子 skill | 用途 |
| --- | --- |
| plugin-workflow | 编排检查, 升级, 测试, 命名注册, 发布与回滚, 维护阶段账本与独立授权边界 |
| plugin-upgrade | 只读升级检查, 已安装插件升级与宿主兼容迁移 (七类触点 + 版本卡片 + 安全回滚) |
| plugin-write | 编写 DSH 插件, 按目标 Harness 版本选择扩展形态, 区分官方单仓与外部插件规则 |
| plugin-test | 为插件变更选择测试层级, 覆盖真实组合, 发布产物与目标版本产品入口 |
| plugin-release | 打包, 发布与分发: 发布轨选择, 未发布 cohort 安装, CI 门禁与回滚 |
| plugin-runtime-debug | 依据 DSH 源码契约排查 Web 插件运行时故障 (粘贴/附件/输入机, 版本 chip 等) |
| plugin-fleet-sweep | 宿主升级后整批巡检已安装插件: 版本卡静态扫描, 真浏览器逐插件断言, 判定与修复发布循环 |
| plugin-heavy-dep | 轻量 Web 插件接入重依赖 (mermaid 等): 懒加载 chunk, 宿主路由防护, SVG 白名单, 事件所有权 |
| dsh-upgrade-audit | 审计两个 DSH 版本间的外部兼容性变化与 revert, 产出适配报告与边界签名表 |
| dsh-benchmark-case | 把真实迁移经验提取成可自动判分的 Harbor 基准考题 |
| generic-migration | 框架无关的插件迁移方法论 (盘点耦合面, 通读版本走廊, 分层验证), benchmark 侧 generic 对照 |
