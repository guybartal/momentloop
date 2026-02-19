// Azure Database for PostgreSQL Flexible Server with Entra auth
param name string
param location string
param tags object = {}

// SKU parameters (configurable for cost control)
param skuName string = 'Standard_B1ms'
param skuTier string = 'Burstable'
param storageSizeGB int = 32
param haMode string = 'Disabled'
param version string = '16'
param databaseName string = 'momentloop'

// Managed Identity for Entra authentication
param backendPrincipalId string

// Admin - used for initial setup only
param administratorLogin string = 'momentloopadmin'
@secure()
param administratorPassword string

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: skuTier
  }
  properties: {
    version: version
    storage: {
      storageSizeGB: storageSizeGB
    }
    highAvailability: {
      mode: haMode
    }
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Enabled' // Keep password auth for initial setup
    }
    administratorLogin: administratorLogin
    administratorLoginPassword: administratorPassword
  }
}

// Create the application database
resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: databaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// Allow Azure services to connect (for Container Apps)
resource firewallAllowAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgres
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

output id string = postgres.id
output name string = postgres.name
output fqdn string = postgres.properties.fullyQualifiedDomainName
output databaseName string = databaseName
