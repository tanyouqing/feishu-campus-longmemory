# P0 正式版真实事件、显式记忆、上下文与主动提醒接入操作文档

本文档说明如何把真实飞书事件和 OpenClaw Hook 事件写入 `work_events` Evidence Store，从真实消息里抽取显式个人记忆，通过 `/memory/search` 生成 Memory Context Pack，并通过飞书 Bot 发送真实主动提醒。

P0 正式版会写入 `personal_memories`、`memory_evidence_links`、`reminder_jobs` 和 `memory_audit_logs`，并提供 SQLite 结构化检索、短上下文注入和主动提醒能力；但不发送飞书交互卡片，不扫描飞书文档，不接入向量数据库。所有事件必须来自真实飞书回调、OpenClaw Hook，或带鉴权的标准事件入口。

## 1. 启动中间层

安装依赖：

```powershell
python -m pip install -e ".[dev]"
```

复制环境变量示例：

```powershell
Copy-Item .env.example .env
```

至少配置：

```powershell
$env:LONGMEMORY_INGEST_TOKEN="替换为足够长的随机字符串"
```

启动服务：

```powershell
uvicorn feishu_campus_longmemory.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## 2. 飞书事件接入

### 2.1 前置工作

在飞书开放平台完成以下配置：

1. 创建企业自建应用。
2. 启用 Bot 能力。
3. 在权限管理中配置机器人接收消息和发送消息相关权限，至少包含：
   - `im:message.p2p_msg:readonly`
   - `im:message.group_at_msg:readonly`
   - `im:message:readonly`
   - `im:message:send_as_bot`
4. 在事件订阅中选择 Request URL 模式。
5. 订阅事件：`im.message.receive_v1`。
6. 获取事件订阅中的 Verification Token 和 Encrypt Key。

本地调试时，飞书需要访问公网 HTTPS 地址。可以用内网穿透把本地端口暴露出去，再把公网地址配置为：

```text
https://<你的公网域名>/integrations/feishu/events
```

### 2.2 中间层配置

```powershell
$env:LONGMEMORY_FEISHU_VERIFICATION_TOKEN="飞书事件订阅 Verification Token"
$env:LONGMEMORY_FEISHU_ENCRYPT_KEY="飞书事件订阅 Encrypt Key"
$env:LONGMEMORY_FEISHU_APP_ID="cli_xxx"
$env:LONGMEMORY_FEISHU_APP_SECRET="飞书 App Secret"
$env:LONGMEMORY_FEISHU_DOMAIN="feishu"
$env:LONGMEMORY_FEISHU_DEFAULT_RECEIVE_ID_TYPE="open_id"
```

重启 FastAPI 服务。

### 2.3 验收

在飞书中给 Bot 发送一条真实消息后，查询 Evidence：

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
Invoke-RestMethod "http://127.0.0.1:8000/events?source=feishu&event_type=im.message.receive_v1&limit=20" -Headers $headers
```

预期可以看到 `source=feishu`、`event_type=im.message.receive_v1` 的 `work_events` 记录。如果消息中包含“以后...”“我喜欢...”“记住...”“提醒我...”“忘掉...”等显式表达，V0.3 会进一步写入或更新个人记忆。

查询编码错误解法：

```python
python -c "import sqlite3; db=r'D:\feishu_campuscomp\feishu-campus-longmemory\data\longmemory.db'; conn=sqlite3.connect(db); cur=conn.cursor(); cur.execute('SELECT user_id, source, COUNT(*) FROM work_events GROUP BY user_id, source ORDER BY COUNT(*) DESC'); print('UserID'.ljust(40) + 'Source'.ljust(15) + 'EventCount'); print('-'*65); [print(f'{row[0]:<40}{row[1]:<15}{row[2]}') for row in cur.fetchall()]"
```

## 3. OpenClaw Hook 接入

### 3.1 前置工作

按 OpenClaw 官方文档启用 Feishu Channel：

```powershell
openclaw channels add
openclaw gateway status
```

飞书应用事件订阅中需要包含：

```text
im.message.receive_v1
```

### 3.2 安装 Hook 示例

本项目提供 Hook 示例：

```text
integrations\openclaw\longmemory-ingest
```

将该目录复制到 OpenClaw hooks 目录，例如：

```powershell
Copy-Item -Recurse integrations\openclaw\longmemory-ingest "$env:USERPROFILE\.openclaw\hooks\longmemory-ingest"
```

配置 Hook 环境变量：

```powershell
$env:LONGMEMORY_BASE_URL="http://127.0.0.1:8000"
$env:LONGMEMORY_INGEST_TOKEN="与中间层一致的 token"
$env:LONGMEMORY_CONTEXT_LIMIT="5"
$env:LONGMEMORY_CONTEXT_ENABLED="true"
```

启用 Hook：

```powershell
openclaw hooks enable longmemory-ingest
openclaw hooks check
openclaw gateway restart
```

或使用.env文件，配置好后执行：然后重启gateway

```bash
set -a;
source ~/longmemory.env;
set +a
```

 另外要加入longmemory context plugin并激活，还要改openclaw.json（用于plugins）

### 3.3 验收

在 OpenClaw 所连接的真实会话中发送消息，然后查询：

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
Invoke-RestMethod "http://127.0.0.1:8000/events?source=openclaw&limit=20" -Headers $headers
```

预期可以看到 `source=openclaw` 的事件记录。

## 4. V0.3 显式记忆抽取

真实事件进入 `/events/ingest` 或 `/integrations/feishu/events` 后，系统会从脱敏后的文本里抽取显式记忆。

支持表达：

- `以后...`
- `我喜欢...`
- `记住...`
- `不要再...`
- `提醒我...`
- `忘掉...` / `忘记...`

示例：用户在真实 OpenClaw 会话中发送：

```text
以后我的周报先写结论，再写风险
```

系统会写入 `WorkPreferenceMemory`，并通过 `memory_evidence_links` 关联来源 `work_events.event_id`。

示例：用户发送：

```text
每周五上午提醒我写周报
```

系统会写入 `ReminderPreferenceMemory`，并创建 weekly 类型的 `reminder_jobs`。V0.3 只持久化提醒任务，不主动发送飞书消息。

V0.5 支持用户反馈取消提醒，例如：

```text
以后别提醒这个了
取消提醒写周报
不用提醒我写周报了
```

系统会软删除匹配的 `ReminderPreferenceMemory`，并把关联 `reminder_jobs` 置为 `cancelled`。

强敏感内容不会生成长期记忆。例如包含 token、password、secret、api_key 或私钥块的文本只会作为脱敏 Evidence 保存，不会提升为 `personal_memories`。

## 5. V0.4 记忆检索与 OpenClaw 上下文注入

V0.4 新增：

```text
POST /memory/search
```

该接口沿用 `LONGMEMORY_INGEST_TOKEN` 鉴权。它不会调用外部 LLM、embedding provider 或 OpenClaw 原生 memory 后端，只使用 SQLite 中的 `personal_memories` 做结构化过滤、关键词匹配和排序评分。

手动检索示例：

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
$body = @{
  user_id = "ou_xxx"
  query = "帮我写这周周报"
  work_type = "weekly_report"
  memory_categories = @("WorkPreferenceMemory", "ReminderPreferenceMemory")
  limit = 5
} | ConvertTo-Json -Depth 8

Invoke-RestMethod http://127.0.0.1:8000/memory/search -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

响应包含：

- `detected_work_type`：根据 query 或请求字段识别的工作类型。
- `empty`：没有可用记忆时为 `true`。
- `context_pack`：可直接注入 OpenClaw prompt 的短上下文。
- `memories`：调试用检索结果，包含 `memory_id`、类别、工作类型、摘要、分数、证据数量和更新时间。

`context_pack` 只包含短摘要，不输出 `content_json` 原始对象、不输出 Evidence 全文、不输出数据库 ID，并会明确写入“以下是历史偏好，仅在不冲突时使用；当前用户请求优先。”

OpenClaw Hook 在 `message:preprocessed` 中会读取 `event.context.bodyForAgent`，调用 `/memory/search`，如果返回非空 `context_pack`，则把它追加到 `bodyForAgent` 前方。若 OpenClaw 运行时没有提供可修改的 `bodyForAgent`，或中间层不可用，Hook 只记录 warning，不阻断 OpenClaw 主流程。

支持的工作类型：

- `weekly_report`
- `meeting_minutes`
- `document_writing`
- `task_followup`
- `knowledge_lookup`
- `general`

## 6. P0 主动提醒闭环

P0 主动提醒接口：

```text
POST /proactive/trigger
```

该接口沿用 `LONGMEMORY_INGEST_TOKEN` 鉴权，只处理当前已经到期的提醒任务，不提供 force 发送。后台 Scheduler 默认关闭，避免本地开发误发真实飞书消息。

### 6.1 飞书发送前置条件

1. 企业自建应用已启用 Bot。
2. 应用已发布并通过审批。
3. 权限包含 `im:message:send_as_bot`。
4. 中间层已配置 `LONGMEMORY_FEISHU_APP_ID` 和 `LONGMEMORY_FEISHU_APP_SECRET`。
5. 默认 `user_id` 必须是飞书 `open_id`；如果不是，创建提醒时在 `payload_json` 中写入 `feishu_receive_id` 和 `feishu_receive_id_type`。

### 6.2 手动触发

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
$body = @{
  limit = 10
} | ConvertTo-Json -Depth 8

Invoke-RestMethod http://127.0.0.1:8000/proactive/trigger -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

指定单个 job：

```powershell
$body = @{
  job_id = "<reminder_jobs.job_id>"
  limit = 1
} | ConvertTo-Json -Depth 8

Invoke-RestMethod http://127.0.0.1:8000/proactive/trigger -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

### 6.3 启用后台 Scheduler

```powershell
$env:LONGMEMORY_REMINDER_SCHEDULER_ENABLED="true"
$env:LONGMEMORY_REMINDER_POLL_INTERVAL_SECONDS="30"
$env:LONGMEMORY_REMINDER_BATCH_SIZE="10"
uvicorn feishu_campus_longmemory.main:app --reload --host 127.0.0.1 --port 8000
```

发送结果：

- 成功写入 `source=feishu`、`event_type=im.message.create_v1` 的 Evidence。
- 失败写入 `source=longmemory`、`event_type=reminder.delivery.failed` 的 Evidence。
- `once` 成功后 `reminder_jobs.status=triggered`。
- `daily` / `weekly` 成功后继续保持 `active`，并推进 `next_run_at`。
- 失败后 `reminder_jobs.status=paused`，`payload_json.delivery_status=failed`。

## 7. P0 验收脚本

脚本路径：

```powershell
scripts\p0_acceptance.ps1
```

运行：

```powershell
.\scripts\p0_acceptance.ps1 -BaseUrl "http://127.0.0.1:8000" -IngestToken $env:LONGMEMORY_INGEST_TOKEN -UserId "ou_xxx"
```

该脚本不会创建模拟飞书/OpenClaw 事件，不会伪造成功。它只检查：

- `/health` 是否返回当前服务版本。
- 指定用户是否已有真实 Evidence。
- `/memory/search` 是否能召回记忆或给出空结果提示。
- `/proactive/trigger` 是否能处理当前到期提醒，或给出未到期提示。

## 8. Evidence 查询接口

### 查询列表

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
Invoke-RestMethod "http://127.0.0.1:8000/events?user_id=ou_xxx&source=feishu&limit=20" -Headers $headers
```

可选查询参数：

- `user_id`
- `source`
- `event_type`
- `limit`，范围 1 到 100

### 查询单条

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
Invoke-RestMethod "http://127.0.0.1:8000/events/<event_id>" -Headers $headers
```

## 9. Memory API

所有 Memory API 都需要 `LONGMEMORY_INGEST_TOKEN`。

### 写入结构化记忆

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
$body = @{
  user_id = "ou_xxx"
  memory_category = "WorkPreferenceMemory"
  work_type = "weekly_report"
  content_json = @{
    summary = "周报先写结论，再写风险"
    normalized_key = "weekly_report:preference"
  }
  evidence_event_ids = @("<已有 work_events.event_id>")
} | ConvertTo-Json -Depth 8

Invoke-RestMethod http://127.0.0.1:8000/memory/write -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

### 查询记忆详情

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
Invoke-RestMethod "http://127.0.0.1:8000/memory/<memory_id>" -Headers $headers
```

### 更新记忆

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
$body = @{
  memory_id = "<memory_id>"
  content_json = @{
    summary = "周报先写结论，再列风险和阻塞"
    normalized_key = "weekly_report:preference"
  }
  confidence = 0.95
} | ConvertTo-Json -Depth 8

Invoke-RestMethod http://127.0.0.1:8000/memory/update -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

### 忘记记忆

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
Invoke-RestMethod http://127.0.0.1:8000/memory/forget -Method Post -Headers $headers -ContentType "application/json" -Body '{"memory_id":"<memory_id>"}'
```

也可以按查询文本忘记：

```powershell
$body = @{
  user_id = "ou_xxx"
  query = "周报格式偏好"
  memory_category = "WorkPreferenceMemory"
  work_type = "weekly_report"
} | ConvertTo-Json -Depth 8

Invoke-RestMethod http://127.0.0.1:8000/memory/forget -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

### 创建提醒任务

```powershell
$headers = @{ Authorization = "Bearer $env:LONGMEMORY_INGEST_TOKEN" }
$body = @{
  user_id = "ou_xxx"
  reminder_text = "每周五上午提醒我写周报"
  evidence_event_ids = @("<已有 work_events.event_id>")
} | ConvertTo-Json -Depth 8

Invoke-RestMethod http://127.0.0.1:8000/reminder/schedule -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

## 10. 数据与隐私说明

- `event_id` 使用 `sha256(source + source_event_id)` 生成，重复投递不会重复写入。
- 文本内容会做基础脱敏，覆盖邮箱、手机号、Bearer token、常见 token/password/secret/api_key 赋值和私钥块。
- 非文本飞书消息只保存消息类型和必要元数据，不下载附件、不读取文档正文。
- Evidence 查询接口和 Memory API 必须带 `LONGMEMORY_INGEST_TOKEN`，避免工作证据和个人记忆被公开访问。
- 每条长期记忆必须关联至少一条 Evidence。直接调用 `/memory/write` 或 `/reminder/schedule` 时必须传入 `evidence_event_ids`，或传入真实 OpenClaw tool-call `evidence_event`。
- `/memory/search` 只返回记忆摘要和检索元数据；`context_pack` 不包含内部 JSON、数据库 ID 或完整 Evidence 文本。
- 含 token、password、secret、api_key 或私钥块等强敏感内容的提醒不会发送，只会记录失败 Evidence。
- 飞书 App Secret、飞书 tenant token、OpenClaw token 和中间层 ingest token 不写入数据库或日志；都必须通过环境变量或请求头传入。

## 11. 常见问题

### 飞书 URL verification 失败

检查：

- `LONGMEMORY_FEISHU_VERIFICATION_TOKEN` 是否与飞书开放平台一致。
- Request URL 是否是公网 HTTPS 地址。
- FastAPI 服务是否能被飞书访问。

### 飞书消息没有入库

检查：

- 飞书应用是否已发布并通过审批。
- Bot 能力是否启用。
- 事件订阅是否包含 `im.message.receive_v1`。
- 权限是否包含机器人接收消息相关权限。
- FastAPI 日志中是否出现 SDK 验签或解密错误。

### OpenClaw Hook 没有入库

检查：

- Hook 是否已启用：`openclaw hooks list`。
- Gateway 是否已重启：`openclaw gateway restart`。
- Hook 环境变量 `LONGMEMORY_BASE_URL` 和 `LONGMEMORY_INGEST_TOKEN` 是否存在。
- 中间层 `/events/ingest` 是否能从 OpenClaw 所在环境访问。

### 飞书主动提醒发送失败

检查：

- 飞书应用是否已发布。
- Bot 能力是否启用。
- 权限是否包含 `im:message:send_as_bot`。
- `LONGMEMORY_FEISHU_APP_ID` 和 `LONGMEMORY_FEISHU_APP_SECRET` 是否正确。
- 默认发送时 `user_id` 是否为飞书 `open_id`；若不是，请在提醒 `payload_json` 中提供 `feishu_receive_id` 和 `feishu_receive_id_type`。
- 目标用户是否已经与 Bot 建立可触达关系。

### OpenClaw 没有注入 Memory Context Pack

检查：

- Hook metadata 是否包含 `message:preprocessed`，并已重新复制到 OpenClaw hooks 目录。
- `LONGMEMORY_CONTEXT_ENABLED` 是否被设置为 `false`、`0`、`off`、`disabled` 或 `no`。
- `LONGMEMORY_CONTEXT_LIMIT` 是否是 1 到 20 之间的整数。
- 中间层 `/memory/search` 是否能从 OpenClaw 所在环境访问。
- 当前用户是否已有 `active`、`reinforced` 或 `candidate` 状态的相关记忆。
- OpenClaw 当前版本是否在 `message:preprocessed` 中提供可修改的 `context.bodyForAgent`。
