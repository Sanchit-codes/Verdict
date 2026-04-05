# GuardlyAI Deployment Guide

## System Requirements

**Python:** >= 3.10
**CPU:** Recommended 4+ cores (heuristics and embedding run on CPU)
**Memory:** Minimum 4GB, recommended 8GB (models cached in memory)
**Disk:** Minimum 1GB for model cache (~500MB HHEM, ~100MB embedding)

---

## Environment Variables

### Required

```bash
GUARDLY_API_KEYS="key1,key2,key3"  # Comma-separated API keys for authentication
```

### Optional

```bash
GUARDLY_PORT=5000                  # Port to listen on (default: 5000)
GUARDLY_HOST=0.0.0.0               # Host to bind to (default: 0.0.0.0)
GUARDLY_WORKERS=4                  # Gunicorn workers (default: 4)
GUARDLY_THREADS=2                  # Threads per worker (default: 2)
GUARDLY_TIMEOUT=120                # Request timeout in seconds (default: 120)

HG_LOG_LEVEL=INFO                  # Logging level: DEBUG, INFO, WARNING, ERROR (default: WARNING)
HG_TRACE_DIR=~/.hallucination_guard/traces/  # Directory for JSON trace logs
HG_MODEL_CACHE=~/.cache/huggingface/         # HuggingFace model cache directory
HG_DEFAULT_POLICY=default          # Default policy if not specified in request
HG_DISABLE_HHEM=false              # Disable HHEM for faster inference (heuristics + embedding only)

GOOGLE_API_KEY=                    # Optional, for integrating with Gemini (if using GuardedGemini)
LANGFUSE_PUBLIC_KEY=               # Optional, for trace export to Langfuse dashboard
LANGFUSE_SECRET_KEY=
```

---

## Installation

### 1. Create Virtual Environment

```bash
python3.10 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
# Production (minimal)
pip install -e .

# Development with all extras
pip install -e ".[gemini,langchain,observability,dev]"

# Or specific extras
pip install -e ".[gemini]"           # Gemini integration
pip install -e ".[langchain]"        # LangChain integration
pip install -e ".[observability]"    # Langfuse tracing
```

### 3. Verify Installation

```bash
python3 -c "from hallucination_guard import Guard; print('✓ Guard imported successfully')"
python3 -c "from frontend.app import app; print('✓ Flask app imported successfully')"
```

---

## Local Development

### Run Flask Development Server

```bash
export GUARDLY_API_KEYS="dev-key-123"
python3 examples/flask_api_server.py
```

Access at: `http://localhost:5000`

### Test with curl

```bash
# Health check (no auth)
curl http://localhost:5000/health

# Validate (with auth)
curl -X POST http://localhost:5000/validate \
  -H "Authorization: Bearer dev-key-123" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"test","output":"test"}'
```

---

## Production Deployment

### 1. Using Gunicorn + Nginx

**Install Gunicorn:**
```bash
pip install gunicorn
```

**Run with Gunicorn:**
```bash
export GUARDLY_API_KEYS="prod-key-1,prod-key-2"
gunicorn \
  --workers 4 \
  --threads 2 \
  --bind 0.0.0.0:5000 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile - \
  --log-level info \
  "frontend.app:app"
```

**Nginx configuration:**
```nginx
upstream guardly_backend {
    server localhost:5000;
    server localhost:5001;
    server localhost:5002;
    server localhost:5003;
}

server {
    listen 80;
    server_name api.guardly.ai;

    # Health check endpoint
    location /health {
        proxy_pass http://guardly_backend;
        access_log off;
    }

    # All other endpoints
    location / {
        proxy_pass http://guardly_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Request timeout: 150ms for single request + 300ms buffer
        proxy_read_timeout 150s;
        proxy_connect_timeout 10s;
    }
}
```

### 2. Using Docker

**Create Dockerfile:**
```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Copy dependencies
COPY pyproject.toml .
COPY hallucination_guard/ hallucination_guard/
COPY frontend/ frontend/
COPY examples/ examples/

# Install
RUN pip install -e .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s \
  CMD curl -f http://localhost:5000/health || exit 1

# Run
ENV PYTHONUNBUFFERED=1
EXPOSE 5000
CMD ["gunicorn", \
  "--workers", "4", \
  "--threads", "2", \
  "--bind", "0.0.0.0:5000", \
  "--timeout", "120", \
  "--access-logfile", "-", \
  "--error-logfile", "-", \
  "frontend.app:app"]
```

**Build and run:**
```bash
docker build -t guardly-ai:latest .

docker run \
  --env GUARDLY_API_KEYS="key1,key2" \
  --env HG_LOG_LEVEL=INFO \
  --publish 5000:5000 \
  --memory 4g \
  guardly-ai:latest
```

### 3. Using Kubernetes

**Deployment manifest:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: guardly-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: guardly-api
  template:
    metadata:
      labels:
        app: guardly-api
    spec:
      containers:
      - name: api
        image: guardly-ai:latest
        ports:
        - containerPort: 5000
        
        env:
        - name: GUARDLY_API_KEYS
          valueFrom:
            secretKeyRef:
              name: guardly-secrets
              key: api-keys
        - name: GUARDLY_WORKERS
          value: "4"
        - name: GUARDLY_THREADS
          value: "2"
        - name: HG_LOG_LEVEL
          value: "INFO"
        
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        
        livenessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 60
          periodSeconds: 30
          timeoutSeconds: 10
        
        readinessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5

---
apiVersion: v1
kind: Service
metadata:
  name: guardly-api-service
spec:
  selector:
    app: guardly-api
  ports:
  - port: 80
    targetPort: 5000
  type: LoadBalancer
```

**Deploy:**
```bash
kubectl apply -f guardly-deployment.yaml
kubectl apply -f guardly-secrets.yaml
```

---

## Performance Tuning

### Model Preloading

Reduce cold-start latency by preloading models on server startup:

```python
from hallucination_guard import Guard

# This loads models on startup (~6-8 seconds)
# All subsequent requests hit the cache
guard = Guard(policy="default")
```

Alternatively, use the provided Flask server which preloads models:

```bash
python3 examples/flask_api_server.py  # Auto-preloads on startup
```

### Worker Configuration

```bash
# For CPU-only workloads:
gunicorn --workers 4 --threads 2 ...
# workers = 2 × CPU_CORES (e.g., 8 cores = 4-6 workers)
# threads = 2-4 per worker

# For memory-constrained environments:
gunicorn --workers 2 --threads 1 ...
# Reduces memory overhead, slightly slower concurrency

# For high-throughput requirements:
gunicorn --workers 8 --threads 4 ...
# Requires 8GB+ RAM and 4+ CPU cores
```

### Batch Processing

For bulk validation, use the batch endpoint with sequential mode on memory-constrained systems:

```bash
curl -X POST http://localhost:5000/validate/batch \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "sequential",  # Memory-efficient
    "items": [...]
  }'
```

### Latency Budget

If your application requires latency < 50ms, use the chatbot policy which disables HHEM:

```python
guard = Guard(policy="chatbot")  # Only heuristics + embedding, ~30ms
```

---

## Monitoring & Logging

### Structured Logging

Set `HG_LOG_LEVEL=DEBUG` for verbose logs:

```bash
export HG_LOG_LEVEL=DEBUG
python3 examples/flask_api_server.py
```

**Log output:**
```
DEBUG hallucination_guard.core.guard: Guard initialized with policy 'default'
DEBUG hallucination_guard.core.pipeline: Loaded validator: heuristics
DEBUG hallucination_guard.core.pipeline: Tier 1 score: 0.88, passed=True
INFO hallucination_guard.validators.embedding: Loading embedding model
INFO hallucination_guard.validators.hhem: HHEM model loaded successfully
```

### Health Check Monitoring

Query health endpoint periodically in production:

```bash
# Every 30 seconds
while true; do
  curl -s http://localhost:5000/health | jq '.status'
  sleep 30
done
```

### Langfuse Integration (Optional)

Export traces to Langfuse dashboard for monitoring:

```bash
export LANGFUSE_PUBLIC_KEY="pk-..."
export LANGFUSE_SECRET_KEY="sk-..."
python3 examples/flask_api_server.py

# Traces appear in Langfuse dashboard at https://cloud.langfuse.com
```

---

## Troubleshooting

### Cold Start (First Request Takes 6-8 Seconds)

**Expected behavior** - Models download and cache on first request.

**Solution:** Use model preloading:
```python
# examples/flask_api_server.py already does this
guard = Guard(policy="default")  # Pre-loads on startup
```

### HHEM Model Download Fails

**Check:**
```bash
# Verify HuggingFace cache
ls ~/.cache/huggingface/hub/models--vectara*

# Pre-download model
python3 -c "from transformers import AutoModelForSequenceClassification; \
  AutoModelForSequenceClassification.from_pretrained('vectara/hallucination_evaluation_model')"
```

### Out of Memory (OOM)

**Symptoms:** Process killed, validation fails with 503

**Solutions:**
1. Reduce workers: `--workers 2 --threads 1`
2. Disable HHEM: `export HG_DISABLE_HHEM=true`
3. Increase system memory or use sequential batch mode
4. Set memory limit in Docker: `--memory 4g`

### High Latency (p95 > 150ms)

**Check validator status:**
```bash
curl http://localhost:5000/health | jq '.validators'
```

**Solutions:**
1. Increase Gunicorn workers
2. Use chatbot policy (heuristics + embedding only)
3. Check system CPU/memory usage
4. Add more machines behind load balancer

### Validation Returns 503 Service Unavailable

**Cause:** Model loading timeout or initialization failure

**Solutions:**
1. Check logs: `tail -f gunicorn.log`
2. Pre-load models: Use the Flask server example with preloading
3. Increase timeout: `export GUARDLY_TIMEOUT=180`
4. Verify models downloaded: `ls ~/.cache/huggingface/`

---

## Backup & Disaster Recovery

### Model Cache Backup

Models are cached in `~/.cache/huggingface/`. Back this up:

```bash
# Backup
tar -czf huggingface_cache.tar.gz ~/.cache/huggingface/

# Restore
tar -xzf huggingface_cache.tar.gz -C ~
```

### Policy Configuration Backup

Policies are in `hallucination_guard/policies/`. Version control them:

```bash
git add hallucination_guard/policies/
git commit -m "backup: save policies"
```

---

## Security

### API Key Management

1. Generate strong random keys:
```bash
openssl rand -hex 32
```

2. Rotate keys regularly:
```bash
# Update GUARDLY_API_KEYS env var
export GUARDLY_API_KEYS="new_key_1,new_key_2"
# Restart service
```

3. Use secrets management in production:
```bash
# Kubernetes
kubectl create secret generic guardly-secrets \
  --from-literal=api-keys="key1,key2,key3"

# Docker Swarm
echo "key1,key2,key3" | docker secret create guardly_api_keys -
```

### HTTPS

Use Nginx or cloud load balancer for SSL/TLS:

```nginx
server {
    listen 443 ssl http2;
    ssl_certificate /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;
    
    location / {
        proxy_pass http://guardly_backend;
    }
}
```

### Input Validation

All requests validated against schema (done automatically by Flask/Pydantic). No SQL injection or injection attacks possible.

---

## Support

- Check logs: `tail -f deployment.log`
- Run health check: `curl http://localhost:5000/health`
- Test with curl: `curl -X POST http://localhost:5000/validate ...`
- See [REST_API.md](REST_API.md) for endpoint details
