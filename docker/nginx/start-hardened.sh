#!/bin/sh
set -euo pipefail

# Security-hardened startup script for nginx
echo "🔒 Starting security-hardened nginx..."

# Security: Set umask for file creation
umask 0027

# Security: Validate nginx configuration
echo "🔍 Validating nginx configuration..."
nginx -t

# Security: Set file permissions
chmod 644 /etc/nginx/nginx.conf /etc/nginx/conf.d/*.conf
chown root:root /etc/nginx/nginx.conf /etc/nginx/conf.d/*.conf

# Security: Create error page
cat > /usr/share/nginx/html/error.html << 'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Service Unavailable</title>
    <style>
        body { 
            font-family: Arial, sans-serif; 
            text-align: center; 
            padding: 50px; 
            background: #f5f5f5; 
        }
        .error { 
            background: white; 
            padding: 30px; 
            border-radius: 10px; 
            display: inline-block; 
            box-shadow: 0 2px 10px rgba(0,0,0,0.1); 
        }
    </style>
</head>
<body>
    <div class="error">
        <h1>Service Temporarily Unavailable</h1>
        <p>Please try again later.</p>
    </div>
</body>
</html>
EOF

chown nginx-app:nginx-app /usr/share/nginx/html/error.html
chmod 644 /usr/share/nginx/html/error.html

# Security: Test backend connectivity
echo "🔗 Testing backend connectivity..."
timeout 10 sh -c 'until nc -z backend 8000; do sleep 1; done' || {
    echo "⚠️  Warning: Backend not immediately available"
}

# Security: Set process limits
ulimit -n 8192   # Max open files
ulimit -u 256    # Max user processes

echo "🚀 Starting nginx with hardened configuration..."
echo "📊 nginx settings:"
echo "   - Server tokens: hidden"
echo "   - Rate limiting: enabled"
echo "   - Security headers: enabled"
echo "   - Connection limits: enabled"
echo "   - File upload limit: 5MB"

# Security: Start nginx with proper signal handling
exec nginx -g "daemon off;"