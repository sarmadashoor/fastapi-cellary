from pydantic import BaseModel


class ResumeUploadResponse(BaseModel):
    """Response model for resume upload endpoint."""
    
    task_id: str