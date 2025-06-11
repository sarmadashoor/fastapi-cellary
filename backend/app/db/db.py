"""Database dependency injection for FastAPI request handlers.

This module provides database session dependency injection for FastAPI
routes through request state management.
"""

from typing import Any

from starlette.requests import Request


def get_db(request: Request) -> Any:
    """Get database session from request state.
    
    Args:
        request: FastAPI/Starlette request object with attached database session.
        
    Returns:
        Any: Database session instance attached to request state.
    """
    return request.state.db
