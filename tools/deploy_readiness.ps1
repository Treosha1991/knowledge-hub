param(
    [ValidateSet("text", "json")]
    [string]$Format = "text"
)

$projectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $projectRoot
try {
    python .\tools\deploy_readiness.py --format $Format
}
finally {
    Pop-Location
}
