param(
    [double]$Interval = 5.0,
    [int]$Limit
)

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$intervalText = $Interval.ToString([System.Globalization.CultureInfo]::InvariantCulture)
$pythonCandidates = @(
    (Join-Path $root ".venv\\Scripts\\python.exe"),
    (Join-Path $root ".venv-1\\Scripts\\python.exe"),
    "python"
)
$python = $pythonCandidates | Where-Object { $_ -eq "python" -or (Test-Path $_) } | Select-Object -First 1
$script = Join-Path $PSScriptRoot "process_inbox.py"
$dataDir = if ($env:KH_DATA_DIR) { $env:KH_DATA_DIR } else { Join-Path $root "data\\knowledge_hub" }
$statusPath = Join-Path $dataDir "runtime\\inbox_watcher_status.json"

$arguments = @($script, "--watch", "--interval", $intervalText)
if ($PSBoundParameters.ContainsKey("Limit")) {
    $arguments += "--limit"
    $arguments += $Limit
}

$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Minimized -PassThru
Start-Sleep -Milliseconds 750
$watcherStatus = $null
if (Test-Path $statusPath) {
    try {
        $watcherStatus = Get-Content $statusPath -Raw | ConvertFrom-Json
    } catch {
        $watcherStatus = $null
    }
}

[pscustomobject]@{
    ok = $true
    pid = $process.Id
    interval_seconds = $Interval
    command = "$python $($arguments -join ' ')"
    status_path = $statusPath
    watcher_pid = if ($watcherStatus) { $watcherStatus.pid } else { $null }
    watcher_state = if ($watcherStatus) { $watcherStatus.state } else { $null }
} | ConvertTo-Json -Depth 3
