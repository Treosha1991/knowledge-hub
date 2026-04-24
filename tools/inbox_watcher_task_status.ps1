param(
    [string]$TaskName = "KnowledgeHub Inbox Watcher"
)

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$dataDir = if ($env:KH_DATA_DIR) { $env:KH_DATA_DIR } else { Join-Path $root "data\\knowledge_hub" }
$watcherStatusPath = Join-Path $dataDir "runtime\\inbox_watcher_status.json"

$queryOutput = & schtasks.exe /Query /TN $TaskName /FO LIST /V 2>&1
$taskRegistered = $LASTEXITCODE -eq 0
$queryFields = @{}

if ($taskRegistered) {
    foreach ($line in $queryOutput) {
        if ($line -match "^\s*([^:]+):\s*(.*)$") {
            $queryFields[$matches[1].Trim()] = $matches[2].Trim()
        }
    }
}

$watcherStatus = $null
if (Test-Path $watcherStatusPath) {
    try {
        $watcherStatus = Get-Content $watcherStatusPath -Raw | ConvertFrom-Json
    } catch {
        $watcherStatus = [pscustomobject]@{
            state = "error"
            last_error = $_.Exception.Message
            status_path = $watcherStatusPath
        }
    }
}

[pscustomobject]@{
    ok = $true
    task_name = $TaskName
    task_registered = $taskRegistered
    scheduler_query = if ($taskRegistered) { $queryFields } else { $null }
    scheduler_output = ($queryOutput | Out-String).Trim()
    watcher_status_path = $watcherStatusPath
    watcher_status = $watcherStatus
} | ConvertTo-Json -Depth 6
