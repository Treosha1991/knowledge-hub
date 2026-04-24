param(
    [ValidateSet("text", "json")]
    [string]$Format = "text"
)

$python = Join-Path $PSScriptRoot "..\.venv-1\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

& $python (Join-Path $PSScriptRoot "deploy_env_status.py") --format $Format
