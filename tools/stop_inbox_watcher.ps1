$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$dataDir = if ($env:KH_DATA_DIR) { $env:KH_DATA_DIR } else { Join-Path $root "data\\knowledge_hub" }
$statusPath = Join-Path $dataDir "runtime\\inbox_watcher_status.json"

if (!(Test-Path $statusPath)) {
    Write-Output (@{
        ok = $false
        error = "Inbox watcher status file was not found."
        status_path = $statusPath
    } | ConvertTo-Json -Depth 3)
    exit 1
}

$status = Get-Content $statusPath -Raw | ConvertFrom-Json
if (-not $status.pid) {
    Write-Output (@{
        ok = $false
        error = "No watcher PID is recorded in the status file."
        status_path = $statusPath
    } | ConvertTo-Json -Depth 3)
    exit 1
}

$stopped = $false
try {
    Stop-Process -Id ([int]$status.pid) -Force -ErrorAction Stop
    $stopped = $true
} catch {
    $stopped = $false
}

[pscustomobject]@{
    ok = $stopped
    pid = [int]$status.pid
    status_path = $statusPath
    note = if ($stopped) { "Process stop requested. The watcher status may remain 'running' until the heartbeat goes stale." } else { "The recorded PID was not running or could not be stopped." }
} | ConvertTo-Json -Depth 3

if (-not $stopped) {
    exit 1
}
