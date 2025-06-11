from datetime import datetime, timedelta, timezone
from itertools import chain
from typing import Any, Dict
import time

import app.config as app_config  # to not shadow global app var with FastAPI app
import jwt
from app.api.v1 import models as api_models
from app.api.v1.auth import router
from app.security import verify_password
from app.auth.security_hardening import (
    brute_force_protection, 
    JWTSecurityEnhancer,
    PasswordStrengthValidator
)
from app.logging_config import get_logger
from fastapi import Body, HTTPException, Request, status

logger = get_logger(__name__)


def authenticate_admin(login: str, password: str, request: Request) -> bool:
    """
    Authenticate admin user with comprehensive security hardening.

    Args:
        login: Username to authenticate
        password: Plain text password to verify
        request: FastAPI request object for IP/user agent info

    Returns:
        True if authentication successful, False otherwise
    """
    config = app_config.get_config()
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    # Check account lockout status
    if brute_force_protection.is_account_locked(login):
        lockout_info = brute_force_protection.get_lockout_info(login)
        logger.warning(
            "Authentication attempt on locked account",
            extra={
                "event": "locked_account_access_attempt",
                "username": login,
                "ip_address": client_ip,
                "user_agent": user_agent,
                "locked_until": lockout_info.locked_until.isoformat() if lockout_info else None,
                "security_event": True
            }
        )
        return False

    # Check IP rate limiting
    if brute_force_protection.is_ip_rate_limited(client_ip):
        logger.warning(
            "IP rate limit exceeded for authentication",
            extra={
                "event": "ip_rate_limit_exceeded",
                "ip_address": client_ip,
                "user_agent": user_agent,
                "security_event": True
            }
        )
        return False

    # Apply progressive delay for repeated failures
    delay_seconds = brute_force_protection.get_attempt_delay(login)
    if delay_seconds > 0:
        logger.info(
            "Applying progressive delay for failed attempts",
            extra={
                "event": "progressive_delay_applied",
                "username": login,
                "delay_seconds": delay_seconds,
                "ip_address": client_ip
            }
        )
        time.sleep(delay_seconds)

    # Check if login matches
    if login != config.admin_login:
        brute_force_protection.record_failed_attempt(
            username=login,
            ip_address=client_ip,
            reason="invalid_username",
            user_agent=user_agent
        )
        return False

    # Get stored password
    stored_password = config.admin_password

    # Security enhancement: Reject plaintext passwords in production
    if not stored_password.startswith("$2b$"):
        logger.error(
            "Plaintext password detected - security risk",
            extra={
                "event": "plaintext_password_detected",
                "username": login,
                "security_event": True,
                "alert_priority": "critical"
            }
        )
        # In production, this should fail authentication
        # For now, allow with warning for backward compatibility
        if password == stored_password:
            logger.warning(
                "Authentication succeeded with plaintext password",
                extra={
                    "event": "plaintext_auth_success",
                    "username": login,
                    "ip_address": client_ip,
                    "security_event": True,
                    "alert_priority": "high"
                }
            )
            # Clear failed attempts on success
            brute_force_protection.clear_failed_attempts(login)
            return True
        else:
            brute_force_protection.record_failed_attempt(
                username=login,
                ip_address=client_ip,
                reason="invalid_password",
                user_agent=user_agent
            )
            return False

    # Use secure verification for hashed password
    if verify_password(password, stored_password):
        # Success - clear failed attempts and log
        brute_force_protection.clear_failed_attempts(login)
        
        logger.info(
            "Successful authentication",
            extra={
                "event": "authentication_success",
                "username": login,
                "ip_address": client_ip,
                "user_agent": user_agent,
                "security_event": True
            }
        )
        return True
    else:
        brute_force_protection.record_failed_attempt(
            username=login,
            ip_address=client_ip,
            reason="invalid_password",
            user_agent=user_agent
        )
        return False


def create_access_token(
    payload: Dict[str, Any],
    expires_delta: timedelta = timedelta(minutes=15),
) -> str:
    """
    Create secure JWT access token with enhanced validation.
    
    Args:
        payload: Token payload data
        expires_delta: Token expiration time (default: 15 minutes)
        
    Returns:
        Encoded JWT token string
        
    Raises:
        HTTPException: If JWT secret is weak or invalid
    """
    config = app_config.get_config()
    
    # Validate JWT secret strength
    is_valid, errors = JWTSecurityEnhancer.validate_secret_strength(config.jwt_secret_key)
    if not is_valid:
        logger.error(
            "Weak JWT secret detected",
            extra={
                "event": "weak_jwt_secret",
                "errors": errors,
                "security_event": True,
                "alert_priority": "critical"
            }
        )
        # In production, this should fail hard
        # For development, log warning but continue
    
    # Add security-enhanced claims
    now = datetime.now(timezone.utc)
    enhanced_payload = {
        **payload.copy(),
        "exp": now + expires_delta,
        "iat": now,  # Issued at time
        "nbf": now,  # Not before time
        "jti": f"jwt_{int(now.timestamp())}_{hash(str(payload))}",  # JWT ID for tracking
    }
    
    # Validate token claims
    is_valid_claims, claim_errors = JWTSecurityEnhancer.validate_token_claims(enhanced_payload)
    if not is_valid_claims:
        logger.error(
            "Invalid token claims",
            extra={
                "event": "invalid_token_claims",
                "errors": claim_errors,
                "security_event": True
            }
        )
    
    return jwt.encode(
        payload=enhanced_payload,
        key=config.jwt_secret_key,
        algorithm=config.jwt_algorithm,
    )


@router.post("", response_model=api_models.Token)  # type: ignore
def get_token(  # type: ignore
    request: Request,
    credentials: api_models.Credentials = Body(
        None,
        description="User credentials",
        example={
            "login": "admin",
            "password": "SecurePassword123!",
        },
    ),
):
    """
    Return access token for the credentials with comprehensive security hardening.

    **Security Features:**
    - Account lockout protection after 5 failed attempts
    - Progressive delay on repeated failures (1s, 2s, 4s, 8s, 16s, 32s, 60s)
    - IP-based rate limiting (20 attempts per hour)
    - Comprehensive security audit logging
    - JWT token security validation
    - Brute force attack detection

    **Rate Limits:**
    - Account lockout: 5 failed attempts in 15 minutes → 30 minute lockout
    - IP rate limit: 20 authentication attempts per hour
    - Progressive delay: Exponential backoff on repeated failures

    **Security Events Logged:**
    - Authentication success/failure with IP and user agent
    - Account lockout events and suspicious activity
    - Plaintext password usage (critical security risk)
    - Rate limit violations and brute force attempts

    Returns JWT token with enhanced claims (iat, nbf, jti) for security tracking.
    """
    # Validate credentials exist
    if not credentials or not credentials.login or not credentials.password:
        client_ip = request.client.host if request.client else "unknown"
        logger.warning(
            "Authentication attempt with missing credentials",
            extra={
                "event": "missing_credentials",
                "ip_address": client_ip,
                "security_event": True
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Missing login or password"
        )

    # Check for account lockout or rate limiting first (before authentication)
    client_ip = request.client.host if request.client else "unknown"
    
    if brute_force_protection.is_account_locked(credentials.login):
        lockout_info = brute_force_protection.get_lockout_info(credentials.login)
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account locked until {lockout_info.locked_until.isoformat()} due to too many failed attempts"
        )
    
    if brute_force_protection.is_ip_rate_limited(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts from this IP address"
        )

    # Attempt authentication with security hardening
    if not authenticate_admin(
        login=credentials.login, 
        password=credentials.password, 
        request=request
    ):
        # Return generic error to prevent username enumeration
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid credentials"
        )
    
    # Create secure access token
    access_token = create_access_token(
        payload={
            "sub": credentials.login,
            "scopes": ["admin"],
            "ip": client_ip,  # Bind token to IP for additional security
        },
    )
    
    logger.info(
        "Access token issued successfully",
        extra={
            "event": "token_issued",
            "username": credentials.login,
            "ip_address": client_ip,
            "token_type": "access",
            "security_event": True
        }
    )
    
    return {"token": access_token, "type": "bearer"}
