"""
Tests for rate limiting middleware.
"""

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.middleware.rate_limiting import cleanup_old_entries, request_counts


class TestRateLimitingMiddleware:
    """Test cases for rate limiting middleware."""
    
    def setup_method(self):
        """Set up test client and clear rate limit storage."""
        self.client = TestClient(app)
        # Clear rate limiting storage before each test
        request_counts.clear()
    
    def test_upload_endpoint_rate_limiting(self):
        """Test rate limiting on resume upload endpoint."""
        # Upload endpoint allows 10 requests per 5 minutes
        # Make 10 requests (should all succeed)
        for i in range(10):
            response = self.client.post("/api/resumes/upload")
            # Expect 422 for missing file, not rate limit error
            assert response.status_code == 422
            assert "X-RateLimit-Limit" in response.headers
            assert response.headers["X-RateLimit-Limit"] == "10"
            assert response.headers["X-RateLimit-Remaining"] == str(9 - i)
        
        # 11th request should be rate limited
        response = self.client.post("/api/resumes/upload")
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["detail"]
        assert "X-RateLimit-Limit" in response.headers
        assert "Retry-After" in response.headers
    
    def test_status_endpoint_rate_limiting(self):
        """Test rate limiting on status endpoint."""
        # Status endpoint allows 60 requests per minute
        task_id = "test-task-123"
        
        # Make 60 requests (should all succeed)
        for i in range(60):
            response = self.client.get(f"/api/resumes/status/{task_id}")
            # Expect various responses (200 or 404), not rate limit error
            assert response.status_code in [200, 404, 500]
            assert "X-RateLimit-Limit" in response.headers
            assert response.headers["X-RateLimit-Limit"] == "60"
            assert response.headers["X-RateLimit-Remaining"] == str(59 - i)
        
        # 61st request should be rate limited
        response = self.client.get(f"/api/resumes/status/{task_id}")
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["detail"]
    
    def test_different_endpoints_separate_limits(self):
        """Test that different endpoints have separate rate limits."""
        # Make requests to upload endpoint
        for i in range(5):
            response = self.client.post("/api/resumes/upload")
            assert response.status_code == 422  # Missing file
            assert response.headers["X-RateLimit-Remaining"] == str(9 - i)
        
        # Make requests to status endpoint - should have separate limit
        response = self.client.get("/api/resumes/status/test-task")
        assert response.status_code in [200, 404, 500]  # Not rate limited
        assert response.headers["X-RateLimit-Limit"] == "60"
        assert response.headers["X-RateLimit-Remaining"] == "59"
    
    def test_rate_limit_headers_present(self):
        """Test that rate limit headers are always present."""
        response = self.client.get("/api/resumes/status/test-task")
        
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
        
        # Verify header values
        assert int(response.headers["X-RateLimit-Limit"]) > 0
        assert int(response.headers["X-RateLimit-Remaining"]) >= 0
        assert int(response.headers["X-RateLimit-Reset"]) > int(time.time())
    
    def test_rate_limit_reset_after_window(self):
        """Test that rate limits reset after the time window."""
        # Make some requests to consume limit
        for i in range(3):
            response = self.client.post("/api/resumes/upload")
            assert response.status_code == 422
        
        # Verify remaining count is reduced
        response = self.client.post("/api/resumes/upload")
        assert response.headers["X-RateLimit-Remaining"] == "6"
        
        # Mock time to simulate window expiration
        with patch('app.middleware.rate_limiting.time.time', return_value=time.time() + 301):
            response = self.client.post("/api/resumes/upload")
            # Should be reset to full limit minus this request
            assert response.headers["X-RateLimit-Remaining"] == "9"
    
    def test_different_ips_separate_limits(self):
        """Test that different IP addresses have separate rate limits."""
        # Default request (simulated IP)
        for i in range(5):
            response = self.client.post("/api/resumes/upload")
            assert response.status_code == 422
        
        # Simulate request from different IP
        with patch('app.middleware.rate_limiting.get_client_ip', return_value='192.168.1.100'):
            response = self.client.post("/api/resumes/upload")
            # Should have full limit available
            assert response.headers["X-RateLimit-Remaining"] == "9"
    
    def test_health_endpoints_not_rate_limited(self):
        """Test that health check endpoints are not rate limited."""
        # Make many requests to docs endpoint
        for i in range(20):
            response = self.client.get("/docs")
            assert response.status_code == 200
            # Should not have rate limit headers
            assert "X-RateLimit-Limit" not in response.headers
    
    def test_cleanup_old_entries(self):
        """Test cleanup of expired rate limit entries."""
        # Add some test data to rate limit storage
        current_time = time.time()
        old_time = current_time - 400  # 400 seconds ago (older than 5 minute window)
        
        request_counts["192.168.1.1"]["/api/resumes/upload"] = (5, old_time)
        request_counts["192.168.1.2"]["/api/resumes/status/test"] = (10, current_time)
        
        # Run cleanup
        cleanup_old_entries()
        
        # Old entry should be removed
        assert "192.168.1.1" not in request_counts
        # Recent entry should remain
        assert "192.168.1.2" in request_counts
    
    def test_forwarded_ip_header_handling(self):
        """Test handling of X-Forwarded-For and X-Real-IP headers."""
        # Test with X-Forwarded-For header
        headers = {"X-Forwarded-For": "203.0.113.1, 192.168.1.1"}
        response = self.client.post("/api/resumes/upload", headers=headers)
        assert response.status_code == 422
        
        # Make more requests with same forwarded IP
        for i in range(9):
            response = self.client.post("/api/resumes/upload", headers=headers)
            assert response.status_code == 422
        
        # Should be rate limited now
        response = self.client.post("/api/resumes/upload", headers=headers)
        assert response.status_code == 429
        
        # Test with X-Real-IP header (without X-Forwarded-For)
        real_ip_headers = {"X-Real-IP": "203.0.113.2"}
        response = self.client.post("/api/resumes/upload", headers=real_ip_headers)
        # Should have fresh limit
        assert response.status_code == 422
        assert response.headers["X-RateLimit-Remaining"] == "9"
    
    def test_rate_limit_response_format(self):
        """Test the format of rate limit error response."""
        # Exhaust rate limit
        for i in range(10):
            self.client.post("/api/resumes/upload")
        
        # Get rate limited response
        response = self.client.post("/api/resumes/upload")
        
        assert response.status_code == 429
        response_data = response.json()
        
        # Verify response structure
        assert "detail" in response_data
        assert "limit" in response_data
        assert "window" in response_data
        assert "reset_time" in response_data
        
        # Verify response values
        assert response_data["limit"] == 10
        assert response_data["window"] == 300
        assert response_data["reset_time"] > int(time.time())
        assert "Rate limit exceeded" in response_data["detail"]
    
    def test_middleware_error_handling(self):
        """Test that middleware errors don't break the application."""
        # Mock an error in rate limiting logic
        with patch('app.middleware.rate_limiting.is_rate_limited', side_effect=Exception("Rate limit error")):
            response = self.client.get("/api/resumes/status/test-task")
            # Should still process the request despite rate limiting error
            assert response.status_code in [200, 404, 500]
    
    def test_cors_headers_present_with_rate_limiting(self):
        """Test that CORS headers are present along with rate limiting headers."""
        # Test with a GET request to status endpoint (which supports CORS)
        response = self.client.get("/api/resumes/status/test-task", 
                                 headers={"Origin": "http://localhost:3000"})
        
        # Should have rate limiting headers
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
        
        # Make an OPTIONS request to test CORS preflight
        response = self.client.options("/api/", 
                                     headers={"Origin": "http://localhost:3000",
                                             "Access-Control-Request-Method": "POST"})
        
        # Should have CORS headers for preflight
        if "Access-Control-Allow-Origin" in response.headers:
            assert "Access-Control-Allow-Methods" in response.headers
    
    def test_multiple_status_endpoints_same_limit(self):
        """Test that different task IDs on status endpoint share the same rate limit."""
        # Make requests to different task IDs
        response1 = self.client.get("/api/resumes/status/task-1")
        response2 = self.client.get("/api/resumes/status/task-2")
        response3 = self.client.get("/api/resumes/status/task-3")
        
        # All should count against the same rate limit
        assert response1.headers["X-RateLimit-Remaining"] == "59"
        assert response2.headers["X-RateLimit-Remaining"] == "58"
        assert response3.headers["X-RateLimit-Remaining"] == "57"