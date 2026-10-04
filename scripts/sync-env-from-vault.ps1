#Requires -Version 5.1
<#
.SYNOPSIS
  Pull Azure Key Vault secrets into .env.docker for local Docker -> Azure resources.

.NOTES
  Requires: az login, access to claim-ai-kv.
  Does NOT use local Postgres. Chroma stays the compose service.
#>
param(
  [string]$VaultName = "claim-ai-kv",
  [string]$OutFile = ".env.docker"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Get-Secret([string]$name) {
  $v = az keyvault secret show --vault-name $VaultName --name $name --query value -o tsv 2>$null
  if ($LASTEXITCODE -ne 0) { return "" }
  return ("$v").Trim()
}

function Esc([string]$value) {
  if ($null -eq $value) { return "" }
  return $value.Replace("`r", "").Replace("`n", "")
}

Write-Host "Reading secrets from $VaultName ..."
$dbUrl = Get-Secret "database-url"
$jwt = Get-Secret "jwt-secret-key"
$jwtAlg = Get-Secret "jwt-algorithm"
if (-not $jwtAlg) { $jwtAlg = "HS256" }
$storage = Get-Secret "azure-storage-connection-string"
$img = Get-Secret "azure-storage-images-container-name"
$vid = Get-Secret "azure-storage-videos-container-name"
$pds = Get-Secret "azure-storage-pds-policies-container-name"
$aiProj = Get-Secret "azure-ai-project-endpoint"
$aiSvc = Get-Secret "azure-ai-services-endpoint"
$gpt = Get-Secret "foundry-gpt-deployment"
$router = Get-Secret "foundry-router-deployment"
$claude = Get-Secret "foundry-claude-deployment"
$acs = Get-Secret "azure-communication-connection-string"
$acsEmail = Get-Secret "azure-communication-email-sender"

if (-not $dbUrl) { throw "Vault secret database-url is empty" }

if (-not $jwt -or $jwt.Length -lt 32 -or $jwt -match '^(changeme|change-me|secret|password)$') {
  Write-Host "WARNING: vault jwt-secret-key is missing/weak - rotating in Key Vault..."
  $jwt = python -c "import secrets; print(secrets.token_urlsafe(48))"
  $tmp = New-TemporaryFile
  try {
    Set-Content -Path $tmp.FullName -Value $jwt -NoNewline -Encoding ascii
    az keyvault secret set --vault-name $VaultName --name jwt-secret-key --file $tmp.FullName | Out-Null
    Write-Host "Rotated jwt-secret-key in $VaultName (invalidates existing JWTs)."
  } finally {
    Remove-Item -Force $tmp.FullName -ErrorAction SilentlyContinue
  }
}

$chroma = ""
$enc = ""
if (Test-Path $OutFile) {
  foreach ($line in Get-Content $OutFile) {
    if ($line -match '^CHROMA_AUTH_TOKEN=(.+)$') { $chroma = $Matches[1] }
    if ($line -match '^CLAIM_AI_ENCRYPTION_KEY=(.+)$') { $enc = $Matches[1] }
  }
}
if (-not $chroma) { $chroma = python -c "import secrets; print(secrets.token_urlsafe(48))" }
if (-not $enc) { $enc = python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" }

$notify = if ($acs) { "true" } else { "false" }

$lines = @(
  "# Claim AI Docker -> Azure (synced from Key Vault). NEVER commit.",
  "#   .\scripts\sync-env-from-vault.ps1",
  "#   docker compose --env-file .env.docker -f docker-compose.hub.yml up -d",
  "",
  "APP_ENV=production",
  "CLAIM_AI_SECRETS_SOURCE=env",
  "ENABLE_TEST_UI=false",
  "ENABLE_OPENAPI_DOCS=false",
  "",
  "FRONTEND_PORT=8088",
  "BACKEND_PORT=8000",
  "DOCKERHUB_NAMESPACE=ctinashe",
  "IMAGE_TAG=local",
  "",
  "JWT_SECRET_KEY=$(Esc $jwt)",
  "JWT_ALGORITHM=$(Esc $jwtAlg)",
  "DATABASE_URL=$(Esc $dbUrl)",
  "",
  "AZURE_STORAGE_CONNECTION_STRING=$(Esc $storage)",
  "AZURE_STORAGE_IMAGES_CONTAINER_NAME=$(Esc $img)",
  "AZURE_STORAGE_VIDEOS_CONTAINER_NAME=$(Esc $vid)",
  "AZURE_STORAGE_PDS_POLICIES_CONTAINER_NAME=$(Esc $pds)",
  "",
  "AZURE_AI_PROJECT_ENDPOINT=$(Esc $aiProj)",
  "AZURE_AI_SERVICES_ENDPOINT=$(Esc $aiSvc)",
  "FOUNDRY_GPT_DEPLOYMENT=$(Esc $gpt)",
  "FOUNDRY_MINI_DEPLOYMENT=gpt-5.4-mini",
  "FOUNDRY_NANO_DEPLOYMENT=gpt-5.4-nano",
  "FOUNDRY_ROUTER_DEPLOYMENT=$(Esc $router)",
  "FOUNDRY_CLAUDE_DEPLOYMENT=$(Esc $claude)",
  "FOUNDRY_EMBEDDING_DEPLOYMENT=text-embedding-3-large",
  "",
  "CLAIM_AI_ENCRYPTION_KEY=$(Esc $enc)",
  "CORS_ORIGINS=http://127.0.0.1:8088,http://localhost:8088",
  "TRUSTED_HOSTS=localhost,127.0.0.1,backend,frontend",
  "",
  "AZURE_KEY_VAULT_NAME=$VaultName",
  "",
  "CHROMA_HOST=chroma",
  "CHROMA_PORT=8000",
  "CHROMA_COLLECTION_NAME=claim-ai",
  "CHROMA_AUTH_TOKEN=$(Esc $chroma)",
  "",
  "NOTIFICATIONS_ENABLED=$notify",
  "AZURE_COMMUNICATION_CONNECTION_STRING=$(Esc $acs)",
  "AZURE_COMMUNICATION_EMAIL_SENDER=$(Esc $acsEmail)",
  "AZURE_COMMUNICATION_SMS_SENDER="
)

Set-Content -Path $OutFile -Value $lines -Encoding utf8
Write-Host "Wrote $OutFile"

$uri = $dbUrl -replace '^postgresql\+psycopg', 'postgresql'
$hostName = ([uri]$uri).Host
$ip = Invoke-RestMethod -Uri "https://api.ipify.org"
Write-Host "Ensuring Postgres firewall allows $ip on $hostName ..."
$rgQuery = "[?fullyQualifiedDomainName=='$hostName'].resourceGroup | [0]"
$nameQuery = "[?fullyQualifiedDomainName=='$hostName'].name | [0]"
$rg = az postgres flexible-server list --query $rgQuery -o tsv
$server = az postgres flexible-server list --query $nameQuery -o tsv
if ($rg -and $server) {
  $rule = "claim-ai-docker-" + ($ip -replace '\.', '-')
  cmd /c "az postgres flexible-server firewall-rule create -g $rg -n $server --rule-name $rule --start-ip-address $ip --end-ip-address $ip >nul 2>&1"
  Write-Host "Firewall rule OK: $rule"
} else {
  Write-Host "WARNING: could not resolve flexible server for firewall update - add $ip manually."
}

Write-Host ""
Write-Host "Next:"
Write-Host "  docker compose --env-file .env.docker -f docker-compose.hub.yml up -d"
Write-Host "(no --profile local-db - Azure Postgres is used)"
