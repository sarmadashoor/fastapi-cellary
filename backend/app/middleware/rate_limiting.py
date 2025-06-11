"""
Rate limiting middleware for FastAPI applications.

This module provides simple in-memory rate limiting functionality
for protecting API endpoints from abuse.
"""

import logging
import time
from collections import defaultdict
from typing import Dict, Tuple

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)

# In-memory storage for rate limiting (use Redis in production)
request_counts: Dict[str, Dict[str, Tuple[int, float]]] = defaultdict(lambda: defaultdict(lambda: (0, 0.0)))

# Rate limit configurations per endpoint
RATE_LIMITS = {
    "/api/resumes/upload": {"requests": 10, "window": 300},  # 10 requests per 5 minutes
    "/api/resumes/status": {"requests": 60, "window": 60},   # 60 requests per minute
}

# Default rate limit for other endpoints
DEFAULT_RATE_LIMIT = {"requests": 100, "window": 60}  # 100 requests per minute


def get_client_ip(request: Request) -> str:
    """
    Extract client IP address from request.
    
    Args:
        request: The FastAPI request object
        
    Returns:
        Client IP address as string
    """
    # Check for forwarded IP (behind proxy/load balancer)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    # Check for real IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    # Fall back to client IP
    return request.client.host if request.client else "unknown"


def get_rate_limit_config(path: str) -> Dict[str, int]:
    """
    Get rate limit configuration for a given path.
    
    Args:
        path: The request path
        
    Returns:
        Dictionary with 'requests' and 'window' limits
    """
    # Check for exact path match
    if path in RATE_LIMITS:
        return RATE_LIMITS[path]
    
    # Check for status endpoint patterns (status endpoints with task IDs)
    if "/api/resumes/status/" in path:
        return RATE_LIMITS["/api/resumes/status"]
    
    return DEFAULT_RATE_LIMIT


def is_rate_limited(client_ip: str, path: str) -> Tuple[bool, Dict[str, int]]:
    """
    Check if a client is rate limited for a given path.
    
    Args:
        client_ip: Client IP address
        path: Request path
        
    Returns:
        Tuple of (is_limited, rate_limit_info)
    """
    config = get_rate_limit_config(path)
    max_requests = config["requests"]
    window_seconds = config["window"]
    
    # Normalize path for rate limiting (group status endpoints together)
    rate_limit_key = path
    if "/api/resumes/status/" in path:
        rate_limit_key = "/api/resumes/status"
    
    current_time = time.time()
    
    # Get current count and window start time for this client/path
    count, window_start = request_counts[client_ip][rate_limit_key]
    
    # Reset counter if window has expired
    if current_time - window_start >= window_seconds:
        count = 0
        window_start = current_time
    
    # Increment counter
    count += 1
    request_counts[client_ip][rate_limit_key] = (count, window_start)
    
    # Check if limit exceeded
    is_limited = count > max_requests
    
    rate_limit_info = {
        "limit": max_requests,
        "remaining": max(0, max_requests - count),
        "reset_time": int(window_start + window_seconds),
        "window": window_seconds
    }
    
    return is_limited, rate_limit_info


async def rate_limit_middleware(request: Request, call_next):
    """
    Rate limiting middleware for FastAPI.
    
    Args:
        request: The incoming request
        call_next: The next middleware/endpoint in the chain
        
    Returns:
        Response or rate limit error response
    """
    # Skip rate limiting for health checks and docs
    if request.url.path in ["/docs", "/redoc", "/openapi.json", "/", "/api/"]:
        return await call_next(request)
    
    client_ip = get_client_ip(request)
    path = request.url.path
    
    # Clean up old entries periodically (simple cleanup)
    if int(time.time()) % 300 == 0:  # Every 5 minutes
        cleanup_old_entries()
    
    try:
        is_limited, rate_info = is_rate_limited(client_ip, path)
        
        if is_limited:
            log.warning(f"Rate limit exceeded for {client_ip} on {path}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Rate limit exceeded. Too many requests.",
                    "limit": rate_info["limit"],
                    "window": rate_info["window"],
                    "reset_time": rate_info["reset_time"]
                },
                headers={
                    "X-RateLimit-Limit": str(rate_info["limit"]),
                    "X-RateLimit-Remaining": str(rate_info["remaining"]),
                    "X-RateLimit-Reset": str(rate_info["reset_time"]),
                    "Retry-After": str(rate_info["reset_time"] - int(time.time()))
                }
            )
        
        # Add rate limit headers to response
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(rate_info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(rate_info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(rate_info["reset_time"])
        
        log.debug(f"Request from {client_ip} to {path}: {rate_info['remaining']} requests remaining")
        
        return response
        
    except Exception as e:
        log.error(f"Error in rate limiting middleware: {e}")
        # If rate limiting fails, allow the request through
        return await call_next(request)


def cleanup_old_entries():
    """Clean up expired rate limit entries from memory."""
    current_time = time.time()
    clients_to_remove = []
    
    for client_ip, paths in request_counts.items():
        paths_to_remove = []
        
        for path, (count, window_start) in paths.items():
            config = get_rate_limit_config(path)
            if current_time - window_start >= config["window"]:
                paths_to_remove.append(path)
        
        for path in paths_to_remove:
            del paths[path]
        
        if not paths:
            clients_to_remove.append(client_ip)
    
    for client_ip in clients_to_remove:
        del request_counts[client_ip]
    
    if clients_to_remove or any(len(paths) for paths in request_counts.values()):
        log.debug(f"Cleaned up rate limit entries: {len(clients_to_remove)} clients removed")