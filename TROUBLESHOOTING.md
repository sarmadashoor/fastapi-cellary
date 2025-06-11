# Troubleshooting Guide

This guide helps resolve common issues encountered during development of the FastAPI + Celery application.

## 🚨 Quick Fixes

### Reset Everything
If you're experiencing persistent issues, try a complete reset:

```bash
# Nuclear option - resets everything
make clean-all
make setup
```

### Check Service Status
```bash
# Quick health check
make health

# Detailed status
make status
docker ps
```

## 🐳 Docker Issues

### Docker Permission Denied (Linux)

**Problem**: `permission denied while trying to connect to the Docker daemon socket`

**Solution**:
```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Apply group changes
newgrp docker

# Or restart your terminal/shell
```

### Port Already in Use

**Problem**: `port is already allocated` or `address already in use`

**Solution**:
```bash
# Find process using port 8000
lsof -i :8000
lsof -i :5432

# Kill specific process
kill -9 <PID>

# Or stop all services first
make stop
# Wait a few seconds, then restart
make start
```

### Container Build Failures

**Problem**: Docker build fails with dependency errors

**Solution**:
```bash
# Clean build without cache
make build-clean

# If still failing, check Docker space
docker system df
make clean  # Free up space

# Update Docker if very old version
docker --version
```

### Container Won't Start

**Problem**: Container exits immediately or won't start

**Solutions**:
```bash
# Check container logs
make logs-recent
docker logs <container-name>

# Common fixes:
1. Check .env file exists and has correct format
2. Verify database is ready before app starts
3. Check for syntax errors in code

# Start services one by one to isolate issue
docker-compose up postgres -d
docker-compose up redis -d
docker-compose up backend -d
```

## 🗄️ Database Issues

### Database Connection Failed

**Problem**: `could not connect to server` or `connection refused`

**Solutions**:
```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Wait for database to be ready
docker exec postgres pg_isready -U postgres

# Check database logs
docker logs postgres

# Reset database if corrupted
make db-reset  # WARNING: Destroys data
```

### Migration Errors

**Problem**: `alembic.util.exc.CommandError` or migration conflicts

**Solutions**:
```bash
# Check migration history
./alembic.sh history

# Check current version
./alembic.sh current

# Force migration to head (dangerous)
./alembic.sh stamp head
./alembic.sh upgrade head

# If completely broken, reset migrations:
make db-reset
./alembic.sh upgrade head
```

### Database Permission Errors

**Problem**: `permission denied for database` or `role does not exist`

**Solutions**:
```bash
# Connect as postgres user
docker exec -it postgres psql -U postgres

# Check users and permissions
\du
\l

# Create user if missing
CREATE USER postgres WITH SUPERUSER PASSWORD 'postgres';

# Grant permissions
GRANT ALL PRIVILEGES ON DATABASE fastapi_celery TO postgres;
```

### Can't Connect to Database from Host

**Problem**: Local tools can't connect to containerized PostgreSQL

**Solutions**:
```bash
# Add to /etc/hosts (Linux/macOS)
echo "127.0.0.1 postgres" | sudo tee -a /etc/hosts

# Use localhost instead of postgres
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/fastapi_celery

# Check port forwarding
docker ps | grep postgres  # Should show 5432->5432
```

## 🔄 Celery Issues

### Celery Worker Not Starting

**Problem**: Worker exits or doesn't process tasks

**Solutions**:
```bash
# Check worker logs
docker logs celeryworker -f

# Common issues:
1. Redis connection failed
2. Python import errors
3. Module not found

# Restart worker
docker restart celeryworker

# Test Redis connection
docker exec redis redis-cli ping
```

### Tasks Not Processing

**Problem**: Tasks stay in PENDING state

**Solutions**:
```bash
# Check if worker is running
docker ps | grep celery

# Check task queue in Redis
docker exec redis redis-cli LLEN celery

# Check for task routing issues
# In worker logs, look for:
# - Task registration messages
# - Routing errors
# - Import failures

# Clear task queue if stuck
docker exec redis redis-cli FLUSHDB
```

### Worker Memory Issues

**Problem**: Worker killed by OOM or consuming too much memory

**Solutions**:
```bash
# Check memory usage
docker stats

# Reduce tasks per child (in celery_app.py)
worker_max_tasks_per_child=10  # Lower value

# Increase memory limit in docker-compose.yml
mem_limit: 1g  # Increase if needed

# Monitor memory in worker
docker exec celeryworker ps aux
```

## 🌐 API Issues

### API Not Responding

**Problem**: `curl: (7) Failed to connect` or timeout errors

**Solutions**:
```bash
# Check if backend container is running
docker ps | grep backend

# Check backend logs
docker logs backend -f

# Common causes:
1. Python syntax errors
2. Import failures
3. Port conflicts
4. FastAPI not binding to 0.0.0.0

# Test inside container
docker exec backend curl http://localhost:8000/health
```

### 500 Internal Server Error

**Problem**: API returns 500 errors

**Solutions**:
```bash
# Check backend logs for stack traces
docker logs backend --tail=100

# Common causes:
1. Database connection issues
2. Missing environment variables
3. Unhandled exceptions
4. Import errors

# Enable debug mode temporarily
# In .env:
DEBUG=true
LOG_LEVEL=DEBUG

# Restart to apply changes
make restart
```

### CORS Errors

**Problem**: Browser blocks requests with CORS errors

**Solutions**:
```bash
# Check CORS configuration in main.py
# Should include your frontend URL

# For development, temporarily allow all origins:
# In main.py:
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Only for development!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Authentication Issues

**Problem**: 401 Unauthorized or JWT token issues

**Solutions**:
```bash
# Test token generation
curl -X POST "http://localhost:8000/api/auth/token" \
     -H "Content-Type: application/json" \
     -d '{"login": "admin", "password": "admin"}'

# Check JWT secret is set
echo $JWT_SECRET  # Should be 32+ characters

# Check token in JWT debugger: https://jwt.io
# Look for exp (expiration) claim

# Reset admin password
# In .env:
ADMIN_PASSWORD=admin  # Will be hashed automatically
```

## 🔍 Testing Issues

### Tests Failing

**Problem**: Test suite fails with various errors

**Solutions**:
```bash
# Run tests with verbose output
./test.sh -v

# Run specific failing test
./test.sh tests/path/to/test.py::test_function -v

# Common issues:
1. Database not ready
2. Missing test data
3. Port conflicts
4. Async test issues

# Reset test environment
make stop
make start
sleep 10  # Wait for services
./test.sh
```

### Pytest Import Errors

**Problem**: `ModuleNotFoundError` during test runs

**Solutions**:
```bash
# Check Python path
cd backend
python -c "import sys; print(sys.path)"

# Ensure you're in the right directory
cd backend  # Tests should run from here
python -m pytest tests/

# Check conftest.py is present
ls tests/conftest.py

# Virtual environment activated
source ../activate.sh
```

### Test Database Issues

**Problem**: Tests can't connect to test database

**Solutions**:
```bash
# For local testing, ensure postgres in /etc/hosts
grep postgres /etc/hosts

# Or use localhost for tests
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/fastapi_celery

# Check if test database exists
./psql.sh -c "\l" | grep fastapi_celery
```

## 📊 Performance Issues

### Slow API Response

**Problem**: API endpoints taking too long to respond

**Solutions**:
```bash
# Check database query performance
# Enable query logging in PostgreSQL

# Monitor database connections
./psql.sh -c "SELECT count(*) FROM pg_stat_activity;"

# Check for slow queries
./psql.sh -c "SELECT query, mean_time FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"

# Monitor container resources
docker stats

# Profile specific endpoints
time curl http://localhost:8000/api/health
```

### High Memory Usage

**Problem**: Containers consuming too much memory

**Solutions**:
```bash
# Check memory usage
docker stats --no-stream

# Identify memory leaks
# In backend logs, look for:
# - Connection pool exhaustion
# - Unclosed database sessions
# - Large object creation

# Reduce connection pool size
# In config.py:
db_pool_size = 5  # Reduce if needed

# Monitor garbage collection
# Add to Python code temporarily:
import gc
print(f"Objects: {len(gc.get_objects())}")
```

## 🔐 Security Issues

### File Upload Failing

**Problem**: File uploads return validation errors

**Solutions**:
```bash
# Check file size limit (default 5MB)
# In .env:
MAX_UPLOAD_SIZE_MB=10  # Increase if needed

# Check allowed file types
# Should be PDF or DOCX only

# Test with curl
curl -X POST "http://localhost:8000/api/resumes/upload" \
     -H "Authorization: Bearer $TOKEN" \
     -F "file=@test.pdf"

# Check upload directory permissions
ls -la backend/uploads/
```

### Rate Limiting Issues

**Problem**: Requests blocked by rate limiter

**Solutions**:
```bash
# Disable rate limiting temporarily
# In .env:
RATE_LIMITING_ENABLED=false

# Or increase limits
RATE_LIMIT_GLOBAL=10000

# Clear rate limit data
docker exec redis redis-cli FLUSHDB

# Check rate limit logs
docker logs backend | grep "rate.limit"
```

## 🧰 Development Environment Issues

### Virtual Environment Problems

**Problem**: Package import errors or wrong Python version

**Solutions**:
```bash
# Recreate virtual environment
rm -rf .venv
source activate.sh

# Check Python version
python --version  # Should be 3.10+

# Check installed packages
pip list | grep fastapi
pip list | grep celery

# Reinstall dependencies
pip install -r requirements/requirements.dev.in
```

### IDE Configuration Issues

**Problem**: IDE not recognizing imports or showing errors

**Solutions**:
```bash
# For VS Code, ensure Python interpreter is set to .venv
# Cmd/Ctrl + Shift + P -> "Python: Select Interpreter"
# Choose: ./venv/bin/python

# For PyCharm, set project interpreter to .venv

# Generate .env for IDE
cp .env.hardened.example .env

# Check if .venv is in Python path
echo $PYTHONPATH
```

### Git Hooks Failing

**Problem**: Pre-commit hooks fail or don't run

**Solutions**:
```bash
# Install pre-commit hooks
pre-commit install

# Update hooks
pre-commit autoupdate

# Skip hooks temporarily (for urgent commits)
git commit --no-verify -m "message"

# Run hooks manually
pre-commit run --all-files
```

## 🔧 Advanced Debugging

### Enable Debug Logging

```bash
# In .env:
LOG_LEVEL=DEBUG
DEBUG=true

# Restart services
make restart

# Follow logs
make logs
```

### Database Query Debugging

```bash
# Enable query logging in PostgreSQL
docker exec postgres psql -U postgres -c "ALTER SYSTEM SET log_statement = 'all';"
docker exec postgres psql -U postgres -c "SELECT pg_reload_conf();"

# Watch query logs
docker logs postgres -f | grep STATEMENT
```

### Network Debugging

```bash
# Check container networking
docker network ls
docker network inspect fastapi-celery_default

# Test connectivity between containers
docker exec backend ping postgres
docker exec backend ping redis

# Check port bindings
docker port backend
docker port postgres
```

### Memory Profiling

```bash
# Install memory profiler in container
docker exec backend pip install memory-profiler

# Add to Python code:
@profile
def your_function():
    pass

# Run with profiler
python -m memory_profiler your_script.py
```

## 📞 Getting Help

### Information to Gather

When seeking help, provide:

```bash
# System information
make env

# Service status
make status

# Recent logs
make logs-recent

# Error details
# Copy exact error messages and stack traces

# Configuration
cat .env | grep -v PASSWORD  # Hide sensitive values
```

### Common Log Locations

```bash
# Application logs
docker logs backend
docker logs celeryworker

# Database logs
docker logs postgres

# Redis logs
docker logs redis

# Nginx logs (if using)
docker logs nginx
```

### Debugging Commands Cheat Sheet

```bash
# Quick diagnostics
make health
make status
make logs-recent

# Service-specific debugging
docker exec backend python -c "from app.config import get_config; print(get_config().db_uri)"
docker exec postgres pg_isready -U postgres
docker exec redis redis-cli ping

# Network debugging
docker exec backend nslookup postgres
docker exec backend telnet postgres 5432

# File system debugging
docker exec backend ls -la /app
docker exec backend df -h
```

Remember: When in doubt, try the "reset everything" approach first, then gradually narrow down the issue!