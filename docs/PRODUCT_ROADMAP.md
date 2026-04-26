# Personal Work Memory Middleware 产品方案与迭代计划

版本：V1.0  
日期：2026-04-26  
项目：feishu-campus-longmemory  
赛道：飞书 AI 校园大赛 - 企业级 Agent 存储系统  
方向：个人工作习惯与偏好记忆

## 1. 文档目的

本文档用于定义 Personal Work Memory Middleware 的产品定位、功能边界、核心架构、版本规划与验收标准，作为后续项目实现的主要迭代依据。

本项目要求以可正式实现为目标，而不是通过模拟接口、mock 数据或烟雾测试证明概念成立。P0 阶段数据库限制为 SQLite，后续版本可根据需求引入向量索引、更多飞书数据源和团队记忆能力。

## 2. 项目理解

Personal Work Memory Middleware 不是一个通用聊天记忆插件，也不是替代飞书知识库或 OpenClaw Agent Framework 的完整系统。它是位于飞书办公生态和 OpenClaw Agent Runtime 之间的个人工作记忆中间层。

系统的核心价值是把用户在真实办公环境中的个人偏好、时间规律、行为习惯和提醒需求沉淀为可检索、可解释、可管理的长期记忆，并在 OpenClaw 执行任务前或主动服务触发时提供个性化上下文。

项目关注三类真实信号来源：

1. 用户在飞书或 OpenClaw 中明确表达的工作偏好与提醒需求。
2. 用户与 Agent 的真实对话、工具调用结果和反馈。
3. 后续通过飞书文档、任务、日历、知识库等 API 获取的真实办公行为元数据。

系统不应将所有输入直接写入长期记忆。所有信号应先标准化为 WorkEvent，并进入 Evidence Store。长期记忆必须由证据、规则、抽取逻辑或用户确认共同支撑。

## 3. 产品定义

一句话定义：

> Personal Work Memory Middleware 是飞书与 OpenClaw Agent Runtime 之间的个人工作记忆服务，负责采集真实办公信号，抽取个人工作偏好、时间规律、行为习惯和提醒偏好，并在 Agent 回复前或主动服务触发时提供个性化上下文。

核心能力包括：

1. 事件采集：接收飞书和 OpenClaw 的真实消息、反馈、工具调用事件。
2. 证据存储：所有输入先进入 Evidence Store，形成可追溯证据。
3. 记忆抽取：从显式表达和真实行为中抽取候选记忆。
4. 记忆管理：支持写入、更新、替换、停用和删除。
5. 记忆检索：按用户、工作类型、记忆类型、状态、置信度和时间召回。
6. Prompt 注入：生成短小、相关、可控的 Memory Context Pack。
7. 主动服务：基于提醒偏好和调度器触发飞书消息或 OpenClaw 请求。
8. 可解释性：每条记忆可以回溯到具体事件证据。

## 4. 产品边界

### 4.1 当前项目做什么

1. 建立个人工作记忆中间层。
2. 接入真实飞书或 OpenClaw 事件。
3. 存储 WorkEvent、Evidence 和 PersonalMemory。
4. 支持显式偏好与提醒偏好的正式闭环。
5. 在 OpenClaw 执行任务前提供 Memory Context Pack。
6. 基于真实调度器和飞书 Bot 实现主动提醒。

### 4.2 当前项目不做什么

1. 不替代 OpenClaw Agent Framework。
2. 不替代飞书知识库、文档或任务系统。
3. 不无授权监听企业全量内容。
4. 不默认读取或向量化全量聊天记录和文档正文。
5. P0 不依赖 Embedding 或外部向量数据库。
6. P0 不用模拟飞书文档行为证明时间规律。
7. P0 不实现团队记忆和组织级知识治理。

## 5. 个人工作记忆模型

系统统一维护四类 Personal Work Memory：

| 记忆类型 | 说明 | Agent 价值 |
| --- | --- | --- |
| WorkPreferenceMemory | 用户希望成果如何生成、呈现、沟通和交付 | 个性化输出、工具选择、语气和结构适配 |
| WorkTimePatternMemory | 用户通常在什么时间处理什么工作 | 选择合适提醒时间，降低打扰 |
| WorkBehaviorMemory | 用户通常按什么流程完成工作 | 适配工作流程，建议下一步动作 |
| ReminderPreferenceMemory | 什么事情需要未来主动提醒、跟进或准备 | 定时提醒、条件触发、主动服务闭环 |

P0 阶段重点正式实现 WorkPreferenceMemory 和 ReminderPreferenceMemory。WorkTimePatternMemory 与 WorkBehaviorMemory 可保留数据模型，但不应在没有真实行为数据的情况下声称完成。

## 6. 核心数据流

### 6.1 写入流

1. 用户在飞书或 OpenClaw 中产生真实消息、反馈或工具调用事件。
2. Event Collector 接收事件并校验来源。
3. WorkEvent Normalizer 将输入标准化。
4. Evidence Store 持久化原始证据和摘要。
5. Extractor 判断事件是否值得形成候选记忆。
6. Memory Store 写入、更新或替换 PersonalMemory。
7. Memory Evidence Link 记录记忆与证据的关系。

### 6.2 读取流

1. 用户向 OpenClaw 发起任务。
2. OpenClaw Adapter 携带 user_id、query、session_id 和可选 work_type 请求记忆。
3. Retriever 按结构化字段检索 SQLite。
4. 系统按相关性、置信度、新鲜度和证据数量排序。
5. Context Builder 生成 Memory Context Pack。
6. OpenClaw 将上下文注入 Prompt 并生成个性化回复。

### 6.3 主动服务流

1. Scheduler 扫描 active 状态的 reminder_jobs。
2. 命中时间或条件后，系统召回相关个人记忆。
3. 系统构造 Proactive Service Request。
4. OpenClaw 或中间层生成提醒内容。
5. 飞书 Bot 发送真实消息给用户。
6. 发送结果和用户反馈继续写入 Evidence Store。

## 7. P0 技术约束

P0 阶段必须满足以下约束：

1. 数据库使用 SQLite。
2. 事件接入必须来自真实飞书或 OpenClaw 通道。
3. 不以 mock 接口、模拟事件或固定样例作为正式能力。
4. 不引入外部向量数据库作为核心依赖。
5. 不默认采集敏感个人信息、密钥、薪资、绩效评价等内容。
6. 每条长期记忆必须有来源证据。
7. 用户必须能够更新、停用或删除个人记忆。

## 8. P0 推荐数据表

### 8.1 work_events

用于存储所有标准化事件和证据。

关键字段：

| 字段 | 说明 |
| --- | --- |
| event_id | 事件唯一 ID |
| user_id | 用户 ID |
| tenant_id | 租户 ID |
| source | 事件来源 |
| event_type | 事件类型 |
| actor_type | user 或 agent_on_behalf_of_user |
| object_type | message、doc、task、calendar 等 |
| object_id | 来源对象 ID |
| work_type | 工作类型 |
| timestamp | 事件发生时间 |
| content_json | 事件内容、摘要和元数据 |
| privacy_level | 隐私级别 |
| created_at | 入库时间 |

### 8.2 personal_memories

用于统一存储四类个人工作记忆。

关键字段：

| 字段 | 说明 |
| --- | --- |
| memory_id | 记忆唯一 ID |
| user_id | 用户 ID |
| memory_category | 记忆类型 |
| work_type | 工作类型 |
| content_json | 记忆摘要和结构化详情 |
| source_channel | 来源通道 |
| source_signal_type | explicit_statement、behavior_pattern 等 |
| confidence | 置信度 |
| status | candidate、active、reinforced、outdated、replaced、deleted |
| created_at | 创建时间 |
| updated_at | 更新时间 |

### 8.3 memory_evidence_links

用于记录记忆和证据之间的关系。

关键字段：

| 字段 | 说明 |
| --- | --- |
| memory_id | 记忆 ID |
| event_id | 事件 ID |
| relation_type | created_from、reinforced_by、replaced_by 等 |
| created_at | 创建时间 |

### 8.4 reminder_jobs

用于持久化主动提醒任务。

关键字段：

| 字段 | 说明 |
| --- | --- |
| job_id | 提醒任务 ID |
| user_id | 用户 ID |
| memory_id | 对应 ReminderPreferenceMemory |
| schedule_type | once、weekly、daily、cron_like |
| timezone | 时区 |
| next_run_at | 下次触发时间 |
| payload_json | 提醒内容和上下文 |
| status | active、paused、triggered、cancelled |
| last_run_at | 上次触发时间 |
| created_at | 创建时间 |
| updated_at | 更新时间 |

### 8.5 memory_audit_logs

用于记录记忆变更历史。

关键字段：

| 字段 | 说明 |
| --- | --- |
| audit_id | 审计记录 ID |
| memory_id | 记忆 ID |
| user_id | 用户 ID |
| action | create、update、replace、delete、restore |
| before_json | 变更前内容 |
| after_json | 变更后内容 |
| created_at | 变更时间 |

## 9. API 定义

P0 阶段建议优先实现以下接口：

| 接口 | 调用方 | 用途 |
| --- | --- | --- |
| GET /health | 运维或本地检查 | 服务健康检查 |
| POST /events/ingest | 飞书事件接收器、OpenClaw Hook | 写入 WorkEvent 证据 |
| POST /memory/write | OpenClaw Tool、Extractor | 写入显式个人记忆 |
| POST /memory/search | OpenClaw Adapter | 检索相关个人记忆 |
| POST /memory/update | OpenClaw Tool、用户反馈 | 更新记忆内容或状态 |
| POST /memory/forget | OpenClaw Tool、用户反馈 | 停用或删除记忆 |
| POST /reminder/schedule | Reminder Extractor、OpenClaw Tool | 创建提醒任务 |
| POST /proactive/trigger | Scheduler | 触发主动服务 |

## 10. 版本规划

## 10.1 V0.1 工程基础与本地服务骨架

目标：建立可运行、可维护的正式工程骨架。

应实现内容：

1. 后端服务框架。
2. SQLite 数据库初始化与迁移机制。
3. 基础配置管理。
4. 标准错误处理和日志。
5. 健康检查接口。
6. README 与开发启动说明。

验收标准：

1. 服务可以本地启动。
2. SQLite 表结构可自动初始化。
3. GET /health 正常返回。
4. README 中说明项目定位、环境变量和启动方式。

不做内容：

1. 不接入向量数据库。
2. 不实现飞书文档扫描。
3. 不实现团队记忆。

## 10.2 V0.2 真实事件接入与 Evidence Store

目标：接入真实事件流，建立可追溯证据存储。

应实现内容：

1. POST /events/ingest。
2. 飞书 Bot 消息事件接收。
3. OpenClaw 对话事件或工具调用事件接收。
4. WorkEvent 标准化。
5. 事件去重。
6. 隐私等级标注。
7. Evidence 查询能力，用于调试和解释。

验收标准：

1. 用户在真实飞书或 OpenClaw 中发送消息后，SQLite 中产生 work_events。
2. 重复投递的同一事件不会重复写入。
3. 事件可以追溯来源、用户、会话、时间和内容摘要。

不做内容：

1. 不用手写模拟事件作为正式演示。
2. 不采集无授权的企业全量消息。

## 10.3 V0.3 显式个人记忆抽取与写入

目标：让用户明确说出的偏好和提醒需求转化为长期记忆。

应实现内容：

1. 显式偏好识别。
2. Reminder 请求识别。
3. WorkPreferenceMemory 写入。
4. ReminderPreferenceMemory 写入。
5. POST /memory/write。
6. POST /memory/update。
7. POST /memory/forget。
8. 记忆与证据关联。
9. 基础冲突处理和替换逻辑。

推荐支持表达：

1. "以后..."
2. "我喜欢..."
3. "记住..."
4. "不要再..."
5. "提醒我..."
6. "忘掉..."

验收标准：

1. 用户说"以后我的周报先写结论，再写风险"，系统能写入 WorkPreferenceMemory。
2. 用户说"每周五上午提醒我写周报"，系统能写入 ReminderPreferenceMemory 和 reminder_jobs。
3. 用户说"忘掉我的周报格式偏好"，系统能停用相关记忆。
4. 每条记忆都能查询到来源事件。

不做内容：

1. 不用固定样例硬编码冒充抽取能力。
2. 不把单次弱行为事件直接写成长期习惯。

## 10.4 V0.4 SQLite 结构化检索与 Prompt Context Pack

目标：让 OpenClaw 在执行任务前真实使用个人记忆。

应实现内容：

1. POST /memory/search。
2. 工作类型识别。
3. SQLite 结构化检索。
4. 相关性排序。
5. Memory Context Pack 生成。
6. OpenClaw Adapter 集成。

推荐支持 work_type：

1. weekly_report
2. meeting_minutes
3. document_writing
4. task_followup
5. knowledge_lookup
6. general

排序因素：

1. work_type 命中。
2. memory_category 命中。
3. 置信度。
4. 最近更新时间。
5. 证据数量。
6. 用户确认状态。

验收标准：

1. 用户已有周报偏好后，再说"帮我写这周周报"，OpenClaw 能收到 Memory Context Pack。
2. Context Pack 内容短小，不暴露内部数据库 JSON。
3. 当前请求与历史记忆冲突时，当前请求优先。
4. 没有相关记忆时，系统正常返回空上下文。

不做内容：

1. P0 不强制使用 Embedding。
2. P0 不依赖外部向量数据库。

## 10.5 V0.5 Reminder Scheduler 与主动服务闭环

目标：实现真实主动提醒，而不是只保存提醒配置。

应实现内容：

1. reminder_jobs 持久化。
2. 后台 Scheduler。
3. 一次性提醒。
4. 每周固定时间提醒。
5. 提醒状态管理。
6. 到期后通过飞书 Bot 发送真实消息。
7. 发送结果写回 work_events。
8. 用户反馈继续更新记忆或提醒任务。

验收标准：

1. 用户说"每周五 9:30 提醒我写周报"，系统能持久化提醒。
2. 到达时间后，飞书 Bot 真实发送消息。
3. 发送成功或失败都有事件记录。
4. 用户说"以后别提醒这个了"，提醒任务会停用。

不做内容：

1. 不自动替用户执行高风险操作。
2. 不在没有用户授权的情况下创建或发送正式文档。

## 10.6 P0 正式版 个人显式记忆闭环

目标：交付可正式演示、可真实运行的个人工作记忆最小闭环。

P0 包含：

1. 真实飞书或 OpenClaw 事件接入。
2. SQLite Evidence Store。
3. 四类 PersonalMemory 统一模型。
4. 显式偏好抽取。
5. ReminderPreferenceMemory 抽取。
6. 记忆写入、搜索、更新、删除。
7. Memory Context Pack。
8. Reminder Scheduler。
9. 飞书 Bot 主动提醒。
10. README、接口文档、部署说明和演示脚本。

P0 不包含：

1. 真实全量文档行为分析。
2. 真实知识库访问习惯分析。
3. 复杂时间规律自动发现。
4. Embedding 混合检索。
5. 团队记忆。

P0 总体验收标准：

> 用户在真实飞书或 OpenClaw 中表达偏好，系统写入 SQLite；用户之后发起任务时，OpenClaw 能召回该偏好；用户设置提醒后，系统能在真实时间点通过飞书主动触达。

## 11. P1 真实飞书办公行为采集与隐式记忆

目标：从显式记忆扩展到基于真实办公元数据的隐式行为记忆。

应实现内容：

1. 飞书文档元数据扫描。
2. 飞书任务元数据扫描。
3. 飞书日历元数据扫描。
4. 知识库页面访问或编辑元数据接入。
5. WorkTimePatternMemory 统计生成。
6. WorkBehaviorMemory 候选生成。
7. 用户确认机制。
8. 行为证据解释。
9. 基础记忆管理界面或飞书卡片。

验收标准：

1. 系统基于真实飞书 API 或真实授权数据形成行为证据。
2. 隐式记忆默认进入 candidate 状态。
3. 多次证据支持后，记忆可升级为 active 或 reinforced。
4. 用户能看到系统为什么认为自己有某种时间规律或行为习惯。

不做内容：

1. 不用模拟文档编辑事件证明时间规律。
2. 不读取无授权正文内容。
3. 不默认对全量文档正文做长期存储。

## 12. P1.5 Embedding 与混合检索增强

目标：增强模糊表达、相似记忆合并和跨场景召回能力。

应实现内容：

1. 记忆摘要 Embedding。
2. 证据摘要 Embedding。
3. 结构化检索与语义检索混合召回。
4. 相似记忆合并建议。
5. 冲突检测辅助。
6. 证据语义检索。

可选技术路线：

1. SQLite + FTS5 + sqlite-vec。
2. SQLite + 外部 FAISS。
3. Postgres + pgvector。

原则：

1. Embedding 用于增强召回，不替代结构化记忆模型。
2. 不向量化密钥、密码、薪资、绩效评价等敏感内容。
3. 不默认向量化全量聊天记录或全量文档正文。

## 13. P2 主动服务增强与工作流闭环

目标：从提醒用户升级为准备工作和辅助执行。

应实现内容：

1. 会议结束后提醒整理纪要。
2. 任务长期未更新提醒跟进。
3. 周报自动准备草稿。
4. 周一任务规划草稿。
5. 根据个人偏好选择输出格式、语气和交付位置。
6. 与 OpenClaw 工具调用深度集成。
7. 用户反馈驱动记忆更新。

典型场景：

1. 到周五上午，系统提醒用户准备周报，并询问是否生成草稿。
2. 会议结束后，系统提醒用户整理纪要和 Action Items。
3. 任务多日未更新时，系统提醒用户检查进展。
4. 用户确认后，OpenClaw 创建飞书文档草稿，并将工具调用结果写回 Evidence Store。

## 14. P3 团队记忆与组织级扩展

目标：在个人记忆稳定后扩展到团队和项目维度。

应实现内容：

1. scope 扩展为 personal、team、project。
2. 团队文档规范。
3. 团队会议纪要模板。
4. 项目输出标准。
5. 文档过期预警。
6. owner 风险提醒。
7. 重复问题检测。
8. 新成员知识断层识别。
9. 团队记忆权限和可见性控制。

必须额外设计：

1. 谁可以创建团队记忆。
2. 谁可以修改团队记忆。
3. 谁可以查看证据来源。
4. 哪些内容不能进入团队记忆。
5. 团队记忆与个人记忆冲突时如何处理。

## 15. 安全与隐私原则

1. 默认最小采集。
2. 默认优先存储元数据和摘要，不存储全文。
3. 敏感信息不得写入长期记忆。
4. 用户可以查看、修改、删除个人记忆。
5. 记忆召回时不暴露内部 ID 和完整证据，除非用户请求解释。
6. Agent 使用记忆时，当前用户请求优先于历史记忆。
7. 所有主动服务必须可关闭。

## 16. 评测指标

| 维度 | 指标 | 说明 |
| --- | --- | --- |
| 偏好记忆 | 偏好抽取准确率 | 显式偏好是否被正确分类和结构化 |
| 偏好应用 | 个性化一致性 | Agent 输出是否遵循已记忆偏好 |
| 主动服务 | 提醒命中率 | 是否在正确时间触发提醒 |
| 主动服务 | 打扰率 | 用户是否拒绝或认为提醒不合时宜 |
| 可解释性 | 证据链完整率 | 每条记忆是否能追溯来源 |
| 安全性 | 敏感信息过滤率 | 是否避免敏感内容进入长期记忆 |
| 检索质量 | 相关记忆召回率 | 查询是否召回正确记忆 |
| 可维护性 | 接口和数据模型稳定性 | 是否支持后续扩展 |

## 17. 比赛交付建议

比赛阶段建议聚焦可信、可演示、可解释的正式闭环。

推荐展示路径：

1. 展示真实飞书或 OpenClaw 消息进入 Evidence Store。
2. 展示用户显式偏好被抽取为 PersonalMemory。
3. 展示用户再次发起任务时，OpenClaw 收到 Memory Context Pack。
4. 展示用户设置周期提醒后，Scheduler 在真实时间点触发飞书 Bot 消息。
5. 展示用户反馈后，系统更新或停用记忆。

不建议展示方式：

1. 不用模拟飞书文档编辑事件作为 P0 核心证据。
2. 不把未来规划能力包装成已完成能力。
3. 不将 Embedding 作为 P0 必需卖点。

## 18. 后续实现顺序

建议后续开发按以下顺序推进：

1. 完成 V0.1 工程骨架。
2. 完成 SQLite schema 和迁移机制。
3. 完成真实事件接入与 Evidence Store。
4. 完成显式记忆抽取和写入。
5. 完成记忆检索和 Memory Context Pack。
6. 完成 Reminder Scheduler 和飞书 Bot 主动提醒。
7. 整理 P0 演示脚本和部署文档。
8. 再进入 P1 飞书真实元数据扫描。

## 19. 结论

本项目的合理落地路径是先做小而真实的个人记忆闭环，再逐步扩展到隐式行为记忆、语义检索、主动工作流和团队记忆。

P0 的核心不是证明系统能保存一段文本，而是证明以下闭环可以正式运行：

> 真实事件进入系统 -> SQLite 保存证据 -> 抽取个人记忆 -> OpenClaw 任务前召回 -> Agent 个性化执行 -> Scheduler 主动提醒 -> 用户反馈更新记忆。

在 SQLite 限制下，P0 完全可以实现正式版本。需要严格避免将 mock 事件、模拟接口或演示脚本包装成正式能力。P0 应以真实接入、结构化存储、可解释证据链和可管理记忆作为主要竞争力。
