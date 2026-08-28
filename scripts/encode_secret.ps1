param(
  [Parameter(Mandatory=$true)]
  [string]$Path
)

if (-not (Test-Path $Path)) {
  throw "File not found: $Path"
}

$bytes = [System.IO.File]::ReadAllBytes((Resolve-Path $Path))
$encoded = [Convert]::ToBase64String($bytes)
Set-Clipboard -Value $encoded
Write-Host "Base64 value copied to your clipboard. Paste it into the matching GitHub Actions secret."
