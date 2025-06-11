"""
Resume upload endpoint for processing PDF and DOCX files.

This module implements secure file upload handling with:
- File type validation (PDF, DOCX only)
- File size limits (5MB maximum)
- Secure logging without exposing user data
- In-memory processing without disk writes
"""

import logging
from typing import Optional

from app.api.v1.models.resumes import ResumeUploadResponse
from fastapi import APIRouter, File, HTTPException, UploadFile, status

# Configure logger
log = logging.getLogger(__name__)

# File size limit: 5MB
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB in bytes

# Allowed content types
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
}

# Allowed file extensions
ALLOWED_EXTENSIONS = {".pdf", ".docx"}

router = APIRouter()


def validate_file_type(file: UploadFile) -> None:
    """
    Validate file type based on content type and extension.
    
    Args:
        file: The uploaded file to validate
        
    Raises:
        HTTPException: If file type is not supported
    """
    if not file.content_type or file.content_type not in ALLOWED_CONTENT_TYPES:
        log.warning(f"Unsupported content type attempted: {file.content_type}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Only PDF and DOCX files are allowed."
        )
    
    if file.filename:
        # Extract file extension
        file_ext = None
        if "." in file.filename:
            file_ext = "." + file.filename.split(".")[-1].lower()
        
        if file_ext not in ALLOWED_EXTENSIONS:
            log.warning(f"Unsupported file extension attempted: {file_ext}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type. Only PDF and DOCX files are allowed."
            )


def validate_file_size(content: bytes) -> None:
    """
    Validate file size.
    
    Args:
        content: The file content as bytes
        
    Raises:
        HTTPException: If file is too large or empty
    """
    content_size = len(content)
    
    if content_size == 0:
        log.warning("Empty file upload attempted")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file not allowed. Please upload a valid file."
        )
    
    if content_size > MAX_FILE_SIZE:
        log.warning(f"File size limit exceeded: {content_size} bytes")
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds the maximum limit of {MAX_FILE_SIZE // (1024 * 1024)}MB."
        )


def stub_parse_resume_task(file_content: bytes, filename: Optional[str] = None) -> str:
    """
    Stub implementation of Celery task for resume parsing.
    
    In a real implementation, this would be:
    parse_resume_task.delay(file_content, filename)
    
    Args:
        file_content: The file content as bytes
        filename: Optional filename for processing context
        
    Returns:
        A task ID string
    """
    # This is a stub implementation that returns a fixed task ID
    # In production, this would call the actual Celery task
    return "abc123def456789"


@router.post("/upload", response_model=ResumeUploadResponse, status_code=status.HTTP_200_OK)
async def upload_resume(
    file: UploadFile = File(..., description="Resume file (PDF or DOCX, max 5MB)")
) -> ResumeUploadResponse:
    """
    Upload and process a resume file.
    
    Accepts PDF and DOCX files up to 5MB in size. The file is validated
    for type and size, then queued for background processing.
    
    Args:
        file: The uploaded resume file
        
    Returns:
        ResumeUploadResponse containing the task ID for tracking processing status
        
    Raises:
        HTTPException: 
            - 400 Bad Request: Invalid file type, empty file
            - 413 Payload Too Large: File exceeds size limit
            - 422 Unprocessable Entity: Missing file
    """
    if not file:
        log.warning("Upload request with no file")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No file provided"
        )
    
    # Validate file type first (before reading content for security)
    validate_file_type(file)
    
    try:
        # Read file content into memory for validation
        file_content = await file.read()
        
        # Validate file size
        validate_file_size(file_content)
        
        # Log successful upload (without exposing filename or user data)
        file_size_mb = len(file_content) / (1024 * 1024)
        log.info(f"Resume upload successful: {file.content_type}, {file_size_mb:.2f}MB")
        
        # Process file with Celery task (stubbed for now)
        task_id = stub_parse_resume_task(file_content, file.filename)
        
        return ResumeUploadResponse(task_id=task_id)
        
    except HTTPException:
        # Re-raise HTTP exceptions (validation errors)
        raise
    except Exception as e:
        # Handle unexpected errors without exposing stack trace
        log.error(f"Unexpected error during resume upload: {type(e).__name__}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the file"
        )
    finally:
        # Ensure file is closed
        await file.close()