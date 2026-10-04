#Requires -Version 5.1
<#
.SYNOPSIS
  Wire GitHub Actions secrets, variables, and environments for claim-ai CI/CD.

.NOTES
  Prerequisites:
    - gh auth login
    - Azure SP JSON at $env:TEMP\claim-ai-gha-sp.json (or pass -AzureCredsFile)
    - Docker Hub creds at $env:TEMP\claim-ai-hub.env (HUB_USER / HUB_PASS) or env vars
#>
param(
  [string]$Repo = "jjustisk/claim-ai",
  [string]$AzureCredsFile = "$env:TEMP\claim-ai-gha-sp.json",
  [string]$HubEnvFile = "$env:TEMP\claim-ai-hub.env",
  [string]$Reviewer = ""
)

$ErrorActionPreference = "Stop"

gh auth status | Out-Null
Write-Host "Authenticated. Configuring $Repo ..."

# --- Docker Hub ---
$hubUser = $env:DOCKERHUB_USERNAME
$hubPass = $env:DOCKERHUB_TOKEN
if (Test-Path $HubEnvFile) {
  Get-Content $HubEnvFile | ForEach-Object {
    if ($_ -match '^HUB_USER=(.+)$') { $hubUser = $matches[1] }
    if ($_ -match '^HUB_PASS=(.+)$') { $hubPass = $matches[1] }
  }
}
if (-not $hubUser -or -not $hubPass) {
  throw "Docker Hub credentials missing. Expected $HubEnvFile or DOCKERHUB_* env vars."
}

# --- Azure ---
if (-not (Test-Path $AzureCredsFile)) {
  throw "Azure credentials file missing: $AzureCredsFile"
}
$azureJson = Get-Content $AzureCredsFile -Raw

Write-Host "Setting Actions secrets..."
$hubUser | gh secret set DOCKERHUB_USERNAME --repo $Repo
$hubPass | gh secret set DOCKERHUB_TOKEN --repo $Repo
$azureJson | gh secret set AZURE_CREDENTIALS --repo $Repo

Write-Host "Setting repository variables..."
gh variable set DOCKERHUB_NAMESPACE --body "ctinashe" --repo $Repo
gh variable set AZURE_RESOURCE_GROUP --body "claim-ai-rg" --repo $Repo
gh variable set ACA_STAGING_FRONTEND --body "claim-ai-app" --repo $Repo
gh variable set ACA_STAGING_BACKEND --body "backend" --repo $Repo
gh variable set ACA_STAGING_CHROMA --body "chroma" --repo $Repo
gh variable set ACA_PROD_FRONTEND --body "claim-ai-app" --repo $Repo
gh variable set ACA_PROD_BACKEND --body "backend" --repo $Repo
gh variable set ACA_PROD_CHROMA --body "chroma" --repo $Repo

Write-Host "Creating environments (requires repo admin)..."
$envOk = $true
foreach ($envName in @("staging", "production")) {
  try {
    gh api -X PUT "repos/$Repo/environments/$envName" --silent 2>$null
    Write-Host "  environment: $envName"
  } catch {
    $envOk = $false
    Write-Host "  WARN: could not create '$envName' (need admin). It can be created on first workflow run."
  }
}

if ($envOk) {
  if (-not $Reviewer) {
    $Reviewer = (gh api user -q .login)
  }
  Write-Host "Setting production required reviewer: $Reviewer"
  try {
    $userId = gh api "users/$Reviewer" -q .id
    $body = @{
      wait_timer = 0
      prevent_self_review = $false
      reviewers = @(@{ type = "User"; id = [int]$userId })
      deployment_branch_policy = $null
    } | ConvertTo-Json -Depth 5
    $body | gh api -X PUT "repos/$Repo/environments/production" --input - --silent
  } catch {
    Write-Host "  WARN: could not set production reviewers (need admin). Add Required reviewers in GitHub → Settings → Environments → production."
  }
} else {
  Write-Host "Ask a repo admin (or open Settings → Environments) to create 'production' with Required reviewers for the APPROVE gate."
}
Write-Host ""
Write-Host "Done."
Write-Host "Secrets: DOCKERHUB_USERNAME, DOCKERHUB_TOKEN, AZURE_CREDENTIALS"
Write-Host "Next: commit/push .github/workflows/ci-cd.yml, then Actions → ci-cd → Run workflow."
Write-Host "For APPROVE gate: repo admin should add Required reviewers on Environment 'production'."
