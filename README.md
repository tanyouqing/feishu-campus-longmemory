# feishu-campus-longmemory

飞书 AI 校园大赛 - 企业级 Agent 存储系统赛题参赛项目。

本项目实现一个面向飞书与 OpenClaw Agent Runtime 的 Personal Work Memory Middleware，用于采集真实办公信号，沉淀个人工作记忆，并在 Agent 回复前或主动服务触发时提供个性化上下文。

## 当前版本：用户建模 V1.1 / 1.1.0

V1.1 在个人显式记忆闭环上新增用户建模：真实飞书/OpenClaw 事件进入 Evidence Store 后，系统可用 LLM 抽取离散 PersonalMemory 候选，也可抽取用户画像 patch，经后端校验后写入 `user_profiles`。OpenClaw 回复前可获得压缩后的 User Profile Context 与相关 Memory Context Pack。系统仍只接收来自飞书官方事件回调、OpenClaw Hook，或带鉴权的标准事件入口的数据；不提供 mock 飞书或 mock OpenClaw 接口。

已实现内容：

- Python 3.11 + FastAPI 后端服务。
- SQLite 数据库初始化与 Alembic 迁移机制。
- 服务启动时自动执行数据库迁移。
- 健康检查接口 `GET /health`。
- 飞书事件回调入口 `POST /integrations/feishu/events`。
- OpenClaw Hook 事件入口 `POST /events/ingest`。
- Evidence 查询接口 `GET /events` 和 `GET /events/{event_id}`。
- 事件标准化、幂等去重、基础敏感信息脱敏和隐私等级标注。
- 从真实事件自动抽取显式偏好、提醒和忘记指令。
- 可选启用 OpenAI-compatible LLM 抽取工作偏好和提醒候选；LLM 只返回候选结构，后端校验后仍通过现有 `MemoryStore` 写入。
- 可选启用 LLM 用户画像抽取，捕获职位、当前工作阶段、工作偏好、沟通偏好、工具偏好、提醒偏好、饮食偏好等非敏感画像信息。
- 用户画像以 `user_profiles.profile_json` 作为权威存储，以 `profile_markdown` 作为 Prompt 注入和展示用派生视图。
- 用户画像证据链通过 `user_profile_evidence_links` 关联真实 `work_events`。
- 记忆写入、更新、软删除、证据关联和审计日志。
- 提醒偏好写入后持久化 `reminder_jobs`。
- 记忆检索接口 `POST /memory/search`。
- 用户画像查询接口 `GET /profile/{user_id}` 和 `GET /profile/{user_id}/markdown`。
- 上下文聚合接口 `POST /context/build`，拼接 User Profile Context 和相关 Memory Context Pack。
- 基于用户、query、work_type、memory_category 的 SQLite 结构化召回、关键词匹配和排序评分。
- 面向 OpenClaw 的短 `Memory Context Pack`，不暴露内部 JSON、数据库 ID 或完整 Evidence。
- OpenClaw context 插件支持 `before_prompt_build`，可在模型回复前注入 `/context/build` 或 `/memory/search` 返回的 `context_pack`。
- 主动提醒接口 `POST /proactive/trigger`。
- 后台 Reminder Scheduler，可按配置扫描到期提醒并通过飞书 Bot 发送真实文本消息。
- 飞书发送成功或失败都会写回 `work_events`。
- “别提醒 / 取消提醒 / 不用提醒”等反馈会软删除提醒记忆并取消关联任务。
- P0 验收脚本 `scripts/p0_acceptance.ps1`，只检查真实数据链路，不制造模拟事件。
- V1.1 推荐表结构：`work_events`、`personal_memories`、`memory_evidence_links`、`reminder_jobs`、`memory_audit_logs`、`user_profiles`、`user_profile_evidence_links`。

暂不实现内容：

- 不发送飞书交互卡片。
- 不接入向量数据库。
- 不接入 OpenClaw 原生 memory 后端或 embedding provider。
- 不实现飞书文档扫描。
- 不实现团队记忆。

## 项目文档

- [产品方案与迭代计划](docs/PRODUCT_ROADMAP.md)
- [行为抽取规则与数据表增量写入说明](docs/EXTRACTION_RULES_AND_DATA_FLOW.md)
- [OpenClaw + 飞书集成官方文档与接口清单](docs/OpenClaw_Feishu_Integration_Docs_Links.md)
- [从零启动操作文档](docs/STARTUP_GUIDE.md)
- [V0.2 真实事件接入操作文档](docs/V0_2_EVENT_INGESTION_GUIDE.md)

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LONGMEMORY_ENV` | `local` | 运行环境标识 |
| `LONGMEMORY_HOST` | `127.0.0.1` | 本地服务监听地址 |
| `LONGMEMORY_PORT` | `8000` | 本地服务端口 |
| `LONGMEMORY_DATABASE_URL` | `sqlite:///./data/longmemory.db` | SQLite 数据库地址 |
| `LONGMEMORY_LOG_LEVEL` | `INFO` | 日志级别 |
| `LONGMEMORY_INGEST_TOKEN` | 无 | OpenClaw 写入和 Evidence 查询鉴权 token |
| `LONGMEMORY_FEISHU_VERIFICATION_TOKEN` | 无 | 飞书事件订阅 Verification Token |
| `LONGMEMORY_FEISHU_ENCRYPT_KEY` | 无 | 飞书事件订阅 Encrypt Key |
| `LONGMEMORY_FEISHU_APP_ID` | 无 | 飞书自建应用 App ID，用于 Bot 主动发送消息 |
| `LONGMEMORY_FEISHU_APP_SECRET` | 无 | 飞书自建应用 App Secret，用于 SDK 获取 tenant token |
| `LONGMEMORY_FEISHU_DOMAIN` | `feishu` | `feishu` 或 `lark` |
| `LONGMEMORY_FEISHU_DEFAULT_RECEIVE_ID_TYPE` | `open_id` | 主动提醒默认接收者 ID 类型 |
| `LONGMEMORY_CONTEXT_LIMIT` | `5` | OpenClaw Hook 调用 `/memory/search` 时的上下文条数上限 |
| `LONGMEMORY_CONTEXT_ENABLED` | `true` | OpenClaw Hook 是否启用 Context Pack 注入 |
| `LONGMEMORY_REMINDER_SCHEDULER_ENABLED` | `false` | 是否启用后台主动提醒发送 |
| `LONGMEMORY_REMINDER_POLL_INTERVAL_SECONDS` | `30` | Scheduler 轮询间隔 |
| `LONGMEMORY_REMINDER_BATCH_SIZE` | `10` | 单次扫描处理的提醒任务数 |
| `LONGMEMORY_LLM_EXTRACTION_ENABLED` | `false` | 是否启用 LLM 候选抽取层 |
| `LONGMEMORY_LLM_BASE_URL` | `https://ark.cn-beijing.volces.com/api/v3` | OpenAI-compatible LLM provider base URL |
| `LONGMEMORY_LLM_MODEL` | `doubao-seed-2-0-lite-260215` | LLM 抽取模型名称 |
| `LONGMEMORY_LLM_API_KEY` | 无 | LLM provider API key，仅从环境变量或本地 `.env` 读取 |
| `LONGMEMORY_LLM_TIMEOUT_SECONDS` | `10` | LLM 抽取请求超时时间 |
| `LONGMEMORY_PROFILE_CONTEXT_ENABLED` | `true` | `/context/build` 是否注入用户画像 Markdown |
| `LONGMEMORY_PROFILE_CONTEXT_MAX_CHARS` | `1200` | 用户画像 Markdown 注入长度上限 |
| `LONGMEMORY_PROFILE_CONTEXT_POSITION` | `before_memory` | 用户画像放在 Memory Context 前或后 |

## 快速启动

```powershell
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn feishu_campus_longmemory.main:app --reload --host 127.0.0.1 --port 8000
```

Windows 环境下项目依赖 `tzdata` 提供 IANA 时区数据，用于解析默认时区 `Asia/Shanghai` 的提醒任务；执行上述安装命令会自动安装该依赖。

启用 LLM 候选抽取时，在本地 `.env` 中设置：

```powershell
LONGMEMORY_LLM_EXTRACTION_ENABLED=true
LONGMEMORY_LLM_API_KEY=replace-with-your-ark-api-key
```

LLM 只负责返回候选 JSON，不直接写数据库。记忆候选会由后端校验类别、work_type、置信度、敏感信息和证据片段，再调用现有 `MemoryStore` 写入；用户画像候选会由后端校验 dimension、claim、敏感信息和证据片段，再写入 `UserProfileStore`。

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

预期返回：

```json
{
  "status": "ok",
  "service": "feishu-campus-longmemory",
  "version": "1.1.0",
  "database": "ok"
}
```

## P0 API

### 飞书事件回调

```text
POST /integrations/feishu/events
```

用于配置到飞书开放平台事件订阅 Request URL。该入口通过飞书官方 Python SDK 处理 URL verification、verification token 校验、加密事件解密和签名校验。

### OpenClaw 事件写入

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
$body = @{
  type = "message"
  action = "received"
  sessionKey = "真实 OpenClaw sessionKey"
  timestamp = (Get-Date).ToUniversalTime().ToString("o")
  context = @{
    from = "真实发送者 ID"
    content = "真实消息内容"
    channelId = "feishu"
  }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod http://127.0.0.1:8000/events/ingest -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

### Evidence 查询

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
Invoke-RestMethod "http://127.0.0.1:8000/events?source=openclaw&limit=20" -Headers $headers
```

### 显式记忆写入

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
$body = @{
  user_id = "真实用户 ID"
  memory_category = "WorkPreferenceMemory"
  work_type = "weekly_report"
  content_json = @{
    summary = "周报先写结论，再写风险"
    normalized_key = "weekly_report:preference"
  }
  evidence_event_ids = @("已有 work_events.event_id")
} | ConvertTo-Json -Depth 8

Invoke-RestMethod http://127.0.0.1:8000/memory/write -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

### 记忆更新与忘记

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
Invoke-RestMethod http://127.0.0.1:8000/memory/<memory_id> -Headers $headers
Invoke-RestMethod http://127.0.0.1:8000/memory/forget -Method Post -Headers $headers -ContentType "application/json" -Body '{"memory_id":"<memory_id>"}'
```

### 记忆检索与 Context Pack

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
$body = @{
  user_id = "真实用户 ID"
  query = "帮我写这周周报"
  work_type = "weekly_report"
  memory_categories = @("WorkPreferenceMemory", "ReminderPreferenceMemory")
  limit = 5
} | ConvertTo-Json -Depth 8

Invoke-RestMethod http://127.0.0.1:8000/memory/search -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

返回中的 `context_pack` 可由 OpenClaw Hook 注入模型前上下文。它只包含短摘要，并明确包含“历史偏好仅在不冲突时使用；当前用户请求优先”的约束。`memory_id` 仅在 API 响应里用于调试，不会出现在 `context_pack`。

### 用户画像查询

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
Invoke-RestMethod http://127.0.0.1:8000/profile/真实用户ID -Headers $headers
Invoke-RestMethod http://127.0.0.1:8000/profile/真实用户ID/markdown -Headers $headers
```

`profile_json` 是权威结构化画像，`profile_markdown` 是压缩后的可读视图，不包含原始 Evidence、内部数据库 ID 或 event_id。

### 上下文聚合

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
$body = @{
  user_id = "真实用户 ID"
  query = "帮我写这周周报"
  work_type = "weekly_report"
  limit = 5
} | ConvertTo-Json -Depth 8

Invoke-RestMethod http://127.0.0.1:8000/context/build -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

该接口会读取压缩后的 User Profile Context，并调用现有 MemoryRetriever 生成相关 Memory Context。OpenClaw context 插件优先调用 `/context/build`；如果该接口失败，会回退到 `/memory/search`。插件当前保留既有 `defaultForcedUserId` 和 `resolveUserId` 优先级。

### 提醒任务持久化

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
$body = @{
  user_id = "真实用户 ID"
  reminder_text = "每周五上午提醒我写周报"
  evidence_event_ids = @("已有 work_events.event_id")
} | ConvertTo-Json -Depth 8

Invoke-RestMethod http://127.0.0.1:8000/reminder/schedule -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

### 主动提醒触发

当前版本默认不启用后台发送，避免本地开发误发真实飞书消息。手动触发已到期提醒：

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
$body = @{
  limit = 10
} | ConvertTo-Json -Depth 8

Invoke-RestMethod http://127.0.0.1:8000/proactive/trigger -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

发送前必须配置真实飞书应用：

```powershell
$env:LONGMEMORY_FEISHU_APP_ID="cli_xxx"
$env:LONGMEMORY_FEISHU_APP_SECRET="飞书 App Secret"
$env:LONGMEMORY_FEISHU_DOMAIN="feishu"
```

飞书应用需要启用 Bot、发布应用，并拥有 `im:message:send_as_bot` 权限。默认用 `user_id` 作为 `open_id` 发送；如果接收者不是 open_id，请在创建提醒时通过 `payload_json.feishu_receive_id` 和 `payload_json.feishu_receive_id_type` 指定真实接收者。

## P0 验收

P0 验收必须使用真实飞书或 OpenClaw 数据。脚本只做健康检查、鉴权、Evidence 查询、Memory Search 和到期提醒触发入口检查；如果没有真实数据，会输出缺失项和下一步操作，不会制造模拟事件。

```powershell
.\scripts\p0_acceptance.ps1 -BaseUrl "http://127.0.0.1:8000" -IngestToken $env:LONGMEMORY_INGEST_TOKEN -UserId "真实用户 open_id"
```

完整演示路径：

1. 用户在真实飞书或 OpenClaw 中发送“以后我的周报先写结论，再写风险”。
2. 查询 `/events`，确认出现真实 `work_events`。
3. 用户发送“我现在负责飞书校园大赛项目，我喜欢清淡饮食”，启用 LLM 后系统写入 `user_profiles`。
4. 查询 `/profile/{user_id}`，确认返回结构化画像和 `profile_markdown`。
5. 查询 `/context/build`，确认返回 User Profile Context 与相关 Memory Context。
6. OpenClaw Hook 在 `before_prompt_build` 中优先使用 `/context/build` 的 `context_pack` 注入模型前上下文。
7. 用户创建提醒或调用 `/reminder/schedule` 创建真实提醒任务。
8. 到期后 Scheduler 或 `/proactive/trigger` 通过飞书 Bot 发送文本消息。
9. 查询 `/events`，确认发送成功或失败都已回写 Evidence。

安全边界：

- 不存储飞书 App Secret、tenant token、OpenClaw token；全部通过环境变量提供。
- 不在代码或文档中存储 LLM API key；`LONGMEMORY_LLM_API_KEY` 只从环境变量或本地 `.env` 读取。
- 含 token、password、secret、api_key、邮箱、电话或私钥块的敏感内容不会进入长期记忆或用户画像，也不会主动发送。
- 当前请求优先于历史记忆和用户画像，Context Pack 不暴露内部 JSON、数据库 ID、event_id 或完整 Evidence。

## 开发检查

```powershell
pytest
```

测试覆盖本地工程骨架、SQLite 迁移、健康检查、OpenClaw/飞书事件入库、幂等去重、Evidence 查询鉴权、基础脱敏、显式记忆抽取、LLM 候选抽取兜底与安全校验、用户画像抽取与合并、Profile API、上下文聚合、提醒任务持久化、记忆更新、软删除、冲突替换、结构化检索排序、Context Pack 隐私边界、OpenClaw Hook 的上下文注入配置、主动提醒发送状态管理、成功/失败 Evidence 回写、敏感提醒拦截和 P0 验收脚本静态检查。
