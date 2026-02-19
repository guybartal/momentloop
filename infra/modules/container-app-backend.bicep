// Backend Container App (FastAPI + uvicorn)
param name string
param location string
param tags object = {}
param environmentId string

// Container configuration (configurable SKUs)
param containerImage string
param cpu string = '0.25'
param memory string = '0.5Gi'
param minReplicas int = 0
param maxReplicas int = 3

// ACR configuration
param acrLoginServer string

// Environment variables
param databaseUrl string
param storageAccountName string
param keyVaultName string
param corsOrigins string = ''

// Key Vault secret URIs
param keyVaultUri string

resource backend 'Microsoft.App/containerApps@2025-01-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        corsPolicy: {
          allowedOrigins: empty(corsOrigins) ? ['*'] : split(corsOrigins, ',')
          allowedMethods: ['*']
          allowedHeaders: ['*']
          allowCredentials: true
        }
      }
      registries: [
        {
          server: acrLoginServer
          identity: 'system'
        }
      ]
      secrets: [
        {
          name: 'google-client-id'
          keyVaultUrl: '${keyVaultUri}secrets/google-client-id'
          identity: 'system'
        }
        {
          name: 'google-client-secret'
          keyVaultUrl: '${keyVaultUri}secrets/google-client-secret'
          identity: 'system'
        }
        {
          name: 'google-ai-api-key'
          keyVaultUrl: '${keyVaultUri}secrets/google-ai-api-key'
          identity: 'system'
        }
        {
          name: 'fal-key'
          keyVaultUrl: '${keyVaultUri}secrets/fal-key'
          identity: 'system'
        }
        {
          name: 'jwt-secret'
          keyVaultUrl: '${keyVaultUri}secrets/jwt-secret'
          identity: 'system'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: containerImage
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: [
            { name: 'STORAGE_BACKEND', value: 'azure' }
            { name: 'AZURE_STORAGE_ACCOUNT_NAME', value: storageAccountName }
            { name: 'DATABASE_URL', value: databaseUrl }
            { name: 'GOOGLE_CLIENT_ID', secretRef: 'google-client-id' }
            { name: 'GOOGLE_CLIENT_SECRET', secretRef: 'google-client-secret' }
            { name: 'GOOGLE_AI_API_KEY', secretRef: 'google-ai-api-key' }
            { name: 'FAL_KEY', secretRef: 'fal-key' }
            { name: 'JWT_SECRET', secretRef: 'jwt-secret' }
            { name: 'CORS_ORIGINS', value: corsOrigins }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/api/health'
                port: 8000
              }
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/api/health'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
}

output id string = backend.id
output name string = backend.name
output fqdn string = backend.properties.configuration.ingress.fqdn
output principalId string = backend.identity.principalId
