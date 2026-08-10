@description('Azure region for the Key Vault')
param location string = resourceGroup().location

@description('Environment name (dev, staging, prod)')
param environmentName string = 'dev'

@description('Globally unique Key Vault name (3-24 alphanumeric characters and hyphens)')
param keyVaultName string = 'claim-ai-kv'

@description('Azure AD group object ID — all members get read access to secrets')
param teamGroupObjectId string = ''

@description('Azure AD group object ID — members can create/update secrets')
param teamOfficerGroupObjectId string = ''

@description('App registration / managed identity object ID — the runtime app identity')
param appIdentityObjectId string = ''

@description('Enable purge protection (recommended for production)')
param enablePurgeProtection bool = (environmentName == 'prod')

var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69cf'
var keyVaultSecretsOfficerRoleId = 'b86a8fe4-44d3-4909-bae7-d8a9da7c0880'

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: enablePurgeProtection
  }
  tags: {
    project: 'claim-ai'
    environment: environmentName
  }
}

resource teamSecretsUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(teamGroupObjectId)) {
  name: guid(keyVault.id, teamGroupObjectId, keyVaultSecretsUserRoleId, 'team-secrets-user')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalId: teamGroupObjectId
    principalType: 'Group'
  }
}

resource teamSecretsOfficerRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(teamOfficerGroupObjectId)) {
  name: guid(keyVault.id, teamOfficerGroupObjectId, keyVaultSecretsOfficerRoleId, 'team-secrets-officer')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsOfficerRoleId)
    principalId: teamOfficerGroupObjectId
    principalType: 'Group'
  }
}

resource appSecretsUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(appIdentityObjectId)) {
  name: guid(keyVault.id, appIdentityObjectId, keyVaultSecretsUserRoleId, 'app-secrets-user')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalId: appIdentityObjectId
    principalType: 'ServicePrincipal'
  }
}

output keyVaultName string = keyVault.name
output keyVaultUri string = keyVault.properties.vaultUri
output resourceGroupName string = resourceGroup().name
output location string = location
