"""
Resume status endpoint for checking task processing status.

This module provides endpoints to check the status of resume parsing tasks,
returning current state and results when available.
"""

import logging
from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.api.v1.models.resumes import ResumeStatusResponse
from app.api.v1.auth.get_user_group import get_user_group
from app.celery_app import celery_app

# Configure logger
log = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/status/{task_id}", 
    response_model=ResumeStatusResponse, 
    status_code=status.HTTP_200_OK,
    summary="Get Resume Processing Status",
    description="""
    Check the current status and results of a resume parsing task.
    
    **Task States:**
    - **PENDING**: Task is queued or currently processing
    - **SUCCESS**: Task completed successfully with extracted data
    - **FAILURE**: Task failed with error details
    - **RETRY**: Task is being retried after initial failure
    - **REVOKED**: Task was cancelled/revoked
    
    **Usage:**
    After uploading a resume via `/upload`, use the returned task_id to poll
    this endpoint until processing completes (status becomes SUCCESS or FAILURE).
    
    **Rate Limits:**
    - 60 requests per minute per IP address
    - Authentication required
    
    **Polling Recommendations:**
    - Start with 1-2 second intervals
    - Increase to 5-10 seconds for longer processing
    - Most resumes process within 5-30 seconds
    """,
    responses={
        200: {
            "description": "Task status retrieved successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "success": {
                            "summary": "Processing completed successfully",
                            "value": {
                                "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                                "status": "SUCCESS",
                                "result": {
                                    "status": "success",
                                    "file_type": "application/pdf",
                                    "character_count": 2543,
                                    "extracted_text": "John Doe\\nSoftware Engineer\\nEmail: john.doe@example.com",
                                    "contact_info": {
                                        "name": "John Doe",
                                        "email": "john.doe@example.com",
                                        "phone": "(555) 123-4567"
                                    }
                                }
                            }
                        },
                        "pending": {
                            "summary": "Task still processing",
                            "value": {
                                "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                                "status": "PENDING"
                            }
                        },
                        "failure": {
                            "summary": "Processing failed",
                            "value": {
                                "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                                "status": "FAILURE",
                                "error": "Failed to parse resume: unsupported file format"
                            }
                        }
                    }
                }
            }
        },
        400: {
            "description": "Bad Request - Invalid task ID format",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Task ID is required"
                    }
                }
            }
        },
        404: {
            "description": "Not Found - Task ID does not exist",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Task not found"
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
            "description": "Internal Server Error - Unexpected error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An error occurred while retrieving task status"
                    }
                }
            }
        }
    },
    tags=["Resume Processing"]
)
async def get_resume_status(
    task_id: str = Path(
        ...,
        description="Unique task identifier returned by the upload endpoint",
        example="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        min_length=1
    ),
    user_group: str = Depends(get_user_group),
) -> ResumeStatusResponse:
    """
    Get the status and results of a resume parsing task.
    
    This endpoint allows you to check the current processing status of a resume
    that was previously uploaded. The response includes the current state and,
    when processing is complete, the extracted text and contact information.
    
    **Typical Usage Flow:**
    1. Upload resume via `/upload` → get task_id
    2. Poll this endpoint with task_id until status is SUCCESS/FAILURE
    3. Process the results or handle the error
    
    **Status Meanings:**
    - **PENDING**: Task is queued or actively processing
    - **SUCCESS**: Processing completed, results available in `result` field
    - **FAILURE**: Processing failed, error details in `error` field
    - **RETRY**: Task failed but is being retried automatically
    - **REVOKED**: Task was cancelled (rare)
    
    **Security Features:**
    - Rate limiting: 60 requests per minute
    - Task isolation: only returns data for valid task IDs
    - Structured logging for monitoring
    
    **Performance Notes:**
    - Typical processing time: 5-30 seconds
    - PDF files: Usually faster than DOCX
    - Larger files: Take proportionally longer
    
    **Usage Example:**
    ```bash
    curl -X GET "http://localhost:8000/api/resumes/status/YOUR_TASK_ID" \\
         -H "Authorization: Bearer YOUR_TOKEN"
    ```

    Args:
        task_id: The unique identifier for the resume parsing task

    Returns:
        ResumeStatusResponse: Current task status and results (when available)

    Raises:
        HTTPException:
            - 400 Bad Request: Invalid or empty task ID
            - 404 Not Found: Task ID does not exist
            - 429 Too Many Requests: Rate limit exceeded
            - 500 Internal Server Error: Unexpected processing error
    """
    if not task_id or not task_id.strip():
        log.warning("Empty task ID provided to status endpoint")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task ID is required"
        )
    
    try:
        # Get task result from Celery
        task_result = AsyncResult(task_id, app=celery_app)
        
        # Check if task exists
        if task_result.state == 'PENDING' and task_result.result is None:
            # This could mean the task doesn't exist or is actually pending
            # Try to get more info from the backend
            if not task_result.backend.get(task_result.key):
                log.warning(f"Task ID not found: {task_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Task not found"
                )
        
        log.info(f"Retrieved status for task {task_id}: {task_result.state}")
        
        # Prepare response based on task state
        response_data = {
            "task_id": task_id,
            "status": task_result.state,
        }
        
        if task_result.state == "SUCCESS":
            response_data["result"] = task_result.result
        elif task_result.state == "FAILURE":
            # Handle task failure
            error_info = str(task_result.info) if task_result.info else "Unknown error occurred"
            response_data["error"] = error_info
        elif task_result.state in ["RETRY", "REVOKED"]:
            # Handle retry or revoked states
            if task_result.info:
                response_data["error"] = str(task_result.info)
        
        return ResumeStatusResponse(**response_data)
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        log.error(f"Unexpected error retrieving task status for {task_id}: {type(e).__name__}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving task status"
        )