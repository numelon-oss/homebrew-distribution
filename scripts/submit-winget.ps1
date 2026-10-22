param(
    [Parameter(Mandatory)][string]$Identifier,
    [Parameter(Mandatory)][string]$Version,
    [Parameter(Mandatory)][string]$ManifestPath
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($env:WINGET_CREATE_GITHUB_TOKEN)) {
    throw 'Set the WINGET_TOKEN repository secret to a classic PAT with public_repo scope.'
}

$headers = @{
    Authorization = "Bearer $env:WINGET_CREATE_GITHUB_TOKEN"
    Accept = 'application/vnd.github+json'
    'X-GitHub-Api-Version' = '2022-11-28'
}
$repository = 'https://api.github.com/repos/microsoft/winget-pkgs'
$path = 'manifests/' + $Identifier.Substring(0, 1).ToLowerInvariant() + '/' + $Identifier.Replace('.', '/') + '/' + $Version
try {
    $null = Invoke-RestMethod "$repository/contents/$path" -Headers $headers
    Write-Host "$Identifier $Version is already in WinGet; skipping submission."
    exit 0
} catch {
    if ([int]$_.Exception.Response.StatusCode -ne 404) { throw }
}

$title = "New version: $Identifier version $Version"
$query = [uri]::EscapeDataString("repo:microsoft/winget-pkgs is:pr is:open in:title `"$Identifier`" `"$Version`"")
$pullRequests = Invoke-RestMethod "https://api.github.com/search/issues?q=$query&per_page=100" -Headers $headers
$existing = $pullRequests.items | Where-Object { $_.title -eq $title }
if ($existing) {
    Write-Host "Submission already open: $($existing[0].html_url)"
    exit 0
}

$tool = Join-Path $env:RUNNER_TEMP 'wingetcreate.exe'
Invoke-WebRequest 'https://github.com/microsoft/winget-create/releases/download/v1.12.13.0/wingetcreate.exe' -OutFile $tool
if ((Get-FileHash $tool -Algorithm SHA256).Hash -ne '24042BD37915805615E6CF969AC57C6439124C3FE85823327F5F3FB24BD9FFEA') {
    throw 'WinGetCreate checksum mismatch.'
}

# submit validates the existing manifests and creates a fork/PR using the token owner.
& $tool submit --no-open --prtitle $title $ManifestPath
if ($LASTEXITCODE -ne 0) { throw "WinGetCreate submission failed ($LASTEXITCODE)." }
