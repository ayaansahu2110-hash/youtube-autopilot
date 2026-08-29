param(
    [string]$Repo = "ayaansahu2110-hash/youtube-autopilot"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Find-Python {
    $venvPython = Join-Path (Get-Location) ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) { return $venvPython }
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    throw "Python is unavailable. Create the project .venv first."
}

function Find-Gh {
    $command = Get-Command gh -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $known = @(
        "$env:ProgramFiles\GitHub CLI\gh.exe",
        "$env:LOCALAPPDATA\Programs\GitHub CLI\gh.exe"
    )
    foreach ($path in $known) {
        if (Test-Path -LiteralPath $path) { return $path }
    }
    throw "GitHub CLI is unavailable. Install or reopen PowerShell after installation."
}

if (-not (Test-Path -LiteralPath ".git")) {
    throw "Run this script from the youtube-autopilot repository folder."
}
if (-not (Test-Path -LiteralPath "secrets\client_secret.json")) {
    throw "secrets\client_secret.json is missing. Use the same OAuth Desktop client file already used for ByteVexa."
}

$python = Find-Python
$gh = Find-Gh
$tokenPath = "secrets\youtube_token_curioaxiom.json"

Step "Selecting the isolated CurioAxiom profile"
$env:CHANNEL_PROFILE = "curioaxiom"
$env:CHANNEL_DISPLAY_NAME = "CurioAxiom"
$env:EXPECTED_YOUTUBE_CHANNEL_ID = "UCpddoAgL5DCidscCMx4WMHQ"
$env:YOUTUBE_TOKEN_FILE = $tokenPath

Step "Opening one-time Google authorization"
Write-Host "Choose the Google account that manages both channels, then select/authorize CurioAxiom." -ForegroundColor Yellow
& $python -m autopilot.cli auth-youtube
if ($LASTEXITCODE -ne 0) { throw "Google authorization was not completed." }

Step "Verifying that the token belongs to CurioAxiom, not ByteVexa"
& $python -m autopilot.cli verify-youtube
if ($LASTEXITCODE -ne 0) {
    throw "Channel verification failed. The token was not uploaded to GitHub."
}

Step "Installing only the CurioAxiom token in GitHub Actions"
$tokenB64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $tokenPath)))
& $gh secret set CURIOAXIOM_YOUTUBE_TOKEN_B64 --repo $Repo --body $tokenB64 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to configure CURIOAXIOM_YOUTUBE_TOKEN_B64." }

Step "Starting the first private CurioAxiom Short"
& $gh workflow run curioaxiom.yml --repo $Repo -f slot=morning
if ($LASTEXITCODE -ne 0) { throw "Token was configured, but the private test could not be started." }

Write-Host "`nCurioAxiom Phase 4 authorization is complete." -ForegroundColor Green
Write-Host "A PRIVATE test Short has been started in GitHub Actions." -ForegroundColor Green
Write-Host "ByteVexa credentials and workflows were not changed." -ForegroundColor Green
