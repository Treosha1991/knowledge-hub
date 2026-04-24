param(
    [string]$TaskName = "KnowledgeHub Daily Backup"
)

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

[pscustomobject]@{
    ok = $true
    task_name = $TaskName
    task_registered = $taskRegistered
    scheduler_query = if ($taskRegistered) { $queryFields } else { $null }
    scheduler_output = ($queryOutput | Out-String).Trim()
} | ConvertTo-Json -Depth 6
