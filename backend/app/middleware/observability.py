"""
Observability middleware for automatic metrics collection.

This middleware automatically collects:
- HTTP request/response metrics
- Performance timing data
- Error tracking
- Security event monitoring
"""

import time
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability.metrics import metrics_collector
from app.logging_config import get_logger

logger = get_logger(__name__)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Middleware for automatic observability data collection."""
    
    def __init__(self, app, collect_detailed_metrics: bool = True):
        super().__init__(app)
        self.collect_detailed_metrics = collect_detailed_metrics
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with automatic metrics collection."""
        start_time = time.time()
        
        # Extract request information
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # Generate request ID for tracking
        request_id = f"req_{int(start_time)}_{hash(f'{client_ip}{path}')}"
        
        # Log request start
        logger.info(
            f"Request started: {method} {path}",
            extra={
                "event": "request_started",
                "request_id": request_id,
                "method": method,
                "path": path,
                "client_ip": client_ip,
                "user_agent": user_agent,
                "observability": True
            }
        )
        
        response = None
        error_occurred = False
        
        try:
            # Process the request
            response = await call_next(request)
            
        except Exception as e:
            error_occurred = True
            
            # Record error metrics
            metrics_collector.increment_counter(
                "http_errors_total", 
                1.0, 
                {
                    "method": method,
                    "path": path,
                    "error_type": type(e).__name__
                }
            )
            
            # Log error
            logger.error(
                f"Request failed: {method} {path}",
                extra={
                    "event": "request_error",
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "client_ip": client_ip,
                    "observability": True
                }
            )
            
            # Re-raise the exception
            raise
        
        finally:
            # Calculate request duration
            duration = time.time() - start_time
            
            if response is not None:
                status_code = response.status_code
                
                # Record comprehensive metrics
                self._record_request_metrics(
                    method=method,
                    path=path,
                    status_code=status_code,
                    duration=duration,
                    client_ip=client_ip,
                    user_agent=user_agent,
                    request_id=request_id
                )
                
                # Check for security events
                self._check_security_indicators(
                    request=request,
                    response=response,
                    client_ip=client_ip,
                    duration=duration
                )
                
                # Log request completion
                logger.info(
                    f"Request completed: {method} {path} - {status_code}",
                    extra={
                        "event": "request_completed",
                        "request_id": request_id,
                        "method": method,
                        "path": path,
                        "status_code": status_code,
                        "duration_ms": round(duration * 1000, 2),
                        "client_ip": client_ip,
                        "observability": True
                    }
                )
            
            elif error_occurred:
                # Record error metrics for failed requests
                self._record_error_metrics(
                    method=method,
                    path=path,
                    duration=duration,
                    client_ip=client_ip,
                    request_id=request_id
                )
        
        return response
    
    def _record_request_metrics(self, method: str, path: str, status_code: int, 
                               duration: float, client_ip: str, user_agent: str, 
                               request_id: str) -> None:
        """Record comprehensive request metrics."""
        
        # Core HTTP metrics
        metrics_collector.record_request_time(
            endpoint=path,
            method=method,
            status_code=status_code,
            duration=duration
        )
        
        if self.collect_detailed_metrics:
            # Additional detailed metrics
            
            # Track unique clients
            metrics_collector.increment_counter(
                "unique_clients_total",
                1.0,
                {"client_ip_hash": str(hash(client_ip))}
            )
            
            # Track user agents
            metrics_collector.increment_counter(
                "user_agents_total",
                1.0,
                {"user_agent_hash": str(hash(user_agent))}
            )
            
            # Track endpoint popularity
            metrics_collector.increment_counter(
                "endpoint_requests",
                1.0,
                {"endpoint": path, "method": method}
            )
            
            # Track response size if available
            # Note: This would require access to response content length
            
            # Performance categorization
            if duration > 5.0:
                metrics_collector.increment_counter("slow_requests_total", 1.0)
            elif duration < 0.1:
                metrics_collector.increment_counter("fast_requests_total", 1.0)
    
    def _record_error_metrics(self, method: str, path: str, duration: float,
                             client_ip: str, request_id: str) -> None:
        """Record metrics for failed requests."""
        
        metrics_collector.increment_counter(
            "request_exceptions_total",
            1.0,
            {"method": method, "path": path}
        )
        
        # Record duration even for failed requests
        metrics_collector.record_histogram(
            "failed_request_duration",
            duration,
            {"method": method, "path": path}
        )
    
    def _check_security_indicators(self, request: Request, response: Response,
                                  client_ip: str, duration: float) -> None:
        """Check for security indicators in requests."""
        
        method = request.method
        path = request.url.path
        status_code = response.status_code
        
        # Check for suspicious patterns
        suspicious_indicators = []
        
        # 1. Multiple 401/403 responses (potential brute force)
        if status_code in [401, 403]:
            metrics_collector.record_security_event(
                event_type="auth_failure",
                severity="medium",
                details={
                    "client_ip": client_ip,
                    "path": path,
                    "method": method,
                    "status_code": status_code
                }
            )
        
        # 2. SQL injection attempts (based on path patterns)
        sql_injection_patterns = ["'", "union", "select", "drop", "insert", "--", "/*"]
        query_string = str(request.url.query).lower()
        path_lower = path.lower()
        
        if any(pattern in query_string or pattern in path_lower for pattern in sql_injection_patterns):
            suspicious_indicators.append("sql_injection_attempt")
            metrics_collector.record_security_event(
                event_type="sql_injection_attempt",
                severity="high",
                details={
                    "client_ip": client_ip,
                    "path": path,
                    "query": query_string,
                    "user_agent": request.headers.get("user-agent", "unknown")
                }
            )
        
        # 3. XSS attempts
        xss_patterns = ["<script", "javascript:", "onload=", "onerror="]
        if any(pattern in query_string or pattern in path_lower for pattern in xss_patterns):
            suspicious_indicators.append("xss_attempt")
            metrics_collector.record_security_event(
                event_type="xss_attempt",
                severity="high",
                details={
                    "client_ip": client_ip,
                    "path": path,
                    "query": query_string
                }
            )
        
        # 4. Directory traversal attempts
        traversal_patterns = ["../", "..\\", "....//"]
        if any(pattern in path_lower for pattern in traversal_patterns):
            suspicious_indicators.append("directory_traversal_attempt")
            metrics_collector.record_security_event(
                event_type="directory_traversal_attempt",
                severity="high",
                details={
                    "client_ip": client_ip,
                    "path": path
                }
            )
        
        # 5. Suspicious user agents
        user_agent = request.headers.get("user-agent", "").lower()
        suspicious_ua_patterns = ["sqlmap", "nikto", "nmap", "burp", "scanner"]
        if any(pattern in user_agent for pattern in suspicious_ua_patterns):
            suspicious_indicators.append("suspicious_user_agent")
            metrics_collector.record_security_event(
                event_type="suspicious_user_agent",
                severity="medium",
                details={
                    "client_ip": client_ip,
                    "user_agent": user_agent,
                    "path": path
                }
            )
        
        # 6. Rapid requests (potential DoS)
        # This would require rate tracking per IP
        
        # 7. Large response times (potential DoS or resource exhaustion)
        if duration > 10.0:  # 10 seconds
            metrics_collector.record_security_event(
                event_type="slow_response_potential_dos",
                severity="medium",
                details={
                    "client_ip": client_ip,
                    "path": path,
                    "duration": duration
                }
            )
        
        # 8. 404 scanning
        if status_code == 404:
            metrics_collector.increment_counter(
                "not_found_requests",
                1.0,
                {"client_ip_hash": str(hash(client_ip))}
            )
        
        # Log any suspicious activity
        if suspicious_indicators:
            logger.warning(
                f"Suspicious activity detected from {client_ip}",
                extra={
                    "event": "suspicious_activity",
                    "client_ip": client_ip,
                    "path": path,
                    "indicators": suspicious_indicators,
                    "security_event": True,
                    "alert_priority": "medium"
                }
            )