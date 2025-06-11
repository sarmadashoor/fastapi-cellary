"""Authentication API endpoints package for user login and token management.

This package provides JWT-based authentication endpoints including token
generation, refresh, and user group management for API access control.
"""

from pathlib import Path

from app import modules_load
from fastapi import APIRouter

router = APIRouter()

modules_load.asterisk(Path(__file__).parent, __package__, globals())
