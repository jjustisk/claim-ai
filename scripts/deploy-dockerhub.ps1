#Requires -Version 5.1
<#
.SYNOPSIS
  Build thin images, push to private Docker Hub repo, pull, and run until healthy.

.DESCRIPTION
  Backend image is CODE-ONLY (~hundreds of MB). Python packages install on first
  container start into the python_deps volume — that is what used to bloat Hub to 3.5GB.

  Private Hub repo (free plan = 1 private repo):
    ctinashe/claim-ai:backend-local
    ctinashe/claim-ai:frontend-local
    ctinashe/claim-ai:chroma-local
#>
param(
  [string]$EnvFile = ".env.docker",
  [string]$Namespace = "ctinashe",
  [string]$Tag = "local",
  [string]$RepoName = "claim-ai",
  [switch]$SkipBuild,
  [switch]$SkipPush,
  [switch]$SkipRun
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

$ns = Read-DotEnvValue $EnvFile "DOCKERHUB_NAMESPACE"; if ($ns) { $Namespace = $ns }
$tg = Read-DotEnvValue $EnvFile "IMAGE_TAG"; if ($tg) { $Tag = $tg }

$backend = "$Namespace/${RepoName}:backend-$Tag"
$frontend = "$Namespace/${RepoName}:frontend-$Tag"
$chroma = "$Namespace/${RepoName}:chroma-$Tag"

Write-Host "=== Claim AI Docker Hub deploy ==="
Write-Host "Targets: $backend | $frontend | $chroma"
Write-Host ""
Write-Host "Why backend was 3.5GB before: pip packages (spaCy model, ONNX/Chroma, OpenCV)"
Write-Host "were Baked INTO the image at build time. Now the image ships CODE only;"
Write-Host "pip install runs inside the container on first start (cached in a volume)."
Write-Host ""

if (-not $SkipBuild) {
  Write-Host "[1/4] Building thin images..."
  docker compose --env-file $EnvFile build
  if ($LASTEXITCODE -ne 0) { throw "Build failed" }
  docker images "$Namespace/${RepoName}" --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}"
}

if (-not $SkipPush) {
  Write-Host "`n[2/4] Auth + ensure private Hub repo..."
  $credJson = "https://index.docker.io/v1/" | & docker-credential-desktop get
  $cred = $credJson | ConvertFrom-Json
  $token = $cred.Secret
  $user = $cred.Username
  if (-not $token) { throw "docker login required" }

  $loginBody = @{ username = $user; password = $token } | ConvertTo-Json
  $login = Invoke-RestMethod -Uri "https://hub.docker.com/v2/users/login/" -Method Post -Body $loginBody -ContentType "application/json"
  $headers = @{ Authorization = "JWT $($login.token)" }
  $uri = "https://hub.docker.com/v2/repositories/$Namespace/$RepoName/"
  try {
    $repo = Invoke-RestMethod -Uri $uri -Headers $headers
    if (-not $repo.is_private) { throw "Hub repo $Namespace/$RepoName is PUBLIC — refuse to push." }
  } catch {
    if ($_.Exception.Response.StatusCode.value__ -eq 404) {
      $body = @{ namespace = $Namespace; name = $RepoName; is_private = $true; description = "Claim AI private multi-tag" } | ConvertTo-Json
      Invoke-RestMethod -Uri "https://hub.docker.com/v2/repositories/" -Headers $headers -Method Post -Body $body -ContentType "application/json" | Out-Null
      Write-Host "Created private $Namespace/$RepoName"
    } else { throw }
  }

  $token | docker login -u $user --password-stdin | Out-Null

  Write-Host "[3/4] Pushing (backend should be SMALL now)..."
  foreach ($img in @($frontend, $chroma, $backend)) {
    Write-Host "  -> $img"
    docker push $img
    if ($LASTEXITCODE -ne 0) { throw "Push failed: $img" }
  }
  Write-Host "All pushes OK."
}

if (-not $SkipRun) {
  Write-Host "`n[4/4] Pull + run from Hub..."
  docker compose --env-file $EnvFile --profile local-db -f docker-compose.hub.yml pull
  if ($LASTEXITCODE -ne 0) { throw "Pull failed" }

  docker compose --env-file $EnvFile --profile local-db -f docker-compose.hub.yml up -d
  if ($LASTEXITCODE -ne 0) { throw "Up failed" }

  $backendPort = Read-DotEnvValue $EnvFile "BACKEND_PORT"
  if (-not $backendPort) { $backendPort = "8000" }
  $frontendPort = Read-DotEnvValue $EnvFile "FRONTEND_PORT"
  if (-not $frontendPort) { $frontendPort = "8080" }

  Write-Host "Waiting for backend health (first boot installs pip deps — can take 5–15 min)..."
  $deadline = (Get-Date).AddMinutes(20)
  $ok = $false
  while ((Get-Date) -lt $deadline) {
    try {
      $r = Invoke-WebRequest -Uri "http://127.0.0.1:$backendPort/health" -UseBasicParsing -TimeoutSec 5
      if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch { }
    Start-Sleep -Seconds 15
    Write-Host "  still waiting... $(Get-Date -Format HH:mm:ss)"
  }
  if (-not $ok) {
    docker compose --env-file $EnvFile --profile local-db -f docker-compose.hub.yml logs --tail=80 backend
    throw "Backend did not become healthy in time"
  }

  Write-Host "`nDEPLOY OK"
  Write-Host "  Backend:  http://127.0.0.1:$backendPort/health"
  Write-Host "  Frontend: http://127.0.0.1:$frontendPort/"
  docker compose --env-file $EnvFile --profile local-db -f docker-compose.hub.yml ps
}
