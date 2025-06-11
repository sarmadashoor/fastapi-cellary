#!/bin/sh
set -euo pipefail

# Security-hardened startup script for Redis
echo "🔒 Starting security-hardened Redis server..."

# Security: Set umask for file creation
umask 0027

# Security: Validate environment variables
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
if [ -z "$REDIS_PASSWORD" ]; then
    echo "❌ ERROR: REDIS_PASSWORD environment variable is required"
    exit 1
fi

if [ ${#REDIS_PASSWORD} -lt 20 ]; then
    echo "❌ ERROR: REDIS_PASSWORD must be at least 20 characters for security"
    exit 1
fi

# Security: Set Redis authentication
echo "🔐 Configuring Redis authentication..."
echo "requirepass $REDIS_PASSWORD" >> /usr/local/etc/redis/redis.conf

# Security: Configure ACL passwords
sed -i "s/app_redis_password/${REDIS_APP_PASSWORD:-$REDIS_PASSWORD}/g" /usr/local/etc/redis/users.acl
sed -i "s/celery_redis_password/${REDIS_CELERY_PASSWORD:-$REDIS_PASSWORD}/g" /usr/local/etc/redis/users.acl  
sed -i "s/monitor_redis_password/${REDIS_MONITOR_PASSWORD:-$REDIS_PASSWORD}/g" /usr/local/etc/redis/users.acl

# Security: Set file permissions
chmod 600 /usr/local/etc/redis/redis.conf
chmod 600 /usr/local/etc/redis/users.acl
chown redis-app:redis-app /usr/local/etc/redis/redis.conf /usr/local/etc/redis/users.acl

# Security: Create PID file with correct permissions
touch /var/run/redis.pid
chown redis-app:redis-app /var/run/redis.pid
chmod 644 /var/run/redis.pid

# Security: Set process limits
ulimit -n 65535  # Max open files
ulimit -u 256    # Max user processes

echo "🚀 Starting Redis server with hardened configuration..."
echo "📊 Redis settings:"
echo "   - Authentication: enabled"
echo "   - Protected mode: enabled" 
echo "   - Dangerous commands: disabled"
echo "   - ACL: enabled"
echo "   - Max memory: 256MB"
echo "   - Max clients: 128"

# Security: Start Redis with non-root user
exec su-exec redis-app redis-server /usr/local/etc/redis/redis.conf \
    --pidfile /var/run/redis.pid \
    --daemonize no