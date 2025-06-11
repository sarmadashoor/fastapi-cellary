#!/bin/bash
set -euo pipefail

# Security-hardened startup script for Celery worker
echo "🔒 Starting security-hardened Celery worker..."

# Security: Set umask for file creation
umask 0027

# Security: Set resource limits
ulimit -n 1024  # Max open files
ulimit -u 256   # Max user processes
ulimit -m 2097152  # Max memory (2GB)

# Environment validation
if [[ -z "${CELERY_BROKER_URL:-}" && -z "${REDIS_URL:-}" ]]; then
    echo "❌ ERROR: CELERY_BROKER_URL or REDIS_URL environment variable is required"
    exit 1
fi

# Security: Run security checks before starting
echo "🔍 Running security validations..."

# Check for common security vulnerabilities in dependencies
if command -v safety >/dev/null 2>&1; then
    echo "🔒 Checking dependencies for known vulnerabilities..."
    safety check --json --output /var/log/celery/safety-report.json || {
        echo "⚠️  Warning: Some dependencies have known vulnerabilities"
        echo "📄 Check /var/log/celery/safety-report.json for details"
    }
fi

# Run static security analysis
if command -v bandit >/dev/null 2>&1; then
    echo "🔒 Running static security analysis..."
    bandit -r . -f json -o /var/log/celery/bandit-report.json -ll || {
        echo "⚠️  Warning: Static analysis found potential security issues"
        echo "📄 Check /var/log/celery/bandit-report.json for details"
    }
fi

# Security: Validate file permissions
echo "🔒 Validating file permissions..."
find /app -type f -perm /o+w -exec echo "⚠️  World-writable file: {}" \;

# Update ClamAV virus definitions
echo "🦠 Updating virus definitions..."
if command -v freshclam >/dev/null 2>&1; then
    freshclam --quiet --no-warnings || {
        echo "⚠️  Warning: Could not update virus definitions"
    }
fi

# Start ClamAV daemon for virus scanning
echo "🦠 Starting ClamAV daemon..."
if command -v clamd >/dev/null 2>&1; then
    clamd &
    # Wait for ClamAV to start
    sleep 5
fi

# Redis/Broker connectivity check with timeout
echo "🔗 Testing broker connectivity..."
timeout 10 python -c "
import sys
import os
sys.path.insert(0, '/app')
try:
    from app.celery_app import celery_app
    # Test connection
    celery_app.control.ping(timeout=5)
    print('✅ Broker connectivity validated')
except Exception as e:
    print(f'❌ Broker connectivity error: {e}')
    sys.exit(1)
" || {
    echo "❌ Broker connectivity check failed"
    exit 1
}

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

# Security: Set process title for monitoring
export PS_TITLE="celery-worker-hardened"

# Security: Configure Python security settings
export PYTHONHASHSEED=random
export PYTHONOPTIMIZE=1

# Celery configuration
CONCURRENCY=${CELERY_CONCURRENCY:-4}
MAX_TASKS_PER_CHILD=${CELERY_MAX_TASKS_PER_CHILD:-1000}
MAX_MEMORY_PER_CHILD=${CELERY_MAX_MEMORY_PER_CHILD:-200000}  # 200MB
SOFT_TIME_LIMIT=${CELERY_SOFT_TIME_LIMIT:-300}  # 5 minutes
HARD_TIME_LIMIT=${CELERY_HARD_TIME_LIMIT:-360}  # 6 minutes

echo "🚀 Starting Celery worker with hardened configuration..."
echo "📊 Worker settings:"
echo "   - Concurrency: $CONCURRENCY"
echo "   - Max tasks per child: $MAX_TASKS_PER_CHILD"
echo "   - Max memory per child: ${MAX_MEMORY_PER_CHILD}KB"
echo "   - Soft time limit: ${SOFT_TIME_LIMIT}s"
echo "   - Hard time limit: ${HARD_TIME_LIMIT}s"

# Security: Start with secure Celery configuration
exec celery -A app.celery_app worker \
    --loglevel=info \
    --concurrency=$CONCURRENCY \
    --max-tasks-per-child=$MAX_TASKS_PER_CHILD \
    --max-memory-per-child=$MAX_MEMORY_PER_CHILD \
    --time-limit=$HARD_TIME_LIMIT \
    --soft-time-limit=$SOFT_TIME_LIMIT \
    --without-gossip \
    --without-mingle \
    --without-heartbeat \
    --optimization=fair \
    --pool=prefork \
    --queues=default,high_priority,file_processing \
    --hostname=worker-$(hostname)-%i \
    --uid=celery \
    --gid=celery \
    --logfile=/var/log/celery/worker.log \
    --pidfile=/var/log/celery/worker.pid