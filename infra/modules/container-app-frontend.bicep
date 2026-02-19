// Frontend Container App (React served by nginx)
param name string
param location string
param tags object = {}
param environmentId string

// Container configuration (configurable SKUs)
param containerImage string
param cpu string = '0.25'
param memory string = '0.5Gi'
param minReplicas int = 0
param maxReplicas int = 2

// ACR configuration
param acrLoginServer string

// Backend URL for API proxy
param backendFqdn string

resource frontend 'Microsoft.App/containerApps@2025-01-01' = {
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
        targetPort: 80
        transport: 'auto'
      }
      registries: [
        {
          server: acrLoginServer
          identity: 'system'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: containerImage
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: [
            { name: 'VITE_API_URL', value: 'https://${backendFqdn}' }
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
                concurrentRequests: '100'
              }
            }
          }
        ]
      }
    }
  }
}

output id string = frontend.id
output name string = frontend.name
output fqdn string = frontend.properties.configuration.ingress.fqdn
output principalId string = frontend.identity.principalId
