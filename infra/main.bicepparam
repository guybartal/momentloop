using './main.bicep'

// Environment name — change this per deployment
param environmentName = 'momentloop'

// Tags
param tags = {
  project: 'momentloop'
  environment: 'production'
}

// ============================================================
// SKU Configuration — adjust these to control costs
// ============================================================

// PostgreSQL: Burstable B1ms (~$13/mo) — smallest production-ready SKU
param postgresSkuName = 'Standard_B1ms'
param postgresSkuTier = 'Burstable'
param postgresStorageSizeGB = 32
param postgresHaMode = 'Disabled'

// Backend Container App: 0.25 vCPU, 0.5 GiB — scales to zero
param backendCpu = '0.25'
param backendMemory = '0.5Gi'
param backendMinReplicas = 0
param backendMaxReplicas = 3

// Frontend Container App: 0.25 vCPU, 0.5 GiB — scales to zero
param frontendCpu = '0.25'
param frontendMemory = '0.5Gi'
param frontendMinReplicas = 0
param frontendMaxReplicas = 2

// Storage: Standard LRS (locally redundant)
param storageSkuName = 'Standard_LRS'

// Container Registry: Basic (~$5/mo)
param acrSku = 'Basic'

// ============================================================
// Secrets — read from azd environment variables
// ============================================================
param postgresAdminPassword = readEnvironmentVariable('POSTGRES_ADMIN_PASSWORD', '')
param googleClientId = readEnvironmentVariable('GOOGLE_CLIENT_ID', '')
param googleClientSecret = readEnvironmentVariable('GOOGLE_CLIENT_SECRET', '')
param googleAiApiKey = readEnvironmentVariable('GOOGLE_AI_API_KEY', '')
param falKey = readEnvironmentVariable('FAL_KEY', '')
param jwtSecret = readEnvironmentVariable('JWT_SECRET', '')
