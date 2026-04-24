param(
    [string]$TaskName = "KnowledgeHub Daily Backup",
    [string]$Time = "02:00",
    [switch]$Preview
)

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$script = Join-Path $root "tools\\create_backup_archive.ps1"
$taskCommand = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""

$previewPayload = [pscustomobject]@{
    ok = $true
    preview = $true
    task_name = $TaskName
    schedule_type = "DAILY"
    time = $Time
    task_command = $taskCommand
}

if ($Preview) {
    $previewPayload | ConvertTo-Json -Depth 4
    exit 0
}

$result = & schtasks.exe /Create /TN $TaskName /TR $taskCommand /SC DAILY /ST $Time /RL LIMITED /F 2>&1
$success = $LASTEXITCODE -eq 0

[ordered]@{
    ok = $success
    preview = $false
    task_name = $TaskName
    schedule_type = "DAILY"
    time = $Time
    task_command = $taskCommand
    output = ($result | Out-String).Trim()
} | ConvertTo-Json -Depth 4

if (-not $success) {
    exit 1
}
