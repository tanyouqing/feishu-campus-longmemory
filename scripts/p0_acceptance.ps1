param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [Parameter(Mandatory = $true)]
    [string]$IngestToken,
    [Parameter(Mandatory = $true)]
    [string]$UserId,
    [string]$JobId
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message"
}

function Invoke-LongMemory {
    param(
        [string]$Path,
        [string]$Method = "Get",
        [object]$Body = $null
    )

    $headers = @{ Authorization = "Bearer $IngestToken" }
    $uri = "$($BaseUrl.TrimEnd('/'))$Path"
    if ($null -eq $Body) {
        return Invoke-RestMethod -Uri $uri -Method $Method -Headers $headers
    }

    $json = $Body | ConvertTo-Json -Depth 12
    return Invoke-RestMethod -Uri $uri -Method $Method -Headers $headers -ContentType "application/json" -Body $json
}

Write-Host "P0 acceptance smoke check for feishu-campus-longmemory."
Write-Host "This script does not create mock Feishu/OpenClaw events and does not fake success."

Write-Step "Health"
$health = Invoke-RestMethod -Uri "$($BaseUrl.TrimEnd('/'))/health"
$health | ConvertTo-Json -Depth 8
if ($health.status -ne "ok" -or $health.version -ne "1.0.0") {
    throw "Expected /health status=ok and version=1.0.0."
}

Write-Step "Evidence query for user"
$events = Invoke-LongMemory -Path "/events?user_id=$([uri]::EscapeDataString($UserId))&limit=5"
if ($events.Count -eq 0) {
    Write-Warning "No real work_events found for $UserId. Send a real Feishu/OpenClaw message first, then rerun this script."
} else {
    $events | Select-Object -First 3 | ConvertTo-Json -Depth 8
}

Write-Step "Memory search"
$search = Invoke-LongMemory -Path "/memory/search" -Method "Post" -Body @{
    user_id = $UserId
    query = "P0 验收：检索已有个人工作记忆"
    limit = 5
}
$search | ConvertTo-Json -Depth 8
if ($search.empty) {
    Write-Warning "No memories were recalled. Create a real explicit memory through Feishu/OpenClaw, then rerun this script."
}

Write-Step "Due reminder trigger"
$triggerBody = @{ limit = 10 }
if ($JobId) {
    $triggerBody.job_id = $JobId
    $triggerBody.limit = 1
}
try {
    $trigger = Invoke-LongMemory -Path "/proactive/trigger" -Method "Post" -Body $triggerBody
    $trigger | ConvertTo-Json -Depth 8
    if ($trigger.processed -eq 0) {
        Write-Warning "No due reminder was processed. Create a real due reminder, or pass -JobId for a due active job."
    }
} catch {
    Write-Warning "Proactive trigger check did not complete. Confirm Feishu app credentials and im:message:send_as_bot permission before testing real delivery."
    Write-Warning $_.Exception.Message
}

Write-Step "P0 smoke check finished"
Write-Host "Review warnings above. A full P0 acceptance requires real Feishu/OpenClaw events and a reachable Feishu Bot."
