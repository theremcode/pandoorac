# Pandoorac

A modern web application for managing appraisals and dossiers, built with Flask and fully containerized for Kubernetes deployment—supporting both local development and production environments.

---

## Table of Contents
1. [Quick Start](#quick-start)
2. [Architecture](#architecture)
3. [Requirements](#requirements)
4. [Local Development](#local-development)
5. [Production Deployment](#production-deployment)
6. [Configuration](#configuration)
7. [Storage](#storage)
8. [Networking](#networking)
9. [Security](#security)
10. [Monitoring & Logging](#monitoring--logging)
11. [Troubleshooting](#troubleshooting)
12. [License](#license)

---

## Quick Start

### Local Development

```bash
# Clone the repository
git clone <repository-url>
cd pandoorac

# Start minikube or OrbStack
minikube start
# OR
orb start

# Deploy to development environment
./deploy.sh development deploy
```

The application will be available via Kubernetes ingress or port-forward.

### Production Deployment

```bash
# Deploy to Kubernetes (interactive menu)
./deploy.sh

# OR direct command line
./deploy.sh production deploy
```

---

## Architecture

- **Flask Web Application** – Main app
- **PostgreSQL Database** – Persistent data storage
- **Redis** – Caching and session storage
- **MinIO** – Object storage
- **Kubernetes** – Orchestration (minikube/OrbStack for local, AKS for production)
- **Helm Charts** – Deployment management
- **NGINX Ingress Controller** – External access (production)

---

## Requirements

### Local Development
- minikube or OrbStack
- kubectl
- helm
- docker (for image building)
- python3 (for configuration merging)

### Production Deployment
- Kubernetes 1.19+ (for Ingress v1)
- Helm 3.0+
- Python 3.6+
- NGINX Ingress Controller
- StorageClass supporting `ReadWriteOnce`
- (For Azure AKS: access to AKS cluster, Azure CLI configured)

---

## Local Development

### Installation

1. **Start your local Kubernetes cluster:**
   ```bash
   minikube start
   # OR
   orb start
   ```
2. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd pandoorac
   ```
3. **Deploy to development environment:**
   ```bash
   ./deploy.sh development deploy
   ```
4. **The app is now available via Kubernetes ingress or port-forward.**

### Development Commands

```bash
# Deploy to development
./deploy.sh development deploy

# Check status
./deploy.sh development check

# View logs
./deploy.sh development debug

# Cleanup environment
./deploy.sh development cleanup
```

### Project Structure

```
pandoorac/
├── app.py              # Main application
├── requirements.txt    # Python dependencies
├── Dockerfile          # Web container config
├── deploy.sh           # Deployment script
├── helm/               # Helm charts for Kubernetes
├── config.yaml         # Environment-specific config
└── templates/          # HTML templates
```

---

## Production Deployment

### Prerequisites
- `kubectl` installed and configured
- `helm` installed
- Access to your Kubernetes cluster (e.g., Azure AKS)

### Quick Start (Azure AKS Example)

```bash
# Deploy the application
./deploy.sh deploy

# Check status
./deploy.sh status

# Clean up (if needed)
./deploy.sh cleanup
```

### Update Application Image

1. Build and push your image:
   ```bash
   docker build -t your-registry/pandoorac:latest .
   docker push your-registry/pandoorac:latest
   ```
2. Update `helm/pandoorac/values.yaml`:
   ```yaml
   app:
     image: your-registry/pandoorac:latest
     port: 5001
   ```
3. Redeploy:
   ```bash
   ./deploy.sh deploy
   ```

### Storage Configuration (Azure Example)
- **PostgreSQL**: Uses `azure-disk` (managed-premium)
- **Redis**: Uses `azure-disk` (managed-premium)
- **MinIO**: Uses `azure-storage` (Azure Files)

For local development, use the same Helm chart but with different storage classes in `values.yaml`:
```yaml
postgresql:
  storageClass: standard
redis:
  storageClass: standard
minio:
  storageClass: standard
```

---

## Configuration

### Environment Configuration

Environment-specific settings are defined in `config.yaml`:

```yaml
development:
  app:
    image:
      tag: "dev"
    replicaCount: 1
    config:
      secretKey: "dev-secret-key"
      environment: "development"
  database:
    postgresql:
      auth:
        password: "dev-password"
production:
  app:
    replicaCount: 3
    config:
      secretKey: "production-secret-key"
      environment: "production"
  database:
    postgresql:
      auth:
        password: "production-password"
```

Base Helm values are in `helm/pandoorac/values.yaml` and are merged with environment-specific overrides during deployment.

---

## Storage

### Persistent Volumes
- **PostgreSQL**: 10Gi (default)
- **Redis**: 5Gi (default)
- **MinIO**: 20Gi (default)
- **Local Storage**: 10Gi (if used)

### Storage Classes
Configure the appropriate StorageClass for your cluster:
```yaml
storage_class: "standard"  # or "fast", "ssd", etc.
```

---

## Networking

### Ingress
The application uses the NGINX Ingress Controller:
```yaml
ingress:
  enabled: true
  className: "nginx"
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
```

### Services
All services are available internally via ClusterIP:
- `pandoorac:5001` – Web application
- `pandoorac-postgresql:5432` – Database
- `pandoorac-redis:6379` – Redis
- `pandoorac-minio:9000` – MinIO API
- `pandoorac-minio:9001` – MinIO Console

---

## Security

### Secrets Management
Sensitive data is stored in Kubernetes Secrets:
- `SECRET_KEY` – Flask secret key
- `BAG_API_KEY` – BAG API key
- `WOZ_API_KEY` – WOZ API key
- `database_password` – Database password

### Network Policies
Network policies are available but disabled by default. Enable for extra security:
```yaml
networkPolicy:
  enabled: true
```

### Pod Security
- Non-root user (UID 1000)
- Read-only root filesystem
- Dropped capabilities
- Non-privileged containers

---

## Monitoring & Logging

### Health Checks
- `/health` – General health check
- Database connectivity check
- Redis connectivity check

### Metrics
Prometheus metrics can be enabled:
```yaml
monitoring:
  enabled: true
  prometheus:
    enabled: true
```

### Logs
Use deployment scripts or `kubectl logs` to view logs for the app, database, Redis, and MinIO.

---

## Troubleshooting

### Common Issues
- **Pods not starting:**
  ```bash
  ./deploy.sh <environment> check
  kubectl describe pod <pod-name> -n pandoorac
  kubectl logs <pod-name> -n pandoorac
  ```
- **Database connection issues:**
  ```bash
  kubectl exec -it deployment/pandoorac-postgresql -n pandoorac -- psql -U pandoorac -d pandoorac
  ```
- **Deployment issues:**
  ```bash
  ./deploy.sh <environment> debug
  ```
- **Storage issues:**
  ```bash
  kubectl get pvc -n pandoorac
  kubectl describe pvc <pvc-name> -n pandoorac
  ```
- **Ingress issues:**
  ```bash
  kubectl get ingress -n pandoorac
  kubectl describe ingress pandoorac -n pandoorac
  ```

### Manual Cleanup
If the cleanup script fails, you can manually clean up:
```bash
# Uninstall Helm release
helm uninstall pandoorac -n pandoorac

# Delete namespace
kubectl delete namespace pandoorac

# Remove generated files
rm -f deployment/pandoorac/values-*.yaml
```

---

## License

This project is licensed under the MIT License. 