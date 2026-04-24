param(
    [string]$ProjectSlug,
    [switch]$All
)

$projectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $projectRoot
try {
    if ($All) {
        python .\tools\rebuild_exports.py --all
    }
    elseif ($ProjectSlug) {
        python .\tools\rebuild_exports.py $ProjectSlug
    }
    else {
        Write-Error "Provide -ProjectSlug <slug> or use -All."
        exit 1
    }
}
finally {
    Pop-Location
}
