param(
    [switch]$Watch,
    [double]$Interval = 5.0,
    [int]$Limit
)

$intervalText = $Interval.ToString([System.Globalization.CultureInfo]::InvariantCulture)

$pythonCandidates = @(
    (Join-Path $PSScriptRoot "..\\.venv\\Scripts\\python.exe"),
    (Join-Path $PSScriptRoot "..\\.venv-1\\Scripts\\python.exe"),
    "python"
)
$python = $pythonCandidates | Where-Object { $_ -eq "python" -or (Test-Path $_) } | Select-Object -First 1
$script = Join-Path $PSScriptRoot "process_inbox.py"

$args = @($script)
if ($Watch) {
    $args += "--watch"
    $args += "--interval"
    $args += $intervalText
}
if ($PSBoundParameters.ContainsKey("Limit")) {
    $args += "--limit"
    $args += $Limit
}

& $python @args
exit $LASTEXITCODE
