# P0 正式版从零启动操作文档

本文档说明如何在 Windows PowerShell 中从零启动 `feishu-campus-longmemory` P0 正式版 `1.0.0` 本地服务。

P0 正式版包含工程骨架、SQLite 迁移、健康检查、真实飞书事件回调、OpenClaw Hook 事件写入、Evidence 查询、显式记忆抽取、记忆写入/更新/忘记、提醒任务持久化、SQLite 结构化记忆检索、Memory Context Pack、Reminder Scheduler 和飞书 Bot 主动提醒。飞书消息发送使用官方 `lark-oapi` SDK，不使用模拟接口替代。

## 1. 前置条件

确认本机已有 Python 3.11：

```powershell
python --version
```

推荐版本：

```text
Python 3.11.x
```

进入项目目录：

```powershell
cd D:\feishu_campuscomp\feishu-campus-longmemory
```

## 2. 创建虚拟环境

```powershell
python -m venv .venv
```

激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

如果 PowerShell 阻止脚本执行，可以只对当前窗口放开策略：

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\.venv\Scripts\Activate.ps1
```

## 3. 安装依赖

```powershell
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

说明：

- `-e` 使用可编辑安装，便于本地开发。
- `[dev]` 会安装测试依赖。
- Windows 环境下会安装 `tzdata`，为 `Asia/Shanghai` 等 IANA 时区提供数据，避免提醒解析时报时区缺失错误。

## 4. 配置环境变量

本地健康检查可以直接使用默认配置。事件写入、Evidence 查询和 Memory API 需要配置 `LONGMEMORY_INGEST_TOKEN`。需要自定义时，可以复制示例文件：

```powershell
Copy-Item .env.example .env
```

可用配置：

```powershell
$env:LONGMEMORY_ENV="local"
$env:LONGMEMORY_HOST="127.0.0.1"
$env:LONGMEMORY_PORT="8000"
$env:LONGMEMORY_DATABASE_URL="sqlite:///./data/longmemory.db"
$env:LONGMEMORY_LOG_LEVEL="INFO"
$env:LONGMEMORY_INGEST_TOKEN="替换为足够长的随机字符串"
$env:LONGMEMORY_FEISHU_VERIFICATION_TOKEN="飞书事件订阅 Verification Token"
$env:LONGMEMORY_FEISHU_ENCRYPT_KEY="飞书事件订阅 Encrypt Key"
$env:LONGMEMORY_FEISHU_APP_ID="cli_xxx"
$env:LONGMEMORY_FEISHU_APP_SECRET="飞书 App Secret"
$env:LONGMEMORY_FEISHU_DOMAIN="feishu"
$env:LONGMEMORY_FEISHU_DEFAULT_RECEIVE_ID_TYPE="open_id"
$env:LONGMEMORY_CONTEXT_LIMIT="5"
$env:LONGMEMORY_CONTEXT_ENABLED="true"
$env:LONGMEMORY_REMINDER_SCHEDULER_ENABLED="false"
$env:LONGMEMORY_REMINDER_POLL_INTERVAL_SECONDS="30"
$env:LONGMEMORY_REMINDER_BATCH_SIZE="10"
```

默认 SQLite 文件位置：

```text
D:\feishu_campuscomp\feishu-campus-longmemory\data\longmemory.db
```

服务启动时会自动创建 `data` 目录并执行 Alembic 迁移。

## 5. 启动服务

```powershell
uvicorn feishu_campus_longmemory.main:app --reload --host 127.0.0.1 --port 8000
```

如果端口被占用，可以换一个端口：

```powershell
uvicorn feishu_campus_longmemory.main:app --reload --host 127.0.0.1 --port 8001
```

## 6. 健康检查

打开新的 PowerShell 窗口，执行：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

预期返回：

```json
{
  "status": "ok",
  "service": "feishu-campus-longmemory",
  "version": "1.0.0",
  "database": "ok"
}
```

如果数据库不可用，接口会返回标准错误响应，不会伪造健康状态。

## 7. 运行测试

```powershell
pytest
```

P0 测试覆盖：

- 配置默认值加载。
- SQLite 临时数据库迁移。
- `GET /health` 返回 200。
- OpenClaw 事件写入、去重和 Evidence 查询。
- 飞书官方 SDK 事件回调路径。
- 显式偏好抽取和写入。
- ReminderPreferenceMemory 与 `reminder_jobs` 持久化。
- 记忆更新、软删除、审计和冲突替换。
- `/memory/search` 结构化检索、排序评分和空结果。
- `context_pack` 不泄露内部 JSON、数据库 ID 或完整 Evidence。
- OpenClaw Hook `message:preprocessed` 配置和上下文注入路径。
- `/proactive/trigger` 主动提醒触发。
- 到期 once/weekly 提醒发送后的状态更新。
- 飞书发送成功或失败后的 `work_events` 回写。
- 缺少飞书 App 配置、未鉴权、强敏感提醒的失败路径。
- P0 验收脚本静态检查。

## 8. P0 验收脚本

验收脚本只检查现有真实数据链路，不创建 mock 飞书/OpenClaw 事件，不伪造成功结果：

```powershell
.\scripts\p0_acceptance.ps1 -BaseUrl "http://127.0.0.1:8000" -IngestToken $env:LONGMEMORY_INGEST_TOKEN -UserId "ou_xxx"
```

如果没有真实 `work_events`、可召回记忆或到期提醒，脚本会输出 warning 和下一步操作。完整 P0 验收仍需要真实飞书/OpenClaw 消息和可触达的飞书 Bot。

## 9. 手动验证 Memory Context Pack

先写入一条真实 OpenClaw Evidence，让 P0 系统抽取一条周报偏好：

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
$body = @{
  type = "message"
  action = "received"
  sessionKey = "session-1"
  timestamp = (Get-Date).ToUniversalTime().ToString("o")
  context = @{
    from = "ou_xxx"
    content = "以后我的周报先写结论，再写风险"
    channelId = "feishu"
    metadata = @{
      messageId = "manual-v04-001"
      senderId = "ou_xxx"
    }
  }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod http://127.0.0.1:8000/events/ingest -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

再检索记忆：

```powershell
$body = @{
  user_id = "ou_xxx"
  query = "帮我写这周周报"
  limit = 5
} | ConvertTo-Json -Depth 8

Invoke-RestMethod http://127.0.0.1:8000/memory/search -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

预期返回 `detected_work_type=weekly_report`，`empty=false`，并且 `context_pack` 中只包含短摘要和“当前用户请求优先”的约束。

## 10. 数据库迁移说明

迁移文件位于：

```text
alembic\versions\0001_initial_schema.py
```

首版迁移会创建以下表：

- `work_events`
- `personal_memories`
- `memory_evidence_links`
- `reminder_jobs`
- `memory_audit_logs`

应用启动时会自动执行：

```text
alembic upgrade head
```

通常不需要手动运行迁移。需要手动执行时：

```powershell
alembic upgrade head
```

## 11. 手动验证主动提醒

飞书侧前置条件：

1. 企业自建应用已启用 Bot。
2. 应用已发布。
3. 权限包含 `im:message:send_as_bot`。
4. 目标用户可以被 Bot 触达。

配置发送能力：

```powershell
$env:LONGMEMORY_FEISHU_APP_ID="cli_xxx"
$env:LONGMEMORY_FEISHU_APP_SECRET="飞书 App Secret"
$env:LONGMEMORY_FEISHU_DOMAIN="feishu"
$env:LONGMEMORY_FEISHU_DEFAULT_RECEIVE_ID_TYPE="open_id"
```

创建一个 1 分钟前已到期的提醒：

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
$evidenceBody = @{
  type = "message"
  action = "received"
  sessionKey = "session-1"
  timestamp = (Get-Date).ToUniversalTime().ToString("o")
  context = @{
    from = "ou_xxx"
    content = "真实提醒 evidence"
    channelId = "feishu"
    metadata = @{
      messageId = "manual-v05-evidence-001"
      senderId = "ou_xxx"
    }
  }
} | ConvertTo-Json -Depth 8

$evidence = Invoke-RestMethod http://127.0.0.1:8000/events/ingest -Method Post -Headers $headers -ContentType "application/json" -Body $evidenceBody

$body = @{
  user_id = "ou_xxx"
  reminder_text = "提醒我写周报"
  schedule_type = "once"
  next_run_at = (Get-Date).ToUniversalTime().AddMinutes(-1).ToString("o")
  evidence_event_ids = @($evidence.event_id)
} | ConvertTo-Json -Depth 8

Invoke-RestMethod http://127.0.0.1:8000/reminder/schedule -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

手动触发到期提醒：

```powershell
$body = @{ limit = 10 } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/proactive/trigger -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

后台 Scheduler 默认关闭。确认手动触发链路正常后再启用：

```powershell
$env:LONGMEMORY_REMINDER_SCHEDULER_ENABLED="true"
uvicorn feishu_campus_longmemory.main:app --reload --host 127.0.0.1 --port 8000
```

## 12. 常见问题

### 找不到 `uvicorn`

确认已经激活虚拟环境，并重新安装依赖：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

### 运行提醒相关测试时报 `No module named 'tzdata'`

Windows 通常没有系统级 IANA 时区数据库，提醒解析默认使用 `Asia/Shanghai`，因此需要 Python 包 `tzdata`。重新安装项目依赖即可：

```powershell
python -m pip install -e ".[dev]"
```

### `GET /health` 返回数据库错误

检查 `LONGMEMORY_DATABASE_URL` 是否指向可写路径。默认路径会自动创建：

```text
sqlite:///./data/longmemory.db
```

### 端口 8000 被占用

换用其他端口启动：

```powershell
uvicorn feishu_campus_longmemory.main:app --reload --host 127.0.0.1 --port 8001
```

健康检查地址也要同步调整：

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
```

### 是否需要配置飞书 App ID 或 OpenClaw Token

健康检查不需要。真实飞书事件接入需要 `LONGMEMORY_FEISHU_VERIFICATION_TOKEN` 和 `LONGMEMORY_FEISHU_ENCRYPT_KEY`；OpenClaw Hook 写入、Memory API、`/memory/search` 和 `/proactive/trigger` 需要 `LONGMEMORY_INGEST_TOKEN`。飞书主动发送还需要 `LONGMEMORY_FEISHU_APP_ID` 和 `LONGMEMORY_FEISHU_APP_SECRET`。所有密钥都通过环境变量提供，不会写入代码或文档。

### `/memory/search` 返回空

先确认该 `user_id` 已经通过真实事件或 `/memory/write` 写入 `active`、`reinforced` 或 `candidate` 状态的记忆。`deleted`、`replaced`、`outdated` 记忆不会被召回。P0 正式版仍使用 SQLite 结构化过滤和关键词匹配，不使用 embedding，因此 query 中最好包含“周报”“会议纪要”“文档”“任务”“知识库”等工作类型线索。

### `/proactive/trigger` 返回 `feishu_sender_not_configured`

检查 `LONGMEMORY_FEISHU_APP_ID` 和 `LONGMEMORY_FEISHU_APP_SECRET` 是否已经配置，并确认飞书应用已启用 Bot、已发布、拥有 `im:message:send_as_bot` 权限。

### 提醒发送失败后为什么 job 状态是 `paused`

当前数据库迁移中 `reminder_jobs.status` 只允许 `active`、`paused`、`triggered`、`cancelled`。P0 正式版不做破坏性迁移，因此发送失败时会把持久状态置为 `paused`，并在 `payload_json.delivery_status` 写入 `failed`，同时写入 `reminder.delivery.failed` Evidence。

### P0 是否会保存密钥或 token

不会。飞书 App Secret、飞书 tenant token、OpenClaw token 和中间层 ingest token 都只通过环境变量或请求头传入，不写入数据库、日志或文档示例。强敏感内容会被脱敏，且不会进入长期记忆或主动提醒发送链路。
