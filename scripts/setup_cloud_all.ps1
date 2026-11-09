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
        "C:\Program Files\GitHub CLI\gh.exe",
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
        throw "$Name is missing. Add it before running cloud setup."
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

Step "Locating GitHub CLI"
$gh = Find-Gh
if (-not $gh) {
    throw "GitHub CLI (gh.exe) could not be found."
}
Write-Host "Using GitHub CLI: $gh" -ForegroundColor Green

Step "Reading AI and Pexels API credentials"
$gemini = Read-DotEnvValue "GEMINI_API_KEY"
$pexels = Read-DotEnvValue "PEXELS_API_KEY"
if ([string]::IsNullOrWhiteSpace($gemini)) { throw "GEMINI_API_KEY is missing in .env." }
if ([string]::IsNullOrWhiteSpace($pexels)) { throw "PEXELS_API_KEY is missing in .env." }

Step "Checking YouTube Client Secrets"
$clientPath = "secrets/client_secret.json"
if (-not (Test-Path $clientPath)) { throw "$clientPath is missing." }
$clientB64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Resolve-Path $clientPath)))

Step "Checking all 7 Channel OAuth Tokens"
$channels = @(
    @{ Profile = "bytevexa"; Secret = "YOUTUBE_TOKEN_B64"; File = "secrets/youtube_token.json"; DisplayName = "ByteVexa" },
    @{ Profile = "curioaxiom"; Secret = "CURIOAXIOM_YOUTUBE_TOKEN_B64"; File = "secrets/youtube_token_curioaxiom.json"; DisplayName = "CurioAxiom" },
    @{ Profile = "wondertales"; Secret = "WONDERTALES_YOUTUBE_TOKEN_B64"; File = "secrets/youtube_token_wondertales.json"; DisplayName = "WonderTales Kids" },
    @{ Profile = "mokshavani"; Secret = "MOKSHAVANI_YOUTUBE_TOKEN_B64"; File = "secrets/youtube_token_mokshavani.json"; DisplayName = "MokshaVani" },
    @{ Profile = "apexstoic"; Secret = "APEXSTOIC_YOUTUBE_TOKEN_B64"; File = "secrets/youtube_token_apexstoic.json"; DisplayName = "ApexStoic" },
    @{ Profile = "chronosenigma"; Secret = "CHRONOSENIGMA_YOUTUBE_TOKEN_B64"; File = "secrets/youtube_token_chronosenigma.json"; DisplayName = "ChronosEnigma" },
    @{ Profile = "empirepulse"; Secret = "EMPIREPULSE_YOUTUBE_TOKEN_B64"; File = "secrets/youtube_token_empirepulse.json"; DisplayName = "EmpirePulse" },
    @{ Profile = "astrapulse"; Secret = "ASTRAPULSE_YOUTUBE_TOKEN_B64"; File = "secrets/youtube_token_astrapulse.json"; DisplayName = "AstraPulse" }
)

foreach ($ch in $channels) {
    if (-not (Test-Path $ch.File)) {
        if ($ch.Profile -eq "astrapulse") {
            Write-Host "Notice: AstraPulse token not found yet (will upload after authorization)." -ForegroundColor Yellow
            continue
        }
        throw "Token file for $($ch.DisplayName) ($($ch.File)) is missing!"
    }
}

Step "Uploading Core Secrets to GitHub repository: $Repo"
Set-RepoSecret "GEMINI_API_KEY" $gemini $gh
Set-RepoSecret "PEXELS_API_KEY" $pexels $gh
Set-RepoSecret "YOUTUBE_CLIENT_SECRETS_B64" $clientB64 $gh

Step "Uploading Channel OAuth Tokens to GitHub repository"
foreach ($ch in $channels) {
    if (Test-Path $ch.File) {
        $b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Resolve-Path $ch.File)))
        Set-RepoSecret $ch.Secret $b64 $gh
    }
}
    Set-RepoSecret $ch.Secret $b64 $gh
}

Step "Setting Repository Variables for Production"
Set-RepoVariable "GEMINI_MODEL" "gemini-flash-latest" $gh
Set-RepoVariable "UPLOAD_PRIVACY_STATUS" "public" $gh
Set-RepoVariable "ALLOW_PUBLIC_UPLOADS" "true" $gh
Set-RepoVariable "SHORTS_PUBLIC" "true" $gh
Set-RepoVariable "ENABLE_UPLOADS" "true" $gh
Set-RepoVariable "SCHEDULE_TIMEZONE" "Asia/Kolkata" $gh

Write-Host "`nAll 7 channels' secrets and production variables have been uploaded successfully to GitHub Actions!" -ForegroundColor Green

