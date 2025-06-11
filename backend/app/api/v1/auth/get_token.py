from datetime import datetime, timedelta, timezone
from itertools import chain
from typing import Any, Dict

import app.config as app_config  # to not shadow global app var with FastAPI app
import jwt
from app.api.v1 import models as api_models
from app.api.v1.auth import router
from app.security import verify_password
from fastapi import Body, HTTPException


def authenticate_admin(login: str, password: str) -> bool:
    """
    Authenticate admin user with secure password verification.

    Args:
        login: Username to authenticate
        password: Plain text password to verify

    Returns:
        True if authentication successful, False otherwise
    """
    config = app_config.get_config()

    # Check if login matches
    if login != config.admin_login:
        return False

    # Get stored password (could be hashed or plaintext for backward compatibility)
    stored_password = config.admin_password

    # Check if stored password is already hashed (bcrypt hashes start with $2b$)
    if stored_password.startswith("$2b$"):
        # Use secure verification for hashed password
        return verify_password(password, stored_password)
    # Fallback to plaintext comparison for backward compatibility
    # This should be removed in production after all passwords are migrated
    return password == stored_password


def create_access_token(
    payload: Dict[str, Any],
    expires_delta: timedelta = timedelta(minutes=15),
) -> str:
    """
    Create JWT
    """
    return jwt.encode(
        payload=dict(
            chain(
                payload.copy().items(),
                {"exp": datetime.now(timezone.utc) + expires_delta}.items(),
            ),
        ),
        key=app_config.get_config().jwt_secret_key,
        algorithm=app_config.get_config().jwt_algorithm,
    )


@router.post("", response_model=api_models.Token)  # type: ignore
def get_token(  # type: ignore
    credentials: api_models.Credentials = Body(
        None,
        description="User credentials",
        example={
            "login": "admin",
            "password": "admin",
        },
    ),
):
    """
    Return access token for the credentials.

    Current implementation returns token with `admin` scope for admin's login/password
    defined in env vars (see app.config).
    """
    if not authenticate_admin(login=credentials.login, password=credentials.password):
        raise HTTPException(status_code=400, detail="Incorrect user login or password")
    access_token = create_access_token(
        payload={"sub": "admin", "scopes": ["admin"]},
    )
    return {"token": access_token, "type": "bearer"}
