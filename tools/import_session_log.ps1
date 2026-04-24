param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [string]$ProjectSlug,
    [int]$ProjectId,
    [int]$WorkspaceId,
    [string]$WorkspaceSlug,
    [switch]$NoAutoCreateProject
)

$pythonCandidates = @(
    (Join-Path $PSScriptRoot "..\\.venv\\Scripts\\python.exe"),
    (Join-Path $PSScriptRoot "..\\.venv-1\\Scripts\\python.exe"),
    "python"
)
$python = $pythonCandidates | Where-Object { $_ -eq "python" -or (Test-Path $_) } | Select-Object -First 1
$script = Join-Path $PSScriptRoot "import_session_log.py"

$args = @($script, $Path)
if ($ProjectSlug) {
    $args += @("--project-slug", $ProjectSlug)
}
if ($PSBoundParameters.ContainsKey("ProjectId")) {
    $args += @("--project-id", $ProjectId)
}
if ($PSBoundParameters.ContainsKey("WorkspaceId")) {
    $args += @("--workspace-id", $WorkspaceId)
}
if ($WorkspaceSlug) {
    $args += @("--workspace-slug", $WorkspaceSlug)
}
if ($NoAutoCreateProject) {
    $args += "--no-auto-create-project"
}

& $python @args
exit $LASTEXITCODE
