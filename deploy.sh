#!/bin/bash
set -e

IMAGE_NAME="vertex-final:v2"
CONTAINER_NAME="vertex-proxy"

echo "[INFO] Starting deployment..."

# 1. Update Code
echo "[INFO] Pulling latest code..."
git pull origin main

# 2. Build Image
echo "[INFO] Building Docker image (${IMAGE_NAME})..."
docker build -t "${IMAGE_NAME}" .

# 3. Stop Old Container
echo "[INFO] Stopping old container..."
docker stop "${CONTAINER_NAME}" || true
docker rm "${CONTAINER_NAME}" || true

# 4. Ensure runtime directories exist
mkdir -p "$(pwd)/json"
mkdir -p "$(pwd)/data"

# 5. Start New Container
echo "[INFO] Starting new container..."
if [ -f .env ]; then
  docker run -d \
  --name "${CONTAINER_NAME}" \
  -p 8000:8000 \
  --restart unless-stopped \
  --env-file .env \
  -v "$(pwd)/json:/app/json" \
  -v "$(pwd)/data:/app/data" \
  "${IMAGE_NAME}"
else
  docker run -d \
  --name "${CONTAINER_NAME}" \
  -p 8000:8000 \
  --restart unless-stopped \
  -v "$(pwd)/json:/app/json" \
  -v "$(pwd)/data:/app/data" \
  "${IMAGE_NAME}"
fi

echo "[INFO] Deployment complete. Recent logs:"
docker logs --tail 50 "${CONTAINER_NAME}" || true
