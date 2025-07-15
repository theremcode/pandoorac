#!/bin/bash

set -e

# Start docker-compose services
echo "[INFO] Starting local services with docker-compose..."
docker-compose up -d

echo "[INFO] Waiting for services to be ready..."
sleep 5

# Set environment variables for local development
export FLASK_APP=app.py
export FLASK_ENV=development
export DATABASE_URL=postgresql://pandoorac:change-me@localhost:5432/pandoorac
export REDIS_URL=redis://localhost:6379/0
export MINIO_ENDPOINT=http://localhost:9000
export MINIO_ACCESS_KEY=minioadmin
export MINIO_SECRET_KEY=change-me
export MINIO_BUCKET=pandoorac-local
export SECRET_KEY=dev-secret-key

# Optionally create the MinIO bucket if mc CLI is available
echo "[INFO] Checking for MinIO bucket..."
if command -v mc &> /dev/null; then
  mc alias set localminio http://localhost:9000 minioadmin change-me
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
echo "[INFO] To view app logs, run: docker-compose logs -f app"
echo "[INFO] To stop all services, run: docker-compose down"
echo ""
echo "[INFO] Following app logs (Ctrl+C to stop following logs, services will continue running):"
docker-compose logs -f app 