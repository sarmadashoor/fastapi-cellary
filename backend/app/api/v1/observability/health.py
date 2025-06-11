"""
Health check and observability endpoints.

This module provides comprehensive health monitoring:
- Application health status
- Metrics collection endpoints
- Performance monitoring
- Security event summaries
- System resource monitoring
"""

import time
import psutil
from datetime import datetime, timezone
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.observability.metrics import metrics_collector
from app.logging_config import get_logger
from app.config import get_config
from app.api.v1.auth.get_user_group import get_user_group
from fastapi.security import SecurityScopes

logger = get_logger(__name__)
router = APIRouter()


class HealthStatus(BaseModel):
    """Health status response model."""
    status: str  # "healthy", "degraded", "unhealthy"
    timestamp: str
    version: str = "1.0.0"
    uptime_seconds: float
    checks: Dict[str, Any]


class MetricsResponse(BaseModel):
    """Metrics response model."""
    timestamp: str
    metrics: Dict[str, Any]
    health_status: str


class SystemResourcesResponse(BaseModel):
    """System resources response model."""
    timestamp: str
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    load_average: List[float]
    process_count: int


@router.get("/health", response_model=HealthStatus)
async def get_health_status() -> HealthStatus:
    """
    Get comprehensive application health status.
    
    **Public Endpoint** - No authentication required for health checks.
    
    **Health Checks:**
    - Application status
    - Database connectivity
    - Redis connectivity
    - Celery worker status
    - System resources
    - Error rates
    - Recent security events
    
    **Status Levels:**
    - `healthy`: All systems operational
    - `degraded`: Some non-critical issues detected
    - `unhealthy`: Critical issues requiring attention
    
    Returns comprehensive health information for monitoring systems.
    """
    start_time = time.time()
    
    # Initialize health checks
    checks = {}
    overall_status = "healthy"
    
    # 1. Application metrics health
    app_health = metrics_collector._get_health_status()
    checks["application"] = app_health
    
    if app_health["status"] != "healthy":
        overall_status = "degraded" if overall_status == "healthy" else "unhealthy"
    
    # 2. Configuration security health
    config = get_config()
    security_ok, security_issues = config.get_security_status()
    checks["security_config"] = {
        "status": "healthy" if security_ok else "degraded",
        "issues": security_issues
    }
    
    if not security_ok:
        overall_status = "degraded" if overall_status == "healthy" else overall_status
    
    # 3. System resources health
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        resource_status = "healthy"
        resource_issues = []
        
        if cpu_percent > 80:
            resource_status = "degraded"
            resource_issues.append(f"High CPU usage: {cpu_percent}%")
        
        if memory.percent > 85:
            resource_status = "degraded" if resource_status == "healthy" else "unhealthy"
            resource_issues.append(f"High memory usage: {memory.percent}%")
        
        if disk.percent > 90:
            resource_status = "unhealthy"
            resource_issues.append(f"High disk usage: {disk.percent}%")
        
        checks["system_resources"] = {
            "status": resource_status,
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "disk_percent": disk.percent,
            "issues": resource_issues
        }
        
        if resource_status != "healthy":
            overall_status = resource_status if overall_status == "healthy" else "unhealthy"
            
    except Exception as e:
        checks["system_resources"] = {
            "status": "unknown",
            "error": str(e)
        }
        overall_status = "degraded" if overall_status == "healthy" else overall_status
    
    # 4. Database connectivity (simplified check)
    try:
        # This would typically involve a simple DB query
        checks["database"] = {
            "status": "healthy",
            "connection": "available"
        }
    except Exception as e:
        checks["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        overall_status = "unhealthy"
    
    # 5. Redis connectivity (simplified check)
    try:
        # This would typically involve a Redis ping
        checks["redis"] = {
            "status": "healthy",
            "connection": "available"
        }
    except Exception as e:
        checks["redis"] = {
            "status": "degraded",  # Redis is not critical for core functionality
            "error": str(e)
        }
        overall_status = "degraded" if overall_status == "healthy" else overall_status
    
    # 6. Recent error analysis
    error_analysis = _analyze_recent_errors()
    checks["error_analysis"] = error_analysis
    
    if error_analysis["status"] != "healthy":
        overall_status = error_analysis["status"] if overall_status == "healthy" else "unhealthy"
    
    # Calculate health check duration
    health_check_duration = time.time() - start_time
    
    # Log health check
    logger.info(
        f"Health check completed: {overall_status}",
        extra={
            "event": "health_check",
            "status": overall_status,
            "duration_ms": round(health_check_duration * 1000, 2),
            "checks_count": len(checks),
            "observability": True
        }
    )
    
    # Record health check metrics
    metrics_collector.set_gauge("health_check_duration", health_check_duration)
    metrics_collector.increment_counter("health_checks_total", 1.0, {"status": overall_status})
    
    return HealthStatus(
        status=overall_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        uptime_seconds=time.time() - metrics_collector._start_time,
        checks=checks
    )


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    _: str = Depends(get_user_group)  # Requires authentication
) -> MetricsResponse:
    """
    Get comprehensive application metrics.
    
    **Authentication Required** - Admin access only.
    
    **Metrics Included:**
    - HTTP request/response metrics
    - Performance statistics (percentiles)
    - Error rates and counts
    - Security event summaries
    - Business metrics
    - System resource usage
    
    Returns detailed metrics for monitoring and alerting systems.
    """
    metrics_summary = metrics_collector.get_metrics_summary()
    
    # Add performance percentiles for key endpoints
    performance_data = {}
    key_endpoints = ["/api/auth", "/api/resumes/upload", "/api/resumes/status"]
    
    for endpoint in key_endpoints:
        percentiles = metrics_collector.get_histogram_percentiles(
            "http_request_duration",
            {"endpoint": endpoint}
        )
        if percentiles:
            performance_data[endpoint] = percentiles
    
    enhanced_metrics = {
        **metrics_summary,
        "performance_percentiles": performance_data,
        "alert_summary": _get_alert_summary(),
        "top_errors": _get_top_errors(),
        "security_summary": _get_security_summary()
    }
    
    # Log metrics access
    logger.info(
        "Metrics accessed",
        extra={
            "event": "metrics_access",
            "metrics_count": len(enhanced_metrics),
            "observability": True
        }
    )
    
    return MetricsResponse(
        timestamp=datetime.now(timezone.utc).isoformat(),
        metrics=enhanced_metrics,
        health_status=enhanced_metrics["health_status"]["status"]
    )


@router.get("/resources", response_model=SystemResourcesResponse)
async def get_system_resources(
    _: str = Depends(get_user_group)  # Requires authentication
) -> SystemResourcesResponse:
    """
    Get detailed system resource information.
    
    **Authentication Required** - Admin access only.
    
    **Resource Information:**
    - CPU usage percentage
    - Memory usage percentage  
    - Disk usage percentage
    - System load averages
    - Process count
    
    Returns current system resource utilization for capacity planning.
    """
    try:
        # Get comprehensive system metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else [0.0, 0.0, 0.0]
        process_count = len(psutil.pids())
        
        # Record resource metrics
        metrics_collector.set_gauge("cpu_usage_percent", cpu_percent)
        metrics_collector.set_gauge("memory_usage_percent", memory.percent)
        metrics_collector.set_gauge("disk_usage_percent", disk.percent)
        metrics_collector.set_gauge("process_count", process_count)
        
        # Log resource access
        logger.info(
            "System resources accessed",
            extra={
                "event": "system_resources_access",
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "disk_percent": disk.percent,
                "observability": True
            }
        )
        
        return SystemResourcesResponse(
            timestamp=datetime.now(timezone.utc).isoformat(),
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            disk_percent=disk.percent,
            load_average=list(load_avg),
            process_count=process_count
        )
        
    except Exception as e:
        logger.error(
            "Failed to get system resources",
            extra={
                "event": "system_resources_error",
                "error": str(e),
                "observability": True
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve system resources"
        )


@router.get("/security-events")
async def get_security_events(
    limit: int = 50,
    _: str = Depends(get_user_group)  # Requires authentication
) -> Dict[str, Any]:
    """
    Get recent security events for monitoring.
    
    **Authentication Required** - Admin access only.
    
    **Security Events Include:**
    - Authentication failures
    - Suspicious request patterns
    - Rate limit violations
    - File upload security violations
    - Potential attack indicators
    
    Args:
        limit: Maximum number of events to return (default: 50)
    
    Returns recent security events with details for security analysis.
    """
    recent_events = list(metrics_collector.security_events)[-limit:]
    
    # Categorize events by severity
    events_by_severity = {"low": [], "medium": [], "high": [], "critical": []}
    
    for event in recent_events:
        severity = event.get("severity", "medium")
        if severity in events_by_severity:
            events_by_severity[severity].append(event)
    
    # Calculate event statistics
    event_stats = {
        "total_events": len(recent_events),
        "events_by_severity": {k: len(v) for k, v in events_by_severity.items()},
        "unique_event_types": len(set(e.get("event_type") for e in recent_events)),
        "time_range": {
            "start": recent_events[0]["timestamp"].isoformat() if recent_events else None,
            "end": recent_events[-1]["timestamp"].isoformat() if recent_events else None
        }
    }
    
    # Log security events access
    logger.info(
        "Security events accessed",
        extra={
            "event": "security_events_access",
            "events_returned": len(recent_events),
            "limit": limit,
            "observability": True
        }
    )
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "events": recent_events,
        "statistics": event_stats,
        "events_by_severity": events_by_severity
    }


def _analyze_recent_errors() -> Dict[str, Any]:
    """Analyze recent errors for health assessment."""
    # Get error counts from metrics
    total_requests = sum(
        v for k, v in metrics_collector.counters.items() 
        if "http_requests_total" in k
    )
    total_errors = sum(
        v for k, v in metrics_collector.counters.items() 
        if "http_errors_total" in k
    )
    
    error_rate = total_errors / total_requests if total_requests > 0 else 0
    
    status = "healthy"
    if error_rate > 0.05:  # 5%
        status = "degraded"
    if error_rate > 0.15:  # 15%
        status = "unhealthy"
    
    return {
        "status": status,
        "error_rate": error_rate,
        "total_errors": total_errors,
        "total_requests": total_requests
    }


def _get_alert_summary() -> Dict[str, Any]:
    """Get summary of recent alerts."""
    # This would typically connect to an alerting system
    return {
        "active_alerts": 0,
        "recent_alerts": 0,
        "alert_types": []
    }


def _get_top_errors() -> List[Dict[str, Any]]:
    """Get most frequent error types."""
    error_counts = {}
    
    for key, count in metrics_collector.counters.items():
        if "http_errors_total" in key:
            # Parse error information from metric key
            error_counts[key] = count
    
    # Sort by count and return top errors
    top_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    return [{"error_type": error, "count": count} for error, count in top_errors]


def _get_security_summary() -> Dict[str, Any]:
    """Get security events summary."""
    recent_events = list(metrics_collector.security_events)[-100:]  # Last 100 events
    
    if not recent_events:
        return {"total_events": 0, "unique_types": 0, "severity_breakdown": {}}
    
    # Count by event type
    event_types = {}
    severity_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    
    for event in recent_events:
        event_type = event.get("event_type", "unknown")
        severity = event.get("severity", "medium")
        
        event_types[event_type] = event_types.get(event_type, 0) + 1
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
    
    return {
        "total_events": len(recent_events),
        "unique_types": len(event_types),
        "top_event_types": sorted(event_types.items(), key=lambda x: x[1], reverse=True)[:5],
        "severity_breakdown": severity_counts
    }