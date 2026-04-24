param(
    [Parameter(Mandatory = $true)]
    [string]$ToEmail,

    [string]$Subject = "Knowledge Hub mail backend test",

    [string]$Body
)

$python = Join-Path $PSScriptRoot "..\.venv-1\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$command = @(
    (Join-Path $PSScriptRoot "send_test_email.py"),
    $ToEmail,
    "--subject",
    $Subject
)

if ($Body) {
    $command += @("--body", $Body)
}

& $python @command
