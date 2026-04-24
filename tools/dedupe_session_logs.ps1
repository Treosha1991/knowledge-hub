param(
    [string]$ProjectSlug,
    [switch]$All,
    [switch]$Apply
)

$projectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $projectRoot
try {
    if ($All) {
        if ($Apply) {
            python .\tools\dedupe_session_logs.py --all --apply
        }
        else {
            python .\tools\dedupe_session_logs.py --all
        }
    }
    elseif ($ProjectSlug) {
        if ($Apply) {
            python .\tools\dedupe_session_logs.py $ProjectSlug --apply
        }
        else {
            python .\tools\dedupe_session_logs.py $ProjectSlug
        }
    }
    else {
        Write-Error "Provide -ProjectSlug <slug> or use -All."
        exit 1
    }
}
finally {
    Pop-Location
}
