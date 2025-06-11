"""
Application metrics and observability module.

This module provides comprehensive metrics collection for:
- Performance monitoring
- Security event tracking
- Business metrics
- Health and status monitoring
- Error tracking and alerting
"""

import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from collections import defaultdict, deque
import threading

from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class MetricPoint:
    """Represents a single metric data point."""
    timestamp: datetime
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertRule:
    """Defines an alert rule for metrics."""
    metric_name: str
    threshold: float
    operator: str  # "gt", "lt", "eq", "gte", "lte"
    window_minutes: int
    alert_priority: str  # "low", "medium", "high", "critical"
    description: str
    enabled: bool = True


class MetricsCollector:
    """Thread-safe metrics collector for application observability."""
    
    def __init__(self, max_points_per_metric: int = 1000):
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_points_per_metric))
        self.counters: Dict[str, float] = defaultdict(float)
        self.gauges: Dict[str, float] = defaultdict(float)
        self.histograms: Dict[str, List[float]] = defaultdict(list)
        self.alert_rules: List[AlertRule] = []
        self._lock = threading.RLock()
        
        # Performance tracking
        self.request_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.error_counts: Dict[str, int] = defaultdict(int)
        
        # Security metrics
        self.security_events: deque = deque(maxlen=1000)
        self.failed_auth_attempts: Dict[str, int] = defaultdict(int)
        
        # Business metrics
        self.business_events: deque = deque(maxlen=1000)
        
        # Initialize default alert rules
        self._setup_default_alerts()
    
    def _setup_default_alerts(self) -> None:
        """Setup default alert rules for critical metrics."""
        default_alerts = [
            AlertRule(
                metric_name="http_error_rate",
                threshold=0.05,  # 5% error rate
                operator="gt",
                window_minutes=5,
                alert_priority="high",
                description="High HTTP error rate detected"
            ),
            AlertRule(
                metric_name="failed_auth_attempts",
                threshold=10,
                operator="gt",
                window_minutes=5,
                alert_priority="critical",
                description="Excessive failed authentication attempts"
            ),
            AlertRule(
                metric_name="response_time_p95",
                threshold=5.0,  # 5 seconds
                operator="gt",
                window_minutes=10,
                alert_priority="medium",
                description="High response time P95"
            ),
            AlertRule(
                metric_name="disk_usage",
                threshold=0.85,  # 85%
                operator="gt",
                window_minutes=1,
                alert_priority="high",
                description="High disk usage"
            ),
            AlertRule(
                metric_name="memory_usage",
                threshold=0.90,  # 90%
                operator="gt",
                window_minutes=1,
                alert_priority="critical",
                description="Critical memory usage"
            ),
        ]
        
        self.alert_rules.extend(default_alerts)
    
    def increment_counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter metric."""
        with self._lock:
            metric_key = self._create_metric_key(name, labels)
            self.counters[metric_key] += value
            
            # Record time series data
            self.metrics[metric_key].append(MetricPoint(
                timestamp=datetime.now(timezone.utc),
                value=self.counters[metric_key],
                labels=labels or {},
                metadata={"type": "counter"}
            ))
    
    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge metric value."""
        with self._lock:
            metric_key = self._create_metric_key(name, labels)
            self.gauges[metric_key] = value
            
            # Record time series data
            self.metrics[metric_key].append(MetricPoint(
                timestamp=datetime.now(timezone.utc),
                value=value,
                labels=labels or {},
                metadata={"type": "gauge"}
            ))
    
    def record_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Record a histogram metric value."""
        with self._lock:
            metric_key = self._create_metric_key(name, labels)
            self.histograms[metric_key].append(value)
            
            # Keep only recent values (last 1000)
            if len(self.histograms[metric_key]) > 1000:
                self.histograms[metric_key] = self.histograms[metric_key][-1000:]
            
            # Record time series data
            self.metrics[metric_key].append(MetricPoint(
                timestamp=datetime.now(timezone.utc),
                value=value,
                labels=labels or {},
                metadata={"type": "histogram"}
            ))
    
    def record_request_time(self, endpoint: str, method: str, status_code: int, duration: float) -> None:
        """Record HTTP request metrics."""
        labels = {
            "endpoint": endpoint,
            "method": method,
            "status_code": str(status_code)
        }
        
        # Record response time
        self.record_histogram("http_request_duration", duration, labels)
        
        # Increment request counter
        self.increment_counter("http_requests_total", 1.0, labels)
        
        # Track errors
        if status_code >= 400:
            self.increment_counter("http_errors_total", 1.0, labels)
            self.error_counts[endpoint] += 1
        
        # Store recent request times for percentile calculations
        key = f"{method}:{endpoint}"
        self.request_times[key].append(duration)
        
        # Log performance metrics
        logger.info(
            "HTTP request completed",
            extra={
                "event": "http_request",
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "duration_ms": round(duration * 1000, 2),
                "performance_metric": True
            }
        )
        
        # Check for performance alerts
        self._check_performance_alerts(endpoint, duration)
    
    def record_security_event(self, event_type: str, severity: str, details: Dict[str, Any]) -> None:
        """Record security events for monitoring."""
        security_event = {
            "timestamp": datetime.now(timezone.utc),
            "event_type": event_type,
            "severity": severity,
            "details": details
        }
        
        with self._lock:
            self.security_events.append(security_event)
        
        # Increment security counter
        self.increment_counter("security_events_total", 1.0, {
            "event_type": event_type,
            "severity": severity
        })
        
        # Log security event
        logger.warning(
            f"Security event: {event_type}",
            extra={
                "event": "security_event",
                "event_type": event_type,
                "severity": severity,
                "details": details,
                "security_event": True,
                "alert_priority": severity
            }
        )
        
        # Check for security alerts
        self._check_security_alerts(event_type, severity)
    
    def record_business_event(self, event_name: str, value: float, context: Dict[str, Any]) -> None:
        """Record business metrics and events."""
        business_event = {
            "timestamp": datetime.now(timezone.utc),
            "event_name": event_name,
            "value": value,
            "context": context
        }
        
        with self._lock:
            self.business_events.append(business_event)
        
        # Record as counter
        self.increment_counter(f"business_{event_name}", value, context)
        
        # Log business event
        logger.info(
            f"Business event: {event_name}",
            extra={
                "event": "business_event",
                "event_name": event_name,
                "value": value,
                "context": context,
                "business_metric": True
            }
        )
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get comprehensive metrics summary."""
        with self._lock:
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "counters": dict(self.counters),
                "gauges": dict(self.gauges),
                "recent_security_events": list(self.security_events)[-10:],
                "recent_business_events": list(self.business_events)[-10:],
                "error_counts": dict(self.error_counts),
                "performance_summary": self._get_performance_summary(),
                "health_status": self._get_health_status()
            }
    
    def get_histogram_percentiles(self, name: str, labels: Optional[Dict[str, str]] = None) -> Dict[str, float]:
        """Calculate histogram percentiles."""
        metric_key = self._create_metric_key(name, labels)
        
        with self._lock:
            values = self.histograms.get(metric_key, [])
            
            if not values:
                return {}
            
            sorted_values = sorted(values)
            n = len(sorted_values)
            
            percentiles = {}
            for p in [50, 75, 90, 95, 99]:
                idx = int(n * p / 100) - 1
                if idx < 0:
                    idx = 0
                elif idx >= n:
                    idx = n - 1
                percentiles[f"p{p}"] = sorted_values[idx]
            
            percentiles["min"] = sorted_values[0]
            percentiles["max"] = sorted_values[-1]
            percentiles["mean"] = sum(sorted_values) / n
            
            return percentiles
    
    def _create_metric_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """Create a unique metric key from name and labels."""
        if not labels:
            return name
        
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def _get_performance_summary(self) -> Dict[str, Any]:
        """Get performance metrics summary."""
        summary = {}
        
        for endpoint, times in self.request_times.items():
            if times:
                sorted_times = sorted(times)
                n = len(sorted_times)
                summary[endpoint] = {
                    "request_count": n,
                    "avg_duration": sum(sorted_times) / n,
                    "p50": sorted_times[int(n * 0.5)] if n > 0 else 0,
                    "p95": sorted_times[int(n * 0.95)] if n > 0 else 0,
                    "p99": sorted_times[int(n * 0.99)] if n > 0 else 0,
                }
        
        return summary
    
    def _get_health_status(self) -> Dict[str, Any]:
        """Get overall health status."""
        # Calculate error rates
        total_requests = sum(self.counters.get(k, 0) for k in self.counters.keys() if "http_requests_total" in k)
        total_errors = sum(self.counters.get(k, 0) for k in self.counters.keys() if "http_errors_total" in k)
        
        error_rate = total_errors / total_requests if total_requests > 0 else 0
        
        # Recent security events
        recent_security = len([e for e in self.security_events if 
                              (datetime.now(timezone.utc) - e["timestamp"]).total_seconds() < 300])
        
        # Determine overall health
        health_status = "healthy"
        if error_rate > 0.1:  # 10% error rate
            health_status = "degraded"
        if error_rate > 0.25 or recent_security > 5:  # 25% error rate or many security events
            health_status = "unhealthy"
        
        return {
            "status": health_status,
            "error_rate": error_rate,
            "total_requests": total_requests,
            "total_errors": total_errors,
            "recent_security_events": recent_security,
            "uptime_seconds": time.time() - self._start_time if hasattr(self, '_start_time') else 0
        }
    
    def _check_performance_alerts(self, endpoint: str, duration: float) -> None:
        """Check if performance alerts should be triggered."""
        # Check response time alerts
        if duration > 5.0:  # 5 seconds
            logger.warning(
                "Slow response time detected",
                extra={
                    "event": "performance_alert",
                    "alert_type": "slow_response",
                    "endpoint": endpoint,
                    "duration": duration,
                    "threshold": 5.0,
                    "alert_priority": "medium"
                }
            )
    
    def _check_security_alerts(self, event_type: str, severity: str) -> None:
        """Check if security alerts should be triggered."""
        # Count recent security events
        recent_events = [e for e in self.security_events if 
                        (datetime.now(timezone.utc) - e["timestamp"]).total_seconds() < 300]
        
        if len(recent_events) > 10:
            logger.error(
                "High volume of security events detected",
                extra={
                    "event": "security_alert",
                    "alert_type": "high_security_event_volume",
                    "recent_events_count": len(recent_events),
                    "time_window": "5_minutes",
                    "alert_priority": "critical"
                }
            )


# Global metrics collector instance
metrics_collector = MetricsCollector()

# Initialize start time
metrics_collector._start_time = time.time()