param(
    [string]$ServerUrl = "",
    [ValidateSet("text", "json")]
    [string]$Format = "text"
)

$argsList = @("tools/gpt_actions_setup.py", "--format", $Format)
if ($ServerUrl) {
    $argsList += @("--server-url", $ServerUrl)
}

python @argsList
