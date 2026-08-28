param(
    [string]$Repo = "ayaansahu2110-hash/youtube-autopilot"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Find-Gh {
    $cmd = Get-Command gh -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $known = @(
        "$env:ProgramFiles\GitHub CLI\gh.exe",
        "$env:LOCALAPPDATA\Programs\GitHub CLI\gh.exe"
    )
    foreach ($path in $known) {
        if (Test-Path $path) { return $path }
    }
    return $null
}

function Read-DotEnvValue([string]$Name) {
    if (-not (Test-Path ".env")) { return $null }
    $escaped = [regex]::Escape($Name)
    $value = $null
    foreach ($line in Get-Content ".env") {
        if ($line -match "^\s*$escaped\s*=\s*(.*)$") {
            $value = $Matches[1].Trim()
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }
    }
    return $value
}

function Set-RepoSecret([string]$Name, [string]$Value, [string]$GhPath) {
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "$Name is missing. Add it locally before running setup."
    }
    & $GhPath secret set $Name --repo $Repo --body $Value | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to set GitHub secret $Name." }
    Write-Host "Configured secret: $Name" -ForegroundColor Green
}

function Set-RepoVariable([string]$Name, [string]$Value, [string]$GhPath) {
    & $GhPath variable set $Name --repo $Repo --body $Value | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to set GitHub variable $Name." }
    Write-Host "Configured variable: $Name=$Value" -ForegroundColor Green
}

Step "Checking that you are inside the ByteVexa repository"
if (-not (Test-Path ".git")) {
    throw "Run this command from the youtube-autopilot project folder."
}

Step "Checking GitHub CLI"
$gh = Find-Gh
if (-not $gh) {
    Write-Host "GitHub CLI is not installed. Installing it now..."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "GitHub CLI is missing and winget is unavailable. Install GitHub CLI once, then rerun this script."
    }
    & winget install --id GitHub.cli -e --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "GitHub CLI installation failed." }
    $gh = Find-Gh
    if (-not $gh) {
        throw "GitHub CLI installed, but this shell cannot find it yet. Close PowerShell, reopen it in this folder, and run the same command again."
    }
}
Write-Host "GitHub CLI ready." -ForegroundColor Green

Step "Checking GitHub sign-in"
# GitHub CLI writes its unauthenticated status to stderr. Windows PowerShell 5 can
# turn that expected stderr output into a terminating NativeCommandError when
# ErrorActionPreference is Stop, so run the status probe through cmd and inspect
# only its exit code.
$quotedGh = '"' + $gh + '"'
& cmd.exe /d /c "$quotedGh auth status --hostname github.com >nul 2>&1"
$authStatus = $LASTEXITCODE
if ($authStatus -ne 0) {
    Write-Host "A browser sign-in will open. Sign in to GitHub and approve access once."
    & $gh auth login --hostname github.com --web --git-protocol https
    if ($LASTEXITCODE -ne 0) { throw "GitHub sign-in was not completed." }
}
Write-Host "GitHub authorized." -ForegroundColor Green

Step "Reading local credentials without displaying them"
$gemini = Read-DotEnvValue "GEMINI_API_KEY"
$pexels = Read-DotEnvValue "PEXELS_API_KEY"
$clientPath = "secrets/client_secret.json"
$tokenPath = "secrets/youtube_token.json"

if ([string]::IsNullOrWhiteSpace($gemini)) { throw "GEMINI_API_KEY is missing from .env." }
if ([string]::IsNullOrWhiteSpace($pexels)) { throw "PEXELS_API_KEY is missing from .env." }
if (-not (Test-Path $clientPath)) { throw "$clientPath is missing." }
if (-not (Test-Path $tokenPath)) { throw "$tokenPath is missing." }

$clientB64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Resolve-Path $clientPath)))
$tokenB64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Resolve-Path $tokenPath)))

Step "Securely configuring GitHub Actions"
Set-RepoSecret "GEMINI_API_KEY" $gemini $gh
Set-RepoSecret "PEXELS_API_KEY" $pexels $gh
Set-RepoSecret "YOUTUBE_CLIENT_SECRETS_B64" $clientB64 $gh
Set-RepoSecret "YOUTUBE_TOKEN_B64" $tokenB64 $gh
Set-RepoVariable "GEMINI_MODEL" "gemini-2.5-flash" $gh
Set-RepoVariable "UPLOAD_PRIVACY_STATUS" "private" $gh
Set-RepoVariable "ALLOW_PUBLIC_UPLOADS" "false" $gh

Step "Starting the first private cloud test"
& $gh workflow run daily.yml --repo $Repo
if ($LASTEXITCODE -ne 0) {
    throw "Secrets were configured, but the first workflow could not be started."
}

Write-Host "`nByteVexa cloud automation is configured." -ForegroundColor Green
Write-Host "The first test has been started with PRIVATE YouTube visibility." -ForegroundColor Green
Write-Host "Your PC can be switched off after this command finishes." -ForegroundColor Green
Write-Host "The scheduled workflow will run daily in GitHub Actions." -ForegroundColor Green
