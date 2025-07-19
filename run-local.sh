#!/bin/bash

set -e

# Handle command line arguments
RESET_DATA=false
if [ "$1" = "--reset" ] || [ "$1" = "-r" ]; then
    RESET_DATA=true
    echo "[INFO] Reset flag detected - will generate new secrets and clear persistent data"
fi

# Check if we have persistent data and should reuse secrets
SECRET_FILE=".env.local"
if [ -f "$SECRET_FILE" ] && [ "$RESET_DATA" = false ]; then
    echo "[INFO] Found existing local secrets file, reusing secrets..."
    source "$SECRET_FILE"
    echo "[INFO] Using existing secrets for persistent data compatibility"
else
    if [ "$RESET_DATA" = true ]; then
        echo "[INFO] Resetting - removing existing secrets and data..."
        rm -f "$SECRET_FILE"
        docker-compose down -v  # Remove volumes to clear persistent data
    fi
    
    echo "[INFO] No existing secrets found, generating new random secrets..."
    # Generate random secrets for local development
    RANDOM_DB_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
    RANDOM_MINIO_SECRET=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
    RANDOM_SECRET_KEY=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
    
    # Save secrets to file for future use
    cat > "$SECRET_FILE" << EOF
# Local development secrets - generated $(date)
RANDOM_DB_PASSWORD=$RANDOM_DB_PASSWORD
RANDOM_MINIO_SECRET=$RANDOM_MINIO_SECRET
RANDOM_SECRET_KEY=$RANDOM_SECRET_KEY
EOF
    echo "[INFO] Saved secrets to $SECRET_FILE for future use"
fi

echo "[INFO] Using secrets for local development"
echo "[INFO] Database password: $RANDOM_DB_PASSWORD"
echo "[INFO] MinIO secret: $RANDOM_MINIO_SECRET"
echo "[INFO] Flask secret key: $RANDOM_SECRET_KEY"

# Export environment variables for docker-compose
export RANDOM_DB_PASSWORD
export RANDOM_MINIO_SECRET
export RANDOM_SECRET_KEY

# Build and start docker-compose services
echo "[INFO] Stopping existing containers..."
docker-compose down

echo "[INFO] Building and starting local services with docker-compose..."
docker-compose build app
docker-compose up -d

echo "[INFO] Waiting for services to be ready..."
sleep 5

# Set environment variables for local development (using the same secrets from above)
export FLASK_APP=app.py
export FLASK_ENV=development
export STORAGE_TYPE=minio
export DATABASE_URL=postgresql://pandoorac:$RANDOM_DB_PASSWORD@localhost:5432/pandoorac
export REDIS_URL=redis://localhost:6379/0
export MINIO_ENDPOINT=http://localhost:9000
export MINIO_ACCESS_KEY=minioadmin
export MINIO_SECRET_KEY=$RANDOM_MINIO_SECRET
export MINIO_BUCKET=pandoorac-local
export SECRET_KEY=$RANDOM_SECRET_KEY

# Optionally create the MinIO bucket if mc CLI is available
echo "[INFO] Checking for MinIO bucket..."
if command -v mc &> /dev/null; then
  mc alias set localminio http://localhost:9000 minioadmin $RANDOM_MINIO_SECRET
  if ! mc ls localminio/$MINIO_BUCKET &> /dev/null; then
    echo "[INFO] Creating MinIO bucket: $MINIO_BUCKET"
    mc mb localminio/$MINIO_BUCKET
  else
    echo "[INFO] MinIO bucket $MINIO_BUCKET already exists."
  fi
else
  echo "[WARN] MinIO Client (mc) not found. Please create the bucket '$MINIO_BUCKET' manually if needed."
fi

echo "[INFO] All services are running!"
echo "[INFO] Flask app is available at: http://localhost:5001"
echo "[INFO] MinIO Console is available at: http://localhost:9001"
echo "[INFO] PostgreSQL is available at: localhost:5432"
echo "[INFO] Redis is available at: localhost:6379"
echo ""
echo "[INFO] Secrets are stored in .env.local for persistent data compatibility"
echo "[INFO] To reset all data and generate new secrets, run: $0 --reset"
echo ""
echo "[INFO] To view app logs, run: docker-compose logs -f app"
echo "[INFO] To stop all services, run: docker-compose down"
echo ""
echo "[INFO] Following app logs (Ctrl+C to stop following logs, services will continue running):"
docker-compose logs -f app 