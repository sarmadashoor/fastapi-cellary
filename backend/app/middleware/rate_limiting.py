"""
Advanced rate limiting middleware for FastAPI applications.

This module provides comprehensive rate limiting and abuse detection:
- Adaptive rate limiting based on client behavior
- Attack pattern detection (SQL injection, XSS, etc.)
- Client threat scoring and profiling
- Automatic blocking of malicious clients
- Detailed security event logging
"""

import time
from typing import Dict, Tuple

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.validation.rate_limiting import advanced_rate_limiter, ThreatLevel
from app.logging_config import get_logger
from app.observability.metrics import metrics_collector

logger = get_logger(__name__)

# Endpoint-specific rate limit rule mappings
ENDPOINT_RULES = {
    "/api/auth/get_token": "auth_strict",
    "/api/auth/refresh_token": "auth_strict", 
    "/api/resumes/upload": "upload_moderate",
    "/api/resumes/status": "status_generous",
    "/api/words/create": "api_general",
    "/api/words/get": "api_general",
    "/api/words/delete": "api_general",
    "/api/observability/health": "status_generous",
    "/api/observability/metrics": "api_general",
    "/api/observability/resources": "api_general"
}

# Default rule for unspecified endpoints
DEFAULT_RULE = "api_general"


def get_client_ip(request: Request) -> str:
    """
    Extract client IP address from request with enhanced proxy support.
    
    Args:
        request: The FastAPI request object
        
    Returns:
        Client IP address as string
    """
    # Check for forwarded IP (behind proxy/load balancer)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain (original client)
        return forwarded_for.split(",")[0].strip()
    
    # Check for real IP header (nginx)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # Check for Cloudflare
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    
    # Fall back to client IP
    return request.client.host if request.client else "unknown"


def get_rate_limit_rule(path: str) -> str:
    """
    Get rate limit rule name for a given path.
    
    Args:
        path: The request path
        
    Returns:
        Rate limit rule name
    """
    # Check for exact path match
    if path in ENDPOINT_RULES:
        return ENDPOINT_RULES[path]
    
    # Check for parameterized endpoints
    if "/api/resumes/status/" in path:
        return "status_generous"
    
    if "/api/words/" in path:
        return "api_general"
    
    if "/api/auth/" in path:
        return "auth_strict"
    
    if "/api/observability/" in path:
        return "api_general"
    
    return DEFAULT_RULE


def get_user_agent(request: Request) -> str:
    """
    Extract user agent from request headers.
    
    Args:
        request: The FastAPI request object
        
    Returns:
        User agent string
    """
    return request.headers.get("User-Agent", "")


def get_geo_country(request: Request) -> str:
    """
    Extract geo country from request headers (if available).
    
    Args:
        request: The FastAPI request object
        
    Returns:
        Country code or None
    """
    # Common headers used by CDNs and proxies
    return (
        request.headers.get("CF-IPCountry") or  # Cloudflare
        request.headers.get("X-Country-Code") or  # Various proxies
        request.headers.get("GeoIP-Country") or  # GeoIP services
        None
    )


async def rate_limit_middleware(request: Request, call_next):
    """
    Advanced rate limiting middleware with abuse detection.
    
    Args:
        request: The incoming request
        call_next: The next middleware/endpoint in the chain
        
    Returns:
        Response or rate limit/block error response
    """
    # Skip rate limiting for health checks and docs
    exempt_paths = ["/docs", "/redoc", "/openapi.json", "/", "/api/", "/favicon.ico"]
    if request.url.path in exempt_paths:
        return await call_next(request)
    
    # Extract request information
    client_ip = get_client_ip(request)
    path = request.url.path
    method = request.method
    user_agent = get_user_agent(request)
    geo_country = get_geo_country(request)
    
    # Get rate limit rule for this endpoint
    rule_name = get_rate_limit_rule(path)
    
    start_time = time.time()
    
    try:
        # Check rate limits and get decision
        is_allowed, limit_info = advanced_rate_limiter.check_rate_limit(
            client_id=client_ip,
            endpoint=path,
            rule_name=rule_name
        )
        
        if not is_allowed:
            # Handle blocked or rate limited requests
            if limit_info.get("blocked", False):
                # Client is blocked due to suspicious activity
                logger.warning(
                    f"Blocked client attempted access: {client_ip}",
                    extra={
                        "event": "blocked_client_access",
                        "client_ip": client_ip,
                        "path": path,
                        "method": method,
                        "user_agent": user_agent,
                        "blocked_until": limit_info.get("blocked_until"),
                        "reason": limit_info.get("reason"),
                        "security_event": True,
                        "alert_priority": "high"
                    }
                )
                
                # Record security event
                metrics_collector.record_security_event(
                    event_type="blocked_client_access",
                    severity="high",
                    details={
                        "client_ip": client_ip,
                        "path": path,
                        "method": method,
                        "reason": limit_info.get("reason")
                    }
                )
                
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "detail": "Access denied due to suspicious activity.",
                        "blocked_until": limit_info.get("blocked_until"),
                        "contact": "Contact support if you believe this is an error"
                    },
                    headers={
                        "X-Block-Reason": limit_info.get("reason", "suspicious_activity"),
                        "Retry-After": "3600"  # Suggest retry after 1 hour
                    }
                )
            else:
                # Standard rate limit exceeded
                logger.info(
                    f"Rate limit exceeded: {client_ip} on {path}",
                    extra={
                        "event": "rate_limit_exceeded",
                        "client_ip": client_ip,
                        "path": path,
                        "method": method,
                        "rule_name": rule_name,
                        "limit_info": limit_info,
                        "security_event": True
                    }
                )
                
                # Calculate retry after time
                retry_after = max(1, limit_info.get("reset_time", 0) - int(time.time()))
                
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "detail": "Rate limit exceeded. Please slow down your requests.",
                        "limit": limit_info.get("limit"),
                        "window": limit_info.get("window"),
                        "reset_time": limit_info.get("reset_time"),
                        "rule": limit_info.get("rule_name")
                    },
                    headers={
                        "X-RateLimit-Limit": str(limit_info.get("limit", 0)),
                        "X-RateLimit-Remaining": str(limit_info.get("remaining", 0)),
                        "X-RateLimit-Reset": str(limit_info.get("reset_time", 0)),
                        "X-RateLimit-Rule": rule_name,
                        "Retry-After": str(retry_after)
                    }
                )
        
        # Process the request
        response = await call_next(request)
        response_time = time.time() - start_time
        
        # Record the request for pattern analysis
        advanced_rate_limiter.record_request(
            client_id=client_ip,
            endpoint=path,
            method=method,
            response_code=response.status_code,
            response_time=response_time,
            user_agent=user_agent,
            geo_country=geo_country
        )
        
        # Add rate limit headers to successful responses
        if "limit" in limit_info:
            response.headers["X-RateLimit-Limit"] = str(limit_info["limit"])
            response.headers["X-RateLimit-Remaining"] = str(limit_info.get("remaining", 0))
            response.headers["X-RateLimit-Reset"] = str(limit_info.get("reset_time", 0))
            response.headers["X-RateLimit-Rule"] = rule_name
        
        # Log successful request
        threat_level = advanced_rate_limiter.get_client_threat_level(client_ip)
        if threat_level != ThreatLevel.LOW:
            logger.info(
                f"Request from elevated threat client: {client_ip}",
                extra={
                    "event": "elevated_threat_request",
                    "client_ip": client_ip,
                    "path": path,
                    "threat_level": threat_level.value,
                    "response_code": response.status_code,
                    "response_time_ms": round(response_time * 1000, 2),
                    "security_event": True
                }
            )
        
        return response
        
    except Exception as e:
        logger.error(
            f"Error in advanced rate limiting middleware: {e}",
            extra={
                "event": "rate_limiting_error",
                "client_ip": client_ip,
                "path": path,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        # If rate limiting fails, allow the request through but log the failure
        metrics_collector.record_security_event(
            event_type="rate_limiting_failure",
            severity="medium",
            details={"error": str(e), "client_ip": client_ip}
        )
        return await call_next(request)


def get_rate_limiting_statistics() -> Dict:
    """
    Get current rate limiting statistics for monitoring.
    
    Returns:
        Dictionary with current rate limiting statistics
    """
    return advanced_rate_limiter.get_statistics()