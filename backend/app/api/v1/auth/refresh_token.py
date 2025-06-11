"""
JWT token refresh endpoint with security hardening.

This module provides secure token refresh functionality:
- Refresh token rotation for security
- Token family tracking to detect theft
- Client fingerprinting for additional security
- Comprehensive security audit logging
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any
import secrets

import app.config as app_config
import jwt
from app.api.v1 import models as api_models
from app.api.v1.auth import router
from app.auth.security_hardening import token_refresh_manager, JWTSecurityEnhancer
from app.logging_config import get_logger
from fastapi import Body, HTTPException, Request, status
from pydantic import BaseModel

logger = get_logger(__name__)


class RefreshTokenRequest(BaseModel):
    """Request model for token refresh."""
    refresh_token: str
    grant_type: str = "refresh_token"


class RefreshTokenResponse(BaseModel):
    """Response model for token refresh."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


def create_refresh_token(user_id: str, client_info: Dict[str, Any]) -> str:
    """
    Create a secure refresh token.
    
    Args:
        user_id: User identifier
        client_info: Client fingerprinting information
        
    Returns:
        Encoded refresh token
    """
    config = app_config.get_config()
    
    # Create token family for tracking
    family_id = token_refresh_manager.create_token_family(user_id, client_info)
    
    # Create refresh token payload
    now = datetime.now(timezone.utc)
    refresh_payload = {
        "sub": user_id,
        "type": "refresh",
        "family_id": family_id,
        "exp": now + timedelta(days=30),  # 30 days for refresh tokens
        "iat": now,
        "nbf": now,
        "jti": f"refresh_{int(now.timestamp())}_{secrets.token_urlsafe(16)}",
        "client_fingerprint": token_refresh_manager._create_client_fingerprint(client_info)
    }
    
    return jwt.encode(
        payload=refresh_payload,
        key=config.jwt_secret_key,
        algorithm=config.jwt_algorithm,
    )


def create_access_token_from_refresh(payload: Dict[str, Any], client_ip: str) -> str:
    """
    Create access token from validated refresh token.
    
    Args:
        payload: Validated refresh token payload
        client_ip: Client IP address for binding
        
    Returns:
        New access token
    """
    config = app_config.get_config()
    
    # Create new access token
    now = datetime.now(timezone.utc)
    access_payload = {
        "sub": payload["sub"],
        "scopes": ["admin"],  # Default admin scope - could be from user data
        "exp": now + timedelta(minutes=15),  # 15 minutes for access tokens
        "iat": now,
        "nbf": now,
        "jti": f"access_{int(now.timestamp())}_{secrets.token_urlsafe(16)}",
        "ip": client_ip,  # Bind to IP
        "refresh_family": payload.get("family_id"),  # Link to refresh family
    }
    
    return jwt.encode(
        payload=access_payload,
        key=config.jwt_secret_key,
        algorithm=config.jwt_algorithm,
    )


@router.post("/refresh", response_model=RefreshTokenResponse)
def refresh_access_token(
    request: Request,
    refresh_request: RefreshTokenRequest = Body(
        ...,
        description="Refresh token request",
        example={
            "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "grant_type": "refresh_token"
        }
    )
) -> RefreshTokenResponse:
    """
    Refresh access token using a valid refresh token.
    
    **Security Features:**
    - Refresh token rotation (old token invalidated, new one issued)
    - Token family tracking to detect theft and replay attacks
    - Client fingerprinting for additional security validation
    - Comprehensive security audit logging
    - Automatic family revocation on suspicious activity
    
    **Token Lifetimes:**
    - Access Token: 15 minutes
    - Refresh Token: 30 days (rotated on each use)
    
    **Security Events Logged:**
    - Token refresh success/failure
    - Token theft detection (reuse of old refresh tokens)
    - Client fingerprint mismatches
    - Suspicious refresh patterns
    
    Args:
        request: FastAPI request object for client fingerprinting
        refresh_request: Refresh token and grant type
        
    Returns:
        New access token and refresh token pair
        
    Raises:
        HTTPException: 400/401 for invalid tokens or security violations
    """
    if refresh_request.grant_type != "refresh_token":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid grant type"
        )
    
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    accept_language = request.headers.get("accept-language", "unknown")
    
    # Create client info for fingerprinting
    client_info = {
        "ip_address": client_ip,
        "user_agent": user_agent,
        "accept_language": accept_language
    }
    
    try:
        config = app_config.get_config()
        
        # Decode and validate refresh token
        payload = jwt.decode(
            refresh_request.refresh_token,
            config.jwt_secret_key,
            algorithms=[config.jwt_algorithm],
            options={
                "verify_exp": True,
                "verify_iat": True,
                "verify_nbf": True,
                "verify_signature": True,
                "require": ["exp", "iat", "sub", "type", "family_id"]
            }
        )
        
        # Validate token type
        if payload.get("type") != "refresh":
            logger.warning(
                "Invalid token type for refresh endpoint",
                extra={
                    "event": "invalid_refresh_token_type",
                    "token_type": payload.get("type"),
                    "ip_address": client_ip,
                    "security_event": True
                }
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token type"
            )
        
        # Validate token claims
        is_valid, validation_errors = JWTSecurityEnhancer.validate_token_claims(payload)
        if not is_valid:
            logger.warning(
                "Invalid refresh token claims",
                extra={
                    "event": "invalid_refresh_token_claims", 
                    "errors": validation_errors,
                    "ip_address": client_ip,
                    "security_event": True
                }
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        # Extract token information
        user_id = payload["sub"]
        family_id = payload["family_id"]
        old_token_id = payload.get("jti", "unknown")
        
        # Attempt token rotation with theft detection
        new_refresh_token_id = token_refresh_manager.rotate_refresh_token(
            family_id=family_id,
            old_token_id=old_token_id,
            client_info=client_info
        )
        
        if new_refresh_token_id is None:
            # Token theft detected or family revoked
            logger.error(
                "Refresh token theft detected - access denied",
                extra={
                    "event": "refresh_token_theft_access_denied",
                    "family_id": family_id,
                    "user_id": user_id,
                    "ip_address": client_ip,
                    "user_agent": user_agent,
                    "security_event": True,
                    "alert_priority": "critical"
                }
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token - possible security violation"
            )
        
        # Create new access token
        new_access_token = create_access_token_from_refresh(payload, client_ip)
        
        # Create new refresh token
        new_refresh_token = create_refresh_token(user_id, client_info)
        
        # Log successful refresh
        logger.info(
            "Token refreshed successfully",
            extra={
                "event": "token_refresh_success",
                "user_id": user_id,
                "family_id": family_id,
                "ip_address": client_ip,
                "user_agent": user_agent,
                "security_event": True
            }
        )
        
        return RefreshTokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=15 * 60  # 15 minutes in seconds
        )
        
    except jwt.ExpiredSignatureError:
        logger.warning(
            "Expired refresh token used",
            extra={
                "event": "expired_refresh_token_used",
                "ip_address": client_ip,
                "user_agent": user_agent,
                "security_event": True
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired"
        )
    except jwt.InvalidTokenError as e:
        logger.warning(
            "Invalid refresh token format",
            extra={
                "event": "invalid_refresh_token_format",
                "error": str(e),
                "ip_address": client_ip,
                "user_agent": user_agent,
                "security_event": True
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    except Exception as e:
        logger.error(
            "Unexpected error during token refresh",
            extra={
                "event": "token_refresh_error",
                "error": str(e),
                "error_type": type(e).__name__,
                "ip_address": client_ip,
                "security_event": True
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during token refresh"
        )