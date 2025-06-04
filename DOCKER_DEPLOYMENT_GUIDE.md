# FlowBit Docker Deployment Guide

🐳 **Complete containerization of the FlowBit Multi-Agent AI System**

## 📋 Prerequisites

1. **Docker & Docker Compose** installed
   ```bash
   # Check installation
   docker --version
   docker-compose --version
   ```

2. **Google Gemini API Key**
   - Get your API key from [Google AI Studio](https://makersuite.google.com/app/apikey)

## 🚀 Quick Start

### 1. Environment Setup

```bash
# Clone or navigate to project directory
cd project_flowbit

# Copy environment template
cp docker.env .env

# Edit .env with your API key
# Replace 'your_gemini_api_key_here' with your actual Gemini API key
```

### 2. Production Deployment

```bash
# Build and start all services
docker-compose up --build -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f flowbit-app
```

### 3. Development Mode

```bash
# Start in development mode with hot reload
docker-compose --profile dev up --build

# This will mount your code for live editing
```

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Network                      │
│                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │
│  │  FlowBit    │    │    Mock     │    │   SQLite    │ │
│  │     App     │◄──►│  Services   │    │    Web      │ │
│  │  (Port 8000)│    │(Ports 8001-4)│    │ (Port 8080) │ │
│  └─────────────┘    └─────────────┘    └─────────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## 📦 Service Details

| Service | Port | Purpose | Health Check |
|---------|------|---------|--------------|
| **flowbit-app** | 8000 | Main FastAPI application | `GET /` |
| **mockserver** | 8001-8004 | Mock external services | nginx status |
| **sqlite-web** | 8080 | Database viewer (optional) | Web interface |

## 🔧 Configuration

### Environment Variables (.env)

```bash
# Required
GOOGLE_API_KEY=your_actual_gemini_api_key

# Database (auto-configured for Docker)
DATABASE_URL=sqlite:///./data/flowbit.db

# External services (auto-configured)
CRM_ENDPOINT=http://mockserver:8001/crm
RISK_ALERT_ENDPOINT=http://mockserver:8002/risk
COMPLIANCE_ENDPOINT=http://mockserver:8003/compliance
NOTIFICATION_ENDPOINT=http://mockserver:8004/notify

# Application settings
DEBUG=false
LOG_LEVEL=INFO
MAX_UPLOAD_SIZE=10485760
```

## 🛠️ Available Commands

### Basic Operations

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# Restart specific service
docker-compose restart flowbit-app

# View logs
docker-compose logs -f [service-name]

# Shell access
docker-compose exec flowbit-app bash
```

### Development Commands

```bash
# Development mode with code reload
docker-compose --profile dev up

# Run tests inside container
docker-compose exec flowbit-app python -m pytest

# Database access
docker-compose --profile tools up sqlite-web
# Access at http://localhost:8080
```

### Maintenance Commands

```bash
# Rebuild services
docker-compose build --no-cache

# Clean up
docker-compose down -v  # Remove volumes too
docker system prune     # Clean Docker cache

# View resource usage
docker stats
```

## 🌐 Accessing Services

| Service | URL | Description |
|---------|-----|-------------|
| **FlowBit App** | http://localhost:8000 | Main application |
| **API Docs** | http://localhost:8000/docs | FastAPI documentation |
| **Mock Services** | http://localhost:8001-8004 | External service mocks |
| **Database Viewer** | http://localhost:8080 | SQLite database browser |

## 📊 Testing the Deployment

### 1. Health Check

```bash
# Check if services are running
curl http://localhost:8000/

# Check mock services
curl http://localhost:8001/crm
curl http://localhost:8002/risk
```

### 2. File Upload Test

```bash
# Upload a test file
curl -X POST \
  http://localhost:8000/process \
  -F "file=@test_samples/test_sample.json"

# Check processing status
curl http://localhost:8000/status/{process_id}
```

### 3. Web Interface Test

1. Open http://localhost:8000 in browser
2. Upload any JSON/Email/PDF file
3. Watch real-time processing results

## 🐛 Troubleshooting

### Common Issues

**Issue: Container won't start**
```bash
# Check logs for errors
docker-compose logs flowbit-app

# Common fixes:
# 1. Invalid API key in .env
# 2. Port conflicts
# 3. Permission issues
```

**Issue: Database errors**
```bash
# Reset database
docker-compose down -v
docker-compose up -d

# Check volume mounts
docker volume ls
docker volume inspect project_flowbit_flowbit-data
```

**Issue: API key errors**
```bash
# Verify environment variables
docker-compose exec flowbit-app env | grep GOOGLE_API_KEY

# Update .env file and restart
docker-compose restart flowbit-app
```

### Debugging Commands

```bash
# Container shell access
docker-compose exec flowbit-app bash

# Check Python environment
docker-compose exec flowbit-app pip list

# View container resources
docker stats

# Network inspection
docker network ls
docker network inspect project_flowbit_flowbit-network
```

## 🔒 Security Considerations

### Production Hardening

1. **Environment Variables**
   ```bash
   # Use Docker secrets for sensitive data
   echo "your_api_key" | docker secret create gemini_api_key -
   ```

2. **Network Security**
   ```yaml
   # Restrict external access in docker-compose.yml
   ports:
     - "127.0.0.1:8000:8000"  # Localhost only
   ```

3. **File Permissions**
   ```bash
   # Check container runs as non-root
   docker-compose exec flowbit-app whoami
   # Should return: flowbit
   ```

## 📈 Scaling & Production

### Horizontal Scaling

```yaml
# Add to docker-compose.yml
services:
  flowbit-app:
    deploy:
      replicas: 3
    environment:
      - WORKERS=4
```

### Load Balancer

```yaml
# Add nginx load balancer
nginx-lb:
  image: nginx:alpine
  ports:
    - "80:80"
  volumes:
    - ./nginx-lb.conf:/etc/nginx/nginx.conf
```

### Monitoring

```yaml
# Add monitoring stack
prometheus:
  image: prom/prometheus
  ports:
    - "9090:9090"

grafana:
  image: grafana/grafana
  ports:
    - "3000:3000"
```

## 🔄 CI/CD Integration

### GitHub Actions Example

```yaml
name: Deploy FlowBit
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Deploy with Docker Compose
        run: |
          docker-compose -f docker-compose.prod.yml up -d
        env:
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
```

## 📝 Backup & Recovery

### Database Backup

```bash
# Backup SQLite database
docker-compose exec flowbit-app cp /app/data/flowbit.db /app/data/backup-$(date +%Y%m%d).db

# Extract backup from container
docker cp $(docker-compose ps -q flowbit-app):/app/data/backup-*.db ./
```

### Volume Backup

```bash
# Backup entire data volume
docker run --rm -v project_flowbit_flowbit-data:/source -v $(pwd):/backup alpine tar czf /backup/flowbit-data-backup.tar.gz -C /source .
```

## 🎯 Success Criteria

✅ **Deployment Successful When:**
- All containers start without errors
- Health checks pass for all services
- Web interface accessible at localhost:8000
- File upload and processing works end-to-end
- Mock services respond correctly
- Database persists data across restarts

🚀 **Your FlowBit system is now fully containerized and production-ready!** 