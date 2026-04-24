$pythonCandidates = @(
    (Join-Path $PSScriptRoot "..\\.venv\\Scripts\\python.exe"),
    (Join-Path $PSScriptRoot "..\\.venv-1\\Scripts\\python.exe"),
    "python"
)

$python = $pythonCandidates | Where-Object { $_ -eq "python" -or (Test-Path $_) } | Select-Object -First 1
$script = Join-Path $PSScriptRoot "create_backup_archive.py"

& $python $script
exit $LASTEXITCODE
