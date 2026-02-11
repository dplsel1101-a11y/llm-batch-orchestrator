#!/bin/bash
set -e

echo "🚀 Starting Deployment..."

# 1. Update Code
echo "📥 Pulling latest code..."
git pull origin main

# 2. Build Image
echo "📦 Building Docker Image (vertex-final:v2)..."
docker build -t vertex-final:v2 .

# 3. Stop Old Container
echo "🛑 Stopping old container..."
docker stop vertex-proxy || true
docker rm vertex-proxy || true

# 4. Start New Container
echo "▶️ Starting new container..."
# Mount local_jobs.db to persist data
docker run -d \
  --name vertex-proxy \
  -p 8000:8000 \
  --restart unless-stopped \
  -v $(pwd)/local_jobs.db:/app/local_jobs.db \
  vertex-final:v2

echo "✅ Deployment Complete! Access Admin Panel at http://<YOUR-IP>:8000/admin"
