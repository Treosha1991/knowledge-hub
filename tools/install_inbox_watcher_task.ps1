param(
    [string]$TaskName = "KnowledgeHub Inbox Watcher",
    [double]$Interval = 5.0,
    [ValidateSet("OnLogon", "OnStartup")]
    [string]$Trigger = "OnLogon",
    [switch]$Preview
)

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$intervalText = $Interval.ToString([System.Globalization.CultureInfo]::InvariantCulture)
$startScript = Join-Path $root "tools\\start_inbox_watcher.ps1"
$scheduleType = if ($Trigger -eq "OnStartup") { "ONSTART" } else { "ONLOGON" }
$taskCommand = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startScript`" -Interval $intervalText"

$previewPayload = [pscustomobject]@{
    ok = $true
    preview = $true
    task_name = $TaskName
    trigger = $Trigger
    schedule_type = $scheduleType
    interval_seconds = $Interval
    task_command = $taskCommand
}

if ($Preview) {
    $previewPayload | ConvertTo-Json -Depth 4
    exit 0
}

$result = & schtasks.exe /Create /TN $TaskName /TR $taskCommand /SC $scheduleType /RL LIMITED /F 2>&1
$success = $LASTEXITCODE -eq 0

$payload = [ordered]@{
    ok = $success
    preview = $false
    task_name = $TaskName
    trigger = $Trigger
    schedule_type = $scheduleType
    interval_seconds = $Interval
    task_command = $taskCommand
    output = ($result | Out-String).Trim()
}

$payload | ConvertTo-Json -Depth 4
if (-not $success) {
    exit 1
}
