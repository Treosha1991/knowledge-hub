param(
    [int]$Limit = 8,

    [ValidateSet("text", "json")]
    [string]$Format = "text"
)

$projectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $projectRoot
try {
    python .\tools\latest_handoffs.py --limit $Limit --format $Format
}
finally {
    Pop-Location
}
