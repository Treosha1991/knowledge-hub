param(
    [string]$ServerUrl = ""
)

$argsList = @("tools/gpt_actions_schema.py")
if ($ServerUrl) {
    $argsList += @("--server-url", $ServerUrl)
}

python @argsList
