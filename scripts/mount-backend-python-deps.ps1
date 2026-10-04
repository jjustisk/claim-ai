# Mount persistent Azure Files at /deps on the backend Container App.
# Entrypoint installs pip packages into /deps once; later code deploys reuse them
# until requirements.txt changes.
#
# Usage: pwsh ./scripts/mount-backend-python-deps.ps1

$ErrorActionPreference = "Stop"

$rg = "claim-ai-rg"
$sa = "claimaistorage"
$share = "python-deps"
$envName = "managedEnvironment-claimairg-ac23"
$storageName = "pythondeps"
$app = "backend"

Write-Host "Ensuring Azure Files share '$share'..."
$exists = az storage share-rm exists -g $rg --storage-account $sa --name $share --query exists -o tsv
if ($exists -ne "true") {
  az storage share-rm create -g $rg --storage-account $sa --name $share --quota 64 -o none
}

$key = az storage account keys list -g $rg -n $sa --query "[0].value" -o tsv
Write-Host "Registering storage '$storageName' on ACA environment..."
az containerapp env storage set `
  --name $envName `
  --resource-group $rg `
  --storage-name $storageName `
  --azure-file-account-name $sa `
  --azure-file-account-key $key `
  --azure-file-share-name $share `
  --access-mode ReadWrite -o none

$doc = az containerapp show -g $rg -n $app -o json | ConvertFrom-Json
$c = $doc.properties.template.containers[0]

$envs = @()
foreach ($e in $c.env) {
  if ($e.name -eq "CLAIM_AI_DEPS_DIR") { continue }
  if ($e.secretRef) {
    $envs += @{ name = $e.name; secretRef = $e.secretRef }
  } else {
    $envs += @{ name = $e.name; value = $e.value }
  }
}
$envs += @{ name = "CLAIM_AI_DEPS_DIR"; value = "/deps" }

$payload = @{
  properties = @{
    template = @{
      containers = @(
        @{
          name = $c.name
          image = $c.image
          env = $envs
          resources = @{
            cpu = $c.resources.cpu
            memory = $c.resources.memory
          }
          volumeMounts = @(
            @{ volumeName = "python-deps"; mountPath = "/deps" }
          )
        }
      )
      scale = @{
        minReplicas = $doc.properties.template.scale.minReplicas
        maxReplicas = $doc.properties.template.scale.maxReplicas
      }
      volumes = @(
        @{ name = "python-deps"; storageType = "AzureFile"; storageName = $storageName }
      )
    }
  }
}

$dst = Join-Path $env:TEMP "backend-aca-deps-volume.json"
[System.IO.File]::WriteAllText($dst, ($payload | ConvertTo-Json -Depth 30))
Write-Host "Patching $app to mount /deps..."
az rest --method patch --uri "$($doc.id)?api-version=2024-03-01" --body "@$dst" -o none

az containerapp show -g $rg -n $app --query "{volumes:properties.template.volumes, mounts:properties.template.containers[0].volumeMounts, depsDir:properties.template.containers[0].env[?name=='CLAIM_AI_DEPS_DIR'].value|[0]}" -o json
Write-Host "Done. First boot still installs once into the share; later code deploys reuse /deps."
