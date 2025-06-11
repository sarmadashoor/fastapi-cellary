"""Pydantic models for authentication and authorization."""

from typing import List

from pydantic import BaseModel


class Token(BaseModel):
    """JWT token response model.
    
    Attributes:
        token: The JWT token string.
        type: The token type (typically 'bearer').
    """
    
    token: str
    type: str


class TokenData(BaseModel):
    """JWT token payload data model.
    
    Attributes:
        user_group: User group identifier for authorization.
        scopes: List of permission scopes granted to the token.
    """
    
    user_group: str | None = None
    scopes: List[str] = []


class Credentials(BaseModel):
    """User login credentials model.
    
    Attributes:
        login: User login identifier (username or email).
        password: User password in plain text (will be hashed).
    """
    
    login: str
    password: str
