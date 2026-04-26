# feishu-campus-longmemory

飞书 AI 校园大赛 - 企业级 Agent 存储系统赛题参赛项目。

本项目计划实现一个面向飞书与 OpenClaw Agent Runtime 的 Personal Work Memory Middleware，用于采集真实办公信号，沉淀个人工作记忆，并在 Agent 回复前或主动服务触发时提供个性化上下文。

## 项目文档

- [产品方案与迭代计划](docs/PRODUCT_ROADMAP.md)

## 当前阶段

当前仓库处于产品定义与工程初始化阶段。后续实现将按 `docs/PRODUCT_ROADMAP.md` 中的版本路线逐步推进，优先完成 P0 的正式闭环：

1. 真实飞书或 OpenClaw 事件接入。
2. SQLite Evidence Store。
3. 显式个人记忆抽取、写入、检索和删除。
4. Memory Context Pack 注入。
5. Reminder Scheduler 与飞书 Bot 主动提醒。
