# OpenClaw + 飞书集成官方文档与接口清单

> 面向项目：**Personal Work Memory Middleware / 个人工作记忆中间层**  
> 目标：整理与飞书、OpenClaw 集成相关的官方接口文档、工具包、调用文档与案例链接，方便后续实现“飞书信息抽取、OpenClaw Prompt 介入、主动服务触发”等能力。

---

## 1. 总览：项目需要关注的资料类型

| 类别 | 项目中的用途 | 推荐优先级 |
|---|---|---|
| OpenClaw Feishu Channel | 让 OpenClaw 接入飞书 Bot，接收飞书消息、发送回复 | P0 |
| 飞书开放平台 IM API / 事件订阅 | 监听消息、发送提醒、发送卡片 | P0 |
| 飞书官方 SDK / CLI / MCP | 快速调用飞书 API，适合 Demo 和 Agent 工具化 | P0 / P1 |
| 飞书云文档 / Wiki / Task / Calendar API | 获取文档、知识库、任务、日历操作元数据 | P1 |
| OpenClaw Tools / Plugins / Hooks | 把 Memory Middleware 暴露给 OpenClaw 使用 | P0 |
| OpenClaw Memory / Active Memory | 在 Agent 回复前检索并注入个人记忆 | P0 / P1 |

---

## 2. OpenClaw 官方文档

| 名称 | 用途 | 链接 |
|---|---|---|
| OpenClaw Feishu Channel | 接入飞书 Bot，收发飞书消息，配置飞书应用、事件订阅、群聊/单聊权限 | https://docs.openclaw.ai/channels/feishu |
| OpenClaw Tools and Plugins | 理解 Tool / Skill / Plugin 的区别；把 Memory Middleware 注册成 OpenClaw Tool | https://docs.openclaw.ai/tools |
| OpenClaw Plugins | 插件安装、配置、启用；适合把中间层封装成 OpenClaw 插件 | https://docs.openclaw.ai/plugins |
| OpenClaw Plugin Hooks | 插件级 Hook，可用于 `before_prompt_build`、`before_agent_reply`、`after_tool_call` 等深度介入 | https://docs.openclaw.ai/plugins/hooks |
| OpenClaw Hooks | Gateway 内部事件 Hook，用于消息接收、会话、启动、命令等事件自动化 | https://docs.openclaw.ai/automation/hooks |
| OpenClaw Memory Overview | OpenClaw 原生记忆文件、`MEMORY.md`、`memory_search`、`memory_get` | https://docs.openclaw.ai/concepts/memory |
| OpenClaw Active Memory | 主回复前的主动记忆召回机制，适合个人偏好、长期习惯、上下文个性化 | https://docs.openclaw.ai/concepts/active-memory |
| OpenClaw Memory Search | 记忆语义搜索，embedding + keyword hybrid 检索，适合 P1 语义召回 | https://docs.openclaw.ai/concepts/memory-search |
| OpenClaw Webhooks Plugin | 外部系统触发 OpenClaw TaskFlow，可用于 Middleware 主动服务触发 OpenClaw | https://docs.openclaw.ai/plugins/webhooks |
| OpenClaw CLI Hooks | `openclaw hooks` 命令文档，管理、启用、检查 Hook | https://docs.openclaw.ai/cli/hooks |
| OpenClaw CLI Webhooks | `openclaw webhooks` 命令文档 | https://docs.openclaw.ai/cli/webhooks |

---

## 3. 飞书开放平台：应用、认证、事件订阅

| 名称 | 用途 | 链接 |
|---|---|---|
| 飞书开放平台首页 | 创建企业自建应用、配置权限、机器人、事件订阅 | https://open.feishu.cn/ |
| 飞书开放平台控制台 | 管理飞书应用、App ID、App Secret、权限、事件订阅 | https://open.feishu.cn/app |
| Lark 国际版开放平台 | 国际版 Lark 应用管理入口 | https://open.larksuite.com/app |
| 获取自建应用 `tenant_access_token` | 服务端调用飞书 OpenAPI 的基础认证接口 | https://open.feishu.cn/document/server-docs/authentication-management/access-token/tenant_access_token_internal |
| 服务端 API 调用指南 | 理解 tenant token、user token、权限、错误码等基础概念 | https://open.feishu.cn/document/server-docs/api-call-guide/terminology |
| 配置事件订阅方式 | 配置飞书事件订阅、回调地址、加密策略等 | https://open.feishu.cn/document/server-docs/event-subscription-guide/event-subscription-configure-/request-url-configuration-case |

---

## 4. 飞书 IM 消息、事件、卡片

| 名称 | 用途 | 链接 |
|---|---|---|
| 发送消息 API | 主动提醒用户、发送记忆确认消息、发送 Agent 回复 | https://open.feishu.cn/document/server-docs/im-v1/message/create |
| 回复消息 API | 对用户某条消息进行线程内回复 | https://open.feishu.cn/document/server-docs/im-v1/message/reply |
| 获取消息 API | 读取指定消息内容或附件信息 | https://open.feishu.cn/document/server-docs/im-v1/message/get |
| 查询消息历史 API | 定时抽取消息行为、分析活跃时间段 | https://open.feishu.cn/document/server-docs/im-v1/message/list |
| 接收消息事件 `im.message.receive_v1` | 监听用户发给 Bot 的消息、群里 @Bot 消息 | https://open.feishu.cn/document/server-docs/im-v1/message/events/receive |
| 编辑消息 API | 更新 Bot 已发送的消息 | https://open.feishu.cn/document/server-docs/im-v1/message/update |
| 撤回消息 API | 撤回 Bot 消息 | https://open.feishu.cn/document/server-docs/im-v1/message/recall |
| 更新应用发送的消息卡片 | 更新交互卡片状态，例如“已记住 / 已忽略” | https://open.feishu.cn/document/server-docs/im-v1/message-card/patch |
| 交互式卡片概览 | 做“记住 / 暂不 / 忘记 / 修改”按钮卡片 | https://open.feishu.cn/document/server-docs/cardkit-v1/card/overview |

---

## 5. 飞书云文档 Docx / Drive

| 名称 | 用途 | 链接 |
|---|---|---|
| 创建新版文档 Docx | Agent 主动创建周报、会议纪要、总结草稿 | https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document/create |
| 获取文档基本信息 | 获取标题、文档 ID、版本等元信息 | https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document/get |
| 获取文档纯文本内容 | 需要分析文档内容时使用，注意权限和隐私 | https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document/raw_content |
| 获取文档所有块 | 读取结构化文档 blocks | https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document-block/list |
| 创建文档块 | 将 Agent 生成内容写入飞书文档 | https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document-block/create |
| 更新文档块 | 修改文档内容 | https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document-block/update |
| 删除文档块 | 删除文档中的块 | https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document-block/delete |
| 云文档评论事件 | 监听文档评论，适合“文档里 @Agent 修改/记忆偏好”场景 | https://open.feishu.cn/document/server-docs/drive-v1/notice/events/comment_add |

---

## 6. 飞书知识库 Wiki

| 名称 | 用途 | 链接 |
|---|---|---|
| 获取知识库空间列表 | 识别用户常用知识库空间 | https://open.feishu.cn/document/server-docs/docs/wiki-v2/space/list |
| 获取知识库节点列表 | 获取某个知识库空间下的页面结构 | https://open.feishu.cn/document/server-docs/docs/wiki-v2/node/list |
| 获取知识库节点信息 | 获取某个知识库页面元信息 | https://open.feishu.cn/document/server-docs/docs/wiki-v2/node/get |
| 创建知识库节点 | Agent 主动沉淀知识到 Wiki | https://open.feishu.cn/document/server-docs/docs/wiki-v2/node/create |
| 移动知识库节点 | 调整 Wiki 页面位置 | https://open.feishu.cn/document/server-docs/docs/wiki-v2/node/move |
| 搜索云文档 | 可用于知识库/文档检索和用户查询行为建模 | https://open.feishu.cn/document/server-docs/search-v2/data-search/create |

---

## 7. 飞书任务 Task

| 名称 | 用途 | 链接 |
|---|---|---|
| 创建任务 | Agent 将会议 Action Items 转为飞书任务 | https://open.feishu.cn/document/server-docs/task-v2/task/create |
| 获取任务详情 | 获取任务状态、负责人、截止时间 | https://open.feishu.cn/document/server-docs/task-v2/task/get |
| 更新任务 | Agent 代用户更新任务状态、截止时间等 | https://open.feishu.cn/document/server-docs/task-v2/task/update |
| 删除任务 | 删除任务 | https://open.feishu.cn/document/server-docs/task-v2/task/delete |
| 查询任务列表 | 定时扫描用户任务，建模任务跟进习惯 | https://open.feishu.cn/document/server-docs/task-v2/task/list |
| 完成任务 | 记录用户完成任务时间，建模工作节奏 | https://open.feishu.cn/document/server-docs/task-v2/task/complete |
| 任务评论 | 记录任务跟进、评论、协作行为 | https://open.feishu.cn/document/server-docs/task-v2/comment/create |

---

## 8. 飞书日历 Calendar

| 名称 | 用途 | 链接 |
|---|---|---|
| 创建日程 | Agent 帮用户安排会议、提醒 | https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/create |
| 获取日程 | 读取会议时间、会议详情 | https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/get |
| 查询日程列表 | 统计用户会议时间规律 | https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/list |
| 更新日程 | Agent 代用户改期 | https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/patch |
| 删除日程 | 删除日程 | https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/delete |
| 查询主日历 | 获取用户日历 ID | https://open.feishu.cn/document/server-docs/calendar-v4/calendar/primary |
| 查询空闲忙碌 | 主动服务时避开用户忙碌时间 | https://open.feishu.cn/document/server-docs/calendar-v4/freebusy/list |

---

## 9. 飞书官方 SDK / CLI / MCP

| 名称 | 用途 | 链接 |
|---|---|---|
| 飞书官方 Python SDK：`lark-oapi` | Python 中间层调用飞书 OpenAPI、处理事件、处理卡片回调 | https://github.com/larksuite/oapi-sdk-python |
| 飞书官方 CLI：`@larksuite/cli` | 快速 Demo；Agent 通过命令行操作飞书消息、文档、任务、日历等 | https://github.com/larksuite/cli |
| 飞书 CLI 官网 | CLI 安装、能力介绍、AI Agent 使用说明 | https://feishu-cli.com/ |
| 飞书官方 OpenAPI MCP | 将飞书 OpenAPI 封装为 MCP 工具，适合 Agent 工具化调用 | https://github.com/larksuite/lark-openapi-mcp |

---

## 10. OpenClaw + 飞书相关源码 / 案例

| 名称 | 用途 | 链接 |
|---|---|---|
| OpenClaw Feishu Channel 文档 | 官方接入流程和配置示例 | https://docs.openclaw.ai/channels/feishu |
| OpenClaw Plugin Hooks 示例 | 插件内注册 Hook 的代码示例 | https://docs.openclaw.ai/plugins/hooks |
| OpenClaw Tools and Plugins 示例 | 理解工具、技能、插件的组合方式 | https://docs.openclaw.ai/tools |
| Feishu CLI GitHub 示例 | CLI 里有大量 Messenger、Docs、Calendar、Tasks 调用案例 | https://github.com/larksuite/cli |
| Feishu Python SDK samples | Python SDK 仓库内 samples 目录，可参考事件、卡片、API 调用 | https://github.com/larksuite/oapi-sdk-python/tree/v2_main/samples |
| Lark OpenAPI MCP docs | MCP 工具的安装与配置说明 | https://github.com/larksuite/lark-openapi-mcp/tree/main/docs |

---

## 11. 与项目功能的接口映射

| 项目功能 | 推荐文档 |
|---|---|
| 飞书 Bot 接入 OpenClaw | OpenClaw Feishu Channel |
| 用户消息进入记忆系统 | 飞书 `im.message.receive_v1` + OpenClaw `message_received` Hook |
| 主动提醒用户 | 飞书发送消息 API / OpenClaw Feishu Channel |
| 发送“记住 / 忽略 / 忘记”按钮 | 飞书交互式卡片 / 消息卡片 patch |
| 用户说“记住这个偏好” | OpenClaw Tool：`personal_memory.write` + Plugin Hooks |
| 用户说“忘掉这个偏好” | OpenClaw Tool：`personal_memory.forget` |
| Agent 回复前注入个人记忆 | OpenClaw `before_prompt_build` / Active Memory |
| 记录 Agent 代用户操作飞书 | OpenClaw `after_tool_call` Hook |
| 文档编辑 / 创建时间建模 | 飞书 Docx / Drive API |
| 知识库访问 / 更新建模 | 飞书 Wiki API |
| 任务跟进习惯建模 | 飞书 Task API |
| 会议与提醒时间建模 | 飞书 Calendar API |
| 语义检索个人记忆 | OpenClaw Memory Search / 自建 embedding index |
| 外部 Scheduler 触发主动服务 | OpenClaw Webhooks Plugin / 飞书 Send Message API |

---

## 12. 建议阅读顺序

### 第一批：最小闭环

1. OpenClaw Feishu Channel  
   https://docs.openclaw.ai/channels/feishu

2. OpenClaw Tools and Plugins  
   https://docs.openclaw.ai/tools

3. OpenClaw Plugin Hooks  
   https://docs.openclaw.ai/plugins/hooks

4. 飞书发送消息 API  
   https://open.feishu.cn/document/server-docs/im-v1/message/create

5. 飞书接收消息事件  
   https://open.feishu.cn/document/server-docs/im-v1/message/events/receive

6. 飞书 tenant access token  
   https://open.feishu.cn/document/server-docs/authentication-management/access-token/tenant_access_token_internal

### 第二批：多源行为采集

1. 飞书 Docx 创建文档  
   https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document/create

2. 飞书 Wiki 空间列表  
   https://open.feishu.cn/document/server-docs/docs/wiki-v2/space/list

3. 飞书 Task 创建任务  
   https://open.feishu.cn/document/server-docs/task-v2/task/create

4. 飞书 Calendar 创建日程  
   https://open.feishu.cn/document/server-docs/calendar-v4/calendar-event/create

### 第三批：深度记忆融合

1. OpenClaw Memory Overview  
   https://docs.openclaw.ai/concepts/memory

2. OpenClaw Active Memory  
   https://docs.openclaw.ai/concepts/active-memory

3. OpenClaw Memory Search  
   https://docs.openclaw.ai/concepts/memory-search

4. OpenClaw Webhooks Plugin  
   https://docs.openclaw.ai/plugins/webhooks

---

## 13. 推荐落地路线

### P0：最小闭环

目标：证明个人记忆可以在 OpenClaw + 飞书里闭环。

使用资料：

- OpenClaw Feishu Channel
- OpenClaw Tools / Plugins
- 飞书 IM message create API
- 飞书 tenant_access_token API

实现内容：

1. OpenClaw Feishu Channel 接收用户消息。
2. Middleware 记录用户与 Agent 对话。
3. 抽取 `WorkPreferenceMemory` / `ReminderPreferenceMemory`。
4. OpenClaw 回复前调用 `personal_memory.search`。
5. Scheduler 到点后调用飞书 Send Message API 或 OpenClaw message tool 主动提醒。

### P1：多源行为采集

目标：建模 `WorkTimePatternMemory` / `WorkBehaviorMemory`。

使用资料：

- 飞书 Docx API
- 飞书 Wiki API
- 飞书 Task API
- 飞书 Calendar API
- 飞书 CLI 或官方 SDK
- OpenClaw `after_tool_call` / logs / hooks

实现内容：

1. 定时扫描文档、知识库、任务、日历元数据。
2. 捕获 OpenClaw 代用户操作飞书的工具调用日志。
3. 统一转成 `WorkEvent`。
4. 统计行为时间规律和工作流程习惯。

### P2：深度 OpenClaw Memory 融合

目标：让 `PersonalMemory` 成为 OpenClaw 原生可召回记忆。

使用资料：

- OpenClaw Memory Overview
- OpenClaw Memory Search
- OpenClaw Active Memory
- OpenClaw Plugin SDK / memory slot

实现内容：

1. 将 `PersonalMemory.summary` 同步成 Markdown memory 文件。
2. 或实现兼容 `memory_search` / `memory_get` 的插件后端。
3. 启用 Active Memory，让主回复前自动召回个人记忆。

---

## 14. 一句话总结

飞书侧用 **IM 事件订阅 + OpenAPI / SDK / CLI / MCP** 获取办公信号；中间层统一转成 `WorkEvent` 和 `PersonalMemory`；OpenClaw 侧用 **Tool / Plugin / Hook / Active Memory** 把记忆注入回复前流程，并用 **Scheduler + 飞书消息 API / OpenClaw Webhooks** 实现主动服务。
