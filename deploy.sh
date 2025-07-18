#!/bin/bash

# Simple deployment script for Pandoorac on Azure AKS
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
RELEASE_NAME="pandoorac-prod"
NAMESPACE="pandoorac-prod"
CHART_PATH="helm/pandoorac"
ACR_REGISTRY="acrtheremcode.azurecr.io"
IMAGE_NAME="pandoorac"
IMAGE_TAG="latest"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed"
        exit 1
    fi
    
    if ! command -v helm &> /dev/null; then
        log_error "helm is not installed"
        exit 1
    fi
    
    if ! command -v docker &> /dev/null; then
        log_error "docker is not installed"
        exit 1
    fi
    
    # Check if Docker Buildx is available
    if ! docker buildx version &> /dev/null; then
        log_error "Docker Buildx is not available. Please enable Docker Buildx for multi-architecture builds."
        exit 1
    fi
    
    # Check if we're connected to a cluster
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Not connected to a Kubernetes cluster"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Show cluster info
show_cluster_info() {
    log_info "Current Kubernetes context:"
    kubectl config current-context
    kubectl cluster-info | head -1
    echo
}

# Build and push Docker image
build_and_push_image() {
    log_info "Building and pushing Docker image to ACR..."
    
    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running"
        exit 1
    fi
    
    # Check if Docker Buildx is available
    if ! docker buildx version &> /dev/null; then
        log_error "Docker Buildx is not available. Please enable Docker Buildx."
        exit 1
    fi
    
    # Create and use a new builder instance for multi-platform builds
    log_info "Setting up Docker Buildx for multi-architecture builds..."
    docker buildx create --name pandoorac-builder --use --bootstrap 2>/dev/null || true
    
    # Build multi-architecture image
    FULL_IMAGE_NAME="$ACR_REGISTRY/$IMAGE_NAME:$IMAGE_TAG"
    log_info "Building multi-architecture Docker image: $FULL_IMAGE_NAME"
    log_info "Target platforms: linux/amd64, linux/arm64"
    
    docker buildx build \
        --platform linux/amd64,linux/arm64 \
        --tag "$FULL_IMAGE_NAME" \
        --push \
        --file Dockerfile \
        .
    
    if [ $? -ne 0 ]; then
        log_error "Docker multi-architecture build failed"
        exit 1
    fi
    
    log_success "Multi-architecture image built and pushed successfully: $FULL_IMAGE_NAME"
    
    # Update values.yaml with the ACR image
    log_info "Updating Helm values with ACR image..."
    sed -i.bak "s|image: .*|image: $FULL_IMAGE_NAME|" "$CHART_PATH/values.yaml"
    
    log_success "Helm values updated"
}

# Deploy function
deploy() {
    log_info "Deploying Pandoorac to Azure AKS..."
    
    # Check if namespace exists and has existing secrets
    if kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
        log_info "Namespace $NAMESPACE exists, checking for existing secrets..."
        
        # Try to get existing secrets from the Kubernetes cluster
        if kubectl get secret "$RELEASE_NAME-postgresql-secret" -n "$NAMESPACE" >/dev/null 2>&1; then
            log_info "Found existing PostgreSQL secret, extracting password..."
            RANDOM_DB_PASSWORD=$(kubectl get secret "$RELEASE_NAME-postgresql-secret" -n "$NAMESPACE" -o jsonpath='{.data.postgres-password}' | base64 -d)
        else
            log_info "No existing PostgreSQL secret found, generating new one..."
            RANDOM_DB_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
        fi
        
        if kubectl get secret "$RELEASE_NAME-minio-secret" -n "$NAMESPACE" >/dev/null 2>&1; then
            log_info "Found existing MinIO secret, extracting password..."
            RANDOM_MINIO_SECRET=$(kubectl get secret "$RELEASE_NAME-minio-secret" -n "$NAMESPACE" -o jsonpath='{.data.minio-secret-key}' | base64 -d)
        else
            log_info "No existing MinIO secret found, generating new one..."
            RANDOM_MINIO_SECRET=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
        fi
        
        if kubectl get secret "$RELEASE_NAME-app-secret" -n "$NAMESPACE" >/dev/null 2>&1; then
            log_info "Found existing app secret, extracting secret key..."
            RANDOM_SECRET_KEY=$(kubectl get secret "$RELEASE_NAME-app-secret" -n "$NAMESPACE" -o jsonpath='{.data.secret-key}' | base64 -d)
        else
            log_info "No existing app secret found, generating new one..."
            RANDOM_SECRET_KEY=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
        fi
        
        log_info "Using existing/compatible secrets for deployment"
    else
        log_info "Namespace $NAMESPACE does not exist, generating new secrets..."
        # Generate random secrets for production
        RANDOM_DB_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
        RANDOM_MINIO_SECRET=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
        RANDOM_SECRET_KEY=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
        log_info "Generated new secrets for production deployment"
    fi
    
    log_info "Database password: $RANDOM_DB_PASSWORD"
    log_info "MinIO secret: $RANDOM_MINIO_SECRET"
    log_info "Flask secret key: $RANDOM_SECRET_KEY"
    
    # Check if release exists
    if helm list -n "$NAMESPACE" | grep -q "^$RELEASE_NAME[[:space:]]"; then
        log_info "Release $RELEASE_NAME exists, upgrading..."
        helm upgrade "$RELEASE_NAME" "$CHART_PATH" \
            --namespace "$NAMESPACE" \
            --set postgresql.password="$RANDOM_DB_PASSWORD" \
            --set minio.secretKey="$RANDOM_MINIO_SECRET" \
            --set app.secretKey="$RANDOM_SECRET_KEY" \
            --wait \
            --timeout=10m
    else
        log_info "Installing new release $RELEASE_NAME..."
        helm install "$RELEASE_NAME" "$CHART_PATH" \
            --create-namespace \
            --namespace "$NAMESPACE" \
            --set postgresql.password="$RANDOM_DB_PASSWORD" \
            --set minio.secretKey="$RANDOM_MINIO_SECRET" \
            --set app.secretKey="$RANDOM_SECRET_KEY" \
            --wait \
            --timeout=10m
    fi
    
    log_success "Deployment completed"
}

# Check deployment status
check_status() {
    log_info "Checking deployment status..."
    
    echo
    echo "Pod status:"
    kubectl get pods -n "$NAMESPACE"
    
    echo
    echo "Services:"
    kubectl get svc -n "$NAMESPACE"
    
    echo
    echo "PVCs:"
    kubectl get pvc -n "$NAMESPACE"
    
    echo
    echo "Storage classes:"
    kubectl get pvc -n "$NAMESPACE" -o custom-columns=NAME:.metadata.name,STORAGECLASS:.spec.storageClassName
    
    echo
    echo "CronJobs:"
    kubectl get cronjob -n "$NAMESPACE"
    
    echo
    echo "Ingress:"
    kubectl get ingress -n "$NAMESPACE"
}

# Create manual backup
create_backup() {
    log_info "Creating manual PostgreSQL backup..."
    
    # Get the current database password from the secret
    DB_PASSWORD=$(kubectl get secret "$RELEASE_NAME-postgresql" -n "$NAMESPACE" -o jsonpath='{.data.postgres-password}' | base64 -d 2>/dev/null || echo "pandoorac123")
    
    # Create a temporary backup job
    cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: ${RELEASE_NAME}-manual-backup-$(date +%s)
  namespace: $NAMESPACE
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: postgresql-backup
        image: postgres:14
        env:
        - name: PGPASSWORD
          value: "$DB_PASSWORD"
        - name: POSTGRES_USER
          value: pandoorac
        - name: POSTGRES_DB
          value: pandoorac
        command:
        - /bin/bash
        - -c
        - |
          set -e
          
          # Create backup directory with timestamp
          BACKUP_DIR="/backup/\$(date +%Y-%m-%d_%H-%M-%S)"
          mkdir -p "\$BACKUP_DIR"
          
          echo "Starting PostgreSQL backup at \$(date)"
          
          # PostgreSQL backup
          pg_dump -h ${RELEASE_NAME}-postgresql \
                  -p 5432 \
                  -U "\$POSTGRES_USER" \
                  -d "\$POSTGRES_DB" \
                  --verbose \
                  --format=custom \
                  --file="\$BACKUP_DIR/postgresql-backup.dump"
          
          # Create a compressed archive
          cd /backup
          tar -czf "\$BACKUP_DIR/postgresql-backup.tar.gz" "\$(basename "\$BACKUP_DIR")"
          
          echo "PostgreSQL backup completed at \$(date)"
          echo "Backup size: \$(du -h "\$BACKUP_DIR/postgresql-backup.tar.gz" | cut -f1)"
          
          # Clean up old backups (keep last 7 days)
          find /backup -name "*.tar.gz" -mtime +7 -delete
          
          echo "Backup cleanup completed"
        volumeMounts:
        - name: backup-storage
          mountPath: /backup
      volumes:
      - name: backup-storage
        persistentVolumeClaim:
          claimName: ${RELEASE_NAME}-backup-storage
EOF
    
    log_success "Manual backup job created"
    log_info "Check backup status with: kubectl get jobs -n $NAMESPACE"
}

# List backups
list_backups() {
    log_info "Listing available backups..."
    
    # Create a temporary pod to list backups
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: ${RELEASE_NAME}-list-backups-$(date +%s)
  namespace: $NAMESPACE
spec:
  containers:
  - name: list-backups
    image: alpine:latest
    command:
    - /bin/sh
    - -c
    - |
      echo "Available backups:"
      ls -la /backup/*.tar.gz 2>/dev/null || echo "No backups found"
      echo
      echo "Backup details:"
      for backup in /backup/*.tar.gz 2>/dev/null; do
        if [ -f "\$backup" ]; then
          echo "File: \$(basename \$backup)"
          echo "Size: \$(du -h \$backup | cut -f1)"
          echo "Date: \$(stat -c %y \$backup)"
          echo "---"
        fi
      done
    volumeMounts:
    - name: backup-storage
      mountPath: /backup
  volumes:
  - name: backup-storage
    persistentVolumeClaim:
      claimName: ${RELEASE_NAME}-backup-storage
  restartPolicy: Never
EOF
    
    # Wait for pod to complete
    sleep 5
    kubectl logs -n "$NAMESPACE" "${RELEASE_NAME}-list-backups-$(date +%s)" 2>/dev/null || true
    
    # Clean up
    kubectl delete pod -n "$NAMESPACE" "${RELEASE_NAME}-list-backups-$(date +%s)" --ignore-not-found=true
}

# Download backup
download_backup() {
    if [ -z "$1" ]; then
        log_error "Please specify a backup filename"
        echo "Usage: $0 download-backup <backup-filename>"
        echo "Use '$0 list-backups' to see available backups"
        exit 1
    fi
    
    BACKUP_FILE="$1"
    log_info "Downloading backup: $BACKUP_FILE"
    
    # Create a temporary pod to copy backup
    POD_NAME="${RELEASE_NAME}-download-backup-$(date +%s)"
    
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: $POD_NAME
  namespace: $NAMESPACE
spec:
  containers:
  - name: download-backup
    image: alpine:latest
    command:
    - /bin/sh
    - -c
    - |
      if [ -f "/backup/$BACKUP_FILE" ]; then
        echo "Backup file found, copying to /tmp for download..."
        cp "/backup/$BACKUP_FILE" "/tmp/$BACKUP_FILE"
        echo "Backup ready for download"
        sleep 3600  # Keep pod alive for 1 hour
      else
        echo "Backup file not found: /backup/$BACKUP_FILE"
        exit 1
      fi
    volumeMounts:
    - name: backup-storage
      mountPath: /backup
    - name: tmp-storage
      mountPath: /tmp
  volumes:
  - name: backup-storage
    persistentVolumeClaim:
      claimName: ${RELEASE_NAME}-backup-storage
  - name: tmp-storage
    emptyDir: {}
  restartPolicy: Never
EOF
    
    log_info "Waiting for pod to be ready..."
    kubectl wait --for=condition=ready pod/$POD_NAME -n "$NAMESPACE" --timeout=60s
    
    log_info "Downloading backup file..."
    kubectl cp "$NAMESPACE/$POD_NAME:/tmp/$BACKUP_FILE" "./$BACKUP_FILE"
    
    log_success "Backup downloaded to: ./$BACKUP_FILE"
    
    # Clean up
    kubectl delete pod $POD_NAME -n "$NAMESPACE" --ignore-not-found=true
}

# Cleanup function
cleanup() {
    log_warning "This will delete the entire deployment!"
    read -p "Are you sure? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Uninstalling Helm release..."
        helm uninstall "$RELEASE_NAME" -n "$NAMESPACE" --wait
        
        log_info "Deleting namespace..."
        kubectl delete namespace "$NAMESPACE" --wait
        
        log_success "Cleanup completed"
    else
        log_info "Cleanup cancelled"
    fi
}

# Main script
main() {
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║                    Pandoorac Deployment Script               ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo
    
    check_prerequisites
    show_cluster_info
    
    case "${1:-deploy}" in
        "deploy")
            build_and_push_image
            deploy
            check_status
            ;;
        "deploy-no-build")
            deploy
            check_status
            ;;
        "build")
            build_and_push_image
            ;;
        "status")
            check_status
            ;;
        "cleanup")
            cleanup
            ;;
        "backup")
            create_backup
            ;;
        "list-backups")
            list_backups
            ;;
        "download-backup")
            download_backup "$2"
            ;;
        "help"|"-h"|"--help")
            echo "Usage: $0 [deploy|deploy-no-build|build|status|cleanup|backup|list-backups|download-backup|help]"
            echo
            echo "Commands:"
            echo "  deploy           - Build, push to ACR, and deploy (default)"
            echo "  deploy-no-build  - Deploy without building/pushing image"
            echo "  build            - Build and push image to ACR only"
            echo "  status           - Check deployment status"
            echo "  cleanup          - Remove the deployment"
            echo "  backup           - Create manual PostgreSQL backup"
            echo "  list-backups     - List available backups"
            echo "  download-backup  - Download a backup file (requires filename)"
            echo "  help             - Show this help message"
            ;;
        *)
            log_error "Unknown command: $1"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

# Run main function
main "$@" 