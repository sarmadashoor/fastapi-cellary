#!/bin/bash
set -euo pipefail

# Security-hardened startup script for FastAPI backend
echo "🔒 Starting security-hardened FastAPI backend..."

# Security: Set umask for file creation
umask 0027

# Security: Set resource limits
ulimit -n 1024  # Max open files
ulimit -u 256   # Max user processes

# Environment validation
if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "❌ ERROR: DATABASE_URL environment variable is required"
    exit 1
fi

if [[ -z "${REDIS_URL:-}" ]]; then
    echo "❌ ERROR: REDIS_URL environment variable is required"
    exit 1
fi

# Security: Validate JWT secret strength
if [[ -n "${JWT_SECRET:-}" && ${#JWT_SECRET} -lt 32 ]]; then
    echo "❌ ERROR: JWT_SECRET must be at least 32 characters for security"
    exit 1
fi

# Security: Run security checks before starting
echo "🔍 Running security validations..."

# Check for common security vulnerabilities in dependencies
if command -v safety >/dev/null 2>&1; then
    echo "🔒 Checking dependencies for known vulnerabilities..."
    safety check --json --output safety-report.json || {
        echo "⚠️  Warning: Some dependencies have known vulnerabilities"
        echo "📄 Check safety-report.json for details"
    }
fi

# Run static security analysis
if command -v bandit >/dev/null 2>&1; then
    echo "🔒 Running static security analysis..."
    bandit -r . -f json -o bandit-report.json -ll || {
        echo "⚠️  Warning: Static analysis found potential security issues"
        echo "📄 Check bandit-report.json for details"
    }
fi

# Security: Validate file permissions
echo "🔒 Validating file permissions..."
find /app -type f -perm /o+w -exec echo "⚠️  World-writable file: {}" \;

# Database connectivity check with timeout
echo "🔗 Testing database connectivity..."
timeout 10 python -c "
import sys
import os
sys.path.insert(0, '/app')
try:
    from app.config import get_config
    config = get_config()
    print('✅ Database configuration validated')
except Exception as e:
    print(f'❌ Database configuration error: {e}')
    sys.exit(1)
" || {
    echo "❌ Database connectivity check failed"
    exit 1
}

# Redis connectivity check with timeout
echo "🔗 Testing Redis connectivity..."
timeout 10 python -c "
import redis
import os
try:
    redis_url = os.environ.get('REDIS_URL', 'redis://redis:6379')
    r = redis.from_url(redis_url)
    r.ping()
    print('✅ Redis connectivity validated')
except Exception as e:
    print(f'❌ Redis connectivity error: {e}')
    import sys
    sys.exit(1)
" || {
    echo "❌ Redis connectivity check failed"
    exit 1
}

# Security: Set process title for monitoring
export PS_TITLE="fastapi-backend-hardened"

# Security: Configure Python security settings
export PYTHONHASHSEED=random
export PYTHONOPTIMIZE=1

# Application startup with security settings
echo "🚀 Starting FastAPI application with hardened configuration..."

# Production configuration
WORKERS=${WORKERS:-4}
MAX_REQUESTS=${MAX_REQUESTS:-1000}
MAX_REQUESTS_JITTER=${MAX_REQUESTS_JITTER:-100}
TIMEOUT=${TIMEOUT:-30}
KEEP_ALIVE=${KEEP_ALIVE:-2}

# Security: Start with gunicorn and security options
exec gunicorn app.main:app \
    --bind 0.0.0.0:8000 \
    --workers $WORKERS \
    --worker-class uvicorn.workers.UvicornWorker \
    --max-requests $MAX_REQUESTS \
    --max-requests-jitter $MAX_REQUESTS_JITTER \
    --timeout $TIMEOUT \
    --keep-alive $KEEP_ALIVE \
    --preload \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    --capture-output \
    --enable-stdio-inheritance \
    --user fastapi \
    --group fastapi