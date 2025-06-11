# Development Guide

This guide provides comprehensive instructions for setting up, running, and testing the FastAPI + Celery resume parsing application locally.

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+** (recommended: 3.12)
- **Docker & Docker Compose** (v2.36.2+)
- **Git** for version control
- **UV** package manager (installed automatically)

### 1. Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd fastapi-celery

# Activate development environment (creates venv and installs dependencies)
source ./activate.sh
```

### 2. Start Development Environment

```bash
# Start all services (PostgreSQL, Redis, FastAPI, Celery)
./up.sh

# Verify services are running
./smoke_test.sh local
```

### 3. Verify Installation

```bash
# Run the test suite
./test.sh

# Check API documentation
open http://localhost:8000/docs
```

## 📋 Development Environment Details

### Core Services

| Service | Port | Description | Health Check |
|---------|------|-------------|--------------|
| **FastAPI** | 8000 | Main API server | `curl http://localhost:8000/health` |
| **PostgreSQL** | 5432 | Primary database | `./psql.sh` |
| **Redis** | 6379 | Message broker/cache | `docker exec -it redis redis-cli ping` |
| **Celery Worker** | - | Background task processor | `docker logs celeryworker` |
| **Nginx** | 8001 | Production proxy | `curl http://localhost:8001` |

### Environment Configuration

Create your local environment file:

```bash
cp .env.hardened.example .env
# Edit .env with your local settings
```

**Key Environment Variables:**
```bash
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/fastapi_celery
DB_POOL_SIZE=5

# Redis/Celery
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URI=redis://localhost:6379/1

# Security (Development)
JWT_SECRET=dev_secret_key_32_chars_minimum
ADMIN_PASSWORD=admin  # Will be hashed automatically

# Feature Flags
RATE_LIMITING_ENABLED=true
VIRUS_SCANNING_ENABLED=false  # Disable ClamAV in dev
STRUCTURED_LOGGING_ENABLED=true
```

## 🐳 Docker Development

### Available Scripts

#### Core Operations
```bash
./up.sh                # Start all services with logs
./up.sh backend        # Start only specific service
./stop.sh             # Stop all services
./build.sh            # Rebuild containers
./build.sh --no-cache # Force rebuild without cache
```

#### Database Operations
```bash
./psql.sh                    # Connect to PostgreSQL container
./local-psql.sh             # Connect from host (requires setup)
./alembic.sh upgrade head   # Run database migrations
./alembic.sh revision --autogenerate -m "Add feature"  # Create migration
```

#### Testing
```bash
./test.sh                   # Run tests locally (fastest)
./test_docker.sh           # Run tests in Docker
./smoke_test.sh local      # Quick API health check
./smoke_test.sh dev        # Test dev environment
```

#### Utilities
```bash
./exec.sh backend /bin/bash        # Open shell in container
./run.sh backend python manage.py  # Run one-off commands
./compose.sh logs -f               # Follow all container logs
```

### Service Dependencies

```mermaid
graph TD
    A[PostgreSQL] --> B[FastAPI]
    C[Redis] --> B
    C --> D[Celery Worker]
    B --> E[Nginx]
    F[ClamAV] -.-> D
```

## 🔧 Local Development Setup

### Option 1: Full Docker (Recommended)

All services run in containers with live code reloading:

```bash
# Start everything
./up.sh

# Code changes automatically reload FastAPI
# Celery worker needs restart for code changes:
docker restart celeryworker
```

### Option 2: Hybrid Development

Run some services locally for faster iteration:

```bash
# Start only infrastructure
docker-compose up postgres redis -d

# Add to /etc/hosts (Linux/macOS)
echo "127.0.0.1 postgres redis" | sudo tee -a /etc/hosts

# Run FastAPI locally
source ./activate.sh
cd backend
python -m uvicorn app.main:app --reload --port 8000

# Run Celery worker locally
cd backend
python -m celery -A app.celery_app.celery_app worker --loglevel=info
```

### Option 3: Local Database Setup

For development with local PostgreSQL:

```bash
# Install PostgreSQL locally
brew install postgresql  # macOS
sudo apt install postgresql postgresql-contrib  # Ubuntu

# Setup database
createdb fastapi_celery
psql fastapi_celery < docker/postgres/schema.sql

# Update .env
DATABASE_URL=postgresql://username:password@localhost:5432/fastapi_celery
```

## 🧪 Testing Guide

### Test Structure

```
backend/tests/
├── conftest.py              # Pytest configuration
├── fixtures/                # Reusable test fixtures
│   ├── client.py            # FastAPI test client
│   ├── db.py                # Database fixtures
│   └── celery.py            # Celery test setup
├── api/v1/                  # API endpoint tests
├── security/                # Security hardening tests
├── integration/             # Cross-service tests
└── performance/             # Load testing
```

### Running Tests

```bash
# All tests with coverage
./test.sh

# Specific test files
./test.sh tests/api/v1/test_resume_upload.py

# Test patterns
./test.sh -k "test_upload"

# Fast unit tests only
./test.sh -m "not slow"

# With verbose output
./test.sh -v

# Coverage report
./test.sh --cov --cov-report=html
open htmlcov/index.html
```

### Test Categories

- **Unit Tests**: Fast tests with mocked dependencies
- **Integration Tests**: Cross-service functionality
- **Security Tests**: Authentication, authorization, input validation
- **Performance Tests**: Load testing and benchmarks

### Writing Tests

```python
# Example test structure
import pytest
from fastapi.testclient import TestClient

def test_upload_resume(client: TestClient, auth_token: str):
    """Test resume upload with authentication."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    files = {"file": ("test.pdf", b"fake pdf content", "application/pdf")}
    
    response = client.post("/api/resumes/upload", 
                          files=files, headers=headers)
    
    assert response.status_code == 200
    assert "task_id" in response.json()
```

## 🔍 Debugging Guide

### Common Issues

#### 1. Database Connection Issues
```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Check connection from container
./exec.sh backend python -c "from app.config import get_config; print(get_config().db_uri)"

# Reset database
docker-compose down -v
./up.sh
```

#### 2. Celery Worker Not Processing Tasks
```bash
# Check Celery worker logs
docker logs celeryworker -f

# Check Redis connection
docker exec -it redis redis-cli ping

# Restart worker
docker restart celeryworker
```

#### 3. File Upload Issues
```bash
# Check file permissions
ls -la backend/uploads/

# Check ClamAV status (if enabled)
docker logs clamav
```

#### 4. Port Conflicts
```bash
# Find processes using ports
lsof -i :8000
lsof -i :5432

# Stop conflicting services
./stop.sh
```

### Development Tools

#### Database Inspection
```bash
# Connect to database
./psql.sh

# Useful queries
\dt                     # List tables
\d+ table_name         # Describe table
SELECT * FROM alembic_version;  # Check migration version
```

#### Redis Inspection
```bash
# Connect to Redis
docker exec -it redis redis-cli

# Useful commands
PING                   # Test connection
KEYS *                # List all keys
GET key_name          # Get value
FLUSHALL              # Clear all data (dev only!)
```

#### Log Analysis
```bash
# Follow all logs
docker-compose logs -f

# Specific service logs
docker logs backend -f
docker logs celeryworker -f

# Search logs
docker logs backend 2>&1 | grep ERROR
```

## 🔐 Security in Development

### Authentication Testing

```bash
# Get development token
curl -X POST "http://localhost:8000/api/auth/token" \
     -H "Content-Type: application/json" \
     -d '{"login": "admin", "password": "admin"}'

# Use token in requests
export TOKEN="your_jwt_token_here"
curl -H "Authorization: Bearer $TOKEN" \
     "http://localhost:8000/api/resumes/status/task_id"
```

### Security Features in Development

- **Rate Limiting**: Enabled but with relaxed limits
- **File Validation**: Active with size/type restrictions
- **Virus Scanning**: Disabled by default (ClamAV optional)
- **HTTPS**: Not required in development
- **JWT Validation**: Active with development secret

### Security Testing

```bash
# Run security test suite
./test.sh tests/security/

# Test file upload security
./test.sh tests/security/test_file_upload_hardening.py

# Test authentication
./test.sh tests/security/test_authentication_hardening.py
```

## 📊 Monitoring in Development

### Health Checks

```bash
# Application health
curl http://localhost:8000/health

# Detailed system info
curl http://localhost:8000/health/system

# Metrics endpoint
curl http://localhost:8000/metrics
```

### Performance Monitoring

```bash
# Stress test the API
cd backend && ./stress.sh

# Monitor resource usage
docker stats

# Profile database queries
# (Enable query logging in development)
```

## 🏗️ Code Quality

### Pre-commit Hooks

```bash
# Install pre-commit hooks
pre-commit install

# Run all hooks manually
pre-commit run --all-files

# Specific hooks
pre-commit run ruff
pre-commit run mypy
```

### Code Standards

- **Formatting**: `ruff` for code formatting
- **Linting**: `ruff` for code quality
- **Type Checking**: `mypy` for static analysis
- **Docstrings**: Google-style format
- **Testing**: `pytest` with fixtures

### Development Workflow

1. **Feature Development**:
   ```bash
   git checkout -b feature/new-feature
   # Develop with live reload
   ./up.sh
   # Write tests first (TDD)
   ./test.sh
   ```

2. **Code Quality**:
   ```bash
   # Format and lint
   pre-commit run --all-files
   
   # Type check
   mypy backend/app
   
   # Test coverage
   ./test.sh --cov
   ```

3. **Integration Testing**:
   ```bash
   # Full test suite
   ./test.sh
   
   # Security tests
   ./test.sh tests/security/
   
   # Smoke tests
   ./smoke_test.sh local
   ```

## 🚀 Production Deployment

### Building for Production

```bash
# Build production images
docker build -f docker/backend/Dockerfile.hardened -t app:latest .

# Run production compose
docker-compose -f docker-compose-hardened.yml up -d

# Verify deployment
./smoke_test.sh production
```

### Environment Differences

| Feature | Development | Production |
|---------|-------------|------------|
| **Debug Mode** | Enabled | Disabled |
| **SSL/HTTPS** | Optional | Required |
| **Rate Limiting** | Relaxed | Strict |
| **Virus Scanning** | Optional | Required |
| **Logging Level** | DEBUG | INFO |
| **Secret Management** | File-based | Vault/K8s |

## 🆘 Getting Help

### Documentation

- **API Docs**: `http://localhost:8000/docs` (Swagger UI)
- **Redoc**: `http://localhost:8000/redoc` (Alternative API docs)
- **Code Documentation**: Generated with `pydoc`

### Common Commands Reference

```bash
# Quick reference card
./activate.sh          # Setup environment
./up.sh                 # Start services
./test.sh               # Run tests
./smoke_test.sh local   # Health check
./psql.sh               # Database access
./stop.sh               # Stop everything
```

### Troubleshooting Checklist

1. ✅ **Environment**: `source ./activate.sh` completed
2. ✅ **Services**: `./up.sh` running without errors
3. ✅ **Database**: `./psql.sh` connects successfully
4. ✅ **API**: `curl http://localhost:8000/health` returns OK
5. ✅ **Tests**: `./test.sh` passes
6. ✅ **Dependencies**: No Docker permission issues

### Getting Support

1. **Check Logs**: `docker-compose logs -f`
2. **Run Diagnostics**: `./smoke_test.sh local`
3. **Reset Environment**: `./stop.sh && docker system prune -f && ./up.sh`
4. **Consult Documentation**: Review this guide and API docs

---

**Happy Coding! 🎉**

This development environment is designed for productivity and includes all tools needed for feature development, testing, and debugging the FastAPI + Celery resume processing application.