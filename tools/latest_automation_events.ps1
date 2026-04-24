param(
    [int]$Limit = 10,
    [string]$ProjectSlug,

    [ValidateSet("text", "json")]
    [string]$Format = "text"
)

$projectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $projectRoot
try {
    if ($ProjectSlug) {
        python .\tools\latest_automation_events.py --limit $Limit --project-slug $ProjectSlug --format $Format
    }
    else {
        python .\tools\latest_automation_events.py --limit $Limit --format $Format
    }
}
finally {
    Pop-Location
}
