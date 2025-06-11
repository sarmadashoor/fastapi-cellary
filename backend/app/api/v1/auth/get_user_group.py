from typing import Any, Dict, Optional, Tuple
from datetime import datetime, timezone

import app.config as app_config  # to not shadow global app var with FastAPI app
import jwt
from app.api.v1 import models as api_models
from app.auth.security_hardening import JWTSecurityEnhancer
from app.logging_config import get_logger
from fastapi import Depends, HTTPException, Request, status
from fastapi.openapi.models import SecuritySchemeType
from fastapi.security import SecurityScopes
from fastapi.security.base import SecurityBase
from pydantic import BaseModel, Field, ValidationError

logger = get_logger(__name__)


def extract_token(authorization_header_value: str) -> Tuple[str, str]:
    """
    Extract token value from HTTP header value ('Bearer <token_value>')
    """
    if not authorization_header_value:
        return "", ""
    scheme, _, token = authorization_header_value.partition(" ")
    return scheme, token


class JWTSchema(SecurityBase):
    type_ = Field(SecuritySchemeType.apiKey, alias="type")
    flows: BaseModel


class JwtPasswordBearer(SecurityBase):
    def __init__(
        self,
        tokenUrl: str,  # pylint: disable=unused-argument
        scopes: Dict[str, Any] | None = None,
    ):
        if not scopes:
            scopes = {}
        self.scopes = scopes
        self.model = JWTSchema()  # type: ignore
        self.scheme_name = self.__class__.__name__

    async def __call__(self, request: Request) -> Optional[str]:
        authorization: str = request.headers.get("Authorization")  # type: ignore
        scheme, param = extract_token(authorization)
        if not authorization or scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return param


jwt_scheme = JwtPasswordBearer(
    tokenUrl="/api/auth",
    scopes={"admin": "Create/delete", "user": "Use"},
)


def get_user_group(
    security_scopes: SecurityScopes,
    request: Request,
    token: str = Depends(jwt_scheme),
) -> str:
    """
    Validate JWT token with enhanced security checks.
    
    **Security Enhancements:**
    - Comprehensive token validation (signature, expiration, claims)
    - IP binding validation for token security
    - Security event logging for monitoring
    - Protection against token replay and manipulation
    - Detailed error logging for security analysis
    
    Args:
        security_scopes: Required permission scopes
        request: FastAPI request object for IP validation
        token: JWT token from Authorization header
        
    Returns:
        User group/username from validated token
        
    Raises:
        HTTPException: 401 if token is invalid or insufficient permissions
    """
    if security_scopes.scopes:
        authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
    else:
        authenticate_value = "Bearer"
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": authenticate_value},
    )
    
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    
    try:
        config = app_config.get_config()
        
        # Decode and validate token
        payload = jwt.decode(
            token,
            config.jwt_secret_key,
            algorithms=[config.jwt_algorithm],
            options={
                "verify_exp": True,      # Verify expiration
                "verify_iat": True,      # Verify issued at
                "verify_nbf": True,      # Verify not before
                "verify_signature": True, # Verify signature
                "require": ["exp", "iat", "sub", "scopes"],  # Required claims
            }
        )
        
        # Enhanced token validation
        is_valid, validation_errors = JWTSecurityEnhancer.validate_token_claims(payload)
        if not is_valid:
            logger.warning(
                "Invalid token claims detected",
                extra={
                    "event": "invalid_token_claims",
                    "errors": validation_errors,
                    "ip_address": client_ip,
                    "user_agent": user_agent,
                    "security_event": True
                }
            )
            raise credentials_exception
        
        # Extract user information
        user_group: str | None = payload.get("sub")
        if user_group is None:
            logger.warning(
                "Missing subject claim in token",
                extra={
                    "event": "missing_subject_claim",
                    "ip_address": client_ip,
                    "security_event": True
                }
            )
            raise credentials_exception
        
        # Validate IP binding if present in token
        token_ip = payload.get("ip")
        if token_ip and token_ip != client_ip:
            logger.warning(
                "Token IP mismatch detected - possible token theft",
                extra={
                    "event": "token_ip_mismatch",
                    "token_ip": token_ip,
                    "client_ip": client_ip,
                    "user": user_group,
                    "security_event": True,
                    "alert_priority": "high"
                }
            )
            # For now, log but allow - in production this could block access
        
        # Validate scopes
        token_scopes = payload.get("scopes", [])
        token_data = api_models.TokenData(scopes=token_scopes, user_group=user_group)
        
        # Log successful token validation
        logger.debug(
            "Token validated successfully",
            extra={
                "event": "token_validation_success",
                "user": user_group,
                "scopes": token_scopes,
                "ip_address": client_ip,
                "jti": payload.get("jti"),  # JWT ID for tracking
                "security_event": True
            }
        )
        
    except jwt.ExpiredSignatureError:
        logger.warning(
            "Expired token used",
            extra={
                "event": "expired_token_used",
                "ip_address": client_ip,
                "user_agent": user_agent,
                "security_event": True
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": authenticate_value},
        )
    except jwt.InvalidTokenError as e:
        logger.warning(
            "Invalid token format",
            extra={
                "event": "invalid_token_format",
                "error": str(e),
                "ip_address": client_ip,
                "user_agent": user_agent,
                "security_event": True
            }
        )
        raise credentials_exception from e
    except (jwt.PyJWTError, ValidationError) as e:
        logger.error(
            "Token validation error",
            extra={
                "event": "token_validation_error",
                "error": str(e),
                "error_type": type(e).__name__,
                "ip_address": client_ip,
                "user_agent": user_agent,
                "security_event": True
            }
        )
        raise credentials_exception from e
    
    # Check scope permissions
    for scope in security_scopes.scopes:
        if scope not in token_data.scopes:
            logger.warning(
                "Insufficient permissions for requested scope",
                extra={
                    "event": "insufficient_permissions",
                    "required_scope": scope,
                    "user_scopes": token_data.scopes,
                    "user": user_group,
                    "ip_address": client_ip,
                    "security_event": True
                }
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,  # 403 for permission denied
                detail="Insufficient permissions",
                headers={"WWW-Authenticate": authenticate_value},
            )
    
    return user_group
