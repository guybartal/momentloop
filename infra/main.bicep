// MomentLoop Azure Infrastructure
// Deploy with: azd provision
targetScope = 'resourceGroup'

// ============================================================
// Parameters — all configurable via main.bicepparam
// ============================================================

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Unique environment name used for resource naming')
param environmentName string

@description('Tags applied to all resources')
param tags object = {}

// -- PostgreSQL SKU parameters --
@description('PostgreSQL compute SKU name (e.g. Standard_B1ms, Standard_D2s_v3)')
param postgresSkuName string = 'Standard_B1ms'
@description('PostgreSQL compute tier (Burstable, GeneralPurpose, MemoryOptimized)')
param postgresSkuTier string = 'Burstable'
@description('PostgreSQL storage size in GB')
param postgresStorageSizeGB int = 32
@description('PostgreSQL HA mode (Disabled, ZoneRedundant)')
param postgresHaMode string = 'Disabled'
@secure()
@description('PostgreSQL admin password (for initial setup)')
param postgresAdminPassword string

// -- Container Apps SKU parameters --
@description('Backend CPU cores (e.g. 0.25, 0.5, 1.0, 2.0)')
param backendCpu string = '0.25'
@description('Backend memory (e.g. 0.5Gi, 1.0Gi, 2.0Gi)')
param backendMemory string = '0.5Gi'
@description('Backend minimum replicas (0 = scale to zero)')
param backendMinReplicas int = 0
@description('Backend maximum replicas')
param backendMaxReplicas int = 3
@description('Frontend CPU cores')
param frontendCpu string = '0.25'
@description('Frontend memory')
param frontendMemory string = '0.5Gi'
@description('Frontend minimum replicas')
param frontendMinReplicas int = 0
@description('Frontend maximum replicas')
param frontendMaxReplicas int = 2

// -- Storage SKU --
@description('Storage account SKU (Standard_LRS, Standard_GRS, etc.)')
param storageSkuName string = 'Standard_LRS'

// -- Container Registry SKU --
@description('Container Registry SKU (Basic, Standard, Premium)')
param acrSku string = 'Basic'

// -- Container images (set by CI/CD or azd deploy) --
param backendImage string = ''
param frontendImage string = ''

// -- Key Vault secrets (set during first deployment) --
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

// -- CORS --
param corsOrigins string = ''

// ============================================================
// Resource naming
// ============================================================

// Short unique suffix for globally-unique names (ACR, Storage)
var uniqueSuffix = toLower(take(uniqueString(resourceGroup().id, environmentName), 6))

var names = {
  logAnalytics: 'log-${environmentName}'
  acr: 'cr${environmentName}${uniqueSuffix}'
  storageAccount: 'st${environmentName}${uniqueSuffix}'
  keyVault: 'kv-${environmentName}'
  postgres: 'psql-${environmentName}'
  containerAppsEnv: 'cae-${environmentName}'
  backendApp: 'ca-${environmentName}-backend'
  frontendApp: 'ca-${environmentName}-frontend'
}

// ============================================================
// Modules
// ============================================================

// 1. Monitoring (Log Analytics)
module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    name: names.logAnalytics
    location: location
    tags: tags
  }
}

// 2. Container Registry
module acr 'modules/container-registry.bicep' = {
  name: 'acr'
  params: {
    name: names.acr
    location: location
    tags: tags
    sku: acrSku
  }
}

// 3. Container Apps Environment
module containerAppsEnv 'modules/container-apps-env.bicep' = {
  name: 'containerAppsEnv'
  params: {
    name: names.containerAppsEnv
    location: location
    tags: tags
    logAnalyticsCustomerId: monitoring.outputs.customerId
    logAnalyticsSharedKey: monitoring.outputs.sharedKey
  }
}

// 4. Backend Container App
//    Uses Key Vault name (not output) to construct URI deterministically,
//    breaking the cycle: backend <-> keyVault
module backend 'modules/container-app-backend.bicep' = {
  name: 'backend'
  params: {
    name: names.backendApp
    location: location
    tags: tags
    environmentId: containerAppsEnv.outputs.id
    containerImage: !empty(backendImage)
      ? backendImage
      : 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
    cpu: backendCpu
    memory: backendMemory
    minReplicas: backendMinReplicas
    maxReplicas: backendMaxReplicas
    acrLoginServer: acr.outputs.loginServer
    databaseUrl: 'postgresql+asyncpg://momentloopadmin:${postgresAdminPassword}@${names.postgres}.postgres.database.azure.com:5432/momentloop?ssl=require'
    storageAccountName: names.storageAccount
    keyVaultName: names.keyVault
    corsOrigins: corsOrigins
  }
}

// 5. Frontend Container App
module frontend 'modules/container-app-frontend.bicep' = {
  name: 'frontend'
  params: {
    name: names.frontendApp
    location: location
    tags: tags
    environmentId: containerAppsEnv.outputs.id
    containerImage: !empty(frontendImage)
      ? frontendImage
      : 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
    cpu: frontendCpu
    memory: frontendMemory
    minReplicas: frontendMinReplicas
    maxReplicas: frontendMaxReplicas
    acrLoginServer: acr.outputs.loginServer
    backendFqdn: backend.outputs.fqdn
  }
}

// 6. PostgreSQL Flexible Server
module postgres 'modules/postgresql.bicep' = {
  name: 'postgres'
  params: {
    name: names.postgres
    location: location
    tags: tags
    skuName: postgresSkuName
    skuTier: postgresSkuTier
    storageSizeGB: postgresStorageSizeGB
    haMode: postgresHaMode
    administratorPassword: postgresAdminPassword
  }
}

// 7. Storage Account (depends on backend for RBAC principalId)
module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    name: names.storageAccount
    location: location
    tags: tags
    skuName: storageSkuName
    backendPrincipalId: backend.outputs.principalId
  }
}

// 8. Key Vault (depends on backend for RBAC principalId)
module keyVault 'modules/key-vault.bicep' = {
  name: 'keyVault'
  params: {
    name: names.keyVault
    location: location
    tags: tags
    backendPrincipalId: backend.outputs.principalId
    googleClientId: googleClientId
    googleClientSecret: googleClientSecret
    googleAiApiKey: googleAiApiKey
    falKey: falKey
    jwtSecret: jwtSecret
  }
}

// 9. RBAC: Backend -> ACR (AcrPull)
//    Use deterministic names for guid() to avoid BCP120 errors
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, names.backendApp, 'AcrPull')
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull
    )
    principalId: backend.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

// RBAC: Frontend -> ACR (AcrPull)
resource acrPullRoleFrontend 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, names.frontendApp, 'AcrPull')
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull
    )
    principalId: frontend.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================
// Outputs
// ============================================================

output AZURE_CONTAINER_REGISTRY_NAME string = acr.outputs.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = acr.outputs.loginServer
output BACKEND_FQDN string = backend.outputs.fqdn
output FRONTEND_FQDN string = frontend.outputs.fqdn
output BACKEND_URL string = 'https://${backend.outputs.fqdn}'
output FRONTEND_URL string = 'https://${frontend.outputs.fqdn}'
output POSTGRES_FQDN string = postgres.outputs.fqdn
output STORAGE_ACCOUNT_NAME string = storage.outputs.name
output KEY_VAULT_NAME string = keyVault.outputs.name
