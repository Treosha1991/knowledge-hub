param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectSlug,

    [ValidateSet("text", "json")]
    [string]$Format = "text"
)

$projectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $projectRoot
try {
    python .\tools\ready_for_next_chat.py $ProjectSlug --format $Format
}
finally {
    Pop-Location
}
