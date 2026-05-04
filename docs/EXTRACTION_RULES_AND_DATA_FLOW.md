# 行为抽取规则与数据表增量写入说明

版本：P0 正式版 / 1.0.0  
日期：2026-05-04  
适用范围：当前仓库已实现的 P0 能力，以及 P1 后续计划能力边界

## 1. 文档目的

本文档整理当前项目会实际实现哪些行为提取、规则抽取、记忆生成逻辑，以及 SQLite 数据表如何生成、如何增加数据、如何被更新。

当前 P0 阶段的原则是：只基于真实飞书事件、OpenClaw Hook 事件、带鉴权的标准事件入口和真实提醒发送结果生成数据，不使用 mock 飞书或 mock OpenClaw 事件作为正式能力。

## 2. 当前 P0 会提取的行为类型

P0 已实现的行为提取集中在显式文本表达和提醒闭环，不做复杂隐式办公行为分析。

| 行为类型 | 输入来源 | 当前是否实现 | 生成结果 |
| --- | --- | --- | --- |
| 显式工作偏好 | 飞书消息、OpenClaw message 事件 | 已实现 | WorkPreferenceMemory |
| 显式提醒偏好 | 飞书消息、OpenClaw message 事件、/reminder/schedule | 已实现 | ReminderPreferenceMemory + reminder_jobs |
| 忘记记忆 | 飞书消息、OpenClaw message 事件、/memory/forget | 已实现 | 相关 personal_memories 标记为 deleted |
| 取消提醒 | 飞书消息、OpenClaw message 事件、/memory/forget | 已实现 | ReminderPreferenceMemory 标记为 deleted，reminder_jobs 标记为 cancelled |
| OpenClaw 工具或对话事件证据 | /events/ingest | 已实现 | work_events |
| 飞书文本消息证据 | /integrations/feishu/events | 已实现 | work_events |
| 主动提醒发送结果 | /proactive/trigger 或后台 Scheduler | 已实现 | work_events + reminder_jobs 更新 |
| 敏感信息脱敏 | 飞书消息、OpenClaw 事件、提醒发送 | 已实现 | content_json.summary.text 被脱敏，privacy_level=sensitive |
| 文档编辑时间规律 | 飞书文档元数据扫描 | P1 计划 | WorkTimePatternMemory candidate |
| 任务跟进习惯 | 飞书任务元数据扫描 | P1 计划 | WorkBehaviorMemory candidate |
| 日历会议后整理习惯 | 飞书日历元数据扫描 | P1 计划 | WorkBehaviorMemory / ReminderPreferenceMemory candidate |
| 知识库查询路径习惯 | 飞书知识库元数据扫描 | P1 计划 | WorkBehaviorMemory candidate |

## 3. 当前 P0 不会提取的行为

当前版本不会把以下能力包装成已实现：

1. 不从模拟文档编辑事件中生成时间规律。
2. 不分析飞书全量文档正文。
3. 不分析企业全量聊天记录。
4. 不基于 embedding 做语义合并。
5. 不自动生成团队记忆。
6. 不从单次弱行为事件直接生成长期行为习惯。

## 4. 事件标准化规则

所有输入先标准化为 WorkEvent，再进入 work_events 表。

### 4.1 OpenClaw 事件标准化

入口：

```text
POST /events/ingest
```

事件来源：

```text
source = openclaw
```

标准化规则：

| 字段 | 生成规则 |
| --- | --- |
| event_type | 优先使用 payload.event_type；否则使用 `${type}:${action}` |
| source_event_id | 优先使用 source_event_id、event_id、object_id、metadata.messageId、metadata.message_id |
| event_id | `sha256("openclaw:" + source_event_id)` |
| user_id | 优先使用 payload.user_id、metadata.senderId、metadata.open_id、context.from、context.to、sessionKey |
| actor_type | payload.actor_type 优先；否则 `message:sent` 或包含 tool 的事件为 `agent_on_behalf_of_user`，其他为 `user` |
| object_type | payload.object_type 优先；message 事件为 `message`，其他默认为 `tool_call` |
| object_id | object_id、metadata.messageId、metadata.message_id、source_event_id |
| work_type | payload.work_type；未提供则为 `general` |
| timestamp | payload.timestamp；缺失时使用当前 UTC 时间 |
| content_json.summary.text | 从 payload.text、payload.content、context.content、context.bodyForAgent、context.transcript 中取第一段文本并脱敏 |
| privacy_level | 文本脱敏后发生变化则为 `sensitive`，否则为 `normal` |

### 4.2 飞书消息事件标准化

入口：

```text
POST /integrations/feishu/events
```

事件来源：

```text
source = feishu
event_type = im.message.receive_v1
```

标准化规则：

| 字段 | 生成规则 |
| --- | --- |
| event_id | `sha256("feishu:" + message.message_id)` |
| user_id | sender_id.open_id 优先，其次 union_id、user_id |
| tenant_id | sender.tenant_key、data.tenant_key 或 header.tenant_key |
| actor_type | 固定为 `user` |
| object_type | 固定为 `message` |
| object_id | message.message_id |
| work_type | 当前固定为 `general` |
| timestamp | message.create_time |
| content_json.summary.text | 文本消息 content.text；非文本消息不取正文 |
| content_json.metadata | chat_id、chat_type、thread_id、root_id、parent_id、sender_type、feishu_event_id |

## 5. 文本脱敏规则

文本进入长期流程前会先执行脱敏。

| 规则 | 匹配内容 | 替换结果 |
| --- | --- | --- |
| 私钥块 | `-----BEGIN ... PRIVATE KEY-----` 到 `-----END ... PRIVATE KEY-----` | `[REDACTED_PRIVATE_KEY]` |
| Bearer token | `Bearer <token>` | `Bearer [REDACTED_SECRET]` |
| 密钥赋值 | password、passwd、token、secret、api_key、access_token 等赋值 | `key=[REDACTED_SECRET]` |
| 邮箱 | 常见邮箱格式 | `[REDACTED_EMAIL]` |
| 电话 | 9 位以上电话号码模式 | `[REDACTED_PHONE]` |

如果文本包含 `[REDACTED_SECRET]` 或 `[REDACTED_PRIVATE_KEY]`，显式记忆抽取会直接跳过，不会写入长期记忆。

## 6. 显式记忆抽取规则

当前显式抽取器只从 `WorkEvent.content_json.summary.text` 读取文本。

处理顺序非常重要：

1. 空文本或强敏感文本：跳过。
2. 取消提醒：优先处理。
3. 忘记记忆：其次处理。
4. 提醒偏好：再次处理。
5. 工作偏好：最后处理。
6. 未命中任何规则：只保留 work_events，不生成长期记忆。

### 6.1 取消提醒规则

触发关键词：

```text
别提醒
不要提醒
不用提醒
取消提醒
不要再提醒
```

行为：

1. 从文本中移除触发关键词，得到 query。
2. memory_category 固定为 `ReminderPreferenceMemory`。
3. work_type 使用 query 进行识别。
4. 如果 query 是空、`这个`、`这条`、`它`、`此提醒`，则视为泛化取消提醒。
5. 匹配到的提醒记忆标记为 `deleted`。
6. 关联的 active 或 paused reminder_jobs 标记为 `cancelled`。
7. 如果取消事件来自真实 WorkEvent，则写入 `memory_evidence_links.relation_type = deleted_by`。
8. 写入 `memory_audit_logs.action = delete`。

示例：

```text
以后别提醒这个了
取消提醒写周报
不要再提醒我周报
```

### 6.2 忘记记忆规则

触发关键词：

```text
忘掉
忘记
```

类别识别：

| query 内容 | memory_category |
| --- | --- |
| 包含 `提醒` | ReminderPreferenceMemory |
| 包含 `偏好`、`格式`、`喜欢` | WorkPreferenceMemory |
| 其他 | 不限定类别 |

行为：

1. 从文本中移除 `忘掉` 或 `忘记`，得到 query。
2. 根据 query 推断 memory_category。
3. 根据 query 推断 work_type。
4. 匹配 active、candidate、reinforced 状态的记忆。
5. 匹配结果标记为 `deleted`。
6. 关联 reminder_jobs 标记为 `cancelled`。
7. 写入 audit 日志。

示例：

```text
忘掉我的周报格式偏好
忘记这个提醒
```

### 6.3 提醒偏好规则

触发关键词：

```text
提醒我
```

行为：

1. 调用 ReminderParser 解析时间。
2. 从 `提醒我` 后截取 reminder_text。
3. 生成 `ReminderPreferenceMemory`。
4. 如果能解析出 schedule，则同步生成 `reminder_jobs`。
5. 如果不能解析出 schedule，仍生成提醒偏好记忆，但不会生成提醒任务。

自动抽取生成的 content_json：

```json
{
  "summary": "写周报",
  "reminder_text": "写周报",
  "normalized_key": "<work_type>:reminder:<normalized_text_with_unique_suffix>",
  "source_text": "每周五上午提醒我写周报",
  "extractor": "rules_v0_3"
}
```

置信度：

| 情况 | confidence |
| --- | --- |
| 能解析出提醒时间 | 0.9 |
| 不能解析出提醒时间 | 0.7 |

注意：自动抽取的提醒 normalized_key 会加入时间后缀，目的是让用户多次说“提醒我吃饭”时可以形成多个独立任务。

### 6.4 工作偏好规则

触发关键词：

```text
以后
今后
我喜欢
记住
不要再
```

行为：

1. 从文本中移除触发关键词，得到 preference。
2. 生成 `WorkPreferenceMemory`。
3. 如果文本包含 `不要再`，polarity 为 `negative`；否则为 `positive`。
4. work_type 根据全文识别。
5. normalized_key 固定为 `<work_type>:preference`。
6. 同一用户、同一 memory_category、同一 work_type、同一 normalized_key 下，新偏好会替换旧偏好。

自动抽取生成的 content_json：

```json
{
  "summary": "我的周报先写结论，再写风险",
  "preference": "我的周报先写结论，再写风险",
  "polarity": "positive",
  "normalized_key": "weekly_report:preference",
  "source_text": "以后我的周报先写结论，再写风险",
  "extractor": "rules_v0_3"
}
```

置信度：

```text
confidence = 0.85
status = active
```

示例：

```text
以后我的周报先写结论，再写风险
今后会议纪要都列 Action Items
我喜欢文档写得简洁一点
记住正式输出要生成飞书文档
不要再用很长的铺垫
```

## 7. work_type 识别规则

当前 work_type 由关键词规则识别。

| work_type | 命中关键词 |
| --- | --- |
| weekly_report | `周报`、`weekly report`、`weekly_report` |
| meeting_minutes | `会议纪要`、`纪要`、`meeting minutes` |
| document_writing | `文档`、`文章`、`方案`、`draft` |
| task_followup | `任务`、`跟进`、`待办`、`follow up`、`todo` |
| knowledge_lookup | `知识库`、`查询`、`检索`、`搜索`、`lookup` |
| general | 未命中以上规则 |

## 8. 提醒时间解析规则

ReminderParser 支持以下时间表达。

### 8.1 每周提醒

匹配规则：

```text
每周[一二三四五六日天]
```

weekday 映射：

| 文本 | weekday |
| --- | --- |
| 一 | 0 |
| 二 | 1 |
| 三 | 2 |
| 四 | 3 |
| 五 | 4 |
| 六 | 5 |
| 日 / 天 | 6 |

生成：

```text
schedule_type = weekly
next_run_at = 下一个匹配星期与时间
```

### 8.2 每日提醒

匹配规则：

```text
每天
每日
```

生成：

```text
schedule_type = daily
next_run_at = 今天或明天的指定时间
```

### 8.3 今天 / 明天一次性提醒

匹配规则：

```text
今天
明天
```

生成：

```text
schedule_type = once
```

如果今天指定时间已经过去，则顺延一天。

### 8.4 指定日期一次性提醒

匹配规则：

```text
YYYY-M-D
YYYY-MM-DD
```

生成：

```text
schedule_type = once
next_run_at = 指定日期 + 指定时间
```

### 8.5 时间点解析

匹配规则：

```text
(\d{1,2})\s*[:：点号]\s*(\d{1,2})?
```

时间修正：

| 文本 | 规则 |
| --- | --- |
| 下午 + 小于 12 的小时 | 小时 + 12 |
| 晚上 / 晚间 + 小于 12 的小时 | 小时 + 12 |
| 只有下午，没有具体时间 | 15:00 |
| 只有晚上 / 晚间，没有具体时间 | 20:00 |
| 没有具体时间 | 09:00 |

## 9. 记忆写入与冲突处理规则

所有长期记忆必须至少关联一个 evidence_event_id。

### 9.1 写入新记忆

触发来源：

1. `/events/ingest` 自动抽取。
2. `/integrations/feishu/events` 自动抽取。
3. `/memory/write` 手动写入。
4. `/reminder/schedule` 手动创建提醒。

写入流程：

1. 校验 memory_category、status、confidence。
2. 校验 evidence_event_ids 均存在于 work_events。
3. 根据 normalized_key 查找同用户、同类别、同 work_type 的 active/candidate/reinforced 记忆。
4. 如果已有等价 summary，则不新建记忆，只追加 evidence link。
5. 如果 normalized_key 相同但 summary 不同，则旧记忆标记为 replaced，新建记忆。
6. 写入 personal_memories。
7. 写入 memory_evidence_links。
8. 写入 memory_audit_logs。
9. 如果是带 schedule 的 ReminderPreferenceMemory，写入 reminder_jobs。

### 9.2 强化已有记忆

条件：

1. normalized_key 相同。
2. summary 规整后完全一致。

行为：

1. 不新建 personal_memories。
2. 给已有记忆增加 `reinforced_by` evidence link。
3. 如果原状态是 active，则升级为 reinforced。
4. 写入 audit action=update。

### 9.3 替换冲突记忆

条件：

1. 同 user_id。
2. 同 memory_category。
3. 同 work_type。
4. normalized_key 相同。
5. summary 不同。

行为：

1. 旧记忆 status 更新为 replaced。
2. 新记忆 status 为 active。
3. 旧记忆写入 audit action=replace。
4. 新记忆写入 audit action=create。

示例：

```text
旧：以后我的周报先写结论，再写风险
新：以后我的周报先写风险，再写结论
```

结果：旧记忆 replaced，新记忆 active。

## 10. 记忆检索规则

入口：

```text
POST /memory/search
```

默认检索类别：

```text
WorkPreferenceMemory
ReminderPreferenceMemory
```

候选范围：

1. user_id 必须匹配。
2. status 只取 candidate、active、reinforced。
3. memory_category 必须在请求类别内。

相关性过滤：

1. 记忆 work_type 与目标 work_type 一致：保留。
2. 记忆 work_type 是 general：保留。
3. 其他 work_type：只有关键词命中时保留。

排序评分因素：

| 因素 | 当前权重逻辑 |
| --- | --- |
| work_type 精确命中 | +20，general 命中 +10 |
| general 记忆兜底 | +6 |
| 跨 work_type 关键词命中 | +2 |
| reinforced 状态 | +12 |
| active 状态 | +10 |
| candidate 状态 | +1 |
| WorkPreferenceMemory | +2 |
| ReminderPreferenceMemory | +1.5 |
| confidence | `confidence * 5` |
| evidence 数量 | 最多 4 条，每条 +0.75 |
| query 关键词命中 | 最多 +6 |
| 新鲜度 | 1 天内 +3，7 天内 +2，30 天内 +1 |

Context Pack 规则：

1. 空结果返回空字符串。
2. 不暴露 memory_id。
3. 不暴露 content_json。
4. 不暴露完整 evidence 正文。
5. 最多输出 7 行。
6. 每条摘要最多约 120 字。
7. 固定包含约束：历史偏好仅在不冲突时使用，当前用户请求优先。

## 11. 主动提醒发送规则

入口：

```text
POST /proactive/trigger
```

或后台 Scheduler 定时调用。

处理流程：

1. 查询 status=active 且 next_run_at <= now 的 reminder_jobs。
2. 将任务临时标记为 paused，并在 payload_json 中写入 dispatching、attempt_id、attempt_count。
3. 读取 reminder_text。
4. 再次脱敏检查。
5. 如果包含强敏感内容，不发送，记录失败事件。
6. 调用飞书 Bot 发送文本消息。
7. 发送成功后记录成功 work_event。
8. once 任务标记为 triggered。
9. weekly/daily 任务保持 active，并推进 next_run_at。
10. 发送失败后任务保持 paused，并记录失败 work_event。

发送消息格式：

```text
提醒：<reminder_text>
```

成功事件：

```text
source = feishu
event_type = im.message.create_v1
actor_type = system
object_type = message
```

失败事件：

```text
source = longmemory
event_type = reminder.delivery.failed
actor_type = system
object_type = reminder_job
```

## 12. 当前 SQLite 数据表

当前数据库由 Alembic 迁移 `0001_initial_schema.py` 创建，共 5 张业务表。

| 表名 | 用途 |
| --- | --- |
| work_events | 存储标准化事件和证据 |
| personal_memories | 存储四类个人工作记忆 |
| memory_evidence_links | 记录记忆和证据之间的关系 |
| reminder_jobs | 存储主动提醒任务 |
| memory_audit_logs | 存储记忆变更审计日志 |

## 13. work_events 表

用途：保存所有真实输入、系统发送结果和失败结果，是所有长期记忆的证据来源。

### 13.1 字段

| 字段 | 说明 |
| --- | --- |
| event_id | 主键，来源 + source_event_id 的哈希 |
| user_id | 用户 ID |
| tenant_id | 租户 ID，可为空 |
| source | openclaw、feishu、longmemory 等 |
| event_type | 标准化事件类型 |
| actor_type | user、agent_on_behalf_of_user、system |
| object_type | message、tool_call、reminder_job 等 |
| object_id | 来源对象 ID |
| work_type | 工作类型 |
| timestamp | 事件发生时间 |
| content_json | 摘要和元数据 |
| privacy_level | normal 或 sensitive |
| created_at | 入库时间 |

### 13.2 数据如何增加

| 触发动作 | 写入方式 |
| --- | --- |
| OpenClaw 调用 /events/ingest | normalize_openclaw_event 后 insert |
| 飞书事件回调 | normalize_feishu_message 后 insert |
| /memory/write 提供 evidence_event | 先标准化为 OpenClaw 事件再 insert |
| /memory/forget 提供 evidence_event | 先标准化为 OpenClaw 事件再 insert |
| /reminder/schedule 提供 evidence_event | 先标准化为 OpenClaw 事件再 insert |
| 提醒发送成功 | ReminderDispatcher 生成 im.message.create_v1 事件 |
| 提醒发送失败 | ReminderDispatcher 生成 reminder.delivery.failed 事件 |

### 13.3 幂等规则

插入使用 SQLite `OR IGNORE`。如果 event_id 已存在，不重复创建，也不会再次触发自动记忆抽取。

## 14. personal_memories 表

用途：统一保存四类 PersonalMemory。

### 14.1 字段

| 字段 | 说明 |
| --- | --- |
| memory_id | 主键 |
| user_id | 用户 ID |
| memory_category | WorkPreferenceMemory、WorkTimePatternMemory、WorkBehaviorMemory、ReminderPreferenceMemory |
| work_type | weekly_report、meeting_minutes、document_writing、task_followup、knowledge_lookup、general |
| content_json | 摘要、偏好、提醒文本、normalized_key 等 |
| source_channel | openclaw、feishu 等 |
| source_signal_type | explicit_statement 等 |
| confidence | 0 到 1 |
| status | candidate、active、reinforced、outdated、replaced、deleted |
| created_at | 创建时间 |
| updated_at | 更新时间 |

### 14.2 数据如何增加

| 触发动作 | 生成内容 |
| --- | --- |
| 显式偏好自动抽取 | WorkPreferenceMemory |
| 显式提醒自动抽取 | ReminderPreferenceMemory |
| /memory/write | 请求指定的 memory_category |
| /reminder/schedule | ReminderPreferenceMemory |

### 14.3 数据如何更新

| 触发动作 | 更新结果 |
| --- | --- |
| 等价记忆再次出现 | status 可能从 active 变为 reinforced，updated_at 更新 |
| 冲突偏好写入 | 旧记忆 status=replaced，新建 active 记忆 |
| /memory/update | 更新 content_json、work_type、confidence、status |
| 忘记或取消提醒 | status=deleted |

## 15. memory_evidence_links 表

用途：记录 personal_memories 和 work_events 的证据关系。

### 15.1 字段

| 字段 | 说明 |
| --- | --- |
| memory_id | 记忆 ID |
| event_id | 事件 ID |
| relation_type | 证据关系 |
| created_at | 创建时间 |

### 15.2 relation_type

| relation_type | 生成场景 |
| --- | --- |
| created_from | 新记忆创建时 |
| reinforced_by | 等价记忆再次出现时 |
| deleted_by | 忘记或取消提醒时 |

当前迁移和设计文档允许更多 relation_type，例如 replaced_by，但当前实现主要使用以上三类。

### 15.3 数据如何增加

1. 新建记忆时，为所有 evidence_event_ids 写入 created_from。
2. 强化记忆时，为新的 evidence_event_ids 写入 reinforced_by。
3. 删除记忆时，如果有 evidence_event_id，写入 deleted_by。

插入同样使用 `OR IGNORE`，避免重复证据关系。

## 16. reminder_jobs 表

用途：持久化主动提醒任务。

### 16.1 字段

| 字段 | 说明 |
| --- | --- |
| job_id | 主键 |
| user_id | 用户 ID |
| memory_id | 对应 ReminderPreferenceMemory |
| schedule_type | once、weekly、daily、cron_like |
| timezone | 默认 Asia/Shanghai |
| next_run_at | 下次触发时间，保存为 UTC |
| payload_json | reminder_text、source_text、发送状态、飞书接收者等 |
| status | active、paused、triggered、cancelled |
| last_run_at | 最近一次触发时间 |
| created_at | 创建时间 |
| updated_at | 更新时间 |

### 16.2 数据如何增加

只有在写入 ReminderPreferenceMemory 且存在 reminder_schedule 时才创建。

来源：

1. 用户消息中包含可解析时间的 `提醒我`。
2. `/reminder/schedule` 提供可解析 reminder_text。
3. `/reminder/schedule` 显式提供 schedule_type + next_run_at。

### 16.3 数据如何更新

| 触发动作 | 更新结果 |
| --- | --- |
| Scheduler claim 到期任务 | status=paused，payload_json.delivery_status=dispatching |
| once 提醒发送成功 | status=triggered，last_run_at 更新，写入 sent_event_id |
| daily/weekly 提醒发送成功 | status=active，last_run_at 更新，next_run_at 顺延 |
| 发送失败 | status=paused，写入 failed_event_id、last_error |
| 忘记或取消提醒 | status=cancelled |

## 17. memory_audit_logs 表

用途：记录记忆变更历史，支撑审计和解释。

### 17.1 字段

| 字段 | 说明 |
| --- | --- |
| audit_id | 主键 |
| memory_id | 记忆 ID |
| user_id | 用户 ID |
| action | create、update、replace、delete、restore |
| before_json | 变更前 |
| after_json | 变更后 |
| created_at | 创建时间 |

### 17.2 数据如何增加

| action | 生成场景 |
| --- | --- |
| create | 新建 personal_memories |
| update | /memory/update 或等价记忆强化 |
| replace | 冲突记忆被新记忆替换 |
| delete | /memory/forget 或取消提醒 |
| restore | 当前表结构支持，当前 P0 暂未实现恢复入口 |

## 18. 当前端到端数据生成示例

### 18.1 用户表达工作偏好

输入：

```text
以后我的周报先写结论，再写风险
```

数据变化：

1. work_events 新增一条 OpenClaw 或 Feishu message 事件。
2. personal_memories 新增一条 WorkPreferenceMemory。
3. memory_evidence_links 新增 created_from 关系。
4. memory_audit_logs 新增 create 日志。

### 18.2 用户创建周期提醒

输入：

```text
每周五上午提醒我写周报
```

数据变化：

1. work_events 新增一条消息事件。
2. personal_memories 新增一条 ReminderPreferenceMemory。
3. memory_evidence_links 新增 created_from 关系。
4. reminder_jobs 新增一条 weekly active 任务。
5. memory_audit_logs 新增 create 日志。

### 18.3 用户取消提醒

输入：

```text
以后别提醒这个了
```

数据变化：

1. work_events 新增一条取消提醒消息事件。
2. personal_memories 中匹配的 ReminderPreferenceMemory 更新为 deleted。
3. reminder_jobs 中关联任务更新为 cancelled。
4. memory_evidence_links 新增 deleted_by 关系。
5. memory_audit_logs 新增 delete 日志。

### 18.4 到期提醒发送成功

触发：

```text
POST /proactive/trigger
```

数据变化：

1. reminder_jobs 到期任务先更新为 paused + dispatching。
2. 飞书 Bot 发送文本消息。
3. work_events 新增一条 `source=feishu`、`event_type=im.message.create_v1` 的发送成功事件。
4. once 任务更新为 triggered；weekly/daily 任务更新为 active 并推进 next_run_at。
5. reminder_jobs.payload_json 写入 sent_event_id、feishu_message_id、last_sent_at。

### 18.5 到期提醒发送失败

触发：

```text
POST /proactive/trigger
```

数据变化：

1. reminder_jobs 到期任务先更新为 paused + dispatching。
2. 飞书发送失败或敏感内容拦截。
3. work_events 新增一条 `source=longmemory`、`event_type=reminder.delivery.failed` 的失败事件。
4. reminder_jobs 保持 paused。
5. reminder_jobs.payload_json 写入 failed_event_id、last_error、last_failed_at。

## 19. P1 后续行为抽取计划

P1 将在真实飞书 API 授权基础上增加隐式行为抽取。

| 行为 | 数据来源 | 候选记忆 | 生成条件建议 |
| --- | --- | --- | --- |
| 周五上午反复编辑周报 | 飞书文档元数据 | WorkTimePatternMemory | 同一 work_type 在多个周期间重复出现 |
| 会议后整理纪要 | 日历会议结束时间 + 文档创建或消息反馈 | WorkBehaviorMemory / ReminderPreferenceMemory | 会议后固定时间窗口内多次出现纪要行为 |
| 任务多日未更新后跟进 | 飞书任务状态和更新时间 | ReminderPreferenceMemory candidate | 多次任务延期或停滞后用户跟进 |
| 先查知识库再写方案 | 知识库访问元数据 + 文档创建元数据 | WorkBehaviorMemory | 多次出现访问知识库后创建文档 |
| 正式输出沉淀飞书文档 | OpenClaw tool_call + 飞书文档创建 | WorkBehaviorMemory | 多次由 Agent 代用户创建文档 |

P1 隐式行为记忆默认应进入 candidate 状态，必须提供证据链和用户确认入口，不能单次事件直接变为 active。

## 20. 实现文件索引

| 能力 | 主要文件 |
| --- | --- |
| OpenClaw 事件标准化 | `src/feishu_campus_longmemory/events/normalize.py` |
| 飞书消息标准化 | `src/feishu_campus_longmemory/events/normalize.py` |
| 文本脱敏 | `src/feishu_campus_longmemory/events/privacy.py` |
| Evidence Store | `src/feishu_campus_longmemory/events/store.py` |
| 显式记忆抽取 | `src/feishu_campus_longmemory/memory/extractor.py` |
| 提醒时间解析 | `src/feishu_campus_longmemory/memory/reminder.py` |
| 记忆写入与冲突处理 | `src/feishu_campus_longmemory/memory/store.py` |
| 记忆检索与 Context Pack | `src/feishu_campus_longmemory/memory/retriever.py` |
| 主动提醒发送 | `src/feishu_campus_longmemory/proactive/dispatcher.py` |
| 飞书消息发送 | `src/feishu_campus_longmemory/proactive/feishu.py` |
| SQLite 表定义 | `src/feishu_campus_longmemory/tables.py` |
| Alembic 迁移 | `alembic/versions/0001_initial_schema.py` |
