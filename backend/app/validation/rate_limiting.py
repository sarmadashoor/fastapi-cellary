"""
Advanced rate limiting and abuse detection system.

This module provides comprehensive protection against:
- Rate limit violations
- Distributed attacks
- Bot detection
- Suspicious behavior patterns
- Adaptive rate limiting
- Geolocation-based filtering
"""

import time
import hashlib
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

from app.logging_config import get_logger
from app.observability.metrics import metrics_collector

logger = get_logger(__name__)


class ThreatLevel(Enum):
    """Threat level classification."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RateLimitType(Enum):
    """Types of rate limiting."""
    PER_IP = "per_ip"
    PER_USER = "per_user"
    PER_ENDPOINT = "per_endpoint"
    GLOBAL = "global"


@dataclass
class RateLimitRule:
    """Rate limit rule configuration."""
    name: str
    limit_type: RateLimitType
    max_requests: int
    window_seconds: int
    burst_allowance: int = 0  # Additional requests allowed in burst
    adaptive: bool = False  # Whether to adapt based on server load
    enabled: bool = True


@dataclass
class ClientProfile:
    """Profile of a client's behavior."""
    client_id: str
    first_seen: datetime
    total_requests: int = 0
    failed_requests: int = 0
    blocked_requests: int = 0
    unique_endpoints: Set[str] = field(default_factory=set)
    user_agents: Set[str] = field(default_factory=set)
    threat_score: float = 0.0
    threat_level: ThreatLevel = ThreatLevel.LOW
    is_bot: bool = False
    is_blocked: bool = False
    blocked_until: Optional[datetime] = None
    notes: List[str] = field(default_factory=list)


@dataclass
class RequestPattern:
    """Pattern analysis of requests."""
    timestamp: datetime
    client_id: str
    endpoint: str
    method: str
    user_agent: str
    response_code: int
    response_time: float
    geo_country: Optional[str] = None


class AdvancedRateLimiter:
    """Advanced rate limiting with abuse detection."""
    
    def __init__(self):
        # Core rate limiting data
        self.request_counts: Dict[str, Dict[str, Tuple[int, float]]] = defaultdict(
            lambda: defaultdict(lambda: (0, 0.0))
        )
        
        # Client profiles for behavior analysis
        self.client_profiles: Dict[str, ClientProfile] = {}
        
        # Request patterns for analysis
        self.request_patterns: deque = deque(maxlen=10000)
        
        # Blocked IPs and temporary bans
        self.blocked_ips: Dict[str, datetime] = {}
        self.suspicious_ips: Dict[str, float] = defaultdict(float)
        
        # Bot detection patterns
        self.bot_user_agents = {
            "googlebot", "bingbot", "slurp", "crawler", "spider", "bot",
            "curl", "wget", "python-requests", "go-http-client", "scanner",
            "nikto", "sqlmap", "nmap", "burp", "zap", "w3af"
        }
        
        # Rate limit rules
        self.rules = self._setup_default_rules()
        
        # Pattern detection
        self.attack_patterns = self._setup_attack_patterns()
        
        # Performance metrics
        self.performance_window = deque(maxlen=1000)
        
    def _setup_default_rules(self) -> List[RateLimitRule]:
        """Setup default rate limiting rules."""
        return [
            # Authentication endpoints - strict limits
            RateLimitRule(
                name="auth_strict",
                limit_type=RateLimitType.PER_IP,
                max_requests=5,
                window_seconds=300,  # 5 minutes
                burst_allowance=0
            ),
            
            # File upload endpoints - moderate limits
            RateLimitRule(
                name="upload_moderate",
                limit_type=RateLimitType.PER_IP,
                max_requests=10,
                window_seconds=300,  # 5 minutes
                burst_allowance=2
            ),
            
            # Status check endpoints - generous limits
            RateLimitRule(
                name="status_generous",
                limit_type=RateLimitType.PER_IP,
                max_requests=60,
                window_seconds=60,  # 1 minute
                burst_allowance=10
            ),
            
            # General API endpoints
            RateLimitRule(
                name="api_general",
                limit_type=RateLimitType.PER_IP,
                max_requests=100,
                window_seconds=60,
                burst_allowance=20,
                adaptive=True
            ),
            
            # Global rate limit for extreme cases
            RateLimitRule(
                name="global_emergency",
                limit_type=RateLimitType.GLOBAL,
                max_requests=1000,
                window_seconds=60,
                burst_allowance=0
            ),
        ]
    
    def _setup_attack_patterns(self) -> Dict[str, Dict]:
        """Setup attack pattern detection rules."""
        return {
            "sql_injection": {
                "patterns": [
                    r"(\bunion\b|\bselect\b|\binsert\b|\bdelete\b|\bdrop\b|\btable\b)",
                    r"(\-\-|\#|\/\*|\*\/)",
                    r"(\bor\b\s+\d+\s*=\s*\d+|\band\b\s+\d+\s*=\s*\d+)",
                    r"(\bor\b\s+[\'\"]?\w+[\'\"]?\s*=\s*[\'\"]?\w+[\'\"]?)"
                ],
                "threat_level": ThreatLevel.HIGH,
                "block_duration": 3600  # 1 hour
            },
            "xss_attempt": {
                "patterns": [
                    r"<script[^>]*>.*?</script>",
                    r"javascript:",
                    r"onload\s*=",
                    r"onerror\s*=",
                    r"eval\s*\(",
                    r"document\s*\.\s*cookie"
                ],
                "threat_level": ThreatLevel.HIGH,
                "block_duration": 1800  # 30 minutes
            },
            "directory_traversal": {
                "patterns": [
                    r"\.\.\/",
                    r"\.\.\\",
                    r"\.\.%2f",
                    r"\.\.%2F",
                    r"\.\.%5c",
                    r"\.\.%5C"
                ],
                "threat_level": ThreatLevel.HIGH,
                "block_duration": 1800  # 30 minutes
            },
            "command_injection": {
                "patterns": [
                    r"[\|;&`]",
                    r"\$\(",
                    r"`.*`",
                    r">\s*\/",
                    r"<\s*\/",
                    r"\bcat\b|\bls\b|\bpwd\b|\bwhoami\b"
                ],
                "threat_level": ThreatLevel.CRITICAL,
                "block_duration": 7200  # 2 hours
            },
            "brute_force": {
                "indicators": {
                    "rapid_failed_auth": {"threshold": 5, "window": 60},
                    "dict_attack_pattern": {"threshold": 20, "window": 300},
                    "credential_stuffing": {"threshold": 50, "window": 900}
                },
                "threat_level": ThreatLevel.HIGH,
                "block_duration": 1800
            }
        }
    
    def check_rate_limit(self, client_id: str, endpoint: str, rule_name: str) -> Tuple[bool, Dict]:
        """
        Check if request should be rate limited.
        
        Args:
            client_id: Unique client identifier (usually IP)
            endpoint: API endpoint being accessed
            rule_name: Name of the rate limit rule to apply
            
        Returns:
            Tuple of (is_allowed, limit_info)
        """
        # Check if client is blocked
        if self.is_blocked(client_id):
            block_info = self.blocked_ips.get(client_id)
            return False, {
                "blocked": True,
                "blocked_until": block_info.isoformat() if block_info else None,
                "reason": "Client temporarily blocked due to suspicious activity"
            }
        
        # Find applicable rule
        rule = self._get_rule_by_name(rule_name)
        if not rule or not rule.enabled:
            return True, {"allowed": True, "rule": "none"}
        
        # Check rate limit
        is_allowed, limit_info = self._check_rule_limit(client_id, endpoint, rule)
        
        # Update client profile
        self._update_client_profile(client_id, endpoint, is_allowed)
        
        # Analyze for suspicious patterns
        self._analyze_request_pattern(client_id, endpoint)
        
        return is_allowed, limit_info
    
    def record_request(self, client_id: str, endpoint: str, method: str, 
                      response_code: int, response_time: float, 
                      user_agent: str = "", geo_country: str = None) -> None:
        """Record request for pattern analysis."""
        
        pattern = RequestPattern(
            timestamp=datetime.now(timezone.utc),
            client_id=client_id,
            endpoint=endpoint,
            method=method,
            user_agent=user_agent,
            response_code=response_code,
            response_time=response_time,
            geo_country=geo_country
        )
        
        self.request_patterns.append(pattern)
        
        # Update client profile
        if client_id not in self.client_profiles:
            self.client_profiles[client_id] = ClientProfile(
                client_id=client_id,
                first_seen=datetime.now(timezone.utc)
            )
        
        profile = self.client_profiles[client_id]
        profile.total_requests += 1
        profile.unique_endpoints.add(endpoint)
        profile.user_agents.add(user_agent)
        
        if response_code >= 400:
            profile.failed_requests += 1
        
        # Bot detection
        self._detect_bot_behavior(client_id, user_agent, endpoint)
        
        # Attack pattern detection
        self._detect_attack_patterns(client_id, endpoint, user_agent)
        
        # Update threat score
        self._update_threat_score(client_id)
        
        # Log metrics
        metrics_collector.record_security_event(
            event_type="request_analyzed",
            severity="low",
            details={
                "client_id": hashlib.sha256(client_id.encode()).hexdigest()[:16],
                "endpoint": endpoint,
                "response_code": response_code,
                "threat_score": profile.threat_score
            }
        )
    
    def is_blocked(self, client_id: str) -> bool:
        """Check if client is currently blocked."""
        if client_id in self.blocked_ips:
            blocked_until = self.blocked_ips[client_id]
            if datetime.now(timezone.utc) < blocked_until:
                return True
            else:
                # Block expired, remove it
                del self.blocked_ips[client_id]
                logger.info(
                    f"Block expired for client {client_id}",
                    extra={
                        "event": "block_expired",
                        "client_id": hashlib.sha256(client_id.encode()).hexdigest()[:16],
                        "security_event": True
                    }
                )
        return False
    
    def block_client(self, client_id: str, duration_seconds: int, reason: str) -> None:
        """Block a client for specified duration."""
        blocked_until = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
        self.blocked_ips[client_id] = blocked_until
        
        # Update client profile
        if client_id in self.client_profiles:
            profile = self.client_profiles[client_id]
            profile.is_blocked = True
            profile.blocked_until = blocked_until
            profile.notes.append(f"Blocked: {reason}")
        
        logger.warning(
            f"Client blocked: {reason}",
            extra={
                "event": "client_blocked",
                "client_id": hashlib.sha256(client_id.encode()).hexdigest()[:16],
                "duration_seconds": duration_seconds,
                "blocked_until": blocked_until.isoformat(),
                "reason": reason,
                "security_event": True,
                "alert_priority": "high"
            }
        )
        
        # Record security event
        metrics_collector.record_security_event(
            event_type="client_blocked",
            severity="high",
            details={
                "client_id": hashlib.sha256(client_id.encode()).hexdigest()[:16],
                "duration_seconds": duration_seconds,
                "reason": reason
            }
        )
    
    def get_client_threat_level(self, client_id: str) -> ThreatLevel:
        """Get client's current threat level."""
        if client_id in self.client_profiles:
            return self.client_profiles[client_id].threat_level
        return ThreatLevel.LOW
    
    def get_statistics(self) -> Dict:
        """Get comprehensive rate limiting statistics."""
        total_clients = len(self.client_profiles)
        blocked_clients = len(self.blocked_ips)
        bot_clients = sum(1 for p in self.client_profiles.values() if p.is_bot)
        
        threat_distribution = {level.value: 0 for level in ThreatLevel}
        for profile in self.client_profiles.values():
            threat_distribution[profile.threat_level.value] += 1
        
        return {
            "total_clients": total_clients,
            "blocked_clients": blocked_clients,
            "bot_clients": bot_clients,
            "threat_distribution": threat_distribution,
            "recent_patterns": len(self.request_patterns),
            "active_rules": len([r for r in self.rules if r.enabled])
        }
    
    def _get_rule_by_name(self, rule_name: str) -> Optional[RateLimitRule]:
        """Get rate limit rule by name."""
        for rule in self.rules:
            if rule.name == rule_name:
                return rule
        return None
    
    def _check_rule_limit(self, client_id: str, endpoint: str, rule: RateLimitRule) -> Tuple[bool, Dict]:
        """Check specific rule against client/endpoint."""
        current_time = time.time()
        key = f"{client_id}:{endpoint}:{rule.name}"
        
        count, window_start = self.request_counts[client_id][key]
        
        # Reset window if expired
        if current_time - window_start >= rule.window_seconds:
            count = 0
            window_start = current_time
        
        # Increment count
        count += 1
        self.request_counts[client_id][key] = (count, window_start)
        
        # Check limit (including burst allowance)
        effective_limit = rule.max_requests + rule.burst_allowance
        is_allowed = count <= effective_limit
        
        limit_info = {
            "rule_name": rule.name,
            "limit": rule.max_requests,
            "burst_allowance": rule.burst_allowance,
            "current_count": count,
            "remaining": max(0, effective_limit - count),
            "reset_time": int(window_start + rule.window_seconds),
            "window": rule.window_seconds
        }
        
        return is_allowed, limit_info
    
    def _update_client_profile(self, client_id: str, endpoint: str, is_allowed: bool) -> None:
        """Update client behavior profile."""
        if client_id not in self.client_profiles:
            self.client_profiles[client_id] = ClientProfile(
                client_id=client_id,
                first_seen=datetime.now(timezone.utc)
            )
        
        profile = self.client_profiles[client_id]
        if not is_allowed:
            profile.blocked_requests += 1
    
    def _analyze_request_pattern(self, client_id: str, endpoint: str) -> None:
        """Analyze request patterns for suspicious behavior."""
        if client_id not in self.client_profiles:
            return
        
        profile = self.client_profiles[client_id]
        
        # Check for rapid-fire requests
        recent_requests = [
            p for p in self.request_patterns
            if p.client_id == client_id and 
            (datetime.now(timezone.utc) - p.timestamp).total_seconds() < 60
        ]
        
        if len(recent_requests) > 30:  # More than 30 requests per minute
            self._escalate_threat(client_id, "rapid_requests", ThreatLevel.MEDIUM)
        
        # Check for scanning behavior (many unique endpoints)
        if len(profile.unique_endpoints) > 20:
            self._escalate_threat(client_id, "endpoint_scanning", ThreatLevel.MEDIUM)
    
    def _detect_bot_behavior(self, client_id: str, user_agent: str, endpoint: str) -> None:
        """Detect bot behavior patterns."""
        user_agent_lower = user_agent.lower()
        
        # Check for bot user agents
        if any(bot_pattern in user_agent_lower for bot_pattern in self.bot_user_agents):
            if client_id in self.client_profiles:
                self.client_profiles[client_id].is_bot = True
                self.client_profiles[client_id].notes.append(f"Bot detected: {user_agent}")
        
        # Check for missing or suspicious user agents
        if not user_agent or len(user_agent) < 10:
            self._escalate_threat(client_id, "suspicious_user_agent", ThreatLevel.LOW)
    
    def _detect_attack_patterns(self, client_id: str, endpoint: str, user_agent: str) -> None:
        """Detect attack patterns in requests."""
        combined_input = f"{endpoint} {user_agent}".lower()
        
        for attack_type, config in self.attack_patterns.items():
            if "patterns" in config:
                for pattern in config["patterns"]:
                    if re.search(pattern, combined_input, re.IGNORECASE):
                        self._handle_attack_detection(
                            client_id, attack_type, config["threat_level"], 
                            config["block_duration"]
                        )
                        break
    
    def _handle_attack_detection(self, client_id: str, attack_type: str, 
                                threat_level: ThreatLevel, block_duration: int) -> None:
        """Handle detected attack patterns."""
        logger.warning(
            f"Attack pattern detected: {attack_type}",
            extra={
                "event": "attack_pattern_detected",
                "attack_type": attack_type,
                "client_id": hashlib.sha256(client_id.encode()).hexdigest()[:16],
                "threat_level": threat_level.value,
                "security_event": True,
                "alert_priority": "high"
            }
        )
        
        # Escalate threat and potentially block
        self._escalate_threat(client_id, attack_type, threat_level)
        
        if threat_level in [ThreatLevel.HIGH, ThreatLevel.CRITICAL]:
            self.block_client(client_id, block_duration, f"Attack detected: {attack_type}")
    
    def _escalate_threat(self, client_id: str, reason: str, threat_level: ThreatLevel) -> None:
        """Escalate threat level for a client."""
        if client_id not in self.client_profiles:
            return
        
        profile = self.client_profiles[client_id]
        
        # Increase threat score
        threat_increases = {
            ThreatLevel.LOW: 10,
            ThreatLevel.MEDIUM: 25,
            ThreatLevel.HIGH: 50,
            ThreatLevel.CRITICAL: 100
        }
        
        profile.threat_score += threat_increases[threat_level]
        profile.notes.append(f"Threat escalated: {reason} ({threat_level.value})")
        
        # Update threat level based on score
        if profile.threat_score >= 100:
            profile.threat_level = ThreatLevel.CRITICAL
        elif profile.threat_score >= 50:
            profile.threat_level = ThreatLevel.HIGH
        elif profile.threat_score >= 25:
            profile.threat_level = ThreatLevel.MEDIUM
        else:
            profile.threat_level = ThreatLevel.LOW
        
        logger.info(
            f"Threat escalated for client",
            extra={
                "event": "threat_escalated",
                "client_id": hashlib.sha256(client_id.encode()).hexdigest()[:16],
                "reason": reason,
                "new_threat_level": profile.threat_level.value,
                "threat_score": profile.threat_score,
                "security_event": True
            }
        )
    
    def _update_threat_score(self, client_id: str) -> None:
        """Update threat score based on overall behavior."""
        if client_id not in self.client_profiles:
            return
        
        profile = self.client_profiles[client_id]
        
        # Calculate threat score based on behavior
        error_rate = profile.failed_requests / max(profile.total_requests, 1)
        block_rate = profile.blocked_requests / max(profile.total_requests, 1)
        
        # Threat factors
        if error_rate > 0.5:  # More than 50% errors
            profile.threat_score += 5
        
        if block_rate > 0.1:  # More than 10% blocked
            profile.threat_score += 10
        
        if profile.is_bot and len(profile.unique_endpoints) > 10:
            profile.threat_score += 15  # Scanning bot
        
        # Decay threat score over time
        time_since_first = (datetime.now(timezone.utc) - profile.first_seen).total_seconds()
        decay_factor = max(0.1, 1.0 - (time_since_first / (7 * 24 * 3600)))  # Decay over 7 days
        profile.threat_score *= decay_factor


# Global rate limiter instance
advanced_rate_limiter = AdvancedRateLimiter()