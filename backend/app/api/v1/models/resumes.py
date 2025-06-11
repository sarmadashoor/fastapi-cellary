from typing import Dict, Optional, Any
from pydantic import BaseModel


class ResumeUploadResponse(BaseModel):
    """Response model for resume upload endpoint."""

    task_id: str


class ContactInfo(BaseModel):
    """Contact information extracted from resume."""
    
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class ResumeStatusResponse(BaseModel):
    """Response model for resume status endpoint."""
    
    task_id: str
    status: str  # PENDING, SUCCESS, FAILURE, RETRY, REVOKED
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
