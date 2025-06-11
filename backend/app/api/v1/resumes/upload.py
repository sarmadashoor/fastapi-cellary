"""
Resume upload endpoint for processing PDF and DOCX files.

This module implements secure file upload handling with:
- File type validation (PDF, DOCX only)
- File size limits (5MB maximum)
- Secure logging without exposing user data
- In-memory processing without disk writes
- Celery background task queueing for processing
"""

import logging
from typing import Optional
import time

from app.api.v1.models.resumes import ResumeUploadResponse
from app.workers.resume_parser import parse_resume_task
from app.logging_config import get_logger
from app.api.v1.auth.get_user_group import get_user_group
from app.validation.file_validation import comprehensive_file_validation, SecurityValidationError
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.security import SecurityScopes

# Configure structured logger
logger = get_logger(__name__)

# File size limit: 5MB
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB in bytes

# Allowed content types
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Allowed file extensions
ALLOWED_EXTENSIONS = {".pdf", ".docx"}

router = APIRouter()


# Legacy validation functions maintained for backward compatibility
# These are now replaced by comprehensive_file_validation in upload endpoint

def validate_file_type(file: UploadFile) -> None:
    """
    Legacy file type validation function.
    
    DEPRECATED: Use comprehensive_file_validation instead.
    Maintained for backward compatibility with existing tests.
    """
    if not file.content_type or file.content_type not in ALLOWED_CONTENT_TYPES:
        logger.warning(
            "Unsupported content type attempted",
            extra={
                "content_type": file.content_type,
                "allowed_types": list(ALLOWED_CONTENT_TYPES),
                "event": "file_validation_failed",
                "validation_type": "content_type"
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Only PDF and DOCX files are allowed.",
        )

    if file.filename:
        # Extract file extension
        file_ext = None
        if "." in file.filename:
            file_ext = "." + file.filename.split(".")[-1].lower()

        if file_ext not in ALLOWED_EXTENSIONS:
            logger.warning(
                "Unsupported file extension attempted",
                extra={
                    "file_extension": file_ext,
                    "allowed_extensions": list(ALLOWED_EXTENSIONS),
                    "event": "file_validation_failed",
                    "validation_type": "file_extension"
                }
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type. Only PDF and DOCX files are allowed.",
            )


def validate_file_size(content: bytes) -> None:
    """
    Legacy file size validation function.
    
    DEPRECATED: Use comprehensive_file_validation instead.
    Maintained for backward compatibility with existing tests.
    """
    content_size = len(content)

    if content_size == 0:
        logger.warning(
            "Empty file upload attempted",
            extra={
                "file_size_bytes": content_size,
                "event": "file_validation_failed",
                "validation_type": "empty_file"
            }
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file not allowed. Please upload a valid file.",
        )

    if content_size > MAX_FILE_SIZE:
        logger.warning(
            "File size limit exceeded",
            extra={
                "file_size_bytes": content_size,
                "file_size_mb": round(content_size / (1024 * 1024), 2),
                "max_size_mb": MAX_FILE_SIZE // (1024 * 1024),
                "event": "file_validation_failed",
                "validation_type": "size_limit"
            }
        )
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds the maximum limit of {MAX_FILE_SIZE // (1024 * 1024)}MB.",
        )


def queue_resume_parsing_task(file_content: bytes, content_type: str) -> str:
    """
    Queue resume parsing task with Celery.

    Args:
        file_content: The file content as bytes
        content_type: MIME type of the file

    Returns:
        A task ID string for tracking the background job
    """
    task = parse_resume_task.delay(file_content, content_type)
    
    logger.info(
        "Resume parsing task queued",
        extra={
            "task_id": task.id,
            "content_type": content_type,
            "file_size_bytes": len(file_content),
            "file_size_mb": round(len(file_content) / (1024 * 1024), 2),
            "event": "task_queued",
            "task_type": "resume_parsing"
        }
    )
    
    return task.id


@router.post(
    "/upload", 
    response_model=ResumeUploadResponse, 
    status_code=status.HTTP_200_OK,
    summary="Upload Resume for Processing",
    description="""
    Upload a resume file (PDF or DOCX) for asynchronous text extraction and parsing.
    
    **Supported File Types:**
    - PDF (application/pdf)
    - DOCX (application/vnd.openxmlformats-officedocument.wordprocessingml.document)
    
    **File Constraints:**
    - Maximum file size: 5MB
    - File must not be empty
    - Valid file extension required (.pdf or .docx)
    
    **Processing:**
    - File is validated synchronously for type and size
    - Background processing extracts text and contact information
    - Returns a task ID for status tracking via `/status/{task_id}`
    
    **Rate Limits:**
    - 10 uploads per 5 minutes per IP address
    - Authentication required
    """,
    responses={
        200: {
            "description": "File uploaded successfully and queued for processing",
            "content": {
                "application/json": {
                    "example": {
                        "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
                    }
                }
            }
        },
        400: {
            "description": "Bad Request - Invalid file type or empty file",
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_type": {
                            "summary": "Unsupported file type",
                            "value": {
                                "detail": "Unsupported file type. Only PDF and DOCX files are allowed."
                            }
                        },
                        "empty_file": {
                            "summary": "Empty file",
                            "value": {
                                "detail": "Empty file not allowed. Please upload a valid file."
                            }
                        }
                    }
                }
            }
        },
        413: {
            "description": "Payload Too Large - File exceeds size limit",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "File size exceeds the maximum limit of 5MB."
                    }
                }
            }
        },
        422: {
            "description": "Unprocessable Entity - Missing file",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "No file provided"
                    }
                }
            }
        },
        429: {
            "description": "Too Many Requests - Rate limit exceeded",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Rate limit exceeded. Try again later."
                    }
                }
            }
        },
        500: {
            "description": "Internal Server Error - Unexpected processing error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred while processing the file"
                    }
                }
            }
        }
    },
    tags=["Resume Processing"]
)
async def upload_resume(
    file: UploadFile = File(
        ..., 
        description="Resume file to process (PDF or DOCX format, maximum 5MB)",
        media_type="application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    user_group: str = Depends(get_user_group),
) -> ResumeUploadResponse:
    """
    Upload and process a resume file.

    This endpoint accepts resume files in PDF or DOCX format and queues them
    for background processing. The processing includes text extraction and
    contact information parsing.

    **Processing Steps:**
    1. File type validation (PDF/DOCX only)
    2. File size validation (5MB limit)
    3. Content validation (non-empty)
    4. Queue for background processing
    5. Return task ID for status tracking

    **Security Features:**
    - Rate limiting: 10 uploads per 5 minutes
    - Content type validation
    - File size limits
    - In-memory processing (no disk writes)
    - Structured logging without PII exposure

    **Usage Example:**
    ```bash
    curl -X POST "http://localhost:8000/api/resumes/upload" \\
         -H "Authorization: Bearer YOUR_TOKEN" \\
         -F "file=@resume.pdf"
    ```

    Args:
        file: The uploaded resume file (PDF or DOCX, max 5MB)

    Returns:
        ResumeUploadResponse: Contains task ID for tracking processing status

    Raises:
        HTTPException:
            - 400 Bad Request: Invalid file type, empty file
            - 413 Payload Too Large: File exceeds size limit
            - 422 Unprocessable Entity: Missing file
            - 429 Too Many Requests: Rate limit exceeded
            - 500 Internal Server Error: Unexpected processing error
    """
    # Generate request ID for tracking
    request_start_time = time.time()
    
    if not file:
        logger.warning(
            "Upload request with no file",
            extra={
                "event": "upload_failed",
                "error_type": "no_file_provided"
            }
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No file provided",
        )

    try:
        # Read file content into memory for validation
        file_content = await file.read()

        # Run comprehensive security validation pipeline
        comprehensive_file_validation(file, file_content)

        # Log successful upload (without exposing filename or user data)
        file_size_mb = len(file_content) / (1024 * 1024)
        processing_time_ms = round((time.time() - request_start_time) * 1000, 2)
        
        logger.info(
            "Resume upload successful",
            extra={
                "content_type": file.content_type,
                "file_size_bytes": len(file_content),
                "file_size_mb": round(file_size_mb, 2),
                "processing_time_ms": processing_time_ms,
                "event": "upload_successful",
                "validation_passed": True
            }
        )

        # Queue file for background processing with Celery
        task_id = queue_resume_parsing_task(file_content, file.content_type)

        return ResumeUploadResponse(task_id=task_id)

    except SecurityValidationError as e:
        # Convert security validation errors to HTTP exceptions
        status_code = status.HTTP_400_BAD_REQUEST
        
        # Use specific status codes for certain error types
        if e.reason_code == "SECURITY_FILE_SIZE_VIOLATION":
            status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        elif e.reason_code in ["SECURITY_VIRUS_DETECTED", "SECURITY_EXECUTABLE_DETECTED"]:
            status_code = status.HTTP_400_BAD_REQUEST  # Security threat
        
        logger.error(
            "Security validation failed during upload",
            extra={
                "reason_code": e.reason_code,
                "error_message": str(e),
                "error_details": e.details,
                "event": "upload_security_violation",
                "processing_time_ms": round((time.time() - request_start_time) * 1000, 2)
            }
        )
        
        raise HTTPException(
            status_code=status_code,
            detail=str(e)
        )
    except HTTPException:
        # Re-raise HTTP exceptions (validation errors)
        raise
    except Exception as e:
        # Handle unexpected errors without exposing stack trace
        processing_time_ms = round((time.time() - request_start_time) * 1000, 2)
        
        logger.error(
            "Unexpected error during resume upload",
            extra={
                "error_type": type(e).__name__,
                "processing_time_ms": processing_time_ms,
                "event": "upload_failed",
                "error_category": "internal_error"
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the file",
        )
    finally:
        # Ensure file is closed
        await file.close()
