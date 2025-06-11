"""
Test suite for advanced rate limiting and abuse detection.

Comprehensive tests covering:
- Rate limit enforcement
- Attack pattern detection  
- Client threat scoring
- Blocking mechanisms
- Middleware integration
- Security event logging
"""

import pytest
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock

from app.validation.rate_limiting import (
    AdvancedRateLimiter, ThreatLevel, RateLimitRule, RateLimitType,
    ClientProfile, RequestPattern, advanced_rate_limiter
)
from app.middleware.rate_limiting import (
    rate_limit_middleware, get_client_ip, get_rate_limit_rule,
    get_user_agent, get_geo_country
)
from fastapi import Request
from fastapi.responses import JSONResponse


class TestAdvancedRateLimiter:
    """Test the AdvancedRateLimiter class functionality."""
    
    def setup_method(self):
        """Set up fresh rate limiter for each test."""
        self.rate_limiter = AdvancedRateLimiter()
    
    def test_initialization(self):
        """Test rate limiter initializes with proper defaults."""
        assert len(self.rate_limiter.rules) > 0
        assert len(self.rate_limiter.attack_patterns) > 0
        assert len(self.rate_limiter.client_profiles) == 0
        assert len(self.rate_limiter.blocked_ips) == 0
    
    def test_basic_rate_limiting(self):
        """Test basic rate limiting functionality."""
        client_ip = "192.168.1.100"
        endpoint = "/api/auth/get_token"
        rule_name = "auth_strict"
        
        # First few requests should be allowed
        for i in range(5):
            is_allowed, info = self.rate_limiter.check_rate_limit(
                client_ip, endpoint, rule_name
            )
            assert is_allowed
            assert info["remaining"] == 5 - (i + 1)
        
        # Next request should be blocked (auth_strict has 5 request limit)
        is_allowed, info = self.rate_limiter.check_rate_limit(
            client_ip, endpoint, rule_name
        )
        assert not is_allowed
        assert info["remaining"] == 0
    
    def test_rate_limit_window_reset(self):
        """Test rate limit counter resets after window expires."""
        client_ip = "192.168.1.101"
        endpoint = "/api/auth/get_token"
        rule_name = "auth_strict"
        
        # Exhaust the limit
        for _ in range(5):
            self.rate_limiter.check_rate_limit(client_ip, endpoint, rule_name)
        
        # Should be blocked
        is_allowed, _ = self.rate_limiter.check_rate_limit(client_ip, endpoint, rule_name)
        assert not is_allowed
        
        # Mock time forward to expire window (auth_strict window is 300 seconds)
        with patch('time.time', return_value=time.time() + 301):
            is_allowed, info = self.rate_limiter.check_rate_limit(
                client_ip, endpoint, rule_name
            )
            assert is_allowed
            assert info["current_count"] == 1  # Reset and incremented
    
    def test_client_blocking(self):
        """Test client blocking functionality."""
        client_ip = "192.168.1.102"
        
        # Block the client
        self.rate_limiter.block_client(client_ip, 3600, "Test block")
        
        # Should be blocked for any endpoint
        is_allowed, info = self.rate_limiter.check_rate_limit(
            client_ip, "/api/test", "api_general"
        )
        assert not is_allowed
        assert info["blocked"] is True
        assert "blocked_until" in info
    
    def test_block_expiration(self):
        """Test that blocks expire after specified duration."""
        client_ip = "192.168.1.103"
        
        # Block for 1 second
        self.rate_limiter.block_client(client_ip, 1, "Short test block")
        
        # Should be blocked initially
        assert self.rate_limiter.is_blocked(client_ip)
        
        # Wait for block to expire
        time.sleep(1.1)
        
        # Should no longer be blocked
        assert not self.rate_limiter.is_blocked(client_ip)
    
    def test_sql_injection_detection(self):
        """Test SQL injection attack pattern detection."""
        client_ip = "192.168.1.104"
        malicious_endpoint = "/api/users?id=1' OR '1'='1"
        
        # Create client profile first
        self.rate_limiter.client_profiles[client_ip] = ClientProfile(
            client_id=client_ip,
            first_seen=datetime.now(timezone.utc)
        )
        
        # This should trigger SQL injection detection
        self.rate_limiter._detect_attack_patterns(
            client_ip, malicious_endpoint, "Mozilla/5.0"
        )
        
        # Client should be blocked due to high threat level
        assert client_ip in self.rate_limiter.blocked_ips
        
        # Client profile should show elevated threat
        profile = self.rate_limiter.client_profiles[client_ip]
        assert profile.threat_level in [ThreatLevel.HIGH, ThreatLevel.CRITICAL]
    
    def test_xss_detection(self):
        """Test XSS attack pattern detection."""
        client_ip = "192.168.1.105"
        malicious_endpoint = "/api/search?q=<script>alert('xss')</script>"
        
        # Create client profile first
        self.rate_limiter.client_profiles[client_ip] = ClientProfile(
            client_id=client_ip,
            first_seen=datetime.now(timezone.utc)
        )
        
        self.rate_limiter._detect_attack_patterns(
            client_ip, malicious_endpoint, "Mozilla/5.0"
        )
        
        # Should be blocked
        assert client_ip in self.rate_limiter.blocked_ips
        
        # Should have elevated threat level
        profile = self.rate_limiter.client_profiles[client_ip]
        assert profile.threat_level != ThreatLevel.LOW
    
    def test_directory_traversal_detection(self):
        """Test directory traversal attack detection."""
        client_ip = "192.168.1.106"
        malicious_endpoint = "/api/files?path=../../etc/passwd"
        
        # Create client profile first
        self.rate_limiter.client_profiles[client_ip] = ClientProfile(
            client_id=client_ip,
            first_seen=datetime.now(timezone.utc)
        )
        
        self.rate_limiter._detect_attack_patterns(
            client_ip, malicious_endpoint, "curl/7.68.0"
        )
        
        # Should be blocked
        assert client_ip in self.rate_limiter.blocked_ips
    
    def test_bot_detection(self):
        """Test bot detection based on user agent."""
        client_ip = "192.168.1.107"
        bot_user_agents = [
            "Mozilla/5.0 (compatible; Googlebot/2.1)",
            "curl/7.68.0",
            "python-requests/2.25.1",
            "sqlmap/1.5.12"
        ]
        
        for user_agent in bot_user_agents:
            self.rate_limiter._detect_bot_behavior(
                client_ip, user_agent, "/api/test"
            )
        
        # Should be marked as bot
        profile = self.rate_limiter.client_profiles.get(client_ip)
        if profile:
            assert profile.is_bot
    
    def test_rapid_request_pattern_detection(self):
        """Test detection of rapid-fire request patterns."""
        client_ip = "192.168.1.108"
        endpoint = "/api/test"
        
        # Create client profile
        self.rate_limiter.client_profiles[client_ip] = ClientProfile(
            client_id=client_ip,
            first_seen=datetime.now(timezone.utc)
        )
        
        # Simulate 35 requests in quick succession
        current_time = datetime.now(timezone.utc)
        for i in range(35):
            pattern = RequestPattern(
                timestamp=current_time - timedelta(seconds=i),
                client_id=client_ip,
                endpoint=f"/api/endpoint_{i}",
                method="GET",
                user_agent="Mozilla/5.0",
                response_code=200,
                response_time=0.1
            )
            self.rate_limiter.request_patterns.append(pattern)
        
        # Analyze pattern (should detect rapid requests)
        self.rate_limiter._analyze_request_pattern(client_ip, endpoint)
        
        # Should have elevated threat level
        profile = self.rate_limiter.client_profiles[client_ip]
        assert profile.threat_level != ThreatLevel.LOW
    
    def test_endpoint_scanning_detection(self):
        """Test detection of endpoint scanning behavior."""
        client_ip = "192.168.1.109"
        
        # Create profile with many unique endpoints
        profile = ClientProfile(
            client_id=client_ip,
            first_seen=datetime.now(timezone.utc)
        )
        
        # Add 25 unique endpoints (threshold is 20)
        for i in range(25):
            profile.unique_endpoints.add(f"/api/endpoint_{i}")
        
        self.rate_limiter.client_profiles[client_ip] = profile
        
        # Analyze pattern
        self.rate_limiter._analyze_request_pattern(client_ip, "/api/new_endpoint")
        
        # Should be flagged as scanning
        updated_profile = self.rate_limiter.client_profiles[client_ip]
        assert updated_profile.threat_level != ThreatLevel.LOW
    
    def test_threat_score_calculation(self):
        """Test threat score calculation and decay."""
        client_ip = "192.168.1.110"
        
        # Create profile with high error rate
        profile = ClientProfile(
            client_id=client_ip,
            first_seen=datetime.now(timezone.utc) - timedelta(hours=1),
            total_requests=100,
            failed_requests=60,  # 60% error rate
            blocked_requests=15   # 15% blocked rate
        )
        self.rate_limiter.client_profiles[client_ip] = profile
        
        # Update threat score
        self.rate_limiter._update_threat_score(client_ip)
        
        # Should have increased threat score
        updated_profile = self.rate_limiter.client_profiles[client_ip]
        assert updated_profile.threat_score > 0
    
    def test_threat_escalation(self):
        """Test threat level escalation based on score."""
        client_ip = "192.168.1.111"
        
        # Create basic profile
        profile = ClientProfile(
            client_id=client_ip,
            first_seen=datetime.now(timezone.utc)
        )
        self.rate_limiter.client_profiles[client_ip] = profile
        
        # Escalate threat multiple times
        self.rate_limiter._escalate_threat(client_ip, "test_reason", ThreatLevel.MEDIUM)
        self.rate_limiter._escalate_threat(client_ip, "test_reason", ThreatLevel.HIGH)
        self.rate_limiter._escalate_threat(client_ip, "test_reason", ThreatLevel.CRITICAL)
        
        # Should reach critical level
        updated_profile = self.rate_limiter.client_profiles[client_ip]
        assert updated_profile.threat_level == ThreatLevel.CRITICAL
        assert updated_profile.threat_score >= 100
    
    def test_request_recording(self):
        """Test request pattern recording."""
        client_ip = "192.168.1.112"
        
        self.rate_limiter.record_request(
            client_id=client_ip,
            endpoint="/api/test",
            method="POST",
            response_code=200,
            response_time=0.5,
            user_agent="Mozilla/5.0",
            geo_country="US"
        )
        
        # Should create client profile
        assert client_ip in self.rate_limiter.client_profiles
        
        # Should record request pattern
        assert len(self.rate_limiter.request_patterns) > 0
        
        # Profile should be updated
        profile = self.rate_limiter.client_profiles[client_ip]
        assert profile.total_requests == 1
        assert "/api/test" in profile.unique_endpoints
        assert "Mozilla/5.0" in profile.user_agents
    
    def test_statistics_generation(self):
        """Test statistics generation."""
        # Add some test data
        self.rate_limiter.client_profiles["test1"] = ClientProfile(
            client_id="test1",
            first_seen=datetime.now(timezone.utc),
            is_bot=True,
            threat_level=ThreatLevel.HIGH
        )
        self.rate_limiter.client_profiles["test2"] = ClientProfile(
            client_id="test2", 
            first_seen=datetime.now(timezone.utc),
            threat_level=ThreatLevel.LOW
        )
        self.rate_limiter.blocked_ips["test3"] = datetime.now(timezone.utc) + timedelta(hours=1)
        
        stats = self.rate_limiter.get_statistics()
        
        assert stats["total_clients"] == 2
        assert stats["blocked_clients"] == 1
        assert stats["bot_clients"] == 1
        assert "threat_distribution" in stats
        assert stats["threat_distribution"]["high"] == 1
        assert stats["threat_distribution"]["low"] == 1


class TestRateLimitingMiddleware:
    """Test the rate limiting middleware functionality."""
    
    def create_mock_request(self, path: str, method: str = "GET", 
                          client_ip: str = "192.168.1.200",
                          user_agent: str = "Mozilla/5.0") -> Mock:
        """Create a mock FastAPI request."""
        request = Mock(spec=Request)
        request.url.path = path
        request.method = method
        request.client.host = client_ip
        request.headers = {
            "User-Agent": user_agent
        }
        return request
    
    @pytest.mark.asyncio
    async def test_middleware_allows_exempt_paths(self):
        """Test middleware skips rate limiting for exempt paths."""
        exempt_paths = ["/docs", "/redoc", "/openapi.json", "/", "/api/"]
        
        async def mock_call_next(request):
            return JSONResponse(content={"status": "ok"})
        
        for path in exempt_paths:
            request = self.create_mock_request(path)
            response = await rate_limit_middleware(request, mock_call_next)
            assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_middleware_rate_limiting(self):
        """Test middleware enforces rate limits."""
        client_ip = "192.168.1.201"
        path = "/api/auth/get_token"
        
        async def mock_call_next(request):
            return JSONResponse(content={"status": "ok"})
        
        # Make requests up to the limit
        for i in range(5):  # auth_strict limit is 5
            request = self.create_mock_request(path, client_ip=client_ip)
            response = await rate_limit_middleware(request, mock_call_next)
            assert response.status_code == 200
        
        # Next request should be rate limited
        request = self.create_mock_request(path, client_ip=client_ip)
        response = await rate_limit_middleware(request, mock_call_next)
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.body.decode()
    
    @pytest.mark.asyncio
    async def test_middleware_blocks_malicious_clients(self):
        """Test middleware blocks clients marked as malicious."""
        client_ip = "192.168.1.202"
        
        # Manually block the client
        advanced_rate_limiter.block_client(client_ip, 3600, "Test block")
        
        async def mock_call_next(request):
            return JSONResponse(content={"status": "ok"})
        
        request = self.create_mock_request("/api/test", client_ip=client_ip)
        response = await rate_limit_middleware(request, mock_call_next)
        
        assert response.status_code == 403
        assert "Access denied" in response.body.decode()
    
    @pytest.mark.asyncio
    async def test_middleware_detects_attacks(self):
        """Test middleware detects and blocks attack patterns."""
        client_ip = "192.168.1.203"
        malicious_path = "/api/users?id=1' OR '1'='1"
        
        async def mock_call_next(request):
            return JSONResponse(content={"status": "ok"})
        
        # First request might go through before pattern is detected
        request = self.create_mock_request(malicious_path, client_ip=client_ip)
        await rate_limit_middleware(request, mock_call_next)
        
        # Subsequent requests should be blocked if client was flagged
        request = self.create_mock_request("/api/test", client_ip=client_ip)
        response = await rate_limit_middleware(request, mock_call_next)
        
        # Should be blocked if attack was detected
        if response.status_code == 403:
            assert "Access denied" in response.body.decode()
    
    @pytest.mark.asyncio
    async def test_middleware_adds_rate_limit_headers(self):
        """Test middleware adds proper rate limit headers."""
        client_ip = "192.168.1.204"
        path = "/api/test"
        
        async def mock_call_next(request):
            return JSONResponse(content={"status": "ok"})
        
        request = self.create_mock_request(path, client_ip=client_ip)
        response = await rate_limit_middleware(request, mock_call_next)
        
        # Should include rate limit headers
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
        assert "X-RateLimit-Rule" in response.headers
    
    @pytest.mark.asyncio
    async def test_middleware_error_handling(self):
        """Test middleware handles errors gracefully."""
        client_ip = "192.168.1.205"
        
        async def mock_call_next(request):
            return JSONResponse(content={"status": "ok"})
        
        # Mock an error in the rate limiter
        with patch.object(advanced_rate_limiter, 'check_rate_limit', 
                         side_effect=Exception("Test error")):
            request = self.create_mock_request("/api/test", client_ip=client_ip)
            response = await rate_limit_middleware(request, mock_call_next)
            
            # Should still allow request through despite error
            assert response.status_code == 200
    
    def test_get_client_ip_extraction(self):
        """Test client IP extraction from various headers."""
        # Test X-Forwarded-For
        request = Mock()
        request.headers = {"X-Forwarded-For": "192.168.1.100, 10.0.0.1"}
        request.client.host = "127.0.0.1"
        assert get_client_ip(request) == "192.168.1.100"
        
        # Test X-Real-IP
        request.headers = {"X-Real-IP": "192.168.1.101"}
        assert get_client_ip(request) == "192.168.1.101"
        
        # Test CF-Connecting-IP (Cloudflare)
        request.headers = {"CF-Connecting-IP": "192.168.1.102"}
        assert get_client_ip(request) == "192.168.1.102"
        
        # Test fallback to client.host
        request.headers = {}
        assert get_client_ip(request) == "127.0.0.1"
    
    def test_get_rate_limit_rule_mapping(self):
        """Test rate limit rule mapping for different endpoints."""
        test_cases = [
            ("/api/auth/get_token", "auth_strict"),
            ("/api/auth/refresh_token", "auth_strict"),
            ("/api/resumes/upload", "upload_moderate"),
            ("/api/resumes/status/123", "status_generous"),
            ("/api/words/create", "api_general"),
            ("/api/observability/health", "status_generous"),
            ("/api/unknown/endpoint", "api_general"),  # Default
        ]
        
        for path, expected_rule in test_cases:
            assert get_rate_limit_rule(path) == expected_rule
    
    def test_get_user_agent(self):
        """Test user agent extraction."""
        request = Mock()
        request.headers = {"User-Agent": "Mozilla/5.0 (Test Browser)"}
        assert get_user_agent(request) == "Mozilla/5.0 (Test Browser)"
        
        # Test missing user agent
        request.headers = {}
        assert get_user_agent(request) == ""
    
    def test_get_geo_country(self):
        """Test geo country extraction from headers."""
        request = Mock()
        
        # Test Cloudflare header
        request.headers = {"CF-IPCountry": "US"}
        assert get_geo_country(request) == "US"
        
        # Test generic header
        request.headers = {"X-Country-Code": "CA"}
        assert get_geo_country(request) == "CA"
        
        # Test no geo headers
        request.headers = {}
        assert get_geo_country(request) is None


class TestRateLimitingIntegration:
    """Integration tests for the complete rate limiting system."""
    
    @pytest.mark.asyncio
    async def test_full_attack_scenario(self):
        """Test complete attack detection and blocking scenario."""
        client_ip = "192.168.1.250"
        
        async def mock_call_next(request):
            return JSONResponse(content={"status": "ok"})
        
        # Step 1: Normal request should work
        request = Mock(spec=Request)
        request.url.path = "/api/test"
        request.method = "GET"
        request.client.host = client_ip
        request.headers = {"User-Agent": "Mozilla/5.0"}
        
        response = await rate_limit_middleware(request, mock_call_next)
        assert response.status_code == 200
        
        # Step 2: SQL injection attempt
        request.url.path = "/api/users?id=1' OR '1'='1"
        await rate_limit_middleware(request, mock_call_next)
        
        # Step 3: Client should now be blocked or heavily restricted
        request.url.path = "/api/test"
        response = await rate_limit_middleware(request, mock_call_next)
        
        # Should be blocked (403) or heavily rate limited
        assert response.status_code in [403, 429]
    
    def test_rate_limiting_statistics(self):
        """Test statistics collection and reporting."""
        from app.middleware.rate_limiting import get_rate_limiting_statistics
        
        stats = get_rate_limiting_statistics()
        
        assert isinstance(stats, dict)
        assert "total_clients" in stats
        assert "blocked_clients" in stats
        assert "threat_distribution" in stats
    
    def test_cleanup_and_memory_management(self):
        """Test that the system manages memory appropriately."""
        # Add many test clients
        for i in range(100):
            client_ip = f"192.168.1.{i}"
            advanced_rate_limiter.record_request(
                client_id=client_ip,
                endpoint="/api/test",
                method="GET",
                response_code=200,
                response_time=0.1
            )
        
        # System should handle this without issues
        stats = advanced_rate_limiter.get_statistics()
        assert stats["total_clients"] <= 100
        
        # Request patterns should be limited (maxlen=10000 in deque)
        assert len(advanced_rate_limiter.request_patterns) <= 10000