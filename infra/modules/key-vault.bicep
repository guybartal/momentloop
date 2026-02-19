// Azure Key Vault for storing external API secrets
param name string
param location string
param tags object = {}

// Managed Identity principal ID for RBAC
param backendPrincipalId string

// Secrets to store (passed as secure parameters)
@secure()
param googleClientId string = ''
@secure()
param googleClientSecret string = ''
@secure()
param googleAiApiKey string = ''
@secure()
param falKey string = ''
@secure()
param jwtSecret string = ''

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: tenant().tenantId
    enableRbacAuthorization: true
    enabledForDeployment: false
    enabledForDiskEncryption: false
    enabledForTemplateDeployment: false
  }
}

// RBAC: Key Vault Secrets User for backend managed identity
resource kvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, backendPrincipalId, 'Key Vault Secrets User')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '4633458b-17de-408a-b874-0445c86b69e6' // Key Vault Secrets User
    )
    principalId: backendPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Store secrets (only if non-empty values provided)
resource secretGoogleClientId 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(googleClientId)) {
  parent: keyVault
  name: 'google-client-id'
  properties: {
    value: googleClientId
  }
}

resource secretGoogleClientSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(googleClientSecret)) {
  parent: keyVault
  name: 'google-client-secret'
  properties: {
    value: googleClientSecret
  }
}

resource secretGoogleAiApiKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(googleAiApiKey)) {
  parent: keyVault
  name: 'google-ai-api-key'
  properties: {
    value: googleAiApiKey
  }
}

resource secretFalKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(falKey)) {
  parent: keyVault
  name: 'fal-key'
  properties: {
    value: falKey
  }
}

resource secretJwtSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(jwtSecret)) {
  parent: keyVault
  name: 'jwt-secret'
  properties: {
    value: jwtSecret
  }
}

output id string = keyVault.id
output name string = keyVault.name
output uri string = keyVault.properties.vaultUri
