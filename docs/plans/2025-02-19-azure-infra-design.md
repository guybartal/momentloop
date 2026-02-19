# Azure Infrastructure Design for MomentLoop

## Summary

Deploy MomentLoop to Azure using Bicep infrastructure-as-code with azd (Azure Developer CLI). All resource SKUs are parameterized for cost control. The app supports dual-mode operation: local development (unchanged) and Azure production.

## Architecture

```
                    +-------------------------------------+
                    |     Azure Container Apps Env         |
                    |  +-------------+ +---------------+  |
  Users ----------> |  |  Frontend   | |   Backend     |  |
  (HTTPS)           |  |  (React)    | |  (FastAPI)    |  |
                    |  |  nginx      | |  + WebSocket  |  |
                    |  +-------------+ +-------+-------+  |
                    +-------------------------- | ---------+
                                                |
                    +---------------------------|---------+
                    |                           v         |
                    |  +----------+  +-----------------+  |
                    |  |Key Vault |  |  PostgreSQL     |  |
                    |  |(Secrets) |  |  Flexible Server|  |
                    |  +----------+  +-----------------+  |
                    |                                      |
                    |  +----------+  +-----------------+  |
                    |  |  ACR     |  |  Blob Storage   |  |
                    |  |(Images)  |  |  (Media Files)  |  |
                    |  +----------+  +-----------------+  |
                    |                                      |
                    |  +------------------------------+    |
                    |  |  Log Analytics Workspace     |    |
                    |  +------------------------------+    |
                    +--------------------------------------+
```

## Decisions

### Compute: Azure Container Apps (Consumption)
- Serverless, pay-per-use, scales to zero when idle.
- Built-in HTTPS ingress and WebSocket support.
- Two separate container apps: frontend (nginx) and backend (FastAPI/uvicorn).

### Database: Azure Database for PostgreSQL Flexible Server
- Managed PostgreSQL with burstable B-series SKUs.
- Microsoft Entra authentication (Managed Identity) — no passwords.
- Default SKU: B1ms (1 vCore, 2 GiB RAM, ~$13/mo).

### File Storage: Azure Blob Storage
- Five containers: `uploads`, `styled`, `videos`, `exports`, `thumbnails`.
- Standard LRS (locally redundant), Hot tier.
- Backend serves files to frontend via proxy endpoint `/api/storage/{path}`.

### Secrets: Azure Key Vault
- Stores only external API keys (Google OAuth, Gemini, fal.ai, JWT secret).
- All Azure-to-Azure connections use Managed Identity instead.

### Container Registry: Azure Container Registry (Basic)
- Stores Docker images built by GitHub Actions.
- Backend pulls images via Managed Identity (AcrPull role).

### Monitoring: Log Analytics Workspace
- Container Apps logs and metrics.
- Pay-as-you-go (~$2.76/GB ingested).

### CI/CD: GitHub Actions
- Build Docker images on push to main.
- Push to ACR, deploy via `azd deploy`.

## Dual-Mode Operation

The app supports two storage backends, controlled by `STORAGE_BACKEND` environment variable:

### Local mode (default — current behavior, zero changes)
- `STORAGE_BACKEND=local`
- Files stored on local disk at `./storage/`.
- PostgreSQL via Docker Compose.
- Secrets in `.env` file.
- FastAPI `StaticFiles` serves media at `/storage/`.

### Azure mode
- `STORAGE_BACKEND=azure`
- Files stored in Azure Blob Storage.
- Managed PostgreSQL with Entra authentication.
- Secrets from Azure Key Vault via Managed Identity.
- Backend proxy route `/api/storage/{path}` streams from Blob Storage.
- FFmpeg operations: download blobs to `/tmp/`, process locally, upload result.

### What changes in backend code

| File | Change |
|------|--------|
| `app/core/config.py` | Add `STORAGE_BACKEND` setting, Azure Blob connection settings |
| `app/services/storage.py` | Add `AzureBlobStorageBackend` alongside existing local logic |
| `app/api/routes/storage_proxy.py` | New: `/api/storage/{path}` proxy for Azure mode |
| `app/main.py` | Conditionally mount StaticFiles (local) or proxy route (Azure) |
| `pyproject.toml` | Add `azure-storage-blob`, `azure-identity` as optional deps |

### What does NOT change
- Database models and schemas (paths remain relative).
- All API routes (they use StorageService abstraction).
- Frontend code (URLs come from API responses).
- Docker Compose setup.
- Tests.

## Managed Identity Strategy

Every Azure resource-to-resource connection uses System-Assigned Managed Identity. No passwords or connection strings with keys.

| Connection | RBAC Role |
|------------|-----------|
| Backend -> PostgreSQL | Entra auth (azure_pg_admin) |
| Backend -> Blob Storage | Storage Blob Data Contributor |
| Backend -> Key Vault | Key Vault Secrets User |
| Backend -> ACR | AcrPull |

### Key Vault contents (external API secrets only)

| Secret | Purpose |
|--------|---------|
| `google-client-id` | Google OAuth |
| `google-client-secret` | Google OAuth |
| `google-ai-api-key` | Gemini API for style transfer |
| `fal-key` | fal.ai for video generation |
| `jwt-secret` | JWT token signing |

## Configurable SKUs

All SKUs parameterized in `main.bicepparam` for cost control:

### Default values (minimum cost, ~$35-40/mo)

```
PostgreSQL:          B1ms (1 vCore, 2 GiB), 32 GB storage, HA disabled
Backend App:         0.25 vCPU, 0.5 GiB, 0-3 replicas (scales to zero)
Frontend App:        0.25 vCPU, 0.5 GiB, 0-2 replicas (scales to zero)
Storage Account:     Standard_LRS
Container Registry:  Basic
```

### Scaling up

```
PostgreSQL:          Standard_D2s_v3 (2 vCPU, 8 GiB), ZoneRedundant HA
Backend App:         1.0 vCPU, 2.0 GiB, 1-10 replicas
Frontend App:        0.5 vCPU, 1.0 GiB, 1-5 replicas
Storage Account:     Standard_GRS (geo-redundant)
Container Registry:  Standard or Premium
```

## File Structure

```
infra/
  main.bicep                       # Orchestrator
  main.bicepparam                  # All configurable parameters
  abbreviations.json               # Azure naming conventions
  modules/
    container-apps-env.bicep       # Environment + Log Analytics
    container-app-backend.bicep    # Backend container app
    container-app-frontend.bicep   # Frontend container app
    postgresql.bicep               # PostgreSQL Flexible Server + DB
    storage.bicep                  # Storage Account + blob containers
    key-vault.bicep                # Key Vault + secret references
    container-registry.bicep       # ACR
    monitoring.bicep               # Log Analytics Workspace
azure.yaml                        # azd manifest (project root)
```

## Estimated Monthly Cost (minimum SKUs)

| Resource | Est. Cost |
|----------|-----------|
| PostgreSQL Flexible Server (B1ms) | ~$13 |
| Backend Container App (idle most of time) | ~$0-15 |
| Frontend Container App (idle most of time) | ~$0-5 |
| Container Registry (Basic) | ~$5 |
| Storage Account (< 1 GB) | ~$0.02 |
| Key Vault | ~$0.03 |
| Log Analytics (light usage) | ~$1-3 |
| **Total** | **~$35-40** |
