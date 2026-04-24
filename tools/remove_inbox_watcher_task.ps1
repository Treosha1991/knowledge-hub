param(
    [string]$TaskName = "KnowledgeHub Inbox Watcher"
)

$result = & schtasks.exe /Delete /TN $TaskName /F 2>&1
$success = $LASTEXITCODE -eq 0

[pscustomobject]@{
    ok = $success
    task_name = $TaskName
    output = ($result | Out-String).Trim()
    note = "Removing the scheduled task does not stop an already running watcher process."
} | ConvertTo-Json -Depth 4

if (-not $success) {
    exit 1
}
