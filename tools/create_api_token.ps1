param(
    [string]$Email = "",
    [string]$Label = "Chat Integration Token",
    [int]$ExpiresInDays = 90,
    [ValidateSet("text", "json")]
    [string]$Format = "text"
)

$argsList = @(
    "tools/create_api_token.py",
    "--label", $Label,
    "--expires-in-days", $ExpiresInDays.ToString(),
    "--format", $Format
)

if ($Email) {
    $argsList += @("--email", $Email)
}

python @argsList
