FROM python:3.10-slim

WORKDIR /app

# 1. Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Copy code
COPY . .

# 3. Create secrets directory (for mounting key)
RUN mkdir -p /app/secrets

# 4. Default Environment Variables (Overridden by ECS)
ENV PORT=8000
ENV GOOGLE_APPLICATION_CREDENTIALS="/app/secrets/gcp-key.json"

# 5. Start
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
