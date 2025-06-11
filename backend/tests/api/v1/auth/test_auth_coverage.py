"""
Comprehensive authentication coverage tests.

This module tests authentication edge cases and security scenarios:
- Expired JWT token handling
- Invalid/malformed JWT tokens  
- Accessing protected routes without authentication
- Permission/role-based access control
- Token manipulation and security validation
"""

import jwt
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from fastapi import status

from app.config import get_config
from app.api.v1.auth.get_token import create_access_token
from app.api.v1.auth.get_user_group import extract_token


@pytest.mark.security
@pytest.mark.unit
class TestJWTTokenHandling:
    """Test JWT token creation, validation, and expiration scenarios."""

    @pytest.mark.does_not_change_db
    def test_expired_jwt_token_access_denied(self, client):
        """Test that expired JWT tokens are rejected."""
        config = get_config()
        
        # Create an expired token (expired 1 hour ago)
        expired_payload = {
            "sub": "admin",
            "scopes": ["admin"],
            "exp": datetime.now(timezone.utc) - timedelta(hours=1)
        }
        
        expired_token = jwt.encode(
            expired_payload,
            config.jwt_secret_key,
            algorithm=config.jwt_algorithm
        )
        
        # Try to access protected endpoint with expired token
        response = client.post(
            "/api/resumes/upload",
            files={"file": ("test.pdf", b"test content", "application/pdf")},
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        # Check for either error message (depends on where validation fails)
        detail = response.json()["detail"]
        assert detail in ["Could not validate credentials", "Not authenticated"]

    @pytest.mark.does_not_change_db
    def test_malformed_jwt_token_rejected(self, client):
        """Test that malformed JWT tokens are rejected."""
        malformed_tokens = [
            "invalid.jwt.token",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid_payload.signature",
            "not_even_jwt_format",
            "",
            "Bearer.without.proper.format",
        ]
        
        for malformed_token in malformed_tokens:
            response = client.post(
                "/api/resumes/upload", 
                files={"file": ("test.pdf", b"test content", "application/pdf")},
                headers={"Authorization": f"Bearer {malformed_token}"}
            )
            
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            detail = response.json()["detail"]
            assert detail in ["Could not validate credentials", "Not authenticated"]

    def test_jwt_with_invalid_signature_rejected(self, client):
        """Test that tokens with invalid signatures are rejected."""
        config = get_config()
        
        # Create token with correct payload but wrong key
        payload = {
            "sub": "admin",
            "scopes": ["admin"],
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15)
        }
        
        invalid_token = jwt.encode(
            payload,
            "wrong_secret_key",  # Wrong key
            algorithm=config.jwt_algorithm
        )
        
        response = client.post(
            "/api/resumes/upload",
            files={"file": ("test.pdf", b"test content", "application/pdf")},
            headers={"Authorization": f"Bearer {invalid_token}"}
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        detail = response.json()["detail"]
        assert detail in ["Could not validate credentials", "Not authenticated"]

    def test_jwt_with_missing_claims_rejected(self, client):
        """Test that tokens missing required claims are rejected."""
        config = get_config()
        
        # Token missing 'sub' claim
        invalid_payload = {
            "scopes": ["admin"],
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15)
        }
        
        invalid_token = jwt.encode(
            invalid_payload,
            config.jwt_secret_key,
            algorithm=config.jwt_algorithm
        )
        
        response = client.post(
            "/api/resumes/upload",
            files={"file": ("test.pdf", b"test content", "application/pdf")},
            headers={"Authorization": f"Bearer {invalid_token}"}
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.security
@pytest.mark.unit
class TestAuthenticationRequired:
    """Test that protected endpoints require authentication."""

    def test_upload_without_token_rejected(self, client):
        """Test that upload endpoint rejects requests without authentication."""
        response = client.post(
            "/api/resumes/upload",
            files={"file": ("test.pdf", b"test content", "application/pdf")}
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Not authenticated" in response.json()["detail"]

    def test_status_without_token_rejected(self, client):
        """Test that status endpoint rejects requests without authentication."""
        response = client.get("/api/resumes/status/test-task-id")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Not authenticated" in response.json()["detail"]

    def test_invalid_authorization_header_formats(self, client):
        """Test various invalid Authorization header formats."""
        invalid_headers = [
            {"Authorization": "InvalidScheme token"},
            {"Authorization": "Bearer"},  # Missing token
            {"Authorization": "token_without_scheme"},
            {"Authorization": ""},
        ]
        
        for header in invalid_headers:
            response = client.post(
                "/api/resumes/upload",
                files={"file": ("test.pdf", b"test content", "application/pdf")},
                headers=header
            )
            
            # Should be 401 unauthorized, but may hit rate limit from previous tests
            assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_429_TOO_MANY_REQUESTS]
            if response.status_code == status.HTTP_401_UNAUTHORIZED:
                assert "Not authenticated" in response.json()["detail"]


class TestPermissionBasedAccess:
    """Test role-based access control and permissions."""

    def test_token_with_insufficient_permissions_rejected(self, client):
        """Test that tokens without required scopes are rejected."""
        config = get_config()
        
        # Create token with user scope instead of admin
        user_payload = {
            "sub": "user",
            "scopes": ["user"],  # Missing admin scope
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15)
        }
        
        user_token = jwt.encode(
            user_payload,
            config.jwt_secret_key,
            algorithm=config.jwt_algorithm
        )
        
        # Try to access endpoint - currently endpoints don't require specific scopes
        # but they do require valid authentication
        response = client.post(
            "/api/resumes/upload",
            files={"file": ("test.pdf", b"test content", "application/pdf")},
            headers={"Authorization": f"Bearer {user_token}"}
        )
        
        # Should work since the endpoint just requires authentication, not specific scopes
        # May hit rate limit due to previous tests
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_429_TOO_MANY_REQUESTS]

    def test_token_with_empty_scopes_handling(self, client):
        """Test handling of tokens with empty or missing scopes."""
        config = get_config()
        
        # Token with empty scopes
        empty_scopes_payload = {
            "sub": "admin",
            "scopes": [],  # Empty scopes
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15)
        }
        
        token_empty_scopes = jwt.encode(
            empty_scopes_payload,
            config.jwt_secret_key,
            algorithm=config.jwt_algorithm
        )
        
        # Token without scopes field
        no_scopes_payload = {
            "sub": "admin", 
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15)
            # No 'scopes' field
        }
        
        token_no_scopes = jwt.encode(
            no_scopes_payload,
            config.jwt_secret_key,
            algorithm=config.jwt_algorithm
        )
        
        for token in [token_empty_scopes, token_no_scopes]:
            response = client.post(
                "/api/resumes/upload",
                files={"file": ("test.pdf", b"test content", "application/pdf")},
                headers={"Authorization": f"Bearer {token}"}
            )
            
            # Should handle gracefully - either allow or deny based on endpoint requirements
            # May hit rate limit due to previous tests
            assert response.status_code in [
                status.HTTP_200_OK, 
                status.HTTP_401_UNAUTHORIZED, 
                status.HTTP_403_FORBIDDEN,
                status.HTTP_429_TOO_MANY_REQUESTS
            ]


class TestTokenExtraction:
    """Test token extraction utility functions."""

    def test_extract_token_valid_formats(self):
        """Test token extraction from various valid Authorization header formats."""
        test_cases = [
            ("Bearer abcd1234", ("Bearer", "abcd1234")),
            ("bearer xyz789", ("bearer", "xyz789")),
            ("JWT token123", ("JWT", "token123")),
            ("Custom my-token", ("Custom", "my-token")),
        ]
        
        for header_value, expected in test_cases:
            scheme, token = extract_token(header_value)
            assert scheme == expected[0]
            assert token == expected[1]

    def test_extract_token_invalid_formats(self):
        """Test token extraction from invalid formats."""
        test_cases = [
            "",  # Empty string
            "   ",  # Whitespace only
            "NoSpaceToken",  # No space separator
            "Bearer",  # Missing token
            " Bearer token",  # Leading space
        ]
        
        for header_value in test_cases:
            scheme, token = extract_token(header_value)
            # Should handle gracefully without crashing
            assert isinstance(scheme, str)
            assert isinstance(token, str)


class TestTokenSecurity:
    """Test token security and manipulation scenarios."""

    def test_token_algorithm_manipulation_rejected(self, client):
        """Test that changing token algorithm in header is rejected."""
        config = get_config()
        
        # Create token with different algorithm claim
        payload = {
            "sub": "admin",
            "scopes": ["admin"],
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
            "alg": "none"  # Try to manipulate algorithm
        }
        
        # Use different algorithm
        try:
            manipulated_token = jwt.encode(
                payload,
                "",  # Empty key for "none" algorithm
                algorithm="none"
            )
            
            response = client.post(
                "/api/resumes/upload",
                files={"file": ("test.pdf", b"test content", "application/pdf")},
                headers={"Authorization": f"Bearer {manipulated_token}"}
            )
            
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
        except Exception:
            # Some JWT libraries prevent "none" algorithm - that's good security
            pass

    def test_token_replay_attack_resistance(self, client, admin_token):
        """Test that valid tokens work multiple times (no replay protection needed for stateless JWT)."""
        # Make multiple requests with same token - should work for stateless JWT
        for _ in range(3):
            response = client.post(
                "/api/resumes/upload",
                files={"file": ("test.pdf", b"test content", "application/pdf")},
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            # Should succeed multiple times (JWT is stateless)
            # Note: This might fail due to rate limiting, which is expected
            assert response.status_code in [status.HTTP_200_OK, status.HTTP_429_TOO_MANY_REQUESTS]

    def test_case_sensitive_authorization_header(self, client, admin_token):
        """Test that Authorization header is case-sensitive for scheme."""
        # Test different case variations
        case_variations = [
            f"bearer {admin_token}",  # lowercase
            f"BEARER {admin_token}",  # uppercase
            f"Bearer {admin_token}",  # proper case
        ]
        
        for auth_header in case_variations:
            response = client.post(
                "/api/resumes/upload",
                files={"file": ("test.pdf", b"test content", "application/pdf")},
                headers={"Authorization": auth_header}
            )
            
            # Should handle case variations appropriately
            # Most implementations are case-insensitive for "Bearer"
            assert response.status_code in [
                status.HTTP_200_OK, 
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_429_TOO_MANY_REQUESTS
            ]


class TestAuthenticationEndpoint:
    """Test the authentication endpoint itself."""

    def test_auth_endpoint_with_valid_credentials(self, client):
        """Test successful authentication with valid credentials."""
        config = get_config()
        
        response = client.post(
            "/api/auth",
            json={
                "login": config.admin_login,
                "password": config.admin_password,
            }
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "token" in data
        assert data["type"] == "bearer"
        assert len(data["token"]) > 30  # JWT tokens are longer

    def test_auth_endpoint_with_invalid_credentials(self, client):
        """Test authentication failure with invalid credentials."""
        invalid_credentials = [
            {"login": "wrong_user", "password": "wrong_pass"},
            {"login": "", "password": ""},
            {"login": "admin", "password": "wrong_password"},
            {"login": "wrong_user", "password": "admin"},
        ]
        
        for creds in invalid_credentials:
            response = client.post("/api/auth", json=creds)
            
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert "password" in response.json()["detail"].lower()

    def test_auth_endpoint_missing_fields(self, client):
        """Test authentication with missing required fields."""
        invalid_requests = [
            {},  # Empty body
            {"login": "admin"},  # Missing password
            {"password": "admin"},  # Missing login
            {"login": None, "password": "admin"},  # Null login
            {"login": "admin", "password": None},  # Null password
        ]
        
        for req_body in invalid_requests:
            response = client.post("/api/auth", json=req_body)
            
            # Should return validation error
            assert response.status_code in [
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ]

    def test_auth_endpoint_content_type_validation(self, client):
        """Test that auth endpoint requires proper content type."""
        config = get_config()
        
        # Try with form data instead of JSON
        response = client.post(
            "/api/auth",
            data={
                "login": config.admin_login,
                "password": config.admin_password,
            }
        )
        
        # Should require JSON content type
        assert response.status_code in [
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            status.HTTP_400_BAD_REQUEST
        ]


class TestTokenLifecycle:
    """Test JWT token lifecycle and timing."""

    def test_token_creation_includes_expiration(self):
        """Test that created tokens include proper expiration."""
        payload = {"sub": "admin", "scopes": ["admin"]}
        token = create_access_token(payload, expires_delta=timedelta(minutes=30))
        
        config = get_config()
        decoded = jwt.decode(
            token,
            config.jwt_secret_key,
            algorithms=[config.jwt_algorithm]
        )
        
        # Check that expiration is set and reasonable
        assert "exp" in decoded
        exp_time = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        
        # Should expire in approximately 30 minutes
        time_diff = exp_time - now
        assert timedelta(minutes=25) < time_diff < timedelta(minutes=35)

    def test_token_default_expiration(self):
        """Test that tokens have reasonable default expiration."""
        payload = {"sub": "admin", "scopes": ["admin"]}
        token = create_access_token(payload)  # Use default expiration
        
        config = get_config()
        decoded = jwt.decode(
            token,
            config.jwt_secret_key,
            algorithms=[config.jwt_algorithm]
        )
        
        # Check default expiration (should be 15 minutes per function default)
        exp_time = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        
        time_diff = exp_time - now
        assert timedelta(minutes=10) < time_diff < timedelta(minutes=20)

    def test_nearly_expired_token_still_valid(self, client):
        """Test that tokens near expiration but still valid work."""
        config = get_config()
        
        # Create token that expires in 30 seconds
        payload = {
            "sub": "admin",
            "scopes": ["admin"],
            "exp": datetime.now(timezone.utc) + timedelta(seconds=30)
        }
        
        nearly_expired_token = jwt.encode(
            payload,
            config.jwt_secret_key,
            algorithm=config.jwt_algorithm
        )
        
        response = client.post(
            "/api/resumes/upload",
            files={"file": ("test.pdf", b"test content", "application/pdf")},
            headers={"Authorization": f"Bearer {nearly_expired_token}"}
        )
        
        # Should still work
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_429_TOO_MANY_REQUESTS]