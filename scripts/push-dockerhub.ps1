#Requires -Version 5.1
<#
.SYNOPSIS
  Push Claim AI images to a single private Docker Hub repo (free-plan friendly).

.NOTES
  Docker Hub free accounts allow only ONE private repository.
  This script uses:  <namespace>/claim-ai:<service>-<tag>
    e.g. ctinashe/claim-ai:backend-local
         ctinashe/claim-ai:frontend-local
         ctinashe/claim-ai:chroma-local

  - Refuses to push if compose is unhealthy or images are missing.
  - Refuses to push to a public repo.
  - Never prints tokens.
  - Set DOCKERHUB_TOKEN to a Hub Access Token, or the script uses docker-credential-desktop.
#>
param(
  [string]$EnvFile = ".env.docker",
  [string]$Namespace = "",
  [string]$Tag = "",
  [string]$RepoName = "claim-ai",
  [switch]$SkipComposeCheck,
  [switch]$SkipBackend
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Read-DotEnvValue([string]$Path, [string]$Key) {
  if (-not (Test-Path $Path)) { return $null }
  foreach ($line in Get-Content $Path) {
    if ($line -match "^\s*#" -or $line -notmatch "=") { continue }
    $parts = $line.Split("=", 2)
    if ($parts[0].Trim() -eq $Key) { return $parts[1].Trim() }
  }
  return $null
}

if (-not $Namespace) {
  $Namespace = Read-DotEnvValue $EnvFile "DOCKERHUB_NAMESPACE"
  if (-not $Namespace) { $Namespace = "ctinashe" }
}
if (-not $Tag) {
  $Tag = Read-DotEnvValue $EnvFile "IMAGE_TAG"
  if (-not $Tag) { $Tag = "local" }
}

$hubRepo = "$Namespace/$RepoName"
$backendRemote = "${hubRepo}:backend-$Tag"
$frontendRemote = "${hubRepo}:frontend-$Tag"
$chromaRemote = "${hubRepo}:chroma-$Tag"

# Local compose build names (may differ)
$backendLocal = "$Namespace/claim-ai-backend:$Tag"
$frontendLocal = "$Namespace/claim-ai-frontend:$Tag"
$chromaLocal = "$Namespace/claim-ai-chroma:$Tag"

Write-Host "Private Hub target (single repo, multi-tag):"
Write-Host "  $backendRemote"
Write-Host "  $frontendRemote"
Write-Host "  $chromaRemote"

if (-not $SkipComposeCheck) {
  Write-Host "`nChecking compose health..."
  $psJson = docker compose --env-file $EnvFile --profile local-db ps --format json
  if (-not $psJson) { throw "Compose stack not running." }
  $services = $psJson | ConvertFrom-Json
  if ($services -isnot [System.Array]) { $services = @($services) }
  foreach ($name in @("chroma", "backend", "frontend", "postgres")) {
    $svc = $services | Where-Object { $_.Service -eq $name } | Select-Object -First 1
    if (-not $svc) { throw "Required service '$name' is not running." }
    if ($svc.State -ne "running") { throw "Service '$name' state=$($svc.State)" }
    if ($svc.Health -and $svc.Health -ne "healthy") { throw "Service '$name' health=$($svc.Health)" }
    Write-Host "  OK $name"
  }
  $backendPort = Read-DotEnvValue $EnvFile "BACKEND_PORT"
  if (-not $backendPort) { $backendPort = "8000" }
  $probe = Invoke-WebRequest -Uri "http://127.0.0.1:$backendPort/health" -UseBasicParsing -TimeoutSec 10
  if ($probe.StatusCode -ne 200) { throw "Backend health failed" }
}

foreach ($img in @($backendLocal, $frontendLocal, $chromaLocal)) {
  docker image inspect $img *> $null
  if ($LASTEXITCODE -ne 0) { throw "Local image missing: $img" }
}

# Auth
$token = $env:DOCKERHUB_TOKEN
if (-not $token) {
  $credJson = "https://index.docker.io/v1/" | & docker-credential-desktop get
  $cred = $credJson | ConvertFrom-Json
  $token = $cred.Secret
  if (-not $Namespace) { $Namespace = $cred.Username }
}
if (-not $token) { throw "No Docker Hub credentials. Set DOCKERHUB_TOKEN or docker login." }

$loginBody = @{ username = $Namespace; password = $token } | ConvertTo-Json
$login = Invoke-RestMethod -Uri "https://hub.docker.com/v2/users/login/" -Method Post -Body $loginBody -ContentType "application/json"
$jwt = $login.token
if (-not $jwt) { throw "Docker Hub API login failed." }
$headers = @{ Authorization = "JWT $jwt" }

$uri = "https://hub.docker.com/v2/repositories/$Namespace/$RepoName/"
try {
  $existing = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get
  if (-not $existing.is_private) {
    throw "Repo $hubRepo is PUBLIC. Refusing to push. Make it private first."
  }
  Write-Host "Repo $hubRepo is private: OK"
} catch {
  if ($_.Exception.Response.StatusCode.value__ -eq 404) {
    $createBody = @{
      namespace = $Namespace
      name = $RepoName
      is_private = $true
      description = "Claim AI private multi-tag images (backend/frontend/chroma)"
    } | ConvertTo-Json
    Invoke-RestMethod -Uri "https://hub.docker.com/v2/repositories/" -Headers $headers -Method Post -Body $createBody -ContentType "application/json" | Out-Null
    Write-Host "Created private repo $hubRepo"
  } else { throw }
}

$token | docker login -u $Namespace --password-stdin
if ($LASTEXITCODE -ne 0) { throw "docker login failed" }

docker tag $backendLocal $backendRemote
docker tag $frontendLocal $frontendRemote
docker tag $chromaLocal $chromaRemote

Write-Host "`nPushing frontend..."
docker push $frontendRemote
if ($LASTEXITCODE -ne 0) { throw "Push failed: $frontendRemote" }

Write-Host "Pushing chroma..."
docker push $chromaRemote
if ($LASTEXITCODE -ne 0) { throw "Push failed: $chromaRemote" }

if (-not $SkipBackend) {
  Write-Host "Pushing backend (large)..."
  docker push $backendRemote
  if ($LASTEXITCODE -ne 0) { throw "Push failed: $backendRemote" }
} else {
  Write-Host "Skipping backend push (-SkipBackend)"
}

$repo = Invoke-RestMethod -Uri $uri -Headers $headers
Write-Host "`nDone. private=$($repo.is_private)"
Write-Host "  docker pull $frontendRemote"
Write-Host "  docker pull $chromaRemote"
if (-not $SkipBackend) { Write-Host "  docker pull $backendRemote" }
