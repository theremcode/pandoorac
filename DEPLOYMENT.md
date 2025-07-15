# Pandoorac Deployment Guide

Simple deployment for Pandoorac on Azure AKS.

## Prerequisites

- `kubectl` installed and configured
- `helm` installed
- Access to Azure AKS cluster

## Quick Start

### 1. Deploy to Azure AKS

```bash
# Deploy the application
./deploy.sh deploy

# Check status
./deploy.sh status

# Clean up (if needed)
./deploy.sh cleanup
```

### 2. Update Application Image

To deploy your actual application:

1. Build and push your image:
   ```bash
   docker build -t your-registry/pandoorac:latest .
   docker push your-registry/pandoorac:latest
   ```

2. Update `helm/pandoorac/values.yaml`:
   ```yaml
   app:
     image: your-registry/pandoorac:latest
     port: 5001  # Your app port
   ```

3. Redeploy:
   ```bash
   ./deploy.sh deploy
   ```

## Storage Configuration

- **PostgreSQL**: Uses `azure-disk` (managed-premium) for reliable database storage
- **Redis**: Uses `azure-disk` (managed-premium) for cache storage  
- **MinIO**: Uses `azure-storage` (Azure Files) for object storage

## Services

- **App**: Port 80 (or your app port)
- **PostgreSQL**: Port 5432
- **Redis**: Port 6379
- **MinIO**: Port 9000 (API), 9001 (Console)

## Troubleshooting

```bash
# Check pod logs
kubectl logs -n pandoorac-prod <pod-name>

# Check events
kubectl get events -n pandoorac-prod

# Check storage
kubectl get pvc -n pandoorac-prod
```

## Local Development

For local development (OrbStack, Docker Desktop, etc.), use the same Helm chart but with different storage classes in `values.yaml`:

```yaml
postgresql:
  storageClass: standard  # or your local storage class
redis:
  storageClass: standard  # or your local storage class
minio:
  storageClass: standard  # or your local storage class
``` 